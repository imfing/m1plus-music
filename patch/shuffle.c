/* M1+ Music Shuffle: Shuffle Songs, Shuffle Albums and Shuffle Folders from the M1+ Music menu.
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * After q2-pod's Shuffle page (patch/navigation.c shuffle_play / shuffle_songs / shuffle_groups,
 * patch/playback.c rand_below / shuffle / make_order). The xorshift32 generator and its seeding,
 * the Fisher-Yates shuffle of the groups, the group orders (an album's disc, then track, then
 * path; a folder's path) and the user-facing messages follow q2-pod. q2-pod keeps the groups
 * together at play time with hooks in the stock player (mclNextSong, mclLoadPlayList, ...); here
 * Shuffle Albums/Folders build the whole queue up front, in its play order, and hand it to the
 * stock player in a sequential mode (docs/architecture.md).
 *
 * Shuffle itself (Apple Music's): stock's own Shuffle (mode 2, which draws from a pool and leaves
 * the queue in library order) is never used. The payload keeps its own flag (/mnt/data/m1plus/
 * playback-shuffle); turning it on shuffles the queue after the playing song in place, turning it
 * off puts the queue back in its original order, and a queue loaded while it is on arrives shuffled,
 * its first song (the tapped or resumed one) first. Stock plays that queue in order in mode 0 or 3.
 * Two pinned hooks make it hold for every way stock changes the mode or loads a queue: mclSetPlayMode
 * (sh_set_mode: a request for 2 means "flag on, stock mode 0", any other request flag off, except for
 * the Queue page's Repeat and the first call at boot) and mclLoadPlayList (sh_load_playlist); the
 * display sites of stock that read the mode through mclGetPlayMode call sh_display_mode (2 while the
 * flag is on) instead (tools/pod.py MODE_SITES, docs/modules/shuffle.md).
 *
 * Everything else here runs from a tap on a row of the M1+ Music menu (patch/m1plus.c on_row) or a
 * button, once, on the UI thread, and returns: no timer, no thread, no state kept between taps
 * except the random generator's word, the flag and the original order of a shuffled queue.
 *
 * The stock path is the Songs page's: loadLocalClassList(0xf001) (getAllMusic into
 * *pdeq_showlist), loadSongList(queue, name, cue, 0xf001) (the queue, as the page's row handler
 * builds it @0x5258a0, and the memory-playback record), navigator_to_with_context("playing_page",
 * {queue, index, 0xf001, 2}) (start_player: mclLoadPlayList + mclStartPlayer), and the play mode
 * as the Play settings page sets it (@0x49fc78).
 */
#include "offsets.inc"
#include "stock.h"
#include "i18n.h"
#include "podcasts.h"
#include "home.h"

#define P(r, off) (*(char **)((char *)(r) + (off)))
#define I(r, off) (*(int *)((char *)(r) + (off)))

enum { SHUFFLE_SONGS = 0, SHUFFLE_ALBUMS = 1, SHUFFLE_FOLDERS = 2 }; /* tools/pod_pages.py */

static unsigned rng __attribute__((section(".scratch")));
static int by_folder __attribute__((section(".scratch"))); /* the group key of the sort in progress */

/* xorshift32, seeded once from stock's generator and the tick clock (q2-pod playback.c
 * rand_below): stock's toolsRandnum reseeds from time() on every call, so two taps in the same
 * second would repeat. */
static unsigned rand_below(unsigned n) {
    if (!rng) rng = ((unsigned)toolsRandnum(0x7fffffff) ^ time_now_ms() * 2654435761u) | 1;
    rng ^= rng << 13;
    rng ^= rng >> 17;
    rng ^= rng << 5;
    return rng % n;
}

static const char *str(void *r, int field) {
    const char *s = r ? P(r, field) : (const char *)0;
    return s ? s : "";
}

/* The stock one-line message box, as the Songs page shows "file not found" (@0x5259dc). */
static void toast(const char *text) {
    struct {
        int kind, ms;
        char text[MSGINFO_TEXT], text2[MSGINFO_TEXT];
    } info;
    unsigned i;
    memset(&info, 0, sizeof info);
    info.kind = MSGINFO_KIND;
    info.ms = MSGINFO_MS;
    for (i = 0; text[i] && i < sizeof info.text - 1; ++i) info.text[i] = text[i];
    navigator_to_with_context("dialog/msginfo_dialog", &info);
}

/* ---------------------------------------------------------------------------
 * Apple-style Shuffle: the flag, the queue's reorder and the two hooks.
 */
extern int stock_setmode_trampoline(int mode); /* stock mclSetPlayMode past the hook's prologue (patch/pod_asm) */
extern int stock_loadplaylist_trampoline(void *queue, int pos, int cls); /* the same for mclLoadPlayList */

