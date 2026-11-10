/* M1+ Music: new pages inside the Shanling M1 Plus UI app (/release/bin/demo).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 * The injection scheme -- a non-PIC payload in an appended PT_LOAD at 0xb00000, checked PIC-prologue
 * jumps, a $gp-restoring trampoline, stock functions reached through absolute-address macros, and
 * libc only through demo's own GOT slots -- follows q2-pod's design (https://github.com/DiamondBond/q2-pod).
 *
 * Exactly one stock function is hooked: the Home screen's icon click dispatcher (0x533b80, unnamed,
 * registered per icon during home_page_init). It runs only when the user taps a Home icon -- never
 * on the boot path, in the main loop or during paint. Any tap that is not the M1+ Music icon (id 99, added to
 * the grid by patch/home.c; Tidal is a normal icon again), or
 * when the kill-switch file exists, or if the page fails to open, continues into stock behaviour
 * through the trampoline.
 *
 * A second hook, home_page_init, does its work in patch/home.c behind a crash marker (the boot
 * guard, docs/architecture.md); m1plus.c only has the two launcher rows and the entry-page open
 * used by the Home timer (the menu's own arrangement, which items show and in which order, is patch/menu.c).
 */
#include "offsets.inc"

/* ACT_* mirror tools/pod_pages.py. */
enum {
    ACT_HOME = 0,
    ACT_PAGE = 1,
    ACT_PLAYER = 2,
    ACT_COVER = 3,
    ACT_SHUFFLE = 4,
    ACT_ARTISTS = 8,
    ACT_GRID = 9,
    ACT_STARTUP = 10,
    ACT_ALBUMS = 11,
    ACT_LANDSCAPE = 12,
    ACT_VOLKEYS = 89,
    ACT_SHOT = 14,
    ACT_REBUILD = 15,
    ACT_SHELF = 16,
    ACT_PLAYLISTS = 17,
    ACT_SONGS = 18,
    ACT_DAILY = 19,
    ACT_REGEN = 20,
    ACT_LIST = 21,
    ACT_IPOD = 22,
    ACT_PODCASTS = 23,
    ACT_CTHEME = 24,
    ACT_SEARCH = 35,
    ACT_KB_EN = 27,
    ACT_KB_ZH = 28,
    ACT_STOCK = 29,
    ACT_THEMESET = 31,
    ACT_INFO = 33,
    ACT_PCSEARCH = 34,
    ACT_BATTPCT = 36,
    ACT_FOLDERS = 37,
    ACT_VREC = 38,
    ACT_RECSET = 39,
    ACT_VTHEME = 40,
    ACT_VTHSET = 41,
    ACT_CLEARCACHE = 42,
    ACT_CCLIST = 43,
    ACT_CLEARDUR = 44,
    ACT_UPDATE = 45,
    ACT_BG = 46,
    ACT_BGSET = 47,
    ACT_ACCENT = 48,
    ACT_ACCENTSET = 49,
    ACT_RADIO = 50,
    ACT_SFDEL = 51,
    ACT_SFOLD = 52, /* Settings Files: Unsupported Files, a count (a chevron and the list only when it is not zero) */
    ACT_SFDELALL = 53, /* Settings Files: Delete Unsupported Files, an action row */
    ACT_RESETALL = 54, /* Developer > Tools: Reset All Settings, an action row (a confirm, then setfiles_reset_all) */
    ACT_REGION = 55,
    ACT_REGIONSET = 56,
    ACT_PEQ = 57,
    ACT_AZRAIL = 77, /* Settings > Library > Index Rail: a switch row, on by default (patch/azlist.c azrail_toggle) */
    ACT_AZHEAD =
        78, /* Settings > Library > Section Headers: a switch row, on by default (patch/azlist.c azhead_toggle) */
    ACT_LOCKSET = 88,
    ACT_LOCKON = 79,
    ACT_CHGLIM = 80, /* Settings > System > Battery: Charge Limit, a value row opening its picker */
    ACT_CHGLIMSET = 81, /* the Charge Limit picker's rows (arg = the limit, 80 .. 100) */
    ACT_IDLE =
        82, /* Settings > Now Playing > Idle Display: a value row (Off, Album Cover, Cassette, Vinyl) opening its picker */
    ACT_IDLESET = 83, /* the picker's rows (arg 0 Off, 1 Album Cover, 2 Cassette, 3 Vinyl) */
    ACT_LOCKWP = 84, /* Settings > Lock Screen > Wallpaper: our picker page (patch/lockscreen.c lkwp_open) */
    ACT_LOCKSTYLE =
        85, /* Settings > Lock Screen > Player Style: a value row (Large Cover / Mini Player) opening its picker */
    ACT_LOCKTIME =
        86, /* Settings > Lock Screen > Show Time: a switch row, stock's own clock switch (patch/lockscreen.c lk_time_toggle) */
    ACT_LOCKINFO =
        87, /* Settings > Lock Screen > Custom Wallpaper: the instructions page (patch/relnotes.c lockinfo_open) */
    ACT_NEXTALBUM = 90, /* Settings > Playback: Continue Playing, a value row opening its picker */
    ACT_NASET = 91, /* the Continue Playing picker's rows (arg = NA_OFF or NA_ALBUMS) */
    ACT_AREBUILD =
        92 /* Settings > Library: Rebuild Artist Photos, an action row (a confirm, then the request file Home's pass acts on) */
};

extern void shot_start(void); /* patch/shot.c: the Screenshot row: confirm, 5 s countdown, capture; or cancel */
extern int artists_open(
    int home); /* patch/artists.c: the Artists list, its own page; arg HOME_GENRE / HOME_COMPOSER: Genres / Composers on it */
extern int albums_open(void); /* patch/albums.c: Albums, our page in the mode used last (grid or list) */
extern int playlists_open(void); /* patch/playlists.c: Playlists, a grid of mosaics of each playlist's covers */
extern int ipod_open(void); /* patch/ipod.c: the virtual iPod Classic, a fullscreen page with a touch click wheel */
extern int podcasts_open(void); /* patch/podcasts.c: the shows on the card and their episodes */
extern int lockinfo_open(
    void); /* patch/relnotes.c: the Lock Screen's Custom Wallpaper instructions, a Release Notes page; -1 when it did not open */
extern int update_open(void); /* patch/update.c: Software Update, our page; -1 when it did not open */
extern int
lkwp_open(void); /* patch/lockscreen.c: the Lock Screen's Wallpaper picker, our page; -1 when it did not open */
extern int wifipage_open(
    void); /* patch/wifipage.c: Settings > Wi-Fi, our page; -1 when it did not open (the stock page then opens) */
