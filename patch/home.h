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
#define BAD_NOTE "/mnt/data/m1plus-bad" /* written when a marker was found at boot */
#define START_FILE "/mnt/data/m1plus-start" /* "1" = start in M1+ Music (default when missing), "0" = Shanling */
#define ALBUMS_FILE \
    "/mnt/data/m1plus/albums-view" /* "1" = the Albums grid (default when missing, ALBUMS_DEFAULT_GRID), "0" = the list mode of the same page */
#define ALBUMS_SORT_FILE \
    "/mnt/data/m1plus/albums-sort" /* the Albums page's order (its "..." card): "0" Title, "1" Artist, "2" Recently Added, "3" Year, or "a" .. "d" for the same order in its other direction; missing or anything else is Artist (cc_sort_mode, cc_sort_rev) */
#define ARTISTS_SORT_FILE \
    "/mnt/data/m1plus/artists-sort" /* the Artists page's order (its "..." card): "a" Name Z-A; missing or anything else Name A-Z (patch/artists.c) */
#define GENRES_SORT_FILE "/mnt/data/m1plus/genres-sort" /* the same for the Genres page */
#define COMPOSERS_SORT_FILE "/mnt/data/m1plus/composers-sort" /* and the Composers page */
#define SONGS_SORT_FILE \
    "/mnt/data/m1plus/songs-sort-rev" /* the Songs page's direction of its Title, File Name and Format orders (its Sort card): "a" Z-A; missing or anything else A-Z (patch/songs.c); the order itself is the stock sort_flag */
#define FOLDERS_SORT_FILE \
    "/mnt/data/m1plus/folders-sort" /* the Folders page's order (its "..." card, every level): "0" Name, "1" Date Modified, "2" Type, or "a" "b" "c" for the same order reversed (Z-A, Oldest First); missing or anything else Name A-Z (patch/folders.c) */
#define PLAYLISTS_FILE \
    "/mnt/data/m1plus/playlists-view" /* the Playlists page's mode, as ALBUMS_FILE: "1" the grid (default), "0" the list */
#define PLAYLISTS_SORT_FILE \
    "/mnt/data/m1plus/playlists-sort" /* the Playlists page's name order (its "..." card): "a" Z-A; missing or anything else A-Z (patch/playlists.c) */
#define RECENTADD_VIEW_FILE \
    "/mnt/data/m1plus/recently-added-view" /* Recently Added on the Songs page: "1" the albums grid, anything else (missing too) the songs (docs/modules/recent-albums.md) */
#define LANDSCAPE_FILE \
    "/mnt/data/m1plus/coverflow-landscape" /* "1" = Cover Flow opens in landscape, anything else portrait (the default) */
#define VOLKEYS_FILE \
    "/mnt/data/m1plus/coverflow-volume-keys" /* "1" = the volume keys step Cover Flow, anything else or missing off (the default) */
#define OLD_ORDER_FILE \
    "/mnt/data/m1plus/album-order" /* the retired Settings > Library > Album Order ("0" Title, else Artist): cc_sort_mode moves it into ALBUMS_SORT_FILE once and deletes it */
#define TAPETHEME_FILE \
    "/mnt/data/m1plus/cassette-theme" /* the Cassette Mode theme: "0" = Normal, "1" = Chrome, "2" = Metal, "3" = Auto, by the track's quality (each with an optional newline), anything else or missing = Auto (the default) */
#define IDLE_FILE \
    "/mnt/data/m1plus/nowplaying-idle" /* where Now Playing's timed view goes: "1" Cassette, "2" Vinyl (each with an optional newline), anything else or missing = Album Cover (the default; docs/modules/bigcover.md "Idle view") */
#define LYRSIZE_FILE \
    "/mnt/data/m1plus/nowplaying-lyrics-size" /* the lyrics page's text size: "0" Small (22 px), "1" Medium (26), "2" Large (30; also a missing or invalid file); docs/modules/lyrics.md "Text size" */
