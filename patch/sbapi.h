/* Navidrome / Subsonic data layer: the calls, the cache on the card and the two workers (patch/sbapi.c, patch/sbparse.c, patch/sbdl.c; docs/modules/subsonic.md has the design).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE). Navidrome support began as a pull request by Gaurav Mishra (its patch/subsonic.c, MIT, removed in the rebuild); the HTTP, token, JSON and MD5 code under
 * this layer is that work (patch/sbnet.c), and the queue ABI was cross-checked against shivaluma/shanling-m1plus-navidrome (MIT, Copyright 2026 shivaluma and contributors).
 *
 * The pages never touch the network. They READ lists from the cache (sba_albums, sba_album_tracks, ...), ASK for a refresh (sba_sync, sba_fetch_album, ...) and then only read the
 * status record (sba_gen / sba_state) from their own timer, re-reading a list when sba_gen changed: the model patch/pcnet.h uses (AWTK is not thread safe). Two detached
 * pthreads exist: ONE metadata worker (a request at a time from a small queue: lists, covers, star, search) and ONE download worker (patch/sbdl.c, one file at a time). Neither
 * runs while nothing was asked and neither outlives its requests; a worker never calls an AWTK or stock function and never touches a page's memory: it writes the cache files
 * (atomically: .tmp, fsync, rename) and then moves sba_gen. Lists come back as heap copies the caller frees (sba_free_*), so a page's lists never change under it.
 *
 * Offline: a list read never needs the network. A call with no cached answer returns 0 rows, and sba_state says SBA_ST_NONE (nothing asked), SBA_ST_LOAD (asked), SBA_ST_FAIL (the
 * last ask failed: its code is an SBA_* below) or SBA_ST_OK. A request made without Wi-Fi fails at once with SBA_NOWIFI and changes nothing.
 * Ids are the server's opaque strings (Navidrome: UUID / 22 characters); they are never parsed, only escaped into a URL.
 */
#pragma once

#define SBA_ID \
    64 /* bytes of a server id, the NUL included (Navidrome's are 22..36); a row with a longer id is dropped */
#define SBA_TEXT 192 /* bytes of a title, name or artist kept (cut at a UTF-8 boundary) */
#define SBA_SUFFIX 12
#define SBA_URL 1024
#define SBA_ALBUM_PAGE \
    250 /* albums asked per page of getAlbumList2: a response is about 0.8 KB an album, and one over SBN_RESPONSE_MAX (4 MiB) fails whole; divides SBA_MAX_ALBUMS */
#define SBA_SONG_PAGE \
    100 /* songs asked per page of search3: about 1.4 KB a song on the demo server (500 were 644 KB and never arrived); divides SBA_MAX_TRACKS */
#define SBA_MAX_ALBUMS 20000 /* a library with more albums or artists is cut here (sba_summary says so) */
#define SBA_MAX_TRACKS 50000 /* the Songs list's cap (paged search3) */
#define SBA_DIR \
    "/mnt/mmc/.m1plus/subsonic" /* the cache: albums.idx, artists.idx, playlists.idx, starred.idx (tracks), songs.idx, search.idx, search-al.idx, search-ar.idx, al/<id>.idx, ar/<id>.idx, pl/<id>.idx, covers/, sync.txt, bg.txt, songs.part; dl.idx is the download manifest (sbdl.c), not cache */
#define SBA_COVER_DIR \
    SBA_DIR \
    "/covers" /* Navidrome covers only (never Cover Flow's own folder): <hash of the coverArt id>-168.jpg, the Cover Flow cache file format; an empty file = the server has no art */
#define SBA_CONF \
    "/mnt/mmc/.m1plus/subsonic.conf" /* one line "url|user|secret" (no newline): the secret is the salt and the token md5(password + salt) as 48 hex digits (patch/sbnet.h sbn_auth_make), never the password; mode 0600 where the card allows */
