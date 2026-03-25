import SwiftUI

/// Shows per-phase progress during pipeline execution.
struct ProgressOverlay: View {
    let steps: [StepState]
    let elapsed: TimeInterval

    struct StepState: Identifiable {
        let id = UUID()
        let name: String
        var status: Status

        enum Status {
            case pending
            case active(current: Int, total: Int)
            case completed(summary: String)
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            ForEach(steps) { step in
                HStack(spacing: 8) {
                    stepIcon(step.status)
                        .frame(width: 16)

                    Text(step.name)
                        .font(.callout)

                    Spacer()

                    stepDetail(step.status)
                }
            }

            Divider()

            HStack {
                Text("Elapsed: \(formattedTime(elapsed))")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .monospacedDigit()
                Spacer()
            }
        }
        .padding()
    }

    @ViewBuilder
    private func stepIcon(_ status: StepState.Status) -> some View {
        switch status {
        case .pending:
            Image(systemName: "circle")
                .foregroundStyle(.tertiary)
        case .active:
            ProgressView()
                .scaleEffect(0.5)
        case .completed:
            Image(systemName: "checkmark.circle.fill")
                .foregroundStyle(.green)
        }
    }

    @ViewBuilder
    private func stepDetail(_ status: StepState.Status) -> some View {
        switch status {
        case .pending:
            EmptyView()
        case .active(let current, let total):
            Text("\(current)/\(total)")
                .font(.caption)
                .monospacedDigit()
                .foregroundStyle(.secondary)
        case .completed(let summary):
            Text(summary)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
    }

    private func formattedTime(_ interval: TimeInterval) -> String {
        let minutes = Int(interval) / 60
        let seconds = Int(interval) % 60
        return String(format: "%d:%02d", minutes, seconds)
    }
}
