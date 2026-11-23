/* M1+ Music parametric EQ, shared by demo (patch/peq_ui.c, the Equalizer page) and hciplayer (patch/peq_player.c, the
 * filter): the preset, its APO / AutoEQ text parser, the state record and the biquad DSP (docs/modules/peq.md).
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 * After q2-pod's patch/peq.h and patch/peq.c (Copyright (c) 2026 Diamond Bond, MIT licence): the preset layout, the parser,
 * the RBJ designs, Auto preamp and the ramped engine are its, cut to what this project uses (no 3EQ, no visualizer tap,
 * no crossfade; the player carries the filter memory, patch/peq_player.c) and with this project's state record.
 *
 * Built twice: into demo's payload (stock.h's libc stubs) and into hciplayer's (PEQ_PLAYER: player.h, which
 * tools/mod_player.py writes). Each links only what it calls (--gc-sections).
 */
#pragma once

#ifdef PEQ_PLAYER
#include "player.h"
#else
#include "stock.h"
#endif

#define PEQ_BANDS 64 /* the most a preset may have; the engine runs only the bands a preset has */
#define PEQ_CHANNELS 8
#define PEQ_OUT_MAX 1000.0 /* the engine's output bound, +60 dBFS: a finite float whatever the preset */
#define PEQ_FILE_LIMIT 16384
#define PEQ_LINE_LIMIT 512
#define PEQ_TENBAND 10 /* the 10-Band EQ: ten gains, 31 Hz .. 16 kHz, one octave wide */
#define PEQ_GAIN_MAX 12 /* the 10-Band EQ's gain range, dB, either way (stock's ten sliders: the same) */
#define PEQ_PREAMP_AUTO -1 /* peq_state.preamp: Auto; 0..12 is a cut of that many dB */

#define PEQ_STATE \
    "/mnt/data/m1plus/playback-eq" /* the state record in the settings folder, demo writes it whole (tmp, fsync, rename; makes the folder when missing) */
#define PEQ_STATE_DIR "/mnt/data/m1plus"
#define PEQ_MAGIC "M1PEQ03" /* 8 bytes with its NUL */
#define PEQ_DIR "/mnt/mmc/EQ" /* the APO / AutoEQ presets the page lists */
#define PEQ_KILL "/mnt/mmc/m1plus-off" /* the payload's kill switch: the player's filter passes audio through */
#define PEQ_NAME 64

/* enabled: 0 off, 1 both channels, 2 left only, 3 right only. type: 0 peak, 1 low shelf, 2 high shelf.
 * balance: dB, above 0 turns the left channel down, below 0 the right.
 * automatic: the preamp is 1 Auto (the player cuts each rate's own peak), 2 as given (the file's own Preamp:). */
typedef struct {
    int enabled, type;
    double frequency, gain, q;
} peq_band;
typedef struct {
    int count, bypass;
    double preamp;
    peq_band bands[PEQ_BANDS];
    double balance;
    int automatic, spare;
} peq_preset;
typedef struct {
    unsigned line;
    const char *reason; /* a refusal: the line and why; a success: 0 */
    unsigned
        skipped; /* a success: how many lines the parser left out (commands, filter types and channels it has no band for) */
} peq_error;
typedef struct {
    double b0, b1, b2, a1, a2;
} peq_coeff;
typedef struct {
    peq_coeff c[PEQ_BANDS];
    double z[PEQ_CHANNELS][PEQ_BANDS][2], gain[PEQ_CHANNELS];
    int bypass, used,
        only[PEQ_BANDS]; /* used: bands past it are identity with zero memory; only: 0 every channel, else channel only-1 */
} peq_engine;
typedef struct {
    peq_engine current, next, pending;
    int rate, channels, ramp, ramp_length, waiting;
} peq_dsp;

