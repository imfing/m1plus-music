/* Small helpers every page of the payload shares (patch/common.h).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 */
#include "offsets.inc"
#include "stock.h"
#include "common.h"
#include "home.h"
#include "utf8.h"
#include "radio.h"
#include "shot.h"
#include "covercache.h"
#include "palette.h"

/* The library scan's folder walk (tools/pod.py SCAN_SITE, docs/modules/payload.md hook 5): stock skips a directory entry when strcmp(name, ".") is 0 (and then ".." and a list of
 * system folders); the call is replaced by `jal m1_scan_dir`, whose delay slot still loads a1 = ".". A hidden folder (a name starting with '.') counts as a match, so
 * /mnt/mmc/.m1plus/ (our cache, covers and downloads) never joins Songs and Albums; anything else is stock's strcmp. (q2-pod's ringnav_scan_dir.) */
__attribute__((noinline)) int m1_scan_dir(const char *name, const char *dot) {
    return name[0] == '.' ? 0 : strcmp(name, dot);
}

static int m1_lower(int c) { return c >= 'A' && c <= 'Z' ? c + 32 : c; }

/* An artist field's names (docs/modules/artists.md "Separators"). One pass over the field finds each separator the caller's mask allows; the parts are slices of the
 * caller's string (nothing is copied or allocated), trimmed, and a part that is empty or repeats an earlier one (ASCII case folded) is dropped. */
static const char *const m1_artist_exceptions[] = {
    "AC/DC",        "Simon & Garfunkel",      "Earth, Wind & Fire", "Crosby, Stills, Nash & Young",
    "Hall & Oates", "Florence + the Machine", "Tyler, the Creator", 0};

const char *const *m1_artist_split_exceptions(void) { return m1_artist_exceptions; }

/* The symbol separator at s: its length (0: none) and bit. ASCII and the full-width / CJK forms. */
static unsigned m1_split_symbol(const unsigned char *s, unsigned *bit) {
    switch (s[0]) {
    case ';':
        *bit = M1_SPLIT_SEMICOLON;
        return 1;
    case '/':
        *bit = M1_SPLIT_SLASH;
        return 1;
    case '&':
        *bit = M1_SPLIT_AMPERSAND;
        return 1;
    case ',':
        *bit = M1_SPLIT_COMMA;
        return 1;
    case '+':
        *bit = M1_SPLIT_PLUS;
        return 1;
    case 0xc3:
        if (s[1] != 0x97) return 0;
        *bit = M1_SPLIT_X; /* x with the multiplication sign */
        return 2;
    case 0xe3:
        if (s[1] != 0x80 || s[2] != 0x81) return 0;
        *bit = M1_SPLIT_COMMA; /* the ideographic comma */
        return 3;
    case 0xef:
        if (s[1] != 0xbc) return 0;
        switch (s[2]) {
        case 0x9b:
            *bit = M1_SPLIT_SEMICOLON;
            return 3;
        case 0x8f:
            *bit = M1_SPLIT_SLASH;
            return 3;
        case 0x86:
            *bit = M1_SPLIT_AMPERSAND;
            return 3;
        case 0x8c:
            *bit = M1_SPLIT_COMMA;
            return 3;
        case 0x8b:
            *bit = M1_SPLIT_PLUS;
            return 3;
        }
    }
    return 0;
}

/* word, bit, flags: 1 = a full stop may follow, 2 = ASCII case matters, 4 = also splits inside brackets (it opens the list there) */
static const struct {
    const char *w;
    unsigned char len, flags;
    unsigned short bit;
} m1_split_words[] = {{"featuring", 9, 5, M1_SPLIT_FEAT}, {"feat", 4, 5, M1_SPLIT_FEAT}, {"ft", 2, 5, M1_SPLIT_FEAT},
                      {"versus", 6, 5, M1_SPLIT_VS},      {"vs", 2, 5, M1_SPLIT_VS},     {"x", 1, 2, M1_SPLIT_X},
                      {"with", 4, 0, M1_SPLIT_WITH},      {"and", 3, 0, M1_SPLIT_AND}};

/* The word separator at field[i] (the caller checked the byte before it): its length with a full stop it takes, its bit, whether it splits inside brackets; 0 for none. */
static unsigned m1_split_word(const char *f, unsigned i, unsigned *bit, unsigned *inner) {
    unsigned w, k;
    for (w = 0; w < sizeof m1_split_words / sizeof *m1_split_words; ++w) {
        unsigned l = m1_split_words[w].len, fl = m1_split_words[w].flags;
        for (k = 0; k < l; ++k) {
            int c = (unsigned char)f[i + k];
            if (!(fl & 2)) c = m1_lower(c);
            if (c != (unsigned char)m1_split_words[w].w[k]) break;
        }
        if (k < l) continue;
        *bit = m1_split_words[w].bit;
        *inner = (fl & 4) != 0;
        if (f[i + l] == ' ') return l;
        if ((fl & 1) && f[i + l] == '.') return l + 1;
        return 0;
    }
    return 0;
}

static int m1_split_same(const char *a, const char *b, unsigned n) {
    unsigned i;
    for (i = 0; i < n; ++i)
        if (m1_lower((unsigned char)a[i]) != m1_lower((unsigned char)b[i])) return 0;
    return 1;
}

/* Whether byte i of field lies inside an occurrence of one of the exception names. */
static int m1_split_protected(const char *f, unsigned len, unsigned i, const char *const *ex) {
    for (; ex && *ex; ++ex) {
        unsigned el = (unsigned)strlen(*ex), j = i + 1 > el ? i + 1 - el : 0;
        for (; j <= i && j + el <= len; ++j)
            if (m1_split_same(f + j, *ex, el)) return 1;
    }
    return 0;
}

static int m1_split_open(char c) { return c == '(' || c == '['; }
static int m1_split_close(char c) { return c == ')' || c == ']'; }

/* Add f[a, b) as a name: trimmed of spaces and of the brackets the cut left unmatched (a trailing opener, a leading closer, a closer or opener the part does not balance), nothing when
 * it is then empty or repeats a name already in out[0, n). Returns 1 when added. */
static int m1_split_add(const char *f, unsigned a, unsigned b, m1_artist_span *out, unsigned n) {
    unsigned i;
    for (;;) {
        unsigned opens = 0, closes = 0;
        while (a < b && (f[a] == ' ' || f[a] == '\t')) ++a;
        while (b > a && (f[b - 1] == ' ' || f[b - 1] == '\t')) --b;
        if (a >= b) return 0;
        for (i = a; i < b; ++i) opens += m1_split_open(f[i]), closes += m1_split_close(f[i]);
        if (m1_split_open(f[b - 1]) || (closes > opens && m1_split_close(f[b - 1])))
            --b;
        else if (m1_split_close(f[a]) || (opens > closes && m1_split_open(f[a])))
            ++a;
        else
            break;
    }
    for (i = 0; i < n; ++i)
        if (out[i].n == b - a && m1_split_same(out[i].p, f + a, b - a)) return 0;
    out[n].p = f + a;
    out[n].n = b - a;
    return 1;
}

