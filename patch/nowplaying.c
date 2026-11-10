/* M1+ Music Now Playing: the stock playing_page (ui/playing_page.bin, tools/mod_nowplaying.py) gets a cover-tinted
 * background, rounded cover corners that match it, and a remaining-time label that the assets cannot give it.
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * One hook, playing_page_init (0x53d1e4): the page's init, run when Now Playing is built, never at boot or in the
 * main loop. It runs the stock function to completion and then
 * starts a page-scoped 500 ms timer (np_tick) and registers EVT_DESTROY on the window, which removes the timer. It also binds a click handler on the queue
 * button (np_on_queue: our Queue page, patch/queuepage.c; the stock drawer opens when it answers RET_OK).
 * The timer does three things and nothing else:
 *   - the tint: demo writes the track's cover to /tmp/coverpic.jpg or /tmp/externpic.jpg (parseplaycover_thd,
 *     source type word 0x97cad8: 2 and 3/5; 1 while it works); when the file changes (a hash of its bytes) the
 *     picture is decoded by the stock loader, box-averaged to one colour (patch/covercache.c) and np_tone turns that
 *     into a dark, a little desaturated tone that is set as the window's bg_color (widget_set_style); a static
 *     gradient image over it (ui/playing_page.bin, np_tint.png) fades it to black towards the bottom. No cover, or a
 *     source that is not a JPEG file: the neutral dark tone.
 *   - the times: label_playtime and label_playlen carry stock's elapsed and total (stock rewrites both on every tick);
 *     np_elapsed and np_remaining, labels of the asset, show "m:ss" and "-m:ss" from get_playtimeandlength while that
 *     call gives a length, and stock's two show again whenever it does not.
 *   - the info page's lines (np_info): rewritten as "Label: value" with spaced units, only when stock wrote them anew;
 *     the quality line is shown by np_quality, a label of ours, because stock rewrites label_info on every tick.
 * EXPERIMENTAL, the status bar: while the page is in front its bg_color is the page's colour on the first row (np_bar_color),
 * set from np_set_color; EVT_WINDOW_TO_BACKGROUND, the destroy, a replaced page and the tick's top-window check put the stock
 * black back (np_bar_black). Nothing is done unless both window events are registered.
 * The cover is square (AWTK cannot clip an image); its four corners are painted over in the colour the window has
 * there (the tone under the gradient), anti-aliased, from the cover widget's own EVT_AFTER_PAINT: 4 x 12 x 12 pixels
 * of a table np_corner_init computes once, a few dozen canvas_fill_rect calls, and only when the cover repaints.
 * Every failure (a widget of the asset missing, no timer, an unreadable file, an undecodable picture)
 * leaves the stock page as it is, square corners included. docs/architecture.md section 8a.
 */
#include "offsets.inc"
#include "stock.h"
#include "covercache.h"
#include "home.h"
#include "i18n.h"
#include "common.h"
#include "lyrics.h"

extern int
queue_open(void); /* patch/queuepage.c: our Queue page; 0 once it is open, else the stock drawer should open */

/* The queue button (btn_queue, stock handler 0x53b14c: navigator_to("dialog/playqueue_dialog")) opens our Queue page instead. Bound after the stock init, so it runs before the stock
 * handler: RET_STOP keeps the drawer from opening once our page is up, RET_OK lets it open (a stream, a window that will not open). docs/modules/queue.md. */
static int np_on_queue(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    return queue_open() == 0 ? RET_STOP : RET_OK;
}
#include "podcasts.h"

