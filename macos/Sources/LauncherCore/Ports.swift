import Foundation

public protocol HealthProbe: Sendable {
    func isUp() async -> Bool
}

public struct CommandResult: Equatable, Sendable {
    public let exitCode: Int32
    public let output: String

    public init(exitCode: Int32, output: String) {
        self.exitCode = exitCode
        self.output = output
    }
}

public protocol CommandRunner: Sendable {
    func run(_ command: String, in directory: URL) async -> CommandResult
}

public protocol Sleeper: Sendable {
    func sleep(for duration: Duration) async
}

public struct TaskSleeper: Sleeper {
    public init() {}

    public func sleep(for duration: Duration) async {
        try? await Task.sleep(for: duration)
    }
}