static struct {
    unsigned char loaded; /* the flag file has been read */
    unsigned char on; /* the flag */
    unsigned char keep; /* pod_set_repeat is changing the stock mode: the flag stays */
    unsigned char
        fresh; /* set_mode / set_in_order for a queue about to load: the flag changes without reordering the current queue */
    unsigned char booted; /* mclSetPlayMode has run once this session (stock's own boot restore is the first call) */
    unsigned
        *orig; /* orig[slot] = the position the song at that slot had before the shuffle; NULL when there is none */
    unsigned n; /* the queue's size when orig was made: a different size means the queue changed and orig is stale */
} sh __attribute__((section(".scratch")));

static void *play_queue(void) { return *(void **)PLAY_QUEUE; }

static int flag(void) {
    if (!sh.loaded) {
        sh.on = !home_off() && set_read(SHUFFLE_FILE, '0') == '1';
        sh.loaded = 1;
    }
    return sh.on;
}

static void flag_save(int on) {
    sh.on = (unsigned char)on, sh.loaded = 1;
    home_write_atomic(SHUFFLE_FILE, SHUFFLE_TMP,
                      on ? "1\n" : "0\n"); /* a failed save leaves the flag for this session */
}

static void drop_order(void) { /* with the payload lock held */
    free(sh.orig);
    sh.orig = (unsigned *)0, sh.n = 0;
}

/* The payload lock (docs/modules/shuffle.md, Locking). One stock pthread mutex (libc's, imported by demo like the cover code's) over a zero-filled word
 * block, which is PTHREAD_MUTEX_INITIALIZER. Not recursive: it is only taken in the functions below, which call no hook of ours (stock mclSetPlayPos,
 * the file write and, in sh_load_playlist, stock's mclLoadPlayList, which reaches no hook, are the only calls made under it), and never across the stock
 * trampoline of mclSetPlayMode. */
static unsigned sh_mutex[8] __attribute__((section(".scratch"), aligned(8)));
static void sh_enter(void) { pthread_mutex_lock(sh_mutex); }
static void sh_leave(void) { pthread_mutex_unlock(sh_mutex); }

/* Flag only, no reorder: for a request that is followed by a queue load (the loaded queue is shuffled by sh_load_playlist when the flag is on). The order
 * saved for the queue about to be replaced is dropped. */
static void flag_only(int on) {
    sh_enter();
    drop_order();
    flag_save(on);
    sh_leave();
}

/* The mode the player is shown to be in (the call sites of tools/pod.py MODE_SITES): 2 while the flag is on. */
int sh_display_mode(void) { return flag() ? MODE_SHUFFLE : mclGetPlayMode(); }
int pod_play_mode(void) { return sh_display_mode(); }
int pod_shuffle_on(void) { return flag(); }

/* A random permutation of p[0..m): Fisher-Yates with the payload's generator (the groups' ranks use the same loop). */
static void permute(unsigned *p, unsigned m) {
    unsigned i, j, t;
    for (i = m; i > 1; --i) {
        j = rand_below(i);
        t = p[i - 1], p[i - 1] = p[j], p[j] = t;
    }
}

/* Slots lo .. lo + m of the queue q become new[lo + i] = old[p[i]], p[i] being a slot number (lo .. lo + m), the same meaning as sh.orig: p = sh.orig + lo.
 * Cycle-following with one record of temporary storage, so every string stays owned by one slot, as group_order
 * does it. 0 when the done-bitmap cannot be allocated (nothing is touched then). */
static int apply_perm(void *q, unsigned lo, unsigned m, const unsigned *p) {
    unsigned char *done = calloc((m + 7) / 8 + 1, 1);
    char tmp[REC_SIZE];
    unsigned i, j, k;
    if (!done) return 0;
    for (i = 0; i < m; ++i) {
        if (done[i >> 3] >> (i & 7) & 1) continue;
        done[i >> 3] |= (unsigned char)(1 << (i & 7));
        if (p[i] == lo + i) continue;
        memcpy(tmp, deque_at(q, lo + i), REC_SIZE);
        for (j = i;; j = k) {
            k = p[j] - lo;
            done[j >> 3] |= (unsigned char)(1 << (j & 7));
            if (k == i) break;
            memcpy(deque_at(q, lo + j), deque_at(q, lo + k), REC_SIZE);
        }
        memcpy(deque_at(q, lo + j), tmp, REC_SIZE);
    }
    free(done);
    return 1;
}

/* A queue just loaded (n songs): the song at pos first, the rest shuffled. The permutation is the original order. 0 on a failed allocation. */
static int shuffle_load(void *q, unsigned n, unsigned pos) {
    unsigned *p = calloc(n, sizeof *p), i;
    if (!p) return 0;
    for (i = 0; i < n; ++i) p[i] = i;
    p[0] = pos, p[pos] = 0;
    permute(p + 1, n - 1);
    if (!apply_perm(q, 0, n, p)) {
        free(p);
        return 0;
    }
    drop_order();
    sh.orig = p, sh.n = n;
    mclSetPlayPos(0);
    return 1;
}