static struct {
    void *fav; /* btn_fav (stock's star button): wears the bookmark styles while an episode plays */
    void *win, *rem, *tot; /* the window, np_remaining (ours), label_playlen (stock) */
    void *el, *pt; /* np_elapsed (ours), label_playtime (stock's elapsed time); both 0 if the page lacks either */
    unsigned timer; /* the repeating np_tick timer */
    unsigned interval; /* interval last accepted by timer_modify */
    unsigned key; /* what the colour was last made from: 0 nothing yet, NP_KEY_NEUTRAL, or a file's hash */
    unsigned sig; /* np_cover_sig at the last full hash: while it is unchanged the file is not hashed again */
    unsigned color; /* the window's bg_color as 0x00BBGGRR (what the corners are painted from) */
    int shown; /* the seconds np_remaining shows, -1 none */
    int eshown; /* the seconds np_elapsed shows, -1 none */
    int own; /* 1: our times are the visible labels, 0: stock's are */
    int fg; /* 1 from the page's start and EVT_WINDOW_TO_FOREGROUND, 0 after EVT_WINDOW_TO_BACKGROUND */
    int barok; /* 1: both window events are registered, so the status bar may be tinted (else it never is) */
    int bar; /* 1: the status bar's bg_color is ours (np_bar_color) and must go back to black */
    void *q; /* np_quality (ours): the quality line shown in place of label_info, 0 if the page lacks it */
    unsigned qdone; /* the hash of the text np_quality holds, 0 none yet */
    int qown; /* 1: np_quality is the visible quality line and label_info is hidden */
    void *info[NP_INFO_N]; /* the info page's labels (np_info_names), 0 for one the page lacks */
    unsigned
        done[NP_INFO_N]; /* the hash of the text each label held after our last look: stock's text, or what we wrote */
    unsigned char corner[NP_ART_R * NP_ART_R]; /* the top left corner's coverage outside the arc, 0..255 */
} np __attribute__((section(".scratch")));

/* A dark, a little desaturated tone of the cover's average colour (r, g, b bytes), as a color_t word
 * (0xAABBGGRR, alpha ff). Value: NP_V_MIN + v * (NP_V_MAX - NP_V_MIN) / 255 for the brightest channel v; every
 * channel keeps NP_SAT_NUM / NP_SAT_DEN of its distance from v (a grey stays grey). A black cover is the neutral
 * tone. With NP_V_MAX 192 the white title and the #AAAAAA lines keep 4.5:1 over the gradient (test/pod/nowplaying.py). */
__attribute__((noinline)) unsigned np_tone(unsigned r, unsigned g, unsigned b) {
    return pod_tone(r, g, b); /* patch/common.c, shared with the album page's tint */
}

/* A clock without a leading zero, as Apple Music prints it: "m:ss", or "h:mm:ss" from an hour on; neg puts a "-" first. */
__attribute__((noinline)) void np_format_clock(char *out, unsigned size, int secs, int neg) {
    const char *sign = neg ? "-" : "";
    if (secs < 0) secs = 0;
    if (secs >= 3600)
        snprintf(out, size, "%s%d:%02d:%02d", sign, secs / 3600, secs / 60 % 60, secs % 60);
    else
        snprintf(out, size, "%s%d:%02d", sign, secs / 60, secs % 60);
}

/* "-m:ss", or "-h:mm:ss" from an hour on: the seconds left. A position past the end shows -0:00. */
__attribute__((noinline)) void np_format_remaining(char *out, unsigned size, int pos, int len) {
    np_format_clock(out, size, len - pos, 1);
}

/* The gradient's alpha on window row y (np_tint.png: black, NP_ALPHA_TOP at the first row to NP_ALPHA_BOTTOM at the last). */
__attribute__((noinline)) unsigned np_alpha(unsigned y) {
    return pod_alpha(y, NP_ALPHA_TOP, NP_ALPHA_BOTTOM, NP_WIN_H);
}

/* color (0x..BBGGRR) as the window shows it on row y: under the black gradient. */
__attribute__((noinline)) unsigned np_shade(unsigned color, unsigned y) {
    return pod_shade(color, y, NP_ALPHA_TOP, NP_ALPHA_BOTTOM, NP_WIN_H);
}

/* The coverage of the area outside a quarter circle of radius NP_ART_R in the corner square of NP_ART_R pixels
 * (the circle's centre at the square's inner corner), 0..255: each pixel is sampled 8 x 8 times. The same numbers
 * as the PNG mask of the earlier builds (test/pod/nowplaying.py). */
__attribute__((noinline)) void np_corner_init(void) { pod_corner_fill(np.corner, NP_ART_R); }

/* The cover widget's EVT_AFTER_PAINT: the four corners, in widget coordinates (the stock paint only translates). */
static int np_on_art_paint(void *ctx, void *e) {
    void *canvas = e ? *(void **)((char *)e + EVENT_PAINT_CANVAS) : (void *)0;
    (void)ctx;
    if (!canvas || !np.win) return RET_OK;
    pod_corners(canvas, np.corner, NP_ART_R, NP_ART, np.color, NP_ART_Y, NP_ALPHA_TOP, NP_ALPHA_BOTTOM, NP_WIN_H);
    return RET_OK;
}

