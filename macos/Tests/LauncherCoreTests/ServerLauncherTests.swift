import XCTest
@testable import LauncherCore

final class ServerLauncherTests: XCTestCase {
    private let projectDir = URL(fileURLWithPath: "/tmp/project")

    func testUsesRunningServerWithoutStartingIt() async {
        let probe = FakeProbe(upAfter: 0)
        let runner = FakeRunner()
        let launcher = makeLauncher(probe: probe, runner: runner)

        let outcome = await launcher.start()

        XCTAssertEqual(outcome, .ready)
        let observed1 = await runner.commands
        XCTAssertEqual(observed1, [])
    }

    func testStartsServerWhenItIsDown() async {
        let probe = FakeProbe(upAfter: 3)
        let runner = FakeRunner()
        let launcher = makeLauncher(probe: probe, runner: runner)

        let outcome = await launcher.start()

        XCTAssertEqual(outcome, .ready)
        let observed2 = await runner.commands
        XCTAssertEqual(observed2, ["make up"])
        let observed3 = await runner.directories
        XCTAssertEqual(observed3, [projectDir])
    }

    func testReportsFailedStartWithOutputTail() async {
        let probe = FakeProbe(upAfter: nil)
        let output = (1...50).map { "line \($0)" }.joined(separator: "\n")
        let runner = FakeRunner(results: ["make up": CommandResult(exitCode: 2, output: output)])
        let launcher = makeLauncher(probe: probe, runner: runner)

        let outcome = await launcher.start()

        guard case let .failed(message, tail) = outcome else { return XCTFail("expected failure, got \(outcome)") }
        XCTAssertTrue(message.contains("код выхода 2"))
        XCTAssertTrue(tail.hasSuffix("line 50"))
        XCTAssertFalse(tail.contains("line 1\n"))
    }

    func testReportsTimeoutWhenServerNeverAnswers() async {
        let probe = FakeProbe(upAfter: nil)
        let launcher = makeLauncher(probe: probe, runner: FakeRunner())

        let outcome = await launcher.start()

        guard case .failed = outcome else { return XCTFail("expected failure, got \(outcome)") }
    }

    func testStopsOnlyProcessesItStarted() async {
        let runner = FakeRunner()
        let launcher = makeLauncher(probe: FakeProbe(upAfter: 1), runner: runner)

        _ = await launcher.start()
        await launcher.stop()

        let observed4 = await runner.commands
        XCTAssertEqual(observed4, ["make up", "make down"])
    }

    func testLeavesForeignProcessesRunning() async {
        let runner = FakeRunner()
        let launcher = makeLauncher(probe: FakeProbe(upAfter: 0), runner: runner)

        _ = await launcher.start()
        let owns = await launcher.ownsServers
        await launcher.stop()

        XCTAssertFalse(owns)
        let observed5 = await runner.commands
        XCTAssertEqual(observed5, [])
    }

    func testAdoptedRunningServersAreStoppedOnQuit() async {
        let runner = FakeRunner()
        let launcher = makeLauncher(probe: FakeProbe(upAfter: 0), runner: runner, adoptRunningServers: true)

        let outcome = await launcher.start()
        let owns = await launcher.ownsServers
        await launcher.stop()

        XCTAssertEqual(outcome, .ready)
        XCTAssertTrue(owns)
        let observed = await runner.commands
        XCTAssertEqual(observed, ["make down"])
    }

    func testAdoptingStartsServersThatAreDown() async {
        let runner = FakeRunner()
        let launcher = makeLauncher(probe: FakeProbe(upAfter: 1), runner: runner, adoptRunningServers: true)

        _ = await launcher.start()
        await launcher.stop()

        let observed = await runner.commands
        XCTAssertEqual(observed, ["make up", "make down"])
    }

    func testStopsProcessesStartedEvenIfServerNeverCameUp() async {
        let runner = FakeRunner()
        let launcher = makeLauncher(probe: FakeProbe(upAfter: nil), runner: runner)

        _ = await launcher.start()
        await launcher.stop()

        let observed6 = await runner.commands
        XCTAssertEqual(observed6, ["make up", "make down"])
    }

