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
from typing import List, Optional

# Pre-compiled date extraction patterns (compiled once at import time, not per-file)
_RE_DATE_FULL    = re.compile(r"(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})")
_RE_DATE_SEMI    = re.compile(r"(\d{4})-(\d{2})-(\d{2})T(\d{2});(\d{2});(\d{2})")
_RE_DATE_DASH    = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_RE_DATE_DOT     = re.compile(r"(\d{4})\.(\d{2})\.(\d{2})")
_RE_DATE_COMPACT = re.compile(r"(?<!\d)(\d{4})(\d{2})(\d{2})(?!\d)")

# macOS creation-date setter via setattrlist syscall (replaces SetFile subprocess)
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
        """Set macOS file creation (birth) time via setattrlist — no subprocess."""
        al = _Attrlist(); al.bitmapcount = 5; al.commonattr = _ATTR_CMN_CRTIME
        tv = _Timespec(); tv.tv_sec = int(ts); tv.tv_nsec = int((ts % 1) * 1_000_000_000)
        return _libc.setattrlist(
            path.encode('utf-8'), _ct.byref(al), _ct.byref(tv),
            _ct.sizeof(tv), _ct.c_ulong(0)
        ) == 0

except Exception:
    def _set_creation_date(path: str, ts: float) -> bool:  # type: ignore
        return False


def update_progress(current, total, filename):
    """No-op progress updater.

    Removed macOS GUI progress. When `ORGANIZE_DEBUG` is set the function
    will print a concise progress line to stdout; otherwise it is silent.
    """
    if os.environ.get('ORGANIZE_DEBUG'):
        try:
            print(f"[{current}/{total}] {filename}")
        except Exception:
            pass

def _notify(msg: str, subtitle: str = ""):
    """Fire a macOS Notification Center banner — no click required, auto-dismisses."""
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
    """Banner shown when a folder starts processing."""
    _notify(f"Organizing {folder_name}…")


def notify_final(total_success, total_errors):
    """Banner shown when all processing is complete."""
    msg = f"Done — {total_success} file{'s' if total_success != 1 else ''} organized."
    if total_errors > 0:
        msg += f" ({total_errors} error{'s' if total_errors != 1 else ''})"
    print(f"\n✓ {msg}")
    _notify(msg)

def get_items(paths):
    """Gathers all files to be processed from the selection."""
    to_process = []
    recursive = bool(os.environ.get('ORGANIZE_RECURSIVE'))
    for p in paths:
        path = Path(p)
        if not path.exists():
            continue
        if path.is_dir():
            if recursive:
                count = 0
                last_print = time.time()
                for f in path.rglob('*'):
                    if f.is_file():
                        to_process.append(f)
                        count += 1
                    # print progress every 500 files or every 2 seconds
                    now = time.time()
                    if count and (count % 500 == 0 or now - last_print > 2):
                        last_print = now
                            # progress messaging intentionally suppressed
            else:
                to_process.extend([f for f in path.iterdir() if f.is_file()])
        else:
            to_process.append(path)
    # Filter out hidden files and the script itself
    filtered = [i for i in to_process if not i.name.startswith('.') and i.name != "organize.py"]
    # debug listing suppressed to avoid noisy output
    return filtered