/* The playing queue (n songs): the songs after the playing one shuffled in place, orig keeping where each came from. 0 on a failed allocation. */
static int shuffle_tail(void *q, unsigned n, int pos) {
    unsigned lo = pos >= 0 && (unsigned)pos < n ? (unsigned)pos + 1 : 0, m = n - lo, i;
    unsigned *orig;
    if (m < 2) return 1;
    orig = calloc(
        n,
        sizeof *orig); /* the one allocation (and apply_perm's bitmap): orig is the identity, its tail the permutation */
    if (!orig) return 0;
    for (i = 0; i < n; ++i) orig[i] = i;
    permute(orig + lo, m);
    if (!apply_perm(q, lo, m, orig + lo)) {
        free(orig);
        return 0;
    }
    drop_order();
    sh.orig = orig, sh.n = n;
    return 1;
}

/* The queue back in its original order; the play position follows the playing song. A stale or missing order leaves the queue as it is. Allocates nothing,
 * so it cannot fail: the record at slot j goes to slot orig[j] (orig[j] is where it came from), following each cycle of orig with the record in hand; the
 * slots done are marked with the high bit of their orig entry (n <= SHUFFLE_MAX; the array is freed right after, so the marks need no clearing).
 * With the payload lock held. */
#define SEEN 0x80000000u
static void restore_order(void *q, unsigned n, int pos) {
    unsigned *o = sh.orig, i, j, d;
    char hold[REC_SIZE], tmp[REC_SIZE];
    if (o && sh.n == n) {
        for (i = 0; i < n && o[i] < n; ++i) {
        }
        if (i == n) { /* every entry is a valid slot */
            unsigned want = pos >= 0 && (unsigned)pos < n ? o[pos] : n;
            for (i = 0; i < n; ++i) {
                if (o[i] & SEEN || o[i] == i) continue;
                memcpy(hold, deque_at(q, i), REC_SIZE);
                for (j = i;;) {
                    d = o[j] & ~SEEN;
                    o[j] |= SEEN;
                    if (d == i) { /* the cycle closes: slot i takes the record that came last */
                        memcpy(deque_at(q, i), hold, REC_SIZE);
                        break;
                    }
                    if (o[d] & SEEN) break; /* not a permutation (cannot happen): stop, never loop */
                    memcpy(tmp, deque_at(q, d), REC_SIZE);
                    memcpy(deque_at(q, d), hold, REC_SIZE);
                    memcpy(hold, tmp, REC_SIZE);
                    j = d;
                }
            }
            if (want < n) mclSetPlayPos((int)want);
        }
    }
    drop_order();
}

/* The one gapless cancel (the shuffle reorders and the insert below). A change of which song comes next makes a gapless preload of the old next one stale. It is
 * closed with stock's Gapless setter: mclSetGaplessMode(0) @0x5d28ac stores the setting byte 0xa0ab89, and with the preload state 0xa0abd0 at 1 sends
 * {mcl-closegapless} and stores -1 in the state; mclSetGaplessMode(old) puts the byte back. The other way to reach the same close, mclSetPlayMode(1) twice
 * (@0x5d27b8..0x5d2804), stores the mode word 0xa0abe0 = 1 (Repeat one) for a few instructions, and a track that ends in that window repeats once (mclNextSong
 * reads the mode raw). In the setter's window the byte is 0 and the state is 1 or -1, and every reader of the byte goes the way the closed state goes anyway:
 * mclNextSong @0x5d583c (byte 0: the queue path), mclAutoChange @0x5d632c (byte 0: no preload), the set-gapless send @0x5d0dd0 (only on the tick's preload,
 * the same thread as the UI). No stock mode word is touched and the setter reaches only `send`, no hooked address, so it is safe under the payload lock.
 * After the cancel stock does not preload again in the same song (the tick calls the preload only while the state is 0): the join into the new next song is
 * not gapless, accepted. */
static void cancel_preload(void) {
    unsigned char old = *(unsigned char *)MCL_GAPLESS;
    if (*(int *)MCL_PRELOAD != 1) return;
    mclSetGaplessMode(0);
    mclSetGaplessMode(old);
}

/* The flag on or off, with the reorder: 1 done, 0 more songs than SHUFFLE_MAX (the flag stays off), -1 out of memory (the same). Off always succeeds. */
static int flag_set(int on) {
    void *q;
    unsigned n;
    int r = 1;
    sh_enter(); /* the queue's size, the reorder and who owns sh.orig change together; one exit */
    q = play_queue();
    n = q ? deque_size(q) : 0;
    if (on) {
        if (n > SHUFFLE_MAX)
            r = 0;
        else if (n > 1 && !shuffle_tail(q, n, mclGetPlayPos()))
            r = -1;
    } else if (q && sh.orig)
        restore_order(q, n, mclGetPlayPos());
    else
        drop_order();
    if (r > 0) flag_save(on);
    sh_leave();
    if (r > 0 && q && n > 1) cancel_preload();
    return r;
}

/* ---------------------------------------------------------------------------
 * Play Next / Play After: rows inserted into the playing queue in place (docs/modules/queue.md "Up Next"), through here so that Shuffle's saved order stays valid.
 */
