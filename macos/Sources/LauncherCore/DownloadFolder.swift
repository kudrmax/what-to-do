import Foundation

/// Where files the page hands over (an event's .ics) land before the system opens them.
/// Every download gets its own subfolder, so the file keeps its own name and never overwrites an earlier one.
public struct DownloadFolder {
    public static let fallbackName = "download"

    private let root: URL

    public init(root: URL = FileManager.default.temporaryDirectory.appendingPathComponent("WhatToDo Downloads", isDirectory: true)) {
        self.root = root
    }

    public func destination(suggestedName: String) throws -> URL {
        let folder = root.appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        return folder.appendingPathComponent(Self.safeName(suggestedName), isDirectory: false)
    }

    private static func safeName(_ suggested: String) -> String {
        let name = URL(fileURLWithPath: suggested).lastPathComponent
        return name.isEmpty || name == "/" || name == "." || name == ".." ? fallbackName : name
    }
}
