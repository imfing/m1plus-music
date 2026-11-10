/* M1+ Music Equalizer page: Settings > Playback > EQ (docs/modules/peq.md).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 *
 * The page picks what hciplayer's equalizer plays (patch/peq_player.c): the 10-Band EQ (ten gains of one curve, Flat, a
 * genre of stock's table or Custom, and a preamp: the state record, patch/peq.c) or an APO / AutoEQ preset from /mnt/mmc/EQ. A tap on a preset parses the file
 * (patch/peq.c), writes the state record and, as stock's own switch handler does (on_eqswitch_onclick 0x49d750), turns
 * stock's Equalizer on if it was off and calls set_equalizer_value: its mcl-seteq makes the player add the equalizer or
 * send it the gains again, which is when the filter rereads the record, so the curve changes while the track plays (a
 * 20 ms ramp). The switch row is stock's switch. No hook: the page opens from the Settings EQ row and its handlers are
 * its own; nothing here runs at boot, in the main loop or at paint.
 */
#include "offsets.inc"
#include "stock.h"
#include "common.h"
#include "i18n.h"
#include "peq.h"
#include "autoeq.h"
#include "peqpage.h"
#include "peqlib.h"
#include "tenband.h"
#include "peqout.h"

extern void pod_toast(const char *text); /* patch/shuffle.c: the stock message box */

#define PQ_N (PQ_FIRST + PQ_ROWS) /* the 10-Band EQ link row; the Presets link row is PQ_N + 1 */
#define PQ_DNAME 11 /* struct dirent (32-bit, MIPS o32): d_name at 11 (patch/pcmodel.c PM_DNAME) */
#define PQ_PATH (sizeof(PEQ_DIR) + PEQ_NAME + 1)

static struct {
    void *win, *sv, *sw, *note, *gap, *out_t, *curve_value, *tb_row, *tb_value, *lib_row,
        *lib_value; /* gap: the space before the bottom card (hidden while the hint shows); curve_value: the picker row's grey curve name; tb: the 10-Band EQ link row and its curve name; lib: the Presets link row and its count */
    void *row[PQ_N], *check[PQ_N], *label[PQ_N], *hair[PQ_N];
    char piece[PQ_N]; /* the card piece a row shows: 1 + PQ_SINGLE.., 0 while the asset's own */
    char name[PQ_ROWS][PEQ_NAME]; /* the preset files, sorted */
    int n, total; /* the rows shown; every .txt file on the card */
    peq_state st;
} pq __attribute__((section(".scratch")));

static unsigned pq_len(const char *s) {
    unsigned n = 0;
    while (s[n]) ++n;
    return n;
}

/* A preset file: a name ending in .txt (any case), not a dot file, short enough to keep. */
static int pq_is_preset(const char *s) {
    unsigned n = pq_len(s);
    return s[0] != '.' && n > 4 && n < PEQ_NAME && !strcasecmp(s + n - 4, ".txt");
}

/* The presets of PEQ_DIR, sorted by name (insertion; at most max are kept, the first ones); *total (when not null) counts every one of
 * them. None while the card is out. */
int peq_list(char (*names)[PEQ_NAME], int max, int *total) {
    void *d;
    char *ent;
    int n = 0, all = 0;
    if (!pod_card_mounted() || !(d = opendir(PEQ_DIR))) {
        if (total) *total = 0;
        return 0;
    }
    while ((ent = readdir(d)) != (char *)0) {
        const char *s = ent + PQ_DNAME;
        int i;
        if (!pq_is_preset(s)) continue;
        ++all;
        for (i = n; i > 0 && strcasecmp(names[i - 1], s) > 0; --i)
            if (i < max) memcpy(names[i], names[i - 1], PEQ_NAME);
        if (i < max) {
            memcpy(names[i], s, pq_len(s) + 1);
            if (n < max) ++n;
        }
    }
    closedir(d);
    if (total) *total = all;
    return n;
}

static void pq_scan(void) { pq.n = peq_list(pq.name, PQ_ROWS, &pq.total); }

static void pq_show(void *w, int on) {
    widget_set_visible(w, on, 0);
    widget_set_sensitive(w, on);
}

/* The switch and the checks as the flag and the record are: 10-Band EQ, or the row of the file that plays (none when that file
 * is gone from the card: the record still plays it). */
