/* M1+ Music Daily Mix: a card of the day's mix on the Home instance of the menu (docs/modules/dailymix.md), made on the device once a day.
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * No stock function is hooked and nothing runs at boot, in the main loop or in paint but the card's own after-paint. Everything runs from the menu
 * window's and the card's own widgets, their events and one page timer, as the Recently Played shelf (patch/recent.c) and the mini bar do.
 *
 * The card. dailymix_start looks the section up (pod_daily: the header "Made for You", the card pod_dm_card, the glass play disc pod_dm_play, two hidden
 * labels that carry the text styles), reads the Settings > Home Screen switch (DAILY_SET_FILE) and the mix file (MIX_FILE, strictly validated: any
 * deviation is "no mix") and shows the section (menu_daily in patch/menu.c: visible and sensitive together, the list keeps its place) when there is a
 * mix and the switch is on. DM_FIRST_MS later its one-shot reads the art file (MIX_ART_FILE, validated: size, magic, size fields, the art seed of the
 * mix file, the checksum) into a 296 x 220 bitmap; the card's after-paint draws the bitmap and the text (title in two lines, the top artists in up to
 * two), laid out once with the canvas' own font. Tapping the card opens the Daily Mix page (dp_*, below); the disc plays the mix from its first song (the queue, then Now Playing, as the
 * Shuffle page starts a song). The mix is the mix file: no stock table holds it, so the Playlists page never shows it, except the one-off copy the user saves with the page's Add disc (dp_save). Every file written is under
 * /mnt/mmc/.m1plus (the card carries its own mix; nothing is read or written while the card is not mounted) and never ends in .m3u or .m3u8 (the stock Import
 * reads only the card's _explaylist_data).
 *
 * The mix. Once per calendar day, the first time the Home menu is in front DM_START_MS after it opened (never inside the boot guard's window), a job
 * runs on the page timer, one slice per tick (DM_TICK_MS), and the card shows yesterday's mix until it is ready. Stock lists are read through the Songs
 * page's own call, loadLocalClassList: the Most Played, Recently Played and Favourites lists and the library, each hashed into our own tables within
 * slices (the list is checked at every tick: a changed one ends the job); the score and the picks (tools/pod_mix.py is the model the test compares with);
 * the picked records are copied after a second read of the library; the top albums' cover tones come from the tone cache of the album page or one cover
 * decode a tick; the art (the blob field, the scrim that gives the text 4.7:1, the dither) in DM_ROWS rows a tick; then the files: the mix file (the day, seed, tones, names and the songs' paths
 * in play order) and the art file. A job that fails or is cut short by the menu going away frees everything and writes nothing (the files come last); a failed day is not tried again until
 * the next day or a restart. Regenerate Daily Mix (dailymix_regen) asks for a new mix with the next seed, made when the Home menu is next in front.
 */
#include "offsets.inc"
#include "stock.h"
#include "home.h"
#include "covercache.h"
#include "common.h"
#include "i18n.h"
#include "grid.h"
#include "scroll.h"
#include "podcasts.h"
#include "songops.h"

extern void pod_toast(const char *text); /* patch/shuffle.c */
extern unsigned pod_rand(unsigned n); /* patch/shuffle.c */
extern void pod_set_mode(int mode); /* patch/shuffle.c: the stock play mode (patch/songops.c uses it for Shuffle) */
extern void pod_set_in_order(void); /* patch/shuffle.c: Shuffle and Repeat one become List play (Play) */

#define P(r, off) (*(char **)((char *)(r) + (off)))
#define I(r, off) (*(int *)((char *)(r) + (off)))
#define DM_GREY 0xff1c1c1eu
#define DM_TEXT 48 /* wide chars of a title line */
#define DM_STEXT 160 /* wide chars of an artists line */
#define DM_LINES 16 /* most lines a wrap may need before it is given up */
#define DM_DIV255(t) (((t) + 1 + ((t) >> 8)) >> 8)
#define DM_L_MIN 153 /* HLS lightness bounds of a prepared tone in 1/510: 0.30, 0.56 (colourful); 0.25, 0.66 (grey) */
#define DM_L_MAX 286
#define DM_G_MIN 127
#define DM_G_MAX 337
#define DM_A64_MIN 10
#define DM_A64_START_MAX 52
#define DM_A64_MAX 56

/* tools/pod_dailymix.py --c-table (test/pod/dailymix.py compares it): sRGB to linear light, 16 bit */
static const unsigned short dm_lin[256] = {
    0,     20,    40,    60,    80,    99,    119,   139,   159,   179,   199,   219,   241,   264,   288,   313,
    340,   367,   396,   427,   458,   491,   526,   562,   599,   637,   677,   718,   761,   805,   851,   898,
    947,   997,   1048,  1101,  1156,  1212,  1270,  1330,  1391,  1453,  1517,  1583,  1651,  1720,  1790,  1863,
    1937,  2013,  2090,  2170,  2250,  2333,  2418,  2504,  2592,  2681,  2773,  2866,  2961,  3058,  3157,  3258,
    3360,  3464,  3570,  3678,  3788,  3900,  4014,  4129,  4247,  4366,  4488,  4611,  4736,  4864,  4993,  5124,
    5257,  5392,  5530,  5669,  5810,  5953,  6099,  6246,  6395,  6547,  6700,  6856,  7014,  7174,  7335,  7500,
    7666,  7834,  8004,  8177,  8352,  8528,  8708,  8889,  9072,  9258,  9445,  9635,  9828,  10022, 10219, 10417,
    10619, 10822, 11028, 11235, 11446, 11658, 11873, 12090, 12309, 12530, 12754, 12980, 13209, 13440, 13673, 13909,
    14146, 14387, 14629, 14874, 15122, 15371, 15623, 15878, 16135, 16394, 16656, 16920, 17187, 17456, 17727, 18001,
    18277, 18556, 18837, 19121, 19407, 19696, 19987, 20281, 20577, 20876, 21177, 21481, 21787, 22096, 22407, 22721,
    23038, 23357, 23678, 24002, 24329, 24658, 24990, 25325, 25662, 26001, 26344, 26688, 27036, 27386, 27739, 28094,
    28452, 28813, 29176, 29542, 29911, 30282, 30656, 31033, 31412, 31794, 32179, 32567, 32957, 33350, 33745, 34143,
    34544, 34948, 35355, 35764, 36176, 36591, 37008, 37429, 37852, 38278, 38706, 39138, 39572, 40009, 40449, 40891,
    41337, 41785, 42236, 42690, 43147, 43606, 44069, 44534, 45002, 45473, 45947, 46423, 46903, 47385, 47871, 48359,
    48850, 49344, 49841, 50341, 50844, 51349, 51858, 52369, 52884, 53401, 53921, 54445, 54971, 55500, 56032, 56567,
    57105, 57646, 58190, 58737, 59287, 59840, 60396, 60955, 61517, 62082, 62650, 63221, 63795, 64372, 64952, 65535};

/* ---------------------------------------------------------------------------
 * Small helpers (the payload links no libc string functions but those in stock.h)
 */
static unsigned dm_len(const char *s) {
    unsigned n = 0;
    while (s[n]) ++n;
    return n;
}

static int dm_bad(unsigned char c) { return c < 0x20 || c == 0x7f; }

static unsigned dm_xs(unsigned x) {
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    return x;
}

/* FNV-1a with ASCII letters folded to lower case (the identity of an artist or an album; the stock list groups albums by title, NOCASE), never 0. */
static unsigned dm_fold_to(const char *s, const char *end) {
    unsigned h = FNV_SEED;
    for (; *s && s != end; ++s) h = (h ^ (unsigned char)((unsigned char)*s - 'A' < 26u ? *s + 32 : *s)) * 16777619u;
    return h | !h;
}

static unsigned dm_fold(const char *s) { return dm_fold_to(s, (const char *)0); }

/* The identity of a song's artist or album: the tag, or for an untagged song its folder (the path up to the last '/'), so untagged songs are not all one. */
static unsigned dm_tag(const char *tag, const char *path) {
    const char *e = path, *p;
    if (*tag) return dm_fold(tag);
    for (p = path; *p; ++p)
        if (*p == '/') e = p;
    return dm_fold_to(path, e);
}

/* 16 * log2(1 + n): the octave and four bits of the mantissa. */
static unsigned dm_lg(unsigned n) {
    unsigned v = n + 1, e = 31u - (unsigned)__builtin_clz(v);
    return 16 * e + ((v << (31 - e)) >> 27 & 15);
}

static unsigned dm_lum(unsigned r, unsigned g, unsigned b) {
    return (2126u * dm_lin[r] + 7152u * dm_lin[g] + 722u * dm_lin[b]) / 10000u;
}

/* s into out (size bytes with the NUL), control bytes as spaces, cut before a UTF-8 continuation byte that would be split. */
static void dm_copy(char *out, unsigned size, const char *s) {
    unsigned n = dm_len(s), j;
    if (n >= size) {
        n = size - 1;
        while (n && ((unsigned char)s[n] & 0xc0) == 0x80) --n;
    }
    for (j = 0; j < n; ++j) out[j] = dm_bad((unsigned char)s[j]) ? ' ' : s[j];
    out[n] = 0;
}

static int dm_read(const char *path, void *buf, unsigned max) {
    int fd, n;
    if (!pod_card_mounted())
        return -1; /* no card: no mix (an unmounted /mnt/mmc is a directory on the internal flash) */
    fd = open(path, O_RDONLY, 0);
    if (fd < 0) return -1;
    n = read(fd, buf, max);
    close(fd);
    return n;
}

/* The local calendar day as a count of days since 1970-01-01 (0: the clock is not set, any time before 2020). */
static unsigned dm_today(void) {
    long t = time((long *)0);
    const int *tm;
    unsigned y, m, d, era, yoe, doy, doe;
    if (t < 1577836800L) return 0;
    tm = localtime(&t);
    if (!tm) return 0;
    y = (unsigned)(tm[5] + 1900), m = (unsigned)(tm[4] + 1), d = (unsigned)tm[3];
    y -= m <= 2;
    era = y / 400, yoe = y - era * 400;
    doy = (153 * (m > 2 ? m - 3 : m + 9) + 2) / 5 + d - 1;
    doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    return era * 146097 + doe - 719468;
}

/* ---------------------------------------------------------------------------
 * The state. dm is the card on the Home window; the job is the mix being made (heap, only while it runs).
 */
typedef struct {
    int cx, cy;
    unsigned r2;
    int t[3];
} blob_t;
typedef struct {
    unsigned *key;
    unsigned short *val;
    unsigned mask;
} ht_t;
typedef struct {
    int score;
    unsigned path, artist, album;
    unsigned short plays, idx;
    unsigned char rec, fav, ca, cb, used;
} cand_t;
typedef struct {
    unsigned char raw[REC_SIZE];
} pick_t;

static void dm_apply(void);

enum {
    PH_OFT,
    PH_REC,
    PH_FAV,
    PH_LIB,
    PH_SCORE,
    PH_PICK,
    PH_COPY,
    PH_ALBUM,
    PH_FIELD,
    PH_BRIGHT,
    PH_RENDER,
    PH_COMMIT,
    PH_SAVE
};
#define PH_LAST PH_SAVE

typedef struct {
    int phase, manual, art_only, failed;
    unsigned pos, n; /* progress inside the phase; the size of the list being read */
    void *dq; /* the stock list being read in slices (and its guard: size, first and last record) */
    void *first, *last;
    unsigned day, seed, aseed, regen;
    ht_t oft, fav, art;
    unsigned rec[DM_REC_MAX], nrec;
    cand_t *c;
    unsigned nc, nlib;
    unsigned short pick[MIX_SONGS];
    unsigned npick, lvl; /* the picks; the step of the limits (dm_cap_*) */
    pick_t *pk; /* the picked records, copied (strings strdup'ed) */
    char name[DM_MAX_NAMES][DM_NAME];
    unsigned nname;
    unsigned alb[MIX_ALBUMS], nalb; /* the cover keys of the top albums */
    const char *title[MIX_ALBUMS]; /* ... and their titles (inside pk) */
    unsigned tone[4], ntone; /* r | g << 8 | b << 16 */
    unsigned char *fld; /* the blob field, 3 bytes a pixel */
    unsigned short *px; /* the art, RGB565 */
    blob_t bl[4];
    unsigned nbl;
    int base[3];
    unsigned a64, maxlum, limit, row;
    unsigned char bright[3];
    unsigned blum;
} job_t;

static struct {
    void *win, *card, *disc, *sec, *sv, *st_title, *st_sub;
    unsigned timer;
    int fg, on, shown, have, load, laid;
    unsigned t0;
    /* the mix as the file holds it */
    unsigned day, seed, aseed, regen, count;
    unsigned tone[4], ntone;
    char name[DM_MAX_NAMES][DM_NAME];
    unsigned nname;
    char *paths; /* the songs' paths in play order, NUL separated (heap, count of them) */
    void *bmp;
    int down, down_x, down_y;
    unsigned fail_day;
    unsigned char corner[DM_R * DM_R];
    /* the text, laid out for the canvas' font */
    unsigned tl[2][DM_TEXT];
    int tn, tlen[2];
    unsigned sl[DM_SUB_LINES][DM_STEXT];
    int sn, slen[DM_SUB_LINES];
    job_t *job;
} dm __attribute__((section(".scratch")));

static int dm_regen_req
    __attribute__((section(".scratch"))); /* Regenerate Daily Mix was asked (survives the Home window) */
static int dm_small __attribute__((section(
    ".scratch"))); /* the last job found fewer than MIX_MIN_LIB songs: Regenerate is off until a job finds enough */

/* ---------------------------------------------------------------------------
 * The setting: the file holds "0" for off, anything else or no file is on.
 */
int dailymix_setting(void) { return set_read(DAILY_SET_FILE, '1') != '0'; }

int dailymix_toggle(void) {
    int next = !dailymix_setting();
    return home_write_atomic(DAILY_SET_FILE, DAILY_SET_TMP, next ? "1\n" : "0\n") == 0 ? next : -1;
}

/* Regenerate Daily Mix can make a mix: the switch is on and the library was not too small (Settings dims the row otherwise). A day's first job reads the
 * library again, so songs added since are seen the next day or after a restart. */
int dailymix_can_regen(void) { return dailymix_setting() && !dm_small; }

void dailymix_regen(void) {
    if (!dailymix_can_regen()) return;
    if (dm_regen_req < 255) ++dm_regen_req;
    pod_toast(TR("New mix when Home opens")); /* a short form of the page's note */
}

/* ---------------------------------------------------------------------------
 * The mix file (tools/pod_mix.py parse_mix / dump_mix are the model)
 */
static int dm_hexv(unsigned c) {
    if (c - '0' < 10) return (int)(c - '0');
    if (c - 'a' < 6) return (int)(c - 'a' + 10);
    return -1;
}

/* n lowercase hex digits at p into *out; 0 when one is not */
static int dm_hex(const char *p, unsigned n, unsigned *out) {
    unsigned v = 0, k;
    for (k = 0; k < n; ++k) {
        int d = dm_hexv((unsigned char)p[k]);
        if (d < 0) return 0;
        v = v << 4 | (unsigned)d;
    }
    *out = v;
    return 1;
}