#define NPPOS_FILE \
    "/mnt/data/m1plus/nowplaying-position" /* "1" = Now Playing shows the queue position (5/10) between the times, anything else or missing off (the default); docs/modules/nowplaying.md */
#define NPSHRINK_FILE \
    "/mnt/data/m1plus/nowplaying-shrink" /* "0" = the Now Playing cover stays full size while paused, anything else or missing: it shrinks (a spring; the default); docs/modules/nowplaying.md */
#define SWAPKEYS_FILE \
    "/mnt/data/m1plus/buttons-swap" /* "1" = the previous and next buttons are swapped, anything else or missing off (the default); docs/modules/keyspower.md */
#define VOLTAP_FILE \
    "/mnt/data/m1plus/volume-tap" /* "0" = the status bar tap does not open the Volume page, anything else or missing on (the default); docs/modules/volume.md */
#define VINYLREC_FILE \
    "/mnt/data/m1plus/vinyl-record" /* Vinyl Mode's record colour: "1" Cover (with an optional newline), anything else or missing = Black (the default) */
#define VINYLTHEME_FILE \
    "/mnt/data/m1plus/vinyl-base" /* Vinyl Mode's plinth theme: "1" Snow (with an optional newline), anything else or missing = Graphite (the default) */
#define BG_FILE \
    "/mnt/data/m1plus/appearance-background" /* the background (patch/palette.c): "1" = Tinted, "2" = Light, "3" = Light Auto (07:00 - 18:59; Light is not in the picker), each with an optional newline, anything else or missing = Black (the default) */
#define LK_LAYOUT_FILE \
    "/mnt/data/m1plus/lockscreen-layout" /* the lock screen layout (patch/lockscreen.c): "1" mini player, anything else or missing = the large cover (the default) */
#define ACCENT_FILE \
    "/mnt/data/m1plus/appearance-accent" /* the accent (patch/palette.c): one digit, the index 0 Neutral (default) .. 6 Champagne, with an optional newline; anything else or missing = Neutral */
#define AZRAIL_FILE \
    "/mnt/data/m1plus/appearance-index-rail" /* Index Rail (patch/azlist.c): "1" = the A-Z rail and its bubble on the A-Z lists, "0" = off, anything else or missing = on (the default) */
#define AZHEAD_FILE \
    "/mnt/data/m1plus/appearance-headers" /* Section Headers (patch/azlist.c): "0" = no section letters and no pinned header, anything else or missing = on (the default) */
#define MENU_FILE \
    "/mnt/data/m1plus/home-menu" /* the menu's visible items in order, one digit (item id) each (patch/menu.c); missing or invalid = the defaults */
#define PULLDOWN_FILE \
    "/mnt/data/m1plus/pulldown-tiles" /* the pull-down's tiles: the shown ones' ids in order, optionally '-' and the hidden ones (patch/pulldown.c); missing or invalid = all eight in stock order */
#define PDLABELS_FILE \
    "/mnt/data/m1plus/pulldown-labels" /* Control Labels (patch/pulldown.c): "0" = hide the pull-down's tile captions, anything else or missing = shown (the default) */
#define RECENT_FILE \
    CARD_DIR \
    "/recently-played" /* the albums played last, most recent first (patch/recent.c): on the card, like the keys and paths it holds; missing, malformed or no card = none */
#define PINS_FILE \
    CARD_DIR \
    "/home-pins" /* the albums, playlists and songs pinned at the top of Home, newest first (patch/pins.c): on the card, like the keys and paths it holds; missing, malformed or no card = none */
#define SEARCH_RECENT_FILE \
    "/mnt/data/m1plus/search-history" /* the last searches, newest first, one UTF-8 line each (patch/search.c); missing or malformed = none */
#define SHELF_FILE \
    "/mnt/data/m1plus/home-recent-albums" /* the Recently Played shelf: "0" = off, anything else or missing = on (Settings > Home Screen) */
