import AppKit
import LauncherCore
import WebKit

/// Answers `window.webkit.messageHandlers.titlebar.postMessage("drag" | "doubleClick")`:
/// the page's top bar covers the title bar, so it moves and zooms the window in its place.
final class TitlebarBridge: NSObject, WKScriptMessageHandler {
    static let name = "titlebar"

    private weak var window: NSWindow?
    private let isAppFrame: (WKFrameInfo) -> Bool
    private let lastMouseDown: () -> NSEvent?

    init(isAppFrame: @escaping (WKFrameInfo) -> Bool, lastMouseDown: @escaping () -> NSEvent?) {
        self.isAppFrame = isAppFrame
        self.lastMouseDown = lastMouseDown
    }

    func attach(to window: NSWindow?) {
        self.window = window
    }

    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        guard isAppFrame(message.frameInfo),
              let window,
              let action = (message.body as? String).flatMap(TitlebarAction.init)
        else { return }
        switch action {
        case .drag: drag(window)
        case .doubleClick: doubleClick(window)
        }
    }

    /// The page asks after its own mousedown, so the button may already be up after a quick click.
    private func drag(_ window: NSWindow) {
        let leftButton = 1
        guard NSEvent.pressedMouseButtons & leftButton != 0, let event = lastMouseDown() else { return }
        window.performDrag(with: event)
    }

    private func doubleClick(_ window: NSWindow) {
        switch TitlebarDoubleClick(preference: UserDefaults.standard.string(forKey: TitlebarDoubleClick.preferenceKey)) {
        case .zoom: window.zoom(nil)
        case .minimize: window.miniaturize(nil)
        case .none: break
        }
    }
}
