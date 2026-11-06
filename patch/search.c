/* M1+ Music Search: the library search, in the Apple Music manner: a field, chips, live results, on ONE page that has our keyboard embedded at its bottom.
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * docs/modules/search.md has the whole design. ui/m1plus_search.bin: a rounded field (the magnifier, the text and caret, a clear disc, the widgets of patch/keyboard.c's field), the round X button
 * (Back), a row of chips (Top Results, Artists, Albums, Songs, Playlists: one is selected and filters the list), a stock list holding ONE content view that paints the rows itself (a thumbnail, a
 * title, a grey line, a chevron; the painted-view pattern of the Artists page) and, at the bottom, the keyboard's pad: keyboard_attach (patch/keyboard.c) puts the same pad, candidate strip
 * and key pop-up on this page, so nothing is opened or closed when the user types or searches. search_open is the Songs page's Search and the album page's search button.
 *
 *   data      the library the way our pages read it, read ONCE when the page has been shown (and again when another query replaced the stock song list under it): the Artists page's list
 *             (loadLocalClassList(0xf004), copied), cc_albums() (copied), the playlists (loadLocalClassList(0xf00b), copied) and the Songs page's list (loadLocalClassList(0xf001), left in
 *             *pdeq_showlist, record numbers kept). Stock queries are page state, run from this page in front (its timer, its to-foreground), never from a key's handler.
 *   live      every change of the field's committed text (a Chinese candidate still being composed is not in it) restarts a countdown of SE_DEBOUNCE ticks of the page's ONE timer (SE_TICK_MS); at
 *             zero the query is applied. The same timer then loads covers, one per tick, and ends when there is nothing left.
 *   matching  the query is folded (case, Latin diacritics, hiragana / katakana, half / full width) and split at spaces into at most SE_TERMS terms; a record matches when every term is a substring of
 *             its folded key (song: title, artist, album; album: album, artist; artist and playlist: the name), in any order. The matches of each type are kept in library order with their quality
 *             (0 the name is the whole query, 1 it starts with the first term, 2 otherwise). A query that extends the previous one (its folding starts with it) can only match what matched
 *             before, so only those are tested; anything else scans the library. se_key builds one key per record; a record with Chinese characters has a second, the initials of the characters' readings (the engine's dictionary, held open for the page's life), tested the same way.
 *   rows      Top Results: the best quality first, in each quality artists, albums, playlists, songs, SE_CAP_TOP rows; a type chip: that type's matches, best quality first, up to its cap.
 *   touch     a tap on a row: an artist opens Cover Flow (coverflow_artist), an album our album page (cc_open_album), a playlist our Songs page, a song plays the library in its order from it.
 *             Dragging the list hides the keyboard, a tap on the field shows it, the keyboard's action key hides it, Back (the X or the hardware key) leaves.
 * No hook, no import; the one timer ends with the page.
 */
#include "offsets.inc"
#include "stock.h"
#include "covercache.h"
#include "common.h"
#include "grid.h"
#include "azlist.h"
#include "keyboard.h"
#include "search.h"
#include "home.h"
#include "i18n.h"
#include "subsonic.h"
#include "songops.h"

extern int coverflow_artist(void *artists, unsigned index, unsigned scope); /* patch/coverflow.c */
extern int albums_open_artist(void *artists, unsigned index,
                              unsigned scope); /* patch/albums.c: -1 when the window will not open */
extern int songs_open_playlist(int id, const char *name); /* patch/songs.c: -1 when it did not open */
extern void pod_toast(const char *text); /* patch/shuffle.c: the stock message box */

#define I(w, off) (*(int *)((char *)(w) + (off)))

#define SE_TERMS 8 /* terms taken from the query (the rest are ignored) */
#define SE_QMAX 64 /* the keyboard's 63 bytes and the NUL */
#define SE_KEY 160 /* code points of a record's key (a longer one is cut) */
#define SE_TILES 16 /* thumbnails kept per kind of shape: the rows in view, two beyond and the history */
#define SE_DRAG 6 /* px a finger moves on the chips before it is a scroll */
#define SE_HZ0 0x4e00u /* the characters whose reading is kept: U+4E00 .. U+9FFF */
#define SE_HZN 0x5200u
#define SE_PAL 254 /* distinct sets of initials (one per reading set: 26 single letters first) */
#define SE_MASK \
    0x80000000u /* a key entry with this bit is a set of initials (bit 0 'a' .. bit 25 'z'), not a code point */

enum { SE_ARTIST, SE_ALBUM, SE_SONG, SE_PLAYLIST, SE_KINDS };
enum { CH_TOP, CH_ARTISTS, CH_ALBUMS, CH_SONGS, CH_PLAYLISTS };

static const unsigned char se_chip_kind[SE_CHIPS] = {0xff, SE_ARTIST, SE_ALBUM, SE_SONG,
                                                     SE_PLAYLIST}; /* the type a chip shows (Top Results: all) */
static const char *const se_chip_key[SE_CHIPS] = {"Top Results", "Artists", "Albums", "Songs", "Playlists"};
static const unsigned se_cap[SE_KINDS] = {SE_CAP_ARTISTS, SE_CAP_ALBUMS, SE_CAP_SONGS, SE_CAP_PLAYLISTS};
static const unsigned char se_top_order[SE_KINDS] = {
    SE_ARTIST, SE_ALBUM, SE_PLAYLIST, SE_SONG}; /* within a quality, Top Results lists the types in this order */

typedef struct {
    unsigned char kind;
    unsigned char pad[3];
    unsigned idx; /* the record in its list */
} se_row_t;

static struct {
    void *win, *view, *sv, *list, *status, *chips, *chl, *field, *st_title, *st_sub, *st_chip, *st_chip_on;
    char query[SE_QMAX], typed[SE_QMAX]; /* the query being applied; the field's text last seen */
    unsigned q[SE_QMAX + 2]; /* its folding */
    unsigned pq[SE_QMAX + 2]; /* the folding of the query the candidates are of */
    unsigned toff[SE_TERMS], tlen[SE_TERMS];
    int nterms, nq, pn, have_prev, loaded;
    void *lists[SE_KINDS]; /* artists, albums, playlists: our copies; songs: the stock list */
    unsigned n[SE_KINDS]; /* their sizes */
    unsigned *cand[SE_KINDS]; /* the records that match, in library order */
    unsigned char *sc[SE_KINDS]; /* ... and how well */
    unsigned nc[SE_KINDS];
    unsigned local_song_count, local_song_matches, nav_count, nav_cursor, nav_match_count;
    int nav_searching;
    sb_library_index_t nav_index;
    sb_library_downloads_t nav_downloads;
    se_row_t *rows;
    int nrows, chip, content;
    int lo, hi; /* the chips of the page: all of them, or only the scope's (lo = scope, hi = lo + 1) */
    int chip_x[SE_CHIPS + 1], chip_sx, chip_down, chip_dx, chip_sx0, chip_drag;
    unsigned chip_text[SE_CHIPS][24];
    int chip_len[SE_CHIPS];
    int press, down, down_x, down_y, pressing;
    int wait; /* ticks until the typed text is applied; 0 none */
    unsigned timer;
    void *chev;
    grid_t ga, gb; /* the thumbnails: artists (round), the others (corners) */
    int py, seen,
        npal; /* the engine is held; a hanzi-range character went into the key being built; palette entries in use */
    unsigned pal[SE_PAL];
    unsigned char *hz; /* SE_HZN bytes, per character: 0 not asked, 1 no reading, else the palette index + 2 */
    char rec[SE_REC_MAX][SE_QMAX]; /* the recent searches, newest first */
    int nrec, rm, dx; /* how many; the list shows them (empty state); the x zone of the press */
    int hitx; /* set by se_item_of: the touch is in the x zone */
    void *cross;
    grid_tile_t rt[SE_REC_MAX + 1]; /* the texts of the rows, then the header */
} se __attribute__((section(".scratch")));

static void se_kick(void);

static void se_show(void *w, int on) {
    if (!w) return;
    widget_set_visible(w, on, 0);
    widget_set_sensitive(w, on);
}

static int se_abs(int v) { return v < 0 ? -v : v; }
static int se_off(void) { return se.sv ? I(se.sv, SC_YOFF) : 0; }
static void se_redraw(void) { widget_invalidate_force(se.sv, (void *)0); }

/* ---------------------------------------------------------------------------
 * Folding. A text becomes lower-case code points with the marks of the Latin letters taken off, katakana as hiragana, full / half width forms as plain, every kind of space as
 * ' ' (the query is split at it). Nothing else changes: a dakuten stays (か is not が), CJK is as it is.
 */
static unsigned
se_next(const char **p) { /* the next UTF-8 character: 0 at the end; a byte that is not UTF-8 is its own code point */
    const unsigned char *s = (const unsigned char *)*p;
    unsigned c = s[0], n = 0, i;
    if (!c) return 0;
    if (c >= 0xf0 && c < 0xf8)
        c &= 7, n = 3;
    else if (c >= 0xe0)
        c &= 15, n = 2;
    else if (c >= 0xc0)
        c &= 31, n = 1;
    else {
        ++*p;
        return c;
    }
    for (i = 1; i <= n; ++i)
        if ((s[i] & 0xc0) != 0x80) {
            ++*p;
            return s[0];
        }
    for (i = 1; i <= n; ++i) c = c << 6 | (s[i] & 63);
    *p += n + 1;
    return c;
}

