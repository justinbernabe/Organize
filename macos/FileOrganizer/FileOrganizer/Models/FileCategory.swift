import Foundation

/// Maps file extensions to category folder names.
/// Users can override via Settings.
struct FileCategory {
    /// Default extension-to-category mapping (mirrors organize.py DIRECTORIES)
    static let defaultCategories: [String: [String]] = [
        "videos": [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v",
                   ".3gp", ".rmvb", ".vob", ".m2ts", ".ts"],
        "images": [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".tif",
                   ".ico", ".heic", ".raw", ".cr2", ".nef", ".arw", ".dng", ".svg"],
        "audio":  [".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg"],
        "text":   [".txt", ".pdf", ".docx", ".md", ".csv"],
        "misc":   [".html", ".htm", ".json", ".js", ".css", ".py", ".sh", ".zip", ".rar"]
    ]

    /// Default folder-name normalization mappings (mirrors organize.py MAPPINGS)
    static let defaultFolderMappings: [String: String] = [
        "pics": "images",
        "image": "images",
        "img": "images",
        "pictures": "images",
        "picture": "images",
        "photo": "images",
        "photos": "images",
        "vids": "videos",
        "video": "videos",
        "vid": "videos",
    ]

    /// Resolve extension to category name using provided (or default) mappings
    static func category(for ext: String, using categories: [String: [String]]? = nil) -> String {
        let cats = categories ?? defaultCategories
        let lowered = ext.lowercased()
        for (name, extensions) in cats {
            if extensions.contains(lowered) {
                return name
            }
        }
        return "misc"
    }
}
