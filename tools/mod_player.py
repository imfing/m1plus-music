#!/usr/bin/env python3
"""The player side of the parametric EQ, Mono Audio / Crossfeed, Crossfade, VU tap, radio ICY tap and MQA probe skip:
hciplayer's equalizer filter replaced by patch/peq_player.c (docs/modules/peq.md, docs/modules/stereo.md,
docs/modules/crossfade.md, docs/modules/vu.md, docs/modules/radio.md, docs/modules/mqa.md).

hciplayer (/usr/bin/hciplayer, the audio daemon: MPlayer 1.3.0 modified) is pinned by SHA-256. Its final program
header is an unused PT_NULL; pod.py's append_payload turns it into a file-backed PT_LOAD (RWX) at PLAYER_BASE holding the
payload (patch/peq.c, patch/stereo.c, patch/vu.c and patch/peq_player.c, built with PEQ_PLAYER, non-PIC, linked at PLAYER_BASE, no .bss: per-instance
state is heap). Five edit groups, each pinned with its neighbours and the facts the C code reads:

  * the equalizer's af_info open slot (EQ_OPEN_SLOT, stock af_equalizer open 0x44fd14) becomes peq_open;
  * stock skips the equalizer above 48 kHz in two places (RATE_GATES): the mcl-seteq command (beqz to the
    "===setequalizer off===" log) becomes a nop, and the playback loop's per-stream insert (bnez around the add at
    0x42fbc4) an unconditional branch, so the filter runs at every rate (it passes DSD through itself);
  * the strtol call that parses mcl-seteq's flag (SETEQ_CALL) becomes peq_seteq_flag, which answers 2 for an off flag, so
    stock keeps the filter in the chain with its Equalizer switch off (the filter then passes the native format through
    unless Mono Audio or Crossfeed is on) and, when the filter must leave native pass-through, calls stock's removal
    0x42929c so the playback loop adds a float one. The kill switch gets stock's own answer;
  * the ICY metadata tap calls (ICY_CALLS) and Crossfade's ao_alsa slots and uninit/reinit calls (AO_SLOTS, UNINIT_CALLS);
  * mqa_probe's two non-MQA return immediates (MQA_PROBE_RET: 0x42e548, 0x42e564) change from 1 to 0, so ordinary
    FLAC/PCM tracks skip stock's shadow MQA decoder while real MQA tracks still return 2.

libc is reached only through hciplayer's own PLT GOT slots (no new import): a stub sets $gp and $t8 (the slot, which
the lazy resolver PLT0 expects) and jumps through it, as q2-pod's tools/peq.py does.

Usage: mod_player.py SRC_WORKDIR OUT_WORKDIR     (OUT == SRC edits in place)
"""
import json, os, pathlib, re, stat, struct, sys
from elftools.elf.elffile import ELFFile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modlib import clone_workdir
import pod

REL = 'usr/bin/hciplayer'
PLAYER_SHA = 'a64503746862af3e69b57f2e06167351b30cda28479348a845be5172e083a8c6'
PLAYER_GP = 0xb16750          # DT_PLTGOT + 0x7ff0
PLAYER_BASE = 0xe10000        # stock's last LOAD ends at 0xe03b38
SOURCES = ['peq.c', 'stereo.c', 'vu.c', 'icy.c', 'xfade.c', 'xfsrc.c', 'peq_player.c']
FLAGS = [*pod.FLAGS, '-mnan=2008', '-fno-math-errno', '-DPEQ_PLAYER']   # hciplayer: FP64, NaN2008 (its .MIPS.abiflags, e_flags 0x400)

# The equalizer's af_info: info, name ("equalizer"), author, comment, flags, open.
EQ_INFO = 0x893808
EQ_INFO_WORDS = (0x8937bc, 0x885e2c, 0x89354c, 0x88c3b8, 1, 0x44fd14)
EQ_OPEN_SLOT, STOCK_OPEN = EQ_INFO + 0x14, 0x44fd14
# (address, stock word, patched word)
RATE_GATES = ((0x42ce34, 0x10400098, 0),             # mcl-seteq: beqz $v0, 0x42d098 ("setequalizer off") -> nop
              (0x42fa78, 0x14400052, 0x10000052))    # the insert: bnez $v0, 0x42fbc4 -> b 0x42fbc4
# Non-MQA probe returns (docs/modules/mqa.md): mqa_probe (0x42e428) returns 1 when the track-start probe finds no MQA
# (or a short/unaligned first read), causing reinit_audio_chain (0x42e940) to create the MQA decoder and feed every block
# through it only to discard the output. Returning 0 skips the decoder while real MQA tracks still return 2.
MQA_PROBE_RET = ((0x42e548, 0x24020001, 0x24020000),  # unaligned/short probe: addiu $v0, $zero, 1 -> 0
                 (0x42e564, 0x24020001, 0x24020000))  # detector returned 0:   addiu $v0, $zero, 1 -> 0
