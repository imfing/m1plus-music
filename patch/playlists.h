/* The Playlists page (patch/playlists.c, docs/modules/playlists.md). */
#pragma once
#include "libsrc.h"

/* The Playlists page over a library source: the grid (mosaics of the tracks' covers via src->cover, "N tracks") from src->list(LS_PLAYLISTS, NULL), a tap on a playlist opens its page
 * (songs_open_src_in, the Songs page of its tracks) or, if that does not open, plays it in order through so_play_src. Read-only for a non-stock source: no list-plus button (New Playlist, Import, Export, Delete Playlists,
 * Clean Up). A change of src->gen() reads again. src NULL or &lib_stock is playlists_open (today's page). 0 once up, < 0 where the window did not open. */
int playlists_open_src(const lib_src_t *src);