extern int radio_open(void); /* patch/radiopage.c: Radio's stations page */
extern int search_open(void); /* patch/search.c: our keyboard, then the results page; -1 when it did not open */
extern int songs_open(void); /* patch/songs.c: Songs, the library as one list with sections and a jump rail */
extern int folders_open(
    int home); /* patch/folders.c: Folders, the card's folders and audio files; a window that will not open leaves the stock folder_page through the Home tile home */
extern int songs_open_list(
    int home); /* patch/songs.c: another stock song list (Favourites ...) on the same page; arg = its Home tile */
extern void menu_arrange(void *win, int extras); /* patch/menu.c: the menu / Extras rows as the saved list says */
extern void menu_custom_opened(void *win); /* patch/menu.c: the Main Menu page's switches and arrows */
extern void pulldown_page_opened(void *win); /* patch/pulldown.c: the Pull-down page's switches and arrows */
extern void menu_extras_opened(void *win); /* patch/menu.c: the Settings > Extras page's switches */
extern void peq_opened(void *win); /* patch/peq_ui.c: the Equalizer page's switch, 10-Band EQ and presets */
extern void peqpage_opened(void *win); /* patch/peqpage.c: the preset page's graph, preamp and bands */
extern void tenband_opened(void *win); /* patch/tenband.c: the 10-Band editor and its two picker pages */
extern void peqband_opened(void *win); /* patch/peqband.c: the band page of a preset */
extern void tencurve_opened(void *win);
extern void tenpreamp_opened(void *win);
extern void peqlib_opened(void *win); /* patch/peqlib.c: the Presets page's download row and the card's files */
extern int peq_playing_name(
    char *buf,
    unsigned
        size); /* patch/peq_ui.c: the preset the record plays, as the page names it, or the 10-Band EQ's curve key */

struct pod_row {
    const char *name; /* row widget name in the asset (pod_row0, pod_row1, ...) */
    int action; /* ACT_* */
    int arg; /* HOME_* id, or a page index */
};

struct pod_page {
    const char *asset; /* window resource name (ui/<asset>.bin) */
    const struct pod_row *rows;
    int count;
    unsigned
        wrap_notes; /* bit n: the page's note pod_note<n>_t is a wrapping (plain) label, Note lines > 1: its wrap is turned on as the page opens */
};

struct pod_stock {
    const char *name; /* a stock page, for navigator_to */
    const char *
        window; /* its window's name (the asset's root), restacked when opened; 0: always opened afresh (Wi-Fi, Bluetooth: init does what a restack would not redo) */
    int value; /* the value the row shows at the right: VK_* (0: none) */
};

/* The values a Settings row shows at the right (tools/pod_pages.py STOCK_VALUES in this order, then the two of ours). */
/* ACT_INFO's arg: where an About row's value comes from (tools/pod_pages.py INFO_*). */
enum {
    INFO_TAG = 0,
    INFO_FW,
    INFO_MODEL,
    INFO_SN,
    INFO_MAC,
    INFO_IP,
    INFO_CAP,
    INFO_FREE,
    INFO_CC, /* the Cache page's seven Covers values start here: homecover_stat(kind - INFO_CC) */
    INFO_SF = INFO_CC + 7, /* the Settings Files page's 45 values: setfiles_stat(kind - INFO_SF) */
    INFO_SFOLD = INFO_SF + 45, /* the Unsupported Files count (setfiles_old_count), above those rows */
    INFO_DUR = INFO_SFOLD + 1, /* the Cache page's Measured Tracks: dur_stat (patch/durations.c) */
    INFO_APHOTOS = INFO_DUR +
        1, /* the Cache page's Artist Photos card: the photos, and the artists with none (homecover_stat 7, 8) */
    INFO_ANONE = INFO_DUR + 2
};

enum {
    VK_NONE = 0,
    VK_WIFI,
    VK_BLUETOOTH,
    VK_EQ,
    VK_THEME,
    VK_RECORD,
    VK_VTHEME,
    VK_BG,
    VK_ACCENT,
    VK_REGION,
    VK_CHGLIM,
    VK_LOCKSTYLE,
    VK_IDLE,
    VK_NA
};

/* stock.h (generated by tools/pod.py) supplies the stock-function address macros, the libc GOT
 * stubs and the externs (the trampoline, coverflow_open); pages.h, from the same generator, the
 * stage's POD_PAGES/POD_PAGE_COUNT tables and the constants POD_ENTRY_ID and POD_ENTRY_PAGE. */
#include "stock.h"
#include "pages.h"
#include "covercache.h"
#include "durations.h" /* Clear Track Durations */

/* The stock Home dispatcher reads only the clicked icon's name (widget_t + W_NAME): it atoi()s it
 * to a Home id and opens that destination. A fake icon with a numeric name reuses it to open any
 * stock Home page without touching the real widget tree. */
struct fake_icon {
    char pad[W_NAME];
    const char *name;
};

static const char HOME_NAMES[18][3] = {"0", "1",  "2",  "3",  "4",  "5",  "6",  "7",  "8",
                                       "9", "10", "11", "12", "13", "14", "15", "16", "17"};

#include "home.h"
#include "common.h"
#include "i18n.h"
#include "pcregion.h"
#include "charging.h"
#include "nextalbum.h"
static int pod_off(void) { return home_off(); } /* the SD file and the flash one */

static int home_open(int id) {
    struct fake_icon icon;
    int i;
    for (i = 0; i < W_NAME; i++) icon.pad[i] = 0;
    if (id < 0 || id >= HOME_IDS) return -1;
    icon.name = HOME_NAMES[id];
    return stock_home_click_trampoline(&icon, (void *)0);
}

/* A stock Home destination through the dispatcher (the Albums toggle opens the stock list this way). */
int pod_home_open(int id) { return home_open(id); }

static int open_page(int index, int as_home);

/* The Extras page's Settings button: the page a Settings row opens (ACT_PAGE), over the Extras page (patch/home.c knows it for the Shanling Home exit). */
static int on_settings(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    open_page(POD_SETTINGS_PAGE, 0);
    return RET_OK;
}

static int on_menu_fg(void *ctx, void *e) {
    (void)e;
    menu_arrange(ctx, 0);
    return RET_OK;
}

#define POD_SCRIM_COLOR 0x82000000u /* #00000082 (PL_DIM) as value_t's uint32: AWTK's colour, alpha in the top byte */

/* Whether win is still a window of the window manager. Only pointers are compared: a window that closed is never read. */
static int pod_window_open(void *wm, void *win) {
    unsigned i, n;
    for (n = widget_count_children(wm), i = 0; i < n; ++i)
        if (widget_get_child(wm, i) == win) return 1;
    return 0;
}

/* The confirm dialog over the page. The stock dialog's highlighter does not dim the window below on the device, so while the modal
 * dialog is up a full-window scrim (#00000082, our popups' colour) is a view on the top main window: its last child, insensitive, and
 * removed when the call returns (or never touched when that window has closed meanwhile). Pinned stock functions only. The result is
 * the dialog's raw result (CONFIRM_YES for Yes). */
