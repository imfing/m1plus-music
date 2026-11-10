#!/usr/bin/env python3
"""The agreement table: Python asset-builder constants that copy a C #define (patch/offsets.inc) must hold its value.

  make test TEST=consts        (or: uv run python -I test/consts.py)

Each ROWS entry is (module, python name or expression, C define or integer expression over offsets.inc names, kind):
  kind 'int' (default) compares integers; 'rgb' compares colours, the Python side a '#RRGGBB' string or an (r, g, b) tuple,
  the C side a colour word 0xAABBGGRR (red in the low byte, as offsets.inc writes them).
The Python value is read from the module (importable tools/ module), the C value with tools/cdefs.py over offsets.inc.
A row that disagrees fails, naming both sides with file:line. XFAIL marks a known MISMATCH (kept, not fixed): it is printed
as MISMATCH and does not fail; once the two agree the XFAIL entry itself fails so it gets removed.
SKIPPED lists literals that copy nothing in C or whose meaning differs; each has its reason.
"""
import ast, importlib, os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import cdefs   # noqa: E402

HEADER = os.path.join(ROOT, 'patch', 'offsets.inc')
O = cdefs.defines(HEADER)

PA = ('PA_SIZE', 'PA_RING_N', 'PA_RING_PX', 'PA_RING_COLS', 'PA_G_Y', 'PA_G_PX', 'PA_DOTS_Y', 'PA_DOTS_PX', 'PA_BADGE_X',
      'PA_BADGE_PX', 'PA_PILL_Y', 'PA_PILLF_X', 'PA_PILLO_X', 'PA_PILLW_X', 'PA_PILLR_X', 'PA_PILL_PX', 'PA_PILLW_PX',
      'PA_FILL_A', 'PA_RING_A', 'PA_CHEV', 'PA_TILE_PX', 'PA_DL_X', 'PA_DL_Y', 'PA_DL_PX', 'PA_DL_N', 'PA_DL_COLS', 'PA_DL_ARROW', 'PA_DL_STOP')
MB = ('MB_TITLE_Y', 'MB_TITLE_H', 'MB_ART', 'MB_ART_X', 'MB_ART_Y', 'MB_ART_R', 'MB_TEXT_X', 'MB_TEXT_W', 'MB_ARTIST_Y',
      'MB_ARTIST_H', 'MB_PLAY_X', 'MB_NEXT_X', 'MB_BTN_W')
DP = ('DP_TITLE_Y', 'DP_SUB_Y', 'DP_UPD_Y', 'DP_BTN_Y', 'DP_DESC_Y')

