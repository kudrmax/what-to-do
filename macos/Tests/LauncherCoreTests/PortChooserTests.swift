import XCTest
@testable import LauncherCore

final class PortChooserTests: XCTestCase {
    func testTakesThePortFromTheLastLineAfterTheNotes() async {
        let output = "Port 48765 is taken by another program, so What To Do moves to port 48766 and stays there.\n48766\n"
        let chooser = PortChooser(command: "port", workingDirectory: URL(fileURLWithPath: "/tmp"), runner: AnsweringRunner(CommandResult(exitCode: 0, output: output)))

        let port = await chooser.port(fallback: 48765)

        XCTAssertEqual(port, 48766)
    }

    func testFallsBackWhenTheCommandFailsOrSaysNoPort() async {
        for result in [CommandResult(exitCode: 1, output: "48766"), CommandResult(exitCode: 0, output: "Traceback: boom"), CommandResult(exitCode: 0, output: "70000")] {
            let chooser = PortChooser(command: "port", workingDirectory: URL(fileURLWithPath: "/tmp"), runner: AnsweringRunner(result))

            let port = await chooser.port(fallback: 48765)

            XCTAssertEqual(port, 48765, "\(result)")
        }
    }

    func testTheBundledAppAsksItsOwnPythonForThePort() {
        let home = ServerHome.bundle(python: URL(fileURLWithPath: "/Applications/What To Do.app/Contents/Resources/python/bin/python3"), state: URL(fileURLWithPath: "/tmp"))

        XCTAssertEqual(ServerCommands(home: home, port: 48765).port, "'/Applications/What To Do.app/Contents/Resources/python/bin/python3' -m where_to_go port")
    }

    func testTheAppMovesToTheChosenPort() throws {
        let config = try AppConfig(infoDictionary: [AppConfig.bundledKey: true, AppConfig.portKey: "48765"], environment: [:], home: URL(fileURLWithPath: "/Users/me"))

        let moved = config.with(port: 48766)

        XCTAssertEqual(moved.port, 48766)
        XCTAssertEqual(moved.versionURL.absoluteString, "http://127.0.0.1:48766/api/version")
        XCTAssertTrue(moved.isAppURL(URL(string: "http://127.0.0.1:48766/event/1")!))
        XCTAssertFalse(moved.isAppURL(URL(string: "http://127.0.0.1:48765/")!))
        XCTAssertEqual(moved.home, config.home)
    }
}

private struct AnsweringRunner: CommandRunner {
    let result: CommandResult

    init(_ result: CommandResult) {
        self.result = result
    }

    func run(_ command: String, in directory: URL) async -> CommandResult {
        result
    }
}
