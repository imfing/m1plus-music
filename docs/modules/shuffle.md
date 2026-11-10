# Shuffle

**Sources:** `patch/shuffle.c`, `tools/pod.py` (`SETMODE`, `LOADPL`, `MODE_SITES`, `SHUFFLE_PINS`), tests `test/pod/shuffle.py`
(`apple_tests`), `test/pod/queuepage.py`, `test/pod/settings.py`.

The Shuffle page (`ui/m1plus_shuffle.bin`, opened by the menu's one Shuffle row as in q2-pod's Library)
has three rows: **Shuffle Songs** (the library as the queue, Shuffle on, from a random song), **Shuffle
Albums** (albums in random order, each in track order), **Shuffle Folders** (folders in random order,
each in file-name order). One call `shuffle_play(kind)`, no timer, thread or page left behind.

Every row takes the stock Songs path with class `0xf001`: `loadLocalClassList(0xf001)`;
`loadSongList(queue, name, cue_start, 0xf001)` (copies the list, stamps the class, fills
`g_memory_info`); Albums/Folders reorder the queue; the first file is checked with `access`; the play
mode is set if needed; `navigator_to_with_context("playing_page", {queue, index, 0xf001, 2})`
(`playing_page_init` -> `start_player` `0x4e4648` copies the queue with `mclLoadPlayList`; the payload destroys its own copy).

## Apple-style Shuffle

