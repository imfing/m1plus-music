"""Settings > Playback Settings (patch/playset.c, docs/modules/playset.md): our page for stock's All Playback Settings rows. Every state is stock's own and is written the way stock's own click handlers write it, which the
tests check by running stock's handlers under the emulator on the same state and comparing the stored values, the saves and the calls into the player and the driver, in order, with ours."""
import os
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)
import awtk_ui

D = pod.DATA
MCL_GAPLESS, MCL_JUMP = D['MCL_GAPLESS'][0], 0xa0ab88   # the mcl bytes
MCL_GAIN, MCL_FILTER, MCL_REPLAY, MCL_DSD = 0xa0abbc, 0xa0abac, 0xa0abb8, 0xa0abb4   # the mcl words (the getters' reads)
MEM, DIGITAL, USBVOL, LINEOUT, FOLDER, VOLUME = (D[n][0] for n in ('MEMORY_PLAY', 'DIGITAL_FLAG', 'USBVOL_MODE', 'LINEOUT_FLAG', 'FOLDER_COVER', 'G_VOLUME'))
MAXV, BOOTV, BOOTFLAG, BAL, HEADSET = (D[n][0] for n in ('MAX_VOLUME', 'BOOT_VOLUME', 'BOOT_VOLFLAG', 'BALANCE', 'HEADSET_OUTPUT'))   # the loudness words (stock's own)
GETTERS = {'mclGetGaplessMode': 0x5d44b4, 'mclGetJumpFolder': 0x5d4450, 'mclGetGainMode': 0x5d44cc, 'mclGetReplayGain': 0x5d44e4, 'mclGetfilter': 0x5d452c, 'mclGetDsdMode': 0x5d44fc}   # run for real: stock's own reads
CLICK, LIST_TABLE = 0x49ffe8, 0x97c7d0          # stock's playset list click handler (the row item in a0; its name is the row's place), the table from the place to the id
SET_MEM, SET_RG, SET_FILTER, SET_DSD, SET_USB, SET_MODE = 0x49f608, 0x4a0f48, 0x49e95c, 0x4a61f8, 0x4af9a4, 0x49fb58   # the sub-pages' set functions (the window in a0, the choice in a1)
ID = {'gain': 0, 'gapless': 9, 'digital': 12, 'foldercover': 15, 'folderskip': 16}   # the list's row ids
WIN = 0x30000000
LEAVES = {0x742da0: 'memset', 0x70f8d8: 'tk_snprintf', 0x7435b0: 'atoi'}   # (the PLT stubs stock's code calls through)
SETTERS = ('mclSetGainMode', 'mclSetFilter', 'mclSetReplayGain', 'mclSetDsdMode', 'mclSetJumpFolder', 'mclSetLineOut', 'save_stop_player', 'save_start_player', 'set_devicevolume')   # mocked: recorded, their stores modelled
RECORDED = SETTERS + ('write_int_config', 'mclSetGaplessMode', 'mclSetPlayMode', 'notifyPlayMode', 'dmrSendPlayMode')


class PM(Machine):
    """Stock's handlers and set functions run for real, the mcl getters too (they read the words); the setters are mocked and record their arguments, and model what they store (tools/pod.py FUNCTIONS, docs/modules/playset.md
    "The mcl state words and calls"). Every recorded call is preceded by a snapshot of the state: the order of the stores, the saves and the calls."""
    def __init__(self, gapless=0, jump=1, gain=0, lineout=0, mem=2, digital=0, usbvol=1, folder=1, replay=0, filt=3, dsd=0, way=0, volume=20, maxv=100, bootv=30, flag=0, bal=10, headset=0):
        super().__init__()
        for a, n in LEAVES.items(): self.handlers[a] = n
        for a in GETTERS.values(): self.handlers.pop(a)
        self.snap = []
        self.out_way = way
        for a, v in ((MCL_GAPLESS, gapless), (MCL_JUMP, jump), (LINEOUT, lineout), (DIGITAL, digital), (FOLDER, folder)): self.u.mem_write(a, bytes([v]))
        for a, v in ((MCL_GAIN, gain), (MCL_FILTER, filt), (MCL_REPLAY, replay), (MCL_DSD, dsd), (MEM, mem), (USBVOL, usbvol), (VOLUME, volume), (MAXV, maxv), (BOOTV, bootv), (BAL, bal), (HEADSET, headset)): self.setword(a, v)
        self.u.mem_write(BOOTFLAG, bytes([flag]))

    def _hook(self, u, address, size, _):
        name = self.handlers.get(address)
        if name in RECORDED: self.snap.append(self.state())
        if name == 'tk_snprintf':
            a0, a2, a3 = (u.reg_read(r) for r in (UC_MIPS_REG_A0, UC_MIPS_REG_A2, UC_MIPS_REG_A3))
            text = self.read_cstr(a2) % a3
            u.mem_write(a0, text.encode() + b'\0')
            u.reg_write(UC_MIPS_REG_V0, len(text)); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))
            return
        if name not in SETTERS: return super()._hook(u, address, size, _)
        a0, a1 = u.reg_read(UC_MIPS_REG_A0), u.reg_read(UC_MIPS_REG_A1)
        if name == 'mclSetGainMode':
            self.calls.append((name, a0, a1))
            if a1: self.setword(MCL_GAIN, a0)                 # (the word only when the second argument asks)
        elif name == 'mclSetFilter':
            self.calls.append((name, a0)); self.setword(MCL_FILTER, a0)
        elif name == 'mclSetReplayGain':
            self.calls.append((name, a0))
            if a0 < 3: self.setword(MCL_REPLAY, a0)
        elif name == 'mclSetDsdMode':
            self.calls.append((name, a0))
            if a0 < 3: self.setword(MCL_DSD, a0)
        elif name == 'mclSetJumpFolder':
            self.calls.append((name, a0)); self.u.mem_write(MCL_JUMP, bytes([a0 & 0xff]))
        elif name == 'set_devicevolume':
            self.calls.append((name, a0))
        else:
            self.calls.append((name, a0) if name in ('mclSetLineOut', 'save_start_player') else (name,))
        u.reg_write(UC_MIPS_REG_V0, 0); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))

    def byte(self, a): return self.u.mem_read(a, 1)[0]
    def state(self): return (self.byte(MCL_GAPLESS), self.byte(MCL_JUMP), self.word(MCL_GAIN), self.word(MCL_REPLAY), self.word(MCL_FILTER), self.word(MCL_DSD), self.word(MEM), self.word(USBVOL), self.byte(DIGITAL), self.byte(FOLDER))


def seen(m):
    """What reaches stock's state, the player and the driver, in order."""
    return [c for c in m.calls if c[0] in RECORDED]


def stock_click(m, what):
    """Stock's click handler on the row `what`: the item's name is the row's place, which the list's table maps to the id."""
    place = next(p for p in range(16) if m.word(LIST_TABLE + 4 * p) == ID[what])
    node = m.alloc(0x40); m.setword(node + 0x10, m.cstr(str(place)))
    m.call(CLICK, a0=node, count=3000000)
    return m


def stock_set(m, addr, i):
    m.call(addr, a0=WIN, a1=i, count=3000000)
    return m


def same(expect, mo, ms, what):
    """Ours against stock's: the final state, the calls in order, and the state at each of them."""
    expect(mo.state() == ms.state() and seen(mo) == seen(ms) and mo.snap == ms.snap, f'{what}: state {mo.state()} / {ms.state()}, calls {seen(mo)} / {seen(ms)}, at each call {mo.snap} / {ms.snap}')