static void row_swap(void *q, unsigned i, unsigned j) {
    char tmp[REC_SIZE];
    void *a = deque_at(q, i), *b = deque_at(q, j);
    memcpy(tmp, a, REC_SIZE);
    memcpy(a, b, REC_SIZE);
    memcpy(b, tmp, REC_SIZE);
}

/* Stock's DLNA renderer (UPnP) service runs (dlna_service_running 0x507bec: dmr_serverflag == 1). Its callbacks on the UPnP threads (dmrActionPLGetPlayInfo, dmrActionPLReadTrack,
 * dmrActionGetPositionInfo) read the queue without a lock, so Clear and the queue insert (Play Next / Play After: it grows the deque and moves rows) are off while it runs
 * (docs/modules/queue.md "Locking, and what it does not cover"). */
static int dlna_running(void) { return *(volatile int *)DMR_SERVERFLAG == 1; }

static void rows_reverse(void *q, unsigned lo, unsigned hi) { /* [lo, hi] */
    while (lo < hi) row_swap(q, lo++, hi--);
}

/* The n rows at [size, size + n) move to [at, at + n), the rows from at to size - 1 after them: the three reversals of a rotation. Every string stays owned by one slot. */
static void rows_rotate(void *q, unsigned at, unsigned size, unsigned n) {
    if (at >= size || !n) return;
    rows_reverse(q, at, size + n - 1);
    rows_reverse(q, at, at + n - 1);
    rows_reverse(q, at + n, size + n - 1);
}

/* Insert the n rows of `rows` (a deque of stSongInfo that stays the caller's; they are copied) into the playing queue: right after the playing song (after == 0, the
 * rows of one call keep their order, an earlier Play Next ends up behind them) or at the end (after != 0). Under the payload lock, so a queue load or clear on
 * DLNA's thread excludes it, and nothing hooked is called inside (_deque_push_back's copy callback is stock's stSongInfo copy, as in mclLoadPlayList's walk).
 * When Shuffle keeps an order (sh.orig) it grows with the queue and stays a permutation of 0..size-1: the new slots take the original positions right after the
 * playing song's own (Play Next) or at the end (Play After), in the rows' order, and every original position at or above that moves up by n, so Shuffle off puts
 * the original order back with the added songs right after the playing song. An order whose size is not the queue's is stale and dropped. An open gapless
 * preload is cancelled (cancel_preload) when the next song changes (at == pos + 1), also under the lock.
 * POD_INSERT_OK, or nothing changed: POD_INSERT_IDLE (no rows, no queue or no playing position: the caller starts the rows as a queue), POD_INSERT_DLNA (the DLNA renderer service runs), POD_INSERT_FULL (more than
 * SHUFFLE_MAX songs), POD_INSERT_MEMORY (the new order could not be allocated). */
int pod_queue_insert(void *rows, int after) {
    void *q;
    unsigned n = rows ? deque_size(rows) : 0, size, at, base = 0, s, v, i;
    unsigned *no = (unsigned *)0, *o;
    int pos, cls, r = POD_INSERT_OK;
    sh_enter();
    q = play_queue();
    size = q ? deque_size(q) : 0;
    pos = mclGetPlayPos();
    if (!n || !size || pos < 0 || (unsigned)pos >= size) {
        r = POD_INSERT_IDLE;
    } else if (
        dlna_running()) { /* the service starts on the UI thread (this one), so it cannot start before the insert ends */
        r = POD_INSERT_DLNA;
    } else if (size + n > SHUFFLE_MAX) {
        r = POD_INSERT_FULL;
    } else {
        at = after ? size : (unsigned)pos + 1;
        o = sh.orig;
        if (o && sh.n == size) { /* the new order first: a failed allocation refuses the insert with nothing changed */
            no = calloc(size + n, sizeof *no);
            if (!no) r = POD_INSERT_MEMORY;
        }
        if (r == POD_INSERT_OK) {
            if (no) {
                base = after ? size : o[pos] + 1;
                for (s = 0; s < size; ++s) {
                    v = o[s];
                    no[s < at ? s : s + n] = v >= base ? v + n : v;
                }
                for (i = 0; i < n; ++i) no[at + i] = base + i;
            }
            cls = I(deque_at(q, (unsigned)pos), REC_CLASS);
            for (i = 0; i < n; ++i) {
                _deque_push_back(q, deque_at(rows, i));
                I(deque_at(q, size + i), REC_CLASS) = cls; /* what loadSongList stamps in every row of a queue */
            }
            rows_rotate(q, at, size, n);
            drop_order(); /* the old order, or a stale one */
            if (no) sh.orig = no, sh.n = size + n;
            if (at == (unsigned)pos + 1) cancel_preload();
        }
    }
    sh_leave();
    return r;
}

/* The hook on mclSetPlayMode (tools/pod.py SETMODE): a request for 2 is "shuffle on, stock mode 0" (a flag already on is left alone), any other mode is
 * "shuffle off" and that stock mode, except for the Queue page's Repeat (keep) and stock's boot restore of [PLAYSET] PLAYMODE, the session's first call,
 * which leave the flag as its file has it. Stock's function does the rest (and closes a gapless preload for mode 1). The kill switch gives stock's own. */
