import Foundation
import CryptoKit

/// SHA-256 hashing with partial-hash support for duplicate detection.
/// Hardware-accelerated on Apple Silicon via CryptoKit.
struct SHA256Hasher {
    private static let readBufferSize = 256 * 1024  // 256 KB for SMB throughput

    /// Hash the first N bytes of a file (for phase 2 partial-hash).
    static func partialHash(url: URL, bytes: Int = 64 * 1024) -> String? {
        guard let handle = try? FileHandle(forReadingFrom: url) else { return nil }
        defer { try? handle.close() }

        let data = handle.readData(ofLength: bytes)
        let digest = SHA256.hash(data: data)
        return digest.map { String(format: "%02x", $0) }.joined()
    }

    /// Hash the entire file contents.
    static func fullHash(url: URL) -> String? {
        guard let handle = try? FileHandle(forReadingFrom: url) else { return nil }
        defer { try? handle.close() }

        var hasher = SHA256()
        while true {
            let chunk = handle.readData(ofLength: readBufferSize)
            if chunk.isEmpty { break }
            hasher.update(data: chunk)
        }
        let digest = hasher.finalize()
        return digest.map { String(format: "%02x", $0) }.joined()
    }
}
