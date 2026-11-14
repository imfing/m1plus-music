/* M1+ Music Now Playing, the lyrics page: our own line layout over the stock lyric loader.
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE). The look and motion are inspired by amll-dev/applemusic-like-lyrics (the current line anchored
 * above the middle, the other lines fading with their distance, each line starting its move a little after the one before it and settling with a
 * small overshoot), without its blur: the X2000 draws on the CPU.
 *
 * No hook of its own: patch/nowplaying.c's page timer (np_work) calls ly_tick, np_start ly_start, np_stop ly_stop. The stock page still loads
 * and parses the lyrics (online_loadexlyric, the local .lrc reader) and still builds one row per line in the list scroll_lrc (a child
 * of view_lrc), each with the int property "lrc_time" (the line's time, the same unit get_playtime counts in: stock compares them directly)
 * and the text. We read exactly that, so the local and the online source are the same to us, and show the lines in np_lyrics, a
 * scroll_view of the asset (it clips its children; neither axis slidable: it only receives the touches, listeners below) holding a pool of
 * LY_POOL labels made here. The stock list view_lrc is hidden (visible=false and sensitive=false, re-checked every tick); its widgets keep
 * their names and stock keeps filling and scrolling them. label_lyricmsg ("No lyrics") stays stock's.
 *
 * Layout: line i has LYH pixels a text row (1..LY_LINES_MAX rows, estimated from the line's measured width) and LYG below (the chosen text size, ly_sizes; Large is LY_LINE_H / LY_GAP).
 * The anchored line's top sits at LY_ANCHOR (0.35 of the view) plus `man`, the manual scroll; the other lines follow from it up and down. A line of more
 * than three rows is anchored higher (ly_anchor), so that it and, while there is room, the next line's first row stay in the view.
 * Opacity by distance from the current line: 1.0, 0.45, 0.32, 0.24, 0.18 (ly_opacity) times an edge factor that takes a line to 0 over the last LY_FADE px at the top and bottom
 * of the view (ly_edge); while the user has scrolled, every other line is LY_BROWSE_OP. Every line is white; the current one is only the most opaque. Face: a line of
 * Latin, Greek and Cyrillic only is drawn in the bold font file lyrics.ttf (style np_lyric_style, Large and Medium), any other in the default font (np_lyric_cjk_style): AWTK picks a glyph from one font. At Small (22 px) both styles name the default font, so every line is in it.
 *
 * Motion: when the anchored line changes by D pixels every line keeps its place on the screen and gets an offset of D that a damped spring
 * (ly_spring: a 65 entry table of 1024 x e^(-zt)(cos + sin), z 0.72, a few percent of overshoot, LY_SPRING_MS long) brings to 0, each line
 * starting LY_DELAY_MS later than the one before (the step shrinking by 20/21 a line, lines above the one before the current start at once).
 * The offsets are per label slot (o0, ts): a new move adds D to what each line still has. One LY_FRAME_MS timer exists while any line moves and ends
 * itself. A move of more than LY_SNAP_LINES lines jumps.
 *
 * Touch (listeners on np_lyrics; nothing is grabbed or stopped, so the slide view and the window manager see every event as on any page): a
 * vertical drag of LY_TAP_PX or more scrolls the lines with the finger (a sideways one is the slide view's); LY_IDLE_MS after the last touch (checked by
 * the 500 ms page tick) the lines move back to the current one with the same motion; a tap (less than LY_TAP_PX, not within LY_COAST_MS of a move that
 * started) on a line seeks the player to that line's lrc_time with the stock seek_time (the call the Now Playing slider makes) and moves the lines there.
 *
 * Interlude dots (stage 4): for a first line at LY_DOT_MIN_S seconds or later, three images (np_dot) at the anchor row fill dim to full by thirds of the intro, breathe and fade
 * out before the first line; the lines sit LY_DOT_PAD lower meanwhile (ly.pad). get_playtime counts whole seconds, so ly_clock interpolates a position in ms with time_now_ms.
 * One LY_DOT_MS timer (ly_dframe) exists while they show and the player plays; the page tick polls the same (ly_poll) and starts it. Docs: Interlude dots.
 *
 * Only the lines that touch the view are laid out (the label of line i is slot i % LY_POOL, a window of LY_POOL lines round the anchor); a label is
 * touched only when its line, style, opacity, size or position changed. Every failure leaves the stock list showing.
 */
#include "offsets.inc"
#include "stock.h"
#include "home.h"
#include "lyrics.h"
#include "common.h"
#include "textgamma.h"
#include "fnv.h"

/* The text size (Settings > Now Playing > Lyrics Text Size, the file LYRSIZE_FILE: "0" Small, "1" Medium, "2" Large, also for a missing or invalid file): the font px, the text row pitch LYH (the font plus the
 * style's `spacer`: 3 for Small and Medium, 4 for Large, tools/mod_nowplaying.py LYR_SIZES) and the gap LYG between lines (about 0.4 of the font); the intro dots push the lines down by LYH + LYG. Large is the
 * original 30 / 34 / 12 (offsets.inc). The face styles are np_lyric_style[_m|_s] and np_lyric_cjk_style[_m|_s]. */
#define LY_SIZES 3
static const struct {
    unsigned char font, lh, gap;
    const char
        *style[2]; /* the face's style: [0] the bold Latin face (Small: the default font too), [1] the default font */
} ly_sizes[LY_SIZES] = {
    {LY_FONT,
     LY_LINE_H,
     LY_GAP,
     {"np_lyric_style", "np_lyric_cjk_style"}}, /* Large first: a cleared state is the original layout */
    {26, 29, 10, {"np_lyric_style_m", "np_lyric_cjk_style_m"}},
    {22, 25, 9, {"np_lyric_style_s", "np_lyric_cjk_style_s"}}};
#define LYH (ly_sizes[ly.sz].lh)
#define LYG (ly_sizes[ly.sz].gap)
#define LYSTYLE(face) (ly_sizes[ly.sz].style[(face) ? 1 : 0])
/* The view the engine drives: its height (LY_VIEW_H for Now Playing's np_lyrics, the idle page's box otherwise), the anchor (0.35 of it, LY_ANCHOR for np_lyrics) and the offset bound (4 x the height, LY_OFF_MAX). */
#define LYVH (ly.vh ? ly.vh : LY_VIEW_H) /* (a stopped engine is Now Playing's geometry) */
#define LYANC (ly.vh ? ly.anc : LY_ANCHOR)
#define LYOFF (4 * LYVH)

