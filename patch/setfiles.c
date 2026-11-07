/* The payload's own files, for Settings > Developer > Tools > Settings Files (docs/modules/settings.md "Settings Files").
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * The page is an ACT_INFO page like Cache's: setfiles_open reads every file once when the page opens (open, read, close,
 * access; nothing at paint, no timer) into a small table, and setfiles_stat hands a row its text. The rows follow tools/pod_pages.py
 * FILES_PAGE: the guard files, the settings folder, one row per setting file. A setting file's row is tappable while the file is
 * there (ACT_SFDEL, patch/m1plus.c): a confirm, then setfiles_delete removes that file and reads that row again. The guard files
 * and the folder are never deleted; a value already shown stays until its row is read again (a delete, or the device restarts).
 *
 * Unsupported Files: the retired table below names the settings files older builds left behind (each with its .tmp sibling). setfiles_open
 * checks them with access() once, as the page opens, and keeps the result in memory: the page's count (setfiles_old_count) and the list
 * (patch/covlist.c, setfiles_old_present / setfiles_old_name) read nothing, and a delete (setfiles_old_delete, setfiles_old_delete_all)
 * unlinks and checks again. The guard files and the current setting files are never in the table (tests: unsupported_tests).
 */
#include "offsets.inc"
#include "stock.h"
#include "home.h"
#include "battery.h"
#include "tracklamp.h"
#include "ipod_theme.h"
#include "radio.h"
#include "pcregion.h"
#include "peq.h"

enum { K_CHAR, K_PRESENT, K_MENU, K_LINES, K_TEXT };

struct sf_file {
    const char *path;
    char kind;
};

/* The order of the page's rows (INFO_SF + index): 4 guard files, the folder, then the 33 setting files from SF_SETTING on. */
static const struct sf_file sf_files[] = {
    {START_FILE, K_CHAR},
    {MARKER, K_PRESENT},
    {BAD_NOTE, K_PRESENT},
    {KILL_DATA, K_PRESENT},
    {SET_DIR, K_PRESENT},
    {ALBUMS_FILE, K_CHAR},
    {ALBUMS_SORT_FILE, K_CHAR},
    {ARTISTS_SORT_FILE, K_CHAR},
    {GENRES_SORT_FILE, K_CHAR},
    {COMPOSERS_SORT_FILE, K_CHAR},
    {SONGS_SORT_FILE, K_CHAR},
    {FOLDERS_SORT_FILE, K_CHAR},
    {PLAYLISTS_SORT_FILE, K_CHAR},
    {PLAYLISTS_FILE, K_CHAR},
    {RECENTADD_VIEW_FILE, K_CHAR},
    {LANDSCAPE_FILE, K_CHAR},
    {TAPETHEME_FILE, K_CHAR},
    {VINYLREC_FILE, K_CHAR},
    {VINYLTHEME_FILE, K_CHAR},
    {IP_THEME_FILE, K_CHAR},
    {ACCENT_FILE, K_CHAR},
    {BG_FILE, K_CHAR},
    {SHELF_FILE, K_CHAR},
    {DAILY_SET_FILE, K_CHAR},
    {MENU_FILE, K_MENU},
    {PULLDOWN_FILE, K_MENU},
    {KBZH_FILE, K_CHAR},
    {PCSEARCH_FILE, K_CHAR},
    {PCREGION_FILE, K_TEXT},
    {BP_FILE, K_CHAR},
    {TL_FILE, K_CHAR},
    {SHUFFLE_FILE, K_CHAR},
    {PEQ_STATE, K_PRESENT},
    {SEARCH_RECENT_FILE, K_LINES},
    {RD_VIEW_FILE, K_CHAR},
    {RD_RECENT_FILE, K_PRESENT},
    {REBUILD_FILE, K_PRESENT},
    {WIFINET_FILE, K_PRESENT},
};
#define SF_FILES (sizeof sf_files / sizeof sf_files[0])
#define SF_SETTING 5 /* the first setting file's row: the rows before it (guard files, folder) are never deleted */

static char sf_val[SF_FILES][24] __attribute__((section(".scratch")));
/* 1 when the file was there at the last read */
static unsigned char sf_has[SF_FILES] __attribute__((section(".scratch")));

