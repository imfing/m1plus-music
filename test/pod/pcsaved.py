"""The Podcasts page's Saved level (patch/podcasts.c, docs/modules/podcasts.md "Saved"): the Library row, the level (the episodes whose myfav rows stock's star and our Save Episode row add, the
last saved first, the Downloads page's Downloaded rows; a tap opens the episode page; Back returns), the empty state, the stock Favourites query's two answers (music only; episodes with the
payload's scope flag, which is down again afterwards) and a saved episode whose file is gone. The compiled payload runs under Unicorn; the card is a dict of paths and myfav a list."""
import importlib.util, os, sys
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), 'tools'))


def sibling(name):
    mod = sys.modules.get(f'podtest_{name}')
    if mod is None:
        spec = importlib.util.spec_from_file_location(f'podtest_{name}', os.path.join(HERE, name + '.py'))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[f'podtest_{name}'] = mod
        spec.loader.exec_module(mod)
    return mod


PCS = sibling('pcshows')
PCP = PCS.PCP
RP, EP = PCS.RP, PCS.EP
TOP, ROW = O['PP_TITLE_H'], O['PC_ROW_H']
A1, A2, B1 = EP('Alpha Show', 'ep1.mp3'), EP('Alpha Show', 'ep2.mp3'), None


def fav(m, *paths):
    """myfav in the order they were saved."""
    m.fav_rows[:] = [(p.rsplit('/', 1)[1], p, p.rsplit('/', 1)[1]) for p in paths]


def machine(*paths):
    m = PCS.opened(lambda mm: fav(mm, *paths))
    return m


def titles(m):
    _, texts, styles, _ = PCP.paint(m, 0)
    return [PCS.fixed(v) for (v, r), s in sorted(zip(texts, styles), key=lambda t: t[0][1][1]) if s == 'label_row_title']


def scope(m): return m.u.mem_read(PSYMS['pc_saved_scope'], 1)[0]


def row_tests(ctx):
    expect = ctx.expect
    m = machine(A1, A2)
    expect(('fav_query', 1) in m.calls and scope(m) == 0, 'the Shows level counts the saved episodes with the Saved scope set around stock\'s Favourites query, and puts it down again')
    expect(PCS.lib(m)[-1] == ('Saved', '2 episodes'), f'the Saved row counts them ({PCS.lib(m)})')
    m = machine(A1)
    expect(PCS.lib(m)[-1] == ('Saved', '1 episode'), f'one episode ({PCS.lib(m)})')
    m = machine(A1, EP('Alpha Show', 'gone.mp3'), '/mnt/mmc/Music/song.flac')
    expect(PCS.lib(m)[-1] == ('Saved', '1 episode'), f'a saved episode whose file is gone, and music in myfav, are not counted ({PCS.lib(m)})')
    m = machine()
    expect(PCS.lib(m)[-1] == ('Saved', 'No saved episodes'), f'nothing saved ({PCS.lib(m)})')


def level_tests(ctx):
    expect = ctx.expect
    m = machine(A1, A2)
    PCS.tap_row(m, 'Saved')
    PCS.settle(m)
    expect(PCP.title_text(m) == 'Saved' and m.props.get((m.widgets['pg_big'], 'visible')) != 0 and scope(m) == 0, 'the Saved level: its large title, the scope flag down')
    got = titles(m)
    expect(len(got) == 2 and got[0] != got[1], f'two rows, Downloaded-style ({got})')
    expect(m.props.get((m.sv, 'virtual_h')) == TOP + 2 * ROW, 'rows from the large title on, no storage line and no section header')
    # the last saved first
    m = machine(A2, A1)
    PCS.tap_row(m, 'Saved'); PCS.settle(m)
    m2 = machine(A1, A2)
    PCS.tap_row(m2, 'Saved'); PCS.settle(m2)
    expect(titles(m2) == titles(m)[::-1], f'the order is the saving order, newest first ({titles(m)} vs {titles(m2)})')
    expect(m.props.get((m.widgets['btn_more'], 'visible'), 0) == 0, 'no "..." sheet on the Saved page (the Downloads page\'s Delete would remove files)')
    # a tap opens the episode page, Back returns to the list
    PCP.tap(m, 150, TOP + 10)
    expect('label_ps_pill' in PCP.paint(m, 0)[2] and 'label_row_title' not in PCP.paint(m, 0)[2], 'a tap on a row opens the episode page (its pill, no rows)')
    PCP.click(m, 'btn_return')
    PCS.settle(m)
    expect(PCP.title_text(m) == 'Saved' and titles(m) == titles(m2)[::-1], 'Back returns to the Saved page, the rows as they were')
    PCP.click(m, 'btn_return')
    expect(PCP.title_text(m) == 'Podcasts', 'Back from Saved returns to the Shows level')
    # an unsaved episode leaves the page when it is made again
    m = machine(A1, A2)
    PCS.tap_row(m, 'Saved'); PCS.settle(m)
    PCP.tap(m, 150, TOP + 10)
    m.fav_rows[:] = [r for r in m.fav_rows if r[1] != A2]
    PCP.click(m, 'btn_return'); PCS.settle(m)
    expect(len(titles(m)) == 1, f'unsaved while its page was open: the list, made again on Back, has one row ({titles(m)})')


def empty_tests(ctx):
    expect = ctx.expect
    m = machine()
    PCS.tap_row(m, 'Saved'); PCS.settle(m)
    expect(PCP.title_text(m) == 'Saved' and 'No saved episodes' in PCP.hint(m), 'nothing saved: the page says so')


SECTIONS = [row_tests, level_tests, empty_tests]


def run(ctx):
    for f in SECTIONS: f(ctx)