int sh_set_mode(int mode) {
    int first = !sh.booted, was, want, r;
    sh.booted = 1;
    if (home_off()) {
        sh_enter();
        sh.loaded = 1, sh.on = 0;
        drop_order();
        sh_leave();
        return stock_setmode_trampoline(mode);
    }
    was = flag();
    if (mode == MODE_SHUFFLE && was && !first) return 1;
    want = mode == MODE_SHUFFLE ? 1 : (sh.keep || first) ? was : 0;
    r = stock_setmode_trampoline(mode == MODE_SHUFFLE ? MODE_ORDER : mode);
    if (want != was) { /* a failed shuffle leaves the flag off: the request becomes List play */
        if (sh.fresh)
            flag_only(
                want); /* a queue load follows (set_mode): the replacement is shuffled by sh_load_playlist, the old one is not touched */
        else
            flag_set(want);
    }
    return r;
}

/* The hook on mclLoadPlayList (tools/pod.py LOADPL): stock loads the queue, then with the flag on it is shuffled, the song at pos first (and playing at slot 0).
 * Over SHUFFLE_MAX songs or out of memory the flag goes off and the queue stays as loaded (silently: this also runs for the boot resume).
 * The payload lock is held across stock's load: it clears and refills the very deque another thread (DLNA) may be reordering under the lock, and stock's clear
 * frees the deque's blocks. Stock's function cannot re-enter a payload hook (docs/modules/shuffle.md, Locking), so the lock needs no recursion. */
int sh_load_playlist(void *queue, int pos, int cls) {
    int r;
    void *q;
    unsigned n;
    sh_enter();
    r = stock_loadplaylist_trampoline(queue, pos, cls);
    drop_order();
    if (!home_off() && flag()) {
        q = play_queue();
        n = q ? deque_size(q) : 0;
        if (n > 1 && (n > SHUFFLE_MAX || !shuffle_load(q, n, pos >= 0 && (unsigned)pos < n ? (unsigned)pos : 0)))
            flag_save(0);
    }
    sh_leave();
    return r;
}

/* The call site in dmr_serverstart (tools/pod.py CLEAR_SITE, `jalr deque_clear` @0x5089e4, its delay slot loads a0 = the play queue): stock clears the playing
 * queue directly, not through mclLoadPlayList, and the clear frees the deque's blocks. Same lock as the loader, so a reorder on another thread is never copying
 * records of freed blocks; the saved order describes a queue that is gone, so it is dropped. deque_clear's element free callback is the stSongInfo destructor
 * @0x5dabfc (free, memset), which reaches no hook of ours, so the lock is never taken twice. The kill switch keeps the lock too: switched on mid-reorder, the
 * clear still waits for it. */
void sh_clear_queue(void *deque) {
    sh_enter();
    deque_clear(deque);
    drop_order();
    sh_leave();
}

/* The mode changed: tell the remotes and the config as the stock mode button does after its change (@0x53b648..0x53b6a0). */
static void announce(int config) {
    notifyPlayMode();
    dmrSendPlayMode(sh_display_mode());
    write_int_config(config, "PLAYSET", "PLAYMODE");
}

/* The stock play mode, changed the way the Play settings page changes it (@0x49fc78): the player,
 * the SyncLink and DLNA remotes, and [PLAYSET] PLAYMODE in /mnt/data/config.ini. Nothing is
 * written when the mode is already the one shown. Asking for Shuffle also means List play under it. */
static void set_mode_now(int mode) {
    if (mode == MODE_SHUFFLE && flag() && mclGetPlayMode() != MODE_ORDER) {
        sh.keep = 1;
        mclSetPlayMode(MODE_ORDER);
        sh.keep = 0;
        announce(MODE_SHUFFLE);
        return;
    }
    if (sh_display_mode() == mode) return;
    mclSetPlayMode(mode);
    announce(mode);
}

/* fresh: a queue load follows, so the flag changes without reordering (or restoring) the queue that is about to be replaced; sh_load_playlist shuffles the
 * new one. Not fresh: the current queue is reordered now. */
static void set_mode(int mode, int fresh) {
    sh.fresh = (unsigned char)fresh;
    set_mode_now(mode);
    sh.fresh = 0;
}

/* Shuffle on or off from a button of ours (the Queue page): the repeat mode stays. 1 done; 0 refused with the stock message box. */
int pod_set_shuffle(int on) {
    int r;
    if (flag() == on) return 1;
    if (home_off()) return 0;
    r = flag_set(on);
    if (r <= 0) {
        toast(TR(r ? "Not enough memory" : "Too many songs to shuffle"));
        return 0;
    }
    announce(mclGetPlayMode());
    return 1;
}

/* Repeat from the Queue page: off (0), all (3) or one (1), the shuffle flag kept. */
void pod_set_repeat(int mode) {
    if (mclGetPlayMode() == mode) return;
    sh.keep = 1;
    mclSetPlayMode(mode);
    sh.keep = 0;
    announce(mode);
}

