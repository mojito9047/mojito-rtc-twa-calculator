"""Build and publish a release: the zip that installs on the boat PC, and its GitHub release.

    .venv\\Scripts\\python.exe tools\\release.py build       (make_release.bat)
    .venv\\Scripts\\python.exe tools\\release.py publish

The version is VERSION in server/__init__.py, its git tag has the same name
(v71), and its release notes are the "### v71" section of the README's version
history. See docs/RELEASING.md.

build exports the tagged commit, not the working folder, so uncommitted edits
and this PC's settings.json and runtime/ never ship. It adds Flask and its
dependencies as wheels, so install.bat needs no internet on the boat, runs the
test suite on exactly what will ship, and writes
dist/mojito_rtc_twa_calculator_v71.zip.

publish puts that release on GitHub. The public repository gets one commit per
release, holding the tagged files, authored as PUBLIC_AUTHOR; the development
history stays on this PC. Re-running either step is safe.
"""

import argparse
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"

PUBLIC_REPO = "mojito9047/mojito-rtc-twa-calculator"
REMOTE = "github"
PUBLIC_AUTHOR = ("CapeNet Dev", "dev@capenet.co.uk")

# Wheels are downloaded for each of these (64-bit Windows), so the zip installs
# whichever Python the boat PC has.
PYTHON_VERSIONS = ("3.11", "3.12", "3.13", "3.14")

# In the repository but not in the zip: developer tooling.
DEV_ONLY = ("tools", "make_release.bat", ".gitignore", ".gitattributes")
# Must be in the zip.
REQUIRED = ("app.py", "install.bat", "start_app.bat", "run_tests.bat", "copy_previous_install.py",
            "requirements.txt", "server/__init__.py", "templates/index.html", "README.md", "LICENSE",
            "SailChart J122 North.txt", "J122.txt", "marks.example.json", "course.example.json",
            "static/leaflet/leaflet.js", "static/leaflet/leaflet.css", "server/tiles.py",
            "autostart.py", "autostart.bat")
# Must not be: this PC's state, caches and build output.
FORBIDDEN_DIRS = {".venv", "runtime", "__pycache__", ".git", "dist"}
FORBIDDEN_FILES = {"settings.json"}          # each install's own; a fresh one uses the defaults

# Set while publish pushes, so the pre-push hook lets it through.
PUSH_ENV = "MOJITO_RELEASE_PUSH"
PRE_PUSH_HOOK = f"""#!/bin/sh
# Installed by tools/release.py. The public repository only gets release
# snapshots: pushing a branch from here would publish the whole development
# history. Use: .venv\\Scripts\\python.exe tools\\release.py publish
[ "${PUSH_ENV}" = "1" ] && exit 0
echo "Refusing to push: GitHub gets release snapshots only. Use tools/release.py publish." >&2
exit 1
"""


class ReleaseError(Exception):
    pass


# -------------------------------------------------------------------- names --

