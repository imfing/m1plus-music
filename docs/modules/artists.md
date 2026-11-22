# Artists

**Sources:** `patch/artists.c` (the page), `patch/artsplit.c` (split index), `patch/genresplit.c` (genre split), `patch/artistphoto.c`
(photos), `cc_build_add_artist` in `patch/covercache.c`, the artist stage of `hc_on_start` in
`patch/homecover.c`, `tools/pod_ui.py` `build_artists_page`.

Our Artists page, with Genres and Composers on the same code. No hook; if the window will not open
the Home dispatcher opens the tile's stock `localclass_page`.

## Genres and Composers are the same page

`ACT_ARTISTS` with the row's Home tile as argument: `artists_open(0)` Artists, `HOME_GENRE` 7,
`HOME_COMPOSER` 8. `ar.cls` is the stock class listed: `0xf004`, `0xf006` `getAllGenre`, `0xf005`
`getAllComposer`.

- Rows, copy and the empty line ("Update Library first") are shared. The title is the menu row's
  text.
- The "..." card has Name alone: no Search row (`search_open_in` has no genre or composer scope) and
  no Show group.
- The `ar_sort` name keys are **not** applied. A-Z is stock's own order (sort 1 with comparator
  `0x5e0dac`; the "Unknown Genre / Composer" row, id -1, last) and Z-A is that reversed with the
  Unknown row still last.
- A **genre's tap** is `songs_open_genre(name, unknown)` ([songs](songs.md) "A genre's songs"). A
  **composer's tap** is `albums_open_artist(list, row, CLASS_COMPOSERS)`: the Albums page scoped
  exactly as an artist's, with `loadAlbumList(0xf005, row)` and `albuminfo_page` class `0xff02`.

## The page

