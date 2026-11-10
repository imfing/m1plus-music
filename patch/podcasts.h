/* Podcasts: the episode model, the resume ring and the per-show speeds (patch/pcmodel.c); the page is patch/podcasts.c.
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 * The resume ring (a fixed ring of places keyed by the FNV-1a hash of the path, most recent first, a place within 30 s of either end forgotten), the
 * jump to the place a little after an episode starts and the per-folder speed follow q2-pod's Resume and Podcasts sections.
 * docs/modules/podcasts.md has the design, the file formats and the approximations.
 *
 * ONE module makes the episode list of a show (pc_load_show): the files on the card, merged with the metadata file the subscribe phase will write
 * (.episodes: one line per episode), sorted newest first. The RSS client of the next phase feeds the same list by writing that file; nothing in the
 * page knows where an episode came from. An episode has a state: PC_LOCAL (the file is on the card), PC_PART (a download under way), PC_REMOTE (known,
 * not downloaded). P0 shows PC_LOCAL only.
 */
#pragma once

/* (the PC_* sizes are patch/offsets.inc's: include it first) */

#define PC_ROOT_PATH \
    "/mnt/mmc/Podcasts" /* the folder, matched case-insensitively (pc_root gives the spelling the card has) */

typedef struct {
    char file[PC_FILE]; /* the file name in the show folder; "" = no file (yet) */
    char title[PC_TITLE]; /* the metadata title, else the file name without its extension */
    unsigned guid; /* FNV-1a of the metadata guid, 0 = none */
    unsigned pub; /* publication date, seconds since 1970 (UTC); the file's modification time without metadata */
    unsigned dur; /* duration in seconds; 0 = unknown */
    unsigned length; /* enclosure length in bytes (metadata), 0 = unknown */
    unsigned hash; /* ring key (pc_hash of the full path) of the local file; 0 when there is none */
    unsigned state; /* PC_LOCAL, PC_PART or PC_REMOTE */
    char desc[PC_DESC]; /* the entry's x=: the description as plain text, at most PC_DESC_CUT bytes; "" = none */
} pc_ep_t;

typedef struct {
    char dir[PC_FILE]; /* the folder name, as the card spells it */
    char title[PC_TITLE]; /* the show file's title, else the folder name */
    char cover[PC_FILE]; /* cover.jpg / folder.jpg (or .jpeg / .png), "" = none */
    char feed[PC_URL]; /* the show file's feed url ("" = none): kept for the subscribe phase */
    char image[PC_URL]; /* the show file's image url */
    unsigned count; /* episodes with a file */
    unsigned hash; /* pc_hash of dir (lower-cased): the key of the show's speed */
    unsigned fresh; /* of those, episodes not played and with no place saved */
    unsigned checked; /* the show file's checked=: seconds since 1970 of the last successful refresh, 0 = never */
    char author[PC_AUTHOR]; /* the show file's author= (the channel's itunes:author), "" = none */
    char category[PC_CAT]; /* the show file's category= (the first itunes:category), "" = none */
    char desc[PC_DESC]; /* the show file's desc= (the channel's itunes:summary, else description, as plain text) */
    unsigned
        newest; /* the newest episode's date, remote or local: the largest p= of the .episodes entries, else (no .episodes) the newest audio file's date; 0 = none: the Shows page's order */
    unsigned
        modified; /* the show file's modified=: the server's Last-Modified (seconds since 1970) of the feed we hold, 0 = none */
} pc_show_t;

/* The folder: out (PC_FILE + 20 bytes) is "/mnt/mmc/<Podcasts as the card spells it>"; 1 when it exists, else 0 (out then holds the default spelling). */
int pc_root(char *out);
/* The shows: the folders in it (those with an episode file or a metadata file), the most recently updated first (newest episode, remote or local; ties by title, a leading "The " aside); at most max. Returns the count. */
int pc_scan_shows(pc_show_t *out, int max);
/* Whether any show folder holds an episode file (the Pod's No Podcasts): stops at the first one, no metadata read. */
int pc_any_episode(void);
/* The episodes of a show in the show's order (pc_order_get): newest first (publication date, then file name, digit runs by value, descending; a show of copied files only, no metadata entry, by file name alone), or the exact reverse, PC_LOCAL / PC_PART / PC_REMOTE together; at most max. Returns the count. */
int pc_load_show(const pc_show_t *show, pc_ep_t *out, int max);
/* One file of a show folder: its modification time and its size in KB; 1 when it exists. */
int pc_stat(const char *root, const char *dir, const char *file, unsigned *mtime, unsigned *kb);
/* The audio files and .part files of a show folder, one callback each (name, size in KB, 1 for a .part); the count. No .episodes is read (the Shows page's totals). */
int pc_walk(const char *root, const char *dir, void (*cb)(void *ctx, const char *name, unsigned kb, int part),
            void *ctx);
/* The text formats (docs/modules/podcasts.md "Files"): the .episodes buffer into out (a header line, then one line per episode, tab separated key=value fields); the .show buffer into show.
 * Both return the number of records (pc_parse_show: 1 when the header is right). */
int pc_parse_eps(const char *buf, unsigned n, pc_ep_t *out, int max);
int pc_parse_show(const char *buf, unsigned n, pc_show_t *show);
void pc_when(
    unsigned pub, unsigned now, char *out,
    unsigned
        size); /* an episode's date, Apple Podcasts style, in the language (docs/modules/podcasts.md "The date"); now: seconds since 1970 */
