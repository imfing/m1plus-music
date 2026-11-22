# Build, test and flash

Run `make help` for common tasks. Direct tools use `uv run python -I tools/<name>.py`.

## Setup

```sh
brew install uv squashfs llvm lld
make setup
cp "M1 Plus Firmware V2.1.zip" firmware/
uv run python -I tools/mod_font.py --fetch
uv run python -I tools/mod_wpa.py --fetch   # hostap sources for the Wi-Fi supplicant ([wifi](modules/wifi.md))
make doctor
```

- Each checkout and worktree runs its own `make setup`: its own uv `.venv` (Python 3.15) and its
  own `work/` and `out/`. Never borrow another checkout's interpreter or write into its outputs.
- Firmware, fonts and a matching stock tree may be read from the main checkout through
  `tools/paths.py`, which resolves read-only inputs.
- Update `pyproject.toml` and `uv.lock` together (`uv sync --locked`).
- Use Homebrew LLVM/LLD (Apple clang lacks MIPS support); override with `LLVM_BIN` / `LLD_BIN`.
- Keep `-I` on Python tools. Never execute code from extracted firmware or a reference clone.
- `make doctor` checks pinned inputs, native tools and Unicorn MIPS execution. SIGILL can mean a
  sandbox forbids native JIT; use an environment that permits it.

## Editing rules

- Run builds and tests in the foreground; never background them and sleep-poll.
- Edit with the editor tool. Other tools:
  - `tools/sub.py --pairs` for checked mechanical replacements
  - `tools/peek.py` to crop, zoom and diff images
  - `tools/stock.py` to search the stock tree (`addr`, `sym`, `callers`, `strings`)
- No heredoc scripts, `VAR=value cmd` prefixes or `cd X && …` chains. Use absolute paths and `git -C`.
- Stage explicit paths, never `-A`. Never commit `.venv`, packages or previews. Never run `ruff format`.
- Start a UI bug fix with a failing emulation test or a device capture. A look-only tweak (size,
  colour, spacing) needs only a preview.

## Development

```sh
make test TEST=albums/toggle_tests   # selected sections; comma-separated, module or module/section
make dev                       # dev tag, one tree, full tests, verified package; reuses an identical passing build
make dev FRESH=1               # force a full run
make dev PERF=1                # plus instruction budgets and stress-scale inputs
make preview                   # approximate render of that dev tree
make flash                     # verified SD copy, then eject
make ota                       # push that build to the local update server (make ota-serve; see update)
```

### How much to run

Size the checks to the change. A full suite never proves more than the sections the change can
reach.

| Change | Run |
|---|---|
| Docs or comments only | `make test TEST=docs`. No `make dev`. |
| Tests only | The changed sections. |
| Code, while iterating | The sections that the change and the recipe name. |
| Something for the device (flash, OTA) | `make dev`, once per build you want to try. |
| Branch done or squash merge | `make dev` once. An identical tree reuses the passing build in seconds. |
| Payload instruction budgets or stress inputs touched | Add `PERF=1` to that one run. |

- The user guides change only when the change is user-visible. Module docs change only when
  behaviour or interfaces change.

Dev artifacts stay in `out/dev/<tag>/` (newest 10 per checkout, `DEV_KEEP`, plus `latest`): `tree/`, `update.bin`, logs and `results.json`.
`tree/build.json` records the tag, inputs, environment and artifact hashes. Tests and packaging
use the same tree; About, the preview and the package use its tag.

- Targeted `make test` reuses `work/check`'s tree when nothing outside `test/` changed (about 3 s).
- Only a fully passing build becomes `latest`. A failed dev run leaves the previous latest
  selected; pass `BUILD=out/dev/<tag>` to choose another.
- `make flash` verifies the full test receipt, package, target card and read-back hash. It never
  rebuilds. `VOLUME=/Volumes/Name` picks another card; `DRY_RUN=1` checks without copying.
- Dev tags are `V2.1z` plus four checkout-namespace letters and four counter letters. Keep the
  gitignored `.dev-number.json`; never reset the counter or reuse an output directory.
  Collisions, moved worktrees and exhausted counters fail explicitly.
