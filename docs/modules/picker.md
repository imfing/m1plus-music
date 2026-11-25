# Add to Playlist picker

**Sources:** `patch/picker.c`, `patch/picker.h` (the add and the copies), `patch/playlists.c` (pick mode),
`patch/songops.c` (`so_add`, `so_song_key`), `patch/rowmenu.c` (`rowmenu_make_glyph`), `patch/playmore.c` (`pm_on_addpl`), `PICKER_PINS` in `tools/pod.py`.
Our own picker replaces the stock one. Add on the Songs page and the album page (`so_add`) opens it,
and so does Add to playlist on Now Playing's More sheet (`picker_open_rec`, [More menu](playmore.md));
the stock `playlist_page` in picker mode is only the fallback.

## Choice: a page, not a sheet

Our Playlists page in list mode, titled "Add to Playlist". A glass sheet (the Playlists "..." card, the Songs Sort card) is for a handful of fixed rows; the picker
lists up to 100 playlists with mosaics and counts, so it needs the scrolling list, the mosaic loader and the row painter the Playlists page already has. One
code path, the same rows the user knows, nothing new to keep in step. The design is the page's: neutral greys, 64 px rows (52 px mosaic, name, count), the
pressed row `#333334`.

- Navbar: Back (glass chevron) and the title "Add to Playlist" (the Songs pill's text, short in all 13 languages; its label is widened to `SG_SELALL_X`, as
  in select mode). The "..." button and Now Playing are hidden and insensitive; the page is always the list (the saved grid / list choice is
  the Playlists page's own and is not written). The playlists after the two pinned rows follow the Playlists page's saved order (`playlists-sort`: Title A–Z by default, or any of its orders); the picker has no card to change it. A playlist that gets songs is stamped as updated (`picker_add(id, name)`, [playlists](playlists.md) "Order").
- Row 0: "New playlist" (the stock key `playlist_create`, the New playlist keyboard's title), a white plus on a dark rounded square (`pl_plus`), no count. A tap opens our keyboard
  (`keyboard_open`, as the Playlists New); its Done creates the playlist (`createPlayListItem`: -1 full and -2 exists say the stock message and leave the picker
  open) and adds to it.
- Row 1: "Favorites" (our own key, the Favorites row of the Extras page, translated in all 13 languages), a white filled star (24 px alpha bitmap made at open by `pl_make_star`, 4 x 4 samples a pixel; the same glyph as the Favorites icon, which the repo draws as a star everywhere, not a heart) on the New row's dark rounded square, no count. A tap adds to Favourites and closes, as a playlist row does. `pl_v()` is 2 in pick mode (the rows before the playlists).
- Rows 2..n: the playlists, the name and "N tracks" once read (the page's loader, one playlist a tick). A tap adds and closes.
- Back, or the system back, closes with nothing added; there is no tap-outside (it is a page). Now Playing is not offered.

## Already there

A row (Favourites or a playlist) that holds every song being added shows the Add Songs page's grey tick (`sg_pdone` in `SG_HANDLE_RGB`,
made by `rowmenu_make_glyph`) where a row's "..." would be (`rowmenu_paint_bmp` at `RM_MORE_RIGHT`). Its texts end where the "..." zone begins
(`grid_tile_t.markw`, `rowmenu_text_end`). A tap on it toasts "Already in Playlist" / "Already in Favorites" and adds nothing; the picker stays.

- **Which songs.** `picker_open` keys the marked rows of its copy with `so_song_key` (path and CUE span, two FNV words: what stock's duplicate check
  compares; the Add Songs page keys a playlist the same way), sorted, each once (`pk_make_keys`). `picker_count` is how many.
  A marked row that is not a song (`REC_TYPE` 8) makes none: the Folders page's folders, playlist files and storages, which
  `batch_add_file` turns into a folder's direct audio files or nothing. Then no row is ticked and the add's message is stock's.
- **Which rows.** The loader's scan of a playlist already reads all its songs (`pl_scan`, for the count). In pick mode it also counts the keys that
  list holds (`picker_in`: a binary search a song, a bit a key so a song the playlist has twice counts once) into `info_t.has`. Favourites (row 1) is
  scanned too: `picker_in_fav` runs the stock query `loadLocalClassList(0xf00a)` (music only, hook 6) and puts the browsing record back. A row
  shows the tick once its scan has run, as its count does; a tap before then adds as before.
- **Some of them.** A tap on a row that holds some adds as before (stock skips the ones there) and toasts "Added N of M songs" (`picker_add`'s
  `have`) instead of the stock message.
- `pl_load` keeps the scans while the database is unchanged; the songs being added do not change while the picker is open, so `has` stays right.

## What it does with a tap

Stock's row handler in picker mode calls `batch_add_file(class, 0xf00b, *pdeq_showlist, *SEL_VEC, playlist id)`
(the id is the row's `REC_DISC`; it skips songs already in the playlist), shows `msg_addplaylistsuccess`
in `dialog/msginfo_dialog` and closes the picker's window. `picker_add` does the same, in the same
order. The prologue of `batch_add_file` and the handler's class, call and 5th-argument words are pinned
(`PICKER_PINS`). Stock returns nothing the handler tests, so its message is always the success one; ours says how many were added when the scan found some of the songs there ("Already there").

**Favourites** is the stock Add button's other choice (`dialog/batchadd_dialog` returns 1): `batch_add_file(g_class_type, 0xf00a, *pdeq_showlist, *SEL_VEC, 0)`, then the message `msg_addfavsuccess` in `dialog/msginfo_dialog`. Stock stays on its page afterwards; ours closes the picker, as for a playlist. With nothing selected stock shows `msg_addfailed` first: ours never opens with an empty selection (`so_add`). `picker_add(PICKER_FAVOURITES, have)` does it on the same copies, with class `0xf00a` and 0 for the id. The words are pinned in `PICKER_PINS`.

**The copies.** The Playlists page reads every playlist to show its count and mosaic (`loadLocalClassList(0xff13)`), and each read replaces `*pdeq_showlist`, the list
the add needs. So `picker_open` copies the list (`cc_copy_list`: the page's `count` rows must be the stock list's, else -1) and the marks (the page's bitset)
when it opens; `picker_add` fills the stock selection vector from the copy of the marks (`so_selection`, as the stock-picker path did) and passes the copy to
`batch_add_file`. The call writes the new ids into the copy's records (stock writes them into the shown list's); the caller reads its list again anyway.

**One record.** `picker_open_rec(class, rec)` is the picker for a record that is in no shown list (the playing row of the queue): the list is a one-row copy
of it (`so_row_deque`) with its one mark, and `*pdeq_showlist` is not read. Everything after the open is the same.

**The browsing record.** Those queries also set the browsing class, `classinfo[0..1]` and the navigation title. The picker saves them at open and puts them back
after every query it runs (`picker_restore`: after each playlist scan, the playlist list, the creating query) and when the page is gone (`picker_release`, from
the page's destroy), so the caller's own restore on its to-foreground (which `so_add` still sets up: `title_save`, `*picker`) finds them as they were, and its
reload of the list uses them. The stock picker's side effects (class `0xf00b`, the saved title) do not happen: stock's page never runs.

**Over our Playlists page.** The Playlists page keeps its state in one struct (`pl`). When the picker opens while the Playlists page exists (Playlists >
a playlist's Songs page > Add, or the Playlists page's own long press sheet > Add to Playlist), the state is copied aside (`calloc`) and `pl` is the picker's; the
page's destroy puts the copy back. A Playlists page still in front is sent to the background first (`pl_on_bg`: its loader stopped, its sheet closed), and its
window's to-foreground and to-background handlers act only for their own window (`ctx` is the window), so the original window's events never touch the
picker's state. Its to-foreground, once the picker has gone, reads it again.

**Over an embedded keyboard.** A page that keeps our keyboard embedded (Search, [keyboard](keyboard.md)) holds the one keyboard, so New playlist's
`keyboard_open` would refuse. `pk_open` sets the embedded keyboard aside (`keyboard_park`) before the page opens and `picker_release` gives it back
(`keyboard_unpark`): the field's text, the layer and the pad's shown state come back; a pinyin composition in progress is dropped.

**Fallback.** `picker_open` returns -1 and `so_add` runs the stock path exactly as before (the selection into the stock vector, `playlist_page` with `PICKER_ADD |
class`) when: the stock list is not the one the marks are of, the copies cannot be made, the window `m1plus_playlists` does not open, the asset lacks a widget,
or a picker is already open. The SD file `/mnt/mmc/m1plus-off` disables the whole payload (then stock's page is the only one).