int pod_confirm_dialog(void *info) {
    void *wm = window_manager(), *win = wm ? window_manager_get_top_main_window(wm) : (void *)0, *scrim = (void *)0;
    unsigned v[4], i, n;
    int r;
    if (win) {
        scrim = view_create(win, 0, 0, *(int *)((char *)win + W_W), *(int *)((char *)win + W_H));
        if (scrim) {
            memset(v, 0, sizeof v);
            value_set_uint32(v, POD_SCRIM_COLOR);
            widget_set_style(scrim, "normal:bg_color", v);
            widget_set_sensitive(scrim, 0);
        }
    }
    r = navigator_to_with_context("dialog/confirminfo_dialog", info);
    if (scrim && pod_window_open(wm, win))
        for (n = widget_count_children(win), i = 0; i < n; ++i)
            if (widget_get_child(win, i) == scrim) {
                widget_set_visible(scrim, 0, 0);
                widget_set_sensitive(scrim, 0);
                widget_destroy(scrim);
                break;
            }
    return r;
}

/* Settings > Library > Rebuild Covers: the stock yes/no dialog (dialog/confirminfo_dialog, the one the equaliser
 * reset and the Bluetooth reconnect use) with a wrapped message; the call is modal and returns CONFIRM_YES for Yes.
 * No (or the dialog failing to open) does nothing at all; Yes stays on Settings, writes the request file (REBUILD_FILE) that
 * Home's cover build (patch/homecover.c) acts on, and shows a toast. */
int pod_confirm_code(const char *s) { /* the dialog's raw result; also patch/shot.c: Take / Cancel the screenshot */
    struct {
        int kind, ms;
        char text[MSGINFO_TEXT], text2[MSGINFO_TEXT];
    } info;
    unsigned i;
    memset(&info, 0, sizeof info);
    info.kind = CONFIRM_KIND_WRAP;
    for (i = 0; s[i] && i < sizeof info.text - 1; ++i) info.text[i] = s[i];
    return pod_confirm_dialog(&info);
}

int pod_confirm(const char *s) { return pod_confirm_code(s) == CONFIRM_YES; }

static void rebuild_ask(void) {
    if (!pod_confirm(TR("Rebuild all covers? This may take a few minutes."))) return;
    if (home_write_atomic(REBUILD_FILE, REBUILD_TMP, "1\n") == 0) {
        cc_clear_bad();
        homecover_rebuild_asked();
        pod_toast(TR("Covers will rebuild on Home"));
    } else
        pod_toast(TR("Storage unavailable"));
}

/* Settings > Library > Rebuild Artist Photos: the same dialog, then the request file (AREBUILD_FILE) Home's pass acts on (every artist is looked at again, found photos too). Rebuild Covers and this stay apart. */
static void arebuild_ask(void) {
    if (!pod_confirm(TR("Rebuild all artist photos? This may take a few minutes."))) return;
    if (home_write_atomic(AREBUILD_FILE, AREBUILD_TMP, "1\n") == 0) {
        homecover_rebuild_asked();
        pod_toast(TR("Artist photos will rebuild on Home"));
    } else
        pod_toast(TR("Storage unavailable"));
}

void pod_page_refresh(int index);

/* Settings > Developer > Clear Cover Cache: the same confirm dialog; refused (a toast) while the cover worker is busy. */
__attribute__((noinline)) static void clear_ask(void) {
    if (cc_build_busy()) {
        pod_toast(TR("Covers are being made, try later"));
        return;
    }
    if (pod_confirm(TR("Delete all cached covers? They will be made again on Home.")) && !homecover_clear())
        pod_toast(TR("Covers are being made, try later"));
}

/* Settings > Developer > Clear Track Durations: the confirm dialog, then the table is deleted (Home measures the songs again) and the
 * Cache page's Measured Tracks reads the file again (0 now). */
__attribute__((noinline)) static void durations_clear_ask(void) {
    if (!pod_confirm(TR("Delete all measured track durations? They will be measured again on Home."))) return;
    dur_clear();
    dur_stat_open();
    pod_page_refresh(POD_CACHE_PAGE);
    homecover_stamp_drop(2); /* Home measures them again */
    pod_toast(TR("Track durations cleared"));
}

/* Settings > Developer > Tools > Settings Files: a setting file's row (tappable only while its file is there): the confirm dialog, then the file
 * is deleted and its row reads again (the page is refreshed). Storage that refuses the delete: a toast. */
__attribute__((noinline)) static void setfiles_delete_ask(int idx) {
    if (!pod_confirm(TR("Delete this settings file?"))) return;
    if (setfiles_delete(idx) == 0) {
        pod_page_refresh(POD_FILES_PAGE);
        pod_toast(TR("Settings file deleted"));
    } else
        pod_toast(TR("Storage unavailable"));
}

/* Settings > Developer > Tools > Settings Files > Delete Unsupported Files: nothing to delete is a toast; else a confirm, then every retired file
 * (the old builds' leftovers, setfiles.c) is deleted and the page's count reads again. Storage that keeps one: a toast. */
__attribute__((noinline)) static void unsupported_delete_ask(void) {
    if (setfiles_old_count() == 0) {
        pod_toast(TR("No unsupported files"));
        return;
    }
    if (!pod_confirm(TR("Delete all unsupported files?"))) return;
    if (setfiles_old_delete_all() == 0)
        pod_toast(TR("Unsupported files deleted"));
    else
        pod_toast(TR("Storage unavailable"));
    pod_page_refresh(POD_FILES_PAGE);
}

/* Settings > Developer > Tools > Reset All Settings: the confirm dialog, then every settings file is deleted (patch/setfiles.c). No reboot:
 * the values in memory keep until the device restarts. */
__attribute__((noinline)) static void reset_all_ask(void) {
    if (!pod_confirm(TR("Reset all settings to their defaults?"))) return;
    if (setfiles_reset_all() == 0)
        pod_toast(TR("Settings reset. Restart to apply."));
    else
        pod_toast(TR("Storage unavailable"));
}

static void pick_choose(const struct pod_row *row);

static int is_pick(const struct pod_row *row) { /* the pickers' check rows */
    return row->action == ACT_THEMESET || row->action == ACT_RECSET || row->action == ACT_VTHSET ||
           row->action == ACT_BGSET || row->action == ACT_ACCENTSET || row->action == ACT_REGIONSET ||
           row->action == ACT_CHGLIMSET || row->action == ACT_LOCKSET || row->action == ACT_IDLESET ||
           row->action == ACT_NASET;
}

static void *stock_front __attribute__((section(
    ".scratch"))); /* the window an ACT_STOCK row opened; forgotten when a Settings page is back in front (page_refresh) */

