"""The Podcasts Show page's select mode (patch/podcasts.c, docs/modules/podcasts.md "Downloads"; the Downloads page and its select mode are test/pod/pcdlpage.py) in the Playlists page's manner (the navbar's x,
"N Selected", Select All, marks, a Delete bar, a confirm; only episodes on the card are marked; the file and its .part unlinked, the `.episodes` line kept, the playing episode kept, a show with no file
staying on the Shows level). The compiled payload runs under Unicorn; the card is a dict of paths."""
import importlib.util, os, struct, sys
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)

HERE = os.path.dirname(os.path.abspath(__file__))


def sibling(name):
    mod = sys.modules.get(f'podtest_{name}')
    if mod is None:
        spec = importlib.util.spec_from_file_location(f'podtest_{name}', os.path.join(HERE, name + '.py'))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[f'podtest_{name}'] = mod
        spec.loader.exec_module(mod)
    return mod


DL = sibling('pcdl')
PF, PCN, PCP = DL.PF, DL.PCN, DL.PCP
RP, ROW, NOW, PN = DL.RP, DL.ROW, DL.NOW, DL.PN
pn_at, poke_slot, poke_fail, key_of = DL.pn_at, DL.poke_slot, DL.poke_fail, DL.key_of
SG_MARK, SG_BAR_H = O['SG_MARK'], O['SG_BAR_H']
SUB = 'Sub One'


def card(m):
    """Sub One: a.mp3 and b.mp3 on the card (local), c.mp3 not, d.mp3 with a .part, e.mp3 and f.mp3 not; every line has its url."""
    PF.card(m)
    lines_ = ''.join(f'g=s{i}\tp={NOW - 5000 - 100 * i}\td=600\tl=1000\tf={f}.mp3\tt=Ep {f.upper()}\tu=https://e.example/{f}.mp3\n' for i, f in enumerate('abcdef'))
    m.put(f'{RP}/{SUB}/.episodes', (PCP.EPS_HEAD + lines_).encode())
    for f in 'ab': m.put(f'{RP}/{SUB}/{f}.mp3', b'audio-' + f.encode())
    m.put(f'{RP}/{SUB}/d.mp3.part', b'half')


def page():
    m = PCP.opened(lambda mm: (card(mm), mm.images.update({'unselect': (26, 26, struct.pack('<I', 0xff111111) * 676), 'selected': (26, 26, struct.pack('<I', 0xff2222ee) * 676)})), PCN.NM)
    m.curl_site = DL.server(DL.DATA)
    return m


def flags(m, n): return PF.flags(m, n)
def toasts(m): return [c[1] for c in m.calls if c[0] == 'toast']
def confirms(m): return [c[1] for c in m.calls if c[0] == 'confirm']
def unlinks(m): return [c[1].replace(RP + '/', '') for c in m.calls if c[0] == 'unlink']
def tick(m): return DL.tick(m)
def to_downloads(m):
    tick(m)   # (the page reads the queue again from its timer: the row appears)
    PCP.tap_downloads(m)
def title(m): return PCP.title_text(m)