unsigned pc_hash(const char *s); /* FNV-1a over the ASCII-lower-cased bytes, never 0 */
unsigned pc_guid_hash(
    const char *s,
    unsigned n); /* the hash an .episodes line's g= gets (pc_ep_t.guid): FNV-1a over the n bytes as they are, never 0 */
int pc_is_path(const char *path); /* the path is a file in a show folder under the Podcasts folder (case-insensitive) */
void pc_fmt(char *out, unsigned size, const char *fmt, unsigned n);
void pc_fmt2(char *out, unsigned size, const char *fmt, unsigned a, unsigned b);
/* the same for a text with two %d: the first becomes a, the second b */ /* fmt with its one %d replaced by n */
/* Whether a cover picture's header says it is small enough to decode (PC_COVER_MAX_PX); a missing or unknown file is refused. path is a plain path. */
int pc_cover_ok(const char *path);
/* A picture file's kind and size from its header: 1 JPEG (*sof its start-of-frame marker: 0xc0 / 0xc1 baseline, 0xc2 progressive), 2 PNG (*sof 0), 0 anything else (then *w = *h = 0). */
int pc_pic_info(const char *path, unsigned *w, unsigned *h, unsigned *sof);

/* The resume ring and the played marks. pc_state: PC_NEW (nothing saved), PC_PROGRESS (a place, *pos and *len set), PC_DONE (played). */
enum { PC_NEW = 0, PC_PROGRESS = 1, PC_DONE = 2 };
int pc_state(unsigned hash, unsigned *pos, unsigned *len);
void pc_mark(unsigned hash,
             int played); /* played: the episode is done (place cleared); else it is new again (forgotten) */
void pc_flush(void); /* write the ring if it changed (the page's own actions) */
unsigned pc_rev(void); /* grows with every change a list shows (a place, a mark) */
typedef struct { /* an episode partly played, for Continue Listening */
    int show; /* the index in the shows array given to pc_continue */
    unsigned hash, pos,
        len; /* the ring key, the place and the length the ring saw (an episode in progress always has both: a place is only kept for a length that is known) */
    char file[PC_FILE], title[PC_TITLE];
} pc_cont_t;
/* The episodes partly played, the most recently played first (the ring's order), at most max, found among the shows' files (docs/modules/podcasts.md "The Shows page"). Returns the count. */
int pc_continue(const pc_show_t *shows, int nshows, pc_cont_t *out, int max);

/* Per-show speed: playspeed_mode 0..3 (1x, 1.25x, 1.5x, 2x). pc_speed_set saves at once (0 when it could not be written). */
int pc_speed_get(unsigned show);
int pc_speed_set(unsigned show, int mode);
/* Per-show episode order: 0 newest first (the default), 1 oldest first (.m1plus/podcasts/order). pc_order_set saves at once (0 when it could not be written). */
int pc_order_get(unsigned show);
int pc_order_set(unsigned show, int order);
void pc_speed_apply(unsigned show); /* before an episode starts: the show's mode into playspeed_mode and the player */
unsigned pc_show_of(const char *path); /* pc_hash of the show folder name inside a podcast path, 0 for another path */
/* An episode's show-folder picture as "file://<path>" in url (size), NULL for another path or a show with none usable (the Queue page's episode covers). */
const char *pc_show_cover(const char *path, char *url, unsigned size);

/* The timer hook: the track the player is on (cc_playing(), NULL when none). Called by the places that already see it on a timer (recent_note, so the
 * Now Playing tick, the mini bar's and the Podcasts page's). Saves the place, marks played, jumps to a saved place after a start, and puts the speed back. */
void pc_note(void *track);
/* The hook in stock's tag reader (get_id3info 0x4dfd58, the strcpy of the parsed path at 0x4dff4c; docs/modules/podcasts.md "Tags"): stock's strcpy(info, path), then for a podcast path the episode and the show
 * in the struct's title / artist / album. Returns info, as strcpy does. */
char *pc_id3_path(char *info, const char *path);
/* The Library query filter (the two hooks on toolsQueryDbTable 0x5ee77c and toolsQueryDbTableAndSort 0x5ee9ac; docs/modules/payload.md hook 6): stock's query with songtable replaced by a subquery without
 * the /mnt/mmc/Podcasts/ paths. Same arguments and result as the stock functions. */
int pc_library_query(const char *db, const char *sql, void *row, int sort);
int pc_sorted_query(const char *db, const char *sql, void *row, int sort);
/* Set around a loadLocalClassList(0xf00a) (the Favourites query) to read the Saved episodes (myfav rows under the Podcasts folder) instead of the music Favourites; 0 otherwise. */
extern unsigned char pc_saved_scope;
/* An episode is about to start: forget a played mark so it plays from the beginning (a place is kept: pc_note jumps to it). */
void pc_restart(unsigned hash);
/* A queue (stSongInfo deque) with the podcast files taken out, for Shuffle: the queue itself when it has none; else a new queue (copies), *idx now the song that followed or was
 * at *idx, the old queue destroyed. NULL when nothing but podcasts was in it (the old queue destroyed too). */
void *pc_strip(void *queue, int *idx);