#define DAILY_SET_FILE \
    "/mnt/data/m1plus/home-daily-mix" /* the Daily Mix card: "0" = off, anything else or missing = on (Settings > Home Screen) */
#define SHUFFLE_FILE \
    "/mnt/data/m1plus/playback-shuffle" /* Shuffle (patch/shuffle.c): "1" = songs, "2" = albums, anything else or missing = off; stock's play mode is never 2 */
#define REBUILD_FILE \
    "/mnt/data/m1plus/covers-rebuild" /* exists while a Settings > Library > Rebuild Covers is requested; Home's cover build (patch/homecover.c) does it and removes it when done */
#define AREBUILD_FILE \
    "/mnt/data/m1plus/artists-rebuild" /* exists while a rebuild of the artist photos is requested (Settings > Library > Rebuild Artist Photos writes it); Home's build (patch/homecover.c) checks every artist again and removes it when done */
#define STAMP_FILE \
    CARD_DIR \
    "/cache-stamp" /* what the library was when Home's last pass finished: "covers <albums> <hash>" and "tracks <albums> <hash>" lines (patch/homecover.c); on the card, like the cache it describes */
#define KBZH_FILE \
    "/mnt/data/m1plus/keyboard-pinyin" /* the on-screen keyboard's Chinese (Pinyin) layer: "1" = on, anything else or missing = off (Settings > General > Keyboards; patch/keyboard.c) */
#define KBFR_FILE \
    "/mnt/data/m1plus/keyboard-french" /* the French (AZERTY) layer: "1" = on, anything else or missing = off (Settings > General > Keyboards; patch/keyboard.c) */
#define PCSEARCH_FILE \
    "/mnt/data/m1plus/podcast-online-search" /* Podcast Discover: "0" = off, anything else or missing = on (Settings > Library > Podcasts; patch/podcasts.c) */
#define PCDIR_FILE \
    "/mnt/data/m1plus/podcast-directory" /* Podcast Directory: "1" = Podcast Index, anything else or missing = Apple Podcasts (Settings > Library > Podcasts; patch/podcasts.c) */
#define WIFINET_FILE \
    "/mnt/data/m1plus/wifi-networks" /* the saved networks a stock 2.9 supplicant cannot read (WPA3, Enhanced Open, Enterprise): network={} blocks the Wi-Fi page writes (patch/wifipage.c) and /usr/bin/wifi_connect.sh adds to the copy of the configuration only the newer supplicant reads */
#define SCROBBLE_FILE \
    "/mnt/data/m1plus/scrobbling" /* the scrobble log: "1" = on, anything else or missing = off (Settings > Library; patch/scrobble.c) */
#define SCROBBLE_AUTO_FILE \
    "/mnt/data/m1plus/scrobble-auto" /* Settings > Library > Scrobbling > Auto Upload: "1" = on, anything else or missing = off (patch/scrobble.c sa_*) */
#define MIX_DIR \
    CARD_DIR \
    "/daily-mix" /* the Daily Mix's own folder inside the card folder (CARD_DIR, patch/covercache.h); made by the writer */
#define MIX_FILE \
    MIX_DIR \
    "/tracks" /* the card's Daily Mix: day, seed, tones, names, the songs' card paths (patch/dailymix.c; tools/pod_mix.py is the model) */
#define MIX_ART_FILE MIX_DIR "/art" /* its card art, 296 x 220 RGB565 with a checksummed header */
#define DATA_DIR "/mnt/data"
#define SET_DIR \
    "/mnt/data/m1plus" /* the feature settings above; the guard files (KILL_DATA to START_FILE ".tmp") stay in DATA_DIR */
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
#define HOME_TMP_MAX 416 /* a path of up to 411 bytes (the longest stack paths are 400) plus ".tmp" and the NUL */
extern int
home_tmp_path(char *out,
              const char *path); /* path + ".tmp" into out (HOME_TMP_MAX bytes); 0, or -1 when it does not fit */
