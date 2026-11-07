"""The iPod page's Cover Flow screen (patch/ipod_cf.c, the K_CF level of patch/ipod.c, docs/modules/ipod-coverflow.md): entering it from the iPod main menu (its frame and
textures, the albums query, nothing of the old Cover Flow page), what paints (the iPod title bar, white, the shared depth renderer's frame, the album and artist under the centre cover, seven
covers), the wheel (one album a step, the tiers on a long list, the hard stop at the ends), the slide's animation on the page's ONE timer (set to 33 ms in place while it slides
and decodes, back to 500 ms), the centre button (the album's tracks, a track plays), MENU on every level, the skip keys, and the failure paths. Paint never queries."""
import os, re
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)

ip = sibling('ipod')
CX, CY, STEP_DEG, BARH = ip.CX, ip.CY, ip.STEP_DEG, ip.BARH
FH, ART, TICK, FAST = O['IPCF_FRAME_H'], O['ART_SIZE'], O['IP_TICK_MS'], O['IPCF_FRAME_MS']
RET_REPEAT = O['RET_REPEAT']
MID = O['IPCF_TOP'] + O['IPCF_ART'] // 2   # the frame row through the middle of the centre cover
MODS = lambda calls: [c[2] for c in calls if c[0] == 'timer_modify']   # the page timer's intervals set in place (patch/ipod.c ip_retime)
SWAPS = lambda calls: [c for c in calls if c[0] in ('timer_add', 'timer_remove')]   # never while the page lives: the one timer is modified, not replaced
TRACKS_OF = {}


def colour(i):
    """Album i's cover: a flat colour whose red : green ratio is its own (so a dimmed copy is still told apart)."""
    i %= 12
    return (40 + 18 * i, 250 - 18 * i, 90)


def machine(n=12, art=True, **kw):
    """The iPod page's machine with n albums (Artist i / Album i), each with a cached cover of its own colour, open on the main menu with the page timer running."""
    m = ip.machine(albums=[(f'Album {i}', f'Artist {i}') for i in range(n)], **kw)
    for i, r in enumerate(m.class_lists[O['CLASS_ALBUMS']]):   # the records ip.machine made carry the artist's name given there: Artist i
        pass
    if art:
        for i in range(n):
            path = art_file(album_key(f'Artist {i}', f'Album {i}'))
            m.present.add(path); m.files[path] = 4096
            m.images['file://' + path] = (ART, ART, bytes(colour(i) + (255,)) * (ART * ART))
    m.open(); m.timers = []
    m.clock = 5000
    m.call(PSYMS['ip_first'], a0=0, count=40000000)   # the 50 ms one-shot: the 500 ms tick is armed
    m.timers = []
    return m


def enter(m):
    m.tap(CX, CY)
    m.tap(CX, CY)
    return m


def paint(m):
    """One paint of the screen: (texts, fills, blits, the names of the calls it made)."""
    if m.call(PSYMS['ip_render_active']):
        m.clock += 301
        m.call(PSYMS['ip_tick'], count=80000000)
    ev = m.alloc(0x40); m.u.mem_write(ev, bytes(0x40)); m.setword(ev + O['EVENT_PAINT_CANVAS'], m.canvas)
    m.texts, m.fills, m.blits, m.text_styles = [], [], [], []
    m.call(PSYMS['ip_on_paint'], a0=0, a1=ev, count=80000000)
    return list(m.texts), list(m.fills), list(m.blits), m.names()


def frame(m):
    """(data address, w, h) of the Cover Flow frame bitmap."""
    return next((d, w, h) for d, w, h in reversed(list(m.bitmaps.values())) if (w, h) == (320, FH))


def px(m, x, y):
    d, w, _ = frame(m)
    v = m.word(d + (y * w + x) * 4)
    return v & 255, v >> 8 & 255, v >> 16 & 255


def state(m):
    """(pos, target) of the slide, 16.16 albums (the first two words of ipcf_c's struct)."""
    return m.s32(PSYMS['ipcf']), m.s32(PSYMS['ipcf'] + 4)


