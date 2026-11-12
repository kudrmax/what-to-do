import Foundation

/// The server is up once the app's version endpoint answers with a version. Any other answer
/// on the port comes from another program and does not count.
public struct HTTPHealthProbe: HealthProbe {
    private static let timeout: TimeInterval = 2

    private struct VersionAnswer: Decodable {
        let version: String
    }

    private let url: URL
    private let session: URLSession

    public init(url: URL) {
        self.url = url
        session = Self.ephemeralSession()
    }

    public func isUp() async -> Bool {
        guard let (body, response) = try? await session.data(from: url),
              (response as? HTTPURLResponse)?.statusCode == 200 else { return false }
        return Self.isVersionAnswer(body)
    }

    static func isVersionAnswer(_ body: Data) -> Bool {
        (try? JSONDecoder().decode(VersionAnswer.self, from: body)) != nil
    }

    private static func ephemeralSession() -> URLSession {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = timeout
        configuration.connectionProxyDictionary = [:]
        return URLSession(configuration: configuration)
    }
}
