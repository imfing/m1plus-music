/* M1+ Music Screenshot: a developer's screen grab from the Extras page (docs/modules/screenshot.md).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * A tap on the Screenshot row (Settings > Developer) asks in the stock confirm dialog; Yes starts a payload-owned countdown (5 s or 10 s, chosen in the dialog, one stock timer, so the user can
 * leave the page and go where the picture should be), shows a camera in the status bar while it runs, and then
 * writes what is on the panel to /mnt/mmc/screenshots/shot-NNNN.bmp (24 bit, bottom-up). No stock function is
 * hooked and nothing runs unless that row was tapped: no thread, no paint hook, no main loop work; the timers exist only
 * between the tap and the toast that ends the capture.
 *
 * The grab reads the frame buffer, the one thing that is exactly what is on screen (status bar, dialogs, Cover Flow's
 * own drawing). Stock opens /dev/fb0 in lcd_linux_fb_create (0x6393dc) and learns the format with FBIOGET_VSCREENINFO
 * and FBIOGET_FSCREENINFO (0x4600, 0x4602); the payload does the same on its own descriptor and maps the same memory
 * read-only, and reads the visible buffer (yoffset, which FBIOPAN_DISPLAY moves when the lcd is double buffered). The
 * format is never assumed: 16, 24 or 32 bits per pixel with the channel positions the driver reports (stock picks its
 * lcd_mem_* class from the same fields); anything it cannot read exactly is a failure, never a wrong picture.
 * widget_take_snapshot_rect (0x671cb8) was the alternative: it repaints the widget tree into a new bitmap instead of
 * reading the screen, so dialogs, the status bar and the pages' own after-paint drawing depend on which widget is
 * handed in.
 *
 * Order of a capture: the last countdown tick hides the status bar camera (widget_set_visible invalidates it), and
 * the grab runs from a second one-shot SHOT_SETTLE_MS later, so the main loop has repainted the bar and the frame
 * buffer no longer holds it; only then is the card checked (mounted, SHOT_MIN_FREE_MB free), the frame written to
 * a temp file, fsynced and renamed, and the toast shown (after the grab, so it is not in the picture). Every
 * failure leaves no partial file and ends in a toast; the camera is hidden on every path.
 */
#include "offsets.inc"
#include "stock.h"
#include "home.h"
#include "common.h"
#include "i18n.h"
#include "shot.h"
#include "lineout.h"

#define BMP_HEADER 54

enum {
    SH_IDLE,
    SH_ASK,
    SH_COUNT,
    SH_ASK_CANCEL,
    SH_GRAB
}; /* nothing pending, asking to start, counting down, asking to cancel, waiting for the repaint */
enum { R_OK, R_STORAGE, R_FAIL }; /* a saved file; no card / no room; the frame buffer or the write */

static struct {
    int phase;
    int left; /* countdown ticks to go */
    int tries; /* looks for the dialog by the relabel timer */
    unsigned timer; /* the tick timer while it runs, else 0 */
} sh __attribute__((section(".scratch")));

/* The status bar camera, found by name from the window manager (it is a child of the system bar's right group, hidden
 * in the asset). Missing, or no window manager: no indicator, the capture goes on. Shown only with room beside stock's marks, left of the centred clock (patch/lineout.c lo_shot_fits; its
 * 1 s bar tick hides it if the room goes while it counts). */
static void indicator(int on) {
    void *wm = window_manager(), *w = wm ? widget_lookup(wm, SHOT_IND, 1) : (void *)0;
    if (w) widget_set_visible(w, on && lo_shot_fits(w), 0);
}

static void finish(void) {
    indicator(0);
    sh.phase = SH_IDLE;
    sh.timer = 0;
}

/* 8 bit value of the len bit channel field at off of px (len 4..8, the bits replicated like the stock expansion). */
static unsigned chan(unsigned px, unsigned off, unsigned len) {
    unsigned c = (px >> off) & ((1u << len) - 1);
    return len == 8 ? c : (c << (8 - len)) | (c >> (2 * len - 8));
}

static void put32(unsigned char *p, unsigned v) {
    p[0] = (unsigned char)v;
    p[1] = (unsigned char)(v >> 8);
    p[2] = (unsigned char)(v >> 16);
    p[3] = (unsigned char)(v >> 24);
}

/* The 54 byte header of a w x h, 24 bit, bottom-up BMP whose rows are `stride` bytes. */
static void bmp_header(unsigned char *p, unsigned w, unsigned h, unsigned stride) {
    memset(p, 0, BMP_HEADER);
    p[0] = 'B';
    p[1] = 'M';
    put32(p + 2, BMP_HEADER + stride * h);
    put32(p + 10, BMP_HEADER);
    put32(p + 14, 40); /* BITMAPINFOHEADER */
    put32(p + 18, w);
    put32(p + 22, h);
    p[26] = 1; /* planes */
    p[28] = 24;
    put32(p + 34, stride * h);
    put32(p + 38, 2835);
    put32(p + 42, 2835); /* 72 dpi */
}

