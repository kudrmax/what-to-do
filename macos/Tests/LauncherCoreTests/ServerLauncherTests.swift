import XCTest
@testable import LauncherCore

final class ServerLauncherTests: XCTestCase {
    private let projectDir = URL(fileURLWithPath: "/tmp/project")
    private lazy var commands = ServerCommands(projectDir: projectDir, port: 18765)
    private var up: String { commands.up }
    private var down: String { commands.down }

    func testUsesRunningServerWithoutStartingIt() async {
        let probe = FakeProbe(upAfter: 0)
        let runner = FakeRunner(upCommand: up)
        let launcher = makeLauncher(probe: probe, runner: runner)

        let outcome = await launcher.start()

        XCTAssertEqual(outcome, .ready)
        let observed1 = await runner.commands
        XCTAssertEqual(observed1, [])
    }

    func testStartsServerWhenItIsDown() async {
        let probe = FakeProbe(upAfter: 3)
        let runner = FakeRunner(upCommand: up)
        let launcher = makeLauncher(probe: probe, runner: runner)

        let outcome = await launcher.start()

        XCTAssertEqual(outcome, .ready)
        let observed2 = await runner.commands
        XCTAssertEqual(observed2, [up])
        let observed3 = await runner.directories
        XCTAssertEqual(observed3, [projectDir])
    }

    func testReportsFailedStartWithOutputTail() async {
        let probe = FakeProbe(upAfter: nil)
        let output = (1...50).map { "line \($0)" }.joined(separator: "\n")
        let runner = FakeRunner(upCommand: up, results: [up: CommandResult(exitCode: 2, output: output)])
        let launcher = makeLauncher(probe: probe, runner: runner)

        let outcome = await launcher.start()

        guard case let .failed(message, tail) = outcome else { return XCTFail("expected failure, got \(outcome)") }
        XCTAssertTrue(message.contains("exit code 2"))
        XCTAssertTrue(tail.hasSuffix("line 50"))
        XCTAssertFalse(tail.contains("line 1\n"))
    }

    func testReportsTimeoutWhenServerNeverAnswers() async {
        let probe = FakeProbe(upAfter: nil)
        let launcher = makeLauncher(probe: probe, runner: FakeRunner(upCommand: up))

        let outcome = await launcher.start()

        guard case .failed = outcome else { return XCTFail("expected failure, got \(outcome)") }
    }

    func testStopsServersItStarted() async {
        let runner = FakeRunner(upCommand: up)
        let launcher = makeLauncher(probe: FakeProbe(upAfter: 1), runner: runner)

        _ = await launcher.start()
        await launcher.stop()

        let observed4 = await runner.commands
        XCTAssertEqual(observed4, [up, down])
    }

    func testStopsServersThatWereAlreadyRunning() async {
        let runner = FakeRunner(upCommand: up)
        let launcher = makeLauncher(probe: FakeProbe(upAfter: 0), runner: runner)

        _ = await launcher.start()
        await launcher.stop()

        let observed5 = await runner.commands
        XCTAssertEqual(observed5, [down])
    }

    func testStopsProcessesStartedEvenIfServerNeverCameUp() async {
        let runner = FakeRunner(upCommand: up)
        let launcher = makeLauncher(probe: FakeProbe(upAfter: nil), runner: runner)

        _ = await launcher.start()
        await launcher.stop()

        let observed6 = await runner.commands
        XCTAssertEqual(observed6, [up, down])
    }

    func testQuitDuringUpWaitsForItAndThenStops() async {
        let runner = FakeRunner(upCommand: up, holdUp: true)
        let launcher = makeLauncher(probe: FakeProbe(upAfter: 1), runner: runner)

        let starting = Task { await launcher.start() }
        await runner.waitUntilUpStarted()
        let stopping = Task { await launcher.stop() }
        await Task.yield()
        let observed7 = await runner.commands
        XCTAssertEqual(observed7, [up])

        await runner.releaseUp()
        _ = await starting.value
        await stopping.value

        let observed8 = await runner.commands
        XCTAssertEqual(observed8, [up, down])
    }

