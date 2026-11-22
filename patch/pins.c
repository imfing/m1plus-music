/* M1+ Music Home pins: albums and playlists pinned at the very top of the Home instance of the menu (docs/modules/pins.md): PIN_COLS columns of PIN_COVER px covers with
 * the name under each, at most PIN_MAX, in the user's order (a new pin joins the end), scrolling with the list. No stock function is hooked: the section is a widget of the menu's own asset (ui/m1plus_menu.bin,
 * tools/pod_ui.py pins(): pod_pins, a view that is the first shown child of the list's scroll view, hidden and insensitive, and one hidden label that carries the name's text
 * style); patch/home.c calls pins_start for the Home instance only. Everything here runs from the section's and the menu window's events and one page-scoped timer.
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * The file .m1plus/home-pins on the card (PINS_FILE; no card: no pins, nothing written; tools/pod_pins_home.py is the model the tests compare with), strictly validated when read (anything else shows no pins and is never written over: pn_load, pn.good):
 *     M1P1\n
 *     <a|p|s|r>\t<key 8 hex>\t<cover key 8 hex> x 4\t<name>\t<path>\n      (one line per pin, in the user's order)
 * An album's key is its title's identity as Recently Played has it (the stock list groups albums by title alone), its first cover key the Cover Flow cache key of the album row and its
 * path a track of the album. A playlist's key is its stock id, its cover keys the (up to four) albums of the mosaic the Playlists page makes, found when it was pinned (so Home runs
 * no query to draw them), its path empty.
 *
 * The API (patch/pins.h) reads the file fresh, changes it and writes it back; it needs no menu. The section:
 *   start    looks the widgets up, registers the window events and the section's paint and pointer events, arms a one-shot PIN_FIRST_MS later (the menu's first paint decodes
 *            nothing) and, when something is pinned, sizes and shows the section (menu_pins in patch/menu.c: visible and sensitive together, the rows move down).
 *            Any widget missing, any registration or the timer failing: nothing is shown or moved, the menu is as it was.
 *   tiles    the grid's (patch/grid.c with PIN_COVER and PIN_R): an album's cover is its cache file box-reduced, a playlist's the mosaic of its keys (one source a tick), else the
 *            shared placeholder disc; ONE cover (or mosaic quarter) per PIN_TICK_MS tick on the page's timer, paint never decodes.
 *   refresh  EVT_WINDOW_TO_FG reads the file again and redoes only the tiles whose pin changed.
 *   check    once, from the menu's to-foreground at least PIN_CHECK_MS after the menu opened (the stock album list is loaded: never at boot, in a tick or in paint): an album pin
 *            takes its row's new cover key. No pin is ever dropped for a missing item (a library mid-scan lists fewer): a tap on one says "Not found" / "Can't play"; only Unpin removes.
 *   touch    a tile is its cover and its name; a press that begins on one and is released closer than SC_DRAG_PX to it on the same tile opens it (an album: our album page, as
 *            Recently Played does; a playlist: our Songs page on it, as the Playlists page does). A press held RM_LONG_MS opens the sheet (the Queue page's three-row sheet with
 *            other words: Play, Shuffle, and Unpin Album / Unpin Playlist by the tile's type), opened when the held press is released where it was.
 *            Held and then dragged SC_DRAG_PX, the tile (drawn larger) follows the finger, the others close up around the slot under it and the release saves the new order; the
 *            list's yslidable is off and the touch grabbed at the list for the lift (pn_lift_end gives both back on a release, an abort, the window leaving). Before the hold a
 *            drag is the scroll view's. The section never consumes an event.
 */
#include "offsets.inc"
#include "stock.h"
#include "home.h"
#include "covercache.h"
#include "common.h"
#include "grid.h"
#include "fnv.h"
#include "i18n.h"
#include "upnext.h"
#include "rowmenu.h"
#include "songops.h"
#include "entries.h"
#include "artistphoto.h"
#include "artists.h"
#include "albums.h"
#include "coverflow.h"
#include "pins.h"

#define PN_MAGIC "M1P1\n"
#define PN_MAGIC_LEN 5
#define PN_HEAD 47 /* kind, tab, key, tab, four cover keys each followed by a tab: the bytes before the name */

#if PIN_MAX != PIN_COLS * PIN_ROWS
#error the section shows every pin the file keeps: PIN_MAX = PIN_COLS * PIN_ROWS
#endif

typedef struct {
    char kind; /* a album, p playlist, s song, r artist */
    unsigned key; /* an album's identity (pn_album_id), a playlist's stock id (from 0); else never 0 */
    unsigned ck[4]; /* cover keys: an album's row key then zeros; a playlist's distinct album keys, then zeros */
    char name[PIN_STR],
        path[PIN_PATH]; /* a song's path is the file's alone; an artist's is its scope ("0" Artists, "1" Album Artists, "" an old line) */
    unsigned
        start; /* a song's CUE start (REC_CUE_START; 0: not a CUE track): the file's tracks share a path and tell apart by it */
} pin_t;

static struct {
    pin_t ent[PIN_MAX];
    unsigned n; /* pins held, in the user's order */
    int good; /* the last pn_load read the file (or found none): pn_save writes nothing else, so an unreadable file is never overwritten */
    void *win, *sec, *sv, *st_title, /* sv: the list's scroll_view (its yslidable is off while a tile is lifted) */
        *lab_row2,
        *ic_row2, /* the sheet's third row (Play Next on an album; Unpin Playlist / Unpin Artist on a three-row sheet) */
        *lab_pin, *ic_pin; /* the sheet's fifth row (Pin Album / Unpin Album on an album) */
    char xname[PIN_STR],
        xpath
            [PIN_PATH]; /* the album the open sheet is for when it came from Recently Played (pins_album_sheet): its title and a track path; xckey its cover key */
    unsigned xckey;
    void *lab_shuf, *ic_shuf; /* the second row's label and glyph (Shuffle; Unpin Song on a song's tile) */
    unsigned *tmp; /* one quadrant of a mosaic (PIN_COVER / 2 squared words) for grid_mosaic */
    unsigned timer; /* the one-shot or the decode tick, 0 none */
    int fg; /* the window is in front */
    int warm; /* the one-shot after start has run */
    int shown; /* the section is up */
    int checked; /* the library check has run */
    unsigned t0; /* time_now_ms at start: the check waits PIN_CHECK_MS after it */
    int down; /* the tile a press began on, + 1; 0 none */
    m1_tap_t tap;
    int lift, drag, slot, fx, fy,
        slide; /* a tile lifted by the hold (tile + 1, 0 none), dragged (moved SC_DRAG_PX), the slot it would land in, the finger in section coordinates, yslidable before the lift */
    grid_t g; /* the tiles (PIN_MAX, tile i shows entry i), the placeholder, the rounded corners: patch/grid.c */
    char tkind[PIN_MAX]; /* the pin each tile was made for: kind, key and cover keys */
    char tph
        [PIN_MAX]; /* an artist's tile that shows the placeholder (no photo yet): it looks again when the menu is in front */
    unsigned tkey[PIN_MAX], tck[PIN_MAX][4];
    rowmenu_t rm; /* the long press sheet */
} pn __attribute__((section(".scratch")));

/* ---------------------------------------------------------------------------
 * The file
 */
static int pn_bad(unsigned char c) { return c < 0x20 || c == 0x7f; }

static int pn_hex(unsigned c) {
    if (c - '0' < 10) return (int)(c - '0');
    if (c - 'a' < 6) return (int)(c - 'a' + 10);
    return -1;
}

/* 8 lowercase hex digits at p as a number; sets *ok to 0 when one is not. */
static unsigned pn_hex8(const char *p, int *ok) {
    unsigned v = 0, k;
    int d;
    for (k = 0; k < 8; ++k) {
        d = pn_hex((unsigned char)p[k]);
        if (d < 0) *ok = 0;
        v = v << 4 | (unsigned)(d < 0 ? 0 : d);
    }
    return v;
}

/* The field at *pp up to the byte `end`, at most max - 1 bytes, no control byte: copied to out, *pp after the end byte; the length, or -1 when it is malformed. */
static int pn_field(const char **pp, const char *stop, char end, char *out, unsigned max) {
    const char *p = *pp;
    unsigned n = 0;
    while (p < stop && *p != end) {
        if (pn_bad((unsigned char)*p) || n + 1 >= max) return -1;
        out[n++] = *p++;
    }
    if (p >= stop) return -1; /* no end byte: the file stops inside the line */
    out[n] = 0;
    *pp = p + 1;
    return (int)n;
}

