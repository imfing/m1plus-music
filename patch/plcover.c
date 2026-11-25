/* M1+ Music generated playlist covers: a style drawn in colours taken from a playlist's albums, the Daily Mix way (docs/modules/plcover.md).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * plc_art draws styles 1..5 (Solid, Mesh, Sunburst, Stripes, Band) into a side x side bitmap of opaque RGBA words, RGB565 values through the Daily Mix's
 * dither (patch/dmart.h). Integers only: tools/pod_plcover.py is the model, line by line, and test/pod/plcover.py compares the pixels. Style 0 (Albums)
 * is the mosaic the grid composes, and the corners are the caller's. plc_art touches no widget, file or heap; the stored choice (plc_get and the rest, below it) is the card file.
 */
#include "offsets.inc"
#include "stock.h"
#include "covercache.h"
#include "common.h"
#include "fnv.h"
#include "dmart.h"
#include "plcover.h"

static const unsigned short plc_atan[66] = {
    0,    163,  326,  489,  651,  813,  975,  1136, 1297, 1457, 1617, 1775, 1933, 2090, 2246, 2401, 2555,
    2708, 2860, 3010, 3159, 3307, 3453, 3599, 3742, 3884, 4025, 4164, 4302, 4438, 4572, 4705, 4836, 4966,
    5094, 5220, 5344, 5467, 5589, 5708, 5826, 5943, 6058, 6171, 6282, 6392, 6500, 6607, 6712, 6815, 6917,
    7018, 7117, 7214, 7310, 7405, 7498, 7589, 7679, 7768, 7856, 7942, 8026, 8110, 8192, 8273,
};

static const unsigned short plc_rays[256] = {
    256, 256, 256, 256, 255, 255, 255, 254, 254, 253, 252, 251, 250, 250, 249, 247, 246, 245, 244, 242, 241, 239,
    238, 236, 234, 233, 231, 229, 227, 225, 223, 221, 219, 216, 214, 212, 209, 207, 204, 202, 199, 196, 194, 191,
    188, 186, 183, 180, 177, 174, 171, 168, 165, 162, 159, 156, 153, 150, 147, 144, 141, 137, 134, 131, 128, 125,
    122, 119, 115, 112, 109, 106, 103, 100, 97,  94,  91,  88,  85,  82,  79,  76,  73,  70,  68,  65,  62,  60,
    57,  54,  52,  49,  47,  44,  42,  40,  37,  35,  33,  31,  29,  27,  25,  23,  22,  20,  18,  17,  15,  14,
    12,  11,  10,  9,   7,   6,   6,   5,   4,   3,   2,   2,   1,   1,   1,   0,   0,   0,   0,   0,   0,   0,
    1,   1,   1,   2,   2,   3,   4,   5,   6,   6,   7,   9,   10,  11,  12,  14,  15,  17,  18,  20,  22,  23,
    25,  27,  29,  31,  33,  35,  37,  40,  42,  44,  47,  49,  52,  54,  57,  60,  62,  65,  68,  70,  73,  76,
    79,  82,  85,  88,  91,  94,  97,  100, 103, 106, 109, 112, 115, 119, 122, 125, 128, 131, 134, 137, 141, 144,
    147, 150, 153, 156, 159, 162, 165, 168, 171, 174, 177, 180, 183, 186, 188, 191, 194, 196, 199, 202, 204, 207,
    209, 212, 214, 216, 219, 221, 223, 225, 227, 229, 231, 233, 234, 236, 238, 239, 241, 242, 244, 245, 246, 247,
    249, 250, 250, 251, 252, 253, 254, 254, 255, 255, 255, 256, 256, 256,
};

static const unsigned char plc_levels[5] = {128, 92, 154, 113, 77}; /* the columns' step heights of Stripes, /256 */

typedef struct {
    unsigned char c[3];
} plc_rgb_t;

static int plc_sm(int t) { return t * t * (768 - 2 * t) >> 16; }

static void plc_mix(const int *a, const int *b, int t, int *o) {
    int i;
    for (i = 0; i < 3; ++i) o[i] = a[i] + ((b[i] - a[i]) * t >> 8);
}