static struct {
    int vh, anc; /* the view's height and the anchor's place in it (ly_target) */
    int noseek; /* a tap seeks nothing (the idle page: a tap there closes it) */
    int sz; /* the text size: an index of ly_sizes (0 Large, 1 Medium, 2 Small: 2 - the saved digit), read when the page starts (ly_start) and when it is in front again (ly_refresh) */
    void *win, *src, *view, *box,
        *probe; /* the window, scroll_lrc (stock rows), view_lrc (stock list), np_lyrics (ours), the measuring label */
    void *lab[LY_POOL];
    int line[LY_POOL]; /* the line each label shows, -1 none */
    int mv[LY_POOL]; /* the line whose motion o0 / ts describe, -1 none */
    short y[LY_POOL]; /* where the label was last put (box coordinates) */
    short o0[LY_POOL]; /* the offset (px) the line's spring starts from ... */
    unsigned ts[LY_POOL]; /* ... at this time (time_now_ms; later than the move when the line is delayed) */
    unsigned char op[LY_POOL], sel[LY_POOL], vis[LY_POOL],
        rows[LY_POOL]; /* opacity, face (style: 0 bold Latin, 1 default font), visibility, height in rows */
    unsigned char pface; /* the face the probe measures in */
    unsigned sig; /* what the stock rows were when we last read them */
    int n; /* the rows, at most LY_MAX */
    int cur; /* the highlighted line, -1 before the first */
    int base; /* the line anchored at ly_anchor(base) + man */
    int man; /* the manual scroll: where the anchored line's top is, from its anchor (px) */
    int gd, gcur; /* the latest move: its distance and its target line (a line new to a slot moves with it) */
    unsigned gt; /* and when it started */
    unsigned timer; /* the animation timer, 0 none */
    int dirty; /* the layout must be redone */
    int browse; /* the user has scrolled: the lines do not follow the song until LY_IDLE_MS after the last touch */
    int hold; /* a tap seeked: the tick does not move the lines until the player has caught up */
    unsigned hold_until, touch_at;
    int down, moved, tapok, sx, sy, ly; /* the touch: down, scrolling, tap allowed, where it began, the last y */
    /* The interlude dots: three images, their opacity (the group's, before the edge factor) and visibility; pad is how far the lines sit below the anchor
     * while they show; est is the player's position in ms (get_playtime counts whole seconds), interpolated by the monotonic clock. */
    void *dot[3];
    unsigned char dop[3], dvis[3], dlast[3];
    short dy;
    int pad, fresh, ck_ok, ck_pos, ck_pl, est;
    unsigned ck_t, dtimer;
    unsigned char ht[LY_MAX]; /* rows of each line, 0 not measured yet */
    unsigned char fc[LY_MAX]; /* face of each measured line */
    unsigned char brk
        [LY_MAX]
        [LY_LINES_MAX]; /* a wrapped line's break offsets in its text and, last, the offset it is cut at (ly_break) */
    unsigned char miss, redo,
        skip; /* page ticks whose layout could not measure a line (since the lyrics loaded); whether the layout must run again for that; a measure failed in this layout */
} ly __attribute__((section(".scratch")));

/* The damped spring, 1024 x g(t) every 10 ms, g = e^(-zeta wn t) (cos wd t + zeta / sqrt(1 - zeta^2) sin wd t), zeta 0.72, wn 12 /s, wd = wn sqrt(1 - zeta^2):
 * 1 at 0, -0.038 at 380 ms (the overshoot), -0.001 at 640 ms. test/pod/lyrics.py computes the same numbers. */
static const short ly_tab[LY_SPRING_MS / 10 + 1] = {
    1024, 1017, 998, 968, 931, 887, 838, 786, 732, 677, 622, 567, 513, 461, 412, 364, 320, 278, 239, 203, 171, 141,
    114,  90,   68,  49,  32,  18,  6,   -5,  -14, -21, -27, -31, -34, -37, -38, -39, -39, -39, -38, -37, -35, -34,
    -32,  -30,  -28, -25, -23, -21, -19, -17, -15, -14, -12, -10, -9,  -7,  -6,  -5,  -4,  -3,  -2,  -2,  -1};

/* The offset of a line whose spring started at o0 and has run `elapsed` ms (negative: not started, the whole offset; at LY_SPRING_MS and after: 0).
 * Linear between the table's entries, toward zero in the integer divisions; an overshoot past zero is cut at LY_OVERSHOOT_MAX px. */
__attribute__((noinline)) int ly_spring(int o0, int elapsed) {
    int idx, g, v;
    if (elapsed <= 0) return o0;
    if (elapsed >= LY_SPRING_MS) return 0;
    idx = elapsed / 10;
    g = ly_tab[idx] + (ly_tab[idx + 1] - ly_tab[idx]) * (elapsed % 10) / 10;
    v = (int)((long long)o0 * g / 1024);
    if (o0 > 0 && v < -LY_OVERSHOOT_MAX) v = -LY_OVERSHOOT_MAX;
    if (o0 < 0 && v > LY_OVERSHOOT_MAX) v = LY_OVERSHOOT_MAX;
    return v;
}

/* How long after a move starts line i starts: lines above the one before the target line c at once, then LY_DELAY_MS, the step shrinking by 20/21 a line. */
__attribute__((noinline)) int ly_delay(int i, int c) {
    int r = i - (c - 1), d = 0, s = LY_DELAY_MS;
    if (r > LY_POOL) r = LY_POOL;
    while (r-- > 0) {
        d += s;
        s = s * 20 / 21;
    }
    return d;
}

/* The time of stock row i; a missing row is never reached. */
static int ly_time(int i) {
    void *c = widget_get_child(ly.src, (unsigned)i);
    return c ? widget_get_prop_int(c, "lrc_time", 0x7fffffff) : 0x7fffffff;
}

/* The bytes of blank characters s starts with: space, tab, U+00A0, U+2000..U+200B, U+202F, U+3000 and U+FEFF. */
static int ly_lead(const char *s) {
    const unsigned char *u = (const unsigned char *)s;
    int p = 0;
    for (;;) {
        if (u[p] == ' ' || u[p] == '\t')
            p += 1;
        else if (u[p] == 0xc2 && u[p + 1] == 0xa0)
            p += 2;
        else if (u[p] == 0xe2 && u[p + 1] == 0x80 && ((u[p + 2] >= 0x80 && u[p + 2] <= 0x8b) || u[p + 2] == 0xaf))
            p += 3;
        else if (u[p] == 0xe3 && u[p + 1] == 0x80 && u[p + 2] == 0x80)
            p += 3;
        else if (u[p] == 0xef && u[p + 1] == 0xbb && u[p + 2] == 0xbf)
            p += 3;
        else
            return p;
    }
}

/* The text of stock row i into buf (LY_BUF bytes), without its leading blanks (ly_lead); 0 when the row or its text is missing. Stock's loader keeps everything after
 * the time stamp's ']' (0x5d3f28), so a file written "[00:12.34] text" gave every line a space: its first row was indented and the rows we break were not. */
static int ly_text(int i, char *buf) {
    void *c = widget_get_child(ly.src, (unsigned)i);
    int p, k = 0;
    buf[0] = 0;
    /* (a line over LY_BUF - 1 bytes is cut: at most LY_LINES_MAX rows of it are drawn anyway) */
    if (!c || m1_text_utf8(c, buf, LY_BUF) < 0) {
        buf[0] = 0;
        return 0;
    }
    if ((p = ly_lead(buf)) != 0)
        while ((buf[k] = buf[p + k]) != 0) ++k;
    return 1;
}