/* The next free shot-NNNN.bmp in the directory; 0 when all SHOT_MAX_NUM exist. */
static unsigned next_number(char *path, unsigned n) {
    unsigned i;
    for (i = 1; i <= SHOT_MAX_NUM; i++) {
        snprintf(path, n, SHOT_DIR "/shot-%04d.bmp", (int)i);
        if (access(path, F_OK)) return i;
    }
    return 0;
}

/* Whether the card is mounted (its mount point is another file system than the one it is in) and has room for the file. */
static int storage_ok(unsigned bytes) {
    unsigned a[32];
    if (!m1_card_mounted()) return 0;
    mkdir(SHOT_DIR, 0755);
    if (access(SHOT_DIR, F_OK) || statfs(SHOT_DIR, a)) return 0;
    return (unsigned long long)a[7] * a[1] >=
           ((unsigned long long)SHOT_MIN_FREE_MB << 20) + bytes; /* f_bavail * f_bsize */
}

/* The frame at fb (rows `line` bytes apart, `bytes` per pixel, channels at the offsets / lengths in c) as the BMP. */
static int write_bmp(const unsigned char *fb, unsigned w, unsigned h, unsigned line, unsigned bytes,
                     const unsigned *c) {
    unsigned char hdr[BMP_HEADER], row[SHOT_MAX_DIM * 3 + 4];
    unsigned stride = (w * 3 + 3) & ~3u, y, x;
    char path[48];
    int fd, ok;
    if (!storage_ok(BMP_HEADER + stride * h)) return R_STORAGE;
    if (!next_number(path, sizeof path)) return R_FAIL;
    fd = open(SHOT_TMP, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (fd < 0) return R_STORAGE;
    memset(row, 0, sizeof row); /* the pad bytes of a row stay zero */
    bmp_header(hdr, w, h, stride);
    ok = write(fd, hdr, BMP_HEADER) == BMP_HEADER;
    for (y = h; ok && y--;) { /* bottom-up */
        const unsigned char *s = fb + y * line;
        unsigned char *o = row;
        for (x = 0; x < w; x++, s += bytes, o += 3) {
            unsigned px = s[0] | s[1] << 8 | (bytes > 2 ? s[2] << 16 : 0) | (bytes > 3 ? (unsigned)s[3] << 24 : 0);
            o[0] = (unsigned char)chan(px, c[FBV_BLUE - FBV_RED + 0], c[FBV_BLUE - FBV_RED + 1]);
            o[1] = (unsigned char)chan(px, c[FBV_GREEN - FBV_RED + 0], c[FBV_GREEN - FBV_RED + 1]);
            o[2] = (unsigned char)chan(px, c[0], c[1]);
        }
        ok = write(fd, row, stride) == (int)stride;
    }
    return m1_commit(fd, ok, SHOT_TMP, path) ? R_OK : R_FAIL; /* (no partial file) */
}

/* Read the panel: its format from the driver, the visible buffer mapped read-only, written out. */
static int capture(void) {
    unsigned v[FBV_WORDS], f[FBF_WORDS], w, h, bpp, line, yoff, len, i;
    const unsigned char *map;
    int fd, rc;
    memset(v, 0, sizeof v);
    memset(f, 0, sizeof f);
    fd = open(SHOT_FB, O_RDONLY, 0);
    if (fd < 0) return R_FAIL;
    if (ioctl(fd, FBIOGET_VSCREENINFO, v) || ioctl(fd, FBIOGET_FSCREENINFO, f)) {
        close(fd);
        return R_FAIL;
    }
    w = v[FBV_XRES];
    h = v[FBV_YRES];
    bpp = v[FBV_BPP];
    line = f[FBF_LINE_LENGTH];
    yoff = v[FBV_YOFFSET];
    len = f[FBF_SMEM_LEN];
    for (i = 0; i < 3; i++) { /* red, green, blue: 4..8 bit fields inside the pixel */
        unsigned off = v[FBV_RED + 3 * i], n = v[FBV_RED + 3 * i + 1];
        if (n < 4 || n > 8 || off + n > bpp) {
            close(fd);
            return R_FAIL;
        }
    }
    if (!w || !h || w > SHOT_MAX_DIM || h > SHOT_MAX_DIM || (bpp != 16 && bpp != 24 && bpp != 32) ||
        line < w * (bpp / 8) || yoff + h > v[FBV_YRES_VIRTUAL] || (unsigned long long)(yoff + h) * line > len) {
        close(fd);
        return R_FAIL;
    }
    map = mmap((void *)0, len, PROT_READ, MAP_SHARED, fd, 0);
    close(fd); /* the mapping outlives the descriptor */
    if (map == (const unsigned char *)MAP_FAILED) return R_FAIL;
    rc = write_bmp(map + yoff * line, w, h, line, bpp / 8, v + FBV_RED);
    munmap((void *)map, len);
    return rc;
}

/* The grab, SHOT_SETTLE_MS after the camera was hidden. Runs once, then the toast. */
static int shot_grab(const void *timer) {
    const char *msg;
    int rc;
    (void)timer;
    rc = capture();
    finish();
    if (rc == R_OK)
        msg = TR("Screenshot saved");
    else if (rc == R_STORAGE)
        msg = TR("Storage unavailable");
    else
        msg = TR("Screenshot failed");
    pod_toast(msg);
    return RET_OK;
}

static int shot_tick(const void *timer) {
    (void)timer;
    if (--sh.left > 0) return RET_REPEAT;
    indicator(0); /* out of the frame before it is read */
    sh.timer = 0; /* this timer ends below */
    sh.phase = SH_GRAB;
    if (!timer_add(shot_grab, (void *)0, SHOT_SETTLE_MS)) {
        finish();
        pod_toast(TR("Screenshot failed"));
    }
    return RET_OK; /* this timer ends */
}

/* The first main loop turn inside the confirm dialog (started just before it opens; the dialog is modal): the stock dialog's two
 * buttons become the choice, "5 s" on the left (btn_cancel) and "10 s" on the right (btn_enter). The dialog is found by its name
 * (a stock window is not named like ours, nothing else is touched); until it is up the timer repeats, SHOT_RELABEL_TRIES times at most,
 * and then ends: a dialog that never opened leaves nothing behind. */
static int shot_relabel(const void *timer) {
    void *wm = window_manager(), *dlg = wm ? widget_lookup(wm, SHOT_DIALOG, 1) : (void *)0, *b;
    (void)timer;
    if (!dlg) return ++sh.tries < SHOT_RELABEL_TRIES ? RET_REPEAT : RET_OK;
    if ((b = widget_lookup(dlg, SHOT_BTN_SHORT, 1)) != (void *)0) widget_set_text_utf8(b, TR("5 s"));
    if ((b = widget_lookup(dlg, SHOT_BTN_LONG, 1)) != (void *)0) widget_set_text_utf8(b, TR("10 s"));
    return RET_OK;
}

/* The Screenshot row was tapped (patch/m1plus.c on_row). Idle: the stock confirm dialog asks with "5 s" and "10 s" as its buttons, either starts the countdown.
 * Counting: the dialog asks to cancel, Yes removes the tick timer. The dialog is modal and the main loop runs under it, so
 * the phase is looked at again after it returns. One capture at a time; in the settle phase the capture is committed and the
 * tap does nothing. */
void shot_start(void) {
    int secs, code;
    if (sh.phase == SH_COUNT) {
        sh.phase = SH_ASK_CANCEL;
        if (pod_confirm(TR("Cancel the screenshot?")) && sh.phase == SH_ASK_CANCEL) {
            m1_timer_stop(&sh.timer);
            finish();
        } else if (sh.phase == SH_ASK_CANCEL)
            sh.phase = SH_COUNT;
        return;
    }
    if (sh.phase != SH_IDLE) return;
    sh.phase = SH_ASK;
    if (!pod_confirm(TR("Take a screenshot?"))) { /* step 1: plain Yes / No (the back key does not close it) */
        sh.phase = SH_IDLE;
        return;
    }
    sh.tries = 0; /* step 2: the delay, the same dialog with its buttons relabelled */
    timer_add(shot_relabel, (void *)0, SHOT_RELABEL_MS); /* a refused timer only leaves the buttons Yes / No */
    code = pod_confirm_code(TR("Take a screenshot in:"));
    secs = code == SHOT_QUIT_LONG ? SHOT_SECONDS_LONG : code == SHOT_QUIT_SHORT ? SHOT_SECONDS : 0;
    if (!secs) {
        sh.phase = SH_IDLE;
        return;
    }
    sh.timer = timer_add(shot_tick, (void *)0, SHOT_TICK_MS);
    if (!sh.timer) {
        sh.phase = SH_IDLE;
        pod_toast(TR("Screenshot failed"));
        return;
    }
    sh.phase = SH_COUNT;
    sh.left = secs;
    indicator(1);
}
