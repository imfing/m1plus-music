# Build, test and flash

Run `make help` for common tasks. Direct tools use `uv run python -I tools/<name>.py`.

## Editing rules

Run builds and tests in the foreground; never background them and sleep-poll.
Edit with the editor tool. Use `tools/sub.py --pairs` for checked mechanical replacements,
`tools/peek.py` for image crops/zooms/diffs, and `tools/stock.py` for stock-tree searches.
Do not use heredoc scripts, `VAR=value cmd` prefixes or `cd X && ...` chains;
use tool flags, absolute paths and `git -C` instead. Stage explicit paths with `git add`,
never `-A`; never commit virtual environments or generated packages/previews.

Worktrees require their own `make setup`; never borrow another checkout's interpreter,
symlink inputs or write into another checkout's `work/` or `out/`.
`tools/paths.py` resolves shared read-only inputs. Python stays at 3.15 with dependencies
managed by `uv sync --locked`, `pyproject.toml` and `uv.lock`. Do not run `ruff format`.

## Setup

```sh
brew install uv squashfs llvm lld
make setup
cp "M1 Plus Firmware V2.1.zip" firmware/
uv run python -I tools/mod_font.py --fetch
make doctor
```

Each checkout needs its own uv-managed `.venv` and Python 3.15. Update `pyproject.toml` and
`uv.lock` together. Use Homebrew LLVM/LLD (Apple clang lacks MIPS support); override locations
with `LLVM_BIN` / `LLD_BIN`.

Each worktree runs `make setup`. Firmware, fonts and a matching stock tree may be read from
the main checkout; outputs, caches and counters stay local. `tools/paths.py` resolves data only;
run it to inspect paths. Never execute code from extracted firmware or a reference clone.
Keep `-I` on Python tools.

`make doctor` checks pinned inputs, native tools and Unicorn MIPS execution. SIGILL can indicate
that a sandbox prohibits native JIT. Use an environment that permits Unicorn; failures report
their signal and log path without silently retrying or escalating.

## Development

```sh
make test TEST=albums           # selected tests; comma-separated modules or module/section
make test                      # feature-branch done criterion; no package or goldens; skips cost/stress checks
make test PERF=1               # the same plus instruction budgets and stress-scale inputs
make dev                       # fresh dev tag, one tree, full tests and verified package
make preview                   # approximate render of that dev tree
make flash                     # verified SD copy, then eject
make ota                       # push that build to the local update server (make ota-serve; docs/modules/update.md)
```

Dev artifacts stay in `out/dev/<tag>/`: `tree/`, `update.bin`, logs and `results.json`.
`tree/build.json` records the tag, inputs, environment and artifact hashes. Tests and packaging
use the same tree; About, iPod About, the preview and package use its tag.

Only a fully passing build becomes `latest`. `make flash` verifies its full test receipt,
package, target card and read-back hash. It never rebuilds. A failed dev run leaves the previous
latest selected; check the printed tag, or choose `BUILD=out/dev/<tag>` explicitly. Use
`VOLUME=/Volumes/Name` for another card and `DRY_RUN=1` to check without copying or ejecting.

Dev tags reserve `V2.1z` plus four checkout-namespace letters and four counter letters. Keep
the gitignored `.dev-number.json`; never reset the counter or reuse an output directory.
Namespace collisions, moved worktrees and exhausted counters fail explicitly. Releases use `V2.1-<VERSION>` tags. No shared checkout state is written.

```sh
uv run python -I tools/check.py --list
uv run python -I tools/check.py --test albums/toggle_tests
uv run python -I tools/check.py --tests-only --jobs 4 --timeout 300
```

`JOBS=4` also works with Makefile test/build targets. The runner prints failures and one summary
line (`--verbose` prints every pass too); it reports completed tasks, native crashes and assertion
totals separately. Missing inputs/results fail; subprocess groups have
wall-time limits. Logs and failed trees are retained. `make clean` removes `work/check` only,
keeping dev artifacts, counters and caches. Locks prevent overlapping writes.

The runner reports build durations, test progress about every ten seconds as tasks finish,
and the three slowest tasks. Dev `results.json` also records `timings.setup`, `timings.tests`
and `timings.package` in wall seconds; setup includes input checks, tree construction and validation.

## CI

Start `.github/workflows/ci.yml` manually through Actions > ci > Run workflow or
`gh workflow run ci --repo imfing/m1plus-music` (macOS runners cost 10x). Its `macos-latest`
job installs Homebrew `llvm lld squashfs librsvg`, firmware and Source Han Sans, then runs
`make setup`, `make doctor`, `make format-check` and `make dev` (lint, all tests and a verified
package). The run number seeds a fresh `V2.1z...` tag; `update.bin` is retained for 14 days.
CI neither checks goldens nor publishes. Releases stay local (`make check`, `make publish`):
Linux Pillow uses zlib rather than zlib-ng, changing PNG and merged CJK-font bytes.
PNG tests compare pixels.