def normalize_subfolders(paths):
    """Normalize subfolder names under each provided directory.
    - Map common variants to canonical names (e.g. Pics -> images, Vids/Video -> videos)
    - Otherwise ensure subfolder names are lowercase
    - Merge contents when the target name already exists, with duplicate protection
    """
    MAPPINGS = {
        "pics": "images",
        "image": "images",
        "img": "images",
        "pictures": "images",
        "picture": "images",
        "photo": "images",
        "photos": "images",
        "vids": "videos",
        "video": "videos",
        "videos": "videos",
        "vid": "videos",
    }

    for p in paths:
        base = Path(p)
        if not base.exists() or not base.is_dir():
            continue

        for entry in list(base.iterdir()):
            if not entry.is_dir():
                continue

            desired = MAPPINGS.get(entry.name.lower(), entry.name.lower())
            # If name already matches desired, skip
            if entry.name == desired:
                continue

            target = base / desired

            try:
                # Special-case case-only rename on case-insensitive filesystems.
                # On macOS HFS/APFS a directory named "Twitter" and one named
                # "twitter" are actually the same inode; ``target.exists()`` will
                # be True but ``entry`` and ``target`` refer to the same folder.
                # The previous merge behaviour would attempt to move the contents
                # of ``entry`` into itself and then ``rmdir`` it, effectively
                # deleting the directory.  We detect this situation by comparing
                # inode/device numbers and perform a two-step rename through a
                # unique temporary name so that the case-change takes effect.
                if target.exists():
                    try:
                        st_e = entry.stat()
                        st_t = target.stat()
                        if (st_e.st_ino == st_t.st_ino and
                                st_e.st_dev == st_t.st_dev):
                            # same underlying directory, just adjust case
                            import uuid
                            tmp = base / (desired + "_" + uuid.uuid4().hex)
                            entry.rename(tmp)
                            tmp.rename(target)
                            # done, move on to next entry
                            continue
                    except Exception:
                        # if we can't stat the paths for some reason, fall
                        # back to the normal merge logic below
                        pass

                if target.exists():
                    # Merge contents from entry into target
                    target.mkdir(exist_ok=True)
                    for child in list(entry.iterdir()):
                        dest = target / child.name
                        if dest.exists():
                            stem = child.stem
                            suffix = child.suffix
                            counter = 1
                            new_dest = target / f"{stem}_{counter}{suffix}"
                            while new_dest.exists():
                                counter += 1
                                new_dest = target / f"{stem}_{counter}{suffix}"
                            dest = new_dest

                        shutil.move(str(child), str(dest))

                    # Remove the now-empty source folder
                    try:
                        entry.rmdir()
                    except Exception:
                        pass
                else:
                    # Simple rename to desired lowercased name
                    entry.rename(target)
            except Exception:
                # On any error, skip renaming/merging that folder
                continue


def set_parent_mtime(paths):
    """Set each provided directory's mtime to the *newest* timestamp found
    under that directory.

    For each root path provided, this finds every item (files and directories)
    under the root and propagates the **maximum** mtime up through the ancestor
    chain.  This ensures the parent folder shows the modification time of its
    most recently modified child, regardless of how deep it is nested.

    When the environment variable ``ORGANIZE_DEBUG`` is set to a non-empty
    value the function logs the timestamps it observes and the values it sets
    on each directory.  This can help diagnose situations where macOS appears
    to revert or ignore the changed mtime after the script exits.
    """
    for p in paths:
        base = Path(p)
        if not base.exists() or not base.is_dir():
            continue

        # Map of directory -> newest mtime found under that directory
        dir_latest = {}

        try:
            if os.environ.get('ORGANIZE_DEBUG'):
                print(f"[DEBUG] scanning root {base}")
            for f in base.rglob('*'):
                try:
                    # skip hidden files and folders (names starting with '.') so
                    # Finder artifacts like .DS_Store don't incorrectly win the
                    # "newest" calculation. This keeps the parent mtime driven
                    # by user content instead of system metadata.
                    if f.name.startswith('.'):
                        if os.environ.get('ORGANIZE_DEBUG'):
                            print(f"[DEBUG]   skipping hidden {f}")
                        continue

                    # Only use regular FILES to determine what a folder’s date
                    # should be. Directories are what we’re setting — reading
                    # their current mtime would contaminate the result (e.g. a
                    # newly-created ‘misc/’ folder has today’s mtime and would
                    # make every ancestor look like it was modified today).
                    if not f.is_file():
                        continue
                    m = f.stat().st_mtime
                    if os.environ.get('ORGANIZE_DEBUG'):
                        print(f"[DEBUG]   found {f} -> {m}")
                except Exception:
                    continue

                curr = f.parent
                # Propagate mtime up to base
                while True:
                    prev = dir_latest.get(curr)
                    # keep the maximum timestamp seen so far
                    if prev is None or m > prev:
                        dir_latest[curr] = m
                    if curr == base:
                        break
                    curr = curr.parent

            # Apply mtimes for each directory that had files
            for d, mtime in dir_latest.items():
                try:
                    if os.environ.get('ORGANIZE_DEBUG'):
                        prev = d.stat().st_mtime
                        print(f"[DEBUG] updating {d} from {prev} to {mtime}")
                    os.utime(str(d), (mtime, mtime))
                except Exception:
                    # ignore errors setting times for individual dirs
                    continue
        except Exception:
            # If anything goes wrong scanning this root, skip it
            continue


