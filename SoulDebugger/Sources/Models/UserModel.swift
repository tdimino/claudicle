import Foundation
import GRDB

/// Maps `user_models` table in memory.db.
struct UserModel: Codable, Identifiable, Sendable, FetchableRecord, TableRecord {
    static let databaseTableName = "user_models"

    var id: String { userId }
    var userId: String
    var displayName: String?
    var modelMd: String
    var entityType: String?
    var interactionCount: Int
    var createdAt: Double
    var updatedAt: Double

    var createdDate: Date { Date(timeIntervalSince1970: createdAt) }
    var updatedDate: Date { Date(timeIntervalSince1970: updatedAt) }

    enum CodingKeys: String, CodingKey, ColumnExpression {
        case userId = "user_id"
        case displayName = "display_name"
        case modelMd = "model_md"
        case entityType = "entity_type"
        case interactionCount = "interaction_count"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
}

/// Maps `user_model_modules` table in memory.db.
struct UserModelModule: Codable, Identifiable, Sendable, FetchableRecord, TableRecord {
    var id: String { "\(userId)-\(moduleName)" }

    static let databaseTableName = "user_model_modules"

    var userId: String
    var moduleName: String
    var moduleMd: String
    var createdAt: Double
    var updatedAt: Double

    enum CodingKeys: String, CodingKey, ColumnExpression {
        case userId = "user_id"
        case moduleName = "module_name"
        case moduleMd = "module_md"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
}
