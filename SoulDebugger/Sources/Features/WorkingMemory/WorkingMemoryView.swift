import ComposableArchitecture
import SwiftUI

struct WorkingMemoryView: View {
    @Bindable var store: StoreOf<WorkingMemoryFeature>

    var body: some View {
        VStack(spacing: 0) {
            // Header with channel picker + region tabs
            HStack {
                Text("Working Memory")
                    .font(SoulFont.monoLarge)
                    .foregroundStyle(SoulColor.violet)

                Spacer()

                if !store.channels.isEmpty {
                    Picker("Channel", selection: $store.selectedChannel.sending(\.channelSelected)) {
                        Text("Select Channel").tag(String?.none)
                        ForEach(store.channels, id: \.self) { channel in
                            Text(channel).tag(String?.some(channel))
                        }
                    }
                    .pickerStyle(.menu)
                    .frame(width: 220)
                }
            }
            .padding()

            // Region tabs
            HStack(spacing: 12) {
                ForEach(store.availableRegions, id: \.self) { region in
                    Button(action: { store.send(.regionSelected(region)) }) {
                        Text(region)
                            .font(SoulFont.monoSmall)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(
                                store.selectedRegion == region
                                    ? SoulColor.teal.opacity(0.2)
                                    : Color.clear
                            )
                            .clipShape(RoundedRectangle(cornerRadius: 4))
                    }
                    .buttonStyle(.plain)
                }
                Spacer()
            }
            .padding(.horizontal)

            Divider()

            // Entry list
            if store.isLoading {
                ProgressView("Loading...")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if store.entries.isEmpty {
                ContentUnavailableView {
                    Label("No Entries", systemImage: "memorychip")
                } description: {
                    Text("Working memory entries will appear here once Claudicle processes messages.")
                }
            } else {
                List(store.entries) { entry in
                    HStack(spacing: 8) {
                        EntryTypeBadge(entryType: entry.entryType)

                        if let verb = entry.verb {
                            Text(verb)
                                .font(SoulFont.monoSmall)
                                .foregroundStyle(.secondary)
                                .italic()
                        }

                        Text(entry.content.prefix(80))
                            .font(SoulFont.mono)
                            .lineLimit(1)

                        Spacer()

                        Text(entry.date, style: .relative)
                            .font(SoulFont.monoSmall)
                            .foregroundStyle(.tertiary)
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
