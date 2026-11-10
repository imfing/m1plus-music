# Daily Mix

The Home menu shows a Made for You card above Recently Played. It contains generated gradient
art, the mix title/artists and a play disc. A tap opens the detail page or starts playback.
The mix is a file of song paths regenerated from listening history once a day; it becomes a
stock playlist only when the user saves a copy with the detail page's Add action. Existing
playlists from older builds are not automatically removed. The normal menu has no mix card.

Sources: `patch/dailymix.c`, `patch/menu.c` (`menu_daily`), `tools/pod_ui.py` (`daily()`),
`tools/pod_pages.py` (`ACT_DAILY`, `ACT_REGEN`) and `tools/mod_icons.py` (`DAILY`). Geometry and
selection use `DM_*` / `MIX_*` in `offsets.inc`; Python models are `tools/pod_dailymix.py`
and `tools/pod_mix.py`. Texts are in `pod_i18n.py`. Tests: `test/pod/dailymix.py` and
`test/pod/dmpage.py`; previews: `preview_dailymix.py`, `preview_dmpage.py`.

No stock hook or boot work is added. Window/widget events and a page-owned timer drive the
job and card. Detailed formats, phases and failure rules follow.

## Layout (section-local y; `tools/pod_dailymix.py` DM_*, `patch/offsets.inc` DM_*)

The section is one `view` 310 wide (`SH_W`), a child of `pod_scrollview` between the last shown row and `pod_shelf` (child order: shown rows, **daily section**, shelf, hidden rows, spacer `pod_pad`), hidden and
insensitive in the asset, shown by the payload when a mix exists and the switch is on; height `DM_SEC_H` = 272. With it (and the shelf, six albums) the default menu is 416 + 272 + 634 + 64 = 1386 px.

