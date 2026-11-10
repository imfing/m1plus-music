/* M1+ Music preset page: a preset's frequency response, preamp and bands, read only (docs/modules/peq.md "Preset page").
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * Opened by a row of the Presets page (patch/peqlib.c): peqpage_show parses the file of the card's EQ folder (the Equalizer's own parser, so the page shows exactly the bands the
 * player has) and opens ui/m1plus_peqpage.bin through patch/m1plus.c open_page, which calls peqpage_opened. A cards page (docs/modules/settings.md): the graph card, the Preamp row, a Bands header and one
 * two-line row per band, a note under them when the parser skipped lines, and the Delete Preset card (its confirm, then peq_delete and back). Nothing here runs a timer or hooks anything.
 *
 * The graph is drawn once, as the page opens: peq_compile at 48 kHz, peq_response of the left channel (no preamp) at one frequency per pixel column (GR_PW of them, 20 Hz .. 20 kHz, GR_DECADE per decade),
 * the dB range 12, 18 or 24 (the first that holds the curve; a curve past 24 is clamped), then one GR_W x GR_H bitmap, the card baked into it (its rounded corners in the alpha, the grid, the faint fill
 * down to 0 dB, a thin white line, antialiased) and then blitted by the graph view's EVT_BEFORE_PAINT (the view's own background is transparent, so the labels, its children, are painted over the bitmap).
 * Painting is one canvas_draw_image. The bitmap is freed with the page.
 */
#include "offsets.inc"
#include "stock.h"
#include "common.h"
#include "azlist.h"
#include "i18n.h"
#include "peq.h"
#include "peqpage.h"
#include "peqout.h"
#include "peqlib.h"
#include "keyboard.h"
#include "tenband.h"

extern void pod_toast(const char *text); /* patch/shuffle.c: the stock message box */
extern int pod_open_peqpage(void); /* patch/m1plus.c: open_page(POD_PEQP_PAGE) */

#define PP_N PEQ_BANDS
#define PP_RATE 48000
#define MINUS "\xe2\x88\x92" /* U+2212: the sign of a cut */
#define DOT " \xc2\xb7 "
#define GR_GREY_CARD 28 /* #1C1C1C */
#define GR_GREY_GRID 48
#define GR_GREY_ZERO 62
#define GR_GREY_INK 242

#if GR_BANDS != PEQ_BANDS
#error "the preset page's band rows are the engine's bands"
#endif

/* What peqpage_show leaves for the page that opens next (cleared once it is used). */
static struct {
    int ok;
    peq_error err;
    peq_preset p;
    char file[PEQ_NAME];
} pre __attribute__((section(".scratch")));

static struct {
    void *win, *graph, *top, *bot, *note, *note_t, *del, *ren, *gap, *title;
    void *row[PP_N + 1], *label[PP_N + 1], *value[PP_N + 1], *sub[PP_N + 1], *hair[PP_N + 1];
    char piece[PP_N + 1], shown[PP_N + 1], file[PEQ_NAME]; /* the preset's file name (Save, Rename, Delete Preset) */
    peq_graph
        g; /* the graph card: the bitmap, its range and the curve (shared with the 10-Band editor, patch/tenband.c) */
    peq_preset work,
        saved; /* the bands that play (the band page edits them) and the file's own (what Save wrote or the file parsed to) */
    unsigned skipped; /* the lines the parser left out of the file (a Save drops them) */
    int owner; /* the output whose record received this session's live edits, plus 1; 0 before the first edit (peqpage_commit(1) sets it) */
} pg __attribute__((section(".scratch")));

/* ---------------------------------------------------------------------------
 * Numbers
 */
/* 10 * log10(x) to about 1e-5 dB (x = m * 2^k, m in [1, 2): ln m by the atanh series); -120 for x too small. No libm log in the payload. */
__attribute__((noinline)) double pp_db10(double x) {
    int k = 0;
    double z, z2;
    if (!(x > 1e-12)) return -120;
    while (x >= 2) x *= 0.5, ++k;
    while (x < 1) x *= 2, --k;
    z = (x - 1) / (x + 1), z2 = z * z;
    return 4.342944819032518 *
           (2 * z * (1 + z2 * (1.0 / 3 + z2 * (1.0 / 5 + z2 * (1.0 / 7 + z2 * (1.0 / 9))))) + k * 0.6931471805599453);
}

/* v100 (hundredths) as "12", "0.7", "0.89": the digits trimmed of trailing zeros. Returns the length. */
static unsigned pp_dec(char *s, unsigned v100) {
    unsigned w = v100 / 100, f = v100 % 100, n = 0, d = 0;
    char t[12];
    do t[d++] = (char)('0' + w % 10);
    while ((w /= 10) != 0);
    while (d) s[n++] = t[--d];
    if (f) {
        s[n++] = '.';
        s[n++] = (char)('0' + f / 10);
        if (f % 10) s[n++] = (char)('0' + f % 10);
    }
    s[n] = 0;
    return n;
}

