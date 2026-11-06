/* The cover cache and the album helpers Cover Flow and the Albums grid share.
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE). The cache design follows q2-pod's Cover Flow.
 *
 * One JPEG per album, /mnt/mmc/.m1plus/covers/r<key>-168.jpg, written by the one worker thread below (started by
 * Cover Flow's Preparing screen, its Rebuild Covers, or the Albums page in the background); key = FNV-1a of the artist then the album, so the same album has the same file
 * wherever it is listed. Readers decode through the stock image loader (JPEG and PNG to RGBA8888) and
 * reduce the centred square to the size they draw: nearest for Cover Flow's depth textures, an area
 * average for the grid's small tiles. UI thread only. docs/architecture.md section 4.
 */
#include "offsets.inc"

#ifdef CF_HOST
#include <stdlib.h>
#include <string.h>
#else
#include "stock.h"
#include "home.h"
#include "podcasts.h"
#include "pccover.h"
#endif
#include "covercache.h"
#include "durations.h"

/* FNV-1a over a string, with a separator so "ab"+"c" and "a"+"bc" differ (q2-pod). */
unsigned cc_fnv(unsigned h, const char *s) {
    for (; s && *s; ++s) h = (h ^ (unsigned char)*s) * 16777619u;
    return h * 16777619u;
}

/* One source pixel over black (straight alpha; the offsets of r, g, b, a in the pixel), into the sums. The fully
 * opaque pixel, which is nearly all of them, takes no multiplication. -Oz would call this per pixel. */
static inline __attribute__((always_inline)) void over_black(const unsigned char *px, unsigned ro, unsigned go,
                                                             unsigned bo, unsigned ao, unsigned *r, unsigned *g,
                                                             unsigned *b) {
    unsigned a = px[ao];
    if (a == 255)
        *r += px[ro], *g += px[go], *b += px[bo];
    else
        *r += px[ro] * a / 255, *g += px[go] * a / 255, *b += px[bo] * a / 255;
}

/* floor((start + n * inc) / den) for n = 0, 1, 2, ..., exactly, without a division per step: the quotient and the
 * remainder advance together. A row's x mapping costs two divisions instead of one per pixel. */
typedef struct {
    unsigned q, r, dq, dr, den;
} stepper_t;

static inline __attribute__((always_inline)) void step_init(stepper_t *s, unsigned start, unsigned inc, unsigned den) {
    s->q = start / den, s->r = start % den, s->dq = inc / den, s->dr = inc % den, s->den = den;
}

static inline __attribute__((always_inline)) void step_next(stepper_t *s) {
    s->q += s->dq, s->r += s->dr;
    if (s->r >= s->den) s->r -= s->den, ++s->q;
}

void cc_sample(const unsigned char *data, unsigned w, unsigned h, unsigned stride, const unsigned char *at,
               unsigned size, unsigned *out) {
    unsigned side = w < h ? w : h, x, y, ro = at[0], go = at[1], bo = at[2], ao = at[3];
    const unsigned char *base = data + (h - side) / 2 * stride + (w - side) / 2 * 4;
    for (y = 0; y < size; ++y) {
        const unsigned char *line = base + y * side / size * stride;
        stepper_t sx;
        step_init(&sx, 0, side, size); /* x * side / size */
        for (x = 0; x < size; ++x, step_next(&sx)) {
            unsigned r = 0, g = 0, b = 0;
            over_black(line + sx.q * 4, ro, go, bo, ao, &r, &g, &b);
            *out++ = 0xff000000u | r | g << 8 | b << 16;
        }
    }
}

int ar_init(ar_t *a, unsigned ow, unsigned oh, unsigned tw, unsigned th) {
    if (!ow || !oh || !tw || !th || tw > AR_MAX || ow > 8192 || oh > 8192 || ow * oh > AR_LIMIT) return 0;
    memset(a->acc, 0, tw * 3 * sizeof a->acc[0]);
    a->ow = ow, a->oh = oh, a->tw = tw, a->th = th, a->total = ow * oh, a->j = a->ty = 0, a->rend = oh;
    return 1;
}

/* Target cell k covers [k * ow, (k + 1) * ow) and source pixel i [i * tw, (i + 1) * tw), the same units, so a pixel's share of a cell is an integer: the
 * horizontal sums of one source row (each at most 255 * ow), then the vertical weights the same way over the rows; a pixel or a row meets one cell, or two. */
void ar_push(ar_t *a, const unsigned char *px, unsigned step, unsigned ro, unsigned go, unsigned bo, unsigned ao,
             ar_emit_t emit, void *user) {
    unsigned ow = a->ow, tw = a->tw, i, x, k = 0, cell = ow, p = 0, e, q, *h = a->h;
    memset(h, 0, tw * 3 * sizeof h[0]);
    for (i = 0; i < ow; ++i, px += step) {
        unsigned r = px[ro], g = px[go], b = px[bo], end = p + tw;
        if (ao < step && px[ao] != 255) {
            unsigned al = px[ao];
            r = r * al / 255, g = g * al / 255, b = b * al / 255;
        }
        while (p < end) { /* the part of this pixel in cell k */
            e = end < cell ? end : cell, q = e - p;
            h[3 * k] += q * r, h[3 * k + 1] += q * g, h[3 * k + 2] += q * b;
            p = e;
            if (p == cell) ++k, cell += ow;
        }
    }
    p = a->j++ * a->th;
    for (cell = p + a->th; p < cell;) { /* this row's share of target row ty */
        e = cell < a->rend ? cell : a->rend, q = e - p;
        for (x = 0; x < tw * 3; ++x) a->acc[x] += q * h[x];
        p = e;
        if (p == a->rend) {
            for (x = 0; x < tw * 3; ++x) a->out[x] = (unsigned char)((a->acc[x] + a->total / 2) / a->total);
            memset(a->acc, 0, tw * 3 * sizeof a->acc[0]);
            ++a->ty, a->rend += a->oh;
            emit(user, a->out);
        }
    }
}

typedef struct {
    unsigned *out, size;
} box_out_t;

static void box_emit(void *user, const unsigned char *rgb) {
    box_out_t *o = user;
    unsigned x;
    for (x = 0; x < o->size; ++x, rgb += 3) *o->out++ = 0xff000000u | rgb[0] | rgb[1] << 8 | rgb[2] << 16;
}

/* Every destination pixel is the exact area average of the source its box covers: edge pixels count for the fraction of them inside (ar_push), so a 168 px
 * cover reduced to 144 or 92 reads cleanly where nearest sampling would shimmer, and no ratio blurs more than the box itself. */
void cc_box(const unsigned char *data, unsigned w, unsigned h, unsigned stride, const unsigned char *at, unsigned size,
            unsigned *out) {
    ar_t a;
    unsigned side = w < h ? w : h, y;
    const unsigned char *base = data + (h - side) / 2 * stride + (w - side) / 2 * 4;
    box_out_t o;
    o.out = out, o.size = size;
    if (!ar_init(&a, side, side, size, size)) {
        cc_sample(data, w, h, stride, at, size, out);
        return;
    }
    for (y = 0; y < side; ++y) ar_push(&a, base + y * stride, 4, at[0], at[1], at[2], at[3], box_emit, &o);
}

/* Stock's resize 0x5e00bc (toolsGetAlbumCover / toolsGetExternCover) with the picture decoded to w x h and t the requested size on both sides. The wider side (the
 * width when square) is cut to t when it is over t, the other side follows by single precision division (the FPU sequence at 0x5e0200..0x5e0228 and, for a
 * portrait, 0x5e02c4..0x5e02ec, so the same truncation); a side exactly t falls through to the resize with the plain request, t x t (0x5e02f0..0x5e02f8, a stretch of
 * the other side); a smaller picture is kept as it is (a copy of the file, or the decoded rows encoded again). */
int cc_stock_fit(unsigned w, unsigned h, unsigned t, unsigned *tw, unsigned *th) {
    float f;
    if (w >= h) {
        if (t < w) {
            f = (float)(int)w /
                (float)(int)t; /* (signed: an unsigned conversion would be a libgcc call, which the payload has not) */
            *tw = t, *th = (unsigned)(int)((float)(int)h / f);
        } else if (w == t)
            *tw = *th = t;
        else
            return 0;
    } else {
        if (t < h) {
            f = (float)(int)h / (float)(int)t;
            *th = t, *tw = (unsigned)(int)((float)(int)w / f);
        } else if (h == t)
            *tw = *th = t;
        else
            return 0;
    }
    if (!*tw) *tw = 1;
    if (!*th) *th = 1;
    return 1;
}

