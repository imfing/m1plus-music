# Albums

**Sources:** `patch/albums.c`, `patch/grid.c`, `patch/covercache.c`,
`tools/pod_ui.py`. **Tests:** `test/pod/albums.py`, `test/coverflow.py`.
Previews: the Albums panels in `tools/preview_icons.py`.

Albums opens a grid or list in the last selected mode. Tapping an album calls
`cc_open_album`; Back returns to the same position. Cover Flow opens above this page.
If the window cannot open, the Home dispatcher opens stock Albums.

Scoped to an artist or composer: a tap on a row of the Artists page (`albums_open_artist(list, row, scope)`)
opens the same window and mode on that artist's albums. The page holds a copy of the artist's row and the album list
and cache keys from `coverflow_artist_albums` (`patch/coverflow.c`: `loadAlbumList(0xf004 / 0xf005, artist)`, each album
keyed like the library album of the same name, the case-insensitive index from 24 albums; shared with Cover Flow's
scoped page). The stock trailing "All songs" row (id -2) is kept as the last tile with two albums or more (dropped with one):
same tile size, the cards' placeholder disc (key 0: no cache file, never scanned or built), "All Songs" (stock key
`local_allsong`) over the artist's name. Its tap opens our Songs page on every song of the artist (`songs_open_artist`;
the stock page on the All songs row if it will not open, and for a composer, which has no songs page, as Cover Flow's card). The title is the name, fitted with an ellipsis; an empty
list says "No albums". An album tap is `cc_open_album(row, scope, index)`: class `0xff01` / `0xff02`. The Cover Flow
button opens Cover Flow scoped to the same artist (`coverflow_artist`) above the page; Back returns here, then to
the Artists page. The mode file is shared with Home > Albums, toggling writes it, and Cover Flow is never stored.
The cache scan uses the scoped keys (`cc_build_near_step`'s `keys`; it skips the All songs row). The deque, list and keys are freed on destroy.
If the window cannot open the caller opens Cover Flow on the artist.

## Layout and state

| Element | Contract |
|---|---|
| Window | `ui/m1plus_albums.bin`; 320 × 450 px with a 50 px navbar |
| Scrolling | `albums_listview` > `albums_scrollview` > `view_grid`, plus `scroll_bar_m` |
| Grid | Two 144 px covers, 12 px margins, 8 px column gap; 190 px cells on a 200 px pitch |
| Grid text | Album 18 px white, artist 15 px grey; one ellipsized line each |
| List | 64 px rows, 52 px covers at (10, 6) (6 px above, 5 + the 1 px hairline below), text from x 74 (title y 9, artist y 35) to x 278 (`LIST_TEXT_W_CHEV`); title 21 px, artist 18 px; the hairline runs from the text to x 310 (`LIST_HAIR_END`, Apple's inset) and the grey chevron (`pod_make_chevron`, 10 x 16, x 288 `LIST_CHEV_X`, centred above the hairline) marks that a row opens a page (the artist-scoped page and its All Songs row too) |
| Corners | Grid 8 px blended into black; list 4 px in the bitmap alpha |
| Navbar | Back, title, Cover Flow at x 168, view toggle at x 214, Now Playing at x 260 |
| Mode file | `/mnt/data/m1plus/albums-view`: 1 grid, 0 list; otherwise `ALBUMS_DEFAULT_GRID` |

The stock mobile scrollbar is required: the list-view layouter enables vertical scrolling
through it (`0x60b1c8..0x60b1e8`). The content view and `virtual_h` both hold the full
content height as 32-bit integers. Empty content is hidden and insensitive.

The toggle stops a running scroll animation, drops tiles, changes geometry and preserves
the first visible album. It updates the glyph to the other mode and writes the choice with
`home_write_atomic`. Missing required style labels or content widgets close the page.

## Covers and painting

The shared grid supplies tile records, rounded artwork, ellipsis fitting, painting and hit
testing. Recently Played uses the same helpers. Covers come from
`r<album-key>-168.jpg`, reduced by an area average of the centered square.
An absent file or empty “no art” marker uses the placeholder disc.
A `.bad` marker (an album whose extraction hung, `docs/modules/coverflow.md`) also keeps it out of the missing set.

Twelve resident tiles cover visible cells, prefetch and recent history. Grid artwork uses
about 1.1 MB including the placeholder; list artwork about 130 KB for the ring. The copied
album list adds about 0.3 KB per album. A decode temporarily holds the 168 px source.

Paint draws resident covers and text only: no image decoding, bitmap allocation or timer
creation. Text is measured and ellipsized once per tile. Drawing is limited to the 400 px
viewport; partial text lines are omitted. The stock scroll view clips the canvas.

The 16 ms loader decodes at most one cover per tick, prioritizing visible cells nearest the
viewport center, then one grid row or two list rows ahead in the scroll direction.
Visible tiles are retained; other tiles use LRU replacement. Decoding pauses during a stock
drag or running scroll animation (`grid_moving`) and resumes when it ends.
Backgrounding stops the loader; foregrounding restarts missing work.
If scroll events cannot be registered, the loader polls while the page is open.

## Cache building

The shared `cc_build_*` worker builds missing cache files without blocking page open.
A 50 ms startup timer scans in batches of 64 albums, 20 ms apart, nearest the initial
viewport first. The worker starts after the scan finishes; scrolling does not reorder it.
A 500 ms poll makes placeholder tiles eligible for reload as files arrive.

Only one page owns the worker. Opening Cover Flow releases the Albums build first.
Destroy stops owned work and removes timers. `cc_build_stop` never waits for the thread: a worker
that has exited is joined and its set freed; one still inside a job (stock's art call cannot be
interrupted, and can be slow) is cancelled and orphaned, keeps the set and is joined and freed by the next
`cc_build_open` / `cc_build_busy` / `cc_build_orphan` after it exits. Meanwhile `cc_build_open` refuses and
`cc_build_busy` is true; the Albums and Songs start timers ask again every 500 ms while `cc_build_orphan` (true for 10 s after the orphaning, then they stop until the next foreground or open).
A refused timer/thread, busy worker or less than 16 MB free space leaves placeholders.
A completed scan with no missing files is not repeated during that page's lifetime.

## Input and validation

The stock scroll view owns drag, fling and end stops; [list gestures](gestures.md) handles
coasting catches. Page listeners return without consuming events. A release on the original
cell within 10 px on both axes opens the album. Drag, abort, backgrounding or a touch that
stops coasting clears the press and opens nothing. List presses use `#333334` (`LIST_PRESS`, the pressed-row role colour).

Tests cover both modes, real stock layout and pointer handlers, large-library content
heights, tile bounds, loader deferral, cache-worker ownership, persistence and failure paths.
Real frame timing and canvas/text appearance require [device checks](device-checks.md).
See [album page](album-page.md) for album opening, [Cover Flow](coverflow.md) for the shared
cache worker and [rows](rows.md) for common library styling.
