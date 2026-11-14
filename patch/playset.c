/* M1+ Music Settings > Playback Settings (docs/modules/playset.md): the state behind our page's rows and their seven pickers.
 *
 * Every state is stock's own, loaded by config_init (anything out of range becomes its default) and shown by stock's pages, which stay reachable where stock still opens them (the pull-down's Playback tile, the
 * Control Center) and read the same words and bytes. Nothing of ours is saved. The setters repeat what stock's click handlers do, in their order (tools/pod_pins.py PLAYSET_PINS), and nothing else: stock's
 * handlers need their own widgets for the refresh, so they are not called. The mcl getters are stock's own functions; a state without a getter is the word itself (tools/pod.py DATA). Play Mode is the one
 * exception to "stock's setter": pod_set_mode (patch/shuffle.c) is stock's sequence with the meaning of a Shuffle request. The three loudness pages (end of file) bind stock's own handlers instead. */
#include "offsets.inc"
#include "stock.h"
#include "entries.h"
#include "home.h"

#define memory_play (*(volatile int *)MEMORY_PLAY)
#define digital_flag (*(volatile unsigned char *)DIGITAL_FLAG)
#define usbvol_mode (*(volatile int *)USBVOL_MODE)
#define lineout (*(volatile unsigned char *)LINEOUT_FLAG)
#define folder_cover (*(volatile unsigned char *)FOLDER_COVER)
#define volume_word (*(volatile int *)G_VOLUME)

#define PS_MODE_MAX 3
#define PS_MEM_MAX 2
#define PS_RG_MAX 2
#define PS_FILTER_MAX 7
#define PS_DSD_MAX 2
#define PS_OUTPUT_USB 2 /* mclGetOutputWay: 0 built-in, 1 Bluetooth, 2 USB audio */

/* Play Mode: the mode as stock's page and Now Playing show it, 0 List Play, 1 Repeat Track, 2 Shuffle (our request; stock's own mode 2 never runs), 3 Repeat All. */
int ps_playmode(void) {
    int m = pod_play_mode();
    return m >= 0 && m <= PS_MODE_MAX ? m : 0;
}

/* Stock's page calls its set function when the mode differs and the function does mclSetPlayMode, notifyPlayMode, dmrSendPlayMode and the save of PLAYMODE; pod_set_mode is that and does nothing when the mode is
 * shown already. 0, or -1 for a mode stock does not have. */
int ps_playmode_set(int v) {
    if (v < 0 || v > PS_MODE_MAX) return -1;
    pod_set_mode(v);
    return 0;
}

/* Gapless: stock's switch (0x4a015c): the byte xor 1, its save, then mclSetGaplessMode (which closes an open preload for 0). The new state. */
int ps_gapless(void) { return (mclGetGaplessMode() & 0xff) != 0; }

int ps_gapless_toggle(void) {
    int next = (mclGetGaplessMode() ^ 1) & 0xff;
    write_int_config(next, "PLAYSET", "GAPLESS");
    mclSetGaplessMode(next);
    return next != 0;
}

/* Memory Playback: stock's word memory_play, 0 off, 1 track, 2 location. Stock's choice (0x49f608), when the word differs: the word stored, then the save; nothing else (the resume at boot reads it). */
int ps_memplay(void) {
    int v = memory_play;
    return v >= 0 && v <= PS_MEM_MAX ? v : 0;
}

int ps_memplay_set(int v) {
    if (v < 0 || v > PS_MEM_MAX) return -1;
    if (memory_play == v) return 0;
    memory_play = v;
    write_int_config(v, "PLAYSET", "MEMORYPLAY");
    return 0;
}

/* Folder Skip: stock's switch (0x4a0504): the state xor 1, its save, then mclSetJumpFolder. The new state. */
int ps_folderskip(void) { return (mclGetJumpFolder() & 0xff) != 0; }

int ps_folderskip_toggle(void) {
    int next = (mclGetJumpFolder() ^ 1) & 0xff;
    write_int_config(next, "PLAYSET", "JUMPFOLDER");
    mclSetJumpFolder(next);
    return next != 0;
}

/* Gain: stock's mode, 0 low, 1 high. While the Line Out byte is set stock greys the row and its click does nothing at all (0x4a0224), so the choice is refused here and the page dims the row. */
int ps_gain_locked(void) { return lineout != 0; }

int ps_gain(void) { return mclGetGainMode() == 1; }

