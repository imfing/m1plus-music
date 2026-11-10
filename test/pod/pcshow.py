"""The Podcasts Show page (patch/podcasts.c, patch/pcwrap.c, docs/modules/podcasts.md "The Show page"): the header of the album page's manner (a 160 px cover, the name, one Latest Episode pill, the
description and the "Category - Author" line) and its layout numbers against the shared model (tools/pod_show.py), the cover tint reused from the album page (the window colour, the gradient image, the
status bar, the tone cache), the navbar ("..." | Now Playing, the small title and the fade once scrolled), the fixed height cells (date line with its badges, the title, the description, the state
pill, the "...") in every combination of badges and every state of the pill with what a tap on each does, the two bottom sheets (the show's: each row shown only where it applies and what it does, a
single-feed refresh, Select Episodes, Mark All as Played, Unsubscribe in both cases; an episode's), the Latest Episode pill in both cases, the line breaking with the kinsoku rules against the Python
port, the strings' widths in the 13 languages, and the screen-off rule. The compiled payload runs under Unicorn; the card is a dict of paths."""
import importlib.util, os, struct, sys
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


PCP, PCN, DL, SEL = sibling('podcasts'), sibling('pcnet'), sibling('pcdl'), sibling('pcsel')
import pod_show, mod_icons   # noqa: E402

RP, ROW, CELL, NOW, PN = PCP.ROOT, PCP.ROW, PCP.CELL, DL.NOW, DL.PN
DAY, MB = 86400, 1048576
DEEP = 'Deep'
FEED = 'https://f.example/deep'
_FONT = []


def font():
    if not _FONT: _FONT.append(pod_show.Font(pod_show.font_path(WORK)))
    return _FONT[0]


class SM(PCN.NM):
    """The page machine with the real font's widths for widget_measure_text (by the style label's size), and rmdir."""
    px = None

    def with_bar(self):
        nav = self.alloc(0x80); self.bar = self.alloc(0x80)
        self.children[self.wm] = [nav, self.bar]; self.types[nav] = 'system_bar_bottom'; self.types[self.bar] = 'system_bar'
        return self

    def bar_styles(self): return [s[2] for s in self.styled if s[0] == self.bar]

    def _hook(self, u, address, size, _):
        name = self.handlers.get(address, '')
        if name not in ('widget_measure_text', 'rmdir'): return super()._hook(u, address, size, _)
        a0, a1 = (u.reg_read(r) for r in (UC_MIPS_REG_A0, UC_MIPS_REG_A1))
        if name == 'widget_measure_text':
            n = 0
            while self.word(a1 + 4 * n): n += 1
            t = ''.join(chr(c) for c in struct.unpack(f'<{n}I', self.u.mem_read(a1, 4 * n))) if n else ''
            w = float(font().width(t, (self.px or {}).get(a0, 16))) if t else 0.0
            u.reg_write(UC_MIPS_REG_F0, struct.unpack('<I', struct.pack('<f', w))[0]); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))
            return
        if name == 'rmdir':
            p = self.read_cstr(a0); self.calls.append(('rmdir', p))
            kids = [q for q in list(self.fs) + list(self.dirs) if q != p and q.startswith(p + '/')]
            ret = -1 if kids or p not in self.dirs else 0
            if ret == 0: self.dirs.discard(p)
            u.reg_write(UC_MIPS_REG_V0, ret & 0xffffffff); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))
            return
        return super()._hook(u, address, size, _)


def flags(m, n): return SEL.flags(m, n)


def eps_text(entries):
    """.episodes text: entries are dicts (g, p, d, l, f, t, u, x)."""
    out = PCP.EPS_HEAD
    for e in entries:
        out += '\t'.join(f'{k}={e[k]}' for k in ('g', 'p', 'd', 'l', 'f', 't', 'u', 'x') if k in e and e[k] != '') + '\n'
    return out.encode()


LONG_TITLE = "Trump's Tariffs, Nvidia's $5T Moment, AI Bubble Debate, Fed Rate Cut and the Government Shutdown Fallout"
LONG_DESC = ("Chamath, Jason, Sacks and Friedberg break down the week's biggest stories: the market's reaction, what the Fed's next move means for tech valuations, and why the shutdown is dragging on.")
SHOW_TITLE = 'All-In with Chamath, Jason, Sacks & Friedberg'
SHOW_DESC = 'Chamath, Jason, Sacks and Friedberg are the besties: four friends with a show about the markets, tech, politics and everything in between, every week.'


def entry(i, **kw):
    e = dict(g=f'g{i}', p=NOW - (i + 1) * DAY, d=3600, l=48 * MB, f=f'e{i}.mp3', t=f'Episode {i}', u=f'https://cdn.example/e{i}.mp3', x=f'About episode {i}.')
    e.update(kw)
    return e


def deep_card(m, feed=True, entries=None, files=(0, 1, 2), desc=SHOW_DESC, author='All-In Podcast', category='Technology', checked=None, cover=True):
    """The Deep show: a feed, a description, an author and a category; eight episodes (0 on the card unplayed, 1 played, 2 started, 3 remote with a size, 4 remote without,
    5 downloading, 6 a paused .part, 7 failed) unless `entries` says otherwise; the files of `files` are on the card. Alpha Show and bravo (PCP.page_card) are the other shows."""
    PCP.page_card(m)
    m.put(f'{RP}/{DEEP}/.show', (f'M1PLUS-SHOW 1\ntitle={SHOW_TITLE}\n' + (f'feed={FEED}\n' if feed else '') + f'image=\nchecked={NOW - 3600 if checked is None else checked}\n'
                                 + (f'author={author}\n' if author else '') + (f'category={category}\n' if category else '') + (f'desc={desc}\n' if desc else '')).encode())
    es = entries if entries is not None else [
        entry(0, t=LONG_TITLE, x=LONG_DESC, d=4320), entry(1, d=3960), entry(2, d=3600), entry(3), entry(4, l=0), entry(5), entry(6), entry(7)]
    m.put(f'{RP}/{DEEP}/.episodes', eps_text(es))
    for e in es:
        i = int(e['f'][1:-4])
        if i in files: m.put(f'{RP}/{DEEP}/{e["f"]}', b'audio')
    if entries is None: m.put(f'{RP}/{DEEP}/e6.mp3.part', b'half')
    if cover:
        m.put(f'{RP}/{DEEP}/cover.jpg', PCP.jpeg(600, 600))
        m.images[f'file://{RP}/{DEEP}/cover.jpg'] = (600, 600, bytes((200, 40, 40, 255)) * 600 * 600)
    m.images.update({'unselect': (26, 26, struct.pack('<I', 0xff111111) * 676), 'selected': (26, 26, struct.pack('<I', 0xff2222ee) * 676)})
    m.present.add(PCN.CA)
    m.wall = NOW


def machine(card=deep_card, up=True, **kw):
    """The page open on the Shows level (up=False: not opened yet), the font model set for the style labels."""
    m = PCP.page_machine(lambda mm: card(mm, **kw) if kw else card(mm), SM)
    m.px = {m.widgets[n]: px for n, px, *_ in pod_ui.PS_STYLES}
    m.px.update({m.widgets['pg_sh_speed_vl']: pod_ui.PS_SHEET_PX, m.widgets['pg_sh_refresh_vl']: pod_ui.PS_SHEET_PX, m.widgets['pg_sh_order_vl']: pod_ui.PS_SHEET_PX})
    m.px.update({m.widgets[n]: px for n, px in (('label_row_title', 21), ('label_row_sub', 18))})
    for r, _, label, *_ in pod_ui.PS_SHEET_ROWS:
        m.px[m.widgets[f'pg_sh_{r}_tx']] = pod_ui.PS_SHEET_PX
        m.wtext[m.widgets[f'pg_sh_{r}_tx']] = label   # (the label's text, as the asset's tr_text gives it)
    m.curl_site = DL.server(DL.DATA)
    if up: assert m.call(PSYMS['podcasts_open'], count=40000000) == 0
    return m


def open_show(m, title=SHOW_TITLE[:6]):
    """A tap on the show's cover on the Shows level (its name is cut with an ellipsis under it: matched by its start)."""
    PCP.tap_show(m, title)


def shown(**kw):
    """The page with the Deep show open, with its downloading / failed states set and a place on episode 2, as the card_machine of this file describes."""
    m = machine(**kw)
    # a place on episode 2: the page's timer notes what the player has played
    h2 = PCP.pc_hash(f'{RP}/{DEEP}/e2.mp3')
    m.call(PSYMS['pc_mark'], a0=PCP.pc_hash(f'{RP}/{DEEP}/e1.mp3'), a1=1, count=2000000)
    m.pt = (1500, 3600, 1); m.status = 2
    m.play([m.record(path=f'{RP}/{DEEP}/e2.mp3')], 0); m.clock += 40000
    m.call(PSYMS['pc_note'], a0=m.record(path=f'{RP}/{DEEP}/e2.mp3'), count=40000000)
    assert m.state(h2)[0] == 1, m.state(h2)
    DL.poke_slot(m, 0, DEEP, 'e5.mp3', 2, seq=1)
    m.setword(DL.pn_at(DL.DKEY), DL.key_of(DEEP, 'e5.mp3')); m.setword(DL.pn_at(DL.DGOT), 420000); m.setword(DL.pn_at(DL.DTOTAL), 1000000)
    m.setword(DL.pn_at(DL.KIND), 2); m.setword(DL.pn_at(0), 1); m.setword(DL.pn_at(DL.DSEQ), 10)
    DL.poke_fail(m, 0, DEEP, 'e7.mp3', PN['NET'])
    open_show(m)
    return m


def hdr_model(m, title=SHOW_TITLE, desc=SHOW_DESC, category='Technology', author='All-In Podcast', has_latest=True):
    return pod_show.header(font(), title, desc, category, author, has_latest)


def frame(m, off=0):
    """A frame of the content view at scroll offset off: (blits, texts, styles, fills)."""
    return PCP.paint(m, off)


def texts_of(m, style, off=0):
    _, texts, styles, _ = frame(m, off)
    return [(t, r) for (t, r), s in zip(texts, styles) if s == style]


