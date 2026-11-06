/* The palette: the interface's colours as the painter gets them, mapped at run time (docs/modules/accent.md).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE). After q2-pod's Light Mode and accents (ringnav_style_color, ringnav_style_gradient, ringnav_image_add, ui_ink in its navigation.c):
 * the same three stock functions are hooked and the same rules apply.
 *
 * One mapping entry point, pal_map, takes the background (PAL_BLACK: as stock; PAL_LIGHT: Light Mode's neutral flip) and the accent (PAL_NEUTRAL: as stock; the others change the role colours: a pressed row, the Now Playing progress fill, and tint the images of tools/palette.py ACCENT_*). Every hook, and the payload's own drawing (ui_ink), goes through it. While the background is Black and the accent Neutral the palette is not
 * active and every hook is a plain pass-through to stock.
 *
 * Three hooks, each pinned by tools/pod.py and a plain pass-through while the palette is not active (also: the kill switch /mnt/mmc/m1plus-off, or the bad-boot note):
 *   style_get_color     (0x659fcc, PIC prologue) every colour a style gives the painter. A neutral colour (channels within LIGHT_SPREAD) is flipped per channel: black becomes
 *                       LIGHT_PAPER, white LIGHT_INK; any other hue and the alpha stay. Only the outermost call maps: a mutable style (inline style:*, widget_set_style) answers from its
 *                       default style through style_get_color again, and the flip is not idempotent. `selected_text_color` is not mapped (a text input's pending letter is near-black
 *                       on its light blue selection, which stays).
 *   style_get_gradient  (0x659f9c, a leaf without prologue: its first two words become the jump, this function is the whole of it) the stops of a background gradient
 *                       (widget_fill_rect asks for bg_color here). style_get_color's own call (return address STYLE_COLOR_GRADIENT_RET) stays unmapped: its colour is mapped once, by the
 *                       colour hook.
 *   image_manager_add   (0x655638, PIC prologue) a decoded theme image before the manager caches it: see pal_image.
 * The payload's own drawing passes ui_ink (the canvas colour setters it calls: ui_fill_color). Album art, covers, wallpapers, photos and videos are never changed.
 *
 * The background (/mnt/data/m1plus/appearance-background: "1" Tinted, "2" Light, "3" Light Auto, anything else or missing Black) is read at the first call. The accent (/mnt/data/m1plus/appearance-accent, one digit) is read with it. While the background is not Black or the accent not Neutral one timer (LIGHT_TICK_MS, UI thread,
 * answering RET_REPEAT) looks at the clock (Auto), the kill switch and the setting again; a change drops the cached images, lets the tinted pages tint again and repaints.
 * Nothing runs per paint but a flag test.
 */
#include "offsets.inc"
#include "stock.h"
#include "home.h"
#include "palette.h"

static struct {
    int read; /* the setting has been read */
    int mode; /* the saved background: 0 Black, 1 Tinted, 2 Light, 3 Light Auto */
    int day; /* Light Auto: the clock says light */
    int on; /* the answer pal_light gives */
    int tint_on; /* effective Tinted: the setting is Tinted, an accent is chosen, and no kill switch */
    int acc; /* the saved accent, 0 .. ACC_COUNT - 1 */
    int acc_on; /* the answer pal_accent gives: the saved accent, or 0 under the kill switch or the bad-boot note */
    unsigned timer;
    int depth; /* style hook nesting */
    void *top; /* the window manager's top main window and its name when pal_exempt last looked, and what it found */
    const char *name;
    int exempt;
    int cover; /* the cover-tinted page the top window is: PAL_COVER_* (0 none) */
} pal __attribute__((section(".scratch")));

static const char keep_names[] = LIGHT_KEEP;
static const char surface_names[] =
    TINT_SURFACE; /* the images the Tinted background tints (tools/palette.py TINT_SURFACE) */
static const char whole_names[] = LIGHT_WHOLE;
static const char exempt_names[] = LIGHT_EXEMPT;
static const char cover_names[] =
    LIGHT_COVER; /* the cover-tinted pages (tools/palette.py COVER_PAGES), in the order of the PAL_COVER_* codes */
static const char fill_names[] =
    ACCENT_FILL; /* the images the accent tints (tools/palette.py ACCENT_*): fills, the switch on, the pressed card pieces */
