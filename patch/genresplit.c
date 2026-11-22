/* Genre split: the Genres index and a genre's songs when one genre field names several genres (patch/genresplit.h, docs/modules/artists.md "Split Genres").
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 * Based on a contribution by powkakashi (GitHub issue 18): the index from the stock genre list, the one stock query per tag, the semicolon-only default.
 *
 * Stateless: the index lives only in the Genres page's rows, and a name's songs are answered from the stock genre query, once per tag that names it (gs_fill). No songtable read of our own, no
 * second copy of the library to go stale, and no SQL: a tag the stock genre list gave is replayed through the stock 0xff09 query exactly as a stock row tap would ask it.
 */
#include "offsets.inc"
#include "stock.h"
#include "common.h"
#include "covercache.h"
#include "libsrc.h"
#include "entries.h"
#include "home.h"
#include "podcasts.h"
#include "genresplit.h"

#define GS_MAX 20000 /* distinct names kept (the Genres page's MAX_ARTISTS) */
#define GS_PER 8 /* names taken from one tag */
#define GS_NAME 255 /* the longest name a row carries whole (the Songs page's sg.name is 0x100 bytes) */
#define GS_EXC_MAX 64 /* names read from the card's exceptions file */
#define GS_EXC_BYTES 4096 /* the exceptions file is read up to this size */
#define GS_TAGS 512 /* raw tags one name may be answered from (one stock query each) */
#define GS_TAG_MAX 300 /* longer raw tags are left out (see gs_long): what the query filter's buffer takes escaped */
#define GS_P(w, off) (*(char **)((char *)(w) + (off)))

static int gs_fold(int c) { return c >= 'A' && c <= 'Z' ? c + 32 : c; }

/* The saved setting: on or off and the mask kept for it. "1" on with GS_DEFAULT, "m<n>" on with mask n, "o<n>" off keeping mask n (so a switch turned off and on again keeps the separators),
 * anything else (missing, "0") off with the default mask. */
static void gs_parse(int *on, unsigned *mask) {
    unsigned n, v = GS_DEFAULT;
    char *s = m1_read_file(GS_FILE, 32, &n), *p = s;
    *on = 0;
    if (s) {
        while (*p == ' ' || *p == '\t' || *p == '\n' || *p == '\r') ++p;
        if (*p == '1' && (p[1] == 0 || p[1] == '\n' || p[1] == '\r' || p[1] == ' '))
            *on = 1;
        else if (*p == 'm' || *p == 'o') {
            *on = *p == 'm';
            for (v = 0, ++p; *p >= '0' && *p <= '9' && v < 0x100000u; ++p) v = v * 10 + (unsigned)(*p - '0');
            v &= GS_ALL;
        }
        free(s);
    }
    *mask = v;
}

/* The separators in force: 0 off, else the mask (an on setting with no separator splits nothing). */
unsigned gs_mask(void) {
    int on;
    unsigned v;
    gs_parse(&on, &v);
    return on ? v : 0;
}

int gs_setting(void) {
    int on;
    unsigned v;
    gs_parse(&on, &v);
    return on;
}

static int gs_save(int on, unsigned mask) {
    char buf[16], d[8];
    unsigned i = 0, k = 0;
    buf[k++] = on ? 'm' : 'o';
    do d[i++] = (char)('0' + mask % 10), mask /= 10;
    while (mask && i < sizeof d);
    while (i) buf[k++] = d[--i];
    buf[k++] = '\n', buf[k] = 0;
    return home_write_atomic(GS_FILE, buf) != 0 ? -1 : on;
}

int gs_toggle(void) {
    int on;
    unsigned v;
    gs_parse(&on, &v);
    return gs_save(!on, v);
}

int gs_sep(int k) {
    int on;
    unsigned v;
    gs_parse(&on, &v);
    return k >= 0 && k < 32 && (v & GS_ALL) >> k & 1;
}

int gs_sep_toggle(int k) {
    int on;
    unsigned v;
    if (k < 0 || k >= 32 || !(GS_ALL >> k & 1)) return -1;
    gs_parse(&on, &v);
    v ^= 1u << k;
    return gs_save(on, v) < 0 ? -1 : (int)(v >> k & 1);
}