static int on_row(void *ctx, void *e) {
    const struct pod_row *row = ctx;
    (void)e;
    if (!row) return RET_OK;
    if (row->action == ACT_HOME)
        home_open(row->arg);
    else if (row->action == ACT_PAGE || row->action == ACT_CTHEME || row->action == ACT_VREC ||
             row->action == ACT_VTHEME || row->action == ACT_BG || row->action == ACT_ACCENT ||
             row->action == ACT_REGION || row->action == ACT_PEQ || row->action == ACT_CHGLIM ||
             row->action == ACT_LOCKSTYLE || row->action == ACT_IDLE ||
             row->action == ACT_NEXTALBUM) /* the value rows open their picker page */
        open_page(row->arg, 0);
    else if (row->action == ACT_PLAYER)
        pod_open_now_playing();
    else if (row->action == ACT_COVER)
        coverflow_open(); /* patch/coverflow.c; its own page */
    else if (row->action == ACT_ARTISTS)
        artists_open(row->arg);
    else if (row->action == ACT_ALBUMS)
        albums_open();
    else if (row->action == ACT_PLAYLISTS)
        playlists_open();
    else if (row->action == ACT_SONGS)
        songs_open();
    else if (row->action == ACT_FOLDERS)
        folders_open(row->arg);
    else if (row->action == ACT_IPOD)
        ipod_open();
    else if (row->action == ACT_PODCASTS)
        podcasts_open();
    else if (row->action == ACT_RADIO)
        radio_open();
    else if (row->action == ACT_SUBSONIC)
        open_page(POD_SUBSONIC_PAGE, 0);
    else if (row->action == ACT_SEARCH) {
        if (search_open() < 0)
            navigator_to_with_context(
                "search_page",
                (const void
                     *)0); /* the stock page where ours will not open, as the Songs page's Search (patch/songs.c) */
    } else if (row->action == ACT_LIST)
        songs_open_list(row->arg);
    else if (row->action == ACT_SHUFFLE)
        shuffle_play(row->arg); /* patch/shuffle.c; plays, no page */
    else if (row->action == ACT_GRID)
        home_to_grid(); /* patch/home.c: the stock grid */
    else if (row->action == ACT_SHOT)
        shot_start(); /* patch/shot.c; a timer, no page */
    else if (row->action == ACT_REBUILD)
        rebuild_ask(); /* a confirm dialog, then a request for Home's cover build */
    else if (row->action == ACT_AREBUILD)
        arebuild_ask(); /* a confirm dialog, then a request for Home's artist photo pass */
    else if (row->action == ACT_CCLIST)
        homecover_list_open(
            row->arg -
            INFO_CC); /* the albums with no art / no cache file, a plain list (nothing when the count is 0 or still being made) */
    else if (row->action == ACT_LOCKWP)
        lkwp_open(); /* patch/lockscreen.c: the wallpaper grid, our page (nothing when it will not open) */
    else if (row->action == ACT_LOCKINFO)
        lockinfo_open(); /* patch/relnotes.c: the instructions, a Release Notes page (nothing when it will not open) */
    else if (row->action == ACT_UPDATE)
        update_open(); /* patch/update.c: our page; the check, the download and the hand-over to the firmware's TF card update */
    else if (row->action == ACT_CLEARCACHE)
        clear_ask(); /* a confirm dialog, then the cache files are removed in steps */
    else if (row->action == ACT_CLEARDUR)
        durations_clear_ask(); /* a confirm dialog, then the track durations table is deleted */
    else if (row->action == ACT_SFDEL)
        setfiles_delete_ask(row->arg - INFO_SF); /* Settings Files: a confirm, then that file is deleted */
    else if (row->action == ACT_SFOLD)
        covlist_open(2, (const unsigned short *)0, 0); /* Settings Files: the Unsupported Files list */
    else if (row->action == ACT_SFDELALL)
        unsupported_delete_ask(); /* Settings Files: a confirm, then every retired file is deleted */
    else if (row->action == ACT_RESETALL)
        reset_all_ask(); /* Developer > Tools: a confirm, then every settings file is deleted */
    else if (row->action == ACT_REGEN)
        dailymix_regen(); /* patch/dailymix.c: no page, a toast when asked; the card is made again when the Home menu is back in front */
    else if (row->action == ACT_STOCK) {
        if (row->arg == 0 /* STOCK_WIFI */ && wifipage_open() == 0)
            return RET_OK; /* patch/wifipage.c: our Wi-Fi page; the stock page where it will not open */
        {
            void *wm = window_manager(), *top = wm ? window_manager_get_top_main_window(wm) : (void *)0;
            if (top && top == stock_front)
                return RET_OK; /* the stock page this row opened is still the front window: a repeated tap opens no second one */
            pod_open_stock(POD_STOCK[row->arg].name,
                           POD_STOCK[row->arg].window); /* stock's navigator_to, or the page's window if in the stack */
            top = wm ? window_manager_get_top_main_window(wm) : (void *)0;
            stock_front = top;
        }
    } else if (is_pick(row))
        pick_choose(ctx); /* a picker row */
    return RET_OK;
}

/* The Settings pages' rows (docs/modules/settings.md): switches, rows with a value at the right, and the pickers' check rows. The pages are generic (tools/pod_ui.py build_cards_page): a row is bound
 * by name (pod_row<i>), its switch image is pod_switch<i>, its value label pod_value<i> (the row's own label pod_label<i>), a picker row's check pod_check<i>. page_refresh sets all of them from
 * the saved or stock state when the page opens and each time it is back in front (a stock page or a picker may have changed what it shows). */
static void *pod_fg[POD_PAGE_COUNT] __attribute__((section(".scratch")));

struct swctx {
    int action;
    void *img;
};
static struct swctx sw_slot[13] __attribute__((section(".scratch")));

static void switch_show(void *img, int on) {
    if (img) image_base_set_image(img, on ? "sset_on" : "sset_off");
}

/* Settings > Home Screen > Regenerate Daily Mix: its row and its note are hidden (not visible, not sensitive: the list_view layouter skips them and the rows below close up, though
 * there are none) while no mix can be made (the Daily Mix switch off, or a library under MIX_MIN_LIB songs); the Daily Mix switch updates them in place. The row is a card of its own
 * (a single piece) at the end of the page, so nothing else changes with it. They are the page's last row and fourth note (pod_note3; tools/pod_pages.py HOMESET_PAGE, pinned by test). */
static void *regen_row __attribute__((section(".scratch"))), *regen_note __attribute__((section(".scratch")));
#define KB_EN_DIM 153 /* 60 %: Settings > Keyboards > English, always on and not switchable */

