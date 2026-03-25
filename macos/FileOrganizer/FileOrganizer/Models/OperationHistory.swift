import Foundation

/// Tracks file operations for undo support.
/// Persists to ~/Library/Application Support/FileOrganizer/history/
@Observable
class OperationHistory {
    private(set) var operations: [FileOperation] = []
    private let historyDir: URL

    var canUndo: Bool { !operations.isEmpty }

    init() {
        let appSupport = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
        historyDir = appSupport.appendingPathComponent("FileOrganizer/history", isDirectory: true)
        try? FileManager.default.createDirectory(at: historyDir, withIntermediateDirectories: true)
    }

    func record(_ operation: FileOperation) {
        operations.append(operation)
        // TODO: Persist to disk
    }

    func undoLast() -> FileOperation? {
        guard !operations.isEmpty else { return nil }
        let op = operations.removeLast()
        // TODO: Execute reverse operation, persist
        return op
    }

    func clear() {
        operations.removeAll()
    }
}
