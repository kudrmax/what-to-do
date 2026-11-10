// swift-tools-version:5.10
import PackageDescription

let package = Package(
    name: "WhatToDo",
    platforms: [.macOS(.v14)],
    targets: [
        .target(name: "LauncherCore"),
        .executableTarget(name: "WhatToDo", dependencies: ["LauncherCore"]),
        .testTarget(name: "LauncherCoreTests", dependencies: ["LauncherCore"]),
    ]
)