void cc_stock_dims(unsigned w0, unsigned h0, unsigned ncomp, unsigned *w, unsigned *h) {
    unsigned m = w0 > h0 ? w0 : h0, d = m < 1024 ? 1 : m <= 2048 ? 2 : m <= 4096 ? 4 : 8;
    if (w0 <= 1024 && h0 <= 1024 && ncomp >= 3) d = 1; /* 0x5de8cc..0x5de8e4: the whole picture */
    *w = (w0 + d - 1) / d, *h = (h0 + d - 1) / d;
}

#ifndef CF_HOST
#define P(r, off) (*(char **)((char *)(r) + (off)))
#define I(r, off) (*(int *)((char *)(r) + (off)))
#define CF_STR_(x) #x
#define CF_STR(x) CF_STR_(x)

const char *cc_str(void *r, int field) {
    const char *s = r ? P(r, field) : (const char *)0;
    return s ? s : "";
}

unsigned cc_key_of(const char *artist, const char *album) {
    unsigned h = cc_fnv(cc_fnv(FNV_SEED, artist), album);
    return h | !h;
}

unsigned cc_album_key(void *r) { return cc_key_of(cc_str(r, REC_ARTIST), cc_str(r, REC_ALBUM)); }

/* ART_DIR/r<key>-168.jpg<suffix>: the cache files carry their size, so the 140 px files of the earlier
 * builds are never scaled up, and the prefix says how the cover was made: r = from an album's first track (what f meant) by the area average of pv_cover (art_embedded, art_folder
 * below). It supersedes f (first track, stock's bilinear resize) and the unprefixed files (any track): neither is read again, so every cover is made once more. Bump the letter when the way a
 * cover is made changes. out holds at least 64 bytes. */
char *cc_path(char *out, unsigned size, unsigned key, const char *suffix) {
    snprintf(out, size, ART_DIR "/r%08x-" CF_STR(ART_SIZE) ".jpg%s", key, suffix);
    return out;
}

long cc_file_size(const char *path) {
    void *f = fopen(path, "rb");
    long size = f && !fseek(f, 0, 2) ? ftell(f) : -1;
    if (f) fclose(f);
    return size;
}

/* The url of key's cache file when it exists and holds a picture (an empty file is the "no art"
 * marker), else NULL. */
const char *cc_url(char *out, unsigned key) {
    if (!key) return (const char *)0;
    memcpy(out, "file://", 8);
    cc_path(out + 7, 73, key, "");
    return cc_file_size(out + 7) > 0 ? out : (const char *)0; /* a missing file does not open: -1 */
}

/* A song's or an album's cover: the cache is keyed by the library's album record, which lists an album once under the artist of
 * one of its tracks, so a track of a compilation (its own artist) finds no file under its own key, and the album of that name has it. */
unsigned cc_cover_key(void *albums, unsigned key, const char *album, char *url) {
    char tmp[80];
    unsigned n = albums ? deque_size(albums) : 0, i;
    if (!url) url = tmp;
    if (cc_url(url, key)) return key;
    for (i = 0; album && *album && i < n; ++i) {
        void *r = deque_at(albums, i);
        if (I(r, REC_ID) != -1 && !cc_nocase(cc_str(r, REC_ALBUM), album) && cc_url(url, cc_album_key(r)))
            return cc_album_key(r);
    }
    url[0] = 0;
    return key;
}

/* A decoded image reduced to size x size over black. Only the four 32-bit formats; the stock loader
 * decodes JPEG and PNG to RGBA8888 with straight alpha. The image manager's copy is only read, and a
 * cover's load is dropped again at once (unload), as the stock cover rows do; w is any widget (the
 * loader needs one). */
int cc_decode(void *w, const char *url, int unload, unsigned size, int box, unsigned *out) {
    static const unsigned char at[4][4] = BITMAP_RGBA_AT;
    unsigned bitmap[32]; /* bitmap_t is 0x48 bytes */
    unsigned iw, ih, format;
    const unsigned char *data;
    memset(bitmap, 0, sizeof bitmap);
    if (widget_load_image(w, url, bitmap)) return 0;
    iw = bitmap[0], ih = bitmap[1];
    format = (unsigned)(*(unsigned short *)((char *)bitmap + BITMAP_FORMAT)) - 1u;
    data = format < 4 && iw && ih && iw <= 4096 && ih <= 4096 ? bitmap_lock_buffer_for_read(bitmap)
                                                              : (const unsigned char *)0;
    if (data) {
        (box ? cc_box : cc_sample)(data, iw, ih, bitmap_get_line_length(bitmap), at[format], size, out);
        bitmap_unlock_buffer(bitmap);
    }
    if (unload) widget_unload_image(w, bitmap);
    return data != (const unsigned char *)0;
}

/* A stock list copied into a deque of our own, so later stock queries cannot pull it away. */
void *cc_copy_list(void *list) {
    void *d = _create_deque("stSongInfo");
    if (!d) return d;
    deque_init(d);
    deque_assign(d, list);
    return d;
}

static int cc_lfail __attribute__((section(
    ".scratch"))); /* the last cc_albums / cc_songs failed to copy a non-empty list, as opposed to an empty one: cc_list_failed */

/* A stock list class read into *pdeq_showlist and copied. NULL when empty (cc_lfail 0: stock's loadLocalClassList returns the deque's size, so a query that failed before any row reads as empty too) or when
 * the copy failed (cc_lfail 1: rows but no memory for the copy). */
static void *cc_class_copy(int cls) {
    void *list, *copy;
    cc_lfail = 0;
    if (loadLocalClassList(cls) <= 0) return (void *)0;
    list = *(void **)PDEQ_SHOWLIST;
    if (!list || !deque_size(list)) return (void *)0;
    copy = cc_copy_list(list);
    if (copy && !deque_size(copy)) {
        deque_destroy(copy);
        copy = (void *)0;
    }
    if (!copy) cc_lfail = 1; /* (the source had rows) */
    return copy;
}

/* The albums, exactly as the stock Albums page lists them (loadLocalClassList 0xf003 = getAllAlbum into
 * *pdeq_showlist), copied. NULL when the library has none (or the read failed: cc_list_failed). */
void *cc_albums(void) { return cc_class_copy(CLASS_ALBUMS); }

/* The library's songs as the Songs page lists them (loadLocalClassList 0xf001 = getAllMusic into *pdeq_showlist), copied; NULL when there are none (or the read failed: cc_list_failed). */
void *cc_songs(void) { return cc_class_copy(CLASS_ALL_SONGS); }

int cc_list_failed(void) { return cc_lfail; }

extern int album_open(
    unsigned cls,
    void *
        row); /* patch/albumpage.c: our album page on an album row; 0 opened, -1 not tried, -2 tried and left (the tracks' query replaced the list) */

/* The stock album list the album page is opened from (the Albums rows, or an artist's / composer's): into *pdeq_showlist, the browsing record set. */
static void cc_album_list(void *artist_row, unsigned scope) {
    if (artist_row)
        loadAlbumList(scope == CLASS_COMPOSERS ? CLASS_COMPOSERS : CLASS_ARTISTS, deque_at(artist_row, 0));
    else
        loadAlbumList(CLASS_ALBUMS, (void *)0);
}

/* Open the album page on row `index` of the album list the page was built from, the way a stock Albums row does. Ours first (patch/albumpage.c: album_open takes the album row,
 * runs loadAlbumdetailList on it and opens ui/m1plus_album.bin); when it cannot (the kill switch, the All albums card, a window that will not open) the plain stock albuminfo_page, below:
 * the stock list the page's own copy was made from goes back into
 * *pdeq_showlist (albuminfo_page_init reads the album row from it), the cover-task list is rebuilt
 * from it (album_page_init's albumcoverinfo_init, which add_albumcover_task indexes) and released, and
 * the page opens with the context the row handler builds, the browsing class in the low 16 bits and the
 * row in the high ones (@0x523d94). Library: loadAlbumList(0xf003, 0), class 0xf003. Scoped to an artist
 * (artist_row: a deque holding our copy of the artist's row): loadAlbumList(0xf004, artist) puts the
 * artist into the browsing record (and the cover-task list is rebuilt for it), class 0xff01; the All
 * albums card is the stock All songs row of that list, which the page loads as the artist's every
 * song. Both repeat on every open: the stock queries since our copy was made may have reused the record.
 *
 * albumcoverinfo_init leaves albumcover_taskstate (0xa05a18) at 2, which parks the cover thread
 * (parse_albumcovertask_thd sleeps while it is 2); only the batch queuers (batchadd_albumcover_task ->
 * local_albumsmallcover_task, run by the stock Albums list right after) set it back to 1, and
 * albuminfo_page_init's add_albumcover_task(row, 1) does not. Without this call the page's cover task
 * waits forever and the header keeps its placeholder. batchadd_albumcover_task(0, 0) queues nothing (the
 * page clears and refills the task list itself) and sets the state to 1; the page's own 500 ms timer
 * (@0x5261d8) then picks the finished /tmp/abp file up. Returns -1 when the row is not in the list. */