static void regen_show(void) {
    int on = dailymix_can_regen();
    if (regen_row) widget_set_visible(regen_row, on, 0), widget_set_sensitive(regen_row, on);
    if (regen_note)
        widget_set_visible(regen_note, on, 0),
            widget_set_sensitive(regen_note, 0); /* the note is never a touch target */
}

extern int lk_enabled(void); /* patch/lockscreen.c: stock's lock screen switch (the byte screensaver_mode): 1 on */
extern int
lk_enabled_toggle(void); /* flip it as stock's switch does (byte, then [SYSSET] SCREENSAVER); the new state */
extern int
lk_time(void); /* patch/lockscreen.c: stock's lock screen clock switch (the byte screensaver_timeshow): 1 on */
extern int
lk_time_toggle(void); /* flip it as stock's switch does (byte, then [SYSSET] SSAVERTIMESHOW); the new state */

static int switch_state(int action) {
    return action == ACT_STARTUP    ? home_start()
           : action == ACT_SHELF    ? recent_setting()
           : action == ACT_DAILY    ? dailymix_setting()
           : action == ACT_KB_EN    ? 1 /* English: always on */
           : action == ACT_KB_ZH    ? kb_zh_setting()
           : action == ACT_PCSEARCH ? pcsearch_setting()
           : action == ACT_BATTPCT  ? battpct_setting()
           : action == ACT_AZRAIL   ? azrail_setting()
           : action == ACT_AZHEAD   ? azhead_setting()
           : action == ACT_LOCKON   ? lk_enabled()
           : action == ACT_LOCKTIME ? lk_time()
           : action == ACT_VOLKEYS  ? coverflow_volkeys()
                                    : coverflow_landscape();
}

static int on_switch(void *ctx, void *e) {
    const struct swctx *s = ctx;
    int on;
    (void)e;
    if (!s) return RET_OK;
    on = s->action == ACT_STARTUP    ? home_toggle()
         : s->action == ACT_SHELF    ? recent_toggle()
         : s->action == ACT_DAILY    ? dailymix_toggle()
         : s->action == ACT_KB_ZH    ? kb_zh_toggle()
         : s->action == ACT_PCSEARCH ? pcsearch_toggle()
         : s->action == ACT_BATTPCT  ? battpct_toggle()
         : s->action == ACT_AZRAIL   ? azrail_toggle()
         : s->action == ACT_AZHEAD   ? azhead_toggle()
         : s->action == ACT_LOCKON   ? lk_enabled_toggle()
         : s->action == ACT_LOCKTIME ? lk_time_toggle()
         : s->action == ACT_VOLKEYS  ? coverflow_volkeys_toggle()
                                     : coverflow_landscape_toggle(); /* -1: not saved, unchanged */
    if (on >= 0) switch_show(s->img, on);
    if (s->action == ACT_DAILY) regen_show();
    return RET_OK;
}

static void bind_switch(void *win, unsigned i, const struct pod_row *row) {
    char name[24];
    void *r = widget_lookup(win, row->name, 1);
    int k = row->action == ACT_LANDSCAPE  ? 1
            : row->action == ACT_SHELF    ? 2
            : row->action == ACT_DAILY    ? 3
            : row->action == ACT_KB_EN    ? 4
            : row->action == ACT_KB_ZH    ? 5
            : row->action == ACT_PCSEARCH ? 6
            : row->action == ACT_BATTPCT  ? 7
            : row->action == ACT_AZRAIL   ? 8
            : row->action == ACT_AZHEAD   ? 9
            : row->action == ACT_LOCKON   ? 10
            : row->action == ACT_LOCKTIME ? 11
            : row->action == ACT_VOLKEYS  ? 12
                                          : 0;
    snprintf(name, sizeof name, "pod_switch%u", i);
    sw_slot[k].action = row->action;
    sw_slot[k].img = widget_lookup(win, name, 1);
    if (row->action == ACT_KB_EN) { /* English cannot be turned off: on, dimmed, and the row takes no tap */
        if (r) widget_set_opacity(r, KB_EN_DIM), widget_set_sensitive(r, 0);
        return;
    }
    if (r) widget_on(r, EVT_CLICK, on_switch, &sw_slot[k]);
}

/* The values (tr keys of the stock tables where the value is stock's own, so they follow Settings > Language): Wi-Fi and Bluetooth On / Off (the flags the status bar reads), the EQ (Off, or the preset's name from stock's own lookup), the album order and the
 * cassette theme (ours). */
extern int tape_theme(void); /* patch/tape.c: the saved theme, 0 Normal (the default), 1 Chrome, 2 Metal */
extern int tape_theme_set(int theme); /* choose it, saved atomically; the theme or -1 */
extern int vinyl_record(void); /* patch/vinyl.c: the saved record colour, 0 Black (the default) .. VN_RECS - 1 */
extern int vinyl_record_set(int rec); /* choose it, saved atomically; the colour or -1 */
extern int
lk_layout(void); /* patch/lockscreen.c: the saved lock screen layout, 0 Large Cover (the default), 1 Mini Player */
extern int lk_layout_set(int layout); /* choose it, saved atomically; the layout or -1 */
extern int idle_choice(
    void); /* patch/bigcover.c: Idle Display: 0 Off (stock's Cover mode byte off), 1 Album Cover, 2 Cassette, 3 Vinyl; read live */
extern int idle_set(
    int choice); /* choose it, saved (the byte through stock's save, the destination atomically); the choice or -1 */
static const char *const idle_key[4] = {"Off", "Album Cover", "Cassette", "Vinyl"};
static const char *const record_key[VN_RECS] = {"Black", "Cover"};
extern int vinyl_theme(void); /* patch/vinyl.c: the saved plinth theme, 0 Graphite (the default), 1 White */
extern int vinyl_theme_set(int theme); /* choose it, saved atomically; the theme or -1 */
static const char *const vtheme_key[VN_THEMES] = {"Graphite", "Snow"};
static const char *const accent_key[PAL_ACCENTS] = {
    "Neutral", "Red", "Orange", "Green", "Teal", "Purple", "Champagne"}; /* tools/pod_pages.py ACCENT_VALUES */

