/* Entry points of the pages and modules that have no header of their own: each function is declared here once, grouped by the
 * file that defines it. (Not pages.h: tools/pod.py generates a pages.h of that name into the build directory.)
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 */
#pragma once
#include "libsrc.h"

/* patch/songs.c */
int songs_open(void); /* Songs, the library as one list with sections and a jump rail */
int songs_open_list(int home); /* another stock song list (Favourites ...) on the same page; arg = its Home tile */
int songs_open_artist(void *artist, unsigned scope);
void *songs_artist_list(
    void *artist,
    unsigned
        scope); /* the artist's (or composer's) songs through the stock queries (no page); NULL when there is no All songs row */
int songs_play_artist(
    void *artist, unsigned scope,
    int how); /* Play (SO_IN_ORDER) / Shuffle (SO_SHUFFLE) on the artist's (or composer's) songs; -1 when nothing plays */
int songs_open_src(const lib_src_t *src, int which, const char *title);
int songs_open_src_in(
    const lib_src_t *src, int which, void *scope,
    const char *title); /* the source's tracks of a row (the artist's All Songs, a playlist's) on our Songs page */
int songs_open_genre(const char *name, int unknown);
int songs_open_genre_split(
    const char *name,
    int unknown); /* a genre row the genre split made (patch/genresplit.c); -1 when the page did not open */
void songs_genre_record(
    const char *name,
    int unknown); /* the browsing record a stock genre row tap leaves (class 0xff09, the name, the Unknown byte) */
int songs_open_playlist(int id, const char *name); /* our Songs page on a playlist; -1 when it did not open */

/* patch/folders.c */
int folders_open(
    int home); /* Folders, the card's folders and audio files; a window that will not open leaves the stock folder_page through the Home tile home */

/* patch/albumpage.c */
int album_open_src(const lib_src_t *src, unsigned cls, void *row); /* the album page of a source's album */
int album_open(
    unsigned cls,
    void *
        row); /* our album page on an album row; 0 opened, -1 not tried, -2 tried and left (the tracks' query replaced the list) */
int album_page_up(void); /* its window is not destroyed yet */
void ab_relight(
    void); /* the open cover-tinted pages tint again (patch/albumpage.c, nowplaying.c, podcasts.c; the Daily Mix page, whose art is made once, keeps what it was opened with) */
int ab_has_tone(
    void); /* the page shows a cover's tone now (the album page when tinted; the Show page, not the shows list or an episode) */

/* patch/nowplaying.c */
/* "file://" and any path np_cover_file answers (a book's cover: the Audiobooks root, a folder and a file name of BK_FILE each) */
#define NP_COVER_URL 320
const char *
np_cover_file(int *busy); /* demo's cover file of the playing track, NULL for none; busy while demo makes it */
/* the book's cover file of the playing audiobook part (a plain path), NULL for another track or a book with none; np_cover_file answers it when stock has no picture */
const char *np_book_cover(void);
unsigned np_file_key(const char *path); /* a hash of the picture file, 0 if unreadable */
void np_relight(void);
void *np_window(void); /* Now Playing's window, 0 when it has none (patch/idlelyrics.c) */
/* An episode's or a part's skip and speed buttons (the Control Center's page 2 uses them too): np_spoken_seek(fwd) seeks 30 s on / 15 s back as Now Playing's buttons do (1 when the player had a length to seek in); np_speed_step()
 * saves and applies the show's or the book's next speed (the player restarts at its place as stock's Multiple Speed handlers do), 0 when it could not be saved (the toast is shown) */
int np_spoken_seek(int fwd);
int np_speed_step(void);
unsigned np_idle_color(void); /* the window's colour (a color_t word) after the cover's tone is looked at again */
void np_on_dark(
    void); /* screen off (patch/battery.c bp_light_off): pause stock's 500 ms timer and title/artist marquees */