int m1_artist_split(const char *field, m1_artist_span *out, int max, const m1_split_opts *opts) {
    unsigned len, start = 0, i = 0, n = 0, depth = 0, seen = 0;
    unsigned mask = opts ? opts->mask : M1_SPLIT_DEFAULT;
    const char *const *ex = opts ? opts->except : 0;
    if (!field || !out || max <= 0) return 0;
    len = (unsigned)strlen(field);
    for (;;) {
        unsigned sl = 0, bit = 0, inner = 0;
        if (i < len) {
            char c = field[i];
            if (m1_split_open(c)) {
                if (depth < 31) seen &= ~(1u << ++depth);
            } else if (m1_split_close(c)) {
                if (depth) --depth;
            } else {
                /* (an exception only ever suppresses a separator, so it is looked for where one was found: a field with none costs no exception scan) */
                sl = m1_split_symbol((const unsigned char *)field + i, &bit);
                if (sl) {
                    if (!(mask & bit) || (depth && (bit == M1_SPLIT_X || !(seen >> depth & 1))) ||
                        m1_split_protected(field, len, i, ex))
                        sl = 0;
                } else if (i && (field[i - 1] == ' ' || m1_split_open(field[i - 1]))) {
                    sl = m1_split_word(field, i, &bit, &inner);
                    if (sl && (!(mask & bit) || (depth && !inner) || m1_split_protected(field, len, i, ex))) sl = 0;
                    if (sl && depth) seen |= 1u << depth;
                }
            }
        }
        if (i >= len || sl) {
            n += (unsigned)m1_split_add(field, start, i, out, n);
            if (i >= len || n >= (unsigned)max) break;
            start = i += sl;
        } else {
            ++i;
        }
    }
    return (int)n;
}

/* A widget's text as UTF-8 in buf (size bytes, never written past): stock widget_get_text_utf8 ignores its size for a wide text (tk_utf8_from_utf16 at 0x70e790 overwrites
 * its out_size argument before reading it, counts the whole encoding and writes all of it), so a long lyric line or tag overran the caller's stack buffer. This reads the wide
 * text (widget_get_text) and encodes it here: a text that does not fit is cut at a character boundary, buf is always NUL terminated (size >= 1). Returns the length the whole
 * text needs (snprintf's), so the text fitted when the result is below size; -1 when the widget has no text (buf is then empty). A code point beyond U+10FFFF or a surrogate is U+FFFD. */
int m1_text_utf8(void *widget, char *buf, unsigned size) {
    const unsigned *t = widget ? widget_get_text(widget) : (const unsigned *)0;
    unsigned n = 0, w = 0, c, len, cut = 0;
    char e[4];
    if (!size) return -1;
    buf[0] = 0;
    if (!t) return -1;
    for (; (c = *t) != 0; ++t) {
        if (c > 0x10ffff || (c >= 0xd800 && c < 0xe000)) c = 0xfffd;
        len = m1_utf8_put(e, c);
        /* (room for the character and the NUL; once one does not fit, the rest only counts) */
        if (!cut && w + len < size) {
            unsigned k;
            for (k = 0; k < len; ++k) buf[w + k] = e[k];
            buf[w += len] = 0;
        } else {
            cut = 1;
        }
        n += len;
    }
    return (int)n;
}

/* The n bytes at in with each %XX (hex digits of either case) decoded to its byte, into out (size bytes, never written past, always NUL terminated; size >= 1). A '%' not followed
 * by two hex digits stays as it is. Stops when the next byte does not fit (a cut can split a UTF-8 character: the caller trims). Returns the length written. */
unsigned m1_url_decode(char *out, unsigned size, const char *in, unsigned n) {
    unsigned o = 0, i;
    if (!size) return 0;
    for (i = 0; i < n && o + 1 < size; ++i) {
        unsigned char c = (unsigned char)in[i];
        if (c == '%' && i + 2 < n) {
            int h = m1_hexval((unsigned char)in[i + 1]), l = m1_hexval((unsigned char)in[i + 2]);
            if (h >= 0 && l >= 0) c = (unsigned char)(h << 4 | l), i += 2;
        }
        out[o++] = (char)c;
    }
    out[o] = 0;
    return o;
}

int m1_screen_lit(void) { return *(volatile unsigned char *)BACKLIGHT_STATUS != 0; }

/* Whether the card is mounted: its mount point is another file system than the one it is in (an unmounted /mnt/mmc is a plain directory on the internal flash). */
int m1_card_mounted(void) {
    unsigned a[32], b[32];
    memset(a, 0, sizeof a);
    memset(b, 0, sizeof b);
    if (statfs(SHOT_CARD, a) || statfs(SHOT_PARENT, b)) return 0;
    return !(a[0] == b[0] && a[8] == b[8] &&
             a[9] == b[9]); /* f_type, f_fsid (MIPS o32 statfs words 0, 8, 9): the same, nothing mounted */
}

int m1_write_all(int fd, const void *data, unsigned n) {
    unsigned at = 0;
    while (at < n) {
        int w = write(fd, (const char *)data + at, n - at);
        if (w <= 0) return 0;
        at += (unsigned)w;
    }
    return 1;
}

int m1_commit(int fd, int ok, const char *tmp, const char *path) {
    ok = ok && fsync(fd) == 0;
    ok = close(fd) == 0 && ok;
    if (ok && rename(tmp, path) != 0) ok = 0;
    if (!ok) unlink(tmp);
    return ok;
}

int m1_save_as(const char *path, const char *tmp, unsigned mode, const void *data, unsigned n) {
    int fd = open(tmp, O_WRONLY | O_CREAT | O_TRUNC, mode);
    return fd >= 0 && m1_commit(fd, m1_write_all(fd, data, n), tmp, path);
}

int m1_save(const char *path, unsigned mode, const void *data, unsigned n) {
    char tmp[HOME_TMP_MAX];
    return home_tmp_path(tmp, path) == 0 && m1_save_as(path, tmp, mode, data, n);
}

int m1_sync_dir(const char *dir) {
    int d = open(dir, O_RDONLY, 0), ok;
    if (d < 0) return 0;
    ok = fsync(d) == 0;
    return close(d) == 0 && ok;
}

/* The one writer of the payload's card files: CARD_DIR then dir made (EEXIST is fine; a failure shows in the open), a then b (either may
 * be empty) into path + ".tmp", fsync, rename onto path, fsync of dir. 0 on success; 1 when path was replaced but the directory's fsync failed (the
 * new bytes are there, a power cut may lose the rename); -1, path untouched, on any earlier failure or while the card is not mounted. */
int m1_card_write(const char *dir, const char *path, const void *a, unsigned na, const void *b, unsigned nb) {
    char tmp[HOME_TMP_MAX];
    int fd;
    if (!m1_card_mounted()) return -1; /* never write to the internal flash under the mount point */
    if (home_tmp_path(tmp, path) != 0) return -1;
    mkdir(CARD_DIR, 0755);
    if (strcmp(dir, CARD_DIR)) mkdir(dir, 0755);
    fd = open(tmp, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (fd < 0) return -1;
    if (!m1_commit(fd, m1_write_all(fd, a, na) && m1_write_all(fd, b, nb), tmp, path)) return -1;
    return m1_sync_dir(dir) ? 0 : 1;
}

unsigned m1_urlenc(char *out, unsigned cap, unsigned used, const char *s) {
    static const char hex[] = "0123456789ABCDEF";
    unsigned i;
    if (!s) return 0;
    for (i = 0; s[i]; ++i) {
        unsigned c = (unsigned char)s[i];
        if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '-' || c == '_' ||
            c == '.' || c == '~') {
            if (used + 1 >= cap) return 0;
            out[used++] = (char)c;
        } else {
            if (used + 3 >= cap) return 0;
            out[used++] = '%', out[used++] = hex[c >> 4], out[used++] = hex[c & 15];
        }
    }
    return used;
}

