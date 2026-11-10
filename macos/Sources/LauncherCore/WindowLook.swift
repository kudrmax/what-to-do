import Foundation

/// The page's theme setting, as it reports it with `window.webkit.messageHandlers.theme.postMessage(mode)`.
/// WebKit answers the page's `prefers-color-scheme` from the window's appearance, not from macOS,
/// so a window set light or dark by hand would lock the page in that scheme. The window follows
/// the setting instead: it is light or dark with the page, or inherits from macOS for `system`.
public enum ThemeMode: String, Sendable {
    case light
    case dark
    case system
}

/// How a window looks before its page has loaded and reported its theme.
public struct WindowLook: Equatable {
    public let mode: ThemeMode
    /// The page's last background makes the status screen open in the app's colours; it is skipped
    /// when it would clash with the appearance the window starts in.
    public let usesStoredBackground: Bool

    public static func atLaunch(reported: ThemeMode?, storedBackgroundIsDark: Bool?, systemIsDark: Bool) -> WindowLook {
        switch reported {
        case .system:
            return WindowLook(mode: .system, usesStoredBackground: storedBackgroundIsDark == systemIsDark)
        case let mode?:
            return WindowLook(mode: mode, usesStoredBackground: storedBackgroundIsDark != nil)
        case nil:
            // Installed before the page reported its theme: the background's darkness is all there is.
            guard let storedBackgroundIsDark else { return WindowLook(mode: .system, usesStoredBackground: false) }
            return WindowLook(mode: storedBackgroundIsDark ? .dark : .light, usesStoredBackground: true)
        }
    }
}