def extract_date_from_filename(name: str):
    """Try to extract a datetime from a filename using known patterns.

    Supported patterns (checked in order):
    1. YYYYMMDDTHHMMSS (e.g. 20240226T134501)
    2. YYYY-MM-DDTHH;MM;SS (e.g. 2024-02-26T13;45;01)
    3. YYYY-MM-DD
    4. YYYY.MM.DD
    5. YYYYMMDD

    Returns a timezone-naive datetime or None.
    """
    # Pattern 1: YYYYMMDDTHHMMSS
    m = _RE_DATE_FULL.search(name)
    if m:
        y,mo,d,h,mi,s = map(int, m.groups())
        try:
            return datetime.datetime(y,mo,d,h,mi,s)
        except Exception:
            return None

    # Pattern 1b: YYYY-MM-DDTHH;MM;SS (semicolons used as time separators)
    m = _RE_DATE_SEMI.search(name)
    if m:
        y,mo,d,h,mi,s = map(int, m.groups())
        try:
            return datetime.datetime(y,mo,d,h,mi,s)
        except Exception:
            return None

    # Pattern 2: YYYY-MM-DD
    m = _RE_DATE_DASH.search(name)
    if m:
        y,mo,d = map(int, m.groups())
        try:
            return datetime.datetime(y,mo,d,0,0,0)
        except Exception:
            return None

    # Pattern 3: YYYY.MM.DD
    m = _RE_DATE_DOT.search(name)
    if m:
        y,mo,d = map(int, m.groups())
        try:
            return datetime.datetime(y,mo,d,0,0,0)
        except Exception:
            return None

    # Pattern 4: YYYYMMDD (ensure not part of longer run handled above)
    m = _RE_DATE_COMPACT.search(name)
    if m:
        y,mo,d = map(int, m.groups())
        try:
            return datetime.datetime(y,mo,d,0,0,0)
        except Exception:
            return None

    return None


def apply_dates_from_filenames(root):
    """Scan files under `root` and set their mtime and creation date
    from dates found in their filenames. Skips hidden files.
    """
    base = Path(root)
    if not base.exists():
        return

    for p in base.rglob('*'):
        try:
            if not p.is_file() or p.name.startswith('.'):
                continue

            dt = extract_date_from_filename(p.name)
            if not dt:
                continue

            # Reject dates more than 1 day in the future — likely a
            # misparse (e.g. digit sequences producing year 9066).
            max_allowed = datetime.datetime.now() + datetime.timedelta(days=1)
            if dt > max_allowed:
                if os.environ.get('ORGANIZE_DEBUG'):
                    print(f"[DEBUG] skipping future date {dt.isoformat()} for {p}")
                continue

            ts = dt.timestamp()
            try:
                if os.environ.get('ORGANIZE_DEBUG'):
                    print(f"[DEBUG] setting times for {p} -> {dt.isoformat()}")
                os.utime(str(p), (ts, ts))
            except Exception:
                pass

            # Set creation (birth) date via syscall — no subprocess needed
            try:
                _set_creation_date(str(p), ts)
            except Exception:
                pass
        except Exception:
            continue

