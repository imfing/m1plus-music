/* Internet Radio: the engine (patch/radio.c); the pages are patch/radiopage.c and patch/radionp.c. docs/modules/radio.md has the design.
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 * The playlist, CSV, escape and ffmpeg-line parsers and the station favourites follow q2-pod's patch/radio.c and patch/video.c (MIT, README.md).
 */
#pragma once

#define RD_MAX 300 /* stations, countries or genres one list holds (the directory has some 250 countries) */
#define RD_FETCH_MAX (256 << 10) /* the directory's answer is cut here */
#define RD_DIR \
    "/mnt/mmc/Radio" /* favourites.m3u (the Stations list), the user's own .m3u / .pls (read only by Import from Card) */
#define RD_FAVS RD_DIR "/favourites.m3u"
#define RD_FAVS_TMP RD_DIR "/favourites.m3u.tmp"
#define RD_RECENT_FILE \
    "/mnt/data/m1plus/radio-recent" /* the last stations played, newest first, as an .m3u (settings folder) */
#define RD_RECENT_TMP "/mnt/data/m1plus/radio-recent.tmp"
#define RD_VIEW_FILE \
    "/mnt/data/m1plus/radio-view" /* the station lists' mode, as ALBUMS_FILE: "1" the grid, "0" the list (also when missing or garbage) */
#define RD_VIEW_TMP "/mnt/data/m1plus/radio-view.tmp"
#define RD_RECENT_MAX 10
#define RD_API "https://all.api.radio-browser.info" /* the directory's round-robin name */
#define RD_QUERY "order=votes&reverse=true&limit=100&hidebroken=true"
#define RD_SILENT_MS 20000 /* a start hciplayer never reports playing for fails after this long */
#define RD_STALL_MS 10000 /* a playing stream hciplayer stops reporting playing for this long is restarted once */
#define RD_STEADY_MS 60000 /* a stream that played this long earns a new restart */
#define RD_GRACE_MS 1500 /* after a start stock's flags are not read yet */
#define RD_POLL_MS 500
#define RD_FAV_MAX 200 /* a favicon address longer than this is dropped */
#define RD_LOGO_DIR \
    RD_DIR "/.logos" /* <hash>.jpg: a station's logo shrunk to 192 px; <hash>.no: no picture to be had */
#define RD_NAME_MAX 120 /* bytes of a station's name kept for display */

/* A list's text, cut into strings in place: a station's name, url and (the directory's country, codec and bitrate, tab separated, or "") info; a country's or
 * genre's name, key (its code or its tag) and station count (as text, in info). */
typedef struct {
    char *buf;
    unsigned len;
    int n, truncated;
    unsigned name[RD_MAX + 1], url[RD_MAX + 1],
        info[RD_MAX + 1]; /* offsets into buf; info 0 = none (offset 0 is never a string start of a later row) */
} rd_list_t;

static inline const char *rd_name(const rd_list_t *l, int i) { return l->buf + l->name[i]; }
static inline const char *rd_url(const rd_list_t *l, int i) { return l->buf + l->url[i]; }
static inline const char *rd_info(const rd_list_t *l, int i) { return l->info[i] ? l->buf + l->info[i] : ""; }

/* ---- the parsers (pure; tests call them) ---- */
/* An .m3u's or .pls's stations in buf (NUL-terminated, cut in place), at most max: #EXTINF names the next URL, "#M1+:country<TAB>codec<TAB>bitrate" is its info, a .pls's FileN= is
 * a URL and TitleN= names the FileN of the same N whatever their order. A line without "://" is no station. Returns the count. */
int rd_playlist(char *buf, unsigned *name, unsigned *url, unsigned *info, int max);
/* radio-browser's /csv/stations/... in src (len bytes, a NUL after; decoded in place): the columns are found by their header (name, url, url_resolved, country, codec, bitrate); a row without a
 * name or an address, or with fewer fields than the header, is skipped; the stream is url_resolved when it has one. Each station's name, address and info ("country<TAB>codec<TAB>bitrate") are
 * written to pool (size bytes; offset 0 is a NUL, "no info"), the offsets to name / url / info. Quoted fields (commas, "" and line feeds inside) are decoded. */
