import Foundation

/// Asks the app's own command line which port to start on. It keeps the port the copy ran on, and moves to a
/// free one when another program holds it, so the window never loads someone else's server.
public struct PortChooser: Sendable {
    private let command: String
    private let workingDirectory: URL
    private let runner: CommandRunner

    public init(command: String, workingDirectory: URL, runner: CommandRunner) {
        self.command = command
        self.workingDirectory = workingDirectory
        self.runner = runner
    }

    /// The fallback stands when the command fails: starting then fails with the reason shown in the window.
    public func port(fallback: Int) async -> Int {
        let result = await runner.run(command, in: workingDirectory)
        guard result.exitCode == 0 else { return fallback }
        return Self.lastPort(in: result.output) ?? fallback
    }

    /// The command prints the port alone on its last line; notes about a move come before it.
    static func lastPort(in output: String) -> Int? {
        output
            .split(whereSeparator: \.isNewline)
            .reversed()
            .lazy
            .compactMap { Int($0.trimmingCharacters(in: .whitespaces)) }
            .first { (1...65535).contains($0) }
    }
}
