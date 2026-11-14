# Idle lyrics page

A full-screen page of our own that opens over Now Playing as an Idle Display destination (Settings > Now Playing > Idle Display > Lyrics). Apple-like: an 88 px header (the cover, the title and the artist, no
controls) over the synchronized lyrics, on the Now Playing cover tone with the light lyrics scrim.

**Sources:** `patch/idlelyrics.c`, `patch/lyrics.c` (`ly_retarget`, `ly_release`), `patch/minibar.c` (`mb_art_*`),
`patch/nowplaying.c` (`np_window`, `np_idle_color`), `tools/pod_ui.py` `build_idlelyrics_page`, `tools/pod_pages.py`
`IDLELYRICS_PAGE`, `tools/mod_nowplaying.py` (`np_scrim_idle`), `patch/offsets.inc` `IL_*`.
**Validation:** `test/pod/idlelyrics.py` (`asset_tests`, `open_tests`, `rows_tests`, `life_tests`, `layout_tests`, `touch_tests`, `fail_tests`, `dreams_tests`),
`test/pod/lyrics.py` `retarget_tests`, `LYRICS_PINS` in `tools/pod_pins.py`, `tools/preview/preview_idlelyrics.py` (the design
reference: header, large header, CJK, the three sizes, no lyrics; its lyric pitch and gap are `preview_lyrics.sized`'s).

## Page

`m1plus_idlelyrics_page`: a fullscreen 320 x 480 window (`fullscreen`, no status bar, as the Vinyl page) taking Now Playing's theme (`theme=playing_page`, for the
engine's `np_lyric_style[_m|_s]` / `np_lyric_cjk_style[_m|_s]`). Children in order: `img_il_tint` (`np_tint_idle`: Now Playing's gradient over 480 rows) and `img_il_scrim`
(`np_scrim_idle`, 320 x 480, the lyrics scrim's alpha 68 with 44-row smoothstep edges at the window's top and bottom), both insensitive;
`il_view` (the transparent touch target over the window; paints the cover); `il_title` (19 px white) and `il_artist` (17 px `#D0D0D0`),
`hscroll_label`s 196 px wide at x 96 that end in an ellipsis and never scroll (y 25 and 49: a 23 px line pitch, centred
on the cover; the mini bar's colours, its 17 / 16 px a size up); `il_lyrics` (a `scroll_view`, 28, 96, 264 x 372: the engine's view, 12 px above the window's bottom); `il_hint` ("No Lyrics Found", 20 px `#AAAAAA`,
centred over the lyrics view, hidden and insensitive); `label_title` (hidden, "Lyrics"). Neutral colours only; the window colour is
Now Playing's (`np_idle_color`, a color_t word) and follows the track.

The cover is the mini bar's `mb_art_*` at another size (`mb_art_size(56, 8)`: a 56 px bitmap, radius 8 anti-aliased corners in its own alpha, the same
album-cache / `/tmp` file / placeholder-disc source and settle ticks as the Home bar and the lock bar); `il_view`'s `EVT_AFTER_PAINT` blits it at
(28, 20) (`mb_art_paint_at`), so the cover ends 20 px above the lyrics view. Nothing is decoded in the paint. The header was first the mini bar's size (a 48 px cover at y 28,
17 / 16 px text); the user asked for a slightly larger cover and name, closer to the top (2026-11-14). The lyrics view did not move.

## Behaviour