/* One line at *pp into e; 1 when it is a valid pin. */
static int pn_line(const char **pp, const char *stop, pin_t *e) {
    const char *p = *pp;
    int ok = 1, k, nz = 0;
    if (stop - p < PN_HEAD + 2) return 0;
    e->kind = p[0];
    if ((e->kind != 'a' && e->kind != 'p' && e->kind != 's' && e->kind != 'r') || p[1] != '\t' || p[10] != '\t')
        return 0;
    e->key = pn_hex8(p + 2, &ok);
    for (k = 0; k < 4; ++k) {
        e->ck[k] = pn_hex8(p + 11 + 9 * k, &ok);
        if (p[19 + 9 * k] != '\t') return 0;
        if (e->ck[k]) ++nz;
    }
    if (!ok || (!e->key && e->kind != 'p')) return 0; /* (stock playlist ids start at 0) */
    if (e->kind != 'p' && (!e->ck[0] || nz != 1)) return 0; /* an album's, a song's and an artist's one cover key */
    if (e->kind == 'p') { /* the non-zero keys first, then zeros, no key twice */
        for (k = 0; k < 4; ++k)
            if ((k < nz) != (e->ck[k] != 0)) return 0;
        for (k = 1; k < nz; ++k)
            if (e->ck[k] == e->ck[0] || (k > 1 && e->ck[k] == e->ck[1]) || (k > 2 && e->ck[k] == e->ck[2])) return 0;
    }
    p += PN_HEAD;
    if (pn_field(&p, stop, '\t', e->name, PIN_STR) <= 0) return 0;
    if (pn_field(&p, stop, '\n', e->path, PIN_PATH) < 0) return 0;
    e->start = 0;
    if (e->kind == 'p' && *e->path) return 0;
    if (e->kind == 'r' && *e->path && ((e->path[0] != '0' && e->path[0] != '1') || e->path[1]))
        return 0; /* the scope, or an old line's none */
    if (e->kind == 's') { /* "/path", or "<CUE start>@/path" (a CUE track: no leading zero, 1 to 9 digits) */
        const char *q = e->path;
        unsigned v = 0, d = 0;
        while (*q >= '0' && *q <= '9' && d < 10) v = v * 10 + (unsigned)(*q++ - '0'), ++d;
        if (*q == '@' && d && d < 10 && e->path[0] != '0' && q[1] == '/') {
            e->start = v;
            for (d = 0, ++q; (e->path[d] = q[d]) != 0; ++d) {
            }
        } else if (e->path[0] != '/')
            return 0;
    }
    *pp = p;
    return 1;
}

/* errno values (the same numbers on MIPS o32): a file or a folder above it that is not there. */
#define PN_ENOENT 2
#define PN_ENOTDIR 20

/* 1 when the open that just failed means the file is not there (nothing else: a card that is busy or erroring says nothing about it). */
static int pn_absent(void) {
    int e = *__errno_location();
    return e == PN_ENOENT || e == PN_ENOTDIR;
}

/* PINS_FILE into pn.ent. 0: the list is in pn (the file absent, or empty, is no pins). -1: the file is there but could not be read (open, read) or is not a list we understand (magic, a field, a
 * seventh pin, too big, an unknown kind from a later version): pn.n is 0 (a display shows no pins; an unreadable one keeps the list it had) and pn.good is 0, so nothing is written over the file. */
static int pn_load(void) {
    char buf[PIN_FILE_MAX + 1];
    const char *p = buf, *stop;
    int fd, n = 0, r = 1, ok = 1;
    unsigned i, j;
    pn.good = 0;
    if (!m1_card_mounted()) { /* the pins belong to the card: no card, no pins (a write fails on its own) */
        pn.n = 0;
        return 0;
    }
    fd = open(PINS_FILE, O_RDONLY, 0);
    if (fd < 0) {
        if (!pn_absent()) return -1; /* an error is not "no pins" */
        pn.n = 0, pn.good = 1;
        return 0;
    }
    while (n < (int)sizeof buf && (r = read(fd, buf + n, sizeof buf - (unsigned)n)) > 0) n += r;
    close(fd);
    if (r < 0) return -1;
    pn.n = 0;
    if (!n) { /* a file with nothing in it holds nothing to lose */
        pn.good = 1;
        return 0;
    }
    if (n < PN_MAGIC_LEN || n > PIN_FILE_MAX) return -1;
    stop = buf + n;
    for (i = 0; i < PN_MAGIC_LEN; ++i)
        if (buf[i] != PN_MAGIC[i]) return -1;
    p += PN_MAGIC_LEN;
    while (ok && p < stop) {
        pin_t *e = &pn.ent[pn.n];
        if (pn.n >= PIN_MAX || !pn_line(&p, stop, e)) {
            ok = 0;
            break;
        }
        for (j = 0; j < pn.n; ++j)
            if (pn.ent[j].kind == e->kind && pn.ent[j].key == e->key) ok = 0;
        if (ok) ++pn.n;
    }
    if (!ok) {
        pn.n = 0;
        return -1;
    }
    pn.good = 1;
    return 0;
}

static void pn_put(char **o, const char *end, const char *s) {
    while (*s && *o < end) *(*o)++ = *s++;
}

static void pn_puthex(char **o, const char *end, unsigned v) {
    char hex[9];
    unsigned k;
    for (k = 0; k < 8; ++k) hex[k] = "0123456789abcdef"[v >> (28 - 4 * k) & 15];
    hex[8] = 0;
    pn_put(o, end, hex);
}

/* The decimal digits of v. */
static void pn_putdec(char **o, const char *end, unsigned v) {
    char d[11];
    unsigned n = 0;
    do d[n++] = (char)('0' + v % 10), v /= 10;
    while (v);
    while (n) {
        if (*o < end)
            *(*o)++ = d[--n];
        else
            --n;
    }
}

/* The list as the file holds it, on the card; 0 when it was written. -1 and nothing written while the last pn_load did not read the file: the list in memory is not the file's, and the file may be one
 * that is only unreadable now (a card that errors, a list written by a later version), so it is left as it is. */
static int pn_save(void) {
    char buf[PIN_FILE_MAX + 1], *o = buf, kind[2];
    const char *end = buf + PIN_FILE_MAX;
    unsigned i, k;
    if (!pn.good) return -1;
    pn_put(&o, end, PN_MAGIC);
    kind[1] = 0;
    for (i = 0; i < pn.n; ++i) {
        kind[0] = pn.ent[i].kind;
        pn_put(&o, end, kind);
        pn_put(&o, end, "\t");
        pn_puthex(&o, end, pn.ent[i].key);
        pn_put(&o, end, "\t");
        for (k = 0; k < 4; ++k) {
            pn_puthex(&o, end, pn.ent[i].ck[k]);
            pn_put(&o, end, "\t");
        }
        pn_put(&o, end, pn.ent[i].name);
        pn_put(&o, end, "\t");
        if (pn.ent[i].kind == 's' && pn.ent[i].start) {
            pn_putdec(&o, end, pn.ent[i].start);
            pn_put(&o, end, "@");
        }
        pn_put(&o, end, pn.ent[i].path);
        pn_put(&o, end, "\n");
    }
    return m1_card_write(CARD_DIR, PINS_FILE, PINS_TMP, buf, (unsigned)(o - buf), (const void *)0,
                         0); /* -1 and nothing written while the card is out */
}

/* s into out (size bytes with the NUL), control bytes as spaces, cut before a UTF-8 continuation byte that would be split. */
static void pn_copy(char *out, unsigned size, const char *s) {
    unsigned n = 0, j;
    while (s[n]) ++n;
    if (n >= size) {
        n = size - 1;
        while (n && ((unsigned char)s[n] & 0xc0) == 0x80) --n;
    }
    for (j = 0; j < n; ++j) out[j] = pn_bad((unsigned char)s[j]) ? ' ' : s[j];
    out[n] = 0;
}

/* The album's identity: FNV-1a of its title with ASCII letters folded to lower case, never 0 (Recently Played's rc_id; the stock album list groups albums by title alone). */
static unsigned pn_album_id(const char *album) {
    unsigned h = m1_fnv_fold(FNV_SEED, album);
    return h | !h;
}

static int pn_at(char kind, unsigned key) {
    unsigned i;
    for (i = 0; i < pn.n; ++i)
        if (pn.ent[i].kind == kind && pn.ent[i].key == key) return (int)i;
    return -1;
}

/* ---------------------------------------------------------------------------
 * The API (patch/pins.h)
 */
/* e to the end of the file's list: the others keep their places. A playlist pin of the same id and another name is a deleted playlist's (stock reuses the ids): it is replaced in place. A write that fails puts the list in memory back
 * as the file has it, so a section redone from it keeps what the file keeps. */
static int pn_pin(const pin_t *e) {
    pin_t old[PIN_MAX];
    unsigned on;
    int at;
    if (pn_load() < 0) { /* the file is there and cannot be read: the new list would replace it */
        pod_toast(TR("Can't update pins"));
        return PINS_FAIL;
    }
    at = pn_at(e->kind, e->key);
    if (at >= 0 && (e->kind != 'p' || !strcmp(pn.ent[at].name, e->name))) return PINS_OK;
    if (at < 0 && pn.n >= PIN_MAX) {
        pod_toast(TR("Unpin an item first"));
        return PINS_FULL;
    }
    memcpy(old, pn.ent, sizeof old);
    on = pn.n;
    if (at < 0) at = (int)pn.n++;
    memcpy(&pn.ent[at], e, sizeof *e); /* (an explicit call: the payload links no compiler-made memcpy) */
    if (pn_save() == 0) return PINS_OK;
    memcpy(pn.ent, old, sizeof old);
    pn.n = on;
    pod_toast(TR("Can't update pins"));
    return PINS_FAIL;
}

/* Removes the pin of kind and key (a playlist's also by `name` when given: a replacement playlist is not the deleted one's pin). loud: a pin the user asked to remove (the toast when the file cannot be read or written); not loud: one the
 * library no longer has (nothing is said, the pin stays until the file reads and writes). A write that fails puts the pin back in memory: 0 then, as when there was none. */