| part | geometry | |
|---|---|---|
| header `pod_dm_head` | label at (10, 17), **269** x 22 (the shelf's is 300; it stops 6 px before the busy mark), **20 px** white `hscroll_label`, otherwise the shelf's (`SH_HEAD_*`), key `Made for You` | ink 20..33 below the Settings hairline: the same 20 px of air as "Recently Played", text at x 12 |
| busy mark `pod_dm_busy` | an `image` 16 x 16 at (285, 20) (`DM_BUSY_X`, `DM_BUSY_Y`), `draw_type center`, image `dm_sync` (`SYNC_DM`: the status bar's sync glyph, Lucide refresh-cw, in #AAAAAA), hidden and insensitive in the asset | about 14 px of ink centred under the list rows' chevron (x 288..298), and centred on the header's text line. Static; a diagnostic for correlating UI stalls with the job |
| card `pod_dm_card` | a `view` **296 x 220 at (12, 44)** (`DM_X`, `DM_W`, `DM_H`; top = `SH_TOP`) | x 12..308 is the extent of the shelf's two covers (`GRID_MARGIN` + 2 x `GRID_COVER` + `GRID_GAP`): the card's edges line up with the covers below it. It paints the art and the text itself (its own `EVT_AFTER_PAINT`) and takes the taps |
| corners | **12 px** (`DM_R`) blended into black **in the bitmap** once (`grid_round`'s blend, `pod_corner_fill`'s table) | 4.1 % of the card's width, the same ratio as Now Playing's 12 on 264 and the shelf's 8 on 144 |
| art | the 296 x 220 RGBA bitmap, opaque, 260 KB (`bitmap_create_ex`, like the covers', freed with the window) | made by the generator below, read from or written to the art file as RGB565 |
| title | "Daily Mix" in two lines, 36 px white, left, x 18, boxes 38 high at y 84 / 122 (`DM_TITLE_Y1`, `DM_TITLE_Y2`), 260 wide | split at the **first space**; a title without a space (Tagesmix, 每日精选) is one line on the bottom box. Drawn with the stock canvas text in the style of the hidden label `pod_dm_title`; a line wider than the box is cut with an ellipsis |
| artists | up to **2 lines** of 16 px `#EBEBEB`, x 18, y 164 / 184 (`DM_SUB_Y`, `DM_SUB_PITCH` 20), 204 wide (the disc's left edge less 12), style of the hidden label `pod_dm_sub` | "Radiohead, Björk, Air and more": at most 3 names (`DM_MAX_NAMES`), fewer when "names + and more" does not wrap into 2 lines of 204 px; if not even one name does, its text wrapped as far as it goes and cut with an ellipsis |
| disc `pod_dm_play` | a stock `button`, **48 x 48** at (246, 202) in the section = (234, 158) in the card, 14 px from the card's right and bottom edges; `img_btn_style` with the images `dm_disc` (`_down` pressed) | the same glass as Now Playing's star / More discs and the mini bar (`glass_image(48, 48, 24)`), a white 22 px play glyph one px right of centre; a **later sibling of the card**, so hit testing gives it its 48 px square (>= 44) and the card the rest |
| air below | `DM_BOTTOM` 8 | 28 px to the Recently Played header's ink |

Vertical stack from the card's bottom: 16 px, artists 164..204, 4 px, title 122..160 and 84..122, free art 0..84. Previews (`out/dailymix/`): `home-card-visible.png`, `home-card-to-shelf.png`, `home-card-end.png`,
`home-top.png`, `home-card-no-shelf.png`, `card-1x.png`, `card-2x.png`, `section-1x.png`, `card-pressed.png`, `palettes.png`, `settings-home-screen.png`, `card-languages.png`, `settings-longest.png`.

## Files

- **Where.** The mix travels with its card: `CARD_DIR` `/mnt/mmc/.m1plus` (hidden; the writer makes it and then `MIX_DIR` `daily-mix` in it with `mkdir` 0755, EEXIST fine) holds `daily-mix/tracks`, `daily-mix/art` and their `.tmp` files. The mix file stores the card's absolute song paths, so a mix kept on internal flash went stale at a card swap; now a swap
  shows that card's own mix, or, when it has none, the menu makes one after `DM_START_MS` (a mix of another day is made again as always). **No card, no mix**: `pod_card_mounted` (`patch/common.c`, the test `patch/shot.c` uses: `/mnt/mmc` is another file system than `/mnt`, `statfs` type and fsid) is checked
  before every read and write of these files and before a job is wanted, so with the card out (an unmounted `/mnt/mmc` is a plain directory on the internal flash) the section stays hidden, no job runs and nothing is written. The old `/mnt/data/m1plus-mix*` files of earlier builds are left
  unused (no migration, no cleanup; delete them by hand). `/mnt/data` keeps only the device preference below.
- **`/mnt/mmc/.m1plus/daily-mix/tracks`** (`MIX_FILE`; `tools/pod_mix.py` `dump_mix` / `parse_mix` is the model, `dm_load` the strict reader; the same corpus of 40 broken files is run through both):
  ```
  M1X2\n
  <day dec>\t<seed hex8>\t<art seed hex8>\t<regen dec>\t<songs dec>\n
  rrggbb rrggbb [rrggbb [rrggbb]]\n                      (2..4 tones)
  <artist>[\t<artist>[\t<artist>]]\n                      (1..3 names, UTF-8, < 96 bytes, no control byte)
  <path>\n                                               (<songs> lines: the songs' paths in play order, 1..255 bytes each, no control byte)
  ```
  Day = days since 1970-01-01 of the **local** calendar day (`localtime`), seed = `day * 2654435761 ^ regen * 0x85EBCA6B` (never 0), regen = how often today's mix was made again, songs 10..25 and
  exactly that many path lines. At most `DM_FILE_MAX` 8192 bytes; any deviation (magic, a field, a count, a control byte, a path of 0 or 256+ bytes, a missing or trailing byte) is "no mix": the section stays hidden and the
  menu is as before. The reader keeps the paths on the heap (`dm.paths`, freed with the Home window). **No compatibility**: the old `M1X1` file (it carried a playlist id) reads as no mix, and the next job makes a new one.
  **File-name rule: nothing Daily Mix writes can be read by the stock playlist Import.** `importPlayList` (`0x4ef394`) reads only `/mnt/mmc/_explaylist_data`, through `toolsGetDirectoryM3u8` (`0x5e9794`: names ending in
  `.m3u8` or `.m3u`). Every file the payload writes, temp files included, is under `/mnt/mmc/.m1plus/` (the card, never the internal flash), has no `.m3u` / `.m3u8` ending in any case and is in no `_explaylist_data` directory
  (`tracks`, `art`, `.tmp`; the switch file `/mnt/data/m1plus/home-daily-mix` is written by the Settings toggle, not by the job); `test/pod/dailymix.py` and `dmpage.py` collect every path the payload opens for writing, renames or unlinks during a full job (also on a 12,288-song library)
  and a page open and assert it.
- **`/mnt/mmc/.m1plus/daily-mix/art`** (`MIX_ART_FILE`): `M1XA`, width, height (u16), the art seed (u32), the FNV-1a of the pixels (u32), then 296 x 220 RGB565 words (130,256 bytes). Read whole (`dm_load_art`): the size, magic,
  the size fields, **the art seed of the mix file** and the checksum must all agree, else the art is made again from the mix's own tones and seed (no mix change). It is the *uncornered* art; the bitmap gets its corners when it is expanded.
- **`/mnt/data/m1plus/home-daily-mix`** (`DAILY_SET_FILE`): the Settings switch, exactly `0` or `0\n` off, anything else or no file on (read by `set_read`, docs/modules/settings.md), written atomically, a failed save changes nothing. It stays in `/mnt/data`: a device preference, not part of a card.
- All writes are `pod_card_write` (patch/common.c: temp file, `fsync`, `rename`, directory `fsync` of `MIX_DIR`, after the mounted-card check and the two `mkdir`s). The mix file is written **before** the art file, and both at the very end of the job (the `COMMIT` phase), so a job that fails or is dropped has written nothing.

## The art (`dm_*` in C; `tools/pod_dailymix.py` `art(tones, seed)` is the model, **integers only; the test compares the pixels**)

1. **Tones** (`dm_prep`): the mix's top albums' tones, in integers: lightness `l2 = max + min` (0..510), chroma `d = max - min`. A colourful tone (saturation `d / min(l2, 510 - l2)` above 0.10) gets at least 0.55 saturation and a
   lightness in [0.30, 0.56]; a grey one a lightness in [0.25, 0.66] and its saturation. The channels keep their place between min and max, so the hue stays. Pale covers do not wash the card out, dark ones do not vanish.
2. **Base**: the darkest prepared tone (`lum16`, the 16 bit sRGB table `dm_lin`, equal to `pod_dailymix.LIN16`) at 50 %.
3. **Blobs**: n tones = n blobs in n horizontal sectors, centres jittered by an xorshift32 stream seeded with the art seed (x +-0.25 sector, y 12..62 % of the height), radius 0.62..0.92 of the width; each laid over the
   running colour with alpha = 240/256 x (1 - d^2 / R^2)^2 (no exp, no sqrt).
4. **Scrim**: a black vertical scrim, 0 at row `DM_ZONE_Y - DM_RAMP` smoothstepping to a64/64 at the first title row (84) and below, **a64 the least value (at least 10) at which the brightest pixel of the text zone gives the
   dimmer ink #EBEBEB 4.7:1**: estimated from the brightest field pixel, then *verified on the dithered pixels*, one more step and another render pass until it holds or 56 is reached. Over the 71 palettes of the test the
   worst contrast of white and #EBEBEB text over the whole text zone is 4.71:1.
5. **RGB565** with a 4 x 4 Bayer dither (the panel is 16 bit).
The seed of the art is `seed ^ FNV(path of the mix's first song)`, so the card changes every day (and on Regenerate) and not on each visit. Tones come from the mix's three top **albums** (by song count, ties by first appearance):
the cover key of the album's stock row (`cc_albums` + `cc_album_key`), then the album page's tone cache (`pod_tone_get`) or **one cover decode a tick** (`cc_url` + `cc_decode` to one pixel, `pod_tone`, `pod_tone_put`); a
cover that cannot be read adds no tone; **fewer than two tones are completed from a fixed palette** (blue, rose, teal, brown) starting at `seed % 4`, up to three.

## The mix (`tools/pod_mix.py` is the model; `patch/offsets.inc` `MIX_*` hold every constant)

Inputs (all through the Songs page's own call `loadLocalClassList`): the library (`0xf001`), **Most Played** (`0xf008`; plays = `REC_TRACK` + 1, the counts start with every track start, skips included, hence the log and the cap),
**Recently Played** (`0xf007`, the last 100, newest first) and **Favourites** (`0xf00a`); songs are matched by file path (FNV hash). At most `DM_LIB_MAX` 12,288 songs of the library are read (the rest, in stock order, are not
considered), `DM_OFT_MAX` 8,192 Most Played records, `DM_FAV_MAX` 4,096 favourites.

`score = MIX_W_PLAYS (4) x lg(plays, cap 200) + MIX_W_ARTIST (2) x lg(the artist's plays over the library, cap 4000) + novelty (60 never played, 30 played once) + 50 if a favourite - 160 x (100 - position) / 100 for a
song among the last 100 played (position 0 = the last one) + a jitter of 0..127 from the seed and the path`, `lg(n) = 16 log2(1 + n)` in fixed point. Selection: **25 songs** (`MIX_SONGS`), best score first (ties: the first in
library order), **at most 2 songs of one artist and 2 of one album** (artist and album identity = the name with ASCII case folded, as the stock album list groups), then a seeded Fisher-Yates shuffle and one pass that pulls apart two
songs of one artist side by side. **The threshold:** a library of fewer than `MIX_MIN_LIB` (50) playable songs gets **no mix and no card** (two mixes' worth, so a day's mix can differ from the day before; Regenerate is dimmed, below).
**Thin libraries still get a full mix:** when the limits leave the mix short of 25 they loosen a step (`MIX_PER_ARTIST2` 4 of one artist, `MIX_PER_ALBUM2` 3 of one album), then go (no limit), so 300 songs by 3 artists
make 25 songs, not 6; the side-by-side pass is best effort. **An untagged artist or album is the song's folder** (`dm_tag`: the path up to the last `/`), so a library without tags is not one "artist" capped at 2.
Fewer than `MIX_MIN_SONGS` (10) left after the files are checked on the card: **no mix** (the day is not tried again). The weights are the `MIX_*` constants in
`patch/offsets.inc`, in one place; the model and the compiled code agree on random libraries of 556 songs (`test/pod/dailymix.py`).

## The job (`dm_*` phases; one slice per tick of the Home page's timer, `DM_TICK_MS` 30 ms; never in paint, never at boot)

While `dm.job` is set (the daily job, Regenerate and the art-only job alike) `pod_dm_busy` is shown; `dm_busy` toggles it (visible only, on a change; it stays insensitive as decorative widgets do) where the job is created, ends (commit or failure) or is cancelled (menu to the background); the window's destroy drops the pointer without touching the widget. A menu without the widget ignores it. **Not seen for a card's first mix**: the mark is a child of `pod_daily`, which stays hidden until a mix exists, so only jobs that replace a mix (the next days, Regenerate, art-only) show it; chosen over showing an empty section, which would move the menu.

A job starts when the Home menu is in front, the switch is on, `DM_START_MS` (**8 s, past the boot guard's 5 s window**) have passed since the menu opened, and the local day has no mix yet (a different day in the mix file, or no
file) **or Regenerate asked for one**; the previous mix stays on the card until the new one is committed. A day that failed (below) is not tried again until tomorrow, a restart or Regenerate; a clock before 2020 makes no mix.

| phase | one tick does | cost per tick, 12,288 songs (payload instructions under Unicorn; the stock queries are not in it) |
|---|---|---|
| `OFT`, `REC`, `FAV` | load the list (the stock query), then `DM_SLICE` 1,536 records a tick hashed into our tables | the load ticks 0.3k..0.4k (the query is stock's), a slice of Most Played 0.42M, Recent 23k, Favourites 81k |
| `LIB` | the library: path / artist / album hashes, plays, recent position, favourite, the artist's play total, `DM_SLICE` songs a tick | the load tick 0.3k, then 8 slices of 1.94M..2.01M (about 1,300 instructions a song) |
| `SCORE` | `2 x DM_SLICE` songs a tick | 4 ticks of 0.3M |
| `PICK` | one pick a tick (a scan and an update over the candidates), then the shuffle | 25 ticks of 0.48M, the shuffle 1.4k |
| `COPY` | the library read again; the picked records copied with their strings (`strdup`), a song whose file is not on the card dropped; the names and the top albums | 23k (+ the stock query) |
| `ALBUM` | the cover keys from the stock album list once, then one tone a tick | 0.21M (1,024 albums scanned), then 0.6k a tone from the tone cache (a cover decode is `cc_decode`'s) |
| `FIELD`, `BRIGHT`, `RENDER` | the blob field, the brightest pixel of the text zone, the render passes: `DM_ROWS` 20 rows a tick | 11 ticks of 0.72M..0.74M, 7 of 0.23M, 11 of 0.52M a pass (two passes here: the first scrim was one step short) |
| `COMMIT` | the mix file (with the paths), the art file, the file read back, the card switched (no playlist work) | 2.17M (the FNV over 130 KB, the expansion into the bitmap with its corners): **the largest tick** |
| `SAVE` | (an art-only job: the art file written, the bitmap switched) | the same 2.1M |

**Totals**: 556 songs 89 ticks, 24.7M instructions; 12,288 songs (`DM_LIB_MAX`) **102 ticks, 54.2M instructions, at most 2.17M in one tick** (at 1.2 GHz and an IPC of about 0.8, roughly 2.3 ms for the largest tick and 56 ms of CPU
for the whole job, spread over about 3 s: 30 ms between ticks). The first read of the art file at the menu's start is one tick of 2.16M (the checksum and the expansion). Unmeasured on the device: the stock queries between them (`getAllMusic`,
`getAllOftenRecord`, `getAllRecentRecord`, `getAllFav`, the album list).

Every list is checked at every tick (the deque handle, its size, its first and last record): another list loaded in between (or a changed library) **ends the job**; the menu going to the background **drops it** (it starts
again from the top when the menu is back). Memory: the job's tables and candidates are `calloc`ed (the library pass peaks at about 28 bytes x songs + 6 bytes x 2 slots x 3 tables), the art at 325 KB (the 195 KB field and the
130 KB RGB565 words), all freed when the job ends or fails; a refused allocation ends the job (and the day is not tried again).

## The mix as songs and as a queue (no stock playlist but the Add disc's copy; `dm_mix_find`, `dm_play_at`)

- **Storage**: the paths in the mix file (above), nothing in the stock `playlist` table (but the one-off copy the page's Add disc saves, "The Add disc"). The job's picks are copied with their strings in the `COPY` phase (a path the file cannot hold, `dm_path_ok`, or a file not on the card is dropped);
  the commit writes the file once, last of the job's work (a job that fails or is dropped by the menu going away has written nothing), then reads it back with `dm_load`, which sets the card's state.
- **The mix's rows only** (`dm_rows`; the page and the queue; **never the whole library**: the first build read 12,288 songs on the UI thread for 25 of them, getAllMusic's query, its row callback's eight mallocs a row, a sort with a
  `snprintf` comparator, then `loadSongList` copying every record, twice over): stock's own song query with another SQL, `toolsQueryDbTable(db "/mnt/data/database.db" 0x745a34, sql, row callback 0x4e9058, sort 0)` (the call `sort_first_alphabet` 0x4ea0ac makes,
  `QUERY_PINS`), the SQL `select * from songtable where fileurl in ('p1','p2',...)` built in a heap string (the paths with `'` doubled; 25 paths can pass the 1 KB buffer of the Library filter, payload.md hook 6: it then leaves the
  statement as it is, which is as correct, and the mix has no podcast path). The call goes through the hooked entry. Its callback pushes into `*tools_pdeq_directory` (`0xa03964`, `PDEQ_TOOLS_TMP`; `toolsQueryDbTable` clears it first;
  `loadLocalClassList` would assign it to `*pdeq_showlist` and clear it): **`*pdeq_showlist` is not touched**, the Songs page's list stays valid; the rows are in the database's order and `dm_rows_done` clears the deque after use (the
  typed deque frees its strings on clear and deep-copies on `_deque_push_back`, as stock's callback relies on).
- **Finding the songs** (`dm_mix_find`): over those rows, the path of each hashed once (`dm_path_hash`) and compared with the (at most 25) hashes of the mix's paths, a hit verified with `strcmp`; the first record of each path wins; a path
  not in the database is not among the rows. Cost: a few thousand instructions (it was 4.8 M on 12,288 songs).
- **Queue** (`dm_play_at`, used by the disc, a row, Play and Shuffle): the mix's rows found, those whose file is missing (`access`) left out; the start song is the wanted one (a path), the first, or with
  Shuffle a random one (`pod_rand`, Shuffle turned on with `pod_set_mode`: the payload's flag, [shuffle](shuffle.md)). The kept rows are pushed in the mix's order into a small deque, which `*pdeq_showlist` points at for one call (saved and put back, `loadSongList`
  reads the shown list): `G_CLASS_TYPE` = `0xf001`, `loadSongList(queue, name, cue, 0xf001)` (the queue gets the class and stock's memory-playback record is left as before), and **that queue is what `pod_open_player` hands to Now Playing**
  (class `0xf001`), at the index of the wanted path (searched by path: `loadSongList` finds by name and CUE start, a name shared by several songs is not enough). **After a reboot the player
  resumes in library order** (the memory-playback record is the library's; accepted). The wanted song missing from the library or the card: the usual "Storage unavailable" message, nothing starts. The small deque, the queue and the rows' deque are freed on every path.
- No `classinfo[1]` or `NAV_TITLE` write, no `allmusic_page`, no `0xff13`.

## Card taps (`dm_on_down`/`up`/`abort` on the card; the disc's `EVT_CLICK`)

- The card (pointer down/up/abort, never consuming, `RC_TAP_PX` 10 as the shelf): a tap opens **the Daily Mix page** (next section). A drag, an aborted press and a release 10 px away open nothing. When the page cannot open nothing else
  opens (no stock Songs page any more): with no song of the mix left in the library and on the card the usual "Storage unavailable" message shows; a window that does not open, no memory or an asset that is not ours does nothing.
- The disc (a stock button, its own pressed image): `dm_play` -> `dm_play_at` (below) from the first song. The play mode is the user's.

## Settings > Home Screen

Rows: **Recent Albums**, **Daily Mix** (switch, `ACT_DAILY`) in one card, **Regenerate Daily Mix** (an action row **without a chevron**, `ACT_REGEN`) in a card of its own, **last on the page** after Extras and its note (Boot to M1+ Music and Open Shanling Home are on Settings > Developer). The switch shows or
hides the section (and stops/starts the job: with it off **nothing is made**, not even for Regenerate, which waits). **Regenerate** only asks (`dailymix_regen`, a counter that outlives the Home window); the Home menu makes the
mix the next time it is in front (allow about three seconds for the sliced job after returning to Home; no page; an accepted tap shows a toast, `New mix when Home opens`, a shorter form of the row's note that fits the message box in every language; a refused tap shows nothing). Two asks before the menu is in front are one regeneration.
If Home is covered or destroyed before a manual job commits, `dm_job_cancel` restores its pending request before freeing the job. Returning to Home restarts it with the next seed from the committed mix, even if that mix is already today's. Completing a job clears the request; actual failures still stop retries as described above.
**Regenerate is hidden while no mix can be made** (`dailymix_can_regen`: the switch off, or the last job found fewer than `MIX_MIN_LIB` songs, a RAM flag `dm_small`): `patch/m1plus.c regen_show`
hides the row and its note (`pod_note3`, both at the page's end) (not visible, not sensitive; the note is never sensitive; the layouter skips them), and shows them again
the row sensitive; the Daily Mix switch updates them in place. A hidden row's tap is refused in `dailymix_regen` too. Songs added to a small library are seen by the next day's job (or after a restart), which clears the flag.
Texts (`tools/pod_i18n.py`, 13 languages and the 3 twin tables, a native-speaker pass is wanted): `Made for You`, `Daily Mix`, `Regenerate Daily Mix`, `New mix when Home opens` (the toast), `%s and more`, `%s, %s` (the join of two names: `%s、%s` in Chinese and
Japanese; never passed to printf). Widest in the shipped font: the header 162 of 296 px (ja), a title line 175 of 260 (th, 36 px), the switch row 149 of 195 (ja, 21 px), the action row 206 of 274 (fr), the artists in 2 lines
of 204 in all 13 languages (`test/pod/dailymix.py`).

## Safety

No new hook, no boot-path or main-loop code, nothing at paint but the card's own after-paint (a blit of the resident bitmap and canvas text; it allocates, decodes and reads nothing): the section's widgets, their events and the Home
page's timer only. Every failure leaves the plain menu or yesterday's mix: a missing widget, a refused `widget_on`
(any of the eight), no timer, an unreadable or malformed file, an unreadable art file (made again), no memory, no songs, a list changed under the job, a library under 10 songs, the card not mounted (nothing is read, made or written: no card section),
an unwritable file. A hidden section is hidden **and** insensitive (`visible=false` does not stop hit testing). **The job and the card call no stock playlist function; only the page's Add disc does (`dp_look` reads the list, `dp_save` writes)** (`createPlayListItem`, `checkPlayListExist`, `getPlayListMaxId`, `addPlayList`, pinned in `tools/pod.py` with
their prologues and the words of `batch_add_file` they mirror; `test/pod/dailymix.py` asserts that these names and `PDEQ_PLAYLIST` / `NAV_TITLE` / `CLASSINFO` occur in no other function; `docs/modules/playlists.md` for the Playlists page). `tools/reach.py` has no stock edit to check here (no hook, no patched word); the stock helper the mix uses, `loadLocalClassList`, is reachable from `main` only through `onlineDownloadThd`
and the navigator's page-init dispatcher: unedited stock paths. The payload's own first
entry is the Home menu's opening (`home_menu_opened` -> `dailymix_start`, from the guard's open timer, as `recent_start` and `minibar_start`): it reads the 1 KB mix file and registers events; the art file is read DM_FIRST_MS later, a mix is
made no earlier than DM_START_MS (8 s) after that.

## Validation

`test/pod/dailymix.py` checks the compiled job against the selection/art models,
file parsing and atomic writes, card absence/swaps, generation failures, translated layout,
input and shared stock scrolling. `test/pod/dmpage.py` covers the detail page.
Tests use real stock widget structures and selected layout/pointer code with modeled library,
clock and canvas services.

Device checks cover card changes, flash-write avoidance without a card, panel appearance,
AWTK title rendering, large-library query cost and playback resume after reboot.
See [device checks](device-checks.md); emulation does not establish those results.

## The page (`dp_*` in `patch/dailymix.c`, `ui/m1plus_dailymix.bin`, `tools/pod_ui.py build_dailymix_page`, `tools/pod_dailymix.py` DP_*, `patch/offsets.inc` DP_*, `test/pod/dmpage.py`, previews `tools/preview_dmpage.py` -> `out/dailymix-page/`)

An Apple Music playlist page ("Heavy Rotation"), opened by a tap on the card (the disc still plays directly). No navbar, no new hook, no boot-path code:
own window, the stock `list_view` > `scroll_view` (310 + the mobile bar) over the whole 450 px, one content view `view_dm` that paints (as the Albums list does) the art, the lines and the songs in its after-paint,
a floating glass back disc (`btn_return`, the window's last child, fixed) and, inside the content view, the Shuffle disc, the white Play pill and its glyph, and the Add disc (images are the buttons' styles). Page-scoped: its widgets, events,
one loader timer; everything freed on destroy (a destroy of another window is ignored: the event carries its window). The window, list, scroll view and content view all get the same solid tint (`widget_set_style`, black in the asset = the fallback).

| part | numbers (window px, content scrolls) |
|---|---|
| art | 320 x 180 (16:9) from y 0 (full bleed), RGBA bitmap, last 60 rows fade (smoothstep, `DP_FADE`; kept at 60 on the shorter 180 art: the render shows no seam) into the tint, full tint for the last rows (`DP_HOLD` 4). No text on it |
| back disc | 44 px touch square at (8, 8), 40 px glass disc (`dp_back`, a chevron), the only control outside the list (nothing on the top right) |
| title / subtitle / updated | centred in x 16..304 (288), boxes 24 / 17 / 14 px high at y 193 / 218 / 239 (24, 17, 14 px; one font only, Medium: "the heaviest weight" is it) |
| buttons | **Shuffle disc | Play pill | Add disc**, symmetric about x 160, all at y 263: Shuffle disc 44 x 44 touch at (32, 263) (the album page's `ah_shuffle`, 40 px drawn at x 34..74), Play pill 148 x 44 touch at (86, 263), drawn 148 x 40 white (`dp_pill`, pressed `#D6D6D8`), 16 px glyph + 8 px + text centred as a pair, glyph and text both `#141414` (the album's ink, `DP_PILL_INK`; `dp_pill`, measured with the label's style; room 100 px for the text, the widest "Play" is 88 px, de_DE; one that cannot be measured is 32 px, the album's `AB_PLAY_TEXT_W`, and the text rect is the text plus `AB_TEXT_SLACK` 4), **Add disc** `btn_dp_add` 44 x 44 touch at (244, 263), 40 px drawn at x 246..286 (`dp_add` / `dp_add_down`: Shuffle's disc, `#2A2A2A` and pressed `#444444`, with the Lucide `plus` fitted into the Shuffle glyph's 19 px box, stroke 1.5; once the mix's playlist exists `dp_added` / `dp_added_down`, the same disc with a `check`). Gaps between the drawn parts 12 px (74..86, 234..246); touch rectangles 9 px apart. The old pair was 40 + 12 + 180 |
| description | up to 2 lines of 288 px at y 317 and 337 (pitch 20, 15 px), left, 2nd line ends in an ellipsis if longer; the rows start at 371 whatever the line count |
| rows | 64 px (`LIST_ROW_H`): exactly the Albums list's numbers (`LIST_*`, used directly): cover 52 px at x `LIST_ART_X` 10 (`LIST_ART_Y`, 4 px corners, the grid ring and loader), text at x `LIST_TEXT_X` 74 (`LIST_TEXT_W` 234 wide: 21 px title, 18 px artist, `LIST_TITLE_Y` / `LIST_SUB_Y`), no star or other mark; hairline 13 % white from x 74 to the edge, pressed row 20 % white; the content is 371 + n x 64 + 16 |

**Vertical rhythm** (album page's method, `tools/ah_ink.py`, measured on the shipped font, asserted by the test): art bottom to the title's capitals 16, title baseline to the subtitle's capitals 9, subtitle baseline
to the Updated digits 9, Updated baseline to the pill's top 16, the pill's bottom to the description's capitals 16.

**Tint.** The art's last row is averaged (the card's blob field at 320 x 180, same seed and tones, so the page looks like the card), its brightest channel lifted to 48, darkened by 15/16 steps until its 16 bit luminance
is at most 0.07, snapped to the 565 grid the panel shows (so the art's last rows and the window are the same word). Greys: the artist / description line is the tint + (255 - tint) x 184/256, the Updated accent x 208/256. Over 38 palettes (pale, black,
white, saturated, random) white is >= 8.8:1, grey >= 5.15:1, accent >= 6.3:1 (floor 4.5 asserted); the grey on a pressed row is 3.12:1 (a transient). **The status bar** takes the colour of the art's top row (`dp.barc`, the average of the blob field's row 0, where the bar meets the page; darkened by `pod_bar_color` until its white glyphs keep 4.5:1) while the page is in front, as the album page and Now Playing do (`dp_bar_apply` / `dp_bar_black` over `pod_bar_tint` / `pod_bar_black`, `patch/common.c`): at open and on `EVT_WINDOW_TO_FG`, only when both window events are registered; the stock black comes back on `EVT_WINDOW_TO_BG` and on destroy, and only while the bar is still the page's (Now Playing opened by Play keeps its own colour). Tested in `test/pod/dmpage.py` (the colour against the model, background, foreground, destroy, a lost bar).

**Art cost.** Made once at open, row by row straight into the bitmap (no 130 KB intermediate): **10.9 M payload instructions** in the test (about 15 ms on the device), 230 KB resident while the page is open.
Equal pixel for pixel to `pod_dailymix.page_art`; the card's generator is the same code with the card's width and height (`dm_blobs_wh`, `dm_field_wh`) and unchanged.

**Songs.** The page lists the mix file's songs that are in the library and on the card, in the mix's order (`dp_songs`: one `dm_rows` query of just the mix's paths, `dm_mix_find`, `access`, each record **copied** with its strings by `dm_rec_copy`: the query's deque is cleared by the next query). The page reads no favourites (no star column; the card's scoring still does). Cover keys: each song's album matched by title (NOCASE) to the stock album rows (`cc_albums` once, freed), else the song's own artist + album.
Covers: one per 16 ms tick, nothing while the list is dragged or flung (the Albums loader); a song's key is its own, else the library album of that name's (`cc_cover_key`, `dp_keys`); missing cache file = the placeholder disc; no background cache build here. Row tap, Play and Shuffle all go through `dm_play_at` (the previous section):
the library is read again and the mix found in it (the page's copy may be older), the tapped song is looked for by its path, the file is checked (`access`; missing = the "Storage unavailable" toast, the page stays),
`loadSongList` (class `0xf001`) and the mix's own queue, `pod_open_player` opens Now Playing at that index. **Play** (the page's and the Home card's disc) = in order from the first song in an in-order mode (`pod_set_in_order`: Shuffle and Repeat one become List play, the others are kept; a row tap keeps the mode); **Shuffle** = the stock Shuffle mode (`pod_set_mode`, as the album page) and a random start
(`pod_rand`), the queue is the whole mix. The page keeps its copy while open (the mix can only be regenerated with Home in front,
so it cannot change under the page). **No Regenerate disc**: the job runs on the Home page's timer and needs Home in front, so the page cannot safely rebuild and refresh itself; the row is Shuffle | Play | Add, symmetric about x 160.

**The Add disc** (`dp_save`, `dp_on_add`; `btn_dp_add`'s `EVT_CLICK`; `dp_look`, `dp_mark`). One tap makes a NEW stock playlist and no dialog, **once per mix**: the name is the translated "Daily Mix" + a space + the mix's own day as `YYYY-MM-DD` (`dp_civil` of the mix file's day, not today's), e.g. `Daily Mix 2026-10-29`
(`Tagesmix 2026-10-29`, `デイリー ミックス 2026-10-29`; at most 96 bytes). Sequence: (1) the page's rows (the mix's songs that are in the library and on the card, in the mix's order) are checked again for a song record (`REC_TYPE` 8) and the file (`access`); none left: "Storage unavailable", no
playlist; (2) the browsing class `*0x97cad4`, `classinfo[0..1]` and `nagvation_title` (512 bytes) are saved; (3) `loadLocalClassList(0xf00b)` reads the stock playlist list into `*pdeq_playlist` (the Playlists page's New path, `pl_create`), `createPlayListItem(list, name)`: **-2** (exists): the stock `msg_playlistexist` and the disc a check; **-1** (full, 100 playlists): `msg_playlistfull`; else the result is the playlist's id; (4) **the songs, one by one in the mix's order**, as the stock batch add (`batch_add_file` `0x4da7dc`, class `0xf001` -> `0xf00b`, `0x4db34c..0x4db3d0`) adds a row of the library: a **copy** of the page's record (the stock
library list and the page's rows are not written to; stock writes into the source record), `checkPlayListExist(rec, id)` (1 = skip), `getPlayListMaxId()`, `REC_ID` = max(100, that) + 1, `REC_DISC` (cd_num) = the playlist's id, `addPlayList(rec)` (the song row keeps the library's tags, as an Import's does); (5) the saved globals are put back, then the stock message
`msg_addplaylistsuccess` ("Added To Playlist", key added to the STOCK table of `tools/pod_i18n.py`, 13 languages are stock's), or `msg_addfailed` when no row went in. Why not `batch_add_file` itself: it walks the selection in the list's order (library order), the mix needs its own order, and it needs the stock selection vector over the library deque (one `select_recordinit` of up to 12,288
entries per call). The mix file is not touched and nothing is written to a file (the playlist is a row of `/mnt/data/database.db` written by the stock `addPlayList`; **no file the Daily Mix writes is importable by the stock Import**, line 46, and this adds none). **Saved: a check.** `dp_look` reads the stock playlist list (`loadLocalClassList(0xf00b)`, the globals put back) when the page opens and each time it comes to the front after having been behind (the playlist may have been deleted on the Playlists page meanwhile), and looks for a row whose `REC_TITLE` is exactly the name; found, or made by a tap (or -2), the disc's three icons become `dp_added` / `dp_added_down` (`dp_mark`, `widget_set_prop_str`) and a tap only shows `msg_playlistexist` (no query, no second playlist); not found, the plus. A full table (-1) leaves the plus. The disc is always shown and sensitive. UI thread, a database write per song (25), the same as the stock add.
**Rename: the stock firmware has none.** Searched with `tools/stock.py` (`syms`, `strings`, `ui`): the playlist functions are `createPlayListItem`, `deletePlaylist`, `deleteAllMusicByPlaylist`, `addPlayList`, `checkPlayListExist`, `checkPlayListByName`, `getPlayListMaxId`, `getAllPlayList`, `getMusicByPlayList`, `importPlayList`, `exportPlayList`, `deleteMusicFromPlaylist`; no update / rename / edit call, no rename / edit / modify string
in the `en_US` table (only "Modify Album Information" and "Change Track Information"), and the Playlists page offers New, Import, Export and (multi-)Delete only. The only way to another name is a new playlist (or, not tried, Export, rename the `.m3u8` on the card, Import); no rename is implemented here (`docs/modules/playlists.md`).
**Open cost** (test, instructions, art excluded): 0.15 M on a 72-song library, **4.8 M on 12,288 songs**; the art adds 10.9 M. No song of the mix left in the library and on the card: no page and the "Storage unavailable" message; a missing widget (asset not ours): the window goes again (`navigator_back`) and nothing opens; no window or no memory: nothing happens. No memory for bitmaps: the page opens on its tint without art or covers.

**Updated line.** The mix file's local day against today (`dm_today`): `Updated today` / `Updated yesterday` / `Updated 2026-10-26` (ISO date, `dp_civil`; no month names to translate; a clock that is not set or went back says today).
New keys (13 languages, native-speaker pass wanted): `Updated today`, `Updated yesterday`, `Updated %s`, `Play`, `Songs you love and some to rediscover, made fresh every day.`; every line fits in all 13 (widest `ja_JP`), the description is two lines at most.

**Pins.** The page uses already pinned calls (`window_open`, `widget_set_style`, `widget_load_image`, `widget_move`, `widget_measure_text`, `canvas_*`, `loadLocalClassList`, `loadSongList`); the Add disc adds `checkPlayListExist` `0x4ee1a8`, `getPlayListMaxId` `0x4ee184` and `addPlayList` `0x4ee1cc` (`FUNCTIONS`; prologues of these three and of `createPlayListItem` `0x4eeca8` in `PLAYLIST_PINS`,
checked at build with the words of `batch_add_file` they mirror: the two `bal`s `0x4db34c` / `0x4db360`, the `max(100, ..)` words `0x4db380..0x4db38c`, the two stores `0x4db3a4` (id) / `0x4db3c0` (cd_num) and the call of `addPlayList` `0x4db3d0` / `0x4daff8`), `docs/modules/addresses.md`. New names: asset `ui/m1plus_dailymix.bin`
(window `m1plus_dailymix_page`), widgets `dp_listview`, `dp_scrollview`, `view_dm`, `btn_dp_shuffle`, `btn_dp_play`, `img_dp_glyph`, `btn_dp_add`, `btn_return`, labels `label_dp_*`, hidden `label_title`; images `dp_back`, `dp_back_down`, `dp_pill`, `dp_pill_down`, `dp_play`, `dp_add`, `dp_add_down`, `dp_added`, `dp_added_down`.
**Tests** (`test/pod/dmpage.py`): section 1 the symmetric geometry (drawn 34..74 / 86..234 / 246..286, 12 px gaps, mirrored about 160, touch rectangles apart, >= 44 px), the asset's `btn_dp_add` and its images (the Shuffle disc's size, shape and greys, a centred plus as large as the Shuffle glyph, byte for byte with the generator), the pill's text fit
in all 13 languages (room 100 px); section 6 hit tests (the Add disc takes x 243..287, the gaps nothing); section 6b the Add disc: the dated name from the mix's day (and in 13 languages), after a tap a check and a second tap makes nothing (`msg_playlistexist`), a check when the name is in the list at opening (a near name is not), a plus again after the page was behind and the playlist went, -2 -> a check, full -> `msg_playlistfull` and still a plus, the songs in the mix's order with consecutive ids from `max(100, max) + 1` and the playlist's id,
files gone are skipped, none left -> no playlist, a song already in it skipped, the stock library records and the mix file untouched, the browsing class / classinfo / title put back after the mocked stock calls clobbered them, the success message, an asset without the disc falls back; `test/pod/dailymix.py` the playlist calls exist only in the Add disc code (`dp_name` .. `dp_save`).
Not seen on a device: the look of the fade on the panel, whether the content view's children (the buttons) paint under the scroll offset as in the album page, widget_set_style of the tint on the four widgets, the stock queries' cost; **the Add disc**: the look of the plus disc beside Shuffle, that `addPlayList` with a shallow copy of the page's record produces the same rows as the stock picker (the stock reads `REC_ID` / `REC_DISC` and the strings only, from the disassembly), that the
new playlist opens on the Playlists page with the 25 songs in the mix's order (`getMusicByPlayList` has no ORDER BY: insertion order), the message box over the page, the time of 25 inserts on the UI thread, and that `createPlayListItem`'s id range (1..100) matches what `-2` / `-1` mean in practice.

The Home card's existing job timer defers its work while the screen is off, checking at most once per second, and resumes on its first lit check. A mix due at midnight stays yesterday's until the screen is on and Home is foreground; there is no midnight background job.
