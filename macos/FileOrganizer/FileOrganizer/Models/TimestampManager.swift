import Foundation

/// Manages file timestamp operations.
/// Port of organize.py's set_parent_mtime() and apply_dates_from_filenames().
struct TimestampManager {

    /// Set a file's modification time.
    static func setModificationDate(at url: URL, to date: Date) throws {
        try FileManager.default.setAttributes(
            [.modificationDate: date], ofItemAtPath: url.path)
    }

    /// Set a file's creation (birth) date via setattrlist.
    static func setCreationDate(at url: URL, to date: Date) -> Bool {
        CreationDateSetter.set(path: url.path, date: date)
    }

    /// Propagate the maximum child-file mtime up to each directory in the tree.
    /// Runs from leaf directories up to root. Skips hidden files.
    /// Port of organize.py's set_parent_mtime() — should be called twice
    /// to counteract macOS .DS_Store writes.
    static func propagateTimestamps(root: URL) {
        // TODO: Port set_parent_mtime() using FileManager.enumerator
        // - Build dict of [URL: maxMtime] scanning only regular files
        // - Skip hidden files (names starting with '.')
        // - Skip directories when calculating max (only use file mtimes)
        // - Apply via FileManager.setAttributes
    }

    /// Apply dates extracted from filenames to file timestamps.
    /// Port of organize.py's apply_dates_from_filenames().
    static func applyDatesFromFilenames(root: URL, settings: OrganizeSettings) {
        // TODO: Port — enumerate files, call DateExtractor, set timestamps
        // Respect settings.setModifiedDate, settings.setCreatedDate, settings.setAccessedDate
    }
}
