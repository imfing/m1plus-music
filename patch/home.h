/* M1+ Music as Home: the crash guard and the launcher toggle (patch/home.c, docs/architecture.md).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE). The crash marker follows q2-pod's: a file
 * written and fsynced before a risky first step and removed after the step has proven itself.
 */
#pragma once
#include "covercache.h" /* CARD_DIR */

/* Files in /mnt/data (writable flash) and on the SD card. All of them are plain files the payload
 * checks with access() or reads with open(); none is parsed by stock code. */
#define KILL_SD "/mnt/mmc/m1plus-off" /* the long-standing kill switch (SD, may be unmounted at boot) */
#define KILL_DATA "/mnt/data/m1plus-off" /* the same, in flash (stages with the guard) */
#define MB_BLUR_OFF \
    "/mnt/mmc/m1plus-noblur" /* the mini player bar's backdrop blur (patch/minibar.c, experimental) is off while this exists on the card */
#define MARKER "/mnt/data/m1plus-run" /* exists from "boot attempt armed" until it has proven itself */
#define MARKER_TMP "/mnt/data/m1plus-run.tmp"
#define BAD_NOTE "/mnt/data/m1plus-bad" /* written when a marker was found at boot */
#define BAD_TMP "/mnt/data/m1plus-bad.tmp"
#define START_FILE "/mnt/data/m1plus-start" /* "1" = start in M1+ Music (default when missing), "0" = Shanling */
#define START_TMP "/mnt/data/m1plus-start.tmp"
#define ALBUMS_FILE \
    "/mnt/data/m1plus/albums-view" /* "1" = the Albums grid (default when missing, ALBUMS_DEFAULT_GRID), "0" = the list mode of the same page */
#define ALBUMS_TMP "/mnt/data/m1plus/albums-view.tmp"
#define PLAYLISTS_FILE \
    "/mnt/data/m1plus/playlists-view" /* the Playlists page's mode, as ALBUMS_FILE: "1" the grid (default), "0" the list */
#define PLAYLISTS_TMP "/mnt/data/m1plus/playlists-view.tmp"
#define RECENTADD_VIEW_FILE \
    "/mnt/data/m1plus/recently-added-view" /* Recently Added on the Songs page: "1" the albums grid, anything else (missing too) the songs (docs/modules/recent-albums.md) */
#define RECENTADD_VIEW_TMP "/mnt/data/m1plus/recently-added-view.tmp"
#define LANDSCAPE_FILE \
    "/mnt/data/m1plus/coverflow-landscape" /* "1" = Cover Flow opens in landscape, anything else portrait (the default) */
#define LANDSCAPE_TMP "/mnt/data/m1plus/coverflow-landscape.tmp"
#define CFSORT_FILE \
    "/mnt/data/m1plus/album-order" /* the album order of Cover Flow and Albums: "0" or "0\n" = by album title (stock), anything else or missing = Artist (the default) */
#define CFSORT_TMP "/mnt/data/m1plus/album-order.tmp"
#define TAPETHEME_FILE \
    "/mnt/data/m1plus/cassette-theme" /* the Cassette Mode theme: "1" = Chrome, "2" = Metal (each with an optional newline), anything else or missing = Normal (the default) */
#define TAPETHEME_TMP "/mnt/data/m1plus/cassette-theme.tmp"
#define VINYLREC_FILE \
    "/mnt/data/m1plus/vinyl-record" /* Vinyl Mode's record colour: "1" Cover (with an optional newline), anything else or missing = Black (the default) */
#define VINYLREC_TMP "/mnt/data/m1plus/vinyl-record.tmp"
#define VINYLTHEME_FILE \
    "/mnt/data/m1plus/vinyl-base" /* Vinyl Mode's plinth theme: "1" Snow (with an optional newline), anything else or missing = Graphite (the default) */
#define VINYLTHEME_TMP "/mnt/data/m1plus/vinyl-base.tmp"
#define BG_FILE \
    "/mnt/data/m1plus/appearance-background" /* the background (patch/palette.c): "1" = Tinted, "2" = Light, "3" = Light Auto (07:00 - 18:59; Light is not in the picker), each with an optional newline, anything else or missing = Black (the default) */
