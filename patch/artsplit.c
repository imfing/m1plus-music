/* Artist split: the Artists index and an artist's albums and songs when one artist field names several artists (patch/artsplit.h, docs/modules/artists.md "Split index").
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * Stateless: the index lives only in the Artists page's rows; every answer (an artist's albums, songs, an album's tap) is computed from the library's songs (cc_songs) at that moment,
 * so there is no second copy of the library to go stale. A row's songs are found by splitting each song's artist field with the shared splitter (m1_artist_split) and comparing the
 * names ASCII case-insensitively; a cheap substring test first skips the fields that cannot hold the name.
 */
#include "offsets.inc"
#include "stock.h"
#include "common.h"
#include "covercache.h"
#include "libsrc.h"
#include "entries.h"
#include "home.h"
#include "artsplit.h"

#define AS_MAX 20000 /* distinct names kept (the Artists page's MAX_ARTISTS) */
#define AS_PER 8 /* names taken from one field */
#define AS_NAME 255 /* a row's name is cut here (the browsing record's field is 0x100 bytes) */
#define AS_EXC_MAX 64 /* names read from the card's exceptions file */
#define AS_EXC_BYTES 4096 /* the exceptions file is read up to this size */
#define AS_P(w, off) (*(char **)((char *)(w) + (off)))

static int as_fold(int c) { return c >= 'A' && c <= 'Z' ? c + 32 : c; }

/* The saved setting: on or off and the mask kept for it. "1" on with the default mask, "m<n>" on with mask n, "o<n>" off keeping mask n (so a switch turned off and on again keeps the
 * separators), anything else (missing, "0") off with the default mask. */
static void as_parse(int *on, unsigned *mask) {
    unsigned n, v = M1_SPLIT_DEFAULT;
    char *s = m1_read_file(AS_FILE, 32, &n), *p = s;
    *on = 0;
    if (s) {
        while (*p == ' ' || *p == '\t' || *p == '\n' || *p == '\r') ++p;
        if (*p == '1' && (p[1] == 0 || p[1] == '\n' || p[1] == '\r' || p[1] == ' '))
            *on = 1;
        else if (*p == 'm' || *p == 'o') {
            *on = *p == 'm';
            for (v = 0, ++p; *p >= '0' && *p <= '9' && v < 0x100000u; ++p) v = v * 10 + (unsigned)(*p - '0');
            v &= AS_ALL;
        }
        free(s);
    }
    *mask = v;
}

/* The separators in force: 0 off, else the mask (an on setting with no separator splits nothing). */
unsigned as_mask(void) {
    int on;
    unsigned v;
    as_parse(&on, &v);
    return on ? v : 0;
}

/* Settings > Library > Split Artists: the switch (1 on) and the ten separator switches (bit k of the kept mask). A toggle saves first and returns the new state, or -1 when the save failed. */
int as_setting(void) {
    int on;
    unsigned v;
    as_parse(&on, &v);
    return on;
}

static int as_save(int on, unsigned mask) {
    char buf[16], d[8];
    unsigned i = 0, k = 0;
    buf[k++] = on ? 'm' : 'o';
    do d[i++] = (char)('0' + mask % 10), mask /= 10;
    while (mask && i < sizeof d);
    while (i) buf[k++] = d[--i];
    buf[k++] = '\n', buf[k] = 0;
    return home_write_atomic(AS_FILE, buf) != 0 ? -1 : on;
}

int as_toggle(void) {
    int on;
    unsigned v;
    as_parse(&on, &v);
    return as_save(!on, v);
}

int as_sep(int k) {
    int on;
    unsigned v;
    as_parse(&on, &v);
    return k >= 0 && k < AS_SEPS && (v >> k & 1);
}

int as_sep_toggle(int k) {
    int on;
    unsigned v;
    if (k < 0 || k >= AS_SEPS) return -1;
    as_parse(&on, &v);
    v ^= 1u << k;
    return as_save(on, v) < 0 ? -1 : (int)(v >> k & 1);
}

/* The splitter's options: the setting's mask and the built-in exceptions plus the card's file. */
typedef struct {
    m1_split_opts o;
    char *buf;
    const char **ex;
} as_opts_t;

static void as_opts_free(as_opts_t *a) {
    free(a->buf);
    free((void *)a->ex);
    a->buf = (char *)0, a->ex = (const char **)0;
}

