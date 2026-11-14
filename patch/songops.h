/* What a page that lists stock songs does with them, shared by the Songs page (patch/songs.c) and the album page (patch/albumpage.c).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 * Moved from patch/songs.c (docs/modules/songs.md "Select mode on the page itself: the evidence" has the stock code read): the page keeps its marks in a bitset of its
 * own; the stock Delete and Add run on the stock selection vector, which is filled from that bitset at the moment of the action. A page owns its state (its list, its
 * browsing record, its select mode); these functions take what they need and touch no widget.
 */
#pragma once
#include "libsrc.h"

enum {
    SO_KEEP,
    SO_IN_ORDER,
    SO_SHUFFLE
}; /* the play mode a start sets: a row tap keeps it (as stock), Play plays in order, Shuffle shuffles */

/* How the queue is shown: Now Playing opens on queue at idx with class cls (the caller's way: the Songs page's navigator_to_with_context, the album page's pod_open_player). */
typedef void (*so_open_fn)(void *queue, int idx, int cls);

/* Now Playing on queue at idx with class cls: navigator_to_with_context("playing_page", ...) and nothing else (a so_open_fn). */
void pod_start_player(void *queue, int idx, int cls);

/* Now Playing opens on queue at idx with class cls the way a stock album row's tap opens it (a so_open_fn; also the Daily Mix card's play disc). */
void pod_open_player(void *queue, int idx, int cls);

/* A deque holding a copy of rec alone (as the stock queries push rows); NULL without memory. The caller destroys it. */
void *so_row_deque(void *rec);

/* The stock selection vector filled from the bitset: select_recordinit(count), set_selectindex(i) for each marked row. 0 when there is no vector. */
int so_selection(unsigned count, const unsigned char *sel);

/* The Delete button (the stock handler's sequence, @0x527f48): nothing marked is a message; the confirm dialog (the library only, or the files too); batch_delete_file(cls, list,
 * the selection); the message. 0: nothing was deleted (nothing marked, or the dialog said no); 1: deleted; -1: the selection could not be made (valid 0: the stock list is not
 * the page's any more). The caller leaves select mode and reads the list again for 1 and -1. */
int so_delete(int cls, void *list, unsigned count, const unsigned char *sel, unsigned nsel, int valid);

/* The card is in (/tmp/mmc_add, as the stock About page reads it). */
int so_card(void);
/* The translated message for a song whose file is not found: "File not found" with the card in, "Storage unavailable" without it. */
const char *so_missing(void);
/* Clean Up Playlist, the check: marks in sel ((count + 7) / 8 bytes, cleared first) the rows of list whose path is under /mnt/mmc/ and whose file is not there. Returns
 * how many; *checked is how many rows had a path on the card (the others are never marked). */
unsigned so_gone_mark(void *list, unsigned count, unsigned char *sel, unsigned *checked);
/* Clean Up Playlist, what the user is asked about: the row ids of the n marked rows (calloc'd, the caller frees; 0 for a row that is not a song row), and, after the
 * dialog and a new so_gone_mark, the marks cut down to the rows whose id is among them (so_keep_ids; returns how many stay): a row that went missing under the dialog
 * was not asked about and is not removed. */
int *so_marked_ids(void *list, unsigned count, const unsigned char *sel, unsigned n);
unsigned so_keep_ids(void *list, unsigned count, unsigned char *sel, const int *ids, unsigned n);
/* Clean Up Playlist, the repair: for each marked row of a playlist's list (CLASS_PLAYLIST_SONGS: a record's id is its row's id in the playlist table), the library's song
 * with the same file name, CUE range, title, album and artist whose path is under /mnt/mmc/ and whose file is there (the first when several are); the row's fileurl becomes that song's path
 * (toolsUpdateDbTable, one row by its id). Returns how many rows were rewritten; the list in memory is not changed (the caller reads it again). */
unsigned so_relink(void *list, unsigned count, const unsigned char *sel);
/* Clean Up Playlist, the removal: each marked row leaves the playlist table by its own id (toolsDeleteItemById: this playlist's row only, never a file, never another
 * playlist's copy of the song). Returns how many rows went. */
unsigned so_clean(void *list, unsigned count, const unsigned char *sel);

/* The Add button: our picker (patch/picker.h) over the page, or where it cannot open the stock one (@0x5280c0: playlist_page with PICKER_ADD | cls). Either adds the selection to the playlist that is tapped and closes
 * itself. title_save (0x200 bytes) takes nagvation_title, which the picker may overwrite; *picker is set before the picker opens. 0: nothing marked; 1: the picker is open;
 * -1: the selection could not be made. */
int so_add(int cls, unsigned count, const unsigned char *sel, unsigned nsel, int valid, char *title_save, int *picker);

/* Song `at` (-1: a random one) of the list as the queue, in Now Playing (open). how: SO_*. Nothing changes when the song is not on the card (a message). Returns 0 when the queue was started, -1 when nothing was (the message is shown). */
int so_play(int cls, void *list, int at, int how, so_open_fn open);
/* The same for a page that shows the list reversed (list is the reversed stock list, `at` a position in it): the queue loadSongList builds is reversed too, so the song at `at` is the one shown there and the queue plays in the order shown. */
int so_play_dir(int cls, void *list, int at, int how, so_open_fn open, int rev);
/* so_play through a library source (patch/libsrc.h): src NULL or &lib_stock is so_play(cls, ...) unchanged; another source plays its own records (cls is ignored by it). 0 started, -1 nothing
 * started, -2 a DSD track that is not on the card (the page confirms a download). */
int so_play_src(const lib_src_t *src, int cls, void *list, int at, int how, so_open_fn open);
/* Puts the freshly built queue in the order a page shows (the Folders page's sorts) and returns where the record `pick` (the row played, a record of the page's list) now is, -1 when it cannot say. */
typedef int (*so_reorder_fn)(void *queue, void *pick);
/* so_play_dir with a reorder instead of a reversal (NULL: none). */
int so_play_with(int cls, void *list, int at, int how, so_open_fn open, int rev, so_reorder_fn reorder);
