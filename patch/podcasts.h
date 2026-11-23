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

/* The archive (.archive, docs/modules/podcasts.md "All episodes"): at most PC_ARCH_MAX items and PC_ARCH_BYTES bytes are written and read; PC_ALL_MAX is the archive's count where a list is meant.
 * PC_LIST_MAX: the most episodes a list of a show holds (pc_all_cap; what the pages' rows, select bitsets and search results are sized for): the PC_MAX_EPS entries of .episodes and the files a folder with an archive
 * is scanned for (2400, pcmodel.c PM_ARCH_FILES, which checks the sum), so a recent list is never cut. */
#define PC_ARCH_MAX 2000
#define PC_ARCH_BYTES 1572864u
#define PC_ALL_MAX PC_ARCH_MAX
#define PC_LIST_MAX 2700

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
/* The RECENT list of a show, in the show's order (pc_order_get): newest first (publication date, then file name, digit runs by value, descending; a show of copied files only, no metadata entry, by file name alone), or the exact reverse, PC_LOCAL / PC_PART /
 * PC_REMOTE together; at most max (pc_all_cap of room holds every file of the show and every entry of .episodes: nothing is cut; pcmodel.c pm_load has the rule for a smaller room). It is .episodes (the newest PC_MAX_EPS entries) and the files on the card; a show with an archive reads .archive only to give a file (or .part) that no .episodes entry names its
 * title, date and description, and only when such a file exists. Every page and reader but the All Episodes page and the search inside a show uses this. Returns the count. */
int pc_load_show(const pc_show_t *show, pc_ep_t *out, int max);
/* A list in a block of its own size (pc_all_cap of room while it is read; the caller frees it), *count entries; NULL without memory. What the pages and readers call: pc_load_recent the recent list, pc_load_fit with all the complete one. */
pc_ep_t *pc_load_recent(const pc_show_t *show, int *count);
pc_ep_t *pc_load_fit(const pc_show_t *show, int *count, int all);
/* The COMPLETE list: with an archive (.archive: every item of the feed) the union of .episodes and .archive, an episode once (the .episodes entry wins), at most PC_LIST_MAX (past that the newest PC_MAX_EPS that are only in the feed are kept, then the episodes with a file, then the rest by date); without one it is the recent list. pc_all_cap: how many entries out
 * needs for either list (PC_LIST_MAX with an archive, else PC_MAX_EPS and the files a show folder is scanned for). pc_count_all: the number of episodes pc_load_show_all would return (nothing sorted or copied), for the Show page's See All (N). */
int pc_load_show_all(const pc_show_t *show, pc_ep_t *out, int max);
int pc_count_all(const pc_show_t *show);
int pc_has_archive(const pc_show_t *show);
int pc_all_cap(const pc_show_t *show);
/* A refresh's part of the archive: the lines of the refreshed .episodes text (eps, epsn) that .archive's text (old, oldn) does not have (by guid, else by file name) are put, newest first by date among the archive's lines, into
 * put(ctx, data, n) (return 0 to fail), after a header line, the archive's lines following, at most maxn lines and maxbytes bytes (the oldest are dropped). Nothing is put when the archive has every line. Returns the new lines
 * put (0: none, nothing put), -1 on a failure (no memory, or put failed). */
int pc_archive_merge(const char *eps, unsigned epsn, const char *old, unsigned oldn,
                     int (*put)(void *ctx, const char *data, unsigned n), void *ctx, int maxn, unsigned maxbytes);
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
        size); /* an episode's date, Apple Podcasts style, in the language (docs/modules/podcasts.md "Pages and controls"); now: seconds since 1970 */
unsigned pc_hash(const char *s); /* FNV-1a over the ASCII-lower-cased bytes, never 0 */
unsigned pc_guid_hash(
    const char *s,
    unsigned n); /* the hash an .episodes line's g= gets (pc_ep_t.guid): FNV-1a over the n bytes as they are, never 0 */
int pc_is_path(const char *path); /* the path is a file in a show folder under the Podcasts folder (case-insensitive) */
int bk_is_path(
    const char *
        path); /* the path is a file under the Audiobooks folder (case-insensitive, bounded by the slash); pc_is_path stays podcasts only */
int pc_spoken_path(const char *path); /* pc_is_path or bk_is_path: spoken audio, kept out of the music features */
void pc_fmt(char *out, unsigned size, const char *fmt, unsigned n);
void pc_fmt2(char *out, unsigned size, const char *fmt, unsigned a, unsigned b);
void pc_left_text(char *out, unsigned size,
                  unsigned secs); /* "35m left" (minutes rounded up): an episode's or a book part's remaining time */
void pc_len_text(char *out, unsigned size, unsigned secs); /* "48m": a length */
/* the same for a text with two %d: the first becomes a, the second b */ /* fmt with its one %d replaced by n */
/* Whether a cover picture's header says it is small enough to decode (PC_COVER_MAX_PX); a missing or unknown file is refused. path is a plain path. */
int pc_cover_ok(const char *path);
/* A picture file's kind and size from its header: 1 JPEG (*sof its start-of-frame marker: 0xc0 / 0xc1 baseline, 0xc2 progressive), 2 PNG (*sof 0), 0 anything else (then *w = *h = 0). */
int pc_pic_info(const char *path, unsigned *w, unsigned *h, unsigned *sof);