ROWS = (
    # tools/mod_icons.py: the album page, Daily Mix page, Pod iPod page, navbar, mini bar, Podcasts atlas, row menu
    ('mod_icons', 'AH_DISC_PX', 'AH_DISC'),
    ('mod_icons', 'AH_PILL_PX[0]', 'AH_PLAY_W'),
    ('mod_icons', 'AH_PILL_PX[1]', 'AH_PILL_H'),
    ('mod_icons', 'AH_TINT[2]', 'AH_TINT_ROWS'),
    ('mod_icons', 'DP_BACK_PX', 'DP_BACK_DISC'),
    ('mod_icons', 'DP_PILL_PX[0]', 'DP_PLAY_W'),
    ('mod_icons', 'DP_PILL_PX[1]', 'DP_PILL_H'),
    ('mod_icons', 'DM_DISC_PX', 'DM_DISC'),
    ('mod_icons', 'IPOD_WHEEL_D', 'IP_WHEEL_D'),
    ('mod_icons', 'IPOD_HUB_R', 'IP_HUB_R'),
    ('mod_icons', 'IPOD_PC_PANE[0]', 'IP_PANE_W'),
    ('mod_icons', 'IPOD_PC_PANE[1]', 'IP_PANE_H'),
    ('mod_icons', 'IPOD_PC_GLYPH_Y', 'IP_PC_GLYPH_Y'),
    ('mod_icons', 'IPOD_MODE_SRC', '2 * IP_MODE_PX'),
    ('mod_icons', 'IP_PLAY_SRC', 'IP_PLAY_PX'),
    ('mod_icons', 'NAV_SLOT_W', 'NAV_VIEW_W'),
    ('mod_icons', 'AB_WAVE_PX', 'AB_WAVE'),
    ('mod_icons', 'AB_WAVE_RGB', 'AB_WAVE_COLOR', 'rgb'),
    ('mod_icons', 'GLASS[0]', 'MB_W'),
    ('mod_icons', 'GLASS[1]', 'MB_H'),
    ('mod_icons', 'GLASS[2]', 'MB_R'),
    ('mod_icons', 'RM_DOTS_PX', 'RM_DOTS_PX'),
    *[('mod_icons', n, n) for n in PA],
    # tools/mod_nowplaying.py: the lyrics and the cover tone
    ('mod_nowplaying', 'DOT', 'LY_DOT'),
    ('mod_nowplaying', 'LYR_FONT', 'LY_FONT'),
    ('mod_nowplaying', 'BG', 'NP_NEUTRAL', 'rgb'),
    ('mod_nowplaying', 'NP_V_MIN', 'NP_V_MIN'),
    ('mod_nowplaying', 'NP_V_MAX', 'NP_V_MAX'),
    ('mod_nowplaying', 'NP_SAT_NUM', 'NP_SAT_NUM'),
    ('mod_nowplaying', 'NP_SAT_DEN', 'NP_SAT_DEN'),
    # tools/pod_ui.py: navbar, list chevron, grid, mini bar titles and art
    ('pod_ui', 'NAV_VIEW_X', 'NAV_VIEW_X'),
    ('pod_ui', 'NAV_VIEW_W', 'NAV_VIEW_W'),
    ('pod_ui', 'NAV_CF_W', 'NAV_CF_W'),
    ('pod_ui', 'NAV_CF_X', 'NAV_CF_X'),
    ('pod_ui', 'CHEV_X', 'LIST_CHEV_X'),
    ('pod_ui', 'GRID_VIEW_H', 'GRID_VIEW_H'),
    *[('pod_ui', n, n) for n in MB],
    # tools/pod_dailymix.py: the detail page's vertical numbers
    *[('pod_dailymix', n, n) for n in DP],
    # tools/pod_search.py: the rows' hairline and press colours
    ('pod_search', 'HAIR_RGB', 'LIST_HAIR', 'rgb'),
    ('pod_search', 'PRESS_RGB', 'LIST_PRESS', 'rgb'),
    # tools/pod_recent.py
    ('pod_recent', 'MAX', 'RC_MAX'),
    # tools/tape_art.py: the Now Playing tape picture (framebuffer px)
    ('tape_art', 'W', 'TP_W'),
    ('tape_art', 'H', 'TP_H'),
    ('tape_art', 'HUB_R', 'TP_HUB_R'),
    ('tape_art', 'HOLE_R', 'TP_HOLE_R'),
    ('tape_art', 'PACK_MIN', 'TP_PACK_MIN'),
    ('tape_art', 'PACK_MAX', 'TP_PACK_MAX'),
    ('tape_art', 'HUB_PX', 'TP_HUB_PX'),
    ('tape_art', 'SPRITES', 'TP_SPRITES'),
    ('tape_art', 'MARK_PX', 'TP_MARK_PX'),
    ('tape_art', 'TOP_RECT[0]', 'TP_TOP_X'),
    ('tape_art', 'TOP_RECT[1]', 'TP_TOP_Y'),
    ('tape_art', 'TOP_RECT[2]', 'TP_TOP_X + TP_TOP_W'),
    ('tape_art', 'TOP_RECT[3]', 'TP_TOP_Y + TP_TOP_H'),
    ('tape_art', 'CLEAR[0]', 'TP_CLEAR_X0'),
    ('tape_art', 'CLEAR[1]', 'TP_CLEAR_Y0'),
    ('tape_art', 'CLEAR[2]', 'TP_CLEAR_X1'),
    ('tape_art', 'CLEAR[3]', 'TP_CLEAR_Y1'),
    ('tape_art', 'CLOSE_RECT[0]', 'TP_CLOSE_X0'),
    ('tape_art', 'CLOSE_RECT[1]', 'TP_CLOSE_Y0'),
    ('tape_art', 'CLOSE_RECT[2]', 'TP_CLOSE_X1'),
    ('tape_art', 'CLOSE_RECT[3]', 'TP_CLOSE_Y1'),
    ('tape_art', 'REEL_CX[0]', 'TP_REEL_X0'),
    ('tape_art', 'REEL_CX[1]', 'TP_REEL_X1'),
    ('tape_art', 'REEL_CY', 'TP_REEL_Y'),
    # tools/vinyl_art.py: the Vinyl Mode record (framebuffer px)
    ('vinyl_art', 'W', 'VN_W'),
    ('vinyl_art', 'H', 'VN_H'),
    ('vinyl_art', 'REC_C[0]', 'VN_REC_X'),
    ('vinyl_art', 'REC_C[1]', 'VN_REC_Y'),
    ('vinyl_art', 'REC_R', 'VN_REC_R'),
    ('vinyl_art', 'LAB_R', 'VN_LAB_R'),
    # tools/pod.py: the stock style colour return address and the default layout vtable / function
    ('pod', 'STYLE_COLOR_RET', 'STYLE_COLOR_GRADIENT_RET'),
    ('pod', 'DEFAULT_LAYOUT_VTABLE', 'DEFAULT_LAYOUT_VTABLE'),
    ('pod', 'DEFAULT_LAYOUT_FN', 'DEFAULT_LAYOUT_FN'),
)

# Known MISMATCHes (none at the time of writing): key (module, python, C) -> reason. Left unfixed on purpose.
XFAIL = {}