/* "0.7", "1.41", "10": a Q in hundredths, the zeros trimmed. */
void pp_qtext(char *out, unsigned size, double q) {
    char num[16];
    pp_dec(num, (unsigned)(q * 100 + 0.5));
    snprintf(out, size, "%s", num);
}

/* "105 Hz", "105.5 Hz", "2 kHz", "1.25 kHz": a frequency from 20 Hz, a tenth of a hertz under 1 kHz, a hundredth of a kilohertz from it. */
__attribute__((noinline)) void pp_freq(char *out, unsigned size, double f) {
    char num[16];
    unsigned hz10 = (unsigned)(f * 10 + 0.5);
    if (hz10 < 10000) {
        pp_dec(num, hz10 * 10);
        snprintf(out, size, "%s Hz", num);
    } else {
        pp_dec(num, (unsigned)(f / 10 + 0.5));
        snprintf(out, size, "%s kHz", num);
    }
}

/* "+4.8 dB", "−2.4 dB" (U+2212), "0.0 dB": a tenth of a decibel, rounded away from zero; plus: the "+" of a boost (a preamp row never needs it). */
__attribute__((noinline)) void pp_gain(char *out, unsigned size, double g, int plus) {
    int g10 = (int)(g * 10 + (g < 0 ? -0.5 : 0.5)), a = g10 < 0 ? -g10 : g10;
    snprintf(out, size, "%s%d.%d dB", g10 < 0 ? MINUS : g10 > 0 && plus ? "+" : "", a / 10, a % 10);
}

/* "Low shelf · Q 0.7", with " · L" / " · R" for a band of one side. */
__attribute__((noinline)) void pp_line(char *out, unsigned size, const peq_band *b) {
    char q[16];
    const char *kind = b->type == 1 ? TR("Low shelf") : b->type == 2 ? TR("High shelf") : TR("Peak");
    pp_dec(q, (unsigned)(b->q * 100 + 0.5));
    snprintf(out, size, "%s" DOT "Q %s%s", kind, q, b->enabled == 2 ? DOT "L" : b->enabled == 3 ? DOT "R" : "");
}

/* The preamp row's value: "Auto · −6.0 dB" (the cut the player applies at 48 kHz) or the file's own "−6.0 dB". */
__attribute__((noinline)) void pp_preamp(char *out, unsigned size, const peq_preset *p) {
    char g[24];
    if (p->automatic == 1) {
        double lin = peq_preamp_gain(p, PP_RATE);
        pp_gain(g, sizeof g, pp_db10(lin * lin), 1);
        snprintf(out, size, "%s" DOT "%s", TR("Auto"), g);
    } else
        pp_gain(out, size, p->preamp, 1);
}

/* ---------------------------------------------------------------------------
 * The graph
 */
/* The curve, dB of the left channel at each column's frequency (the card's pixel x GR_PX0 + c is 20 Hz * 10^((c + 0.5) / GR_DECADE)), and the range that holds it. */
void peq_graph_curve(peq_graph *g, const peq_preset *p) {
    peq_engine *e = calloc(1, sizeof *e);
    double top = 0;
    int c;
    if (e && peq_compile(p, PP_RATE, e)) {
        for (c = 0; c < GR_PW; ++c) {
            double l, r, d;
            peq_response(e, PP_RATE, 20 * pow(10, (c + 0.5) / GR_DECADE), &l, &r);
            d = pp_db10(l);
            g->db[c] = (float)d;
            if (d < 0) d = -d;
            if (d > top) top = d;
        }
    }
    free(e);
    g->range = top <= 12.0 ? 12 : top <= 18.0 ? 18 : 24;
}

static double pg_clamp(double v, double lo, double hi) { return v < lo ? lo : v > hi ? hi : v; }