The Songs page's structure ([songs](songs.md); shared furniture below). `ui/m1plus_artists.bin`: the
navbar (Back, small title, "..." `btn_more` as the capsule's left cap at x 214, Now Playing), the
"..." card, a stock `artists_listview` > `artists_scrollview` (310 wide) with **one content view**
that paints the rows, section letters and pinned header itself, the large title `ar_title`, and the
rail `sg_rail` and bubble `sg_bubble`. No widget per artist, so `MAX_ARTISTS` is 20,000.

- **Large title and collapse**: the large title is first in the content (`AR_TOP` = `SG_TITLE_H`
  52 px). The small title (156 px before the "...") shows from `SG_COLLAPSE` 46 (`m1_title_gone`).
  Both are cut with an ellipsis (`az_fit`); of the 13 languages only "Album Artists" is cut (ja, pl,
  ru, uk).
- **Rows** (`AR_ROW` 52): name 21 px white (`AR_TEXT_Y` 14), cut at x 252 (`AR_TEXT_END`),
  chevron at x 262 (`AR_CHEV_X`, 10 x 16, grey bitmap the page makes at open), `#222222` hairline to
  x 296, pressed row `#333333`. No playing marker.
  - **Artists and Album Artists** (`ar.photo`): a 40 px circle (`AR_PHOTO` = `AP_ROW_D`) at x 16, the
    name and hairline from x 68. **Genres and Composers** have no circle and keep name and hairline
    at x 24. The circle is the ring tile's bitmap ([Showing the photos](#showing-the-photos)).
  - A tap (within `SC_DRAG_PX` on the same row) calls `ar_open`: `albums_open_artist(list,
    ar_stock(i), scope)` for an artist or composer (`coverflow_artist` if that returns -1),
    `songs_open_genre` for a genre. The title block, headers (the pinned band too, `az_pin_hit`) and
    the air under the last row open nothing. The last 36 px (x 284) belong to the rail.
- **Sections**: `ar_sections` gives each display position the rank of `cc_name_initial(name)` (the
  first byte of the text the sort compares: white space and a leading "The " dropped, a CJK
  character its pinyin initial, a kana its romaji initial, an accented Latin letter its base
  letter), then `az_rank_of` (A..Z; digits, symbols and scripts with no initial are "#") and
  `az_sections` ([songs](songs.md) "Sections").
  - Artists are sorted by `ar_sort` so they are in letter order but for "Unknown Artist" and
    "#" names. Genres and Composers keep the stock order and take the same labelling.
  - **Name Z-A** (`ar.rev`) reverses all three. Unknown rows keep their stock (last) positions and
    ranks are mirrored (Z 0 .. A 25, "#" 26), so headers and rail run Z to A with "#" last.
  - **The "Unknown ..." row (id -1) takes the rank of the row before it.** As the last row of a run
    of one-row sections it could otherwise swallow the section of the row before it.
  - The rail is always there while there are sections; with no memory the list has none.

### Order and the album Artist rule

The order is the album Artist order's name rule, applied by `ar_sort`. Stock sorts in memory
(`toolsQueryDbTable`, comparator `0x5e0dac`): digit runs as numbers, `strcasecmp`, digits and symbols
before letters, a CJK name through `utf8_to_pinyin`.

`cc_name_keys` (`patch/covercache.c`) makes one key per name once per sort:

- The name without leading white space and a leading "The ".
- Each CJK character becomes its pinyin initial (stock's `utf8_to_pinyin` on that character).
- Each kana becomes its Hepburn initial (`kc_kana`; katakana is hiragana + 0x60; し S, ち C, つ T,
  ふ F, じ ぢ J, づ Z, を O, ヴ V; a small kana by its row; ー and the iteration marks none), so ヨルシカ
  files under Y.
- Each accented Latin letter U+00C0..U+017F becomes its lower-case base letter (`kc_latin`; × ÷ stay
  symbols; ß s, æ œ ø ð þ ł đ ı by hand), so Ólafur Arnalds files under O and Éric ties with Eric on
  "eric" (stock order).

`cc_key_cmp` then compares keys: digit runs by value (leading zeros ignored), then per byte digits
before symbols (every non-ASCII byte is one) before letters, ASCII case folded; a prefix first; ties
by stock position (`cc_heapsort`, no libc callback). Stock's second key for equal initials (the full
pinyin) is not reproduced. `cc_name_cmp` (Radio, podcast and country lists, which have no keys pass)
takes the same class rule.

`ar.order[]` (stock row at each display position) is built over the copy, so no stock row moves.
Every row but "Unknown Artist" (id -1) is sorted as one set; Unknown rows keep their stock
positions. A failed allocation leaves `order` NULL (stock order). `ar_stock` maps a display
position to the stock row handed to `coverflow_artist`. The sort re-runs at every `ar_load`. Our
sort is a small fraction of stock's own, which always runs first.

### The "..." card

`btn_more`, `ar_on_more`, the shared `patch/viewsort.c` ([albums](albums.md) "View sort card").

- **Artists**: `Search Artists` (closes the card, `search_open_in(SEARCH_ARTISTS)`, the library
  search if that returns -1), the **Show** group `Artists` / `Album Artists` (glyphs
  `pod_ic_vsartist`, `pod_ic_vsalbumartist`; the tick follows `artist_type`) and the **Name** sort
  with its grey line A-Z / Z-A: four rows, `vs_glass4`.
- **Genres and Composers**: Name alone, `vs_glass1`, no hairline.
- A tap on the ticked Name row reverses the order, saved first (`home_write_atomic`; a failed save
  changes nothing), then the list is built again from the top.
- The Show rows do what the stock switch handler does (`ar_set_type`): set `artist_type`, write
  `PLAYSET/ARTISTTYPE`, set the stock page's reload flag; then the list is queried and rebuilt. The
  stock toast and style swap are skipped.
- **Order files** (`/mnt/data/m1plus/`): `artists-sort`, `genres-sort`, `composers-sort`; one
  character, `a` Name Z-A, anything else A-Z; read once at open ([settings](settings.md)).
- **No count sorts**: stock rows are one representative song each, carry no counts, and a counts
  query would need its own statement, callback and the podcast filter.

Statics are prefixed `ar_`. Memory: the copy of the stock rows, `order` 4 bytes, `rank` 1 byte and
(Artists) the photo state 2 bits per artist, the 13 text tiles (6.4 KB each with circles), the
placeholder, the rail disc and chevron, all freed with the window. A tile ring that cannot be made
closes the page.

### Long press

On the library's Artists and Album Artists page (not a source, Genres or Composers) a row held `RM_LONG_MS` opens the three-row sheet Play / Shuffle / Pin Artist (Unpin Artist when pinned) (`ar_on_hold`, `ar_sheet`, `ar_pin_rec`: not the Unknown Artist row); the release opens nothing. Play and Shuffle are `songs_play_artist`. `artists_find(name)` is the one-row deque for a name as the page lists it (the split's first name, else the stock row), shared with Look up artist and the Home pins ([pins](pins.md)).

## Shared furniture, `patch/azlist.c`

Moved out of `patch/songs.c`. The Songs page owns the design ([songs](songs.md) "The A-Z rail").

- `az_sections` (the labelling), the geometry of a list with headers (`az_hdr_y`, `az_row_y`,
  `az_row_from`, `az_at`, `az_span`, `az_max_scroll`), `az_paint_heads`, the rail (`az_rail_*`) and
  `az_fit` (a title cut with an ellipsis).
