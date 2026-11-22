# Mono Audio and Crossfeed

**Sources:** `patch/stereo.h`, `patch/stereo.c` (the stage and the record reader),
`patch/peq_player.c` (where it runs, `peq_seteq_flag`), `tools/mod_player.py` (the hciplayer edits),
`patch/stereoset.c` (demo: settings, effective record, player notice), `patch/playset.c` rows via
`patch/m1plus.c`. **Tests:** `test/pod/stereo.py`, `test/pod/playset.py`, `test/pod/i18n.py`.

Two optional stages in the hciplayer float path, set from Settings > Playback Settings. The
crossfeed is Boris Mikhaylov's bs2b (libbs2b 3.1.0, MIT): the one-pole designs, level arithmetic and
three settings are his, rewritten for float blocks (acknowledged in the file headers).

## Behaviour

- **Mono Audio:** L = R = (L + R) / 2 on every output, **before** the EQ cascade (per-side EQ bands
  still apply to the downmix).
- **Crossfeed:** each channel gets the other, low-passed and attenuated, its own highs boosted, the
  sum scaled back (bs2b), **after** the EQ. Levels: Low 650 Hz / 9.5 dB, Medium 700 Hz / 6.0 dB,
  High 700 Hz / 4.5 dB (bs2b's default). The player plays the level the record says; whether it
  applies to the current output is demo's decision (see "Settings and the record").
- Stereo only (`nch == 2`), float domain, 8-384 kHz. Never for DSD, a special format, a rate outside
  the range, or with the kill switch `/mnt/mmc/m1plus-off`.
- **All off is bit-exact:** both stages return before touching a block, and with Equalizer off too
  the native format passes through (see "EQ off keeps the filter").
- A change while playing (the next channel-0 gain command rereads the record) moves linear weights over
  20 ms (`rate / 50` frames). Mono is `L + (M - L) * w`; crossfeed is `dry * (1 - sum w) + sum w * wet`
  over two filter slots. A level change crosses over from the old slot to a new one that starts from
  the old one's memory; changes asked faster than a ramp wait for a free slot (latest wins). A faded
  filter is cleared. A non-finite input sample counts as 0.
- Coefficients are bs2b's, with `exp(x)` as `pow(e, x)` and the gain term as a power of G (no new
  libc import). A `+ 1e-18 - 1e-18` flush keeps tails out of denormals, which trap on the MIPS FPU.

## The record

`/mnt/data/m1plus/playback-stereo` (`STEREO_FILE`), 16 bytes, little endian: `"M1STR01\0"` (8),
`int mono` (0 or 1), `int crossfeed` (0 off, 1 Low, 2 Medium, 3 High). The player reads it with
`fopen/fread` at each REINIT (`stereo_load`) and at each channel-0 gain command. A missing, short,
long, bad-magic or out-of-range record is **both off**. demo writes it whole (tmp, fsync, rename,
creating the folder), like `playback-eq`; `patch/stereo.h` is shared (`stereo_record`).

## The player

`stereo_pre` runs before `peq_process`, `stereo_post` after it, in `play`. State is per instance
(`player_state.st`, heap); the payload has no `.bss`.

**Gapless join.** An instance that played its track out leaves the whole stage in `carry` next to the
EQ's (`stereo_carry`: the Mono weight, both crossfeed slots with weights and filter memory), under
the shared guards (track ended, under 3 s, same rate and channels, finite). The next instance takes it
on its first block and keeps what its own record asks, so a ramp cut short by the track's end finishes
in the next track and a setting changed at the join ramps instead of jumping. The EQ's carry still
needs a settled, equal curve; the stage's does not (`carry.eq`, `carry.st`).

## EQ off keeps the filter