Stock's own Shuffle (mode 2) is never used: `mclNextSong` draws one index from a pool of unplayed songs
(`0x5d58fc` -> `0x5d5a20` -> `0x5d03b0`), so the queue keeps library order, the Queue page cannot show what plays next
and gapless preloading cannot see the next song. Shuffle is the payload's own **flag** (`/mnt/data/m1plus/playback-shuffle`,
`1` on, missing or anything else off; read with `set_read`, saved with `home_write_atomic`, listed on Settings > Developer > Tools >
Settings Files). Stock's mode stays 0 (List play), 3 (Repeat all) or 1 (Repeat one) and plays the queue in order, so the
Queue page shows the real order and gapless works as for any list. Shuffle and Repeat are independent: Shuffle plus Repeat all is
allowed (set from the Queue page; Now Playing's single button shows Shuffle then).

- **Turning it on** (`flag_set(1)`): the songs after the playing one are shuffled **in place** (Fisher-Yates with the xorshift32 of this
  file, `permute`) and the playing song and the ones before it stay. `apply_perm` moves whole records cycle by cycle with one record of
  temporary storage, so every string stays owned by one slot, as Shuffle Albums/Folders do. Each slot's original position is kept
  in `sh.orig` (4 bytes a song, `calloc`, freed when the order is dropped). `shuffle_tail` fills `orig` with the identity, permutes `orig[lo..n)` in
  place (`apply_perm(q, lo, m, orig + lo)`: new slot `lo+i` takes the record at slot `p[i]`, the same meaning as `shuffle_load`) and keeps it: one
  `n`-entry array plus the cycle bitmap (1 bit a song, freed at once). Peak auxiliary memory at the cap: 256 KiB + 8 KiB, was about 520 KiB.
- **Turning it off** (`restore_order`): every record goes back to its original slot and needs **no allocation**, so Shuffle off cannot fail: the
  record at slot `j` goes to slot `orig[j]`, cycle by cycle with one record in hand (two temporary records on the stack), the slots done marked with
  the high bit (`0x80000000`) of their `orig` entry (n <= 65536), the array freed right after. The play
  position follows the playing song (`mclSetPlayPos(orig[pos])`), so the song stays and the songs that followed it originally come next.
  The slots before the playing song are restored too (songs already played in the shuffled order return to their original place;
  the design said "from the current song onwards", this is the whole queue with the playing song kept: the same Up Next).
  A queue whose size changed since the shuffle (a song deleted) has no usable order and keeps its order; the flag still goes off.
- **A queue that is about to be replaced is not reordered** (the flag-only path). `set_mode(mode, fresh)` / `set_in_order(fresh)` with `fresh` set
  (`sh.fresh` while they run, like `keep`) make `sh_set_mode` call `flag_only(want)`: set or clear the flag, drop the old order, reorder nothing.
  Used by `shuffle_play` and the exports `pod_set_mode_for_queue` / `pod_set_in_order_for_queue`, called by every path of ours that sets the mode
  and then loads a queue: ip_play (`patch/ipod.c`), the Songs/album/genre rows (`patch/songops.c`), the Daily Mix, the episode queue
  (`pg_episode_queue`, `patch/podcasts.c`, also used by the iPod). `sh_load_playlist` then shuffles the replacement. So an old queue over 65,536
  songs does not stop Shuffle for a small new one, and no record of the old queue is copied. `pod_set_mode`, `pod_set_in_order`, the Queue page's
  Shuffle button and the stock mode requests (hook) keep the reordering path (no queue load follows).
- **A queue loaded while it is on** (a song tap, Play, the stock folder browser and the stock resume after a reboot): `sh_load_playlist`,
  the hook on `mclLoadPlayList`, lets stock load the queue, then moves the song at the load index to slot 0, shuffles the rest
  (`shuffle_load`: one array `p`, which is also `sh.orig`; under the payload lock) and sets the play position to 0 with `mclSetPlayPos` (what `mclStartPlayer` reads).
  Every loader goes through it: `start_player` (`0x4e46e0`), `refresh_playqueue` (`0x4df59c`, the stock rebuild after a library change)
  and the boot resume in `networkinit_thread` (`0x506374`, `0x506468`). Explicit Play buttons call `pod_set_in_order` first, which turns
  the flag off, as they did for stock Shuffle. After a reboot the order is not saved: the resumed song plays first and the rest is reshuffled.
- **Shuffle Songs** is the library as the queue, the flag on (`pod_set_mode(MODE_SHUFFLE)`; the stock mode goes to 0 under it), a random first
  song (the payload's xorshift32 draw, started on the drawn row itself when the queue's song there is the same file: `loadSongList` matches by
  file name and CUE start, so duplicates like `01.flac` would otherwise always give the first); the load hook shuffles the rest.
  **Shuffle Albums/Folders** build one queue already in play order, play it with the flag off and keep Repeat all (below).
- **Limits.** More than `SHUFFLE_MAX` (65536) songs, or a failed allocation: the queue is untouched, the flag stays off and the stock one-line message
  box (`dialog/msginfo_dialog`, kind 1, 2 s) says "Too many songs to shuffle" / "Not enough memory". The message is shown from the Queue page's
  Shuffle button (`pod_set_shuffle`) and from Albums/Folders; from the two hooks (a request that stock makes: Play settings, Now Playing's button,
  DLNA, the boot restore; a queue load) the flag goes off silently, because the load also runs for the boot resume and the DLNA thread must not
  open a dialog. The Albums/Folders limits are as before.
- **Gapless.** Stock plays the reordered queue in order, so the next song is known. A preload that is already open (the state word `0xa0abd0` is 1) names the old next
  song: `cancel_preload`, the **one** cancel helper (the reorders here, `pod_queue_insert` below and Queue Clear, [queue](queue.md)), closes it with stock's Gapless setter: `mclSetGaplessMode(0)`
  (`0x5d28ac`: stores the setting byte `0xa0ab89`, and with the state at 1 sends `{mcl-closegapless}` and stores -1 in the state), then `mclSetGaplessMode(old)`. It replaces
  the earlier pair of `mclSetPlayMode` calls (mode 1 closes the preload by the same rule at `0x5d27b8..0x5d2804`), which left the mode word `0xa0abe0` at 1 (Repeat one) for a few
  instructions: `mclNextSong` reads the mode raw, so a track that ended in that window repeated once. In the setter's window only the Gapless byte is 0, and each reader of it goes the
  way the closed state goes anyway [S]: `mclNextSong` `0x5d583c` (byte 0: the queue path), `mclAutoChange` `0x5d632c` (byte 0: no new preload), the `set-gapless` send `0x5d0dd0`
  (inside the preload decision the tick calls, the UI thread). The setter reaches only `send`, no hooked address. After the cancel stock does not preload again in the same song
  (the tick calls `0x5d0ea4` only while the state is 0), so the join into the new next song has a gap. A queue load needs nothing: `mclStartPlayer` restarts the player.

- **Rows inserted into the queue** (Play Next / Play After, `pod_queue_insert(rows, after)` in `patch/shuffle.c`, declared in `home.h`, called by `upnext_add`, [queue](queue.md)):
  under the payload lock it copies the rows into the playing queue with `_deque_push_back` (class stamped from the playing row), rotates them to pos + 1 (or leaves them at the end) with
  row swaps, and, when an order is kept (`sh.orig` with `sh.n` equal to the queue's size), grows it so it stays a permutation of 0..size-1: the new slots take the original positions
  right after the playing song's own (Play Next) or at the end (Play After), in the rows' order, and every original position at or above that moves up by n. Shuffle off then
  restores the original order with the added songs right after the playing song. The new array is allocated first (`calloc` + fill; a failure refuses the insert with nothing changed),
  so the queue, `sh.orig` and the preload are untouched on every refusal; over `SHUFFLE_MAX` songs after the insert is refused too. An order of another size is stale and dropped by
  the insert (a song deleted, then one added, must not look like the saved size). The 0x80000000 done mark of `restore_order` stays free: the entries are below 65536.
  Cancelling an open preload (`at == pos + 1` only) happens under the lock; `mclSetGaplessMode` reaches only `send`. The insert is refused (`POD_INSERT_DLNA`, nothing changed) while
  stock's DLNA renderer service runs (`dmr_serverflag` == 1, checked under the lock): `_deque_push_back` can reallocate the deque's map and the rotation moves rows while the
  UPnP threads read the queue without a lock, the same reason as Clear. Shuffle's own reorders (swaps in place) stay allowed. Insert then Clear, or Clear then insert, then Shuffle off: both
  take this lock; Clear drops the order (the insert grew it first, or there is none to grow), so Shuffle off restores nothing and the queue keeps its songs.

### Locking

DLNA calls `mclSetPlayMode` / `mclLoadPlayList` on its own thread, so every queue reorder and every change of `sh.orig` / `sh.n` runs under one
payload mutex: stock libc's `pthread_mutex_lock` / `pthread_mutex_unlock`, imported through demo's GOT like the cover code's (`tools/pod.py`
`LIBC`; slots `0xa03784` and `0xa03238`), on a zero-filled 32-byte `.scratch` block (PTHREAD_MUTEX_INITIALIZER; `sh_enter` / `sh_leave`). It is
not recursive: it is taken only in `flag_set` (queue size, reorder or restore, `drop_order`, flag file), `pod_queue_insert` (the whole insert, its order growth and the preload cancel; it calls only stock's `mclGetPlayPos`, `deque_*`, `_deque_push_back` whose copy callback is the same stSongInfo copy as `mclLoadPlayList`'s, `calloc` / `free` and the Gapless setter), `flag_only`, `sh_load_playlist` (the whole
function: **stock's `mclLoadPlayList` trampoline, then** `drop_order`, flag, `shuffle_load`) the kill-switch branch of `sh_set_mode`, `sh_clear_queue` (the patched `deque_clear` call in `dmr_serverstart`, `0x5089e4`) and `pod_clear_upnext` (the Queue page's Clear: the preload cancel, then libcstl's `deque_pop_back` per tail record, [queue](queue.md)), each with a
single exit. Queue replacement and reordering exclude each other for the whole operation: stock's loader clears the play-queue deque (`deque_clear`, which
frees its blocks) and refills it, so it must never run while DLNA's thread is in `restore_order` / `shuffle_tail` copying records by the size and indices it
captured. Under the lock run `shuffle_tail` / `shuffle_load` / `restore_order`, `mclSetPlayPos`, the flag file write and stock's loader; the
`mclSetPlayMode` trampoline, the toast and `announce` stay outside it; `cancel_preload` runs inside it for `pod_queue_insert` and `pod_clear_upnext` (the setter reaches only `send`) and after the lock for the reorders.

**Why a plain mutex is enough (static walk, `tools/stock.py sym/callers`):** `mclLoadPlayList` `0x5d1f28` (0xd4 bytes) calls only `deque_clear` (twice),
`deque_assign`, `deque_size` and `_deque_push_back`: 0x10-byte stubs into the shared library, whose element copy/free callbacks are stock's own record
functions (`toolsCopyDeque` and the `stSongInfo` destructor `0x5dabfc`: `free`, `strdup`, `memset`, `deque_*`). It reaches no `mclSetPlayMode`, notify callback, UI code or any
other hooked address, so it cannot take the lock again. The lock is therefore not recursive and no owner/depth is kept. Anything that would put a hooked
call into that path (another hook on a `deque_*` caller used there, say) must revisit this.

**Stock has no play-queue lock.** The mutexes stock's mcl functions take (`mclNextSong`, `mclPrevSong`, `mclStartPlayer`, `mclStop`, `mclGetInfo`, ...)
are one command-mailbox mutex at `0xa0ab20`, held only around clearing two command words (`0xa0ab50` + 8 / 12), never around `deque_at` / `deque_size` of the
queue (`mcl_pdeqplaylist` `0xa0394c`). `mclLoadPlayList` takes no lock at all. Nothing stock-side can be borrowed to exclude readers, so only the payload's own writers
are serialized.

**Stock writers of the play queue** (everything that clears or fills the deque behind `mcl_pdeqplaylist`):

| Writer | Goes through `mclLoadPlayList` (so the lock)? |
|---|---|
| `start_player` `0x4e46e0` (song tap, Play all, stock browser, our `playing_page`) | yes |
| `refresh_playqueue` `0x4df59c` (builds a local deque, loads it, destroys it) | yes |
| `networkinit_thread` boot resume `0x506374`, `0x506468` | yes |
| `dmr_serverstart` `0x5089e4` (`deque_clear` of the queue after `stop_dlna_player`, the DLNA session start/stop path) | yes, covered: the call site is patched to `sh_clear_queue` (below) |
| `init_usersetting` `0x4e0d38` (`deque_clear` at boot, before the DLNA / payload threads run) | no, harmless: single-threaded boot, and `sh.orig` is empty then |
| `autochange_updateplayqueue` `0x4dfa08`, `change_music`, `mclNextSong` / `mclPrevSong` | not writers: they only move the position (`mclSetPlayPos`) |
| `dlnaRenderAddTrackList` / `FetchTrackList`, `loadSongList`, `toolsCopyDeque` | write DLNA's / the page's own deques; the playing queue is only read through `mcl_pdeqplaylist` |
| Queue page Clear (`pod_clear_upnext`, ours; [queue](queue.md)) | yes, covered: under the payload lock it re-reads the position and size, closes an open gapless preload (`cancel_preload`, the setter pinned in `SHUFFLE_PINS`), pops the tail records in place with libcstl's `deque_pop_back` (destructor `0x5dabfc`: `free`, `memset`; records `0..pos` untouched, nothing allocated or copied) and calls `drop_order`; stock's unlocked readers on other threads are the open risk below |
| `player_addplayList` `0x4efdcc` | edits the string fields of the record at the playing position in place (the DLNA add-to-queue action); not a reorder |

**`dmr_serverstart`'s clear (covered).** Pinned call site `CLEAR_SITE` `0x5089e4` (`tools/pod.py`): stock's `lw v0, GOT 0xa0394c` (`0x5089dc`, word `0x8f82aa5c`), `lw t9, GOT deque_clear` (`0x5089e0`, `0x8f99f494`), `jalr t9` (`0x5089e4`, `0x0320f809`) and its delay slot `lw a0, (v0)` (`0x5089e8`, `0x8c440000`) are pinned; the build replaces only the `jalr` with `jal sh_clear_queue` (the delay slot still loads `a0` = the queue; `$t9` is simply unused; stock continues with `b 0x5086fc` and reloads what it needs, as at the `MODE_SITES`). `sh_clear_queue(void *deque)` takes the payload lock, calls stock's `deque_clear(deque)`, calls `drop_order` (the saved order describes a queue that is gone, so the `sh.n` size check is not the only guard) and releases the lock; the kill switch keeps the lock (switched on mid-reorder, the clear still waits). The call cannot re-enter our lock: `deque_clear` runs the deque's element free callback, the deque was created as `stSongInfo`, whose registered destructor `0x5dabfc` calls only `free` and `memset`. Tests: test 46 (words), test 51 (a clear against a reorder paused mid-permutation, the reverse, the kill switch switched on mid-reorder).

**Remaining gap:** Stock readers on other threads take no
lock (the player's own advance is not one of them: `mclAutoChange`, which runs the auto-advance and the gapless preload decision, is the AWTK idle handler `on_wm_idle_status`, i.e. the UI thread, as are the Next / Previous keys; the other threads are DLNA's and the boot thread): `mclStartPlayer` `0x5d5300` / `mclNextSong` `0x5d5800` (`deque_at(queue, pos)`) when DLNA's Next / Previous / Play (`dmr_serverstart`, `dlnaRenderStartPlay`) call them,
the DLNA reporters (`dmrActionPLGetPlayInfo`,
`dmrActionPLReadTrack`, `notifyPlayInfo`, ...), `get_id3info` and the UI can see a record that is mid-copy during `apply_perm` / `restore_order` (a duplicate
or a stale record for a moment; the strings stay owned by one slot, never freed by a reorder), and `player_addplayList` can edit whichever record is at the
position while it moves. No pointer is freed, but there is no consistent snapshot: stock reads a record's path and CUE offset separately, so a track start during a reorder can mix two songs' data or play the wrong track (open, playback correctness). Only a stock lock around all readers could close it; none exists.

### The hooks

Both are PIC-prologue hooks (`j target; nop`, a `$gp`-restoring trampoline resuming at `+12`), pinned by `SHUFFLE_PINS`, falling back to stock for
the kill switch (`/mnt/mmc/m1plus-off` or `/mnt/data/m1plus-off`, checked on every call, no state kept) and doing bounded work (at most `SHUFFLE_MAX`
records moved, two `calloc`s, one small file). Both are reachable at boot (`tools/reach.py`: `mclSetPlayMode <- config_init <- platform_init`,
`mclLoadPlayList <- refresh_playqueue <- autochange_updateplayqueue <- platform_init`, and the resume), which is why they only read the flag file
once and never touch the UI.

- **`mclSetPlayMode`** `0x5d278c` (`sh_set_mode`, trampoline resumes at `0x5d2798`). This is the choke point: every stock path that sets the mode
  calls it and nothing else stores the mode word `0xa0abe0` after `initMclModule` (`0x5d1a6c`, default 3): the More dialog `0x47a54c`, Play settings
  `0x49fc78`, Now Playing's cycle button `0x53b648`, DLNA `responseSetPlayMode` `0x50ed9c` / `dmr_serverstart` `0x50856c`, and the boot restore of
  `[PLAYSET] PLAYMODE` (`config_init` `0x4e596c`, `config_mplayer` `0x4d8730`). A request for **2** means "Shuffle on, stock mode 0" (a flag that is
  already on is left alone and stock is not called, so `config_mplayer`'s re-apply of the displayed mode changes nothing); **any other mode** is
  "Shuffle off" and that stock mode. Two exceptions keep the flag: the Queue page's Repeat (`pod_set_repeat`, the `keep` byte) and the **first call of
  the session**, which is stock's own boot restore: it sets the stock mode from the config and leaves the flag as the file has it (a config that says 2,
  written by stock or by an older build, still turns the flag on). The flag change and the reorder come after stock's function (which also closes a
  preload for mode 1).