int rd_stations(char *src, unsigned len, char *pool, unsigned size, unsigned *name, unsigned *url, unsigned *info,
                int max);
/* radio-browser's /csv/countries (name,iso_3166_1,stationcount) or /csv/tags (name,stationcount): name, key (the code, or with coded 0 the name) and the count's text; a row whose count is 0 is dropped. */
int rd_choices(char *buf, unsigned *name, unsigned *key, unsigned *count, int max, int coded);
/* s %-encoded into out (n bytes) as a URL's path segment. */
void rd_url_escape(const char *s, char *out, unsigned n);
/* The favicon address of a station's info (its fourth field), "" and 0 when it has none. */
int rd_favicon(const char *info, char *out, unsigned n);
/* "Germany · MP3 128k" from a station's info ("Germany\tMP3\t128"); "" when it has nothing. */
void rd_caption(const char *info, char *out, unsigned n);

/* ---- lists ---- */
void rd_list_free(rd_list_t *l);
int rd_list_copy(rd_list_t *to, const rd_list_t *from); /* 1 copied, 0 no memory (to is empty) */
/* text (len bytes) parsed into l as an .m3u / .pls (kind 0) or radio-browser's CSV: stations (1), countries (2), genres (3); 1 when something was parsed. */
void rd_list_move(rd_list_t *to, rd_list_t *from); /* to takes from's text (its own is freed); from is empty */
int rd_list_set(rd_list_t *l, const char *text, unsigned len, int kind);

/* ---- the card ---- */
int rd_favs_read(
    rd_list_t
        *l); /* favourites.m3u (the Stations list); 0 when there was no memory or the file is cut or holds a NUL */
int rd_fav_index(const rd_list_t *favs, const char *url); /* url's row, else -1 */
/* l's station i out of favourites.m3u when it is there, else appended: 1 added, 0 removed, -1 not written (nothing changed). */
int rd_fav_toggle(const rd_list_t *l, int i);
int rd_fav_has(const char *url);
/* Import from Card: every .m3u, .m3u8 and .pls of RD_DIR by file name (not favourites.m3u, dot files) appended to favourites.m3u, a station whose address is there already (or came
 * from an earlier file) skipped, written once; the files are never touched. Returns the stations added (0 = none new), -1 not written (no card, write failed; nothing changed), -2 no playlist
 * in the folder. *full is 1 when RD_MAX stopped it (what fitted is added). */
int rd_fav_import(int *full);
unsigned rd_serial(
    void); /* bumped by every start and every favourites change: the Stations list and Now Playing's sheet re-read */
int rd_recent_read(rd_list_t *l);
void rd_recent_push(const rd_list_t *l, int i); /* the station first, once, at most RD_RECENT_MAX */
int rd_recent_clear(
    void); /* radio-recent emptied (a header and no station); 1 written, 0 not. Touches no playing station */
int rd_last_read(
    rd_list_t
        *l); /* the first entry of radio-recent (the station last played) as a one-station list; 1 when there is one */

/* ---- playing ---- */
enum { RD_IDLE = 0, RD_CONNECTING = 1, RD_PLAYING = 2, RD_ERROR = 3, RD_STOPPED = 4, RD_PAUSED = 5 };
/* Events of the state machine (the table is in patch/radio.c and docs/modules/radio.md) and its actions. */
enum {
    RD_EV_PLAY,
    RD_EV_BAD,
    RD_EV_BT,
    RD_EV_FAILSTART,
    RD_EV_STOP,
    RD_EV_LOCAL,
    RD_EV_REROUTE,
    RD_EV_REROUTE_PAUSED,
    RD_EV_HEAR,
    RD_EV_PAUSE,
    RD_EV_RESUME,
    RD_EV_ENDED,
    RD_EV_STALL,
    RD_EV_TIMEOUT,
    RD_EV_NOWIFI,
    RD_EV_N
};
enum { RD_A_STOP = 1, RD_A_START = 2, RD_A_RETRY = 4, RD_A_PAUSE = 8 };
/* The pure step: state | actions << 8 | error words index << 16 for an event in a state (tries = restarts used by this play, wifi = a connection exists). */
int rd_step(int state, int ev, int tries, int wifi);
int rd_play(
    const rd_list_t *l,
    int i); /* stops what plays, readies the DAC, starts station i of a copy of l in hciplayer; 1 started, 0 refused (rd_error says why) */
