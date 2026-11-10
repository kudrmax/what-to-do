import XCTest
@testable import LauncherCore

final class TitlebarInsetsTests: XCTestCase {
    func testScriptSetsEveryInsetInCSSPixels() {
        let script = TitlebarInsets(height: 52, leading: 90, trailing: 0).styleScript(pageZoom: 1)

        XCTAssertTrue(script.contains(#""--shell-titlebar-h":"52.0px""#))
        XCTAssertTrue(script.contains(#""--shell-inset-start":"90.0px""#))
        XCTAssertTrue(script.contains(#""--shell-inset-end":"0.0px""#))
    }

    func testPageZoomShrinksCSSPixels() {
        let script = TitlebarInsets(height: 52, leading: 90, trailing: 30).styleScript(pageZoom: 2)

        XCTAssertTrue(script.contains(#""--shell-titlebar-h":"26.0px""#))
        XCTAssertTrue(script.contains(#""--shell-inset-start":"45.0px""#))
        XCTAssertTrue(script.contains(#""--shell-inset-end":"15.0px""#))
    }

    func testDoubleClickFollowsSystemPreference() {
        XCTAssertEqual(TitlebarDoubleClick(preference: nil), .zoom)
        XCTAssertEqual(TitlebarDoubleClick(preference: "Maximize"), .zoom)
        XCTAssertEqual(TitlebarDoubleClick(preference: "Minimize"), .minimize)
        XCTAssertEqual(TitlebarDoubleClick(preference: "None"), TitlebarDoubleClick.none)
    }
}
