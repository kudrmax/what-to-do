import XCTest
@testable import LauncherCore

final class DownloadFolderTests: XCTestCase {
    private var root: URL!

    override func setUpWithError() throws {
        root = FileManager.default.temporaryDirectory.appendingPathComponent("wtg-downloads-\(UUID().uuidString)", isDirectory: true)
    }

    override func tearDownWithError() throws {
        try? FileManager.default.trashItem(at: root, resultingItemURL: nil)
    }

    func testKeepsTheSuggestedName() throws {
        let destination = try DownloadFolder(root: root).destination(suggestedName: "event-996.ics")

        XCTAssertEqual(destination.lastPathComponent, "event-996.ics")
        XCTAssertFalse(FileManager.default.fileExists(atPath: destination.path))
    }

    func testTheSameFileTwiceGetsTwoPlaces() throws {
        let folder = DownloadFolder(root: root)
        let first = try folder.destination(suggestedName: "event-996.ics")
        FileManager.default.createFile(atPath: first.path, contents: Data())

        let second = try folder.destination(suggestedName: "event-996.ics")

        XCTAssertNotEqual(first, second)
        XCTAssertFalse(FileManager.default.fileExists(atPath: second.path))
    }

    func testNameCannotLeaveTheFolder() throws {
        let destination = try DownloadFolder(root: root).destination(suggestedName: "../../escape.ics")

        XCTAssertTrue(destination.path.hasPrefix(root.path))
        XCTAssertEqual(destination.lastPathComponent, "escape.ics")
    }

    func testEmptyNameStillGivesAFile() throws {
        let destination = try DownloadFolder(root: root).destination(suggestedName: "")

        XCTAssertFalse(destination.lastPathComponent.isEmpty)
        XCTAssertTrue(destination.path.hasPrefix(root.path))
    }
}
