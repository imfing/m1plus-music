/* M1+ Music Audiobooks: the books on the card and their parts, one page with two levels (docs/modules/audiobooks.md "The page").
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 * The model is patch/bkmodel.c (books, parts, progress, the MP4 memory guard); the state is Podcasts' resume ring (patch/pcmodel.c); the speed is the book's, kept by pc_speed_* under the
 * book's key.
 *
 * ui/m1plus_books.bin is the Podcasts page's structure (docs/modules/podcasts.md): the navbar over a stock list, list_view > scroll_view, whose ONE child, view_grid, paints the rows itself in its
 * EVT_AFTER_PAINT (no widget per row). The window is opened by the Extras item Audiobooks and has two levels, switched in place (the navbar's Back goes up a level before it leaves the page):
 *
 *   Library  the large heading and one row per book in the manner of the Downloads rows: the cover, the title and a grey line (Not started - 12 parts / 42% - Part 3 of 12 / Finished).
 *   Book     a header (the cover, the title, Part 3 of 12 - 42%, a white capsule Play / Resume / Play Again and the speed pill that cycles 1x 1.25x 1.5x 2x), then one row per part in reading
 *            order: the title and a grey line (Played / 12m left / the size). The part the player is on has the playing wave before its grey line; played parts are grey.
 *
 * Playing builds stSongInfo records of our own (class 1, the queue handed to playing_page, as Podcasts does): the parts from the one tapped to the end. A part with an MP4 extension is asked of
 * bk_mp4_fits first, every part of the queue: one the guard refuses means nothing starts and a toast says so (a book too long for one file can stall the player, and Memory Playback would stall it
 * again at boot). Covers are decoded one per 16 ms tick (pc_cover_ok first). The page's 1 s timer calls pc_note, like the other pages that already look at the playing track. No hook.
 */
#include "bkpage.h"
#include "covercache.h"
#include "common.h"
#include "azlist.h"
#include "libsrc.h"
#include "home.h"
#include "i18n.h"
#include "podcasts.h"
#include "bknet.h"
#include "bkdl.h"
#include "pcjson.h"
#include "pcnet.h"

extern void pod_toast(const char *text); /* patch/shuffle.c: the stock message box */
extern void pod_set_in_order(void); /* patch/shuffle.c: Shuffle and Repeat one become List play */

bk_t bk __attribute__((section(".scratch")));

static const char *const bk_speed_name[PC_SPEEDS] = {"1\xc3\x97", "1.25\xc3\x97", "1.5\xc3\x97",
                                                     "2\xc3\x97"}; /* "1x" with the multiplication sign U+00D7 */

void bk_show(void *w, int on) {
    if (!w) return;
    widget_set_visible(w, on, 0);
    widget_set_sensitive(w, on);
}
static int bk_abs(int v) { return v < 0 ? -v : v; }
int bk_off(void) { return bk.sv ? I(bk.sv, SC_YOFF) : 0; }
void bk_redraw(void) { widget_invalidate_force(bk.sv, (void *)0); }

/* ---------------------------------------------------------------------------
 * Geometry (content y; tools/pod_books.py is the same arithmetic)
 */
static int bk_nrows(void);
static int bk_count(void) { return bk.level == BL_BOOK ? bk_nrows() : bk.level == BL_LIB ? bk.l_n : bf_count(); }
static int bk_top(void) { return bk.level == BL_BOOK ? bk.y_list : bk.level == BL_LIB ? bk.l_list : bf_top(); }

/* The Library level's blocks (content y; tools/pod_books.py library() is the same arithmetic), the Podcasts Shows level's order: Continue Listening, the header Books and the books (the first PS_SHOW_MAX, then the See All row when
 * there are more), PP_SEC_GAP of air, the header Discover and the LibriVox row. The See All page (bk.all) is the complete list from the top, nothing else. */
static void bk_lib_layout(void) {
    int y = BK_TOP, n = bk.nbooks;
    bk.l_shelf = bk.l_hbooks = bk.l_all = bk.l_hdisc = bk.l_lv = 0;
    if (bk.all) {
        bk.l_list = 0, bk.l_n = n;
        return;
    }
    if (bk.cont >= 0) bk.l_shelf = y, y += PP_HEAD_PITCH + PP_SHELF_PITCH_Y + PP_SEC_GAP;
    if (n)
        bk
            .l_hbooks = y,
          y +=
          PP_HEAD_PITCH; /* (the Shows level's header; with no book there is none, as Podcasts has none with no show) */
    bk.l_list = y;
    bk.l_n = n > PS_SHOW_MAX ? PS_SHOW_MAX : n;
    y += bk.l_n * PC_ROW_H;
    if (n > PS_SHOW_MAX) bk.l_all = y, y += PS_MORE_H;
    if (n) y += PP_SEC_GAP;
    bk.l_hdisc = y, y += PP_HEAD_PITCH;
    bk.l_lv = y;
}

static int bk_content(void) {
    int n = bk_count();
    if (BK_FIND) return bf_content();
    if (bk.level == BL_LIB) {
        if (bk.all) return n * PC_ROW_H + BK_BOTTOM;
        return bk.nbooks ? bk.l_lv + PC_ROW_H + PP_BOTTOM
                         : GRID_VIEW_H; /* (no book: the hint's room under the LibriVox row) */
    }
    return bk_top() + n * PC_ROW_H + (n ? BK_BOTTOM : 0);
}

void bk_size(void) {
    int h = bk_content();
    widget_resize(bk.view, BK_W, h > 0 ? h : 1);
    widget_set_prop_int(bk.sv, "virtual_h", h > 0 ? h : 1);
}

/* The rows [*r0, *r1] that touch the view (r1 < r0 for none). */
static void bk_span(int *r0, int *r1) {
    int n = bk_count(), s = bk_off() - bk_top();
    *r0 = s / PC_ROW_H;
    *r1 = (s + GRID_VIEW_H - 1) / PC_ROW_H;
    if (s < 0) *r0 = 0;
    if (*r0 < 0) *r0 = 0;
    if (*r1 > n - 1) *r1 = n - 1;
}

/* ---------------------------------------------------------------------------
 * Texts
 */
void bk_cat(char *out, unsigned size, const char *s) {
    unsigned n = 0, k;
    while (out[n]) ++n;
    for (k = 0; s[k] && n + 1 < size; ++k) out[n++] = s[k];
    out[n] = 0;
}

static int bk_wlen(const unsigned *s) {
    int n = 0;
    while (s[n]) ++n;
    return n;
}

/* The UTF-8 text as wide chars into dst (cap of them, the NUL included); its length. */
int bk_wide(unsigned *dst, int cap, const char *utf8) {
    unsigned n = 0;
    while (utf8[n] && n < 4u * (unsigned)cap) ++n;
    tk_utf8_to_utf16_ex(utf8, n, dst, (unsigned)cap);
    return bk_wlen(dst);
}

static int bk_width(void *st, const unsigned *s) { return (int)(widget_measure_text(st, s) + 0.999f); }

/* s (n chars) in at most maxl lines of room px in the style st (patch/pcwrap.c); the number of lines. */
int bk_lines(void *st, unsigned *s, int n, int room, int maxl, pw_line_t *out) {
    unsigned short adv[BK_TITLE_MAX];
    unsigned t[2], e[2];
    int i;
    if (n > BK_TITLE_MAX - 1) n = BK_TITLE_MAX - 1, s[n] = 0;
    t[1] = 0;
    for (i = 0; i < n; ++i) {
        t[0] = s[i];
        adv[i] = (unsigned short)bk_width(st, t);
    }
    e[0] = ELLIPSIS, e[1] = 0;
    return pw_wrap(s, n, adv, room, maxl, bk_width(st, e), out);
}

static void bk_pct(char *out, unsigned size, unsigned permille) {
    unsigned p = permille / 10;
    pc_fmt(out, size, "%d%", p > 100 ? 100 : p);
}

void bk_kb_text(char *out, unsigned size, unsigned kb) {
    out[0] = 0;
    if (kb >= 10u << 20)
        pc_fmt(out, size, TR("%d GB"), (kb + 524288u) >> 20);
    else if (kb >= 1048576u) {
        unsigned tenths = (kb + 52428u) / 104858u;
        pc_fmt2(out, size, TR("%d.%d GB"), tenths / 10, tenths % 10);
    } else
        pc_fmt(out, size, TR("%d MB"), kb ? (kb + 1023) >> 10 : 0);
}

/* " - 12 parts" and the like: the second piece of a line after a middle dot. */
void bk_dot(char *out, unsigned size, const char *piece) {
    bk_cat(out, size, " \xc2\xb7 ");
    bk_cat(out, size, piece);
}

/* ---- The download of a LibriVox book (patch/bkdl.h): what the page shows of it */
enum {
    DR_IDLE = 0,
    DR_RUN = 1,
    DR_WAIT = 2
}; /* the download is not on this book, runs on it, or has it waiting in the queue (bkdl.h BD_S_*) */

static int bk_dl_kind(unsigned h) {
    int s = bd_state(h);
    return s == BD_S_RUN ? DR_RUN : s == BD_S_WAIT ? DR_WAIT : DR_IDLE;
}

/* A signature of the download as the page sees it: moves when the book fetched changes, a part ends, the download starts or ends. */
static unsigned bk_dl_sig(void) {
    unsigned part, parts, got, total, h = bd_active();
    int wait;
    if (!h || !bd_progress(&part, &parts, &got, &total, &wait)) return 0;
    return h * 31u + part + 1u;
}

static void bk_dl_mark(void) {
    bk.bgen = bd_gen();
    bk.bsig = bk_dl_sig();
}

/* The parts the manifest of book k names: its tabs (four a part line) counted in a stream, 0 for no manifest or one that does not add up. A cheap look, not bd_open's 108 KB: the Library asks for every book. */
static unsigned bk_man_total(const bk_book_t *k) {
    char path[BK_FILE * 2 + 40], buf[1024];
    unsigned n = 0, tabs = 0, got = 0, i, at = 0;
    int fd, r;
    for (i = 0; bk.root[i] && at < sizeof path - 1; ++i) path[at++] = bk.root[i];
    path[at++] = '/';
    for (i = 0; k->dir[i] && at < sizeof path - 12; ++i) path[at++] = k->dir[i];
    path[at] = 0;
    bk_cat(path, sizeof path, "/" BD_MANIFEST);
    fd = open(path, O_RDONLY, 0);
    if (fd < 0) return 0;
    while ((r = (int)read(fd, buf, sizeof buf)) > 0 && got < BD_MAN_CAP) {
        got += (unsigned)r;
        for (i = 0; i < (unsigned)r; ++i) tabs += buf[i] == '\t';
    }
    close(fd);
    n = tabs / 4;
    return tabs % 4 || n > BK_MAX_PARTS ? 0 : n;
}

/* The open book's manifest read again (bd_open, 108 KB, freed at once; the parts of the card are read already, bk.parts). A book with parts still to come lists every part the manifest names (bk.mp, in the manifest's order):
 * the files on the card match their rows by name, the others are rows of their own with the manifest's size and time. A book with all its parts, or none, is the plain list of files. */
