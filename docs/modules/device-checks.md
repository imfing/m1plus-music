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
| INPUT-01 | Tap, slow drag, flick, drag out-and-back, abort and catch a coasting list; scrolling must not open/play a row |
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
  queue. Look up album returns correctly to Now Playing. A FLAC, MP3, M4A or WAV album's line
  gains its length shortly after opening (compare with the player's track times) and at once on
  reopening; an album with another format or a CUE track shows none. [Album](album-page.md), [navbars](navbar.md)
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
- **EXTRA-05:** Vinyl Mode cover label, turning and stopping, arm on the groove and parked, keys,
  record tap, close and dark-screen timer behaviour. [Vinyl checklist](vinyl.md#device-checklist)

For captures use Settings → Developer → Screenshot, then `tools/pull_shots.py --build latest`.
See [installation/restore](../install.md) and [capture details](screenshot.md).
