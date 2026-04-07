import Foundation
import GRDB

/// Maps `model_sheds` table in memory.db.
/// Tracks evolution of user models/dossiers as git-like diffs.
struct ShedRecord: Codable, Identifiable, Sendable, FetchableRecord, TableRecord {
    static let databaseTableName = "model_sheds"

    var id: Int64
    var entityId: String
    var entityName: String
    var entityType: String
    var oldContent: String
    var newContent: String
    var diff: String
    var monologue: String?
    var changeNote: String?
    var metaCommentary: String?
    var traceId: String?
    var channel: String
    var threadTs: String
    var createdAt: Double

    var date: Date { Date(timeIntervalSince1970: createdAt) }

    enum CodingKeys: String, CodingKey, ColumnExpression {
        case id
        case entityId = "entity_id"
        case entityName = "entity_name"
        case entityType = "entity_type"
        case oldContent = "old_content"
        case newContent = "new_content"
        case diff, monologue
        case changeNote = "change_note"
        case metaCommentary = "meta_commentary"
        case traceId = "trace_id"
        case channel
        case threadTs = "thread_ts"
        case createdAt = "created_at"
    }
}