/* A decimal number of 1 to 9 digits (no leading zero but 0 itself) ending at the byte `end`; *pp after it; -1 when it is not. */
static long dm_dec(const char **pp, const char *stop, char end) {
    const char *p = *pp;
    unsigned n = 0, v = 0;
    while (p < stop && *p - '0' >= 0 && *p - '0' <= 9 && n < 10) v = v * 10 + (unsigned)(*p++ - '0'), ++n;
    if (n == 0 || n > 9 || (n > 1 && **pp == '0') || p >= stop || *p != end) return -1;
    *pp = p + 1;
    return (long)v;
}

/* MIX_FILE into dm.*; 1 when it is a valid mix. dm is left untouched by a bad file. */
static int dm_load(void) {
    char buf[DM_FILE_MAX + 1];
    const char *p = buf, *stop;
    int n = dm_read(MIX_FILE, buf, sizeof buf), k;
    long day, regen, count;
    unsigned seed, aseed, v, tone[4], nt = 0, nn = 0, i, len;
    char name[DM_MAX_NAMES][DM_NAME], *paths;
    const char *ps;
    if (n < 6 || n > DM_FILE_MAX) return 0;
    stop = buf + n;
    for (k = 0; k < 5; ++k)
        if (buf[k] != "M1X2\n"[k]) return 0;
    if (stop[-1] != '\n') return 0;
    p += 5;
    day = dm_dec(&p, stop, '\t');
    if (day < 1 || stop - p < 20 || !dm_hex(p, 8, &seed) || !seed || p[8] != '\t') return 0;
    p += 9;
    if (!dm_hex(p, 8, &aseed) || p[8] != '\t') return 0;
    p += 9;
    regen = dm_dec(&p, stop, '\t');
    count = dm_dec(&p, stop, '\n');
    if (regen < 0 || regen > 255 || count < MIX_MIN_SONGS || count > MIX_SONGS) return 0;
    for (;;) { /* 2..4 tones of six hex digits, a space between, a newline after */
        if (nt == 4 || stop - p < 7 || !dm_hex(p, 6, &v)) return 0;
        tone[nt++] = v >> 16 | (v & 0xff00) | (v & 0xff) << 16; /* rrggbb to r | g << 8 | b << 16 */
        p += 6;
        if (*p == '\n') {
            ++p;
            break;
        }
        if (*p != ' ') return 0;
        ++p;
    }
    if (nt < 2) return 0;
    for (;;) { /* 1..3 names, a tab between, a newline after (the last byte of the file) */
        unsigned len = 0;
        if (nn == DM_MAX_NAMES) return 0;
        while (p < stop && *p != '\t' && *p != '\n') {
            if (dm_bad((unsigned char)*p) || len + 1 >= DM_NAME) return 0;
            name[nn][len++] = *p++;
        }
        if (!len || p >= stop) return 0;
        name[nn++][len] = 0;
        if (*p++ == '\n') break;
    }
    ps = p;
    for (
        i = 0; i < (unsigned)count;
        ++i) { /* the songs' paths in play order, one a line (1 .. DM_PATH - 1 bytes, no control byte), the last line ends the file */
        for (len = 0; p < stop && *p != '\n'; ++p, ++len)
            if (dm_bad((unsigned char)*p) || len + 1 >= DM_PATH) return 0;
        if (!len || p >= stop) return 0;
        ++p;
    }
    if (p != stop) return 0;
    paths = calloc(1, (unsigned)(stop - ps));
    if (!paths) return 0;
    for (len = 0; ps + len < stop; ++len) paths[len] = ps[len] == '\n' ? 0 : ps[len];
    free(dm.paths);
    dm.paths = paths;
    dm.day = (unsigned)day, dm.seed = seed, dm.aseed = aseed, dm.regen = (unsigned)regen, dm.count = (unsigned)count;
    for (k = 0; k < 4; ++k) dm.tone[k] = (unsigned)k < nt ? tone[k] : 0;
    dm.ntone = nt;
    memcpy(dm.name, name, sizeof name);
    dm.nname = nn;
    return 1;
}

static void dm_put(char **o, const char *end, const char *s) {
    while (*s && *o < end) *(*o)++ = *s++;
}

static void dm_putdec(char **o, const char *end, unsigned v) {
    char t[12];
    unsigned n = 0;
    do t[n++] = (char)('0' + v % 10), v /= 10;
    while (v);
    while (n && *o < end) *(*o)++ = t[--n];
}

static void dm_puthex(char **o, const char *end, unsigned v, unsigned digits) {
    while (digits && *o < end) *(*o)++ = "0123456789abcdef"[v >> (4 * --digits) & 15];
}

/* ---------------------------------------------------------------------------
 * The art (tools/pod_dailymix.py is the model, integers only; test/pod/dailymix.py compares the pixels)
 */

/* A cover's tone made card-ready: a colourful tone (saturation above 0.10) gets at least 0.55 and a lightness in [0.30, 0.56], a grey one a lightness
 * in [0.25, 0.66] and its saturation. l2 is lightness x 2 x 255 (0..510); the channels keep their place between min and max, so the hue stays. */
static void dm_prep(unsigned tone, int *out) {
    int c[3], mx, mn, d, l2, den, colourful, l2n, denn, dn, mnn, i;
    c[0] = (int)(tone & 255), c[1] = (int)(tone >> 8 & 255), c[2] = (int)(tone >> 16 & 255);
    mx = c[0] > c[1] ? c[0] : c[1];
    if (c[2] > mx) mx = c[2];
    mn = c[0] < c[1] ? c[0] : c[1];
    if (c[2] < mn) mn = c[2];
    d = mx - mn, l2 = mx + mn;
    den = l2 < 510 - l2 ? l2 : 510 - l2;
    colourful = d * 10 > den;
    l2n = l2;
    if (l2n < (colourful ? DM_L_MIN : DM_G_MIN)) l2n = colourful ? DM_L_MIN : DM_G_MIN;
    if (l2n > (colourful ? DM_L_MAX : DM_G_MAX)) l2n = colourful ? DM_L_MAX : DM_G_MAX;
    if (d == 0) {
        out[0] = out[1] = out[2] = l2n / 2;
        return;
    }
    denn = l2n < 510 - l2n ? l2n : 510 - l2n;
    dn = d * denn / den;
    if (colourful && dn < 55 * denn / 100) dn = 55 * denn / 100;
    mnn = (l2n - dn) / 2;
    for (i = 0; i < 3; ++i) out[i] = mnn + ((c[i] - mn) * dn * 2 + d) / (2 * d);
}

/* The blobs and the base of tones[0..n) for the seed on a w x h field (pod_dailymix.blobs / field): the card's (DM_W x DM_H) and the page's (DP_W x DP_ART_H). */
static void dm_blobs_wh(const unsigned *tone, unsigned n, unsigned aseed, unsigned w, unsigned h, int *base,
                        blob_t *bl) {
    int prep[4][3], i, dark = 0;
    unsigned st = aseed ? aseed : 0x9E3779B9u, k;
    for (k = 0; k < n; ++k) dm_prep(tone[k], prep[k]);
    for (k = 1; k < n; ++k)
        if (dm_lum((unsigned)prep[k][0], (unsigned)prep[k][1], (unsigned)prep[k][2]) <
            dm_lum((unsigned)prep[dark][0], (unsigned)prep[dark][1], (unsigned)prep[dark][2]))
            dark = (int)k;
    for (i = 0; i < 3; ++i) base[i] = prep[dark][i] * 5 / 10;
    for (k = 0; k < n; ++k) {
        unsigned a, b, c, R;
        st = dm_xs(st), a = st;
        st = dm_xs(st), b = st;
        st = dm_xs(st), c = st;
        R = w * 62 / 100 + (c & 0xffff) * (w * 30 / 100) / 0x10000;
        bl[k].cx = (int)((2 * k + 1) * w / (2 * n)) + (((int)(a & 0xffff) - 0x8000) * (int)(w / n) >> 17);
        bl[k].cy = (int)(h * 12 / 100 + (b & 0xffff) * (h * 50 / 100) / 0x10000);
        bl[k].r2 = R * R;
        for (i = 0; i < 3; ++i) bl[k].t[i] = prep[k][i];
    }
}

static void dm_blobs(job_t *j) {
    dm_blobs_wh(j->tone, j->ntone, j->aseed, DM_W, DM_H, j->base, j->bl);
    j->nbl = j->ntone;
}

/* Row y of the field, w pixels of 3 bytes into o. */
static void dm_field_wh(unsigned char *o, unsigned y, unsigned w, const int *base, const blob_t *bls, unsigned nbl) {
    unsigned x, k;
    for (x = 0; x < w; ++x, o += 3) {
        int r = base[0], g = base[1], b = base[2];
        for (k = 0; k < nbl; ++k) {
            const blob_t *bl = &bls[k];
            int dx = (int)x - bl->cx, dy = (int)y - bl->cy;
            unsigned d2 = (unsigned)(dx * dx + dy * dy), q, a;
            if (d2 >= bl->r2) continue;
            q = 256 - 256 * d2 / bl->r2;
            a = 240 * (q * q >> 8) >> 8;
            r += (bl->t[0] - r) * (int)a >> 8;
            g += (bl->t[1] - g) * (int)a >> 8;
            b += (bl->t[2] - b) * (int)a >> 8;
        }
        o[0] = (unsigned char)r, o[1] = (unsigned char)g, o[2] = (unsigned char)b;
    }
}

static void dm_field_row(job_t *j, unsigned y) { dm_field_wh(j->fld + y * DM_W * 3, y, DM_W, j->base, j->bl, j->nbl); }

/* The scrim's alpha (0..256) on row y: 0 DM_RAMP rows above the text zone, a smoothstep up to a64 / 64 at its top and below. */
static unsigned dm_scrim(unsigned y, unsigned a64) {
    unsigned t = (y + DM_RAMP - DM_ZONE_Y) * 256 / DM_RAMP, s;
    if (t > 256) t = 256;
    s = t * t * (768 - 2 * t) >> 16;
    return s * a64 / 64;
}

static const unsigned char dm_bayer[4][4] = {{0, 8, 2, 10}, {12, 4, 14, 6}, {3, 11, 1, 9}, {15, 7, 13, 5}};

/* One channel through the scrim, the 4 x 4 dither and 5 or 6 bits; the expanded 8 bit value in *e. Returns the quantised value. */
static unsigned dm_quant(int c, unsigned t, int step, unsigned bits, unsigned *e) {
    int v = c + (((int)t * step - 15 * step / 2) >> 4);
    unsigned q;
    if (v < 0) v = 0;
    if (v > 255) v = 255;
    q = (unsigned)v >> (8 - bits);
    *e = q << (8 - bits) | q >> (2 * bits - 8);
    return q;
}

/* Row y of the art for the scrim strength a64: the RGB565 words into px, and the brightest luminance of the row. */
static unsigned dm_render_row(job_t *j, unsigned y, unsigned a64) {
    const unsigned char *f = j->fld + y * DM_W * 3;
    unsigned short *o = j->px + y * DM_W;
    unsigned a = dm_scrim(y, a64), x, mx = 0;
    for (x = 0; x < DM_W; ++x, f += 3) {
        unsigned t = dm_bayer[y & 3][x & 3], er, eg, eb, qr, qg, qb, l;
        int r = f[0] - (int)((unsigned)f[0] * a >> 8), g = f[1] - (int)((unsigned)f[1] * a >> 8),
            b = f[2] - (int)((unsigned)f[2] * a >> 8);
        qr = dm_quant(r, t, 8, 5, &er);
        qg = dm_quant(g, t, 4, 6, &eg);
        qb = dm_quant(b, t, 8, 5, &eb);
        o[x] = (unsigned short)(qr << 11 | qg << 5 | qb);
        l = dm_lum(er, eg, eb);
        if (l > mx) mx = l;
    }
    return mx;
}

/* The bitmap of the card from RGB565 words (expanded to 8 bit), the four corners blended into black (patch/grid.c grid_round). */
static void dm_fill_bitmap(const unsigned short *px) {
    unsigned *d;
    unsigned i, k, x, y;
    if (!dm.bmp) return;
    d = (unsigned *)bitmap_lock_buffer_for_write(dm.bmp);
    if (!d) return;
    for (i = 0; i < DM_W * DM_H; ++i) {
        unsigned v = px[i], r = v >> 11 & 31, g = v >> 5 & 63, b = v & 31;
        d[i] = 0xff000000u | (r << 3 | r >> 2) | (g << 2 | g >> 4) << 8 | (b << 3 | b >> 2) << 16;
    }
    for (k = 0; k < 4; ++k)
        for (y = 0; y < DM_R; ++y)
            for (x = 0; x < DM_R; ++x) {
                unsigned *p = d + (k & 2 ? DM_H - 1 - y : y) * DM_W + (k & 1 ? DM_W - 1 - x : x),
                         a = 255u - dm.corner[y * DM_R + x];
                if (a == 255) continue;
                *p = 0xff000000u | DM_DIV255((*p & 255) * a) | DM_DIV255((*p >> 8 & 255) * a) << 8 |
                     DM_DIV255((*p >> 16 & 255) * a) << 16;
            }
    bitmap_unlock_buffer(dm.bmp);
}

/* ---------------------------------------------------------------------------
 * Tables (open addressing, 16 bit values; a key is never 0)
 */
static int ht_init(ht_t *t, unsigned n) {
    unsigned s = 16;
    while (s < 2 * n) s <<= 1;
    t->key = calloc(s, sizeof(unsigned));
    t->val = calloc(s, sizeof(unsigned short));
    t->mask = s - 1;
    return t->key && t->val;
}

static void ht_free(ht_t *t) {
    free(t->key);
    free(t->val);
    memset(t, 0, sizeof *t);
}

static unsigned short *ht_slot(const ht_t *t, unsigned k, int add) {
    unsigned i, n;
    if (!t->key) return (unsigned short *)0;
    k |= !k;
    i = (k ^ k >> 15) & t->mask;
    for (n = 0; n <= t->mask; ++n, i = (i + 1) & t->mask) {
        if (t->key[i] == k) return &t->val[i];
        if (!t->key[i]) {
            if (!add) return (unsigned short *)0;
            t->key[i] = k;
            return &t->val[i];
        }
    }
    return (unsigned short *)0;
}

static void ht_add(ht_t *t, unsigned k, unsigned v) {
    unsigned short *s = ht_slot(t, k, 1);
    if (s) *s = (unsigned short)(*s + v > 65535u ? 65535u : *s + v);
}

/* ---------------------------------------------------------------------------
 * The job
 */
/* A library record copied with its eight strings (the record's own pointers are the stock list's), and freed again. */
static const unsigned char dm_strs[8] = {0x08, 0x0c, 0x10, 0x14, 0x18, 0x1c, 0x20, 0x24};

static void dm_rec_copy(pick_t *dst, const void *r) {
    unsigned k;
    memcpy(dst->raw, r, REC_SIZE);
    for (k = 0; k < 8; ++k) {
        const char *s = P(r, dm_strs[k]);
        *(char **)(dst->raw + dm_strs[k]) = s ? strdup(s) : (char *)0;
    }
}

static void dm_rec_free(pick_t *p) {
    unsigned k;
    for (k = 0; k < 8; ++k) free(*(char **)(p->raw + dm_strs[k]));
}