int cc_open_album(void *artist_row, unsigned scope, int index) {
    void *list;
    int r;
    unsigned cls = !artist_row ? CLASS_ALBUMS : scope == CLASS_COMPOSERS ? CLASS_COMPOSER_ALBUMS : CLASS_ARTIST_ALBUMS;
    cc_album_list(artist_row, scope);
    list = *(void **)PDEQ_SHOWLIST;
    if (!list || (unsigned)index >= deque_size(list)) return -1;
    r = album_open(cls, deque_at(list, (unsigned)index)); /* our page (patch/albumpage.c) */
    if (r == 0) return 0;
    if (r < -1) { /* it queried the tracks: the album list again for the stock page */
        cc_album_list(artist_row, scope);
        list = *(void **)PDEQ_SHOWLIST;
        if (!list || (unsigned)index >= deque_size(list)) return -1;
    }
    albumcoverinfo_init(list);
    batchadd_albumcover_task(0, 0); /* no row queued: it only ends as stock's Albums list does, taskstate = 1 */
    navigator_to_with_context("albuminfo_page", (const void *)(cls | (unsigned)index << 16));
    return 0;
}

/* The row of the library's album list (the stock Albums rows, class 0xf003) whose album is `album` (ASCII case-insensitive:
 * the list groups by album COLLATE NOCASE, so there is one row per name; "Unknown Album", id -1, is never matched), or -1 when
 * the name is empty or no row has it. Loads the list into *PDEQ_SHOWLIST as cc_open_album does and changes nothing else; the
 * row number is what cc_open_album(NULL, 0, row) opens (it loads the list again). */
int cc_find_album(const char *album) {
    void *list;
    unsigned i, n;
    if (!album || !*album) return -1;
    loadAlbumList(CLASS_ALBUMS, (void *)0);
    list = *(void **)PDEQ_SHOWLIST;
    n = list ? deque_size(list) : 0;
    for (i = 0; i < n; i++) {
        void *r = deque_at(list, i);
        if (*(int *)((char *)r + REC_ID) != -1 && !cc_nocase(cc_str(r, REC_ALBUM), album)) return (int)i;
    }
    return -1;
}

/* ---------------------------------------------------------------------------
 * The album order (Settings > Library > Album Order), shared by Cover Flow and the Albums page.
 *
 * Album: the stock list as it is (getAllAlbum: group by album COLLATE NOCASE, then toolsQueryDbTable's in-memory title sort, comparator
 * 0x5e0dac). Artist (the default, iPod style): by the album row's artist, then by album title, each compared as the stock title sort
 * does in the points that matter here (digit runs by value, ASCII case folded, digits and symbols before letters, a CJK name placed by
 * its pinyin initials among the Latin names) with a leading "The " ignored ("The Beatles" files under B) and leading white space
 * skipped; ties (the same artist and title) keep the stock order, so the order is total and the same on every open. The stock album
 * row carries only the artist of the album's representative track (`select id,album,songer,fileurl`; the album artist is a separate
 * column the Albums query does not fetch), so that is the artist sorted by. The "Unknown Album" row (id -1) stays last. The stock
 * deque is never touched: the sorted view is an array of the rows' stock numbers (a heapsort, no libc callback into the payload), and
 * cc_open_album gets the stock number. The Artist Cover Flow keeps the stock order of an artist's albums.
 */
static int fold(int c) { return c >= 'A' && c <= 'Z' ? c + 32 : c; }

int cc_nocase(const char *a, const char *b) {
    while (*a && fold((unsigned char)*a) == fold((unsigned char)*b)) ++a, ++b;
    return fold((unsigned char)*a) - fold((unsigned char)*b);
}

/* s without leading white space (toolsTrimLeft) and without a following "The " (when something follows it). */
static const char *so_name(const char *s) {
    while (*s == ' ' || (*s >= '\t' && *s <= '\r')) ++s;
    if (fold((unsigned char)s[0]) == 't' && fold((unsigned char)s[1]) == 'h' && fold((unsigned char)s[2]) == 'e' &&
        s[3] == ' ' && s[4])
        return s + 4;
    return s;
}

static int kc_digit(unsigned c) { return c >= '0' && c <= '9'; }

/* The class of a (folded) byte: digits, then symbols, then letters, then anything non-ASCII (stock: "digits and symbols before letters"). */
static int kc_class(unsigned c) { return kc_digit(c) ? 0 : c >= 0x80 ? 3 : c >= 'a' && c <= 'z' ? 2 : 1; }

/* Two keys (see cc_name_cmp): runs of digits by value, other bytes by class and then folded value; a key that is a prefix is first.
 * The common prefix is skipped byte by byte (folding only bytes that differ); a difference inside a run of digits goes back to the
 * run's start (the same offset in both, the prefix being common) and compares the two runs by value. */
/* The digit runs around a and b (the first difference, after a common part since a0) by value: -1, 0 (equal values) or 1. The
 * common digits before a are the same in both; when one of them is not '0', the leading zeros are common too, so the longer rest
 * is the larger value and, at equal lengths, the differing digit decides. Otherwise the zeros after a and b are skipped and the
 * significant digits compared. */
static int __attribute__((noinline)) kc_runs(const char *a, const char *b, const char *a0) {
    unsigned ra = 0, rb = 0, za = 0, zb = 0, i;
    int nz = 0;
    const char *p;
    for (p = a; p > a0 && kc_digit((unsigned char)p[-1]); --p) nz |= p[-1] != '0';
    while (kc_digit((unsigned char)a[ra])) ++ra;
    while (kc_digit((unsigned char)b[rb])) ++rb;
    if (!nz) {
        while (za < ra && a[za] == '0') ++za;
        while (zb < rb && b[zb] == '0') ++zb;
        a += za, b += zb, ra -= za, rb -= zb;
    }
    if (ra != rb) return ra < rb ? -1 : 1;
    for (i = 0; i < ra; ++i)
        if (a[i] != b[i]) return a[i] < b[i] ? -1 : 1;
    return 0;
}

int cc_key_cmp(const char *a, const char *b) {
    const char *a0 = a;
    for (;;) {
        unsigned ca, cb;
        while ((ca = (unsigned char)*a) == (cb = (unsigned char)*b)) {
            if (!ca) return 0;
            ++a, ++b;
        }
        if ((kc_digit(ca) || kc_digit(cb)) &&
            ((kc_digit(ca) && kc_digit(cb)) || (a > a0 && kc_digit((unsigned char)a[-1])))) {
            int d = kc_runs(a, b, a0);
            if (d) return d;
            /* equal values ("007", "7"): go on after each run */
            while (a > a0 && kc_digit((unsigned char)a[-1])) --a, --b;
            while (kc_digit((unsigned char)*a)) ++a;
            while (kc_digit((unsigned char)*b)) ++b;
            a0 = a;
            continue;
        }
        if (!ca || !cb) return (ca != 0) - (cb != 0);
        ca = (unsigned)fold((int)ca), cb = (unsigned)fold((int)cb);
        if (ca == cb) {
            ++a, ++b;
            continue;
        }
        if (ca - 'a' < 26 && cb - 'a' < 26) return ca < cb ? -1 : 1;
        {
            int ra = kc_class(ca), rb = kc_class(cb);
            if (ra != rb) return ra < rb ? -1 : 1;
            return ca < cb ? -1 : 1;
        }
    }
}

/* The order of both lists on raw names (the Artist order's name, the podcast and country lists): no pinyin (see cc_name_keys). */
int cc_name_cmp(const char *a, const char *b) { return cc_key_cmp(so_name(a), so_name(b)); }
const char *cc_name_key(const char *s) { return so_name(s); }

/* A CJK character (UTF-8 U+4E00..U+9FFF: E4..E9 and two continuation bytes) at s. */
static int kc_cjk(const unsigned char *s) {
    return s[0] >= 0xe4 && s[0] <= 0xe9 && (s[1] & 0xc0) == 0x80 && (s[2] & 0xc0) == 0x80;
}

/* The pinyin initial of the CJK character at s, as stock's utf8_to_pinyin gives it (it appends to a zeroed buffer: nothing for a character
 * outside U+4E00..U+9FA5), else 0. */
static int kc_initial(const unsigned char *s) {
    char in[4], out[4] = {0, 0, 0, 0};
    in[0] = (char)s[0], in[1] = (char)s[1], in[2] = (char)s[2], in[3] = 0;
    utf8_to_pinyin(in, out);
    return (unsigned char)out[0];
}

int cc_name_initial(const char *name) {
    const unsigned char *s = (const unsigned char *)so_name(name);
    int c;
    return kc_cjk(s) && (c = kc_initial(s)) ? c : *s;
}

