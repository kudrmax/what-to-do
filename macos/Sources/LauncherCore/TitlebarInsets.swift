import Foundation

/// Where the window's own controls sit over the page, which runs under the transparent title bar,
/// so the page lays its top bar out around them. In points.
public struct TitlebarInsets: Equatable {
    public static let heightProperty = "--shell-titlebar-h"
    public static let leadingProperty = "--shell-inset-start"
    public static let trailingProperty = "--shell-inset-end"

    public let height: Double
    public let leading: Double
    public let trailing: Double

    public init(height: Double, leading: Double, trailing: Double) {
        self.height = height
        self.leading = leading
        self.trailing = trailing
    }

    /// Sets the insets as CSS custom properties on the page's root element.
    /// The page zoom scales every CSS pixel, so points are divided by it.
    public func styleScript(pageZoom: Double) -> String {
        let properties = [
            Self.heightProperty: height,
            Self.leadingProperty: leading,
            Self.trailingProperty: trailing,
        ].mapValues { "\($0 / pageZoom)px" }
        let data = try! JSONSerialization.data(withJSONObject: properties, options: [.sortedKeys])
        let json = String(decoding: data, as: UTF8.self)
        return "for (const [name, value] of Object.entries(\(json))) document.documentElement.style.setProperty(name, value)"
    }
}

/// What the page's top bar asks of the window in place of the title bar it covers.
public enum TitlebarAction: String {
    case drag
    case doubleClick
}

/// What a double click on the title bar does, as chosen in System Settings › Desktop & Dock.
public enum TitlebarDoubleClick: Equatable {
    case zoom
    case minimize
    case none

    public static let preferenceKey = "AppleActionOnDoubleClick"

    public init(preference: String?) {
        switch preference {
        case "Minimize": self = .minimize
        case "None": self = .none
        default: self = .zoom
        }
    }
}
