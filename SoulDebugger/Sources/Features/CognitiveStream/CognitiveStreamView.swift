import ComposableArchitecture
import SwiftUI

struct CognitiveStreamView: View {
    @Bindable var store: StoreOf<CognitiveStreamFeature>

    var body: some View {
        VStack(spacing: 0) {
            // Filter bar
            HStack {
                Text("Cognitive Stream")
                    .font(SoulFont.monoLarge)
                    .foregroundStyle(SoulColor.violet)

                Spacer()

                Picker("Phase", selection: $store.phaseFilter.sending(\.phaseFilterChanged)) {
                    Text("All Phases").tag(Phase?.none)
                    ForEach(Phase.allCases, id: \.self) { phase in
                        Text(phase.rawValue).tag(Phase?.some(phase))
                    }
                }
                .pickerStyle(.menu)
                .frame(width: 160)
            }
            .padding()

            Divider()

            // Event list
            if store.events.isEmpty {
                ContentUnavailableView {
                    Label("No Events", systemImage: "brain.head.profile")
                } description: {
                    Text("Soul stream events will appear here when the daemon is running.")
                }
            } else {
                let filtered = store.phaseFilter.map { phase in
                    store.events.filter { $0.phase == phase }
                } ?? Array(store.events)

                List(filtered, id: \.id) { event in
                    HStack(spacing: 8) {
                        EntryTypeBadge(phase: event.phase)

                        if let traceId = event.traceId {
                            Text(traceId.prefix(8))
                                .font(SoulFont.monoSmall)
                                .foregroundStyle(.secondary)
                        }

                        Spacer()

                        if let date = event.date {
                            Text(date, style: .time)
                                .font(SoulFont.monoSmall)
                                .foregroundStyle(.tertiary)
                        }
                    }
                    .padding(.vertical, 2)
                }
                .listStyle(.plain)
            }
        }
        .background(SoulColor.navy)
        .onAppear { store.send(.onAppear) }
    }
}