static void dm_free_picks(job_t *j) {
    unsigned i;
    if (!j->pk) return;
    for (i = 0; i < j->npick; ++i) dm_rec_free(&j->pk[i]);
    free(j->pk);
    j->pk = (pick_t *)0;
}

static void dm_job_free(job_t *j) {
    if (!j) return;
    ht_free(&j->oft);
    ht_free(&j->fav);
    ht_free(&j->art);
    free(j->c);
    free(j->fld);
    free(j->px);
    dm_free_picks(j);
    free(j);
}

static void dm_job_end(int failed) {
    job_t *j = dm.job;
    if (!j) return;
    dm.job = (job_t *)0;
    if (failed) dm.fail_day = j->day;
    dm_job_free(j);
}

/* A covered or closed Home drops its lists, but still owes an interrupted manual mix.
 * Today's committed mix cannot trigger the automatic retry. Keep any newer ask too. */
static void dm_job_cancel(void) {
    job_t *j = dm.job;
    if (!j) return;
    if (j->manual && !dm_regen_req) dm_regen_req = 1;
    dm.job = (job_t *)0;
    dm_job_free(j);
}

static job_t *dm_job_new(void) {
    job_t *j = calloc(1, sizeof(job_t));
    return j;
}

/* The stock list of a class, or NULL when it is empty. Every read replaces *pdeq_showlist (the Songs page's own call). */
static void *dm_list(unsigned cls) { return loadLocalClassList((int)cls) > 0 ? *(void **)PDEQ_SHOWLIST : (void *)0; }

/* The job keeps a list across ticks: a different one, or one of another size, ends the job. */
static int dm_guard(job_t *j) {
    void *dq = *(void **)PDEQ_SHOWLIST;
    unsigned n = dq ? deque_size(dq) : 0;
    if (!j->dq || dq != j->dq || n != j->n || (n && (deque_at(dq, 0) != j->first || deque_at(dq, n - 1) != j->last)))
        return 0;
    return 1;
}

static int dm_open_list(job_t *j, unsigned cls, unsigned max) {
    void *dq = dm_list(cls);
    unsigned n = dq ? deque_size(dq) : 0;
    j->dq = dq, j->pos = 0;
    j->n = n;
    if (!n) return 0;
    j->first = deque_at(dq, 0), j->last = deque_at(dq, n - 1);
    (void)max;
    return 1;
}

/* Records [pos, pos + DM_SLICE) of the open list within `lim` records: the first and one past the last. */
static unsigned dm_slice(job_t *j, unsigned lim, unsigned *to) {
    unsigned from = j->pos, end = from + DM_SLICE;
    if (end > lim) end = lim;
    *to = end;
    j->pos = end;
    return from;
}

static unsigned dm_path_hash(const char *p) { return cc_fnv(FNV_SEED, p); }

/* A path the mix file can hold: 1 .. DM_PATH - 1 bytes, no control byte (the file is one path a line). */
static int dm_path_ok(const char *p) {
    unsigned n = 0;
    for (; p[n]; ++n)
        if (dm_bad((unsigned char)p[n])) return 0;
    return n > 0 && n < DM_PATH;
}

static int dm_eq(const unsigned char *a, const char *b, unsigned n) {
    while (n--)
        if (*a++ != (unsigned char)*b++) return 0;
    return 1;
}

/* ---- phases */
static int dm_ph_oft(job_t *j) {
    unsigned from, to, k, lim;
    if (!j->dq) {
        if (!dm_open_list(j, CLASS_OFTEN, DM_OFT_MAX)) {
            j->phase = PH_REC;
            return 1;
        } /* nothing was ever played: no plays */
        lim = j->n < DM_OFT_MAX ? j->n : DM_OFT_MAX;
        if (!ht_init(&j->oft, lim)) return 0;
        return 1;
    }
    if (!dm_guard(j)) return 0;
    lim = j->n < DM_OFT_MAX ? j->n : DM_OFT_MAX;
    from = dm_slice(j, lim, &to);
    for (k = from; k < to; ++k) {
        void *r = deque_at(j->dq, k);
        const char *path = cc_str(r, REC_PATH);
        int plays = I(r, REC_TRACK) + 1;
        if (*path) ht_add(&j->oft, dm_path_hash(path), plays < 1 ? 1u : (unsigned)plays);
    }
    if (j->pos >= lim) j->dq = (void *)0, j->phase = PH_REC;
    return 1;
}

static int dm_ph_rec(job_t *j) {
    unsigned k;
    if (!dm_open_list(j, CLASS_RECENT, DM_REC_MAX)) {
        j->dq = (void *)0, j->phase = PH_FAV;
        return 1;
    }
    for (k = 0; k < j->n && k < DM_REC_MAX; ++k) j->rec[j->nrec++] = dm_path_hash(cc_str(deque_at(j->dq, k), REC_PATH));
    j->dq = (void *)0, j->phase = PH_FAV;
    return 1;
}

static int dm_ph_fav(job_t *j) {
    unsigned from, to, k, lim;
    if (!j->dq) {
        if (!dm_open_list(j, CLASS_FAV, DM_FAV_MAX)) {
            j->phase = PH_LIB;
            return 1;
        }
        lim = j->n < DM_FAV_MAX ? j->n : DM_FAV_MAX;
        return ht_init(&j->fav, lim);
    }
    if (!dm_guard(j)) return 0;
    lim = j->n < DM_FAV_MAX ? j->n : DM_FAV_MAX;
    from = dm_slice(j, lim, &to);
    for (k = from; k < to; ++k) {
        const char *path = cc_str(deque_at(j->dq, k), REC_PATH);
        if (*path) ht_add(&j->fav, dm_path_hash(path), 1);
    }
    if (j->pos >= lim) j->dq = (void *)0, j->phase = PH_LIB;
    return 1;
}

static int dm_ph_lib(job_t *j) {
    unsigned from, to, k, lim, i;
    if (!j->dq) {
        if (!dm_open_list(j, CLASS_ALL_SONGS, DM_LIB_MAX)) { /* an empty library: no mix */
            dm_small = 1;
            return 0;
        }
        j->nlib = j->n;
        lim = j->n < DM_LIB_MAX ? j->n : DM_LIB_MAX;
        j->c = calloc(lim, sizeof(cand_t));
        return j->c && ht_init(&j->art, lim);
    }
    if (!dm_guard(j)) return 0;
    lim = j->n < DM_LIB_MAX ? j->n : DM_LIB_MAX;
    from = dm_slice(j, lim, &to);
    for (k = from; k < to; ++k) {
        void *r = deque_at(j->dq, k);
        const char *path = cc_str(r, REC_PATH);
        cand_t *c;
        unsigned short *s;
        if (I(r, REC_TYPE) != 8 || !*path || pc_is_path(path))
            continue; /* (a podcast episode is no candidate for the mix) */
        c = &j->c[j->nc++];
        c->path = dm_path_hash(path);
        c->artist = dm_tag(cc_str(r, REC_ARTIST), path);
        c->album = dm_tag(cc_str(r, REC_ALBUM), path);
        c->idx = (unsigned short)k;
        s = ht_slot(&j->oft, c->path, 0);
        c->plays = s ? *s : 0;
        for (i = 0; i < j->nrec; ++i)
            if (j->rec[i] == c->path) {
                c->rec = (unsigned char)(i + 1);
                break;
            }
        c->fav = ht_slot(&j->fav, c->path, 0) != (unsigned short *)0;
        ht_add(&j->art, c->artist, c->plays);
    }
    if (j->pos >= lim) {
        dm_small = j->nc < MIX_MIN_LIB;
        if (dm_small) return 0; /* too few songs for a mix worth a card */
        j->dq = (void *)0, j->pos = 0, j->phase = PH_SCORE;
        ht_free(&j->oft);
        ht_free(&j->fav);
    }
    return 1;
}

static int dm_score(const cand_t *c, unsigned atot, unsigned seed) {
    unsigned p = c->plays;
    int v = (int)(MIX_W_PLAYS * dm_lg(p < MIX_PLAYS_CAP ? p : MIX_PLAYS_CAP) +
                  MIX_W_ARTIST * dm_lg(atot < MIX_ARTIST_CAP ? atot : MIX_ARTIST_CAP));
    if (!p)
        v += MIX_NOVEL0;
    else if (p == 1)
        v += MIX_NOVEL1;
    if (c->fav) v += MIX_W_FAV;
    if (c->rec) v -= MIX_W_RECENT * (100 - (c->rec - 1)) / 100;
    return v + (int)(dm_xs(dm_xs((c->path ^ seed) | 1)) & (MIX_JITTER - 1));
}

static int dm_ph_score(job_t *j) {
    unsigned end = j->pos + DM_SLICE * 2, k;
    if (end > j->nc) end = j->nc;
    for (k = j->pos; k < end; ++k) {
        unsigned short *s = ht_slot(&j->art, j->c[k].artist, 0);
        j->c[k].score = dm_score(&j->c[k], s ? *s : 0, j->seed);
    }
    j->pos = end;
    if (end >= j->nc) {
        ht_free(&j->art);
        j->pos = 0, j->phase = PH_PICK;
    }
    return 1;
}

/* The per-artist and per-album limits, loosened a step each time the mix would stay short (the last step is no limit: ca, cb stay below MIX_SONGS). */
static const unsigned char dm_cap_artist[3] = {MIX_PER_ARTIST, MIX_PER_ARTIST2, 255},
                           dm_cap_album[3] = {MIX_PER_ALBUM, MIX_PER_ALBUM2, 255};

/* The best candidate that is not taken and keeps the limits of step j->lvl (the first of equal scores), or -1. */
static int dm_best(job_t *j) {
    int best = -1;
    unsigned i, ca = dm_cap_artist[j->lvl], cb = dm_cap_album[j->lvl];
    for (i = 0; i < j->nc; ++i) {
        const cand_t *c = &j->c[i];
        if (c->used || c->ca >= ca || c->cb >= cb) continue;
        if (best < 0 || c->score > j->c[best].score) best = (int)i;
    }
    return best;
}

static int dm_same_artist(const job_t *j, unsigned a, unsigned b) {
    return j->c[j->pick[a]].artist == j->c[j->pick[b]].artist;
}

static int dm_adj_bad(const job_t *j, unsigned t) { return t > 0 && t < j->npick && dm_same_artist(j, t, t - 1); }

/* One pick a tick; when the mix is full or no song is left: the seeded shuffle and the pass that parts neighbours of one artist. */
static int dm_ph_pick(job_t *j) {
    int b = -1;
    unsigned i, k, r;
    while (j->npick < MIX_SONGS && (b = dm_best(j)) < 0 && j->lvl < 2) ++j->lvl;
    if (b >= 0) {
        unsigned a = j->c[b].artist, al = j->c[b].album;
        j->c[b].used = 1;
        j->pick[j->npick++] = (unsigned short)b;
        for (i = 0; i < j->nc; ++i) {
            if (j->c[i].artist == a) ++j->c[i].ca;
            if (j->c[i].album == al) ++j->c[i].cb;
        }
        return 1;
    }
    if (j->npick < MIX_MIN_SONGS) return 0;
    k = j->npick;
    r = dm_xs(j->seed | 1);
    for (i = k - 1; i > 0; --i) {
        unsigned jx, t;
        r = dm_xs(r);
        jx = r % (i + 1);
        t = j->pick[i], j->pick[i] = j->pick[jx], j->pick[jx] = (unsigned short)t;
    }
    for (i = 1; i < k; ++i) {
        unsigned jx;
        if (!dm_adj_bad(j, i)) continue;
        for (jx = i + 1; jx < k; ++jx) {
            unsigned short t = j->pick[i];
            j->pick[i] = j->pick[jx], j->pick[jx] = t;
            if (!dm_adj_bad(j, i) && !dm_adj_bad(j, i + 1) && !dm_adj_bad(j, jx) && !dm_adj_bad(j, jx + 1)) break;
            t = j->pick[i];
            j->pick[i] = j->pick[jx], j->pick[jx] = t;
        }
    }
    j->phase = PH_COPY;
    return 1;
}

/* The picked records, copied out of a second read of the library (the first list is gone): the strings strdup'ed so they outlive the list. A song whose file
 * is not on the card is left out; fewer than MIX_MIN_SONGS left: no mix. Then the names of the top artists and the titles of the top albums. */
static void dm_ranked(const job_t *j, int artist, unsigned n, unsigned *first) {
    /* the indices into pk of the n most frequent artists (artist = 1) or albums (0), the most songs first, ties by first appearance */
    unsigned cnt[MIX_SONGS], key[MIX_SONGS], at[MIX_SONGS], m = 0, i, k, t;
    for (i = 0; i < j->npick; ++i) {
        const char *s = cc_str(j->pk[i].raw, artist ? REC_ARTIST : REC_ALBUM);
        unsigned h = dm_fold(s);
        for (k = 0; k < m && key[k] != h; ++k) {
        }
        if (k == m) key[m] = h, cnt[m] = 0, at[m] = i, ++m;
        ++cnt[k];
    }
    for (i = 1; i < m; ++i) { /* insertion sort by count, stable */
        unsigned kc = cnt[i], kk = key[i], ka = at[i];
        for (k = i; k > 0 && cnt[k - 1] < kc; --k) cnt[k] = cnt[k - 1], key[k] = key[k - 1], at[k] = at[k - 1];
        cnt[k] = kc, key[k] = kk, at[k] = ka;
    }
    for (t = 0; t < n && t < m; ++t) first[t] = at[t];
    for (; t < n; ++t) first[t] = ~0u;
}

static int dm_ph_copy(job_t *j) {
    void *dq = dm_list(CLASS_ALL_SONGS);
    unsigned i, kept = 0, top[MIX_SONGS];
    pick_t *pk;
    if (!dq || deque_size(dq) != j->nlib) return 0;
    pk = calloc(j->npick, sizeof(pick_t));
    if (!pk) return 0;
    j->pk = pk;
    for (i = 0; i < j->npick; ++i) {
        const cand_t *c = &j->c[j->pick[i]];
        void *r = deque_at(dq, c->idx);
        const char *path = r ? cc_str(r, REC_PATH) : "";
        if (!r || dm_path_hash(path) != c->path) return 0; /* the library changed under the job */
        if (!dm_path_ok(path) || access(path, F_OK))
            continue; /* (the mix file holds the path: one the file cannot hold is as good as missing) */
        dm_rec_copy(&pk[kept], r);
        ++kept;
    }
    j->npick = kept; /* (dm_free_picks frees the strings of the kept ones) */
    if (kept < MIX_MIN_SONGS) return 0;
    j->aseed = (j->seed ^ dm_path_hash(cc_str(pk[0].raw, REC_PATH)));
    dm_ranked(j, 1, DM_MAX_NAMES, top);
    for (i = 0; i < DM_MAX_NAMES; ++i) {
        if (top[i] == ~0u) break;
        dm_copy(j->name[j->nname], DM_NAME, cc_str(pk[top[i]].raw, REC_ARTIST));
        if (j->name[j->nname][0]) ++j->nname;
    }
    if (!j->nname) { /* untagged: the library's own word for it, so the card has a line */
        dm_copy(j->name[0], DM_NAME, TR("Daily Mix"));
        j->nname = 1;
    }
    dm_ranked(j, 0, MIX_ALBUMS, top);
    for (i = 0; i < MIX_ALBUMS && top[i] != ~0u; ++i) j->title[j->nalb++] = cc_str(pk[top[i]].raw, REC_ALBUM);
    free(j->c), j->c = (cand_t *)0;
    j->pos = 0, j->phase = PH_ALBUM;
    return 1;
}

