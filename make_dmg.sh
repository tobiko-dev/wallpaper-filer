#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

VERSION="${1:-1.0.0}"
APP="dist/Wallpaper Filer.app"
DMG="dist/WallpaperFiler-${VERSION}-arm64.dmg"
VOLNAME="Wallpaper Filer"

if [[ "$(uname)" != "Darwin" ]]; then
  echo "DMGs can only be made on macOS."
  exit 1
fi

if [ ! -d "$APP" ]; then
  echo "No app bundle found. Run ./build.sh first."
  exit 1
fi

if [ ! -f "$APP"/$'Icon\r' ] && [ ! -f "$APP/Contents/Resources/Assets.car" ]; then
  echo "WARNING: the app has neither a stamped icon nor a native Assets.car."
  echo "         Re-run ./build.sh."
fi

ICON_PATH="$(cd "$(dirname icon.icns)" && pwd)/icon.icns"
STAGE="$(mktemp -d)"
RW_DMG="$(mktemp -u).dmg"
MOUNT=""

cleanup() {
  if [ -n "$MOUNT" ] && [ -d "$MOUNT" ]; then
    hdiutil detach "$MOUNT" -quiet 2>/dev/null || true
  fi
  rm -rf "$STAGE" "$RW_DMG"
}
trap cleanup EXIT

# ditto rather than cp: the custom icon lives in a resource fork plus a Finder
# attribute, and a plain copy drops both without complaining.
ditto --rsrc --extattr "$APP" "$STAGE/$(basename "$APP")"
ln -s /Applications "$STAGE/Applications"

# A volume shows a custom icon only when .VolumeIcon.icns sits at its root AND
# the volume carries the custom-icon flag -- hence the read/write pass below.
cp icon.icns "$STAGE/.VolumeIcon.icns"

echo "Creating writable image..."
hdiutil create \
  -volname "$VOLNAME" \
  -srcfolder "$STAGE" \
  -fs HFS+ \
  -format UDRW -ov \
  "$RW_DMG" >/dev/null

echo "Stamping volume icon..."
MOUNT="$(hdiutil attach "$RW_DMG" -nobrowse -noverify -readwrite | tail -1 | cut -f3-)"
if [ -n "$MOUNT" ] && [ -d "$MOUNT" ]; then
  osascript -l JavaScript stamp_icon.js "$ICON_PATH" "$MOUNT" >/dev/null \
    || echo "WARNING: could not stamp the volume icon."
  hdiutil detach "$MOUNT" -quiet
  MOUNT=""
else
  echo "WARNING: could not mount the writable image; volume icon skipped."
fi

echo "Compressing..."
rm -f "$DMG"
hdiutil convert "$RW_DMG" -format UDZO -o "$DMG" >/dev/null

echo "Stamping the .dmg file icon..."
osascript -l JavaScript stamp_icon.js "$ICON_PATH" "$(cd "$(dirname "$DMG")" && pwd)/$(basename "$DMG")" >/dev/null \
  || echo "WARNING: could not stamp the .dmg file icon."

echo
echo "Built: $DMG"
echo "Size:  $(du -h "$DMG" | cut -f1)"