/* The palette: A the first tone prepared, K its 16 %, L its 70 % toward white, and ramp[0..256] from K through A to L. */
typedef struct {
    int a[3], k[3], l[3];
    plc_rgb_t ramp[257];
} plc_pal_t;

static void plc_pal(plc_pal_t *p, unsigned tone) {
    static const int white[3] = {255, 255, 255};
    int i, m[3];
    dm_prep(tone, p->a);
    for (i = 0; i < 3; ++i) p->k[i] = p->a[i] * PLC_K >> 8;
    plc_mix(p->a, white, PLC_L, p->l);
    for (i = 0; i <= 256; ++i) {
        int j;
        if (i < 128)
            plc_mix(p->k, p->a, plc_sm(2 * i), m);
        else
            plc_mix(p->a, p->l, plc_sm(2 * i - 256), m);
        for (j = 0; j < 3; ++j) p->ramp[i].c[j] = (unsigned char)m[j];
    }
}

/* Row y of f (3 bytes a pixel) through the dither into px. */
static void plc_out(unsigned *px, const unsigned char *f, unsigned y, int side) {
    const unsigned char *bayer = dm_bayer[y & 3];
    int x;
    for (x = 0; x < side; ++x, f += 3) {
        unsigned t = bayer[x & 3], er, eg, eb;
        dm_quant(f[0], t, 8, 5, &er);
        dm_quant(f[1], t, 4, 6, &eg);
        dm_quant(f[2], t, 8, 5, &eb);
        px[x] = 0xff000000u | er | eg << 8 | eb << 16;
    }
}

static void plc_fill(unsigned char *f, int n, const int *c) {
    int i;
    for (i = 0; i < n; ++i, f += 3) f[0] = (unsigned char)c[0], f[1] = (unsigned char)c[1], f[2] = (unsigned char)c[2];
}

static void plc_fill_rgb(unsigned char *f, int n, const plc_rgb_t *c) {
    int i;
    for (i = 0; i < n; ++i, f += 3) f[0] = c->c[0], f[1] = c->c[1], f[2] = c->c[2];
}

/* The angle of (x, y) in 65536ths of a turn (an octant and the 64 step table; rec[m] = 2^22 / m: no division). */
static unsigned plc_atan2(int y, int x, const unsigned *rec) {
    unsigned ax = (unsigned)(x < 0 ? -x : x), ay = (unsigned)(y < 0 ? -y : y), hi = ax > ay ? ax : ay,
             lo = ax > ay ? ay : ax, q, a, i;
    if (!hi) return 0;
    q = lo * rec[hi] >> 10;
    i = q >> 6;
    a = plc_atan[i] + ((plc_atan[i + 1] - plc_atan[i]) * (q & 63) >> 6);
    if (ay > ax) a = 16384 - a;
    if (x >= 0) return y >= 0 ? a : 65536 - a;
    return y >= 0 ? 32768 - a : 32768 + a;
}

static void plc_sunburst(unsigned *px, int side, const plc_pal_t *p) {
    unsigned rec[PLC_MAX * PLC_SUN_Y / 10 + 2], i1, i2, top;
    unsigned char f[PLC_MAX * 3];
    int cx = PLC_SUN_X * side / 10, cy = PLC_SUN_Y * side / 10, r1 = PLC_SUN_FAR * side / 10,
        r2 = PLC_SUN_NEAR * side / 10, y, m;
    int ex = cx > 2 * side - cx ? cx : 2 * side - cx, ey = cy > 2 * side - cy ? cy : 2 * side - cy;
    i1 = (256u << 20) / (unsigned)(r1 * r1), i2 = (256u << 20) / (unsigned)(r2 * r2);
    top = (unsigned)(ex > ey ? ex : ey) + 1;
    rec[0] = 0;
    for (m = 1; m <= (int)top; ++m) rec[m] = (1u << 22) / (unsigned)m;
    for (y = 0; y < side; ++y) {
        int Y = 2 * y + 1 - cy, x;
        unsigned char *o = f;
        for (x = 0; x < side; ++x, o += 3) {
            int X = 2 * x + 1 - cx, fa, ne, t, ray;
            unsigned d2 = (unsigned)(X * X + Y * Y);
            fa = (int)(d2 * i1 >> 20), ne = (int)(d2 * i2 >> 20);
            if (fa > 256) fa = 256;
            if (ne > 256) ne = 256;
            ray = plc_rays[(PLC_SUN_RAYS * plc_atan2(Y, X, rec) & 0xffff) >> 8];
            t = PLC_SUN_T0 + ((PLC_SUN_RAY * ray >> 8) * (256 - (PLC_SUN_FADE * plc_sm(fa) >> 8)) >> 8) +
                (PLC_SUN_GLOW * (256 - plc_sm(ne)) >> 8);
            if (t > 256) t = 256;
            o[0] = p->ramp[t].c[0], o[1] = p->ramp[t].c[1], o[2] = p->ramp[t].c[2];
        }
        plc_out(px + y * side, f, (unsigned)y, side);
    }
}