/* KB free for a non-root user on the file system of path (MIPS o32 statfs: f_bsize is word 1, f_bavail word 7); 0 when statfs fails. */
int m1_free_kb(const char *path, unsigned *kb) {
    unsigned fs[32];
    unsigned long long b;
    memset(fs, 0, sizeof fs);
    if (statfs(path, fs)) return 0;
    b = (unsigned long long)fs[7] * fs[1] >> 10;
    *kb = b > 0xffffffffull ? 0xffffffffu : (unsigned)b;
    return 1;
}

int m1_on_back(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    navigator_back();
    return RET_OK;
}

/* Every Now Playing entry of our pages: Radio's page while a station plays, else stock's player (the trampoline: the hook on stock's handler would decide again). */
void m1_open_now_playing(void) {
    if (!rn_open_if_active()) stock_backtoplayer_trampoline((void *)0, (void *)0);
}

int m1_on_player(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    m1_open_now_playing();
    return RET_OK;
}

int m1_is_type(void *w, const char *type) {
    const char *t = w ? widget_get_type(w) : (const char *)0;
    return t && strcmp(t, type) == 0;
}

/* The topmost opened window called name in the window manager is brought to the front the way stock brings the player back (window_manager_switch_to, nothing closed, Back returns to where the user came from).
 * Stock's navigator_to opens a page that has no single_instance property afresh each time, so a page left in the stack (the top-right Now Playing button restacks the player over it) would be stacked twice. */
void *m1_restack_window(const char *name) {
    void *wm = window_manager();
    unsigned n;
    if (!wm) return (void *)0;
    for (n = widget_count_children(wm); n--;) {
        void *w = widget_get_child(wm, n);
        const char *nm = w ? *(const char **)((char *)w + WIDGET_NAME) : (const char *)0;
        if (nm && !strcmp(nm, name)) {
            if (!widget_is_window_opened(w)) return (void *)0; /* (a page that is closing is gone) */
            return window_manager_switch_to(wm, window_manager_get_top_window(wm), w, 0) == RET_OK ? w : (void *)0;
        }
    }
    return (void *)0;
}

/* The opened windows above win in the window manager closed by handle, top first, so win is in front once they go (AWTK destroys a closed window later). Dialogs and the status bar stay: a sheet's
 * owner closes it (Now Playing's More sheet, patch/playmore.c pm_on_goep, after podcasts_go). The Control Center's shortcuts reuse a page left in the stack this way, whatever covers it (Now Playing,
 * the Queue over it, ..). */
void m1_uncover(void *win) {
    void *wm = window_manager();
    unsigned n;
    if (!wm || !win) return;
    for (n = widget_count_children(wm); n--;) {
        void *w = widget_get_child(wm, n);
        if (w == win) return;
        if (w && m1_is_type(w, "window") && widget_is_window_opened(w)) window_close(w);
    }
}

/* A stock page opened the way the stock lists would, without stacking a second window of a page that has no single_instance property: the opened window is restacked, else navigator_to(path).
 * window is NULL for a page that must be opened afresh because its init starts or reads something that a restack does not redo: stock's restack sends EVT_WINDOW_TO_FG (0x12d) to the page and EVT_WINDOW_TO_BG (0x12c) to the window it leaves, and
 * only a new open runs init. Wi-Fi (init 0x4b1048 calls wifi_scan on every open, its 0x12d handler 0x4b0a34 only rebuilds the list), Bluetooth (its 0x12c handler 0x4a2a20 calls btStopSearch, its 0x12d handler 0x4a3a28 does not restart discovery, init 0x4a411c does) are opened afresh. */
int m1_open_stock(const char *path, const char *window) {
    if (window && m1_restack_window(window)) return RET_OK;
    return navigator_to(path);
}

/* The navbar's small title of a page with a large heading: shown once the heading has scrolled away, i.e. the scroll offset has reached SG_COLLAPSE, or, on a page whose
 * heading is a header's name (a playlist, a podcast show), `head` (the offset the name has gone at). The page ORs in its own conditions (select mode, no scroll events ...). */
int m1_title_gone(int off, int head) { return off >= (head ? head : SG_COLLAPSE); }

char *m1_read_file(const char *path, unsigned cap, unsigned *n) {
    char *buf;
    int fd = open(path, O_RDONLY, 0), got = 0, r;
    if (fd < 0) return (char *)0;
    buf = calloc(cap + 1, 1);
    while (buf && (unsigned)got < cap && (r = read(fd, buf + got, cap - (unsigned)got)) > 0) got += r;
    close(fd);
    if (!buf || got <= 0) {
        free(buf);
        return (char *)0;
    }
    *n = (unsigned)got;
    return buf;
}

unsigned m1_sel_all_can(unsigned char *sel, unsigned count, unsigned nsel, unsigned nmark, int (*can)(void *ctx, int i),
                        void *ctx) {
    unsigned i, n = 0;
    memset(sel, 0, (count + 7) / 8);
    if (nsel >= nmark) return 0;
    for (i = 0; i < count; ++i)
        if (!can || can(ctx, (int)i)) sel[i >> 3] |= (unsigned char)(1 << (i & 7)), ++n;
    return n;
}

void m1_timer_stop(unsigned *t) {
    if (*t) timer_remove(*t);
    *t = 0;
}

void m1_show(void *w, int on) {
    if (!w) return;
    widget_set_visible(w, on, 0);
    widget_set_sensitive(w, on);
}

/* Show or hide the small title w when `on` differs from *cur. */
void m1_title_set(void *w, int *cur, int on) {
    if (on == *cur) return;
    *cur = on;
    if (w) widget_set_visible(w, on, 0);
}

/* A translated "%d songs" with the number put where the translation has its %d. The table's text is never a printf format. */
void m1_fmt(char *out, unsigned size, const char *f, int n) {
    char digits[12];
    unsigned o = 0, d = 0, i;
    for (i = (unsigned)(n < 0 ? 0 : n); d == 0 || i; i /= 10) digits[d++] = (char)('0' + i % 10);
    while (*f && o + 1 < size) {
        if (f[0] == '%' && f[1] == 'd') {
            while (d && o + 1 < size) out[o++] = digits[--d];
            f += 2;
        } else
            out[o++] = *f++;
    }
    out[o] = 0;
}

void *m1_bind(void *win, const char *name, int (*fn)(void *, void *), const void *ctx) {
    void *w = widget_lookup(win, name, 1);
    if (w && fn) widget_on(w, EVT_CLICK, fn, (void *)ctx);
    return w;
}

/* The cover tint (Now Playing's, patch/nowplaying.c, and the album page's, patch/albumpage.c). Value: NP_V_MIN + v *
 * (NP_V_MAX - NP_V_MIN) / 255 for the brightest channel v; every channel keeps NP_SAT_NUM / NP_SAT_DEN of its distance
 * from v (a grey stays grey). A black cover is the neutral tone. With NP_V_MAX 192 white text keeps 4.5:1 under the
 * gradients of both pages (test/pod/nowplaying.py, test/pod/albumpage.py). */