static void value_text(void *label, int kind) {
    char buf[64]; /* a preset name: PEQ_NAME */
    const char *key = "";
    if (kind == VK_WIFI)
        key = *(volatile unsigned char *)WIFI_FLAG ? "On" : "Off";
    else if (kind == VK_BLUETOOTH)
        key = *(volatile unsigned char *)BT_FLAG ? "On" : "Off";
    else if (
        kind ==
        VK_EQ) /* Off, the APO / AutoEQ preset that plays (a file name: no key, shown as it is), or the 10-Band EQ's curve (Flat, Rock, Custom: keys) */
        key = !*(volatile unsigned char *)EQ_FLAG ? "Off" : peq_playing_name(buf, sizeof buf) ? buf : "Off";
    else if (kind == VK_THEME)
        key = tape_theme() == 1 ? "Chrome" : tape_theme() == 2 ? "Metal" : "Normal";
    else if (kind == VK_IDLE)
        key = idle_key[idle_choice()];
    else if (kind == VK_RECORD)
        key = record_key[vinyl_record()];
    else if (kind == VK_VTHEME)
        key = vtheme_key[vinyl_theme()];
    else if (kind == VK_BG)
        key = pal_bg_mode() == 1 ? "Tinted" : "Black"; /* (Light, 2 and 3, is not in the picker) */
    else if (kind == VK_ACCENT)
        key = accent_key[pal_accent_saved()];
    else if (kind == VK_REGION) { /* the storefront's name (English in every language), or Automatic */
        pcregion_value(buf, sizeof buf);
        widget_set_text_utf8(label, buf);
        return;
    } else if (kind == VK_LOCKSTYLE) {
        key = lk_layout() == 1 ? "Mini Player" : "Large Cover";
    } else if (
        kind ==
        VK_NA) { /* Off, Albums (the picker says Next Albums: the full text does not fit beside the label in English) */
        key = na_setting() == NA_ALBUMS ? "Albums" : "Off";
    } else if (kind == VK_CHGLIM) { /* "80%" .. "100%" (100: no limit) */
        snprintf(buf, sizeof buf, "%d%%", chg_limit());
        widget_set_text_utf8(label, buf);
        return;
    }
    widget_set_tr_text(label, key);
}

/* The value takes the room its text needs (at most POD_VALUE_MAX), right aligned at the same edge, and the row's label gets the rest. */
static void value_fit(void *win, unsigned i, void *val, int right, int max, int label_x) {
    char name[24];
    const unsigned *text = widget_get_text(val);
    void *lab;
    int vw = text && *text ? (int)(widget_measure_text(val, text) + 0.999f) + 6 : 8;
    if (vw > max) vw = max;
    snprintf(name, sizeof name, "pod_label%u", i);
    lab = widget_lookup(win, name, 1);
    widget_move(val, right - vw, widget_get_prop_int(val, "y", 0));
    widget_resize(val, vw, widget_get_prop_int(val, "h", 0));
    if (lab) widget_resize(lab, right - vw - POD_VALUE_GAP - label_x, widget_get_prop_int(lab, "h", 0));
}

/* The About page's values (docs/modules/settings.md "About"), read the way the stock About page's widget walk does (the callback of systemset_about_page_init, @0x4a1240..0x4a170c): the model and
 * the firmware version are demo's own literals (so the firmware row follows stock), the serial number and the Wi-Fi MAC are the strings product_sncode and wifi_mac, the IP address is
 * networkGetIPAddr while networkGetConnectStatus says connected, and the card's capacity and free space come from getDiskMemoryInfo("/mnt/mmc") once /tmp/mmc_add says a card is in
 * (an empty one reads as stock's 0). Gigabytes with two decimals as stock's "%.2fG", made with integers (no float printf). An empty value reads "-". */
static void disk_gb(float *cap, float *rem) {
    *cap = *rem = 0.0f;
    if (access("/tmp/mmc_add", 4) == 0) getDiskMemoryInfo("/mnt/mmc", cap, rem);
}

static void info_text(void *label, int kind) {
    char buf[64];
    const char *s = buf;
    float cap, rem;
    buf[0] = 0;
    if (kind == INFO_APHOTOS || kind == INFO_ANONE)
        homecover_stat(kind == INFO_APHOTOS ? 7 : 8, buf, sizeof buf);
    else if (kind == INFO_DUR)
        dur_stat(buf, sizeof buf);
    else if (kind == INFO_SFOLD)
        snprintf(buf, sizeof buf, "%d", setfiles_old_count());
    else if (kind >= INFO_SF)
        setfiles_stat(kind - INFO_SF, buf, sizeof buf);
    else if (kind >= INFO_CC)
        homecover_stat(kind - INFO_CC, buf, sizeof buf);
    else if (kind == INFO_TAG)
        s = M1PLUS_TAG;
    else if (kind == INFO_FW)
        s = (const char *)ABOUT_FW;
    else if (kind == INFO_MODEL)
        s = (const char *)ABOUT_MODEL;
    else if (kind == INFO_SN)
        s = (const char *)PRODUCT_SN;
    else if (kind == INFO_MAC)
        s = (const char *)WIFI_MAC;
    else if (kind == INFO_IP) {
        memset(buf, 0, sizeof buf);
        if (networkGetConnectStatus() > 0) networkGetIPAddr(0, buf);
    } else if (kind == INFO_CAP || kind == INFO_FREE) {
        int g;
        disk_gb(&cap, &rem);
        g = (int)((kind == INFO_CAP ? cap : rem) * 100.0f + 0.5f);
        snprintf(buf, sizeof buf, "%d.%02d GB", g / 100, g % 100);
    }
    widget_set_text_utf8(label, s[0] ? s : "-");
}

static int row_value(const struct pod_row *row) {
    return row->action == ACT_STOCK       ? POD_STOCK[row->arg].value
           : row->action == ACT_CTHEME    ? VK_THEME
           : row->action == ACT_IDLE      ? VK_IDLE
           : row->action == ACT_VREC      ? VK_RECORD
           : row->action == ACT_VTHEME    ? VK_VTHEME
           : row->action == ACT_BG        ? VK_BG
           : row->action == ACT_ACCENT    ? VK_ACCENT
           : row->action == ACT_REGION    ? VK_REGION
           : row->action == ACT_PEQ       ? VK_EQ
           : row->action == ACT_CHGLIM    ? VK_CHGLIM
           : row->action == ACT_LOCKSTYLE ? VK_LOCKSTYLE
           : row->action == ACT_NEXTALBUM ? VK_NA
                                          : VK_NONE;
}

/* The chosen picker row: the cassette theme, the vinyl record or base, the background or the accent. */
static int pick_chosen(const struct pod_row *row) {
    return row->action == ACT_IDLESET     ? row->arg == idle_choice()
           : row->action == ACT_RECSET    ? row->arg == vinyl_record()
           : row->action == ACT_BGSET     ? row->arg == pal_bg_mode()
           : row->action == ACT_ACCENTSET ? row->arg == pal_accent_saved()
           : row->action == ACT_REGIONSET ? row->arg == pcregion_saved()
           : row->action == ACT_CHGLIMSET ? row->arg == chg_limit()
           : row->action == ACT_LOCKSET   ? row->arg == lk_layout()
           : row->action == ACT_NASET     ? row->arg == na_setting()
           : row->action == ACT_VTHSET    ? row->arg == vinyl_theme()
                                          : row->arg == tape_theme();
}

