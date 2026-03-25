import SwiftUI
import UniformTypeIdentifiers

/// Drag-and-drop target area for folders.
/// ImageOptim-inspired: large centered zone with folder icon.
struct DropZoneView: View {
    @Binding var droppedFolders: [URL]
    @State private var isTargeted = false

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 16)
                .strokeBorder(
                    style: StrokeStyle(lineWidth: 2, dash: [8, 4])
                )
                .foregroundStyle(isTargeted ? .accent : .secondary.opacity(0.4))
                .background(
                    RoundedRectangle(cornerRadius: 16)
                        .fill(isTargeted ? Color.accentColor.opacity(0.05) : .clear)
                )

            VStack(spacing: 12) {
                Image(systemName: "folder.badge.plus")
                    .font(.system(size: 48))
                    .foregroundStyle(.secondary)

                Text("Drop folders here")
                    .font(.title2)
                    .foregroundStyle(.secondary)

                Text("or click to browse")
                    .font(.caption)
                    .foregroundStyle(.tertiary)
            }
        }
        .onDrop(of: [.fileURL], isTargeted: $isTargeted) { providers in
            handleDrop(providers)
        }
        .onTapGesture {
            openFolderPicker()
        }
    }

    private func handleDrop(_ providers: [NSItemProvider]) -> Bool {
        for provider in providers {
            _ = provider.loadObject(ofClass: URL.self) { url, _ in
                guard let url = url else { return }
                var isDir: ObjCBool = false
                if FileManager.default.fileExists(atPath: url.path, isDirectory: &isDir), isDir.boolValue {
                    DispatchQueue.main.async {
                        if !droppedFolders.contains(url) {
                            droppedFolders.append(url)
                        }
                    }
                }
            }
        }
        return true
    }

    private func openFolderPicker() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.allowsMultipleSelection = true
        panel.message = "Select folders to organize"
        if panel.runModal() == .OK {
            for url in panel.urls {
                if !droppedFolders.contains(url) {
                    droppedFolders.append(url)
                }
            }
        }
    }
}
