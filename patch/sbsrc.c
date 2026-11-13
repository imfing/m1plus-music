/* The Navidrome library source (patch/sbsrc.h, patch/libsrc.h; docs/modules/subsonic.md "The seam" and "Data and cache"): stock-shaped records from the cache files of patch/sbapi.c, the stock
 * queue a play builds (the PR's: stream addresses, a downloaded file as its local path, DSD only from the card, 64 tracks), the row extras and the row-menu actions.
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE). The queue records are the pull request's by Gaurav Mishra (its page, patch/subsonic.c, MIT, since removed; sb_play_click).
 *
 * Nothing here is a hook or a thread, and the one timer (the keep-awake tick) runs on the UI thread: every member runs from the page that holds the source, on the UI thread. A list read returns what the cache holds now and kicks the request
 * that would complete it (patch/sbapi.c answers with a moved sba_gen, which the page's timer sees through gen()); a request is not repeated every time the page reads again (nl_may_ask).
 *
 * Memory. A record is the stock stSongInfo (0x58 bytes) and the stock deque copies each string it holds (a malloc chunk apiece), so a row costs about 90 bytes for the record, three or four
 * chunks for path, title, album and artist, and one for the row's own data (REC_META). That is ~350 bytes a row with 36 character ids (measured, test/pod/sbsrc.py): 50,000 tracks would be 17 MB, so the Songs list is the first
 * SBS_SONGS_MAX rows of songs.idx, read 32 rows at a time (sba_songs_window; sba_songs would hold the whole file, 820 bytes a row).
 */
#include "offsets.inc"
#include "stock.h"
#include "common.h"
#include "covercache.h"
#include "home.h" /* KILL_SD */
#include "i18n.h"
#include "songops.h"
#include "libsrc.h"
#include "sbnet.h"
#include "sbapi.h"
#include "sbsrc.h"
#include "shot.h"
#include "fnv.h"

#define P(r, off) (*(char **)((char *)(r) + (off)))
#define REC_ALBUMARTIST 0x24
#define REC_RESERVED_A 0x1c
#define REC_RESERVED_B 0x20
#define NL_CHUNK 32 /* songs.idx rows read at a time */
#define NL_ASKS 4 /* album requests one artist's songs read starts (the request queue holds SBA_QMAX) */
#define NL_ARTIST_TRACKS 5000
#define NL_PATH 336 /* a downloaded file's path (sbdl.c SBD_PATH) */
#define NL_META 320
#define NL_RING 16
#define NL_RETRY_MS 10000u
#define NL_FULL_MS 1500u /* a request the full queue refused is made again after this */

static struct {
    unsigned songs_at, ring_n, awake_until,
        stream_at; /* awake_until: the keep-awake timer's grace after a queue; stream_at: the active remote-stream session */
    unsigned awake; /* its timer handle (0 none) */
    char msg[48]; /* sbs_message's "Server error 503" */
    unsigned due,
        epoch; /* due: when a request that did not make its list appear may be made again (0 none); epoch: moves then, so the pages read again (nd_gen) */
    int dsd_row,
        tries; /* dsd_row: the list row the last play answered -2 for; tries: the confirm's button relabel timer */
    char sc_id[SBA_ID]; /* the scrobble's track: the server track the player was on at the last tick ("" none) */
    char sleep_id[SBA_ID]; /* stream that armed the thermal sleep guard; a different track begins a fresh session */
    unsigned sc_ms, sc_need,
        sc_at; /* how long it has played, how long counts as a play (ms), when the last tick saw it playing */
    int sc_run, sc_sent; /* it was playing at the last tick; the play was reported */
    int dlq; /* the rows at the top of the last LS_DOWNLOADED list that are downloads still to come */
    struct {
        unsigned key, at;
    } ring[NL_RING];
} nl __attribute__((section(".scratch")));

/* ---------------------------------------------------------------------------
 * Small helpers
 */
static unsigned nl_fnv(const char *a, const char *b) { return m1_fnv(m1_fnv(FNV_SEED, a), b) | 1u; }

static void nl_copy(char *out, unsigned cap, const char *s) {
    unsigned n = strlen(s);
    if (!cap) return;
    if (n >= cap) n = cap - 1;
    memcpy(out, s, n);
    out[n] = 0;
}

/* The synthetic REC_ID of a list record: never -1 (the Unknown Album row) or -2 (ID_ALL_SONGS). */
static int nl_rid(const char *id) { return -(int)((nl_fnv(id, "") & 0x3fffffffu) + 3u); }

/* The nth tab separated field of a record's data (0 = the kind letter) into out; its length. */
static int nl_field(const char *m, int n, char *out, unsigned cap) {
    unsigned i = 0;
    while (n-- > 0) {
        m = strchr(m, '\t');
        if (!m) {
            if (cap) out[0] = 0;
            return 0;
        }
        ++m;
    }
    while (m[i] && m[i] != '\t' && i + 1 < cap) out[i] = m[i], ++i;
    if (cap) out[i] = 0;
    return (int)i;
}

static unsigned nl_num(const char *m, int n) {
    char b[16];
    nl_field(m, n, b, sizeof b);
    return (unsigned)atoi(b);
}

static const char *nl_meta(void *rec) { return cc_str(rec, REC_META); }

/* A page that waits for a list reads it again at `when` (the gen moves then, nd_gen): without it a failed or refused request would never be made again, because nothing else moves the gen. */
static void nl_later(unsigned when) {
    if (!when) when = 1;
    if (!nl.due || (int)(when - nl.due) < 0) nl.due = when;
}

/* May a request for (tag, id) be started now? have: the cache already answers. A request made earlier in this run is not repeated for a list that is there (the refresh happened); one that
 * was asked for and has not made the list appear is retried after NL_RETRY_MS (a failure moves sba_gen, which makes the page read again at once; nl_ask then has the pages read again later). */
static int nl_may_ask(const char *tag, const char *id, int have) {
    unsigned key = nl_fnv(tag, id), now = (unsigned)time_now_ms(), i;
    for (i = 0; i < NL_RING; ++i)
        if (nl.ring[i].key == key) {
            if (have || now - nl.ring[i].at < NL_RETRY_MS) return 0;
            nl.ring[i].at = now;
            return 1;
        }
    i = nl.ring_n++ % NL_RING;
    nl.ring[i].key = key, nl.ring[i].at = now;
    return 1;
}

static void nl_ask_sync(void) {
    if (sba_state(SBA_K_SYNC, "", (int *)0) != SBA_ST_LOAD && sba_sync_due() && nl_may_ask("sync", "", 0))
        sba_sync_auto();
}

/* The request for (tag, id) was refused by the queue or the guard: it is asked for again at the next read (a full queue, a second and a half later), or 10 s on when there is no Wi-Fi or card. */
static void nl_refused(const char *tag, const char *id, int rc) {
    unsigned key = nl_fnv(tag, id), now = (unsigned)time_now_ms(), i;
    if (rc != SBA_QFULL) {
        nl_later(now + NL_RETRY_MS);
        return;
    }
    for (i = 0; i < NL_RING; ++i)
        if (nl.ring[i].key == key) nl.ring[i].key = 0;
    nl_later(now + NL_FULL_MS);
}

static void nl_ask(int kind, const char *tag, const char *id, int have) {
    int rc, st = id[0] ? sba_state(kind, id, (int *)0) : SBA_ST_LOAD;
    if (st == SBA_ST_LOAD) return;
    if (!nl_may_ask(tag, id, have)) {
        if (!have && st != SBA_ST_OK)
            nl_later(
                (unsigned)time_now_ms() +
                NL_RETRY_MS); /* (asked lately, failed, and the list is not there: a read after the pause asks again; an answer with no rows is final) */
        return;
    }
    if (kind == SBA_K_ALBUM)
        rc = sba_fetch_album(id);
    else if (kind == SBA_K_ARTIST)
        rc = sba_fetch_artist(id);
    else
        rc = sba_fetch_playlist(id);
    if (rc != SBA_OK && !have) nl_refused(tag, id, rc);
}

