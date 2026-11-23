# Build pipeline

`tools/build.py` builds the release from the pinned official zip (`firmware/`, SHA-256 in
`build.py`); `--restore` repacks stock with tag V2.1R. Every step edits one work tree in place
(`work/mod-release`, per checkout); inputs resolve through `tools/paths.py`. uv owns the Python
environment; this module only resolves data. Everyday commands: [`../workflow.md`](../workflow.md).

| # | step | what |
|---|---|---|
| 0 | `fwtool.py unpack` (first run only) | `work/stock`: `rootfs/`, `recovery-update/`, `stock.pseudo` (exact inode metadata), `meta.json` |
| 1 | `mod_battery.py STOCK TREE` | clones stock into the tree; unified battery in the status bar and the pull-down |
| 2 | `mod_font.py` | Inter + Source Han Sans; runs here so every later step measures the new font |
| 3 | `mod_space.py` | zero demo's `.pdr`, remove unreferenced files and the stock theme1 tree ([firmware](../firmware.md)) |
| 4 | `pod.py` | compile the payload, append it to `demo`, install the pinned hooks, apply the library-row edits and write the custom page assets |
| 5 | `mod_theme`, `mod_lists`, `mod_nowplaying`, `mod_boot`, `mod_ipodrows`, `mod_pulldown`, `mod_lockscreen`, `mod_wallpaper`, `mod_icons`, `mod_strings`, `mod_polish`, `mod_overlays`, `mod_cacerts`, `mod_webapp`, `mod_wpa`, `mod_player`, `mod_bluealsa`, `mod_uac2`, `mod_watchdog` | the asset looks and the other payload-adjacent edits, in this order (`STEPS` in `tools/build.py`, [ui](../ui.md)); `mod_strings` adds our translation keys to the 16 string tables; `mod_player` patches hciplayer; `mod_bluealsa` clears one AAC capability bit in bluealsa ([Bluetooth](bluetooth.md#aac-at-48-khz)); `mod_uac2` patches `soc_aic.ko` for USB DAC XRUN recovery ([USB DAC](uac2.md)); `mod_watchdog` replaces `/usr/bin/checkappprocess.sh`'s 2 s `pgrep` fork with an in-shell `/proc/$DEMO_PID/comm` read (leaving only `sleep 2`) while keeping the `pgrep` fallback and `reboot` on exit |
| 6 | `mod_theme.py --scan TREE STOCK` | contrast scan of the finished tree (a pass is cached with the steps) |
| 7 | `fwtool.py repack --tailends --allow-removed ... --allow-added ...` | squashfs (LZO, 128 KiB blocks, tail ends), metadata-exact; refuses a rootfs larger than stock or any unlisted added/removed file; `verify` follows |

Each step lists the files it adds through an `added_rels()` function, which `build.py` passes to
`fwtool --allow-added`. `work/mod-release/podbuild/` (manifest.json, patch.elf) stays for the tests.
Builds are deterministic (added files get fixed mtimes); `tools/check.py` compares the package with
`test/golden.sha256`. Order matters: lock screen layout needs `mod_nowplaying`'s `np_*` glyphs and the
final font; icons run late so they override the theme step's grey discs; the lock screen step also
patches four words of `demo` and so runs after `pod.py`.

Toolchain: Homebrew clang/LLD/llvm-objcopy/llvm-readelf (`$LLVM_BIN`, `$LLD_BIN`; Apple clang has no MIPS
target), unicorn for the tests, mksquashfs. Python runs with `-I` on anything touching extracted
firmware.

Feature source maps are in [architecture](../architecture.md); test boundaries are in
[validation](validation.md). `tools/pod.py` is the authoritative source/order list and `tools/pod_pins.py` the pin list;
`pod_pages.py` defines page actions, `pod_ui.py` emits assets and `pod_i18n.py` supplies texts.
Dev builds use the same stages with an allocated tag and final manifest; see [workflow](../workflow.md).
