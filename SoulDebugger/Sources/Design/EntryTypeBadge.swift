import SwiftUI

/// Colored badge for displaying an EntryType or Phase tag.
struct EntryTypeBadge: View {
    let label: String
    let color: Color

    init(entryType: EntryType) {
        self.label = entryType.rawValue
        self.color = SoulColor.color(for: entryType)
    }

    init(phase: Phase) {
        self.label = phase.rawValue
        self.color = SoulColor.color(for: phase)
    }

    init(label: String, color: Color) {
        self.label = label
        self.color = color
    }

    var body: some View {
        Text(label)
            .font(SoulFont.monoSmall)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(color.opacity(0.2))
            .foregroundStyle(color)
            .clipShape(RoundedRectangle(cornerRadius: 4))
    }
}