/* The tones of the top albums' covers: the cover keys from the stock album list once, then a tone a tick (the tone cache of the album page, else one decode of the
 * cover in the Cover Flow cache). Fewer than two tones are completed from a fixed palette. */
static const unsigned dm_palette[4] = {70 | 110 << 8 | 190u << 16, 190 | 90 << 8 | 120u << 16,
                                       60 | 140 << 8 | 150u << 16, 150 | 120 << 8 | 70u << 16};

static int dm_ph_album(job_t *j) {
    unsigned i, k;
    if (j->pos == 0) { /* the cover keys */
        void *albums = j->nalb ? cc_albums() : (void *)0;
        unsigned n = albums ? deque_size(albums) : 0;
        for (i = 0; i < j->nalb; ++i) {
            j->alb[i] = 0;
            for (k = 0; *j->title[i] && k < n; ++k) {
                void *r = deque_at(albums, k);
                if (I(r, REC_ID) != -1 && !cc_nocase(cc_str(r, REC_ALBUM), j->title[i])) {
                    j->alb[i] = cc_album_key(r);
                    break;
                }
            }
        }
        if (albums) deque_destroy(albums);
        j->pos = 1;
        return 1;
    }
    i = j->pos - 1;
    if (i < j->nalb) {
        unsigned tone;
        char url[80];
        unsigned px;
        const char *file;
        j->pos++;
        if (!j->alb[i]) return 1;
        if (pod_tone_get(j->alb[i], &tone))
            j->tone[j->ntone++] = tone & 0xffffff;
        else if (dm.win && (file = cc_url(url, j->alb[i])) != (const char *)0 &&
                 cc_decode(dm.win, file, 1, 1, 1, &px)) {
            tone = pod_tone(px & 255, px >> 8 & 255, px >> 16 & 255);
            pod_tone_put(j->alb[i], tone);
            j->tone[j->ntone++] = tone & 0xffffff;
        }
        return 1;
    }
    if (j->ntone < 2) { /* no covers (or one): the fixed palette completes the tones to three, starting at seed % 4 */
        k = 3 - j->ntone;
        for (i = 0; i < k; ++i) j->tone[j->ntone + i] = dm_palette[(j->seed % 4 + i) % 4];
        j->ntone = 3;
    }
    j->pos = 0, j->phase = PH_FIELD;
    return 1;
}

/* The art: the blob field DM_ROWS rows a tick, the brightest pixel of the text zone, then the render (scrim, dither, RGB565) in passes until the zone is dark
 * enough for the dimmer ink (#EBEBEB) to reach 4.7:1 (pod_dailymix.art). */
static int dm_ph_field(job_t *j) {
    unsigned end, y;
    if (j->pos == 0) {
        j->fld = calloc(DM_W * DM_H, 3);
        j->px = calloc(DM_W * DM_H, sizeof(unsigned short));
        if (!j->fld || !j->px) return 0;
        dm_blobs(j);
    }
    end = j->pos + DM_ROWS;
    if (end > DM_H) end = DM_H;
    for (y = j->pos; y < end; ++y) dm_field_row(j, y);
    j->pos = end;
    if (end >= DM_H) j->pos = DM_ZONE_Y, j->blum = 0, j->phase = PH_BRIGHT;
    return 1;
}

static int dm_ph_bright(job_t *j) {
    unsigned end = j->pos + DM_ROWS, y, x, s;
    int limit;
    if (end > DM_H) end = DM_H;
    for (y = j->pos; y < end; ++y) {
        const unsigned char *f = j->fld + y * DM_W * 3;
        for (x = 0; x < DM_W; ++x, f += 3) {
            unsigned l = dm_lum(f[0], f[1], f[2]);
            if (l > j->blum) j->blum = l, j->bright[0] = f[0], j->bright[1] = f[1], j->bright[2] = f[2];
        }
    }
    j->pos = end;
    if (end < DM_H) return 1;
    limit = (int)((dm_lum(0xeb, 0xeb, 0xeb) + 3277) * 10 / 47) -
            3277; /* the brightest background luminance under #EBEBEB at 4.7:1 */
    j->limit = (unsigned)limit;
    for (j->a64 = DM_A64_MIN; j->a64 < DM_A64_START_MAX; ++j->a64) {
        s = 256 * j->a64 / 64;
        if ((int)dm_lum(j->bright[0] - (j->bright[0] * s >> 8), j->bright[1] - (j->bright[1] * s >> 8),
                        j->bright[2] - (j->bright[2] * s >> 8)) <= limit)
            break;
    }
    j->pos = 0, j->maxlum = 0, j->phase = PH_RENDER;
    return 1;
}

static int dm_ph_render(job_t *j) {
    unsigned end = j->pos + DM_ROWS, y;
    if (end > DM_H) end = DM_H;
    for (y = j->pos; y < end; ++y) {
        unsigned m = dm_render_row(j, y, j->a64);
        if (y >= DM_ZONE_Y && m > j->maxlum) j->maxlum = m;
    }
    j->pos = end;
    if (end < DM_H) return 1;
    if (j->maxlum > j->limit && j->a64 < DM_A64_MAX) { /* too bright for the text: one more step of scrim, again */
        ++j->a64, j->pos = 0, j->maxlum = 0;
        return 1;
    }
    j->phase = j->art_only ? PH_SAVE : PH_COMMIT;
    return 1;
}

/* ---------------------------------------------------------------------------
 * The files and the card
 */
static void *dm_ensure_bitmap(void) {
    if (!dm.bmp) {
        void *b = bitmap_create_ex(DM_W, DM_H, DM_W * 4, BITMAP_RGBA8888);
        unsigned *d = b ? (unsigned *)bitmap_lock_buffer_for_write(b) : (unsigned *)0;
        if (b && (!d || bitmap_get_line_length(b) != DM_W * 4)) {
            if (d) bitmap_unlock_buffer(b);
            bitmap_destroy(b);
            b = (void *)0;
        } else if (b) {
            *(unsigned short *)((char *)b + BITMAP_FLAGS) |=
                1; /* opaque: every pixel is, the corners are blended into black */
            bitmap_unlock_buffer(b);
        }
        dm.bmp = b;
    }
    return dm.bmp;
}

static unsigned dm_fnv_bytes(const unsigned char *p, unsigned n) {
    unsigned h = FNV_SEED;
    while (n--) h = (h ^ *p++) * 16777619u;
    return h;
}

/* The art file: M1XA, width and height (u16), the art seed, the FNV-1a of the pixels (u32 each), then the RGB565 words. 0 when it was written. */
static int dm_save_art(const job_t *j) {
    unsigned char hdr[DM_ART_HEAD];
    unsigned ck = dm_fnv_bytes((const unsigned char *)j->px, DM_W * DM_H * 2);
    memcpy(hdr, "M1XA", 4);
    hdr[4] = DM_W & 255, hdr[5] = DM_W >> 8, hdr[6] = DM_H & 255, hdr[7] = DM_H >> 8;
    memcpy(hdr + 8, &j->aseed, 4);
    memcpy(hdr + 12, &ck, 4);
    return pod_card_write(MIX_DIR, MIX_ART_FILE, MIX_ART_TMP, hdr, DM_ART_HEAD, j->px, DM_W * DM_H * 2);
}

/* The art file read back into the card's bitmap; 1 when it is whole and was made for the mix's art seed. */
static int dm_load_art(void) {
    unsigned size = DM_ART_HEAD + DM_W * DM_H * 2;
    unsigned char *buf = calloc(1, size + 1);
    unsigned w, h, seed, ck;
    int n, ok = 0;
    dm.load = 0;
    if (!buf) return 0;
    n = dm_read(MIX_ART_FILE, buf, size + 1);
    if (n == (int)size && dm_eq(buf, "M1XA", 4)) {
        w = buf[4] | buf[5] << 8, h = buf[6] | buf[7] << 8;
        memcpy(&seed, buf + 8, 4);
        memcpy(&ck, buf + 12, 4);
        ok = w == DM_W && h == DM_H && seed == dm.aseed && ck == dm_fnv_bytes(buf + DM_ART_HEAD, DM_W * DM_H * 2);
    }
    if (ok && dm_ensure_bitmap()) {
        dm_fill_bitmap((const unsigned short *)(buf + DM_ART_HEAD));
        widget_invalidate_force(dm.card, (void *)0);
    }
    if (!ok) dm.load = 2; /* no art (or a bad file): made again from the mix's tones and seed */
    free(buf);
    return ok;
}

static int dm_ph_save(job_t *j) {
    dm_save_art(j);
    if (dm_ensure_bitmap()) {
        dm_fill_bitmap(j->px);
        widget_invalidate_force(dm.card, (void *)0);
    }
    return 2;
}

/* The mix is made: the art file (a failure costs the next start a re-render), the mix file (a failure fails the job), the card
 * switched to the new mix. */
static int dm_ph_commit(job_t *j) {
    char buf[DM_FILE_MAX + 1], *o = buf;
    const char *end = buf + DM_FILE_MAX;
    unsigned i;
    dm_put(&o, end, "M1X2\n");
    dm_putdec(&o, end, j->day), dm_put(&o, end, "\t");
    dm_puthex(&o, end, j->seed, 8), dm_put(&o, end, "\t");
    dm_puthex(&o, end, j->aseed, 8), dm_put(&o, end, "\t");
    dm_putdec(&o, end, j->regen), dm_put(&o, end, "\t");
    dm_putdec(&o, end, j->npick), dm_put(&o, end, "\n");
    for (i = 0; i < j->ntone; ++i) {
        if (i) dm_put(&o, end, " ");
        dm_puthex(&o, end, j->tone[i] & 255, 2), dm_puthex(&o, end, j->tone[i] >> 8 & 255, 2),
            dm_puthex(&o, end, j->tone[i] >> 16 & 255, 2);
    }
    dm_put(&o, end, "\n");
    for (i = 0; i < j->nname; ++i) {
        if (i) dm_put(&o, end, "\t");
        dm_put(&o, end, j->name[i]);
    }
    dm_put(&o, end, "\n");
    for (i = 0; i < j->npick; ++i)
        dm_put(&o, end, cc_str(j->pk[i].raw, REC_PATH)),
            dm_put(&o, end,
                   "\n"); /* (every path was checked by dm_path_ok in the copy phase: the file holds them all) */
    *o = 0;
    if (pod_card_write(MIX_DIR, MIX_FILE, MIX_TMP, buf, (unsigned)(o - buf), (const void *)0, 0) != 0) return 0;
    dm_save_art(
        j); /* (after the mix file: a failed mix file leaves yesterday's art file alone; a failed art file costs the next start a re-render) */
    if (!dm_load())
        return 0; /* the file read back is the state: day, seed, tones, names and the paths (a file the reader refuses is no mix) */
    dm.have = 1, dm.laid = 0;
    if (dm_ensure_bitmap()) dm_fill_bitmap(j->px);
    dm_apply();
    return 2;
}

/* ---------------------------------------------------------------------------
 * The job's steps, one a tick
 */
static unsigned dm_seed_for(unsigned day, unsigned regen) {
    unsigned s = day * 2654435761u ^ regen * 0x85EBCA6Bu;
    return s ? s : 1;
}

static void dm_job_start(int art_only) {
    job_t *j = dm_job_new();
    unsigned k;
    if (!j) { /* no memory: not tried again before tomorrow or a restart */
        dm.fail_day = dm_today();
        dm_regen_req = 0;
        if (art_only) dm.load = 0;
        return;
    }
    j->art_only = art_only;
    if (art_only) { /* the art again from the mix's own tones and seed */
        for (k = 0; k < dm.ntone; ++k) j->tone[k] = dm.tone[k];
        j->ntone = dm.ntone, j->seed = dm.seed, j->aseed = dm.aseed, j->phase = PH_FIELD;
    } else {
        j->day = dm_today();
        j->manual = dm_regen_req > 0;
        dm_regen_req = 0;
        if (!j->day) { /* the clock is not set: no day to make a mix for */
            free(j);
            return;
        }
        j->regen = j->manual ? (dm.have && dm.day == j->day ? (dm.regen < 255 ? dm.regen + 1 : 255) : 1) : 0;
        j->seed = dm_seed_for(j->day, j->regen);
        j->phase = PH_OFT;
    }
    dm.job = j;
}

static void dm_step(void) {
    job_t *j = dm.job;
    int ok = 0;
    switch (j->phase) {
    case PH_OFT:
        ok = dm_ph_oft(j);
        break;
    case PH_REC:
        ok = dm_ph_rec(j);
        break;
    case PH_FAV:
        ok = dm_ph_fav(j);
        break;
    case PH_LIB:
        ok = dm_ph_lib(j);
        break;
    case PH_SCORE:
        ok = dm_ph_score(j);
        break;
    case PH_PICK:
        ok = dm_ph_pick(j);
        break;
    case PH_COPY:
        ok = dm_ph_copy(j);
        break;
    case PH_ALBUM:
        ok = dm_ph_album(j);
        break;
    case PH_FIELD:
        ok = dm_ph_field(j);
        break;
    case PH_BRIGHT:
        ok = dm_ph_bright(j);
        break;
    case PH_RENDER:
        ok = dm_ph_render(j);
        break;
    case PH_COMMIT:
        ok = dm_ph_commit(j);
        break;
    case PH_SAVE:
        ok = dm_ph_save(j);
        break;
    default:
        break;
    }
    if (ok == 2)
        dm_job_end(0);
    else if (!ok)
        dm_job_end(1);
}

/* ---------------------------------------------------------------------------
 * The text of the card, laid out once per mix and language with the canvas' own font
 */
static int dm_w(void *canvas, const unsigned *s, unsigned n) {
    float w = canvas_measure_text(canvas, s, n);
    return (int)(w + 0.999f);
}

/* s (NUL-terminated) cut with an ellipsis to maxw px: the longest prefix whose width with the ellipsis fits (patch/grid.c grid_fit). Its length. */
static int dm_fit(void *canvas, unsigned *s, int maxw) {
    unsigned len = 0, lo, hi;
    while (s[len]) len++;
    if (len && dm_w(canvas, s, len) > maxw) {
        lo = 0, hi = len - 1;
        while (lo < hi) {
            unsigned mid = (lo + hi + 1) / 2, keep = s[mid];
            s[mid] = ELLIPSIS;
            if (dm_w(canvas, s, mid + 1) <= maxw)
                lo = mid;
            else
                hi = mid - 1;
            s[mid] = keep;
        }
        s[lo] = ELLIPSIS;
        s[lo + 1] = 0;
        len = lo + 1;
    }
    return (int)len;
}

static void dm_wide(unsigned *dst, unsigned cap, const char *s, unsigned n) { tk_utf8_to_utf16_ex(s, n, dst, cap); }

