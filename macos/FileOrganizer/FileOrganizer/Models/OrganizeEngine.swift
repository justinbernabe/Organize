import Foundation

/// Progress events emitted by the engine during processing.
enum ProgressEvent {
    case stepStarted(String)
    case stepProgress(current: Int, total: Int, detail: String)
    case stepCompleted(String, summary: String)
    case fileProcessed(URL, category: String, status: FileStatus)
    case error(String)
    case completed(success: Int, errors: Int, dupes: Int)
}

enum FileStatus: String {
    case pending
    case processing
    case done
    case duplicate
    case skipped
    case error
}

/// Orchestrates the 7-step file organization pipeline.
/// Port of organize.py's organize_folder() with dry-run support.
actor OrganizeEngine {
    let settings: OrganizeSettings
    let history: OperationHistory
    private var cancelled = false

    init(settings: OrganizeSettings, history: OperationHistory) {
        self.settings = settings
        self.history = history
    }

    /// Run the full pipeline on the given root folders.
    /// Returns an AsyncStream of progress events.
    func process(roots: [URL], dryRun: Bool = false) -> AsyncStream<ProgressEvent> {
        AsyncStream { continuation in
            Task {
                var totalSuccess = 0
                var totalErrors = 0
                var totalDupes = 0

                for root in roots {
                    guard !cancelled else { break }

                    // Step 1: Normalize subfolder names
                    continuation.yield(.stepStarted("Normalizing folder names"))
                    // TODO: Port normalize_subfolders()
                    continuation.yield(.stepCompleted("Normalizing folder names", summary: "Done"))

                    // Step 2: Deduplicate
                    if settings.enableDuplicateDetection {
                        continuation.yield(.stepStarted("Scanning for duplicates"))
                        // TODO: Port find_and_remove_duplicates() — 3-phase
                        continuation.yield(.stepCompleted("Scanning for duplicates", summary: "0 duplicates"))
                    }

                    // Step 3: Scan files
                    continuation.yield(.stepStarted("Scanning files"))
                    // TODO: Port get_items() with FileManager.enumerator + stat cache
                    continuation.yield(.stepCompleted("Scanning files", summary: "0 files found"))

                    // Step 4: Organize (move files to category subfolders)
                    if settings.enableFileMoving {
                        continuation.yield(.stepStarted("Organizing files"))
                        // TODO: Port organize_files()
                        continuation.yield(.stepCompleted("Organizing files", summary: "0 moved"))
                    }

                    // Step 5: Apply dates from filenames
                    if settings.defaultAction != .deduplicateOnly {
                        continuation.yield(.stepStarted("Applying dates from filenames"))
                        // TODO: Port apply_dates_from_filenames()
                        continuation.yield(.stepCompleted("Applying dates from filenames", summary: "Done"))
                    }

                    // Step 6: Recursive exempt folder processing
                    continuation.yield(.stepStarted("Processing nested folders"))
                    // TODO: Port coomer/exempt folder recursion
                    continuation.yield(.stepCompleted("Processing nested folders", summary: "Done"))

                    // Step 7: Propagate timestamps (2-pass)
                    continuation.yield(.stepStarted("Updating timestamps"))
                    // TODO: Port set_parent_mtime() — run twice
                    continuation.yield(.stepCompleted("Updating timestamps", summary: "Done"))
                }

                continuation.yield(.completed(success: totalSuccess, errors: totalErrors, dupes: totalDupes))
                continuation.finish()
            }
        }
    }

    func cancel() {
        cancelled = true
    }
}
