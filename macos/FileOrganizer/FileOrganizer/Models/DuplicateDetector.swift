import Foundation

/// 3-phase duplicate file detector.
/// Port of organize.py's find_and_remove_duplicates().
///
/// Phase 1: Group by file size (stat only, zero reads)
/// Phase 2: Partial SHA-256 of first 64KB for size-collision candidates
/// Phase 3: Full SHA-256 only for partial-hash collisions
///
/// Exempt folder files (default: "coomer") are never moved.
struct DuplicateDetector {
    static let partialHashBytes = 64 * 1024  // 64 KB

    struct DuplicateResult {
        let duplicates: [URL]      // Files to move to DUPES/
        let kept: URL              // File that stays
    }

    /// Run the full 3-phase scan under the given root.
    /// Returns list of duplicate groups with which file to keep.
    static func scan(
        root: URL,
        exemptFolderName: String,
        enableExempt: Bool,
        policy: DuplicatePolicy,
        hashThresholdMB: Int,
        progress: ((Int, Int, String) -> Void)? = nil
    ) async -> [DuplicateResult] {
        // TODO: Port 3-phase algorithm
        // Phase 1: FileManager.enumerator → group by .fileSizeKey
        // Phase 2: SHA256Hasher.partialHash() for size-collision groups
        // Phase 3: SHA256Hasher.fullHash() for partial-hash collisions
        // Apply exempt folder logic + duplicate policy
        // Use TaskGroup for concurrent hashing (saturate SMB)
        return []
    }
}