def toggle_tests(ctx):
    """The four switches and Gain (stock's list cases) against ours, from every state, and the calls spelled out."""
    expect = ctx.expect
    pins = {a for a, _, _ in pod.PLAYSET_PINS}
    expect(all(a in pins for a in (0x4a0164, 0x4a0170, 0x4a018c, 0x4a019c, 0x4a0224, 0x4a0230, 0x4a0258, 0x4a026c, 0x4a0440, 0x4a0450, 0x4a04d0, 0x4a050c, 0x4a0534, 0x4a0544, 0x49ffe8, 0x4a0014)),
           'the click handler, Gapless, Gain, Digital Output, Folder Album Cover and Folder Skip: the reads, the stores, the saves and the setters are pinned')
    expect((D['MEMORY_PLAY'], D['DIGITAL_FLAG'], D['USBVOL_MODE']) == ((0xa05ac4, 'memory_play'), (0xa05ac1, 'digital_flag'), (0xa05aac, 'usbvol_mode')), 'the words are stock\'s (checked against demo\'s dynsym by the build)')
    # the list's table maps the five places we run to the ids
    m = PM()
    expect([next(p for p in range(16) if m.word(LIST_TABLE + 4 * p) == i) for i in (0, 9, 12, 15, 16)] == [0, 9, 11, 14, 15], 'the list\'s table: Gain 0, Gapless 9 (place 9), Digital Output 12 (place 11), Folder Album Cover 15 (place 14), Folder Skip 16 (place 15)')
    for what, fn, key in (('gapless', 'ps_gapless_toggle', 'gapless'), ('folderskip', 'ps_folderskip_toggle', 'jump'), ('digital', 'ps_digital_toggle', 'digital'), ('foldercover', 'ps_foldercover_toggle', 'folder')):
        for st in (0, 1):
            ms = stock_click(PM(**{key: st}), what)
            mo = PM(**{key: st}); r = mo.call(PSYMS[fn], count=2000000)
            expect(r == 1 - st, f'{what} from {st}: answers the new state')
            same(expect, mo, ms, f'{what} from {st}')
    S = 'PLAYSET'
    for fn, key, st, want in (('ps_gapless_toggle', 'gapless', 0, [('write_int_config', 1, S, 'GAPLESS'), ('mclSetGaplessMode', 1)]), ('ps_gapless_toggle', 'gapless', 1, [('write_int_config', 0, S, 'GAPLESS'), ('mclSetGaplessMode', 0)]),
                              ('ps_folderskip_toggle', 'jump', 1, [('write_int_config', 0, S, 'JUMPFOLDER'), ('mclSetJumpFolder', 0)]), ('ps_digital_toggle', 'digital', 0, [('write_int_config', 1, S, 'DIGITALMODE'), ('mclSetLineOut', 1)]),
                              ('ps_digital_toggle', 'digital', 1, [('write_int_config', 0, S, 'DIGITALMODE'), ('mclSetLineOut', 0)]), ('ps_foldercover_toggle', 'folder', 1, [('write_int_config', 0, S, 'FOLDERCOVER')])):
        m = PM(**{key: st}); m.call(PSYMS[fn], count=2000000)
        expect(seen(m) == want, f'{fn} from {st}: {seen(m)}')
    m = PM(digital=0); m.call(PSYMS['ps_digital_toggle'], count=2000000)
    expect(all(s[8] == 1 for s in m.snap) and len(m.snap) == 2, "Digital Output: the byte is stored before the save runs (stock stores it in the delay slot of the save call)")
    for st, want in ((0, 0), (1, 1)):
        expect(PM(gapless=st).call(PSYMS['ps_gapless'], count=200000) == want and PM(jump=st).call(PSYMS['ps_folderskip'], count=200000) == want and PM(digital=st).call(PSYMS['ps_digital'], count=200000) == want
               and PM(folder=st).call(PSYMS['ps_foldercover'], count=200000) == want, f'the states {st} are shown as {want}')
    # Gain: stock's click toggles the mode, the picker's choice is that click when it differs; Line Out refuses it as stock does
    for gain in (0, 1):
        for new in (0, 1):
            ms = PM(gain=gain)
            if new != gain: stock_click(ms, 'gain')
            mo = PM(gain=gain); r = mo.call(PSYMS['ps_gain_set'], a0=new, count=2000000)
            expect(r == 0, f'Gain {gain} -> {new}: answers 0')
            same(expect, mo, ms, f'Gain {gain} -> {new}')
        expect(PM(gain=gain).call(PSYMS['ps_gain'], count=200000) == gain, f'the mode {gain} is shown')
    for gain in (0, 1):
        ms = stock_click(PM(gain=gain, lineout=1), 'gain')
        mo = PM(gain=gain, lineout=1); r = mo.call(PSYMS['ps_gain_set'], a0=1 - gain, count=2000000)
        expect(r == 0xffffffff and not seen(mo) and not seen(ms) and mo.state() == ms.state() and ms.state()[2] == gain, f'Line Out with the mode {gain}: stock does nothing (no save, no driver call), and ours refuses the choice ({seen(mo)}, {seen(ms)})')
    for lo, want in ((0, 0), (1, 1), (2, 1), (0xff, 1)):
        expect(PM(lineout=lo).call(PSYMS['ps_gain_locked'], count=200000) == want, f'the Line Out byte {lo}: Gain locked {want} (stock tests the whole byte, bnez)')
    m = PM(gain=0); m.call(PSYMS['ps_gain_set'], a0=1, count=2000000)
    expect(seen(m) == [('write_int_config', 1, S, 'GAIN'), ('mclSetGainMode', 1, 1)], f'Gain to High: the save, then mclSetGainMode(1, 1) (store = 1: the word changes): {seen(m)}')
    m = PM(gain=1); m.call(PSYMS['ps_gain_set'], a0=0, count=2000000)
    expect(seen(m) == [('write_int_config', 0, S, 'GAIN'), ('mclSetGainMode', 0, 1)] and m.state()[2] == 0, f'Gain to Low: {seen(m)}')
    for bad in (-1, 2, 99):
        m = PM(gain=0)
        expect(m.call(PSYMS['ps_gain_set'], a0=bad & 0xffffffff, count=200000) == 0xffffffff and not seen(m), f'Gain {bad}: refused, nothing written')


def choice_tests(ctx):
    """Memory Playback, ReplayGain, Digital Filter, DSD Output Mode and USB Volume against stock's sub-page set functions (called when the choice differs, as the pages' click handlers do)."""
    expect = ctx.expect
    pins = {a for a, _, _ in pod.PLAYSET_PINS}
    expect(all(a in pins for a in (0x49f73c, 0x49f740, 0x4a106c, 0x4a108c, 0x49ea80, 0x49eaa0, 0x4a632c, 0x4a633c, 0x4a6354, 0x4a6364, 0x4a6374, 0x4a638c, 0x4afac8, 0x4afacc, 0x4afaec)),
           'the five set functions: the stores, the saves and the calls are pinned')
    for mem in range(3):
        for new in range(3):
            ms = PM(mem=mem)
            if new != mem: stock_set(ms, SET_MEM, new)
            mo = PM(mem=mem); r = mo.call(PSYMS['ps_memplay_set'], a0=new, count=2000000)
            expect(r == 0, f'Memory Playback {mem} -> {new}: answers 0')
            same(expect, mo, ms, f'Memory Playback {mem} -> {new}')
        expect(PM(mem=mem).call(PSYMS['ps_memplay'], count=200000) == mem, f'the word {mem} is shown')
    for rg in range(3):
        for new in range(3):
            ms = PM(replay=rg)
            if new != rg: stock_set(ms, SET_RG, new)
            mo = PM(replay=rg); mo.call(PSYMS['ps_replaygain_set'], a0=new, count=2000000)
            same(expect, mo, ms, f'ReplayGain {rg} -> {new}')
        expect(PM(replay=rg).call(PSYMS['ps_replaygain'], count=200000) == rg, f'the word {rg} is shown')
    for f in range(8):
        for new in range(8):
            ms = PM(filt=f)
            if new != f: stock_set(ms, SET_FILTER, new)
            mo = PM(filt=f); mo.call(PSYMS['ps_filter_set'], a0=new, count=2000000)
            same(expect, mo, ms, f'Digital Filter {f} -> {new}')
        expect(PM(filt=f).call(PSYMS['ps_filter'], count=200000) == f, f'the filter {f} is shown')
    for way in (0, 1, 2):
        for d in range(3):
            for new in range(3):
                ms = PM(dsd=d, way=way)
                if new != d: stock_set(ms, SET_DSD, new)
                mo = PM(dsd=d, way=way); mo.call(PSYMS['ps_dsd_set'], a0=new, count=2000000)
                same(expect, mo, ms, f'DSD Output Mode {d} -> {new} on output {way}')
    S = 'SYSSET'
    for way, want in ((2, [('write_int_config', 2, S, 'DSDMODE'), ('save_stop_player',), ('mclSetDsdMode', 2), ('save_start_player', 0)]), (0, [('write_int_config', 2, S, 'DSDMODE'), ('mclSetDsdMode', 2)]),
                      (1, [('write_int_config', 2, S, 'DSDMODE'), ('mclSetDsdMode', 2)])):
        m = PM(dsd=0, way=way); m.call(PSYMS['ps_dsd_set'], a0=2, count=2000000)
        expect(seen(m) == want, f'DSD Native on output {way}: {seen(m)}')
    m = PM(dsd=1, way=2); m.call(PSYMS['ps_dsd_set'], a0=1, count=2000000)
    expect(not seen(m), 'the mode that is set: nothing, not even the stop and restart of the player')
    for u in range(2):
        for new in range(2):
            ms = PM(usbvol=u, volume=37)
            if new != u: stock_set(ms, SET_USB, new)
            mo = PM(usbvol=u, volume=37); mo.call(PSYMS['ps_usbvol_set'], a0=new, count=2000000)
            same(expect, mo, ms, f'USB Volume {u} -> {new}')
    m = PM(usbvol=1, volume=37); m.call(PSYMS['ps_usbvol_set'], a0=0, count=2000000)
    expect(seen(m) == [('set_devicevolume', 37), ('write_int_config', 0, S, 'USBVOLMODE')] and m.state()[7] == 0 and m.snap[0][7] == 0, f'USB Volume Fixed: the word, set_devicevolume(volume), the save: {seen(m)}')
    for v, want in ((0, 0), (1, 1), (2, 1), (-1, 1)):
        expect(PM(usbvol=v).call(PSYMS['ps_usbvol'], count=200000) == want, f'the word {v}: USB Volume {want}')
    for fn, ok, n in (('ps_memplay_set', 2, 3), ('ps_replaygain_set', 2, 3), ('ps_filter_set', 7, 8), ('ps_dsd_set', 2, 3), ('ps_usbvol_set', 1, 2), ('ps_playmode_set', 3, 4)):
        for bad in (-1, n, 99):
            m = PM()
            expect(m.call(PSYMS[fn], a0=bad & 0xffffffff, count=200000) == 0xffffffff and not seen(m) and m.state() == PM().state(), f'{fn}({bad}): refused, nothing written')
    for fn, st, want in (('ps_memplay', 9, 0), ('ps_memplay', -1, 0)):
        m = PM(); m.setword(MEM, st & 0xffffffff)
        expect(m.call(PSYMS[fn], count=200000) == want, f'{fn}: the word {st} shows {want}')
    for fn, addr, bad in (('ps_replaygain', MCL_REPLAY, 7), ('ps_filter', MCL_FILTER, 9), ('ps_dsd', MCL_DSD, 5)):
        m = PM(); m.setword(addr, bad)
        expect(m.call(PSYMS[fn], count=200000) == 0, f'{fn}: a word out of range ({bad}) shows the first choice')


def mode_tests(ctx):
    """Play Mode goes through pod_set_mode: stock's sequence (mclSetPlayMode, notifyPlayMode, dmrSendPlayMode, the save of PLAYMODE) for stock's modes, our Shuffle request for 2."""
    expect = ctx.expect
    for cur in (0, 1, 3):
        for new in (0, 1, 3):
            ms = PM(); ms.mode = cur
            if new != cur: stock_set(ms, SET_MODE, new)
            mo = PM(); mo.mode = cur; r = mo.call(PSYMS['ps_playmode_set'], a0=new, count=4000000)
            expect(r == 0 and seen(mo) == seen(ms), f'Play Mode {cur} -> {new}: the same calls as stock\'s set function ({seen(mo)} / {seen(ms)})')
    S = 'PLAYSET'
    m = PM(); m.mode = 3; m.call(PSYMS['ps_playmode_set'], a0=0, count=4000000)
    expect(seen(m) == [('mclSetPlayMode', 0), ('notifyPlayMode',), ('dmrSendPlayMode', 0), ('write_int_config', 0, S, 'PLAYMODE')], f'Play Mode to List Play: {seen(m)}')
    m = PM(); m.mode = 0; m.call(PSYMS['ps_playmode_set'], a0=2, count=4000000)
    expect(('write_int_config', 2, S, 'PLAYMODE') in seen(m) and ('dmrSendPlayMode', 2) in seen(m), f'Play Mode to Shuffle: our request, shown as 2 ({seen(m)})')
    expect(PM().call(PSYMS['ps_playmode'], count=400000) == PM().mode, 'Play Mode shows the mode as pod_play_mode answers')


