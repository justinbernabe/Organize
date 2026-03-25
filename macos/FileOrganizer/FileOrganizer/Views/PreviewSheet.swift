import SwiftUI

/// Dry-run results modal showing planned operations before execution.
struct PreviewSheet: View {
    let operations: [FileOperation]
    let onConfirm: () -> Void
    let onCancel: () -> Void

    var body: some View {
        VStack(spacing: 0) {
            Text("Preview — \(operations.count) operations")
                .font(.headline)
                .padding()

            Divider()

            Table(operations) {
                TableColumn("Type") { op in
                    Text(op.type.rawValue.capitalized)
                        .font(.caption)
                }
                .width(80)

                TableColumn("Source") { op in
                    Text(op.sourceURL.lastPathComponent)
                        .lineLimit(1)
                        .truncationMode(.middle)
                }

                TableColumn("Destination") { op in
                    Text(op.destinationURL?.lastPathComponent ?? "—")
                        .lineLimit(1)
                        .truncationMode(.middle)
                        .foregroundStyle(.secondary)
                }
            }
            .frame(minHeight: 300)

            Divider()

            HStack {
                Button("Cancel", role: .cancel, action: onCancel)
                    .keyboardShortcut(.cancelAction)

                Spacer()

                Button("Apply \(operations.count) Operations", action: onConfirm)
                    .keyboardShortcut(.defaultAction)
            }
            .padding()
        }
        .frame(width: 600, height: 450)
    }
}
