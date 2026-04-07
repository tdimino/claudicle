import Foundation

/// Parsed from soul-stream.jsonl.
/// Each line is a JSON object with phase, trace_id, ts, channel, thread_ts, plus phase-specific fields.
struct SoulStreamEvent: Codable, Identifiable, Equatable, Sendable {
    var id: String { "\(traceId ?? "none")-\(ts)" }

    var phase: Phase
    var traceId: String?
    var ts: String
    var channel: String?
    var threadTs: String?

    /// Phase-specific fields — populated in Phase 2 detail views.
    // TODO: Phase 2 — decode remaining JSON keys into extras
    var extras: [String: AnyCodable]?

    var date: Date? {
        try? Date(ts, strategy: .iso8601)
    }

    enum CodingKeys: String, CodingKey {
        case phase
        case traceId = "trace_id"
        case ts, channel
        case threadTs = "thread_ts"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        phase = try container.decode(Phase.self, forKey: .phase)
        traceId = try container.decodeIfPresent(String.self, forKey: .traceId)
        ts = try container.decode(String.self, forKey: .ts)
        channel = try container.decodeIfPresent(String.self, forKey: .channel)
        threadTs = try container.decodeIfPresent(String.self, forKey: .threadTs)
        extras = nil
    }
}

/// Cognitive pipeline phases from soul_log.py.
enum Phase: String, Codable, CaseIterable, Sendable {
    case stimulus
    case context
    case cognition
    case decision
    case memory
    case response
    case error
}

/// Type-erased JSON value for extras dictionary.
enum AnyCodable: Codable, Equatable, Sendable {
    case string(String)
    case int(Int)
    case double(Double)
    case bool(Bool)
    case null

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let s = try? container.decode(String.self) { self = .string(s) }
        else if let i = try? container.decode(Int.self) { self = .int(i) }
        else if let d = try? container.decode(Double.self) { self = .double(d) }
        else if let b = try? container.decode(Bool.self) { self = .bool(b) }
        else if container.decodeNil() { self = .null }
        else { self = .null }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .string(let s): try container.encode(s)
        case .int(let i): try container.encode(i)
        case .double(let d): try container.encode(d)
        case .bool(let b): try container.encode(b)
        case .null: try container.encodeNil()
        }
    }
}