/* A signature of the stock rows: their number, the first and last row's handle and time. A new song's lyrics (the rows are destroyed and made again) change it. */
static unsigned ly_sig(int n) {
    unsigned h = FNV_SEED;
    void *a = widget_get_child(ly.src, 0), *b = widget_get_child(ly.src, (unsigned)(n - 1));
    h = (h ^ (unsigned)n) * FNV_PRIME;
    h = (h ^ (unsigned)(unsigned long)a) * FNV_PRIME;
    h = (h ^ (unsigned)(unsigned long)b) * FNV_PRIME;
    h = (h ^ (unsigned)ly_time(0)) * FNV_PRIME;
    h = (h ^ (unsigned)ly_time(n - 1)) * FNV_PRIME;
    return h | !h;
}

/* The code points of the bold face lyrics.ttf (the Inter Bold subset of tools/font_inter.py, less the combining marks and U+200B): test/pod/lyrics.py checks every
 * code point up to U+2FFF against that file's cmap. */
static const unsigned short ly_bold[][2] = {
    {0x20, 0x7e},     {0xa0, 0xac},     {0xae, 0x148},    {0x14a, 0x1c3},   {0x1c5, 0x24f},   {0x374, 0x376},
    {0x37a, 0x37f},   {0x384, 0x38a},   {0x38c, 0x38c},   {0x38e, 0x3a1},   {0x3a3, 0x3d7},   {0x3dc, 0x3dd},
    {0x3f0, 0x3f6},   {0x3f9, 0x3fa},   {0x3fc, 0x479},   {0x480, 0x49d},   {0x4a0, 0x4ff},   {0x52f, 0x52f},
    {0x1e00, 0x1e9b}, {0x1e9d, 0x1eff}, {0x2000, 0x200a}, {0x2010, 0x2027}, {0x202f, 0x2055}, {0x2057, 0x2057},
    {0x205f, 0x205f}, {0x2070, 0x2071}, {0x2074, 0x208e}, {0x2090, 0x209c}, {0x20a0, 0x20af}, {0x20b1, 0x20b5},
    {0x20b8, 0x20ba}, {0x20bc, 0x20c0}, {0x2116, 0x2116}, {0x2122, 0x2122}};

/* Whether every code point of the UTF-8 text s is in the bold face. Anything else (CJK, kana, Hangul, symbols, malformed bytes) makes the line the default
 * font's: AWTK takes a glyph from one font only. */
__attribute__((noinline)) int ly_latin(const char *s) {
    const unsigned char *p = (const unsigned char *)s;
    while (*p) {
        unsigned c = *p++;
        if (c >= 0x80) {
            int n = c >= 0xf0 ? 3 : c >= 0xe0 ? 2 : c >= 0xc2 ? 1 : -1;
            if (n < 0 || c >= 0xf8) return 0;
            c &= 0x3f >> n;
            while (n--) {
                if ((*p & 0xc0) != 0x80) return 0;
                c = c << 6 | (*p++ & 0x3f);
            }
        }
        {
            unsigned k;
            for (k = 0; k < sizeof ly_bold / sizeof ly_bold[0]; ++k)
                if (c >= ly_bold[k][0] && c <= ly_bold[k][1]) break;
            if (k == sizeof ly_bold / sizeof ly_bold[0]) return 0;
        }
    }
    return 1;
}

/* The probe in the face's style, resolved; 0: it cannot be yet. widget_use_style resolves a style only in an opened window, and the window resolves every widget's
 * when it is about to open (offsets.inc WINDOW_STAGE_CREATED), after np_start's first tick: a measure before that would be in the label's default style, a width too
 * small that would be kept (a 30 px line of two rows measured as one, its second row cut). So nothing is measured before (the line is retried, as a measure of 0), and
 * the probe's style is resolved here (widget_update_style, which does nothing once it is), as stock label_resize_to_content does before it measures. */
static int ly_probe_face(int face) {
    if (ly.pface != face) {
        widget_use_style(ly.probe, LYSTYLE(face));
        ly.pface = (unsigned char)face;
    }
    if (widget_get_prop_int(ly.win, "stage", 0) < WINDOW_STAGE_CREATED) return 0;
    widget_update_style(ly.probe);
    return 1;
}

/* The width of the n bytes at s (at most LY_BUF - 1) in the probe's face; 0: it could not be measured. */
static int ly_span(const char *s, int n) {
    char t[LY_BUF];
    const unsigned *u;
    int k;
    for (k = 0; k < n; ++k) t[k] = s[k];
    t[n] = 0;
    if (widget_set_text_utf8(ly.probe, t) != RET_OK) return 0;
    u = widget_get_text(ly.probe);
    return u && *u ? m1_text_w(ly.probe, u) : 0;
}

/* Breaks line i (text s, probe ready in its face) into rows ourselves: greedy at the spaces, a word wider than a row (or a text with no spaces: CJK) at any code point.
 * Stock's label wrap would break a row at its first character past the content width (LY_W less the style's 2 px margins), but leaves an overflowing LAST character on
 * its row, clipped at the label's edge, and its row count would then differ from ours. Every row here is at most LY_ROW_W wide: stock's check (0x62ddf0: the row so far +
 * the character + 1 px over the content width) never fires and our '\n's are its only breaks. A line that fits in LY_FIT_W is left to stock (a last character may then
 * reach LY_FIT_W, its ink ends before the label's edge). ly.brk[i] gets the break offsets (a space there becomes the '\n', else the '\n' is put before the byte) and,
 * in its last byte, the offset the text is cut at when it has more than LY_LINES_MAX rows: ly_wrapped puts LY_MARK ("...", one character) there. The last row keeps
 * room for the mark: what does not fit beside it is cut, unless the whole rest of the line fits the row without it (one more measure, of the rest). Returns the rows,
 * 0 when something could not be measured. Widths add up (no kerning): one measure of the line, then one per word (and per code point of a long word), at most the
 * LY_LINES_MAX rows' worth, one of a space and one of the mark; the result is cached with the rows. */
static int ly_break(int i, const char *s) {
    unsigned char *bk = ly.brk[i];
    int len = 0, w, sp, mk, rows = 1, rs = 0, x = 0, p = 0, k;
    while (s[len]) ++len;
    for (k = 0; k < LY_LINES_MAX; ++k) bk[k] = 0;
    w = ly_span(s, len);
    if (!w) return 0;
    if (w <= LY_FIT_W) return 1;
    sp = ly_span(" ", 1);
    if (!sp) return 0;
    mk = ly_span(LY_MARK, sizeof LY_MARK - 1); /* (a face without the character: no room is kept) */
#define LY_LIM (rows == LY_LINES_MAX ? LY_ROW_W - mk : LY_ROW_W)
    for (;;) {
        int e = p, tw = 0;
        while (s[e] && s[e] != ' ') ++e;
        if (e > p && !(tw = ly_span(s + p, e - p))) return 0;
        if (p > rs && x + sp + tw > LY_LIM) { /* the word starts the next row (the space before it is the break) */
            if (rows ==
                LY_LINES_MAX) { /* there is none: the rest fits the row without the mark, or the line is cut here */
                int rest = ly_span(s + p, len - p);
                if (!rest) return 0;
                if (x + sp + rest > LY_ROW_W) bk[LY_LINES_MAX - 1] = (unsigned char)(p - 1);
                return rows;
            }
            bk[rows++ - 1] = (unsigned char)(p - 1), rs = p, x = 0;
        }
        if (p > rs) x += sp;
        if (x + tw <= LY_LIM) {
            x += tw;
        } else { /* wider than a row: by code point */
            int q = p;
            while (q < e) {
                int n = 1, cw;
                while (q + n < e && (s[q + n] & 0xc0) == 0x80) ++n;
                if (!(cw = ly_span(s + q, n))) return 0;
                if (x && x + cw > LY_LIM) {
                    if (rows == LY_LINES_MAX) {
                        int rest = ly_span(s + q, len - q);
                        if (!rest) return 0;
                        if (x + rest > LY_ROW_W) bk[LY_LINES_MAX - 1] = (unsigned char)q;
                        return rows;
                    }
                    bk[rows++ - 1] = (unsigned char)q, rs = q, x = 0;
                }
                x += cw, q += n;
            }
        }
        if (!s[e]) return rows;
        p = e + 1;
    }
#undef LY_LIM
}

