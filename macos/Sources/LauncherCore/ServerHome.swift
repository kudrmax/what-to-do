import Foundation

/// Where the server's code lives and how the window reaches its command line.
public enum ServerHome: Sendable, Equatable {
    /// A git copy built with `make app`: its own `.venv/bin/where-to-go`.
    case project(URL)
    /// The app installed from the disk image: Python and the packages are inside the bundle, and the copy
    /// writes its records and logs into its state folder.
    case bundle(python: URL, state: URL)

    public static let stateDirVariable = "WHERE_TO_GO_STATE_DIR"
    static let stateDirName = "What To Do"
    static let pythonPath = "Contents/Resources/python/bin/python3"

    public static func bundle(at bundleURL: URL, environment: [String: String], home: URL) -> ServerHome {
        let state: URL
        if let named = environment[stateDirVariable], !named.trimmingCharacters(in: .whitespaces).isEmpty {
            state = URL(fileURLWithPath: (named as NSString).expandingTildeInPath, isDirectory: true)
        } else {
            state = home.appending(path: "Library/Application Support/\(stateDirName)", directoryHint: .isDirectory)
        }
        return .bundle(python: bundleURL.appending(path: pythonPath), state: state)
    }

    public var workingDirectory: URL {
        switch self {
        case let .project(dir): dir
        case let .bundle(_, state): state
        }
    }

    /// The bundled Python must see only its own packages: a PYTHONHOME or PYTHONPATH from the user's
    /// shell, or packages in the user's site folder, would mix another Python in. It must not write
    /// bytecode into the bundle either: that would break the bundle's signature.
    public func environment(from base: [String: String]) -> [String: String] {
        guard case .bundle = self else { return base }
        var environment = base.filter { !["PYTHONHOME", "PYTHONPATH", "PYTHONSTARTUP", "VIRTUAL_ENV", "PYTHONEXECUTABLE"].contains($0.key) }
        environment["PYTHONNOUSERSITE"] = "1"
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        return environment
    }
}