/* The card: its fill and rounded corners, the grid, the curve, one grey and one alpha a pixel. */
static void pg_render(const peq_graph *g, unsigned *px) {
    static const int grid_x[3] = {58, 141, 224}; /* 100 Hz, 1 kHz, 10 kHz: GR_DECADE * log10(f / 20), rounded */
    float yc[GR_PW];
    double y0 = GR_PY0 + GR_PH / 2 + 0.5, half = GR_PH / 2.0;
    int x, y, c;
    for (c = 0; c < GR_PW; ++c)
        yc[c] = (float)pg_clamp(y0 - g->db[c] * half / g->range, GR_PY0 + 0.5, GR_PY0 + GR_PH - 0.5);
    for (y = 0; y < GR_H; ++y)
        for (x = 0; x < GR_W; ++x) {
            double v = GR_GREY_CARD, a = 1;
            int in_plot = y >= GR_PY0 && y < GR_PY0 + GR_PH, col = x - GR_PX0;
            if (x < GR_CARD_R || x >= GR_W - GR_CARD_R) {
                if (y < GR_CARD_R || y >= GR_H - GR_CARD_R) {
                    double dx = x + 0.5 - (x < GR_CARD_R ? GR_CARD_R : GR_W - GR_CARD_R),
                           dy = y + 0.5 - (y < GR_CARD_R ? GR_CARD_R : GR_H - GR_CARD_R);
                    a = pg_clamp(GR_CARD_R - __builtin_sqrt(dx * dx + dy * dy) + 0.5, 0, 1);
                }
            }
            if (in_plot && col >= 0 && col < GR_PW) {
                double lo, hi, ov;
                if (y == GR_PY0 || y == GR_PY0 + GR_PH - 1) v = GR_GREY_GRID;
                if (y == GR_PY0 + GR_PH / 2) v = GR_GREY_ZERO;
                if (col == grid_x[0] || col == grid_x[1] || col == grid_x[2]) v = GR_GREY_GRID;
                lo = yc[col] < y0 ? yc[col] : y0, hi = yc[col] < y0 ? y0 : yc[col];
                ov = pg_clamp((hi < y + 1 ? hi : y + 1) - (lo > y ? lo : y), 0, 1);
                v += (GR_GREY_INK - v) * 0.14 * ov; /* the faint fill between the curve and 0 dB */
                {
                    double s = ((col + 1 < GR_PW ? yc[col + 1] : yc[col]) - (col ? yc[col - 1] : yc[col])) /
                               (col && col + 1 < GR_PW ? 2 : 1);
                    double d = (y + 0.5 - yc[col]) / __builtin_sqrt(1 + s * s), cov;
                    if (d < 0) d = -d;
                    cov = pg_clamp(1.25 - d, 0, 1); /* a 1.5 px line */
                    v += (GR_GREY_INK - v) * cov;
                }
            }
            px[y * GR_W + x] = (unsigned)(a * 255 + 0.5) << 24 | (unsigned)(v + 0.5) * 0x010101u;
        }
}

/* The bitmap of the curve g holds: made the first time, drawn again in place after (the editor's drag). 1 when it is there; 0 with no memory (the card stays empty, or as it was). */
int peq_graph_draw(peq_graph *g) {
    unsigned *px;
    void *b = g->bmp ? g->bmp : bitmap_create_ex(GR_W, GR_H, GR_W * 4, BITMAP_RGBA8888);
    if (!b) return 0;
    px = (unsigned *)bitmap_lock_buffer_for_write(b);
    if (!px || bitmap_get_line_length(b) != (unsigned)(GR_W * 4)) {
        if (px) bitmap_unlock_buffer(b);
        if (!g->bmp) bitmap_destroy(b);
        return 0;
    }
    pg_render(g, px);
    bitmap_unlock_buffer(b);
    g->bmp = b;
    return 1;
}

void peq_graph_free(peq_graph *g) {
    if (g->bmp) bitmap_destroy(g->bmp);
    g->bmp = (void *)0;
}

/* One 1:1 blit of bmp (w x h) at x, y: the graph card, the editors' cards, tracks and thumbs, the Auto EQ glyphs. */
void peq_blit(void *canvas, void *bmp, int w, int h, int x, int y) {
    int src[4], dst[4];
    src[0] = src[1] = 0, src[2] = w, src[3] = h;
    dst[0] = x, dst[1] = y, dst[2] = w, dst[3] = h;
    canvas_draw_image(canvas, bmp, src, dst);
}

/* A label's text colour (rgb, "#rrggbb") in the states it can show. */
void peq_label_colors(void *w, const char *rgb) {
    static const char *const prop[3] = {"style:normal:text_color", "style:disable:text_color",
                                        "style:focused:text_color"};
    int s;
    for (s = 0; s < 3; ++s) widget_set_prop_str(w, prop[s], rgb);
}

/* The graph view's EVT_BEFORE_PAINT: one blit of the bitmap at the card's x (nothing with no bitmap or no canvas). */
void peq_graph_paint(const peq_graph *g, void *e) {
    void *canvas = e ? *(void **)((char *)e + EVENT_PAINT_CANVAS) : (void *)0;
    if (!canvas || !g->bmp) return;
    peq_blit(canvas, g->bmp, GR_W, GR_H, GR_CARD_X, 0);
}

/* The scale's ends: +R at the top, -R (U+2212) at the bottom. */
void peq_graph_scale(const peq_graph *g, void *top, void *bot) {
    char text[8];
    snprintf(text, sizeof text, "+%d", g->range);
    widget_set_text_utf8(top, text);
    snprintf(text, sizeof text, MINUS "%d", g->range);
    widget_set_text_utf8(bot, text);
}

/* ---------------------------------------------------------------------------
 * Editing: the working preset, the file it is written to
 */
static unsigned pg_len(const char *s) {
    unsigned n = 0;
    while (s[n]) ++n;
    return n;
}

/* A band for band: the same bands, the same preamp (an edited preset differs from its file by exactly these). */
static int pg_same(const peq_preset *a, const peq_preset *b) {
    int i;
    if (a->count != b->count || a->preamp != b->preamp || a->balance != b->balance || a->automatic != b->automatic)
        return 0;
    for (i = 0; i < a->count; ++i) {
        const peq_band *x = &a->bands[i], *y = &b->bands[i];
        if (x->enabled != y->enabled || x->type != y->type || x->frequency != y->frequency || x->gain != y->gain ||
            x->q != y->q)
            return 0;
    }
    return 1;
}

