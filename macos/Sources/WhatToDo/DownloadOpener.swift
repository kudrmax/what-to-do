import AppKit
import LauncherCore
import WebKit

/// Saves a file the page hands over and opens it in its default app, so an event's .ics goes straight to Calendar.
final class DownloadOpener: NSObject, WKDownloadDelegate {
    private let folder: DownloadFolder
    private var destinations: [ObjectIdentifier: URL] = [:]

    init(folder: DownloadFolder = DownloadFolder()) {
        self.folder = folder
    }

    func take(_ download: WKDownload) {
        download.delegate = self
    }

    func download(
        _ download: WKDownload,
        decideDestinationUsing response: URLResponse,
        suggestedFilename: String,
        completionHandler: @escaping (URL?) -> Void
    ) {
        guard let destination = try? folder.destination(suggestedName: suggestedFilename) else {
            return completionHandler(nil)
        }
        destinations[ObjectIdentifier(download)] = destination
        completionHandler(destination)
    }

    func downloadDidFinish(_ download: WKDownload) {
        guard let destination = destinations.removeValue(forKey: ObjectIdentifier(download)) else { return }
        NSWorkspace.shared.open(destination)
    }

    func download(_ download: WKDownload, didFailWithError error: Error, resumeData: Data?) {
        destinations.removeValue(forKey: ObjectIdentifier(download))
        NSSound.beep()
    }
}