extern int home_write_atomic(const char *path,
                             const char *data); /* path + ".tmp", fsync, rename, directory fsync; 0 = done */
extern int home_set_digit(const char *file, int v,
                          int max); /* "v\n" atomically for 0 <= v <= max <= 9: v, or -1 (out of range, not written) */
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

extern void menu_pins(void *win,
                      int on); /* patch/menu.c: the same for the Home pins (patch/pins.c), which sit above every row */
extern void
pins_start(void *win); /* patch/pins.c: the Home pins of the Home instance of the menu (called by home_menu_opened) */

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
                     int page); /* the Cache page is up: count the cache folder in steps (patch/homecover.c) */
extern int
homecover_tappable(int idx); /* the Cache page's No art (2) / Missing (3) row opens a list: counted and not zero */
extern int homecover_list_open(int idx); /* that list (patch/covlist.c); -1 when the row is not tappable */
extern int covlist_open(
    int kind, const unsigned short *idx,
    unsigned n); /* patch/covlist.c: kind 0 No Art, 1 Missing Covers; idx = display positions of the album list */
extern void homecover_stat(
    int idx, char *buf,
    unsigned n); /* a value of that page: 0 Albums, 1 Covers, 2 No art, 3 Missing, 4 Old files, 5 Size, 6 Status */
extern void setfiles_open(void); /* the Settings Files page is opening: read the files once (patch/setfiles.c) */
extern void setfiles_stat(int idx, char *buf, unsigned n); /* a row's text as read: 0..28 the rows (patch/setfiles.c) */
extern int setfiles_present(int idx); /* the row's file was there at its last read: tappable (patch/setfiles.c) */
extern int setfiles_delete(int idx); /* unlinks a setting file, reads its row again; 0 when gone (patch/setfiles.c) */
extern int
setfiles_old_count(void); /* Unsupported Files: the retired files there at the last check (patch/setfiles.c) */
extern unsigned setfiles_old_n(void); /* the retired entries: name, then .tmp sibling, in order */
extern int setfiles_old_present(unsigned k); /* the retired entry k was there at the last check */
extern int setfiles_old_name(unsigned k, char *out, unsigned n); /* entry k's path into out; 0 when out of range */
extern int setfiles_old_delete(unsigned k); /* unlinks entry k and checks it again; 0 when gone */
extern int setfiles_old_delete_all(void); /* every retired entry unlinked; 0 when none is left */
extern int setfiles_reset_all(
    void); /* Reset All Settings: every entry of the settings folder and the retired ones unlinked; 0 when none is left (patch/setfiles.c) */
extern int pod_confirm(const char *s); /* the confirm dialog's Yes (patch/m1plus.c) */
extern int pod_confirm_dialog(
    void *info); /* the confirm dialog over the page with the dim scrim: its raw result (patch/m1plus.c) */
extern int homecover_clear(
    void); /* Settings > Developer > Clear Cover Cache, after its confirm: 1 under way, 0 the cover worker is busy */
extern void pod_toast(const char *text); /* patch/shuffle.c */
extern void pod_toast_ms(const char *text, int ms); /* patch/shuffle.c: the same message box for ms milliseconds */
extern unsigned pod_rand(unsigned n); /* patch/shuffle.c: 0 .. n - 1, the shuffle generator (seeded once) */
extern void pod_set_mode(
    int mode); /* patch/shuffle.c: the stock play mode, set as the Play settings page does (the queue is reordered now) */