static int pn_unpin(char kind, unsigned key, const char *name, int loud) {
    pin_t old[PIN_MAX];
    unsigned i, on;
    int at;
    if (pn_load() < 0) {
        if (loud) pod_toast(TR("Can't update pins"));
        return 0;
    }
    at = pn_at(kind, key);
    if (at >= 0 && name && strcmp(pn.ent[at].name, name)) at = -1;
    if (at < 0) return 0;
    memcpy(old, pn.ent, sizeof old);
    on = pn.n;
    for (i = (unsigned)at; i + 1 < pn.n; ++i) memcpy(&pn.ent[i], &pn.ent[i + 1], sizeof pn.ent[0]);
    --pn.n;
    if (pn_save() == 0) return 1;
    memcpy(pn.ent, old, sizeof old);
    pn.n = on;
    if (loud) pod_toast(TR("Can't update pins"));
    return 0;
}

int pins_pin_album(const char *album, unsigned ckey, const char *path) {
    pin_t e;
    if (!album || !*album || !ckey) return PINS_FAIL;
    memset(&e, 0, sizeof e);
    e.kind = 'a';
    e.key = pn_album_id(album);
    e.ck[0] = ckey;
    pn_copy(e.name, sizeof e.name, album);
    pn_copy(e.path, sizeof e.path, path ? path : "");
    if (!*e.name) return PINS_FAIL;
    return pn_pin(&e);
}

int pins_pin_playlist(int id, const char *name, const unsigned *keys, unsigned nk) {
    pin_t e;
    unsigned i, j, m = 0;
    if (id < 0 || !name || !*name) return PINS_FAIL;
    memset(&e, 0, sizeof e);
    e.kind = 'p';
    e.key = (unsigned)id;
    for (i = 0; keys && i < nk && m < 4; ++i) { /* the distinct non-zero keys, in order */
        for (j = 0; j < m && e.ck[j] != keys[i]; ++j) {
        }
        if (keys[i] && j == m) e.ck[m++] = keys[i];
    }
    pn_copy(e.name, sizeof e.name, name);
    if (!*e.name) return PINS_FAIL;
    return pn_pin(&e);
}

int pins_has_album(const char *album) {
    if (!album || !*album) return 0;
    pn_load();
    return pn_at('a', pn_album_id(album)) >= 0;
}

/* The playlist's pin: its id and its name as the file keeps it (a replacement playlist reuses a deleted one's id: another name is another playlist). -1 when there is none. */
static int pn_pl_at(int id, const char *name) {
    char nm[PIN_STR];
    int at;
    if (id < 0 || !name || !*name) return -1;
    pn_copy(nm, sizeof nm, name);
    at = pn_at('p', (unsigned)id);
    return at >= 0 && !strcmp(pn.ent[at].name, nm) ? at : -1;
}

int pins_has_playlist(int id, const char *name) {
    pn_load();
    return pn_pl_at(id, name) >= 0;
}

const char *pins_label_album(const char *album) { return pins_has_album(album) ? "Unpin Album" : "Pin Album"; }
const char *pins_label_playlist(int id, const char *name) {
    return pins_has_playlist(id, name) ? "Unpin Playlist" : "Pin Playlist";
}

int pins_unpin_album(const char *album) {
    return album && *album && pn_unpin('a', pn_album_id(album), (const char *)0, 1);
}

int pins_unpin_playlist(int id, const char *name) {
    char nm[PIN_STR];
    if (id < 0 || !name || !*name) return 0;
    pn_copy(nm, sizeof nm, name);
    return pn_unpin('p', (unsigned)id, nm, 1);
}

int pins_rename_playlist(int id, const char *old, const char *name) {
    char nm[PIN_STR];
    pin_t keep;
    int at;
    if (id < 0 || !old || !*old || !name || !*name || pn_load() < 0) return 0;
    at = pn_pl_at(id, old);
    if (at < 0) return 0;
    pn_copy(nm, sizeof nm, name);
    if (!*nm) return 0;
    memcpy(&keep, &pn.ent[at], sizeof keep);
    memcpy(pn.ent[at].name, nm, sizeof nm);
    if (pn_save() == 0) return 1;
    memcpy(&pn.ent[at], &keep, sizeof keep);
    pod_toast(TR("Can't update pins"));
    return 0;
}

/* A song's identity: FNV-1a of its path (case as written: the card's names are), then its CUE start (the tracks of a CUE image share the file: 0, a plain file, leaves the hash as it was), never 0. */
static unsigned pn_song_id(const char *path, unsigned start) {
    unsigned h = m1_fnv(FNV_SEED, path);
    if (start) h = (h ^ start) * 16777619u;
    return h | !h;
}

/* A CUE start as a pin keeps it: the record's REC_CUE_START when it is above 0 and fits 9 digits, else 0. */
static unsigned pn_start(int cue) { return cue > 0 && cue < 1000000000 ? (unsigned)cue : 0; }

/* A path and a CUE start the file can hold: the path absolute, the line's path field (with "<start>@" for a CUE track) under PIN_PATH bytes. */
int pins_song_ok(const char *path, int cue) {
    unsigned extra = 0, v = pn_start(cue);
    for (; v; v /= 10) ++extra;
    if (extra) ++extra; /* the "@" */
    return path && path[0] == '/' && strlen(path) + extra < PIN_PATH;
}

int pins_pin_song(void *rec) {
    pin_t e;
    const char *path, *title, *base;
    unsigned ckey;
    if (!rec) return PINS_FAIL;
    path = cc_str(rec, REC_PATH);
    if (!pins_song_ok(path, I(rec, REC_CUE_START))) return PINS_FAIL;
    title = cc_str(rec, REC_TITLE);
    if (!*title) { /* no title tag: the file's name */
        for (base = path; *base; ++base)
            if (*base == '/' && base[1]) title = base + 1;
    }
    ckey = cc_album_rep_key(cc_str(
        rec,
        REC_ALBUM)); /* the cover of the library album of that name (one targeted query), else the record's own key */
    if (!ckey) ckey = cc_album_key(rec);
    memset(&e, 0, sizeof e);
    e.kind = 's';
    e.start = pn_start(I(rec, REC_CUE_START));
    e.key = pn_song_id(path, e.start);
    e.ck[0] = ckey;
    pn_copy(e.name, sizeof e.name, title);
    pn_copy(e.path, sizeof e.path, path);
    if (!*e.name || !ckey) return PINS_FAIL;
    return pn_pin(&e);
}

int pins_has_song(const char *path, int cue) {
    if (!pins_song_ok(path, cue)) return 0;
    pn_load();
    return pn_at('s', pn_song_id(path, pn_start(cue))) >= 0;
}

int pins_unpin_song(const char *path, int cue) {
    return pins_song_ok(path, cue) && pn_unpin('s', pn_song_id(path, pn_start(cue)), (const char *)0, 1);
}

/* The artist list the Artists page shows now: 1 Album Artists (the stock artist_type switch), 0 Artists. */
static int pn_type(void) { return *(volatile int *)ARTIST_TYPE == 1; }

/* An artist's identity: FNV-1a of the name as the Artists page lists it, ASCII letters folded (as an album's title), never 0; 0 when the name cannot be pinned (blank, no photo key, too long for the file). The cover key is
 * the artist photo's cache key (ap_key). */
static unsigned pn_artist_id(const char *name) {
    return name && *name && ap_key(name) && strlen(name) < PIN_STR ? pn_album_id(name) : 0;
}

int pins_pin_artist(const char *name) {
    pin_t e;
    if (!pn_artist_id(name)) return PINS_FAIL;
    memset(&e, 0, sizeof e);
    e.kind = 'r';
    e.key = pn_artist_id(name);
    e.ck[0] = ap_key(name);
    e.path[0] =
        pn_type() ? '1' : '0'; /* the list it was pinned from: a guest artist is in Artists and not in Album Artists */
    pn_copy(e.name, sizeof e.name, name);
    if (!*e.name) return PINS_FAIL;
    return pn_pin(&e);
}

int pins_has_artist(const char *name) {
    if (!pn_artist_id(name)) return 0;
    pn_load();
    return pn_at('r', pn_artist_id(name)) >= 0;
}

int pins_unpin_artist(const char *name) {
    return pn_artist_id(name) && pn_unpin('r', pn_artist_id(name), (const char *)0, 1);
}

/* ---------------------------------------------------------------------------
 * Tiles (the grid's, patch/grid.c: tile i shows entry i)
 */
static int pn_cells(void) { return pn.n < PIN_MAX ? (int)pn.n : PIN_MAX; }

static int pn_same_ck(const unsigned *a, const unsigned *b) {
    return a[0] == b[0] && a[1] == b[1] && a[2] == b[2] && a[3] == b[3];
}

/* A tile made for pin e: its name, and its cover keys (an album's one key; a playlist's up to four, the mosaic, one only when there is no room for the quadrant buffer). */
static void pn_set(grid_tile_t *t, const pin_t *e) {
    unsigned nk = 0;
    grid_set(t, e->name, "", e->kind != 'p' ? e->ck[0] : 0);
    if (e->kind != 'p') return;
    while (nk < 4 && e->ck[nk]) ++nk;
    t->nq = nk > 1 && !pn.tmp ? 1 : (int)nk;
    t->qi = 0;
    memcpy(t->qkey, e->ck, sizeof t->qkey);
    if (!nk) t->art = 2; /* no album with a cover: the placeholder */
}

/* The tiles for the pins. A tile whose pin (and cover keys) moved to another place keeps its cover and takes the pin's name again; the others are made again; a tile whose cover was only the placeholder
 * tries again when its cache file exists now. */