/* ---------------------------------------------------------------------------
 * Records
 */
typedef struct {
    const char *id, *title, *artist, *album, *meta;
    int rid, type;
    unsigned year, track, disc, created;
} nl_rec_t;

static void *nl_new(void) {
    void *q = _create_deque("stSongInfo");
    if (q) deque_init(q);
    return q;
}

/* The list, or NULL (destroyed) when it holds nothing. */
static void *nl_done(void *q) {
    if (q && !deque_size(q)) {
        deque_destroy(q);
        return (void *)0;
    }
    return q;
}

static int nl_push(void *q, const nl_rec_t *r) {
    unsigned rec[REC_SIZE / 4], n = deque_size(q);
    char path[SBA_ID + 8];
    memset(rec, 0, sizeof rec);
    snprintf(path, sizeof path, "nd://%s", r->id);
    I(rec, REC_ID) = r->rid;
    P(rec, REC_PATH) = path;
    P(rec, REC_TITLE) = (char *)r->title;
    P(rec, REC_ALBUM) = (char *)r->album;
    P(rec, REC_ARTIST) = (char *)r->artist;
    P(rec, REC_META) = (char *)r->meta;
    I(rec, REC_YEAR) = (int)r->year;
    I(rec, REC_TYPE) = r->type;
    I(rec, REC_TRACK) = (int)r->track;
    I(rec, REC_DISC) = (int)r->disc;
    I(rec, REC_TIME_CREATE) = (int)r->created;
    _deque_push_back(q, rec); /* the stock copy: the record, then every string */
    return deque_size(q) > n;
}

static int nl_push_track(void *q, const sba_track_t *t) {
    char meta[NL_META];
    nl_rec_t r;
    snprintf(meta, sizeof meta, "t\t%u\t%s\t%u\t%s\t%s", t->seconds, t->suffix, t->starred ? 1u : 0u, t->cover,
             t->album_id);
    memset(&r, 0, sizeof r);
    r.id = t->id, r.title = t->title, r.artist = t->artist, r.album = t->album, r.meta = meta;
    r.rid = nl_rid(t->id), r.type = 8;
    r.year = t->year, r.track = t->track, r.disc = t->disc, r.created = t->created;
    return nl_push(q, &r);
}

static int nl_push_album(void *q, const sba_album_t *a) {
    char meta[NL_META];
    nl_rec_t r;
    snprintf(meta, sizeof meta, "a\t%s\t%s\t%u\t%u\t%u", a->cover, a->artist_id, a->songs, a->seconds,
             a->starred ? 1u : 0u);
    memset(&r, 0, sizeof r);
    r.id = a->id, r.title = a->name, r.album = a->name, r.artist = a->artist, r.meta = meta;
    r.rid = nl_rid(a->id), r.type = 4, r.year = a->year, r.created = a->created;
    return nl_push(q, &r);
}

static int nl_push_artist(void *q, const sba_artist_t *a) {
    char meta[NL_META];
    nl_rec_t r;
    snprintf(meta, sizeof meta, "r\t%s\t%u", a->cover, a->albums);
    memset(&r, 0, sizeof r);
    r.id = a->id, r.title = a->name, r.artist = a->name, r.meta = meta;
    r.rid = nl_rid(a->id), r.type = 4;
    return nl_push(q, &r);
}

static int nl_push_playlist(void *q, const sba_playlist_t *p) {
    char meta[NL_META];
    nl_rec_t r;
    snprintf(meta, sizeof meta, "p\t%s\t%u\t%u", p->cover, p->songs, p->seconds);
    memset(&r, 0, sizeof r);
    r.id = p->id, r.title = p->name, r.meta = meta;
    r.rid = nl_rid(p->id), r.type = 4;
    return nl_push(q, &r);
}

static const char *nd_rec_id(const lib_src_t *s, void *rec) {
    const char *path = rec ? cc_str(rec, REC_PATH) : "";
    (void)s;
    return path[0] == 'n' && path[1] == 'd' && path[2] == ':' && path[3] == '/' && path[4] == '/' ? path + 5 : "";
}

/* ---------------------------------------------------------------------------
 * Lists
 */
static void *nl_tracks(const sba_track_t *v, int n) {
    void *q = nl_new();
    int i;
    for (i = 0; q && i < n; ++i)
        if (!nl_push_track(q, &v[i])) break;
    return nl_done(q);
}

/* The Songs list: the first SBS_SONGS_MAX rows of songs.idx, a window at a time; the next page is asked for while the file says there is one. */
static void nl_ask_songs(unsigned cached) {
    unsigned now = (unsigned)time_now_ms();
    int st = sba_state(SBA_K_SONGS, "", (int *)0);
    if (st == SBA_ST_LOAD || cached >= SBS_SONGS_MAX) return;
    if (cached ? !sba_songs_more() : st == SBA_ST_OK) return; /* complete, or the server lists none */
    if (st == SBA_ST_FAIL && now - nl.songs_at < NL_RETRY_MS) {
        nl_later(nl.songs_at + NL_RETRY_MS);
        return;
    }
    nl.songs_at = now;
    sba_fetch_songs(cached);
}

static void *nl_songs(void) {
    unsigned cached = (unsigned)sba_songs_cached(), want, off = 0;
    sba_track_t *buf;
    void *q;
    nl_ask_songs(cached);
    want = cached < SBS_SONGS_MAX ? cached : SBS_SONGS_MAX;
    if (!want) return (void *)0;
    buf = calloc(NL_CHUNK, sizeof *buf);
    q = buf ? nl_new() : (void *)0;
    while (q && off < want) {
        int take = (int)(want - off < NL_CHUNK ? want - off : NL_CHUNK), got = sba_songs_window(off, take, buf), i;
        if (got <= 0) break;
        for (i = 0; i < got; ++i)
            if (!nl_push_track(q, &buf[i])) {
                off = want;
                break;
            }
        off += (unsigned)got;
    }
    free(buf);
    return nl_done(q);
}

static void *nl_album_tracks(const char *id) {
    sba_tracks_t t;
    void *q;
    int n = sba_album_tracks(id, &t);
    nl_ask(SBA_K_ALBUM, "al", id, n > 0);
    q = nl_tracks(t.v, t.n);
    sba_free_tracks(&t);
    return q;
}

/* An artist's songs: the tracks of its albums that are cached, in the albums' order; the albums that are not are asked for (a few at a time). */
static void *nl_artist_tracks(const char *id) {
    sba_albums_t al;
    void *q;
    int n = sba_artist_albums(id, &al), i, asks = 0;
    nl_ask(SBA_K_ARTIST, "ar", id, n > 0);
    q = nl_new();
    for (i = 0; q && i < al.n; ++i) {
        sba_tracks_t t;
        int j, tn = sba_album_tracks(al.v[i].id, &t);
        if (tn <= 0 && asks < NL_ASKS && sba_state(SBA_K_ALBUM, al.v[i].id, (int *)0) != SBA_ST_LOAD &&
            nl_may_ask("al", al.v[i].id, 0) && sba_fetch_album(al.v[i].id) == SBA_OK)
            ++asks;
        for (j = 0; j < t.n && (int)deque_size(q) < NL_ARTIST_TRACKS; ++j)
            if (!nl_push_track(q, &t.v[j])) break;
        sba_free_tracks(&t);
    }
    sba_free_albums(&al);
    return nl_done(q);
}

