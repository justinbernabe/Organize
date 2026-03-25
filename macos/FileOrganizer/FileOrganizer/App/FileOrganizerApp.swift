import SwiftUI

@main
struct FileOrganizerApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate

    var body: some Scene {
        WindowGroup {
            MainWindow()
        }
        .commands {
            CommandGroup(replacing: .newItem) {
                Button("Open Folder...") {
                    // TODO: Trigger folder picker
                }
                .keyboardShortcut("o", modifiers: .command)
            }
        }

        Settings {
            SettingsView(settings: OrganizeSettings())
        }
    }
}