def settings_tests(ctx):
    """The Settings rows, the page, its seven pickers, the switches and values, the Line Out grey, the refresh on return, the Library row and the assets."""
    expect, P = ctx.expect, pod_pages
    V, PS, LIB = P.SETTINGS_PAGE, P.PLAYSET_PAGE, P.LIBRARY_PAGE
    labels = [r.label for r in V.rows]
    pi = labels.index('Playback Settings')
    expect(V.rows[pi].action == P.ACT_PAGE and V.rows[pi].arg == P.PLAYSET_PAGE_INDEX and P.PAGES[P.PLAYSET_PAGE_INDEX] is P.PLAYSET_PAGE and P.row_kind(V.rows[pi]) == 'link' and labels[pi - 1] == 'EQ' and labels[pi + 1] == 'Display'
           and 'Continue Playing' not in labels and 'All Playback Settings' not in labels and not any(r.action == P.ACT_HOME and r.arg == P.HOME_PLAYSET for r in V.rows),
           'Settings > Playback Settings: after EQ, opens our page; Continue Playing moved onto it; the row no longer opens stock\'s list')
    pickers = (P.PSMODE_PAGE, P.PSMEM_PAGE, P.PSGAIN_PAGE, P.PSRG_PAGE, P.PSFILTER_PAGE, P.PSDSD_PAGE, P.PSUSB_PAGE)
    expect(P.PAGES[P.PLAYSET_PAGE_INDEX] is PS and all(P.PAGES[i_] is p_ for i_, p_ in zip((P.PSMODE_PAGE_INDEX, P.PSMEM_PAGE_INDEX, P.PSGAIN_PAGE_INDEX, P.PSRG_PAGE_INDEX, P.PSFILTER_PAGE_INDEX, P.PSDSD_PAGE_INDEX, P.PSUSB_PAGE_INDEX), pickers))
           and all(P.PAGES[i_] is p_ for i_, p_ in ((P.PSMAXVOL_PAGE_INDEX, P.PSMAXVOL_PAGE), (P.PSBOOTVOL_PAGE_INDEX, P.PSBOOTVOL_PAGE), (P.PSBAL_PAGE_INDEX, P.PSBAL_PAGE))) and PS.key == 'm1plus_playset' and PS.title == 'Playback'
           and [p.key for p in pickers] == ['m1plus_psmode', 'm1plus_psmem', 'm1plus_psgain', 'm1plus_psrg', 'm1plus_psfilter', 'm1plus_psdsd', 'm1plus_psusb'], 'the page, its seven pickers and the three loudness pages are in the page table at their indexes')
    expect([(r.label, r.action, r.arg) for r in PS.rows] == [('Play Mode', P.ACT_PLAYMODE, P.PSMODE_PAGE_INDEX), ('Gapless', P.ACT_GAPLESS, 0), ('Resume', P.ACT_MEMPLAY, P.PSMEM_PAGE_INDEX), ('Folder Skip', P.ACT_FOLDERSKIP, 0),
                                                           ('Continue Playing', P.ACT_NEXTALBUM, P.NEXTALBUM_PAGE_INDEX), ('Gain', P.ACT_GAIN, P.PSGAIN_PAGE_INDEX), ('Max Volume', P.ACT_MAXVOL, P.PSMAXVOL_PAGE_INDEX), ('Default Volume', P.ACT_BOOTVOL, P.PSBOOTVOL_PAGE_INDEX), ('Channel Balance', P.ACT_BALANCE, P.PSBAL_PAGE_INDEX),
                                                           ('ReplayGain', P.ACT_REPLAYGAIN, P.PSRG_PAGE_INDEX), ('Digital Filter', P.ACT_PAGE, P.PSFILTER_PAGE_INDEX), ('DSD Output Mode', P.ACT_DSD, P.PSDSD_PAGE_INDEX), ('USB Volume', P.ACT_USBVOL, P.PSUSB_PAGE_INDEX), ('Digital Output', P.ACT_DIGITAL, 0)]
           and [P.row_kind(r) for r in PS.rows] == ['value', 'switch', 'value', 'switch', 'value', 'value', 'value', 'value', 'value', 'value', 'link', 'value', 'value', 'switch'], 'the page\'s rows and their kinds')
    pl = [x.text if isinstance(x, P.Hdr) else x.label for x in PS.layout]
    expect(pl == ['Play Mode', 'Gapless', 'Resume', 'Folder Skip', 'Continue Playing', 'Volume', 'Gain', 'Max Volume', 'Default Volume', 'Channel Balance', 'ReplayGain', 'Output', 'Digital Filter', 'DSD Output Mode', 'USB Volume', 'Digital Output'],
           f'three cards: Playback (no header), Volume (Gain, Max Volume, Default Volume, Channel Balance, ReplayGain), Output ({pl})')
    expect([(r.label, r.action, r.arg) for r in P.PSMODE_PAGE.rows] == [(t, P.ACT_PLAYMODESET, i) for i, t in enumerate(('List Play', 'Repeat Track', 'Shuffle', 'Repeat All'))]
           and [(r.label, r.action, r.arg) for r in P.PSMEM_PAGE.rows] == [(t, P.ACT_MEMPLAYSET, i) for i, t in enumerate(('Off', 'Track', 'Location'))]
           and [(r.label, r.action, r.arg) for r in P.PSGAIN_PAGE.rows] == [('Low', P.ACT_GAINSET, 0), ('High', P.ACT_GAINSET, 1)]
           and [(r.label, r.action, r.arg) for r in P.PSRG_PAGE.rows] == [(t, P.ACT_RGSET, i) for i, t in enumerate(('Off', 'Track', 'Album'))]
           and [(r.label, r.arg) for r in P.PSFILTER_PAGE.rows] == list(zip(P.FILTER_VALUES, range(8))) and all(r.action == P.ACT_FILTERSET for r in P.PSFILTER_PAGE.rows) and len(P.FILTER_VALUES) == 8
           and [(r.label, r.action, r.arg) for r in P.PSDSD_PAGE.rows] == [(t, P.ACT_DSDSET, i) for i, t in enumerate(('D2P', 'DOP', 'Native'))]
           and [(r.label, r.action, r.arg) for r in P.PSUSB_PAGE.rows] == [('Fixed', P.ACT_USBVOLSET, 0), ('Variable', P.ACT_USBVOLSET, 1)] and all(P.row_kind(r) == 'check' for p in pickers for r in p.rows),
           'the pickers: stock\'s choices in stock\'s numbers (Play Mode as shown), a check each')
    expect(sorted((P.ACT_PLAYMODE, P.ACT_PLAYMODESET, P.ACT_GAPLESS, P.ACT_MEMPLAY, P.ACT_MEMPLAYSET, P.ACT_FOLDERSKIP, P.ACT_GAIN, P.ACT_GAINSET, P.ACT_REPLAYGAIN, P.ACT_RGSET, P.ACT_FILTERSET,
                                  P.ACT_DSD, P.ACT_DSDSET, P.ACT_DIGITAL, P.ACT_USBVOL, P.ACT_USBVOLSET, P.ACT_FOLDERCOVER, P.ACT_MAXVOL, P.ACT_BOOTVOL, P.ACT_BALANCE, P.ACT_BOOTMEM)) == list(range(114, 135))
           and {P.ACT_GAPLESS, P.ACT_FOLDERSKIP, P.ACT_DIGITAL, P.ACT_FOLDERCOVER, P.ACT_BOOTMEM} <= set(P.SWITCH_ACTIONS) and {P.ACT_PLAYMODE, P.ACT_MEMPLAY, P.ACT_GAIN, P.ACT_REPLAYGAIN, P.ACT_DSD, P.ACT_USBVOL, P.ACT_MAXVOL, P.ACT_BOOTVOL, P.ACT_BALANCE} <= set(P.VALUE_ACTIONS)
           and {P.ACT_PLAYMODESET, P.ACT_MEMPLAYSET, P.ACT_GAINSET, P.ACT_RGSET, P.ACT_FILTERSET, P.ACT_DSDSET, P.ACT_USBVOLSET} <= set(P.CHECK_ACTIONS), 'the actions 114 .. 134 (108, 109, 112 and 113 are the Library rows; 110 and 111 stay retired)')
    expect(not any(r.action == P.ACT_STOCK for r in PS.rows) and not any(r.action == P.ACT_HOME for p in [PS] + list(pickers) for r in p.rows), 'no row of ours opens a stock page')
    li = [x.text if isinstance(x, P.Hdr) else x.label if isinstance(x, P.Row) else None for x in LIB.layout]
    fi = li.index('Folder Album Cover')
    expect(li[fi - 1] == 'Folders' and li[fi + 1] == 'Cover Flow' and next(r for r in LIB.rows if r.label == 'Folder Album Cover').action == P.ACT_FOLDERCOVER == 124
           and P.row_kind(next(r for r in LIB.rows if r.label == 'Folder Album Cover')) == 'switch', 'Settings > Library: the Folder Album Cover switch under a Folders header, before Cover Flow')
    import pod_i18n
    import mod_icons
    keys = ['Playback Settings', 'Play Mode', 'List Play', 'Repeat Track', 'Repeat All', 'Gapless', 'Resume', 'Track', 'Location', 'Folder Skip', 'Low', 'High', 'ReplayGain', 'Digital Filter', 'DSD Output Mode',
            'D2P', 'DOP', 'Native', 'Digital Output', 'USB Volume', 'Fixed', 'Variable', 'Folder Album Cover', 'Max Volume', 'Default Volume', 'Channel Balance', 'Volume Memory', 'Memory'] + list(P.FILTER_VALUES)
    for loc in pod_i18n.LOCALES:
        expect(all(pod_i18n.TEXT[k][loc] for k in keys), f'the page texts have a translation in {loc}')
    expect([mod_icons.CARD_GLYPHS[k] for k in ('Playback Settings', 'Play Mode', 'Gapless', 'Resume', 'Folder Skip', 'Continue Playing', 'Gain', 'Max Volume', 'Default Volume', 'Channel Balance', 'ReplayGain', 'Digital Filter', 'DSD Output Mode', 'USB Volume', 'Digital Output', 'Folder Album Cover', 'Volume Memory')]
           == ['headphones', 'repeat', 'infinity', 'history', 'folder', 'skip-forward', 'gauge', 'volume-2', 'volume-1', 'sliders-horizontal', 'scale', 'waves', 'audio-lines', 'usb', 'cable', 'image', 'memory-stick'], 'the glyphs')

    def page(index, nrows, kinds=('pod_check', 'pod_label'), **state):
        m = PM(**state)
        m.widgets = {n: 0x30000000 + 0x100 * i for i, n in enumerate(['btn_return', 'btn_backtoplayer'] + [f'{k}{i}' for k in ('pod_row',) + tuple(kinds) for i in range(nrows)])}
        row = m.alloc(12)
        m.setword(row, m.cstr('pod_row0')); m.setword(row + 4, P.ACT_PAGE); m.setword(row + 8, index)
        m.call(PSYMS['on_row'], a0=row, count=6000000)
        return m

    def checks(m, n):
        out = []
        for i in range(n):
            v = [c[2] for c in m.calls if c[0] == 'widget_set_visible' and c[1] == m.widgets[f'pod_check{i}']]
            out.append(v[-1] if v else None)
        return out

    def value(m, i):
        got = [(c[0], c[2]) for c in m.calls if c[0] in ('widget_set_text_utf8', 'widget_set_tr_text') and c[1] == m.widgets[f'pod_value{i}']]
        return got, [t for n, t in got if n == 'widget_set_tr_text']

    def sw_images(m, i): return [c[2] for c in m.calls if c[0] == 'image_base_set_image' and c[1] == m.widgets[f'pod_switch{i}']]
    # the pickers: the check follows the state, a tap saves as stock's choice does and the checks follow
    for mem in range(3):
        m = page(pod_pages.PSMEM_PAGE_INDEX, 3, mem=mem)
        expect(('window_open', 'm1plus_psmem') in m.calls and checks(m, 3) == [int(i == mem) for i in range(3)] and not seen(m), f'Memory Playback {mem}: the picker\'s check {checks(m, 3)}, nothing written')
    m = page(pod_pages.PSMEM_PAGE_INDEX, 3, mem=2)
    m.click('pod_row0')
    expect(m.word(MEM) == 0 and seen(m) == [('write_int_config', 0, 'PLAYSET', 'MEMORYPLAY')] and checks(m, 3) == [1, 0, 0], 'a tap on Off: the word, the save, the check follows')
    m.calls = []; m.click('pod_row0')
    expect(not seen(m), 'a tap on the chosen row writes nothing')
    for rg in range(3):
        m = page(pod_pages.PSRG_PAGE_INDEX, 3, replay=rg)
        expect(checks(m, 3) == [int(i == rg) for i in range(3)], f'ReplayGain {rg}: the check')
    m = page(pod_pages.PSRG_PAGE_INDEX, 3, replay=0); m.click('pod_row2')
    expect(seen(m) == [('mclSetReplayGain', 2), ('write_int_config', 2, 'PLAYSET', 'REPLAYGAIN')] and checks(m, 3) == [0, 0, 1], 'ReplayGain Album: stock\'s set, then the save')
    for f in (0, 3, 7):
        m = page(pod_pages.PSFILTER_PAGE_INDEX, 8, filt=f)
        expect(checks(m, 8) == [int(i == f) for i in range(8)], f'Digital Filter {f}: the check')
    m = page(pod_pages.PSFILTER_PAGE_INDEX, 8, filt=3); m.click('pod_row7')
    expect(seen(m) == [('mclSetFilter', 7), ('write_int_config', 7, 'PLAYSET', 'FILTER')] and checks(m, 8) == [0] * 7 + [1], 'Digital Filter: mclSetFilter, then the save')
    m = page(pod_pages.PSDSD_PAGE_INDEX, 3, dsd=0, way=2); m.click('pod_row1')
    expect(seen(m) == [('write_int_config', 1, 'SYSSET', 'DSDMODE'), ('save_stop_player',), ('mclSetDsdMode', 1), ('save_start_player', 0)] and checks(m, 3) == [0, 1, 0], 'DSD DOP on USB audio: stop, set, restart')
    m = page(pod_pages.PSUSB_PAGE_INDEX, 2, usbvol=1, volume=50); m.click('pod_row0')
    expect(seen(m) == [('set_devicevolume', 50), ('write_int_config', 0, 'SYSSET', 'USBVOLMODE')] and checks(m, 2) == [1, 0], 'USB Volume Fixed: set_devicevolume, the save')
    for mode in (0, 1, 3):
        m = page(pod_pages.PSMODE_PAGE_INDEX, 4); m.mode = mode; m.calls = []; m.fire(O['EVT_WINDOW_TO_FG'])
        expect(checks(m, 4)[mode] == 1 and sum(checks(m, 4)) == 1, f'Play Mode {mode}: the check follows the mode shown')
    m = page(pod_pages.PSMODE_PAGE_INDEX, 4); m.mode = 3; m.click('pod_row0')
    expect(('write_int_config', 0, 'PLAYSET', 'PLAYMODE') in seen(m) and checks(m, 4) == [1, 0, 0, 0], 'a tap on List Play: through pod_set_mode, the check follows')
    gm = page(pod_pages.PSGAIN_PAGE_INDEX, 2, gain=1)
    expect(checks(gm, 2) == [0, 1], 'Gain High: the picker\'s check')
    gm.click('pod_row0')
    expect(seen(gm) == [('write_int_config', 0, 'PLAYSET', 'GAIN'), ('mclSetGainMode', 0, 1)] and checks(gm, 2) == [1, 0], 'a tap on Low: the save, mclSetGainMode(0, 1), the check follows')
    # the page: values, switches, the Gain row's grey, the picker rows
    PK = ('pod_value', 'pod_label', 'pod_switch')
    rows = 14
    pm = page(P.PLAYSET_PAGE_INDEX, rows, PK, gapless=1, jump=0, gain=1, replay=2, dsd=2, usbvol=0, mem=1, digital=1, maxv=80, bootv=35, bal=7)
    pm.mode = 1
    pm.calls = []; pm.fire(O['EVT_WINDOW_TO_FG'])
    vals = {i: value(pm, i)[1] for i in (0, 2, 4, 5, 9, 11, 12)}
    expect(vals == {0: ['Repeat Track'], 2: ['Track'], 4: ['Off'], 5: ['High'], 9: ['Album'], 11: ['Native'], 12: ['Fixed']}, f'the value rows show stock\'s state ({vals})')
    nums = {i: [t for _, t in value(pm, i)[0]][-1:] for i in (6, 7, 8)}
    expect(nums == {6: ['80'], 7: ['35'], 8: ['L3']}, f'the loudness rows: Max Volume the number, Default Volume the number, Channel Balance as stock\'s label writes it ({nums})')
    expect([sw_images(pm, i)[-1] for i in (1, 3, 13)] == ['sset_on', 'sset_off', 'sset_on'], 'the switches show Gapless on, Folder Skip off, Digital Output on')
    expect(not seen(pm), 'nothing is written when the page opens or comes back to the front')
    for lo, dim in ((0, 0), (1, 1)):
        m = page(P.PLAYSET_PAGE_INDEX, rows, PK, lineout=lo)
        op = [c[2] for c in m.calls if c[0] == 'widget_set_opacity' and c[1] == m.widgets['pod_row5']]
        se = [c[2] for c in m.calls if c[0] == 'widget_set_sensitive' and c[1] == m.widgets['pod_row5']]
        expect(op[-1:] == [153 if dim else 255] and se[-1:] == [0 if dim else 1], f'Line Out {lo}: the Gain row is {"dimmed and insensitive" if dim else "plain and sensitive"} ({op}, {se})')
        expect(not [c for c in m.calls if c[0] in ('widget_set_opacity', 'widget_set_sensitive') and c[1] != m.widgets['pod_row5']], f'Line Out {lo}: only the Gain row is touched')
    m.u.mem_write(LINEOUT, b'\0'); m.calls = []; m.fire(O['EVT_WINDOW_TO_FG'])
    expect([c[2] for c in m.calls if c[0] == 'widget_set_sensitive' and c[1] == m.widgets['pod_row5']] == [1], 'back in front after Line Out went off (the pull-down\'s tile): the Gain row is live again')
    m = page(P.PLAYSET_PAGE_INDEX, rows, PK, lineout=1)
    m.u.mem_write(LINEOUT, b'\0'); m.calls = []; m.fire(O['EVT_WINDOW_TO_FG'])
    expect([c[2] for c in m.calls if c[0] == 'widget_set_opacity' and c[1] == m.widgets['pod_row5']] == [255], 'and the grey goes')
    # taps: the switches toggle through ours, the value rows open their pickers, Digital Filter is a link, Continue Playing opens its own picker
    m = page(P.PLAYSET_PAGE_INDEX, rows, PK, gapless=0, jump=1, digital=0)
    m.click('pod_row1')
    expect(seen(m) == [('write_int_config', 1, 'PLAYSET', 'GAPLESS'), ('mclSetGaplessMode', 1)] and sw_images(m, 1)[-1] == 'sset_on', 'a tap on Gapless: stock\'s save and setter, the switch follows')
    m.calls = []; m.click('pod_row3')
    expect(seen(m) == [('write_int_config', 0, 'PLAYSET', 'JUMPFOLDER'), ('mclSetJumpFolder', 0)] and sw_images(m, 3)[-1] == 'sset_off', 'a tap on Folder Skip')
    m.calls = []; m.click('pod_row13')
    expect(seen(m) == [('write_int_config', 1, 'PLAYSET', 'DIGITALMODE'), ('mclSetLineOut', 1)] and sw_images(m, 13)[-1] == 'sset_on', 'a tap on Digital Output')
    for row, target in ((0, 'm1plus_psmode'), (2, 'm1plus_psmem'), (4, 'm1plus_nextalbum'), (5, 'm1plus_psgain'), (6, 'm1plus_psmaxvol'), (7, 'm1plus_psbootvol'), (8, 'm1plus_psbal'), (9, 'm1plus_psrg'), (10, 'm1plus_psfilter'), (11, 'm1plus_psdsd'), (12, 'm1plus_psusb')):
        m = page(P.PLAYSET_PAGE_INDEX, rows, PK); m.calls = []; m.click(f'pod_row{row}')
        expect([c[1] for c in m.calls if c[0] == 'window_open'] == [target] and 'navigator_to' not in m.names() and not seen(m), f'row {row} opens {target} and nothing else')
    # the Library page's switch, and the Folders page's reading of the byte
    ll = [r.label for r in LIB.rows]
    fi = ll.index('Folder Album Cover')
    m = page(P.LIBRARY_PAGE_INDEX, len(LIB.rows), PK, folder=1)
    expect(sw_images(m, fi)[-1] == 'sset_on', 'Library: the Folder Album Cover switch shows the byte')
    m.calls = []; m.click(f'pod_row{fi}')
    expect(m.byte(FOLDER) == 0 and seen(m) == [('write_int_config', 0, 'PLAYSET', 'FOLDERCOVER')] and sw_images(m, fi)[-1] == 'sset_off', 'a tap: the byte, the save, the switch')
    m.u.mem_write(FOLDER, b'\1'); m.calls = []; m.fire(O['EVT_WINDOW_TO_FG'])
    expect(sw_images(m, fi)[-1] == 'sset_on', 'back in front: the switch follows the byte')
    # the assets
    raw = os.path.join(WORK, 'rootfs/release/assets/default/raw/ui')
    trees = {k: awtk_ui.parse(open(os.path.join(raw, k + '.bin'), 'rb').read()) for k in ['m1plus_playset', 'm1plus_settings', 'm1plus_library'] + [p.key for p in pickers]}
    pt = trees['m1plus_playset']
    expect([pt.find(f'pod_row{i}').find('pod_icon').get('image') for i in range(rows)] == ['pod_ci_repeat', 'pod_ci_infinity', 'pod_ci_history', 'pod_ci_folder', 'pod_ci_skip_forward', 'pod_ci_gauge', 'pod_ci_volume_2', 'pod_ci_volume_1', 'pod_ci_sliders_horizontal', 'pod_ci_scale', 'pod_ci_waves',
                                                                                              'pod_ci_audio_lines', 'pod_ci_usb', 'pod_ci_cable'] and pt.find('label_title').get('tr_text') == 'Playback',
           'the page asset: fourteen glyphs and the title')
    expect([pt.find(f'pod_label{i}').get('tr_text') for i in range(rows)] == ['Play Mode', 'Gapless', 'Resume', 'Folder Skip', 'Continue Playing', 'Gain', 'Max Volume', 'Default Volume', 'Channel Balance', 'ReplayGain', 'Digital Filter', 'DSD Output Mode', 'USB Volume', 'Digital Output'],
           'the row labels')
    for p in pickers:
        t = trees[p.key]
        expect(all(t.find(f'pod_check{i}').get('visible') == 'false' and t.find(f'pod_check{i}').get('sensitive') == 'false' for i in range(len(p.rows))) and t.find('label_title').get('tr_text') == p.title
               and [t.find(f'pod_label{i}').get('tr_text') for i in range(len(p.rows))] == [pod_i18n.key_for(r.label) for r in p.rows], f'the {p.title} picker asset: a hidden insensitive check each, the labels translated (Album is stock\'s own key)')


