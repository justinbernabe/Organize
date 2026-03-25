import Foundation

/// Cached file metadata from a single scan pass.
struct CachedFileInfo {
    let url: URL
    let size: Int
    let modificationDate: Date?
    let creationDate: Date?
    let isDirectory: Bool
    let isHidden: Bool
}

/// File system operations optimized for SMB/NAS.
/// Caches stat results to minimize network round-trips.
struct FileSystemService {
    /// Prefetch keys for FileManager.enumerator — batches metadata in one pass.
    private static let prefetchKeys: [URLResourceKey] = [
        .fileSizeKey,
        .contentModificationDateKey,
        .creationDateKey,
        .isDirectoryKey,
        .isHiddenKey,
        .nameKey,
    ]

    /// Scan a directory tree in a single pass, returning cached metadata for all files.
    /// Uses FileManager.enumerator with prefetched keys to minimize SMB round-trips.
    static func scan(root: URL, recursive: Bool = true) -> [CachedFileInfo] {
        var results: [CachedFileInfo] = []
        guard let enumerator = FileManager.default.enumerator(
            at: root,
            includingPropertiesForKeys: prefetchKeys,
            options: recursive ? [.skipsHiddenFiles] : [.skipsHiddenFiles, .skipsSubdirectoryDescendants]
        ) else { return results }

        for case let url as URL in enumerator {
            guard let values = try? url.resourceValues(forKeys: Set(prefetchKeys)) else { continue }
            let info = CachedFileInfo(
                url: url,
                size: values.fileSize ?? 0,
                modificationDate: values.contentModificationDate,
                creationDate: values.creationDate,
                isDirectory: values.isDirectory ?? false,
                isHidden: values.isHidden ?? false
            )
            results.append(info)
        }
        return results
    }

    /// Move a file, using rename() for same-volume (atomic, zero-copy).
    static func moveFile(from source: URL, to destination: URL) throws {
        try FileManager.default.moveItem(at: source, to: destination)
    }

    /// Check if a path is on an SMB mount (for tuning buffer sizes).
    static func isSMBMount(url: URL) -> Bool {
        // TODO: Use statfs to detect SMB filesystem type
        return false
    }
}