/* The resume ring and the played marks. pc_state: PC_NEW (nothing saved), PC_PROGRESS (a place, *pos and *len set), PC_DONE (played). */
enum { PC_NEW = 0, PC_PROGRESS = 1, PC_DONE = 2 };
int pc_state(unsigned hash, unsigned *pos, unsigned *len);
void pc_mark(
    unsigned hash,
    int played); /* played: the episode is done (place cleared); else it is new again (forgotten); written at once */
void pc_mark_hold(
    unsigned hash,
    int played); /* the same with nothing written: the caller's pc_flush does (one write for a loop of marks) */
void pc_flush(void); /* write the ring if it changed (the page's own actions) */
unsigned pc_rev(void); /* grows with every change a list shows (a place, a mark) */
typedef struct { /* an episode partly played, for Continue Listening */
    int show; /* the index in the shows array given to pc_continue */
    unsigned hash, pos,
        len; /* the ring key, the place and the length the ring saw (an episode in progress always has both: a place is only kept for a length that is known) */
    char file[PC_FILE], title[PC_TITLE];
} pc_cont_t;
/* The episodes partly played, the most recently played first (the ring's order), at most max, found among the shows' files (docs/modules/podcasts.md "Pages and controls"). Returns the count. */
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
unsigned bk_book_of(
    const char *
        path); /* the book's speed key: pc_hash of "audiobooks/" + the book folder's name (a loose file: its own name) inside an Audiobooks path, 0 for another path */

/* The timer hook: the track the player is on (cc_playing(), NULL when none). Called by the places that already see it on a timer (recent_note, so the
 * Now Playing tick, the mini bar's and the Podcasts page's). Saves the place, marks played, jumps to a saved place after a start, and puts the speed back. */
void pc_note(void *track);
/* The hook in stock's tag reader (get_id3info 0x4dfd58, the strcpy of the parsed path at 0x4dff4c; docs/modules/podcasts.md): stock's strcpy(info, path), then for a podcast path the episode and the show
 * in the struct's title / artist / album. Returns info, as strcpy does. */
char *pc_id3_path(char *info, const char *path);
/* The Library query filter (the two hooks on toolsQueryDbTable 0x5ee77c and toolsQueryDbTableAndSort 0x5ee9ac; docs/modules/payload.md hook 6): stock's query with songtable replaced by a subquery without
 * the /mnt/mmc/Podcasts/ and /mnt/mmc/Audiobooks/ paths. Same arguments and result as the stock functions. */
int pc_library_query(const char *db, const char *sql, void *row, int sort);
int pc_sorted_query(const char *db, const char *sql, void *row, int sort);
/* Set around a loadLocalClassList(0xf00a) (the Favourites query) to read the Saved episodes (myfav rows under the Podcasts folder) instead of the music Favourites; 0 otherwise. */
extern unsigned char pc_saved_scope;
extern const char
    *pc_genre_exact; /* the genre split's per-tag query: the whole raw tag, asked exactly (pcmodel.c pq_filter) */
/* An episode is about to start: forget a played mark so it plays from the beginning (a place is kept: pc_note jumps to it). */
void pc_restart(unsigned hash);
/* A queue (stSongInfo deque) with the podcast and audiobook files taken out, for Shuffle: the queue itself when it has none; else a new queue (copies), *idx now the song that followed or was
 * at *idx, the old queue destroyed. NULL when nothing but podcasts was in it (the old queue destroyed too). */
void *pc_strip(void *queue, int *idx);

/* patch/podcasts.c: the queue of a show's local episodes, set up as an episode start does. */
void *pg_episode_queue(const char *root, const pc_show_t *s, const pc_ep_t *eps, int neps, int at, int *idx);
int podcasts_open(void); /* the shows on the card and their episodes */
int podcasts_go(void);
int podcasts_goto(
    const char *path,
    int notes); /* the Control Center's shortcuts: the Shows level (path 0), the Show page of the episode path, or (notes) its own page */
void pg_relight(void); /* the open cover-tinted pages tint again (see ab_relight, patch/entries.h) */
int pg_has_tone(void); /* the Show page shows a cover's tone now (not the shows list or an episode) */

/* The Show page's list for the search inside the show (patch/pcfind.c): the episodes in the show's order, whether one is played, the open show's key, and the episode page of episode i opened on the
 * Show page (1; 0 when it will not: Back from it opens the search again). */
int pg_find_count(void);
const pc_ep_t *pg_find_ep(int i);
int pg_find_played(int i);
unsigned pg_find_show(void);
int pg_find_pick(int i);
int pg_find_more(char *out, unsigned size);
void pg_find_more_tap(void);
int pg_find_sync(void);

/* The slot of a key in the resume ring: 0 the most recently played, -1 absent (patch/pcmodel.c; the Audiobooks model, patch/bkmodel.c, finds a book's current part with it). */
int pc_recent_rank(unsigned hash);

/* A named image of the theme (a w x h RGBA tile such as pod_ic_discovertile) decoded WITH its alpha into a bitmap of ours (the image manager's copy is dropped at once); NULL when it cannot be made. The caller
 * bitmap_destroy's it. The Podcasts Library rows' tiles, and the Audiobooks Library's LibriVox row (patch/bkpage.c). */
void *pg_rgba_win(void *win, const char *name, unsigned w, unsigned h);