static const char switch_names[] = ACCENT_SWITCH;
static const char press_names[] = ACCENT_PRESS;
static const char disc_names[] = ACCENT_DISC;
static const char glyph_names[] =
    ACCENT_GLYPH; /* the M1+ Music rows' glyphs, tinted at decode (all but the two tiles) */
static const char glyph_not[] = ACCENT_GLYPH_NOT;
static const char shuf_names[] = ACCENT_SHUFDOWN; /* the pressed Shuffle disc */
static const char tile_names[] = ACCENT_TILE; /* the Podcasts Library tiles (a grey square, a white glyph) */
static const char glyph_stock[] =
    ACCENT_GLYPH_STOCK; /* the stock sheets' row glyphs and selection checks, by exact name */

/* ---------------------------------------------------------------------------
 * The flip (tools/palette.py is its model).
 */
int light_is_neutral(unsigned c) {
    unsigned hi = 0, lo = 255, s, v;
    for (s = 0; s < 24; s += 8) {
        v = c >> s & 255;
        hi = v > hi ? v : hi;
        lo = v < lo ? v : lo;
    }
    return hi - lo <= LIGHT_SPREAD;
}

static unsigned flip_v(unsigned v) { return LIGHT_PAPER - v * (LIGHT_PAPER - LIGHT_INK) / 255; }

unsigned light_flip(unsigned c) {
    unsigned out = c & 0xff000000u, s;
    if (!light_is_neutral(c)) return c;
    for (s = 0; s < 24; s += 8) out |= flip_v(c >> s & 255) << s;
    return out;
}

/* ---------------------------------------------------------------------------
 * The accent (tools/palette.py is its model). Colours of offsets.inc are 0xRRGGBB; color_t words hold r, g, b, a as bytes (red lowest).
 */
#define RGBW(x) (0xff000000u | ((x) & 0xffu) << 16 | ((x) & 0xff00u) | ((x) >> 16 & 0xffu))
#define ACC_CARD_WORD RGBW(ACC_CARD)
#define ACC_NEUTRAL_WORD 0xffeceeeeu /* Neutral's fill, #EEEEEC (not an accent: nothing is mapped) */
static const unsigned acc_word[ACC_COUNT] = {
    ACC_NEUTRAL_WORD, RGBW(ACC_RED),    RGBW(ACC_ORANGE),    RGBW(ACC_GREEN),
    RGBW(ACC_TEAL),   RGBW(ACC_PURPLE), RGBW(ACC_CHAMPAGNE),
};

static void pal_load(void);
static int pal_cover_page(void);

unsigned pal_accent_color(int index) { return index > 0 && index < ACC_COUNT ? acc_word[index] : ACC_NEUTRAL_WORD; }

/* base with pct percent of acc, per channel byte, rounded (the alpha byte is whatever the caller keeps) */
static unsigned pal_mix(unsigned base, unsigned acc, unsigned pct) {
    unsigned out = 0, s, b, a;
    for (s = 0; s < 24; s += 8) {
        b = base >> s & 255, a = acc >> s & 255;
        out |= ((b * (100 - pct) + a * pct + 50) / 100) << s;
    }
    return out;
}

static unsigned pal_tint(unsigned base, unsigned acc) { return pal_mix(base, acc, ACC_TINT); }

/* The Tinted background (tools/palette.py wash): a dark neutral colour (channels within LIGHT_SPREAD, none above ACC_DARK) takes ACC_WASH percent of the accent. The colour itself
 * otherwise. Where it applies is by window, not by colour: pal_cover_page. */
static int pal_dark(unsigned c) {
    unsigned hi = (c & 255) > (c >> 8 & 255) ? (c & 255) : (c >> 8 & 255);
    hi = hi > (c >> 16 & 255) ? hi : (c >> 16 & 255);
    return light_is_neutral(c) && hi <= ACC_DARK;
}

static unsigned pal_wash(unsigned c, unsigned acc) {
    if (!pal_dark(c)) return c;
    return (c & 0xff000000u) | (pal_mix(c, acc, ACC_WASH) & 0xffffffu);
}

