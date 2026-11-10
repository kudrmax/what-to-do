#!/bin/zsh
# Builds the .app for one working copy and installs it into ~/Applications.
# Usage: build-app.sh <project dir> <port> <instance env name> [menu bar icon: 1 or 0]
set -euo pipefail

project_dir=${1:?project dir}
port=${2:?port}
env_name=${3:?instance env name}
menu_bar_icon=${4:-0}

macos_dir=${0:A:h:h}

command -v trash >/dev/null || { echo "ERROR: 'trash' not found (macOS 15+ has it, or: brew install trash)"; exit 1; }
if [[ $(git -C "$project_dir" rev-parse --git-dir) != $(git -C "$project_dir" rev-parse --git-common-dir) ]]; then
    echo "ERROR: make app is for the dev and prod copies, not a worktree: the app would run make up on the dev port."
    exit 1
fi
install_dir="$HOME/Applications"
build_dir="$macos_dir/.build/app"

if [[ $env_name == prod ]]; then
    app_name="What To Do"
    bundle_id="local.what-to-do"
else
    app_name="What To Do ${(C)env_name}"
    bundle_id="local.what-to-do.${${env_name:l}//[^a-z0-9-]/-}"
fi
version=$(git -C "$project_dir" rev-parse --short HEAD)
bundle="$build_dir/$app_name.app"

echo "Building $app_name for $project_dir (port $port)..."
swift build --package-path "$macos_dir" -c release --product WhatToDo
binary="$(swift build --package-path "$macos_dir" -c release --show-bin-path)/WhatToDo"

[[ -e $build_dir ]] && trash "$build_dir"
mkdir -p "$bundle/Contents/MacOS" "$bundle/Contents/Resources"
cp "$binary" "$bundle/Contents/MacOS/$app_name"
plist="$bundle/Contents/Info.plist"
cp "$macos_dir/Resources/Info.plist" "$plist"
for key in CFBundleName CFBundleDisplayName CFBundleExecutable; do
    plutil -replace $key -string "$app_name" "$plist"
done
plutil -replace CFBundleIdentifier -string "$bundle_id" "$plist"
plutil -replace CFBundleShortVersionString -string "$version" "$plist"
plutil -replace CFBundleVersion -string "$version" "$plist"
plutil -replace WTGProjectDir -string "$project_dir" "$plist"
plutil -replace WTGPort -string "$port" "$plist"
plutil -replace WTGMacosTree -string "$(git -C "$project_dir" rev-parse HEAD:macos)" "$plist"
plutil -replace WTGMenuBarIcon -bool $([[ $menu_bar_icon == 1 ]] && echo YES || echo NO) "$plist"
plutil -lint -s "$plist"

iconset="$build_dir/AppIcon.iconset"
mkdir -p "$iconset"
for size in 16 32 128 256 512; do
    sips -z $size $size "$macos_dir/Resources/AppIcon.png" --out "$iconset/icon_${size}x${size}.png" >/dev/null
    sips -z $((size * 2)) $((size * 2)) "$macos_dir/Resources/AppIcon.png" --out "$iconset/icon_${size}x${size}@2x.png" >/dev/null
done
iconutil -c icns "$iconset" -o "$bundle/Contents/Resources/AppIcon.icns"

codesign --force --sign - "$bundle"

mkdir -p "$install_dir"
[[ -e "$install_dir/$app_name.app" ]] && trash "$install_dir/$app_name.app"
mv "$bundle" "$install_dir/"
echo "Installed $install_dir/$app_name.app"
