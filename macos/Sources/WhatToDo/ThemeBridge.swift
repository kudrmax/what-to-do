import LauncherCore
import WebKit

/// Answers `window.webkit.messageHandlers.theme.postMessage("light" | "dark" | "system")`:
/// the page's theme setting, which the window's appearance follows.
final class ThemeBridge: NSObject, WKScriptMessageHandler {
    static let name = "theme"

    var onChange: ((ThemeMode) -> Void)?

    private let isAppFrame: (WKFrameInfo) -> Bool

    init(isAppFrame: @escaping (WKFrameInfo) -> Bool) {
        self.isAppFrame = isAppFrame
    }

    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        guard isAppFrame(message.frameInfo),
              let mode = (message.body as? String).flatMap(ThemeMode.init)
        else { return }
        onChange?(mode)
    }
}