/* A role colour (ROLE_*, compared without its alpha, which is kept) becomes the accent's: a pressed row the black page tinted, the progress fill the accent. 1 when c was one. */
static int pal_role(unsigned *c, unsigned acc) {
    unsigned rgb = (*c & 255) << 16 | (*c & 0xff00) | (*c >> 16 & 255), surface;
    if (rgb == ROLE_PROGRESS) {
        *c = (*c & 0xff000000u) | (acc & 0xffffffu);
        return 1;
    }
    if (rgb == ROLE_PRESS_ROW)
        surface = 0;
    else if (rgb == ROLE_PRESS_PILL)
        surface = RGBW(ACC_PILL);
    else if (rgb == ROLE_PRESS_QPILL)
        surface = RGBW(ACC_QPILL);
    else
        return 0;
    *c = (*c & 0xff000000u) |
         (pal_tint(pal.tint_on ? pal_mix(surface, acc, ACC_WASH) : surface, acc) &
          0xffffffu); /* the pressed surface: the rest colour tinted (Tinted: the tinted rest colour, tinted again) */
    return 1;
}

/* ---------------------------------------------------------------------------
 * The palette: the one colour mapping (tools/palette.py map_colour is its model). An accent's role colours first (they are chromatic or accent-coloured, so the background never
 * touches them), else the background (Light: the neutral flip; Black: as it is). Callers test pal_active first where a pass-through must cost nothing; pal_map itself is correct
 * either way.
 */
unsigned pal_map(unsigned c) {
    unsigned acc = pal_accent_color(pal_accent());
    if (acc != ACC_NEUTRAL_WORD && pal_role(&c, acc)) return c;
    if (pal_light())
        c = light_flip(c);
    else if (pal.tint_on && acc != ACC_NEUTRAL_WORD && !pal_cover_page())
        c = pal_wash(c, acc);
    return c;
}

int pal_background(void) { return pal_light() ? PAL_LIGHT : pal.tint_on ? PAL_TINTED : PAL_BLACK; }

int pal_accent(void) {
    if (!pal.read) pal_load();
    return pal.acc_on;
}

int pal_active(void) {
    if (!pal.read) pal_load();
    return pal.on || pal.tint_on || pal.acc_on; /* (tint_on implies acc_on) */
}

/* ---------------------------------------------------------------------------
 * The setting and the clock.
 */
static int pal_read_mode(void) {
    char b[4];
    int fd = open(BG_FILE, O_RDONLY, 0), n;
    if (fd < 0) return 0;
    n = read(fd, b, sizeof b);
    close(fd);
    return n >= 1 && b[0] >= '1' && b[0] <= '3' && (n == 1 || (n == 2 && b[1] == '\n')) ? b[0] - '0' : 0;
}

/* The device's hour is in LIGHT_FROM .. LIGHT_UNTIL - 1 (struct tm: tm_hour at +8). A clock that cannot be read is night, as q2-pod's. */
static int pal_day(void) {
    long t = time((long *)0);
    const int *tm = t < 1577836800L ? (const int *)0 : localtime(&t);
    return tm && tm[2] >= LIGHT_FROM && tm[2] < LIGHT_UNTIL;
}

/* The saved accent: one digit 0 .. ACC_COUNT - 1 (set_read: "x" or "x\n"), else Neutral. */
static int pal_read_accent(void) {
    int c = set_read(ACCENT_FILE, '0') - '0';
    return c >= 0 && c < ACC_COUNT ? c : 0;
}

/* What the settings, the kill switch and the bad-boot note (an earlier boot failed: stock until re-enabled) say now: sets the effective background (pal.on) and accent (pal.acc_on),
 * and tells whether either changed. */
static int pal_refresh(void) {
    int on = 0, acc = 0, tint = 0, changed;
    if (!(home_off() || access(BAD_NOTE, F_OK) == 0)) {
        if (pal.mode == 3) pal.day = pal_day();
        on = pal.mode == 2 || (pal.mode == 3 && pal.day);
        acc = pal.acc;
        tint = pal.mode == 1 && acc; /* Tinted with no accent has no hue to tint with: Black */
    }
    changed = on != pal.on || acc != pal.acc_on || tint != pal.tint_on;
    pal.on = on, pal.acc_on = acc, pal.tint_on = tint;
    return changed;
}

extern void ab_relight(
    void); /* the open cover-tinted pages tint again (patch/albumpage.c, nowplaying.c, podcasts.c; the Daily Mix page, whose art is made once, keeps what it was opened with) */
extern void np_relight(void);
extern void pg_relight(void);

/* The effective mode changed: the cached images were flipped (or not) when they were decoded, so drop them, then repaint everything. */
static void pal_apply(void) {
    void *wm;
    image_manager_unload_all(image_manager());
    ab_relight();
    np_relight();
    pg_relight();
    wm = window_manager();
    if (wm) widget_invalidate_force(wm, (void *)0);
}

