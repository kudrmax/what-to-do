import Foundation

/// Page zoom for Cmd+= / Cmd+- / Cmd+0, remembered between launches.
final class PageZoom {
    enum Step {
        case zoomIn, zoomOut, reset
    }

    private static let key = "PageZoom"
    private static let levels: [Double] = [0.67, 0.75, 0.8, 0.9, 1.0, 1.1, 1.25, 1.5, 1.75, 2.0]
    private static let defaultLevel = 1.0

    private let defaults: UserDefaults
    private(set) var current: Double

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        let stored = defaults.double(forKey: Self.key)
        current = stored > 0 ? stored : Self.defaultLevel
    }

    func apply(_ step: Step) -> Double {
        switch step {
        case .zoomIn: current = Self.levels.first { $0 > current } ?? current
        case .zoomOut: current = Self.levels.last { $0 < current } ?? current
        case .reset: current = Self.defaultLevel
        }
        defaults.set(current, forKey: Self.key)
        return current
    }
}