# The strtol call that parses mcl-seteq's flag (jal 0xadae10, the PLT stub of strtol): peq_seteq_flag takes it over.
SETEQ_CALL, SETEQ_STOCK = 0x42cd1c, 0x0c2b6b84
# Read-only ICY metadata tap (patch/icy.c, docs/modules/radio.md): MPlayer HTTP mp_msg (jal 0x445cec) and FFmpeg HTTPS av_opt_set (jal 0x6f86f0).
ICY_MP_CALL, ICY_MP_STOCK = 0x4be4d0, 0x0c11173b
ICY_FF_CALL, ICY_FF_STOCK = 0x5020cc, 0x0c1be1bc
# ao_alsa's driver table (0x88f168): the init, pause and resume slots -> Crossfade's wrappers, which call stock's function
# (patch/xfsrc.c, docs/modules/crossfade.md).
AO_SLOTS = ((0x88f170, 0x438648, 'xf_ao_init'), (0x88f188, 0x438224, 'xf_ao_pause'), (0x88f18c, 0x4384ac, 'xf_ao_resume'))
# Two jal calls. The end-of-track cleanup's uninit_player (0x4217d8) is the only one wrapped: xf_uninit_player keeps ALSA open
# across an automatic change while Crossfade is on (patch/xfsrc.c). The other uninit_player sites (0x424074, 0x424244,
# 0x425df8, 0x42e1b4, 0x42eb00, 0x42fa3c, 0x42fae4, 0x430084) stay stock. And reinit_audio_chain (0x421cec): xf_reinit_chain
# prepares the swap's chain.
UNINIT_CALLS = ((0x4217d8, 0x0c10b7bd, 'xf_uninit_player'),
                (0x421cec, 0x0c10b9a0, 'xf_reinit_chain'))