/* The rows line i takes (ly_break), 1 when it fits one row, at most LY_LINES_MAX. Its face is chosen here (ly_latin). Cached, except a
 * measure of non-empty text that came back 0 or was not made (the probe not ready, ly_probe_face): that line is 1 row for now and measured again by the layout ly.redo asks for. Once a measure
 * failed, the rest of that layout (ly.skip, cleared as a layout starts) measures nothing; the page tick counts a layout that saw a failure in ly.miss, and after
 * LY_MISS_MAX of them (10 s at the 500 ms tick) a line is kept at 1 row, so a probe that never measures costs a bounded number of calls. */
__attribute__((noinline)) int ly_rows(int i) {
    char buf[LY_BUF];
    int rows = 0, face = 0, text = 0;
    if (i < 0 || i >= ly.n) return 1;
    if (ly.ht[i]) return ly.ht[i];
    if (ly.probe && ly_text(i, buf) && buf[0]) {
        text = 1;
        face = !ly_latin(buf);
        if (!(ly.skip && ly.miss < LY_MISS_MAX) && ly_probe_face(face)) rows = ly_break(i, buf);
    }
    ly.fc[i] = (unsigned char)face;
    if (text && !rows && ly.miss < LY_MISS_MAX) { /* not measured: not kept */
        ly.skip = ly.redo = 1;
        return 1;
    }
    if (ly.miss) ly.redo = 1; /* a line measured after a miss: the layout above may have used its 1 row */
    if (rows < 1) rows = 1;
    ly.ht[i] = (unsigned char)rows;
    return rows;
}

/* The text of line i for its label: ly_text with the breaks of ly_break (rows is ly_rows(i)) and, when the line is cut, LY_MARK at its end. out holds LY_OUT bytes. */
#define LY_OUT (LY_BUF + LY_LINES_MAX + (int)sizeof LY_MARK)
static void ly_wrapped(int i, int rows, char *out) {
    char buf[LY_BUF];
    int p, o = 0, k = 0, cut = rows > 1 ? ly.brk[i][LY_LINES_MAX - 1] : 0;
    ly_text(i, buf);
    for (p = 0; buf[p] && !(cut && p == cut); ++p) {
        if (k < rows - 1 && p == ly.brk[i][k]) {
            out[o++] = '\n', ++k;
            if (buf[p] == ' ') continue;
        }
        out[o++] = buf[p];
    }
    if (cut)
        for (p = 0; p < (int)sizeof LY_MARK - 1; ++p) out[o++] = LY_MARK[p];
    out[o] = 0;
}

/* The pixels line i occupies, its gap included. */
static int ly_pitch(int i) { return ly_rows(i) * LYH + LYG; }

/* Where line i's top sits when it is the anchored one: LY_ANCHOR for up to three rows; a taller line higher, so that the next line's first row still ends
 * LY_ANCHOR_ROOM px above the view's bottom, but not above LY_ANCHOR_MIN (LY_LINES_MAX rows from there end inside the view). */
__attribute__((noinline)) int ly_anchor(int i) {
    int a = LYVH - LY_ANCHOR_ROOM - LYH - ly_pitch(i);
    return a >= LYANC ? LYANC : a < LY_ANCHOR_MIN ? LY_ANCHOR_MIN : a;
}

/* Opacity (0..255) of a line `dist` lines from the current one: 1.0, 0.45, 0.32, 0.24, then 0.18. */
__attribute__((noinline)) unsigned ly_opacity(int dist) {
    static const unsigned char table[5] = {255, 115, 82, 61, 46};
    if (dist < 0) dist = -dist;
    return table[dist > 4 ? 4 : dist];
}

/* The edge factor (0..255) of a label of `rows` rows at y: its row nearest an edge, by the row's centre, over the last LY_FADE px of the view (0 with the centre on the edge). */
__attribute__((noinline)) unsigned ly_edge(int y, int rows) {
    int top = y + rows * LYH - LYH / 2, bot = LYVH - (y + LYH / 2), e = top < bot ? top : bot;
    if (e <= 0) return 0;
    if (e >= LY_FADE) return 255;
    return (unsigned)(e * 255 / LY_FADE);
}

/* Interlude dots. A gap is the stretch of the song with no line current, `len` ms long, of which `el` ms have passed; stage 4 has one, the intro (from the start to
 * the first line); a gap between two lines would give ly_gap_len a start and a length from the two lines' times and ly_dots the same el. */

/* The opacity (0..255) of dot k (0..2) `el` ms into a gap of `len` ms: dim (LY_DOT_DIM) to 255 as the k-th third of the gap (less its last fade) passes, times a slow breath (triangle,
 * between 255 and LY_DOT_BREATH_MIN, from el so it freezes with the player), times a fade out over the last LY_DOT_FADE_MS. */
__attribute__((noinline)) unsigned ly_dot_op(int k, int el, int len) {
    int f, op, tri, left,
        fl = len - LY_DOT_FADE_MS; /* the dots fill over the gap but its last LY_DOT_FADE_MS, which is the fade out */
    if (len <= 0) return 0;
    if (fl < 1) fl = 1;
    if (el < 0) el = 0;
    f = el * 3 - k * fl;
    f = f < 0 ? 0 : f > fl ? fl : f;
    op = LY_DOT_DIM + (255 - LY_DOT_DIM) * f / fl;
    tri = el % LY_DOT_BREATH_MS;
    if (tri > LY_DOT_BREATH_MS / 2) tri = LY_DOT_BREATH_MS - tri;
    op = op * (255 - (255 - LY_DOT_BREATH_MIN) * tri / (LY_DOT_BREATH_MS / 2)) / 255;
    left = len - el;
    if (left < LY_DOT_FADE_MS) op = left <= 0 ? 0 : op * left / LY_DOT_FADE_MS;
    return (unsigned)op;
}

/* The length (ms) of the gap the dots fill now, 0 for none: before the first line, when it is at least LY_DOT_MIN_S seconds in and the dots exist. */
static int ly_gap_len(void) {
    int t;
    if (!ly.dot[0] || ly.n <= 0 || ly.cur >= 0) return 0;
    t = ly_time(0);
    return t >= LY_DOT_MIN_S && t < 10000 ? t * 1000 : 0;
}