/* The bands that play, first: an OFF filter that parsed is kept in the record but never plays (the page's rows are the engine's own list). */
static void pg_compact(peq_preset *p) {
    int i, n = 0;
    for (i = 0; i < p->count && n < PP_N; i++)
        if (p->bands[i].enabled) p->bands[n++] = p->bands[i];
    p->count = n;
}

/* A number to at most four decimals, trailing zeros and a lone point dropped ("105", "0.7071", "-3.5"); the digits are made with integers (no libm, no 64-bit). Returns the length. */
unsigned pp_num(char *out, double v) {
    unsigned n = 0, ip, fr, d, k;
    char t[12];
    int neg = v < 0;
    if (neg) v = -v;
    ip = (unsigned)v;
    fr = (unsigned)((v - ip) * 10000 + 0.5);
    if (fr >= 10000) ++ip, fr -= 10000;
    if (neg && (ip || fr)) out[n++] = '-';
    d = 0;
    do t[d++] = (char)('0' + ip % 10);
    while ((ip /= 10) != 0);
    while (d) out[n++] = t[--d];
    if (fr) {
        out[n++] = '.';
        for (k = 1000; k; k /= 10) {
            out[n++] = (char)('0' + fr / k % 10);
            if (!(fr % k)) break;
        }
    }
    out[n] = 0;
    return n;
}

/* The preset as APO text, which peq_parse reads back to the same bands: PK / LSC / HSC (the centre form, so a shelf's frequency is not moved), the Q of every band, "Preamp:" only for a preset that has
 * one (automatic 2; a balance is the two sides' preamps, the larger one 0), the bands in order with a "Channel:" line wherever the side changes. stamp: a first comment kept as it was ("# AutoEq: ..."), or null. 0 when it does not fit. */
static unsigned pg_text(char *out, unsigned size, const peq_preset *p, const char *stamp) {
    static const char *const type[3] = {"PK", "LSC", "HSC"};
    char f[16], g[16], q[16];
    unsigned n = 0;
    int i, scope = 1, line = 0;
#define PUT(...) \
    do { \
        int w_ = snprintf(out + n, size - n, __VA_ARGS__); \
        if (w_ < 0 || (unsigned)w_ >= size - n) return 0; \
        n += (unsigned)w_; \
    } while (0)
    if (stamp && stamp[0]) PUT("%s\n", stamp);
    if (p->automatic == 2) {
        pp_num(g, p->preamp);
        PUT("Preamp: %s dB\n", g);
        if (p->balance != 0) {
            pp_num(g, p->balance > 0 ? -p->balance : p->balance);
            PUT("Channel: %s\nPreamp: %s dB\nChannel: all\n", p->balance > 0 ? "L" : "R", g);
        }
    }
    for (i = 0; i < p->count; ++i) {
        const peq_band *b = &p->bands[i];
        if (!b->enabled) continue;
        if (b->enabled != scope) {
            scope = b->enabled;
            PUT("Channel: %s\n", scope == 1 ? "all" : scope == 2 ? "L" : "R");
        }
        pp_num(f, b->frequency);
        pp_num(g, b->gain);
        pp_num(q, b->q);
        PUT("Filter %d: ON %s Fc %s Hz Gain %s dB Q %s\n", ++line, type[b->type >= 0 && b->type < 3 ? b->type : 0], f,
            g, q);
    }
#undef PUT
    return n;
}

/* The first line a Save writes over a file: an AutoEq stamp becomes "# AutoEq edited: <path>" (the file is no longer the download, so the AutoEq page does not find it as saved; a comment both parsers skip), an edited one is kept; else empty. */
static unsigned pg_pre(const char *s, const char *pre) {
    unsigned i = 0;
    while (pre[i] && s[i] == pre[i]) ++i;
    return pre[i] ? 0 : i;
}

static void pg_stamp(const char *path, char *out, unsigned size) {
    char buf[260];
    unsigned n, i, o = 0, from = 0;
    void *f = fopen(path, "rb");
    out[0] = 0;
    if (!f) return;
    n = fread(buf, 1, sizeof buf - 1, f);
    fclose(f);
    buf[n] = 0;
    from = pg_pre(buf, "# AutoEq: ");
    if (!from) from = pg_pre(buf, "# AutoEq edited: ");
    if (!from) return;
    o = snprintf(out, size, "# AutoEq edited: ");
    for (i = from; buf[i] && buf[i] != '\n' && buf[i] != '\r' && o < size - 1; ++i) out[o++] = buf[i];
    out[o] = 0;
}

#define PG_TMP PEQ_DIR "/.save.tmp"
/* Writes the preset to path, atomically: a temp file in the same folder, fsynced, parsed back (it must be a preset the engine reads), then renamed over path. On success *back is what the file now holds (its bands compacted);
 * on failure nothing of path is touched and the temp file is gone. */
