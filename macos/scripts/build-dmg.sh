#!/bin/zsh
# Builds the self-contained What To Do.app for one kind of Mac and its disk image: Python, the app's
# packages and the built interface go inside the bundle. Posts are read by the Claude Code or Codex the user installed.
#
# Usage: build-dmg.sh <arm64|x86_64> [output dir] [version]
#   The version defaults to the one in pyproject.toml; a different one is for testing updates.
# Needs: Xcode or its Command Line Tools, uv, Node.js (see .nvmrc). Runs on an Apple Silicon or Intel Mac
# for either architecture.
set -euo pipefail
# The app runs on macOS 14 and later (macos/Package.swift); uv picks wheels for that macOS, so PyAV's
# macOS 14 Apple Silicon wheels qualify.
export MACOSX_DEPLOYMENT_TARGET=14.0

arch=${1:?arm64 or x86_64}
repo=${0:A:h:h:h}
out_dir=${2:-$repo/macos/.build/dmg}
version=${3:-$(sed -nE 's/^version = "(.+)"$/\1/p' "$repo/pyproject.toml" | head -1)}

# python-build-standalone, a relocatable CPython: https://github.com/astral-sh/python-build-standalone
python_release=20261026
python_version=3.13.18
case $arch in
    arm64)  python_triple=aarch64-apple-darwin; python_sha256=8392b6ea51d94391befb2c31ebe75463f045d0b69dfcf5e1bb3234e1f5fa3405; label=Apple-Silicon ;;
    x86_64) python_triple=x86_64-apple-darwin;  python_sha256=7412c19d896c99431b74a18a5643e110449a7f9590fbab179c3e5ab27b9aa9e3; label=Intel ;;
    *) echo "ERROR: unknown architecture $arch (arm64 or x86_64)"; exit 2 ;;
esac
python_archive=cpython-$python_version+$python_release-$python_triple-install_only_stripped.tar.gz
python_url=https://github.com/astral-sh/python-build-standalone/releases/download/$python_release/$python_archive

app_name="What To Do"
bundle_id=io.github.kudrmax.what-to-do
work=$repo/macos/.build/dmg-work/$arch
cache=$repo/macos/.build/dmg-cache
bundle=$work/$app_name.app
resources=$bundle/Contents/Resources
site_packages=$resources/python/lib/python3.13/site-packages
dmg=$out_dir/What-To-Do-$version-$label.dmg

command -v trash >/dev/null || { echo "ERROR: 'trash' not found (macOS 15+ has it, or: brew install trash)"; exit 1; }
[[ -e $work ]] && trash "$work"
mkdir -p "$work" "$cache" "$out_dir" "$resources" "$bundle/Contents/MacOS"

echo "==> Python $python_version for $arch"
if [[ ! -f $cache/$python_archive ]] || [[ $(shasum -a 256 "$cache/$python_archive" | cut -d' ' -f1) != $python_sha256 ]]; then
    curl --fail --location --silent --show-error --output "$cache/$python_archive" "$python_url"
fi
[[ $(shasum -a 256 "$cache/$python_archive" | cut -d' ' -f1) == $python_sha256 ]] || { echo "ERROR: $python_archive checksum mismatch"; exit 1; }
tar -xzf "$cache/$python_archive" -C "$resources"

echo "==> The app's packages for $arch"
uv build --wheel --out-dir "$work/wheel" "$repo" >/dev/null
uv export --project "$repo" --frozen --no-dev --no-emit-project --no-hashes --format requirements-txt --output-file "$work/requirements.txt" >/dev/null
if [[ $arch == x86_64 ]]; then
    # cryptography stopped publishing Intel Mac wheels with 49.0; 48.0.1 is the last release with them.
    # The phone page's encryption needs only AES-GCM, PBKDF2 and HMAC, which 48.0.1 has.
    sed -i '' -E 's/^cryptography==.+$/cryptography==48.0.1/' "$work/requirements.txt"