static int dm_cjk(unsigned c) {
    return (c >= 0x2e80 && c <= 0xffef) || (c >= 0x0e00 && c <= 0x0e7f) || (c >= 0xac00 && c <= 0xd7af);
}

/* The width of t[s..e) without its trailing spaces. */
static int dm_wr(void *canvas, const unsigned *t, unsigned s, unsigned e) {
    while (e > s && t[e - 1] == ' ') --e;
    return e > s ? dm_w(canvas, t + s, e - s) : 0;
}

/* Greedy wrap of t[0..n) into at most maxl lines of room px (pod_dailymix.wrap): the units are a run of non-space, non-CJK characters with the space after it,
 * or one CJK / Thai / Hangul character. Lines as [ls, le) ranges without trailing spaces; the number of lines, 0 when a unit is wider than the room or more
 * lines would be needed. */
static int dm_wrap(void *canvas, const unsigned *t, unsigned n, int room, int maxl, unsigned *ls, unsigned *le) {
    unsigned i = 0, cs = 0, ce = 0, as, ae, e;
    int nl = 0;
    while (i < n) {
        as = i;
        if (dm_cjk(t[i]) || t[i] == ' ')
            ae = i + 1;
        else {
            ae = i;
            while (ae < n && t[ae] != ' ' && !dm_cjk(t[ae])) ++ae;
            if (ae < n && t[ae] == ' ') ++ae;
        }
        i = ae;
        if (dm_wr(canvas, t, cs, ae) <= room &&
            ce >= cs) { /* the unit joins the line (cs == ce: an empty line starts at this unit) */
            if (cs == ce) cs = as;
            ce = ae;
            continue;
        }
        if (cs == ce || dm_wr(canvas, t, as, ae) > room) return 0;
        if (nl == DM_LINES) return 0;
        for (e = ce; e > cs && t[e - 1] == ' ';) --e;
        ls[nl] = cs, le[nl++] = e;
        cs = as, ce = ae;
    }
    if (cs < ce) {
        if (nl == DM_LINES) return 0;
        for (e = ce; e > cs && t[e - 1] == ' ';) --e;
        ls[nl] = cs, le[nl++] = e;
    }
    return nl <= maxl ? nl : 0;
}

/* tpl with its first %s replaced by a and its second (if it has one) by b, into out (size bytes with the NUL); the length. The translations are printf
 * templates in form only: they are never passed to printf. */
static unsigned dm_subst(char *out, unsigned size, const char *tpl, const char *a, const char *b) {
    char *o = out;
    const char *end = out + size - 1;
    int used = 0;
    for (; *tpl && o < end; ++tpl) {
        if (tpl[0] == '%' && tpl[1] == 's' && used < 2) {
            dm_put(&o, end, used++ ? b : a);
            ++tpl;
        } else
            *o++ = *tpl;
    }
    *o = 0;
    return (unsigned)(o - out);
}

/* The artists line for n names: "A, B, C and more" in the language (the two-name template applied name by name, then the "and more" one). */
static unsigned dm_names_text(char *out, unsigned size, unsigned n) {
    char acc[256], next[256];
    unsigned i;
    dm_copy(acc, sizeof acc, dm.name[0]);
    for (i = 1; i < n; ++i) {
        dm_subst(next, sizeof next, TR("%s, %s"), acc, dm.name[i]);
        memcpy(acc, next, sizeof acc);
    }
    return dm_subst(out, size, TR("%s and more"), acc, "");
}

static void dm_set_sub(const unsigned *t, const unsigned *ls, const unsigned *le, int nl) {
    int i;
    for (i = 0; i < nl && i < DM_SUB_LINES; ++i) {
        unsigned len = le[i] - ls[i];
        if (len >= DM_STEXT) len = DM_STEXT - 1;
        memcpy(dm.sl[i], t + ls[i], len * sizeof(unsigned));
        dm.sl[i][len] = 0;
        dm.slen[i] = (int)len;
    }
    dm.sn = nl < DM_SUB_LINES ? nl : DM_SUB_LINES;
}

/* The top-artists line: the most names (in order) whose "A, B, C and more" wraps into DM_SUB_LINES lines of DM_SUB_W; if not even one name does, the first
 * name's text wrapped as far as it goes, cut with an ellipsis on the last line (pod_dailymix.artist_lines). */
static void dm_artist_lines(void *canvas) {
    char utf[512];
    unsigned wide[DM_STEXT * 2], ls[DM_LINES], le[DM_LINES], n, len, i;
    int nl;
    dm.sn = 0;
    for (n = dm.nname < DM_MAX_NAMES ? dm.nname : DM_MAX_NAMES; n >= 1; --n) {
        len = dm_names_text(utf, sizeof utf, n);
        dm_wide(wide, DM_STEXT * 2, utf, len);
        for (len = 0; wide[len]; ++len) {
        }
        nl = dm_wrap(canvas, wide, len, DM_SUB_W, DM_SUB_LINES, ls, le);
        if (nl) {
            dm_set_sub(wide, ls, le, nl);
            return;
        }
    }
    len = dm_names_text(utf, sizeof utf, 1);
    dm_wide(wide, DM_STEXT * 2, utf, len);
    for (len = 0; wide[len]; ++len) {
    }
    nl = dm_wrap(canvas, wide, len, DM_SUB_W, DM_LINES, ls, le);
    if (!nl) { /* a unit wider than the line: the first name alone */
        dm_wide(wide, DM_STEXT * 2, dm.name[0], dm_len(dm.name[0]));
        for (len = 0; wide[len]; ++len) {
        }
        ls[0] = 0, le[0] = len, nl = 1;
    }
    dm_set_sub(wide, ls, le, nl);
    i = (unsigned)dm.sn - 1;
    if (dm.slen[i] >= DM_STEXT - 1) dm.slen[i] = DM_STEXT - 2;
    dm.sl[i][dm.slen[i]] = ELLIPSIS;
    dm.sl[i][dm.slen[i] + 1] = 0;
    dm.slen[i]++;
    while (dm_w(canvas, dm.sl[i], (unsigned)dm.slen[i]) > DM_SUB_W && dm.slen[i] > 1) {
        dm.sl[i][dm.slen[i] - 2] = ELLIPSIS;
        dm.sl[i][dm.slen[i] - 1] = 0;
        dm.slen[i]--;
    }
}

/* The title "Daily Mix" in the player's language, split at its first space into two lines (a word without one is one line, on the bottom line's box). */
static void dm_title_lines(void) {
    const char *t = TR("Daily Mix"), *sp = t;
    while (*sp && *sp != ' ') ++sp;
    if (*sp == ' ') {
        dm_wide(dm.tl[0], DM_TEXT, t, (unsigned)(sp - t));
        dm_wide(dm.tl[1], DM_TEXT, sp + 1, dm_len(sp + 1));
        dm.tn = 2;
    } else {
        dm_wide(dm.tl[1], DM_TEXT, t, dm_len(t));
        dm.tn = 1;
    }
}

static void dm_layout(void *canvas) {
    int i;
    dm_title_lines();
    widget_prepare_text_style(dm.st_title, canvas);
    for (i = 2 - dm.tn; i < 2; ++i) dm.tlen[i] = dm_fit(canvas, dm.tl[i], DM_TITLE_W);
    widget_prepare_text_style(dm.st_sub, canvas);
    dm_artist_lines(canvas);
    dm.laid = 1;
}