static void pn_tiles(void) {
    grid_tile_t old[PIN_MAX];
    char okind[PIN_MAX], oph[PIN_MAX];
    unsigned okey[PIN_MAX], ock[PIN_MAX][4], i, j, used = 0;
    char url[80];
    if (!pn.g.tiles) return;
    memcpy(old, pn.g.tiles, sizeof old);
    memcpy(okind, pn.tkind, sizeof okind);
    memcpy(oph, pn.tph, sizeof oph);
    memcpy(okey, pn.tkey, sizeof okey);
    memcpy(ock, pn.tck, sizeof ock);
    memset(pn.g.tiles, 0, sizeof old);
    memset(pn.tkind, 0, sizeof pn.tkind);
    memset(pn.tph, 0, sizeof pn.tph);
    memset(pn.tkey, 0, sizeof pn.tkey);
    memset(pn.tck, 0, sizeof pn.tck);
    for (i = 0; i < PIN_MAX && i < pn.n; ++i) {
        const pin_t *e = &pn.ent[i];
        for (j = 0; j < PIN_MAX; ++j)
            if (!(used >> j & 1) && okey[j] == e->key && okind[j] == e->kind && pn_same_ck(ock[j], e->ck)) {
                used |= 1u << j;
                memcpy(&pn.g.tiles[i], &old[j], sizeof old[j]);
                grid_set(&pn.g.tiles[i], e->name, "",
                         old[j].ckey); /* (a renamed playlist keeps its id and keys: the name is the file's) */
                pn.g.tiles[i].fit = 0;
                pn.tph[i] = oph[j];
                if (e->kind == 'r') {
                    int st = oph[j] ? ap_lookup(e->name, AP_HEAD, url) : AP_NONE;
                    if (st == AP_PHOTO || st == AP_LEAD) { /* the photo exists now */
                        grid_free_art(&pn.g.tiles[i]);
                        pn.g.tiles[i].art = 0, pn.tph[i] = 0;
                    }
                } else if (old[j].art == 2 && e->kind != 'p' && cc_url(url, e->ck[0]))
                    pn.g.tiles[i].art = 0; /* the cover exists now */
                break;
            }
        if (j == PIN_MAX) pn_set(&pn.g.tiles[i], e);
        pn.g.tiles[i].album = (int)i + 1;
        pn.tkind[i] = e->kind;
        pn.tkey[i] = e->key;
        memcpy(pn.tck[i], e->ck, sizeof pn.tck[i]);
    }
    for (j = 0; j < PIN_MAX; ++j)
        if (!(used >> j & 1)) grid_free_art(&old[j]); /* the bitmaps of the tiles that were not kept */
}

static int pn_pin_of(int i, pin_t *out);

/* Tile i of an artist: the -168 photo of its key (or the lead artist's, ap_lookup; the Artists page's cache, nothing is fetched here) decoded to the cell's size, a portrait cut from its top third, as a circle; no photo, or one that
 * does not decode: the Artists page's own circle placeholder (ap_placeholder), tph set so that the tile looks again later. */
static void pn_artist_art(unsigned i) {
    grid_tile_t *t = &pn.g.tiles[i];
    pin_t e;
    char url[80];
    unsigned *px;
    void *b;
    int st;
    t->art = 2;
    if (!pn_pin_of((int)i, &e)) return;
    st = ap_lookup(e.name, AP_HEAD, url);
    if ((st == AP_PHOTO || st == AP_LEAD) && (b = ap_bitmap(PIN_COVER, &px))) {
        int ok = cc_decode(pn.g.win, url, 1, PIN_COVER, 2, px);
        if (ok)
            ap_circle(px, PIN_COVER); /* the circle cut in the alpha, as every pin tile's corners (see pins_start) */
        bitmap_unlock_buffer(b);
        if (ok) {
            t->bmp = b, t->art = 1, pn.tph[i] = 0;
            return;
        }
        bitmap_destroy(b);
    }
    b = ap_placeholder(pn.g.win, PIN_COVER); /* already a circle in the alpha */
    if (!b) return;
    t->bmp = b, t->art = 1, pn.tph[i] = 1;
}

/* The next step of tile i's cover: an album's cache file box-reduced to the tile's size, a playlist's one mosaic source; else the placeholder disc. */
static void pn_make(unsigned i) {
    grid_tile_t *t = &pn.g.tiles[i];
    if (pn.tkind[i] == 'p')
        grid_mosaic(&pn.g, t, pn.tmp);
    else if (pn.tkind[i] == 'r')
        pn_artist_art(i);
    else
        grid_art(&pn.g, t);
    if (t->art != 1 && !pn.g.placeholder)
        grid_placeholder(
            &pn.g); /* one bitmap shared by the tiles without a cover (a mosaic's unfinished tile shows it too) */
    widget_invalidate_force(pn.sec, (void *)0);
}

static int pn_next(void) {
    unsigned i;
    if (!pn.shown || !pn.g.tiles) return -1; /* a section that is not shown needs no covers */
    for (i = 0; i < PIN_MAX; ++i)
        if (pn.g.tiles[i].album && !pn.g.tiles[i].art) return (int)i;
    return -1;
}

/* ---------------------------------------------------------------------------
 * The timer: a one-shot after start, then one step per tick until none is left
 */
static void pn_unarm(void) { m1_timer_stop(&pn.timer); }

static int pn_work(void) {
    int i = pn_next();
    if (i >= 0) pn_make((unsigned)i);
    return pn_next() >= 0;
}

static int pn_dark(const void *timer);

static int pn_tick(const void *timer) {
    (void)timer;
    if (!pn.win || !pn.fg) {
        pn.timer = 0;
        return RET_OK;
    }
    if (!m1_screen_lit()) {
        pn.timer = timer_add(pn_dark, (void *)0, POD_DARK_MS);
        return RET_OK;
    }
    if (!pn_work()) {
        pn.timer = 0;
        return RET_OK;
    } /* nothing left: the timer ends with the return */
    return RET_REPEAT;
}

static int pn_dark(const void *timer) {
    (void)timer;
    pn.timer = 0;
    if (!pn.win || !pn.fg) return RET_OK;
    if (!m1_screen_lit()) {
        pn.timer = timer_add(pn_dark, (void *)0, POD_DARK_MS);
    } else if (pn_next() >= 0) {
        pn.timer = timer_add(pn_tick, (void *)0, PIN_TICK_MS);
        if (pn.timer && !pn_work()) pn_unarm();
    }
    return RET_OK;
}

static int pn_first(const void *timer) {
    (void)timer;
    pn.timer = 0; /* this one ends with the return */
    if (!pn.win || !pn.fg) return RET_OK;
    pn.warm = 1;
    if (pn_next() < 0) return RET_OK;
    if (!m1_screen_lit())
        pn.timer = timer_add(pn_dark, (void *)0, POD_DARK_MS);
    else {
        pn.timer = timer_add(pn_tick, (void *)0, PIN_TICK_MS);
        if (pn.timer && !pn_work()) pn_unarm();
    }
    return RET_OK;
}

/* Arms the timer when a tile waits for its cover and none runs: the one-shot before the first work, then the tick itself. */
static void pn_kick(void) {
    if (pn.timer || !pn.win || !pn.fg || pn_next() < 0) return;
    pn.timer = pn.warm ? timer_add(pn_tick, (void *)0, PIN_TICK_MS) : timer_add(pn_first, (void *)0, PIN_FIRST_MS);
}

/* ---------------------------------------------------------------------------
 * The section as the file says
 */
static void pn_apply(void) {
    int want = pn.n > 0;
    pn_tiles();
    if (want)
        widget_resize(
            pn.sec, PIN_W,
            PIN_H((pn_cells() + PIN_COLS - 1) / PIN_COLS)); /* ceil(pins / 3) rows: set before the rows are arranged */
    if (want || want != pn.shown) menu_pins(pn.win, want);
    pn.shown = want;
    if (want) {
        widget_invalidate_force(pn.sec, (void *)0);
        pn_kick();
    }
}

/* ---------------------------------------------------------------------------
 * Paint: the resident covers and the names. Nothing is decoded here.
 */
/* The first tile's x: one short row (1 or 2 pins) is centred in the section, as Apple Music does; from a full row on, the grid starts at the margin and a partial last row at its left. */
static int pn_x0(void) {
    int n = pn_cells();
    return n < PIN_COLS ? (PIN_W - (n * PIN_COVER + (n - 1) * PIN_GAP)) / 2 : PIN_MARGIN;
}
static int pn_x(int i) { return pn_x0() + i % PIN_COLS * (PIN_COVER + PIN_GAP); }
static int pn_y(int i) { return PIN_TOP + i / PIN_COLS * PIN_PITCH; }

/* The tile shown in slot p: while one is dragged the others close up around the slot it would land in. */
static int pn_tile_in(int p) {
    int k;
    if (!pn.drag) return p;
    if (p == pn.slot) return pn.lift - 1;
    k = p < pn.slot ? p : p - 1; /* the k-th tile that is not the lifted one */
    return k < pn.lift - 1 ? k : k + 1;
}

/* The slot of the cell under section point (x, y), clamped to the tiles there are (a point beside or above the grid is its nearest cell). */
static int pn_slot(int x, int y) {
    int cx = x - pn_x0(), cy = y - PIN_TOP, col, row, rows = (pn_cells() + PIN_COLS - 1) / PIN_COLS, a;
    col = cx < 0 ? 0 : cx / (PIN_COVER + PIN_GAP);
    row = cy < 0 ? 0 : cy / PIN_PITCH;
    if (col >= PIN_COLS) col = PIN_COLS - 1;
    if (row >= rows) row = rows - 1;
    a = row * PIN_COLS + col;
    return a < pn_cells() ? a : pn_cells() - 1;
}

