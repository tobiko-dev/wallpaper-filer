"""Close numbering gaps for one show. Run this rarely and on purpose.

    python3 compact.py ~/Pictures/anime-wallpapers frieren          # preview
    python3 compact.py ~/Pictures/anime-wallpapers frieren --apply  # do it
"""

import argparse
from pathlib import Path

import core


def main():
    parser = argparse.ArgumentParser(description="Renumber one show so its files run 001..N with no gaps.")
    parser.add_argument("folder", type=Path)
    parser.add_argument("show")
    parser.add_argument("--apply", action="store_true", help="actually rename (default is a preview)")
    args = parser.parse_args()

    if not args.folder.is_dir():
        raise SystemExit(f"no such folder: {args.folder}")

    changes = core.compact(args.folder, args.show, dry_run=True)
    if not changes:
        print(f"{core.normalize_show(args.show)}: already contiguous, nothing to do")
        return

    for old, new in changes:
        print(f"  {old}  ->  {new}")

    if not args.apply:
        print(f"\n{len(changes)} file(s) would be renamed. Re-run with --apply to go ahead.")
        return

    core.compact(args.folder, args.show, dry_run=False)
    (args.folder / core.HASH_CACHE).unlink(missing_ok=True)
    (args.folder / core.UNDO_LOG).unlink(missing_ok=True)
    print(f"\nRenamed {len(changes)} file(s).")


if __name__ == "__main__":
    main()