/* Stock's click (0x4a021c) toggles: the save of GAIN with the new mode, then mclSetGainMode(new, 1), which stores the word and reaches the driver (a store of 0 would leave the word unchanged). The picker's
 * choice is that click when it differs from the shown mode. 0, or -1 for a mode stock does not have or while Line Out is on. */
int ps_gain_set(int v) {
    if (v < 0 || v > 1 || ps_gain_locked()) return -1;
    if (ps_gain() == v) return 0;
    write_int_config(v, "PLAYSET", "GAIN");
    mclSetGainMode(v, 1);
    return 0;
}

/* ReplayGain: stock's word, 0 off, 1 track, 2 album. Stock's choice (0x4a0f48), when it differs: mclSetReplayGain (the word, then the hciplayer is told), then the save. */
int ps_replaygain(void) {
    int v = mclGetReplayGain();
    return v >= 0 && v <= PS_RG_MAX ? v : 0;
}

int ps_replaygain_set(int v) {
    if (v < 0 || v > PS_RG_MAX) return -1;
    if (mclGetReplayGain() == v) return 0;
    mclSetReplayGain(v);
    write_int_config(v, "PLAYSET", "REPLAYGAIN");
    return 0;
}

/* Digital Filter: stock's word, 0 .. 7. Stock's choice (0x49e95c), when it differs: mclSetFilter (the driver), then the save. */
int ps_filter(void) {
    int v = mclGetfilter();
    return v >= 0 && v <= PS_FILTER_MAX ? v : 0;
}

int ps_filter_set(int v) {
    if (v < 0 || v > PS_FILTER_MAX) return -1;
    if (mclGetfilter() == v) return 0;
    mclSetFilter(v);
    write_int_config(v, "PLAYSET", "FILTER");
    return 0;
}

/* DSD Output Mode: stock's word, 0 D2P, 1 DOP, 2 Native. Stock's choice (0x4a61f8), when it differs: the save of DSDMODE; on USB audio the player is stopped (save_stop_player), then mclSetDsdMode (the word, and
 * the hciplayer is told); on USB audio again it is started again at its place (save_start_player(0)). The output is asked twice, as stock does. */
int ps_dsd(void) {
    int v = mclGetDsdMode();
    return v >= 0 && v <= PS_DSD_MAX ? v : 0;
}

int ps_dsd_set(int v) {
    if (v < 0 || v > PS_DSD_MAX) return -1;
    if (mclGetDsdMode() == v) return 0;
    write_int_config(v, "SYSSET", "DSDMODE");
    if (mclGetOutputWay() == PS_OUTPUT_USB) save_stop_player();
    mclSetDsdMode(v);
    if (mclGetOutputWay() == PS_OUTPUT_USB) save_start_player(0);
    return 0;
}

/* USB Volume (stock's USB Audio Output): stock's word, 0 fixed, 1 variable. Stock's choice (0x4af9a4), when it differs: the word stored, set_devicevolume with the volume (it sends 100 or the volume to a USB DAC
 * and does nothing to another output), then the save. */
int ps_usbvol(void) { return usbvol_mode == 0 ? 0 : 1; }

int ps_usbvol_set(int v) {
    if (v < 0 || v > 1) return -1;
    if (usbvol_mode == v) return 0;
    usbvol_mode = v;
    set_devicevolume(volume_word);
    write_int_config(v, "SYSSET", "USBVOLMODE");
    return 0;
}

/* Digital Output: stock's byte (0x4a0418): the byte xor 1 stored as the save's callee starts, then mclSetLineOut with the byte. The new state. */
int ps_digital(void) { return digital_flag != 0; }

int ps_digital_toggle(void) {
    unsigned char next = digital_flag ^ 1;
    digital_flag = next;
    write_int_config(next, "PLAYSET", "DIGITALMODE");
    mclSetLineOut(digital_flag);
    return digital_flag != 0;
}

/* Folder Album Cover (Settings > Library): stock's byte (0x4a04a8): the byte xor 1 stored as the save's callee starts, nothing else (the Folders page reads it when it is back in front). The new state. */
int ps_foldercover(void) { return folder_cover != 0; }

int ps_foldercover_toggle(void) {
    unsigned char next = folder_cover ^ 1;
    folder_cover = next;
    write_int_config(next, "PLAYSET", "FOLDERCOVER");
    return folder_cover != 0;
}

