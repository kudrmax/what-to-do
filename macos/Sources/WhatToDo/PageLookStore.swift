import AppKit
import LauncherCore

/// Remembers the page's look, so a window opens in the app's colours before the page loads.
struct PageLookStore {
    private static let backgroundKey = "PageBackgroundColor"
    private static let themeModeKey = "PageThemeMode"

    private let defaults: UserDefaults

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
    }

    func loadBackground() -> NSColor? {
        guard let data = defaults.data(forKey: Self.backgroundKey) else { return nil }
        return try? NSKeyedUnarchiver.unarchivedObject(ofClass: NSColor.self, from: data)
    }

    func saveBackground(_ color: NSColor) {
        guard let data = try? NSKeyedArchiver.archivedData(withRootObject: color, requiringSecureCoding: true) else { return }
        defaults.set(data, forKey: Self.backgroundKey)
    }

    func loadThemeMode() -> ThemeMode? {
        defaults.string(forKey: Self.themeModeKey).flatMap(ThemeMode.init)
    }

    func saveThemeMode(_ mode: ThemeMode) {
        defaults.set(mode.rawValue, forKey: Self.themeModeKey)
    }
}