static int pg_store(const char *path, const peq_preset *p, const char *stamp, peq_preset *back, peq_error *err) {
    char *text = calloc(1, PEQ_FILE_LIMIT + 1);
    unsigned len;
    int fd, ok = 0;
    if (!text) return 0;
    len = pg_text(text, PEQ_FILE_LIMIT, p, stamp);
    if (len) {
        mkdir(PEQ_DIR, 0755);
        fd = open(PG_TMP, O_WRONLY | O_CREAT | O_TRUNC, 0644);
        if (fd >= 0) {
            ok = write(fd, text, len) == (int)len && fsync(fd) == 0;
            ok = close(fd) == 0 && ok;
        }
    }
    free(text);
    ok = ok && peq_import_file(PG_TMP, back, err) && rename(PG_TMP, path) == 0;
    if (!ok)
        unlink(PG_TMP);
    else
        pg_compact(back);
    return ok;
}

/* A name typed for a file: the characters a card cannot hold become "-", the ends are trimmed, a ".txt" the user typed is dropped, at most PEQ_NAME - 5 bytes (cut on a character boundary) so that the file name, ".txt" and the NUL fit
 * PEQ_NAME. Returns the length; 0 when nothing is left. out needs PEQ_NAME bytes. */
static unsigned pg_clean(char *out, const char *text) {
    unsigned n = 0, i = 0;
    while (text[i] == ' ') ++i;
    for (; text[i] && n < PEQ_NAME - 5; ++i) {
        unsigned char c = (unsigned char)text[i];
        out[n++] = (char)(c < 0x20 || c == '\\' || c == '/' || c == ':' || c == '*' || c == '?' || c == '"' ||
                                  c == '<' || c == '>' || c == '|'
                              ? '-'
                              : c);
    }
    if (text[i] && ((unsigned char)text[i] & 0xc0) == 0x80) { /* cut inside a character: drop it whole */
        while (n && ((unsigned char)out[n - 1] & 0xc0) == 0x80) --n;
        if (n) --n;
    }
    for (;;) {
        while (n && (out[n - 1] == ' ' || out[n - 1] == '.')) --n;
        out[n] = 0;
        if (n >= 4 && !strcasecmp(out + n - 4, ".txt"))
            n -= 4;
        else
            break;
    }
    if (n && out[0] == '.') out[0] = '_';
    out[n] = 0;
    return n;
}

/* ---------------------------------------------------------------------------
 * The page
 */
static void pg_show(void *w, int on) {
    widget_set_visible(w, on, 0);
    widget_set_sensitive(w, on);
}

/* The rows and the graph from the working preset (the page opening, and each time it is back in front after the band page). */
static void pg_fill(void) {
    int i, n = pg.work.count;
    char text[96];
    pp_preamp(text, sizeof text, &pg.work);
    widget_set_text_utf8(pg.value[0], text);
    for (i = 1; i <= n; i++) {
        int piece = n == 1 ? 0 : i == 1 ? 1 : i == n ? 3 : 2;
        pp_freq(text, sizeof text, pg.work.bands[i - 1].frequency);
        widget_set_text_utf8(pg.label[i], text);
        pp_gain(text, sizeof text, pg.work.bands[i - 1].gain, 1);
        widget_set_text_utf8(pg.value[i], text);
        pp_line(text, sizeof text, &pg.work.bands[i - 1]);
        widget_set_text_utf8(pg.sub[i], text);
        peq_piece_set(pg.row[i], &pg.piece[i], piece, 0);
        if (pg.hair[i]) widget_set_visible(pg.hair[i], i < n, 0);
        if (!pg.shown[i]) pg_show(pg.row[i], 1), pg.shown[i] = 1;
    }
    peq_graph_curve(&pg.g, &pg.work);
    peq_graph_scale(&pg.g, pg.top, pg.bot);
    peq_graph_draw(&pg.g); /* none (no memory): the card stays empty, the rows are there */
    widget_invalidate_force(pg.graph, (void *)0);
}

/* The note about skipped lines (their count is the file's: a Save writes none of them back), the gap before the Rename / Delete card when there is none. */
static void pg_note(void) {
    char text[96];
    if (pg.skipped) {
        pod_fmt(text, sizeof text,
                TR(pg.skipped == 1 ? "%d line not supported was skipped." : "%d lines not supported were skipped."),
                (int)pg.skipped);
        widget_set_text_utf8(pg.note_t, text);
    }
    widget_set_visible(pg.note, pg.skipped != 0, 0);
    if (pg.gap) widget_set_visible(pg.gap, pg.skipped == 0, 0);
}

/* The title: the file's name without its .txt. */
static void pg_title(void) {
    char shown[PEQ_NAME];
    peq_shown(shown, sizeof shown, pg.file);
    az_fit(pg.title, shown);
}

static int pg_on_paint(void *ctx, void *e) {
    (void)ctx;
    if (pg.win) peq_graph_paint(&pg.g, e);
    return RET_OK;
}

static int pg_on_destroy(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    peq_graph_free(&pg.g);
    memset(&pg, 0, sizeof pg);
    return RET_OK;
}

/* Back in front (the band page was open, or the keyboard): the rows again from the working preset. */
static int pg_on_fg(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (!pg.win) return RET_OK;
    pg_fill();
    return RET_OK;
}

/* Whether the working preset differs from the file (an edit not saved): the band page asks before it closes. */
int peqpage_edited(void) { return pg.win && !pg_same(&pg.work, &pg.saved); }

