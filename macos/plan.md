# Plan: macOS Native App for File Organizer

## Context

The existing `organize.py` CLI script works well but is invisible when run from Automator. The goal is a native macOS app with an ImageOptim-style drag-and-drop UI that exposes all the script's features as user-configurable settings, adds preview/undo, and is optimized for NAS/SMB speed.

## Branch & Folder Structure

- Create branch `macos` from `main`
- All app code lives in `/macos/FileOrganizer/` — does **not** touch `organize.py` on `main`
- `organize.py` remains the CLI tool; the Swift app is a full rewrite (not a wrapper)

```
macos/
  plan.md                          # This plan
  FileOrganizer/
    FileOrganizer.xcodeproj
    FileOrganizer/
      App/
        FileOrganizerApp.swift       # @main, SwiftUI lifecycle
        AppDelegate.swift            # Dock drop target
      Models/
        OrganizeEngine.swift         # 7-step pipeline orchestrator
        FileCategory.swift           # Extension → category mapping
        DuplicateDetector.swift      # 3-phase dedup
        DateExtractor.swift          # Filename date parsing (5 patterns)
        TimestampManager.swift       # setattrlist + utime
        OrganizeSettings.swift       # @Observable settings, @AppStorage
        FileOperation.swift          # Operation record (for undo)
        OperationHistory.swift       # Undo stack
      Views/
        MainWindow.swift             # Drop zone + file list composition
        DropZoneView.swift           # Drag-and-drop target
        FileListView.swift           # Table with status per file
        ProgressOverlay.swift        # Per-phase progress bars
        SettingsView.swift           # Preferences (tabbed)
        PreviewSheet.swift           # Dry-run results modal
      Services/
        FileSystemService.swift      # Scan, move, stat caching
        SMBOptimizer.swift           # Detect SMB mounts, tune buffers
        NotificationService.swift    # macOS notification banners
      Utilities/
        CreationDateSetter.swift     # setattrlist via Darwin C interop
        SHA256Hasher.swift           # CryptoKit (hardware-accelerated)
      Resources/
        Assets.xcassets
```

## Framework: SwiftUI + Targeted AppKit

- **SwiftUI** for all UI (free dark mode, minimal code, modern)
- **AppKit bridges** only for: `NSOpenPanel` (folder picker), robust Finder drag-and-drop (`NSDraggingDestination`), dock drop (`NSApplicationDelegate`)
- Minimum deployment: macOS 14 (Sonoma)

## Why Rewrite in Swift (Not Wrap organize.py)

1. **Speed** — Swift's Foundation + structured concurrency (`TaskGroup`) can pipeline SMB I/O; Python's GIL prevents true parallelism
2. **No Python dependency** — single `.app` bundle vs bundling 50-80MB Python runtime
3. **Native setattrlist** — direct Darwin module call, no ctypes
4. **CryptoKit SHA-256** — hardware-accelerated on Apple Silicon, replaces hashlib SHA-1

## Core Engine (Port of organize.py's 7-Step Pipeline)

`OrganizeEngine.swift` orchestrates the same 7 steps, emitting progress via `AsyncStream<ProgressEvent>`:

1. Normalize subfolder names (MAPPINGS dict → configurable)
2. 3-phase dedup (size → 64KB partial hash → full hash) with exempt folder
3. Scan files (skip hidden, skip already-categorized)
4. Move files to category subfolders by extension
5. Extract dates from filenames, set mtime + creation date
6. Recursively process nested exempt subfolders
7. Propagate mtimes (2-pass for .DS_Store correction)

**SMB optimizations:**
- `FileManager.enumerator(includingPropertiesForKeys:)` to batch-prefetch metadata in one pass (not per-file `stat`)
- Concurrent hashing via `TaskGroup` to saturate SMB connection
- Cache all `stat` results in `[URL: StatResult]` dictionary — reuse across all pipeline steps
- `rename()` for same-volume moves (atomic, zero-copy)
- Detect SMB mounts via `statfs`, use larger read buffers (256KB+)