def lines(m, top=0):
    """[(row, title, grey line)] of a frame: the titles and the grey lines by row (top: where the first row starts)."""
    _, texts, styles, _ = PCP.paint(m)
    t = {(y - top) // ROW: v for (v, (x, y, w, h)), s in zip(texts, styles) if s == 'label_row_title' and y >= top and (y - top) % ROW == O['LIST_TITLE_Y']}
    g = {(y - top) // ROW: v for (v, (x, y, w, h)), s in zip(texts, styles) if s == 'label_row_sub' and y >= top and (y - top) % ROW == O['LIST_SUB_Y']}
    return [(r, t.get(r), g.get(r)) for r in sorted(t)]


def marks(m, off=0):
    bl, *_ = PCP.paint(m, off)
    return sorted((b[2][0], b[2][1], b[0]) for b in bl if tuple(b[2][2:]) == (SG_MARK, SG_MARK))


def running(m, f='e.mp3', got=420000, total=1000000):
    """The status record as it is while f downloads (slot 0, seq 1)."""
    poke_slot(m, 0, SUB, f, 2, seq=1)
    m.setword(pn_at(DL.DKEY), key_of(SUB, f)); m.setword(pn_at(DL.DGOT), got); m.setword(pn_at(DL.DTOTAL), total)
    m.setword(pn_at(DL.KIND), 2); m.setword(pn_at(0), 1); m.setword(pn_at(DL.DSEQ), 10)


def start_select(m):
    """Select mode of the Show page: the show's "..." and its sheet's Select Episodes."""
    PCP.click(m, 'btn_more')
    PCP.click(m, 'pg_sh_select')


def all_marks(m):
    """{cell: image} of the select marks of the open show's cells, from frames scrolled 120 px apart (a mark is drawn only wholly in view)."""
    h = PCP.hdr(m)
    n = (m.props.get((m.sv, 'virtual_h')) - h - 20 - SG_BAR_H) // PCP.CELL
    out = {}
    for k in range(n * PCP.CELL // 120 + 2):
        for x, y, b in marks(m, h + 120 * k):
            i = (y + h + 120 * k - h) // PCP.CELL
            if 0 <= i < n: out.setdefault(i, (x, b))
    return out


def select_tests(ctx):
    expect = ctx.expect
    m = page()
    expect(flags(m, 'btn_more') == (0, 0), 'the Shows level: no "..." (nothing to import)')
    PCP.tap_show(m, 'Alpha Show')   # (two files)
    expect(title(m) == 'Alpha Show' and flags(m, 'btn_more') == (1, 1) and m.props[(m.widgets['btn_backtoplayer'], 'style:normal:icon')] == 'ah_nav_play',
           'a show\'s page: the "..." (the capsule\'s left cap) and Now Playing as its right cap; the Select button is not there (Select Episodes is in the sheet)')
    m = page()
    m.put(f'{RP}/Sub Two/.episodes', (PCP.EPS_HEAD + 'g=t1\tp=5\tf=t.mp3\tt=T\tu=https://e.example/t.mp3\n').encode())
    PCP.tap_show(m, 'Sub Two')   # one episode, not on the card
    PCP.click(m, 'btn_more')
    expect(title(m) == 'Sub Two' and flags(m, 'pg_sh_select') == (0, 0) and flags(m, 'pg_sh_speed')[0] == 1,
           'a show with only remote episodes: the sheet has no Select Episodes row (nothing can be marked)')
    # Sub One: a, b local, c, e, f remote, d paused
    m = page()
    PCP.tap_show(m, SUB)
    PCP.click(m, 'btn_more')
    expect(title(m) == SUB and flags(m, 'pg_sh_select') == (1, 1), 'Sub One: the sheet has Select Episodes')
    PCP.click(m, 'pg_sh_scrim')
    h0 = m.props.get((m.sv, 'virtual_h'))
    m.calls = []
    start_select(m)
    t, back = m.widgets['label_title'], m.widgets['btn_return']
    expect(('widget_set_text_utf8', t, '0 Selected') in m.calls and ('widget_resize', t, O['SG_SELALL_X'] - O['NAV_TITLE_X'], 22) in m.calls and flags(m, 'pg_sh_card') == (0, 0), 'Select Episodes: the sheet closes, the title reads 0 Selected and runs to Select All')
    expect(flags(m, 'btn_selall') == (1, 1) and flags(m, 'pg_bar') == (1, 1) and flags(m, 'btn_more') == (0, 0) and flags(m, 'btn_backtoplayer') == (0, 0),
           'Select All and the bar show; the "..." and Now Playing go (hidden and insensitive)')
    expect(m.props.get((t, 'visible')) == 1, 'the title shows (in select mode it is "N Selected", not the collapsing show title)')
    expect(m.props.get((back, 'style:normal:icon')) == 'ah_nav_close' and m.props.get((back, 'style:pressed:icon')) == 'ah_nav_close_down', 'Back becomes the glass x')
    expect(m.props.get((m.sv, 'virtual_h')) == h0 + SG_BAR_H, 'the content is the bar\'s height longer')
    mk = all_marks(m)
    expect(sorted(mk) == [0, 1, 3] and len({b for _, b in mk.values()}) == 1, f'a mark on each cell that can be marked (the two files and the .part), all unselected ({sorted(mk)})')
    expect(all(x == O['PS_CELL_X'] + (O['SG_SEL_COL'] - 6 - SG_MARK) // 2 for x, _ in mk.values()), 'in the mark column that opens left of the texts')
    c = PCP.all_cells(m)
    expect([c[i]['title'] for i in range(4)] == [['Ep A'], ['Ep B'], ['Ep C'], ['Ep D']], f'the cells: {[c[i]["title"] for i in range(4)]}')
    _, texts, styles, _ = PCP.paint(m, PCP.hdr(m))
    xs = [r[0] for (v, r), s in zip(texts, styles) if s in ('label_ps_ctitle', 'label_ps_cdim')]
    expect(xs and all(x == O['PS_CELL_X'] + O['SG_SEL_COL'] for x in xs), f'the texts moved right by the mark column ({xs})')
    expect(not [b for b in PCP.paint(m, PCP.hdr(m))[0] if tuple(b[2][2:]) == (O['PA_DOTS_PX'], O['PA_DOTS_PX'])], 'and the "..." of the cells is gone')
    # taps: a remote cell marks nothing, a local one marks
    m.calls = []
    PCP.body(m, 2)   # Ep C: remote
    expect(not [c_ for c_ in m.calls if c_[0] == 'widget_set_text_utf8' and c_[1] == t] and DL.fn(m, 'pn_dl_count') == 0 and 'pthread_create' not in [c_[0] for c_ in m.calls],
           'a tap on a remote cell marks nothing and downloads nothing')
    m.calls = []
    PCP.body(m, 0)
    expect(('widget_set_text_utf8', t, '1 Selected') in m.calls and 'navigator_to_with_context' not in [c_[0] for c_ in m.calls], 'a tap on a file marks it (1 Selected) and plays nothing')
    expect(len({b for _, b in all_marks(m).values()}) == 2, 'the marked cell has the selected image')
    m.calls = []
    PCP.act(m, 0)   # the pill: in select mode the whole cell is its body
    expect(m.ring() is None and ('widget_set_text_utf8', t, '0 Selected') in m.calls, 'a tap on the pill unmarks (in select mode it does not play, and nothing is toggled played)')
    m.calls = []
    PCP.click(m, 'btn_selall')
    expect(('widget_set_text_utf8', t, '3 Selected') in m.calls, 'Select All marks the three that can be marked')
    m.calls = []
    PCP.click(m, 'btn_selall')
    expect(('widget_set_text_utf8', t, '0 Selected') in m.calls, 'Select All again: none')
    m.calls = []
    PCP.body(m, 0, move=40)
    expect(not [c_ for c_ in m.calls if c_[0] == 'widget_set_text_utf8' and c_[1] == t], 'a drag marks nothing')
    m.calls = []
    PCP.click(m, 'btn_return')
    expect(flags(m, 'pg_bar') == (0, 0) and flags(m, 'btn_selall') == (0, 0) and flags(m, 'btn_more') == (1, 1) and m.props.get((back, 'style:normal:icon')) == 'ah_nav_back' and title(m) == SUB
           and 'navigator_back' not in [c_[0] for c_ in m.calls] and m.props.get((m.sv, 'virtual_h')) == h0 and m.props.get((t, 'visible')) == 0,
           'Back (the x) leaves select mode first: the bar goes, the "..." is back, the title (hidden again at the top) and the content are as before')
    start_select(m); m.calls = []
    PCP.click(m, 'pg_del')
    expect(not confirms(m), 'Delete with nothing marked does nothing')
    PCP.body(m, 0); m.calls = []; m.confirm_yes = False
    PCP.click(m, 'pg_del')
    expect(confirms(m) == ['Delete the selected episodes?'] and not unlinks(m) and flags(m, 'pg_bar') == (1, 1), 'Delete asks; No: nothing is deleted and the mode stays')
    # Yes, with the playing episode among them
    m.confirm_yes = True
    h = PCP.pc_hash(f'{RP}/{SUB}/b.mp3')
    m.call(PSYMS['pc_mark'], a0=h, a1=1, count=2000000)
    expect(m.state(h)[0] == 2, 'b.mp3 is marked played before')
    m.track(f'{RP}/{SUB}/a.mp3')
    PCP.click(m, 'btn_selall'); m.calls = []
    PCP.click(m, 'pg_del')
    expect(confirms(m) == ['Delete the selected episodes?'], 'Delete asks first')
    expect(sorted(unlinks(m)) == sorted([f'{SUB}/b.mp3', f'{SUB}/b.mp3.part', f'{SUB}/d.mp3', f'{SUB}/d.mp3.part']), f'each marked file and its .part is unlinked, the playing a.mp3 is not touched ({unlinks(m)})')
    expect(toasts(m) == ['The playing episode was kept'], 'the playing episode is kept, with a toast')
    expect(f'{RP}/{SUB}/a.mp3' in m.fs and f'{RP}/{SUB}/b.mp3' not in m.fs and f'{RP}/{SUB}/d.mp3.part' not in m.fs, 'the card: a.mp3 stays; b.mp3 and the paused d.mp3.part are gone')
    eps = m.fs[f'{RP}/{SUB}/.episodes']
    expect(b'f=b.mp3' in eps and b'f=d.mp3' in eps, 'the .episodes lines are kept (the episodes are remote again)')
    expect(flags(m, 'pg_bar') == (0, 0) and title(m) == SUB and flags(m, 'btn_more') == (1, 1), 'the mode ended; the page is read again')
    expect(m.state(h)[0] == 0, 'the played mark of a deleted episode is forgotten')
    c = PCP.all_cells(m)
    expect([c[i]['title'] for i in range(2)] == [['Ep A'], ['Ep B']] and [c[i]['pill'] for i in range(2)][0].endswith('m') and c[1]['pill'] == '1 MB', f'the page now: Ep A on the card, Ep B a download cell again ({c[0]["pill"]}, {c[1]["pill"]})')
    # a show left with no file stays on the Shows level (it is a subscription with its metadata; every show is listed)
    m = page()
    PCP.tap_show(m, 'Alpha Show')
    start_select(m); PCP.click(m, 'btn_selall'); m.calls = []; m.confirm_yes = True
    PCP.click(m, 'pg_del')
    expect(sorted(unlinks(m)) == sorted(['Alpha Show/ep1.mp3', 'Alpha Show/ep1.mp3.part', 'Alpha Show/ep2.mp3', 'Alpha Show/ep2.mp3.part']) and title(m) == 'Alpha Show',
           f'Alpha Show: both files deleted; the page is empty ({unlinks(m)})')
    expect('No episodes yet. Choose Refresh Feed in the menu at the top right.' in PCP.hint(m), 'and says so under its header (a subscription: use Refresh Feed in the menu)')
    PCP.click(m, 'btn_return')
    expect(PCP.show_at(m, 'Alpha')[2] >= 0 and title(m) == 'Podcasts', 'Back: the Shows level still lists it (a subscription is a show without a file; every show is listed)')
    m = page()
    PCP.tap_show(m, SUB)
    start_select(m); PCP.click(m, 'btn_selall'); m.confirm_yes = True
    PCP.click(m, 'pg_del')
    PCP.click(m, 'btn_return')
    expect(PCP.show_at(m, SUB)[2] >= 0 and title(m) == 'Podcasts', 'the same for Sub One, whose files are all deleted')

    # a download finishing while rows are marked does not reload the list under the marks; and a dark tick does no visual work
    m = page(); PCP.tap_show(m, SUB); start_select(m); PCP.body(m, 0)
    m.setword(pn_at(12), 700); tick(m)
    expect(len(all_marks(m)) == 3 and len({b for _, b in all_marks(m).values()}) == 2, 'the generation moves while rows are marked: the cells and the marks stay as they are')
    m.screen(False); m.calls = []; m.setword(pn_at(12), 800)
    m.call(PSYMS['pg_tick'], a0=0, count=40000000)
    expect(not [c for c in m.calls if c[0] in ('widget_invalidate_force', 'widget_set_text_utf8', 'widget_set_visible')], 'screen off: a tick does no visual work in select mode')


def width_tests(ctx):
    expect = ctx.expect
    from awtk_text import Ttf, StbText
    font = Ttf(os.path.join(WORK, 'rootfs', 'release', 'assets', 'default', 'raw', 'fonts', 'default.ttf'))
    st = StbText(font, O['LIST_SUB_PX'] if 'LIST_SUB_PX' in O else 18)
    title = StbText(font, 22)
    room = O['SG_SELALL_X'] - O['NAV_TITLE_X']
    worst = []
    for loc in pod_i18n.LOCALES:
        t = pod_i18n.table_for(loc)
        tr = lambda key, t=t: pod_i18n.TEXT[key][t]
        worst.append((loc, round(title.layout(tr('%d Selected').replace('%d', '300'))[1]), round(st.layout(tr('No downloads'))[1]), round(st.layout(tr('The playing episode was kept'))[1]),
                      round(title.layout(tr('Downloads'))[1])))
    print('  widths in px per language (300 Selected in the', room, 'px title room, No downloads, the toast, the Downloads title):', worst)
    expect(all(w <= room for _, w, _, _, _ in worst), f'"300 Selected" fits the title room in every language ({[x for x in worst if x[1] > room]})')
    expect(all(w <= 280 for _, _, w, _, _ in worst), 'No downloads fits one line of the empty-state label')
    expect(all(w <= 300 for _, _, _, w, _ in worst), f'the toast fits 300 px in every language ({[x for x in worst if x[3] > 300]})')
    room_n = O['NAV_VIEW_X'] - O['NAV_TITLE_X']
    expect(all(w <= room_n for _, _, _, _, w in worst), f'the Downloads title fits the title room of {room_n} px ({[x for x in worst if x[4] > room_n]})')


SECTIONS = [select_tests, width_tests]


def run(ctx):
    for f in SECTIONS: f(ctx)
