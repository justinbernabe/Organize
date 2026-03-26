import os
import shutil
import subprocess
import time
from pathlib import Path
import sys
import re
import datetime
import hashlib
import shlex
import atexit
from typing import List, Optional, Dict, Set, Tuple

# ── Extension → category lookup (O(1) via dict, not nested loop) ─────────
_DIRECTORIES = {
    "videos": [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v",
               ".3gp", ".rmvb", ".vob", ".m2ts", ".ts"],
    "images": [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".tif",
               ".ico", ".heic", ".raw", ".cr2", ".nef", ".arw", ".dng", ".svg"],
    "audio":  [".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg"],
    "text":   [".txt", ".pdf", ".docx", ".md", ".csv"],
    "misc":   [".html", ".htm", ".json", ".js", ".css", ".py", ".sh", ".zip", ".rar"]
}
# Flat lookup: ".mp4" → "videos", ".jpg" → "images", etc.
_EXT_TO_CATEGORY: Dict[str, str] = {}
for _cat, _exts in _DIRECTORIES.items():
    for _ext in _exts:
        _EXT_TO_CATEGORY[_ext] = _cat
_CATEGORY_NAMES: Set[str] = set(_DIRECTORIES.keys())

# Pre-compiled date extraction patterns (compiled once at import time)
_RE_DATE_FULL = re.compile(r"(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})")
_RE_DATE_SEMI = re.compile(r"(\d{4})-(\d{2})-(\d{2})T(\d{2});(\d{2});(\d{2})")
_RE_DATE_DASH = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_RE_DATE_DOT  = re.compile(r"(\d{4})\.(\d{2})\.(\d{2})")

# macOS creation-date setter via setattrlist syscall
try:
    import ctypes as _ct
    import ctypes.util as _ctu
    _libc = _ct.CDLL(_ctu.find_library('c'))

    class _Attrlist(_ct.Structure):
        _fields_ = [
            ('bitmapcount', _ct.c_ushort), ('reserved',   _ct.c_uint16),
            ('commonattr',  _ct.c_uint32), ('volattr',    _ct.c_uint32),
            ('dirattr',     _ct.c_uint32), ('fileattr',   _ct.c_uint32),
            ('forkattr',    _ct.c_uint32),
        ]

    class _Timespec(_ct.Structure):
        _fields_ = [('tv_sec', _ct.c_long), ('tv_nsec', _ct.c_long)]

    _ATTR_CMN_CRTIME = 0x00000200

    def _set_creation_date(path: str, ts: float) -> bool:
        """Set macOS file creation (birth) time via setattrlist."""
        al = _Attrlist(); al.bitmapcount = 5; al.commonattr = _ATTR_CMN_CRTIME
        tv = _Timespec(); tv.tv_sec = int(ts); tv.tv_nsec = int((ts % 1) * 1_000_000_000)
        return _libc.setattrlist(
            path.encode('utf-8'), _ct.byref(al), _ct.byref(tv),
            _ct.sizeof(tv), _ct.c_ulong(0)
        ) == 0

except Exception:
    def _set_creation_date(path: str, ts: float) -> bool:  # type: ignore
        return False


# ── Notifications ─────────────────────────────────────────────────────────

