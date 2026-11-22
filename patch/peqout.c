/* M1+ Music per-output EQ: Headphones, Line Out and USB DAC each keep their own EQ (docs/modules/peq.md "Per-output EQ").
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * The player still reads one record, PEQ_STATE (patch/peq_player.c), and the Equalizer pages still edit it. Each output has a slot beside it (playback-eq-headphones,
 * playback-eq-lineout, playback-eq-usb: the same record) and playback-eq-output names the output the record belongs to, with each output's setting of stock's
 * Equalizer switch. peqout_sync runs where the output can change: the status bar's one second timer (patch/lineout.c; the Line Out switch, a USB DAC, any page), stock's
 * save_start_player (a jack or a DAC changed under a playing track) and mclStartPlayer (a track starts on whatever is plugged in, screen off too), both hooks of
 * patch/radio.c. A changed output files the record under the old output, loads the new output's slot over PEQ_STATE (an output with no slot keeps what plays) and sets the
 * switch as that output had it; with notify (the UI thread's timer) the player is also told to reread. The first run only notes the output: the old single record plays on
 * every output until each is edited. Bluetooth is not an output of its own: it keeps the headphone EQ. Not on the boot path; the kill switch makes it do nothing. It also runs stereo_sync (patch/stereoset.c: the Mono Audio / Crossfeed record for the output).
 */
#include "offsets.inc"
#include "stock.h"
#include "peq.h"
#include "peqout.h"
#include "common.h"
#include "peqpage.h"
#include "stereo.h"

static const char *const po_file[PO_N] = {PEQ_STATE_DIR "/playback-eq-headphones", PEQ_STATE_DIR "/playback-eq-lineout",
                                          PEQ_STATE_DIR "/playback-eq-usb"};
static const char *const po_text[PO_N] = {"For Headphones", "For Line Out", "For USB DAC"};

typedef struct {
    char magic[8];
    int owner, on[PO_N];
} po_rec;

static struct {
    int known, cur, busy,
        pending; /* pending: a switch without notify (the player thread) the open pages have not been shown yet */
} po __attribute__((section(".scratch")));

/* The output playing now: USB audio (the output way 2); else Line Out while stock's Line Out byte is set on the jacks; else the headphone jacks (and Bluetooth, way 1). */
int peqout_current(void) {
    int way = mclGetOutputWay();
    if (way == 2) return PO_USB;
    if (way == 0 && *(volatile unsigned char *)LINEOUT_FLAG) return PO_LINEOUT;
    return PO_HEADPHONES;
}

const char *peqout_key(int output) { return po_text[output >= 0 && output < PO_N ? output : PO_HEADPHONES]; }

static int po_read(po_rec *r) {
    void *f = fopen(PO_OUTPUT_FILE, "rb");
    int ok, i;
    char extra;
    if (!f) return 0;
    memset(r, 0, sizeof *r);
    ok = fread(r, 1, sizeof *r, f) == sizeof *r && fread(&extra, 1, 1, f) == 0;
    if (fclose(f)) ok = 0;
    for (i = 0; i < 8; i++) ok = ok && r->magic[i] == PO_MAGIC[i];
    ok = ok && r->owner >= 0 && r->owner < PO_N;
    for (i = 0; i < PO_N; i++) ok = ok && (r->on[i] == 0 || r->on[i] == 1);
    return ok;
}

/* A fixed temp name, not m1_save: this runs on the status bar timer, within patch/lineout.c's instruction budget. */
static int po_write(const po_rec *r) {
    int ok = m1_save_as(PO_OUTPUT_FILE, PO_OUTPUT_FILE ".tmp", 0644, r, sizeof *r);
    if (!ok && mkdir(PEQ_STATE_DIR, 0755) == 0)
        ok = m1_save_as(PO_OUTPUT_FILE, PO_OUTPUT_FILE ".tmp", 0644, r, sizeof *r);
    return ok ? 0 : -1;
}