typedef struct {
    unsigned short lo, hi; /* a range of code points, inclusive */
    char a, b; /* its letters: one or two (b is 0 for one) */
} se_range_t;

static const se_range_t se_latin[] = {
    /* Latin-1 */
    {0xc0, 0xc5, 'a', 0},
    {0xc6, 0xc6, 'a', 'e'},
    {0xc7, 0xc7, 'c', 0},
    {0xc8, 0xcb, 'e', 0},
    {0xcc, 0xcf, 'i', 0},
    {0xd0, 0xd0, 'd', 0},
    {0xd1, 0xd1, 'n', 0},
    {0xd2, 0xd6, 'o', 0},
    {0xd8, 0xd8, 'o', 0},
    {0xd9, 0xdc, 'u', 0},
    {0xdd, 0xdd, 'y', 0},
    {0xde, 0xde, 't', 'h'},
    {0xdf, 0xdf, 's', 's'},
    {0xe0, 0xe5, 'a', 0},
    {0xe6, 0xe6, 'a', 'e'},
    {0xe7, 0xe7, 'c', 0},
    {0xe8, 0xeb, 'e', 0},
    {0xec, 0xef, 'i', 0},
    {0xf0, 0xf0, 'd', 0},
    {0xf1, 0xf1, 'n', 0},
    {0xf2, 0xf6, 'o', 0},
    {0xf8, 0xf8, 'o', 0},
    {0xf9, 0xfc, 'u', 0},
    {0xfd, 0xfd, 'y', 0},
    {0xfe, 0xfe, 't', 'h'},
    {0xff, 0xff, 'y', 0},
    /* Latin Extended-A */
    {0x100, 0x105, 'a', 0},
    {0x106, 0x10d, 'c', 0},
    {0x10e, 0x111, 'd', 0},
    {0x112, 0x11b, 'e', 0},
    {0x11c, 0x123, 'g', 0},
    {0x124, 0x127, 'h', 0},
    {0x128, 0x131, 'i', 0},
    {0x132, 0x133, 'i', 'j'},
    {0x134, 0x135, 'j', 0},
    {0x136, 0x138, 'k', 0},
    {0x139, 0x142, 'l', 0},
    {0x143, 0x14b, 'n', 0},
    {0x14c, 0x151, 'o', 0},
    {0x152, 0x153, 'o', 'e'},
    {0x154, 0x159, 'r', 0},
    {0x15a, 0x161, 's', 0},
    {0x162, 0x167, 't', 0},
    {0x168, 0x173, 'u', 0},
    {0x174, 0x175, 'w', 0},
    {0x176, 0x178, 'y', 0},
    {0x179, 0x17e, 'z', 0},
    {0x17f, 0x17f, 's', 0},
    /* Latin Extended-B, the letters with marks that songs use */
    {0x1cd, 0x1ce, 'a', 0},
    {0x1cf, 0x1d0, 'i', 0},
    {0x1d1, 0x1d2, 'o', 0},
    {0x1d3, 0x1dc, 'u', 0},
    {0x1e6, 0x1e7, 'g', 0},
    {0x1e8, 0x1e9, 'k', 0},
    {0x1ea, 0x1eb, 'o', 0},
    {0x218, 0x219, 's', 0},
    {0x21a, 0x21b, 't', 0},
    /* Latin Extended Additional */
    {0x1e00, 0x1e01, 'a', 0},
    {0x1e02, 0x1e07, 'b', 0},
    {0x1e08, 0x1e09, 'c', 0},
    {0x1e0a, 0x1e13, 'd', 0},
    {0x1e14, 0x1e1d, 'e', 0},
    {0x1e1e, 0x1e1f, 'f', 0},
    {0x1e20, 0x1e21, 'g', 0},
    {0x1e22, 0x1e2b, 'h', 0},
    {0x1e2c, 0x1e2f, 'i', 0},
    {0x1e30, 0x1e35, 'k', 0},
    {0x1e36, 0x1e3d, 'l', 0},
    {0x1e3e, 0x1e43, 'm', 0},
    {0x1e44, 0x1e4b, 'n', 0},
    {0x1e4c, 0x1e53, 'o', 0},
    {0x1e54, 0x1e57, 'p', 0},
    {0x1e58, 0x1e5f, 'r', 0},
    {0x1e60, 0x1e69, 's', 0},
    {0x1e6a, 0x1e71, 't', 0},
    {0x1e72, 0x1e7b, 'u', 0},
    {0x1e7c, 0x1e7f, 'v', 0},
    {0x1e80, 0x1e89, 'w', 0},
    {0x1e8a, 0x1e8d, 'x', 0},
    {0x1e8e, 0x1e8f, 'y', 0},
    {0x1e90, 0x1e95, 'z', 0},
    {0x1e9e, 0x1e9e, 's', 's'},
    {0x1ea0, 0x1eb7, 'a', 0}, /* Vietnamese */
    {0x1eb8, 0x1ec7, 'e', 0},
    {0x1ec8, 0x1ecb, 'i', 0},
    {0x1ecc, 0x1ee3, 'o', 0},
    {0x1ee4, 0x1ef1, 'u', 0},
    {0x1ef2, 0x1ef9, 'y', 0},
};

/* Greek letters with a tonos, as the plain letter (the capitals and small letters of the rest are folded by arithmetic). */
static const unsigned short se_greek[][2] = {{0x386, 0x3b1}, {0x388, 0x3b5}, {0x389, 0x3b7}, {0x38a, 0x3b9},
                                             {0x38c, 0x3bf}, {0x38e, 0x3c5}, {0x38f, 0x3c9}, {0x3ac, 0x3b1},
                                             {0x3ad, 0x3b5}, {0x3ae, 0x3b7}, {0x3af, 0x3b9}, {0x3cc, 0x3bf},
                                             {0x3cd, 0x3c5}, {0x3ce, 0x3c9}, {0x3c2, 0x3c3}};

/* Half-width katakana U+FF66 .. U+FF9D as the full-width katakana. */
static const unsigned short se_half[] = {
    0x30f2, 0x30a1, 0x30a3, 0x30a5, 0x30a7, 0x30a9, 0x30e3, 0x30e5, 0x30e7, 0x30c3, 0x30fc, 0x30a2, 0x30a4, 0x30a6,
    0x30a8, 0x30aa, 0x30ab, 0x30ad, 0x30af, 0x30b1, 0x30b3, 0x30b5, 0x30b7, 0x30b9, 0x30bb, 0x30bd, 0x30bf, 0x30c1,
    0x30c4, 0x30c6, 0x30c8, 0x30ca, 0x30cb, 0x30cc, 0x30cd, 0x30ce, 0x30cf, 0x30d2, 0x30d5, 0x30d8, 0x30db, 0x30de,
    0x30df, 0x30e0, 0x30e1, 0x30e2, 0x30e4, 0x30e6, 0x30e8, 0x30e9, 0x30ea, 0x30eb, 0x30ec, 0x30ed, 0x30ef, 0x30f3};

/* Hiragana h with a dakuten (mark 0x3099) or a handakuten (0x309a): the voiced letter, or 0 when it has none. */
static unsigned se_voice(unsigned h, unsigned mark) {
    int hrow = h == 0x306f || h == 0x3072 || h == 0x3075 || h == 0x3078 || h == 0x307b;
    if (mark == 0x309a) return hrow ? h + 2 : 0;
    if (h == 0x3046) return 0x3094;
    if (hrow || (h >= 0x304b && h <= 0x3061 && !((h - 0x304b) & 1)) ||
        (h >= 0x3064 && h <= 0x3068 && !((h - 0x3064) & 1)))
        return h + 1;
    return 0;
}