/* The keys of n names: key[i] is name(ctx, i) without white space and "The ", the text cc_key_cmp compares. A name with a CJK character
 * has its own copy in which each such character is its pinyin initial (stock's utf8_to_pinyin; other bytes as they are, so a name in
 * another script follows the Latin ones); every other key points into the name. One block (the pointers, then the copies), free()d by
 * the caller; NULL when n is 0 or there is no memory (the caller keeps the stock order). */
const char **cc_name_keys(unsigned n, const char *(*name)(const void *, unsigned), const void *ctx) {
    unsigned i, pool = 0;
    const char **key;
    char *p;
    if (!n) return (const char **)0;
    for (i = 0; i < n; ++i) {
        const unsigned char *s = (const unsigned char *)so_name(name(ctx, i)), *e = s;
        while (*e && !(*e >= 0xe4 && *e <= 0xe9)) ++e;
        if (!*e) continue;
        while (*e) ++e;
        pool += (unsigned)(e - s) + 1;
    }
    key = calloc(1, n * sizeof *key + pool);
    if (!key) return (const char **)0;
    p = (char *)(key + n);
    for (i = 0; i < n; ++i) {
        const char *s = so_name(name(ctx, i)), *t = "";
        if (pool) /* else no name has a CJK lead byte: no second scan */
            for (t = s; *t && !((unsigned char)*t >= 0xe4 && (unsigned char)*t <= 0xe9); ++t) {
            }
        key[i] = s;
        if (*t) {
            char *o = p;
            for (; *s;) {
                int c;
                if (kc_cjk((const unsigned char *)s) && (c = kc_initial((const unsigned char *)s)))
                    *o++ = (char)c, s += 3;
                else
                    *o++ = *s++;
            }
            *o++ = 0;
            key[i] = p, p = o;
        }
    }
    return key;
}

/* Heapsort of v[0..n) by cmp, which must be total (ties broken by the row numbers in v, so equal names keep the stock
 * order). No libc callback into the payload; no memory. */
static int (*so_less)(unsigned, unsigned) __attribute__((section(".scratch")));

static void so_sift(unsigned *v, unsigned i, unsigned n) {
    for (;;) {
        unsigned c = 2 * i + 1, t;
        if (c >= n) return;
        if (c + 1 < n && so_less(v[c], v[c + 1]) < 0) ++c;
        if (so_less(v[i], v[c]) >= 0) return;
        t = v[i], v[i] = v[c], v[c] = t;
        i = c;
    }
}

void cc_heapsort(unsigned *v, unsigned n, int (*cmp)(unsigned, unsigned)) {
    unsigned i, t;
    so_less = cmp;
    for (i = n / 2; i-- > 0;) so_sift(v, i, n);
    for (i = n; i-- > 1;) {
        t = v[0], v[0] = v[i], v[i] = t;
        so_sift(v, 0, i);
    }
}

static void **so_rec __attribute__((section(".scratch"))); /* the rows being sorted, by stock number */
static const char **so_key __attribute__((section(".scratch"))); /* their keys: artist 2 * i, album title 2 * i + 1 */

static int so_cmp(unsigned a, unsigned b) {
    int ua = I(so_rec[a], REC_ID) == -1, ub = I(so_rec[b], REC_ID) == -1, d;
    if (ua != ub) return ua - ub;
    d = cc_key_cmp(so_key[2 * a], so_key[2 * b]);
    if (!d) d = cc_key_cmp(so_key[2 * a + 1], so_key[2 * b + 1]);
    return d ? d : a < b ? -1 : a > b;
}

/* The key texts of the albums being sorted: even i the artist of row i / 2, odd i its title. */
static const char *so_text(const void *ctx, unsigned i) {
    void *r = ((void *const *)ctx)[i / 2];
    return cc_str(r, i & 1 ? REC_ALBUM : REC_ARTIST);
}

int cc_sort_artist(void) { return set_read(CFSORT_FILE, '1') != '0'; /* only "0" / "0\n" is Album */ }

int cc_sort_set(int artist) {
    artist = artist != 0;
    return home_write_atomic(CFSORT_FILE, CFSORT_TMP, artist ? "1\n" : "0\n") == 0 ? artist : -1;
}

unsigned *cc_album_order(void *albums) {
    unsigned n = albums ? deque_size(albums) : 0, i;
    unsigned *v;
    if (!n || !cc_sort_artist()) return (unsigned *)0;
    v = calloc(n, sizeof *v);
    so_rec = calloc(n, sizeof *so_rec);
    so_key = (const char **)0;
    if (v && so_rec) {
        for (i = 0; i < n; ++i) v[i] = i, so_rec[i] = deque_at(albums, i);
        so_key = cc_name_keys(2 * n, so_text, so_rec);
    }
    if (!v || !so_rec || !so_key) {
        free(v);
        v = (unsigned *)0;
    } else
        cc_heapsort(v, n, so_cmp);
    free(so_rec);
    free((void *)so_key);
    so_rec = (void **)0, so_key = (const char **)0;
    return v;
}

void *cc_row(void *albums, const unsigned *order, unsigned i) { return deque_at(albums, order ? order[i] : i); }

/* The track the player is on: the stock readers (get_playtimeandlength, the lock screen) take the position
 * mclGetPlayPos and the row of the play queue (a deque_t * at PLAY_QUEUE) at it; "queued" is 0 <= position < size. */
void *cc_playing(void) {
    int pos = mclGetPlayPos();
    void *queue = *(void **)PLAY_QUEUE;
    return pos >= 0 && queue && (unsigned)pos < deque_size(queue) ? deque_at(queue, (unsigned)pos) : (void *)0;
}

/* ---------------------------------------------------------------------------
 * The cache builder (see covercache.h): the one worker thread of the app. Moved from Cover Flow unchanged in behaviour.
 *
 * The thread touches only: its own job array (built before it started), the volatile counters below, files under
 * ART_DIR, and the art calls (art_make: taglib_album_picture and our resize, with the two stock art functions as the fallback) under parse_cover_mutex, which is the lock every stock caller holds
 * (parse_albumcovertask_thd 0x4dd68c, parseplaycover_thd 0x4df1c4). It never touches a widget, a deque or the image manager.
 */
#define CC_STALL_MS 10000 /* a job that takes longer is taken to be hung */
#define MIN_FREE_MB 16 /* no new cache files below this much free space on the card */

#define CR_PATH 256 /* a path kept in a record: cut (on a character boundary) to this many bytes with the NUL */
#define CR_MAX 2400 /* a record: its fields stop at CR_SOFT, only the line ends and `end` use the rest */
#define CR_SOFT 2048

/* The image a job is working on (set under cb_mutex before pv_cover; path "" none). kind: 1 JPEG, 2 PNG; sof: the JPEG frame marker (0xc2 progressive). w = 0: size unknown (an embedded picture is not opened for diagnostics). */
typedef struct {
    unsigned w, h, kind, sof;
    char path[CR_PATH];
} img_t;

typedef struct {
    char *track; /* the album's first track, copied so the thread never reads stock deques */
    unsigned
        key; /* 0: the one transient job (xf below), not a cache job (cc_build_add refuses key 0); CC_DURATIONS: the path's dur_key */
    unsigned size,
        sec; /* CC_DURATIONS: the file's size when queued, and its measured seconds (written by the worker before done advances) */
} job_t;

/* The one transient extraction a set may hold instead of cache jobs (cc_build_add_file): where it writes and how big. Set before the worker starts, read only by it. */
static struct {
    char dst[80];
    unsigned px;
} xf __attribute__((section(".scratch")));

static struct {
    job_t *jobs;
    unsigned cap;
    unsigned long thread;
    int mode, running;
    volatile int done, total, cancelled;
    volatile int exited; /* the worker's last act: join it now and it returns at once */
    int orphan; /* stopped while the worker was still inside a job: it keeps the set (jobs, tracks, xf) until it has exited */
    int seen; /* done when last looked at, and the time_now_ms it last moved (build_watch) */
    unsigned at;
    volatile int
        stalled; /* build_watch gave up on the set (kept after it is freed, until the next open: cc_build_stalled) */
    unsigned cur,
        orphan_at; /* the card job's key, and whether art_lock has written its .inflight (began); when the worker was orphaned */
    volatile int began;
    volatile unsigned seq,
        claimed; /* the job sequence (started under cb_mutex); the key build_watch gave up on (read by the worker to undo its .bad on a late success) */
    unsigned seen_seq; /* seq when build_watch last looked */
    int phase; /* where the current card job's progress is (PH_*, the "phase:" of a .bad); set and read under cb_mutex, reset when a job starts */
    img_t img; /* its image (same rules) */
    volatile int
        truncated; /* cc_build_near_step could not queue an album (the set was full, or no memory): cc_build_truncated, kept like stalled */
} cb __attribute__((section(".scratch")));