/* A mode that plays a queue in order: Shuffle goes off, List play or Repeat all are kept, Repeat one becomes List play. */
static void set_in_order(int fresh) {
    int mode = mclGetPlayMode(), was = flag();
    if (was) {
        if (fresh)
            flag_only(0);
        else
            flag_set(0);
    }
    if (mode == MODE_SHUFFLE || mode == MODE_REPEAT_ONE)
        set_mode(MODE_ORDER, fresh);
    else if (was)
        announce(mode);
}

/* ---------------------------------------------------------------------------
 * Album and folder order. One index entry per queued song; a heapsort (no libc callback into the
 * payload) groups them, the groups get a random rank, a second sort puts them in play order, and
 * the queue's own records are then permuted in place, so no second copy of the library is made.
 */
typedef struct {
    void *rec; /* the song's record inside the queue */
    unsigned group; /* pass 2: the group's random rank; while permuting, ~0 once placed */
    unsigned idx; /* its position in the queue as loadSongList built it */
    unsigned dir; /* Shuffle Folders: the length of its path's folder (dir_len), computed once */
} entry;
typedef int (*cmp_fn)(const entry *, const entry *);

static void sift(entry *v, unsigned i, unsigned n, cmp_fn cmp) {
    for (;;) {
        unsigned c = 2 * i + 1;
        entry t;
        if (c >= n) return;
        if (c + 1 < n && cmp(&v[c], &v[c + 1]) < 0) ++c;
        if (cmp(&v[i], &v[c]) >= 0) return;
        t = v[i], v[i] = v[c], v[c] = t;
        i = c;
    }
}

static void sort(entry *v, unsigned n, cmp_fn cmp) {
    unsigned i;
    entry t;
    for (i = n / 2; i-- > 0;) sift(v, i, n, cmp);
    for (i = n; i-- > 1;) {
        t = v[0], v[0] = v[i], v[i] = t;
        sift(v, 0, i, cmp);
    }
}

/* SQLite's NOCASE, which the stock Albums list groups by (getAllAlbum: "group by album COLLATE
 * NOCASE"): ASCII letters fold, nothing else does. */
static int fold(int c) { return c >= 'A' && c <= 'Z' ? c + 32 : c; }
static int nocase(const char *a, const char *b) {
    while (*a && fold((unsigned char)*a) == fold((unsigned char)*b)) ++a, ++b;
    return fold((unsigned char)*a) - fold((unsigned char)*b);
}

/* The folder of a path: everything before its last '/'. */
static unsigned dir_len(const char *p) {
    unsigned i, n = 0;
    for (i = 0; p[i]; ++i)
        if (p[i] == '/') n = i;
    return n;
}
static int dir_cmp(const char *a, unsigned la, const char *b, unsigned lb) {
    unsigned i;
    for (i = 0; i < la && i < lb; ++i)
        if (a[i] != b[i]) return (unsigned char)a[i] - (unsigned char)b[i];
    return (int)la - (int)lb;
}

static int key_cmp(const entry *a, const entry *b) {
    return by_folder ? dir_cmp(str(a->rec, REC_PATH), a->dir, str(b->rec, REC_PATH), b->dir)
                     : nocase(str(a->rec, REC_ALBUM), str(b->rec, REC_ALBUM));
}

static int by_index(const entry *a, const entry *b) { return a->idx < b->idx ? -1 : a->idx != b->idx; }

/* Pass 1: groups together, each in queue order. */
static int group_cmp(const entry *a, const entry *b) {
    int d = key_cmp(a, b);
    return d ? d : by_index(a, b);
}

/* Pass 2: the groups in their random order; an album as the stock album page orders it (disc,
 * then track: getMusicByAlbum's sort @0x4e9020), then by path, so an untagged album keeps its
 * file-name order (q2-pod album_before); a folder by path; a CUE image's tracks by start. */
static int play_cmp(const entry *a, const entry *b) {
    void *ra = a->rec, *rb = b->rec;
    int d;
    if (a->group != b->group) return a->group < b->group ? -1 : 1;
    if (!by_folder) {
        d = I(ra, REC_DISC) - I(rb, REC_DISC);
        if (!d) d = I(ra, REC_TRACK) - I(rb, REC_TRACK);
        if (d) return d;
    }
    d = strcmp(str(ra, REC_PATH), str(rb, REC_PATH));
    if (!d) d = I(ra, REC_CUE_START) - I(rb, REC_CUE_START);
    return d ? d : by_index(a, b);
}

/* Reorder queue (n songs) into albums or folders in random order, each in its own order. 0 when
 * the index could not be allocated (the queue is then untouched). */
