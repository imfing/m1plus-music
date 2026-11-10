/* Continue with Next Album (patch/nextalbum.c, docs/modules/nextalbum.md): constants the payload and test/pod/nextalbum.py share.
 * The test parses the #defines in this file, so a change cannot leave the mocks behind.
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 */
#pragma once

#define NA_FILE \
    "/mnt/data/m1plus/playback-next-album" /* "1" = Next Albums, anything else or missing = Off ("2" is reserved for Auto Mix; Settings > Playback > Continue Playing) */
#define NA_TMP "/mnt/data/m1plus/playback-next-album.tmp"

#define NA_OFF 0 /* the modes of na_setting / na_set */
#define NA_ALBUMS 1
int na_setting(void); /* the saved mode: NA_ALBUMS, else NA_OFF (the default) */
int na_set(
    int mode); /* choose NA_OFF or NA_ALBUMS, saved atomically; the mode, or -1 when it is not one or could not be saved */

/* The order an album page was opened from. na_note_albums (called by the Albums page and Cover Flow just before cc_open_album) records the shown album keys,
 * album_open takes the note (na_page_open), ab_play_at arms it (na_arm .. na_disarm) around the load, and the mclLoadPlayList hook (na_on_load) keeps the
 * source for the armed load and drops it for every other one. */
void na_note(const unsigned *keys, unsigned n, unsigned scope,
             void *artist_row); /* keys: the shown order; artist_row copied (NULL: the library) */
void na_note_albums(
    void *albums, const unsigned *order, unsigned n, unsigned scope,
    void *artist_row); /* the keys of the first n shown rows (All Songs and Unknown Album left out), then na_note */
void na_note_drop(void); /* the opener returned: a note album_open did not take is dropped */
void na_page_open(
    unsigned
        key); /* album_open: the note becomes the page's order when it holds that album, else it is dropped; the page's own key */
void na_page_close(void); /* the album page is gone */
void na_arm(void); /* Play / Shuffle / a track: the page's order becomes the source for the load that follows */
void na_disarm(void); /* the play call is over: no load happened = the previous source stays */
void na_on_load(void); /* mclLoadPlayList (hook 14): the armed load keeps the source, any other drops it */
int na_next_key(
    unsigned cur_key,
    unsigned *
        out); /* 1 and the key after cur_key in the source's order; 0 at the end (no wrap) or when cur_key is not in it */
void na_set_cur(unsigned key); /* the album now playing (na_end moves it on after an append) */
unsigned na_cur(void);
int na_active(void); /* 1 while a source is held */
int na_end(
    void); /* hook 26 (mclNextSong's List play end): 1 when the next album's tracks were appended to the queue that just ended, 0 for stock's own end */
