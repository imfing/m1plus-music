/* M1+ Music Podcasts, the feed reader: an RSS push parser and the writers of the show's .episodes and .show files.
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * See patch/pcfeed.h. The parser is a byte at a time state machine over libcurl's chunks (any split): text, a tag, a comment, CDATA, and a skipped declaration. Only the elements the
 * model needs are collected (the channel's title, picture, author, first category and summary; an item's title, guid, pubDate, itunes:duration, enclosure and description); a description
 * streams through a tag-stripping sink that keeps at most PC_DESC_CUT bytes, and everything else is discarded as it passes, so a 4 MB feed costs the 25 KB parser and nothing more. Atom feeds are not read (a podcast feed is RSS; "Not a feed" otherwise).
 */
#include "offsets.inc"
#include "stock.h"
#include "podcasts.h"
#include "pcfeed.h"
#include "utf8.h"

#define PF_TEXT 512 /* the text of the element being collected (a title is cut to PC_TITLE later) */
#define PF_TAG \
    1024 /* a tag (a long enclosure url with its tracking path fits; a longer tag keeps its first PF_TAG bytes) */
#define PF_EPS_MAX 65536 /* the .episodes text the model reads at most (PM_META_MAX) */

enum { M_TEXT, M_TAG, M_COMMENT, M_CDATA, M_SKIP };
/* W_ISUM..: the description kinds (item: itunes:summary, description, content:encoded = ranks 1..3; channel: itunes:summary, description = ranks 1..2); they stream through the description sink */
enum { W_NONE, W_ITITLE, W_CTITLE, W_GUID, W_PUB, W_DUR, W_IMGURL, W_AUTHOR, W_ISUM, W_IDESC, W_IENC, W_CSUM, W_CDESC };
enum {
    E_NONE,
    E_RSS,
    E_ITEM,
    E_IMAGE,
    E_TITLE,
    E_GUID,
    E_PUB,
    E_DUR,
    E_URL,
    E_ENCL,
    E_ITUNES_IMAGE,
    E_ISUM,
    E_DESC,
    E_ENC,
    E_AUTHOR,
    E_CAT
};
enum {
    DM_TEXT,
    DM_LT,
    DM_TAG,
    DM_COMMENT
}; /* the description sink's modes: text, after a '<', in a tag, in a comment */

struct pf_parser {
    int mode, want, in_item, in_image, saw_feed, img_itunes, nitems, seen, drank, srank;
    unsigned tl, tn, en, dn, dtn, dnl, den;
    char quote, trunc, d1, d2, tover, inent;
    char dm, dq, dcut, dcont, dspace, dnend, dent_on, dc1, dc2, dhead[3], dnlc,
        dnlc0; /* dnlc0: dnlc before the last lead byte (a white space character gives it back) */
    unsigned dlim; /* the sink's budget: PF_NOTE for an item, PC_DESC_CUT for the channel */
    char ent[12];
    char dname[12];
    char dent[12];
    char dbuf[PF_NOTE + 1]; /* the description being collected (the sink's output; '\n' marks a paragraph) */
    char txt[PF_TEXT];
    char tag[PF_TAG];
    char title[PC_TITLE];
    char author[PC_AUTHOR];
    char category[PC_CAT];
    char summary[PC_DESC];
    char image[PC_URL];
    pf_item_t cur;
    pf_item_t items[PF_KEEP];
    pf_sink_t sink; /* pf_set_sink: every item goes there and none is kept */
    void *sink_ctx;
};

/* ---------------------------------------------------------------------------
 * Small helpers
 */
static int pf_lc(int c) { return (unsigned)(c - 'A') < 26u ? c + 32 : c; }

static int pf_is(const char *nm, unsigned len, const char *s) {
    unsigned i;
    for (i = 0; i < len; ++i)
        if (!s[i] || nm[i] != s[i]) return 0;
    return !s[len];
}

/* The UTF-8 bytes of code point cp into dst[*n..cap): 0 when it does not fit whole (or is not a character). */
static int pf_put_cp(char *dst, unsigned *n, unsigned cap, unsigned cp) {
    unsigned len = m1_utf8_len(cp);
    if (!cp || cp > 0x10ffff || (cp >= 0xd800 && cp < 0xe000) || *n + len > cap) return 0;
    *n += m1_utf8_put(dst + *n, cp);
    return 1;
}

/* The character an entity names: e is the text between "&" and ";" (n bytes). 0 when it is not one we know. */
static unsigned pf_ent_cp(const char *e, unsigned n) {
    unsigned v = 0, i;
    if (n >= 2 && e[0] == '#') {
        if (e[1] == 'x' || e[1] == 'X') {
            for (i = 2; i < n; ++i) {
                int c = pf_lc((unsigned char)e[i]), d = (unsigned)(c - '0') < 10u  ? c - '0'
                                                        : (unsigned)(c - 'a') < 6u ? c - 'a' + 10
                                                                                   : -1;
                if (d < 0 || v > 0x10ffffu) return 0;
                v = v * 16 + (unsigned)d;
            }
            return n > 2 ? v : 0;
        }
        for (i = 1; i < n; ++i) {
            if ((unsigned)(e[i] - '0') >= 10u || v > 0x10ffffu) return 0;
            v = v * 10 + (unsigned)(e[i] - '0');
        }
        return v;
    }
    if (pf_is(e, n, "amp")) return '&';
    if (pf_is(e, n, "lt")) return '<';
    if (pf_is(e, n, "gt")) return '>';
    if (pf_is(e, n, "quot")) return '"';
    if (pf_is(e, n, "apos")) return '\'';
    return 0;
}

/* src[0..n) into dst (cap bytes, a NUL at the end): leading and trailing white space dropped, every run of white space and control bytes one space, cut before a split UTF-8 character. */
static void pf_norm(char *dst, unsigned cap, const char *src, unsigned n) {
    unsigned o = 0, i;
    int space = 0, cut = 0;
    for (i = 0; i < n && src[i]; ++i) {
        unsigned char c = (unsigned char)src[i];
        if (c <= 32) {
            space = o != 0;
            continue;
        }
        if (o + (space ? 2 : 1) >= cap) {
            cut = 1;
            break;
        }
        if (space) dst[o++] = ' ', space = 0;
        dst[o++] = (char)c;
    }
    if (cut && i < n &&
        ((unsigned char)src[i] & 0xc0) == 0x80) { /* the cut splits a character: drop its first bytes too */
        while (o && ((unsigned char)dst[o - 1] & 0xc0) == 0x80) --o;
        if (o) --o;
    }
    dst[o] = 0;
}

/* ---------------------------------------------------------------------------
 * Dates and durations
 */
static int pf_civil_days(int y, int m,
                         int d) { /* days since 1970-01-01 of a proleptic Gregorian date (Hinnant's days_from_civil) */
    int era, yoe, doy, doe;
    y -= m <= 2;
    era = (y >= 0 ? y : y - 399) / 400;
    yoe = y - era * 400;
    doy = (153 * (m + (m > 2 ? -3 : 9)) + 2) / 5 + d - 1;
    doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    return era * 146097 + doe - 719468;
}