/* Ours, zero-filled like stock's parse_cover_mutex (a default mutex): serialises a job's start (cur, began, seq) with build_watch's claim of a stalled job. Never held over extraction or file I/O. */
static unsigned cb_mutex[8] __attribute__((section(".scratch"), aligned(8)));

/* ---- The text records of ART_DIR: .inflight (header, key, build, track, end) and the .bad of a job that hung or died twice (header, key, build, result, phase, track, image if known, end). One line per field: `\` and
 * newline in a path are written as `\\` and `\n`, any other control byte as `\xNN`. A record without its `end` line was cut short. The phase says where progress stopped, not that a file is corrupt. docs/modules/coverflow.md. */
enum { PH_NONE, PH_EMB_TAGS, PH_EMB_SHRINK, PH_EMB_STOCK, PH_FOLDER_SCAN, PH_FOLDER_SHRINK, PH_FOLDER_STOCK };
static const char *const ph_name[] = {
    "unknown",          "embedded art, reading tags", "embedded art, shrinking", "embedded art, stock fallback",
    "folder, scanning", "folder image, shrinking",    "folder, stock fallback"};

typedef struct {
    char b[CR_MAX];
    unsigned n;
} rec_t;

/* What a .bad says about a job. pre: track is already escaped (read back from an .inflight). */
typedef struct {
    unsigned key, phase, pre;
    img_t img;
    char track[CR_MAX / 2];
} snap_t;

static void r_put(rec_t *r, const char *s) {
    for (; *s && r->n < CR_SOFT; ++s) r->b[r->n++] = *s;
}

static void r_nl(rec_t *r) { r->b[r->n++] = '\n'; } /* (at most 10 lines: CR_MAX - CR_SOFT is room enough) */

/* s as one line: `\`, newline and the other control bytes escaped; bytes from 0x80 as they are (UTF-8). */
static void r_esc(rec_t *r, const char *s) {
    static const char hex[] = "0123456789abcdef";
    for (; *s && r->n + 4 < CR_SOFT; ++s) {
        unsigned c = (unsigned char)*s;
        if (c == '\\' || c == '\n') {
            r->b[r->n++] = '\\', r->b[r->n++] = c == '\n' ? 'n' : '\\';
        } else if (c < 32 || c == 127) {
            r->b[r->n++] = '\\', r->b[r->n++] = 'x', r->b[r->n++] = hex[c >> 4], r->b[r->n++] = hex[c & 15];
        } else
            r->b[r->n++] = (char)c;
    }
}

/* s, already escaped (an .inflight's track line), to its end of line: a control byte, which no record of ours holds, becomes '?'. */
static void r_pre(rec_t *r, const char *s) {
    for (; *s && *s != '\n' && r->n < CR_SOFT; ++s) r->b[r->n++] = (unsigned char)*s < 32 || *s == 127 ? '?' : *s;
}

static void r_num(rec_t *r, unsigned v, unsigned base, unsigned width) {
    char t[10];
    unsigned i = 0;
    do t[i++] = "0123456789abcdef"[v % base], v /= base;
    while (i < width || v);
    while (i && r->n < CR_SOFT) r->b[r->n++] = t[--i];
}

static void r_head(rec_t *r, unsigned key) {
    r_put(r, "m1plus cover 1\nkey: "), r_num(r, key, 16, 8);
    r_put(r, "\nbuild: "), r_esc(r, M1PLUS_TAG), r_nl(r);
}

static void r_end(rec_t *r) { /* (the room above CR_SOFT) */ memcpy(r->b + r->n, "end\n", 4), r->n += 4; }

/* Up to n - 1 bytes of s, cut before a UTF-8 sequence the limit would split. */
static void cp_str(char *d, unsigned n, const char *s) {
    unsigned i = 0;
    while (s[i] && i < n - 1) d[i] = s[i], ++i;
    if (s[i])
        while (i && ((unsigned char)s[i] & 0xc0) == 0x80) --i;
    d[i] = 0;
}

static int r_write(const char *path, const rec_t *r) {
    void *f = fopen(path, "w");
    int ok;
    if (!f) return 0;
    ok = fwrite(r->b, r->n, 1, f) == 1;
    fclose(f);
    return ok;
}

static void r_bad(rec_t *r, const snap_t *s, const char *result) {
    r->n = 0, r_head(r, s->key);
    r_put(r, "result: "), r_put(r, result), r_put(r, "\nphase: "), r_put(r, ph_name[s->phase]);
    r_put(r, "\ntrack: "), s->pre ? r_pre(r, s->track) : r_esc(r, s->track), r_nl(r);
    if (s->img.path[0]) {
        r_put(r, "image: "), r_esc(r, s->img.path);
        if (s->img.w) r_put(r, " "), r_num(r, s->img.w, 10, 1), r_put(r, "x"), r_num(r, s->img.h, 10, 1);
        if (s->img.kind) r_put(r, s->img.kind == 1 ? " jpeg" : " png");
        if (s->img.kind == 1 && s->img.sof) r_put(r, s->img.sof == 0xc2 ? " progressive" : " baseline");
        r_nl(r);
    }
    r_end(r);
}

/* The phase (and, when img is not NULL, the image: "" clears it) of the card job in flight, for the watchdog. */
static void at(int phase, const char *img, unsigned w, unsigned h, unsigned kind, unsigned sof) {
    pthread_mutex_lock(cb_mutex);
    cb.phase = phase;
    if (img)
        cb.img.w = w, cb.img.h = h, cb.img.kind = kind, cb.img.sof = sof, cp_str(cb.img.path, sizeof cb.img.path, img);
    pthread_mutex_unlock(cb_mutex);
}

/* Whether dir's file system has MIN_FREE_MB free (statfs, MIPS o32 layout: f_bsize is word 1,
 * f_bavail word 7), as q2-pod's card_space. */
static int card_space(const char *dir) {
    unsigned fs[32];
    memset(fs, 0, sizeof fs);
    return !statfs(dir, fs) && (unsigned long long)fs[7] * fs[1] >= (unsigned long long)MIN_FREE_MB << 20;
}

/* The longer side of the JPEG at path (its SOF marker, in the first 4 KB: the stock encoder's files have a short header), 0 when it cannot be read. */
static unsigned jpeg_long_side(const char *path) {
    unsigned char b[4096];
    unsigned n, i = 2, w, h;
    void *f = fopen(path, "rb");
    if (!f) return 0;
    n = (unsigned)fread(b, 1, sizeof b, f);
    fclose(f);
    if (n < 4 || b[0] != 0xff || b[1] != 0xd8) return 0;
    while (i + 9 < n) {
        unsigned m;
        if (b[i] != 0xff) {
            ++i;
            continue;
        }
        m = b[i + 1];
        if (m == 0xff) {
            ++i;
            continue;
        }
        if (m >= 0xc0 && m <= 0xcf && m != 0xc4 && m != 0xc8 && m != 0xcc) {
            h = (unsigned)b[i + 5] << 8 | b[i + 6], w = (unsigned)b[i + 7] << 8 | b[i + 8];
            return w > h ? w : h;
        }
        if (m == 0xd8 || (m >= 0xd0 && m <= 0xd7) || m == 0x01) {
            i += 2;
            continue;
        }
        i += 2 + ((unsigned)b[i + 2] << 8 | b[i + 3]);
    }
    return 0;
}

/* ---- The extraction: stock's two art calls, with the resize replaced. Stock's calls run under parse_cover_mutex (the whole call, as stock's do: /tmp/.tmp_picture is shared with the
 * stock threads); of ours only taglib_album_picture does, and our resize runs outside it on a private copy. Any failure of ours hands the same album to the stock call, so a cover is never lost; a picture smaller than the size (stock copies it, or encodes it again as it is)
 * and an interlaced PNG are stock's too. docs/modules/coverflow.md "Cover resampling". */
#define TAG_TMP \
    "/tmp/.tmp_picture" /* where libtag_c's save_picturefile writes the embedded picture; toolsGetAlbumCover reads and removes it (the string at 0x757838, pinned) */
#define TAG_LIMIT_A \
    0x100000 /* taglib_album_picture's last two arguments, as toolsGetAlbumCover passes them (0x5eaf00, 0x5eaf0c) */
#define TAG_LIMIT_B 0x600000
#define TAG_COPY \
    "/tmp/.m1plus_art" /* the embedded picture moved out of TAG_TMP while the lock is held, shrunk after it is released */

#define INFLIGHT \
    ART_DIR \
    "/.inflight" /* the text record (r_head, track, end) of the album being extracted: left behind, the run died or hung on it */