/* The preset's name as the pages show it (without .txt). */
void peqpage_name(char *out, unsigned size) {
    out[0] = 0;
    if (pg.win) peq_shown(out, size, pg.file);
}

/* The working preset for the band page (patch/peqband.c), null with no Preset page up. */
peq_preset *peqpage_work(void) { return pg.win ? &pg.work : (peq_preset *)0; }

/* What the band page changed is what plays now: the working preset in the record as the preset of this file (play 1: stock's Equalizer turned on and the player told, peq_commit; play 0, for a Save, a Save As or a Revert: the record only, and the
 * player told when the Equalizer is on, peq_record). 1 when it was saved. */
int peqpage_commit(int play) {
    peq_state s;
    if (!pg.win) return 0;
    peq_state_load(&s);
    s.mode = PEQ_FILE;
    s.preset = pg.work;
    memset(s.name, 0, sizeof s.name);
    memcpy(s.name, pg.file, pg_len(pg.file) + 1);
    if (!play) return peq_record(&s);
    if (!peq_commit(&s)) return 0;
    pg.owner =
        peqout_session(); /* a live edit goes to the output playing now: that output owns the session from here */
    return 1;
}

/* ---------------------------------------------------------------------------
 * Save, Save As, Revert, Rename (the band page's unsaved-changes dialog asks for the first three: patch/peqband.c)
 */
/* The file's own preset again (it may have been edited elsewhere, or by this page): the working copy, what is saved, the skipped count. 0 when it no longer parses. */
static int pg_load(void) {
    char path[sizeof(PEQ_DIR) + PEQ_NAME + 1];
    peq_error err;
    peq_preset p;
    snprintf(path, sizeof path, "%s/%s", PEQ_DIR, pg.file);
    if (!peq_import_file(path, &p, &err)) return 0;
    pg_compact(&p);
    pg.saved = pg.work = p;
    pg.skipped = err.skipped;
    return 1;
}

/* After the file changed under the page: what plays is the file's preset, then the rows, the note and the title (only once that was written: a failure leaves the page undrawn for the caller to restore). */
static int pg_refresh(const char *prev, int active) {
    if (!peqout_away(
            pg.owner)) { /* else the record playing now is not this session's (peqout_sync filed the edits in the session output's slot) */
        if (!peqpage_commit(0)) return 0; /* the session keeps its output until the record is written */
        pg.owner = 0;
        pg_note();
        pg_title();
        pg_fill();
        return 1;
    }
    /* Another output plays now: its record and playback stay as they are. The session output's slot, when it still names the file `prev`, takes the file's preset (as `file`); the record
     * playing now takes it only when it names this file (a Save changed that file; active 0 for a Don't Save, which changed nothing). */
    if (!peqout_session_filed(pg.owner, prev, pg.file, &pg.work)) {
        pod_toast(TR("Not saved"));
        return 0;
    }
    pg.owner = 0;
    pg_note();
    pg_title();
    pg_fill();
    return active ? peqout_playing_filed(pg.file, &pg.work) : 1;
}

/* Don't Save: the file's preset plays again. 1 when it was read. */
int peqpage_revert(void) {
    peq_preset work, saved;
    int skipped;
    if (!pg.win) return 0;
    work = pg.work, saved = pg.saved, skipped = pg.skipped;
    if (!pg_load()) {
        pod_toast(TR("Cannot read this preset"));
        return 0;
    }
    if (!pg_refresh(
            pg.file,
            0)) { /* the record could not be replaced (peq_record said "Not saved"): the edit still plays, so the page keeps it unsaved */
        pg.work = work, pg.saved = saved, pg.skipped = skipped;
        return 0;
    }
    return 1;
}

void peqpage_named(const char *text);

/* Save: the file is written whole from the working preset (same name; an AutoEq stamp becomes the edited marker). The lines the parser skipped are not written back. 1 when written; else the message box said so. */
int peqpage_save(void) {
    char path[sizeof(PEQ_DIR) + PEQ_NAME + 1], stamp[300];
    peq_preset back, work = pg.work, saved = pg.saved;
    int skipped = pg.skipped;
    peq_error err;
    snprintf(path, sizeof path, "%s/%s", PEQ_DIR, pg.file);
    pg_stamp(path, stamp, sizeof stamp);
    if (!pg.win) return 0;
    if (!pg_store(path, &pg.work, stamp, &back, &err)) {
        pod_toast(TR("Not saved"));
        return 0;
    }
    pg.saved = pg.work = back;
    pg.skipped = 0;
    if (pg_refresh(pg.file, 1)) return 1;
    pg.work = work, pg.saved = saved,
    pg.skipped =
        skipped; /* the file stays written when the record or slot was not ("Not saved"): the edit stays unsaved, so Back asks again and a Save retries */
    return 0;
}

/* Save As New: the name entry (initial "<name> (Edited)"), whose Done is peqpage_named. */
void peqpage_saveas(void) {
    char shown[PEQ_NAME], init[PEQ_NAME + 24];
    if (!pg.win) return;
    peq_shown(shown, sizeof shown, pg.file);
    snprintf(init, sizeof init, "%s (%s)", shown, TR("Edited"));
    keyboard_open(TR("Save As"), "", init, peqpage_named, (kb_cancel_fn)0, KB_DONE);
}

