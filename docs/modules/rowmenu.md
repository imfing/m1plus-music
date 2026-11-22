# Track rows' "..." menu (Play Next, Play After, Add to Playlist, Favorite, Get Info)

A grey "..." at the right end of every track row opens a bottom sheet in the look of Now Playing's More sheet ([playmore](playmore.md)).
Pages: the album page (`patch/albumpage.c`) and the Songs page (`patch/songs.c`) with every list it hosts (the library, a playlist, genre, artist, Most Played,
Recently Played / Added, Hi-Res, Favourites; whatever `sg.cls` covers). Not covered: Search, Daily Mix, the Albums grid, Folders, Podcasts rows; a "..." pressed state.

**Sources:** `patch/rowmenu.c` / `rowmenu.h` (open, close, the "..." bitmap and its painter, the actions), `patch/songinfo.c` (Get Info, [songinfo](songinfo.md)), the pages' row painters, hit tests and one-row
`Add to Playlist`, `patch/upnext.c` (`upnext_add`, [queue](queue.md)), `patch/songops.c` (`so_add`), `patch/picker.c`, `tools/pod_ui.py` (`row_menu`),
`tools/mod_icons.py` (`RM_MENU_ICONS`, `RM_DOTS`, `GLASS_ROWMENU`), `patch/offsets.inc` (`RM_*`), `tools/pod_i18n.py`.
## What the user sees

