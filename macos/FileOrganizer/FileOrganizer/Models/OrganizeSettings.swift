import Foundation
import SwiftUI

enum DefaultAction: String, CaseIterable, Identifiable {
    case organize = "Organize"
    case deduplicateOnly = "Deduplicate Only"
    case timestampsOnly = "Timestamps Only"
    var id: String { rawValue }
}

enum NameScheme: String, CaseIterable, Identifiable {
    case lowercase = "lowercase"
    case uppercase = "UPPERCASE"
    case titleCase = "Title Case"
    case custom = "Custom"
    var id: String { rawValue }
}

enum DuplicatePolicy: String, CaseIterable, Identifiable {
    case keepOldest = "Keep Oldest"
    case keepNewest = "Keep Newest"
    case keepLargest = "Keep Largest"
    var id: String { rawValue }
}

enum DateSource: String, CaseIterable, Identifiable {
    case filename = "Filename"
    case exif = "EXIF"
    case current = "Current"
    var id: String { rawValue }
}

@Observable
class OrganizeSettings {
    // MARK: - General
    var defaultAction: DefaultAction = .organize
    var dryRunByDefault: Bool = false
    var showNotifications: Bool = true
    var launchAtLogin: Bool = false

    // MARK: - Date Handling
    var setModifiedDate: Bool = true
    var setCreatedDate: Bool = true
    var setAccessedDate: Bool = false
    var dateSourcePriority: DateSource = .filename

    // MARK: - Duplicates
    var enableDuplicateDetection: Bool = true
    var hashThresholdMB: Int = 100
    var duplicatePolicy: DuplicatePolicy = .keepOldest
    var exemptFolderName: String = "coomer"
    var enableExemptFolder: Bool = true

    // MARK: - Organization
    var enableFileMoving: Bool = true
    var nameScheme: NameScheme = .lowercase
    var customCategories: [String: [String]] = FileCategory.defaultCategories
    var folderMappings: [String: String] = FileCategory.defaultFolderMappings

    // MARK: - Persistence

    func save() {
        // TODO: Persist to UserDefaults / JSON in Application Support
    }

    func load() {
        // TODO: Load from UserDefaults / JSON
    }
}
