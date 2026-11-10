import AppKit
import LauncherCore

extension NSWindow {
    /// The window takes the page's own background, so the status screen opens in the app's colours.
    func applyPageBackground(_ color: NSColor) {
        backgroundColor = color
    }

    /// Window chrome and native text go light or dark with the page, or follow macOS for `system`.
    /// The page's `prefers-color-scheme` follows the window, so only this lets it follow macOS.
    func applyThemeMode(_ mode: ThemeMode) {
        appearance = mode.windowAppearance
    }

    /// Before the page loads: the look its last run left, so the window does not flash another one.
    func applyStoredLook(from store: PageLookStore) {
        let background = store.loadBackground()
        let look = WindowLook.atLaunch(
            reported: store.loadThemeMode(),
            storedBackgroundIsDark: background?.isDarkBackground,
            systemIsDark: NSApp.effectiveAppearance.isDark
        )
        applyThemeMode(look.mode)
        if look.usesStoredBackground, let background { applyPageBackground(background) }
    }
}

extension ThemeMode {
    var windowAppearance: NSAppearance? {
        switch self {
        case .light: NSAppearance(named: .aqua)
        case .dark: NSAppearance(named: .darkAqua)
        case .system: nil
        }
    }
}

extension NSAppearance {
    var isDark: Bool {
        bestMatch(from: [.aqua, .darkAqua]) == .darkAqua
    }
}

extension NSColor {
    var isDarkBackground: Bool {
        (usingColorSpace(.sRGB)?.brightnessComponent ?? 0) < 0.5
    }
}