/* parse_cover_mutex, taken unless the set was cancelled while waiting for it (0: not held, nothing to extract). The first time for a card job the extraction begins: .inflight is written
 * (an album that only waited for the lock is not to blame), and only then `began` is set under cb_mutex, so a claim (which needs `began`) always finds the journal and unlinks it. */
static int art_lock(int phase, const char *track) {
    int first;
    pthread_mutex_lock((void *)PARSE_COVER_MUTEX);
    first = cb.cur && !cb.began && !cb.cancelled;
    if (first) {
        unsigned key = cb.cur;
        rec_t r;
        r.n = 0, r_head(&r, key);
        r_put(&r, "track: "), r_esc(&r, track), r_nl(&r), r_end(&r);
        r_write(INFLIGHT, &r);
    }
    pthread_mutex_lock(cb_mutex);
    if (cb.cancelled) { /* claimed while this job waited */
        pthread_mutex_unlock(cb_mutex);
        if (first) unlink(INFLIGHT);
        pthread_mutex_unlock((void *)PARSE_COVER_MUTEX);
        return 0;
    }
    if (first) cb.began = 1;
    cb.phase = phase;
    pthread_mutex_unlock(cb_mutex);
    return 1;
}

/* The embedded picture, as toolsGetAlbumCover finds it (taglib_album_picture: 2 a JPEG, 1 a PNG, saved to TAG_TMP, moved to TAG_COPY under the lock), shrunk by pv_cover. No picture, or
 * one pv_cover refuses (PV_REFUSED): 0, and stock's call is not made (it would ask taglib the same, or decode it). */
static int art_embedded(const char *track, const char *dst, unsigned px) {
    int kind, r = 0;
    if (!art_lock(PH_EMB_TAGS, track)) return 0;
    kind = taglib_album_picture(track, (char *)dst, TAG_LIMIT_A, TAG_LIMIT_B);
    if ((kind == 1 || kind == 2) && rename(TAG_TMP, TAG_COPY))
        unlink(TAG_TMP), unlink(TAG_COPY); /* (a stale copy is never shrunk instead: stock is asked) */
    pthread_mutex_unlock((void *)PARSE_COVER_MUTEX);
    if (kind != 1 && kind != 2) return 0;
    at(PH_EMB_SHRINK, "embedded", 0, 0, kind == 2 ? 1 : 2, 0); /* (the picture is not opened again to say more) */
    if (!access(TAG_COPY, 4)) r = pv_cover(TAG_COPY, dst, px);
    unlink(TAG_COPY);
    if (r != 0 && r != -1) return r == 1; /* done, or refused */
    if (!art_lock(PH_EMB_STOCK, track)) return 0;
    r = toolsGetAlbumCover(track, dst, px, px) == 1;
    pthread_mutex_unlock((void *)PARSE_COVER_MUTEX);
    return r;
}

#define FL_MAX 48 /* the folder's pictures looked at (a folder of more has its first ones) */
#define FL_NAME 256
#define FL_STOCK_JPEG \
    0x600000 /* toolsGetExternCover (0x5eb760, 0x5eb7bc) passes a picture file by its size in bytes: a PNG up to 1 MiB, a JPEG up to 6 MiB */
#define FL_STOCK_PNG 0x100000

static unsigned fl_len(const char *s) {
    unsigned n = 0;
    while (s[n]) ++n;
    return n;
}

static int fl_ext(const char *name) { /* the last extension is .jpg, .png or .jpeg, any case */
    const char *dot = (const char *)0;
    for (; *name; ++name)
        if (*name == '.') dot = name;
    return dot && (!cc_nocase(dot, ".jpg") || !cc_nocase(dot, ".png") || !cc_nocase(dot, ".jpeg"));
}

/* Stock's choice of the folder picture (toolsGetExternCover 0x5eb314..0x5eb684): the regular files with those extensions, in readdir order; then for each of folder.png, folder.jpg,
 * folder.jpeg, cover.png, cover.jpg, cover.jpeg, <track>.png, <track>.jpg, <track>.jpeg in that order the file of that name (any case) moves to the front, so the order tried is the
 * reverse of that list for the files that exist (<track>.jpeg first, folder.png last of them), then the others as listed. The first whose header is a picture within stock's
 * file size limit goes to pv_cover. 1 when the cover was made; any other outcome is stock's own call (which does the same walk again and handles what is left). */
static int art_folder(const char *track, const char *dst, unsigned px) {
    static const char *const pri[6] = {"folder.png", "folder.jpg", "folder.jpeg",
                                       "cover.png",  "cover.jpg",  "cover.jpeg"};
    static const char *const ext[3] = {".png", ".jpg", ".jpeg"};
    char dir[FL_NAME], base[FL_NAME], path[FL_NAME * 2 + 2], want[FL_NAME + 8], (*names)[FL_NAME];
    int rank[FL_MAX], n = 0, i, p, r = 0, done = 0;
    unsigned len = fl_len(track), slash = len, dot;
    void *d;
    char *ent;
    while (slash && track[slash - 1] != '/') --slash;
    if (!slash || slash >= sizeof dir || len - slash >= FL_NAME) goto stock;
    memcpy(dir, track, slash - 1), dir[slash - 1] = 0;
    memcpy(base, track + slash, len - slash + 1);
    for (dot = fl_len(base); dot && base[dot - 1] != '.'; --dot) {
    }
    if (dot) base[dot - 1] = 0; /* the name without its last extension */
    names = calloc(FL_MAX, FL_NAME);
    at(PH_FOLDER_SCAN, "", 0, 0, 0, 0);
    d = names ? opendir(dir) : (void *)0;
    if (!d) {
        free(names);
        goto stock;
    }
    while (n < FL_MAX && (ent = readdir(d)) != (char *)0) {
        const char *name = ent + 11; /* struct dirent: d_type at 10, d_name at 11 */
        if (ent[10] != 8 || fl_len(name) >= FL_NAME || !fl_ext(name)) continue;
        memcpy(names[n], name, fl_len(name) + 1);
        rank[n] = 9; /* the others */
        for (p = 0; p < 9; ++p) {
            if (p < 6)
                snprintf(want, sizeof want, "%s", pri[p]);
            else
                snprintf(want, sizeof want, "%s%s", base, ext[p - 6]);
            if (!cc_nocase(name, want)) rank[n] = 8 - p;
        }
        ++n;
    }
    closedir(d);
    for (p = 0; p < 10 && !done; ++p)
        for (i = 0; i < n && !done; ++i) {
            unsigned w, h, sof;
            long size;
            int kind;
            if (rank[i] != p) continue;
            snprintf(path, sizeof path, "%s/%s", dir, names[i]);
            kind = pc_pic_info(path, &w, &h, &sof);
            size = cc_file_size(path);
            if (!(kind == 1 && (sof == 0xc0 || sof == 0xc1 || sof == 0xc2) && size > 0 && size <= FL_STOCK_JPEG) &&
                !(kind == 2 && size > 0 && size <= FL_STOCK_PNG))
                continue;
            at(PH_FOLDER_SHRINK, path, w, h, (unsigned)kind, sof);
            r = pv_cover(path, dst, px), done = 1;
        }
    free(names);
    if (r == 1) return 1;
    if (r == PV_REFUSED) return 0; /* no art, as for an embedded one */
stock:
    if (!art_lock(PH_FOLDER_STOCK, track)) return 0;
    r = toolsGetExternCover(track, dst, px, px) == 1;
    pthread_mutex_unlock((void *)PARSE_COVER_MUTEX);
    return r;
}

/* The album's art at px x px into dst: the embedded picture, else the folder's. Takes the lock itself, around the stock calls only. */
static int art_make(const char *track, const char *dst, unsigned px) {
    return art_embedded(track, dst, px) || (!cb.cancelled && art_folder(track, dst, px));
}

/* A transient extraction (the Pod's cover pane, docs/modules/ipod.md): the album's art, fitted inside px x px by art_make (never upscaled), into xf.dst through
 * dst.tmp and a rename. A picture whose longer side is under px (a small source) is not kept, and nothing else is written: no cache file, no marker. */
static void build_file(const job_t *j) {
    char tmp[96];
    int ok;
    snprintf(tmp, sizeof tmp, "%s.tmp", xf.dst);
    if (access(j->track, F_OK)) return;
    ok = art_make(j->track, tmp, xf.px);
    if (cb.cancelled) { /* the pane has gone (and removed xf.dst): publish nothing */
        unlink(tmp);
        return;
    }
    if (ok && jpeg_long_side(tmp) >= xf.px) {
        if (rename(tmp, xf.dst)) unlink(tmp);
        return;
    }
    unlink(tmp);
}