#define BG_TMP "/mnt/data/m1plus/appearance-background.tmp"
#define ACCENT_FILE \
    "/mnt/data/m1plus/appearance-accent" /* the accent (patch/palette.c): one digit, the index 0 Neutral (default) .. 6 Champagne, with an optional newline; anything else or missing = Neutral */
#define ACCENT_TMP "/mnt/data/m1plus/appearance-accent.tmp"
#define MENU_FILE \
    "/mnt/data/m1plus/home-menu" /* the menu's visible items in order, one digit (item id) each (patch/menu.c); missing or invalid = the defaults */
#define MENU_TMP "/mnt/data/m1plus/home-menu.tmp"
#define PULLDOWN_FILE \
    "/mnt/data/m1plus/pulldown-tiles" /* the pull-down's tiles: the shown ones' ids in order, optionally '-' and the hidden ones (patch/pulldown.c); missing or invalid = all eight in stock order */
#define PULLDOWN_TMP "/mnt/data/m1plus/pulldown-tiles.tmp"
#define RECENT_FILE \
    CARD_DIR \
    "/recently-played" /* the albums played last, most recent first (patch/recent.c): on the card, like the keys and paths it holds; missing, malformed or no card = none */
#define RECENT_TMP CARD_DIR "/recently-played.tmp"
#define SEARCH_RECENT_FILE \
    "/mnt/data/m1plus/search-history" /* the last searches, newest first, one UTF-8 line each (patch/search.c); missing or malformed = none */
#define SEARCH_RECENT_TMP "/mnt/data/m1plus/search-history.tmp"
#define SHELF_FILE \
    "/mnt/data/m1plus/home-recent-albums" /* the Recently Played shelf: "0" = off, anything else or missing = on (Settings > Home Screen) */
#define SHELF_TMP "/mnt/data/m1plus/home-recent-albums.tmp"
#define DAILY_SET_FILE \
    "/mnt/data/m1plus/home-daily-mix" /* the Daily Mix card: "0" = off, anything else or missing = on (Settings > Home Screen) */
#define DAILY_SET_TMP "/mnt/data/m1plus/home-daily-mix.tmp"
#define SHUFFLE_FILE \
    "/mnt/data/m1plus/playback-shuffle" /* Shuffle (patch/shuffle.c): "1" = on, anything else or missing = off; stock's play mode is never 2 */
#define SHUFFLE_TMP "/mnt/data/m1plus/playback-shuffle.tmp"
#define REBUILD_FILE \
    "/mnt/data/m1plus/covers-rebuild" /* exists while a Settings > Library > Rebuild Covers is requested; Home's cover build (patch/homecover.c) does it and removes it when done */
#define REBUILD_TMP "/mnt/data/m1plus/covers-rebuild.tmp"
#define STAMP_FILE \
    CARD_DIR \
    "/cache-stamp" /* what the library was when Home's last pass finished: "covers <albums> <hash>" and "tracks <albums> <hash>" lines (patch/homecover.c); on the card, like the cache it describes */
#define STAMP_TMP CARD_DIR "/cache-stamp.tmp"
#define KBZH_FILE \
    "/mnt/data/m1plus/keyboard-pinyin" /* the on-screen keyboard's Chinese (Pinyin) layer: "1" = on, anything else or missing = off (Settings > Keyboards; patch/keyboard.c) */
#define KBZH_TMP "/mnt/data/m1plus/keyboard-pinyin.tmp"
#define PCSEARCH_FILE \
    "/mnt/data/m1plus/podcast-online-search" /* Podcast Search: "1" = on, anything else or missing = off (Settings > Library > Podcasts; patch/podcasts.c) */
#define PCSEARCH_TMP "/mnt/data/m1plus/podcast-online-search.tmp"
#define MIX_DIR \
    CARD_DIR \
    "/daily-mix" /* the Daily Mix's own folder inside the card folder (CARD_DIR, patch/covercache.h); made by the writer */
#define MIX_FILE \
    MIX_DIR \
    "/tracks" /* the card's Daily Mix: day, seed, tones, names, the songs' card paths (patch/dailymix.c; tools/pod_mix.py is the model) */