void np_on_wake(
    void); /* screen on (patch/battery.c bp_light_on): refresh and resume stock's timer and marquees before paint */

/* patch/idlelyrics.c */
int idlelyrics_open_idle(
    void); /* Now Playing's idle timer: 0 once the page is up (or already open), -1 when it could not open (nothing left of it) */
int idlelyrics_up(void); /* 1 while the page is open */

/* patch/playmore.c */
int pm_goto(
    int artist); /* the Control Center's Go to Artist (1) / Go to Album (0) for the playing track: 1 once a page was opened or the Subsonic miss was told, 0 nothing opened */

/* patch/queuepage.c */
int queue_open(void); /* our Queue page; 0 once it is open, else the stock drawer should open */

/* patch/bigcover.c */
int idle_choice(
    void); /* Idle Display: 0 Off (stock's Cover mode byte off), 1 Album Cover, 2 Cassette, 3 Vinyl, 4 Lyrics, 5 VU Meter; read live */
int idle_set(
    int choice); /* choose it, saved (the byte through stock's save, the destination atomically); the choice or -1 */

/* patch/tape.c */
int tape_open(void);
int tape_open_idle(
    void); /* 0 once the page is up (or already open), -1 when it could not open; a tap on a page it opened closes it */
int tape_theme(void); /* the saved theme, 0 Normal (the default), 1 Chrome, 2 Metal, 3 Auto (by the track's quality) */
int tape_theme_set(int theme); /* choose it, saved atomically; the theme or -1 */
int tape_badge(
    void *
        rec); /* the sticker the playing record's quality earns (the cassette's rule, one mclGetInfo): 0 none, 1 HI-RES, 2 DSD; Now Playing's info page shows it too */

/* patch/vinyl.c */
int vinyl_open(void);
int vinyl_open_idle(void); /* the same for Vinyl Mode (a tap on the record closes) */
int vinyl_record(void); /* the saved record colour, 0 Black (the default) .. VN_RECS - 1 */
int vinyl_record_set(int rec); /* choose it, saved atomically; the colour or -1 */
int vinyl_theme(void); /* the saved plinth theme, 0 Graphite (the default), 1 White */
int vinyl_theme_set(int theme); /* choose it, saved atomically; the theme or -1 */

/* patch/vupage.c (docs/modules/vu.md) */
int vupage_open(void); /* the VU Meter page: 0 once it is up (or already open), -1 when it could not open */
int vupage_open_idle(void); /* the same for Now Playing's idle timer (a tap on the page closes it) */
void vupage_boot(void); /* demo starts: a level-tap mark left by an earlier run is removed */
void rd_icy_boot(void); /* demo starts: a radio ICY metadata mark left by an earlier run is removed */

/* patch/libload.c (docs/modules/libload.md) */
int lib_deque_swap(void *a, void *b); /* two deques' contents exchanged in place; 0 when refused (nothing changed) */
void *lib_take_list(
    void *
        list); /* a deque of our own that takes the stock list's records (the list is left empty); a copy when refused */

/* patch/filetime.c */
int ft_statx(int dirfd, const char *path, int flags, unsigned mask,
             void *buf); /* the statx syscall (demo imports none) */

/* patch/ipod.c */
int ipod_open(void); /* the virtual iPod Classic, a fullscreen page with a touch click wheel */
int books_open(void); /* patch/bkpage.c: the books in Audiobooks on the card and their parts */
int books_goto(
    const char *
        path); /* the Control Center's shortcut: the Library (path 0) or the Book level of the book path is in; 0 once the page is up, -1 when it could not open */
unsigned ip_fit(void *canvas, unsigned *s, int maxw); /* the wide string cut with an ellipsis to maxw px */

