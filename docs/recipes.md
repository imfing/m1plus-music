# Change recipes

Checklists for the most common changes. They list every place that change touches, so that you
don't have to find them by searching or from failing tests. Copy the named precedent; then read
only the module doc of the feature you are changing. Symbols are given instead of line numbers:
`grep -n` for them.

## Where things live

| What | Where |
|---|---|
| Page registry: `Page`, `Row`, `PAGE_ORDER`, `*_PAGE_INDEX`, `ACT_*`, `SWITCH_/VALUE_/CHECK_/ACTION_ACTIONS`, `VALUE_INIT`, `SETTING_FILES`, `INFO_*` | `tools/pod_pages.py` |
| Card and row geometry (`ROW_H`, `*_CARD_H`) | `tools/pod_settings.py` |
| Card types to widgets (layout, names) | `tools/pod_ui.py` |
| Page builder, payload sources (`SOURCES` list near the top), stock symbols and data (`FUNCTIONS`, `DATA`), `POD_<X>_PAGE` macros (`gen_stock_h`), `--undefined=` symbols (`compile_payload`), hook writes and `check_pins` (`patch_demo`), manifest `hook_*` keys (`main`) | `tools/pod.py` |
| Pinned sites and words (`<X>_SITE`, `<X>_PINS`) | `tools/pod_pins.py` |
| Player Crossfade decoder calls, vendor FLAC seek threshold isolation, and the kept output (driver slots `AO_SLOTS`, wrapped calls `UNINIT_CALLS`) | `patch/xfade.c`, `patch/xfsrc.c`, `tools/mod_player.py` `PINS`; [Crossfade](modules/crossfade.md) |
| Our strings, all languages (`_t('English', zh_CN, zh_HK, ja, ko, fr, de, es, it, th, pl, ru, uk)`) | `tools/pod_i18n.py` |
| Row icons (label to Lucide name) | `tools/mod_icons.py` `CARD_GLYPHS` |
| Row dispatch: `ACT_*` / `INFO_*` (generated into `acts.h` from `pod_pages.py`), `on_row`, the `pod_switch` table, `open_page` (per-page binding after the window opens), `pod_open_*` | `patch/m1plus.c` |
| Shared declarations: setting file paths (`*_FILE`), `pod_open_*` | `patch/home.h` |
| Payload entry points called across files, hook functions | `patch/entries.h` |
| Stock offsets and shared C constants | `patch/offsets.inc` |
| Settings Files list (every persisted file) | `patch/setfiles.c` |
| Emulator harness and its stubbed stock calls | `test/pod/harness.py` |
| Settings layout tests, the full page list | `test/pod/settings.py` |
| Settings previews (page state in the `STATE` dict near the top) | `tools/preview/preview_settings.py` |
| Hook inventory (numbered) | [payload](modules/payload.md) "Hook sites" |
| Stock addresses table | [addresses](modules/addresses.md) |
| Multi-select on a list page (`m1_sel_*`) | `patch/selmode.c`, [select mode](modules/selmode.md) |
| Module doc index | [architecture](architecture.md) |

`uv run python -I tools/check.py --list` lists every test section. Run the sections named below.

## Switch row (a persisted on/off setting)

Precedent: Settings > Now Playing > Track Position (`git show 2ef3283a`).

1. `tools/pod_pages.py`: new `ACT_<X> = <next free id>`, the next unused number above the
   current maximum, with a comment saying where it is used. Add it to `SWITCH_ACTIONS`, and add a
   `Row('<Label>', ACT_<X>)` to the page's `layout`. If the setting is persisted, append its file
   name to `SETTING_FILES`, then increase `INFO_DUR` and `INFO_SFOLD` by one. The
   id is written only here: `tools/pod.py` generates `acts.h` for the payload.
2. `patch/m1plus.c`: add `{ACT_<X>, <x>_setting, <x>_toggle}` to the `pod_switch` table.
3. `patch/home.h`: `<X>_FILE` (`/mnt/data/m1plus/<name>`; state about library items
   goes on the card in `/mnt/mmc/.m1plus/`), plus the setter and getter declarations. Implement
   them in the feature's `.c` file with `home_write_atomic` or `home_set_digit` (they write
   `<X>_FILE.tmp` first and then rename it over the real file; no temp-path macro).
4. `patch/setfiles.c`: add `{<X>_FILE, K_CHAR}` and bump the count in the comment.
5. `tools/pod_i18n.py`: add `_t(...)` for the label and any note. `tools/mod_icons.py`: add the
   row icon.
6. Tests: the feature's module test, plus `settings/layout_tests` and `i18n`.
7. Docs: [settings](modules/settings.md) "Persisted choices", the feature's module doc and
   `docs/settings-guide.md`.

## Value row and picker page

Precedent: Lyrics Text Size (`ACT_LYRSIZE`, `ACT_LYRSIZESET`, `LYRSIZE_PAGE_INDEX`).

- The value row's `ACT_` goes into `VALUE_ACTIONS` and `VALUE_INIT`. The picker's rows use a
  second `ACT_..SET` in `CHECK_ACTIONS`. The picker is its own `Page` (see the next recipe).
- `patch/m1plus.c`: add the pick definition that `pick_set_of` finds, and the value text.

## Own page (a new settings page)

Precedent: a plain list page is `m1plus_psmaxvol` or the Sleep Timer page. A page with its own
card type is the Volume page (`git show 5b68e831`).

