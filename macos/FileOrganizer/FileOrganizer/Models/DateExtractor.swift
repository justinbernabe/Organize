import Foundation

/// Extracts dates from filenames using known patterns.
/// Port of organize.py's extract_date_from_filename().
struct DateExtractor {
    // Pre-compiled patterns (same order as organize.py)
    private static let patterns: [(NSRegularExpression, (NSTextCheckingResult) -> Date?)] = {
        var p: [(NSRegularExpression, (NSTextCheckingResult) -> Date?)] = []

        // 1. YYYYMMDDTHHMMSS (e.g. 20240226T134501)
        if let re = try? NSRegularExpression(pattern: #"(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})"#) {
            p.append((re, { match in
                dateFrom(match: match, groups: 6, hasTime: true)
            }))
        }

        // 2. YYYY-MM-DDTHH;MM;SS (semicolons as time separators)
        if let re = try? NSRegularExpression(pattern: #"(\d{4})-(\d{2})-(\d{2})T(\d{2});(\d{2});(\d{2})"#) {
            p.append((re, { match in
                dateFrom(match: match, groups: 6, hasTime: true)
            }))
        }

        // 3. YYYY-MM-DD
        if let re = try? NSRegularExpression(pattern: #"(\d{4})-(\d{2})-(\d{2})"#) {
            p.append((re, { match in
                dateFrom(match: match, groups: 3, hasTime: false)
            }))
        }

        // 4. YYYY.MM.DD
        if let re = try? NSRegularExpression(pattern: #"(\d{4})\.(\d{2})\.(\d{2})"#) {
            p.append((re, { match in
                dateFrom(match: match, groups: 3, hasTime: false)
            }))
        }

        // 5. YYYYMMDD (compact, word-boundary protected)
        if let re = try? NSRegularExpression(pattern: #"(?<!\d)(\d{4})(\d{2})(\d{2})(?!\d)"#) {
            p.append((re, { match in
                dateFrom(match: match, groups: 3, hasTime: false)
            }))
        }

        return p
    }()

    /// Try to extract a date from the given filename.
    static func extractDate(from filename: String) -> Date? {
        let range = NSRange(filename.startIndex..., in: filename)

        for (regex, parser) in patterns {
            if let match = regex.firstMatch(in: filename, range: range),
               let date = parser(match) {
                // Reject dates > 1 day in the future (likely misparse)
                if date > Date().addingTimeInterval(86400) {
                    continue
                }
                return date
            }
        }
        return nil
    }

    // MARK: - Helpers

    private static func dateFrom(match: NSTextCheckingResult, groups: Int, hasTime: Bool) -> Date? {
        // Extract captured group values as substring indices are complex with NSTextCheckingResult
        // For now, stub — full implementation extracts Int values from match ranges
        // TODO: Full implementation
        return nil
    }
}
