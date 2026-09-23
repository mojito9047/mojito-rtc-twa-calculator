# Releasing

A release is a zip, `mojito_rtc_twa_calculator_vNN.zip`, that installs on the
boat PC with no internet, published on GitHub at
[mojito9047/mojito-rtc-twa-calculator](https://github.com/mojito9047/mojito-rtc-twa-calculator/releases).
`tools/release.py` builds and publishes it; `make_release.bat` runs both steps.

## Making a release

1. **Finish the work** with the tests passing (`run_tests.bat`).
2. **Bump the version.** Set `VERSION` in `server/__init__.py` to the next
   number (`v72`) and add a `### v72` section at the end of the README's version
   history. That section is the release notes; `test_version_matches_readme`
   fails until both are done.
3. **Commit and tag** with the same name:

   ```text
   git commit -m "v72: ..."
   git tag v72
   ```

4. **Double-click `make_release.bat`.** It builds the zip (below), then asks
   whether to publish it on GitHub. Answer `y` to publish.
5. **Check the release page** it prints: the notes, and the zip attached.

Either step can be run on its own:

```text
.venv\Scripts\python.exe tools\release.py build
.venv\Scripts\python.exe tools\release.py publish
```

Both are safe to re-run. `build --skip-tests` is for trying the build; publish
refuses a zip built that way.

## What the build does

1. Exports the files of the **tagged commit** into `dist\build\`, never the
   working folder, so uncommitted edits and this PC's `settings.json`,
   `runtime\` and `.venv\` cannot ship. Developer tooling (`tools\`,
   `make_release.bat`, `.gitignore`, `.gitattributes`) is left out.
2. Downloads Flask, Waitress and their dependencies as wheels into `wheels\`, for Python
   3.11 to 3.14 on 64-bit Windows, at the versions installed in this `.venv`
   (the ones the tests ran against). This needs the internet; installing from
   the zip does not.
3. Checks pip can install `requirements.txt` from those wheels alone, for each
   Python version.
4. Runs the whole test suite **on the exported copy**, so what is tested is
   what ships.
5. Writes `dist\mojito_rtc_twa_calculator_vNN.zip`, with everything under one
   top folder of that name, and checks it: every required file present, a
   MarkupSafe wheel for each Python version, and no settings, state, caches or
   tooling. `dist\` is not in git.

## What publishing does

1. Adds **one commit** to `main` on GitHub holding exactly the tagged files,
   authored `CapeNet Dev <dev@capenet.co.uk>`, on top of the previous release's
   commit. The public repository therefore has one commit per release; the
   development history stays on this PC.
2. Creates the GitHub release `vNN` at that commit, with the README's notes and
   the zip, marked *Latest* unless a higher version is already published. If
   the release exists already, its notes and zip are updated instead.

The local repository reaches GitHub through the remote `github`, set to fetch
no tags: the local `vNN` tags point at development commits, the GitHub ones at
the release commits. A `pre-push` hook (installed by `publish`) refuses any
other push, because pushing a branch from here would publish the whole
development history.

## Setting up on another PC

Needs git, Python with this app's `.venv` (`install.bat`) and the GitHub CLI
signed in to the `mojito9047` account (`gh auth login`). The repository was
created once with:

```text
gh repo create mojito9047/mojito-rtc-twa-calculator --public --description "..."
```

`publish` adds the `github` remote and the hook itself.
