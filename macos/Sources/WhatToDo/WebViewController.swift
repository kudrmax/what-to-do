import AppKit
import LauncherCore
import WebKit

final class WebViewController: NSViewController {
    static let openSettingsEvent = "nativeopensettings"
    static let checkForUpdatesEvent = "nativecheckforupdates"

    var onLoadFailed: ((String) -> Void)?
    var onPageLoaded: (() -> Void)?

    private let config: AppConfig
    private lazy var isAppFrame: (WKFrameInfo) -> Bool = { [config] frame in
        frame.isMainFrame && frame.request.url.map(config.isAppURL) == true
    }
    private lazy var titlebar = TitlebarBridge(isAppFrame: isAppFrame, lastMouseDown: { [weak self] in
        self?.webView.lastMouseDown
    })
    private lazy var theme = ThemeBridge(isAppFrame: isAppFrame)
    private lazy var webView: AppWebView = makeWebView()
    private let pageZoom = PageZoom()
    private var titlebarInsets: TitlebarInsets?

    init(config: AppConfig) {
        self.config = config
        super.init(nibName: nil, bundle: nil)
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) { fatalError("init(coder:) is not supported") }

    override func loadView() {
        view = webView
    }

    override func viewDidAppear() {
        super.viewDidAppear()
        titlebar.attach(to: view.window)
    }

    func loadApp() {
        loadViewIfNeeded()
        // After a failed load the old page is still shown, so a retry has to reload it.
        if webView.url.map(config.isAppURL) == true {
            webView.reload()
        } else {
            webView.load(URLRequest(url: config.serverURL))
        }
    }

    func reload() {
        webView.reload()
    }

    func zoom(_ step: PageZoom.Step) {
        webView.pageZoom = pageZoom.apply(step)
        applyTitlebarInsets()
    }

    func setTitlebarInsets(_ insets: TitlebarInsets) {
        guard insets != titlebarInsets else { return }
        titlebarInsets = insets
        applyTitlebarInsets()
    }

    /// Set before the page's own scripts run, so its top bar never renders under the window controls.
    private func applyTitlebarInsets() {
        guard let titlebarInsets else { return }
        loadViewIfNeeded()
        let script = titlebarInsets.styleScript(pageZoom: webView.pageZoom)
        let userContent = webView.configuration.userContentController
        userContent.removeAllUserScripts()
        userContent.addUserScript(WKUserScript(source: script, injectionTime: .atDocumentStart, forMainFrameOnly: true))
        guard webView.url.map(config.isAppURL) == true else { return }
        webView.evaluateJavaScript(script)
    }

    /// The page owns its routes, so the menu only tells it to open settings.
    func openSettings() {
        dispatchPageEvent(Self.openSettingsEvent)
    }

    /// The page checks and shows the result itself, as its own Check for updates button does.
    func checkForUpdates() {
        dispatchPageEvent(Self.checkForUpdatesEvent)
    }

    private func dispatchPageEvent(_ name: String) {
        guard webView.url.map(config.isAppURL) == true else { return }
        webView.callAsyncJavaScript(
            "window.dispatchEvent(new CustomEvent(name))",
            arguments: ["name": name],
            in: nil,
            in: .page
        )
    }

    func observeTheme(_ apply: @escaping (ThemeMode) -> Void) {
        loadViewIfNeeded()
        theme.onChange = apply
    }

    func observeBackground(_ apply: @escaping (NSColor) -> Void) -> NSKeyValueObservation {
        loadViewIfNeeded()
        return webView.observe(\.underPageBackgroundColor, options: [.new]) { webView, _ in
            guard webView.url != nil else { return }
            apply(webView.underPageBackgroundColor)
        }
    }

    private func makeWebView() -> AppWebView {
        let configuration = WKWebViewConfiguration()
        configuration.mediaTypesRequiringUserActionForPlayback = []
        configuration.preferences.isElementFullscreenEnabled = true
        configuration.userContentController.add(titlebar, contentWorld: .page, name: TitlebarBridge.name)
        configuration.userContentController.add(theme, contentWorld: .page, name: ThemeBridge.name)
        let webView = AppWebView(frame: .zero, configuration: configuration)
        webView.navigationDelegate = self
        webView.uiDelegate = self
        webView.allowsBackForwardNavigationGestures = true
        webView.isInspectable = true
        webView.pageZoom = pageZoom.current
        return webView
    }

    private func openExternally(_ url: URL) {
        NSWorkspace.shared.open(url)
    }
}

extension WebViewController: WKNavigationDelegate {
    func webView(
        _ webView: WKWebView,
        decidePolicyFor navigationAction: WKNavigationAction,
        decisionHandler: @escaping (WKNavigationActionPolicy) -> Void
    ) {
        guard let url = navigationAction.request.url,
              navigationAction.targetFrame?.isMainFrame != false,
              !config.isAppURL(url),
              url.scheme != "about", url.scheme != "blob", url.scheme != "data"
        else { return decisionHandler(.allow) }
        openExternally(url)
        decisionHandler(.cancel)
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        onPageLoaded?()
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        guard !Self.isInterruption(error) else { return }
        onLoadFailed?(error.localizedDescription)
    }

    /// A load superseded by another one (double Cmd+R, a click mid-load) is not a failure.
    private static func isInterruption(_ error: Error) -> Bool {
        let error = error as NSError
        let frameLoadInterrupted = 102
        return (error.domain == NSURLErrorDomain && error.code == NSURLErrorCancelled)
            || (error.domain == "WebKitErrorDomain" && error.code == frameLoadInterrupted)
    }

    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
        webView.reload()
    }
}

extension WebViewController: WKUIDelegate {
    func webView(
        _ webView: WKWebView,
        createWebViewWith configuration: WKWebViewConfiguration,
        for navigationAction: WKNavigationAction,
        windowFeatures: WKWindowFeatures
    ) -> WKWebView? {
        if let url = navigationAction.request.url { openExternally(url) }
        return nil
    }

    func webView(
        _ webView: WKWebView,
        runOpenPanelWith parameters: WKOpenPanelParameters,
        initiatedByFrame frame: WKFrameInfo,
        completionHandler: @escaping ([URL]?) -> Void
    ) {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = parameters.allowsMultipleSelection
        panel.canChooseDirectories = parameters.allowsDirectories
        panel.canChooseFiles = true
        guard let window = view.window else { return completionHandler(nil) }
        panel.beginSheetModal(for: window) { response in
            completionHandler(response == .OK ? panel.urls : nil)
        }
    }

    func webView(
        _ webView: WKWebView,
        runJavaScriptAlertPanelWithMessage message: String,
        initiatedByFrame frame: WKFrameInfo,
        completionHandler: @escaping () -> Void
    ) {
        presentAlert(message, buttons: ["OK"]) { _ in completionHandler() }
    }

    func webView(
        _ webView: WKWebView,
        runJavaScriptConfirmPanelWithMessage message: String,
        initiatedByFrame frame: WKFrameInfo,
        completionHandler: @escaping (Bool) -> Void
    ) {
        presentAlert(message, buttons: ["OK", "Отменить"]) { completionHandler($0 == .alertFirstButtonReturn) }
    }

    private func presentAlert(_ message: String, buttons: [String], completion: @escaping (NSApplication.ModalResponse) -> Void) {
        let alert = NSAlert()
        alert.messageText = message
        buttons.forEach { alert.addButton(withTitle: $0) }
        guard let window = view.window else { return completion(alert.runModal()) }
        alert.beginSheetModal(for: window, completionHandler: completion)
    }
}