static int group_order(void *queue, unsigned n, int folders) {
    entry *v = calloc(n, sizeof *v);
    unsigned *rank, groups = 0, i, j, k;
    char tmp[REC_SIZE];
    if (!v) return 0;
    by_folder = folders;
    for (i = 0; i < n; ++i) {
        v[i].rec = deque_at(queue, i), v[i].idx = i;
        if (folders) v[i].dir = dir_len(str(v[i].rec, REC_PATH)); /* once per song, not on every comparison */
    }
    sort(v, n, group_cmp);
    for (i = 0; i < n; ++i) { /* number the groups, in sorted order */
        if (i && key_cmp(&v[i - 1], &v[i])) ++groups;
        v[i].group = groups;
    }
    ++groups;
    rank = calloc(groups, sizeof *rank);
    if (!rank) {
        free(v);
        return 0;
    }
    for (i = 0; i < groups; ++i) rank[i] = i;
    for (i = groups; i > 1; --i) { /* Fisher-Yates (q2-pod make_order's group ranks) */
        unsigned t;
        j = rand_below(i);
        t = rank[i - 1], rank[i - 1] = rank[j], rank[j] = t;
    }
    for (i = 0; i < n; ++i) v[i].group = rank[v[i].group];
    free(rank);
    sort(v, n, play_cmp);
    /* new[i] = old[v[i].idx]: follow each cycle with one record of temporary storage. A record's
     * strings stay owned by exactly one slot, so the deque frees them as usual. */
    for (i = 0; i < n; ++i) {
        if (v[i].group == ~0u) continue;
        if (v[i].idx == i) {
            v[i].group = ~0u;
            continue;
        }
        memcpy(tmp, deque_at(queue, i), REC_SIZE);
        for (j = i;; j = k) {
            k = v[j].idx;
            v[j].group = ~0u;
            if (k == i) break;
            memcpy(deque_at(queue, j), deque_at(queue, k), REC_SIZE);
        }
        memcpy(deque_at(queue, j), tmp, REC_SIZE);
    }
    free(v);
    return 1;
}

/* ---------------------------------------------------------------------------
 * The rows. 0 once Now Playing is opened, -1 with a message otherwise (nothing changed then: the
 * play mode is only set once the queue is ready and its first track is on the card).
 */
int shuffle_play(int kind) {
    void *list, *queue, *pick, *first;
    unsigned n, at = 0, idx = 0;
    int found;
    struct {
        void *dq;
        int idx, cls, mode;
    } context;
    if (kind < SHUFFLE_SONGS || kind > SHUFFLE_FOLDERS) return -1;
    /* the library, exactly as the Songs page loads it */
    list = loadLocalClassList(CLASS_ALL_SONGS) > 0 ? *(void **)PDEQ_SHOWLIST : (void *)0;
    n = list ? deque_size(list) : 0;
    if (!n) {
        toast(TR("Update Local Music first"));
        return -1;
    }
    if (kind != SHUFFLE_SONGS && n > SHUFFLE_MAX) {
        toast(TR("Too many songs to shuffle"));
        return -1;
    }
    if (kind == SHUFFLE_SONGS) {
        unsigned tries;
        at = rand_below(n);
        for (tries = 0; tries < 50 && pc_is_path(str(deque_at(list, at), REC_PATH)); ++tries)
            at = rand_below(n); /* podcasts stay out of the shuffle (patch/pcmodel.c) */
    }
    pick = deque_at(list, at);
    queue = _create_deque("stSongInfo");
    if (!queue) return -1;
    deque_init(queue);
    /* the Songs page's row handler: the queue of the list's songs and the memory-playback record */
    found = loadSongList(queue, str(pick, REC_NAME), I(pick, REC_CUE_START), CLASS_ALL_SONGS);
    n = deque_size(queue);
    if (kind == SHUFFLE_SONGS && n) {
        /* loadSongList finds a song by file name and CUE start, so a duplicate name (01.flac in
         * every album) would always start at the first; the drawn row's own index wins when it is
         * the same song */
        if (at < n && !strcmp(str(deque_at(queue, at), REC_PATH), str(pick, REC_PATH)))
            idx = at;
        else if (found >= 0 && (unsigned)found < n)
            idx = (unsigned)found;
    }
    if (n) { /* the podcast files are taken out of the queue (a copy, made only when there are any), then the albums and folders are put in their play order */
        int at_i = (int)idx;
        queue = pc_strip(queue, &at_i);
        idx = (unsigned)at_i;
        n = queue ? deque_size(queue) : 0;
        if (!queue) {
            toast(TR("Update Local Music first"));
            return -1;
        }
    }
    if (kind != SHUFFLE_SONGS && n && !group_order(queue, n, kind == SHUFFLE_FOLDERS)) {
        deque_destroy(queue);
        toast(TR("Not enough memory"));
        return -1;
    }
    first = n ? deque_at(queue, idx) : (void *)0;
    if (!first || access(str(first, REC_PATH), F_OK)) {
        deque_destroy(queue);
        toast(TR(n ? "Storage unavailable" : "Update Local Music first"));
        return -1;
    }
    /* Shuffle Songs: shuffle on over the whole library (stock mode List play), the queue shuffled
     * behind the drawn first song when Now Playing loads it (sh_load_playlist). Albums and folders
     * play their queue in order, shuffle off. */
    if (kind == SHUFFLE_SONGS)
        set_mode(MODE_SHUFFLE, 1); /* the queue about to load replaces the current one: no reorder of it */
    else
        set_in_order(1);
    *(int *)G_CLASS_TYPE = CLASS_ALL_SONGS; /* as allmusic_page_init leaves it (@0x5289e8) */
    context.dq = queue, context.idx = (int)idx, context.cls = CLASS_ALL_SONGS, context.mode = PLAY_MODE;
    navigator_to_with_context("playing_page", &context); /* start_player copies the queue */
    deque_destroy(queue);
    return 0;
}