Stock removes the hciplayer filter when the Equalizer switch is off (`mcl-seteq` flag 0). The stage
needs the filter in the chain, so the patched `strtol` call (`SETEQ_CALL`, [peq](peq.md) "The player")
answers 2 for an off flag. Stock takes its flag-2 path: it adds the filter at each file and sends
GAIN SET, and nothing on that path reads the Equalizer switch. Stock's `set_equalizer_value` still
sends flag 0 when the switch is off, so the flag takeover is what keeps the filter.

- With `eq_off` the curve is bypassed (`effective()`). REINIT with both options off (or a track that is
  not stereo) passes the native format and every block through (`pass_native`), so playback is stock's
  bit for bit.
- One exception: a gapless join whose carried stage still has a weight above 0 (an option switched off
  just before the track's end) makes the next instance filter in float, finish the fade, then leave
  every sample alone for the rest of that track (`stereo_carry_live`).
- When the filter must leave native pass-through (EQ switched on, or an option switched on with EQ
  off), `peq_seteq_flag` calls stock's removal once on `mpctx + 0x40` and marks the replacement
  (`replaced`, taken by the next `peq_open` as `ramp_in`). Until that instance has played a block its
  REINIT starts the stage at weight 0 (`stereo_reset` `ramp`), so the option ramps in over 20 ms. A
  track's start plays what the record asks from its first frame.
- The kill switch gets stock's own flag back.

Pins live in `tools/mod_player.py` (`SETEQ_CALL`, the flag paths, the removal call, the insert state
words, the `strtol` stub and its GOT slot); every pin fails the build on a mismatch. `strtol` is the
only libc addition.

## The UI

Settings > Playback Settings > Volume & Sound (`m1plus_psvolume`), under the Stereo header, directly after Channel Balance
([playset](playset.md)):

- **Mono Audio**: a switch row (`ACT_MONO` 145, glyph `volume`).
- **Crossfeed**: a value row (`ACT_XFEED` 146, glyph `headphones`, grey value Off / Low / Medium /
  High) opening the picker `m1plus_psxfeed` (`PSXFEED_PAGE`; rows `ACT_XFEEDSET` 147, arg 0..3, a check
  on the chosen one). A two-line grey note under it: "For headphones and Bluetooth. Not applied to Line
  Out, USB DAC or DSD."

The value row shows the level the user chose, also on Line Out (where the effective level is 0).
"Mono Audio", "Crossfeed" and the note are translated in all 13 languages (`tools/pod_i18n.py`).

## Settings and the record

The user's choices are ours, not stock's: `/mnt/data/m1plus/playback-mono` (`1\n` on; anything else
off) and `/mnt/data/m1plus/playback-crossfeed` (`0\n`..`3\n`; anything else off), written with
`home_write_atomic`. A failed save returns -1 and changes nothing (no toast, as the neighbouring
rows). Choosing the level already set writes nothing. Both are Settings Files rows ([settings](settings.md));
the effective record `playback-stereo` is derived and not listed, and Reset All Settings removes it with
the folder.

`stereo_sync(output, notify)` (`patch/stereoset.c`) computes the effective state: mono = the setting on
every output; crossfeed = the setting when `peqout_current()` is Headphones (jacks and Bluetooth), 0 on
Line Out and USB DAC. It compares with the record on disk and writes it whole only when it differs, so
both off with no record writes nothing. After a write with `notify` it calls
`set_equalizer_value(equalizer_mode)`; the record is always in place before that call. A failed write
leaves the state dirty and the next call retries. A busy flag keeps two threads from writing at once.

**Where it runs:** at the top of `peqout_sync` (after its kill-switch check), so only where peqout
already runs: the status bar timer (`notify` 1, within a second of a jack or DAC change), stock's
`save_start_player` and `mclStartPlayer` hooks (`notify` 0, player thread) and the Equalizer page. No
new hook, timer or boot work. With `notify` 0 the record is written and no command is sent, since the
player reads it at REINIT. A setting change calls it with `notify` 1 on the UI thread. With the kill
switch present nothing is written or sent; the dirty state is applied once it is gone.
