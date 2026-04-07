import ComposableArchitecture
import Foundation

/// TCA dependency for tailing JSONL log files (soul-stream.jsonl, working-memory-stream.jsonl).
/// Phase 1: stubs returning empty streams. Phase 2: DispatchSource file monitoring.
@DependencyClient
struct StreamClient: Sendable {
    var soulStream: @Sendable () -> AsyncStream<SoulStreamEvent> = { .finished }
    var wmStream: @Sendable () -> AsyncStream<MemoryEntry> = { .finished }
}

extension StreamClient: DependencyKey {
    static let liveValue = StreamClient()
    static let testValue = StreamClient()
}

extension DependencyValues {
    var streamClient: StreamClient {
        get { self[StreamClient.self] }
        set { self[StreamClient.self] = newValue }
    }
}
