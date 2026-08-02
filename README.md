# Wallpaper filer
<img width="180" height="180" alt="icon-app" src="https://github.com/user-attachments/assets/b191bc47-4a20-48a2-81d1-08dc737c09af" />

Drop images in, pick a show, get `show-name_007.jpg`. Built for macOS.

<img width="415" height="415" alt="image" src="https://github.com/user-attachments/assets/4619a0dd-fb1e-46f0-a49b-b4b34960e79e" />

The folder is the database. Show names are derived by scanning filenames, so
there's no index file to keep in sync — if you rename or delete things in
Finder, the app just agrees with you on the next scan.

### Before ...
<img width="750" height="417" alt="image" src="https://github.com/user-attachments/assets/d76fcaf1-e52d-4e4d-8d9e-f7af21a04a0b" />
<img width="415" height="415" alt="image" src="https://github.com/user-attachments/assets/3bcdfef8-6bc6-4cf7-ba19-4b99d891ab20" />


### After!
<img width="754" height="412" alt="image" src="https://github.com/user-attachments/assets/3a574e0a-7f80-4799-8b89-826024d82c95" />


## Setup

```bash
cd wallpaper-filer
python3 -m venv .venv
source .venv/bin/activate
pip install PySide6
python3 app.py
```

Needs Python 3.10+. On Apple Silicon, PySide6 ships native arm64 wheels, so
there's nothing to compile.

To launch it without the terminal, make `run.command` executable and
double-click it:

```bash
chmod +x run.command
```

## Using it

Set the target folder once (top right, "Change") — it's remembered between
launches. Type a show name; existing shows autocomplete, and anything new
starts at `_001`. Drop files anywhere on the window, check the preview, hit
"Add to folder".

- **Move files** (on by default) takes the originals out of Downloads. Turn it
  off to copy instead.
- **Undo last** reverses the most recent batch — the one you want after
  realising you filed 12 images under the wrong show.
- Duplicates are caught by content hash, not filename, so re-downloading the
  same Wallhaven image is a no-op.

## Numbering

Numbers only ever go up. Delete `frieren_004` and the next file is still
`frieren_015`, not `004` — a filename never changes once it's assigned, which
is what keeps duplicate detection honest.

When the drift starts to bother you, close the gaps deliberately:

```bash
python3 compact.py ~/Pictures/anime-wallpapers frieren          # preview
python3 compact.py ~/Pictures/anime-wallpapers frieren --apply
```

## Wiring it to the desktop

System Settings → Wallpaper → Add Folder → pick the same folder. Set
"Change picture" to hourly or on wake. For the screen saver: Screen Saver →
Custom → scroll to Other → Photos → Options → Choose Folder.

## Files

| File | What it does |
|---|---|
| `core.py` | Scanning, normalising, numbering, dedup, undo, compaction. No GUI imports — testable on its own. |
| `app.py` | The window. |
| `compact.py` | Gap-closing CLI. |

Two dotfiles get written into your wallpaper folder: `.wallpaper-filer-cache.json`
(hash cache, safe to delete) and `.wallpaper-filer-undo.json` (last batch).

## Building a real .app

```bash
./build.sh
cp -R "dist/Wallpaper Filer.app" /Applications/
```