    func testConcurrentStartsRunUpOnce() async {
        let runner = FakeRunner(upCommand: up, holdUp: true)
        let launcher = makeLauncher(probe: FakeProbe(upAfter: 2), runner: runner)

        let first = Task { await launcher.start() }
        await runner.waitUntilUpStarted()
        let second = Task { await launcher.start() }
        await Task.yield()
        await runner.releaseUp()

        let observed9 = await first.value
        XCTAssertEqual(observed9, .ready)
        let observed10 = await second.value
        XCTAssertEqual(observed10, .ready)
        let observed11 = await runner.commands
        XCTAssertEqual(observed11, [up])
    }

    func testStoppingTwiceRunsDownOnce() async {
        let runner = FakeRunner(upCommand: up)
        let launcher = makeLauncher(probe: FakeProbe(upAfter: 1), runner: runner)
        _ = await launcher.start()

        async let first: Void = launcher.stop()
        async let second: Void = launcher.stop()
        _ = await (first, second)

        let observed12 = await runner.commands
        XCTAssertEqual(observed12, [up, down])
    }

    func testDoesNotStartAfterStop() async {
        let runner = FakeRunner(upCommand: up)
        let launcher = makeLauncher(probe: FakeProbe(upAfter: nil), runner: runner)

        await launcher.stop()
        let outcome = await launcher.start()

        guard case .failed = outcome else { return XCTFail("expected failure, got \(outcome)") }
        let observed13 = await runner.commands
        XCTAssertEqual(observed13, [down])
    }

    func testRunsTheCopysOwnCommandLineByItsFullPath() {
        let commands = ServerCommands(projectDir: URL(fileURLWithPath: "/Users/max/what's on"), port: 18766)

        XCTAssertEqual(commands.up, "'/Users/max/what'\\''s on/.venv/bin/where-to-go' up --port 18766")
        XCTAssertEqual(commands.down, "'/Users/max/what'\\''s on/.venv/bin/where-to-go' down")
    }

    func testOutputTailIsReadable() async {
        let runner = FakeRunner(upCommand: up, results: [up: CommandResult(exitCode: 1, output: "\u{1B}[1;33mBuilding\u{1B}[0m\nboom")])
        let launcher = makeLauncher(probe: FakeProbe(upAfter: nil), runner: runner)

        let outcome = await launcher.start()

        XCTAssertEqual(outcome, .failed(message: "The server didn’t start (exit code 1)", outputTail: "Building\nboom"))
    }

    private func makeLauncher(probe: FakeProbe, runner: FakeRunner) -> ServerLauncher {
        ServerLauncher(
            projectDir: projectDir,
            commands: commands,
            probe: probe,
            runner: runner,
            sleeper: InstantSleeper(),
            policy: LaunchPolicy(pollInterval: .milliseconds(1), attempts: 10, outputTailLines: 20)
        )
    }
}

private final class FakeProbe: HealthProbe, @unchecked Sendable {
    private let upAfter: Int?
    private var calls = 0

    init(upAfter: Int?) { self.upAfter = upAfter }

    func isUp() async -> Bool {
        defer { calls += 1 }
        guard let upAfter else { return false }
        return calls >= upAfter
    }
}

private actor FakeRunner: CommandRunner {
    private let upCommand: String
    private let results: [String: CommandResult]
    private var gate: CheckedContinuation<Void, Never>?
    private var holdUp: Bool
    private var arrived: CheckedContinuation<Void, Never>?
    private(set) var commands: [String] = []
    private(set) var directories: [URL] = []

    init(upCommand: String, results: [String: CommandResult] = [:], holdUp: Bool = false) {
        self.upCommand = upCommand
        self.results = results
        self.holdUp = holdUp
    }

    func run(_ command: String, in directory: URL) async -> CommandResult {
        commands.append(command)
        directories.append(directory)
        if command == upCommand && holdUp {
            arrived?.resume()
            arrived = nil
            await withCheckedContinuation { gate = $0 }
        }
        return results[command] ?? CommandResult(exitCode: 0, output: "")
    }

    func waitUntilUpStarted() async {
        if commands.contains(upCommand) { return }
        await withCheckedContinuation { arrived = $0 }
    }

    func releaseUp() {
        holdUp = false
        gate?.resume()
        gate = nil
    }
}

private struct InstantSleeper: Sleeper {
    func sleep(for duration: Duration) async {}
}
