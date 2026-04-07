import SwiftUI

/// Minoan-Daimonic color system from the Soul Debugger plan.
/// Extends the existing monitor.py palette (deep navy + violet + teal).
enum SoulColor {
    // MARK: - Primary Spectrum

    static let violet = Color(hex: 0xBB86FC)
    static let teal = Color(hex: 0x03DAC6)
    static let navy = Color(hex: 0x0A0A1A)
    static let surface = Color(hex: 0x16213E)

    // MARK: - Entry Type Colors (12 types)

    static let userMessage = Color(hex: 0x64B5F6)
    static let internalMonologue = Color(hex: 0xCE93D8)
    static let externalDialog = Color(hex: 0x81C784)
    static let mentalQuery = Color(hex: 0xFFB74D)
    static let toolAction = Color(hex: 0x4FC3F7)
    static let decision = Color(hex: 0xFFF176)
    static let daimonicIntuition = Color(hex: 0xF48FB1)
    static let onboardingStep = Color(hex: 0xA5D6A7)
    static let memorySummary = Color(hex: 0x90A4AE)
    static let soulStateShift = Color(hex: 0xB39DDB)
    static let lifecycle = Color(hex: 0x78909C)
    static let modelShed = Color(hex: 0xFFCC80)

    // MARK: - Emotional State Gradient

    static let neutral = Color(hex: 0x90A4AE)
    static let engaged = Color(hex: 0x66BB6A)
    static let focused = Color(hex: 0x42A5F5)
    static let sardonic = Color(hex: 0xEF5350)
    static let frustrated = Color(hex: 0xFF7043)
    static let absorbed = Color(hex: 0xAB47BC)
    static let curious = Color(hex: 0x26C6DA)

    // MARK: - Phase Colors (soul-stream.jsonl)

    static let stimulus = Color(hex: 0xFFB74D)
    static let context = Color(hex: 0x90A4AE)
    static let cognition = Color(hex: 0xBB86FC)
    static let decisionPhase = Color(hex: 0x03DAC6)
    static let memory = Color(hex: 0x81C784)
    static let response = Color(hex: 0x64B5F6)
    static let error = Color(hex: 0xEF5350)

    /// Map an EntryType to its display color.
    static func color(for entryType: EntryType) -> Color {
        switch entryType {
        case .userMessage: userMessage
        case .internalMonologue: internalMonologue
        case .externalDialog: externalDialog
        case .mentalQuery: mentalQuery
        case .toolAction: toolAction
        case .decision: decision
        case .daimonicIntuition: daimonicIntuition
        case .onboardingStep: onboardingStep
        case .memorySummary: memorySummary
        case .soulStateShift: soulStateShift
        case .lifecycle: lifecycle
        case .modelShed: modelShed
        case .myceliumContext: teal
        case .myceliumSpore: teal
        }
    }

    /// Map a Phase to its display color.
    static func color(for phase: Phase) -> Color {
        switch phase {
        case .stimulus: stimulus
        case .context: context
        case .cognition: cognition
        case .decision: decisionPhase
        case .memory: memory
        case .response: response
        case .error: error
        }
    }

    /// Map an emotional state string to its display color.
    static func color(forEmotionalState state: String) -> Color {
        switch state.lowercased() {
        case "neutral": neutral
        case "engaged": engaged
        case "focused": focused
        case "sardonic": sardonic
        case "frustrated": frustrated
        case "absorbed": absorbed
        case "curious": curious
        default: neutral
        }
    }
}

// MARK: - Color Extension

extension Color {
    init(hex: UInt, opacity: Double = 1.0) {
        self.init(
            .sRGB,
            red: Double((hex >> 16) & 0xFF) / 255,
            green: Double((hex >> 8) & 0xFF) / 255,
            blue: Double(hex & 0xFF) / 255,
            opacity: opacity
        )
    }
}

// MARK: - Typography

enum SoulFont {
    static let mono = Font.system(.body, design: .monospaced)
    static let monoSmall = Font.system(.caption, design: .monospaced)
    static let monoLarge = Font.system(.title3, design: .monospaced)
    static let label = Font.system(.body, design: .default)
    static let labelSmall = Font.system(.caption, design: .default)
}
