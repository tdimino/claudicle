import ComposableArchitecture
import SwiftUI

struct SoulStateView: View {
    @Bindable var store: StoreOf<SoulStateFeature>

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text("Soul State")
                    .font(SoulFont.monoLarge)
                    .foregroundStyle(SoulColor.violet)

                Spacer()

                Button(action: { store.send(.refresh) }) {
                    Image(systemName: "arrow.clockwise")
                }
            }
            .padding()

            Divider()

            if store.isLoading {
                ProgressView("Loading...")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ScrollView {
                    VStack(alignment: .leading, spacing: 16) {
                        // Emotional state badge
                        HStack {
                            Text("Emotional State")
                                .font(SoulFont.label)
                                .foregroundStyle(.secondary)
                            Spacer()
                            EntryTypeBadge(
                                label: store.emotionalState,
                                color: SoulColor.color(forEmotionalState: store.emotionalState)
                            )
                        }
                        .padding(.horizontal)

                        Divider()

                        // Topic stack
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Topic Stack")
                                .font(SoulFont.label)
                                .foregroundStyle(.secondary)
                                .padding(.horizontal)

                            if store.topics.isEmpty {
                                Text("No active topics")
                                    .font(SoulFont.mono)
                                    .foregroundStyle(.tertiary)
                                    .padding(.horizontal)
                            } else {
                                ForEach(store.topics) { topic in
                                    HStack(spacing: 8) {
                                        Text(topic.isPrimary ? "Primary" : "Sub \(topic.rank)")
                                            .font(SoulFont.monoSmall)
                                            .foregroundStyle(topic.isPrimary ? SoulColor.teal : .secondary)
                                            .frame(width: 70, alignment: .leading)

                                        Text(topic.label)
                                            .font(topic.isPrimary ? SoulFont.mono.bold() : SoulFont.mono)

                                        Spacer()

                                        Text(topic.promotedDate, style: .relative)
                                            .font(SoulFont.monoSmall)
                                            .foregroundStyle(.tertiary)
                                    }
                                    .padding(.horizontal)
                                }
                            }
                        }

                        Divider()

                        // Recent transitions
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Recent Transitions")
                                .font(SoulFont.label)
                                .foregroundStyle(.secondary)
                                .padding(.horizontal)

                            if store.transitions.isEmpty {
                                Text("No transitions recorded")
                                    .font(SoulFont.mono)
                                    .foregroundStyle(.tertiary)
                                    .padding(.horizontal)
                            } else {
                                ForEach(store.transitions) { transition in
                                    HStack(spacing: 8) {
                                        Text(transition.field)
                                            .font(SoulFont.monoSmall)
                                            .foregroundStyle(.secondary)

                                        if let old = transition.oldValue {
                                            Text(old)
                                                .font(SoulFont.monoSmall)
                                                .foregroundStyle(.red.opacity(0.6))
                                                .strikethrough()
                                        }

                                        Image(systemName: "arrow.right")
                                            .font(.caption2)
                                            .foregroundStyle(.tertiary)

                                        Text(transition.newValue)
                                            .font(SoulFont.monoSmall)
                                            .foregroundStyle(.green)

                                        Spacer()

                                        Text(transition.date, style: .relative)
                                            .font(SoulFont.monoSmall)
                                            .foregroundStyle(.tertiary)
                                    }
                                    .padding(.horizontal)
                                }
                            }
                        }
                    }
                    .padding(.vertical)
                }
            }
        }
        .background(SoulColor.navy)
        .onAppear { store.send(.onAppear) }
    }
}
