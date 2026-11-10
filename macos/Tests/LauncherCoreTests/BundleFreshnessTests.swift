import XCTest
@testable import LauncherCore

final class BundleFreshnessTests: XCTestCase {
    private var root: URL!

    override func setUpWithError() throws {
        root = FileManager.default.temporaryDirectory.appendingPathComponent("wtg-freshness-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    }

    func testSameTreeIsNotStale() throws {
        let running = try makeBundle("Running", tree: "aaa")
        let installed = try writeBundle("Installed", tree: "aaa")

        XCTAssertFalse(BundleFreshness.isStale(running: running, installedAt: installed))
    }

    func testDifferentTreeIsStale() throws {
        let running = try makeBundle("Running", tree: "aaa")
        let installed = try writeBundle("Installed", tree: "bbb")

        XCTAssertTrue(BundleFreshness.isStale(running: running, installedAt: installed))
    }

    func testBundleRebuiltAtTheSamePathIsStale() throws {
        let running = try makeBundle("App", tree: "aaa")
        _ = running.infoDictionary
        let installed = try writeBundle("App", tree: "bbb")

        XCTAssertTrue(BundleFreshness.isStale(running: running, installedAt: installed))
    }

    func testRunningWithoutTreeIsNotStale() throws {
        let running = try makeBundle("Running", tree: nil)
        let installed = try writeBundle("Installed", tree: "bbb")

        XCTAssertFalse(BundleFreshness.isStale(running: running, installedAt: installed))
    }

    func testInstalledWithoutTreeIsNotStale() throws {
        let running = try makeBundle("Running", tree: "aaa")
        let installed = try writeBundle("Installed", tree: nil)

        XCTAssertFalse(BundleFreshness.isStale(running: running, installedAt: installed))
    }

    func testEmptyTreeFromTheTemplateIsNotStale() throws {
        let running = try makeBundle("Running", tree: "")
        let installed = try writeBundle("Installed", tree: "bbb")

        XCTAssertFalse(BundleFreshness.isStale(running: running, installedAt: installed))
    }

    func testMissingInstalledBundleIsNotStale() throws {
        let running = try makeBundle("Running", tree: "aaa")

        XCTAssertFalse(BundleFreshness.isStale(running: running, installedAt: root.appendingPathComponent("Gone.app")))
    }

    private func makeBundle(_ name: String, tree: String?) throws -> Bundle {
        try XCTUnwrap(Bundle(url: try writeBundle(name, tree: tree)))
    }

    private func writeBundle(_ name: String, tree: String?) throws -> URL {
        let bundle = root.appendingPathComponent("\(name).app", isDirectory: true)
        let contents = bundle.appendingPathComponent("Contents", isDirectory: true)
        try FileManager.default.createDirectory(at: contents, withIntermediateDirectories: true)
        var info: [String: Any] = ["CFBundleIdentifier": "test.\(name)"]
        if let tree { info[BundleFreshness.treeKey] = tree }
        let data = try PropertyListSerialization.data(fromPropertyList: info, format: .xml, options: 0)
        try data.write(to: contents.appendingPathComponent("Info.plist"))
        return bundle
    }
}