/* Genres that hold a separator and are one genre whatever the mask. Every name is from a published genre list, read 2026-11-22, and is there because a part of it is not a genre by itself
 * ("Stage", "Singer", "Drum"); a name that joins two genres of the same list (Pop/Rock, Hip-Hop/Rap, Funk / Soul, Jazz+Funk) is left to the mask. An exception only protects its own bytes, so
 * "R&B/Soul" and "Contemporary R&B; Soul" still give their names.
 *   ID3v1 / Winamp (mutagen _constants.py GENRES): R&B, Rock & Roll, Drum & Bass
 *   Discogs genres (Database Guidelines 9; the style guide drops the second comma): Folk, World, & Country, Stage & Screen, Brass & Military
 *   Apple Music (the iTunes genres service, id 34): Singer/Songwriter, Brass & Woodwinds, Devotional & Spiritual, Fitness & Workout, Praise & Worship (and R&B, Rock & Roll)
 *   MusicBrainz genres: rhythm & blues (as "british rhythm & blues"), slowed & reverb (and r&b, praise & worship)
 *   AllMusic genres: Stage & Screen, R&B.  Beatport genres: Melodic House & Techno (and Drum & Bass, R&B) */
static const char *const gs_builtin[] = {"R&B",
                                         "Rhythm & Blues",
                                         "Rock & Roll",
                                         "Drum & Bass",
                                         "Folk, World, & Country",
                                         "Folk, World & Country",
                                         "Stage & Screen",
                                         "Brass & Military",
                                         "Brass & Woodwinds",
                                         "Devotional & Spiritual",
                                         "Fitness & Workout",
                                         "Praise & Worship",
                                         "Slowed & Reverb",
                                         "Melodic House & Techno",
                                         "Singer/Songwriter",
                                         0};
#define GS_BUILTIN (sizeof gs_builtin / sizeof *gs_builtin - 1)

/* The splitter's options: the setting's mask and the built-in genre exceptions plus the card's file. The built-in artist exceptions (AC/DC, Simon & Garfunkel) are left out: they are artists. */
typedef struct {
    m1_split_opts o;
    char *buf;
    const char **ex;
} gs_opts_t;

static void gs_opts_free(gs_opts_t *a) {
    free(a->buf);
    free((void *)a->ex);
    a->buf = (char *)0, a->ex = (const char **)0;
}