__attribute__((noinline)) unsigned m1_tone(unsigned r, unsigned g, unsigned b) {
    unsigned v = r > g ? r : g, c[3], i, vt;
    if (b > v) v = b;
    if (!v) return NP_NEUTRAL;
    c[0] = r, c[1] = g, c[2] = b;
    vt = NP_V_MIN + v * (NP_V_MAX - NP_V_MIN) / 255;
    for (i = 0; i < 3; ++i) c[i] = vt - vt * NP_SAT_NUM * (v - c[i]) / (NP_SAT_DEN * v);
    return 0xff000000u | c[0] | c[1] << 8 | c[2] << 16;
}

/* The status bar (a window of the window manager, vtable type "system_bar") in a page's top-edge colour. One owner at a time:
 * the window that last tinted it. Only the owner can put the stock black back, so a page that is replaced or covered after the
 * next page has taken the bar over (Play, Back) never undoes the new owner's colour. */
#define POD_LUM(r, g, b) (2126u * (r) * (r) + 7152u * (g) * (g) + 722u * (b) * (b))
static void *bar_owner __attribute__((section(".scratch")));

__attribute__((noinline)) unsigned m1_bar_color(unsigned color) {
    unsigned r = color & 255, g = color >> 8 & 255, b = color >> 16 & 255;
    while (POD_LUM(r, g, b) > NP_BAR_LUM_MAX) r = r * 15 >> 4, g = g * 15 >> 4, b = b * 15 >> 4;
    return pal_not_role(0xff000000u | r | g << 8 | b << 16);
}

static void *bar_find(void) {
    void *wm = window_manager(), *w;
    unsigned i, n;
    if (!wm) return (void *)0;
    for (n = widget_count_children(wm), i = 0; i < n; ++i) {
        w = widget_get_child(wm, i);
        if (m1_is_type(w, "system_bar")) return w; /* the navbar is "system_bar_bottom" */
    }
    return (void *)0;
}

static int bar_set(unsigned color) {
    void *bar = bar_find();
    unsigned v[4]; /* value_t: type at 0, the uint32 at 8 */
    if (!bar) return 0;
    memset(v, 0, sizeof v);
    value_set_uint32(v, color);
    if (widget_set_style(bar, "normal:bg_color", v) != RET_OK) return 0;
    widget_invalidate_force(bar, (void *)0);
    return 1;
}

__attribute__((noinline)) int m1_bar_tint(void *win, unsigned color) {
    if (!win || !bar_set(m1_bar_color(color))) return 0; /* a failed call keeps what the bar has (and owes) */
    bar_owner = win;
    return 1;
}

__attribute__((noinline)) void m1_bar_black(void *win) {
    if (!win || bar_owner != win) return;
    bar_owner = (void *)0;
    bar_set(NP_BAR_STOCK);
}

__attribute__((noinline)) int m1_is_top(void *win) {
    void *wm = window_manager();
    return win && wm && window_manager_get_top_main_window(wm) == win;
}

/* The status bar under a page's dim scrim. A sheet's or dialog's scrim is a widget of the page's window, which starts below the bar (a window of its own), so the bar stayed
 * lit while the page went dark. The bar's own EVT_AFTER_PAINT (over its children, so the clock and the icons too) fills it with the scrim's colour once for every shown scrim of
 * the top main window, so a confirm over a sheet darkens the bar twice as it does the page. Window and scrim pointers are only compared, never read. Each window with a scrim
 * gets one EVT_DESTROY listener, and the window is in `wins` exactly while that listener stands: its destroy takes it and its scrims out, so a later window at the same address
 * is never taken for it. `seen` holds the layer counts the bar's paints drew (bit n: n layers), like patch/palette.c pal_bar_follow: a page change that invalidates nothing of the
 * bar is caught by the bar's next tick (m1_bar_scrim_tick). */
#define BS_SCRIMS 4 /* shown scrims tracked at once (the oldest goes when a fifth shows) */
#define BS_WINS 6 /* windows with a destroy listener (a scrim of a seventh window does not dim the bar) */
static struct {
    void *bar; /* the bar listened to */
    void *win[BS_SCRIMS], *scrim[BS_SCRIMS]; /* the shown scrims and their windows, oldest first; the rest 0 */
    void *wins[BS_WINS]; /* the windows listened to (their destroy not seen yet) */
    unsigned seen;
} bs __attribute__((section(".scratch")));

/* The layers over the bar now: the shown scrims of the top main window. */
static int bar_scrim_layers(void) {
    void *wm = window_manager(), *top = wm ? window_manager_get_top_main_window(wm) : (void *)0;
    int i, n = 0;
    if (top)
        for (i = 0; i < BS_SCRIMS; ++i) n += bs.win[i] == top;
    return n;
}

static int bar_scrim_paint(void *ctx, void *e) {
    void *canvas = e ? *(void **)((char *)e + EVENT_PAINT_CANVAS) : (void *)0;
    int n = bar_scrim_layers();
    (void)ctx;
    bs.seen |= 1u << n;
    if (!canvas || !bs.bar) return RET_OK;
    while (n-- > 0) {
        ui_fill_color(canvas, M1_SCRIM_COLOR); /* through the palette as the scrim's style colour is */
        canvas_fill_rect(canvas, 0, 0, *(int *)((char *)bs.bar + W_W), *(int *)((char *)bs.bar + W_H));
    }
    return RET_OK;
}

/* Listen to the bar's paints (once per bar) and repaint it whole. */
static void bar_scrim_repaint(void) {
    void *bar = bar_find();
    if (!bar) return;
    if (bar != bs.bar) {
        if (!widget_on(bar, EVT_AFTER_PAINT, bar_scrim_paint, (void *)0)) return;
        bs.bar = bar;
    }
    bs.seen = 0;
    widget_invalidate_force(bar, (void *)0);
}

/* Remove scrim entry i, the later ones moved up. */
static void bar_scrim_drop(int i) {
    for (; i < BS_SCRIMS - 1; ++i) bs.win[i] = bs.win[i + 1], bs.scrim[i] = bs.scrim[i + 1];
    bs.win[i] = bs.scrim[i] = (void *)0;
}

/* A listened window's destroy (ctx: the window): it and its scrims are forgotten before its address can be reused. */
static int bar_scrim_on_destroy(void *ctx, void *e) {
    int i, hit = 0;
    (void)e;
    for (i = 0; i < BS_WINS; ++i)
        if (bs.wins[i] == ctx) bs.wins[i] = (void *)0;
    for (i = BS_SCRIMS - 1; i >= 0; --i)
        if (bs.win[i] == ctx) bar_scrim_drop(i), hit = 1;
    if (hit) bar_scrim_repaint();
    return RET_OK;
}

/* win listened to (its destroy listener added once); 0 when there is no room or the listener fails. */
static int bar_scrim_listen(void *win) {
    int i, free_ = -1;
    for (i = 0; i < BS_WINS; ++i) {
        if (bs.wins[i] == win) return 1;
        if (!bs.wins[i] && free_ < 0) free_ = i;
    }
    if (free_ < 0 || !widget_on(win, EVT_DESTROY, bar_scrim_on_destroy, win)) return 0;
    bs.wins[free_] = win;
    return 1;
}

