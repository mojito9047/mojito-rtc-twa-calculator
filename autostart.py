"""Start the app automatically when you sign in to Windows (run by install.bat and autostart.bat).

Auto-start is a shortcut in your Windows Startup folder to this version's
start_app.bat, set to open minimised. It starts at sign-in, not at power-on:
a Windows service would run outside your session and might not see
Expedition's data, and there would be no window showing the version and the
addresses.

Each version is installed in its own folder, so the shortcut has to follow the
upgrades. install.bat runs this with --install: when auto-start is already on,
the shortcut is pointed at the version just installed without asking, so the
old version is never the one that starts; otherwise it asks. Any other
shortcut in the Startup folder to a copy of this app's start_app.bat (one made
by hand, say) is replaced, so two versions never both start. Other shortcuts
are left alone.

    python autostart.py --install    ask, or follow an upgrade (install.bat)
    python autostart.py              show whether it is on, offer to change it (autostart.bat)
    python autostart.py --on | --off | --status

Windows only; standard library only. Shortcuts are made with Windows' own
WScript.Shell, through PowerShell.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SHORTCUT_NAME = "Mojito RTC TWA Calculator.lnk"
MINIMISED = 7                                   # WScript.Shell WindowStyle: minimised, not focused


# ------------------------------------------------ Windows (via PowerShell) --

def _powershell(script, **env):
    """Run a PowerShell script (values passed in environment variables); its output."""
    full_env = dict(os.environ, **{k: str(v) for k, v in env.items()})
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command",
         "[Console]::OutputEncoding = [Text.Encoding]::UTF8; " + script],
        capture_output=True, env=full_env, timeout=60)
    if result.returncode != 0:
        raise OSError(result.stderr.decode("utf-8", "replace").strip() or "PowerShell failed")
    return result.stdout.decode("utf-8", "replace").strip()


def startup_folder():
    """This user's Windows Startup folder."""
    try:
        folder = _powershell("[Environment]::GetFolderPath('Startup')")
        if folder:
            return Path(folder)
    except (OSError, subprocess.SubprocessError):
        pass
    return Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def shortcut_targets(folder):
    """{shortcut path: target path} of the shortcuts in a folder."""
    if not Path(folder).is_dir():
        return {}
    out = _powershell(
        "$s = New-Object -ComObject WScript.Shell; "
        "@(Get-ChildItem -LiteralPath $env:MOJITO_FOLDER -Filter *.lnk | ForEach-Object { "
        "[pscustomobject]@{path = $_.FullName; target = $s.CreateShortcut($_.FullName).TargetPath} }) "
        "| ConvertTo-Json -Compress",
        MOJITO_FOLDER=folder)
    if not out:
        return {}
    items = json.loads(out)
    if isinstance(items, dict):
        items = [items]
    return {Path(i["path"]): Path(i["target"]) for i in items if i.get("target")}


def write_shortcut(path, target):
    _powershell(
        "$l = (New-Object -ComObject WScript.Shell).CreateShortcut($env:MOJITO_LNK); "
        "$l.TargetPath = $env:MOJITO_TARGET; $l.WorkingDirectory = $env:MOJITO_DIR; "
        f"$l.WindowStyle = {MINIMISED}; $l.Description = 'Mojito RTC TWA Calculator'; $l.Save()",
        MOJITO_LNK=path, MOJITO_TARGET=target, MOJITO_DIR=Path(target).parent)


# -------------------------------------------------------------------- logic --

def is_install(folder):
    return (folder / "app.py").is_file() and (folder / "templates" / "index.html").is_file()


def app_shortcuts(folder):
    """{shortcut: target} for the Startup folder's shortcuts that start a copy of this app."""
    return {lnk: target for lnk, target in shortcut_targets(folder).items()
            if lnk.name == SHORTCUT_NAME or (target.name.lower() == "start_app.bat" and is_install(target.parent))}


def turn_on(here, folder):
    """Make the one auto-start shortcut start this version; remove any others. Returns what changed."""
    target = here / "start_app.bat"
    removed = []
    for lnk in app_shortcuts(folder):
        if lnk.name != SHORTCUT_NAME:
            lnk.unlink()
            removed.append(lnk.name)
    folder.mkdir(parents=True, exist_ok=True)
    write_shortcut(folder / SHORTCUT_NAME, target)
    return removed


def turn_off(folder):
    removed = []
    for lnk in app_shortcuts(folder):
        lnk.unlink()
        removed.append(lnk.name)
    return removed


def describe(targets, here):
    if not targets:
        return "Auto-start is off."
    starts = sorted({str(t.parent) for t in targets.values()})
    which = "this version" if starts == [str(here)] else ", ".join(Path(s).name for s in starts)
    return f"Auto-start is on: signing in to Windows starts {which}."


def ask_yes(ask, prompt):
    try:
        return ask(prompt).strip().lower() in ("y", "yes")
    except EOFError:
        return False


def main(argv=None, here=HERE, folder=None, ask=input):
    parser = argparse.ArgumentParser(description="Start the app automatically when you sign in to Windows.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--install", action="store_true", help="ask, or move auto-start to this version (install.bat)")
    mode.add_argument("--on", action="store_true", help="start this version at sign-in")
    mode.add_argument("--off", action="store_true", help="stop starting the app at sign-in")
    mode.add_argument("--status", action="store_true", help="say whether auto-start is on")
    args = parser.parse_args(argv)

    if folder is None:
        if sys.platform != "win32":
            print("Auto-start is only set up on Windows.")
            return 0
        folder = startup_folder()
    here, folder = Path(here).resolve(), Path(folder)
    try:
        existing = app_shortcuts(folder)
        if args.status:
            print(describe(existing, here))
        elif args.off:
            print("Auto-start turned off." if turn_off(folder) else "Auto-start was already off.")
        elif args.on:
            turn_on(here, folder)
            print("Auto-start is on: signing in to Windows starts this version (minimised).")
        elif args.install:
            if existing:
                if {t.parent.resolve() for t in existing.values()} != {here} or len(existing) > 1:
                    turn_on(here, folder)
                    print("Auto-start moved to this version: signing in to Windows now starts it (minimised).")
                else:
                    print("Auto-start is on for this version.")
            elif ask_yes(ask, "Start the app automatically when you sign in to Windows? [y/N] "):
                turn_on(here, folder)
                print("Auto-start is on: signing in to Windows starts this version (minimised).")
                print("To turn it off, double-click autostart.bat.")
            else:
                print("Auto-start not set up. To set it up later, double-click autostart.bat.")
        else:
            print(describe(existing, here))
            if existing and ask_yes(ask, "Turn auto-start off? [y/N] "):
                turn_off(folder)
                print("Auto-start turned off.")
            elif not existing and ask_yes(ask, "Start this version automatically when you sign in to Windows? [y/N] "):
                turn_on(here, folder)
                print("Auto-start is on: signing in to Windows starts this version (minimised).")
            elif existing and {t.parent.resolve() for t in existing.values()} != {here} \
                    and ask_yes(ask, "Start this version instead? [y/N] "):
                turn_on(here, folder)
                print("Auto-start moved to this version.")
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        print(f"Could not change auto-start: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
