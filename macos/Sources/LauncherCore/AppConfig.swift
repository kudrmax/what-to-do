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
    /// The server listens only on 127.0.0.1. `localhost` may resolve to ::1 first, where any
    /// other program can listen on the same port and answer instead of the app.
    public let serverURL: URL
    /// Answers only the app itself, so a stranger on the port is not taken for it.
    public var versionURL: URL { serverURL.appending(path: "api/version") }
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
        serverURL = URL(string: "http://127.0.0.1:\(port)/")!
        showsMenuBarIcon = infoDictionary[Self.menuBarIconKey] as? Bool ?? false
    }

    public func isAppURL(_ url: URL) -> Bool {
        url.scheme == serverURL.scheme && url.host == serverURL.host && url.port == serverURL.port
    }
}