static void pq_marks(void) {
    int i;
    if (!pq.win)
        return; /* (the AutoEq page selects a preset while this page is under it: always up, but nothing is drawn without it) */
    image_base_set_image(pq.sw, *(volatile unsigned char *)EQ_FLAG ? "sset_on" : "sset_off");
    for (i = 1; i < PQ_N; i++) {
        int on = i == 1 ? pq.st.mode == PEQ_TENBAND_MODE
                        : i - PQ_FIRST < pq.n && pq.st.mode == PEQ_FILE && !strcmp(pq.st.name, pq.name[i - PQ_FIRST]);
        widget_set_visible(pq.check[i], on, 0);
    }
    widget_invalidate_force(pq.win, (void *)0);
}

/* A row's piece of a card: 0 single, 1 top, 2 middle, 3 bottom (tools/pod_settings.py pieces), for every state a tap can show (the pressed one is the lit
 * twin). The style is the widget's own, made mutable by the stock setter. cache: the row's byte, so a piece is set once. tall: a 60 px row (the Presets
 * page's files, pod_cdl_*), else 52 px. The preset page's rows use it too. */
void peq_piece_set(void *row, char *cache, int piece, int tall) {
    static const char *const prop[5] = {"style:normal:bg_image", "style:over:bg_image", "style:pressed:bg_image",
                                        "style:focused:bg_image", "style:disable:bg_image"};
    static const char *const up[4] = {"pod_cd_single", "pod_cd_top", "pod_cd_mid", "pod_cd_bot"};
    static const char *const down[4] = {"pod_cd_single_down", "pod_cd_top_down", "pod_cd_mid_down", "pod_cd_bot_down"};
    static const char *const tall_up[4] = {"pod_cdl_single", "pod_cdl_top", "pod_cdl_mid", "pod_cdl_bot"};
    static const char *const tall_down[4] = {"pod_cdl_single_down", "pod_cdl_top_down", "pod_cdl_mid_down",
                                             "pod_cdl_bot_down"};
    int s;
    if (*cache == piece + 1) return;
    *cache = (char)(piece + 1);
    for (s = 0; s < 5; s++)
        widget_set_prop_str(row, prop[s], s == 2 ? (tall ? tall_down : down)[piece] : (tall ? tall_up : up)[piece]);
}

static void pq_piece(int i, int piece) { peq_piece_set(pq.row[i], &pq.piece[i], piece, 0); }

/* A preset's name as the page shows it: the file name without its .txt (into size bytes, cut if it must be). */
void peq_shown(char *out, unsigned size, const char *file) {
    unsigned n = pq_len(file);
    n = n > 4 ? n - 4 : n;
    if (n >= size) n = size - 1;
    memcpy(out, file, n);
    out[n] = 0;
}

/* A curve's name as a translation key (its own English): Flat, Pop, ... Jazz, Custom. */
const char *peq_curve_key(int curve) {
    static const char *const key[PEQ_CURVES] = {"Flat",  "Pop",   "Rock",      "Dance", "Blues",
                                                "Metal", "Vocal", "Classical", "Jazz",  "Custom"};
    return key[curve >= 0 && curve < PEQ_CURVES ? curve : PEQ_FLAT];
}

/* Settings > Playback > EQ's value (patch/m1plus.c value_text, set as a translation key): the preset the record plays, named as
 * the page names it, or, for the 10-Band EQ (also with no record), its curve's key (Flat, Rock, Custom, ...). Always 1. */
int peq_playing_name(char *buf, unsigned size) {
    peq_state s;
    const char *k;
    if (!size) return 0;
    if (peq_state_load(&s) && s.mode == PEQ_FILE && s.name[0]) {
        peq_shown(buf, size, s.name);
        return 1;
    }
    k = peq_curve_key(s.curve);
    if (pq_len(k) >= size) return 0;
    memcpy(buf, k, pq_len(k) + 1);
    return 1;
}

/* The picker card: 10-Band EQ and the preset rows the card has, named (the others hidden: the list's layouter skips them and
 * stacks the rest). The card's top row is a top piece, the last a bottom piece with no hairline, the rows between middle pieces;
 * 10-Band EQ alone is a single piece, with the hint (a note) under it. The column's height is the layouter's own (the asset's
 * model, tools/pod_settings.py), set now so a list that got shorter is not left scrolled past its end. */