/* 1 with the options filled (the caller gs_opts_free's them), 0 when the setting is off. */
static int gs_opts(gs_opts_t *a) {
    unsigned ne, n = 0, i;
    memset(a, 0, sizeof *a);
    a->o.mask = gs_mask();
    if (!a->o.mask) return 0;
    a->o.except = gs_builtin;
    a->ex = calloc(GS_BUILTIN + GS_EXC_MAX + 1, sizeof *a->ex);
    if (!a->ex) return 1; /* the built-in names alone */
    for (ne = 0; ne < GS_BUILTIN; ++ne) a->ex[ne] = gs_builtin[ne];
    a->buf = m1_read_file(GS_EXCEPTIONS, GS_EXC_BYTES, &n);
    for (i = 0; a->buf && i < n && ne < GS_BUILTIN + GS_EXC_MAX;) {
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

static int gs_blank(const char *f) {
    for (; *f; ++f)
        if (*f != ' ' && *f != '\t') return 0;
    return 1;
}

static int gs_eq(const char *a, unsigned an, const char *b, unsigned bn) {
    unsigned i;
    if (an != bn) return 0;
    for (i = 0; i < an; ++i)
        if (gs_fold((unsigned char)a[i]) != gs_fold((unsigned char)b[i])) return 0;
    return 1;
}

static unsigned gs_hash(const char *p, unsigned n) {
    unsigned h = 2166136261u, i;
    for (i = 0; i < n; ++i) h = (h ^ (unsigned)gs_fold((unsigned char)p[i])) * 16777619u;
    return h;
}

/* 1 when `tag` holds `name` somewhere (ASCII case folded): the cheap test before a tag is split. */
static int gs_has(const char *tag, const char *name, unsigned nn) {
    unsigned i;
    if (!nn) return 1;
    for (; *tag; ++tag) {
        for (i = 0; i < nn && tag[i] && gs_fold((unsigned char)tag[i]) == gs_fold((unsigned char)name[i]); ++i) {
        }
        if (i == nn) return 1;
    }
    return 0;
}

static void *gs_new(void) {
    void *q = _create_deque("stSongInfo");
    if (q) deque_init(q);
    return q;
}

int gs_is_row(void *rec) { return rec && I(rec, REC_CLASS) == GS_MARK; }

/* One row: the name (at most GS_NAME bytes: it comes from a tag of at most GS_TAG_MAX) as title and artist, class GS_MARK. */
static int gs_push_row(void *q, const char *p, unsigned n, int id) {
    unsigned rec[REC_SIZE / 4], before = deque_size(q);
    char name[GS_NAME + 1];
    if (n > GS_NAME) return 0;
    memcpy(name, p, n);
    name[n] = 0;
    memset(rec, 0, sizeof rec);
    I(rec, REC_ID) = id;
    GS_P(rec, REC_TITLE) = name;
    GS_P(rec, REC_ARTIST) = name;
    I(rec, REC_TYPE) = 4;
    I(rec, REC_CLASS) = GS_MARK;
    _deque_push_back(q, rec); /* the stock copy: the record, then every string */
    return deque_size(q) > before;
}

/* The stock genre list taken from *pdeq_showlist (lib_take_list: the records change owner, none is copied, *pdeq_showlist is left empty); NULL when the query fails or there is no memory. */
static void *gs_stock_list(void) {
    if (loadLocalClassList(CLASS_GENRES) <= 0) return (void *)0;
    return lib_take_list(*(void **)PDEQ_SHOWLIST);
}

/* Order of the index: the Artists page's name order (cc_name_keys / cc_key_cmp: digit runs by value, ASCII case folded, "The " dropped, a CJK name by its pinyin initials), so the A-Z sections
 * the page cuts by cc_name_initial stay in order. Ties keep the first-seen order. */
static const char **gs_key __attribute__((section(".scratch")));
static const char *gs_nz_text(const void *ctx, unsigned i) { return ((const char *const *)ctx)[i]; }
static int gs_cmp(unsigned a, unsigned b) {
    int d = cc_key_cmp(gs_key[a], gs_key[b]);
    return d ? d : a < b ? -1 : a > b;
}

/* idx[0 .. nn) the order of the names nm[0 .. nn); the first-seen order when there is no memory. */
static void gs_order(const m1_artist_span *nm, unsigned nn, unsigned *idx) {
    unsigned i, total = 0, at = 0;
    char *pool;
    const char **nz;
    for (i = 0; i < nn; ++i) idx[i] = i, total += nm[i].n + 1;
    nz = calloc(nn ? nn : 1, sizeof *nz);
    pool = calloc(1, total ? total : 1);
    if (nz && pool) {
        for (i = 0; i < nn; ++i) {
            memcpy(pool + at, nm[i].p, nm[i].n);
            pool[at + nm[i].n] = 0;
            nz[i] = pool + at;
            at += nm[i].n + 1;
        }
        gs_key = cc_name_keys(nn, gs_nz_text, nz);
        if (gs_key) cc_heapsort(idx, nn, gs_cmp);
        free((void *)gs_key);
        gs_key = (const char **)0;
    }
    free((void *)nz);
    free(pool);
}

/* A tag's names, those beyond GS_NAME bytes dropped (a row carries its name whole, so it finds its tags again); 0 when none is left: the tag then goes to the Unknown row. */
static int gs_names(const char *tag, m1_artist_span *sp, gs_opts_t *op) {
    int c = m1_artist_split(tag, sp, GS_PER, &op->o), i, n = 0;
    for (i = 0; i < c; ++i)
        if (sp[i].n <= GS_NAME) sp[n++] = sp[i];
    return n;
}

/* A tag the index and the queries both leave out: one whose escaped text could not be asked in the query filter's buffer (patch/pcmodel.c pq_filter). */
static int gs_long(const char *f) { return strlen(f) > GS_TAG_MAX; }

void *gs_rows(void) {
    gs_opts_t op;
    void *list, *out = (void *)0;
    unsigned nt, i, k, capn, tsize, nn = 0, unk = 0, *tab = (unsigned *)0, *idx;
    m1_artist_span *nm = (m1_artist_span *)0, sp[GS_PER];
    if (!gs_opts(&op)) return (void *)0;
    list = gs_stock_list();
    if (!list) {
        gs_opts_free(&op);
        return (void *)0;
    }
    nt = deque_size(list);
    capn = nt >= GS_MAX / GS_PER ? GS_MAX : nt * GS_PER + 1; /* a tag names up to GS_PER */
    for (tsize = 64; tsize < capn * 2; tsize <<= 1) {
    }
    tab = calloc(tsize, sizeof *tab);
    nm = calloc(capn, sizeof *nm);
    if (tab && nm) {
        for (i = 0; i < nt; ++i) {
            const char *f = cc_str(deque_at(list, i), REC_TITLE);
            int c;
            if (gs_long(f)) continue;
            c = I(deque_at(list, i), REC_ID) == -1 || gs_blank(f) ? 0 : gs_names(f, sp, &op);
            if (c <= 0) { /* a tag that names nothing (blank, or the stock Unknown Genre row) */
                unk = 1;
                continue;
            }
            for (k = 0; k < (unsigned)c; ++k) {
                unsigned j = gs_hash(sp[k].p, sp[k].n) & (tsize - 1);
                while (tab[j] && !gs_eq(nm[tab[j] - 1].p, nm[tab[j] - 1].n, sp[k].p, sp[k].n))
                    j = (j + 1) & (tsize - 1);
                if (!tab[j] && nn < capn && nn < GS_MAX)
                    nm[nn] = sp[k], tab[j] = ++nn; /* the first spelling seen stays */
            }
        }
        idx = calloc(nn ? nn : 1, sizeof *idx);
        if (idx) gs_order(nm, nn, idx);
        out = idx ? gs_new() : (void *)0;
        for (i = 0; out && i < nn; ++i)
            if (!gs_push_row(out, nm[idx[i]].p, nm[idx[i]].n, (int)i + 1)) break;
        free(idx);
        if (out && (deque_size(out) < nn || (unk && !gs_push_row(out, "Unknown Genre", 13, -1)))) {
            deque_destroy(out);
            out = (void *)0;
        }
    }
    free(tab);
    free(nm);
    deque_destroy(list);
    gs_opts_free(&op);
    return out;
}

/* The name's songs: copies of the stock genre query's records, one query per tag that names it (a deque the caller destroys), or NULL when no tag names it or there is no memory. Every song of
 * a tag belongs to each name the tag makes, so the results concatenate without a duplicate: one song has one tag. */
static void *gs_tracks(const char *name, int unknown) {
    gs_opts_t op;
    void *list, *res, *rows, *match[GS_TAGS];
    unsigned nt, i, k, n, nn = unknown ? 0 : strlen(name), hits = 0;
    m1_artist_span sp[GS_PER];
    if (!gs_opts(&op)) return (void *)0;
    list = gs_stock_list();
    if (!list) {
        gs_opts_free(&op);
        return (void *)0;
    }
    nt = deque_size(list);
    for (i = 0; i < nt && hits < GS_TAGS; ++i) {
        void *r = deque_at(list, i);
        const char *tag = cc_str(r, REC_TITLE);
        int c, hit = 0;
        if (gs_long(tag)) continue;
        if (unknown) { /* the Unknown Genre row: the stock one and every tag that names nothing, each asked as its own row would be */
            if (I(r, REC_ID) == -1 || gs_blank(tag) || gs_names(tag, sp, &op) <= 0) match[hits++] = r;
            continue;
        }
        if (I(r, REC_ID) == -1 || gs_blank(tag) || !gs_has(tag, name, nn)) continue;
        c = gs_names(tag, sp, &op);
        for (k = 0; k < (unsigned)(c > 0 ? c : 0) && !hit; ++k) hit = gs_eq(sp[k].p, sp[k].n, name, nn);
        if (hit) match[hits++] = r;
    }
    res = gs_new();
    for (i = 0; res && i < hits; ++i) {
        songs_genre_record(cc_str(match[i], REC_TITLE), I(match[i], REC_ID) == -1);
        pc_genre_exact = I(match[i], REC_ID) == -1
                             ? (const char *)0
                             : cc_str(match[i], REC_TITLE); /* the whole tag, exactly (pq_filter) */
        k = (unsigned)loadLocalClassList(CLASS_GENRE_SONGS);
        pc_genre_exact = (const char *)0;
        if (k > 0 && (rows = *(void **)PDEQ_SHOWLIST)) {
            n = deque_size(rows);
            for (k = 0; k < n; ++k) {
                unsigned before = deque_size(res);
                _deque_push_back(res, deque_at(rows, k));
                if (deque_size(res) == before) break; /* (no memory: the songs so far) */
            }
            deque_clear(rows); /* (copied: the next query starts from an empty list) */
        }
    }
    deque_destroy(list);
    gs_opts_free(&op);
    if (res && !deque_size(res)) deque_destroy(res), res = (void *)0;
    return res;
}

int gs_fill(const char *name, int unknown) {
    void *res = gs_tracks(name, unknown), *dst = *(void **)PDEQ_SHOWLIST;
    unsigned n = res ? deque_size(res) : 0;
    if (dst) deque_clear(dst);
    if (dst && n && !lib_deque_swap(dst, res)) deque_assign(dst, res);
    if (res) deque_destroy(res);
    return dst ? (int)n : 0;
}
