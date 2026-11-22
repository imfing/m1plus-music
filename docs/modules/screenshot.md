# Screenshot

**Sources:** `patch/shot.c`, `patch/shot.h`, `tools/pull_shots.py`.
A developer's screen grab: the Screenshot row of Settings > Developer (`ACT_SHOT`, page
`m1plus_developer`). No stock function is hooked and nothing runs at boot, in the main loop or at
paint. A tap starts a payload-owned countdown; the only code that runs afterwards is two timer
callbacks. The menu entry gates the row, so it has no kill-switch check of its own.

## Flow

Two entries call `shot_start()`: the Developer row and the Control Center tile `f` ([pulldown](pulldown.md)).

1. **Confirm.** The stock confirm dialog (`pod_confirm`, [overlays](overlays.md)) asks "Take a
   screenshot?". Only Yes goes on.
2. **Delay.** A second dialog, "Take a screenshot in:", has the delay as its two buttons: 5 s
   (left) and 10 s (right). Anything else cancels.
3. **Countdown.** A 1 s timer shows the camera in the status bar and counts down. The last tick
   hides the camera and arms a one-shot (`SHOT_SETTLE_MS`, 120 ms) so the main loop repaints
   first.
4. **Capture.** The one-shot reads the panel and writes the file. The toast follows the capture so
   it is not in the picture: "Screenshot saved", "Storage unavailable" (no card, no room, no
   directory) or "Screenshot failed". A refused timer is a failure toast with the camera hidden.
5. **Cancel.** A tap on the row during the countdown asks "Cancel the screenshot?". Yes removes
   the tick timer and hides the camera. No leaves the countdown
   running (the Cancel dialog stays Yes / No). The dialog is modal, so ticks may run under it: the
   phase is read again when it returns, and a countdown that ended meanwhile is not cancelled. A tap
   once the capture is committed does nothing.

The user may leave the Developer page during the countdown: the state belongs to the payload, not
the page.

**Why two steps:** the back key does not close `confirminfo_dialog` (device finding), so one
dialog with the delay on both buttons would have no way out. No stock dialog offers three free
choices, so the delay dialog is stock's Yes / No relabelled "5 s" / "10 s" by a short timer that
finds the dialog once it opens (at most `SHOT_RELABEL_TRIES` turns). If the timer is refused the
buttons stay Yes / No (Yes = 10 s). The dialog's quit code is the result: 4 = 5 s, `CONFIRM_YES` =
10 s.

## Why the frame buffer

It is what is on screen: status bar, dialogs and Cover Flow's own drawing.
`widget_take_snapshot_rect` repaints one widget tree, misses the separately painted system bar and
re-runs page paint code.

The payload opens `/dev/fb0` on its own descriptor (read-only, `mmap` `PROT_READ`) and never
assumes the format. It reads the geometry (16, 24 or 32 bit, per-channel offsets and lengths,
`line_length`, `yoffset` for a panned buffer) with stock's two `FBIOGET` ioctls. The frame must
lie inside the mapping and be at most 1024 x 1024, or the capture fails.

## File

`/mnt/mmc/screenshots/shot-NNNN.bmp`, NNNN the first free number from 0001 to 9999. A 24 bit
bottom-up BMP, written to `shot.tmp` row by row, `fsync`ed and renamed; any failure unlinks the
temp file. Before writing: the card is mounted, the directory exists and the card has
`SHOT_MIN_FREE_MB` (16) plus the file free.

`tools/pull_shots.py [CARD_DIR] [--build latest|DIR]` imports the files as PNG. Names include the
source content hash, so another card reusing `shot-0001.bmp` loses nothing. JSON sidecars record
the original path and hash (and the dev tag and package hash with `--build`, which stores into
that artifact's `device/` directory; otherwise `out/shots/`).

## Status bar camera

`pod_shot` is a hidden, insensitive 16 px image (Lucide `camera`) that `add_shot_indicator` in
`tools/pod_ui.py` appends to `view_bar_right` in `ui/system_bar.bin`. While hidden the bar lays
out as stock. Shown, it sits against the battery and the icons to its left move 20 px. The payload
looks it up each time; a missing widget only means no camera. The pull-down's own bar gets none.
It shows only with room beside stock's marks left of the clock (`lo_shot_fits`, and the bar's 1 s
tick hides it if the room goes; [lineout](lineout.md) "Room"); the countdown and capture run either way.

**No "saved" glyph:** the toast already says it, and a second state would need a second timer and
image for no new information.

## Pins

Stock `timer_add`, `widget_lookup`, `widget_set_visible`, `window_manager`, `locale_info_tr`, the
stock message box, and demo's own GOT slots for `ioctl`, `mmap`, `munmap`, `statfs`, `mkdir`,
`open`, `write`, `fsync`, `rename`. `tools/pod.py` checks every address and slot at build time.