## UI Design (ImageOptim-Inspired)

### Main Window — Two States

**Empty:** Large centered drop zone with folder icon + "Drop folders here or click to browse". Toolbar: gear icon (settings), profile dropdown.

**Active:** Drop zone shrinks to header strip. Below: file list table (filename, category, status icon, size, detected date). Bottom status bar: total files, dupes found, errors, elapsed time. Start/Stop button (or "Preview" in dry-run mode).

### Settings Window (Tabbed)

| Tab | Settings |
|-----|----------|
| **General** | Default action (Organize / Dedup only / Timestamps only), Dry run toggle, Notifications, Launch at login |
| **Dates** | Checkboxes: set modified / created / accessed date. Date source priority (Filename > EXIF > Current). Custom date regex patterns |
| **Duplicates** | Enable/disable, hash threshold (MB), policy (keep oldest/newest/largest), exempt folder name + toggle |
| **Organization** | Enable/disable file moving, name scheme (lowercase/UPPERCASE/Title Case/Custom), category rules editor (extension→category table), folder normalization mappings |
| **Profiles** | Saved presets list, import/export as JSON. Built-in: "Full Organize", "Dedup Only", "Fix Timestamps", "Quick Sort" |

## Additional Features

### Phase 1 (MVP)

- **Dry run / preview mode** — run pipeline but record ops to array, show sheet with "Source → Destination" table, user confirms or cancels
- **Undo** — every move/timestamp change recorded in `OperationHistory` with original state; Cmd+Z triggers undo; persists to `~/Library/Application Support/FileOrganizer/history/`
- **Keyboard shortcuts** — Cmd+O (open), Cmd+R (run), Cmd+Z (undo), Cmd+, (settings), Space (Quick Look)
- **Dark mode** — automatic via SwiftUI
- **macOS notifications** — completion banners via `UserNotifications`
- **Drag-to-dock** — drop folder on dock icon to queue

### Phase 2 (Post-MVP)

- Custom category rules UI
- Profiles/presets with toolbar switching
- Menu bar extra (recent operations, quick access)
- EXIF date extraction via `CGImageSource` / `ImageIO`
- Estimated time remaining in progress
- Batch progress per-move granularity

### Phase 3 (Future)

- Watched folders / scheduled organizing (FSEvents)
- Rule engine (Hazel-style conditions)
- Shortcuts.app integration (expose as Shortcuts action)
- iCloud settings sync
- App Store distribution (sandbox + security-scoped bookmarks)

## Build Order (Phase 1)

1. Create Xcode project + folder structure
2. **Models** — `FileCategory.swift`, `OrganizeSettings.swift`, `FileOperation.swift`
3. **Utilities** — `CreationDateSetter.swift` (setattrlist), `SHA256Hasher.swift` (CryptoKit with partial-hash), `DateExtractor.swift` (5 regex patterns)
4. **Services** — `FileSystemService.swift` (scan + stat cache), `DuplicateDetector.swift` (3-phase), `TimestampManager.swift` (date apply + mtime propagation)
5. **Engine** — `OrganizeEngine.swift` (7-step pipeline, `AsyncStream<ProgressEvent>`, dry-run support)
6. **Views** — `DropZoneView`, `FileListView`, `ProgressOverlay`, `MainWindow`, `SettingsView`, `PreviewSheet`
7. **App shell** — `FileOrganizerApp.swift`, `AppDelegate.swift` (dock drop)
8. **Undo** — `OperationHistory.swift` wired into engine

## Verification

1. Build and run in Xcode — app launches, drop zone visible
2. Drag a test folder onto drop zone — file list populates
3. Click Start — files organized into subfolders, progress shown
4. Verify dry-run mode — preview sheet shows planned ops, no files moved until confirmed
5. Cmd+Z — last operation undone, files restored
6. Test on SMB-mounted NAS folder — confirm speed improvement over `organize.py`
7. Test settings toggles — disable dedup, disable dates, change name scheme, verify behavior changes
