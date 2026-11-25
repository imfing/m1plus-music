/* The Add to Playlist picker (patch/picker.h; docs/modules/picker.md has the design and the stock code read).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 * Stock's picker is playlist_page opened with PICKER_ADD | class; its row handler (@0x53d300) calls batch_add_file(class, 0xf00b, *pdeq_showlist, *SEL_VEC, the playlist's
 * id), shows msg_addplaylistsuccess and closes. Ours is the Playlists page in pick mode (patch/playlists.c); a tap there comes here with the playlist's id.
 *
 * The page reads every playlist (loadLocalClassList(0xff13) for its count and mosaic), and each read replaces *pdeq_showlist, the list the add needs. So the picker
 * copies the list (cc_copy_list) and the marks when it opens, and the add runs on the copy: the stock selection vector is filled from the marks at that moment (as
 * so_selection does for the stock picker) and batch_add_file takes the list as an argument. The browsing class, classinfo[0..1] and the navigation title that those
 * queries change are put back after each of them and when the page goes (the caller's own restore, patch/songs.c and patch/albumpage.c, then finds them as they were).
 */
#include "offsets.inc"
#include "stock.h"
#include "common.h"
#include "covercache.h"
#include "i18n.h"
#include "songops.h"
#include "picker.h"
#include "home.h"
#include "playlists.h"
#include "keyboard.h"
#include "plmeta.h"

static struct {
    int on, done;
    void *list; /* the copy of *pdeq_showlist at open */
    unsigned char *sel; /* the marks at open */
    unsigned count;
    int cls; /* the browsing class of the list: batch_add_file's first argument, as the stock picker's context carries it */
    int cls0, ci[2];
    char title[NAV_TITLE_SIZE];
    unsigned *keys; /* so_song_key of each song being added (the marked rows), two words each, sorted, no key twice */
    unsigned nkeys;
    unsigned char *seen; /* picker_in: a bit for each key, the ones found in the list it reads */
} pk __attribute__((section(".scratch")));

void picker_restore(void) {
    if (!pk.on) return;
    *(int *)G_CLASS_TYPE = pk.cls0;
    memcpy((void *)CLASSINFO, pk.ci, sizeof pk.ci);
    memcpy((void *)NAV_TITLE, pk.title, sizeof pk.title);
}

void picker_release(void) {
    if (!pk.on) return;
    picker_restore();
    if (pk.list) deque_destroy(pk.list);
    free(pk.sel);
    free(pk.keys);
    free(pk.seen);
    memset(&pk, 0, sizeof pk);
    keyboard_unpark();
}

static int pk_less(const unsigned *a, const unsigned *b) { return a[0] != b[0] ? a[0] < b[0] : a[1] < b[1]; }

/* The keys of the marked rows of the copy, sorted (Shell sort: no qsort among the imports) and each once. Without memory there are none: no row is marked as holding
 * the songs, the add is as before. Nor where a marked row is not a song (REC_TYPE 8): the Folders page's folders, playlist files and storages, which batch_add_file
 * turns into a folder's direct audio files or nothing, so the songs being added are not the rows. */
static void pk_make_keys(void) {
    unsigned i, j, n = 0, gap, *k;
    for (i = 0; i < pk.count; ++i)
        if (pk.sel[i / 8] >> (i % 8) & 1) {
            if (I(deque_at(pk.list, i), REC_TYPE) != 8) return;
            ++n;
        }
    k = n ? calloc(2 * n, sizeof *k) : (unsigned *)0;
    pk.seen = k ? calloc((n + 7) / 8, 1) : (unsigned char *)0;
    if (!pk.seen) {
        free(k);
        return;
    }
    for (i = j = 0; i < pk.count; ++i)
        if (pk.sel[i / 8] >> (i % 8) & 1) so_song_key(deque_at(pk.list, i), &k[2 * j++]);
    for (gap = n / 2; gap; gap /= 2)
        for (i = gap; i < n; ++i)
            for (j = i; j >= gap && pk_less(&k[2 * j], &k[2 * (j - gap)]); j -= gap) {
                unsigned a = k[2 * j], b = k[2 * j + 1];
                k[2 * j] = k[2 * (j - gap)], k[2 * j + 1] = k[2 * (j - gap) + 1];
                k[2 * (j - gap)] = a, k[2 * (j - gap) + 1] = b;
            }
    for (i = j = 0; i < n; ++i) /* (a song marked twice, as a list can hold it, is one song being added) */
        if (!j || pk_less(&k[2 * (j - 1)], &k[2 * i])) k[2 * j] = k[2 * i], k[2 * j + 1] = k[2 * i + 1], ++j;
    pk.keys = k, pk.nkeys = j;
}