static void pf_civil(unsigned days, int *y, int *m, int *d) { /* the inverse (civil_from_days) */
    int z = (int)days + 719468, era = z / 146097, doe = z - era * 146097;
    int yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365, doy, mp;
    *y = yoe + era * 400;
    doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    mp = (5 * doy + 2) / 153;
    *d = doy - (153 * mp + 2) / 5 + 1;
    *m = mp + (mp < 10 ? 3 : -9);
    *y += *m <= 2;
}

static int pf_digits(const char **s, int max, int *out) { /* up to max decimal digits: how many were read */
    int n = 0, v = 0;
    while (n < max && (unsigned)(**s - '0') < 10u) v = v * 10 + (**s - '0'), ++*s, ++n;
    *out = v;
    return n;
}

unsigned pf_rfc822(const char *s) {
    static const char mon[] = "janfebmaraprmayjunjulaugsepoctnovdec";
    int day, year, hh, mm = 0, ss = 0, m = -1, i, nd, zone = 0;
    long t;
    while (*s && (unsigned)(*s - '0') >= 10u) ++s; /* the weekday and its comma */
    if (!pf_digits(&s, 2, &day)) return 0;
    while (*s == ' ' || *s == '-') ++s;
    for (i = 0; i < 12; ++i)
        if (pf_lc((unsigned char)s[0]) == mon[3 * i] && pf_lc((unsigned char)s[1]) == mon[3 * i + 1] &&
            pf_lc((unsigned char)s[2]) == mon[3 * i + 2])
            m = i + 1;
    if (m < 0) return 0;
    s += 3;
    while ((unsigned)(pf_lc((unsigned char)*s) - 'a') < 26u) ++s; /* "October" */
    while (*s == ' ' || *s == '-') ++s;
    nd = pf_digits(&s, 4, &year);
    if (nd == 2)
        year += year < 70 ? 2000 : 1900;
    else if (nd != 4)
        return 0;
    while (*s == ' ' || *s == ',') ++s;
    if (!pf_digits(&s, 2, &hh) || *s != ':') return 0;
    ++s;
    if (!pf_digits(&s, 2, &mm)) return 0;
    if (*s == ':') ++s, pf_digits(&s, 2, &ss);
    while (*s == ' ') ++s;
    if (*s == '+' || *s == '-') {
        int sign = *s == '-' ? -1 : 1, zh, zm = 0;
        ++s;
        if (pf_digits(&s, 2, &zh)) {
            if (*s == ':') ++s;
            pf_digits(&s, 2, &zm);
            zone = sign * (zh * 3600 + zm * 60);
        }
    } else {
        static const struct {
            const char *n;
            int h;
        } z[] = {{"EST", -5}, {"EDT", -4}, {"CST", -6}, {"CDT", -5},
                 {"MST", -7}, {"MDT", -6}, {"PST", -8}, {"PDT", -7}};
        for (i = 0; i < 8; ++i)
            if (pf_lc((unsigned char)s[0]) == pf_lc(z[i].n[0]) && pf_lc((unsigned char)s[1]) == pf_lc(z[i].n[1]) &&
                pf_lc((unsigned char)s[2]) == pf_lc(z[i].n[2]))
                zone = z[i].h * 3600;
    }
    if (day < 1 || day > 31 || hh > 23 || mm > 59 || ss > 60 || year < 1970 || year > 2100) return 0;
    t = (long)pf_civil_days(year, m, day) * 86400 + hh * 3600 + mm * 60 + ss - zone;
    return t > 0 ? (unsigned)t : 0;
}

unsigned pf_iso(const char *s) {
    int y = 0, mo = 0, d = 0, hh = 0, mm = 0, ss = 0;
    const char *p = s;
    if (pf_digits(&p, 4, &y) != 4 || *p++ != '-') return 0;
    if (pf_digits(&p, 2, &mo) != 2 || *p++ != '-') return 0;
    if (pf_digits(&p, 2, &d) != 2 || (*p != 'T' && *p != ' ')) return 0;
    ++p;
    if (pf_digits(&p, 2, &hh) != 2 || *p++ != ':') return 0;
    if (pf_digits(&p, 2, &mm) != 2) return 0;
    if (*p == ':') {
        ++p;
        if (pf_digits(&p, 2, &ss) != 2) return 0;
    }
    if (*p == 'Z') ++p;
    if (*p || y < 1970 || mo < 1 || mo > 12 || d < 1 || d > 31 || hh > 23 || mm > 59 || ss > 60) return 0;
    return (unsigned)((long)pf_civil_days(y, mo, d) * 86400 + hh * 3600 + mm * 60 + ss);
}

static int pf_key_eq(const char *a, const char *b) {
    while (*a && *a == *b) ++a, ++b;
    return *a == *b;
}

/* A title for comparison into out (cap bytes): ASCII lower case, a leading "586. " dropped, runs of spaces one, no space at either end. */
static void pf_key_title(const char *s, char *out, unsigned cap) {
    const char *p = s;
    unsigned n = 0;
    while (*p == ' ') ++p;
    if (*p >= '0' && *p <= '9') {
        const char *q = p;
        while (*q >= '0' && *q <= '9') ++q;
        if (*q == '.' && q[1] == ' ') {
            p = q + 1;
            while (*p == ' ') ++p;
        }
    }
    for (; *p && n + 1 < cap; ++p) {
        if (*p == ' ') {
            if (n && out[n - 1] != ' ') out[n++] = ' ';
        } else
            out[n++] = (char)pf_lc((unsigned char)*p);
    }
    if (n && out[n - 1] == ' ') --n;
    out[n] = 0;
}

int pf_match(const pf_parser_t *p, const char *url, unsigned pub, const char *title) {
    int i, n = pf_items(p);
    char a[PC_TITLE], b[PC_TITLE];
    if (url[0])
        for (i = 0; i < n; ++i)
            if (pf_key_eq(pf_item(p, i)->url, url)) return i;
    if (pub)
        for (i = 0; i < n; ++i)
            if (pf_item(p, i)->pub && pf_item(p, i)->pub / 60 == pub / 60) return i;
    pf_key_title(title, a, sizeof a);
    if (a[0])
        for (i = 0; i < n; ++i) {
            pf_key_title(pf_item(p, i)->title, b, sizeof b);
            if (pf_key_eq(a, b)) return i;
        }
    return -1;
}

unsigned pf_duration(const char *s) {
    unsigned parts[3] = {0, 0, 0}, n = 0, v = 0;
    int any = 0;
    for (; *s; ++s) {
        if ((unsigned)(*s - '0') < 10u) {
            if (v > 100000u) return 0;
            v = v * 10 + (unsigned)(*s - '0'), any = 1;
        } else if (*s == ':' && n < 2)
            parts[n++] = v, v = 0, any = 0;
        else if (*s == '.')
            break;
        else if (*s != ' ')
            return 0;
    }
    if (!any && !n) return 0;
    parts[n++] = v;
    return n == 1 ? parts[0] : n == 2 ? parts[0] * 60 + parts[1] : parts[0] * 3600 + parts[1] * 60 + parts[2];
}

/* ---------------------------------------------------------------------------
 * Attributes: the value of name in the tag (entities decoded) into out; 0 when there is none.
 */