#define MIX_TMP MIX_DIR "/tracks.tmp"
#define MIX_ART_FILE MIX_DIR "/art" /* its card art, 296 x 220 RGB565 with a checksummed header */
#define MIX_ART_TMP MIX_DIR "/art.tmp"
#define DATA_DIR "/mnt/data"
#define SET_DIR \
    "/mnt/data/m1plus" /* the feature settings above; the guard files (KILL_DATA to START_TMP) stay in DATA_DIR */
#define LOG_ENABLE "/mnt/mmc/m1plus-log" /* opt-in: an empty file on the card turns the log on */
#define LOG_FILE "/mnt/mmc/m1plus.log"

#define CLEAR_MS 5000 /* the marker is removed this long after the hook ran */
#define OPEN_FIRST_MS 10 /* the first pod-menu open (1200 before) */
#define OPEN_MS 10 /* later opens, after a window above Home closed (250 before) */
#define RETRY_MS 50 /* Home not opened yet: ask again (250 before) */
#define MAX_TRIES 100 /* 5 s, as 20 x 250 ms before */
#define GRID_ROOT "app_gesture" /* the stock Home grid's content container (home_page.bin) */

/* The hook (tools/pod.py HOME_INIT): installed over home_page_init; runs the stock function first. */
extern int m1plus_home_init(void *win, void *ctx);
extern int stock_home_init_trampoline(void *win, void *ctx);

/* patch/home.c */
extern void home_boot(void *win);
extern int home_off(void);
/* patch/fontregion.c: the CJK forms of the UI language (default.ttf's regional cmaps), from the boot guard */
extern void fr_boot(void);
extern int home_write_atomic(const char *path, const char *tmp,
                             const char *data); /* temp, fsync, rename, directory fsync; 0 = done */
extern int set_read(const char *path, int def); /* a one-character setting file: "x" or "x\n" gives x, else def */
extern void home_menu_opened(void *win, int settings, int entry);
extern void
home_extras_opened(void *win); /* the Extras page: Settings may be opened from it, Shanling Home closes it too */
extern int home_to_grid(void);
extern int home_start(void); /* the "Boot to M1+ Music" setting as Settings > Developer shows it */
extern int home_toggle(void); /* flip it; the new state, or -1 when it could not be saved */
extern int home_restore(void);
extern void home_restore_failed(int restored);

/* patch/minibar.c: the mini player bar of the Home instance of the menu (called by home_menu_opened) */
extern void minibar_start(void *win);

/* patch/recent.c: the Recently Played shelf of the Home instance of the menu (recent_start, called by home_menu_opened) and the albums it shows */
extern void recent_start(void *win);
extern int recent_note(
    void *track); /* the track the player is on: record its album; 1 when the list changed (cheap when it did not) */
extern int recent_rekey(void *albums,
                        unsigned *rows); /* the cover keys checked against a loaded album list (patch/homecover.c's
                                                         scan); rows (SH_TILES) gets the shelf's albums' indices, the count returned */
extern void recent_refresh(void); /* the list changed under a live shelf (the mini bar's tick): show it */
extern int recent_setting(void); /* the Settings > Home Screen switch: 1 on (the default) */
extern void menu_shelf(void *win,
                       int on); /* patch/menu.c: show or hide the shelf and move the rows (the list keeps its place) */
extern void menu_daily(void *win,
                       int on); /* patch/menu.c: the same for the Daily Mix section, which sits above the shelf */

/* patch/dailymix.c: the Daily Mix card of the Home instance of the menu (dailymix_start, called by home_menu_opened) and its Settings > Home Screen rows */
extern void dailymix_start(void *win);

/* patch/homecover.c: the background cover build and its progress line on the Home instance of the menu (called by home_menu_opened) */
extern void homecover_start(void *win);
extern void homecover_stamp_drop(
    int mask); /* the cache stamp forgets the covers (1) and / or the track lengths (2): Home's next open shows the waiting pill */
extern void
homecover_rebuild_asked(void); /* Rebuild Covers was confirmed: the pill's stop no longer holds Home's build back */
extern void
homecover_cache_open(void *win,
                     int page); /* the Cover Cache page is up: count the cache folder in steps (patch/homecover.c) */
extern int homecover_tappable(
    int idx); /* the Cover Cache page's No art (2) / Missing (3) row opens a list: counted and not zero */