- **The "..."**: the Lucide ellipsis (24 px, `rm_dots`, solid dots) in `#8C8C8C` (6.2:1 on black, no accent), in a `RM_MORE_W` 44 px tap zone: centred, except beside the Songs page's A-Z rail where it is right-aligned (bitmap x 260..284, ink ending at 281; `rowmenu_paint`'s `flush`), 19 px down the 64 px row (centred above the hairline).
  The title (and the Songs page's artist line) end `RM_INK_GAP` 10 px before the glyph's ink (the bitmap's ink spans columns 3..20, `RM_INK_X` 3), the chevron rows' gap, so text never runs under it; `rowmenu_text_end(right, flush)` is the one place that computes it. The hairline keeps its old length.

  | Page | Zone | Text ends |
  |---|---|---|
  | album page | x 266..310 (`RM_MORE_RIGHT` 310) | 269 |
  | Songs, no rail (a list, or an order with no sections) | x 266..310 | 269 |
  | Songs, A-Z rail shown | x 240..284 (`RM_MORE_RIGHT_RAIL`: flush with the rail's touch column, which starts at 284); the "..." right-aligned in it | 253 |
  | Queue, Up Next rows | x 266..310 | 269 |

  Select mode has no "...": a tap marks the row. An asset without the menu's widgets also leaves the old rows. The state is read once, when the page opens (`rowmenu_bind`), and again at every open of the menu.
- **Tap**: the page's own press rules. DOWN in the zone remembers it (no press fill: only a tap elsewhere in the row highlights), ABORT (the scroll_view took a drag) forgets it, UP within
  `SC_DRAG_PX` 10 px of the press, on the same row and still in the zone opens the menu. A drag, a scroll, a press that moves 10 px or more, a press that began in the zone and ended off it
  and a release on the title block, a section header or the air below the last row open nothing. A press that began elsewhere in the row and moved a few pixels into the zone is a row tap
  (it plays, as it always did). The rest of the row plays the song as before.
- **Long press**: a press on a row (anywhere on it, the "..." zone included) held `RM_LONG_MS` 500 ms without moving `SC_DRAG_PX` 10 px opens the same menu while the finger is still down. The row's press fill is cleared and the release afterwards does nothing. A scroll (ABORT), a move of 10 px or more or an earlier release cancels it (`rowmenu_hold_start` arms one timer, `rowmenu_hold_stop` / `rowmenu_hold_move` cancel it; `rowmenu_close` stops it too). Select mode (a tap still marks), section headers, the pinned header, the title block and the air below the last row have none. Songs page, album page and the Queue page's Up Next rows (while their "..." shows) have it; no haptics.
- **The sheet** copies Now Playing's More sheet ([playmore](playmore.md) "Glass"): a full-window `#00000082` scrim (the sheet's dim) whose tap closes the menu, then `rm_card`, 320 x 250 on the
  window's foot (window y 200..450, screen 230..480) with `pc_sheet5` (`mod_icons.glass_image(320, 250, 18, GLASS_SHEET_FILL, top_only=True)`: top corners only) as its `bg_image`, drawn 1:1.
  Five full-width 50 px rows: a bare 24 px Lucide glyph at x 14 (the accent with one picked, as every sheet's glyphs: `ACCENT_GLYPH_STOCK`, [accent](accent.md)) and the 18 px white label from x 48 to 298 (the sheet's own rows, `pod_tape`), rows transparent and `#FFFFFF10` pressed,
  the sheet's `#FFFFFF22` hairline above every row but the first. Rows, top to bottom: **Play Next** (`list-start`), **Play After** (`list-end`), **Add to Playlist** (`list-plus`), **Favorite** (`star`; "Undo Favorite" with the filled star `rm_ic_unfav` when the track is a favourite), **Get Info** (`info`).
  The label is "Play After", not "Play Last". The hairline sits above every row (not only between the groups). No Go to Album / Go to Artist.
- **Place and width** are the asset's for every row and language: the payload only shows and hides the scrim and the sheet. The longest label of the 13 languages (Russian, 212 px) fits the 250 px box.

## Actions

A sixth row, **Pin Song** / **Unpin Song**, shows for a song of the card (not a source's row, whose sheet keeps five rows and the five-row glass); see `docs/modules/pins.md`. A seventh, **Remove from Playlist** (`rm_ic_remove`), shows only on a page that registered it with `rowmenu_set_remove` (a stock playlist's songs page) for a playlist song record (`REC_ID` over 100); with Pin Song hidden it moves up into the sixth place. `rm_tail_rows` shows them and `rowmenu_set_rows` sizes the glass to the rows shown (`pc_sheet5` to `pc_sheet7`). The row calls the page's function with the menu's record copy after the sheet closed ([playlists](playlists.md) "Remove from Playlist").


| Row | What it does |
|---|---|
| Play Next / Play After | `rowmenu_open_src` copies the row's `stSongInfo` into a one-row deque (`_create_deque("stSongInfo")`, `_deque_push_back`, as `albums_open_artist` builds its carrier), so a list read again under the open menu cannot pull the row away. The row calls `upnext_add(rows, after)` (0 Play Next, 1 Play After), destroys the deque, closes the menu, then toasts with `pod_toast`. |
| Add to Playlist | closes the menu, then the page's `*_add_one(row)`: a bit for that row in the page's own select bitset (`sg.sel` / `ab.sel`), `so_add(cls, count, sel, 1, valid, ...)` (our picker, `patch/picker.c`, or where it cannot open the stock one with the stock selection vector filled with that row), the bitset cleared again. The picker's return is the page's existing `EVT_WINDOW_TO_FG` handling. |
| Favorite | stock's own star calls on the row's copy (`manage_myfav` 0x4ef884: `checkFavExist`, then `deleteMusicFromFav` or `addMyFav`; the table Now Playing's star and the Playlists page's Favorites read). The state is read at every open (`rowmenu_open_src` sets the label and the glyph's image) and again after the call: a call that changed nothing toasts "Adding Failed", else "Added to Favorites" / "Removed from Favorites". An open Favourites list is not read again until its page returns to the front. |
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
| `UPNEXT_MISSING` | "File not found" with the card in, "Storage unavailable" without it (`so_missing`) |
| `UPNEXT_FULL` | "Queue is full" |
| `UPNEXT_MEMORY` | "Not enough memory" |
| `UPNEXT_DLNA` | "Not available while DLNA is on" |

## A library source's rows

`rowmenu_open_src(rm, row, rec, add, src)` (the pages pass their `src`, NULL for the card's library) shows the same five-row card for a Navidrome track ([subsonic](subsonic.md) "Row sheet"): the third row is **Download**
(`rm_ic_dl`), **Cancel Download** (`rm_ic_cxdl`, waiting or running) or **Remove Download** (`pc_ic_trash`, on the card) from `src->row` (`ls_row_t.dl`), in place of Add to Playlist; Favorite / **Undo Favorite** follows `ls_row_t.fav`
and goes through `src->act(LS_ACT_FAVORITE)` (no stock myfav call); the words and glyph of the third row are set at every open (Add to Playlist and `rm_ic_add` again for the stock library). Download, Cancel and Remove are
`src->act` (`LS_ACT_DOWNLOAD`, `LS_ACT_CANCEL_DL`, `LS_ACT_DELETE_DL`); the row re-paints when `src->gen` moves. Play Next / Play After hand `src->queue_row(rec)` (a stock queue record: the stream address or the local file, its
synthetic id added to the queue map by `sba_queue_add`) to `upnext_add`, which skips the file test for a stream address whose id the map knows; the source shows why when it cannot (offline and not downloaded). An undownloaded DSD
row asks `ls_dsd_confirm` instead ("Download to Play?"). Get Info is `songinfo_open` (it reads the source's data for an `nd://` record).

## The Queue page's sheet

The Queue page ([queue](queue.md) "Row edit") reuses this menu for its Up Next rows: same widgets, scrim, glass, row look and "..." painter, in a three-row form. The page's asset holds `row_menu(queue=True)`: `rm_card` 320 x 150 on `pc_sheet3` with `rm_item0..2`, rows **Play Next**, **Play After** and (under the one hairline) **Remove from Queue** (`rm_ic_remove`, `list-x`, bare 24 px, an accent glyph by the `rm_ic_` prefix). `rowmenu_bind_queue` binds those three (and sets `rowmenu_t.queued`), `rowmenu_open_queue(rm, row, fn)` shows the sheet with no row copy and no source, and a tapped row closes the sheet and calls `fn(row, RMQ_NEXT / RMQ_AFTER / RMQ_REMOVE)`: the page does the act (`pod_queue_move` / `pod_queue_remove`), not `upnext_add`. Everything else (close on the scrim, the "..." bitmap, `rowmenu_paint`) is shared. The Artists page's long press sheet uses the same three-row form (`row_menu(pins=True)`, callbacks `RMP_*`). The album long press sheet on the Albums page and Home ([pins](pins.md)) uses a five-row form (`row_menu(album=True)`, `rowmenu_bind_album`, `pc_sheet5`, callbacks `RMA_*`) with **Play**, **Shuffle**, **Play Next**, **Play After**, and **Pin Album** / **Unpin Album** (Home shrinks it to three rows for playlists and artists, and two for songs). A page whose asset has only the track sheet shows the same five rows with `rowmenu_open_album` (the Recently Added album grid): it rewords the first five rows, hides the other two and sets `rowmenu_t.alt`, and the next `rowmenu_open_src` restores the track sheet's words. `rowmenu_upnext_toast` formats the toast of any `upnext_add` status.

## Design notes

- No widget per row: the "..." is a bitmap (`rm_make_dots`: the image `rm_dots` decoded by `cc_decode`, its red channel the coverage, `#8C8C8C`) drawn by `rowmenu_paint` from the page's row painter with
  the chevrons' crop to the list's view, and the zone is hit-tested in the page's `EVT_POINTER_DOWN/UP` handlers (`sg_in_zone`, `ab_in_zone`). The asset holds only the hidden, insensitive `rm_scrim`
  and `rm_card` (with `rm_item0..6`, `rm_icon0..6`, `rm_label0..6`, on the seven-row `pc_sheet7`) as the window's last two children (`pod_ui.row_menu`, after the sort card on the Songs page and the navbar on the album page).
- `rowmenu_t` lives in each page's state (`sg.rm`, `ab.rm`); the page text edge follows `rowmenu_on` and, on Songs, the rail (`sg_edge`). A list read again with the rail's presence changed drops its text tiles
  (`sg.tend`): their ellipses were cut for the other width.
- No Go to Album / Go to Artist. Removing a queued song is the Queue page's own sheet, above.
