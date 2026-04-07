import Foundation
import GRDB

/// Maps `soul_memory` table in memory.db.
/// Key-value persistent state scoped by soul_id.
struct SoulMemoryEntry: Codable, Identifiable, Sendable, FetchableRecord, TableRecord {
    static let databaseTableName = "soul_memory"

    var id: String { "\(soulId)-\(key)" }
    var key: String
    var soulId: String
    var value: String
    var updatedAt: Double

    var updatedDate: Date { Date(timeIntervalSince1970: updatedAt) }

    enum CodingKeys: String, CodingKey, ColumnExpression {
        case key
        case soulId = "soul_id"
        case value
        case updatedAt = "updated_at"
    }
}