# ---- the three loudness pages: stock's own handlers, bound to our widgets by name -----------------------------------------------------------------------------------------------------------------------------
# The payload binds stock's refresh / slider / button handlers (patch/playset.c ps_vol_opened); these tests open each page, take the handler the payload bound (m.bound) and run it under the emulator on every
# value, and compare what it did, call by call and with the state at each call, with a model written from stock's disassembly (docs/modules/playset.md "Loudness pages"), not from the code that runs.
LOUD = ('write_int_config', 'set_devicevolume', 'reset_poweroptions_timer')
P_IDX = pod_pages.PLAYSET_PAGE_INDEX


def page(index, nrows, kinds=('pod_check', 'pod_label'), **state):
    """A machine with the page opened as its Settings row opens it (the widgets named as the asset names them)."""
    m = PM(**state)
    m.widgets = {n: 0x30000000 + 0x100 * i for i, n in enumerate(['btn_return', 'btn_backtoplayer'] + [f'{k}{i}' for k in ('pod_row',) + tuple(kinds) for i in range(nrows)])}
    row = m.alloc(12)
    m.setword(row, m.cstr('pod_row0')); m.setword(row + 4, pod_pages.ACT_PAGE); m.setword(row + 8, index)
    m.call(PSYMS['on_row'], a0=row, count=6000000)
    return m
