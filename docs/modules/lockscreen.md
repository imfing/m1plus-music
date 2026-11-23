# Lock screen

**Sources:** `tools/mod_lockscreen.py` (asset, `patch_cover_src`, `patch_date_names`, `MINI_RECT`,
`apply_mini`), `tools/mod_wallpaper.py`, `tools/wallpaper_prepare.py`, `patch/lockscreen.c`
(`lk_*`, `lkwp_*`), `patch/relnotes.c` (instructions page); pins `LOCKSCREEN_PINS`, `LOCKROW_PINS` in
`tools/pod_pins.py`.

Our own lock screen: a restyled stock page (large glass card, or a mini player like Home's), a short
localised date, a wallpaper picker and a Lock Screen settings page that replaces stock's. Payload
hook 25 (`screensaver_page_init`, stock-first, [payload](payload.md)) and a tap-only redirect on the
Display page's Lock Screen row.

## Page asset

`ui/screensaver_page.bin` (fullscreen 320x480), the page theme `styles/screensaver_page.bin`, the
three `screens_*` battery images, `screens_rightslide.png` (premultiplied Lanczos) and four words of
`demo`. Every property is set absolutely, so the layout does not depend on earlier edits, and
applying it twice is refused.

What the app looks up by name: `img_screensaver` (wallpaper), `view_timeinfo` (shown by the Show Time
setting), `app_gesture` (swipe), `btn_play`, `btn_next`, `img_battery`, `pgbar_battery`,
`view_bottomview` (hidden and disabled when nothing is queued), `view_scrlabel_title/artist`,
`view_img_icon`. Nothing in stock looks up `dclock_time` / `dclock_date`; the payload sets both formats
([The date](#the-date), [The clock](#the-clock)).

Layout, top to bottom (window y):

- Date, 20 px, ink top 12 ([The date](#the-date)).
- The 68 px clock, centred ([The clock](#the-clock)).
- A **glass card** at 16,108, 288x334, holding the **square 264x264 cover** at 12,12, title (20 px
  white) and artist (16 px `#DDDDDD`) at 12,282 / 12,306, and play and next at 180,278 / 228,278
  (48x56, off-white `np_*` glyphs via the page theme's `btn_imgplay1/pause1_style`).
- The swipe hint `img_slide` at 144,452.
- The battery gauge on the date line at 282,11 (the status bar's 28x14 pictures; the fill
  `pgbar_battery` is drawn under the picture as in the bar) with, hidden, the Battery Percentage's
  number `pod_pct_lk` in its body ([battery](battery.md)). The widest date of every language stays
  4 px clear of it.

With nothing queued the card is hidden and the page is date, clock and gauge on the wallpaper, and
the whole screen swipes.

**Touch.** `app_gesture` is the parent of the page and records the down point, grabs, and compares on
move and up. `view_img_icon` is insensitive, so a touch on the cover, card or text lands on
`view_bottomview` (no handler) and a swipe unlocks. Play and next are 48x56.

**Not possible asset-only:** the cover in place of the wallpaper (`img_screensaver` gets its image
once, in the init visitor).

## Glass card

`view_bottomview` has `bg_image` `lk_card` and a transparent `bg_color` in every state: the same pane
as the Home mini player bar ([minibar](minibar.md); `glass_image(288, 334, 18, ...)` in
`tools/mod_icons.py`; dark gradient `#2A2A2C` to `#1E1E20` at alpha 0.76, a 1 px rim light, a faint
inner highlight). It is the committed `assets/icons/png/lk_card.png`, installed by `mod_nowplaying`,
and drawn 1:1 (a 288x334x4 bitmap in RAM). No 9-patch: no stock style selects it, and a stretched
middle would smear the gradient and rim.

- **Contrast:** white title and `#DDDDDD` artist stay >= 7:1 and >= 4.5:1 over every pixel of their
  boxes on white and on black (`test/pod/assets.py`).
- **No baked blur.** The wallpaper can be any picture, so a blur baked at build time would match only
  the default. The large card has no blur; the mini player has the live one.
- **The cover is square** on purpose. A corner mask paints one fixed colour, wrong over a translucent
  card on any wallpaper, and AWTK cannot clip an image to a radius, so rounding the picture would
  need payload code. The card is rounded and the cover sits 12 px inside, clear of the arcs.

## Cover size patch

demo writes `/tmp/coverpic.jpg` / `/tmp/externpic.jpg` in `parseplaycover_thd`, fitted inside the
requested size, aspect kept, never upscaled, once per new track. Four immediates become 264 (`0x108`)
instead of 254 (`patch_cover_src` pins the stock words and GOT slots and refuses otherwise), because
AWTK draws a smaller picture at the widget size by nearest neighbour, so the card's cover and Now
Playing's `img_playcover` are both 264 and drawn 1:1 (`mod_nowplaying` asserts they agree).

- Cost is 1.08x output pixels. Other readers resample as before: the big cover page (its own 320 px
  picture since [bigcover](bigcover.md)), the Home strip, Now Playing, and the remote-control replies
  (a file must stay under 92,161 bytes or the phone shows no cover; 264 px files are about 1.08x the
  254 ones).
- Unchanged: `.downpic` art, DLNA/AirPlay (270), HiFi/Tidal (254).
- Cover source types: 2 = `/tmp/coverpic.jpg`, 3 and 5 = `/tmp/externpic.jpg`, 4 = `random_cover0..7`,
  6/7 = the HiFi / Tidal album files, else `defaultcover` (a 66x66 placeholder blown up; left alone
  because other pages use it).

## Mini player layout

`/mnt/data/m1plus/lockscreen-layout`: one character, `1` = mini player; missing, empty or anything
else = the large card (default). The payload only reads it (`set_read`, once per lock screen init), so
a change applies the next time the lock screen opens; there is no tap or gesture on the cover.

The init hook (hook 25) runs stock's init completely and returns its result. Only for `RET_OK`, a
window, no `/mnt/mmc/m1plus-off` and a file of `1` does it look up the six stock widgets
(`view_bottomview`, `view_img_icon`, `view_scrlabel_title/artist`, `btn_play`, `btn_next`); when all
exist it moves and resizes them to the Home bar's layout ([minibar](minibar.md); numbers `LK_*` and
`MB_*` in `offsets.inc`): card at 8,386 (304x56, 10 px over the swipe hint), cover 14,10 36x36, title
60,7 at 17 px white, artist 60,29 at 16 px `#D0D0D0`, play 194,0 and next 245,0 (48x56). Position is
the only lock-specific thing; the look is the Home bar's.

- **Cover:** the Home bar's code (`mb_art_*` in `patch/minibar.c`): a 36 px bitmap of our own,
  box-filtered from the album's cache file ([covercache](covercache.md)), else demo's `/tmp` picture,
  else the stock disc, corners rounded in the bitmap's alpha, decoded on the timer and never in paint.
  Stock's `view_img_icon` is hidden; the tick hides it again if stock shows it.
- **Glyphs:** stock swaps the play button's style by name only when the name differs from what the
  status wants, so we never call `widget_use_style` and never rename the style. The glyphs are
  overrides in the widget's own style (`style:normal|over|pressed:icon`). The tick reads
  `mclGetPlayStatus` and the style name stock set and remakes the icons whenever either changed, so a
  swap that reset them is repaired within a tick. Next is not swapped: its `bg_image` is cleared and
  its icons set once.
- **Labels:** `ellipses` and `only_parent_focus` set, so they are one-line and never scroll like the
  Home bar's (stock's scroll over a partly repainted pill would also defeat the blur).
- **Backdrop blur:** the shared `mb_blur_*` routine ([minibar](minibar.md) "Backdrop blur"; escape
  hatch `/mnt/mmc/m1plus-noblur`) blurs the wallpaper under the pill from the card's
  `EVT_BEFORE_PAINT`. A partial frame is not blurred and the next tick invalidates the whole card.
  Without a plane the glass shows over the sharp wallpaper.
- **Timer and handlers** (`lk_*`): `EVT_DESTROY`, `EVT_WINDOW_TO_BG`, `EVT_WINDOW_TO_FG` on the window,
  `EVT_AFTER_PAINT` on the card, one 120 ms one-shot that arms the tick (100 ms while the backlight is
  on, 1000 ms off, so the cover is right when the screen wakes). Only when all of that is up are the
  cover widget hidden and the labels and next restyled. Background removes the timer, foreground arms
  the one-shot again, destroy removes it and frees the bitmap and the plane (`lk_stop`). A missing widget, a refused `widget_on` or no
  timer leaves the moved stock widgets with stock's cover and glyphs.
- Nothing in stock's lock screen code moves, resizes or restyles a widget, so the layout survives
  every refresh and track change. Any failure leaves the large card.
- **Stock 20 ms timer replacement** (`lks_*`, both Large Cover and Mini Player layouts): hook 25
  replaces stock's 20 ms `"timer_idex"` callback (`0x53fc68`) with `lks_tick`. While stock's
  startup delay counter (`0x97ccf0`) is positive, `lks_tick` delegates verbatim to `0x53fc68` so
  the 40 ms backlight-on sequence is unchanged. Afterwards it slows to 200 ms lit—calling
  `0x53f520(win, 0)` only when one of the six battery globals changes, `0x53f520(win, 1)` on the
  track-dirty flag (`0xa05a60`) and `0x53f9b4(win)` on the cover-dirty flag (`0xa05a5c`)—and to
  1000 ms with no repaints while dark. `bp_light_on` (`lk_on_wake`) refreshes synchronously before
  the backlight turns on.

## Radio mode

Radio plays through hciplayer and leaves stock's local play queue intact ([radio](radio.md)), so
while `mb_radio_active()` holds (running, or Stopped / Error while radio owns playback and no
external BT receiver / USB DAC / AirPlay source is hiding the card), hook 25 takes over the card in
both Large Cover and Mini Player layouts:

- Shows and enables `view_bottomview` even with an empty local queue, hides `view_img_icon`, sets
  the station name and state line (`Live`, `Connecting…`, `Paused`, `Stopped`, `Can't play: …`),
  greys and disables `btn_next` (`np_next_off` / `mb_next_off`) and swaps `btn_play` to Stop while
  connecting or playing (`np_stop` / `mb_stop`) and Play otherwise.
- Art: Mini Player shares `mb_radio_art` (36 px rounded logo or radio glyph); Large Cover paints
  the 192 px cached logo on a white 264 px square or the 96 px `pod_ic_rd_art` glyph on `#2C2C2E`
  (decoded on the timer, never in paint).
- Click handlers bound after stock's return `RET_STOP` while radio owns the card (`btn_play` stops,
  resumes or retries; `btn_next` is ignored) and `RET_OK` once a local track takes over. The tick
  repairs stock's `screensaver_refresh` if it overwrites labels or hides the card.

## The date

The short date of the UI language: `Wed, Nov 11`, `11月11日 周三`, `11月11日 週三`, `11月11日(水)`,
`11월 11일 (수)`, `mer. 11 nov.`, `Mi., 11. Nov.`, `mié, 11 nov`, `mer 11 nov`, `พ. 11 พ.ย.`,
`śr., 11 lis`, `ср, 11 нояб.` (uk `ср, 11 лист.`). Stock's formatter writes `MMM` through a locale table that no stock
language file fills, and `W` as a full English weekday (zh_CN has `星期日..`); this date is the only
format that uses either. Three parts (`patch_date_names`, "The lock screen's date" in
`tools/pod_i18n.py`, `lk_date`):

- **Names:** `Sunday..` become `Sun..` and `Sept` becomes `Sep` in place. The 19 names are also i18n
  keys with each language's abbreviations.
- **`W` is translated as `MMM` is:** six stock words that clear a buffer in the weekday path become
  the month's own locale lookup plus a jump to the month's tail (`locale_info_tr`, `wstr_append`).
  Both stock paths are pinned (`DATE_W_CODE`, `DATE_M_CODE`).
- **Format:** the asset's format `W, MMM D` is itself an i18n key (`LOCK_DATE_KEY`) whose translation
  is the language's format (`M月D日 W`, `W D MMM`, `W, D. MMM`, ...). `lk_date` sets it at the page's
  init with `digit_clock_set_format`, after stock's init and not with the kill switch. The widget
  keeps it for its own 1 s timer, so the date turns at midnight. A format's own characters must not
  be formatter tokens and it stays under 64 bytes.

With the kill switch, or without the widget, the asset's format shows with the language's names. The
widest date at 20 px is 120 px (zh). Preview panels with `,lang=zh_CN`.

## The clock

The asset's clock format is `hh:mm` (24 h), and stock's 24-Hour Time switch only reformats the status
bar clock (`change_time24h_12h`), so on stock the lock clock is 24 h whatever the setting. With
24-Hour Time off (stock's byte `time24hflag`), `lk_clock` sets `HH:mm` at the page's init, after
stock's init and not with the kill switch: `9:41`, no AM/PM, as on an iPhone. The page is rebuilt each
time the lock screen opens, so a change shows the next time.

`HH` is stock's 12-hour hour padded with `%02d`. One word in `wstr_format_date_time`
(`HOUR12_VA` 0x64ea60 in `tools/mod_lockscreen.py`, `b 0x64eb0c` to `b 0x64eba8`) sends it to
the `%d` append instead, so `HH` is unpadded everywhere: the status bar shows `9:41 AM` (stock
`09:41 AM`), as our own pages already do. The edited branch is shared with `YY` (year % 100), whose
only user is the unused file browser; years 2022..2050 keep two digits.

## Settings

A **Lock Screen** link row on [our Display page](display.md), under Screen Timeout, opens our page
`m1plus_lockscreen` (`LOCK_PAGE`), which replaces stock's `systemset/screensaver_page` completely.
Four cards:

1. **Enable**: a switch, `ACT_LOCKON` 79.
2. **Wallpaper** (`ACT_LOCKWP` 84, opens [the picker](#wallpaper)) and **Show Time** (`ACT_LOCKTIME`
   86, a switch).
3. **Player Style** (`ACT_LOCKSTYLE` 85): the value is Large Cover or Mini Player; opens the picker
   `m1plus_lockstyle` (`ACT_LOCKSET` 88, arg 0 / 1) with a check and the note "Applies the next time
   the lock screen opens."
4. **Custom Wallpaper** (`ACT_LOCKINFO` 87): the instructions page `m1plus_lockinfo`, a Release Notes
   page in every respect ([update](update.md): same asset and painter via `rn_open`; text 20 px
   `#E6E6E6` on a 27 px pitch for this page only). It has a heading "Add Your Own Pictures" and three
   paragraphs: the folder `lockscreenimage` at the top level of the card; JPG or PNG exactly 320x480
   under 1 MB; at most 5 pictures, chosen in Wallpaper.

Show Time and Custom Wallpaper have our own short labels in 13 languages (stock's texts did not fit
their rows). The rows are not dimmed when Enable is off: a wallpaper chosen now applies the next time
the lock screen opens. Ids: pages `LOCK_PAGE`, `LOCKWALL_PAGE`, `LOCKSTYLE_PAGE`, `LOCKINFO_PAGE`;
hooks 25 and `hook_lock_row`.

`lk_layout()` reads `lockscreen-layout`; `lk_layout_set()` writes `0\n` or `1\n` atomically
(`home_write_atomic`), and the check moves only after a successful write. The checks and the Player
Style value read the file when their page opens and when it is back in front. Settings Files lists
the file, so its per-file delete and Reset All Settings return the large cover.

**Enable.** Stock's switch flips the byte `screensaver_mode` and then calls
`write_int_config("SYSSET", "SCREENSAVER")`. `config_init` loads it once at boot; `into_standby` and
the key handler read it every time the screen goes dark: 0 wakes the screen without a lock screen,
1 shows it. So a change is live at once. `lk_enabled_toggle()` repeats stock's two steps in stock's
order (stock's handler works only inside its own page, so it cannot be called from ours). There is no
failed-save path (stock ignores the result too). The switch is read when the page opens and when it
is back in front. The pins are `LOCKSCREEN_PINS`.

**Show Time.** Same shape: stock stores the byte `screensaver_timeshow` xor 1 and then calls
`write_int_config("SYSSET", "SSAVERTIMESHOW")`, the byte first. The lock screen's page visitor reads
the byte each time the lock screen is built, so the choice is live at the next lock.
`lk_time_toggle()` does the same two steps in the same order. `LOCK_TIMESHOW` is checked against
demo's dynsym by the build; `setting_tests` runs stock's own handler on the same byte and compares.

**The Display row.** Stock's Display page installs one click handler on its four rows and picks the
page by the row's name; case 2 is the only `navigator_to` of `systemset/screensaver_page`. The
redirect is the Equalizer row's mechanism ([peq](peq.md)): the case's first two words become a jump
to `pod_lock_site`, which calls `lk_redirect()` (kill switch first, then `open_page(POD_LOCK_PAGE)`)
and returns through the handler's epilogue when ours opened. With the kill switch on or if the open
fails it runs stock's own two words and the shared `navigator_to` call, so stock's page opens as
before. A row click on a Settings page is a tap-only hook on the paved path ([safety](safety.md)).
The redirect does not depend on whether the Display window was fresh or restacked. Stock's page and
init stay in the image, reached only through the fallback.

## Wallpaper

### Default picture

With no custom wallpaper stock keeps the resource name `screensaver_default` as `SCREENSAVERPATH`; a
chosen picture is `file://` plus its path. Only the resource changes: `images/xx/screensaver_default.png`
(320x480) becomes a drawn bokeh field (`assets/bokeh-320x480.png`, our own design): a vertical
gradient from indigo through aqua to deep sea green with soft discs of lavender, blue and mint light,
large and faint behind the clock, small and brighter along the card's sides. `wallpaper_prepare.py
OUT.png` draws it with Pillow, reduces it to a 256-colour palette and compresses it losslessly with
primage; the output is deterministic, primage is needed only to redraw it, and the build copies the
committed file and pins the stock file's hash. The swap saves about 389 KB of rootfs. demo's loader
(stb_image) expands palette PNGs.

### Wallpaper picker

`m1plus_lockwall` (`LOCKWALL_PAGE`, built by `build_lockwall_page`; opened by `lkwp_open`) is stock's
wallpaper grid under our navbar. It **writes what stock writes, in stock's order**, so stock's page,
stock's lock screen and ours always agree; there is no file of ours.

What it relies on in stock (pins in `LOCKSCREEN_PINS`):

- **The list:** `get_screensaver_image` scans `/mnt/mmc/lockscreenimage` in directory order for regular
  `.jpg` / `.jpeg` / `.png` files (path under 201 bytes) of exactly 320x480 and under 1 MiB, at most
  five, with `screensaver_default` always first. A missing folder leaves only Default. A chosen picture
  that is no longer readable is reset to the default name.
- **The tap:** unless the entry is already chosen, the old mark goes off, the new one on, then the
  global `screensaver_picture` is set to the entry as the deque holds it and written with
  `toolsWriteConfig("/mnt/data/config.ini", "SYSSET", "SCREENSAVERPATH", ...)`. Nothing else.
- **Who reads it:** `config_init` at boot (unreadable file: the default name) and the lock screen's
  page visitor each time the lock screen is built (an unreadable file shows the default). So a tap is
  live at the next lock; nothing is cached.

Our page: `view_covers` (0,50,320,400) holds six cells `imgcover0..5` exactly as stock builds them
(three columns at x 12 / 115 / 218, rows y 0 / 143, 90x135, `scale_auto`; a 26 px `img_choice<i>` mark
at 4,4; cell 0 a 24 px default icon), hidden until the payload shows them. The navbar is ours. The
selected border is 2 px in the accent colour (Neutral by default, dark in Light Mode when neutral;
stock's is orange); the payload sets the colour rather than switching a style name because the page
theme is not ours.

- `lkwp_open` opens the window, looks up the twelve widgets (any missing or a refused handler:
  `navigator_back`, -1), calls stock's list builder, copies the entries (at most six, 208 bytes each,
  so a stock page rebuilding the deque cannot change what a tap writes), shows the cells, binds
  clicks, sets the marks and arms a 40 ms timer that sets one more picture per tick (the page is up at
  once; stock decodes each picture twice before its page shows).
- Differences from stock: when nothing matches the selection counts as none (stock takes it as cell 0,
  so Default could not be chosen then), and the pictures load one per tick.
- The marks are recomputed from the global when the page is back in front.
- The cells are plain AWTK image widgets, so the decode is stock's (614 KB each, held while the page
  is open). `cc_decode` reduces only to squares and was not used.

## Limits

- No hint under the grid when the folder is empty (stock has none; Custom Wallpaper explains the
  folder).