def read_version(root=ROOT):
    """VERSION from server/__init__.py, e.g. "v71"."""
    text = (root / "server" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^VERSION = "(v\d+)"', text, re.M)
    if not match:
        raise ReleaseError(f"No VERSION = \"vNN\" in {root / 'server' / '__init__.py'}")
    return match.group(1)


def version_number(version):
    return int(version[1:])


def folder_name(version):
    """The zip's top folder, also the folder it unzips to on the boat PC."""
    return f"mojito_rtc_twa_calculator_{version}"


def zip_path(version):
    return DIST / f"{folder_name(version)}.zip"


def release_notes(version, readme):
    """The body of the README's "### vNN" section."""
    match = re.search(rf"^### {re.escape(version)}\s*\n(.*?)(?=^#{{1,3}} |\Z)", readme, re.M | re.S)
    if not match or not match.group(1).strip():
        raise ReleaseError(f"No \"### {version}\" section in the README's version history")
    return match.group(1).strip()


def check_zip_names(names, version):
    """Problems with a zip's contents: files outside its top folder, missing or forbidden files, missing wheels."""
    top = folder_name(version) + "/"
    problems, files = [], []
    for name in names:
        if not name.startswith(top):
            problems.append(f"outside {top}: {name}")
        else:
            files.append(name[len(top):])
    for name in files:
        parts = name.split("/")
        if (FORBIDDEN_DIRS.intersection(parts[:-1]) or name in FORBIDDEN_FILES or parts[0] in DEV_ONLY
                or name.endswith((".pyc", ".pyo"))):
            problems.append(f"should not ship: {name}")
    for name in REQUIRED:
        if name not in files:
            problems.append(f"missing: {name}")
    wheels = [name[len("wheels/"):].lower() for name in files if name.startswith("wheels/") and name.endswith(".whl")]
    for package in ("flask", "waitress"):
        if not any(w.startswith(package + "-") for w in wheels):
            problems.append(f"no {package.capitalize()} wheel")
    for py in PYTHON_VERSIONS:
        # MarkupSafe is the one compiled dependency: it needs a wheel per Python version.
        tag = "-cp" + py.replace(".", "") + "-"
        if not any(w.startswith("markupsafe-") and tag in w for w in wheels):
            problems.append(f"no MarkupSafe wheel for Python {py}")
    return problems


# ------------------------------------------------------------------ helpers --

def say(text=""):
    print(text, flush=True)


def run(args, cwd=ROOT, env=None, capture=True):
    """Run a command; its output (stripped) when capture is on. ReleaseError on failure."""
    full_env = dict(os.environ, **(env or {}))
    result = subprocess.run(args, cwd=cwd, env=full_env, text=True, encoding="utf-8",
                            capture_output=capture)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip() if capture else ""
        raise ReleaseError(f"{' '.join(str(a) for a in args[:3])} ... failed (exit {result.returncode})"
                           + (f":\n{detail}" if detail else ""))
    return (result.stdout or "").strip() if capture else ""


def git(*args, env=None):
    return run(["git", *args], env=env)


def git_ok(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True).returncode == 0


def tag_commit(tag):
    if not git_ok("rev-parse", "-q", "--verify", f"refs/tags/{tag}"):
        raise ReleaseError(f"No tag {tag}. Commit the release, then tag it: git tag {tag}")
    return git("rev-parse", f"{tag}^{{commit}}")


def find_gh():
    gh = shutil.which("gh")
    if not gh:
        for p in (Path(os.environ.get("ProgramFiles", "")) / "GitHub CLI" / "gh.exe",
                  Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "GitHub CLI" / "gh.exe"):
            if p.is_file():
                gh = str(p)
                break
    if not gh:
        raise ReleaseError("GitHub CLI (gh) not found. Install it and run: gh auth login")
    return gh


# -------------------------------------------------------------------- build --

def export(tag, target):
    """The tagged files, less the developer tooling, into target."""
    pathspec = ["--", "."] + [f":(exclude){p}" for p in DEV_ONLY]
    data = subprocess.run(["git", "archive", "--format=tar", tag, *pathspec],
                          cwd=ROOT, capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        tar.extractall(target, filter="data")


def download_wheels(target):
    """requirements.txt (Flask, Waitress) with dependencies, for every PYTHON_VERSIONS, at the versions tested in this .venv."""
    wheels = target / "wheels"
    frozen = run([sys.executable, "-m", "pip", "freeze", "--disable-pip-version-check"])
    with tempfile.TemporaryDirectory() as tmp:
        constraints = Path(tmp) / "constraints.txt"
        constraints.write_text(frozen + "\n", encoding="utf-8")
        for py in PYTHON_VERSIONS:
            run([sys.executable, "-m", "pip", "download", "--quiet", "--disable-pip-version-check",
                 "--dest", str(wheels), "--only-binary=:all:", "--platform", "win_amd64",
                 "--python-version", py, "--implementation", "cp",
                 "-r", str(target / "requirements.txt"), "-c", str(constraints)])
    return sorted(p.name for p in wheels.glob("*.whl"))


def check_offline_install(target):
    """pip can install requirements.txt from the wheels alone, for every Python version."""
    with tempfile.TemporaryDirectory() as tmp:
        for py in PYTHON_VERSIONS:
            run([sys.executable, "-m", "pip", "install", "--dry-run", "--quiet", "--disable-pip-version-check",
                 "--no-index", "--find-links", str(target / "wheels"), "--only-binary=:all:",
                 "--platform", "win_amd64", "--python-version", py, "--implementation", "cp",
                 "--target", tmp, "-r", str(target / "requirements.txt")])


def run_tests(target):
    """The full suite, on the exported copy: what is tested is what ships."""
    result = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."],
                            cwd=target, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
                            capture_output=True, text=True, encoding="utf-8")
    summary = [line for line in result.stderr.splitlines() if line.startswith(("Ran ", "OK", "FAILED"))]
    if result.returncode != 0:
        raise ReleaseError("Tests failed on the exported copy:\n" + result.stderr[-4000:])
    return " ".join(summary)


def build(skip_tests=False):
    version = read_version()
    commit = tag_commit(version)
    if commit != git("rev-parse", "HEAD"):
        say(f"Note: HEAD is not {version}; building {version} as tagged.")
    folder = folder_name(version)
    build_dir = DIST / "build"
    target = build_dir / folder
    out = zip_path(version)
    shutil.rmtree(build_dir, ignore_errors=True)
    target.mkdir(parents=True)
    if out.exists():
        out.unlink()

    say(f"Building {version} from commit {commit[:10]}")
    export(version, target)
    if read_version(target) != version:
        raise ReleaseError(f"Tag {version} has VERSION {read_version(target)}")
    notes = release_notes(version, (target / "README.md").read_text(encoding="utf-8"))

    say(f"Downloading wheels for Python {', '.join(PYTHON_VERSIONS)} (64-bit Windows)")
    wheels = download_wheels(target)
    say("  " + ", ".join(wheels))
    say("Checking pip can install from the wheels with no internet")
    check_offline_install(target)
    files = sorted(p for p in target.rglob("*") if p.is_file())

    if skip_tests:
        say("Tests skipped")
    else:
        say("Running the tests on the exported copy")
        say("  " + run_tests(target))

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in files:
            zf.write(path, (Path(folder) / path.relative_to(target)).as_posix())
    with zipfile.ZipFile(out) as zf:
        problems = check_zip_names(zf.namelist(), version)
        count = len(zf.namelist())
    if problems:
        out.unlink()
        raise ReleaseError("The zip is not right:\n  " + "\n  ".join(problems))

    tree = git("rev-parse", f"{version}^{{tree}}")
    (DIST / f"{folder}.json").write_text(json.dumps(
        {"version": version, "commit": commit, "tree": tree, "zip": out.name, "notes": notes,
         "tests_skipped": skip_tests}, indent=2), encoding="utf-8")
    shutil.rmtree(build_dir, ignore_errors=True)
    say()
    say(f"Built {out.relative_to(ROOT)}: {count} files, {out.stat().st_size / 1024 / 1024:.1f} MB")
    return out


# ------------------------------------------------------------------ publish --

def ensure_remote():
    url = f"https://github.com/{PUBLIC_REPO}.git"
    if not git_ok("remote", "get-url", REMOTE):
        git("remote", "add", REMOTE, url)
        say(f"Added remote {REMOTE}: {url}")
    # Local vNN tags point at development commits, the public ones at release
    # snapshots: never fetch the public tags over the local ones.
    git("config", f"remote.{REMOTE}.tagOpt", "--no-tags")
    hook = Path(git("rev-parse", "--git-path", "hooks"))
    hook = (ROOT / hook if not hook.is_absolute() else hook) / "pre-push"
    if not hook.exists() or PUSH_ENV not in hook.read_text(encoding="utf-8", errors="replace"):
        hook.parent.mkdir(parents=True, exist_ok=True)
        hook.write_text(PRE_PUSH_HOOK, encoding="utf-8", newline="\n")
        say(f"Installed the pre-push hook ({hook.relative_to(ROOT)})")


def snapshot_commit(version, tree, notes):
    """The public commit for this release: the tagged files on top of the last public release."""
    git("fetch", "--quiet", "--no-tags", REMOTE)
    parent = None
    if git_ok("rev-parse", "-q", "--verify", f"refs/remotes/{REMOTE}/main"):
        parent = git("rev-parse", f"refs/remotes/{REMOTE}/main")
        if git("rev-parse", f"{parent}^{{tree}}") == tree:
            return parent, False                       # already published
    name, email = PUBLIC_AUTHOR
    env = {"GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": email,
           "GIT_COMMITTER_NAME": name, "GIT_COMMITTER_EMAIL": email}
    args = ["commit-tree", tree, "-m", f"{version}\n\n{notes}"]
    if parent:
        args += ["-p", parent]
    return git(*args, env=env), True


def is_newest(gh, version):
    """No published release has a higher version (so this one gets GitHub's Latest badge)."""
    listing = run([gh, "release", "list", "-R", PUBLIC_REPO, "--limit", "200", "--json", "tagName,isDraft"])
    for release in json.loads(listing or "[]"):
        match = re.fullmatch(r"v(\d+)", str(release.get("tagName", "")))
        if match and not release.get("isDraft") and int(match.group(1)) > version_number(version):
            return False
    return True


def publish(draft=False):
    version = read_version()
    out = zip_path(version)
    info_file = DIST / f"{folder_name(version)}.json"
    if not out.exists() or not info_file.exists():
        raise ReleaseError(f"{out.relative_to(ROOT)} not built. Run: tools\\release.py build")
    info = json.loads(info_file.read_text(encoding="utf-8"))
    tree = git("rev-parse", f"{tag_commit(version)}^{{tree}}")
    if info.get("tree") != tree:
        raise ReleaseError(f"The zip was built from a different {version}. Build it again.")
    if info.get("tests_skipped"):
        raise ReleaseError("The zip was built with the tests skipped. Build it again with the tests.")

    gh = find_gh()
    run([gh, "auth", "status"])
    if subprocess.run([gh, "repo", "view", PUBLIC_REPO, "--json", "name"], capture_output=True).returncode != 0:
        raise ReleaseError(f"GitHub repository {PUBLIC_REPO} not found (see docs/RELEASING.md to create it).")
    ensure_remote()

    commit, new = snapshot_commit(version, tree, info["notes"])
    if new:
        git("push", "--quiet", REMOTE, f"{commit}:refs/heads/main", env={PUSH_ENV: "1"})
        say(f"Pushed {version} to {PUBLIC_REPO} main ({commit[:10]})")
    else:
        say(f"{PUBLIC_REPO} main already has {version} ({commit[:10]})")

    body = f"{info['notes']}\n\n**Download:** `{out.name}` below. To install it, see " \
           f"[Installing](https://github.com/{PUBLIC_REPO}#installing) in the README."
    newest = is_newest(gh, version)
    with tempfile.TemporaryDirectory() as tmp:
        notes_file = Path(tmp) / "notes.md"
        notes_file.write_text(body, encoding="utf-8")
        exists = subprocess.run([gh, "release", "view", version, "-R", PUBLIC_REPO],
                                capture_output=True).returncode == 0
        if exists:
            args = [gh, "release", "edit", version, "-R", PUBLIC_REPO, "--notes-file", str(notes_file)]
            if newest:
                args.append("--latest")
            run(args)
            run([gh, "release", "upload", version, str(out), "-R", PUBLIC_REPO, "--clobber"])
            say(f"Updated release {version}")
        else:
            args = [gh, "release", "create", version, str(out), "-R", PUBLIC_REPO, "--target", commit,
                    "--title", version, "--notes-file", str(notes_file)]
            if draft:
                args.append("--draft")
            else:
                args.append("--latest" if newest else "--latest=false")
            run(args)
            say(f"Created release {version}" + (" (draft)" if draft else ""))
    say(f"https://github.com/{PUBLIC_REPO}/releases/tag/{version}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build and publish a release (docs/RELEASING.md).")
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build", help="test the tagged version and build its zip in dist/")
    b.add_argument("--skip-tests", action="store_true", help="for trying the build only; publish refuses it")
    p = sub.add_parser("publish", help="put the built release on GitHub")
    p.add_argument("--draft", action="store_true", help="create the GitHub release as a draft")
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            build(skip_tests=args.skip_tests)
        else:
            publish(draft=args.draft)
    except (ReleaseError, subprocess.CalledProcessError) as exc:
        say(f"\nRelease stopped: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