/* The key of the value row's text of control ctl (tools/pod_pages.py PLAYMODE_VALUES .. USBVOL_VALUES; the value row's kind is VK_PS + ctl in patch/m1plus.c). */
const char *ps_value_key(int ctl) {
    static const char *const mode[] = {"List Play", "Repeat Track", "Shuffle", "Repeat All"};
    static const char *const mem[] = {"Off", "Track", "Location"};
    static const char *const gain[] = {"Low", "High"};
    static const char *const rg[] = {"Off", "Track", "Album"};
    static const char *const dsd[] = {"D2P", "DOP", "Native"};
    static const char *const usb[] = {"Fixed", "Variable"};
    switch (ctl) {
    case PS_CTL_MODE:
        return mode[ps_playmode()];
    case PS_CTL_MEM:
        return mem[ps_memplay()];
    case PS_CTL_GAIN:
        return gain[ps_gain()];
    case PS_CTL_RG:
        return rg[ps_replaygain()];
    case PS_CTL_DSD:
        return dsd[ps_dsd()];
    case PS_CTL_USB:
        return usb[ps_usbvol()];
    case PS_CTL_BOOTVOL:
        return "Memory"; /* (ps_value_text says 0 only while Volume Memory is on) */
    }
    return "";
}

/* The three loudness pages (docs/modules/playset.md "Loudness pages"): Max Volume, Default Volume and Channel Balance. The pages hold stock's own widgets by stock's names (label_vol / label_balance, btn_dec, btn_add,
 * vol_slider / slider_balance), and stock's own handlers of maxvol_page, bootvol_page and balance_page are bound to them with the window as their context, as stock's page init binds them (PLAYSET_PINS), the way the
 * Display page binds stock's brightness handlers (patch/display.c): the slider's EVT_VALUE_CHANGING handler (stock binds no other event to it, so a drag saves as often as stock's does) and the two buttons' EVT_CLICK.
 * The stores, the clamp of volume to the Max Volume, set_devicevolume (only while headset_output is not 2), the saves and reset_poweroptions_timer are stock's code, in stock's order: nothing of them is repeated here.
 * The refresh is stock's too (it writes the label and sets the slider from the word) and runs when the page opens and each time it is back in front. Volume Memory is the one control without a stock handler we can run
 * (stock's needs its switch image and its hidden view): ps_bootmem_toggle repeats its stores and its save. */
#define boot_volflag (*(volatile unsigned char *)BOOT_VOLFLAG)
#define max_volume (*(volatile int *)MAX_VOLUME)
#define boot_volume (*(volatile int *)BOOT_VOLUME)
#define balance_word (*(volatile int *)BALANCE)
#define PS_DIM \
    153 /* 60 %: the dimmed card under Volume Memory (the Keyboards page's English row, patch/m1plus.c KB_EN_DIM) */

static const struct ps_vol {
    const char *label, *slider;
    unsigned refresh, slider_fn, dec, add;
} ps_vols[PS_VOLS] = {
    {"label_vol", "vol_slider", VOL_REFRESH, VOL_SLIDER, VOL_DEC, VOL_ADD},
    {"label_vol", "vol_slider", BOOT_REFRESH, BOOT_SLIDER, BOOT_DEC, BOOT_ADD},
    {"label_balance", "slider_balance", BAL_REFRESH, BAL_SLIDER, BAL_DEC, BAL_ADD},
};

/* Stock's refresh looks both widgets up by name and does nothing without them (Default Volume's takes a mode too: 1 is the label and the slider, 2 the switch, which our page does not have). */
static int ps_vol_ready(void *win, const struct ps_vol *v) {
    return win && widget_lookup(win, v->label, 1) && widget_lookup(win, v->slider, 1);
}

/* Volume Memory's card: dimmed and inert while the byte is set, as stock hides its slider view (our cards stay in place). */
static void ps_vol_dim(void *win) {
    int off = boot_volflag != 0, k;
    static const char *const card[2] = {"pod_vsval", "pod_vsctl"};
    for (k = 0; k < 2; k++) {
        void *c = widget_lookup(win, card[k], 1);
        if (c) widget_set_opacity(c, off ? PS_DIM : 255), widget_set_sensitive(c, !off);
    }
}

