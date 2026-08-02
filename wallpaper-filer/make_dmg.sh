#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

VERSION="${1:-1.0.0}"
APP="dist/Wallpaper Filer.app"
DMG="dist/WallpaperFiler-${VERSION}-arm64.dmg"

if [[ "$(uname)" != "Darwin" ]]; then
  echo "DMGs can only be made on macOS."
  exit 1
fi

if [ ! -d "$APP" ]; then
  echo "No app bundle found. Run ./build.sh first."
  exit 1
fi

# The custom icon lives in an Icon^M file plus a Finder flag on the bundle.
# HFS+ is specified because it carries resource forks reliably; ditto is used
# instead of cp because it preserves both. Get either wrong and the icon
# reverts to the grey squircle plate on the user's machine.
if [ ! -f "$APP"/$'Icon\r' ]; then
  echo "WARNING: no custom icon stamp found. Re-run ./build.sh."
fi

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

ditto --rsrc --extattr "$APP" "$STAGE/$(basename "$APP")"
ln -s /Applications "$STAGE/Applications"

rm -f "$DMG"
hdiutil create \
  -volname "Wallpaper Filer" \
  -srcfolder "$STAGE" \
  -fs HFS+ \
  -ov -format UDZO \
  "$DMG"

echo
echo "Built: $DMG"
echo "Size:  $(du -h "$DMG" | cut -f1)"