void plc_art(unsigned *px, int side, int style, const unsigned *tones, int nt, unsigned seed) {
    plc_pal_t pal;
    unsigned char f[PLC_MAX * 3];
    int y, i;
    if (side < 1 || side > PLC_MAX || style < PLC_STYLE_SOLID || style > PLC_STYLE_BAND) return;
    plc_pal(&pal, nt > 0 ? tones[0] : PLC_GREY);
    if (style == PLC_STYLE_MESH) {
        unsigned t[4];
        int base[3];
        blob_t bl[4];
        unsigned n = (unsigned)(nt > 4 ? 4 : nt);
        if (nt > 1) {
            for (i = 0; i < (int)n; ++i) t[i] = tones[i];
        } else {
            t[0] = 0xff000000u | (unsigned)pal.a[0] | (unsigned)pal.a[1] << 8 | (unsigned)pal.a[2] << 16;
            t[1] = 0xff000000u | (unsigned)pal.l[0] | (unsigned)pal.l[1] << 8 | (unsigned)pal.l[2] << 16;
            n = 2;
        }
        dm_blobs_wh(t, n, seed, (unsigned)side, (unsigned)side, base, bl);
        for (y = 0; y < side; ++y) {
            dm_field_wh(f, (unsigned)y, (unsigned)side, base, bl, n);
            plc_out(px + y * side, f, (unsigned)y, side);
        }
        return;
    }
    if (style == PLC_STYLE_SUNBURST) {
        plc_sunburst(px, side, &pal);
        return;
    }
    for (y = 0; y < side; ++y) {
        int v = (2 * y + 1) * 256 / (2 * side);
        if (style == PLC_STYLE_SOLID) {
            int top[3], bot[3], c[3];
            for (i = 0; i < 3; ++i) {
                top[i] = pal.a[i] * PLC_SOLID_TOP >> 8;
                if (top[i] > 255) top[i] = 255;
                bot[i] = pal.a[i] * PLC_SOLID_BOT >> 8;
            }
            plc_mix(top, bot, v, c);
            plc_fill(f, side, c);
        } else if (style == PLC_STYLE_BAND) {
            int d = v - PLC_BAND_Y, d2 = d * d, g = 0, c[3], b[3];
            if (d2 < PLC_BAND_R2) {
                int q = 256 - 256 * d2 / PLC_BAND_R2;
                g = (q * q >> 8) * PLC_BAND_MIX >> 8;
            }
            i = PLC_BAND_T0 + (PLC_BAND_TS * v >> 8);
            b[0] = pal.ramp[i].c[0], b[1] = pal.ramp[i].c[1], b[2] = pal.ramp[i].c[2];
            plc_mix(b, pal.l, g, c);
            plc_fill(f, side, c);
        } else { /* Stripes: column i holds x * 5 / side == i */
            for (i = 0; i < 5; ++i) {
                int t = v - plc_levels[i] + 128, x0 = (i * side + 4) / 5, x1 = ((i + 1) * side + 4) / 5;
                if (t < 0) t = 0;
                if (t > 256) t = 256;
                plc_fill_rgb(f + x0 * 3, x1 - x0, &pal.ramp[PLC_STRIPE_LO + (PLC_STRIPE_SPAN * plc_sm(t) >> 8)]);
            }
        }
        plc_out(px + y * side, f, (unsigned)y, side);
    }
}