static int pal_tick(const void *timer) {
    (void)timer;
    if (pal_refresh()) pal_apply();
    return pal.mode || pal.acc ? RET_REPEAT : RET_OK; /* RET_OK ends it: both settings went back to Off / Neutral */
}

/* Keep one timer while the background is not Black or the accent not Neutral (the clock, the kill switch and the bad-boot note are looked at each tick), none otherwise. */
static void pal_arm(void) {
    int want = pal.mode || pal.acc;
    if (want && !pal.timer)
        pal.timer = timer_add(pal_tick, (void *)0, LIGHT_TICK_MS);
    else if (!want && pal.timer)
        timer_remove(pal.timer), pal.timer = 0;
}

static void pal_load(void) {
    pal.read = 1;
    pal.mode = pal_read_mode();
    pal.acc = pal_read_accent();
    pal_refresh();
    pal_arm();
}

int pal_light(void) {
    if (!pal.read) pal_load();
    return pal.on;
}

int pal_bg_mode(void) {
    if (!pal.read) pal_load();
    return pal.mode;
}

int pal_bg_set(int mode) {
    static const char *const text[4] = {"0\n", "1\n", "2\n", "3\n"};
    if (mode < 0 || mode > 3) return -1;
    if (!pal.read) pal_load();
    if (home_write_atomic(BG_FILE, BG_TMP, text[mode]) != 0) return -1;
    pal.mode = mode;
    if (pal_refresh()) pal_apply();
    pal_arm(); /* (an Off with no accent removes the timer at once: a new arm must not wait for the tick to end it) */
    return mode;
}

int pal_accent_saved(void) {
    if (!pal.read) pal_load();
    return pal.acc;
}

/* The accent setting: saved atomically first (a failed save changes nothing), then applied at once: the cached images were tinted (or not) when they were decoded. */
int pal_accent_set(int index) {
    static const char *const text[ACC_COUNT] = {"0\n", "1\n", "2\n", "3\n", "4\n", "5\n", "6\n"};
    if (index < 0 || index >= ACC_COUNT) return -1;
    if (!pal.read) pal_load();
    if (home_write_atomic(ACCENT_FILE, ACCENT_TMP, text[index]) != 0) return -1;
    pal.acc = index;
    if (pal_refresh()) pal_apply();
    pal_arm();
    return index;
}

unsigned pal_fill(void) { return pal_accent_color(pal_accent()); }

unsigned ui_ink(unsigned c) { return pal_active() && c >> 24 ? pal_map(c) : c; }

/* A colour a cover-tinted page derives from its art (a tone, a shade of it, the status bar's colour) is never a role colour (ROLE_*, compared without alpha): the hooks would take it for
 * a pressed row or a progress fill and turn it into the accent's. One LSB of blue moves it off (#333334 to #333333, #FFFFFE to #FFFFFF). Pure, independent of the palette's state. */
unsigned pal_not_role(unsigned c) {
    unsigned rgb = (c & 255) << 16 | (c & 0xff00) | (c >> 16 & 255);
    if (rgb == ROLE_PRESS_ROW) return c - 0x10000u;
    if (rgb == ROLE_PROGRESS || rgb == ROLE_PRESS_PILL || rgb == ROLE_PRESS_QPILL) return c + 0x10000u;
    return c;
}

unsigned pal_tone(unsigned tone) { return pal_light() ? NP_NEUTRAL : pal_not_role(tone); }

/* ---------------------------------------------------------------------------
 * The style hooks.
 */
extern unsigned *stock_style_color_trampoline(unsigned *, void *, const char *, unsigned);

/* The immersive pages stay as they are (LIGHT_EXEMPT, tools/palette.py: the lock screen and the full-screen cover, which put text over a photo or a cover, the power-off splash, the
 * Pod and Cassette Mode, which have looks of their own): while one is the window manager's top main window the style hooks pass through. The cover-tinted pages (LIGHT_COVER: Now
 * Playing, the album page, the Podcasts Show page, the Daily Mix page) keep their background in the Tinted mode (pal_cover_page) and nothing else changes there. Both answers are kept
 * for as long as the top window and its name are the same pointers, so a style call costs a call to the window manager and two compares. */
