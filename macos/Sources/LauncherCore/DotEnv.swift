import Foundation

/// The optional `.env` of a copy, read the way the server reads it: `NAME=value` lines, `#` comments.
public enum DotEnv {
    public static func read(_ url: URL) -> [String: String] {
        guard let text = try? String(contentsOf: url, encoding: .utf8) else { return [:] }
        var values: [String: String] = [:]
        for rawLine in text.split(whereSeparator: \.isNewline) {
            let line = rawLine.trimmingCharacters(in: .whitespaces)
            guard !line.isEmpty, !line.hasPrefix("#"), let equals = line.firstIndex(of: "=") else { continue }
            var name = line[..<equals].trimmingCharacters(in: .whitespaces)
            if name.hasPrefix("export ") { name = String(name.dropFirst("export ".count)).trimmingCharacters(in: .whitespaces) }
            values[name] = unquoted(line[line.index(after: equals)...].trimmingCharacters(in: .whitespaces))
        }
        return values
    }

    private static func unquoted(_ value: String) -> String {
        if value.count >= 2, let first = value.first, first == value.last, first == "\"" || first == "'" {
            return String(value.dropFirst().dropLast())
        }
        return (value.components(separatedBy: " #").first ?? value).trimmingCharacters(in: .whitespaces)
    }
}
