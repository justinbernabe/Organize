import Foundation
import UserNotifications

/// macOS notification banners for organize completion.
struct NotificationService {
    static func requestPermission() {
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) { _, _ in }
    }

    static func notify(title: String, body: String) {
        let content = UNMutableNotificationContent()
        content.title = title
        content.body = body
        content.sound = .default

        let request = UNNotificationRequest(
            identifier: UUID().uuidString,
            content: content,
            trigger: nil
        )
        UNUserNotificationCenter.current().add(request)
    }

    static func notifyComplete(success: Int, errors: Int) {
        var body = "\(success) file\(success == 1 ? "" : "s") organized."
        if errors > 0 {
            body += " (\(errors) error\(errors == 1 ? "" : "s"))"
        }
        notify(title: "File Organizer", body: body)
    }
}