def tick(m, n=1):
    """n timer callbacks, 33 ms apart on the clock; the calls of all of them, and the last return value."""
    calls, ret = [], None
    for _ in range(n):
        m.clock += 33
        ret = m.call(PSYMS['ip_tick'], a0=0, count=60000000)
        calls += m.calls
    m.calls = calls
    return ret


def settle(m, limit=120):
    """Ticks until one does nothing (the slide is on its target, no cover was decoded): the page is then at its slow pace. (The ticks, the calls.)"""
    calls = []
    for n in range(1, limit + 1):
        tick(m); calls += m.calls
        if state(m)[0] == state(m)[1] and not any(c[0] == 'widget_load_image' for c in m.calls): return n, calls
    return limit, calls


def rested(m):
    """The page timer is at its slow pace and idle: one more tick changes no interval (at the fast pace an idle tick would set 500 ms) and repeats."""
    ret = tick(m)
    return ret == RET_REPEAT and not [c for c in m.calls if c[0] in ('timer_add', 'timer_remove', 'timer_modify')]


def captions(m):
    texts = paint(m)[0]
    return [t for t, r in texts if r[1] in (O['IPCF_CAP_Y'], O['IPCF_CAP_Y'] + O['IPCF_CAP_H'])]


def centre_album(m):
    """The centre cover's own colour index and the caption's album, after a paint."""
    cap = captions(m)
    return cap[0] if cap else None