ICY_CALLS = ((ICY_MP_CALL, ICY_MP_STOCK, 'icy_mplayer_msg'), (ICY_FF_CALL, ICY_FF_STOCK, 'icy_av_opt_set'))
# Checked, not written: (address, stock word, what it proves).
PINS = (
    (0x42cd14, 0x2406000a, 'mcl-seteq flag: a2 = 10 (base)'),
    (0x42cd18, 0x00002825, 'mcl-seteq flag: a1 = 0 (no end pointer)'),
    (0x42cd20, 0x27a40e5c, 'mcl-seteq flag: a0 = the text (delay slot of the call)'),
    (0x42cd24, 0x24030001, 'mcl-seteq flag: v1 = 1'),
    (0x42cd28, 0x1043003c, 'mcl-seteq flag: beq v0, v1 -> flag 1 (0x42ce1c)'),
    (0x42cd2c, 0x00408825, 'mcl-seteq flag: s1 = the flag'),
    (0x42cd30, 0x24020002, 'mcl-seteq flag: v0 = 2'),
    (0x42cd34, 0x12220032, 'mcl-seteq flag: beq s1, v0 -> flag 2 (0x42ce00)'),
    (0x42cd54, 0x0c10a4a7, 'mcl-seteq flag 0 (not reached once the flag answers 2): jal 0x42929c, remove "equalizer"'),
    (0x42cd64, 0xac400df0, 'mcl-seteq flag 0 (not reached): sw $zero, 0xdf0: the insert state 0'),
    (0x42ce00, 0x3c060088, 'mcl-seteq flag 2: lui $a2, 0x88 (log)'),
    (0x42ce0c, 0x24c66804, 'mcl-seteq flag 2: the log text "====pre_eqset======" (0x886804)'),
    (0x42ce10, 0x3c0200b1, 'mcl-seteq flag 2: lui $v0, 0xb1'),
    (0x42ce14, 0x1000fc3e, 'mcl-seteq flag 2: b 0x42bf10'),
    (0x42ce18, 0xac510df0, 'mcl-seteq flag 2: sw $s1, 0xdf0($v0): the insert state becomes the flag, 2'),
    (0x42ce3c, 0x24030002, 'mcl-seteq flag 1: v1 = 2'),
    (0x42ce44, 0xac430df0, 'mcl-seteq flag 1: sw $v1, 0xdf0($v0): the insert state 2'),
    (0x42929c, 0x27bdffd8, 'remove: the function stock removes "equalizer" with (a0 = mpctx + 0x40): addiu sp'),
    (0x4292b0, 0x8c920004, 'remove: lw $s2, 4($a0): the filter chain'),
    (0x4224e0, 0x8c440df0, 'file start: lw the insert state'),
    (0x4224e4, 0x14830002, 'file start: bne state, 1'),
    (0x4224ec, 0xac430df0, 'file start: state 1 becomes 2 (the filter is added again for each file)'),
    (0x42f438, 0x8e830df0, 'the loop: lw the insert state'),
    (0x42fbd4, 0xae820df0, 'the insert: state 1 after the add'),
    (0xadae10, 0x3c0f00b0, 'strtol stub: lui $t7, 0xb0'),
    (0xadae14, 0x8df998e8, 'strtol stub: lw $t9, -0x6718($t7): the GOT slot 0xaf98e8 (strtol)'),
    (0x42ce1c, 0x3c0200b0, 'mcl-seteq gate: lui $v0, 0xb0'),
    (0x42ce20, 0x3403bb81, 'mcl-seteq gate: ori $v1, $zero, 48001'),
    (0x42ce24, 0x8c429e30, 'mcl-seteq gate: lw $v0, -0x61d0($v0): mpctx at 0xaf9e30'),
    (0x42ce28, 0x8c42002c, 'mcl-seteq gate: lw $v0, 0x2c($v0): mpctx->sh_audio'),
    (0x42ce2c, 0x8c42003c, 'mcl-seteq gate: lw $v0, 0x3c($v0): the sample rate'),
    (0x42ce30, 0x0043102a, 'mcl-seteq gate: slt $v0, $v0, $v1'),
    (0x42f43c, 0x1062018a, 'the loop: beq $v1, $v0 (insert pending) to the insert gate'),
    (0x42f440, 0x3403bb81, 'the loop: ori $v1, $zero, 48001'),
    (0x42fa68, 0x8e649e30, 'insert gate: lw $a0, -0x61d0($s3): mpctx'),
    (0x42fa6c, 0x8c82002c, 'insert gate: sh_audio'),
    (0x42fa70, 0x8c42003c, 'insert gate: the sample rate'),
    (0x42fa74, 0x0043102a, 'insert gate: slt'),
    (0x42fbc4, 0x0c10a473, 'the insert: jal 0x4291cc (find or add "equalizer", then GAIN SET channels 0..7)'),
    (0x4291f8, 0x26715e2c, 'add: the name "equalizer" (0x885e2c)'),
    (0x429228, 0x3c1300b1, 'add: lui $s3, 0xb1'),
    (0x42922c, 0x3c124000, 'add: lui $s2, 0x4000'),
    (0x429234, 0x26730df4, 'add: the gains at 0xb10df4'),
    (0x429238, 0x26521d00, 'add: AF_CONTROL_EQUALIZER_GAIN | SET (0x40001d00)'),
    (0x42923c, 0x8e190004, 'add: lw $t9, 4($s0): af->control'),
    (0x429250, 0x0320f809, 'add: jalr $t9'),
    (0x42ca74, 0x24570df4, 'mcl-seteq: the ten gains parsed into 0xb10df4'),
    (0x42ca7c, 0xe4400df4, 'mcl-seteq: swc1 (float gains)'),
    (0x42f78c, 0x8e629e30, 'the audio EOF test: lw $v0, -0x61d0($s3): mpctx'),
    (0x42f790, 0x8c420034, 'the audio EOF test: mpctx->d_audio (+0x34)'),
    (0x42f794, 0x8c42001c, 'the audio EOF test: d_audio->eof (+0x1c), what the carried filter memory reads'),
    (0x47ed5c, 0x8e020004, 'sh_audio->codec (+4)'),
    (0x47ed74, 0x8c4703d0, 'codec->name (+0x3d0)'),
    (0x47ed7c, 0x8c4203e0, 'codec->drv (+0x3e0)'),
    (0x44fd38, 0xac820004, 'stock open: af->control at +4'),
    (0x44fd48, 0xac820008, 'stock open: af->uninit at +8'),
    (0x44fd54, 0xf4800028, 'stock open: af->mul (double) at +0x28'),
    (0x44fd60, 0xae02000c, 'stock open: af->play at +0xc'),
    (0x44fd6c, 0xae020014, 'stock open: af->data at +0x14'),
    (0x44fd7c, 0xae020010, 'stock open: af->setup at +0x10'),
    (0x44fe38, 0x3c021000, 'stock control: lui 0x1000'),
    (0x44fe3c, 0x24420100, 'stock control: AF_CONTROL_REINIT 0x10000100'),
    (0x44fe48, 0x3c022000, 'stock control: lui 0x2000'),
    (0x44fe4c, 0x24420300, 'stock control: AF_CONTROL_COMMAND_LINE 0x20000300'),
    (0x42686c, 0x8e060008, 'playing_audio_pts caller: lw $a2, 8($s0): mpctx->audio_out (the level tap reads the output delay from it)'),
    (0x426878, 0x8e050034, 'playing_audio_pts caller: lw $a1, 0x34($s0): mpctx->d_audio'),
    (0x42687c, 0x0c10c03d, 'playing_audio_pts caller: jal 0x4300f4'),
    (0x43010c, 0x00c08825, 'playing_audio_pts: move $s1, $a2 (the audio_out)'),
    (0x430148, 0x8e39001c, 'playing_audio_pts: lw $t9, 0x1c($s1): audio_out->get_delay'),
    (0x430170, 0x0320f809, 'playing_audio_pts: jalr $t9 (no argument; the float seconds come back in $f0)'),
    (0x43018c, 0x46010002, 'playing_audio_pts: mul.s $f0, $f0, $f1 (speed): the delay is a single float'),
    (0x44fddc, 0x3c024000, 'stock control: lui 0x4000'),
    (0x44fdec, 0x24431d00, 'stock control: AF_CONTROL_EQUALIZER_GAIN 0x40001d00'),
    (0x4bdf70, 0x24427264, 'MPlayer ICY: addiu $v0, $v0, 0x7264 ("\\nICY Info: %s\\n" at 0x8a7264)'),
    (0x4be4c0, 0x8fa6002c, 'MPlayer ICY: lw $a2, 0x2c($sp) (format string)'),
    (0x4be4c4, 0x24050004, 'MPlayer ICY: a1 = MSGL_INFO (4)'),
    (0x4be4c8, 0x24040005, 'MPlayer ICY: a0 = MSGT_NETWORK (5)'),
    (0x4be4cc, 0x03c03825, 'MPlayer ICY: a3 = $fp (ICY info string)'),
    (0x4be4d4, 0xa0400000, 'MPlayer ICY: delay slot sb $zero, ($v0) (NUL-terminates $fp)'),
    (0x445cec, 0x27bdffd8, 'mp_msg prologue: addiu $sp, $sp, -0x28'),
    (0x445cfc, 0xafa70034, 'mp_msg prologue: sw $a3, 0x34($sp)'),
    (0x5020b4, 0x3c05008b, 'FFmpeg ICY: lui $a1, 0x8b'),
    (0x5020bc, 0x00003825, 'FFmpeg ICY: a3 = 0 (flags)'),
    (0x5020c0, 0x24a52b50, 'FFmpeg ICY: a1 = "icy_metadata_packet" (0x8b2b50)'),
    (0x5020c4, 0x00403025, 'FFmpeg ICY: a2 = $v0 (packet buffer)'),
    (0x5020c8, 0xa2800001, 'FFmpeg ICY: sb $zero, 1($s4) (NUL-terminates packet buffer)'),
    (0x5020d0, 0x02602025, 'FFmpeg ICY: delay slot a0 = $s3 (HTTPContext)'),
    (0x6f86f0, 0x27bdffb0, 'av_opt_set prologue: addiu $sp, $sp, -0x50'),
    # Sticky output (patch/xfsrc.c): the end-of-track cleanup, the swap's mpctx copy, the AO-kept chain rebuild.
    (0x4217c8, 0x3404ff7a, 'end-of-track cleanup: ori $a0, $zero, 0xff7a (the uninit_player mask)'),
    (0x4217d0, 0x8c420bb8, 'end-of-track cleanup: lw $v0, 0xbb8($v0)'),
    (0x4217d4, 0x2c420001, 'end-of-track cleanup: sltiu $v0, $v0, 1 (mask + 1 when [0xb10bb8] == 0)'),
    (0x4217dc, 0x00442021, 'end-of-track cleanup: addu $a0, $v0, $a0 (delay slot: the mask)'),
    (0x42def4, 0x27bdffd0, 'uninit_player prologue (a0 = mask, anded with the flags word 0xb10e70)'),
    (0x42df28, 0x02078024, 'uninit_player: and $s0, $s0, $a3 (mask & flags)'),
    (0x42e01c, 0x32020002, 'uninit_player: andi $v0, $s0, 2 (the audio output bit)'),
    (0x42e050, 0x8c820008, 'uninit_player: lw $v0, 8($a0): mpctx->audio_out'),
    (0x422268, 0x8c440008, 'gapless swap: lw $a0, 8($v0): next_mpctx->audio_out is copied into mpctx'),
    (0x421a0c, 0x8e030e40, 'loop head: lw $v1, 0xe40($s0): the gapless switch'),
    (0x421a10, 0x1062020c, 'loop head: beq $v1, 1 -> the swap'),
    (0x42e6d0, 0x32100002, 'reinit_audio_chain: andi $s0, $s0, 2 (audio output initialized: skip ao init)'),
    (0x42e7cc, 0x8c640008, 'reinit_audio_chain (output kept): lw $a0, 8($v1): mpctx->audio_out'),
    (0x42e7d4, 0xac640040, 'reinit_audio_chain (output kept): sw $a0, 0x40($v1)'),
    (0x42e7b0, 0x0c11fbc1, 'reinit_audio_chain (output kept): jal init_audio_filters (0x47ef04) against ao_data'),
    (0x44c79c, 0x26130028, 'rate negotiation: addiu $s3, $s0, 0x28 (the wanted rate)'),
    (0x44c7a0, 0x26520100, 'rate negotiation: addiu $s2, $s2, 0x100 (AF_CONTROL_RESAMPLE_RATE | SET 0x40000100)'),
    (0x44c7a4, 0x8e390004, 'rate negotiation: lw $t9, 4($s1): the filter\'s control'),
    (0x44c7b0, 0x0320f809, 'rate negotiation: jalr $t9'),
    (0x44c7b8, 0x24030001, 'rate negotiation: v1 = 1 (AF_OK)'),
    (0x44c7bc, 0x10430057, 'rate negotiation: beq v0, v1: the first AF_OK stops the search'),
    (0x44c7c4, 0x8e31001c, 'rate negotiation: lw $s1, 0x1c($s1): the previous filter'),
    # The position of a track whose decoder gives no timestamps (patch/xfade.c track_a_pos): stock's calc_a_pts.
    (0x44601c, 0x8c8200d0, 'calc_a_pts: lw $v0, 0xd0($a0): sh_audio->pts_bytes'),
    (0x446020, 0xd4800020, 'calc_a_pts: ldc1 $f0, 0x20($a0): sh_audio->pts'),
    (0x446038, 0xd4a00010, 'calc_a_pts: ldc1 $f0, 0x10($a1): d_audio->pts'),
    (0x44603c, 0x8c830050, 'calc_a_pts: lw $v1, 0x50($a0): sh_audio->i_bps'),
    (0x446098, 0x8ca60004, 'calc_a_pts: lw $a2, 4($a1): d_audio->buffer_size'),
    (0x4460a0, 0x8ca20018, 'calc_a_pts: lw $v0, 0x18($a1): d_audio->pts_bytes'),
    (0x4460a4, 0x8ca50000, 'calc_a_pts: lw $a1, ($a1): d_audio->buffer_pos'),
    (0x4460a8, 0x8c83005c, 'calc_a_pts: lw $v1, 0x5c($a0): sh_audio->a_in_buffer_len'),
    # The unwritten tail (flush_tail) and pause in a sticky session (xf_ao_pause, xf_ao_resume).
    (0x42f2d4, 0x8c590014, 'fill_audio_out_buffers: lw $t9, 0x14($v0): the driver\'s get_space'),
    (0x42f6d0, 0x8c590018, 'fill_audio_out_buffers: lw $t9, 0x18($v0): the driver\'s play'),
    (0x42f6ec, 0x8e26007c, 'fill_audio_out_buffers: lw $a2, 0x7c($s1): sh_audio->a_out_buffer_len (what play left)'),
    (0x42f6f0, 0x8e240078, 'fill_audio_out_buffers: lw $a0, 0x78($s1): sh_audio->a_out_buffer'),
    (0x88f17c, 0x00437e1c, 'ao_alsa driver table: get_space'),
    (0x42fd00, 0x8c790020, 'pause loop: lw $t9, 0x20($v1): the driver\'s pause'),
    (0x42fe80, 0x8c420014, 'pause loop end: lw $v0, 0x14($v0): mpctx->eof'),
    (0x42fe84, 0x1040008f, 'pause loop end: beqz -> the driver\'s resume (else its reset)'),
    (0x4300c4, 0x8c790024, 'pause loop end: lw $t9, 0x24($v1): the driver\'s resume'),
    (0x430084, 0x0c10b7bd, 'pause loop end, output device changed: jal uninit_player'),
    (0x430088, 0x24040002, 'pause loop end, output device changed: a0 = 2 (the audio output)'),
    (0x43008c, 0x0c10b9a0, 'pause loop end, output device changed: jal reinit_audio_chain, then the resume'),
    (0x42e680, 0x27bdff90, 'reinit_audio_chain prologue'),
    (0x4a4730, 0x27bdffd8, 'usec_sleep prologue'),
    # libswresample (statically linked, plain O32 calls, patch/xfsrc.c).
    (0x7235bc, 0x27bdffc0, 'swr_alloc_set_opts prologue: addiu $sp, $sp, -0x40'),
    (0x7235d4, 0xafa40040, 'swr_alloc_set_opts: sw $a0, 0x40($sp)'),
    (0x7235d8, 0x8fb00050, 'swr_alloc_set_opts: lw $s0, 0x50($sp): the stack arguments start at the caller\'s 0x10'),
    (0x41e32c, 0x27bdf798, 'swr_init prologue: addiu $sp, $sp, -0x868'),
    (0x724b40, 0x27bdfea0, 'swr_convert prologue: addiu $sp, $sp, -0x160'),
    (0x724b44, 0x8c8231f8, 'swr_convert: lw $v0, 0x31f8($a0)'),
    (0x41e2d0, 0x27bdffd8, 'swr_free prologue: addiu $sp, $sp, -0x28'),
    (0x6f9770, 0x27bdffb0, 'av_opt_set_int prologue: addiu $sp, $sp, -0x50'),
    (0x6f9774, 0x00c01825, 'av_opt_set_int: move $v1, $a2 (the int64 value in a2:a3)'),
    (0x6f870c, 0x00c09025, 'av_opt_set prologue: move $s2, $a2'),
    # Crossfade (patch/xfade.c, docs/modules/crossfade.md): PreInitNextSong next_mpctx, codec init, cleanup, duration, ReplayGain.
    (0x42b8c8, 0x26109b90, 'PreInitNextSong: next_mpctx 0xaf9b90'),
    (0x42b9d4, 0xae020028, 'PreInitNextSong: next_mpctx->demuxer (+0x28)'),
    (0x42ba7c, 0xac440dd0, 'PreInitNextSong: next_state = 2 (0xb10dd0)'),
    (0x42ba9c, 0x8c460c28, 'PreInitNextSong: afm_list (0xb10c28)'),
    (0x42baa4, 0x0c11fad4, 'PreInitNextSong: jal init_best_audio_codec (0x47eb50)'),
    (0x42baa8, 0x8c450c4c, 'PreInitNextSong: acodec_list (0xb10c4c)'),
    (0x42babc, 0xac430d70, 'PreInitNextSong: next_codec_inited = 1 (0xb10d70)'),
    (0x42ba38, 0x8c630c54, 'PreInitNextSong: mqa_mode (0xb10c54)'),
    (0x422244, 0x8ec30dd0, 'gapless swap: lw next_state (0xb10dd0)'),
    (0x422258, 0x24429b90, 'gapless swap: next_mpctx (0xaf9b90)'),
    (0x4222b0, 0x8c820d70, 'gapless swap: lw next_codec_inited (0xb10d70)'),
    (0x42a9cc, 0x27bdffd8, 'uninit_next_song prologue'),
    (0x42a9e0, 0x26109b90, 'uninit_next_song: next_mpctx (0xaf9b90)'),
    (0x42aa1c, 0x8c630d70, 'uninit_next_song: lw next_codec_inited (0xb10d70)'),
    (0x42aab4, 0x0c11f980, 'uninit_next_song: jal uninit_audio (0x47e600)'),
    (0x42c1cc, 0x8c440dd0, 'mcl-closegapless: lw next_state (0xb10dd0)'),
    (0x42c1d4, 0xaca00de0, 'mcl-closegapless: sw zero, next_flag (0xb10de0)'),
    (0x42d05c, 0xac430de0, 'set-gapless: sw 1, next_flag (0xb10de0)'),
    (0x47eb50, 0x27bdff90, 'init_best_audio_codec prologue'),
    (0x5b6504, 0x3c0200b1, 'flac_decode_frame: lui 0xb1 (FLAC seek trim 0xb15290)'),
    (0x5b6508, 0xc4415290, 'flac_decode_frame: lwc1 seek trim (0xb15290): frames starting before it return -1'),
    (0x5b650c, 0x4601003c, 'flac_decode_frame: c.lt.s start time, seek trim'),
    (0x48b2c8, 0xac405290, 'demux_audio close: seek trim = 0 (0xb15290)'),
    (0x48cdd8, 0xe6405290, 'demux_audio FLAC seek: swc1 seek trim (0xb15290)'),
    (0x486914, 0x27bdffc8, 'demuxer_get_time_length prologue'),
    (0x42c9d0, 0xac470e30, 'mcl-replaygain: sw rg_mode (0xb10e30)'),
    (0x428358, 0x24c3c790, 'replaygain: rg_next (0xb0c790)'),
    (0x47f35c, 0x8fc90088, 'mp_decode_audio: lw ad_driver (+0x88)'),
    (0x47f36c, 0x8d390014, 'mp_decode_audio: lw decode_audio (+0x14)'),
    (0x44601c, 0x8c8200d0, 'audio_pts: lw sh->pts_bytes (+0xd0)'),
    (0x446020, 0xd4800020, 'audio_pts: ldc1 sh->pts (+0x20)'),
    (0x446078, 0x8c83004c, 'audio_pts: lw sh->o_bps (+0x4c)'),
    # MQA track-start probe (0x42e428, docs/modules/mqa.md) and its callers / play_audio gates.
    (0x42e428, 0x27bdffd8, 'mqa_probe prologue: addiu $sp, $sp, -0x28'),
    (0x42e430, 0x2403000b, 'mqa_probe: codec 11 (FLAC/PCM)'),
    (0x42e450, 0x2403000d, 'mqa_probe: codec 13 (FLAC/PCM)'),
    (0x42e478, 0x24020002, 'mqa_probe: stereo check (2 channels)'),
    (0x42e47c, 0x1622fff8, 'mqa_probe: bne $s1, 2 -> return 0'),
    (0x42e4d8, 0x0c1cbcc0, 'mqa_probe: jal 0x72f300 (alloc MQA detector)'),
    (0x42e53c, 0x0c1cbcd8, 'mqa_probe: jal 0x72f360 (free detector on unaligned/short read)'),
    (0x42e544, 0x1000ffc6, 'mqa_probe: b 0x42e460 (return path for 0x42e548 delay slot)'),
    (0x42e550, 0x0c1cbce0, 'mqa_probe: jal 0x72f380 (run MQA detector)'),
    (0x42e55c, 0x0c1cbcd8, 'mqa_probe: jal 0x72f360 (free detector after probe)'),
    (0x42e560, 0x00408025, 'mqa_probe: move $s0, $v0 (detector result)'),
    (0x42e568, 0x3a100001, 'mqa_probe: xori $s0, $s0, 1 (0 when real MQA)'),
    (0x42e56c, 0x1000ffbc, 'mqa_probe: b 0x42e460 (return)'),
    (0x42e570, 0x0230100a, 'mqa_probe: movz $v0, $s1, $s0 (real MQA returns 2)'),
    (0x42e578, 0x2402ffff, 'mqa_probe: decode error returns -1'),
    (0x42e924, 0x0c10b90a, 'reinit_audio_chain: jal 0x42e428 (mqa_probe, 0xc00 bytes)'),
    (0x42e940, 0x19a001d1, 'reinit_audio_chain: blez $t5, 0x42f088 (skip MQA decoder when <= 0)'),
    (0x42eeac, 0x0c10b90a, 'reinit_audio_chain: jal 0x42e428 (mqa_probe, 0x10000 bytes)'),
    (0x42ea88, 0x0c1cbce2, 'reinit_audio_chain: jal 0x72f388 (create MQA decoder)'),
    (0x42efbc, 0xad8d0c54, 'reinit_audio_chain: sw $t5, 0xc54($t4) (store mqa_mode)'),
    (0x42f468, 0x8c420c54, 'fill_audio_out_buffers: lw mqa_mode (status check)'),
    (0x42f690, 0x8c420c54, 'fill_audio_out_buffers: lw mqa_mode (decode gate)'),
    (0x42f7cc, 0x8c420c54, 'fill_audio_out_buffers: lw mqa_mode (EOF flush gate)'),
)
NAME_AT, NAME = 0x885e2c, b'equalizer\0'
DSD_DRV = (0x89b4f0, b'dsdiff\0')   # the vendor's DSD driver name, as the filter compares it
ICY_STRS = ((0x8a7264, b'\nICY Info: %s\n\0'), (0x8b2b50, b'icy_metadata_packet\0'))
# libc: name -> (C prototype, the PLT symbol hciplayer imports it as)
LIBC = {
    'memset': ('void *', 'void *, int, unsigned', 'memset'), 'memcpy': ('void *', 'void *, const void *, unsigned', 'memcpy'),
    'memcmp': ('int', 'const void *, const void *, unsigned', 'memcmp'), 'strcmp': ('int', 'const char *, const char *', 'strcmp'),
    'strlen': ('unsigned', 'const char *', 'strlen'), 'calloc': ('void *', 'unsigned, unsigned', 'calloc'),
    'free': ('void', 'void *', 'free'), 'fopen': ('void *', 'const char *, const char *', 'fopen64'),
    'fread': ('unsigned', 'void *, unsigned, unsigned, void *', 'fread'), 'fclose': ('int', 'void *', 'fclose'),
    'fseek': ('int', 'void *, long, int', 'fseek'), 'fwrite': ('unsigned', 'const void *, unsigned, unsigned, void *', 'fwrite'),
    'clock_gettime': ('int', 'int, void *', 'clock_gettime'), 'strtol': ('long', 'const char *, char **, int', 'strtol'),
    'pow': ('double', 'double, double', '__pow_finite'), 'cos': ('double', 'double', 'cos'), 'sin': ('double', 'double', 'sin'),
}


