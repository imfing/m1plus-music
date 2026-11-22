# The Queue page

**Sources:** `patch/queuepage.c` (page), `patch/upnext.c` + `upnext.h` and `pod_queue_insert`,
`pod_queue_move`, `pod_queue_remove`, `pod_clear_upnext` in `patch/shuffle.c`, `np_on_queue` in
`patch/nowplaying.c`, `patch/rowmenu.c` (`rowmenu_bind_queue`, `rowmenu_open_queue`), `tools/pod_ui.py`
`build_queue_page`, `tools/pod_pages.py` `QUEUE_PAGE`, `QP_*` in `patch/offsets.inc`.
Now Playing's queue button opens our own page (`ui/m1plus_queue.bin`, window `m1plus_queue_page`)
instead of stock's side drawer. It shows the playing track, Shuffle and Repeat buttons, and Up Next
in real queue order, with Clear and a "..." sheet per row. No hook of its own: `np_on_queue` is a
click handler bound on `btn_queue` after the stock init, from the existing Now Playing init hook.

## What the stock app does

- The queue button opens `dialog/playqueue_dialog`, a 240 px drawer: a play-mode header, the rows,
  a bottom button. A row tap calls `start_playqueue(index)` (offline, a stream row shows
  `msg_notnetwork`). `playerjumpinfo_page` is not reached from the queue button.
- The queue is the deque `PLAY_QUEUE` plus the play position `mclGetPlayPos`; every stock reader pairs them.
- Stock cannot remove a track, clear the queue or reorder it. Delete song in the More sheet deletes
  the file. Stock has no `deque_pop_back` import.
- Stock's mode word is 0 List play, 1 Repeat one, 3 Repeat all. Shuffle is our own flag
  ([shuffle](shuffle.md)), not stock's mode 2.

`np_on_queue` answers `RET_OK` (the drawer opens as before) for an empty queue, no track at the play
position, a stream play type (2, 3, `0xf0`, `0xf1`) or a window or asset that will not open.

## Our page

A list that fills the 450 px window (the album page's structure) under one glass control, the Back
disc. No Now Playing disc and no close chevron: the page always opens from Now Playing.

```
y   0   (back)                                  glass Back, over the rows
   56   [cover 64] Title 20 px / Artist 16 px   header: the track at the play position
  136   [ shuffle ]  [ repeat ]                 two equal icon-only pills, 145 x 40, x 10 and 165
  192   Queue                         Clear     "Queue" 20 px; Clear 17 px #AAAAAA, right edge x 310
  226   [cover 52] Title 21 / Artist 18   ...   Up Next rows 64 px, hairline x 74..298
```

- **Up Next** is the tracks after the play position in queue order, which is the real play order.
  The playing track is only in the header. Row text follows the stock drawer (CUE track or no
  title: file name). Empty: "No upcoming songs".
- **Decision: no Shuffle placeholder.** Turning Shuffle on shuffles the queue in place
  ([shuffle](shuffle.md)), so Up Next never lies. The page reads the queue again at once (its
  own button) or at its next tick (`qp_sync`).
- **Buttons are independent, as on Apple.** Shuffle toggles the flag (`pod_set_shuffle`). Repeat
  cycles off, all, one (`pod_set_repeat`), whatever the flag is. Over `SHUFFLE_MAX` songs or with
  no memory, Shuffle stays off and the stock message box says why. On is a light pill
  (`QP_PILL_ON` `#C8C8C8`) with a near-black glyph, off is a dark pill (`#2C2C2E`, role
  `ROLE_PRESS_QPILL`, [accent](accent.md)) with a white glyph. Repeat one shows the repeat-1 glyph.
  Neutral greys, no accent; no autoplay or infinity button (stock has none).
- **Sync with Now Playing.** Now Playing's button reads the shown mode (`sh_display_mode`: 2 while
  the flag is on, so it shows Shuffle also with Repeat all; its cycle Shuffle -> Repeat all turns the
  flag off). This page's `qp_sync` reads stock's mode and the flag: a flag change reloads the rows
  from the top, a repeat change only touches the buttons. Our setters repeat stock's click handler calls (`mclSetPlayMode`,
  `write_int_config`, `notifyPlayMode`, `dmrSendPlayMode`) except the button picture, so
  `np_on_foreground` redraws it (pinned `stock_np_mode_button`) when Now Playing is back in front.
