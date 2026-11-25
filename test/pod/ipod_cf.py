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
    ev = m.paint_event()
    m.texts, m.fills, m.blits, m.text_styles = [], [], [], []
    m.call(PSYMS['ip_on_paint'], a0=0, a1=ev, count=80000000)
    return list(m.texts), list(m.fills), list(m.blits), m.names()


def album_px(m, x, y=MID):
    """The album whose cover shows at frame pixel (x, y) by its red : green ratio (a faded cover keeps it over white), None on the background."""
    r, g, b = px(m, x, y)
    dr, dg = 255 - r, 255 - g
    if dr + dg < 12: return None
    ratio = dr / (dr + dg)
    return min(range(12), key=lambda i: abs(ratio - (255 - colour(i)[0]) / (510 - colour(i)[0] - colour(i)[1])))


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


def flip_state(m):
    """(flip, flip_to) of the 3D album flip (0 cover .. 256 card)."""
    return m.s32(PSYMS['ipcf'] + 20), m.s32(PSYMS['ipcf'] + 28)


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
    """Ticks until one does nothing (the slide is on its target, no cover going, no cover was decoded): the page is then at its slow pace. (The ticks, the calls.)"""
    calls = []
    for n in range(1, limit + 1):
        tick(m); calls += m.calls
        if state(m)[0] == state(m)[1] and not m.call(PSYMS['ipcf_going']) and not any(c[0] == 'widget_load_image' for c in m.calls): return n, calls
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
    expect(('bitmap_create_ex', 320, FH) in c and any(x[0] == 'calloc' and x[1] == (9 * ART * ART + O['IPCF_CARD_W'] * O['IPCF_CARD_H']) * 4 and x[2] for x in c), f'a 320 x {FH} frame, the nine textures (eight slots and the placeholder) and the card\'s face are made')
    expect(not m.opened and 'coverflow_open' not in m.names() and 'window_open' not in m.names(), 'the old full-screen Cover Flow page does not open: the screen is the iPod\'s')
    # something playing: the shelf opens on its album at once, no slide; the wheel goes on from there
    p = machine()
    p.play([p.record(album='Album 5', artist='Artist 5', path='Album 5-0.flac', title='Album 5 0')], 0)
    enter(p)
    for _ in range(12): tick(p)
    expect(state(p) == (5 << 16, 5 << 16) and 'Album 5' in captions(p) and px(p, 160, MID) == colour(5),
           f'the playing album is in the centre on entry ({state(p)}, {captions(p)})')
    p.turn(0, STEP_DEG + 3); settle(p)
    expect(sel_of(p) == 6, f'and a step goes on to the next album ({sel_of(p)})')
    expect(MODS(c)[-1:] == [FAST] and not SWAPS(c), f'the page\'s one timer goes to 33 ms in place (timer_modify; not replaced, not added to) ({MODS(c)})')
    texts, fills, blits, names = paint(m)
    expect(fills[0][1:] == (0, 0, 320, 240) and fills[0][0] == 0xffffffff, 'the screen is white first')
    expect(len(blits) == 1 and blits[0][1] == (0, 0, 320, FH) and blits[0][2] == (0, O['IPCF_FRAME_Y'], 320, FH) and O['IPCF_FRAME_Y'] == BARH, f'one picture: the frame, 320 x {FH}, right under the title bar ({blits})')
    expect(O['IPCF_BG'] == 0xffffff and not any(f[0] == 0xff000000 and f[3] > 100 for f in fills), 'the shelf is white: no black fill of the screen')
    expect(not [t for t, r in texts if r[1] < BARH], 'no title bar while the page opens: it drops in after')
    m2 = enter(machine())
    for _ in range(2): m2.clock += 301; m2.call(PSYMS['ip_tick'], count=80000000)   # the split, then the title bar's drop
    t2, f2, _, _ = paint(m2)
    expect(['Cover Flow'] == [t for t, r in t2 if r[1] < BARH] and any(f[1:] == (0, BARH - 1, 320, 1) for f in f2), 'then the iPod title bar: "Cover Flow" (no clock)')
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
    for i in range(14):   # (the title bar waits IP_BAR_WAIT_MS and drops meanwhile)
        rets.append(tick(m)); loads += [x[1] for x in m.calls if x[0] == 'widget_load_image']; swaps += MODS(m.calls) + SWAPS(m.calls)
    expect(len(loads) == 4 and all(l.endswith('-168.jpg') for l in loads), f'one cover decoded a tick, the centre and three ahead (album 0 has no covers behind it): four in all ({len(loads)})')
    expect(loads[0].endswith(f'{album_key("Artist 0", "Album 0"):08x}-168.jpg') and loads[1].endswith(f'{album_key("Artist 1", "Album 1"):08x}-168.jpg'), 'the centre album first, then the next ahead')
    expect(rets == [RET_REPEAT] * 14 and swaps == [TICK], f'nothing wanted any more: the tick that decoded the last cover sets the one timer back to 500 ms in place, and it repeats ({rets}, {swaps})')
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
    expect(sel_of(m) == 3, f'three steps of 20 degrees: album 3 ({sel_of(m)})')
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
    expect(sel_of(m) == 9, f'400 albums, a fast turn: the first half second is one album per 20 degrees ({sel_of(m)})')
    prev = sel_of(m)
    for _ in range(300):
        d.go(6, 16); s = sel_of(m); deltas.append(s - prev); prev = s
        if s >= 399: deltas.pop(); break  # the last step is clamped at the end
    expect(set(deltas) <= {0, 1, 2, 3, 5} and {1, 2, 3, 5} <= set(deltas), f'held fast the albums a step climb the capped tiers ({sorted(set(deltas))})')
    expect(max(deltas) == 5 or prev == 399, f'capped at 5 ({max(deltas)})')
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
    # the slide: monotone, smooth spring (eases in and out), lands exactly, ends with the swap back
    poss, rets, adds, folds = [pos0], [], [], []
    for i in range(60):
        ret = tick(m); rets.append(ret); poss.append(state(m)[0]); adds += MODS(m.calls) + SWAPS(m.calls)
        folds.append(m.s32(PSYMS['ipcf'] + 12))
        if adds: break
    expect(max(folds) == 0, f'a single step never folds the shelf: its peak speed stays under the fold threshold ({max(folds)})')
    expect(all(a < b for a, b in zip(poss, poss[1:])) and poss[-1] == 1 << 16, f'the slide moves forward every tick and lands exactly on album 1 ({poss[:3]} .. {poss[-1]})')
    steps = [b - a for a, b in zip(poss, poss[1:])]
    peak = max(steps)
    expect(len(poss) - 1 <= 25 and steps[0] < peak and steps[-2] < peak, f'it eases in and eases out like a spring ({len(poss) - 1} ticks, first {steps[0]}, peak {peak}, last but one {steps[-2]})')
    expect(rets == [RET_REPEAT] * len(rets) and adds == [TICK],
           f'the timer repeats while it slides; the tick that lands sets it back to 500 ms in place ({adds})')
    # steps in a row glide: the shelf keeps an even speed between steps instead of easing to a near stop on each album
    m = machine(24, art=False); enter(m); settle(m)
    for _ in range(10): tick(m)
    poss = [state(m)[0]]
    for _ in range(16):
        m.turn(0, STEP_DEG + 1)
        for _ in range(2): tick(m); poss.append(state(m)[0])
    moves = [b - a for a, b in zip(poss, poss[1:])][12:]
    fold = m.s32(PSYMS['ipcf'] + 12)
    expect(fold < 64, f'a steady turn keeps the covers turned, as on the iPod ({fold} of 256)')
    settle(m); tick(m, 30)
    expect(m.s32(PSYMS['ipcf'] + 12) == 0, 'at rest it is open again, the last album facing front')
    expect(min(moves) > 0 and min(moves) * 10 >= max(moves) * 7, f'a steady turn, one album every 66 ms: the shelf moves evenly ({[round(v / 65536, 2) for v in moves]}, album {sel_of(m)})')
    # a fast burst left behind: the release rush lies the shelf flat for a moment, then it opens as it slows
    m = machine(40, art=False); enter(m); settle(m)
    for _ in range(10): tick(m)
    for _ in range(8): m.turn(0, STEP_DEG + 1)
    folds = []
    for _ in range(40): tick(m); folds.append(m.s32(PSYMS['ipcf'] + 12))
    expect(max(folds) > 128 and folds[-1] == 0, f'the rush folds the shelf at its peak and opens it again ({folds})')
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
    for _ in range(60):
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
    m.canvas = m.canvas_mem = m.alloc(0x80)   # a canvas in memory: the card's face reads the font the styles put there
    m.turn(0, STEP_DEG * 2 + 3); settle(m)
    for _ in range(12): tick(m)
    m.calls = []
    m.tap(CX, CY)
    expect(('loadAlbumdetailList', O['CLASS_ALBUMS'], 'Album 2') in m.calls, 'the centre button: the album\'s tracks, queried as the Albums level does')
    expect(flip_state(m) == (0, 256) and MODS(m.calls)[-1:] == [FAST] and not SWAPS(m.calls), f'the centre button starts the 3D flip in place on the 33 ms timer ({flip_state(m)}, {MODS(m.calls)})')
    _, _, blits0, _ = paint(m)
    expect([b[2] for b in blits0] == [(0, O['IPCF_FRAME_Y'], 320, FH)] and abs(px(m, 160, MID)[0] * colour(2)[1] - px(m, 160, MID)[1] * colour(2)[0]) < 2000,
           f'before the first tick the flip frame at 0 is the shelf\'s cover, no blank frame ({blits0})')
    # mid-flip paints the 3D flip frame without switching to a separate full-screen list
    tick(m, 4)
    expect(0 < flip_state(m)[0] < 256, f'mid-flip: progress between 0 and 256 ({flip_state(m)})')
    _, _, blits_mid, _ = paint(m)
    expect(len(blits_mid) == 1 and blits_mid[0][2] == (0, O['IPCF_FRAME_Y'], 320, FH), f'mid-flip blits the 3D perspective flip frame ({blits_mid})')
    # the back half turns the card's own picture: its track titles are in it, though nothing is drawn on the canvas but the frame
    while flip_state(m)[0] < 200: tick(m)
    texts_mid, _, _, _ = paint(m); d, w, h = frame(m); raw = m.u.mem_read(d, w * h * 4)
    cy = O['IPCF_CARD_Y'] - O['IPCF_FRAME_Y']
    ink = sum(1 for y in range(cy + O['IPCF_CARD_HDR'], min(h, cy + O['IPCF_CARD_H'])) for x in range(O['IPCF_CARD_X'], O['IPCF_CARD_X'] + O['IPCF_CARD_W'])
              if max(raw[(y * w + x) * 4:(y * w + x) * 4 + 3]) < 80)
    expect(ink > 100 and not [t for t, r in texts_mid if r[1] >= BARH], f'the turning card carries its track titles ({ink} dark pixels in its rows), none drawn on the canvas ({texts_mid})')
    # settle the flip: card opens at 256 and timer drops back to 500 ms
    mods = []
    for _ in range(20):
        tick(m); mods += MODS(m.calls)
        if flip_state(m) == (256, 256): break
    expect(flip_state(m) == (256, 256) and mods[-1:] == [TICK] and not SWAPS(m.calls), f'flip lands at 256 and returns the timer to 500 ms ({flip_state(m)}, {mods})')
    texts, fills, blits, names = paint(m)
    expect(any(t == 'Cover Flow' and r[1] < BARH for t, r in texts), 'title bar stays "Cover Flow" while the album is flipped')
    card_texts = [t for _, t in sorted((r[1], t) for t, r in texts if r[1] >= O['IPCF_CARD_Y'])]
    expect(card_texts == ['Album 2', 'Artist 2', 'Album 2 0', 'Album 2 1', 'Album 2 2'], f'flipped card shows album, artist and tracks ({card_texts})')
    expect(any(f[1:] == (O['IPCF_CARD_X'], O['IPCF_CARD_Y'], O['IPCF_CARD_W'], O['IPCF_CARD_HDR'] + 1) for f in fills), 'floating card sky-blue header frame drawn at IPCF_CARD_*')
    expect(len(blits) == 1 and blits[0][2] == (0, O['IPCF_FRAME_Y'], 320, FH), f'side covers stay visible behind the floating card ({blits})')
    # a track: wheel one, centre plays it
    m.turn(0, STEP_DEG + 3)
    m.tap(CX, CY)
    sp = [c for c in m.calls if c[0] == 'start_player']
    expect(sp == [('start_player', 1, 0xff10, O['PLAY_MODE'])] and ('loadSongList', 'Album 2-1.flac', 0, 0xff10) in m.calls, f'the centre button on a track plays it (the Albums level\'s path) ({sp})')
    expect(m.played is not None and m.played[1] == 1, 'the queue is the album, at the track')
    texts = paint(m)[0]
    # the card turns away as one turn with the cover turning in: its right (near) edge first, its axis going left
    while m.s32(PSYMS['ipcf'] + 360) < 80: tick(m)
    paint(m); d, w, h = frame(m); raw = m.u.mem_read(d, w * h * 4)
    hdr = [(x, y) for y in range(h) for x in range(w) if raw[(y * w + x) * 4 + 2] > 200 and raw[(y * w + x) * 4 + 2] > raw[(y * w + x) * 4] + 60]
    xs = [x for x, _ in hdr]; lo, hi = min(xs), max(xs)
    top = lambda c: min(y for x, y in hdr if x == c)
    expect(top(hi) < top(lo) and (lo + hi) // 2 < 140, f'the card turns away right edge near, towards the turn-in column ({lo}..{hi}, tops {top(lo)} {top(hi)})')
    expect('Cover Flow' in [t for t, _ in texts] and flip_state(m) == (0, 0), 'the card gives way to its cover, which goes to Now Playing under Cover Flow\'s title')
    tick(m, (O['IPCF_GO_MS'] + O['IPCF_GO_HOLD_MS']) // FAST + 4)
    expect('Now Playing' in [t for t, _ in paint(m)[0]], 'and the iPod shows Now Playing')
    # MENU: Now Playing -> the cover comes back to Cover Flow on the same album (not the card)
    x, y = m.polar(0, 85); m.calls = []; m.tap(x, y)
    reloaded = ('loadLocalClassList', O['CLASS_ALBUMS']) in m.calls
    texts = [t for t, _ in paint(m)[0]]
    expect(reloaded and sel_of(m) == 2 and flip_state(m) == (0, 0) and 'Album 2' in texts and 'Album 2 0' not in texts,
           f'MENU from Now Playing: the cover comes back to the covers on the same album, not the card ({texts})')
    settle(m)
    # the card again, and MENU on it: flips back to Cover Flow
    m.tap(CX, CY)
    for _ in range(20): tick(m)
    m.calls = []
    m.tap(x, y)
    expect(('loadLocalClassList', O['CLASS_ALBUMS']) in m.calls and sel_of(m) == 2 and flip_state(m) == (255, 0), f'MENU from the card: flips back to Cover Flow on the same album ({flip_state(m)})')
    paint(m); d, w, h = frame(m); raw = m.u.mem_read(d, w * h * 4)
    cy = O['IPCF_CARD_Y'] - O['IPCF_FRAME_Y']
    hdr = sum(1 for y in range(cy, cy + O['IPCF_CARD_HDR']) for x in range(O['IPCF_CARD_X'], O['IPCF_CARD_X'] + O['IPCF_CARD_W'])
              if raw[(y * w + x) * 4 + 2] > 200 and raw[(y * w + x) * 4 + 2] > raw[(y * w + x) * 4] + 60)
    expect(hdr > O['IPCF_CARD_W'] * O['IPCF_CARD_HDR'] // 2, f'the first closing frame still holds the card, no blank gap where it was ({hdr} header pixels)')
    tick(m, 4)
    expect(0 < flip_state(m)[0] < 256, f'closing flip animates back toward 0 ({flip_state(m)})')
    for _ in range(20):
        tick(m)
        if flip_state(m) == (0, 0): break
    expect(flip_state(m) == (0, 0), 'closing flip settles at 0')
    texts = [t for t, r in paint(m)[0] if r[1] >= BARH]
    expect(texts == ['Album 2', 'Artist 2'] and state(m) == (2 << 16, 2 << 16), f'Cover Flow shows album 2 again ({texts})')
    expect(px(m, 160, MID) == colour(2), 'with its cover (the textures were kept while flipped)')
    # turning the wheel during a closing flip cancels it immediately and glides to the next album
    m.tap(CX, CY)
    for _ in range(20): tick(m)
    m.tap(x, y); tick(m, 2)
    expect(0 < flip_state(m)[0] < 256, 'closing flip in flight')
    m.turn(0, STEP_DEG + 3)
    expect(flip_state(m) == (0, 0) and sel_of(m) == 3, f'turning the wheel cancels a closing flip and steps to album 3 ({flip_state(m)}, {sel_of(m)})')
    settle(m)
    # MENU mid-opening-flip smoothly reverses back toward 0
    m.tap(CX, CY); tick(m, 3)
    mid_f = flip_state(m)[0]
    expect(0 < mid_f < 256, f'opening flip in flight ({mid_f})')
    m.tap(x, y)
    expect(flip_state(m) == (mid_f, 0), f'MENU mid-flip reverses from {mid_f} back to 0 ({flip_state(m)})')
    for _ in range(20): tick(m)
    expect(flip_state(m) == (0, 0), 'reversed flip lands back at 0')
    paint(m)
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
    for deg, want in ((90, 'next'), (270, 'prev')):
        m.cmds = []
        x, y = m.polar(deg, 85); m.tap(x, y)
        expect(m.cmds and m.cmds[0][0] == want, f'in Cover Flow a tap at {deg} degrees is {want}')
    expect(sel_of(m) == 0 and state(m) == (0, 0), 'and they do not move the slide')
    # the play key on an album: it plays from its first track, Now Playing opens, MENU comes back to the covers
    m.turn(0, STEP_DEG + 3); settle(m); m.calls = []; m.cmds = []
    x, y = m.polar(180, 85); m.tap(x, y)
    sp = [c for c in m.calls if c[0] == 'start_player']
    expect(sp == [('start_player', 0, 0xff10, O['PLAY_MODE'])] and ('loadSongList', 'Album 1-0.flac', 0, 0xff10) in m.calls and not m.cmds,
           f'in Cover Flow the play key plays the centre album from its first track, no play/pause ({sp}, {m.cmds})')
    expect('Cover Flow' in [t for t, _ in paint(m)[0]] and flip_state(m) == (0, 0), 'and Now Playing opens under Cover Flow\'s title while its cover goes, not flipped')
    FRAME = (0, O['IPCF_FRAME_Y'], 320, FH)
    texts, _, blits, _ = paint(m)
    expect([b[2] for b in blits] == [FRAME] and 'Album 1 0' not in [t for t, _ in texts],
           f'no level slide: the cover goes to Now Playing\'s place in the Cover Flow frame, on the page timer ({[b[2] for b in blits]}, {texts})')
    tick(m, O['IPCF_GO_MS'] // FAST + 2)
    texts, _, blits, _ = paint(m)
    expect([b[2] for b in blits] == [FRAME] and 'Cover Flow' in [t for t, _ in texts], 'arrived, the cover stays there alone a moment')
    tick(m, O['IPCF_GO_HOLD_MS'] // FAST + 2)
    texts, _, blits, _ = paint(m)
    expect(FRAME not in [b[2] for b in blits] and 'Now Playing' in [t for t, _ in texts], 'once there, Now Playing itself')
    m.calls = []
    x, y = m.polar(0, 85); m.tap(x, y)
    reloaded = ('loadLocalClassList', O['CLASS_ALBUMS']) in m.calls
    texts, _, blits, _ = paint(m)
    expect(reloaded and sel_of(m) == 1 and flip_state(m) == (0, 0) and
           [b[2] for b in blits] == [FRAME] and 'Album 1' in [t for t, _ in texts] and 'Album 1 0' not in [t for t, _ in texts],
           'MENU from Now Playing: the cover comes back to the covers at the same album, its captions already up, no card')
    for _ in range(7): tick(m)   # into the side covers sliding in on the way back
    paint(m); back = [album_px(m, x) for x in range(320)]
    settle(m)
    expect(rested(m) and 'Album 1' in captions(m), 'and the shelf rests on it again')
    paint(m); rest = [album_px(m, x) for x in range(320)]
    at = lambda row, a: [x for x, v in enumerate(row) if v == a]
    mean = lambda xs: sum(xs) / len(xs) if xs else None
    expect(at(back, 2) and at(back, 0) and mean(at(back, 2)) > mean(at(rest, 2)) + 8 and mean(at(back, 0)) < mean(at(rest, 0)) - 8,
           f'on the way back the side covers slide in from both edges ({mean(at(back, 0))}, {mean(at(back, 2))} at rest {mean(at(rest, 0))}, {mean(at(rest, 2))})')
    # a stall before the first tick (the first play after boot starting the player cold) is not taken out of the go
    p = machine(); enter(p); p.turn(0, STEP_DEG + 3); settle(p)
    x, y = p.polar(180, 85); p.tap(x, y)
    p.clock += O['IPCF_GO_MS'] + O['IPCF_GO_HOLD_MS']
    tick(p, O['IPCF_GO_MS'] // FAST // 2)
    texts, _, blits, _ = paint(p)
    expect(FRAME in [b[2] for b in blits] and 'Now Playing' not in [t for t, _ in texts],
           f'a stall before the first tick: the cover still goes, frame by frame ({texts})')
    tick(p, (O['IPCF_GO_MS'] + O['IPCF_GO_HOLD_MS']) // FAST + 4)
    expect('Now Playing' in [t for t, _ in paint(p)[0]], 'and arrives at Now Playing after the whole go')
    # back on the covers with the album playing: the play key pauses there; paused, it plays on and the cover goes again
    m.status = 2; m.play([m.record(album='Album 1', artist='Artist 1', path='Album 1-0.flac', title='Album 1 0')], 0)
    m.calls = []; m.cmds = []
    x, y = m.polar(180, 85); m.tap(x, y)
    expect(m.cmds == [('playpause',)] and m.status == 3 and 'start_player' not in m.names() and 'Album 1' in captions(m) and rested(m),
           f'playing: the play key pauses, Cover Flow stays ({m.cmds})')
    m.calls = []; m.cmds = []
    m.tap(x, y)
    expect(m.cmds == [('playpause',)] and m.status == 2 and 'start_player' not in m.names() and 'Cover Flow' in [t for t, _ in paint(m)[0]],
           f'paused on its album: it plays on (no new start) and the cover goes to Now Playing ({m.cmds})')
    tick(m, (O['IPCF_GO_MS'] + O['IPCF_GO_HOLD_MS']) // FAST + 4)
    expect('Now Playing' in [t for t, _ in paint(m)[0]], 'then Now Playing itself')
    x, y = m.polar(0, 85); m.tap(x, y); settle(m)
    m.status = 3; m.turn(0, STEP_DEG + 3); settle(m); m.calls = []; m.cmds = []
    x, y = m.polar(180, 85); m.tap(x, y)
    sp = [c for c in m.calls if c[0] == 'start_player']
    expect(sp == [('start_player', 0, 0xff10, O['PLAY_MODE'])] and not m.cmds, f'paused on another album: the play key plays that one from its first track ({sp}, {m.cmds})')
    # MENU while the slide is still moving: the page timer is back at 500 ms
    m = machine(); enter(m); settle(m)
    m.turn(0, STEP_DEG * 3 + 3); m.calls = []
    x, y = m.polar(0, 85); m.tap(x, y); calls = list(m.calls)
    tick(m, 20); calls += m.calls   # the split closes, then the main menu's title bar drops in
    mods = MODS(calls)
    expect(mods and mods[-1] in (TICK, O['IP_DRIFT_MS'], O['IP_PAN_MS']) and not SWAPS(calls), f'MENU while it slides: once the menu is back the one timer leaves 33 ms in place, for the main menu\'s pace ({mods})')
    # an album with no cached cover shows the placeholder, the rest still work
    m = machine(4, art=False); enter(m)
    for _ in range(10): tick(m)
    expect(px(m, 160, MID) != colour(0) and ('widget_load_image', 'file://' + art_file(album_key('Artist 0', 'Album 0'))) not in m.calls, 'no cached cover: the placeholder, no decode of a file that is not there')
    settle(m); tick(m, 12)   # (and the title bar has dropped in)
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
    # a stale list (another page queried): the screen is black, not a wrong list; the tick reads it again
    m = machine(); enter(m)
    for _ in range(14): tick(m)
    m.setword(ip.SHOWLIST, m.new_deque([m.record(album='Other', artist='X', path='/x.flac', rid=900)]))
    texts, fills, blits, names = paint(m)
    expect(not [t for t, r in texts if r[1] >= BARH] and fills and fills[0][1:] == (0, 0, 320, 240) and not blits and 'Cover Flow' in [t for t, _ in texts], 'a stale stock list: white with the title bar, no rows, no cover (paint never reads it)')


def i18n_tests(ctx):
    expect = ctx.expect
    src = open(os.path.join(ROOT, 'patch', 'ipod_cf.c')).read()
    keys = set(re.findall(r'TR\("([^"]+)"\)', src))
    missing = [k for k in keys if k not in pod_i18n.TEXT and k not in pod_i18n.STOCK]
    expect(keys == {'No songs'} and not missing, f'the screen\'s texts are keys that exist ({keys}, missing {missing})')
    # the geometry in offsets.inc is one shelf: the three caption lines and the reflection fit the 240 px screen, the frame the covers and their reflection
    expect(abs((O['IPCF_FRAME_Y'] + O['IPCF_TOP'] + O['IPCF_ART'] // 2) - 106) <= 2 and O['IP_SCREEN_H'] - (O['IPCF_CAP_Y'] + 2 * O['IPCF_CAP_H']) >= 4, 'the centre cover is centred about 106 px down the 240 px screen (22 px of air under the title bar), the captions end at least 4 px above its bottom edge')
    top, art, refl, cap, caph = O['IPCF_TOP'], O['IPCF_ART'], O['IPCF_REFLECT'], O['IPCF_CAP_Y'], O['IPCF_CAP_H']
    expect(top + art + refl <= O['IPCF_FRAME_H'] and O['IPCF_FRAME_Y'] + O['IPCF_FRAME_H'] <= O['IP_SCREEN_H'] and top + art <= cap - O['IPCF_FRAME_Y'] and cap + 2 * caph <= O['IP_SCREEN_H'],
           'the covers and their reflection end inside the frame, the frame inside the screen, the covers above the captions (drawn over the reflection, as on the iPod), the two caption lines inside the 240 px screen')
    expect(O['IPCF_FRAME_MS'] < O['IP_TICK_MS'] and O['IPCF_NEAR'] <= 12, 'the slide runs at 33 ms against the 500 ms rest; a far jump stays bounded')


def order_tests(ctx):
    """The shared order, Start At and the shared position (docs/modules/ipod-coverflow.md "Order and start"): the shelf in the Albums page's order (the file the Cover Flow page's "..." card
    changes too), opening where Settings > Library > Cover Flow > Start At says, and leaving its centre album where the Cover Flow page opens."""
    expect = ctx.expect
    START, POS = '/mnt/data/m1plus/coverflow-start', '/mnt/mmc/.m1plus/coverflow-position'

    def key_of(i): return album_key(f'Artist {i}', f'Album {i}')

    def opened(sort=None, play=None, **fs):
        m = machine(); m.fresh_rows = True
        if sort is not None: m.fs[SORT_FILE] = sort
        m.fs.update(fs)
        if play is not None: m.play([m.record(album=f'Album {play}', artist=f'Artist {play}', path=f'Album {play}-0.flac', title=f'Album {play} 0')], 0)
        enter(m)
        for _ in range(12): tick(m)
        return m
    m = opened(sort=b'b\n')   # Artist, Z-A
    expect(centre_album(m) == 'Album 11', f'the shelf in the saved order: Artist Z-A starts on the last artist ({centre_album(m)})')
    m.turn(0, STEP_DEG + 3); settle(m)
    expect(centre_album(m) == 'Album 10', f'and a step goes on in that order ({centre_album(m)})')
    m.canvas = m.canvas_mem = m.alloc(0x80)
    m.calls = []; m.tap(CX, CY)
    expect(('loadAlbumdetailList', O['CLASS_ALBUMS'], 'Album 10') in m.calls, 'the centre button flips the album in the centre: the reordered row is its record')
    m = opened(sort=b'1\n')
    expect(centre_album(m) == 'Album 0', 'Artist A-Z: the stock order\'s first album')
    # Start At
    for data, want in ((None, 'Album 4'), (b'0\n', 'Album 4'), (b'1\n', 'Album 8'), (b'2\n', 'Album 0')):
        fs = {POS: b'%08x\n' % key_of(8)}
        if data is not None: fs[START] = data
        m = opened(play=4, **fs)
        expect(centre_album(m) == want, f'Start At {data!r}: opens on {want} ({centre_album(m)})')
    m = opened(**{POS: b'%08x\n' % key_of(6)})
    expect(centre_album(m) == 'Album 6', 'Playing Album with nothing playing: the album last centred on either shelf')
    # leaving saves the centre album for both shelves
    m.turn(0, STEP_DEG + 3); settle(m)
    m.tap(*m.polar(0, 85))
    expect(m.fs.get(POS) == b'%08x\n' % key_of(7), f'MENU leaves Cover Flow: its centre album is the saved position ({m.fs.get(POS)})')


SECTIONS = [enter_tests, wheel_tests, anim_tests, track_tests, life_tests, i18n_tests, order_tests]