/* patch/ipod_cf.c */
int ipcf_open(void *win), ipcf_busy(void), ipcf_tick(void *list, unsigned count);
int ipcf_start(void *list, unsigned count);
int ipcf_flipping(void), ipcf_flip_tick(void), ipcf_going(void), ipcf_gone(void), ipcf_go_tick(void);
void ipcf_go_open(void *list, unsigned count, int sel), ipcf_go_close(int quiet), ipcf_rush(void),
    ipcf_go_card(int row), ipcf_paint_go(void *canvas, void *list, unsigned count, void *style);
void ipcf_close(void), ipcf_goto(int sel), ipcf_flip_open(void *list, unsigned count, int sel),
    ipcf_flip_close(int row);
void ipcf_flip_settle(void);
void ipcf_paint(void *canvas, void *list, unsigned count, void *style), ipcf_paint_flip(void *canvas, int sel_row),
    ipcf_paint_bg(void *canvas);
const char *ipcf_album(void), *ipcf_artist(void);
unsigned *ipcf_face(void);
int ipcf_face_ok(void);
void ipcf_face_done(int ok);

/* patch/lockscreen.c */
int lkwp_open(void); /* the Lock Screen's Wallpaper picker, our page; -1 when it did not open */
int lk_layout(void); /* the saved lock screen layout, 0 Large Cover (the default), 1 Mini Player */
int lk_layout_set(int layout); /* choose it, saved atomically; the layout or -1 */
int lk_enabled(void); /* stock's lock screen switch (the byte screensaver_mode): 1 on */
int lk_enabled_toggle(void); /* flip it as stock's switch does (byte, then [SYSSET] SCREENSAVER); the new state */
int lk_time(void); /* stock's lock screen clock switch (the byte screensaver_timeshow): 1 on */
int lk_time_toggle(void); /* flip it as stock's switch does (byte, then [SYSSET] SSAVERTIMESHOW); the new state */
void lk_on_dark(
    void); /* screen off (patch/battery.c bp_light_off): pause stock's 20 ms lock screen refresh while dark */
void lk_on_wake(void); /* screen on (patch/battery.c bp_light_on): refresh the lock screen synchronously before paint */

/* patch/power.c */
void *
m1plus_check_cpumem(void *arg); /* payload hook 41: disable stock's 6 s drop_caches=3 thread (stock on kill switch) */

/* patch/relnotes.c */
int lockinfo_open(
    void); /* the Lock Screen's Custom Wallpaper instructions, a Release Notes page; -1 when it did not open */
int relnotes_open(void); /* the offered release's notes, a page of their own */
int cardsrc_open(
    void); /* Card Script > View Script: the first 16 KiB of the card's m1plus-run.sh, a Release Notes page; -1 when it did not open */
int cardlog_open(
    void); /* Developer > Tools > Card Script > View Log: the last 16 KiB of /tmp/m1plus-run.log, a Release Notes page; -1 when it did not open */

/* patch/cardrun.c: Developer > Tools > Card Script (the runner /usr/bin/m1plus-run started and stopped by hand, its log) */
int cardrun_pid(void); /* the live run's pid, 0 when none */
void cardrun_status_text(char *buf, unsigned n); /* the Status row's value */
void cardrun_run(
    void); /* Run Now (a toast with no script); starts the 500 ms timer (page refresh, external audio hold) */
void cardrun_stop(void); /* Stop */
void cardrun_watch(void); /* the page shows: start the timer when a run is alive */
void cardrun_refresh(void); /* patch/m1plus.c: the Card Script page, when open, reads its rows again */
int cardrun_src(char *buf,
                int n); /* the card script's start for the page: the same cleanup, from the first line, whole lines */
int cardrun_log(
    char *buf,
    int n); /* the log's tail for the page: ASCII, from a line start, at most n - 1 bytes; its length, 0 when none */

/* patch/update.c */
int update_open(void); /* Software Update, our page; -1 when it did not open */