def organize_files(file_list, root_path=None, progress_callback=None):
    """Organize a list of files.

    Accepts an optional ``progress_callback(current, total, filename)`` function. If a
    callback is provided it will be invoked on every file, otherwise the existing
    AppleScript-based :func:`update_progress` will be used to show progress.
    """
    DIRECTORIES = {
        "videos": [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v",
                   ".3gp", ".rmvb", ".vob", ".m2ts", ".ts"],
        "images": [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".tif",
                   ".ico", ".heic", ".raw", ".cr2", ".nef", ".arw", ".dng", ".svg"],
        "audio": [".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg"],
        "text": [".txt", ".pdf", ".docx", ".md", ".csv"],
        "misc": [".html", ".htm", ".json", ".js", ".css", ".py", ".sh", ".zip", ".rar"]
    }

    total_files = len(file_list)
    success_count = 0
    error_count = 0

    if total_files == 0:
        return 0, 0, 0

    start_time = time.time()
    processed = 0
    last_progress_print = start_time
    show_progress = bool(os.environ.get('ORGANIZE_PROGRESS'))
    created_folders = set()

    # Normalize provided root path to a Path (may be None)
    root_dir = Path(root_path) if root_path is not None else None

    def _sha1(path):
        h = hashlib.sha1()
        try:
            size = os.path.getsize(path)
            # default threshold 100MB unless overridden
            threshold = int(os.environ.get('ORGANIZE_HASH_MAX', 100 * 1024 * 1024))
            if size > threshold and not os.environ.get('ORGANIZE_FORCE_HASH'):
                # skip verbose messaging about large-file hash skipping
                return None

            start = time.time()
            with open(path, 'rb') as fh:
                for chunk in iter(lambda: fh.read(8192), b''):
                    h.update(chunk)
            digest = h.hexdigest()
            # do not print SHA1 timing here
            return digest
        except Exception:
            return None

    for index, item in enumerate(file_list, 1):
        # Update progress bar (AppleScript or provided callback)
        if progress_callback and callable(progress_callback):
            try:
                progress_callback(index, total_files, item.name)
            except Exception:
                # trust the callback but don't let failures abort the loop
                pass
        else:
            update_progress(index, total_files, item.name)

        # If the file is already inside one of the canonical folders, skip
        # moving it. This prevents cascading folders such as
        # "images/images/..." when a user already has an `Images` folder.
        try:
            parent_name = item.parent.name.lower()
            if parent_name in {k.lower() for k in DIRECTORIES.keys()}:
                if os.environ.get('ORGANIZE_DEBUG'):
                    print(f"[DEBUG] skipping move for {item} (already in {item.parent})")
                # Do not treat this as an error; simply skip moving.
                continue
        except Exception:
            # If anything goes wrong determining the parent, continue
            # with normal processing.
            pass

        file_ext = item.suffix.lower()
        target_folder_name = "misc"
        
        for folder_name, extensions in DIRECTORIES.items():
            if file_ext in extensions:
                target_folder_name = folder_name
                break
        
        base_dir = item.parent
        dest_folder = base_dir / target_folder_name
        
        try:
            existed_before = dest_folder.exists()
            dest_folder.mkdir(exist_ok=True)
            if not existed_before:
                created_folders.add(str(dest_folder))
            dest_path = dest_folder / item.name

            # If a file with the same name already exists, use suffix-based
            # renaming to avoid overwriting. Duplicate detection is disabled.
            if dest_path.exists():
                try:
                    # If they are the same underlying file (same inode), skip.
                    st_item = item.stat()
                    st_dest = dest_path.stat()
                    if (st_item.st_ino == st_dest.st_ino and
                            st_item.st_dev == st_dest.st_dev):
                        success_count += 1
                        continue
                except Exception:
                    pass

                stem, suffix, counter = item.stem, item.suffix, 1
                while dest_path.exists():
                    dest_path = dest_folder / f"{stem}_{counter}{suffix}"
                    counter += 1

            shutil.move(str(item), str(dest_path))
            success_count += 1
        except Exception:
            error_count += 1

        # periodic progress messaging suppressed

    # Clear progress line if shown
    if show_progress:
        try:
            print('', flush=True)
        except Exception:
            pass

    return success_count, error_count, len(created_folders)


# Headless progress wrapper. No GUI is created; progress is silent unless
# `ORGANIZE_DEBUG=1` is set, in which case concise progress lines are printed.
_PROGRESS_UI = None