static int pf_attr(const char *tag, unsigned n, const char *name, char *out, unsigned cap) {
    unsigned i = 1;
    while (i < n && (unsigned char)tag[i] > 32 && tag[i] != '/' && tag[i] != '>') ++i; /* the element's name */
    while (i < n) {
        unsigned s, e;
        while (i < n && ((unsigned char)tag[i] <= 32 || tag[i] == '/')) ++i;
        s = i;
        while (i < n && tag[i] != '=' && (unsigned char)tag[i] > 32 && tag[i] != '>' && tag[i] != '/') ++i;
        e = i;
        if (i == s && (i >= n || tag[i] != '=')) { /* nothing read (the closing '>'): never stand still */
            ++i;
            continue;
        }
        while (i < n && (unsigned char)tag[i] <= 32) ++i;
        if (i < n && tag[i] == '=') {
            char q;
            ++i;
            while (i < n && (unsigned char)tag[i] <= 32) ++i;
            q = i < n ? tag[i] : 0;
            if (q == '"' || q == '\'') {
                unsigned o = 0, v = ++i;
                int match = pf_is(tag + s, e - s, name);
                while (i < n && tag[i] != q) ++i;
                if (match) {
                    unsigned k = v;
                    while (k < i) {
                        if (tag[k] == '&') {
                            unsigned j = k + 1;
                            while (j < i && j - k < 11 && tag[j] != ';') ++j;
                            if (j < i && tag[j] == ';' && pf_ent_cp(tag + k + 1, j - k - 1) &&
                                pf_put_cp(out, &o, cap - 1, pf_ent_cp(tag + k + 1, j - k - 1))) {
                                k = j + 1;
                                continue;
                            }
                        }
                        if (o + 1 < cap) out[o++] = tag[k];
                        ++k;
                    }
                    out[o] = 0;
                    return 1;
                }
                ++i;
            } else
                while (i < n && (unsigned char)tag[i] > 32 && tag[i] != '>') ++i; /* an unquoted value */
        }
    }
    return 0;
}

/* ---------------------------------------------------------------------------
 * The parser
 */
pf_parser_t *pf_new(void) { return calloc(1, sizeof(pf_parser_t)); }
void pf_free(pf_parser_t *p) {
    int i;
    if (!p) return;
    for (i = 0; i < p->nitems; ++i) free(p->items[i].note);
    free(p->cur.note);
    free(p);
}
const char *pf_note(const pf_parser_t *p, int i) {
    return i >= 0 && i < p->nitems && p->items[i].note ? p->items[i].note : "";
}
void pf_set_sink(pf_parser_t *p, pf_sink_t fn, void *ctx) { p->sink = fn, p->sink_ctx = ctx; }
int pf_is_feed(const pf_parser_t *p) { return p->saw_feed; }
int pf_items(const pf_parser_t *p) { return p->nitems; }
const pf_item_t *pf_item(const pf_parser_t *p, int i) {
    return i >= 0 && i < p->nitems ? &p->items[i] : (const pf_item_t *)0;
}
int pf_seen(const pf_parser_t *p) { return p->seen; }
const char *pf_title(const pf_parser_t *p) { return p->title; }
const char *pf_image(const pf_parser_t *p) { return p->image; }
const char *pf_author(const pf_parser_t *p) { return p->author; }
const char *pf_category(const pf_parser_t *p) { return p->category; }
const char *pf_summary(const pf_parser_t *p) { return p->summary; }

/* ---------------------------------------------------------------------------
 * The description sink: the text of an itunes:summary / description / content:encoded as plain text, a byte at a time in bounded memory (the element of a real feed is up to 100 KB of HTML).
 * The bytes come entity- and CDATA-decoded by the parser, so they hold real tags and double-encoded entities. Tags are skipped (a boundary tag counts as a space; a comment is skipped whole; a '<'
 * that does not start one stays text), the common entities are decoded once more, white space runs (and U+00A0 and the Unicode spaces of pf_dws3) become one space, the zero width characters (U+200B, U+2060, U+FEFF) go, the ends are trimmed, and the text is cut at PC_DESC_CUT bytes before
 * a split UTF-8 character. After the cut the sink ignores everything, so the rest of a long element costs a compare per byte.
 */
/* dspace: 0 nothing pending, 1 a space, 2 a paragraph break ('\n'); a break tag or a blank line sets 2, any other white space 1. The text is at most dlim bytes (PF_NOTE for an item: the notes; the cells'
 * x= is its first PC_DESC_CUT bytes with the breaks as spaces, pf_flat). */
static void pf_dbrk(pf_parser_t *p, int level) {
    if (p->dn && level > p->dspace) p->dspace = (char)level;
}

/* The white space of three UTF-8 bytes: 1 a space (U+2000..200A, 202F, 205F, 3000), 2 a paragraph break (U+2028, 2029), 3 nothing (the zero width U+200B, 2060, FEFF); 0 any other character.
 * A feed's text often starts with one of them (a BOM, a paragraph of one ideographic space), which as text was a blank first line on the episode page. */
static int pf_dws3(unsigned char a, unsigned char b, unsigned char c) {
    if (a == 0xe2 && b == 0x80) return c <= 0x8a ? 1 : c == 0x8b ? 3 : c == 0xa8 || c == 0xa9 ? 2 : c == 0xaf ? 1 : 0;
    if (a == 0xe2 && b == 0x81) return c == 0x9f ? 1 : c == 0xa0 ? 3 : 0;
    if (a == 0xe3 && b == 0x80) return c == 0x80;
    if (a == 0xef && b == 0xbb) return c == 0xbf ? 3 : 0;
    return 0;
}

static void pf_dout(pf_parser_t *p, unsigned char c) { /* an output byte */
    int ws = 0;
    unsigned k = 0; /* the bytes of the character already in dbuf */
    if (p->dcut) return;
    if (c == 0xa0 && p->dn && (unsigned char)p->dbuf[p->dn - 1] == 0xc2)
        ws = 1, k = 1; /* U+00A0 (also from an entity): a space */
    else if ((c & 0xc0) == 0x80 && p->dn >= 2 &&
             (ws = pf_dws3((unsigned char)p->dbuf[p->dn - 2], (unsigned char)p->dbuf[p->dn - 1], c)) != 0)
        k = 2;
    if (ws) {
        int was = ws == 3 ? 0 : ws;
        p->dn -= k;
        if (p->dn && (p->dbuf[p->dn - 1] == ' ' ||
                      p->dbuf[p->dn - 1] == '\n')) { /* the one put before it: the pending one replaces it */
            int lvl = p->dbuf[p->dn - 1] == '\n' ? 2 : 1;
            if (lvl > was) was = lvl;
            --p->dn;
        }
        p->dspace = 0;
        p->dnlc = p->dnlc0; /* its bytes were text when they came: the run of newlines goes on through it */
        pf_dbrk(p, was);
        return;
    }
    if (c <= 32) {
        if (c == '\n' && ++p->dnlc >= 2)
            pf_dbrk(p, 2); /* a blank line is a paragraph break (plain text); a single newline is a space (HTML) */
        else
            pf_dbrk(p, 1);
        return;
    }
    if (p->dn + (p->dspace ? 2 : 1) > p->dlim) {
        p->dcut = 1, p->dcont = (c & 0xc0) == 0x80;
        return;
    }
    if (p->dspace) p->dbuf[p->dn++] = p->dspace == 2 ? '\n' : ' ', p->dspace = 0;
    if (c >= 0xc0) p->dnlc0 = p->dnlc;
    p->dnlc = 0;
    p->dbuf[p->dn++] = (char)c;
}

