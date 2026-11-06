/* The payload's own files, for Settings > Developer > Tools > Settings Files (docs/modules/settings.md "Settings Files").
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * The page is an ACT_INFO page like Cover Cache's: setfiles_open reads every file once when the page opens (open, read, close,
 * access; nothing at paint, no timer) into a small table, and setfiles_stat hands a row its text. The rows follow tools/pod_pages.py
 * SETTINGS_FILES_PAGE: the guard files, the settings folder, one row per setting file.
 */
#include "offsets.inc"
#include "stock.h"
#include "home.h"
#include "battery.h"
#include "ipod_theme.h"
#include "radio.h"

enum { K_CHAR, K_PRESENT, K_MENU, K_LINES };

struct sf_file {
    const char *path;
    char kind;
};

/* The order of the page's rows (INFO_SF + index): 4 guard files, the folder, 20 settings. */
static const struct sf_file sf_files[] = {
    {START_FILE, K_CHAR},      {MARKER, K_PRESENT},      {BAD_NOTE, K_PRESENT},         {KILL_DATA, K_PRESENT},
    {SET_DIR, K_PRESENT},      {ALBUMS_FILE, K_CHAR},    {PLAYLISTS_FILE, K_CHAR},      {RECENTADD_VIEW_FILE, K_CHAR},
    {CFSORT_FILE, K_CHAR},     {LANDSCAPE_FILE, K_CHAR}, {TAPETHEME_FILE, K_CHAR},      {VINYLREC_FILE, K_CHAR},
    {VINYLTHEME_FILE, K_CHAR}, {IP_THEME_FILE, K_CHAR},  {SHELF_FILE, K_CHAR},          {DAILY_SET_FILE, K_CHAR},
    {MENU_FILE, K_MENU},       {PULLDOWN_FILE, K_MENU},  {KBZH_FILE, K_CHAR},           {PCSEARCH_FILE, K_CHAR},
    {BP_FILE, K_CHAR},         {SHUFFLE_FILE, K_CHAR},   {SEARCH_RECENT_FILE, K_LINES}, {RD_RECENT_FILE, K_PRESENT},
    {REBUILD_FILE, K_PRESENT},
};
#define SF_FILES (sizeof sf_files / sizeof sf_files[0])

static char sf_val[SF_FILES][24] __attribute__((section(".scratch")));

static void sf_read(const struct sf_file *f, char *out) {
    char b[512];
    int fd, n, lines = 0, i;
    if (f->kind == K_PRESENT) {
        snprintf(out, 24, "%s", access(f->path, F_OK) == 0 ? "present" : "missing");
        return;
    }
    fd = open(f->path, O_RDONLY, 0);
    if (fd < 0) {
        snprintf(out, 24, "missing");
        return;
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
    } else {
        n = read(fd, b, 3);
        if (n == 1 || (n == 2 && b[1] == '\n')) {
            out[0] = b[0] >= ' ' && b[0] < 127 ? b[0] : '?';
            out[1] = 0;
        } else
            snprintf(out, 24, n <= 0 ? "empty" : "other");
    }
    close(fd);
}

/* The page is opening: read everything once. */
void setfiles_open(void) {
    unsigned i;
    for (i = 0; i < SF_FILES; i++) sf_read(&sf_files[i], sf_val[i]);
}

/* Row idx's text (0 .. SF_FILES - 1), as read when the page opened. */
void setfiles_stat(int idx, char *buf, unsigned n) {
    snprintf(buf, n, "%s", idx >= 0 && (unsigned)idx < SF_FILES ? sf_val[idx] : "");
}
