import Foundation

/// Runs a command in zsh. A login shell gives an app opened from the Dock the same PATH as Terminal;
/// a plain one with a given environment keeps the user's shell setup out.
public struct ShellRunner: CommandRunner {
    private static let shell = URL(fileURLWithPath: "/bin/zsh")

    private let login: Bool
    private let environment: [String: String]?

    public static let login = ShellRunner(login: true, environment: nil)

    public static func plain(environment: [String: String]) -> ShellRunner {
        ShellRunner(login: false, environment: environment)
    }

    private init(login: Bool, environment: [String: String]?) {
        self.login = login
        self.environment = environment
    }

    public func run(_ command: String, in directory: URL) async -> CommandResult {
        // Output goes to a file, not a pipe: background children keep inherited descriptors open,
        // and reading a pipe to EOF would wait for them.
        let logURL = FileManager.default.temporaryDirectory.appendingPathComponent("wtg-\(UUID().uuidString).log")
        FileManager.default.createFile(atPath: logURL.path, contents: nil)
        defer { try? FileManager.default.removeItem(at: logURL) }

        do {
            let log = try FileHandle(forWritingTo: logURL)
            defer { try? log.close() }
            let exitCode = try await launch(command, in: directory, output: log)
            let output = String(decoding: (try? Data(contentsOf: logURL)) ?? Data(), as: UTF8.self)
            return CommandResult(exitCode: exitCode, output: output)
        } catch {
            return CommandResult(exitCode: -1, output: "Could not run `\(command)`: \(error.localizedDescription)")
        }
    }

    private func launch(_ command: String, in directory: URL, output: FileHandle) async throws -> Int32 {
        let process = Process()
        process.executableURL = Self.shell
        process.arguments = login ? ["-lc", command] : ["-f", "-c", command]
        if let environment { process.environment = environment }
        process.currentDirectoryURL = directory
        process.standardInput = FileHandle.nullDevice
        process.standardOutput = output
        process.standardError = output

        return try await withCheckedThrowingContinuation { continuation in
            process.terminationHandler = { continuation.resume(returning: $0.terminationStatus) }
            do {
                try process.run()
            } catch {
                process.terminationHandler = nil
                continuation.resume(throwing: error)
            }
        }
    }
}