The firmware zip is the asset of a prerelease (tag `m1plus-firmware-v2.1`) in this
repository, downloaded by CI with `GITHUB_TOKEN`.

Start UI fixes with a failing emulation test or device capture. Previews use the shared AWTK
layout/text model and the built font. Keep feature details and device checks in `docs/modules/`.

Previews: `tools/preview*.py` write to `out/preview/` (gitignored). Generate the release sheet with
`uv run python -I tools/preview.py WORKDIR`. Release packages and generated previews stay out of Git.

## Context budget

The 2026-10-25–11-01 audit found cache reads dominated cost: turns above 400k context accounted
for 45% of reads; subagents accounted for 72%. Keep sessions small:

- Give subagents one stage (probe, implement or test), ending with branch, commit and doc
  handoff; start the next stage fresh.
- One topic per session. Past ~250k context or at a topic change, document conclusions and
  compact/start fresh. Close unused sessions.
- Search large files first, then read relevant ranges. Do not reread unchanged files;
  `docs/history.md` is for people, not agent context.
- Crop/zoom images with `tools/peek.py`, then read once.
- Batch mechanical edits with `tools/sub.py FILE... --pairs PAIRS.json --stat`.
  Run selected tests while iterating and the full suite at completion.

## C formatting

Run `make format`, then `make format-check` for tracked payload C/headers. `.clang-format`
defines four spaces, attached braces and 120 columns; include order and comment wrapping stay
unchanged. Select Homebrew clang-format with `LLVM_BIN` or `CLANG_FORMAT`. Keep formatting
separate from functional changes and verify package hashes afterward.

## Python lint

`make lint` runs pinned Ruff bug/syntax checks (pyflakes), without formatting. Test, dev and
check targets run it first. Star-import exceptions cover `test/pod/*.py` and
`tools/preview_tape.py`; the harness may import names for re-export.

## Integration and restore

Feature branches leave release `VERSION`, goldens and history unchanged. The README names no release.
GitHub releases and git tags use plain `VERSION` without a `v`; dev About shows the dev tag.
At integration, bump `VERSION` in `tools/build.py` (semantic: patch for fixes, minor for features, major by decision;
`TAG = V2.1-<VERSION>` is the package version the updater compares, About shows the plain `VERSION`; dev tags stay `V2.1z...`), then run:

```sh
make check                     # both packages and all tests against existing goldens
make accept                    # accept intended changes; reuse complete matching evidence
```

CHANGED and NEW fail until accepted. Acceptance requires both packages and every test;
`--no-tests` and `--only` cannot bypass it. Reuse validates inputs, test coverage and package
hashes. Source changes during a run invalidate its evidence. Commit the golden and README
status; add history only for milestones or device findings. Resolve golden/history conflicts
from the integration side and rerun.

Checked packages stay in `work/check/release/out` and `work/check/restore/out`. Direct builds
retain the established `out/M1Plus-<tag>-release-update.bin` naming:

```sh
uv run python -I tools/build.py
uv run python -I tools/build.py --restore
uv run python -I tools/fwtool.py verify out/M1Plus-<tag>-release-update.bin
uv run python -I tools/flash_sd.py out/M1Plus-<tag>-release-update.bin
```

The `V2.1R` restore package (stock images, own tag) is a developer tool: users restore with Shanling's official V2.1 (`docs/modules/version.md`).

Release/restore copies require golden bytes; dev copies require a full receipt. There is no
`--force` bypass. `build.py --dev` alone creates no test receipt; use `make dev` for installation.
`--pack-only` rejects stale trees. Payload edits retain the font/base cache; `--no-cache`
supports cold-build comparisons.

## Publish

After the integration commit and a matching `make check`, `make publish` uploads the golden release
package (as `update.bin`, with `SHA256SUMS`) to a draft GitHub release named `VERSION` (for example `1.0.0`) created with
`--target HEAD`, notes = the golden's last commit message; it downloads the assets back and compares
hashes. It creates and pushes no tag (q2-pod's model): GitHub creates the tag `VERSION` at HEAD when the draft
is published. Review the draft, then `make publish PUBLISH=1` (or publish it on GitHub). `DRY_RUN=1`
checks and stages `out/publish/<VERSION>/` only. It refuses a dirty tree, a package that is not the
golden, a local tag on another commit and an already published release. The restore image stays local.

## Device checks

Follow [Install](install.md) for card preparation, update confirmation and restore. Use
[device checks](modules/device-checks.md) and the feature's module doc to validate a build. Record the tag,
pass/fail/untested status and captures. Emulation does not certify hardware timing or appearance.

**Settings → Developer → Screenshot** asks first, then captures after five seconds.
See [capture details](modules/screenshot.md). With the card mounted:

```sh
uv run python -I tools/pull_shots.py --build latest
uv run python -I tools/peek.py info out/dev/<tag>/device/<capture>.png
```

Content hashes prevent filename collisions; sidecars record capture/build identity. Remote
screenshots, logs, input and update navigation remain future hardware-validated work.