/* Reads one row's file into out; returns 1 when the file is there. */
static int sf_read(const struct sf_file *f, char *out) {
    char b[512];
    int fd, n, lines = 0, i;
    if (f->kind == K_PRESENT) {
        int there = access(f->path, F_OK) == 0;
        snprintf(out, 24, "%s", there ? "present" : "missing");
        return there;
    }
    fd = open(f->path, O_RDONLY, 0);
    if (fd < 0) {
        snprintf(out, 24, "missing");
        return 0;
    }
    if (f->kind == K_LINES) {
        while ((n = read(fd, b, sizeof b)) > 0)
            for (i = 0; i < n; i++)
                if (b[i] == '\n') lines++;
        snprintf(out, 24, "%d", lines);
    } else if (f->kind == K_MENU) {
        n = read(fd, b, 16);
        if (n > 0 && b[n - 1] == '\n') n--;
        if (n <= 0) {
            snprintf(out, 24, "empty");
        } else {
            for (i = 0; i < n && i < 12; i++) out[i] = b[i] >= ' ' && b[i] < 127 ? b[i] : '?';
            out[i] = 0;
            if (n > 12) snprintf(out + 12, 12, "\xe2\x80\xa6");
        }
    } else if (f->kind == K_TEXT) { /* a short word (the Podcast Region's two letters) */
        n = read(fd, b, 8);
        if (n > 0 && b[n - 1] == '\n') n--;
        if (n <= 0 || n > 4)
            snprintf(out, 24, n <= 0 ? "empty" : "other");
        else {
            for (i = 0; i < n; i++) out[i] = b[i] >= ' ' && b[i] < 127 ? b[i] : '?';
            out[i] = 0;
        }
    } else {
        n = read(fd, b, 3);
        if (n == 1 || (n == 2 && b[1] == '\n')) {
            out[0] = b[0] >= ' ' && b[0] < 127 ? b[0] : '?';
            out[1] = 0;
        } else
            snprintf(out, 24, n <= 0 ? "empty" : "other");
    }
    close(fd);
    return 1;
}

/* The retired files: the settings files of older builds, nothing in this build reads or writes them (docs/modules/settings.md "Settings
 * Files", Unsupported Files). Each name is listed once here; its .tmp sibling is the next entry. Only this table names these paths (tests). */
static const char *const sf_retired[] = {
    "/mnt/data/m1plus-albums",         "/mnt/data/m1plus-playlists",
    "/mnt/data/m1plus-cfsort",         "/mnt/data/m1plus-landscape",
    "/mnt/data/m1plus-tapetheme",      "/mnt/data/m1plus-vinylrec",
    "/mnt/data/m1plus-vinyltheme",     "/mnt/data/m1plus-menu",
    "/mnt/data/m1plus-recent",         "/mnt/data/m1plus-search-recent",
    "/mnt/data/m1plus-shelf",          "/mnt/data/m1plus-daily",
    "/mnt/data/m1plus-covers-rebuild", "/mnt/data/m1plus-kbzh",
    "/mnt/data/m1plus-pcsearch",       "/mnt/data/m1plus-battpct",
    "/mnt/data/m1plus-pod-theme",      "/mnt/data/m1plus-mix",
    "/mnt/data/m1plus-mix.art",        "/mnt/data/m1plus/recently-played",
};
#define SF_RETIRED (sizeof sf_retired / sizeof sf_retired[0])
#define SF_OLD (2 * SF_RETIRED) /* entry k: sf_retired[k / 2], and its .tmp sibling when k is odd */
/* 1 when entry k was there at the last check */
static unsigned char sf_old_has[SF_OLD] __attribute__((section(".scratch")));

/* Entry k's path (its name, or the .tmp sibling for an odd k) into out; 0 when k is out of range. */
int setfiles_old_name(unsigned k, char *out, unsigned n) {
    if (k >= SF_OLD) return 0;
    snprintf(out, n, "%s%s", sf_retired[k / 2], (k & 1) ? ".tmp" : "");
    return 1;
}

static int sf_old_there(unsigned k) {
    char p[96];
    return setfiles_old_name(k, p, sizeof p) && access(p, F_OK) == 0;
}

/* The page is opening: read everything once. */
void setfiles_open(void) {
    unsigned i, k;
    for (i = 0; i < SF_FILES; i++) sf_has[i] = (unsigned char)sf_read(&sf_files[i], sf_val[i]);
    for (k = 0; k < SF_OLD; k++) sf_old_has[k] = (unsigned char)sf_old_there(k);
}

/* Unsupported Files: how many retired entries were there at the last check (memory only). */
int setfiles_old_count(void) {
    unsigned k, c = 0;
    for (k = 0; k < SF_OLD; k++) c += sf_old_has[k];
    return (int)c;
}

