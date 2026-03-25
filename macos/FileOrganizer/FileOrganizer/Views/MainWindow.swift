import SwiftUI

/// Main app window composing drop zone, file list, and progress.
/// ImageOptim-inspired: empty state shows drop zone, active state shows file table.
struct MainWindow: View {
    @State private var folders: [URL] = []
    @State private var files: [FileEntry] = []
    @State private var isProcessing = false
    @State private var isDryRun = false

    @State private var settings = OrganizeSettings()
    @State private var history = OperationHistory()

    var body: some View {
        VStack(spacing: 0) {
            // Toolbar area
            toolbar

            Divider()

            // Main content
            if files.isEmpty && !isProcessing {
                // Empty state: full drop zone
                DropZoneView(droppedFolders: $folders)
                    .padding(24)
                    .frame(minHeight: 300)
            } else {
                // Active state: compact drop zone + file list
                VStack(spacing: 0) {
                    DropZoneView(droppedFolders: $folders)
                        .frame(height: 60)
                        .padding(.horizontal)
                        .padding(.top, 8)

                    FileListView(files: $files)
                        .frame(minHeight: 200)
                }
            }

            Divider()

            // Status bar
            statusBar
        }
        .frame(minWidth: 600, minHeight: 450)
        .onChange(of: folders) { _, newFolders in
            scanFolders(newFolders)
        }
    }

    // MARK: - Toolbar

    private var toolbar: some View {
        HStack {
            Text("File Organizer")
                .font(.headline)

            Spacer()

            Toggle("Preview", isOn: $isDryRun)
                .toggleStyle(.switch)
                .controlSize(.small)

            Button(isProcessing ? "Stop" : "Start") {
                if isProcessing {
                    stopProcessing()
                } else {
                    startProcessing()
                }
            }
            .keyboardShortcut("r", modifiers: .command)
            .disabled(folders.isEmpty)
        }
        .padding(.horizontal)
        .padding(.vertical, 8)
    }

    // MARK: - Status Bar

    private var statusBar: some View {
        HStack {
            let total = files.count
            let done = files.filter { $0.status == .done }.count
            let dupes = files.filter { $0.status == .duplicate }.count
            let errors = files.filter { $0.status == .error }.count

            Text("\(total) files")
            if dupes > 0 { Text("• \(dupes) dupes").foregroundStyle(.orange) }
            if errors > 0 { Text("• \(errors) errors").foregroundStyle(.red) }
            if done > 0 { Text("• \(done) done").foregroundStyle(.green) }

            Spacer()
        }
        .font(.caption)
        .foregroundStyle(.secondary)
        .padding(.horizontal)
        .padding(.vertical, 6)
    }

    // MARK: - Actions

    private func scanFolders(_ urls: [URL]) {
        // TODO: Use FileSystemService.scan() to populate files list
    }

    private func startProcessing() {
        isProcessing = true
        // TODO: Create OrganizeEngine, call process(), update files from stream
    }

    private func stopProcessing() {
        isProcessing = false
        // TODO: Cancel engine
    }
}
