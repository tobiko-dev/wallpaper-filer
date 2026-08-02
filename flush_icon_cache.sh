#!/bin/bash
# Flush every cache macOS uses to render app icons, then restart what draws
# them. These are derived caches -- rendered thumbnails, no originals, no user
# data -- and macOS rebuilds them automatically. Safe to run repeatedly.
set -uo pipefail

APP="/Applications/Wallpaper Filer.app"

echo "This will:"
echo "  1. delete the system icon cache        (asks for your password)"
echo "  2. delete your user-level icon caches"
echo "  3. re-register the app with LaunchServices (feeds Spotlight)"
echo "  4. restart Dock and Finder"
echo
read -r -p "Continue? [y/N] " answer
[ "$answer" = "y" ] || [ "$answer" = "Y" ] || exit 0

sudo rm -rf /Library/Caches/com.apple.iconservices.store
rm -rf ~/Library/Caches/com.apple.iconservices* 2>/dev/null

LSREGISTER="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
if [ -x "$LSREGISTER" ] && [ -d "$APP" ]; then
  "$LSREGISTER" -f "$APP"
fi

# Bump the modification time so icon services treats its next look as fresh.
[ -d "$APP" ] && sudo touch "$APP"

sudo killall iconservicesd iconservicesagent 2>/dev/null
killall Dock Finder 2>/dev/null

echo
echo "Done. Now:"
echo "  - If the app is pinned to the Dock, drag it OFF and re-add it from"
echo "    /Applications. The Dock keeps its own copy of pinned tiles."
echo "  - If Spotlight still shows an old icon, log out and back in once;"
echo "    the last layer of this cache lives in memory."
