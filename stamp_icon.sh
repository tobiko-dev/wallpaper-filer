#!/bin/bash
# Verbatim icon stamp -- byte-for-byte what Finder's Get Info drag does.
# Uses the canonical recipe (sips -i -> DeRez -> Rez -append): the icns is
# injected into a resource fork, lifted out as resource source, and appended
# into the bundle's Icon^M file. Nothing is re-rendered, so the icon's
# built-in 824-grid margins survive and the Dock displays it at the same
# size as native icons.
#
#   ./stamp_icon.sh <icon.icns> <target .app>
set -euo pipefail

ICNS="$1"
TARGET="$2"

for tool in Rez DeRez SetFile; do
  if ! xcrun --find "$tool" >/dev/null 2>&1; then
    echo "stamp_icon.sh: $tool not found (needs Xcode command line tools)" >&2
    exit 1
  fi
done

[ -f "$ICNS" ]   || { echo "stamp_icon.sh: no such icon: $ICNS" >&2; exit 1; }
[ -d "$TARGET" ] || { echo "stamp_icon.sh: no such app: $TARGET" >&2; exit 1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Work on a copy: sips -i mutates the file it touches, and the project's
# icon.icns should stay pristine.
cp "$ICNS" "$TMP/icon.icns"
sips -i "$TMP/icon.icns" >/dev/null

xcrun DeRez -only icns "$TMP/icon.icns" > "$TMP/icon.rsrc"
[ -s "$TMP/icon.rsrc" ] || { echo "stamp_icon.sh: DeRez produced no resource" >&2; exit 1; }

ICONFILE="$TARGET/"$'Icon\r'
rm -f "$ICONFILE"
touch "$ICONFILE"
xcrun Rez -append "$TMP/icon.rsrc" -o "$ICONFILE"

# The stamp only works if the resource fork actually has the icon in it.
[ -s "$ICONFILE/..namedfork/rsrc" ] || {
  echo "stamp_icon.sh: Icon file has an empty resource fork" >&2
  exit 1
}

xcrun SetFile -a C "$TARGET"
xcrun SetFile -a V "$ICONFILE"

echo "verbatim-stamped $TARGET"