def plt_slots(path):
    """name -> the .got.plt slot of each LIBC import (the MIPS PLT: .rel.plt's R_MIPS_JUMP_SLOT entries)."""
    with open(path, 'rb') as f:
        elf = ELFFile(f)
        rel, syms = elf.get_section_by_name('.rel.plt'), elf.get_section_by_name('.dynsym')
        found = {syms.get_symbol(r['r_info_sym']).name: r['r_offset'] for r in rel.iter_relocations()}
    want = {imp for _, _, imp in LIBC.values()}
    missing = sorted(want - set(found))
    pod.check(not missing, f'hciplayer does not import {missing}')
    return {name: found[imp] for name, (_, _, imp) in LIBC.items()}


def word(b, a): return struct.unpack_from('<I', b, pod.fileoff(b, a))[0]


def check_stock(raw):
    pod.check(pod.sha(raw) == PLAYER_SHA, f'{REL} is not the pinned stock binary')
    got = tuple(word(raw, EQ_INFO + 4 * i) for i in range(6))
    pod.check(got == EQ_INFO_WORDS, f'equalizer af_info at {EQ_INFO:#x}: {[hex(w) for w in got]}')
    pod.check(word(raw, SETEQ_CALL) == SETEQ_STOCK, f'{SETEQ_CALL:#x}: mcl-seteq strtol call {word(raw, SETEQ_CALL):#010x}')
    for a, old, name in ICY_CALLS:
        pod.check(word(raw, a) == old, f'{a:#x} ({name}): {word(raw, a):#010x} != {old:#010x}')
    for a, old, name in UNINIT_CALLS:
        pod.check(word(raw, a) == old, f'{a:#x} ({name}): {word(raw, a):#010x} != {old:#010x}')
    for a, old, name in AO_SLOTS:
        pod.check(word(raw, a) == old, f'{a:#x} ({name}): ao_alsa slot {word(raw, a):#010x} != {old:#010x}')
    for a, old, _ in RATE_GATES:
        pod.check(word(raw, a) == old, f'{a:#x}: rate gate {word(raw, a):#010x} != {old:#010x}')
    for a, old, _ in MQA_PROBE_RET:
        pod.check(word(raw, a) == old, f'{a:#x}: mqa probe return {word(raw, a):#010x} != {old:#010x}')
    for a, old, what in PINS:
        pod.check(word(raw, a) == old, f'{a:#x} ({what}): {word(raw, a):#010x} != pinned {old:#010x}')
    for a, s in ((NAME_AT, NAME), DSD_DRV, *ICY_STRS):
        off = pod.fileoff(raw, a)
        pod.check(raw[off:off + len(s)] == s, f'{a:#x}: not {s!r}')


