# Library list hand-over (`patch/libload.c`)

Every local list (Songs, Albums, Artists, Most Played, Recently Played, Favourites, a playlist's or an album's songs) is read by stock's
`loadLocalClassList(cls)` `0x4ee504`. Payload hook 29 ([payload](payload.md)) removes the copies that function made, and the pages no longer keep a
second copy of a list they have just read.

## Stock

`loadLocalClassList` runs the class's query (`getAllMusic`, `getAllOftenRecord`, ...; Songs and Most Played have no `LIMIT`) into `*tools_pdeq_directory`
(`0xa03964`) and ends, for every class, in one tail at `0x4ee638`:

```
deque_clear(*dst); deque_assign(*dst, *tools_pdeq_directory); deque_clear(*tools_pdeq_directory); return deque_size(*dst);
```

`dst` is `pdeq_showlist` (`0xa045d8`), `pdeq_playlist` (`0xa045d0`, class `0xf00b`) or `0xa05fb4` (the online classes). `deque_assign` copies every
record (88 bytes) and its strings through the stSongInfo copy callback. The preceding list coexists with the query's rows until the tail clears it;
then the query's rows coexist with their copy. libcstl's allocator is plain `malloc` / `free` (`_alloc_allocate` `0x2d680` -> `_alloc_malloc`,
`_alloc_init` empty), so each of them is heap.

## The hook

- **`ll_load`** replaces the prologue. For a local class whose destination is the show list (`LCL_LOCAL`: `0xf001`..`0xf00a`, `0xff01`, `0xff02`,
  `0xff09`, `0xff10`..`0xff14`; proven by the two jump tables, pinned as `LCL_TABLES`) it clears `*pdeq_showlist` first, then runs stock's function
  through `stock_loadclass_trampoline`. Stock clears that list in the tail anyway and no query reads it (the arguments come from the browsing record
  `0xa0c768`), so only the moment of the free moves. The playlists and the online classes are not cleared early.
- **`ll_assign`** replaces the tail's `jalr deque_assign` (`0x4ee650`). It exchanges the two `deque_t` structs (`lib_deque_swap`): the destination owns
  the query's rows, and the row deque is the empty one stock's tail clears next. Both global pointers keep their values. No record is copied.
- `lib_deque_swap` repeats libcstl's `deque_swap` (`0x3ac1c`, pinned by offset and SHA-256 of its 0x148 bytes, `CSTL_SWAP`): 0x14c bytes each way, then
  the two iterators' container pointers (`+0x124`, `+0x140`) set to their own deque. It refuses, changing nothing, unless both deques' container
  pointers point at themselves (true of every initialised deque). The library function is not called: it compares the lists first (`deque_equal`) and
  demo does not import it.
- Stock's code runs unchanged with `/mnt/mmc/m1plus-off` (one `access` per call) and whenever the exchange refuses.
- Boot reachability (`tools/reach.py`): reachable (`onlineDownloadThd`, `home_page_init`). Bounded work: no allocation, thread, timer or file.

Peak record sets while a local show list of N records is read, with M old records: stock `max(M + N, 2N)`, now N (excluding the play queue and page-owned lists).

## Pages

- `lib_take_list(list)` makes a deque of our own that takes the stock list's records and leaves the list empty; a copy (`deque_assign`) only when the
  exchange is refused. `cc_albums` / `cc_songs` (`patch/covercache.c cc_class_copy`) and the Artists page (`patch/artists.c ar_load`) use it, so the
  list is held once, not twice. `*pdeq_showlist` is empty afterwards; a page that shows the stock list checks it (`grid_list_same`: pointer, size,
  first record) and reads it again, as after any other query.
- Lists read for one scan are freed after it: the Albums page's Recently Added / Year scan (`so_stats`), the Artists page's foreground comparison
  (`ar_local_changed`).
- Daily Mix (`patch/dailymix.c dm_ph_copy`) copies its picks from the library `PH_LIB` read while that is still the show list, and reads the library a
  second time only when another query came between; the library is freed once the picks are copied.

## Not changed

- The queries themselves: Most Played and the library are still read whole; Recently Played keeps its stock limit of 100 (Daily Mix looks at the first `DM_*_MAX` rows of each result).
- `loadSongList` / `mclLoadPlayList` copy the shown list into the play queue (stock; the queue and the list are two lists).
- Pages that show the stock list itself (Songs, an album's tracks, the iPod levels, Search's songs) hold it once, as before.

## Validation

`test/pod/libload.py` (Unicorn, built demo): the two edits and every pin; the jump tables against `LCL_LOCAL`; `ll_load` for every class
`0xeff0`..`0xff3f`; the exchange on real 0x14c-byte blocks and its refusals; stock's own tail run from the built demo for both destinations and with the
kill switch; `lib_take_list`. The tail tests follow storage tokens moved by the real MIPS exchange and check the returned count and surviving rows, including repeated 47,000-row hand-overs.
Page behaviour: `albums/layout_tests`, `albums/sort_card_tests`, `artists/artists_tests`, `artists/reread_tests`,
`dailymix/job_tests`, `dailymix/failure_tests`.

Not verified: anything on a device. The emulation models libcstl's deques as lists, so no test measures heap use or runs the real row callback; the
peak figures above are from reading the disassembly. A crash log from the reported large library has not been seen, so that this was its cause is
not proven.