static int ly_want_pad(void) { return ly_gap_len() ? (LYH + LYG) : 0; }

/* The player's position in ms from get_playtime's whole seconds: a first read or a seek is taken as the middle of the second; a second that has just turned is its
 * start; between turns the monotonic clock adds the time that passed while playing (not across a pause), never past the end of the second. */
static void ly_clock(int pos, unsigned now, int playing) {
    int dt = (int)(now - ly.ck_t);
    ly.ck_t = now;
    if (!ly.ck_ok || pos < ly.ck_pos || pos > ly.ck_pos + 1)
        ly.est = pos * 1000 + 500;
    else if (pos == ly.ck_pos + 1)
        ly.est = pos * 1000;
    else if (playing && ly.ck_pl && dt > 0) {
        ly.est += dt;
        if (ly.est > pos * 1000 + 999) ly.est = pos * 1000 + 999;
    }
    ly.ck_ok = 1, ly.ck_pos = pos, ly.ck_pl = playing;
}

/* The dots of the gap, riding with line 0 (whose top is at d0): hidden when no gap is on, line 0 is not laid out, or the opacity is 0. */
static void ly_dots(int have0, int d0) {
    int k, y = d0 - (LYH + LYG), on = have0 && ly_gap_len() > 0;
    for (k = 0; k < 3; ++k) {
        unsigned op = on ? ly.dop[k] * ly_edge(y, 1) / 255 : 0;
        void *w = ly.dot[k];
        if (!w) return;
        if (!op) {
            if (ly.dvis[k]) {
                widget_set_visible(w, 0, 0);
                ly.dvis[k] = 0;
            }
            continue;
        }
        if (ly.dlast[k] != op || !ly.dvis[k]) {
            widget_set_opacity(w, (int)op);
            ly.dlast[k] = (unsigned char)op;
        }
        if (ly.dy != y + (LYH - LY_DOT) / 2 || !ly.dvis[k])
            widget_move(w, LY_DOT_X + k * LY_DOT_PITCH, y + (LYH - LY_DOT) / 2);
        if (!ly.dvis[k]) {
            widget_set_visible(w, 1, 0);
            ly.dvis[k] = 1;
        }
    }
    ly.dy = (short)(y + (LYH - LY_DOT) / 2);
}

static int ly_off(int slot, unsigned now) { return ly_spring(ly.o0[slot], (int)(now - ly.ts[slot])); }

/* Some line still has a spring running. */
static int ly_busy(unsigned now) {
    int s;
    for (s = 0; s < LY_POOL; ++s)
        if (ly.mv[s] >= 0 && ly.o0[s] && (int)(now - ly.ts[s]) < LY_SPRING_MS) return 1;
    return 0;
}

static void ly_hide(int slot) {
    if (ly.vis[slot]) {
        widget_set_visible(ly.lab[slot], 0, 0);
        ly.vis[slot] = 0;
    }
}

/* Line i at y in the box: the label of its slot takes the text, style, size, opacity and place it needs. */
static void ly_place(int i, int y) {
    int slot = i % LY_POOL, rows = ly_rows(i), face = ly.fc[i];
    unsigned op = ly.browse ? (i == ly.cur ? 255 : LY_BROWSE_OP) : ly_opacity(i - (ly.cur < 0 ? -1 : ly.cur));
    void *w = ly.lab[slot];
    op = op * ly_edge(y, rows) / 255;
    if (!op) { /* faded out at the edge */
        ly_hide(slot);
        return;
    }
    if (ly.line[slot] != i || ly.rows[slot] != rows) { /* (a line placed before it was measured has no breaks yet) */
        char buf[LY_OUT];
        ly_wrapped(i, rows, buf);
        widget_set_text_utf8(w, buf);
        ly.line[slot] = i;
    }
    if (ly.rows[slot] != rows) {
        widget_resize(w, LY_W, rows * LYH);
        ly.rows[slot] = (unsigned char)rows;
    }
    if (ly.sel[slot] != face) {
        widget_use_style(w, LYSTYLE(face));
        ly.sel[slot] = (unsigned char)face;
    }
    if (ly.op[slot] != op) {
        widget_set_opacity(w, (int)op);
        ly.op[slot] = (unsigned char)op;
    }
    if (ly.y[slot] != y || !ly.vis[slot]) {
        widget_move(w, 0, y);
        ly.y[slot] = (short)y;
    }
    if (!ly.vis[slot]) {
        widget_set_visible(w, 1, 0);
        ly.vis[slot] = 1;
    }
}

/* Lay the lines out: the LY_POOL lines round the anchored one, each at its nominal place plus its spring's offset, those that touch the view placed. */
static void ly_layout(void) {
    unsigned char used[LY_POOL];
    int np[LY_POOL], lo0, lo, hi, i, y, slot, have0 = 0, d0 = 0;
    unsigned now = time_now_ms();
    memset(used, 0, sizeof used);
    ly.skip = 0;
    if (ly.n > 0) {
        lo0 = ly.base - LY_POOL / 2 + 1;
        if (lo0 < 0) lo0 = 0;
        lo = lo0, hi = ly.base + LY_POOL / 2;
        if (hi > ly.n - 1) hi = ly.n - 1;
        y = ly_anchor(ly.base) + ly.man + ly.pad;
        np[ly.base - lo0] = y;
        for (i = ly.base; i < hi; ++i) {
            y += ly_pitch(i);
            if (y > LYVH + LYOFF) {
                hi = i;
                break;
            }
            np[i + 1 - lo0] = y;
        }
        y = ly_anchor(ly.base) + ly.man + ly.pad;
        for (i = ly.base - 1; i >= lo0; --i) {
            y -= ly_pitch(i);
            if (y < -LYOFF - LY_LINES_MAX * LYH) {
                lo = i + 1;
                break;
            }
            np[i - lo0] = y;
        }
        for (i = lo; i <= hi; ++i) {
            int disp;
            slot = i % LY_POOL;
            if (ly.mv[slot] != i) { /* a line new to the slot moves with the latest move */
                ly.o0[slot] = (short)ly.gd;
                ly.ts[slot] = ly.gt + (unsigned)ly_delay(i, ly.gcur);
                ly.mv[slot] = i;
            }
            disp = np[i - lo0] + ly_off(slot, now);
            if (i == 0) have0 = 1, d0 = disp;
            if (disp + ly_rows(i) * LYH > 0 && disp < LYVH) {
                ly_place(i, disp);
                used[slot] = 1;
            }
        }
    }
    for (slot = 0; slot < LY_POOL; ++slot)
        if (!used[slot]) ly_hide(slot);
    ly_dots(have0, d0);
    ly.dirty = ly.redo,
    ly.redo = 0; /* a line that was not measured is tried again by the next layout (the page tick) */
}

static int ly_frame(const void *timer) {
    (void)timer;
    if (!ly.box) return RET_OK;
    ly_layout();
    if (ly_busy(time_now_ms())) return RET_REPEAT;
    ly.timer = 0; /* RET_OK ends the timer */
    return RET_OK;
}