- A page owns an `az_t` (`sg.al`, `ar.al`, the Albums list's `al.az`, Radio countries) and fills the
  fields its comment marks `(page)`: widgets, the three label styles, the top of the first header,
  row height and count, content height. `tools/pod_ui.py` shares the asset side (`azlist_labels`,
  `azlist_rail`).
- **The two switches** (Settings > Library): `az_prefs` reads `appearance-index-rail` (Index Rail,
  on unless the file is `0`) and `appearance-headers` (Section Headers, on unless `0`). Rail off:
  none drawn or touchable, rows keep the full list-row width (chevron 288, text to 278, hairline to
  310). Headers off: `hdr_h` 0 and no header band. Each page reads them once at open.

## A tap opens the Albums page scoped to the artist

`albums_open_artist` (`patch/albums.c`, [albums](albums.md) "Scoped to an artist"): the page in the
last chosen grid or list mode, the artist's name as title, their albums and, with two or more, the
All Songs tile last (our Songs page on every song). Its Cover Flow button calls
`coverflow_artist(list, index, scope)` for the same artist (`CLASS_ARTISTS`, or `CLASS_COMPOSERS`:
`cf.scope`, which also decides whether the album page opens as `0xff01` or `0xff02`). The artist's
albums follow the one album order `albums-sort` (the card without the Artist row; Artist is shown as
Title), and so does the scoped Cover Flow. Everything below holds for a composer with `0xf005` and
`0xff02`.

- **Albums**: `loadAlbumList(0xf004, artist)`, copied into the page's deque with the artist's row.
- **All albums card**: the stock list's last "All songs" row is kept with two albums or more
  (caption "All albums" over the artist, placeholder art, no cache file) and dropped with one.
- **Covers**: each album takes the cache key of the library album of the same name, so the page
  shows the main page's files and builds only covers the library lacks. Below `IDX_MIN` 24 albums the
  match is a scan per album (first library row of a name wins); from 24 up `load_artist` builds a
  temporary case-insensitive hash index of the library's album names (FNV-1a over ASCII-folded
  bytes, first row wins) and frees it after. A refused allocation falls back to the scan. Below 24
  the index costs more than the scans it saves.
- **The album**: `loadAlbumList(0xf004, artist)`, `albumcoverinfo_init`,
  `batchadd_albumcover_task(0, 0)`, then our album page, else `navigator_to_with_context(
  "albuminfo_page", 0xff01 | row << 16)`, the context stock's artist page builds. The page runs
  `loadAlbumdetailList(0xff01, row)` itself and leaves class `0xff11`.
- **Songs button** `btn_songs` (the left cap of Songs | Now Playing at 214) and the All albums card
  open our Songs page on the artist's songs (`songs_open_artist`).
- **Ends**: the scoped shelf does not wrap (the main page does). The scope never reads or writes
  `coverflow-position`. "No albums" when empty. Back goes covers -> Albums page -> Artists -> menu.
  The stock list always ends with "Unknown Artist" (id -1), which opens to "No albums" without
  untagged songs. A second open while Cover Flow is open is refused.

The artist page uses the stock page's list and All songs row, so no hook is needed.

## Artist photos

Photos for the local library. The source is a picture the user puts beside the music (found
automatically), or one picked online for one artist: **Find Artist Photo** on the artist's page
(`ap_pick`, [onlineart](onlineart.md) "Artist photos"; never automatic).

A library source's Artists and artist pages ([subsonic](subsonic.md)) never look for a photo file of
the library. Their picture is the file `src->cover` names for the artist record (Subsonic: the
server's artist image in its own cover folder). A row with it decodes into the same 40 px circle
(`ar_src_row`; a portrait file is cut from its top third, as `pv_square` cuts the library's). While
it is fetched the circle is the placeholder with the cover spinner; with none it is the placeholder.

### Discovery (worker, per artist)

For each album of the artist, from its first track's folder `D` (a disc folder `CD1`, `Disc 1`,
`disc-03`... is stepped up once, so `A` = the album folder, `P` = its parent), in order:

1. `P/artist.jpg|jpeg|png`, 2. `A/artist.jpg|jpeg|png`, 3. `P/folder.jpg|jpeg|png` (never in `A`: that
is the album cover).

Each tier is tried over all the artist's albums before the next. **Every matching file of a folder
is tried** before the next folder or tier, so a corrupt `artist.jpg` does not hide a valid
`artist.png`. Names match in any case; regular files only; a JPEG over 6 MiB or a PNG over 1 MiB, or
one that does not decode, is passed over.

- **Purity**: a folder counts only when every album the library has under it (itself and below;
  "Abba - Live" is not under "Abba") is by that artist. This rejects `Various Artists/`, `Rock/`,
  `Music/` and flat many-artist folders.
- An **album with no artist** (blank or "Unknown Artist") has key 0, which conflicts with every
  real key: a folder holding one is nobody's (an `artist.jpg` in an album folder of its own still
  works).