def compile_payload(build, slots):
    header = ['/* generated by tools/mod_player.py: hciplayer libc through its own PLT slots */', '#pragma once']
    asm = ['.set noreorder', '.text']
    for name, (ret, args, _) in LIBC.items():
        header += [f'extern {ret} peq_lib_{name}({args});', f'#define {name} peq_lib_{name}']
        slot = slots[name]
        asm += [f'.section .text.peq_lib_{name},"ax",@progbits', f'.globl peq_lib_{name}', f'peq_lib_{name}:',
                f'lui $gp, {PLAYER_GP >> 16}', f'ori $gp, $gp, {PLAYER_GP & 0xffff}',
                f'lui $t8, {slot >> 16}', f'ori $t8, $t8, {slot & 0xffff}', 'lw $t9, 0($t8)', 'jr $t9', 'nop']
    asm += ['.globl memcpy', '.set memcpy, peq_lib_memcpy', '.globl memset', '.set memset, peq_lib_memset']   # the compiler's own struct copies
    (build / 'player.h').write_text('\n'.join(header) + '\n')
    (build / 'player_asm.S').write_text('\n'.join(asm) + '\n')
    objs = []
    for src in SOURCES:
        obj = build / (src + '.o')
        pod.run(pod.CLANG, *FLAGS, '-I', build, '-I', pod.PATCH, '-c', os.path.join(pod.PATCH, src), '-o', obj)
        objs.append(obj)
    pod.run(pod.CLANG, *FLAGS, '-c', build / 'player_asm.S', '-o', build / 'player_asm.o')
    script = build / 'player.ld'
    script.write_text(f'SECTIONS {{ . = {PLAYER_BASE:#x}; .text : {{ *(.text*) }} .rodata : {{ *(.rodata*) }} '
                      '.data : { *(.data*) *(.sdata*) } .bss : { *(.bss*) *(.sbss*) *(COMMON) } '
                      '/DISCARD/ : { *(.comment) *(.note*) *(.pdr) *(.mdebug*) *(.MIPS.abiflags) *(.reginfo) *(.gnu.attributes) } }\n')
    pod.run(pod.LD, '-m', 'elf32ltsmip', '--gc-sections', '-T', script, '-e', 'peq_open', '-u', 'peq_seteq_flag',
            '-u', 'icy_mplayer_msg', '-u', 'icy_av_opt_set', *(x for _, _, n in UNINIT_CALLS for x in ('-u', n)),
            *(x for _, _, n in AO_SLOTS for x in ('-u', n)), *objs, build / 'player_asm.o', '-o', build / 'player.elf')
    pod.run(pod.OBJCOPY, '-O', 'binary', build / 'player.elf', build / 'player.bin')
    with open(build / 'player.elf', 'rb') as f:
        elf = ELFFile(f)
        for sec in elf.iter_sections():
            if sec.name in ('.bss', '.sbss') and sec['sh_size']:
                raise ValueError(f'player payload has non-empty {sec.name}: its state is per instance, on the heap')
        syms = {s.name: s['st_value'] for s in elf.get_section_by_name('.symtab').iter_symbols() if s.name}
    return syms, (build / 'player.bin').read_bytes()