1. `tools/pod_pages.py`:
   - Write `<X>_PAGE = Page('m1plus_<x>', 'm1plus_<x>_page', '<Title>', layout=[...])`.
   - Append `'m1plus_<x>'` at the END of `PAGE_ORDER`, so that no other page's number moves.
   - Add `<X>_PAGE_INDEX = page_index('m1plus_<x>')`.
   - Add the parent row `Row('<Title>', ACT_PAGE, <X>_PAGE_INDEX)`, or the feature's own `ACT_`.
2. `tools/pod.py`: add `'<X>'` to the macro tuple in `gen_stock_h` when C code needs
   `POD_<X>_PAGE`. Add new `.c` files to the sources list near the top, and add new
   cross-file payload symbols that nothing else references to `--undefined=`.
3. A new card type: add a class in `pod_pages.py`, its widgets in `pod_ui.py`, its height in
   `pod_settings.py`, and a branch in `test/pod/settings.py`'s layout walk
   (`isinstance(it, P.<Card>)`).
4. `patch/m1plus.c`:
   - If the page binds stock handlers or its own widgets, add an `else if (index == POD_<X>_PAGE)`
     branch in `open_page` that calls `<x>_opened(win)` (declared in `entries.h`).
   - If other code opens the page, add `int pod_open_<x>(void)` (declared in `home.h`).
5. Strings: `tools/pod_i18n.py`. A term that stays English in every table goes into
   `SAME_AS_ENGLISH` in `test/pod/i18n.py`.
6. `test/pod/settings.py` has the full list of page keys. Add the new key there.
7. Preview: add a state to `STATE` in `tools/preview/preview_settings.py` and the page to its sheet.
   To check the layout, run that script directly, then crop the result with `tools/peek.py`:
   `uv run python -I tools/preview/preview_settings.py work/check/release/work/mod-release`.
8. Tests: a new `test/pod/<x>.py` that follows the precedent's test, plus `settings/layout_tests`,
   `i18n`, `assets` and `navbars`.
9. Docs: a module doc `docs/modules/<x>.md` with its row in [architecture](architecture.md), plus
   [settings](modules/settings.md) "Page tree" and the user guide.

## Call-site hook (stock calls ours instead of a stock function)

Precedent: the Volume page's tap (`VOLUME_SITE`, hook 33, `git show 5b68e831`). Read
[safety](modules/safety.md) first. A boot-reachable site needs bounded work and must fall back
to stock.

1. `tools/pod_pins.py`: add `<X>_SITE = 0x...` and `<X>_PINS`, which pin the site word, its
   delay slot, the surrounding instructions that the hook relies on, and the prologue of every
   stock function it calls. Each entry is `(addr, word, reason)`.
   Read words with `uv run python -I tools/stock.py addr ADDR [LEN]` (also `sym`, `callers`,
   `strings`; it finds the stock tree from a worktree too).
2. `tools/pod.py`:
   - Add `<X>_PINS` to the `check_pins(...)` sum in `patch_demo`.
   - Add the `struct.pack_into(... jal(ps['<fn>'], <X>_SITE))`.
   - Add the site to the hook-overlap tuple (`HOME_CLICK, HOME_INIT, ...`).
   - Add `--undefined=<fn>` and `'hook_<x>': {...}` in `main`'s manifest.
   - Stock symbols that the C code calls go in `FUNCTIONS` and `DATA`.
3. `patch/entries.h`: declare the hook function with a `payload hook N` comment. On any failure,
   the function calls the stock function it replaced.
4. Tests that list every hook:
   - `test/demo_diff.py` (`allow(...)` and its check)
   - `test/pod/rows.py` (`allowed`)
   - `test/pod/lyrics.py` (the manifest `hook*` keys)
   - the harness stub, if the hook calls an unstubbed stock function.
5. Docs: a row in the [payload](modules/payload.md) "Hook sites" table (the next free number) and
   the [addresses](modules/addresses.md) row.

## New payload source file

1. Add `patch/<x>.c` to the sources list in `tools/pod.py`, and declare its entry points in
   `patch/entries.h`.
2. Stock calls go through the `FUNCTIONS` table, which generates `stock.h`. Before adding a
   stock symbol, grep `tools/pod.py` for it.
3. Run `make format` after editing C.

## Rootfs binary or kernel module patch (`tools/mod_<x>.py`)

Precedent: `tools/mod_bluealsa.py` (one byte in `/usr/bin/bluealsa`) and `tools/mod_uac2.py`
(relocated `.text` in `/module_driver/soc_aic.ko`, [uac2](modules/uac2.md)).

1. `tools/mod_<x>.py`: pin the stock input by SHA-256 and exact offsets/bytes/ELF fields, raise
   `ValueError` on any mismatch, preserve stock mode and mtime with `write_keep_mode`, and leave
   the kernel `xImage` untouched.
2. `tools/build.py`: append `('mod_<x>', [])` to `STEPS` (if it adds files, implement `added_rels`).
3. `test/pod/<x>.py`: verify stock pin, determinism, mode/mtime, refusals on bad input, ELF/disasm
   checks, and Unicorn execution of any injected machine code.
4. Docs: `docs/modules/<x>.md` with rows in [architecture](architecture.md) and
   [pipeline](modules/pipeline.md). Run `make test TEST=<x>,docs`.

## Collateral to expect

- Adding a top-level icon PNG prefix: add the prefix to `NEW_IMAGES` in `test/pod/navbars.py`.
- Changing what stock `ui/*.bin` contains changes `test/navbars-stock.sha256`. Regenerate it
  only when the change is intended.
- `docs/guide.md` and the other user guides need updating for user-visible changes.
