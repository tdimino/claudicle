import Foundation
import GRDB

/// Maps `soul_state_transitions` table in memory.db.
/// Audit log of emotional state changes across all channels.
struct SoulTransition: Codable, Identifiable, Equatable, Sendable, FetchableRecord, TableRecord {
    static let databaseTableName = "soul_state_transitions"

    var id: Int64
    var soulId: String
    var field: String
    var oldValue: String?
    var newValue: String
    var channel: String
    var metadata: String?
    var createdAt: Double

    var date: Date { Date(timeIntervalSince1970: createdAt) }

    enum CodingKeys: String, CodingKey, ColumnExpression {
        case id
        case soulId = "soul_id"
        case field
        case oldValue = "old_value"
        case newValue = "new_value"
        case channel, metadata
        case createdAt = "created_at"
    }
}
