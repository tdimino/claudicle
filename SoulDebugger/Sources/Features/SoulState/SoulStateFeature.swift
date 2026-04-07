import ComposableArchitecture
import Foundation
import IdentifiedCollections

/// Topic stack + emotional state + recent transitions.
@Reducer
struct SoulStateFeature {
    @ObservableState
    struct State: Equatable {
        var topics: IdentifiedArrayOf<SoulTopic> = []
        var emotionalState: String = "neutral"
        var transitions: IdentifiedArrayOf<SoulTransition> = []
        var isLoading = false
    }

    enum Action {
        case onAppear
        case topicsLoaded([SoulTopic])
        case emotionalStateLoaded(String)
        case transitionsLoaded([SoulTransition])
        case refresh
    }

    @Dependency(\.databaseClient) var db

    var body: some ReducerOf<Self> {
        Reduce { state, action in
            switch action {
            case .onAppear, .refresh:
                state.isLoading = true
                return .run { send in
                    async let topics = db.topicStack()
                    async let emotional = db.emotionalState()
                    async let transitions = db.transitions(20)
                    try await send(.topicsLoaded(topics))
                    try await send(.emotionalStateLoaded(emotional))
                    try await send(.transitionsLoaded(transitions))
                }

            case let .topicsLoaded(topics):
                state.topics = IdentifiedArrayOf(uniqueElements: topics)
                state.isLoading = false
                return .none

            case let .emotionalStateLoaded(emotional):
                state.emotionalState = emotional
                return .none

            case let .transitionsLoaded(transitions):
                state.transitions = IdentifiedArrayOf(uniqueElements: transitions)
                return .none
            }
        }
    }
}
