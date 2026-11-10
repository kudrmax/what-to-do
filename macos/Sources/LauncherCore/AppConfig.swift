import Foundation

public struct AppConfigError: Error, CustomStringConvertible {
    public let description: String
}

/// Which working copy this app bundle runs, as written into Info.plist by `make app`.
public struct AppConfig: Sendable {
    public static let projectDirKey = "WTGProjectDir"
    public static let portKey = "WTGPort"
    public static let menuBarIconKey = "WTGMenuBarIcon"

    public let projectDir: URL
    public let serverURL: URL
    /// The app lives in the menu bar and leaves the Dock when its window is closed.
    public let showsMenuBarIcon: Bool

    public init(infoDictionary: [String: Any]) throws {
        guard let dir = infoDictionary[Self.projectDirKey] as? String, !dir.isEmpty else {
            throw AppConfigError(description: "\(Self.projectDirKey) is missing in Info.plist")
        }
        guard let rawPort = infoDictionary[Self.portKey] as? String, let port = Int(rawPort) else {
            throw AppConfigError(description: "\(Self.portKey) in Info.plist is not a port number")
        }
        projectDir = URL(fileURLWithPath: dir, isDirectory: true)
        serverURL = URL(string: "http://localhost:\(port)/")!
        showsMenuBarIcon = infoDictionary[Self.menuBarIconKey] as? Bool ?? false
    }

    public func isAppURL(_ url: URL) -> Bool {
        url.scheme == serverURL.scheme && url.host == serverURL.host && url.port == serverURL.port
    }
}
