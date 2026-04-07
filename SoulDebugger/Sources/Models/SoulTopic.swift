import Foundation
import GRDB

/// Maps `soul_topics` table in memory.db.
/// Topic stack: 1 primary (rank=0) + up to 7 subtopics.
struct SoulTopic: Codable, Identifiable, Equatable, Sendable, FetchableRecord, TableRecord {
    static let databaseTableName = "soul_topics"

    var id: Int64
    var soulId: String
    var rank: Int
    var label: String
    var metadata: String?
    var promotedAt: Double
    var createdAt: Double

    var isPrimary: Bool { rank == 0 }
    var promotedDate: Date { Date(timeIntervalSince1970: promotedAt) }
    var createdDate: Date { Date(timeIntervalSince1970: createdAt) }

    enum CodingKeys: String, CodingKey, ColumnExpression {
        case id
        case soulId = "soul_id"
        case rank, label, metadata
        case promotedAt = "promoted_at"
        case createdAt = "created_at"
    }
}