/* patch/wifipage.c */
int wifipage_open(void); /* Settings > Wi-Fi, our page; -1 when it did not open (the stock page then opens) */
/* The card list helpers of the Wi-Fi page, which the Bluetooth page (patch/btpage.c) uses as well. */
enum { WP_P_NONE, WP_P_SINGLE, WP_P_TOP, WP_P_MID, WP_P_BOT }; /* the picture piece of a card row */
void wp_put(void *row, int *y, int h,
            int touch); /* a shown row or header at *y, then *y += h (a header is never a touch target) */
void wp_vis(void *w, int on); /* a row child's visibility alone (it is insensitive in the asset) */
void wp_piece(void *row, unsigned char *have, int p); /* the row's picture piece WP_P_*, set only when it changed */
int wp_pos(int i, int n); /* the piece of the i-th of n rows of a card */
void wp_clamp(void *sv, int content); /* the scroll offset back into range after the content shrank */
int wf_on_scroll(
    void *ctx,
    void *e); /* the top fade of a page's scroll view; ctx is the page's struct, which starts with win, sv, fade */
void wk_subst(char *out, unsigned size, const char *tpl,
              const char *name); /* tpl with its %s replaced by name (a template of the translation table) */
int wf_name_lines(void *l0, void *l1,
                  const char *u); /* the whole name above the cards for a title that was cut: the lines used (1 or 2) */
void wf_name_put(void *nm[2], int lines,
                 int *y); /* those lines' views at *y (the unused one hidden), then *y past them */

/* patch/btpage.c */
int btpage_open(void); /* Settings > Bluetooth, our page; -1 when it did not open (the stock page then opens) */
int bp_codec(void); /* the Audio Codec page's chosen row: stock's btcoding 0 .. 7 */
int bp_codec_set(
    int c); /* a row of the Audio Codec page: the init guard, stock's Quality choice; 0 when the choice is c afterwards, else -1 */

/* patch/ndroot.c */
int nd_root_open(void); /* the Navidrome root page; -1 when it did not open */
void nd_synced_line(char *out, unsigned size); /* "Synced 5m ago" / "Synced just now" / "Not synced yet" */

/* patch/ndfolders.c */
int nd_folders_open(void); /* the Subsonic Folders browser (the root's Folders row); -1 when it did not open */

/* patch/ndserver.c */
int nd_server_open(void);
void nd_sync_now(void); /* asks first, then syncs */
int nd_signin_open(void); /* the Sign In page on the Server URL row */

/* patch/menu.c */
void menu_custom_opened(void *win); /* the Main Menu page's switches and arrows */
void menu_extras_opened(void *win); /* the Settings > Extras page's switches */
void menu_plain_paint(void *sv);

/* patch/pulldown.c */
void pulldown_page_opened(void *win); /* the Pull-down page's switches and arrows */
/* patch/pulldown.c: our page by its window name: left alone in front, else restacked (its sub-pages closed), else open_it(); 1 when it is up */
int pd_open_own(const char *window, int (*open_it)(void));
/* the same for a page several routes open (the Volume page, Gain, Equalizer, Volume & Sound): only the windows it opened (the opener table) are closed before it is restacked; the windows of the route the user came
 * by stay. rooted: the route is a Control Center tile or the status bar tap (no opener); 0: a row tap on the page in front, which becomes its opener */
int pd_open_page(const char *window, int (*open_it)(void), int rooted);
/* the window in front, or NULL; and the opener table's entry for win: opened from `from` (NULL: by a tile or the status bar tap) */
void *pd_front_window(void);
void pd_note_opener(void *win, void *from);

/* patch/volume.c */
void volpage_opened(void *win); /* the Volume page's window is up: stock's volume handlers bound to its widgets */
void volpage_go(
    int k); /* the Volume page's second card: row k (0 Max Volume, 1 Equalizer, 2 Volume & Sound) opens its page without a second window */
int vol_tap_open(const char *name, int ctx); /* payload hook 33: the status bar tap's open of the volume dialog */
int vol_tap_on(void); /* Tap for Volume, ours (VOLTAP_FILE): 0 off, anything else on (the default) */
int vol_tap_toggle(void); /* flip it; the new state, or -1 when it could not be saved */

