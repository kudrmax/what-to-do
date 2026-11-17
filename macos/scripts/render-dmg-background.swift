// Renders the disk image window's background: an arrow from the app to Applications and what to do.
// Run once after changing the design or the icon positions in dmg/settings.py:
//   swift scripts/render-dmg-background.swift dmg/background.png 1 && swift scripts/render-dmg-background.swift dmg/background@2x.png 2
import AppKit

let size = NSSize(width: 640, height: 400)
let appCenter = NSPoint(x: 170, y: 180)
let applicationsCenter = NSPoint(x: 470, y: 180)
let arrowInset: CGFloat = 92
let arrowHead: CGFloat = 16

let paper = NSColor(srgbRed: 0xfa / 255, green: 0xf9 / 255, blue: 0xf7 / 255, alpha: 1)
let ink = NSColor(srgbRed: 0x20 / 255, green: 0x20 / 255, blue: 0x20 / 255, alpha: 1)
let muted = NSColor(srgbRed: 0x6b / 255, green: 0x6b / 255, blue: 0x6b / 255, alpha: 1)
let accent = NSColor(srgbRed: 0xdc / 255, green: 0x4c / 255, blue: 0x3e / 255, alpha: 1)

let arguments = CommandLine.arguments.dropFirst()
let output = arguments.first ?? "background.png"
let scale = CGFloat(Double(arguments.dropFirst().first ?? "1") ?? 1)

func draw(_ text: String, size fontSize: CGFloat, weight: NSFont.Weight, color: NSColor, centerY: CGFloat) {
    let attributes: [NSAttributedString.Key: Any] = [.font: NSFont.systemFont(ofSize: fontSize, weight: weight), .foregroundColor: color]
    let line = NSAttributedString(string: text, attributes: attributes)
    let bounds = line.size()
    line.draw(at: NSPoint(x: (size.width - bounds.width) / 2, y: centerY - bounds.height / 2))
}

let rep = NSBitmapImageRep(
    bitmapDataPlanes: nil, pixelsWide: Int(size.width * scale), pixelsHigh: Int(size.height * scale),
    bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0
)!
rep.size = size
NSGraphicsContext.saveGraphicsState()
let context = NSGraphicsContext(bitmapImageRep: rep)!
NSGraphicsContext.current = context
context.cgContext.translateBy(x: 0, y: size.height)
context.cgContext.scaleBy(x: 1, y: -1)
let flipped = NSGraphicsContext(cgContext: context.cgContext, flipped: true)
NSGraphicsContext.current = flipped

paper.setFill()
NSRect(origin: .zero, size: size).fill()

let start = NSPoint(x: appCenter.x + arrowInset, y: appCenter.y)
let end = NSPoint(x: applicationsCenter.x - arrowInset, y: applicationsCenter.y)
let shaft = NSBezierPath()
shaft.move(to: start)
shaft.line(to: NSPoint(x: end.x - arrowHead * 0.6, y: end.y))
shaft.lineWidth = 5
shaft.lineCapStyle = .round
accent.setStroke()
shaft.stroke()
let head = NSBezierPath()
head.move(to: NSPoint(x: end.x, y: end.y))
head.line(to: NSPoint(x: end.x - arrowHead * 1.3, y: end.y - arrowHead))
head.line(to: NSPoint(x: end.x - arrowHead * 1.3, y: end.y + arrowHead))
head.close()
accent.setFill()
head.fill()

draw("Drag What To Do to Applications", size: 17, weight: .semibold, color: ink, centerY: 56)
draw("The first time, macOS may say it can’t check the app for malware:", size: 12, weight: .regular, color: muted, centerY: 318)
draw("open System Settings, then Privacy & Security, and press Open Anyway.", size: 12, weight: .regular, color: muted, centerY: 338)

NSGraphicsContext.restoreGraphicsState()
try! rep.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: output))
