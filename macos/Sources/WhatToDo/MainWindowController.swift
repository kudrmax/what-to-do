import AppKit
import LauncherCore

final class MainWindowController: NSWindowController, NSWindowDelegate {
    private static let frameName = "MainWindow"
    private static let defaultSize = NSSize(width: 1440, height: 900)
    private static let minimumSize = NSSize(width: 900, height: 600)

    var onRetry: (() -> Void)?
    var onClose: (() -> Void)?
    var onPageLoaded: (() -> Void)?
    var onRestart: (() -> Void)?

    private let webController: WebViewController
    private let statusController = StatusViewController()
    private let lookStore = PageLookStore()
    private var restartBanner: RestartBanner?
    private var status: LaunchStatus?
    private var backgroundObservation: NSKeyValueObservation?
    private let titlebarHeight: CGFloat

    init(config: AppConfig) {
        webController = WebViewController(config: config)
        let window = NSWindow(
            contentRect: NSRect(origin: .zero, size: Self.defaultSize),
            styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView],
            backing: .buffered,
            defer: false
        )
        window.title = ProcessInfo.processInfo.processName
        window.titleVisibility = .hidden
        window.titlebarAppearsTransparent = true
        // The page's top bar takes the title bar's place: an empty unified toolbar makes the title bar
        // as tall as that bar and centres the window controls on it.
        window.toolbar = NSToolbar()
        window.toolbarStyle = .unified
        window.titlebarSeparatorStyle = .none
        titlebarHeight = window.frame.height - window.contentLayoutRect.height
        window.isReleasedWhenClosed = false
        window.minSize = Self.minimumSize
        window.center()
        super.init(window: window)
        // Set on the controller: NSWindowController clears an autosave name set on the window itself.
        windowFrameAutosaveName = Self.frameName
        window.delegate = self

        statusController.onRetry = { [weak self] in self?.onRetry?() }
        webController.onPageLoaded = { [weak self] in self?.onPageLoaded?() }
        webController.onLoadFailed = { [weak self] message in
            self?.showStatus(.failed(message: "Страница не загрузилась", details: message))
        }
        window.applyStoredLook(from: lookStore)
        webController.observeTheme { [weak window, lookStore] mode in
            window?.applyThemeMode(mode)
            lookStore.saveThemeMode(mode)
        }
        backgroundObservation = webController.observeBackground { [weak window, lookStore] color in
            window?.applyPageBackground(color)
            lookStore.saveBackground(color)
        }
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) { fatalError("init(coder:) is not supported") }

    func windowWillClose(_ notification: Notification) {
        onClose?()
    }

    /// Full screen slides the title bar in as an opaque bar over the top of the window, so there
    /// the page goes back under it, and the bar pushes the page down instead of covering its top bar.
    func windowWillEnterFullScreen(_ notification: Notification) {
        setPageUnderTitlebar(false)
    }

    func windowDidExitFullScreen(_ notification: Notification) {
        setPageUnderTitlebar(true)
    }

    func windowDidFailToEnterFullScreen(_ window: NSWindow) {
        setPageUnderTitlebar(true)
    }

    private func setPageUnderTitlebar(_ under: Bool) {
        guard let window else { return }
        if under { window.styleMask.insert(.fullSizeContentView) } else { window.styleMask.remove(.fullSizeContentView) }
        window.toolbar?.isVisible = under
        updateTitlebarInsets()
    }

    func showStatus(_ status: LaunchStatus) {
        self.status = status
        statusController.show(status)
        setContent(statusController)
    }

    func showApp() {
        status = nil
        updateTitlebarInsets()
        webController.loadApp()
        setContent(webController)
    }

    /// Cmd+R: reloads the page, retries a failed start, and does nothing while starting or stopping.
    func reload() {
        switch status {
        case nil: webController.reload()
        case .failed: onRetry?()
        case .starting, .stopping: break
        }
    }

    func zoom(_ step: PageZoom.Step) {
        webController.zoom(step)
    }

    /// Cmd+,: opens the page's settings once the app is shown; the status screen has none.
    func openSettings() {
        guard status == nil else { return }
        webController.openSettings()
    }

    /// The page's own Check for updates; the status screen has none.
    func checkForUpdates() {
        guard status == nil else { return }
        webController.checkForUpdates()
    }

    func showRestartBanner() {
        guard let window, restartBanner == nil else { return }
        let banner = RestartBanner()
        banner.onRestart = { [weak self] in self?.onRestart?() }
        window.addTitlebarAccessoryViewController(banner)
        restartBanner = banner
        updateTitlebarInsets()
    }

    private func updateTitlebarInsets() {
        guard let window else { return }
        guard window.styleMask.contains(.fullSizeContentView) else {
            return webController.setTitlebarInsets(TitlebarInsets(height: titlebarHeight, leading: 0, trailing: 0))
        }
        window.layoutIfNeeded()
        let controls = [NSWindow.ButtonType.closeButton, .zoomButton]
            .compactMap { window.standardWindowButton($0) }
            .map { $0.convert($0.bounds, to: nil) }
        // The controls get as much room after them as they have before them.
        let leading = controls.count == 2 ? controls[1].maxX + controls[0].minX : 0
        webController.setTitlebarInsets(TitlebarInsets(
            height: titlebarHeight,
            leading: leading,
            trailing: restartBanner.map { $0.view.frame.width } ?? 0
        ))
    }

    private func setContent(_ controller: NSViewController) {
        guard let window, window.contentViewController !== controller else { return }
        let frame = window.frame
        window.contentViewController = controller
        window.setFrame(frame, display: true)
    }
}