- Tier 3 also needs the folder's name to give the artist's key.

### Separators

One artist field can name several artists. `m1_artist_split(field, out, max, opts)`
(`patch/common.c`) returns them in order as spans into the caller's string. `opts` is a bitmask
(`M1_SPLIT_SEMICOLON`, `_SLASH`, `_AMPERSAND`, `_COMMA`, `_FEAT`, `_VS`, `_X`, `_PLUS`, `_WITH`,
`_AND`; NULL = `M1_SPLIT_DEFAULT`: semicolon, slash, ampersand, feat) plus names that never split;
a separator whose bit is off is plain text.

| Kind | Rule |
|---|---|
| Symbols `;` `/` `&` `,` `+` | split with or without spaces; full-width and CJK forms `；` `／` `＆` `，` `、` `＋` are the same; `×` belongs to `_X` |
| Words | need a space or an opening bracket before and a space after |
| `feat`, `ft`, `featuring`, `vs`, `versus` | ASCII case folded, may end in a full stop |
| `x` | lower case only, so `Malcolm X` stays whole |
| `with`, `and` | case folded |
| inside `()` / `[]` | only feat/ft/featuring/vs/versus split; a symbol splits there only after one of those in the same brackets: `A (feat. B & C)` is A, B, C; `A (B & C)` is one name |
| each part | trimmed of spaces and of brackets a cut leaves unmatched; matched brackets stay (`A (Live)`); empty parts and repeats dropped; at most `max` names |
| exceptions | `m1_split_opts.except` (NULL-terminated, ASCII case-insensitive, never split wherever they occur); `m1_artist_split_exceptions()`: `AC/DC`, `Simon & Garfunkel`, `Earth, Wind & Fire`, `Crosby, Stills, Nash & Young`, `Hall & Oates`, `Florence + the Machine`, `Tyler, the Creator` |

`ap_lead` is the first name, through its own mask (semicolon, slash, ampersand, comma, feat, x) and
the built-in exceptions. It is none for a field with one name, an exception name, or one starting
with a separator. The photo fallback and every later consumer read this one rule.

### Split index

`patch/artsplit.c`; Artists mode only (not Album Artists, Genres, Composers or Navidrome). **Off by
default, and then no line of it runs**: the page reads the stock `loadLocalClassList(0xf004)` and an
artist's albums and songs are the stock queries.

The setting is `/mnt/data/m1plus/library-artist-split` (`AS_FILE`, read at each build; Settings >
Library > Split Artists, [settings](settings.md)): missing, `0` or unrecognised off; `1` on with
`M1_SPLIT_DEFAULT`; `m<decimal>` on with that mask (`m0` splits nothing); `o<decimal>` off but keeps
the mask for the page. Extra never-split names come from the card file `/mnt/mmc/artist-exceptions.txt`
(`AS_EXCEPTIONS`): one name per line, trimmed, `#` lines and blanks skipped, at most 64 names and the
first 4096 bytes, read once per build or tap.

- **Rows** (`as_rows`): one pass over `cc_songs()`; each `REC_ARTIST` is split (at most 8 names a
  field) and names are merged ASCII case-insensitively in a hash table (linear in the songs).
  **The first spelling seen** is the row's name. A blank field or one that splits to nothing is the
  "Unknown Artist" row (id -1, last). Rows are page-owned records (`REC_ID` 1.., type 4, **`REC_CLASS`
  = `AS_MARK`** `0x41535031`, which stock rows leave 0: `as_is_row`), up to `MAX_ARTISTS` names.
  `ar_sort`, sections, rail, Z-A, photos and the card work on them as on stock rows. Without songs or
  memory the page falls back to the stock query.
- **An artist's albums** (`as_albums`, reached through `coverflow_artist_albums`, so the Albums page,
  Cover Flow and the All Songs tile all use it): library album rows whose album name is the album of
  one of the artist's songs, then the All Songs record (`REC_ID` -2, key 0) **always last**. It
  counts as a tile only with 2+ albums or with none (an artist whose songs have no album tag). A
  song with no album tag is in All Songs only. An album tap opens the library album's own page
  (`as_open_album`, class `0xf003`, the whole album).
- **An artist's songs** (`as_fill`, `as_load`): copies of the library records whose field splits to
  the name, in library order, handed over as stock hands a class query's rows. `songs_artist_list`
  calls `as_load`, which first runs the two stock queries on the name so the browsing record is what
  the stock artist songs page leaves (class `0xff11`). Our Songs page (`sg.split`) reads with
  `as_fill` in place of `loadLocalClassList(0xff11)`, so the stock query never decides which songs
  show. Delete and Add to Playlist work unchanged on these records (the generic class `0xff11`
  paths).