/* ---------------------------------------------------------------------------
 * The file, strictly read: PLC_FILE on the card (no card: no covers, nothing written)
 *     M1PC1\n
 *     <id>\t<style 1..5>\t<flags hex>\t<seed hex8>\t<0..3 tones rrggbb, a space between>\t<name>\n      (one line per playlist)
 * The text is the state: plc_load keeps the lines that read (a line that does not is dropped, a bad header drops the file) in one buffer; the calls find a line by its id and name and edit the text.
 */
#define PLC_MAGIC "M1PC1\n"
#define PLC_MAGIC_LEN 6

static struct {
    char buf[PLC_FILE_MAX + 1]; /* (one byte more than the file may hold: a longer file is told by its size) */
    unsigned n; /* bytes of buf in use (0: nothing loaded) */
    unsigned
        sig[3]; /* the file's mtime, nanoseconds and size when read (0xffffffff x3: not known, read it every time) */
    int have; /* sig and buf are of the file (or of its absence) */
} plc __attribute__((section(".scratch")));

static int plc_bad(unsigned char c) { return c < 0x20 || c == 0x7f; }

static int plc_hexv(unsigned c) {
    if (c - '0' < 10) return (int)(c - '0');
    if (c - 'a' < 6) return (int)(c - 'a' + 10);
    return -1;
}

/* n lowercase hex digits at p; -1 when one is not. */
static long long plc_hex(const char *p, int n) {
    unsigned long long v = 0;
    int i, d;
    for (i = 0; i < n; ++i) {
        d = plc_hexv((unsigned char)p[i]);
        if (d < 0) return -1;
        v = v << 4 | (unsigned)d;
    }
    return (long long)v;
}

/* name into out (PLC_NAME_MAX bytes), control bytes as spaces, cut before a UTF-8 continuation byte that would be split. */
static void plc_copy(char *out, const char *s) {
    unsigned n = 0, j;
    while (s[n]) ++n;
    if (n >= PLC_NAME_MAX) {
        n = PLC_NAME_MAX - 1;
        while (n && ((unsigned char)s[n] & 0xc0) == 0x80) --n;
    }
    for (j = 0; j < n; ++j) out[j] = plc_bad((unsigned char)s[j]) ? ' ' : s[j];
    out[n] = 0;
}

static unsigned plc_sig(const plc_t *c) {
    unsigned h = FNV_SEED, i;
    h = (h ^ (unsigned)c->style) * FNV_PRIME;
    h = (h ^ c->flags) * FNV_PRIME;
    h = (h ^ c->seed) * FNV_PRIME;
    for (i = 0; i < (unsigned)c->nt; ++i) h = (h ^ c->tones[i]) * FNV_PRIME;
    h = (h ^ (unsigned)c->nt) * FNV_PRIME;
    return h | !h;
}