#define SBA_SYNC_MAX_AGE 900u /* seconds: Sync is "due" when the last one is older than this (15 minutes) */
#define SBA_MUSIC_DIR \
    "/mnt/mmc/Subsonic" /* downloaded files: <id-prefix>-<name>.<suffix>, a .part file until complete */
#define SBA_CA \
    "/etc/m1plus-cacert.pem" /* the CA bundle HTTPS verifies with; HTTP is allowed (a LAN server) and unencrypted */
#define SBA_RESERVE_KB 32768u /* a download leaves the card this much free (the PR's 32 MiB) */
#define SBA_CACHE_RESERVE_KB 4096u /* the cache files keep this much free */
#define SBA_QMAX 8 /* metadata requests waiting; the next is SBA_QFULL */
#define SBA_DLMAX 32 /* downloads waiting or running */

/* Results: what a request returns at once (the guards) and what sba_state reports for a finished one. The page shows the words. */
enum {
    SBA_OK = 0,
    SBA_NOCONF, /* no server saved */
    SBA_NOWIFI, /* the Wi-Fi is not connected (stock get_wifisignal) */
    SBA_NOCLOCK, /* the clock was never set: a certificate would not verify (HTTPS only) */
    SBA_NOCERT, /* SBA_CA is missing or unreadable (HTTPS only) */
    SBA_CERT, /* the server's certificate was refused */
    SBA_NET, /* no connection, no answer, a time-out */
    SBA_AUTH, /* Subsonic error 40 / 41: wrong user or password */
    SBA_NOTFOUND, /* Subsonic error 70, or HTTP 404 */
    SBA_HTTP, /* another HTTP error */
    SBA_PARSE, /* the answer is not a Subsonic response (a web page, a proxy's error) or carries another Subsonic error */
    SBA_STORAGE, /* no card, or a cache file could not be written */
    SBA_MEM, /* no memory, or no thread */
    SBA_QFULL, /* the request queue is full */
    SBA_CARDFULL, /* a download or the cache would keep less than its reserve free */
    SBA_NOTAUDIO, /* a download: the answer is a web page or text, not the file */
    SBA_WRITE, /* a download: the card refused a write, a sync or a rename */
    SBA_CANCELLED /* stopped by sba_cancel / sba_dl_cancel (never shown) */
};

/* ---- the rows: one struct per kind; strings are fixed arrays so a row is a plain value (a page copies the rows it keeps) ---- */

typedef struct {
    char id[SBA_ID];
    char title[SBA_TEXT];
    char artist[SBA_TEXT];
    char album[SBA_TEXT];
    char album_id[SBA_ID]; /* "" for a track the server lists without an album */
    char cover[SBA_ID]; /* the coverArt id (getCoverArt); "" = none */
    char suffix[SBA_SUFFIX]; /* the file's own suffix: flac, mp3, dsf ... (original, lower case) */
    unsigned seconds;
    unsigned track;
    unsigned disc;
    unsigned year;
    unsigned size; /* bytes (0 unknown; the stock 32-bit file calls cannot hold more than 2 GiB) */
    unsigned bitrate; /* kbit/s */
    unsigned sample_rate; /* Hz, 0 unknown */
    unsigned bit_depth; /* 0 unknown */
    unsigned created; /* seconds since the epoch, 0 unknown */
    unsigned char starred; /* in the server's favourites (getStarred2, star / unstar) */
} sba_track_t;

typedef struct {
    char id[SBA_ID];
    char name[SBA_TEXT];
    char artist[SBA_TEXT];
    char artist_id[SBA_ID];
    char cover[SBA_ID];
    unsigned year; /* 0 unknown */
    unsigned songs; /* the track count the server states */
    unsigned seconds;
    unsigned created;
    unsigned char starred;
} sba_album_t;

typedef struct {
    char id[SBA_ID];
    char name[SBA_TEXT];
    char cover[SBA_ID]; /* the artist picture's coverArt id; "" none */
    unsigned albums;
    unsigned char starred;
} sba_artist_t;

