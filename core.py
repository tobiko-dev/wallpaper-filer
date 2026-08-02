"""Core logic for the wallpaper filer.

No GUI imports live here on purpose -- everything in this module is plain
Python so it can be tested from the command line without opening a window.

The folder is the database. There is no index file, no sidecar JSON, no
state to keep in sync. Show names are derived by scanning filenames, which
means the app and the folder can never disagree with each other.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import unicodedata
from dataclasses import dataclass
from pathlib import Path

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff", ".heic"}
PAD = 3
NAME_RE = re.compile(r"^(?P<show>.+)_(?P<index>\d+)$")
UNDO_LOG = ".wallpaper-filer-undo.json"
HASH_CACHE = ".wallpaper-filer-cache.json"


def normalize_show(raw: str) -> str:
    """Turn anything a human types into a canonical filename prefix.

    'Frieren: Beyond Journey's End' -> 'frieren-beyond-journeys-end'

    Underscores become hyphens because the underscore is the delimiter
    between the show and its index -- letting one into the show name
    would make the filename ambiguous.
    """
    text = unicodedata.normalize("NFKD", raw)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = re.sub(r"['\u2019\u02bc]", "", text)
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def split_name(stem: str) -> tuple[str, int] | None:
    """Split 'frieren_015' into ('frieren', 15). Returns None if unparseable."""
    match = NAME_RE.match(stem)
    if not match:
        return None
    return match.group("show"), int(match.group("index"))


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass
class Library:
    """A snapshot of the target folder."""

    folder: Path
    counts: dict[str, int]
    highest: dict[str, int]
    hashes: dict[str, str]
    unparsed: list[str]

    @property
    def shows(self) -> list[str]:
        return sorted(self.counts)

    def next_index(self, show: str) -> int:
        return self.highest.get(show, 0) + 1


def _load_cache(folder: Path) -> dict:
    try:
        return json.loads((folder / HASH_CACHE).read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def scan(folder: Path, want_hashes: bool = True) -> Library:
    """Read the folder and derive the show list from filenames alone.

    Hashes are cached against (size, mtime) so a folder of several hundred
    images only gets fully read once.
    """
    counts: dict[str, int] = {}
    highest: dict[str, int] = {}
    hashes: dict[str, str] = {}
    unparsed: list[str] = []

    if not folder.is_dir():
        return Library(folder, counts, highest, hashes, unparsed)

    cache = _load_cache(folder) if want_hashes else {}
    fresh: dict[str, list] = {}

    for entry in sorted(folder.iterdir()):
        if not entry.is_file() or entry.name.startswith("."):
            continue
        if entry.suffix.lower() not in IMAGE_SUFFIXES:
            continue

        parsed = split_name(entry.stem)
        if parsed is None:
            unparsed.append(entry.name)
        else:
            show, index = parsed
            counts[show] = counts.get(show, 0) + 1
            highest[show] = max(highest.get(show, 0), index)

        if not want_hashes:
            continue

        try:
            stat = entry.stat()
            cached = cache.get(entry.name)
            if cached and cached[0] == stat.st_size and cached[1] == stat.st_mtime_ns:
                digest = cached[2]
            else:
                digest = file_hash(entry)
            fresh[entry.name] = [stat.st_size, stat.st_mtime_ns, digest]
            hashes[digest] = entry.name
        except OSError:
            pass

    if want_hashes and fresh != cache:
        try:
            (folder / HASH_CACHE).write_text(json.dumps(fresh))
        except OSError:
            pass

    return Library(folder, counts, highest, hashes, unparsed)


@dataclass
class PlannedFile:
    source: Path
    target_name: str = ""
    status: str = "ok"      # ok | duplicate | unsupported | missing
    detail: str = ""

    @property
    def will_write(self) -> bool:
        return self.status == "ok"


def plan(sources, show_raw: str, library: Library) -> list[PlannedFile]:
    """Work out what each dropped file would be renamed to.

    Nothing touches disk here -- this only builds the preview. Numbering
    always continues from the highest existing index and never fills gaps,
    so a file's name is stable for as long as it exists.
    """
    show = normalize_show(show_raw)
    results: list[PlannedFile] = []

    if not show:
        return [PlannedFile(Path(s), status="missing", detail="no show name") for s in sources]

    index = library.next_index(show)
    seen_hashes = dict(library.hashes)
    taken = {p.name.lower() for p in library.folder.glob("*")} if library.folder.is_dir() else set()

    for source in sorted((Path(s) for s in sources), key=lambda p: p.name.lower()):
        if not source.is_file():
            results.append(PlannedFile(source, status="missing", detail="file not found"))
            continue

        suffix = source.suffix.lower()
        if suffix not in IMAGE_SUFFIXES:
            results.append(PlannedFile(source, status="unsupported", detail=f"{suffix or 'no extension'} not an image"))
            continue

        try:
            digest = file_hash(source)
        except OSError as exc:
            results.append(PlannedFile(source, status="missing", detail=str(exc)))
            continue

        if digest in seen_hashes:
            existing_name = seen_hashes[digest]
            
            # Check if the "duplicate" is actually just the file we are currently trying to rename
            is_same_file = (library.folder / existing_name).resolve() == source.resolve()
            
            if not is_same_file:
                results.append(PlannedFile(source, status="duplicate", detail=f"already have {existing_name}"))
                continue

        while f"{show}_{index:0{PAD}d}{suffix}".lower() in taken:
            index += 1

        target = f"{show}_{index:0{PAD}d}{suffix}"
        taken.add(target.lower())
        seen_hashes[digest] = target
        index += 1
        results.append(PlannedFile(source, target_name=target))

    return results


def apply(planned: list[PlannedFile], folder: Path, move: bool = True) -> tuple[int, list[str]]:
    """Carry out the plan. Returns (files written, error messages)."""
    folder.mkdir(parents=True, exist_ok=True)
    written: list[dict[str, str]] = []
    errors: list[str] = []

    for item in planned:
        if not item.will_write:
            continue
        destination = folder / item.target_name
        try:
            if destination.exists():
                errors.append(f"{item.target_name} already exists, skipped")
                continue
            if move:
                shutil.move(str(item.source), destination)
            else:
                shutil.copy2(item.source, destination)
            written.append({"from": str(item.source), "to": str(destination), "moved": move})
        except OSError as exc:
            errors.append(f"{item.source.name}: {exc}")

    if written:
        (folder / UNDO_LOG).write_text(json.dumps(written, indent=2))

    return len(written), errors


def can_undo(folder: Path) -> int:
    """How many files the last batch wrote, or 0 if there's nothing to reverse.

    Lets the UI disable the undo button rather than letting someone press a
    button that does nothing.
    """
    log = folder / UNDO_LOG
    if not log.exists():
        return 0
    try:
        entries = json.loads(log.read_text())
    except (OSError, json.JSONDecodeError):
        return 0
    return sum(1 for e in entries if Path(e.get("to", "")).exists())


def undo_last(folder: Path) -> tuple[int, list[str]]:
    """Reverse the most recent batch. Moves go back, copies are deleted."""
    log = folder / UNDO_LOG
    if not log.exists():
        return 0, ["nothing to undo"]

    try:
        entries = json.loads(log.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return 0, [f"could not read undo log: {exc}"]

    reverted = 0
    errors: list[str] = []
    for entry in entries:
        destination = Path(entry["to"])
        if not destination.exists():
            continue
        try:
            if entry.get("moved") and not Path(entry["from"]).exists():
                shutil.move(str(destination), entry["from"])
            else:
                destination.unlink()
            reverted += 1
        except OSError as exc:
            errors.append(f"{destination.name}: {exc}")

    log.unlink(missing_ok=True)
    return reverted, errors


def compact(folder: Path, show: str, dry_run: bool = True) -> list[tuple[str, str]]:
    """Close numbering gaps for one show. Deliberate cleanup, never automatic.

    Renames in two passes through temporary names so a file never lands on
    one that is still occupied.
    """
    show = normalize_show(show)
    files = []
    for entry in sorted(folder.iterdir()):
        if not entry.is_file() or entry.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        parsed = split_name(entry.stem)
        if parsed and parsed[0] == show:
            files.append((parsed[1], entry))

    files.sort(key=lambda pair: pair[0])
    changes = []
    for position, (_, entry) in enumerate(files, start=1):
        new_name = f"{show}_{position:0{PAD}d}{entry.suffix.lower()}"
        if new_name != entry.name:
            changes.append((entry.name, new_name))

    if dry_run or not changes:
        return changes

    staged = []
    for old_name, new_name in changes:
        temporary = folder / f".compact-{old_name}"
        (folder / old_name).rename(temporary)
        staged.append((temporary, folder / new_name))
    for temporary, final in staged:
        temporary.rename(final)

    return changes