extern void pod_set_in_order(void); /* patch/shuffle.c: Shuffle and Repeat one become List play */
extern int pod_home_open(int id); /* patch/m1plus.c: a stock Home destination through the dispatcher */
extern void pod_page_refresh(int index); /* patch/m1plus.c: the page's values are read again */
extern int pod_open_lock(void); /* patch/m1plus.c */
extern int pod_open_settings(void); /* patch/m1plus.c: open_page(POD_SETTINGS_PAGE); 0 once its window is up */
extern int pod_open_peq(void); /* patch/m1plus.c: open_page(POD_PEQ_PAGE) */
extern int
pod_open_psgain(void); /* patch/m1plus.c: open_page(POD_PSGAIN_PAGE), the Gain picker; 0 once its window is up */
extern int pod_open_psmaxvol(
    void); /* patch/m1plus.c: open_page(POD_PSMAXVOL_PAGE), the Max Volume slider page; 0 once its window is up */
extern int
pod_open_psvolume(void); /* patch/m1plus.c: open_page(POD_PSVOLUME_PAGE), Volume & Sound; 0 once its window is up */
extern int
pod_open_plcover(void); /* patch/m1plus.c: open_page(POD_PLCOVER_PAGE) (patch/plcpage.c); 0 once its window is up */
extern int pod_open_volume(void); /* patch/m1plus.c: open_page(POD_VOLUME_PAGE); 0 once its window is up */
extern void *
pd_window_open(const char *asset); /* patch/pulldown.c: window_open, the page in front recorded as the opener */
extern int pod_open_wifitransfer(void); /* patch/m1plus.c: open_page(POD_WIFITRANSFER_PAGE); 0 once its window is up */
extern int pod_open_sleeptimer(void); /* patch/m1plus.c: open_page(POD_SLEEPTIMER_PAGE); 0 once its window is up */
extern int pod_open_btcodec(
    void); /* patch/m1plus.c: open_page(POD_BTCODEC_PAGE), the Audio Codec picker; 0 once its window is up */
extern int pod_open_playset(void); /* patch/m1plus.c: open_page(POD_PLAYSET_PAGE); 0 once its window is up */
extern int pod_open_peqlib(void); /* patch/m1plus.c: open_page(POD_PEQLIB_PAGE) */
extern int pod_open_peqpage(void); /* patch/m1plus.c: open_page(POD_PEQP_PAGE) */
extern int pod_confirm_code(
    const char
        *text); /* patch/m1plus.c: the stock confirm dialog's raw result (CONFIRM_YES 0xa, btn_cancel 4, else 0) */
extern int pod_play_mode(
    void); /* patch/shuffle.c: the play mode as shown (2 while Shuffle is on, whatever stock's mode is), else stock's */
extern int pod_shuffle_on(void); /* the Shuffle flag */
extern int pod_shuffle_kind(void); /* patch/shuffle.c: 0 off, 1 songs, 2 albums */
extern int pod_set_shuffle_kind(
    int kind); /* patch/shuffle.c: Shuffle to a kind (0 off, 1 songs, 2 albums); 0 refused, as pod_set_shuffle */
extern int
pod_set_shuffle(int on); /* Shuffle on / off, the repeat mode kept; 0 refused (the stock message box was shown) */
extern void pod_set_mode_for_queue(
    int mode); /* patch/shuffle.c: pod_set_mode right before a queue load: the flag only, the queue being replaced is not reordered */
extern void
pod_set_in_order_for_queue(void); /* patch/shuffle.c: pod_set_in_order right before a queue load: the flag only */
extern int pod_clear_upnext(void); /* patch/shuffle.c: Clear: 1 done, 0 nothing after the position, -1 refused */
extern void (*cstl_pop_back(void))(
    void *); /* patch/shuffle.c: libcstl's deque_pop_back when the library is the pinned one, else NULL */
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
/* patch/shuffle.c: move the Up Next row at absolute queue index `from` to index `to` (the rows between shift by one), or remove the row at `i`; in place, under the payload lock, Shuffle's
 * saved order kept valid. Both indices must be after the play position and inside the queue; from == to changes nothing. POD_EDIT_OK, or nothing changed: _RANGE (an index not in Up Next, nothing
 * playing), _DLNA (the DLNA renderer service runs), _LIBCSTL (remove: libcstl is not the pinned one). The UI offers the actions while pod_clear_ready() (the same conditions). */