/* r<key>-168.jpg.bad, a text record of the job (r_bad): the album is not tried again (until the next Rebuild Covers request, cc_clear_bad; the skip looks only at the file's existence). 1 if it was written. */
static int mark_bad(const snap_t *s, const char *result) {
    char path[72];
    rec_t r;
    r_bad(&r, s, result);
    return r_write(cc_path(path, sizeof path, s->key, ".bad"), &r);
}

/* Rebuild Covers is requested: every .bad goes, so each album gets one more try (a resumed rebuild skips the ones that hang again). */
void cc_clear_bad(void) {
    void *d = opendir(ART_DIR);
    char *ent;
    if (!d) return;
    while ((ent = readdir(d)) != (char *)0) {
        const char *name = ent + 11; /* struct dirent: d_type at 10, d_name at 11 */
        const char *e = name;
        char path[300];
        while (*e) ++e;
        if (ent[10] != 8 || e - name < 5 || e[-4] != '.' || e[-3] != 'b' || e[-2] != 'a' || e[-1] != 'd') continue;
        snprintf(path, sizeof path, ART_DIR "/%s", name);
        unlink(path);
    }
    closedir(d);
}

/* The line `name` (with its colon and space) of the record in b, as a pointer to the value, or NULL. */
static const char *r_field(const char *b, const char *name) {
    unsigned n = fl_len(name);
    for (; *b; ++b) {
        unsigned i = 0;
        while (i < n && b[i] == name[i]) ++i;
        if (i == n) return b + n;
        while (*b && *b != '\n') ++b;
        if (!*b) break;
    }
    return (const char *)0;
}

/* A new set begins: an .inflight left by the last run names the album it died or hung on. Two strikes, so a power-off does not blame a healthy album: the first leaves an empty
 * r<key>-168.jpg.try; the second (a .try still there: a finished job for the key removes it) marks it bad ("interrupted twice", the track from the .inflight). A strike that failed to be written leaves .inflight for the next open.
 * The .inflight is read defensively: at most 1 KB, the header and a valid key line required (else it is removed and no one is blamed); a cut one (no track or no end) still strikes its key, with the track unknown. */
static void build_recover(void) {
    char path[72], b[1024];
    snap_t s;
    unsigned n, i;
    const char *k, *t;
    int ok = 1;
    void *f = fopen(INFLIGHT, "rb");
    if (!f) return;
    n = (unsigned)fread(b, 1, sizeof b - 1, f);
    fclose(f);
    b[n] = 0;
    memset(&s, 0, sizeof s);
    k = r_field(b, "key: ");
    if (k && r_field(b, "m1plus cover 1\n") == b + 15) {
        unsigned v = 0;
        for (i = 0; i < 8; ++i) { /* exactly eight hex digits, then the end of the line */
            unsigned c = (unsigned char)k[i], d = c - '0', l = (c | 32) - 'a';
            if (d > 9 && l > 5) break;
            v = v << 4 | (d <= 9 ? d : l + 10);
        }
        if (i == 8 && k[8] == '\n') s.key = v;
    }
    if (s.key) {
        t = r_field(b, "track: ");
        s.pre = 1;
        cp_str(s.track, sizeof s.track, "unknown");
        if (t && r_field(b, "end\n")) {
            for (i = 0; t[i] && t[i] != '\n' && i < sizeof s.track - 1; ++i) s.track[i] = t[i];
            s.track[i] = 0;
        }
        cc_path(path, sizeof path, s.key, ".try");
        if (!access(path, F_OK)) {
            ok = mark_bad(&s, "interrupted twice");
            if (ok) unlink(path);
        } else {
            void *e = fopen(path, "w");
            ok = e != (void *)0;
            if (e) fclose(e);
        }
    }
    if (ok) unlink(INFLIGHT);
}

static void build_art(const job_t *j) {
    char dst[64], tmp[64], pick[72], path[72];
    int ok;
    void *f;
    if (!j->key) {
        build_file(j);
        return;
    }
    if (access(j->track, F_OK)) return; /* storage gone: no marker, the next open retries */
    cc_path(dst, sizeof dst, j->key, "");
    cc_path(tmp, sizeof tmp, j->key, ".tmp");
    cc_path(pick, sizeof pick, j->key, ".pick");
    if (!access(pick, F_OK) && !access(dst, F_OK))
        return; /* a cover picked in Find Cover & Lyrics (docs/modules/onlineart.md): Rebuild Covers keeps it */
    pthread_mutex_lock(cb_mutex);
    if (cb.cancelled) { /* build_watch claimed the previous job (or the set was stopped): no new job starts */
        pthread_mutex_unlock(cb_mutex);
        return;
    }
    cb.cur = j->key, cb.began = 0, ++cb.seq;
    cb.phase = PH_NONE, cb.img.path[0] = 0, cb.img.w = cb.img.h = cb.img.kind = cb.img.sof = 0;
    pthread_mutex_unlock(cb_mutex);
    ok = art_make(j->track, tmp, ART_SIZE);
    pthread_mutex_lock(cb_mutex);
    cb.cur = 0;
    pthread_mutex_unlock(cb_mutex);
    if (cb.began) unlink(INFLIGHT);
    if (!ok && cb.cancelled) { /* cancelled: no marker (a stalled extraction was marked bad by build_watch) */
        unlink(tmp);
        return;
    }
    unlink(cc_path(path, sizeof path, j->key, ".try")); /* finished: no strike against it */
    if (ok && cc_file_size(tmp) > 0) {
        if (rename(tmp, dst))
            unlink(tmp); /* extracted but not published: no marker, the next open retries */
        else { /* (a rebuild's rename replaces the old picture or marker) */
            unsigned late;
            pthread_mutex_lock(cb_mutex);
            late = cb.claimed == j->key;
            if (late) cb.claimed = 0; /* acknowledged: build_watch sees it and removes a .bad it writes after this */
            pthread_mutex_unlock(cb_mutex);
            if (late)
                unlink(cc_path(path, sizeof path, j->key,
                               ".bad")); /* claimed as hung, yet it came back and published: not bad */
        }
        return;
    }
    unlink(tmp);
    if (access(j->track, F_OK)) return;
    if (!access(dst, F_OK)) return; /* a rebuild that finds no art keeps the file it has */
    f = fopen(dst, "w"); /* an empty file marks "no art": the placeholder shows, no retry */
    if (f) fclose(f);
}

/* The worker thread's niceness (docs/modules/coverflow.md "Worker priority"): setpriority(PRIO_PROCESS, 0, CC_NICE), o32 syscall 4097 (no import; as patch/filetime.c's statx). On Linux "who 0" is the calling thread
 * alone, so the UI and the player keep the CPU while covers are built; raising the value needs no privilege, a refused call changes nothing. */
extern int cc_setprio(int which, int who, int prio);
__asm__(".text\n.globl cc_setprio\ncc_setprio:\nli $v0, 4097\nsyscall\njr $ra\nnop\n");
#define CC_NICE 10

static void *cc_worker(void *unused) {
    (void)unused;
    cc_setprio(0, 0, CC_NICE);
    while (cb.done < cb.total && !cb.cancelled) {
        if (cb.mode == CC_DURATIONS)
            cb.jobs[cb.done].sec = (unsigned)dur_probe(cb.jobs[cb.done].track);
        else
            build_art(&cb.jobs[cb.done]);
        ++cb.done;
    }
    cb.exited = 1;
    return (void *)0;
}

static void build_free(void) {
    int i;
    for (i = 0; i < cb.total; ++i)
        if (cb.jobs) free(cb.jobs[i].track);
    free(cb.jobs);
    cb.jobs = (job_t *)0;
    cb.cap = 0;
    cb.total = cb.done = cb.cancelled = 0;
}

/* An orphaned worker (cc_build_stop found it inside a job) is joined and its set freed once it has exited; never waits. */
static void build_reap(void) {
    if (!cb.orphan || !cb.exited) return;
    pthread_join(cb.thread, (void **)0);
    cb.orphan = 0;
    build_free();
}

int cc_build_open(unsigned capacity, int mode) {
    build_reap();
    if (cb.jobs) return 0;
    build_recover();
    if (capacity > (mode == CC_DURATIONS ? CC_MAX_LEN_JOBS : CC_MAX_JOBS))
        capacity = mode == CC_DURATIONS ? CC_MAX_LEN_JOBS : CC_MAX_JOBS;
    cb.jobs = calloc(capacity ? capacity : 1, sizeof(job_t));
    if (!cb.jobs) return 0;
    cb.cap = capacity;
    cb.mode = mode;
    cb.done = cb.total = cb.cancelled = cb.stalled = cb.truncated = cb.claimed = 0;
    return 1;
}

