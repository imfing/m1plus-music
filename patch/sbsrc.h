/* The Navidrome library source (patch/sbsrc.c; docs/modules/subsonic.md "The seam"): records for the pages, the stock queue for a play, the row extras and the row-menu actions.
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * Records (stSongInfo, see patch/libsrc.h): REC_PATH "nd://<server id>", REC_ID synthetic <= -3 (a hash of the id; -2 stays ID_ALL_SONGS; the queue records of a play carry sba_queue_note's ids, <= -2, below), REC_TITLE / REC_ALBUM / REC_ARTIST the texts,
 * REC_TRACK / REC_DISC / REC_YEAR / REC_TIME_CREATE the numbers, REC_TYPE 8 for a track and 4 for an album, artist, playlist or All Songs row; REC_NAME and the other strings are NULL
 * (cc_str reads them as ""). One more string, at +0x28, is the row's own data (tab separated, a leading letter t / a / r / p for the kind): a track's length, file suffix, favourite flag,
 * coverArt id and album id, an album's cover, artist id, track count, length and favourite flag, an artist's or playlist's cover and counts. rec_id / cover / seconds / row / act / play read it,
 * so a record needs nothing else to be played or acted on, even when it was copied.
 *
 * The queue records a play builds are not these: their REC_PATH is the stream address (or the local file) and their REC_ID the synthetic id sba_queue_note gives, so the stock player and
 * Now Playing work on them. The playing marker is therefore sbs_playing(rec_id), never a REC_PATH comparison.
 */
#pragma once
#include "libsrc.h"
#include "sbapi.h"

#define SBS_SONGS_MAX \
    10000 /* rows of the Songs list held as records (about 3.4 MB with 36 character ids); songs.idx may hold more, the list stops here and is then complete */

extern const lib_src_t
    lib_nd; /* the Navidrome source; lib_navidrome() (patch/libsrc.h) hands it out while a server is saved */

/* The words (translated, valid until the next call) for an SBA_* failure of a download (sbs_message) or of a request, a sync or a ping (sbs_request_message); status is the HTTP status for SBA_HTTP (else 0). */
const char *sbs_message(int code, int status);
/* The same words for a request, a sync or a ping that failed: SBA_NET reads "Can't connect to the server" (sbs_message's "Download interrupted" is a download's). */
const char *sbs_request_message(int code, int status);
/* 1 when the stock player is on the Navidrome track with this server id (a streamed or a downloaded file): the playing marker of a page with a Navidrome source. */
int sbs_playing(const char *id);
void *sbs_playlist_scan(
    const lib_src_t *s,
    void *
        rec); /* a playlist row's tracks like src->list, but a cached playlist is not asked for again (the Playlists page's scan of all of them) */
int sbs_playing_server(
    void); /* 1 when the player is on a Navidrome track streaming from the server (a downloaded file does not count) */
/* The full track a record stands for (Get Info, a download, a star): the record's own data, completed from the album's cache file when that has the track (sizes, bit rate). 1 for a track record, else 0. */
int sbs_track(void *rec, sba_track_t *out);
/* A cover file of the source by key (the 8 hex digits of its name, sba_cover_hash): "file://<path>" in out (80 bytes) when the file is there with a picture, else NULL. grid_t.url for a page whose tiles hold such keys. */
const char *sbs_cover_url(char *out, unsigned key);
/* The cover keys of a list of tracks for a mosaic (the Playlists page, a playlist's header): the first four distinct cover files among the first PL_SCAN tracks, as sbs_cover_url keys, into key (4). src->cover is
 * asked for each track's album (the files that are missing are fetched). *miss (NULL ok) is set when a cover was asked for and is not there yet. The number of keys. */
int sbs_mosaic_keys(const lib_src_t *src, void *list, unsigned *key, int *miss);
