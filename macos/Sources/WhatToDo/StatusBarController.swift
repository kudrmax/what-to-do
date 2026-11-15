import AppKit

/// The menu bar icon that keeps the app reachable while its window is closed and it is out of the Dock.
@MainActor
final class StatusBarController {
    private let statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)

    init(appName: String, target: AppDelegate) {
        if let button = statusItem.button {
            button.image = MenuBarIcon.make(accessibilityDescription: appName)
            button.toolTip = appName
        }
        let menu = NSMenu()
        let open = NSMenuItem(title: "Open \(appName)", action: #selector(AppDelegate.openMainWindow(_:)), keyEquivalent: "")
        open.target = target
        let quit = NSMenuItem(title: "Quit \(appName)", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "")
        quit.target = NSApp
        menu.addItem(open)
        menu.addItem(.separator())
        menu.addItem(quit)
        statusItem.menu = menu
    }
}
