/* Song list operations shared by the Songs page and the album page (patch/songops.h has the design).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 */
#include "offsets.inc"
#include "stock.h"
#include "common.h"
#include "home.h"
#include "covercache.h"
#include "i18n.h"
#include "podcasts.h"
#include "songops.h"
#include "libsrc.h"
#include "picker.h"

static int so_marked(const unsigned char *sel, unsigned i) { return sel[i >> 3] >> (i & 7) & 1; }

int so_selection(unsigned count, const unsigned char *sel) {
    unsigned i;
    if (!*(void **)SEL_VEC) return 0;
    select_recordinit((int)count);
    for (i = 0; i < count; ++i)
        if (so_marked(sel, i)) set_selectindex((int)i);
    return 1;
}

/* The stock confirm dialog: modal, the button pressed is the result. */
static void so_ask(const char *text, int kind, int *answer) {
    struct {
        int kind, ms;
        char text[MSGINFO_TEXT], text2[MSGINFO_TEXT];
    } info;
    unsigned i;
    memset(&info, 0, sizeof info);
    info.kind = kind;
    for (i = 0; text[i] && i < sizeof info.text - 1; ++i) info.text[i] = text[i];
    *answer = pod_confirm_dialog(&info);
}

/* Delete: the stock handler's sequence (@0x527f48): nothing selected is a message; the confirm dialog (0xa: the library only, 0x14: the files too); then
 * batch_delete_file on the shown list and the selection; the message. The stock handler leaves the list as it was (the page rebuilds on its next show): the pages read it again.
 * The class is the list's, as the stock handler passes g_class_type: batch_delete_file removes the songs from the library (the generic loop: the library, Hi-Res,
 * Recently Added, an album's tracks), from myfav, oftenplay, recentplay or the playlist (its jump tables @0x74b7b0, @0x74b7d4; docs/modules/addresses.md), and the files when asked. */
int so_delete(int cls, void *list, unsigned count, const unsigned char *sel, unsigned nsel, int valid) {
    int r;
    if (!nsel) {
        pod_toast(TR("msg_delsongfailed"));
        return 0;
    }
    so_ask(TR("msg_delsong"), CONFIRM_KIND_DELETE, &r);
    if (r != CONFIRM_DELETE_LIBRARY && r != CONFIRM_DELETE_FILE) return 0;
    if (!valid || !so_selection(count, sel)) return -1;
    batch_delete_file(cls, list, *(void **)SEL_VEC, 0, r == CONFIRM_DELETE_FILE);
    pod_toast(TR("msg_delsongsuccess"));
    return 1;
}

int so_card(void) { return access("/tmp/mmc_add", F_OK) == 0; }

const char *so_missing(void) { return TR(so_card() ? "File not found" : "Storage unavailable"); }

/* A row is checked only when its path is on the card (SO_CARD_ROOT): any other path (USB, none) is never tested, marked or deleted. */
#define SO_CARD_ROOT "/mnt/mmc/"
static int so_on_card(const char *p) {
    const char *r = SO_CARD_ROOT;
    while (*r && *p == *r) ++p, ++r;
    return !*r;
}

unsigned so_gone_mark(void *list, unsigned count, unsigned char *sel, unsigned *checked) {
    unsigned i, gone = 0;
    memset(sel, 0, (count + 7) / 8);
    for (i = 0, *checked = 0; i < count; ++i) {
        const char *p = cc_str(deque_at(list, i), REC_PATH);
        if (!so_on_card(p)) continue;
        ++*checked;
        if (access(p, F_OK) != 0) sel[i >> 3] |= (unsigned char)(1 << (i & 7)), ++gone;
    }
    return gone;
}

/* A playlist song's row id (REC_ID: getMusicByPlayList's `select * from playlist where id > 100 and cd_num=`); the ids up to PL_MAX are the playlists themselves and
 * are never written here. */
static int so_row_id(void *rec) {
    int id = I(rec, REC_ID);
    return id > PL_MAX ? id : 0;
}

int *so_marked_ids(void *list, unsigned count, const unsigned char *sel, unsigned n) {
    int *ids = calloc(n ? n : 1, sizeof *ids);
    unsigned i, k = 0;
    for (i = 0; ids && i < count && k < n; ++i)
        if (so_marked(sel, i)) ids[k++] = so_row_id(deque_at(list, i));
    return ids;
}