static void bk_man_rows(void) {
    bd_book_t *b = bd_open(bk.books[bk.sel].dir);
    int i, j = 0, k;
    bk.mrows = bk.has_man = bk.nm = 0;
    bk.dl_missing = bk.man_parts = bk.man_secs = bk.man_bytes = 0;
    if (!b) return;
    bk.has_man = 1;
    bk.man_parts = (unsigned)b->n;
    for (i = 0; i < b->n; ++i) {
        bk_mrow_t *r = &bk.mp[i];
        const char *f = b->parts[i].file;
        unsigned n = 0, dot = 0, c;
        int p = -1;
        if (j < bk.nparts &&
            !strcmp(bk.parts[j].rel, f)) /* (the files are in the manifest's order unless the folder holds others) */
            p = j++;
        else
            for (k = 0; k < bk.nparts; ++k)
                if (!strcmp(bk.parts[k].rel, f)) p = k;
        for (c = 0; f[c] && n < BK_TITLE - 1; ++c) {
            r->title[n++] = f[c];
            if (f[c] == '.') dot = n;
        }
        r->title[dot > 1 ? dot - 1 : n] = 0; /* (the file name without its extension, as the model titles a part) */
        r->secs = b->parts[i].secs, r->bytes = b->parts[i].bytes, r->part = (short)p;
        bk.man_secs += r->secs;
        bk.man_bytes = r->bytes > 0xffffffffu - bk.man_bytes ? 0xffffffffu : bk.man_bytes + r->bytes;
        bk.dl_missing += p < 0;
    }
    bd_free(b);
    if (bk.dl_missing) bk.mrows = 1, bk.nm = (int)bk.man_parts;
}

/* How many rows the Book level has, and the file (place in bk.parts) of row r: -1 for a part that is not on the card yet. */
static int bk_nrows(void) { return bk.mrows ? bk.nm : bk.nparts; }
static int bk_row_part(int r) { return r < 0 || r >= bk_nrows() ? -1 : bk.mrows ? bk.mp[r].part : r; }
/* The row of the part the player is on right now (the stock playing record's path is the part's file), -1 when it is on another book, music, or nothing. */
static int bk_playing_row(void) {
    void *track = cc_playing();
    const char *pp = track ? *(const char **)((char *)track + REC_PATH) : (const char *)0;
    int r;
    if (!pp || bk_book_of(pp) != bk.sel_hash) return -1;
    for (r = 0; r < bk_nrows(); ++r) {
        char path[BK_FILE * 2 + BK_REL + 40];
        int p = bk_row_part(r);
        if (p >= 0 && bk_part_path(&bk.books[bk.sel], &bk.parts[p], path, sizeof path) && !strcasecmp(path, pp))
            return r;
    }
    return -1;
}

/* The open book's manifest and the row that plays, read together (the rows make the playing part's place). */
static void bk_man_read(void) {
    bk_man_rows();
    bk.pl_row = bk_playing_row();
}

/* The playing marker follows the player (the 1 s tick): the grey line of the row that gained or lost it is cut again for the room the wave takes, and the page repaints. No list is read again. */
static void bk_wave_sync(void) {
    int now = bk_playing_row(), i, rows[2];
    if (now == bk.pl_row) return;
    rows[0] = bk.pl_row, rows[1] = now;
    for (i = 0; i < 2; ++i) {
        grid_tile_t *t = rows[i] >= 0 ? grid_find(&bk.pt, rows[i]) : (grid_tile_t *)0;
        if (t) t->fit &= ~GRID_FIT_ARTIST;
    }
    bk.pl_row = now;
    bk_redraw();
}

/* Percent of the part being fetched, 0 to 100 (the sizes are scaled down first: no 64-bit division). */
static unsigned bk_dl_pct(unsigned got, unsigned total) {
    unsigned p;
    while (total > (1u << 24)) got >>= 4, total >>= 4;
    p = total ? got * 100u / total : 0;
    return p > 100 ? 100 : p;
}

/* The download ring of the running book `hash`, as Podcasts' In Progress rows have it (patch/podcasts.c pg_ip_ring, drawn by libsrc's ls_marks_draw): the arc is the percent of the part being fetched,
 * the empty ring (step 0) when its size is unknown; the empty ring with the arrow while the job waits to retry (Podcasts' WAIT). 0 when the job is not on this book. */
static int bk_ring(unsigned hash, ls_row_t *lr) {
    unsigned part, parts, got, total;
    int wait;
    if (hash && bd_active() != hash &&
        bk_dl_kind(hash) == DR_WAIT) { /* queued: the ring at step 0, as a queued episode has it */
        memset(lr, 0, sizeof *lr);
        lr->dl = LS_DL_WAIT, lr->pct = -1;
        return 1;
    }
    if (!hash || bd_active() != hash || !bd_progress(&part, &parts, &got, &total, &wait)) return 0;
    memset(lr, 0, sizeof *lr);
    lr->dl = wait ? LS_DL_WAIT : LS_DL_ACTIVE;
    lr->pct = total ? (int)bk_dl_pct(got, total) : -1;
    return 1;
}

/* The first manifest part that is not on the card: where the job is, or stopped. */
static int bk_first_missing(void) {
    int i;
    for (i = 0; bk.mrows && i < bk.nm; ++i)
        if (bk.mp[i].part < 0) return i;
    return -1;
}

/* "Failed: <why>" (Podcasts' In Progress rows): the page's word for the code. */
static void bk_failed_text(char *out, unsigned size, int code) {
    bk_cat(out, size, TR("Failed"));
    bk_cat(out, size, ": ");
    bk_cat(out, size, bf_word(code));
}

/* The row of the manifest part that the job is fetching, -1 when it is on no part of this book. */
static int bk_dl_row_now(void) {
    unsigned part, parts, got, total;
    int wait;
    if (bk_dl_kind(bk.sel_hash) != DR_RUN || !bd_progress(&part, &parts, &got, &total, &wait)) return -1;
    return (int)part;
}

/* The grey line of manifest part i that is not on the card: the part being fetched says how far it is, as Podcasts' In Progress rows do ("45%", "12 MB" when its length is unknown, Waiting while the job sleeps before a
 * retry); the part the last try failed on, "Failed: <why>"; the others their time and size, as the preview's rows. */
static void bk_miss_sub(int i, char *out, unsigned size) {
    unsigned part, parts, got, total;
    int wait, code;
    out[0] = 0;
    if (i == bk_dl_row_now() && bd_progress(&part, &parts, &got, &total, &wait)) {
        if (wait)
            bk_cat(out, size, TR("Waiting"));
        else if (total)
            bk_pct(out, size, bk_dl_pct(got, total) * 10u);
        else if (got >> 20)
            pc_fmt(out, size, TR("%d MB"), got >> 20);
        else /* (no length yet and no whole MB: not "0 MB" beside the ring) */
            bk_cat(out, size, TR("Downloading"));
        return;
    }
    if (bk_dl_kind(bk.sel_hash) == DR_IDLE && bd_result(bk.sel_hash, &code) == BD_R_FAILED && i == bk_first_missing()) {
        bk_failed_text(out, size, code);
        return;
    }
    bf_line(out, size, 0, bk.mp[i].secs, bk.mp[i].bytes);
}

/* "Downloading · Part 13 of 37" ("Waiting · Part 13 of 37" while the job sleeps before a retry): the one wording of the Library's row and of the Book header while a job runs on the book. */
static void bk_dl_text(char *out, unsigned size, int wait, unsigned part, unsigned total) {
    char t[48];
    out[0] = 0;
    bk_cat(out, size, wait ? TR("Waiting") : TR("Downloading"));
    pc_fmt2(t, sizeof t, TR("Part %d of %d"), part + 1, total);
    bk_dot(out, size, t);
}

/* The reading progress, one wording for every line of the page: "Part 14 of 41 · 33%", "42%" (a book of one file), "Finished", "Not started · 12 parts" ("Not started" for one file). "" for a book with no part. */
static void bk_prog(char *out, unsigned size, int state, unsigned permille, unsigned cur, unsigned parts) {
    char t[48];
    out[0] = 0;
    if (!parts) return;
    if (state == BK_FINISHED) {
        bk_cat(out, size, TR("Finished"));
    } else if (state == BK_IN_PROGRESS) {
        if (parts > 1) {
            pc_fmt2(out, size, TR("Part %d of %d"), cur + 1, parts);
            bk_pct(t, sizeof t, permille);
            bk_dot(out, size, t);
        } else
            bk_pct(out, size, permille);
    } else {
        bk_cat(out, size, TR("Not started"));
        if (parts > 1) {
            pc_fmt(t, sizeof t, TR("%d parts"), parts);
            bk_dot(out, size, t);
        }
    }
}

/* The header's grey line of a book with parts on the card and parts to come: what the download does, why it stopped ("Failed: <why>"), or how many parts are there. */
static void bk_dl_head(char *out, unsigned size) {
    unsigned part, parts, got, total;
    int wait, code;
    out[0] = 0;
    if (bk_dl_kind(bk.sel_hash) == DR_RUN && bd_progress(&part, &parts, &got, &total, &wait))
        bk_dl_text(out, size, wait, part, bk.man_parts);
    else if (bk_dl_kind(bk.sel_hash) ==
             DR_WAIT) { /* queued behind another book: "Waiting · 12 of 37 parts downloaded" */
        char t[64];
        bk_cat(out, size, TR("Waiting"));
        pc_fmt2(t, sizeof t, TR("%d of %d parts downloaded"), bk.man_parts - bk.dl_missing, bk.man_parts);
        bk_dot(out, size, t);
    } else if (bd_result(bk.sel_hash, &code) == BD_R_FAILED)
        bk_failed_text(out, size, code);
    else
        pc_fmt2(out, size, TR("%d of %d parts downloaded"), bk.man_parts - bk.dl_missing, bk.man_parts);
}

/* The Library line of a book whose manifest names more parts than are on the card: the part the job is on (after the ring), or the parts downloaded. */
static void bk_dl_lib_sub(int b, char *out, unsigned size) {
    const bk_book_t *k = &bk.books[b];
    unsigned total = bk.bst[b].total, done = k->parts, part, parts, got, t;
    int wait;
    if (bk_dl_kind(k->hash) == DR_RUN && bd_progress(&part, &parts, &got, &t, &wait) && part < total) {
        pc_fmt2(
            out, size, TR("Part %d of %d"), part + 1,
            total); /* (the ring before it says Downloading: the row's text ends at the chevron, 204 px, and "Downloading · Part 13 of 37" does not fit) */
        return;
    }
    if (done > total) done = total;
    if (bk_dl_kind(k->hash) == DR_WAIT) { /* (the ring before it says the book is queued) */
        bk_cat(out, size, TR("Waiting"));
        return;
    }
    pc_fmt2(out, size, TR("%d of %d parts downloaded"), done, total);
}

/* The grey line of book b on the Library level ("" until its progress is read): a LibriVox book with parts still to come says what the download does or how many parts are there. */
static void bk_lib_sub(int b, char *out, unsigned size) {
    const bk_st_t *s = &bk.bst[b];
    const bk_book_t *k = &bk.books[b];
    out[0] = 0;
    if (!s->have) return;
    if (s->total > k->parts)
        bk_dl_lib_sub(b, out, size);
    else
        bk_prog(out, size, s->state, s->permille, s->cur, k->parts);
}

/* The header's grey line of the open book: the reading progress; a LibriVox book with parts to come: its totals, or what the download does. */
static void bk_book_sub(char *out, unsigned size) {
    const bk_book_t *k = &bk.books[bk.sel];
    out[0] = 0;
    if (bk.mrows &&
        !bk.nparts) /* nothing on the card yet: what the manifest says of the book, as the preview's line does */
        bf_line(out, size, bk.man_parts, bk.man_secs, bk.man_bytes);
    else if (bk.mrows) /* parts on the card and parts to come: the download's state */
        bk_dl_head(out, size);
    else
        bk_prog(out, size, bk.state, bk.permille, (unsigned)bk.cur, k->parts);
}