- **Tap a row:** `start_playqueue(play position + 1 + row)`, then the page reads the player again
  and stays. A drag, the header and the air play nothing.
- **Refresh timer** (`QP_TICK_MS` 500 ms, 1 s with the screen dark): a moved play position reloads
  the rows, a mode change touches the buttons, a replaced queue reloads when the page is on top.
  The queue is checked by pointer, size and first record (`qp_valid`).
- **Header:** the track at the play position, no tint (the page is black).
- **Server, podcast and audiobook tracks** are never looked up as albums. Subsonic rows (`sba_rec_track`) show
  the source's cover (`sba_rec_cover`, see [subsonic](subsonic.md)), podcast episodes (`pc_is_path`)
  the show folder's picture (`pc_show_cover`, ranked as the Shows page ranks them), audiobook parts
  (`bk_is_path`) their book's cover (`bk_art_cover`, the one the Audiobooks page shows: the book's
  `cover.*` / `folder.*`, else its art cache file; see [audiobooks](audiobooks.md)). Each is
  read once per show or book while the page is open (`qp.pshow`, `qp.pbook`) and the header uses the
  same. All get the placeholder when there is none; the page never starts the cover worker, so a
  book whose art file is not made yet shows the placeholder. A server queue is this page's, not the stock drawer's:
  `qp_stream` reads the class word the play set, and only stock's stream classes (2, 3, `0xf0`,
  `0xf1`) count as streams.

### Covers

A row shows the Cover Flow cache file of its own artist and album (`cc_album_key`; see
[covercache](covercache.md)), loaded one per tick on the page timer, none while the list moves,
nearest the middle first. A miss with an album tag asks the **cover map** (`cc_cmap_*` in
`patch/covercache.c`), because the cache is keyed by the library's album record, so a collab
("A; B") or a feature has no file under its own artist.

- One query per page, on its first miss: getAllAlbum's own statement through `toolsQueryDbTable`
  (pinned in `QUERY_PINS`), so the Library filter applies and the keys are the ones the Albums
  page and Cover Flow use. `cc_albums` is not used: it replaces the list the page under Now
  Playing draws from. A queue with a file for every track runs no query.
- The map is an array of `{hash, key}` sorted by hash (FNV-1a of the album name, ASCII case
  folded as SQLite NOCASE does). A hash shared by two keys is dropped (placeholder, never the wrong
  cover). At most `CC_CMAP_MAX` 4096 albums are kept (the first by name); rows past the cap are still
  checked for a shared hash, so an album beyond the cap never gets a kept album's cover.
- Whether an entry's cache file holds a picture is checked lazily, once per album shown.
- The map is freed with the page. An empty library, a failed query or no memory is not retried.
  The query's records (about 300 bytes an album) are freed as soon as the map is built.
- With the opt-in log (`m1plus-log` on the card) each build writes
  `queue: cover map <ms> ms, <rows> albums, <kept> kept, <ambiguous> ambiguous, <n> queued`.

Get Info does not use the map ([songinfo](songinfo.md)).

### Clear

**Clear** (`btn_qclear`) is Apple's text button, right-aligned on the "Queue" line
(`QP_CLEAR_X/Y/W/H` 210, 186, 100 x 40). It is shown only while Up Next is not empty, the play
type is neither a stream nor folder playback and `pod_clear_ready()` holds (libcstl as pinned,
no DLNA service running); otherwise hidden. `qp_clear_sync` re-reads this on every tick.

- **Decision: no confirmation.** A tap calls `pod_clear_upnext`, then the page reloads: Up Next
  shows "No upcoming songs". The playing track keeps playing; the play position and the tracks
  before it stay.
- **Hidden in folder playback** (play type 1, also Podcasts and Audiobooks): stock rebuilds a folder
  queue at its end, so a cleared Up Next would come back on the next Next.
- **Decision: hidden while DLNA runs.** The UPnP threads read the queue without a lock, so a freed
  tail record would be a use-after-free. The gate is stock's `dmr_serverflag` (1 while the
  service runs), read again under the lock. Clear shows with the DLNA switch off or Wi-Fi off.
- **Clear drops Shuffle's saved order**: it describes a queue that is gone. The flag stays, and
  Shuffle off afterwards restores nothing.
