import Foundation

public struct LaunchPolicy: Sendable {
    public let pollInterval: Duration
    public let attempts: Int
    public let outputTailLines: Int

    public init(pollInterval: Duration, attempts: Int, outputTailLines: Int) {
        self.pollInterval = pollInterval
        self.attempts = attempts
        self.outputTailLines = outputTailLines
    }

    public static let standard = LaunchPolicy(pollInterval: .milliseconds(500), attempts: 240, outputTailLines: 40)
}

public enum LaunchOutcome: Equatable, Sendable {
    case ready
    case failed(message: String, outputTail: String)
}

/// Brings the local server up through the copy's command line, and always takes it down on exit, whoever
/// started it: a server left behind keeps a refresh running and Claude reading after the app is gone.
///
/// Starts are single-flight, and stopping waits for an in-flight `up`: killing it midway
/// would leave whatever it already spawned running with nobody to stop it.
public actor ServerLauncher {
    private static let ansiEscape = "\u{1B}\\[[0-9;?]*[A-Za-z]"

    private let projectDir: URL
    private let commands: ServerCommands
    private let probe: HealthProbe
    private let runner: CommandRunner
    private let sleeper: Sleeper
    private let policy: LaunchPolicy
    private var inFlightStart: Task<LaunchOutcome, Never>?
    private var inFlightStop: Task<Void, Never>?

    public init(
        projectDir: URL,
        commands: ServerCommands,
        probe: HealthProbe,
        runner: CommandRunner,
        sleeper: Sleeper,
        policy: LaunchPolicy
    ) {
        self.projectDir = projectDir
        self.commands = commands
        self.probe = probe
        self.runner = runner
        self.sleeper = sleeper
        self.policy = policy
    }

    public func start() async -> LaunchOutcome {
        if inFlightStop != nil { return .failed(message: "The app is quitting", outputTail: "") }
        if let inFlightStart { return await inFlightStart.value }
        let task = Task { await performStart() }
        inFlightStart = task
        let outcome = await task.value
        inFlightStart = nil
        return outcome
    }

    public func stop() async {
        if let inFlightStop { return await inFlightStop.value }
        let task = Task { await performStop() }
        inFlightStop = task
        await task.value
    }

    private func performStart() async -> LaunchOutcome {
        if await probe.isUp() { return .ready }

        let result = await runner.run(commands.up, in: projectDir)
        guard result.exitCode == 0 else {
            return .failed(message: "The server didn’t start (exit code \(result.exitCode))", outputTail: tail(of: result.output))
        }

        for _ in 0..<policy.attempts where inFlightStop == nil {
            if await probe.isUp() { return .ready }
            await sleeper.sleep(for: policy.pollInterval)
        }
        return .failed(message: "The server started but isn’t responding", outputTail: tail(of: result.output))
    }

    private func performStop() async {
        _ = await inFlightStart?.value
        _ = await runner.run(commands.down, in: projectDir)
    }

    private func tail(of output: String) -> String {
        output
            .replacingOccurrences(of: Self.ansiEscape, with: "", options: .regularExpression)
            .split(separator: "\n", omittingEmptySubsequences: false)
            .suffix(policy.outputTailLines)
            .joined(separator: "\n")
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }
}