/* The manifest's row of file i of the card (bk.parts), NULL for a book of your own or a file the manifest does not name. */
static const bk_mrow_t *bk_mrow_of(int i) {
    int r;
    if (!bk.has_man) return (const bk_mrow_t *)0;
    for (r = 0; r < (int)bk.man_parts && r < BK_MAX_PARTS; ++r)
        if (bk.mp[r].part == i) return &bk.mp[r];
    return (const bk_mrow_t *)0;
}

/* The grey line of part i: Played, "12m left" (a place in the ring) or, for a part not played, what it said before it landed: the manifest's time and size ("19m · 9 MB"; the size of the file for a book of your own). */
static void bk_part_sub(int i, char *out, unsigned size) {
    unsigned pos, len;
    int s = pc_state(bk.parts[i].hash, &pos, &len);
    const bk_mrow_t *m;
    out[0] = 0;
    if (s == PC_DONE)
        bk_cat(out, size, TR("Played"));
    else if (s == PC_PROGRESS && len > pos)
        pc_left_text(out, size, len - pos);
    else if ((m = bk_mrow_of(i)) != (const bk_mrow_t *)0 && (m->secs || m->bytes))
        bf_line(out, size, 0, m->secs, m->bytes);
    else
        bk_kb_text(out, size, bk.parts[i].kb);
}

/* ---------------------------------------------------------------------------
 * Tiles: a Library row's cover and texts (keyed by book), a part's texts (keyed by part)
 */
static void bk_lib_text(int b, grid_tile_t *t) {
    char sub[96];
    bk_lib_sub(b, sub, sizeof sub);
    grid_set(t, bk.books[b].title, sub, 0);
}

static grid_tile_t *bk_tile(int b) {
    int fresh;
    grid_tile_t *t = grid_tile(&bk.g, b, 0, -1, &fresh);
    if (fresh) bk_lib_text(b, t);
    return t;
}

/* The texts of row i of the Book level: a file on the card (its title and grey line), or a part the manifest names that is not there yet (the manifest's title, and its time and size or the download's progress). */
static void bk_part_text(int i, grid_tile_t *t) {
    char sub[96];
    int p = bk_row_part(i);
    if (p < 0) {
        if (i < bk_nrows()) bk_miss_sub(i, sub, sizeof sub), grid_set(t, bk.mp[i].title, sub, 0);
        return;
    }
    bk_part_sub(p, sub, sizeof sub);
    grid_set(t, bk.parts[p].title, sub, 0);
}

static grid_tile_t *bk_ptile(int i) {
    int fresh;
    grid_tile_t *t = grid_tile(&bk.pt, i, 0, -1, &fresh);
    if (fresh) bk_part_text(i, t);
    return t;
}

/* The texts made again where a place or a mark moved (the tiles keep their covers). */
static void bk_retext_lib(int b) {
    grid_tile_t *t = grid_find(&bk.g, b);
    if (!t) return;
    bk_lib_text(b, t);
    t->fit = 0, t->tw = t->aw = 0;
}

/* The parts' texts made again (only = 1: the row the job is on, and the first part not on the card, where a failure shows). */
static void bk_retext_parts(int only) {
    int k, now = bk_dl_row_now(), first = bk_first_missing();
    for (k = 0; k < bk.pt.n; ++k) {
        grid_tile_t *t = &bk.pt.tiles[k];
        if (!t->album || t->album > bk_nrows() || (only && t->album - 1 != now && t->album - 1 != first)) continue;
        bk_part_text(t->album - 1, t);
        t->fit = 0, t->tw = t->aw = 0;
    }
}

/* ---------------------------------------------------------------------------
 * Progress
 */
/* Book b's progress from the ring into bst[b] (its parts are read into bk.parts: the Library level only; the open book's list is its own). */
static void bk_read_status(int b) {
    unsigned pm = 0;
    int cur = 0, n = bk_load_parts(&bk.books[b], bk.parts, BK_MAX_PARTS);
    bk_st_t *s = &bk.bst[b];
    s->state = (unsigned char)bk_progress(bk.parts, n, &pm, &cur);
    s->permille = (unsigned short)pm;
    s->cur = (unsigned short)(cur < 0 ? 0 : cur);
    s->total = (unsigned short)bk_man_total(&bk.books[b]);
    s->rank = 0xffff;
    for (
        cur = 0; cur < n;
        ++cur) { /* the latest touched part's place in the ring: Continue Listening picks the in-progress book with the smallest */
        unsigned h = bk.parts[cur].hash, ps, pl;
        int rk;
        if (pc_state(h, &ps, &pl) == PC_NEW) continue;
        rk = pc_recent_rank(h);
        if (rk >= 0 && rk < s->rank) s->rank = (unsigned short)rk;
    }
    s->have = 1;
}

/* Continue Listening: the book in progress that was played last (-1 for none). 1 when it changed: the shelf's cover and title are made for the new one, the blocks move. */
static int bk_pick_cont(void) {
    int b, best = -1, was = bk.cont;
    for (b = 0; b < bk.nbooks; ++b)
        if (bk.bst[b].have && bk.bst[b].state == BK_IN_PROGRESS && bk.bst[b].rank != 0xffff &&
            (best < 0 || bk.bst[b].rank < bk.bst[best].rank))
            best = b;
    bk.cont = best;
    if (best >= 0 &&
        bk.books[best].hash != bk.cont_hash) { /* (a new book: its cover is loaded and its title cut again) */
        pw_line_t ln;
        int len = bk_wide(bk.ctitle, BK_TITLE_MAX, bk.books[best].title);
        bk.cont_hash = bk.books[best].hash;
        grid_drop(&bk.sg);
        grid_placeholder(&bk.sg);
        bk.ctn = bk_lines(bk.st[BS_STITLE], bk.ctitle, len, PP_SHELF_W, 1, &ln) == 1 ? ln.len : 0;
    }
    if (best < 0) bk.cont_hash = 0;
    bk_lib_layout();
    return best != was;
}

static void bk_read_all(void) {
    int b;
    for (b = 0; b < bk.nbooks; ++b) {
        bk_read_status(b);
        bk_retext_lib(b);
    }
}

/* The Library level after a place moved: the book the player is on, read again (the others cannot have changed: only playing writes the ring there). */
static void bk_refresh_playing(void) {
    void *track = cc_playing();
    unsigned h = track ? bk_book_of(*(const char **)((char *)track + REC_PATH)) : 0;
    int b;
    for (b = 0; h && b < bk.nbooks; ++b)
        if (bk.books[b].hash == h) {
            unsigned short was = bk.bst[b].rank;
            int k;
            bk_read_status(b);
            bk_retext_lib(b);
            if (was &&
                bk.bst[b].rank == 0) /* (it moved to the front of the ring: the others' places are one further back) */
                for (k = 0; k < bk.nbooks; ++k)
                    if (k != b && bk.bst[k].rank < 0xfffe) ++bk.bst[k].rank;
        }
    if (bk_pick_cont()) { /* the shelf came, went or changed books: the blocks moved */
        bk_size();
        bk_kick();
    }
}

/* The open book's progress from its parts. */
static void bk_book_progress(void) {
    unsigned pm = 0;
    int cur = 0;
    bk.state = bk_progress(bk.parts, bk.nparts, &pm, &cur);
    bk.permille = pm;
    bk.cur = cur;
}

/* ---------------------------------------------------------------------------
 * Painting
 */
void bk_text(void *canvas, const unsigned *s, int n, int x, int y, int w, int h) {
    int rect[4];
    rect[0] = x, rect[1] = y, rect[2] = w, rect[3] = h;
    if (n > 0 && y >= 0 && y + h <= GRID_VIEW_H) canvas_draw_text_in_rect(canvas, s, (unsigned)n, rect);
}

void bk_text_utf8(void *canvas, void *style, const char *utf8, int x, int y, int w, int h) {
    unsigned t[96];
    int n = bk_wide(t, 96, utf8);
    widget_prepare_text_style(style, canvas);
    bk_text(canvas, t, n, x, y, w, h);
}

/* A stadium of w x h at (x, y) in colour argb: each row's ends are inset by the circle's chord, the end pixel blended by its coverage. */
void bk_capsule(void *canvas, int x, int y, int w, int h, unsigned argb) {
    int r = h / 2, row;
    unsigned a = argb >> 24, rgb = argb & 0xffffffu;
    for (row = 0; row < h; ++row) {
        int d = 2 * row + 1 - h, e16, xi, cov16;
        e16 = r * 16 - (int)m1_isqrt((unsigned)(4 * r * r - d * d) * 64u);
        xi = (e16 + 15) / 16;
        cov16 = xi * 16 - e16; /* coverage of the pixel before xi, in 1/16 */
        az_fill(canvas, x + xi, y + row, y + row + 1, w - 2 * xi, argb);
        if (cov16 > 0) {
            unsigned edge = (a * (unsigned)cov16 / 16) << 24 | rgb;
            az_fill(canvas, x + xi - 1, y + row, y + row + 1, 1, edge);
            az_fill(canvas, x + w - xi, y + row, y + row + 1, 1, edge);
        }
    }
}

/* What the header's capsule is: Play (the book has a part), or, for a LibriVox book with no part on the card yet, the download's own button: Pause while it downloads, Retry after a failure, else Resume
 * (the words of Podcasts' pill and sheet). It stands alone, centred, as the Show page's Latest Episode pill and the preview's capsule do. */
enum { HB_NONE = 0, HB_PLAY, HB_PAUSE, HB_RESUME, HB_RETRY };

static int bk_hdr_btn(void) {
    int code;
    if (bk.nparts) return HB_PLAY;
    if (!bk.mrows) return HB_NONE;
    if (bk_dl_kind(bk.sel_hash) != DR_IDLE) return HB_PAUSE;
    return bd_result(bk.sel_hash, &code) == BD_R_FAILED ? HB_RETRY : HB_RESUME;
}

static int bk_btn_x(void) { return (BK_W - BK_PLAY_W) / 2; }

/* The capsule's word: Play (not started), Resume (a place in the book), Play Again (every part played); the download's Pause, Resume or Retry. */
static void bk_play_text(char *out, unsigned size) {
    int kind = bk_hdr_btn();
    out[0] = 0;
    if (kind == HB_PAUSE)
        bk_cat(out, size, TR("Pause"));
    else if (kind == HB_RESUME)
        bk_cat(out, size, TR("Resume"));
    else if (kind == HB_RETRY)
        bk_cat(out, size, TR("Retry"));
    else
        bk_cat(out, size,
               bk.state == BK_FINISHED      ? TR("Play Again")
               : bk.state == BK_IN_PROGRESS ? TR("Resume")
                                            : TR("Play"));
}

/* The shared grey chevron (m1_make_chevron) at (x, y) of the view. */
void bk_chevron(void *canvas, int x, int y) {
    if (!bk.chev) bk.chev = m1_make_chevron();
    grid_blit_from(canvas, bk.chev, 0, 0, POD_CHEV_W, POD_CHEV_H, x, y, GRID_VIEW_H);
}

/* A section header (the Podcasts Shows level's pg_paint_head: the section style BS_SECH, PP_HEAD_H high) at content y top, x x. */
static void bk_paint_head(void *canvas, int top, const char *text, int x) {
    bk_text_utf8(canvas, bk.st[BS_SECH], text, x, top, BK_W - 2 * x, PP_HEAD_H);
}

/* The Library's LibriVox row, under the header Discover: the Podcasts Shows level's Discover row (a PA_TILE_PX tile, the title, the grey line, the chevron, the hairline from the text). The row's own title is the
 * product's, the grey line says what it is. */