static void pq_layout(void) {
    int i, n = pq.n, vh = n ? POD_PEQ_BASE + n * POD_ROW_H : POD_PEQ_NONE, max;
    for (i = 1; i < PQ_N; i++) {
        int p = i - 1, on = i == 1 || i - PQ_FIRST < n;
        if (i >= PQ_FIRST) {
            if (on) {
                char shown[PEQ_NAME];
                peq_shown(shown, sizeof shown, pq.name[i - PQ_FIRST]);
                widget_set_text_utf8(pq.label[i], shown);
            }
            pq_show(pq.row[i], on);
        }
        if (!on) continue;
        pq_piece(i, !n ? 0 : p == 0 ? 1 : p == n ? 3 : 2);
        if (pq.hair[i]) widget_set_visible(pq.hair[i], p < n, 0);
    }
    widget_set_prop_int(pq.sv, "virtual_h", vh);
    max = vh - widget_get_prop_int(pq.sv, "h", 0);
    if (max < 0) max = 0;
    if (widget_get_prop_int(pq.sv, "yoffset", 0) > max) widget_set_prop_int(pq.sv, "yoffset", max);
    if (pq.note) widget_set_visible(pq.note, !n, 0);
    if (pq.out_t)
        widget_set_tr_text(pq.out_t, peqout_key(peqout_current())); /* the output this page edits (patch/peqout.c) */
    if (pq.curve_value) widget_set_tr_text(pq.curve_value, peq_curve_key(pq.st.curve));
    if (pq.tb_value) widget_set_tr_text(pq.tb_value, peq_curve_key(pq.st.curve));
    if (pq.gap) widget_set_visible(pq.gap, n != 0, 0); /* the hint is the space under the picker card with no preset */
    if (pq.lib_value) {
        char count[12];
        snprintf(
            count, sizeof count, "%d",
            pq.total); /* the Presets link's grey count: every file on the card (both lists keep at most PQ_ROWS) */
        widget_set_text_utf8(pq.lib_value, count);
    }
    pq_marks();
}

/* Stock's switch handler, as it is: flip the flag, save it ([PLAYSET] EQFLAG), send the mode's gains (or close the equalizer). */
static void pq_set_flag(int on) {
    *(volatile unsigned char *)EQ_FLAG = (unsigned char)on;
    write_int_config(on, "PLAYSET", "EQFLAG");
    set_equalizer_value(*(volatile int *)EQ_MODE);
}

static int pq_on_switch(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    pq_set_flag(!*(volatile unsigned char *)EQ_FLAG);
    pq_marks();
    return RET_OK;
}

/* Save the record; then the player plays it: stock's Equalizer turned on, or its gains sent again (the filter rereads
 * the record). A failed save leaves the record on the flash as it was. */
static int pq_commit(const peq_state *s) {
    int ok = peq_state_save(s) == 0;
    if (!ok) {
        pod_toast(TR("Not saved"));
        peq_state_load(&pq.st);
    } else {
        pq.st = *s;
        if (*(volatile unsigned char *)EQ_FLAG)
            set_equalizer_value(*(volatile int *)EQ_MODE);
        else
            pq_set_flag(1);
    }
    pq_marks();
    return ok;
}

/* Like pq_commit, for a Save, a Save As or a Revert of the Preset page (patch/peqpage.c): the record is saved and, when stock's Equalizer is on, the player rereads it; the switch is never turned on by it. */
int peq_record(const peq_state *s) {
    int ok = peq_state_save(s) == 0;
    if (!ok) {
        pod_toast(TR("Not saved"));
        peq_state_load(&pq.st);
    } else {
        pq.st = *s;
        if (*(volatile unsigned char *)EQ_FLAG) set_equalizer_value(*(volatile int *)EQ_MODE);
    }
    pq_marks();
    return ok;
}

/* Rename Preset (patch/peqpage.c): the file is renamed; the record's file name follows when it is the preset that plays (nothing is sent to the player: it reads the preset, not the name). */
void peq_renamed(const char *from, const char *to) {
    peq_state s;
    if (pq_len(to) >= PEQ_NAME) return;
    if (!peqout_renamed(from, to)) pod_toast(TR("Not saved"));
    if (!peq_state_load(&s) || s.mode != PEQ_FILE || strcmp(s.name, from)) return;
    memset(s.name, 0, sizeof s.name);
    memcpy(s.name, to, pq_len(to) + 1);
    if (peq_state_save(&s) == 0)
        pq.st = s;
    else
        pod_toast(TR("Not saved"));
}

