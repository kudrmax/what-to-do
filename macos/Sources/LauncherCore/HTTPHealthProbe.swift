import Foundation

/// The server is up once it answers HTTP at all; the status code does not matter.
public struct HTTPHealthProbe: HealthProbe {
    private static let timeout: TimeInterval = 2

    private let url: URL
    private let session: URLSession

    public init(url: URL) {
        self.url = url
        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = Self.timeout
        configuration.connectionProxyDictionary = [:]
        session = URLSession(configuration: configuration)
    }

    public func isUp() async -> Bool {
        var request = URLRequest(url: url)
        request.httpMethod = "HEAD"
        return (try? await session.data(for: request)) != nil
    }
}
