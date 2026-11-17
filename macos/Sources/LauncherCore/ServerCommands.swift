import Foundation

/// The copy's own command line, by its full path, so the app needs neither `make` nor the copy's folder
/// on PATH. A git copy's runs in a login shell: building the interface needs Node.js from the user's PATH.
/// The bundled one needs nothing from the user's shell.
public struct ServerCommands: Sendable, Equatable {
    public let up: String
    public let down: String
    /// Prints the port the copy starts on, moving off one another program holds.
    public let port: String

    public init(home: ServerHome, port: Int) {
        let cli: String
        switch home {
        case let .project(dir):
            cli = Self.quoted(dir.appending(path: ".venv/bin/where-to-go").path)
        case let .bundle(python, _):
            cli = "\(Self.quoted(python.path)) -m where_to_go"
        }
        up = "\(cli) up --port \(port)"
        down = "\(cli) down"
        self.port = "\(cli) port"
    }

    static func quoted(_ text: String) -> String {
        "'" + text.replacingOccurrences(of: "'", with: "'\\''") + "'"
    }
}