typedef struct {
    char id[SBA_ID];
    char name[SBA_TEXT];
    char cover[SBA_ID]; /* the playlist's own coverArt; "" none (the page then makes a mosaic of its tracks' covers) */
    unsigned songs;
    unsigned seconds;
} sba_playlist_t;

/* A list read from the cache: n rows in v (heap; NULL when n is 0). The row order is the server's (albums: alphabeticalByName; artists: the server's index order; tracks: disc then
 * track for an album, the playlist's own order, the Songs list's server order); the page sorts what it shows. */
typedef struct {
    int n;
    sba_track_t *v;
} sba_tracks_t;
typedef struct {
    int n;
    sba_album_t *v;
} sba_albums_t;
typedef struct {
    int n;
    sba_artist_t *v;
} sba_artists_t;
typedef struct {
    int n;
    sba_playlist_t *v;
} sba_playlists_t;

void sba_free_tracks(sba_tracks_t *l);
void sba_free_albums(sba_albums_t *l);
void sba_free_artists(sba_artists_t *l);
void sba_free_playlists(sba_playlists_t *l);

/* ---- the server (UI thread) ---- */

/* The saved server: url ("https://host[:port][/base]", no /rest), user and the login secret (the salt and token made from the password at Sign In; the password itself is not kept, in the file or in memory). sba_configured: all three are set. sba_host: the url without scheme and path, for the Server row (a
 * static buffer; "" when none). The setters validate (a scheme, a host, each text under its cap) and write the file atomically: SBA_OK, SBA_STORAGE, or SBA_PARSE for a refused value;
 * the Server page edits one field at a time. sba_conf_clear is Sign Out: the conf, the whole cache (not the downloaded music) and every queued request go. */
int sba_configured(void);
const char *sba_host(void);
const char *sba_user(void);
int sba_password_saved(
    void); /* a login secret is saved (the Server row shows dots; there is no password text to show) */
const char *sba_url(
    void); /* the saved address as the Server page edits it (a static buffer; "" when none; the password is never given out) */
int sba_conf_url_set(const char *url);
int sba_conf_user_set(const char *user);
int sba_conf_password_set(const char *password);
int sba_conf_clear(void);
void sba_retire_old(
    void); /* once per boot, card in: deletes the pull request's old index, artwork folder and view file if present (the conf and downloads stay) */

/* The conditions to start (UI thread): a server saved, the Wi-Fi connected, the clock set and the CA bundle there for an https address. SBA_OK or the first failing SBA_*. */
int sba_guard(void);

/* ---- the status record (UI thread; the pages' timers read these, they never block) ---- */

enum { SBA_ST_NONE = 0, SBA_ST_LOAD, SBA_ST_OK, SBA_ST_FAIL };
enum {
    SBA_K_PING, /* `id` ignored */
    SBA_K_SYNC, /* albums, artists, playlists and starred lists; `id` ignored */
    SBA_K_ALBUM, /* id = the album */
    SBA_K_ARTIST, /* id = the artist (its albums) */
    SBA_K_PLAYLIST, /* id = the playlist */
    SBA_K_SONGS, /* the Songs list (paged search3); `id` ignored */
    SBA_K_SEARCH, /* the last search3; `id` ignored */
    SBA_K_COVER, /* id = the coverArt id */
    SBA_K_STAR /* id = the track */
};

unsigned sba_gen(
    void); /* changes whenever a list's status or cache file does (a request finished, a page of rows arrived, a worker ended); a cover request or file does not move it */
unsigned sba_cover_gen(
    void); /* changes whenever a cover request finished (the file, or the empty marker, is there; or it failed): for a page that waits for a cover and has no timer of its own */
int sba_state(int kind, const char *id, int *code); /* SBA_ST_*; *code (NULL ok) is the SBA_* of a failed request */
void sba_cancel(
    void); /* stop the metadata worker and drop what is queued (a page's destroy): never waits for the thread */

/* "Synced N songs . time": the totals of the last finished SBA_K_SYNC (songs = the sum of the albums' track counts), when it finished (epoch seconds) and whether the library hit
 * SBA_MAX_ALBUMS. 0 when there has been none. */
