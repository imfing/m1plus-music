/* M1+ Music Podcasts: the shows on the card and their episodes, one page with three levels.
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 * Resume, played marks and speed per show follow q2-pod; the data is patch/pcmodel.c's.
 *
 * ui/m1plus_podcasts.bin is the Albums page's structure (docs/modules/albums.md): the navbar over a stock list, list_view > scroll_view, whose ONE child, view_grid, paints
 * the rows itself in its EVT_AFTER_PAINT (no widget per row), so a show of hundreds of episodes costs a tile ring. The window is opened by the Extras item Podcasts and has three
 * levels, switched in place (the Pod's way: no second window; the navbar's Back goes up a level before it leaves the page):
 *
 *   Shows      the Apple Podcasts style top level (docs/modules/podcasts.md "The Shows page"): the large title, the refresh line (Refresh All), Continue Listening (a static row of at most three
 *              partly played episodes), the Downloads row and the Albums grid of every show (the most recently updated first), a caption under each; the "..." sheet has Import from Card.
 *   Downloads  the queue, the failed and the paused downloads, behind the Downloads row (Back returns to Shows).
 *   Show       the Apple Podcasts style page (docs/modules/podcasts.md "The Show page"): a header in the album page's manner (the PS_ART px cover, the name, a Latest Episode pill, the
 *              show's description and its "Category - Author" line, tinted from the cover as the album page is), then a fixed height cell per episode, newest first (PS_CELL_H: the date
 *              line with its badges, the title, the description, the state pill and the "..."). The navbar is "... | Now Playing" (the sheet of the show's actions) and, scrolled, the small
 *              title. A tap on a cell's pill plays an episode that is on the card (and the ones after it in the list's order: from the first second, or from the saved place: pc_note jumps there); a tap on its body opens the episode page (pcdetail.c).
 *
 * Playing builds stSongInfo records of our own for the show's files (the library may not have scanned them) and starts them as the stock Folders page does: class 1, the
 * queue handed to playing_page (start_player copies it). Cover pictures are decoded one per 16 ms tick (pc_cover_ok first: a picture that is too large for the stock decoder is
 * refused). The page's 1 s timer calls pc_note, like the other pages that already look at the playing track. No hook.
 */
#include "offsets.inc"
#include "stock.h"
#include "covercache.h"
#include "common.h"
#include "grid.h"
#include "azlist.h"
#include "home.h"
#include "i18n.h"
#include "keyboard.h"
#include "podcasts.h"
#include "pcfeed.h"
#include "pcjson.h"
#include "pcnet.h"
#include "pcnotes.h"
#include "pcdetail.h"
#include "pcopml.h"
#include "pcwrap.h"

extern void pod_toast(const char *text); /* patch/shuffle.c: the stock message box */
extern void pod_set_in_order(void); /* patch/shuffle.c: Shuffle and Repeat one become List play */

#define I(w, off) (*(int *)((char *)(w) + (off)))
#define B(w, off) (*(unsigned char *)((char *)(w) + (off)))
#define P(w, off) (*(void **)((char *)(w) + (off)))

#define PG_W 320
#define PG_LOAD_MS 16
#define PG_TICK_MS 1000
#define PG_TAP_PX SC_DRAG_PX
#define PG_HINT_H (8 + 4 * PS_TITLE_PITCH) /* the empty page's hint: room for four lines under the header */
#define PG_BOTTOM 20 /* the Show level's last cell has this much under it */
#define PG_REC_SIZE 0x58
#define PG_CELLS \
    8 /* the Show level's cell layouts: a ring keyed by the episode's index modulo this (at most four cells show at once) */
#define PG_FADE_H \
    20 /* the Show level's navbar fade (the page's colour, drawn over the first rows while the list is scrolled): nb_fade's height */
#define PG_TEXT_MAX 232 /* wide chars of a cell's description (at most PC_DESC_CUT bytes) and room for the ellipsis */
#define PG_TITLE_MAX 100 /* wide chars of a title (95 bytes at most) */
#define PG_PILL_MAX 48 /* wide chars of a pill's label */
#define PG_SHEET_ROWS 13 /* the sheets' fixed rows (tools/pod_ui.py PS_SHEET_ROWS) */
#define PG_AWAKE_MS 1000 /* the downloads' timer */

enum {
    L_SHOWS = 0,
    L_EPS = 1,
    L_DLS = 2,
    L_SRCH = 3
}; /* the search level: Podcast Search on in Settings, behind the Shows level's Search button */
enum {
    SP_NONE = 0,
    SP_SEARCH = 1,
    SP_PREVIEW = 2
}; /* the job the search level waits to start (the downloads pause for it first) */
enum {
    SS_IDLE = 0,
    SS_WAIT = 1,
    SS_RUN = 2,
    SS_DONE = 3
}; /* the search: nothing asked, asked and waiting for the worker, the worker has it, the answer is in */

#define PG_IP_MAX PC_MAX_SHOWS /* In Progress rows of the Downloads level (queued, running, failed, paused) */
#define PG_DLD_MAX 300 /* Downloaded rows: the newest this many (docs/modules/podcasts.md "The Downloads page") */
#define PG_DLS_MAX \
    (PG_IP_MAX + PG_DLD_MAX) /* slots of the Downloads level: In Progress in 0..PG_IP_MAX - 1, Downloaded after */
#define PG_PICK_BYTES ((PG_DLS_MAX + 7) / 8) /* the select mode's bitsets (display rows) */

struct pg_dl { /* a row of the Downloads level (a slot: its tile's key stays when rows come and go) */
    char dir[PC_FILE], file[PC_FILE], title[PC_TITLE];
    unsigned key; /* In Progress: the download's key (pn_dl_key) */
    unsigned hash, when, kb, dur,
        pub; /* Downloaded: the ring key of the file, its modification time (else the episode's date) and size in KB, the episode's length and date */
    int si; /* the show (an index into shows): the row's cover and name */
};

typedef struct
{ /* a cell's layout: made once when it first paints (the wrap needs the font), dropped when the list is made again */
    int idx; /* the episode's index + 1, 0 = free */
    unsigned title[PG_TITLE_MAX], desc[PG_TEXT_MAX], date[40];
    pw_line_t tl[2], dl[2];
    int tn, dn, datelen;
} pg_cell_t;

typedef struct { /* the Show header's layout: the texts wrapped, the blocks' tops (content y) */
    unsigned name[PG_TITLE_MAX], desc[PG_TEXT_MAX], meta[PG_TEXT_MAX];
    pw_line_t nl[PS_NAME_LINES], dl[PS_DESC_LINES], ml[1];
    int nn, nd, nm; /* lines of each */
    int y_name, y_latest, y_desc, y_meta, y_head, h; /* the blocks' tops; h is where the cells start */
    int has_latest; /* there is an episode: the pill shows */
    int collapse; /* the offset from which the navbar shows the small title */
} pg_hdr_t;

enum {
    PK_PLAY = 0,
    PK_RESUME,
    PK_DOWN,
    PK_RING,
    PK_PAUSED,
    PK_RETRY,
    PK_SUB
}; /* a state pill's kind: the first two are filled (play-type), the others outlined (download-type); the preview's Subscribe (white) has no glyph */
enum {
    PH_BODY = 0,
    PH_PILL = 1,
    PH_DOTS = 2,
    PH_LATEST = 3,
    PH_LINE = 4,
    PH_DLROW = 5,
    PH_SHELF = 6,
    PH_CELL = 7,
    PH_FIELD = 8,
    PH_CLEAR = 9,
    PH_SUBROW = 11,
    PH_SHOW = 12,
    PH_SAVROW = 13
}; /* what a touch hit: on the Show level the first four (the episode page's show row: PH_SHOW); on the Shows level the refresh line, the Downloads and Subscriptions rows, a Continue Listening item, a show's cover and captions */
enum {
    SR_SPEED = 0,
    SR_REFRESH,
    SR_SELECT,
    SR_MARKALL,
    SR_UNSUB,
    SR_DL,
    SR_RM,
    SR_MARK,
    SR_UNMARK,
    SR_IMPORT,
    SR_DELPLAYED,
    SR_EXPORT,
    SR_SAVE
}; /* the sheets' rows, tools/pod_ui.py PS_SHEET_ROWS */
enum { SH_NONE = 0, SH_SHOW = 1, SH_CELL = 2, SH_HOME = 3, SH_SUBS = 4, SH_DLS = 5 };
enum {
    ST_NAME = 0,
    ST_SEC,
    ST_META,
    ST_HEAD,
    ST_DATE,
    ST_CTITLE,
    ST_CDIM,
    ST_CDESC,
    ST_PILL,
    ST_LATEST,
    ST_LATESTW,
    ST_SECH,
    ST_LINE,
    ST_STITLE,
    ST_SLEFT,
    ST_GTITLE,
    ST_GSUB,
    ST_N
}; /* the text styles of the Show page and the Shows page (tools/pod_ui.py PS_STYLES, in that order) */

typedef struct { /* a state pill: its kind, the ring step, and the label (wide) with its width in px */
    int kind, ring, nlabel, w, tx; /* tx: where the label starts inside a Latest Episode pill */
    unsigned label[PG_PILL_MAX];
} pg_pill_t;

static struct {
    void *win, *view, *sv, *status, *title, *fade,
        *big; /* big: the Shows level's large title (a child of the content view) */
    void *st_title, *st_sub; /* hidden labels whose styles are the Downloads rows' title and grey line */
    void *st[ST_N]; /* the Show page's text styles, hidden labels (tools/pod_ui.py PS_STYLES, in that order) */
    void *dlg_scrim, *dlg_card, *dlg_name, *dlg_count, *dlg_fill,
        *dlg_cancel; /* the refresh dialog (hidden widgets of the asset) */
    void *btn_more,
        *np; /* the navbar's "..." (the Show level, and the Shows level when its sheet has a row) and Now Playing (the capsule's right cap, a disc where there is no "...") */
    void *tint_img; /* img_ah_tint: the album page's gradient, shown on the Show level while the page is tinted */
    void *sh_scrim, *sh_card, *sh_row[PG_SHEET_ROWS], *sh_tx[PG_SHEET_ROWS], *sh_hr[PG_SHEET_ROWS],
        *sh_vl
            [2]; /* the sheets (widgets of the asset): scrim, card, and per row the button, its label, its hairline; the value labels of Playback Speed and Refresh Feed */
    int sheet, sh_ep; /* SH_NONE / SH_SHOW / SH_CELL / SH_HOME; the episode of a cell's sheet */
    char root[PC_FILE + 20];
    pc_show_t *shows;
    int nshows; /* every folder the model found (shows with files, subscriptions without), the most recently updated first */
    int nrows; /* the Downloads level's display rows: nip In Progress, then nd Downloaded (pg.ord maps a row to its slot) */
    int nip, nd;
    unsigned gen; /* pn_gen() the Shows and Downloads levels were made at */
    pc_ep_t *eps; /* the episodes of the show open (on the card or not), newest first */
    int neps;
    int level, sel,
        show_off; /* the level, the show open (an index into shows), the Shows level's offset to come back to */
    int press, down, down_part, down_x,
        down_y; /* the row under the finger + 1; the row a press began on + 1 (0 none) and what of it (PH_*), and where */
    int fg, noscroll;
    unsigned rev; /* pc_rev() the rows were made at */
    unsigned timer, load_timer, dlg_timer,
        awake; /* awake: the downloads' timer (keeps the device awake, starts the queue again): scoped to the window, in front or not */
    int rpend; /* a refresh waits for the downloads to pause: 1 + only_new */
    int rone; /* ... and it is of the show open only (the Show level's Refresh Feed): 1, else 0 (Refresh All / Import) */
    int saved, want_off,
        sv_n; /* the Downloads-style level (L_DLS) lists the Saved episodes (docs/modules/podcasts.md "Saved"); the offset the list is to come back to once its rows are in; the Saved episodes counted by pg_saved_load */
    unsigned *sv_h,
        *sv_d; /* their ring keys (pc_hash of the path), the last saved first, and the hashes of their show folders */
    int subs, from_subs,
        subs_off; /* the Downloads-style level (L_DLS) lists the Subscriptions instead of the downloads; the Show level was opened from it (Back returns there, to this offset) */
    void *
        unsubp; /* the select bar's Unsubscribe pill: a second pill in the Delete pill's place (the Subscriptions level shows it instead) */
    unsigned dgen; /* pn_dl_gen() the Show level's lines were made at */
    void *back, *btn_selall, *bar, *del,
        *mark
            [2]; /* select mode: the navbar's Back (its x), Select, Select All, the bottom bar and its Delete pill, the unselect / selected marks */
    int select; /* select mode (the Show and Downloads levels: marks, Select All, a Delete bar) */
    unsigned npick, ncan; /* rows marked, rows that can be */
    unsigned char pick[PG_PICK_BYTES], can[PG_PICK_BYTES]; /* the marks, and the rows that may be marked */
    struct pg_dl *dls; /* the Downloads level's slots (PG_DLS_MAX) */
    unsigned short *ord,
        *dord; /* ord: display row -> slot (PG_DLS_MAX); dord: the Downloaded slots, newest first (PG_DLD_MAX) */
    /* The Downloaded scan (docs/modules/podcasts.md "The Downloads page"): one show a tick of the loader; dscan is the next of the dsn shows in dsl; the totals count every file, past the cap too */
    int dscan, dsn, dscan_on, dfree_ok, dtick;
    unsigned char dsl[PC_MAX_SHOWS];
    unsigned dtot_n, dtot_kb, dfree_kb;
    /* The Shows level's totals (the Downloads row's grey line): a light scan of the folders, one show a tick; the figures of the last complete scan stay until the next one ends */
    int tscan, tscan_on, tot_ok;
    unsigned ta_kb, ta_parts, tot_kb, tot_parts, tot_gen;
    int from_dls,
        dls_off; /* the Show level (the episode page) was opened from the Downloads page: Back returns there, to this offset */
    int dlg; /* the refresh dialog is up */
    unsigned dlg_name_hash; /* pc_hash of the feed whose name the dialog shows */
    unsigned dlg_px,
        dlg_done; /* what the dialog last drew: the fill's width, and the "n of m" it showed (so a tick without news changes nothing) */
    unsigned
        feed_hash; /* pc_hash of the open show's feed url (0: none): a refresh may rename the folder, so the show is found again by it */
    unsigned tint,
        tint_key; /* the Show page's colour (0x00BBGGRR, 0: black) and the tone cache key of the show (0: none) */
    int tint_on, bar_ours,
        collapsed; /* the page is tinted (window colour, gradient shown); the status bar is ours; the small title shows */
    void *dltile; /* pod_ic_dltile (the Downloads row's tile) */
    void *atlas; /* pc_atlas decoded with its alpha (PA_SIZE square), once the Show level first paints */
    void *
        subtile; /* pod_ic_subtile (the Subscriptions row's tile), decoded the same way once the Shows level first paints */
    void *savetile; /* pod_ic_savetile (the Saved row's tile) */
    void *chev; /* the shared list chevron (pod_make_chevron), made on first use */
    pg_cell_t *cells; /* PG_CELLS layouts of the Show level's cells */
    pg_hdr_t *hdr; /* the Show header's layout */
    pd_t *
        pd; /* the episode page's texts (docs/modules/podcasts.md "The episode page"), made when it opens; NULL while the Show level is the list */
    int det,
        det_off; /* the episode page is open on episode det - 1 of eps (0: the list); the list's scroll offset to come back to */
    unsigned det_key; /* pg_ep_key of that episode: it is found again when the episodes are read again */
    grid_t g; /* the tiles: an episode's show's cover and texts (the Downloads level's rows) */
    grid_t hg; /* the Show header's cover (one tile) */
    grid_t
        gg; /* the Shows level's grid: the shows' GRID_COVER px covers and their captions (the Albums grid's tiles and loader) */
    grid_t sg; /* Continue Listening's covers (PP_SHELF_ART px, one tile each) */
    struct
        pg_item { /* a Continue Listening item: the episode's show, its ring key, its title cut to PP_SHELF_W px (wide chars) */
        int show, tn;
        unsigned hash;
        unsigned title[PG_TITLE_MAX];
    } cont[PP_SHELF_MAX];
    int ncont;
    int has_import; /* Podcasts/subscriptions.txt exists: the Shows level's "..." has Import from Card */
    int has_line; /* some show has a feed: the refresh line shows */
    int y_shelf, y_dl, y_sub, y_sav, y_shows, y_grid,
        home_h; /* the Shows level's blocks' tops (content y): the shelf's header (0: none), the Downloads row, the Subscriptions row (0: none), the "Shows" header, the grid; the content's height */
    unsigned gsig,
        ssig; /* what the grid's and the shelf's tiles were made for (a hash of the shows' folders, covers and the items' hashes): the tiles stay when a reload finds the same */
    /* Search (docs/modules/podcasts.md "Search"): searchon: Podcast Search is on (read when the page opens and each time it is back in front); the field's widgets; the text
     * of the field; sstate: SS_*; scode: the answer's PN_*; srn: result rows shown; sgen: pn_search_gen() the rows were made at; spend: the job waiting to start (with its address or Apple id); loading:
     * a preview is being fetched; sdone / sback: the keyboard's callbacks, handled when the page is in front; preview: the Show level is a preview (shows[PC_MAX_SHOWS], eps from the held feed); from_search: the Show
     * level (a preview, or the real page of a show that is subscribed already) was opened from the search level: Back returns there. */
    int searchon, sstate, scode, srn, spend, loading, sdone, sback, preview, from_search;
    void *sf, *sf_hint, *sf_text, *sf_clear;
    unsigned sgen;
    char sq[KB_MAX_LONG + 1], sp_url[PC_URL], sp_id[16], sp_text[KB_MAX_LONG + 1];
    /* aqh: pc_hash of the text the Apple answer is of (0: none); btn_globe: the navbar's globe (the entry to the search). */
    unsigned aqh;
    void *btn_globe;
} pg __attribute__((section(".scratch")));

/* Settings > Library > Podcasts > Podcast Search: "1" = on, anything else or no file = off. Read when the Podcasts page opens and each time it is back in front. */
int pcsearch_setting(void) { return set_read(PCSEARCH_FILE, 0) == '1'; }

int pcsearch_toggle(void) {
    int next = !pcsearch_setting();
    if (home_write_atomic(PCSEARCH_FILE, PCSEARCH_TMP, next ? "1\n" : "0\n") != 0) return -1;
    return next;
}

static void pg_show(void *w, int on) {
    if (!w) return;
    widget_set_visible(w, on, 0);
    widget_set_sensitive(w, on);
}

static int pg_abs(int v) { return v < 0 ? -v : v; }
static int pg_off(void) { return pg.sv ? I(pg.sv, SC_YOFF) : 0; }
static void pg_redraw(void) { widget_invalidate_force(pg.sv, (void *)0); }
static void pg_awake_arm(void); /* the downloads' timer, armed when something is queued */

static int pg_count(void) {
    return pg.level == L_EPS ? pg.neps : pg.level == L_DLS ? pg.nrows : pg.level == L_SRCH ? pg.srn : 0;
}
/* The Downloads level's geometry (content y; tools/pod_show.py downloads_layout is the same arithmetic): the storage line, then In Progress (a header and its rows), PP_SEC_GAP, then Downloaded (a header and its
 * rows). The Subscriptions page is plain rows from 0. pg_dy is the top of display row a. */
static int pg_dy(int a) {
    int y = PDL_LINE_PITCH;
    if (pg.subs || pg.saved) return PP_TITLE_H + a * PC_ROW_H;
    if (pg.nip) {
        y += PP_HEAD_PITCH;
        if (a < pg.nip) return y + a * PC_ROW_H;
        y += pg.nip * PC_ROW_H + PP_SEC_GAP;
    }
    return y + PP_HEAD_PITCH + (a - pg.nip) * PC_ROW_H;
}
/* The top of the In Progress header (sec 0) or the Downloaded header (sec 1). */
static int pg_dhead(int sec) {
    return sec && pg.nip ? PDL_LINE_PITCH + PP_HEAD_PITCH + pg.nip * PC_ROW_H + PP_SEC_GAP : PDL_LINE_PITCH;
}
static int pg_dh(void) {
    return pg.subs || pg.saved ? PP_TITLE_H + pg.nrows * PC_ROW_H
                               : (pg.nrows ? pg_dy(pg.nrows - 1) + PC_ROW_H + PP_BOTTOM : PDL_LINE_PITCH);
}
/* The display row under content y, -1 for none (a header, the line, the gap). */
static int pg_dhit(int y) {
    int a;
    for (a = 0; a < pg.nrows; ++a)
        if (y >= pg_dy(a) && y < pg_dy(a) + PC_ROW_H) return a;
    return -1;
}
static int pg_top(void) {
    return pg.level == L_SRCH ? PQ_TOP : pg.level == L_EPS && pg.hdr ? pg.hdr->h : 0;
} /* where the rows start in the content */
/* The Show level's cell height: PS_CELL_H, or PS_PCELL_H for the preview (no pill row under the description). */
static int pg_cell_h(void) { return pg.preview ? PS_PCELL_H : PS_CELL_H; }
static int pg_row_h(void) { return pg.level == L_EPS ? pg_cell_h() : PC_ROW_H; }
static const char *pg_no_eps_key(void);
/* The empty page's hint ("No downloads", the Show page's "No episodes yet..."), painted in the content under the header so it scrolls with it (NULL: none); pg_hint_y is its top (content y). While a Downloads scan runs nothing is
 * said yet. */
static const char *pg_hint(void) {
    if (pg.det) return (const char *)0;
    if (pg.level == L_DLS && !pg.nrows && (pg.subs || !pg.dscan_on))
        return pg.subs ? "No subscriptions" : pg.saved ? "No saved episodes" : "No downloads";
    if (pg.level == L_EPS && !pg.neps && !pg.preview) return pg_no_eps_key();
    return (const char *)0;
}
static int pg_hint_y(void) { return pg.level == L_EPS ? pg_top() : pg_dh(); }
static int pg_content(void) {
    if (pg.det && pg.pd) return pg.pd->h; /* (the episode page) */
    if (pg.level == L_SHOWS) return pg.home_h;
    if (pg.level == L_SRCH) return PQ_TOP + pg.srn * PC_ROW_H + (pg.srn ? PQ_BOTTOM : 0);
    if (pg_hint())
        return pg_hint_y() +
               PG_HINT_H; /* (an empty page: its header and the hint, no taller, so it only scrolls when they don't fit) */
    if (pg.level == L_DLS) return pg_dh() + (pg.select && pg.nrows ? SG_BAR_H : 0);
    return (pg_count()          ? pg_top() + pg_count() * pg_row_h() + (pg.level == L_EPS ? PG_BOTTOM : 0)
            : pg.level == L_EPS ? pg_top()
                                : 0) +
           (pg.select && pg_count() ? SG_BAR_H : 0); /* (the select mode's bar covers the last rows' place) */
}

static void pg_size(void) {
    int h = pg_content();
    widget_resize(pg.view, PG_W, h > 0 ? h : 1);
    widget_set_prop_int(pg.sv, "virtual_h", h > 0 ? h : 1);
}

/* The rows [*r0, *r1] that touch the view (r1 < r0 for none); inside [0, count - 1] also while the list is pulled past an end. */
static void pg_span(int *r0, int *r1) {
    int n = pg_count(), s = pg_off() - pg_top();
    if (pg.level == L_DLS) { /* (the Downloads level's rows are in sections: the first and last that touch the view) */
        int a;
        *r0 = n, *r1 = -1;
        for (a = 0; a < n; ++a)
            if (pg_dy(a) + PC_ROW_H > pg_off() && pg_dy(a) < pg_off() + GRID_VIEW_H) {
                if (a < *r0) *r0 = a;
                *r1 = a;
            }
        return;
    }
    *r0 = s / pg_row_h();
    *r1 = (s + GRID_VIEW_H - 1) / pg_row_h();
    if (s < 0) *r0 = 0;
    if (*r0 < 0) *r0 = 0;
    if (*r1 > n - 1) *r1 = n - 1;
}

/* ---------------------------------------------------------------------------
 * Texts and tiles
 */
static void pg_cat(char *out, unsigned size, const char *s);
static int pg_wide(unsigned *dst, int cap, const char *utf8);
static int pg_width(void *st, const unsigned *s);

/* The words of a feed's state, for its grey line: what the worker found this session, else when it was last refreshed. */
static const char *pg_status_word(int code) {
    switch (code) {
    case PN_NOWIFI:
        return TR("No Wi-Fi");
    case PN_NOCLOCK:
        return TR("Set the date first");
    case PN_NOCERT:
        return TR("Certificates missing");
    case PN_CERT:
        return TR("Certificate problem");
    case PN_NET:
        return TR("Can't connect");
    case PN_GONE:
        return TR("Feed not found");
    case PN_HTTP:
        return TR("Server error");
    case PN_NOTFEED:
        return TR("Not a podcast feed");
    case PN_STORAGE:
        return TR("Storage unavailable");
    case PN_NOFEED:
        return TR("Not available");
    default:
        return TR("Not enough memory");
    }
}

static void pg_cat(char *out, unsigned size, const char *s) {
    unsigned o = 0, k;
    while (out[o]) ++o;
    for (k = 0; s[k] && o + 1 < size; ++k) out[o++] = s[k];
    out[o] = 0;
}

/* The words of a download that failed: for an episode a 404 is "Not found" (a missing feed is another thing). */
static const char *pg_dl_word(int code) {
    switch (code) {
    case PN_GONE:
        return TR("Not found");
    case PN_CARDFULL:
        return TR("Card is full");
    case PN_NOTAUDIO:
        return TR("Not audio");
    case PN_QFULL:
        return TR("Queue is full");
    default:
        return pg_status_word(code);
    }
}

/* "Downloading 42%" when the length is known, else "Downloading 12 MB". */
static void pg_dl_progress(char *out, unsigned size, unsigned got, unsigned total) {
    char num[24];
    out[0] = 0;
    pg_cat(out, size, TR("Downloading"));
    if (total) {
        unsigned pct = (got >> 10) * 100 / ((total >> 10) ? (total >> 10) : 1);
        pc_fmt(num, sizeof num, " %d%", pct > 100 ? 100 : pct);
    } else
        pc_fmt(num, sizeof num, " %d MB", got >> 20);
    pg_cat(out, size, num);
}

/* The state line of an episode that is not on the card, when it has one: Waiting, Downloading 42%, Failed: <why>, or Paused (a .part from before). 0 when it is a plain remote episode (its date line). */
static int pg_dl_line(unsigned key, int part, char *out, unsigned size) {
    int code = 0, st;
    unsigned got = 0, total = 0;
    out[0] = 0;
    st = key ? pn_dl_state(key, &code, &got, &total) : PN_DL_NONE;
    if (st == PN_DL_ACTIVE)
        pg_dl_progress(out, size, got, total);
    else if (st == PN_DL_WAIT)
        pg_cat(out, size, TR("Waiting"));
    else if (st == PN_DL_FAILED) {
        pg_cat(out, size, TR("Failed"));
        pg_cat(out, size, ": ");
        pg_cat(out, size, pg_dl_word(code));
    } else if (part)
        pg_cat(out, size, TR("Paused"));
    return out[0] != 0;
}

static void pg_row_sub(int a, char *out, unsigned size);
static int pg_wide(unsigned *dst, int cap, const char *utf8);
static int pg_width(void *st, const unsigned *s);
static int pg_lines(void *st, unsigned *s, int n, int room, int maxl, pw_line_t *out);

/* The Downloads level's rows: display row a lives in slot ord[a] (the slot is its tile's key, so rows coming and going do not make the tiles lose their covers). On the Subscriptions page the order is the identity. */
static struct pg_dl *pg_row(int a) { return &pg.dls[pg.ord[a]]; }
static int pg_is_dld(int a) { return !pg.subs && a >= pg.nip; } /* a Downloaded row (the others are In Progress) */

/* A size in KB as the pages say it: "48 MB", from a GB "1.4 GB" (one decimal, the language's mark), from 10 GB "18 GB". */
static void pg_kb_text(char *out, unsigned size, unsigned kb) {
    out[0] = 0;
    if (kb >= 10u << 20)
        pc_fmt(out, size, TR("%d GB"), (kb + 524288u) >> 20);
    else if (kb >= 1048576u) {
        unsigned tenths = (kb + 52428u) / 104858u;
        pc_fmt2(out, size, TR("%d.%d GB"), tenths / 10, tenths % 10);
    } else
        pc_fmt(out, size, TR("%d MB"), kb ? (kb + 1023) >> 10 : 0);
}