EVT_CHANGING, EVT_CLICK_ = 0x11d, 0x10c
STRCPY, SLIDER_SET, SET_ENABLE = 0x743570, 0x6316dc, 0x669320   # leaves of stock's refresh (the PLT stub of strcpy, slider_set_value, widget_set_enable)
H = {n: D[n][0] for n in ('VOL_REFRESH', 'VOL_SLIDER', 'VOL_DEC', 'VOL_ADD', 'BOOT_REFRESH', 'BOOT_SLIDER', 'BOOT_DEC', 'BOOT_ADD', 'BAL_REFRESH', 'BAL_SLIDER', 'BAL_DEC', 'BAL_ADD')}
PAGE_OF = {'max': pod_pages.PSMAXVOL_PAGE_INDEX, 'boot': pod_pages.PSBOOTVOL_PAGE_INDEX, 'bal': pod_pages.PSBAL_PAGE_INDEX}
WIDGETS = {'max': ('label_vol', 'vol_slider'), 'boot': ('label_vol', 'vol_slider'), 'bal': ('label_balance', 'slider_balance')}
SWITCH_STOCK = 0x49d328   # stock's Volume Memory click (the window in a0)


class LM(PM):
    """Stock's loudness handlers run for real (state: max, volume, the default volume, its byte, the balance, headset_output); the leaves of its refresh are recorded, set_devicevolume and the save are PM's."""
    def __init__(self, **kw):
        super().__init__(**kw)
        for a, n in ((STRCPY, 'strcpy'), (SLIDER_SET, 'slider_set_value'), (SET_ENABLE, 'widget_set_enable'), (0x742ab0, 'tk_snprintf')): self.handlers[a] = n   # (stock's refresh calls libc's snprintf through its stub)

    def state(self): return (self.word(MAXV), self.word(VOLUME), self.word(BOOTV), self.byte(BOOTFLAG), self.word(BAL), self.word(HEADSET))

    def _hook(self, u, address, size, _):
        name = self.handlers.get(address)
        if name in ('strcpy', 'slider_set_value', 'widget_set_enable'):
            a0, a1, a2, a3 = (u.reg_read(r) for r in (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3))
            if name == 'strcpy': u.mem_write(a0, self.read_cstr(a1).encode() + b'\0')
            elif name == 'slider_set_value': self.calls.append((name, a0, struct.unpack('<d', struct.pack('<II', a2, a3))[0]))
            else: self.calls.append((name, a0, a1))
            u.reg_write(UC_MIPS_REG_V0, 0); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))
            return
        super()._hook(u, address, size, _)


def loud_calls(m):
    """What reaches stock's state and the device, in order: each save and set_devicevolume with the (max, volume, ..) state at the call (the timer has none)."""
    out, snaps = [], iter(m.snap)
    for c in m.calls:
        if c[0] not in LOUD: continue
        out.append(c + (next(snaps),) if c[0] != 'reset_poweroptions_timer' else c)
    return out


def lc2(m, which='max'):
    """loud_calls with the state cut to what the page is about: (max, volume), (balance, volume) or (default volume, byte)."""
    return norm(loud_calls(m), {'max': lambda st: st[:2], 'bal': lambda st: (st[4], st[1]), 'boot': lambda st: (st[2], st[3])}[which])


def loud_page(which, **state):
    """A machine with the page's stock widgets, the page opened as its row opens it (our payload binds stock's handlers), and the bound handlers."""
    m = LM(**state)
    label, slider = WIDGETS[which]
    for n in ('btn_return', 'btn_backtoplayer', 'pod_vsval', 'pod_vsctl', label, slider, 'btn_dec', 'btn_add') + (('pod_vsnum',) if which != 'bal' else ()): m.widget(n)
    if which == 'boot':
        for n in ('pod_row0', 'pod_switch0', 'pod_label0', 'bootvol_view', 'img_switchmemory'): m.widget(n)
    row = m.alloc(12)
    m.setword(row, m.cstr('pod_row0')); m.setword(row + 4, pod_pages.ACT_PAGE); m.setword(row + 8, PAGE_OF[which])
    m.call(PSYMS['on_row'], a0=row, count=6000000)
    return m


def event(m, s, value):
    e = m.alloc(0x30); m.u.mem_write(e, bytes(0x30)); m.setword(e + 0x10, s)   # the event: its target
    m.props[(s, 'value')] = value
    return e


def run(m, which, what, v=0):
    """Run the handler the payload bound: 'slider' (value v), 'dec' or 'add'. The calls and the snapshots are the run's own."""
    label, slider = WIDGETS[which]
    s = m.widgets[slider]
    if what == 'slider': fn, ctx = m.bound[(s, EVT_CHANGING)]; e = event(m, s, v)
    else: fn, ctx = m.bound[(m.widgets['btn_dec' if what == 'dec' else 'btn_add'], EVT_CLICK_)]; e = 0
    m.calls, m.snap = [], []
    m.call(fn, a0=ctx, a1=e, count=3000000)
    return m


def spec_max(what, v, mx, vol, hs):
    """Stock's Max Volume handlers (0x49f24c slider, 0x49f16c dec, 0x49f0f4 add), from the disassembly: (calls with the state at each, final max, final volume)."""
    calls = []
    def save(key, val): calls.append(('write_int_config', val, 'PLAYSET', key, (mx, vol)))
    if what == 'add':
        if mx < 100: mx += 1; save('MAXVOLUME', mx)
        return calls, mx, vol
    if what == 'dec':
        if mx <= 0: return calls, mx, vol
        mx -= 1
        if mx < vol:
            vol = mx
            if hs != 2: calls.append(('set_devicevolume', vol, (mx, vol)))
            save('VOLUME', vol)
        save('MAXVOLUME', mx)
        return calls, mx, vol
    if v > 100: return calls, mx, vol
    mx = v
    if v < vol:
        vol = v
        if hs != 2: calls.append(('set_devicevolume', vol, (mx, vol)))
        save('VOLUME', vol)
    save('MAXVOLUME', mx)
    calls.append(('reset_poweroptions_timer', 1, 1, 1))
    return calls, mx, vol