def asset_tests(ctx):
    """The page's asset: the tint under the transparent list, the navbar's "...", the sheets' widgets, the styles, the images."""
    expect = ctx.expect
    path = os.path.join(WORK, 'rootfs', 'release/assets/default/raw/ui/m1plus_podcasts.bin')
    tree = awtk_ui.parse(open(path, 'rb').read())
    kids = [c.name for c in tree.children]
    expect(kids[0] == 'img_ah_tint' and tree.children[0].type == 'image' and tree.children[0].get('image') == 'ah_tint' and (tree.children[0].w, tree.children[0].h) == (320, 450)
           and tree.children[0].get('visible') == 'false' and tree.children[0].get('sensitive') == 'false',
           'the album page\'s gradient image (ah_tint, 320 x 450) is the window\'s first child, hidden and insensitive until the page is tinted')
    lv = tree.find('podcasts_listview')
    sv, grid = lv.children[0], lv.children[0].children[0]
    expect(all(w.get(f'style:{st}:bg_color') == '#00000000' for w in (lv, sv) for st in ('normal', 'disable', 'focused')) and grid.get('style:normal:bg_color') == '#00000000',
           'the list, its scroll view and the content view are transparent (over the black window they look as before)')
    expect(tree.get('style:normal:bg_color') == '#000000', 'the window is black until the payload tints it')
    nav = tree.find('navigationbar_view')
    more = tree.find('btn_more')
    expect(more is not None and more in nav.children and more.x == O['NAV_VIEW_X'] and more.get('style:normal:icon') == 'pod_nav_more' and more.get('visible') == 'false' and more.get('sensitive') == 'false',
           'the navbar has the "..." (the glass left cap, at the capsule\'s slot), hidden and insensitive')
    for name, px, colour, align in pod_ui.PS_STYLES:
        w = tree.find(name)
        expect(w is not None and w.get('visible') == 'false' and w.get('sensitive') == 'false' and w.get('style:normal:font_size') == str(px) and w.get('style:normal:text_color') == colour
               and w.get('style:normal:text_align_h') == align, f'{name}: {px} px {colour} {align}, hidden')
    expect(contrast('#FFFFFF', '#000000') >= 4.5 and all(contrast(c, '#000000') >= 4.5 for _, _, c, _ in pod_ui.PS_STYLES if c != '#000000'), 'every light style reads on black (4.5:1)')
    # the sheet
    scrim, card = tree.find('pg_sh_scrim'), tree.find('pg_sh_card')
    expect(scrim.type == 'button' and (scrim.x, scrim.y, scrim.w, scrim.h) == (0, 0, 320, 450) and scrim.get('visible') == 'false' and scrim.get('sensitive') == 'false' and scrim.get('style:normal:bg_color') == pod_ui.PL_DIM,
           'the scrim covers the client area, dimmed as the Playlists menu\'s, hidden and insensitive')
    rh = O['PM_ROW_H']
    expect((card.x, card.y, card.w, card.h) == (0, 450 - 6 * rh, 320, 6 * rh) and card.get('style:normal:bg_image') == 'pc_sheet6' and card.get('visible') == 'false',
           'the card is the six-row sheet at the bottom of the window (the payload sets its size and picture)')
    expect([c.name for c in card.children] == [f'pg_sh_{r}' for r in PCP.SHEET_ROWS] and len(PCP.SHEET_ROWS) == 14, 'fourteen rows (Episode Order last): the show sheet\'s five, the episode sheet\'s five (Save Episode), the Shows level\'s Import from Card and Subscriptions, the Subscriptions level\'s Export OPML (Select is the show sheet\'s, relabelled)')
    for r, icon, label, value, red in pod_ui.PS_SHEET_ROWS:
        row = tree.find(f'pg_sh_{r}')
        ic, tx, hr = tree.find(f'pg_sh_{r}_ic'), tree.find(f'pg_sh_{r}_tx'), tree.find(f'pg_sh_{r}_hr')
        expect(row.type == 'button' and row.h == rh and row.w == 320 and row.get('visible') == 'false' and row.get('sensitive') == 'false' and row.get('style:pressed:bg_color') == pod_ui.PL_PRESSED
               and row.get('style:normal:bg_color') == '#00000000', f'{r}: a 50 px row button, transparent, 6 % white pressed, hidden')
        expect(ic.get('image') == icon and ic.get('sensitive') == 'false' and (ic.w, ic.h) == (20, 20) and ic.x == O['PS_SHEET_ICON_X'] and tx.x == O['PS_SHEET_TEXT_X'] and tx.get('sensitive') == 'false'
               and tx.get('style:normal:font_size') == '18' and tx.get('style:normal:text_color') == ('#FF6B6B' if red else '#FFFFFF') and pod_i18n.shown_english(tx) == label, f'{r}: the glyph {icon}, the 18 px label "{label}"{" in the delete red" if red else ""}')
        expect(hr.h == 1 and hr.get('sensitive') == 'false' and hr.get('style:normal:bg_color') == pod_ui.PL_HAIR, f'{r}: a hairline on its top')
        vl = tree.find(f'pg_sh_{r}_vl')
        expect(all(n.get(f'style:{st}:margin_{side}') == '0' for n in (tx, vl) if n is not None for st in ('normal', 'disable', 'focused') for side in ('left', 'right')),
               f'{r}: the label and its value have no margins (stock\'s 2 px each side cut a value as wide as its text to "...")')
        expect((vl is not None) == value and (vl is None or (vl.get('style:normal:text_align_h') == 'right' and vl.get('style:normal:text_color') == '#AAAAAA' and vl.x + vl.w == O['PS_SHEET_VALUE_R'])), f'{r}: {"a grey value label right aligned to x 304" if value else "no value"}')
    expect(contrast('#FF6B6B', '#1E1E20') >= 4.5, 'the red label reads on the glass (4.5:1)')
    # the images
    img = lambda n: os.path.join(WORK, 'rootfs', 'release/assets/default/raw/images/xx', n + '.png')
    from PIL import Image
    a = Image.open(img('pc_atlas'))
    expect(a.size == (O['PA_SIZE'], O['PA_SIZE']) and a.size == (mod_icons.PA_SIZE,) * 2, f'the atlas is {O["PA_SIZE"]} px square in the tree')
    for n, h in mod_icons.PC_SHEETS:
        im = Image.open(img(n))
        expect(im.size == (320, h) and h // rh == int(n[-1]), f'{n}: 320 x {h}, the glass of {n[-1]} row(s)')
    for n, g, _ in mod_icons.PC_SHEET_ICONS:
        expect(Image.open(img(n)).size == (20, 20), f'{n}: the 20 px glyph ({g})')
    expect(os.path.isfile(os.path.join(mod_icons.LUCIDE_SVG, 'arrow-down.svg')) and any(g == 'arrow-down' for _, g, _ in mod_icons.PC_SHEET_ICONS) and 'arrow-down' in mod_icons.PC_GLYPHS,
           'the Lucide arrow-down is the download symbol of the sheet, the pill and the badge (not download or arrow-down-to-line)')
    # the atlas numbers are the payload's
    expect(all(getattr(mod_icons, k) == O[k] for k in ('PA_SIZE', 'PA_RING_PX', 'PA_RING_N', 'PA_RING_COLS', 'PA_G_Y', 'PA_G_PX', 'PA_DOTS_Y', 'PA_DOTS_PX', 'PA_BADGE_X', 'PA_BADGE_PX', 'PA_PILL_Y', 'PA_PILLF_X', 'PA_PILLO_X',
                                                       'PA_PILLW_X', 'PA_PILLR_X', 'PA_PILL_PX', 'PA_PILLW_PX', 'PA_FILL_A', 'PA_RING_A')), 'tools/mod_icons.py and patch/offsets.inc agree on every atlas number')
    px = a.convert('RGBA')
    def alpha(x, y, w=1, h=1): return max(px.getpixel((x + i, y + j))[3] for i in range(w) for j in range(h))
    expect(all(alpha(k % O['PA_RING_COLS'] * 16, k // O['PA_RING_COLS'] * 16, 16, 16) > 0 for k in range(O['PA_RING_N'])), 'the twelve ring steps are drawn')
    expect(all(alpha(i * O['PA_G_PX'], O['PA_G_Y'], 16, 16) > 0 for i in range(6)) and alpha(0, O['PA_DOTS_Y'], 20, 20) > 0 and alpha(O['PA_BADGE_X'], O['PA_DOTS_Y'], 12, 12) > 0, 'the glyphs, the "..." and the badge are drawn')
    cx, cy = O['PA_BADGE_X'] + 6, O['PA_DOTS_Y'] + 6
    cut = [px.getpixel((cx + dx, cy + dy))[3] for dx in range(-2, 3) for dy in range(-3, 4)]
    expect(min(cut) == 0 and max(cut) == 255 and px.getpixel((O['PA_BADGE_X'] + 1, O['PA_DOTS_Y'] + 6))[3] > 200, 'the badge is a light disc with the arrow cut out of it (transparent)')
    expect(px.getpixel((O['PA_BADGE_X'] + 1, O['PA_DOTS_Y'] + 6))[:3] == mod_icons.PA_BADGE_GREY, 'in a light grey')
    expect(px.getpixel((O['PA_PILLF_X'] + 15, O['PA_PILL_Y'] + 15))[3] == O['PA_FILL_A'] and abs(px.getpixel((O['PA_PILLO_X'] + 15, O['PA_PILL_Y'] + 1))[3] - O['PA_RING_A']) <= 10 and px.getpixel((O['PA_PILLO_X'] + 15, O['PA_PILL_Y'] + 15))[3] == 0
           and px.getpixel((O['PA_PILLW_X'] + 20, O['PA_PILL_Y'] + 20))[3] == 255 and abs(px.getpixel((O['PA_PILLR_X'] + 20, O['PA_PILL_Y'] + 1))[3] - O['PA_RING_A']) <= 10,
           f'the pills\' ends: filled (alpha 56), outlined (a 2 px ring, alpha 110), the Latest Episode pill\'s white and outlined 40 px discs {[px.getpixel(p) for p in ((O["PA_PILLF_X"] + 15, O["PA_PILL_Y"] + 15), (O["PA_PILLO_X"] + 15, O["PA_PILL_Y"] + 1), (O["PA_PILLO_X"] + 15, O["PA_PILL_Y"] + 15), (O["PA_PILLW_X"] + 20, O["PA_PILL_Y"] + 20), (O["PA_PILLR_X"] + 20, O["PA_PILL_Y"] + 1))]}')


def layout_tests(ctx):
    """The header and the cells against the shared model: the numbers of patch/offsets.inc, the wrap of the font."""
    expect = ctx.expect
    m = shown()
    h = hdr_model(m)
    expect(PCP.title_text(m).startswith('All-In with') and PCP.title_text(m).endswith('…') and m.props.get((m.sv, 'yoffset')) == 0 and m.props.get((m.widgets['label_title'], 'visible')) == 0,
           f'the show opens at the top, its title (cut to the label) in the navbar label, which is hidden until the header has scrolled away ({PCP.title_text(m)})')
    bl, texts, styles, fills = frame(m)
    covers = [b for b in bl if tuple(b[2][2:]) == (O['PS_ART'], O['PS_ART'])]
    expect([tuple(b[2]) for b in covers] == [(O['PS_ART_X'], 0, 160, 160)] and O['PS_ART'] == 160 and O['PS_ART_X'] == 80 and O['PS_ART_R'] == 10,
           f'the cover: 160 px at x 80 (centred), 10 px corners, flush with the list ({[tuple(b[2]) for b in covers]})')
    name = texts_of(m, 'label_ps_name')
    expect([t for t, _ in name] == h['name'] and len(h['name']) == 2 and [r for _, r in name] == [(17, h['y_name'] + k * 26, 286, 26) for k in range(2)],
           f'the name: 14 px under the cover, 22 px, centred, two lines at most ({[t for t, _ in name]})')
    expect(h['y_name'] == 160 + 14 and O['PS_NAME_PX'] == 22 and pod_show.PX['label_ps_name'] == 22, 'its place and size are the album page\'s (14 px under the cover, 22 px)')
    desc = texts_of(m, 'label_ps_sec')
    expect([t for t, _ in desc] == h['desc'] and len(h['desc']) == 2 and h['desc'][-1].endswith('…') and [r for _, r in desc] == [(16, h['y_desc'] + k * 21, 288, 21) for k in range(2)],
           f'the description: two grey lines, an ellipsis, no MORE ({[t for t, _ in desc]})')
    expect(not [t for t, _ in texts if t in ('MORE', 'More')], 'there is no MORE label (no detail view is behind it)')
    meta = texts_of(m, 'label_ps_meta')
    expect([t for t, _ in meta] == ['Technology · All-In Podcast'] and meta[0][1] == (16, h['y_meta'], 288, 22), f'the meta line: Category · Author, no cadence ({meta})')
    head = texts_of(m, 'label_ps_head', 100)
    expect(head == [('Episodes', (16, h['y_head'] - 100, 288, 28))] and h['h'] == h['y_head'] + 34, f'the Episodes header ({head}); the cells start at {h["h"]}')
    expect(m.props.get((m.sv, 'virtual_h')) == pod_show.content_height(h['h'], 8), f'the content: header, eight cells of {CELL} px, 20 px of air ({m.props.get((m.sv, "virtual_h"))})')
    # the latest pill's place: centred under the name, 40 px high
    lat = texts_of(m, 'label_ps_latest')
    expect(len(lat) == 1 and lat[0][0] == 'Latest Episode' and lat[0][1][1] == h['y_latest'] and lat[0][1][3] == 40 and h['y_latest'] == h['y_name'] + 2 * 26 + 12, f'the Latest Episode label ({lat})')
    w = pod_show.latest_width(font(), 'Latest Episode', True)
    expect(lat[0][1][0] == (320 - w) // 2 + 18 + 14 + 8 and lat[0][1][0] + lat[0][1][2] == (320 - w) // 2 + w, f'centred: the pill is {w} px wide ({lat[0][1]})')
    pill_bl = [b for b in bl if b[2][1] == h['y_latest'] and b[2][3] == 40]
    expect(len(pill_bl) == 2 and sorted(b[2][0] for b in pill_bl) == [(320 - w) // 2, (320 - w) // 2 + w - 20] and all(b[1][0] in (O['PA_PILLW_X'], O['PA_PILLW_X'] + 20) for b in pill_bl),
           'its two ends are halves of the white 40 px disc')
    expect([f for f in fills if f[0] == 0xffffffff and f[2] == h['y_latest'] and f[4] == 40] == [(0xffffffff, (320 - w) // 2 + 20, h['y_latest'], w - 40, 40)] or
           any(f[0] == 0xffffffff and f[2] == h['y_latest'] for f in fills), 'and the body between them a white fill')
    glyph = [b for b in bl if tuple(b[2][2:]) == (16, 16) and b[2][1] == h['y_latest'] + 12]
    expect(len(glyph) == 1 and glyph[0][1][:2] == (O['PA_PLAYK'] * 16, O['PA_G_Y']), 'the dark play glyph in it')
    # no round download button: the header has only the cover, the pill's ends and glyph
    expect(not [b for b in bl if b[2][1] < h['y_name'] and tuple(b[2][2:]) != (160, 160)], 'no round download button (nothing is drawn but the cover above the name)')
    # the cells: fixed height, newest first
    c = PCP.all_cells(m)
    expect(sorted(c) == list(range(8)) and [' '.join(c[i]['title']) for i in range(8)][1:] == [f'Episode {i}' for i in range(1, 8)], 'eight cells, newest first, one per episode')
    cm = pod_show.cell(font(), LONG_TITLE, LONG_DESC)
    expect(c[0]['title'] == cm[0] and c[0]['desc'] == cm[1] and len(cm[0]) == 2 and cm[0][-1].endswith('…') and len(cm[1]) == 2, f'a cell\'s title and description wrapped as the model wraps them (two lines each, an ellipsis): {c[0]["title"]}')
    y0 = lambda i: h['h'] + i * CELL
    _, texts, styles, fills = frame(m, h['h'])
    rects = lambda style: [r for (t, r), s in zip(texts, styles) if s == style]
    expect(rects('label_ps_date')[0] == (34, 9, 270, 22), f'the date line is 9 px into the cell, 22 px high, after the disc badge ({rects("label_ps_date")[0]})')
    t0 = [r for (t, r), s in zip(texts, styles) if s == 'label_ps_ctitle' and r[1] < CELL]
    expect([(r[1], r[3]) for r in t0] == [(32, 24), (56, 24)] and all(r[0] == 16 and r[2] == 288 for r in t0), f'the title: two 24 px lines from 32, 16 px in, 288 wide ({t0})')
    d0 = [r for (t, r), s in zip(texts, styles) if s == 'label_ps_cdesc' and r[1] < CELL]
    expect([(r[1], r[3]) for r in d0] == [(83, 20), (103, 20)], f'the description: two 20 px grey lines from 83 ({d0})')
    p0 = [r for (t, r), s in zip(texts, styles) if s == 'label_ps_pill' and r[1] < CELL]
    expect(len(p0) == 1 and (p0[0][1], p0[0][3]) == (131, 30), 'the state pill: 30 px high, 131 px into the cell')
    expect(O['PS_CELL_H'] == 173 and all(y0(i + 1) - y0(i) == 173 for i in range(7)), 'every cell is 173 px high whatever it holds')
    hair = [f for f in fills if f[0] == 0x22ffffff]
    expect(all(f[1] == 16 and f[3] == 304 for f in hair) and [f[2] for f in hair][:2] == [172, 172 + CELL], 'a 13 % white hairline under each cell, from x 16')
    dots = [b for b in frame(m, h['h'])[0] if tuple(b[2][2:]) == (20, 20)]
    expect(dots and all(b[2][0] == 282 and b[1][:2] == (0, O['PA_DOTS_Y']) for b in dots) and dots[0][2][1] == 131 + 15 - 10, 'the "..." is a 20 px glyph centred at x 292 on the pill\'s middle')
    # shows with less: no description, no meta, no episode; a short title; a CJK one
    for kw, what in ((dict(desc='', author='', category=''), 'no description and no meta'), (dict(desc='Short.', author='', category='News'), 'a short description and a category only'),
                     (dict(author='Someone', category=''), 'an author only')):
        m2 = shown(**kw)
        h2 = hdr_model(m2, desc=kw.get('desc', SHOW_DESC), category=kw.get('category', 'Technology'), author=kw.get('author', 'All-In Podcast'))
        expect(PCP.hdr(m2) == h2['h'] and m2.props.get((m2.sv, 'virtual_h')) == pod_show.content_height(h2['h'], 8), f'{what}: the blocks that are not there leave no gap (header {PCP.hdr(m2)} = {h2["h"]})')


def cell_parts(m, i):
    """What cell i paints, cell-relative (the frame is scrolled to show it whole): (sprites [(src x, src y, w, h, dst x, dst y)], texts {style: [(text, (x, y, w, h))]}, fills [(colour, x, y, w, h)])."""
    h = PCP.hdr(m)
    bl, tx, st, fl = frame(m, h + i * CELL - 20)
    y = 20
    sprites = [(b[1][0], b[1][1], b[2][2], b[2][3], b[2][0], b[2][1] - y) for b in bl if y <= b[2][1] < y + CELL]
    texts = {}
    for (t, r), s in zip(tx, st):
        if y <= r[1] < y + CELL: texts.setdefault(s, []).append((t, (r[0], r[1] - y, r[2], r[3])))
    fills = [(f[0], f[1], f[2] - y, f[3], f[4]) for f in fl if y <= f[2] < y + CELL]
    return sprites, texts, fills


def pill_expect(label, kind, glyph, ring=None, x=16, sx=0):
    """The sprites, fills and label of a state pill at cell x: kind 'play'/'resume' are filled, the others outlined."""
    o = O
    w = pod_show.pill_width(font(), label)
    filled = kind in ('play', 'resume')
    ax = o['PA_PILLF_X'] if filled else o['PA_PILLO_X']
    gl = (ring % o['PA_RING_COLS'] * 16, ring // o['PA_RING_COLS'] * 16) if ring is not None else (glyph * 16, o['PA_G_Y'])
    sprites = [(ax, o['PA_PILL_Y'], 15, 30, x, 131), (ax + 15, o['PA_PILL_Y'], 15, 30, x + w - 15, 131), (gl[0], gl[1], 16, 16, x + 10, 131 + 7)]
    colour = (o['PA_FILL_A'] if filled else o['PA_RING_A']) << 24 | 0xffffff
    fills = [(colour, x + 15, 131, w - 30, 30)] if filled else [(colour, x + 15, 131, w - 30, 2), (colour, x + 15, 131 + 28, w - 30, 2)]
    return w, sprites, fills, (label, (x + 10 + 16 + 6, 131, w - 32, 30))


def cell_tests(ctx):
    """The cells: the badges in every combination, the state pill of every state with its sprites, fills and label, the title brightness, the hairline."""
    expect = ctx.expect
    m = shown()
    o = O
    A = o
    states = [  # cell, label, kind, glyph, ring, check, disc, played
        (0, '72m', 'play', A['PA_PLAY'], None, False, True, False),
        (1, '66m', 'play', A['PA_PLAY'], None, True, True, True),
        (2, '35m left', 'resume', A['PA_RETRY'], None, False, True, False),
        (3, '48 MB', 'down', A['PA_ARROW'], None, False, False, False),
        (4, 'Download', 'down', A['PA_ARROW'], None, False, False, False),
        (5, '42%', 'ring', None, 5, False, False, False),
        (6, 'Paused', 'paused', A['PA_PAUSE'], None, False, False, False),
        (7, 'Retry', 'retry', A['PA_RETRY'], None, False, False, False)]
    for i, label, kind, glyph, ring, check, disc, played in states:
        sprites, texts, fills = cell_parts(m, i)
        w, want_sp, want_fl, want_tx = pill_expect(label, kind, glyph, ring)
        expect(all(s in sprites for s in want_sp), f'cell {i} ({kind}, "{label}"): the pill\'s two ends and its glyph/ring are the atlas\' sprites in place')
        expect(all(f in fills for f in want_fl), f'cell {i}: the pill\'s body is {"one fill (play-type: filled)" if kind in ("play", "resume") else "two 2 px lines (download-type: outlined)"}')
        expect(texts.get('label_ps_pill') == [want_tx], f'cell {i}: the label "{label}" is left aligned after the glyph, {w} px pill ({texts.get("label_ps_pill")})')
        x = 16
        badge = (A['PA_BADGE_X'], A['PA_DOTS_Y'], 12, 12)
        got_check = [s for s in sprites if s[:4] == (A['PA_CHECK'] * 16, A['PA_G_Y'], 16, 16)]
        got_disc = [s for s in sprites if s[:4] == badge]
        if check: x += 20
        expect(bool(got_check) == check and (not check or got_check[0][4:] == (15, 12)), f'cell {i}: the check{" is there at x 15" if check else " is not"} (played: {played})')
        expect(bool(got_disc) == disc and (not disc or got_disc[0][4:] == (x, 14)), f'cell {i}: the on-the-card disc{" is there, 12 px, in the date line" if disc else " is not"}')
        if disc: x += 18
        d = texts.get('label_ps_date', [])
        expect(len(d) == 1 and d[0][1] == (x, 9, 304 - x, 22), f'cell {i}: the date after the badges, from x {x} ({d})')
        expect(('label_ps_cdim' in texts) == played and ('label_ps_ctitle' in texts) == (not played), f'cell {i}: the title is {"grey (played)" if played else "bright (unplayed)"}')
        expect(sum(1 for s in sprites if s[:4] == (0, A['PA_DOTS_Y'], 20, 20)) == 1 and [s for s in sprites if s[:4] == (0, A['PA_DOTS_Y'], 20, 20)][0][4:] == (282, 136), f'cell {i}: the "..." (44 px target around it)')
        expect(any(f[0] == 0x22ffffff and f[1] == 16 and f[2] == 172 and f[3] == 304 for f in fills), f'cell {i}: the hairline')
    # both badges: "check, disc, Oct 10" (a played, downloaded episode); the date line reads as the date model says
    sprites, texts, _ = cell_parts(m, 1)
    expect(texts['label_ps_date'][0][0] == PCP.when_model(NOW - 2 * DAY, NOW), f'the date line: {texts["label_ps_date"][0][0]}')
    # the pill widths are the model's (measured in the real font)
    expect(pod_show.pill_width(font(), '72m') == 10 + 16 + 6 + font().width('72m', 16) + 12, 'a pill is the pad, the 16 px glyph, 6 px, the label and the pad')
    # a played remote episode: the check without the disc
    PCP.dots(m, 3); PCP.click(m, 'pg_sh_mark')
    sprites, texts, fills = cell_parts(m, 3)
    expect([s for s in sprites if s[:4] == (A['PA_CHECK'] * 16, A['PA_G_Y'], 16, 16)] and not [s for s in sprites if s[:4] == (A['PA_BADGE_X'], A['PA_DOTS_Y'], 12, 12)] and 'label_ps_cdim' in texts,
           'an episode that is not on the card but was played: the check alone, a grey title, its download pill')
    # the cell is the same height whatever it holds: a title of one word, no description
    m2 = shown(entries=[entry(0, t='Short', x=''), entry(1, t=LONG_TITLE, x=LONG_DESC)], files=(0, 1))
    sp, tx_, fl_ = cell_parts(m2, 0)
    expect(tx_['label_ps_ctitle'] == [('Short', (16, 32, 288, 24))] and 'label_ps_cdesc' not in tx_ and tx_['label_ps_pill'][0][1][1] == 131, 'a one line title and no description leave the pill where it is (a fixed height)')
    expect(PCP.hdr(m2) + 2 * CELL + 20 == m2.props.get((m2.sv, 'virtual_h')), 'two cells, two heights')


def tap_tests(ctx):
    """A tap on each state's pill, on a cell's body and on its "...": play (a started one keeps its place, a played one starts again), download, pause, resume, retry."""
    expect = ctx.expect
    m = shown()
    h0, h1, h2 = (PCP.pc_hash(f'{RP}/{DEEP}/e{i}.mp3') for i in range(3))
    # local: the pill and the body play it with the queue of the files from the first cell
    m.calls = []; PCP.act(m, 0)
    nav = [c for c in m.calls if c[0] == 'navigator_to_with_context']
    q, idx = m.played
    expect(len(nav) == 1 and idx == 0 and [m.read_cstr(m.word(r + O['REC_PATH'])) for r in q] == [f'{RP}/{DEEP}/e{i}.mp3' for i in range(3)], 'a tap on the "72m" pill plays the episode with the files that follow')
    m.calls = []; PCP.body(m, 2)
    expect(not [c for c in m.calls if c[0] == 'navigator_to_with_context'] and m.state(h2) == (1, 1500, 3600) and texts_of(m, 'label_ps_head') and not texts_of(m, 'label_ps_ctitle'),
           'a tap on the body of a started episode opens its episode page (docs: "The episode page"), it plays nothing and keeps the place')
    PCP.click(m, 'btn_return')
    expect(not texts_of(m, 'label_ps_head') and texts_of(m, 'label_ps_name'), 'Back returns to the show\'s list (its header is back, the episode page gone)')
    m.calls = []; PCP.act(m, 2)
    expect(len([c for c in m.calls if c[0] == 'navigator_to_with_context']) == 1 and m.state(h2) == (1, 1500, 3600), 'the "35m left" pill resumes it')
    m.calls = []; PCP.act(m, 1)
    expect(len([c for c in m.calls if c[0] == 'navigator_to_with_context']) == 1 and m.state(PCP.pc_hash(f'{RP}/{DEEP}/e1.mp3'))[0] == 0, 'the pill of a played episode plays it again from the start (the mark goes)')
    # remote: the body opens the episode page and downloads nothing, the pill downloads; a queued one is paused by a tap, resumed by another
    m.calls = []; PCP.body(m, 3)
    expect(DL.fn(m, 'pn_dl_count') == 1 and not [c for c in m.calls if c[0] in ('navigator_to_with_context', 'toast')] and texts_of(m, 'label_ps_head'),
           'a tap on the body of a download cell opens its episode page and downloads nothing (the user dislikes "tap play to download")')
    PCP.click(m, 'btn_return')
    k3, k4, k5, k6, k7 = (DL.key_of(DEEP, f'e{i}.mp3') for i in range(3, 8))
    m.thread = None
    PCP.act(m, 3)
    armed = ('timer_add', PSYMS['pg_awake_tick'], 1000) in m.calls
    expect(armed and DL.state(m, 'e3.mp3', DEEP)[0] == 1 and DL.fn(m, 'pn_dl_count') == 2, 'a tap on the "48 MB" pill queues the download (and the page arms its downloads timer)')
    PCP.tap(m, 4, 10)
    c = PCP.all_cells(m)
    expect(c[3]['pill'] == 'Waiting', f'its pill reads Waiting (a ring at 0) ({c[3]["pill"]})')
    PCP.act(m, 3)
    expect(DL.state(m, 'e3.mp3', DEEP)[0] == 0, 'a second tap takes it out of the queue')
    m.thread = None
    PCP.act(m, 4)
    expect(DL.state(m, 'e4.mp3', DEEP)[0] == 1, 'the "Download" pill (no size) downloads too')
    m.setword(DL.pn_at(DL.DCANCEL), 0)
    PCP.act(m, 5)
    expect(m.word(DL.pn_at(DL.DCANCEL)) == k5, 'a tap on the downloading pill (the ring, 42%) pauses it: the worker is told to cancel it, the .part stays')
    PCP.act(m, 6)
    expect(DL.state(m, 'e6.mp3', DEEP)[0] == 1, 'the Paused pill resumes it (queued: it goes on from the .part)')
    PCP.act(m, 7)
    expect(DL.state(m, 'e7.mp3', DEEP)[0] == 1, 'the Retry pill tries again')
    # the "..." opens the cell's sheet, a tap near it too
    PCP.dots(m, 3)
    expect(flags(m, 'pg_sh_card') == (1, 1), 'a tap on the "..." opens the sheet')
    PCP.click(m, 'pg_sh_scrim')
    # a drag is no tap; a tap between the pill and the "..." is a body tap
    m.calls = []; PCP.act(m, 0, move=40)
    expect(not [c for c in m.calls if c[0] == 'navigator_to_with_context'], 'a drag on a pill does nothing')
    # touch targets are 44 px: the pill's 30 plus 7 above and below, the dots' 44 square
    h = PCP.hdr(m)
    m.thread = None
    for y, what, want in ((131 - 7, 'the pill\'s top margin', True), (131 - 8, 'the row above it', False), (131 + 30 + 6, 'the pill\'s bottom margin', True), (131 + 30 + 7, 'below it', False)):
        m.calls = []; before = DL.fn(m, 'pn_dl_count')
        PCP.tap(m, 30, h + 3 * CELL + y)
        # cell 3 is a download pill: a hit queues or unqueues it
        now = DL.fn(m, 'pn_dl_count')
        expect((now != before) == want, f'{what}: {"hits" if want else "misses"} the pill (44 px target)')
        opened = bool(texts_of(m, 'label_ps_head') and not texts_of(m, 'label_ps_ctitle'))
        expect(opened == (not want), f'{what}: {"no episode page" if want else "a tap beside the pill is a body tap: the episode page opens"}')
        if opened: PCP.click(m, 'btn_return')


def latest_tests(ctx):
    """The Latest Episode pill: white and playing when the newest episode is on the card; outlined, "Latest Episode - 48 MB", downloading it when it is not; the white pill once it has arrived."""
    expect = ctx.expect
    m = shown()
    m.calls = []
    PCP.latest(m)
    q, idx = m.played
    expect(len([c for c in m.calls if c[0] == 'navigator_to_with_context']) == 1 and idx == 0 and [m.read_cstr(m.word(r + O['REC_PATH'])) for r in q][0] == f'{RP}/{DEEP}/e0.mp3', 'the newest is on the card: a tap on the white pill plays it')
    # the newest is not on the card
    m = shown(files=(1, 2))
    hh = hdr_model(m)
    lat = texts_of(m, 'label_ps_latestw')
    label = 'Latest Episode · 48 MB'
    w = pod_show.latest_width(font(), label, False)
    expect(len(lat) == 1 and lat[0][0] == label and not texts_of(m, 'label_ps_latest'), f'the newest is not on the card: the pill reads "{label}", in the white label style ({[t for t, _ in lat]})')
    bl, _, _, fills = frame(m)
    ends = sorted(b[2][0] for b in bl if b[2][1] == hh['y_latest'] and b[2][3] == 40)
    expect(ends == [(320 - w) // 2, (320 - w) // 2 + w - 20] and all(b[1][0] in (O['PA_PILLR_X'], O['PA_PILLR_X'] + 20) for b in bl if b[2][1] == hh['y_latest'] and b[2][3] == 40),
           f'it is outlined: the ring disc\'s halves, {w} px wide, centred')
    arrow = [b for b in bl if b[2][1] == hh['y_latest'] + 12 and tuple(b[2][2:]) == (16, 16)]
    expect(len(arrow) == 1 and arrow[0][1][:2] == (O['PA_ARROW'] * 16, O['PA_G_Y']), 'with the arrow-down glyph (the download symbol)')
    expect(not [f for f in fills if f[0] == 0xffffffff], 'and no white fill')
    m.thread = None; m.calls = []
    PCP.latest(m)
    expect(DL.state(m, 'e0.mp3', DEEP)[0] == 1 and not [c for c in m.calls if c[0] == 'navigator_to_with_context'], 'a tap downloads it (queued)')
    lat = texts_of(m, 'label_ps_latestw')
    expect(lat and lat[0][0] == 'Latest Episode · Waiting', f'the pill follows the state ({lat})')
    # it arrives: a file on the card, the page reads the episodes again, the pill is the white play pill
    m.put(f'{RP}/{DEEP}/e0.mp3', b'audio')
    for i in range(8): DL.poke_slot(m, i, DEEP, 'x.mp3', 0)
    m.setword(DL.pn_at(DL.KIND), 0); m.setword(DL.pn_at(0), 0); m.setword(DL.pn_at(12), 900)
    DL.tick(m)
    lat = texts_of(m, 'label_ps_latest')
    expect(lat and lat[0][0] == 'Latest Episode' and not texts_of(m, 'label_ps_latestw'), 'when the download is done the pill is the white "Latest Episode" play pill')
    m.calls = []
    PCP.latest(m)
    expect(len([c for c in m.calls if c[0] == 'navigator_to_with_context']) == 1, 'and a tap plays it')
    # a started newest episode: still the white play pill; a show with no episode has no pill
    m = shown(entries=[])
    expect(not texts_of(m, 'label_ps_latest') and not texts_of(m, 'label_ps_latestw'), 'a show with no episode has no pill')
    expect(m.props.get((m.view, 'visible')) == 1 and 'No episodes yet' in PCP.hint(m),
           'the hint is painted under its header, in the content (the header stays: its sheet has Refresh Feed and Unsubscribe)')
    expect(PCP.hdr(m) == pod_show.header(font(), SHOW_TITLE, SHOW_DESC, 'Technology', 'All-In Podcast', False)['h'], 'the header has no pill then')


def nav_tests(ctx):
    """The navbar: "..." | Now Playing on the Show page; the small title once the header's name has scrolled away; the page's fade, not the stock black one."""
    expect = ctx.expect
    m = shown()
    h = hdr_model(m)
    expect(flags(m, 'btn_more') == (1, 1), 'the Show page: the "..." shows')
    expect(m.props[(m.widgets['btn_backtoplayer'], 'style:normal:icon')] == 'ah_nav_play' and m.props[(m.widgets['btn_backtoplayer'], 'style:pressed:icon')] == 'ah_nav_play_down',
           'Now Playing is the capsule\'s right cap, so "..." | Now Playing is one capsule')
    t = m.widgets['label_title']
    expect(m.props.get((t, 'visible')) == 0, 'at rest the title is hidden: the cover is the page\'s top')
    expect(m.props.get((m.widgets['img_nb_fade'], 'visible'), 0) == 0 and h['collapse'] == h['y_name'] + 52 - 12, f'the stock fade stays hidden (the page paints its own); the small title comes at offset {h["collapse"]}')
    fn_, ctx_ = m.bound[(m.sv, O['EVT_SCROLL'])]
    def scroll(off):
        m.props[(m.sv, 'yoffset')] = off; m.setword(m.sv + PCP.SC_YOFF, off)
        m.call(fn_, a0=ctx_, a1=0, count=4000000)
    scroll(h['collapse'] - 1)
    expect(m.props.get((t, 'visible')) == 0, f'one pixel before {h["collapse"]}: still hidden')
    scroll(h['collapse'])
    expect(m.props.get((t, 'visible')) == 1, f'at {h["collapse"]}: the small title shows (the large header is going away)')
    scroll(0)
    expect(m.props.get((t, 'visible')) == 0, 'scrolled back: hidden again')
    # the fade: none at rest; scrolled, the page's colour over the first rows with the eased alpha
    _, _, _, fills = frame(m, 0)
    expect(not [f for f in fills if f[1] == 0 and f[3] == 320 and f[4] == 1 and f[2] < 20], 'no fade at rest')
    _, _, _, fills = frame(m, h['h'] + 40)
    fade = [f for f in fills if f[1] == 0 and f[3] == 320 and f[4] == 1 and f[2] < 20]
    alpha = [mod_icons.nb_fade_alpha(y) for y in range(20)]
    expect([f[2] for f in fade] == [y for y in range(20) if alpha[y]] and [f[0] >> 24 for f in fade] == [a for a in alpha if a], 'scrolled: a 20 row fade whose alpha is nb_fade\'s eased curve')
    tone = tone_word_of(m)
    expect(all(f[0] & 0xffffff == pod_shade(tone, 50 + f[2]) for f in fade), 'in the page\'s own colour (the tone under the gradient at those window rows), not black')
    # select mode: the title is "N Selected", visible at the top; leaving it hides the small title again
    PCP.click(m, 'btn_more'); PCP.click(m, 'pg_sh_select')
    expect(m.props.get((t, 'visible')) == 1 and flags(m, 'btn_more') == (0, 0), 'select mode shows its title and hides the "..."')
    PCP.click(m, 'btn_return')
    expect(m.props.get((t, 'visible')) == 0 and flags(m, 'btn_more') == (1, 1), 'leaving select mode: the "..." is back, the title hidden at the top')
    # the Shows level: the large title is the page's, the navbar's is hidden at rest and there is no "..." without Import
    PCP.click(m, 'btn_return')
    expect(m.props.get((t, 'visible')) == int(m.props.get((m.sv, 'yoffset'), 0) > O['SG_COLLAPSE']) and flags(m, 'btn_more') == (0, 0) and flags(m, 'btn_globe') == (1, 1) and m.props[(m.widgets['btn_backtoplayer'], 'style:normal:icon')] == 'ah_nav_play',
           'the Shows level: the large title (the navbar\'s shows only once it has scrolled away, where the page comes back to), no "..." (nothing to import): [Globe | Now Playing]')
    # the Downloads page has the "..." (its sheet) once it has a row
    m = shown()
    PCP.click(m, 'btn_return')
    DL.poke_slot(m, 0, DEEP, 'e3.mp3', 1, seq=2)
    m.setword(DL.pn_at(12), 5); DL.tick(m)
    PCP.tap_downloads(m)
    expect(PCP.title_text(m) == 'Downloads' and flags(m, 'btn_more') == (1, 1) and 'btn_select' not in m.widgets, 'the Downloads page has the "..." (its sheet: Select, Delete Played Episodes) and no Select button')


def pod_shade(tone, y):
    """patch/common.c pod_shade: the colour 0x..BBGGRR as it shows on window row y under the album page's gradient."""
    a = mod_icons.ah_tint_alpha(y)
    return (tone & 255) * (255 - a) // 255 | ((tone >> 8) & 255) * (255 - a) // 255 << 8 | ((tone >> 16) & 255) * (255 - a) // 255 << 16


def tone_word(rgb):
    import mod_nowplaying as mn
    t = mn.tone(*rgb)
    return 0xff000000 | t[0] | t[1] << 8 | t[2] << 16


def tone_word_of(m):
    """The page's tone as the payload set it on the window (the last bg_color of the window that is not black)."""
    s = [x for x in m.styled if x[0] == m.window and x[1] == 'normal:bg_color' and x[2] != 0xff000000]
    return s[-1][2] & 0xffffff if s else 0


RED = (200, 40, 40)
BAR_BLACK = O['NP_BAR_STOCK']


def bar_model(t):
    """The bar's colour for a tone: the tone under the gradient's first row, darkened until the white glyphs keep 4.5:1."""
    keep = 255 - mod_icons.ah_tint_alpha(0)
    r, g, b = (v * keep // 255 for v in t)
    while 2126 * r * r + 7152 * g * g + 722 * b * b > O['NP_BAR_LUM_MAX']: r, g, b = r * 15 >> 4, g * 15 >> 4, b * 15 >> 4
    return 0xff000000 | r | g << 8 | b << 16


def tint_tests(ctx):
    """The album page's tint on this page: the window's tone, the gradient image, the status bar's hand-over, the tone cache; a show without a cover stays black."""
    expect = ctx.expect
    import mod_nowplaying as mn
    BG, FG = O['EVT_WINDOW_TO_BG'], O['EVT_WINDOW_TO_FG']
    tone = mn.tone(*RED)
    word = tone_word(RED)

    def page():
        m = machine()
        m.with_bar()
        for _ in range(4): m.call(PSYMS['pg_on_load'], a0=0, count=40000000)
        return m
    m = page()
    open_show(m)
    for _ in range(6): m.call(PSYMS['pg_on_load'], a0=0, count=40000000)
    win = [s for s in m.styled if s[0] == m.window and s[1] == 'normal:bg_color']
    expect(win and win[-1][2] == word, f'the Show page\'s window colour is the tone of its cover\'s average colour, the album page\'s function ({[hex(s[2]) for s in win]} want {word:#x})')
    img = m.widgets['img_ah_tint']
    expect(m.props.get((img, 'visible')) == 1 and m.props.get((img, 'sensitive'), 0) == 0, 'the gradient image (ah_tint) shows under the page, and stays insensitive (it is decorative)')
    expect(m.bar_styles() == [bar_model(tone)], f'the status bar takes the page\'s first row: the tone under the overlay\'s first alpha, darkened for the white glyphs ({[hex(x) for x in m.bar_styles()]})')
    expect(contrast(((m.bar_styles()[0]) & 255, (m.bar_styles()[0] >> 8) & 255, (m.bar_styles()[0] >> 16) & 255), (255, 255, 255)) >= 4.5, 'the white clock and glyphs keep 4.5:1 on it')
    # the window's events: background -> black, foreground -> the colour again; one owner
    m.fire_ev = lambda ev: m.call(m.bound[(m.window, ev)][0], a0=m.bound[(m.window, ev)][1], a1=0, count=2000000)
    m.fire_ev(BG)
    expect(m.bar_styles()[-1] == BAR_BLACK, 'the page goes to the background: the bar is black again')
    m.fire_ev(FG)
    expect(m.bar_styles()[-1] == bar_model(tone) and len(m.bar_styles()) == 3, 'back in front: the bar is the page\'s colour again')
    expect(m.call(PSYMS['pg_has_tone'], count=20000) == 1, 'pg_has_tone: the Show page shows a cover\'s tone (the Tinted wash leaves it alone)')
    # another level: black again (the tint and the bar go)
    PCP.click(m, 'btn_return')
    expect(m.call(PSYMS['pg_has_tone'], count=20000) == 0, 'pg_has_tone: the Shows level does not')
    win = [s for s in m.styled if s[0] == m.window and s[1] == 'normal:bg_color']
    expect(win[-1][2] == 0xff000000 and m.props.get((img, 'visible')) == 0 and m.bar_styles()[-1] == BAR_BLACK, 'the Shows level: the window, the gradient and the bar are black')
    # the tone cache: the show again tints at once, with no decode
    m.loads.clear(); m.styled.clear()
    open_show(m)
    win = [s for s in m.styled if s[0] == m.window and s[1] == 'normal:bg_color']
    expect(win and win[-1][2] == word and not [u for u in m.loads if u.startswith('file://')] and m.bar_styles() == [bar_model(tone)], 'the show again: the tone comes from the cache (no decode) and the bar is tinted at once')
    # a cover that is not a picture: black
    m = machine(cover=False); m.with_bar()
    open_show(m)
    for _ in range(6): m.call(PSYMS['pg_on_load'], a0=0, count=40000000)
    expect(not [s for s in m.styled if s[0] == m.window] and not m.bar_styles() and m.props.get((m.widgets['img_ah_tint'], 'visible'), 0) == 0, 'a show without a cover picture stays black: the window, the gradient and the bar are untouched')
    m.fire_ev = lambda ev: m.call(m.bound[(m.window, ev)][0], a0=m.bound[(m.window, ev)][1], a1=0, count=2000000)
    m.fire_ev(BG); m.fire_ev(FG)
    expect(not m.bar_styles(), 'and its window events leave the bar alone')
    # destroy: the bar goes black; a bar that is another page's is left alone
    m = page(); open_show(m)
    for _ in range(6): m.call(PSYMS['pg_on_load'], a0=0, count=40000000)
    m.call(m.bound[(m.window, O['EVT_DESTROY'])][0], a0=m.bound[(m.window, O['EVT_DESTROY'])][1], a1=0, count=4000000)
    expect(m.bar_styles()[-1] == BAR_BLACK, 'the window is destroyed (the hardware Back key): the bar is black')
    m = page(); open_show(m)
    for _ in range(6): m.call(PSYMS['pg_on_load'], a0=0, count=40000000)
    m.call(PSYMS['pod_bar_tint'], a0=0x1234, a1=0xff112233, count=200000)   # another page takes the bar
    n = len(m.bar_styles())
    m.call(m.bound[(m.window, BG)][0], a0=m.bound[(m.window, BG)][1], a1=0, count=2000000)
    expect(len(m.bar_styles()) == n, 'the bar is another page\'s now: this page\'s late background event leaves it alone (one owner)')
    # no cover refresh in the dark: the tint decode waits for the screen
    m = page(); m.screen(False); m.styled.clear(); m.loads.clear()
    open_show(m)
    for _ in range(6): m.call(PSYMS['pg_on_load'], a0=0, count=40000000)
    expect(not [s for s in m.styled if s[0] == m.window and s[2] != 0xff000000] and not [u for u in m.loads if u.startswith('file://')] , 'screen off: the cover is not decoded and the page is not tinted (no visual work in the dark)')
    m.screen(True)
    m.call(PSYMS['pg_tick'], a0=0, count=40000000)
    for _ in range(6): m.call(PSYMS['pg_on_load'], a0=0, count=40000000)
    expect([s for s in m.styled if s[0] == m.window and s[2] == word], 'the screen is back: the tick starts the loader again and the page is tinted')


def sheet_state(m):
    """(the rows that show, in the card's order from the top, the card's height, its glass picture) of the open sheet, from the calls the payload made."""
    card = m.widgets['pg_sh_card']
    rows = [r for r in PCP.SHEET_ROWS if flags(m, f'pg_sh_{r}') == (1, 1)]
    moves = {n: c for n in PCP.SHEET_ROWS for c in m.calls if c[0] == 'widget_move' and c[1] == m.widgets[f'pg_sh_{n}']}
    rows.sort(key=lambda r: moves[r][3])
    return rows, [c for c in m.calls if c[0] == 'widget_resize' and c[1] == card][-1][3], m.props.get((card, 'style:normal:bg_image')), moves


def text_of(m, name):
    t = m.wtext.get(m.widgets[name])
    return t.encode('latin-1').decode('utf-8') if t is not None else None


def show_sheet(m):
    """The show's "..." and what the sheet made of itself (a fresh call list)."""
    PCP.click(m, 'btn_more')
    return sheet_state(m)


def sheet_tests(ctx):
    """The show's sheet: each row shown only where it applies, in the More sheet's layout; and the cell's."""
    expect = ctx.expect
    GLASS = {n: f'pc_sheet{n}' for n in range(1, 7)}
    m = shown()
    rows, h, glass, moves = show_sheet(m)
    expect(rows == ['speed', 'order', 'refresh', 'select', 'markall', 'unsub'] and h == 300 and glass == GLASS[6], f'a subscribed show with files and unplayed episodes: Playback Speed, Episode Order, Refresh Feed, Select Episodes, Mark All as Played, Unsubscribe ({rows}, {h}, {glass})')
    expect(all(moves[r][2] == 0 and moves[r][3] == i * 50 for i, r in enumerate(rows)) and ('widget_move', m.widgets['pg_sh_card'], 0, 150) in m.calls and ('widget_resize', m.widgets['pg_sh_card'], 320, 300) in m.calls,
           'the rows are 50 px each from the top of the card, which is 300 px high at the bottom of the window (y 150 of 450)')
    expect(all(flags(m, f'pg_sh_{r}') == (0, 0) for r in ('dl', 'rm', 'mark', 'unmark')) and flags(m, 'pg_sh_scrim') == (1, 1) and flags(m, 'pg_sh_card') == (1, 1), 'the episode rows stay hidden and insensitive; the scrim and the card show')
    hair = [r for r in rows if m.props.get((m.widgets[f'pg_sh_{r}_hr'], 'visible')) == 1]
    expect(hair == rows[1:], 'a hairline on the top of every row but the first')
    expect(text_of(m, 'pg_sh_speed_vl') == '1×' and text_of(m, 'pg_sh_refresh_vl') == '1h ago', f'the values: the speed ({text_of(m, "pg_sh_speed_vl")}) and the age alone, "1h ago" ({text_of(m, "pg_sh_refresh_vl")})')
    tx = {r: [c for c in m.calls if c[0] == 'widget_resize' and c[1] == m.widgets[f'pg_sh_{r}_tx']] for r in ('speed', 'refresh')}
    vw = font().width('1h ago', 18) + 12
    expect(tx['refresh'][-1][2:] == (304 - 56 - vw, 50), f'the label makes room for the value ({tx["refresh"][-1]})')
    # the value for every speed, the default first: the sheet opens on the show's own speed
    for mode, want in enumerate(('1×', '1.25×', '1.5×', '2×')):
        m2 = shown()
        if mode: m2.call(PSYMS['pc_speed_set'], a0=PCP.pc_hash(DEEP), a1=mode, count=2000000)
        show_sheet(m2)
        got = text_of(m2, 'pg_sh_speed_vl')
        vw = font().width(want, 18)
        expect(got == want and ('widget_resize', m2.widgets['pg_sh_speed_vl'], vw, 50) in m2.calls, f'Playback Speed shows {want!r} for speed {mode}{" (the default)" if not mode else ""} in a label as wide as the text ({got!r})')
    # the speed row cycles; the sheet stays
    seq = []
    for _ in range(5):
        PCP.click(m, 'pg_sh_speed')
        seq.append((text_of(m, 'pg_sh_speed_vl'), m.call(PSYMS['pc_speed_get'], a0=PCP.pc_hash(DEEP), count=2000000)))
    expect(seq == [('1.25×', 1), ('1.5×', 2), ('2×', 3), ('1×', 0), ('1.25×', 1)] and flags(m, 'pg_sh_card') == (1, 1), f'a tap on Playback Speed cycles 1×, 1.25×, 1.5×, 2× (the four speeds the player has) and saves it; the sheet stays open ({seq})')
    expect(m.fs[PCP.SPEED][:4] == b'PCS1' and m.word(PCP.PLAYSPEED_MODE) == 1 and m.speeds[-1] == 1, 'the speed file, the stock mode and the player follow')
    PCP.click(m, 'pg_sh_scrim')
    expect(flags(m, 'pg_sh_card') == (0, 0) and flags(m, 'pg_sh_scrim') == (0, 0), 'a tap on the dimmed page closes the sheet')
    PCP.click(m, 'btn_more')
    PCP.click(m, 'btn_return')
    expect(flags(m, 'pg_sh_card') == (0, 0) and PCP.title_text(m).startswith('All-In'), 'Back closes the open sheet first (the page stays)')
    # a show without a feed (bravo): no Refresh Feed, no Unsubscribe
    m = machine(); open_show(m, 'bravo')
    rows, h, glass, _ = show_sheet(m)
    expect(rows == ['speed', 'order', 'select', 'markall'] and h == 200 and glass == GLASS[4], f'a show of files (no feed): Playback Speed, Episode Order, Select Episodes, Mark All as Played; a 200 px sheet ({rows}, {h}, {glass})')
    # all played: no Mark All as Played
    for i in (1, 2, 3): m.call(PSYMS['pc_mark'], a0=PCP.pc_hash(f'{RP}/bravo/b{i}.mp3'), a1=1, count=2000000)
    PCP.click(m, 'pg_sh_scrim')
    rows, h, glass, _ = show_sheet(m)
    expect(rows == ['speed', 'order', 'select'] and h == 150 and glass == GLASS[3], f'every episode played: Mark All as Played is gone ({rows})')
    # a subscribed show with nothing on the card: no Select Episodes
    m = machine(entries=[entry(i) for i in range(3)], files=()); open_show(m)
    rows, h, glass, _ = show_sheet(m)
    expect(rows == ['speed', 'order', 'refresh', 'markall', 'unsub'] and h == 250 and glass == GLASS[5], f'nothing on the card: no Select Episodes ({rows}, {h}, {glass})')
    # a show with no episode and no mark: its own sheet (speed, refresh, unsubscribe)
    m = machine(entries=[]); open_show(m)
    rows, h, glass, _ = show_sheet(m)
    expect(rows == ['speed', 'order', 'refresh', 'unsub'] and h == 200, f'a subscription with no episode yet: speed, order, refresh, unsubscribe ({rows})')
    # never refreshed
    m = machine(checked=0, files=()); open_show(m); show_sheet(m)
    expect(text_of(m, 'pg_sh_refresh_vl') == 'Never refreshed', 'never refreshed: the value says so')
    # no sheet in select mode, none over the refresh dialog
    m = shown()
    PCP.click(m, 'btn_more'); PCP.click(m, 'pg_sh_select')
    m.calls = []
    PCP.dots(m, 0)
    expect(flags(m, 'pg_sh_card') == (0, 0), 'select mode has no sheet (the "..." of a cell is not there)')
    PCP.click(m, 'btn_return')
    # the cell's sheet
    m = shown()
    PCP.dots(m, 3)
    rows, h, glass, _ = sheet_state(m)
    expect(rows == ['dl', 'mark'] and h == 100 and glass == GLASS[2] and text_of(m, 'pg_sh_dl_tx') == 'Download · 48 MB', f'an episode not on the card: "Download · 48 MB" and Mark as Played ({rows}, {text_of(m, "pg_sh_dl_tx")})')
    PCP.click(m, 'pg_sh_scrim'); PCP.dots(m, 4)
    expect(sheet_state(m)[0] == ['dl', 'mark'] and text_of(m, 'pg_sh_dl_tx') == 'Download', 'without a size: just Download')
    PCP.click(m, 'pg_sh_scrim'); PCP.dots(m, 0)
    expect(sheet_state(m)[0] == ['rm', 'save', 'mark'] and text_of(m, 'pg_sh_save_tx') == 'Save Episode', 'on the card: Remove Download, Save Episode and Mark as Played')
    PCP.click(m, 'pg_sh_scrim'); PCP.dots(m, 1)
    expect(sheet_state(m)[0] == ['rm', 'save', 'unmark'], 'played: Remove Download, Save Episode and Mark as Unplayed')
    PCP.click(m, 'pg_sh_scrim'); m.calls = []
    PCP.dots(m, 0); PCP.click(m, 'pg_sh_save')
    path = f'{RP}/{DEEP}/e0.mp3'
    expect(flags(m, 'pg_sh_card') == (0, 0) and [r[:2] for r in m.fav_rows] == [('e0.mp3', path)] and [c[1:] for c in m.calls if c[0] == 'addMyFav'] == [('e0.mp3', path)] and [c[1] for c in m.calls if c[0] == 'toast'] == ['Saved'],
           f'Save Episode: stock\'s addMyFav on the record the episode plays as (its name and path), the sheet closes, a toast ({m.fav_rows})')
    PCP.dots(m, 0)
    expect(sheet_state(m)[0] == ['rm', 'save', 'mark'] and text_of(m, 'pg_sh_save_tx') == 'Unsave Episode', 'a saved episode: the row says Unsave Episode')
    PCP.click(m, 'pg_sh_save'); m.calls = []
    expect(m.fav_rows == [] and not [c for c in m.calls if c[0] == 'addMyFav'], 'Unsave Episode: stock\'s deleteMusicFromFav takes it out')
    PCP.dots(m, 0)
    expect(text_of(m, 'pg_sh_save_tx') == 'Save Episode', 'and the row offers Save again')
    PCP.click(m, 'pg_sh_scrim'); PCP.dots(m, 6)
    expect(sheet_state(m)[0] == ['rm', 'mark'], 'a paused .part: Remove Download (it takes the .part away)')
    PCP.click(m, 'pg_sh_scrim')
    PCP.dots(m, 3)   # a hidden-mark episode without a file name has no mark rows
    PCP.click(m, 'pg_sh_dl'); expect(DL.state(m, 'e3.mp3', DEEP)[0] == 1 and flags(m, 'pg_sh_card') == (0, 0), 'Download: queues it and closes the sheet')
    PCP.dots(m, 0); PCP.click(m, 'pg_sh_mark')
    expect(m.state(PCP.pc_hash(f'{RP}/{DEEP}/e0.mp3'))[0] == 2 and PCP.all_cells(m)[0]['played'], 'Mark as Played: the episode is played (a grey title and the check)')
    PCP.dots(m, 0); PCP.click(m, 'pg_sh_unmark')
    expect(m.state(PCP.pc_hash(f'{RP}/{DEEP}/e0.mp3'))[0] == 0 and not PCP.all_cells(m)[0]['played'], 'Mark as Unplayed: new again')
    m.calls = []
    PCP.dots(m, 0); PCP.click(m, 'pg_sh_rm')
    expect(f'{RP}/{DEEP}/e0.mp3' not in m.fs,
           'Remove Download: the file is gone')
    c = PCP.all_cells(m)
    expect(b'f=e0.mp3' in m.fs[f'{RP}/{DEEP}/.episodes'] and c[0]['pill'] == '48 MB', f'the .episodes line stays, so the cell is a download cell again ({c[0]["pill"]})')
    # the playing episode is never removed
    m.track(f'{RP}/{DEEP}/e1.mp3')
    m.calls = []
    PCP.dots(m, 1); PCP.click(m, 'pg_sh_rm')
    expect(f'{RP}/{DEEP}/e1.mp3' in m.fs and [c_[1] for c_ in m.calls if c_[0] == 'toast'] == ['The playing episode was kept'], 'the playing episode is kept, with the toast')
    # Remove Download of a paused download takes the .part away
    PCP.dots(m, 6); PCP.click(m, 'pg_sh_rm')
    expect(f'{RP}/{DEEP}/e6.mp3.part' not in m.fs, 'a paused one: its .part is removed')


def order_tests(ctx):
    """Episode Order on the show's sheet: the grey value, a tap flips it and sorts the list again (the sheet stays), a failed save, the queue and the Latest Episode pill under both values."""
    expect = ctx.expect
    paths = lambda m: [m.read_cstr(m.word(r + O['REC_PATH'])).rsplit('/', 1)[1] for r in m.played[0]]
    m = shown()
    rows, *_ = show_sheet(m)
    expect(rows[:2] == ['speed', 'order'] and text_of(m, 'pg_sh_order_vl') == 'Newest First' and text_of(m, 'pg_sh_order_tx') == 'Episode Order', f'the row follows Playback Speed and says Newest First by default ({rows})')
    expect(m.props.get((m.widgets['pg_sh_order_vl'], 'visible')) in (None, 1) and ('widget_resize', m.widgets['pg_sh_order_vl'], font().width('Newest First', 18), 50) in m.calls, 'its value label is as wide as the text')
    first = lambda mm: [c['date'] for _, c in sorted(PCP.all_cells(mm).items())]
    before = first(m)
    PCP.click(m, 'pg_sh_order')
    expect(text_of(m, 'pg_sh_order_vl') == 'Oldest First' and flags(m, 'pg_sh_card') == (1, 1) and m.fs[PCP.ORDER][:4] == b'PCO1' and m.call(PSYMS['pc_order_get'], a0=PCP.pc_hash(DEEP), count=2000000) == 1,
           'a tap says Oldest First, saves it (PCO1) and the sheet stays open')
    after = first(m)
    expect(after == before[::-1], f'the list is sorted again at once: the cells run the other way ({before} -> {after})')
    PCP.click(m, 'pg_sh_order')
    expect(text_of(m, 'pg_sh_order_vl') == 'Newest First' and first(m) == before and m.call(PSYMS['pc_order_get'], a0=PCP.pc_hash(DEEP), count=2000000) == 0, 'a second tap goes back')
    # a failed save: the toast, nothing changes
    m.fail.add(('write', PCP.ORDER + '.tmp')); m.calls = []
    PCP.click(m, 'pg_sh_order')
    toast = [c[1] for c in m.calls if c[0] == 'toast']   # (before the list is painted again: a paint clears the calls)
    expect(text_of(m, 'pg_sh_order_vl') == 'Newest First' and first(m) == before and toast == ['Storage unavailable'], 'a failed save: "Storage unavailable", the value and the list stay')
    m.fail.clear()
    # no memory after the save: the rows are turned round in place, so the saved order, the list, the queue and Latest Episode still agree
    m = shown()
    before = first(m)
    PCP.click(m, 'btn_more')
    m.calloc_fail = True
    PCP.click(m, 'pg_sh_order')
    m.calloc_fail = False
    expect(text_of(m, 'pg_sh_order_vl') == 'Oldest First' and m.call(PSYMS['pc_order_get'], a0=PCP.pc_hash(DEEP), count=2000000) == 1 and first(m) == before[::-1],
           f'calloc failing during the flip: saved Oldest First and the cells run the other way all the same ({before} -> {first(m)})')
    PCP.click(m, 'pg_sh_scrim')
    m.calls = []; PCP.latest(m)
    expect(paths(m) == ['e2.mp3', 'e1.mp3', 'e0.mp3'] and m.played[1] == 2, f'and the Latest Episode pill plays the newest, e0, from the oldest-first queue ({paths(m)}, {m.played[1]})')
    # the queue: from the tapped episode down the displayed rows (local ones: e0 e1 e2 newest first)
    m = shown()
    m.call(PSYMS['pc_order_set'], a0=PCP.pc_hash(DEEP), a1=0, count=30000000)
    n = len(PCP.all_cells(m))
    m.calls = []; PCP.act(m, 1)
    expect(paths(m) == ['e0.mp3', 'e1.mp3', 'e2.mp3'] and m.played[1] == 1, f'newest first: a tap on e1 queues e0 e1 e2 and starts at the second ({paths(m)}, {m.played[1]})')
    PCP.click(m, 'btn_more'); PCP.click(m, 'pg_sh_order'); PCP.click(m, 'pg_sh_scrim')
    expect(n == len(PCP.all_cells(m)) == 8, 'all eight episodes are listed either way')
    m.calls = []; PCP.act(m, 8 - 3)   # e2, the oldest on the card: cells run e7 .. e0
    expect(paths(m) == ['e2.mp3', 'e1.mp3', 'e0.mp3'] and m.played[1] == 0, f'oldest first: a tap on e2 plays it and goes on to the newer ones ({paths(m)}, {m.played[1]})')
    m.calls = []; PCP.act(m, 8 - 2)
    expect(paths(m) == ['e2.mp3', 'e1.mp3', 'e0.mp3'] and m.played[1] == 1, f'oldest first: a tap on e1 starts at the second of the queue ({paths(m)}, {m.played[1]})')
    m.calls = []; PCP.latest(m)
    expect(paths(m) == ['e2.mp3', 'e1.mp3', 'e0.mp3'] and m.played[1] == 2 and texts_of(m, 'label_ps_latest'), f'the Latest Episode pill still plays the newest, e0, under Oldest First ({paths(m)}, {m.played[1]})')
    # rows above the tapped one that are not on the card do not move its place in the queue (e0, e1 remote above e2)
    m = shown(files=(1, 2))
    m.calls = []; PCP.act(m, 2)
    expect(paths(m) == ['e1.mp3', 'e2.mp3'] and m.played[1] == 1, f'a tap on e2 under a remote e0: the queue is e1 e2 and e2 is the second ({paths(m)}, {m.played[1]})')
    m = shown(files=(2,))
    m.calls = []; PCP.act(m, 2)
    expect(paths(m) == ['e2.mp3'] and m.played[1] == 0, f'two remote episodes above e2: it is the only one, place 0 ({paths(m)}, {m.played[1]})')
    # the pill reads the newest episode too: e0 is not on the card
    m = shown(files=(1, 2))
    m.call(PSYMS['pc_order_set'], a0=PCP.pc_hash(DEEP), a1=1, count=30000000)
    PCP.click(m, 'btn_return'); open_show(m)
    expect([t for t, _ in texts_of(m, 'label_ps_latestw')] == ['Latest Episode · 48 MB'], 'oldest first, the newest not on the card: the pill still reads its size')
    m.thread = None; m.calls = []
    PCP.latest(m)
    expect(DL.state(m, 'e0.mp3', DEEP)[0] == 1 and not [c for c in m.calls if c[0] == 'navigator_to_with_context'], 'and a tap downloads e0, the newest')


def mark_all_tests(ctx):
    expect = ctx.expect
    m = shown()
    PCP.click(m, 'btn_more'); PCP.click(m, 'pg_sh_markall')
    ok = [m.state(PCP.pc_hash(f'{RP}/{DEEP}/e{i}.mp3'))[0] for i in range(8)]
    expect(ok == [2] * 8 and flags(m, 'pg_sh_card') == (0, 0), f'Mark All as Played: every episode of the show, on the card or not, is played; the sheet closes ({ok})')
    c = PCP.all_cells(m)
    expect(all(c[i]['played'] for i in range(8)), 'every title is grey')
    PCP.click(m, 'btn_more')
    expect(sheet_state(m)[0] == ['speed', 'order', 'refresh', 'select', 'unsub'], 'and the row is gone from the sheet')
    expect(m.ring() is not None, 'the ring is written')


def refresh_tests(ctx):
    """Refresh Feed: a single-feed refresh through the existing dialog ("1 of 1"), pausing downloads first like Refresh All; the page is the show again afterwards."""
    expect = ctx.expect
    m = shown()
    # no download runs now (a running one is poked in `shown`: stop it)
    for i in range(8): DL.poke_slot(m, i, DEEP, 'x.mp3', 0)
    m.setword(DL.pn_at(DL.KIND), 0); m.setword(DL.pn_at(0), 0); m.setword(DL.pn_at(DL.DKEY), 0)
    m.curl_site = lambda url, o: {'body': PCN.feed_bytes('headlines-3items.xml')} if 'f.example' in url else DL.server(DL.DATA)(url, o)
    m.thread = None; m.calls = []
    PCP.click(m, 'btn_more'); PCP.click(m, 'pg_sh_refresh')
    expect(m.thread and m.thread[0] == PSYMS['pn_main'] and flags(m, 'pg_sh_card') == (0, 0), 'Refresh Feed closes the sheet and starts the worker')
    expect(flags(m, 'pod_pd_scrim') == (1, 1) and flags(m, 'pod_pd_card') == (1, 1) and text_of(m, 'pod_pd_count') == '1 of 1', f'the progress dialog opens, "1 of 1" ({text_of(m, "pod_pd_count")})')
    expect(DL.fn(m, 'pn_busy') == 1, 'one refresh is running')
    th = m.thread
    m.call(th[0], a0=th[1], count=1 << 40)
    checked = [s for s in m.shows()[0] if s['feed'] == FEED]
    expect(len(checked) == 1 and checked[0]['checked'] >= NOW, 'only this show was refreshed (its checked= moved)')
    expect(b'f=e0.mp3' in m.fs[f'{RP}/{DEEP}/.episodes'], 'the files on the card keep their lines')
    m.call(PSYMS['pg_dlg_tick'], a0=0, count=40000000)
    expect(flags(m, 'pod_pd_scrim') == (0, 0) and [c[1] for c in m.calls if c[0] == 'toast'] == ['1 updated'], f'the dialog closes by itself: "1 updated" ({[c[1] for c in m.calls if c[0] == "toast"]})')
    expect(PCP.title_text(m).startswith('All-In') and m.props.get((m.sv, 'virtual_h')) > 0 and flags(m, 'btn_more') == (1, 1), 'the page is the show again, read again from its files')
    c = PCP.all_cells(m)
    titles = [' '.join(c[i]['title']) for i in sorted(c)]
    expect(len(titles) == 7 and {'Episode 1', 'Episode 2', 'Episode 6'} <= set(titles) and sum(t.endswith('…') or t.startswith(('Trump', 'At Least', 'Fl')) for t in titles) == 4,
           f'the feed\'s three episodes join the ones the card keeps (the files, and the paused .part: its line is kept) ({titles})')
    # a download runs: Refresh Feed pauses it first, as Refresh All does; the refresh starts when its thread has stopped
    m = shown()   # (the status record says a download runs)
    m.curl_site = lambda url, o: {'body': PCN.feed_bytes('headlines-3items.xml')} if 'f.example' in url else DL.server(DL.DATA)(url, o)
    m.thread = None; m.calls = []
    PCP.click(m, 'btn_more'); PCP.click(m, 'pg_sh_refresh')
    expect(m.word(DL.pn_at(DL.DPAUSE)) == 1 and m.thread is None and m.props.get((m.widgets['pod_pd_scrim'], 'visible'), 0) == 0 and DL.fn(m, 'pn_busy') == 0,
           'a download runs: it is asked to pause, no refresh thread yet, no dialog yet')
    m.setword(DL.pn_at(DL.KIND), 0); m.setword(DL.pn_at(0), 0); m.setword(DL.pn_at(DL.DPAUSE), 0); m.setword(DL.pn_at(DL.DKEY), 0)
    DL.poke_slot(m, 0, DEEP, 'e5.mp3', 1, seq=5)   # (it stopped and kept its place in the queue)
    m.thread = None
    DL.tick(m)
    expect(m.thread and m.thread[0] == PSYMS['pn_main'] and flags(m, 'pod_pd_scrim') == (1, 1) and text_of(m, 'pod_pd_count') == '1 of 1',
           'the next tick starts the single-feed refresh once the download has stopped, and opens the dialog ("1 of 1")')
    m.call(m.thread[0], a0=m.thread[1], count=1 << 40)
    m.thread = None
    m.call(PSYMS['pg_dlg_tick'], a0=0, count=40000000)
    expect(m.thread and m.thread[0] == PSYMS['pn_dmain'], 'when the dialog closes the paused downloads go on')
    # Cancel stops the refresh at once and the show stays as it was
    m = shown()
    for i in range(8): DL.poke_slot(m, i, DEEP, 'x.mp3', 0)
    m.setword(DL.pn_at(DL.KIND), 0); m.setword(DL.pn_at(0), 0); m.setword(DL.pn_at(DL.DKEY), 0)
    m.thread = None
    PCP.click(m, 'btn_more'); PCP.click(m, 'pg_sh_refresh')
    PCP.click(m, 'pod_pd_cancel')
    expect(DL.fn(m, 'pn_cancelling') == 1 and flags(m, 'pod_pd_scrim') == (1, 1), 'Cancel in the dialog: "Cancelling…", the worker is told to stop')


def unsub_tests(ctx):
    """Unsubscribe: the feed goes from .show, the .episodes stay, the .part files and queued downloads go; with no file left the show's own files and its folder go and the page leaves."""
    expect = ctx.expect
    # files stay: the page stays, no longer a subscription
    m = shown()
    m.confirm_yes = False
    PCP.click(m, 'btn_more'); m.calls = []
    PCP.click(m, 'pg_sh_unsub')
    expect([c[1] for c in m.calls if c[0] == 'confirm'] == ['Unsubscribe from this show?'] and b'feed=' in m.fs[f'{RP}/{DEEP}/.show'] and flags(m, 'pg_sh_card') == (0, 0), 'Unsubscribe asks first (the sheet closes); No changes nothing')
    m.confirm_yes = True
    PCP.click(m, 'btn_more'); m.calls = []
    PCP.click(m, 'pg_sh_unsub')
    show = m.fs[f'{RP}/{DEEP}/.show'].decode()
    expect('feed=http' not in show and '\nfeed=\n' in show and f'title={SHOW_TITLE}' in show and 'author=All-In Podcast' in show and 'category=Technology' in show and 'desc=' in show and 'checked=' in show,
           f'.show loses feed= and keeps everything else ({show!r})')
    expect(f'{RP}/{DEEP}/.episodes' in m.fs and b'f=e0.mp3' in m.fs[f'{RP}/{DEEP}/.episodes'], 'the .episodes stay: the titles and dates of the files on the card')
    expect(f'{RP}/{DEEP}/e6.mp3.part' not in m.fs, 'the .part files go')
    expect(all(f'{RP}/{DEEP}/e{i}.mp3' in m.fs for i in range(3)), 'the episode files stay')
    expect(m.word(DL.pn_at(DL.DCANCEL)) == DL.key_of(DEEP, 'e5.mp3') and DL.fn(m, 'pn_dl_count') <= 1, 'the running download is told to stop (the worker drops it) and nothing else of the show is queued')
    expect(PCP.title_text(m).startswith('All-In') and flags(m, 'btn_more') == (1, 1), 'the page is still the show (it has files)')
    PCP.click(m, 'btn_more')
    expect(sheet_state(m)[0] == ['speed', 'order', 'select', 'markall'], 'its sheet has no Refresh Feed and no Unsubscribe now')
    PCP.click(m, 'pg_sh_scrim')
    shows, _ = m.shows()
    expect([s['feed'] for s in shows if s['dir'] == DEEP] == [''], 'the show is no subscription: pc_scan_shows reads no feed address')
    PCP.click(m, 'btn_return')
    expect(PCP.title_text(m) == 'Podcasts', 'Back goes to the Shows level')
    _, _, off = PCP.show_at(m, 'All-In')
    expect([t[:5] for t, _ in PCP.drawn(m, off, style='label_ps_gsub')][:1] == ['Local'] and not [t for t, _ in PCP.drawn(m, 0, style='label_ps_line')],
           'the show is still on the Shows level, now a local one (its caption says Local) and with no refresh line: no show has a feed')
    # no file left: its own files and the folder go, the page leaves for the level below
    m = machine(files=()); open_show(m)
    m.put(f'{RP}/{DEEP}/e1.mp3.part', b'x')
    m.confirm_yes = True
    PCP.click(m, 'btn_more'); m.calls = []
    PCP.click(m, 'pg_sh_unsub')
    gone = [p for p in m.fs if p.startswith(f'{RP}/{DEEP}/')]
    expect(not gone and f'{RP}/{DEEP}' not in m.dirs and ('rmdir', f'{RP}/{DEEP}') in m.calls, f'nothing is left: .show, .episodes, cover.jpg and the .part files are deleted and the empty folder is removed ({gone})')
    expect(PCP.title_text(m) == 'Podcasts' and not [t for t, _ in PCP.drawn(m, 0, style='label_ps_gtitle') if t.startswith('All-In')], 'the page goes back to the Shows level, which no longer lists the show')
    m2 = machine(files=(0,)); open_show(m2)
    m2.track(f'{RP}/{DEEP}/e0.mp3'); m2.confirm_yes = True
    PCP.click(m2, 'btn_more'); PCP.click(m2, 'pg_sh_unsub')
    expect(f'{RP}/{DEEP}/e0.mp3' in m2.fs and f'{RP}/{DEEP}/.episodes' in m2.fs and PCP.title_text(m2).startswith('All-In'), 'the playing episode is never deleted: its file stays, so the folder and its .episodes do too')
    m4 = machine(files=()); open_show(m4)
    m4.put(f'{RP}/{DEEP}/notes.txt', b'mine'); m4.confirm_yes = True
    PCP.click(m4, 'btn_more'); PCP.click(m4, 'pg_sh_unsub')
    expect(f'{RP}/{DEEP}/notes.txt' in m4.fs and f'{RP}/{DEEP}/.show' not in m4.fs and f'{RP}/{DEEP}' in m4.dirs, 'a file of the user\'s in the folder stays; the folder is not removed (rmdir refuses)')
    # a .show that cannot be written: said, nothing else done
    m5 = shown(); m5.confirm_yes = True; m5.fail.add(('open', f'{RP}/{DEEP}/.show.tmp'))
    PCP.click(m5, 'btn_more'); m5.calls = []
    PCP.click(m5, 'pg_sh_unsub')
    expect([c[1] for c in m5.calls if c[0] == 'toast'] == ['Storage unavailable'] and b'feed=' in m5.fs[f'{RP}/{DEEP}/.show'] and f'{RP}/{DEEP}/e6.mp3.part' in m5.fs,
           'a .show that cannot be written: said, and nothing else is touched (the feed, the .part files stay)')


def wrap_tests(ctx):
    """pw_wrap against the Python port on a corpus, and the kinsoku rules: no line starts with closing punctuation, none ends with an opening bracket."""
    expect = ctx.expect
    import pod_wrap
    m = SM()
    adv_of = lambda s, px: [font().width(c, px) for c in s]
    corpus = [
        ('Plain words that wrap around two lines of a header description, then run on and on past the second line.', 16, 288, 2),
        ("Trump's Tariffs, Nvidia's $5T Moment, AI Bubble Debate, Fed Rate Cut and the Government Shutdown Fallout", 20, 288, 2),
        ('第128期｜为什么年轻人不再相信“努力就会有回报”？聊聊内卷、躺平与新的生活方式，以及在不确定的时代里如何找到属于自己的节奏。', 20, 288, 2),
        ('这一期我们邀请了三位八零后、九零后的朋友，聊聊他们眼中的努力、回报与生活的意义，以及在不确定的时代里如何找到属于自己的节奏。', 16, 288, 2),
        ('Supercalifragilisticexpialidocious' * 3, 16, 288, 2),
        ('', 16, 288, 2), ('   ', 16, 288, 2), ('One', 22, 286, 2), ('A B C D E F G H I J K L M N O P Q R S T U V W X Y Z ' * 3, 22, 286, 2),
        ('日本語の説明文です。「かぎ括弧」（丸括弧）、読点、句点。これは長い文章で、二行に収まりません。もっと長くします、長く長く長く長く長く長く長く長く。', 16, 288, 2),
        ('Café ünïcödé wörds with àccents and “curly quotes”, (parentheses) and dashes — like this one — in the middle of a line, repeated.' * 2, 16, 288, 2),
        ('Short title', 22, 286, 1), ('A much longer single line title that must be cut with an ellipsis at the end of its only line', 15, 288, 1),
        ('ภาษาไทยไม่มีช่องว่างระหว่างคำและต้องตัดบรรทัดที่ตัวอักษรใดก็ได้ในกรณีที่ไม่มีที่ว่างพอสำหรับข้อความนี้', 16, 288, 2)]
    # an exhaustive sweep of widths over a CJK sentence with punctuation: every room from 40 to 300 px
    cjk = '你好，世界！“引号”（括号）《书名》「直角」、顿号；分号：冒号。省略号…破折号——结束？'
    corpus += [(cjk, 16, w, 3) for w in range(40, 300, 7)]
    for s, px, room, maxl in corpus:
        n = len(s)
        adv = adv_of(s, px)
        ellw = font().width('…', px)
        want = pod_wrap.wrap(s, adv, room, maxl, ellw)
        buf = m.alloc(4 * (n + 2)); m.u.mem_write(buf, struct.pack(f'<{n + 1}I', *map(ord, s), 0))
        ab = m.alloc(2 * (n + 2)); m.u.mem_write(ab, struct.pack(f'<{n}H', *adv) if n else b'')
        out = m.alloc(16)
        m.u.mem_write(out, bytes(16))
        m.setword(STACK + 16, maxl); m.setword(STACK + 20, ellw); m.setword(STACK + 24, out)
        got_n = m.call(PSYMS['pw_wrap'], a0=buf, a1=n, a2=ab, a3=room, count=4000000)
        spans = [struct.unpack_from('<hh', bytes(m.u.mem_read(out + 4 * i, 4))) for i in range(got_n)]
        chars = struct.unpack(f'<{n + 1}I', bytes(m.u.mem_read(buf, 4 * (n + 1))))
        got = [''.join(map(chr, chars[a:a + b])) for a, b in spans]
        if got != want:
            expect(False, f'pw_wrap = the Python port on {s[:30]!r} at {room} px, {maxl} lines: {got} != {want}')
            break
    else:
        expect(True, f'pw_wrap equals the Python port on {len(corpus)} texts and widths (Latin, CJK, kana, Thai, accents, quotes, one long word, empty)')
    # the rules, over the sweep
    bad_start, bad_end, over, count = [], [], [], 0
    for room in range(40, 300, 3):
        adv = adv_of(cjk, 16)
        for line in pod_wrap.wrap(cjk, adv, room, 6, adv_of('…', 16)[0]):
            count += 1
            if line[0] in pod_wrap.NO_START: bad_start.append((room, line))
            if line[-1] in pod_wrap.NO_END: bad_end.append((room, line))
            if sum(adv_of(line, 16)) > room + 20: over.append((room, line))
    expect(count > 100 and not bad_start and not bad_end, f'kinsoku over {count} lines: no line starts with closing punctuation ({bad_start[:2]}) or ends with an opening bracket ({bad_end[:2]})')
    expect(not over, f'and no line is wider than its room ({over[:2]})')
    # the ellipsis: the last line, only when text is left
    adv = adv_of('abc def ghi', 16)
    expect(pod_wrap.wrap('abc def ghi', adv, 1000, 2, 16) == ['abc def ghi'] and pod_wrap.wrap('abc def ghi', adv, 40, 1, 16)[-1].endswith('…'), 'text that fits has no ellipsis; one line of room cuts with one')


def width_tests(ctx):
    """The page's strings in the 13 languages, measured in the real font: the pills, the Latest Episode pill, the sheets' labels and values (a label and its value share a 248 px row), the header's Episodes."""
    expect = ctx.expect
    fnt = pod_show.Font(pod_show.font_path(WORK))
    worst = {}
    for loc in pod_i18n.LOCALES:
        t = pod_i18n.table_for(loc)
        tr = lambda key, n=None, t=t: (pod_i18n.TEXT[key][t].replace('%d', str(n)) if n is not None else pod_i18n.TEXT[key][t])
        pills = [tr('%dm', 999), tr('%dm left', 999), tr('%d MB', 999), tr('Download'), '100%', tr('Waiting'), tr('Paused'), tr('Retry'), tr('Play')]
        latest = [tr('Latest Episode'), f'{tr("Latest Episode")} · {tr("%d MB", 999)}', f'{tr("Latest Episode")} · {tr("Download")}', f'{tr("Latest Episode")} · {tr("Waiting")}',
                  f'{tr("Latest Episode")} · {tr("Paused")}', f'{tr("Latest Episode")} · {tr("Retry")}', f'{tr("Latest Episode")} · 100%']
        w18 = lambda s: fnt.width(s, 18)
        lab = {k: w18(tr(k)) for k in ('Playback Speed', 'Refresh Feed', 'Select Episodes', 'Mark All as Played', 'Unsubscribe', 'Remove Download', 'Mark as Played', 'Mark as Unplayed', 'Episode Order')}
        ages = [tr('Just now'), tr('%dm ago', 59), tr('%dh ago', 23), tr('%dd ago', 6)] + [tr(f'{mo} %d', 30) for mo in ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')]
        age = max(w18(a) for a in ages)
        worst[loc] = dict(pill=max(pod_show.pill_width(fnt, p) for p in pills), latest=max(pod_show.latest_width(fnt, p, True) for p in latest), labels=max(lab.values()),
                          speed=lab['Playback Speed'] + 12 + max(w18(s) for s in ('1×', '1.25×', '1.5×', '2×')), refresh=lab['Refresh Feed'] + 12 + age,
                          order=lab['Episode Order'] + 12 + max(w18(tr(k)) for k in ('Newest First', 'Oldest First')), never=lab['Refresh Feed'] + 12 + w18(tr('Never refreshed')), dl=w18(f'{tr("Download")} · {tr("%d MB", 999)}'), head=fnt.width(tr('Episodes'), 22),
                          confirm=w18(tr('Unsubscribe from this show?')))
    print('  widest per language (px):', {k: max(v[k] for v in worst.values()) for k in worst['en_US']}, 'in', {k: max(worst, key=lambda loc: worst[loc][k]) for k in worst['en_US']})
    row = O['PS_SHEET_VALUE_R'] - O['PS_SHEET_TEXT_X']
    bad = lambda k, room: [(loc, w[k]) for loc, w in worst.items() if w[k] > room]
    expect(not bad('pill', 246), f'every state pill ends before the "..." column (246 px) in every language ({bad("pill", 246)})')
    expect(not bad('latest', O['PS_LATEST_MAX']), f'the Latest Episode pill fits {O["PS_LATEST_MAX"]} px in every language (a long state word is cut with an ellipsis: {bad("latest", O["PS_LATEST_MAX"])})')
    expect(not bad('labels', row), f'every sheet label fits its {row} px row ({bad("labels", row)})')
    expect(not bad('speed', row), f'Playback Speed and its value share the row ({bad("speed", row)})')
    expect(not bad('order', row), f'Episode Order and its widest value share the row ({bad("order", row)})')
    expect(not bad('refresh', row), f'Refresh Feed and its widest age ("Just now", "59m ago", "23h ago", "6d ago", a date this year; one from last year with its ", 2025" may be cut by the ellipsis in ja) share the row ({bad("refresh", row)})')
    expect(not bad('never', row), f'Refresh Feed and "Never refreshed" share the row ({bad("never", row)})')
    expect(not bad('dl', row), f'"Download · 999 MB" fits the row ({bad("dl", row)})')
    expect(not bad('head', 288) and not bad('confirm', 300), 'the Episodes header and the confirm\'s question fit')


def screen_off_tests(ctx):
    """No visual work while the screen is off: the tick, the loader, the pills' states, the sheet's rows are read at paint only."""
    expect = ctx.expect
    m = shown()
    m.screen(False); m.calls = []
    DL.poke_slot(m, 0, DEEP, 'e5.mp3', 2, seq=1)
    m.setword(DL.pn_at(12), 4242); m.setword(DL.pn_at(DL.DGEN), 4242)
    m.call(PSYMS['pg_tick'], a0=0, count=40000000)
    expect(not [c for c in m.calls if c[0] in ('widget_invalidate_force', 'widget_set_text_utf8', 'widget_set_visible', 'widget_resize', 'widget_move', 'widget_set_style', 'bitmap_create_ex', 'widget_load_image')],
           'screen off: a tick with the worker moved on does no widget, bitmap, image or style work')
    m.calls = []
    m.call(PSYMS['pg_on_load'], a0=0, count=40000000)
    expect(not [c for c in m.calls if c[0] in ('widget_load_image', 'bitmap_create_ex', 'widget_invalidate_force', 'widget_set_style')], 'screen off: the cover loader does nothing')
    m.screen(True)
    m.call(PSYMS['pg_tick'], a0=0, count=40000000)
    expect(any(c[0] == "widget_invalidate_force" for c in m.calls), "the screen is back: the first tick repaints")
    # the timers: the page keeps its own, only while in front; the awake timer is the downloads' and does no widget work
    m = shown(); m.calls = []
    fn_, ctx_ = m.bound[(m.window, O['EVT_WINDOW_TO_BG'])]; m.call(fn_, a0=ctx_, a1=0, count=4000000)
    m.calls = []
    r = m.call(PSYMS['pg_tick'], a0=0, count=4000000)
    expect(r == 0 and not m.calls, 'in the background the page\'s tick ends at once and touches nothing')
    # a refresh waiting for the downloads to pause is dropped when the screen is dark (no dialog is opened in the dark): the downloads go on
    m = shown(); m.thread = None
    PCP.click(m, 'btn_more'); PCP.click(m, 'pg_sh_refresh')
    m.setword(DL.pn_at(DL.KIND), 0); m.setword(DL.pn_at(0), 0); m.setword(DL.pn_at(DL.DPAUSE), 0); m.setword(DL.pn_at(DL.DKEY), 0)
    DL.poke_slot(m, 0, DEEP, 'e5.mp3', 1, seq=5)
    m.screen(False); m.thread = None
    m.call(PSYMS['pg_awake_tick'], a0=0, count=40000000)
    expect(m.thread and m.thread[0] == PSYMS['pn_dmain'] and m.props.get((m.widgets['pod_pd_scrim'], 'visible'), 0) == 0, 'the dark: the waiting refresh is dropped, the downloads go on, no dialog')


SECTIONS = [asset_tests, layout_tests, cell_tests, tap_tests, latest_tests, order_tests, nav_tests, tint_tests, sheet_tests, mark_all_tests, refresh_tests, unsub_tests, wrap_tests, width_tests, screen_off_tests]


def run(ctx):
    for f in SECTIONS: f(ctx)