static void bk_paint_lv_row(void *canvas, int off) {
    int y = bk.l_lv - off;
    if (bk.pbtn == BP_LV) az_fill(canvas, 0, y, y + PC_ROW_H - 1, BK_W, LIST_PRESS);
    if (bk.ltile)
        grid_blit_from(canvas, bk.ltile, 0, 0, PA_TILE_PX, PA_TILE_PX, PP_DL_TILE_X, y + PP_DL_TILE_Y, GRID_VIEW_H);
    bk_chevron(canvas, PP_DL_CHEV_X, y + (PC_ROW_H - 1 - POD_CHEV_H) / 2);
    az_fill(canvas, PP_DL_TEXT_X, y + PC_ROW_H - 1, y + PC_ROW_H, LIST_HAIR_END - PP_DL_TEXT_X, LIST_HAIR);
    bk_text_utf8(canvas, bk.st_title, TR("LibriVox"), PP_DL_TEXT_X, y + LIST_TITLE_Y, PP_DL_TEXT_W, LIST_TITLE_H);
    bk_text_utf8(canvas, bk.st_sub, TR("Public domain audiobooks"), PP_DL_TEXT_X, y + LIST_SUB_Y, PP_DL_TEXT_W,
                 LIST_SUB_H);
}

/* Continue Listening (the Podcasts Shows level's shelf, one item): the header, the cover with the play disc, the title cut to the cover's width and the percent in place of the minutes left. */
static void bk_paint_shelf(void *canvas, int off) {
    int y = bk.l_shelf - off, fresh, n;
    char left[16];
    unsigned w[16];
    pw_line_t cut;
    grid_tile_t *t = grid_tile(&bk.sg, 0, 0, 0, &fresh);
    if (bk.cont < 0) return;
    grid_blit(canvas, &bk.sg, t, PP_SHELF_X, y + PP_HEAD_PITCH, GRID_VIEW_H);
    if (!bk.atlas) bk.atlas = pg_rgba_win(bk.win, "pc_atlas", PA_SIZE, PA_SIZE);
    grid_blit_from(canvas, bk.atlas, PA_PLAYB_X, PA_PLAYB_Y, PA_PLAYB_PX, PA_PLAYB_PX,
                   PP_SHELF_X + PP_SHELF_ART - PP_SHELF_PLAY_INSET - PA_PLAYB_PX,
                   y + PP_HEAD_PITCH + PP_SHELF_ART - PP_SHELF_PLAY_INSET - PA_PLAYB_PX, GRID_VIEW_H);
    bk_paint_head(canvas, y, TR("Continue Listening"), PP_HEAD_X);
    widget_prepare_text_style(bk.st[BS_STITLE], canvas);
    bk_text(canvas, bk.ctitle, bk.ctn, PP_SHELF_X, y + PP_HEAD_PITCH + PP_SHELF_TITLE_Y, PP_SHELF_W, PP_SHELF_TITLE_H);
    bk_pct(left, sizeof left, bk.bst[bk.cont].permille);
    n = bk_wide(w, 16, left);
    n = bk_lines(bk.st[BS_SLEFT], w, n, PP_SHELF_W, 1, &cut) == 1 ? cut.len : 0;
    widget_prepare_text_style(bk.st[BS_SLEFT], canvas);
    bk_text(canvas, w, n, PP_SHELF_X, y + PP_HEAD_PITCH + PP_SHELF_LEFT_Y, PP_SHELF_W, PP_SHELF_LEFT_H);
}

/* A Library row's tile; the book that downloads has its grey line start after the ring (the text is cut again when that changes). */
static grid_tile_t *bk_tile_of(void *ctx, int b) {
    grid_tile_t *t = bk_tile(b);
    ls_row_t lr;
    int subx = bk_ring(bk.books[b].hash, &lr) ? ls_marks_w(&lr) + LS_MK_GAP : 0;
    (void)ctx;
    if (t->subx != subx) t->subx = subx, t->fit &= ~GRID_FIT_ARTIST;
    return t;
}

static void bk_paint_lib(void *canvas) {
    int r0, r1, r, off = bk_off();
    char line[40];
    unsigned w[40];
    if (bk.l_shelf) bk_paint_shelf(canvas, off);
    if (bk.l_hbooks) bk_paint_head(canvas, bk.l_hbooks - off, TR("Books"), PP_SHOWS_X);
    if (bk.l_hdisc) bk_paint_head(canvas, bk.l_hdisc - off, TR("Discover"), PP_SHOWS_X);
    bk_span(&r0, &r1);
    if (r1 >=
        r0) { /* the list painter of the other pages: the cover, the hairline from the text, the chevron, the texts */
        grid_list_paint(canvas, &bk.g, bk.st_title, bk.st_sub, r0, r1, off - bk.l_list, GRID_VIEW_H, bk.press, 0, 1,
                        bk_tile_of, (void *)0);
        for (
            r = r0; r <= r1;
            ++r) { /* the download ring of the book that downloads, before its grey line (Podcasts' In Progress rows) */
            ls_row_t lr;
            if (bk_ring(bk.books[r].hash, &lr))
                ls_marks_draw(canvas, bk.win, &lr, LIST_TEXT_X,
                              bk.l_list + r * PC_ROW_H - off + LIST_SUB_Y + LIST_SUB_H / 2, GRID_VIEW_H);
        }
    }
    if (bk.l_all) { /* the See All row: the Show page's, with the count of every book */
        int y = bk.l_all - off, n;
        if (bk.pbtn == BP_ALL) az_fill(canvas, 0, y, y + PS_MORE_H, BK_W, 0x30ffffffu);
        pc_fmt(line, sizeof line, TR("See All (%d)"), (unsigned)bk.nbooks);
        n = bk_wide(w, 40, line);
        widget_prepare_text_style(bk.st[BS_CTITLE], canvas);
        bk_text(canvas, w, n, PP_SHOWS_X, y + (PS_MORE_H - PS_TITLE_PITCH) / 2, BK_W - 2 * PP_SHOWS_X,
                PS_TITLE_PITCH); /* (under the Books header and the covers, not at the Show page's cell x) */
    }
    if (bk.l_lv) bk_paint_lv_row(canvas, off);
    if (!bk.nbooks) {
        // clang-format off: a translation key stays on one line (test/pod/i18n.py reads the source)
        const char *hint = TR("No audiobooks. Copy a folder for each book into Audiobooks on the card.");
        // clang-format on
        grid_hint_paint(canvas, &bk.hg, bk.st[BS_HINT], hint, 0, bk.l_lv + PC_ROW_H, GRID_VIEW_H, off);
    }
}

static void bk_paint_book(void *canvas) {
    int r0, r1, r, k, pass, off = bk_off(), now;
    char line[96], label[48];
    unsigned w[48];
    int n;
    if (off < bk.y_list) { /* the header */
        int btn = bk_hdr_btn(), px = bk_btn_x(), by = bk.y_btn - off;
        grid_blit(canvas, &bk.hg, &bk.hg.tiles[0], PS_ART_X, BK_ART_Y - off, GRID_VIEW_H);
        if (btn) /* (a book with nothing on the card yet has the download's button) */
            bk_capsule(canvas, px, by, BK_PLAY_W, BK_BTN_H, bk.pbtn == BP_PLAY ? 0xffc8c8c8u : 0xffffffffu);
        widget_prepare_text_style(bk.st[BS_TITLE], canvas);
        for (k = 0; k < bk.nn; ++k)
            bk_text(canvas, bk.name + bk.nl[k].start, bk.nl[k].len, BK_NAME_X, bk.y_name + k * BK_NAME_PITCH - off,
                    BK_NAME_W, BK_NAME_PITCH);
        bk_book_sub(line, sizeof line);
        bk_text_utf8(canvas, bk.st[BS_SUB], line, BK_NAME_X, bk.y_sub - off, BK_NAME_W, BK_SUB_H);
        if (btn) {
            bk_play_text(label, sizeof label);
            n = bk_wide(w, 48, label);
            widget_prepare_text_style(bk.st[BS_BTN], canvas);
            bk_text(canvas, w, n, px + 8, by, BK_PLAY_W - 16, BK_BTN_H);
        }
    }
    bk_span(&r0, &r1);
    now = bk_dl_row_now();
    for (r = r0; r <= r1; ++r) {
        int y = bk.y_list + r * PC_ROW_H - off;
        if (bk.press == r + 1) az_fill(canvas, 0, y, y + PC_ROW_H - 1, BK_W, LIST_PRESS);
        az_fill(canvas, BK_PART_X, y + PC_ROW_H - 1, y + PC_ROW_H, LIST_HAIR_END - BK_PART_X, LIST_HAIR);
    }
    for (pass = 0; pass < 3; ++pass) { /* titles of the parts to play, titles of played parts, grey lines */
        widget_prepare_text_style(pass == 0 ? bk.st_title : pass == 1 ? bk.st[BS_DIM] : bk.st_sub, canvas);
        for (r = r0; r <= r1; ++r) {
            unsigned pos, len;
            int p = bk_row_part(r), played = p >= 0 && pc_state(bk.parts[p].hash, &pos, &len) == PC_DONE;
            int x = BK_PART_X, w = BK_PART_W;
            ls_row_t lr;
            if (pass < 2 && pass != played) continue;
            if (pass == 2 && r == now && bk_ring(bk.sel_hash, &lr))
                x += ls_marks_w(&lr) + LS_MK_GAP, w -= ls_marks_w(&lr) + LS_MK_GAP;
            else if (pass == 2 && r == bk.pl_row && bk.wave)
                x += AB_WAVE + LS_MK_GAP, w -= AB_WAVE + LS_MK_GAP; /* (the wave stands in the slot the ring has) */
            grid_text(canvas, bk_ptile(r), pass == 2, x,
                      bk.y_list + r * PC_ROW_H - off + (pass == 2 ? LIST_SUB_Y : LIST_TITLE_Y), w,
                      pass == 2 ? LIST_SUB_H : LIST_TITLE_H, GRID_VIEW_H);
        }
    }
    if (bk.pl_row >= r0 && bk.pl_row <= r1 &&
        bk.wave) /* the playing part: the album page's wave in the ring's slot, centred on the grey line */
        grid_wave_draw(canvas, bk.wave, BK_PART_X,
                       bk.y_list + bk.pl_row * PC_ROW_H - off + LIST_SUB_Y + LIST_SUB_H / 2 - AB_WAVE / 2, GRID_VIEW_H);
    if (now >= r0 && now <= r1) { /* the download ring before the grey line of the part being fetched */
        ls_row_t lr;
        if (bk_ring(bk.sel_hash, &lr))
            ls_marks_draw(canvas, bk.win, &lr, BK_PART_X,
                          bk.y_list + now * PC_ROW_H - off + LIST_SUB_Y + LIST_SUB_H / 2, GRID_VIEW_H);
    }
}

