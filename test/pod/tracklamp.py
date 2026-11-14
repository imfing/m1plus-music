"""Sample Rate, the lamp's fourth mode (patch/tracklamp.c, docs/modules/display.md "Sample Rate"): the hook's cost with the setting off and on, the rate's colour (every band, DSD, USB DAC
mode), the six themes as the timer draws them, the pause fade, what lets the lamp go (stop, the kill switch, Follow Screen, the radio) and what it then shows, the saved setting, and the
LED Light and Theme pickers."""
import os
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)
import cdefs

DEFS = cdefs.defines(os.path.join(ROOT, 'patch', 'tracklamp.h'), strings=True)
FILE, LAMP, UAC, KILL = DEFS['TL_FILE'], DEFS['TL_LAMP'], DEFS['TL_UAC'], '/mnt/mmc/m1plus-off'
POLL, FAST, FADE, PAUSE, GONE, LEVEL = (DEFS[k] for k in ('TL_POLL_MS', 'TL_FAST_MS', 'TL_FADE_MS', 'TL_PAUSE_MS', 'TL_GONE', 'TL_LEVEL'))
REFERENCE, BREATHE, HEARTBEAT, LIGHTHOUSE, CANDLE, OCEAN = range(6)
STATE, LED, FOLLOW, LIT = pod.DATA['ATMOSPHERE_RGB_STATE'][0], pod.DATA['LED_MODE'][0], pod.DATA['LED_FOLLOW'][0], pod.DATA['BACKLIGHT_STATUS'][0]
EXT, PMU, USBSTATE, USBFLAG = (pod.DATA[k][0] for k in ('POWER_EXT', 'PMUCHARGE_STATUS', 'POWER_USBSTATE', 'POWER_FLAG'))
PASS = 50   # the main loop's pass in these runs, ms
RED = LEVEL << 16


class LM(Machine):
    """The player: its status (1 stopped, 2 playing, 3 paused) and its information record (mclGetInfo: bit/s, Hz, the codec's name at 0x10, bits at 0x30)."""
    def __init__(self):
        super().__init__()
        self.status, self.info = 2, dict(rate=44100, fmt='FLAC', bits=16)
        self.clock = 100000
        self.timer = None   # our timer as the loop holds it: [period, due]
        for n in ('mclGetPlayStatus', 'mclGetInfo'): self.handlers[pod.FUNCTIONS[n][2]] = n

    def _hook(self, u, address, size, _):
        name = self.handlers.get(address)
        if name not in ('mclGetPlayStatus', 'mclGetInfo', 'reset_atmosphereled_rgb'): return super()._hook(u, address, size, _)
        ret = self.status
        if name == 'mclGetInfo':
            i = self.info
            u.mem_write(u.reg_read(UC_MIPS_REG_A0), struct.pack('<iiii32si', 900000, i['rate'], 0, 0, i['fmt'].encode(), i['bits'])); ret = 1
        self.calls.append((name,))
        u.reg_write(UC_MIPS_REG_V0, ret); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))

    def byte(self, a): return self.u.mem_read(a, 1)[0]


def machine(saved=b'1\n', rate=44100, bits=16, fmt='FLAC', name='1.flac', status=2):
    """A track that plays, the screen lit, Follow Screen off, on battery; saved: the setting file (None: missing)."""
    m = LM()
    if saved is not None: m.fs[FILE] = saved
    m.fs[LAMP] = b''
    m.status, m.info = status, dict(rate=rate, fmt=fmt, bits=bits)
    m.play([m.record(name=name, path='/mnt/mmc/a/' + name)], 0)
    for a in (EXT, PMU, USBSTATE): m.setword(a, 0)
    m.u.mem_write(USBFLAG, b'\0'); m.u.mem_write(FOLLOW, b'\0'); m.u.mem_write(LED, b'\0'); m.u.mem_write(LIT, b'\1'); m.u.mem_write(STATE, bytes(4))
    return m


