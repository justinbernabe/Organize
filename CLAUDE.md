# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Goal

**SUPER FAST organization.** Speed is the #1 priority. The primary use case is organizing a NAS drive mounted via SMB on macOS. Every operation — scanning, hashing, moving, timestamp setting — must be optimized for network filesystem latency. Avoid unnecessary I/O round-trips, minimize `stat` calls, batch operations where possible, and prefer parallel/concurrent work over sequential. Nothing should block longer than it has to. If a step can be skipped or deferred to save time, it should be. macOS is the host OS so we have access to `setattrlist`, `osascript`, and other native APIs for touching files and editing dates.

## Overview

Single-file Python script (`organize.py`) that sorts files into category subfolders (`images/`, `videos/`, `audio/`, `text/`, `misc/`), deduplicates them, and fixes filesystem timestamps. Designed to run as a macOS Finder Quick Action (Automator) or from the command line. Targets NAS/external drives.

## Running

```bash
# Organize one or more folders
python3 organize.py /path/to/folder1 /path/to/folder2

# With debug output
ORGANIZE_DEBUG=1 python3 organize.py /path/to/folder

# Recursive mode (process subdirectories)
ORGANIZE_RECURSIVE=1 python3 organize.py /path/to/folder
```

No dependencies beyond the Python 3 standard library. Uses `ctypes` to call macOS `setattrlist` for setting file creation dates.

## Environment Variables

- `ORGANIZE_DEBUG` — verbose debug output
- `ORGANIZE_RECURSIVE` — recurse into subdirectories when gathering files
- `ORGANIZE_PROGRESS` — show progress bar during organizing
- `ORGANIZE_SKIP_DATE_APPLY` — skip the filename→timestamp extraction step
- `ORGANIZE_HASH_MAX` — byte threshold for SHA1 hashing (default 100MB); files larger are skipped
- `ORGANIZE_FORCE_HASH` — hash files regardless of size

## Architecture

The script processes each root folder through a 7-step pipeline in `organize_folder()`:

1. **Normalize subfolders** — renames variants (Pics→images, Vids→videos) to canonical lowercase names, handling case-insensitive filesystem edge cases
2. **Deduplicate** — 3-phase scan (size→partial SHA1→full SHA1) across all files; moves dupes to `DUPES/` folder. Files inside a `coomer/` subfolder are treated as source-of-truth and never moved
3. **Scan** — collects non-hidden files via `get_items()`
4. **Organize** — moves files into category subfolders by extension; skips files already in a canonical folder; handles name collisions with suffix numbering
5. **Apply dates** — extracts dates from filenames (supports `YYYYMMDD`, `YYYY-MM-DD`, `YYYY.MM.DD`, `YYYYMMDDTHHMMSS` formats) and sets both mtime and macOS creation date
6. **Recursive coomer pass** — recursively organizes nested `coomer/` subfolders
7. **Timestamp propagation** — sets each directory's mtime to its newest child file's mtime (run twice to counteract macOS `.DS_Store` writes)

Key design decisions:
- macOS creation date is set via `setattrlist` syscall (ctypes), not `SetFile` subprocess
- When run from Automator (non-tty), opens a Terminal window tailing `/tmp/organize_latest.log` for visibility
- Duplicate detection keeps the **oldest** copy by default; the newer copy goes to `DUPES/`
- Progress output is throttled to avoid performance overhead on large file sets
