import SwiftUI

/// Represents a file in the processing queue.
struct FileEntry: Identifiable {
    let id = UUID()
    let url: URL
    var category: String = ""
    var status: FileStatus = .pending
    var detectedDate: Date? = nil

    var name: String { url.lastPathComponent }
    var size: String {
        let bytes = (try? url.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0
        return ByteCountFormatter.string(fromByteCount: Int64(bytes), countStyle: .file)
    }
}

/// Table showing files with their status, category, and detected dates.
struct FileListView: View {
    @Binding var files: [FileEntry]

    var body: some View {
        Table(files) {
            TableColumn("Status") { file in
                statusIcon(for: file.status)
            }
            .width(40)

            TableColumn("Name") { file in
                Text(file.name)
                    .lineLimit(1)
                    .truncationMode(.middle)
            }

            TableColumn("Category") { file in
                Text(file.category)
                    .foregroundStyle(.secondary)
            }
            .width(80)

            TableColumn("Size") { file in
                Text(file.size)
                    .monospacedDigit()
                    .foregroundStyle(.secondary)
            }
            .width(80)

            TableColumn("Date") { file in
                if let date = file.detectedDate {
                    Text(date, style: .date)
                        .foregroundStyle(.secondary)
                } else {
                    Text("—")
                        .foregroundStyle(.quaternary)
                }
            }
            .width(100)
        }
    }

    @ViewBuilder
    private func statusIcon(for status: FileStatus) -> some View {
        switch status {
        case .pending:
            Image(systemName: "circle")
                .foregroundStyle(.tertiary)
        case .processing:
            ProgressView()
                .scaleEffect(0.5)
        case .done:
            Image(systemName: "checkmark.circle.fill")
                .foregroundStyle(.green)
        case .duplicate:
            Image(systemName: "doc.on.doc.fill")
                .foregroundStyle(.orange)
        case .skipped:
            Image(systemName: "minus.circle")
                .foregroundStyle(.secondary)
        case .error:
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundStyle(.red)
        }
    }
}