static void *nl_albums(const char *artist_id, const char *artist_name) {
    sba_albums_t a;
    void *q = nl_new();
    int n, i;
    if (artist_id) {
        n = sba_artist_albums(artist_id, &a);
        nl_ask(SBA_K_ARTIST, "ar", artist_id, n > 0);
    } else {
        n = sba_albums(&a);
        nl_ask_sync();
    }
    for (i = 0; q && i < a.n; ++i)
        if (!nl_push_album(q, &a.v[i])) break;
    if (q && artist_id && deque_size(q)) { /* the stock All songs row, last */
        nl_rec_t r;
        memset(&r, 0, sizeof r);
        r.id = artist_id, r.title = "", r.artist = artist_name, r.meta = "a", r.rid = ID_ALL_SONGS, r.type = 4;
        nl_push(q, &r);
    }
    sba_free_albums(&a);
    return nl_done(q);
}

static void *nl_artists(void) {
    sba_artists_t a;
    void *q = nl_new();
    int i;
    sba_artists(&a);
    nl_ask_sync();
    for (i = 0; q && i < a.n; ++i)
        if (!nl_push_artist(q, &a.v[i])) break;
    sba_free_artists(&a);
    return nl_done(q);
}

static void *nl_playlists(void) {
    sba_playlists_t p;
    void *q = nl_new();
    int i;
    sba_playlists(&p);
    nl_ask_sync();
    for (i = 0; q && i < p.n; ++i)
        if (!nl_push_playlist(q, &p.v[i])) break;
    sba_free_playlists(&p);
    return nl_done(q);
}

/* quiet: the Playlists page's scan of every playlist for its mosaic and count: a playlist already cached is not refreshed by it (the refresh belongs to opening that playlist; the 16-entry ring
 * of nl_may_ask would forget it with more playlists than that and the scan would ask for all of them on every page open); one that is not cached is still asked for. */
static void *nl_playlist_tracks(const char *id, int quiet) {
    sba_tracks_t t;
    void *q;
    int n = sba_playlist_tracks(id, &t);
    if (!(quiet && n > 0)) nl_ask(SBA_K_PLAYLIST, "pl", id, n > 0);
    q = nl_tracks(t.v, t.n);
    sba_free_tracks(&t);
    return q;
}

void *sbs_playlist_scan(const lib_src_t *s, void *rec) {
    const char *id = rec ? nd_rec_id(s, rec) : "";
    return id[0] ? nl_playlist_tracks(id, 1) : (void *)0;
}

static void *nd_list(const lib_src_t *s, int which, void *scope) {
    const char *id = scope ? nd_rec_id(s, scope) : "";
    void *q = (void *)0;
    sba_tracks_t t;
    if (scope && !id[0]) return (void *)0;
    switch (which) {
    case LS_ALBUMS:
        return nl_albums(scope ? id : (const char *)0, scope ? cc_str(scope, REC_TITLE) : "");
    case LS_ARTISTS:
        return scope ? (void *)0 : nl_artists();
    case LS_SONGS:
        if (!scope) return nl_songs();
        return I(scope, REC_ID) == ID_ALL_SONGS ? nl_artist_tracks(id) : nl_album_tracks(id);
    case LS_PLAYLISTS:
        return scope ? nl_playlist_tracks(id, 0) : nl_playlists();
    case LS_FAVORITES:
        if (scope) return (void *)0;
        sba_starred_tracks(&t);
        nl_ask_sync();
        q = nl_tracks(t.v, t.n);
        sba_free_tracks(&t);
        return q;
    case LS_SEARCH_ARTISTS: {
        sba_artists_t a;
        int i;
        if (scope) return (void *)0;
        sba_search_artists(&a);
        q = nl_new();
        for (i = 0; q && i < a.n; ++i)
            if (!nl_push_artist(q, &a.v[i])) break;
        sba_free_artists(&a);
        return nl_done(q);
    }
    case LS_SEARCH_ALBUMS: {
        sba_albums_t a;
        int i;
        if (scope) return (void *)0;
        sba_search_albums(&a);
        q = nl_new();
        for (i = 0; q && i < a.n; ++i)
            if (!nl_push_album(q, &a.v[i])) break;
        sba_free_albums(&a);
        return nl_done(q);
    }
    case LS_SEARCH_SONGS:
        if (scope) return (void *)0;
        sba_search_tracks(&t);
        q = nl_tracks(t.v, t.n);
        sba_free_tracks(&t);
        return q;
    case LS_DOWNLOADED: { /* the downloads still to come (the page's "Downloading" section: nd_dl_rows tells how many), then the finished ones */
        sba_tracks_t w;
        int i;
        if (scope) return (void *)0;
        nl.dlq = 0;
        sba_dl_queue(&w);
        sba_hearts(w.v, w.n);
        sba_downloaded(&t); /* the manifest: no network, works offline */
        sba_hearts(t.v, t.n); /* (the manifest's flag is the day of the download's) */
        q = w.n || t.n ? nl_new() : (void *)0;
        for (i = 0; q && i < w.n; ++i) {
            if (!nl_push_track(q, &w.v[i])) break;
            ++nl.dlq;
        }
        for (i = 0; q && i < t.n; ++i)
            if (!nl_push_track(q, &t.v[i])) break;
        sba_free_tracks(&w);
        sba_free_tracks(&t);
        return nl_done(q);
    }
    }
    return (void *)0;
}

/* ---------------------------------------------------------------------------
 * A record back to a track
 */
static void nl_from_rec(void *rec, sba_track_t *t) {
    const char *m = nl_meta(rec);
    memset(t, 0, sizeof *t);
    nl_copy(t->id, sizeof t->id, nd_rec_id((const lib_src_t *)0, rec));
    nl_copy(t->title, sizeof t->title, cc_str(rec, REC_TITLE));
    nl_copy(t->artist, sizeof t->artist, cc_str(rec, REC_ARTIST));
    nl_copy(t->album, sizeof t->album, cc_str(rec, REC_ALBUM));
    t->seconds = nl_num(m, 1);
    nl_field(m, 2, t->suffix, sizeof t->suffix);
    t->starred = (unsigned char)(nl_num(m, 3) != 0);
    nl_field(m, 4, t->cover, sizeof t->cover);
    nl_field(m, 5, t->album_id, sizeof t->album_id);
    t->track = (unsigned)I(rec, REC_TRACK), t->disc = (unsigned)I(rec, REC_DISC);
    t->year = (unsigned)I(rec, REC_YEAR), t->created = (unsigned)I(rec, REC_TIME_CREATE);
}

/* A queue record's track (REC_PATH a stream address or the local file, REC_ID in the queue map): what the map kept, the texts and numbers of the record. */
static int nl_from_queue(void *rec, sba_track_t *t) {
    if (!sba_rec_row(I(rec, REC_ID), t)) return 0;
    nl_copy(t->title, sizeof t->title, cc_str(rec, REC_TITLE));
    nl_copy(t->artist, sizeof t->artist, cc_str(rec, REC_ARTIST));
    nl_copy(t->album, sizeof t->album, cc_str(rec, REC_ALBUM));
    t->track = (unsigned)I(rec, REC_TRACK), t->disc = (unsigned)I(rec, REC_DISC), t->year = (unsigned)I(rec, REC_YEAR);
    return 1;
}