    func testQuitDuringMakeUpWaitsForItAndThenStops() async {
        let runner = FakeRunner(holdMakeUp: true)
        let launcher = makeLauncher(probe: FakeProbe(upAfter: 1), runner: runner)

        let starting = Task { await launcher.start() }
        await runner.waitUntilMakeUpStarted()
        let stopping = Task { await launcher.stop() }
        await Task.yield()
        let observed7 = await runner.commands
        XCTAssertEqual(observed7, ["make up"])

        await runner.releaseMakeUp()
        _ = await starting.value
        await stopping.value

        let observed8 = await runner.commands
        XCTAssertEqual(observed8, ["make up", "make down"])
    }

    func testConcurrentStartsRunMakeUpOnce() async {
        let runner = FakeRunner(holdMakeUp: true)
        let launcher = makeLauncher(probe: FakeProbe(upAfter: 2), runner: runner)

        let first = Task { await launcher.start() }
        await runner.waitUntilMakeUpStarted()
        let second = Task { await launcher.start() }
        await Task.yield()
        await runner.releaseMakeUp()

        let observed9 = await first.value
        XCTAssertEqual(observed9, .ready)
        let observed10 = await second.value
        XCTAssertEqual(observed10, .ready)
        let observed11 = await runner.commands
        XCTAssertEqual(observed11, ["make up"])
    }

    func testStoppingTwiceRunsMakeDownOnce() async {
        let runner = FakeRunner()
        let launcher = makeLauncher(probe: FakeProbe(upAfter: 1), runner: runner)
        _ = await launcher.start()

        async let first: Void = launcher.stop()
        async let second: Void = launcher.stop()
        _ = await (first, second)

        let observed12 = await runner.commands
        XCTAssertEqual(observed12, ["make up", "make down"])
    }

    func testDoesNotStartAfterStop() async {
        let runner = FakeRunner()
        let launcher = makeLauncher(probe: FakeProbe(upAfter: nil), runner: runner)

        await launcher.stop()
        let outcome = await launcher.start()

        guard case .failed = outcome else { return XCTFail("expected failure, got \(outcome)") }
        let observed13 = await runner.commands
        XCTAssertEqual(observed13, [])
    }

    func testOutputTailIsReadable() async {
        let runner = FakeRunner(results: ["make up": CommandResult(exitCode: 1, output: "\u{1B}[1;33mBuilding\u{1B}[0m\nboom")])
        let launcher = makeLauncher(probe: FakeProbe(upAfter: nil), runner: runner)

        let outcome = await launcher.start()

        XCTAssertEqual(outcome, .failed(message: "Сервер не запустился (код выхода 1)", outputTail: "Building\nboom"))
    }

    private func makeLauncher(probe: FakeProbe, runner: FakeRunner, adoptRunningServers: Bool = false) -> ServerLauncher {
        ServerLauncher(
            projectDir: projectDir,
            probe: probe,
            runner: runner,
            sleeper: InstantSleeper(),
            policy: LaunchPolicy(pollInterval: .milliseconds(1), attempts: 10, outputTailLines: 20),
            adoptRunningServers: adoptRunningServers
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
    private let results: [String: CommandResult]
    private var gate: CheckedContinuation<Void, Never>?
    private var holdUp: Bool
    private var arrived: CheckedContinuation<Void, Never>?
    private(set) var commands: [String] = []
    private(set) var directories: [URL] = []

    init(results: [String: CommandResult] = [:], holdMakeUp: Bool = false) {
        self.results = results
        self.holdUp = holdMakeUp
    }

    func run(_ command: String, in directory: URL) async -> CommandResult {
        commands.append(command)
        directories.append(directory)
        if command == "make up" && holdUp {
            arrived?.resume()
            arrived = nil
            await withCheckedContinuation { gate = $0 }
        }
        return results[command] ?? CommandResult(exitCode: 0, output: "")
    }

    func waitUntilMakeUpStarted() async {
        if commands.contains("make up") { return }
        await withCheckedContinuation { arrived = $0 }
    }

    func releaseMakeUp() {
        holdUp = false
        gate?.resume()
        gate = nil
    }
}

private struct InstantSleeper: Sleeper {
    func sleep(for duration: Duration) async {}
}
