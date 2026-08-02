"""Wallpaper filer -- drop images, pick a show, get consistent filenames.

Run with:  python3 app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QEvent, QSettings, QStringListModel, QTimer
from PySide6.QtGui import QAction, QIcon, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QCompleter, QFileDialog, QFrame,
    QHBoxLayout, QHeaderView, QLabel, QMainWindow, QMessageBox, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

import core

ORG = "tobiko-dev"
APP = "wallpaper-filer"


def resource_path(name: str) -> str:
    """Locate a bundled file, whether running from source or from the .app.

    PyInstaller unpacks data files into a temp dir it advertises as
    sys._MEIPASS; from source they sit next to this script.
    """
    base = getattr(sys, "_MEIPASS", None)
    return str((Path(base) if base else Path(__file__).resolve().parent) / name)


def app_pixmap(size: int = 96) -> QPixmap:
    """The slime, scaled. Dialogs use this instead of the bundle icon, which
    macOS 26 draws inside its grey squircle plate."""
    pixmap = QPixmap(resource_path("icon-app.png"))
    if pixmap.isNull():
        return pixmap
    return pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)


class DropZone(QFrame):
    """Dashed rectangle that accepts a file drop and reports it upward."""

    def __init__(self, on_files):
        super().__init__()
        self.on_files = on_files
        self.setAcceptDrops(True)
        self.setMinimumHeight(96)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(
            "Drop images here, or click to browse.\n"
            "Drop a folder and its files are pulled in.\n"
            "Nothing is written until you press Add to folder."
        )
        self._idle()

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        self.label = QLabel("Drop images here\nor click to browse")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("color: palette(mid); border: none;")
        layout.addWidget(self.label)

    def _idle(self):
        self.setStyleSheet(
            "QFrame { border: 1px dashed palette(mid); border-radius: 8px; "
            "background: transparent; }"
        )

    def _active(self):
        self.setStyleSheet(
            "QFrame { border: 1px dashed palette(highlight); border-radius: 8px; "
            "background: palette(alternate-base); }"
        )

    def mousePressEvent(self, event):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Choose images", str(Path.home()),
            "Images (*.jpg *.jpeg *.png *.webp *.gif *.bmp *.tiff *.heic)",
        )
        if paths:
            self.on_files([Path(p) for p in paths])

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._active()

    def dragLeaveEvent(self, event):
        self._idle()

    def dropEvent(self, event):
        self._idle()
        paths = [
            Path(url.toLocalFile())
            for url in event.mimeData().urls()
            if url.isLocalFile()
        ]
        expanded: list[Path] = []
        for path in paths:
            if path.is_dir():
                expanded.extend(p for p in sorted(path.iterdir()) if p.is_file())
            else:
                expanded.append(path)
        if expanded:
            self.on_files(expanded)
        event.acceptProposedAction()


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings(ORG, APP)
        default = str(Path.home() / "Pictures" / "anime-wallpapers")
        self.folder = Path(self.settings.value("folder", default))
        self.queue: list[Path] = []
        self.library = core.scan(self.folder)
        self.planned: list[core.PlannedFile] = []

        self.setWindowTitle("Wallpaper Filer")
        icon = QIcon(resource_path("icon-app.png"))
        if not icon.isNull():
            self.setWindowIcon(icon)
        self.setAcceptDrops(True)
        self.resize(620, 620)
        self._build()
        self._refresh_shows()
        self._replan()
        self._refresh_undo_state()

    # ---------- layout ----------

    def _build(self):
        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(16, 14, 16, 14)
        outer.setSpacing(12)

        folder_row = QHBoxLayout()
        self.folder_label = QLabel()
        self.folder_label.setStyleSheet("color: palette(mid); font-family: Menlo, monospace;")
        self.folder_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        change = QPushButton("Change")
        change.setToolTip("Pick the folder images get filed into. Remembered between launches.")
        change.clicked.connect(self.choose_folder)
        reveal = QPushButton("Reveal")
        reveal.setToolTip("Open this folder in Finder")
        reveal.clicked.connect(self.reveal_folder)
        folder_row.addWidget(self.folder_label, 1)
        folder_row.addWidget(reveal)
        folder_row.addWidget(change)
        outer.addLayout(folder_row)

        show_row = QVBoxLayout()
        show_row.setSpacing(5)
        show_row.addWidget(QLabel("Show"))
        self.show_box = QComboBox()
        self.show_box.setEditable(True)
        self.show_box.setInsertPolicy(QComboBox.NoInsert)
        self.show_box.setMinimumHeight(30)
        self.show_box.lineEdit().setPlaceholderText("frieren")
        self.show_box.setToolTip(
            "Which show these images belong to.\n"
            "Existing shows autocomplete; anything new starts at 001.\n"
            "Punctuation and spaces are normalised, so "
            "\u201cFrieren: Beyond Journey\u2019s End\u201d becomes "
            "frieren-beyond-journeys-end."
        )
        self.completer_model = QStringListModel()
        completer = QCompleter(self.completer_model, self)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        self.show_box.setCompleter(completer)
        self.show_box.currentTextChanged.connect(self._replan)
        show_row.addWidget(self.show_box)
        self.show_hint = QLabel()
        self.show_hint.setStyleSheet("color: palette(mid); font-size: 11px;")
        show_row.addWidget(self.show_hint)
        outer.addLayout(show_row)

        self.zone = DropZone(self.add_files)
        outer.addWidget(self.zone)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Dropped", "", "New name"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setToolTip(
            "Preview only \u2014 what each file will be called once filed.\n"
            "Greyed rows are skipped: duplicates, or files that aren't images."
        )
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setColumnWidth(1, 24)
        outer.addWidget(self.table, 1)

        footer = QHBoxLayout()
        self.status = QLabel("Nothing queued")
        self.status.setStyleSheet("color: palette(mid);")
        self.move_box = QCheckBox("Move files")
        self.move_box.setChecked(self.settings.value("move", True, type=bool))
        self.move_box.setToolTip(
            "On: originals are moved out of Downloads.\n"
            "Off: originals stay put and copies are filed."
        )
        self.undo_button = undo = QPushButton("Undo last")
        undo.setToolTip(
            "Reverse the most recent batch.\n"
            "Moved files go back where they came from; copies are deleted.\n"
            "Use this after filing images under the wrong show."
        )
        undo.clicked.connect(self.undo)
        clear = QPushButton("Clear")
        clear.setToolTip("Empty the queue. Nothing on disk is touched.")
        clear.clicked.connect(self.clear_queue)
        self.commit = QPushButton("Add to folder")
        self.commit.setToolTip("Rename the queued images and file them (\u2318\u21A9)")
        self.commit.setDefault(True)
        self.commit.clicked.connect(self.apply_plan)
        self.status.setMinimumHeight(24)
        footer.addWidget(self.status, 1)
        footer.addWidget(self.move_box)
        footer.addWidget(undo)
        footer.addWidget(clear)
        footer.addWidget(self.commit)
        outer.addLayout(footer)

        self.setCentralWidget(root)

        for shortcut, slot in (
            (QKeySequence.Open, self.zone.mousePressEvent),
            (QKeySequence("Ctrl+Return"), self.apply_plan),
            (QKeySequence.Undo, self.undo),
        ):
            action = QAction(self)
            action.setShortcut(shortcut)
            action.triggered.connect(lambda _=False, s=slot: s(None) if s is self.zone.mousePressEvent else s())
            self.addAction(action)

    # ---------- window-level drop ----------

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        self.zone.dropEvent(event)

    def _flash(self, text: str, tone: str = "info") -> None:
        """Say something in the footer and make it briefly impossible to miss.

        A plain label change in the corner reads as nothing happening, so the
        message gets a coloured pill for a couple of seconds before settling
        back to the normal muted style.
        """
        colours = {
            "info": ("palette(highlight)", "palette(highlighted-text)"),
            "warn": ("#B8860B", "white"),
        }
        background, foreground = colours.get(tone, colours["info"])
        self.status.setText(text)
        self.status.setStyleSheet(
            f"background: {background}; color: {foreground};"
            "border-radius: 6px; padding: 3px 10px; font-weight: 600;"
        )
        QTimer.singleShot(2400, self._unflash)

    def _unflash(self) -> None:
        self.status.setStyleSheet("color: palette(mid);")

    def _refresh_undo_state(self) -> None:
        pending = core.can_undo(self.folder)
        self.undo_button.setEnabled(pending > 0)
        if pending:
            self.undo_button.setToolTip(
                f"Put the last {pending} file{'s' if pending != 1 else ''} back.\n"
                "Moved files return to where they came from; copies are deleted."
            )
        else:
            self.undo_button.setToolTip(
                "Nothing to undo \u2014 available right after you file a batch."
            )

    def _dialog(self, title: str, text: str) -> None:
        """One place for message boxes, so they all carry the real icon."""
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setText(text)
        pixmap = app_pixmap(72)
        if not pixmap.isNull():
            box.setIconPixmap(pixmap)
        else:
            box.setIcon(QMessageBox.Information)
        box.exec()

    # ---------- actions ----------

    def choose_folder(self):
        chosen = QFileDialog.getExistingDirectory(self, "Wallpaper folder", str(self.folder))
        if chosen:
            self.folder = Path(chosen)
            self.settings.setValue("folder", chosen)
            self.rescan()

    def reveal_folder(self):
        if self.folder.is_dir():
            import subprocess
            subprocess.run(["open", str(self.folder)], check=False)

    def add_files(self, paths):
        known = {p.resolve() for p in self.queue}
        for path in paths:
            if path.resolve() not in known:
                self.queue.append(path)
        self._replan()

    def clear_queue(self):
        self.queue.clear()
        self._replan()

    def rescan(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.library = core.scan(self.folder)
        finally:
            QApplication.restoreOverrideCursor()
        self._refresh_shows()
        self._replan()
        self._refresh_undo_state()

    def apply_plan(self):
        writable = [p for p in self.planned if p.will_write]
        if not writable:
            return
        move = self.move_box.isChecked()
        self.settings.setValue("move", move)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            count, errors = core.apply(self.planned, self.folder, move=move)
        finally:
            QApplication.restoreOverrideCursor()
        if errors:
            self._dialog("Some files were skipped", "\n".join(errors[:10]))
        self.queue.clear()
        self.rescan()
        self._flash(f"Added {count} file{'s' if count != 1 else ''}")

    def undo(self):
        reverted, errors = core.undo_last(self.folder)
        real_errors = [e for e in errors if e != "nothing to undo"]
        if real_errors:
            self._dialog("Undo", "\n".join(real_errors[:10]))
        self.rescan()
        if reverted:
            self._flash(f"Put {reverted} file{'s' if reverted != 1 else ''} back")
        elif not real_errors:
            self._flash("Nothing to undo", tone="warn")

    # ---------- rendering ----------

    def _refresh_shows(self):
        current = self.show_box.currentText()
        shows = self.library.shows
        self.completer_model.setStringList(shows)
        self.show_box.blockSignals(True)
        self.show_box.clear()
        for show in shows:
            self.show_box.addItem(f"{show}    ({self.library.counts[show]})", userData=show)
        self.show_box.setCurrentText(current)
        self.show_box.blockSignals(False)
        self.folder_label.setText(self._short_path())

    def _short_path(self):
        text = str(self.folder)
        home = str(Path.home())
        if text.startswith(home):
            text = "~" + text[len(home):]
        missing = "" if self.folder.is_dir() else "   (will be created)"
        return text + missing

    def _current_show(self) -> str:
        index = self.show_box.currentIndex()
        typed = self.show_box.currentText()
        if index >= 0 and self.show_box.itemText(index) == typed:
            return self.show_box.itemData(index) or typed
        return typed

    def _replan(self, *_):
        raw = self._current_show()
        show = core.normalize_show(raw)

        if not show:
            self.show_hint.setText("Type a show name to start")
        elif show in self.library.counts:
            self.show_hint.setText(
                f"{show}  ·  {self.library.counts[show]} on file  ·  next is "
                f"{show}_{self.library.next_index(show):03d}"
            )
        else:
            self.show_hint.setText(f"New show  ·  will start at {show}_001")

        if self.queue and show:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                self.planned = core.plan(self.queue, raw, self.library)
            finally:
                QApplication.restoreOverrideCursor()
        else:
            self.planned = [core.PlannedFile(p, status="missing", detail="waiting for a show name")
                            for p in self.queue] if self.queue else []

        self._render_table()

    def _render_table(self):
        self.table.setRowCount(len(self.planned))
        writable = 0
        for row, item in enumerate(self.planned):
            source = QTableWidgetItem(item.source.name)
            source.setToolTip(str(item.source))
            arrow = QTableWidgetItem("\u2192" if item.will_write else "")
            arrow.setTextAlignment(Qt.AlignCenter)

            if item.will_write:
                writable += 1
                target = QTableWidgetItem(item.target_name)
            else:
                target = QTableWidgetItem(item.detail or item.status)
                for cell in (source, target):
                    cell.setForeground(Qt.gray)

            for column, cell in enumerate((source, arrow, target)):
                self.table.setItem(row, column, cell)

        skipped = len(self.planned) - writable
        parts = []
        if writable:
            parts.append(f"{writable} to add")
        if skipped:
            parts.append(f"{skipped} skipped")
        self.status.setText("  ·  ".join(parts) if parts else "Nothing queued")
        self.commit.setEnabled(writable > 0)


class FilerApp(QApplication):
    """Handles files dropped onto the Dock icon or opened via 'Open With'.

    macOS delivers these as QEvent.FileOpen rather than argv, and they can
    arrive before the window exists -- so anything early gets parked in
    `pending` and picked up once the window registers itself.
    """

    def __init__(self, argv):
        super().__init__(argv)
        self.window = None
        self.pending: list[Path] = []

    def event(self, event):
        if event.type() == QEvent.FileOpen:
            path = Path(event.file())
            if self.window is not None:
                self.window.add_files([path])
                self.window.raise_()
                self.window.activateWindow()
            else:
                self.pending.append(path)
            return True
        return super().event(event)

    def attach(self, window):
        self.window = window
        if self.pending:
            window.add_files(self.pending)
            self.pending.clear()


def main():
    app = FilerApp(sys.argv)
    app.setApplicationName("Wallpaper Filer")
    icon = QIcon(resource_path("icon-app.png"))
    if not icon.isNull():
        app.setWindowIcon(icon)
    window = Window()
    app.attach(window)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