fi
uv pip install --quiet --target "$site_packages" --python-platform "$python_triple" --python-version 3.13 --only-binary :all: \
    --requirement "$work/requirements.txt" "$work"/wheel/*.whl
bundled_cli=$site_packages/claude_agent_sdk/_bundled
[[ -e $bundled_cli ]] && trash "$bundled_cli"
[[ ! -e $bundled_cli ]] || { echo "ERROR: the Claude CLI of claude-agent-sdk is still in the bundle"; exit 1; }
codex_package=$site_packages/codex_cli_bin
[[ -d $codex_package ]] || { echo "ERROR: codex_cli_bin is missing from the app's packages"; exit 1; }
for codex_binaries in "$codex_package/bin" "$codex_package/codex-path"; do
    if [[ -e $codex_binaries ]]; then trash "$codex_binaries"; fi
done
codex_programs=$(find "$codex_package" -type f -exec file {} + | grep 'Mach-O' || true)
[[ -z $codex_programs ]] || { echo "ERROR: codex_cli_bin still carries programs: $codex_programs"; exit 1; }
[[ -e $site_packages/bin ]] && trash "$site_packages/bin"

echo "==> The interface"
(cd "$repo/frontend" && npm ci --no-audit --no-fund --silent && npm run build --silent)
project=$resources/project
mkdir -p "$project/frontend" "$project/scripts" "$project/docs/images"
cp -R "$repo/frontend/dist" "$project/frontend/dist"
cp "$repo/pyproject.toml" "$repo/CHANGELOG.md" "$project/"
cp "$repo/scripts/update_status_server.py" "$project/scripts/"
cp -R "$repo/docs/images/changelog" "$project/docs/images/changelog"
printf '{"arch": "%s", "version": "%s"}\n' "$arch" "$version" > "$project/bundle.json"
if [[ $version != $(sed -nE 's/^version = "(.+)"$/\1/p' "$repo/pyproject.toml" | head -1) ]]; then
    # A test build under another version: the server reports the version of its package metadata.
    sed -i '' -E "s/^version = \".+\"$/version = \"$version\"/" "$project/pyproject.toml"
    sed -i '' -E "s/^Version: .+$/Version: $version/" "$site_packages"/where_to_go-*.dist-info/METADATA
fi

echo "==> Bytecode, so the bundle never writes into itself"
uv run --no-project --python 3.13 python -m compileall -q -j 0 --invalidation-mode unchecked-hash "$resources/python/lib/python3.13" >/dev/null

echo "==> The window"
swift build --package-path "$repo/macos" -c release --arch "$arch" --product WhatToDo
cp "$(swift build --package-path "$repo/macos" -c release --arch "$arch" --show-bin-path)/WhatToDo" "$bundle/Contents/MacOS/$app_name"
plist=$bundle/Contents/Info.plist
cp "$repo/macos/Resources/Info.plist" "$plist"
for key in CFBundleName CFBundleDisplayName CFBundleExecutable; do
    plutil -replace $key -string "$app_name" "$plist"
done
plutil -replace CFBundleIdentifier -string "$bundle_id" "$plist"
plutil -replace CFBundleShortVersionString -string "$version" "$plist"
plutil -replace CFBundleVersion -string "$version" "$plist"
plutil -remove WTGProjectDir "$plist"
plutil -replace WTGBundled -bool YES "$plist"
plutil -replace WTGPort -string 48765 "$plist"
# Every update replaces the bundle, so the running window offers to restart into the new one.
plutil -replace WTGMacosTree -string "$version" "$plist"
plutil -lint -s "$plist"
iconset=$work/AppIcon.iconset
mkdir -p "$iconset"
for size in 16 32 128 256 512; do
    sips -z $size $size "$repo/macos/Resources/AppIcon.png" --out "$iconset/icon_${size}x${size}.png" >/dev/null
    sips -z $((size * 2)) $((size * 2)) "$repo/macos/Resources/AppIcon.png" --out "$iconset/icon_${size}x${size}@2x.png" >/dev/null
done
iconutil -c icns "$iconset" -o "$resources/AppIcon.icns"

echo "==> Signing ad hoc (no Apple Developer ID): every program inside, then the bundle"
find "$resources" -type f \( -perm -u+x -o -name '*.so' -o -name '*.dylib' \) -print0 | while IFS= read -r -d '' file; do
    [[ $(file -b "$file") == Mach-O* ]] || continue
    codesign --force --sign - "$file" 2>/dev/null
done
codesign --force --sign - "$bundle"
codesign --verify --strict "$bundle"

echo "==> Disk image"
[[ -e $dmg ]] && trash "$dmg"
uvx --from 'dmgbuild==2.0.0' dmgbuild -s "$repo/macos/dmg/settings.py" \
    -D app="$bundle" -D background="$repo/macos/dmg/background.png" -D icon="$resources/AppIcon.icns" \
    "$app_name" "$dmg"
echo "Built $dmg ($(du -h "$dmg" | cut -f1))"
