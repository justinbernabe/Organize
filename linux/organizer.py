"""Cross-platform file organizer engine.

Refactored from organize.py for use as an importable library.
Works on macOS (setattrlist for creation date) and Linux (mtime only).
Emits progress events via callback for WebSocket/UI consumption.
"""
import os
import re
import sys
import time
import shutil
import hashlib
import datetime
from pathlib import Path
from typing import Dict, Set, List, Tuple, Optional, Callable, Any

# ── Platform-specific creation date setter ────────────────────────────────

_IS_MACOS = sys.platform == "darwin"

if _IS_MACOS:
    try:
        import ctypes as _ct
        import ctypes.util as _ctu
        _libc = _ct.CDLL(_ctu.find_library('c'))

        class _Attrlist(_ct.Structure):
            _fields_ = [
                ('bitmapcount', _ct.c_ushort), ('reserved', _ct.c_uint16),
                ('commonattr', _ct.c_uint32), ('volattr', _ct.c_uint32),
                ('dirattr', _ct.c_uint32), ('fileattr', _ct.c_uint32),
                ('forkattr', _ct.c_uint32),
            ]

        class _Timespec(_ct.Structure):
            _fields_ = [('tv_sec', _ct.c_long), ('tv_nsec', _ct.c_long)]

        def _set_creation_date(path: str, ts: float) -> bool:
            al = _Attrlist()
            al.bitmapcount = 5
            al.commonattr = 0x00000200  # ATTR_CMN_CRTIME
            tv = _Timespec()
            tv.tv_sec = int(ts)
            tv.tv_nsec = int((ts % 1) * 1_000_000_000)
            return _libc.setattrlist(
                path.encode('utf-8'), _ct.byref(al), _ct.byref(tv),
                _ct.sizeof(tv), _ct.c_ulong(0)
            ) == 0
    except Exception:
        def _set_creation_date(path: str, ts: float) -> bool:
            return False
else:
    def _set_creation_date(path: str, ts: float) -> bool:
        return False  # Linux: btime not writable via standard syscalls


# ── Default configuration ─────────────────────────────────────────────────

DEFAULT_CATEGORIES: Dict[str, List[str]] = {
    "videos": [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v",
               ".3gp", ".rmvb", ".vob", ".m2ts", ".ts"],
    "images": [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".tif",
               ".ico", ".heic", ".raw", ".cr2", ".nef", ".arw", ".dng", ".svg"],
    "audio":  [".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg"],
    "text":   [".txt", ".pdf", ".docx", ".md", ".csv"],
    "misc":   [".html", ".htm", ".json", ".js", ".css", ".py", ".sh", ".zip", ".rar"],
}

DEFAULT_FOLDER_MAPPINGS: Dict[str, str] = {
    "pics": "images", "image": "images", "img": "images",
    "pictures": "images", "picture": "images",
    "photo": "images", "photos": "images",
    "vids": "videos", "video": "videos", "vid": "videos",
}

# ── Date extraction ───────────────────────────────────────────────────────

_RE_DATE_FULL = re.compile(r"(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})")
_RE_DATE_SEMI = re.compile(r"(\d{4})-(\d{2})-(\d{2})T(\d{2});(\d{2});(\d{2})")
_RE_DATE_DASH = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_RE_DATE_DOT  = re.compile(r"(\d{4})\.(\d{2})\.(\d{2})")


def extract_date_from_filename(name: str) -> Optional[datetime.datetime]:
    """Extract date from filename. Patterns: YYYYMMDDTHHMMSS, YYYY-MM-DDTHH;MM;SS, YYYY-MM-DD, YYYY.MM.DD"""
    for regex, has_time in [
        (_RE_DATE_FULL, True), (_RE_DATE_SEMI, True),
        (_RE_DATE_DASH, False), (_RE_DATE_DOT, False),
    ]:
        m = regex.search(name)
        if m:
            parts = list(map(int, m.groups()))
            try:
                if has_time:
                    return datetime.datetime(*parts)
                else:
                    return datetime.datetime(*parts, 0, 0, 0)
            except Exception:
                continue
    return None


# ── Progress event types ──────────────────────────────────────────────────

class ProgressEvent:
    """Progress event emitted by the engine."""
    def __init__(self, event_type: str, **kwargs):
        self.type = event_type
        self.data = kwargs

    def to_dict(self) -> dict:
        return {"type": self.type, **self.data}


# Event callback type
EventCallback = Callable[[ProgressEvent], None]


# ── Build extension lookup ────────────────────────────────────────────────

def build_ext_lookup(categories: Dict[str, List[str]]) -> Dict[str, str]:
    """Build flat ext→category dict for O(1) lookup."""
    lookup = {}
    for cat, exts in categories.items():
        for ext in exts:
            lookup[ext] = cat
    return lookup


# ── Folder normalization ──────────────────────────────────────────────────