static void pf_dcp(pf_parser_t *p, unsigned cp) {
    char b[4];
    unsigned n = 0, k;
    if (pf_put_cp(b, &n, 4, cp))
        for (k = 0; k < n; ++k) pf_dout(p, (unsigned char)b[k]);
}

static int pf_alnum(int c) { return (unsigned)(c - '0') < 10u || (unsigned)(pf_lc(c) - 'a') < 26u; }

static void pf_dlit(pf_parser_t *p) { /* a '&' that is not an entity: as written */
    unsigned k;
    pf_dout(p, '&');
    for (k = 0; k < p->den; ++k) pf_dout(p, (unsigned char)p->dent[k]);
    p->dent_on = 0;
}

static int pf_dboundary(
    const pf_parser_t *p) { /* a tag that separates words: p, br, li, ul, ol, div, tr, td, h1..h6, hr, blockquote */
    static const char *const tab[] = {"p",  "br", "li", "ul", "ol", "div", "tr", "td",
                                      "h1", "h2", "h3", "h4", "h5", "h6",  "hr", "blockquote"};
    unsigned i;
    for (i = 0; i < sizeof tab / sizeof *tab; ++i)
        if (pf_is(p->dname, p->dnl, tab[i])) return 1;
    return 0;
}

static void pf_dbyte(pf_parser_t *p, unsigned char c) {
    if (p->dcut) return;
    if (p->dent_on) {
        if (c == ';') {
            unsigned cp = p->den == 4 && pf_is(p->dent, 4, "nbsp") ? 0xa0 : pf_ent_cp(p->dent, p->den);
            if (cp) {
                char b[4];
                unsigned n = 0;
                if (pf_put_cp(b, &n, 4, cp)) {
                    p->dent_on = 0;
                    pf_dcp(p, cp);
                    return;
                }
            }
            pf_dlit(p);
            pf_dout(p, ';');
            return;
        }
        if (p->den < 10 && (pf_alnum(c) || c == '#')) {
            p->dent[p->den++] = (char)c;
            return;
        }
        pf_dlit(p); /* not an entity after all: what was read, then this byte as any other */
    }
    switch (p->dm) {
    case DM_LT:
        if ((unsigned)(pf_lc(c) - 'a') < 26u || c == '/' || c == '!' || c == '?') {
            p->dm = DM_TAG, p->dtn = 0, p->dnl = 0, p->dnend = 0, p->dq = 0;
            pf_dbyte(p, c);
            return;
        }
        p->dm = DM_TEXT;
        pf_dout(p, '<');
        pf_dbyte(p, c);
        return;
    case DM_TAG:
        if (!p->dnend) {
            if (pf_alnum(c)) {
                if (p->dnl < sizeof p->dname - 1) p->dname[p->dnl++] = (char)pf_lc(c);
            } else if (!(c == '/' && p->dtn == 0))
                p->dnend = 1;
        }
        if (p->dtn < 3) p->dhead[p->dtn] = (char)c;
        ++p->dtn;
        if (p->dq) {
            if (c == (unsigned char)p->dq) p->dq = 0;
        } else if (c == '"' || c == '\'')
            p->dq = (char)c;
        else if (c == '>') {
            if (pf_dboundary(p))
                pf_dbrk(p, pf_is(p->dname, p->dnl, "td") ? 1 : 2); /* a cell is a space, the rest a paragraph */
            p->dm = DM_TEXT;
        } else if (p->dtn == 3 && p->dhead[0] == '!' && p->dhead[1] == '-' && p->dhead[2] == '-')
            p->dm = DM_COMMENT, p->dc1 = p->dc2 = 0;
        return;
    case DM_COMMENT:
        if (c == '>' && p->dc1 == '-' && p->dc2 == '-') p->dm = DM_TEXT;
        p->dc1 = p->dc2, p->dc2 = (char)c;
        return;
    default:
        if (c == '<')
            p->dm = DM_LT;
        else if (c == '&')
            p->dent_on = 1, p->den = 0;
        else
            pf_dout(p, c);
        return;
    }
}

static void pf_start_desc(pf_parser_t *p, int want) {
    p->dm = DM_TEXT, p->dn = 0, p->dspace = p->dcut = p->dcont = p->dent_on = 0;
    p->dq = 0, p->den = 0, p->dnlc = p->dnlc0 = 0;
    p->dlim =
        want < W_CSUM ? PF_NOTE : PC_DESC_CUT; /* an item's text is kept long (the episode page), the channel's short */
    p->dbuf[0] = 0;
    p->want = want, p->tn = 0, p->tover = 0, p->inent = 0, p->en = 0;
}

/* The end of the element: what is left of an open entity or '<' is text, a split last character goes, the text is trimmed; dbuf holds it (NUL ended). */
static void pf_dfinish(pf_parser_t *p) {
    unsigned n;
    if (!p->dcut) {
        if (p->dent_on) pf_dlit(p);
        if (p->dm == DM_LT) pf_dout(p, '<');
    }
    n = p->dn;
    if (p->dcut && p->dcont) {
        while (n && ((unsigned char)p->dbuf[n - 1] & 0xc0) == 0x80) --n;
        if (n) --n;
    }
    while (n && (p->dbuf[n - 1] == ' ' || p->dbuf[n - 1] == '\n')) --n;
    p->dbuf[n] = 0;
    p->dn = n;
}

/* The cell description x= from the long text: its first PC_DESC_CUT bytes with every paragraph break a space, cut before a split UTF-8 character, no trailing space (what the sink gave before the long text existed). */
static void pf_flat(char *dst, const char *src, unsigned n) {
    unsigned m = n, i;
    int cut = 0;
    if (m > PC_DESC_CUT) m = PC_DESC_CUT, cut = ((unsigned char)src[m] & 0xc0) == 0x80;
    for (i = 0; i < m; ++i) dst[i] = src[i] == '\n' ? ' ' : src[i];
    if (cut) {
        while (m && ((unsigned char)dst[m - 1] & 0xc0) == 0x80) --m;
        if (m) --m;
    }
    while (m && dst[m - 1] == ' ') --m;
    dst[m] = 0;
}

static void pf_txt_cp(pf_parser_t *p, unsigned cp) {
    if (p->want >=
        W_ISUM) { /* a character the parser decoded: its bytes go through the sink as any others (a '<' is a tag, an '&' an entity) */
        char b[4];
        unsigned n = 0, k;
        if (pf_put_cp(b, &n, 4, cp))
            for (k = 0; k < n; ++k) pf_dbyte(p, (unsigned char)b[k]);
    } else if (!pf_put_cp(p->txt, &p->tn, PF_TEXT - 1, cp))
        p->tover = 1;
}

static void pf_txt(pf_parser_t *p, unsigned char c) {
    if (p->want >= W_ISUM)
        pf_dbyte(p, c);
    else if (p->tn < PF_TEXT - 1)
        p->txt[p->tn++] = (char)c;
    else
        p->tover = 1;
}