/* 1 with the options filled (the caller as_opts_free's them), 0 when the setting is off. */
static int as_opts(as_opts_t *a) {
    const char *const *b = m1_artist_split_exceptions();
    unsigned nb = 0, ne, n = 0, i;
    memset(a, 0, sizeof *a);
    a->o.mask = as_mask();
    if (!a->o.mask) return 0;
    a->o.except = b;
    while (b[nb]) ++nb;
    a->ex = calloc(nb + AS_EXC_MAX + 1, sizeof *a->ex);
    if (!a->ex) return 1; /* the built-in names alone */
    for (ne = 0; ne < nb; ++ne) a->ex[ne] = b[ne];
    a->buf = m1_read_file(AS_EXCEPTIONS, AS_EXC_BYTES, &n);
    for (i = 0; a->buf && i < n && ne < nb + AS_EXC_MAX;) {
        unsigned s = i, e;
        while (i < n && a->buf[i] != '\n') ++i;
        e = i;
        if (i < n) a->buf[i++] = 0;
        while (s < e && (a->buf[s] == ' ' || a->buf[s] == '\t')) ++s;
        while (e > s && (a->buf[e - 1] == ' ' || a->buf[e - 1] == '\t' || a->buf[e - 1] == '\r')) a->buf[--e] = 0;
        if (e > s && a->buf[s] != '#') a->ex[ne++] = a->buf + s;
    }
    a->o.except = a->ex;
    return 1;
}

/* The Home photo pass's session: the options (the mask and the exceptions file) read once for the pass, not once per album. as_session(1) opens it (1 when the setting is on), as_session(0) ends it. */
static as_opts_t as_sess __attribute__((section(".scratch")));
static int as_sess_on __attribute__((section(".scratch")));

int as_session(int open) {
    if (as_sess_on) as_opts_free(&as_sess), as_sess_on = 0;
    if (open) as_sess_on = as_opts(&as_sess);
    return as_sess_on;
}

/* With a session open, the first name of an artist field into out (n bytes): 1 when there is one that fits. */
int as_lead(const char *field, char *out, unsigned n) {
    m1_artist_span sp[1];
    if (!as_sess_on || !field || m1_artist_split(field, sp, 1, &as_sess.o) < 1 || sp[0].n >= n) return 0;
    memcpy(out, sp[0].p, sp[0].n);
    out[sp[0].n] = 0;
    return 1;
}

static int as_blank(const char *f) {
    for (; *f; ++f)
        if (*f != ' ' && *f != '\t') return 0;
    return 1;
}

static int as_eq(const char *a, unsigned an, const char *b, unsigned bn) {
    unsigned i;
    if (an != bn) return 0;
    for (i = 0; i < an; ++i)
        if (as_fold((unsigned char)a[i]) != as_fold((unsigned char)b[i])) return 0;
    return 1;
}

static unsigned as_hash(const char *p, unsigned n) {
    unsigned h = 2166136261u, i;
    for (i = 0; i < n; ++i) h = (h ^ (unsigned)as_fold((unsigned char)p[i])) * 16777619u;
    return h;
}

/* 1 when `field` holds `name` somewhere (ASCII case folded): the cheap test before a field is split. */
static int as_has(const char *field, const char *name, unsigned nn) {
    unsigned i;
    if (!nn) return 1;
    for (; *field; ++field) {
        for (i = 0; i < nn && field[i] && as_fold((unsigned char)field[i]) == as_fold((unsigned char)name[i]); ++i) {
        }
        if (i == nn) return 1;
    }
    return 0;
}

static void *as_new(void) {
    void *q = _create_deque("stSongInfo");
    if (q) deque_init(q);
    return q;
}

int as_is_row(void *rec) { return rec && I(rec, REC_CLASS) == AS_MARK; }

const char *as_row_name(void *row, int *unknown) {
    *unknown = I(row, REC_ID) == -1;
    return cc_str(row, REC_TITLE);
}

/* One row: the name (cut to AS_NAME bytes, not inside a character) as title and artist, class AS_MARK. */
static int as_push_row(void *q, const char *p, unsigned n, int id) {
    unsigned rec[REC_SIZE / 4], before = deque_size(q);
    char name[AS_NAME + 1];
    if (n > AS_NAME) {
        n = AS_NAME;
        while (n && ((unsigned char)p[n] & 0xc0) == 0x80) --n;
    }
    memcpy(name, p, n);
    name[n] = 0;
    memset(rec, 0, sizeof rec);
    I(rec, REC_ID) = id;
    AS_P(rec, REC_TITLE) = name;
    AS_P(rec, REC_ARTIST) = name;
    I(rec, REC_TYPE) = 4;
    I(rec, REC_CLASS) = AS_MARK;
    _deque_push_back(q, rec); /* the stock copy: the record, then every string */
    return deque_size(q) > before;
}

