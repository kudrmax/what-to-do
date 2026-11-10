import AppKit

enum MainMenu {
    static func build(appName: String) -> NSMenu {
        let menu = NSMenu()
        menu.addItem(submenu(appName, [
            item("О программе «\(appName)»", #selector(NSApplication.orderFrontStandardAboutPanel(_:))),
            .separator(),
            item("Настройки…", #selector(AppDelegate.openSettings(_:)), ","),
            item("Проверить обновления…", #selector(AppDelegate.checkForUpdates(_:))),
            .separator(),
            item("Скрыть «\(appName)»", #selector(NSApplication.hide(_:)), "h"),
            item("Скрыть остальные", #selector(NSApplication.hideOtherApplications(_:)), "h", [.command, .option]),
            item("Показать все", #selector(NSApplication.unhideAllApplications(_:))),
            .separator(),
            item("Завершить «\(appName)»", #selector(NSApplication.terminate(_:)), "q"),
        ]))
        menu.addItem(submenu("Правка", [
            item("Отменить", Selector(("undo:")), "z"),
            item("Повторить", Selector(("redo:")), "z", [.command, .shift]),
            .separator(),
            item("Вырезать", #selector(NSText.cut(_:)), "x"),
            item("Скопировать", #selector(NSText.copy(_:)), "c"),
            item("Вставить", #selector(NSText.paste(_:)), "v"),
            item("Выбрать все", #selector(NSText.selectAll(_:)), "a"),
        ]))
        menu.addItem(submenu("Вид", [
            item("Перезагрузить", #selector(AppDelegate.reloadPage(_:)), "r"),
            .separator(),
            item("Реальный размер", #selector(AppDelegate.resetZoom(_:)), "0"),
            item("Увеличить", #selector(AppDelegate.zoomIn(_:)), "="),
            item("Уменьшить", #selector(AppDelegate.zoomOut(_:)), "-"),
            .separator(),
            item("Перейти в полноэкранный режим", #selector(NSWindow.toggleFullScreen(_:)), "f", [.command, .control]),
        ]))
        let window = submenu("Окно", [
            item("Свернуть", #selector(NSWindow.performMiniaturize(_:)), "m"),
            item("Изменить масштаб", #selector(NSWindow.performZoom(_:))),
            item("Закрыть", #selector(NSWindow.performClose(_:)), "w"),
        ])
        NSApp.windowsMenu = window.submenu
        menu.addItem(window)
        return menu
    }

    private static func submenu(_ title: String, _ items: [NSMenuItem]) -> NSMenuItem {
        let holder = NSMenuItem()
        let submenu = NSMenu(title: title)
        items.forEach(submenu.addItem)
        holder.submenu = submenu
        return holder
    }

    private static func item(
        _ title: String,
        _ action: Selector,
        _ key: String = "",
        _ modifiers: NSEvent.ModifierFlags = .command
    ) -> NSMenuItem {
        let item = NSMenuItem(title: title, action: action, keyEquivalent: key)
        item.keyEquivalentModifierMask = modifiers
        return item
    }
}