/* The grey line of Downloaded row d, made for the tile: "show - date - size"; a partly played episode says "35m left" for the date. The show's name is what gives way (cut to the room the rest leaves, with an ellipsis); the
 * played check takes PS_BADGE_CHECK_W of the line's room. The wide text goes straight into the tile (grid_set takes UTF-8 and cuts at GRID_TEXT chars). */
static void pg_dld_text(const struct pg_dl *d, grid_tile_t *t) {
    char mid[56], size[24], tail[120];
    unsigned pos, len, whole, w[PG_TEXT_MAX], tw[GRID_TEXT];
    int n, room = LIST_TEXT_W - (pg.select ? SG_SEL_COL : 0), k, played = 0;
    pw_line_t ln;
    mid[0] = 0;
    if (d->hash) {
        int s = pc_state(d->hash, &pos, &len);
        whole = len ? len : d->dur;
        played = s == PC_DONE;
        if (s == PC_PROGRESS && whole > pos) pc_fmt(mid, sizeof mid, TR("%dm left"), (whole - pos + 59) / 60);
    }
    if (!mid[0] && d->pub) pc_when(d->pub, (unsigned)time((long *)0), mid, sizeof mid);
    pg_kb_text(size, sizeof size, d->kb);
    tail[0] = 0;
    if (mid[0]) pg_cat(tail, sizeof tail, " \xc2\xb7 "), pg_cat(tail, sizeof tail, mid); /* " · " */
    if (d->kb) pg_cat(tail, sizeof tail, " \xc2\xb7 "), pg_cat(tail, sizeof tail, size);
    if (played) room -= PS_BADGE_CHECK_W;
    grid_set(t, d->title, "", 0);
    n = pg_wide(tw, GRID_TEXT, tail);
    room -= pg_width(pg.st_sub, tw);
    k = 0;
    if (room >= 40) { /* the show's name, cut to what is left (the tail keeps its room) */
        n = pg_wide(w, PG_TEXT_MAX, pg.shows[d->si].title);
        if (pg_lines(pg.st_sub, w, n, room, 1, &ln) == 1)
            for (; k < ln.len && k < GRID_TEXT - 1; ++k) t->artist[k] = w[k];
    }
    for (n = k || !tw[0] ? 0 : 3; tw[n] && k < GRID_TEXT - 1; ++n)
        t->artist[k++] = tw[n]; /* (the leading " - " goes when the name is not there) */
    t->artist[k] = 0;
    t->fit = 0, t->tw = t->aw = 0;
}

/* The texts of row a's tile: the episode (or show) and its grey line. */
static void pg_row_text(int a, grid_tile_t *t) {
    if (pg_is_dld(a))
        pg_dld_text(pg_row(a), t);
    else {
        char sub[80];
        pg_row_sub(a, sub, sizeof sub);
        grid_set(t, pg_row(a)->title, sub, 0);
    }
}

/* The tile of row a of the Downloads level (the episode and its state line, the show's cover); a new tile gets its texts. The ring is keyed by slot and keeps the least recently used. */
static grid_tile_t *pg_tile(int a) {
    int fresh;
    grid_tile_t *t = grid_tile(&pg.g, pg.ord[a], 0, -1, &fresh);
    if (fresh) pg_row_text(a, t);
    return t;
}

/* The grey line under show s's cover on the Shows level. In this order: the words of the feed's last result when it failed this session (No Wi-Fi, Feed not found, ...); "N new" when the last refresh
 * found episodes; "Updated today" / "Updated 2d ago" from the last refresh (the show file's checked=); "Never refreshed" for a subscription never refreshed; "12 episodes" for a show that has
 * no feed (its files). */
static void pg_caption(const pc_show_t *s, char *out, unsigned size) {
    unsigned now = (unsigned)time((long *)0), fresh = 0;
    int code = 0, known = 0;
    out[0] = 0;
    if (s->feed[0]) known = pn_status(pc_hash(s->feed), &code, &fresh);
    if (!s->feed
             [0]) { /* a show that is only on the card: the marker and the count, or the marker alone where that is wider than the cover */
        char cnt[40];
        unsigned w[96];
        pc_fmt(cnt, sizeof cnt, TR(s->count == 1 ? "%d episode" : "%d episodes"), s->count);
        snprintf(out, size, "%s \xc2\xb7 %s", TR("Local"), cnt); /* " · " */
        pg_wide(w, 96, out);
        if (pg_width(pg.st[ST_GSUB], w) > GRID_COVER) {
            out[0] = 0;
            pg_cat(out, size, TR("Local"));
        }
    } else if (known && code != PN_OK)
        pg_cat(out, size, pg_status_word(code));
    else if (known && fresh)
        pc_fmt(out, size, TR("%d new"), fresh);
    else if (s->checked) {
        if (now >= s->checked && now - s->checked < 86400)
            pg_cat(out, size, TR("Updated today"));
        else {
            char when[48];
            unsigned w[96];
            pc_when(s->checked, now, when, sizeof when);
            snprintf(out, size, TR("Updated %s"), when);
            pg_wide(w, 96, out);
            if (pg_width(pg.st[ST_GSUB], w) >
                GRID_COVER) { /* a long language's "Updated <age>" is wider than the cover: the age alone (as the sheet's value does) */
                out[0] = 0;
                pg_cat(out, size, when);
            }
        }
    } else
        pg_cat(out, size, TR("Never refreshed"));
}

/* The grey line of row a of the Downloads-style level: a download's state, or on the Subscriptions page the show's caption (its feed status: "3 new", "Updated 2d ago", "No Wi-Fi", ...). */
static void pg_row_sub(int a, char *out, unsigned size) {
    if (pg.level == L_DLS && pg.subs)
        pg_caption(&pg.shows[pg_row(a)->si], out, size);
    else
        pg_dl_line(pg_row(a)->key, 1, out, size);
}

/* The Shows grid's cells in view, [*c0, *c1] (c1 < c0 for none). */
static void pg_gspan(int *c0, int *c1) {
    int r0 = (pg_off() - pg.y_grid) / GRID_PITCH, r1 = (pg_off() - pg.y_grid + GRID_VIEW_H - 1) / GRID_PITCH;
    if (pg_off() < pg.y_grid) r0 = 0;
    if (r0 < 0) r0 = 0;
    *c0 = r0 * GRID_COLS;
    *c1 = r1 * GRID_COLS + GRID_COLS - 1;
    if (*c1 > pg.nshows - 1) *c1 = pg.nshows - 1;
}

/* The tile of show a (a cell of the Shows grid); a new tile gets its title and caption. */
static grid_tile_t *pg_gtile(int a) {
    int c0, c1, fresh;
    grid_tile_t *t;
    pg_gspan(&c0, &c1);
    t = grid_tile(&pg.gg, a, c0 - 2 * GRID_COLS, c1 + 2 * GRID_COLS, &fresh);
    if (fresh) {
        char sub[80];
        pg_caption(&pg.shows[a], sub, sizeof sub);
        grid_set(t, pg.shows[a].title, sub, 0);
    }
    return t;
}

/* The captions made again (a refresh moved on, a day passed): the covers stay. */
static void pg_gretext(void) {
    int a;
    for (a = 0; a < pg.nshows; ++a) {
        grid_tile_t *t = grid_find(&pg.gg, a);
        char sub[80];
        if (!t) continue;
        pg_caption(&pg.shows[a], sub, sizeof sub);
        grid_set(t, pg.shows[a].title, sub, 0);
        t->fit = 0, t->tw = t->aw = 0;
    }
}

/* The texts of the Downloads rows made again (a step of progress, a place that moved): the covers stay. */
static void pg_dls_retext(void) {
    int a;
    for (a = 0; a < pg.nrows; ++a) {
        grid_tile_t *t = grid_find(&pg.g, pg.ord[a]);
        if (!t) continue;
        pg_row_text(a, t);
        t->fit = 0, t->tw = t->aw = 0;
    }
}

/* ---------------------------------------------------------------------------
 * The Show page's layouts (docs/modules/podcasts.md "The Show page"): the texts are wrapped once, from the glyphs' own advances (patch/pcwrap.c), when the page opens and when a cell first
 * paints; the states (pills, badges, colours) are read at every paint, from the model, the ring and the worker, so a step of progress needs no layout.
 */
static int pg_join(char *out, unsigned size, const char *dir, const char *file);

static int pg_wlen(const unsigned *s) {
    int n = 0;
    while (s[n]) ++n;
    return n;
}

/* The UTF-8 text as wide chars into dst (cap of them, the NUL included); its length. */
static int pg_wide(unsigned *dst, int cap, const char *utf8) {
    unsigned n = 0;
    while (utf8[n] && n < 4u * (unsigned)cap) ++n;
    tk_utf8_to_utf16_ex(utf8, n, dst, (unsigned)cap);
    return pg_wlen(dst);
}

static int pg_width(void *st, const unsigned *s) { return (int)(widget_measure_text(st, s) + 0.999f); }

/* The advance AWTK charges for each of the n chars of s in the style label st (the glyph's width and 1 px: docs/modules/text-width.md): one measure per char, the widths being additive. */
static void pg_adv(void *st, const unsigned *s, int n, unsigned short *adv) {
    unsigned t[2];
    int i;
    t[1] = 0;
    for (i = 0; i < n; ++i) {
        t[0] = s[i];
        adv[i] = (unsigned short)pg_width(st, t);
    }
}

/* s (n chars) in at most maxl lines of room px in the style st (patch/pcwrap.c: kinsoku, an ellipsis on the last line when text is left); the number of lines. */
static int pg_lines(void *st, unsigned *s, int n, int room, int maxl, pw_line_t *out) {
    unsigned short adv[PG_TEXT_MAX];
    unsigned e[2];
    e[0] = ELLIPSIS, e[1] = 0;
    if (n > PG_TEXT_MAX - 1) n = PG_TEXT_MAX - 1, s[n] = 0;
    pg_adv(st, s, n, adv);
    return pw_wrap(s, n, adv, room, maxl, pg_width(st, e), out);
}

/* The Show header's layout of the show open: the name, the pill, the description and the "Category - Author" line wrapped, the blocks' tops (docs/modules/podcasts.md for the rhythm). */
static void pg_hdr_make(void) {
    pg_hdr_t *h = pg.hdr;
    const pc_show_t *s = &pg.shows[pg.sel];
    char meta[PC_CAT + PC_AUTHOR + 8];
    int y, n, gap = PS_LATEST_GAP;
    if (!h) return;
    memset(h, 0, sizeof *h);
    n = pg_wide(h->name, PG_TITLE_MAX, s->title);
    h->nn = pg_lines(pg.st[ST_NAME], h->name, n, PS_NAME_W, PS_NAME_LINES, h->nl);
    y = PS_ART + PS_NAME_GAP;
    h->y_name = y;
    y += h->nn * PS_NAME_PITCH;
    h->collapse = y - PS_COLLAPSE_BACK;
    h->has_latest =
        pg.neps > 0 || pg.preview; /* (the preview has the Subscribe pill even when the feed lists no episode) */
    if (h->has_latest) {
        y += PS_LATEST_GAP;
        h->y_latest = y;
        y += PS_LATEST_H;
        gap = PS_DESC_GAP;
    }
    n = pg_wide(h->desc, PG_TEXT_MAX, s->desc);
    if (n) {
        y += gap;
        h->y_desc = y;
        h->nd = pg_lines(pg.st[ST_SEC], h->desc, n, PS_DESC_W, PS_DESC_LINES, h->dl);
        y += h->nd * PS_DESC_PITCH;
        gap = PS_META_GAP;
    }
    meta[0] = 0;
    pg_cat(meta, sizeof meta, s->category);
    if (s->category[0] && s->author[0]) pg_cat(meta, sizeof meta, " \xc2\xb7 "); /* " · " */
    pg_cat(meta, sizeof meta, s->author);
    n = pg_wide(h->meta, PG_TEXT_MAX, meta);
    if (n) {
        y += gap;
        h->y_meta = y;
        h->nm = pg_lines(pg.st[ST_META], h->meta, n, PS_DESC_W, 1, h->ml);
        y += PS_META_PITCH;
    }
    y += PS_HEAD_GAP;
    h->y_head = y;
    h->h = y + PS_HEAD_H;
}

/* The ring key of an episode: its file's, else the one its name would have (a played mark and a place belong to the path, so they survive a download and a removal). 0: no name. */
static unsigned pg_ep_hash(const pc_ep_t *e) {
    char path[PC_FILE * 3 + 24];
    if (e->hash) return e->hash;
    if (!e->file[0] || !pg_join(path, sizeof path, pg.shows[pg.sel].dir, e->file)) return 0;
    return pc_hash(path);
}

/* An episode's played state (PC_NEW / PC_PROGRESS / PC_DONE), also for one that is not on the card. */
static int pg_ep_state(const pc_ep_t *e, unsigned *pos, unsigned *len) {
    unsigned h = pg_ep_hash(e);
    *pos = *len = 0;
    return h ? pc_state(h, pos, len) : PC_NEW;
}

/* A cell's layout: the title and the description wrapped (two lines each), the date; made when it first paints, kept in the ring until the list is made again. */
static pg_cell_t *pg_cell(int a) {
    pg_cell_t *c;
    char date[48];
    int n, room = PS_CELL_W - (pg.select ? SG_SEL_COL : 0);
    if (!pg.cells || a < 0 || a >= pg.neps) return (pg_cell_t *)0;
    c = &pg.cells[a % PG_CELLS];
    if (c->idx == a + 1) return c;
    memset(c, 0, sizeof *c);
    c->idx = a + 1;
    n = pg_wide(c->title, PG_TITLE_MAX, pg.eps[a].title);
    c->tn = pg_lines(pg.st[ST_CTITLE], c->title, n, room, 2, c->tl);
    n = pg_wide(c->desc, PG_TEXT_MAX, pg.eps[a].desc);
    c->dn = pg_lines(pg.st[ST_CDESC], c->desc, n, room, 2, c->dl);
    date[0] = 0;
    if (pg.eps[a].pub) pc_when(pg.eps[a].pub, (unsigned)time((long *)0), date, sizeof date);
    c->datelen = pg_wide(c->date, 40, date);
    return c;
}

static void pg_cells_drop(void) {
    if (pg.cells) memset(pg.cells, 0, PG_CELLS * sizeof *pg.cells);
}

/* The kind and the words of an episode's state pill (the table in docs/modules/podcasts.md): on the card a play pill (the length, or what is left of a started one), not on the card a
 * download-type pill (its size; the ring and its percent while it downloads, Waiting, Paused, Retry). ring: the step of the progress ring. */
static void pg_pill_base(const pc_ep_t *e, int *kind, int *ring, char *out, unsigned size) {
    int code = 0, st;
    unsigned got = 0, total = 0, key;
    out[0] = 0;
    *ring = 0;
    if (e->state == PC_LOCAL) {
        unsigned pos, len, whole;
        int s = pc_state(e->hash, &pos, &len);
        whole = len ? len : e->dur;
        if (s == PC_PROGRESS && whole > pos) {
            *kind = PK_RESUME;
            pc_fmt(out, size, TR("%dm left"), (whole - pos + 59) / 60);
        } else {
            *kind = PK_PLAY;
            if (whole)
                pc_fmt(out, size, TR("%dm"), (whole + 59) / 60);
            else
                pg_cat(out, size, TR("Play"));
        }
        return;
    }
    key = e->file[0] ? pn_dl_key(pg.shows[pg.sel].dir, e->file) : 0;
    st = key ? pn_dl_state(key, &code, &got, &total) : PN_DL_NONE;
    if (st == PN_DL_ACTIVE) {
        *kind = PK_RING;
        if (total && total >= got) {
            unsigned pct = (got >> 10) * 100 / ((total >> 10) ? (total >> 10) : 1);
            if (pct > 100) pct = 100;
            *ring = (int)(pct * PA_RING_N / 100);
            if (*ring > PA_RING_N - 1) *ring = PA_RING_N - 1;
            pc_fmt(out, size, "%d%", pct);
        } else
            pc_fmt(out, size, TR("%d MB"), got >> 20);
    } else if (st == PN_DL_WAIT) {
        *kind = PK_RING;
        pg_cat(out, size, TR("Waiting"));
    } else if (st == PN_DL_FAILED) {
        *kind = PK_RETRY;
        pg_cat(out, size, TR("Retry"));
    } else if (e->state == PC_PART) {
        *kind = PK_PAUSED;
        pg_cat(out, size, TR("Paused"));
    } else {
        *kind = PK_DOWN;
        if (e->length)
            pc_fmt(out, size, TR("%d MB"), (e->length + 1048575) >> 20);
        else
            pg_cat(out, size, TR("Download"));
    }
}

static void pg_pill_of(const pc_ep_t *e, pg_pill_t *p) {
    char label[72];
    pg_pill_base(e, &p->kind, &p->ring, label, sizeof label);
    p->nlabel = pg_wide(p->label, PG_PILL_MAX, label);
    p->w = PS_PILL_PADL + PA_G_PX + PS_PILL_GAP + pg_width(pg.st[ST_PILL], p->label) + PS_PILL_PADR;
}

/* The Latest Episode pill of episode e (the newest): white with the dark play glyph when it is on the card (a started one too); else outlined, reading "Latest Episode - <the cell's pill>". */
static void pg_latest_of(const pc_ep_t *e, pg_pill_t *p) {
    char base[72], label[110];
    pg_pill_base(e, &p->kind, &p->ring, base, sizeof base);
    label[0] = 0;
    pg_cat(label, sizeof label, TR("Latest Episode"));
    if (e->state == PC_LOCAL)
        p->kind = PK_PLAY;
    else {
        pg_cat(label, sizeof label, " \xc2\xb7 "); /* " · " */
        pg_cat(label, sizeof label, base);
    }
    p->nlabel = pg_wide(p->label, PG_PILL_MAX, label);
    {
        void *st = pg.st[e->state == PC_LOCAL ? ST_LATEST : ST_LATESTW];
        pw_line_t ln;
        if (pg_lines(st, p->label, p->nlabel,
                     PS_LATEST_MAX - PS_LATEST_PADL - PS_LATEST_GLYPH - PS_LATEST_GAPG - PS_LATEST_PADR, 1, &ln) == 1) {
            p->nlabel =
                ln.len; /* (a long state word in a long language: the label ends in an ellipsis, the pill is at most PS_LATEST_MAX) */
            p->label[ln.len] = 0;
        }
        p->w = PS_LATEST_PADL + PS_LATEST_GLYPH + PS_LATEST_GAPG + pg_width(st, p->label) + PS_LATEST_PADR;
        p->tx = PS_LATEST_PADL + PS_LATEST_GLYPH + PS_LATEST_GAPG;
    }
}

/* The preview's pill: Subscribe (white, the dark label); no glyph, the label centred in a pill of at least PQ_SUB_MIN px. */
static void pg_sub_pill(pg_pill_t *p) {
    int tw;
    memset(p, 0, sizeof *p);
    p->kind = PK_SUB;
    p->nlabel = pg_wide(p->label, PG_PILL_MAX, TR("Subscribe"));
    tw = pg_width(pg.st[ST_LATEST], p->label);
    p->w = tw + PS_LATEST_PADL + PS_LATEST_PADR;
    if (p->w < PQ_SUB_MIN) p->w = PQ_SUB_MIN;
    p->tx = (p->w - tw) / 2;
}

/* The Show header's pill: the Latest Episode pill of the newest episode, or the preview's Subscribe. */
static void pg_latest(pg_pill_t *p) {
    if (pg.preview)
        pg_sub_pill(p);
    else
        pg_latest_of(&pg.eps[0], p);
}

/* ---------------------------------------------------------------------------
 * Paint
 */
static int pg_is_pick(int i) { return pg.pick[i >> 3] >> (i & 7) & 1; }
static int pg_can_pick(int i) { return pg.can[i >> 3] >> (i & 7) & 1; }

/* The select mark of a row that can be marked, wholly inside the window (as the Playlists page's). */
static void pg_mark(void *canvas, int i, int x, int y) {
    int src[4], dst[4];
    if (!pg.mark[0] || !pg_can_pick(i) || y < 0 || y + SG_MARK > GRID_VIEW_H) return;
    src[0] = src[1] = 0, src[2] = src[3] = SG_MARK;
    dst[0] = x, dst[1] = y, dst[2] = dst[3] = SG_MARK;
    canvas_draw_image(canvas, pg.mark[pg_is_pick(i)], src, dst);
}

/* The search level (docs/modules/podcasts.md "Search"): the field is widgets of the content view (ps_field); the result rows are the Downloads rows' look, a show's thumbnail, its name and its author in grey, from PQ_TOP.
 * A result with no feed address says "Not available" under its name and is dimmed (it takes no tap). The rows are the worker's record (pn_search_result): nothing is copied. */
static grid_tile_t *pg_stile(int a) {
    int fresh;
    grid_tile_t *t = grid_tile(&pg.g, a, 0, pg.srn - 1, &fresh);
    if (fresh) {
        const pj_result_t *r = pn_search_result(a);
        if (r) grid_set(t, r->name, r->feed[0] ? r->author : TR("Not available"), 0), t->nochev = !r->feed[0];
    }
    return t;
}

static grid_tile_t *pg_stile_of(void *ctx, int a) {
    (void)ctx;
    return pg_stile(a);
}

static void pg_paint_srch(void *canvas) {
    int r0, r1, r;
    pg_span(&r0, &r1);
    if (r1 < r0) return;
    grid_list_paint(canvas, &pg.g, pg.st_title, pg.st_sub, r0, r1, pg_off() - PQ_TOP, GRID_VIEW_H, pg.press, 0, 1,
                    pg_stile_of, (void *)0);
    for (r = r0; r <= r1; ++r) {
        const pj_result_t *p = pn_search_result(r);
        if (p && !p->feed[0])
            az_fill(canvas, 0, PQ_TOP + r * PC_ROW_H - pg_off(), PQ_TOP + (r + 1) * PC_ROW_H - 1 - pg_off(), PG_W,
                    PQ_DIM);
    }
}

/* pc_atlas (tools/mod_icons.py pc_atlas: the progress ring, the state glyphs, the badge, the "..." and the pills' ends) decoded WITH its alpha into a bitmap of ours, once: the image manager's copy is
 * dropped at once, as the covers' are. cc_decode would composite over black. NULL when it cannot be made (the Show level then paints no cells). */
static void *pg_rgba(const char *name, unsigned w, unsigned h) {
    static const unsigned char at[4][4] = BITMAP_RGBA_AT;
    unsigned bitmap[32], format, x, y, *px;
    const unsigned char *data;
    void *b = (void *)0;
    memset(bitmap, 0, sizeof bitmap);
    if (widget_load_image(pg.win, name, bitmap)) return (void *)0;
    format = (unsigned)(*(unsigned short *)((char *)bitmap + BITMAP_FORMAT)) - 1u;
    data =
        format < 4 && bitmap[0] == w && bitmap[1] == h ? bitmap_lock_buffer_for_read(bitmap) : (const unsigned char *)0;
    if (data) b = bitmap_create_ex(w, h, w * 4, BITMAP_RGBA8888);
    px = b ? (unsigned *)bitmap_lock_buffer_for_write(b) : (unsigned *)0;
    if (px && bitmap_get_line_length(b) == w * 4) {
        unsigned stride = bitmap_get_line_length(bitmap);
        for (y = 0; y < h; ++y)
            for (x = 0; x < w; ++x) {
                const unsigned char *s = data + y * stride + x * 4;
                px[y * w + x] = s[at[format][0]] | s[at[format][1]] << 8 | s[at[format][2]] << 16 |
                                (unsigned)s[at[format][3]] << 24;
            }
    } else if (b) {
        bitmap_destroy(b);
        b = (void *)0;
    }
    if (px) bitmap_unlock_buffer(b);
    if (data) bitmap_unlock_buffer(bitmap);
    widget_unload_image(pg.win, bitmap);
    return b;
}

static void *pg_atlas(void) {
    if (!pg.atlas) pg.atlas = pg_rgba("pc_atlas", PA_SIZE, PA_SIZE);
    return pg.atlas;
}

/* The Downloads row's tile (pod_ic_dltile, PA_TILE_PX square: an image of its own, like the other two, so the accent can tint its glyph by name) decoded the same way, once. */
static void *pg_dltile(void) {
    if (!pg.dltile) pg.dltile = pg_rgba("pod_ic_dltile", PA_TILE_PX, PA_TILE_PX);
    return pg.dltile;
}
/* The Subscriptions row's tile (pod_ic_subtile), the same. */
static void *pg_subtile(void) {
    if (!pg.subtile) pg.subtile = pg_rgba("pod_ic_subtile", PA_TILE_PX, PA_TILE_PX);
    return pg.subtile;
}
/* The Saved row's tile (pod_ic_savetile), the same. */
static void *pg_savetile(void) {
    if (!pg.savetile) pg.savetile = pg_rgba("pod_ic_savetile", PA_TILE_PX, PA_TILE_PX);
    return pg.savetile;
}

/* A w x h piece of the atlas from (sx, sy) at (x, y) of the view, cut by hand to the rows inside it (grid_blit's rule). */
static void pg_blit_from(void *canvas, void *bmp, int sx, int sy, int w, int h, int x, int y) {
    int src[4], dst[4], top = y < 0 ? -y : 0, bottom = y + h > GRID_VIEW_H ? GRID_VIEW_H - y : h;
    if (!bmp || bottom <= top) return;
    src[0] = sx, src[1] = sy + top, src[2] = w, src[3] = bottom - top;
    dst[0] = x, dst[1] = y + top, dst[2] = w, dst[3] = bottom - top;
    canvas_draw_image(canvas, bmp, src, dst);
}

static void pg_sprite(void *canvas, int sx, int sy, int w, int h, int x, int y) {
    pg_blit_from(canvas, pg.atlas, sx, sy, w, h, x, y);
}

/* The shared list chevron (POD_CHEV_W x POD_CHEV_H) at (x, y) of the view. */
static void pg_chev(void *canvas, int x, int y) {
    if (!pg.chev) pg.chev = pod_make_chevron();
    pg_blit_from(canvas, pg.chev, 0, 0, POD_CHEV_W, POD_CHEV_H, x, y);
}

static void pg_glyph(void *canvas, int idx, int x, int y) {
    pg_sprite(canvas, idx * PA_G_PX, PA_G_Y, PA_G_PX, PA_G_PX, x, y);
}

/* The glyph of a pill of kind k (the ring's step ring): the play triangle, the arrow, the pause bars, the retry arrow, a ring. */
static void pg_kind_glyph(void *canvas, int kind, int ring, int x, int y) {
    if (kind == PK_RING)
        pg_sprite(canvas, ring % PA_RING_COLS * PA_RING_PX, ring / PA_RING_COLS * PA_RING_PX, PA_RING_PX, PA_RING_PX, x,
                  y);
    else
        pg_glyph(canvas,
                 kind == PK_PLAY     ? PA_PLAY
                 : kind == PK_DOWN   ? PA_ARROW
                 : kind == PK_PAUSED ? PA_PAUSE
                                     : PA_RETRY,
                 x, y);
}

/* A stadium of w x h at (x, y): its ends are halves of the disc at atlas x ax (the ring or the filled disc), the body between them a fill (colour body: a filled pill) or two 2 px lines (outlined). */
static void pg_pill_shape(void *canvas, int x, int y, int w, int h, int ax, unsigned body, int outline) {
    int r = h / 2;
    pg_sprite(canvas, ax, PA_PILL_Y, r, h, x, y);
    pg_sprite(canvas, ax + r, PA_PILL_Y, r, h, x + w - r, y);
    if (!outline) {
        az_fill(canvas, x + r, y, y + h, w - 2 * r, body);
    } else {
        az_fill(canvas, x + r, y, y + 2, w - 2 * r, body);
        az_fill(canvas, x + r, y + h - 2, y + h, w - 2 * r, body);
    }
}

/* A cell's state pill at (x, y): filled for the play-type kinds, outlined for the download-type ones, the glyph in the pad. The label is drawn in the text pass. */
static void pg_pill_paint(void *canvas, int x, int y, const pg_pill_t *p) {
    int filled = p->kind <= PK_RESUME;
    pg_pill_shape(canvas, x, y, p->w, PS_PILL_H, filled ? PA_PILLF_X : PA_PILLO_X,
                  ((unsigned)(filled ? PA_FILL_A : PA_RING_A) << 24) | 0xffffffu, !filled);
    pg_kind_glyph(canvas, p->kind, p->ring, x + PS_PILL_PADL, y + (PS_PILL_H - PA_G_PX) / 2);
}

