/* M1+ Music library list hand-over: a stock list is read without a second copy of it (docs/modules/libload.md).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * Stock's loadLocalClassList (0x4ee504; every local list: Songs, Albums, Artists, Most Played, a playlist's songs ...) runs the class's query into
 * *tools_pdeq_directory and ends in one tail: deque_clear(*dst); deque_assign(*dst, *tmp); deque_clear(*tmp). deque_assign copies every record and its strings
 * (the stSongInfo copy callback). The old list coexists with the query's rows until the tail clears it; then the query's rows coexist with their copy.
 * On a large library either peak can exhaust memory.
 *
 * Two edits (tools/pod_pins.py LCL_PINS, docs/modules/payload.md hook 29):
 *   ll_load    replaces the prologue (`j ll_load`): for a local class whose destination is the show list (ll_local: the jump tables pinned as LCL_TABLES) the old
 *              list is cleared before the query, then stock's function runs through the trampoline. Stock clears it in the tail anyway; no query reads it (their
 *              arguments are the browsing record's), so only the moment of the free changes.
 *   ll_assign  replaces the tail's `jalr deque_assign` (`jal ll_assign`): the two deque_t structs are exchanged (lib_deque_swap), so the destination owns the
 *              query's rows and the row deque is the empty one stock's tail clears next. No record is copied.
 * lib_deque_swap repeats libcstl's deque_swap (0x3ac1c, pinned by tools/pod.py CSTL_SWAP): 0x14c bytes each way, then the two iterators' container pointers
 * (+0x124, +0x140) point at their own deque again. libcstl's allocator is malloc / free with no state of its own (_alloc_init is empty), so the blocks follow the
 * struct. It refuses (returns 0, nothing changed) unless both deques' container pointers point at themselves, which every initialised deque's do: a different
 * layout is never exchanged. The function itself is not called: it compares the two lists first (deque_equal) and demo does not import it.
 *
 * Stock's own code runs unchanged with the kill switch /mnt/mmc/m1plus-off (one access a call) and whenever the exchange refuses. Reachable at boot
 * (tools/reach.py: onlineDownloadThd, home_page_init): bounded work, no thread, timer, file or allocation of our own.
 */
#include "offsets.inc"
#include "stock.h"
#include "home.h"
#include "entries.h"

extern int stock_loadclass_trampoline(int cls);

#define LL_WORDS (CSTL_DEQUE_SIZE / 4)
#define LL_SELF(d, off) (*(void **)((char *)(d) + (off)))

static int ll_deque(const void *d) { return LL_SELF(d, CSTL_DEQUE_SELF_A) == d && LL_SELF(d, CSTL_DEQUE_SELF_B) == d; }

/* The contents of two initialised deques of the same element type exchanged in place (both pointers stay what they were). 1 when done, 0 when it was refused. */
__attribute__((noinline)) int lib_deque_swap(void *a, void *b) {
    unsigned *x = (unsigned *)a, *y = (unsigned *)b, i;
    if (!a || !b || a == b || !ll_deque(a) || !ll_deque(b)) return 0;
    for (i = 0; i < LL_WORDS; ++i) {
        unsigned t = x[i];
        x[i] = y[i], y[i] = t;
    }
    LL_SELF(a, CSTL_DEQUE_SELF_A) = LL_SELF(a, CSTL_DEQUE_SELF_B) = a;
    LL_SELF(b, CSTL_DEQUE_SELF_A) = LL_SELF(b, CSTL_DEQUE_SELF_B) = b;
    return 1;
}

/* A new deque that owns the records of the stock list `list`, which is left empty (no record is copied); when the exchange is refused, a copy as cc_copy_list
 * makes it (the list keeps its records). NULL without memory for the deque. For a list the caller has just read and nothing shows: a page that shows the stock
 * list finds it changed (grid_list_same) and reads it again, as after any other query. */
void *lib_take_list(void *list) {
    void *d = _create_deque("stSongInfo");
    if (!d) return d;
    deque_init(d);
    if (!lib_deque_swap(d, list)) deque_assign(d, list);
    return d;
}

/* The local classes whose rows go to *pdeq_showlist (tools/pod_pins.py LCL_LOCAL, checked against this by test/pod/libload.py). */
static int ll_local(int cls) {
    return (cls >= 0xf001 && cls <= 0xf00a) || cls == 0xff01 || cls == 0xff02 || cls == 0xff09 ||
           (cls >= 0xff10 && cls <= 0xff14);
}

/* The prologue hook: loadLocalClassList(cls), the list it replaces freed first. */
int ll_load(int cls) {
    if (ll_local(cls) && access(KILL_SD, F_OK) != 0) {
        void *old = *(void **)PDEQ_SHOWLIST;
        if (old && ll_deque(old)) deque_clear(old);
    }
    return stock_loadclass_trampoline(cls);
}

/* The call-site hook, in place of deque_assign(dst, rows): dst (cleared by stock just before) takes the rows; stock clears `rows` next. */
void ll_assign(void *dst, void *rows) {
    if (access(KILL_SD, F_OK) == 0 || !lib_deque_swap(dst, rows)) deque_assign(dst, rows);
}
