# Songs

**Sources:** `patch/songs.c`, `patch/azlist.c` / `azlist.h` (sections, rail, pinned header),
`patch/songops.c`, `patch/filetime.c`, shared grid / cache / shuffle / scroll helpers,
`tools/pod_ui.py` (`build_songs_page`, `navbar(songs=True)`), `tools/pod_pages.py` (`SONGS`,
`ACT_SONGS`, `ACT_LIST`), `tools/mod_icons.py` (`SONGS_IMAGES`), `SG_*` in `offsets.inc`.

The menu's Songs action opens `ui/m1plus_songs.bin`. A failure falls back through `pod_home_open(3)`
to stock `allmusic_page` (class `0xf001`). No hook; the menu's kill-switch check keeps it closed
while disabled. The same page lists every other song list ([The other lists](#the-other-lists)).

Sections, pinned headers, the rail, the bubble and title fitting are the shared `patch/azlist.c`
(`az_t sg.al`). The Artists, Albums list and Radio countries pages use it too. Pills and selection
marks use `patch/common.c`, shared with Playlists.

## What the user sees

- **Navbar**: the glass navbar ([navbar](navbar.md)): Back, the small title from x 58, and one glass
  capsule **Search 168 | "..." 214 | Now Playing 260** (46 / 46 / 60 px).
  - Search (`btn_search`) is hidden on a genre's songs, a playlist's songs (no Search inside) and an
    artist's songs, where **Cover Flow** takes its place (168).
  - Where the card would hold Select alone (`sg_direct`: every list but the library and Recently
    Added) the "..." is a **Select button** (`btn_select`, `pod_nav_selectl` left cap) that enters
    select mode at once. Select mode hides both.
  - The small title runs to x 168 (110 px), a genre's and a playlist's to 214 (156 px). A title
    wider than its room is cut with an ellipsis, never hidden.
  - Glass is on the toolbar only; every other button of the page is flat.
- **Content** (one scrolling list): the large title (32 px white, x 12), the **Play and Shuffle
  pills** (flat `#1C1C1E`, pressed `#333335`, 129 x 40 at x 10 and 149, ending at x 278, short of
  the rail's touch column at 284), then the songs.
- **Title order (`sort_flag` 0): sections.** A 28 px header over each group: the letter alone,
  20 px white at x 10, no band and no hairline (the Recently Played shelf's header style).
  - Rows at a 64 px pitch: 52 px cover at (10, 4) with 4 px corners, title 21 px white at y 7,
    artist 18 px `#AAAAAA` at y 33, both from x 74, cut with an ellipsis at `az_end`, hairline x 74
    to the same x. No stars.
  - Each row ends with a grey "..." (24 px `#8C8C8C`, 44 px zone) that opens the Play Next / Play
    After / Add to Playlist menu ([rowmenu](rowmenu.md)). Text ends at x 269, or x 253 while the
    rail shows (the zone then sits left of the rail's touch column). Select mode has neither.
  - The pressed row is filled `#333333` (not when the press is in the "..." zone). A press held 500 ms opens the row's menu ([rowmenu](rowmenu.md) "Long press").
- **Any other order is a plain list** (no headers, no rail): File Name, Format, Recently Added.
  Title Z-A keeps its sections, mirrored.
- **Pinned header**: the section at the window's top stays under the navbar and the next header
  pushes it up. A header not wholly inside the window has no letter. The pinned copy has an opaque
  black fill (`SG_HDR_BG`, 28 px, window width), the only fill a header has.
- **The title collapses**: the small title shows once the offset reaches `SG_COLLAPSE` 46
  (`m1_title_gone`, from the scroll_view's `EVT_SCROLL`). Without scroll events the navbar keeps
  its title.
- **Z-A is the stock list reversed in place** (`sg_reverse`): after `loadLocalClassList(0xf001)` the
  records are swapped end for end, so index, rows, Select, Delete, Add to Playlist and a row's "..."
  all use the order shown. Title Z-A mirrors the section ranks (Z 0 .. A 25, `#` last). The play
  queue comes from `loadSongList` in stock order, so `so_play_dir(.., rev)` reverses it the same
  way. Shuffle is random, so order does not matter. After a restart the memory-playback record
  resumes in stock order.
- **Search** (`sg_on_search`): `search_open()` ([search](search.md)); the stock `search_page` when
  that will not open. The results' queries leave their list in `*pdeq_showlist`, which makes this
  page read it again when it is back. The button does nothing in select mode.
- **Playing**: a tap plays as the stock row handler does (`loadSongList` of the shown list, then
  `playing_page` at that row). **Play** starts the list from its first song in an in-order mode
  (`pod_set_in_order`: Shuffle and Repeat one become List play; a row tap keeps the mode).
  **Shuffle** is `shuffle_play(SHUFFLE_SONGS)` ([shuffle](shuffle.md)).

### The "..." card

The shared view-sort card ([albums](albums.md) "View sort card"). Each list offers only what stock's
navbar had (`sg_offers` passed to `vs_bind`; a row not offered is hidden and the card is packed in
the glass of its row count).

| List | Rows | Glass |
|---|---|---|
| Songs (library) | Select, hairline, Title, File Name, Format, Recently Added | `vs_glass5` |
| Recently Added, songs view | Select, hairline, Albums, Songs (ticked) | `vs_glass3` |
| Recently Added, albums view | Albums (ticked), Songs; Select goes (`vs_offer` repacks) | `vs_glass2` |
| a stock playlist | Edit, Clean Up, Pin Playlist ([playlists](playlists.md) "Rename Playlist", "Clean Up Playlist") | `vs_glass3` |
| Favorites, Recently Played, Most Played, Hi-Res, a genre, an artist, a server playlist | no card: the Select button | - |

**Select** is a Tabler `circle-check` glyph (`pod_ic_vsselect`); it works only with songs listed and
not in Recently Added's albums view. On a stock playlist the row is **Edit**: the same Select row
(`VS_SELECT`, relabelled and given the Lucide `pencil` glyph `pod_ic_vsrename` by `sg_edit_row`
when the card opens), which enters Edit mode (below). Albums / Songs switch to a newest-first Albums grid
([recent-albums](recent-albums.md)).

**Sort** (library only): **Title, File Name, Format, Recently Added** (`SONGS_SORT_KEYS`), a tick on
the current one with the direction line under it (`vs_dated`: only Recently Added reads Newest First
/ Oldest First). A row not ticked sets `sort_flag` 0, 1, 2 or 3 as the stock sort dialog does and
clears the direction file. **A tap on the ticked row reverses it**: Recently Added flips `sort_flag`
3 and 4; Title, File Name and Format flip A-Z / Z-A, saved first in `songs-sort-rev`
(`SONGS_SORT_FILE`: `a` Z-A, else A-Z; ignored while `sort_flag` is 3 or 4; a failed save changes
nothing). `sort_flag` stays 0..4, so stock and `config.ini` stay consistent. The card is fitted to
the widest label in each language.

### Select

The chrome, marks and bar are the shared module [selmode](selmode.md); this page keeps its own
nav buttons, sizes, rail and actions. The card's Select row: the navbar becomes the glass x
(cancel), "Select Items" from x 58 ("N Selected" once a row is marked) and the text button Select
All (all, or none when all are marked; it reads Deselect All while every row is marked). The bar's
pills are dim and dead until a row is marked, and a marked row has a faint white fill. Each row gets a 26 px mark in a 30 px column
left of the cover (cover and text move right by 30, text width 192); the pills dim. A 64 px bottom
bar holds one centred glass capsule (120 x 42) of two icon-only buttons, **Add to Playlist** (`list-plus`) and **Delete** (`trash`, glyph
`#FF6B6B`; [selmode](selmode.md)). The rail stays, centred on the 336 px the bar leaves; the content is 64 px longer. A tap
marks a row. Back (the x) leaves the mode.

## The A-Z rail

A widget of its own: x 284, 36 wide (`SG_RAIL_X`, `SG_RAIL_W`), as high as the drawn span plus 12 px
above and below (`SG_RAIL_PAD`), centred on the list, outside the `scroll_view`. `sg_rail_fit`
resizes it when the sections or select mode change, so the wide column takes no taps from the rows'
edge or from pills outside the span. The drawn column is centred on x 310 (`SG_RAIL_CX`).

The rail and bubble show only with Settings > Library > **Index Rail** on, the headers only with
**Section Headers** on (both default on, read when the page opens, `az_prefs`; [settings](settings.md)).

**Drawn plan** (`az_rail_plan`): items 13 px apart (`SG_RAIL_PITCH`), at most 20 (`SG_RAIL_ITEMS`),
letters 12 px `#EEEEEC` centred on x 310, the index centred vertically.

- With at most 20 sections every letter is drawn. Otherwise every k-th section's letter is drawn, k
  the smallest from 2 that fits, with one 4 px dot (`SG_RAIL_DOT`, `#8A8A8A`) between each pair.
  The first and last section are always drawn.
- 27 sections draw `# C F I L O R U X Z` (247 px, 76 px above and below on the 400 px list); 26
  draw `# C F I L O R U Y`; 21 draw `# C F I L O R T`; 10 or fewer draw every letter.
- Stock does the same thing: a sparse picture over a dense touch map (below). Ours uses 13 px items
  where stock uses about 15, so 27 sections take 247 px instead of 354.

**Touch.** A finger maps to every section, not only the drawn letters: the drawn span is split into
equal shares per section, so a drag visits every section in order and the bubble shows the real
letter. Above the span is the first section, below the last. A touch grabs (`widget_grab`) and every
position sets the scroll_view's `yoffset` to that section's header (clamped; a coasting list is
stopped first, `sc_down`). A section on a **drawn** letter gets a 16 px accent disc with a black
letter, and a **110 x 110 bubble** (`#262626`, radius 14, 56 px white letter, centred on the list,
insensitive). A section between two drawn letters has the bubble only. The rail is not a descendant
of the scroll_view, so a touch on it never reaches the stock drag code.

**The rail's footprint on the rows.** While the rail is shown every A-Z row gives up
`SG_RAIL_INSET` 26 px on its right (`az_inset`; `az_end` is the hairline end, `LIST_HAIR_END` less
the inset): chevron x 288 -> 262, text end 278 -> 252, the "..." zone's right edge 310 -> 284.
Plain lists and pages with the switch off keep the full width. One rule for Songs, Artists / Genres /
Composers, Radio countries and the Albums list. With `hdr_h` 0 there is no header band and a rail
jump lands on the section's first row.

### Alignment

Letters and dots share one centre line, taken from the font's own ink.

- **Vertical:** the cap ink of A..Z sits at rows 1..8 of the 12 px box, so `SG_RAIL_INK2` (twice the
  ink centre) is 10. A dot's top is `(INK2 - DOT) / 2` = 3 into its item (7 px of air above and
  below); the disc is centred on the ink.
- **Horizontal:** each letter gets a 24 px rect (`SG_RAIL_TEXT_W`) centred on x 310, moved by its
  own `SG_RAIL_DX[letter]` (0 or +1) so the **ink**, not the advance, is centred on the dots within
  0.5 px.
- Both are derived from the tree's own `default.ttf` by `pod_ui.rail_metrics`, which `tools/pod.py`
  writes into the generated `stock.h`, so a different font gives new numbers at the next build.
  The preview uses the same function.

### Sections

`az_sections` is the shared non-decreasing labelling ("#" 0, A..Z 1..26) that puts the most rows
under their own letter. A stray stays in the section around it and cannot open one early (a 'Y'
title between C and D does not swallow D..X). The list keeps its order (the play queue), there are
at most 27 sections, and no memory means a plain list.

### The Initial

Stock's section letter lives in `songtable` column 15 (`stSongInfo + 0x54`, `REC_INITIAL`), computed
at scan time from the title through `utf8_to_pinyin`: a digit gives `'*'`, a letter its upper case,
anything else `'#'`. The page's section letter is that byte folded to `A..Z` or `#` (digits and
symbols are one section); 0 (a database older than the column) takes the title's first character.

Stock's own order is the title comparator `0x5e0dac`: digits first, then ASCII letters and CJK (by
pinyin), then other non-ASCII, kana and CJK punctuation, Hangul, then symbol classes. So a
symbol-led title sits after Z and `az_sections` folds that tail into the last section. The rail
cannot reorder the list. The Albums Title order does not have this problem: it uses our name keys
([albums](albums.md)). A name's key and initial are in [artists](artists.md) "Order and the album
Artist rule".

### Stock's own index (the evidence)

The stock Songs page draws a collapsed index from the image `search_icon.png` (16 x 400): `* A . . F .
. K . . P . . U . . Z #`, a letter every five with two dots between. It is destroyed in select mode.
Its touch handler (only for `sort_flag` 0) maps y - 80 in 12 px bands to all 28 letters
(`getsidebarbyoffset`), scrolls to that row and shows `view_letter`. So the shape is sparse picture,
dense touch map, as ours.

## The other lists

The stock app shows every song list in one page, `allmusic_page`, with the class as context. Ours
does the same for Favorites, Recently Added, Recently Played, Most Played, Hi-Res, a playlist, a
genre, an artist and a composer. No hook.

| From | Call | Class | Title | Fallback |
|---|---|---|---|---|
| menu / Extras rows (`ACT_LIST`, arg = Home tile) | `songs_open_list(home)` (`SG_LISTS`) | `0xf00a`, `0xf009`, `0xf007`, `0xf008`, `0xf002` | the row's key | the tile's stock page |
| Playlists tap (`pl_open`) | `songs_open_playlist(id, name)` | `0xff13`, id in `classinfo[1]` | the name | the stock songs page |
| Genres tap (`ar_open`) | `songs_open_genre(name, unknown)` | `0xff09`, name at `classinfo + 0x30d`, Unknown byte at `+0xc` | the genre; no Search | the stock tap's sequence |
| Cover Flow's Songs button, the All albums card, the scoped Albums All Songs tile | `songs_open_artist(row, CLASS_ARTISTS)` | `0xff11`, the whole browsing record | the artist | the stock album page on the All songs row |
| the same on a composer | `songs_open_artist(row, CLASS_COMPOSERS)` | `0xff14` | the composer; grey line is the artist | the same |

`songs_artist_list(artist)` is the two stock queries without a page (also used for the albums
page's years). `songs_play_artist(artist, SO_IN_ORDER / SO_SHUFFLE)` plays that list as this page's
pills would.

Only one Songs page lives in `sg`. The exception is a playlist, or a source's row list, opened from
Search over a Songs page, and Add Songs over a playlist's page: `sg_stack` ends the page below's timers and cover build, moves its state
to the heap (`sg_under`) and starts `sg` empty; `sg_on_destroy` puts it back. The window manager can send the
page below its foreground event before that destroy, so the put-back also arms a 0 ms timer (`sg_on_put_back`) that
runs the fg handler unless it ran since. One level only.

What a list is:

- **Navbar**: see above. Titles are the large `sg_title` (`SG_TITLE_W` 296 px) and the small one,
  both cut with an ellipsis (`sg_fit`, at most `SG_NAME_MAX` 128 characters looked at; a playlist
  name is copied at most 255 bytes, cut before a character). A title is set as text, so a language
  change shows on the next open.
- **Order**: the query's own (Recently Played newest first, Most Played by plays, a playlist in
  insertion order). A list has no sections and no rail, whatever `sort_flag` says.
- **Most Played**: the grey line is `N plays · Artist` (N = `REC_TRACK` + 1), the count first so a long
  artist is what is cut. Keys `%d play` / `%d plays`.
- **Play, Shuffle**: `loadSongList(queue, name, cue, class)` with `g_class_type` and Now Playing's
  class = the list's class. For a playlist the page puts its id into `classinfo[1]` before every
  query and before `loadSongList`, because another page's query may have left another id. Shuffle on
  a list is that list in Shuffle mode from a random song (`pod_set_mode(MODE_SHUFFLE)`).
- **Select**: as on Songs. **Delete** is the stock dialog and `batch_delete_file(class, ...)`
  ([addresses](addresses.md) "Deleting by class"): Favorites lose the song from `myfav`, Most Played
  from `oftenplay`, Recently Played from `recentplay`, a playlist from the playlist, Hi-Res and
  Recently Added from the library. The file goes too when the dialog's second answer is taken.
  **Add to Playlist** opens the picker with `PICKER_ADD | class`.
- **Read again when back in front** (`sg_on_fg`) only for lists that change while behind another
  (`sg_changes`): Recently Played and Most Played (a play), Favorites (Now Playing's star), and
  after the picker. Every other list is read again only when another query replaced the stock list
  (`sg_valid`) or the page changed it. `sg_on_fg` always ends with `sg_kick` to restart the cover
  loader.
- **A list read again keeps its tiles** when it is the same rows (`sg_load`: count, cover key,
  section and a 24 bit hash of both text lines in `song_t.sig`). A play does not flash covers to
  placeholders.
- **Empty**: a list without a header keeps its large title with the grey line centred under it (`ls_room`): "No songs", the library's "Update Library first".

### A genre's songs

Class `0xff09`. The stock row tap sets `classinfo[0]`, copies the genre name into
`classinfo + 0x30d` and the Unknown byte (`+0xc`, row id -1) and opens `allmusic_page`;
`loadLocalClassList(0xff09)` reads that record. Ours is a list like the others. `sg_classinfo()` puts
the record back (`sg_genre_info`) **before every `sg_query()` and `loadSongList`**, because another
page's query may have changed it. `sg.pl_id` carries the Unknown byte. Delete and Add to Playlist use `0xff09` through the generic library path.
With Split Genres on, a split name's list is `gs_fill` (`sg.gsplit`), Delete and Add pass `0xf001` and a row plays an All Songs queue ([artists](artists.md#split-genres)). There is **no Search** (stock
leaves it out for `0xff09`): the capsule is Select | Now Playing, the small title runs to 214. A
window that will not open repeats the stock tap's sequence.

### An artist's songs and a composer's

The other view of Cover Flow's artist page, a toggle. The hidden `btn_coverflow` (x 168) is shown;
a tap runs `navigator_back`, so the covers page under it is the top again. Back closes the list and,
when the top window is then the artist's covers page (`coverflow_artist_page()`), that too. Select
mode's Back only leaves select mode.

The state is the whole 0x390 byte browsing record `CLASSINFO`. `songs_open_artist` builds it as the
stock artist page does: `loadAlbumList(0xf004, artist)` (the albums go to `*pdeq_showlist`, the All
songs row last, `REC_ID` -2), then `loadAlbumdetailList(0xff01, that row)` (class becomes `0xff11`),
then `loadLocalClassList(0xff11)`. The page copies the record into `sg.ci` and puts it back before
every `loadLocalClassList` and `loadSongList`. The title is the artist; a row's grey line is its
**album**. Delete and Add use `0xff11` through the generic songtable path.

A **composer's** songs are the same page on class `0xff14` (`sg_artist()` covers both): the composer
queries (`loadAlbumList(0xf005)`, `loadAlbumdetailList(0xff02, ...)`) build the record. The title is
the composer and the grey line stays the **artist**. `batch_add_file` sends every class it does not
name, `0xff14` included, to the generic path.

With Split Artists on, the artist's list is `as_fill` instead of the stock query
([artists](artists.md) "Split index").

## A playlist's header (class `0xff13`, `songs_open_playlist`)

A playlist opens on a header in the album page's and Daily Mix page's manner instead of the large
title ([album-page](album-page.md) "Layout", [dailymix](dailymix.md) "The page"): the playlist's
**2 x 2 mosaic** (a chosen cover of a local playlist, [plcover](plcover.md), instead; a source's never), its **name** centred, the album page's Shuffle disc and Play pill, then the rows.
Only here; other lists keep the large title and the two flat pills. The song count is the footer
only (Apple shows an "Updated" line there, which needs a change time we do not have).

| part | geometry (`patch/offsets.inc` `PH_*`) |
|---|---|
| mosaic | `PH_COVER` 160 px at x `PH_COVER_X` 80, y `PH_COVER_Y` 8; corners `PH_COVER_R` 10 |
| name | `sg_hname`, x `PH_NAME_X` 17, 286 wide, y `PH_NAME_Y` 182, 22 px white centred; a wider name takes a second line `sg_hname2` `AH_TITLE_LH` (26) px lower (`m1_wrap2`, the album page's title), line 2 cut with `...`, and the pills, the spinner, the rows and `PH_COLLAPSE` move down 26 px (`sg.tsh`) |
| disc and pill | `hd_shuffle` / `hd_play` 44 px at `AH_SHUF_X` 42 / `AH_PLAY_X` 96, drawn at y `PH_PILL_Y` 220, buttons at `PH_BTN_Y` 218; glyph `sg_glyph` is insensitive over the pill; text painted from hidden `sg_play_text` (18 px `#141414`, `m1_pill_place` / `m1_pill_paint`) |
| rows | from `PH_TOP` 272 (`PH_TOP - PH_EDIT_UP` 52 in Edit mode; `sg_top`) |
| collapse | the small title shows from `PH_COLLAPSE` 204 (`m1_title_gone(off, PH_COLLAPSE)`) |

**The mosaic is the Playlists page's code.** `grid_mosaic_keys` (`patch/grid.c`) picks the first
four distinct albums of the first `PL_SCAN` 50 songs that have a cache file (a song's own key, else
the library album's); `grid_mosaic` composes the tile ([playlists](playlists.md)). The header has its
own one-tile `grid_t` (`sg.hg`) and a quadrant buffer (`sg.htmp`, 25.6 KB). The loader (`sg_on_load`,
16 ms) makes the mosaic **first**, one cover a tick, only while the header is in view. The keys come
from the list just read, so no extra query. `sg_head_prep` remakes the tile only when the four keys
changed. In Edit mode it keeps the tile it has (a move, a remove or an add reads the list
again), and leaving Edit (`sg_select`, Done) checks the keys once. No tile ring or no `sg_hname` / `sg_hname2` in the asset gives the plain look. A tap on the header opens
nothing, and neither does the pinned band over scrolled rows (`az_pin_hit`). An empty playlist
without the Add Songs row says "No songs" and shows no header.

**An empty stock playlist's Add Songs row (`sg.addrow`, `sg_paint_add`).** A stock playlist
(`sg_cleans`) with no songs keeps its header (the placeholder mosaic, the name) and, in place of the
pills, the footer and "No songs", paints one row at `PH_TOP - PH_EDIT_UP` (`sg_top`): a `LIST_ART` px
`SG_ADD_TILE_RGB` (#2C2C2E) square with `LIST_R` corners (`m1_capsule`), the `sg_addnote` mask in
`SG_HANDLE_RGB` grey and the white `sg_addbadge` mask over it (`tools/mod_icons.py`
`add_tile_images`), and "Add Songs" in the title style centred on the row; its text is held by the
hidden `label_status`. No hairline. A press fills it `LIST_PRESS`; a tap (`sg_in_add`) opens the Add
Songs page as Edit's **+** does (`sg_add_songs`), in or out of Edit. Without the two masks the page
says "No songs" as before. A new playlist made on the Playlists page opens here
([playlists](playlists.md)).

**Two sets of buttons, one shown (`sg_pills`).** The asset carries the library's flat `btn_play` /
`btn_shuffle` and the header's `hd_shuffle` / `hd_play` + `sg_glyph`, built hidden and insensitive.
`sg_pills` shows one set and hides the other (visible 0 and sensitive 0: this AWTK's hit test ignores
`visible`): the flat pills without a header, the disc and pill with one, neither in Recently Added's
albums view. In select mode the shown set stays and goes insensitive. Both sets use the same Play /
Shuffle handlers.

**Edit mode (a stock playlist, `sg_edit`: select mode with a header and `sg_cleans`).** The card's
Edit row runs `sg_select(1)` (marks, Select All, "N Selected"), plus:

- The navbar's close disc shows a check (`ah_nav_done`, Lucide `check`, swapped in after
  `m1_sel_enter` sets the x); it leaves the mode like the x.
- `hd_shuffle`, `hd_play` and `sg_glyph` are hidden and insensitive (`sg_pills`), the Play pill text
  is not painted, and the rows start `PH_EDIT_UP` 52 higher (`sg_top`, with the pills' band gone;
  the scroll offset is clamped by `sg_select`).
- A tap on the name's band (`sg_in_name`, y `PH_NAME_Y` - 4 to the name's bottom + 4, full width)
  opens the rename keyboard (`sg_rename`; [playlists](playlists.md) "Rename Playlist"). `sg_pencil`
  places the hidden image `sg_hpencil` (16 px grey `#8E8E93`, `sg_pencil`) 8 px after the name's
  last line, centred on it, and shows it only in Edit. A rename reads the list again through
  `sg_edit_reload`, which keeps Edit mode and the marks.
- A round pencil badge (`sg_cbadge`, 28 px, `sg_cbadge_paint`) is painted over the header cover's lower
  right corner in Edit (it is painted, not a widget: the content paints after its children). A tap on the
  cover (`sg_in_cover`, `sg_cover`) opens the Cover page ([plcover](plcover.md) "Cover page");
  when this page is back in front `sg_head_prep` makes the header from the stored choice.
- The bottom bar shows Delete (red trash, left, `sg_edel`) and + (right, `sg_eplus`, 16 px glyph)
  instead of Add / Delete, which are hidden and insensitive (`sg_bar_edit`). Delete is dim until a
  row is marked and removes the marked songs from this playlist ([playlists](playlists.md)
  "Remove from Playlist"). After the confirm the list is read again and Edit stays on, with no
  marks, also when the playlist is left empty. + opens Add Songs (below).
- Edit is allowed on an empty playlist: no handles, Delete dim, + works.
- Every action commits at once; there is no save or cancel.

**Add Songs (Edit's +, the empty playlist's Add Songs row; `sg_pick`).** `sg_add_songs` collects the playlist's songs as two FNV words of
each path and CUE span (`sg_pk_hash`, `m1_fnv` over `REC_PATH` seeded with `REC_CUE_START` /
`REC_CUE_END`: a CUE image's tracks share one path, and stock's duplicate check compares the times
too; no strings are kept), then opens the library (`CLASS_ALL_SONGS`, the
same rows, sort and A-Z rail as `songs_open`) over the playlist page with `sg_open_page` and
`sg_pick_next`, stacked by `sg_stack`. A playlist page that is already over another page (reached
through Search) opens nothing. The page differs in these ways:

- The navbar has the check disc (`ah_nav_done`) where Back is and the title "Add to <name>"
  (`wk_subst` on the key, cut with an ellipsis to its room, `NAV_VIEW_X + NAV_VIEW_W`); the large title,
  Play / Shuffle, "...", Search, Cover Flow and Now Playing are hidden and insensitive; the rows start
  right under the navbar (`al.top` 0). The check closes the page.
- Each row's "..." is a 24 px mark in its place (`rowmenu_paint_bmp`): a white `circle-plus`
  (`sg_padd`) or, when the song (its path and CUE span) is in the playlist (`sg_pk_has`), a grey `#8E8E93` `circle-check`
  (`sg_pdone`); both baked in `tools/mod_icons.py` and made into bitmaps by `sg_make_bmp`.
- A tap on a row (`sg_pick_tap`) adds that song at once with the stock engine (`so_add_row`: the
  vector holds the row alone, `batch_add_file(class, CLASS_PLAYLISTS, list, vector, id)`, which
  appends and skips duplicates), turns the mark to the tick (the hash is added) and toasts
  `msg_addplaylistsuccess`. A ticked row does nothing, no tap opens Now Playing, a long press does
  nothing (`sg_more` is off, so no row sheet).
- On close `sg_on_destroy` restores the playlist page below and sets `reread`; its foreground handler
  reads the list again (`sg_edit_reload`: Edit if on, offset and, if the count is unchanged, the marks),
  so the new songs are at the end and an empty page's Add Songs row gives way to them.

**Reorder (Edit mode, `sg_handles`).** Every row has a handle at the right: the baked image `sg_handle`
(`tools/mod_icons.py` `handle_image`: three rounded bars 20 px wide, 6 px apart, in a 20 px square) made
into a bitmap by `sg_make_handle` (alpha = coverage, colour `SG_HANDLE_RGB` #8E8E93, as the rows' "...")
and blitted by `sg_handle_paint`, centred at x `SG_HANDLE_CX` 286 on the row. The touch zone is x
`SG_HANDLE_X` 262 .. 310; the row text ends at 262 (`sg_text_end`), the hairline still at
`LIST_HAIR_END`. Without the bitmap, or on a list with sections, there are no handles and no reorder.

- **Lift.** A press in the zone (`sg_on_down` → `sg_lift_start`) lifts that row at once, with no hold:
  the touch is grabbed at the list (`widget_grab(sv, view)`), the list's `yslidable` is turned off and
  `m1_lift_sv` (patch/scroll.c, shared with the Home pins' lift, [gestures](gestures.md)) names the
  list so the gesture hook clears `yslidable` again before each pointer event. A press elsewhere on the
  row is today's (marks the row). `sg_lift_end` gives all of it back on release, abort, select mode
  ending (`sg_select`), a list read again (`sg_load`), the window leaving the front and the page's end.
- **Drag.** The row is painted last (`sg_paint_float`) at the finger minus where on the row it was
  taken, on `SG_FLOAT_BG` (#242426), with its cover, texts, mark and handle; there is no shadow (the list
  is black around it). Its slot (`sg_lift_slot`: the row whose band holds the floating row's middle)
  is empty and the rows between close up one position (`sg_vrow`; the paint widens its row span by one).
- **Edge scroll.** A finger within `SG_EDGE` 40 px of the list's top, or of the select bar's top, starts
  a timer (`sg_edge_arm`, `SG_EDGE_MS` 30) that scrolls `SG_EDGE_STEP` 8 px per tick and recomputes the
  slot (`sg_on_edge`). It ends by itself at an end of the list or away from the edge (a move re-arms
  it) and is removed by `sg_lift_end`.
- **Drop** (`sg_lift_drop`, `sg_reorder`). The slot under the release point; if it changed, the rows
  of the range take their ids in the new order (`so_reorder_rows`, [playlists](playlists.md)
  "Reorder"), the marks move with their rows (`sg_move_marks`) and the list is read again with the
  offset, Edit and the marks (`sg_edit_reload`). A write that did not run toasts "Can't reorder
  playlist" and leaves the list as it was, the row back in its place. No change writes nothing.
- The lifted row's cover shows the placeholder if the auto-scroll took its tile out of the cover ring.

## The data

- **The stock list**: `loadLocalClassList(0xf001)` (`getAllMusic` into `*pdeq_showlist`, in the
  order of `sort_flag`), what `allmusic_page_init` runs. **The 20,000 songs of a big library are not
  copied**: the page keeps an 8 byte `song_t` per song (cover key and section letter) and reads title
  and artist from the stock list while painting.
- **The stock list is replaced by the next stock query** (another page's, Search's, `shuffle_play`'s).
  `sg_valid` is the list pointer, its size and its first record. A paint over an invalid list draws
  no row and arms a one-shot timer (`sg_on_stale`, 100 ms) that reads again **only if the page is on
  top**; a page behind another reads when its window comes back (`EVT_WINDOW_TO_FG`). A tap on rows
  that are not the page's plays nothing. The library's albums (`cc_albums`) are read first, once, for
  the cover lookup.
- **Sort order**: `sort_flag` (0 alphabetical, 1 file name, 2 format, 3 newest first, 4 oldest
  first) is persisted by the stock sort row handler as `write_int_config(.., "SYSSET", "SORTSELECT")`
  into `/mnt/data/config.ini`; the page does the same two writes. It affects class `0xf001` only,
  which is why sections and the rail exist only in order 0.
- **Covers**: per song the Cover Flow key `cc_album_key`, computed at open. A song whose own key has
  no cache file takes the library album's (`cc_cover_key`), looked up when its tile is made. The
  ring is the Albums list's (`GRID_TILES` 12 tiles of 52 px, one decode per 16 ms tick for the row
  nearest the middle, nothing while the scroll_view moves, paint never decodes). The **background
  build** ([covercache](covercache.md)) makes the covers missing for the songs within `SG_BUILD_N` 64
  of the first in view, one job per album, started 50 ms after open and when the page has scrolled
  `SG_BUILD_MOVE` 32 songs, polled every 500 ms.

## Select mode: stock delete and add

Stock's multi-select **Add to Playlist** and **Delete** are called with a selection made on OUR page
(pins: `SONGS_PINS` in `tools/pod.py`).

- **The selection** is the global vector `*0xa045e0` (`SEL_VEC`), indexed by the row of
  `*pdeq_showlist`, 1 = selected, tied to no page. Our page keeps marks in its own bitset and fills
  the stock vector **at the moment of the action** (`select_recordinit(count)`, then
  `set_selectindex(i)` per marked row, once the list is checked to be the stock one).
- **A stock playlist's trash** is not the stock delete (it would take each song out of every playlist
  and offer to delete the file): `sg_remove_marked` asks "Remove N song(s) from this playlist?" and
  removes the marked rows by their row ids ([playlists](playlists.md) "Remove from Playlist").
  Every other list keeps the stock delete below.
- **Delete**: nothing selected shows `msg_delsongfailed`; else `confirminfo_dialog` (kind 3, a
  checkbox "also delete the file"; returns 0xa library only, 0x14 with the file); then
  `batch_delete_file(class, *pdeq_showlist, vector, 0, delete_file)`: per marked row
  `deleteMusicFromMusicDb`, and `remove_file` when flagged; the "library changed" flag is set; then
  `msg_delsongsuccess`. It touches no widget and does not remove rows from the deque. The page then
  ends select mode and reads again. It runs on the UI thread (a database open per song and `sync`),
  so a big multi-delete blocks, as in stock.
- **Add to Playlist**: our own picker ([picker](picker.md)) with `PICKER_ADD | class`; where ours
  cannot open, the stock picker with the stock vector filled. `batch_add_file` takes the generic
  path for the library class (rows of type 8; duplicates skipped; it writes new ids into the source
  records in place). The picker sets the browsing class to `0xf00b` and never puts it back, so the
  page saves `nagvation_title`, and on return restores it, sets the class back, ends select mode and
  reads the list again. The Favorites path of the stock dialog is not offered.
- The stock Songs page in select mode is started only by its own button handler.

## The page (`patch/songs.c`)

- **Widgets**: the navbar (`label_title` hidden, `btn_return`, `btn_more`, hidden `btn_coverflow`,
  `btn_backtoplayer`, hidden `btn_selall`), `songs_listview` > `songs_scrollview` (310 wide) >
  `view_grid` holding `sg_title`, `btn_play`, `btn_shuffle` and the playlist header's widgets, the
  stock `scroll_bar_m` (required: it makes the scroll_view slidable, [albums](albums.md)),
  `img_nb_fade`, hidden style labels, `label_status`, then `sg_rail`, `sg_bubble`, `sg_bar`, the
  shared card `vs_scrim` / `vs_card`, and last the rows' menu `rm_scrim` / `rm_card`
  ([rowmenu](rowmenu.md)). Everything shown later starts hidden and insensitive. No stock widget is
  renamed.
- **The pills** are buttons with the style's `bg_color`, `round_radius` 20 and the glyph as the
  style's `icon`. `sg_centre_pill` centres glyph + 8 px + the measured translated text in every
  language. A label wider than the 93 px beside the glyph steps down to `SG_PILL_PX_SMALL` 16 px
  (only Russian "Перемешать").
- **Row paint** (`sg_on_paint`, the content view's `EVT_AFTER_PAINT`): header bands, then each row's
  press fill, mark, cover and hairline, titles and artists in one text pass each, header letters,
  and last the pinned band. Geometry helpers work on at most 28 section starts, so a paint never
  walks the list. Text room comes from `sg_text_end` (`sg_edge` 262 / 236, 296 in select mode).
- **Size**: the content is `SG_TOP` 104 + sections x 28 + songs x 64 (+ 64 in select mode):
  1,281,000 px for 20,000 songs; `widget_resize` and `virtual_h` get the same 32 bit number.
- Texts are in `tools/pod_i18n.py`; all 13 languages fit the pill, card and select title.

## The song count

Under the last row of every list: **"25 songs"** ("1 song"; keys `%d song` / `%d songs`; pl, ru, uk
use a label form). A label `sg_foot` (15 px `#9C9C9C`, x `SG_HDR_X` 10), `SG_FOOT_GAP` 14 below the
last row; the content is `SG_FOOT_H` 52 longer. `sg_foot_text` updates it at every read. No
duration: the song table has none.

## Recently Added dates (`patch/filetime.c`, payload hook 19)

Recently Added orders by `songtable.time_create`, which the library scan takes from stock's
`toolsGetFileCreateTime` (`0x5e4ac8`). Stock returns `st_ctime` (the creation time on FAT) but
`st_atime` when the filesystem byte `0xa0ac7c` says exFAT or NTFS, where `stat` has no creation
time. Reads move the access time, so on an exFAT card a rescan dated the whole library to the update
day.

- `ft_created` replaces the function's prologue. It calls `statx(AT_FDCWD, path, 0, STATX_BTIME)`
  through the o32 syscall (4366; demo imports no `statx`) and returns `stx_btime.tv_sec`, which reads
  never move. A copy gets the time of the copy on Windows and Linux; a Mac keeps the file's date.
- Stock's function runs (through `stock_file_created_trampoline`) for a null path, with
  `/mnt/mmc/m1plus-off`, when the call fails, when the mask lacks `STATX_BTIME`, or when the stamp is
  0. FAT32 is unchanged in effect. Cost: one `access` and one `statx` per file, 256 bytes of stack.
- Existing dates change only after a rescan: Update Library rebuilds the table, so the first full
  update re-dates the library by creation stamp.

## A library source (`songs_open_src`)

`songs_open_src(src, which, title)` (`LS_SONGS`, `LS_FAVORITES`, `LS_DOWNLOADED`; `patch/libsrc.h`)
opens this page on a non-stock source. The list is `src->list(which, NULL)`, kept as the page's own
copy (`sg.list`); class `0xf001` with `sg.src` set, so no stock-library path (sort card,
`*pdeq_showlist`, cover build, delete, add) applies.

- Taps, Play and Shuffle go through `so_play_src`; covers through `src->cover` (0 = asked: the
  shared cover poll, [subsonic](subsonic.md) "Shared source-page helpers").
- A `LS_GEN_MS` 500 ms timer reads `src->gen` and re-reads the list (scroll position and tiles of
  unchanged leading rows kept) when it moved and the page is on top and idle.
- `lib_src_t.complete` NULL or 1: sectioned with the rail; 0 (paged): plain rows, no rail. The "N
  songs" footer is hidden while a paged list is growing.
- `LS_DOWNLOADED` with `dl_rows`: rows still to download form a "Downloading" section with a Clear
  text button above "Downloaded" ([subsonic](subsonic.md) "Downloads";
  named headers are `az_t.sec_text` / `sec_act`).
- **A source's pages are the local classes** (`sg_playlist`, `sg_artist_songs`,
  `songs_open_src_in`): a source playlist gets the local playlist header and no Search; a source
  artist's All Songs is the artist's songs (grey line the album, no sections or rail, no Search).
- `src` NULL or `&lib_stock` is `songs_open()` (Songs), `songs_open_list(HOME_FAV)` (Favorites), -1
  (Downloaded).
- **Controls follow the source**: `ls_caps(src)` (NULL has all) decides Search (`LS_CAP_SEARCH`) and
  Select (`LS_CAP_SELECT`). A source without Select has no "..." or Select button; one without any
  has no button, the title runs to Now Playing (x 260) and Now Playing becomes the plain disc
  `ah_nav_np`. `lib_nd` has `LS_CAP_SEARCH` only, so its Songs, Favorites and Downloaded lists have no
  Select or "..."; Search shows only with a saved server ([subsonic](subsonic.md)).