/* patch/lineout.c */
int lo_link_show(
    void *w, int on,
    int recursive); /* payload hook 40: both face ticks' widget_set_visible(img_synclink, 1): SyncLink yields when stock's marks would reach the clock */

/* patch/pulldown.c */
int pd_usb_poll(
    void); /* payload hook 38: the idle pass's check_usb_status call (a stale USB state 2 after the unplug) */

/* patch/display.c */
int disp_light(void); /* stock's backlight time index, 0 never .. 4 five minutes */
int disp_light_set(int index); /* ... chosen the way stock's own page does; -1 for an index stock does not have */
int disp_led(void); /* stock's lamp mode: 0 off, 1 green, 2 blue */
int disp_led_set(int mode);
int disp_follow(void); /* stock's Follow Screen switch */
int disp_follow_toggle(void);
int disp_rotate(void); /* Screen Rotation, stock's word rotate_mode: 1 = 180 degrees */
int disp_rotate_toggle(void);
void disp_opened(void *win); /* the Display page's brightness card */
void disp_refresh(void *win);

/* patch/keyspower.c */
int kp_lock(void); /* Button Lock, 0 off, else stock's mode 1 .. 3 */
int kp_lock_set(int v);
int kp_tap(void); /* Tap to Wake, stock's byte */
int kp_tap_toggle(void);
int kp_standby(void); /* Auto-Standby, stock's byte */
int kp_standby_toggle(void);
int kp_car(void); /* Car Mode, stock's byte */
int kp_car_toggle(void);
int kp_shutdown(void); /* Auto-Shutdown, stock's word 0 .. 4 */
int kp_shutdown_set(int v);
int kp_swap(void); /* Swap Prev / Next, ours (SWAPKEYS_FILE): 1 on, 0 off (the default) */
int kp_swap_toggle(void); /* flip it, saved atomically; the new state, or -1 when it could not be saved */
int kp_key_map(
    int key,
    int value); /* the pod_keys_site stub: an event1 key code after stock's table and the event's value; previous and next swapped while kp_swap, chosen at key down */

/* patch/sleeptimer.c: the Sleep Timer page, stock's byte sleepflag and word sleep_time */
int st_choice(void); /* the row to check: 0 Off, 1 .. 6 a time, -1 none of them */
int st_set(int v);
int st_left_text(char *buf, unsigned n); /* the Time Left value, H:MM rounded up; 0 (buf empty) while no timer runs */
void st_opened(void *win, int page); /* the page's window is up: a refresh timer while it is in front */
void st_front(void); /* back in front: the timer again */
void st_gone(void); /* the window is destroyed: the timer is removed */

/* patch/netservice.c: Settings > Network Services and Wi-Fi Transfer (stock's airplayflag, dlnaflag and the Wi-Fi file transfer page) */
int ns_airplay(void);
int ns_airplay_toggle(
    void); /* stock's airplay_switch; the new state, with the Wi-Fi toast when it is on and Wi-Fi is not */
int ns_dlna(void);
int ns_dlna_toggle(void);
int ns_transfer_ok(void); /* the Wi-Fi Transfer row: 1 when Wi-Fi is connected, else a toast and 0 */
void wt_url_text(char *buf, unsigned n); /* "<ip>:8888", or "-" */
void wt_opened(
    void *win); /* the page's window is up: stop_player, switch_wifitransport(1), and the exits that stop it */
void wt_front(void); /* back in front after the player: the server again */

/* patch/libupdate.c: Settings > Library > Update Library (stock's autoscan_flag, scan dialog and folder page; the Last Updated record) */
int lu_auto(void);
int lu_auto_toggle(void); /* stock's switch: the byte xor 1, then [SYSSET] AUTOSCAN; the new state */
void lu_update_now(void); /* stock's Update Now: the scan dialog with a zero context */
void lu_folders(void); /* stock's Choose Folders row: the card check, then the folder picker (lupick_open) */
int lupick_open(
    void); /* patch/lupick.c: the folder picker; 0 up, -1 would not open (stock's page is the fallback), -2 an asset that is not ours */
