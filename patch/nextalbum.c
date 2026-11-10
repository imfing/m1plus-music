/* M1+ Music Continue with Next Album (docs/modules/nextalbum.md): the order an album was opened from (phase 1), and the queue's end (phase 2, na_end below).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * The order is memory only. The Albums page (library or one artist's / composer's albums) and Cover Flow call na_note_albums just before
 * cc_open_album with the albums as they show them; album_open takes the note (na_page_open) when the album it opens is in it, so an album opened by any other caller
 * has no order; the album page arms it around its play call (na_arm / na_disarm), and the mclLoadPlayList hook (patch/shuffle.c sh_load_playlist -> na_on_load) keeps the
 * order for that one load and drops it for every other. A source is a reference counted block (the album keys in order, the album now playing, the scope and a copy of the
 * artist row of a scoped page), held by up to three slots: the pending note, the open album page and the active source, so a page closing or a new note never frees what
 * is playing. Turned off (Settings > Playback) or under the kill switch, nothing is recorded.
 */
#include "offsets.inc"
#include "stock.h"
#include "home.h"
#include "covercache.h"
#include "upnext.h"
#include "nextalbum.h"

#define I(w, off) (*(int *)((char *)(w) + (off)))

struct na_src {
    unsigned ref, n, scope, own, cur; /* own: the album the page was opened on; cur: the album now playing */
    void *artist; /* a deque holding the artist's (or composer's) stock row; NULL for the library */
    unsigned keys[1]; /* n album keys, in the order shown */
};

static struct {
    unsigned char loaded, on;
    unsigned char armed; /* na_arm .. the load */
    struct na_src *pending; /* noted by the opener, not yet taken */
    struct na_src *page; /* the open album page's order */
    struct na_src *active; /* the order the playing queue's album came from */
    struct na_src *prev; /* the source na_arm replaced, put back by na_disarm when no load followed */
} na __attribute__((section(".scratch")));

static int enabled(void) {
    if (home_off()) return 0;
    if (!na.loaded) na.on = set_read(NA_FILE, '0') == '1', na.loaded = 1;
    return na.on;
}

int na_setting(void) { return set_read(NA_FILE, '0') == '1' ? NA_ALBUMS : NA_OFF; }

static struct na_src *retain(struct na_src *s) {
    if (s) s->ref++;
    return s;
}

static void release(struct na_src *s) {
    if (!s || --s->ref) return;
    if (s->artist) deque_destroy(s->artist);
    free(s);
}

static void release_active(void) {
    release(na.active);
    na.active = (struct na_src *)0;
}

int na_set(int mode) {
    if (mode != NA_OFF && mode != NA_ALBUMS) return -1;
    if (home_write_atomic(NA_FILE, NA_TMP, mode == NA_ALBUMS ? "1\n" : "0\n") != 0) return -1;
    na.on = mode == NA_ALBUMS, na.loaded = 1;
    if (mode == NA_OFF) { /* off: nothing continues */
        if (na.active) release_active();
    }
    return mode;
}

void na_note(const unsigned *keys, unsigned n, unsigned scope, void *artist_row) {
    struct na_src *s;
    release(na.pending);
    na.pending = (struct na_src *)0;
    if (!keys || !n || !enabled()) return;
    if (n > CC_CMAP_MAX) n = CC_CMAP_MAX;
    s = calloc(1, sizeof *s + n * sizeof(unsigned));
    if (!s) return;
    s->ref = 1, s->n = n, s->scope = scope;
    memcpy(s->keys, keys, n * sizeof(unsigned));
    if (artist_row && !(s->artist = cc_copy_list(artist_row))) { /* a scoped order needs its artist: none, no source */
        free(s);
        return;
    }
    na.pending = s;
}