extern int homecover_list_open(int idx); /* that list (patch/covlist.c); -1 when the row is not tappable */
extern int covlist_open(
    int kind, const unsigned short *idx,
    unsigned n); /* patch/covlist.c: kind 0 No Art, 1 Missing Covers; idx = display positions of the album list */
extern void homecover_stat(
    int idx, char *buf,
    unsigned n); /* a value of that page: 0 Albums, 1 Covers, 2 No art, 3 Missing, 4 Old files, 5 Size, 6 Status */
extern void setfiles_open(void); /* the Settings Files page is opening: read the files once (patch/setfiles.c) */
extern void setfiles_stat(int idx, char *buf, unsigned n); /* a row's text as read: 0..24 the files */
extern int homecover_clear(
    void); /* Settings > Developer > Clear Cover Cache, after its confirm: 1 under way, 0 the cover worker is busy */
extern void pod_toast(const char *text); /* patch/shuffle.c */
extern int pod_play_mode(
    void); /* patch/shuffle.c: the play mode as shown (2 while Shuffle is on, whatever stock's mode is), else stock's */
extern int pod_shuffle_on(void); /* the Shuffle flag */
extern int
pod_set_shuffle(int on); /* Shuffle on / off, the repeat mode kept; 0 refused (the stock message box was shown) */
extern void pod_set_mode_for_queue(
    int mode); /* patch/shuffle.c: pod_set_mode right before a queue load: the flag only, the queue being replaced is not reordered */
extern void
pod_set_in_order_for_queue(void); /* patch/shuffle.c: pod_set_in_order right before a queue load: the flag only */
extern int pod_clear_upnext(void); /* patch/shuffle.c: Clear: 1 done, 0 nothing after the position, -1 refused */
extern int pod_clear_ready(void); /* patch/shuffle.c: Clear can run (kill switch off, libcstl as pinned) */
extern void pod_set_repeat(int mode); /* the stock repeat mode (0 off, 3 all, 1 one), the Shuffle flag kept */
/* patch/shuffle.c: rows (a deque of stSongInfo, copied) into the playing queue right after the playing song (after == 0) or at its end, under the payload lock, with Shuffle's
 * saved order kept valid. POD_INSERT_OK, or nothing changed: _IDLE (no rows, nothing playing), _FULL (past SHUFFLE_MAX songs), _MEMORY (no memory for the order), _DLNA (the DLNA renderer service runs). */
#define POD_INSERT_OK 1
#define POD_INSERT_IDLE 0
#define POD_INSERT_FULL (-1)
#define POD_INSERT_MEMORY (-2)
#define POD_INSERT_DLNA (-3)
extern int pod_queue_insert(void *rows, int after);
extern void menu_arrange(void *win,
                         int extras); /* patch/menu.c: the rows as the saved list says (the scroll offset is clamped) */
extern int dailymix_setting(void); /* the Settings > Home Screen switch: 1 on (the default) */
extern int dailymix_toggle(void); /* flip it, saved atomically; the new state, or -1 when it could not be saved */
extern void dailymix_regen(
    void); /* Regenerate Daily Mix: today's mix is made again with a new seed, when the Home menu is in front */
extern int dailymix_can_regen(
    void); /* Regenerate can make a mix: the switch is on and the last job did not find the library too small */
extern int recent_toggle(void); /* flip it, saved atomically; the new state, or -1 when it could not be saved */
extern int
kb_zh_setting(void); /* patch/keyboard.c: Settings > Keyboards > Chinese (Pinyin): 1 on, 0 off (the default) */
extern int kb_zh_toggle(void); /* flip it, saved atomically; the new state, or -1 when it could not be saved */
extern int pcsearch_setting(
    void); /* patch/podcasts.c: Settings > Library > Podcasts > Podcast Search: 1 on, 0 off (the default) */
extern int pcsearch_toggle(void); /* flip it, saved atomically; the new state, or -1 when it could not be saved */
extern int
battpct_setting(void); /* patch/battery.c: Settings > Home Screen > Battery Percentage: 1 on, 0 off (the default) */
extern int battpct_toggle(void); /* flip it, saved atomically; the new state, or -1 when it could not be saved */

/* patch/m1plus.c (stages with the home feature) */
extern int m1plus_open_entry(void);