/* The name entry's Done for a new preset file (Save As here, Save as Preset in the 10-Band editor): the typed name cleaned (pg_clean) with ".txt" added into file (PEQ_NAME bytes); an existing name is refused ("Name already in use"), a
 * full list too ("Preset limit reached"); p is written to the new file (pg_store: atomic, parsed back; "Not saved" when that fails) and back is what the file holds. 1 when written; 0 otherwise (nothing typed: nothing said). */
int peq_save_new(const char *text, const peq_preset *p, char *file, peq_preset *back) {
    char name[PEQ_NAME], path[sizeof(PEQ_DIR) + PEQ_NAME + 1];
    peq_error err;
    int total = 0;
    unsigned len;
    if (!(len = pg_clean(name, text))) return 0;
    memcpy(name + len, ".txt", 5);
    snprintf(path, sizeof path, "%s/%s", PEQ_DIR, name);
    if (access(path, 0) == 0) {
        pod_toast(TR("Name already in use"));
        return 0;
    }
    peq_list((char (*)[PEQ_NAME])0, 0, &total);
    if (total >= PQ_ROWS) {
        pod_toast(TR("Preset limit reached"));
        return 0;
    }
    if (!pg_store(path, p, (const char *)0, back, &err)) {
        pod_toast(TR("Not saved"));
        return 0;
    }
    memcpy(file, name, len + 5);
    return 1;
}

/* The keyboard's Done for Save As: a new file in the card's EQ folder (peq_save_new), and the page shows that preset now (the edited one plays; the
 * original file is as it was). Not static: the tests call it as the keyboard would. */
__attribute__((used, retain)) void peqpage_named(const char *text) {
    char file[PEQ_NAME], prev[PEQ_NAME], path[sizeof(PEQ_DIR) + PEQ_NAME + 1];
    peq_preset back, work = pg.work, saved = pg.saved;
    int skipped = pg.skipped;
    if (!pg.win || !peq_save_new(text, &pg.work, file, &back)) return;
    memcpy(prev, pg.file, pg_len(pg.file) + 1);
    memcpy(pg.file, file, pg_len(file) + 1);
    pg.saved = pg.work = back;
    pg.skipped = 0;
    if (!pg_refresh(
            prev,
            0)) { /* the record or slot was not written ("Not saved"): the new file goes, the page stays on the old one with its edit unsaved */
        snprintf(path, sizeof path, "%s/%s", PEQ_DIR, file);
        unlink(path);
        memcpy(pg.file, prev, pg_len(prev) + 1);
        pg.work = work, pg.saved = saved, pg.skipped = skipped;
    }
}

/* The keyboard's Done for Rename Preset: the file takes the new name (an existing one is refused; the same name in another case is allowed), the record follows when this is the preset that plays. */
__attribute__((used, retain)) void peqpage_renamed(const char *text) {
    char name[PEQ_NAME], from[sizeof(PEQ_DIR) + PEQ_NAME + 1], to[sizeof(PEQ_DIR) + PEQ_NAME + 1];
    unsigned pg_clean_len;
    if (!pg.win || !(pg_clean_len = pg_clean(name, text))) return;
    memcpy(name + pg_clean_len, ".txt", 5);
    if (!strcmp(name, pg.file)) return;
    snprintf(from, sizeof from, "%s/%s", PEQ_DIR, pg.file);
    snprintf(to, sizeof to, "%s/%s", PEQ_DIR, name);
    if (strcasecmp(name, pg.file) != 0 && access(to, 0) == 0) {
        pod_toast(TR("Name already in use"));
        return;
    }
    if (rename(from, to) != 0) {
        pod_toast(TR("Not saved"));
        return;
    }
    peq_renamed(pg.file, name);
    memcpy(pg.file, name, pg_len(name) + 1);
    pg_title();
}

static int pg_on_rename(void *ctx, void *e) {
    char shown[PEQ_NAME];
    (void)ctx;
    (void)e;
    if (!pg.win) return RET_OK;
    peq_shown(shown, sizeof shown, pg.file);
    keyboard_open(TR("Rename Preset"), "", shown, peqpage_renamed, (kb_cancel_fn)0, KB_DONE);
    return RET_OK;
}

/* A band row opens the band page on that band. */
static int pg_on_band(void *ctx, void *e) {
    (void)e;
    if (pg.win) peqband_open((int)(long)ctx);
    return RET_OK;
}

/* The stock confirm dialog (patch/playlists.c pl_ask): modal; CONFIRM_YES (0xa) is Yes. */
int peq_ask(const char *text) {
    struct {
        int kind, ms;
        char text[MSGINFO_TEXT], text2[MSGINFO_TEXT];
    } info;
    unsigned i;
    memset(&info, 0, sizeof info);
    info.kind = 1;
    for (i = 0; text[i] && i < sizeof info.text - 1; ++i) info.text[i] = text[i];
    return navigator_to_with_context("dialog/confirminfo_dialog", &info) == CONFIRM_YES;
}