__attribute__((noinline)) void m1_bar_scrim(void *win, void *scrim, int on) {
    int i;
    if (!scrim) return;
    for (i = 0; i < BS_SCRIMS && bs.scrim[i] != scrim; ++i) {
    }
    if (on) {
        if (!win || (i < BS_SCRIMS && bs.win[i] == win) || !bar_scrim_listen(win))
            return; /* (already shown: no change) */
        if (i < BS_SCRIMS) bar_scrim_drop(i);
        for (i = 0; i < BS_SCRIMS && bs.scrim[i]; ++i) {
        }
        if (i == BS_SCRIMS) bar_scrim_drop(0), i = BS_SCRIMS - 1;
        bs.win[i] = win, bs.scrim[i] = scrim;
    } else {
        if (i == BS_SCRIMS) return; /* not shown: the bar's answer is unchanged */
        bar_scrim_drop(i);
    }
    bar_scrim_repaint();
}

__attribute__((noinline)) void m1_scrim(void *scrim, int on) {
    if (!scrim) return;
    m1_show(scrim, on);
    m1_bar_scrim(on ? widget_get_window(scrim) : (void *)0, scrim, on);
}

void m1_bar_scrim_tick(void *bar) {
    if (!bar || bar != bs.bar) return; /* no scrim has been shown on this bar: nothing listens */
    if (bs.seen & ~(1u << bar_scrim_layers())) {
        bs.seen = 0;
        widget_invalidate_force(bar, (void *)0);
    }
}

/* The tone cache: album key (cc_album_key) -> m1_tone word, RAM only, fixed size, least recently used out. Both pages look
 * an album up before they decode a cover; a miss is decoded once and inserted. A key is never 0 (0 marks a free entry). */
static struct {
    unsigned key, tone, used;
} tone_tab[TONE_CACHE_N] __attribute__((section(".scratch")));
static unsigned tone_clock __attribute__((section(".scratch")));

__attribute__((noinline)) int m1_tone_get(unsigned key, unsigned *tone) {
    unsigned i;
    if (!key) return 0;
    for (i = 0; i < TONE_CACHE_N; ++i)
        if (tone_tab[i].key == key) {
            tone_tab[i].used = ++tone_clock;
            *tone = tone_tab[i].tone;
            return 1;
        }
    return 0;
}

__attribute__((noinline)) void m1_tone_put(unsigned key, unsigned tone) {
    unsigned i, at = 0;
    if (!key) return;
    for (i = 0; i < TONE_CACHE_N; ++i) {
        if (tone_tab[i].key == key) {
            at = i;
            break;
        } /* the same album again: replaced in place */
        if (!tone_tab[i].key) {
            at = i;
            break;
        } /* the first free entry */
        if (tone_tab[i].used < tone_tab[at].used) at = i; /* else the least recently used */
    }
    tone_tab[at].key = key, tone_tab[at].tone = tone, tone_tab[at].used = ++tone_clock;
}

__attribute__((noinline)) unsigned m1_alpha(unsigned y, unsigned a_top, unsigned a_bot, unsigned rows) {
    if (y >= rows - 1) return a_bot;
    return a_top + ((a_bot - a_top) * y + (rows - 1) / 2) / (rows - 1);
}

__attribute__((noinline)) unsigned m1_shade(unsigned color, unsigned y, unsigned a_top, unsigned a_bot, unsigned rows) {
    unsigned keep = 255 - m1_alpha(y, a_top, a_bot, rows);
    return pal_not_role((color & 255) * keep / 255 | (color >> 8 & 255) * keep / 255 << 8 |
                        (color >> 16 & 255) * keep / 255 << 16);
}

/* The coverage of the area outside a quarter circle of radius r in the corner square of r pixels (the circle's centre at
 * the square's inner corner), 0..255: each pixel is sampled 8 x 8 times. */
__attribute__((noinline)) void m1_corner_fill(unsigned char *tab, unsigned r) {
    unsigned x, y, i, j, n, c = 2 * 8 * r;
    for (y = 0; y < r; ++y)
        for (x = 0; x < r; ++x) {
            for (n = 0, i = 0; i < 8; ++i)
                for (j = 0; j < 8; ++j) {
                    int dx = (int)(2 * (x * 8 + i) + 1) - (int)c, dy = (int)(2 * (y * 8 + j) + 1) - (int)c;
                    n += (unsigned)(dx * dx + dy * dy) > c * c;
                }
            tab[y * r + x] = (unsigned char)((n * 255 + 32) / 64);
        }
}

__attribute__((noinline)) void m1_corners(void *canvas, const unsigned char *tab, unsigned r, unsigned side,
                                          unsigned color, int row0, unsigned a_top, unsigned a_bot, unsigned rows) {
    unsigned k, x, y;
    for (k = 0; k < 4; ++k)
        for (y = 0; y < r; ++y) {
            unsigned ly = k & 2 ? side - 1 - y : y;
            int row = row0 + (int)ly;
            unsigned shade = m1_shade(color, row < 0 ? 0 : (unsigned)row, a_top, a_bot, rows);
            for (x = 0; x < r; ++x) {
                unsigned a = tab[y * r + x];
                if (!a) continue;
                ui_fill_color(canvas, shade | a << 24);
                canvas_fill_rect(canvas, k & 1 ? side - 1 - x : x, ly, 1, 1);
            }
        }
}

int m1_text_w(void *w, const unsigned *t) { return (int)(widget_measure_text(w, t) + 0.999f); }

int m1_text_wn(void *w, int dots, const char *s, unsigned n) {
    char b[M1_FIT_TAIL + 4];
    unsigned wide[M1_FIT_TAIL + 4], m = 0;
    if (dots) b[0] = b[1] = b[2] = '.', m = 3;
    if (n > M1_FIT_TAIL) n = M1_FIT_TAIL;
    memcpy(b + m, s, n);
    m += n;
    b[m] = 0;
    if (!m) return 0;
    tk_utf8_to_utf16_ex(b, m, wide, M1_FIT_TAIL + 3);
    return m1_text_w(w, wide);
}

unsigned m1_utf8_mid(const char *v, unsigned lo, unsigned hi) {
    unsigned m = (lo + hi) / 2;
    while (m < hi && m1_utf8_cont(v, m)) ++m;
    if (m >= hi || m <= lo) {
        m = lo + 1;
        while (m < hi && m1_utf8_cont(v, m)) ++m;
    }
    return m;
}

void m1_fit(void *w, const char *v, int room) {
    char l[M1_FIT_TAIL + 8];
    unsigned len = 0, lo = 0, hi, m;
    while (v[len]) ++len;
    if (len <= M1_FIT_TAIL && m1_text_wn(w, 0, v, len) <= room) { /* whole only when all of it was measured */
        widget_set_text_utf8(w, v);
        return;
    }
    hi = len > M1_FIT_TAIL ? M1_FIT_TAIL : len; /* the longest start that fits before the dots */
    while (hi && m1_utf8_cont(v, hi)) --hi;
    if (len > M1_FIT_TAIL && m1_text_wn(w, 1, v, hi) <= room)
        lo = hi; /* a longer text whose measured start fits: that start and the dots */
    while ((m = m1_utf8_mid(v, lo, hi)) < hi) {
        if (m1_text_wn(w, 1, v, m) <= room)
            lo = m;
        else
            hi = m;
    }
    while (lo && v[lo - 1] == ' ') --lo;
    memcpy(l, v, lo);
    l[lo] = l[lo + 1] = l[lo + 2] = '.';
    l[lo + 3] = 0;
    widget_set_text_utf8(w, l);
}

