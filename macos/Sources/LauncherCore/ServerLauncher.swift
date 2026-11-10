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

/// Brings the local server up through `make`, and takes it down on exit only if it started it
/// or adopted the running one from the instance it replaced on restart.
///
/// Starts are single-flight, and stopping waits for an in-flight `make up`: killing it midway
/// would leave whatever it already spawned running with nobody to stop it.
public actor ServerLauncher {
    static let upCommand = "make up"
    static let downCommand = "make down"
    private static let ansiEscape = "\u{1B}\\[[0-9;?]*[A-Za-z]"

    private let projectDir: URL
    private let probe: HealthProbe
    private let runner: CommandRunner
    private let sleeper: Sleeper
    private let policy: LaunchPolicy
    private let adoptRunningServers: Bool
    private var ownsProcesses = false
    private var inFlightStart: Task<LaunchOutcome, Never>?
    private var inFlightStop: Task<Void, Never>?

    public init(
        projectDir: URL,
        probe: HealthProbe,
        runner: CommandRunner,
        sleeper: Sleeper,
        policy: LaunchPolicy,
        adoptRunningServers: Bool = false
    ) {
        self.projectDir = projectDir
        self.probe = probe
        self.runner = runner
        self.sleeper = sleeper
        self.policy = policy
        self.adoptRunningServers = adoptRunningServers
    }

    /// Whether quitting runs `make down`: what a restarted instance has to take over.
    public var ownsServers: Bool { ownsProcesses }

    public func start() async -> LaunchOutcome {
        if inFlightStop != nil { return .failed(message: "Приложение закрывается", outputTail: "") }
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
        if await probe.isUp() {
            if adoptRunningServers { ownsProcesses = true }
            return .ready
        }

        ownsProcesses = true
        let result = await runner.run(Self.upCommand, in: projectDir)
        guard result.exitCode == 0 else {
            return .failed(message: "Сервер не запустился (код выхода \(result.exitCode))", outputTail: tail(of: result.output))
        }

        for _ in 0..<policy.attempts where inFlightStop == nil {
            if await probe.isUp() { return .ready }
            await sleeper.sleep(for: policy.pollInterval)
        }
        return .failed(message: "Сервер запустился, но не отвечает", outputTail: tail(of: result.output))
    }

    private func performStop() async {
        _ = await inFlightStart?.value
        guard ownsProcesses else { return }
        ownsProcesses = false
        _ = await runner.run(Self.downCommand, in: projectDir)
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