int sba_summary(unsigned *songs, unsigned *when, int *truncated);

/* ---- asking (UI thread; each returns at once: SBA_OK = queued, else the guard that refused it; the answer is a cache file and a moved sba_gen) ---- */

int sba_conf_check(
    int field,
    const char *
        text); /* SBA_OK or SBA_PARSE: whether the setters would take `text` as the address (field 0), the user (1) or the password (2); saves nothing */
int sba_ping_try(
    const char *url, const char *user,
    const char *
        password); /* a ping with this login, which is NOT saved (the conf and the cache stay as they are); an empty password uses the saved one. The answers are the server's ping (SBA_OK, SBA_AUTH, SBA_NET ...); save with the setters when it succeeds */
unsigned sba_trial_id(
    void); /* the request id of the trial ping the last successful sba_ping_try queued (never 0 once there was one). Each trial carries its own login and id, so a second sign-in is a second request and the first one's answer is for the first */
int sba_trial_state(unsigned id,
                    int *code); /* SBA_ST_* of that trial ping (like sba_state); SBA_ST_NONE for another or no id */
int sba_sync_due(
    void); /* 1 when there is no finished sync, or the last is older than SBA_SYNC_MAX_AGE (or the clock was never set) */
int sba_sync_auto(
    void); /* the root page's open: when the cache is fresh nothing is queued except what phase 2 still has to do (sba_bg_kick), else sba_sync() */
int sba_sync(
    void); /* Sync Now: getAlbumList2 (alphabeticalByName, SBA_ALBUM_PAGE a call), getArtists, getPlaylists, getStarred2: replaces albums.idx, artists.idx, playlists.idx, starred.idx whole; phase 2 (below) follows on the same worker */

/* Phase 2, the background fill (docs/modules/subsonic.md "Background fill"): after a sync the worker, with no request waiting, (A) pages the whole library's songs (search3, SBA_SONG_PAGE a call, the Songs
 * pager's request) into songs.part, makes it songs.idx and derives al/<id>.idx for every album whose songs are all there, then (B) fetches every album's cover at SBA_COVER_PX and (C) every artist's picture the same way (a coverArt id each, getArtists). One request or a few dozen rows of
 * file work at a time; a request a page makes goes first (a transfer of phase 2 is cut off for it), a download pauses it, an error backs off (SBA_BG_FAILS in a row stop it for the run). bg.txt in SBA_DIR is the
 * cursor (the library signature, the stage, the album the derive reached); songs.part and the cover files are the rest of it, so a stop, a lost Wi-Fi, a sleep or a reboot resumes without refetching. It starts again
 * when the cache is cleared or the library's signature (songs, seconds, albums, newest album) changed, or after SBA_BG_MAX_AGE. */
#define SBA_BG_FAILS 5 /* errors in a row that end the run */
#define SBA_BG_MAX_AGE \
    (7u * 86400u) /* a finished fill is repeated after a week even when the signature is the same (retags) */
void sba_bg_kick(
    void); /* UI thread: with Wi-Fi up and something left to do, start (or resume) phase 2; nothing otherwise. The root page's open calls it through sba_sync_auto */
int sba_bg_progress(
    unsigned *done,
    unsigned *
        total); /* 0 = idle (or paused), 1 = songs (done of total), 2 = covers, 3 = artist pictures (done of total); read by the root page's status line */
unsigned sba_bg_gen(void); /* moves with every step of phase 2 (the root page re-reads its status line on it) */
int sba_fetch_album(const char *id); /* getAlbum: al/<id>.idx */
int sba_fetch_artist(const char *id); /* getArtist: ar/<id>.idx (the artist's albums) */
int sba_fetch_playlist(const char *id); /* getPlaylist: pl/<id>.idx */
int sba_fetch_songs(
    unsigned
        offset); /* search3 with an empty query, SBA_SONG_PAGE songs from offset, appended to songs.idx; offset 0 starts the list again */