int m1_wrap2(void *w1, void *w2, const char *v, int room) {
    char l[M1_FIT_TAIL + 8];
    unsigned len = 0, lo, hi, m, n1, k, e;
    const char *rest;
    while (v[len]) ++len;
    widget_set_text_utf8(w2, "");
    if (len <= M1_FIT_TAIL && m1_text_wn(w1, 0, v, len) <= room) { /* one line only when all of it was measured */
        widget_set_text_utf8(w1, v);
        return 0;
    }
    lo = 0, hi = len > M1_FIT_TAIL ? M1_FIT_TAIL : len; /* the longest prefix that fits line 1 */
    while (hi < len && m1_utf8_cont(v, hi)) --hi;
    while ((m = m1_utf8_mid(v, lo, hi)) < hi) {
        if (m1_text_wn(w1, 0, v, m) <= room)
            lo = m;
        else
            hi = m;
    }
    n1 = lo;
    if (!n1) { /* a first character wider than the line: it stays alone */
        n1 = 1;
        while (m1_utf8_cont(v, n1)) ++n1;
    }
    for (k = n1; k > 0 && v[k] != ' '; --k) {
    }
    for (e = k; e > 0 && v[e - 1] == ' '; --e) {
    }
    if (!e) k = e = n1; /* no usable space: the character break */
    for (rest = v + k; *rest == ' '; ++rest) {
    }
    memcpy(l, v, e);
    l[e] = 0;
    widget_set_text_utf8(w1, l);
    m1_fit(w2, rest, room);
    return 1;
}

void m1_tap_at(m1_tap_t *t, void *e) { t->x = *(int *)((char *)e + PE_X), t->y = *(int *)((char *)e + PE_Y); }

int m1_tap_near(const m1_tap_t *t, void *e) {
    return m1_abs(*(int *)((char *)e + PE_X) - t->x) < SC_DRAG_PX &&
           m1_abs(*(int *)((char *)e + PE_Y) - t->y) < SC_DRAG_PX;
}

int m1_pill_pair(int x0, int w0, int glyph, int gap, int tw, int *tx, int *twide) {
    int gx = x0 + (w0 - (glyph + gap + tw)) / 2;
    *tx = gx + glyph + gap, *twide = tw + AB_TEXT_SLACK;
    return gx;
}

void m1_pill_place(m1_pill_t *p, int y) {
    const unsigned *text = widget_get_text(p->ptext);
    int tw = text && *text ? m1_text_w(p->ptext, text) : 0, x;
    if (tw <= 0 || AH_PILL_GLYPH + AH_PILL_GAP + tw > AH_PLAY_W) tw = AB_PLAY_TEXT_W;
    x = m1_pill_pair(AH_PLAY_X, AH_PLAY_W, AH_PILL_GLYPH, AH_PILL_GAP, tw, &p->tx, &p->tw);
    widget_move(p->glyph, x, y + (AH_BTN_H - AH_PILL_GLYPH) / 2);
}

void m1_sheet_rows(void *scrim, void *card, int w, void *const *rows, void *const *hrs, int n) {
    static const char *const glass[] = {"",          "pc_sheet1", "pc_sheet2", "pc_sheet3",
                                        "pc_sheet4", "pc_sheet5", "pc_sheet6", "pc_sheet7"};
    int i, h = n * PM_ROW_H;
    for (i = 0; i < n; ++i) {
        widget_move(rows[i], 0, i * PM_ROW_H);
        m1_show(rows[i], 1);
        widget_set_visible(hrs[i], i > 0, 0);
    }
    widget_move(card, 0, AH_WIN_H - h);
    widget_resize(card, w, h);
    widget_set_prop_str(card, "style:normal:bg_image", glass[n]);
    m1_scrim(scrim, 1);
    m1_show(card, 1);
}

void m1_sheet_value(void *label, void *value, const char *text) {
    const unsigned *w;
    int lw = 0, vw = 0, room;
    if (!value) return;
    w = widget_get_text(label);
    if (w && *w) lw = m1_text_w(label, w);
    room = PS_SHEET_VALUE_R - PS_SHEET_TEXT_X - lw - PS_SHEET_GAP;
    widget_set_text_utf8(value, text);
    w = widget_get_text(value);
    if (w && *w) vw = m1_text_w(value, w);
    if (vw > room) vw = room > 0 ? room : 0;
    widget_move(value, PS_SHEET_VALUE_R - vw, 0);
    widget_resize(value, vw, PM_ROW_H);
    widget_resize(label, PS_SHEET_VALUE_R - PS_SHEET_TEXT_X - vw - (vw ? PS_SHEET_GAP : 0), PM_ROW_H);
}

void m1_pill_paint(const m1_pill_t *p, void *canvas, int y) {
    const unsigned *text = widget_get_text(p->ptext);
    unsigned n = 0;
    int rect[4];
    while (text && text[n]) ++n;
    rect[0] = p->tx, rect[1] = y + (AH_BTN_H - AB_TEXT_H) / 2, rect[2] = p->tw, rect[3] = AB_TEXT_H;
    widget_prepare_text_style(p->ptext, canvas);
    if (n) canvas_draw_text_in_rect(canvas, text, n, rect);
}

static const char *const pill_key[5] = {"normal:", "pressed:", "over:", "focused:", "disable:"};

/* A pill pw x ph whose glyph (glyph px) and label (tw px) are centred as a pair gap apart: AWTK puts the glyph in a square as high as the button at margin_left and the
 * text at the square's end plus the spacer, so these five styles are set in every state. */
void m1_pill_styles(void *btn, int pw, int ph, int glyph, int gap, int tw) {
    static const char *const prop[5] = {"margin_left", "icon_at", "margin_right", "spacer", "text_align_h"};
    int margin = (pw - (glyph + gap + tw)) / 2 - (ph - glyph) / 2, i, j;
    unsigned v[4], val[5]; /* value_t: type at 0, the uint32 at 8 */
    char name[32];
    if (margin < 0) margin = 0;
    val[0] = (unsigned)margin, val[1] = 1, val[2] = 0, val[3] = (unsigned)(gap - (ph - glyph) / 2),
    val[4] = 2; /* icon_at left, text_align_h left */
    for (j = 0; j < 5; ++j) {
        memset(v, 0, sizeof v);
        value_set_uint32(v, val[j]);
        for (i = 0; i < 5; ++i) {
            unsigned k = 0, m = 0;
            while (pill_key[i][k]) name[k] = pill_key[i][k], ++k;
            while (prop[j][m]) name[k++] = prop[j][m++];
            name[k] = 0;
            widget_set_style(btn, name, v);
        }
    }
}