/* The line at p (up to stop) as an entry: *id, *c, *name (a pointer into the line, *nlen bytes) and *end after its newline. 0 when the line does not read. */
static int plc_line(const char *p, const char *stop, int *id, plc_t *c, const char **name, unsigned *nlen,
                    const char **end) {
    unsigned long long v = 0;
    unsigned d = 0;
    long long h;
    int i;
    while (p < stop && *p >= '0' && *p <= '9' && d < 10) v = v * 10 + (unsigned)(*p++ - '0'), ++d;
    if (!d || p >= stop || *p != '\t' || v > 0x7fffffffull || (d > 1 && p[-(int)d] == '0')) return 0;
    *id = (int)v, ++p;
    if (stop - p < 2 || p[0] < '1' || p[0] > '0' + PLC_STYLE_BAND || p[1] != '\t') return 0;
    c->style = p[0] - '0', p += 2;
    for (v = 0, d = 0; p < stop && plc_hexv((unsigned char)*p) >= 0 && d < 2; ++p, ++d)
        v = v << 4 | (unsigned)plc_hexv((unsigned char)*p);
    if (!d || p >= stop || *p != '\t' || (d > 1 && p[-2] == '0')) return 0;
    c->flags = (unsigned)v, ++p;
    if (stop - p < 9 || (h = plc_hex(p, 8)) < 0 || p[8] != '\t') return 0;
    c->seed = (unsigned)h, p += 9;
    for (c->nt = 0; p < stop && *p != '\t';) { /* 0..3 tones, a space between */
        if (c->nt == 3 || stop - p < 7 || (h = plc_hex(p, 6)) < 0) return 0;
        c->tones[c->nt++] = 0xff000000u | (unsigned)(h >> 16) | (unsigned)(h & 0xff00) | (unsigned)(h & 0xff) << 16;
        p += 6;
        if (*p == ' ')
            ++p;
        else if (*p != '\t')
            return 0;
        else
            break;
        if (p >= stop || *p == '\t') return 0; /* a trailing space */
    }
    if (p >= stop) return 0;
    for (i = c->nt; i < 3; ++i) c->tones[i] = 0;
    ++p; /* the tab */
    *name = p;
    while (p < stop && *p != '\n') {
        if (plc_bad((unsigned char)*p)) return 0;
        ++p;
    }
    *nlen = (unsigned)(p - *name);
    if (p >= stop || !*nlen || *nlen >= PLC_NAME_MAX) return 0;
    *end = p + 1;
    c->sig = plc_sig(c);
    return 1;
}

/* The file's mtime (seconds, nanoseconds) and size; all 0xffffffff when it cannot be read. struct stat (MIPS o32): st_size at +0x30, st_mtime at +0x40, its nanoseconds at +0x44. */
static void plc_stat(unsigned sig[3]) {
    unsigned st[40];
    memset(st, 0, sizeof st);
    if (__xstat(3, PLC_FILE, st) != 0)
        sig[0] = sig[1] = sig[2] = 0xffffffffu;
    else
        sig[0] = st[0x40 / 4], sig[1] = st[0x44 / 4], sig[2] = st[0x30 / 4];
}

/* The file into plc.buf, the lines that read; plc.n 0 when there is no card, no file or nothing that reads. */
static void plc_read(void) {
    const char *p, *stop;
    int fd, n = 0, r = 1, ents = 0, i;
    unsigned o = 0;
    plc.n = 0;
    plc.have = 1;
    plc_stat(plc.sig);
    if (!m1_card_mounted()) return;
    fd = open(PLC_FILE, O_RDONLY, 0);
    if (fd < 0) return;
    while (n < (int)sizeof plc.buf && (r = read(fd, plc.buf + n, sizeof plc.buf - (unsigned)n)) > 0) n += r;
    close(fd);
    if (r < 0 || n <= PLC_MAGIC_LEN || n > PLC_FILE_MAX) return;
    for (i = 0; i < PLC_MAGIC_LEN; ++i)
        if (plc.buf[i] != PLC_MAGIC[i]) return;
    stop = plc.buf + n, p = plc.buf + PLC_MAGIC_LEN,
    o = PLC_MAGIC_LEN; /* (the kept lines are moved down over the read ones: in place) */
    while (p < stop && ents < PL_MAX) {
        int id, dup = 0;
        plc_t c;
        const char *nm, *end, *q = p;
        unsigned nl;
        if (!plc_line(p, stop, &id, &c, &nm, &nl, &end)) { /* a line that does not read: dropped, up to its newline */
            while (q < stop && *q != '\n') ++q;
            if (q >= stop) break;
            p = q + 1;
            continue;
        }
        for (q = plc.buf + PLC_MAGIC_LEN; q < plc.buf + o && !dup;
             ++q) { /* the same id twice: the first stays (the kept lines read already: only their ids are compared) */
            int id2 = 0;
            while (*q != '\t') id2 = id2 * 10 + (*q++ - '0');
            dup = id2 == id;
            while (*q != '\n') ++q;
        }
        if (!dup) memmove(plc.buf + o, p, (unsigned)(end - p)), o += (unsigned)(end - p), ++ents;
        p = end;
    }
    plc.n = ents ? o : 0;
}

