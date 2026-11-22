/* M1+ Music Mono Audio and Crossfeed, demo's side (docs/modules/stereo.md): the user's two settings and the record the player reads.
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * The settings are two small files (STEREO_MONO_FILE, STEREO_XFEED_FILE); the player never reads them. It reads STEREO_FILE, which holds the state in effect for the output playing now: Mono Audio on every output,
 * the crossfeed level on the headphone jacks and Bluetooth, off on Line Out and a USB DAC. stereo_sync (called by peqout_sync, so it runs where the output can change and nowhere else) writes that record whole
 * (tmp, fsync, rename) only when it differs from what is on disk, then makes the player reread it (set_equalizer_value: stock's mcl-seteq, answered by hciplayer with a gain command on channel 0). With every
 * option off and no record on disk nothing is written. Under the kill switch it does nothing. Not on the boot path.
 */
#include "offsets.inc"
#include "stock.h"
#include "home.h"
#include "common.h"
#include "peqout.h"
#include "stereo.h"

static struct {
    unsigned char loaded, mono, level;
    unsigned char known,
        dirty; /* known: out is what the record on disk was made for; dirty: a setting changed or the last write failed */
    int out, busy;
} ss __attribute__((section(".scratch")));

static void ss_load(void) {
    int c;
    if (ss.loaded) return;
    ss.mono = set_read(STEREO_MONO_FILE, '0') == '1';
    c = set_read(STEREO_XFEED_FILE, '0');
    ss.level = c >= '1' && c <= '0' + STEREO_HIGH ? (unsigned char)(c - '0') : STEREO_OFF;
    ss.loaded = 1;
}

int stereo_mono(void) {
    ss_load();
    return ss.mono;
}

int stereo_crossfeed(void) {
    ss_load();
    return ss.level;
}

/* The record on disk as the player reads it: the same rules as stereo_load (16 bytes exactly, the magic, both fields in range); anything else is both off. */
static void ss_disk(stereo_record *r) {
    void *f = fopen(STEREO_FILE, "rb");
    char extra;
    int ok, i;
    memset(r, 0, sizeof *r);
    if (!f) return;
    ok = fread(r, 1, sizeof *r, f) == sizeof *r && fread(&extra, 1, 1, f) == 0;
    if (fclose(f)) ok = 0;
    for (i = 0; i < 8; i++) ok = ok && r->magic[i] == STEREO_MAGIC[i];
    ok = ok && (r->mono == 0 || r->mono == 1) && r->crossfeed >= STEREO_OFF && r->crossfeed < STEREO_LEVELS;
    if (!ok) memset(r, 0, sizeof *r);
}

/* A fixed temp name, not m1_save: peqout_sync runs this on the status bar timer (patch/lineout.c's instruction budget). */
static int ss_write(const stereo_record *r) {
    int ok = m1_save_as(STEREO_FILE, STEREO_FILE ".tmp", 0644, r, sizeof *r);
    if (!ok && mkdir(PEQ_STATE_DIR, 0755) == 0) ok = m1_save_as(STEREO_FILE, STEREO_FILE ".tmp", 0644, r, sizeof *r);
    return ok;
}

int stereo_sync(int output, int notify) {
    stereo_record want, have;
    int wrote = 0, i;
    if (ss.known && ss.out == output && !ss.dirty) return 0;
    if (access(PEQ_KILL, F_OK) == 0) return 0;
    if (__sync_lock_test_and_set(&ss.busy, 1)) return 0; /* the other thread is on it: the next call looks again */
    ss.dirty = 0; /* before the settings are read: a change meanwhile sets it again */
    ss_load();
    memset(&want, 0, sizeof want);
    for (i = 0; i < 8; i++) want.magic[i] = STEREO_MAGIC[i];
    want.mono = ss.mono;
    want.crossfeed = output == PO_HEADPHONES ? ss.level : STEREO_OFF;
    ss_disk(&have);
    if (have.mono != want.mono || have.crossfeed != want.crossfeed) {
        if (!ss_write(&want)) {
            ss.dirty = 1; /* asked again at the next call */
            goto done;
        }
        wrote = 1;
        if (notify) set_equalizer_value(*(volatile int *)EQ_MODE); /* after the record is in place */
    }
    ss.out = output;
    ss.known = 1;
done:
    __sync_lock_release(&ss.busy);
    return wrote;
}

/* A setting changed: the record for the output now, at once, with the player told (the UI thread). */
static void ss_apply(void) {
    ss.dirty = 1;
    stereo_sync(peqout_current(), 1);
}

int stereo_mono_toggle(void) {
    int next = !stereo_mono();
    if (home_write_atomic(STEREO_MONO_FILE, next ? "1\n" : "0\n") != 0) return -1;
    ss.mono = (unsigned char)next;
    ss_apply();
    return next;
}

int stereo_crossfeed_set(int level) {
    char text[3] = {'0', '\n', 0};
    if (level < STEREO_OFF || level >= STEREO_LEVELS) return -1;
    if (level == stereo_crossfeed()) return level;
    text[0] = (char)('0' + level);
    if (home_write_atomic(STEREO_XFEED_FILE, text) != 0) return -1;
    ss.level = (unsigned char)level;
    ss_apply();
    return level;
}