int sbs_track(void *rec, sba_track_t *out) {
    sba_tracks_t l;
    int i, found = 0, queued;
    l.n = 0, l.v = (sba_track_t *)0;
    if (!rec || I(rec, REC_TYPE) != 8) return 0;
    queued = !nd_rec_id((const lib_src_t *)0, rec)[0];
    if (queued ? !nl_from_queue(rec, out) : (nl_from_rec(rec, out), !out->id[0])) return 0;
    if (out->album_id[0] &&
        sba_album_tracks(out->album_id, &l) > 0) { /* the cached row has the sizes and the current favourite flag */
        for (i = 0; i < l.n; ++i)
            if (!strcmp(l.v[i].id, out->id)) {
                memcpy(out, &l.v[i], sizeof *out);
                found = 1;
                break;
            }
    }
    sba_free_tracks(&l);
    if (queued && !found &&
        sba_starred_tracks(&l) > 0) { /* no album row (a track listed without an album): the Favorites list says */
        for (i = 0; i < l.n; ++i)
            if (!strcmp(l.v[i].id, out->id)) {
                out->starred = 1;
                break;
            }
    }
    sba_free_tracks(&l);
    if ((i = sba_star_pending(out->id)) >= 0) out->starred = (unsigned char)i; /* a star the worker has not finished */
    return 1;
}

const char *sbs_cover_url(char *out, unsigned key) {
    memcpy(out, "file://", 8);
    return key && !sba_cover_hash_path(key, out + 7, 73) && cc_file_size(out + 7) > 0 ? out : (const char *)0;
}

int sbs_mosaic_keys(const lib_src_t *src, void *list, unsigned *key, int *miss) {
    unsigned tried[16];
    char path[80];
    int n = list ? (int)deque_size(list) : 0, k, i, ntried = 0, nk = 0, asked = 0;
    for (k = 0; k < n && k < PL_SCAN && nk < 4; ++k) {
        void *r = deque_at(list, (unsigned)k);
        unsigned own = cc_album_key(r), file;
        int c;
        for (i = 0; i < ntried && tried[i] != own; ++i) {
        }
        if (i < ntried) continue; /* a later track of an album looked at */
        if (ntried < 16) tried[ntried++] = own;
        c = src->cover(src, r, own, path, sizeof path);
        if (c == 0) asked = 1;
        file = c == 1 ? sba_cover_hash(path) : 0;
        if (!file) continue;
        for (i = 0; i < nk && key[i] != file; ++i) {
        }
        if (i == nk) key[nk++] = file; /* (albums that share a cover file fill one quadrant) */
    }
    if (miss) *miss = asked;
    return nk;
}

int sbs_playing_server(void) {
    void *rec = cc_playing();
    return rec && sba_rec_track(I(rec, REC_ID))[0] && sbn_http_url(P(rec, REC_PATH));
}

/* The player is on a stream address in a library queue: a Subsonic stream, told without the queue map (sba_queue_note builds the queue even when the map cannot be allocated, and the map is memory
 * only). A library play type (& 0xf000) never holds an address of stock's: Tidal, DLNA and the stock stream lists play under their own types (2, 3, 0xf0, 0xf1), which keep stock's behaviour. */
int sbs_playing_stream(void) {
    void *rec = cc_playing();
    return rec && sbn_http_url(P(rec, REC_PATH)) && (sba_rec_track(I(rec, REC_ID))[0] || (mclGetPlayType() & 0xf000));
}

int sbs_playing_ours(void) {
    void *rec = cc_playing();
    return rec && sba_rec_track(I(rec, REC_ID))[0];
}

/* The hook (tools/pod.py PLAYREC_SITE, payload hook 28): stock's add_playrecord, called by on_wm_idle_status once per track start, writes the queue record of a list play into recentplay and oftenplay
 * (/mnt/data/database.db). A stream's record is an address with the login token: it is not written (no dead row in the card's Recently Played and Most Played, no token in the database). The test is
 * the path alone, so it holds without the queue map; a downloaded file is a file and is written as any other. With the kill switch it is stock's call. */
int sbs_play_record(void) {
    void *rec;
    if (access(KILL_SD, F_OK) != 0 && (rec = cc_playing()) && sbn_http_url(P(rec, REC_PATH))) return 0;
    return add_playrecord();
}

/* The album of the track the player is on, as a list of one album record: the cached album row (albums.idx) when the sync has it, else a row made of what the queue and the player's record know (the id,
 * the name, the artist, the cover), which is all the album page needs to read the tracks. *artist_id (NULL: not asked; SBA_ID bytes) is the cached row's artist id, "" unknown. */
static void *nl_playing_album(char *artist_id) {
    void *rec = cc_playing(), *q;
    sba_track_t *t;
    sba_album_t *one;
    sba_albums_t a;
    int i, found = -1;
    if (artist_id) artist_id[0] = 0;
    if (!rec || !(t = (sba_track_t *)calloc(1, sizeof *t))) return (void *)0;
    if (!sba_rec_row(I(rec, REC_ID), t) || !t->album_id[0]) {
        free(t);
        return (void *)0;
    }
    sba_albums(&a);
    for (i = 0; i < a.n && found < 0; ++i)
        if (!strcmp(a.v[i].id, t->album_id)) found = i;
    q = nl_new();
    if (q && found >= 0) {
        if (artist_id) snprintf(artist_id, SBA_ID, "%s", a.v[found].artist_id);
        nl_push_album(q, &a.v[found]);
    } else if (q && (one = (sba_album_t *)calloc(1, sizeof *one)) != 0) {
        snprintf(one->id, sizeof one->id, "%s", t->album_id);
        snprintf(one->name, sizeof one->name, "%s", cc_str(rec, REC_ALBUM));
        snprintf(one->artist, sizeof one->artist, "%s", cc_str(rec, REC_ARTIST));
        snprintf(one->cover, sizeof one->cover, "%s", t->cover);
        nl_push_album(q, one);
        free(one);
    }
    sba_free_albums(&a);
    free(t);
    return nl_done(q);
}

void *sbs_playing_album(void) { return nl_playing_album((char *)0); }

/* Its artist, as a list of one artist record: the artist of the cached album row (by id; the Artists list's row when it has one, else a row of the id and the album's artist name), or, for an album the
 * sync does not have, the Artists list's row of the track's artist name (ASCII case-insensitive). NULL when neither is known. */
void *sbs_playing_artist(void) {
    void *rec = cc_playing(), *al, *q = (void *)0;
    char aid[SBA_ID];
    sba_artists_t r;
    sba_artist_t *one;
    const char *name;
    int i, found = -1;
    if (!rec || !sbs_playing_ours()) return (void *)0;
    al = nl_playing_album(aid);
    name = aid[0] && al ? cc_str(deque_at(al, 0), REC_ARTIST) : cc_str(rec, REC_ARTIST);
    sba_artists(&r);
    for (i = 0; i < r.n && found < 0; ++i)
        if (aid[0] ? !strcmp(r.v[i].id, aid) : (name[0] && !cc_nocase(r.v[i].name, name))) found = i;
    if (found >= 0 || aid[0]) q = nl_new();
    if (q && found >= 0)
        nl_push_artist(q, &r.v[found]);
    else if (q && (one = (sba_artist_t *)calloc(1, sizeof *one)) != 0) {
        snprintf(one->id, sizeof one->id, "%s", aid);
        snprintf(one->name, sizeof one->name, "%s", name);
        nl_push_artist(q, one);
        free(one);
    }
    sba_free_artists(&r);
    if (al) deque_destroy(al);
    return nl_done(q);
}

int sbs_playing(const char *id) {
    void *rec = cc_playing();
    return id && id[0] && rec && !strcmp(sba_rec_track(I(rec, REC_ID)), id);
}

