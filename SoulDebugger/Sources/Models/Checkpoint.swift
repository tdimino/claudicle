import Foundation
import GRDB

/// Maps `wm_checkpoints` table in memory.db.
/// Point-in-time bookmarks for working memory rollback.
struct Checkpoint: Codable, Identifiable, Sendable, FetchableRecord, TableRecord {
    static let databaseTableName = "wm_checkpoints"

    var id: Int64
    var name: String
    var channel: String
    var threadTs: String
    var createdAt: Double
    var maxEntryId: Int64
    var soulStateJson: String?
    var metadata: String?

    var date: Date { Date(timeIntervalSince1970: createdAt) }

    enum CodingKeys: String, CodingKey, ColumnExpression {
        case id, name, channel
        case threadTs = "thread_ts"
        case createdAt = "created_at"
        case maxEntryId = "max_entry_id"
        case soulStateJson = "soul_state_json"
        case metadata
    }
}