static void page_refresh(void *win, const struct pod_page *page) {
    char name[24];
    int i;
    stock_front = (void *)0;
    for (i = 0; i < page->count; i++) {
        const struct pod_row *row = &page->rows[i];
        void *w;
        int kind = row_value(row);
        if (row->action == ACT_STARTUP || row->action == ACT_LANDSCAPE || row->action == ACT_SHELF ||
            row->action == ACT_DAILY || row->action == ACT_KB_EN || row->action == ACT_KB_ZH ||
            row->action == ACT_PCSEARCH || row->action == ACT_BATTPCT || row->action == ACT_AZRAIL ||
            row->action == ACT_AZHEAD || row->action == ACT_LOCKON || row->action == ACT_LOCKTIME ||
            row->action == ACT_VOLKEYS) {
            snprintf(name, sizeof name, "pod_switch%d", i);
            switch_show(widget_lookup(win, name, 1), switch_state(row->action));
        } else if (row->action == ACT_CCLIST || row->action == ACT_SFOLD) {
            /* Cache's No art / Missing, and Unsupported Files: a value; the chevron and the tap only while there is a list to open */
            int on = row->action == ACT_SFOLD ? setfiles_old_count() > 0 : homecover_tappable(row->arg - INFO_CC);
            void *item = widget_lookup(win, row->name, 1),
                 *chev = item ? widget_lookup(item, "pod_chevron", 1) : (void *)0;
            snprintf(name, sizeof name, "pod_value%d", i);
            w = widget_lookup(win, name, 1);
            if (chev) widget_set_visible(chev, on, 0);
            if (item) widget_set_sensitive(item, on);
            if (w) {
                info_text(w, row->arg);
                if (on)
                    value_fit(win, (unsigned)i, w, POD_VALUE_RIGHT, POD_VALUE_MAX, POD_INFO_LABEL_X);
                else
                    value_fit(win, (unsigned)i, w, POD_INFO_RIGHT, POD_INFO_MAX, POD_INFO_LABEL_X);
            }
        } else if (row->action == ACT_INFO || row->action == ACT_SFDEL) {
            snprintf(name, sizeof name, "pod_value%d", i);
            w = widget_lookup(win, name, 1);
            if (w)
                info_text(w, row->arg), value_fit(win, (unsigned)i, w, POD_INFO_RIGHT, POD_INFO_MAX, POD_INFO_LABEL_X);
            if (row->action == ACT_SFDEL) { /* a setting file's row takes the tap only while its file is there */
                void *item = widget_lookup(win, row->name, 1);
                if (item) widget_set_sensitive(item, setfiles_present(row->arg - INFO_SF));
            }
        } else if (kind) {
            snprintf(name, sizeof name, "pod_value%d", i);
            w = widget_lookup(win, name, 1);
            if (w)
                value_text(w, kind),
                    value_fit(win, (unsigned)i, w, POD_VALUE_RIGHT, POD_VALUE_MAX,
                              row->action == ACT_REGION ? POD_INFO_LABEL_X
                                                        : POD_LABEL_X); /* (the Podcast Region row has no glyph) */
        } else if (is_pick(row)) {
            snprintf(name, sizeof name, "pod_check%d", i);
            w = widget_lookup(win, name, 1);
            if (w) widget_set_visible(w, pick_chosen(row), 0);
            if (row->action == ACT_REGIONSET && row->arg == 0) { /* Automatic names the storefront it gives */
                char label[64];
                snprintf(name, sizeof name, "pod_label%d", i);
                w = widget_lookup(win, name, 1);
                pcregion_auto_label(label, sizeof label);
                if (w) widget_set_text_utf8(w, label);
            }
        }
    }
}

/* A page whose values changed on their own (the Cache page's counts and status): read them again. */
void pod_page_refresh(int index) {
    if (index >= 0 && index < POD_PAGE_COUNT && pod_fg[index]) page_refresh(pod_fg[index], &POD_PAGES[index]);
}

/* A picker row (Cassette Theme, Record, Background, Accent): choose it (saved first: a failed save leaves the old choice and its check), then the checks follow. */
static void pick_choose(const struct pod_row *row) {
    void *win = (void *)0;
    int i;
    for (i = 0; i < POD_PAGE_COUNT; i++)
        if (POD_PAGES[i].rows && row >= POD_PAGES[i].rows && row < POD_PAGES[i].rows + POD_PAGES[i].count) {
            if ((row->action == ACT_IDLESET     ? idle_set(row->arg)
                 : row->action == ACT_RECSET    ? vinyl_record_set(row->arg)
                 : row->action == ACT_BGSET     ? pal_bg_set(row->arg)
                 : row->action == ACT_ACCENTSET ? pal_accent_set(row->arg)
                 : row->action == ACT_REGIONSET ? pcregion_set(row->arg)
                 : row->action == ACT_CHGLIMSET ? chg_set(row->arg)
                 : row->action == ACT_LOCKSET   ? lk_layout_set(row->arg)
                 : row->action == ACT_NASET     ? na_set(row->arg)
                 : row->action == ACT_VTHSET    ? vinyl_theme_set(row->arg)
                                                : tape_theme_set(row->arg)) >= 0) {
                win = pod_fg[i];
                if (win) page_refresh(win, &POD_PAGES[i]);
            }
            return;
        }
}

/* Each of our pages with rows to refresh keeps its window here (the page is open once: a settings page opens over its parent, never twice), for the window's
 * foreground event and for pick_choose. */
static int on_page_fg(void *ctx, void *e) {
    long i = (long)ctx;
    (void)e;
    if (pod_fg[i]) page_refresh(pod_fg[i], &POD_PAGES[i]);
    return RET_OK;
}

static int on_page_gone(void *ctx, void *e) {
    long i = (long)ctx;
    (void)e;
    pod_fg[i] = (void *)0;
    return RET_OK;
}

/* Open POD_PAGES[index]; 0 once its window is up, -1 if AWTK could not open the asset. as_home: the entry
 * page as the Home instance (no navbar); 0 gives the normal instance with Back. */