void na_note_albums(void *albums, const unsigned *order, unsigned n, unsigned scope, void *artist_row) {
    unsigned *keys, i, m = 0;
    if (!albums || !n || !enabled()) {
        na_note((const unsigned *)0, 0, 0, (void *)0);
        return;
    }
    if (n > deque_size(albums)) n = deque_size(albums);
    keys = calloc(n, sizeof(unsigned));
    if (!keys) {
        na_note((const unsigned *)0, 0, 0, (void *)0);
        return;
    }
    for (i = 0; i < n && m < CC_CMAP_MAX; i++) {
        void *r = cc_row(albums, order, i);
        if (!r || I(r, REC_ID) == ID_ALL_SONGS || I(r, REC_ID) == -1)
            continue; /* the All Songs card and Unknown Album are not albums to continue to */
        keys[m++] = cc_album_key(r);
    }
    na_note(keys, m, scope, artist_row);
    free(keys);
}

void na_note_drop(void) {
    release(na.pending);
    na.pending = (struct na_src *)0;
}

void na_page_open(unsigned key) {
    struct na_src *s = na.pending;
    unsigned i;
    release(na.page);
    na.page = (struct na_src *)0;
    na.pending = (struct na_src *)0;
    if (!s) return;
    for (i = 0; i < s->n; i++)
        if (s->keys[i] == key) {
            s->own = s->cur = key;
            na.page = s; /* (the pending slot's reference moves to the page) */
            return;
        }
    release(s); /* an album that is not in the note: not opened from that list */
}

void na_page_close(void) {
    release(na.page);
    na.page = (struct na_src *)0;
}

void na_arm(void) {
    if (na.armed) na_disarm();
    na.prev = na.active;
    na.active = retain(na.page);
    if (na.active) na.active->cur = na.active->own;
    na.armed = 1;
}

void na_disarm(void) {
    if (na.armed) { /* no load came: the old queue plays on, with its old source */
        release(na.active);
        na.active = na.prev;
        na.prev = (struct na_src *)0;
        na.armed = 0;
    }
}

void na_on_load(void) {
    if (na.armed) {
        release(na.prev);
        na.prev = (struct na_src *)0;
        na.armed = 0;
        return;
    }
    release_active();
}

int na_next_key(unsigned cur_key, unsigned *out) {
    struct na_src *s = na.active;
    unsigned i;
    if (!s || !out) return 0;
    for (i = 0; i < s->n; i++)
        if (s->keys[i] == cur_key) {
            if (i + 1 >= s->n) return 0;
            *out = s->keys[i + 1];
            return 1;
        }
    return 0;
}

__attribute__((noinline)) void na_set_cur(unsigned key) { /* (noinline: the tests call these three by name) */
    if (na.active) na.active->cur = key;
}

__attribute__((noinline)) unsigned na_cur(void) { return na.active ? na.active->cur : 0; }

__attribute__((noinline)) int na_active(void) { return na.active != (struct na_src *)0; }

/* ---------------------------------------------------------------------------
 * The end of the queue (hook 26, tools/pod.py NEXTALBUM_SITE, the stub pod_na_site): mclNextSong's List play branch found the playing song last.
 */
#define NA_REC_ALBUMARTIST \
    0x24 /* an artist row's album-artist string (loadAlbumList @0x4ee968 stores it for ARTIST_TYPE 1; else REC_ARTIST) */
#define NA_REC_COMPOSER 0x20 /* a composer row's name string (@0x4ee9f4) */
#define NA_NAME \
    256 /* loadAlbumdetailList snprintf's the album and artist names into 0x100 byte fields of the browsing record; the queries get the same cut */

static void na_tmp_clear(void) {
    void *d = *(void **)PDEQ_TOOLS_TMP;
    if (d) deque_clear(d);
}

static void na_copy(char *out, const char *s) {
    unsigned i = 0;
    while (s[i] && i < NA_NAME - 1) out[i] = s[i], i++;
    out[i] = 0;
}

/* The stock queries of the album page's lists, called as loadLocalClassList / loadAlbumList make them (but not their last step, which replaces *pdeq_showlist): the
 * rows are left in *PDEQ_TOOLS_TMP. The artist's name field depends on the album-artist switch (ARTIST_TYPE 1, @0x4ee960..0x4ee9b4). */
