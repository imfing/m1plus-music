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

extern void pod_toast(const char *text); /* patch/shuffle.c: the stock message box */
extern void pod_set_in_order(void); /* patch/shuffle.c: Shuffle and Repeat one become List play */
extern void pod_set_mode_for_queue(
    int mode); /* patch/shuffle.c: the play mode right before a queue load (the old queue is not reordered) */
extern void pod_set_in_order_for_queue(void); /* the same for Play */
extern unsigned pod_rand(unsigned n); /* patch/shuffle.c: 0 .. n - 1 */

#define I(w, off) (*(int *)((char *)(w) + (off)))

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

/* Open Now Playing on the queue exactly as a track row's tap does (the stock album row handler @0x52569c, its tail
 * @0x5258c8..0x525970): when songerinfoflag is set and a playing_page is in the stack, the windows above it are popped
 * with navigator_back and the old playing_page is closed (the stock loop, which also stops at home_page); then
 * navigator_to_with_context("playing_page", {queue, index, class, 2}), whose init starts the player. Stock's loop
 * trusts every navigator_back to change the top window at once (true for these pages: none has a close animation);
 * a bound of POP_MAX turns that trust into a limit, after which the page is opened over what is left. */
void pod_open_player(void *queue, int idx,
                     int cls) { /* (the album page's so_open_fn; also the Daily Mix card's play disc) */
    struct {
        void *dq;
        int idx, cls, mode;
    } context;
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
    context.dq = queue, context.idx = idx, context.cls = cls, context.mode = PLAY_MODE;
    navigator_to_with_context("playing_page", &context); /* playing_page_init -> start_player copies the queue */
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
        pod_toast(TR(n ? "Storage unavailable" : "Update Local Music first"));
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