/* Max Volume and Default Volume show the number alone: stock's label (label_vol, hidden on our page) gets "VOL: 80" from stock's refresh, ours (pod_vsnum) is set from the same word. Channel Balance shows stock's own text. */
static void ps_vol_num(void *win, int which) {
    char buf[12];
    void *lab = which == PS_VOL_BAL ? (void *)0 : widget_lookup(win, "pod_vsnum", 1);
    if (!lab) return;
    snprintf(buf, sizeof buf, "%d", which == PS_VOL_MAX ? max_volume : boot_volume);
    widget_set_text_utf8(lab, buf);
}

/* Bound to the same events as stock's handlers, and bound first: the emitter puts the newest handler at the head of its list and dispatches from the head (emitter_on_with_tag 0x6f45ac, emitter_dispatch 0x6f4458),
 * so ours runs after stock's, which return 0 (the dispatch goes on), and sees the word as stock left it. */
static int ps_num_max(void *ctx, void *e) {
    (void)e;
    ps_vol_num(ctx, PS_VOL_MAX);
    return RET_OK;
}

static int ps_num_boot(void *ctx, void *e) {
    (void)e;
    ps_vol_num(ctx, PS_VOL_BOOT);
    return RET_OK;
}

void ps_vol_refresh(void *win, int which) {
    const struct ps_vol *v;
    if (which < 0 || which >= PS_VOLS) return;
    v = &ps_vols[which];
    if (ps_vol_ready(win, v)) ((int (*)(void *, int))v->refresh)(win, 1);
    if (win) ps_vol_num(win, which);
    if (which == PS_VOL_BOOT && win) ps_vol_dim(win);
}

void ps_vol_opened(void *win, int which) {
    const struct ps_vol *v;
    void *s, *b;
    if (which < 0 || which >= PS_VOLS) return;
    v = &ps_vols[which];
    if (!ps_vol_ready(win, v)) return;
    ps_vol_refresh(win, which); /* before the handlers are bound: setting the slider is not a change to save */
    s = widget_lookup(win, v->slider, 1);
    {
        int (*num)(void *, void *) = which == PS_VOL_MAX    ? ps_num_max
                                     : which == PS_VOL_BOOT ? ps_num_boot
                                                            : (int (*)(void *, void *))0;
        void *dec = widget_lookup(win, "btn_dec", 1), *add = widget_lookup(win, "btn_add", 1);
        if (num) { /* ours first, so it runs after stock's */
            widget_on(s, EVT_VALUE_CHANGING, (void *)num, win);
            if (dec) widget_on(dec, EVT_CLICK, (void *)num, win);
            if (add) widget_on(add, EVT_CLICK, (void *)num, win);
        }
    }
    widget_on(s, EVT_VALUE_CHANGING, (void *)v->slider_fn, win);
    if ((b = widget_lookup(win, "btn_dec", 1))) widget_on(b, EVT_CLICK, (void *)v->dec, win);
    if ((b = widget_lookup(win, "btn_add", 1))) widget_on(b, EVT_CLICK, (void *)v->add, win);
}

/* Volume Memory: stock's switch (0x49d328): the byte xor 1 stored as the save's callee starts, write_int_config(byte, "PLAYSET", "BOOTVOLFLAG"); stock then redraws its switch and hides its slider view (our page dims the
 * cards when it refreshes). The new state. */
int ps_bootmem(void) { return boot_volflag != 0; }

int ps_bootmem_toggle(void) {
    unsigned char next = boot_volflag ^ 1;
    boot_volflag = next;
    write_int_config(next, "PLAYSET", "BOOTVOLFLAG");
    return boot_volflag != 0;
}

/* The value rows' text on the Playback Settings page: Max Volume the number, Default Volume Memory (a key: 0 here) or the number, Channel Balance as stock's label writes it (L3, 0, R2: 0 is the centre). 1 when buf
 * holds the text, 0 when the row shows ps_value_key's key. */
int ps_value_text(int ctl, char *buf, int n) {
    if (ctl == PS_CTL_MAXVOL)
        snprintf(buf, (unsigned)n, "%d", max_volume);
    else if (ctl == PS_CTL_BOOTVOL) {
        if (boot_volflag) return 0;
        snprintf(buf, (unsigned)n, "%d", boot_volume);
    } else if (ctl == PS_CTL_BAL) {
        int b = balance_word;
        if (b < 10)
            snprintf(buf, (unsigned)n, "L%d", 10 - b);
        else if (b > 10)
            snprintf(buf, (unsigned)n, "R%d", b - 10);
        else
            snprintf(buf, (unsigned)n, "0");
    } else
        return 0;
    return 1;
}