static int pq_on_tenband_pick(void *ctx, void *e) {
    peq_state s;
    (void)ctx;
    (void)e;
    peq_state_load(
        &s); /* the record of the output playing now, not the page's copy (the output may have changed under an open page) */
    s.mode = PEQ_TENBAND_MODE;
    memset(s.name, 0, sizeof s.name);
    pq_commit(&s);
    return RET_OK;
}

/* A preset of PEQ_DIR by its file name, as a tap on its row does (the AutoEq page's "Tap to use" too): parsed, the record saved, the player told. 1 when it plays now; else the message box said why and nothing changed. */
int peq_select(const char *file) {
    char path[PQ_PATH];
    peq_state s;
    peq_error err;
    if (pq_len(file) >= PEQ_NAME) return 0;
    snprintf(path, sizeof path, "%s/%s", PEQ_DIR, file);
    peq_state_load(&s); /* the 10-Band EQ's curve, gains and preamp stay as they are while a file plays */
    memset(s.name, 0, sizeof s.name);
    if (!peq_import_file(path, &s.preset, &err)) {
        pod_toast(TR("Cannot read this preset"));
        return 0;
    }
    s.mode = PEQ_FILE;
    memcpy(s.name, file, pq_len(file) + 1);
    return pq_commit(&s);
}

/* A tap on a preset's row selects the preset: the row has no chevron (the Preset page is opened from the Presets page). */
static int pq_on_preset(void *ctx, void *e) {
    int k = (int)(long)ctx - PQ_FIRST;
    (void)e;
    if (k < 0 || k >= pq.n) return RET_OK;
    peq_select(pq.name[k]);
    return RET_OK;
}

/* The editor's saves (patch/tenband.c): the same save, switch and gain command as a tap on a preset. */
int peq_commit(const peq_state *s) { return pq_commit(s); }

/* The 10-Band EQ link row opens the editor (patch/tenband.c: its page reads the record, edits curve / gains / preamp and commits with peq_commit). */
static int pq_on_tenband(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    tenband_open();
    return RET_OK;
}

/* The Presets link's row opens its page (patch/peqlib.c). */
static int pq_on_presets(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    peqlib_open();
    return RET_OK;
}

/* Delete Preset (the Preset page, after its confirm; patch/peqpage.c): the file is unlinked, then, when it is the preset that plays, the record
 * points at the 10-Band EQ and stock's Equalizer goes off (its switch path), so nothing keeps playing the deleted curve. 0 when the file cannot be
 * removed; the record is only touched after the unlink. */
int peq_delete(const char *file) {
    char path[PQ_PATH];
    peq_state s;
    if (pq_len(file) >= PEQ_NAME) return 0;
    snprintf(path, sizeof path, "%s/%s", PEQ_DIR, file);
    if (unlink(path) != 0) return 0;
    if (!peqout_deleted(file)) pod_toast(TR("Not saved")); /* the other outputs' slots must not bring the file back */
    if (peq_state_load(&s) && s.mode == PEQ_FILE && !strcmp(s.name, file)) {
        s.mode = PEQ_TENBAND_MODE;
        memset(s.name, 0, sizeof s.name);
        if (peq_state_save(&s) == 0)
            pq.st = s;
        else
            pod_toast(TR("Not saved"));
        pq_set_flag(0);
    }
    return 1;
}
/* peqout_sync switched outputs on the UI thread (the status bar's timer): the open pages show the new output's record. An edit session on a Preset page keeps its
 * preset file and its unsaved edits; they reach the new output's record only when the user saves or edits again. */
void peq_output_changed(void) {
    tenband_output_changed();
    if (!pq.win) return;
    peq_state_load(&pq.st);
    pq_layout();
}

/* Back in front (after stock's Equalizer page, or the card changed): the files and the switch again. */
static int pq_on_fg(void *ctx, void *e) {
    (void)ctx;
    (void)e;
    if (!pq.win) return RET_OK;
    peqout_sync(1);
    peq_state_load(&pq.st);
    pq_scan();
    pq_layout();
    return RET_OK;
}

