/* M1+ Music Folders: the card's folders and audio files, our own page in place of the stock folder_page (docs/modules/folders.md has the design).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * One window for every level, ui/m1plus_folders.bin (tools/pod_ui.py build_folders_page): the Songs page's structure (patch/songs.c): the glass navbar (Back, the small title,
 * Select | Now Playing) over a stock list, list_view > scroll_view, whose ONE child, view_grid, holds the large title and the Play / Shuffle pills and paints the rows itself in
 * its EVT_AFTER_PAINT (an icon, the name, the chevron of a folder or the wave of what plays, the press fill, the hairline, the select marks), with no widget per row.
 *
 *   state     the stock page's own, untouched: the layer (0xa0554c), the path, the title (0xa0533c), the stack of scroll offsets, and the shown list, *pdeq_showlist, whose records
 *             are stSongInfo (+8 name, +0xc url, +0x34 type 2 SD / 3 OTG / 4 folder / 1 playlist file / 8 audio file). The page only calls the stock functions on it: folder_enter(record,
 *             offset) goes into a record (or reports an audio file, a missing card, ...), folder_back(&offset) one level up (0: the root is left, the state is cleared and the window
 *             closes), folder_reload() the level again. Records whose name starts with '.' are not shown (the library scan skips such folders too).
 *   levels    one window swaps its list: Back pops a level through the stock stack (the offset the list was left at comes back), at the root it closes the window. Now Playing and
 *             the dialogs open over it as over any page; when it comes to the front the list is read again only if another query replaced it.
 *   play      a file's tap is the stock row's: loadSongList(queue, name, cue, class 1) on the folder's files, then Now Playing at the file (patch/songops.c so_play, a simple
 *             navigator_to_with_context as stock's folder row does, no songerinfoflag pop). Play and Shuffle (shown while the folder holds an audio file) play its first / a random file
 *             with the in-order / Shuffle mode. The wave marks the folder or file that plays (is_folderplaying, is_playing as the stock row asks them).
 *   select    the page's own multi-select on folders and audio files (a folder's tap in select mode marks it; not at the root, where Select is hidden): marks in a bitset by record, "N Selected", Select All, the bar. Delete and
 *             Add to Playlist run the stock code on the stock selection vector, which is filled from the bitset at that moment (patch/songops.c so_selection): Delete is the stock folder
 *             handler's sequence (@0x5324d0: the confirm dialog, "can't be removed" while a playlist file is open, batch_delete_file(1, list, vector, 0, 1)), Add the stock playlist
 *             picker (so_add, class 1; the stock handler's Favourites question is not asked).
 * No hook; everything runs from the page's widgets and timers.
 */
#include "offsets.inc"
#include "stock.h"
#include "home.h"
#include "scroll.h"
#include "covercache.h"
#include "common.h"
#include "grid.h"
#include "azlist.h"
#include "i18n.h"
#include "songops.h"

extern int pod_home_open(int id); /* patch/m1plus.c: a stock Home destination through the dispatcher */
extern void pod_toast(const char *text); /* patch/shuffle.c: the stock message box */
extern unsigned pod_rand(unsigned n); /* patch/shuffle.c: 0 .. n - 1 */

#define ROW POD_ROW_H /* the menu rows' pitch (52): one line a row */
#define FO_ASSET "m1plus_folders"
#define FO_CLASS 1 /* the stock folder page's class (loadSongList, batch_delete_file, the picker) */
#define FO_W 320 /* the content's width: the list_view's (the scroll_view clips at 310) */
#define FO_TOP_PLAIN 60 /* the first row when there are no pills: under the large title (SG_PILL_Y 52 + 8) */
#define FO_END 24 /* the air under the last row */
/* The menu rows' numbers (tools/mod_icons.py POD_ICON 24, POD_ICON_X 16, POD_TEXT_X 56): a 24 px bare white Lucide glyph at x 16, the text at x 56, the hairline from there. The names are cut at
 * FO_TEXT_END: the wave (24 px, x 262) and the chevron (the shared list chevron, x 288) follow. */
#define FO_ICON 24
#define FO_ICON_X 16
#define FO_ICON_Y ((ROW - FO_ICON) / 2)
#define FO_TEXT_X 56
#define FO_TEXT_END 256
#define FO_MARK_X 262
#define FO_CHEV_X LIST_CHEV_X /* 288: the shared list chevron */
#define FO_TEXT_Y ((ROW - LIST_TITLE_H) / 2) /* the name centred in the row */
#define FO_NAME_MAX 160 /* bytes of a name kept (the tile keeps 47 characters anyway) */
#define FO_PLAYING_MAX 32 /* rows in view are at most GRID_VIEW_H / ROW + 2 */