/* The pills: the glyph and the label centred as a pair SG_PILL_GAP apart (the flat pills of the Songs, Folders and artist pages, the select bars'). Moved from patch/songs.c. */
void m1_centre_pill(void *btn, int pw) {
    const unsigned *text = widget_get_text(btn);
    int tw = text && *text ? m1_text_w(btn, text) : 0, i;
    unsigned v[4]; /* value_t: type at 0, the uint32 at 8 */
    char name[32];
    if (!text || !*text)
        return; /* (a text that cannot be measured is taken as 0 px wide: the glyph is still put at the left, not above the text as the automatic icon position would) */
    if (tw > pw - (SG_PILL_H - SG_PILL_GLYPH) / 2 - SG_PILL_GLYPH -
                 SG_PILL_GAP) { /* too wide beside the glyph (ru "Перемешать"): the label steps down to
                                                                                      * SG_PILL_PX_SMALL, as an iOS button shrinks its title, and is measured again */
        for (i = 0; i < 5; ++i) {
            unsigned k = 0, m = 0;
            static const char fs[] = "font_size";
            while (pill_key[i][k]) name[k] = pill_key[i][k], ++k;
            while (fs[m]) name[k++] = fs[m++];
            name[k] = 0;
            memset(v, 0, sizeof v);
            value_set_uint32(v, SG_PILL_PX_SMALL);
            widget_set_style(btn, name, v);
        }
        tw = m1_text_w(btn, text);
    }
    m1_pill_styles(btn, pw, SG_PILL_H, SG_PILL_GLYPH, SG_PILL_GAP, tw);
}

/* A select mark: the stock image (26 px) as a bitmap, cut to its circle. cc_decode flattens the image over black, so the square
 * around the ring would be black on a cover (the Playlists grid): every pixel's alpha becomes its coverage by the ink's circle
 * (the stock unselect / selected images: ink 2 .. 23, a circle of radius SG_MARK_INK centred in the square; 8 x 8 samples a pixel),
 * so only the ring and what it holds are drawn. Over the Songs page's black it looks as before.
 * The selected mark ("selected": a white disc, the tick cut out, so black once flattened) takes the accent under one, like Select All (mulselected): white goes to the accent, the black tick
 * stays black (dark ink on an accent fill, as the Play pill's); Neutral keeps it white. The unselected ring stays white. */
#define SG_MARK_INK 11
void *m1_make_mark(void *win, const char *name) {
    unsigned *px, x, y, i, j, n, c = 8 * SG_MARK, rr = 2 * 8 * SG_MARK_INK;
    unsigned acc = name[0] == 's' && pal_accent() ? pal_fill() : 0; /* "selected" (not "unselect") under an accent */
    void *b = bitmap_create_ex(SG_MARK, SG_MARK, SG_MARK * 4, BITMAP_RGBA8888);
    int ok;
    if (!b) return b;
    px = (unsigned *)bitmap_lock_buffer_for_write(b);
    if (!px || bitmap_get_line_length(b) != SG_MARK * 4) {
        if (px) bitmap_unlock_buffer(b);
        bitmap_destroy(b);
        return (void *)0;
    }
    ok = cc_decode(win, name, 1, SG_MARK, 1, px);
    for (y = 0; ok && y < SG_MARK; ++y)
        for (x = 0; x < SG_MARK; ++x) {
            for (n = 0, i = 0; i < 8; ++i)
                for (j = 0; j < 8;
                     ++j) { /* (coordinates doubled: the sample centres are odd, the circle's centre is c) */
                    int dx = (int)(2 * (x * 8 + i) + 1) - (int)c, dy = (int)(2 * (y * 8 + j) + 1) - (int)c;
                    n += (unsigned)(dx * dx + dy * dy) <= rr * rr;
                }
            if (acc) { /* the pixel's lightness (its red: white to black) scales the accent, per channel, rounded */
                unsigned v = px[y * SG_MARK + x] & 255, s;
                px[y * SG_MARK + x] = 0;
                for (s = 0; s < 24; s += 8) px[y * SG_MARK + x] |= ((acc >> s & 255) * v + 127) / 255 << s;
            }
            px[y * SG_MARK + x] = (px[y * SG_MARK + x] & 0xffffff) | ((n * 255 + 32) / 64) << 24;
        }
    bitmap_unlock_buffer(b);
    if (!ok) {
        bitmap_destroy(b);
        return (void *)0;
    }
    return b;
}

int m1_make_marks(void *win, void *mark[2]) {
    mark[0] = m1_make_mark(win, "unselect");
    mark[1] = m1_make_mark(win, "selected");
    if (mark[0] && mark[1]) return 1;
    if (mark[0]) bitmap_destroy(mark[0]);
    if (mark[1]) bitmap_destroy(mark[1]);
    mark[0] = mark[1] = (void *)0;
    return 0;
}

/* The chevron: a stroke of two segments (the stock right_arrow is 13 x 22 and our image loader only makes squares), antialiased by 4 x 4 samples per pixel, in the
 * alpha of a grey bitmap (the rail's disc is made the same way). Coordinates are eighths of a pixel. */
static int pod_seg2(int px, int py, int ax, int ay, int bx,
                    int by) { /* the squared distance of (px, py) to the segment a-b */
    int dx = bx - ax, dy = by - ay, n = (px - ax) * dx + (py - ay) * dy, d = dx * dx + dy * dy, cx, cy, cr;
    if (n <= 0)
        cx = px - ax, cy = py - ay;
    else if (n >= d)
        cx = px - bx, cy = py - by;
    else {
        cr = (px - ax) * dy - (py - ay) * dx; /* the cross product: distance = |cr| / sqrt(d) */
        return cr * cr / d;
    }
    return cx * cx + cy * cy;
}

void *m1_make_cross(void) {
    unsigned *px;
    int x, y, i, j, n, d, e;
    void *b = bitmap_create_ex(POD_CROSS, POD_CROSS, POD_CROSS * 4, BITMAP_RGBA8888);
    if (!b) return (void *)0;
    px = (unsigned *)bitmap_lock_buffer_for_write(b);
    if (!px || bitmap_get_line_length(b) != POD_CROSS * 4) {
        if (px) bitmap_unlock_buffer(b);
        bitmap_destroy(b);
        return (void *)0;
    }
    e = POD_CROSS * 8 - 16; /* the strokes run from 2 px in from each corner */
    for (y = 0; y < POD_CROSS; ++y)
        for (x = 0; x < POD_CROSS; ++x) {
            for (n = 0, i = 0; i < 4; ++i)
                for (j = 0; j < 4; ++j) {
                    int sx = x * 8 + 2 * j + 1, sy = y * 8 + 2 * i + 1;
                    d = pod_seg2(sx, sy, 16, 16, e, e);
                    if (pod_seg2(sx, sy, e, 16, 16, e) < d) d = pod_seg2(sx, sy, e, 16, 16, e);
                    if (d <= 49) ++n; /* a stroke 1.75 px wide */
                }
            px[y * POD_CROSS + x] = (unsigned)(n * 255 / 16) << 24 | POD_CHEV_RGB;
        }
    bitmap_unlock_buffer(b);
    return b;
}