Produces `dist/Wallpaper Filer.app` — double-clickable, shows in Spotlight and
the Dock, keeps its own icon. The build script installs PyInstaller into the
venv, generates `icon.icns` if it's missing, and ad-hoc signs the bundle
(required on Apple Silicon — an unsigned arm64 binary won't launch at all).

Expect roughly 150–250 MB. Qt is large and PyInstaller bundles a whole Python
runtime; the spec already drops the Qt modules this app never touches.

To change the icon, edit `make_icon.py`, delete `icon.icns`, and rebuild.

### Rebuilding after code changes

`./build.sh` again. There's no incremental build — it's a fresh bundle each
time, about a minute.

## Shipping a DMG

```bash
./build.sh
./make_dmg.sh 1.0.0
```

Produces `dist/WallpaperFiler-1.0.0-arm64.dmg` — a disk image with the app and
an `/Applications` shortcut, so opening it gives the familiar drag-across
install window.

Tagging a release builds and attaches the DMG automatically:

```bash
git tag v1.0.0 && git push origin v1.0.0
```

The workflow in `.github/workflows/release.yml` runs on a macOS arm64 runner,
builds, packages, and uploads the DMG to the GitHub release.

### The icon, and why the build does something odd

macOS 26 puts legacy `.icns` icons in a grey "squircle plate" and shrinks the
artwork inside it. Assigning the icon through Finder's Get Info panel makes
macOS respect the real shape instead -- and that assignment lives in the
bundle, so `build.sh` performs it for you and it survives into the DMG.

Three ordering constraints make this work, and rearranging them breaks it:

1. `xattr -cr` runs first, because it wipes the custom-icon flag.
2. The icon is stamped second, writing an `Icon^M` file plus a Finder flag.
3. Signing runs last, sealing the bundle *including* the stamp. Signing before
   the stamp leaves an invalid signature and the app won't launch on Apple
   Silicon at all.

`make_dmg.sh` then uses `ditto --rsrc --extattr` and an HFS+ image, both of
which are needed to carry the resource fork and Finder flag through. A plain
`cp` or an APFS image can silently drop them and the icon reverts.

This is a workaround for a legacy format. The supported fix is Apple's `.icon`
format, made in Icon Composer (ships with Xcode 26) and dropped into
`Contents/Resources`. PyInstaller can't generate one. If a future macOS breaks
the Finder-assignment trick, that's the path.

### What downloaders will hit

The build is **unsigned and un-notarized**, so Gatekeeper blocks it on first
launch with a message about the app not being verified. The old right-click →
Open trick no longer works on current macOS. The actual path is:

> System Settings → Privacy & Security → scroll to Security → "Open Anyway"

Put that in your release notes verbatim or people will assume it's broken.

Removing that friction means joining the Apple Developer Program ($99/year),
signing with a Developer ID certificate, and notarizing through Apple. That's
the only way to get a clean double-click install for other people.

The DMG is **Apple Silicon only**. Intel Macs won't run it. Universal binaries
are possible (PySide6 ships universal2 wheels) but need a universal2 Python
interpreter from python.org — Homebrew's is single-arch.

## Native Tahoe icon (the proper fix)

The stamped icon escapes macOS 26's grey plate but renders slightly oversized:
the Dock crops a stamped icon to its visible content and fits THAT to the
tile, so baked-in margins are ignored. Native icons don't have this problem
because the system draws them itself.

One-time setup:

1. Download **Icon Composer** (free from Apple, runs on Sequoia+).
2. Install **Xcode** from the App Store (actool, the compiler this needs,
   ships only with full Xcode), then:
   `sudo xcode-select -s /Applications/Xcode.app/Contents/Developer`
   `sudo xcodebuild -license accept`
3. Regenerate icons — `make_icon.py` now also writes `icon-native.png`,
   a full-bleed square with no corners and no margins.
4. In Icon Composer: new macOS icon, drag `icon-native.png` in, save as
   **`AppIcon.icon`** in the project root (the filename matters — it becomes
   the asset name the build wires up).
5. `./build.sh` — it detects `AppIcon.icon` automatically, compiles it with
   actool into `Assets.car`, and sets `CFBundleIconName`. The Finder stamp is
   skipped in this mode (it would override the native icon).

Without `AppIcon.icon` or Xcode, the build falls back to the stamped icon and
keeps working. `CFBundleIconFile` continues to point at `icon.icns` either
way, which is what macOS 15 and earlier read. The DMG volume icon also still
uses the `.icns` — that part of `make_dmg.sh` is unchanged.

Note: the stamped icon is applied verbatim via `stamp_icon.sh` (Rez/SetFile),
which preserves the 824-grid margins so the Dock size matches native icons.
`stamp_icon.js` (setIconForFile) re-renders the image and loses the margins;
it remains only as a fallback and for the DMG volume icon.