int cc_build_add(const char *track, unsigned key) {
    char path[64];
    job_t *j;
    if (!cb.jobs || cb.running || cb.mode == CC_DURATIONS || !key || !track || !*track) return 0;
    if ((cb.mode == CC_MISSING && !access(cc_path(path, sizeof path, key, ""), F_OK)) ||
        !access(cc_path(path, sizeof path, key, ".bad"), F_OK))
        return 0;
    if ((unsigned)cb.total >= cb.cap) return -1;
    j = &cb.jobs[cb.total];
    j->track = strdup(track);
    if (!j->track) return -1;
    j->key = key;
    ++cb.total;
    return 1;
}

int cc_build_add_dur(const char *track, unsigned key, unsigned size) {
    int i;
    job_t *j;
    if (!cb.jobs || cb.running || cb.mode != CC_DURATIONS || !key || !track || !*track) return 0;
    for (i = 0; i < cb.total; ++i)
        if (cb.jobs[i].key == key) return 0; /* one file, one measurement (the tracks of a CUE image) */
    if ((unsigned)cb.total >= cb.cap) return -1;
    j = &cb.jobs[cb.total];
    j->track = strdup(track);
    if (!j->track) return -1;
    j->key = key, j->size = size, j->sec = 0;
    ++cb.total;
    return 1;
}

int cc_build_dur(int i, unsigned *key, unsigned *size, unsigned *sec) {
    if (!cb.jobs || cb.mode != CC_DURATIONS || i < 0 || i >= cb.done) return 0;
    *key = cb.jobs[i].key, *size = cb.jobs[i].size, *sec = cb.jobs[i].sec;
    return 1;
}

int cc_build_add_file(const char *track, const char *dst, unsigned px) {
    unsigned n;
    job_t *j;
    if (!cb.jobs || cb.running || cb.total || !track || !*track || !dst || !*dst || !px) return 0;
    j = &cb.jobs[0];
    j->track = strdup(track);
    if (!j->track) return -1;
    j->key = 0;
    for (n = 0; dst[n] && n < sizeof xf.dst - 5; ++n)
        xf.dst[n] = dst[n]; /* (a path that does not fit is cut: the callers' is short) */
    xf.dst[n] = 0;
    xf.px = px;
    cb.total = 1;
    return 1;
}

void cc_build_stop(void) {
    if (cb.orphan) { /* not the caller's set: the orphan's */
        build_reap();
        return;
    }
    if (cb.running) {
        cb.cancelled = 1;
        cb.running = 0;
        if (!cb.exited &&
            cb.done <
                cb.total) { /* inside a job (stock's parser can take long): the UI thread never waits, the worker keeps the set */
            cb.orphan = 1, cb.orphan_at = (unsigned)time_now_ms();
            return;
        }
        pthread_join(cb.thread, (void **)0);
    }
    build_free();
}

int cc_build_start(void) {
    if (!cb.jobs || cb.running || cb.orphan) return 0;
    if (!cb.total) {
        cc_build_stop(); /* nothing to build: free the job array */
        return 0;
    }
    if (cb.mode != CC_DURATIONS) {
        mkdir(CARD_DIR, 0755); /* the folder, then the cache in it (EEXIST is fine) */
        mkdir(ART_DIR, 0755);
    }
    cb.exited = 0;
    if ((cb.mode != CC_DURATIONS && !card_space(ART_DIR)) ||
        pthread_create(&cb.thread, (void *)0, cc_worker, (void *)0)) {
        cc_build_stop(); /* no card, no space, or no thread: the caller shows what is cached already */
        return 0;
    }
    cb.running = 1;
    cb.seen = 0, cb.seen_seq = cb.seq, cb.at = (unsigned)time_now_ms();
    return 1;
}

/* Polled with cc_build_done: a card job that has made no progress for CC_STALL_MS (time_now_ms, a steady clock) is taken to be hung: the set is stopped (the worker orphaned) and the job, if its extraction had
 * begun, is marked .bad here, as only a worker that came back could write it. A text record (the phase and image the worker last reported, copied with the track under the same mutex hold; nothing live is read after the unlock); its .inflight goes, so the next open takes no strike. The claim (progress re-checked, cancelled set, the key
 * captured) is made under cb_mutex, so the worker cannot start the next job after it, and the .bad can only name the claimed job; a worker that published meanwhile clears `claimed` (its acknowledgement),
 * whichever of the two removes the .bad last: the watchdog re-checks after writing it. The .bad write and the .inflight unlink run on the UI thread: a card that
 * stalls can still block the UI there, for an unbounded time. An orphan need not hold stock's lock (our resize runs outside it); builds stay refused until it exits, as it still owns the set's resources. */
static void build_watch(void) {
    unsigned now = (unsigned)time_now_ms(), key = 0;
    int i = cb.done;
    snap_t
        s; /* the claimed job, copied under cb_mutex: after the unlock only this is read (the worker moves on, and rewrites cb.img) */
    if (!cb.running || cb.mode == CC_DURATIONS || i >= cb.total) return;
    if (i != cb.seen || cb.seq != cb.seen_seq) {
        cb.seen = i, cb.seen_seq = cb.seq, cb.at = now;
        return;
    }
    if (now - cb.at < CC_STALL_MS) return;
    pthread_mutex_lock(cb_mutex);
    if (cb.done != i || cb.seq != cb.seen_seq) { /* progress since the look above */
        pthread_mutex_unlock(cb_mutex);
        return;
    }
    cb.stalled = cb.cancelled = 1;
    if (cb.cur && cb.began) {
        key = s.key = cb.claimed = cb.cur, s.phase = (unsigned)cb.phase, s.pre = 0;
        cp_str(s.track, CR_PATH, cb.jobs[i].track); /* (owned by the set, which the orphaned worker keeps) */
        memcpy(&s.img, &cb.img, sizeof s.img);
    }
    pthread_mutex_unlock(cb_mutex);
    if (key && mark_bad(&s, "timed out")) {
        char path[72];
        int acked;
        unlink(INFLIGHT);
        pthread_mutex_lock(cb_mutex);
        acked = cb.claimed != key;
        pthread_mutex_unlock(cb_mutex);
        if (acked)
            unlink(
                cc_path(path, sizeof path, key,
                        ".bad")); /* the worker published and acknowledged meanwhile: its cover stands, not this .bad */
    }
    cc_build_stop();
}

/* A stalled set reads as finished, so the pages that poll it end; once its worker has exited the set is freed (done = total = 0). */
int cc_build_done(void) {
    build_watch();
    build_reap();
    return cb.orphan && cb.stalled ? cb.total : cb.done;
}
int cc_build_total(void) { return cb.total; }
int cc_build_running(void) { return cb.running; }
int cc_build_active(void) {
    return cb.running && !cb.cancelled && cb.done < cb.total && cb.jobs &&
           cb.jobs[0].key; /* (a transient file job, key 0, is the Pod cover pane's: not a build) */
}
int cc_build_busy(void) {
    build_reap();
    return cb.jobs != (job_t *)0;
}
int cc_build_stalled(void) { return cb.stalled; }
int cc_build_truncated(void) { return cb.truncated; }
int cc_build_orphan(void) {
    build_reap();
    return cb.orphan && (unsigned)time_now_ms() - cb.orphan_at <
                            CC_STALL_MS; /* a worker that stays inside its job is not waited for longer */
}

int cc_build_near_step(void *albums, const unsigned *order, const unsigned *keys, unsigned centre, unsigned *cursor,
                       unsigned batch) {
    unsigned n = albums ? deque_size(albums) : 0, c = *cursor, left = batch;
    int full = 0;
    if (centre >= n) centre = n ? n - 1 : 0;
    while ((c >> 1) < n && left) { /* the cursor is 2 x distance + (0 after the centre, 1 before it) */
        unsigned d = c >> 1, k = c & 1, i;
        void *r;
        ++c;
        if (k ? !d || d > centre : centre + d >= n) continue; /* out of range or d = 0 twice: free */
        i = k ? centre - d : centre + d;
        r = cc_row(albums, order, i);
        --left;
        if (I(r, REC_ID) == ID_ALL_SONGS || (keys && !keys[i]))
            continue; /* a scoped list's All songs row has no cover */
        if (cc_build_add(cc_str(r, REC_PATH), keys ? keys[i] : cc_album_key(r)) < 0) {
            cb.truncated = 1;
            --c; /* full (or out of memory): done, the caller told, and the cursor left on the album that did not fit (a later walk can resume there) */
            full = 1;
            break;
        }
    }
    *cursor = c;
    return full || (c >> 1) >= n;
}

int cc_build_near(void *albums, const unsigned *order, unsigned centre) {
    unsigned c = 0;
    cc_build_near_step(albums, order, (const unsigned *)0, centre, &c, ~0u);
    return cb.total;
}
#endif /* CF_HOST */