class _ProgressWindow:
    """Progress reporter that prints phase labels and a live progress bar."""

    BAR_WIDTH = 20

    def __init__(self, steps: List[str], total: int):
        self.steps = steps
        self.total = total
        self.current = 0
        self.step = ''
        self._last_print = 0.0
        self._bar_active = False  # True while a \r progress line is live

    def _clear_bar(self):
        if self._bar_active:
            print()  # newline so next print starts on a fresh line
            self._bar_active = False

    def set_step(self, name: str):
        self._clear_bar()
        self.step = name
        try:
            print(f"  ► {name.capitalize()}...", flush=True)
        except Exception:
            pass

    def update(self, current: int, total: int, filename: str):
        self.current = current
        self.total = total
        now = time.time()
        if now - self._last_print < 0.25 and current != total:
            return
        self._last_print = now
        try:
            pct = int(100 * current / total) if total else 100
            filled = pct * self.BAR_WIDTH // 100
            bar = '█' * filled + '░' * (self.BAR_WIDTH - filled)
            name_trunc = filename[:35]
            print(f"\r    [{bar}] {pct:3d}%  {current}/{total}  {name_trunc:<35}", end='', flush=True)
            self._bar_active = True
        except Exception:
            pass

    def close(self):
        self._clear_bar()
        if os.environ.get('ORGANIZE_DEBUG'):
            try:
                print("  ► Done", flush=True)
            except Exception:
                pass


def start_progress(steps: List[str], total: int):
    global _PROGRESS_UI
    try:
        _PROGRESS_UI = _ProgressWindow(steps, total)
    except Exception:
        _PROGRESS_UI = None


def set_progress_step(name: str):
    if _PROGRESS_UI:
        try:
            _PROGRESS_UI.set_step(name)
        except Exception:
            pass


def update_progress_ui(current: int, total: int, filename: str):
    if _PROGRESS_UI:
        try:
            _PROGRESS_UI.update(current, total, filename)
            return
        except Exception:
            pass
    # fallback to AppleScript progress if no UI
    try:
        update_progress(current, total, filename)
    except Exception:
        pass


def finish_progress():
    global _PROGRESS_UI
    if _PROGRESS_UI:
        try:
            _PROGRESS_UI.close()
        except Exception:
            pass
    _PROGRESS_UI = None


class _Ticker:
    """Throttled one-line progress printer — at most one update every `interval` seconds."""

    def __init__(self, interval: float = 5.0):
        self.interval = interval
        self._last = 0.0

    def tick(self, label: str, current: int, total: int):
        now = time.time()
        if current < total and now - self._last < self.interval:
            return
        self._last = now
        pct = int(100 * current / total) if total else 100
        print(f"  ► {label}: {current}/{total} ({pct}%)...", flush=True)


