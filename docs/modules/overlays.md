# Overlay screens

**Sources:** `tools/mod_overlays.py`, `tools/mod_overlays_pins.txt`, `assets/overlays/`,
`tools/coex.py`, `tools/pod_i18n.py` (`COEX_TEXT`), `patch/m1plus.c` (`pod_confirm_dialog`).
Two stock-looking screens restyled with assets only (no new or renamed widget): the message and
confirm dialogs and the power-off splash. The step runs after `mod_polish` in `tools/build.py`. It
copies PNGs committed in `assets/overlays/` (`mod_overlays.py --generate` redraws them), refuses any
file that is not the pinned stock one (SHA-256, `--pins`) and keeps the file mode and pixel sizes.
The Update Library spinner, the charging bolt and the USB / Wi-Fi / Bluetooth mode pages are drawn by
`tools/mod_icons.py` ([icons](icons.md)), not here.

## Message and confirm dialogs

`msginfo_bg` and `confirminfo_bg` are 260 x 180 glass cards (`mod_icons.glass_image`, the More
sheet's pane at alpha 0.94, the page dimmed behind). The confirm card also has a 13 % white
horizontal divider at y 130.

- The stock buttons were opaque black over the image. The buttons of `confirminfo_dialog` and
  `rippercompleted_dialog` get a transparent `bg_color` in the non-pressed states and pressed corner
  radii 11. The vertical divider is `btn_cancel`'s right border, because the ripper dialog has no
  second button. Widget names and rectangles are unchanged and the contrast scan passes.
- The card is translucent, so a dialog opened over the More sheet would show it through. The sheet
  closes first ([playmore](playmore.md)).
- **Message padding.** The stock confirm dialog creates its kind-5 message in code, with a style
  nothing else uses (`label_centerwhite20_style`). `edit_confirm_label` gives that style 12 px
  `margin_left` / `margin_right`. Every kind-5 confirm gets it: ours and stock's Bluetooth / Wi-Fi
  switch-on questions. The label is 80 px high (three lines of 20 px); `test/pod/i18n.py` wraps every
  such message in 13 languages at 236 px. 12 px is the largest margin that keeps every message at
  three lines (20 px pushed the Wi-Fi question to four in twelve languages).
- **Dimming.** Stock's confirm does not visibly dim the page below, although its highlighter is set
  to alpha 130 (`CONFIRM_DIM` = `PL_DIM`). `pod_confirm_dialog` puts a full-window `#00000082` view
  as the top main window's last child, insensitive, before opening the dialog, and destroys it when
  the call returns. `m1_bar_scrim` dims the status bar with it. It uses only pinned stock functions. If the page closed meanwhile, or the view
  fails, the dialog opens without a scrim. Stock's own confirms (Bluetooth / Wi-Fi, stock delete
  questions) do not go through the wrapper.
- **Other message-like dialogs.** `cardupdate_dialog`, `formatcard_dialog` and `dialog_autoshutdown`
  were black with a grey `#666666` border; they get the same card (`CARD_DIALOGS`).
  `btscan_dialog` is left. `test/pod/overlays.py` compares the resolved card styles.
- The Software Update page clears its block around stock's install confirmation, because the page's
  pills stood out behind the translucent card ([update](update.md)).
- **Power-off splash** (`ui/poweroff_page.bin` `img_shutdown`, 320 x 480; the page is stock): the
  boot splash raster (`assets/boot-logo.svg`, [boot](boot.md)).

## Confirm dialog

Our yes/no questions (Rebuild Covers, Rebuild Artist Photos, Clear Cover Cache, Reset All Settings
and others) use the stock `dialog/confirminfo_dialog`, opened with `navigator_to_with_context`.

- The context is `{kind, ms, text[0x200], text2[0x200]}`; the text starts at +8.
- **Kind 5** gives wrapped 20 px text in a 260 x 80 box at y 25. **Kind 1** scrolls one line and
  must not be used for a long message.
- Only `CONFIRM_YES` (`0xa`, `btn_enter`) acts; No or a failed dialog does nothing.
- Stock's equalizer reset uses the same dialog.

## Wi-Fi and Bluetooth together

Stock keeps the two radios exclusive in the UI only. They are one RTL8733BS combo chip with both
drivers loaded at boot and BTCoex compiled in, and the switch functions never touch the other radio.
Turning one on while the other is on asked a kind-5 confirm (`msg_wifi_open` or `msg_bt_open`, "turn
the other off first?"); OK switched the other off, Cancel did nothing.

The confirm still appears, only when the other radio is on, but it is a warning now and OK leaves
the other radio on. Four pinned words in demo (`tools/coex.py`; no code added, nothing
boot-reachable, so no kill-switch wiring):

| Caller | Change | Skips after OK |
|---|---|---|
| Control Center Bluetooth tile | `beqz` becomes `b` | `wifi_switch(1)` (Wi-Fi stays on) |
| Bluetooth settings switch | `beqz` becomes `b` | `wifi_switch(1)` |
| Control Center Wi-Fi tile | first word of the preamble becomes a branch to the `wifi_switch(1)` call setup | the whole Bluetooth cancellation preamble |
| Wi-Fi settings switch (stock page, a fallback behind our own page) | same | the same preamble |

The Wi-Fi-side handlers do more before the switch: after OK they cancel a Bluetooth start in
progress (set `bt_exit_init`, wait up to 4 s, `switchBluetooth(1, 0)`). With only the switch-off
skipped, turning Wi-Fi on while Bluetooth was still starting aborted the startup worker and left
`bluetoothflag` 1: Bluetooth "on" but dead until an off/on cycle. So the Wi-Fi-side patch skips the
whole preamble. Cancel is unchanged. The words around each patch are pinned (`PINS`), so a different
firmware fails the build.

The text is one string under both keys, in the 13 language tables: "Bluetooth audio may stutter while
Wi-Fi is on." (`COEX_TEXT` has the other twelve). The buttons are stock's `msg_no` ("Cancel") and
`msg_yes` ("OK"). All 13 texts wrap to at most three lines. Audio stutter on 2.4 GHz (shared antenna
and band) is the expected risk.
