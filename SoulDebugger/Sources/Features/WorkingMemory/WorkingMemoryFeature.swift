import ComposableArchitecture
import Foundation
import IdentifiedCollections

/// Channel selector + paginated entry list with region tabs.
@Reducer
struct WorkingMemoryFeature {
    @ObservableState
    struct State: Equatable {
        var channels: [String] = []
        var selectedChannel: String?
        var entries: IdentifiedArrayOf<MemoryEntry> = []
        var selectedEntryId: Int64?
        var selectedRegion: String = "default"
        var availableRegions: [String] = ["default"]
        var isLoading = false
    }

    enum Action {
        case onAppear
        case channelsLoaded([String])
        case channelSelected(String?)
        case entriesLoaded([MemoryEntry])
        case entrySelected(Int64?)
        case regionSelected(String)
        case regionsLoaded([String])
        case loadMore
    }

    @Dependency(\.databaseClient) var db

    var body: some ReducerOf<Self> {
        Reduce { state, action in
            switch action {
            case .onAppear:
                state.isLoading = true
                return .run { send in
                    let channels = try await db.channelList()
                    await send(.channelsLoaded(channels))
                }

            case let .channelsLoaded(channels):
                state.channels = channels
                state.isLoading = false
                if state.selectedChannel == nil, let first = channels.first {
                    state.selectedChannel = first
                    return .send(.channelSelected(first))
                }
                return .none

            case let .channelSelected(channel):
                state.selectedChannel = channel
                guard let channel else { return .none }
                return .run { send in
                    let entries = try await db.recentEntries(channel, 200)
                    await send(.entriesLoaded(entries))
                }

            case let .entriesLoaded(entries):
                state.entries = IdentifiedArrayOf(uniqueElements: entries)
                return .none

            case let .entrySelected(id):
                state.selectedEntryId = id
                return .none

            case let .regionSelected(region):
                state.selectedRegion = region
                return .none

            case let .regionsLoaded(regions):
                state.availableRegions = regions
                return .none

            case .loadMore:
                return .none
            }
        }
    }
}