void lp_scan_done(void); /* the picker's scan deque, freed once the scan's worker has returned (lu_scan_finish) */
void lu_songs_text(char *buf, unsigned n); /* the songtable's row count with a comma; empty when the query fails */
void lu_when_text(
    char *buf,
    unsigned n); /* the last completed scan (Today 09:41, Yesterday, Nov 14, a date); empty when none is recorded */
int lu_scan_finish(void *win, int done); /* the hook at the scan dialog's finish branch (payload hook 34) */

/* patch/playset.c: Settings > Playback Settings. A getter answers the shown state, a setter 0 or -1 (refused), a toggle the new state. */
enum {
    PS_CTL_MODE,
    PS_CTL_MEM,
    PS_CTL_GAIN,
    PS_CTL_RG,
    PS_CTL_DSD,
    PS_CTL_USB,
    PS_CTL_MAXVOL,
    PS_CTL_BOOTVOL,
    PS_CTL_BAL,
    PS_CTLS
}; /* the value rows, by ps_value_key */
int ps_playmode(void);
int ps_playmode_set(int v);
int ps_gapless(void);
int ps_gapless_toggle(void);
int ps_memplay(void);
int ps_memplay_set(int v);
int ps_folderskip(void);
int ps_folderskip_toggle(void);
int ps_gain_locked(void); /* the Line Out byte: stock greys Gain and ignores its click */
int ps_gain(void);
int ps_gain_set(int v);
int ps_replaygain(void);
int ps_replaygain_set(int v);
int ps_filter(void);
int ps_filter_set(int v);
int ps_dsd(void);
int ps_dsd_set(int v);
int ps_usbvol(void);
int ps_usbvol_set(int v);
int ps_digital(void);
int ps_digital_toggle(void);
int ps_foldercover(void); /* Settings > Library */
int ps_foldercover_toggle(void);
const char *ps_value_key(int ctl);
int ps_value_text(int ctl, char *buf,
                  int n); /* 1: buf holds the text (a number, L3), 0: the row shows ps_value_key's key */
enum {
    PS_VOL_MAX,
    PS_VOL_BOOT,
    PS_VOL_BAL,
    PS_VOLS
}; /* the loudness pages: stock's own handlers bound to our widgets */
void ps_vol_opened(void *win, int which);
void ps_vol_refresh(void *win, int which);
int ps_bootmem(void); /* Volume Memory */
int ps_bootmem_toggle(void);

/* patch/onlineart.c */
int onlineart_open(void);
int onlineart_open_artist(const char *name);

/* patch/language.c: Settings > General > Language, stock's language word */
int lang_get(void); /* the row of stock's language page that is loaded, 0 .. 12 */
int lang_set(int v); /* stock's row handler: store, save, switch_language, the Home menu flags, back to Home */
const char *lang_key(int v); /* the language's own name, stock's key lan_* */
/* patch/datetime.c: Settings > General > Date & Time. Every state is stock's own. */
int dt_auto(void); /* Set Automatically */
int dt_auto_toggle(void);
int dt_24h(void); /* 24-Hour Time */
int dt_24h_toggle(void);
int dt_zone(void); /* Time Zone: the saved index of our table */
int dt_zone_set(int index);
const char *tz_label_of(unsigned index); /* patch/timezones.c: the zone's English label */
void dt_text(int which, char *buf, int n); /* the date (0) or the time (1) as the rows show it */
void dt_edit_start(void); /* the date being typed from the clock */
void dt_field_text(int field, char *buf, int n);
int dt_chosen(int arg);
int dt_set(int arg);
int dt_apply(int which); /* Set Date (0) / Set Time (1) */
