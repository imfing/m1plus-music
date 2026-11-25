/* The Add to Playlist picker: our own page in place of the stock playlist picker (docs/modules/picker.md).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 * The page is the Playlists page (patch/playlists.c) in pick mode; this file holds what the add needs: a copy of the list and the marks made when the picker opened,
 * and the stock batch_add_file called as the stock picker's row handler (@0x53d300) calls it.
 */
#pragma once

/* Opens the picker over the page that owns the stock list in *pdeq_showlist (count rows, marks in the bitset sel): the list is copied (the picker's own reads
 * of the playlists replace *pdeq_showlist) and so are the marks. 1: open; -1: not opened (the stock picker is the caller's fallback). The browsing class,
 * classinfo[0..1] and the navigation title the picker's stock queries change are put back when it closes. */
int picker_open(int cls, unsigned count, const unsigned char *sel);

/* The picker for one record that is in no shown list (Now Playing's Add to playlist: the playing row of the queue): the list is a one-row copy of rec, marked.
 * 1: open; -1: not opened. *pdeq_showlist is not read; the browsing record is put back as for picker_open. */
int picker_open_rec(int cls, void *rec);

/* picker_add's argument for the Favourites row (a playlist id is never negative). */
#define PICKER_FAVOURITES (-1)

/* The playlist's songs (or Favourites): batch_add_file on the copy and the marks, then the stock message, or "Added N of M songs" where have (picker_in of the playlist,
 * 0 when not read) of the M were there already. A playlist (not Favourites, whose `name` is unused) is stamped as updated (patch/plmeta.c). Once per picker. Playlists page only. */
void picker_add(int playlist, int have, const char *name);

/* How many songs the picker adds (the marked rows, a song marked twice once); 0 with no picker. */
unsigned picker_count(void);

/* How many of the songs being added the stock song list `songs` holds (by so_song_key: path and CUE span, as stock's duplicate check). 0 with no picker. Playlists page
 * only: its scan of each playlist, so the row of a playlist that holds them all shows the tick (docs/modules/picker.md "Already there"). */
int picker_in(void *songs);

/* The same for Favourites: its stock query (loadLocalClassList(0xf00a), into *pdeq_showlist), then the browsing record put back. */
int picker_in_fav(void);

/* The browsing record as it was when the picker opened (after each stock query the picker runs). No-op when no picker is open. Playlists page only. */
void picker_restore(void);

/* The picker's page is gone: the record put back, the copies freed. Playlists page only. */
void picker_release(void);
