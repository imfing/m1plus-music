/* M1+ Music Settings > Library > Update Library (docs/modules/libupdate.md): the state and actions behind our page.
 *
 * Auto Update is stock's own switch, the byte autoscan_flag ([SYSSET] AUTOSCAN): stock's toggle (0x4af0bc) stores the xor of the byte and writes the ini with write_int_config, nothing else
 * (tools/pod_pins.py LIBUPDATE_PINS). Update Now is stock's row handler (0x4af070): navigator_to_with_context("dialog/scanmusic_dialog", four zero words), a full scan. Choose Folders is stock's handler
 * (0x4af1f4): toolsCheckMount("/mnt/mmc"), then navigator_to("systemset/specfolder_page"); with no card its message box (msg_nottf). lu_folders keeps the check and opens our folder picker (patch/lupick.c); stock's page is the fallback.
 *
 * Last Updated is ours: one decimal Unix time on the card (/mnt/mmc/.m1plus/library-updated), written by lu_scan_finish, the hook at the scan dialog's finish branch (tools/pod.py LIBUPDATE_SITE, payload
 * hook 34). Stock's timer callback 0x47bab0 calls its refresh 0x47b604 (the "finished" texts) at the first tick that sees the worker's state word (0xa03a40) above 0; the state is 1 at that tick and
 * 2 at the next, and the dialog quits at 3. The worker sets 1 when scanAllMusicFile / scanSpecFolder returns, cancelled or not, so a scan counts as completed only when toolsGetUserStop() (the
 * flag Cancel sets, cleared by the dialog's init) is 0 and the scan reached its toolsDatabaseCommit (lu_commit: both scan functions call it at the end of a scan, from `jalr t9` at 0x4e9e70 and 0x4e9f9c, which
 * become jal lu_commit; a failed toolsInitDatabase skips it). Songs is toolsGetDbTableNumber("songtable"), stock's own count query. */
#include "offsets.inc"
#include "stock.h"
#include "i18n.h"
#include "home.h"
#include "common.h"
#include "entries.h"

#define autoscan_flag (*(volatile unsigned char *)AUTOSCAN_FLAG)
#define scan_state (*(volatile int *)SCAN_STATE)
#define db_tx (*(volatile int *)DB_TX)
#define db_handle (*(void *volatile *)DB_HANDLE)
/* Set by lu_commit when a scan reached its toolsDatabaseCommit; cleared when a scan finishes. */
static int lu_committed __attribute__((section(".scratch")));
/* Set by lu_batch_exec when stock's batch COMMIT (every 100 inserted rows) failed; cleared when a scan finishes. */
static int lu_failed __attribute__((section(".scratch")));
/* The scan dialog's refresh of its texts (0x47b604; a1 = 1 shows the finish): demo has no export for it, so the address is pinned by tools/pod_pins.py LIBUPDATE_PINS (its prologue). */
#define scan_refresh ((int (*)(void *, int))0x47b604u)

#define LU_DIR "/mnt/mmc/.m1plus"
#define LU_FILE LU_DIR "/library-updated"

int lu_auto(void) { return autoscan_flag != 0; }

/* Stock's toggle: the byte becomes its xor, then the ini. The new state. */
int lu_auto_toggle(void) {
    unsigned char v = (unsigned char)(autoscan_flag ^ 1);
    autoscan_flag = v;
    write_int_config(v, "SYSSET", "AUTOSCAN");
    return v != 0;
}

/* Update Now: stock's handler, the dialog with a context of four zero words (a full scan). */
void lu_update_now(void) {
    int ctx[4] = {0, 0, 0, 0};
    navigator_to_with_context("dialog/scanmusic_dialog", ctx);
}

/* Choose Folders, as stock's row handler (0x4af1f4): the card must be mounted, else stock's message box. With the card, our picker (patch/lupick.c); stock's page only where that will not open. */
void lu_folders(void) {
    if (toolsCheckMount("/mnt/mmc")) {
        if (lupick_open() == -1) navigator_to("systemset/specfolder_page");
    } else {
        char msg[256];
        memset(msg, 0, sizeof msg);
        getFormatString("msg_nottf", msg, sizeof msg - 1);
        pod_toast_ms(msg, 2000);
    }
}

/* The Songs row: the songtable's rows with a thousands comma, "-" when the query fails. */
void lu_songs_text(char *buf, unsigned n) {
    int c = toolsGetDbTableNumber("songtable", STOCK_DB_PATH);
    if (c < 0) {
        buf[0] = 0;
        return;
    }
    if (c >= 1000000)
        snprintf(buf, n, "%d,%03d,%03d", c / 1000000, c / 1000 % 1000, c % 1000);
    else if (c >= 1000)
        snprintf(buf, n, "%d,%03d", c / 1000, c % 1000);
    else
        snprintf(buf, n, "%d", c);
}

/* The recorded time: 0 when the file is missing or is not one decimal number after the clock's first possible day. */
static long lu_read(void) {
    unsigned n, i;
    long t = 0;
    char *p = m1_read_file(LU_FILE, 16, &n);
    if (!p) return 0;
    for (i = 0; i < n && p[i] >= '0' && p[i] <= '9'; i++) t = t * 10 + (p[i] - '0');
    if (i == 0 || (i < n && p[i] != '\n') || t < (long)M1_MIN_EPOCH) t = 0;
    free(p);
    return t;
}