enum {
    PAL_COVER_NP = 1,
    PAL_COVER_AB,
    PAL_COVER_PG,
    PAL_COVER_DM,
    PAL_COVER_RN
}; /* tools/palette.py COVER_PAGES, in order */

static void pal_look(void) {
    void *wm = window_manager(), *top;
    const char *name;
    const char *list;
    int i;
    if (!wm) {
        pal.exempt = pal.cover = 0;
        return;
    }
    top = window_manager_get_top_main_window(wm);
    name = top ? *(const char **)((char *)top + W_NAME) : (const char *)0;
    if (top != pal.top || name != pal.name) {
        pal.top = top, pal.name = name, pal.exempt = pal.cover = 0;
        for (list = exempt_names; name && *list; ++list) {
            if (!strcmp(name, list)) pal.exempt = 1;
            while (*list) ++list; /* the next name */
        }
        for (i = 1, list = cover_names; name && *list; ++list, ++i) {
            if (!strcmp(name, list)) pal.cover = i;
            while (*list) ++list;
        }
    }
}

static int pal_exempt(void) {
    pal_look();
    return pal.exempt;
}

extern int ab_has_tone(
    void); /* patch/albumpage.c, patch/podcasts.c: the page shows a cover's tone now (the album page when tinted; the Show page, not the shows list or an episode) */
extern int pg_has_tone(void);

/* The top main window is a cover-tinted page showing a cover's tone: the Tinted wash leaves the background alone (the accent roles still apply). Windows opened over it follow their own name. */
static int pal_cover_page(void) {
    pal_look();
    switch (pal.cover) {
    case PAL_COVER_NP:
    case PAL_COVER_DM:
    case PAL_COVER_RN:
        return 1;
    case PAL_COVER_AB:
        return ab_has_tone();
    case PAL_COVER_PG:
        return pg_has_tone();
    }
    return 0;
}

/* What the style hooks do: the palette is active and the page in front is not exempt. */
static int pal_styled(void) { return pal_active() && !pal_exempt(); }

unsigned *m1plus_style_color(unsigned *color, void *style, const char *name, unsigned fallback) {
    ++pal.depth;
    stock_style_color_trampoline(color, style, name, fallback);
    if (--pal.depth || !color || !pal_styled()) return color;
    if (name && !strcmp(name, "selected_text_color")) return color;
    if (*color >> 24) *color = pal_map(*color);
    return color;
}

/* style_get_gradient(style, name, out): null style, no vtable or no get_gradient slot (+0x18) is "no gradient"; else the stock slot fills out (nr at +8, 8 byte {color, offset} stops
 * from +0xc, at most 8) and returns it. The stops are mapped unless this is a nested call or style_get_color's own. */
void *m1plus_style_gradient(void *style, const char *name, void *out) {
    void *vt = style ? *(void **)style : (void *)0;
    void *(*get)(void *, const char *, void *) =
        vt ? *(void *(**)(void *, const char *, void *))((char *)vt + 0x18) : (void *)0;
    void *g;
    int own, i, nr;
    ++pal.depth;
    g = get ? get(style, name, out) : (void *)0;
    own = --pal.depth || __builtin_return_address(0) == (void *)STYLE_COLOR_GRADIENT_RET;
    if (!own && g && g == out && pal_styled()) {
        nr = *(int *)((char *)g + 8);
        for (i = 0; i < nr && i < 8; ++i) {
            unsigned *stop = (unsigned *)((char *)g + 0xc + 8 * i);
            if (*stop >> 24) *stop = pal_map(*stop);
        }
    }
    return g;
}

/* ---------------------------------------------------------------------------
 * Theme images.
 */
extern int stock_image_add_trampoline(void *, const char *, void *);

static int has_prefix(const char *s, const char *prefixes) {
    const char *p;
    for (p = prefixes; *p;) {
        const char *a = s, *b = p;
        while (*b && *a == *b) ++a, ++b;
        if (!*b) return 1;
        while (*p++) {
        }
    }
    return 0;
}

static int has_slash_colon(const char *s) { /* a cover by path or URL */
    for (; *s; ++s)
        if (*s == '/' || *s == ':') return 1;
    return 0;
}

static unsigned flip_channel(unsigned v, unsigned a, int premul) {
    return premul ? a ? flip_v(v * 255u / a) * a / 255 : 0 : flip_v(v);
}