def find_and_remove_duplicates(root_path, ticker=None):
    """Fast 3-phase duplicate scan across ALL files under root_path.

    Phase 1 — group by exact file size (stat only, zero reads).
              Files with a unique size cannot have duplicates → skipped.
    Phase 2 — partial SHA1 of first 64 KB for size-collision candidates.
    Phase 3 — full SHA1 only for partial-hash collisions (true-dupe confirm).

    Coomer rule: any file whose path contains a 'coomer' folder component is
    treated as source of truth and is NEVER moved.  Among confirmed duplicates,
    all non-coomer copies go to DUPES/.  When no coomer copy exists, the oldest
    file (lowest mtime) is kept and the rest go to DUPES/.
    """
    PARTIAL_BYTES = 64 * 1024  # 64 KB — fast pre-filter read

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

    dbg = bool(os.environ.get('ORGANIZE_DEBUG'))

    # Phase 1: group by size — pure stat, no reads
    size_map: dict = {}
    _p1_count = 0
    _p1_last = time.time()
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
            _p1_count += 1
            if ticker:
                _now = time.time()
                if _now - _p1_last >= ticker.interval:
                    _p1_last = _now
                    print(f"  ► Scanning: {_p1_count} files indexed...", flush=True)
        except Exception:
            continue

    # Flatten size-collision candidates for phase 2 (enables progress tracking)
    candidates_p2 = [
        (sz, p) for sz, paths in size_map.items() if len(paths) >= 2 for p in paths
    ]
    total_p2 = len(candidates_p2)

    if dbg:
        print(f"[DEBUG] dedup phase1: {len(size_map)} unique sizes, {total_p2} size-collision candidates", flush=True)
    if ticker and total_p2:
        print(f"  ► Found {total_p2} size-match candidates to verify...", flush=True)

    # Phase 2: partial hash within size-collision groups
    partial_map: dict = {}
    for i, (sz, p) in enumerate(candidates_p2, 1):
        if ticker:
            ticker.tick("Dupe Checking", i, total_p2)
        ph = _hash(p, limit=PARTIAL_BYTES)
        if ph is None:
            continue
        partial_map.setdefault((sz, ph), []).append(p)

    partial_candidates = sum(len(v) for v in partial_map.values() if len(v) >= 2)
    if dbg:
        print(f"[DEBUG] dedup phase2: {partial_candidates} partial-hash collision candidates", flush=True)

    # Phase 3: full hash for partial-hash collisions → confirmed duplicates
    # Hash each candidate once with progress, cache results, then group for removal.
    candidates_p3 = list({
        str(p): p
        for paths in partial_map.values() if len(paths) >= 2
        for p in paths
    }.values())
    total_p3 = len(candidates_p3)
    if ticker and total_p3:
        print(f"  ► Full hashing {total_p3} candidates for final confirmation...", flush=True)
        ticker._last = 0.0  # reset so first tick fires immediately

    p3_cache: dict = {}  # str(path) -> full_hash
    for i, p in enumerate(candidates_p3, 1):
        if ticker:
            ticker.tick("Full Hashing", i, total_p3)
        fh = _hash(p)
        p3_cache[str(p)] = fh

    moved = 0
    for _, paths in partial_map.items():
        if len(paths) < 2:
            continue
        full_map: dict = {}
        for p in paths:
            fh = p3_cache.get(str(p))
            if fh is None:
                continue
            full_map.setdefault(fh, []).append(p)

        for dupe_paths in full_map.values():
            if len(dupe_paths) < 2:
                continue

            coomer_copies = [p for p in dupe_paths if _is_coomer(p)]
            other_copies  = [p for p in dupe_paths if not _is_coomer(p)]

            if coomer_copies:
                # Coomer = source of truth; all non-coomer copies are dupes
                to_remove = other_copies
            else:
                # No coomer copy: keep the oldest file, remove the rest
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
                    if os.environ.get('ORGANIZE_DEBUG'):
                        print(f"[DEBUG] dupe → DUPES: {dup}")
                    shutil.move(str(dup), str(dup_target))
                    moved += 1
                except Exception:
                    pass

    return moved