/* The glyphs are the menu rows' images (pod_ic_folders, pod_ic_playlists, pod_ic_cdripper, pod_ic_nowplaying: the wave) and three of ours (tools/mod_icons.py FOLDER_ROWS) */
enum { FO_I_FOLDER, FO_I_SD, FO_I_USB, FO_I_CD, FO_I_LIST, FO_I_FILE, FO_I_WAVE, FO_ICONS };
static const char *const FO_ICON_NAME[FO_ICONS] = {"pod_ic_folders",   "fo_ic_sd",         "fo_ic_usb",
                                                   "pod_ic_cdripper",  "pod_ic_playlists", "fo_ic_file",
                                                   "pod_ic_nowplaying"};

enum { T_LIST = 1, T_SD = 2, T_OTG = 3, T_DIR = 4, T_FILE = 8 }; /* a record's type (+0x34) */

#define B(w, off) (*(unsigned char *)((char *)(w) + (off)))
#define I(w, off) (*(int *)((char *)(w) + (off)))
#define P(w, off) (*(void **)((char *)(w) + (off)))

static struct {
    void *win, *view, *sv, *status, *title, *big, *fade, *back, *np;
    void *btn_select, *btn_selall, *btn_play, *btn_shuffle, *btn_add, *btn_del, *bar;
    void *st_title; /* hidden labels whose styles are the row's text styles */
    void *list; /* the stock list the index is of (*pdeq_showlist when valid) */
    void *first; /* its first record: with the size, tells a list another query replaced */
    unsigned count; /* its records */
    int *vis; /* the records shown, in order: the stock list without the dot names */
    unsigned nvis;
    int nfile; /* audio files among them */
    int nmark; /* the rows select mode can mark: folders and audio files */
    int first_file; /* the record of the first one, -1 for none */
    unsigned char *sel; /* the select mode's bitset, by record: (count + 7) / 8 bytes */
    unsigned nsel;
    int select; /* select mode */
    int press; /* the row under the finger, + 1 */
    int down, down_x, down_y; /* the row a press began on, + 1, and where */
    int title_on; /* the small title is shown */
    int noscroll; /* the scroll events could not be bound: the navbar keeps its title */
    int picker; /* the stock playlist picker is open over this page */
    unsigned stale_timer;
    char title_save[0x200]; /* nagvation_title across the picker */
    void *mark[2]; /* the select marks: unselect, selected */
    void *chev; /* the chevron */
    void *ic[FO_ICONS]; /* the glyphs, FO_ICON px */
    grid_t g; /* the rows' texts: the ring (a tile holds a name cut to its width and the extension; no cover) */
} fo __attribute__((section(".scratch")));

static int fo_on_stale(const void *unused);
static void fo_cap(void);
static void fo_select(int on);

static void fo_show(void *w, int on) {
    if (!w) return;
    widget_set_visible(w, on, 0);
    widget_set_sensitive(w, on);
}

static int fo_abs(int v) { return v < 0 ? -v : v; }
static int fo_off(void) { return fo.sv ? I(fo.sv, SC_YOFF) : 0; }
static void fo_redraw(void) { widget_invalidate_force(fo.sv, (void *)0); }

/* The index is of the stock list as long as that list is still in *pdeq_showlist, as big, and starts with the same record. */
static int fo_valid(void) {
    void *cur = *(void **)PDEQ_SHOWLIST;
    return fo.list && cur == fo.list && deque_size(cur) == fo.count && (!fo.count || deque_at(cur, 0) == fo.first);
}

static int fo_type(int rec) { return I(deque_at(fo.list, (unsigned)rec), REC_TYPE); }
static int fo_markable(int type) { return type == T_FILE || type == T_DIR; }
static int fo_root(void) { return *(int *)FOLDER_LAYER <= 1; } /* the list of storages: nothing to select there */

/* ---------------------------------------------------------------------------
 * Geometry: the large title (and the pills when the folder holds an audio file), then one ROW per shown record
 */
static int fo_top(void) { return fo.nfile ? SG_TOP : FO_TOP_PLAIN; }
static int fo_row_y(int r) { return fo_top() + r * ROW; }
static int fo_pad(void) {
    return fo.select ? SG_BAR_H : 0;
} /* the bar covers the window's last SG_BAR_H rows: the list scrolls clear of it */
static int fo_content(void) { return fo_top() + (int)fo.nvis * ROW + FO_END + fo_pad(); }

static int fo_max_scroll(void) {
    int m = fo_content() - GRID_VIEW_H;
    return m > 0 ? m : 0;
}

/* The row under content point y, -1 for the title block and the air below the last row. */
static int fo_at(int y) {
    int r = (y - fo_top()) / ROW;
    return y < fo_top() || r >= (int)fo.nvis ? -1 : r;
}

/* The rows [*r0, *r1] that touch the view (r1 < r0 for none). */
static void fo_span(int *r0, int *r1) {
    int s = fo_off(), n = (int)fo.nvis;
    *r0 = s <= fo_top() ? 0 : (s - fo_top()) / ROW;
    *r1 = s + GRID_VIEW_H - 1 < fo_top() ? -1 : (s + GRID_VIEW_H - 1 - fo_top()) / ROW;
    if (*r1 > n - 1) *r1 = n - 1;
}