/* The Latest Episode pill at (x, y): white with the dark play glyph, or outlined with the state's glyph. */
static void pg_latest_paint(void *canvas, int x, int y, const pg_pill_t *p) {
    int white = p->kind == PK_PLAY || p->kind == PK_SUB, gx = x + PS_LATEST_PADL - (PA_G_PX - PS_LATEST_GLYPH) / 2,
        gy = y + (PS_LATEST_H - PA_G_PX) / 2;
    pg_pill_shape(canvas, x, y, p->w, PS_LATEST_H, white ? PA_PILLW_X : PA_PILLR_X,
                  white ? 0xffffffffu : (((unsigned)PA_RING_A << 24) | 0xffffffu), !white);
    if (p->kind >= PK_SUB) return; /* (Subscribe and Subscribed have no glyph) */
    if (white)
        pg_glyph(canvas, PA_PLAYK, gx, gy);
    else
        pg_kind_glyph(canvas, p->kind, p->ring, gx, gy);
}

/* A text drawn wholly inside the view only (every text of the payload's pages: AWTK does not clip it). The canvas has the style. */
static void pg_text(void *canvas, const unsigned *s, int n, int x, int y, int w, int h) {
    int rect[4];
    rect[0] = x, rect[1] = y, rect[2] = w, rect[3] = h;
    if (n > 0 && y >= 0 && y + h <= GRID_VIEW_H) canvas_draw_text_in_rect(canvas, s, (unsigned)n, rect);
}

static void pg_style(void *canvas, int st) { widget_prepare_text_style(pg.st[st], canvas); }

/* The navbar's fade on the Show level, over the first rows while the list is scrolled: the page's colour (the tone under the gradient, black on a page without a cover) with nb_fade's eased alpha
 * (tools/mod_icons.py nb_fade_alpha), so the rows dissolve under the bar as they do on the other pages; the bar itself is the page behind it. */
static void pg_paint_fade(void *canvas) {
    static const unsigned char alpha[PG_FADE_H] = {233, 193, 158, 128, 102, 80, 62, 47, 35, 25,
                                                   17,  12,  7,   4,   2,   1,  0,  0,  0,  0};
    int y;
    for (y = 0; y < PG_FADE_H; ++y)
        if (alpha[y])
            az_fill(canvas, 0, y, y + 1, PG_W,
                    ((unsigned)alpha[y] << 24) | (pg.tint ? pod_shade(pg.tint, (unsigned)(PG_LIST_Y + y), AH_TINT_A_TOP,
                                                                      AH_TINT_A_BOT, AH_TINT_ROWS)
                                                          : 0));
}

#define PG_SEEN 6 /* cells the view can touch at once (400 / PS_CELL_H rounded up, plus a margin) */

static void pg_paint_eps(void *canvas) {
    int r0, r1, r, k, off = pg_off(), sx = pg.select ? SG_SEL_COL : 0, hy = pg_top(), played[PG_SEEN], datex[PG_SEEN];
    pg_hdr_t *h = pg.hdr;
    pg_pill_t pill[PG_SEEN], lp;
    if (!h || !pg.hg.tiles || !pg_atlas()) return;
    memset(&lp, 0, sizeof lp);
    pg_span(&r0, &r1);
    if (r1 - r0 + 1 > PG_SEEN) r1 = r0 + PG_SEEN - 1;
    if (off < hy) {
        grid_blit(canvas, &pg.hg, &pg.hg.tiles[0], PS_ART_X, -off, GRID_VIEW_H);
        if (h->has_latest) {
            pg_latest(&lp);
            pg_latest_paint(canvas, (PG_W - lp.w) / 2, h->y_latest - off, &lp);
        }
    }
    for (r = r0; r <= r1; ++r) { /* the cells' fills and pictures */
        const pc_ep_t *e = &pg.eps[r];
        unsigned pos, len;
        int y = hy + r * pg_cell_h() - off, x = PS_CELL_X + sx, i = r - r0;
        played[i] = pg_ep_state(e, &pos, &len) == PC_DONE;
        pg_pill_of(e, &pill[i]);
        if (pg.press == r + 1 && !pg.select) az_fill(canvas, 0, y, y + pg_cell_h() - 1, PG_W, 0x30ffffffu);
        az_fill(canvas, PS_CELL_X, y + pg_cell_h() - 1, y + pg_cell_h(), PG_W - PS_CELL_X, 0x22ffffffu);
        if (pg.select) pg_mark(canvas, r, PS_CELL_X + (SG_SEL_COL - 6 - SG_MARK) / 2, y + (pg_cell_h() - SG_MARK) / 2);
        if (played[i]) { /* the date line's badges: a check when played, the disc when the file is on the card */
            pg_glyph(canvas, PA_CHECK, x - 1, y + PS_DATE_Y + PS_DATE_H / 2 - PA_G_PX / 2);
            x += PS_BADGE_CHECK_W;
        }
        if (e->state == PC_LOCAL) {
            pg_sprite(canvas, PA_BADGE_X, PA_DOTS_Y, PA_BADGE_PX, PA_BADGE_PX, x,
                      y + PS_DATE_Y + PS_DATE_H / 2 - PA_BADGE_PX / 2);
            x += PS_BADGE_DISC_W;
        }
        datex[i] = x;
        if (!pg.preview) pg_pill_paint(canvas, PS_CELL_X + sx, y + PS_PILL_Y, &pill[i]);
        if (!pg.select && !pg.preview)
            pg_sprite(canvas, 0, PA_DOTS_Y, PA_DOTS_PX, PA_DOTS_PX, PS_DOTS_CX - PA_DOTS_PX / 2,
                      y + PS_PILL_Y + PS_PILL_H / 2 - PA_DOTS_PX / 2);
    }
    if (off < hy) { /* the header's texts */
        pg_style(canvas, ST_NAME);
        for (k = 0; k < h->nn; ++k)
            pg_text(canvas, h->name + h->nl[k].start, h->nl[k].len, PS_NAME_X, h->y_name + k * PS_NAME_PITCH - off,
                    PS_NAME_W, PS_NAME_PITCH);
        if (h->has_latest) {
            int x0 = (PG_W - lp.w) / 2, px = x0 + lp.tx;
            pg_style(canvas, lp.kind == PK_PLAY || lp.kind == PK_SUB ? ST_LATEST : ST_LATESTW);
            pg_text(canvas, lp.label, lp.nlabel, px, h->y_latest - off, x0 + lp.w - px, PS_LATEST_H);
        }
        pg_style(canvas, ST_SEC);
        for (k = 0; k < h->nd; ++k)
            pg_text(canvas, h->desc + h->dl[k].start, h->dl[k].len, PS_DESC_X, h->y_desc + k * PS_DESC_PITCH - off,
                    PS_DESC_W, PS_DESC_PITCH);
        pg_style(canvas, ST_META);
        if (h->nm)
            pg_text(canvas, h->meta + h->ml[0].start, h->ml[0].len, PS_DESC_X, h->y_meta - off, PS_DESC_W,
                    PS_META_PITCH);
        pg_style(canvas, ST_HEAD);
        {
            unsigned head[40];
            int n = pg_wide(head, 40, TR("Episodes"));
            pg_text(canvas, head, n, PS_DESC_X, h->y_head - off, PS_DESC_W, PS_HEAD_H - 6);
        }
    }
    for (k = 0; k < 5; ++k) { /* the cells' texts, one style at a time */
        pg_style(canvas, k == 0 ? ST_DATE : k == 1 ? ST_CTITLE : k == 2 ? ST_CDIM : k == 3 ? ST_CDESC : ST_PILL);
        for (r = r0; r <= r1; ++r) {
            pg_cell_t *c = pg_cell(r);
            int y = hy + r * pg_cell_h() - off, i = r - r0, j;
            if (!c) continue;
            if (k == 0)
                pg_text(canvas, c->date, c->datelen, datex[i], y + PS_DATE_Y, PS_CELL_X + PS_CELL_W - datex[i],
                        PS_DATE_H);
            else if (k == 1 + played[i])
                for (j = 0; j < c->tn; ++j)
                    pg_text(canvas, c->title + c->tl[j].start, c->tl[j].len, PS_CELL_X + sx,
                            y + PS_TITLE_Y + j * PS_TITLE_PITCH, PS_CELL_W - sx, PS_TITLE_PITCH);
            else if (k == 3)
                for (j = 0; j < c->dn; ++j)
                    pg_text(canvas, c->desc + c->dl[j].start, c->dl[j].len, PS_CELL_X + sx,
                            y + PS_CDESC_Y + j * PS_CDESC_PITCH, PS_CELL_W - sx, PS_CDESC_PITCH);
            else if (k == 4 && !pg.preview)
                pg_text(canvas, pill[i].label, pill[i].nlabel, PS_CELL_X + sx + PS_PILL_PADL + PA_G_PX + PS_PILL_GAP,
                        y + PS_PILL_Y, pill[i].w - PS_PILL_PADL - PA_G_PX - PS_PILL_GAP, PS_PILL_H);
        }
    }
    if (off > 0) pg_paint_fade(canvas);
}

/* The episode page (docs/modules/podcasts.md "The episode page"): the date line (with the size) and the cell's badges, the title, the show row (a small cover, the name, a chevron: not in a preview), the cell's
 * state pill and "..." (not in a preview), the description. The texts are pcdetail.c's; the states are read at every paint, as the cells' are. The page is black, with the plain fade under the navbar. */
static void pg_paint_det(void *canvas) {
    const pd_t *d = pg.pd;
    const pc_ep_t *e;
    pg_pill_t pl;
    unsigned pos, len;
    int off = pg_off(), x = PD_X, y;
    if (!d || !pg.hg.tiles || !pg_atlas() || pg.det > pg.neps) return;
    e = &pg.eps[pg.det - 1];
    y = d->y_show - off + (PD_SHOW_H - PD_COVER) / 2;
    grid_blit(canvas, &pg.g, &pg.g.tiles[0], PD_X, y, GRID_VIEW_H);
    if (d->y_pill) pg_chev(canvas, PD_CHEV_X, d->y_show - off + (PD_SHOW_H - POD_CHEV_H) / 2);
    y = d->y_date - off;
    if (pg_ep_state(e, &pos, &len) == PC_DONE) {
        pg_glyph(canvas, PA_CHECK, x - 1, y + PD_DATE_H / 2 - PA_G_PX / 2);
        x += PS_BADGE_CHECK_W;
    }
    if (e->state == PC_LOCAL) {
        pg_sprite(canvas, PA_BADGE_X, PA_DOTS_Y, PA_BADGE_PX, PA_BADGE_PX, x, y + PD_DATE_H / 2 - PA_BADGE_PX / 2);
        x += PS_BADGE_DISC_W;
    }
    pd_paint(canvas, d, off, pg.st[ST_DATE], pg.st[ST_HEAD], pg.st[ST_META], pg.st[ST_SEC], x);
    if (d->y_pill) {
        y = d->y_pill - off;
        pg_pill_of(e, &pl);
        pg_pill_paint(canvas, PD_X, y, &pl);
        pg_sprite(canvas, 0, PA_DOTS_Y, PA_DOTS_PX, PA_DOTS_PX, PS_DOTS_CX - PA_DOTS_PX / 2,
                  y + PS_PILL_H / 2 - PA_DOTS_PX / 2);
        pg_style(canvas, ST_PILL);
        pg_text(canvas, pl.label, pl.nlabel, PD_X + PS_PILL_PADL + PA_G_PX + PS_PILL_GAP, y,
                pl.w - PS_PILL_PADL - PA_G_PX - PS_PILL_GAP, PS_PILL_H);
    }
}

/* ---------------------------------------------------------------------------
 * The Shows level (Apple Podcasts style, docs/modules/podcasts.md "The Shows page"): the large title (a label of the asset, a child of the content view), then painted by the content view: the refresh line,
 * Continue Listening (a static row of at most PP_SHELF_MAX covers), the Downloads row, the "Shows" header and the grid of every show. The numbers are PP_* of patch/offsets.inc (tools/pod_show.py shows_layout).
 */
typedef struct { /* the refresh line: the grey part, then the white "Refresh" (nw 0: none) */
    unsigned grey[96], white[24];
    int ng, nw, gw, ww;
} pg_line_t;

static int pg_last_checked(void) {
    unsigned last = 0;
    int i;
    for (i = 0; i < pg.nshows; ++i)
        if (pg.shows[i].feed[0] && pg.shows[i].checked > last) last = pg.shows[i].checked;
    return (int)last;
}

/* The refresh line from the worker's state: "Refreshing 2/5…" while it runs, "Waiting" while the downloads pause for it, else "Updated 1h ago · " (or "Never refreshed · ") and the word Refresh. */
static void pg_line_make(pg_line_t *l) {
    char buf[120];
    unsigned last = (unsigned)pg_last_checked(), now = (unsigned)time((long *)0);
    memset(l, 0, sizeof *l);
    if (pn_busy() && !pg.rpend) {
        int done, total;
        pn_progress(&done, &total);
        pc_fmt2(buf, sizeof buf, TR("Refreshing %d/%d…"), (unsigned)done, (unsigned)total);
    } else if (pg.rpend) {
        buf[0] = 0;
        pg_cat(buf, sizeof buf, TR("Waiting"));
    } else {
        char when[48];
        const char *word = TR("Refresh");
        int k;
        l->nw = pg_wide(l->white, 24, word);
        l->ww = pg_width(pg.st[ST_LINE], l->white);
        for (k = 0; k < 2;
             ++k) { /* "Updated 1h ago · ", else "1h ago · " when a long language leaves no room for the whole */
            buf[0] = 0;
            if (!last)
                pg_cat(buf, sizeof buf, TR("Never refreshed"));
            else {
                pc_when(last, now, when, sizeof when);
                if (!k)
                    snprintf(buf, sizeof buf, TR("Updated %s"), when);
                else
                    pg_cat(buf, sizeof buf, when);
            }
            pg_cat(buf, sizeof buf, " \xc2\xb7 "); /* " · " */
            l->ng = pg_wide(l->grey, 96, buf);
            l->gw = pg_width(pg.st[ST_META], l->grey);
            if (l->gw + l->ww <= PG_W - 2 * PP_LINE_X || !last) break;
        }
        return;
    }
    l->ng = pg_wide(l->grey, 96, buf);
    l->gw = pg_width(pg.st[ST_META], l->grey);
}

/* Where the blocks of the Shows level are (content y) and how tall the content is: after the title the refresh line (when a show has a feed), Continue Listening (when something is partly played),
 * the Downloads row (while something is queued), a header "Shows" (only when one of those shows) and the grid. */
static void pg_home_layout(void) {
    int y = PP_LINE_Y + (pg.has_line ? PP_LINE_PITCH : PP_NOLINE_PITCH);
    pg.y_shelf = pg.y_sub = pg.y_sav = 0;
    if (pg.ncont) {
        pg.y_shelf = y;
        y += PP_HEAD_PITCH + PP_SHELF_PITCH_Y + PP_SEC_GAP;
    }
    pg.y_shows = y;
    y += PP_HEAD_PITCH;
    pg.y_grid = y;
    y += (pg.nshows + GRID_COLS - 1) / GRID_COLS * GRID_PITCH;
    pg.y_dl =
        y + (pg.nshows
                 ? PP_LIB_GAP
                 : 0); /* the Library rows close the page: Downloads always, Subscriptions while a show has a feed */
    y = pg.y_dl + PC_ROW_H;
    if (pg.has_line) {
        pg.y_sub = y;
        y += PC_ROW_H;
    }
    pg.y_sav = y; /* Saved closes the Library rows */
    y += PC_ROW_H;
    pg.home_h = y + PP_BOTTOM;
}

/* The "35m left" of a Continue Listening item, read at every paint from the ring (a place moves while it plays); "Play" for an item that is no longer partly played (the next tick makes the row again). */
static void pg_cont_left(const struct pg_item *it, char *out, unsigned size) {
    unsigned pos, len;
    out[0] = 0;
    if (pc_state(it->hash, &pos, &len) == PC_PROGRESS && len > pos)
        pc_fmt(out, size, TR("%dm left"), (len - pos + 59) / 60);
    else
        pg_cat(out, size, TR("Play"));
}

static void pg_paint_text_at(void *canvas, void *style, const unsigned *s, int n, int x, int y, int w, int h) {
    widget_prepare_text_style(style, canvas);
    pg_text(canvas, s, n, x, y, w, h);
}

static void pg_paint_head(void *canvas, int top, const char *key, int x) {
    unsigned t[48];
    int n = pg_wide(t, 48, TR(key));
    pg_paint_text_at(canvas, pg.st[ST_SECH], t, n, x, top, PG_W - 2 * x, PP_HEAD_H);
}

static int pg_fits(void *st, const char *text, int room) {
    unsigned w[96];
    pg_wide(w, 96, text);
    return pg_width(st, w) <= room;
}

/* The Downloads row's grey line: what the worker is doing (Downloading 42%, N waiting), else N paused (a .part nothing holds, or a failed download: a tap on its row goes on), else "12 episodes - 1.4 GB" (the size
 * once the totals scan has finished; the count alone where that is too wide), else No downloads. */
static void pg_lib_dl_sub(char *out, unsigned size) {
    unsigned got = 0, total = 0, files = 0, failed = 0, key;
    int waiting = pn_dl_waiting(), code = 0, i;
    char dir[PC_FILE], file[PC_FILE];
    out[0] = 0;
    if (pn_dl_current(&got, &total)) {
        pg_dl_progress(out, size, got, total);
        return;
    }
    if (waiting > 0) {
        pc_fmt(out, size, TR("%d waiting"), (unsigned)waiting);
        return;
    }
    for (i = 0; (key = pn_dl_listed(i, dir, file, &code)) != 0; ++i)
        failed += pn_dl_state(key, &code, &got, &total) == PN_DL_FAILED;
    if (pg.tot_parts + failed) {
        pc_fmt(out, size, TR("%d paused"), pg.tot_parts + failed);
        return;
    }
    for (i = 0; i < pg.nshows; ++i) files += pg.shows[i].count;
    if (!files) {
        pg_cat(out, size, TR("No downloads"));
        return;
    }
    pc_fmt(out, size, TR(files == 1 ? "%d episode" : "%d episodes"), files);
    if (pg.tot_ok && pg.tot_kb) {
        char sz[24], full[96];
        pg_kb_text(sz, sizeof sz, pg.tot_kb);
        snprintf(full, sizeof full, "%s \xc2\xb7 %s", out, sz); /* " · " */
        if (pg_fits(pg.st_sub, full, PP_DL_TEXT_W)) out[0] = 0, pg_cat(out, size, full);
    }
}

/* The Subscriptions row's grey line: "8 shows" (the shows with a feed address). */
static void pg_lib_subs_sub(char *out, unsigned size) {
    unsigned n = 0;
    int i;
    for (i = 0; i < pg.nshows; ++i) n += pg.shows[i].feed[0] != 0;
    pc_fmt(out, size, TR(n == 1 ? "%d show" : "%d shows"), n);
}

/* The Saved row's grey line: how many episodes (pg_saved_load's count, read when the Shows level was made). */
static void pg_lib_saved_sub(char *out, unsigned size) {
    out[0] = 0;
    if (!pg.sv_n)
        pg_cat(out, size, TR("No saved episodes"));
    else
        pc_fmt(out, size, TR(pg.sv_n == 1 ? "%d episode" : "%d episodes"), (unsigned)pg.sv_n);
}

/* The top of Library row i (Downloads, Subscriptions, Saved), 0 when the row is not there. */
static int pg_ylib(int i) { return i == 0 ? pg.y_dl : i == 1 ? pg.y_sub : pg.y_sav; }

static void pg_paint_home(void *canvas) {
    int off = pg_off(), i, a, c0, c1, y;
    pg_line_t ln;
    if (!pg.gg.tiles || !pg_atlas()) return;
    /* fills and pictures */
    if (pg.ncont && pg.sg.tiles)
        for (i = 0; i < pg.ncont; ++i) {
            int fresh;
            grid_tile_t *t = grid_tile(&pg.sg, i, 0, PP_SHELF_MAX - 1, &fresh);
            grid_blit(canvas, &pg.sg, t, PP_SHELF_X + i * PP_SHELF_PITCH, pg.y_shelf + PP_HEAD_PITCH - off,
                      GRID_VIEW_H);
            /* the round play disc at the cover's bottom right (a tap anywhere on the item resumes) */
            pg_sprite(canvas, PA_PLAYB_X, PA_PLAYB_Y, PA_PLAYB_PX, PA_PLAYB_PX,
                      PP_SHELF_X + i * PP_SHELF_PITCH + PP_SHELF_ART - PP_SHELF_PLAY_INSET - PA_PLAYB_PX,
                      pg.y_shelf + PP_HEAD_PITCH + PP_SHELF_ART - PP_SHELF_PLAY_INSET - PA_PLAYB_PX - off);
        }
    for (i = 0; i < 3;
         ++i) { /* the Library rows (Downloads, Subscriptions, Saved): a tile, a chevron, a hairline from the text */
        if (!pg_ylib(i)) continue;
        y = pg_ylib(i) - off;
        if (pg.press == i + 1 && !pg.select) az_fill(canvas, 0, y, y + PC_ROW_H - 1, PG_W, LIST_PRESS);
        pg_blit_from(canvas,
                     i == 2 ? pg_savetile()
                     : i    ? pg_subtile()
                            : pg_dltile(),
                     0, 0, PA_TILE_PX, PA_TILE_PX, PP_DL_TILE_X, y + PP_DL_TILE_Y);
        pg_chev(canvas, PP_DL_CHEV_X, y + (PC_ROW_H - 1 - POD_CHEV_H) / 2);
        az_fill(canvas, PP_DL_TEXT_X, y + PC_ROW_H - 1, y + PC_ROW_H, PG_W - PP_DL_TEXT_X, LIST_HAIR);
    }
    pg_gspan(&c0, &c1);
    for (a = c0; a <= c1; ++a)
        grid_blit(canvas, &pg.gg, pg_gtile(a), grid_cell_x(a), grid_cell_y(a, pg.y_grid - off), GRID_VIEW_H);
    /* the refresh line */
    if (pg.has_line) {
        int ty = PP_LINE_Y - off;
        pg_line_make(&ln);
        pg_paint_text_at(canvas, pg.st[ST_META], ln.grey, ln.ng, PP_LINE_X, ty, ln.gw + 4, PP_LINE_H);
        if (ln.nw)
            pg_paint_text_at(canvas, pg.st[ST_LINE], ln.white, ln.nw, PP_LINE_X + ln.gw, ty, ln.ww + 4, PP_LINE_H);
    }
    /* Continue Listening: the header, then each item's title and what is left */
    if (pg.ncont) {
        pg_paint_head(canvas, pg.y_shelf - off, "Continue Listening", PP_HEAD_X);
        for (i = 0; i < pg.ncont; ++i)
            pg_paint_text_at(canvas, pg.st[ST_STITLE], pg.cont[i].title, pg.cont[i].tn, PP_SHELF_X + i * PP_SHELF_PITCH,
                             pg.y_shelf + PP_HEAD_PITCH + PP_SHELF_TITLE_Y - off, PP_SHELF_W, PP_SHELF_TITLE_H);
        for (i = 0; i < pg.ncont; ++i) {
            char left[48];
            unsigned w[48];
            pw_line_t cut;
            int n;
            pg_cont_left(&pg.cont[i], left, sizeof left);
            n = pg_wide(w, 48, left);
            n = pg_lines(pg.st[ST_SLEFT], w, n, PP_SHELF_W, 1, &cut) == 1
                    ? cut.len
                    : 0; /* (a long language's "999m left" ends in an ellipsis rather than run into the next item) */
            pg_paint_text_at(canvas, pg.st[ST_SLEFT], w, n, PP_SHELF_X + i * PP_SHELF_PITCH,
                             pg.y_shelf + PP_HEAD_PITCH + PP_SHELF_LEFT_Y - off, PP_SHELF_W, PP_SHELF_LEFT_H);
        }
    }
    /* the Library rows' texts: the title and the grey line of each */
    for (i = 0; i < 3; ++i) {
        char sub[96];
        unsigned w[PG_TITLE_MAX];
        int n;
        if (!pg_ylib(i)) continue;
        y = pg_ylib(i) - off;
        if (i == 2)
            pg_lib_saved_sub(sub, sizeof sub);
        else if (i)
            pg_lib_subs_sub(sub, sizeof sub);
        else
            pg_lib_dl_sub(sub, sizeof sub);
        n = pg_wide(w, PG_TITLE_MAX, TR(i == 2 ? "Saved" : i ? "Subscriptions" : "Downloads"));
        pg_paint_text_at(canvas, pg.st_title, w, n, PP_DL_TEXT_X, y + LIST_TITLE_Y, PP_DL_TEXT_W, LIST_TITLE_H);
        n = pg_wide(w, PG_TITLE_MAX, sub);
        pg_paint_text_at(canvas, pg.st_sub, w, n, PP_DL_TEXT_X, y + LIST_SUB_Y, PP_DL_TEXT_W, LIST_SUB_H);
    }
    if (pg.y_shows) pg_paint_head(canvas, pg.y_shows - off, "Shows", PP_SHOWS_X);
    /* the grid's titles, then its grey lines (the Albums grid's styles) */
    for (i = 0; i < 2; ++i) {
        pg_style(canvas, i ? ST_GSUB : ST_GTITLE);
        for (a = c0; a <= c1; ++a)
            grid_text(canvas, pg_gtile(a), i, grid_cell_x(a),
                      grid_cell_y(a, pg.y_grid - off) + GRID_COVER + GRID_TITLE_GAP + (i ? GRID_TITLE_H : 0),
                      GRID_COVER, i ? GRID_SUB_H : GRID_TITLE_H, GRID_VIEW_H);
    }
}

/* The Downloads page's storage line (docs/modules/podcasts.md "The Downloads page"): "12 episodes - 1.4 GB - 18 GB free", the shorter forms (the size and the free space; the free space) where that is wider than the page's
 * margins. The counts are there once the scan has finished (they are the whole card's, the rows' cap aside). */
static void pg_dls_line(char *out, unsigned size) {
    int k;
    for (k = 0; k < 3; ++k) {
        char part[48];
        out[0] = 0;
        if (k < 1 && pg.dtot_n && !pg.dscan_on) {
            pc_fmt(part, sizeof part, TR(pg.dtot_n == 1 ? "%d episode" : "%d episodes"), pg.dtot_n);
            pg_cat(out, size, part);
        }
        if (k < 2 && pg.dtot_kb && !pg.dscan_on) {
            if (out[0]) pg_cat(out, size, " \xc2\xb7 "); /* " · " */
            pg_kb_text(part, sizeof part, pg.dtot_kb);
            pg_cat(out, size, part);
        }
        if (pg.dfree_ok) {
            char kb[24];
            if (out[0]) pg_cat(out, size, " \xc2\xb7 ");
            pg_kb_text(kb, sizeof kb, pg.dfree_kb);
            snprintf(part, sizeof part, TR("%s free"), kb);
            pg_cat(out, size, part);
        }
        if (pg_fits(pg.st[ST_META], out, PG_W - 2 * PP_LINE_X)) return;
    }
}

static int pg_played_row(int a) {
    unsigned pos, len;
    return pg_is_dld(a) && pg_row(a)->hash && pc_state(pg_row(a)->hash, &pos, &len) == PC_DONE;
}

/* The Downloads level: the storage line and the section headers, then the rows (the list rows of the stock Albums list mode, painted here: a played Downloaded row has the check before its grey line, as the Show page's cells have).
 * In select mode a mark column opens left of the covers. */