def spec_bal(what, v, bal, vol, hs):
    """Stock's Channel Balance handlers (0x49cd78 slider, 0x49ce4c dec, 0x49ccd8 add): the store and the save, then set_devicevolume(volume) unless headset_output is 2; the slider also resets the power timers."""
    calls = []
    if what == 'add': nb = bal + 1 if bal < 20 else None
    elif what == 'dec': nb = bal - 1 if bal > 0 else None
    else: nb = v if v <= 20 else None
    if nb is None: return calls, bal, vol
    calls.append(('write_int_config', nb, 'PLAYSET', 'BALANCE', (nb, vol)))
    if hs != 2: calls.append(('set_devicevolume', vol, (nb, vol)))
    if what == 'slider': calls.append(('reset_poweroptions_timer', 1, 1, 1))
    return calls, nb, vol


def spec_boot(what, v, boot, flag):
    """Stock's Default Volume handlers (0x49d418 slider, 0x49d39c dec, 0x49d4c8 add): the store (in the save's delay slot) and the save; never a volume call."""
    calls = []
    if what == 'add': nb = boot + 1 if boot < 100 else None
    elif what == 'dec': nb = boot - 1 if boot > 0 else None
    else: nb = v if v <= 100 else None
    if nb is None: return calls, boot
    calls.append(('write_int_config', nb, 'PLAYSET', 'BOOTVOLUME', (nb, flag)))
    if what == 'slider': calls.append(('reset_poweroptions_timer', 1, 1, 1))
    return calls, nb


def norm(calls, keep):
    """The recorded calls with the state cut to the words that matter: keep(state) -> a tuple."""
    return [c[:-1] + (keep(c[-1]),) if c[0] != 'reset_poweroptions_timer' else c for c in calls]


def pin_tests(ctx):
    """The entries, the events and every store, save and call of stock's three loudness pages are pinned; the payload binds exactly them."""
    expect = ctx.expect
    pins = {a: w for a, w, _ in pod.PLAYSET_PINS}
    expect(all(a in pins for a in H.values()), 'the twelve entries of stock\'s refresh, slider, dec and add handlers are pinned')
    expect(all(pins.get(a) == w for a, w in ((0x49ef68, 0x2405011d), (0x49ef6c, 0x24c6f24c), (0x49efb4, 0x24c6f16c), (0x49efe0, 0x24c6f0f4), (0x49ee68, 0x2405010c), (0x49cb08, 0x2405011d), (0x49cb0c, 0x24c6cd78), (0x49cb54, 0x24c6ce4c), (0x49cb80, 0x24c6ccd8),
                                              (0x49ca08, 0x2405010c), (0x49d0dc, 0x2405011d), (0x49d0e0, 0x24c6d418), (0x49d128, 0x24c6d39c), (0x49d0b0, 0x24c6d4c8), (0x49cfd4, 0x2405010c))),
           'stock\'s page inits bind the slider on 0x11d (EVT_VALUE_CHANGING only) and the two buttons on 0x10c, to the handlers we run')
    expect(O['EVT_VALUE_CHANGING'] == EVT_CHANGING and O['EVT_CLICK'] == EVT_CLICK_, 'the event numbers')
    expect(all(a in pins for a in (0x49f13c, 0x49f1d8, 0x49f1f4, 0x49f210, 0x49f2dc, 0x49f2f8, 0x49f314, 0x49f340, 0x49cd20, 0x49cd5c, 0x49ce94, 0x49ced0, 0x49cddc, 0x49ce18, 0x49ce30, 0x49d3e4, 0x49d47c, 0x49d4ac, 0x49d510, 0x49d368, 0x49d36c)),
           'every save, the device call and the timer reset of the three pages are pinned')
    expect((D['MAX_VOLUME'], D['BOOT_VOLUME'], D['BOOT_VOLFLAG'], D['BALANCE'], D['HEADSET_OUTPUT']) == ((0x97cb08, 'max_volume'), (0x97cb04, 'boot_volume'), (0xa05ac8, 'boot_volflag'), (0x97cafc, 'balance'), (0xa05a10, 'headset_output')),
           'the words are stock\'s (checked against demo\'s dynsym by the build)')
    for which, (r, s, d, a) in (('max', ('VOL_REFRESH', 'VOL_SLIDER', 'VOL_DEC', 'VOL_ADD')), ('boot', ('BOOT_REFRESH', 'BOOT_SLIDER', 'BOOT_DEC', 'BOOT_ADD')), ('bal', ('BAL_REFRESH', 'BAL_SLIDER', 'BAL_DEC', 'BAL_ADD'))):
        m = loud_page(which)
        label, slider = WIDGETS[which]
        sw = m.widgets[slider]
        ours = {'max': PSYMS['ps_num_max'], 'boot': PSYMS['ps_num_boot']}.get(which)
        got = [c[1:] for c in m.calls if c[0] == 'widget_on' and c[1] in (sw, m.widgets['btn_dec'], m.widgets['btn_add'])]
        win = m.window
        stock = [c for c in got if c[2] != ours]
        expect(sorted(stock) == sorted([(sw, EVT_CHANGING, H[s], win), (m.widgets['btn_dec'], EVT_CLICK_, H[d], win), (m.widgets['btn_add'], EVT_CLICK_, H[a], win)]) and len(stock) == 3,
               f'{which}: stock\'s slider (0x11d only), dec and add handlers bound to our widgets with the window as their context ({got})')
        mine = [c for c in got if c[2] == ours]
        expect(len(got) == (6 if ours else 3) and len(mine) == (3 if ours else 0) and sorted(c[:2] for c in mine) == sorted([(sw, EVT_CHANGING), (m.widgets['btn_dec'], EVT_CLICK_), (m.widgets['btn_add'], EVT_CLICK_)] if ours else []),
               f'{which}: our number handler on the same three events, and only on Max Volume and Default Volume ({got})')
        # the emitter keeps its handlers newest first and dispatches from the head (emitter_on_with_tag 0x6f45ac, emitter_dispatch 0x6f4458, read from stock): ours is bound first so that it runs after stock's
        expect(all(got.index(next(c for c in mine if c[:2] == st[:2])) < got.index(st) for st in stock) if ours else True, f'{which}: our handler is bound before stock\'s on each widget, so it runs after (the emitter dispatches the newest first)')
        expect(not [c for c in m.calls if c[0] in LOUD], f'{which}: opening the page saves and sends nothing')
        i = next(k for k, c in enumerate(m.calls) if c[0] == 'slider_set_value')
        expect(all(c[0] != 'widget_on' or c[1] not in (sw, m.widgets['btn_dec'], m.widgets['btn_add']) for c in m.calls[:i]), f'{which}: stock\'s refresh runs before the handlers are bound (setting the slider is not a change to save)')
    m = LM()
    m.call(PSYMS['ps_vol_opened'], a0=WIN, a1=0, count=2000000); m.call(PSYMS['ps_vol_refresh'], a0=0, a1=0, count=2000000); m.call(PSYMS['ps_vol_opened'], a0=WIN, a1=7, count=2000000)
    expect(not [c for c in m.calls if c[0] in ('widget_on', 'slider_set_value', 'write_int_config')], 'a page without stock\'s widgets, no window, an unknown page: nothing bound, nothing called')


def maxvol_tests(ctx):
    """Max Volume: stock's slider, dec and add handlers, on every target 0 .. 100 from starts with the volume above, at and below the new max, on each output; and the properties we need on top."""
    expect = ctx.expect
    starts = [(100, 20), (100, 100), (60, 50), (60, 60), (50, 0), (30, 30), (0, 0), (100, 1), (75, 74), (40, 60)]   # (max, volume); the last has the volume above the max (the volume keys cannot do that)
    bad = []; n = 0
    for hs in (0, 1, 2, 3):
        m = loud_page('max', headset=hs)
        for mx, vol in starts:
            for what, targets in (('slider', range(0, 103)), ('dec', (0,)), ('add', (0,))):
                for v in targets:
                    m.setword(MAXV, mx); m.setword(VOLUME, vol); m.setword(HEADSET, hs)
                    run(m, 'max', what, v)
                    want, wm, wv = spec_max(what, v, mx, vol, hs)
                    got = norm(loud_calls(m), lambda st: st[:2]); n += 1
                    if got != want or (m.word(MAXV), m.word(VOLUME)) != (wm, wv): bad.append((hs, mx, vol, what, v, got, want, (m.word(MAXV), m.word(VOLUME))))
    expect(not bad, f'Max Volume: {n} runs (every target 0 .. 102, dec and add, 10 starts, 4 outputs): stock\'s handlers do what the model says, store for store, call for call, state at each call ({bad[:2]})')
    # the properties of ours on top
    broke = []
    for hs in (0, 1, 2, 3):
        m = loud_page('max', headset=hs)
        for mx, vol in starts:
            for what, targets in (('slider', range(0, 101)), ('dec', (0,)), ('add', (0,))):
                for v in targets:
                    m.setword(MAXV, mx); m.setword(VOLUME, vol); m.setword(HEADSET, hs)
                    run(m, 'max', what, v)
                    nm, nv = m.word(MAXV), m.word(VOLUME)
                    devs = [c[1] for c in m.calls if c[0] == 'set_devicevolume']
                    saves = [c[3] for c in m.calls if c[0] == 'write_int_config']
                    ok = nv <= vol and (vol > mx or nv <= nm) and all(d <= nm for d in devs) and (hs != 2 or not devs) and (not devs or hs != 2) and saves in ([], ['MAXVOLUME'], ['VOLUME', 'MAXVOLUME']) and (what != 'add' or (nv == vol and not devs))
                    if not ok: broke.append((hs, mx, vol, what, v, nm, nv, devs, saves))
    expect(not broke, f'Max Volume, any change: the volume never goes up, it is at most the max when it was, set_devicevolume never gets a level above the new max and is never called on Bluetooth, VOLUME is saved before MAXVOLUME, add never touches the volume ({broke[:2]})')
    m = loud_page('max', headset=0); m.setword(MAXV, 80); m.setword(VOLUME, 50)
    run(m, 'max', 'slider', 30)
    expect(lc2(m) == [('set_devicevolume', 30, (30, 30)), ('write_int_config', 30, 'PLAYSET', 'VOLUME', (30, 30)), ('write_int_config', 30, 'PLAYSET', 'MAXVOLUME', (30, 30)), ('reset_poweroptions_timer', 1, 1, 1)],
           f'a max of 30 over a volume of 50 on headphones: the volume is lowered to 30 at once, the device is told 30, VOLUME then MAXVOLUME are saved ({lc2(m)})')
    run(m, 'max', 'slider', 90)
    expect(lc2(m) == [('write_int_config', 90, 'PLAYSET', 'MAXVOLUME', (90, 30)), ('reset_poweroptions_timer', 1, 1, 1)] and m.word(VOLUME) == 30, 'raising the max saves it and leaves the volume where it is')
    m = loud_page('max', headset=2); m.setword(MAXV, 80); m.setword(VOLUME, 50)
    run(m, 'max', 'slider', 30)
    expect(lc2(m) == [('write_int_config', 30, 'PLAYSET', 'VOLUME', (30, 30)), ('write_int_config', 30, 'PLAYSET', 'MAXVOLUME', (30, 30)), ('reset_poweroptions_timer', 1, 1, 1)],
           'Bluetooth (headset_output 2): the volume word is lowered and saved, the device is not called')
    m = loud_page('max'); m.setword(MAXV, 50); m.setword(VOLUME, 50)
    run(m, 'max', 'slider', 0)
    expect(m.word(MAXV) == 0 and m.word(VOLUME) == 0 and ('set_devicevolume', 0, (0, 0)) in lc2(m), 'a max of 0 is legal: the volume goes to 0')
    # stale values: the handlers read volume and max when they run; the page shows only the max, and writes only what it was given
    m = loud_page('max'); m.setword(MAXV, 80); m.setword(VOLUME, 20)
    m.setword(VOLUME, 70)   # a volume key (the volume dialog, under the page) changed it
    run(m, 'max', 'slider', 60)
    expect(m.word(VOLUME) == 60 and ('set_devicevolume', 60, (60, 60)) in lc2(m), 'the volume changed by the keys while the page is up: the next change compares with the volume as it is now, not as it was when the page opened')
    m = loud_page('max'); lab, sl = m.widgets['label_vol'], m.widgets['vol_slider']
    expect(('widget_set_text_utf8', lab, 'VOL: 100') in m.calls and ('slider_set_value', sl, 100.0) in m.calls, 'the page opens with stock\'s refresh: label_vol "VOL: 100" and the slider at the max')
    num = m.widgets['pod_vsnum']
    expect(('widget_set_text_utf8', num, '100') in m.calls, 'and our label shows the number alone')
    m.setword(MAXV, 55); m.calls = []; m.fire(O['EVT_WINDOW_TO_FG'])
    expect(('widget_set_text_utf8', lab, 'VOL: 55') in m.calls and ('slider_set_value', sl, 55.0) in m.calls and not [c for c in m.calls if c[0] in LOUD], 'back in front: the label and the slider follow the word, nothing is written')
    expect(('widget_set_text_utf8', num, '55') in m.calls, 'back in front: our label shows 55')
    m.setword(VOLUME, 10); m.calls = []; m.fire(O['EVT_WINDOW_TO_FG'])
    expect(not [c for c in m.calls if c[0] in LOUD] and m.word(VOLUME) == 10, 'a volume key press changes nothing the page shows or writes: the volume is not on the page')