- **Play** (pills, a row tap, Shuffle): `so_play_own(cls, list, at, how, open)` copies the page's
  list into the queue with `REC_CLASS` set to the class, no `loadSongList`.
  **The queue's class is All Songs (`0xf001`), not `0xff11`**, so Memory Playback resumes after a
  reboot. The boot resume (`memeory_startplayer`) re-runs the saved class's list query and matches
  the saved name and path; with `0xff11` that query would run on whatever browsing record the last
  stock `loadSongList` left (the split name matches no `songer` of a combined field), so nothing
  would resume. With `0xf001` no browsing record is read. Daily Mix and Shuffle Songs queues do the
  same.
- **Search** (`se_load`): with the setting on (and not Album Artists) the artist list is `as_rows`, so
  a name that occurs only inside another's field is found and a tap opens that name's scoped page.
- **Look up artist** (`pm_on_lookup_artist`): the artist is the first name of the playing track's
  field (`as_first_row`) and the scoped page opens on it, never the joined name's empty page. There
  is no chooser. The row menu has no artist action.
- **Photos** (`cc_build_add_artist`, the artist stage of `hc_on_start`): the Home pass opens a
  session (`as_session`) and keys each album by the **first name** of its artist field (`as_lead`):
  its snapshot entry, purity and job. So `Music/A/` holding albums by `A` and `A feat. B` stays pure
  for A. A name that only ever appears as a later artist gets no automatic photo (a shared folder
  cannot be attributed to it by the purity rule); its photo is the one picked in Find Artist Photo.
  The pass's keys change with the setting, so use Settings > Library > Rebuild Artist Photos after
  turning it on or off. The pass walks albums, not songs, so names only on some tracks of an album
  are not looked at.
