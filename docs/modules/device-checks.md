# Device checks

Record the build tag, device/card, result (pass/fail/untested) and capture for each applicable
check. This is a checklist, not a record of completed testing. Historical observations stay
in [history](../history.md); feature modules retain their detailed edge cases.

## Common checks

| ID | Check |
|---|---|
| SYS-01 | Boot, sleep/wake and reboot; switch startup, return to Shanling Home and reopen M1+ Music; verify the kill switch |
| SYS-02 | Boot guard: install the guard alone, wait 10 s past Home and power-cycle; power off within 5 s of Home once to prove the failure branch; then Home on top. Card log `m1plus: armed` -> `m1plus: boot ok, marker cleared` |
| UI-01 | Upright boot logo; readable fonts at 16/18/20/21 px; stable digits/clocks; CJK, Cyrillic, Vietnamese, Thai and curly quotes |
| UI-02 | Status bar in 12/24 h mode with wireless icons; captions fit; settings slides, pull-down and stock theme behave correctly |
| UI-03 | Pull-down over the main menu: pull down over the first row slowly and fast, default and custom order; rows stay behind the dialog and after it closes. Lock/unlock with a custom order shows no default-order frame. Main Menu arrows and switches work; the menu scrolls |
| UI-04 | Pull-down tiles ([details](pulldown.md)): open it with no `pulldown-tiles` file (all eight in stock order), then reorder, hide some and hide all on Settings → System → Appearance → Control Center and reopen it after each change. Every shown tile does its stock action (Wi-Fi, Bluetooth, buttons lock, gain, USB mode, output, playback settings, system settings); a hidden tile and its caption are gone and a touch where it was does nothing; the captions follow their tiles; brightness slider and status bar are unchanged; with `/mnt/mmc/m1plus-off` the stock layout returns. Hardware keys while the pull-down is open behave as in stock |
| LO-01 | Line Out pill ([details](lineout.md)): turn Line Out on (Settings or the pull-down's Output tile): the status bar shows an amber pill with a black "LO" where the volume number was, within a second, and the pull-down's bar shows it too; PO shows the number again; the pill is not tinted by any Accent and sits level with the other icons; with `/mnt/mmc/m1plus-off` the stock white "LO" returns |
| INPUT-01 | Tap, slow drag, flick, drag out-and-back, abort and catch a coasting list; scrolling must not open/play a row |
| TIME-01 | Automatic time ([details](autotime.md)): with the auto time setting on, connect Wi-Fi; the clock becomes correct for the zone (`date`), `hwclock -r -u` shows UTC, and the status bar clock is still right after a reboot. Set the time by hand and reboot: still correct. After updating from stock the first boot is off by the zone offset until a sync. `/tmp/result_ntpdate` may be empty (`&>`); do not rely on it |
| TZ-01 | Time zones ([details](timezones.md)): Date & Time with auto time off lists 43 zones west to east and ticks the current one; pick GMT+5:30 Kolkata, reboot: the picker still ticks it and the clock shows UTC+5:30. Pick Los Angeles, Dhaka, Tehran and Auckland: the status bar clock changes by the expected offset. A device saved at Shanghai (22) or any stock index boots on the same zone. Scroll the long list; every row taps. With `/mnt/mmc/m1plus-off` a stock zone (0-26) keeps working. Row text longer than the row scrolls |
| CAP-01 | Confirm/cancel a screenshot, leave the page, check indicator and captured colours; test missing/full card |

## Library and playback

- **ALB-01 — Albums:** switch grid/list in place, retain the first visible album and mode after
  reboot, and return from an album to the same position. Check long labels, missing covers,
  pressed rows, sharp tiles and a large library. [Details](albums.md)
- **CF-01 — Cover Flow:** portrait/landscape, artist scope, ends, drag/fling/snap, side/centre
  taps, first cache build, cancel and rebuild. The navbar stays usable. [Details](coverflow.md)
- **SONG-01 — Songs:** title collapse, pinned letters, all rail sections/bubble, search, each
  sort, select-all, add/delete and return position. Check a large library; covers load after
  scrolling stops. [Details](songs.md)
- **NAV-01 — Album/navbar:** one seamless capsule, contained pressed highlights and no leftover
  pixels in button gaps. Play all resets in-order mode; Shuffle and track taps use the expected
  queue. Look up album returns correctly to Now Playing. [Album](album-page.md), [navbars](navbar.md)
- **PLAY-01 — Now Playing/lock screen:** sharp rounded covers, tint changes, neutral missing
  art, remaining time, transport/favorite/More controls, translucent card and swipe behaviour.
  Check idle/no-queue and charging states. [Now Playing](nowplaying.md), [lock screen](lockscreen.md)

## Home content

- **HOME-01 — Mini player:** absent with no queue and on the normal menu; appears within a
  tick for playback. Check long titles, transport/track updates, Now Playing return, dialogs,
  pull-down and the final row scrolling clear above it. [Details](minibar.md)
- **HOME-02 — Blur:** smooth scrolling and track changes, rounded glass without seams/colour
  casts or persistent sharp patches. Compare `m1plus-noblur`; BGRA5551 intentionally omits blur.
- **HOME-03 — Recently Played:** newest-first covers, one entry for compilations, one to three
  rows without layout jumps, lazy cover loads and no stutter. Check missing/deleted albums,
  taps versus drags, coasting catch, setting persistence and reboot. [Details](recent.md)
- **HOME-04 — Daily Mix:** responsive creation/regeneration, readable card over varied palettes,
  expected songs/artist limits, play/shuffle/track taps and correct detail page. Check settings,
  reboot, card swap/no card, missing covers and Add-to-playlist behaviour. [Details](dailymix.md)
- **HOME-05 — Cache pill and sync icon:** with covers missing (Developer > Clear Cover Cache, then Home) the pill "Checking library…" (empty bar, no count; "Rebuilding covers…" after Rebuild Covers) appears at once, and about 5 s after Home is in front it becomes "Preparing covers n/m"
  with the bar growing and the list below it intact; "Measuring tracks n/m" follows. The x stops the pass at once without a stall, the pill hides, and the pass does not return
  on leaving and re-entering Home until a reboot or Settings > Library > Rebuild Covers (which then runs). While any build runs, on Home, Albums, Songs, Cover Flow and Settings, the static sync glyph
  shows between Bluetooth and Wi-Fi in the status bar and in the pull-down's bar, clear of the clock (also with Battery Percentage on); it goes out when the build ends or is stopped. Playback and scrolling stay smooth during
  a build (the worker runs at nice 10). With the cache complete, leaving and re-entering Home shows no pill and does no scan; after playing a song no pill shows (same library); adding an album shows it about 5 s later and builds; the x while it waits cancels it, and after a reboot it returns. Leaving Home mid-build (or during the wait) and coming back restarts it after about 1 s, not 5. Check the pill's text and bar in several languages. [Details](homecover.md), [sync icon](lineout.md)

## Extras

- **EXTRA-01:** playlist grid/list and actions; Artists/Album Artists, Genres and Composers;
  menu show/hide/reorder and empty Extras groups; translated text fits.
- **EXTRA-02:** local podcast scan, dates, resume, played marks, speed and covers.
  [Podcast checklist](podcasts.md#device-checks)
- **EXTRA-03:** virtual iPod wheel/navigation/playback and embedded Cover Flow.
  [iPod checklist](ipod.md#device-checklist)
- **EXTRA-04:** Cassette Mode orientation, text, theme, progress/reels, pause/resume, close
  and dark-screen timer behaviour. [Cassette checklist](tape.md#device-checklist)
- **EXTRA-06:** Find Cover & Lyrics (More sheet, More page): row dimmed with Wi-Fi off, covers from iTunes and Deezer,
  a tapped cover on Albums, Cover Flow, the album page, mini player and Vinyl, the folder picture, LRCLIB lyrics saved as
  `.lrc`. [Checklist](onlineart.md#device-checks-not-run)
- **EXTRA-07:** Radio (Home menu item, Pod row): directory lists, search, favourites, playback, hand-over with local music, standby and
  screen-off playback, volume, Wi-Fi drop. [Checklist](radio.md#device-checks)
- **EXTRA-05:** Vinyl Mode cover label, turning and stopping, arm on the groove and parked, keys,
  record tap, close and dark-screen timer behaviour. [Vinyl checklist](vinyl.md#device-checklist)
- **ACCENT-01 defaults:** with no `appearance-accent` file everything looks as on main: Settings, Home, lists, keyboard,
  Now Playing; a pressed row is `#333334` and a pressed Settings card `#2C2C2E`, every glyph stays white. Settings > System shows
  Appearance (between Display and Keyboards, a chevron, no value) opens a page with Accent = Neutral, which opens the picker; back from the
  picker returns to Appearance; the Light row stays hidden.
- **ACCENT-05 Tinted background and menu glyphs:** Appearance > Background > Tinted with an accent: pages, cards, hairlines, sheets, mini player glass and navbar fade take the wash at once (Teal page `#08181B`); text, secondary greys and chevrons unchanged; Now Playing, album page, Show page and Daily Mix page keep their cover backgrounds and black fades; lock screen, full-screen cover, power-off splash, Pod and Cassette unchanged; Neutral + Tinted looks Black; reboot keeps both; `m1plus-off` returns Black + Neutral. With any accent the M1+ Music rows' glyphs (main menu, Shuffle, Extras, Main Menu pages) are the accent at rest (white text; the Settings cards' glyphs are the accent too, see ACCENT-06; the Folders list, all of it (storage, folder, playlist, CD Library, audio file glyphs: one colour, none white), and Now Playing's More sheet glyphs are the accent too), changing the accent updates them when back on the page; a press and release does not flash white. Open the main menu right after a boot (glyphs are the accent from the first paint), idle in front for over a minute, and leave it behind another page and come back: the glyphs are still the accent, never blank or white; open and close the pull-down (and Now Playing's mini bar) after 15 s idle: no glyph blanks.
- **ACCENT-02 each accent (Red, Orange, Green, Teal, Purple, Champagne), applied at once with the picker open:** the check and
  Settings value follow; pressed Settings card, M1+ menu row (Music, Shuffle, Extras, Main Menu) and list row tint, with the
  row's glyph already the accent (nothing changes on the glyph at a press or a release); switch on is accent with white knob;
  pull-down brightness/volume fills, the lit (ON) pull-down tiles (Wi-Fi, Bluetooth, EQ, Key Lock, USB Audio/DAC/Storage, High Gain, LO, the pressed Play/System Settings: an accent disc with the dark glyph; off and disabled tiles unchanged), the date selector line, the Now Playing progress fill, the playing wave in a list and on
  the album page (reopen the page after a change); picker check and swatches (Neutral light grey, never tinted).
- **ACCENT-06 Settings glyphs in the accent at rest:** with an accent, every glyph of the Settings pages (Settings, System, Appearance, Library, Playback, Developer, the pickers' link rows; Wi-Fi
  to Open Shanling Home) is the accent while the row is idle, white text beside it; the pressed row is the 22 % tint with the same accent glyph, nothing flashes white at a press, release or scroll. The
  accent swatches in the Accent picker, the chevrons and the stock Settings pages' 40 px disc icons keep their colours. Leave Settings, wait over a minute, come back, and open a deep page cold: the glyphs
  are the accent, never white or blank. Neutral: all white. [Accent](accent.md)
- **ACCENT-03 unchanged under any accent:** lock screen, full-screen cover, power-off splash, Pod, Cassette Mode, cover-tinted
  page backgrounds, chevrons, secondary text, navbars.
- **THEME-01 theme1 off:** Settings > All System Settings lists no Theme row (the rows after it moved up; the tap of every row opens its own page). To prove the clamp, first flash the previous build or stock, pick System > Theme > the second theme (salmon look), then flash this build: it comes up on the default look at the first boot, and `config.ini` still says `THEME=1`. With `/mnt/mmc/m1plus-off` present the look stays the default (the edits are in `demo`). [Theme](theme.md)
- **ACCENT-04 persistence and kill switch:** the accent survives a reboot; `/mnt/mmc/m1plus-off` returns Neutral within a
  minute (all glyphs white again); removing it brings the accent back.
  [Accent](accent.md)

For captures use Settings → Developer → Screenshot, then `tools/pull_shots.py --build latest`.
See [installation/restore](../install.md) and [capture details](screenshot.md).