#define POD_EDIT_OK 1
#define POD_EDIT_RANGE (-1)
#define POD_EDIT_DLNA (-2)
#define POD_EDIT_LIBCSTL (-3)
extern int pod_queue_move(unsigned from, unsigned to);
extern int pod_queue_remove(unsigned i);
extern void menu_arrange(void *win,
                         int extras); /* patch/menu.c: the rows as the saved list says (the scroll offset is clamped) */
extern int dailymix_setting(void); /* the Settings > Home Screen switch: 1 on (the default) */
extern int dailymix_toggle(void); /* flip it, saved atomically; the new state, or -1 when it could not be saved */
extern void dailymix_regen(
    void); /* Regenerate Daily Mix: today's mix is made again with a new seed, when the Home menu is in front */
extern int dailymix_can_regen(
    void); /* Regenerate can make a mix: the switch is on and the last job did not find the library too small */
extern int recent_toggle(void); /* flip it, saved atomically; the new state, or -1 when it could not be saved */
extern int kb_zh_setting(
    void); /* patch/keyboard.c: Settings > General > Keyboards > Chinese (Pinyin): 1 on, 0 off (the default) */
extern int
np_pos_setting(void); /* Settings > Now Playing > Track Position: 1 on, 0 off (the default) (patch/nowplaying.c) */
extern int np_pos_toggle(void); /* flip it, saved atomically; the new state, or -1 when it could not be saved */
extern int
np_shrink_setting(void); /* Settings > Now Playing > Shrink on Pause: 1 on (the default), 0 off (patch/nowplaying.c) */
extern int np_shrink_toggle(void); /* flip it, saved atomically; the new state, or -1 when it could not be saved */
extern int kb_fr_setting(void); /* ... > French (AZERTY): 1 on, 0 off (the default) */
extern int kb_fr_toggle(void); /* flip it, saved atomically; the new state, or -1 when it could not be saved */
extern int kb_zh_toggle(void); /* flip it, saved atomically; the new state, or -1 when it could not be saved */
extern int pcsearch_setting(
    void); /* patch/podcasts.c: Settings > Library > Podcasts > Podcast Discover: 1 on (the default), 0 off */
extern int pcsearch_toggle(void); /* flip it, saved atomically; the new state, or -1 when it could not be saved */
extern int pcdir_setting(
    void); /* patch/podcasts.c: Settings > Library > Podcasts > Podcast Directory: PCDIR_APPLE (the default) or PCDIR_INDEX */
extern int
pcdir_set(int dir); /* choose one, saved atomically; the choice, or -1 when it is not one or could not be saved */
#define PCDIR_APPLE 0
#define PCDIR_INDEX 1
extern int
battpct_setting(void); /* patch/battery.c: Settings > Battery > Battery Percentage: 1 on, 0 off (the default) */
extern int battpct_toggle(void); /* flip it, saved atomically; the new state, or -1 when it could not be saved */
extern int azrail_setting(void); /* patch/azlist.c: Settings > Library > Index Rail: 1 on (the default), 0 off */
extern int azrail_toggle(void); /* flip it, saved atomically; the new state, or -1 when it could not be saved */
extern int azhead_setting(void); /* patch/azlist.c: Settings > Library > Section Headers: 1 on (the default), 0 off */
extern int azhead_toggle(void); /* flip it, saved atomically; the new state, or -1 when it could not be saved */
extern int
pd_labels_setting(void); /* patch/pulldown.c: Settings > Appearance > Control Labels: 1 on (the default), 0 off */
extern int pd_labels_toggle(void); /* flip it, saved atomically; the new state, or -1 when it could not be saved */

/* patch/m1plus.c (stages with the home feature) */
extern int m1plus_open_entry(void);