/* FNV-1a over the file's bytes (at most NP_HASH_MAX of them) and its length, never 0; 0 when it cannot be read or is
 * empty. */
__attribute__((noinline)) unsigned np_file_key(const char *path) {
    unsigned char buf[512];
    unsigned h = 2166136261u, total = 0, n, i;
    void *f = fopen(path, "rb");
    if (!f) return 0;
    while (total < NP_HASH_MAX && (n = fread(buf, 1, sizeof buf, f)) > 0) {
        for (i = 0; i < n; ++i) h = (h ^ buf[i]) * 16777619u;
        total += n;
    }
    fclose(f);
    h = (h ^ total) * 16777619u;
    return total ? h | !h : 0;
}

/* EXPERIMENTAL: the status bar takes the colour the page has on its first row, so the bar and the page read as one surface
 * (pod_bar_tint / pod_bar_black, patch/common.c, shared with the album page). np_bar_color is np_shade(color, 0), darkened
 * until the bar's white glyphs keep 4.5:1 (pod_bar_color). */
__attribute__((noinline)) unsigned np_bar_color(unsigned color) { return pod_bar_color(np_shade(color, 0)); }

/* The bar in the page's colour, while the page is in front and its events are registered. */
static void np_bar_apply(void) {
    if (np.barok && np.fg && pod_bar_tint(np.win, np_bar_color(np.color)))
        np.bar = 1; /* a failed call keeps what the bar has (and owes) */
}

/* The stock black, if the bar is ours. Called on every way out: background, destroy, a window above, a replaced page. A page
 * that took the bar over since (the album page on Back) keeps it: only the owner restores. */
static void np_bar_black(void) {
    if (!np.bar) return;
    np.bar = 0;
    pod_bar_black(np.win);
}

/* The timer's check, for what the events missed: the bar is ours only while the page is the top normal window. A dialog
 * (the pull-down) is not a normal window; its EVT_WINDOW_TO_BACKGROUND has cleared np.fg. */
static int np_bar_sync(void) {
    int top = pod_is_top(np.win);
    if (np.bar && !top)
        np_bar_black();
    else if (!np.bar && top)
        np_bar_apply();
    return top;
}

/* The cover's tone as the page shows it: in Light Mode the page is neutral (pal_tone: the dark chromatic tone cannot flip, and the page's white text does). np_tone_raw is
 * the tone as chosen, so np_relight can put the page right when the mode changes while it is open. */
static unsigned np_tone_raw __attribute__((section(".scratch")));

static void np_set_color(unsigned tone) {
    unsigned v[4], color = pal_tone(tone); /* value_t: type at 0, the uint32 at 8 */
    np_tone_raw = tone;
    memset(v, 0, sizeof v);
    value_set_uint32(v, color);
    if (widget_set_style(np.win, "normal:bg_color", v) != RET_OK) return;
    np.color = color & 0xffffff;
    widget_invalidate_force(np.win, (void *)0);
    np_bar_apply();
}

void np_relight(void) {
    if (np.win && np_tone_raw) np_set_color(np_tone_raw); /* (patch/palette.c pal_apply) */
}

/* The cover file of the source type, or NULL for a source with no JPEG file; busy is set while demo is still making it. */
const char *np_cover_file(int *busy) { /* also the mini player bar's (patch/minibar.c) */
    int src = *(volatile int *)COVER_SRC;
    *busy = src == COVER_SRC_BUSY;
    if (src == COVER_SRC_EMBEDDED) return "/tmp/coverpic.jpg";
    if (src == COVER_SRC_FOLDER || src == COVER_SRC_CACHE) return "/tmp/externpic.jpg";
    return (const char *)0;
}

/* The cheap look at the cover (no byte of it is read): a hash of the source type, the file's length (fseek/ftell) and the
 * playing track's path. demo writes a new cover for every track change (and passes through the busy state first), so while
 * all three are as at the last full hash the file is taken as unchanged; any difference sends it to np_file_key. 0: the
 * file cannot be opened (a full look, which tries again too). */