/* The text as the file has it now: read again when the file's state changed. No file (no card, or no cover chosen: the usual case)
 * is a state too, so a call costs one stat; a card put in or taken out, or the file written, changes it. */
static void plc_load(void) {
    unsigned sig[3];
    plc_stat(sig);
    if (plc.have && sig[0] == plc.sig[0] && sig[1] == plc.sig[1] && sig[2] == plc.sig[2]) return;
    plc_read();
}

/* The line of (id, name): its start (and its end, the entry) in plc.buf, 0 when there is none. */
static const char *plc_find(int id, const char *name, plc_t *c, const char **end) {
    char nm[PLC_NAME_MAX];
    const char *p = plc.buf + PLC_MAGIC_LEN, *stop = plc.buf + plc.n;
    if (id < 0 || !name || !*name || !plc.n) return (const char *)0;
    plc_copy(nm, name);
    while (p < stop) {
        int id2;
        plc_t c2;
        const char *nm2, *e2;
        unsigned nl, k;
        if (!plc_line(p, stop, &id2, &c2, &nm2, &nl, &e2)) return (const char *)0;
        if (id2 == id) {
            if (nl != strlen(nm)) return (const char *)0;
            for (k = 0; k < nl; ++k)
                if (nm2[k] != nm[k]) return (const char *)0;
            if (c) *c = c2;
            if (end) *end = e2;
            return p;
        }
        p = e2;
    }
    return (const char *)0;
}

int plc_get(int id, const char *name, plc_t *out) {
    plc_t c;
    plc_load();
    if (!plc_find(id, name, &c, (const char **)0)) return 0;
    if (out) *out = c;
    return 1;
}

static char *plc_put(char *o, const char *s) {
    while (*s) *o++ = *s++;
    return o;
}

static char *plc_puthex(char *o, unsigned v, int digits) {
    int k;
    for (k = 0; k < digits; ++k) *o++ = "0123456789abcdef"[v >> (4 * (digits - 1 - k)) & 15];
    return o;
}

/* The line of an entry at o; its end. */
static char *plc_fmt(char *o, int id, const plc_t *c, const char *name) {
    char dec[11];
    unsigned n = 0, v = (unsigned)id, k;
    int i;
    do dec[n++] = (char)('0' + v % 10), v /= 10;
    while (v);
    while (n) *o++ = dec[--n];
    *o++ = '\t', *o++ = (char)('0' + c->style), *o++ = '\t';
    k = c->flags > 15 ? 2 : 1; /* (flags are one byte) */
    o = plc_puthex(o, c->flags & 255, k), *o++ = '\t';
    o = plc_puthex(o, c->seed, 8), *o++ = '\t';
    for (i = 0; i < c->nt; ++i) {
        if (i) *o++ = ' ';
        o = plc_puthex(o, c->tones[i] & 255, 2), o = plc_puthex(o, c->tones[i] >> 8 & 255, 2),
        o = plc_puthex(o, c->tones[i] >> 16 & 255, 2);
    }
    *o++ = '\t';
    o = plc_put(o, name);
    *o++ = '\n';
    return o;
}

/* plc.buf as the file; 0 when written. A failed write leaves the file as it was and the text is read again from it. */
static int plc_save(void) {
    if (m1_card_write(CARD_DIR, PLC_FILE, plc.buf, plc.n, (const void *)0, 0) < 0) return -1;
    plc.have = 1;
    plc_stat(plc.sig); /* the text just written is what the file holds */
    return 0;
}

/* Takes the line at p..e out of the text. */
/* (the header alone stays when the last line goes: an empty file) */
static void plc_cut(const char *p, const char *e) {
    unsigned at = (unsigned)(p - plc.buf), len = (unsigned)(e - p);
    memmove(plc.buf + at, plc.buf + at + len, plc.n - at - len);
    plc.n -= len;
}

