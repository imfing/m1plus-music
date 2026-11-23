/* What a page that lists stock songs does with them, shared by the Songs page (patch/songs.c) and the album page (patch/albumpage.c).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 * Moved from patch/songs.c (docs/modules/songs.md "Select mode: stock delete and add" has the stock code read): the page keeps its marks in a bitset of its
 * own; the stock Delete and Add run on the stock selection vector, which is filled from that bitset at the moment of the action. A page owns its state (its list, its
 * browsing record, its select mode); these functions take what they need and touch no widget.
 */
#pragma once
#include "libsrc.h"

enum {
    SO_KEEP,
    SO_IN_ORDER,
    SO_SHUFFLE,
    SO_ROW_ORDER
}; /* the play mode a start sets: SO_KEEP keeps it (as stock), SO_IN_ORDER / SO_ROW_ORDER play in order (Play pill vs a row tap), SO_SHUFFLE shuffles */

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

/* One row of the stock list `list` (count rows, class cls) added to playlist `playlist` as the stock picker adds: the vector holds that row alone, batch_add_file appends it (a song the playlist has is skipped). 0 when there is no vector. */
int so_add_row(int cls, void *list, unsigned count, unsigned row, int playlist);

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
/* Remove from Playlist (the row sheet, a stock playlist's select mode): the n playlist song rows of these ids (REC_ID of a playlist song record, taken before any dialog, so a list read
 * again meanwhile changes nothing) leave the table by their own ids as so_clean's do; an id of 100 or less (a playlist, or 0) is skipped. Returns how many went. */
unsigned so_remove_ids(const int *ids, unsigned n);
/* Rename Playlist: the playlist `id` (1..PL_MAX) gets `name` (not empty; quotes doubled) in both name columns of its header row through toolsUpdateDbTable. 1 when the statement ran. */
int so_rename_pl(int id, const char *name);

/* Reorder (a stock playlist's Edit mode, docs/modules/playlists.md "Reorder"): stock reads a playlist's songs by `id` order, so the order is the ids'. ids[0..n-1] are the row ids (REC_ID) of the displayed
 * rows of one range, strictly ascending and over PL_MAX; the row at index `from` of it moves to index `to`. The n ids stay where they are, the rows take them in the new order: one transaction through
 * toolsUpdateDbTable (each row to -its own id, with cd_num = playlist, then to its new id; negative ids are never used). Nothing is sent while stock's scan holds a transaction on the shared handle (DB_TX
 * above 0); else one call: SAVEPOINT, the updates, RELEASE (never refused for an open transaction; the serialized connection runs it whole). 1 when it ran; 0 when it did not (a bad argument,
 * no memory, a scan's transaction, a statement that failed: the handle's close rolled ours back) and nothing changed. The list in memory is not changed (the caller reads it again). */
int so_reorder_rows(int playlist, const int *ids, unsigned n, unsigned from, unsigned to);

/* The Add button: our picker (patch/picker.h) over the page, or where it cannot open the stock one (@0x5280c0: playlist_page with PICKER_ADD | cls). Either adds the selection to the playlist that is tapped and closes
 * itself. title_save (0x200 bytes) takes nagvation_title, which the picker may overwrite; *picker is set before the picker opens. 0: nothing marked; 1: the picker is open;
 * -1: the selection could not be made. */
int so_add(int cls, unsigned count, const unsigned char *sel, unsigned nsel, int valid, char *title_save, int *picker);

/* Song `at` (-1: a random one) of the list as the queue, in Now Playing (open). how: SO_*. Nothing changes when the song is not on the card (a message). Returns 0 when the queue was started, -1 when nothing was (the message is shown). */
int so_play(int cls, void *list, int at, int how, so_open_fn open);
/* The same for a page that shows the list reversed (list is the reversed stock list, `at` a position in it): the queue loadSongList builds is reversed too, so the song at `at` is the one shown there and the queue plays in the order shown. */
int so_play_dir(int cls, void *list, int at, int how, so_open_fn open, int rev);
/* so_play for a list that is the queue itself, in the order shown (the artist split's songs, patch/artsplit.c): its records are copied into the queue with class All Songs (0xf001) stamped, no stock query runs and the
 * memory playback's record is not written (loadSongList is not called): after a restart the same track resumes from the library list (docs/modules/artists.md "Split index"). */
int so_play_own(void *list, int at, int how, so_open_fn open);
/* so_play through a library source (patch/libsrc.h): src NULL or &lib_stock is so_play(cls, ...) unchanged; another source plays its own records (cls is ignored by it). 0 started, -1 nothing
 * started, -2 a DSD track that is not on the card (the page confirms a download). */
int so_play_src(const lib_src_t *src, int cls, void *list, int at, int how, so_open_fn open);
/* Puts the freshly built queue in the order a page shows (the Folders page's sorts) and returns where the record `pick` (the row played, a record of the page's list) now is, -1 when it cannot say. */
typedef int (*so_reorder_fn)(void *queue, void *pick);
/* so_play_dir with a reorder instead of a reversal (NULL: none). */
int so_play_with(int cls, void *list, int at, int how, so_open_fn open, int rev, so_reorder_fn reorder);