unsigned np_hash(const char *s);
__attribute__((noinline)) unsigned np_cover_sig(const char *path, int src) {
    void *f = fopen(path, "rb");
    void *track;
    long size;
    unsigned h;
    if (!f) return 0;
    size = !fseek(f, 0, 2) ? ftell(f) : -1;
    fclose(f);
    if (size <= 0) return 0;
    track = cc_playing();
    h = np_hash(track ? cc_str(track, REC_PATH) : "");
    h = (h ^ (unsigned)size) * 16777619u;
    h = (h ^ (unsigned)src) * 16777619u;
    return h | !h;
}

static void np_cover(void) {
    int busy;
    const char *path = np_cover_file(&busy);
    unsigned key, sig, px, album, tone;
    char url[80]; /* cc_url's size */
    void *track;
    if (busy) return; /* the file is being replaced: keep the colour */
    if (!path) { /* no picture file: the neutral tone, once */
        if (np.key != NP_KEY_NEUTRAL) np.key = NP_KEY_NEUTRAL, np_set_color(NP_NEUTRAL);
        return;
    }
    sig = np_cover_sig(path, *(volatile int *)COVER_SRC);
    if (sig && sig == np.sig && np.key && np.key != NP_KEY_NEUTRAL)
        return; /* same source, length and track as at the last look */
    track =
        cc_playing(); /* the track's album: its tone may be known (the album page's, an earlier play); an untagged one has no key */
    album = track && *cc_str(track, REC_ALBUM) ? cc_album_key(track) : 0;
    if (sig && album && pod_tone_get(album, &tone)) { /* known: no hash of the file (up to NP_HASH_MAX bytes) */
        np.sig = sig, np.key = NP_KEY_TONE; /* a key no hash is compared equal to: the next full look colours again */
        np_set_color(tone);
        return;
    }
    key = np_file_key(path);
    if (!key) return; /* unreadable: try again next tick */
    if (*(volatile int *)COVER_SRC == COVER_SRC_BUSY) return; /* demo started over while we read */
    np.sig = sig;
    if (key == np.key) return; /* unchanged: nothing to do */
    np.key = key;
    /* the tone cache is RAM only: after a boot the album's Cover Flow cache file (168 px, the album page's source) is a far
     * cheaper decode than the embedded picture (often 600-1400 px); no such file: the playing cover's own file */
    if (album && cc_url(url, album) && cc_decode(np.win, url, 1, 1, 1, &px)) {
        tone = np_tone(px & 255, px >> 8 & 255, px >> 16 & 255);
        np_set_color(tone);
        pod_tone_put(album, tone);
        return;
    }
    snprintf(url, sizeof url, "file://%s", path);
    if (cc_decode(np.win, url, 1, 1, 1, &px)) {
        tone = np_tone(px & 255, px >> 8 & 255, px >> 16 & 255);
        np_set_color(tone);
        pod_tone_put(album, tone);
    }
}

/* np_elapsed and np_remaining are the visible labels while the player gives a length, label_playtime and label_playlen
 * (stock's) otherwise. Stock rewrites its two on its own tick ("01:27"), so ours are separate labels and not rewrites of
 * stock's text, which a paint between the two timers would show. */
static void np_label(int own) {
    if (own == np.own) return;
    np.own = own;
    widget_set_visible(np.rem, own, 0); /* all four are insensitive in the asset, so hidden is also untouchable */
    widget_set_visible(np.tot, !own, 0);
    if (np.el) {
        widget_set_visible(np.el, own, 0);
        widget_set_visible(np.pt, !own, 0);
    }
}

static void np_time(void) {
    int pos = 0, len = 0;
    char text[16];
    if (!np.rem || !np.tot) return;
    if (get_playtimeandlength(&pos, &len) != 1 || len <= 0) {
        np_label(0);
        return;
    }
    if (pos < 0) pos = 0;
    if (pos > len) pos = len;
    if (np.shown != len - pos) {
        np_format_remaining(text, sizeof text, pos, len);
        widget_set_text_utf8(np.rem, text);
        np.shown = len - pos;
    }
    if (np.el && np.eshown != pos) {
        np_format_clock(text, sizeof text, pos, 0);
        widget_set_text_utf8(np.el, text);
        np.eshown = pos;
    }
    np_label(1);
}

