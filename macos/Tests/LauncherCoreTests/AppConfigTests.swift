import XCTest
@testable import LauncherCore

final class AppConfigTests: XCTestCase {
    func testReadsProjectDirAndPort() throws {
        let config = try AppConfig(infoDictionary: [
            AppConfig.projectDirKey: "/Users/me/projects/app",
            AppConfig.portKey: "17833",
        ])

        XCTAssertEqual(config.home, .project(URL(fileURLWithPath: "/Users/me/projects/app", isDirectory: true)))
        XCTAssertFalse(config.isBundled)
        XCTAssertEqual(config.serverURL.absoluteString, "http://127.0.0.1:17833/")
        XCTAssertEqual(config.versionURL.absoluteString, "http://127.0.0.1:17833/api/version")
    }

    func testTheFirstLoadAsksTheServerSoAnUpdateIsNotHiddenByTheCache() throws {
        let config = try AppConfig(infoDictionary: [AppConfig.projectDirKey: "/tmp", AppConfig.portKey: "17833"])

        XCTAssertEqual(config.pageRequest.url, config.serverURL)
        XCTAssertEqual(config.pageRequest.cachePolicy, .reloadRevalidatingCacheData)
    }

    func testMenuBarIconIsOffByDefault() throws {
        let config = try AppConfig(infoDictionary: [AppConfig.projectDirKey: "/tmp", AppConfig.portKey: "17833"])

        XCTAssertFalse(config.showsMenuBarIcon)
    }

    func testReadsMenuBarIcon() throws {
        let config = try AppConfig(infoDictionary: [
            AppConfig.projectDirKey: "/tmp",
            AppConfig.portKey: "17833",
            AppConfig.menuBarIconKey: true,
        ])

        XCTAssertTrue(config.showsMenuBarIcon)
    }

    func testRejectsMissingProjectDir() {
        XCTAssertThrowsError(try AppConfig(infoDictionary: [AppConfig.portKey: "17833"]))
    }

    func testRejectsNonNumericPort() {
        XCTAssertThrowsError(try AppConfig(infoDictionary: [
            AppConfig.projectDirKey: "/tmp",
            AppConfig.portKey: "$(PORT)",
        ]))
    }

    func testKnowsWhichURLsBelongToTheApp() throws {
        let config = try AppConfig(infoDictionary: [AppConfig.projectDirKey: "/tmp", AppConfig.portKey: "17833"])

        XCTAssertTrue(config.isAppURL(URL(string: "http://127.0.0.1:17833/event/3")!))
        XCTAssertFalse(config.isAppURL(URL(string: "http://127.0.0.1:8766/")!))
        XCTAssertFalse(config.isAppURL(URL(string: "http://localhost:17833/")!))
        XCTAssertFalse(config.isAppURL(URL(string: "https://youtube.com/watch?v=1")!))
    }

    private let bundleURL = URL(fileURLWithPath: "/Applications/What To Do.app")

    private func bundledConfig(environment: [String: String] = [:], home: URL = URL(fileURLWithPath: "/Users/me")) throws -> AppConfig {
        try AppConfig(
            infoDictionary: [AppConfig.bundledKey: true, AppConfig.portKey: "18765"],
            bundleURL: bundleURL,
            environment: environment,
            home: home
        )
    }

    func testTheBundledAppRunsItsOwnPythonAndWritesToApplicationSupport() throws {
        let config = try bundledConfig()

        XCTAssertTrue(config.isBundled)
        XCTAssertEqual(config.port, 18765)
        XCTAssertEqual(config.home, .bundle(
            python: URL(fileURLWithPath: "/Applications/What To Do.app/Contents/Resources/python/bin/python3"),
            state: URL(fileURLWithPath: "/Users/me/Library/Application Support/What To Do", isDirectory: true)
        ))
    }

    func testTheBundledAppTakesThePortAndStateFolderFromTheEnvironment() throws {
        let config = try bundledConfig(environment: ["WHERE_TO_GO_PORT": "18799", "WHERE_TO_GO_STATE_DIR": "/tmp/wtg-state"])

        XCTAssertEqual(config.port, 18799)
        XCTAssertEqual(config.home.workingDirectory.path, "/tmp/wtg-state")
    }

    func testTheBundledAppTakesThePortFromTheEnvFileOfItsStateFolder() throws {
        let home = FileManager.default.temporaryDirectory.appending(path: UUID().uuidString)
        let state = home.appending(path: "Library/Application Support/What To Do")
        try FileManager.default.createDirectory(at: state, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: home) }
        try "# moved off a busy port\nexport PORT=\"18800\"\n".write(to: state.appending(path: ".env"), atomically: true, encoding: .utf8)

        XCTAssertEqual(try bundledConfig(home: home).port, 18800)
        XCTAssertEqual(try bundledConfig(environment: ["WHERE_TO_GO_PORT": "18801"], home: home).port, 18801)
    }

    func testTheBundledPythonSeesNoOtherPython() throws {
        let environment = try bundledConfig().home.environment(from: ["PATH": "/usr/bin", "PYTHONHOME": "/opt/conda", "PYTHONPATH": "/x", "HOME": "/Users/me"])

        XCTAssertEqual(environment, ["PATH": "/usr/bin", "HOME": "/Users/me", "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1"])
    }
}