static int bk_on_paint(void *ctx, void *e) {
    void *canvas = e ? *(void **)((char *)e + EVENT_PAINT_CANVAS) : (void *)0;
    int off = bk_off();
    (void)ctx;
    if (!canvas || !bk.view || !bk.g.tiles) return RET_OK;
    I(canvas, CANVAS_OY) += off;
    if (bk.level == BL_LIB)
        bk_paint_lib(canvas);
    else if (bk.level == BL_BOOK && bk.hg.tiles)
        bk_paint_book(canvas);
    else if (BK_FIND)
        bf_paint(canvas);
    I(canvas, CANVAS_OY) -= off;
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * The loader: one cover a tick
 */
static int bk_on_load(const void *unused);

void bk_kick(void) {
    if (bk.win && bk.fg && !bk.load_timer) bk.load_timer = timer_add(bk_on_load, (void *)0, BK_LOAD_MS);
}

/* ---------------------------------------------------------------------------
 * A book with no cover file the loader takes (docs/modules/audiobooks.md "The book's own art"): the art of its first part, i.e. the picture embedded in that file, else a picture of
 * its folder, shrunk by the cover cache's worker into the cache file of the book's own key (cc_build_add: made once; the empty marker for a book with none). The books in view are
 * one job set; the poll hands each file to the loader as it appears. Another page's set, a full card or no thread: the placeholders stay and the page's tick asks again.
 */
#define BK_ART_MS 250 /* the poll of the set */
static const char *bk_cover_url(const bk_book_t *b, char *url, unsigned size);
static int bk_on_art(const void *unused);

/* The cache key of a book's own art (bk_art_key_of). */
static unsigned bk_art_key(const bk_book_t *b) { return bk_art_key_of(b->dir); }

static void bk_art_flags(int from, int to) {
    int b;
    for (b = 0; b < bk.nbooks; ++b)
        if (bk.bst[b].art == from) bk.bst[b].art = (unsigned char)to;
}

/* The set released (a running worker is cancelled, cc_build_stop); the books whose job was not seen to end are looked at again. */
static void bk_art_end(void) {
    if (bk.art_timer) timer_remove(bk.art_timer);
    bk.art_timer = 0;
    if (bk.art_own) cc_build_stop();
    bk.art_own = 0;
    if (bk.bst) bk_art_flags(1, 0);
}

/* Book b's placeholders (its Library row, the shelf, the open book's header) are tried again by the loader; how many there were. */
static int bk_art_fresh(int b) {
    grid_tile_t *t = bk.g_lv || !bk.g.tiles ? (grid_tile_t *)0 : grid_find(&bk.g, b);
    int n = 0;
    if (t && t->art == 2) t->art = 0, ++n;
    if (b == bk.cont && bk.sg.tiles && bk.sg.tiles[0].art == 2) bk.sg.tiles[0].art = 0, ++n;
    if (bk.level == BL_BOOK && b == bk.sel && bk.hg.tiles && bk.hg.tiles[0].art == 2) bk.hg.tiles[0].art = 0, ++n;
    return n;
}

/* Book b looked at once since the books were read: 1 when its job joined the set. A book that has a picture after all (a job that ended unseen) gives it to the loader. */
static int bk_art_want(int b) {
    char path[BK_FILE * 2 + BK_REL + 40], url[BK_FILE * 2 + 60];
    const bk_book_t *k = &bk.books[b];
    unsigned key = bk_art_key(k);
    int n;
    if (bk.bst[b].art || !k->parts) return 0;
    bk.bst[b].art = 2;
    if (bk_cover_url(k, url, sizeof url)) {
        if (bk_art_fresh(b)) bk_kick();
        return 0;
    }
    if (!access(cc_path(path, sizeof path, key, ""), F_OK)) return 0; /* the marker: no art in it */
    n = bk.level == BL_BOOK
            ? bk.nparts
            : bk_load_parts(k, bk.parts, BK_MAX_PARTS); /* (the Library borrows bk.parts, as bk_read_status) */
    if (n <= 0 || !bk_part_path(k, &bk.parts[0], path, sizeof path) || cc_build_add(path, key) != 1) return 0;
    bk.bst[b].art = 1;
    return 1;
}

/* The books in view that were not looked at yet (the rows the loader covers and the shelf; the open book) become one set of the worker. */
static void bk_art_build(void) {
    int r0 = 0, r1 = -1, a, n = 0, any = 0;
    if (!bk.win || !bk.fg || bk.art_own || !bk.bst || (bk.level != BL_LIB && bk.level != BL_BOOK)) return;
    if (bk.level == BL_BOOK)
        r0 = r1 = bk.sel;
    else {
        bk_span(&r0, &r1);
        r0 = r0 > 2 ? r0 - 2 : 0, r1 += 2;
        if (bk.cont >= 0 && !bk.bst[bk.cont].art) any = 1;
    }
    if (r1 >= bk.nbooks) r1 = bk.nbooks - 1;
    for (a = r0; a <= r1 && !any; ++a) any = !bk.bst[a].art;
    if (!any || cc_build_busy() || !m1_card_mounted() || !cc_build_open(BK_TILES + 1, CC_MISSING)) return;
    bk.art_own = 1;
    if (bk.level == BL_LIB && bk.cont >= 0) n += bk_art_want(bk.cont);
    for (a = r0; a <= r1; ++a) n += bk_art_want(a);
    bk.art_done = 0;
    if (n && cc_build_start()) bk.art_timer = timer_add(bk_on_art, (void *)0, BK_ART_MS);
    if (!bk.art_timer) { /* nothing to make, no space, no thread: these books are not asked again until the books are read again */
        bk_art_flags(1, 2);
        bk_art_end();
    }
}

static int bk_on_art(const void *unused) {
    int done, fin, b, n = 0;
    (void)unused;
    bk.art_timer = 0;
    if (!bk.win || !bk.art_own) return RET_OK;
    done = cc_build_done();
    fin = done >= cc_build_total();
    if (fin || done != bk.art_done) { /* a file (or a marker) appeared: the loader tries the books of the set again */
        bk.art_done = done;
        for (b = 0; b < bk.nbooks; ++b)
            if (bk.bst[b].art == 1) n += bk_art_fresh(b);
    }
    if (fin) {
        bk_art_flags(1, 2);
        bk_art_end();
    } else {
        bk.art_timer = timer_add(bk_on_art, (void *)0, BK_ART_MS);
        if (!bk.art_timer) bk_art_end();
    }
    if (n || fin)
        bk_kick(); /* (the loader, once it has nothing left, asks for the books that came into view meanwhile) */
    return RET_OK;
}

/* A book's cover as a file:// url: its cover file, else its own art from the cache; NULL for none or one the stock decoder would refuse. */
static const char *bk_cover_url(const bk_book_t *b, char *url, unsigned size) {
    char path[BK_FILE * 2 + 40];
    unsigned n = 0, k;
    if (b->cover[0]) {
        for (k = 0; bk.root[k] && n < sizeof path - 1; ++k) path[n++] = bk.root[k];
        path[n++] = '/';
        for (k = 0; b->dir[k] && n < sizeof path - 1; ++k) path[n++] = b->dir[k];
        path[n++] = '/';
        for (k = 0; b->cover[k] && n < sizeof path - 1; ++k) path[n++] = b->cover[k];
        path[n] = 0;
        if (pc_cover_ok(path) && n + 8 <= size) {
            memcpy(url, "file://", 7);
            memcpy(url + 7, path, n + 1);
            return url;
        }
    }
    return size >= 80 ? cc_url(url, bk_art_key(b))
                      : (const char *)0; /* (the book's own art, once the worker has made it) */
}

static void bk_art(grid_t *g, grid_tile_t *t, const bk_book_t *b) {
    char url[BK_FILE * 2 + 60];
    grid_art_url(g, t, bk_cover_url(b, url, sizeof url));
}

/* The Library row whose cover is next: the rows in view and two either side (the ring holds that many), -1 when every tile there has been tried. */
static int bk_next_cover(void) {
    int r0, r1, a;
    bk_span(&r0, &r1);
    if (r1 < r0) return -1;
    for (a = r0 > 2 ? r0 - 2 : 0; a <= r1 + 2 && a < bk.nbooks; ++a) {
        grid_tile_t *t = grid_find(&bk.g, a);
        if (!t || !t->art) return a;
    }
    return -1;
}

/* Continue Listening's cover is next while it has not been tried. */
static int bk_shelf_pending(void) {
    grid_tile_t *t;
    int fresh;
    if (bk.level != BL_LIB || bk.all || bk.cont < 0 || !bk.sg.tiles) return 0;
    t = grid_tile(&bk.sg, 0, 0, 0, &fresh);
    return !t->art;
}

static int bk_load_pending(void) {
    if (bk.level == BL_LIB) return bk_shelf_pending() || bk_next_cover() >= 0;
    if (BK_FIND) return bf_load_pending();
    return bk.hg.tiles && !bk.hg.tiles[0].art;
}

static int bk_on_load(const void *unused) {
    (void)unused;
    bk.load_timer = 0;
    if (!bk.win || !bk.fg || !bk.g.tiles || !m1_screen_lit()) return RET_OK;
    if (bk.level == BL_LIB) {
        int a = bk_next_cover(), fresh;
        if (bk_shelf_pending()) {
            bk_art(&bk.sg, grid_tile(&bk.sg, 0, 0, 0, &fresh), &bk.books[bk.cont]);
            bk_redraw();
        } else if (a >= 0) {
            grid_tile_t *t = bk_tile(a);
            if (!t->art) bk_art(&bk.g, t, &bk.books[a]);
            bk_redraw();
        }
    } else if (BK_FIND) {
        bf_load();
    } else if (bk.hg.tiles && !bk.hg.tiles[0].art) {
        bk_art(&bk.hg, &bk.hg.tiles[0], &bk.books[bk.sel]);
        bk_redraw();
    }
    if (bk_load_pending())
        bk_kick();
    else
        bk_art_build();
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * Levels
 */
static void bk_empty(const char *key) {
    widget_move(bk.status, 20, 180);
    bk_show(bk.view, 0);
    bk_show(bk.status, 1);
    widget_set_tr_text(bk.status, key);
}

void bk_fade(void) {
    if (!bk.fade) return;
    widget_set_visible(bk.fade, bk_off() > 0, 0);
    widget_set_sensitive(bk.fade, 0);
}

static void bk_nav(void);
static void bk_sheet_close(void);

void bk_title_show(void) {
    if (bk.title) widget_set_visible(bk.title, bk.collapsed, 0);
    bk_nav(); /* (every level change comes through here: the "..." and the title's width follow the level) */
}

/* Whether the navbar shows its small title: the Library and LibriVox levels once the large title has scrolled away (m1_title_gone, the rule every large-title page shares, as the Podcasts Shows level), the Book and
 * Preview levels once the header's title has; the See All page and the search level have no large title: the navbar's is always there. */
static int bk_gone(void) {
    if (bk.level == BL_BOOK || bk.level == BL_PRE) return bk_off() >= bk.collapse;
    if (bk.level == BL_LIB) return bk.all || m1_title_gone(bk_off(), 0);
    if (bk.level == BL_LV) return m1_title_gone(bk_off(), 0);
    return 1;
}

void bk_collapse(void) {
    int c = bk_gone();
    if (c != bk.collapsed) {
        bk.collapsed = c;
        bk_title_show();
    }
}

void bk_level_title(void) {
    bk.collapsed = bk_gone();
    bk_title_show();
}

static int bk_on_scroll(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (!bk.win) return RET_OK;
    bk_collapse();
    bk_fade();
    bk_kick();
    return RET_OK;
}

/* The navbar's small title (az_fit cuts it to the title's width). */
void bk_set_title(const char *utf8) {
    char title[BK_TITLE];
    title[0] = 0;
    bk_cat(title, sizeof title, utf8);
    if (bk.title) az_fit(bk.title, title);
}

/* What the Library's tiles were made for: a hash of the books' folders and cover names; the covers stay when a reload finds the same. */
static unsigned bk_sig(void) {
    unsigned s = 0;
    int b;
    for (b = 0; b < bk.nbooks; ++b) s = s * 31u + bk.books[b].hash + pc_hash(bk.books[b].cover);
    return s;
}

/* The books again (one may have come or gone): the Library level at scroll offset off, with every progress read. */
/* The books read again. Their progress (bk.bst) is by position in the sorted list, which a new or deleted book shifts, so every book's art is looked at again (bk_art_build);
 * the Library reads the rest of the progress again itself (bk_load_library). */
static void bk_scan(void) {
    int b;
    bk.nbooks = bk_scan_books(bk.books, BK_MAX_BOOKS);
    for (b = 0; b < BK_MAX_BOOKS; ++b) bk.bst[b].art = 0;
}

void bk_load_library(int off) {
    unsigned sig;
    bf_leave_cancel();
    bk.level = BL_LIB;
    bk_sheet_close();
    bk.press = bk.pbtn = bk.down = 0;
    grid_drop(&bk.hg);
    grid_drop(&bk.pt);
    bk_scan();
    if (bk.nbooks <= PS_SHOW_MAX) bk.all = 0; /* (books deleted: the See All page has nothing more than the Library) */
    bk_set_title(TR("Audiobooks"));
    memset(bk.bst, 0, BK_MAX_BOOKS * sizeof *bk.bst);
    bk.nparts = 0;
    bk.sel_hash = 0;
    sig = bk_sig();
    if (sig != bk.sig || !bk.g.placeholder || bk.g_lv) {
        grid_drop(&bk.g);
        grid_placeholder(&bk.g);
        bk.cont_hash = 0; /* (the shelf's cover is made again too) */
    }
    bk.g_lv = 0;
    bk.sig = sig;
    bk_read_all();
    bk_pick_cont();
    bk_dl_mark();
    bk.mrows = bk.nm = bk.has_man = 0;
    bk.rev = pc_rev();
    widget_set_text_utf8(bk.big, TR("Audiobooks"));
    bk_show(bk.view, 1);
    bk_show(bk.status, 0);
    bk_show(bk.big, !bk.all);
    bk_size();
    widget_set_prop_int(bk.sv, "yoffset", off);
    bk_level_title(); /* (after the offset: the small title is right at once at a kept offset) */
    bk_fade();
    bk_redraw();
    bk_kick();
}

/* The header's title wrapped and the blocks' tops (content y) of a book or a preview titled `title`: the cover on top, the title (at most two lines), `extra` grey lines more than one, the grey line, the buttons, the rows. */
void bk_header(const char *title, int extra) {
    int y, m = bk_wide(bk.name, BK_TITLE_MAX, title);
    bk.nn = bk_lines(bk.st[BS_TITLE], bk.name, m, BK_NAME_W, BK_NAME_LINES, bk.nl);
    y = BK_ART_Y + PS_ART + BK_NAME_GAP;
    bk.y_name = y;
    y += bk.nn * BK_NAME_PITCH;
    bk.collapse = y - BK_COLLAPSE_BACK;
    y += BK_SUB_GAP + extra * BK_SUB_H;
    bk.y_sub = y;
    y += BK_SUB_H + BK_BTN_GAP;
    bk.y_btn = y;
    y += BK_BTN_H + BK_LIST_GAP;
    bk.y_list = y;
}

/* Book b's page (the books read already): its parts and its progress. A book with a manifest and no part on the card yet has none: its header only. */
static void bk_show_book(int b) {
    int n = bk_load_parts(&bk.books[b], bk.parts, BK_MAX_PARTS);
    if (n < 0 || (n == 0 && bk.books[b].parts)) {
        pod_toast(TR("Storage unavailable"));
        return;
    }
    bf_leave_cancel();
    bk.sel = b, bk.sel_hash = bk.books[b].hash, bk.nparts = n;
    bk.level = BL_BOOK;
    bk_sheet_close();
    bk.press = bk.pbtn = bk.down = 0;
    grid_drop(&bk.hg);
    grid_placeholder(&bk.hg);
    grid_drop(&bk.pt);
    bk_book_progress();
    bk_man_read();
    bk_dl_mark();
    bk_header(bk.books[b].title, 0);
    bk.rev = pc_rev();
    bk_set_title(bk.books[b].title);
    bk.collapsed = 0;
    bk_title_show();
    bk_show(bk.big, 0);
    bk_show(bk.view, 1);
    bk_show(bk.status, 0);
    bk_size();
    widget_set_prop_int(bk.sv, "yoffset", 0);
    bk_fade();
    bk_redraw();
    bk_kick();
}

/* Where Back from a book lands: the Library, or the See All page, at the offset it was left at. */
static int bk_back_off(void) { return bk.all ? bk.all_off : bk.lib_off; }

static void bk_open_book(int b) {
    if (bk.all)
        bk.all_off = bk_off();
    else
        bk.lib_off = bk_off();
    bk_show_book(b);
}

/* The books read again and the Book level of the folder dir (a book just made by the LibriVox download); the Library level when the folder is not a book. */
void bk_open_dir(const char *dir) {
    int b;
    bk_scan();
    for (b = 0; b < bk.nbooks; ++b)
        if (!strcmp(bk.books[b].dir, dir)) {
            bk_show_book(b);
            return;
        }
    bk_load_library(bk_back_off());
}

/* The open book again after the page was behind another or the card changed: found by its key, its parts and progress read again; the Library level when it is gone. */
static void bk_reload_book(void) {
    int b, off = bk_off();
    bk_scan();
    for (b = 0; b < bk.nbooks; ++b)
        if (bk.books[b].hash == bk.sel_hash) break;
    if (b >= bk.nbooks) {
        bk_load_library(0);
        return;
    }
    bk.sel = b;
    bk.nparts = bk_load_parts(&bk.books[b], bk.parts, BK_MAX_PARTS);
    if (bk.nparts < 0 || (bk.nparts == 0 && bk.books[b].parts)) {
        bk_load_library(0);
        return;
    }
    grid_drop(&bk.pt);
    bk_book_progress();
    bk_man_read();
    bk_dl_mark();
    bk_nav();
    bk.rev = pc_rev();
    bk_size();
    widget_set_prop_int(bk.sv, "yoffset", off);
    bk_redraw();
}

/* The download moved (bd_gen): the row's text follows; when a part came, or the download began or ended (or force), the parts and the counts are read again at the same offset, so a part
 * appears in the list as it lands and a book of no part gets its Play capsule with the first. */
static void bk_dl_sync(int force) {
    unsigned sig = bk_dl_sig();
    if (force || sig != bk.bsig) {
        bk_reload_book();
        return;
    }
    bk.bgen = bd_gen();
    bk_retext_parts(1);
    bk_redraw();
}

/* The Library follows it too: the lines of the books with parts to come, and the whole list read again when a part came or the job began or ended. */
static void bk_dl_lib(void) {
    unsigned sig = bk_dl_sig();
    int b;
    if (sig != bk.bsig) {
        bk_load_library(bk_off());
        return;
    }
    bk.bgen = bd_gen();
    for (b = 0; b < bk.nbooks; ++b)
        if (bk.bst[b].total > bk.books[b].parts) bk_retext_lib(b);
    bk_redraw();
}

/* A tap on the download row: a download that runs or waits is paused for good (it does not come back by itself), else it starts; a refusal says why in the page's words. */
static void bk_dl_set(int run) {
    int r = 0, idle = bk_dl_kind(bk.sel_hash) == DR_IDLE;
    if (bk.del_hash) return; /* (the book is being deleted) */
    if (!run && !idle)
        bd_pause(bk.sel_hash);
    else if (run && idle)
        r = bd_start(bk.books[bk.sel].dir);
    if (r) pod_toast(bf_word(r));
    bk_dl_sync(1);
}

static void bk_dl_tap(void) { bk_dl_set(bk_dl_kind(bk.sel_hash) == DR_IDLE); }

/* ---------------------------------------------------------------------------
 * The "..." and its sheet (the Podcasts sheets' widget set, tools/pod_ui.py BK_SHEET_ROWS): on the Book level of a LibriVox book (it has a manifest). Pause Download while the book downloads, Resume Download
 * while parts are missing and it does not (a failure too), Delete Book. A book of your own (no manifest) has none: its files are not ours to delete.
 */
enum { BH_SPEED = 0, BH_PAUSE, BH_RESUME, BH_DELETE, BH_ROWS };

/* The navbar's right end: the "..." on the Book level, with Now Playing the capsule's right cap beside it; else Now Playing is the disc. The small title ends before the leftmost button. */
static void bk_nav(void) {
    int more = bk.level == BL_BOOK && bk.more && bk.sh_card, find = bk.find && bk.level == BL_LV, cap = more || find;
    if (bk.more) m1_show(bk.more, more);
    if (bk.find)
        m1_show(
            bk.find,
            find); /* (the LibriVox level's magnifier, the Podcasts Discover level's: [Search | Now Playing]; the two are never there together) */
    if (bk.np) grid_icons(bk.np, cap ? "ah_nav_play" : "ah_nav_np", cap ? "ah_nav_play_down" : "ah_nav_np_down");
    if (bk.title) grid_title_end(bk.title, cap ? NAV_VIEW_X : NAV_VIEW_X + NAV_VIEW_W);
}

static void bk_sheet_close(void) {
    if (!bk.sheet) return;
    bk.sheet = 0;
    m1_show(bk.sh_scrim, 0);
    m1_show(bk.sh_card, 0);
}

static void bk_sheet_open(void) {
    void *row[BH_ROWS], *hr[BH_ROWS];
    int n = 0, i, rows[BH_ROWS];
    if (!bk.sh_card || bk.sheet || bk.level != BL_BOOK || bk.del_hash) return;
    rows[n++] = BH_SPEED;
    m1_sheet_value(bk.sh_tx[BH_SPEED], bk.sh_vl, bk_speed_name[pc_speed_get(bk.books[bk.sel].hash)]);
    if (bk.mrows) rows[n++] = bk_dl_kind(bk.sel_hash) != DR_IDLE ? BH_PAUSE : BH_RESUME;
    if (bk.has_man) rows[n++] = BH_DELETE;
    for (i = 0; i < BH_ROWS; ++i) {
        int at = -1, k;
        for (k = 0; k < n; ++k)
            if (rows[k] == i) at = k;
        if (at < 0)
            m1_show(bk.sh_row[i], 0);
        else
            row[at] = bk.sh_row[i], hr[at] = bk.sh_hr[i];
    }
    bk.sheet = 1;
    m1_sheet_rows(bk.sh_scrim, bk.sh_card, BK_W, row, hr, n);
}

/* A tap on Playback Speed: the next of 1x 1.25x 1.5x 2x, saved under the book's key at once and applied (a part that plays takes it now, the stock page shows it); the sheet stays, the value follows (the Show sheet's row). */
static void bk_speed_next(void) {
    unsigned h = bk.books[bk.sel].hash;
    int mode = (pc_speed_get(h) + 1) % PC_SPEEDS;
    if (!pc_speed_set(h, mode)) pod_toast(TR("Storage unavailable"));
    m1_sheet_value(bk.sh_tx[BH_SPEED], bk.sh_vl, bk_speed_name[pc_speed_get(h)]);
    pc_speed_apply(h);
    bk_redraw();
}

/* Whether the player is on a file of the open book. */
static int bk_book_playing(void) {
    void *track = cc_playing();
    return track && bk_book_of(*(const char **)((char *)track + REC_PATH)) == bk.sel_hash;
}

/* The file `name` of the book folder dir (and, for a part, the same with ".part"): removed, and its place in the ring forgotten. 1 when the file is gone after it. */
static int bk_rm(const char *dir, const char *name, int part) {
    char path[BK_FILE * 2 + BK_REL + 40];
    unsigned at = 0, k;
    for (k = 0; bk.root[k] && at < sizeof path - 8; ++k) path[at++] = bk.root[k];
    path[at++] = '/';
    for (k = 0; dir[k] && at < sizeof path - 8; ++k) path[at++] = dir[k];
    path[at++] = '/';
    for (k = 0; name[k] && at < sizeof path - 8; ++k) path[at++] = name[k];
    path[at] = 0;
    pc_mark(pc_hash(path), 0);
    unlink(path);
    if (part) {
        bk_cat(path, sizeof path, ".part");
        unlink(path);
        path[at] = 0;
    }
    return access(path, F_OK) != 0;
}

/* The files the manifest of the book folder del_dir names (and their .part files), a cover the download wrote, the manifest, then the folder if nothing else is in it (rmdir: never a recursive delete, never a file
 * the manifest does not name). A part that cannot be removed leaves the manifest (the book stays whole enough to be deleted or fetched again) and a toast. Then the Library, read again. */
static void bk_delete_run(void) {
    bd_book_t *b;
    char dirpath[BK_FILE * 2 + 40];
    int i, ok = 1;
    unsigned at = 0, k, h = bk.del_hash;
    const char *dir = bk.del_dir;
    bk.del_hash = 0;
    b = bd_open(dir);
    if (!b) {
        pod_toast(TR("Storage unavailable"));
        return;
    }
    for (i = 0; i < b->n; ++i) ok &= bk_rm(dir, b->parts[i].file, 1);
    bd_free(b);
    if (ok) {
        bk_rm(dir, "cover.jpg", 0); /* (the cover the download copied from the preview) */
        bk_rm(dir, "cover.png", 0);
        ok = bk_rm(dir, BD_MANIFEST, 0);
    }
    if (ok) {
        for (k = 0; bk.root[k] && at < sizeof dirpath - 2; ++k) dirpath[at++] = bk.root[k];
        dirpath[at++] = '/';
        for (k = 0; dir[k] && at < sizeof dirpath - 1; ++k) dirpath[at++] = dir[k];
        dirpath[at] = 0;
        rmdir(dirpath); /* (fails, and stays, when the folder holds anything else) */
    }
    pc_flush();
    if (!ok) pod_toast(TR("Storage unavailable"));
    if (bk.level == BL_LIB)
        bk_load_library(bk_off());
    else if (bk.level == BL_BOOK && bk.sel_hash == h)
        bk_load_library(bk_back_off());
}

/* Delete Book: refused with a toast while the player is on one of its files; else after a confirm, a running download is stopped first and the files go when its thread has let go of them (the tick, bk_tick:
 * bd_active() is the thread's own flag, cleared after its last touch of a file), so nothing here waits. */
static void bk_delete_ask(void) {
    if (!bk.has_man || bk.level != BL_BOOK || bk.del_hash) return;
    if (bk_book_playing()) {
        pod_toast(TR("This book is playing"));
        return;
    }
    if (!pod_confirm(TR("Delete this book and its files?"))) return;
    bk.del_hash = bk.sel_hash;
    bk.del_dir[0] = 0;
    bk_cat(bk.del_dir, sizeof bk.del_dir, bk.books[bk.sel].dir);
    if (bk_dl_kind(bk.sel_hash) == DR_RUN) {
        bd_pause(
            bk.sel_hash); /* (the queue goes on with the next book: the tick deletes when this one no longer runs) */
        return;
    }
    bd_pause(bk.sel_hash); /* a book waiting leaves the queue; nothing holds its files */
    bk_delete_run();
}

static int bk_on_more(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (bk.win) bk_sheet_open();
    return RET_OK;
}

/* The navbar's magnifier (the Podcasts Discover level's): the search level; Back returns to the LibriVox level where it was. */
static int bk_on_find(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (bk.win && bk.level == BL_LV && !bk.sheet) bf_search();
    return RET_OK;
}

static int bk_on_sheet_scrim(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    bk_sheet_close();
    return RET_OK;
}

/* A row of the sheet: the state the row was for is looked at again (the download may have ended under the sheet). */
static int bk_on_sheet_row(void *ctx, void *e) {
    int id = (int)(unsigned)ctx - 1;
    (void)e;
    if (!bk.win || !bk.sheet || id < 0 || id >= BH_ROWS) return RET_OK;
    if (id == BH_SPEED) { /* a tap cycles; the sheet stays */
        bk_speed_next();
        return RET_OK;
    }
    bk_sheet_close();
    if (bk.level != BL_BOOK || !bk.has_man) return RET_OK;
    if (id == BH_PAUSE)
        bk_dl_set(0);
    else if (id == BH_RESUME)
        bk_dl_set(1);
    else
        bk_delete_ask();
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * Playing
 */
/* An stSongInfo of our own for part p of the open book (strings duplicated; the deque copies them again and the caller frees these). */
static void bk_record(unsigned *rec, const bk_part_t *p, const char *path) {
    const char *name = path, *s;
    const bk_book_t *b = &bk.books[bk.sel];
    for (s = path; *s; ++s)
        if (*s == '/') name = s + 1;
    memset(rec, 0, REC_SIZE);
    *(char **)((char *)rec + REC_NAME) = strdup(name);
    *(char **)((char *)rec + REC_PATH) = strdup(path);
    *(char **)((char *)rec + REC_TITLE) = strdup(p->title);
    *(char **)((char *)rec + REC_ALBUM) = strdup(b->title);
    *(char **)((char *)rec + REC_ARTIST) = strdup(b->title);
    *(int *)((char *)rec + REC_TYPE) = 8;
    *(int *)((char *)rec + REC_CLASS) = 1;
}

static void bk_record_free(unsigned *rec) {
    static const int field[] = {REC_NAME, REC_PATH, REC_TITLE, REC_ALBUM, REC_ARTIST};
    unsigned i;
    for (i = 0; i < sizeof field / sizeof *field; ++i) free(*(char **)((char *)rec + field[i]));
}

/* Parts `from` to the end as the queue, Now Playing. again: the book's marks and places are forgotten first (Play Again). Nothing starts, and a toast says why, when the first part is not on the card or
 * any part is an MP4 the guard refuses. */
static void bk_play(int from, int again) {
    void *queue;
    int i, ok = 0;
    char path[BK_FILE * 2 + BK_REL + 8];
    struct {
        void *dq;
        int idx, cls, mode;
    } context;
    const bk_book_t *b = &bk.books[bk.sel];
    if (from < 0 || from >= bk.nparts || !bk_part_path(b, &bk.parts[from], path, sizeof path) || access(path, F_OK)) {
        pod_toast(TR("Storage unavailable"));
        return;
    }
    for (i = from; i < bk.nparts; ++i) {
        if (!bk_part_path(b, &bk.parts[i], path, sizeof path)) continue;
        if (!bk_mp4_fits(path)) {
            pod_toast(TR("Too long. Split it into parts."));
            return;
        }
    }
    queue = _create_deque("stSongInfo");
    if (!queue) return;
    deque_init(queue);
    for (i = from; i < bk.nparts; ++i) {
        unsigned rec[REC_SIZE / 4];
        if (!bk_part_path(b, &bk.parts[i], path, sizeof path)) continue; /* (the model refused such names: the belt) */
        bk_record(rec, &bk.parts[i], path);
        _deque_push_back(queue, rec);
        bk_record_free(rec);
        ++ok;
    }
    if (!ok) {
        deque_destroy(queue);
        pod_toast(TR("Storage unavailable"));
        return;
    }
    if (again) {
        for (i = 0; i < bk.nparts; ++i) pc_mark(bk.parts[i].hash, 0);
    } else
        pc_restart(bk.parts[from].hash);
    pc_speed_apply(b->hash);
    pod_set_in_order();
    *(int *)G_CLASS_TYPE = 1;
    context.dq = queue, context.idx = 0, context.cls = 1, context.mode = PLAY_MODE;
    navigator_to_with_context("playing_page", &context); /* start_player copies the queue */
    deque_destroy(queue);
}

static void bk_play_button(void) {
    if (!bk.nparts) { /* a book with no part yet: the capsule is the download's button */
        bk_dl_tap();
        return;
    }
    if (bk.state == BK_FINISHED)
        bk_play(0, 1);
    else
        bk_play(bk.state == BK_IN_PROGRESS ? bk.cur : 0, 0);
}

/* A tap on Continue Listening: the book plays from its place, as the Podcasts item resumes its episode (the book's parts are read for the queue, then let go: the page stays on the Library level). */
static void bk_cont_play(void) {
    int b = bk.cont, n;
    if (b < 0 || b >= bk.nbooks) return;
    n = bk_load_parts(&bk.books[b], bk.parts, BK_MAX_PARTS);
    if (n <= 0) {
        pod_toast(TR("Storage unavailable"));
        return;
    }
    bk.sel = b, bk.nparts = n;
    bk_book_progress();
    bk_play(bk.state == BK_FINISHED ? 0 : bk.state == BK_IN_PROGRESS ? bk.cur : 0, bk.state == BK_FINISHED);
    bk.nparts = 0;
}

/* See All: the complete list of books from the top, the title in the navbar and no large title (the Show page's All Episodes page); Back returns to the Library where it was. */
static void bk_all_open(void) {
    bk.lib_off = bk_off();
    bk.all = 1, bk.all_off = 0;
    bk_load_library(0);
}

static void bk_all_close(void) {
    bk.all = 0;
    bk_load_library(bk.lib_off);
}

/* ---------------------------------------------------------------------------
 * Touch
 */
/* What a touch hit: the row (Library: the book; Book: the part) or the header's button or another part (BP_*, 0 for the row index), -1 for none. */
static int bk_hit(void *e, int *part) {
    int pt[2], row;
    if (BK_FIND) return bf_hit(e, part);
    pt[0] = I(e, PE_X), pt[1] = I(e, PE_Y);
    widget_to_local(bk.view, pt);
    *part = BP_BODY;
    if (bk.level == BL_LIB) {
        int cy = bk.l_shelf + PP_HEAD_PITCH;
        if (bk.l_shelf && pt[0] >= PP_SHELF_X && pt[0] < PP_SHELF_X + PP_SHELF_W && pt[1] >= cy &&
            pt[1] < cy + PP_SHELF_LEFT_Y + PP_SHELF_LEFT_H)
            return *part = BP_CONT, 0;
        if (bk.l_lv && pt[1] >= bk.l_lv && pt[1] < bk.l_lv + PC_ROW_H) return *part = BP_LV, 0;
        if (bk.l_all && pt[1] >= bk.l_all && pt[1] < bk.l_all + PS_MORE_H) return *part = BP_ALL, 0;
        row = (pt[1] - bk.l_list) / PC_ROW_H;
        return pt[1] >= bk.l_list && row < bk.l_n ? row : -1;
    }
    if (pt[1] < bk.y_list) {
        int btn = bk_hdr_btn();
        if (btn && pt[1] >= bk.y_btn && pt[1] < bk.y_btn + BK_BTN_H && pt[0] >= bk_btn_x() &&
            pt[0] < bk_btn_x() + BK_PLAY_W)
            return *part = BP_PLAY, 0;
        return -1;
    }
    row = (pt[1] - bk.y_list) / PC_ROW_H;
    return row < bk_count() ? row : -1;
}

static void bk_set_press(int p, int btn) {
    if (bk.press == p && bk.pbtn == btn) return;
    bk.press = p, bk.pbtn = btn;
    bk_redraw();
}

static int bk_on_down(void *ctx, void *e) {
    int a, part;
    (void)ctx;
    bk.down = 0;
    if (!e || !bk.view) return RET_OK;
    a = bk_hit(e, &part);
    bk.down = a + 1; /* (-1: nothing) */
    bk.down_part = part;
    bk.down_x = I(e, PE_X), bk.down_y = I(e, PE_Y);
    if (a >= 0)
        bk_set_press(part == BP_BODY ? a + 1 : 0, part == BP_BODY                        ? 0
                                                  : part == BP_FIELD || part == BP_CLEAR ? 0
                                                                                         : part);
    return RET_OK;
}

static int bk_on_up(void *ctx, void *e) {
    int a = bk.down, part = bk.down_part, same, part2;
    (void)ctx;
    bk.down = 0;
    bk_set_press(0, 0);
    if (!a || !e || !bk.view || (bk.del_hash && bk.level == BL_BOOK)) return RET_OK;
    if (bk_abs(I(e, PE_X) - bk.down_x) >= SC_DRAG_PX || bk_abs(I(e, PE_Y) - bk.down_y) >= SC_DRAG_PX) return RET_OK;
    same = bk_hit(e, &part2);
    if (same != a - 1 || part2 != part) return RET_OK;
    if (BK_FIND)
        bf_tap(same, part);
    else if (bk.level == BL_LIB && part == BP_LV)
        bf_enter();
    else if (bk.level == BL_LIB && part == BP_ALL)
        bk_all_open();
    else if (bk.level == BL_LIB && part == BP_CONT)
        bk_cont_play();
    else if (bk.level == BL_LIB)
        bk_open_book(same);
    else if (part == BP_PLAY)
        bk_play_button();
    else if (bk_row_part(same) >= 0)
        bk_play(bk_row_part(same), 0);
    else if (bk_dl_kind(bk.sel_hash) ==
             DR_IDLE) /* a part that is not on the card: the book's download starts (or goes on) */
        bk_dl_set(1);
    return RET_OK;
}

static int bk_on_abort(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    bk.down = 0;
    bk_set_press(0, 0);
    return RET_OK;
}

static int bk_on_back(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (!bk.win) return RET_OK;
    if (bk.sheet) { /* the sheet: Back closes it only */
        bk_sheet_close();
        return RET_OK;
    }
    if (bk.level == BL_BOOK)
        bk_load_library(bk_back_off()); /* the Library (or the See All page) again, where it was */
    else if (bk.level == BL_LIB && bk.all)
        bk_all_close(); /* the See All page: the Library again, at the offset it was left at */
    else if (bk.level == BL_LIB)
        navigator_back();
    else if (!bf_back())
        bk_load_library(bk.lib_off);
    return RET_OK;
}

/* ---------------------------------------------------------------------------
 * The timer and the window's events
 */
static int bk_tick(const void *timer) {
    (void)timer;
    if (!bk.win || !bk.fg) {
        bk.timer = 0;
        return RET_OK;
    }
    pc_note(cc_playing());
    if (m1_screen_lit() && bk.level == BL_BOOK) bk_wave_sync(); /* the playing marker follows the player */
    if (bk.del_hash && bd_active() != bk.del_hash)
        bk_delete_run(); /* Delete Book: the download's thread has let go of the files */
    if (m1_screen_lit() && (BK_FIND)) bf_sync(); /* an answer, a thumbnail, the preview */
    if (m1_screen_lit() && (bd_gen() != bk.bgen || bk_dl_sig() != bk.bsig)) {
        if (bk.level == BL_BOOK)
            bk_dl_sync(0);
        else if (bk.level == BL_LIB)
            bk_dl_lib();
        else
            bk.bgen = bd_gen();
    }
    if (m1_screen_lit() && !bk.load_timer && bk_load_pending()) bk_kick(); /* the screen is back on: the covers go on */
    if (m1_screen_lit() && !bk.load_timer) bk_art_build(); /* (the worker another page held may be free now) */
    if (m1_screen_lit() &&
        pc_rev() != bk.rev) { /* a place or a mark moved (a part played on): what is shown is made again */
        bk.rev = pc_rev();
        if (bk.level == BL_BOOK) {
            bk_book_progress();
            bk_retext_parts(0);
        } else if (bk.level == BL_LIB)
            bk_refresh_playing();
        bk_redraw();
    }
    return RET_REPEAT;
}

/* The keep-awake timer (1 s), as Podcasts' downloads timer: while a download runs it sets stock's standby and auto power-off countdowns again (reset_poweroptions_timer(1, 1, 0), the screen's own is
 * left alone). It lives as long as the page does, also behind another page and with the screen off; the page closed, the device may go to standby and the download stops with a network error. */
static int bk_awake_tick(const void *timer) {
    (void)timer;
    if (!bk.win) {
        bk.awake = 0;
        return RET_OK;
    }
    if (bd_active()) reset_poweroptions_timer(1, 1, 0);
    return RET_REPEAT;
}

static void bk_arm(void) {
    if (!bk.timer) bk.timer = timer_add(bk_tick, (void *)0, BK_TICK_MS);
    if (!bk.awake) bk.awake = timer_add(bk_awake_tick, (void *)0, BK_AWAKE_MS);
}

static int bk_on_fg(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    bk.fg = 1;
    bk_arm();
    if (bk.level == BL_LIB)
        bk_load_library(bk_off()); /* the card or the ring may have changed while another page was in front */
    else if (bk.level == BL_BOOK)
        bk_reload_book();
    else
        bf_fg();
    bk_kick();
    return RET_OK;
}

static int bk_on_bg(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    bk.fg = 0;
    bk_art_end(); /* (the worker is the other pages' too) */
    if (bk.timer) timer_remove(bk.timer);
    if (bk.load_timer) timer_remove(bk.load_timer);
    bk.timer = bk.load_timer = 0;
    bk.down = 0;
    bk.press = bk.pbtn = 0;
    bf_bg();
    pc_flush();
    return RET_OK;
}

static int bk_on_destroy(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (bk.timer) timer_remove(bk.timer);
    if (bk.load_timer) timer_remove(bk.load_timer);
    if (bk.awake) timer_remove(bk.awake);
    bk_art_end();
    pc_flush();
    grid_free(&bk.g);
    grid_free(&bk.hg);
    grid_free(&bk.pt);
    grid_free(&bk.sg);
    bf_free();
    if (bk.atlas) bitmap_destroy(bk.atlas);
    if (bk.wave) bitmap_destroy(bk.wave);
    if (bk.chev) bitmap_destroy(bk.chev);
    if (bk.ltile) bitmap_destroy(bk.ltile);
    free(bk.books);
    free(bk.parts);
    free(bk.bst);
    free(bk.mp);
    memset(&bk, 0, sizeof bk);
    return RET_OK;
}

/* The Extras item Audiobooks. 0 once the page is up, -1 if it could not open (the kill switch, a page already up, an asset that is not ours). */
int books_open(void) {
    static const char *const st_name[BS_N] = {"label_bk_title", "label_bk_sub",   "label_bk_btn",  "label_bk_dim",
                                              "label_bk_meta",  "label_bk_hint",  "label_ps_sech", "label_ps_stitle",
                                              "label_ps_sleft", "label_ps_ctitle"};
    int i, ok = 1;
    if (bk.win || access(KILL_SD, F_OK) == 0) return -1;
    memset(&bk, 0, sizeof bk);
    bk.cont = -1;
    bf_reset();
    bk.win = window_open("m1plus_books");
    if (!bk.win) return -1;
    widget_on(bk.win, EVT_DESTROY, bk_on_destroy, (void *)0);
    m1_bind(bk.win, "btn_return", bk_on_back, (void *)0);
    bk.np = m1_bind(bk.win, "btn_backtoplayer", m1_on_player, (void *)0);
    bk.more = m1_bind(bk.win, "btn_more", bk_on_more, (void *)0);
    bk.find = m1_bind(bk.win, "btn_search", bk_on_find, (void *)0); /* (the LibriVox level's magnifier) */
    bk.sh_scrim = m1_bind(bk.win, "bk_sh_scrim", bk_on_sheet_scrim, (void *)0);
    bk.sh_card = widget_lookup(bk.win, "bk_sh_card", 1);
    for (i = 0; i < BH_ROWS; ++i) {
        static const char *const id[BH_ROWS] = {"bk_sh_speed", "bk_sh_pause", "bk_sh_resume", "bk_sh_delete"};
        char name[24];
        bk.sh_row[i] = m1_bind(bk.win, id[i], bk_on_sheet_row, (const void *)(unsigned)(i + 1));
        snprintf(name, sizeof name, "%s_hr", id[i]);
        bk.sh_hr[i] = widget_lookup(bk.win, name, 1);
        snprintf(name, sizeof name, "%s_tx", id[i]);
        bk.sh_tx[i] = widget_lookup(bk.win, name, 1);
        if (!bk.sh_row[i] || !bk.sh_hr[i] || !bk.sh_tx[i])
            bk.sh_card = (void *)0; /* (a missing widget leaves the page without its sheet) */
    }
    bk.sh_vl = widget_lookup(bk.win, "bk_sh_speed_vl", 1);
    if (!bk.sh_vl) bk.sh_card = (void *)0;
    bk.view = widget_lookup(bk.win, "view_grid", 1);
    bk.sv = widget_lookup(bk.win, "books_scrollview", 1);
    bk.status = widget_lookup(bk.win, "label_status", 1);
    bk.title = widget_lookup(bk.win, "label_title", 1);
    bk.fade = widget_lookup(bk.win, "img_nb_fade", 1);
    bk.st_title = widget_lookup(bk.win, "label_row_title", 1);
    bk.st_sub = widget_lookup(bk.win, "label_row_sub", 1);
    bk.big = widget_lookup(bk.win, "bk_big", 1);
    for (i = 0; i < BS_N; ++i) {
        bk.st[i] = widget_lookup(bk.win, st_name[i], 1);
        ok &= bk.st[i] != (void *)0;
    }
    if (!bk.view || !bk.sv || !bk.status || !bk.title || !bk.st_title || !bk.st_sub || !bk.big || !ok) {
        navigator_back(); /* an asset that is not ours */
        return -1;
    }
    label_set_line_wrap(bk.status, 1);
    bk.books = calloc(BK_MAX_BOOKS, sizeof *bk.books);
    bk.parts = calloc(BK_MAX_PARTS, sizeof *bk.parts);
    bk.bst = calloc(BK_MAX_BOOKS, sizeof *bk.bst);
    bk.mp = calloc(BK_MAX_PARTS, sizeof *bk.mp);
    if (!bk.books || !bk.parts || !bk.bst || !bk.mp || !grid_init(&bk.g, bk.win, BK_TILES, LIST_ART, LIST_R) ||
        !grid_init(&bk.hg, bk.win, 1, PS_ART, PS_ART_R) || !grid_init(&bk.pt, bk.win, BK_PTILES, LIST_ART, 0) ||
        !grid_init(&bk.sg, bk.win, 1, PP_SHELF_ART, PP_SHELF_R)) {
        bk_empty("Not enough memory");
        return 0;
    }
    bk.g.st_title = bk.st_title, bk.g.st_sub = bk.st_sub;
    bk.pt.st_title = bk.st_title, bk.pt.st_sub = bk.st_sub;
    bk.ltile = pg_rgba_win(bk.win, "pod_ic_discovertile", PA_TILE_PX, PA_TILE_PX);
    bk.wave = grid_wave_make(bk.win); /* (NULL when it does not decode: no marker) */
    bk.pl_row = -1;
    bf_setup(bk.win);
    bk_root(bk.root);
    bk.fg = 1;
    widget_on(bk.sv, EVT_SCROLL, bk_on_scroll, (void *)0);
    widget_on(bk.sv, EVT_SCROLL_END, bk_on_scroll, (void *)0);
    widget_on(bk.win, EVT_WINDOW_TO_FG, bk_on_fg, (void *)0);
    widget_on(bk.win, EVT_WINDOW_TO_BG, bk_on_bg, (void *)0);
    widget_on(bk.view, EVT_POINTER_DOWN, bk_on_down, (void *)0);
    widget_on(bk.view, EVT_POINTER_UP, bk_on_up, (void *)0);
    widget_on(bk.view, EVT_POINTER_ABORT, bk_on_abort, (void *)0);
    widget_on(bk.view, EVT_AFTER_PAINT, bk_on_paint, (void *)0);
    bk_arm();
    bk_load_library(0);
    return 0;
}