/* A byte of character data (outside CDATA) of an element being collected: entities are decoded, an unknown one stays as written. */
static void pf_text_byte(pf_parser_t *p, unsigned char c) {
    if (p->inent) {
        if (c == ';') {
            unsigned cp = pf_ent_cp(p->ent, p->en), k;
            p->inent = 0;
            if (cp)
                pf_txt_cp(p, cp);
            else {
                pf_txt(p, '&');
                for (k = 0; k < p->en; ++k) pf_txt(p, (unsigned char)p->ent[k]);
                pf_txt(p, ';');
            }
            return;
        }
        if (p->en < sizeof p->ent && ((unsigned)(c - '0') < 10u || (unsigned)(pf_lc(c) - 'a') < 26u || c == '#')) {
            p->ent[p->en++] = (char)c;
            return;
        }
        { /* not an entity after all: what was read, literally, then this byte as any other */
            unsigned k;
            pf_txt(p, '&');
            for (k = 0; k < p->en; ++k) pf_txt(p, (unsigned char)p->ent[k]);
            p->inent = 0;
        }
    }
    if (c == '&')
        p->inent = 1, p->en = 0;
    else
        pf_txt(p, c);
}

static void pf_flush_ent(pf_parser_t *p) {
    if (p->inent && p->want) {
        unsigned k;
        pf_txt(p, '&');
        for (k = 0; k < p->en; ++k) pf_txt(p, (unsigned char)p->ent[k]);
    }
    p->inent = 0;
}

static void pf_start_text(pf_parser_t *p, int want) {
    p->want = want, p->tn = 0, p->tover = 0, p->inent = 0, p->en = 0;
}

static void pf_finish_text(pf_parser_t *p) {
    int w = p->want;
    p->want = 0;
    pf_flush_ent(p);
    p->txt[p->tn] = 0;
    if (w >= W_ISUM) {
        int item = w < W_CSUM, rank = w - (item ? W_ISUM : W_CSUM) + 1;
        pf_dfinish(p);
        if (p->dbuf[0]) { /* present: the first of the preference order wins */
            pf_flat(item ? p->cur.desc : p->summary, p->dbuf, p->dn);
            if (item) {
                free(
                    p->cur
                        .note); /* (the long text of the same element, for the notes file and the episode page; none when there is no memory) */
                p->cur.note = calloc(p->dn + 1, 1);
                if (p->cur.note) memcpy(p->cur.note, p->dbuf, p->dn);
                p->drank = rank;
            } else
                p->srank = rank;
        }
    } else if (w == W_AUTHOR) {
        if (!p->author[0]) pf_norm(p->author, PC_AUTHOR, p->txt, p->tn);
    } else if (w == W_ITITLE)
        pf_norm(p->cur.title, PC_TITLE, p->txt, p->tn);
    else if (w == W_CTITLE)
        pf_norm(p->title, PC_TITLE, p->txt, p->tn);
    else if (w == W_GUID)
        pf_norm(p->cur.guid, PF_GUID, p->txt, p->tn);
    else if (w == W_PUB)
        p->cur.pub = pf_rfc822(p->txt);
    else if (w == W_DUR)
        p->cur.dur = pf_duration(p->txt);
    else if (w == W_IMGURL && !p->image[0])
        pf_norm(p->image, PC_URL, p->txt, p->tn);
}

/* The element a tag names: its code, for the names the parser looks at. */
static int pf_code(const char *nm, unsigned len) {
    static const struct {
        const char *name;
        int code;
    } tab[] = {
        {"item", E_ITEM},
        {"title", E_TITLE},
        {"guid", E_GUID},
        {"pubDate", E_PUB},
        {"enclosure", E_ENCL},
        {"itunes:duration", E_DUR},
        {"itunes:image", E_ITUNES_IMAGE},
        {"itunes:summary", E_ISUM},
        {"description", E_DESC},
        {"content:encoded", E_ENC},
        {"itunes:author", E_AUTHOR},
        {"itunes:category", E_CAT},
        {"image", E_IMAGE},
        {"url", E_URL},
        {"rss", E_RSS},
        {"channel", E_RSS},
    };
    unsigned i;
    for (i = 0; i < sizeof tab / sizeof *tab; ++i)
        if (pf_is(nm, len, tab[i].name)) return tab[i].code;
    return E_NONE;
}

/* The item just read, into the kept list: newest first by pubDate, a later item after an equal date; a full list drops the oldest. */
static void pf_keep(pf_parser_t *p) {
    int i;
    pf_item_t *c = &p->cur;
    if (!c->url[0]) return;
    if (!c->guid[0]) pf_norm(c->guid, PF_GUID, c->url, strlen(c->url));
    ++p->seen;
    if (p->sink) { /* the streaming mode (the archive): the item is handed over whole and not kept; its note stays in cur until the next item */
        p->sink(p->sink_ctx, c);
        return;
    }
    if (p->nitems == PF_KEEP) {
        if (c->pub <= p->items[PF_KEEP - 1].pub) return;
        i = PF_KEEP - 1;
        free(p->items[i].note); /* the oldest goes */
    } else
        i = p->nitems++;
    while (i > 0 && p->items[i - 1].pub < c->pub) {
        memcpy(&p->items[i], &p->items[i - 1], sizeof *c);
        --i;
    }
    memcpy(&p->items[i], c, sizeof *c);
    c->note = (char *)0; /* (the kept item owns it now) */
}

static void pf_open(pf_parser_t *p, int code, int selfclose) {
    unsigned n = p->tl;
    char buf[PF_URL];
    if (code == E_RSS)
        p->saw_feed = 1;
    else if (code == E_ITEM) {
        p->in_item = 1;
        p->drank = 0;
        free(p->cur.note);
        memset(&p->cur, 0, sizeof p->cur);
    } else if (code == E_ISUM || code == E_DESC || code == E_ENC) {
        int rank = code == E_ISUM ? 1 : code == E_DESC ? 2 : 3;
        if (p->in_item) {
            if (!p->drank || rank < p->drank) pf_start_desc(p, W_ISUM + rank - 1);
        } else if (!p->in_image && code != E_ENC && (!p->srank || rank < p->srank))
            pf_start_desc(p, W_CSUM + rank - 1);
    } else if (code == E_AUTHOR) {
        if (!p->in_item && !p->in_image && !p->author[0]) pf_start_text(p, W_AUTHOR);
    } else if (code == E_CAT) {
        if (!p->in_item && !p->category[0] && pf_attr(p->tag, n, "text", buf, sizeof buf))
            pf_norm(p->category, PC_CAT, buf, strlen(buf));
    } else if (code == E_IMAGE) {
        if (!p->in_item) p->in_image = 1;
    } else if (code == E_TITLE) {
        if (p->in_item)
            pf_start_text(p, W_ITITLE);
        else if (!p->in_image && !p->title[0])
            pf_start_text(p, W_CTITLE);
    } else if (code == E_GUID) {
        if (p->in_item) pf_start_text(p, W_GUID);
    } else if (code == E_PUB) {
        if (p->in_item) pf_start_text(p, W_PUB);
    } else if (code == E_DUR) {
        if (p->in_item) pf_start_text(p, W_DUR);
    } else if (code == E_URL) {
        if (p->in_image && !p->image[0]) pf_start_text(p, W_IMGURL);
    } else if (code == E_ENCL) {
        if (p->in_item && !p->cur.url[0] && pf_attr(p->tag, n, "url", buf, sizeof buf)) {
            char type[PF_TYPE], len[16];
            type[0] = 0;
            pf_attr(p->tag, n, "type", type, sizeof type); /* a picture or a page is no episode */
            if (!(type[0] == 'i' || type[0] == 't')) {
                pf_norm(p->cur.url, PF_URL, buf, strlen(buf));
                pf_norm(p->cur.type, PF_TYPE, type, strlen(type));
                if (pf_attr(p->tag, n, "length", len, sizeof len)) {
                    unsigned v = 0, i;
                    for (i = 0; len[i] && (unsigned)(len[i] - '0') < 10u && v < 429496729u; ++i)
                        v = v * 10 + (unsigned)(len[i] - '0');
                    p->cur.length = v;
                }
            }
        }
    } else if (code == E_ITUNES_IMAGE) {
        if (!p->in_item && !p->img_itunes && pf_attr(p->tag, n, "href", buf, sizeof buf)) {
            pf_norm(p->image, PC_URL, buf, strlen(buf));
            p->img_itunes = p->image[0] != 0;
        }
    }
    if (selfclose && p->want) p->want = 0; /* an empty element */
}

