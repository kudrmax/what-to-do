import XCTest
@testable import LauncherCore

final class AppConfigTests: XCTestCase {
    func testReadsProjectDirAndPort() throws {
        let config = try AppConfig(infoDictionary: [
            AppConfig.projectDirKey: "/Users/me/projects/app",
            AppConfig.portKey: "17833",
        ])

        XCTAssertEqual(config.projectDir.path, "/Users/me/projects/app")
        XCTAssertEqual(config.serverURL.absoluteString, "http://127.0.0.1:17833/")
        XCTAssertEqual(config.versionURL.absoluteString, "http://127.0.0.1:17833/api/version")
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
}
