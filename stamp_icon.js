// Assigns a custom icon to any path -- an .app bundle, a .dmg file, or a
// mounted volume. This is the scripted equivalent of dragging an .icns onto
// the thumbnail in Finder's Get Info panel, which is what makes macOS 26
// respect the artwork's own shape instead of drawing it inside the grey
// squircle plate.
//
//   osascript -l JavaScript stamp_icon.js <icon.icns> <target path>
//
// Paths are read from the END of the argument list: NSProcessInfo.arguments
// also contains osascript's own flags, so absolute indices are not stable.

ObjC.import("AppKit");

function run() {
  var args = $.NSProcessInfo.processInfo.arguments;
  var n = args.count;

  if (n < 2) {
    throw new Error("usage: stamp_icon.js <icon.icns> <target>");
  }

  var iconPath = ObjC.unwrap(args.objectAtIndex(n - 2));
  var targetPath = ObjC.unwrap(args.objectAtIndex(n - 1));

  var fm = $.NSFileManager.defaultManager;
  if (!fm.fileExistsAtPath(iconPath)) {
    throw new Error("icon not found: " + iconPath);
  }
  if (!fm.fileExistsAtPath(targetPath)) {
    throw new Error("target not found: " + targetPath);
  }

  var image = $.NSImage.alloc.initWithContentsOfFile(iconPath);
  if (!image || image.isNil()) {
    throw new Error("could not read image: " + iconPath);
  }

  if (!$.NSWorkspace.sharedWorkspace.setIconForFileOptions(image, targetPath, 0)) {
    throw new Error("refused to set icon; check write permission on " + targetPath);
  }

  return "stamped " + targetPath;
}
