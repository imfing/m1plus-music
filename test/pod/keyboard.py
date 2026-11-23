"""The on-screen keyboard (patch/keyboard.c, tools/pod_keyboard.py, tools/pod_ui.py build_keyboard_page, docs/modules/keyboard.md): the asset's geometry and colours against the
design (180 px pad, 44 px pitch, 29 x 36 keys, 3 px gaps, rows centred, no accent colour), every page's widget moves in the payload against the same geometry, typing, shift,
the 123 and #+= pages, delete and its repeat, the clear button, the caret by the measured width, a long text, the key pop-up (insensitive), Search and Back, the log of the touches,
and the strings in every language. The compiled payload runs under Unicorn; the callbacks are stock functions the harness traps (atoi records its string, on_backtoplayer_onclick is
recorded), the field's width is the stb model's (tools/awtk_text.py)."""
import functools, importlib.util, os, sys
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)
import awtk_strings, cdefs, pod_keyboard as PK
from awtk_text import Ttf, StbText

HERE = os.path.dirname(os.path.abspath(__file__))


def load_pinyin():
    """test/pod/pinyin.py as a module (its Engine machine runs demo's real engine code on the real dictionary); loaded once, as test/patch.py loads the others."""
    if 'podtest_pinyin' not in sys.modules:
        spec = importlib.util.spec_from_file_location('podtest_pinyin', os.path.join(HERE, 'pinyin.py'))
        mod = importlib.util.module_from_spec(spec)
        sys.modules['podtest_pinyin'] = mod
        spec.loader.exec_module(mod)
    return sys.modules['podtest_pinyin']


PY = load_pinyin()
RAW = os.path.join(WORK, 'rootfs', 'release', 'assets', 'default', 'raw')
FONT = Ttf(os.path.join(RAW, 'fonts', 'default.ttf'))
DEFS = cdefs.defines(os.path.join(ROOT, 'patch', 'keyboard.h'))
PAD_Y = 270            # the pad's top in the window; the window is 30 px down the screen
WIN_Y = 30
DESTROY, TO_BG = O['EVT_DESTROY'], O['EVT_WINDOW_TO_BG']
PTR = {'down': O['EVT_POINTER_DOWN'], 'up': O['EVT_POINTER_UP'], 'abort': O['EVT_POINTER_ABORT'], 'move': O['EVT_POINTER_MOVE']}
RET_REPEAT = 8


@functools.lru_cache(maxsize=None)
def width(t, px=18): return StbText(FONT, px).layout(t)[1]   # (pure: the font is fixed)


def tree():
    return awtk_ui.parse(open(os.path.join(RAW, 'ui', 'm1plus_keyboard.bin'), 'rb').read())


class ZhMachine(PY.Engine, ListMachine):
    """The keyboard's machine with demo's real pinyin engine under it (the stock im_* functions run, only libc is Python)."""


def keyboard_machine(m=None):
    """The page's widgets as the asset has them: names, geometry, visible / sensitive; the pad inside the window (widget_to_local runs stock's code on these). Fonts per widget for the text measure."""
    m = m or ListMachine()
    m.mem_geometry = True
    m.measure = width
    px = {}
    for w in tree().walk():
        if not w.name: continue
        h = m.widget(w.name)
        px[h] = int(w.get('style:normal:font_size') or 18)
        m.rect(h, w.x, w.y, w.w, w.h)
        m.props[(h, 'visible')] = 0 if w.get('visible') == 'false' else 1
        m.props[(h, 'sensitive')] = 0 if w.get('sensitive') == 'false' else 1
    m.measure_w = lambda h, t: width(t, px.get(h, 18))
    pad, win = m.widgets['kb_pad'], m.alloc(0x80)
    for w, y, parent in ((pad, PAD_Y, win), (win, WIN_Y, 0)):
        m.setword(w, 0); m.setword(w + 4, y); m.setword(w + 8, 320); m.setword(w + 0xc, 450 if w == win else PK.KB_H); m.setword(w + 0x44, parent)
    for n, parent in (('kb_strip', win), ('kb_cands', m.widgets['kb_strip'])):   # the candidates view in the strip in the window (widget_to_local walks the parents)
        for off, k in ((0, 'x'), (4, 'y'), (8, 'w'), (0xc, 'h')): m.setword(m.widgets[n] + off, m.props[(m.widgets[n], k)])
        m.setword(m.widgets[n] + 0x44, parent)
    return m


DONE = lambda: PSYMS['pod_lib_atoi']                          # on_done: records ('atoi', text)
CANCEL = pod.FUNCTIONS['on_backtoplayer_onclick'][2]          # on_cancel: records ('on_backtoplayer_onclick',)


def kopen(m, title=None, ph='Type here', initial=None, done=True, cancel=True, flags=0):
    """keyboard_open(title, placeholder, initial, on_done, on_cancel, flags); the last two arguments are on the stack."""
    m.setword(STACK + 16, CANCEL if cancel else 0)
    m.setword(STACK + 20, flags)
    s = lambda v: m.cstr(v) if v is not None else 0
    r = m.call(PSYMS['keyboard_open'], a0=s(title), a1=s(ph), a2=s(initial), a3=DONE() if done else 0, count=40000000)
    return r - (1 << 32) if r >= 1 << 31 else r


def opened(**kw):
    m = keyboard_machine()
    assert kopen(m, **kw) == 0
    return m


def geo(m, name):
    h = m.widgets[name]
    return tuple((v - (1 << 32) if v >= 1 << 31 else v) for v in (m.props[(h, k)] for k in 'xywh'))   # signed: a candidate scrolled half out of its view has a negative x


def shown(m, name): return (m.props.get((m.widgets[name], 'visible'), 1), m.props.get((m.widgets[name], 'sensitive'), 1))
def keys(m): return [said(m, f'kb_k{i}') for i in range(PK.KB_KEYS)]


def run_evt(m, name, evt, e=0):
    fn, ctx = m.bound[(m.widgets[name], evt)]
    return m.call(fn, a0=ctx, a1=e, count=40000000)


def ptr(m, name, kind, x=0, y=0, t=1000):
    e = m.alloc(0x30); m.u.mem_write(e, bytes(0x30))
    m.setword(e, PTR[kind]); m.setword(e + 8, t); m.setword(e + 0x18, x); m.setword(e + 0x1c, y)
    run_evt(m, name, PTR[kind], e)


def lift(m, name, x=0, y=0, t=1000):
    """The finger lifts on the key it is on: the click first, then the up (the real order)."""
    run_evt(m, name, O['EVT_CLICK']); ptr(m, name, 'up', x, y, t)


def centre(m, name):
    x, y, w, h = geo(m, name)
    return x + w // 2, WIN_Y + PAD_Y + y + h // 2


def press(m, name, t=1000):
    """A tap on a key: down, then the click, then the up (a button's own on_event emits the click before the handlers bound for the up: stock widget_dispatch 0x66cec8 calls vt->on_event
    first, button on_event 0x6224ec); every call's records, in order."""
    x, y = centre(m, name)
    out = []
    ptr(m, name, 'down', x, y, t); out += m.calls
    run_evt(m, name, O['EVT_CLICK']); out += m.calls
    ptr(m, name, 'up', x, y, t + 80); out += m.calls
    m.calls = out
    return out


def typ(m, text):
    """Tap the char key labelled c for each c of text (the current page; labels are looked up)."""
    for c in text:
        k = keys(m).index(c)
        press(m, f'kb_k{k}')


def field(m): return said(m, 'kb_text')
def caret_x(m): return geo(m, 'kb_caret')[0]
def calls_of(m, name, *args): return [c for c in m.calls if c[0] == name and c[1:1 + len(args)] == args]


def layout_ok(m, page, lang=False, zh=False, fr=False):
    """Every char key and function key of the machine against pod_keyboard.layout(page): geometry, text, visibility."""
    lay = PK.layout(page, lang=lang, zh=zh, fr=fr)
    bad = []
    for i in range(PK.KB_KEYS):
        name = f'kb_k{i}'
        if i < len(lay['keys']):
            c, x, y, w = lay['keys'][i]
            if geo(m, name) != (x, y, w, PK.KB_KH) or said(m, name) != c or shown(m, name) != (1, 1): bad.append((name, geo(m, name), said(m, name), shown(m, name), (c, x, y, w)))
        elif shown(m, name) != (0, 0): bad.append((name, 'should be hidden', shown(m, name)))
    for name, role in (('kb_shift', 'shift'), ('kb_sym', 'sym'), ('kb_del', 'del'), ('kb_mode', 'mode'), ('kb_lang', 'lang'), ('kb_space', 'space'), ('kb_go', 'go')):
        if role in lay['fn']:
            x, y, w = lay['fn'][role]
            if geo(m, name) != (x, y, w, PK.KB_KH): bad.append((name, geo(m, name), (x, y, w)))
    return bad