/* The select mode moves the row's content right by one column. */
static int fo_shift(void) { return fo.select ? SG_SEL_COL : 0; }
static int fo_tx(void) { return FO_TEXT_X + fo_shift(); }

static int fo_is_sel(int rec) { return fo.sel && (fo.sel[rec >> 3] >> (rec & 7) & 1); }

/* ---------------------------------------------------------------------------
 * The tiles: the name (a file's without its extension) and a file's extension in capitals, from the stock record
 */
static void fo_prep(grid_tile_t *t, int rec_i) {
    void *rec = deque_at(fo.list, (unsigned)rec_i);
    const char *name = cc_str(rec, REC_NAME);
    char title[FO_NAME_MAX];
    unsigned n = 0;
    while (name[n] && n < sizeof title - 1) title[n] = name[n], ++n;
    if (name[n]) /* a name cut short is cut before a character, not inside one */
        while (n > 0 && ((unsigned char)name[n] & 0xc0) == 0x80) --n;
    title[n] = 0;
    grid_set(t, title, "", 0);
}

static grid_tile_t *fo_tile(int r) {
    int r0, r1, fresh;
    grid_tile_t *t;
    fo_span(&r0, &r1);
    t = grid_tile(&fo.g, r, r0 - 2, r1 + 2, &fresh);
    if (fresh) fo_prep(t, fo.vis[r]);
    return t;
}

/* The names are cut to a width that the select mode changes: every tile's texts are made again from the record. */
static void fo_retext(void) {
    int i;
    for (i = 0; fo.g.tiles && fo.list && i < fo.g.n; ++i) {
        grid_tile_t *t = &fo.g.tiles[i];
        if (t->album && t->album - 1 < (int)fo.nvis) fo_prep(t, fo.vis[t->album - 1]), t->fit = 0;
    }
}

/* ---------------------------------------------------------------------------
 * Paint: the rows in one EVT_AFTER_PAINT of the content view. Coordinates are the window's (its top is 0): the scroll_view has moved the canvas up by yoffset, which the paint
 * adds back (CANVAS_OY) for its duration, as the Songs page does. A bitmap is cut to the view by hand.
 */
static void fo_blit(void *canvas, void *bmp, int w, int h, int x, int y) {
    int top = y < 0 ? -y : 0, bottom = y + h > GRID_VIEW_H ? GRID_VIEW_H - y : h;
    int src[4], dst[4];
    if (!bmp || bottom <= top) return;
    src[0] = 0, src[1] = top, src[2] = w, src[3] = bottom - top;
    dst[0] = x, dst[1] = y + top, dst[2] = w, dst[3] = bottom - top;
    canvas_draw_image(canvas, bmp, src, dst);
}

/* The record's glyph: the storage's (the CD Library, the Ripper folder of the card, has its disc), the folder's, the playlist file's or the audio file's. */
static void *fo_glyph(int rec_i) {
    void *rec = deque_at(fo.list, (unsigned)rec_i);
    int type = I(rec, REC_TYPE), i;
    static const char ripper[] = "/mnt/mmc/Ripper";
    const char *url = cc_str(rec, REC_PATH);
    if (type == T_SD) {
        for (i = 0; ripper[i] && url[i] == ripper[i]; ++i) {
        }
        return fo.ic[ripper[i] || url[i] ? FO_I_SD : FO_I_CD];
    }
    return fo.ic[type == T_OTG ? FO_I_USB : type == T_DIR ? FO_I_FOLDER : type == T_LIST ? FO_I_LIST : FO_I_FILE];
}

/* Whether the record plays: an audio file by the stock row's question (class 1, its cue start, name and url), a folder by is_folderplaying(url). */
static int fo_playing(int rec_i) {
    void *rec = deque_at(fo.list, (unsigned)rec_i);
    int type = I(rec, REC_TYPE);
    if (type == T_FILE)
        return is_playing(FO_CLASS, I(rec, REC_CUE_START), (const char *)P(rec, REC_NAME),
                          (const char *)P(rec, REC_PATH));
    if (type == T_SD || type == T_OTG || type == T_DIR) return is_folderplaying((const char *)P(rec, REC_PATH));
    return 0;
}