int sba_search(
    const char *term); /* search3 (up to 20 artists, albums and songs): search.idx, replaced by the next search */
int sba_search_is(
    const char *
        term); /* 1 when the search3 that finished last (an answer or a failure) was for this term: the page ignores the state of an older one while a newer one is out */
int sba_star(
    const sba_track_t *t,
    int on); /* star.view / unstar.view for a track (its row, so starred.idx can gain it): the heart flips at once (a small overlay every track list read applies, sba_star_pending) and the metadata worker edits the files (starred.idx, the row in songs.idx, search.idx and al/<album>.idx; the UI thread never writes the cache) before it asks the server, and puts them back if the server refuses (SBA_ST_FAIL). SBA_QFULL when the overlay is full. sba_state(SBA_K_STAR, t->id) */
void sba_hearts(
    sba_track_t *v,
    int n); /* the starred flags of rows that did not come from a cache list (the download manifest's): starred.idx says, then the stars in flight, as every list read here does. Page side only */
int sba_star_pending(const char *id); /* -1 when no star of that id is in flight, else the flag it will have (0 / 1) */

/* A cover: getCoverArt?id=<cover>&size=SBA_COVER_PX stored in SBA_COVER_DIR under a name derived from the coverArt id (sba_cover_path). Navidrome covers have their OWN folder and
 * are never mixed with Cover Flow's files for local albums; the file is the same kind (a JPEG or PNG the loaders read as a cache file: file://<path> through cc_decode). Skipped when the
 * file is there (SBA_OK at once; a cover the server does not have is an empty file: SBA_NOTFOUND at once); the answer is checked (JPEG or PNG signature, SBA_COVER_MAX; a WebP answer is Navidrome's stand-in for an artist or album with no art: an empty file, SBA_NOTFOUND); a request already
 * queued is not repeated. One at a time on the metadata worker, behind lists, and never more than SBA_QMAX - 2 at once. sba_state(SBA_K_COVER, cover). */
#define SBA_COVER_MAX (2u << 20)
#define SBA_COVER_PX 168
int sba_cover(const char *cover);
int sba_cover_path(char *out, unsigned cap,
                   const char *cover); /* the file's path (0), -1 for an empty id or a small buffer */
int sba_cover_have(
    const char *
        cover); /* 1 the file is there with a picture, -1 an empty marker file (the server has no art), 0 nothing yet */
unsigned sba_cover_hash(
    const char *
        path); /* the 8 hex digits a cover file's name starts with (a path sba_cover_path made): a key for sba_cover_hash_path; 0 if the name is not one */
int sba_cover_hash_path(
    unsigned hash, char *out,
    unsigned cap); /* the path of the cover file with that hash (0), -1 for a small buffer; the file may not exist */
/* The file a page shows for a coverArt id (an album's, artist's or playlist's): 1 and the path in `path` when it is there; 0 when it was asked for (or is on its way: look again shortly); -1 for no art
 * (an empty id, an empty marker file, a failed or refused ask). */
int sba_cover_get(const char *cover, char *path, unsigned cap);
/* The same for a TRACK: its ALBUM's cover file (the one phase 2 fetched for the album, found by album_id in albcov.idx, which every sync writes with albums.idx), so the songs of an album, Now Playing, the
 * queue and a playlist's mosaic share the album's one file instead of fetching one file per song (a Navidrome song with embedded art has its own coverArt "mf-..."). The track's own coverArt `own` is used
 * only when the album is unknown (no album_id, not in albcov.idx, no albcov.idx yet) or has no coverArt. ask 0 only looks at the card (Get Info): 1 or not. Page (UI) thread only. */
int sba_track_cover(const char *album_id, const char *own, char *path, unsigned cap, int ask);

/* ---- reading the cache (UI thread; heap copies, the caller frees; an empty list when nothing is cached). Each returns the row count, -1 for no memory ---- */