# Literals that are not in the table, with the reason. Not checked by the test.
SKIPPED = (
    ('mod_icons', 'AH_SHUF_GLYPH = 19, AH_PLAY_GLYPH = 16, DP_BACK_GLYPH = 20', 'no C define for the glyph sizes'),
    ('mod_icons', 'DM_PLAY_GLYPH = 22', 'no C define (tools/pod_dailymix.py has the same value; Python to Python)'),
    ('mod_icons', 'GLASS_H = 42, GLASS_GLYPH = 20', 'no C define; NAV_H (50) is the bar, not the glass'),
    ('mod_icons', 'MB_PLAY_INK, MB_PAUSE_H, MB_SKIP_H, MB_SKIP_W', 'no C define (the bar glyph shapes are the Python model\'s)'),
    ('mod_icons', 'NAV_PX = 24, SHOT_BAR_PX, SYNC_BAR_PX, SYNC_DM_PX, PL_MENU_PX, SWATCH_PX', 'no C define'),
    ('mod_icons', 'AH_TINT[0], AH_TINT[1], AH_TINT[3]', 'alpha rows and window height: no C define'),
    ('mod_icons', 'PA_TRACK_A, PA_TILE_R, PA_TILE_GLYPH, PA_DL_TRACK, PA_DL_STROKE, PA_DL_STOP_PX', 'no C define (the stop square\'s size is in the atlas cell)'),
    ('mod_icons', 'CARD_PIECE (ROW_W, ROW_H, CARD_X, CARD_W, CARD_R)', 'no C define (tools/pod_settings.py geometry)'),
    ('mod_nowplaying', 'TITLE_PX, META_PX, TIMES_PX', 'font sizes, no C define'),
    ('mod_ipodrows', 'TITLE_PX, ARTIST_PX, META_PX = 22, 18, 15', 'font sizes; the offsets.inc AH_TITLE_H (22) is a height'),
    ('pod_ui', 'CHEV_TEXT_END = 278', 'no C define'),
    ('pod_ui', 'LIST_TITLE_PX, LIST_SUB_PX, MB_TITLE_PX, MB_ARTIST_PX', 'font sizes, no C define'),
    ('tape_art', 'SCREW_AT, PLAY_AT, REPEAT_AT', 'centres of the mark or screw; TP_SCREW_X/Y, TP_PLAY_X/Y, TP_REPEAT_X/Y are top-left corners'),
)


def py_line(path, expr):
    """The line of the module-level assignment that binds the expression's name (0 if none)."""
    name = re.match(r'\w+', expr).group()
    with open(path, encoding='utf-8') as f:
        tree = ast.parse(f.read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(n, ast.Name) and n.id == name
                                                for t in node.targets for n in ast.walk(t)):
            return node.lineno
    return 0


def c_line(text, expr):
    """The line of the first define in the expression (0 if none)."""
    for name in re.findall(r'[A-Za-z_]\w*', expr):
        m = re.search(rf'^[ \t]*#[ \t]*define[ \t]+{name}\b', text, re.M)
        if m: return text[:m.start()].count('\n') + 1
    return 0


def c_value(expr):
    try:
        return cdefs.parse(f'#define ROW {expr}\n', names=['ROW'], known=O)['ROW']
    except cdefs.CDefError as e:
        raise ValueError(f'C side {expr!r} is not an integer over offsets.inc defines ({e})') from None


def rgb(v):
    if isinstance(v, str): return tuple(int(v[i:i + 2], 16) for i in (1, 3, 5))
    if isinstance(v, int): return (v & 255, (v >> 8) & 255, (v >> 16) & 255)
    return tuple(v)


def main():
    ok = xfailed = fail = 0
    header_text = open(HEADER, encoding='utf-8').read()
    modules = {}
    for row in ROWS:
        mod, py, c = row[:3]
        kind = row[3] if len(row) > 3 else 'int'
        key = (mod, py, c)
        try:
            if mod not in modules:
                modules[mod] = importlib.import_module(mod)
            m = modules[mod]
            pv = eval(py, vars(m))   # the table's own expressions (names and indexes of a module), not extracted code
            cv = c_value(c)
            path = os.path.relpath(m.__file__, ROOT)
            where = (f'{path}:{py_line(m.__file__, py)} {py} = {pv!r} vs patch/offsets.inc:{c_line(header_text, c)} '
                     f'{c} = {cv:#x}' if kind == 'rgb' else
                     f'{path}:{py_line(m.__file__, py)} {py} = {pv!r} vs patch/offsets.inc:{c_line(header_text, c)} {c} = {cv}')
            agree = (rgb(pv) == rgb(cv)) if kind == 'rgb' else (int(pv) == cv)
        except Exception as e:   # a missing name or a bad expression is a failure of the row, reported with the row
            print(f'FAIL {mod}.{py} vs {c}: {type(e).__name__}: {e}')
            fail += 1
            continue
        if key in XFAIL:
            if agree:
                print(f'FAIL {where}: the XFAIL row now agrees; remove it from XFAIL')
                fail += 1
            else:
                print(f'MISMATCH (expected, {XFAIL[key]}) {where}')
                xfailed += 1
        elif agree:
            ok += 1
        else:
            print(f'FAIL MISMATCH {where}')
            fail += 1
    print(f'info: {len(ROWS)} rows; {len(SKIPPED)} skipped literal groups (see SKIPPED)')
    print(f'{ok} passed, {xfailed} MISMATCH expected, {fail} failed')
    sys.exit(1 if fail else 0)


if __name__ == '__main__':
    main()