/* A decoded image of the theme (a plain asset name: a '/' or ':' is a cover by path or URL, never changed) before the manager copies and caches it. LIGHT_KEEP names stay.
 * LIGHT_WHOLE names (plates and cards of ours: the settings cards, glass, sheets) flip every neutral pixel. Any other image flips whole when it has no colour (no opaque pixel more
 * than LIGHT_CHROMA saturated) and is mostly glyph (under 1/LIGHT_SURFACE of its area opaque and darker than LIGHT_GLYPH): white marks, chevrons and status icons turn dark, while a
 * grey or dark disc keeps its white glyph. bitmap_t: w @0, h @4, flags u16 @0xc (BITMAP_PREMULTI), format u16 @0xe; the 32 bit formats 1 - 4 hold r, g, b, a at BITMAP_RGBA_AT. */
static void light_image(const char *name, void *bitmap) {
    static const unsigned char at[4][4] = BITMAP_RGBA_AT;
    unsigned format, stride, y, x, hue = 0, solid = 0, c, a, r, g, b;
    int w, h, whole, premul;
    unsigned char *px, *p;
    const unsigned char *o;
    const char *s;
    if (!name || !*name || !bitmap) return;
    for (s = name; *s && *s != '/' && *s != ':'; ++s) {
    }
    if (*s || has_prefix(name, keep_names)) return;
    format = *(unsigned short *)((char *)bitmap + BITMAP_FORMAT) - 1u;
    w = *(int *)bitmap, h = *(int *)((char *)bitmap + 4);
    if (format >= 4 || w <= 0 || h <= 0 || w > 4096 || h > 4096) return;
    stride = bitmap_get_line_length(bitmap);
    if (stride < (unsigned)w * 4) return;
    whole = has_prefix(name, whole_names);
    premul = *(unsigned short *)((char *)bitmap + BITMAP_FLAGS) & BITMAP_PREMULTI;
    px = bitmap_lock_buffer_for_write(bitmap);
    if (!px) return;
    o = at[format];
    if (!whole) {
        for (y = 0; !hue && y < (unsigned)h; ++y)
            for (p = px + y * stride, x = 0; x < (unsigned)w; ++x, p += 4) {
                a = p[o[3]], r = p[o[0]], g = p[o[1]], b = p[o[2]];
                if (a < 128) continue;
                if (premul) r = r * 255 / a, g = g * 255 / a, b = b * 255 / a;
                c = (r > g ? r > b ? r : b : g > b ? g : b) - (r < g ? r < b ? r : b : g < b ? g : b);
                hue |= c > LIGHT_CHROMA;
                solid += (r * 299 + g * 587 + b * 114) / 1000 < LIGHT_GLYPH;
            }
        if (hue || solid * LIGHT_SURFACE >= (unsigned)w * (unsigned)h) {
            bitmap_unlock_buffer(bitmap);
            return;
        }
    }
    for (y = 0; y < (unsigned)h; ++y)
        for (p = px + y * stride, x = 0; x < (unsigned)w; ++x, p += 4) {
            a = p[o[3]];
            if (!a) continue;
            if (whole) {
                r = p[o[0]], g = p[o[1]], b = p[o[2]];
                if (premul) r = r * 255 / a, g = g * 255 / a, b = b * 255 / a;
                if ((r > g ? r > b ? r : b : g > b ? g : b) - (r < g ? r < b ? r : b : g < b ? g : b) > LIGHT_SPREAD)
                    continue;
            }
            p[o[0]] = (unsigned char)flip_channel(p[o[0]], a, premul);
            p[o[1]] = (unsigned char)flip_channel(p[o[1]], a, premul);
            p[o[2]] = (unsigned char)flip_channel(p[o[2]], a, premul);
        }
    bitmap_unlock_buffer(bitmap);
}

/* An exact name from a NUL-ended list. */
static int in_names(const char *s, const char *list) {
    for (; *list; ++list) {
        if (*s == *list && !strcmp(s, list)) return 1; /* (the first letter alone rejects nearly every name) */
        while (*list) ++list; /* the next name */
    }
    return 0;
}