/* ctx is the window: the late destroy of a page that a newer one replaced leaves the newer one's state alone. */
static int pq_on_destroy(void *ctx, void *e) {
    (void)e;
    if (ctx == pq.win) memset(&pq, 0, sizeof pq);
    return RET_OK;
}

extern int pod_open_peq(void); /* patch/m1plus.c: open_page(POD_PEQ_PAGE) */

/* The Equalizer page, for stock's All Playback Settings Equalizer row (the pod_eq_site stub): 1 once it is opening. */
int peq_open(void) { return pod_open_peq() == 0; }

/* The Equalizer page is up (patch/m1plus.c open_page): find its rows, read the record and the card, bind. A page
 * that is not our asset is left as it is. */
void peq_opened(void *win) {
    int i;
    char name[24];
    if (pq.win) { /* a page exists already (stock's All Playback Settings row opened another over it): the new one replaces it */
        void *old = pq.win;
        memset(&pq, 0, sizeof pq);
        if (widget_is_window_opened(old)) window_close(old);
    }
    memset(&pq, 0, sizeof pq);
    for (i = 0; i < PQ_N; i++) {
        snprintf(name, sizeof name, "pod_row%d", i);
        pq.row[i] = widget_lookup(win, name, 1);
        snprintf(name, sizeof name, "pod_label%d", i);
        pq.label[i] = widget_lookup(win, name, 1);
        snprintf(name, sizeof name, "pod_check%d", i);
        pq.check[i] = i ? widget_lookup(win, name, 1) : (void *)0;
        if (!pq.row[i] || !pq.label[i] || (i && !pq.check[i])) {
            memset(&pq, 0, sizeof pq);
            return;
        }
        pq.hair[i] = pq.row[i] ? widget_lookup(pq.row[i], "pod_hair", 1) : (void *)0; /* the card's last row has none */
    }
    pq.sw = widget_lookup(win, "pod_switch0", 1);
    pq.sv = widget_lookup(win, "pod_scrollview", 1);
    if (!pq.sw || !pq.sv) {
        memset(&pq, 0, sizeof pq);
        return;
    }
    pq.out_t =
        widget_lookup(win, "pod_note0_t", 1); /* the grey line under the switch card: which output's EQ this is */
    pq.note = widget_lookup(win, "pod_note1", 1); /* the hint's item (an optional piece); open_page wraps its label */
    pq.gap = widget_lookup(win, "pod_gap0", 1);
    pq.curve_value = widget_lookup(win, "pod_value1", 1);
    snprintf(name, sizeof name, "pod_row%d",
             PQ_N); /* the bottom card: the 10-Band EQ link row and its curve name (pod_value<PQ_N>) ... */
    pq.tb_row = widget_lookup(win, name, 1);
    snprintf(name, sizeof name, "pod_value%d", PQ_N);
    pq.tb_value = widget_lookup(win, name, 1);
    snprintf(name, sizeof name, "pod_row%d", PQ_N + 1); /* ... and the Presets link row and its count */
    pq.lib_row = widget_lookup(win, name, 1);
    snprintf(name, sizeof name, "pod_value%d", PQ_N + 1);
    pq.lib_value = widget_lookup(win, name, 1);
    pq.win = win;
    peqout_sync(1); /* the record is the current output's before it is read */
    peq_state_load(&pq.st);
    pq_scan();
    pq_layout();
    widget_on(pq.row[0], EVT_CLICK, pq_on_switch, (void *)0);
    widget_on(pq.row[1], EVT_CLICK, pq_on_tenband_pick, (void *)0);
    for (i = PQ_FIRST; i < PQ_N; i++) widget_on(pq.row[i], EVT_CLICK, pq_on_preset, (void *)(long)i);
    if (pq.tb_row) widget_on(pq.tb_row, EVT_CLICK, pq_on_tenband, (void *)0);
    if (pq.lib_row) widget_on(pq.lib_row, EVT_CLICK, pq_on_presets, (void *)0);
    widget_on(win, EVT_WINDOW_TO_FG, pq_on_fg, (void *)0);
    widget_on(win, EVT_DESTROY, pq_on_destroy, win);
}