- **`mclLoadPlayList`** `0x5d1f28` (`sh_load_playlist`, resumes at `0x5d1f34`), described above.
- The mode is read **raw** (not through `mclGetPlayMode`) by `mclNextSong` `0x5d58fc`, `mclPrevSong` `0x5d5748` and the next-index function `0x5d0edc`,
  all pinned, so the mcl core only ever sees 0, 1 or 3. `mclGetPlayMode` itself is **not** hooked: `change_music` (`0x4e3d7c`, Next / Previous) and
  `autochange_updateplayqueue` (`0x4dfa08`) read it and run stock's Shuffle branches for 2.

### Where the mode is shown

Stock's `jalr mclGetPlayMode` at the sites below became `jal sh_display_mode`, which answers 2 while the flag is on (stock's mode otherwise); pinned
with the `lw t9` that loads it (`MODE_SITES`, test: the 19 words in the build, and stock's picture function and click handler run under emulation):

| Site | What it shows or does |
|---|---|
| Now Playing's mode button `0x5398cc` (picture, `0x539888`) | Shuffle style while the flag is on, also with Repeat all |
| the button's click handler `0x53b62c` | the 4-step cycle starts from what is shown: Shuffle -> Repeat all turns the flag off |
| Play settings `0x49fb90`, `0x49fd04`, `0x49fd58`, `0x49fdac`, `0x49fe04`, `0x49fe7c` | the checked row and the rows' "already set" tests |
| Play More dialog `0x47a3fc` (shown), `0x47a530` (cycle) | the same |
| `config_mplayer` `0x4d8720` | re-applies what is shown: Shuffle on is a no-op request |
| DLNA `dmrActionGetPlayMode` `0x4f014c`, `0x4f0164`, `0x4f017c`, `dmrActionGetRendererStatus` `0x4f09d8`, `0x4f0a30`, `0x4f0a50`, `handlePlayModeResponse` `0x50ecf8`, `notifyPlayMode` `0x50ee34` | remotes see Shuffle |
| payload: the Pod's Shuffle / Repeat rows and mode mark (`patch/ipod.c`) | `pod_play_mode()` |

The lock screen reads no play mode (no `mclGetPlayMode` caller). The Queue page and the Cassette page read stock's own mode (Repeat) and the flag
separately.

## Albums, Folders

- **Albums/Folders build one queue already in play order** and let stock play it sequentially, so no hook on the playback path. Group: albums by name with ASCII case folded (SQLite NOCASE, as the Albums
  list groups; no-album songs one group); folders by path up to the last `/`. Groups in Fisher-Yates
  order; inside an album disc, then track (`getMusicByAlbum` comparator `0x4e9020`), then path, then
  CUE start; inside a folder path, then CUE start. Two heapsorts over a 16-byte index
  `{record, group, position, dir}` (no libc `qsort`; `dir` is a path's folder length, found once per song in
  `group_order` for Shuffle Folders and used by every folder comparison and group boundary, 2048 songs: 26.4 M -> 10.6 M
  payload instructions with 22-byte paths, 59.1 M -> 23.7 M with 52-byte paths; folder equality, file-name order and CUE-start ties are unchanged), then the queue's records are permuted in place
  (cycle-following), so every string stays owned by one slot. Peak memory is what tapping a song in
  Songs uses plus the index (1 MB at the cap; a refused allocation still toasts "Not enough memory" and leaves the queue untouched).
  They play with the flag off (`set_in_order`) and keep Repeat all; Repeat one becomes List play.
- **Play mode** is changed as Play settings does (`0x49fc78`): `mclSetPlayMode(m)`, `notifyPlayMode()`, `dmrSendPlayMode(shown mode)`,
  `write_int_config(m, "PLAYSET", "PLAYMODE")`; nothing is written when the shown mode is already right. Values 0 List play, 1 Repeat one,
  2 Shuffle (the request, mapped by the hook), 3 Repeat all. `set_in_order` (exported as `pod_set_in_order` for the Play buttons of the album page,
  the Songs page, the Podcasts page and the Daily Mix): the flag off, Repeat one -> List play, List play and Repeat all kept.
  `pod_set_mode(MODE_SHUFFLE)` (the Shuffle buttons of the album page, Songs, Daily Mix, the Pod, genre) turns the flag on and puts stock under it
  in List play. The mode stays afterwards (q2-pod restores it with a hook on the queue load; not ported).
- **Limits** (stock one-line message box, nothing played, mode untouched): "Update Local Music first" (empty), "Storage unavailable" (first file
  missing), "Too many songs to shuffle" (Albums/Folders over `SHUFFLE_MAX` 65536, checked before copying), "Not enough memory to shuffle".
  About 12 M payload instructions for Shuffle Albums over 2,048 songs.
- After a reboot Shuffle Songs resumes with the flag on and reshuffles the rest; Albums/Folders resume on the same track and continue in Songs order
  (the album order is not saved).

Pinned: `mclGetPlayMode` `0x5d3628`, `mclSetPlayMode` `0x5d278c` (mode word `0xa0abe0`; closes a gapless preload for modes 1, 2), `mclLoadPlayList` `0x5d1f28`
(position `0xa0abdc`, class `0xa0abd8`), `mclSetPlayPos` `0x5d42d8`, `notifyPlayMode` `0x50ee04`, `dmrSendPlayMode` `0x4f10f0`, `write_int_config`
`0x4d6a2c`, `toolsRandnum` `0x5e0c58`, `time_now_ms` `0x70cf58` (AWTK `uint64_t`, low word in `$v0`).
Now Playing's button cycles `(shown mode+1) % 4` (`0x53b634`, styles at `0x5398cc`). msginfo
context `{int kind; int ms; char text[0x200]; char text2[0x200]}` (`dialog_msginfo_dialog_init`
`0x4786f8`, `0x478884`). Not ported: q2-pod's advanced-playback engine, Next/Previous Album,
the audiobook filter, the multi-disc folder merge, and Shuffle Folder from inside the folder browser
(it needs a second hook).

## Handover

Nothing here has been run on the device. Open gaps, in the order worth checking:

1. **Device checks:** gapless after a reorder (turn Shuffle on / off near the end of a song; the next song starts without a gap and is the one the
   Queue page shows); reboot resume with Shuffle on (the resumed song plays first, the rest is reshuffled, no stock Shuffle behaviour, Next / Previous
   follow the Queue page); DLNA / SyncLink (a remote asking for Shuffle gets the flag; remotes read Shuffle back); Now Playing's button through
   all four steps and with Shuffle + Repeat all from the Queue page; stock lists' playing-row marker (stock pages that map the queue position back to
   the library row would now point at the wrong row in a shuffled queue: only our own pages were checked in emulation).