/* The accent's tint of a decoded image (tools/palette.py accent_pixel is the model): kind 0 FILL (slider and progress fills, the check, the playing wave: a pixel as light as the fill or
 * lighter becomes the accent, one at the track grey or darker stays, and one between (an antialiased edge over the track) moves by the same share of the way from the fill to the accent), 1 SWITCH (the track #EEEEEC to the accent, the knob #141414 to white), 2 PRESS (the pressed card piece: mix(card, accent)), 4 GLYPH (a row glyph: every colour the accent), 6 SHUFDOWN (the album page's pressed Shuffle disc: the grey disc becomes the tinted disc, the white glyph stays), 5 TILE (a Podcasts Library tile: the #1E1E1E square stays, white goes to the accent, between by lightness), 3 DISC (a pull-down ON tile: white to the accent, the #141414 glyph stays, between by lightness).
 * Alpha stays; a clear pixel is left. Premultiplied pixels are converted to straight and back. */
static void accent_image(int kind, void *bitmap, unsigned acc) {
    static const unsigned char at[4][4] = BITMAP_RGBA_AT;
    unsigned format, stride, y, x, i, a, v[3], t, card, w4, h4;
    int premul;
    unsigned char *px, *p;
    const unsigned char *o;
    format = *(unsigned short *)((char *)bitmap + BITMAP_FORMAT) - 1u;
    w4 = *(unsigned *)bitmap, h4 = *(unsigned *)((char *)bitmap + 4);
    if (format >= 4 || !w4 || !h4 || w4 > 4096 || h4 > 4096) return;
    stride = bitmap_get_line_length(bitmap);
    if (stride < w4 * 4) return;
    premul = *(unsigned short *)((char *)bitmap + BITMAP_FLAGS) & BITMAP_PREMULTI;
    px = bitmap_lock_buffer_for_write(bitmap);
    if (!px) return;
    o = at[format];
    card = kind == 6 ? RGBW(ACC_SHUF) : ACC_CARD_WORD; /* the surface that is pressed: the card, or the Shuffle disc */
    card = pal_tint(pal.tint_on ? pal_mix(card, acc, ACC_WASH) : card,
                    acc); /* (Tinted: the tinted surface, tinted again) */
    for (y = 0; y < h4; ++y)
        for (p = px + y * stride, x = 0; x < w4; ++x, p += 4) {
            a = p[o[3]];
            if (!a) continue;
            for (i = 0; i < 3; ++i) {
                v[i] = p[o[i]];
                if (premul) v[i] = v[i] * 255 / a > 255 ? 255 : v[i] * 255 / a;
            }
            if (kind == 4) {
                for (i = 0; i < 3; ++i) v[i] = acc >> (8 * i) & 255;
            } else if (kind == 2) {
                for (i = 0; i < 3; ++i) v[i] = card >> (8 * i) & 255;
            } else if (
                kind ==
                6) { /* the pressed Shuffle disc: the grey disc becomes the tinted disc, the white glyph stays white, between by lightness */
                t = v[0] <= ACC_SHUF_DOWN_R ? 0 : (v[0] - ACC_SHUF_DOWN_R) * 255 / (255 - ACC_SHUF_DOWN_R);
                if (t > 255) t = 255;
                for (i = 0; i < 3; ++i) {
                    unsigned b = card >> (8 * i) & 255;
                    v[i] = b + (255 - b) * t / 255;
                }
            } else if (kind == 0) {
                if (v[0] >= ACC_FILL_R) {
                    for (i = 0; i < 3; ++i) v[i] = acc >> (8 * i) & 255; /* the fill itself (or white: the check) */
                } else if (
                    v[0] >
                    ACC_TRACK_R) { /* a pixel between the track and the fill (a bar's antialiased edge over its grey track): the same share t of the fill, as the accent over the track */
                    t = (v[0] - ACC_TRACK_R) * 255 / (ACC_FILL_R - ACC_TRACK_R);
                    for (i = 0; i < 3; ++i) {
                        int dv = ((int)(acc >> (8 * i) & 255) - (int)(ACC_NEUTRAL_WORD >> (8 * i) & 255)) * (int)t;
                        dv = dv >= 0 ? dv / 255 : -(-dv / 255);
                        dv += (int)v[i];
                        v[i] = dv < 0 ? 0 : dv > 255 ? 255 : (unsigned)dv;
                    }
                }
            } else if (kind == 3 ||
                       kind == 5) { /* the fixed end: the disc's #141414 glyph, or the tile's #1E1E1E square */
                unsigned lo = kind == 3 ? ACC_KNOB_R : ACC_TILE_R;
                t = v[0] <= lo ? 0 : (v[0] - lo) * 255 / (255 - lo);
                if (t > 255) t = 255;
                for (i = 0; i < 3; ++i) {
                    int c = (int)(acc >> (8 * i) & 255), dv = (c - (int)lo) * (int)t;
                    dv = dv >= 0 ? dv / 255 : -(-dv / 255);
                    v[i] = (unsigned)((int)lo + dv);
                }
            } else {
                t = v[0] >= ACC_FILL_R ? 0 : (ACC_FILL_R - v[0]) * 255 / (ACC_FILL_R - ACC_KNOB_R);
                if (t > 255) t = 255;
                for (i = 0; i < 3; ++i) {
                    unsigned c = acc >> (8 * i) & 255;
                    v[i] = c + (255 - c) * t / 255;
                }
            }
            for (i = 0; i < 3; ++i) p[o[i]] = (unsigned char)(premul ? v[i] * a / 255 : v[i]);
        }
    bitmap_unlock_buffer(bitmap);
}