- **Engine** (`pod_clear_upnext`): under the payload lock it re-reads position and size, closes an
  open gapless preload (`cancel_preload`), then calls libcstl's `deque_pop_back` until the size is
  `pos + 1`. Records `0..pos` are never moved or copied; nothing is allocated, so Clear cannot fail
  for memory. Answers 1 cleared, 0 nothing after the position, -1 refused.
- **libcstl as pinned:** demo does not import `deque_pop_back`, so `cstl_pop_back` resolves it from
  demo's `deque_size` GOT slot and refuses unless the library's words match the pins
  (`LIBCSTL*` / `CSTL_*` in `tools/pod.py`; `check_libcstl` fails the build otherwise).
- **No hook on `mclNextSong` / `mclPrevSong`:** holding the lock there would need a recursive lock
  (`mclNextSong` can reach our `sh_load_playlist`) and would stall the UI thread across
  `mclStartPlayer`'s sleeps and `mclStop`'s wait (up to 1.5 s).
- **Locking:** the lock excludes our other writers ([shuffle](shuffle.md) "Locking"). Stock's
  unlocked readers are the remaining gap, see [shuffle](shuffle.md) "Remaining gap". Transitions
  run on the UI thread, which is also the thread of the tap.

## Up Next: Play Next / Play After

`upnext_add` (called by the row menu, [rowmenu](rowmenu.md)) inserts rows into the playing queue.
Stock plays the queue in order in every mode, so an inserted row plays when its turn comes, with no
pool or `mclNextSong` hook.

- **Play Next** inserts at pos+1; several stack newest first, the rows of one call keep their
  order. **Play After** appends. Same in List play, Repeat all, Repeat one and Shuffle. The class
  (`REC_CLASS`) is stamped from the playing row. Stock readers read the queue live, so the Queue
  page, lock screen, counts and Previous follow without a hook.
- **The insert** (`pod_queue_insert(rows, after)`): under the payload lock it `_deque_push_back`-copies
  each row, rotates the new rows into place with row swaps (no whole-deque rebuild, so no O(queue)
  allocation) and grows Shuffle's saved order ([shuffle](shuffle.md) "Rows inserted into the
  queue"). Answers `POD_INSERT_OK`, `_IDLE`, `_FULL` (over `SHUFFLE_MAX` 65536), `_MEMORY`; every
  non-OK answer changes nothing.
- **Gapless:** an insert at pos+1 with an open preload calls `cancel_preload`. The cancel leaves no
  preload in that song, so the join into the inserted song has a gap (accepted). An add more than
  about 6 s before the end is gapless. A Play After in the middle leaves the open preload alone.
  Why `mclSetGaplessMode(0)` and not a `mclSetPlayMode` pair: [shuffle](shuffle.md) "Gapless".
- **Refusals** (checked before anything is touched): no rows; Radio running (`rd_running`); a
  podcast episode; a row with no file; a stream play type (2, 3, `0xf0`, `0xf1`); folder playback
  (play type 1: stock rebuilds a folder queue at its end, which drops inserted rows); over 65536
  songs; no memory for the order; the DLNA renderer service running (checked under the lock).
- **Nothing playing:** the rows become the queue as other play paths start one (class of the first
  row or `0xf001`, `start_player`), answer `UPNEXT_STARTED`. The Shuffle flag and repeat mode are kept
  (with Shuffle on, `sh_load_playlist` shuffles the rows with the first row first). The caller may
  open Now Playing.
- Not persisted: after a reboot the queue is the class's own, resumed at the playing song.

```c
int upnext_add(void *rows, int after);   /* rows: a deque_t of stSongInfo, copied; 0 = Play Next */
```

| Status | Value | Meaning | Toast |
|---|---|---|---|
| `UPNEXT_ADDED` | 1 | rows are in the queue | "Playing Next" / "Added to Queue" |
| `UPNEXT_STARTED` | 2 | nothing was playing: the rows are the queue | none |
| `UPNEXT_EMPTY` | -1 | no rows | none |
| `UPNEXT_STREAM` | -2 | stream playing, or Radio running | "Not available while streaming" |
| `UPNEXT_FOLDER` | -3 | folder playback (play type 1, also Podcasts) | "Not available for folder playback" |
| `UPNEXT_PODCAST` | -4 | a podcast episode among the rows | "Not available for podcasts" |
| `UPNEXT_MISSING` | -5 | a row has no file | "File not found" / "Storage unavailable" (`so_missing`) |
| `UPNEXT_FULL` | -6 | queue would pass 65536 songs | "Queue is full" |
| `UPNEXT_MEMORY` | -7 | no memory for Shuffle's order | "Not enough memory" |
| `UPNEXT_DLNA` | -8 | DLNA renderer service runs | "Not available while DLNA is on" |