unsigned picker_count(void) { return pk.on ? pk.nkeys : 0; }

int picker_in(void *songs) {
    unsigned i, n = songs ? deque_size(songs) : 0, found = 0;
    if (!pk.on || !pk.nkeys) return 0;
    memset(pk.seen, 0, (pk.nkeys + 7) / 8);
    for (i = 0; i < n && found < pk.nkeys; ++i) {
        unsigned h[2], lo = 0, hi = pk.nkeys;
        so_song_key(deque_at(songs, i), h);
        while (lo < hi) { /* the first key not below h */
            unsigned mid = (lo + hi) / 2;
            if (pk_less(&pk.keys[2 * mid], h))
                lo = mid + 1;
            else
                hi = mid;
        }
        if (lo < pk.nkeys && pk.keys[2 * lo] == h[0] && pk.keys[2 * lo + 1] == h[1] &&
            !(pk.seen[lo / 8] >> (lo % 8) & 1))
            pk.seen[lo / 8] |= (unsigned char)(1u << (lo % 8)), ++found;
    }
    return (int)found;
}

int picker_in_fav(void) {
    int n;
    if (!pk.on || !pk.nkeys) return 0;
    n = loadLocalClassList(CLASS_FAV) > 0 ? picker_in(*(void **)PDEQ_SHOWLIST) : 0;
    picker_restore();
    return n;
}

/* The picker over `list`, a copy that is the picker's from here (0 where it could not be made): count rows, the marks in sel. */
static int pk_open(int cls, void *list, unsigned count, const unsigned char *sel) {
    unsigned bytes = (count + 7) / 8;
    pk.on = 1; /* from here picker_release undoes what is made */
    pk.list = list;
    pk.sel = calloc(bytes, 1);
    if (!pk.list || !pk.sel || deque_size(pk.list) != count) {
        picker_release();
        return -1;
    }
    memcpy(pk.sel, sel, bytes);
    pk.count = count, pk.cls = cls;
    pk_make_keys();
    pk.cls0 = *(int *)G_CLASS_TYPE;
    memcpy(pk.ci, (void *)CLASSINFO, sizeof pk.ci);
    memcpy(pk.title, (void *)NAV_TITLE, sizeof pk.title);
    keyboard_park(); /* a page under it with the keyboard embedded (Search): New Playlist opens the keyboard page; picker_release gives it back */
    if (playlists_pick() < 0) {
        picker_release();
        return -1;
    }
    return 1;
}

int picker_open(int cls, unsigned count, const unsigned char *sel) {
    void *list = *(void **)PDEQ_SHOWLIST;
    if (pk.on || !count || !list || deque_size(list) != count) return -1;
    return pk_open(cls, cc_copy_list(list), count, sel);
}

int picker_open_rec(int cls, void *rec) {
    static const unsigned char one = 1;
    if (pk.on || !rec) return -1;
    return pk_open(cls, so_row_deque(rec), 1, &one);
}

/* The stock row handler's sequence: the selection into the stock vector, batch_add_file (duplicates skipped by checkPlayListExist; the rows of the copy get the new
 * ids), the message. A selection that cannot be made is msg_addfailed. PICKER_FAVOURITES is the stock Add button's Favourites choice (@0x5281c8):
 * batch_add_file(class, 0xf00a, list, vector, 0), then msg_addfavsuccess. Where some of the songs were there already (have of picker_count), the message says how many
 * of them were added ("Added 3 of 5 songs"): stock skips the others. A playlist (not Favourites, whose `name` is unused) is stamped as updated (patch/plmeta.c). */
void picker_add(int playlist, int have, const char *name) {
    int fav = playlist == PICKER_FAVOURITES, n = (int)picker_count();
    char msg[96];
    if (!pk.on || pk.done) return;
    pk.done = 1;
    if (!so_selection(pk.count, pk.sel)) {
        pod_toast(TR("msg_addfailed"));
        return;
    }
    batch_add_file(pk.cls, fav ? CLASS_FAV : CLASS_PLAYLISTS, pk.list, *(void **)SEL_VEC, fav ? 0 : playlist);
    if (!fav) plm_updated(playlist, name);
    if (have > 0 && have < n) {
        snprintf(msg, sizeof msg, TR("Added %d of %d songs"), n - have, n);
        pod_toast(msg);
    } else
        pod_toast(TR(fav ? "msg_addfavsuccess" : "msg_addplaylistsuccess"));
}
