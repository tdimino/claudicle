import Foundation

/// Groups all working memory entries and soul stream events sharing a trace_id
/// into a single cognitive cycle visualization unit.
struct CognitiveTrace: Identifiable, Sendable {
    var id: String { traceId }
    let traceId: String
    var entries: [MemoryEntry]
    var streamEvents: [SoulStreamEvent]

    var startDate: Date? {
        entries.map(\.date).min()
    }

    var entryTypes: Set<EntryType> {
        Set(entries.map(\.entryType))
    }

    var channel: String? {
        entries.first?.channel
    }
}
