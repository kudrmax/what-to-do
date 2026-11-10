import AppKit
import WebKit

/// Remembers the last press, because the page's top bar asks for a window drag only after its own mousedown,
/// and `performDrag` needs the press it starts from.
final class AppWebView: WKWebView {
    private(set) var lastMouseDown: NSEvent?

    override func mouseDown(with event: NSEvent) {
        lastMouseDown = event
        super.mouseDown(with: event)
    }
}