def normalize_subfolders(root: str, mappings: Dict[str, str],
                         on_event: Optional[EventCallback] = None):
    """Normalize subfolder names using os.scandir + os.rename (fast on NAS)."""
    base = Path(root)
    if not base.exists() or not base.is_dir():
        return

    try:
        entries = [(e.name, e.path, e.is_dir(follow_symlinks=False))
                   for e in os.scandir(str(base))]
    except Exception:
        return

    dirs = [(name, path) for name, path, is_dir in entries if is_dir]

    for dir_name, dir_path in dirs:
        desired = mappings.get(dir_name.lower(), dir_name.lower())
        if dir_name == desired:
            continue

        target = base / desired

        try:
            if target.exists():
                try:
                    st_e = os.stat(dir_path)
                    st_t = target.stat()
                    if st_e.st_ino == st_t.st_ino and st_e.st_dev == st_t.st_dev:
                        import uuid
                        tmp = base / (desired + "_" + uuid.uuid4().hex)
                        os.rename(dir_path, str(tmp))
                        os.rename(str(tmp), str(target))
                        continue
                except Exception:
                    pass

            if target.exists():
                target.mkdir(exist_ok=True)
                try:
                    existing_names = set(e.name for e in os.scandir(str(target)))
                except Exception:
                    existing_names = set()

                try:
                    children = [(e.name, e.path) for e in os.scandir(dir_path)]
                except Exception:
                    children = []

                if on_event and len(children) > 50:
                    on_event(ProgressEvent("step", name=f"Merging {dir_name}/ → {desired}/",
                                           status="started", detail=f"{len(children)} items"))

                for child_name, child_path in children:
                    dest_name = child_name
                    if dest_name in existing_names:
                        stem = Path(child_name).stem
                        suffix = Path(child_name).suffix
                        counter = 1
                        dest_name = f"{stem}_{counter}{suffix}"
                        while dest_name in existing_names:
                            counter += 1
                            dest_name = f"{stem}_{counter}{suffix}"

                    try:
                        os.rename(child_path, str(target / dest_name))
                    except OSError:
                        shutil.move(child_path, str(target / dest_name))
                    existing_names.add(dest_name)

                try:
                    os.rmdir(dir_path)
                except Exception:
                    pass
            else:
                os.rename(dir_path, str(target))
        except Exception:
            continue


# ── Main organize engine ──────────────────────────────────────────────────

class OrganizeResult:
    """Result of an organize run."""
    def __init__(self):
        self.files_moved = 0
        self.bytes_moved = 0
        self.dates_set = 0
        self.errors = 0
        self.elapsed = 0.0

    def to_dict(self) -> dict:
        return {
            "files_moved": self.files_moved,
            "bytes_moved": self.bytes_moved,
            "dates_set": self.dates_set,
            "errors": self.errors,
            "elapsed": round(self.elapsed, 2),
            "files_per_sec": round(self.files_moved / self.elapsed, 1) if self.elapsed > 0.1 else 0,
        }


