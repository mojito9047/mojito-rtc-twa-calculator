"""Bring settings, marks and course across from the previous version (run by install.bat).

Each version is unzipped into its own folder beside the last one
(mojito_rtc_twa_calculator_v70, mojito_rtc_twa_calculator_v71, ...). This finds
the version beside this one that was used most recently and, when asked,
copies from it:

    settings.json   instrument source and addresses, Race Officer address,
                    the files chosen
    runtime/        marks, course, current leg, manual wind, Race Officer poll
                    state and wind history (from the app folder itself for v60
                    and earlier), and the course chart's saved map tiles
    the sail chart, polar and marks XML named in its settings, when this
    version has no file of that name (for example one uploaded on the Settings
    page). A file this version also ships is kept as shipped; if the two
    differ, it says so.

The previous version is not changed. Standard library only.

    python copy_previous_install.py [--from FOLDER] [--yes]
"""

import argparse
import filecmp
import json
import re
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from server.storage import RUNTIME_FILES  # noqa: E402  (standard library only)

FILE_SETTINGS = ("sailchart_file", "polar_file", "expedition_marks_file")


def is_install(folder):
    return (folder / "app.py").is_file() and (folder / "templates" / "index.html").is_file()


def state_files(folder):
    """{name: path} of the state files a folder holds."""
    found = {}
    for name in RUNTIME_FILES:
        for path in (folder / "runtime" / name, folder / name):
            if path.is_file():
                found[name] = path
                break
    return found


def last_used(folder):
    """When the app in this folder last saved anything (0 if never)."""
    paths = list(state_files(folder).values()) + [folder / "settings.json"]
    return max((p.stat().st_mtime for p in paths if p.is_file()), default=0.0)


def version_of(folder):
    init = folder / "server" / "__init__.py"
    if init.is_file():
        match = re.search(r'^VERSION = "([^"]+)"', init.read_text(encoding="utf-8"), re.M)
        if match:
            return match.group(1)
    return folder.name


def find_previous(here):
    """The other install beside this folder that was used most recently, or None."""
    here = here.resolve()
    candidates = [p for p in here.parent.iterdir()
                  if p.is_dir() and p.resolve() != here and is_install(p) and last_used(p) > 0]
    return max(candidates, key=last_used, default=None)


def copy_previous(source, here, say=print):
    """Copy settings, state and uploaded files from source into here; returns what was copied."""
    copied = []
    settings = {}
    if (source / "settings.json").is_file():
        shutil.copy2(source / "settings.json", here / "settings.json")
        copied.append("settings.json")
        try:
            settings = json.loads((source / "settings.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            settings = {}
    for name, path in state_files(source).items():
        (here / "runtime").mkdir(exist_ok=True)
        shutil.copy2(path, here / "runtime" / name)
        copied.append(f"runtime/{name}")
    tiles = source / "runtime" / "tiles"
    if tiles.is_dir():
        count = sum(1 for p in tiles.rglob("*.png"))
        shutil.copytree(tiles, here / "runtime" / "tiles", dirs_exist_ok=True)
        copied.append(f"runtime/tiles ({count} map tiles)")
    for key in FILE_SETTINGS:
        value = settings.get(key) if isinstance(settings, dict) else None
        if not isinstance(value, str) or not value.strip():
            continue
        rel = Path(value.strip())
        if rel.is_absolute() or ".." in rel.parts:
            continue                                   # a full path still points at the same file
        old, new = source / rel, here / rel
        if not old.is_file():
            continue
        if not new.exists():
            new.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(old, new)
            copied.append(str(rel))
        elif not filecmp.cmp(old, new, shallow=False):
            say(f"Kept this version's {rel}; the one in {source.name} is different. "
                "Copy it across by hand if it has your changes.")
    return copied


def main(argv=None, here=HERE, ask=input):
    parser = argparse.ArgumentParser(description="Copy settings, marks and course from the previous version.")
    parser.add_argument("--from", dest="source", help="the previous version's folder (default: found beside this one)")
    parser.add_argument("--yes", action="store_true", help="copy without asking")
    args = parser.parse_args(argv)

    here = Path(here).resolve()
    if args.source:
        source = Path(args.source).resolve()
        if not is_install(source):
            print(f"{source} is not a Mojito RTC TWA Calculator folder.")
            return 1
    else:
        source = find_previous(here)
        if source is None:
            print("No earlier version found beside this folder: starting with the default settings.")
            return 0
    when = time.strftime("%d %b %Y %H:%M", time.localtime(last_used(source)))
    print(f"Earlier version found: {source.name} ({version_of(source)}), last used {when}.")
    if not args.source and last_used(here) > last_used(source):
        print("This version has been used since then, so nothing is copied.")
        return 0
    if not args.yes:
        try:
            answer = ask("Copy its settings, marks and course into this version? [Y/n] ")
        except EOFError:
            answer = "n"
        if answer.strip().lower() not in ("", "y", "yes"):
            print("Nothing copied.")
            return 0
    copied = copy_previous(source, here)
    print("Copied: " + ", ".join(copied) if copied else "Nothing to copy.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
