import Foundation

/// The copy's own command line, by its full path, so the app needs neither `make` nor the copy's folder
/// on PATH. It still runs in a login shell: building the interface needs Node.js from the user's PATH.
public struct ServerCommands: Sendable, Equatable {
    public let up: String
    public let down: String

    public init(projectDir: URL, port: Int) {
        let cli = Self.quoted(projectDir.appending(path: ".venv/bin/where-to-go").path)
        up = "\(cli) up --port \(port)"
        down = "\(cli) down"
    }

    static func quoted(_ text: String) -> String {
        "'" + text.replacingOccurrences(of: "'", with: "'\\''") + "'"
    }
}