static void pf_close(pf_parser_t *p, int code) {
    int w = p->want;
    if (w && ((code == E_ISUM && (w == W_ISUM || w == W_CSUM)) || (code == E_DESC && (w == W_IDESC || w == W_CDESC)) ||
              (code == E_ENC && w == W_IENC) || (code == E_AUTHOR && w == W_AUTHOR) ||
              (code == E_TITLE && (w == W_ITITLE || w == W_CTITLE)) || (code == E_GUID && w == W_GUID) ||
              (code == E_PUB && w == W_PUB) || (code == E_DUR && w == W_DUR) || (code == E_URL && w == W_IMGURL)))
        pf_finish_text(p);
    if (code == E_ITEM && p->in_item) {
        p->in_item = 0;
        p->want = 0;
        pf_keep(p);
    } else if (code == E_IMAGE)
        p->in_image = 0;
}

/* The tag in p->tag[0..tl) is complete. */
static void pf_tag(pf_parser_t *p) {
    const char *nm = p->tag + 1;
    unsigned n = 0, tl = p->tl;
    int closing = p->tag[1] == '/', selfclose = !p->trunc && tl >= 3 && p->tag[tl - 2] == '/';
    if (closing) ++nm;
    while (nm + n < p->tag + tl && (unsigned char)nm[n] > 32 && nm[n] != '/' && nm[n] != '>') ++n;
    if (closing)
        pf_close(p, pf_code(nm, n));
    else {
        int code = pf_code(nm, n);
        pf_open(p, code, selfclose);
        if (selfclose && (code == E_ITEM)) pf_close(p, code);
    }
}

void pf_push(pf_parser_t *p, const char *d, unsigned n) {
    unsigned i = 0;
    while (i < n) {
        unsigned char c = (unsigned char)d[i];
        switch (p->mode) {
        case M_TEXT:
            if (c == '<') {
                pf_flush_ent(p);
                p->mode = M_TAG, p->tag[0] = '<', p->tl = 1, p->quote = 0, p->trunc = 0;
            } else if (p->want)
                pf_text_byte(p, c);
            else
                while (i + 1 < n && d[i + 1] != '<') ++i; /* nothing is collected: skip to the next tag */
            break;
        case M_TAG:
            if (p->tl < PF_TAG - 1)
                p->tag[p->tl++] = (char)c;
            else
                p->trunc = 1;
            if (!p->trunc && p->tl == 2 && c == '?')
                p->mode = M_SKIP; /* <?xml ... ?> */
            else if (!p->trunc && p->tl == 3 && p->tag[1] == '!' && c != '-' && c != '[')
                p->mode = M_SKIP; /* <!DOCTYPE ...> */
            else if (!p->trunc && p->tl == 4 && p->tag[1] == '!' && p->tag[2] == '-' && c == '-')
                p->mode = M_COMMENT, p->d1 = p->d2 = 0;
            else if (!p->trunc && p->tl == 9 && p->tag[1] == '!' && p->tag[2] == '[' && c == '[' && p->tag[8] == '[')
                p->mode = M_CDATA, p->d1 = p->d2 = 0;
            else if (p->quote) {
                if (c == (unsigned char)p->quote) p->quote = 0;
            } else if (c == '"' || c == '\'')
                p->quote = (char)c;
            else if (c == '>') {
                p->mode = M_TEXT;
                pf_tag(p);
            }
            break;
        case M_SKIP:
            if (c == '>') p->mode = M_TEXT;
            break;
        case M_COMMENT:
            if (c == '>' && p->d1 == '-' && p->d2 == '-') p->mode = M_TEXT;
            p->d1 = p->d2, p->d2 = (char)c;
            break;
        case M_CDATA:
            if (c == '>' && p->d1 == ']' && p->d2 == ']') {
                p->mode = M_TEXT;
                if (p->want && p->want < W_ISUM && !p->tover && p->tn >= 2)
                    p->tn -= 2; /* the "]]" that was kept as text */
            } else if (p->want >= W_ISUM) {
                if (p->d1)
                    pf_dbyte(
                        p, (unsigned char)
                               p->d1); /* the description sink gets each byte two late, so the "]]" never reaches it */
            } else if (p->want)
                pf_txt(p, c);
            p->d1 = p->d2, p->d2 = (char)c;
            break;
        }
        ++i;
    }
}

/* ---------------------------------------------------------------------------
 * File names
 */

/* A title as a file name: forbidden characters (the card is ExFAT: \ / : * ? " < > | and controls) turn into '-', white space runs into one space, at most max bytes
 * (cut before a split character), no leading dot or space, no trailing dot or space. */
static void pf_slug(char *out, unsigned cap, const char *title, unsigned max) {
    char tmp[PC_TITLE + 8];
    unsigned i, o = 0, n = strlen(title);
    if (max > cap - 1) max = cap - 1;
    pf_norm(tmp, sizeof tmp, title, n);
    for (i = 0; tmp[i]; ++i) {
        char c = tmp[i];
        if (c == '/' || c == '\\' || c == ':' || c == '*' || c == '?' || c == '"' || c == '<' || c == '>' || c == '|')
            c = '-';
        tmp[i] = c;
    }
    for (i = 0; tmp[i] == '.' || tmp[i] == ' ' || tmp[i] == '-'; ++i) {
    }
    n = strlen(tmp);
    for (; i < n && o < max; ++i) out[o++] = tmp[i];
    if (i < n && ((unsigned char)tmp[i] & 0xc0) == 0x80) {
        while (o && ((unsigned char)out[o - 1] & 0xc0) == 0x80) --o;
        if (o) --o;
    }
    while (o && (out[o - 1] == '.' || out[o - 1] == ' ')) --o;
    out[o] = 0;
}

void pf_folder_name(char *out, unsigned size, const char *title) { pf_slug(out, size, title, PF_MAX_FILE); }

