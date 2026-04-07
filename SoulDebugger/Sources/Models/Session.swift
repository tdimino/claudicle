import Foundation
import GRDB

/// Maps `sessions` table in sessions.db.
/// Tracks ensouled Claude Code sessions across channels.
struct Session: Codable, Identifiable, Sendable, FetchableRecord, TableRecord {
    static let databaseTableName = "sessions"

    var id: String { "\(channel)-\(threadTs)" }
    var channel: String
    var threadTs: String
    var sessionId: String
    var createdAt: Double
    var lastUsed: Double

    var createdDate: Date { Date(timeIntervalSince1970: createdAt) }
    var lastUsedDate: Date { Date(timeIntervalSince1970: lastUsed) }

    enum CodingKeys: String, CodingKey, ColumnExpression {
        case channel
        case threadTs = "thread_ts"
        case sessionId = "session_id"
        case createdAt = "created_at"
        case lastUsed = "last_used"
    }
}