def patch(raw, payload, syms):
    image = bytearray(raw)
    entry = syms['peq_open']
    pod.check(PLAYER_BASE <= entry < PLAYER_BASE + len(payload), 'peq_open outside the payload')
    struct.pack_into('<I', image, pod.fileoff(image, EQ_OPEN_SLOT), entry)
    for a, _, new in RATE_GATES: struct.pack_into('<I', image, pod.fileoff(image, a), new)
    for a, _, new in MQA_PROBE_RET: struct.pack_into('<I', image, pod.fileoff(image, a), new)
    flag = syms['peq_seteq_flag']
    pod.check(PLAYER_BASE <= flag < PLAYER_BASE + len(payload), 'peq_seteq_flag outside the payload')
    struct.pack_into('<I', image, pod.fileoff(image, SETEQ_CALL), 0x0c000000 | flag >> 2)
    for a, _, name in ICY_CALLS:
        target = syms[name]
        pod.check(PLAYER_BASE <= target < PLAYER_BASE + len(payload), f'{name} outside the payload')
        struct.pack_into('<I', image, pod.fileoff(image, a), 0x0c000000 | target >> 2)
    for a, _, name in UNINIT_CALLS:
        target = syms[name]
        pod.check(PLAYER_BASE <= target < PLAYER_BASE + len(payload), f'{name} outside the payload')
        struct.pack_into('<I', image, pod.fileoff(image, a), 0x0c000000 | target >> 2)
    for a, _, name in AO_SLOTS:
        target = syms[name]
        pod.check(PLAYER_BASE <= target < PLAYER_BASE + len(payload), f'{name} outside the payload')
        struct.pack_into('<I', image, pod.fileoff(image, a), target)
    seg_off = pod.append_payload(image, payload, PLAYER_BASE)
    return bytes(image), seg_off