static int pf_audio_ext(const char *e, unsigned n) {
    static const char *const ext[] = {"mp3", "m4a", "m4b", "aac", "ogg", "opus", "flac", "wav", "wma"};
    unsigned i, k;
    char low[8];
    if (n >= sizeof low) return 0;
    for (k = 0; k < n; ++k) low[k] = (char)pf_lc((unsigned char)e[k]);
    for (i = 0; i < sizeof ext / sizeof *ext; ++i)
        if (pf_is(low, n, ext[i])) return 1;
    return 0;
}

/* The extension of an episode's file: the url path's when it is an audio one, else from the MIME type, else mp3. */
static const char *pf_ext(const pf_item_t *it, char *ext) { /* ext: 8 bytes (the result may point into it) */
    const char *u = it->url, *dot = (const char *)0, *s;
    unsigned n = 0, i;
    for (s = u; *s && *s != '?' && *s != '#'; ++s) {
        if (*s == '/')
            dot = (const char *)0;
        else if (*s == '.')
            dot = s + 1;
    }
    if (dot && (unsigned)(s - dot) < 6 && pf_audio_ext(dot, (unsigned)(s - dot))) {
        for (i = 0; i < (unsigned)(s - dot); ++i) ext[n++] = (char)pf_lc((unsigned char)dot[i]);
        ext[n] = 0;
        return ext;
    }
    if (pf_is(it->type, strlen(it->type), "audio/mp4") || pf_is(it->type, strlen(it->type), "audio/x-m4a") ||
        pf_is(it->type, strlen(it->type), "audio/m4a"))
        return "m4a";
    if (pf_is(it->type, strlen(it->type), "audio/aac")) return "aac";
    if (pf_is(it->type, strlen(it->type), "audio/ogg")) return "ogg";
    return "mp3";
}

/* "YYYY-MM-DD Title.ext" (no date when the item has none), at most PF_MAX_FILE bytes. */
static void pf_fname(const pf_item_t *it, char *out, unsigned size) {
    char slug[PC_TITLE + 8], extbuf[8];
    const char *ext = pf_ext(it, extbuf);
    unsigned o = 0, k, room;
    int y, m, d;
    if (it->pub) {
        pf_civil(it->pub / 86400, &y, &m, &d);
        out[o++] = (char)('0' + y / 1000 % 10), out[o++] = (char)('0' + y / 100 % 10),
        out[o++] = (char)('0' + y / 10 % 10), out[o++] = (char)('0' + y % 10);
        out[o++] = '-', out[o++] = (char)('0' + m / 10), out[o++] = (char)('0' + m % 10);
        out[o++] = '-', out[o++] = (char)('0' + d / 10), out[o++] = (char)('0' + d % 10);
        out[o++] = ' ';
    }
    room = PF_MAX_FILE - o - strlen(ext) - 1;
    pf_slug(slug, sizeof slug, it->title, room);
    if (!slug[0]) memcpy(slug, "episode", 8);
    for (k = 0; slug[k] && o + 1 < size; ++k) out[o++] = slug[k];
    out[o++] = '.';
    for (k = 0; ext[k] && o + 1 < size; ++k) out[o++] = ext[k];
    out[o] = 0;
}

/* f with " (n)" before its extension: "2026-10-30 Title.mp3" becomes "2026-10-30 Title (2).mp3". */
static void pf_numbered(char *f, unsigned size, unsigned n) {
    unsigned fl = strlen(f), dot = fl, tl;
    char tail[12];
    while (dot && f[dot - 1] != '.') --dot;
    dot = dot ? dot - 1 : fl;
    tl = fl - dot;
    if (tl >= sizeof tail || dot + 4 + tl + 1 > size) return;
    memcpy(tail, f + dot, tl + 1);
    f[dot++] = ' ', f[dot++] = '(', f[dot++] = (char)('0' + n), f[dot++] = ')';
    memcpy(f + dot, tail, tl + 1);
}

/* ---------------------------------------------------------------------------
 * The writers
 */
static void pf_app(char *out, unsigned *o, unsigned cap, const char *s) {
    while (*s && *o + 1 < cap) out[(*o)++] = *s++;
}

static void pf_app_n(char *out, unsigned *o, unsigned cap, const char *s, unsigned n) {
    unsigned i;
    for (i = 0; i < n && *o + 1 < cap; ++i) out[(*o)++] = s[i];
}

static void pf_app_u(char *out, unsigned *o, unsigned cap, unsigned v) {
    char num[12];
    unsigned k = 0;
    do num[k++] = (char)('0' + v % 10), v /= 10;
    while (v);
    while (k && *o + 1 < cap) out[(*o)++] = num[--k];
}

/* Text with white space and control bytes as single spaces: the text formats have no tab or newline inside a value. */
static void pf_app_plain(char *out, unsigned *o, unsigned cap, const char *s) {
    char tmp[PF_URL];
    pf_norm(tmp, sizeof tmp, s, strlen(s));
    pf_app(out, o, cap, tmp);
}

unsigned pf_render_show(const char *title, const char *feed, const char *image, unsigned checked, unsigned modified,
                        const char *author, const char *category, const char *desc, char *out, unsigned cap) {
    unsigned o = 0;
    pf_app(out, &o, cap, "M1PLUS-SHOW 1\ntitle=");
    pf_app_plain(out, &o, cap, title);
    pf_app(out, &o, cap, "\nfeed=");
    pf_app_plain(out, &o, cap, feed);
    pf_app(out, &o, cap, "\nimage=");
    pf_app_plain(out, &o, cap, image);
    pf_app(out, &o, cap, "\nchecked=");
    pf_app_u(out, &o, cap, checked);
    pf_app(out, &o, cap, "\n");
    if (modified) { /* the server's Last-Modified of the copy we hold: the next request's condition */
        pf_app(out, &o, cap, "modified=");
        pf_app_u(out, &o, cap, modified);
        pf_app(out, &o, cap, "\n");
    }
    if (author[0]) { /* the descriptive keys only when there is something to say */
        pf_app(out, &o, cap, "author=");
        pf_app_plain(out, &o, cap, author);
        pf_app(out, &o, cap, "\n");
    }
    if (category[0]) {
        pf_app(out, &o, cap, "category=");
        pf_app_plain(out, &o, cap, category);
        pf_app(out, &o, cap, "\n");
    }
    if (desc[0]) {
        pf_app(out, &o, cap, "desc=");
        pf_app_plain(out, &o, cap, desc);
        pf_app(out, &o, cap, "\n");
    }
    out[o] = 0;
    return o;
}

/* The value of the field `key=` of a tab separated line (0 when there is none). */
static int pf_field(const char *line, unsigned n, char key, const char **v, unsigned *vn) {
    unsigned at = 0;
    while (at < n) {
        unsigned flen = 0;
        while (at + flen < n && line[at + flen] != '\t') ++flen;
        if (flen >= 2 && line[at] == key && line[at + 1] == '=') {
            *v = line + at + 2, *vn = flen - 2;
            return 1;
        }
        at += flen + 1;
    }
    return 0;
}

static int pf_same(const char *a, unsigned an, const char *b) {
    unsigned i;
    for (i = 0; i < an; ++i)
        if (a[i] != b[i]) return 0;
    return !b[an];
}