static void fo_paint_rows(void *canvas) {
    int r0, r1, r, off = fo_off(), tx = fo_tx(), room = FO_TEXT_END - tx;
    unsigned playing = 0; /* bit r - r0 */
    fo_span(&r0, &r1);
    if (r1 - r0 >= FO_PLAYING_MAX) r1 = r0 + FO_PLAYING_MAX - 1;
    for (r = r0; r <= r1; ++r) {
        int rec = fo.vis[r], type = fo_type(rec), y = fo_row_y(r) - off;
        if (fo_playing(rec)) playing |= 1u << (r - r0);
        if (fo.press == r + 1 && !fo.select) az_fill(canvas, 0, y, y + ROW - 1, FO_W, LIST_PRESS);
        if (fo.select && fo.mark[0] && fo_markable(type)) {
            void *m = fo.mark[fo_is_sel(rec)];
            int src[4], dst[4], top = y + (ROW - SG_MARK) / 2;
            if (top >= 0 && top + SG_MARK <= GRID_VIEW_H) {
                src[0] = 0, src[1] = 0, src[2] = SG_MARK, src[3] = SG_MARK;
                dst[0] = (SG_SEL_COL - SG_MARK) / 2, dst[1] = top, dst[2] = SG_MARK, dst[3] = SG_MARK;
                canvas_draw_image(canvas, m, src, dst);
            }
        }
        fo_blit(canvas, fo_glyph(rec), FO_ICON, FO_ICON, FO_ICON_X + fo_shift(), y + FO_ICON_Y);
        if ((playing >> (r - r0)) & 1) fo_blit(canvas, fo.ic[FO_I_WAVE], FO_ICON, FO_ICON, FO_MARK_X, y + FO_ICON_Y);
        if (type != T_FILE) fo_blit(canvas, fo.chev, POD_CHEV_W, POD_CHEV_H, FO_CHEV_X, y + (ROW - 1 - POD_CHEV_H) / 2);
        az_fill(canvas, tx, y + ROW - 1, y + ROW, FO_W - 10 - tx, LIST_HAIR);
    }
    widget_prepare_text_style(fo.st_title, canvas);
    for (r = r0; r <= r1; ++r)
        grid_text(canvas, fo_tile(r), 0, tx, fo_row_y(r) - off + FO_TEXT_Y, room, LIST_TITLE_H, 0);
}

