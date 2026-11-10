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
}