static int pf_file_here(const char *dir, const char *f, unsigned fn) {
    char path[PC_FILE * 2 + 40];
    unsigned o = 0;
    if (!fn || fn >= PC_FILE) return 0;
    pf_app(path, &o, sizeof path, dir);
    pf_app(path, &o, sizeof path, "/");
    pf_app_n(path, &o, sizeof path, f, fn);
    path[o] = 0;
    if (access(path, F_OK) == 0) return 1;
    pf_app(path, &o, sizeof path, ".part");
    path[o] = 0;
    return access(path, F_OK) == 0;
}

int pf_find_episode(const char *eps, unsigned n, const char *file, char *url, unsigned usize, unsigned *length) {
    const char *stop = eps + n, *q, *next;
    for (q = eps; q < stop; q = next) {
        unsigned len = m1_line(q, stop, &next), fn, un, ln, i, num = 0;
        const char *f, *u, *l;
        if (!len || q[0] == '#' || !pf_field(q, len, 'f', &f, &fn) || !pf_same(f, fn, file)) continue;
        if (!pf_field(q, len, 'u', &u, &un) || !un || un >= usize) return 0;
        memcpy(url, u, un);
        url[un] = 0;
        if (pf_field(q, len, 'l', &l, &ln))
            for (i = 0; i < ln && l[i] >= '0' && l[i] <= '9' && num <= 0x19999999u; ++i)
                num = num * 10 + (unsigned)(l[i] - '0');
        else
            i = ln = 0;
        *length = i == ln && num <= 0x7fffffffu ? num : 0; /* not a number, or too large to be a file here: unknown */
        return 1;
    }
    return 0;
}

unsigned pf_render_note(const pf_parser_t *p, int i, char *out, unsigned cap) {
    const pf_item_t *it = pf_item(p, i);
    unsigned o = 0, k;
    char g[PF_GUID + 4];
    if (!it || !it->note || !it->note[0]) return 0;
    g[0] = 0;
    {
        unsigned go = 0;
        pf_app_plain(g, &go, sizeof g, it->guid);
        g[go] = 0;
    }
    pf_app(out, &o, cap, "g=");
    pf_app(out, &o, cap, g);
    pf_app(out, &o, cap, "\t");
    for (k = 0; it->note[k]; ++k) {
        char c = it->note[k];
        if (o + 3 >= cap) return 0;
        if (c == '\\')
            pf_app(out, &o, cap, "\\\\");
        else if (c == '\n')
            pf_app(out, &o, cap, "\\n");
        else
            out[o++] = c;
    }
    if (o + 2 > cap) return 0;
    out[o++] = '\n';
    out[o] = 0;
    return o;
}

unsigned pf_item_line(const pf_item_t *it, const char *f, const char *od, char *ln, unsigned cap) {
    unsigned lo = 0;
    pf_app(ln, &lo, cap, "g=");
    pf_app_plain(ln, &lo, cap, it->guid);
    pf_app(ln, &lo, cap, "\tp=");
    pf_app_u(ln, &lo, cap, it->pub);
    pf_app(ln, &lo, cap, "\td=");
    pf_app_u(ln, &lo, cap, it->dur);
    pf_app(ln, &lo, cap, "\tl=");
    pf_app_u(ln, &lo, cap, it->length);
    pf_app(ln, &lo, cap, "\tf=");
    pf_app(ln, &lo, cap, f);
    pf_app(ln, &lo, cap, "\tt=");
    pf_app_plain(ln, &lo, cap, it->title);
    pf_app(ln, &lo, cap, "\tu=");
    pf_app_plain(ln, &lo, cap, it->url);
    if (it->desc[0] || od[0]) {
        pf_app(ln, &lo, cap, "\tx=");
        pf_app_plain(ln, &lo, cap, it->desc[0] ? it->desc : od);
    }
    pf_app(ln, &lo, cap, "\n");
    return lo;
}

void pf_item_file(const pf_item_t *it, unsigned tries, char *out, unsigned size) {
    pf_fname(it, out, size);
    if (tries > 1) pf_numbered(out, size, tries);
}

unsigned pf_render_episodes(const pf_parser_t *p, const char *dir, const char *old, unsigned oldn, char *out,
                            unsigned cap, unsigned *fresh) {
    unsigned o = 0, k, n = 0, lo;
    char names[PF_KEEP][PC_FILE], ln[1536];
    const char *stop = old ? old + oldn : (const char *)0, *q, *next;
    if (cap > PF_EPS_MAX) cap = PF_EPS_MAX;
    *fresh = 0;
    pf_app(out, &o, cap, "M1PLUS-EPISODES 1\n");
    for (k = 0; k < (unsigned)p->nitems; ++k) {
        const pf_item_t *it = &p->items[k];
        char f[PC_FILE], od[PC_DESC];
        const char *fv = (const char *)0;
        unsigned fn = 0, gl = strlen(it->guid), j, tries;
        f[0] = od[0] = 0;
        if (old) { /* an old line with this guid keeps its file name (and its description when the feed has none now) */
            for (q = old; q < stop; q = next) {
                unsigned len = m1_line(q, stop, &next), vn;
                const char *v;
                if (len && pf_field(q, len, 'g', &v, &vn) && vn == gl && pf_same(v, vn, it->guid)) {
                    const char *xv;
                    unsigned xn;
                    if (pf_field(q, len, 'f', &fv, &fn) && fn && fn < PC_FILE) memcpy(f, fv, fn), f[fn] = 0;
                    if (pf_field(q, len, 'x', &xv, &xn)) pf_norm(od, PC_DESC, xv, xn);
                    break;
                }
            }
            if (q >= stop) ++*fresh;
        } else
            ++*fresh;
        if (!f[0]) {
            char base[PC_FILE];
            pf_fname(it, f, sizeof f);
            memcpy(base, f, strlen(f) + 1);
            for (tries = 2; tries < 10;
                 ++tries) { /* two items of one day with one title: a number before the extension */
                int clash = 0;
                for (j = 0; j < n; ++j)
                    if (pf_same(names[j], strlen(names[j]), f)) clash = 1;
                if (!clash) break;
                memcpy(f, base, strlen(base) + 1);
                pf_numbered(f, sizeof f, tries);
            }
        }
        memcpy(names[n], f, strlen(f) + 1);
        ++n;
        lo = pf_item_line(it, f, od, ln,
                          sizeof ln); /* made whole, and added whole: a full buffer never ends in half a line */
        if (o + lo < cap) memcpy(out + o, ln, lo), o += lo;
    }
    if (old) /* the old entries that are not in the feed's window any more but have their file (or a started download) stay, as they were written */
        for (q = old; q < stop; q = next) {
            unsigned len = m1_line(q, stop, &next), vn, fnn;
            const char *v, *fvv;
            int listed = 0;
            if (!len || q[0] == '#' || !pf_field(q, len, 'f', &fvv, &fnn) || !pf_file_here(dir, fvv, fnn)) continue;
            if (pf_field(q, len, 'g', &v, &vn))
                for (k = 0; k < (unsigned)p->nitems; ++k)
                    if (vn == strlen(p->items[k].guid) && pf_same(v, vn, p->items[k].guid)) listed = 1;
            if (listed || o + len + 2 >= cap) continue;
            pf_app_n(out, &o, cap, q, len);
            pf_app(out, &o, cap, "\n");
        }
    out[o] = 0;
    return o;
}