def organize_folder(root_path, notify=True, _processed_roots=None):
    """Process a single root path end-to-end: normalize subfolders, collect
    files under that root, organize them, update parent mtimes, and notify.
    This ensures each folder is handled individually (no cross-folder mixing).
    """
    # Track processed roots to avoid infinite recursion when we call this
    # function recursively for special-case folders like 'coomer'. Caller may
    # pass a set in `_processed_roots` to continue tracking across recursive
    # invocations.
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

    # Step 1 — normalize subfolder names (Pics→images, Vids→videos, etc.)
    print("  ► Normalizing folder names...", flush=True)
    normalize_subfolders([root])

    ticker = _Ticker(interval=5.0)

    # Step 2 — duplicate scan DISABLED for speed.
    # To re-enable, uncomment the block below.
    # try:
    #     print("  ► Scanning for duplicates...", flush=True)
    #     dupes_moved = find_and_remove_duplicates(root, ticker=ticker)
    #     if dupes_moved:
    #         print(f"  ✓ Moved {dupes_moved} duplicate{'s' if dupes_moved != 1 else ''} to DUPES/", flush=True)
    #     else:
    #         print("  ✓ No duplicates found.", flush=True)
    # except Exception as _dedup_err:
    #     print(f"  ✗ Duplicate scan error: {_dedup_err}", flush=True)

    # Step 3 — scan for files to move
    print("  ► Scanning for files...", flush=True)
    files_to_sort = get_items([root])
    total_files = len(files_to_sort)

    success, errors = 0, 0
    if total_files > 0:
        print(f"  ► Found {total_files} file{'s' if total_files != 1 else ''} to organize", flush=True)
        if notify:
            _notify(f"Moving {total_files} file{'s' if total_files != 1 else ''}…", subtitle=folder_label)

        # Step 4 — move files into category subfolders
        def _org_progress(current, total, _filename):
            ticker.tick("Organizing", current, total)

        try:
            success, errors, _ = organize_files(files_to_sort, root_path=root, progress_callback=_org_progress)
        except Exception:
            success, errors, _ = 0, 0, 0
    else:
        print("  ✓ No new files to move — fixing timestamps.", flush=True)

    # Step 5 — apply dates from filenames across all files and subfolders,
    # regardless of whether any files were moved at the root level.
    # Set ORGANIZE_SKIP_DATE_APPLY=1 to skip.
    try:
        if not os.environ.get('ORGANIZE_SKIP_DATE_APPLY'):
            print("  ► Reading dates from filenames...", flush=True)
            if notify:
                _notify("Reading dates from filenames…", subtitle=folder_label)
            apply_dates_from_filenames(root)
    except Exception:
        pass

    # Step 6 — recursively organize any nested 'coomer' subfolders first so
    # that any new category folders they create (misc/, images/, etc.) exist
    # before we do the final timestamp pass.
    nested_success = 0
    nested_errors = 0
    try:
        root_path_obj = Path(root)
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

    # Step 7 — final timestamp pass, run AFTER all subfolders (including coomer)
    # have been fully organized. Run twice: the first pass sets correct dates;
    # the second pass corrects any folder whose mtime was bumped by macOS writing
    # invisible system files (.DS_Store etc.) during the first pass.
    print("  ► Updating timestamps...", flush=True)
    if notify:
        _notify("Updating folder timestamps…", subtitle=folder_label)
    for _ in range(2):
        try:
            set_parent_mtime([root])
            root_path_obj = Path(root)
            parent = root_path_obj.parent
            if parent.exists() and parent.is_dir():
                mtime = root_path_obj.stat().st_mtime
                if os.environ.get('ORGANIZE_DEBUG'):
                    prev = parent.stat().st_mtime
                    print(f"[DEBUG] propagating root mtime {mtime} up to parent {parent} (was {prev})")
                os.utime(str(parent), (mtime, mtime))
        except Exception:
            pass

    # Optional per-folder summary/notification (can be suppressed by caller)
    total_success = success + nested_success
    total_errors = errors + nested_errors

    if notify and (total_success > 0 or total_errors > 0):
        notify_final(total_success, total_errors)

    return total_success, total_errors

class _Tee:
    """Write to multiple streams at once (e.g. stdout + log file)."""
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
        time.sleep(0.6)  # give Terminal a moment to open before output starts
    except Exception:
        pass


if __name__ == "__main__":
    # ── Live log window ───────────────────────────────────────────────────────
    # When invoked from Automator / Finder Quick Action, stdout is invisible.
    # Open a Terminal window tailing a log file so progress is always visible.
    # A lock file ensures only the first concurrent process opens a Terminal;
    # subsequent processes append to the same log silently.
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
        """Atomically create the lock file. Returns True if we acquired it."""
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
            # Check if the existing lock is stale (owner process is dead)
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
    # ─────────────────────────────────────────────────────────────────────────

    if len(sys.argv) > 1:
        # Process each provided folder sequentially to avoid NAS concurrency issues
        total_success = 0
        total_errors = 0

        for root in sys.argv[1:]:
            try:
                # suppress per-folder alerts when running over multiple roots
                s, e = organize_folder(root, notify=False)
                total_success += s
                total_errors += e
            except SystemExit:
                # Allow early exit triggered by AppleScript "Stop" button
                break
            except Exception:
                # Skip problematic roots but continue with others
                continue

        # Optionally give an overall summary at the end
        if total_success > 0 or total_errors > 0:
            notify_final(total_success, total_errors)
    else:
        # Fallback for manual run
        print("No files provided.")

    if _log_fh:
        try:
            _log_fh.close()
        except Exception:
            pass