def sel_of(m): return state(m)[1] >> 16


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------
def enter_tests(ctx):
    expect = ctx.expect
    m = machine()
    enter(m)
    c = m.calls
    expect(('loadLocalClassList', O['CLASS_ALBUMS']) in c, 'the Cover Flow row: the stock albums query')
    expect(('bitmap_create_ex', 320, FH) in c and any(x[0] == 'calloc' and x[1] == 9 * ART * ART * 4 and x[2] for x in c), f'a 320 x {FH} frame and the nine textures (eight slots and the placeholder) are made')
    expect(not m.opened and 'coverflow_open' not in m.names() and 'window_open' not in m.names(), 'the old full-screen Cover Flow page does not open: the screen is the iPod\'s')
    expect(MODS(c)[-1:] == [FAST] and not SWAPS(c), f'the page\'s one timer goes to 33 ms in place (timer_modify; not replaced, not added to) ({MODS(c)})')
    texts, fills, blits, names = paint(m)
    expect(fills[0][1:] == (0, 0, 320, 240) and fills[0][0] == 0xffffffff, 'the screen is white first')
    expect(len(blits) == 1 and blits[0][1] == (0, 0, 320, FH) and blits[0][2] == (0, O['IPCF_FRAME_Y'], 320, FH) and O['IPCF_FRAME_Y'] == BARH, f'one picture: the frame, 320 x {FH}, right under the title bar ({blits})')
    expect(O['IPCF_BG'] == 0xffffff and not any(f[0] == 0xff000000 and f[3] > 100 for f in fills), 'the shelf is white: no black fill of the screen')
    expect(['Cover Flow'] == [t for t, r in texts if r[1] < BARH] and any(f[1:] == (0, BARH - 1, 320, 1) for f in fills), 'the iPod title bar: "Cover Flow" (no clock)')
    body = [(t, r, s) for (t, r), s in zip(texts, m.text_styles) if r[1] >= BARH]
    expect([(t, r[1]) for t, r, s in body] == [('Album 0', O['IPCF_CAP_Y']), ('Artist 0', O['IPCF_CAP_Y'] + O['IPCF_CAP_H'])], f'the album over the artist under the covers ({[(t, r[1]) for t, r, s in body]})')
    expect({s for t, r, s in body} == {'label_ip_row'}, f'in the list rows\' dark text style, not the white one ({[s for t, r, s in body]})')
    ys = [r for t, r, s in body]
    expect(all(r[0] >= 12 and r[0] + r[2] <= 308 for r in ys) and ys[0][0] + ys[0][2] // 2 in range(158, 163), f'both lines centred ({ys})')
    # the paint made no query, no file access, no allocation, no timer
    bad = [n for n in names if n in ('loadLocalClassList', 'loadAlbumdetailList', 'loadAlbumList', 'widget_load_image', 'timer_add', 'timer_remove', 'timer_modify', 'bitmap_create_ex', 'calloc', 'fopen', 'open', 'stat')]
    expect(not bad, f'paint never queries, decodes, allocates or touches the timer ({bad})')
    expect(px(m, 160, MID) != colour(0), 'the cover is not decoded yet when the first frame paints: the placeholder stands in')
    # the timer decodes one wanted cover a tick, nearest first, and repaints
    loads, swaps, rets = [], [], []
    for i in range(8):
        rets.append(tick(m)); loads += [x[1] for x in m.calls if x[0] == 'widget_load_image']; swaps += MODS(m.calls) + SWAPS(m.calls)
    expect(len(loads) == 4 and all(l.endswith('-168.jpg') for l in loads), f'one cover decoded a tick, the centre and three ahead (album 0 has no covers behind it): four in all ({len(loads)})')
    expect(loads[0].endswith(f'{album_key("Artist 0", "Album 0"):08x}-168.jpg') and loads[1].endswith(f'{album_key("Artist 1", "Album 1"):08x}-168.jpg'), 'the centre album first, then the next ahead')
    expect(rets == [RET_REPEAT] * 8 and swaps == [TICK], f'nothing wanted any more: the tick that decoded the last cover sets the one timer back to 500 ms in place, and it repeats ({rets}, {swaps})')
    paint(m)
    expect(px(m, 160, MID) == colour(0), f'the centre cover is album 0\'s ({px(m, 160, MID)})')
    # seven covers show: the centre and three either side; the ones four out do not
    m = machine(); enter(m)
    for _ in range(3): m.turn(0, STEP_DEG + 3)
    settle(m)
    for _ in range(12): tick(m)
    paint(m)
    def album_at(x, y):
        r, g, b = px(m, x, y)
        dr, dg = 255 - r, 255 - g   # the distance from white: a faded cover is transparent over white, which keeps the ratio of these
        if dr + dg < 12: return None
        ratio = dr / (dr + dg)
        return min(range(12), key=lambda i: abs(ratio - (255 - colour(i)[0]) / (510 - colour(i)[0] - colour(i)[1])))
    seen = {}
    for x in range(320):
        a = album_at(x, MID)
        if a is not None: seen[a] = seen.get(a, 0) + 1
    expect(sel_of(m) == 3 and set(k for k, v in seen.items() if v >= 3) == set(range(0, 7)), f'on album 3 the row of covers is albums 0 .. 6: three either side ({seen})')
    # the centre cover is IPCF_ART px: wide, and it is the largest
    centre_w = sum(1 for x in range(320) if album_at(x, MID) == 3)
    expect(centre_w == O['IPCF_ART'] and px(m, 160, MID) == colour(3), f'the centre cover is IPCF_ART ({O["IPCF_ART"]}) px wide, facing the viewer ({centre_w})')
    # the reflection: below the cover, paler (towards white), fading out inside the frame
    far = lambda p: 765 - sum(p)   # how far from white
    below = O['IPCF_TOP'] + O['IPCF_ART']
    expect(0 < far(px(m, 160, below + 4)) < far(colour(3)) and far(px(m, 160, below + O['IPCF_REFLECT'] - 8)) < far(px(m, 160, below + 4)) and below + O['IPCF_REFLECT'] <= FH,
           'a reflection under the centre cover, fading out into the white')
    expect(px(m, 160, 0) == px(m, 2, 0) == px(m, 160, FH - 1) == (255, 255, 255), 'white above the covers and below the reflection')
    expect(px(m, 0, MID) != (255, 255, 255) and px(m, 319, MID) != (255, 255, 255), 'as on the iPod, the side covers run to the screen edges')
    # empty library
    m = machine(0); enter(m)
    texts = [t for t, r in paint(m)[0] if r[1] >= BARH]
    expect(texts == [m.tr('No songs')], 'an empty library: "No songs", no crash')
    m.turn(0, 60); m.tap(CX, CY)
    expect('loadAlbumdetailList' not in m.names(), 'and nothing opens')


def wheel_tests(ctx):
    expect = ctx.expect
    m = machine(); enter(m)
    m.turn(0, STEP_DEG * 3 + 4)
    expect(sel_of(m) == 3, f'three steps of 15 degrees: album 3 ({sel_of(m)})')
    m.turn(0, -(STEP_DEG * 2 + 4))
    expect(sel_of(m) == 1, 'two back: album 1')
    expect(centre_album(m) == 'Album 0', 'the caption follows the slide, not the cursor: still album 0 before a tick')
    settle(m)
    expect(centre_album(m) == 'Album 1', 'and album 1 once it has slid')
    # one album a step: a single step moves the target by exactly one
    m = machine(); enter(m); settle(m)
    for want in (1, 2, 3):
        m.turn(0, STEP_DEG + 2)
        expect(sel_of(m) == want, f'one 16 degree turn: one album ({want})')
        settle(m)
    # hard stops
    m = machine(5); enter(m); settle(m)
    m.calls = []; calls = []
    for _ in range(4): m.turn(0, -STEP_DEG * 2); calls += m.calls
    expect(sel_of(m) == 0 and state(m) == (0, 0) and not [c for c in calls if c[0] in ('timer_add', 'timer_remove')], 'turning back at the first album: nothing moves, no timer touched')
    for _ in range(4): m.turn(0, STEP_DEG * 4)
    expect(sel_of(m) == 4, 'the last album stops it (no wrap)')
    settle(m)
    calls = []
    m.turn(0, STEP_DEG * 3); calls += m.calls
    expect(sel_of(m) == 4 and state(m) == (4 << 16, 4 << 16) and not [c for c in calls if c[0] in ('timer_add', 'timer_remove')], 'on past the last: a hard stop, the slide and the timer untouched')
    # a short list moves one album a step at any speed; a long one climbs the tiers
    m = machine(12); enter(m); settle(m)
    d = ip.Drag(m, 0); prev = 0; deltas = []
    for _ in range(40):
        d.go(6, 16); s = sel_of(m); deltas.append(s - prev); prev = s
    expect(max(deltas) == 1 and prev == 11, f'12 albums (16 or fewer): one a step at 375 deg/s ({max(deltas)})')
    m = machine(400, art=False); enter(m); settle(m)
    d = ip.Drag(m, 0); prev = 0; deltas = []
    for _ in range(30): d.go(6, 16)
    expect(sel_of(m) == 12, f'400 albums, a fast turn: the first half second is one album per 15 degrees ({sel_of(m)})')
    prev = 12
    for _ in range(300):
        d.go(6, 16); s = sel_of(m); deltas.append(s - prev); prev = s
        if s >= 399: break
    expect(set(deltas) <= {0, 1, 2, 3, 5, 8, 13, 21, 34} and {1, 2, 3, 5, 8} <= set(deltas), f'held fast the albums a step climb the tiers ({sorted(set(deltas))})')
    expect(max(deltas) == 34 or prev == 399, f'to 34 ({max(deltas)})')
    # a long jump starts the slide at most IPCF_NEAR albums short of the target
    pos, target = state(m)
    expect(target - pos <= O['IPCF_NEAR'] << 16 or target == pos, f'the slide starts within {O["IPCF_NEAR"]} albums of a far target ({(target - pos) / 65536})')
    # the stock list stays the albums list: nothing re-queried by a step
    m = machine(); enter(m); m.calls = []; m.turn(0, STEP_DEG * 2 + 4)
    expect('loadLocalClassList' not in m.names() and 'loadAlbumdetailList' not in m.names(), 'a wheel step queries nothing')


def anim_tests(ctx):
    expect = ctx.expect
    m = machine(); enter(m); settle(m)
    for _ in range(10): tick(m)
    m.calls = []
    m.turn(0, STEP_DEG + 3)
    calls = list(m.calls)
    expect(MODS(calls)[-1:] == [FAST] and set(MODS(calls)) <= {FAST, O['IP_DRIFT_MS']} and not SWAPS(calls), f'a step sets the page\'s one timer from 500 to 33 ms in place (a touch on the MENU sector first watches for its long press at 100 ms) ({MODS(calls)})')
    pos0, target = state(m)
    expect(target == 1 << 16 and pos0 == 0, 'the slide is at album 0 and goes to album 1')
    # the slide: monotone, eases out, lands exactly, ends with the swap back
    poss, rets, adds = [pos0], [], []
    for i in range(60):
        ret = tick(m); rets.append(ret); poss.append(state(m)[0]); adds += MODS(m.calls) + SWAPS(m.calls)
        if adds: break
    expect(all(a < b for a, b in zip(poss, poss[1:])) and poss[-1] == 1 << 16, f'the slide moves forward every tick and lands exactly on album 1 ({poss[:3]} .. {poss[-1]})')
    steps = [b - a for a, b in zip(poss, poss[1:])]
    expect(len(poss) - 1 <= 15 and steps[0] > steps[-2], f'it eases out and takes about 150 ms ({len(poss) - 1} ticks, first step {steps[0]}, last but one {steps[-2]})')
    expect(rets == [RET_REPEAT] * len(rets) and adds == [TICK],
           f'the timer repeats while it slides; the tick that lands sets it back to 500 ms in place ({adds})')
    # frames: the picture changes with the position, and only then
    m = machine(); enter(m); settle(m)
    for _ in range(10): tick(m)
    paint(m); a = bytes(m.u.mem_read(frame(m)[0], 320 * FH * 4))
    paint(m); b = bytes(m.u.mem_read(frame(m)[0], 320 * FH * 4))
    expect(a == b and 'bitmap_lock_buffer_for_write' not in m.names(), 'an unchanged position reuses the frame (no render)')
    m.turn(0, STEP_DEG + 3); tick(m)
    paint(m); c = bytes(m.u.mem_read(frame(m)[0], 320 * FH * 4))
    expect(c != a and 'bitmap_lock_buffer_for_write' in m.names(), 'a slide tick renders a new frame')
    # a long jump is near its target at once; decoding follows the slide, one cover a tick
    m = machine(60); enter(m); settle(m)
    for _ in range(10): tick(m)
    d = ip.Drag(m, 0)
    for _ in range(60): d.go(6, 16)
    pos, target = state(m)
    expect(target - pos <= O['IPCF_NEAR'] << 16, f'a far target: the slide starts {(target - pos) / 65536:.1f} albums short of it')
    m.loads.clear()
    n = 0
    for _ in range(40):
        tick(m); n += 1
        expect(len(m.loads) <= n, 'at most one decode per tick')
        if state(m)[0] == state(m)[1]: break
    for _ in range(30): tick(m)
    paint(m)
    expect(state(m)[0] == state(m)[1] and px(m, 160, MID) == colour(sel_of(m)), f'it lands on the target, album {sel_of(m)}, with its cover')
    expect(rested(m), 'and the page timer is back at 500 ms')


def track_tests(ctx):
    expect = ctx.expect
    m = machine(); enter(m)
    m.turn(0, STEP_DEG * 2 + 3); settle(m)
    m.tap(CX, CY)
    expect(('loadAlbumdetailList', O['CLASS_ALBUMS'], 'Album 2') in m.calls, 'the centre button: the album\'s tracks, queried as the Albums level does')
    texts, fills, blits, names = paint(m)
    rows = ip.rows_of(texts)
    expect(rows == ['Album 2 0', 'Album 2 1', 'Album 2 2'], f'an iPod list of the album\'s tracks ({rows})')
    expect(any(t == 'Album 2' and r[1] < BARH for t, r in texts), 'with the iPod title bar, naming the album')
    expect(FAST not in MODS(m.calls) and not SWAPS(m.calls), 'the page is at its slow pace on the list')
    # a track: wheel one, centre plays it
    m.turn(0, STEP_DEG + 3)
    m.tap(CX, CY)
    sp = [c for c in m.calls if c[0] == 'start_player']
    expect(sp == [('start_player', 1, 0xff10, O['PLAY_MODE'])] and ('loadSongList', 'Album 2-1.flac', 0, 0xff10) in m.calls, f'the centre button on a track plays it (the Albums level\'s path) ({sp})')
    expect(m.played is not None and m.played[1] == 1, 'the queue is the album, at the track')
    texts = paint(m)[0]
    expect('Now Playing' in [t for t, _ in texts], 'and the iPod shows Now Playing')
    # MENU: Now Playing -> tracks -> Cover Flow on the same album -> the iPod main menu
    x, y = m.polar(0, 85); m.tap(x, y)
    expect(ip.rows_of(paint(m)[0]) == ['Album 2 0', 'Album 2 1', 'Album 2 2'], 'MENU from Now Playing: the tracks again')
    m.tap(x, y)
    expect(('loadLocalClassList', O['CLASS_ALBUMS']) in m.calls and sel_of(m) == 2, 'MENU from the tracks: Cover Flow, the albums read again, on the same album')
    texts = paint(m)[0]
    texts = [t for t, r in texts if r[1] >= BARH]
    expect(texts == ['Album 2', 'Artist 2'] and state(m) == (2 << 16, 2 << 16), f'Cover Flow shows album 2 again ({texts})')
    for _ in range(14): tick(m)
    paint(m)
    expect(px(m, 160, MID) == colour(2), 'with its cover (the textures were kept while the tracks showed)')
    m.calls = []
    m.tap(x, y)
    expect(any(c[0] == 'bitmap_destroy' for c in m.calls) and any(c[0] == 'free' for c in m.calls), 'MENU from Cover Flow: the iPod main menu; the frame and the textures are freed')
    texts = paint(m)[0]
    expect('Music' in [t for t, _ in texts] and ip.rows_of(texts) == [m.tr(k) for k in ip.MUSIC_KEYS], 'the Music menu is back, the Cover Flow row selected')
    expect(m.names().count('navigator_back') == 0, 'the page stays open')
    m.tap(x, y)
    m.tap(x, y)
    expect(m.names().count('navigator_back') == 1, 'MENU on the main menu closes the page')
    # a tap in the corner of the wheel / the ring: |<< >>| >||
    m = machine(); enter(m)
    for deg, want in ((90, 'next'), (270, 'prev'), (180, 'playpause')):
        m.cmds = []
        x, y = m.polar(deg, 85); m.tap(x, y)
        expect(m.cmds and m.cmds[0][0] == want, f'in Cover Flow a tap at {deg} degrees is {want}')
    expect(sel_of(m) == 0 and state(m) == (0, 0), 'and they do not move the slide')
    # MENU while the slide is still moving: the page timer is back at 500 ms
    m = machine(); enter(m); settle(m)
    m.turn(0, STEP_DEG * 3 + 3); m.calls = []
    x, y = m.polar(0, 85); m.tap(x, y)
    mods = MODS(m.calls)
    expect(mods and mods[-1] in (TICK, O['IP_DRIFT_MS'], O['IP_PAN_MS']) and not SWAPS(m.calls), f'MENU while it slides: the one timer leaves 33 ms in place, for the main menu\'s pace ({mods})')
    # an album with no cached cover shows the placeholder, the rest still work
    m = machine(4, art=False); enter(m)
    for _ in range(10): tick(m)
    expect(px(m, 160, MID) != colour(0) and ('widget_load_image', 'file://' + art_file(album_key('Artist 0', 'Album 0'))) not in m.calls, 'no cached cover: the placeholder, no decode of a file that is not there')
    settle(m)
    expect(rested(m), 'and the timer still settles at 500 ms')


def life_tests(ctx):
    expect = ctx.expect
    m = machine(); m.calloc_fail = True
    enter(m)
    expect(m.opened == ['coverflow_open'] and 'bitmap_destroy' in m.names(), f'no memory for the textures: the frame goes again and the existing Cover Flow page opens instead ({m.opened})')
    m = machine(); m.bitmap_ok = False
    enter(m)
    expect(m.opened == ['coverflow_open'], 'no frame bitmap: the same fallback')
    m = machine(); enter(m)
    for _ in range(3): tick(m)
    m.calls = []; m.fire(O['EVT_WINDOW_TO_BG'], ip.WIN)
    expect(('timer_remove', 0x777) in m.calls, 'to the background (a window above, the screen off): the timer goes')
    m.calls = []; m.fire(O['EVT_WINDOW_TO_FG'], ip.WIN)
    expect(('timer_add', PSYMS['ip_first'], O['IP_FIRST_MS']) in m.calls and ('loadLocalClassList', O['CLASS_ALBUMS']) in m.calls, 'back in front: the albums are read again and the timer is armed again')
    m.timers = []; m.call(PSYMS['ip_first'], a0=0, count=40000000)
    expect(any(c[:2] == ('timer_add', PSYMS['ip_tick']) and c[2] in (TICK, FAST) for c in m.calls), 'the 50 ms one-shot starts the tick again (at the pace Cover Flow wants)')
    tick(m, 4)
    texts = [t for t, r in paint(m)[0] if r[1] >= BARH]
    expect(texts == ['Album 0', 'Artist 0'], 'and the screen paints again')
    m.calls = []; m.fire(O['EVT_DESTROY'], ip.WIN)
    expect(any(c[0] == 'bitmap_destroy' for c in m.calls) and any(c[0] == 'free' for c in m.calls) and ('timer_remove', 0x777) in m.calls, 'destroy: the timer, the frame and the textures go')
    # another page can replace the stock query result. This page owns its album snapshot, so its
    # current captions and frame stay stable instead of reading the unrelated list.
    m = machine(); enter(m)
    for _ in range(14): tick(m)
    m.setword(ip.SHOWLIST, m.new_deque([m.record(album='Other', artist='X', path='/x.flac', rid=900)]))
    texts, fills, blits, names = paint(m)
    body = [t for t, r in texts if r[1] >= BARH]
    expect(body == ['Album 0', 'Artist 0'] and len(blits) == 1 and 'Other' not in body,
           f'a different page queried the stock list: Cover Flow keeps its owned album snapshot ({body}, {len(blits)} frame blits)')


def i18n_tests(ctx):
    expect = ctx.expect
    src = open(os.path.join(ROOT, 'patch', 'ipod_cf.c')).read()
    keys = set(re.findall(r'TR\("([^"]+)"\)', src))
    missing = [k for k in keys if k not in pod_i18n.TEXT and k not in pod_i18n.STOCK]
    expect(keys == {'No songs'} and not missing, f'the screen\'s texts are keys that exist ({keys}, missing {missing})')
    # the geometry in offsets.inc is one shelf: the three caption lines and the reflection fit the 240 px screen, the frame the covers and their reflection
    expect(abs((O['IPCF_FRAME_Y'] + O['IPCF_TOP'] + O['IPCF_ART'] // 2) - 106) <= 2 and O['IP_SCREEN_H'] - (O['IPCF_CAP_Y'] + 2 * O['IPCF_CAP_H']) >= 4, 'the centre cover is centred about 106 px down the 240 px screen (18 px of air under the title bar), the captions end at least 4 px above its bottom edge')
    top, art, refl, cap, caph = O['IPCF_TOP'], O['IPCF_ART'], O['IPCF_REFLECT'], O['IPCF_CAP_Y'], O['IPCF_CAP_H']
    expect(top + art + refl <= O['IPCF_FRAME_H'] and O['IPCF_FRAME_Y'] + O['IPCF_FRAME_H'] <= O['IP_SCREEN_H'] and top + art <= cap - O['IPCF_FRAME_Y'] and cap + 2 * caph <= O['IP_SCREEN_H'],
           'the covers and their reflection end inside the frame, the frame inside the screen, the covers above the captions (drawn over the reflection, as on the iPod), the two caption lines inside the 240 px screen')
    expect(O['IPCF_FRAME_MS'] < O['IP_TICK_MS'] and O['IPCF_NEAR'] < 7, 'the slide runs at 33 ms against the 500 ms rest; a far jump lands inside the ring of seven')


SECTIONS = [enter_tests, wheel_tests, anim_tests, track_tests, life_tests, i18n_tests]


def run(ctx):
    for f in SECTIONS: f(ctx)