def run(m, ms):
    """The main loop for ms: the hook on every pass, our timer when it is due (at the period it was added with; RET_REPEAT keeps it). Returns the lamp writes as (red, green, blue);
    m.log is every call the payload made, m.periods the periods of the timers it added."""
    out, m.log, m.periods = [], [], []

    def took():
        m.log += m.calls
        for c in m.calls:
            if c[0] == 'timer_add':
                m.timer = [c[2], m.clock + c[2]]; m.periods.append(c[2])
            if c[0] == 'write' and c[1] == LAMP:
                v = int(c[2]); out.append((v >> 16, v >> 8 & 255, v & 255))

    for _ in range(ms // PASS):
        m.clock += PASS
        m.hook_ret = m.call(PSYMS['tl_play_status'], count=400000); took()
        if m.timer and m.clock >= m.timer[1]:
            held = m.timer; m.timer = None
            r = m.call(PSYMS['tl_tick'], count=400000); took()
            if r == O['RET_REPEAT']: held[1] += held[0]; m.timer = held
    return out


def lamp(m):
    """Stock's state as (red, green, blue): it is stored red, blue, green."""
    r, b, g, _ = m.u.mem_read(STATE, 4)
    return (r, g, b)


def names(m): return [c[0] for c in m.log]


def smooth(writes):
    """No channel moves more than one level from one write to the next."""
    return all(abs(a - b) <= 1 for p, q in zip(writes, writes[1:]) for a, b in zip(p, q))


def hook_tests(ctx):
    """Opt in: nothing but a compare with the setting off; with it on the hook starts one timer and the timer does the work."""
    expect = ctx.expect
    expect(MANIFEST['hook_format_lamp'] == {'addr': pod.FORMAT_LAMP_SITE, 'target': PSYMS['tl_play_status']} and pod.FORMAT_LAMP_SITE == 0x4ce968, 'the hook is on_wm_idle_status\'s mclGetPlayStatus call')
    pins = {a: w for a, w, _ in pod.FORMAT_LAMP_PINS}
    expect(pins[0x4ce968] == 0x0320f809 and pins[0x4ce96c] == 0 and all(a in pins for a in (0x4cff88, 0x4cff9c, 0x4e6bac, 0x4e6bd0, 0x4e6bdc, 0x4e6be0)),
           'pinned: the call and its delay slot, stock\'s lamp timer (the state and its pending byte), and reset_atmosphereled_rgb\'s charging rule')
    for saved in (None, b'0\n', b'7\n', b'x\n', b''):
        m = machine(saved=saved)
        for st in (1, 2, 3):
            m.status = st
            w = run(m, PASS)
            expect(m.hook_ret == st and not w and 'timer_add' not in names(m), f'the file {saved}, status {st}: stock\'s answer, no timer, no lamp write')
        w = run(m, 2000)
        expect(not w and set(names(m)) == {'mclGetPlayStatus'} and names(m).count('mclGetPlayStatus') == 2000 // PASS and lamp(m) == (0, 0, 0),
               f'the file {saved}: after the first read a pass is stock\'s call alone (no file, no kill switch test, no timer) ({set(names(m))})')
    m = machine()
    run(m, PASS)
    expect(m.hook_ret == 2 and m.periods == [POLL] and not any(n in names(m) for n in ('access', 'mclGetInfo', 'write')), 'on: the first pass adds the timer (the poll\'s pace) and does nothing else')
    w = run(m, 2000)
    expect(w == [(11, 2, 4)] and 'timer_add' not in names(m) and names(m).count('access') == 2000 // POLL == names(m).count('mclGetInfo'),
           f'then the timer asks every {POLL} ms (the kill switch, the track) and the lamp is written once: 44.1 kHz ({w})')
    m = machine(); m.timer_fail = True
    w = run(m, 3 * PASS)
    expect(not w and names(m).count('timer_add') == 3, 'no timer to be had: the hook tries again on the next pass, the lamp is stock\'s')
    m.timer_fail = False
    expect(run(m, 2 * POLL) == [(11, 2, 4)], 'and the lamp follows once there is one')


def colour_tests(ctx):
    """Reference: the rate's colour, steady. The ten bands, DSD as its DoP carrier's rate, USB DAC mode."""
    expect = ctx.expect
    bands = ((8000, (11, 2, 4)), (44100, (11, 2, 4)), (44101, (9, 2, 7)), (48000, (9, 2, 7)), (88200, (5, 2, 10)), (96000, (2, 3, 12)), (176400, (2, 6, 9)), (192000, (2, 9, 7)),
             (352800, (2, 11, 4)), (384000, (3, 13, 2)), (705600, (2, 14, 2)), (768000, (2, 14, 2)), (1411199, (2, 14, 2)), (1411200, (0, 17, 0)))
    for rate, want in bands:
        m = machine(rate=rate)
        w = run(m, 1000)
        expect(w == [want] and lamp(m) == want and m.byte(STATE + 3) == 0 and m.fs[LAMP] == f'{want[0] << 16 | want[1] << 8 | want[2]}\n'.encode(),
               f'{rate} Hz: {want}, one write of the decimal number, stock\'s state the same with no pending byte ({w})')
    for what, kw, want in (('DSD64 (1 bit)', dict(rate=2822400, bits=1, fmt='DSD', name='1.dsf'), (2, 6, 9)), ('DSD128', dict(rate=5644800, bits=1, fmt='DSD', name='1.dff'), (2, 11, 4)),
                           ('DSD256', dict(rate=11289600, bits=1, fmt='DSD', name='1.dsf'), (2, 14, 2)), ('DSD512', dict(rate=22579200, bits=1, fmt='DSD', name='1.dsf'), (0, 17, 0)),
                           ('a .dsf file whose record has no bit depth', dict(rate=2822400, bits=0, fmt='', name='1.DSF'), (2, 6, 9)),
                           ('the codec label DSD128', dict(rate=5644800, bits=0, fmt='DSD128', name='stream'), (2, 11, 4)),
                           ('a FLAC named dsd.flac', dict(rate=96000, bits=24, fmt='FLAC', name='dsd.flac'), (2, 3, 12))):
        m = machine(**kw)
        w = run(m, 1000)
        expect(w == [want], f'{what}: {want} ({w})')
    # the next track: another colour on the next poll, written once
    m = machine(rate=44100); run(m, 1000)
    m.info['rate'] = 192000
    w = run(m, 1000)
    expect(w == [(2, 9, 7)], f'the track changes to 192 kHz: one write ({w})')
    # nothing to show
    m = machine(rate=0)
    expect(not run(m, 1000) and lamp(m) == (0, 0, 0), 'the player has no rate yet: no write')
    m = machine(); m.play_pos = -1
    expect(not run(m, 1000), 'no track in the queue: no write')
    # USB DAC mode: the host's rate from the gadget driver, no queue record
    for text, want in ((b'96000\n', (2, 3, 12)), (b'44100\n', (11, 2, 4)), (b'2822400\n', (2, 6, 9)), (b'384000\n', (3, 13, 2))):
        m = machine(status=1); m.play_pos = -1
        m.setword(USBSTATE, 2); m.u.mem_write(USBFLAG, b'\1'); m.fs[UAC] = text
        w = run(m, 1000)
        expect(w == [want] and 'mclGetInfo' not in names(m), f'USB DAC mode, the host sends {text}: {want} ({w})')
    m = machine(status=1); m.setword(USBSTATE, 2); m.u.mem_write(USBFLAG, b'\1'); m.fs[UAC] = b'48000\n'
    run(m, 1000); m.fs[UAC] = b'0\n'
    w = run(m, 2000)
    expect(w == [(0, 0, 0)], f'the host stops sending (rate 0): the lamp is let go ({w})')
    m = machine(status=1); m.setword(USBSTATE, 2); m.u.mem_write(USBFLAG, b'\1')
    expect(not run(m, 1000), 'no rate file: no write')
    # the lamp file
    m = machine(); m.fail.add(('open', LAMP))
    w = run(m, 1000)
    expect(not w and lamp(m) == (0, 0, 0), 'the lamp file cannot be opened: stock\'s state is left alone')
    m.fail.clear()
    expect(run(m, POLL) == [(11, 2, 4)], 'and the colour is written on the next tick that can')
    m = machine(); run(m, 1000)
    m.u.mem_write(STATE, bytes([LEVEL, 0, 0, 0]))   # stock lit its red (power was plugged in) and its timer applied it
    w = run(m, POLL)
    expect(w == [(11, 2, 4)] and lamp(m) == (11, 2, 4), 'stock changed the lamp under a playing track: ours is written again on the next tick')


def theme_tests(ctx):
    """The five moving themes: the timer runs TL_FAST_MS apart and every frame's levels are in range; the gentle ones never skip a level."""
    expect = ctx.expect
    expect(FAST == 50 and POLL == 250 and LEVEL == 17, 'the paces: 50 ms while a theme moves, 250 ms otherwise; 17 is the brightest level')

    def play(theme, ms, **kw):
        m = machine(saved=f'{theme + 1}\n'.encode(), **kw)
        return m, run(m, ms)

    m, w = play(BREATHE, 8500)
    expect(m.periods == [POLL, FAST] and names(m).count('access') in range(8500 // POLL - 2, 8500 // POLL + 1), f'Gentle Breathe: the timer turns to {FAST} ms; the player is still asked every {POLL} ms ({m.periods})')
    expect(max(w) == (12, 1, 4) and min(w) == (2, 0, 1) and smooth(w) and len(w) > 30, f'two 4 s breaths between 15 % and the full colour of 44.1 kHz in its palette, a level at a time ({min(w)} .. {max(w)}, {len(w)} writes)')
    reds = [p[0] for p in w]
    turns = sum(1 for a, b, c in zip(reds, reds[1:], reds[2:]) if (b - a) * (c - b) < 0)
    expect(turns in (3, 4), f'it rises and falls twice in 8 s ({turns} turns)')
    m, w = play(BREATHE, 4500, rate=192000)
    expect(max(w, key=sum) == (1, 5, 11), f'192 kHz in its palette ({max(w, key=sum)})')
    m, w = play(HEARTBEAT, 3400)
    full, dark = (9, 3, 4), (0, 0, 0)
    expect(m.periods == [POLL, FAST] and w.count(full) == 2 and dark in w and all(sum(p) <= sum(full) for p in w), f'Heartbeat: two beats in 3.2 s reach the full colour, dark between them ({w.count(full)} full)')
    soft = max(sum(p) for i, p in enumerate(w) if 0 < i < len(w) - 1 and sum(w[i - 1]) < sum(p) > sum(w[i + 1]) and p != full)
    expect(sum(full) * 5 // 10 <= soft <= sum(full) * 8 // 10, f'and a softer second beat ({soft} of {sum(full)})')
    m, w = play(LIGHTHOUSE, 6500)
    expect(m.periods == [POLL, FAST] and max(w, key=sum) == (11, 2, 4) and (0, 0, 0) in w and len(w) > 12, f'Lighthouse: one 6 s turn reaches Reference\'s colour and goes dark ({max(w, key=sum)})')
    m, w = play(CANDLE, 6000, rate=192000)
    expect(m.periods == [POLL, FAST] and all(b == 0 and 9 <= r <= 17 and 1 <= g <= 9 and g < r for r, g, b in w) and len(set(w)) > 3 and smooth(w), f'Candle: red over a little green, never blue, flickering a level at a time ({sorted(set(w))})')
    m2, w2 = play(CANDLE, 6000, rate=44100)
    expect(w2 == w, 'its colours are its own: the rate does not change them')
    m, w = play(OCEAN, 12500)
    expect(m.periods == [POLL, FAST] and smooth(w) and {(17, 0, 0), (0, 17, 0), (0, 0, 17)} <= set(w) and all(sum(p) in (16, 17, 18) for p in w), f'Wave: 12 s around the wheel through red, green and blue at full brightness, a level at a time ({len(w)} writes)')
    # the screen goes dark without Follow Screen: the theme goes on (the lamp is what is left to see)
    m, w = play(BREATHE, 1000)
    m.u.mem_write(LIT, b'\0')
    expect(len(run(m, 2000)) > 5, 'a dark screen without Follow Screen: the theme goes on')
    # a new theme from the page: the next frame is the new theme's
    m, w = play(REFERENCE, 1000)
    expect(w == [(11, 2, 4)] and m.periods == [POLL], f'Reference: steady, at the poll\'s pace ({m.periods})')
    expect(m.call(PSYMS['tl_theme_set'], a0=OCEAN, count=4000000) == 0 and m.fs[FILE] == b'6\n', 'Wave is chosen')
    w = run(m, 1000)
    expect(m.periods == [FAST] and w[0][0] >= 15 and w[0][2] == 0 and smooth(w), f'the next tick draws it from its start and the timer turns fast ({w[:2]}, {m.periods})')
    m.call(PSYMS['tl_theme_set'], a0=REFERENCE, count=4000000)
    w = run(m, 1000)
    expect(w == [(11, 2, 4)] and m.periods == [POLL], 'back to Reference: the rate\'s colour, the slow pace')


def pause_tests(ctx):
    """A pause fades to a fifth and then lets the lamp go; a stop lets it go after a second; the kill switch, Follow Screen and the radio at once. Let go, the lamp is stock's."""
    expect = ctx.expect
    m = machine(); run(m, 1000)
    m.status = 3
    w = run(m, POLL + FADE + 100)
    expect(w[-1] == (2, 0, 1) and smooth(w) and len(w) >= 8 and FAST in m.periods, f'a pause: down to a fifth of the colour in {FADE} ms, a level at a time, the timer fast for it ({w})')
    w = run(m, 1000)
    expect(not w and m.timer[0] == POLL, f'then it holds, at the slow pace ({w}, {m.timer})')
    w = run(m, PAUSE)
    expect(w == [(0, 0, 0)] and lamp(m) == (0, 0, 0), f'{PAUSE} ms after the pause the lamp is let go ({w})')
    expect(not run(m, 2000), 'and stays so while paused')
    m.status = 2
    expect(run(m, 2 * POLL) == [(11, 2, 4)], 'play again: the colour is back')
    m.status = 3; run(m, POLL + 200); m.status = 2
    w = run(m, 2 * POLL)
    expect(w[-1] == (11, 2, 4), 'play during the fade: the full colour again')
    # a moving theme stands still while paused
    m = machine(saved=b'6\n'); run(m, 3000)
    m.status = 3; run(m, POLL + FADE + 100)
    expect(not run(m, 1000), 'Wave paused: the wheel stands still')
    # stop: the gap between two tracks does not blink
    m = machine(); run(m, 1000)
    m.status = 1
    expect(not run(m, (GONE - 1) * POLL - PASS), f'the player stops: the colour stays for {GONE - 1} polls (the gap between two tracks)')
    m.status = 2
    expect(not run(m, 1000), 'the next track of the same rate: nothing was written at all')
    m.status = 1
    w = run(m, (GONE + 1) * POLL)
    expect(w == [(0, 0, 0)], f'stopped for {GONE} polls: the lamp is let go ({w})')
    # let go: what stock shows with its mode Off (reset_atmosphereled_rgb's rule), and no config is saved
    for ext, pmu, want, what in ((1, 1, (LEVEL, 0, 0), 'charging: stock\'s red'), (1, 0, (LEVEL, 0, 0), 'external power, the status not Full: red'), (1, 2, (0, 0, 0), 'full: dark'), (0, 1, (0, 0, 0), 'on battery: dark')):
        m = machine(); m.setword(EXT, ext); m.setword(PMU, pmu); run(m, 1000)
        m.status = 1
        w = run(m, (GONE + 1) * POLL)
        expect(w == [want] and lamp(m) == want and not any(n in names(m) for n in ('write_int_config', 'reset_atmosphereled_rgb')), f'{what} ({w}); nothing is saved to the config')
    # the kill switch, Follow Screen with a dark screen, the radio: at the next poll
    def kill(m): m.present.add(KILL)
    def unkill(m): m.present.discard(KILL)
    def dark(m): m.u.mem_write(FOLLOW, b'\1'); m.u.mem_write(LIT, b'\0')
    def lit(m): m.u.mem_write(LIT, b'\1')
    def radio(m): m.setword(PSYMS['rd'], 2)   # (rd.state = RD_PLAYING)
    def noradio(m): m.setword(PSYMS['rd'], 0)
    for what, on, off in (('the kill switch', kill, unkill), ('Follow Screen and a dark screen', dark, lit), ('the radio plays', radio, noradio)):
        for theme in (REFERENCE, OCEAN):
            m = machine(saved=f'{theme + 1}\n'.encode()); run(m, 1000)
            on(m)
            w = run(m, POLL)
            expect(w[-1:] == [(0, 0, 0)] and lamp(m) == (0, 0, 0), f'{what}, theme {theme}: the lamp is let go at the next poll ({w[-1:]})')
            expect(not run(m, 2000) and m.periods in ([], [POLL]), 'no write while it lasts, the timer at the slow pace')
            off(m)
            w = run(m, 2 * POLL)
            expect(w and w[0] != (0, 0, 0), f'it ends: the theme is back ({w[:1]})')
    m = machine(); m.u.mem_write(FOLLOW, b'\1')
    expect(run(m, 1000) == [(11, 2, 4)], 'Follow Screen with the screen lit: the colour shows')


def setting_tests(ctx):
    """The saved setting, LED Light's fourth mode and the Theme picker."""
    expect = ctx.expect
    display = sibling('display')
    P = pod_pages
    T = P.RGB_THEME_PAGE
    expect(DEFS['TL_THEMES'] == len(P.RGB_THEMES) == 6 and P.RGB_THEMES == ('Reference', 'Gentle Breathe', 'Heartbeat', 'Lighthouse', 'Candle', 'Wave')
           and [DEFS[k] for k in ('TL_REFERENCE', 'TL_BREATHE', 'TL_HEARTBEAT', 'TL_LIGHTHOUSE', 'TL_CANDLE', 'TL_OCEAN')] == list(range(6)), 'six themes, the page\'s order is the header\'s')
    expect([(r.label, r.action, r.arg) for r in T.rows] == [(n, P.ACT_RGBTHEME, i) for i, n in enumerate(P.RGB_THEMES)] and all(P.row_kind(r) == 'check' for r in T.rows) and P.ACT_RGBTHEME == 140
           and (T.key, T.title) == ('m1plus_rgbtheme', 'Theme') and P.PAGES[P.RGB_THEME_PAGE_INDEX] is T, 'the Theme picker: a check row a theme, the argument is the theme')
    lay = [x.label if isinstance(x, P.Row) else (type(x).__name__, x.text) for x in T.layout]
    expect(lay == [('Hdr', 'Sample Rate'), 'Reference', 'Gentle Breathe', 'Heartbeat', 'Lighthouse', ('Note', "The color changes with the file's sample rate"), ('Hdr', 'Ambient'), 'Candle', 'Wave'],
           f'two headed cards: Sample Rate, the four that show the rate, with a note on the colour; Ambient, the two with colours of their own ({lay})')
    led = [x.label if isinstance(x, P.Row) else x for x in P.LED_PAGE.layout]
    expect(led == ['Off', 'Green', 'Blue', 'Dynamic', P.GAP, 'Follow Screen', P.GAP, 'Theme'] and P.row_kind(P.LED_PAGE.rows[4]) == 'switch', f'LED Light: the choices, the Follow Screen switch, then the Theme row, each card of its own ({led})')
    expect(not any(hasattr(P, a) for a in ('ACT_RGBWARNING', 'ACT_RGBVOLUME')) and not any(isinstance(x, P.Row) and P.row_kind(x) == 'switch' for x in T.layout), 'no switch on the page')
    expect(FILE == '/mnt/data/m1plus/led-dynamic' and 'led-dynamic' in P.SETTING_FILES and 'led-dynamic-options' not in P.SETTING_FILES, 'one setting file, listed on Settings Files')
    import pod_i18n
    for loc in pod_i18n.LOCALES:
        expect(all(pod_i18n.TEXT[k][loc] for k in P.RGB_THEMES + ('Dynamic', 'Theme', 'Sample Rate', 'Ambient', "The color changes with the file's sample rate")), f'the page texts have a translation in {loc}')
    # the saved character
    for saved, led, theme in ((None, 0, 0), (b'0\n', 0, 0), (b'1\n', 3, 0), (b'1', 3, 0), (b'4\n', 3, 3), (b'6\n', 3, 5), (b'7\n', 0, 0), (b'11\n', 0, 0), (b'x\n', 0, 0)):
        m = machine(saved=saved)
        expect((m.call(PSYMS['tl_led'], count=400000), m.call(PSYMS['tl_theme'], count=400000)) == (led, theme), f'the file {saved}: LED Light {led}, theme {theme}')
    for stock in (1, 2):
        m = machine(saved=b'0\n'); m.u.mem_write(LED, bytes([stock]))
        expect(m.call(PSYMS['tl_led'], count=400000) == stock, f'off: LED Light shows stock\'s mode {stock}')
    # LED Light
    def dm(saved, led=0):
        m = machine(saved=saved); m.u.mem_write(LED, bytes([led]))
        return m

    def led_set(m, mode):
        r = m.call(PSYMS['tl_led_set'], a0=mode & 0xffffffff, count=4000000)
        return r, [c[:4] for c in m.calls if c[0] in ('write_int_config', 'reset_atmosphereled_rgb')]

    m = dm(None, led=2)
    r, saves = led_set(m, 3)
    expect(r == 0 and m.fs[FILE] == b'1\n' and FILE + '.tmp' not in m.fs and m.byte(LED) == 0 and saves[0] == ('write_int_config', 0, 'SYSSET', 'ATMOSPHERELEDMODE') and saves[1][0] == 'reset_atmosphereled_rgb',
           f'Dynamic from Blue: the file is 1 (Reference), stock\'s mode goes Off the way stock\'s page sets it ({saves})')
    expect(run(m, 2 * POLL) == [(11, 2, 4)], 'and the lamp shows the rate within two polls')
    m = dm(b'5\n')
    r, saves = led_set(m, 3)
    expect(r == 0 and m.fs[FILE] == b'5\n' and not saves and not any(c[0] == 'open' and c[1] == FILE + '.tmp' for c in m.calls), 'Dynamic while on: the theme stays, nothing written')
    m = dm(None); m.fail.add(('open', FILE + '.tmp'))
    r, saves = led_set(m, 3)
    expect(r == 0xffffffff and FILE not in m.fs and not saves and m.call(PSYMS['tl_led'], count=400000) == 0, 'the file cannot be written: refused, nothing changed')
    for mode in (0, 1, 2):
        m = dm(b'3\n'); m.setword(EXT, 1); m.setword(PMU, 1)
        run(m, 1000)
        r, saves = led_set(m, mode)
        rel = [c[2] for c in m.calls if c[0] == 'write' and c[1] == LAMP]
        want = [] if mode == 0 else [('write_int_config', mode, 'SYSSET', 'ATMOSPHERELEDMODE')]
        expect(r == 0 and m.fs[FILE] == b'0\n' and rel == [f'{RED}\n'.encode()] and saves[:1] == want and m.byte(LED) == mode, f'mode {mode} from Dynamic: the file is 0, the lamp is let go at once, then stock\'s own change ({saves})')
        w = run(m, 1000)
        expect(not w and m.timer is None and names(m)[-3:] == ['mclGetPlayStatus'] * 3, 'the timer ends on its next tick: the hook is a compare again')
    for bad in (-1, 4, 9):
        m = dm(b'2\n')
        r, saves = led_set(m, bad)
        expect(r == 0xffffffff and m.fs[FILE] == b'2\n' and not saves, f'mode {bad}: refused')
    # the theme
    m = machine(saved=b'1\n')
    for theme in (5, 0, 3):
        r = m.call(PSYMS['tl_theme_set'], a0=theme, count=4000000)
        expect(r == 0 and m.fs[FILE] == f'{theme + 1}\n'.encode() and m.call(PSYMS['tl_theme'], count=400000) == theme, f'theme {theme}: saved as {theme + 1}')
    m.call(PSYMS['tl_theme_set'], a0=3, count=4000000)
    expect(not any(c[0] == 'open' for c in m.calls), 'the chosen theme again: nothing written')
    for bad in (-1, 6, 10):
        expect(m.call(PSYMS['tl_theme_set'], a0=bad & 0xffffffff, count=4000000) == 0xffffffff and m.fs[FILE] == b'4\n', f'theme {bad}: refused')
    # the pickers on the device: LED Light's Dynamic row saves and shows the Theme row, which opens the theme page; a theme row moves the check
    def page(index, nrows, saved):
        m = machine(saved=saved)
        m.widgets = {n: 0x30000000 + 0x100 * i for i, n in enumerate(['btn_return', 'btn_backtoplayer'] + [f'{k}{i}' for k in ('pod_row', 'pod_check', 'pod_label', 'pod_value') for i in range(nrows)])}
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

    def row_state(m, i):
        vis = [c[2] for c in m.calls if c[0] == 'widget_set_visible' and c[1] == m.widgets[f'pod_row{i}']]
        sens = [c[2] for c in m.calls if c[0] == 'widget_set_sensitive' and c[1] == m.widgets[f'pod_row{i}']]
        return (vis[-1] if vis else None, sens[-1] if sens else None)

    def theme_value(m):
        t = [c[2] for c in m.calls if c[0] == 'widget_set_tr_text' and c[1] == m.widgets['pod_value5']]
        return t[-1] if t else None

    m = page(P.LED_PAGE_INDEX, 6, b'0\n')
    expect(checks(m, 4) == [1, 0, 0, 0], 'the LED Light picker with the setting off: the check is on Off')
    expect(row_state(m, 5) == (0, 0), 'the Theme row is hidden and insensitive while Dynamic is not chosen')
    m.click('pod_row3')
    expect(m.fs[FILE] == b'1\n' and checks(m, 4) == [0, 0, 0, 1] and ('window_open', T.key) not in m.calls, 'a tap on Dynamic: saved, checked, and no page opens')
    expect(row_state(m, 5) == (1, 1) and theme_value(m) == 'Reference', 'the Theme row appears at once, with the theme\'s name')
    m.click('pod_row0')
    expect(m.fs[FILE] == b'0\n' and row_state(m, 5) == (0, 0), 'a tap on Off: the Theme row goes away at once')
    m.click('pod_row3')
    m.click('pod_row5')
    expect(('window_open', T.key) in m.calls, 'a tap on the Theme row opens the Theme page')
    m = page(P.LED_PAGE_INDEX, 6, b'5\n')
    expect(row_state(m, 5) == (1, 1) and theme_value(m) == 'Candle', 'opening with Dynamic on and Candle: the Theme row shows Candle')
    m = page(P.LED_PAGE_INDEX, 6, b'2\n')
    expect(checks(m, 4) == [0, 0, 0, 1], 'with the setting on: the check is on Dynamic')
    for saved, at in ((b'1\n', 0), (b'5\n', 4)):
        m = page(P.RGB_THEME_PAGE_INDEX, 6, saved)
        expect(('window_open', T.key) in m.calls and checks(m, 6) == [int(i == at) for i in range(6)], f'the theme page with the file {saved}: the check is on row {at}')
    m.click('pod_row2')
    expect(m.fs[FILE] == b'3\n' and checks(m, 6) == [0, 0, 1, 0, 0, 0], 'a tap on Heartbeat: saved as 3, the check follows')
    expect(display is not None, 'Display\'s own tests cover Off, Green and Blue')


SECTIONS = [hook_tests, colour_tests, theme_tests, pause_tests, setting_tests]