/* The lifted tile's cover PIN_LIFT px larger on each side (the bitmap scaled). */
static void pn_lifted(void *canvas, const grid_tile_t *t, int x, int y) {
    void *bmp = t->art == 1 ? t->bmp : pn.g.placeholder;
    int src[4], dst[4];
    if (!bmp) return;
    src[0] = src[1] = 0, src[2] = src[3] = PIN_COVER;
    dst[0] = x - PIN_LIFT, dst[1] = y - PIN_LIFT, dst[2] = dst[3] = PIN_COVER + 2 * PIN_LIFT;
    canvas_draw_image(canvas, bmp, src, dst);
}

/* The section's own EVT_AFTER_PAINT, in its coordinates. The scroll view clips its children to its own rectangle, so a tile below the list's bottom edge, or behind the mini
 * bar's pill (a later sibling, painted over it), is cut exactly as a row is. */
static int pn_on_paint(void *ctx, void *e) {
    void *canvas = e ? *(void **)((char *)e + EVENT_PAINT_CANVAS) : (void *)0;
    int i, n = pn_cells(), lt = pn.lift - 1, t, lx, ly;
    (void)ctx;
    if (!canvas || !pn.win || !pn.shown || !pn.g.tiles) return RET_OK;
    for (i = 0; i < n; ++i) { /* the lifted tile is drawn last, over the others; a dragged one leaves its slot empty */
        t = pn_tile_in(i);
        if (t != lt) grid_blit(canvas, &pn.g, &pn.g.tiles[t], pn_x(i), pn_y(i), 0);
    }
    widget_prepare_text_style(pn.st_title, canvas);
    for (i = 0; i < n; ++i) {
        t = pn_tile_in(i);
        if (t != lt)
            grid_text(canvas, &pn.g.tiles[t], 0, pn_x(i), pn_y(i) + PIN_COVER + PIN_TGAP, PIN_COVER, PIN_TH, 0);
    }
    if (lt >= 0 && lt < n) {
        lx = pn.drag ? pn.fx - PIN_COVER / 2 : pn_x(lt);
        ly = pn.drag ? pn.fy - PIN_COVER / 2 : pn_y(lt);
        pn_lifted(canvas, &pn.g.tiles[lt], lx, ly);
        grid_text(canvas, &pn.g.tiles[lt], 0, lx, ly + PIN_COVER + PIN_TGAP, PIN_COVER, PIN_TH, 0);
    }
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * The library: finding the pinned item, opening it, playing it
 */
/* The stock row of the album in a stock album list: by the cover key, else the title (ASCII case aside; the "Unknown Album" row never), else the track path. -1 when none. A song's album is
 * first looked for by what its own library record has now (rtitle, "" for none; `untagged`: the record has no album tag, so its album is the "Unknown Album" row, REC_ID -1): the album's representative track
 * and cover key change when the library does, the song's file does not. */
static int pn_find(void *albums, const pin_t *e, const char *rtitle, int untagged) {
    unsigned n = deque_size(albums), i;
    for (i = 0; untagged && i < n; ++i)
        if (*(int *)((char *)deque_at(albums, i) + REC_ID) == -1) return (int)i;
    for (i = 0; *rtitle && i < n; ++i) {
        void *r = deque_at(albums, i);
        if (*(int *)((char *)r + REC_ID) != -1 && !cc_nocase(cc_str(r, REC_ALBUM), rtitle)) return (int)i;
    }
    for (i = 0; i < n; ++i)
        if (cc_album_key(deque_at(albums, i)) == e->ck[0]) return (int)i;
    for (i = 0; e->kind == 'a' && i < n; ++i) { /* (a song's name is its title, not its album's) */
        void *r = deque_at(albums, i);
        if (*(int *)((char *)r + REC_ID) != -1 && !cc_nocase(cc_str(r, REC_ALBUM), e->name)) return (int)i;
    }
    for (i = 0; *e->path && i < n; ++i)
        if (!strcmp(cc_str(deque_at(albums, i), REC_PATH), e->path)) return (int)i;
    return -1;
}

#define PN_TAG 512 /* room for an album tag (the whole tag is compared: a cut one would match nothing) */

/* The album tag the library has for the song now (`select * from songtable where fileurl='<path>'`, the rows of a CUE image told apart by their start: one query as the Folders page's covers
 * make it, *pdeq_showlist untouched), whole, into out (PN_TAG bytes). 1 when the library has the record (out is "" when it has no album tag: the Unknown Album row), 0 when it has none (no row, a failed query, a path that does not
 * fit, a tag longer than out: nothing is told). */
static int pn_song_album(const pin_t *e, char *out) {
    static const char head[] = "select * from songtable where fileurl='";
    char sql[2 * PIN_PATH + sizeof head + 2], *o = sql;
    const char *p;
    void *dq = (void *)0;
    unsigned i, rows, len;
    int found = 0;
    *out = 0;
    memcpy(o, head, sizeof head - 1), o += sizeof head - 1;
    for (p = e->path; *p; ++p) {
        if (*p == '\'') *o++ = '\'';
        *o++ = *p;
    }
    *o++ = '\'';
    *o = 0;
    if (toolsQueryDbTable(STOCK_DB_PATH, sql, STOCK_SONG_ROW, 0) >= 0) dq = *(void **)PDEQ_TOOLS_TMP;
    rows = dq ? deque_size(dq) : 0;
    for (i = 0; i < rows; ++i) {
        void *r = deque_at(dq, i);
        if (strcmp(cc_str(r, REC_PATH), e->path) || pn_start(I(r, REC_CUE_START)) != e->start) continue;
        p = cc_str(r, REC_ALBUM);
        for (len = 0; p[len] && len < PN_TAG; ++len) out[len] = p[len];
        if (len < PN_TAG)
            out[len] = 0, found = 1;
        else
            *out = 0;
        break;
    }
    if (dq) deque_clear(dq);
    return found;
}

/* The playlist's row in the stock list *pdeq_playlist (id and name as pinned), loaded now; -1 when it is not there, -2 when the list could not be told (empty or failed). */
static int pn_pl_find(const pin_t *e) {
    void *list;
    unsigned n, i;
    char name[PIN_STR];
    if (loadLocalClassList(CLASS_PLAYLISTS) <= 0) return -2;
    list = *(void **)PDEQ_PLAYLIST;
    n = list ? deque_size(list) : 0;
    for (i = 0; i < n; ++i) {
        void *r = deque_at(list, i);
        pn_copy(name, sizeof name, cc_str(r, REC_TITLE));
        if (I(r, REC_DISC) == (int)e->key && !strcmp(name, e->name)) return (int)i;
    }
    return n ? -1 : -2;
}

/* The sheet's Unpin: the user asked, so a file that cannot be written says "Can't update pins" and the tile stays. */
static void pn_remove(char kind, unsigned key) {
    pn_unpin(kind, key, (const char *)0, 1);
    if (pn.win && pn.fg) pn_apply();
}

/* Our album page on the album (the Albums grid's own sequence). Not in the list, or no list (empty or failed: not told apart): "Not found", the pin stays (only the user unpins: a library
 * mid-scan lists fewer). */
static void pn_open_album(const pin_t *e) {
    void *albums = cc_albums();
    int row;
    if (!albums) {
        pod_toast(TR("Not found"));
        return;
    }
    row = pn_find(albums, e, "", 0);
    deque_destroy(albums);
    if (row >= 0)
        cc_open_album((void *)0, 0, row);
    else
        pod_toast(TR("Not found"));
}

/* Our Songs page on the playlist, as the Playlists page's tap opens it; the stock page if ours will not open. Not in the list, or no list (empty or failed): "Not found", the pin stays. */
static void pn_open_playlist(const pin_t *e) {
    if (pn_pl_find(e) < 0) {
        pod_toast(TR("Not found"));
        return;
    }
    if (songs_open_playlist((int)e->key, e->name) != -1) return;
    snprintf((char *)NAV_TITLE, 0x200, "%s", e->name);
    *(int *)(CLASSINFO + CLASSINFO_ARG) = (int)e->key;
    navigator_to_with_context("allmusic_page", (const void *)CLASS_PLAYLIST_SONGS);
}

/* The artist's row as the Artists page lists it (artists_find) in the list the pin was made from (0 Artists, 1 Album Artists; an old line has none: the list shown now, then the other), one-row deque to
 * destroy. The stock artist_type is left at the list the row came from (the stock queries that follow, the artist's albums and songs, read it) and *prev is what it was: pn_scope_end puts it back.
 * NULL when no list shows the artist as a row of its own now (gone, Split Artists turned on since, the library mid-scan or unreadable): the caller says so and the pin stays. */
static void *pn_artist_row(const pin_t *e, int *prev) {
    int cur = pn_type(), sc = e->path[0] == '1' ? 1 : e->path[0] == '0' ? 0 : -1, k, t;
    void *one = (void *)0;
    *prev = cur;
    for (k = 0; k < (sc < 0 ? 2 : 1) && !one; ++k) {
        t = sc >= 0 ? sc : k ? !cur : cur;
        if (t != pn_type()) {
            *(volatile int *)ARTIST_TYPE = t;
            *(volatile unsigned char *)ARTIST_RELOAD = 1; /* (as the Show group does: the stock list is built again) */
        }
        one = artists_find(e->name);
        if (one &&
            cc_nocase(
                cc_str(deque_at(one, 0), REC_TITLE),
                e->name)) { /* Split Artists turned on since the pin: artists_find splits the name and answers with its first one ("Lead; Guest" gives Lead's row), not the artist the tile names */
            deque_destroy(one);
            one = (void *)0;
        }
    }
    if (!one && pn_type() != cur) { /* nothing found: back to the list shown */
        *(volatile int *)ARTIST_TYPE = cur;
        *(volatile unsigned char *)ARTIST_RELOAD = 1;
    }
    return one;
}

/* Gives the stock artist_type back after a play (the artist's list is not the user's choice of what the Artists page shows). */
static void pn_scope_end(int prev) {
    if (pn_type() == prev) return;
    *(volatile int *)ARTIST_TYPE = prev;
    *(volatile unsigned char *)ARTIST_RELOAD = 1;
}

/* Our Albums page on the artist, as a tap on the Artists row (Cover Flow if that window will not open). The page reads its albums by the stock artist_type each time it loads, so a pin made in
 * the other list switches the setting to its own, as the Show group does (saved, the Artists page follows). No row: "Not found", the pin stays. */
static void pn_open_artist(const pin_t *e) {
    int prev;
    void *one = pn_artist_row(e, &prev);
    if (!one) {
        pod_toast(TR("Not found"));
        return;
    }
    if (pn_type() != prev) write_int_config(pn_type(), "PLAYSET", "ARTISTTYPE");
    if (albums_open_artist(one, 0, CLASS_ARTISTS) == -1) coverflow_artist(one, 0, CLASS_ARTISTS);
    deque_destroy(one);
}

/* All the artist's songs, in order or shuffled: the scoped Albums page's Play and Shuffle (songs_play_artist), read in the list the pin was made from. No row or no play: "Can't play", the pin stays. */
static void pn_play_artist(const pin_t *e, int how) {
    int prev, r = -1;
    void *one = pn_artist_row(e, &prev);
    if (one) {
        r = songs_play_artist(deque_at(one, 0), CLASS_ARTISTS, how);
        deque_destroy(one);
        pn_scope_end(prev);
    }
    if (r < 0) pod_toast(TR("Can't play"));
}

/* Loads the album's tracks into *PDEQ_SHOWLIST in album order (disc, then track): the stock album list, loadAlbumdetailList on the matched row, loadLocalClassList on the class it leaves.
 * NULL when the album is not in the library or has no tracks. */
static void *pn_album_tracks(const pin_t *e, const char *rtitle, int untagged, int *cls_out) {
    void *list;
    int at, cls;
    loadAlbumList(CLASS_ALBUMS, (void *)0);
    list = *(void **)PDEQ_SHOWLIST;
    at = list ? pn_find(list, e, rtitle, untagged) : -1;
    if (at < 0) return (void *)0;
    loadAlbumdetailList(CLASS_ALBUMS, deque_at(list, (unsigned)at));
    cls = *(int *)CLASSINFO;
    if (loadLocalClassList(cls) <= 0) return (void *)0;
    list = *(void **)PDEQ_SHOWLIST;
    if (!list || !deque_size(list)) return (void *)0;
    if (cls_out) *cls_out = cls;
    return list;
}

/* The whole album as the queue, from the first song (SO_IN_ORDER) or a random one in the stock Shuffle mode (SO_SHUFFLE), then Now Playing: the album page's Play pill and
 * Shuffle disc (patch/albumpage.c ab_play_at) without the page: the stock album list, loadAlbumdetailList on the row, loadLocalClassList on the class it leaves, so_play. */
static int pn_play_album(const pin_t *e, int how) {
    void *list;
    int cls = 0, from = how == SO_SHUFFLE ? -1 : 0;
    unsigned i, n;
    char rtitle[PN_TAG];
    int untagged = 0;
    rtitle[0] = 0;
    if (e->kind == 's') /* (before the album list: the query leaves *pdeq_showlist alone either way) */
        untagged = pn_song_album(e, rtitle) && !*rtitle;
    list = pn_album_tracks(e, rtitle, untagged, &cls);
    if (!list) return -1;
    if (e->kind == 's') { /* a song: the album from that track on, as a tap on the track of the album page */
        n = deque_size(list);
        for (i = 0; i < n && (strcmp(cc_str(deque_at(list, i), REC_PATH), e->path) ||
                              pn_start(I(deque_at(list, i), REC_CUE_START)) != e->start);
             ++i) { /* the path and the CUE start: a CUE image's tracks share the file */
        }
        if (i == n) return -1;
        from = (int)i;
    }
    *(int *)G_CLASS_TYPE = cls;
    so_play(cls, list, from, how, pod_open_player);
    return 0;
}

int pins_play_album(const char *album, unsigned ckey, const char *path, int shuffle) {
    pin_t e;
    if (!album || !*album) return 0;
    memset(&e, 0, sizeof e);
    e.kind = 'a';
    e.ck[0] = ckey;
    pn_copy(e.name, sizeof e.name, album);
    pn_copy(e.path, sizeof e.path, path ? path : "");
    return pn_play_album(&e, shuffle ? SO_SHUFFLE : SO_IN_ORDER);
}

/* Adds every track of the album in order to the playing queue (Play Next: after == 0; Play After: after != 0) via upnext_add and toasts the outcome.
 * When the library has no such album (or no tracks), toasts "Not found" and returns 0. */
static int pn_queue_album(const pin_t *e, int after) {
    void *list = pn_album_tracks(e, "", 0, (int *)0);
    int r;
    if (!list) {
        pod_toast(TR("Not found"));
        return 0;
    }
    r = upnext_add(list, after);
    rowmenu_upnext_toast(r, after);
    return r;
}

int pins_queue_album(const char *album, unsigned ckey, const char *path, int after) {
    pin_t e;
    if (!album || !*album) return 0;
    memset(&e, 0, sizeof e);
    e.kind = 'a';
    e.ck[0] = ckey;
    pn_copy(e.name, sizeof e.name, album);
    pn_copy(e.path, sizeof e.path, path ? path : "");
    return pn_queue_album(&e, after);
}

/* 1 when the card is in and the file is positively not there (ENOENT, ENOTDIR); 0 when it opens, or when it fails for another reason (EIO, a card that is busy: the file may well be there). */
static int pn_missing(const char *path) {
    int fd;
    if (!so_card()) return 0; /* no card in: nothing is told (the files are not gone) */
    fd = open(path, O_RDONLY, 0);
    if (fd >= 0) {
        close(fd);
        return 0;
    }
    return pn_absent();
}

/* A song tile's tap and Play: the album from the pinned track on. A file that is gone (the card is in) says so, one that fails to open for another reason or an album the library cannot find
 * says "Can't play"; the pin stays either way (only the user unpins). */
static void pn_play_song(const pin_t *e) {
    if (so_card() && pn_missing(e->path)) {
        pod_toast(so_missing());
        return;
    }
    if (pn_play_album(e, SO_IN_ORDER) < 0) pod_toast(TR("Can't play"));
}

/* The whole playlist the same way (the Songs page's Play and Shuffle: classinfo[1] the playlist id, loadLocalClassList, so_play). -1 when nothing plays: not in the list, no list (empty or failed),
 * no songs. */
static int pn_play_playlist(const pin_t *e, int how) {
    void *list;
    if (pn_pl_find(e) < 0) return -1;
    *(int *)(CLASSINFO + CLASSINFO_ARG) = (int)e->key;
    if (loadLocalClassList(CLASS_PLAYLIST_SONGS) <= 0) return -1;
    list = *(void **)PDEQ_SHOWLIST;
    if (!list || !deque_size(list)) return -1;
    *(int *)G_CLASS_TYPE = CLASS_PLAYLIST_SONGS;
    so_play(CLASS_PLAYLIST_SONGS, list, how == SO_SHUFFLE ? -1 : 0, how, pod_open_player);
    return 0;
}

/* Once, the first to-foreground after PIN_CHECK_MS: an album pin whose row now has another cover key takes it (as Recently Played re-keys). Nothing is ever dropped here: the library can be
 * mid-scan (Auto Update rebuilds songtable after a card insert or a USB transfer, and a list read then is short) or unreadable, so a pin leaves only by the user's Unpin. */
static void pn_check(void) {
    void *albums = (void *)0;
    pin_t old[PIN_MAX];
    unsigned i, changed = 0;
    if (pn_load() < 0) return; /* an unreadable file is not checked (nor written): the next to-foreground tries again */
    pn.checked = 1;
    for (i = 0; i < pn.n && pn.ent[i].kind != 'a'; ++i) {
    }
    if (i == pn.n || !(albums = cc_albums())) return;
    memcpy(old, pn.ent, sizeof old);
    for (i = 0; i < pn.n; ++i) {
        pin_t *e = &pn.ent[i];
        int at;
        if (e->kind != 'a' || (at = pn_find(albums, e, "", 0)) < 0) continue;
        if (cc_album_key(deque_at(albums, (unsigned)at)) != e->ck[0]) {
            e->ck[0] = cc_album_key(deque_at(albums, (unsigned)at));
            changed = 1;
        }
    }
    deque_destroy(albums);
    if (changed && pn_save() != 0)
        memcpy(pn.ent, old, sizeof old); /* not written: the list is the file's still (the next menu checks again) */
}

/* ---------------------------------------------------------------------------
 * Touch
 */
/* The tile under the section point (x, y), or -1: the cover and the name; the margins, the gaps between tiles and the air are dead, and so is a place with no pin. */
static int pn_tile_at(int x, int y) {
    int cy = y - PIN_TOP, cx = x - pn_x0(), row, col, a;
    if (cy < 0 || cx < 0) return -1;
    row = cy / PIN_PITCH, col = cx / (PIN_COVER + PIN_GAP);
    if (row >= PIN_ROWS || col >= PIN_COLS || cy % PIN_PITCH >= PIN_COVER + PIN_TGAP + PIN_TH ||
        cx % (PIN_COVER + PIN_GAP) >= PIN_COVER)
        return -1;
    a = row * PIN_COLS + col;
    return a < pn_cells() ? a : -1;
}

/* The event's point in section coordinates: the window sits under the 30 px status bar, the list may be scrolled. */
static void pn_pt(void *e, int *pt) {
    pt[0] = *(int *)((char *)e + PE_X), pt[1] = *(int *)((char *)e + PE_Y);
    widget_to_local(pn.sec, pt);
}

static int pn_local(void *e) {
    int pt[2];
    pn_pt(e, pt);
    return pn_tile_at(pt[0], pt[1]);
}

/* The list's vertical sliding off for a lift (on = 0), back to what it was after (on = 1). */
static void pn_scroll(int on) {
    if (!pn.sv) return;
    if (!on) {
        pn.slide = widget_get_prop_int(pn.sv, "yslidable", 1);
        widget_set_prop_int(pn.sv, "yslidable", 0);
    } else
        widget_set_prop_int(pn.sv, "yslidable", pn.slide);
}

/* The list a tile is lifted in, for the list gesture hook (patch/scroll.c): yslidable off at the hold does not last, the sheet showing or hiding lays the window out again and stock's list_view
 * layouter turns it back on each time (scroll_view_set_yslidable(sv, 1), 0x60b1e4), so the hook turns it off again before every pointer event of the lift reaches the list. */
void *pins_lift_sv __attribute__((section(".scratch")));

/* The lift is over (release, abort, window away): the touch is let go, the list slides again. */
static void pn_lift_end(int repaint) {
    if (!pn.lift) return;
    pn.lift = pn.drag = 0;
    pins_lift_sv = (void *)0;
    widget_ungrab(pn.sv ? pn.sv : pn.win, pn.sec);
    pn_scroll(1);
    if (repaint) widget_invalidate_force(pn.sec, (void *)0);
}

/* The pin tile i was made for, copied (the file may have been read again since). 0 when it is not there any more. */
static int pn_pin_of(int i, pin_t *out) {
    int at;
    if (i < 0 || i >= PIN_MAX) return 0;
    at = pn_at(pn.tkind[i], pn.tkey[i]);
    if (at < 0) return 0;
    memcpy(out, &pn.ent[at], sizeof *out);
    return 1;
}

static void pn_open(int i) {
    pin_t e;
    if (!pn_pin_of(i, &e)) return;
    if (e.kind == 'a')
        pn_open_album(&e);
    else if (e.kind == 's')
        pn_play_song(&e);
    else if (e.kind == 'r')
        pn_open_artist(&e);
    else
        pn_open_playlist(&e);
}

/* A row of the long press sheet (the sheet has closed): Play, Shuffle, (Play Next, Play After for an album), Unpin for the tile it was opened on. */
static void pn_sheet(int tile, int act) {
    pin_t e;
    int r = 0;
    if (!pn_pin_of(tile, &e)) return;
    if (e.kind == 's') { /* a song's sheet has two rows: Play, Unpin Song (the second row is the Shuffle slot) */
        if (act == RMP_PLAY)
            pn_play_song(&e);
        else
            pn_remove(e.kind, e.key);
        return;
    }
    if (e.kind == 'a') { /* an album's sheet has five rows: Play, Shuffle, Play Next, Play After, Unpin Album */
        if (act == RMA_PIN)
            pn_remove(e.kind, e.key);
        else if (act == RMA_NEXT || act == RMA_AFTER)
            pn_queue_album(&e, act == RMA_AFTER);
        else if (pn_play_album(&e, act == RMA_SHUFFLE ? SO_SHUFFLE : SO_IN_ORDER) < 0)
            pod_toast(TR("Can't play")); /* not in the library now (or it could not be read): the pin stays */
        return;
    }
    if (act == RMP_UNPIN) {
        pn_remove(e.kind, e.key);
        return;
    }
    if (e.kind == 'r') {
        pn_play_artist(&e, act == RMP_SHUFFLE ? SO_SHUFFLE : SO_IN_ORDER);
        return;
    }
    r = pn_play_playlist(&e, act == RMP_SHUFFLE ? SO_SHUFFLE : SO_IN_ORDER);
    if (r < 0) pod_toast(TR("Can't play")); /* not in the library now (or it could not be read): the pin stays */
}

/* A row of the sheet opened for a Recently Played tile (the sheet has closed): Play, Shuffle, Play Next, Play After, Pin Album / Unpin Album. Home stays in front, so no to-foreground redoes the section: the pin
 * and the unpin redo it here. */
static void pn_xsheet(int row, int act) {
    (void)row;
    if (act == RMA_PIN) {
        if (pins_has_album(pn.xname))
            pins_unpin_album(pn.xname);
        else
            pins_pin_album(pn.xname, pn.xckey, pn.xpath);
        if (pn.win && pn.fg) pn_apply();
    } else if (act == RMA_NEXT || act == RMA_AFTER)
        pins_queue_album(pn.xname, pn.xckey, pn.xpath, act == RMA_AFTER);
    else if (pins_play_album(pn.xname, pn.xckey, pn.xpath, act == RMA_SHUFFLE) < 0)
        pod_toast(TR("Can't play"));
}

/* Sets the album sheet's five rows (Play, Shuffle, Play Next, Play After, Pin / Unpin Album) and opens it. */
static void pn_album_rows(int pinned) {
    if (pn.lab_shuf) widget_set_tr_text(pn.lab_shuf, "Shuffle");
    if (pn.ic_shuf) widget_set_prop_str(pn.ic_shuf, "image", "rm_ic_pshuffle");
    if (pn.lab_row2) widget_set_tr_text(pn.lab_row2, "Play Next");
    if (pn.ic_row2) widget_set_prop_str(pn.ic_row2, "image", "rm_ic_next");
    if (pn.lab_pin) widget_set_tr_text(pn.lab_pin, pinned ? "Unpin Album" : "Pin Album");
    if (pn.ic_pin) widget_set_prop_str(pn.ic_pin, "image", pinned ? "rm_ic_unpin" : "rm_ic_pin");
    m1_show(pn.rm.item[2], 1);
    m1_show(pn.rm.item[3], 1);
    m1_show(pn.rm.item[4], 1);
    rowmenu_set_rows(&pn.rm, RM_ALBUM_ROWS);
}

int pins_album_sheet(const char *album, unsigned ckey, const char *path) {
    if (!pn.win || !pn.fg || !pn.rm.on || pn.rm.open || !album || !*album || !path || strlen(album) >= PIN_STR ||
        strlen(path) >= PIN_PATH)
        return 0;
    memcpy(pn.xname, album, strlen(album) + 1), memcpy(pn.xpath, path, strlen(path) + 1), pn.xckey = ckey;
    pn_album_rows(pins_has_album(album));
    return rowmenu_open_queue(&pn.rm, 0, pn_xsheet);
}

/* The sheet for tile `row`: a press held and released where it was. */
static void pn_open_sheet(int row) {
    int k;
    if (!pn.win || !pn.shown || !pn.fg || row < 0 || row >= PIN_MAX) return;
    k = pn.tkind[row];
    /* the sheet follows the tile's type: an album has five rows (Play, Shuffle, Play Next, Play After, Unpin Album), a playlist or artist three (Play, Shuffle, Unpin), a song two (Play, Unpin Song) */
    if (k == 's') {
        if (pn.lab_shuf) widget_set_tr_text(pn.lab_shuf, "Unpin Song");
        if (pn.ic_shuf) widget_set_prop_str(pn.ic_shuf, "image", "rm_ic_unpin");
        m1_show(pn.rm.item[2], 0);
        m1_show(pn.rm.item[3], 0);
        m1_show(pn.rm.item[4], 0);
        rowmenu_set_rows(&pn.rm, 2);
    } else if (k == 'a') {
        pn_album_rows(1);
    } else {
        if (pn.lab_shuf) widget_set_tr_text(pn.lab_shuf, "Shuffle");
        if (pn.ic_shuf) widget_set_prop_str(pn.ic_shuf, "image", "rm_ic_pshuffle");
        if (pn.lab_row2) widget_set_tr_text(pn.lab_row2, k == 'p' ? "Unpin Playlist" : "Unpin Artist");
        if (pn.ic_row2) widget_set_prop_str(pn.ic_row2, "image", "rm_ic_unpin");
        m1_show(pn.rm.item[2], 1);
        m1_show(pn.rm.item[3], 0);
        m1_show(pn.rm.item[4], 0);
        rowmenu_set_rows(&pn.rm, RM_QUEUE_ROWS);
    }
    rowmenu_open_queue(&pn.rm, row, pn_sheet);
}

/* The press has been held RM_LONG_MS: the sheet opens at once, the tile lifts (drawn larger) and takes the touch (widget_grab on the list); the list stops sliding (pn_scroll, and pins_lift_sv keeps it so). A drag
 * of SC_DRAG_PX closes the sheet and reorders; a release where it was leaves the sheet open. Without the list's scroll_view there is no lift: the sheet opens at once. */
static void pn_on_hold(int row) {
    pn.down = 0;
    if (!pn.win || !pn.shown || !pn.fg || row < 0 || row >= pn_cells()) return;
    if (!pn.sv || pn.lift) {
        pn_open_sheet(row);
        return;
    }
    pn.lift = row + 1, pn.drag = 0, pn.slot = row;
    pins_lift_sv = pn.sv;
    pn.fx = pn_x(row) + PIN_COVER / 2, pn.fy = pn_y(row) + PIN_COVER / 2;
    widget_grab(
        pn.sv,
        pn.sec); /* (stock refuses it when the list already has another grab: the touch then goes where it goes, the sliding is off all the same) */
    pn_scroll(0);
    pn_open_sheet(row); /* at once, as on the Albums page; a drag closes it again (pn_follow) */
    widget_invalidate_force(pn.sec, (void *)0);
}

/* The new order on release: tile `from` to slot `to`, saved; a failed save puts the old order back. */
static void pn_commit(int from, int to) {
    pin_t old[PIN_MAX], tmp;
    int at;
    unsigned k;
    pn_load(); /* the file as it is: the lifted tile by its pin */
    at = pn_at(pn.tkind[from], pn.tkey[from]);
    if (at >= 0 && to >= (int)pn.n) to = (int)pn.n - 1;
    if (at >= 0 && to != at) {
        memcpy(old, pn.ent, sizeof old);
        memcpy(&tmp, &pn.ent[at], sizeof tmp);
        if (to > at)
            for (k = (unsigned)at; k < (unsigned)to; ++k) memcpy(&pn.ent[k], &pn.ent[k + 1], sizeof tmp);
        else
            for (k = (unsigned)at; k > (unsigned)to; --k) memcpy(&pn.ent[k], &pn.ent[k - 1], sizeof tmp);
        memcpy(&pn.ent[to], &tmp, sizeof tmp);
        if (pn_save() != 0) memcpy(pn.ent, old, sizeof old); /* not written: the old order stays */
    }
    pn_apply();
}

/* A move while lifted: past SC_DRAG_PX the tile follows the finger and the others close up around the slot under it. */
static void pn_follow(void *e) {
    int pt[2];
    pn_pt(e, pt);
    pn.fx = pt[0], pn.fy = pt[1];
    if (!pn.drag && m1_tap_near(&pn.tap, e)) return;
    if (!pn.drag) rowmenu_close(&pn.rm); /* the drag takes over from the sheet */
    pn.drag = 1;
    pn.slot = pn_slot(pt[0], pt[1]);
    widget_invalidate_force(pn.sec, (void *)0);
}

/* The release of a lift: not moved, the sheet (open since the hold) stays; dragged, the sheet closes and the new order is saved (a release outside the section cancels). A release SC_DRAG_PX or more from
 * the press is a drag even when no move event said so. */
static void pn_drop_lift(void *e) {
    int row = pn.lift - 1, drag = pn.drag, pt[2], in = 0;
    if (e && !m1_tap_near(&pn.tap, e)) drag = 1;
    if (e) {
        pn_pt(e, pt);
        in = pt[0] >= 0 && pt[0] < PIN_W && pt[1] >= 0 && pt[1] < PIN_H((pn_cells() + PIN_COLS - 1) / PIN_COLS);
    }
    pn_lift_end(1);
    if (!drag) return;
    rowmenu_close(&pn.rm);
    if (in && pn.win && pn.shown) pn_commit(row, pn_slot(pt[0], pt[1]));
}

static int pn_on_down(void *ctx, void *e) {
    int a;
    (void)ctx;
    pn.down = 0;
    if (!e || !pn.win) return RET_OK;
    a = pn_local(e);
    pn.down = a + 1;
    m1_tap_at(&pn.tap, e);
    if (a >= 0) rowmenu_hold_start(a, pn_on_hold);
    return RET_OK;
}

static int pn_on_move(void *ctx, void *e) {
    (void)ctx;
    if (pn.lift && e)
        pn_follow(e);
    else if (pn.down && e)
        rowmenu_hold_move(&pn.tap, e);
    return RET_OK;
}

static int pn_on_up(void *ctx, void *e) {
    int a = pn.down - 1;
    (void)ctx;
    rowmenu_hold_stop();
    pn.down = 0;
    if (pn.lift) {
        pn_drop_lift(e);
        return RET_OK;
    }
    if (a < 0 || !e || !pn.win || !pn.shown) return RET_OK;
    if (m1_tap_near(&pn.tap, e) && pn_local(e) == a) pn_open(a);
    return RET_OK;
}

static int pn_on_abort(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    rowmenu_hold_stop();
    pn.down = 0;
    if (pn.lift) rowmenu_close(&pn.rm); /* a cancelled hold takes its sheet with it */
    pn_lift_end(1); /* the order as it was, nothing saved */
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * The window's events
 */
static void pn_stop(void) {
    if (pn.win) pn_lift_end(0);
    pn_unarm();
    rowmenu_free(&pn.rm);
    grid_free(&pn.g);
    free(pn.tmp);
    memset(&pn, 0, sizeof pn);
}

static int pn_on_destroy(void *ctx, void *e) {
    (void)e;
    if (ctx == pn.win) pn_stop(); /* an earlier window's end leaves the new one alone */
    return RET_OK;
}

static int pn_on_background(void *ctx, void *e) {
    (void)e;
    if (!pn.win || ctx != pn.win) return RET_OK;
    pn.fg = 0;
    pn.down = 0;
    pn_lift_end(0);
    pn_unarm();
    rowmenu_close(&pn.rm);
    return RET_OK;
}

/* The menu is in front again: the file is read again and only the tiles whose pin changed are redone. */
static int pn_on_foreground(void *ctx, void *e) {
    (void)e;
    if (!pn.win || ctx != pn.win) return RET_OK;
    pn.fg = 1;
    if (!pn.checked && pn.n && (unsigned)time_now_ms() - pn.t0 >= PIN_CHECK_MS)
        pn_check(); /* once, never in the boot window */
    else
        pn_load();
    pn_apply();
    return RET_OK;
}

/* The Home instance of the menu is up (patch/home.c, after the list took the whole window). */
void pins_start(void *win) {
    if (!win) return;
    if (pn.win) pn_stop(); /* an earlier window that never said it was gone */
    pn.win = win;
    pn.sec = widget_lookup(win, "pod_pins", 1);
    pn.st_title = widget_lookup(win, "pod_pin_title", 1);
    pn.sv = widget_lookup(win, "pod_scrollview", 1); /* (none: no reorder, the hold opens the sheet) */
    pn.fg = 1;
    if (!pn.sec || !pn.st_title || !widget_on(win, EVT_DESTROY, pn_on_destroy, win) ||
        !widget_on(win, EVT_WINDOW_TO_BG, pn_on_background, win) ||
        !widget_on(win, EVT_WINDOW_TO_FG, pn_on_foreground, win) ||
        !widget_on(pn.sec, EVT_AFTER_PAINT, pn_on_paint, (void *)0) ||
        !widget_on(pn.sec, EVT_POINTER_DOWN, pn_on_down, (void *)0) ||
        !widget_on(pn.sec, EVT_POINTER_MOVE, pn_on_move, (void *)0) ||
        !widget_on(pn.sec, EVT_POINTER_UP, pn_on_up, (void *)0) ||
        !widget_on(pn.sec, EVT_POINTER_ABORT, pn_on_abort, (void *)0)) {
        pn_stop(); /* a handler that was registered finds no window of ours any more */
        return;
    }
    pn.timer = timer_add(pn_first, (void *)0, PIN_FIRST_MS);
    if (!pn.timer) {
        pn_stop();
        return;
    }
    pn.t0 = (unsigned)time_now_ms();
    if (!grid_init(&pn.g, win, PIN_MAX, PIN_COVER,
                   PIN_R)) { /* the grid's cells at the pins' size, the corners rounded (PIN_R px) */
        pn_stop();
        return;
    }
    grid_shape(
        &pn.g, PIN_COVER, PIN_R,
        1); /* the corners cut in the alpha, not blended into black: a lifted tile is drawn over its neighbours, and black corners (an artist's black square) would show there */
    pn.g.st_title = pn.st_title, pn.g.st_sub = pn.st_title;
    pn.tmp = (unsigned *)calloc((PIN_COVER / 2) * (PIN_COVER / 2),
                                sizeof(unsigned)); /* (none: a mosaic is its first cover alone) */
    pn.lab_row2 = widget_lookup(win, "rm_label2", 1);
    pn.ic_row2 = widget_lookup(win, "rm_icon2", 1);
    pn.lab_pin = widget_lookup(win, "rm_label4", 1);
    pn.ic_pin = widget_lookup(win, "rm_icon4", 1);
    pn.lab_shuf = widget_lookup(win, "rm_label1", 1);
    pn.ic_shuf = widget_lookup(win, "rm_icon1", 1);
    rowmenu_bind_album(&pn.rm, win); /* the long press sheet (an asset without it: no long press, a tap still opens) */
    pn_load();
    pn_apply(); /* the section is up (with its names) from the first paint; the covers come with the ticks */
}