/* The info page's lines. Stock writes them when the track changes (show_player_face 0x53bab4 -> the fill 0x539c40, only
 * while its "changed" flags are set; the page timer calls it every tick but it fills only then): "%s:%s" for album,
 * genre, year, location, "%s:%.2fMB" for the size, "%s|%.1fkHz|%dbit|%dkbps" (the quality line, label_info), the label
 * and the "Unknown" of a missing value in the app's language (getFormatString: player_unknown, player_location,
 * player_filesize ...). Each line is rewritten as "Label: value" with spaced units ("35.92 MB", "16-bit", "950 kbps",
 * "44.1 kHz"); the Genre and Year labels are our own keys (stock's "Genres" and "Era" read poorly or wrong in
 * several languages); everything else keeps the stock label and value text, so the language is the stock one.
 * np.done remembers the hash of what each label held after our last look, so a line is rewritten only when stock has
 * written it again, never in a loop; anything that does not look as expected is left as stock wrote it. */
static const char *const np_info_names[NP_INFO_N] = {"label_info", "label_album", "label_genre",
                                                     "label_year", "label_size",  "label_location"};

typedef struct {
    char *p, *end;
} np_out;
#define NP_UNIT_QUALITY 1 /* kHz, kbps and bit after a digit */
#define NP_UNIT_SIZE 2 /* MB after a digit */

static void np_put(np_out *o, char c) {
    if (o->p < o->end) *o->p++ = c;
}
static void np_puts(np_out *o, const char *s) {
    while (*s) np_put(o, *s++);
}
static int np_starts(const char *s, const char *w) {
    while (*w)
        if (*s++ != *w++) return 0;
    return 1;
}
static int np_digit(char c) { return c >= '0' && c <= '9'; }

__attribute__((noinline)) unsigned np_hash(const char *s) {
    unsigned h = 2166136261u;
    while (*s) h = (h ^ (unsigned char)*s++) * 16777619u;
    return h | !h;
}

/* v copied with the unit spaces of `units`; with `spaced` a quality line's bars get a space on each side. */
static void np_value(const char *v, np_out *o, int units, int spaced) {
    const char *p;
    for (p = v; *p; ++p) {
        int digit = p > v && np_digit(p[-1]);
        if (*p == '|' && (units & NP_UNIT_QUALITY)) {
            if (spaced && p > v && p[-1] != ' ') np_put(o, ' ');
            np_put(o, '|');
            if (spaced && p[1] && p[1] != ' ') np_put(o, ' ');
        } else if (digit && (units & NP_UNIT_QUALITY) && np_starts(p, "kHz"))
            np_puts(o, " kHz"), p += 2;
        else if (digit && (units & NP_UNIT_QUALITY) && np_starts(p, "kbps"))
            np_puts(o, " kbps"), p += 3;
        else if (digit && (units & NP_UNIT_QUALITY) && np_starts(p, "bit"))
            np_puts(o, "-bit"), p += 2;
        else if (digit && (units & NP_UNIT_SIZE) && np_starts(p, "MB"))
            np_puts(o, " MB"), p += 1;
        else
            np_put(o, *p);
    }
}

/* The rewritten text of label i from the stock text s, in out; 0 when there is nothing to do or it does not fit. */
__attribute__((noinline)) int np_info_text(int i, const char *s, char *out, unsigned size) {
    np_out o;
    const char *colon = s, *v;
    unsigned len = 0;
    o.p = out, o.end = out + size - 1;
    if (i == 0) {
        np_value(s, &o, NP_UNIT_QUALITY, 1);
        len = (unsigned)(o.p - out);
        if (len > NP_INFO_SPACED) { /* too wide for the label with its bars spaced: tight bars */
            o.p = out;
            np_value(s, &o, NP_UNIT_QUALITY, 0);
        }
    } else {
        while (*colon && *colon != ':') ++colon;
        if (!*colon || colon == s) return 0;
        if (i == 2 || i == 3) {
            const char *t = TR(i == 2 ? "Genre" : "Year");
            if (!t || !*t) return 0;
            np_puts(&o, t);
        } else {
            for (v = s; v < colon; ++v) np_put(&o, *v);
        }
        np_puts(&o, ": ");
        for (v = colon + 1; *v == ' '; ++v) {
        }
        np_value(v, &o, i == 4 ? NP_UNIT_SIZE : 0, 0);
    }
    if (o.p >= o.end) return 0;
    *o.p = 0;
    return 1;
}

/* The quality line. Stock rewrites label_info with the compact text on every page tick, so a rewrite there would
 * alternate with stock's and the centred text would jump between the two widths. np_quality (a label of the asset, the
 * rectangle and look of label_info, hidden and insensitive) carries the formatted line: written only when its text
 * changes, and shown with label_info hidden once it holds text. Stock keeps writing label_info, our data source.
 * A page without np_quality, or a failed read or write, leaves label_info as stock shows it. */
