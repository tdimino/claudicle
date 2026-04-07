import ComposableArchitecture
import SwiftUI

/// Root reducer composing all Phase 1 features with tab-based navigation.
@Reducer
struct AppFeature {
    @ObservableState
    struct State: Equatable {
        var selectedTab: SidebarSection = .cognitiveStream
        var cognitiveStream = CognitiveStreamFeature.State()
        var workingMemory = WorkingMemoryFeature.State()
        var soulState = SoulStateFeature.State()
    }

    enum Action {
        case tabSelected(SidebarSection)
        case cognitiveStream(CognitiveStreamFeature.Action)
        case workingMemory(WorkingMemoryFeature.Action)
        case soulState(SoulStateFeature.Action)
    }

    var body: some ReducerOf<Self> {
        Scope(state: \.cognitiveStream, action: \.cognitiveStream) {
            CognitiveStreamFeature()
        }
        Scope(state: \.workingMemory, action: \.workingMemory) {
            WorkingMemoryFeature()
        }
        Scope(state: \.soulState, action: \.soulState) {
            SoulStateFeature()
        }
        Reduce { state, action in
            switch action {
            case let .tabSelected(tab):
                state.selectedTab = tab
                return .none
            case .cognitiveStream, .workingMemory, .soulState:
                return .none
            }
        }
    }
}

/// Sidebar sections — an enum, NOT a reducer (plan: "sidebar has no effects").
enum SidebarSection: String, CaseIterable, Identifiable, Sendable {
    case cognitiveStream = "Cognitive Stream"
    case workingMemory = "Working Memory"
    case soulState = "Soul State"

    var id: String { rawValue }

    var systemImage: String {
        switch self {
        case .cognitiveStream: "brain.head.profile"
        case .workingMemory: "memorychip"
        case .soulState: "heart.text.clipboard"
        }
    }
}

/// Root view with tab bar (Phase 1) — three-column layout deferred to Phase 2.
struct AppView: View {
    @Bindable var store: StoreOf<AppFeature>

    var body: some View {
        TabView(selection: $store.selectedTab.sending(\.tabSelected)) {
            CognitiveStreamView(
                store: store.scope(state: \.cognitiveStream, action: \.cognitiveStream)
            )
            .tabItem {
                Label(SidebarSection.cognitiveStream.rawValue, systemImage: SidebarSection.cognitiveStream.systemImage)
            }
            .tag(SidebarSection.cognitiveStream)

            WorkingMemoryView(
                store: store.scope(state: \.workingMemory, action: \.workingMemory)
            )
            .tabItem {
                Label(SidebarSection.workingMemory.rawValue, systemImage: SidebarSection.workingMemory.systemImage)
            }
            .tag(SidebarSection.workingMemory)

            SoulStateView(
                store: store.scope(state: \.soulState, action: \.soulState)
            )
            .tabItem {
                Label(SidebarSection.soulState.rawValue, systemImage: SidebarSection.soulState.systemImage)
            }
            .tag(SidebarSection.soulState)
        }
        .frame(minWidth: 800, minHeight: 600)
    }
}