/* Code point c as 0, 1 or 2 folded code points in o[]; the count. A mark of the kana (dakuten) comes out as 0x3099 / 0x309a for se_fold to put on the letter before. */
static unsigned se_cp(unsigned c, unsigned *o) {
    unsigned i;
    o[0] = c;
    if (c < 0x80) {
        o[0] = c >= 'A' && c <= 'Z' ? c + 32 : c <= ' ' ? ' ' : c;
        return 1;
    }
    if (c == 0xa0 || c == 0x3000 || (c >= 0x2000 && c <= 0x200a)) return o[0] = ' ', 1;
    if (c >= 0x300 && c <= 0x36f) return 0; /* combining marks (a file name in NFD) */
    if (c < 0x250 || (c >= 0x1e00 && c < 0x1f00)) {
        for (i = 0; i < sizeof se_latin / sizeof *se_latin; ++i)
            if (c >= se_latin[i].lo && c <= se_latin[i].hi) {
                o[0] = (unsigned char)se_latin[i].a, o[1] = (unsigned char)se_latin[i].b;
                return o[1] ? 2 : 1;
            }
        return 1;
    }
    if (c >= 0x370 && c < 0x400) {
        for (i = 0; i < sizeof se_greek / sizeof *se_greek; ++i)
            if (c == se_greek[i][0]) return o[0] = se_greek[i][1], 1;
        if (c >= 0x391 && c <= 0x3a9) o[0] = c + 32;
        return 1;
    }
    if (c >= 0x400 && c < 0x460) { /* Cyrillic: lower case, and ё is е */
        if (c == 0x401 || c == 0x451)
            o[0] = 0x435;
        else if (c < 0x410)
            o[0] = c + 0x50;
        else if (c < 0x430)
            o[0] = c + 0x20;
        return 1;
    }
    if (c >= 0x2018 && c <= 0x201f) return o[0] = c < 0x201c ? '\'' : '"', 1; /* typographic quotes */
    if (c >= 0x2010 && c <= 0x2015) return o[0] = '-', 1;
    if (c >= 0x30a1 && c <= 0x30f6) return o[0] = c - 0x60, 1; /* katakana as hiragana */
    if (c == 0x30fd || c == 0x30fe) return o[0] = c - 0x60, 1;
    if (c == 0x309b || c == 0x3099 || c == 0xff9e) return o[0] = 0x3099, 1;
    if (c == 0x309c || c == 0x309a || c == 0xff9f) return o[0] = 0x309a, 1;
    if (c >= 0xff66 && c <= 0xff9d) { /* (the prolonged sound mark ｰ is U+30FC as it is, not a hiragana) */
        o[0] = se_half[c - 0xff66] == 0x30fc ? 0x30fc : se_half[c - 0xff66] - 0x60;
        return 1;
    }
    if (c >= 0xff21 && c <= 0xff3a) return o[0] = c - 0xff21 + 'a', 1; /* full-width Latin and digits */
    if (c >= 0xff41 && c <= 0xff5a) return o[0] = c - 0xff41 + 'a', 1;
    if (c >= 0xff10 && c <= 0xff19) return o[0] = c - 0xff10 + '0', 1;
    return 1;
}

/* The initials of a character's readings as a set (bit 0 'a' .. bit 25 'z'), as a hz[] byte: 0 when the engine is not there (asked again), 1 for a character without a reading. The engine is the
 * keyboard's Chinese layer's (docs/modules/keyboard.md "Hanzi to pinyin"): MatrixSearch +0xc is the DictTrie, its +4 the DictList, its +8 the SpellingTrie. get_splids_for_hanzi crashes for a character
 * that is not in the dictionary, so get_lemma_id (0: not) is asked first. Every reading counts (行: h and x); a spelling's first letter is its initial (Zh, Ch, Sh are z, c, s). */
static unsigned char se_read_hanzi(unsigned c) {
    void *eng = *(void *volatile *)PY_ENGINE, *trie, *dl, *spt;
    unsigned short ch = (unsigned short)c, ids[8];
    unsigned m = 0, first = 0, n, i;
    if (!eng || !*(volatile unsigned char *)eng || !(trie = ((void **)eng)[3]) || !(dl = ((void **)trie)[1]) ||
        !(spt = ((void **)trie)[2]))
        return 0;
    if (!py_lemma_id(dl, &ch, 1)) return 1;
    n = py_splids(dl, ch, 0, ids, 8);
    for (i = 0; i < n && i < 8; ++i) {
        const char *s = py_spelling(spt, ids[i]);
        unsigned l = s ? (unsigned char)s[0] | 0x20u : 0;
        if (l < 'a' || l > 'z') continue;
        m |= 1u << (l - 'a');
        if (!first) first = 1u << (l - 'a');
    }
    if (!m) return 1;
    for (i = 0; i < (unsigned)se.npal; ++i)
        if (se.pal[i] == m) return (unsigned char)(i + 2);
    if (se.npal < SE_PAL) return se.pal[se.npal] = m, (unsigned char)(se.npal++ + 2);
    for (i = 0; se.pal[i] != first;
         ++i) { /* the palette is full: the first reading's letter (the 26 single letters are the first entries) */
    }
    return (unsigned char)(i + 2);
}

/* The set of initials of character c, 0 when it has none or the engine is not held. */
static unsigned se_hanzi(unsigned c) {
    unsigned char *e;
    if (!se.py || c < SE_HZ0 || c >= SE_HZ0 + SE_HZN) return 0;
    e = &se.hz[c - SE_HZ0];
    if (!*e) *e = se_read_hanzi(c);
    return *e > 1 ? se.pal[*e - 2] : 0;
}

/* The folded s, appended to out[n ..] after a ' ' when n > 0 (a term never has a space, so a match cannot straddle two fields); at most max code points and a 0 in out[max]. The new n.
 * se.seen is set when a character of the hanzi range went in. With py a character that has readings is its set of initials (SE_MASK | bits). */
static unsigned se_cat(const char *s, unsigned *out, unsigned n, unsigned max, int py) {
    unsigned c, o[2], k, i, w;
    if (n && n < max) out[n++] = ' ';
    while (n + 2 <= max && (c = se_next(&s))) {
        if (c - SE_HZ0 < SE_HZN) {
            se.seen = 1;
            if (py && (w = se_hanzi(c))) {
                out[n++] = SE_MASK | w;
                continue;
            }
        }
        k = se_cp(c, o);
        for (i = 0; i < k; ++i) {
            if (o[i] == 0x3099 || o[i] == 0x309a) {
                if (n && (w = se_voice(out[n - 1], o[i]))) out[n - 1] = w;
                continue;
            }
            out[n++] = o[i];
        }
    }
    out[n] = 0;
    return n;
}

/* The folded text alone (a query). External so that the compiler keeps its general form: test/pod/search.py calls it with texts and room of its own. */
__attribute__((noinline)) unsigned se_fold(const char *s, unsigned *out, unsigned max) {
    return se_cat(s, out, 0, max, 0);
}

/* ---------------------------------------------------------------------------
 * Matching
 */
static int se_find(const unsigned *key, unsigned n, const unsigned *t, unsigned tn) {
    unsigned i, j;
    for (i = 0; i + tn <= n; ++i) {
        for (j = 0; j < tn; ++j) {
            unsigned k = key[i + j], d = t[j] - 'a'; /* a set of initials holds the letter when its bit is set */
            if (k != t[j] && !(k >= SE_MASK && d < 26 && (k >> d & 1))) break;
        }
        if (j == tn) return (int)i;
    }
    return -1;
}

/* The query as terms: the folded text split at spaces. */
static void se_set_query(const char *text) {
    unsigned n, i = 0, s;
    se.nterms = 0;
    snprintf(se.query, sizeof se.query, "%s", text);
    n = se_fold(se.query, se.q, SE_QMAX);
    se.nq = (int)n;
    while (i < n && se.nterms < SE_TERMS) {
        while (i < n && se.q[i] == ' ') ++i;
        s = i;
        while (i < n && se.q[i] != ' ') ++i;
        if (i > s) se.toff[se.nterms] = s, se.tlen[se.nterms++] = i - s;
    }
}

/* Is the key's first field (pn code points) the whole query, the terms joined by single spaces? */
static int se_exact(const unsigned *key, unsigned pn) {
    unsigned k = 0, j;
    int t;
    for (t = 0; t < se.nterms; ++t) {
        if (t) {
            if (k >= pn || key[k] != ' ') return 0;
            ++k;
        }
        if (k + se.tlen[t] > pn) return 0;
        for (j = 0; j < se.tlen[t]; ++j)
            if (key[k + j] != se.q[se.toff[t] + j]) return 0;
        k += se.tlen[t];
    }
    return k == pn;
}

/* Does the key (n code points, its first field pn long) hold every term? -1 no; else the quality: 0 the first field is the whole query, 1 the key starts with the first term (a title that
 * begins with what was typed), 2 otherwise. A record's initials key (SE_MASK entries) is one more call of this on its own array (se_search), the better quality of the two kept. */
static int se_test(const unsigned *key, unsigned n, unsigned pn) {
    int t, pos, prefix = 0;
    if (!se.nterms) return -1;
    for (t = 0; t < se.nterms; ++t) {
        pos = se_find(key, n, se.q + se.toff[t], se.tlen[t]);
        if (pos < 0) return -1;
        if (t == 0 && pos == 0) prefix = 1;
    }
    if (!prefix) return 2;
    return se_exact(key, pn) ? 0 : 1;
}

/* The key of a record of a kind: its fields in order, folded (with py: the characters with readings as their initials); *pn the length of the first one (the name). The title of a song falls
 * back to its file name. */
static unsigned se_key(void *rec, int kind, unsigned *key, unsigned *pn, int py) {
    unsigned n;
    if (kind == SE_ARTIST || kind == SE_PLAYLIST) return *pn = se_cat(cc_str(rec, REC_TITLE), key, 0, SE_KEY, py);
    if (kind == SE_ALBUM) {
        const char *al = cc_str(rec, REC_ALBUM);
        n = *pn = se_cat(*al ? al : cc_str(rec, REC_TITLE), key, 0, SE_KEY, py);
        return se_cat(cc_str(rec, REC_ARTIST), key, n, SE_KEY, py);
    }
    n = *pn = se_cat(*cc_str(rec, REC_TITLE) ? cc_str(rec, REC_TITLE) : cc_str(rec, REC_NAME), key, 0, SE_KEY, py);
    n = se_cat(cc_str(rec, REC_ARTIST), key, n, SE_KEY, py);
    return se_cat(cc_str(rec, REC_ALBUM), key, n, SE_KEY, py);
}