static void np_quality(void) {
    char s[NP_INFO_BUF], out[NP_INFO_BUF + 64];
    const char *text;
    unsigned h;
    int need;
    if (!np.q || !np.info[0]) return;
    need = pod_text_utf8(np.info[0], s, sizeof s);
    if (need > 0 && (unsigned)need < sizeof s) { /* else none, empty or cut short */
        text = np_info_text(0, s, out, sizeof out) ? out : s;
        h = np_hash(text);
        if (h == np.qdone || widget_set_text_utf8(np.q, text) == RET_OK) {
            np.qdone = h;
            goto own;
        }
    }
    /* stock's text could not be shown as ours: give the line back to label_info, so a stale line never stays up */
    if (np.qown) {
        widget_set_visible(np.q, 0, 0);
        widget_set_visible(np.info[0], 1, 0);
    }
    np.qown = 0;
    np.qdone = 0;
    return;
own:
    if (np.qdone && !np.qown) {
        np.qown = 1;
        widget_set_visible(np.q, 1, 0);
        widget_set_visible(np.info[0], 0, 0);
        widget_set_sensitive(np.info[0], 0);
    }
}

static void np_info(void) {
    char s[NP_INFO_BUF], out[NP_INFO_BUF + 64];
    unsigned i, h, n;
    np_quality();
    for (i = 1; i < NP_INFO_N; ++i) { /* 0, the quality line, is np_quality's */
        int need = np.info[i] ? pod_text_utf8(np.info[i], s, sizeof s) : -1;
        /* none, empty, or too long for s (cut short): leave it */
        if (need <= 0 || (unsigned)need >= sizeof s) continue;
        h = np_hash(s);
        if (h == np.done[i]) continue; /* the text we last left (or saw) */
        np.done[i] = h; /* whatever happens below, this text is not looked at again */
        if (!np_info_text((int)i, s, out, sizeof out)) continue;
        for (n = 0; out[n] == s[n] && s[n]; ++n) {
        }
        if (out[n] == s[n]) continue; /* already as wanted */
        if (widget_set_text_utf8(np.info[i], out) == RET_OK) np.done[i] = np_hash(out);
    }
}

/* The favourite button of an episode is a bookmark (docs/modules/podcasts.md "Saved"): stock's star toggles myfav and sets btn_imgfav_style / btn_imgunfav_style (its click handler at once, show_player_face on a
 * track change); while the playing path is an episode the button's style is mapped to btn_imgsave_style / btn_imgunsave_style (the same icons, a bookmark, in the page theme), and back for music. Stock sets its style
 * only when the name differs from the one it wants, so the swap lasts until stock's next fill; our click handler (run after stock's) and the tick put it back. */
static void np_fav_sync(void) {
    const char *cur, *want = (const char *)0;
    void *rec;
    int ep;
    if (!np.fav) return;
    cur = *(const char *const *)((char *)np.fav + WIDGET_STYLE);
    if (!cur) return;
    rec = cc_playing();
    ep = rec && pc_is_path(cc_str(rec, REC_PATH));
    if (ep) {
        if (!strcmp(cur, "btn_imgfav_style"))
            want = "btn_imgsave_style";
        else if (!strcmp(cur, "btn_imgunfav_style"))
            want = "btn_imgunsave_style";
    } else if (!strcmp(cur, "btn_imgsave_style"))
        want = "btn_imgfav_style";
    else if (!strcmp(cur, "btn_imgunsave_style"))
        want = "btn_imgunfav_style";
    if (want) {
        widget_use_style(np.fav, want);
        /* stock's inline pressed icon (the page sets np_unfav_down on the widget) is a star: the bookmark presses to its own outline */
        widget_set_prop_str(np.fav, "style:pressed:icon", ep ? "np_unsave_down" : "np_unfav_down");
    }
}

static int np_on_fav(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    np_fav_sync();
    return RET_OK;
}

static void np_work(void) {
    recent_note(cc_playing()); /* No stock list query: the page underneath owns pdeq_showlist;
                               * the menu's foreground handler resolves the cover key. */
    if (!pod_screen_lit()) return;
    np_cover();
    np_time();
    np_info();
    ly_tick(); /* the lyrics page (patch/lyrics.c) */
    np_fav_sync();
}

