import XCTest
@testable import LauncherCore

final class SystemAdaptersTests: XCTestCase {
    func testRunnerReturnsExitCodeAndCombinedOutput() async {
        let dir = FileManager.default.temporaryDirectory
        let result = await LoginShellRunner().run("pwd; echo oops >&2; exit 3", in: dir)

        XCTAssertEqual(result.exitCode, 3)
        XCTAssertTrue(result.output.contains(dir.resolvingSymlinksInPath().lastPathComponent))
        XCTAssertTrue(result.output.contains("oops"))
    }

    func testRunnerDoesNotWaitForBackgroundChildren() async {
        let started = ContinuousClock.now
        let result = await LoginShellRunner().run("sleep 5 & echo started", in: FileManager.default.temporaryDirectory)

        XCTAssertEqual(result.exitCode, 0)
        XCTAssertLessThan(ContinuousClock.now - started, .seconds(4))
    }

    func testRunnerKeepsOutputWithInvalidUTF8() async {
        let result = await LoginShellRunner().run("printf 'bad \\377 byte\\nstill here'", in: FileManager.default.temporaryDirectory)

        XCTAssertTrue(result.output.contains("still here"))
    }

    func testProbeReportsClosedPortAsDown() async {
        let probe = HTTPHealthProbe(url: URL(string: "http://localhost:1/")!)

        let isUp = await probe.isUp()

        XCTAssertFalse(isUp)
    }

    func testProbeTakesOnlyAVersionAnswerForTheApp() {
        XCTAssertTrue(HTTPHealthProbe.isVersionAnswer(Data(#"{"version":"1.7.0"}"#.utf8)))
        XCTAssertFalse(HTTPHealthProbe.isVersionAnswer(Data("<html>Directory listing for /</html>".utf8)))
        XCTAssertFalse(HTTPHealthProbe.isVersionAnswer(Data(#"{"detail":"Not Found"}"#.utf8)))
    }

    func testProbeReportsAnotherProgramOnThePortAsDown() async throws {
        let port = 18_000 + Int.random(in: 0..<900)
        let server = Process()
        server.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
        server.arguments = ["-m", "http.server", String(port), "--bind", "127.0.0.1"]
        server.currentDirectoryURL = FileManager.default.temporaryDirectory
        server.standardOutput = FileHandle.nullDevice
        server.standardError = FileHandle.nullDevice
        try server.run()
        defer { server.terminate() }
        let root = URL(string: "http://127.0.0.1:\(port)/")!
        for _ in 0..<50 where (try? await URLSession.shared.data(from: root)) == nil {
            try await Task.sleep(for: .milliseconds(100))
        }
        let foreignAnswer = try? await URLSession.shared.data(from: root)
        XCTAssertNotNil(foreignAnswer, "the stand-in program did not start")

        let isUp = await HTTPHealthProbe(url: root.appending(path: "api/version")).isUp()

        XCTAssertFalse(isUp)
    }
}