/* ---------------------------------------------------------------------------
 * The library: read once, searched in memory
 */
static void se_free_data(void) {
    int k;
    for (k = 0; k < SE_KINDS; ++k) {
        if (se.lists[k] && k != SE_SONG) deque_destroy(se.lists[k]); /* the song list is the stock's own */
        free(se.cand[k]);
        free(se.sc[k]);
        se.lists[k] = (void *)0, se.cand[k] = (unsigned *)0, se.sc[k] = (unsigned char *)0;
        se.n[k] = se.nc[k] = 0;
    }
    sb_library_index_close(&se.nav_index);
    sb_library_downloads_close(&se.nav_downloads);
    se.local_song_count = se.local_song_matches = se.nav_count = se.nav_cursor = se.nav_match_count = 0;
    se.nav_searching = 0;
    se.have_prev = se.loaded = 0;
}

/* The stock song list the rows index is still the one in *pdeq_showlist (another page's query replaces it). */
static int se_valid(void) {
    void *l = se.lists[SE_SONG];
    return !l || (*(void **)PDEQ_SHOWLIST == l && deque_size(l) == se.local_song_count);
}

/* A search key needs the stock record layout; this temporary view points into
 * the read-only, SD-backed Navidrome index and is never retained. */
static void *se_nav_record(const sb_song_t *song, void *record) {
    memset(record, 0, REC_SIZE);
    *(char **)(record + REC_NAME) = (char *)(song->title[0] ? song->title : "Untitled");
    *(char **)(record + REC_TITLE) = (char *)song->title;
    *(char **)(record + REC_ARTIST) = (char *)song->artist;
    *(char **)(record + REC_ALBUM) = (char *)song->album;
    return record;
}

static void *se_result_record(int kind, unsigned index, void *scratch) {
    if (kind == SE_SONG && index >= se.local_song_count && index - se.local_song_count < se.nav_count)
        return se_nav_record(&se.nav_index.songs[index - se.local_song_count], scratch);
    return deque_at(se.lists[kind], index);
}

/* The four stock queries, the songs last so that *pdeq_showlist is the library when it is done, and g_class_type is 0xf001 (as allmusic_page_init leaves it): a stock page under this one
 * (the album page) sees that g_class_type is no longer its own class (its to-foreground handler @0x5266d4 compares it with the class it saved) and runs its own query and list again
 * when this page is gone. */
static void se_load(void) {
    void *list;
    int k;
    se_free_data();
    if (!se.py &&
        pinyin_hold() == 0) { /* the engine's dictionary for the initials; without it the search just has none */
        if (!(se.hz = calloc(SE_HZN, 1))) pinyin_release();
        se.py = se.hz != (unsigned char *)0;
        for (k = 0; k < 26; ++k) se.pal[k] = 1u << k;
        se.npal = 26;
    }
    if (loadLocalClassList(CLASS_ARTISTS) > 0 && (list = *(void **)PDEQ_SHOWLIST) != (void *)0 && deque_size(list))
        se.lists[SE_ARTIST] = cc_copy_list(list);
    se.lists[SE_ALBUM] = cc_albums();
    if (loadLocalClassList(CLASS_PLAYLISTS) > 0 && (list = *(void **)PDEQ_PLAYLIST) != (void *)0 && deque_size(list))
        se.lists[SE_PLAYLIST] = cc_copy_list(list);
    if (loadLocalClassList(CLASS_ALL_SONGS) > 0 && (list = *(void **)PDEQ_SHOWLIST) != (void *)0 && deque_size(list))
        se.lists[SE_SONG] = list;
    *(int *)G_CLASS_TYPE = CLASS_ALL_SONGS;
    se.local_song_count = se.lists[SE_SONG] ? deque_size(se.lists[SE_SONG]) : 0;
    if (!sb_library_index_open(&se.nav_index)) {
        se.nav_count = se.nav_index.count;
        (void)sb_library_downloads_open(&se.nav_downloads);
    }
    if (se.local_song_count <= (unsigned)-1 - se.nav_count)
        se.n[SE_SONG] = se.local_song_count + se.nav_count;
    else
        se.n[SE_SONG] = se.local_song_count;
    for (k = 0; k < SE_KINDS; ++k) {
        if (k != SE_SONG) {
            if (!se.lists[k]) continue;
            se.n[k] = deque_size(se.lists[k]);
        } else if (!se.n[k])
            continue; /* Navidrome-only libraries still need space for async song results */
        se.cand[k] = calloc(se.n[k], sizeof *se.cand[k]);
        se.sc[k] = calloc(se.n[k], 1);
        if (!se.cand[k] || !se.sc[k]) { /* no memory for this type: it has no results */
            free(se.cand[k]);
            free(se.sc[k]);
            se.cand[k] = (unsigned *)0, se.sc[k] = (unsigned char *)0;
        }
    }
    se.loaded = 1;
}

/* The records that match the query now. When its folding starts with the folding of the query the candidates are of, every match is among them: only those are tested (in place: a match
 * is written at or before where it was read). Otherwise the whole list is. */
static void se_search(void) {
    int k, ext = se.have_prev && se.pn > 0 && se.nq >= se.pn;
    unsigned i, key[SE_KEY + 2], key2[SE_KEY + 2], pn, kn;
    for (i = 0; ext && i < (unsigned)se.pn; ++i)
        if (se.q[i] != se.pq[i]) ext = 0;
    for (k = 0; k < SE_KINDS; ++k) {
        unsigned m, w = 0;
        void *list = se.lists[k];
        if ((!list && k != SE_SONG) || !se.cand[k] || !se.nterms ||
            (se.hi - se.lo == 1 && k != se_chip_kind[se.lo])) { /* a scoped page matches its own type only */
            se.nc[k] = 0;
            continue;
        }
        m = ext ? se.nc[k] : se.n[k];
        if (k == SE_SONG) m = ext ? se.nc[k] : se.local_song_count;
        for (i = 0; i < m; ++i) {
            unsigned idx = ext ? se.cand[k][i] : i;
            if (k == SE_SONG && idx >= se.local_song_count)
                continue; /* server matches are scanned in timer-sized batches below */
            void *rec = deque_at(list, idx);
            int tier;
            if ((k == SE_ARTIST || k == SE_ALBUM) && *(int *)((char *)rec + REC_ID) == -1)
                continue; /* "Unknown Artist" / "Unknown Album" */
            se.seen = 0;
            kn = se_key(rec, k, key, &pn, 0);
            tier = se_test(key, kn, pn);
            if (se.py && se.seen &&
                (tier < 0 ||
                 tier ==
                     2)) { /* a record with Chinese characters: its initials can only improve a match that is not a prefix (an initials match is never exact) */
                int t2;
                kn = se_key(rec, k, key2, &pn, 1);
                t2 = se_test(key2, kn, pn);
                if (t2 >= 0 && (tier < 0 || t2 < tier)) tier = t2;
            }
            if (tier >= 0) se.cand[k][w] = idx, se.sc[k][w++] = (unsigned char)tier;
        }
        se.nc[k] = w;
        if (k == SE_SONG) se.local_song_matches = w;
    }
    memcpy(se.pq, se.q, sizeof se.q);
    se.pn = se.nq;
    se.have_prev = se.nterms != 0;
}

/* ---------------------------------------------------------------------------
 * The rows of the selected chip, and the thumbnails' texts
 */
static void se_add(int kind, unsigned idx) {
    se.rows[se.nrows].kind = (unsigned char)kind;
    se.rows[se.nrows++].idx = idx;
}

static void se_grids_reset(void) {
    grid_drop(&se.ga);
    grid_drop(&se.gb);
    grid_placeholder(&se.ga);
    grid_placeholder(&se.gb);
}

static void se_build(void) {
    int t, o, k, cap;
    unsigned j;
    se.nrows = 0;
    se.press = se.down = 0;
    if (se.chip == CH_TOP) {
        for (t = 0; t < 3; ++t)
            for (o = 0; o < SE_KINDS; ++o)
                for (j = 0, k = se_top_order[o]; j < se.nc[k] && se.nrows < SE_CAP_TOP; ++j)
                    if (se.sc[k][j] == t) se_add(k, se.cand[k][j]);
    } else {
        k = se_chip_kind[se.chip], cap = (int)se_cap[k];
        for (t = 0; t < 3; ++t)
            for (j = 0; j < se.nc[k] && se.nrows < cap; ++j)
                if (se.sc[k][j] == t) se_add(k, se.cand[k][j]);
    }
    se_grids_reset();
}

/* ---------------------------------------------------------------------------
 * Recent searches: the last SE_REC_MAX queries the user committed to (a result tapped, the action key), newest first, in SEARCH_RECENT_FILE (one UTF-8 line each).
 * The empty state lists them under a header; a tap on one searches it, a tap on its x removes it.
 */
static unsigned se_rec_fold(const char *t, unsigned *f) { return se_fold(t, f, SE_QMAX); }