static int np_tick(const void *timer) {
    unsigned want;
    (void)timer;
    if (!np.win) return RET_OK; /* not ours any more: a timer that returns RET_OK ends */
    want = pod_screen_lit() ? NP_TICK_MS : POD_DARK_MS;
    if (np.timer && np.interval != want && timer_modify(np.timer, want) == RET_OK) np.interval = want;
    /* another page on top: nothing of this one is seen, np_on_foreground catches up. A dialog (the pull-down) also clears np.fg
     * but leaves the page the top normal window and partly visible, so the work goes on under it. */
    if (!np_bar_sync() && np.barok && !np.fg) return RET_REPEAT;
    np_work();
    return RET_REPEAT;
}

/* The page is over (or replaced): the timer goes, the status bar is black again, the state is cleared. */
static void np_stop(void) {
    np_bar_black();
    ly_stop();
    if (np.timer) timer_remove(np.timer);
    memset(&np, 0, sizeof np);
}

static int np_on_destroy(void *ctx, void *e) {
    (void)e;
    if (ctx != np.win) return RET_OK; /* an earlier page's end: the new one keeps its state */
    np_stop();
    return RET_OK;
}

/* Another window came over the page (a page, a dialog, the pull-down): the bar is black while it covers. */
static int np_on_background(void *ctx, void *e) {
    (void)e;
    if (!np.win || ctx != np.win) return RET_OK;
    np.fg = 0;
    np_bar_black();
    return RET_OK;
}

static int np_on_foreground(void *ctx, void *e) {
    (void)e;
    if (!np.win || ctx != np.win) return RET_OK;
    np_work(); /* the page is current when it reappears (fg still 0: a new colour tints the bar once, below) */
    /* the mode button's picture follows the play mode: stock sets it only in its own click handler, so a mode set on the Queue page (or elsewhere) is shown now */
    stock_np_mode_button(ctx);
    np.fg = 1;
    np_bar_apply();
    return RET_OK;
}

static void np_start(void *win) {
    void *art;
    unsigned n;
    if (np.win) np_stop(); /* an earlier page that never said it was gone */
    np.win = win;
    np.rem = widget_lookup(win, "np_remaining", 1);
    np.tot = widget_lookup(win, "label_playlen", 1);
    np.el = widget_lookup(win, "np_elapsed", 1);
    np.pt = widget_lookup(win, "label_playtime", 1);
    np.fav = widget_lookup(win, "btn_fav", 1);
    if (np.fav) widget_on(np.fav, EVT_CLICK, np_on_fav, (void *)0);
    if (!np.el || !np.pt) np.el = np.pt = (void *)0; /* only the pair is swapped */
    np.shown = np.eshown = -1;
    for (n = 0; n < NP_INFO_N; ++n) np.info[n] = widget_lookup(win, np_info_names[n], 1);
    np.q = widget_lookup(win, "np_quality", 1);
    np.color = NP_NEUTRAL & 0xffffff; /* the asset's window colour */
    if (!widget_on(win, EVT_DESTROY, np_on_destroy, win)) {
        memset(&np, 0, sizeof np);
        return;
    }
    np.timer = timer_add(np_tick, (void *)0, NP_TICK_MS);
    np.interval = NP_TICK_MS;
    if (!np.timer) { /* the page stays stock; the destroy handler finds no window of ours any more */
        memset(&np, 0, sizeof np);
        return;
    }
    art = widget_lookup(win, "img_playcover", 1);
    if (art) {
        np_corner_init();
        widget_on(art, EVT_AFTER_PAINT, np_on_art_paint, (void *)0);
    }
    pod_bind(win, "btn_queue", np_on_queue, (void *)0);
    ly_start(win);
    np.fg = 1;
    np.barok = widget_on(win, EVT_WINDOW_TO_BG, np_on_background, win) &&
               widget_on(win, EVT_WINDOW_TO_FG, np_on_foreground, win);
    np_bar_apply(); /* the asset's tone until the cover's is known */
    np_work();
}

/* The hook (tools/pod.py PLAYING_INIT): stock first, then ours. */
int m1plus_playing_init(void *win, void *ctx) {
    int ret = stock_playing_init_trampoline(win, ctx);
    if (ret == RET_OK && win) np_start(win);
    return ret;
}