/* A spring is running: make sure the frame timer is. No timer: nothing moves smoothly, every line is where it belongs. */
static void ly_kick(void) {
    int s;
    if (ly.timer || !ly_busy(time_now_ms())) return;
    ly.timer = timer_add(ly_frame, (void *)0, LY_FRAME_MS);
    if (!ly.timer)
        for (s = 0; s < LY_POOL; ++s) ly.o0[s] = 0;
}

/* The anchored line becomes nb: every line stays where it is on the screen (the distance D between the two anchors, the manual scroll included, is
 * added to its offset) and its spring, delayed by its place, brings it to its new one. A move over LY_SNAP_LINES lines jumps. */
static void ly_move(int nb) {
    int d = ly.man + ly.pad - ly_want_pad(), i, s;
    unsigned now = time_now_ms();
    if (nb < 0) nb = 0;
    if (ly.n > 0 && nb > ly.n - 1) nb = ly.n - 1;
    d += ly_anchor(ly.base) - ly_anchor(nb);
    if (nb - ly.base > LY_SNAP_LINES || ly.base - nb > LY_SNAP_LINES) {
        for (s = 0; s < LY_POOL; ++s) ly.o0[s] = 0;
        ly.gd = 0;
    } else {
        for (i = ly.base; i < nb; ++i) d += ly_pitch(i);
        for (i = nb; i < ly.base; ++i) d -= ly_pitch(i);
        for (s = 0; s < LY_POOL; ++s)
            if (ly.mv[s] >= 0) {
                int o = ly_off(s, now) + d;
                if (o > LYOFF) o = LYOFF; /* (what the layout keeps laid out) */
                if (o < -LYOFF) o = -LYOFF;
                ly.o0[s] = (short)o;
                ly.ts[s] = now + (unsigned)ly_delay(ly.mv[s], nb);
            }
        ly.gd = d, ly.gt = now, ly.gcur = nb;
    }
    ly.base = nb;
    ly.man = 0;
    ly.pad = ly_want_pad(); /* the dots come or go with this move: the lines slide by their height */
    ly.dirty = 1;
    ly_kick();
}

/* The anchored line is the current one's (or the first): the song moved on, or the user stopped scrolling. */
static void ly_follow(void) { ly_move(ly.cur < 0 ? 0 : ly.cur); }

/* After a manual move: the anchored line is the one nearest LY_ANCHOR again (its top under half a pitch from it), and the first / last line stop at their anchor.
 * t is the anchored line's top from LY_ANCHOR; man is counted from the line's own anchor (ly_anchor), so nothing jumps when the anchored line changes. */
static void ly_rebase(void) {
    int t = ly.man + ly_anchor(ly.base) - LYANC;
    while (ly.base > 0 && t > ly_pitch(ly.base - 1) / 2) {
        ly.base -= 1;
        t -= ly_pitch(ly.base);
    }
    while (ly.base < ly.n - 1 && t < -ly_pitch(ly.base) / 2) {
        t += ly_pitch(ly.base);
        ly.base += 1;
    }
    ly.man = t - (ly_anchor(ly.base) - LYANC);
    if (ly.base == 0 && ly.man > 0) ly.man = 0;
    if (ly.base >= ly.n - 1 && ly.man < 0) ly.man = 0;
}

/* The last line whose time has come at pos (-1 none), searched from the current one: the times grow. */
static int ly_find(int pos) {
    int i = ly.cur < 0 ? 0 : ly.cur;
    while (i > 0 && ly_time(i) > pos) --i;
    while (i + 1 < ly.n && ly_time(i + 1) <= pos) ++i;
    return ly_time(i) <= pos ? i : -1;
}

static void ly_poll(unsigned now);

/* The dots' frame (LY_DOT_MS): the same poll as the page tick, so the position, the current line and the dots agree, then the layout. It ends itself when the dots
 * are gone or the player is not playing (frozen dots stay as they are; the page tick starts it again). */
static int ly_dframe(const void *timer) {
    (void)timer;
    if (!ly.box) return RET_OK;
    ly_poll(time_now_ms());
    if (ly.dirty) ly_layout();
    if (ly.n > 0 && ly_gap_len() && mclGetPlayStatus() == 2) return RET_REPEAT;
    ly.dtimer = 0; /* RET_OK ends the timer */
    return RET_OK;
}

/* The dots show and the player plays: make sure the frame timer runs. A refused timer leaves the dots to the page tick (they move twice a second, never stuck). */
static void ly_dkick(void) {
    if (!ly.dtimer && ly.n > 0 && ly_gap_len() && mclGetPlayStatus() == 2)
        ly.dtimer = timer_add(ly_dframe, (void *)0, LY_DOT_MS);
}

/* Position, current line and dots (the part of the tick the dots' frame repeats). */
static void ly_poll(unsigned now) {
    int pos, st = mclGetPlayStatus(), k, len, np;
    if (ly.hold && (int)(now - ly.hold_until) >= 0) ly.hold = 0;
    pos = st == 1 ? 0 : get_playtime(); /* as the stock tick (0x5385b4..0x5385e8): stopped is 0 */
    if (pos >= 0) {
        ly_clock(pos, now, st == MB_PLAYING);
        if (!ly.hold) {
            int cur = ly_find(pos);
            if (cur != ly.cur) {
                ly.cur = cur;
                if (ly.browse) { /* the highlight moves, the lines stay under the finger: the dots' room comes or goes without moving them */
                    np = ly_want_pad();
                    ly.man += ly.pad - np, ly.pad = np;
                    ly.dirty = 1;
                } else
                    ly_follow();
            }
        }
    }
    if (ly.fresh) { /* new lyrics: the lines take their place (under the dots, if any) without a move */
        ly.fresh = 0, ly.pad = ly_want_pad();
        ly.dirty = 1;
    }
    len = ly_gap_len();
    for (k = 0; k < 3; ++k) {
        unsigned op = len ? ly_dot_op(k, ly.est, len) : 0;
        if (op != ly.dop[k]) ly.dop[k] = (unsigned char)op, ly.dirty = 1;
    }
    if (!len && ly.dvis[0]) ly.dirty = 1;
}

