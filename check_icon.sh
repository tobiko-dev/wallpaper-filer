#!/bin/bash
# Diagnose how an app's icon is wired and whether it will display correctly.
#   ./check_icon.sh "/Applications/Wallpaper Filer.app"

TARGET="${1:-/Applications/Wallpaper Filer.app}"

if [ ! -e "$TARGET" ]; then
  echo "Not found: $TARGET"
  exit 1
fi

echo "Target: $TARGET"
echo

ICON_NAME="$(/usr/libexec/PlistBuddy -c "Print :CFBundleIconName" \
  "$TARGET/Contents/Info.plist" 2>/dev/null || true)"

if [ -f "$TARGET/Contents/Resources/Assets.car" ] && [ -n "$ICON_NAME" ]; then
  echo "  Mode: NATIVE Tahoe icon (system-rendered)"
  echo "  [ok]   Assets.car present in Contents/Resources"
  echo "  [ok]   CFBundleIconName = $ICON_NAME"
  if [ -f "$TARGET"/$'Icon\r' ]; then
    echo "  [warn] a Finder icon stamp is ALSO present -- it overrides the"
    echo "         native icon. Remove it: select the app, Cmd+I, click the"
    echo "         small top-left icon, press Delete."
  else
    echo "  [ok]   no leftover Finder stamp"
  fi
else
  echo "  Mode: STAMPED legacy icon"
  if [ -f "$TARGET"/$'Icon\r' ]; then
    echo "  [ok]   Icon^M file present"
  else
    echo "  [FAIL] no Icon^M file -- the stamp never ran, or was wiped"
  fi
  if xattr "$TARGET" 2>/dev/null | grep -q "com.apple.FinderInfo"; then
    echo "  [ok]   FinderInfo attribute present (carries the custom-icon flag)"
  else
    echo "  [FAIL] no FinderInfo attribute -- codesign or a plain cp stripped it"
  fi
fi

if codesign --verify "$TARGET" 2>/dev/null; then
  echo "  [ok]   signature valid -- app will launch"
else
  echo "  [FAIL] signature invalid -- app will not launch on Apple Silicon"
fi

if codesign --verify --deep --strict "$TARGET" 2>/dev/null; then
  echo "  [ok]   strict verification passes"
else
  echo "  [info] strict verification flags unsealed content (the stamped Icon"
  echo "         file, when present). Expected in stamped mode; harmless."
fi

echo
echo "The real test is launching it. If it opens and the icon looks right,"
echo "you're done."