def _notify(msg: str, subtitle: str = ""):
    """Fire a macOS Notification Center banner."""
    try:
        script = f'display notification "{msg}" with title "File Organizer"'
        if subtitle:
            script += f' subtitle "{subtitle}"'
        subprocess.Popen(
            ['osascript', '-e', script],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    except Exception:
        pass


def notify_start(folder_name: str):
    _notify(f"Organizing {folder_name}…")


def notify_final(total_success, total_errors, elapsed=0.0):
    msg = f"Done — {total_success} file{'s' if total_success != 1 else ''} organized"
    if elapsed > 0:
        msg += f" in {elapsed:.1f}s"
    msg += "."
    if total_errors > 0:
        msg += f" ({total_errors} error{'s' if total_errors != 1 else ''})"
    print(f"\n✓ {msg}")
    _notify(msg)


# ── Date extraction ───────────────────────────────────────────────────────

def extract_date_from_filename(name: str):
    """Extract a datetime from a filename. Returns datetime or None.

    Patterns: YYYYMMDDTHHMMSS, YYYY-MM-DDTHH;MM;SS, YYYY-MM-DD, YYYY.MM.DD
    """
    m = _RE_DATE_FULL.search(name)
    if m:
        y, mo, d, h, mi, s = map(int, m.groups())
        try:
            return datetime.datetime(y, mo, d, h, mi, s)
        except Exception:
            return None

    m = _RE_DATE_SEMI.search(name)
    if m:
        y, mo, d, h, mi, s = map(int, m.groups())
        try:
            return datetime.datetime(y, mo, d, h, mi, s)
        except Exception:
            return None

    m = _RE_DATE_DASH.search(name)
    if m:
        y, mo, d = map(int, m.groups())
        try:
            return datetime.datetime(y, mo, d, 0, 0, 0)
        except Exception:
            return None

    m = _RE_DATE_DOT.search(name)
    if m:
        y, mo, d = map(int, m.groups())
        try:
            return datetime.datetime(y, mo, d, 0, 0, 0)
        except Exception:
            return None

    return None


# ── Folder normalization ──────────────────────────────────────────────────

def normalize_subfolders(paths):
    """Normalize subfolder names: Pics→images, Vids→videos, etc."""
    MAPPINGS = {
        "pics": "images", "image": "images", "img": "images",
        "pictures": "images", "picture": "images",
        "photo": "images", "photos": "images",
        "vids": "videos", "video": "videos", "vid": "videos",
    }

    for p in paths:
        base = Path(p)
        if not base.exists() or not base.is_dir():
            continue

        for entry in list(base.iterdir()):
            if not entry.is_dir():
                continue

            desired = MAPPINGS.get(entry.name.lower(), entry.name.lower())
            if entry.name == desired:
                continue

            target = base / desired

            try:
                if target.exists():
                    try:
                        st_e = entry.stat()
                        st_t = target.stat()
                        if st_e.st_ino == st_t.st_ino and st_e.st_dev == st_t.st_dev:
                            import uuid
                            tmp = base / (desired + "_" + uuid.uuid4().hex)
                            entry.rename(tmp)
                            tmp.rename(target)
                            continue
                    except Exception:
                        pass

                if target.exists():
                    target.mkdir(exist_ok=True)
                    for child in list(entry.iterdir()):
                        dest = target / child.name
                        if dest.exists():
                            stem, suffix, counter = child.stem, child.suffix, 1
                            new_dest = target / f"{stem}_{counter}{suffix}"
                            while new_dest.exists():
                                counter += 1
                                new_dest = target / f"{stem}_{counter}{suffix}"
                            dest = new_dest
                        shutil.move(str(child), str(dest))
                    try:
                        entry.rmdir()
                    except Exception:
                        pass
                else:
                    entry.rename(target)
            except Exception:
                continue


# ── Performance tracker ───────────────────────────────────────────────────

class _PerfTracker:
    """Tracks files/sec and bytes moved for live performance display."""

    def __init__(self):
        self.start_time = time.time()
        self.files_moved = 0
        self.bytes_moved = 0
        self.dates_set = 0
        self._last_print = 0.0

    def record_move(self, size_bytes: int):
        self.files_moved += 1
        self.bytes_moved += size_bytes

    def record_date(self):
        self.dates_set += 1

    @property
    def elapsed(self) -> float:
        return time.time() - self.start_time

    @property
    def files_per_sec(self) -> float:
        e = self.elapsed
        return self.files_moved / e if e > 0.1 else 0.0

    def _format_bytes(self, b: int) -> str:
        if b < 1024:
            return f"{b} B"
        elif b < 1024 * 1024:
            return f"{b / 1024:.0f} KB"
        elif b < 1024 * 1024 * 1024:
            return f"{b / (1024 * 1024):.1f} MB"
        else:
            return f"{b / (1024 * 1024 * 1024):.2f} GB"

    def progress_line(self, current: int, total: int, phase: str) -> str:
        e = self.elapsed
        pct = int(100 * current / total) if total else 100
        bar_w = 20
        filled = pct * bar_w // 100
        bar = '█' * filled + '░' * (bar_w - filled)
        fps = self.files_moved / e if e > 0.1 else 0.0
        throughput = self._format_bytes(int(self.bytes_moved / e)) if e > 0.1 else "—"
        return f"\r    [{bar}] {pct:3d}%  {current}/{total}  {fps:.0f} files/s  {throughput}/s"

    def print_progress(self, current: int, total: int, phase: str):
        now = time.time()
        if current < total and now - self._last_print < 0.25:
            return
        self._last_print = now
        try:
            print(self.progress_line(current, total, phase), end='', flush=True)
        except Exception:
            pass

    def summary(self) -> str:
        e = self.elapsed
        fps = self.files_moved / e if e > 0.1 else 0.0
        throughput = self._format_bytes(int(self.bytes_moved / e)) if e > 0.1 else "—"
        parts = [
            f"{self.files_moved} files moved",
            f"{self._format_bytes(self.bytes_moved)} total",
            f"{e:.1f}s elapsed",
            f"{fps:.0f} files/s",
            f"{throughput}/s throughput",
        ]
        if self.dates_set > 0:
            parts.append(f"{self.dates_set} dates set")
        return "  ✓ " + " · ".join(parts)


# ── Single-pass organize + date setting ───────────────────────────────────

def organize_folder(root_path, notify=True, _processed_roots=None):
    """Process a single root path end-to-end with a single-pass architecture.

    Pipeline:
    1. Normalize subfolder names
    2. Single scan: collect files via os.scandir (fast, cached)
    3. Single loop: move file + set dates from filename — one pass
    4. Propagate directory timestamps from collected data (no re-scan)
    5. Recursively process nested 'coomer' subfolders
    """
    processed = _processed_roots if _processed_roots is not None else set()
    root = str(root_path)
    resolved_root = str(Path(root).resolve())
    if resolved_root in processed:
        return 0, 0
    processed.add(resolved_root)

    folder_label = Path(root).name or root
    print(f"\n[{folder_label}]", flush=True)
    if notify:
        notify_start(folder_label)

    perf = _PerfTracker()
    skip_dates = bool(os.environ.get('ORGANIZE_SKIP_DATE_APPLY'))
    max_future = datetime.datetime.now() + datetime.timedelta(days=1)
    dbg = bool(os.environ.get('ORGANIZE_DEBUG'))

    # ── Step 1: Normalize subfolder names ─────────────────────────────────
    print("  ► Normalizing folder names...", flush=True)
    normalize_subfolders([root])

    # ── Step 2: Single scan with os.scandir (minimal SMB round-trips) ─────
    print("  ► Scanning files...", flush=True)
    root_path_obj = Path(root)
    files_to_process: List[Tuple[Path, int]] = []  # (path, size)

    try:
        for entry in os.scandir(root):
            if entry.is_file(follow_symlinks=False) and not entry.name.startswith('.') and entry.name != "organize.py":
                try:
                    sz = entry.stat(follow_symlinks=False).st_size
                except Exception:
                    sz = 0
                files_to_process.append((Path(entry.path), sz))
    except Exception:
        pass

    total_files = len(files_to_process)
    if total_files == 0:
        print("  ✓ No files to organize.", flush=True)
    else:
        print(f"  ► {total_files} file{'s' if total_files != 1 else ''} to organize", flush=True)

    # ── Step 3: Pre-create target folders in one batch ────────────────────
    # Figure out which category folders we need, create them all upfront
    # to avoid per-file exists()/mkdir() round-trips.
    needed_categories: Set[str] = set()
    for fpath, _ in files_to_process:
        ext = fpath.suffix.lower()
        cat = _EXT_TO_CATEGORY.get(ext, "misc")
        needed_categories.add(cat)

    created_folders: Set[str] = set()
    for cat in needed_categories:
        cat_dir = root_path_obj / cat
        try:
            cat_dir.mkdir(exist_ok=True)
            created_folders.add(cat)
        except Exception:
            pass

    # ── Step 4: Move + set dates in a single pass ─────────────────────────
    # For each file: os.rename (same volume = atomic), then set dates inline.
    # Also collect file mtimes for directory timestamp propagation (no re-scan).
    success_count = 0
    error_count = 0
    dir_latest: Dict[Path, float] = {}  # dir → max mtime of child files

    for index, (item, item_size) in enumerate(files_to_process, 1):
        perf.print_progress(index, total_files, "Organizing")

        # Skip files already in a canonical folder
        parent_name = item.parent.name.lower()
        if parent_name in _CATEGORY_NAMES:
            continue

        ext = item.suffix.lower()
        cat = _EXT_TO_CATEGORY.get(ext, "misc")
        dest_folder = root_path_obj / cat
        dest_path = dest_folder / item.name

        try:
            # Handle name collisions (no hash, just suffix)
            if dest_path.exists():
                try:
                    st_item = item.stat()
                    st_dest = dest_path.stat()
                    if st_item.st_ino == st_dest.st_ino and st_item.st_dev == st_dest.st_dev:
                        success_count += 1
                        continue
                except Exception:
                    pass

                stem, suffix, counter = item.stem, item.suffix, 1
                while dest_path.exists():
                    dest_path = dest_folder / f"{stem}_{counter}{suffix}"
                    counter += 1

            # os.rename = atomic on same volume, no copy overhead
            os.rename(str(item), str(dest_path))
            perf.record_move(item_size)
            success_count += 1

            # ── Inline date setting (no separate rglob pass) ──────────
            if not skip_dates:
                dt = extract_date_from_filename(dest_path.name)
                if dt and dt <= max_future:
                    ts = dt.timestamp()
                    try:
                        os.utime(str(dest_path), (ts, ts))
                        _set_creation_date(str(dest_path), ts)
                        perf.record_date()
                    except Exception:
                        pass

            # ── Collect mtime for dir timestamp propagation ───────────
            try:
                m = dest_path.stat().st_mtime
                curr = dest_path.parent
                while True:
                    prev = dir_latest.get(curr)
                    if prev is None or m > prev:
                        dir_latest[curr] = m
                    if curr == root_path_obj:
                        break
                    curr = curr.parent
            except Exception:
                pass

        except Exception:
            error_count += 1

    # Clear progress line
    if total_files > 0:
        print(flush=True)

    # ── Step 5: Also set dates on files already in category folders ───────
    # These were skipped by the move loop. Scan category dirs for date-only.
    if not skip_dates:
        date_only_count = 0
        for cat in created_folders | _CATEGORY_NAMES:
            cat_dir = root_path_obj / cat
            if not cat_dir.exists():
                continue
            try:
                for entry in os.scandir(str(cat_dir)):
                    if not entry.is_file(follow_symlinks=False) or entry.name.startswith('.'):
                        continue
                    # Skip files we already processed (they were moved into this folder)
                    # We can't easily track this, so just check if date is already set.
                    # This is cheap: just regex on the name, no stat.
                    dt = extract_date_from_filename(entry.name)
                    if not dt or dt > max_future:
                        continue
                    ts = dt.timestamp()
                    try:
                        os.utime(entry.path, (ts, ts))
                        _set_creation_date(entry.path, ts)
                        perf.record_date()
                        date_only_count += 1
                    except Exception:
                        pass
                    # Collect mtime for dir propagation
                    try:
                        m = os.stat(entry.path).st_mtime
                        curr = Path(entry.path).parent
                        while True:
                            prev = dir_latest.get(curr)
                            if prev is None or m > prev:
                                dir_latest[curr] = m
                            if curr == root_path_obj:
                                break
                            curr = curr.parent
                    except Exception:
                        pass
            except Exception:
                continue

    # ── Step 6: Recursively organize nested 'coomer' subfolders ───────────
    nested_success = 0
    nested_errors = 0
    try:
        for d in root_path_obj.iterdir():
            try:
                if d.is_dir() and d.name.lower() == 'coomer':
                    d_res = str(d.resolve())
                    if d_res in processed:
                        continue
                    s, e = organize_folder(str(d), notify=False, _processed_roots=processed)
                    nested_success += s
                    nested_errors += e
            except Exception:
                continue
    except Exception:
        pass

    # ── Step 7: Propagate directory timestamps from collected data ─────────
    # No rglob needed — we already collected all file mtimes during the move.
    # Run once to set dirs, then once more to fix .DS_Store bumps.
    print("  ► Updating timestamps...", flush=True)
    for _ in range(2):
        for d, mtime in dir_latest.items():
            try:
                os.utime(str(d), (mtime, mtime))
            except Exception:
                continue
        # Propagate root mtime to parent
        try:
            parent = root_path_obj.parent
            if parent.exists() and parent.is_dir():
                mtime = root_path_obj.stat().st_mtime
                os.utime(str(parent), (mtime, mtime))
        except Exception:
            pass

    # ── Performance summary ───────────────────────────────────────────────
    print(perf.summary(), flush=True)

    total_success = success_count + nested_success
    total_errors = error_count + nested_errors

    if notify and (total_success > 0 or total_errors > 0):
        notify_final(total_success, total_errors, elapsed=perf.elapsed)

    return total_success, total_errors


# ── find_and_remove_duplicates (kept but not called) ──────────────────────
# Retained for future re-enablement. Not part of the hot path.

def find_and_remove_duplicates(root_path, ticker=None):
    """3-phase duplicate scan. CURRENTLY DISABLED in organize_folder()."""
    PARTIAL_BYTES = 64 * 1024
    root = Path(root_path)
    dupes_dir = root / 'DUPES'

    def _is_coomer(p: Path) -> bool:
        try:
            return any(part.lower() == 'coomer' for part in p.relative_to(root).parts)
        except Exception:
            return False

    def _hash(path: Path, limit: int = 0) -> Optional[str]:
        try:
            h = hashlib.sha1()
            with open(path, 'rb') as fh:
                if limit:
                    h.update(fh.read(limit))
                else:
                    for chunk in iter(lambda: fh.read(65536), b''):
                        h.update(chunk)
            return h.hexdigest()
        except Exception:
            return None

    size_map: dict = {}
    for f in root.rglob('*'):
        if not f.is_file() or f.name.startswith('.'):
            continue
        try:
            rel = f.relative_to(root)
            if rel.parts[0] == 'DUPES':
                continue
            sz = f.stat().st_size
            if sz == 0:
                continue
            size_map.setdefault(sz, []).append(f)
        except Exception:
            continue

    candidates_p2 = [(sz, p) for sz, paths in size_map.items() if len(paths) >= 2 for p in paths]
    partial_map: dict = {}
    for i, (sz, p) in enumerate(candidates_p2, 1):
        ph = _hash(p, limit=PARTIAL_BYTES)
        if ph is None:
            continue
        partial_map.setdefault((sz, ph), []).append(p)

    moved = 0
    for _, paths in partial_map.items():
        if len(paths) < 2:
            continue
        full_map: dict = {}
        for p in paths:
            fh = _hash(p)
            if fh is None:
                continue
            full_map.setdefault(fh, []).append(p)

        for dupe_paths in full_map.values():
            if len(dupe_paths) < 2:
                continue
            coomer_copies = [p for p in dupe_paths if _is_coomer(p)]
            other_copies = [p for p in dupe_paths if not _is_coomer(p)]
            if coomer_copies:
                to_remove = other_copies
            else:
                sorted_by_age = sorted(dupe_paths, key=lambda p: p.stat().st_mtime)
                to_remove = sorted_by_age[1:]
            for dup in to_remove:
                try:
                    dupes_dir.mkdir(exist_ok=True)
                    dup_target = dupes_dir / dup.name
                    counter = 1
                    while dup_target.exists():
                        dup_target = dupes_dir / f"{dup.stem}_{counter}{dup.suffix}"
                        counter += 1
                    shutil.move(str(dup), str(dup_target))
                    moved += 1
                except Exception:
                    pass
    return moved


# ── Terminal log + entry point (unchanged) ────────────────────────────────

class _Tee:
    """Write to multiple streams at once."""
    def __init__(self, *streams):
        self.streams = streams

    def write(self, data):
        for s in self.streams:
            try:
                s.write(data)
                s.flush()
            except Exception:
                pass

    def flush(self):
        for s in self.streams:
            try:
                s.flush()
            except Exception:
                pass

    def fileno(self):
        for s in self.streams:
            try:
                return s.fileno()
            except Exception:
                pass
        raise OSError("no fileno")

    @property
    def encoding(self):
        for s in self.streams:
            enc = getattr(s, 'encoding', None)
            if enc:
                return enc
        return 'utf-8'


def _open_log_terminal(log_path: str):
    """Open a Terminal window that live-tails the log file."""
    try:
        safe = shlex.quote(log_path)
        applescript = (
            'tell application "Terminal"\n'
            '    activate\n'
            f'    do script "echo \'organize.py — live log\'; tail -f {safe}"\n'
            'end tell'
        )
        subprocess.Popen(
            ['osascript', '-e', applescript],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        time.sleep(0.6)
    except Exception:
        pass


if __name__ == "__main__":
    LOG_PATH = '/tmp/organize_latest.log'
    LOCK_PATH = '/tmp/organize_terminal.lock'
    _log_fh = None
    _owns_lock = False

    def _is_pid_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False

    def _try_acquire_lock() -> bool:
        try:
            fd = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return True
        except (FileExistsError, OSError):
            return False

    def _cleanup_lock():
        try:
            os.unlink(LOCK_PATH)
        except OSError:
            pass

    try:
        _owns_lock = _try_acquire_lock()
        if not _owns_lock:
            try:
                with open(LOCK_PATH, 'r') as lf:
                    lock_pid = int(lf.read().strip())
                if not _is_pid_alive(lock_pid):
                    _cleanup_lock()
                    _owns_lock = _try_acquire_lock()
            except Exception:
                pass

        if _owns_lock:
            atexit.register(_cleanup_lock)
            _log_fh = open(LOG_PATH, 'w', buffering=1, encoding='utf-8', errors='replace')
            if not sys.stdout.isatty():
                _open_log_terminal(LOG_PATH)
        else:
            _log_fh = open(LOG_PATH, 'a', buffering=1, encoding='utf-8', errors='replace')

        sys.stdout = _Tee(sys.__stdout__, _log_fh)
    except Exception:
        pass

    if len(sys.argv) > 1:
        overall_start = time.time()
        total_success = 0
        total_errors = 0

        for root in sys.argv[1:]:
            try:
                s, e = organize_folder(root, notify=False)
                total_success += s
                total_errors += e
            except SystemExit:
                break
            except Exception:
                continue

        overall_elapsed = time.time() - overall_start
        if total_success > 0 or total_errors > 0:
            notify_final(total_success, total_errors, elapsed=overall_elapsed)
    else:
        print("No files provided.")

    if _log_fh:
        try:
            _log_fh.close()
        except Exception:
            pass