/* Puts the entry at the end of the text; 0 when there is no room (a file at its size or PL_MAX lines). */
static int plc_add(int id, const plc_t *c, const char *name) {
    char line[48 + PLC_NAME_MAX];
    unsigned n = 0, k;
    const char *p = plc.buf + PLC_MAGIC_LEN;
    for (; p < plc.buf + plc.n; ++n) {
        int id2;
        plc_t c2;
        const char *nm, *e;
        unsigned nl;
        if (!plc_line(p, plc.buf + plc.n, &id2, &c2, &nm, &nl, &e)) return 0;
        p = e;
    }
    if (n >= PL_MAX) return 0;
    k = (unsigned)(plc_fmt(line, id, c, name) - line);
    if (!plc.n) memcpy(plc.buf, PLC_MAGIC, PLC_MAGIC_LEN), plc.n = PLC_MAGIC_LEN;
    if (plc.n + k > PLC_FILE_MAX) return 0;
    memcpy(plc.buf + plc.n, line, k), plc.n += k;
    return 1;
}

/* An entry of this id under another name (a deleted playlist's, its id reused): out of the text. */
static void plc_cut_id(int id) {
    const char *p = plc.buf + PLC_MAGIC_LEN, *stop = plc.buf + plc.n;
    while (p < stop) {
        int id2;
        plc_t c2;
        const char *nm, *e;
        unsigned nl;
        if (!plc_line(p, stop, &id2, &c2, &nm, &nl, &e)) return;
        if (id2 == id) {
            plc_cut(p, e);
            return;
        }
        p = e;
    }
}

/* The seed a playlist gets when its first cover is stored: from the id and the (normalised) name. */
static unsigned plc_new_seed(int id, const char *nm) {
    unsigned seed = (m1_fnv(FNV_SEED, nm) ^ (unsigned)id) * FNV_PRIME;
    return seed | !seed;
}

unsigned plc_seed(int id, const char *name) {
    char nm[PLC_NAME_MAX];
    plc_t c;
    if (plc_get(id, name, &c)) return c.seed;
    plc_copy(nm, name ? name : "");
    return plc_new_seed(id, nm);
}

int plc_set(int id, const char *name, int style, unsigned flags, const unsigned *tones, int nt) {
    char nm[PLC_NAME_MAX];
    plc_t c, old;
    const char *at, *end;
    int i;
    if (id < 0 || !name || !*name || style < 0 || style > PLC_STYLE_BAND || nt < 0 || (nt && !tones)) return -1;
    plc_copy(nm, name);
    if (!*nm) return -1;
    plc_load();
    if (style == PLC_STYLE_ALBUMS) {
        at = plc_find(id, nm, (plc_t *)0, &end);
        if (!at) return 0;
        plc_cut(at, end);
        return plc_save() == 0 ? 0 : (plc_read(), -1);
    }
    if (!m1_card_mounted()) return -1;
    if (nt > 3) nt = 3;
    c.style = style, c.flags = flags & 255, c.nt = nt;
    for (i = 0; i < 3; ++i) c.tones[i] = i < nt ? 0xff000000u | (tones[i] & 0xffffff) : 0;
    at = plc_find(id, nm, &old, &end);
    if (at) {
        c.seed = old.seed;
        plc_cut(at, end);
    } else {
        c.seed = plc_new_seed(id, nm);
        plc_cut_id(id);
    }
    c.sig = plc_sig(&c);
    if (!plc_add(id, &c, nm) || plc_save() != 0) {
        plc_read();
        return -1;
    }
    return 0;
}

int plc_rename(int id, const char *old, const char *name) {
    char nm[PLC_NAME_MAX];
    plc_t c;
    const char *at, *end;
    if (id < 0 || !old || !*old || !name || !*name) return 0;
    plc_copy(nm, name);
    plc_load();
    at = plc_find(id, old, &c, &end);
    if (!at || !*nm) return 0;
    plc_cut(at, end);
    if (!plc_add(id, &c, nm) || plc_save() != 0) {
        plc_read();
        return 0;
    }
    return 1;
}

int plc_forget(int id, const char *name) {
    const char *at, *end;
    plc_load();
    at = plc_find(id, name, (plc_t *)0, &end);
    if (!at) return 0;
    plc_cut(at, end);
    if (plc_save() != 0) {
        plc_read();
        return 0;
    }
    return 1;
}