void ly_tick(void) {
    int n;
    unsigned now;
    if (!ly.box) return;
    now = time_now_ms();
    if (ly.view && widget_get_visible(ly.view)) { /* stock shows it again for its own purposes: ours is the page */
        widget_set_visible(ly.view, 0, 0);
        widget_set_sensitive(ly.view, 0);
    }
    n = (int)widget_count_children(ly.src);
    if (n > LY_MAX) n = LY_MAX;
    if (n <= 0) {
        if (ly.n) { /* the lyrics are gone: the stock message shows */
            memset(ly.ht, 0, sizeof ly.ht), ly.miss = ly.redo = ly.skip = 0;
            ly.n = 0, ly.cur = -1, ly.base = 0, ly.man = 0, ly.browse = ly.hold = 0, ly.sig = 0, ly.dirty = 1;
            ly.pad = ly.fresh = ly.ck_ok = 0, memset(ly.dop, 0, sizeof ly.dop);
            memset(ly.line, 0xff, sizeof ly.line);
            memset(ly.mv, 0xff, sizeof ly.mv);
        }
    } else if (ly_sig(n) != ly.sig || n != ly.n) { /* new lyrics: nothing of the old ones is kept */
        int i;
        memset(ly.ht, 0, sizeof ly.ht), ly.miss = ly.redo = ly.skip = 0;
        for (i = 0; i < LY_POOL; ++i) ly.line[i] = ly.mv[i] = -1, ly.sel[i] = 0xff, ly.o0[i] = 0;
        ly.n = n, ly.cur = -1, ly.base = 0, ly.man = 0, ly.gd = 0, ly.browse = ly.hold = 0, ly.sig = ly_sig(n),
        ly.dirty = 1;
        ly.pad = ly.ck_ok = 0, ly.fresh = 1, memset(ly.dop, 0, sizeof ly.dop);
    }
    if (ly.n > 0) {
        /* a measure that failed in the last layout is tried again by this tick's move as well (its distance is the lines' measured heights) */
        ly.skip = 0;
        ly_poll(now);
        if (ly.browse && !ly.down &&
            (int)(now - ly.touch_at) >= LY_IDLE_MS) { /* the user let go: back to the current line, eased */
            ly.browse = 0;
            ly_follow();
        }
    }
    if (ly.dirty) {
        ly_layout();
        if (ly.skip && ly.miss < LY_MISS_MAX) ly.miss++; /* a tick whose layout could not measure */
    }
    ly_dkick();
}

/* A tap on line `line`: the player seeks to its time (the stock seek_time: the call the Now Playing slider makes; a stopped player does nothing) and the lines
 * move there at once; the tick leaves them alone for LY_HOLD_MS so the player's old position does not pull them back. */
static void ly_goto(int line) {
    int t;
    if (line < 0 || line >= ly.n || mclGetPlayStatus() == 1) return;
    t = ly_time(line);
    if (t == 0x7fffffff) return;
    seek_time(t);
    ly.browse = 0;
    ly.cur = line;
    ly.hold = 1, ly.hold_until = time_now_ms() + LY_HOLD_MS;
    ly_move(line);
    ly_layout();
}

static void ly_tap(int x, int y) {
    int pt[2], s;
    if (ly.noseek) return;
    pt[0] = x, pt[1] = y;
    widget_to_local(ly.box, pt);
    for (s = 0; s < LY_POOL; ++s)
        if (ly.vis[s] && ly.line[s] >= 0 && pt[1] >= ly.y[s] - LYG / 2 &&
            pt[1] < ly.y[s] + ly.rows[s] * LYH + LYG / 2) {
            ly_goto(ly.line[s]);
            return;
        }
}

/* DOWN, MOVE, UP and ABORT of np_lyrics (listeners: they run after the scroll_view's own handler, which has no slidable axis, and never answer RET_STOP). */
static int ly_on_touch(void *ctx, void *e) {
    int type, x, y;
    unsigned now;
    if (!e || !ly.box || ctx != ly.box) return RET_OK; /* (a view that does not have the engine) */
    type = *(int *)e;
    x = *(int *)((char *)e + PE_X), y = *(int *)((char *)e + PE_Y);
    now = time_now_ms();
    ly.touch_at = now;
    if (type == EVT_POINTER_DOWN) {
        ly.down = 1, ly.moved = 0, ly.sx = x, ly.sy = y, ly.ly = y;
        ly.tapok = !(ly_busy(now) &&
                     (int)(now - ly.gt) <
                         LY_COAST_MS); /* a touch within 200 ms of a move that started is no tap (gestures.md) */
    } else if (type == EVT_POINTER_MOVE && ly.down) {
        if (!ly.moved) {
            if (m1_abs(y - ly.sy) >= LY_TAP_PX && m1_abs(y - ly.sy) > m1_abs(x - ly.sx))
                ly.moved = 1, ly.browse = 1, ly.ly = y;
            else if (m1_abs(x - ly.sx) >= LY_TAP_PX)
                ly.down = 0; /* sideways: the slide view's, and its abort ends the touch for us too */
        } else {
            ly.man += y - ly.ly;
            ly.ly = y;
            ly_rebase();
            ly_layout();
        }
    } else if (type == EVT_POINTER_UP && ly.down) {
        ly.down = 0;
        if (!ly.moved && ly.tapok && m1_abs(x - ly.sx) < LY_TAP_PX && m1_abs(y - ly.sy) < LY_TAP_PX) ly_tap(x, y);
    } else if (type == EVT_POINTER_ABORT) {
        ly.down = 0;
    }
    return RET_OK;
}

/* The saved size: 0 Small, 1 Medium, 2 Large (the default, also for a missing or invalid file). Reading never writes. */
int ly_size(void) {
    int c = set_read(LYRSIZE_FILE, '2');
    return c == '0' ? 0 : c == '1' ? 1 : 2;
}

/* The picker's rows: save the size atomically; the size or -1. */
int ly_size_set(int size) { return home_set_digit(LYRSIZE_FILE, LYRSIZE_TMP, size, LY_SIZES - 1); }

/* The page is in front again (np_on_foreground): a size changed in Settings is taken now. The labels' style, height and place, the probe's style and the break cache all follow the size, so
 * everything is laid out again as for new lyrics (ly_tick sees the cleared signature: the lines go back to the current one, as when the page starts). */
void ly_refresh(void) {
    int s, i;
    ly_release(); /* Now Playing is in front: the idle page, if it had the engine, is over */
    if (!ly.box) return;
    s = 2 - ly_size();
    if (s == ly.sz) return;
    ly.sz = s;
    ly.pface = 0xff;
    ly.sig = 0;
    for (i = 0; i < LY_POOL; ++i) {
        ly.line[i] = ly.mv[i] = -1, ly.sel[i] = 0xff, ly.rows[i] = 0, ly.o0[i] = 0;
        ly_hide(i);
    }
    ly.dirty = 1;
}

static void ly_label(void *w) {
    widget_use_style(w, LYSTYLE(0));
    widget_set_sensitive(w, 0);
    widget_set_visible(w, 0, 0);
    label_set_line_wrap(w, 1);
    widget_set_prop_bool(w, "word_wrap", 1);
}

/* The 20 labels, the measuring label and the three dots as children of box (the page's pool); -1 when a label cannot be made (the caller drops box's children: they are ours only). Dots that cannot be made
 * leave the page without them (ly_gap_len is 0 while dot 0 is missing). */
static int ly_make(void *box, void **lab, void **probe, void **dot) {
    int i;
    for (i = 0; i < LY_POOL; ++i) {
        lab[i] = label_create(box, 0, 0, LY_W, LYH);
        if (!lab[i]) return -1;
        ly_label(lab[i]);
    }
    *probe = label_create(box, 0, 0, LY_W, LYH);
    if (!*probe) return -1;
    ly_label(*probe);
    for (i = 0; i < 3; ++i) {
        dot[i] = image_create(box, LY_DOT_X + i * LY_DOT_PITCH, 0, LY_DOT, LY_DOT);
        if (!dot[i]) {
            dot[0] = (void *)0;
            break;
        }
        image_base_set_image(dot[i], "np_dot");
        widget_set_sensitive(dot[i], 0);
        widget_set_visible(dot[i], 0, 0);
    }
    return 0;
}