/* The index of the entry that folds as t, or -1. */
static int se_rec_find(const char *t) {
    unsigned f[SE_QMAX + 2], g[SE_QMAX + 2], n = se_rec_fold(t, f), i, j;
    for (i = 0; i < (unsigned)se.nrec; ++i) {
        if (se_rec_fold(se.rec[i], g) != n) continue;
        for (j = 0; j < n && f[j] == g[j]; ++j) {
        }
        if (j == n) return (int)i;
    }
    return -1;
}

static void se_rec_prep(void) { /* the rows' texts (cut to their width when first painted) and the header's */
    int i;
    memset(se.rt, 0, sizeof se.rt);
    for (i = 0; i < se.nrec; ++i) grid_set(&se.rt[i], se.rec[i], "", 0);
    grid_set(&se.rt[SE_REC_MAX], "", TR("Recently Searched"), 0);
}

static void se_rec_save(void) {
    char buf[SE_REC_MAX * SE_QMAX + 1];
    unsigned k = 0, n;
    int i;
    for (i = 0; i < se.nrec; ++i) {
        for (n = 0; se.rec[i][n]; ++n) {
        }
        memcpy(buf + k, se.rec[i], n);
        k += n;
        buf[k++] = '\n';
    }
    buf[k] = 0;
    home_write_atomic(SEARCH_RECENT_FILE, SEARCH_RECENT_TMP, buf);
}

/* The file into se.rec; anything malformed (too long, a line too long, empty or control characters, a repeat, too many lines) is no history at all. */
static void se_rec_load(void) {
    char buf[SE_REC_MAX * SE_QMAX + 2];
    int fd, n, p = 0;
    se.nrec = 0;
    fd = open(SEARCH_RECENT_FILE, 0, 0);
    if (fd >= 0) {
        n = read(fd, buf, sizeof buf);
        close(fd);
        while (n > 0 && n < (int)sizeof buf && p < n) {
            int e = p, i;
            while (e < n && buf[e] != '\n') ++e;
            if (e == p || e - p >= SE_QMAX || se.nrec == SE_REC_MAX) goto bad;
            for (i = p; i < e; ++i)
                if ((unsigned char)buf[i] < 0x20) goto bad;
            memcpy(se.rec[se.nrec], buf + p, (unsigned)(e - p));
            se.rec[se.nrec][e - p] = 0;
            if (se_rec_find(se.rec[se.nrec]) >= 0) goto bad;
            se.nrec++;
            p = e + 1;
        }
        if (n >= (int)sizeof buf) goto bad;
    }
    se_rec_prep();
    return;
bad:
    se.nrec = 0;
    se_rec_prep();
}

/* A query the user committed to: trimmed, at the top (an entry that folds the same moves there), the file written only when the list changed. */
static void se_rec_add(const char *text) {
    char t[SE_QMAX];
    unsigned n = 0;
    int i, at;
    while (*text == ' ' || *text == '\t') ++text;
    while (text[n]) ++n;
    while (n && (text[n - 1] == ' ' || text[n - 1] == '\t')) --n;
    if (!n || n >= SE_QMAX) return;
    memcpy(t, text, n);
    t[n] = 0;
    at = se_rec_find(t);
    if (at == 0 && !strcmp(se.rec[0], t)) return;
    if (at < 0) at = se.nrec < SE_REC_MAX ? se.nrec++ : SE_REC_MAX - 1;
    for (i = at; i > 0; --i) memcpy(se.rec[i], se.rec[i - 1], SE_QMAX);
    memcpy(se.rec[0], t, n + 1);
    se_rec_save();
    se_rec_prep();
}

static void se_rec_remove(int at) {
    int i;
    for (i = at; i + 1 < se.nrec; ++i) memcpy(se.rec[i], se.rec[i + 1], SE_QMAX);
    se.nrec--;
    se_rec_save();
    se_rec_prep();
}

/* The content: the rows, then the air under them, or the keyboard's height while it is up (the list scrolls clear of it); the list or "No Results" shows.
 * With no query and a history the content is the recent searches instead (se.rm). */
static void se_layout(void) {
    int pad = keyboard_shown() ? KB_H : SE_BOTTOM, h, off = se_off();
    se.rm = se.nterms == 0 && se.nrows == 0 && se.nrec != 0;
    se.content = se.rm ? SE_REC_HEAD_H + se.nrec * SE_REC_ROW_H + pad : se.nrows * SE_ROW_H + pad;
    h = se.content < SE_LIST_H ? SE_LIST_H : se.content;
    widget_resize(se.view, 320, h);
    widget_set_prop_int(se.sv, "virtual_h", h);
    if (off > h - SE_LIST_H) widget_set_prop_int(se.sv, "yoffset", h - SE_LIST_H);
    se_show(se.list, se.nrows != 0 || se.rm);
    se_show(se.status, se.nrows == 0 && se.nterms != 0);
    if (se.nrows == 0 && se.nterms != 0) widget_set_tr_text(se.status, "No Results");
}

/* The typed text is applied: the library is read if it has not been (or another query replaced the song list), the query is searched, the rows of the chip built. */
static void se_apply(void) {
    if (!se.loaded || !se_valid()) se_load();
    se_set_query(se.typed);
    se_search();
    se.nav_cursor = se.nav_match_count = 0;
    se.nav_searching =
        se.nav_index.songs != (const sb_song_t *)0 && se.nterms != 0 && se.cand[SE_SONG] && se.sc[SE_SONG];
    widget_set_prop_int(se.sv, "yoffset", 0);
    se_build();
    se_layout();
    if (se.nav_searching && !se.nrows) widget_set_text_utf8(se.status, "Searching Navidrome...");
    se_redraw();
    se_kick();
}

#define SE_NAV_BATCH 256
static int se_nav_search_step(void) {
    unsigned end;
    if (!se.nav_searching || !se.nav_index.songs || !se.cand[SE_SONG] || !se.sc[SE_SONG]) return 0;
    end = se.nav_cursor + SE_NAV_BATCH;
    if (end < se.nav_cursor || end > se.nav_index.count) end = se.nav_index.count;
    while (se.nav_cursor < end) {
        unsigned index = se.nav_cursor++;
        const sb_song_t *song = &se.nav_index.songs[index];
        unsigned record[REC_SIZE / 4];
        unsigned key[SE_KEY + 2];
        unsigned pn, kn;
        int tier;
        if (sb_library_is_dsd(song) || sb_library_downloads_contains(&se.nav_downloads, song)) continue;
        se.seen = 0;
        kn = se_key(se_nav_record(song, record), SE_SONG, key, &pn, 0);
        tier = se_test(key, kn, pn);
        if (se.py && se.seen && (tier < 0 || tier == 2)) {
            unsigned alt[SE_KEY + 2];
            int t2;
            kn = se_key(se_nav_record(song, record), SE_SONG, alt, &pn, 1);
            t2 = se_test(alt, kn, pn);
            if (t2 >= 0 && (tier < 0 || t2 < tier)) tier = t2;
        }
        if (tier >= 0 && se.nc[SE_SONG] < se.n[SE_SONG]) {
            se.cand[SE_SONG][se.nc[SE_SONG]] = se.local_song_count + index;
            se.sc[SE_SONG][se.nc[SE_SONG]++] = (unsigned char)tier;
            ++se.nav_match_count;
        }
    }
    if (se.nav_cursor < se.nav_index.count) return 1;
    se.nav_searching = 0;
    memcpy(se.pq, se.q, sizeof se.q);
    se.pn = se.nq;
    se.have_prev = se.nterms != 0;
    se_build();
    se_layout();
    se_redraw();
    return 0;
}

static unsigned
se_artist_cover(const char *name) { /* an artist's picture: the cover of the first album of theirs that has one */
    char url[80];
    unsigned i, n = se.n[SE_ALBUM];
    for (i = 0; *name && i < n; ++i) {
        void *a = deque_at(se.lists[SE_ALBUM], i);
        if (!cc_nocase(cc_str(a, REC_ARTIST), name) && cc_url(url, cc_album_key(a))) return cc_album_key(a);
    }
    return 0;
}

/* The texts of row r into its tile: the title, then the grey line ("Artist", "Album · artist", "Song · artist", "Playlist"). Paint calls this for a fresh
 * tile, so it only formats: the cover key (cache file lookups on the SD card) is resolved by the loader (se_art). */
static void se_prep(grid_tile_t *t, int r) {
    const se_row_t *w = &se.rows[r];
    unsigned scratch[REC_SIZE / 4];
    void *rec = se_result_record(w->kind, w->idx, scratch);
    char sub[160];
    const char *a = cc_str(rec, REC_ARTIST), *title = cc_str(rec, REC_TITLE);
    switch (w->kind) {
    case SE_ARTIST:
        snprintf(sub, sizeof sub, "%s", TR("Artist"));
        break;
    case SE_ALBUM:
        if (*cc_str(rec, REC_ALBUM)) title = cc_str(rec, REC_ALBUM);
        snprintf(sub, sizeof sub, *a ? "%s \xc2\xb7 %s" : "%s", TR("album"), a);
        break;
    case SE_PLAYLIST:
        snprintf(sub, sizeof sub, "%s", TR("Playlist"));
        break;
    default:
        if (!*title) title = cc_str(rec, REC_NAME);
        snprintf(sub, sizeof sub, *a ? "%s \xc2\xb7 %s" : "%s", TR("Song"), a);
        break;
    }
    grid_set(t, title, sub, 0);
}

