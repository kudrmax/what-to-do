import AppKit

/// A monochrome take on the app icon: a calendar page with a solid header, two rings and a spark
/// on a day cut out of it. It is a template image, so the menu bar tints it like the system icons.
enum MenuBarIcon {
    private static let size = NSSize(width: 18, height: 18)
    private static let page = NSRect(x: 2, y: 3, width: 14, height: 13)
    private static let pageRadius: CGFloat = 3
    private static let headerHeight: CGFloat = 3.5
    private static let border: CGFloat = 1.4
    private static let rings = [NSRect(x: 5, y: 1.5, width: 1.6, height: 3), NSRect(x: 11.4, y: 1.5, width: 1.6, height: 3)]
    private static let sparkRadius: CGFloat = 4
    private static let sparkWaist: CGFloat = 0.3

    static func make(accessibilityDescription: String) -> NSImage {
        let image = NSImage(size: size, flipped: true) { _ in
            NSColor.black.setFill()
            NSBezierPath(roundedRect: page, xRadius: pageRadius, yRadius: pageRadius).fill()
            guard let context = NSGraphicsContext.current else { return true }
            context.compositingOperation = .destinationOut
            let body = NSRect(
                x: page.minX + border,
                y: page.minY + headerHeight,
                width: page.width - 2 * border,
                height: page.height - headerHeight - border
            )
            NSBezierPath(roundedRect: body, xRadius: pageRadius - border, yRadius: pageRadius - border).fill()
            context.compositingOperation = .sourceOver
            rings.forEach { NSBezierPath(roundedRect: $0, xRadius: $0.width / 2, yRadius: $0.width / 2).fill() }
            spark(center: NSPoint(x: body.midX, y: body.midY), radius: sparkRadius).fill()
            return true
        }
        image.isTemplate = true
        image.accessibilityDescription = accessibilityDescription
        return image
    }

    private static func spark(center: NSPoint, radius: CGFloat) -> NSBezierPath {
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
}