- **Design**: a small branch in the stock path, not a `lib_src_t`. A non-NULL source means Navidrome
  in many places (`ar.src`, `al.src`, `sg.src`: no cover-cache worker, no Select / Cover Flow caps,
  synthetic ids), and a wrapper would have to switch each of those off again. The row marker keeps
  the local library's covers, workers, select, sheet and Cover Flow and replaces only the four calls
  keyed on the whole field (`coverflow_artist_albums`, `songs_artist_list`, `cc_open_album`, the
  Songs page's read and play). Nothing is stored: every answer is computed from the library when
  asked, so there is no copy to go stale.
- **Limits**: a name that only ever appears after another has no automatic photo; an Artists page
  already open under Settings keeps its rows until opened again; the artist's Next Album order and
  the Pod's Artists menu still use the stock queries and show no albums for a secondary name; names
  beyond 20,000 are not listed.
- **Cost**: at most a 256 KB hash table and 160 KB of name spans while rows are built; peak memory is
  the library records (`cc_songs`) plus the row records. The splitter looks for an exception only
  where it found a separator, which keeps a 20,000-song build cheap.

### Split Genres

`patch/genresplit.c`, based on a contribution by powkakashi (GitHub issue 18). Genres page only (not
the albums' genre, Search or Navidrome). **Off by default, and then no line of it runs**: the page
reads the stock `loadLocalClassList(0xf006)` and a genre's songs are the stock `0xff09` query.

The setting is `/mnt/data/m1plus/library-genre-split` (`GS_FILE`, Settings > Library > Split Genres,
[settings](settings.md)), in the format of the artist one (`1`, `m<decimal>`, `o<decimal>`; the mask
bits are the splitter's `M1_SPLIT_*`). A genre splits only on the punctuation separators `;` `/`
`&` `,` `+` (`GS_ALL`, bits 0-3 and 7): the splitter's words (`feat.`, `vs.`, `x`, `with`, `and`)
join artists, and `and` would cut `Drum and Bass`, so any other bit of a saved mask is dropped.
**The default mask (`1`, `GS_DEFAULT`) is the semicolon alone**: a genre field is not an artist
field, so `Rock/Pop` and `Jazz, Blues` stay whole until the user turns `/` or `,` on.

Names never split, whatever the mask (an exception protects only its own bytes, so `R&B/Soul` still
gives `R&B` and `Soul` with the slash on):

- **Built in** (`gs_builtin`): `R&B`, `Rhythm & Blues`, `Rock & Roll`, `Drum & Bass`,
  `Folk, World, & Country` (also without the second comma), `Stage & Screen`, `Brass & Military`,
  `Brass & Woodwinds`, `Devotional & Spiritual`, `Fitness & Workout`, `Praise & Worship`,
  `Slowed & Reverb`, `Melodic House & Techno`, `Singer/Songwriter`. Each is a name in a published
  genre list (ID3v1 / Winamp, Discogs, Apple Music, MusicBrainz, AllMusic, Beatport; the table's
  comment names which) with a part that is not a genre by itself. A name joining two genres of
  the same list (`Pop/Rock`, `Hip-Hop/Rap`, `Funk / Soul`, `Jazz+Funk`) is not in it: the mask
  decides. The built-in artist exceptions (`AC/DC`, ...) are not used. The card file can only add
  to the built-in names; a possible improvement is letting it take one out.
- **The card file** `/mnt/mmc/genre-exceptions.txt` (`GS_EXCEPTIONS`), added to them, with the
  artist file's rule (one name per line, `#` lines and blanks skipped, 64 names, 4096 bytes).

- **Rows** (`gs_rows`): the stock genre list is read and taken (`lib_take_list`); each tag
  (`REC_TITLE`) is split (at most 8 names) and names merge ASCII case-insensitively in a hash table,
  **the first spelling seen** staying. The names are sorted as the Artists page sorts names
  (`gs_order`: `cc_name_keys` / `cc_key_cmp` / `cc_heapsort`, a CJK name by its pinyin initial), so the
  A-Z sections the page cuts by `cc_name_initial` stay in order; the "Unknown Genre"
  row (id -1) comes last, and exists when the stock list has its row or a tag names nothing. Rows are
  page-owned records (`REC_ID` 1.., type 4, **`REC_CLASS` = `GS_MARK`** `0x47535031`: `gs_is_row`). The
  page keeps them in `ar.split` (so the foreground check reads `gs_rows` again, and Z-A, sections and
  the rail work as for stock rows). Without the list or memory the page falls back to the stock rows.
- **A genre's songs** (`gs_fill`, `gs_tracks`): the stock genre list is read again; every tag that
  splits to the name (a cheap substring test first) is replayed through the stock query, the browsing
  record set as a stock row tap leaves it (`songs_genre_record`: class `0xff09`, the tag at `+ 0x30d`,
  the Unknown byte `+ 0xc`) and `loadLocalClassList(0xff09)` run, and the results are concatenated in
  the stock list's order. Stock's statement is ``select * from songtable where style like '<tag cut to 127 bytes>'``
  (`_` and `%` are wildcards, a long tag is cut), so while the query runs `pc_genre_exact` points at the
  whole raw tag and `pq_filter` ([payload](payload.md) hook 6) asks it as
  `style='<tag, quotes doubled>' COLLATE NOCASE and <podcast filter>` instead: `Rock; 80s_` never returns
  `Rock; 80sX`, and a 130-byte tag answers in full. The Unknown row's stock query is left as it is. A song has one tag, so nothing is listed twice. The Unknown Genre row asks
  the stock Unknown row and every tag that names nothing, each as its own row would be. At most 512
  tags answer one name. Our Songs page (`sg.gsplit`, opened by `songs_open_genre_split`, no fallback to
  the stock page: the stock query on a split name finds nothing) reads with `gs_fill` in place of
  `loadLocalClassList(0xff09)`.
- **Play**: as the artist split: `so_play_own`, class All Songs `0xf001`.
- **Delete and Add to Playlist** (Select, and a row's menu): on a split page they pass the generic
  songtable class `0xf001` (`sg_op_cls`), never `0xff09` keyed on the split name; both loops work from
  the selected records of the page's list, which are the real songs of every tag. The page reads its
  list again through `gs_fill`.
- **Limits**: names beyond 20,000 are dropped; a name beyond 255 bytes (`GS_NAME`, the Songs page's
  name field) is dropped from its tag (`gs_names`), the tag's other names stay and a tag left with none
  is the Unknown row's; a raw tag beyond 300 bytes (`GS_TAG_MAX`, what the filter's 1 KB buffer takes
  escaped) names nothing and is not in the Unknown row. An index that leaves no row is an empty page,
  never the stock rows; Memory Playback resumes the track
  through the whole library, not the genre list; an Artists page already open keeps its rows until
  opened again; the splitter is ASCII case folded, so names that differ only in non-ASCII case are two
  rows.

### Key, cache and building

**Key** (`ap_key`): FNV (`cc_fnv`) of the name trimmed, ASCII case folded, without a leading "The "
(a name of only "The" keeps it); no accent folding, no splitting. Blank = no key. Artists and Album
Artists share by name. An album's artist is its stock album row's `REC_ARTIST`. `ap_key` is the one
entry: no other code may hash a name differently.

**Cache** (`CARD_DIR "/artists"`, `AP_DIR`): `a<key>-168.jpg` (page header, drawn as an 88 px circle),
`a<key>-44.jpg` (list rows, 40 px circle), `a<key>.src`, `a<key>.pick`, `a<key>.try`.

- Both sizes come from one decode and both files are **squares** cut when built: `pv_square`
  (`patch/pccover.c`) crops to the short side and area-averages to 168; the 44 px file is made from
  the 168 px one. A landscape source is cropped at the centre; a portrait one starts a third of the
  extra height from the top, so a head near the top stays in. A source with a short side under 168
  is cropped but not enlarged. The pages still crop the centred square when they decode and mask the
  circle.
- **No photo = an EMPTY `-44` file** (the album cache's convention; `-168` and `.src` are removed).
  The `-44` file is published last, so a non-empty one means both exist.
- `.src` is text: `m1plus artist 1`, `src: <path>`, `size: <bytes>`, `mtime: <seconds>`, `end`, for
  the re-check.
- `.pick` marks a photo the user picked (`ap_pick(src, key)` makes both files with `ap_make`, writes
  the marker, removes `.src` and `.try`, bumps `ap_epoch`). While `.pick` and the `-44` file exist no
  automatic build touches the artist (Home pass, rebuild and re-check included), so a picked photo
  also wins over an `artist.jpg` added later. Removing the marker is the only way back.
- **Publishing** is under `ap_mutex` (never held over a decode), because the cover worker and the
  network worker both write an artist's entry. `ap_make` decodes into temporary files first (`.tmp`
  automatic, `.pk` pick), then under the mutex: an automatic build stops if the artist is picked by
  now; a pick writes the marker first and stops if it cannot; the old `-168` file is read into memory
  and written back if the `-44` file cannot be published. A save is whole or leaves the artist as it
  was, and `ap_epoch` moves only for a whole one.
- `.try` is a strike written before discovery and removed after. One found at the start of a job
  means the last attempt died or hung, so the artist gets the empty marker and the same file cannot
  hang every pass.

**Building** (the Home job, [homecover](homecover.md) "Artist photos"). After the cover steps of
`hc_on_start` the album copy is walked in steps of `HC_BATCH` 64 and `cc_build_add_artist(track,
artist, force)` records each album's track folder and artist key in a snapshot (`ap_lib_add`, at
most `AP_LIB_MAX` 8000 albums; a larger library or no memory gets no artist photos) and queues one
job per artist unless its `-44` file exists or `force`. The worker sorts the snapshot once and runs
`ap_job`. Existing results are never re-checked by a foreground pass (only the artist whose page is
opened, below). A new artist comes with a new album, which changes the library signature and runs the
pass. The **`artists` stamp line** (separate from `covers`) is written only when the set finished and
every artist fitted (`CC_MAX_JOBS` 4000). Nothing blocks the UI thread.

**Rebuild Artist Photos is separate from Rebuild Covers.** Settings > Library > Rebuild Artist Photos
(`ACT_AREBUILD` 92, glyph `mic-vocal`, under Rebuild Covers): `arebuild_ask` asks in the stock
confirm ("Rebuild all artist photos? This may take a few minutes."); Yes writes the request file
`/mnt/data/m1plus/artists-rebuild` (`AREBUILD_FILE`, listed in Settings Files), clears `hc_off` and
toasts "Artist photos will rebuild on Home"; a failed write toasts "Storage unavailable". The
request makes `hc_expect` see work, forces every artist (found ones too; a removed picture becomes
the marker) and is deleted when the set finishes, or at once when there is no artist to check. The pill reads
`Rebuilding artist photos...`, then `Rebuilding artist photos n/m` from the first artist job on
(`Preparing artist photos n/m` without the request); covers first when both are pending. It touches no covers. Clear Cover Cache does not touch
`AP_DIR`.

**Limits.** An album is located by its first track only. An interlaced PNG cannot be cropped in
one pass, so it gets no photo (`pv_square` returns 0). "A feat. B" with no photo of its own uses A's
cached photo at lookup time; the cache never holds a file under the full name. An artist with no
picture and a track path that no longer exists gets no marker (retried next pass). Over 4000
distinct artists a rebuild is done as far as the job array goes.

### Purity map

The worker cannot query the stock database, so the Home pass keeps what the purity check needs
(`AP_DIR/purity`). While the snapshot is built, a hash table records for the album folder and every
folder above it the one artist key under it (0 = two artists or an untagged album: conflict). When
the walk is complete `hc_on_start` calls `ap_lib_save` (UI thread, once, before the worker starts):
at most `12 + 8 x AP_PUR_MAX` bytes (24576 entries), written to `purity.tmp` and renamed. File: magic
`0x31555041`, entry count, a check word, then (folder FNV, key) pairs. An unusable snapshot or a pass
that makes none removes the old file, so a map never describes another library. It is as old as the
last Home pass.

### Re-check on open

`ap_recheck(name, tracks)`: the scoped artist page ([albums](albums.md) "Artist photo re-check")
hands over the first track of each of the artist's albums (at most 64 folders). It needs the worker
free (`cc_build_open` refuses otherwise: skipped, the Home pass covers it) and never joins it. The
job (`CC_RECHECK_JOB`, `ap_recheck_job`), per artist key:

- `.pick` and a `-44` file: nothing. A `.try` strike: the empty marker.
- A photo: read `.src`; one stat of the source: size and mtime as recorded means **nothing else
  happens** (no folder is listed, no file written; a photo with no readable `.src` is left alone).
  Changed or gone: discover again; if nothing is found but the old source is still there it is made
  again.
- An empty marker or no `-44` file: discover again (`ap_walk` over the page's folders, purity from
  the saved map).
- **Without a usable map** only the album folders themselves are looked in and nothing is concluded
  from a miss: no marker is written and a removed source is not turned into a marker, so a later
  full pass can still find a photo in a parent folder. With the map, a miss becomes the marker.
- A result that made, replaced or removed a photo bumps `ap_epoch()`.

The open artist page polls its own set (`al_on_build`, 500 ms) and, when it is over, switches the
circle in place or reads a replaced photo again. The Artists page behind learns on
`EVT_WINDOW_TO_FG` (`ar_on_fg`): when `ap_epoch` moved the tiles and 2-bit states are dropped and
every circle decoded again. Rows still unknown are retried while a set runs (`cc_build_active`,
every 1 s, `ar_on_retry`) and once when it ends.

### Showing the photos

**Lookup** (`ap_lookup(name, size, url)`, UI thread, opens files: never from a paint). The name's own
`ap_key`, then, when that file is missing or empty, the **lead artist's** key (photo only). `size` is
`AP_LIST` (-44) or `AP_HEAD` (-168). Answers: `AP_PHOTO`, `AP_LEAD` (the lead's file), `AP_NONE` (the
marker, and the lead has none; a blank name), `AP_UNKNOWN` (a file is missing: the pass has not been
there yet). The lead is the text before the earliest of `" feat. "`, `" ft. "`, `" featuring "`,
`" & "`, `" x "`, `", "`, `"; "` (ASCII case folded); none when there is no separator, the lead is
empty or over 260 bytes, or its key equals the name's.

**Rows.** `ar.photo` sizes the text ring's `grid_t` as 40 px circles (corners cut in the bitmap's
alpha so the press fill shows behind). Each tile's `art` is 0 not looked at, 1 the circle bitmap, 2
placeholder. `ar.pst` keeps 2 bits per display position (`AP_UNKNOWN` 0, `AP_PHOTO` 1, `AP_NONE` 2,
`AP_LEAD` 3), so a row that scrolls out of the 13-tile ring and back is not looked at again when its
answer was "none". The "Unknown Artist" row is never looked up. Paint opens no file and decodes
nothing.

**Loader** (`ar_on_photo`, 16 ms): one row a tick, nearest the middle first: `ap_lookup` then
`grid_art_url` (the centred square of the -44 file box-reduced to 40 px). Nothing happens while the
list moves. **The decode is on the UI thread**, one 44 px JPEG a tick like the Albums and Search
covers, because the stock image loader is not thread safe and the cover worker owns no UI objects.
The cache files themselves are made on the worker.

**Placeholder** (`ap_placeholder(win, d)`, made at open and after every list rebuild; also 88 px for
the artist page): a `#333333` circle with the Lucide `mic-vocal` glyph in `#8C8C8C` at 0.52 of the
diameter (`pod_ic_ar_art`, `mod_icons.ARTIST_ART`), edge cut by `ap_circle`.

**The artist page's header**: [albums](albums.md) "Scoped to an artist". With no photo the page has
the same header without the circle (no placeholder there), the name and pills `PH_SHIFT` 96 higher.

**Developer > Cache > Artist Photos** card (`INFO_APHOTOS` / `INFO_ANONE`): **Photos** counts
`a<8 hex>-44.jpg` files with a picture, **None** the empty ones, read in the Cache page's bounded
steps (`CP_ADIR`).

## Returning to the page

The local list (Artists, Album Artists, Genres, Composers) is read once at open and again when the
page returns to the foreground (`ar_on_fg`, `ar_local_changed`): the stock query is compared with the
page's rows (`ls_same_list`) and a different or now-empty list is read again with the scroll position
kept (`ar_load(1)`). Songs deleted on an album page above leave an artist that has none, and a row
never opens a stale one. The same list is not copied again.