2. **Silent failures in the hooks:** over 65536 songs or no memory at a stock-made request or a queue load turns the flag off without a message
   (the Queue page's button and the Shuffle page do show one). A message there would need a UI-thread hand-off (a pending notice shown by a page tick).
3. **DLNA's thread vs. stock's load: fixed.** `sh_load_playlist` holds the payload lock across stock's `mclLoadPlayList` (see Locking: it cannot re-enter a
   hook), so a load and a reorder exclude each other; test `interleaving A / B` in `apple_tests` (two saved CPU contexts, a modelled mutex, a pause after N
   `memcpy` or right after stock's loader) and every load path asserts the loader runs with the lock held. `dmr_serverstart`'s own `deque_clear` (`0x5089e4`) is covered too (`sh_clear_queue`, test 51). Only the unlocked stock readers remain (Locking: no free, but a track start during a reorder can mix two songs' path and CUE offset or start the wrong track). `sh.fresh` / `sh.keep` are plain bytes set by the UI thread around a call.
4. **`refresh_playqueue`** (the stock rebuild after the library changed under a playing queue, loaded at position 0 or the last) is treated as a new
   queue: it reshuffles with that position first.
5. The order is not saved; Shuffle off after a size change of the queue (a song deleted from it) cannot restore it. Play Next / Play After keep `orig` in step
   (`pod_queue_insert`, above); no other writer may change the queue's size without `drop_order`.
6. The gapless cancel is one helper (Gapless above); a late Play Next / reorder joins without gapless in that song (device check in [queue](queue.md)).