/* "Today 9:41 AM", "Yesterday 21:05", "Nov 14 09:41", "2025-12-31" (another year): the recorded time in local time, the clock as 24-Hour Time says (the Date & Time page's Time row). "" when nothing
 * is recorded or the clock is not set. */
void lu_when_text(char *buf, unsigned n) {
    static const char *const mon[12] = {"Jan %d", "Feb %d", "Mar %d", "Apr %d", "May %d", "Jun %d",
                                        "Jul %d", "Aug %d", "Sep %d", "Oct %d", "Nov %d", "Dec %d"};
    char day[40], clock[16];
    int lt[9], nw[9], yd[9];
    long t = lu_read(), now = time((long *)0), back = now - 86400;
    const int *q;
    int k, h;
    buf[0] = 0;
    if (!t || now < (long)M1_MIN_EPOCH) return;
    if (!(q = localtime(&t))) return;
    for (k = 0; k < 9; k++) lt[k] = q[k]; /* (localtime's one buffer) */
    if (!(q = localtime(&now))) return;
    for (k = 0; k < 9; k++) nw[k] = q[k];
    if (!(q = localtime(&back))) return;
    for (k = 0; k < 9; k++) yd[k] = q[k];
    h = lt[2];
    if (dt_24h())
        snprintf(clock, sizeof clock, "%02d:%02d", h, lt[1]);
    else
        snprintf(clock, sizeof clock, "%d:%02d %s", h % 12 ? h % 12 : 12, lt[1], h < 12 ? "AM" : "PM");
    if (lt[5] != nw[5]) {
        snprintf(buf, n, "%04d-%02d-%02d", lt[5] + 1900, lt[4] + 1, lt[3]);
        return;
    }
    if (lt[4] == nw[4] && lt[3] == nw[3])
        snprintf(day, sizeof day, "%s", TR("Today"));
    else if (lt[5] == yd[5] && lt[4] == yd[4] && lt[3] == yd[3])
        snprintf(day, sizeof day, "%s", TR("Yesterday"));
    else
        snprintf(day, sizeof day, TR(mon[lt[4] < 0 || lt[4] > 11 ? 0 : lt[4]]), lt[3]);
    snprintf(buf, n, "%s %s", day, clock);
}

/* The record: now, one line. No clock, no card (m1_card_write refuses) or a failed write leave the old record. */
static void lu_record(void) {
    char buf[16];
    long t = time((long *)0);
    unsigned o = 0, i;
    char dig[12];
    if (t < (long)M1_MIN_EPOCH) return;
    for (i = 0; t; t /= 10) dig[i++] = (char)('0' + t % 10);
    while (i) buf[o++] = dig[--i];
    buf[o++] = '\n';
    m1_card_write(LU_DIR, LU_FILE, buf, o, (const void *)0, 0);
}

/* The two stock call sites of toolsDatabaseCommit (scanAllMusicFile 0x4e9e70, scanSpecFolder 0x4e9f9c). Stock's own commit drops sqlite3_exec("COMMIT;")'s result, so the COMMIT is run here, as stock
 * does it (when the rows-since-the-last-COMMIT word is above 0, then the word is 0) with its result kept; stock's commit then only closes the handle. The scan counts as committed when the COMMIT
 * returned SQLITE_OK. A word at 0 means no transaction is open (the insert path commits itself every 100 rows), so there is nothing to commit. */
void lu_commit(void) {
    int rc = 0;
    if (db_tx > 0) {
        rc = sqlite3_exec(db_handle, "COMMIT;", (void *)0, (void *)0, (char **)0);
        db_tx = 0;
    }
    lu_committed = rc == 0;
    toolsDatabaseCommit();
}

/* The batch COMMIT of stock's insert path (toolsInsertDbTable 0x5ee090: every 100 rows it runs sqlite3_exec(db, "COMMIT;", 0, 0, errmsg), drops the result and resets the transaction word): its `jalr t9`
 * becomes jal lu_batch_exec, which runs the same call and keeps a failure for lu_scan_finish. The caller's registers a0-a3 and its stack word 0x10($sp) (the fifth argument) are as stock set them, so
 * this five-parameter function reads them as the call would. Stock's insert-error path runs "ROLLBACK;" through the same call, which counts as a failure whatever it returns. The flag is only read by a finish; a batch commit outside a scan needs 100 uncommitted inserts, which only the scan makes. */
int lu_batch_exec(void *db, const char *sql, void *cb, void *arg, char **err) {
    int rc = sqlite3_exec(db, sql, cb, arg, err);
    if (rc != 0 || strcmp(sql, "COMMIT;") != 0)
        lu_failed = 1; /* the insert-error path runs ROLLBACK here: rows were lost even when it succeeds */
    return rc;
}

/* The call site 0x47baec of stock's timer callback: its `bal 0x47b604` (refresh the dialog's texts, done = 1) becomes jal lu_scan_finish. Stock's refresh runs first; at the first finished tick, when
 * the scan was not cancelled, the time is recorded. */
int lu_scan_finish(void *win, int done) {
    int r = scan_refresh(win, done);
    if (done && scan_state == 1) {
        lp_scan_done(); /* the folder picker's deque: the worker has returned */
        if (!toolsGetUserStop() && lu_committed && !lu_failed) lu_record();
        lu_committed = 0;
        lu_failed = 0;
    }
    return r;
}