def bootvol_tests(ctx):
    """Default Volume: Volume Memory (stock's switch repeated store for store) and stock's slider, dec and add handlers, on every value 0 .. 100 with the switch both ways; nothing is applied live."""
    expect = ctx.expect
    bad = []; n = 0
    for flag in (0, 1):
        m = loud_page('boot', flag=flag)
        for boot in (0, 1, 30, 99, 100):
            for what, targets in (('slider', range(0, 103)), ('dec', (0,)), ('add', (0,))):
                for v in targets:
                    m.setword(BOOTV, boot); m.u.mem_write(BOOTFLAG, bytes([flag])); m.setword(VOLUME, 37); m.setword(MAXV, 80)
                    run(m, 'boot', what, v)
                    want, wb = spec_boot(what, v, boot, flag)
                    got = norm(loud_calls(m), lambda st: (st[2], st[3])); n += 1
                    if got != want or m.word(BOOTV) != wb or m.word(VOLUME) != 37 or m.word(MAXV) != 80 or m.byte(BOOTFLAG) != flag or [c for c in m.calls if c[0] == 'set_devicevolume']:
                        bad.append((flag, boot, what, v, got, want, m.word(BOOTV)))
    expect(not bad, f'Default Volume: {n} runs (every value 0 .. 102, dec and add, 5 starts, the switch both ways): stock\'s handlers store and save as the model says, and touch neither the volume, the max nor the device ({bad[:2]})')
    # Volume Memory: stock's click against ours, from both states
    for flag in (0, 1):
        ms = loud_page('boot', flag=flag); ms.calls, ms.snap = [], []
        ms.call(SWITCH_STOCK, a0=WIN, count=3000000)
        mo = loud_page('boot', flag=flag); mo.calls, mo.snap = [], []
        r = mo.call(PSYMS['ps_bootmem_toggle'], count=2000000)
        expect(r == 1 - flag and mo.state() == ms.state() and loud_calls(mo) == loud_calls(ms) == [('write_int_config', 1 - flag, 'PLAYSET', 'BOOTVOLFLAG', (100, 20, 30, 1 - flag, 10, 0))] and mo.byte(BOOTFLAG) == 1 - flag,
               f'Volume Memory from {flag}: the byte is stored as the save starts and saved, the same as stock\'s click ({loud_calls(mo)} / {loud_calls(ms)})')
        expect(PM(flag=flag).call(PSYMS['ps_bootmem'], count=200000) == flag, f'the byte {flag} is shown')
    # the page: the cards follow the byte (dimmed and inert while Volume Memory is on), the switch row follows it, the refresh on return
    def dim(m):
        out = {}
        for n in ('pod_vsval', 'pod_vsctl'):
            h = m.widgets[n]
            out[n] = ([c[2] for c in m.calls if c[0] == 'widget_set_opacity' and c[1] == h][-1:], [c[2] for c in m.calls if c[0] == 'widget_set_sensitive' and c[1] == h][-1:])
        return out
    m = loud_page('boot', flag=0)
    expect(dim(m) == {'pod_vsval': ([255], [1]), 'pod_vsctl': ([255], [1])}, f'Volume Memory off: both cards plain and live ({dim(m)})')
    m = loud_page('boot', flag=1)
    expect(dim(m) == {'pod_vsval': ([153], [0]), 'pod_vsctl': ([153], [0])}, f'Volume Memory on: both cards dimmed to 60 % and insensitive ({dim(m)})')
    sw = m.widgets['pod_switch0']
    expect([c[2] for c in m.calls if c[0] == 'image_base_set_image' and c[1] == sw][-1:] == ['sset_on'], 'the switch row shows the byte')
    m.calls = []; m.click('pod_row0')
    expect(m.byte(BOOTFLAG) == 0 and [c[:4] for c in loud_calls(m)] == [('write_int_config', 0, 'PLAYSET', 'BOOTVOLFLAG')] and dim(m) == {'pod_vsval': ([255], [1]), 'pod_vsctl': ([255], [1])}
           and [c[2] for c in m.calls if c[0] == 'image_base_set_image' and c[1] == sw][-1:] == ['sset_off'], 'a tap on the switch: the byte, the save, the switch, and the cards are live again')
    m.calls = []; m.click('pod_row0')
    expect(m.byte(BOOTFLAG) == 1 and dim(m) == {'pod_vsval': ([153], [0]), 'pod_vsctl': ([153], [0])}, 'and a tap back: dimmed again')
    m = loud_page('boot', flag=0, bootv=45)
    lab, sl = m.widgets['label_vol'], m.widgets['vol_slider']
    expect(('widget_set_text_utf8', lab, 'VOL: 45') in m.calls and ('slider_set_value', sl, 45.0) in m.calls, 'the page opens with the default volume on the label and the slider')
    expect(('widget_set_text_utf8', m.widgets['pod_vsnum'], '45') in m.calls, 'our label shows 45 alone')
    m.setword(BOOTV, 12); m.u.mem_write(BOOTFLAG, b'\1'); m.calls = []; m.fire(O['EVT_WINDOW_TO_FG'])
    expect(('widget_set_text_utf8', m.widgets['pod_vsnum'], '12') in m.calls, 'back in front: our label follows the default volume')
    expect(('slider_set_value', sl, 12.0) in m.calls and dim(m)['pod_vsctl'] == ([153], [0]) and not [c for c in m.calls if c[0] in LOUD], 'back in front: the slider and the dimming follow the words, nothing is written')
    # the value row of the main page: Memory while the byte is set, else the number
    for flag, boot, want in ((1, 30, ['Memory']), (0, 30, ['30']), (0, 0, ['0']), (0, 100, ['100'])):
        m = page(P_IDX, 14, ('pod_value', 'pod_label', 'pod_switch'), flag=flag, bootv=boot)
        got = [c[2] for c in m.calls if c[0] in ('widget_set_text_utf8', 'widget_set_tr_text') and c[1] == m.widgets['pod_value7']][-1:]
        expect(got == want, f'Default Volume row with the byte {flag} and the word {boot}: {got}')