static void pg_paint_dls(void *canvas) {
    int r0, r1, r, pass, off = pg_off(), shift = pg.select ? SG_SEL_COL : 0;
    pg_atlas(); /* (the played check) */
    if (!pg.subs && !pg.saved) {
        char line[120];
        unsigned w[120];
        int n;
        pg_dls_line(line, sizeof line);
        n = pg_wide(w, 120, line);
        if (n)
            pg_paint_text_at(canvas, pg.st[ST_META], w, n, PP_LINE_X, PDL_LINE_Y - off, PG_W - 2 * PP_LINE_X,
                             PP_LINE_H);
        if (pg.nip) pg_paint_head(canvas, pg_dhead(0) - off, "In Progress", PP_SHOWS_X);
        if (pg.nd) pg_paint_head(canvas, pg_dhead(1) - off, "Downloaded", PP_SHOWS_X);
    }
    pg_span(&r0, &r1);
    for (r = r0; r <= r1; ++r) {
        grid_tile_t *t = pg_tile(r);
        int y = pg_dy(r) - off;
        if (!pg.select && pg.press == pg.ord[r] + 1) az_fill(canvas, 0, y, y + PC_ROW_H - 1, PG_W, LIST_PRESS);
        grid_blit(canvas, &pg.g, t, LIST_ART_X + shift, y + LIST_ART_Y, GRID_VIEW_H);
        az_fill(canvas, 0, y + PC_ROW_H - 1, y + PC_ROW_H, PG_W, LIST_HAIR);
    }
    for (pass = 0; pass < 2; ++pass) { /* titles, then grey lines: one text style at a time */
        widget_prepare_text_style(pass ? pg.st_sub : pg.st_title, canvas);
        for (r = r0; r <= r1; ++r) {
            int x = LIST_TEXT_X + shift, w = LIST_TEXT_W - shift;
            if (pass && pg_played_row(r)) x += PS_BADGE_CHECK_W, w -= PS_BADGE_CHECK_W;
            grid_text(canvas, pg_tile(r), pass, x, pg_dy(r) - off + (pass ? LIST_SUB_Y : LIST_TITLE_Y), w,
                      pass ? LIST_SUB_H : LIST_TITLE_H, GRID_VIEW_H);
        }
    }
    for (r = r0; r <= r1; ++r) {
        int y = pg_dy(r) - off;
        if (pg_played_row(r))
            pg_glyph(canvas, PA_CHECK, LIST_TEXT_X + shift - 1, y + LIST_SUB_Y + LIST_SUB_H / 2 - PA_G_PX / 2);
        if (pg.select) pg_mark(canvas, r, LIST_ART_X + (SG_SEL_COL - 6 - SG_MARK) / 2, y + (PC_ROW_H - SG_MARK) / 2);
    }
}

/* The empty page's hint: grey, wrapped to the margins (pg_hint), under the header. */
static void pg_paint_hint(void *canvas, int off) {
    const char *key = pg_hint();
    unsigned t[160];
    pw_line_t ln[4];
    int n, k, nl;
    if (!key) return;
    n = pg_wide(t, 160, TR(key));
    nl = pg_lines(pg.st[ST_CDIM], t, n, PG_W - 2 * PP_LINE_X, 4, ln); /* (the episode cells' dim 20 px grey) */
    for (k = 0; k < nl; ++k)
        pg_paint_text_at(canvas, pg.st[ST_CDIM], t + ln[k].start, ln[k].len, PP_LINE_X,
                         pg_hint_y() + 8 + k * PS_TITLE_PITCH - off, PG_W - 2 * PP_LINE_X, PS_TITLE_PITCH);
}

