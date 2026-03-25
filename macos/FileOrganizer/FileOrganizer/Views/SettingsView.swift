import SwiftUI

/// Preferences window with tabbed settings.
struct SettingsView: View {
    @Bindable var settings: OrganizeSettings

    var body: some View {
        TabView {
            GeneralTab(settings: settings)
                .tabItem { Label("General", systemImage: "gear") }

            DatesTab(settings: settings)
                .tabItem { Label("Dates", systemImage: "calendar") }

            DuplicatesTab(settings: settings)
                .tabItem { Label("Duplicates", systemImage: "doc.on.doc") }

            OrganizationTab(settings: settings)
                .tabItem { Label("Organization", systemImage: "folder") }
        }
        .frame(width: 450, height: 350)
    }
}

// MARK: - General Tab

private struct GeneralTab: View {
    @Bindable var settings: OrganizeSettings

    var body: some View {
        Form {
            Picker("Default action", selection: $settings.defaultAction) {
                ForEach(DefaultAction.allCases) { action in
                    Text(action.rawValue).tag(action)
                }
            }

            Toggle("Dry run by default (preview before executing)", isOn: $settings.dryRunByDefault)
            Toggle("Show notifications", isOn: $settings.showNotifications)
            Toggle("Launch at login", isOn: $settings.launchAtLogin)
        }
        .padding()
    }
}

// MARK: - Dates Tab

private struct DatesTab: View {
    @Bindable var settings: OrganizeSettings

    var body: some View {
        Form {
            Section("Set dates from filenames") {
                Toggle("Modified date", isOn: $settings.setModifiedDate)
                Toggle("Created date", isOn: $settings.setCreatedDate)
                Toggle("Accessed date", isOn: $settings.setAccessedDate)
            }

            Section("Date source priority") {
                Picker("Source", selection: $settings.dateSourcePriority) {
                    ForEach(DateSource.allCases) { source in
                        Text(source.rawValue).tag(source)
                    }
                }
                .pickerStyle(.radioGroup)
            }
        }
        .padding()
    }
}

// MARK: - Duplicates Tab

private struct DuplicatesTab: View {
    @Bindable var settings: OrganizeSettings

    var body: some View {
        Form {
            Toggle("Enable duplicate detection", isOn: $settings.enableDuplicateDetection)

            if settings.enableDuplicateDetection {
                Picker("Keep policy", selection: $settings.duplicatePolicy) {
                    ForEach(DuplicatePolicy.allCases) { policy in
                        Text(policy.rawValue).tag(policy)
                    }
                }

                HStack {
                    Text("Hash threshold")
                    TextField("MB", value: $settings.hashThresholdMB, format: .number)
                        .frame(width: 60)
                    Text("MB")
                        .foregroundStyle(.secondary)
                }

                Toggle("Enable exempt folder", isOn: $settings.enableExemptFolder)
                if settings.enableExemptFolder {
                    TextField("Exempt folder name", text: $settings.exemptFolderName)
                }
            }
        }
        .padding()
    }
}

// MARK: - Organization Tab

private struct OrganizationTab: View {
    @Bindable var settings: OrganizeSettings

    var body: some View {
        Form {
            Toggle("Enable file moving", isOn: $settings.enableFileMoving)

            Picker("Name scheme", selection: $settings.nameScheme) {
                ForEach(NameScheme.allCases) { scheme in
                    Text(scheme.rawValue).tag(scheme)
                }
            }

            // TODO: Category rules editor (extension→category table)
            // TODO: Folder normalization mappings editor
            Section("Categories") {
                Text("Category rules editor — coming soon")
                    .foregroundStyle(.secondary)
            }
        }
        .padding()
    }
}