int sba_albums(sba_albums_t *out); /* every album */
int sba_artists(sba_artists_t *out);
int sba_playlists(sba_playlists_t *out);
int sba_starred_tracks(sba_tracks_t *out); /* the Favorites list (getStarred2 songs) */
int sba_album_tracks(const char *id, sba_tracks_t *out); /* disc, then track */
int sba_artist_albums(const char *id, sba_albums_t *out);
int sba_playlist_tracks(const char *id, sba_tracks_t *out);
int sba_songs(sba_tracks_t *out); /* what sba_fetch_songs has appended so far */
int sba_songs_more(
    void); /* 1 while the last page was full and SBA_MAX_TRACKS is not reached: ask for the next offset */
int sba_search_tracks(sba_tracks_t *out);
int sba_search_albums(sba_albums_t *out);
int sba_search_artists(sba_artists_t *out);
int sba_songs_window(
    unsigned offset, int n,
    sba_track_t *
        out); /* rows [offset, offset + n) of songs.idx without loading the file (out holds n rows); the rows read, 0 past the end. The Songs list reads it a few dozen rows at a time (sba_songs would need 820 bytes a row, 41 MB at the cap) */
int sba_songs_cached(void); /* rows in songs.idx (0 none): the next sba_fetch_songs offset */

/* ---- playing ---- */

/* The stream address of a track: stream.view?id=..&format=raw (no transcoding) with the saved salt and token; there is no password to appear in it. 0, or -1 for no server or a too small
 * buffer. The address lives only in the queue record sbsrc builds; it is never saved. */
int sba_stream_url(char *out, unsigned cap, const char *id);
/* The queue record's file name for a track: "<title>.<suffix>" (the server's own suffix, so the stock player picks the decoder), cut to cap, unsafe characters replaced. */
int sba_track_filename(char *out, unsigned cap, const sba_track_t *t);
/* The suffix is DSD (dsf, dff, dsd, dop): never streamed (the stock player misidentifies it); the track plays from the card after a download. */
int sba_is_dsd(const char *suffix);
/* The cover file of the track the player is on (its queue record's synthetic id -> the coverArt id -> the cache file), NULL when it is not a Navidrome track or has no file yet.
 * Replaces the PR's sb_cover_file; Now Playing calls it as before (patch/nowplaying.c). */
const char *sba_now_cover(void *track);
/* The same lookup for any queue record, with the answer sba_now_cover folds into NULL: the cover file's path in `path` and 1 when it is there; 0 when it was asked for (or is on its way: look
 * again shortly); -1 for a record that is not a server track, has no cover, whose ask failed or was refused (the placeholder). The record's REC_ID is the key; never its REC_PATH. */
int sba_rec_cover(void *track, char *path, unsigned cap);
/* A queue record's synthetic REC_ID (always <= -2, as the PR makes it: -(FNV-1a of the track id & 0x3fffffff) - 2, bumped on a collision) and the reverse: the track id a queued record
 * stands for, "" when it is not ours. The map holds the last queue sbsrc built. */
#define SBA_QUEUE_MAX 64
const char *sba_rec_track(int rec_id);
unsigned
sba_rec_size(int rec_id); /* the server's size in bytes of the track a queue record stands for, 0 unknown or not ours */
/* What the map keeps of the track a queue record stands for: id, cover, album_id, suffix and size (the other fields zero; the cached row, found by album_id, has the rest). 1 found, 0 not ours. */
int sba_rec_row(int rec_id, sba_track_t *out);
void sba_queue_note(
    const sba_track_t *t, int n,
    int *rec_id); /* sbsrc tells the map the queue it is starting (replaces the last one); fills rec_id[0..n) */
/* After sba_queue_note: the queue was built (the old map is dropped) / it could not be (the old map is back). */
void sba_queue_keep(void);
void sba_queue_undo(void);
#define SBA_MAP_MAX \
    1024 /* entries the map holds in all (a play notes SBA_QUEUE_MAX; Play Next / Play After add one each) */
int sba_queue_add(
    const sba_track_t *
        t); /* one more queued track (Play Next / Play After): its synthetic id (the one it already has when the map knows the track), 0 when the map is full or there is no memory */