def apply(out):
    path = os.path.join(out, 'rootfs', REL)
    raw = open(path, 'rb').read()
    check_stock(raw)
    build = pathlib.Path(out) / 'playerbuild'; build.mkdir(exist_ok=True)
    slots = plt_slots(path)
    pod.check(slots['strtol'] == 0xaf98e8, f'strtol slot {slots["strtol"]:#x}: not what the stub at 0xadae10 jumps through')
    syms, payload = compile_payload(build, slots)
    patched, seg_off = patch(raw, payload, syms)
    mode = stat.S_IMODE(os.stat(path).st_mode)
    os.chmod(path, mode | 0o200); open(path, 'wb').write(patched); os.chmod(path, mode)
    manifest = {'stock_sha256': PLAYER_SHA, 'patched_sha256': pod.sha(patched), 'base': PLAYER_BASE, 'gp': PLAYER_GP,
                'payload_len': len(payload), 'payload_sha256': pod.sha(payload), 'segment_file_off': seg_off,
                'open_slot': {'addr': EQ_OPEN_SLOT, 'stock': STOCK_OPEN, 'target': syms['peq_open']},
                'rate_gates': [[a, old, new] for a, old, new in RATE_GATES],
                'mqa_probe_ret': [[a, old, new] for a, old, new in MQA_PROBE_RET], 'libc_slots': slots,
                'seteq_call': {'addr': SETEQ_CALL, 'stock': SETEQ_STOCK, 'target': syms['peq_seteq_flag']},
                'uninit_calls': [{'addr': a, 'stock': old, 'target': syms[name], 'name': name} for a, old, name in UNINIT_CALLS],
                'icy_calls': [{'addr': a, 'stock': old, 'target': syms[name], 'name': name} for a, old, name in ICY_CALLS],
                'symbols': {n: syms[n] for n in sorted(syms) if re.fullmatch(r'(?:peq|icy|xf|xfsrc|xfade)_\w+', n)}}
    (build / 'manifest.json').write_text(json.dumps(manifest, indent=1) + '\n')
    print(f'player: payload {len(payload)} bytes @ {PLAYER_BASE:#x}, equalizer open {EQ_OPEN_SLOT:#x} -> '
          f'{syms["peq_open"]:#x}, rate gates {", ".join(hex(a) for a, _, _ in RATE_GATES)}, '
          f'mcl-seteq flag {SETEQ_CALL:#x} -> {syms["peq_seteq_flag"]:#x}, '
          f'icy {", ".join(f"{a:#x}->{syms[n]:#x}" for a, _, n in ICY_CALLS)}')


if __name__ == '__main__':
    clone_workdir(sys.argv[1], sys.argv[2]); apply(sys.argv[2])
