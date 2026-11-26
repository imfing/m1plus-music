# AGENTS.md

Firmware mods for the Shanling M1 Plus, built from official V2.1 and packaged as a TF-card
`update.bin` ([README](README.md)). This is the only instruction file.

## What to read

Read only the rows that match the task, and in each file only the sections you need
(`grep -n '^## '` first). Never load whole large files or `docs/history.md`.

| Work | Read |
|---|---|
| New page, setting row, hook or source file; where a registry lives | [Change recipes](docs/recipes.md) |
| Commands, worktrees, tests, formatting, releases | [Workflow](docs/workflow.md) |
| Runtime changes | [Safety](docs/modules/safety.md), [architecture](docs/architecture.md) (module index) |
| Binary searches or patches | [Payload](docs/modules/payload.md), [addresses](docs/modules/addresses.md) |
| UI changes | [UI rules](docs/modules/ui-rules.md), [UI reference](docs/ui.md), the feature's module |
| Test boundaries | [Validation](docs/modules/validation.md) |
| Install, restore, firmware | [Install](docs/install.md), [firmware](docs/firmware.md) |

Everything else is in the [documentation index](docs/README.md).

## Working fast

- Start from the matching recipe and its precedent (`git show --stat <sha>`), not from a search.
- Batch independent reads, greps and Edits as parallel calls in one turn. Don't reread
  unchanged files. Crop images with `tools/peek.py`, then read the result once.
- Size the checks to the change ([workflow](docs/workflow.md) "How much to run").
  - Iterate with `make test TEST=<module>/<section>`. Rerun only the sections that failed.
  - Docs only: `TEST=docs`, no `make dev`.
- Run `make dev` once, after the last edit. Don't run a full `make test` before it.
  - On failure, fix it, rerun the failing sections, then `make dev` once more. Never loop on it.
  - On an unchanged tree, `make dev` reuses the passing build, so don't force a rerun.
- Before a heavy run (`make dev`, `make check`, full `make test`), check
  `pgrep -f '[t]ools/check.py --dev'` and wait if one is running; parallel runs double the time.
  Keep the brackets: without them, a waiting shell loop matches itself and the others
  (deadlock).
- In a worktree, use relative `make …`. From outside, use `make -C <worktree> …`.
- Edit with the editor or `tools/sub.py`. No heredocs, multi-line `sed -i` or git chains.

## Subagents

- Subagents run targeted sections only. They never run `make dev`, `make check` or a full
  `make test`, and they don't commit unless told to. The caller runs `make dev` after hand-back.
- Effort: low for routine work (clean rebases, preview tweaks, doc edits, renames, mechanical
  fixes), medium for review fixes and small features. Use the default only for new feature
  phases, hard bugs and conflicted rebases.
- One fresh agent per stage, under about 60 turns and 200k context. The handover goes in the
  module doc. For visual tweaks, batch the edits and render one preview.
- A brief carries:
  - the worktree and branch, and that `make setup` is done
  - the recipe and its precedent sha, with the exact files and functions to change; at most one
    module doc, naming its sections
  - the facts the caller already has (addresses, hook number, names, sizes, strings), marked
    verified or not
  - the exact `TEST=` sections, including collateral ones
  - a hand-back of at most 200 words: files, sections run with pass/fail, deviations

  Don't paste these rules into the brief.

## Rules

- Never execute extracted firmware or code from a reference clone. Clone references outside the
  repo, and keep borrowed-code attribution in file headers and module docs, and q2-pod in the README acknowledgements.
- Pin every binary edit and fail on a mismatch. Hooks fall back to stock. A pinned
  boot-reachable hook that does bounded work and falls back is an approved path.
- Never widen the global paint scope (only the palette's three hooks,
  [accent](docs/modules/accent.md)) or the main-loop scope. Keep the crash guard and the
  `/mnt/mmc/m1plus-off` kill switch. Never write the bootloader or the recovery kernel.
- UI bug fixes need a reproducer (a test or a capture); look-only tweaks need a preview. Previews
  use the shared layout/text model and the built font.
- Keep widget names. Hidden widgets are also made insensitive.
- Feature branches leave `VERSION`, goldens and history unchanged; integration owns them.
- No compatibility flags, and no code paths that exist only for old packages. Exception: when a
  released settings record changes format, the loader also reads the last released format, so
  users keep their choice; mark it temporary and drop it a few releases later.
- Bluetooth work only for approved features ([Bluetooth](docs/modules/bluetooth.md)).
  `hciplayer` is patched only for PEQ, Mono / Crossfeed, Crossfade, the read-only VU tap, the
  read-only radio ICY metadata tap and the non-MQA probe skip ([peq](docs/modules/peq.md),
  [stereo](docs/modules/stereo.md), [crossfade](docs/modules/crossfade.md), [vu](docs/modules/vu.md),
  [radio](docs/modules/radio.md), [mqa](docs/modules/mqa.md)). Any other Bluetooth or `hciplayer`
  change needs a decision first.
- Module docs describe the code as it is now: behaviour, interfaces, constraints and sources.
  Allowed on main: known limitations and gaps, and short "possible improvements".
- Planning is for implementation only. Leave none of it on main: no handover, phases,
  decision logs, "not done" or next steps, device-test status, history or test inventories.
  `TEST=docs` rejects such headings on main.

## Keeping instructions current

- A change that adds a registry, a touchpoint or a recurring step updates
  [recipes](docs/recipes.md) in the same commit. A removal deletes its doc lines. Before
  the squash merge, rewrite the module doc as the final reference, with the planning taken out.
- A new rule replaces or merges into an existing one. `make test TEST=docs` checks size
  budgets, links, the module index, and that the paths, symbols and commits named here, in
  workflow.md and in recipes.md still exist.
- At every release integration, or when a `TEST=docs` budget fails, review in one pass:
  - this file, workflow.md and recipes.md: add recipes for new patterns, merge overlaps, drop
    stale rules
  - agent memory: fold merged items into summary lines
  - module docs changed since the last tag: remove handover, Tests and phase sections
