// Renders Resources/AppIcon.png: a calendar page with one day lit up by a spark, in the web UI palette.
// Run once after changing the design: swift scripts/render-icon.swift Resources/AppIcon.png
import AppKit

let canvas: CGFloat = 1024
let tileInset: CGFloat = 100
let tileRadius: CGFloat = 185
let pageSize = NSSize(width: 560, height: 540)
let pageRadius: CGFloat = 64
let headerHeight: CGFloat = 130
let ringSize = NSSize(width: 34, height: 96)
let ringOffset: CGFloat = 130
let columns = 4
let rows = 3
let cellSize: CGFloat = 72
let cellGap: CGFloat = 34
let sparkCell = (column: 2, row: 1)
let sparkRadius: CGFloat = 82
let sparkWaist: CGFloat = 0.3

let tileTop = NSColor(srgbRed: 0xe8 / 255, green: 0x5d / 255, blue: 0x4f / 255, alpha: 1)
let tileBottom = NSColor(srgbRed: 0xb8 / 255, green: 0x32 / 255, blue: 0x26 / 255, alpha: 1)
let paper = NSColor(srgbRed: 0xff / 255, green: 0xfd / 255, blue: 0xfa / 255, alpha: 1)
let header = NSColor(srgbRed: 0x20 / 255, green: 0x20 / 255, blue: 0x20 / 255, alpha: 1)
let cell = NSColor(srgbRed: 0xeb / 255, green: 0xe8 / 255, blue: 0xe3 / 255, alpha: 1)
let accent = NSColor(srgbRed: 0xdc / 255, green: 0x4c / 255, blue: 0x3e / 255, alpha: 1)
let glint = NSColor(srgbRed: 0xff / 255, green: 0xc8 / 255, blue: 0x57 / 255, alpha: 1)

/// A four-pointed star: long rays with a narrow waist between them.
func spark(center: NSPoint, radius: CGFloat) -> NSBezierPath {
    let path = NSBezierPath()
    for index in 0..<8 {
        let angle = CGFloat(index) * .pi / 4 - .pi / 2
        let length = index.isMultiple(of: 2) ? radius : radius * sparkWaist
        let point = NSPoint(x: center.x + cos(angle) * length, y: center.y + sin(angle) * length)
        index == 0 ? path.move(to: point) : path.line(to: point)
    }
    path.close()
    return path
}

let output = CommandLine.arguments.dropFirst().first ?? "AppIcon.png"
let image = NSImage(size: NSSize(width: canvas, height: canvas), flipped: true) { _ in
    let tile = NSRect(x: tileInset, y: tileInset, width: canvas - 2 * tileInset, height: canvas - 2 * tileInset)
    let tilePath = NSBezierPath(roundedRect: tile, xRadius: tileRadius, yRadius: tileRadius)
    NSGradient(starting: tileTop, ending: tileBottom)!.draw(in: tilePath, angle: 90)

    let page = NSRect(x: tile.midX - pageSize.width / 2, y: tile.midY - pageSize.height / 2 + 24,
                      width: pageSize.width, height: pageSize.height)
    let pagePath = NSBezierPath(roundedRect: page, xRadius: pageRadius, yRadius: pageRadius)
    NSGraphicsContext.saveGraphicsState()
    let shadow = NSShadow()
    shadow.shadowColor = NSColor.black.withAlphaComponent(0.28)
    shadow.shadowBlurRadius = 40
    shadow.shadowOffset = NSSize(width: 0, height: -18)
    shadow.set()
    paper.setFill()
    pagePath.fill()
    NSGraphicsContext.restoreGraphicsState()

    NSGraphicsContext.saveGraphicsState()
    pagePath.addClip()
    header.setFill()
    NSRect(x: page.minX, y: page.minY, width: page.width, height: headerHeight).fill()
    NSGraphicsContext.restoreGraphicsState()

    paper.setFill()
    for x in [page.midX - ringOffset, page.midX + ringOffset] {
        let ring = NSRect(x: x - ringSize.width / 2, y: page.minY - ringSize.height / 2,
                          width: ringSize.width, height: ringSize.height)
        NSBezierPath(roundedRect: ring, xRadius: ringSize.width / 2, yRadius: ringSize.width / 2).fill()
    }

    let gridWidth = CGFloat(columns) * cellSize + CGFloat(columns - 1) * cellGap
    let gridHeight = CGFloat(rows) * cellSize + CGFloat(rows - 1) * cellGap
    let body = NSRect(x: page.minX, y: page.minY + headerHeight, width: page.width, height: page.height - headerHeight)
    let origin = NSPoint(x: body.midX - gridWidth / 2, y: body.midY - gridHeight / 2)
    func cellRect(_ column: Int, _ row: Int) -> NSRect {
        NSRect(x: origin.x + CGFloat(column) * (cellSize + cellGap), y: origin.y + CGFloat(row) * (cellSize + cellGap),
               width: cellSize, height: cellSize)
    }

    cell.setFill()
    for row in 0..<rows {
        for column in 0..<columns where (column, row) != sparkCell {
            NSBezierPath(roundedRect: cellRect(column, row), xRadius: 18, yRadius: 18).fill()
        }
    }

    let sparkRect = cellRect(sparkCell.column, sparkCell.row)
    let center = NSPoint(x: sparkRect.midX, y: sparkRect.midY)
    NSGraphicsContext.saveGraphicsState()
    let glow = NSShadow()
    glow.shadowColor = glint.withAlphaComponent(0.9)
    glow.shadowBlurRadius = 36
    glow.set()
    accent.setFill()
    spark(center: center, radius: sparkRadius).fill()
    NSGraphicsContext.restoreGraphicsState()
    glint.setFill()
    spark(center: NSPoint(x: center.x + sparkRadius * 0.72, y: center.y - sparkRadius * 0.72), radius: sparkRadius * 0.34).fill()
    return true
}

let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: Int(canvas), pixelsHigh: Int(canvas),
                              bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
                              colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: bitmap)
image.draw(in: NSRect(x: 0, y: 0, width: canvas, height: canvas))
NSGraphicsContext.restoreGraphicsState()
try! bitmap.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: output))