void rd_resume(void); /* Paused: stock's resume, or Error "No Wi-Fi" without a connection */
void rd_stop(void); /* the radio's own stop: mclStop, idempotent from any state */
int rd_state(void);
int rd_running(void); /* a station is connecting, playing or paused (the engine's timer lives) */
int rd_at(void);
int rd_owns_bar(
    void); /* the radio owns the Home mini bar: a station started this session and no local track has started since (it outlives Stop) */
const rd_list_t *rd_list(void); /* the list the station plays from (prev / next step along it) */
const char *rd_error(void);
void rd_poll(void); /* one poll (the engine's timer calls it; tests too) */

/* ---- station logos (a worker of its own, one at a time, never beside the directory fetch) ---- */
unsigned rd_logo_hash(const char *url);
/* The logo file of a hash into path (n bytes): 1 it exists, -1 none can be had (a .no file, or a failure this session), 0 not tried. */
int rd_logo_file(unsigned hash, char *path, unsigned n);
int rd_logo_start(
    const char *url); /* 1 started; 0 when the guards, a running job, the directory fetch or the cache say no */
int rd_logo_running(void);
void rd_logo_cancel(void);

/* ---- the directory (one worker thread; patch/radio.c) ---- */
enum { RD_F_NONE = 0, RD_F_RUNNING = 1, RD_F_DONE = 2 };
enum { RD_E_OK = 0, RD_E_WIFI, RD_E_CLOCK, RD_E_BUSY, RD_E_FAIL, RD_E_EMPTY, RD_E_PODBUSY };
/* Fetch path (an API path with its query) as kind (1 stations, 2 countries, 3 genres): 0 started, else RD_E_* (nothing started). RD_E_BUSY: a fetch or the radio's own logo job (asked to end) is in the
 * way, RD_E_PODBUSY: a podcast job is; the caller asks again. */
int rd_fetch(const char *path, int kind);
/* Whether a failed attempt is tried again, and after how many seconds (0: no): attempt = attempts made (1 after the first). A network or TLS failure or an HTTP 5xx: tried again twice (1 s, 2 s);
 * a cancel, the size cap and any other answer (4xx included) not. The worker uses a fresh libcurl handle for each try. */
int rd_fetch_retry(int rc, long code, int attempt);
int rd_fetch_state(void); /* RD_F_* */
void rd_fetch_cancel(void); /* Return while loading: the transfer ends within a second; the result is dropped */
/* The finished fetch into l (1 when it holds rows) and the worker joined; *err is RD_E_OK, or why not (RD_E_FAIL, RD_E_EMPTY). */
int rd_fetch_take(rd_list_t *l, int *err);
void rd_fetch_drop(void); /* the page is closing: cancel, wait for the worker and free */

/* Radio Now Playing (patch/radionp.c). rn_open: 0 opened or already up, -1 not (kill switch, no memory). */
int rn_open(void);
/* Station Info (patch/radioinfo.c), opened from Radio Now Playing's sheet for the station the engine has: 0 opened or already up, -1 not (kill switch, no station, no memory). */
int sinfo_open(void);
/* A Now Playing entry while a station connects or plays: opens Radio Now Playing, 1; else 0 (stock's player is for the caller). */
int rn_open_if_active(void);
/* The hook (tools/pod.py BACKTOPLAYER) over stock's on_backtoplayer_onclick: Radio Now Playing while radio is active, else stock. */
extern int rn_backtoplayer(void *ctx, void *e);

/* The hook (tools/pod.py START_PLAYER): installed over mclStartPlayer; local music stops the radio first, then stock runs. */
extern int rd_start_player(void);
/* The hooks over stock's save_stop_player / save_start_player (tools/pod.py SAVE_STOP, SAVE_START): the pair every output change runs around set_outputchannel. While a station runs,
 * the first stops the stream and the second restarts it on the new output (or refuses on Bluetooth) instead of stock's mclStartPlayer of the old local track. */
extern void rd_save_stop(void);
extern void rd_save_start(int paused);
