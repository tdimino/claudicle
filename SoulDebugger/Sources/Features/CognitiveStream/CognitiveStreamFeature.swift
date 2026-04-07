import ComposableArchitecture
import Foundation
import IdentifiedCollections

/// Live tail of soul-stream.jsonl with phase-colored entries.
/// Phase 1: placeholder state. Phase 2: real StreamClient integration.
@Reducer
struct CognitiveStreamFeature {
    @ObservableState
    struct State: Equatable {
        var events: IdentifiedArrayOf<SoulStreamEvent> = []
        var selectedEventId: String?
        var phaseFilter: Phase?
        var isStreaming = false
    }

    enum Action {
        case onAppear
        case eventReceived(SoulStreamEvent)
        case eventSelected(String?)
        case phaseFilterChanged(Phase?)
        case startStreaming
        case stopStreaming
    }

    private enum CancelID { case streamTail }

    @Dependency(\.streamClient) var streamClient

    var body: some ReducerOf<Self> {
        Reduce { state, action in
            switch action {
            case .onAppear:
                // Phase 2: kick off .startStreaming here
                return .none

            case let .eventReceived(event):
                state.events.append(event)
                if state.events.count > 500 {
                    state.events.removeFirst()
                }
                return .none

            case let .eventSelected(id):
                state.selectedEventId = id
                return .none

            case let .phaseFilterChanged(phase):
                state.phaseFilter = phase
                return .none

            case .startStreaming:
                state.isStreaming = true
                return .none

            case .stopStreaming:
                state.isStreaming = false
                return .none
            }
        }
    }
}