/* The album page's and the Songs page's Play and Shuffle buttons (patch/albumpage.c, patch/songs.c)
 * use the same generator, message box and play-mode setters as the rows above: Shuffle turns the
 * flag on, Play turns it off (and Repeat one into List play), so Now Playing plays what was asked for. */
unsigned pod_rand(unsigned n) { return rand_below(n); }
void pod_toast(const char *text) { toast(text); }
void pod_set_mode(int mode) { set_mode(mode, 0); } /* the current queue is reordered now (no queue load follows) */
void pod_set_in_order(void) { set_in_order(0); }
void pod_set_mode_for_queue(int mode) { set_mode(mode, 1); } /* a queue load follows: the flag only */
void pod_set_in_order_for_queue(void) { set_in_order(1); }

/* libcstl's deque_pop_back (docs/modules/queue.md "Clear engine"). Demo does not import it, but libcstl is the firmware's fixed shared library: demo's GOT slot of deque_size holds
 * its address once the first call has bound it (MIPS lazy binding: until then the stub inside demo's image), and pop_back lies CSTL_POP_OFF - CSTL_SIZE_OFF above it. The build pins the
 * library file (tools/pod.py check_libcstl); here the words of both functions are compared at the resolved addresses, so another library, an unbound slot or a moved function gives 0
 * (Clear refused) and nothing is called. */
static void (*cstl_pop_back(void))(void *) {
    static const unsigned size_words[] = CSTL_SIZE_WORDS, pop_words[] = CSTL_POP_WORDS;
    unsigned size_fn = *(volatile unsigned *)GOT_DEQUE_SIZE, pop_fn, i;
    if ((size_fn & 3) || size_fn <= STOCK_IMAGE_END) return (void (*)(void *))0;
    for (i = 0; i < sizeof size_words / sizeof size_words[0]; ++i)
        if (((const unsigned *)size_fn)[i] != size_words[i]) return (void (*)(void *))0;
    pop_fn = size_fn - CSTL_SIZE_OFF + CSTL_POP_OFF;
    for (i = 0; i < sizeof pop_words / sizeof pop_words[0]; ++i)
        if (((const unsigned *)pop_fn)[i] != pop_words[i]) return (void (*)(void *))0;
    return (void (*)(void *))pop_fn;
}

/* Clear can run: the kill switch is off, libcstl is the pinned one and no DLNA service runs (the Queue page shows its button only then). The slot is bound once the queue was read (deque_size). */
int pod_clear_ready(void) { return !home_off() && !dlna_running() && cstl_pop_back() != (void (*)(void *))0; }

/* Clear on the Queue page: every track after the play position is removed, the playing track and the history stay (docs/modules/queue.md). The deque is shortened in place: libcstl's
 * deque_pop_back runs the stSongInfo destructor @0x5dabfc (free, memset) on the last record and frees a block it empties; it allocates and copies nothing, and the records 0..pos are never
 * moved, rewritten or freed (so a stock reader of the playing track or of the history never sees a change). The payload lock is held for the whole removal, which re-reads the position
 * and the size first (what the lock excludes: our reorders, queue loads and clear, docs/modules/shuffle.md Locking). 1 cleared; 0 nothing after the play position; -1 refused (kill switch, or
 * libcstl is not the pinned one, or the DLNA service runs). The saved shuffle order describes a queue that is gone (the flag itself stays). A preload that is open already opened the old next file: it is closed with
 * stock's own Gapless setter (one send) before the first pop. */
int pod_clear_upnext(void) {
    void *q;
    void (*pop)(void *);
    unsigned n, keep;
    int pos, r = 0;
    if (home_off()) return -1;
    sh_enter();
    if (dlna_running()) { /* the service starts on the UI thread (this one), so it cannot start between this check and the pops */
        sh_leave();
        return -1;
    }
    q = play_queue();
    n = q ? deque_size(q) : 0; /* (binds deque_size's GOT slot if nothing did) */
    pos = mclGetPlayPos();
    pop = cstl_pop_back();
    if (pos >= 0 && (unsigned)pos + 1 < n) {
        r = -1;
        if (pop) {
            keep = (unsigned)pos + 1;
            cancel_preload(); /* an open preload opened the old next file: closed, the Gapless setting put back */
            if (*(int *)MCL_PRELOAD_NEXT > pos) *(int *)MCL_PRELOAD_NEXT = -1;
            while (deque_size(q) > keep) pop(q);
            drop_order();
            r = 1;
        }
    }
    sh_leave();
    return r;
}