/* The Tinted background's surfaces (TINT_SURFACE: the settings cards, the sheets, the mini player's glass, the navbar's fade): every opaque-enough dark neutral pixel takes ACC_WASH percent
 * of the accent (tools/palette.py wash_pixel); light pixels, hues and alpha stay. Premultiplied pixels are converted to straight and back. */
static void tint_image(void *bitmap, unsigned acc) {
    static const unsigned char at[4][4] = BITMAP_RGBA_AT;
    unsigned format, stride, y, x, i, a, v[3], w4, h4, hi, lo;
    int premul;
    unsigned char *px, *p;
    const unsigned char *o;
    format = *(unsigned short *)((char *)bitmap + BITMAP_FORMAT) - 1u;
    w4 = *(unsigned *)bitmap, h4 = *(unsigned *)((char *)bitmap + 4);
    if (format >= 4 || !w4 || !h4 || w4 > 4096 || h4 > 4096) return;
    stride = bitmap_get_line_length(bitmap);
    if (stride < w4 * 4) return;
    premul = *(unsigned short *)((char *)bitmap + BITMAP_FLAGS) & BITMAP_PREMULTI;
    px = bitmap_lock_buffer_for_write(bitmap);
    if (!px) return;
    o = at[format];
    for (y = 0; y < h4; ++y)
        for (p = px + y * stride, x = 0; x < w4; ++x, p += 4) {
            a = p[o[3]];
            if (!a) continue;
            hi = 0, lo = 255;
            for (i = 0; i < 3; ++i) {
                v[i] = p[o[i]];
                if (premul) v[i] = v[i] * 255 / a > 255 ? 255 : v[i] * 255 / a;
                hi = v[i] > hi ? v[i] : hi, lo = v[i] < lo ? v[i] : lo;
            }
            if (hi > ACC_DARK || hi - lo > LIGHT_SPREAD) continue;
            for (i = 0; i < 3; ++i) {
                v[i] = (v[i] * (100 - ACC_WASH) + (acc >> (8 * i) & 255) * ACC_WASH + 50) / 100;
                p[o[i]] = (unsigned char)(premul ? v[i] * a / 255 : v[i]);
            }
        }
    bitmap_unlock_buffer(bitmap);
}

/* The palette's image rule: the accent's tint of the images it owns (tinted instead of flipped, whatever the background), else the background's (Light: light_image). */
static void pal_image(const char *name, void *bitmap) {
    int kind = -1;
    unsigned acc;
    if (!name || !*name || !bitmap) return;
    acc = pal_accent_color(pal_accent());
    if (acc != ACC_NEUTRAL_WORD) {
        if (in_names(name, fill_names))
            kind = 0;
        else if (in_names(name, switch_names))
            kind = 1;
        else if (in_names(name, press_names))
            kind = 2;
        else if (in_names(name, disc_names))
            kind = 3;
        else if (in_names(name, tile_names))
            kind = 5;
        else if (in_names(name, shuf_names))
            kind = 6;
        else if ((has_prefix(name, glyph_names) && !in_names(name, glyph_not)) || in_names(name, glyph_stock))
            kind = 4;
    }
    if (kind >= 0)
        accent_image(kind, bitmap, acc);
    else if (pal_light())
        light_image(name, bitmap);
    else if (pal.tint_on && has_prefix(name, surface_names) && !has_slash_colon(name))
        tint_image(bitmap, acc);
}

int m1plus_image_add(void *manager, const char *name, void *bitmap) {
    if (pal_active()) pal_image(name, bitmap);
    return stock_image_add_trampoline(manager, name, bitmap);
}
