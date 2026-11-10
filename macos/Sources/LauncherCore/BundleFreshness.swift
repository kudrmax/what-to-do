import Foundation

/// Tells whether the bundle on disk was rebuilt from other app sources than the running one,
/// as `scripts/update.sh` does when `macos` changed between versions.
public enum BundleFreshness {
    public static let treeKey = "WTGMacosTree"

    /// The installed Info.plist is read from disk every time: `Bundle` caches it per path,
    /// so a bundle rebuilt in place would otherwise look unchanged.
    public static func isStale(running: Bundle, installedAt bundleURL: URL) -> Bool {
        guard let runningTree = running.object(forInfoDictionaryKey: treeKey) as? String, !runningTree.isEmpty,
              let installedTree = installedTree(at: bundleURL), !installedTree.isEmpty
        else { return false }
        return runningTree != installedTree
    }

    private static func installedTree(at bundleURL: URL) -> String? {
        let plistURL = bundleURL.appendingPathComponent("Contents/Info.plist")
        guard let data = try? Data(contentsOf: plistURL),
              let info = try? PropertyListSerialization.propertyList(from: data, format: nil) as? [String: Any]
        else { return nil }
        return info[treeKey] as? String
    }
}