def organize_folder(
    root_path: str,
    settings: Optional[dict] = None,
    on_event: Optional[EventCallback] = None,
    dry_run: bool = False,
) -> OrganizeResult:
    """Organize a folder using a single-pass architecture.

    Args:
        root_path: Path to folder to organize.
        settings: Dict with keys matching config.py defaults. None = use defaults.
        on_event: Callback for progress events (for WebSocket streaming).
        dry_run: If True, compute operations but don't execute them.

    Returns:
        OrganizeResult with stats.
    """
    s = settings or {}
    categories = s.get("categories", DEFAULT_CATEGORIES)
    folder_mappings = s.get("folder_mappings", DEFAULT_FOLDER_MAPPINGS)
    set_mtime = s.get("set_modified_date", True)
    enable_moving = s.get("enable_file_moving", True)
    name_scheme = s.get("name_scheme", "lowercase")

    ext_lookup = build_ext_lookup(categories)
    category_names = set(categories.keys())

    root = Path(root_path)
    result = OrganizeResult()
    start_time = time.time()
    max_future = datetime.datetime.now() + datetime.timedelta(days=1)
    dir_latest: Dict[Path, float] = {}
    planned_ops: List[dict] = []  # For dry run

    def emit(event_type: str, **kwargs):
        if on_event:
            on_event(ProgressEvent(event_type, **kwargs))

    emit("step", name="Normalizing folder names", status="started")
    normalize_subfolders(root_path, folder_mappings, on_event=on_event)
    emit("step", name="Normalizing folder names", status="completed")

    # ── Scan files ────────────────────────────────────────────────────
    emit("step", name="Scanning files", status="started")
    files: List[Tuple[Path, int]] = []
    try:
        for entry in os.scandir(root_path):
            if (entry.is_file(follow_symlinks=False)
                    and not entry.name.startswith('.')
                    and entry.name != "organize.py"):
                try:
                    sz = entry.stat(follow_symlinks=False).st_size
                except Exception:
                    sz = 0
                files.append((Path(entry.path), sz))
    except Exception:
        pass

    total = len(files)
    emit("step", name="Scanning files", status="completed",
         summary=f"{total} files found")

    if total == 0 and not set_mtime:
        result.elapsed = time.time() - start_time
        emit("complete", **result.to_dict())
        return result

    # ── Pre-create category folders ───────────────────────────────────
    if enable_moving and not dry_run:
        needed = set()
        for fpath, _ in files:
            ext = fpath.suffix.lower()
            needed.add(ext_lookup.get(ext, "misc"))
        for cat in needed:
            try:
                (root / cat).mkdir(exist_ok=True)
            except Exception:
                pass

    # ── Single-pass: move + set dates ─────────────────────────────────
    emit("step", name="Organizing files", status="started")
    last_progress = time.time()

    for i, (item, item_size) in enumerate(files, 1):
        now = time.time()
        if now - last_progress >= 0.25 or i == total:
            last_progress = now
            elapsed = now - start_time
            fps = result.files_moved / elapsed if elapsed > 0.1 else 0
            bps = result.bytes_moved / elapsed if elapsed > 0.1 else 0
            emit("progress", current=i, total=total,
                 files_per_sec=round(fps, 1),
                 throughput=_format_bytes(int(bps)) + "/s")

        # Skip files already in category folders
        parent_name = item.parent.name.lower()
        if parent_name in category_names:
            continue

        ext = item.suffix.lower()
        cat = ext_lookup.get(ext, "misc")
        dest_folder = root / cat
        dest_path = dest_folder / item.name

        try:
            if enable_moving:
                # Handle name collisions
                if dest_path.exists():
                    try:
                        st_i = item.stat()
                        st_d = dest_path.stat()
                        if st_i.st_ino == st_d.st_ino and st_i.st_dev == st_d.st_dev:
                            result.files_moved += 1
                            result.bytes_moved += item_size
                            continue
                    except Exception:
                        pass

                    stem, suffix, counter = item.stem, item.suffix, 1
                    while dest_path.exists():
                        dest_path = dest_folder / f"{stem}_{counter}{suffix}"
                        counter += 1

                if dry_run:
                    planned_ops.append({"source": str(item), "dest": str(dest_path),
                                        "type": "move", "size": item_size})
                else:
                    os.rename(str(item), str(dest_path))

                result.files_moved += 1
                result.bytes_moved += item_size

            # Set dates inline
            final_path = dest_path if enable_moving else item
            if set_mtime and not dry_run:
                dt = extract_date_from_filename(final_path.name)
                if dt and dt <= max_future:
                    ts = dt.timestamp()
                    try:
                        os.utime(str(final_path), (ts, ts))
                        _set_creation_date(str(final_path), ts)
                        result.dates_set += 1
                    except Exception:
                        pass

            # Collect mtime for dir propagation
            if not dry_run:
                try:
                    m = os.stat(str(final_path)).st_mtime
                    curr = final_path.parent
                    while True:
                        prev = dir_latest.get(curr)
                        if prev is None or m > prev:
                            dir_latest[curr] = m
                        if curr == root:
                            break
                        curr = curr.parent
                except Exception:
                    pass

        except Exception:
            result.errors += 1

    emit("step", name="Organizing files", status="completed",
         summary=f"{result.files_moved} moved, {result.errors} errors")

    # ── Set dates on files already in category folders ────────────────
    if set_mtime and not dry_run:
        for cat in category_names:
            cat_dir = root / cat
            if not cat_dir.exists():
                continue
            try:
                for entry in os.scandir(str(cat_dir)):
                    if not entry.is_file(follow_symlinks=False) or entry.name.startswith('.'):
                        continue
                    dt = extract_date_from_filename(entry.name)
                    if not dt or dt > max_future:
                        continue
                    ts = dt.timestamp()
                    try:
                        os.utime(entry.path, (ts, ts))
                        _set_creation_date(entry.path, ts)
                        result.dates_set += 1
                    except Exception:
                        pass
                    try:
                        m = os.stat(entry.path).st_mtime
                        curr = Path(entry.path).parent
                        while True:
                            prev = dir_latest.get(curr)
                            if prev is None or m > prev:
                                dir_latest[curr] = m
                            if curr == root:
                                break
                            curr = curr.parent
                    except Exception:
                        pass
            except Exception:
                continue

    # ── Propagate directory timestamps ────────────────────────────────
    if not dry_run:
        emit("step", name="Updating timestamps", status="started")
        for _ in range(2):
            for d, mtime in dir_latest.items():
                try:
                    os.utime(str(d), (mtime, mtime))
                except Exception:
                    continue
            try:
                parent = root.parent
                if parent.exists() and parent.is_dir():
                    mtime = root.stat().st_mtime
                    os.utime(str(parent), (mtime, mtime))
            except Exception:
                pass
        emit("step", name="Updating timestamps", status="completed")

    result.elapsed = time.time() - start_time
    emit("complete", **result.to_dict())

    if dry_run:
        result._planned_ops = planned_ops

    return result


def _format_bytes(b: int) -> str:
    if b < 1024:
        return f"{b} B"
    elif b < 1024 * 1024:
        return f"{b / 1024:.0f} KB"
    elif b < 1024 * 1024 * 1024:
        return f"{b / (1024 * 1024):.1f} MB"
    else:
        return f"{b / (1024 * 1024 * 1024):.2f} GB"
