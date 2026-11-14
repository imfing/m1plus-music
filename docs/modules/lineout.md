# The Line Out pill, the EQ mark and the sync icon (`patch/lineout.c`, `patch/lineout.h`, `test/pod/lineout.py`; hook 20 in [payload](payload.md))

**Behaviour.** While Line Out is on (stock's byte `0xa05aa7`), the status bar shows an amber pill with a black "LO" in place of stock's white "LO" text, and the same in the
pull-down's own bar copy. Always on: no setting. Everything else is stock: the volume glyph beside it, the volume number in PO mode, the pull-down's Output tile, and the "Line Out sets max volume" confirm.

**Stock.** `show_sysbar_face` (`0x544b48`, the status bar's 1 s timer) and `dropdown_showface` (`0x475c3c`, the pull-down's `view_sysbar`, its own timer) each show `label_volume` (`widget_set_visible(s7, 1)`,
`0x544d90` / `0x4758d8`), then fill a buffer with `strcpy("LO")` (`0x544f7c` / `0x475ac4`, when the byte is set) or `sprintf("%d", volume)`, and join at one call, `widget_set_text_utf8(label_volume, buffer)`
(`0x544f90` / `0x475ad8`). These are the only two "LO" sites.

**The hook.** Both `jalr` words become `jal lo_set_text` (`move a0, s7` stays in the delay slot, `a1` is the buffer). `lo_set_text` runs stock's function first, then finds the pill `pod_lo` among `label_volume`'s siblings
(`widget_lookup(parent, "pod_lo", 0)`, parent at `widget_t + 0x44`). If the text is exactly `LO` and `/mnt/mmc/m1plus-off` is absent, it hides the label and shows the pill (`visible` and `sensitive` both, as hidden widgets must be insensitive);
otherwise it shows the label and hides the pill. It runs in both timers right where stock sets the text and after stock's own show of the label in the same call, so there is no lag and no frame with both or neither (the UI thread paints between timer calls). With the kill
switch present, or no `pod_lo` in the bar (an asset from another build), stock's text stays. Cost: one `access` and one lookup in a small group per tick per bar, a few hundred instructions; no allocation, state or thread. Not on the boot path (`tools/reach.py`:
the same page-init dispatcher as the battery hook). Each site is pinned with its neighbours and the Line Out byte test (`LINEOUT_PINS` in `tools/pod_pins.py`); a mismatch fails the build.

**The pill.** `pod_lo` is an `image` (30 px wide like `label_volume`, the 26 x 16 picture centred by `draw_type` center; hidden and insensitive in the file) right after `label_volume` in `view_bar_left`, added by `tools/statusbar.py` so the real bar and
`dropdown_dialog.bin` are identical (`test/pod/assets.py` compares them). The group's layouter skips an invisible child, so the pill takes the label's place at the same width and the digital-out glyph does not move. Image `pod_bar_lo` (`tools/mod_icons.py` `lo_pill`, committed PNG): amber `#FFD60A` fully rounded pill, black "LO" in Inter Medium 12 px with a 0.33 px stroke, 8x supersampled. It is not the Accent Orange `#FF9F0A`; the accent never tints it
(not in `ACCENT_*` or the glyph prefixes) and Light Mode's flip leaves it (it has colour). `tools/preview/preview.py` writes `lineout.png` (bar off, bar on, the pull-down's bar on).

**Limits.** The pill is an asset swap, so the pull-down's bar shows it up to a second after Line Out changes, as stock's text did.

## EQ mark

**Behaviour.** While the Equalizer switch is on (stock's `equalizer_flag`, the byte the [Equalizer page](peq.md) and the per-output EQ keep), the status bar shows a white "EQ" after the volume number (or the Line Out pill), and the
pull-down's bar copy shows it too. It follows the switch, not the sound: DSD plays without the EQ and the mark stays. No setting. Stock's M1 Plus bar has no EQ widget.

**Implementation.** No new hook: `lo_set_text` calls `lo_eq` after `peqout_sync` (which can turn the switch for a new output). It looks up `pod_eq` among `label_volume`'s siblings and sets it visible and sensitive together when the byte is
set, the kill switch is absent and stock's digital-out glyph `img_digital` is hidden; only on a change. A bar without `pod_eq` is left as it is. Cost per tick per bar: one or two lookups in the small group.
The widget is added by `tools/statusbar.py` `apply` to both copies: a `label` with the text `EQ` in `label_volume`'s white at 16 px, the volume number's size (19 px wide, the text's width), hidden and insensitive, right after `pod_lo` in `view_bar_left`.

**Placement.** Left group: play state, volume glyph, volume number, the mark end at x 100, clear of the 12 h clock's ink at 116 (`test/pod/lineout.py`). With the digital-out glyph as well the group would end at 126, over the clock,
so the mark gives way to the glyph. Stock sets the glyph later in the same tick, so the mark follows it one tick late.

`tools/preview/preview.py` writes `eqmark.png` (off, on, on with Line Out, the pull-down's bar).

**Limits.** Not device-tested. The mark is the default white: the Accent does not tint it.

## Sync icon

**Behaviour.** While the shared cover worker runs a set with work left (a cover build, Rebuild Covers or a track-duration pass, whichever page owns it: Home, Albums, Songs, Cover Flow, an album page), the status bar shows a static white sync glyph
(Lucide `refresh-cw`, 18 x 18, 1.5 px stroke), and the pull-down's bar copy shows it too. It is the same glyph colour as the other white status icons (not Accent-tinted; Light Mode flips it with them). Hidden otherwise. No setting.

**Implementation.** No new hook: `lo_set_text` (hook 20, both bars' 1 s timers) first looks up `pod_sync` in the bar (`widget_lookup(bar, "pod_sync", 1)`, the bar is `label_volume`'s parent's parent, `LO_W_PARENT` twice) and sets it visible and sensitive together when
`cc_build_active()` (`patch/covercache.c`: `running`, not `cancelled`, `done < total`, a cache or duration set rather than the Pod cover pane's key-0 file job; volatile reads, no lock, no file) is true and the kill switch is absent, hidden and insensitive otherwise.
It sets only on a change (`widget_get_visible` differs), so a steady state costs no relayout. A bar without `pod_sync` (an older asset) is left as it is. Cost per tick per bar: one extra lookup and a handful of loads. Not on the boot path.
The widget is added by `tools/statusbar.py` `apply` to both copies (`test/pod/assets.py` compares them): an `image` (`pod_bar_sync`, 18 px wide, `draw_type center`, hidden and insensitive) in `view_bar_right` right after `img_btclass`. Image `pod_bar_sync` (`tools/mod_icons.py` `SYNC_BAR`, committed PNG).

**Placement.** Right group, between the Bluetooth glyph and Wi-Fi (the layouter skips it while hidden, so nothing moves otherwise). Left of the Bluetooth glyph itself is not possible: the stock `img_btclass` box is 47 px wide with its glyph at the right
end (ink x 35..47), so the slot left of the box lies over the clock text. Shown, the icon moves Bluetooth's glyph 22 px left: with Bluetooth and Wi-Fi lit the ink starts clear of the 12 h and 24 h clock (`test/pod/lineout.py`); with the Battery Percentage at 4 characters and the Screenshot camera counting down as well it would not (rare, accepted).

**Priority.** The worker runs at nice 10, see [Home cover build](homecover.md).

**Limits.** Hardware behaviour is not covered by emulation.