def base_tests(ctx):
    expect = ctx.expect
    t = tree()
    node = lambda n: t.find(n)

    # 1. The asset against the design
    expect(DEFS['KB_W'] == PK.SCREEN_W and DEFS['KB_H'] == PK.KB_H == 180 and DEFS['KB_PAD'] == PK.KB_PAD == 6 and DEFS['KB_PITCH'] == PK.KB_PITCH == 44 and DEFS['KB_KH'] == PK.KB_KH == 36
           and DEFS['KB_KW'] == PK.KB_KW == 29 and DEFS['KB_GAP'] == PK.KB_GAP == 3 and DEFS['KB_NUM_KW'] == PK.KB_NUM_KW and DEFS['KB_FN_W'] == PK.KB_FN_W == 40 and DEFS['KB_MODE_W'] == PK.KB_MODE_W == 74
           and DEFS['KB_EDGE'] == PK.KB_EDGE and DEFS['KB_KEYS'] == PK.KB_KEYS == 26 and DEFS['KB_MAX'] == PK.KB_MAX and DEFS['KB_POP_W'] == PK.KB_POP_W == 46 and DEFS['KB_POP_H'] == PK.KB_POP_H == 50
           and DEFS['KB_POP_GAP'] == PK.KB_POP_GAP and DEFS['KB_STEM_UP'] == PK.KB_STEM_UP and DEFS['KB_TEXT_X'] == PK.FIELD_TEXT_X and DEFS['KB_TEXT_W'] == PK.FIELD_TEXT_W and DEFS['KB_CARET_Y'] == PK.CARET_Y
           and (DEFS['KB_FIELD_H'], DEFS['KB_CLEAR_W']) == (PK.FIELD_H, PK.FIELD_CLEAR_W) and [DEFS['KB_' + n] for n in ('NAME_Y', 'NAME_ROW', 'NAME_X', 'NAME_DY', 'NAME_FIELD_W', 'NAME_TW')] == [PK.NAME_Y, PK.NAME_ROW, PK.NAME_X, PK.NAME_DY, PK.NAME_FIELD_W, PK.NAME_TW]
           and DEFS['KB_WIN_H'] == 450, 'patch/keyboard.h and tools/pod_keyboard.py agree on every number')
    pad = node('kb_pad')
    expect((pad.x, pad.y, pad.w, pad.h) == (0, 270, 320, 180) and pad.get('style:normal:bg_color') == '#1C1C1E', 'the pad is 180 px high at the bottom of the 450 px window (the bottom of the 480 px screen), #1C1C1E')
    lay = PK.layout('abc')
    kids = {c.name: c for c in pad.children}
    letters = [kids[f'kb_k{i}'] for i in range(26)]
    expect([(c.x, c.y, c.w, c.h) for c in letters] == [(x, y, w, 36) for _, x, y, w in lay['keys']] and [c.get('text') for c in letters] == list('qwertyuiopasdfghjklzxcvbnm'),
           'the tree holds the lowercase page: 26 keys, 29 x 36')
    rows = [[c for c in letters if c.y == y] for y in (6, 50, 94)]
    expect([len(r) for r in rows] == [10, 9, 7] and all(r[0].w == 29 and all(b.x - (a.x + a.w) == 3 for a, b in zip(r, r[1:])) for r in rows),
           'rows of ten, nine and seven keys with 3 px gaps')
    expect(rows[0][0].x == 2 and rows[0][-1].x + 29 == 319 and rows[1][0].x == 18 and rows[2][0].x == 50, 'ten across with a 1.5 px margin (2 on the left, 1 on the right), the rows of nine and seven start at 18 and 50')
    expect(abs((rows[1][0].x) - (320 - (rows[1][-1].x + 29))) <= 1 and abs((rows[2][0].x) - (320 - (rows[2][-1].x + 29))) <= 1, 'rows two and three are centred (within the half pixel)')
    sh, de, mo, sp, go = kids['kb_shift'], kids['kb_del'], kids['kb_mode'], kids['kb_space'], kids['kb_go']
    expect((sh.x, sh.y, sh.w, sh.h) == (2, 94, 40, 36) and (de.x, de.y, de.w, de.h) == (279, 94, 40, 36), 'shift and delete: 40 wide, at the left and right edge of the third row')
    expect((mo.x, mo.y, mo.w) == (2, 138, 74) and (sp.x, sp.w) == (79, 163) and (go.x, go.w) == (245, 74) and sp.x - (mo.x + mo.w) == 3 and go.x - (sp.x + sp.w) == 3 and go.x + go.w == 319,
           'the bottom row: 123 (74), space (163), Search (74), 3 px apart')
    expect(all(w.y + w.h <= 180 for w in pad.children) and 138 + 36 + 6 == 180, 'six pixels of padding under the last row')
    fills = {n: kids[n].get('style:normal:bg_color') for n in kids}
    expect(all(fills[f'kb_k{i}'] == '#4A4A4E' for i in range(26)) and fills['kb_space'] == '#4A4A4E', 'letter keys (and space) are #4A4A4E')
    expect(all(fills[n] == '#2E2E32' for n in ('kb_shift', 'kb_sym', 'kb_del', 'kb_mode', 'kb_go')) and fills['kb_shifton'] == '#E5E5EA', 'function keys (shift, #+=, delete, 123 / ABC, Search) are #2E2E32; shift on is a light key')
    expect(all(kids[n].get(f'style:{st}:round_radius') == '5' for n in kids for st in ('normal', 'pressed')), 'every key is rounded, 5 px')
    expect(all(kids[n].get('style:normal:font_size') == '20' for n in [f'kb_k{i}' for i in range(26)]) and kids['kb_go'].get('tr_text') == 'Search' and kids['kb_space'].get('tr_text') == 'space', 'letters 20 px; Search and space are translated keys')
    expect([node(n).get('visible') for n in ('kb_shifton', 'kb_sym', 'kb_clear', 'kb_stem', 'kb_pop')] == ['false'] * 5 and all(node(n).get('sensitive') == 'false' for n in ('kb_shifton', 'kb_sym', 'kb_clear', 'kb_stem', 'kb_pop')),
           'what starts hidden is invisible and insensitive')
    stem, pop, pop_l = node('kb_stem'), node('kb_pop'), node('kb_pop_l')
    expect((pop.w, pop.h) == (46, 50) and pop.get('style:normal:bg_color') == '#6E6E73' and pop.get('style:normal:round_radius') == '10' and stem.get('style:normal:bg_color') == '#6E6E73'
           and pop_l.get('style:normal:font_size') == '34' and pop_l.get('style:normal:text_color') == '#FFFFFF', 'the pop-up: a #6E6E73 balloon, 46 x 50, radius 10, the letter at 34 px')
    expect(all(node(n).get('sensitive') == 'false' for n in ('kb_stem', 'kb_pop', 'kb_pop_l', 'kb_text', 'kb_hint', 'kb_caret', 'kb_mag')) and node('kb_field').get('sensitive') == 'true', 'the pop-up and the field\'s decorations take no touches (the field itself stays sensitive: the clear button inside it needs it)')
    expect([c.name for c in t.children][-3:] == ['kb_stem', 'kb_pop', 'kb_acc'] and t.children[-2].children[0].name == 'kb_pop_l', 'the pop-up and the accent strip are last: over the pad (and not clipped by it)')
    acc = node('kb_acc')
    expect([c.name for c in acc.children] == ['kb_acc_h'] + [f'kb_a{i}' for i in range(PK.ACC_MAX)] and all(c.get('sensitive') == 'false' for c in [acc] + acc.children) and acc.get('visible') == 'false'
           and acc.get('style:normal:bg_color') == '#6E6E73' and node('kb_acc_h').get('style:normal:bg_color') == '#3A3A3C' and node('kb_a0').get('style:normal:text_color') == '#FFFFFF' and node('kb_a0').get('style:normal:font_size') == '24',
           'the accent strip: a hidden insensitive #6E6E73 bar with a highlight pill and seven white labels, all insensitive')
    fld = node('kb_field')
    cap, card = node('kb_capsule'), node('kb_card')
    expect((fld.x, fld.y, fld.w, fld.h) == (10, 58, 300, 36) and fld.get('style:normal:bg_color') == '#00000000' and fld.get('sensitive') == 'true', 'the field: 300 x 36, transparent, sensitive')
    expect((cap.x, cap.y, cap.w, cap.h) == (10, 58, 300, 36) and cap.get('style:normal:bg_color') == '#1C1C1E' and cap.get('style:normal:round_radius') == '10' and cap.get('sensitive') == 'false'
           and [c.name for c in cap.children] == ['kb_mag'] and [c.name for c in t.children].index('kb_capsule') < [c.name for c in t.children].index('kb_field'),
           'the search fill is kb_capsule under the field: a rounded #1C1C1E bar, 300 x 36, with the magnifier')
    expect((card.x, card.y, card.w, card.h) == (10, 56, 300, 48) and card.get('visible') == 'false' and card.get('sensitive') == 'false' and [c.name for c in t.children].index('kb_card') < [c.name for c in t.children].index('kb_field'),
           'kb_card is the Sign In card\'s one row, hidden, under the field')
    expect(node('kb_text').get('style:normal:font_size') == '18' and node('kb_text').get('style:normal:text_color') == '#FFFFFF' and node('kb_hint').get('style:normal:text_color') == '#8E8E93' and node('kb_caret').get('style:normal:bg_color') == '#FFFFFF'
           and (node('kb_caret').w, node('kb_caret').h) == (2, 22), 'white 18 px text, a grey hint, a white 2 x 22 caret')

    def geo_w(n): return node(n).w

    def neutral(c): return len(c) < 7 or max(int(c[i:i + 2], 16) for i in (1, 3, 5)) - min(int(c[i:i + 2], 16) for i in (1, 3, 5)) <= 6   # the design's greys lean 2 to 5 levels to blue (#6E6E73, #8E8E93, #E5E5EA)
    colours = [(w.name, k, v) for w in t.walk() if w.name.startswith('kb_') for k, v in w.props if k.endswith(('bg_color', 'text_color', 'border_color')) and v.startswith('#')]
    expect(colours and all(neutral(v) for _, _, v in colours), f'no accent colour anywhere: white and grey only ({[c for c in colours if not neutral(c[2])]})')
    for n in ('qk_shift', 'qk_shifton', 'qk_delete', 'qk_mag', 'qk_clear', 'pod_ci_keyboard'):
        im = asset_image(n)
        px = [im.getpixel((x, y)) for x in range(im.width) for y in range(im.height) if im.getpixel((x, y))[3] > 40]
        expect(px and all(neutral('#%02x%02x%02x' % p[:3]) for p in px), f'{n}.png is grey and white only')
    expect(os.path.isfile(os.path.join(RAW, 'images', 'xx', 'qk_shift.png')) and node('kb_shift').get('style:normal:icon') == 'qk_shift' and node('kb_del').get('style:normal:icon') == 'qk_delete'
           and node('kb_mag').get('image') == 'qk_mag' and node('kb_clear').get('style:normal:icon') == 'qk_clear', 'the glyph images are in the tree and the widgets name them (not the stock kb_* names)')
    expect(len({w.name for w in t.walk() if w.name}) == len([w for w in t.walk() if w.name]), 'every widget name is unique')

    # 2. Opening: the page, the field, shift on for the empty field
    m = keyboard_machine()
    expect(kopen(m, title='Search', ph='Shows') == 0 and ('window_open', 'm1plus_keyboard') in m.calls, 'keyboard_open opens ui/m1plus_keyboard')
    expect(said(m, 'label_title') == 'Search' and said(m, 'kb_hint') == 'Shows' and shown(m, 'kb_hint')[0] == 1, 'the title and the placeholder are set')
    expect(field(m) == '' and shown(m, 'kb_clear') == (0, 0) and caret_x(m) == 30, 'an empty field: no text, no clear button, the caret at the text start')
    expect(keys(m)[:3] == ['Q', 'W', 'E'] and shown(m, 'kb_shifton') == (1, 1) and shown(m, 'kb_shift') == (0, 0) and said(m, 'kb_mode') == '123', 'an empty field starts on the uppercase page, shift on')
    expect(not layout_ok(m, 'ABC') and not [c for c in m.calls if c[0] in ('widget_move', 'widget_resize') and c[1] in [m.widgets[f'kb_k{i}'] for i in range(26)]], 'the uppercase page keeps the lowercase geometry: no key moves')
    m = keyboard_machine()
    kopen(m, ph=None)
    expect(said(m, 'label_title') is None and said(m, 'kb_hint') == '', 'no title: the page\'s own stays; no placeholder: an empty hint')
    m = keyboard_machine()
    kopen(m, initial='Hello')
    expect(field(m) == 'Hello' and keys(m)[0] == 'q' and shown(m, 'kb_shift') == (1, 1) and shown(m, 'kb_hint')[0] == 0 and shown(m, 'kb_clear') == (1, 1) and caret_x(m) == 30 + width('Hello') + 1,
           'an initial text: lowercase page, the clear button, the caret after the text')
    m = keyboard_machine()
    kopen(m, initial='a' * 80)
    expect(len(field(m).replace('…', '')) <= 63 + 0 and field(m).startswith('…'), 'an initial text over 63 bytes is cut')
    m = keyboard_machine()
    kopen(m, initial='é' * 40)
    expect(len(said(m, 'kb_text').replace('…', '').encode()) <= 63 and not said(m, 'kb_text').endswith('�'), 'the cut is on a character boundary')
    m = keyboard_machine()
    expect(kopen(m, ph=None) == 0 and kopen(m) == -1 and [c for c in m.calls if c[0] == 'window_open'] == [], 'a second keyboard while one is up is refused, without opening a window')
    m = keyboard_machine()
    del m.widgets['kb_k7']
    expect(kopen(m) == -1 and ('navigator_back',) in m.calls, 'an asset that is not ours (a key missing): the window is closed and -1 comes back')
    m = keyboard_machine(); m.windows['m1plus_keyboard'] = 0
    expect(kopen(m) == -1 and 'widget_on' not in m.names(), 'a window that will not open: -1')
    expect((m.widgets['kb_k0'], O['EVT_CLICK']) not in m.bound, 'nothing is bound on a window that did not open')

    # 3. Every page's layout in the payload against the geometry
    m = opened()
    seq = []
    for page, name in (('123', 'kb_mode'), ('#+=', 'kb_sym'), ('123', 'kb_sym'), ('ABC', 'kb_mode')):
        press(m, name)
        seq.append((page, layout_ok(m, page)))
    expect(all(not bad for _, bad in seq), f'123, #+=, 123 and back (an empty field: capitals): each page\'s keys sit where tools/pod_keyboard.py puts them ({[s for s in seq if s[1]][:1]})')
    m = opened()
    press(m, 'kb_mode')
    expect(keys(m)[:10] == list('1234567890') and keys(m)[10:20] == list('-/:;()$&@"') and keys(m)[20:25] == list(".,?!'") and shown(m, 'kb_k25') == (0, 0), 'the 123 page: 1-0, - / : ; ( ) $ & @ ", then . , ? ! \' (25 keys)')
    expect(said(m, 'kb_mode') == 'ABC' and said(m, 'kb_sym') == '#+=' and shown(m, 'kb_sym') == (1, 1) and shown(m, 'kb_shift') == (0, 0) and shown(m, 'kb_shifton') == (0, 0), '123 shows ABC at the bottom left and #+= where shift was')
    expect([geo(m, f'kb_k{i}')[2] for i in (20, 24)] == [41, 41] and geo(m, 'kb_k20')[0] == 52 and geo(m, 'kb_del')[0] == 279, 'the third row of the 123 page: five 41 px keys between #+= and delete')
    press(m, 'kb_sym')
    expect(keys(m)[:10] == list('[]{}#%^*+=') and keys(m)[10:20] == list('_\\|~<>€£¥`') and said(m, 'kb_sym') == '123', 'the #+= page: [ ] { } # % ^ * + =, _ \\ | ~ < > € £ ¥ ` (the backtick took the bullet\'s place: every printable ASCII character is typeable), with 123 where #+= was')
    expect(all(c == ' ' or FONT.glyph(c) != 0 for c in PK.LABELS if len(c) == 1), 'the shipped font has a glyph for every key label')

    # 4. Typing, shift, 123
    m = opened()
    typ(m, 'H')
    expect(field(m) == 'H' and keys(m)[0] == 'q' and shown(m, 'kb_shift') == (1, 1) and shown(m, 'kb_shifton') == (0, 0) and shown(m, 'kb_hint')[0] == 0 and shown(m, 'kb_clear') == (1, 1),
           'a letter on the uppercase page types a capital and shift goes off (one-shot); the hint goes, the clear button comes')
    typ(m, 'i')
    expect(field(m) == 'Hi' and keys(m)[0] == 'q', 'then lowercase')
    press(m, 'kb_shift')
    expect(keys(m)[0] == 'Q' and shown(m, 'kb_shifton') == (1, 1) and shown(m, 'kb_shift') == (0, 0), 'a tap on shift: capitals, the key lights')
    press(m, 'kb_shifton')
    expect(keys(m)[0] == 'q' and shown(m, 'kb_shift') == (1, 1), 'a tap on the lit shift: lowercase again')
    press(m, 'kb_shift'); press(m, 'kb_mode'); press(m, 'kb_mode')
    expect(keys(m)[0] == 'q' and field(m) == 'Hi', 'to 123 and back with text in the field: the lowercase page (shift off)')
    press(m, 'kb_mode'); typ(m, '1'); typ(m, '-')
    expect(field(m) == 'Hi1-' and said(m, 'kb_mode') == 'ABC', 'digits and symbols type as they are and the page stays')
    press(m, 'kb_mode')
    press(m, 'kb_space')
    expect(field(m) == 'Hi1- ', 'space types a space')
    press(m, 'kb_space')
    expect(field(m) == 'Hi1- ', 'a second space in a row does nothing')
    m = opened()
    press(m, 'kb_space')
    expect(field(m) == '', 'a space in an empty field does nothing')
    m = opened()
    press(m, 'kb_mode'); press(m, 'kb_sym'); typ(m, '€'); typ(m, '[')
    expect(field(m) == '€[', 'symbols from the #+= page, a three byte character among them')
    press(m, 'kb_del', 5000)
    expect(field(m) == '€', 'delete removes one character')
    press(m, 'kb_del', 6000)
    expect(field(m) == '', 'a three byte character goes whole')
    m = opened()
    typ(m, 'A')
    for _ in range(69): typ(m, 'a')
    full = [c for c in press(m, 'kb_go') if c[0] == 'atoi']
    expect(PK.KB_MAX == 63 and full and full[0][1] == 'A' + 'a' * 62, f'70 letters typed: 63 bytes of text and not a byte more reach on_done ({len(full[0][1]) if full else None})')

    # KB_LONG (the podcast search field takes a feed address): up to 255 bytes, a long initial text kept whole, the field still shows the end of what does not fit
    m = opened(flags=4)
    typ(m, 'A')
    for _ in range(299): typ(m, 'a')
    full = [c for c in press(m, 'kb_go') if c[0] == 'atoi']
    expect(full and full[0][1] == 'A' + 'a' * 254 and len(full[0][1]) == 255, f'with KB_LONG 300 letters typed: 255 bytes reach on_done ({len(full[0][1]) if full else None})')
    m = opened(flags=4, initial='h' * 300)
    expect(field(m).startswith('…') and field(m).endswith('h'), 'a long initial text is cut at 255 bytes and the field shows the end of it')
    full = [c for c in press(m, 'kb_go') if c[0] == 'atoi']
    expect(full and len(full[0][1]) == 255, 'and returns all 255 bytes')
    m = opened(initial='h' * 300)
    full = [c for c in press(m, 'kb_go') if c[0] == 'atoi']
    expect(full and len(full[0][1]) == 63, 'without the flag the limit is still 63 bytes')

    # 5. Delete: on touch down, repeating while held
    m = opened(initial='abcdefgh')
    x, y = centre(m, 'kb_del')
    ptr(m, 'kb_del', 'down', x, y)
    expect(field(m) == 'abcdefg' and any(c[0] == 'timer_add' and c[2] == DEFS['KB_HOLD_MS'] for c in m.calls), 'delete acts on touch down and starts the repeat timer (80 ms)')
    fn = next(c[1] for c in m.calls if c[0] == 'timer_add')
    rets = []
    for _ in range(5):
        rets.append(m.call(fn, a0=0, count=4000000))
    expect(rets == [RET_REPEAT] * 5 and field(m) == 'abcdefg', 'held, nothing repeats for the first five ticks (400 ms)')
    r = m.call(fn, a0=0, count=4000000)
    expect(r == RET_REPEAT and field(m) == 'abcdef', 'the sixth tick deletes one character and the timer goes on')
    for _ in range(3): m.call(fn, a0=0, count=4000000)
    expect(field(m) == 'abc', 'and one every tick after that')
    ptr(m, 'kb_del', 'up', x, y)
    expect(calls_of(m, 'timer_remove'), 'lifting the finger removes the timer')
    expect(m.call(fn, a0=0, count=4000000) == 0 and field(m) == 'abc', 'a tick that still arrives after the release does nothing')
    run_evt(m, 'kb_del', O['EVT_CLICK'])
    expect(field(m) == 'abc', 'the click that follows the release deletes nothing more')
    ptr(m, 'kb_del', 'down', x, y)
    fn = next(c[1] for c in m.calls if c[0] == 'timer_add')
    for _ in range(12): r = m.call(fn, a0=0, count=4000000)
    expect(field(m) == '' and r == 0, 'a repeat that reaches the start of the text ends the timer')
    expect(keys(m)[0] == 'Q' and shown(m, 'kb_shifton') == (1, 1) and shown(m, 'kb_hint')[0] == 1 and shown(m, 'kb_clear') == (0, 0) and caret_x(m) == 30, 'an emptied field: shift on again, the hint back, no clear button, the caret at the start')
    ptr(m, 'kb_del', 'up', x, y)
    m = opened(initial='abc')
    x, y = centre(m, 'kb_del')
    ptr(m, 'kb_del', 'down', x, y)
    ptr(m, 'kb_del', 'abort', x, y)
    expect(field(m) == 'ab' and calls_of(m, 'timer_remove'), 'abort (a slide off the key) also stops the repeat')
    m = opened(initial='abc')
    ptr(m, 'kb_del', 'down', x, y)
    m.call(m.bound[(m.window, TO_BG)][0], a0=m.bound[(m.window, TO_BG)][1], count=4000000)
    expect(calls_of(m, 'timer_remove'), 'the page going to the background stops the repeat')
    m = opened()
    ptr(m, 'kb_del', 'down', x, y)
    expect(field(m) == '' and any(c[0] == 'timer_add' for c in m.calls), 'delete on an empty field does nothing (its timer ends at the first tick)')
    fn = next(c[1] for c in m.calls if c[0] == 'timer_add')
    expect(m.call(fn, a0=0, count=4000000) == 0, 'at once')

    # 6. The clear button
    m = opened()
    typ(m, 'H'); typ(m, 'i')
    expect(shown(m, 'kb_clear') == (1, 1), 'with text the clear button is shown and sensitive')
    run_evt(m, 'kb_clear', O['EVT_CLICK'])
    expect(field(m) == '' and shown(m, 'kb_clear') == (0, 0) and shown(m, 'kb_hint')[0] == 1 and caret_x(m) == 30 and keys(m)[0] == 'Q', 'clear empties the field: no button, the hint, the caret at the start, shift on')
    press(m, 'kb_mode'); typ(m, '7'); run_evt(m, 'kb_clear', O['EVT_CLICK'])
    expect(field(m) == '' and keys(m)[0] == 'Q' and said(m, 'kb_mode') == '123' and not layout_ok(m, 'ABC'), 'clear on the 123 page goes back to the (uppercase) letters')

    # 7. The caret follows the measured width
    m = opened()
    seen = []
    for c in 'All in on data':
        press(m, 'kb_space') if c == ' ' else typ(m, c)
        seen.append((field(m), caret_x(m)))
    expect(all(cx == 30 + width(tx) + 1 for tx, cx in seen) and seen[-1][0] == 'All in on data', 'the caret is the text start plus the measured width (advances and 1 px a glyph) plus 1 px, at every length')
    expect(seen[0][1] > 30 and all(b[1] > a[1] for a, b in zip(seen, seen[1:])), 'it moves right with every character')
    expect(any(len(c) == 1 and c == ' ' for c in 'All in on data') and caret_x(m) == 30 + width('All in on data') + 1, 'spaces count')
    m = opened()
    for i in range(40): typ(m, 'W') if i == 0 else typ(m, 'm')
    shown_text = field(m)
    expect(shown_text.startswith('…') and width(shown_text) <= PK.FIELD_TEXT_W and shown_text.endswith('mmm') and caret_x(m) == 30 + width(shown_text) + 1,
           f'a text too wide shows its end after an ellipsis, inside the {PK.FIELD_TEXT_W} px; the caret follows ({shown_text!r}, {width(shown_text)} px)')
    press(m, 'kb_del')
    expect(width(field(m)) <= PK.FIELD_TEXT_W and caret_x(m) <= 30 + PK.FIELD_TEXT_W + 1, 'after a delete it still fits')
    ptr(m, 'kb_del', 'up', 0, 0)
    press(m, 'kb_go')
    done = [c for c in m.calls if c[0] == 'atoi']
    expect(done and done[0][1] == 'W' + 'm' * 38, 'the whole text, not the shown end, goes to on_done')

    # 8. The pop-up
    m = opened(initial='x')
    n_idx = keys(m).index('n')
    x, y = centre(m, f'kb_k{n_idx}')
    ptr(m, f'kb_k{n_idx}', 'down', x, y)
    kx, ky, kw, _ = geo(m, f'kb_k{n_idx}')
    bx, by, sx, sy, sw, sh = PK.pop_rect(kx, ky, kw, PAD_Y)
    expect(shown(m, 'kb_stem')[0] == 1 and shown(m, 'kb_pop')[0] == 1 and said(m, 'kb_pop_l') == 'n', 'a key held shows the balloon and the stem with its letter')
    expect(geo(m, 'kb_pop')[:2] == (bx, by) and geo(m, 'kb_stem') == (sx, sy, sw, sh) and sy < by + 50 and sy + sh == PAD_Y + ky + 36 and by + 50 == PAD_Y + ky - 10,
           'the balloon stands 10 px above the key, centred; the stem as wide as the key runs from 12 px under the balloon down over the key')
    expect(shown(m, 'kb_stem')[1] == 0 and shown(m, 'kb_pop')[1] == 0 and not [c for c in m.calls if c[0] == 'widget_set_sensitive' and c[1] in (m.widgets['kb_stem'], m.widgets['kb_pop'], m.widgets['kb_pop_l'])],
           'the pop-up is insensitive: shown, never made sensitive (decorative overlays take no taps)')
    ptr(m, f'kb_k{n_idx}', 'up', x, y)
    expect(shown(m, 'kb_stem')[0] == 0 and shown(m, 'kb_pop')[0] == 0, 'lifting the finger hides it')
    ptr(m, f'kb_k{n_idx}', 'down', x, y); ptr(m, f'kb_k{n_idx}', 'abort', x, y)
    expect(shown(m, 'kb_pop')[0] == 0, 'abort hides it too')
    ptr(m, 'kb_k0', 'down', *centre(m, 'kb_k0')); ptr(m, 'kb_k9', 'down', *centre(m, 'kb_k9'))
    expect(geo(m, 'kb_pop')[0] == 273 and said(m, 'kb_pop_l') == 'p', 'the right edge key\'s balloon is kept inside the screen (1 px from the edge)')
    ptr(m, 'kb_k0', 'down', *centre(m, 'kb_k0'))
    expect(geo(m, 'kb_pop')[0] == 1 and said(m, 'kb_pop_l') == 'q', 'and the left one')
    expect(geo(m, 'kb_pop')[1] == PAD_Y + 6 - 60 == 216, 'the top row\'s balloon is on the screen (y 216)')
    press(m, 'kb_mode')
    ptr(m, 'kb_k12', 'down', *centre(m, 'kb_k12'))
    expect(said(m, 'kb_pop_l') == keys(m)[12] == ':', 'on the 123 page the balloon shows the key\'s own character')
    ptr(m, 'kb_k12', 'up', *centre(m, 'kb_k12'))
    for name in ('kb_sym', 'kb_mode', 'kb_go', 'kb_space', 'kb_del'):
        ptr(m, name, 'down', *centre(m, name))
        expect(shown(m, 'kb_pop')[0] == 0, f'no balloon for {name}')
        ptr(m, name, 'up', *centre(m, name))

    # 9. Search and Back
    m = opened(initial='  All in  ')
    out = press(m, 'kb_go')
    names_ = [c[0] for c in out]
    expect(names_.index('navigator_back') < names_.index('atoi') and [c[1] for c in out if c[0] == 'atoi'] == ['All in'], 'Search closes the page, then calls on_done with the text, spaces at both ends removed')
    expect(not [c for c in out if c[0] == 'on_backtoplayer_onclick'], 'on_cancel is not called after Search')
    press(m, 'kb_go')
    expect(not [c for c in m.calls if c[0] == 'atoi'], 'a second Search tap while the page closes does nothing')
    fn, ctx_ = m.bound[(m.window, DESTROY)]
    m.call(fn, a0=ctx_, a1=0, count=4000000)
    expect(not [c for c in m.calls if c[0] == 'on_backtoplayer_onclick'] and kopen(m) == 0, 'the destroy after Search calls nothing and frees the keyboard for the next one')
    m = opened()
    press(m, 'kb_go')
    expect(not [c for c in m.calls if c[0] in ('navigator_back', 'atoi')], 'Search with an empty field does nothing')
    typ(m, 'H'); press(m, 'kb_space'); press(m, 'kb_go')
    expect([c[1] for c in m.calls if c[0] == 'atoi'] == ['H'], 'Search with a text and a trailing space gives the trimmed text')
    m = opened()
    run_evt(m, 'btn_return', O['EVT_CLICK'])
    expect([c[0] for c in m.calls if c[0] in ('navigator_back', 'on_backtoplayer_onclick', 'atoi')] == ['navigator_back', 'on_backtoplayer_onclick'], 'Back closes the page and calls on_cancel, never on_done')
    m = opened()
    typ(m, 'H')
    fn, ctx_ = m.bound[(m.window, DESTROY)]
    m.call(fn, a0=ctx_, a1=0, count=4000000)
    expect([c[0] for c in m.calls if c[0] in ('navigator_back', 'on_backtoplayer_onclick', 'atoi')] == ['on_backtoplayer_onclick'], 'the page destroyed some other way (the hardware Back key) is a cancel too')
    expect(kopen(m) == 0, 'and the keyboard is free again')
    m = keyboard_machine()
    kopen(m, done=False, cancel=False)
    typ(m, 'H')
    out = press(m, 'kb_go')
    expect(('navigator_back',) in out and not [c for c in out if c[0] in ('atoi', 'on_backtoplayer_onclick')], 'no callbacks: Search and Back just close')
    m = opened()
    typ(m, 'H')
    run_evt(m, 'btn_backtoplayer', O['EVT_CLICK'])
    expect(('on_backtoplayer_onclick',) in m.calls and field(m) == 'H', 'the Now Playing button goes to the player and leaves the keyboard as it is')
    m = opened()
    fn, ctx_ = m.bound[(m.window, DESTROY)]
    m.call(fn, a0=m.alloc(8), a1=0, count=4000000)
    expect(kopen(m) == -1, 'a destroy event of another window changes nothing')

    # 12. Touches, by demo's own hit test: a key takes a touch inside it, a gap lands on the pad, the pop-up takes none, what is hidden takes none
    def hit_tree(m):
        root = asset_tree(os.path.join(RAW, 'ui', 'm1plus_keyboard.bin'))
        root.y = WIN_Y
        def sync(n):
            h = m.widgets.get(n.name)
            if h is not None and (h, 'x') in m.props:
                n.x, n.y, n.w, n.h = (m.props[(h, k)] for k in 'xywh')
                n.flags = F_ENABLE | (F_VISIBLE if m.props.get((h, 'visible'), 1) else 0) | (F_SENSITIVE if m.props.get((h, 'sensitive'), 1) else 0)
            for c in n.children: sync(c)
        for c in root.children: sync(c)
        root.by_addr = lay_out(m, root)   # once per tree: lay_out allocates every widget again
        return root
    def target(m, root, wx, wy):
        """The name of the widget a touch at window (wx, wy) goes to: demo's widget_find_target down the tree, as stock_target does."""
        w, name = root.addr, root.name
        while True:
            t = m.call(FIND_TARGET, a0=w, a1=wx, a2=WIN_Y + wy, count=200000)
            if not t or (root.by_addr[t].flags & 9) != 9: return name
            w, name = t, root.by_addr[t].name
    m = opened()
    for page, action in (('ABC', None), ('123', 'kb_mode'), ('#+=', 'kb_sym'), ('ABC', 'kb_mode')):
        if action: press(m, action)
        root, bad = hit_tree(m), []
        for i, (c, x, y, w) in enumerate(PK.layout(page)['keys']):
            got = target(m, root, x + w // 2, PAD_Y + y + 18)
            if got != f'kb_k{i}': bad.append((c, got))
            for dx, dy in ((0, 0), (w - 1, 0), (0, 35), (w - 1, 35)):
                if target(m, root, x + dx, PAD_Y + y + dy) != f'kb_k{i}': bad.append((c, dx, dy))
        for role, name in (('shift', 'kb_shifton' if page == 'ABC' else 'kb_shift'), ('sym', 'kb_sym'), ('del', 'kb_del'), ('mode', 'kb_mode'), ('space', 'kb_space'), ('go', 'kb_go')):
            if role in PK.layout(page)['fn']:
                x, y, w = PK.layout(page)['fn'][role]
                got = target(m, root, x + w // 2, PAD_Y + y + 18)
                if got != name: bad.append((role, got, name))
        expect(not bad, f'the {page} page: a touch in the middle and at the four corners of every key lands on that key, the function keys on theirs ({bad[:3]})')
    root = hit_tree(m)
    gaps = [(31, 24), (32, 24), (33, 24), (16, 45), (160, 176), (0, 24), (319, 24), (1, 100)]
    expect(all(target(m, root, x, PAD_Y + y) == 'kb_pad' for x, y in gaps), f'a touch in a gap or in the margin lands on the pad: {[(g, target(m, root, g[0], PAD_Y + g[1])) for g in gaps]}')
    expect(target(m, root, 100, 150) == 'm1plus_keyboard_page', 'the empty area between the field and the pad is the window')
    ptr(m, 'kb_k24', 'down', *centre(m, 'kb_k24'))
    root = hit_tree(m)
    kx, ky, kw, _ = geo(m, 'kb_k24')
    bx, by, _, sy, _, sh = PK.pop_rect(kx, ky, kw, PAD_Y)
    expect(target(m, root, kx + kw // 2, PAD_Y + ky + 18) == 'kb_k24' and target(m, root, kx + kw // 2, sy + 2) != 'kb_stem' and target(m, root, bx + 20, by + 20) not in ('kb_pop', 'kb_pop_l', 'kb_stem'),
           'with the pop-up up, a touch on the held key still goes to the key, and a touch on the balloon or the stem goes to nothing of the pop-up (they are insensitive)')
    ptr(m, 'kb_k24', 'up', *centre(m, 'kb_k24'))
    m = opened()
    root = hit_tree(m)
    expect(target(m, root, 282, 76) != 'kb_clear', 'an empty field: the hidden clear button takes no touch')
    typ(m, 'A')
    root = hit_tree(m)
    expect(target(m, root, 282, 76) == 'kb_clear' and target(m, root, 100, 76) == 'kb_field', 'with text the clear button is the target at the right of the field; its text takes no touch (the field gets it)')

    # 13. The strings fit in every language
    built = {loc: dict(awtk_strings.load(os.path.join(RAW, 'strings', loc + '.bin'))) for loc in pod_i18n.LOCALES}
    worst = {}
    title = node('label_title')
    for key, px, room in (('Search', 15, PK.KB_MODE_W - 8), ('space', 15, geo_w('kb_space') - 8), ('Keyboard', 22, title.w)):   # a key's label keeps 4 px each side
        worst[key] = max((width(built[loc][key], px), loc) for loc in pod_i18n.LOCALES), room
    print('  widest keyboard texts (px, room):', worst)
    expect(all(w <= room for (w, _), room in worst.values()), f'Search, space, the placeholder and the title fit their room in all 13 languages ({worst})')


# ====================================================================================================================================
# The gap rule: a touch on the pad that hits no key goes to the nearest key
# ====================================================================================================================================
def gap_tests(ctx):
    expect = ctx.expect

    def sweep(m, page, lang=False, zh=False):
        """Every point of a grid over the pad, as a pad touch (aborted, so no key is clicked): the key that looks pressed against pod_keyboard.nearest_key (none for a touch inside a key: the key takes it)."""
        lay = PK.layout(page, lang=lang, zh=zh)
        by_handle = {h: n for n, h in m.widgets.items()}
        fn_widget = {'shift': 'kb_shifton' if page == 'ABC' else 'kb_shift', 'sym': 'kb_sym', 'del': 'kb_del', 'mode': 'kb_mode', 'lang': 'kb_lang', 'space': 'kb_space', 'go': 'kb_go'}
        xs = sorted(set(range(0, 320, 13)) | {0, 1, 2, 29, 30, 31, 32, 33, 34, 317, 318, 319})
        ys = sorted(set(range(0, 180, 7)) | {0, 5, 6, 41, 42, 43, 49, 50, 85, 86, 87, 93, 94, 129, 130, 131, 137, 138, 173, 174, 175, 179})
        bad, n, gaps, t = [], 0, 0, 10000
        for y in ys:
            for x in xs:
                t += 1
                ptr(m, 'kb_pad', 'down', x, WIN_Y + PAD_Y + y, t)
                pressed = [by_handle.get(c[1]) for c in m.calls if c[0] == 'widget_set_state' and c[2] == 'pressed']
                kind, ident, d2 = PK.nearest_key(lay, x, y)
                name = f'kb_k{ident}' if kind == 'char' else fn_widget[ident]
                if pressed != ([name] if d2 > 0 else []): bad.append((page, x, y, pressed, name, d2))
                n += 1; gaps += d2 > 0
                ptr(m, 'kb_pad', 'abort', x, WIN_Y + PAD_Y + y, t)
        return bad, n, gaps

    # 1. The model: the payload's nearest key against the model, over every page
    m = opened()
    res = []
    for page, action in (('ABC', None), ('abc', 'kb_shifton'), ('123', 'kb_mode'), ('#+=', 'kb_sym')):
        if action: press(m, action)
        res.append((page, sweep(m, page)))
    for page, (bad, n, gaps) in res:
        expect(not bad and n > 800 and gaps > 100, f'the {page} page: {n} touches over the pad ({gaps} in gaps or margins): each one presses the key pod_keyboard.nearest_key picks (none inside a key) ({bad[:2]})')
    expect(not [c for c in m.calls if c[0] == 'atoi'] and field(m) == '', 'aborted touches type nothing')

    # 2. The behaviour: a gap touch presses the nearest key at once and types it when the finger lifts
    m = opened()
    qx, qy = 31, WIN_Y + PAD_Y + 24                  # between Q and W, nearer Q
    ptr(m, 'kb_pad', 'down', qx, qy, 100)
    expect(said(m, 'kb_pop_l') == 'Q' and shown(m, 'kb_pop')[0] == 1 and shown(m, 'kb_stem')[0] == 1 and ('widget_set_state', m.widgets['kb_k0'], 'pressed') in m.calls and field(m) == '',
           'a touch in the gap between Q and W: the pop-up shows Q, Q looks pressed, nothing is typed yet')
    expect(geo(m, 'kb_pop')[:2] == PK.pop_rect(*geo(m, 'kb_k0')[:3], PAD_Y)[:2] and shown(m, 'kb_pop')[1] == 0, 'the balloon stands where Q\'s own would (and takes no touches)')
    ptr(m, 'kb_pad', 'up', qx, qy, 180)
    expect(field(m) == 'Q' and shown(m, 'kb_pop')[0] == 0 and ('widget_set_state', m.widgets['kb_k0'], 'normal') in m.calls, 'lifting types Q, hides the pop-up and Q looks normal again')
    ptr(m, 'kb_pad', 'up', qx, qy, 190)
    expect(field(m) == 'Q', 'a second lift (the pad gets one for every touch) does nothing')
    ptr(m, 'kb_pad', 'down', qx, qy, 200); ptr(m, 'kb_pad', 'abort', qx, qy, 210)
    expect(field(m) == 'Q' and shown(m, 'kb_pop')[0] == 0 and ('widget_set_state', m.widgets['kb_k0'], 'normal') in m.calls, 'an aborted gap touch (the finger slid away, the page went to the background) types nothing and lets go of the key')
    ptr(m, 'kb_pad', 'down', qx, qy, 220); m.call(m.bound[(m.window, TO_BG)][0], a0=m.bound[(m.window, TO_BG)][1], count=4000000)
    ptr(m, 'kb_pad', 'up', qx, qy, 230)
    expect(field(m) == 'Q' and shown(m, 'kb_pop')[0] == 0, 'the page going to the background while a gap touch is down lets it go, and its lift types nothing')

    # 3. The gaps of the device log: just above delete (the 8 px between rows) goes to delete, which acts on touch down and repeats
    m = opened(initial='abcd')
    x, y = 290, WIN_Y + PAD_Y + 90                   # pad (290, 90): 4 px above delete, 5 px under L
    ptr(m, 'kb_pad', 'down', x, y, 300)
    expect(field(m) == 'abc' and any(c[0] == 'timer_add' for c in m.calls) and shown(m, 'kb_pop')[0] == 0 and ('widget_set_state', m.widgets['kb_del'], 'pressed') in m.calls,
           'a touch just above delete deletes at once, starts the repeat and shows delete pressed (no pop-up)')
    fn = next(c[1] for c in m.calls if c[0] == 'timer_add')
    for _ in range(6): m.call(fn, a0=0, count=4000000)
    expect(field(m) == 'ab', 'held, it repeats like delete itself')
    ptr(m, 'kb_pad', 'up', x, y, 900)
    expect(calls_of(m, 'timer_remove') and field(m) == 'ab' and ('widget_set_state', m.widgets['kb_del'], 'normal') in m.calls, 'lifting stops it; it deletes nothing more')
    m = opened(initial='Hi')
    ptr(m, 'kb_pad', 'down', 319, WIN_Y + PAD_Y + 179, 400)       # the very corner: Search
    expect(field(m) == 'Hi' and [c for c in m.calls if c[0] == 'atoi'] == [], 'a touch in the corner (the pad\'s margin) is Search; nothing happens before the finger lifts')
    ptr(m, 'kb_pad', 'up', 319, WIN_Y + PAD_Y + 179, 480)
    expect([c[1] for c in m.calls if c[0] == 'atoi'] == ['Hi'] and ('navigator_back',) in m.calls, 'and lifting searches')
    m = opened(initial='x')
    ptr(m, 'kb_pad', 'down', 0, WIN_Y + PAD_Y + 2, 500); ptr(m, 'kb_pad', 'up', 0, WIN_Y + PAD_Y + 2, 560)
    expect(field(m) == 'xq', 'a touch in the pad\'s corner margin goes to the nearest key, Q')
    ptr(m, 'kb_pad', 'down', 160, WIN_Y + PAD_Y + 1, 600); ptr(m, 'kb_pad', 'up', 160, WIN_Y + PAD_Y + 1, 660)
    expect(field(m)[-1] == keys(m)[PK.layout('abc')['keys'].index(next(k for k in PK.layout('abc')['keys'] if k[1] <= 160 < k[1] + k[3] + 3))] or field(m)[-1] in 'tyb', f'and the top margin to the key under it ({field(m)})')

    expect(field(m) == 'xqt', f'and the top margin (4 px over the gap between T and Y: 2 px from both, the first wins) to T ({field(m)})')
    m = opened(initial='x')
    x, y = centre(m, 'kb_k5')
    ptr(m, 'kb_k5', 'down', x, y, 700); ptr(m, 'kb_pad', 'down', x, y, 700)
    ptr(m, 'kb_k5', 'up', x, y, 780); ptr(m, 'kb_pad', 'up', x, y, 780)
    run_evt(m, 'kb_k5', O['EVT_CLICK'])
    expect(field(m) == 'xy', f'a touch on a key that the pad hears too types once ({field(m)})')
    m = opened(initial='x')
    ptr(m, 'kb_pad', 'down', qx, qy, 800)            # the pad takes it for a gap ...
    ptr(m, 'kb_k1', 'down', qx, qy, 800)             # ... but W's own handler gets the same touch: the key wins
    ptr(m, 'kb_k1', 'up', qx, qy, 880); ptr(m, 'kb_pad', 'up', qx, qy, 880)
    run_evt(m, 'kb_k1', O['EVT_CLICK'])
    expect(field(m) == 'xw' and shown(m, 'kb_pop')[0] == 0, f'if the pad resolved a touch that a key also got, only the key types ({field(m)})')


# ====================================================================================================================================
# The asset: the language key and the candidate strip
# ====================================================================================================================================
def asset_tests(ctx):
    expect = ctx.expect
    t = tree()
    node = t.find
    lay = PK.layout('abc', lang=True)
    lang, strip, py, sep, cands, chl = (node(n) for n in ('kb_lang', 'kb_strip', 'kb_py', 'kb_sep', 'kb_cands', 'kb_chl'))
    expect((lang.x, lang.y, lang.w, lang.h) == (lay['fn']['lang'][0], lay['fn']['lang'][1], 40, 36) and lang.get('visible') == 'false' and lang.get('sensitive') == 'false' and lang.get('style:normal:bg_color') == '#2E2E32'
           and lang.get('text') == '中' and (lang.x, lang.w) == (79, 40), 'the language key is in the tree, 40 x 36 right of 123 (x 79), a function key, hidden and insensitive')
    expect(lay['fn']['space'][0] == 122 and lay['fn']['space'][2] == 120 and PK.layout('abc')['fn']['space'][:1] == (79,) and PK.layout('abc')['fn']['space'][2] == 163, 'with the key, space starts at 122 and is 120 wide; without it, 79 and 163 (the asset)')
    expect((strip.x, strip.y, strip.w, strip.h) == (0, 234, 320, 36) and strip.y + strip.h == node('kb_pad').y and DEFS['KB_STRIP_Y'] == PK.STRIP_Y == 234 and DEFS['KB_STRIP_H'] == PK.STRIP_H == 36
           and strip.get('visible') == 'false' and strip.get('sensitive') == 'false' and strip.get('style:normal:bg_color') == '#2A2A2C',
           'the strip is 36 px high directly above the pad (y 234 to 270, in the window), hidden and insensitive until shown')
    fld = node('kb_field')
    expect(strip.y > fld.y + fld.h and strip.y >= 94 + 100, 'it does not cover the search field (the field ends at y 94, the strip begins at 234)')
    expect([c.name for c in strip.children] == ['kb_py', 'kb_sep', 'kb_cands'] and [c.name for c in cands.children] == ['kb_chl'] + [f'kb_c{i}' for i in range(12)] and DEFS['KB_POOL'] == PK.POOL == 12,
           'the strip holds the pinyin label, the divider and the candidates view (a highlight and twelve item labels)')
    expect(cands.get('sensitive') != 'false' and cands.get('enable') == 'true' and all(c.get('sensitive') == 'false' for c in cands.children) and py.get('sensitive') == 'false' and sep.get('sensitive') == 'false'
           and all(c.get('visible') == 'false' for c in cands.children + [sep]), 'only the candidates view takes touches (its items, the label, the divider and the highlight are insensitive); the items, divider and highlight start hidden')
    items = cands.children[1:]
    expect(all(c.get('style:normal:font_size') == '20' and c.get('style:normal:text_color') == '#FFFFFF' and c.get('style:normal:text_align_h') == 'left' and c.h == 36 for c in items) and py.get('style:normal:font_size') == '16'
           and py.get('style:normal:text_color') == '#AEAEB2' and (py.x, py.w) == (8, 120) and DEFS['KB_PY_X'] == 8 and DEFS['KB_PY_MAX'] == 120, 'candidates 20 px white, the pinyin 16 px light grey: no accent colour')
    expect(chl.get('style:normal:bg_color') == '#4A4A4E' and chl.get('style:normal:round_radius') == '5' and (chl.y, chl.h) == (DEFS['KB_CHL_Y'], DEFS['KB_CHL_H']) == (4, 28) and DEFS['KB_SEP_Y'] == 8 and DEFS['KB_SEP_H'] == 20,
           'the pressed item\'s highlight is a rounded #4A4A4E bar, 28 px high')
    order = [c.name for c in t.children]
    expect(order.index('kb_strip') > order.index('kb_pad') and order[-3:] == ['kb_stem', 'kb_pop', 'kb_acc'] and order.index('kb_strip') == len(order) - 4, 'the strip comes after the pad and before the pop-up, so the balloons of the top row paint over it')
    expect(DEFS['KB_LANG_W'] == PK.KB_LANG_W == 40 and DEFS['KB_CAND_PAD'] == PK.CAND_PAD == 12 and DEFS['KB_CAND_MIN'] == PK.CAND_MIN == 36 and DEFS['KB_CAND_MAXW'] == PK.CAND_MAXW == 230 and DEFS['KB_DRAG'] == PK.DRAG == 6
           and PK.CAND_MIN * (PK.POOL - 2) >= 320, 'keyboard.h and pod_keyboard.py agree; twelve item widgets are enough for the narrowest items across 320 px')
    expect(all(c.get('text') == '' or c.get('text') is None for c in items + [py]), 'the label and items start empty')
    colours = [(w.name, k, v) for w in t.walk() if w.name.startswith('kb_') for k, v in w.props if k.endswith(('bg_color', 'text_color', 'border_color')) and v.startswith('#')]
    expect(all(len(v) < 7 or max(int(v[i:i + 2], 16) for i in (1, 3, 5)) - min(int(v[i:i + 2], 16) for i in (1, 3, 5)) <= 6 for _, _, v in colours), 'still no accent colour anywhere')
    expect(all(c in PK.LABELS for c in PK.LANG_TAGS) and PK.LANG_TAGS == ('中', 'EN') and FONT.glyph('中') != 0, 'the language key\'s labels are characters the font has (中 for the Chinese layer, EN to go back)')

    # the Keyboards page of Settings is a cards page; its strings fit
    built = {loc: dict(awtk_strings.load(os.path.join(RAW, 'strings', loc + '.bin'))) for loc in pod_i18n.LOCALES}
    import pod_settings as ST
    room = ST.label_box('switch', True)[1] - 4
    worst = max((width(built[loc][k], 20), loc, k) for loc in pod_i18n.LOCALES for k in ('English', 'Chinese (Pinyin)'))
    expect(worst[0] <= room, f'the rows\' labels fit the room before the switch in every language (widest {worst}, room {room})')


# ====================================================================================================================================
# The setting, the language key, the layers
# ====================================================================================================================================
KBZH = '/mnt/data/m1plus/keyboard-pinyin'
DICT_DATA = open(PY.DICT, 'rb').read()


def zh_machine(setting=True, dictionary=True):
    """The keyboard's machine over the real engine; setting: Settings > General > Keyboards > Chinese (Pinyin) is on; dictionary: gpinyin.dat is there."""
    m = keyboard_machine(ZhMachine({PY.SYS_PATH: DICT_DATA} if dictionary else {}))
    if setting: m.fs[KBZH] = b'1\n'
    if dictionary: m.present.add(PY.SYS_PATH)
    return m


def zh_opened(setting=True, dictionary=True, **kw):
    m = zh_machine(setting, dictionary)
    assert kopen(m, **kw) == 0
    return m


def setting_tests(ctx):
    expect = ctx.expect
    ENG = PY.ENGINE_PTR

    # 1. Chinese off (the default): the keyboard is exactly as it was
    m = opened()
    expect(shown(m, 'kb_lang') == (0, 0) and not layout_ok(m, 'ABC') and geo(m, 'kb_space') == PK.layout('abc')['fn']['space'] + (36,) and not [c for c in m.calls if c[0] in ('im_open_decoder', 'access')],
           'no setting: no language key, space and every key where they were (79, 163 wide), the dictionary never looked at, the engine never opened')
    m = zh_opened(setting=False)
    expect(shown(m, 'kb_lang') == (0, 0) and not layout_ok(m, 'ABC') and m.word(ENG) == 0 and geo(m, 'kb_space')[0] == 79, 'the dictionary there but the setting off: the same')
    for data in (b'0\n', b'', b'x', b'\n1', b'1x', b'11'):
        m = keyboard_machine(); m.fs[KBZH] = data; m.present.add(PY.SYS_PATH)
        kopen(m)
        expect(shown(m, 'kb_lang') == (0, 0), f'the file {data!r}: off')

    # 2. Chinese on: the language key, space gives it the room; the engine is not opened until the layer is used
    m = zh_opened()
    x, y, w = PK.layout('abc', lang=True)['fn']['lang']
    expect(shown(m, 'kb_lang') == (1, 1) and geo(m, 'kb_lang') == (x, y, w, 36) and said(m, 'kb_lang') == '中' and (x, w) == (79, 40), 'on: the language key sits right of 123, reads 中')
    sx, sy, sw = PK.layout('abc', lang=True)['fn']['space']
    expect(geo(m, 'kb_space') == (sx, sy, sw, 36) and (sx, sw) == (122, 120) and sx - (x + w) == 3 and geo(m, 'kb_go')[0] - (sx + sw) == 3, 'space starts after it (122) and is 120 wide, 3 px gaps to both neighbours')
    expect(not layout_ok(m, 'ABC', lang=True) and said(m, 'kb_k0') == 'Q' and shown(m, 'kb_shifton') == (1, 1), 'the English layer is as before (capitals for an empty field)')
    expect(m.word(ENG) == 0 and 'im_open_decoder' not in [c[0] for c in m.calls] and PY.SYS_PATH not in m.opened, 'the engine is not opened yet (it is when the Chinese layer is first used)')
    press(m, 'kb_mode')
    expect(shown(m, 'kb_lang') == (1, 1) and geo(m, 'kb_lang')[:3] == (79, 138, 40), 'the language key is there on the 123 page too')

    # 3. Switching: the engine opens, the layer's page, the key's label, shift gone
    m = zh_opened()
    press(m, 'kb_lang')
    eng, inited = m.engine()
    expect(eng and inited == 1 and PY.SYS_PATH in m.opened, 'the language key opens the engine on the real dictionary (initialised)')
    expect(said(m, 'kb_lang') == 'EN' and keys(m)[:3] == ['q', 'w', 'e'] and shown(m, 'kb_shift') == (0, 0) and shown(m, 'kb_shifton') == (0, 0) and shown(m, 'kb_sym') == (1, 1) and said(m, 'kb_sym') == "'" and said(m, 'kb_mode') == '123',
           'the Chinese layer: lowercase letters, no shift, the pinyin separator \' where shift was, the key now reads EN')
    expect(not layout_ok(m, 'abc', lang=True, zh=True) and geo(m, 'kb_sym')[:3] == PK.layout('abc', lang=True, zh=True)['fn']['sym'] and geo(m, 'kb_space')[0] == 122, 'the keys are where the model puts them (with the language key, no shift, the separator)')
    expect(shown(m, 'kb_strip') == (0, 0) and shown(m, 'kb_hint')[0] == 1, 'no strip until something is composed')
    press(m, 'kb_lang')
    expect(said(m, 'kb_lang') == '中' and shown(m, 'kb_shifton') == (1, 1) and said(m, 'kb_k0') == 'Q' and shown(m, 'kb_sym') == (0, 0) and not layout_ok(m, 'ABC', lang=True) and m.engine()[1] == 1,
           'back to English: capitals for the empty field, shift on, the key reads 中; the engine stays open until the page closes')
    press(m, 'kb_lang')
    expect(said(m, 'kb_lang') == 'EN' and m.word(ENG) == eng, 'to Chinese again: the same engine object, not opened twice')
    typ(m, 'ni')
    press(m, 'kb_mode')
    expect(field(m) == '你' and said(m, 'kb_mode') == 'ABC' and shown(m, 'kb_strip') == (0, 0) and keys(m)[:3] == list('123'), 'the 123 page (also on the Chinese layer) commits what was typed first (你) and takes it over')
    typ(m, '5')
    press(m, 'kb_mode')
    expect(keys(m)[0] == 'q' and shown(m, 'kb_shift') == (0, 0) and field(m) == '你5', 'ABC returns to the layer\'s own letters (lowercase, no shift)')
    press(m, 'kb_lang')
    expect(said(m, 'kb_k0') == 'q' and shown(m, 'kb_shift') == (1, 1) and said(m, 'kb_lang') == '中', 'back to English with text in the field: the lowercase page')
    press(m, 'kb_lang'); typ(m, 'ni'); press(m, 'kb_lang')
    expect(field(m) == '你5你' and said(m, 'kb_lang') == '中', 'the language key with pinyin pending commits it (the first candidate) and then switches')
    fn, ctx_ = m.bound[(m.window, DESTROY)]
    m.call(fn, a0=ctx_, a1=0, count=4000000)
    expect(m.engine() == (0, None), 'the page closing closes the engine: the global is NULL, the megabyte is back')

    # 4. The layer is kept for the session
    m = zh_opened()
    press(m, 'kb_lang')
    fn, ctx_ = m.bound[(m.window, DESTROY)]
    m.call(fn, a0=ctx_, a1=0, count=4000000)
    assert kopen(m) == 0
    expect(said(m, 'kb_lang') == 'EN' and keys(m)[0] == 'q' and m.engine()[1] == 1 and shown(m, 'kb_shift') == (0, 0), 'the next keyboard starts on the Chinese layer the last one ended on (engine open again)')
    press(m, 'kb_lang')
    m.call(*m.bound[(m.window, DESTROY)][:1], a0=m.bound[(m.window, DESTROY)][1], count=4000000)
    assert kopen(m) == 0
    expect(said(m, 'kb_lang') == '中' and keys(m)[0] == 'Q' and m.word(ENG) == 0, 'and on English when that is where it ended (no engine opened)')
    press(m, 'kb_lang')
    m.fs[KBZH] = b'0\n'
    m.call(*m.bound[(m.window, DESTROY)][:1], a0=m.bound[(m.window, DESTROY)][1], count=4000000)
    assert kopen(m) == 0
    expect(shown(m, 'kb_lang') == (0, 0) and keys(m)[0] == 'Q' and m.word(ENG) == 0 and geo(m, 'kb_space')[0] == 79, 'with the setting turned off meanwhile: English, no key, the dictionary untouched')

    # 5. Turning the setting off in Settings forgets the layer
    m = zh_opened()
    press(m, 'kb_lang')
    m.call(*m.bound[(m.window, DESTROY)][:1], a0=m.bound[(m.window, DESTROY)][1], count=4000000)
    expect(m.call(PSYMS['kb_zh_toggle'], count=4000000) == 0 and m.fs[KBZH] == b'0\n', 'the setting toggled off (saved)')
    expect(m.call(PSYMS['kb_zh_toggle'], count=4000000) == 1, 'and on again')
    assert kopen(m) == 0
    expect(said(m, 'kb_lang') == '中' and keys(m)[0] == 'Q', 'turned on again: the keyboard starts on English')

    # 6. The engine that will not open: the key goes away, English stays, nothing crashes
    m = zh_opened(dictionary=False)
    expect(shown(m, 'kb_lang') == (0, 0) and geo(m, 'kb_space')[0] == 79 and m.word(ENG) == 0, 'the dictionary missing: no language key, English as ever')
    typ(m, 'H'); typ(m, 'i')
    expect(field(m) == 'Hi', 'and typing works')
    m = keyboard_machine(); m.fs[KBZH] = b'1\n'; m.present.add(PY.SYS_PATH); m.py_open_ok = False
    kopen(m)
    expect(shown(m, 'kb_lang') == (1, 1), 'a dictionary that is there: the key shows')
    press(m, 'kb_lang')
    names_ = [c[0] for c in m.calls]
    expect(names_.count('im_open_decoder') == 1 and names_.count('im_close_decoder') == 1 and shown(m, 'kb_lang') == (0, 0) and geo(m, 'kb_space')[0] == 79 and keys(m)[0] == 'Q' and said(m, 'kb_lang') == '中' and m.word(ENG) == 0,
           'an engine that fails to initialise: closed again (no dead object left), the key goes away, space is wide again, still English')
    typ(m, 'H')
    expect(field(m) == 'H', 'typing still works after the engine failed to open')
    m = zh_machine()
    m.run(PY.IM['im_open_decoder'], m.cstr('/usr/dict_pinyin.dat'), m.cstr('/usr/dict/dict_pinyin_user.dat'))   # stock's keyboard was opened once: a dead object sits there
    expect(m.engine()[0] and m.engine()[1] == 0, 'setup: stock\'s failed init left an object that is not initialised')
    kopen(m); press(m, 'kb_lang')
    typ(m, 'nihao')
    expect(m.engine()[1] == 1 and said(m, 'kb_c0') == '你好', 'with stock\'s dead object in the way ours replaces it and works')
    m.call(*m.bound[(m.window, DESTROY)][:1], a0=m.bound[(m.window, DESTROY)][1], count=4000000)
    expect(m.engine() == (0, None), 'and closes it with the page')
    m = zh_machine()
    m.open_engine(); live = m.word(ENG)
    kopen(m); press(m, 'kb_lang'); typ(m, 'nihao')
    expect(m.word(ENG) == live and said(m, 'kb_c0') == '你好', 'an engine somebody else opened and initialised is used as it is')
    m.call(*m.bound[(m.window, DESTROY)][:1], a0=m.bound[(m.window, DESTROY)][1], count=4000000)
    expect(m.word(ENG) == live and m.engine()[1] == 1, 'and left open when the page closes')
    expect('hook_pinyin' not in MANIFEST and all(n in pod.FUNCTIONS for n in ('im_get_spl_start_pos', 'im_get_fixed_len')) and len(pod.PINYIN_PINS) >= 26, 'no new hook; the two extra engine functions are declared and pinned')
    stock_demo = stock_demo_bytes()
    wd = lambda b, a: struct.unpack_from('<I', b, pod.fileoff(b, a))[0]
    expect(all(wd(stock_demo, a) == old and wd(m.data, a) == old for a, old, _ in pod.PINYIN_PINS), 'every pinned word of the engine is stock\'s in the stock demo and unchanged in the build')
    expect({n: pod.FUNCTIONS[n][2] for n in PY.IM} == {'im_open_decoder': 0x5c7350, 'im_close_decoder': 0x5c7534, 'im_search': 0x5c760c, 'im_reset_search': 0x5c76e8, 'im_get_candidate': 0x5c7754,
           'im_choose': 0x5c77c0, 'im_get_fixed_len': 0x5c7824, 'im_get_spl_start_pos': 0x5c778c}, 'the engine functions are at the addresses docs/modules/addresses.md records')


# ====================================================================================================================================
# The Chinese layer: composing, the strip, choosing, predictions
# ====================================================================================================================================
def iw(s): return min(max(width(s, PK.CAND_PX) + 2 * PK.CAND_PAD, PK.CAND_MIN), PK.CAND_MAXW)


def strip_on(m): return shown(m, 'kb_strip') == (1, 1)
def py_text(m): return said(m, 'kb_py')


def visible_items(m):
    """[(x in the candidates view, text)] of the item widgets that are shown, left to right."""
    out = [(geo(m, f'kb_c{j}')[0], said(m, f'kb_c{j}')) for j in range(PK.POOL) if shown(m, f'kb_c{j}')[0]]
    return sorted(out)


def cand_texts(m): return [t for _, t in visible_items(m)]


def strip_ptr(m, kind, x, t=1000, y=18):
    """A pointer event on the candidates view at x (its own coordinates)."""
    e = m.alloc(0x30); m.u.mem_write(e, bytes(0x30))
    m.setword(e, PTR[kind]); m.setword(e + 8, t); m.setword(e + 0x18, geo(m, 'kb_cands')[0] + x); m.setword(e + 0x1c, WIN_Y + PK.STRIP_Y + y)
    run_evt(m, 'kb_cands', PTR[kind], e)


def tap_item(m, k, t=2000):
    """A tap on candidate k (it must be on screen): down, up just inside its text."""
    x = geo(m, f'kb_c{k % PK.POOL}')[0] + 3
    strip_ptr(m, 'down', x, t); strip_ptr(m, 'up', x, t + 80)


def searched(m):
    """Search: the text on_done got (None when it was not called)."""
    got = [c[1].encode('latin-1').decode('utf-8') for c in press(m, 'kb_go') if c[0] == 'atoi']
    return got[0] if got else None


def expected(word, n=12):
    """What the real engine says for a pinyin string (a machine of its own): [the first n candidates]."""
    e = PY.Engine({PY.SYS_PATH: DICT_DATA}); e.open_engine()
    return e.candidates(word, n)[1]


def zh_tests(ctx):
    expect = ctx.expect
    m = zh_opened(); press(m, 'kb_lang')

    # 1. Composing: the strip, the pinyin as the engine segments it, the candidates
    typ(m, 'nihao')
    want = expected('nihao', 12)
    expect(strip_on(m) and field(m) == '' and py_text(m) == 'ni hao', 'typing nihao shows the strip with the pinyin as the engine segments it ("ni hao"); the field is untouched')
    got = cand_texts(m)
    expect(got[:3] == ['你好', '你', '拟'] and got == want[:len(got)] and len(got) >= 6, f'the candidates are the engine\'s, 你好 first: {got}')
    items = visible_items(m)
    cx = geo(m, 'kb_cands')[0]
    expect(cx == PK.PY_X + width('ni hao', 16) + PK.PY_X and geo(m, 'kb_cands')[2] == 320 - cx and shown(m, 'kb_sep')[0] == 1 and geo(m, 'kb_sep')[0] == cx - 4, f'the candidates start after the pinyin ({cx}) and a divider ({geo(m, "kb_sep")[0]})')
    xs, acc = [x for x, _ in items], 0
    for tx in want[:len(items)]:
        acc += iw(tx)
    pos = [0]
    for tx in want[:len(items)]: pos.append(pos[-1] + iw(tx))
    expect(xs == [p + PK.CAND_PAD for p in pos[:len(items)]], f'each candidate is as wide as its text (20 px, measured) plus 12 px a side, side by side: {xs[:4]} vs {[p + 12 for p in pos[:4]]}')
    expect(shown(m, 'kb_chl')[0] == 0 and all(shown(m, f'kb_c{j}')[1] == 0 for j in range(12)), 'no highlight yet; the items are never sensitive')
    sy, sh = geo(m, 'kb_strip')[1], geo(m, 'kb_strip')[3]
    expect(sy == 234 and sy + sh == 270 and geo(m, 'kb_pad')[1] == 270 and sy >= 94, 'the strip sits on the pad, below the field')

    # 2. Delete takes the pinyin first
    press(m, 'kb_del', 5000)
    expect(py_text(m) == 'ni ha' and cand_texts(m)[:2] == expected('niha', 3)[:2] and field(m) == '', 'delete removes the last letter of the pinyin (ni ha), the candidates follow, the field is not touched')
    for _ in range(4): press(m, 'kb_del', 5100)
    expect(not strip_on(m) and field(m) == '', 'the last letter gone: no strip')
    typ(m, 'wo'); press(m, 'kb_space')
    expect(field(m) == '我' and strip_on(m), 'wo + space commits 我')
    press(m, 'kb_del', 5200)
    expect(field(m) == '' and not strip_on(m), 'delete with predictions showing hides them and deletes the character')

    # 3. Space commits the first candidate, then the words that follow are offered
    m = zh_opened(); press(m, 'kb_lang')
    typ(m, 'nihao'); press(m, 'kb_space')
    expect(field(m) == '你好' and strip_on(m) and py_text(m) == '' and shown(m, 'kb_sep')[0] == 0, 'space commits 你好 and shows predictions: no pinyin, no divider')
    pred = cand_texts(m)
    expect(pred[:6] == ['啊', '吗', '像', '的', '了', '好'], f'the words that follow 你好: {pred}')
    expect(geo(m, 'kb_cands')[0] == 0 and geo(m, 'kb_cands')[2] == 320 and visible_items(m)[0][0] == PK.CAND_PAD, 'predictions fill the whole strip from its left edge')
    tap_item(m, 1)
    expect(field(m) == '你好吗' and strip_on(m), 'a tap on a prediction appends it ...')
    expect(cand_texts(m)[:3] == PY_PRED('你好吗')[:3] and cand_texts(m)[0] != pred[0], '... and the next ones are offered (what follows 你好吗)')
    press(m, 'kb_space')
    expect(field(m) == '你好吗 ' and not strip_on(m), 'space with only predictions showing hides them and types a space')
    typ(m, 'zhongguo'); press(m, 'kb_space')
    expect(field(m) == '你好吗 中国' and cand_texts(m)[:4] == ['人', '队', '特色', '政府'], 'zhongguo + space: 中国, then 人 队 特色 政府')
    typ(m, 'ma')
    expect(not [t for t in cand_texts(m) if t in ('人', '队')] and py_text(m) == 'ma', 'typing again takes the predictions away')

    # 4. Choosing, a long input in steps
    m = zh_opened(); press(m, 'kb_lang')
    typ(m, 'woxihuantingboke')
    got = cand_texts(m)
    expect(got[:2] == ['我喜欢听博客', '我'], f'the sentence is the first candidate, 我 the second ({got[:3]})')
    expect(width(py_text(m).lstrip('…'), 16) <= PK.PY_MAX and py_text(m).startswith('…') and py_text(m).endswith('ting bo ke'), f'the pinyin is too wide for its room: its end shows after an ellipsis ({py_text(m)!r}, {width(py_text(m), 16)} px of {PK.PY_MAX})')
    tap_item(m, 1)
    expect(field(m) == '我' and py_text(m).endswith('ting bo ke'), f'tapping 我 puts it in the field and keeps the rest of the pinyin ({field(m)!r}, {py_text(m)!r})')
    rest = expected('xihuantingboke', 12)
    expect(cand_texts(m)[:3] == rest[:3], f'the candidates are now those of the rest ({cand_texts(m)[:3]} vs {rest[:3]})')
    tap_item(m, 0)
    expect(field(m) == '我' + rest[0] and not any(c in cand_texts(m) for c in rest[:3]) and strip_on(m) and py_text(m) == '', f'the first candidate of the rest finishes the sentence ({field(m)}); the predictions follow')
    m = zh_opened(); press(m, 'kb_lang')
    typ(m, 'nihao'); tap_item(m, 2)
    expect(field(m) == '拟' and py_text(m) == 'hao', f'a candidate of one character takes one syllable: 拟 and "hao" is left ({field(m)!r}, {py_text(m)!r})')
    tap_item(m, 0)
    expect(field(m) == '拟' + expected('hao', 1)[0], f'then 好: {field(m)}')
    m = zh_opened(); press(m, 'kb_lang')
    typ(m, 'nh')
    expect(py_text(m) == 'n h' and cand_texts(m)[:3] == ['你好', '女孩', '您好'], f'jianpin: nh gives 你好 女孩 您好 (the pinyin "{py_text(m)}")')
    tap_item(m, 1)
    expect(field(m) == '女孩', f'a two character candidate for two initials ({field(m)})')
    m = zh_opened(); press(m, 'kb_lang')
    typ(m, 'xi'); press(m, 'kb_sym'); typ(m, 'an')
    expect(py_text(m) == "xi'an" and cand_texts(m)[0] == '西安', f'the apostrophe key separates syllables: xi\'an 西安 ({py_text(m)!r}, {cand_texts(m)[:2]})')
    press(m, 'kb_sym'); press(m, 'kb_sym')
    expect(py_text(m) == "xi'an'", 'a separator may end the pinyin; a second one in a row does nothing')
    for t in (7000, 7100, 7200, 7300): press(m, 'kb_del', t)
    expect(py_text(m) == 'xi', f'delete takes the letters and the separator off one at a time ({py_text(m)!r})')
    m = zh_opened(); press(m, 'kb_lang')
    press(m, 'kb_sym')
    expect(not strip_on(m) and field(m) == '', 'the separator with nothing typed does nothing')


def zh_search_tests(ctx):
    expect = ctx.expect
    # 5. Search with pinyin pending: it is committed first, as its first candidate
    m = zh_opened(); press(m, 'kb_lang')
    typ(m, 'nihao')
    out = press(m, 'kb_go')
    expect([c[1].encode('latin-1').decode('utf-8') for c in out if c[0] == 'atoi'] == ['你好'] and ('navigator_back',) in out, 'Search with nihao pending searches for 你好 (the first candidate; the engine\'s best, as space)')
    m = zh_opened(); press(m, 'kb_lang')
    typ(m, 'woxihuantingboke')
    expect(searched(m) == '我喜欢听博客', 'a long sentence goes in whole')
    m = zh_opened(); press(m, 'kb_lang')
    typ(m, 'vvv')
    expect(strip_on(m) and py_text(m) == 'vvv' and cand_texts(m) == [], 'letters the engine cannot read: the strip shows them, no candidates')
    expect(searched(m) == 'vvv', 'Search takes the letters as typed when there is no candidate')
    m = zh_opened(); press(m, 'kb_lang')
    typ(m, 'nihaov'); press(m, 'kb_space')
    expect(field(m) == '你好v', f'space with a tail the engine cannot read commits what it can and the tail as typed ({field(m)!r})')
    m = zh_opened(); press(m, 'kb_lang')
    out = press(m, 'kb_go')
    expect(not [c for c in out if c[0] == 'atoi'], 'Search with nothing at all does nothing')
    typ(m, 'ni'); press(m, 'kb_lang')
    typ(m, 'ok')
    expect(searched(m) == '你ok', 'English after Chinese in one text')
    m = zh_opened(); press(m, 'kb_lang')
    typ(m, 'nihao'); run_evt(m, 'btn_return', O['EVT_CLICK'])
    expect(not [c for c in m.calls if c[0] == 'atoi'] and ('navigator_back',) in m.calls, 'Back with pinyin pending cancels: nothing is committed or searched')

    # 6. Clear and the delete key's repeat
    m = zh_opened(); press(m, 'kb_lang')
    typ(m, 'nihao'); press(m, 'kb_space'); typ(m, 'ni')
    run_evt(m, 'kb_clear', O['EVT_CLICK'])
    expect(field(m) == '' and not strip_on(m), 'clear empties the field and drops the pinyin and the strip')
    typ(m, 'a'); press(m, 'kb_del', 5300)
    expect(not strip_on(m) and field(m) == '', 'and the pinyin is really gone (a new letter starts a new one)')
    typ(m, 'nihao')
    x, y = centre(m, 'kb_del')
    ptr(m, 'kb_del', 'down', x, y)
    fn = next(c[1] for c in m.calls if c[0] == 'timer_add')
    expect(py_text(m) == 'ni ha', 'delete (held) takes a pinyin letter on touch down')
    for _ in range(5): m.call(fn, a0=0, count=4000000)
    r = m.call(fn, a0=0, count=4000000)
    expect(py_text(m) == 'ni h' and r == RET_REPEAT, 'and repeats while there is pinyin')
    for _ in range(4): r = m.call(fn, a0=0, count=4000000)
    expect(not strip_on(m) and r == 0 and field(m) == '', 'when the pinyin and the text are both gone the repeat ends')
    ptr(m, 'kb_del', 'up', x, y)


def zh_limit_tests(ctx):
    expect = ctx.expect
    # 7. Limits: the input length, the field's 63 bytes
    m = zh_opened(); press(m, 'kb_lang')
    for _ in range(45): typ(m, 'a')
    expect(width(py_text(m), 16) <= PK.PY_MAX and py_text(m).startswith('…'), 'at most 39 letters of pinyin are taken; the label still fits')
    for _ in range(45): press(m, 'kb_del', 8000)
    expect(not strip_on(m), 'deleted down to nothing')
    m = zh_opened(); press(m, 'kb_lang')
    for _ in range(25):
        typ(m, 'ni'); press(m, 'kb_space')
        if not strip_on(m): break
    text = searched(m)
    expect(text and len(text.encode()) == 63 and set(text) <= set('你') | set('好'), f'the field never takes more than 63 bytes, whole characters only ({len(text.encode()) if text else None} bytes)')
    m = zh_opened(initial='a' * 62); press(m, 'kb_lang')
    typ(m, 'ni'); press(m, 'kb_space')
    expect(searched(m) == 'a' * 62, 'no room for a three byte character: it is not cut in two, the text stays')

    # 8. Glyph coverage: every candidate the engine offers for common input has a glyph in the shipped font
    e = PY.Engine({PY.SYS_PATH: DICT_DATA}); e.open_engine()
    missing = set()
    for w in ('nihao', 'zhongguo', 'bokesou', 'yinyue', 'shanling', 'nh', 'zg', 'bjdx', 'woxihuantingboke', 'zhou', 'jie', 'lun', 'xian', 'shi', 'yi', 'de', 'wo', 'ai', 'zhang', 'li'):
        n = e.search(w)
        for c in ''.join(e.read(n, 60)):
            if FONT.glyph(c) == 0: missing.add(c)
    expect(not missing, f'the font has a glyph for every character of the first 60 candidates of common input ({sorted(missing)})')


def PY_PRED(text):
    e = PY.Engine({PY.SYS_PATH: DICT_DATA}); e.open_engine()
    return e.predicts(text, 10)


# ====================================================================================================================================
# The strip's touches: highlight, tap, scroll
# ====================================================================================================================================
def strip_tests(ctx):
    expect = ctx.expect
    m = zh_opened(); press(m, 'kb_lang')
    typ(m, 'nh')
    cands = expected('nh', 100)
    # a press highlights the item under the finger, a lift on it takes it
    x1 = visible_items(m)[1][0] + 5
    strip_ptr(m, 'down', x1, 100)
    expect(shown(m, 'kb_chl')[0] == 1 and geo(m, 'kb_chl')[0] == visible_items(m)[1][0] - PK.CAND_PAD + 2 and geo(m, 'kb_chl')[1] == PK.CHL_Y and geo(m, 'kb_chl')[2] == iw(cands[1]) - 4 and shown(m, 'kb_chl')[1] == 0,
           'a press shows the highlight behind that item (its width less 2 px a side), insensitive')
    strip_ptr(m, 'up', x1, 180)
    expect(field(m) == cands[1] and shown(m, 'kb_chl')[0] == 0, f'lifting on it takes the candidate ({field(m)}) and hides the highlight')
    # a press on the empty part right of the last item, or left of nothing, takes nothing
    m = zh_opened(); press(m, 'kb_lang')
    typ(m, 'bokesou')
    total = sum(iw(t) for t in expected('bokesou', 100))
    strip_ptr(m, 'down', 315, 100)
    expect(shown(m, 'kb_chl')[0] == (1 if total > 320 - geo(m, 'kb_cands')[0] else 0), 'a press where there is an item highlights it, where there is none it does not')
    strip_ptr(m, 'abort', 315, 110)
    expect(shown(m, 'kb_chl')[0] == 0 and field(m) == '', 'abort drops the highlight and takes nothing')

    # scrolling: a move of 6 px makes the press a scroll; the row follows the finger, the highlight goes, the lift takes nothing
    m = zh_opened(); press(m, 'kb_lang')
    typ(m, 'nh')
    items0 = visible_items(m)
    strip_ptr(m, 'down', 150, 300)
    strip_ptr(m, 'move', 147, 310)
    expect(visible_items(m) == items0 and shown(m, 'kb_chl')[0] == 1, 'a move of 3 px is still a press')
    strip_ptr(m, 'move', 140, 320)
    items1 = visible_items(m)
    expect(shown(m, 'kb_chl')[0] == 0 and [x for x, _ in items1][:2] == [x - 10 for x, _ in items0][:2] or items1[0][0] != items0[0][0], f'past 6 px it is a scroll and the highlight goes: the items moved with the finger ({items0[:2]} -> {items1[:2]})')
    strip_ptr(m, 'move', 100, 330)
    items2 = visible_items(m)
    expect(items2[0][1] != items0[0][1] or items2[0][0] < items0[0][0] - 40, f'it follows the finger (the first items scrolled out: {items2[:3]})')
    strip_ptr(m, 'up', 100, 340)
    expect(field(m) == '' and shown(m, 'kb_chl')[0] == 0, 'lifting after a scroll takes nothing')
    # the ring of widgets: an item always sits in widget k % 12; the visible ones are consecutive and cover the strip
    cw = geo(m, 'kb_cands')[2]
    vis = [(j, geo(m, f'kb_c{j}')[0], said(m, f'kb_c{j}')) for j in range(12) if shown(m, f'kb_c{j}')[0]]
    texts = [t for _, _, t in sorted(vis, key=lambda v: v[1])]
    allc = expected('nh', 100)
    first = allc.index(texts[0]) if texts[0] in allc else None
    expect(first is not None and texts == allc[first:first + len(texts)] and all(sorted(vis, key=lambda v: v[1])[i][0] == (first + i) % 12 for i in range(len(texts))), f'the visible items are consecutive candidates, candidate k in widget k % 12 ({texts})')
    expect(sum(iw(t) for t in allc[first:first + len(texts)]) >= cw - 0, 'and they cover the strip')
    # scroll to the very end: more candidates are read as the strip nears the end of what was loaded; the scroll stops at the last
    for i in range(60):
        strip_ptr(m, 'down', 300, 1000 + 10 * i); strip_ptr(m, 'move', 20, 1001 + 10 * i); strip_ptr(m, 'up', 20, 1002 + 10 * i)
    vis = [(geo(m, f'kb_c{j}')[0], said(m, f'kb_c{j}')) for j in range(12) if shown(m, f'kb_c{j}')[0]]
    texts = [t for _, t in sorted(vis)]
    expect(texts and texts[-1] == allc[-1] and len(allc) == 100 and sum(iw(t) for t in allc) > 320, f'many drags later the row ends on the last of the 100 candidates the layer takes ({texts[-1:]} vs {allc[-1]})')
    right = max(x + width(t, 20) for x, t in vis)
    expect(right <= geo(m, 'kb_cands')[2] and right >= geo(m, 'kb_cands')[2] - 2 * PK.CAND_PAD - 6, f'the last item\'s text ends at the right edge less its padding ({right} of {geo(m, "kb_cands")[2]})')
    # a tap on an item far along takes that very candidate
    k = allc.index(texts[1])
    x = next(x for x, t in sorted(vis) if t == texts[1]) + 3
    strip_ptr(m, 'down', x, 5000); strip_ptr(m, 'up', x, 5080)
    expect(field(m) == allc[k], f'a tap on an item far along the row takes exactly that candidate ({field(m)!r} == {allc[k]!r})')

    # a new letter starts at the left again; predictions scroll too
    m = zh_opened(); press(m, 'kb_lang')
    typ(m, 'nh')
    strip_ptr(m, 'down', 300, 100); strip_ptr(m, 'move', 100, 110); strip_ptr(m, 'up', 100, 120)
    typ(m, 'x')
    expect(visible_items(m)[0][0] == PK.CAND_PAD and said(m, 'kb_c0') == expected('nhx', 1)[0], 'a new letter shows the new candidates from the start of the row')

    # touches on the strip while nothing is shown take nothing; the lang key and the strip do not collide
    m = zh_opened(); press(m, 'kb_lang')
    strip_ptr(m, 'down', 30, 10); strip_ptr(m, 'up', 30, 20)
    expect(field(m) == '' and not strip_on(m), 'a touch on the (hidden) strip does nothing')


# ====================================================================================================================================
# The hit test of demo on the real tree: the strip
# ====================================================================================================================================
def hit_tests(ctx):
    expect = ctx.expect

    def hit_tree(m):
        root = asset_tree(os.path.join(RAW, 'ui', 'm1plus_keyboard.bin'))
        root.y = WIN_Y
        def sync(n):
            h = m.widgets.get(n.name)
            if h is not None and (h, 'x') in m.props:
                n.x, n.y, n.w, n.h = (m.props[(h, k)] for k in 'xywh')
                n.flags = F_ENABLE | (F_VISIBLE if m.props.get((h, 'visible'), 1) else 0) | (F_SENSITIVE if m.props.get((h, 'sensitive'), 1) else 0)
            for c in n.children: sync(c)
        for c in root.children: sync(c)
        root.by_addr = lay_out(m, root)
        return root

    def target(m, root, wx, wy):
        w, name = root.addr, root.name
        while True:
            t = m.call(FIND_TARGET, a0=w, a1=wx, a2=WIN_Y + wy, count=200000)
            if not t or (root.by_addr[t].flags & 9) != 9: return name
            w, name = t, root.by_addr[t].name

    m = opened()
    root = hit_tree(m)
    expect(target(m, root, 100, 250) == 'm1plus_keyboard_page', 'the strip hidden: its area belongs to the window, not to the strip or the candidates view')
    m = zh_opened(); press(m, 'kb_lang'); typ(m, 'nihao')
    root = hit_tree(m)
    cx = geo(m, 'kb_cands')[0]
    expect(target(m, root, cx + 20, PK.STRIP_Y + 18) == 'kb_cands' and target(m, root, 310, PK.STRIP_Y + 2) == 'kb_cands', 'the strip shown: a touch over the candidates (an item or the empty part) lands on the candidates view')
    expect(target(m, root, 20, PK.STRIP_Y + 18) == 'kb_strip', 'over the pinyin label it lands on the strip (the label takes none)')
    expect(target(m, root, 100, PK.STRIP_Y - 2) == 'm1plus_keyboard_page', 'just above the strip is the window')
    lay = PK.layout('abc', lang=True, zh=True)
    x, y, w = lay['fn']['lang']
    expect(target(m, root, x + w // 2, PAD_Y + y + 18) == 'kb_lang' and target(m, root, x, PAD_Y + y) == 'kb_lang' and target(m, root, x + w - 1, PAD_Y + y + 35) == 'kb_lang', 'the language key takes touches over its rectangle')
    x, y, w = lay['fn']['space']
    expect(target(m, root, x + w // 2, PAD_Y + y + 18) == 'kb_space' and target(m, root, x + 1, PAD_Y + y + 1) == 'kb_space', 'space (narrower now) over its own')
    x, y, w = lay['fn']['sym']
    expect(target(m, root, x + w // 2, PAD_Y + y + 18) == 'kb_sym', 'the pinyin separator takes the shift key\'s place')
    kinds = []
    for xx in (31, 32, 33):
        kinds.append(target(m, root, xx, PAD_Y + 24))
    expect(kinds == ['kb_pad'] * 3, f'the gaps between keys are still the pad\'s (the payload resolves them): {kinds}')


# ====================================================================================================================================
# The model against the language key's sweep
# ====================================================================================================================================
def lang_gap_tests(ctx):
    expect = ctx.expect
    m = zh_opened(); press(m, 'kb_lang')
    by_handle = {h: n for n, h in m.widgets.items()}
    fn_widget = {'shift': 'kb_shift', 'sym': 'kb_sym', 'del': 'kb_del', 'mode': 'kb_mode', 'lang': 'kb_lang', 'space': 'kb_space', 'go': 'kb_go'}
    lay = PK.layout('abc', lang=True, zh=True)
    bad, t = [], 20000
    for y in sorted(set(range(0, 180, 9)) | {131, 137, 138, 175}):
        for x in sorted(set(range(0, 320, 11)) | {2, 41, 42, 43, 78, 79, 80, 118, 119, 120, 121, 122, 123, 240, 241, 242, 243, 244, 245}):
            t += 1
            ptr(m, 'kb_pad', 'down', x, WIN_Y + PAD_Y + y, t)
            pressed = [by_handle.get(c[1]) for c in m.calls if c[0] == 'widget_set_state' and c[2] == 'pressed']
            kind, ident, d2 = PK.nearest_key(lay, x, y)
            name = f'kb_k{ident}' if kind == 'char' else fn_widget[ident]
            if pressed != ([name] if d2 > 0 else []): bad.append((x, y, pressed, name))
            ptr(m, 'kb_pad', 'abort', x, WIN_Y + PAD_Y + y, t)
    expect(not bad, f'with the language key and without shift (the Chinese layer) every point of the pad presses the key the model picks ({bad[:2]})')
    # a gap touch that resolves to the language key switches layers when the finger lifts; one to a char key composes pinyin
    ptr(m, 'kb_pad', 'down', 78, WIN_Y + PAD_Y + 150, 2); ptr(m, 'kb_pad', 'up', 78, WIN_Y + PAD_Y + 150, 82)
    expect(said(m, 'kb_lang') == '中' and keys(m)[0] == 'Q', 'a touch in the gap between 123 and the language key (one px from it) taps the key: back to English')
    press(m, 'kb_lang')
    ptr(m, 'kb_pad', 'down', 31, WIN_Y + PAD_Y + 24, 5); ptr(m, 'kb_pad', 'up', 31, WIN_Y + PAD_Y + 24, 85)
    expect(py_text(m) == 'q' and strip_on(m), 'on the Chinese layer a gap touch between Q and W composes a q')


def name_tests(ctx):
    """The New playlist consumer (patch/playlists.c pl_create / pl_named): title, placeholder, the Done label (KB_DONE), the name through createPlayListItem after the page was told to close,
    nothing for an empty name (the keyboard stays), Back, the two messages, the 63 byte limit under stock's 127."""
    expect = ctx.expect
    def create(**kw):
        m = keyboard_machine()
        m.setword(STACK + 16, 0); m.setword(STACK + 20, DEFS['KB_DONE'])
        assert DEFS['KB_DONE'] == 2
        r = m.call(PSYMS['keyboard_open'], a0=m.cstr('New playlist'), a1=m.cstr('Enter a playlist name'), a2=0, a3=PSYMS['pl_named'], count=40000000)
        assert r == 0
        for k, v in kw.items(): setattr(m, k, v)
        return m
    def made(m): return [c for c in m.calls if c[0] == 'createPlayListItem']
    def toast_calls(m): return [c for c in m.calls if c[0] == 'toast']
    m = create()
    expect(said(m, 'label_title') == 'New playlist' and said(m, 'kb_hint') == 'Enter a playlist name' and said(m, 'kb_go') == 'Done' and field(m) == '',
           f'New playlist: the keyboard has the stock title and hint and the action key reads Done ({said(m, "label_title")}, {said(m, "kb_hint")}, {said(m, "kb_go")})')
    expect(not [c for c in m.calls if c[0] in ('navigator_to_with_context', 'createPlayListItem')], 'opening creates nothing and opens no stock dialog')
    def rowgeo(m):
        f = geo(m, 'kb_field')
        return f[:4], geo(m, 'kb_clear')[:2], geo(m, 'kb_caret')[:2], shown(m, 'kb_card'), shown(m, 'kb_capsule'), shown(m, 'kb_mag'), shown(m, 'kb_field')
    f, cl, car, card, cap, mag, fld = rowgeo(m)
    expect(card == (1, 1) and cap == (0, 0) and fld[1] == 1 and f == (DEFS['KB_NAME_X'] - DEFS['KB_TEXT_X'], DEFS['KB_NAME_Y'] + DEFS['KB_NAME_DY'], DEFS['KB_NAME_FIELD_W'] + DEFS['KB_TEXT_X'], DEFS['KB_FIELD_H'])
           and f[0] + DEFS['KB_TEXT_X'] == 24 and f[0] + f[2] - DEFS['KB_CLEAR_W'] + DEFS['KB_CLEAR_W'] // 2 == 287 and cl == (f[2] - DEFS['KB_CLEAR_W'], 0) and car[0] == DEFS['KB_TEXT_X'],
           f'a name entry: the card row shown, the capsule hidden and insensitive, the field on the row (text at x 24, 6 px down), the clear button at its right end, the caret at the text origin ({rowgeo(m)})')
    mt = create(); typ(mt, 'M')
    expect(shown(mt, 'kb_clear') == (1, 1) and caret_x(mt) == 30 + width('M') + 1, 'typing in the row: the clear button shows, the caret follows the text')
    mn = opened()
    f, cl, car, card, cap, mag, fld = rowgeo(mn)
    expect(f == (10, 58, 300, 36) and cl == (264, 0) and card == (0, 0) and cap[0] == 1 and fld[1] == 1, f'a search entry keeps the capsule and the old field geometry ({rowgeo(mn)})')
    m0 = opened()
    expect(said(m0, 'kb_go') is None and not [c for c in m0.calls if c[0] == 'widget_set_tr_text' and c[1] == m0.widgets['kb_go']], 'without KB_DONE the action key is the asset\'s Search')
    expect(shown(m, 'btn_backtoplayer') == (0, 0) and shown(m0, 'btn_backtoplayer') == (1, 1), f'a name entry hides Now Playing (hidden and insensitive), a search entry keeps it ({shown(m, "btn_backtoplayer")}, {shown(m0, "btn_backtoplayer")})')
    m.calls = []
    press(m, 'kb_go')
    expect(shown(m, 'kb_go') == (1, 1) and not made(m) and ('navigator_back',) not in m.calls, 'Done with an empty field does nothing and the keyboard stays')
    press(m, 'kb_space'); press(m, 'kb_go')
    expect(not made(m) and ('navigator_back',) not in m.calls, 'a field of spaces is empty as well')
    typ(m, 'Mix'); press(m, 'kb_space'); m.calls = []
    press(m, 'kb_go')
    order = [c[0] for c in m.calls if c[0] in ('navigator_back', 'loadLocalClassList', 'createPlayListItem')]
    expect(order == ['navigator_back', 'loadLocalClassList', 'createPlayListItem'] and made(m) == [('createPlayListItem', 'Mix', 0)] and not toast_calls(m),
           f'Done: the page is told to close, the stock list is read, createPlayListItem gets the trimmed name ({order}, {made(m)})')
    for ret, key in ((-1, 'msg_playlistfull'), (-2, 'msg_playlistexist')):
        m = create(create_ret=ret); typ(m, 'Mix'); m.calls = []
        press(m, 'kb_go')
        expect(toast_calls(m) == [('toast', key, 1, 2000)] and [c[0] for c in m.calls if c[0] in ('navigator_back', 'toast')] == ['navigator_back', 'toast'],
               f'{key} is shown in the stock message box after the keyboard closed ({toast_calls(m)})')
    m = create(); typ(m, 'Mix'); m.calls = []
    run_evt(m, 'btn_return', O['EVT_CLICK'])
    expect(not made(m) and ('navigator_back',) in m.calls and not toast_calls(m), 'Back creates nothing')
    m = create(); typ(m, 'A' + 'a' * 69); m.calls = []
    press(m, 'kb_go')
    expect(len(made(m)) == 1 and made(m)[0][1] == 'A' + 'a' * 62, 'the keyboard\'s own 63 bytes are the name\'s limit (stock\'s edit took 127)')
    m = create(); typ(m, 'Ab'); m.calls = []
    press(m, 'kb_go')
    expect(made(m)[0][1] == 'Ab', 'the name is what the field shows')
    for loc in pod_i18n.LOCALES:   # the Done key's text fits its 74 px
        t = pod_i18n.TEXT['Done'][loc]
        expect(width(t, 15) <= PK.KB_MODE_W - 8, f'Done fits the action key in {loc} ({t}: {width(t, 15)} px)')


def attach(m, flags=0, ph=None, tx=0, tw=130, cy=15):
    """keyboard_attach(win, placeholder, text_x, text_w, caret_y, flags, on_change, on_go): on_change records ('atoi', text), on_go ('on_backtoplayer_onclick',)."""
    m.setword(STACK + 16, cy); m.setword(STACK + 20, flags); m.setword(STACK + 24, DONE()); m.setword(STACK + 28, CANCEL)
    r = m.call(PSYMS['keyboard_attach'], a0=m.window, a1=m.cstr(ph) if ph else 0, a2=tx, a3=tw, count=40000000)
    return r - (1 << 32) if r >= 1 << 31 else r


def raw_text(m):
    """keyboard_text(): the committed text as the payload holds it (UTF-8)."""
    return m.read_cstr(m.call(PSYMS['keyboard_text'], count=100000)).encode('latin-1').decode('utf-8')


def password_tests(ctx):
    """KB_PASSWORD (keyboard_attach flags): English only, a lowercase page, spaces anywhere, the text as typed, dots with an eye, the action key's label and its dimmed state."""
    expect = ctx.expect
    PW = DEFS['KB_PASSWORD']
    # 1. Chinese on and the dictionary there: a password field has no language key and no composition, a plain one has both
    m = zh_machine()
    expect(attach(m) == 0 and shown(m, 'kb_lang') == (1, 1), 'the same machine without the flag: the language key (the setting is on)')
    m = zh_machine()
    expect(attach(m, PW, tw=130) == 0 and shown(m, 'kb_lang') == (0, 0) and geo(m, 'kb_space')[0] == 79 and geo(m, 'kb_space')[2] == 163 and not [c for c in m.calls if c[0] in ('im_open_decoder', 'access')],
           'KB_PASSWORD with Chinese on: no language key, space is as wide as with one keyboard, the dictionary is never looked at')
    typ(m, 'nihao')
    expect(raw_text(m) == 'nihao' and not strip_on(m) and m.word(PY.ENGINE_PTR) == 0 and not [c for c in m.calls if c[0] in ('im_search', 'im_open_decoder')], 'letters are typed as they are: no pinyin, no candidate strip, no engine')
    # a remembered Chinese layer does not carry over either
    m = zh_machine(); m.setword(PSYMS['kb_memo'], 1)
    expect(attach(m, PW) == 0 and shown(m, 'kb_lang') == (0, 0) and keys(m)[0] == 'q', 'a remembered Chinese layer does not make a password field Chinese')
    # 2. Lowercase start, no capital after the field was emptied, spaces anywhere, backtick
    m = keyboard_machine(); m.fs[KBZH] = b'1\n'
    attach(m, PW)
    expect(keys(m)[0] == 'q' and shown(m, 'kb_shift') == (1, 1) and shown(m, 'kb_shifton') == (0, 0) and said(m, 'kb_mode') == '123', 'the pad starts on the lowercase page (an empty search field starts on capitals)')
    typ(m, 'a'); press(m, 'kb_del')
    expect(raw_text(m) == '' and keys(m)[0] == 'q' and shown(m, 'kb_shifton') == (0, 0), 'emptying the field does not turn capitals on')
    press(m, 'kb_space'); press(m, 'kb_space'); typ(m, 'a'); press(m, 'kb_space'); press(m, 'kb_space')
    expect(raw_text(m) == '  a  ', f'spaces are typed at the start, doubled and at the end, and the text is returned untrimmed ({raw_text(m)!r})')
    press(m, 'kb_shift'); typ(m, 'B')
    expect(raw_text(m) == '  a  B' and keys(m)[0] == 'q', 'shift still works for one capital, then back to lowercase')
    press(m, 'kb_mode'); press(m, 'kb_sym')
    expect('`' in keys(m) and keys(m).index('`') == 19, 'the backtick is on the #+= page, last key of the second row')
    typ(m, '`')
    expect(raw_text(m).endswith('B`'), 'and types')
    press(m, 'kb_mode')
    expect(keys(m)[0] == 'q', 'ABC from a symbol page returns to lowercase')
    m2 = keyboard_machine(); attach(m2, PW); press(m2, 'kb_mode'); press(m2, 'kb_mode')
    expect(keys(m2)[0] == 'q', 'and for an empty field too')
    # a search field is as before: no leading space, no double space
    m3 = keyboard_machine(); attach(m3)
    press(m3, 'kb_space'); typ(m3, 'A'); press(m3, 'kb_space'); press(m3, 'kb_space')
    expect(raw_text(m3) == 'A ', 'a field without the flag: no space at the start, none after a space')
    # 3. The text is dots; the eye shows it; the caret follows what is shown
    m = keyboard_machine(); attach(m, PW, tw=130)
    expect(said(m, 'kb_text') in (None, '') and shown(m, 'kb_hint')[0] == 1 and shown(m, 'kb_clear') == (0, 0), 'empty: no text; there is no clear button in a password field')
    typ(m, 'ab')
    dot = '•'
    expect(said(m, 'kb_text') == dot * 2 and caret_x(m) == width(dot * 2) + 1 and geo(m, 'kb_caret')[1] == 15 and shown(m, 'kb_clear') == (0, 0), f'two characters: two dots, the caret after them by their measured width ({said(m, "kb_text")!r}, {caret_x(m)})')
    expect(FONT.glyph(dot) != 0, 'the shipped font has the dot')
    press(m, 'kb_space')
    expect(said(m, 'kb_text') == dot * 3, 'a space is a dot too')
    m.call(PSYMS['keyboard_set_mask'], a0=0, count=2000000)
    expect(said(m, 'kb_text') == 'ab ' and caret_x(m) == width('ab ') + 1 and raw_text(m) == 'ab ', 'the eye open: the text, the caret on its width')
    typ(m, 'c')
    expect(said(m, 'kb_text') == 'ab c' and caret_x(m) == width('ab c') + 1, 'typing while it is shown')
    m.call(PSYMS['keyboard_set_mask'], a0=1, count=2000000)
    expect(said(m, 'kb_text') == dot * 4 and caret_x(m) == width(dot * 4) + 1, 'and hidden again')
    typ(m, 'defghijklmnopqrstuvwxyz')
    t = said(m, 'kb_text')
    expect(t.startswith('…') and set(t[1:]) == {dot} and width(t) <= 130 and caret_x(m) == width(t) + 1 and raw_text(m) == 'ab cdefghijklmnopqrstuvwxyz', f'a long password: dots cut with an ellipsis to the field ({width(t)} px, {len(t)} chars), the caret at its end, the text whole')
    m.call(PSYMS['keyboard_set_mask'], a0=0, count=2000000)
    t = said(m, 'kb_text')
    expect(t.startswith('…') and width(t) <= 130 and t.endswith('xyz') and caret_x(m) == width(t) + 1, f'shown, the end of the text after an ellipsis ({t!r})')
    for _ in range(40): press(m, 'kb_del')
    expect(raw_text(m) == '' and said(m, 'kb_text') in (None, '') and caret_x(m) == 0, 'delete empties it, the caret goes back to the text start')
    typ(m, 'x')
    expect(said(m, 'kb_text') == 'x', 'with the eye open: the text is shown as typed')
    # 4. The text limit of a password field is KB_PASS_MAX (127: a WPA3 password; a 64 digit raw PSK needs more than 63); a plain field keeps 63
    m = keyboard_machine(); attach(m, PW)
    for _ in range(140): typ(m, 'a')
    expect(DEFS['KB_PASS_MAX'] == 127 and len(raw_text(m)) == 127, f'a password field takes 127 characters and not one more ({len(raw_text(m))})')
    t = said(m, 'kb_text')
    expect(t.startswith('…') and set(t[1:]) == {'•'} and width(t) <= 130 and caret_x(m) == width(t) + 1, 'and shows dots for them, cut to the field')
    m.call(PSYMS['keyboard_set_mask'], a0=0, count=2000000)
    expect(said(m, 'kb_text').endswith('aaa') and len(raw_text(m)) == 127, 'with the eye open too')
    m = keyboard_machine(); attach(m, 0)
    typ(m, 'A')
    for _ in range(70): typ(m, 'a')
    expect(len(raw_text(m)) == 63, 'a plain embedded field keeps 63 bytes')
    # 5. The action key: its label, dimmed and inert, enabled
    m = keyboard_machine(); attach(m, PW)
    m.calls = []
    m.call(PSYMS['keyboard_set_go'], a0=m.cstr('Join'), a1=0, count=2000000)
    expect(('widget_set_tr_text', m.widgets['kb_go'], 'Join') in m.calls and shown(m, 'kb_go')[1] == 0 and ('widget_set_state', m.widgets['kb_go'], 'disable') in m.calls, 'Join, dimmed (the disable style) and insensitive')
    typ(m, 'password')
    press(m, 'kb_go')
    expect(not [c for c in m.calls if c[0] == 'on_backtoplayer_onclick'], 'a dimmed key does nothing: on_go does not fire')
    gx, gy, gw, gh = geo(m, 'kb_go')
    ptr(m, 'kb_pad', 'down', gx + gw // 2, WIN_Y + PAD_Y + gy - 4, 3000)
    seen = list(m.calls)
    ptr(m, 'kb_pad', 'up', gx + gw // 2, WIN_Y + PAD_Y + gy - 4, 3080)
    seen += m.calls
    expect(any(c[0] == 'widget_set_state' for c in seen) is False and not [c for c in seen if c[0] == 'on_backtoplayer_onclick'], 'a touch between the keys that the gap rule gives the dimmed key: no pressed look, nothing')
    m.calls = []
    m.call(PSYMS['keyboard_set_go'], a0=0, a1=1, count=2000000)
    expect(('widget_set_state', m.widgets['kb_go'], 'normal') in m.calls and shown(m, 'kb_go')[1] == 1 and not [c for c in m.calls if c[0] == 'widget_set_tr_text'], 'enabled again, the label as it was set (NULL keeps it)')
    press(m, 'kb_go')
    expect([c for c in m.calls if c[0] == 'on_backtoplayer_onclick'] == [('on_backtoplayer_onclick',)] and ('navigator_back',) not in m.calls, 'enabled: on_go fires once, no page is closed')
    m.call(PSYMS['keyboard_detach'], count=2000000)
    expect(b'password' not in bytes(m.u.mem_read(PSYMS['kb'], 0x1400)), 'keyboard_detach wipes the typed text from the keyboard\'s state')


def refocus(m, ph, tw, flags, text):
    """keyboard_refocus(placeholder, text_w, flags, text, on_change, on_go): another field of the page takes the pad."""
    m.setword(STACK + 16, DONE()); m.setword(STACK + 20, CANCEL)
    r = m.call(PSYMS['keyboard_refocus'], a0=m.cstr(ph) if ph else 0, a1=tw, a2=flags, a3=m.cstr(text) if text is not None else 0, count=40000000)
    return r - (1 << 32) if r >= 1 << 31 else r


def refocus_tests(ctx):
    """keyboard_refocus: one embedded keyboard serving the page's fields in turn (patch/wifipage.c Join Wi-Fi Network): the mode, text, text room and placeholder of the new field, the pending state of the old one dropped."""
    expect = ctx.expect
    PW = DEFS['KB_PASSWORD']
    dot = '•'
    m = keyboard_machine()
    expect(refocus(m, 'x', 100, 0, 'a') == -1, 'no keyboard: -1')
    # a plain field and a password field in turn: the mode, the text each holds, the dots, the hint, the text room
    m = zh_machine()
    expect(attach(m, 0, 'Network Name', tw=156) == 0 and shown(m, 'kb_lang') == (1, 1) and said(m, 'kb_hint') == 'Network Name' and keys(m)[0] == 'Q', 'a plain field with Chinese on: the language key, capitals, the placeholder')
    typ(m, 'H')
    r = refocus(m, None, 118, PW, 'hunter22')
    calls = list(m.calls)
    expect(r == 0 and raw_text(m) == 'hunter22' and said(m, 'kb_text') == dot * 8 and shown(m, 'kb_lang') == (0, 0) and keys(m)[0] == 'q' and shown(m, 'kb_clear') == (0, 0) and said(m, 'kb_hint') in (None, ''),
           'the password field: its text as dots, no language key, lowercase, no clear button, no placeholder')
    expect(('atoi', 'hunter22') in calls, 'on_change got the new field\'s text')
    typ(m, 'x')
    expect(raw_text(m) == 'hunter22x' and said(m, 'kb_text') == dot * 9, 'typing goes into the password')
    m.call(PSYMS['keyboard_set_mask'], a0=0, count=2000000)
    expect(said(m, 'kb_text') == 'hunter22x', 'the eye shows it')
    expect(refocus(m, 'Network Name', 156, 0, 'Home') == 0 and raw_text(m) == 'Home' and said(m, 'kb_text') == 'Home' and shown(m, 'kb_lang') == (1, 1) and said(m, 'kb_hint') == 'Network Name' and shown(m, 'kb_clear') == (1, 1),
           'back to the plain field: its text as typed (not masked), the language key, the clear button')
    typ(m, 'x')
    expect(raw_text(m) == 'Homex', 'and it types')
    # a layer the plain field had stays open for it; the password field is English; a pending composition does not travel
    m = zh_machine()
    attach(m, 0, 'N', tw=156)
    press(m, 'kb_lang'); typ(m, 'ni')
    expect(strip_on(m) and said(m, 'kb_lang') == 'EN', 'the Chinese layer with pinyin pending: the candidate strip')
    refocus(m, None, 118, PW, '')
    expect(not strip_on(m) and raw_text(m) == '' and shown(m, 'kb_lang') == (0, 0) and keys(m)[0] == 'q' and shown(m, 'kb_shift') == (1, 1), 'the password field: no composition, no strip, English letters')
    typ(m, 'nihao')
    expect(raw_text(m) == 'nihao' and not strip_on(m), 'letters are typed as they are')
    refocus(m, 'N', 156, 0, 'abc')
    expect(said(m, 'kb_lang') == 'EN' and shown(m, 'kb_lang') == (1, 1) and raw_text(m) == 'abc' and m.opened.count(PY.SYS_PATH) == 1, 'the plain field is on the Chinese layer again, the engine opened once')
    typ(m, 'ni')
    expect(strip_on(m), 'and composes')
    # the 123 page of one field does not leak a wrong geometry into the next
    m = keyboard_machine()
    attach(m, 0, None, tw=156)
    press(m, 'kb_mode')
    expect(keys(m)[0] == '1', 'the 123 page')
    refocus(m, None, 118, PW, 'ab')
    expect(keys(m)[0] == 'q' and not layout_ok(m, 'abc'), 'the new field starts on the lowercase page, the keys where the model puts them')
    typ(m, 'c')
    expect(raw_text(m) == 'abc', 'and types')
    # the limit follows the field: 127 in a password field, 63 in a plain one (a longer text handed over is cut to it)
    refocus(m, None, 118, PW, 'p' * 140)
    expect(len(raw_text(m)) == 127, 'a password field is cut to 127 bytes')
    refocus(m, 'N', 156, 0, 'n' * 100)
    expect(len(raw_text(m)) == 63, 'and the plain field after it to 63')
    refocus(m, None, 118, PW, '')
    for _ in range(140): typ(m, 'a')
    expect(len(raw_text(m)) == 127, 'typing into the password field again stops at 127')
    m.call(PSYMS['keyboard_detach'], count=2000000)
    expect(b'abc' not in bytes(m.u.mem_read(PSYMS['kb'], 0x1400)), 'detach wipes it')


KBFR = '/mnt/data/m1plus/keyboard-french'


def fr_machine(fr=True, zh=False, dictionary=True):
    """The keyboard's machine with the French keyboard on (Settings > General > Keyboards > French (AZERTY)), and Chinese (Pinyin) too when zh."""
    m = zh_machine(setting=zh, dictionary=dictionary)
    if fr: m.fs[KBFR] = b'1\n'
    return m


def reopen(m):
    m.call(*m.bound[(m.window, DESTROY)][:1], a0=m.bound[(m.window, DESTROY)][1], count=4000000)
    assert kopen(m) == 0


def french_tests(ctx):
    """The French (AZERTY) layer: its letter pages, the language key cycling EN -> FR -> 中 -> EN over the keyboards that are on, the remembered layer, password fields."""
    expect = ctx.expect
    expect(PK.FR_ROWS['abc'] == ('azertyuiop', 'qsdfghjklm', 'wxcvbn') and PK.FR_ROWS['ABC'] == tuple(r.upper() for r in PK.FR_ROWS['abc']) and sorted(''.join(PK.FR_ROWS['abc'])) == sorted('abcdefghijklmnopqrstuvwxyz'),
           'the model: AZERTY, 10 + 10 + 6 keys, every letter once')
    lay = PK.layout('abc', lang=True, fr=True)
    expect([c for c, *_ in lay['keys']] == list('azertyuiopqsdfghjklmwxcvbn') and [x for _, x, y, _ in lay['keys'] if y == 94] == [PK.row_x(6, 29) + 32 * i for i in range(6)]
           and lay['fn'] == PK.layout('abc', lang=True)['fn'] and PK.layout('123', lang=True, fr=True) == PK.layout('123', lang=True), 'layout(fr=True): the AZERTY keys, the function keys and the symbol pages as English')

    # 1. French only on: the key appears, EN -> FR -> EN
    m = fr_machine(); kopen(m)
    x, y, w = lay['fn']['lang']
    expect(shown(m, 'kb_lang') == (1, 1) and geo(m, 'kb_lang') == (x, y, w, 36) and said(m, 'kb_lang') == 'FR' and geo(m, 'kb_space')[:3] == lay['fn']['space'] and not layout_ok(m, 'ABC', lang=True),
           'French on: the language key (row-four geometry of two keyboards) reads FR on the English layer')
    expect(not [c for c in m.calls if c[0] in ('im_open_decoder', 'access')], 'French needs no dictionary and no engine')
    press(m, 'kb_lang')
    expect(said(m, 'kb_lang') == 'EN' and keys(m)[:10] == list('AZERTYUIOP') and not layout_ok(m, 'ABC', lang=True, fr=True) and shown(m, 'kb_shifton') == (1, 1) and shown(m, 'kb_sym') == (0, 0),
           'the French layer: AZERTY capitals for an empty field, shift on, the key reads EN')
    typ(m, 'A')
    expect(field(m) == 'A' and keys(m)[:10] == list('azertyuiop') and not layout_ok(m, 'abc', lang=True, fr=True) and shown(m, 'kb_shift') == (1, 1), 'a capital, then lowercase AZERTY (shift as in English)')
    typ(m, 'z'); press(m, 'kb_shift'); typ(m, 'Q')
    expect(field(m) == 'AzQ' and keys(m)[0] == 'a', 'letters type as they are; shift is one-shot')
    press(m, 'kb_del'); press(m, 'kb_del'); press(m, 'kb_del')
    expect(field(m) == '' and shown(m, 'kb_shifton') == (1, 1) and keys(m)[0] == 'A', 'an emptied field turns shift on again')
    press(m, 'kb_mode'); press(m, 'kb_mode')
    expect(keys(m)[0] == 'A' and said(m, 'kb_lang') == 'EN', '123 and back keeps the French letters')
    typ(m, 'M'); press(m, 'kb_mode')
    expect(keys(m)[:10] == list('1234567890') and said(m, 'kb_lang') == 'EN' and shown(m, 'kb_lang') == (1, 1), 'the 123 page is the English one, the key stays')
    press(m, 'kb_lang')
    expect(said(m, 'kb_lang') == 'FR' and keys(m)[:10] == list('qwertyuiop') and not layout_ok(m, 'abc', lang=True), 'the key on the 123 page switches layer and shows its letters (English now, the key reads FR)')
    expect(not [c for c in m.calls if c[0] in ('im_open_decoder', 'access')], 'no engine through all of it')

    # 2. All three on: EN -> FR -> 中 -> EN
    m = fr_machine(zh=True); kopen(m)
    expect(said(m, 'kb_lang') == 'FR' and shown(m, 'kb_lang') == (1, 1), 'EN: the key reads FR')
    press(m, 'kb_lang')
    expect(said(m, 'kb_lang') == '中' and keys(m)[0] == 'A' and m.word(PY.ENGINE_PTR) == 0, 'FR: the key reads 中, the engine is not open')
    press(m, 'kb_lang')
    expect(said(m, 'kb_lang') == 'EN' and keys(m)[0] == 'q' and shown(m, 'kb_shift') == (0, 0) and said(m, 'kb_sym') == "'" and m.engine()[1] == 1 and not layout_ok(m, 'abc', lang=True, zh=True), '中: Chinese letters, no shift, the key reads EN, the engine open')
    typ(m, 'nihao')
    expect(said(m, 'kb_c0') == '你好', 'pinyin composes')
    press(m, 'kb_lang')
    expect(field(m) == '你好' and said(m, 'kb_lang') == 'FR' and keys(m)[0] == 'q' and shown(m, 'kb_shift') == (1, 1) and not strip_on(m), 'EN again (pending pinyin committed first), the key reads FR')
    press(m, 'kb_lang'); typ(m, 'a')
    expect(said(m, 'kb_lang') == '中' and field(m) == '你好a' and keys(m)[0] == 'a', 'a French letter types as it is (no composition)')
    press(m, 'kb_lang'); press(m, 'kb_lang'); press(m, 'kb_lang')
    expect(said(m, 'kb_lang') == '中' and keys(m)[0] == 'a', 'three taps are a full turn')

    # 3. Chinese and French on but no dictionary: EN <-> FR only
    m = fr_machine(zh=True, dictionary=False); kopen(m)
    press(m, 'kb_lang')
    expect(said(m, 'kb_lang') == 'EN' and keys(m)[0] == 'A', 'no dictionary: the Chinese layer is not offered, FR')
    press(m, 'kb_lang')
    expect(said(m, 'kb_lang') == 'FR' and keys(m)[0] == 'Q' and m.word(PY.ENGINE_PTR) == 0, 'and EN again')

    # 4. The Chinese engine fails to open when tapped: it is dropped, the others keep cycling
    m = keyboard_machine(); m.fs[KBZH] = b'1\n'; m.fs[KBFR] = b'1\n'; m.present.add(PY.SYS_PATH); m.py_open_ok = False
    kopen(m)
    names_ = [c[0] for k in range(2) for c in press(m, 'kb_lang')]
    expect(names_.count('im_open_decoder') == 1 and said(m, 'kb_lang') == 'FR' and keys(m)[0] == 'Q' and shown(m, 'kb_lang') == (1, 1) and geo(m, 'kb_space')[0] == 122 and m.word(PY.ENGINE_PTR) == 0,
           'FR -> 中 fails: the engine closed, the cycle goes on to English, the key stays (it reads FR)')
    names_ = [c[0] for k in range(2) for c in press(m, 'kb_lang')]
    expect(said(m, 'kb_lang') == 'FR' and 'im_open_decoder' not in names_, 'and Chinese is not tried again')
    m = keyboard_machine(); m.fs[KBZH] = b'1\n'; m.fs[KBFR] = b'1\n'; m.present.add(PY.SYS_PATH); m.py_open_ok = False
    m.setword(PSYMS['kb_memo'], 1)
    kopen(m)
    expect(said(m, 'kb_lang') == 'FR' and keys(m)[0] == 'Q' and shown(m, 'kb_lang') == (1, 1) and m.word(PSYMS['kb_memo']) == 0, 'a remembered Chinese layer that will not open: English, the French key still there')

    # 5. The remembered layer; a setting turned off meanwhile
    m = fr_machine(); kopen(m); press(m, 'kb_lang'); reopen(m)
    expect(said(m, 'kb_lang') == 'EN' and keys(m)[0] == 'A' and not layout_ok(m, 'ABC', lang=True, fr=True), 'the next keyboard starts on the French layer the last one ended on')
    m.fs[KBFR] = b'0\n'; reopen(m)
    expect(shown(m, 'kb_lang') == (0, 0) and keys(m)[0] == 'Q' and geo(m, 'kb_space')[0] == 79 and m.word(PSYMS['kb_memo']) == 0, 'French turned off meanwhile: English, no key, memo not left on French')
    m.fs[KBFR] = b'1\n'; reopen(m)
    expect(said(m, 'kb_lang') == 'FR' and keys(m)[0] == 'Q', 'turned on again: English first')
    m = fr_machine(zh=True); kopen(m); press(m, 'kb_lang'); press(m, 'kb_lang'); reopen(m)
    expect(said(m, 'kb_lang') == 'EN' and keys(m)[0] == 'q' and m.engine()[1] == 1, 'the Chinese layer is remembered too')
    m.fs[KBZH] = b'0\n'; reopen(m)
    expect(said(m, 'kb_lang') == 'FR' and keys(m)[0] == 'Q' and m.word(PSYMS['kb_memo']) == 0, 'Chinese off meanwhile (French on): English, the key now goes to FR')
    m = fr_machine(zh=True); kopen(m); press(m, 'kb_lang')
    m.call(*m.bound[(m.window, DESTROY)][:1], a0=m.bound[(m.window, DESTROY)][1], count=4000000)
    expect(m.call(PSYMS['kb_fr_setting']) == 1 and m.call(PSYMS['kb_fr_toggle'], count=4000000) == 0 and m.fs[KBFR] == b'0\n' and m.word(PSYMS['kb_memo']) == 0, 'kb_fr_toggle turns it off (saved) and forgets a French layer')
    expect(m.call(PSYMS['kb_fr_toggle'], count=4000000) == 1 and m.fs[KBFR] == b'1\n', 'and on again')
    m.setword(PSYMS['kb_memo'], 1)
    m.call(PSYMS['kb_fr_toggle'], count=4000000); m.call(PSYMS['kb_fr_toggle'], count=4000000)
    expect(m.word(PSYMS['kb_memo']) == 1, 'turning French off or on leaves a Chinese memo alone')
    m.call(PSYMS['kb_zh_toggle'], count=4000000)
    expect(m.word(PSYMS['kb_memo']) == 0, 'turning Chinese off forgets it')
    m = keyboard_machine()
    for data in (b'0\n', b'', b'x', b'\n1', b'1x', b'11'):
        m.fs[KBFR] = data; m.call(PSYMS['kb_fr_setting'])
        expect(m.call(PSYMS['kb_fr_setting']) == 0, f'the file {data!r}: off')

    # 6. A password field is English only, whatever is on or remembered
    m = fr_machine(zh=True); m.setword(PSYMS['kb_memo'], 2)
    expect(attach(m, DEFS['KB_PASSWORD']) == 0 and shown(m, 'kb_lang') == (0, 0) and keys(m)[0] == 'q' and geo(m, 'kb_space')[2] == 163 and not [c for c in m.calls if c[0] in ('im_open_decoder', 'access')],
           'KB_PASSWORD with French remembered: English, no language key')
    refocus(m, 'N', 156, 0, '')
    expect(said(m, 'kb_lang') == '中' and keys(m)[0] == 'A' and shown(m, 'kb_lang') == (1, 1), 'the plain field after it: the remembered French layer is back, the key reads 中')

    # 7. The touch model with French (a gap goes to the nearest AZERTY key)
    m = fr_machine(); kopen(m); press(m, 'kb_lang')   # (an empty field: delete acts on touch down, so the capitals page stays)
    by_handle = {h: n for n, h in m.widgets.items()}
    lay = PK.layout('ABC', lang=True, fr=True)
    fn_widget = {'shift': 'kb_shifton', 'sym': 'kb_sym', 'del': 'kb_del', 'mode': 'kb_mode', 'lang': 'kb_lang', 'space': 'kb_space', 'go': 'kb_go'}
    bad, t = [], 40000
    for y in sorted(set(range(0, 180, 9)) | {131, 137, 138, 175}):
        for x in sorted(set(range(0, 320, 11)) | {2, 41, 42, 43, 78, 79, 80, 118, 119, 120, 121, 122, 123, 240, 241, 242, 243, 244, 245}):
            t += 1
            ptr(m, 'kb_pad', 'down', x, WIN_Y + PAD_Y + y, t)
            pressed = [by_handle.get(c[1]) for c in m.calls if c[0] == 'widget_set_state' and c[2] == 'pressed']
            kind, ident, d2 = PK.nearest_key(lay, x, y)
            name = f'kb_k{ident}' if kind == 'char' else fn_widget[ident]
            if pressed != ([name] if d2 > 0 else []): bad.append((x, y, pressed, name))
            ptr(m, 'kb_pad', 'abort', x, WIN_Y + PAD_Y + y, t)
    expect(not bad, f'with the language key every point of the French page presses the key the model picks ({bad[:2]})')


def key_at(m, c): return keys(m).index(c)


def acc_timers(m): return [c for c in m.calls if c[0] == 'timer_add' and c[2] == DEFS['KB_ACC_MS']]


def acc_up(m): return shown(m, 'kb_acc') == (1, 0)


def acc_labels(m, n): return [said(m, f'kb_a{i}') for i in range(n)]


def hold(m, c, via='key', gap=False, t=1000):
    """Put a finger down on the char key c (its own touch, or the pad's for a touch in the gap just right of it) and let the 500 ms timer fire; returns (screen x, y of the finger, the widget that
    got the down)."""
    i = key_at(m, c); name = f'kb_k{i}'
    x, y = centre(m, name)
    if gap:
        kx, ky, kw, _ = geo(m, name); x = kx + kw + 1; name = 'kb_pad'
    ptr(m, name, 'down', x, y, t)
    fns = [c_[1] for c_ in acc_timers(m)]
    assert fns, f'no accent timer for {c}'
    m.acc_fn = fns[-1]
    m.call(fns[-1], a0=0, count=4000000)
    return x, y, name


def slot_x(rect, slot): return rect[0] + PK.ACC_PAD + slot * PK.ACC_CELL + PK.ACC_CELL // 2


def accent_tests(ctx):
    """Long-press accents (English and French letter pages): the strip over the key after 500 ms, sliding picks a variant, lifting types it; the model in tools/pod_keyboard.py."""
    expect = ctx.expect
    expect(PK.ACC_MS == DEFS['KB_ACC_MS'] and (PK.ACC_CELL, PK.ACC_H, PK.ACC_PAD, PK.ACC_GAP, PK.ACC_MAX) == tuple(DEFS[k] for k in ('KB_ACC_CELL', 'KB_ACC_H', 'KB_ACC_PAD', 'KB_ACC_GAP', 'KB_ACC_MAX')), 'the constants agree')
    expect(PK.ACCENTS == {'e': 'éèêë', 'a': 'àâæáäãå', 'c': 'ç', 'u': 'ùûüú', 'i': 'îïìí', 'o': 'ôœöòóõø', 'y': 'ÿ', 'n': 'ñ'} and PK.accents('E') == 'ÉÈÊË' and PK.accents('w') == '' and PK.accents('Y') == 'Ÿ' and PK.accents('O') == 'ÔŒÖÒÓÕØ',
           'the table, French first, capitals for a capital')
    src = open(os.path.join(ROOT, 'patch', 'keyboard.c'), encoding='utf-8').read()
    expect(all(f'{{\'{c}\', "{v}", "{v.upper()}"}}' in src.replace('\n', ' ') or f'"{v}", "{v.upper()}"' in src for c, v in PK.ACCENTS.items()), 'patch/keyboard.c has the same table')
    r = PK.acc_rect(290, 29, 6, 4)
    expect(r[0] + r[2] <= 319 and r[0] >= 1 and PK.acc_rect(2, 29, 6, 7)[0] == 1 and PK.acc_rect(2, 29, 6, 7)[4] is False and PK.acc_rect(290, 29, 6, 7)[4] is True and PK.acc_rect(290, 29, 6, 7)[0] + 204 == 319,
           'the model clamps a strip inside the screen (left key grows right, right key grows left)')
    r = PK.acc_rect(66, 29, 6, 4)
    expect([PK.acc_pick(r, 4, x) for x in (0, 66, 93, 94, 121, 122, 149, 150, 400)] == [0, 0, 0, 1, 1, 2, 2, 3, 3] and PK.acc_pick(PK.acc_rect(258, 29, 6, 4), 4, 5000) == 0 and PK.acc_pick(PK.acc_rect(258, 29, 6, 4), 4, -50) == 3, 'the finger picks the slot under it, reversed on a right-side strip')

    # 1. Hold e, lift without moving: the first variant
    m = opened(initial='x'); ex = PK.layout('abc')['keys'][key_at(m, 'e')]
    x, y = centre(m, f'kb_k{key_at(m, "e")}')
    ptr(m, f'kb_k{key_at(m, "e")}', 'down', x, y)
    expect(acc_timers(m) and not acc_up(m) and shown(m, 'kb_pop')[0] == 1, 'a key with accents arms the 500 ms timer and shows the balloon at once')
    fn = acc_timers(m)[0][1]; m.call(fn, a0=0, count=4000000)
    rect = PK.acc_rect(ex[1], ex[3], ex[2], 4)
    expect(acc_up(m) and shown(m, 'kb_pop')[0] == 0 and shown(m, 'kb_stem')[0] == 0 and geo(m, 'kb_acc') == rect[:4] and acc_labels(m, 4) == list('éèêë') and [shown(m, f'kb_a{i}')[0] for i in range(7)] == [1] * 4 + [0] * 3
           and geo(m, 'kb_acc_h')[0] == PK.ACC_PAD and shown(m, 'kb_acc_h') == (1, 0) and all(shown(m, f'kb_a{i}')[1] == 0 for i in range(7)), f'the strip replaces the balloon: four variants, the first highlighted, all insensitive {geo(m, "kb_acc")} {rect}')
    lift(m, f'kb_k{key_at(m, "e")}', x, y, 1700)
    expect(field(m) == 'xé' and not acc_up(m) and shown(m, 'kb_pop')[0] == 0, f'lifting without a move types é, and the click after it types nothing more ({field(m)})')
    expect(field(m) == 'xé' and not acc_up(m) and shown(m, 'kb_acc') == (0, 0), 'the strip is gone')
    ptr(m, 'kb_k0', 'down', *centre(m, 'kb_k0'), 3000); lift(m, 'kb_k0', *centre(m, 'kb_k0'), 3050)
    expect(field(m) == 'xéq', f'the next tap is a normal tap ({field(m)})')

    # 2. Slide to the second variant, then lift: è
    m = opened(initial='x'); name = f'kb_k{key_at(m, "e")}'
    x, y, _ = hold(m, 'e')
    ptr(m, name, 'move', slot_x(rect, 1), y, 1600)
    expect(geo(m, 'kb_acc_h')[0] == PK.ACC_PAD + PK.ACC_CELL, 'sliding right moves the highlight to the second variant')
    ptr(m, name, 'move', slot_x(rect, 3), y, 1620); ptr(m, name, 'move', slot_x(rect, 1), y, 1640)
    lift(m, name, slot_x(rect, 1), y, 1700)
    expect(field(m) == 'xè' and not acc_up(m), f'lifting types the highlighted variant, è ({field(m)})')
    m = opened(initial='x'); x, y, _ = hold(m, 'e')
    ptr(m, name, 'move', 0, y, 1600); ptr(m, name, 'move', 5000, y, 1610)
    expect(geo(m, 'kb_acc_h')[0] == PK.ACC_PAD + 3 * PK.ACC_CELL, 'sliding past the end holds the last variant')
    ptr(m, name, 'up', 5000, y, 1700)
    expect(field(m) == 'xë', f'a lift far off the strip types the nearest end ({field(m)})')

    # 3. A quick tap is unchanged; so is a tap on a key without accents
    m = opened(initial='x'); press(m, f'kb_k{key_at(m, "e")}')
    expect(field(m) == 'xe' and not acc_up(m) and calls_of(m, 'timer_remove'), 'a quick tap types e and takes the timer away')
    m = opened(initial='x'); ptr(m, f'kb_k{key_at(m, "w")}', 'down', *centre(m, f'kb_k{key_at(m, "w")}'))
    expect(not acc_timers(m), 'a key without accents arms no timer')
    m = opened(initial='x'); name = f'kb_k{key_at(m, "e")}'; x, y, _ = hold(m, 'e')
    fn = m.acc_fn
    lift(m, name, x, y, 1700); m.calls = []
    expect(m.call(fn, a0=0, count=4000000) == 0 and not acc_up(m) and field(m) == 'xé', 'a tick that arrives after the lift does nothing')
    m = opened(initial='x'); ptr(m, name, 'down', x, y, 100); fn = acc_timers(m)[0][1]; lift(m, name, x, y, 180); m.call(fn, a0=0, count=4000000)
    expect(field(m) == 'xe' and not acc_up(m), 'a quick tap whose timer tick arrives late shows no strip')

    # 4. Capitals: É on the upper page, then shift is off
    m = opened(); name = f'kb_k{key_at(m, "E")}'
    expect(keys(m)[0] == 'Q', 'an empty field starts on capitals')
    x, y, _ = hold(m, 'E')
    expect(acc_up(m) and acc_labels(m, 4) == list('ÉÈÊË'), 'capital variants on the upper page')
    lift(m, name, x, y, 1700)
    expect(field(m) == 'É' and keys(m)[0] == 'q' and shown(m, 'kb_shift') == (1, 1), 'the accented capital counts as the letter: shift is off after it')
    m = opened(); x, y, _ = hold(m, 'O')
    expect(acc_labels(m, 7) == list('ÔŒÖÒÓÕØ')[::-1], 'o: seven capitals (a right-side strip lists them reversed, the first nearest the key)')
    m = opened(initial='a'); press(m, 'kb_shift'); x, y, _ = hold(m, 'A')
    expect(acc_labels(m, 7) == list('ÀÂÆÁÄÃÅ'), 'a: shift pressed by hand, capitals')

    # 5. Abort and background type nothing
    m = opened(initial='x'); name = f'kb_k{key_at(m, "e")}'; x, y, _ = hold(m, 'e')
    ptr(m, name, 'move', slot_x(rect, 2), y, 1600); ptr(m, name, 'abort', x, y, 1700)
    expect(field(m) == 'x' and not acc_up(m) and shown(m, 'kb_pop')[0] == 0, 'abort types nothing and the strip goes')
    m = opened(initial='x'); name = f'kb_k{key_at(m, "e")}'; x, y, _ = hold(m, 'e')
    m.call(m.bound[(m.window, TO_BG)][0], a0=m.bound[(m.window, TO_BG)][1], count=4000000)
    expect(not acc_up(m), 'the page going to the background lets the strip go')
    ptr(m, name, 'up', x, y, 1700)
    expect(field(m) == 'x', 'and the lift after it types nothing')
    m = opened(initial='x'); x, y, _ = hold(m, 'e'); fn_d = m.bound[(m.window, DESTROY)]
    m.call(fn_d[0], a0=fn_d[1], count=4000000)
    expect(m.call(m.acc_fn, a0=0, count=4000000) == 0, 'destroy with the strip up is safe (a late tick does nothing)')

    # 6. Byte limit
    m = opened(initial='x' * 62); name = f'kb_k{key_at(m, "e")}'; x, y, _ = hold(m, 'e')
    lift(m, name, x, y, 1700)
    expect(raw_text(m) == 'x' * 62, 'a variant that does not fit (2 bytes in 1) is not typed')
    m = opened(initial='x' * 61); x, y, _ = hold(m, 'e'); ptr(m, name, 'up', x, y, 1700)
    expect(raw_text(m) == 'x' * 61 + 'é', 'one that does fit is typed')
    press(m, 'kb_del')
    expect(raw_text(m) == 'x' * 61, 'delete removes the whole accented character')

    # 7. Gap rule: a touch the pad resolves to the key gets the strip too; moves and the lift can come on the pad
    m = opened(initial='x'); x, y, nm = hold(m, 'e', gap=True)
    expect(nm == 'kb_pad' and acc_up(m) and acc_labels(m, 4) == list('éèêë'), 'a touch in the gap right of e shows the strip')
    ptr(m, 'kb_pad', 'move', slot_x(rect, 2), y, 1600); ptr(m, 'kb_pad', 'up', slot_x(rect, 2), y, 1700)
    expect(field(m) == 'xê' and not acc_up(m) and ('widget_set_state', m.widgets[f'kb_k{key_at(m, "e")}'], 'normal') in m.calls, f'moves and the lift on the pad pick ê ({field(m)})')
    m = opened(initial='x'); x, y, nm = hold(m, 'e', gap=True)
    ptr(m, 'kb_pad', 'abort', x, y, 1700)
    expect(field(m) == 'x' and not acc_up(m), 'an aborted gap touch types nothing')
    m = opened(initial='x'); name = f'kb_k{key_at(m, "e")}'; x, y, _ = hold(m, 'e')
    ptr(m, 'kb_pad', 'move', slot_x(rect, 1), y, 1600); ptr(m, 'kb_pad', 'up', slot_x(rect, 1), y, 1700); ptr(m, name, 'up', slot_x(rect, 1), y, 1700)
    expect(field(m) == 'xè', f'a key touch whose moves and lift the pad hears too types once ({field(m)})')

    # 7b. Real event order (click, then up) and the capture of a gap-started gesture
    m = opened(initial='x'); name = f'kb_k{key_at(m, "e")}'; x, y, _ = hold(m, 'e')
    run_evt(m, name, O['EVT_CLICK'])
    expect(field(m) == 'x' and acc_up(m), f'with the strip up the click types nothing, the strip stays for the lift ({field(m)})')
    ptr(m, name, 'up', x, y, 1700)
    expect(field(m) == 'xé' and not acc_up(m), f'the lift types the variant once: é, not eé ({field(m)})')
    m = opened(initial='x'); name = f'kb_k{key_at(m, "e")}'; x, y = centre(m, name)
    ptr(m, name, 'down', x, y, 100); lift(m, name, x, y, 180)
    expect(field(m) == 'xe', f'a quick tap in the real order types e once ({field(m)})')
    m = opened(initial='x'); name = f'kb_k{key_at(m, "e")}'; x, y, _ = hold(m, 'e')
    ptr(m, name, 'up', x, y, 1700); run_evt(m, name, O['EVT_CLICK'])
    expect(field(m) == 'xé', f'an up before the click types é once too ({field(m)})')
    m = opened(initial='x'); kx, ky, kw, _ = geo(m, f'kb_k{key_at(m, "e")}'); x, y = centre(m, f'kb_k{key_at(m, "e")}')
    ptr(m, 'kb_pad', 'down', kx + kw + 1, y, 1000)
    expect(('widget_grab', m.window, m.widgets['kb_pad']) in m.calls, 'a gap touch on a key with accents grabs the touch at the pad (moves and the lift come wherever the finger goes)')
    m.call(acc_timers(m)[-1][1], a0=0, count=4000000)
    ptr(m, 'kb_pad', 'move', slot_x(rect, 2), -40, 1600); ptr(m, 'kb_pad', 'up', slot_x(rect, 2), -40, 1700)
    expect(field(m) == 'xê' and not acc_up(m) and ('widget_ungrab', m.window, m.widgets['kb_pad']) in m.calls, f'a lift above the pad types the variant, hides the strip and lets go ({field(m)})')
    m = opened(initial='x'); x, y, nm = hold(m, 'e', gap=True); ptr(m, 'kb_pad', 'move', slot_x(rect, 2), -40, 1600); ptr(m, 'kb_pad', 'abort', 0, -40, 1700)
    expect(field(m) == 'x' and not acc_up(m) and ('widget_ungrab', m.window, m.widgets['kb_pad']) in m.calls, 'an abort outside the pad types nothing, hides the strip and lets go')
    m = opened(initial='x'); x, y, nm = hold(m, 'e', gap=True); m.calls = []
    m.call(m.bound[(m.window, TO_BG)][0], a0=m.bound[(m.window, TO_BG)][1], count=4000000)
    expect(not acc_up(m) and ('widget_ungrab', m.window, m.widgets['kb_pad']) in m.calls, 'the page going to the background lets go of the grab')
    m = opened(initial='x'); x, y, nm = hold(m, 'e', gap=True); m.calls = []; fn_d = m.bound[(m.window, DESTROY)]
    m.call(fn_d[0], a0=fn_d[1], count=4000000)
    expect(('widget_ungrab', m.window, m.widgets['kb_pad']) in m.calls, 'destroy lets go of the grab')
    m = opened(initial='x'); kx, ky, kw, _ = geo(m, f'kb_k{key_at(m, "w")}'); wx, wy = centre(m, f'kb_k{key_at(m, "w")}')
    ptr(m, 'kb_pad', 'down', kx + kw + 1, wy, 1000)
    expect(not [c for c in m.calls if c[0] == 'widget_grab'], 'a gap touch on a key without accents takes no grab')

    # 8. Not on the symbol pages, not on the Chinese layer; a password field takes them
    m = opened(initial='x'); press(m, 'kb_mode'); c = [k for k in keys(m)]
    ptr(m, 'kb_k0', 'down', *centre(m, 'kb_k0'))
    expect(not acc_timers(m), 'no accents on the 123 page')
    m = zh_opened(initial='x'); press(m, 'kb_lang'); ptr(m, f'kb_k{key_at(m, "e")}', 'down', *centre(m, f'kb_k{key_at(m, "e")}'))
    expect(said(m, 'kb_lang') == 'EN' and not acc_timers(m) and not acc_up(m), 'no accents on the Chinese layer')
    m = keyboard_machine(); kopen(m, flags=8)
    x, y, _ = hold(m, 'e'); ptr(m, f'kb_k{key_at(m, "e")}', 'up', x, y, 1700)
    expect(raw_text(m) == 'é', 'a password field takes the strip')

    # 9. Every accent key on every letter page of English and French: the strip is inside the screen, matches the model, and a finger at each slot picks that variant
    for fr in (False, True):
        for page_shift in (False, True):
            m = fr_machine(fr=True) if fr else keyboard_machine()
            kopen(m, initial='x')
            if fr: press(m, 'kb_lang')
            if page_shift: press(m, 'kb_shift')
            lay = PK.layout('ABC' if page_shift else 'abc', lang=fr, fr=fr)['keys']
            for c, kx, ky, kw in lay:
                v = PK.accents(c)
                if not v: continue
                name = f'kb_k{key_at(m, c)}'
                x, y, _ = hold(m, c)
                rect = PK.acc_rect(kx, kw, ky, len(v))
                expect(acc_up(m), f'{c}: strip up')
                expect(geo(m, 'kb_acc') == rect[:4] and rect[0] >= 1 and rect[0] + rect[2] <= 319, f'{"FR" if fr else "EN"} {c}: the strip {geo(m, "kb_acc")} is the model\'s {rect[:4]} and inside the screen')
                labs = acc_labels(m, len(v))
                expect(labs == (list(v)[::-1] if rect[4] else list(v)), f'{c}: slot order {labs}')
                for k in range(len(v)):
                    fx = slot_x(rect, k) if not rect[4] else slot_x(rect, len(v) - 1 - k)
                    ptr(m, name, 'move', fx, y, 2000 + k)
                    expect(geo(m, 'kb_acc_h')[0] == PK.ACC_PAD + PK.ACC_CELL * ((len(v) - 1 - k) if rect[4] else k), f'{c}: a finger over variant {k}')
                    expect(PK.acc_pick(rect, len(v), fx) == k, f'{c}: model pick {k}')
                ptr(m, name, 'abort', x, y, 3000)


SECTIONS = [base_tests, name_tests, password_tests, refocus_tests, gap_tests, asset_tests, setting_tests, zh_tests, zh_search_tests, zh_limit_tests, strip_tests, hit_tests, lang_gap_tests, french_tests, accent_tests]   # tools/check.py runs each as its own task
