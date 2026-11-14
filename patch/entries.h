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
const char *
np_cover_file(int *busy); /* demo's cover file of the playing track, NULL for none; busy while demo makes it */
unsigned np_file_key(const char *path); /* a hash of the picture file, 0 if unreadable */
void np_relight(void);
void *np_window(void); /* Now Playing's window, 0 when it has none (patch/idlelyrics.c) */
unsigned np_idle_color(void); /* the window's colour (a color_t word) after the cover's tone is looked at again */

/* patch/idlelyrics.c */
int idlelyrics_open_idle(
    void); /* Now Playing's idle timer: 0 once the page is up (or already open), -1 when it could not open (nothing left of it) */
int idlelyrics_up(void); /* 1 while the page is open */

/* patch/queuepage.c */
int queue_open(void); /* our Queue page; 0 once it is open, else the stock drawer should open */

/* patch/bigcover.c */
int idle_choice(
    void); /* Idle Display: 0 Off (stock's Cover mode byte off), 1 Album Cover, 2 Cassette, 3 Vinyl, 4 Lyrics; read live */
int idle_set(
    int choice); /* choose it, saved (the byte through stock's save, the destination atomically); the choice or -1 */

/* patch/tape.c */
int tape_open(void);
int tape_open_idle(
    void); /* 0 once the page is up (or already open), -1 when it could not open; a tap on a page it opened closes it */
int tape_theme(void); /* the saved theme, 0 Normal (the default), 1 Chrome, 2 Metal, 3 Auto (by the track's quality) */
int tape_theme_set(int theme); /* choose it, saved atomically; the theme or -1 */

/* patch/vinyl.c */
int vinyl_open(void);
int vinyl_open_idle(void); /* the same for Vinyl Mode (a tap on the record closes) */
int vinyl_record(void); /* the saved record colour, 0 Black (the default) .. VN_RECS - 1 */
int vinyl_record_set(int rec); /* choose it, saved atomically; the colour or -1 */
int vinyl_theme(void); /* the saved plinth theme, 0 Graphite (the default), 1 White */
int vinyl_theme_set(int theme); /* choose it, saved atomically; the theme or -1 */

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
unsigned ip_fit(void *canvas, unsigned *s, int maxw); /* the wide string cut with an ellipsis to maxw px */

/* patch/ipod_cf.c */
int ipcf_open(void *win), ipcf_up(void), ipcf_busy(void), ipcf_tick(void *list, unsigned count);
void ipcf_close(void), ipcf_goto(int sel), ipcf_paint(void *canvas, void *list, unsigned count, void *style);

/* patch/lockscreen.c */
int lkwp_open(void); /* the Lock Screen's Wallpaper picker, our page; -1 when it did not open */
int lk_layout(void); /* the saved lock screen layout, 0 Large Cover (the default), 1 Mini Player */
int lk_layout_set(int layout); /* choose it, saved atomically; the layout or -1 */
int lk_enabled(void); /* stock's lock screen switch (the byte screensaver_mode): 1 on */
int lk_enabled_toggle(void); /* flip it as stock's switch does (byte, then [SYSSET] SCREENSAVER); the new state */
int lk_time(void); /* stock's lock screen clock switch (the byte screensaver_timeshow): 1 on */
int lk_time_toggle(void); /* flip it as stock's switch does (byte, then [SYSSET] SSAVERTIMESHOW); the new state */

/* patch/relnotes.c */
int lockinfo_open(
    void); /* the Lock Screen's Custom Wallpaper instructions, a Release Notes page; -1 when it did not open */
int relnotes_open(void); /* the offered release's notes, a page of their own */

/* patch/update.c */
int update_open(void); /* Software Update, our page; -1 when it did not open */

/* patch/wifipage.c */
int wifipage_open(void); /* Settings > Wi-Fi, our page; -1 when it did not open (the stock page then opens) */

/* patch/ndroot.c */
int nd_root_open(void); /* the Navidrome root page; -1 when it did not open */
void nd_synced_line(char *out, unsigned size); /* "Synced 5m ago" / "Synced just now" / "Not synced yet" */

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

/* patch/display.c */
int disp_light(void); /* stock's backlight time index, 0 never .. 4 five minutes */
int disp_light_set(int index); /* ... chosen the way stock's own page does; -1 for an index stock does not have */
int disp_led(void); /* stock's lamp mode: 0 off, 1 green, 2 blue */
int disp_led_set(int mode);
int disp_follow(void); /* stock's Follow Screen switch */
int disp_follow_toggle(void);
void disp_opened(void *win); /* the Display page's brightness card */
void disp_refresh(void *win);

/* patch/keyspower.c */
int kp_lock(void); /* Button Lock, 0 off, else stock's mode 1 .. 3 */
int kp_lock_set(int v);
int kp_tap(void); /* Tap to Wake, stock's byte */
int kp_tap_toggle(void);
int kp_standby(void); /* Auto-Standby, stock's byte */
int kp_standby_toggle(void);
int kp_shutdown(void); /* Auto-Shutdown, stock's word 0 .. 4 */
int kp_shutdown_set(int v);

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
