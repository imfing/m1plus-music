/* The playlists' own times (patch/plmeta.c, docs/modules/playlists.md "Order"): when each playlist was added, last changed and last played, for the Playlists page's Date Added,
 * Last Played and Updated orders. Stock's playlist table has no time columns, so the times live in PLAYLISTS_META_FILE.
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * A playlist is its stock id AND its name: createPlayListItem reuses the lowest free id, so an entry whose name differs from the playlist with that id is the one of a deleted playlist and is
 * ignored (and replaced at the next stamp). Each call reads the file, changes it and writes it back; 0 when it was written, -1 when it was not (nothing else changed: the file is as it was).
 * A file that is there but is not one we wrote, or cannot be read, is never written over. A stamp is max(time(), the largest stamp in the file + 1): strictly increasing, whatever the clock says.
 */
#pragma once

#define PLM_ADDED \
    1 /* the rows of the Playlists "..." card: Date Added, Last Played, Updated (row 0 is Title); plm_get takes one */
#define PLM_PLAYED 2
#define PLM_UPDATED 3

int plm_added(int id, const char *name); /* a new playlist: added = updated = now, never played */
/* After an Import, in one write, each its own stamp: playlist i (id[i], name[i]) is new when was[i] < 0 (added = updated = now, never played), else it replaced the playlist of that
 * name whose id was was[i] (stock deletes it and makes it again, maybe under another id): its times move to id[i] and updated = now. A name too long to key is skipped. */
int plm_imported(unsigned n, const int *id, const char *const *name, const int *was);
int plm_updated(int id, const char *name); /* its songs or its order changed */
int plm_played(int id, const char *name); /* it was played from a row, Play or Shuffle */
int plm_rename(int id, const char *old,
               const char *name); /* the same playlist under another name: the times stay, updated = now */
int plm_forget_many(
    unsigned n, const int *id,
    const char *const *
        name); /* n deleted playlists: their entries go (an entry of the id under another name is a stale one and stays), one write */
/* Reads the file into memory for plm_get; -1 when it is not usable (plm_get then finds nothing). */
int plm_read(void);
/* The time (seconds, never 0) of the playlist (id, name) in what plm_read read; 0 when it has none for that row (PLM_ADDED, PLM_PLAYED, PLM_UPDATED). */
unsigned plm_get(int id, const char *name, int row);
