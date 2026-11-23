# Item sheets: the track rows' "..." menu and its forms

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
- **The sheet** copies Now Playing's More sheet ([playmore](playmore.md) "Glass"): a full-window `#00000082` scrim (the sheet's dim) whose tap closes the menu, then `rm_card` on the
  window's foot, as high as its rows, with `pc_sheet<n>` (`mod_icons.glass_image(320, 50 n, 18, GLASS_SHEET_FILL, top_only=True)`: top corners only) as its `bg_image`, drawn 1:1.
  Full-width 50 px rows: a bare 24 px Lucide glyph at x 14 (the accent with one picked, as every sheet's glyphs: `ACCENT_GLYPH_STOCK`, [accent](accent.md)) and the 18 px white label from x 48 to 298 (the sheet's own rows, `pod_tape`), rows transparent and `#FFFFFF10` pressed.
- **Groups** ([ui-rules](ui-rules.md) "Item sheets"): the rows come in groups with one `#FFFFFF22` hairline between two groups (`rm_hair0` / `rm_hair1`, 320 x 1 views, the card's last children, shown with `widget_set_visible` only: they stay insensitive) and none inside a group or above the first row. The track sheet, top to bottom:
  **Pin Song** / **Unpin Song** (`pin` / `pin-off`; a song of the card only), **Add to Playlist** (`list-plus`), **Favorite** (`star`; "Undo Favorite" with the filled star `rm_ic_unfav` when the track is a favourite), **Get Info** (`info`) |
  **Play Next** (`list-start`), **Play After** (`list-end`) | **Remove from Playlist** (a stock playlist's songs page only). The label is "Play After", not "Play Last". No Go to Album / Go to Artist.
- **Place**: `rm_layout(rm, seq, len)` lays every sheet out from a sequence of the asset's row indices with `RM_BREAK` between groups: the rows listed `PM_ROW_H` apart from y 0, the others hidden, a hairline on the top edge of each later group's first row, the card moved to `AH_WIN_H` minus its height and given the glass of that many rows (`pc_sheet1..7`). The track sheet's widget indices keep their meaning (`rm_item0` Play Next .. `rm_item6` Remove from Playlist); only their places follow the groups. The longest label of the 13 languages (Russian, 212 px) fits the 250 px box.
- **Destructive rows** (Remove from Playlist, Remove from Queue) have the red label `RED_RGB` and the red `list-x` glyph `pod_ic_remove_red` (in `ACCENT_GLYPH_NOT`: no accent tints it), as the other sheets' Delete rows.

## Actions

**Pin Song** / **Unpin Song** shows for a song of the card (not a source's row); see `docs/modules/pins.md`. **Remove from Playlist** shows only on a page that registered it with `rowmenu_set_remove` (a stock playlist's songs page) for a playlist song record (`REC_ID` over 100). `rm_track_rows` decides both at every open and lays the sheet out (five to seven rows). The row calls the page's function with the menu's record copy after the sheet closed ([playlists](playlists.md) "Remove from Playlist").


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
| `UPNEXT_FOLDER` | "Not available for folder playback" |
| `UPNEXT_PODCAST` | "Not available for podcasts" |
| `UPNEXT_MISSING` | "File not found" with the card in, "Storage unavailable" without it (`so_missing`) |
| `UPNEXT_FULL` | "Queue is full" |
| `UPNEXT_MEMORY` | "Not enough memory" |
| `UPNEXT_DLNA` | "Not available while DLNA is on" |

## A library source's rows

`rowmenu_open_src(rm, row, rec, add, src)` (the pages pass their `src`, NULL for the card's library) shows the same sheet for a Navidrome track ([subsonic](subsonic.md) "Row sheet"), five rows (Download, Favorite, Get Info | Play Next, Play After): the Add to Playlist row is **Download**
(`rm_ic_dl`), **Cancel Download** (`rm_ic_cxdl`, waiting or running) or **Remove Download** (`pc_ic_trash`, on the card) from `src->row` (`ls_row_t.dl`), in place of Add to Playlist; Favorite / **Undo Favorite** follows `ls_row_t.fav`
and goes through `src->act(LS_ACT_FAVORITE)` (no stock myfav call); the words and glyph of the third row are set at every open (Add to Playlist and `rm_ic_add` again for the stock library). Download, Cancel and Remove are
`src->act` (`LS_ACT_DOWNLOAD`, `LS_ACT_CANCEL_DL`, `LS_ACT_DELETE_DL`); the row re-paints when `src->gen` moves. Play Next / Play After hand `src->queue_row(rec)` (a stock queue record: the stream address or the local file, its
synthetic id added to the queue map by `sba_queue_add`) to `upnext_add`, which skips the file test for a stream address whose id the map knows; the source shows why when it cannot (offline and not downloaded). An undownloaded DSD
row asks `ls_dsd_confirm` instead ("Download to Play?"). Get Info is `songinfo_open` (it reads the source's data for an `nd://` record).

## The Queue page's sheet

The Queue page ([queue](queue.md) "Row edit") reuses this menu for its Up Next rows: same widgets, scrim, glass, row look and "..." painter, in a three-row form. The page's asset holds `row_menu(queue=True)`: `rm_card` 320 x 150 on `pc_sheet3` with `rm_item0..2`, rows **Play Next**, **Play After** | **Remove from Queue** (red, `pod_ic_remove_red`). `rowmenu_bind_queue` binds those three (and sets `rowmenu_t.queued`), `rowmenu_open_queue(rm, row, fn)` lays out rows 0, 1 | 2 and shows the sheet with no row copy and no source, and a tapped row closes the sheet and calls `fn(row, RMQ_NEXT / RMQ_AFTER / RMQ_REMOVE)`: the page does the act (`pod_queue_move` / `pod_queue_remove`), not `upnext_add`. Everything else (close on the scrim, the "..." bitmap, `rowmenu_paint`) is shared. The Artists and Playlists pages' long press sheets use the same three-row form (`row_menu(pins=True)`: Play, Shuffle | Pin; callbacks `RMP_*`).

## Sheets from a table

`rowmenu_open_rows(rm, row, rows, n, fn)` opens any bound menu with a table of `rowmenu_row_t` (words, glyph, act) and `RM_GROUP` breaks: the asset's rows are worded in order, their acts kept in `rowmenu_t.act`, the sheet laid out by `rm_layout`, `rowmenu_t.alt` set; a tapped row calls `fn(row, act)` once the sheet has closed. On the track sheet's widgets the next `rowmenu_open_src` puts the track words back (rows 0, 1 and 4; no table rewords row 6). Users:

| Sheet | Rows (act) |
|---|---|
| Album (`rowmenu_open_album`: Albums long press, the Recently Added album grid, Home's Recently Played, an album pin on Home) | Play, Shuffle \| Pin Album / Unpin Album, Add to Playlist \| Play Next, Play After (`RMA_*`); the album form of the asset (`row_menu(album=True)`, `rowmenu_bind_album`, 6 rows) or the track sheet's |
| Album page "..." (the library's, [album-page](album-page.md)): the popup form, below | Select \| Pin Album / Unpin Album (a titled album), Add to Playlist \| Play Next, Play After (20 px `pod_ic_vs*` glyphs) |
| Home: a pinned playlist or artist | Play, Shuffle \| Unpin Playlist / Unpin Artist |
| Home: a pinned song | Play \| Unpin Song |

The album sheet's rows go to `pins_album_act` ([pins](pins.md)) on the Albums page, the Recently Added grid and Recently Played. `rowmenu_upnext_toast` formats the toast of any `upnext_add` status.

## Popup form

A navbar "..." opens a floating card under the button, as every page's "..." card does; a long press or a row's "..." opens the sheet ([ui-rules](ui-rules.md) "Item sheets"). `rowmenu_bind_popup(rm, win)` binds the popup widgets of `tools/pod_ui.py popup_menu()` (`rp_scrim`, `rp_card`, `rp_item0..4` with `rp_icon` / `rp_label`, `rp_hair0..1`; `RM_POPUP_ROWS` 5; no "..." bitmap) and `rowmenu_open_rows` opens it with the same tables, groups and acts. `rm_popup_fit` places it as `vs_fit` places the action-only view-sort card ([albums](albums.md) "View sort card"): 50 px rows, the 20 px glyph at `VS_TICK_X`, the 18 px label 28 px after it, as wide as the widest label plus `VS_TEXT_SLACK` and `VS_LABEL_R` (`VS_CARD_MIN`..`PL_CARD_MAX`), its right edge at `PL_CARD_RIGHT`, its top at `PL_CARD_Y`, in the glass `vs_glass<n>` (`patch3_x`); the rows, labels and hairlines take that width. User: the library album page (`ab.pop`).

## Design notes

- No widget per row: the "..." is a bitmap (`rm_make_dots`: the image `rm_dots` decoded by `cc_decode`, its red channel the coverage, `#8C8C8C`) drawn by `rowmenu_paint` from the page's row painter with
  the chevrons' crop to the list's view, and the zone is hit-tested in the page's `EVT_POINTER_DOWN/UP` handlers (`sg_in_zone`, `ab_in_zone`). The asset holds only the hidden, insensitive `rm_scrim`
  and `rm_card` (with `rm_item0..6`, `rm_icon0..6`, `rm_label0..6` and the hairlines `rm_hair0..1`, on the seven-row `pc_sheet7`) as the window's last two children (`pod_ui.row_menu`, after the sort card on the Songs page and the navbar on the album page).
- `rowmenu_t` lives in each page's state (`sg.rm`, `ab.rm`); the page text edge follows `rowmenu_on` and, on Songs, the rail (`sg_edge`). A list read again with the rail's presence changed drops its text tiles
  (`sg.tend`): their ellipses were cut for the other width.
- No Go to Album / Go to Artist. Removing a queued song is the Queue page's own sheet, above.