/* ---------------------------------------------------------------------------
 * Paint: the rows (one EVT_AFTER_PAINT of the content view, in window coordinates: the Artists page's), and the chips
 */
static void se_span(int *r0, int *r1) {
    int off = se_off();
    *r0 = off < 0 ? 0 : off / SE_ROW_H;
    *r1 = (off + SE_LIST_H - 1) / SE_ROW_H;
    if (*r1 > se.nrows - 1) *r1 = se.nrows - 1;
}

static grid_tile_t *se_tile(int r) {
    grid_t *g = se.rows[r].kind == SE_ARTIST ? &se.ga : &se.gb;
    int r0, r1, fresh;
    grid_tile_t *t;
    se_span(&r0, &r1);
    t = grid_tile(g, r, r0 - 2, r1 + 2, &fresh);
    if (fresh) se_prep(t, r);
    return t;
}

static grid_tile_t *se_cover_next(grid_t **gp);

static void se_paint_rows(void *canvas) {
    int r0, r1, r, off = se_off(), pass;
    se_span(&r0, &r1);
    for (r = r0; r <= r1; ++r) {
        int y = r * SE_ROW_H - off, kind = se.rows[r].kind;
        grid_tile_t *t = se_tile(r);
        if (se.press == r + 1) az_fill(canvas, 0, y, y + SE_ROW_H - 1, 320, LIST_PRESS);
        grid_blit(canvas, kind == SE_ARTIST ? &se.ga : &se.gb, t, SE_ART_X, y + SE_ART_Y, SE_LIST_H);
        az_fill(canvas, SE_TEXT_LEFT, y + SE_ROW_H - 1, y + SE_ROW_H, SE_SEP_END - SE_TEXT_LEFT, LIST_HAIR);
        if (kind != SE_SONG && se.chev) {
            int src[4], dst[4], top = y + (SE_ROW_H - POD_CHEV_H) / 2;
            if (top >= 0 && top + POD_CHEV_H <= SE_LIST_H) {
                src[0] = src[1] = 0, src[2] = POD_CHEV_W, src[3] = POD_CHEV_H;
                dst[0] = SE_CHEV_X, dst[1] = top, dst[2] = POD_CHEV_W, dst[3] = POD_CHEV_H;
                canvas_draw_image(canvas, se.chev, src, dst);
            }
        }
    }
    for (pass = 0; pass < 2; ++pass) { /* the titles, then the grey lines: one text style at a time */
        widget_prepare_text_style(pass ? se.st_sub : se.st_title, canvas);
        for (r = r0; r <= r1; ++r) {
            int end = se.rows[r].kind == SE_SONG ? SE_END_PLAIN : SE_END_CHEV;
            grid_text(canvas, se_tile(r), pass, SE_TEXT_LEFT, r * SE_ROW_H - off + (pass ? SE_SUB_Y : SE_TITLE_Y),
                      end - SE_TEXT_LEFT, pass ? LIST_SUB_H : LIST_TITLE_H, 0);
        }
    }
}

/* The recent searches: the header, then a row each (the query, an x on the right), a hairline under every row. */
static void se_paint_recent(void *canvas) {
    int i, off = se_off(), pass;
    for (i = 0; i < se.nrec; ++i) {
        int y = SE_REC_HEAD_H + i * SE_REC_ROW_H - off;
        if (se.press == i + 1) az_fill(canvas, 0, y, y + SE_REC_ROW_H - 1, 320, LIST_PRESS);
        az_fill(canvas, SE_REC_TEXT_X, y + SE_REC_ROW_H - 1, y + SE_REC_ROW_H, SE_SEP_END - SE_REC_TEXT_X, LIST_HAIR);
        if (se.cross) {
            int src[4], dst[4], top = y + (SE_REC_ROW_H - POD_CROSS) / 2;
            if (top >= 0 && top + POD_CROSS <= SE_LIST_H) {
                src[0] = src[1] = 0, src[2] = src[3] = POD_CROSS;
                dst[0] = SE_REC_X_C - POD_CROSS / 2, dst[1] = top, dst[2] = dst[3] = POD_CROSS;
                canvas_draw_image(canvas, se.cross, src, dst);
            }
        }
    }
    for (pass = 0; pass < 2; ++pass) { /* the queries in the title style, then the header in the grey one */
        widget_prepare_text_style(pass ? se.st_sub : se.st_title, canvas);
        if (pass)
            grid_text(canvas, &se.rt[SE_REC_MAX], 1, SE_REC_TEXT_X, SE_REC_HEAD_H - LIST_SUB_H - 6 - off,
                      SE_REC_TEXT_END - SE_REC_TEXT_X, LIST_SUB_H, 0);
        else
            for (i = 0; i < se.nrec; ++i)
                grid_text(canvas, &se.rt[i], 0, SE_REC_TEXT_X,
                          SE_REC_HEAD_H + i * SE_REC_ROW_H + (SE_REC_ROW_H - LIST_TITLE_H) / 2 - off,
                          SE_REC_TEXT_END - SE_REC_TEXT_X, LIST_TITLE_H, 0);
    }
}

static int se_on_paint(void *ctx, void *e) {
    void *canvas = e ? *(void **)((char *)e + EVENT_PAINT_CANVAS) : (void *)0;
    int off = se_off();
    grid_t *g;
    (void)ctx;
    if (canvas && se.view && se.rm) {
        I(canvas, CANVAS_OY) += off;
        se_paint_recent(canvas);
        I(canvas, CANVAS_OY) -= off;
        return RET_OK;
    }
    if (!canvas || !se.view || !se.rows || !se.nrows) return RET_OK;
    if (!se_valid()) { /* another query replaced the stock song list: nothing of it is read; the timer reads it again */
        if (!se.wait) se.wait = 1;
        se_kick();
        return RET_OK;
    }
    I(canvas, CANVAS_OY) += off;
    se_paint_rows(canvas);
    I(canvas, CANVAS_OY) -= off;
    if (se_cover_next(&g))
        se_kick(); /* new tiles (another chip, a scroll) after the timer ended: it loads their covers */
    return RET_OK;
}

/* The chips: the selected one's pill is a view behind (se.chl, moved under it); the texts are painted here, the selected one in the dark style over it. */
static int se_chip_w(int i) { return se.chip_x[i + 1] - se.chip_x[i] - SE_CHIP_GAP; }

static void se_chip_fx(void) {
    widget_move(se.chl, se.chip_x[se.chip] - se.chip_sx, SE_CHIP_Y);
    widget_resize(se.chl, se_chip_w(se.chip), SE_CHIP_H);
    widget_set_visible(se.chl, 1, 0);
    widget_invalidate_force(se.chips, (void *)0);
}

static int se_chips_end(void) { return se.chip_x[se.hi] - SE_CHIP_GAP + SE_CHIP_X; }

static int se_on_chips_paint(void *ctx, void *e) {
    void *canvas = e ? *(void **)((char *)e + EVENT_PAINT_CANVAS) : (void *)0;
    int i, pass;
    (void)ctx;
    if (!canvas || !se.chips) return RET_OK;
    for (pass = 0; pass < 2; ++pass) {
        widget_prepare_text_style(pass ? se.st_chip_on : se.st_chip, canvas);
        for (i = se.lo; i < se.hi; ++i) {
            int rect[4];
            if ((i == se.chip) != pass) continue;
            rect[0] = se.chip_x[i] - se.chip_sx, rect[1] = SE_CHIP_Y, rect[2] = se_chip_w(i), rect[3] = SE_CHIP_H;
            if (rect[0] + rect[2] <= 0 || rect[0] >= 320) continue;
            canvas_draw_text_in_rect(canvas, se.chip_text[i], (unsigned)se.chip_len[i], rect);
        }
    }
    return RET_OK;
}

/* The chips' places from the texts' widths in the chip font (the page's language). */
static void se_chips_setup(void) {
    int i, x = SE_CHIP_X;
    for (i = se.lo; i < se.hi; ++i) {
        const char *s = TR(se_chip_key[i]);
        unsigned n = 0;
        float f;
        while (s[n] && n < 60) n++;
        memset(se.chip_text[i], 0, sizeof se.chip_text[i]);
        tk_utf8_to_utf16_ex(s, n, se.chip_text[i], 23);
        se.chip_len[i] = 0;
        while (se.chip_text[i][se.chip_len[i]]) se.chip_len[i]++;
        f = widget_measure_text(se.st_chip, se.chip_text[i]);
        se.chip_x[i] = x;
        x += (f > 0.0f ? (int)(f + 0.999f) : se.chip_len[i] * 9) + 2 * SE_CHIP_PAD + SE_CHIP_GAP;
    }
    se.chip_x[se.hi] = x;
}