unsigned so_keep_ids(void *list, unsigned count, unsigned char *sel, const int *ids, unsigned n) {
    unsigned i, k, kept = 0;
    for (i = 0; i < count; ++i) {
        int id;
        if (!so_marked(sel, i)) continue;
        id = so_row_id(deque_at(list, i));
        for (k = 0; id && k < n && ids[k] != id; ++k) {
        }
        if (id && k < n)
            ++kept;
        else
            sel[i >> 3] &= (unsigned char)~(1 << (i & 7));
    }
    return kept;
}

/* The library's row a missing playlist row now is: the same file name (the rows asked for), CUE range, title, album and artist, another path that is on the card
 * (so_on_card: a row is never moved to a USB path, which the check would not look at again), and its file there. */
static int so_same_song(void *lib, void *rec) {
    return !strcmp(cc_str(lib, REC_NAME), cc_str(rec, REC_NAME)) && I(lib, REC_CUE_START) == I(rec, REC_CUE_START) &&
           I(lib, REC_CUE_END) == I(rec, REC_CUE_END) && !strcmp(cc_str(lib, REC_TITLE), cc_str(rec, REC_TITLE)) &&
           !strcmp(cc_str(lib, REC_ALBUM), cc_str(rec, REC_ALBUM)) &&
           !strcmp(cc_str(lib, REC_ARTIST), cc_str(rec, REC_ARTIST)) && so_on_card(cc_str(lib, REC_PATH)) &&
           strcmp(cc_str(lib, REC_PATH), cc_str(rec, REC_PATH)) && !access(cc_str(lib, REC_PATH), F_OK);
}

/* text with its quotes doubled, after o; the new end. */
static char *so_quoted(char *o, const char *text) {
    *o++ = '\'';
    for (; *text; ++text) {
        if (*text == '\'') *o++ = '\'';
        *o++ = *text;
    }
    *o++ = '\'';
    return o;
}

/* One playlist row's path: `update playlist set fileurl='..' where id=N` through stock's own statement runner (toolsUpdateDbTable: 1 when it ran). */
static int so_set_path(int id, const char *path) {
    static const char head[] = "update playlist set fileurl=";
    char tail[32], *sql = calloc(sizeof head + 2 * strlen(path) + 2 + sizeof tail, 1), *o;
    int ok;
    if (!sql) return 0;
    memcpy(sql, head, sizeof head - 1);
    o = so_quoted(sql + sizeof head - 1, path);
    snprintf(tail, sizeof tail, " where id=%d", id);
    memcpy(o, tail, strlen(tail) + 1);
    ok = toolsUpdateDbTable(STOCK_DB_PATH, sql) == 1;
    free(sql);
    return ok;
}

/* SO_RELINK_ROWS marked rows from row `from` on: the library's rows with their file names in one query (dailymix.c dm_rows' way: stock's song query and row callback
 * with our WHERE, the rows in *tools_pdeq_directory, cleared after), then each marked row that has a twin gets the twin's path. *next: where the following chunk starts. */
#define SO_RELINK_ROWS 40
static unsigned so_relink_chunk(void *list, unsigned count, const unsigned char *sel, unsigned from, unsigned *next) {
    static const char head[] = "select * from songtable where filename in (";
    unsigned i, k, n = sizeof head + 1, rows = 0, done = 0, end, nlib;
    char *sql, *o;
    void *lib;
    for (i = from; i < count && rows < SO_RELINK_ROWS; ++i)
        if (so_marked(sel, i)) n += 2 * strlen(cc_str(deque_at(list, i), REC_NAME)) + 3, ++rows;
    *next = end = i;
    if (!rows) return 0;
    sql = calloc(n, 1);
    if (!sql) return 0;
    memcpy(sql, head, sizeof head - 1);
    o = sql + sizeof head - 1;
    for (i = from, k = 0; i < end; ++i) {
        if (!so_marked(sel, i)) continue;
        if (k++) *o++ = ',';
        o = so_quoted(o, cc_str(deque_at(list, i), REC_NAME));
    }
    *o++ = ')';
    lib = toolsQueryDbTable(STOCK_DB_PATH, sql, STOCK_SONG_ROW, 0) >= 0 ? *(void **)PDEQ_TOOLS_TMP : (void *)0;
    free(sql);
    nlib = lib ? deque_size(lib) : 0;
    for (i = from; i < end && nlib; ++i) {
        void *rec = deque_at(list, i);
        if (!so_marked(sel, i) || !so_row_id(rec)) continue;
        for (k = 0; k < nlib && !so_same_song(deque_at(lib, k), rec); ++k) {
        }
        if (k < nlib && so_set_path(so_row_id(rec), cc_str(deque_at(lib, k), REC_PATH))) ++done;
    }
    if (lib) deque_clear(lib);
    return done;
}