static int open_page(int index, int as_home) {
    const struct pod_page *page;
    void *win;
    int i, refresh = 0;
    if (index < 0 || index >= POD_PAGE_COUNT) return -1;
    page = &POD_PAGES[index];
    win = window_open(page->asset);
    if (!win) return -1;
    if (index == POD_FILES_PAGE) setfiles_open(); /* the files, read once as the page opens */
    for (i = 0; i < 32; i++)
        if (page->wrap_notes >> i & 1) { /* a note of more than one line is a plain label: its wrap is on at run time */
            char nm[16];
            void *note;
            snprintf(nm, sizeof nm, "pod_note%d_t", i);
            note = widget_lookup(win, nm, 1);
            if (note) label_set_line_wrap(note, 1);
        }
    if (index == POD_CACHE_PAGE) dur_stat_open(); /* the track table's header, read once as the page opens */
    if (index !=
        POD_PEQBAND_PAGE) { /* the band page asks about unsaved changes first: it binds both itself (patch/peqband.c) */
        pod_bind(win, "btn_return", pod_on_back, (void *)0);
        pod_bind(win, "btn_backtoplayer", pod_on_player, (void *)0);
    }
    for (i = 0; i < page->count; i++) {
        const struct pod_row *row = &page->rows[i];
        if (row->action == ACT_STARTUP || row->action == ACT_LANDSCAPE || row->action == ACT_SHELF ||
            row->action == ACT_DAILY || row->action == ACT_KB_EN || row->action == ACT_KB_ZH ||
            row->action == ACT_PCSEARCH || row->action == ACT_BATTPCT || row->action == ACT_AZRAIL ||
            row->action == ACT_AZHEAD || row->action == ACT_LOCKON || row->action == ACT_LOCKTIME ||
            row->action == ACT_VOLKEYS)
            bind_switch(win, i, row), refresh = 1;
        else {
            if (row->action != ACT_INFO) pod_bind(win, row->name, on_row, row); /* an information row takes no tap */
            if (row->action == ACT_INFO || row->action == ACT_SFDEL || row->action == ACT_CCLIST ||
                row->action == ACT_SFOLD || row_value(row) || is_pick(row))
                refresh = 1;
        }
        if (row->action == ACT_REGEN) {
            regen_row = widget_lookup(win, row->name, 1);
            regen_note = widget_lookup(win, "pod_note3", 1);
            regen_show();
        }
    }
    if (refresh) { /* the state the page shows, now and each time it is back in front */
        pod_fg[index] = win;
        page_refresh(win, page);
        widget_on(win, EVT_WINDOW_TO_FG, on_page_fg, (void *)(long)index);
        widget_on(win, EVT_DESTROY, on_page_gone, (void *)(long)index);
    }
    if (index == POD_CACHE_PAGE)
        homecover_cache_open(win, index); /* counts the cache folder in steps while the page is open */
    if (index == POD_MENU_PAGE) {
        menu_arrange(win, 0);
        widget_on(win, EVT_WINDOW_TO_FG, on_menu_fg, win); /* back in front after the Main Menu page: arrange again */
    } else if (index == POD_EXTRAS_PAGE) {
        menu_arrange(win, 1);
        home_extras_opened(win);
        pod_bind(win, "btn_settings", on_settings,
                 (void *)0); /* the navbar's Settings button (a missing one: stock-safe, nothing happens) */
    } else if (index == POD_MENUCFG_PAGE)
        menu_custom_opened(win);
    else if (index == POD_PULLDOWN_PAGE)
        pulldown_page_opened(win);
    else if (index == POD_EXTRASCFG_PAGE)
        menu_extras_opened(win);
    else if (index == POD_PEQ_PAGE)
        peq_opened(win);
    else if (index == POD_PEQP_PAGE)
        peqpage_opened(win);
    else if (index == POD_PEQLIB_PAGE)
        peqlib_opened(win);
    else if (index == POD_TENBAND_PAGE)
        tenband_opened(win);
    else if (index == POD_TENCURVE_PAGE)
        tencurve_opened(win);
    else if (index == POD_TENPREAMP_PAGE)
        tenpreamp_opened(win);
    else if (index == POD_PEQBAND_PAGE)
        peqband_opened(win);
    else if (index == POD_SUBSONIC_PAGE)
        sb_page_open(win);
    { /* the Settings page is the way out to the grid; the menu may be the Home instance (no navbar) */
        int entry = as_home && index == POD_ENTRY_PAGE;
        if (index == POD_SETTINGS_PAGE || entry) home_menu_opened(win, index == POD_SETTINGS_PAGE, entry);
    }
    return 0;
}

int m1plus_open_entry(void) { return open_page(POD_ENTRY_PAGE, 1); }

/* The Settings page, for the iPod page's Settings row (patch/ipod.c): the normal instance, with Back, over whatever is in front. */
int pod_open_settings(void) { return open_page(POD_SETTINGS_PAGE, 0); }

/* The Lock Screen page, for stock's Display page Lock Screen row (patch/lockscreen.c lk_redirect): the normal instance, with Back. */
int pod_open_lock(void) { return open_page(POD_LOCK_PAGE, 0); }

/* The preset page, for the Presets page's rows (patch/peqpage.c): the normal instance, with Back. */
int pod_open_peqpage(void) { return open_page(POD_PEQP_PAGE, 0); }

/* The Equalizer page, for the All Playback Settings Equalizer row (patch/peq_ui.c peq_open): the normal instance, with Back. */
int pod_open_peq(void) { return open_page(POD_PEQ_PAGE, 0); }

/* The 10-Band editor and its Curve and Preamp pages (patch/tenband.c): the normal instance, with Back. */
int pod_open_tenband(void) { return open_page(POD_TENBAND_PAGE, 0); }
int pod_open_tencurve(void) { return open_page(POD_TENCURVE_PAGE, 0); }
int pod_open_tenpreamp(void) { return open_page(POD_TENPREAMP_PAGE, 0); }

/* The band page of a preset (patch/peqband.c): the normal instance, with Back. */
int pod_open_peqband(void) { return open_page(POD_PEQBAND_PAGE, 0); }

/* The Presets page, for the Equalizer page's Presets card (patch/peqlib.c): the normal instance, with Back. */
int pod_open_peqlib(void) { return open_page(POD_PEQLIB_PAGE, 0); }

/* Recovery: while the boot guard's bad note exists the grid has no M1+ Music icon (it is boot-created), so the
 * Tidal icon (id 1) opens the menu (normal instance, with Back) to reach Settings > Developer > Boot to M1+ Music (Settings is
 * a menu item that can be hidden from the default list, but the menu then still shows Extras, whose navbar has the Settings button). */
#define TIDAL_ID 1
static int recovery_tap(int id) { return id == TIDAL_ID && access(BAD_NOTE, F_OK) == 0; }

/* Installed over the stock Home icon click dispatcher's PIC prologue (tools/pod.py). */
int m1plus_home_click(void *icon, void *e) {
    const char *name = icon ? *(const char **)((char *)icon + W_NAME) : (const char *)0;
    int id = (name && name[0]) ? atoi(name) : -1;
    if (id == POD_ENTRY_ID && !pod_off()) {
        int restored = home_restore(); /* after "Shanling Home": this tap makes M1+ Music Home again */
        if (open_page(POD_ENTRY_PAGE, 1) == 0) return RET_OK;
        home_restore_failed(restored);
    } else if (recovery_tap(id) && !pod_off()) {
        if (open_page(POD_ENTRY_PAGE, 0) == 0) return RET_OK;
    }
    return stock_home_click_trampoline(icon, e);
}