/* A one-row deque (the caller destroys it) for the first name of an artist field, as the Artists page's row of that name: Now Playing's "Look up artist". NULL when the setting is off, the field
 * has no name or there is no memory (the caller then keeps the stock behaviour). */
void *as_first_row(const char *field) {
    as_opts_t op;
    m1_artist_span sp[1];
    void *q = (void *)0;
    if (!field || !as_opts(&op)) return (void *)0;
    if (m1_artist_split(field, sp, 1, &op.o) > 0 && (q = as_new()) && !as_push_row(q, sp[0].p, sp[0].n, 1))
        deque_destroy(q), q = (void *)0;
    as_opts_free(&op);
    return q;
}

void *as_rows(void) {
    as_opts_t op;
    void *all, *out = (void *)0;
    unsigned n, i, k, capn, tsize, nn = 0, unk = 0, *tab = (unsigned *)0;
    m1_artist_span *nm = (m1_artist_span *)0, sp[AS_PER];
    if (!as_opts(&op)) return (void *)0;
    all = cc_songs();
    if (!all) {
        as_opts_free(&op);
        return (void *)0;
    }
    n = deque_size(all);
    capn = n >= AS_MAX / AS_PER ? AS_MAX : n * AS_PER + 1; /* a field names up to AS_PER */
    for (tsize = 64; tsize < capn * 2; tsize <<= 1) {
    }
    tab = calloc(tsize, sizeof *tab);
    nm = calloc(capn, sizeof *nm);
    if (tab && nm) {
        for (i = 0; i < n; ++i) {
            const char *f = cc_str(deque_at(all, i), REC_ARTIST);
            int c = as_blank(f) ? 0 : m1_artist_split(f, sp, AS_PER, &op.o);
            if (c <= 0) {
                unk = 1;
                continue;
            }
            for (k = 0; k < (unsigned)c; ++k) {
                unsigned j = as_hash(sp[k].p, sp[k].n) & (tsize - 1);
                while (tab[j] && !as_eq(nm[tab[j] - 1].p, nm[tab[j] - 1].n, sp[k].p, sp[k].n))
                    j = (j + 1) & (tsize - 1);
                if (!tab[j] && nn < capn && nn < AS_MAX)
                    nm[nn] = sp[k], tab[j] = ++nn; /* the first spelling seen stays */
            }
        }
        out = as_new();
        for (i = 0; out && i < nn; ++i)
            if (!as_push_row(out, nm[i].p, nm[i].n, (int)i + 1)) break;
        if (out && (deque_size(out) < nn || (unk && !as_push_row(out, "Unknown Artist", 14, -1)))) {
            deque_destroy(out);
            out = (void *)0;
        }
        if (out && !deque_size(out)) deque_destroy(out), out = (void *)0;
    }
    free(tab);
    free(nm);
    deque_destroy(all);
    as_opts_free(&op);
    return out;
}

/* The artist's songs: copies of the library's records (a deque the caller destroys), or NULL when none or no memory. */
static void *as_tracks(const char *name, int unknown) {
    as_opts_t op;
    void *all, *res;
    unsigned n, i, k, nn = unknown ? 0 : strlen(name);
    m1_artist_span sp[AS_PER];
    if (!as_opts(&op)) return (void *)0;
    all = cc_songs();
    res = all ? as_new() : (void *)0;
    n = all ? deque_size(all) : 0;
    for (i = 0; res && i < n; ++i) {
        void *rec = deque_at(all, i);
        const char *f = cc_str(rec, REC_ARTIST);
        int c, hit = 0;
        if (unknown)
            hit = as_blank(f) || m1_artist_split(f, sp, AS_PER, &op.o) <= 0;
        else if (!as_blank(f) && as_has(f, name, nn)) {
            c = m1_artist_split(f, sp, AS_PER, &op.o);
            for (k = 0; k < (unsigned)(c > 0 ? c : 0) && !hit; ++k) hit = as_eq(sp[k].p, sp[k].n, name, nn);
        }
        if (hit) _deque_push_back(res, rec);
    }
    if (all) deque_destroy(all);
    as_opts_free(&op);
    if (res && !deque_size(res)) deque_destroy(res), res = (void *)0;
    return res;
}

int as_fill(const char *name, int unknown) {
    void *res = as_tracks(name, unknown), *dst = *(void **)PDEQ_SHOWLIST;
    unsigned n = res ? deque_size(res) : 0;
    if (dst) deque_clear(dst);
    if (dst && n && !lib_deque_swap(dst, res)) deque_assign(dst, res);
    if (res) deque_destroy(res);
    return dst ? (int)n : 0;
}