- Release tags are `V2.1-<VERSION>`.
- `make test` and `make dev` skip the instruction budgets and stress-scale inputs unless `PERF=1`;
  `make check` always runs them.
- `JOBS=4` limits workers (default one per CPU). Runs in several worktrees share one
  set of machine-wide test slots, so they queue for the CPUs.
- `make dev` reuses another worktree's passing tests when the inputs are identical (a squash
  of a rebased, tested branch): it only builds and packs. `FRESH=1` reruns them.
- `make clean` removes `work/check` only.

```sh
uv run python -I tools/check.py --list
uv run python -I tools/check.py --test albums/toggle_tests
uv run python -I tools/check.py --tests-only --jobs 4 --timeout 300
```

Previews: `tools/preview/preview*.py` write to `out/preview/` (gitignored). Generate the release
sheet with `uv run python -I tools/preview/preview.py WORKDIR`.

## Formatting and lint

- Run `make format` after editing C. It covers tracked payload C and headers: four spaces,
  attached braces, 120 columns. `make dev` runs `format-check`. Select Homebrew clang-format
  with `LLVM_BIN` or `CLANG_FORMAT`. A reformat-only commit stays apart from functional changes.
- `make lint` runs pinned Ruff bug and syntax checks without formatting. Test, dev and check
  targets run it first. Star imports are allowed in `test/pod/*.py` and
  `tools/preview/preview_tape.py`.

## Integration and restore

Feature branches leave `VERSION`, goldens and history unchanged. GitHub releases and git tags use
the plain `VERSION` without a `v`; dev About shows the dev tag.

At integration, bump `VERSION` in `tools/build.py` (patch for fixes, minor for features, major by
decision). `TAG = V2.1-<VERSION>` is the package version the updater compares; About shows the
plain `VERSION`. Then run:

```sh
make check                     # both packages and all tests against existing goldens
make accept                    # accept intended changes; reuse complete matching evidence
```

- CHANGED and NEW fail until accepted. Acceptance needs both packages and every test;
  `--no-tests` and `--only` cannot bypass it. Source changes during a run invalidate its evidence.
- Commit the golden; add history only for milestones or device findings. Resolve golden and
  history conflicts from the integration side and rerun.
- Checked packages stay in `work/check/release/out` and `work/check/restore/out`.
- Release and restore copies require golden bytes; dev copies require a full receipt. There is
  no `--force`. `build.py --dev` alone creates no test receipt; use `make dev` to install.
- `--pack-only` rejects stale trees. `--no-cache` supports cold-build comparisons.

Direct builds:

```sh
uv run python -I tools/build.py
uv run python -I tools/build.py --restore
uv run python -I tools/fwtool.py verify out/M1Plus-<tag>-release-update.bin
uv run python -I tools/flash_sd.py out/M1Plus-<tag>-release-update.bin
```

The `V2.1R` restore package (stock images, own tag) is a developer tool. Users restore with
Shanling's official V2.1 ([version](modules/version.md)).

## Publish

After the integration commit and a matching `make check`, `make publish NOTES=<file>` uploads the
golden release package (as `update.bin`, with `SHA256SUMS`) to a draft GitHub release named
`VERSION` (`--target HEAD`) and compares the downloaded assets. The notes come from the `NOTES`
file, never the commit message.

- No tag is created or pushed: GitHub tags `VERSION` at HEAD on publish.
- A refresh keeps the draft's notes unless `NOTES` is given.
- Review the draft, then `make publish PUBLISH=1` (or publish on GitHub).
- `DRY_RUN=1` checks and stages `out/publish/<VERSION>/` only.
- It refuses a dirty tree, a package that is not the golden, a local tag on another commit and
  an already published release. The restore image stays local.

## Device checks

Follow [Install](install.md) for card preparation, update confirmation and restore, and the
feature's module doc to validate a build. Emulation does not certify hardware timing or
appearance.

**Settings → Developer → Screenshot** asks first, then captures after a delay
([screenshot](modules/screenshot.md)).
With the card mounted:

```sh
uv run python -I tools/pull_shots.py --build latest
uv run python -I tools/peek.py info out/dev/<tag>/device/<capture>.png
```