Refusals change nothing; check the answer, not the queue. Rows are any `stSongInfo` the library
lists; an album or artist is a deque of its tracks. Call from the UI thread. The album long-press
sheet (Albums, Home pins, Recently Played; `pins_queue_album`, [pins](pins.md)) passes every track
of the album in order to `upnext_add`. Continue with Next Album also uses `upnext_add(rows, 1)`
([nextalbum](nextalbum.md)); only `UPNEXT_ADDED` counts.

### Edit engine: move / remove

- `pod_queue_move(from, to)`: the row at absolute index `from` goes to `to`, the rows between shift by
  one. `pod_queue_remove(i)`: the row is rotated to the last slot and libcstl's `deque_pop_back`
  destroys it (never `deque_erase`). Rotation is the insert's `row_swap`: no allocation, every
  string stays owned by one slot.
- Up Next only: every index must be above the play position and below the size; rows `0..pos`
  and the position are never touched. `from == to` is OK
  and changes nothing. Codes `POD_EDIT_*`: `OK` 1; `RANGE` -1, `DLNA` -2, `LIBCSTL` -3 (remove
  only). Refusals change nothing. The queue, size and position are re-read under the lock.
- Shuffle's saved order: a move rotates `orig` with the rows, so Shuffle off restores the original
  order (the manual order is dropped by Shuffle off, by design). A remove deletes the entry and
  lowers the positions above it, in place.
- Gapless: `cancel_preload` runs when the row at pos+1 changes; a remove also resets a remembered
  preload target at or past the new end.
- `pod_clear_ready()` is the readiness test for both Clear and the edit actions.

### Row edit (the "..." of an Up Next row)

- **The dots:** each Up Next row ends with the row lists' grey "..." ([rowmenu](rowmenu.md)), in a
  44 px zone x 266..310. The text ends at x 269 (10 px before the glyph's ink). A tap on the dots, or a press held on the row, opens the sheet; a tap elsewhere
  plays the row; the press rules are the lists' ([rowmenu](rowmenu.md) "Long press").
- **When they show** (`qp.edit_on`): Clear's condition and the play type is not folder playback.
  Otherwise the rows have no dots and the text ends at x 298.
- **The sheet** is the row menu's queue form ([rowmenu](rowmenu.md)): **Play Next**, **Play After**,
  then, under the hairline, **Remove from Queue** (red). No Add to Playlist, Favorite or Get Info. A scrim tap closes it and
  changes nothing; so do a queue reload, the page going behind another and the edit condition
  turning off.
- **The action** (`qp_on_menu`): `pod_queue_move(at, pos + 1)`, `pod_queue_move(at, size - 1)` or
  `pod_queue_remove(at)`, then `qp_load(1)` (scroll offset kept). No confirmation, no toast on
  success. `POD_EDIT_DLNA` shows "Not available while DLNA is on"; any other refusal only reloads.
- **Row identity:** the sheet remembers the row's path pointer (`qp.mid`). The action does nothing
  unless the queue is still the page's, the play position is unchanged and the record at `at` has
  that path pointer, so a stale sheet never edits another track.

## Limits

- No drag handles, swipe, marker or count on rows.
- No cover tint. The playing track's `/tmp` cover is not used when the cache has no file.
- Now Playing's idle countdown is not reset (the big-cover page opens only over `playing_page`).
- Stock's unlocked readers on other threads can see a row mid-swap ([shuffle](shuffle.md)).

Pinned stock: `tools/pod.py` `SONGS_PINS` (the queue button's handler, the drawer's row handler,
prologues of `start_playqueue`, `mclGetPlayType`, `mclGetPlayPos`) and `SHUFFLE_PINS`
(`mclSetGaplessMode` words, `dmr_serverflag` reader and setter).
