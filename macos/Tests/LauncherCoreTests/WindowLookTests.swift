import XCTest
@testable import LauncherCore

final class WindowLookTests: XCTestCase {
    func testExplicitModeKeepsItsLookAndBackground() {
        XCTAssertEqual(
            WindowLook.atLaunch(reported: .light, storedBackgroundIsDark: false, systemIsDark: true),
            WindowLook(mode: .light, usesStoredBackground: true)
        )
        XCTAssertEqual(
            WindowLook.atLaunch(reported: .dark, storedBackgroundIsDark: nil, systemIsDark: false),
            WindowLook(mode: .dark, usesStoredBackground: false)
        )
    }

    func testSystemModeInheritsAndKeepsOnlyAMatchingBackground() {
        XCTAssertEqual(
            WindowLook.atLaunch(reported: .system, storedBackgroundIsDark: true, systemIsDark: true),
            WindowLook(mode: .system, usesStoredBackground: true)
        )
        XCTAssertEqual(
            WindowLook.atLaunch(reported: .system, storedBackgroundIsDark: true, systemIsDark: false),
            WindowLook(mode: .system, usesStoredBackground: false)
        )
        XCTAssertEqual(
            WindowLook.atLaunch(reported: .system, storedBackgroundIsDark: nil, systemIsDark: false),
            WindowLook(mode: .system, usesStoredBackground: false)
        )
    }

    func testNothingReportedFallsBackToTheBackgroundsDarkness() {
        XCTAssertEqual(
            WindowLook.atLaunch(reported: nil, storedBackgroundIsDark: true, systemIsDark: false),
            WindowLook(mode: .dark, usesStoredBackground: true)
        )
        XCTAssertEqual(
            WindowLook.atLaunch(reported: nil, storedBackgroundIsDark: false, systemIsDark: true),
            WindowLook(mode: .light, usesStoredBackground: true)
        )
        XCTAssertEqual(
            WindowLook.atLaunch(reported: nil, storedBackgroundIsDark: nil, systemIsDark: true),
            WindowLook(mode: .system, usesStoredBackground: false)
        )
    }

    func testModeParsesWhatThePagePosts() {
        XCTAssertEqual(ThemeMode(rawValue: "system"), .system)
        XCTAssertNil(ThemeMode(rawValue: "auto"))
    }
}
