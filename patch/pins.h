/* The Home pins: albums and playlists pinned at the top of the Home instance of the menu (patch/pins.c, docs/modules/pins.md).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 * The pin and unpin calls read the file /mnt/mmc/.m1plus/home-pins (the card's) fresh, change it and write it back (a new pin joins the end, PIN_MAX at most); they work whether or not a Home
 * menu is alive (a live one shows the change when it is in front again). A pin that would be the seventh shows the toast "Unpin an item first" itself.
 */
#pragma once

#define PINS_OK 0
#define PINS_FULL -1 /* PIN_MAX are pinned already (the toast is shown) */
#define PINS_FAIL \
    -2 /* nothing to pin (empty name, no cover key), the file could not be written, or it could not be read (the toast "Can't update pins"; the file is left alone) */

/* An album (its title is its identity, as Recently Played has it: ASCII case folded, the stock list groups by title alone): `ckey` is cc_album_key of the stock album row (not 0),
 * `path` a track of the album (the way to find the row again; NULL: none). Pinning an album that is pinned changes nothing and answers PINS_OK. */
int pins_pin_album(const char *album, unsigned ckey, const char *path);
/* A stock playlist: its id (REC_DISC, not 0), its name (the stock ids are reused after a delete: a pin is the id and the name; pinning a replacement replaces the stale pin of the same id), and the cover keys of up to `nk` distinct albums of its songs (grid_mosaic_keys; the mosaic of the Playlists page; nk may be 0). */
int pins_pin_playlist(int id, const char *name, const unsigned *keys, unsigned nk);
/* The words of the pin row of an item's "..." card or long press sheet by its state now: "Unpin Playlist" / "Pin Playlist" as translation keys for widget_set_tr_text (from the file). */
const char *pins_label_playlist(int id, const char *name);
/* 1 when the album / playlist is pinned (read from the file). */
int pins_has_album(const char *album);
int pins_has_playlist(int id, const char *name);
/* Removes the pin; 1 when there was one, 0 when not (or when the file could not be written: "Can't update pins", the pin stays). */
int pins_unpin_album(const char *album);
int pins_unpin_playlist(int id, const char *name);
/* Rename Playlist (patch/songs.c): the pin of playlist `id` called `old` takes `name`, in its place, with its cover keys; the Home tile reads it when Home is in front again. 1 when it was renamed; 0 when
 * there is no such pin, or the file cannot be read (nothing said) or written ("Can't update pins", the pin keeps the old name). */
int pins_rename_playlist(int id, const char *old, const char *name);
/* Plays the stock playlist `id` called `name` as the Playlists long press sheet's Play (shuffle 0: in order) or Shuffle (1), Now Playing opens: the Home pin's play without the pin. 0 when it was started,
 * -1 when nothing plays (not in the list, empty, or no list). */
int pins_play_playlist(int id, const char *name, int shuffle);
/* Plays the album as the Albums long press sheet's Play (shuffle 0: in order from the first) or Shuffle (1): the album page's Play pill and Shuffle disc without the page, Now Playing opens. The album is found by
 * `ckey` (cc_album_key of its row), else by title, else by a track `path` (NULL: none). 0 when it was started or could not be told, -1 when the library has no such album (nothing happens). */
int pins_play_album(const char *album, unsigned ckey, const char *path, int shuffle);
/* Adds every track of the album in order to the playing queue (after 0: Play Next; after != 0: Play After) via upnext_add and toasts the outcome. When the library has no such album (or no tracks), toasts
 * "Not found" and returns 0. Otherwise returns upnext_add's status (UPNEXT_*). */
int pins_queue_album(const char *album, unsigned ckey, const char *path, int after);
/* A row of the album sheet (rowmenu_open_album, act RMA_*; the sheet has closed) for an album of the library: Play / Shuffle (pins_play_album, "Can't play" when nothing plays), Pin / Unpin Album,
 * Add to Playlist (every track marked, our picker over the page: picker_open; "Not found" without the album, "Adding Failed" when the picker cannot open), Play Next / Play After (pins_queue_album). */
void pins_album_act(const char *album, unsigned ckey, const char *path, int act);

/* A song (the track row sheet's Pin Song): the stock record of a local file, identified by its path. `rec` is an stSongInfo: its REC_PATH (a file of the card, under PIN_PATH bytes), REC_TITLE (else the file name)
 * and REC_ALBUM (its cover is the album's: cc_album_rep_key, else the record's own key). Pinning a pinned song changes nothing and answers PINS_OK; a seventh pin shows the toast and answers PINS_FULL. */
int pins_pin_song(void *rec);
/* A song is its file's path and, for a track of a CUE image (the tracks share the file), its REC_CUE_START (`cue`: the record's value, 0 or below for none). */
int pins_song_ok(const char *path, int cue); /* 1 when that song can be pinned (a local file path that fits the file) */
int pins_has_song(const char *path, int cue);
int pins_unpin_song(const char *path, int cue);

/* An artist (the Artists page's row, the scoped Albums page's "..."): identity = its name as the Artists page lists it (ASCII case folded, as an album's title), the cover key the artist photo's cache key (ap_key; no photo is the circle placeholder),
 * no path. It is looked for in the artist list the pin was made from (Artists or Album Artists): never dropped because the list shown now lacks it. PINS_FAIL for a blank name or one that does not fit the file. The Home tile is a circle; a tap opens the artist's Albums page, the sheet has Play, Shuffle (all the artist's songs) and Unpin Artist. */
int pins_pin_artist(const char *name);
int pins_has_artist(const char *name);
int pins_unpin_artist(const char *name);

/* The Home menu's long press sheet (Play, Shuffle, Play Next, Play After, Pin Album / Unpin Album) for an album that is not a pin: the Recently Played shelf's tile (patch/recent.c). `ckey` is its cover key, `path` a track of it (""
 * for none). 1 when the sheet opened; 0 when there is none (the pins are not up on the window, the menu is not in front, a sheet is open or the strings do not fit the file). */
int pins_album_sheet(const char *album, unsigned ckey, const char *path);

/* The scroll_view a tile of the Home grid is lifted in (held, maybe dragged), 0 when none: the list gesture hook keeps that list from sliding (patch/scroll.c). */
extern void *pins_lift_sv;
