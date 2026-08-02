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

if [ ! -f icon.icns ] || [ ! -f icon-app.png ]; then
  echo "Generating icon..."
  python make_icon.py
fi

APP="dist/Wallpaper Filer.app"
rm -rf build "$APP"
pyinstaller --noconfirm wallpaper-filer.spec

# ---------------------------------------------------------------------------
# Icon, two ways.
#
# PREFERRED (native): if AppIcon.icon exists (made in Apple's Icon Composer)
# and actool is available (ships with full Xcode), compile it into Assets.car
# and point CFBundleIconName at it. macOS 26 then renders the icon itself --
# Dock, Spotlight, Finder all correct, at the same size as every other app,
# with no measuring or stamping on our side. CFBundleIconFile keeps serving
# the .icns to macOS 15 and earlier.
#
# FALLBACK (stamped): without AppIcon.icon or Xcode, assign the .icns as a
# Finder custom icon after signing. Escapes Tahoe's grey squircle plate but
# renders the artwork content-fit to the Dock slot (slightly oversized next
# to native icons).
#
# The deployment target for actool is 26.0 on purpose: with a lower target,
# actool emits flat legacy renders instead of the icon stack Tahoe
# recognises, and macOS then displays the raw square artwork with no mask,
# no glass, at full Dock-slot size. Older macOS is unaffected -- it reads
# CFBundleIconFile (the .icns) and never looks at Assets.car here.
#
# The native branch runs BEFORE signing: Assets.car lives inside Contents/
# and must be part of the sealed bundle. The stamp runs AFTER signing:
# codesign strips the FinderInfo attribute the stamp depends on.
# ---------------------------------------------------------------------------

NATIVE_ICON=0
if [ -e "AppIcon.icon" ]; then
  if xcrun --find actool >/dev/null 2>&1; then
    echo "Compiling native Tahoe icon (Assets.car)..."
    PARTIAL="$(mktemp -t actool-partial).plist"
    if xcrun actool "AppIcon.icon" \
        --compile "$APP/Contents/Resources" \
        --app-icon AppIcon \
        --include-all-app-icons \
        --enable-on-demand-resources NO \
        --development-region en \
        --target-device mac \
        --platform macosx \
        --minimum-deployment-target 26.0 \
        --output-format human-readable-text --notices --warnings --errors \
        --output-partial-info-plist "$PARTIAL" \
        && [ -f "$APP/Contents/Resources/Assets.car" ]; then
      # actool's partial plist states the exact CFBundleIconName the catalog
      # was built around. Use ITS value -- hardcoding the name risks pointing
      # macOS at a flat layer image inside the catalog instead of the icon
      # stack, which displays as an unmasked square.
      ICON_NAME="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIconName' \
        "$PARTIAL" 2>/dev/null || true)"
      if [ -z "$ICON_NAME" ]; then
        ICON_NAME="AppIcon"
        echo "NOTE: actool's partial plist had no CFBundleIconName; using AppIcon."
      else
        echo "actool says CFBundleIconName = $ICON_NAME"
      fi
      /usr/libexec/PlistBuddy -c "Delete :CFBundleIconName" \
        "$APP/Contents/Info.plist" 2>/dev/null || true
      /usr/libexec/PlistBuddy -c "Add :CFBundleIconName string $ICON_NAME" \
        "$APP/Contents/Info.plist"
      NATIVE_ICON=1
      echo "Native icon compiled. macOS renders it itself from here."
    else
      echo "WARNING: actool failed; falling back to the stamped legacy icon."
      echo "         Make sure full Xcode 26 (with the macOS 26 SDK) is installed"
      echo "         and selected: xcodebuild -version should report Xcode 26.x."
    fi
    rm -f "$PARTIAL"
  else
    echo "NOTE: AppIcon.icon is present but actool was not found."
    echo "      actool ships with full Xcode (not the Command Line Tools):"
    echo "        1. Install Xcode from the App Store"
    echo "        2. sudo xcode-select -s /Applications/Xcode.app/Contents/Developer"
    echo "        3. sudo xcodebuild -license accept"
    echo "      Falling back to the stamped legacy icon for this build."
  fi
fi

xattr -cr "$APP" 2>/dev/null || true
codesign --force --deep --sign - "$APP"
if codesign --verify "$APP" 2>/dev/null; then
  echo "Signature valid."
else
  echo "WARNING: signature did not verify. The app may refuse to launch."
fi

STAMPED=0
if [ "$NATIVE_ICON" = "1" ]; then
  echo "Skipping the Finder icon stamp: the native icon replaces it, and a"
  echo "stamped custom icon would override the system-rendered one."
else
  echo "Stamping custom icon so macOS 26 skips the squircle plate..."
  ICON_PATH="$(cd "$(dirname icon.icns)" && pwd)/icon.icns"
  APP_PATH="$(cd "$(dirname "$APP")" && pwd)/$(basename "$APP")"
  # Verbatim stamp (preserves the 824-grid margins, so the Dock size matches
  # native icons). If it fails, the setIconForFile fallback is announced
  # LOUDLY, because that path re-renders the image and displays oversized --
  # a failure that must never masquerade as success.
  if ./stamp_icon.sh "$ICON_PATH" "$APP_PATH" && [ -f "$APP"/$'Icon\r' ]; then
    STAMPED=1
    echo "Icon stamped (verbatim)."
  else
    echo
    echo "WARNING: the verbatim stamp FAILED. Falling back to setIconForFile,"
    echo "         which re-renders the image: the icon will show rounded but"
    echo "         OVERSIZED in the Dock. Fine for testing, wrong to ship."
    echo
    if osascript -l JavaScript stamp_icon.js "$ICON_PATH" "$APP_PATH" \
       && [ -f "$APP"/$'Icon\r' ]; then
      STAMPED=2
    else
      echo "WARNING: the fallback stamp also failed; macOS will use the grey plate."
    fi
  fi
  # The stamp writes Icon^M at the bundle root, which strict verification
  # flags as unsealed content. Expected; the launch-relevant signature above
  # is what matters.
fi

echo
if [ "$NATIVE_ICON" = "1" ]; then
  echo "Built: $APP  (native Tahoe icon)"
elif [ "$STAMPED" = "1" ]; then
  echo "Built: $APP  (stamped legacy icon, verbatim -- correct Dock size)"
elif [ "$STAMPED" = "2" ]; then
  echo "Built: $APP  (FALLBACK stamp -- icon will render OVERSIZED; fix"
  echo "stamp_icon.sh before shipping this build)"
else
  echo "Built: $APP  (no custom icon -- see warnings above)"
fi
echo "Install with:  rm -rf '/Applications/Wallpaper Filer.app' && cp -R '$APP' /Applications/"