/* The state record, PEQ_STATE after PEQ_MAGIC: which curve plays while stock's Equalizer switch is on. mode PEQ_TENBAND: the 10-Band
 * EQ, ten peaking bands of gain[] (the curve's gains, which are custom[] while curve is PEQ_CUSTOM) and the preamp; PEQ_FILE: preset,
 * parsed from PEQ_DIR/name. curve: PEQ_FLAT .. PEQ_JAZZ (stock's genre gains, peq_curve_gains) or PEQ_CUSTOM (the user's custom[]).
 * preamp: PEQ_PREAMP_AUTO (the player cuts by the response's own peak) or 0..12, a fixed cut in dB. The fields after name are the
 * 10-Band EQ's; a record without them (the previous magic) is no record: Flat, Auto. */
enum { PEQ_TENBAND_MODE, PEQ_FILE };
enum {
    PEQ_FLAT,
    PEQ_POP,
    PEQ_ROCK,
    PEQ_DANCE,
    PEQ_BLUES,
    PEQ_METAL,
    PEQ_VOCAL,
    PEQ_CLASSICAL,
    PEQ_JAZZ,
    PEQ_CUSTOM,
    PEQ_CURVES
};
typedef struct {
    int mode;
    peq_preset preset;
    char name[PEQ_NAME];
    int curve, preamp;
    float gain[PEQ_TENBAND], custom[PEQ_TENBAND];
} peq_state;

void peq_default(peq_preset *p);
int peq_valid(const peq_preset *p);
int peq_number(const char *s, double *out);
int peq_parse(const char *text, unsigned size, peq_preset *out, peq_error *error);
int peq_import_file(const char *path, peq_preset *out, peq_error *error);
int peq_state_load(peq_state *s); /* 0: none readable, s holds the 10-Band EQ: Flat, Auto */
int peq_state_save(const peq_state *s); /* 0 on success */
int peq_state_load_from(const char *path,
                        peq_state *s); /* the same for another record file (a per-output slot, patch/peqout.c) */
int peq_state_save_to(const char *path, const peq_state *s);
/* the 10-Band EQ, gain dB per band (31 Hz .. 16 kHz), as a preset: ten peaking bands, Q 1.41; preamp as peq_state.preamp (Auto: the
 * engine cuts by the response's peak, per rate; else that many dB down) */
void peq_tenband(peq_preset *p, const float *gain, int preamp);
int peq_compile(const peq_preset *p, int rate, peq_engine *out); /* the saved preamp, Auto or not */
void peq_response(const peq_engine *e, int rate, double f, double *l, double *r);
#ifndef PEQ_PLAYER
/* demo only: curve's ten gains (stock's genre table, or s->custom for PEQ_CUSTOM) and the record set to curve with them */
void peq_curve_gains(const peq_state *s, int curve, float *out);
void peq_set_curve(peq_state *s, int curve);
double peq_preamp_gain(
    const peq_preset *p,
    int rate); /* demo only (the preset page): the preamp the player applies at rate, linear (Auto: this rate's own cut) */
#endif
void peq_reset(peq_dsp *d, int rate, int channels, const peq_preset *p);
int peq_update(peq_dsp *d, const peq_preset *p);
void peq_process(peq_dsp *d, float *audio, unsigned frames);

/* MPlayer 1.3.0 libaf/af.h as hciplayer (a64503746862…) has it: the filter peq_player.c opens (tools/mod_player.py pins
 * the stock equalizer's open, which stores control +4, uninit +8, play +0xc, setup +0x10, data +0x14 and mul +0x28). */
typedef struct {
    void *audio;
    int len, rate, nch, format, bps;
} af_data;
typedef struct af_instance {
    const void *info;
    int (*control)(struct af_instance *, int, void *);
    void (*uninit)(struct af_instance *);
    af_data *(*play)(struct af_instance *, af_data *);
    void *setup;
    af_data *data;
    struct af_instance *next, *prev;
    double delay, mul;
} af_instance;

/* The first line of a preset file downloaded from AutoEq (autoeq.c), and what a Save writes over it (peqpage.c); peqlib.c reads both. */
#define PEQ_STAMP "# AutoEq: "
#define PEQ_STAMP_EDITED "# AutoEq edited: "
