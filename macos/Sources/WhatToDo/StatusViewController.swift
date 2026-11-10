import AppKit

enum LaunchStatus {
    case starting
    case stopping
    case failed(message: String, details: String)
}

/// What the window shows while the server is not serving the app: progress, or an error with a retry.
final class StatusViewController: NSViewController {
    private static let spacing: CGFloat = 16
    private static let detailsSize = NSSize(width: 640, height: 240)

    var onRetry: (() -> Void)?

    private let spinner = NSProgressIndicator()
    private let titleLabel = NSTextField(labelWithString: "")
    private let messageLabel = NSTextField(wrappingLabelWithString: "")
    private let detailsView = NSTextView()
    private lazy var detailsScroll = NSScrollView()
    private lazy var retryButton = NSButton(title: "Повторить", target: self, action: #selector(retry))

    override func loadView() {
        spinner.style = .spinning
        titleLabel.font = .preferredFont(forTextStyle: .title2)
        messageLabel.textColor = .secondaryLabelColor
        messageLabel.alignment = .center
        detailsView.isEditable = false
        detailsView.font = .monospacedSystemFont(ofSize: NSFont.smallSystemFontSize, weight: .regular)
        detailsView.textColor = .secondaryLabelColor
        detailsView.drawsBackground = false
        detailsScroll.documentView = detailsView
        detailsScroll.hasVerticalScroller = true
        detailsScroll.drawsBackground = false
        detailsScroll.borderType = .noBorder
        detailsScroll.translatesAutoresizingMaskIntoConstraints = false
        detailsScroll.widthAnchor.constraint(equalToConstant: Self.detailsSize.width).isActive = true
        detailsScroll.heightAnchor.constraint(equalToConstant: Self.detailsSize.height).isActive = true
        detailsView.autoresizingMask = [.width]
        retryButton.keyEquivalent = "\r"

        let stack = NSStackView(views: [spinner, titleLabel, messageLabel, detailsScroll, retryButton])
        stack.orientation = .vertical
        stack.alignment = .centerX
        stack.spacing = Self.spacing
        stack.translatesAutoresizingMaskIntoConstraints = false

        let root = NSView()
        root.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.centerXAnchor.constraint(equalTo: root.centerXAnchor),
            stack.centerYAnchor.constraint(equalTo: root.centerYAnchor),
            stack.leadingAnchor.constraint(greaterThanOrEqualTo: root.leadingAnchor, constant: Self.spacing),
        ])
        view = root
    }

    func show(_ status: LaunchStatus) {
        loadViewIfNeeded()
        switch status {
        case .starting:
            render(title: "Запускается…", message: "", details: nil, spinning: true)
        case .stopping:
            render(title: "Останавливается…", message: "", details: nil, spinning: true)
        case let .failed(message, details):
            render(title: "Не получилось запустить", message: message, details: details, spinning: false)
        }
    }

    private func render(title: String, message: String, details: String?, spinning: Bool) {
        titleLabel.stringValue = title
        messageLabel.stringValue = message
        messageLabel.isHidden = message.isEmpty
        detailsView.string = details ?? ""
        detailsScroll.isHidden = (details ?? "").isEmpty
        retryButton.isHidden = spinning
        spinner.isHidden = !spinning
        spinning ? spinner.startAnimation(nil) : spinner.stopAnimation(nil)
    }

    @objc private func retry() { onRetry?() }
}
