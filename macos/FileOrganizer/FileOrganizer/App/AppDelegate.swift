import AppKit

/// Handles dock icon drag-and-drop and app-level events.
class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        NotificationService.requestPermission()
    }

    /// Accept folder drops on the dock icon.
    func application(_ sender: NSApplication, openFiles filenames: [String]) {
        let urls = filenames.compactMap { URL(fileURLWithPath: $0) }
        let folders = urls.filter {
            var isDir: ObjCBool = false
            return FileManager.default.fileExists(atPath: $0.path, isDirectory: &isDir) && isDir.boolValue
        }
        guard !folders.isEmpty else { return }
        // TODO: Pass folders to MainWindow via environment or notification
        NSApplication.shared.reply(toOpenOrPrint: .success)
    }
}
