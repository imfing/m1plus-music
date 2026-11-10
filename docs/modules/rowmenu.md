# Track rows' "..." menu (Play Next, Play After, Add to Playlist, Favorite, Get Info)

A grey "..." at the right end of every track row opens a bottom sheet in the look of Now Playing's More sheet ([playmore](playmore.md)).
Pages: the album page (`patch/albumpage.c`) and the Songs page (`patch/songs.c`) with every list it hosts (the library, a playlist, genre, artist, Most Played,
Recently Played / Added, Hi-Res, Favourites; whatever `sg.cls` covers). Not in this phase: Search, Daily Mix, the Albums grid, Folders, Podcasts.

**Sources:** `patch/rowmenu.c` / `rowmenu.h` (open, close, the "..." bitmap and its painter, the actions), `patch/songinfo.c` (Get Info, [songinfo](songinfo.md)), the pages' row painters, hit tests and one-row
`Add to Playlist`, `patch/upnext.c` (`upnext_add`, [queue](queue.md)), `patch/songops.c` (`so_add`), `patch/picker.c`, `tools/pod_ui.py` (`row_menu`),
`tools/mod_icons.py` (`RM_MENU_ICONS`, `RM_DOTS`, `GLASS_ROWMENU`), `patch/offsets.inc` (`RM_*`), `tools/pod_i18n.py`.
**Tests:** `test/pod/rowmenu.py` (five sections; `fav_info_tests`: the toggle, its label and glyph, the toasts, a failed add, Get Info); the pages' own tests keep their old numbers with no menu assets (`test/pod/songs.py`, `albumpage.py`).
**Preview:** `uv run python -I tools/preview_rowmenu.py work/mod-release out/preview/rowmenu.png` (also `tools/preview_songs.py`).
Evidence tags: **[S]** static (read from the stock code), **[E]** emulated (Unicorn), **[U]** untested on the device. Nothing here has been on the device: **[E]** or **[U]** throughout.

## What the user sees

