import ComposableArchitecture
import Foundation

/// TCA dependency for all SQLite reads against Claudicle's memory.db and sessions.db.
/// Phase 1: stubs returning empty data. Phase 2: GRDB read-only pool + WAL monitoring.
@DependencyClient
struct DatabaseClient: Sendable {
    // MARK: - Working Memory

    var recentEntries: @Sendable (_ channel: String, _ limit: Int) async throws -> [MemoryEntry] = { _, _ in [] }
    var entriesForTrace: @Sendable (_ traceId: String) async throws -> [MemoryEntry] = { _ in [] }
    var regions: @Sendable (_ channel: String, _ threadTs: String) async throws -> [String] = { _, _ in [] }
    var regionEntries: @Sendable (_ channel: String, _ threadTs: String, _ region: String) async throws -> [MemoryEntry] = { _, _, _ in [] }

    // MARK: - Soul State

    var topicStack: @Sendable () async throws -> [SoulTopic] = { [] }
    var transitions: @Sendable (_ limit: Int) async throws -> [SoulTransition] = { _ in [] }
    var emotionalState: @Sendable () async throws -> String = { "neutral" }

    // MARK: - Soul Memory

    var soulMemory: @Sendable () async throws -> [SoulMemoryEntry] = { [] }

    // MARK: - User Models

    var allModels: @Sendable () async throws -> [UserModel] = { [] }
    var modelSheds: @Sendable (_ entityId: String) async throws -> [ShedRecord] = { _ in [] }

    // MARK: - Daimon Memory

    var daimonChannels: @Sendable () async throws -> [String] = { [] }
    var daimonEntries: @Sendable (_ agentName: String, _ limit: Int) async throws -> [MemoryEntry] = { _, _ in [] }
    var daimonLessons: @Sendable (_ agentName: String) async throws -> [MemoryEntry] = { _ in [] }

    // MARK: - Sessions

    var activeSessions: @Sendable () async throws -> [Session] = { [] }

    // MARK: - Checkpoints

    var checkpoints: @Sendable (_ channel: String) async throws -> [Checkpoint] = { _ in [] }

    // MARK: - Stats

    var entryCount: @Sendable () async throws -> Int = { 0 }
    var channelList: @Sendable () async throws -> [String] = { [] }
}

extension DatabaseClient: DependencyKey {
    static let liveValue = DatabaseClient()
    static let testValue = DatabaseClient()
}

extension DependencyValues {
    var databaseClient: DatabaseClient {
        get { self[DatabaseClient.self] }
        set { self[DatabaseClient.self] = newValue }
    }
}