/* ---- downloads (patch/sbdl.c: the PR's resume, stall and free-space rules; one file at a time; the queue is in memory, the files and the manifest dl.idx are on the card) ---- */

enum { SBA_DL_NONE = 0, SBA_DL_WAIT, SBA_DL_ACTIVE, SBA_DL_DONE, SBA_DL_FAILED };

int sba_dl_add(
    const sba_track_t *
        t); /* queue t: SBA_OK, a guard (SBA_NOWIFI ...), SBA_QFULL, SBA_CARDFULL; a track already on the card is SBA_OK and DONE */
void sba_dl_cancel(
    const char *
        id); /* a waiting (or failed) download leaves the queue; the active one stops (sbn_download then removes its .part, as the PR did; a network fault keeps it for the next try) */
void sba_dl_cancel_all(void);
int sba_dl_state(const char *id, int *code, unsigned *got,
                 unsigned *total); /* SBA_DL_*; code: the SBA_* of a failure; got / total in bytes (total 0 unknown) */
int sba_dl_failure(
    int *
        status); /* UI thread: the SBA_* of the newest download failure nobody has been told of (0 none; one older than 30 s is dropped), *status its HTTP status for SBA_HTTP. Taking it clears it */
unsigned sba_dl_gen(void); /* moves with every state change and about every 2 % of the active file */
int sba_dl_busy(void); /* the download worker runs */
/* The path of a finished download of track id (a stat), 1 when there is one. A file deleted by hand is dropped from the manifest. */
int sba_dl_path(const char *id, char *path, unsigned cap);
int sba_dl_delete(const char *id); /* the file and its manifest row: 0 gone or never there, -1 could not be removed */
int sba_downloaded(
    sba_tracks_t *
        out); /* every finished download (dl.idx holds the track's whole row, so Downloaded works offline); rows whose file was deleted by hand are dropped */

/* Between sbdl.c and sbapi.c (sbapi.c provides the first, sbdl.c the second):
 * sba_net_open copies the saved login (url, user, secret; the caller's buffers, so a Server-page edit mid-download cannot dangle) and makes sure sbn_init has run; SBA_OK or SBA_NOCONF.
 * sba_dl_xfer is the transfer-info hook for the download sink: the hook sbapi.c gives sbn_init must call it first and return its result (0 for any sink that is not the download's;
 * non-zero stops the transfer). */
int sba_net_open(char *base, unsigned bcap, char *user, unsigned ucap, char *auth, unsigned acap);
int sba_dl_xfer(void *sink, long long total, long long now, long long up_total, long long up_now);

/* ---- pure parsers (no network, no files; test/pod/subsonic.py calls them like rd_playlist) ---- */

/* json: a Subsonic response of n bytes. Each returns the rows parsed (at most max), or -1 for a body that is not a Subsonic "ok" response (*err, NULL ok: SBA_AUTH, SBA_NOTFOUND or
 * SBA_PARSE). Missing fields are "" or 0; overlong text is cut safely; a row without an id is skipped. */
int sba_parse_tracks(
    const char *json, unsigned n, sba_track_t *out, int max,
    int *
        err); /* getAlbum, getPlaylist, search3 song[], getStarred2 song[] (a getAlbum's songs inherit its album id, cover and year when they omit them) */
int sba_parse_albums(const char *json, unsigned n, sba_album_t *out, int max,
                     int *err); /* getAlbumList2, getArtist's album[], search3 and getStarred2 album[] */
int sba_parse_artists(const char *json, unsigned n, sba_artist_t *out, int max,
                      int *err); /* getArtists (index[].artist[] flattened), search3 and getStarred2 artist[] */
int sba_parse_playlists(const char *json, unsigned n, sba_playlist_t *out, int max, int *err); /* getPlaylists */
int sba_parse_ping(
    const char *json, unsigned n,
    int *
        err); /* ping / any call: 0 for a complete ok response, else -1 with *err (SBA_AUTH for error 40 / 41, SBA_NOTFOUND for 70, else SBA_PARSE) */
