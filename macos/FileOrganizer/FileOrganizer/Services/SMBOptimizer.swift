import Foundation

/// SMB-specific optimizations for NAS file operations.
struct SMBOptimizer {
    /// Detect if the given URL is on an SMB-mounted volume via statfs.
    static func isSMBVolume(at path: String) -> Bool {
        var stat = statfs()
        guard statfs(path, &stat) == 0 else { return false }
        let fsType = withUnsafePointer(to: stat.f_fstypename) {
            $0.withMemoryRebound(to: CChar.self, capacity: Int(MFSTYPENAMELEN)) {
                String(cString: $0)
            }
        }
        return fsType == "smbfs"
    }

    /// Recommended read buffer size based on mount type.
    static func readBufferSize(for path: String) -> Int {
        if isSMBVolume(at: path) {
            return 256 * 1024  // 256 KB for SMB
        }
        return 64 * 1024  // 64 KB for local
    }
}
