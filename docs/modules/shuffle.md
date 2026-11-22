# Shuffle

**Sources:** `patch/shuffle.c`, `tools/pod_pins.py` (`SETMODE`, `LOADPL`, `MODE_SITES`,
`SHUFFLE_PINS`).
Shuffle is a payload flag, not stock's mode 2, and owns the queue's locking. Two hooks
(`mclSetPlayMode`, `mclLoadPlayList`) keep stock's mode word at 0, 1 or 3. The Shuffle page
(`ui/m1plus_shuffle.bin`, one Shuffle row in the menu, as in q2-pod's Library) has three rows:
**Shuffle Songs** (the library as the queue, flag on, random first song), **Shuffle Albums**
(albums in random order, each in track order) and **Shuffle Folders** (folders in random order,
each in file-name order). One call `shuffle_play(kind)`, no timer or thread left behind.

Every row takes the stock Songs path with class `0xf001`: `loadLocalClassList`, `loadSongList`
(copies the list, stamps the class), Albums and Folders reorder the queue, the first file is checked
with `access`, then `navigator_to_with_context("playing_page", ...)` starts it.

## Apple-style Shuffle

Stock's mode 2 draws one index from a pool of unplayed songs at each advance. The queue keeps library
order, the Queue page cannot show what plays next, and gapless cannot see the next song. So the flag
(`/mnt/data/m1plus/playback-shuffle`: `1` songs, `2` albums, anything else off; [settings](settings.md)) reorders the
queue itself and stock plays it in order. The Queue page shows the real order and gapless works as
for any list. Shuffle and Repeat are independent: Shuffle plus Repeat all is allowed.

- **Kinds.** `pod_shuffle_kind()` is 0 off, 1 songs, 2 albums; `pod_set_shuffle_kind(kind)` sets it
  (0 when refused, as `pod_set_shuffle`, which keeps meaning off / songs). `pod_play_mode()` shows
  Shuffle for both. `sh.on` holds the kind. A request for stock mode 2 keeps the kind already on.
- **Albums** (`album_shuffle`, the grouping of Shuffle Albums: album NOCASE, `play_cmp` order inside):
  the songs after the playing one (all of a loaded queue after the first) are regrouped, the albums
  in random order, each in album order. The playing song's album comes first, with all its
  remaining songs in album order (also those that sort before the playing track). The permutation
  is composed into `sh.orig`, so Shuffle off restores the original order the same way. It allocates
  an index (16 bytes a song), the new order, the ranks and the apply bitmap, freed on return.
- **Switching kind while on** restores the original order, then shuffles by the new kind. A refusal
  after the restore leaves the queue restored and the flag off.

- **Turning on** (`flag_set(1)`): the songs after the playing one are shuffled in place
  (Fisher-Yates, xorshift32). The playing song and the ones before it stay. `apply_perm` moves whole
  records cycle by cycle, so every string stays owned by one slot. Each slot's original position is
  kept in `sh.orig` (4 bytes a song).
- **Turning off** (`restore_order`): every record goes back to its original slot with no
  allocation, so Shuffle off cannot fail. The play position follows the playing song. Slots before
  the playing song are restored too. A queue whose size changed since the shuffle has no usable
  order and keeps its order; the flag still goes off.
- **A queue about to be replaced is not reordered** (`flag_only`): `set_mode(mode, fresh)` and
  `set_in_order(fresh)` with `fresh` set only change the flag and drop the old order. Used by
  `shuffle_play`, `pod_set_mode_for_queue` / `pod_set_in_order_for_queue` and every path that sets
  the mode and then loads a queue. So an old queue over 65,536 songs does not stop Shuffle for a
  small new one.
- **A queue loaded while it is on** (song tap, Play, the stock folder browser, boot resume):
  `sh_load_playlist` lets stock load the queue, moves the song at the load index to slot 0 and
  shuffles the rest (`shuffle_load`, under the lock; with albums the tapped song's album follows
  in album order, then the other albums). Every loader goes through it, including
  `refresh_playqueue`. After a reboot the order is not saved: the resumed song plays first and the
  rest is reshuffled. Explicit Play buttons and album page track taps call `pod_set_in_order` first, which turns the flag off.
- **Shuffle Songs** draws a random first song (started on the drawn row itself when the queue has the
  same file, since `loadSongList` matches by file name and CUE start). **Shuffle Albums/Folders**
  build one queue already in play order, play it with the flag off and keep Repeat all (Repeat one
  becomes List play). After a reboot they resume on the same track in Songs order.
- **Rows inserted into the queue** (Play Next / Play After, [queue](queue.md)): when an order is kept
  (`sh.orig`, `sh.n` equal to the size), the insert grows it so it stays a permutation. New slots
  take original positions right after the playing song's (Play Next) or at the end (Play After),
  and every original position at or above moves up. The new array is allocated first, so every
  refusal changes nothing. An order of another size is stale and dropped.
- **Limits:** over `SHUFFLE_MAX` (65536) songs or a failed allocation, the queue is untouched, the
  flag stays off and the stock message box says "Too many songs to shuffle" or "Not enough memory".
  From the two hooks (a stock mode request, a queue load, the DLNA thread, the boot restore) the
  flag goes off silently, because those paths must not open a dialog.
- **Gapless.** An open preload names the old next song. `cancel_preload` is the one helper that
  closes it, used by the reorders, `pod_queue_insert`, Clear and the edits ([queue](queue.md)). It calls
  `mclSetGaplessMode(0)` and then `mclSetGaplessMode(old)`. Decision: not a `mclSetPlayMode` pair,
  which leaves the mode word at 1 (Repeat one) for a few instructions and a track ending then
  repeats once. After the cancel stock does not preload again in that song, so the join into the new
  next song has a gap. A queue load needs nothing: `mclStartPlayer` restarts the player.

## Locking

DLNA calls `mclSetPlayMode` / `mclLoadPlayList` on its own thread, so every queue reorder and every
change of `sh.orig` / `sh.n` runs under one payload mutex: stock libc's `pthread_mutex_lock` /
`unlock`, imported through demo's GOT (`LIBC` in `tools/pod.py`), on a zero-filled `.scratch` block
(`sh_enter` / `sh_leave`). It is not recursive. Holders: `flag_set`, `pod_queue_insert`,
`pod_queue_move` / `pod_queue_remove`, `flag_only`, `sh_load_playlist` (stock's loader runs inside
it), the kill-switch branch of `sh_set_mode`, `sh_clear_queue` and `pod_clear_upnext`, each with a
single exit. The `mclSetPlayMode` trampoline, toasts and `announce` stay outside it.

**Why a plain mutex is enough.** `mclLoadPlayList` calls only `deque_clear`, `deque_assign`,
`deque_size` and `_deque_push_back`, whose element callbacks are stock's own record functions
(`free`, `strdup`, `memset`). It reaches no hooked address, so it cannot take the lock again. Any
new hook on a `deque_*` caller used there must revisit this.

**Stock has no play-queue lock.** Its mcl mutex guards only a command mailbox, never the queue, so
nothing stock-side can exclude readers; only our own writers are serialized.

**Stock writers of the play queue:**

| Writer | Covered by the lock? |
|---|---|
| `start_player`, `refresh_playqueue`, boot resume (`networkinit_thread`) | yes: all go through `mclLoadPlayList` |
| `dmr_serverstart`'s `deque_clear` | yes: the call is patched to `sh_clear_queue` (`CLEAR_SITE`, `SHUFFLE_PINS`), which also calls `drop_order` |
| `init_usersetting` `deque_clear` | no, harmless: single-threaded boot, `sh.orig` empty |
| Queue Clear, insert, move, remove (ours) | yes |
| `autochange_updateplayqueue`, `change_music`, `mclNextSong` / `mclPrevSong` | not writers: they only move the position |
| `player_addplayList` | edits strings of the record at the playing position in place; not a reorder |

**Remaining gap.** Stock readers on other threads take no lock: DLNA's Next / Previous / Play and its
reporters, `get_id3info`, and the UI. They can see a record mid-copy during a reorder, so a track
start during a reorder can mix two songs' path and CUE offset or play the wrong track. No pointer
is freed by a reorder. Clear, insert and remove are refused while the DLNA service runs
(`dmr_serverflag`), because they free or reallocate rows. The auto-advance and the Next / Previous keys
run on the UI thread, so they cannot interleave with our UI-thread calls. Only a stock-wide lock
around all readers could close the gap.

## The hooks

Both are PIC-prologue hooks (`j target; nop`, a `$gp`-restoring trampoline), pinned by
`SHUFFLE_PINS`, falling back to stock for the kill switch (checked on every call) and doing bounded
work. Both are boot-reachable (config restore, the resume), so they read the flag file once and
never touch the UI.

- **`mclSetPlayMode`** (`sh_set_mode`) is the choke point: every stock path that sets the mode
  calls it. A request for **2** means "Shuffle on, stock mode 0"; any other mode is "Shuffle off"
  with that stock mode. Two exceptions keep the flag: the Queue page's Repeat (`pod_set_repeat`) and
  the **first call of the session**, stock's own boot restore, which sets the mode from the config
  and leaves the flag as its file has it. The flag change and reorder come after stock's function.
- **`mclLoadPlayList`** (`sh_load_playlist`): described above.
- The mode is read raw by `mclNextSong`, `mclPrevSong` and the next-index function, so the mcl core
  only sees 0, 1 or 3. `mclGetPlayMode` is not hooked; `change_music` and
  `autochange_updateplayqueue` read it and would run stock's Shuffle branches only for 2.

### Where the mode is shown

Stock's `jalr mclGetPlayMode` at these sites became `jal sh_display_mode`, which answers 2 while the
flag is on (`MODE_SITES`):

| Site | Shows or does |
|---|---|
| Now Playing's mode button picture and click handler | Shuffle style while the flag is on, also with Repeat all; the 4-step cycle starts from what is shown (Shuffle -> Repeat all turns the flag off) |
| Play settings, Play More dialog | the checked row and the "already set" tests |
| `config_mplayer` | re-applies what is shown: Shuffle on is a no-op request |
| DLNA play-mode replies and `notifyPlayMode` | remotes see Shuffle |
| payload: the Pod's Shuffle / Repeat rows (`pod_play_mode()`) | the same |

The lock screen reads no play mode. The Queue page and the Cassette page read stock's mode (Repeat)
and the flag separately.

## Albums, Folders

- Albums/Folders build one queue in play order and let stock play it sequentially, so no playback
  hook. Albums group by name with ASCII case folded (as the Albums list groups; no-album songs one
  group), folders by path up to the last `/`. Groups go in Fisher-Yates order. Inside an album: disc,
  track, path, CUE start. Inside a folder: path, CUE start. Two heapsorts over a 16-byte index
  (no libc `qsort`), then the records are permuted in place, so every string stays owned by one
  slot. Peak memory is what a song tap in Songs uses plus the index (1 MB at the cap).
- **Play mode** is set as Play settings does: `mclSetPlayMode(m)`, `notifyPlayMode()`,
  `dmrSendPlayMode(shown mode)`, `write_int_config(m, "PLAYSET", "PLAYMODE")`; nothing when the mode is
  already right. `pod_set_in_order` (Play buttons and album track taps; Songs, Podcasts, Daily Mix Play)
  turns the flag off and maps Repeat one to List play. `pod_set_mode(MODE_SHUFFLE)` (Shuffle buttons)
  turns the flag on over List play. The mode stays afterwards.
- **Errors** (stock message box, nothing played, mode untouched): "Update Library first" (empty),
  "File not found" / "Storage unavailable" (`so_missing`, first file missing), "Too many songs to
  shuffle" (over `SHUFFLE_MAX`), "Not enough memory to shuffle".

Not ported from q2-pod: its advanced-playback engine, Next/Previous Album, the audiobook filter, the
multi-disc folder merge, and Shuffle Folder from inside the folder browser.

## Limits

- Stock pages that map the queue position back to a library row would point at the wrong row in a
  shuffled queue. Only our own pages follow the real order.
- The order is not saved across a reboot. Shuffle off after the queue's size changed (a song deleted)
  cannot restore it. Play Next / Play After and the single-row edits keep `orig` in step; no other
  writer may change the queue's size without `drop_order`.
- `refresh_playqueue` (the stock rebuild after a library change) counts as a new queue and
  reshuffles with that position first.
- A late Play Next or reorder joins without gapless in that song.