def balance_tests(ctx):
    """Channel Balance: stock's slider, dec and add handlers on every value 0 .. 20 on each output; stock's own label against the main page's row text."""
    expect = ctx.expect
    bad = []; n = 0
    for hs in (0, 1, 2, 3):
        m = loud_page('bal', headset=hs)
        for bal in (0, 1, 7, 10, 13, 19, 20):
            for vol in (0, 37, 100):
                for what, targets in (('slider', range(0, 23)), ('dec', (0,)), ('add', (0,))):
                    for v in targets:
                        m.setword(BAL, bal); m.setword(VOLUME, vol); m.setword(HEADSET, hs)
                        run(m, 'bal', what, v)
                        want, wb, _ = spec_bal(what, v, bal, vol, hs)
                        got = norm(loud_calls(m), lambda st: (st[4], st[1])); n += 1
                        if got != want or m.word(BAL) != wb or m.word(VOLUME) != vol: bad.append((hs, bal, vol, what, v, got, want, m.word(BAL)))
    expect(not bad, f'Channel Balance: {n} runs (every value 0 .. 22, dec and add, 7 starts, 3 volumes, 4 outputs): stock\'s handlers store, save and call set_devicevolume(volume) as the model says, in that order ({bad[:2]})')
    m = loud_page('bal', headset=0); m.setword(VOLUME, 64)
    run(m, 'bal', 'slider', 3)
    expect(lc2(m, 'bal') == [('write_int_config', 3, 'PLAYSET', 'BALANCE', (3, 64)), ('set_devicevolume', 64, (3, 64)), ('reset_poweroptions_timer', 1, 1, 1)], f'a drag to 3: the word and its save, then set_devicevolume with the volume, then the timers ({lc2(m, "bal")})')
    m = loud_page('bal', headset=2)
    run(m, 'bal', 'slider', 3)
    expect([c[0] for c in loud_calls(m)] == ['write_int_config', 'reset_poweroptions_timer'], 'Bluetooth: saved, the device is not called')
    # the text: stock's own refresh writes the label; the main page's row reads the same word and says the same
    lab = None
    for b in range(0, 21):
        m = loud_page('bal', bal=b); lab = m.widgets['label_balance']
        stock = [c[2] for c in m.calls if c[0] == 'widget_set_text_utf8' and c[1] == lab][-1]
        pm = page(P_IDX, 14, ('pod_value', 'pod_label', 'pod_switch'), bal=b)
        row = [c[2] for c in pm.calls if c[0] == 'widget_set_text_utf8' and c[1] == pm.widgets['pod_value8']][-1]
        want = f'L{10 - b}' if b < 10 else '0' if b == 10 else f'R{b - 10}'
        sl = [c[2] for c in m.calls if c[0] == 'slider_set_value' and c[1] == m.widgets['slider_balance']][-1]
        if not (stock == row == want and sl == float(b)): expect(False, f'balance {b}: stock\'s label {stock!r}, the row {row!r}, expected {want!r}, the slider {sl}'); break
    else: expect(True, 'balance 0 .. 20: stock\'s label, the Playback Settings row and the model say L10 .. L1, 0, R1 .. R10, and the slider is at the word')
    m = loud_page('bal', bal=10)
    m.setword(BAL, 4); m.calls = []; m.fire(O['EVT_WINDOW_TO_FG'])
    expect(('widget_set_text_utf8', m.widgets['label_balance'], 'L6') in m.calls and ('slider_set_value', m.widgets['slider_balance'], 4.0) in m.calls and not [c for c in m.calls if c[0] in LOUD], 'back in front: the label and the slider follow the word, nothing is written')




def loudpages_tests(ctx):
    """The pages as built: the model's layout, stock's widget names and ranges, the buttons, the texts in 13 languages, and the main page's rows."""
    expect, P = ctx.expect, pod_pages
    import pod_i18n
    def desc(x): return (x.kind, x.part) if isinstance(x, P.VolCard) else 'row' if isinstance(x, P.Row) else 'gap' if x is P.GAP else '?'
    expect([(p.key, p.title, [desc(x) for x in p.layout]) for p in (P.PSMAXVOL_PAGE, P.PSBOOTVOL_PAGE, P.PSBAL_PAGE)] == [
        ('m1plus_psmaxvol', 'Max Volume', [('maxvol', 'value'), 'gap', ('maxvol', 'slider')]),
        ('m1plus_psbootvol', 'Default Volume', ['row', 'gap', ('bootvol', 'value'), 'gap', ('bootvol', 'slider')]),
        ('m1plus_psbal', 'Channel Balance', [('balance', 'value'), 'gap', ('balance', 'slider')])], 'the three pages: a value card, a gap and a control card; Default Volume starts with the Volume Memory switch row')
    expect([(r.label, r.action) for r in P.PSBOOTVOL_PAGE.rows] == [('Volume Memory', P.ACT_BOOTMEM)] and P.row_kind(P.PSBOOTVOL_PAGE.rows[0]) == 'switch' and not P.PSMAXVOL_PAGE.rows and not P.PSBAL_PAGE.rows, 'Volume Memory is the only row')
    raw = os.path.join(WORK, 'rootfs/release/assets/default/raw/ui')
    for key, label, slider, top, texts in (('m1plus_psmaxvol', 'label_vol', 'vol_slider', '100', ('−', '+')), ('m1plus_psbootvol', 'label_vol', 'vol_slider', '100', ('−', '+')), ('m1plus_psbal', 'label_balance', 'slider_balance', '20', ('L', 'R'))):
        t = awtk_ui.parse(open(os.path.join(raw, key + '.bin'), 'rb').read())
        s, lab, dec, add = t.find(slider), t.find(label), t.find('btn_dec'), t.find('btn_add')
        expect(s.type == 'slider' and s.get('max') == top and s.get('step') == '1' and s.get('slide_with_bar') == 'true' and s.get('style:normal:icon') == 'pod_sl_thumb' and s.get('style:normal:bg_image') == 'drop_bg' and s.get('style:normal:fg_image') == 'drop_fg',
               f'{key}: stock\'s slider name, 0 .. {top}, the Display page\'s slider look')
        num = t.find('pod_vsnum')
        expect((num is None) == (label == 'label_balance') and (num is None or (num.type == 'label' and num.get('sensitive') == 'false' and num.get('visible') != 'false' and num.get('text') == '' and num.w == lab.w and num.x == lab.x))
               and (lab.get('visible') == 'false') == (num is not None), f'{key}: stock\'s label is kept hidden (and insensitive) beside our number label on Max Volume and Default Volume; Channel Balance shows stock\'s')
        expect(lab.type == 'label' and lab.get('sensitive') == 'false' and dec.type == 'button' and add.type == 'button' and dec.get('text') == texts[0] and add.get('text') == texts[1] and dec.w >= 44 and add.w >= 44
               and dec.x < s.x and s.x + s.w <= add.x, f'{key}: the label is shown, the buttons ({texts[0]} / {texts[1]}) are touch-sized and sit either side of the slider')
        expect(all(b.get(f'style:{st}:border_width') == '0' and b.get(f'style:{st}:border_color') == '#00000000' and b.get(f'style:{st}:bg_color') == '#00000000' for b in (dec, add) for st in ('normal', 'pressed', 'over', 'focused', 'disable', 'selected')),
               f'{key}: the buttons draw no border and no fill in any state (the theme\'s default button style would draw a square one)')
        ctl = t.find('pod_vsctl').children
        for b, dn in ((dec, 'pod_vsdisc_dec'), (add, 'pod_vsdisc_add')):
            d = t.find(dn)
            expect(d is not None and d.type == 'view' and d.get('sensitive') == 'false' and d.w == d.h == 36 and d.get('style:normal:round_radius') == '18' and d.get('style:normal:bg_color') == '#FFFFFF14' and d.get('style:normal:border_width') == '0'
                   and 2 * d.x + d.w == 2 * b.x + b.w and 2 * d.y + d.h == 2 * b.y + b.h and ctl.index(d) < ctl.index(b), f'{key}: {dn} is a faint round disc centred under the button, insensitive and drawn before it')
        expect(s.x - (t.find('pod_vsdisc_dec').x + 36) == t.find('pod_vsdisc_add').x - (s.x + s.w) == 13, f'{key}: the bar\'s ends stand 13 px clear of the discs, the same on both sides')
        expect(t.find('pod_vsval') is not None and t.find('pod_vsctl') is not None and t.find('pod_vsval').find(label) is lab and (num is None or t.find('pod_vsval').find('pod_vsnum') is num) and t.find('pod_vsctl').find(slider) is s, f'{key}: the value card holds the label, the control card the slider')
    for loc in pod_i18n.LOCALES:
        expect(all(pod_i18n.TEXT[k][pod_i18n.table_for(loc)] for k in ('Max Volume', 'Default Volume', 'Channel Balance', 'Volume Memory', 'Memory')), f'the loudness texts have a translation in {loc}')


def volnum_tests(ctx):
    """Max Volume and Default Volume show the number alone: the handlers run in the emitter's order (the newest bound first, read from stock), stock's then ours, and the label shows the word as stock left it."""
    expect = ctx.expect

    def dispatch(m, widget, ev, e):
        hs = m.bindings[(widget, ev)]   # in the order they were bound
        calls = []
        for fn, ctx_ in reversed(hs):   # emitter_on_with_tag puts the new handler at the head, emitter_dispatch walks from the head
            m.call(fn, a0=ctx_, a1=e, count=3000000); calls += m.calls   # (each call starts a new record)
        m.calls = calls
    for which, word, text in (('max', MAXV, 'VOL: %d'), ('boot', BOOTV, 'VOL: %d')):
        m = loud_page(which, volume=20, maxv=90, bootv=30, flag=0)
        num, lab, sl = m.widgets['pod_vsnum'], m.widgets['label_vol'], m.widgets['vol_slider']
        m.bindings = {}
        for c in m.calls:
            if c[0] == 'widget_on': m.bindings.setdefault((c[1], c[2]), []).append((c[3], c[4]))
        bad = []
        for v in (0, 1, 47, 100):
            m.calls, m.snap = [], []
            dispatch(m, sl, EVT_CHANGING, event(m, sl, v))
            shown = [c[2] for c in m.calls if c[0] == 'widget_set_text_utf8' and c[1] == num]
            stock = [c[2] for c in m.calls if c[0] == 'widget_set_text_utf8' and c[1] == lab]
            if shown != [str(m.word(word))] or stock != [text % m.word(word)] or m.word(word) != v: bad.append((v, shown, stock, m.word(word)))
        expect(not bad, f'{which}: after each slider change stock\'s label says "VOL: n" (hidden) and ours says n, once, from the word stock has just stored ({bad[:2]})')
        for btn in ('btn_dec', 'btn_add'):
            for start in (0, 1, 50, 99, 100):
                m.setword(word, start); m.calls, m.snap = [], []
                dispatch(m, m.widgets[btn], EVT_CLICK_, 0)
                shown = [c[2] for c in m.calls if c[0] == 'widget_set_text_utf8' and c[1] == num]
                if shown != [str(m.word(word))]: bad.append((btn, start, shown, m.word(word)))
        expect(not bad, f'{which}: after each - and + tap our label shows the word as stock left it ({bad[:2]})')
    m = loud_page('bal')
    expect('pod_vsnum' not in m.widgets and not [c for c in m.calls if c[0] == 'widget_set_text_utf8' and c[2][:1] not in ('L', 'R', '0')], 'Channel Balance has no number label: stock\'s own L3 / 0 / R2 text')


SECTIONS = [toggle_tests, choice_tests, mode_tests, settings_tests, pin_tests, maxvol_tests, bootvol_tests, balance_tests, loudpages_tests, volnum_tests]