/* Delete Preset: the stock confirm; Yes deletes the file (peq_delete: the record and the Equalizer follow when it was the one that played),
 * then back to the Presets page, which reads the card again. A file that cannot be removed says so and the page stays. */
static int pg_on_delete(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (!pg.win || !pg.file[0]) return RET_OK;
    if (!peq_ask(TR("Delete Preset?"))) return RET_OK;
    if (!peq_delete(pg.file)) {
        pod_toast(TR("Failed To Delete Preset"));
        return RET_OK;
    }
    window_close(
        pg.win); /* this page, not the top window: the confirm dialog is still closing, so a navigator_back would go to it */
    return RET_OK;
}

/* Parses the preset first, so that a file that went away or no longer parses opens nothing. */
int peqpage_show(const char *file) {
    char path[sizeof(PEQ_DIR) + PEQ_NAME + 1];
    unsigned n = 0;
    while (file[n]) ++n;
    if (n >= PEQ_NAME) return 0;
    memset(&pre, 0, sizeof pre);
    snprintf(path, sizeof path, "%s/%s", PEQ_DIR, file);
    if (!peq_import_file(path, &pre.p, &pre.err)) {
        pod_toast(TR("Cannot read this preset"));
        return 0;
    }
    memcpy(pre.file, file, n + 1);
    pre.ok = 1;
    if (pod_open_peqpage() != 0) {
        memset(&pre, 0, sizeof pre);
        return 0;
    }
    return 1;
}

void peqpage_opened(void *win) {
    int i;
    char name[24];
    peq_state st;
    if (!pre.ok) return;
    memset(&pg, 0, sizeof pg);
    memcpy(pg.file, pre.file, sizeof pg.file);
    pg.graph = widget_lookup(win, "pod_graph", 1);
    pg.top = widget_lookup(win, "pod_gr_top", 1);
    pg.bot = widget_lookup(win, "pod_gr_bot", 1);
    pg.note = widget_lookup(win, "pod_note0", 1);
    pg.note_t = pg.note ? widget_lookup(pg.note, "pod_note0_t", 1) : (void *)0;
    pg.title = widget_lookup(win, "label_title", 1);
    for (i = 0; i <= PP_N; i++) {
        snprintf(name, sizeof name, "pod_row%d", i);
        pg.row[i] = widget_lookup(win, name, 1);
        snprintf(name, sizeof name, "pod_value%d", i);
        pg.value[i] = widget_lookup(win, name, 1);
        if (i) {
            snprintf(name, sizeof name, "pod_label%d", i);
            pg.label[i] = widget_lookup(win, name, 1);
            snprintf(name, sizeof name, "pod_sub%d", i);
            pg.sub[i] = widget_lookup(win, name, 1);
        }
        if (!pg.row[i] || !pg.value[i] || (i && (!pg.label[i] || !pg.sub[i]))) goto bad;
        pg.hair[i] = widget_lookup(pg.row[i], "pod_hair", 1); /* the card's last row has none */
    }
    snprintf(name, sizeof name, "pod_row%d",
             PP_N + 1); /* the Rename / Delete Preset card, after the bands and the note */
    pg.del = widget_lookup(win, name, 1);
    snprintf(name, sizeof name, "pod_row%d", PP_N + 2);
    pg.ren = widget_lookup(win, name, 1);
    pg.gap =
        widget_lookup(win, "pod_gap1", 1); /* the space before the Rename / Delete card (hidden while the note shows) */
    if (!pg.graph || !pg.top || !pg.bot || !pg.note || !pg.note_t || !pg.title || !pg.del || !pg.ren) goto bad;
    pg.saved = pre.p;
    pg_compact(&pg.saved);
    pg.work = pg.saved;
    pg.skipped = pre.err.skipped;
    if (peq_state_load(&st) && st.mode == PEQ_FILE &&
        !strcmp(st.name, pg.file)) { /* this preset plays, maybe edited (the record holds what plays) */
        pg.work = st.preset;
        pg_compact(&pg.work);
        pg.owner =
            peqout_session(); /* an earlier session's unsaved edits are in the record of the output playing now */
    }
    pg.win = win;
    memset(&pre, 0, sizeof pre);
    pg_title();
    pg_note();
    pg_fill();
    widget_on(pg.graph, EVT_BEFORE_PAINT, pg_on_paint, (void *)0);
    widget_on(pg.del, EVT_CLICK, pg_on_delete, (void *)0);
    widget_on(pg.ren, EVT_CLICK, pg_on_rename, (void *)0);
    for (i = 1; i <= pg.work.count; i++) widget_on(pg.row[i], EVT_CLICK, pg_on_band, (void *)(long)(i - 1));
    widget_on(win, EVT_WINDOW_TO_FG, pg_on_fg, (void *)0);
    widget_on(win, EVT_DESTROY, pg_on_destroy, (void *)0);
    return;
bad: /* an asset that is not ours */
    memset(&pg, 0, sizeof pg);
    memset(&pre, 0, sizeof pre);
}