/* ---------------------------------------------------------------------------
 * Keep awake while a server stream plays or a download runs (the PR's stream timer, on the paved path of Radio and the Podcast downloads: stock's reset_poweroptions_timer(1, 1, 0), tools/pod.py).
 * One 1 s timer, armed when a play or Play Next / After queues a track and when a download is queued; it runs on the UI thread whichever page is open. It calls while the player is playing
 * (status 2) a Navidrome record whose path is a stream address, and while the download worker runs (sba_dl_busy; the Podcast downloads' pg_awake_tick does the same): paused, stopped, a
 * downloaded file or another source's track never call by themselves. It ends when neither holds -- the player stopped or plays something else and no download runs -- after a grace
 * for the queue to load.
 */
#define NL_AWAKE_MS 1000
#define NL_AWAKE_GRACE_MS 5000u
#define NL_STREAM_SLEEP_MS 1800000u /* 30 minutes of confirmed active remote playback */
#define NL_SCROBBLE_MS \
    240000u /* a play counts after four minutes, or half the track when that is sooner (the usual scrobble rule) */

/* Scrobble: a server track (a stream or its downloaded file) that has played for half its length or four minutes is reported to the server once (sba_scrobble: scrobble.view), so its
 * play count and last played move and the server forwards the play where it is set up to. The keep-awake tick counts the time the player spends playing it (the clock between two
 * ticks that both saw it playing, so a late tick loses nothing). A report the guard or the full queue refuses is made again at the next tick while the track still plays; a play
 * with no Wi-Fi to the end is not reported. */
static void nl_scrobble(void *rec, int st, int ours) {
    const char *id = ours ? sba_rec_track(I(rec, REC_ID)) : "";
    unsigned now = (unsigned)time_now_ms();
    if (strcmp(nl.sc_id, id)) {
        sba_track_t *t = id[0] ? calloc(1, sizeof *t) : (sba_track_t *)0;
        nl_copy(nl.sc_id, sizeof nl.sc_id, id);
        nl.sc_ms = 0, nl.sc_run = 0, nl.sc_sent = 0, nl.sc_need = NL_SCROBBLE_MS;
        if (t && sba_rec_row(I(rec, REC_ID), t) && t->seconds && t->seconds * 500u < NL_SCROBBLE_MS)
            nl.sc_need = t->seconds * 500u;
        free(t);
    }
    if (st == 2 && nl.sc_run) nl.sc_ms += now - nl.sc_at;
    nl.sc_run = st == 2, nl.sc_at = now;
    if (id[0] && st == 2 && !nl.sc_sent && nl.sc_ms >= nl.sc_need && sba_scrobble(id) == SBA_OK) nl.sc_sent = 1;
}

static int nl_awake_tick(const void *timer) {
    void *rec = cc_playing();
    int st = mclGetPlayStatus(), ours = rec && sba_rec_track(I(rec, REC_ID))[0];
    int remote = st == 2 && ours && sbn_http_url(P(rec, REC_PATH));
    unsigned now = (unsigned)time_now_ms();
    (void)timer;
    nl_scrobble(rec, st, ours);
    if (remote) {
        const char *id = sba_rec_track(I(rec, REC_ID));
        if (!nl.stream_at || strcmp(nl.sleep_id, id)) {
            nl.stream_at = now;
            nl_copy(nl.sleep_id, sizeof nl.sleep_id, id);
        }
        if (now - nl.stream_at >= NL_STREAM_SLEEP_MS) {
            mclSetPause(); /* pause before stock standby so wake never resumes a live network stream */
            nl.awake = 0;
            nl.stream_at = 0;
            nl.sleep_id[0] = 0;
            into_standby(); /* stock path: display and Wi-Fi off, no persistent power-setting write */
            return RET_OK;
        }
    } else {
        nl.stream_at = 0;
        nl.sleep_id[0] = 0;
    }
    if (remote || sba_dl_busy()) {
        reset_poweroptions_timer(1, 1,
                                 0); /* a stream plays or a download runs: stock standby would stop Wi-Fi and the CPU */
        return RET_REPEAT;
    }
    if ((int)((unsigned)time_now_ms() - nl.awake_until) < 0 || st == 3 || (st == 2 && ours)) return RET_REPEAT;
    nl.awake = 0;
    nl.sc_id[0] = 0; /* (the same track started again later is a new play) */
    return RET_OK;
}

static void nl_awake_arm(void) {
    nl.awake_until = (unsigned)time_now_ms() + NL_AWAKE_GRACE_MS;
    if (!nl.awake) nl.awake = timer_add(nl_awake_tick, (void *)0, NL_AWAKE_MS);
}

void sbs_dl_resume(void) {
    if (sba_dl_resume() > 0) nl_awake_arm(); /* the tick holds the device awake while the files come */
}

/* ---------------------------------------------------------------------------
 * Cover, length, row extras, actions, generation
 */
static int nd_cover(const lib_src_t *s, void *rec, unsigned key, char *path, unsigned cap) {
    const char *m = nl_meta(rec);
    char cover[SBA_ID], album[SBA_ID];
    (void)s, (void)key;
    nl_field(m, m[0] == 't' ? 4 : 1, cover, sizeof cover);
    if (m[0] != 't') return sba_cover_get(cover, path, cap);
    nl_field(m, 5, album, sizeof album);
    return sba_track_cover(album, cover, path, cap,
                           1); /* a track shows its album's file (the one phase 2 fetched), not its own "mf-" cover */
}

static unsigned nd_seconds(const lib_src_t *s, void *rec) {
    const char *m = nl_meta(rec);
    (void)s;
    return m[0] == 't' ? nl_num(m, 1) : m[0] == 'a' ? nl_num(m, 4) : m[0] == 'p' ? nl_num(m, 3) : 0;
}

static void nd_row(const lib_src_t *s, void *rec, ls_row_t *out) {
    const char *id = nd_rec_id(s, rec), *m = nl_meta(rec);
    unsigned got = 0, total = 0, sh = 0;
    char suffix[SBA_SUFFIX];
    sba_track_t q;
    int queued = 0;
    memset(out, 0, sizeof *out);
    if (I(rec, REC_TYPE) != 8) return;
    if (!id[0]) { /* a queue record (Now Playing's star): its state is the cache's, read from the files, so not for a page's paint */
        if (!sbs_track(rec, &q)) return;
        id = q.id, queued = 1;
    }
    out->dl = sba_dl_state(id, (int *)0, &got, &total); /* SBA_DL_* and LS_DL_* are the same numbers */
    if (out->dl == LS_DL_ACTIVE) {
        if (!total)
            out->pct = -1;
        else {
            while ((total >> sh) >= (1u << 24)) ++sh;
            out->pct = (int)((got >> sh) * 100u / (total >> sh));
            if (out->pct > 100) out->pct = 100;
        }
    }
    if (queued) {
        out->dsd = sba_is_dsd(q.suffix);
        out->fav = q.starred != 0;
    } else {
        nl_field(m, 2, suffix, sizeof suffix);
        out->dsd = sba_is_dsd(suffix);
        out->fav = nl_num(m, 3) != 0;
    }
    out->offline = out->dl != LS_DL_DONE && get_wifisignal() <= 0;
}