void *m1_make_chevron(void) {
    unsigned *px;
    int x, y, i, j, n, d;
    void *b = bitmap_create_ex(POD_CHEV_W, POD_CHEV_H, POD_CHEV_W * 4, BITMAP_RGBA8888);
    if (!b) return (void *)0;
    px = (unsigned *)bitmap_lock_buffer_for_write(b);
    if (!px || bitmap_get_line_length(b) != POD_CHEV_W * 4) {
        if (px) bitmap_unlock_buffer(b);
        bitmap_destroy(b);
        return (void *)0;
    }
    for (y = 0; y < POD_CHEV_H; ++y)
        for (x = 0; x < POD_CHEV_W; ++x) {
            for (n = 0, i = 0; i < 4; ++i)
                for (j = 0; j < 4; ++j) {
                    int sx = x * 8 + 2 * j + 1, sy = y * 8 + 2 * i + 1;
                    d = pod_seg2(sx, sy, 14, 14, 68, 64);
                    if (pod_seg2(sx, sy, 68, 64, 14, 114) < d) d = pod_seg2(sx, sy, 68, 64, 14, 114);
                    if (d <= 64) ++n; /* half the stroke's width: 1 px */
                }
            px[y * POD_CHEV_W + x] = (unsigned)(n * 255 / 16) << 24 | POD_CHEV_RGB;
        }
    bitmap_unlock_buffer(b);
    return b;
}

/* One row of a shape: x .. x + w - 1 of row y of the canvas, in colour c, only when the row is inside the view (rows 0 .. view_h - 1). */
static void pod_fill_row(void *canvas, int view_h, int x, int y, int w, unsigned c) {
    if (w <= 0 || y < 0 || y >= view_h) return;
    ui_fill_color(canvas, c);
    canvas_fill_rect(canvas, x, y, w, 1);
}

void m1_capsule(void *canvas, int view_h, int x, int y, int w, int h, int r, unsigned c) {
    int i, top, bottom;
    unsigned a;
    if (r > h / 2) r = h / 2;
    if (r > w / 2) r = w / 2;
    if (r < 0) r = 0;
    /* the corner rows, from the outside in: the circle's chord on the row's middle, its ends smoothed by a pixel of partial cover */
    for (i = 0; i < r; ++i) {
        int dy = 2 * (r - i) - 1, inset, x0, f;
        inset = r * 256 - (int)(m1_isqrt((unsigned)(4 * r * r - dy * dy) << 16) / 2); /* in 1/256 px */
        x0 = inset >> 8, f = inset & 255;
        a = (unsigned)(255 - f);
        top = y + i, bottom = y + h - 1 - i;
        if (f) {
            unsigned edge = (c & 0x00ffffffu) | (((c >> 24) * a / 255) << 24);
            pod_fill_row(canvas, view_h, x + x0, top, 1, edge);
            pod_fill_row(canvas, view_h, x + w - 1 - x0, top, 1, edge);
            pod_fill_row(canvas, view_h, x + x0, bottom, 1, edge);
            pod_fill_row(canvas, view_h, x + w - 1 - x0, bottom, 1, edge);
            ++x0;
        }
        pod_fill_row(canvas, view_h, x + x0, top, w - 2 * x0, c);
        pod_fill_row(canvas, view_h, x + x0, bottom, w - 2 * x0, c);
    }
    top = y + r, bottom = y + h - r;
    if (top < 0) top = 0;
    if (bottom > view_h) bottom = view_h;
    if (bottom > top) {
        ui_fill_color(canvas, c);
        canvas_fill_rect(canvas, x, top, w, bottom - top);
    }
}

void m1_segmented(void *canvas, int view_h, int x, int y, int w, int h, int n, int sel, void *st_on, void *st_off,
                  const unsigned *const *label, const int *len) {
    int seg = (w - 2 * SEG_PAD) / n, k, rect[4];
    if (n < 1) return;
    m1_capsule(canvas, view_h, x, y, w, h, h / 2, SEG_TRACK);
    m1_capsule(canvas, view_h, x + SEG_PAD + sel * seg, y + SEG_PAD, sel == n - 1 ? w - 2 * SEG_PAD - sel * seg : seg,
               h - 2 * SEG_PAD, (h - 2 * SEG_PAD) / 2, SEG_THUMB);
    /* a short hairline between two segments that are both unselected (none next to the thumb) */
    for (k = 1; k < n; ++k)
        if (k - 1 != sel && k != sel && y + h / 4 >= 0 && y + h - h / 4 <= view_h) {
            ui_fill_color(canvas, SEG_SEP);
            canvas_fill_rect(canvas, x + SEG_PAD + k * seg, y + h / 4, 1, h / 2);
        }
    /* the labels, each centred in its segment: the selected one on the thumb in the dark ink */
    for (k = 0; k < n; ++k) {
        void *st = k == sel ? st_on : st_off;
        int tw;
        widget_prepare_text_style(st, canvas);
        tw = m1_text_w(st, label[k]);
        rect[0] = x + SEG_PAD + k * seg + (seg - tw) / 2, rect[1] = y + (h - SEG_LABEL_H) / 2, rect[2] = tw + 2,
        rect[3] = SEG_LABEL_H;
        if (len[k] > 0 && rect[1] >= 0 && rect[1] + SEG_LABEL_H <= view_h)
            canvas_draw_text_in_rect(canvas, label[k], (unsigned)len[k], rect);
    }
}

/* s appended to out (capacity size); 0 when it does not all fit, the part that fit stays. */
int m1_cat(char *out, unsigned size, const char *s) {
    unsigned o = strlen(out), k;
    for (k = 0; s[k]; ++k) {
        if (o + 1 >= size) return 0;
        out[o++] = s[k];
    }
    out[o] = 0;
    return 1;
}

unsigned m1_isqrt(unsigned v) {
    unsigned r = 0, bit = 1u << 30;
    while (bit > v) bit >>= 2;
    while (bit) {
        if (v >= r + bit)
            v -= r + bit, r = (r >> 1) + bit;
        else
            r >>= 1;
        bit >>= 2;
    }
    return r;
}

void *m1_asset_rgba(void *win, const char *name, unsigned w, unsigned h, int pm) {
    static const unsigned char at[4][4] = BITMAP_RGBA_AT;
    unsigned bitmap[32], format, x, y, ok = 0, *out, stride;
    const unsigned char *data;
    void *bmp = (void *)0;
    memset(bitmap, 0, sizeof bitmap);
    if (widget_load_image(win, name, bitmap)) return bmp;
    format = (unsigned)(*(unsigned short *)((char *)bitmap + BITMAP_FORMAT)) - 1u;
    data =
        format < 4 && bitmap[0] == w && bitmap[1] == h ? bitmap_lock_buffer_for_read(bitmap) : (const unsigned char *)0;
    if (data) {
        stride = bitmap_get_line_length(bitmap);
        bmp = bitmap_create_ex(w, h, w * 4, BITMAP_RGBA8888);
        out = bmp ? (unsigned *)bitmap_lock_buffer_for_write(bmp) : (unsigned *)0;
        if (out) {
            for (y = 0; y < h; ++y) {
                const unsigned char *s = data + y * stride;
                for (x = 0; x < w; ++x, s += 4) {
                    unsigned r = s[at[format][0]], g = s[at[format][1]], b = s[at[format][2]], a = s[at[format][3]];
                    if (pm) r = (r * a + 127) / 255, g = (g * a + 127) / 255, b = (b * a + 127) / 255;
                    out[y * w + x] = r | g << 8 | b << 16 | a << 24;
                }
            }
            ok = 1;
            bitmap_unlock_buffer(bmp);
        }
        bitmap_unlock_buffer(bitmap);
    }
    widget_unload_image(win, bitmap);
    if (!ok && bmp) bitmap_destroy(bmp), bmp = (void *)0;
    return bmp;
}