static int fo_on_paint(void *ctx, void *e) {
    void *canvas = e ? *(void **)((char *)e + EVENT_PAINT_CANVAS) : (void *)0;
    int off = fo_off();
    (void)ctx;
    if (!canvas || !fo.view || !fo.g.tiles || !fo.nvis) return RET_OK;
    if (!fo_valid()) { /* another query replaced the stock list: nothing of it is read; the page reads it again when it is on top */
        if (!fo.stale_timer) fo.stale_timer = timer_add(fo_on_stale, (void *)0, 100);
        return RET_OK;
    }
    I(canvas, CANVAS_OY) += off;
    fo_paint_rows(canvas);
    I(canvas, CANVAS_OY) -= off;
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * The titles: the large one in the content, the small one in the navbar once the large one has scrolled away (and in an empty folder, where nothing scrolls)
 */
static const char *fo_text(void) {
    return fo_root() ? TR("Folders") : (const char *)FOLDER_TITLE;
} /* the root list says "Folders" (the stock title is the singular), a folder its name */

static void fo_title_update(void) {
    pod_title_set(fo.title, &fo.title_on, fo.noscroll || fo.select || !fo.nvis || pod_title_gone(fo_off(), 0));
    /* The navbar's fade (an insensitive image, built hidden) is for rows passing under the bar: shown while the list is scrolled, hidden at rest, where it would darken
     * the large title. Never a touch target. */
    if (fo.fade) {
        widget_set_visible(fo.fade, fo_off() > 0, 0);
        widget_set_sensitive(fo.fade, 0);
    }
}

static void fo_head(void) { /* the navbar's title: "N Selected" in select mode, else the level's name cut to its room */
    char buf[64];
    if (!fo.select) {
        az_fit(fo.title, fo_text());
        return;
    }
    pod_fmt(buf, sizeof buf, TR("%d Selected"), (int)fo.nsel);
    widget_set_text_utf8(fo.title, buf);
}

/* The scroll_view's EVT_SCROLL (every change of its offset) and scroll end. */
static int fo_on_scroll(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (fo.view) fo_title_update();
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * Reading the stock list
 */
static void fo_size(void) {
    int h = fo.nvis ? fo_content() : GRID_VIEW_H;
    widget_resize(fo.view, FO_W, h);
    widget_set_prop_int(fo.sv, "virtual_h", h);
}

/* The pills belong to a folder that holds an audio file; in select mode they stay, dim and dead (their disabled style). */
static void fo_pills(void) {
    widget_set_visible(fo.btn_play, fo.nfile != 0, 0);
    widget_set_visible(fo.btn_shuffle, fo.nfile != 0, 0);
    widget_set_sensitive(fo.btn_play, fo.nfile != 0 && !fo.select);
    widget_set_sensitive(fo.btn_shuffle, fo.nfile != 0 && !fo.select);
}

/* The stock list as the page shows it: the index of the shown records, the marks, the titles. keep: the scroll offset stays (a list read again); else the top. */
static void fo_load(int keep) {
    int at = keep ? fo_off() : 0, nomem = 0;
    unsigned i;
    void *list = *(void **)PDEQ_SHOWLIST;
    grid_drop(&fo.g);
    free(fo.vis);
    free(fo.sel);
    fo.vis = (int *)0, fo.sel = (unsigned char *)0, fo.list = fo.first = (void *)0;
    fo.count = fo.nvis = fo.nsel = 0, fo.nfile = fo.nmark = 0, fo.first_file = -1, fo.press = fo.down = 0;
    if (list) fo.count = deque_size(list);
    if (fo.count) {
        fo.vis = calloc(fo.count, sizeof(int));
        fo.sel = calloc((fo.count + 7) / 8, 1);
        if (!fo.vis || !fo.sel) {
            free(fo.vis);
            free(fo.sel);
            fo.vis = (int *)0, fo.sel = (unsigned char *)0, fo.count = 0, nomem = 1;
        }
    }
    if (fo.count) {
        fo.list = list, fo.first = deque_at(list, 0);
        for (i = 0; i < fo.count; ++i) {
            void *rec = deque_at(list, i);
            if (*cc_str(rec, REC_NAME) == '.') continue; /* a dot name (a hidden folder or file) is not shown */
            fo.vis[fo.nvis++] = (int)i;
            if (I(rec, REC_TYPE) == T_FILE) {
                if (fo.first_file < 0) fo.first_file = (int)i;
                ++fo.nfile;
            }
            if (fo_markable(I(rec, REC_TYPE))) ++fo.nmark;
        }
    }
    fo_show(fo.view, fo.nvis != 0);
    fo_show(fo.status, fo.nvis == 0);
    if (!fo.nvis) widget_set_tr_text(fo.status, nomem ? "Not enough memory" : "Empty folder");
    fo_pills();
    fo_size();
    widget_set_prop_int(fo.sv, "yoffset", at < 0 ? 0 : at > fo_max_scroll() ? fo_max_scroll() : at);
    az_fit(fo.big, fo_text());
    fo_head();
    fo.title_on = -1;
    fo_title_update();
    fo_redraw();
    if (fo.select && fo_root())
        fo_select(0); /* the root has nothing to select: the mode ends (and the capsule is made again) */
    else
        fo_cap();
}

/* Another query replaced the stock list under a page that is on top (a paint found it): the level is read again (the stock folder_reload: the card's directory). A page behind
 * another does it when it comes back. */
static int fo_on_stale(const void *unused) {
    (void)unused;
    fo.stale_timer = 0;
    if (fo.view && fo.g.tiles && !fo_valid() && pod_is_top(fo.win)) {
        folder_reload();
        fo_load(1);
    }
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * Playing: the stock folder row's handler (@0x531e00: loadSongList of the folder's files, then Now Playing at the row)
 */
static void fo_open_player(void *queue, int idx, int cls) {
    struct {
        void *dq;
        int idx, cls, mode;
    } context;
    context.dq = queue, context.idx = idx, context.cls = cls, context.mode = PLAY_MODE;
    navigator_to_with_context("playing_page", &context);
}

/* Record rec (an audio file) of the list and the folder's files as the queue, in Now Playing (patch/songops.c). */
static void fo_play(int rec, int how) {
    if (!fo_valid()) {
        folder_reload();
        fo_load(1);
        return;
    }
    so_play(FO_CLASS, fo.list, rec, how, fo_open_player);
}

static int fo_on_play(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (fo.view && fo.first_file >= 0 && !fo.select) fo_play(fo.first_file, SO_IN_ORDER);
    return RET_OK;
}

/* Shuffle: a random file of the folder, in the stock Shuffle mode (the queue is the folder's files, so the stock Shuffle shuffles exactly them). */
static int fo_on_shuffle(void *ctx, void *e) {
    unsigned k;
    unsigned r;
    (void)ctx;
    (void)e;
    if (!fo.view || fo.first_file < 0 || fo.select) return RET_OK;
    k = pod_rand((unsigned)fo.nfile);
    for (r = 0; r < fo.nvis; ++r)
        if (fo_type(fo.vis[r]) == T_FILE && !k--) break;
    if (r < fo.nvis) fo_play(fo.vis[r], SO_SHUFFLE);
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * Levels: the stock functions on the stock state
 */
/* Into record rec (a folder, a storage, a playlist file): folder_enter says what happened; the stock messages for a card that is not there. -1 for a folder or a storage is
 * toolsLoadDirectory returning 0 (nothing in it to list; folder_enter strips the path again and leaves the layer and the shown list as they were; stock says "File Not Found"):
 * ours says what it is. A playlist file keeps the stock message. */
static void fo_enter(int rec) {
    int r, type;
    if (!fo_valid()) {
        folder_reload();
        fo_load(1);
        return;
    }
    type = fo_type(rec);
    r = folder_enter(rec, fo_off());
    if (r == -2)
        pod_toast(TR("msg_nottf"));
    else if (r == -3)
        pod_toast(TR("msg_nototg"));
    else if (r == -1 && type == T_LIST)
        pod_toast(TR("msg_notfile"));
    else if (r == -1)
        pod_toast(TR("No music in this folder"));
    else if (r == 1)
        fo_load(0);
    /* the failed load emptied the folder deque 0xa03964 (batch_delete_file's class 1 source): read the level again, as the stock page does when the message closes */
    if (r == -1) {
        folder_reload();
        fo_load(1);
    }
}

/* ---------------------------------------------------------------------------
 * The select mode
 */
/* The capsule: Select | Now Playing, Select hidden in select mode and at the root (nothing selectable there); Now Playing alone is the glass disc, the capsule's right cap otherwise. */
static void fo_cap(void) {
    int sel = !fo.select && !fo_root(), np = !fo.select;
    const char *img = sel ? "ah_nav_play" : "ah_nav_np";
    fo_show(fo.btn_select, sel);
    fo_show(fo.np, np);
    if (fo.np) {
        widget_set_prop_str(fo.np, "style:normal:icon", img);
        widget_set_prop_str(fo.np, "style:over:icon", img);
        widget_set_prop_str(fo.np, "style:pressed:icon", sel ? "ah_nav_play_down" : "ah_nav_np_down");
    }
}

static void fo_select(int on) {
    if (on == fo.select) return;
    fo.select = on;
    fo.nsel = 0;
    if (fo.sel) memset(fo.sel, 0, (fo.count + 7) / 8);
    fo.press = fo.down = 0;
    fo_cap();
    fo_show(fo.btn_selall, on);
    fo_show(fo.bar, on);
    fo_pills();
    widget_set_prop_str(fo.back, "style:normal:icon", on ? "ah_nav_close" : "ah_nav_back");
    widget_set_prop_str(fo.back, "style:over:icon", on ? "ah_nav_close" : "ah_nav_back");
    widget_set_prop_str(fo.back, "style:pressed:icon", on ? "ah_nav_close_down" : "ah_nav_back_down");
    fo.title_on = -1;
    fo_head();
    fo_title_update();
    fo_retext();
    fo_size();
    if (fo_off() > fo_max_scroll()) widget_set_prop_int(fo.sv, "yoffset", fo_max_scroll());
    fo_redraw();
}

static void fo_changed(void) {
    fo_head();
    fo_redraw();
}

static void fo_toggle(int rec) {
    if (rec < 0 || rec >= (int)fo.count || !fo.sel || !fo_markable(fo_type(rec))) return;
    fo.sel[rec >> 3] ^= (unsigned char)(1 << (rec & 7));
    fo.nsel += fo_is_sel(rec) ? 1 : (unsigned)-1;
    fo_changed();
}

static int fo_on_select(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (fo.view && fo.nvis) fo_select(1);
    return RET_OK;
}

static int fo_on_selall(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (!fo.select || !fo.sel) return RET_OK;
    memset(fo.sel, 0, (fo.count + 7) / 8);
    if ((int)fo.nsel < fo.nmark) { /* every folder and audio file, unless all are marked: then none */
        unsigned r;
        fo.nsel = 0;
        for (r = 0; r < fo.nvis; ++r) {
            int rec = fo.vis[r];
            if (fo_markable(fo_type(rec))) fo.sel[rec >> 3] |= (unsigned char)(1 << (rec & 7)), ++fo.nsel;
        }
    } else
        fo.nsel = 0;
    fo_changed();
    return RET_OK;
}

/* The stock confirm dialog (the folder handler's kind 1: a yes / no question): modal, Yes returns CONFIRM_YES. */
static int fo_ask(const char *text) {
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

/* Whether a marked record is a folder: stock removes it with rm -rf, so the confirm says so. */
static int fo_marked_dir(void) {
    int rec;
    for (rec = 0; rec < (int)fo.count; ++rec)
        if (fo_is_sel(rec) && fo_type(rec) == T_DIR) return 1;
    return 0;
}

/* Delete: the stock folder handler's sequence (@0x5324d0): nothing marked is a message; the confirm dialog; a playlist file's list cannot be removed from; then
 * batch_delete_file(1, the shown list, the selection, 0, 1) (the files too, as the stock page always does) and the message. The list is read again. */
static int fo_on_delete(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (!fo.select) return RET_OK;
    if (!fo.nsel) {
        pod_toast(TR("msg_delfilefailed"));
        return RET_OK;
    }
    if (!fo_ask(TR(fo_marked_dir() ? "Delete folder and everything in it?" : "msg_delfile"))) return RET_OK;
    if (*(char *)FOLDER_M3U) {
        pod_toast(TR("msg_notsupportdel"));
        return RET_OK;
    }
    if (!fo_valid() || !so_selection(fo.count, fo.sel)) {
        fo_select(0);
        folder_reload();
        fo_load(1);
        return RET_OK;
    }
    batch_delete_file(FO_CLASS, fo.list, *(void **)SEL_VEC, 0, 1);
    pod_toast(TR("msg_delfilesuccess"));
    fo_select(0);
    folder_reload();
    fo_load(1);
    return RET_OK;
}

/* Add to playlist: the stock playlist picker over this page (class 1); the title the picker may overwrite and the browsing class it sets are put back when this window
 * comes to the front. */
static int fo_on_add(void *ctx, void *e) {
    int r;
    (void)ctx;
    (void)e;
    if (!fo.select) return RET_OK;
    r = so_add(FO_CLASS, fo.count, fo.sel, fo.nsel, fo_valid(), fo.title_save, &fo.picker);
    if (r < 0) {
        fo_select(0);
        folder_reload();
        fo_load(1);
    }
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * Touch on the rows (the Songs page's: DOWN remembers, ABORT forgets, UP within the drag threshold on the same row acts)
 */
static int fo_item_of(void *e) {
    int pt[2];
    pt[0] = I(e, PE_X), pt[1] = I(e, PE_Y);
    widget_to_local(fo.view, pt);
    return fo_at(pt[1]);
}

static void fo_set_press(int p) {
    if (fo.press == p) return;
    fo.press = p;
    fo_redraw();
}

static int fo_on_down(void *ctx, void *e) {
    int a;
    (void)ctx;
    fo.down = 0;
    if (!e || !fo.view || !fo.nvis || !fo_valid()) return RET_OK;
    a = fo_item_of(e);
    fo.down = a + 1, fo.down_x = I(e, PE_X), fo.down_y = I(e, PE_Y);
    if (!fo.select) fo_set_press(a + 1);
    return RET_OK;
}

/* A tap: in select mode a folder or an audio file toggles its mark (nothing else is marked); else a file plays and anything else is gone into. */
static void fo_tap(int r) {
    int rec = fo.vis[r];
    if (fo.select)
        fo_toggle(rec);
    else if (fo_type(rec) == T_FILE)
        fo_play(rec, SO_KEEP);
    else
        fo_enter(rec);
}

static int fo_on_up(void *ctx, void *e) {
    int a = fo.down - 1;
    (void)ctx;
    fo.down = 0;
    fo_set_press(0);
    if (a < 0 || !e || !fo.view) return RET_OK;
    if (fo_abs(I(e, PE_X) - fo.down_x) < SC_DRAG_PX && fo_abs(I(e, PE_Y) - fo.down_y) < SC_DRAG_PX &&
        fo_item_of(e) == a && (unsigned)a < fo.nvis)
        fo_tap(a);
    return RET_OK;
}

static int fo_on_abort(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    fo.down = 0;
    fo_set_press(0);
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * The window
 */
/* Back: select mode ends; else one level up through the stock stack (the offset the level was left at comes back); at the root the stock state is cleared (folder_back
 * returns 0) and the window closes. */
static int fo_on_back(void *ctx, void *e) {
    int y = 0, r;
    (void)ctx;
    (void)e;
    if (fo.select) {
        fo_select(0);
        return RET_OK;
    }
    r = folder_back(&y);
    if (!r) {
        fo.nvis = 0; /* nothing of the cleared list is read while the window closes */
        navigator_back();
        return RET_OK;
    }
    fo_load(0);
    widget_set_prop_int(fo.sv, "yoffset", y < 0 ? 0 : y > fo_max_scroll() ? fo_max_scroll() : y);
    fo_title_update();
    return RET_OK;
}

static int fo_on_fg(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (!fo.view || !fo.g.tiles) return RET_OK;
    if (fo.picker) { /* back from the stock playlist picker: its title and class put back, the add done, select mode over */
        fo.picker = 0;
        *(int *)G_CLASS_TYPE = FO_CLASS;
        memcpy((void *)NAV_TITLE, fo.title_save, sizeof fo.title_save);
        fo_select(0);
        folder_reload();
        fo_load(1);
    } else if (!fo_valid()) { /* (a dialog or Now Playing closing leaves the list as it was: the marks stay) */
        folder_reload();
        fo_load(1);
    }
    return RET_OK;
}

static int fo_on_bg(void *ctx, void *e) { return fo_on_abort(ctx, e); }

static int fo_on_destroy(void *ctx, void *e) {
    int i;
    (void)ctx;
    (void)e;
    if (fo.stale_timer) timer_remove(fo.stale_timer);
    grid_free(&fo.g);
    for (i = 0; i < 2; ++i)
        if (fo.mark[i]) bitmap_destroy(fo.mark[i]);
    if (fo.chev) bitmap_destroy(fo.chev);
    for (i = 0; i < FO_ICONS; ++i)
        if (fo.ic[i]) bitmap_destroy(fo.ic[i]);
    free(fo.vis);
    free(fo.sel);
    memset(&fo, 0, sizeof fo);
    return RET_OK;
}

/* A stock 40 x 40 glyph as a bitmap (the Albums page's cover decode, size 40: the image as it is), NULL when it cannot be made. win: any widget of the page. */
static void *fo_bitmap(void *win, const char *name) {
    unsigned *px;
    void *b = bitmap_create_ex(FO_ICON, FO_ICON, FO_ICON * 4, BITMAP_RGBA8888);
    int ok;
    if (!b) return b;
    px = (unsigned *)bitmap_lock_buffer_for_write(b);
    if (!px || bitmap_get_line_length(b) != FO_ICON * 4) {
        if (px) bitmap_unlock_buffer(b);
        bitmap_destroy(b);
        return (void *)0;
    }
    ok = cc_decode(win, name, 1, FO_ICON, 1, px);
    bitmap_unlock_buffer(b);
    if (!ok) {
        bitmap_destroy(b);
        return (void *)0;
    }
    return b;
}

/* The Folders page. 0 once it is up, -1 if it could not open (the kill switch, a page already open, a window that will not open: the caller leaves it to the stock page), -2 if the
 * asset is not ours (the page is left again). */
static int fo_open_page(void) {
    int i;
    if (fo.win || home_off()) return -1;
    memset(&fo, 0, sizeof fo);
    fo.first_file = -1;
    fo.win = window_open(FO_ASSET);
    if (!fo.win) return -1;
    widget_on(fo.win, EVT_DESTROY, fo_on_destroy, (void *)0);
    fo.back = pod_bind(fo.win, "btn_return", fo_on_back, (void *)0);
    fo.np = pod_bind(fo.win, "btn_backtoplayer", pod_on_player, (void *)0);
    fo.btn_select = pod_bind(fo.win, "btn_select", fo_on_select, (void *)0);
    fo.btn_selall = pod_bind(fo.win, "btn_selall", fo_on_selall, (void *)0);
    fo.btn_play = pod_bind(fo.win, "btn_play", fo_on_play, (void *)0);
    fo.btn_shuffle = pod_bind(fo.win, "btn_shuffle", fo_on_shuffle, (void *)0);
    fo.btn_add = pod_bind(fo.win, "sg_add", fo_on_add, (void *)0);
    fo.btn_del = pod_bind(fo.win, "sg_del", fo_on_delete, (void *)0);
    fo.title = widget_lookup(fo.win, "label_title", 1);
    fo.big = widget_lookup(fo.win, "sg_title", 1);
    fo.fade = widget_lookup(fo.win, "img_nb_fade", 1); /* optional */
    fo.view = widget_lookup(fo.win, "view_grid", 1);
    fo.sv = widget_lookup(fo.win, "folders_scrollview", 1);
    fo.status = widget_lookup(fo.win, "label_status", 1);
    fo.st_title = widget_lookup(fo.win, "label_row_title", 1);
    fo.bar = widget_lookup(fo.win, "sg_bar", 1);
    if (!fo.back || !fo.np || !fo.btn_select || !fo.btn_selall || !fo.btn_play || !fo.btn_shuffle || !fo.btn_add ||
        !fo.btn_del || !fo.title || !fo.big || !fo.view || !fo.sv || !fo.status || !fo.st_title || !fo.bar) {
        navigator_back(); /* an asset that is not ours */
        return -2;
    }
    pod_centre_pill(fo.btn_play, SG_PILL_W);
    pod_centre_pill(fo.btn_shuffle, SG_PILL_W);
    pod_centre_pill(fo.btn_add, SG_BAR_PILL_W);
    pod_centre_pill(fo.btn_del, SG_BAR_PILL_W);
    fo.mark[0] = pod_make_mark(fo.win, "unselect");
    fo.mark[1] = pod_make_mark(fo.win, "selected");
    if (!fo.mark[0] || !fo.mark[1])
        fo.mark[0] = fo.mark[1] =
            (void *)0; /* (one that did not decode is freed with the other at destroy: the pair is all or none) */
    fo.chev = pod_make_chevron();
    for (i = 0; i < FO_ICONS; ++i) fo.ic[i] = fo_bitmap(fo.win, FO_ICON_NAME[i]);
    fo.noscroll = !widget_on(fo.sv, EVT_SCROLL, fo_on_scroll, (void *)0) ||
                  !widget_on(fo.sv, EVT_SCROLL_END, fo_on_scroll, (void *)0);
    if (fo.noscroll)
        widget_set_visible(fo.title, 1,
                           0); /* the large title's collapse needs the scroll events: the navbar keeps its title */
    fo.title_on = fo.noscroll;
    widget_on(fo.win, EVT_WINDOW_TO_FG, fo_on_fg, (void *)0);
    widget_on(fo.win, EVT_WINDOW_TO_BG, fo_on_bg, (void *)0);
    widget_on(fo.view, EVT_POINTER_DOWN, fo_on_down, (void *)0);
    widget_on(fo.view, EVT_POINTER_UP, fo_on_up, (void *)0);
    widget_on(fo.view, EVT_POINTER_ABORT, fo_on_abort, (void *)0);
    widget_on(fo.view, EVT_AFTER_PAINT, fo_on_paint, (void *)0);
    if (!grid_init(&fo.g, fo.win, GRID_TILES, LIST_ART, 0)) {
        grid_free(&fo.g);
        fo_show(fo.view, 0);
        fo_show(fo.status, 1);
        widget_set_tr_text(fo.status, "Not enough memory");
        return 0;
    }
    folder_enter(-1, 0); /* as the stock folder_page_init: the root list of storages, layer 1 */
    *(int *)G_CLASS_TYPE = FO_CLASS; /* as folder_page_init leaves it (@0x5334b4: 1) */
    fo_load(0);
    return 0;
}

/* The M1+ Music menu's Folders row. A window that will not open leaves the stock folder page, through the Home dispatcher. 0 once something is requested. */
int folders_open(int home) {
    int r = fo_open_page();
    if (r == -1 && !fo.win && home >= 0) return pod_home_open(home);
    return r;
}
