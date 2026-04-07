import ComposableArchitecture
import SwiftUI

@main
struct SoulDebuggerApp: App {
    static let store = Store(initialState: AppFeature.State()) {
        AppFeature()
    }

    var body: some Scene {
        WindowGroup {
            AppView(store: Self.store)
        }
        .defaultSize(width: 1200, height: 800)
    }
}