void *as_load(void *row) {
    unsigned rec[REC_SIZE / 4], card[REC_SIZE / 4];
    int unknown;
    const char *name = as_row_name(row, &unknown);
    memset(rec, 0, sizeof rec), memset(card, 0, sizeof card);
    I(rec, REC_ID) = unknown ? -1 : 1;
    AS_P(rec, REC_TITLE) = AS_P(rec, REC_ARTIST) = (char *)name;
    I(rec, REC_TYPE) = 4;
    loadAlbumList(CLASS_ARTISTS,
                  rec); /* the browsing record as the stock artist page leaves it (its albums are not used) */
    I(card, REC_ID) = ID_ALL_SONGS;
    AS_P(card, REC_ALBUM) = "local_allsong";
    AS_P(card, REC_ARTIST) = (char *)name;
    I(card, REC_TYPE) = 4;
    loadAlbumdetailList(CLASS_ARTIST_ALBUMS, card); /* classinfo[0] = 0xff11, the all-songs flag set */
    return as_fill(name, unknown) ? *(void **)PDEQ_SHOWLIST : (void *)0;
}

int as_albums(void *row, int keep_card, void **albums, unsigned **keys) {
    int unknown;
    const char *name = as_row_name(row, &unknown);
    void *tr = as_tracks(name, unknown), *lib, *res = (void *)0;
    unsigned nt = tr ? deque_size(tr) : 0, nl, i, j, tsize, n, card, *tab;
    *albums = (void *)0, *keys = (unsigned *)0;
    if (!tr) return 0;
    lib = cc_albums();
    for (tsize = 16; tsize < nt * 2; tsize <<= 1) {
    }
    tab = lib ? calloc(tsize, sizeof *tab) : (unsigned *)0;
    for (i = 0; tab && i < nt;
         ++i) { /* the albums the songs name (ASCII case folded, as the library's one row per album name) */
        const char *a = cc_str(deque_at(tr, i), REC_ALBUM);
        j = as_hash(a, strlen(a)) & (tsize - 1);
        while (tab[j] && cc_nocase(cc_str(deque_at(tr, tab[j] - 1), REC_ALBUM), a)) j = (j + 1) & (tsize - 1);
        if (!tab[j] && *a) tab[j] = i + 1;
    }
    nl = lib ? deque_size(lib) : 0;
    if (tab) res = as_new();
    for (i = 0; res && i < nl; ++i) {
        void *r = deque_at(lib, i);
        const char *a = cc_str(r, REC_ALBUM);
        if (I(r, REC_ID) == -1 || !*a) continue; /* "Unknown Album": its songs are in All Songs only */
        j = as_hash(a, strlen(a)) & (tsize - 1);
        while (tab[j] && cc_nocase(cc_str(deque_at(tr, tab[j] - 1), REC_ALBUM), a)) j = (j + 1) & (tsize - 1);
        if (tab[j]) _deque_push_back(res, r);
    }
    free(tab);
    if (lib) deque_destroy(lib);
    deque_destroy(tr);
    if (!res) return 0;
    n = deque_size(res);
    { /* the All Songs record always ends the list (the stock list does: Cover Flow's Songs button reads it); it counts only when kept and with two albums or more (or none, so the page has a tile that opens his songs) */
        unsigned rec[REC_SIZE / 4];
        memset(rec, 0, sizeof rec);
        I(rec, REC_ID) = ID_ALL_SONGS;
        AS_P(rec, REC_ALBUM) = "local_allsong";
        AS_P(rec, REC_ARTIST) = (char *)name;
        I(rec, REC_TYPE) = 4;
        _deque_push_back(res, rec);
    }
    card = keep_card && (n >= 2 || !n); /* with no named album the card is the only route to his songs */
    *albums = res;
    if (n + card) *keys = calloc(n + card, sizeof **keys); /* none: each album keys itself */
    for (i = 0; *keys && i < n; ++i) (*keys)[i] = cc_album_key(deque_at(res, i));
    return (int)(n + card);
}

int as_open_album(void *row, int index) {
    void *albums;
    unsigned *keys;
    char name[AS_NAME + 1];
    int n = as_albums(row, 0, &albums, &keys), r = -1;
    if (index >= 0 && index < n) {
        const char *a = cc_str(deque_at(albums, (unsigned)index), REC_ALBUM);
        unsigned i;
        for (i = 0; a[i] && i < AS_NAME; ++i) name[i] = a[i];
        name[i] = 0;
        r = cc_find_album(name);
    }
    if (albums) deque_destroy(albums);
    free(keys);
    return r >= 0 ? cc_open_album((void *)0, 0, r) : -1;
}
