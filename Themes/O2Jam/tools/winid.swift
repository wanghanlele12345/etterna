import CoreGraphics
import Foundation
let pid = Int32(CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "0") ?? 0
let list = CGWindowListCopyWindowInfo([.optionAll], kCGNullWindowID) as? [[String: Any]] ?? []
for w in list {
    guard (w[kCGWindowOwnerPID as String] as? Int32) == pid else { continue }
    let b = w[kCGWindowBounds as String] as? [String: Any] ?? [:]
    print(w[kCGWindowNumber as String] ?? 0, Int((b["Width"] as? Double) ?? 0), Int((b["Height"] as? Double) ?? 0), "layer", w[kCGWindowLayer as String] ?? 0, "onscreen", w[kCGWindowIsOnscreen as String] ?? false)
}
