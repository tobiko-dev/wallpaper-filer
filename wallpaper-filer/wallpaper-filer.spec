# PyInstaller spec for the macOS app bundle.
#     pyinstaller --noconfirm wallpaper-filer.spec

block_cipher = None

EXCLUDES = [
    "PySide6.Qt3DAnimation", "PySide6.Qt3DCore", "PySide6.Qt3DExtras",
    "PySide6.Qt3DInput", "PySide6.Qt3DLogic", "PySide6.Qt3DRender",
    "PySide6.QtBluetooth", "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "PySide6.QtHelp", "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets",
    "PySide6.QtNfc", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets",
    "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtPositioning",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuick3D",
    "PySide6.QtQuickControls2", "PySide6.QtQuickWidgets", "PySide6.QtRemoteObjects",
    "PySide6.QtScxml", "PySide6.QtSensors", "PySide6.QtSerialPort",
    "PySide6.QtSpatialAudio", "PySide6.QtSql", "PySide6.QtStateMachine",
    "PySide6.QtTest", "PySide6.QtTextToSpeech", "PySide6.QtWebChannel",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebSockets",
    "matplotlib", "numpy", "pandas", "scipy", "tkinter", "PIL",
]

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=[],
    datas=[("icon-app.png", ".")],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=EXCLUDES,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Wallpaper Filer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Wallpaper Filer",
)

app = BUNDLE(
    coll,
    name="Wallpaper Filer.app",
    icon="icon.icns",
    bundle_identifier="dev.tobiko.wallpaperfiler",
    version="1.0.0",
    info_plist={
        "CFBundleName": "Wallpaper Filer",
        "CFBundleDisplayName": "Wallpaper Filer",
        "CFBundleShortVersionString": "1.0.0",
        "CFBundleVersion": "1.0.0",
        "LSMinimumSystemVersion": "12.0",
        "NSHighResolutionCapable": True,
        "NSRequiresAquaSystemAppearance": False,
        "LSApplicationCategoryType": "public.app-category.utilities",
        "NSDownloadsFolderUsageDescription":
            "Wallpaper Filer reads the images you drop in from your Downloads folder.",
        "NSDesktopFolderUsageDescription":
            "Wallpaper Filer reads the images you drop in from your Desktop.",
        "NSDocumentsFolderUsageDescription":
            "Wallpaper Filer reads the images you drop in from your Documents folder.",
        "CFBundleDocumentTypes": [
            {
                "CFBundleTypeName": "Image",
                "CFBundleTypeRole": "Editor",
                "LSItemContentTypes": ["public.image"],
                "LSHandlerRank": "Alternate",
            }
        ],
    },
)