unsigned so_relink(void *list, unsigned count, const unsigned char *sel) {
    unsigned at = 0, done = 0;
    while (at < count) done += so_relink_chunk(list, count, sel, at, &at);
    return done;
}

unsigned so_clean(void *list, unsigned count, const unsigned char *sel) {
    unsigned i, done = 0;
    for (i = 0; i < count; ++i) {
        int id = so_marked(sel, i) ? so_row_id(deque_at(list, i)) : 0;
        if (id && toolsDeleteItemById("playlist", STOCK_DB_PATH, id) == 1) ++done;
    }
    if (done)
        *(volatile unsigned char *)DELETE_FLAG = 1; /* as batch_delete_file leaves it after a delete (@0x4e1474) */
    return done;
}

/* Add to playlist: our picker (patch/picker.c: the Playlists page in pick mode) over the page, which adds the selection to the playlist that is tapped and closes. Where
 * it cannot open, the stock Add button's path (@0x5280c0) to its playlist picker: playlist_page with the add context; tapping a playlist there adds the
 * selection (batch_add_file on *pdeq_showlist and the vector) and closes the picker. The title the picker may overwrite and the browsing class it sets are put back
 * by the page when its window is back in front (ours puts them back itself). */
int so_add(int cls, unsigned count, const unsigned char *sel, unsigned nsel, int valid, char *title_save, int *picker) {
    if (!nsel) {
        pod_toast(TR("msg_addfailed"));
        return 0;
    }
    if (!valid) return -1;
    memcpy(title_save, (void *)NAV_TITLE, 0x200);
    if (picker_open(cls, count, sel) > 0) {
        *picker = 1;
        return 1;
    }
    if (!so_selection(count, sel)) return -1;
    *(int *)NAVIGATION_STATUS =
        0; /* the picker's mode is a page that is not in multi-select (@0x53d300 tests navigation_status != 1) */
    *picker = 1;
    navigator_to_with_context(
        "playlist_page",
        (const void *)(long)(PICKER_ADD | cls)); /* batch_add_file takes the class from it, as from the stock button */
    return 1;
}

void *so_row_deque(void *rec) {
    void *d = _create_deque("stSongInfo");
    if (!d) return (void *)0;
    deque_init(d);
    _deque_push_back(d, rec);
    return d;
}

/* Now Playing on the queue at idx with class cls: navigator_to_with_context("playing_page", {queue, idx, cls, PLAY_MODE}); start_player copies the queue. */
void pod_start_player(void *queue, int idx, int cls) {
    struct {
        void *dq;
        int idx, cls, mode;
    } context;
    context.dq = queue, context.idx = idx, context.cls = cls, context.mode = PLAY_MODE;
    navigator_to_with_context("playing_page", &context);
}

/* Open Now Playing on the queue exactly as a track row's tap does (the stock album row handler @0x52569c, its tail
 * @0x5258c8..0x525970): when songerinfoflag is set and a playing_page is in the stack, the windows above it are popped
 * with navigator_back and the old playing_page is closed (the stock loop, which also stops at home_page); then
 * navigator_to_with_context("playing_page", {queue, index, class, 2}), whose init starts the player. Stock's loop
 * trusts every navigator_back to change the top window at once (true for these pages: none has a close animation);
 * a bound of POP_MAX turns that trust into a limit, after which the page is opened over what is left. */
void pod_open_player(void *queue, int idx,
                     int cls) { /* (the album page's so_open_fn; also the Daily Mix card's play disc) */
    if (*(unsigned char *)SONGER_FLAG && navigator_window_is_exist("playing_page")) {
        void *wm = window_manager();
        int i;
        for (i = 0; i < POP_MAX; ++i) {
            void *top = window_manager_get_top_window(wm);
            const char *name = top ? *(const char **)((char *)top + WIDGET_NAME) : (const char *)0;
            if (!name) break;
            if (!strcmp(name, "playing_page")) {
                window_close(top);
                break;
            }
            if (!strcmp(name, "home_page")) break;
            navigator_back();
        }
    }
    pod_start_player(queue, idx, cls); /* playing_page_init -> start_player copies the queue */
}

