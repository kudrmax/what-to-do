import AppKit
import LauncherCore

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    /// Passed to the instance started by Restart: it takes over stopping the servers on quit.
    private static let adoptServersArgument = "--adopt-servers"

    private var launcher: ServerLauncher?
    private var windowController: MainWindowController?
    private var statusBar: StatusBarController?
    private var isTerminating = false
    private var handsServersOver = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        let config: AppConfig
        do {
            config = try AppConfig(infoDictionary: Bundle.main.infoDictionary ?? [:])
        } catch {
            showFatalError(error)
            return
        }

        let appName = ProcessInfo.processInfo.processName
        NSApp.mainMenu = MainMenu.build(appName: appName)
        launcher = ServerLauncher(
            projectDir: config.projectDir,
            probe: HTTPHealthProbe(url: config.serverURL),
            runner: LoginShellRunner(),
            sleeper: TaskSleeper(),
            policy: .standard,
            adoptRunningServers: CommandLine.arguments.contains(Self.adoptServersArgument)
        )
        let controller = MainWindowController(config: config)
        controller.onRetry = { [weak self] in self?.launch() }
        controller.onPageLoaded = { [weak self] in self?.checkBundleFreshness() }
        controller.onRestart = { [weak self] in self?.restart() }
        if config.showsMenuBarIcon {
            statusBar = StatusBarController(appName: appName, target: self)
            controller.onClose = { NSApp.setActivationPolicy(.accessory) }
        }
        windowController = controller
        openMainWindow(nil)
        launch()
    }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        guard let launcher, !handsServersOver else { return .terminateNow }
        if isTerminating { return .terminateLater }
        isTerminating = true
        windowController?.showStatus(.stopping)
        Task {
            await launcher.stop()
            NSApp.reply(toApplicationShouldTerminate: true)
        }
        return .terminateLater
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        if !flag { openMainWindow(nil) }
        return true
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }

    /// With the menu bar icon, closing the window takes the app out of the Dock; opening it brings the app back.
    @objc func openMainWindow(_ sender: Any?) {
        NSApp.setActivationPolicy(.regular)
        windowController?.showWindow(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    @objc func openSettings(_ sender: Any?) {
        openMainWindow(nil)
        windowController?.openSettings()
    }

    @objc func checkForUpdates(_ sender: Any?) {
        openMainWindow(nil)
        windowController?.checkForUpdates()
    }

    @objc func reloadPage(_ sender: Any?) {
        windowController?.reload()
    }

    @objc func zoomIn(_ sender: Any?) {
        windowController?.zoom(.zoomIn)
    }

    @objc func zoomOut(_ sender: Any?) {
        windowController?.zoom(.zoomOut)
    }

    @objc func resetZoom(_ sender: Any?) {
        windowController?.zoom(.reset)
    }

    private func launch() {
        guard let launcher, let windowController, !isTerminating else { return }
        windowController.showStatus(.starting)
        Task {
            let outcome = await launcher.start()
            guard !isTerminating else { return }
            switch outcome {
            case .ready:
                windowController.showApp()
            case let .failed(message, outputTail):
                windowController.showStatus(.failed(message: message, details: outputTail))
            }
        }
    }

    /// The page reloads once the servers come back from `scripts/update.sh`, so every load is a chance to notice a rebuilt app.
    private func checkBundleFreshness() {
        guard BundleFreshness.isStale(running: .main, installedAt: Bundle.main.bundleURL) else { return }
        windowController?.showRestartBanner()
    }

    /// The servers already run the new version, so this instance quits without `make down`
    /// and the new one takes over stopping them if this one would have.
    private func restart() {
        guard let launcher, !isTerminating else { return }
        Task {
            let configuration = NSWorkspace.OpenConfiguration()
            configuration.createsNewApplicationInstance = true
            configuration.arguments = await launcher.ownsServers ? [Self.adoptServersArgument] : []
            do {
                _ = try await NSWorkspace.shared.openApplication(at: Bundle.main.bundleURL, configuration: configuration)
            } catch {
                showRestartError(error)
                return
            }
            handsServersOver = true
            NSApp.terminate(nil)
        }
    }

    private func showRestartError(_ error: Error) {
        let alert = NSAlert()
        alert.messageText = "Не получилось перезапустить"
        alert.informativeText = error.localizedDescription
        alert.runModal()
    }

    private func showFatalError(_ error: Error) {
        let alert = NSAlert()
        alert.messageText = "Приложение собрано с ошибкой"
        alert.informativeText = "\(error)\n\nПересоберите его командой `make app` в папке проекта."
        alert.runModal()
        NSApp.terminate(nil)
    }
}
