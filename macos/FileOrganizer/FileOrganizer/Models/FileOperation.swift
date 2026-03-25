import Foundation

/// Represents a single file operation that can be undone.
enum OperationType: String, Codable {
    case move
    case duplicate
    case timestampChange
}

struct FileOperation: Identifiable, Codable {
    let id: UUID
    let type: OperationType
    let sourceURL: URL
    let destinationURL: URL?
    let originalModifiedDate: Date?
    let originalCreatedDate: Date?
    let timestamp: Date

    init(type: OperationType, source: URL, destination: URL? = nil,
         originalModified: Date? = nil, originalCreated: Date? = nil) {
        self.id = UUID()
        self.type = type
        self.sourceURL = source
        self.destinationURL = destination
        self.originalModifiedDate = originalModified
        self.originalCreatedDate = originalCreated
        self.timestamp = Date()
    }
}
