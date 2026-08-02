#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

if [[ "$(uname)" != "Darwin" ]]; then
  echo "This builds a macOS .app and has to run on the Mac."
  exit 1
fi

if [ -z "${CI:-}" ]; then
  if [ ! -d .venv ]; then
    echo "Creating virtualenv..."
    python3 -m venv .venv
  fi
  source .venv/bin/activate
fi

python -m pip install --quiet --upgrade pip
python -m pip install --quiet PySide6 pyinstaller pillow

# icon-app.png is bundled as a PyInstaller data file, so both must exist or
# packaging fails late with a confusing error.
if [ ! -f icon.icns ] || [ ! -f icon-app.png ]; then
  echo "Generating icon..."
  python make_icon.py
fi

APP="dist/Wallpaper Filer.app"
rm -rf build "$APP"
pyinstaller --noconfirm wallpaper-filer.spec

# Order below is deliberate and fragile if rearranged:
#   1. clear quarantine and stray xattrs  (this also wipes any custom-icon flag)
#   2. stamp the custom icon              (writes Icon^M + sets the Finder flag)
#   3. sign                               (seals the bundle including step 2)
# Signing before step 2 leaves an invalid signature and the app won't launch
# on Apple Silicon.

xattr -cr "$APP" 2>/dev/null || true

echo "Stamping custom icon so macOS 26 skips the squircle plate..."
ICON_PATH="$(cd "$(dirname icon.icns)" && pwd)/icon.icns"
APP_PATH="$(cd "$(dirname "$APP")" && pwd)/$(basename "$APP")"
osascript -l JavaScript \
  -e 'ObjC.import("AppKit");' \
  -e 'var args = $.NSProcessInfo.processInfo.arguments;' \
  -e 'var icon = ObjC.unwrap(args.objectAtIndex(4));' \
  -e 'var target = ObjC.unwrap(args.objectAtIndex(5));' \
  -e 'var img = $.NSImage.alloc.initWithContentsOfFile(icon);' \
  -e 'var ok = $.NSWorkspace.sharedWorkspace.setIconForFileOptions(img, target, 0);' \
  -e 'if (!ok) { throw new Error("could not set icon"); }' \
  "$ICON_PATH" "$APP_PATH"

codesign --force --deep --sign - "$APP"

if codesign --verify --deep --strict "$APP" 2>/dev/null; then
  echo "Signature verified."
else
  echo "WARNING: signature did not verify. The app may refuse to launch."
fi

echo
echo "Built: $APP"
echo "Install with:  cp -R '$APP' /Applications/"