/* The words for a failure code (status: the HTTP status of SBA_HTTP); nl_message's `download` tells a download's SBA_NET ("Download interrupted") from a request's. Already translated; valid until the next call. */
static const char *nl_message(int code, int status, int download) {
    switch (code) {
    case SBA_NOCONF:
        return TR("Add a server first");
    case SBA_NOWIFI:
        return TR("Connect to Wi-Fi first");
    case SBA_NOCLOCK:
        return TR("Set the date and time first");
    case SBA_CERT:
    case SBA_NOCERT:
        return TR("Server certificate not trusted");
    case SBA_AUTH:
        return TR("Incorrect username or password");
    case SBA_NOTFOUND:
        return TR("Song not found on the server");
    case SBA_HTTP:
        if (status < 100 || status > 999) return TR("Server error");
        snprintf(nl.msg, sizeof nl.msg, "%s %d", TR("Server error"), status);
        return nl.msg;
    case SBA_NOTAUDIO:
        return TR("Unexpected server response");
    case SBA_STORAGE:
        return TR("Storage unavailable");
    case SBA_CARDFULL:
        return TR("Card is full");
    case SBA_WRITE:
        return TR("Write failed");
    case SBA_QFULL:
        return TR("Queue is full");
    case SBA_MEM:
        return TR("Not enough memory");
    case SBA_NET:
        return download ? TR("Download interrupted") : TR("Can't connect to the server");
    default:
        return TR("Can't connect to the server");
    }
}

const char *sbs_message(int code, int status) { return nl_message(code, status, 1); }

const char *sbs_request_message(int code, int status) { return nl_message(code, status, 0); }

/* The message for a refused request. */
static int nl_why(int code) {
    if (code != SBA_OK) pod_toast(sbs_message(code, 0));
    return code;
}

/* Download Album: every track of the page's list that is not on the card and not waiting or running is queued, in list order, with the one toast. A guard that refuses the first one (no Wi-Fi, no card, card full ...) shows its
 * message and queues nothing; a full queue keeps the tracks that fit and says so. Returns 0 when something was queued or all were there already, else the SBA_* that stopped it. */
static int nl_download_all(void *list) {
    unsigned i, n, queued = 0;
    sba_track_t t;
    int code = SBA_OK, st;
    char msg[96];
    if (!list) return -1;
    for (i = 0, n = deque_size(list); i < n && code == SBA_OK; ++i) {
        if (!sbs_track(deque_at(list, i), &t)) continue;
        st = sba_dl_state(t.id, (int *)0, (unsigned *)0, (unsigned *)0);
        if (st == SBA_DL_DONE || st == SBA_DL_WAIT || st == SBA_DL_ACTIVE) continue;
        if ((code = sba_dl_add(&t)) == SBA_OK) ++queued;
    }
    if (queued) nl_awake_arm(); /* the tick holds the device awake while the files come */
    if (code == SBA_QFULL && queued) { /* the ones that fit are on their way: say how many */
        m1_fmt(msg, sizeof msg, TR("Downloading %d, queue full"), (int)queued);
        pod_toast(msg);
    } else if (code == SBA_QFULL)
        pod_toast(TR("Download queue is full"));
    else if (code != SBA_OK && !queued)
        pod_toast(sbs_message(code, 0));
    else if (queued == 1)
        pod_toast(TR("Downloading 1 song"));
    else if (queued) {
        m1_fmt(msg, sizeof msg, TR("Downloading %d songs"), (int)queued);
        pod_toast(msg);
    } else
        pod_toast(TR("Already downloaded"));
    return code;
}

static int nd_act(const lib_src_t *s, void *rec, int what) {
    sba_track_t t;
    (void)s;
    if (what == LS_ACT_DOWNLOAD_ALL) return nl_download_all(rec);
    if (what == LS_ACT_CANCEL_ALL_DL) {
        sba_dl_cancel_all();
        return 0;
    }
    if (what == LS_ACT_CANCEL_DL) {
        const char *id = nd_rec_id(s, rec);
        if (!id[0]) return -1;
        return nl_why(sba_dl_cancel(id)) == SBA_OK
                   ? 0
                   : -1; /* (a cancel the card does not take is told later, as a failed download is: nd_gen, "Storage unavailable") */
    }
    if (what == LS_ACT_DELETE_DL) {
        const char *id = nd_rec_id(s, rec);
        if (!id[0]) return -1;
        if (sba_dl_delete(id) == 0) return 0;
        pod_toast(TR("Storage unavailable"));
        return -1;
    }
    if (!sbs_track(rec, &t)) return -1;
    if (what == LS_ACT_DOWNLOAD) {
        int code = sba_dl_add(&t);
        if (code == SBA_QFULL) {
            pod_toast(TR("Download queue is full"));
            return code;
        }
        if (code == SBA_OK) nl_awake_arm(); /* the tick holds the device awake while the file comes */
        return nl_why(code);
    }
    if (what == LS_ACT_FAVORITE || what == LS_ACT_UNFAVORITE) return nl_why(sba_star(&t, what == LS_ACT_FAVORITE));
    return -1;
}

static int nd_playing(const lib_src_t *s, void *rec) { return sbs_playing(nd_rec_id(s, rec)); }

static unsigned nd_gen(const lib_src_t *s) {
    int code, status = 0;
    (void)s;
    if ((code = sba_dl_failure(&status)) != 0 && code != SBA_CANCELLED)
        pod_toast(sbs_message(code, status)); /* a download failed while a Navidrome page was up to hear of it */
    if (nl.due && (int)((unsigned)time_now_ms() - nl.due) >= 0) nl.due = 0, ++nl.epoch;
    return sba_gen() + sba_dl_gen() + nl.epoch;
}

static unsigned nd_gen_rows(const lib_src_t *s) {
    (void)s;
    return sba_gen() +
           nl.epoch; /* (the data layer's counter and the retry epoch; a download's progress changes no list) */
}

static unsigned nd_dl_rows(const lib_src_t *s, int *queued) {
    (void)s;
    if (queued) *queued = nl.dlq;
    return sba_dl_rows();
}

/* A playlist's row count before its tracks are cached (the Playlists page's tiles): the sync's songCount from the row's own data. A list the server answered as empty is final: 0. */
static int nd_count(const lib_src_t *s, int which, void *rec) {
    const char *m, *id;
    if (which != LS_PLAYLISTS || !rec) return 0;
    id = nd_rec_id(s, rec);
    if (!id[0]) return 0;
    if (sba_state(SBA_K_PLAYLIST, id, (int *)0) == SBA_ST_OK) return 0;
    m = nl_meta(rec);
    return m && m[0] == 'p' ? (int)nl_num(m, 2) : 0;
}

/* A request's state as a page sees it: the server's answer, even an empty one, is final (READY); a failed request is FAILED, OFFLINE when it failed for want of Wi-Fi; nothing asked yet is OFFLINE
 * with no Wi-Fi to ask on, else LOADING (asked, or refused for now and asked again at the next read). `known`: the answer is known to exist without a request of this run (the sync's summary). */
static int nd_ask_state(int kind, const char *id, int known) {
    int code = 0, st = sba_state(kind, id, &code);
    if (st == SBA_ST_FAIL) return code == SBA_NOWIFI ? LS_ST_OFFLINE : LS_ST_FAILED;
    if (st == SBA_ST_OK || (st == SBA_ST_NONE && known)) return LS_ST_READY;
    if (st == SBA_ST_NONE && get_wifisignal() <= 0) return LS_ST_OFFLINE;
    return LS_ST_LOADING;
}

/* LS_ST_*: whether the rows of a list can still arrive. The tracks of an album, an artist or a playlist row, and (scope NULL) the whole-library lists: albums, artists, playlists and favourites
 * come with the sync, the Songs list with its own paging. An artist's All songs row is loading while any of its albums is. */