- **The "..."**: the Lucide ellipsis (24 px, `rm_dots`, solid dots) in `#8C8C8C` (6.2:1 on black, no accent), in a `RM_MORE_W` 44 px tap zone: centred, except beside the Songs page's A-Z rail where it is right-aligned (bitmap x 260..284, ink ending at 281; `rowmenu_paint`'s `flush`), 19 px down the 64 px row (centred above the hairline).
  The title (and the Songs page's artist line) end `RM_TEXT_GAP` 4 px before the zone, so text never runs under it. The hairline keeps its old length.

  | Page | Zone | Text ends |
  |---|---|---|
  | album page | x 266..310 (`RM_MORE_RIGHT` 310) | 262 (was 298) |
  | Songs, no rail (a list, or an order with no sections) | x 266..310 | 262 (was 296) |
  | Songs, A-Z rail shown | x 240..284 (`RM_MORE_RIGHT_RAIL`: flush with the rail's touch column, which starts at 284); the "..." right-aligned in it | 236 (26 px narrower) |

  Select mode has no "...": the text ends where it used to and a tap marks the row. An asset without the menu's widgets also leaves the old rows. The state is read once, when the page opens (`rowmenu_bind`), and again at every open of the menu.
- **Tap**: the page's own press rules. DOWN in the zone remembers it (no press fill: only a tap elsewhere in the row highlights), ABORT (the scroll_view took a drag) forgets it, UP within
  `SC_DRAG_PX` 10 px of the press, on the same row and still in the zone opens the menu. A drag, a scroll, a press that moves 10 px or more, a press that began in the zone and ended off it
  and a release on the title block, a section header or the air below the last row open nothing. A press that began elsewhere in the row and moved a few pixels into the zone is a row tap
  (it plays, as it always did). The rest of the row plays the song as before.
- **The sheet** copies Now Playing's More sheet ([playmore](playmore.md) "Glass"): a full-window `#00000082` scrim (the sheet's dim) whose tap closes the menu, then `rm_card`, 320 x 250 on the
  window's foot (window y 200..450, screen 230..480) with `rm_glass` (`mod_icons.glass_image(320, 250, 18, GLASS_SHEET_FILL, top_only=True)`: top corners only) as its `bg_image`, drawn 1:1.
  Five full-width 50 px rows: a bare 24 px Lucide glyph at x 14 (the accent with one picked, as every sheet's glyphs: `ACCENT_GLYPH_STOCK`, [accent](accent.md)) and the 18 px white label from x 48 to 298 (the sheet's own rows, `pod_tape`), rows transparent and `#FFFFFF10` pressed,
  the sheet's `#FFFFFF22` hairline above every row but the first. Rows, top to bottom: **Play Next** (`list-start`), **Play After** (`list-end`), **Add to Playlist** (`list-plus`), **Favorite** (`star`; "Undo Favorite" with the filled star `rm_ic_unfav` when the track is a favourite), **Get Info** (`info`).
  The label is "Play After", not "Play Last". The hairline sits above every row (not only between the groups). No Go to Album / Go to Artist.
- **Place and width** are the asset's for every row and language: the payload only shows and hides the scrim and the sheet. The longest label of the 13 languages (Russian, 212 px) fits the 250 px box.

## Actions

| Row | What it does |
|---|---|
| Play Next / Play After | `rowmenu_open` copies the row's `stSongInfo` into a one-row deque (`_create_deque("stSongInfo")`, `_deque_push_back`, as `albums_open_artist` builds its carrier), so a list read again under the open menu cannot pull the row away. The row calls `upnext_add(rows, after)` (0 Play Next, 1 Play After), destroys the deque, closes the menu, then toasts with `pod_toast`. |
| Add to Playlist | closes the menu, then the page's `*_add_one(row)`: a bit for that row in the page's own select bitset (`sg.sel` / `ab.sel`), `so_add(cls, count, sel, 1, valid, ...)` (our picker, `patch/picker.c`, or where it cannot open the stock one with the stock selection vector filled with that row), the bitset cleared again. The picker's return is the page's existing `EVT_WINDOW_TO_FG` handling. |
| Favorite | stock's own star calls on the row's copy (`manage_myfav` 0x4ef884: `checkFavExist`, then `deleteMusicFromFav` or `addMyFav`; the table Now Playing's star and the Playlists page's Favorites read). The state is read at every open (`rowmenu_open` sets the label and the glyph's image) and again after the call: a call that changed nothing toasts "Adding Failed", else "Added to Favorites" / "Removed from Favorites". An open Favourites list is not read again until its page returns to the front. |
| Get Info | closes the menu, `songinfo_open(rec)` on the row's copy, frees the copy ([songinfo](songinfo.md)). |
| scrim | closes the menu (and drops the copy). |

The menu also closes when the page reads its list again (`sg_load` / `ab_load`: the row is an index into the old list), when the window goes behind another and when the page is destroyed.

| `upnext_add` | Toast (13 languages in `tools/pod_i18n.py`) |
|---|---|
| `UPNEXT_ADDED` | "Playing Next" (Play Next), "Added to Queue" (Play After) |
| `UPNEXT_STARTED` | none: nothing was playing, the row is the queue and plays; the page stays (opens nothing, unlike a row tap, which opens Now Playing) |
| `UPNEXT_EMPTY` | "Adding Failed" (the stock `msg_addfailed`; cannot happen from a row) |
| `UPNEXT_STREAM` (also while a Radio station connects, plays or is paused) | "Not available while streaming" |
| `UPNEXT_FOLDER` | "Not available for folder playback" (also Podcasts' play type) |
| `UPNEXT_PODCAST` | "Not available for podcasts" |
| `UPNEXT_MISSING` | "Storage unavailable" |
| `UPNEXT_FULL` | "Queue is full" |
| `UPNEXT_MEMORY` | "Not enough memory" |
| `UPNEXT_DLNA` | "Not available while DLNA is on" |

## A library source's rows (ND-14)

`rowmenu_open_src(rm, row, rec, add, src)` (the pages pass their `src`; `rowmenu_open` is it with NULL) shows the same five-row card for a Navidrome track (docs/modules/subsonic.md "Row sheet"): the third row is **Download**
(`rm_ic_dl`), **Cancel Download** (`rm_ic_cxdl`, waiting or running) or **Remove Download** (`rm_ic_rmdl`, on the card) from `src->row` (`ls_row_t.dl`), in place of Add to Playlist; Favorite / **Undo Favorite** follows `ls_row_t.fav`
and goes through `src->act(LS_ACT_FAVORITE)` (no stock myfav call); the words and glyph of the third row are set at every open (Add to Playlist and `rm_ic_add` again for the stock library). Download, Cancel and Remove are
`src->act` (`LS_ACT_DOWNLOAD`, `LS_ACT_CANCEL_DL`, `LS_ACT_DELETE_DL`); the row re-paints when `src->gen` moves. Play Next / Play After hand `src->queue_row(rec)` (a stock queue record: the stream address or the local file, its
synthetic id added to the queue map by `sba_queue_add`) to `upnext_add`, which skips the file test for a stream address whose id the map knows; the source shows why when it cannot (offline and not downloaded). An undownloaded DSD
row asks `ls_dsd_confirm` instead ("Download to Play?"). Get Info is `songinfo_open` (it reads the source's data for an `nd://` record). Tests: `rowmenu/source_tests` (album page and Songs page over fake sources).

## Design notes

- No widget per row: the "..." is a bitmap (`rm_make_dots`: the image `rm_dots` decoded by `cc_decode`, its red channel the coverage, `#8C8C8C`) drawn by `rowmenu_paint` from the page's row painter with
  the chevrons' crop to the list's view, and the zone is hit-tested in the page's `EVT_POINTER_DOWN/UP` handlers (`sg_in_zone`, `ab_in_zone`). The asset holds only the hidden, insensitive `rm_scrim`
  and `rm_card` (with `rm_item0..4`, `rm_icon0..4`, `rm_label0..4`) as the window's last two children (`pod_ui.row_menu`, after the sort card on the Songs page and the navbar on the album page).
- `rowmenu_t` lives in each page's state (`sg.rm`, `ab.rm`); the page text edge follows `rowmenu_on` and, on Songs, the rail (`sg_edge`). A list read again with the rail's presence changed drops its text tiles
  (`sg.tend`): their ellipses were cut for the other width.
- The temporary Developer rows "Test: Play Next / Test: Play After" (`ACT_UPNEXT_NEXT` 50, `ACT_UPNEXT_AFTER` 51), their log `/mnt/mmc/queue-probe.log` and their texts are gone; the ids 50 and 51 are unused.
- Not done: Search, Daily Mix, Albums, Folders and Podcasts rows; a "..." pressed state; a menu on a long press; Go to Album / Go to Artist (dropped by the user); removing a queued song.

## Tests (`test/pod/rowmenu.py`, emulated)

`asset_tests` (both assets: the menu last; the sheet's place, rows, glyphs, labels, hairlines; `rm_glass` and the glyph PNGs are the generator's; white labels >= 7:1 on the glass over black and over
white under the dim, at rest and pressed; the "..." 6.2:1 on black; the Developer rows, their ids, texts and `upnext_test` gone; every text in 13 languages),
`paint_tests` (the "..." at the right place (right-aligned beside the rail, centred without it and on the album page); the text widths 162 / 188 / 220; none in select mode, without the widgets;
the bitmap's pixels), `touch_tests` (tap in the zone, one pixel left of it, first pixel of it, a drag, an abort, a press that leaves the zone, the title block, a section header, select mode, both pages),
`menu_tests` (the sheet shown in the asset's place for rows on both pages, nothing moved or resized; every label of the 13 locales fits 250 px with the real font; Play Next / Play After with every status:
the call, the one-row deque, destroy, close, toast and nothing else opened; Add to Playlist with our picker and with the stock fallback: class, count and exactly one mark, a second Add carries only its own row; the
menu closing with the page). `upnext_add` and `picker_open` are trapped there: their own tests are `test/pod/upnext.py` and `picker.py`.

## Device checklist (all [U])

Use Songs (a library with sections and the rail), a playlist, Favourites and an album page.
1. **Tap target**: the "..." on the real touchscreen is hit with a thumb at 44 px wide; the rail's side (x 240..284; a tap at 284 or right of it is the rail) and the right edge (266..310) both. Taps just left of the zone play the song.
2. **No accidental opens**: scroll the list starting your finger on a "...": the list scrolls, no menu opens, no song starts. A slow slide off the zone and a double tap behave.
3. **Look**: the dots are neutral grey (not too faint), the title and artist never run under them (try a long title), the Songs rail does not touch the zone.
4. **Menu**: the sheet rises from the screen's foot for any row (top, middle, bottom, the album page) and looks like Now Playing's More sheet (glass, glyph size, hairlines); the scrim
   dims the page and a tap on it closes the menu; a long language (German, Russian) is not cut.
5. **Play Next**: with a song playing, "Playing Next" shows, the song is first under Up Next on the Queue page and plays after the current one; **Play After**: "Added to Queue", last under Up Next
   ([queue](queue.md) device checklist for gapless, Shuffle and Repeat).
6. **Nothing playing** (after a reboot): Play Next starts the song with no toast and the page stays.
7. **Refusals**: while a stream, a folder play, a podcast or with the DLNA switch on and Wi-Fi connected: the toast of each; nothing changes in the queue.
8. **Add to Playlist**: the picker opens for that song alone (the playlist gets only it; a duplicate is skipped), returns to the page, the list is the same.
9. **Select mode**: no "..." and the text wide again; tapping rows still marks them. Leaving it brings the "..." back.
10. A long list: the menu on the 1st and the 500th row; scroll with the menu closed after use (no stuck press fill).
11. **Favorite**: the star fills and the row reads "Undo Favorite" the next time; the song shows under Playlists > Favorites and Now Playing's star is on for it; Undo removes it. **Get Info**: the page shows the right format, rate, depth, duration and size for a FLAC, an MP3 and an M4A (rate and depth rows absent), a long path wraps, Back returns to the list.
