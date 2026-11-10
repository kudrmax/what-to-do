import AppKit

/// A quiet note in the title bar once `scripts/update.sh` has rebuilt the app on disk.
final class RestartBanner: NSTitlebarAccessoryViewController {
    private static let spacing: CGFloat = 8
    private static let trailingInset: CGFloat = 12

    var onRestart: (() -> Void)?

    override func loadView() {
        let label = NSTextField(labelWithString: "Перезапустите, чтобы завершить обновление")
        label.font = .systemFont(ofSize: NSFont.smallSystemFontSize)
        label.textColor = .secondaryLabelColor
        let button = NSButton(title: "Перезапустить", target: self, action: #selector(restart))
        button.controlSize = .small
        button.font = .systemFont(ofSize: NSFont.smallSystemFontSize)

        let stack = NSStackView(views: [label, button])
        stack.orientation = .horizontal
        stack.spacing = Self.spacing
        stack.edgeInsets = NSEdgeInsets(top: 0, left: 0, bottom: 0, right: Self.trailingInset)
        stack.frame.size = stack.fittingSize
        view = stack
        layoutAttribute = .trailing
    }

    @objc private func restart() { onRestart?() }
}