static const char *na_scope_name(const struct na_src *s, char *buf, int *unknown) {
    void *r = s->artist ? deque_at(s->artist, 0) : (void *)0;
    const char *n;
    *unknown = r && I(r, REC_ID) == -1; /* the Unknown Artist row: stock passes no name */
    if (!r) return (const char *)0;
    n = cc_str(r, s->scope == CLASS_COMPOSERS         ? NA_REC_COMPOSER
                  : *(volatile int *)ARTIST_TYPE == 1 ? NA_REC_ALBUMARTIST
                                                      : REC_ARTIST);
    na_copy(buf, n);
    return *unknown ? (const char *)0 : buf;
}

/* The albums of the source's list into *PDEQ_TOOLS_TMP; 0 on a failed query. */
static int na_albums(const struct na_src *s, const char *who) {
    if (!s->artist) return toolsQueryDbTable(STOCK_DB_PATH, STOCK_ALBUM_SQL, STOCK_ALBUM_ROW, 0) >= 0;
    if (s->scope == CLASS_COMPOSERS) return getAlbumByComposer(who) >= 0;
    return (*(volatile int *)ARTIST_TYPE == 1 ? getAlbumByAlbumArtist(who) : getAlbumByArtist(who)) >= 0;
}

/* The tracks of album `alb` (by `who` in a scoped list) into *PDEQ_TOOLS_TMP, in the order the album page lists them (the stock getter sorts them: disc, then track). */
static int na_tracks(const struct na_src *s, const char *alb, const char *who) {
    if (!s->artist) return getMusicByAlbum(alb) >= 0;
    if (s->scope == CLASS_COMPOSERS) return getMusicByAlbumAndComposer(alb, who, 0) >= 0;
    return (*(volatile int *)ARTIST_TYPE == 1 ? getMusicByAlbumAndAlbumSonger(alb, who, 0)
                                              : getMusicByAlbumAndSonger(alb, who, 0)) >= 0;
}

/* 1 when the queue just ended was extended with the next album's tracks (the caller plays on), 0 for stock's own end. Nothing is changed on any 0. */
int na_end(void) {
    char alb[NA_NAME], who[NA_NAME];
    const char *name;
    struct na_src *s;
    unsigned key, i, n;
    void *q, *list, *rows;
    int unknown, found = 0, r;
    if (!enabled() || !na_active() || *(volatile int *)DMR_SERVERFLAG == 1 || pod_shuffle_on() || mclGetPlayMode() != 0)
        return 0;
    q = *(void **)PLAY_QUEUE;
    n = q ? deque_size(q) : 0;
    s = na.active;
    r = mclGetPlayPos();
    if (!n || r < 0 || (unsigned)r != n - 1)
        return 0; /* (stock's test said last; a queue that changed since is not ours to extend) */
    if (!na_next_key(na_cur(), &key)) return 0;
    retain(s); /* the source stays while the queries run */
    name = na_scope_name(s, who, &unknown);
    if (s->artist && !unknown && !name) goto out; /* a scoped list without its artist */
    if (!na_albums(s, name)) goto out;
    list = *(void **)PDEQ_TOOLS_TMP;
    for (i = 0; list && i < deque_size(list); i++) {
        void *row = deque_at(list, i);
        if (I(row, REC_ID) == ID_ALL_SONGS || I(row, REC_ID) == -1 || cc_album_key(row) != key) continue;
        na_copy(alb, cc_str(row, REC_ALBUM)); /* (copied: the next query replaces the list) */
        found = 1;
        break;
    }
    na_tmp_clear();
    if (!found || !alb[0] || !na_tracks(s, alb, name)) goto out;
    rows = *(void **)PDEQ_TOOLS_TMP;
    if (!rows || !deque_size(rows)) goto out;
    found = upnext_add(rows, 1) == UPNEXT_ADDED;
    na_tmp_clear();
    if (found) na_set_cur(key); /* the chain goes on from this album */
    release(s);
    return found;
out:
    na_tmp_clear();
    release(s);
    return 0;
}