/* The pool's per-label state of fresh labels (ly_make's): every line unset, the style the first face, opacity 255. */
static void ly_fresh_pool(void) {
    int i;
    for (i = 0; i < LY_POOL; ++i) ly.line[i] = ly.mv[i] = -1, ly.sel[i] = 0, ly.op[i] = 255;
}

static void ly_listen(void *box) {
    widget_on(box, EVT_POINTER_DOWN, ly_on_touch, box); /* a refusal leaves the lines without touch, nothing else */
    widget_on(box, EVT_POINTER_MOVE, ly_on_touch, box);
    widget_on(box, EVT_POINTER_UP, ly_on_touch, box);
    widget_on(box, EVT_POINTER_ABORT, ly_on_touch, box);
}

/* Now Playing's pool, parked while another view (the idle page) has the engine: the widgets only. Everything else of the engine is rebuilt from the stock rows. */
static struct {
    void *win, *box, *probe, *lab[LY_POOL], *dot[3];
    int vh, anc, sz;
} lyp __attribute__((section(".scratch")));

void ly_stop(void) {
    m1_timer_stop(&ly.timer);
    m1_timer_stop(&ly.dtimer);
    memset(&ly, 0, sizeof ly);
    memset(&lyp, 0, sizeof lyp); /* (Now Playing is over: its parked widgets go with it) */
}

void ly_start(void *win) {
    void *fm;
    if (ly.win) ly_stop();
    memset(&ly, 0, sizeof ly);
    memset(&lyp, 0, sizeof lyp);
    ly.sz = 2 - ly_size();
    ly.vh = LY_VIEW_H, ly.anc = LY_ANCHOR;
    ly.src = widget_lookup(win, "scroll_lrc", 1);
    ly.view = widget_lookup(win, "view_lrc", 1);
    ly.box = widget_lookup(win, "np_lyrics", 1);
    if (!ly.src || !ly.view || !ly.box) goto fail;
    fm = font_manager(); /* the coverage gamma on the lyrics face (patch/textgamma.c; a no-op once installed) */
    if (fm) tg_apply(fm, font_manager_get_font(fm, "lyrics", 0));
    if (ly_make(ly.box, ly.lab, &ly.probe, ly.dot) < 0) goto fail;
    ly_fresh_pool();
    ly.win = win;
    ly.cur = -1;
    ly_listen(ly.box);
    widget_set_visible(ly.view, 0, 0);
    widget_set_sensitive(ly.view, 0);
    return;
fail: /* nothing of ours is shown; the stock list stays */
    if (ly.box) widget_destroy_children(ly.box);
    memset(&ly, 0, sizeof ly);
}

/* The engine's current view (0 when it is stopped): the idle page asks whether it still has it. */
void *ly_target(void) { return ly.box; }

/* The stock lyric rows the engine reads (0 for none): the idle page shows its hint with none. */
int ly_lines(void) { return ly.n; }

/* Whether Now Playing's stock rows hold a lyric line right now (the widget's child count, read live; the engine's own count lags until its tick): the idle dispatcher opens the lyrics page only
 * then. 0 with the engine stopped or the rows not built yet. */
int ly_has_rows(void) { return ly.src && widget_count_children(ly.src) > 0; }

/* The idle page takes the engine from Now Playing: the page's box (a scroll_view of its own, h px high, in the window win) gets the pool, the probe and the dots, the engine drives it
 * (anchor 0.35 of h, offset bound 4 h) and a tap on a line seeks nothing. The lines are still read from Now Playing's scroll_lrc, which stock keeps building under another window. Now
 * Playing's own pool is parked, untouched (its widgets are alive and hidden), until ly_release. 0, or -1 with the engine as it was: Now Playing not running its engine, the engine already
 * taken, or a label that cannot be made (the page then drops its box's children and itself). */
int ly_retarget(void *win, void *box, int h) {
    int i, sz;
    void *nl[LY_POOL], *np, *nd[3], *src, *view;
    if (!ly.box || !ly.src || lyp.box || !win || !box || h < 3 * LY_LINE_H) return -1;
    if (ly_make(box, nl, &np, nd) < 0) return -1; /* (nothing of Now Playing's is touched) */
    src = ly.src, view = ly.view, sz = ly.sz;
    lyp.win = ly.win, lyp.box = ly.box, lyp.probe = ly.probe, lyp.vh = ly.vh, lyp.anc = ly.anc, lyp.sz = sz;
    for (i = 0; i < LY_POOL; ++i) lyp.lab[i] = ly.lab[i];
    for (i = 0; i < 3; ++i) lyp.dot[i] = ly.dot[i];
    m1_timer_stop(&ly.timer);
    m1_timer_stop(&ly.dtimer);
    memset(&ly, 0, sizeof ly);
    ly.src = src, ly.view = view;
    ly.sz = sz; /* (the setting cannot change while the page is up) */
    ly.vh = h, ly.anc = h * 35 / 100, ly.noseek = 1;
    for (i = 0; i < LY_POOL; ++i) ly.lab[i] = nl[i];
    ly.probe = np;
    for (i = 0; i < 3; ++i) ly.dot[i] = nd[i];
    ly.win = win, ly.box = box, ly.cur = -1;
    ly_fresh_pool();
    ly_listen(box);
    return 0;
}

/* The page is over (or Now Playing is back in front): Now Playing's pool and view are the engine's again. Its labels are hidden and every cached fact about them forgotten, so the next tick
 * lays the lines out from the stock rows as for new lyrics; the idle page's widgets are not touched (they may be gone). Nothing parked: nothing to do. */
void ly_release(void) {
    int i;
    void *src, *view;
    if (!lyp.box) return;
    m1_timer_stop(&ly.timer);
    m1_timer_stop(&ly.dtimer);
    src = ly.src, view = ly.view;
    memset(&ly, 0, sizeof ly);
    ly.src = src, ly.view = view;
    ly.win = lyp.win, ly.box = lyp.box, ly.probe = lyp.probe, ly.vh = lyp.vh, ly.anc = lyp.anc, ly.sz = lyp.sz;
    for (i = 0; i < LY_POOL; ++i) ly.lab[i] = lyp.lab[i], widget_set_visible(ly.lab[i], 0, 0);
    for (i = 0; i < 3; ++i) {
        ly.dot[i] = lyp.dot[i];
        if (ly.dot[i]) widget_set_visible(ly.dot[i], 0, 0);
    }
    memset(&lyp, 0, sizeof lyp);
    for (i = 0; i < LY_POOL; ++i) ly.line[i] = ly.mv[i] = -1, ly.sel[i] = 0xff, ly.op[i] = 0, ly.rows[i] = 0;
    ly.pface = 0xff;
    ly.cur = -1;
    ly.dirty = 1;
    ly_refresh(); /* a size changed since (it cannot while the page is up, but the file is the truth) */
}