/* Select a chip: scrolled into view, the rows of that type built from the matches already known. */
static __attribute__((noinline)) void se_chip_set(int k) {
    int l = se.chip_x[k] - SE_CHIP_X, r = se.chip_x[k] + se_chip_w(k) + SE_CHIP_X, mx = se_chips_end() - 320;
    se.chip = k;
    if (l < se.chip_sx) se.chip_sx = l;
    if (r > se.chip_sx + 320) se.chip_sx = r - 320;
    if (se.chip_sx > mx) se.chip_sx = mx;
    if (se.chip_sx < 0) se.chip_sx = 0;
    se_chip_fx();
    widget_set_prop_int(se.sv, "yoffset", 0);
    se_build();
    se_layout();
    se_redraw();
}

static int
se_chip_at(int x) { /* the chip under x (the row's coordinates), the nearest one for a gap, -1 past the ends */
    int i;
    x += se.chip_sx;
    for (i = se.lo; i < se.hi; ++i)
        if (x < se.chip_x[i + 1]) return x >= se.chip_x[i] - SE_CHIP_GAP / 2 ? i : -1;
    return -1;
}

static int se_on_chips(void *ctx, void *e) {
    int pt[2], type = e ? *(int *)e : 0, mx = se_chips_end() - 320;
    (void)ctx;
    if (!se.win || !e) return RET_OK;
    pt[0] = I(e, PE_X), pt[1] = I(e, PE_Y);
    widget_to_local(se.chips, pt);
    if (type == EVT_POINTER_DOWN) {
        se.chip_down = 1, se.chip_drag = 0, se.chip_dx = pt[0], se.chip_sx0 = se.chip_sx;
    } else if (type == EVT_POINTER_MOVE && se.chip_down) {
        int dx = pt[0] - se.chip_dx;
        if (!se.chip_drag && se_abs(dx) >= SE_DRAG) se.chip_drag = 1;
        if (se.chip_drag) {
            se.chip_sx = se.chip_sx0 - dx;
            if (se.chip_sx > mx) se.chip_sx = mx;
            if (se.chip_sx < 0) se.chip_sx = 0;
            se_chip_fx();
        }
    } else if (type == EVT_POINTER_UP || type == EVT_POINTER_ABORT) {
        int tap = se.chip_down && !se.chip_drag && type == EVT_POINTER_UP, k = tap ? se_chip_at(pt[0]) : -1;
        se.chip_down = se.chip_drag = 0;
        if (k >= 0 && k != se.chip) se_chip_set(k);
    }
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * Touch: a press remembers its row, a drag takes it back (and puts the keyboard away), a lift within the threshold on the same row acts
 */
static int se_at(int y) {
    if (se.rm) {
        y -= SE_REC_HEAD_H;
        return y >= 0 && y / SE_REC_ROW_H < se.nrec ? y / SE_REC_ROW_H : -1;
    }
    return y >= 0 && y / SE_ROW_H < se.nrows ? y / SE_ROW_H : -1;
}

static int se_item_of(void *e) {
    int pt[2];
    pt[0] = I(e, PE_X), pt[1] = I(e, PE_Y);
    widget_to_local(se.view, pt);
    se.hitx = pt[0] >= SE_REC_X && pt[0] < SE_REC_X + SE_REC_X_W;
    return se_at(pt[1]);
}

static void se_set_press(int p) {
    if (se.press == p) return;
    se.press = p;
    se_redraw();
}

/* A song: the library in its stock order (the Songs page's class) as the queue, Now Playing at the song (patch/songs.c sg_play_at: the stock Songs row's handler). */
static void se_play(int at) {
    void *pick, *queue, *first;
    unsigned n, idx = 0;
    int found;
    struct {
        void *dq;
        int idx, cls, mode;
    } context;
    if (se.rows[at].idx >= se.local_song_count) {
        sb_library_queue_entry_t entry;
        memset(&entry, 0, sizeof entry);
        entry.server_song = &se.nav_index.songs[se.rows[at].idx - se.local_song_count];
        entry.server_index = se.rows[at].idx - se.local_song_count;
        entry.source = SB_LIBRARY_STREAM;
        (void)sb_library_play_queue(&entry, 1, 0, SO_KEEP);
        return;
    }
    pick = deque_at(se.lists[SE_SONG], se.rows[at].idx);
    queue = _create_deque("stSongInfo");
    if (!queue) return;
    deque_init(queue);
    found = loadSongList(queue, cc_str(pick, REC_NAME), I(pick, REC_CUE_START), CLASS_ALL_SONGS);
    n = deque_size(queue);
    if (n) { /* loadSongList finds a song by file name and CUE start: the row's own index in the list wins for a duplicate name */
        unsigned row = se.rows[at].idx;
        if (row < n && !strcmp(cc_str(deque_at(queue, row), REC_PATH), cc_str(pick, REC_PATH)))
            idx = row;
        else if (found >= 0 && (unsigned)found < n)
            idx = (unsigned)found;
    }
    first = n ? deque_at(queue, idx) : (void *)0;
    if (!first || access(cc_str(first, REC_PATH), F_OK)) {
        deque_destroy(queue);
        pod_toast(TR(n ? "Storage unavailable" : "Update Local Music first"));
        return;
    }
    *(int *)G_CLASS_TYPE = CLASS_ALL_SONGS;
    context.dq = queue, context.idx = (int)idx, context.cls = CLASS_ALL_SONGS, context.mode = PLAY_MODE;
    navigator_to_with_context("playing_page", &context); /* start_player copies the queue */
    deque_destroy(queue);
}

/* A tap on a result row (a symbol of its own: the tests call it with a row). */
/* A tap on a recent search (a symbol of its own: the tests call it): its x removes it; the row searches it now, as if it had been typed. */
static __attribute__((noinline)) void se_rec_tap(int i, int on_x) {
    char q[SE_QMAX];
    if (i < 0 || i >= se.nrec) return;
    if (on_x) {
        se_rec_remove(i);
        se.press = 0;
        se_layout();
        se_redraw();
        return;
    }
    memcpy(q, se.rec[i], SE_QMAX);
    keyboard_set_text(q);
    se.wait = 0;
    se_apply();
}

static __attribute__((noinline)) void se_open_row(int i) {
    void *rec;
    if (i < 0 || i >= se.nrows) return;
    se_rec_add(se.query);
    switch (se.rows[i].kind) {
    case SE_ARTIST:
        if (albums_open_artist(se.lists[SE_ARTIST], se.rows[i].idx, CLASS_ARTISTS) == -1)
            coverflow_artist(se.lists[SE_ARTIST], se.rows[i].idx, CLASS_ARTISTS);
        break;
    case SE_ALBUM:
        cc_open_album((void *)0, 0, (int)se.rows[i].idx); /* the Albums list's rows are the stock rows */
        break;
    case SE_PLAYLIST: /* as the Playlists page's tap: our Songs page, else the stock one */
        rec = deque_at(se.lists[SE_PLAYLIST], se.rows[i].idx);
        if (songs_open_playlist(I(rec, REC_DISC), cc_str(rec, REC_TITLE)) == -1) {
            snprintf((char *)NAV_TITLE, 0x200, "%s", cc_str(rec, REC_TITLE));
            *(int *)(CLASSINFO + 4) = I(rec, REC_DISC);
            navigator_to_with_context("allmusic_page", (const void *)CLASS_PLAYLIST_SONGS);
        }
        break;
    default:
        if (!se_valid()) {
            se.wait = 1; /* another query replaced the list: it is read again, the tap is lost */
            se_kick();
            break;
        }
        se_play(i);
        break;
    }
}

static int se_on_down(void *ctx, void *e) {
    int a;
    (void)ctx;
    se.down = 0;
    se.pressing = 1;
    if (!e || !se.view) return RET_OK;
    a = se_item_of(e);
    se.dx = se.hitx;
    se.down = a + 1, se.down_x = I(e, PE_X), se.down_y = I(e, PE_Y);
    se_set_press(a + 1);
    return RET_OK;
}

static int se_on_up(void *ctx, void *e) {
    int a = se.down - 1;
    (void)ctx;
    se.down = 0, se.pressing = 0;
    se_set_press(0);
    if (a < 0 || !e || !se.view) return RET_OK;
    if (se_abs(I(e, PE_X) - se.down_x) < SC_DRAG_PX && se_abs(I(e, PE_Y) - se.down_y) < SC_DRAG_PX &&
        se_item_of(e) == a && se.hitx == se.dx) {
        if (se.rm)
            se_rec_tap(a, se.dx);
        else
            se_open_row(a);
    }
    return RET_OK;
}

static void se_kb_hide(void) {
    keyboard_show(0);
    se_layout();
    se_redraw();
}

/* The scroll_view took the gesture as a drag (it aborts its children's press): the keyboard goes away. */
static int se_on_abort(void *ctx, void *e) {
    int drag = se.pressing;
    (void)ctx;
    (void)e;
    se.down = se.pressing = 0;
    se_set_press(0);
    if (drag && keyboard_shown()) se_kb_hide();
    return RET_OK;
}

static int se_on_bg(void *ctx,
                    void *e) { /* the page goes behind another: the press is let go, the keyboard stays as it is */
    (void)ctx;
    (void)e;
    se.down = se.pressing = 0;
    se_set_press(0);
    return RET_OK;
}

/* A tap on the field brings the keyboard back. */
static int se_on_field(void *ctx, void *e) {
    (void)ctx;
    if (e && *(int *)e == EVT_POINTER_UP && !keyboard_shown()) {
        keyboard_show(1);
        se_layout();
        se_redraw();
    }
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * The keyboard's callbacks, the one timer, the page
 */
static void
se_on_text(const char *text) { /* the field's text may have changed: apply it SE_DEBOUNCE ticks after the last change */
    if (!se.win || !strcmp(text, se.typed)) return;
    snprintf(se.typed, sizeof se.typed, "%s", text);
    se.wait = SE_DEBOUNCE;
    se_kick();
}

static void se_on_go(void) { /* the keyboard's action key: a query is kept as a recent search */
    se_rec_add(keyboard_text());
    se_kb_hide();
}

/* The first row in view (or two beyond) whose tile has no thumbnail yet: its grid and tile; 0 when there is none. */
static grid_tile_t *se_cover_next(grid_t **gp) {
    int r0, r1, r;
    if (!se.rows || !se.nrows) return (grid_tile_t *)0;
    se_span(&r0, &r1);
    for (r = r0; r <= r1 + 2 && r < se.nrows; ++r) {
        grid_t *g = se.rows[r].kind == SE_ARTIST ? &se.ga : &se.gb;
        grid_tile_t *t = grid_find(g, r);
        if (t && !t->art) {
            *gp = g;
            return t;
        }
    }
    return (grid_tile_t *)0;
}

/* The cover of a tile: the key of its row (a song's or album's own cover, an artist's first album with one) and its decode; no file ends as the placeholder (art 2). */
static void se_art(grid_t *g, grid_tile_t *t, int r) {
    const se_row_t *w = &se.rows[r];
    unsigned scratch[REC_SIZE / 4];
    void *rec = se_result_record(w->kind, w->idx, scratch);
    char url[512];
    switch (w->kind) {
    case SE_ARTIST:
        t->ckey = se_artist_cover(cc_str(rec, REC_TITLE));
        break;
    case SE_ALBUM:
        t->ckey = cc_cover_key(se.lists[SE_ALBUM], cc_album_key(rec),
                               *cc_str(rec, REC_ALBUM) ? cc_str(rec, REC_ALBUM) : cc_str(rec, REC_TITLE), url);
        grid_art_url(g, t, *url ? url : (const char *)0);
        return;
    case SE_PLAYLIST:
        break;
    default:
        if (w->idx >= se.local_song_count) {
            const sb_song_t *song = &se.nav_index.songs[w->idx - se.local_song_count];
            grid_art_url(g, t, sb_library_cover_url(song, url, sizeof url) > 0 ? url : (const char *)0);
            return;
        }
        t->ckey = cc_cover_key(se.lists[SE_ALBUM], cc_album_key(rec), cc_str(rec, REC_ALBUM), url);
        grid_art_url(g, t, *url ? url : (const char *)0);
        return;
    }
    grid_art(g, t);
}

/* One cover per tick; 1 when one was made, or is waiting for the list to stop: nothing is read or decoded while the scroll_view moves. */
static int se_cover_step(void) {
    grid_t *g;
    grid_tile_t *t = se_cover_next(&g);
    if (!t) return 0;
    if (grid_moving(se.sv)) return 1;
    se_art(g, t, t->album - 1);
    se_redraw();
    return 1;
}

static int se_tick(const void *timer) {
    (void)timer;
    if (!se.win) return RET_OK;
    if (se.wait > 0 && --se.wait == 0) {
        se_apply();
        return RET_REPEAT;
    }
    if (se.wait > 0 || se_nav_search_step() || se_cover_step()) return RET_REPEAT;
    se.timer = 0;
    return RET_OK;
}

static void se_kick(void) {
    if (!se.timer) se.timer = timer_add(se_tick, (void *)0, SE_TICK_MS);
}

/* Back to the front: the stock song list was replaced under the page (an album or an artist was opened from it), or the library was read before the page was shown: read it again. */
static int se_on_fg(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (se.win && se.loaded && !se_valid()) {
        se.wait = 1;
        se_kick();
    }
    return RET_OK;
}

static int se_on_destroy(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    keyboard_detach();
    if (se.py) pinyin_release(); /* the engine's megabyte goes back with the page */
    free(se.hz);
    if (se.timer) timer_remove(se.timer);
    se_free_data();
    grid_free(&se.ga);
    grid_free(&se.gb);
    if (se.chev) bitmap_destroy(se.chev);
    if (se.cross) bitmap_destroy(se.cross);
    free(se.rows);
    memset(&se, 0, sizeof se);
    return RET_OK;
}

/* The Songs page's Search and the Menu's Search item: the Search page over the page in front, the keyboard up and the results empty. 0 once it is up; -1: not opened (a Search page
 * exists already, or the window or its widgets are not there): the caller opens the stock search page. scope is SEARCH_ALL or one type: that page shows its one chip (selected, the others
 * not drawn or tappable) and matches only that type. */
int search_open_in(int scope) {
    if (se.win || scope < SEARCH_ALL || scope >= SE_CHIPS) return -1;
    memset(&se, 0, sizeof se);
    se.lo = scope == SEARCH_ALL ? 0 : scope, se.hi = scope == SEARCH_ALL ? SE_CHIPS : scope + 1;
    se.win = window_open("m1plus_search");
    if (!se.win) {
        memset(&se, 0, sizeof se);
        return -1;
    }
    widget_on(se.win, EVT_DESTROY, se_on_destroy, (void *)0);
    pod_bind(se.win, "btn_return", pod_on_back, (void *)0);
    se.list = widget_lookup(se.win, "se_listview", 1);
    se.sv = widget_lookup(se.win, "se_scrollview", 1);
    se.view = widget_lookup(se.win, "view_grid", 1);
    se.status = widget_lookup(se.win, "label_status", 1);
    se.chips = widget_lookup(se.win, "se_chips", 1);
    se.chl = widget_lookup(se.win, "se_chip_hl", 1);
    se.field = widget_lookup(se.win, "kb_field", 1);
    se.st_title = widget_lookup(se.win, "label_row_title", 1);
    se.st_sub = widget_lookup(se.win, "label_row_sub", 1);
    se.st_chip = widget_lookup(se.win, "label_chip", 1);
    se.st_chip_on = widget_lookup(se.win, "label_chip_on", 1);
    se.rows = calloc(SE_MAX_ROWS, sizeof *se.rows);
    se.chev = pod_make_chevron();
    se.cross = pod_make_cross();
    if (!se.rows || !se.list || !se.sv || !se.view || !se.status || !se.chips || !se.chl || !se.field || !se.st_title ||
        !se.st_sub || !se.st_chip || !se.st_chip_on || !grid_init(&se.ga, se.win, SE_TILES, SE_ART, SE_ART / 2) ||
        !grid_init(&se.gb, se.win, SE_TILES, SE_ART, SE_ART_R)) {
        navigator_back(); /* an asset that is not ours, or no memory: the destroy handler frees what exists */
        return -1;
    }
    grid_shape(&se.ga, SE_ART, SE_ART / 2, 1); /* corners cut in the alpha: the pressed row's fill shows behind them */
    grid_shape(&se.gb, SE_ART, SE_ART_R, 1);
    se_grids_reset();
    if (keyboard_attach(se.win, TR("Search"), SE_TEXT_X, SE_TEXT_W, SE_CARET_Y, se_on_text, se_on_go) != 0) {
        navigator_back();
        return -1;
    }
    widget_on(se.win, EVT_WINDOW_TO_FG, se_on_fg, (void *)0);
    widget_on(se.win, EVT_WINDOW_TO_BG, se_on_bg, (void *)0);
    widget_on(se.view, EVT_POINTER_DOWN, se_on_down, (void *)0);
    widget_on(se.view, EVT_POINTER_UP, se_on_up, (void *)0);
    widget_on(se.view, EVT_POINTER_ABORT, se_on_abort, (void *)0);
    widget_on(se.view, EVT_AFTER_PAINT, se_on_paint, (void *)0);
    widget_on(se.chips, EVT_AFTER_PAINT, se_on_chips_paint, (void *)0);
    widget_on(se.chips, EVT_POINTER_DOWN, se_on_chips, (void *)0);
    widget_on(se.chips, EVT_POINTER_MOVE, se_on_chips, (void *)0);
    widget_on(se.chips, EVT_POINTER_UP, se_on_chips, (void *)0);
    widget_on(se.chips, EVT_POINTER_ABORT, se_on_chips, (void *)0);
    widget_on(se.field, EVT_POINTER_UP, se_on_field, (void *)0);
    se_chips_setup();
    se.chip = se.lo;
    se_chip_fx();
    se_show(se.list, 0);
    se_show(se.status, 0);
    se_rec_load();
    se_layout();
    se.wait = 1; /* the library is read once the page has been shown */
    se_kick();
    return 0;
}

/* The unscoped page: every chip, Top Results selected. */
int search_open(void) { return search_open_in(SEARCH_ALL); }