- **Opened by** `bc_timed_open` ([bigcover](bigcover.md) "Idle view", payload hook 24) when Idle Display is Lyrics and the track has lyric rows now (`ly_has_rows()`, the child count of Now Playing's `scroll_lrc`); else stock's Album Cover page opens. There is no other way in (no More-sheet entry).
- **`idlelyrics_open_idle()`**: 0 once the page is up or
  already open (nothing opened twice); -1 when it could not open, with nothing left behind and Now Playing's lyrics as they were. Failures: no Now Playing
  window (`np_window`), Now Playing's engine not running, the window or one of its widgets missing, the destroy listener refused, the engine's labels
  refused (`ly_retarget`), the page timer refused. After the window exists a failure calls `navigator_back` and clears the state.
- **Timer.** One page-scoped timer (50 ms first, then 500 ms through `timer_modify`). Each tick: the engine's view is still the page's (else the page closes, once);
  screen lit; the window colour; the playing track (`mb_track_key`: title, artist, cover; settle ticks for demo's `/tmp` file); `ly_tick()`; the hint is shown
  (visible, insensitive) exactly when the engine reads no lyric rows. A dark screen does no work.
- **Lyrics.** The existing engine, retargeted (below): anchor at 0.35 of 372 = 130 px, the edge fades, opacities, spring, intro dots, own word wrap and
  the chosen Lyrics Text Size (pitch 25 / 29 / 34, gap 9 / 10 / 12). At Large the view holds the current line, about three above and six below.
- **Touch.** A tap anywhere (header, margins, lyrics; under `LY_TAP_PX` = 10 px) closes the page (`navigator_back`); a vertical drag over 10 px on the lyrics
  browses them as on Now Playing (the engine's listeners on `il_lyrics`), returning after 3 s; **no tap seeks** (`ly.noseek`). Listeners return RET_OK, nothing is
  grabbed (the pull-down and the window manager see every drag). Hardware keys keep their stock actions (no key handler).
- **End.** `EVT_DESTROY` (this window only): `ly_release` (the engine back to Now Playing), the timer removed, the cover bitmap freed, the state cleared.
  Repeated open and close leave nothing held. `ly_refresh` (Now Playing's `np_on_foreground`) also releases, so Now Playing in front never meets an engine
  bound to a closing window.

## Stock facts relied on (from disassembly, not device-tested)

The lines are Now Playing's `scroll_lrc` rows (text, int `lrc_time`), read exactly as the engine does on Now Playing. Stock keeps rebuilding them while another
window covers Now Playing: its 500 ms timer callback `0x53cf48` (registered by `player_timer_start`, window in `0x24(a0)`) calls `show_player_face(win, 0)`
(`0x53bab4`) at `0x53cffc` on every tick, before and independent of the `playing_page`-on-top test (which only guards the idle countdown). With
`autochange_refresh` (`0xa05a62`, set by the main loop's song change at `0x4ce8f8`) or `force_refreshflag` (`0xa05a63`) set, `show_player_face` runs the full
refresh, which calls the row builder `0x53a240` (`scroll_lrc`, then `label_lyricmsg`) and clears both flags; with neither set it takes the light path. The lyrics
themselves are loaded by `mclLoadExLyric` (`0x5d41e4`: `mclStartPlayer`, `mclNextSong`, `mcl_tidalStartPlayer`, one more call site at `0x537cbc`), not by the page.
Pinned in `LYRICS_PINS` (the callback's window load and null test, the call at `0x53cffc`, both flag tests, the builder call, the flag clears, the builder's
`"scroll_lrc"` load). **Inferred, not traced:** that the full-refresh path from `0x53bb88` reaches the builder call at `0x53bed0` through the `btn_fav` / `label_index`
blocks without a branch that skips it (the straight-line order is as described); that the main loop sets `autochange_refresh` on a track change while Now Playing is covered;
that the rows exist at the idle page's first tick when the track had loaded lyrics before. A track change under the page therefore shows no lyrics (the hint) until stock
rebuilds the rows, at most one stock tick later.

## Constraints

All work on the UI thread from the page timer and listeners; no new thread, lock, global paint or main-loop work; no stock word written; no hook of its own (it is opened by hook 24's dispatcher, below). Every failure leaves stock
behaviour. Hidden widgets are also insensitive. The page does not stop the stock screen-off (no wake lock, no input read but its own touches).

## Validation limits

Verified by the emulation tests: the asset and its hit map, open / close / reopen, the engine's hand-over and return, the layout numbers at the three sizes in the 372 px
view, track change, no lyrics, taps and drags, every failure path. Not verified without a device: that stock really rebuilds the rows under the page (above), the
look (the preview is the reference), AWTK's wrap and baseline at 22 / 26 px, the cover's decode time on a big embedded picture, the header's top margin (20 px; the side margin is 28; the Vinyl status line sits at y 12),
and the behaviour with the screen going dark and waking under the page.

- **Closing.** `il_close` closes the page's own window (`window_close(il.win)`), never `navigator_back`: when another page's Now Playing button brings the player forward, `np_on_foreground` gives the engine back and the tick closes the page while Now Playing is the top window.
- **Tinted background.** The window is a cover-tinted page (`PAL_COVER_IL`, [accent](accent.md)): its tone keeps its colour in the Tinted mode, as Now Playing's does.