static int pg_on_paint(void *ctx, void *e) {
    void *canvas = e ? *(void **)((char *)e + EVENT_PAINT_CANVAS) : (void *)0;
    int off = pg_off();
    (void)ctx;
    if (!canvas || !pg.view || !pg.g.tiles) return RET_OK;
    I(canvas, CANVAS_OY) += off;
    if (pg.level == L_DLS)
        pg_paint_dls(canvas);
    else if (pg.level == L_SHOWS && pg.nshows)
        pg_paint_home(canvas);
    else if (pg.level == L_EPS && pg.hg.tiles) {
        if (pg.det)
            pg_paint_det(canvas);
        else
            pg_paint_eps(canvas);
    } else if (pg.level == L_SRCH && pg.srn)
        pg_paint_srch(canvas);
    pg_paint_hint(canvas, off);
    I(canvas, CANVAS_OY) -= off;
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * The loader: one cover a tick
 */
static int pg_on_load(const void *unused);

static void pg_kick(void) {
    if (pg.win && pg.fg && !pg.load_timer) pg.load_timer = timer_add(pg_on_load, (void *)0, PG_LOAD_MS);
}

/* The path of a show's cover picture as a file:// url. */
static const char *pg_has_tone_url(const pc_show_t *s, char *url, unsigned size) {
    char path[PC_FILE * 2 + 40];
    unsigned n = 0, k;
    if (!s->cover[0]) return (const char *)0;
    if (s == &pg.shows[PC_MAX_SHOWS]) { /* the preview's picture is in the search directory, not in a show folder */
        for (k = 0; PN_PREVIEW_COVER[k]; ++k) path[n++] = PN_PREVIEW_COVER[k];
    } else {
        for (k = 0; pg.root[k] && n < sizeof path - 1; ++k) path[n++] = pg.root[k];
        path[n++] = '/';
        for (k = 0; s->dir[k] && n < sizeof path - 1; ++k) path[n++] = s->dir[k];
        path[n++] = '/';
        for (k = 0; s->cover[k] && n < sizeof path - 1; ++k) path[n++] = s->cover[k];
    }
    path[n] = 0;
    if (!pc_cover_ok(path) || n + 8 > size) return (const char *)0;
    memcpy(url, "file://", 7);
    memcpy(url + 7, path, n + 1);
    return url;
}

static void pg_art(grid_t *g, grid_tile_t *t, const pc_show_t *s) {
    char url[PC_FILE * 2 + 60];
    grid_art_url(g, t, pg_has_tone_url(s, url, sizeof url));
}

/* ---------------------------------------------------------------------------
 * The Show page's tint: the album page's (docs/modules/album-page.md "Cover tint", "Status bar"; patch/albumpage.c) on this window, with the same functions and assets: the window's bg_color is the
 * tone (pod_tone) of the cover's average colour under the black gradient image ah_tint (the window's first child, img_ah_tint, shown only now), so the list over it is transparent; the status bar takes
 * the window's row 0 (pod_bar_tint, pod_bar_black: the one owner of the bar) while the page is in front and tinted; the tone cache (pod_tone_get / pod_tone_put, shared with the album page and Now
 * Playing) remembers it per show. A show without a cover picture stays black. The state is the page's: it is cleared when another level shows, when the page is behind another and when it is destroyed.
 */
static void pg_win_color(unsigned color) {
    unsigned v[4]; /* value_t: type at 0, the uint32 at 8 */
    memset(v, 0, sizeof v);
    value_set_uint32(v, color);
    widget_set_style(pg.win, "normal:bg_color", v);
}

static void pg_bar_apply(void) {
    if (pg.tint_on && pg.fg && pg.level == L_EPS && !pg.det &&
        pod_bar_tint(pg.win, pod_shade(pg.tint, 0, AH_TINT_A_TOP, AH_TINT_A_BOT, AH_TINT_ROWS)))
        pg.bar_ours = 1; /* a failed call keeps what the bar has (and owes) */
}

__attribute__((noinline)) static void pg_bar_black(void) {
    if (!pg.bar_ours) return;
    pg.bar_ours = 0;
    pod_bar_black(pg.win);
}

static unsigned pg_tone_raw __attribute__((section(
    ".scratch"))); /* the tone as chosen (the page shows pal_tone of it: neutral in Light Mode), for pg_relight */

/* The tint on the window: shown on the Show page, plain black (window, gradient, status bar) on an episode's page; called when the tint changes and when the page opens and closes. */
static void pg_tint_view(void) {
    int on = pg.tint_on && !pg.det;
    pg_win_color(on ? pg.tint | 0xff000000u : 0xff000000u);
    if (pg.tint_img) widget_set_visible(pg.tint_img, on, 0); /* (decorative: it stays insensitive) */
    widget_invalidate_force(pg.win, (void *)0);
    if (on)
        pg_bar_apply();
    else
        pg_bar_black();
}

static void pg_tint_set(unsigned tone) {
    unsigned color = pal_tone(tone);
    pg_tone_raw = tone;
    pg.tint = color & 0xffffff;
    pg.tint_on = 1;
    pg_tint_view();
}

/* The Show page shows a cover's tone now (not the shows list, not an episode: pg_tint_view). */
int pg_has_tone(void) { return pg.win && pg.tint_on && !pg.det; }

void pg_relight(void) {
    if (pg.win && pg.tint_on) pg_tint_set(pg_tone_raw); /* (patch/palette.c pal_apply) */
}

static void pg_tint_clear(void) {
    pg_bar_black();
    pg.tint_key = 0;
    if (!pg.tint_on) return;
    pg.tint = 0, pg.tint_on = 0;
    pg_win_color(0xff000000u);
    if (pg.tint_img) widget_set_visible(pg.tint_img, 0, 0);
    widget_invalidate_force(pg.win, (void *)0);
}

/* The show's tone from the tone cache at once (the show was open before in this session), else from the cover once the header's picture is loaded (pg_tint_cover). */
static void pg_tint_open(void) {
    unsigned tone;
    pg.tint_key = cc_key_of("Podcasts", pg.shows[pg.sel].dir);
    if (pod_tone_get(pg.tint_key, &tone)) pg_tint_set(tone);
}

/* The tint from the header's cover, once it is a real picture (the placeholder disc and a refused picture leave the page black): cc_decode box-averages the centred square to one pixel, as the
 * album page's poll does, pod_tone makes the tone of it. */
static void pg_tint_cover(void) {
    char url[PC_FILE * 2 + 60];
    unsigned px, tone;
    if (pg.tint_on || pg.level != L_EPS || !pg.hg.tiles || pg.hg.tiles[0].art != 1) return;
    if (pg_has_tone_url(&pg.shows[pg.sel], url, sizeof url) && cc_decode(pg.win, url, 1, 1, 1, &px)) {
        tone = pod_tone(px & 255, px >> 8 & 255, px >> 16 & 255);
        pod_tone_put(pg.tint_key, tone);
        pg_tint_set(tone);
    }
}

/* The navbar's small title: shown once the large title (the Shows, Downloads, Subscriptions and Saved levels: SG_COLLAPSE, as every large-title page) or the Show level's header name has scrolled
 * away (pod_title_gone); in select mode it has its own: "N Selected". The search level's title is Apple Podcasts, always (empty and with results): it has no large title to scroll away. */
static void pg_title_show(void) {
    if (pg.title) widget_set_visible(pg.title, pg.collapsed || pg.select || pg.level == L_SRCH, 0);
}

static void pg_collapse(void) {
    int c = pg.level == L_EPS ? !pg.det && pg.hdr && pod_title_gone(pg_off(), pg.hdr->collapse)
                              : (pg.level == L_SHOWS || pg.level == L_DLS) && pod_title_gone(pg_off(), 0);
    if (c != pg.collapsed) {
        pg.collapsed = c;
        pg_title_show();
    }
}

/* The Downloads row whose cover is next: the rows in view and two either side (a ring of tiles holds that many; the rows are many), -1 when every tile there has been tried. */
static int pg_next_cover(void) {
    int r0, r1, a;
    pg_span(&r0, &r1);
    if (r1 < r0) return -1;
    for (a = r0 > 2 ? r0 - 2 : 0; a <= r1 + 2 && a < pg.nrows; ++a) {
        grid_tile_t *t = grid_find(&pg.g, pg.ord[a]);
        if (!t || !t->art) return a;
    }
    return -1;
}

/* The search level's next thumbnail: a result whose picture has arrived (pn_search_thumb) and whose tile has no picture yet, the rows in view first; -1 for none. */
static int pg_srch_next(void) {
    int r0, r1, a;
    char path[160];
    pg_span(&r0, &r1);
    for (a = r0; a <= r1; ++a) {
        grid_tile_t *t = grid_find(&pg.g, a);
        if ((!t || !t->art) && pn_search_thumb(a, path, sizeof path)) return a;
    }
    for (a = 0; a < pg.srn; ++a) {
        grid_tile_t *t = grid_find(&pg.g, a);
        if ((!t || !t->art) && pn_search_thumb(a, path, sizeof path)) return a;
    }
    return -1;
}

/* The Shows level's next cover: a Continue Listening item's first, then the grid's cells in view and a row either side (the ring holds that many); *idx is the item or the show. 1: an item, 2: a show, 0: none. */
static int pg_home_next(int *idx) {
    int i, a, c0, c1;
    for (i = 0; i < pg.ncont && pg.sg.tiles; ++i) {
        grid_tile_t *t = grid_find(&pg.sg, i);
        if (!t || !t->art) return *idx = i, 1;
    }
    pg_gspan(&c0, &c1);
    c0 -= GRID_COLS, c1 += GRID_COLS;
    if (c0 < 0) c0 = 0;
    if (c1 > pg.nshows - 1) c1 = pg.nshows - 1;
    for (a = c0; a <= c1 && pg.gg.tiles; ++a) {
        grid_tile_t *t = grid_find(&pg.gg, a);
        if (!t || !t->art) return *idx = a, 2;
    }
    return 0;
}

/* Whether a cover is still to be loaded (the page's tick starts the loader again when the screen is back: nothing is decoded in the dark). */
static void pg_dscan_step(void);
static void pg_tscan_step(void);

static int pg_load_pending(void) {
    int idx;
    if (pg.level == L_SHOWS) return pg_home_next(&idx) != 0 || pg.tscan_on;
    if (pg.level == L_SRCH) return pg_srch_next() >= 0;
    if (pg.level == L_DLS) return (!pg.subs && pg.dscan_on && !pg.select) || pg_next_cover() >= 0;
    if (pg.level != L_EPS) return pg_next_cover() >= 0;
    return (pg.hg.tiles && !pg.hg.tiles[0].art) || (pg.det && !pg.g.tiles[0].art);
}

static int pg_on_load(const void *unused) {
    int idx, kind;
    (void)unused;
    pg.load_timer = 0;
    if (!pg.win || !pg.fg || !pg.g.tiles || !pod_screen_lit()) return RET_OK;
    if (pg.level == L_SHOWS) {
        kind = pg_home_next(&idx);
        if (kind == 1) {
            int fresh;
            grid_tile_t *t = grid_tile(&pg.sg, idx, 0, PP_SHELF_MAX - 1, &fresh);
            pg_art(&pg.sg, t, &pg.shows[pg.cont[idx].show]);
        } else if (kind == 2) {
            grid_tile_t *t = pg_gtile(idx);
            if (!t->art) pg_art(&pg.gg, t, &pg.shows[idx]);
        }
        if (kind) {
            pg_redraw();
        } else
            pg_tscan_step(); /* (the Downloads row's totals, a show a tick, once the covers are done) */
        if (pg_load_pending()) pg_kick();
    } else if (pg.level == L_SRCH) {
        int a = pg_srch_next();
        if (a >= 0) {
            grid_tile_t *t = pg_stile(a);
            char path[160], url[180];
            if (pn_search_thumb(a, path, sizeof path) && pc_cover_ok(path)) {
                url[0] = 0;
                pg_cat(url, sizeof url, "file://");
                pg_cat(url, sizeof url, path);
                grid_art_url(&pg.g, t, url);
            } else
                grid_art_url(&pg.g, t, (const char *)0);
            pg_redraw();
            pg_kick();
        }
    } else if (pg.level == L_DLS) { /* the covers of the rows in view, then the Downloaded scan, a show a tick */
        int a = pg_next_cover(), scan = !pg.subs && pg.dscan_on && !pg.select;
        if (scan && (a < 0 || (pg.dtick = !pg.dtick))) /* (both pending: a tick each, so neither starves the other) */
            pg_dscan_step();
        else if (a >= 0) {
            grid_tile_t *t = pg_tile(a);
            if (!t->art) pg_art(&pg.g, t, &pg.shows[pg_row(a)->si]);
            pg_redraw();
        }
        if (pg_load_pending()) pg_kick();
    } else if (pg.hg.tiles && !pg.hg.tiles[0].art) {
        pg_art(&pg.hg, &pg.hg.tiles[0], &pg.shows[pg.sel]);
        pg_tint_cover();
        pg_redraw();
        if (pg_load_pending()) pg_kick();
    } else if (pg.det && !pg.g.tiles[0].art) { /* the episode page's show row cover */
        pg_art(&pg.g, &pg.g.tiles[0], &pg.shows[pg.sel]);
        pg_redraw();
    }
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * Levels
 */
static void pg_title(const char *key, const char *text) {
    if (key) { /* the Shows, Downloads, Subscriptions and Saved levels: the large heading at the top of the content, and the same words for the navbar's small title (shown once it has scrolled away) */
        az_fit(pg.big, TR(key));
        text = TR(key);
    }
    if (pg.title) az_fit(pg.title, text);
}

static void pg_empty(const char *key) {
    widget_move(pg.status, 20, 180);
    pg_show(pg.view, 0);
    pg_show(pg.status, 1);
    widget_set_tr_text(pg.status, key);
}

static void pg_fade(void) {
    if (!pg.fade) return;
    widget_set_visible(pg.fade, pg_off() > 0 && (pg.level != L_EPS || pg.det),
                       0); /* (the Show level paints its own, in the page's colour; the episode page is black) */
    widget_set_sensitive(pg.fade, 0);
}

static int pg_on_scroll(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (!pg.win) return RET_OK;
    pg_collapse();
    pg_fade();
    pg_kick();
    return RET_OK;
}

static void pg_drop_tiles(void) {
    grid_drop(&pg.g);
    grid_drop(&pg.hg);
    grid_drop(&pg.gg);
    grid_drop(&pg.sg);
    pg.gsig = pg.ssig = 0;
    pg.press = pg.down = 0;
}

/* Whether row a can be marked in select mode. Show level: an episode with a file, or a .part that no download holds (a paused one: deleting it takes the paused download away); a remote
 * row cannot. Downloads level: every row but the one running (it is paused with a tap first). */
static int pg_pickable(int a) {
    int code, st;
    unsigned got, total;
    if (pg.level == L_DLS)
        return a < pg.nrows &&
               (pg.subs || pg_is_dld(a) || pn_dl_state(pg_row(a)->key, &code, &got, &total) != PN_DL_ACTIVE);
    if (pg.level != L_EPS || a >= pg.neps) return 0;
    if (pg.eps[a].state == PC_LOCAL) return 1;
    if (pg.eps[a].state != PC_PART || !pg.eps[a].file[0]) return 0;
    st = pn_dl_state(pn_dl_key(pg.shows[pg.sel].dir, pg.eps[a].file), &code, &got, &total);
    return st == PN_DL_NONE || st == PN_DL_FAILED;
}

/* How many rows can be marked; with fill the bitset of them is made. */
static unsigned pg_sel_scan(int fill) {
    int i, n = pg_count();
    unsigned c = 0;
    if (fill) memset(pg.can, 0, sizeof pg.can);
    for (i = 0; i < n && i < PG_DLS_MAX; ++i)
        if (pg_pickable(i)) {
            ++c;
            if (fill) pg.can[i >> 3] |= (unsigned char)(1 << (i & 7));
        }
    return c;
}

static void pg_select(int on);
static void pg_sheet_close(void);

/* Leaving the Show level (every other level's loader): its sheet, its tint and its small title go. */
static void pg_det_drop(void);

static void pg_leave_show(void) {
    pg_det_drop();
    pg_sheet_close();
    pg_tint_clear();
    pg.collapsed = 0;
}

/* The navbar's right end. Shows level: the "..." (the sheet's button) only while the card has something to import (Import from Card). Show level: the "..." (its sheet). Downloads page and Subscriptions page: the "..."
 * (Select and Delete Played Episodes / Select Shows and Export OPML) while there are rows. Elsewhere all are hidden (and out of the hit test) and Now Playing is the glass disc; with a cap beside it Now Playing is the capsule's right cap.
 * The large title is the Shows level's (a child of the content view); the navbar's small one: see pg_title_show. */
static void pg_head(void);
static void pg_nav(void) {
    int more = !pg.select && pg.btn_more &&
               ((pg.level == L_EPS && !pg.preview && !pg.det) || (pg.level == L_SHOWS && pg.has_import) ||
                (pg.level == L_DLS && pg.nrows && !pg.saved)),
        globe = !pg.select && pg.btn_globe && pg.level == L_SHOWS &&
                pg.searchon, /* (the Apple Podcasts search, only while Podcast Search is on) */
        cap = more || globe,
        gx = NAV_VIEW_X - (more ? NAV_VIEW_W : 0); /* the pieces are right-aligned to Now Playing, 46 apart */
    const char *img = cap ? "ah_nav_play" : "ah_nav_np", *mimg = globe && more ? "pod_nav_moremid" : "pod_nav_more";
    pg_show(pg.btn_more, more);
    pg_show(pg.btn_globe, globe);
    if (globe) widget_move(pg.btn_globe, gx, 0); /* [Globe | Now Playing], [Globe | ... | NP] or [... | NP] */
    if (pg.btn_more) {
        widget_set_prop_str(pg.btn_more, "style:normal:icon", mimg);
        widget_set_prop_str(pg.btn_more, "style:over:icon", mimg);
        widget_set_prop_str(pg.btn_more, "style:pressed:icon",
                            globe && more ? "pod_nav_moremid_down" : "pod_nav_more_down");
    }
    if (pg.sf)
        widget_set_visible(pg.sf, pg.level == L_SRCH,
                           0); /* (insensitive for life: a touch on the field goes to the content view) */
    pg_show(pg.big, pg.level == L_SHOWS || pg.level == L_DLS);
    if (pg.title &&
        !pg.select) { /* the small title ends before the leftmost button, cut with an ellipsis (pg_head sets the text again at the new width) */
        widget_resize(pg.title, (globe ? gx : more ? NAV_VIEW_X : NAV_VIEW_X + NAV_VIEW_W) - NAV_TITLE_X, 22);
        pg_head();
    }
    pg_title_show();
    if (pg.np) {
        widget_set_prop_str(pg.np, "style:normal:icon", img);
        widget_set_prop_str(pg.np, "style:over:icon", img);
        widget_set_prop_str(pg.np, "style:pressed:icon", cap ? "ah_nav_play_down" : "ah_nav_np_down");
    }
}

/* The model's folders again (a show may have come, gone or been renamed): every one of them is a show of the Shows level. */
static void pg_scan(void) { pg.nshows = pc_scan_shows(pg.shows, PC_MAX_SHOWS); }

/* Continue Listening: the episodes partly played, the most recently played first (the ring's order), at most PP_SHELF_MAX; each title cut to the item's width. */
static void pg_cont_load(void) {
    pc_cont_t c[PP_SHELF_MAX];
    int n = pc_continue(pg.shows, pg.nshows, c, PP_SHELF_MAX), i;
    pg.ncont = 0;
    for (i = 0; i < n; ++i) {
        struct pg_item *it = &pg.cont[i];
        pw_line_t ln;
        int len = pg_wide(it->title, PG_TITLE_MAX, c[i].title);
        it->show = c[i].show, it->hash = c[i].hash;
        it->tn = pg_lines(pg.st[ST_STITLE], it->title, len, PP_SHELF_W, 1, &ln) == 1 ? ln.len : 0;
    }
    pg.ncont = n;
}

/* The Shows level's tiles for the shows and items now: kept when they are the ones the tiles were made for (keep, and the same folders, covers and items: a visit to Now Playing and back loads nothing again),
 * else made afresh. A kept grid has its captions made again. */
static void pg_home_shape(int keep) {
    unsigned gs = 17, ss = 17;
    int i, k;
    for (i = 0; i < pg.nshows; ++i) {
        gs = gs * 31 + pg.shows[i].hash;
        for (k = 0; pg.shows[i].cover[k]; ++k) gs = gs * 31 + (unsigned char)pg.shows[i].cover[k];
    }
    for (i = 0; i < pg.ncont; ++i) {
        ss = ss * 31 + pg.cont[i].hash;
        for (k = 0; pg.shows[pg.cont[i].show].cover[k]; ++k)
            ss = ss * 31 + (unsigned char)pg.shows[pg.cont[i].show].cover[k];
    }
    if (!keep || gs != pg.gsig || !pg.gg.placeholder) {
        grid_drop(&pg.gg);
        grid_shape(&pg.gg, GRID_COVER, GRID_R, 0);
        grid_placeholder(&pg.gg);
        pg.gsig = gs;
    } else
        pg_gretext();
    if (!keep || ss != pg.ssig || !pg.sg.placeholder) {
        grid_drop(&pg.sg);
        grid_shape(&pg.sg, PP_SHELF_ART, PP_SHELF_R, 0);
        grid_placeholder(&pg.sg);
        pg.ssig = ss;
    }
}

/* The Shows level (docs/modules/podcasts.md "The Shows page"): every show the card has, most recently updated first. keep: the page is on it already and is made again (a refresh moved on, it came back to
 * the front): the scroll position and the covers stay. */
/* The Shows level's totals scan (the Downloads row's grey line): the folders of the shows are walked one a tick of the loader (pc_walk: the audio files' sizes and the .part files nothing holds); the figures shown stay
 * those of the last complete scan until this one ends. It starts when the level is made after another level (files may have come or gone), when the worker moved, and the first time. */
struct pg_tctx {
    char dir[PC_FILE];
    unsigned kb, parts;
};

static void pg_tscan_cb(void *ctx, const char *name, unsigned kb, int part) {
    struct pg_tctx *c = ctx;
    char base[PC_FILE];
    unsigned n = 0, got, total;
    int code;
    if (!part) {
        c->kb += kb;
        return;
    }
    while (name[n] && n < PC_FILE - 1) base[n] = name[n], ++n;
    base[n] = 0;
    if (n > 5) base[n - 5] = 0;
    if (pn_dl_state(pn_dl_key(c->dir, base), &code, &got, &total) == PN_DL_NONE)
        ++c->parts; /* (paused: nothing holds it) */
}

static void pg_tscan_start(void) {
    pg.tscan = pg.ta_kb = pg.ta_parts = 0;
    pg.tscan_on = pg.nshows > 0;
    pg.tot_gen = pn_gen();
}

static void pg_tscan_step(void) {
    struct pg_tctx c;
    if (!pg.tscan_on) return;
    if (pg.tscan < pg.nshows) {
        memset(&c, 0, sizeof c);
        pg_cat(c.dir, sizeof c.dir, pg.shows[pg.tscan].dir);
        pc_walk(pg.root, c.dir, pg_tscan_cb, &c);
        pg.ta_kb += c.kb, pg.ta_parts += c.parts;
    }
    if (++pg.tscan >= pg.nshows) {
        pg.tot_kb = pg.ta_kb, pg.tot_parts = pg.ta_parts, pg.tot_ok = 1, pg.tscan_on = 0;
        pg_redraw();
    }
}

/* The Saved episodes (docs/modules/podcasts.md "Saved"): the myfav rows under the Podcasts folder, which stock's star adds and removes (the query filter, payload.md hook 6, keeps them out of the music Favourites
 * and lists only them while pc_saved_scope is set). Read with stock's own Favourites query, last saved first; the ones whose file is on the card are kept, at most PG_DLD_MAX: pg.sv_h their ring keys (pc_hash of the
 * path, what pc_ep_t.hash is), pg.sv_d the hashes of their show folders, pg.sv_n the count. The stock list the query leaves in *pdeq_showlist is not used after. */
static void pg_saved_load(void) {
    void *list;
    unsigned i, n, root = 0;
    while (pg.root[root]) ++root;
    pg.sv_n = 0;
    if (!pg.sv_h || !pg.sv_d) return;
    pc_saved_scope = 1;
    list = loadLocalClassList(CLASS_FAV) > 0 ? *(void **)PDEQ_SHOWLIST : (void *)0;
    pc_saved_scope = 0;
    n = list ? deque_size(list) : 0;
    for (i = 0; i < n && pg.sv_n < PG_DLD_MAX; ++i) {
        const char *p = cc_str(deque_at(list, i), REC_PATH);
        char dir[PC_FILE];
        unsigned k;
        if (!pc_is_path(p) || access(p, F_OK)) continue;
        for (k = 0; k <= root && p[k]; ++k) {
        }
        if (k != root + 1 || !p[root + 1]) continue;
        for (k = 0; p[root + 1 + k] && p[root + 1 + k] != '/' && k < (unsigned)PC_FILE - 1; ++k)
            dir[k] = p[root + 1 + k];
        dir[k] = 0;
        pg.sv_h[pg.sv_n] = pc_hash(p), pg.sv_d[pg.sv_n] = pc_hash(dir);
        ++pg.sv_n;
    }
}

/* The rank of a saved episode (0 the last saved), -1 when the file is not saved. */
static int pg_saved_rank(unsigned hash) {
    int i;
    for (i = 0; i < pg.sv_n; ++i)
        if (pg.sv_h[i] == hash) return i;
    return -1;
}

static void pg_load_shows(int keep) {
    int i, off = keep && pg.level == L_SHOWS ? pg_off() : pg.show_off, was = pg.level;
    if (pg.select) pg_select(0);
    if (keep) {
        grid_drop(&pg.g); /* (the grid's covers stay when the shows are the same) */
        grid_drop(&pg.hg);
        pg.press = pg.down = 0;
    } else
        pg_drop_tiles();
    pg.level = L_SHOWS;
    pg.preview = pg.from_search = pg.subs = pg.from_subs = pg.from_dls = pg.saved = 0;
    pg_leave_show();
    pg_scan();
    pg_saved_load(); /* (the Saved row's count) */
    pg.has_line = pg.has_import = 0;
    for (i = 0; i < pg.nshows; ++i) pg.has_line |= pg.shows[i].feed[0] != 0;
    if (!pg.tot_ok || was != L_SHOWS || pn_gen() != pg.tot_gen) pg_tscan_start();
    pg.has_import =
        pn_import_found(pg.root) > 0; /* subscriptions.txt, subscriptions.opml or an *.opml in the card's root */
    pg_cont_load();
    free(pg.eps);
    pg.eps = (pc_ep_t *)0;
    pg.neps = 0;
    pg.gen = pn_gen(), pg.dgen = pn_dl_gen();
    pg.rev = pc_rev();
    pg_title("Podcasts", (const char *)0);
    pg_show(pg.view, 1);
    pg_show(pg.status, 0);
    // clang-format off: a translation key stays on one line (test/pod/i18n.py reads the source)
    if (!pg.nshows) pg_empty("No podcasts. Copy a folder for each show into Podcasts on the card, or put subscriptions.txt there and choose Import from Card in the menu at the top right.");
    // clang-format on
    pg_nav();
    pg_home_shape(keep);
    pg_home_layout();
    pg_size();
    widget_set_prop_int(pg.sv, "yoffset", off);
    pg_collapse();
    pg_title_show();
    pg_fade();
    pg_redraw();
    pg_kick();
}

/* The index in shows of the show folder dir, -1 when there is none. */
static int pg_show_of(const char *dir) {
    int i;
    for (i = 0; i < pg.nshows; ++i)
        if (!strcmp(pg.shows[i].dir, dir)) return i;
    return -1;
}

static void pg_dl_row(int n, int si, const char *dir, const char *file, const char *title, unsigned key) {
    struct pg_dl *d = &pg.dls[n];
    memset(d, 0, sizeof *d);
    pg_cat(d->dir, sizeof d->dir, dir);
    pg_cat(d->file, sizeof d->file, file);
    pg_cat(d->title, sizeof d->title, title);
    d->key = key;
    d->si = si;
}

/* ---------------------------------------------------------------------------
 * The Downloads level (docs/modules/podcasts.md "The Downloads page"): two sections, In Progress (what the worker holds, in the order it was asked, then the failed ones, then the paused .part files the card has) and
 * Downloaded (every episode file of every show, the newest download first, at most PG_DLD_MAX). A row lives in a slot (In Progress 0..PG_IP_MAX - 1, Downloaded after) and its tile is keyed by the slot; pg.ord maps the
 * display rows to slots. The Downloaded rows come from a scan the page's loader runs, ONE show a tick (pg_dscan_step, as the local search does: pc_load_show reads, parses and merges one show), so a touch is answered
 * between slices; nothing runs while the screen is off. After the scan the lists are kept up to date from the worker's state (pg_dls_sync) without reading the shows again.
 */
static pc_ep_t *pg_eps_of(int si, int *count);
static void pg_dls_apply(void);
static void pg_dls_retext(void);

/* The display order: In Progress, then Downloaded (the Subscriptions page is the identity). */
static void pg_ord_build(void) {
    int i, n = 0;
    if (pg.subs) {
        for (i = 0; i < pg.nrows; ++i) pg.ord[i] = (unsigned short)i;
        return;
    }
    for (i = 0; i < pg.nip; ++i) pg.ord[n++] = (unsigned short)i;
    for (i = 0; i < pg.nd; ++i) pg.ord[n++] = pg.dord[i];
    pg.nrows = n;
}

/* A slot's tile is made again (its row changed hands). */
static void pg_tile_forget(int slot) {
    grid_tile_t *t = pg.g.tiles ? grid_find(&pg.g, slot) : (grid_tile_t *)0;
    if (t) {
        grid_free_art(t);
        memset(t, 0, sizeof *t);
    }
}

/* Downloaded row k (an index into dord) added: sorted by when, newest first (a tie after the ones it equals); at the cap the oldest goes (or the new one is not kept when it is older than all). The totals count every file. */
static void pg_dld_insert(int si, const pc_ep_t *e, unsigned when, unsigned kb) {
    unsigned char used[PG_DLD_MAX];
    struct pg_dl *d;
    int pos, i, slot;
    ++pg.dtot_n, pg.dtot_kb += kb;
    if (pg.nd >= PG_DLD_MAX) {
        if (when <= pg.dls[pg.dord[pg.nd - 1]].when) return;
        slot = pg.dord[--pg.nd];
    } else {
        memset(used, 0, sizeof used);
        for (i = 0; i < pg.nd; ++i) used[pg.dord[i] - PG_IP_MAX] = 1;
        for (i = 0; i < PG_DLD_MAX && used[i]; ++i) {
        }
        slot = PG_IP_MAX + i;
    }
    for (pos = 0; pos < pg.nd && pg.dls[pg.dord[pos]].when >= when; ++pos) {
    }
    memmove(&pg.dord[pos + 1], &pg.dord[pos], (unsigned)(pg.nd - pos) * sizeof *pg.dord);
    pg.dord[pos] = (unsigned short)slot;
    ++pg.nd;
    pg_dl_row(slot, si, pg.shows[si].dir, e->file, e->title, 0);
    d = &pg.dls[slot];
    d->hash = e->hash, d->when = when, d->kb = kb, d->dur = e->dur, d->pub = e->pub;
    pg_tile_forget(slot);
}

/* Downloaded row k (an index into dord) gone from the card. */
static void pg_dld_remove(int k) {
    struct pg_dl *d = &pg.dls[pg.dord[k]];
    if (pg.dtot_n) --pg.dtot_n;
    pg.dtot_kb = pg.dtot_kb > d->kb ? pg.dtot_kb - d->kb : 0;
    pg_tile_forget(pg.dord[k]);
    memmove(&pg.dord[k], &pg.dord[k + 1], (unsigned)(pg.nd - k - 1) * sizeof *pg.dord);
    --pg.nd;
}

/* In Progress row i gone (the rows after it move up: their slots change, so the In Progress tiles are made again). */
static void pg_ip_remove(int i) {
    int k;
    memmove(&pg.dls[i], &pg.dls[i + 1], (unsigned)(pg.nip - i - 1) * sizeof *pg.dls);
    --pg.nip;
    for (k = 0; k < PG_IP_MAX; ++k) pg_tile_forget(k);
}

/* The episodes of show si read: file == NULL is a slice of the scan (every episode on the card is a Downloaded row; the In Progress rows of the show get their titles; a .part the worker does not hold is a paused row);
 * else only that file (a download that has finished), as one Downloaded row. */
static void pg_dscan_show(int si, const char *only) {
    int m = 0, k, j;
    pc_ep_t *all = pg_eps_of(si, &m);
    if (!all) return;
    for (k = 0; k < m; ++k) {
        const pc_ep_t *e = &all[k];
        unsigned mt, kb;
        if (!e->file[0]) continue;
        if (e->state == PC_LOCAL) {
            int rank = pg.saved ? pg_saved_rank(e->hash) : 0;
            if (rank < 0 || (only && strcmp(only, e->file)) || !pc_stat(pg.root, pg.shows[si].dir, e->file, &mt, &kb))
                continue;
            pg_dld_insert(si, e,
                          pg.saved ? ~0u - (unsigned)rank
                          : mt     ? mt
                                   : e->pub,
                          kb); /* (Saved: the order is the rank) */
            if (only) break;
            continue;
        }
        if (only || pg.saved) continue;
        for (j = 0; j < pg.nip; ++j)
            if (pg.dls[j].si == si && !strcmp(pg.dls[j].file, e->file)) break;
        if (j < pg.nip) {
            pg.dls[j].title[0] = 0;
            pg_cat(pg.dls[j].title, PC_TITLE, e->title);
            pg_tile_forget(j);
        } else if (e->state == PC_PART && pg.nip < PG_IP_MAX)
            pg_dl_row(pg.nip++, si, pg.shows[si].dir, e->file, e->title, pn_dl_key(pg.shows[si].dir, e->file));
    }
    free(all);
}

/* Whether file (with suffix) of show folder dir is on the card. */
static int pg_has_file(const char *dir, const char *file, const char *suffix) {
    char name[PC_FILE + 8];
    unsigned mt, kb;
    name[0] = 0;
    pg_cat(name, sizeof name, file);
    pg_cat(name, sizeof name, suffix);
    return pc_stat(pg.root, dir, name, &mt, &kb);
}

/* The In Progress rows from the worker (what it holds in the order it was asked, then the failed ones) and the old rows it no longer holds: one whose .part is still there is a paused row and stays, one whose file is
 * there has finished (it becomes a Downloaded row: its show is read once for the episode's date and length), one with neither is gone (a waiting one that was taken out of the queue). Titles are carried over. */
static void pg_ip_sync(void) {
    struct pg_dl *nw = calloc(PG_IP_MAX, sizeof *nw);
    char dir[PC_FILE], file[PC_FILE];
    int n = 0, i, j, k, code;
    unsigned key;
    if (!nw) return;
    for (i = 0; n < PG_IP_MAX && (key = pn_dl_listed(i, dir, file, &code)); ++i) {
        int si = pg_show_of(dir);
        struct pg_dl *r = &nw[n];
        if (si < 0) continue;
        memset(r, 0, sizeof *r);
        pg_cat(r->dir, sizeof r->dir, dir);
        pg_cat(r->file, sizeof r->file, file);
        pg_cat(r->title, sizeof r->title, file);
        r->key = key, r->si = si;
        for (j = 0; j < pg.nip; ++j)
            if (pg.dls[j].key == key) {
                r->title[0] = 0;
                pg_cat(r->title, sizeof r->title, pg.dls[j].title);
            }
        ++n;
    }
    for (j = 0; j < pg.nip; ++j) {
        const struct pg_dl *o = &pg.dls[j];
        int held = 0;
        for (k = 0; k < n; ++k) held |= nw[k].key == o->key;
        if (held) continue;
        if (pg_has_file(o->dir, o->file, ".part")) {
            if (n < PG_IP_MAX) memcpy(&nw[n++], o, sizeof *o);
        } else if (pg_has_file(o->dir, o->file, ""))
            pg_dscan_show(o->si, o->file);
    }
    memcpy(pg.dls, nw, (unsigned)n * sizeof *nw);
    pg.nip = n;
    free(nw);
    for (k = 0; k < PG_IP_MAX; ++k) pg_tile_forget(k);
}

/* The scan starts over (the level was entered, or the worker moved while it was running): nothing listed, the In Progress rows from the worker, the shows to read in an order that has the ones the worker names first
 * (their rows get their titles), then the page's order. */
static void pg_dscan_start(void) {
    int i, n = 0, k;
    unsigned kb = 0;
    pg.nd = pg.nip = pg.nrows = 0;
    pg.dtot_n = pg.dtot_kb = 0;
    if (pg.saved) { /* the shows that hold a saved episode, in the page's order: nothing is in progress here */
        for (i = 0; i < pg.nshows && n < PC_MAX_SHOWS; ++i)
            for (k = 0; k < pg.sv_n; ++k)
                if (pg.sv_d[k] == pg.shows[i].hash) {
                    pg.dsl[n++] = (unsigned char)i;
                    break;
                }
        pg.dsn = n, pg.dscan = 0, pg.dscan_on = n > 0, pg.dfree_ok = 0;
        return;
    }
    pg_ip_sync();
    for (i = 0; i < pg.nip; ++i) {
        for (k = 0; k < n && pg.dsl[k] != pg.dls[i].si; ++k) {
        }
        if (k == n) pg.dsl[n++] = (unsigned char)pg.dls[i].si;
    }
    for (i = 0; i < pg.nshows && n < PC_MAX_SHOWS; ++i) {
        for (k = 0; k < n && pg.dsl[k] != i; ++k) {
        }
        if (k == n) pg.dsl[n++] = (unsigned char)i;
    }
    pg.dsn = n, pg.dscan = 0, pg.dscan_on = n > 0;
    pg.dfree_ok = pn_free_kb(pg.root, &kb);
    pg.dfree_kb = kb;
}

/* One slice of the scan: the next show. */
static void pg_dscan_step(void) {
    if (!pg.dscan_on) return;
    pg_dscan_show(pg.dsl[pg.dscan++], (const char *)0);
    if (pg.dscan >= pg.dsn) pg.dscan_on = 0;
    pg_dls_apply();
}

/* The Subscriptions page's rows (docs/modules/podcasts.md "Subscriptions and OPML"): every show with a feed address, by title; a row is the show (its cover, its name, its feed status line: pg_row_sub). */
static void pg_subs_build(void) {
    int order[PC_MAX_SHOWS], n = po_order(pg.shows, pg.nshows, order), i;
    for (i = 0; i < n; ++i)
        pg_dl_row(i, order[i], pg.shows[order[i]].dir, "", pg.shows[order[i]].title, pc_hash(pg.shows[order[i]].feed));
    pg.nrows = n;
}

/* The lists changed (a slice found something, the worker moved, rows were deleted): the display order, the empty state, the size, the navbar. The scroll offset stays inside the content. */
static void pg_dls_apply(void) {
    int max;
    pg_ord_build();
    if (!pg.nrows && (pg.subs || !pg.dscan_on)) {
        pg_show(
            pg.view,
            1); /* (the large title and the storage line stay, the hint is painted under them: the first frame is the last) */
        pg_show(pg.status, 0);
    } else {
        pg_show(pg.view, 1);
        pg_show(pg.status, 0);
    }
    pg_size();
    max = pg_content() - GRID_VIEW_H;
    if (max < 0) max = 0;
    if (pg.want_off && (pg.want_off <= max || !pg.dscan_on)) { /* the offset a Back asked for, once the rows reach it */
        widget_set_prop_int(pg.sv, "yoffset", pg.want_off > max ? max : pg.want_off);
        pg.want_off = 0;
    } else if (pg_off() > max)
        widget_set_prop_int(pg.sv, "yoffset", max);
    pg_nav();
    pg_redraw();
    pg_kick();
}

/* The lists kept up to date after the scan, from the worker's state and the card (no show is read again but one whose download has finished): the In Progress rows (pg_ip_sync), the Downloaded rows whose file is gone leave,
 * the free space is read again, the texts are made again (a place moved). While the scan still runs and the worker moved, it starts over. */
static void pg_dls_sync(void) {
    int k;
    unsigned kb = 0, mt, fkb;
    if (pg.subs || pg.saved) return; /* (the Saved page is made again by pg_load_downloads) */
    if (pg.dscan_on) {
        if (pn_gen() != pg.gen) pg_dscan_start();
    } else {
        pg_ip_sync();
        for (k = pg.nd - 1; k >= 0; --k) {
            const struct pg_dl *d = &pg.dls[pg.dord[k]];
            if (!pc_stat(pg.root, d->dir, d->file, &mt, &fkb)) pg_dld_remove(k);
        }
        pg.dfree_ok = pn_free_kb(pg.root, &kb);
        pg.dfree_kb = kb;
    }
    pg.gen = pn_gen(), pg.dgen = pn_dl_gen();
    pg_dls_retext();
    pg_dls_apply();
}

/* The Downloads level, behind the Shows level's Downloads row: the storage line, In Progress and Downloaded. The same level is the Subscriptions page (pg.subs: behind the Shows level's Subscriptions row, same taps and
 * select mode, other rows). keep (the Subscriptions page only): the scroll position stays when the rows are made again; the Downloads page reads the worker and the card through pg_dls_sync instead. */
static void pg_load_downloads(int keep) {
    int off = keep && (pg.subs || pg.saved) ? pg_off() : 0;
    if (!pg.dls || !pg.ord) {
        pod_toast(TR("Not enough memory"));
        return;
    }
    if (pg.select) pg_select(0);
    if (pg.level == L_SHOWS) pg.show_off = pg_off();
    pg_drop_tiles();
    pg.level = L_DLS;
    pg_leave_show();
    pg_scan();
    free(pg.eps);
    pg.eps = (pc_ep_t *)0;
    pg.neps = 0;
    pg.nip = pg.nd = pg.nrows = pg.dscan_on = 0;
    pg.want_off = 0;
    if (pg.subs)
        pg_subs_build();
    else {
        if (pg.saved) pg_saved_load();
        pg_dscan_start();
    }
    pg.gen = pn_gen(), pg.dgen = pn_dl_gen();
    pg.rev = pc_rev();
    pg_title(pg.subs ? "Subscriptions" : pg.saved ? "Saved" : "Downloads", (const char *)0);
    grid_shape(&pg.g, LIST_ART, LIST_R, 1);
    grid_placeholder(&pg.g);
    pg_dls_apply();
    widget_set_prop_int(pg.sv, "yoffset", off);
    if (pg.saved) pg.want_off = off; /* (the rows come a show a tick: the offset is put back as they reach it) */
    pg_collapse();
    pg_fade();
    pg_kick();
}

/* The Saved page: the Downloads level with the saved episodes as its Downloaded rows, the last saved first (from the Shows level, or back from an episode page opened from it). */
static void pg_load_saved(void) {
    pg.saved = 1;
    pg.subs = 0;
    pg_load_downloads(0);
}

/* The Subscriptions page: the Downloads level with the subscriptions as its rows (from the Shows level, or back from a Show page opened from it). */
static void pg_load_subs(int keep) {
    pg.subs = 1;
    pg_load_downloads(keep);
}

/* The episodes of show si (an index into shows): every one the show knows, on the card or not, newest first. The Show page lists them all: a cell's pill says which can be played and which downloaded. */
static pc_ep_t *pg_eps_of(int si, int *count) {
    pc_ep_t *all = calloc(PC_MAX_EPS, sizeof *all);
    if (!all) return all;
    *count = pc_load_show(&pg.shows[si], all, PC_MAX_EPS);
    return all;
}

static const char *pg_no_eps_key(void) {
    return pg.shows[pg.sel].feed[0] ? "No episodes yet. Choose Refresh Feed in the menu at the top right."
                                    : "No downloaded episodes";
}

/* The Show level of show si (docs/modules/podcasts.md "The Show page"; Back goes to the Shows level). off: the scroll position to keep (a show opened again after a refresh), 0 the top. */
static void pg_open_show_with(int si, int off, pc_ep_t *all, int m) {
    pg_det_drop();
    pg.gen = pn_gen(), pg.dgen = pn_dl_gen();
    if (pg.level == L_SHOWS) pg.show_off = pg_off();
    pg_sheet_close();
    pg_tint_clear();
    grid_drop(&pg.g); /* (the Shows level's covers stay: Back finds them) */
    grid_drop(&pg.hg);
    pg.press = pg.down = 0;
    free(pg.eps);
    pg.eps = all, pg.neps = m, pg.sel = si, pg.level = L_EPS;
    pg.feed_hash = pg.shows[si].feed[0] ? pc_hash(pg.shows[si].feed) : 0;
    pg.rev = pc_rev();
    pg.collapsed = 0;
    pg_cells_drop();
    pg_hdr_make();
    pg_title((const char *)0, pg.shows[si].title);
    pg_nav();
    pg_show(pg.view, 1);
    pg_show(pg.status, 0);
    grid_shape(&pg.g, LIST_ART, LIST_R, 1);
    grid_shape(&pg.hg, PS_ART, PS_ART_R,
               1); /* (the corners are cut in the alpha: the page's tint shows through them) */
    grid_placeholder(&pg.hg);
    pg_size();
    widget_set_prop_int(pg.sv, "yoffset", off > 0 ? off : 0);
    pg_tint_open();
    pg_collapse();
    pg_fade();
    pg_redraw();
    pg_kick();
}

static void pg_open_show(int si, int off) {
    int m = 0;
    pc_ep_t *all = pg_eps_of(si, &m);
    if (!all) {
        pod_toast(TR("Not enough memory"));
        return;
    }
    pg.preview = 0;
    pg_open_show_with(si, off, all, m);
}

static void pg_det_refind(void);

/* The Show level's episodes read again (a download finished, failed or was started, a file was removed: the list changed): the scroll position stays, the layouts are made again. */
static void pg_reload_eps(void) {
    int m = 0, max;
    pc_ep_t *all = pg_eps_of(pg.sel, &m);
    pg.gen = pn_gen(), pg.dgen = pn_dl_gen();
    if (!all) return;
    free(pg.eps);
    pg.eps = all, pg.neps = m;
    pg.press = pg.down = 0;
    pg_det_refind(); /* (the episode page stays on its episode, wherever the list put it) */
    pg_cells_drop();
    pg_hdr_make();
    pg_show(pg.status, 0);
    pg_size();
    max = pg_content() - GRID_VIEW_H;
    if (max < 0) max = 0;
    if (pg_off() > max) widget_set_prop_int(pg.sv, "yoffset", max);
    pg_collapse();
    pg_nav();
    pg_redraw();
}
/* ---------------------------------------------------------------------------
 * The search level (docs/modules/podcasts.md "Search"): behind the Shows level's Search button while Podcast Search is on in Settings. The field at the top opens our keyboard (the Playlists page's New
 * playlist does the same: keyboard_open, its Search key calls back when the page is in front again); the answer, the thumbnails and the preview are the worker's (patch/pcnet.c): this reads its record from
 * the page's 1 s tick and does no widget work in the dark. A job waits for the downloads to pause, as a refresh does; a running one is cancelled by a newer one and by leaving the page.
 */
static void pg_copy(char *dst, unsigned size, const char *src) {
    dst[0] = 0;
    pg_cat(dst, size, src);
}

static void pg_srch_edit(void);
static void pg_srch_pending(void);
static void pg_open_preview(void);
static int pg_open_subscribed(const char *feed);

/* The rows again for another answer: the tiles go, so each row's text and thumbnail are made afresh. */
static void pg_srch_rows_reset(void) {
    grid_drop(&pg.g);
    grid_shape(&pg.g, LIST_ART, LIST_R, 1);
    grid_placeholder(&pg.g);
    pg.press = pg.down = 0;
}

/* The status line under the field (the label of the empty states), or none. */
static void pg_srch_hint(const char *text) {
    if (text) {
        widget_move(pg.status, 20, PG_LIST_Y + PQ_TOP + PQ_HINT_Y);
        widget_set_text_utf8(pg.status, text);
    }
    pg_show(pg.status, text != (const char *)0);
}

/* What the level shows for the state: the field's texts, the status line (Loading... while a preview is fetched, Searching..., No results, the failure's words) or the rows of the answer. */
static void pg_srch_apply(void) {
    int n = 0, max;
    const char *hint = (const char *)0;
    if (pg.level != L_SRCH) return;
    if (pg.loading)
        hint = TR("Loading…");
    else if (pg.sstate == SS_WAIT || pg.sstate == SS_RUN)
        hint = TR("Searching…");
    else if (pg.sstate == SS_DONE && pg.scode != PN_CANCELLED) {
        if (pg.scode != PN_OK)
            hint = pg_status_word(pg.scode);
        else if (!(n = pn_search_count()))
            hint = TR("No results");
    }
    pg.srn = n;
    pg_srch_hint(hint);
    if (pg.sf_hint) widget_set_visible(pg.sf_hint, pg.sq[0] == 0, 0);
    if (pg.sf_clear)
        widget_set_visible(pg.sf_clear, pg.sq[0] != 0, 0); /* (an image: insensitive for life, the touch is PH_CLEAR) */
    if (pg.sf_text) {
        az_fit(pg.sf_text, pg.sq);
        widget_set_visible(pg.sf_text, pg.sq[0] != 0, 0);
    }
    pg_size();
    max = pg_content() - GRID_VIEW_H;
    if (max < 0) max = 0;
    if (pg_off() > max) widget_set_prop_int(pg.sv, "yoffset", max);
    pg_redraw();
    pg_kick();
}

static void pg_srch_submit(const char *text);

/* The level: the field (its text and hint), the answer so far. fresh: the page is entered from the Shows level; the text kept from last time is searched again when it is not the one the answer is of, and with nothing typed the keyboard opens at once. */
static void pg_load_search(int fresh) {
    if (pg.select) pg_select(0);
    if (pg.level == L_SHOWS) pg.show_off = pg_off();
    pg_sheet_close();
    pg_leave_show();
    grid_drop(&pg.hg);
    free(pg.eps);
    pg.eps = (pc_ep_t *)0;
    pg.neps = 0;
    pg.preview = 0;
    pg.level = L_SRCH;
    pg.from_search = 0;
    pg.gen = pn_gen(), pg.dgen = pn_dl_gen();
    pg_nav();
    pg_show(pg.view, 1);
    if (pg.sf_hint) widget_set_tr_text(pg.sf_hint, "Search Apple Podcasts");
    pg_srch_rows_reset();
    pg.sgen = pn_search_gen();
    pg_nav();
    if (fresh && pg.sq[0] && pc_hash(pg.sq) != pg.aqh) {
        pg_copy(pg.sp_text, sizeof pg.sp_text, pg.sq);
        pg_srch_submit(pg.sp_text);
    } else
        pg_srch_apply();
    widget_set_prop_int(pg.sv, "yoffset", 0);
    pg_title((const char *)0, TR("Apple Podcasts")); /* after pg_nav has sized the title (az_fit cuts to the width) */
    pg_collapse();
    pg_title_show();
    pg_fade();
    if (fresh && !pg.sq[0]) pg_srch_edit();
}

/* Leaving the level (Back, or the preview taking the worker): nothing waits any more and what runs is told to stop. */
static void pg_srch_leave(void) {
    pg.spend = SP_NONE;
    pg.loading = 0;
    if (pg.sstate == SS_WAIT) pg.sstate = SS_IDLE;
    if (pn_job_busy()) pn_cancel();
}

/* The preview (or the lookup of an Apple link) failed, or Subscribe could not write: the toast says Can't subscribe and why; where that is wider than the toast (300 px, 18 px text) only why. No folder was made. */
static void pg_srch_fail(int code) {
    char msg[128];
    unsigned w[128];
    msg[0] = 0;
    pg_cat(msg, sizeof msg, TR("Can't subscribe"));
    pg_cat(msg, sizeof msg, ": ");
    pg_cat(msg, sizeof msg, pg_status_word(code));
    pg_wide(w, 128, msg);
    if (pg_width(pg.st_sub, w) > 300) { /* the reason alone, and where even that is too wide only that it failed */
        msg[0] = 0;
        pg_cat(msg, sizeof msg, pg_status_word(code));
        pg_wide(w, 128, msg);
        if (pg_width(pg.st_sub, w) > 300) {
            msg[0] = 0;
            pg_cat(msg, sizeof msg, TR("Can't subscribe"));
        }
    }
    pod_toast(msg);
}

/* Start the job the level waits for: the downloads that run are asked to pause first (the page's tick asks again), a search or preview that runs is cancelled, a refresh is waited for. */
static void pg_srch_pump(void) {
    int r, job = pg.spend;
    if (!job) return;
    if (pn_dl_running()) {
        pn_dl_pause();
        pg_awake_arm();
        return;
    }
    if (pn_busy() || pn_job_busy()) {
        if (pn_job_busy()) pn_cancel();
        return;
    }
    r = job == SP_SEARCH ? pn_search(pg.sq) : pn_preview(pg.sp_url, pg.sp_id);
    if (r == PN_BUSY) return;
    pg.spend = SP_NONE;
    if (job == SP_SEARCH) {
        pg.sstate = r == PN_OK ? SS_RUN : SS_DONE;
        pg.scode = r;
        pg.sgen = pn_search_gen();
    } else if (r != PN_OK) {
        pg.loading = 0;
        pg_srch_fail(r);
    }
    pg_srch_apply();
}

/* The text of the field was submitted: an Apple Podcasts link or a feed address goes to its preview, anything else is searched. */
static void pg_srch_submit(const char *text) {
    char id[16];
    int kind;
    if (pg.level != L_SRCH || !text[0]) return;
    pg_copy(pg.sq, sizeof pg.sq, text);
    pg.aqh = pc_hash(text);
    kind = pn_classify(text, id, sizeof id);
    pg.loading = 0;
    if (kind == 1 && pg_open_subscribed(text))
        return; /* a typed address of a show that is subscribed already: its real page, nothing fetched */
    if (kind == 0) {
        pg.spend = SP_SEARCH;
        pg.sstate = SS_WAIT;
        pg.scode = PN_OK;
        pg_srch_rows_reset();
    } else {
        pg.spend = SP_PREVIEW;
        pg.loading = 1;
        pg_copy(pg.sp_url, sizeof pg.sp_url, kind == 1 ? text : "");
        pg_copy(pg.sp_id, sizeof pg.sp_id, kind == 2 ? id : "");
    }
    widget_set_prop_int(pg.sv, "yoffset", 0);
    pg_srch_apply();
    pg_srch_pump();
}

static void pg_srch_done(const char *text) {
    pg_copy(pg.sp_text, sizeof pg.sp_text, text);
    pg.sdone = 1;
    if (pg.fg) pg_srch_pending();
}

static void pg_srch_cancel(void) {
    if (!pg.sq[0]) pg.sback = 1; /* nothing was ever typed: the page goes back to the Shows level */
    if (pg.fg) pg_srch_pending();
}

/* What the keyboard's callbacks left, once the page is in front again (they run while its page is closing). */
static void pg_srch_pending(void) {
    if (!pg.win) return;
    if (pg.sdone) {
        pg.sdone = 0;
        pg_srch_submit(pg.sp_text);
    }
    if (pg.sback) {
        pg.sback = 0;
        if (pg.level == L_SRCH) {
            pg_srch_leave();
            pg_load_shows(1);
        }
    }
}

static void pg_srch_edit(void) {
    if (pg.level != L_SRCH || pg.dlg) return;
    keyboard_open(TR("Apple Podcasts"), TR("Search Apple Podcasts"), pg.sq, pg_srch_done, pg_srch_cancel, KB_LONG);
}

/* The 1 s tick of the level (lit screen only): a job that waits, the answer that came, a thumbnail that arrived, the preview that is ready. */
static void pg_srch_sync(void) {
    if (pg.spend) pg_srch_pump();
    if (pg.sstate == SS_RUN && pn_search_state() >= PN_S_THUMBS) { /* the answer is in (or failed, or was cancelled) */
        pg.sstate = SS_DONE;
        pg.scode = pn_search_code();
        pg_srch_rows_reset();
        widget_set_prop_int(pg.sv, "yoffset", 0);
        pg.sgen = pn_search_gen();
        pg_srch_apply();
    } else if (pg.sstate == SS_DONE && pn_search_gen() != pg.sgen) { /* a thumbnail arrived */
        pg.sgen = pn_search_gen();
        pg_kick();
        pg_redraw();
    }
    if (pg.loading && !pg.spend && !pn_job_busy() && pn_preview_state() == 2) {
        if (pn_preview_code() == PN_OK) {
            pg_open_preview();
        } else {
            pg.loading = 0;
            pg_srch_fail(pn_preview_code());
            pg_srch_apply();
        }
    }
    if (!pn_job_busy() && !pg.spend && pn_dl_waiting() && !pn_dl_running())
        pn_dl_start(); /* the downloads that paused go on */
}

/* A feed that is a show already (the same address, any case): its real Show page opens at once (the cells with their pills, the "..." and the sheets), no fetch and no preview; Back returns to the
 * results. 1 when it did. */
static int pg_open_subscribed(const char *feed) {
    int i;
    for (i = 0; i < pg.nshows; ++i)
        if (pg.shows[i].feed[0] && !strcasecmp(pg.shows[i].feed, feed)) {
            pg_srch_leave();
            pg_open_show(i, 0);
            pg.from_search = 1;
            return 1;
        }
    return 0;
}

/* The field's clear button: the text, the rows and what waits or runs go, the keyboard opens on the empty field. */
static void pg_srch_clear(void) {
    pg.sq[0] = 0;
    pg.aqh = 0;
    pg.spend = SP_NONE;
    pg.loading = 0;
    pg.sstate = SS_IDLE;
    if (pn_job_busy()) pn_cancel();
    pg_srch_rows_reset();
    pg_srch_apply();
    pg_srch_edit();
}

/* A tap on a part of the level: the field (it opens the keyboard; its clear button empties it first), a result with a feed address (its preview). */
static void pg_srch_tap(int a, int part) {
    const pj_result_t *r;
    if (part == PH_CLEAR) {
        pg_srch_clear();
        return;
    }
    if (part == PH_FIELD) {
        pg_srch_edit();
        return;
    }
    r = pn_search_result(a);
    if (!r || !r->feed[0] || pg.loading) return;
    if (pg_open_subscribed(r->feed)) return;
    pg.spend = SP_PREVIEW;
    pg.loading = 1;
    pg_copy(pg.sp_url, sizeof pg.sp_url, r->feed);
    pg.sp_id[0] = 0;
    pg_srch_apply();
    pg_srch_pump();
}

/* The preview: the held feed as a Show level (docs/modules/podcasts.md "Search"). The show is the spare slot after the folders' (shows[PC_MAX_SHOWS]); its folder name ".pv<hash>" makes the tone cache's key
 * its own, its cover is the search directory's preview.jpg (pg_has_tone_url), its episodes are the feed's items (remote, greyed, nothing to tap); the Latest Episode pill is Subscribe. */
static void pg_open_preview(void) {
    const pf_parser_t *p = pn_preview_parser();
    pc_show_t *s = &pg.shows[PC_MAX_SHOWS];
    pc_ep_t *all;
    int i, n;
    pg.loading = 0;
    if (!p) {
        pg_srch_fail(PN_NOTFEED);
        pg_srch_apply();
        return;
    }
    all = calloc(PF_KEEP + 1, sizeof *all);
    if (!all) {
        pg_srch_fail(PN_MEM);
        pg_srch_apply();
        return;
    }
    memset(s, 0, sizeof *s);
    pg_copy(s->title, sizeof s->title, pf_title(p)[0] ? pf_title(p) : pn_preview_feed());
    pg_copy(s->feed, sizeof s->feed, pn_preview_feed());
    pg_copy(s->image, sizeof s->image, pf_image(p));
    pg_copy(s->author, sizeof s->author, pf_author(p));
    pg_copy(s->category, sizeof s->category, pf_category(p));
    pg_copy(s->desc, sizeof s->desc, pf_summary(p));
    pc_fmt(s->dir, sizeof s->dir, ".pv%d", pc_hash(s->feed));
    if (pn_preview_cover()) pg_copy(s->cover, sizeof s->cover, "preview.jpg");
    s->hash = pc_hash(s->dir);
    if (pg_open_subscribed(s->feed)) { /* (an Apple link or a typed address that turns out to be a show already) */
        free(all);
        pn_preview_drop();
        return;
    }
    n = pf_items(p);
    for (i = 0; i < n; ++i) {
        const pf_item_t *it = pf_item(p, i);
        pc_ep_t *e = &all[i];
        pg_copy(e->title, sizeof e->title, it->title);
        pg_copy(e->desc, sizeof e->desc, it->desc);
        e->pub = it->pub, e->dur = it->dur, e->length = it->length;
        e->state = PC_REMOTE;
    }
    pg_srch_leave();
    pg.preview = 1;
    pg_open_show_with(PC_MAX_SHOWS, 0, all, n);
    pg.from_search = 1;
}

/* Back from a Show page opened from the search level (a preview, or a show subscribed already): the held feed is let go and the search level is as it was. */
static void pg_preview_close(void) {
    pg.preview = 0;
    pn_preview_drop();
    pg_load_search(0);
}

/* The Subscribe pill: the show is made from the held feed exactly as an import and its first refresh make it, and the page becomes its real Show page in place (the same level, at the top: the preview's
 * shorter cells do not line up with the real ones): the cells with their pills and badges, the "..." and the sheets as when it is opened from the grid. Back still returns to the results. */
static void pg_subscribe(void) {
    char dir[PC_FILE];
    int r, si;
    if (!pg.preview) return;
    r = pn_subscribe(pg.root, pg.shows, pg.nshows, dir, sizeof dir);
    if (r != PN_OK) {
        pg_srch_fail(r);
        return;
    }
    pg_scan();
    si = pg_show_of(dir);
    pg.preview = 0;
    pn_preview_drop();
    if (si < 0) {
        pg_load_shows(1);
        return;
    }
    pg_open_show(si, 0);
    pg.from_search = 1;
}

/* ---------------------------------------------------------------------------
 * The episode page (docs/modules/podcasts.md "The episode page"): a tap on a cell's body, on a subscribed show, a local show or a search preview, opens it in place on the Show level (Back returns to the
 * list at its scroll offset). The level stays L_EPS (the tint, the status bar, the sheets and the cover loader are the Show level's); pg.det says the content is the page: pg_content, pg_paint_det, pg_hit.
 * The full description is the episode's line of the show's .notes (one bounded scan), else the preview's held item, else the cell's x=.
 */
static unsigned pg_ep_key(const pc_ep_t *e) { return e->guid ? e->guid : pc_hash(e->file[0] ? e->file : e->title); }

static void pg_det_drop(void) {
    if (pg.det && pg.g.tiles) { /* (the show row's small cover: the grid is the list's again) */
        grid_drop(&pg.g);
        grid_shape(&pg.g, LIST_ART, LIST_R, 1);
    }
    free(pg.pd);
    pg.pd = (pd_t *)0;
    pg.det = 0;
}

/* The page's text for episode a into out (PF_NOTE + 1 bytes): .notes' line of its guid, or the held preview's item, else x=; "" when there is none. */
static void pg_det_note(int a, char *out) {
    const pc_ep_t *e = &pg.eps[a];
    char path[PC_FILE * 3 + 24];
    out[0] = 0;
    if (pg.preview) {
        const pf_parser_t *p = pn_preview_parser();
        if (p) pg_copy(out, PF_NOTE + 1, pf_note(p, a));
    } else if (e->guid && pg_join(path, sizeof path, pg.shows[pg.sel].dir, ".notes"))
        pno_read(path, e->guid, out, PF_NOTE + 1);
    if (!out[0]) pg_copy(out, PF_NOTE + 1, e->desc); /* (a feed refreshed before the notes existed, a local show) */
}

static void pg_det_open(int a) {
    const pc_ep_t *e;
    pd_t *d;
    char *note, when[40], date[48];
    if (a < 0 || a >= pg.neps || pg.det || pg.select || pg.sheet || pg.dlg) return;
    e = &pg.eps[a];
    d = calloc(1, sizeof *d);
    note = calloc(PF_NOTE + 1, 1);
    if (!d || !note) {
        free(d);
        free(note);
        pod_toast(TR("Not enough memory"));
        return;
    }
    pg_det_note(a, note);
    when[0] = 0;
    if (e->pub) pc_when(e->pub, (unsigned)time((long *)0), when, sizeof when);
    pd_date(date, sizeof date, when, e->length);
    pd_make(d, pg.st[ST_HEAD], pg.st[ST_META], pg.st[ST_SEC], e->title, pg.shows[pg.sel].title, date, note,
            TR("No description"), !pg.preview);
    free(note);
    grid_drop(&pg.g);
    grid_shape(&pg.g, PD_COVER, PD_COVER_R, 1);
    grid_placeholder(&pg.g);
    pg.pd = d;
    pg.det = a + 1;
    pg.det_off = pg_off();
    pg.det_key = pg_ep_key(e);
    pg.press = pg.down = 0;
    pg_nav();
    pg_size();
    widget_set_prop_int(pg.sv, "yoffset", 0);
    pg_tint_view();
    pg_collapse();
    pg_fade();
    pg_redraw();
    pg_kick();
}

/* Back from the episode page: the list at the offset it had. */
static void pg_det_close(void) {
    int max;
    if (!pg.det) return;
    pg_sheet_close();
    pg_det_drop();
    pg.press = pg.down = 0;
    pg_nav();
    pg_size();
    max = pg_content() - GRID_VIEW_H;
    widget_set_prop_int(pg.sv, "yoffset", pg.det_off > max ? (max > 0 ? max : 0) : pg.det_off);
    pg_tint_view(); /* (the Show page's tint and status bar colour come back) */
    pg_collapse();
    pg_fade();
    pg_redraw();
}

/* The episodes were read again while the page is open: it stays on its episode (found by its key); if the episode is gone the list is back. */
static void pg_det_refind(void) {
    int i;
    if (!pg.det) return;
    for (i = 0; i < pg.neps; ++i)
        if (pg_ep_key(&pg.eps[i]) == pg.det_key) {
            pg.det = i + 1;
            return;
        }
    pg_det_drop();
    widget_set_prop_int(pg.sv, "yoffset", pg.det_off);
    pg_tint_view();
}

/* ---------------------------------------------------------------------------
 * Select mode (the Show and Downloads levels), in the Playlists page's manner (docs/modules/playlists.md "Select mode"): the navbar's Back becomes the x, the title "N Selected", Select All at the
 * right, a mark on every row that can be marked, a bottom bar with one Delete pill and a confirm before anything is removed.
 */
static void pg_head(void) { /* the navbar's title: "N Selected" in select mode, else the level's */
    char buf[64];
    if (!pg.title) return;
    if (!pg.select) {
        if (pg.level == L_EPS)
            pg_title((const char *)0, pg.shows[pg.sel].title);
        else if (pg.level == L_SHOWS)
            pg_title("Podcasts", (const char *)0);
        else if (pg.level == L_DLS)
            pg_title(pg.subs ? "Subscriptions" : pg.saved ? "Saved" : "Downloads", (const char *)0);
        return;
    }
    pc_fmt(buf, sizeof buf, TR("%d Selected"), pg.npick);
    widget_set_text_utf8(pg.title, buf);
}

static void pg_select(int on) {
    int max;
    if (on == pg.select) return;
    if (on && !(pg.btn_selall && pg.bar && pg.del && pg.mark[0] && pg.mark[1])) return;
    pg.select = on;
    pg.npick = 0;
    memset(pg.pick, 0, sizeof pg.pick);
    pg.ncan = on ? pg_sel_scan(1) : 0;
    pg.press = pg.down = 0;
    pg_show(pg.btn_more, 0);
    pg_show(pg.np, !on);
    pg_show(pg.btn_selall, on);
    pg_show(pg.bar, on);
    pg_show(pg.del, on && !(pg.level == L_DLS &&
                            pg.subs)); /* the bar's one pill: Delete, or on the Subscriptions page Unsubscribe */
    pg_show(pg.unsubp, on && pg.level == L_DLS && pg.subs);
    if (pg.title && on)
        widget_resize(pg.title, SG_SELALL_X - NAV_TITLE_X,
                      22); /* (leaving select mode, pg_nav sets the width of the level) */
    if (pg.back) {
        widget_set_prop_str(pg.back, "style:normal:icon", on ? "ah_nav_close" : "ah_nav_back");
        widget_set_prop_str(pg.back, "style:over:icon", on ? "ah_nav_close" : "ah_nav_back");
        widget_set_prop_str(pg.back, "style:pressed:icon", on ? "ah_nav_close_down" : "ah_nav_back_down");
    }
    pg_head();
    if (!on) pg_nav();
    pg_title_show();
    grid_drop(&pg.g); /* the texts are made again at the other width */
    pg_cells_drop();
    pg_size();
    max = pg_content() - GRID_VIEW_H;
    if (max < 0) max = 0;
    if (pg_off() > max) widget_set_prop_int(pg.sv, "yoffset", max);
    pg_fade();
    pg_redraw();
}

static void pg_toggle_pick(int i) {
    if (i < 0 || i >= pg_count() || !pg_can_pick(i)) return;
    pg.pick[i >> 3] ^= (unsigned char)(1 << (i & 7));
    pg.npick += pg_is_pick(i) ? 1 : (unsigned)-1;
    pg_head();
    pg_redraw();
}

static int pg_on_selall(void *ctx, void *e) {
    int i, all;
    (void)ctx;
    (void)e;
    if (!pg.select) return RET_OK;
    all = pg.npick < pg.ncan; /* all that can be, unless all are: then none */
    memset(pg.pick, 0, sizeof pg.pick);
    pg.npick = 0;
    if (all)
        for (i = 0; i < pg_count() && i < PG_DLS_MAX; ++i)
            if (pg_can_pick(i)) pg.pick[i >> 3] |= (unsigned char)(1 << (i & 7)), ++pg.npick;
    pg_head();
    pg_redraw();
    return RET_OK;
}

static int pg_on_cancel(void *ctx, void *e);
static void pg_dls_back(void);

static int pg_on_back(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (!pg.win) return RET_OK;
    if (pg.dlg) return pg_on_cancel((void *)0, (void *)0); /* Back while the refresh dialog is up is its Cancel */
    if (pg.sheet)
        pg_sheet_close();
    else if (pg.det && pg.from_dls)
        pg_dls_back(); /* an episode page opened from the Downloads page goes back to it */
    else if (pg.det)
        pg_det_close(); /* the episode page goes back to the list */
    else if (pg.select)
        pg_select(0); /* the x leaves select mode first */
    else if (pg.level == L_EPS && pg.from_dls)
        pg_dls_back();
    else if (pg.level == L_EPS && pg.from_search)
        pg_preview_close(); /* a Show page opened from the search level goes back to it */
    else if (pg.level == L_EPS && pg.from_subs) {
        pg_load_subs(0); /* ... and one opened from the Subscriptions page goes back there, to where it was */
        widget_set_prop_int(pg.sv, "yoffset", pg.subs_off);
    } else if (pg.level == L_SRCH) {
        pg_srch_leave();
        pg_load_shows(1);
    } else if (pg.level != L_SHOWS)
        pg_load_shows(1); /* the Show and Downloads levels go back to the Shows level, where it was */
    else
        navigator_back();
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * The refresh dialog: a modal card over the page while the worker runs (docs/modules/podcasts.md "Feeds and the refresh dialog"). The worker only writes the status record; this reads it from a page-scoped
 * 200 ms timer (armed while the page is in front and the screen is lit; the 1 s tick re-arms it when the screen comes back), and closes itself when the worker has stopped.
 */
#define PG_DLG_MS 200

static void pg_dlg_show(int on) {
    pg_show(pg.dlg_scrim, on);
    pg_show(pg.dlg_card, on);
    pg.dlg = on;
}

/* The dialog's texts and bar from the status record. */
static void pg_dlg_update(void) {
    int done, total, i;
    unsigned permille, px;
    char line[48];
    unsigned hash = pn_current();
    pn_progress(&done, &total);
    if (total < 1) total = 1;
    if (done >= total) done = total - 1;
    if (hash &&
        hash !=
            pg.dlg_name_hash) { /* the show being fetched: its name in the list's words (the folder rename of a first refresh changes it later, the list is read again then) */
        for (i = 0; i < pg.nshows; ++i)
            if (pc_hash(pg.shows[i].feed) == hash) {
                widget_set_text_utf8(pg.dlg_name, pg.shows[i].title);
                break;
            }
        pg.dlg_name_hash = hash;
    }
    if (pn_cancelling())
        widget_set_text_utf8(pg.dlg_count, TR("Cancelling…"));
    else {
        pc_fmt2(line, sizeof line, TR("%d of %d"), (unsigned)(done + 1), (unsigned)total);
        widget_set_text_utf8(pg.dlg_count, line);
    }
    permille = ((unsigned)done * 1000 + pn_part()) / (unsigned)total;
    px = PD_BAR_W * permille / 1000;
    if (px < 1) px = 1;
    if (px != pg.dlg_px) {
        pg.dlg_px = px;
        widget_resize(pg.dlg_fill, (int)px, PD_BAR_H);
    }
}

/* The Show level after a refresh of its show: the folders are read again (the first refresh names an imported show and may rename its folder, a cover may have come) and the show is found by its feed
 * address; the page is made again at the same place. A show that is gone (it cannot be) leaves for the level below. */
static void pg_after_refresh(void) {
    int i, si = -1, off = pg_off();
    pg_scan();
    for (i = 0; pg.feed_hash && i < pg.nshows; ++i)
        if (pg.shows[i].feed[0] && pc_hash(pg.shows[i].feed) == pg.feed_hash) si = i;
    if (si >= 0)
        pg_open_show(si, off);
    else
        pg_load_shows(1);
}

/* The worker has stopped: the dialog goes, the rows are read again, one line says how it went. */
static void pg_dlg_finish(void) {
    unsigned ok, failed;
    int cancelled;
    char msg[96];
    const char *shown = msg;
    pg_dlg_show(0);
    pn_summary(&ok, &failed, &cancelled);
    pn_dl_start(); /* the downloads that paused for the refresh go on */
    pg_awake_arm();
    if (cancelled) {
        if (ok)
            pc_fmt(msg, sizeof msg, TR("Cancelled, %d updated"), ok);
        else
            shown = TR("Cancelled");
    } else if (!ok && !failed)
        msg[0] = 0;
    else if (!failed)
        pc_fmt(msg, sizeof msg, TR("%d updated"), ok);
    else if (!ok)
        pc_fmt(msg, sizeof msg, TR("%d failed"), failed);
    else
        pc_fmt2(msg, sizeof msg, TR("%d updated, %d failed"), ok, failed);
    if (pg.level == L_SHOWS)
        pg_load_shows(1);
    else if (pg.level == L_EPS)
        pg_after_refresh();
    pg_redraw();
    if (shown[0]) pod_toast(shown);
}

static int pg_dlg_tick(const void *timer) {
    (void)timer;
    if (!pg.win || !pg.fg || !pg.dlg ||
        !pod_screen_lit()) { /* behind another page, closed, or dark: no visual work; the page's tick starts this again */
        pg.dlg_timer = 0;
        return RET_OK;
    }
    if (!pn_busy()) {
        pg.dlg_timer = 0;
        pg_dlg_finish();
        return RET_OK;
    }
    pg_dlg_update();
    return RET_REPEAT;
}

static void pg_dlg_arm(void) {
    if (pg.dlg && !pg.dlg_timer) pg.dlg_timer = timer_add(pg_dlg_tick, (void *)0, PG_DLG_MS);
}

static void pg_dlg_open(void) {
    pg.dlg_name_hash = 0, pg.dlg_px = 0;
    widget_set_text_utf8(pg.dlg_name, "");
    widget_set_sensitive(pg.dlg_cancel, 1);
    pg_dlg_show(1);
    pg_dlg_update();
    pg_dlg_arm();
}

/* Cancel: the worker is asked to stop (the transfer in progress is aborted, no further show starts); the dialog stays, "Cancelling…", until it has. */
static int pg_on_cancel(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (!pg.dlg) return RET_OK;
    pn_cancel();
    widget_set_sensitive(pg.dlg_cancel, 0);
    if (pn_busy()) pg_dlg_update();
    pg_dlg_arm();
    return RET_OK;
}
/* The guards' words as a toast, for a refresh that did not start. */
static void pg_toast_code(int code) {
    if (code != PN_OK && code != PN_BUSY) pod_toast(pg_status_word(code));
}

/* Refresh the subscriptions (every show with a feed: the Shows level's refresh line; only those never refreshed after an import), or the show open (one: the Show level's Refresh Feed). */
static void pg_refresh_job(int only_new, int one) {
    int idx[PC_MAX_SHOWS], n = 0, i, r;
    if (pn_dl_running()) { /* downloads pause for a refresh (the queue stays, they go on when it ends): the refresh starts from the page's tick once the thread has stopped */
        pn_dl_pause();
        pg.rpend = only_new + 1;
        pg.rone = one;
        pg_awake_arm();
        pg_redraw();
        return;
    }
    if (one)
        idx[n++] = pg.sel;
    else
        for (i = 0; i < pg.nshows; ++i)
            if (pg.shows[i].feed[0] && (!only_new || !pg.shows[i].checked)) idx[n++] = i;
    r = pn_refresh(pg.root, pg.shows, idx, n);
    pg_toast_code(r);
    if (r == PN_OK && pn_busy()) pg_dlg_open();
    pg_redraw();
}

static void pg_refresh(int only_new) { pg_refresh_job(only_new, 0); }

/* The sheet's Import from Card: subscribe to what subscriptions.txt lists, then refresh the new ones. */
static void pg_import(void) {
    int n = pn_import(pg.root, pg.shows, pg.nshows);
    char msg[64];
    if (n < 0) {
        pod_toast(TR("Storage unavailable"));
        return;
    }
    if (!n) {
        pod_toast(TR("Nothing new to import"));
        return;
    }
    pc_fmt(msg, sizeof msg, TR("%d added"), (unsigned)n);
    pod_toast(msg);
    pg_load_shows(1);
    pg_refresh(1);
}

/* ---------------------------------------------------------------------------
 * Playing
 */
/* An stSongInfo of our own for episode e of the show open (strings duplicated; the deque copies them again and the caller frees these). */
static void pg_record(unsigned *rec, const pc_show_t *s, const pc_ep_t *e, const char *path) {
    memset(rec, 0, PG_REC_SIZE);
    *(char **)((char *)rec + REC_NAME) = strdup(e->file);
    *(char **)((char *)rec + REC_PATH) = strdup(path);
    *(char **)((char *)rec + REC_TITLE) = strdup(e->title);
    *(char **)((char *)rec + REC_ALBUM) = strdup(s->title);
    *(char **)((char *)rec + REC_ARTIST) = strdup(s->title);
    *(int *)((char *)rec + REC_TYPE) = 8;
    *(int *)((char *)rec + REC_CLASS) = 1;
}

static void pg_record_free(unsigned *rec) {
    static const int field[] = {REC_NAME, REC_PATH, REC_TITLE, REC_ALBUM, REC_ARTIST};
    unsigned i;
    for (i = 0; i < sizeof field / sizeof *field; ++i) free(*(char **)((char *)rec + field[i]));
}

static int pg_join_in(const char *root, char *out, unsigned size, const char *dir, const char *file) {
    unsigned n = 0, k;
    const char *parts[3];
    int p;
    parts[0] = root, parts[1] = dir, parts[2] = file;
    for (p = 0; p < 3; ++p) {
        if (p) out[n++] = '/';
        for (k = 0; parts[p][k]; ++k) {
            if (n + 2 >= size) return 0;
            out[n++] = parts[p][k];
        }
    }
    out[n] = 0;
    return 1;
}

static int pg_join(char *out, unsigned size, const char *dir, const char *file) {
    return pg_join_in(pg.root, out, size, dir, file);
}

/* A queue of the local episodes of show s (the list's order, from the first row, so Previous goes back up the list) with episode `at` of eps as the one to start: the queue (*idx its place in it), the resume
 * and the speed set as an episode start does, List play; NULL (a toast said why) when that episode is not on the card. root is the Podcasts folder (pc_root). Used by the Podcasts page (pg_play) and the Pod. */
void *pg_episode_queue(const char *root, const pc_show_t *s, const pc_ep_t *eps, int neps, int at, int *idx) {
    void *queue;
    int i, ok = 0;
    char path[PC_FILE * 2 + 40];
    if (at < 0 || at >= neps || eps[at].state != PC_LOCAL ||
        !pg_join_in(root, path, sizeof path, s->dir, eps[at].file) || access(path, F_OK)) {
        pod_toast(TR("Storage unavailable"));
        return (void *)0;
    }
    queue = _create_deque("stSongInfo");
    if (!queue) return queue;
    deque_init(queue);
    for (i = 0; i < neps; ++i) {
        unsigned rec[PG_REC_SIZE / 4];
        char p[PC_FILE * 2 + 40];
        if (eps[i].state != PC_LOCAL || !pg_join_in(root, p, sizeof p, s->dir, eps[i].file)) {
            if (i < at)
                --at; /* not on the card (the Show page lists those, greyed), or a name that does not fit (the model refused such names; this is the belt): not in the queue */
            continue;
        }
        pg_record(rec, s, &eps[i], p);
        _deque_push_back(queue, rec);
        pg_record_free(rec);
        ++ok;
    }
    if (!ok) {
        deque_destroy(queue);
        pod_toast(TR("Storage unavailable"));
        return (void *)0;
    }
    pc_restart(eps[at < neps ? at : 0].hash);
    pc_speed_apply(s->hash);
    pod_set_in_order_for_queue(); /* the episode queue loads next: the flag only */
    *idx = at;
    return queue;
}

/* Episode `at` and the ones after it: the queue, Now Playing. */
static void pg_play(int at) {
    void *queue;
    int idx;
    struct {
        void *dq;
        int idx, cls, mode;
    } context;
    queue = pg_episode_queue(pg.root, &pg.shows[pg.sel], pg.eps, pg.neps, at, &idx);
    if (!queue) return;
    *(int *)G_CLASS_TYPE = 1;
    context.dq = queue, context.idx = idx, context.cls = 1, context.mode = PLAY_MODE;
    navigator_to_with_context("playing_page", &context); /* start_player copies the queue */
    deque_destroy(queue);
}

/* A tap on a Continue Listening item: the episode plays from its place, as the Show page's resume pill does (the show's episodes are read for the queue; pg_play, then they are let go: the page stays on the Shows level). */
static void pg_cont_play(int i) {
    const struct pg_item *it;
    pc_ep_t *all;
    int m = 0, k, at = -1;
    if (i < 0 || i >= pg.ncont) return;
    it = &pg.cont[i];
    all = pg_eps_of(it->show, &m);
    if (!all) {
        pod_toast(TR("Not enough memory"));
        return;
    }
    for (k = 0; k < m; ++k)
        if (all[k].state == PC_LOCAL && all[k].hash == it->hash) at = k;
    if (at < 0) {
        free(all);
        pod_toast(TR("Storage unavailable"));
        return;
    }
    free(pg.eps);
    pg.eps = all, pg.neps = m, pg.sel = it->show;
    pg_play(at);
    free(pg.eps);
    pg.eps = (pc_ep_t *)0;
    pg.neps = 0;
}
/* ---------------------------------------------------------------------------
 * Touch
 */
/* What a touch hit: the row (Downloads), the cell (Show) or the part of the Shows level under it, -1 for none; on the Shows level the part is PH_LINE (the refresh line, a PP_LINE_HIT high touch across the page), PH_DLROW,
 * PH_SHELF (the item) or PH_CELL (the show); on the Show level which part of the cell (PH_*): the "..." (a PS_DOTS_HIT square), the state pill (its width and 7 px more above and below, for a 44 px target), the body. The
 * Latest Episode pill is cell 0's part PH_LATEST (above the cells). Select mode has the bodies only. */
static int pg_hit(void *e, int *part) {
    int pt[2], y;
    pt[0] = I(e, PE_X), pt[1] = I(e, PE_Y);
    widget_to_local(pg.view, pt);
    *part = PH_BODY;
    if (pg.level == L_SRCH) { /* the field, or a result that has a feed address (the others take no touch) */
        const pj_result_t *r;
        if (pt[0] >= PQ_FIELD_X && pt[0] < PQ_FIELD_X + PQ_FIELD_W && pt[1] >= PQ_FIELD_Y &&
            pt[1] < PQ_FIELD_Y + PQ_FIELD_H)
            return *part = pg.sq[0] && pt[0] >= PQ_FIELD_X + PQ_CLEAR_X ? PH_CLEAR : PH_FIELD, 0;
        y = pt[1] - PQ_TOP;
        if (y < 0) return -1;
        y /= PC_ROW_H;
        r = y < pg.srn ? pn_search_result(y) : (const pj_result_t *)0;
        return r && r->feed[0] ? y : -1;
    }
    if (pg.level == L_SHOWS) {
        int i, a, mid = PP_LINE_Y + PP_LINE_H / 2, cy = pg.y_shelf + PP_HEAD_PITCH;
        if (pg.has_line && pt[1] >= mid - PP_LINE_HIT / 2 && pt[1] < mid - PP_LINE_HIT / 2 + PP_LINE_HIT)
            return *part = PH_LINE, 0;
        for (i = 0; i < pg.ncont; ++i) {
            int x = PP_SHELF_X + i * PP_SHELF_PITCH;
            if (pt[0] >= x && pt[0] < x + PP_SHELF_W && pt[1] >= cy && pt[1] < cy + PP_SHELF_LEFT_Y + PP_SHELF_LEFT_H)
                return *part = PH_SHELF, i;
        }
        if (pt[1] >= pg.y_dl && pt[1] < pg.y_dl + PC_ROW_H) return *part = PH_DLROW, 0;
        if (pg.y_sub && pt[1] >= pg.y_sub && pt[1] < pg.y_sub + PC_ROW_H) return *part = PH_SUBROW, 1;
        if (pg.y_sav && pt[1] >= pg.y_sav && pt[1] < pg.y_sav + PC_ROW_H) return *part = PH_SAVROW, 2;
        a = grid_cell_at(pt[0], pt[1], pg.y_grid, pg.nshows);
        if (a >= 0) *part = PH_CELL;
        return a;
    }
    if (pg.level == L_EPS &&
        pg.det) { /* the episode page: its pill and its "..." (none in a preview); the rest of it takes no touch */
        int py = pt[1] - (pg.pd ? pg.pd->y_pill : 0), mid = PS_PILL_H / 2;
        pg_pill_t pl;
        if (!pg.pd || !pg.pd->y_pill || pg.det > pg.neps) return -1;
        if (pt[1] >= pg.pd->y_show && pt[1] < pg.pd->y_show + PD_SHOW_H) return *part = PH_SHOW, pg.det - 1;
        if (py < -7 || py >= PS_PILL_H + 7) return -1;
        if (pt[0] >= PS_DOTS_CX - PS_DOTS_HIT / 2 && pt[0] < PS_DOTS_CX + PS_DOTS_HIT / 2 &&
            py >= mid - PS_DOTS_HIT / 2 && py < mid + PS_DOTS_HIT / 2)
            return *part = PH_DOTS, pg.det - 1;
        pg_pill_of(&pg.eps[pg.det - 1], &pl);
        if (pt[0] >= PD_X - 4 && pt[0] < PD_X + pl.w + 4) return *part = PH_PILL, pg.det - 1;
        return -1;
    }
    if (pg.level == L_EPS) {
        const pg_hdr_t *h = pg.hdr;
        int row, cy, mid = PS_PILL_Y + PS_PILL_H / 2;
        if (!h) return -1;
        if (pt[1] < h->h) {
            if (!pg.select && h->has_latest && pt[1] >= h->y_latest - 2 && pt[1] < h->y_latest + PS_LATEST_H + 2) {
                pg_pill_t lp;
                pg_latest(&lp);
                if (pt[0] >= (PG_W - lp.w) / 2 && pt[0] < (PG_W + lp.w) / 2) {
                    *part = PH_LATEST;
                    return 0;
                }
            }
            return -1;
        }
        row = (pt[1] - h->h) / pg_cell_h();
        if (row >= pg.neps) return -1;
        cy = (pt[1] - h->h) % pg_cell_h();
        if (!pg.select && !pg.preview) {
            if (pt[0] >= PS_DOTS_CX - PS_DOTS_HIT / 2 && pt[0] < PS_DOTS_CX + PS_DOTS_HIT / 2 &&
                cy >= mid - PS_DOTS_HIT / 2 && cy < mid + PS_DOTS_HIT / 2)
                *part = PH_DOTS;
            else if (cy >= PS_PILL_Y - 7 && cy < PS_PILL_Y + PS_PILL_H + 7) {
                pg_pill_t pl;
                pg_pill_of(&pg.eps[row], &pl);
                if (pt[0] >= PS_CELL_X - 4 && pt[0] < PS_CELL_X + pl.w + 4) *part = PH_PILL;
            }
        }
        return row;
    }
    return pg_dhit(pt[1]); /* (the Downloads level and the Subscriptions page) */
}

static void pg_set_press(int p) {
    if (pg.press == p) return;
    pg.press = p;
    pg_redraw();
}

static int pg_on_down(void *ctx, void *e) {
    int a, part;
    (void)ctx;
    pg.down = 0;
    if (!e || !pg.view) return RET_OK;
    a = pg_hit(e, &part);
    pg.down = a + 1; /* (-1: nothing) */
    pg.down_part = part;
    pg.down_x = I(e, PE_X), pg.down_y = I(e, PE_Y);
    if (a >= 0 && !pg.select &&
        (pg.level == L_SHOWS  ? part == PH_DLROW || part == PH_SUBROW || part == PH_SAVROW
         : pg.level == L_SRCH ? part == PH_BODY
                              : pg.level != L_EPS || part == PH_BODY))
        pg_set_press(
            pg.level == L_DLS
                ? pg.ord[a] + 1
                : a + 1); /* (the Shows level presses only its Library rows; the Downloads level's tiles are keyed by slot) */
    return RET_OK;
}

/* A tap on an episode that is not on the card: a queued or running download is cancelled (its .part stays, a later tap resumes it); anything else (not downloaded, Paused, Failed) is queued. */
static void pg_dl_toggle(const char *dir, const char *file) {
    unsigned key, got, total;
    int code, st, r;
    if (!file[0]) return;
    key = pn_dl_key(dir, file);
    st = pn_dl_state(key, &code, &got, &total);
    if (st == PN_DL_WAIT || st == PN_DL_ACTIVE)
        pn_dl_cancel(key);
    else {
        r = pn_dl_add(pg.root, dir, file);
        if (r != PN_OK) pod_toast(pg_dl_word(r));
        pg_awake_arm();
    }
}

/* A tap on a Downloaded row: the episode's page (the Show level's, as a tap on a cell's body opens it; its pill plays). The page remembers where the Downloads page was: Back returns there (pg_dls_back). A file that has gone
 * since the scan takes its row away. */
static void pg_dls_open_ep(int a) {
    int si = pg_row(a)->si, m = 0, k, at = -1;
    char file[PC_FILE];
    pc_ep_t *all;
    file[0] = 0;
    pg_cat(file, sizeof file, pg_row(a)->file);
    all = pg_eps_of(si, &m);
    if (!all) {
        pod_toast(TR("Not enough memory"));
        return;
    }
    for (k = 0; k < m; ++k)
        if (all[k].state == PC_LOCAL && !strcmp(all[k].file, file)) at = k;
    if (at < 0) {
        free(all);
        pg_dls_sync();
        return;
    }
    pg.dls_off = pg_off();
    pg.from_dls = 1;
    pg.preview = 0;
    pg_open_show_with(si, 0, all, m);
    pg_det_open(at);
}

/* Back from the episode page (or from the list of its show, once the episode is gone) to the Downloads page, where it was left: the rows are as they were (the scan's, kept) brought up to date by pg_dls_sync, the scroll
 * position is the one the tap left. */
static void pg_dls_back(void) {
    int off = pg.dls_off, max;
    pg.from_dls = 0;
    pg_leave_show();
    grid_drop(&pg.hg);
    grid_drop(&pg.g);
    pg_cells_drop();
    free(pg.eps);
    pg.eps = (pc_ep_t *)0;
    pg.neps = 0;
    pg.press = pg.down = 0;
    pg.level = L_DLS;
    pg.subs = 0;
    grid_shape(&pg.g, LIST_ART, LIST_R, 1);
    grid_placeholder(&pg.g);
    pg_title(pg.saved ? "Saved" : "Downloads", (const char *)0);
    pg_show(pg.view, 1);
    pg_show(pg.status, 0);
    if (pg.saved) { /* the episode may have been unsaved (or saved) since: the page is made again, at the offset it was left */
        pg_load_downloads(0);
        pg.want_off = off;
        pg_dls_apply();
        pg_collapse();
        pg_fade();
        return;
    }
    pg_dls_sync();
    max = pg_content() - GRID_VIEW_H;
    if (max < 0) max = 0;
    widget_set_prop_int(pg.sv, "yoffset", off > max ? max : off);
    pg_collapse();
    pg_fade();
    pg_redraw();
    pg_kick();
}

/* A tap on a row of the Downloads level: an In Progress row does what it does on the Show level (a running or waiting one is paused, a paused one resumes, a failed one is tried again); a Downloaded row opens the
 * episode's page; on the Subscriptions page a tap opens the show. */
static void pg_dls_tap(int a) {
    if (pg.subs) {
        pg.subs_off = pg_off();
        pg.from_subs = 1;
        pg_open_show(pg_row(a)->si, 0);
        return;
    }
    if (pg_is_dld(a)) {
        pg_dls_open_ep(a);
        return;
    }
    pg_dl_toggle(pg_row(a)->dir, pg_row(a)->file);
    pg_dls_sync();
}

extern int pod_confirm(const char *text); /* patch/m1plus.c: the stock confirm dialog, modal; nonzero for Yes */

/* Whether the player has this file (the stock playing record's path, as the tag reader and the resume code compare). */
static int pg_playing(const char *path) {
    void *t = cc_playing();
    const char *p = t ? *(const char **)((char *)t + REC_PATH) : (const char *)0;
    return p && !strcasecmp(p, path);
}

/* The Delete pill of the select bar, after a confirm (No: the mode stays). Show level: each marked episode's file and .part are unlinked (a .part marked alone is a paused download taken away); the
 * `.episodes` line stays, so the episode is a remote one again, greyed and downloadable; its resume place and played mark are forgotten (pc_mark: it starts fresh when downloaded again). The episode
 * the player is on is never deleted (it is skipped, with a toast). Downloads level: a waiting one leaves the queue, a paused or failed one loses its .part and its failure. */
static int pg_on_delete(void *ctx, void *e) {
    int i, kept = 0, files = 0;
    unsigned char gone[PG_DLS_MAX]; /* the Downloads level's rows taken off the list */
    (void)ctx;
    (void)e;
    if (!pg.select || !pg.npick) return RET_OK;
    for (i = 0; pg.level == L_DLS && i < pg.nrows && i < PG_DLS_MAX; ++i)
        files |= pg_is_dld(i) && pg_is_pick(i); /* (a Downloaded row among the marks: the files go) */
    if (!pod_confirm(pg.level == L_DLS && !files ? TR("Remove the selected downloads?")
                                                 : TR("Delete the selected episodes?")))
        return RET_OK;
    memset(gone, 0, sizeof gone);
    for (i = 0; i < pg_count() && i < PG_DLS_MAX; ++i) {
        char path[PC_FILE * 3 + 24];
        const struct pg_dl *d = pg.level == L_DLS ? pg_row(i) : (const struct pg_dl *)0;
        int dld = d && pg_is_dld(i);
        const char *dir = d ? d->dir : pg.shows[pg.sel].dir, *file = d ? d->file : pg.eps[i].file;
        unsigned key = d && !dld ? d->key : pn_dl_key(dir, file),
                 hash = dld ? d->hash : (pg.level == L_EPS && pg.eps[i].state == PC_LOCAL ? pg.eps[i].hash : 0);
        if (!pg_is_pick(i) || !pg_can_pick(i) || !pg_join(path, sizeof path - 6, dir, file)) continue;
        if ((dld || pg.level == L_EPS) && pg_playing(path)) {
            ++kept;
            continue;
        }
        pn_dl_cancel(key); /* a waiting one leaves the queue */
        if (dld || pg.level == L_EPS) unlink(path);
        pg_cat(path, sizeof path, ".part");
        unlink(path);
        pn_dl_clear(key);
        if (hash) pc_mark(hash, 0);
        gone[i] = 1;
    }
    pc_flush();
    pg_select(0);
    if (pg.level == L_DLS) { /* the rows leave the lists (Downloaded first: In Progress shifts the slots) */
        for (i = pg.nrows - 1; i >= pg.nip; --i)
            if (gone[i]) pg_dld_remove(i - pg.nip);
        for (i = pg.nip - 1; i >= 0; --i)
            if (gone[i]) pg_ip_remove(i);
        pg_dls_apply();
    } else
        pg_reload_eps();
    if (kept) pod_toast(TR("The playing episode was kept"));
    return RET_OK;
}

/* Delete Played Episodes (the Downloads page's sheet), after a confirm: every Downloaded episode that is played goes (its file; the `.episodes` line stays, so the episode is a remote one again; the played mark is
 * forgotten as the select mode's Delete forgets it), except the one the player is on. The toast says how many and how much space that freed (the rows the page lists: its cap is PG_DLD_MAX). */
static void pg_delete_played(void) {
    int k, n = 0, kept = 0;
    unsigned freed = 0;
    char msg[96], sz[24];
    if (pg.level != L_DLS || pg.subs || pg.saved || pg.dscan_on || pg.select) return;
    if (!pod_confirm(TR("Delete all played episodes?"))) return;
    for (k = pg.nd - 1; k >= 0; --k) {
        const struct pg_dl *d = &pg.dls[pg.dord[k]];
        unsigned pos, len, hash = d->hash, kb = d->kb;
        char path[PC_FILE * 3 + 24];
        if (!hash || pc_state(hash, &pos, &len) != PC_DONE || !pg_join(path, sizeof path, d->dir, d->file)) continue;
        if (pg_playing(path)) {
            ++kept;
            continue;
        }
        unlink(path);
        pc_mark(hash, 0);
        freed += kb, ++n;
        pg_dld_remove(k);
    }
    pc_flush();
    pg_dls_apply();
    if (!n) {
        if (kept) pod_toast(TR("The playing episode was kept"));
        return;
    }
    pg_kb_text(sz, sizeof sz, freed);
    snprintf(msg, sizeof msg, TR("%d deleted, %s freed"), n, sz);
    if (!pg_fits(pg.st_sub, msg,
                 300)) { /* (the stock toast is one line of 300 px at 18 px: the count alone where that is too wide) */
        msg[0] = 0;
        pc_fmt(msg, sizeof msg, TR("%d deleted"), (unsigned)n);
    }
    pod_toast(msg);
}

static const char *const pg_speed_name[PC_SPEEDS] = {"1\xc3\x97", "1.25\xc3\x97", "1.5\xc3\x97",
                                                     "2\xc3\x97"}; /* "1x" with the multiplication sign U+00D7 */

/* ---------------------------------------------------------------------------
 * The Show page's bottom sheets (docs/modules/podcasts.md "The Show page"; the look is Now Playing's More sheet): one widget set of the asset (tools/pod_ui.py podcasts_sheet), nine fixed rows of
 * which each sheet shows the ones that apply, placed from the card's top, the card as high as its rows over the window's bottom edge. The show's "..." opens the show's: Playback Speed (a tap cycles
 * and the sheet stays), Refresh Feed, Select Episodes, Mark All as Played, Unsubscribe. A cell's "..." opens that episode's: Download or Remove Download, Mark as Played or Unplayed.
 */
static const char *const pg_row_id[PG_SHEET_ROWS] = {"speed", "refresh", "select", "markall",   "unsub",  "dl",  "rm",
                                                     "mark",  "unmark",  "import", "delplayed", "export", "save"};

static void pg_sheet_close(void) {
    if (!pg.sheet) return;
    pg.sheet = SH_NONE;
    pg_show(pg.sh_scrim, 0);
    pg_show(pg.sh_card, 0);
}

/* The grey value of row i (a value label v: 0 speed, 1 refresh), right aligned to x PS_SHEET_VALUE_R, in the room the row's label leaves (the label keeps its whole text), cut with an ellipsis by
 * the label when wider. The value label is as wide as its text (the asset gives these labels no margins: stock's 2 px each side would cut it) and the row's label ends PS_SHEET_GAP before it. */
static void pg_sheet_value(int i, int v, const char *text) {
    const unsigned *w;
    int lw = 0, vw = 0, room;
    if (!pg.sh_vl[v]) return;
    w = widget_get_text(pg.sh_tx[i]);
    if (w && *w) lw = pg_width(pg.sh_tx[i], w);
    room = PS_SHEET_VALUE_R - PS_SHEET_TEXT_X - lw - PS_SHEET_GAP;
    widget_set_text_utf8(pg.sh_vl[v], text);
    w = widget_get_text(pg.sh_vl[v]);
    if (w && *w) vw = pg_width(pg.sh_vl[v], w);
    if (vw > room) vw = room > 0 ? room : 0;
    widget_move(pg.sh_vl[v], PS_SHEET_VALUE_R - vw, 0);
    widget_resize(pg.sh_vl[v], vw, PM_ROW_H);
    widget_resize(pg.sh_tx[i], PS_SHEET_VALUE_R - PS_SHEET_TEXT_X - vw - (vw ? PS_SHEET_GAP : 0), PM_ROW_H);
}

/* Show the rows (ids, in order) and the card that holds them: PM_ROW_H each from the card's top, the first without its hairline, the glass picture of that height. */
static void pg_sheet_rows(const int *rows, int n) {
    static const char *const glass[] = {"", "pc_sheet1", "pc_sheet2", "pc_sheet3", "pc_sheet4", "pc_sheet5"};
    int i, k, h = n * PM_ROW_H;
    for (i = 0; i < PG_SHEET_ROWS; ++i) {
        int at = -1;
        for (k = 0; k < n; ++k)
            if (rows[k] == i) at = k;
        if (at < 0) {
            pg_show(pg.sh_row[i], 0);
            continue;
        }
        widget_move(pg.sh_row[i], 0, at * PM_ROW_H);
        pg_show(pg.sh_row[i], 1);
        widget_set_visible(pg.sh_hr[i], at > 0, 0);
    }
    widget_move(pg.sh_card, 0, AH_WIN_H - h);
    widget_resize(pg.sh_card, PG_W, h);
    widget_set_prop_str(pg.sh_card, "style:normal:bg_image", glass[n]);
    pg_show(pg.sh_scrim, 1);
    pg_show(pg.sh_card, 1);
}

static int pg_any_unplayed(void) {
    unsigned pos, len;
    int i;
    for (i = 0; i < pg.neps; ++i)
        if (pg_ep_hash(&pg.eps[i]) && pg_ep_state(&pg.eps[i], &pos, &len) != PC_DONE) return 1;
    return 0;
}

/* Save / Unsave Episode (docs/modules/podcasts.md "Saved"): the star button's own calls on stock's favourites table (manage_myfav 0x4ef884: checkFavExist, then deleteMusicFromFav or addMyFav, on the record) with
 * the record the episode plays as (pg_record: the same name and path, so the star in Now Playing sees it as saved). Only an episode on the card can be saved. pg_save_state: 1 saved, 0 not, -1 cannot. */
static int pg_save_rec(int ep, unsigned *rec) {
    char path[PC_FILE * 2 + 40];
    if (ep < 0 || ep >= pg.neps || pg.eps[ep].state != PC_LOCAL ||
        !pg_join(path, sizeof path, pg.shows[pg.sel].dir, pg.eps[ep].file))
        return 0;
    pg_record(rec, &pg.shows[pg.sel], &pg.eps[ep], path);
    return 1;
}

static int pg_save_state(int ep) {
    unsigned rec[PG_REC_SIZE / 4];
    int on;
    if (!pg_save_rec(ep, rec)) return -1;
    on = checkFavExist(rec) != 0;
    pg_record_free(rec);
    return on;
}

static void pg_save_toggle(int ep) {
    unsigned rec[PG_REC_SIZE / 4];
    if (!pg_save_rec(ep, rec)) return;
    if (checkFavExist(rec)) {
        deleteMusicFromFav(rec);
    } else {
        addMyFav(rec);
        pod_toast(TR("Saved"));
    }
    pg_record_free(rec);
}

/* The sheet of the show (SH_SHOW) or of episode ep (SH_CELL). */
static void pg_sheet_open(int kind, int ep) {
    int rows[PG_SHEET_ROWS], n = 0, k;
    unsigned pos, len;
    char text[96];
    if (!pg.sh_card || pg.sheet ||
        (kind == SH_HOME   ? pg.level != L_SHOWS
         : kind == SH_SUBS ? pg.level != L_DLS || !pg.subs
         : kind == SH_DLS  ? pg.level != L_DLS || pg.subs || pg.saved
                           : pg.level != L_EPS) ||
        pg.dlg || pg.select || pg.preview)
        return;
    pg.sheet = kind, pg.sh_ep = ep;
    if (kind == SH_HOME) {
        /* Import from Card while the card has a subscriptions.txt or an OPML file (the only row: the Subscriptions page is a Library row of the Shows page). Add Show is not a row: round 3's search is the navbar's Search button. */
        if (pg.has_import) rows[n++] = SR_IMPORT;
        if (!n) {
            pg.sheet = SH_NONE;
            return;
        }
    } else if (kind == SH_DLS) {
        /* The Downloads page's sheet: Select (the select mode's Delete) and Delete Played Episodes (once the scan has finished and a Downloaded row is played). */
        int i, played = 0;
        unsigned c = pg_sel_scan(0);
        widget_set_text_utf8(pg.sh_tx[SR_SELECT], TR("Select"));
        if (c && pg.bar) rows[n++] = SR_SELECT;
        for (i = pg.nip; !pg.dscan_on && i < pg.nrows && !played; ++i) played = pg_played_row(i);
        if (played) rows[n++] = SR_DELPLAYED;
        if (!n) {
            pg.sheet = SH_NONE;
            return;
        }
    } else if (kind == SH_SUBS) {
        /* The Subscriptions page's sheet: Select Shows (the select mode's Unsubscribe) and Export OPML. */
        widget_set_text_utf8(pg.sh_tx[SR_SELECT], TR("Select Shows"));
        if (pg.nrows && pg.unsubp) rows[n++] = SR_SELECT;
        if (pg.nrows) rows[n++] = SR_EXPORT;
        if (!n) {
            pg.sheet = SH_NONE;
            return;
        }
    } else if (kind == SH_SHOW) {
        const pc_show_t *s = &pg.shows[pg.sel];
        widget_set_text_utf8(pg.sh_tx[SR_SELECT],
                             TR("Select Episodes")); /* (the row is shared with the Subscriptions page's) */
        rows[n++] = SR_SPEED;
        pg_sheet_value(SR_SPEED, 0, pg_speed_name[pc_speed_get(s->hash)]);
        if (s->feed[0]) {
            rows[n++] = SR_REFRESH;
            text[0] = 0;
            if (s->checked) /* "1h ago" */
                pc_when(s->checked, (unsigned)time((long *)0), text, sizeof text);
            else
                pg_cat(text, sizeof text, TR("Never refreshed"));
            pg_sheet_value(SR_REFRESH, 1, text);
        }
        if (pg_sel_scan(0) > 0) rows[n++] = SR_SELECT;
        if (pg_any_unplayed()) rows[n++] = SR_MARKALL;
        if (s->feed[0]) rows[n++] = SR_UNSUB;
    } else {
        const pc_ep_t *e = &pg.eps[ep];
        if (e->state == PC_REMOTE) {
            rows[n++] = SR_DL;
            text[0] = 0;
            pg_cat(text, sizeof text, TR("Download"));
            if (e->length) { /* "Download - 48 MB" */
                char size[24];
                pg_cat(text, sizeof text, " \xc2\xb7 ");
                pc_fmt(size, sizeof size, TR("%d MB"), (e->length + 1048575) >> 20);
                pg_cat(text, sizeof text, size);
            }
            widget_set_text_utf8(pg.sh_tx[SR_DL], text);
        } else
            rows[n++] = SR_RM;
        if (!pg.preview && (k = pg_save_state(ep)) >= 0) {
            rows[n++] = SR_SAVE;
            widget_set_text_utf8(pg.sh_tx[SR_SAVE], TR(k ? "Unsave Episode" : "Save Episode"));
        }
        if (pg_ep_hash(e)) rows[n++] = pg_ep_state(e, &pos, &len) == PC_DONE ? SR_UNMARK : SR_MARK;
    }
    pg_sheet_rows(rows, n);
}

static void pg_speed_cycle(void) {
    const pc_show_t *s = &pg.shows[pg.sel];
    int mode = (pc_speed_get(s->hash) + 1) % PC_SPEEDS;
    if (!pc_speed_set(s->hash, mode)) pod_toast(TR("Storage unavailable"));
    mode = pc_speed_get(s->hash);
    pg_sheet_value(SR_SPEED, 0, pg_speed_name[mode]);
    pc_speed_apply(
        s->hash); /* an episode of this show that plays: the decoder takes it at the next start; the stock page shows it */
    pg_redraw();
}

/* A tap on an episode's download pill, a Latest Episode pill that is not on the card, or the sheet's Download: a queued or running download is cancelled, anything else is queued (pg_dl_toggle). */
static void pg_dl_tap(int a) {
    pg_dl_toggle(pg.shows[pg.sel].dir, pg.eps[a].file);
    pg_redraw();
}

/* Remove Download (an episode's sheet): its file and its .part go, a download of it is taken out of the queue; the .episodes line stays, so the cell is a download cell again; its resume place and
 * played mark are forgotten, as the select mode's Delete does. The playing episode is never removed. */
static void pg_remove(int ep) {
    const pc_ep_t *e;
    char path[PC_FILE * 3 + 24];
    unsigned key, hash;
    if (ep < 0 || ep >= pg.neps) return;
    e = &pg.eps[ep];
    if (!e->file[0] || !pg_join(path, sizeof path - 6, pg.shows[pg.sel].dir, e->file)) return;
    if (e->state == PC_LOCAL && pg_playing(path)) {
        pod_toast(TR("The playing episode was kept"));
        return;
    }
    key = pn_dl_key(pg.shows[pg.sel].dir, e->file);
    hash = e->state == PC_LOCAL ? e->hash : 0;
    pn_dl_cancel(key);
    unlink(path);
    pg_cat(path, sizeof path, ".part");
    unlink(path);
    pn_dl_clear(key);
    if (hash) pc_mark(hash, 0);
    pc_flush();
    pg_reload_eps();
}

/* Mark All as Played: every episode the show knows that has a file name (one not on the card too: the mark belongs to the path, which a later download takes). */
static void pg_mark_all(void) {
    unsigned pos, len, hash;
    int i;
    for (i = 0; i < pg.neps; ++i) {
        hash = pg_ep_hash(&pg.eps[i]);
        if (hash && pg_ep_state(&pg.eps[i], &pos, &len) != PC_DONE) pc_mark(hash, 1);
    }
    pc_flush();
    pg_redraw();
}

/* Unsubscribe (after a confirm): the show is no longer a subscription (its .show loses feed=, so it is not refreshed), the .episodes stay (the titles and dates of the files left on the
 * card), the .part files and the queued downloads of the show go; with no episode file left the show's own files (.show, .episodes, cover.jpg) and the folder (when nothing else is in it) go too and the
 * page returns to the level below; else it stays, reading the show again. The playing episode is a file that stays. */
static void pg_unsub(void) {
    const pc_show_t *s = &pg.shows[pg.sel];
    char dir[PC_FILE], path[PC_FILE * 3 + 24];
    int i, left = 0, off = pg_off();
    static const char *const own[] = {".show", ".episodes", ".notes", "cover.jpg"};
    if (!s->feed[0] || pn_busy() || !pod_confirm(TR("Unsubscribe from this show?"))) return;
    memcpy(dir, s->dir, sizeof dir);
    if (!pn_unsubscribe(pg.root, s)) { /* (first: a .show that cannot be written changes nothing else) */
        pod_toast(TR("Storage unavailable"));
        return;
    }
    for (i = 0; i < pg.neps; ++i) {
        const pc_ep_t *e = &pg.eps[i];
        unsigned key;
        if (!e->file[0]) continue;
        key = pn_dl_key(dir, e->file);
        pn_dl_cancel(key);
        if (pg_join(path, sizeof path - 6, dir, e->file)) {
            pg_cat(path, sizeof path, ".part");
            unlink(path);
        }
        pn_dl_clear(key);
        left += e->state == PC_LOCAL;
    }
    if (!left) {
        for (i = 0; i < (int)(sizeof own / sizeof *own); ++i)
            if (pg_join(path, sizeof path, dir, own[i])) unlink(path);
        if (pg_join(path, sizeof path, dir, "")) {
            unsigned n = 0;
            while (path[n]) ++n;
            if (n && path[n - 1] == '/') path[n - 1] = 0;
            rmdir(path);
        }
    }
    pg_scan();
    for (i = 0; left && i < pg.nshows; ++i)
        if (!strcmp(pg.shows[i].dir, dir)) {
            pg_open_show(i, off); /* (it is no subscription now) */
            return;
        }
    pg_load_shows(1);
}

/* The Subscriptions page's Export OPML: Podcasts/subscriptions-export.opml (pn_export), and a toast, "Exported 5 shows". The file name does not fit the stock one-line toast (300 px at 18 px: "Exported 5 shows:
 * subscriptions-export.opml" is about 380 px in English and wider in the other languages, test/pod/pcsubs.py width_tests), so it is in the docs. */
static void pg_export(void) {
    char msg[96];
    int n = 0;
    if (!pn_export(pg.root, pg.shows, pg.nshows, &n)) {
        pod_toast(TR("Storage unavailable"));
        return;
    }
    pc_fmt(msg, sizeof msg, TR(n == 1 ? "Exported %d show" : "Exported %d shows"), (unsigned)n);
    pod_toast(msg);
}

/* The select bar's Unsubscribe pill (the Subscriptions page), after a confirm: each marked show as the Show page's Unsubscribe does it (pn_unsubscribe_show: feed= dropped, the episode files kept, the folder removed when
 * nothing is left; no audio file is ever deleted, so never the playing episode). The page reads its rows again; a show that could not be written stays and says so. */
static int pg_on_unsubs(void *ctx, void *e) {
    int i, failed = 0;
    (void)ctx;
    (void)e;
    if (!pg.win || !pg.select || !pg.npick || pg.level != L_DLS || !pg.subs || pn_busy()) return RET_OK;
    if (!pod_confirm(TR("Unsubscribe from these shows?"))) return RET_OK;
    for (i = 0; i < pg.nrows && i < PG_DLS_MAX; ++i)
        if (pg_is_pick(i) && pg_can_pick(i) && !pn_unsubscribe_show(pg.root, &pg.shows[pg_row(i)->si])) ++failed;
    pg_select(0);
    pg_load_downloads(1);
    if (failed) pod_toast(TR("Storage unavailable"));
    return RET_OK;
}

static int pg_on_sheet_scrim(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    pg_sheet_close();
    return RET_OK;
}

static int pg_on_sheet_row(void *ctx, void *e) {
    int id = (int)(unsigned)ctx - 1, ep = pg.sh_ep;
    unsigned hash;
    (void)e;
    if (!pg.win || !pg.sheet || id < 0 || id >= PG_SHEET_ROWS) return RET_OK;
    if (id == SR_SPEED) { /* a tap cycles; the sheet stays */
        pg_speed_cycle();
        return RET_OK;
    }
    pg_sheet_close();
    switch (id) {
    case SR_REFRESH:
        if (pg.shows[pg.sel].feed[0]) pg_refresh_job(0, 1);
        break;
    case SR_IMPORT:
        if (pg.level == L_SHOWS && !pn_busy()) pg_import();
        break;
    case SR_DELPLAYED:
        pg_delete_played();
        break;
    case SR_EXPORT:
        if (pg.level == L_DLS && pg.subs) pg_export();
        break;
    case SR_SELECT:
        pg_select(1);
        break;
    case SR_MARKALL:
        pg_mark_all();
        break;
    case SR_UNSUB:
        pg_unsub();
        break;
    case SR_DL:
        if (ep >= 0 && ep < pg.neps) pg_dl_tap(ep);
        break;
    case SR_RM:
        pg_remove(ep);
        break;
    case SR_SAVE:
        pg_save_toggle(ep);
        break;
    default: /* Mark as Played / Unplayed */
        hash = ep >= 0 && ep < pg.neps ? pg_ep_hash(&pg.eps[ep]) : 0;
        if (hash) {
            pc_mark(hash, id == SR_MARK);
            pc_flush();
            pg_redraw();
        }
    }
    return RET_OK;
}

/* The navbar's globe: the search level (Apple Podcasts; only while Podcast Search is on). */
static int pg_on_globe(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (pg.win && pg.level == L_SHOWS && pg.searchon && !pg.select && !pg.dlg && !pg.sheet) pg_load_search(1);
    return RET_OK;
}

static int pg_on_more(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (pg.win && pg.level == L_EPS && !pg.select)
        pg_sheet_open(SH_SHOW, 0);
    else if (pg.win && pg.level == L_SHOWS)
        pg_sheet_open(SH_HOME, 0);
    else if (pg.win && pg.level == L_DLS && !pg.select && !pg.saved)
        pg_sheet_open(pg.subs ? SH_SUBS : SH_DLS, 0);
    return RET_OK;
}

/* A tap on a part of cell a of the Show level (select mode taps are the marks'): the Latest Episode pill, the "...", the state pill (play it, or what its state says: download, pause, resume, retry), the
 * body (play it when it is on the card; a cell that is not does nothing: only the pill and the "..." download). */
static void pg_cell_tap(int a, int part) {
    const pc_ep_t *e;
    if (pg.preview) { /* the preview: the Subscribe pill and nothing else */
        if (part == PH_LATEST)
            pg_subscribe();
        else if (part == PH_BODY)
            pg_det_open(a);
        return;
    }
    if (part ==
        PH_SHOW) { /* the episode page's show row: the show's own page (from the Downloads page too: Back is still that page's) */
        pg_det_close();
        return;
    }
    e = &pg.eps[part == PH_LATEST ? 0 : a];
    if (part == PH_DOTS)
        pg_sheet_open(SH_CELL, a);
    else if (part == PH_BODY)
        pg_det_open(a); /* (the cell's body opens the episode page, on the card or not) */
    else if (e->state == PC_LOCAL)
        pg_play(part == PH_LATEST ? 0 : a);
    else
        pg_dl_tap(part == PH_LATEST ? 0 : a);
}

/* A tap on a part of the Shows level: the refresh line runs Refresh All (the guards' words as toasts, the progress dialog; nothing while a refresh runs or waits), the Downloads row and the Subscriptions row open
 * their pages, a Continue Listening item resumes its episode, a show opens its page. */
static void pg_home_tap(int part, int a) {
    if (part == PH_LINE) {
        if (!pn_busy() && !pg.rpend) pg_refresh(0);
    } else if (part == PH_DLROW)
        pg_load_downloads(0);
    else if (part == PH_SUBROW)
        pg_load_subs(0);
    else if (part == PH_SAVROW)
        pg_load_saved();
    else if (part == PH_SHELF)
        pg_cont_play(a);
    else if (part == PH_CELL)
        pg_open_show(a, 0);
}

static int pg_on_up(void *ctx, void *e) {
    int a = pg.down, part = pg.down_part, same, part2;
    (void)ctx;
    pg.down = 0;
    pg_set_press(0);
    if (!a || !e || !pg.view) return RET_OK;
    if (pg_abs(I(e, PE_X) - pg.down_x) >= PG_TAP_PX || pg_abs(I(e, PE_Y) - pg.down_y) >= PG_TAP_PX) return RET_OK;
    same = pg_hit(e, &part2);
    if (pg.select) {
        if (a > 0 && same == a - 1) pg_toggle_pick(same); /* a tap marks and unmarks; a drag marks nothing */
    } else if (same == a - 1 && part2 == part) {
        if (pg.level == L_DLS)
            pg_dls_tap(same);
        else if (pg.level == L_SRCH)
            pg_srch_tap(same, part2);
        else if (pg.level == L_SHOWS)
            pg_home_tap(part, same);
        else
            pg_cell_tap(same, part);
    }
    return RET_OK;
}
static int pg_on_abort(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    pg.down = 0;
    pg_set_press(0);
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * The timer and the window's events
 */
static int pg_tick(const void *timer) {
    (void)timer;
    if (!pg.win || !pg.fg) {
        pg.timer = 0;
        return RET_OK;
    }
    pc_note(cc_playing());
    if (pod_screen_lit() && !pg.load_timer && pg_load_pending())
        pg_kick(); /* the screen is back on: the covers go on (the loader does nothing in the dark) */
    if (pg.dlg && pod_screen_lit())
        pg_dlg_arm(); /* the screen is back on: the dialog's own timer stopped while it was dark */
    if (pod_screen_lit() && pg.level == L_SHOWS) {
        if (!pg.dlg && pn_gen() != pg.gen)
            pg_load_shows(
                1); /* the worker moved on (a show finished, a download came or went) or it ended: the files are read again, the covers and the place stay (not under the refresh dialog: every finished show would scan every folder again; pg_dlg_finish reads them once) */
        else if (
            pg.dgen !=
            pn_dl_gen()) { /* a step of progress: the Downloads row's line and the refresh line are painted again (read at every paint) */
            pg.dgen = pn_dl_gen();
            pg_redraw();
        } else if (
            pc_rev() !=
            pg.rev) { /* a place or a mark changed (an episode played on): what is left is painted again; an item that is no longer partly played takes the row to be made again */
            int i;
            unsigned pos, len;
            pg.rev = pc_rev();
            for (i = 0; i < pg.ncont; ++i)
                if (pc_state(pg.cont[i].hash, &pos, &len) != PC_PROGRESS) break;
            if (i < pg.ncont)
                pg_load_shows(1);
            else
                pg_redraw();
        }
    }
    if (pg.sdone || pg.sback) pg_srch_pending();
    if (pod_screen_lit() && pg.level == L_SRCH) pg_srch_sync();
    if (pod_screen_lit() && pg.level == L_EPS && !pg.preview &&
        !pg.dlg) { /* (not under the refresh dialog: it reads the show again when it closes; the preview is no folder) */
        if (pn_gen() != pg.gen && !pg.select)
            pg_reload_eps(); /* (not while rows are marked: the marks are of these rows) a download started, finished or failed: the episodes are read again (a finished one is a file now) */
        else if (pn_dl_gen() !=
                 pg.dgen) { /* a step of progress: the pills are painted again (their states are read at every paint) */
            pg.dgen = pn_dl_gen();
            pg_redraw();
        }
    }
    if (pod_screen_lit() &&
        pg.level ==
            L_DLS) { /* the Downloads level: the rows again when the worker's state moved, the lines for a step of progress */
        if (pn_gen() != pg.gen && !pg.select) {
            if (pg.subs)
                pg_load_downloads(1);
            else
                pg_dls_sync(); /* (the worker's rows and the card, no show read again but a finished download's) */
        } else if (pg.subs)
            pg.dgen = pn_dl_gen(); /* (the Subscriptions page's lines are the feeds' status: read again with pn_gen) */
        else if (pn_dl_gen() != pg.dgen || (pc_rev() != pg.rev && !pg.select)) {
            pg.dgen = pn_dl_gen(), pg.rev = pc_rev();
            pg_dls_retext(); /* (a step of progress, or a place that moved: the lines are made again) */
            pg_redraw();
        }
    }
    if (pod_screen_lit() && pg.level == L_EPS &&
        pc_rev() != pg.rev) { /* a place or a mark changed: the pills and the badges are painted again */
        pg.rev = pc_rev();
        pg_redraw();
    }
    if (pg.rpend && (pg.level == L_SHOWS || (pg.level == L_EPS && pg.rone)) && pod_screen_lit() && !pn_dl_running() &&
        !pn_busy()) {
        int only_new = pg.rpend - 1,
            one = pg.rone; /* the downloads have paused: the refresh the user asked for starts */
        pg.rpend = pg.rone = 0;
        pg_refresh_job(only_new, one);
    }
    return RET_REPEAT;
}

/* The downloads' timer (1 s), page-scoped like the others but kept in the background too: while a download runs it calls stock's reset_poweroptions_timer(1, 1, 0), which sets the standby and
 * auto power-off countdowns again and leaves the screen's alone (stock standby would stop the Wi-Fi and the CPU, found by a device probe). It runs on the UI thread, never from the worker. It also starts the
 * queue again when no thread runs (after a refresh, or a tap that raced the worker's end) and drops a refresh nobody can see start. No widget is touched. It ends when nothing is queued. */
static int pg_awake_tick(const void *timer) {
    (void)timer;
    if (!pg.win) {
        pg.awake = 0;
        return RET_OK;
    }
    if (pn_dl_running()) reset_poweroptions_timer(1, 1, 0);
    if (pg.rpend && !pn_dl_running() && !pn_busy() &&
        (!(pg.level == L_SHOWS || (pg.level == L_EPS && pg.rone)) || !pg.fg || !pod_screen_lit()))
        pg.rpend = pg.rone = 0; /* the page is not there to open the refresh's dialog: the downloads go on */
    if (!pg.rpend && pn_dl_waiting() && !pn_dl_running()) pn_dl_start();
    if (!pn_dl_count() && !pg.rpend) {
        pg.awake = 0;
        return RET_OK;
    }
    return RET_REPEAT;
}

static void pg_awake_arm(void) {
    if (pg.win && !pg.awake && (pn_dl_count() > 0 || pg.rpend))
        pg.awake = timer_add(pg_awake_tick, (void *)0, PG_AWAKE_MS);
}

static void pg_arm(void) {
    if (!pg.timer) pg.timer = timer_add(pg_tick, (void *)0, PG_TICK_MS);
}

static int pg_on_fg(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    pg.fg = 1;
    pg_arm();
    if (pg.btn_globe) {
        pg.searchon = pcsearch_setting(); /* Podcast Search may have been switched in Settings */
        if (!pg.searchon && pg.level == L_SRCH) { /* the level goes with the setting: back to the Shows level */
            pg_srch_leave();
            pg_load_shows(1);
        }
    }
    pg_srch_pending();
    if (pg.dlg &&
        pod_screen_lit()) { /* the dialog was up when another page came in front: it is still right (or closes at its first tick) */
        pg_dlg_update();
        pg_dlg_arm();
    }
    if (pg.level ==
        L_SHOWS) { /* a refresh may have ended, an episode played on, while another page was in front (dark: the next lit tick does it) */
        if (pod_screen_lit())
            pg_load_shows(1);
        else
            pg.gen = pn_gen() - 1;
    }
    if (pg.level == L_DLS && !pg.select) { /* so may a download */
        if (pg.subs || pg.saved)
            pg_load_downloads(1);
        else
            pg_dls_sync();
    }
    if (pg.level ==
        L_EPS) { /* the layouts (the dates) are made again: "4h ago" is a time later; the status bar is the page's again */
        pg.rev = pc_rev();
        pg_cells_drop();
        pg_bar_apply();
        pg_redraw();
    }
    pg_kick();
    return RET_OK;
}

static int pg_on_bg(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    pg.fg = 0;
    if (pg.timer) timer_remove(pg.timer);
    if (pg.load_timer) timer_remove(pg.load_timer);
    if (pg.dlg_timer) timer_remove(pg.dlg_timer);
    pg.timer = pg.load_timer = pg.dlg_timer = 0;
    pg.down = 0;
    pg.press = 0;
    pg_bar_black(); /* the status bar is black again while another page is in front (it tints it itself) */
    pc_flush();
    return RET_OK;
}

static int pg_on_destroy(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (pg.timer) timer_remove(pg.timer);
    if (pg.load_timer) timer_remove(pg.load_timer);
    if (pg.dlg_timer) timer_remove(pg.dlg_timer);
    if (pg.awake)
        timer_remove(
            pg.awake); /* the downloads go on while the device is awake; nothing keeps it awake without this window */
    if (pg.dlg) pn_cancel(); /* the page is closed (the hardware Back key) with the dialog up: that is Cancel too */
    if (pn_job_busy()) pn_cancel(); /* ... and a search or preview that runs stops */
    pn_search_clean();
    pn_preview_drop();
    pg_bar_black();
    pc_flush();
    grid_free(&pg.g);
    grid_free(&pg.hg);
    grid_free(&pg.gg);
    grid_free(&pg.sg);
    if (pg.atlas) bitmap_destroy(pg.atlas);
    if (pg.dltile) bitmap_destroy(pg.dltile);
    if (pg.subtile) bitmap_destroy(pg.subtile);
    if (pg.savetile) bitmap_destroy(pg.savetile);
    if (pg.chev) bitmap_destroy(pg.chev);
    free(pg.sv_h);
    free(pg.sv_d);
    free(pg.cells);
    free(pg.hdr);
    free(pg.pd);
    if (pg.mark[0]) bitmap_destroy(pg.mark[0]);
    if (pg.mark[1]) bitmap_destroy(pg.mark[1]);
    free(pg.shows);
    free(pg.eps);
    free(pg.dls);
    free(pg.ord);
    memset(&pg, 0, sizeof pg);
    return RET_OK;
}

/* The sheets' widgets (the asset's, tools/pod_ui.py podcasts_sheet); one missing leaves the page without sheets (pg.sh_card is the switch). */
static void pg_sheet_bind(void) {
    char name[40];
    int i, ok = 1;
    pg.sh_scrim = pod_bind(pg.win, "pg_sh_scrim", pg_on_sheet_scrim, (void *)0);
    pg.sh_card = widget_lookup(pg.win, "pg_sh_card", 1);
    for (i = 0; i < PG_SHEET_ROWS; ++i) {
        snprintf(name, sizeof name, "pg_sh_%s", pg_row_id[i]);
        pg.sh_row[i] = pod_bind(pg.win, name, pg_on_sheet_row, (const void *)(unsigned)(i + 1));
        snprintf(name, sizeof name, "pg_sh_%s_tx", pg_row_id[i]);
        pg.sh_tx[i] = widget_lookup(pg.win, name, 1);
        snprintf(name, sizeof name, "pg_sh_%s_hr", pg_row_id[i]);
        pg.sh_hr[i] = widget_lookup(pg.win, name, 1);
        ok &= pg.sh_row[i] && pg.sh_tx[i] && pg.sh_hr[i];
    }
    pg.sh_vl[0] = widget_lookup(pg.win, "pg_sh_speed_vl", 1);
    pg.sh_vl[1] = widget_lookup(pg.win, "pg_sh_refresh_vl", 1);
    if (!ok || !pg.sh_scrim || !pg.sh_card || !pg.sh_vl[0] || !pg.sh_vl[1]) pg.sh_card = (void *)0;
}

/* The Extras item Podcasts. 0 once the page is up, -1 if it could not open. */
int podcasts_open(void) {
    static const char *const st_name[ST_N] = {
        "label_ps_name", "label_ps_sec",    "label_ps_meta",  "label_ps_head",   "label_ps_date",    "label_ps_ctitle",
        "label_ps_cdim", "label_ps_cdesc",  "label_ps_pill",  "label_ps_latest", "label_ps_latestw", "label_ps_sech",
        "label_ps_line", "label_ps_stitle", "label_ps_sleft", "label_ps_gtitle", "label_ps_gsub"};
    int i, ok = 1;
    if (pg.win) return -1;
    memset(&pg, 0, sizeof pg);
    pg.win = window_open("m1plus_podcasts");
    if (!pg.win) return -1;
    widget_on(pg.win, EVT_DESTROY, pg_on_destroy, (void *)0);
    pg.back = pod_bind(pg.win, "btn_return", pg_on_back, (void *)0);
    pod_bind(pg.win, "btn_backtoplayer", pod_on_player, (void *)0);
    pg.view = widget_lookup(pg.win, "view_grid", 1);
    pg.sv = widget_lookup(pg.win, "podcasts_scrollview", 1);
    pg.status = widget_lookup(pg.win, "label_status", 1);
    pg.title = widget_lookup(pg.win, "label_title", 1);
    pg.fade = widget_lookup(pg.win, "img_nb_fade", 1);
    pg.st_title = widget_lookup(pg.win, "label_row_title", 1);
    pg.st_sub = widget_lookup(pg.win, "label_row_sub", 1);
    pg.big = widget_lookup(pg.win, "pg_big", 1);
    pg.np = widget_lookup(pg.win, "btn_backtoplayer", 1);
    pg.dlg_scrim = widget_lookup(pg.win, "pod_pd_scrim", 1);
    pg.dlg_card = widget_lookup(pg.win, "pod_pd_card", 1);
    pg.dlg_name = widget_lookup(pg.win, "pod_pd_name", 1);
    pg.dlg_count = widget_lookup(pg.win, "pod_pd_count", 1);
    pg.dlg_fill = widget_lookup(pg.win, "pod_pd_fill", 1);
    pg.dlg_cancel = pod_bind(pg.win, "pod_pd_cancel", pg_on_cancel, (void *)0);
    /* select mode's widgets: optional (without them the sheets' Select rows never show) */
    pg.btn_selall = pod_bind(pg.win, "btn_selall", pg_on_selall, (void *)0);
    pg.del = pod_bind(pg.win, "pg_del", pg_on_delete, (void *)0);
    pg.unsubp = pod_bind(pg.win, "pg_unsubp", pg_on_unsubs, (void *)0);
    pg.bar = widget_lookup(pg.win, "pg_bar", 1);
    pg.tint_img =
        widget_lookup(pg.win, "img_ah_tint",
                      1); /* the Show page's widgets: without the sheet or the tint the page works without them */
    pg.btn_more = pod_bind(pg.win, "btn_more", pg_on_more, (void *)0);
    pg.sf = widget_lookup(pg.win, "ps_field", 1);
    pg.sf_hint = widget_lookup(pg.win, "ps_hint", 1);
    pg.sf_text = widget_lookup(pg.win, "ps_text", 1);
    pg.sf_clear = widget_lookup(pg.win, "ps_clear", 1);
    pg.btn_globe = pod_bind(pg.win, "btn_globe", pg_on_globe, (void *)0);
    if (!pg.sf || !pg.sf_hint || !pg.sf_text) pg.btn_globe = (void *)0; /* without the field the page has no search */
    for (i = 0; i < ST_N; ++i) {
        pg.st[i] = widget_lookup(pg.win, st_name[i], 1);
        ok &= pg.st[i] != (void *)0;
    }
    if (!pg.view || !pg.sv || !pg.status || !pg.title || !pg.st_title || !pg.st_sub || !pg.big || !pg.dlg_scrim ||
        !pg.dlg_card || !pg.dlg_name || !pg.dlg_count || !pg.dlg_fill || !pg.dlg_cancel || !ok) {
        navigator_back(); /* an asset that is not ours */
        return -1;
    }
    pg_sheet_bind();
    label_set_line_wrap(pg.status, 1);
    pg.shows = calloc(PC_MAX_SHOWS + 1, sizeof *pg.shows); /* (the spare slot is the preview's show) */
    pg.hdr = calloc(1, sizeof *pg.hdr);
    pg.cells = calloc(PG_CELLS, sizeof *pg.cells);
    if (!pg.shows || !pg.hdr || !pg.cells || !grid_init(&pg.g, pg.win, PC_TILES, LIST_ART, LIST_R) ||
        !grid_init(&pg.hg, pg.win, 1, PS_ART, PS_ART_R) || !grid_init(&pg.gg, pg.win, GRID_TILES, GRID_COVER, GRID_R) ||
        !grid_init(&pg.sg, pg.win, PP_SHELF_MAX, PP_SHELF_ART, PP_SHELF_R)) {
        pg_empty("Not enough memory");
        return 0;
    }
    pg.g.st_title = pg.st_title, pg.g.st_sub = pg.st_sub;
    pg.dls = calloc(PG_DLS_MAX, sizeof *pg.dls);
    pg.ord = calloc(PG_DLS_MAX + PG_DLD_MAX, sizeof *pg.ord);
    pg.dord = pg.ord ? pg.ord + PG_DLS_MAX : (unsigned short *)0;
    pg.sv_h = calloc(PG_DLD_MAX, sizeof *pg.sv_h);
    pg.sv_d = calloc(PG_DLD_MAX, sizeof *pg.sv_d);
    if (pg.del) pod_centre_pill(pg.del, PL_BAR_PILL_W);
    if (pg.unsubp) pod_centre_pill(pg.unsubp, PL_BAR_PILL_W);
    pc_root(pg.root);
    pg.searchon = pg.btn_globe ? pcsearch_setting() : 0;
    pg.mark[0] = pod_make_mark(pg.win, "unselect");
    pg.mark[1] = pod_make_mark(pg.win, "selected");
    if (!pg.mark[1] && pg.mark[0]) bitmap_destroy(pg.mark[0]), pg.mark[0] = (void *)0;
    pg.fg = 1;
    pg.noscroll = !widget_on(pg.sv, EVT_SCROLL, pg_on_scroll, (void *)0) ||
                  !widget_on(pg.sv, EVT_SCROLL_END, pg_on_scroll, (void *)0);
    widget_on(pg.win, EVT_WINDOW_TO_FG, pg_on_fg, (void *)0);
    widget_on(pg.win, EVT_WINDOW_TO_BG, pg_on_bg, (void *)0);
    widget_on(pg.view, EVT_POINTER_DOWN, pg_on_down, (void *)0);
    widget_on(pg.view, EVT_POINTER_UP, pg_on_up, (void *)0);
    widget_on(pg.view, EVT_POINTER_ABORT, pg_on_abort, (void *)0);
    widget_on(pg.view, EVT_AFTER_PAINT, pg_on_paint, (void *)0);
    pg_arm();
    pg_awake_arm(); /* a download queued by an earlier window of the page is still going */
    pg_load_shows(0);
    return 0;
}

/* Go to Podcasts (Now Playing's More sheet, patch/playmore.c): a Podcasts page already in the stack (the episode was started from it) is shown as it was by closing the Now Playing over it (AWTK destroys
 * a closed window later, so closing that page and opening a new one in the same call finds the old one still there: V2.1zCQUGAAAE did nothing); else the page opens at the Shows level. 0 once it is up or
 * uncovered, -1 if it could not open. */
int podcasts_go(void) {
    if (pg.win) {
        if (navigator_window_is_exist("playing_page")) navigator_close("playing_page");
        return 0;
    }
    return podcasts_open();
}