/* The card's own EVT_AFTER_PAINT, in the card's coordinates: the bitmap (a flat grey until it is made) and the text. Nothing is made here. */
static int dm_on_paint(void *ctx, void *e) {
    void *canvas = e ? *(void **)((char *)e + EVENT_PAINT_CANVAS) : (void *)0;
    int src[4], dst[4], rect[4], i;
    (void)ctx;
    if (!canvas || !dm.win || !dm.shown) return RET_OK;
    if (dm.bmp) {
        src[0] = 0, src[1] = 0, src[2] = DM_W, src[3] = DM_H;
        dst[0] = 0, dst[1] = 0, dst[2] = DM_W, dst[3] = DM_H;
        canvas_draw_image(canvas, dm.bmp, src, dst);
    } else {
        canvas_set_fill_color(canvas, DM_GREY);
        canvas_fill_rect(canvas, 0, 0, DM_W, DM_H);
    }
    if (!dm.laid) dm_layout(canvas);
    widget_prepare_text_style(dm.st_title, canvas);
    for (i = 2 - dm.tn; i < 2; ++i) {
        rect[0] = DM_PAD, rect[1] = i ? DM_TITLE_Y2 : DM_TITLE_Y1, rect[2] = DM_TITLE_W, rect[3] = DM_TITLE_PITCH;
        if (dm.tlen[i]) canvas_draw_text_in_rect(canvas, dm.tl[i], (unsigned)dm.tlen[i], rect);
    }
    widget_prepare_text_style(dm.st_sub, canvas);
    for (i = 0; i < dm.sn; ++i) {
        rect[0] = DM_PAD, rect[1] = DM_SUB_Y + i * DM_SUB_PITCH, rect[2] = DM_SUB_W, rect[3] = DM_SUB_PITCH;
        if (dm.slen[i]) canvas_draw_text_in_rect(canvas, dm.sl[i], (unsigned)dm.slen[i], rect);
    }
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * Touch: the card opens the page, the disc plays the mix
 */

/* The mix's paths (dm.paths, NUL separated) as an array; their number. */
static unsigned dm_paths(const char **out) {
    const char *p = dm.paths;
    unsigned i;
    if (!p) return 0;
    for (i = 0; i < dm.count && i < MIX_SONGS; ++i) {
        out[i] = p;
        while (*p) ++p;
        ++p;
    }
    return i;
}

/* Where the mix's songs are in a stock list of the library's songs (the list loadLocalClassList(0xf001) leaves, or the queue loadSongList makes from it): for each of the np paths,
 * in order, the index of the first record that has it, ~0 for none. The path of every record is hashed once (12,288 songs: about 4 M instructions) and compared with the
 * np hashes, a hit verified with strcmp. Returns how many were found. */
static unsigned dm_mix_find(void *dq, const char *const *paths, unsigned np, unsigned *at) {
    unsigned h[MIX_SONGS], n = dq ? deque_size(dq) : 0, i, k, found = 0;
    for (k = 0; k < np; ++k) at[k] = ~0u, h[k] = dm_path_hash(paths[k]);
    if (n > DM_LIB_MAX) n = DM_LIB_MAX;
    for (i = 0; i < n && found < np; ++i) {
        const char *p = cc_str(deque_at(dq, i), REC_PATH);
        unsigned x = dm_path_hash(p);
        for (k = 0; k < np; ++k)
            if (at[k] == ~0u && h[k] == x && !strcmp(paths[k], p)) at[k] = i, ++found;
    }
    return found;
}

/* The mix's rows alone, not the library: stock's own song query (getAllMusic's `select * from songtable`, same database, same row callback) with `where fileurl in (...)`,
 * the paths with their quotes doubled, in a heap string (25 paths of 255 bytes are over the Library filter's 1 KB buffer: pq_filter then leaves the statement as it is, which
 * is as correct). The callback leaves the rows in *tools_pdeq_directory (toolsQueryDbTable clears it first); *pdeq_showlist is not touched. The deque is the rows in the
 * database's order, NULL when the query failed or found none; the caller reads it, then dm_rows_done() clears it (stock clears it after every list it loads). */
static void *dm_rows(const char *const *paths, unsigned np) {
    static const char head[] = "select * from songtable where fileurl in (";
    unsigned i, n = sizeof head + 1;
    const char *p;
    char *sql, *o;
    void *dq = (void *)0;
    for (i = 0; i < np; ++i) {
        for (p = paths[i]; *p; ++p) n += 2;
        n += 3;
    }
    sql = calloc(n, 1);
    if (!sql) return (void *)0;
    memcpy(sql, head, sizeof head - 1);
    o = sql + sizeof head - 1;
    for (i = 0; i < np; ++i) {
        if (i) *o++ = ',';
        *o++ = '\'';
        for (p = paths[i]; *p; ++p) {
            if (*p == '\'') *o++ = '\'';
            *o++ = *p;
        }
        *o++ = '\'';
    }
    *o++ = ')';
    if (toolsQueryDbTable(STOCK_DB_PATH, sql, STOCK_SONG_ROW, 0) >= 0) dq = *(void **)PDEQ_TOOLS_TMP;
    free(sql);
    return dq && deque_size(dq) ? dq : (void *)0;
}

static void dm_rows_done(void) { deque_clear(*(void **)PDEQ_TOOLS_TMP); }

static int dp_open(void); /* the page (below): 0 once it is up or already open */

/* The card's tap: the page. (A tap that cannot open it does nothing; with no song of the mix left on the card, the usual message.) */
static void dm_open(void) {
    if (dm.have) dp_open();
}

/* The mix as the queue, from the song `want` (a path; none: the first, or with `shuffle` a random one, with the stock Shuffle mode), then Now Playing, the way the Shuffle page
 * starts a song (patch/shuffle.c shuffle_play): the library as the Songs page loads it, loadSongList(queue, name, cue, 0xf001) from the song (this also leaves stock's memory
 * playback record: after a restart the player resumes in library order), the first file checked with access, pod_open_player. The queue Now Playing gets is the mix's songs in
 * the mix's order, made of the records loadSongList made (they carry the class). paths: the mix's paths in order. A song that is not in the library or not on the card is left
 * out; none left, or the wanted one gone: the usual message and nothing starts. */
static void dm_play_at(const char *const *paths, unsigned np, const char *want, int shuffle) {
    const char *sel[MIX_SONGS];
    unsigned at[MIX_SONGS], m = 0, k = 0, i, n, start;
    void *lib, *queue = (void *)0, *small = (void *)0, *saved, *pick;
    lib = np ? dm_rows(paths, np) : (void *)0;
    if (lib) dm_mix_find(lib, paths, np, at);
    for (i = 0; lib && i < np; ++i)
        if (at[i] != ~0u && !access(paths[i], F_OK)) sel[m] = paths[i], at[m++] = at[i];
    if (want)
        for (k = 0; k < m && strcmp(sel[k], want); ++k) {
        }
    else if (shuffle && m)
        k = pod_rand(m);
    if (k >= m) {
        dm_rows_done();
        pod_toast(TR("Storage unavailable"));
        return;
    }
    small = _create_deque("stSongInfo");
    if (small) queue = _create_deque("stSongInfo");
    if (queue) {
        deque_init(small);
        deque_init(queue);
        for (i = 0; i < m; ++i) _deque_push_back(small, deque_at(lib, at[i])); /* the mix's rows in the mix's order */
        pick = deque_at(small, k);
        saved = *(void **)PDEQ_SHOWLIST;
        *(void **)PDEQ_SHOWLIST = small; /* loadSongList copies the shown list */
        *(int *)G_CLASS_TYPE = CLASS_ALL_SONGS;
        loadSongList(queue, cc_str(pick, REC_NAME), I(pick, REC_CUE_START), CLASS_ALL_SONGS);
        *(void **)PDEQ_SHOWLIST = saved;
        n = deque_size(queue);
        for (start = 0; start < n && strcmp(cc_str(deque_at(queue, start), REC_PATH), sel[k]);
             ++start) { /* by path: a file name shared by several songs is not enough */
        }
        if (start < n) {
            if (shuffle)
                pod_set_mode_for_queue(MODE_SHUFFLE);
            else if (!want)
                pod_set_in_order_for_queue(); /* Play plays the mix in order, even after a Shuffle; a row tap keeps the mode */
            pod_open_player(queue, (int)start, CLASS_ALL_SONGS);
        }
    }
    if (queue) deque_destroy(queue);
    if (small) deque_destroy(small);
    dm_rows_done();
}

/* From the first song (the card's disc). */
static void dm_play(void) {
    const char *paths[MIX_SONGS];
    unsigned np = dm_paths(paths);
    dm_play_at(paths, np, (const char *)0, 0);
}

static int dm_on_play(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (dm.win && dm.shown) dm_play();
    return RET_OK;
}

static int dm_pe(void *e, int field) { return *(int *)((char *)e + field); }

static int dm_on_down(void *ctx, void *e) {
    (void)ctx;
    dm.down = 0;
    if (!e || !dm.win) return RET_OK;
    dm.down = 1;
    dm.down_x = dm_pe(e, PE_X), dm.down_y = dm_pe(e, PE_Y);
    return RET_OK;
}

static int dm_on_up(void *ctx, void *e) {
    int dx, dy, was = dm.down;
    (void)ctx;
    dm.down = 0;
    if (!was || !e || !dm.win || !dm.shown) return RET_OK;
    dx = dm_pe(e, PE_X) - dm.down_x;
    dy = dm_pe(e, PE_Y) - dm.down_y;
    if (dx < 0) dx = -dx;
    if (dy < 0) dy = -dy;
    if (dx < RC_TAP_PX && dy < RC_TAP_PX) dm_open();
    return RET_OK;
}

static int dm_on_abort(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    dm.down = 0;
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * The card as the mix and the switch say; the timer; the window's events
 */
static void dm_apply(void) {
    int want = dm.on && dm.have;
    if (want || want != dm.shown) menu_daily(dm.win, want);
    dm.shown = want;
    if (want) widget_invalidate_force(dm.card, (void *)0);
}

/* A mix is wanted: the switch is on and the day has no mix yet (or Regenerate asked for one). A day that failed is not tried again before the next day. */
static int dm_need(void) {
    unsigned today;
    if (!dm.on || !pod_card_mounted()) return 0; /* no card, no mix */
    if (dm_regen_req) return 1;
    today = dm_today();
    if (!today || dm.fail_day == today) return 0;
    return !dm.have || dm.day != today;
}

static void dm_unarm(void) {
    if (dm.timer) timer_remove(dm.timer);
    dm.timer = 0;
}

static int dm_tick(const void *timer);

static void dm_kick(void) {
    unsigned ms, waited;
    if (dm.timer || !dm.win || !dm.fg) return;
    if (dm.job || (dm.load && dm.on))
        ms = DM_TICK_MS; /* (with the card off its art waits: nothing is read or made) */
    else if (dm_need()) {
        waited = (unsigned)time_now_ms() - dm.t0;
        ms = waited >= DM_START_MS ? DM_TICK_MS : DM_START_MS - waited; /* never inside the boot guard's window */
    } else
        return;
    if (!pod_screen_lit() && ms < POD_DARK_MS) ms = POD_DARK_MS;
    dm.timer = timer_add(dm_tick, (void *)0, ms);
}

/* The one thing the timer does: a step of the job, else the art file (or its re-render), else a new job when one is wanted. */
static void dm_work(void) {
    if (dm.job) {
        dm_step();
        return;
    }
    if (dm.load == 1 && dm.on) {
        dm_load_art();
        return;
    }
    if (dm.load == 2 && dm.on) {
        dm.load = 0;
        dm_job_start(1);
        return;
    }
    if ((unsigned)time_now_ms() - dm.t0 >= DM_START_MS && dm_need()) dm_job_start(0);
}

static int dm_tick(const void *timer) {
    (void)timer;
    dm.timer = 0; /* this one ends with the return */
    if (!dm.win || !dm.fg) return RET_OK;
    if (pod_screen_lit()) dm_work();
    dm_kick();
    return RET_OK;
}

static void dm_stop(void) {
    dm_unarm();
    dm_job_cancel();
    if (dm.bmp) bitmap_destroy(dm.bmp);
    free(dm.paths);
    memset(&dm, 0, sizeof dm);
}

static int dm_on_destroy(void *ctx, void *e) {
    (void)e;
    if (ctx == dm.win) dm_stop(); /* an earlier window's end leaves the new one alone */
    return RET_OK;
}

/* The menu goes away: the timer stops and a job in the middle is dropped (its lists belong to whoever loads the next one; it starts again from the top). */
static int dm_on_background(void *ctx, void *e) {
    (void)e;
    if (!dm.win || ctx != dm.win) return RET_OK;
    dm.fg = 0;
    dm.down = 0;
    dm_unarm();
    if (dm.job) {
        int art = dm.job->art_only;
        dm_job_cancel();
        if (art) dm.load = 2;
    }
    return RET_OK;
}

static int dm_on_foreground(void *ctx, void *e) {
    (void)e;
    if (!dm.win || ctx != dm.win) return RET_OK;
    dm.fg = 1;
    dm.on = dailymix_setting();
    dm.laid = 0;
    dm_apply();
    dm_kick();
    return RET_OK;
}

/* The Home instance of the menu is up (patch/home.c, after the list took the whole window). */
void dailymix_start(void *win) {
    if (!win || home_off()) return;
    if (dm.win) dm_stop(); /* an earlier window that never said it was gone */
    dm.win = win;
    dm.sec = widget_lookup(win, "pod_daily", 1);
    dm.card = widget_lookup(win, "pod_dm_card", 1);
    dm.disc = widget_lookup(win, "pod_dm_play", 1);
    dm.sv = widget_lookup(win, "pod_scrollview", 1);
    dm.st_title = widget_lookup(win, "pod_dm_title", 1);
    dm.st_sub = widget_lookup(win, "pod_dm_sub", 1);
    dm.fg = 1;
    if (!dm.sec || !dm.card || !dm.disc || !dm.sv || !dm.st_title || !dm.st_sub ||
        !widget_on(win, EVT_DESTROY, dm_on_destroy, win) || !widget_on(win, EVT_WINDOW_TO_BG, dm_on_background, win) ||
        !widget_on(win, EVT_WINDOW_TO_FG, dm_on_foreground, win) ||
        !widget_on(dm.card, EVT_AFTER_PAINT, dm_on_paint, (void *)0) ||
        !widget_on(dm.card, EVT_POINTER_DOWN, dm_on_down, (void *)0) ||
        !widget_on(dm.card, EVT_POINTER_UP, dm_on_up, (void *)0) ||
        !widget_on(dm.card, EVT_POINTER_ABORT, dm_on_abort, (void *)0) ||
        !widget_on(dm.disc, EVT_CLICK, dm_on_play, (void *)0)) {
        dm_stop(); /* a handler that was registered finds no window of ours any more */
        return;
    }
    pod_corner_fill(dm.corner, DM_R);
    dm.t0 = (unsigned)time_now_ms();
    dm.on = dailymix_setting();
    dm.have = dm_load();
    dm.load = dm.have ? 1 : 0;
    dm.timer = timer_add(dm_tick, (void *)0, DM_FIRST_MS);
    if (!dm.timer) {
        dm_stop();
        return;
    }
    dm_apply();
}

/* ---------------------------------------------------------------------------
 * The page (docs/modules/dailymix.md "The page"): an Apple Music playlist page, opened by a tap on the card. Its own window ui/m1plus_dailymix.bin (the stock list_view >
 * scroll_view over the whole 450 px window, one content view, a floating glass back disc); everything else is painted by the content view's own EVT_AFTER_PAINT as the
 * Albums page paints its list (patch/albums.c): the art (320 x DP_ART_H, made here at open from the mix file's tones and seed: the card's blob field, no scrim, the foot
 * fading into the page's solid tint), the centred lines, the description and the songs (the grid's 52 px covers, a star for favourites). The Shuffle disc, the white Play pill
 * and its glyph are widgets of the content view (their images are the style's); their text is painted. Page-scoped: its widgets, their events, one loader timer.
 * No stock hook. Everything is freed with the window. The songs are the mix file's paths found in the library (copied: the stock list is replaced by every other query).
 */
#define DP_TAP_PX SC_DRAG_PX
#define DP_AHEAD 2 /* rows loaded beyond the view in the scroll direction */
#define DP_DESC_WIDE 160 /* wide chars of the description (DM_STEXT) */

static struct {
    void *win, *lv, *sv, *view, *shuf, *play, *glyph, *add;
    void *st_title, *st_sub, *st_upd, *st_desc, *st_play, *st_row, *st_artist; /* hidden labels: the text styles */
    pick_t *
        rows; /* the mix's songs that are in the library and on the card, copied (strings strdup'ed), in the mix's order */
    unsigned n;
    unsigned day; /* the mix's day (the Updated line) */
    void *art; /* the art (RGBA, DP_W x DP_ART_H) */
    unsigned tint, grey, accent; /* 0x00BBGGRR */
    unsigned barc; /* the art's top row (0x00BBGGRR): the status bar's colour, darkened by pod_bar_color */
    int barok, bar; /* the window's foreground and background events are registered; the bar's colour is ours */
    int laid, glyph_x, text_x, text_w;
    unsigned tl[DM_TEXT], sl[DM_TEXT], ul[DM_TEXT], pl[DM_TEXT];
    int tlen, slen, ulen, plen;
    unsigned dl[DP_DESC_LINES][DP_DESC_WIDE];
    int dlen[DP_DESC_LINES], dn;
    unsigned key[DP_ROWS_MAX]; /* the cover cache key of each song's album */
    int press, down, down_x, down_y; /* the row under the finger + 1 / the row a press began on + 1 and where */
    int seen, dir, noscroll;
    int saved,
        away; /* the mix's playlist exists (the Add disc shows a check); the window went to the back since it was looked up */
    unsigned more_timer;
    grid_t g; /* the 52 px cover ring (patch/grid.c), the placeholder */
} dp __attribute__((section(".scratch")));

static int dp_off(void) { return dp.sv ? I(dp.sv, SC_YOFF) : 0; }
static int dp_abs(int v) { return v < 0 ? -v : v; }
static int dp_content(void) { return DP_ROWS_Y + (int)dp.n * LIST_ROW_H + DP_BOTTOM; }

static void dp_color(void *w, const char *prop, unsigned c) {
    unsigned v[4]; /* value_t: type at 0, the uint32 at 8 */
    if (!w) return;
    memset(v, 0, sizeof v);
    value_set_uint32(v, 0xff000000u | c);
    widget_set_style(w, prop, v);
}

/* ---- colours (tools/pod_dailymix.py tint_of, pale: integers, the same) */
static unsigned dp_snap(const unsigned *c) {
    unsigned r = c[0] >> 3, g = c[1] >> 2, b = c[2] >> 3;
    return (r << 3 | r >> 2) | (g << 2 | g >> 4) << 8 | (b << 3 | b >> 2) << 16;
}

/* The page's solid tint from the average of the art's last row (r | g << 8 | b << 16): the brightest channel lifted to DP_V_MIN, darkened by 15/16 until the 16 bit
 * luminance is at most DP_LUM_MAX, snapped to the 565 grid the panel shows (the art's last rows and the window's colour are then the same word). */
static unsigned dp_tint(unsigned avg) {
    unsigned c[3], v, i;
    c[0] = avg & 255, c[1] = avg >> 8 & 255, c[2] = avg >> 16 & 255;
    v = c[0] > c[1] ? c[0] : c[1];
    if (c[2] > v) v = c[2];
    if (v < DP_V_MIN) {
        for (i = 0; i < 3; ++i) c[i] = v ? DP_V_MIN * c[i] / v : DP_V_MIN;
    }
    for (;;) { /* the cap is checked on what the panel shows (the snap can lift a channel by a few levels) */
        unsigned s = dp_snap(c);
        if (dm_lum(s & 255, s >> 8 & 255, s >> 16 & 255) <= DP_LUM_MAX) return s;
        for (i = 0; i < 3; ++i) c[i] = c[i] * 15 >> 4;
    }
}

static unsigned dp_pale(unsigned tint, unsigned k) {
    unsigned i, out = 0;
    for (i = 0; i < 3; ++i) {
        unsigned c = tint >> (8 * i) & 255;
        out |= (c + ((255 - c) * k >> 8)) << (8 * i);
    }
    return out;
}

/* ---- the art: the card's blobs (the same seed) over DP_W x DP_ART_H, the foot faded into the tint, RGB565 dithered, straight into the bitmap */
static unsigned dp_fade(int y) {
    int t = (y - (DP_ART_H - DP_FADE) + 1) * 256 / (DP_FADE - DP_HOLD);
    unsigned s;
    if (t < 0) t = 0;
    if (t > 256) t = 256;
    s = (unsigned)t;
    return s * s * (768 - 2 * s) >> 16;
}

static void dp_art(void) {
    int base[3];
    blob_t bl[4];
    unsigned char row[DP_W * 3];
    unsigned avg[3] = {0, 0, 0}, x, y, i, *d, tint, tc[3];
    dm_blobs_wh(dm.tone, dm.ntone, dm.aseed, DP_W, DP_ART_H, base, bl);
    dm_field_wh(row, DP_ART_H - 1, DP_W, base, bl, dm.ntone);
    for (x = 0; x < DP_W; ++x)
        for (i = 0; i < 3; ++i) avg[i] += row[x * 3 + i];
    dp.tint = dp_tint(avg[0] / DP_W | avg[1] / DP_W << 8 | avg[2] / DP_W << 16);
    dp.grey = dp_pale(dp.tint, DP_GREY_K), dp.accent = dp_pale(dp.tint, DP_ACC_K);
    dm_field_wh(row, 0, DP_W, base, bl, dm.ntone); /* the top row: where the status bar meets the page */
    for (i = 0; i < 3; ++i) avg[i] = 0;
    for (x = 0; x < DP_W; ++x)
        for (i = 0; i < 3; ++i) avg[i] += row[x * 3 + i];
    dp.barc = avg[0] / DP_W | avg[1] / DP_W << 8 | avg[2] / DP_W << 16;
    tint = dp.tint;
    if (pal_light()) { /* Light Mode: no tint. The window's colour is black (the style hook flips it to paper), the art fades into that paper, the greys are neutral (they flip too) */
        dp.tint = dp.barc = 0, dp.grey = 0xaaaaaau, dp.accent = 0xddddddu;
        tint = pal_map(0xff000000u) & 0xffffff;
    }
    for (i = 0; i < 3; ++i) tc[i] = tint >> (8 * i) & 255;
    dp.art = bitmap_create_ex(DP_W, DP_ART_H, DP_W * 4, BITMAP_RGBA8888);
    d = dp.art ? (unsigned *)bitmap_lock_buffer_for_write(dp.art) : (unsigned *)0;
    if (dp.art && (!d || bitmap_get_line_length(dp.art) != DP_W * 4)) {
        if (d) bitmap_unlock_buffer(dp.art);
        bitmap_destroy(dp.art);
        dp.art = (void *)0;
    } else if (dp.art) {
        *(unsigned short *)((char *)dp.art + BITMAP_FLAGS) |= 1; /* opaque */
        for (y = 0; y < DP_ART_H; ++y) {
            unsigned s = dp_fade((int)y);
            if (s >= 256) {
                for (x = 0; x < DP_W; ++x) d[y * DP_W + x] = 0xff000000u | tint;
                continue;
            }
            dm_field_wh(row, y, DP_W, base, bl, dm.ntone);
            for (x = 0; x < DP_W; ++x) {
                const unsigned char *f = row + x * 3;
                unsigned t = dm_bayer[y & 3][x & 3], er, eg, eb;
                dm_quant(
                    f[0] + (((int)tc[0] - f[0]) * (int)s >> 8) + ((4 * (int)s + 128) >> 8), t, 8, 5,
                    &er); /* + up to half a step as the fade completes: the 565 floor would leave the faded rows darker than the tint */
                dm_quant(f[1] + (((int)tc[1] - f[1]) * (int)s >> 8) + ((2 * (int)s + 128) >> 8), t, 4, 6, &eg);
                dm_quant(f[2] + (((int)tc[2] - f[2]) * (int)s >> 8) + ((4 * (int)s + 128) >> 8), t, 8, 5, &eb);
                d[y * DP_W + x] = 0xff000000u | er | eg << 8 | eb << 16;
            }
        }
        bitmap_unlock_buffer(dp.art);
    }
}

/* ---- the texts (laid out once per open and when the page comes back to the front, with the canvas' own font) */
static void dp_civil(unsigned days, int *y, int *m, int *d) {
    int z = (int)days + 719468, era = z / 146097, doe = z - era * 146097;
    int yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    int doy = doe - (365 * yoe + yoe / 4 - yoe / 100), mp = (5 * doy + 2) / 153;
    *d = doy - (153 * mp + 2) / 5 + 1;
    *m = mp < 10 ? mp + 3 : mp - 9;
    *y = yoe + era * 400 + (*m <= 2);
}

/* "Updated today" / "Updated yesterday" / "Updated 2026-10-26": the mix's day against the local day now (a clock that is not set, or went back, says today). */
static unsigned dp_updated(char *out, unsigned size) {
    unsigned today = dm_today(), gone = today > dp.day ? today - dp.day : 0;
    char date[16];
    int y, m, d;
    if (!today || !gone || gone == 1) {
        dm_copy(out, size, TR(gone == 1 ? "Updated yesterday" : "Updated today"));
        return dm_len(out);
    }
    dp_civil(dp.day, &y, &m, &d);
    snprintf(date, sizeof date, "%04d-%02d-%02d", y, m, d);
    return dm_subst(out, size, TR("Updated %s"), date, "");
}

static void dp_wide(unsigned *dst, unsigned cap, const char *s) {
    memset(dst, 0, cap * sizeof(unsigned));
    dm_wide(dst, cap, s, dm_len(s));
}

/* The description wrapped into at most DP_DESC_LINES lines of DP_TEXT_W; a longer text ends its last line with an ellipsis. */
static void dp_desc(void *canvas) {
    const char *t = TR("Songs you love and some to rediscover, made fresh every day.");
    unsigned wide[DP_DESC_WIDE], ls[DM_LINES], le[DM_LINES], n = 0, e, len;
    int nl, i;
    dp_wide(wide, DP_DESC_WIDE, t);
    while (wide[n]) ++n;
    nl = dm_wrap(canvas, wide, n, DP_TEXT_W, DM_LINES, ls, le);
    if (!nl) ls[0] = 0, le[0] = n, nl = 1; /* a unit wider than the line: one line, cut with an ellipsis */
    dp.dn = nl < DP_DESC_LINES ? nl : DP_DESC_LINES;
    for (i = 0; i < dp.dn; ++i) {
        e = i == dp.dn - 1 && nl > dp.dn ? n : le[i];
        len = e - ls[i];
        if (len > DP_DESC_WIDE - 1) len = DP_DESC_WIDE - 1;
        memset(dp.dl[i], 0, sizeof dp.dl[i]);
        memcpy(dp.dl[i], wide + ls[i], len * sizeof(unsigned));
        dp.dlen[i] = dm_fit(canvas, dp.dl[i], DP_TEXT_W);
    }
}

static void dp_layout(void *canvas) {
    char line[96];
    dp_wide(dp.tl, DM_TEXT, TR("Daily Mix"));
    widget_prepare_text_style(dp.st_title, canvas);
    dp.tlen = dm_fit(canvas, dp.tl, DP_TEXT_W);
    dp_wide(dp.sl, DM_TEXT, TR("Made for You"));
    widget_prepare_text_style(dp.st_sub, canvas);
    dp.slen = dm_fit(canvas, dp.sl, DP_TEXT_W);
    dp_updated(line, sizeof line);
    dp_wide(dp.ul, DM_TEXT, line);
    widget_prepare_text_style(dp.st_upd, canvas);
    dp.ulen = dm_fit(canvas, dp.ul, DP_TEXT_W);
    dp_wide(dp.pl, DM_TEXT, TR("Play"));
    widget_prepare_text_style(dp.st_play, canvas);
    dp.plen = dm_fit(canvas, dp.pl, dp.text_w);
    widget_prepare_text_style(dp.st_desc, canvas);
    dp_desc(canvas);
    dp.laid = 1;
}

/* The pill's glyph, the gap and the text centred as a pair for the language (the album page's centring, patch/albumpage.c). The text is measured with the
 * hidden label's own style; one that cannot be measured is taken as 40 px. */
static void dp_pill(void) {
    unsigned wide[DM_TEXT];
    float w;
    int tw, room = DP_PLAY_W - 2 * (DP_PILL_GLYPH + DP_PILL_GAP);
    dp_wide(wide, DM_TEXT, TR("Play"));
    w = widget_measure_text(dp.st_play, wide);
    tw = (int)(w + 0.999f);
    if (tw <= 0) tw = 40;
    if (tw > room) tw = room;
    dp.glyph_x = DP_PLAY_X + (DP_PLAY_W - (DP_PILL_GLYPH + DP_PILL_GAP + tw)) / 2;
    dp.text_x = dp.glyph_x + DP_PILL_GLYPH + DP_PILL_GAP;
    dp.text_w = tw + 2;
    if (dp.glyph) widget_move(dp.glyph, dp.glyph_x, DP_BTN_Y + (DP_BTN_H - DP_PILL_GLYPH) / 2);
}

/* ---- the songs */
static void dp_row_window(int *r0, int *r1) {
    int s = dp_off(), n = (int)dp.n;
    *r0 = s > DP_ROWS_Y ? (s - DP_ROWS_Y) / LIST_ROW_H : 0;
    *r1 = s + DP_VIEW_H - 1 >= DP_ROWS_Y ? (s + DP_VIEW_H - 1 - DP_ROWS_Y) / LIST_ROW_H : -1;
    if (*r1 > n - 1) *r1 = n - 1;
}

/* The songs [*lo, *hi] the tiles are kept for: those in view and DP_AHEAD rows beyond them in the scroll direction. */
static void dp_window(int *lo, int *hi) {
    int r0, r1;
    dp_row_window(&r0, &r1);
    if (dp.dir < 0)
        r0 -= DP_AHEAD;
    else
        r1 += DP_AHEAD;
    if (r0 < 0) r0 = 0;
    if (r1 > (int)dp.n - 1) r1 = (int)dp.n - 1;
    *lo = r0, *hi = r1;
}

static grid_tile_t *dp_tile(int a) {
    int lo, hi, fresh;
    grid_tile_t *t;
    dp_window(&lo, &hi);
    t = grid_tile(&dp.g, a, lo, hi, &fresh);
    if (fresh) {
        void *rec = dp.rows[a].raw;
        const char *title = cc_str(rec, REC_TITLE);
        if (!*title) title = cc_str(rec, REC_NAME);
        grid_set(t, title, cc_str(rec, REC_ARTIST), dp.key[a]);
    }
    return t;
}

/* A bitmap of w x h at (x, y) in the window, rows beyond the view cut by hand. */
static void dp_blit(void *canvas, void *bmp, int w, int h, int x, int y) {
    int top = y < 0 ? -y : 0, bottom = y + h > DP_VIEW_H ? DP_VIEW_H - y : h, src[4], dst[4];
    if (!bmp || bottom <= top) return;
    src[0] = 0, src[1] = top, src[2] = w, src[3] = bottom - top;
    dst[0] = x, dst[1] = y + top, dst[2] = w, dst[3] = bottom - top;
    canvas_draw_image(canvas, bmp, src, dst);
}

static void dp_fill(void *canvas, int x, int y0, int w, int y1, unsigned c) {
    if (y0 < 0) y0 = 0;
    if (y1 > DP_VIEW_H) y1 = DP_VIEW_H;
    if (y1 <= y0) return;
    ui_fill_color(canvas, c);
    canvas_fill_rect(canvas, x, y0, w, y1 - y0);
}

static void dp_line(void *canvas, const unsigned *s, int len, int x, int y, int w, int h) {
    int rect[4];
    if (!len || y + h <= 0 || y >= DP_VIEW_H) return;
    rect[0] = x, rect[1] = y, rect[2] = w, rect[3] = h;
    canvas_draw_text_in_rect(canvas, s, (unsigned)len, rect);
}

static void dp_paint_header(void *canvas, int s) {
    int i;
    dp_blit(canvas, dp.art, DP_W, DP_ART_H, 0, -s);
    if (!dp.laid) dp_layout(canvas);
    widget_prepare_text_style(dp.st_title, canvas);
    dp_line(canvas, dp.tl, dp.tlen, DP_TEXT_X, DP_TITLE_Y - s, DP_TEXT_W, DP_TITLE_PX);
    widget_prepare_text_style(dp.st_sub, canvas);
    dp_line(canvas, dp.sl, dp.slen, DP_TEXT_X, DP_SUB_Y - s, DP_TEXT_W, DP_SUB_PX);
    widget_prepare_text_style(dp.st_upd, canvas);
    dp_line(canvas, dp.ul, dp.ulen, DP_TEXT_X, DP_UPD_Y - s, DP_TEXT_W, DP_UPD_PX);
    widget_prepare_text_style(dp.st_play, canvas);
    dp_line(canvas, dp.pl, dp.plen, dp.text_x, DP_BTN_Y + (DP_BTN_H - DP_PILL_H) / 2 - s, dp.text_w, DP_PILL_H);
    widget_prepare_text_style(dp.st_desc, canvas);
    for (i = 0; i < dp.dn; ++i)
        dp_line(canvas, dp.dl[i], dp.dlen[i], DP_TEXT_X, DP_DESC_Y + i * DP_DESC_PITCH - s, DP_TEXT_W, DP_DESC_PITCH);
}

static void dp_paint_rows(void *canvas, int s) {
    int r0, r1, r, pass;
    dp_row_window(&r0, &r1);
    for (r = r0; r <= r1; ++r) {
        int y = DP_ROWS_Y + r * LIST_ROW_H - s;
        grid_tile_t *t = dp_tile(r);
        if (dp.press == r + 1) dp_fill(canvas, 0, y, DP_W, y + LIST_ROW_H - 1, DP_PRESS);
        grid_blit(canvas, &dp.g, t, LIST_ART_X, y + LIST_ART_Y, DP_VIEW_H);
        dp_fill(canvas, LIST_TEXT_X, y + LIST_ROW_H - 1, DP_W - LIST_TEXT_X, y + LIST_ROW_H, DP_HAIR);
    }
    for (pass = 0; pass < 2; ++pass) { /* titles, then artists: one text style at a time */
        widget_prepare_text_style(pass ? dp.st_artist : dp.st_row, canvas);
        for (r = r0; r <= r1; ++r)
            grid_text(canvas, dp_tile(r), pass, LIST_TEXT_X,
                      DP_ROWS_Y + r * LIST_ROW_H - s + (pass ? LIST_SUB_Y : LIST_TITLE_Y), LIST_TEXT_W,
                      pass ? LIST_SUB_H : LIST_TITLE_H, 0);
    }
}

/* The content view's EVT_AFTER_PAINT: the header and the visible songs and nothing else; it decodes nothing, arms nothing. The canvas origin is the content view's, which the
 * scroll_view has moved up by yoffset: moved back down for the paint (as the Albums page does), so the window's top is 0. */
static int dp_on_paint(void *ctx, void *e) {
    void *canvas = e ? *(void **)((char *)e + EVENT_PAINT_CANVAS) : (void *)0;
    int off = dp_off();
    (void)ctx;
    if (!canvas || !dp.win || !dp.g.tiles) return RET_OK;
    I(canvas, CANVAS_OY) += off;
    dp_paint_header(canvas, off);
    dp_paint_rows(canvas, off);
    I(canvas, CANVAS_OY) -= off;
    return RET_OK;
}

/* ---- the cover loader: one cover per tick, nothing while the scroll_view moves (the Albums list's, patch/albums.c) */
static void dp_redraw(void) { widget_invalidate_force(dp.sv, (void *)0); }

static int dp_next_load(void) {
    int lo, hi, a, best = -1, bd = 0x7fffffff, s = dp_off();
    if (!dp.g.tiles || !dp.n) return -1;
    dp_window(&lo, &hi);
    for (a = lo; a <= hi; ++a) {
        grid_tile_t *t = grid_find(&dp.g, a);
        int top, d;
        if (t && t->art) continue;
        top = DP_ROWS_Y + a * LIST_ROW_H - s;
        d = dp_abs(top + LIST_ROW_H / 2 - DP_VIEW_H / 2);
        if (top >= DP_VIEW_H || top + LIST_ROW_H <= 0) d += 100000; /* ahead of the view */
        if (d < bd) bd = d, best = a;
    }
    return best;
}

static int dp_on_load(const void *unused);

static int dp_moving(void) { return grid_moving(dp.sv); }

static void dp_kick(void) {
    if (!dp.more_timer && dp.view && (dp.noscroll || dp_next_load() >= 0))
        dp.more_timer = timer_add(dp_on_load, (void *)0, DP_MORE_MS);
}

static void dp_dir(void) {
    int s = dp_off();
    if (s != dp.seen) dp.dir = s > dp.seen ? 1 : -1;
    dp.seen = s;
}

static int dp_on_load(const void *unused) {
    int a;
    (void)unused;
    dp.more_timer = 0;
    if (!dp.view) return RET_OK;
    dp_dir();
    if (dp_moving()) { /* nothing is decoded while it moves: look again next tick */
        dp_kick();
        return RET_OK;
    }
    a = dp_next_load();
    if (a >= 0) {
        int top = DP_ROWS_Y + a * LIST_ROW_H - dp_off();
        grid_art(&dp.g, dp_tile(a));
        if (top < DP_VIEW_H && top + LIST_ROW_H > 0) dp_redraw();
    }
    dp_kick();
    return RET_OK;
}

static int dp_on_scroll(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (!dp.view) return RET_OK;
    dp_dir();
    dp_kick();
    return RET_OK;
}

/* ---- touch: the songs (the buttons are widgets) */
static int dp_row_at(int y) {
    int a;
    if (y < DP_ROWS_Y) return -1;
    a = (y - DP_ROWS_Y) / LIST_ROW_H;
    return a < (int)dp.n ? a : -1;
}

static int dp_item_of(void *e) {
    int pt[2];
    pt[0] = I(e, PE_X), pt[1] = I(e, PE_Y);
    widget_to_local(dp.view, pt);
    return dp_row_at(pt[1]);
}

static void dp_set_press(int p) {
    if (dp.press == p) return;
    dp.press = p;
    dp_redraw();
}

/* The page's rows as the mix's paths in order, then the queue (dm_play_at): the song `want` (a path), else the first or a random one. */
static void dp_play(const char *want, int shuffle) {
    const char *paths[MIX_SONGS];
    unsigned i, n = dp.n < MIX_SONGS ? dp.n : MIX_SONGS;
    for (i = 0; i < n; ++i) paths[i] = cc_str(dp.rows[i].raw, REC_PATH);
    dm_play_at(paths, n, want, shuffle);
}

static int dp_on_down(void *ctx, void *e) {
    int a;
    (void)ctx;
    dp.down = 0;
    if (!e || !dp.view) return RET_OK;
    a = dp_item_of(e);
    dp.down = a + 1, dp.down_x = I(e, PE_X), dp.down_y = I(e, PE_Y);
    dp_set_press(a + 1);
    return RET_OK;
}

static int dp_on_up(void *ctx, void *e) {
    int a = dp.down - 1;
    (void)ctx;
    dp.down = 0;
    dp_set_press(0);
    if (a < 0 || !e || !dp.view) return RET_OK;
    if (dp_abs(I(e, PE_X) - dp.down_x) < DP_TAP_PX && dp_abs(I(e, PE_Y) - dp.down_y) < DP_TAP_PX && dp_item_of(e) == a)
        dp_play(cc_str(dp.rows[a].raw, REC_PATH), 0);
    return RET_OK;
}

/* The scroll_view took the gesture as a drag (it aborts its children's press), or the window went to the background. */
static int dp_on_abort(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    dp.down = 0;
    dp_set_press(0);
    return RET_OK;
}

/* The status bar takes the colour of the art's top row (darkened for its white glyphs, pod_bar_color) while the page is in front, as the album page and Now
 * Playing tint it; the stock black comes back when the page goes to the background or closes, and only while the bar is still ours (pod_bar_black: Now Playing
 * opened by Play keeps its own colour). Only when both window events are registered, so every way out restores it. */
static void dp_bar_apply(void) {
    if (dp.win && dp.barok && pod_bar_tint(dp.win, dp.barc))
        dp.bar = 1; /* a failed call keeps what the bar has (and owes) */
}

static void dp_bar_black(void) {
    if (!dp.bar) return;
    dp.bar = 0;
    pod_bar_black(dp.win);
}

/* The Add disc's playlist: "<Daily Mix> <the mix's day as YYYY-MM-DD>", one per mix. */
static void dp_name(char *name, unsigned size) {
    int y, m, d;
    dp_civil(dp.day, &y, &m, &d);
    snprintf(name, size, "%s %04d-%02d-%02d", TR("Daily Mix"), y, m, d);
}

/* What the stock playlist calls change and the page puts back: the browsing class, classinfo[0..1], the navigation title. */
typedef struct {
    int cls, ci[2];
    char title[NAV_TITLE_SIZE];
} dp_state_t;

static void dp_keep(dp_state_t *s) {
    s->cls = *(int *)G_CLASS_TYPE;
    memcpy(s->ci, (void *)CLASSINFO, sizeof s->ci);
    memcpy(s->title, (void *)NAV_TITLE, sizeof s->title);
}

static void dp_put_back(const dp_state_t *s) {
    *(int *)G_CLASS_TYPE = s->cls;
    memcpy((void *)CLASSINFO, s->ci, sizeof s->ci);
    memcpy((void *)NAV_TITLE, s->title, sizeof s->title);
}

/* The Add disc: a plus, or a check once the mix's playlist exists. */
static void dp_mark(int on) {
    dp.saved = on;
    widget_set_prop_str(dp.add, "style:normal:icon", on ? "dp_added" : "dp_add");
    widget_set_prop_str(dp.add, "style:over:icon", on ? "dp_added" : "dp_add");
    widget_set_prop_str(dp.add, "style:pressed:icon", on ? "dp_added_down" : "dp_add_down");
}

/* Whether the mix's playlist exists: the stock playlist list (loadLocalClassList(0xf00b) replaces *pdeq_playlist) has a row titled with its name. At the page's opening
 * and each time it comes back to the front (the playlist may have been deleted on the Playlists page meanwhile). */
static void dp_look(void) {
    char name[112];
    dp_state_t s;
    void *list;
    unsigned i, n;
    int on = 0;
    if (!dp.add) return;
    dp_name(name, sizeof name);
    dp_keep(&s);
    loadLocalClassList(CLASS_PLAYLISTS);
    list = *(void **)PDEQ_PLAYLIST;
    n = list ? deque_size(list) : 0;
    for (i = 0; i < n && !on; ++i) on = !strcmp(cc_str(deque_at(list, i), REC_TITLE), name);
    dp_put_back(&s);
    dp_mark(on);
}

static int dp_on_foreground(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    dp.laid = 0; /* the language, or the day, may have changed */
    if (dp.away) {
        dp.away = 0;
        dp_look();
    }
    dp_redraw();
    dp_bar_apply();
    return RET_OK;
}

static int dp_on_background(void *ctx, void *e) {
    dp.away = 1;
    dp_bar_black();
    return dp_on_abort(ctx, e); /* and a press in progress ends */
}

/* The Add disc: the mix as a NEW stock playlist named dp_name, its songs in the mix's order; once it exists (dp_look, or this tap) the disc is a check and a tap only says so
 * (the stock "Playlist Already Exists"), so the mix is never saved twice. The only stock playlist the Daily Mix ever makes; the mix itself stays in its own file. Creation is
 * the Playlists page's (createPlayListItem on the stock list, -1 full, -2 exists); the songs are added the way the stock batch add (batch_add_file, class 0xf001 -> 0xf00b)
 * adds one: a shallow copy of the page's record whose id is max(100, getPlayListMaxId()) + 1 and whose REC_DISC is the playlist id, checkPlayListExist first, then addPlayList
 * (the page's own rows are not written to, and neither is the stock library list). A song whose file is gone or whose record is not a song is left out; none left: "Storage
 * unavailable" and no playlist. The browsing class, classinfo[0..1] and the navigation title are put back as they were. Runs on the UI thread (a database write per song, as stock). */
static void dp_save(void) {
    char name[112];
    unsigned char rec[REC_SIZE];
    dp_state_t s;
    int ok[DP_ROWS_MAX], r, added = 0;
    unsigned i, n = 0;
    void *list;
    const char *msg;
    if (!dp.win || !dp.n || dp.n > DP_ROWS_MAX) return;
    if (dp.saved) {
        pod_toast(TR("msg_playlistexist"));
        return;
    }
    for (i = 0; i < dp.n; ++i) {
        ok[i] = I(dp.rows[i].raw, REC_TYPE) == 8 && !access(cc_str(dp.rows[i].raw, REC_PATH), F_OK);
        n += ok[i];
    }
    if (!n) {
        pod_toast(TR("Storage unavailable"));
        return;
    }
    dp_name(name, sizeof name);
    dp_keep(&s);
    loadLocalClassList(CLASS_PLAYLISTS);
    list = *(void **)PDEQ_PLAYLIST;
    r = list ? createPlayListItem(list, name) : -3;
    if (r == -3)
        msg = "msg_addfailed";
    else if (r == -1)
        msg = "msg_playlistfull";
    else if (r < 0)
        msg = "msg_playlistexist";
    else {
        for (i = 0; i < dp.n; ++i) {
            int mx;
            if (!ok[i]) continue;
            memcpy(rec, dp.rows[i].raw, REC_SIZE);
            if (checkPlayListExist(rec, r)) continue;
            mx = getPlayListMaxId();
            I(rec, REC_ID) = (mx < 100 ? 100 : mx) + 1;
            I(rec, REC_DISC) = r;
            added += addPlayList(rec) == 1;
        }
        msg = added ? "msg_addplaylistsuccess" : "msg_addfailed";
    }
    dp_put_back(&s);
    if (r >= 0 || r == -2) dp_mark(1); /* made now, or made before: the name is taken either way */
    pod_toast(TR(msg));
}

static int dp_on_add(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    dp_save();
    return RET_OK;
}

static int dp_on_play(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    dp_play((const char *)0, 0);
    return RET_OK;
}
static int dp_on_shuffle(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    dp_play((const char *)0, 1);
    return RET_OK;
}

/* Everything the page holds is freed. A window that is already gone (or never was ours) is not this page: the destroy event carries the window it was registered on. */
static void dp_release(void) {
    unsigned i;
    if (dp.more_timer) timer_remove(dp.more_timer);
    grid_free(&dp.g);
    if (dp.art) bitmap_destroy(dp.art);
    for (i = 0; i < dp.n; ++i) dm_rec_free(&dp.rows[i]);
    free(dp.rows);
    memset(&dp, 0, sizeof dp);
}

static int dp_on_destroy(void *ctx, void *e) {
    (void)e;
    if (ctx == dp.win) { /* an earlier window's end leaves a newer page alone */
        dp_bar_black();
        dp_release();
    }
    return RET_OK;
}

/* The cover cache key of each song's album (cc_cover_key: its own, else the library album of that title's; 0 without an album tag). One copy of the stock album list,
 * dropped at once. */
static void dp_keys(void) {
    void *albums = cc_albums();
    unsigned i;
    for (i = 0; i < dp.n; ++i) {
        void *rec = dp.rows[i].raw;
        const char *album = cc_str(rec, REC_ALBUM);
        dp.key[i] = *album ? cc_cover_key(albums, cc_album_key(rec), album, (char *)0) : 0;
    }
    if (albums) deque_destroy(albums);
}

/* The mix's songs that are in the library and on the card, copied from the library as the Songs page loads it (one stock query, one hash pass over it): dp.rows, dp.n. */
static void dp_songs(void) {
    const char *paths[MIX_SONGS];
    unsigned at[MIX_SONGS], np = dm_paths(paths), i;
    void *lib = np ? dm_rows(paths, np) : (void *)0;
    dp.rows = np ? calloc(np, sizeof(pick_t)) : (pick_t *)0;
    if (lib && dp.rows) {
        dm_mix_find(lib, paths, np, at);
        for (i = 0; i < np; ++i)
            if (at[i] != ~0u && !access(paths[i], F_OK)) dm_rec_copy(&dp.rows[dp.n++], deque_at(lib, at[i]));
    }
    if (lib) dm_rows_done();
}

/* The page. 0 once it is up (or already open); -1 when nothing could be made (no song of the mix left in the library and on the card: the usual message; no window, an asset
 * that is not ours, no memory: nothing happens). */
static int dp_open(void) {
    if (dp.win) return 0;
    if (!dm.have) return -1;
    memset(&dp, 0, sizeof dp);
    dp.day = dm.day;
    dp_songs();
    if (!dp.n) {
        if (dp.rows) pod_toast(TR("Storage unavailable")); /* (no memory for the rows: nothing, no message) */
        free(dp.rows);
        memset(&dp, 0, sizeof dp);
        return -1;
    }
    dp_keys();
    dp.win = window_open("m1plus_dailymix");
    if (!dp.win) {
        dp_release();
        return -1;
    }
    widget_on(dp.win, EVT_DESTROY, dp_on_destroy, dp.win);
    pod_bind(dp.win, "btn_return", pod_on_back, (void *)0);
    dp.lv = widget_lookup(dp.win, "dp_listview", 1);
    dp.sv = widget_lookup(dp.win, "dp_scrollview", 1);
    dp.view = widget_lookup(dp.win, "view_dm", 1);
    dp.shuf = widget_lookup(dp.win, "btn_dp_shuffle", 1);
    dp.play = widget_lookup(dp.win, "btn_dp_play", 1);
    dp.glyph = widget_lookup(dp.win, "img_dp_glyph", 1);
    dp.add = widget_lookup(dp.win, "btn_dp_add", 1);
    dp.st_title = widget_lookup(dp.win, "label_dp_title", 1);
    dp.st_sub = widget_lookup(dp.win, "label_dp_sub", 1);
    dp.st_upd = widget_lookup(dp.win, "label_dp_upd", 1);
    dp.st_desc = widget_lookup(dp.win, "label_dp_desc", 1);
    dp.st_play = widget_lookup(dp.win, "label_dp_play", 1);
    dp.st_row = widget_lookup(dp.win, "label_dp_row", 1);
    dp.st_artist = widget_lookup(dp.win, "label_dp_artist", 1);
    if (!dp.lv || !dp.sv || !dp.view || !dp.shuf || !dp.play || !dp.glyph || !dp.add || !dp.st_title || !dp.st_sub ||
        !dp.st_upd || !dp.st_desc || !dp.st_play || !dp.st_row || !dp.st_artist ||
        !grid_init(&dp.g, dp.win, GRID_TILES, LIST_ART, 0)) {
        navigator_back(); /* an asset that is not ours, or no memory for the ring: the window goes again, the caller opens the stock list */
        dp_release();
        return -1;
    }
    grid_shape(&dp.g, LIST_ART, LIST_R,
               1); /* the corners are cut in the alpha: the pressed row's fill shows behind them */
    grid_placeholder(&dp.g);
    dp_art();
    dp_color(dp.win, "normal:bg_color", dp.tint);
    dp_color(dp.lv, "normal:bg_color", dp.tint);
    dp_color(dp.sv, "normal:bg_color", dp.tint);
    dp_color(dp.view, "normal:bg_color", dp.tint);
    dp_color(dp.st_upd, "normal:text_color", dp.accent);
    dp_color(dp.st_play, "normal:text_color", DP_PILL_INK);
    dp_color(dp.st_desc, "normal:text_color", dp.grey);
    dp_color(dp.st_artist, "normal:text_color", dp.grey);
    dp_pill();
    widget_resize(dp.view, DP_W, dp_content());
    widget_set_prop_int(dp.sv, "virtual_h", dp_content());
    dp.dir = 1;
    dp.noscroll = !widget_on(dp.sv, EVT_SCROLL, dp_on_scroll, (void *)0) ||
                  !widget_on(dp.sv, EVT_SCROLL_END, dp_on_scroll, (void *)0);
    widget_on(dp.play, EVT_CLICK, dp_on_play, (void *)0);
    widget_on(dp.shuf, EVT_CLICK, dp_on_shuffle, (void *)0);
    widget_on(dp.add, EVT_CLICK, dp_on_add, (void *)0);
    dp_look();
    dp.barok = widget_on(dp.win, EVT_WINDOW_TO_FG, dp_on_foreground, (void *)0) != 0;
    dp.barok &= widget_on(dp.win, EVT_WINDOW_TO_BG, dp_on_background, (void *)0) != 0;
    widget_on(dp.view, EVT_POINTER_DOWN, dp_on_down, (void *)0);
    widget_on(dp.view, EVT_POINTER_UP, dp_on_up, (void *)0);
    widget_on(dp.view, EVT_POINTER_ABORT, dp_on_abort, (void *)0);
    widget_on(dp.view, EVT_AFTER_PAINT, dp_on_paint, (void *)0);
    dp_bar_apply(); /* the page is in front */
    dp_kick();
    return 0;
}
