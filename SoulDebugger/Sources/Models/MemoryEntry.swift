import Foundation
import GRDB

/// Maps `working_memory` table in memory.db.
/// Also used for `working_memory_archive` (with extra archive fields).
struct MemoryEntry: Codable, Identifiable, Equatable, Sendable, FetchableRecord, TableRecord {
    static let databaseTableName = "working_memory"

    var id: Int64
    var channel: String
    var threadTs: String
    var userId: String
    var entryType: EntryType
    var verb: String?
    var content: String
    var metadata: String?
    var traceId: String?
    var displayName: String?
    var region: String?
    var createdAt: Double

    var date: Date { Date(timeIntervalSince1970: createdAt) }

    var decodedMetadata: [String: String]? {
        guard let metadata, let data = metadata.data(using: .utf8) else { return nil }
        return try? JSONDecoder().decode([String: String].self, from: data)
    }

    enum CodingKeys: String, CodingKey, ColumnExpression {
        case id, channel
        case threadTs = "thread_ts"
        case userId = "user_id"
        case entryType = "entry_type"
        case verb, content, metadata
        case traceId = "trace_id"
        case displayName = "display_name"
        case region
        case createdAt = "created_at"
    }
}

/// The 14 cognitive entry types defined in Claudicle.
enum EntryType: String, Codable, CaseIterable, Sendable {
    case userMessage
    case internalMonologue
    case externalDialog
    case mentalQuery
    case toolAction
    case decision
    case daimonicIntuition
    case onboardingStep
    case memorySummary
    case soulStateShift
    case lifecycle
    case modelShed
    case myceliumContext
    case myceliumSpore
}

/// Archive-specific variant with extra columns.
struct ArchivedMemoryEntry: Codable, Identifiable, Sendable, FetchableRecord, TableRecord {
    static let databaseTableName = "working_memory_archive"

    var id: Int64
    var channel: String
    var threadTs: String
    var userId: String
    var entryType: EntryType
    var verb: String?
    var content: String
    var metadata: String?
    var traceId: String?
    var displayName: String?
    var region: String?
    var createdAt: Double
    var archivedAt: Double
    var compressionTraceId: String?

    var date: Date { Date(timeIntervalSince1970: createdAt) }
    var archiveDate: Date { Date(timeIntervalSince1970: archivedAt) }

    enum CodingKeys: String, CodingKey, ColumnExpression {
        case id, channel
        case threadTs = "thread_ts"
        case userId = "user_id"
        case entryType = "entry_type"
        case verb, content, metadata
        case traceId = "trace_id"
        case displayName = "display_name"
        case region
        case createdAt = "created_at"
        case archivedAt = "archived_at"
        case compressionTraceId = "compression_trace_id"
    }
}