int peqout_sync(int notify) {
    po_rec r;
    peq_state s, old;
    int cur, flag, i, had, have_old, switched = 0;
    if (access(PEQ_KILL, F_OK) == 0) return 0;
    cur = peqout_current();
    stereo_sync(
        cur,
        notify); /* Mono Audio and Crossfeed: the record for this output (patch/stereoset.c; the same early exit while nothing changed) */
    if (po.known && cur == po.cur) {
        if (notify &&
            po.pending) { /* the player thread switched outputs: the UI thread's next call shows it on the open pages */
            po.pending = 0;
            peq_output_changed();
        }
        return 0;
    }
    if (__sync_lock_test_and_set(&po.busy, 1)) return 0;
    flag = *(volatile unsigned char *)EQ_FLAG != 0;
    if (!po_read(
            &r)) { /* the first run (or a record that cannot be read): the playing record belongs to this output, every output starts as it is */
        memset(&r, 0, sizeof r);
        memcpy(r.magic, PO_MAGIC, 8);
        r.owner = cur;
        for (i = 0; i < PO_N; i++) r.on[i] = flag;
        if (po_write(&r) != 0) goto done; /* nothing is recorded: ask again at the next call */
    }
    if (r.owner != cur) {
        r.on[r.owner] = flag;
        have_old = peq_state_load(&old);
        if (have_old && peq_state_save_to(po_file[r.owner], &old) != 0)
            goto done; /* the old output's EQ could not be filed: keep it playing */
        had = peq_state_load_from(po_file[cur], &s);
        if (had && peq_state_save(&s) != 0) goto done;
        if (had) flag = r.on[cur]; /* an output with no slot keeps the switch as it is, too */
        r.owner = cur;
        r.on[cur] = flag;
        if (po_write(&r) != 0) {
            /* The owner could not be recorded, so the playing record must stay the old owner's (its slot holds the same copy): put it back, or remove it when
             * even that fails (a missing record is never filed over a slot); tried again at the next call. */
            if (had && (!have_old || peq_state_save(&old) != 0)) unlink(PEQ_STATE);
            goto done;
        }
        switched = 1;
        if (flag != (*(volatile unsigned char *)EQ_FLAG != 0)) {
            *(volatile unsigned char *)EQ_FLAG = (unsigned char)flag;
            write_int_config(flag, "PLAYSET", "EQFLAG");
            set_equalizer_value(*(volatile int *)EQ_MODE);
        } else if (notify && flag)
            set_equalizer_value(*(volatile int *)EQ_MODE);
    }
    po.cur = cur;
    po.known = 1;
done:
    __sync_lock_release(&po.busy);
    if (switched && notify) {
        po.pending = 0;
        peq_output_changed(); /* the UI thread: the open EQ pages show the new output */
    } else if (switched)
        po.pending = 1;
    return switched;
}

/* Rename Preset (patch/peq_ui.c): every output's slot that names the preset `from` follows it to `to`, so no output switches back to a file that is gone. 0 when a slot could not be rewritten. */
int peqout_renamed(const char *from, const char *to) {
    peq_state s;
    int i, ok = 1, n = 0;
    while (to[n]) n++;
    if (n >= PEQ_NAME) return 0;
    for (i = 0; i < PO_N; i++) {
        if (!peq_state_load_from(po_file[i], &s) || s.mode != PEQ_FILE || strcmp(s.name, from)) continue;
        memset(s.name, 0, sizeof s.name);
        memcpy(s.name, to, n + 1);
        if (peq_state_save_to(po_file[i], &s) != 0) ok = 0;
    }
    return ok;
}

/* Delete Preset (patch/peq_ui.c): every output's slot that names the deleted file points at the 10-Band EQ again and that output's Equalizer switch goes off (what the playing record
 * does), so no output brings the file back. 0 when a slot or the output file could not be rewritten. */
int peqout_deleted(const char *file) {
    peq_state s;
    po_rec r;
    int i, ok = 1, have = po_read(&r), dirty = 0;
    for (i = 0; i < PO_N; i++) {
        if (!peq_state_load_from(po_file[i], &s) || s.mode != PEQ_FILE || strcmp(s.name, file)) continue;
        s.mode = PEQ_TENBAND_MODE;
        memset(s.name, 0, sizeof s.name);
        if (peq_state_save_to(po_file[i], &s) != 0)
            ok = 0;
        else if (have && r.on[i])
            r.on[i] = 0, dirty = 1;
    }
    if (dirty && po_write(&r) != 0) ok = 0;
    return ok;
}

/* An edit session on the Preset page (patch/peqpage.c) belongs to the output whose record received its live edits: the token is that output + 1. */
int peqout_session(void) { return peqout_current() + 1; }

int peqout_away(int session) {
    if (!session) return 0;
    peqout_sync(1);
    return session - 1 != peqout_current();
}

/* The Preset page puts a preset file's preset into the session output's slot while another output plays: only when the slot is in file mode and names `from`; its file name becomes `to`
 * (a Save As) and its preset `p`. 0 when the slot could not be rewritten; 1 otherwise, also when there was nothing to do. */
int peqout_session_filed(int session, const char *from, const char *to, const peq_preset *p) {
    peq_state s;
    int output = session - 1, n = 0;
    if (output < 0 || output >= PO_N || !peq_state_load_from(po_file[output], &s) || s.mode != PEQ_FILE ||
        strcmp(s.name, from))
        return 1;
    while (to[n]) n++;
    if (n >= PEQ_NAME) return 0;
    s.preset = *p;
    memset(s.name, 0, sizeof s.name);
    memcpy(s.name, to, n + 1);
    return peq_state_save_to(po_file[output], &s) == 0;
}

int peqout_playing_filed(const char *file, const peq_preset *p) {
    peq_state s;
    if (!peq_state_load(&s) || s.mode != PEQ_FILE || strcmp(s.name, file)) return 1;
    s.preset = *p;
    return peq_record(&s);
}