/* Song `at` (-1: a random one) of the list and the list as the queue, in Now Playing: the stock Songs row's handler (@0x5275a4: loadSongList of the shown list, then
 * Now Playing at the row), as Shuffle Songs does it (patch/shuffle.c). The caller has put the browsing record back (loadSongList runs the class query again and keeps
 * classinfo for the memory playback). */
int so_play_with(int cls, void *list, int at, int how, so_open_fn open, int rev, so_reorder_fn reorder) {
    void *pick, *queue, *first;
    unsigned n, idx = 0, count = deque_size(list);
    int found;
    if (at < 0 && count) at = (int)pod_rand(count);
    if (at < 0 || at >= (int)count) return -1;
    pick = deque_at(list, (unsigned)at);
    queue = _create_deque("stSongInfo");
    if (!queue) return -1;
    deque_init(queue);
    found = loadSongList(queue, cc_str(pick, REC_NAME), I(pick, REC_CUE_START), cls);
    n = deque_size(queue);
    if (rev &&
        n > 1) { /* the page shows the stock order the other way round (the Songs page's Z-A): the queue too, so the row tapped is where the page shows it */
        unsigned i;
        char tmp[REC_SIZE];
        for (i = 0; i < n / 2; ++i) {
            void *a = deque_at(queue, i), *b = deque_at(queue, n - 1 - i);
            memcpy(tmp, a, REC_SIZE), memcpy(a, b, REC_SIZE), memcpy(b, tmp, REC_SIZE);
        }
        if (found >= 0 && (unsigned)found < n) found = (int)(n - 1 - (unsigned)found);
    }
    if (reorder &&
        n > 1) { /* the page shows another order (the Folders page's sorts): the queue follows it, and the row's own place in it comes back (-1: left as it was) */
        int f = reorder(queue, pick);
        if (f >= 0) found = f;
    }
    if (n) { /* loadSongList finds a song by file name and CUE start: a duplicate name (01.flac) would always start at the first, so the row's own index wins (the same song: its path and its CUE start, since the tracks of a CUE image share the path) */
        void *q = deque_at(queue, (unsigned)at < n ? (unsigned)at : 0);
        if ((unsigned)at < n && !strcmp(cc_str(q, REC_PATH), cc_str(pick, REC_PATH)) &&
            I(q, REC_CUE_START) == I(pick, REC_CUE_START))
            idx = (unsigned)at;
        else if (found >= 0 && (unsigned)found < n)
            idx = (unsigned)found;
    }
    if (how == SO_SHUFFLE &&
        n) { /* a shuffle leaves the podcast episodes out (patch/pcmodel.c; the queue itself when there are none) */
        int at_i = (int)idx;
        queue = pc_strip(queue, &at_i);
        idx = (unsigned)at_i;
        n = queue ? deque_size(queue) : 0;
        if (!queue) {
            pod_toast(TR("Update Local Music first"));
            return -1;
        }
    }
    first = n ? deque_at(queue, idx) : (void *)0;
    if (!first || access(cc_str(first, REC_PATH), F_OK)) {
        deque_destroy(queue);
        if (n)
            pod_toast(so_missing());
        else
            pod_toast(TR("Update Local Music first"));
        return -1;
    }
    if (how == SO_IN_ORDER)
        pod_set_in_order_for_queue(); /* Play: the list in order, even after a Shuffle; a row tap keeps the mode, as stock */
    else if (how == SO_SHUFFLE)
        pod_set_mode_for_queue(MODE_SHUFFLE);
    *(int *)G_CLASS_TYPE = cls; /* as allmusic_page_init leaves it */
    open(queue, (int)idx, cls);
    deque_destroy(queue);
    return 0;
}

int so_play_dir(int cls, void *list, int at, int how, so_open_fn open, int rev) {
    return so_play_with(cls, list, at, how, open, rev, (so_reorder_fn)0);
}
int so_play(int cls, void *list, int at, int how, so_open_fn open) {
    return so_play_with(cls, list, at, how, open, 0, (so_reorder_fn)0);
}

/* A page's play through its source (patch/libsrc.h): NULL or lib_stock is so_play exactly (cls is the stock class of the list), any other source builds and starts its own queue. */
int so_play_src(const lib_src_t *src, int cls, void *list, int at, int how, so_open_fn open) {
    if (!src || src == &lib_stock) return so_play(cls, list, at, how, open);
    return src->play(src, list, at, how, open, cls);
}