static int nd_state(const lib_src_t *s, int which, void *rec) {
    const char *id;
    int kind, st;
    if (!rec) {
        if (which == LS_SONGS) return nd_ask_state(SBA_K_SONGS, "", 0);
        if (which == LS_ALBUMS || which == LS_ARTISTS || which == LS_PLAYLISTS || which == LS_FAVORITES)
            return nd_ask_state(SBA_K_SYNC, "",
                                !sba_sync_due()); /* (a recent sync that found none: final even in a new run) */
        return LS_ST_READY;
    }
    if (which != LS_SONGS && which != LS_PLAYLISTS && which != LS_ALBUMS) return LS_ST_READY;
    id = nd_rec_id(s, rec);
    if (!id[0]) return LS_ST_READY;
    if (which == LS_PLAYLISTS)
        kind = SBA_K_PLAYLIST;
    else if (which == LS_ALBUMS || I(rec, REC_ID) == ID_ALL_SONGS)
        kind = SBA_K_ARTIST;
    else
        kind = SBA_K_ALBUM;
    st = nd_ask_state(kind, id, 0);
    if (st == LS_ST_READY && which == LS_SONGS && kind == SBA_K_ARTIST) {
        sba_albums_t al;
        int i, busy = 0;
        sba_artist_albums(id, &al);
        for (i = 0; i < al.n && !busy; ++i) busy = sba_state(SBA_K_ALBUM, al.v[i].id, (int *)0) == SBA_ST_LOAD;
        sba_free_albums(&al);
        if (busy) return LS_ST_LOADING;
    }
    return st;
}

static int nd_complete(const lib_src_t *s, int which) {
    unsigned cached;
    (void)s;
    if (which != LS_SONGS) return 1;
    cached = (unsigned)sba_songs_cached();
    if (cached >= SBS_SONGS_MAX) return 1;
    if (sba_songs_more()) return 0;
    return cached || sba_state(SBA_K_SONGS, "", (int *)0) != SBA_ST_LOAD;
}

/* ---------------------------------------------------------------------------
 * Play
 */
static void nl_queue_free(void *q, sba_track_t *t, char (*local)[NL_PATH], int *ids) {
    if (q) deque_destroy(q);
    free(t);
    free(local);
    free(ids);
}

/* One stock queue record: the PR's fields (sb_play_click) -- the file name, the address (or the local file), the texts and the numbers; the strings are copied by the push. */
static int nl_push_queue(void *q, const sba_track_t *t, int rid, const char *name, const char *where) {
    unsigned rec[REC_SIZE / 4], n = deque_size(q);
    memset(rec, 0, sizeof rec);
    I(rec, REC_ID) = rid;
    P(rec, REC_NAME) = (char *)name;
    P(rec, REC_PATH) = (char *)where;
    P(rec, REC_TITLE) = (char *)(t->title[0] ? t->title : name);
    P(rec, REC_ALBUM) = (char *)t->album;
    P(rec, REC_ARTIST) = (char *)t->artist;
    P(rec, REC_ALBUMARTIST) = (char *)t->artist;
    P(rec, REC_RESERVED_A) = (char *)"";
    P(rec, REC_RESERVED_B) = (char *)"";
    I(rec, REC_YEAR) = (int)t->year;
    I(rec, REC_TYPE) = 8;
    I(rec, REC_CLASS) = 0;
    I(rec, REC_TRACK) = (int)t->track;
    I(rec, REC_DISC) = (int)t->disc;
    _deque_push_back(q, rec);
    return deque_size(q) > n;
}

/* The queue record of one track: its local file when `local` is not empty, else the stream address (the file name is the PR's "<title>.<suffix>" so the stock player picks the decoder). 0 when the address could not be made. */
static int nl_push_item(void *q, const sba_track_t *t, int rid, const char *local) {
    char name[SBA_TEXT + 16], url[SBA_URL];
    const char *where = local, *file;
    if (local[0]) {
        file = strrchr(where, '/');
        nl_copy(name, sizeof name, file ? file + 1 : where);
    } else {
        if (sba_stream_url(url, sizeof url, t->id) || sba_track_filename(name, sizeof name, t) < 0) return 0;
        where = url;
    }
    return nl_push_queue(q, t, rid, name, where);
}

/* 1 when the row can start now: a track that is on the card, or a streamable one with the Wi-Fi up. */
static int nl_playable(const lib_src_t *s, void *rec, int online) {
    char local[NL_PATH];
    const char *id = nd_rec_id(s, rec), *m;
    char suffix[SBA_SUFFIX];
    if (I(rec, REC_TYPE) != 8 || !id[0]) return 0;
    if (sba_dl_path(id, local, sizeof local)) return 1;
    m = nl_meta(rec);
    nl_field(m, 2, suffix, sizeof suffix);
    return online && !sba_is_dsd(suffix);
}

static unsigned nl_gcd(unsigned a, unsigned b) {
    while (b) {
        unsigned r = a % b;
        a = b, b = r;
    }
    return a;
}

/* A Shuffle's walk over a list of `count` rows: row (start + k * stride) % count for k = 0, 1, ... The stride is random and coprime with the count, so the walk visits every row once, spread over
 * the whole list and not one run. The search is bounded (at most count tries); when no stride in 2 .. count - 2 is coprime (count 6, say) the walk is the list in order: stride 1. */
static unsigned nl_stride(unsigned count, int shuffle) {
    unsigned st, tries;
    if (!shuffle || count < 5) return 1;
    st = 2 + pod_rand(count - 3); /* 2 .. count - 2 */
    for (tries = 0; tries < count; ++tries) {
        if (nl_gcd(st, count) == 1) return st;
        st = st + 1 < count - 1 ? st + 1 : 2;
    }
    return 1;
}

/* A play over a list. A row tap or Play (at >= 0): the queue is the list's rows in the list's order, opened at the tapped track's place in it (as the library's so_play_with); a list longer than
 * the queue gives a window of SBA_QUEUE_MAX rows from the tapped one, moved back near the end so it still holds that many. Rows that cannot play are left out. A Shuffle (at < 0): a random
 * playable start and the stride walk, opened at 0. */