/* The number of entries (the list walks them in this order) and whether entry k was there at the last check. */
unsigned setfiles_old_n(void) { return SF_OLD; }
int setfiles_old_present(unsigned k) { return k < SF_OLD && sf_old_has[k]; }

/* Deletes entry k, then checks it again: 0 when it is gone (a file already gone counts), -1 when it is still there or k is out of range. */
int setfiles_old_delete(unsigned k) {
    char p[96];
    if (!setfiles_old_name(k, p, sizeof p)) return -1;
    unlink(p);
    sf_old_has[k] = (unsigned char)sf_old_there(k);
    return sf_old_has[k] ? -1 : 0;
}

/* Delete Unsupported Files: every entry is tried (a file that appeared since the check goes too); 0 when none is left, else -1. */
int setfiles_old_delete_all(void) {
    unsigned k;
    int left = 0;
    for (k = 0; k < SF_OLD; k++)
        if (setfiles_old_delete(k) != 0) left = 1;
    return left ? -1 : 0;
}

/* Row idx's text (0 .. SF_FILES - 1), as read when the page opened. */
void setfiles_stat(int idx, char *buf, unsigned n) {
    snprintf(buf, n, "%s", idx >= 0 && (unsigned)idx < SF_FILES ? sf_val[idx] : "");
}

/* Whether row idx's file was there when it was last read: a setting row is tappable (ACT_SFDEL) only then. */
int setfiles_present(int idx) { return idx >= 0 && idx < (int)SF_FILES && sf_has[idx]; }

/* Deletes row idx's setting file, then reads that row again. Refused (-1) for the guard files and the folder (idx below SF_SETTING)
 * and for an index out of range, and when the file is still there after unlink (-1). A file that is already gone counts as deleted. */
int setfiles_delete(int idx) {
    if (idx < SF_SETTING || idx >= (int)SF_FILES) return -1;
    if (unlink(sf_files[idx].path) != 0 && access(sf_files[idx].path, F_OK) == 0) return -1;
    sf_has[idx] = (unsigned char)sf_read(&sf_files[idx], sf_val[idx]);
    return 0;
}

#define SF_RESET_MAX 256

/* 1 when an entry other than . and .. is still in the settings folder (or more than SF_RESET_MAX of them), or the folder exists but
 * cannot be opened again; 0 when it is empty or gone. */
static int sf_folder_left(void) {
    void *d = opendir(SET_DIR);
    char *ent;
    int n = 0;
    if (!d) return access(SET_DIR, F_OK) == 0;
    while ((ent = readdir(d)) != (char *)0) {
        const char *name = ent + 11;
        if (name[0] == '.' && (name[1] == 0 || (name[1] == '.' && name[2] == 0))) continue;
        if (++n > SF_RESET_MAX) break;
    }
    closedir(d);
    return n != 0;
}

/* Settings > Developer > Tools > Reset All Settings (docs/modules/settings.md "Reset All Settings"): every entry of the settings folder
 * is unlinked (names this build does not know too; no recursion, the folder stays), then the retired entries. The guard files in
 * /mnt/data and the card (/mnt/mmc) are never listed here. A missing folder is nothing to do. Returns 0 when every entry is gone,
 * -1 when one remains, the folder holds more than SF_RESET_MAX entries, or it cannot be read (opendir fails while the folder
 * exists, or readdir stops early and the folder is read again with entries left). Nothing is re-read: the page's values
 * stay until it opens again, and the settings are read again at the next start. */
int setfiles_reset_all(void) {
    void *d = opendir(SET_DIR);
    int bad = 0, n = 0;
    char *ent;
    if (!d && access(SET_DIR, F_OK) == 0) bad = 1; /* the folder is there but cannot be read */
    if (d) {
        while ((ent = readdir(d)) != (char *)0) {
            /* struct dirent: d_type at 10, d_name at 11 (at most 255 bytes) */
            const char *name = ent + 11;
            char path[300];
            if (name[0] == '.' && (name[1] == 0 || (name[1] == '.' && name[2] == 0))) continue;
            if (n == SF_RESET_MAX) { /* more entries than the bound: the rest stays */
                bad = 1;
                break;
            }
            snprintf(path, sizeof path, SET_DIR "/%s", name);
            if (unlink(path) != 0 && access(path, F_OK) == 0) bad = 1;
            ++n;
        }
        closedir(d);
        if (sf_folder_left()) bad = 1; /* readdir may have stopped early, or an unlink failed */
    }
    if (setfiles_old_delete_all() != 0) bad = 1;
    return bad ? -1 : 0;
}
