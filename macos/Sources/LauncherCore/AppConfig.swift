import Foundation

public struct AppConfigError: Error, CustomStringConvertible {
    public let description: String
}

/// Which server this app bundle runs, as its Info.plist says: a git copy's, written there by `make app`,
/// or its own, for the app installed from the disk image.
public struct AppConfig: Sendable {
    public static let projectDirKey = "WTGProjectDir"
    public static let bundledKey = "WTGBundled"
    public static let portKey = "WTGPort"
    public static let menuBarIconKey = "WTGMenuBarIcon"
    public static let portVariable = "WHERE_TO_GO_PORT"

    public let home: ServerHome
    public private(set) var port: Int
    /// The server listens only on 127.0.0.1. `localhost` may resolve to ::1 first, where any
    /// other program can listen on the same port and answer instead of the app.
    public private(set) var serverURL: URL
    /// Answers only the app itself, so a stranger on the port is not taken for it.
    public var versionURL: URL { serverURL.appending(path: "api/version") }
    /// Checked with the server even when WebKit holds a copy it thinks is fresh: an update replaces the page,
    /// and a cached old page would load the old build.
    public var pageRequest: URLRequest { URLRequest(url: serverURL, cachePolicy: .reloadRevalidatingCacheData) }
    /// The app lives in the menu bar and leaves the Dock when its window is closed.
    public let showsMenuBarIcon: Bool

    /// The bundled app takes its port the way its server does: `WHERE_TO_GO_PORT`, then `PORT` in the
    /// `.env` of its state folder, then the default in Info.plist.
    public init(
        infoDictionary: [String: Any],
        bundleURL: URL = Bundle.main.bundleURL,
        environment: [String: String] = ProcessInfo.processInfo.environment,
        home: URL = FileManager.default.homeDirectoryForCurrentUser
    ) throws {
        var portText = infoDictionary[Self.portKey] as? String
        if infoDictionary[Self.bundledKey] as? Bool == true {
            self.home = .bundle(at: bundleURL, environment: environment, home: home)
            let dotenv = DotEnv.read(self.home.workingDirectory.appending(path: ".env"))
            portText = [environment[Self.portVariable], dotenv["PORT"], portText].compactMap { $0 }.first { !$0.isEmpty }
        } else {
            guard let dir = infoDictionary[Self.projectDirKey] as? String, !dir.isEmpty else {
                throw AppConfigError(description: "\(Self.projectDirKey) is missing in Info.plist")
            }
            self.home = .project(URL(fileURLWithPath: dir, isDirectory: true))
        }
        guard let portText, let port = Int(portText), (1...65535).contains(port) else {
            throw AppConfigError(description: "\(Self.portKey) in Info.plist is not a port number")
        }
        self.port = port
        serverURL = URL(string: "http://127.0.0.1:\(port)/")!
        showsMenuBarIcon = infoDictionary[Self.menuBarIconKey] as? Bool ?? false
    }

    /// The same app on another port, once the command line chose one.
    public func with(port: Int) -> AppConfig {
        var copy = self
        copy.port = port
        copy.serverURL = URL(string: "http://127.0.0.1:\(port)/")!
        return copy
    }

    public var isBundled: Bool {
        if case .bundle = home { return true }
        return false
    }

    public func isAppURL(_ url: URL) -> Bool {
        url.scheme == serverURL.scheme && url.host == serverURL.host && url.port == serverURL.port
    }
}