static int nd_play(const lib_src_t *s, void *list, int at, int how, void (*open)(void *queue, int idx, int cls),
                   int cls) {
    unsigned count = list ? deque_size(list) : 0, i, n = 0, first = 0, last, idx = 0;
    sba_track_t *t;
    char (*local)[NL_PATH];
    int *ids, *lone, online = get_wifisignal() > 0, shuffle = at < 0, here, dsd;
    unsigned k, stride,
        cap = count < SBA_QUEUE_MAX ? count : SBA_QUEUE_MAX; /* the queue's rows: the list, or a window of it */
    const char *id;
    void *q;
    if (at < 0 &&
        count) { /* a random start: a row that can play, the first from the random pick on (wrapping), so Shuffle never lands on a DSD file that is not on the card unless there is nothing else */
        unsigned pick = pod_rand(count);
        at = (int)pick;
        for (k = 0; k < count; ++k)
            if (nl_playable(s, deque_at(list, (pick + k) % count), online)) {
                at = (int)((pick + k) % count);
                break;
            }
    } else if (
        how == LS_PLAY_ORDER && at >= 0 && at < (int)count &&
        !nl_playable(
            s, deque_at(list, (unsigned)at),
            online)) { /* the Play pill, not a row: it starts at the first row from there that can play (offline with some tracks on the card, a DSD file first), the row itself when none can */
        for (k = (unsigned)at + 1; k < count; ++k)
            if (nl_playable(s, deque_at(list, k), online)) {
                at = (int)k;
                break;
            }
    }
    if (at < 0 || at >= (int)count) return -1;
    id = nd_rec_id(s, deque_at(list, (unsigned)at));
    if (I(deque_at(list, (unsigned)at), REC_TYPE) != 8 || !id[0]) return -1;
    t = calloc(cap, sizeof *t);
    local = calloc(cap, sizeof *local);
    ids = calloc(2 * cap, sizeof *ids); /* the records' ids, then whether each plays from the card */
    lone = ids + cap;
    if (!t || !local || !ids) {
        nl_queue_free((void *)0, t, local, ids);
        pod_toast(TR("Not enough memory"));
        return -1;
    }
    nl_from_rec(deque_at(list, (unsigned)at), &t[0]); /* the tapped row's own checks come first */
    here = sba_dl_path(t[0].id, local[0], NL_PATH);
    dsd = sba_is_dsd(t[0].suffix);
    if (dsd && !here) { /* the page asks to download it first */
        nl.dsd_row = at;
        nl_queue_free((void *)0, t, local, ids);
        return -2;
    }
    if (!here && !online) {
        nl_queue_free((void *)0, t, local, ids);
        pod_toast(TR("Connect to Wi-Fi first"));
        return -1;
    }
    stride = nl_stride(count, shuffle);
    if (!shuffle) {
        first = count > SBA_QUEUE_MAX && (unsigned)at > count - SBA_QUEUE_MAX ? count - SBA_QUEUE_MAX : (unsigned)at;
        if (count <= SBA_QUEUE_MAX) first = 0;
    }
    last = shuffle ? count : (count - first > SBA_QUEUE_MAX ? first + SBA_QUEUE_MAX : count);
    for (k = 0, i = shuffle ? (unsigned)at : first; n < cap; ++k) {
        void *rec;
        if (shuffle ? k >= count : i >= last) break;
        rec = deque_at(list, i);
        if (I(rec, REC_TYPE) == 8 && nd_rec_id(s, rec)[0]) {
            nl_from_rec(rec, &t[n]);
            here = sba_dl_path(t[n].id, local[n], NL_PATH);
            dsd = sba_is_dsd(t[n].suffix);
            if (here || (!dsd && online)) { /* DSD is never streamed; offline only the downloaded play */
                if (i == (unsigned)at) idx = n;
                lone[n] = here;
                ++n;
            }
        }
        i = shuffle ? (i + stride) % count : i + 1;
    }
    if (!n) {
        nl_queue_free((void *)0, t, local, ids);
        return -1;
    }
    sba_queue_note(t, (int)n, ids);
    q = nl_new();
    for (i = 0; q && i < n; ++i) {
        if (!nl_push_item(q, &t[i], ids[i], lone[i] ? local[i] : "")) break;
    }
    if (!q || deque_size(q) != n) {
        sba_queue_undo(); /* the playing stream keeps its map */
        if (q)
            pod_toast(TR("Can't play")); /* no stream address could be made for a track */
        else
            pod_toast(TR("Not enough memory")); /* no memory for the queue */
        nl_queue_free(q, t, local, ids);
        return -1;
    }
    sba_queue_keep();
    if (how == LS_PLAY_ORDER)
        pod_set_in_order_for_queue(); /* Play: the list in order, even after a Shuffle; a row tap keeps the mode, as stock */
    else if (how == LS_PLAY_SHUFFLE)
        pod_set_mode_for_queue(MODE_SHUFFLE);
    *(int *)G_CLASS_TYPE = cls;
    open(q, (int)idx, cls);
    nl_queue_free(q, t, local, ids);
    nl_awake_arm();
    return 0;
}

/* Play Next / Play After: the row as a queue record (the stream address, or the local file when downloaded) in a deque of one, its synthetic id added to the queue map so the playing marker and Now Playing's cover know it. */
static void *nd_queue_row(const lib_src_t *s, void *rec) {
    sba_track_t t;
    char local[NL_PATH];
    void *q;
    int here, rid;
    if (!sbs_track(rec, &t)) return (void *)0;
    here = sba_dl_path(t.id, local, sizeof local);
    if (!here &&
        (sba_is_dsd(t.suffix) || get_wifisignal() <= 0)) { /* DSD is never streamed; offline only the downloaded play */
        pod_toast(TR("Connect to Wi-Fi first"));
        return (void *)0;
    }
    q = nl_new();
    rid = sba_queue_add(&t);
    if (!q || !rid || !nl_push_item(q, &t, rid, here ? local : "") || deque_size(q) != 1) {
        if (q)
            pod_toast(TR("Can't play"));
        else
            pod_toast(TR("Not enough memory"));
        if (q) deque_destroy(q);
        return (void *)0;
    }
    (void)s;
    nl_awake_arm();
    return q;
}

/* The confirm dialog's buttons become Cancel (left, btn_cancel) and Download (right, btn_enter), found by the dialog's name once it is up (Software Update's way, patch/update.c). */
static int nl_relabel(const void *timer) {
    void *wm = window_manager(), *dlg = wm ? widget_lookup(wm, SHOT_DIALOG, 1) : (void *)0, *b;
    (void)timer;
    if (!dlg) return ++nl.tries < SHOT_RELABEL_TRIES ? RET_REPEAT : RET_OK;
    if ((b = widget_lookup(dlg, SHOT_BTN_SHORT, 1)) != (void *)0) widget_set_text_utf8(b, TR("Cancel"));
    if ((b = widget_lookup(dlg, SHOT_BTN_LONG, 1)) != (void *)0) widget_set_text_utf8(b, TR("Download"));
    return RET_OK;
}

int ls_dsd_confirm(const lib_src_t *src, void *list, int at) {
    sba_track_t t;
    char title[32], size[16], body[160], text[400];
    unsigned n;
    void *rec, *one;
    if (!src || !list) return 0;
    if (at < 0) at = nl.dsd_row;
    if (at < 0 || at >= (int)deque_size(list)) return 0;
    rec = deque_at(list, (unsigned)at);
    if (!sbs_track(rec, &t)) return 0;
    for (n = 0; t.title[n] && n < 24; ++n) title[n] = t.title[n];
    if (t.title[n]) { /* a long title: cut at a character boundary, then the ellipsis */
        while (n && ((unsigned char)t.title[n] & 0xc0) == 0x80) --n;
        title[n++] = '.', title[n++] = '.', title[n++] = '.';
    }
    title[n] = 0;
    if (t.size)
        snprintf(size, sizeof size, "%u", (t.size + 500000u) / 1000000u);
    else
        nl_copy(size, sizeof size, "?");
    snprintf(body, sizeof body, TR("DSD tracks play from the card. %s, %s MB."), title, size);
    snprintf(text, sizeof text, "%s\n%s", TR("Download to Play?"), body);
    one =
        nl_new(); /* the page's list may be read again while the dialog is up (its timers run): the row is kept in a deque of our own */
    if (!one) return 0;
    _deque_push_back(one, rec);
    nl.tries = 0;
    timer_add(nl_relabel, (void *)0, SHOT_RELABEL_MS); /* a refused timer only leaves the buttons Yes / No */
    if (deque_size(one) == 1 && pod_confirm_code(text) == CONFIRM_YES)
        n = (unsigned)(src->act(src, deque_at(one, 0), LS_ACT_DOWNLOAD) == 0);
    else
        n = 0;
    deque_destroy(one);
    return (int)n;
}

const lib_src_t
    lib_nd = {"navidrome",   nd_list,  nd_rec_id, nd_play,     nd_cover,   nd_seconds,
              nd_row,        nd_act,   nd_gen,    nd_complete, nd_playing, nd_queue_row,
              LS_CAP_SEARCH, nd_count, nd_state,  nd_gen_rows, nd_dl_rows}; /* caps: Search only (no Cover Flow or Select on its pages yet) */

const lib_src_t *lib_navidrome(void) { return sba_configured() ? &lib_nd : (const lib_src_t *)0; }
