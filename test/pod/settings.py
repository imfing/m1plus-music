"""Settings (patch/m1plus.c, tools/pod_pages.py cards pages, tools/pod_settings.py): the built assets against the shared layout model, the deep links into the stock pages, the values read from
the stock state, and the page's refresh. The Library, Now Playing, Home Screen, Developer and Keyboards pages' own behaviour is in test/pod/menu.py, tape.py,
recent.py, home.py and keyboard.py."""
import os, struct
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)
import mod_icons, pod_settings as ST

pulldown = sibling('pulldown')
UI = os.path.join(WORK, 'rootfs', 'release', 'assets', 'default', 'raw', 'ui')


def page_tree(page): return awtk_ui.parse(open(os.path.join(UI, page.key + '.bin'), 'rb').read())


class SL(pulldown.SM):
    """A cards page as real widget structs (window > list_view > scroll_view > the asset's children, flags from the asset) under demo's own layouter (window_manager_check_and_layout:
    children_layouter_list_view stacks the visible children in child order, ignoring their y), as test/pod/recent.py does for the menu. hide: names of children that start hidden (and
    insensitive: what the payload does with widget_set_visible / widget_set_sensitive)."""

    def __init__(self, page, hide=(), show_all=False):
        super().__init__(True)
        self.page = page
        self.tree = awtk_ui.parse(open(os.path.join(UI, page.key + '.bin'), 'rb').read())
        a_sv = self.tree.find('pod_scrollview')
        self.root = self.win = self.widget(LI_VT, 0, 0, 320, 450)
        self.lv = self.widget(LV_VT, 0, 50, 320, 400, self.root)
        self.sv = sv = self.widget(SV_VT, 0, 0, a_sv.w, 400, self.lv)
        self.zv = self.alloc(0x80); self.u.mem_write(self.zv, bytes(0x80))
        self.kid = {}
        for c in a_sv.children:
            w = self.widget(LI_VT if c.type == 'list_item' else self.zv, 7, 0, c.w, c.h, sv, emitter=True)   # (x and y start wrong: only the layouter can put them right)
            flags = F_ENABLE | (F_VISIBLE if c.get('visible') != 'false' else 0) | (F_SENSITIVE if c.get('sensitive') != 'false' else 0)
            if show_all and c.get('visible') == 'false': flags |= F_VISIBLE | (F_SENSITIVE if c.type == 'list_item' else 0)   # the Equalizer page's rows the payload shows
            if c.name in hide: flags = F_ENABLE
            self.u.mem_write(w + 0x24, struct.pack('<H', flags))
            self.kid[c.name] = w
        self.kids(self.root, [self.lv]); self.kids(self.lv, [sv]); self.kids(sv, [self.kid[c.name] for c in a_sv.children])
        for off, v in ((0x78, a_sv.w), (0x7c, 0), (0xec, 0x611450), (0xf0, pulldown.LV_HOOK), (0xf4, pulldown.PAINT_HOOK)): self.setword(sv + off, v)
        self.u.mem_write(sv + 0x90, bytes([0, 1, 0]))
        speed = self.word(0x759814); self.setword(sv + 0x88, speed); self.setword(sv + 0x8c, speed)
        for off, v in ((0x7c, 52), (0x84, sv)): self.setword(self.lv + off, v)
        lay = self.alloc(0x1c); self.u.mem_write(lay, bytes(0x1c)); self.setword(lay + 0xc, pulldown.LAYOUTER_VT); self.u.mem_write(lay + 0x1a, bytes([4]))
        self.setword(sv + 0x64, lay)
        self.props[(sv, 'h')] = 400
        self.wm = self.widget(LI_VT, 0, 0, 320, 480); self.kids(self.wm, [self.root])
        self.window = self.root
        self.mark(); self.relayout()

    def box(self, name):
        a = self.kid[name]
        return self.s32(a), self.s32(a + 4), self.s32(a + 8), self.s32(a + 0xc)


def layout_tests(ctx):
    """Every cards page under demo's own layouter, plus the asset against the model."""
    expect, P = ctx.expect, pod_pages
    pages = [p for p in P.PAGES if p.kind in ('cards', 'peq')]   # (the Equalizer page is a cards page its payload binds itself: its layout is the asset's, every row shown)
    expect([p.key for p in pages] == ['m1plus_settings', 'm1plus_library', 'm1plus_homeset', 'm1plus_developer', 'm1plus_npset', 'm1plus_keyboards', 'm1plus_tapetheme', 'm1plus_about', 'm1plus_vinylrec', 'm1plus_vinyltheme', 'm1plus_cache', 'm1plus_files', 'm1plus_background', 'm1plus_accent', 'm1plus_appearance', 'm1plus_podcastregion', 'm1plus_peq', 'm1plus_battery', 'm1plus_chargelimit', 'm1plus_idleview', 'm1plus_lockscreen', 'm1plus_lockstyle', 'm1plus_nextalbum', 'm1plus_display', 'm1plus_lighttime', 'm1plus_ledlight', 'm1plus_keyspower', 'm1plus_keylock', 'm1plus_shutdown', 'm1plus_rgbtheme'],
           'the cards pages: Settings, Library, Home Screen, Developer, Now Playing, Keyboards, the three pickers, About, Cache, Settings Files, the Background picker, the Accent picker, Appearance and the Podcast Region picker, Equalizer, Battery, the Charge Limit picker, the Idle Display picker, the Lock Screen page, the Player Style picker, the Continue Playing picker, the Display page and its Screen Timeout and LED Light pickers, and the Buttons & Power page and its Button Lock and Auto-Shutdown pickers last')
    expect(mod_icons.CARD_PIECE == {'ROW_W': ST.ROW_W, 'ROW_H': ST.ROW_H, 'CARD_X': ST.CM, 'CARD_W': ST.CARD_W, 'CARD_R': ST.CARD_R, 'FILL': (0x1C, 0x1C, 0x1E), 'LIT': (0x2C, 0x2C, 0x2E)}
           and ST.CARD_RGB == '#1C1C1E' and ST.PRESSED_RGB == '#2C2C2E', 'the pieces\' geometry in tools/mod_icons.py is the layout model\'s')
    expect(mod_icons.CARD_TALL == ST.LIB_ROW_H == 60 and ST.piece_images('top', tall=True) == ('pod_cdl_top', 'pod_cdl_top_down') and ST.piece_images('mid') == ('pod_cd_mid', 'pod_cd_mid_down')
           and mod_icons.CARD_TALL_IMAGES == [f'pod_cdl_{p}{d}' for p in mod_icons.CARD_PIECES for d in ('', '_down')] and ST.row_h(P.PEQLIB_ROW) == 60 and ST.row_h(P.PEQ_PRESET) == ST.ROW_H and ST.item_h(P.PEQLIB_ROW) == 60,
           'the Presets page\'s rows are 60 px with the tall pod_cdl_* pieces; every other row 52')
    for page in pages:
        prows = [x for x in page.layout if isinstance(x, P.Row)]
        t = page_tree(page)
        lv = next(w for w in t.walk() if w.type == 'list_view')
        sv = lv.children[0]
        placed, end = ST.layout(page.layout)
        kinds = ST.pieces(page.layout)
        expect((lv.x, lv.y, lv.w, lv.h) == (0, 50, 320, 400) and sv.w == 310 and sv.name == 'pod_scrollview' and any(c.name == 'scroll_bar_m' for c in lv.children),
               f'{page.key}: the stock list (50 .. 450, scroll_view 310 wide and its scroll bar)')
        expect(not [c for c in sv.children if c.name.startswith('pod_card')] and all(c.w == ST.LIST_W for c in sv.children), f'{page.key}: no card views: the scroll_view holds only the items of the column')
        # the asset's own order, names and heights are the model's column
        names = []
        n_h = n_n = n_g = n_r = 0
        for it, y in placed:
            if it == ST.TOP: names.append(('pod_top', y, ST.CM))
            elif it == ST.END: names.append(('pod_end', y, ST.END_H))
            elif it is P.GAP: names.append((f'pod_gap{n_g}', y, ST.GAP_H)); n_g += 1
            elif isinstance(it, P.Hdr): names.append((f'pod_sec{n_h}', y, ST.HDR_H)); n_h += 1
            elif isinstance(it, P.Note): names.append((f'pod_note{n_n}', y, ST.item_h(it))); n_n += 1
            elif isinstance(it, P.Brightness): names.append(('pod_bright', y, ST.ROW_H))   # the Display page's brightness card: a row's height
            else: names.append((f'pod_row{n_r}', y, ST.ROW_H)); n_r += 1
        expect([(c.name, c.y, c.h) for c in sv.children] == names, f'{page.key}: the scroll_view\'s children are the model\'s column in display order, each as high as the model says (asset y = the stacked y)')
        # demo's own layouter on the structs
        m = SL(page, show_all=True)
        got =[(n, ) + m.box(n) for n, _, _ in names]
        expect(all((x, y, h) == (0, ey, eh) for (n, x, y, w, h), (_, ey, eh) in zip(got, names)), f'{page.key}: demo\'s layouter puts every child at x 0 and the model\'s y with its own height ({[(g[0], g[2]) for g, (_, ey, _) in zip(got, names) if g[2] != ey][:3]})')
        widths = {w for _, _, _, w, _ in got}
        expect(widths <= {ST.ROW_W, ST.LIST_W}, f'{page.key}: every child gets the list width ({sorted(widths)}), which the 320 px pieces cover')
        expect(m.vh() == end and m.vh() == sum(h for _, _, h in names), f'{page.key}: virtual_h {m.vh()} is the model\'s end {end}')
        # the rows, their pieces, glyphs, accessories, hairlines; the headers and notes
        rows = [c for c in sv.children if c.type == 'list_item']
        expect(len(rows) == len(prows) and [c.name for c in rows] == [f'pod_row{i}' for i in range(len(rows))], f'{page.key}: one list_item per row, pod_row0 ..')
        for n, it in enumerate(prows):
            r, kind = rows[n], P.row_kind(it)
            last = kinds[n] in ('single', 'bot')
            swatch = it.action == P.ACT_ACCENTSET   # the Accent picker's rows: a round swatch where a glyph goes (pod_swatch)
            has_icon = swatch or (kind not in ('check', 'info', 'preset') and it.action not in (P.ACT_CCLIST, P.ACT_SFOLD, P.ACT_UPDATE, P.ACT_REGION, P.ACT_PEQ_PRESETS, P.ACT_PEQ_TENBAND))
            lab = next(c for c in r.children if c.name == f'pod_label{n}')
            lx, lw = ST.label_box(kind, has_icon)
            if it.action == P.ACT_PEQ_PICK and it.label: lw = ST.curve_box()[0] - ST.VALUE_LABEL_GAP - lx   # the 10-Band EQ row's grey curve name
            normal, down = ST.piece_images(kinds[n])
            expect((r.x, r.h) == (0, ST.ROW_H) and r.get('style') == 'list_item_style' and (lab.x, lab.w) == (lx, lw) and lab.get('style') == 'srlabel_leftwhite21_style'
                   and r.get('style:normal:bg_image') == normal and r.get('style:pressed:bg_image') == down and r.get('style:normal:bg_image_draw_type') == 'default'
                   and r.get('style:normal:bg_color') == '#00000000', f'{page.key}:{it.label}: the {kinds[n]} piece of its card (lit when pressed), the label box from x {lx} to {lx + lw}')
            ic = [c for c in r.children if c.name in ('pod_icon', 'pod_swatch')]
            expect(bool(ic) == has_icon and (not ic or ((ic[0].x, ic[0].y, ic[0].w, ic[0].h) == (ST.ICON_X, ST.ICON_Y, 24, 24) and ic[0].get('sensitive') == 'false'
                                                         and ic[0].name == ('pod_swatch' if swatch else 'pod_icon')
                                                         and ic[0].get('image') == (f'pod_sw{it.arg}' if swatch else mod_icons.card_name(mod_icons.CARD_GLYPHS[it.label])))), f'{page.key}:{it.label}: the 20 px glyph (or the swatch) in its 24 px image, or none on a picker row')
            hair = [c for c in r.children if c.name == 'pod_hair']
            expect(bool(hair) == (not last) and (not hair or ((hair[0].x, hair[0].y, hair[0].w, hair[0].h) == (lx, ST.ROW_H - 1, ST.CM + ST.CARD_W - lx, 1) and hair[0].get('sensitive') == 'false'
                                                              and hair[0].get('style:normal:bg_color') == ST.CARD_HAIR_RGB)), f'{page.key}:{it.label}: a hairline from the label to the card\'s edge, none on the last row')
            chev = [c for c in r.children if c.name == 'pod_chevron']
            expect(bool(chev) == (kind in ('link', 'value')) and (not chev or (chev[0].x, chev[0].y, chev[0].w, chev[0].h) == ST.accessory('chevron')), f'{page.key}:{it.label}: the chevron on links and values')
            sw = [c for c in r.children if c.name == f'pod_switch{n}']
            expect(bool(sw) == (kind == 'switch') and (not sw or (sw[0].x, sw[0].y, sw[0].w, sw[0].h) == ST.accessory('switch') and sw[0].get('sensitive') == 'false'), f'{page.key}:{it.label}: the stock switch on switches')
            ck = [c for c in r.children if c.name == f'pod_check{n}']
            expect(bool(ck) == (kind in ('check', 'preset')) and (not ck or ((ck[0].x, ck[0].y, ck[0].w, ck[0].h) == ST.accessory('check' if kind == 'check' else 'preset_check') and ck[0].get('visible') == 'false' and ck[0].get('sensitive') == 'false')),
                   f'{page.key}:{it.label}: a hidden insensitive check on picker rows (a preset row\'s left of its chevron)')
            vl = [c for c in r.children if c.name == f'pod_value{n}']
            pick = it.action == P.ACT_PEQ_PICK and bool(it.label)   # the Equalizer page's 10-Band EQ row: a curve name before the check
            expect(bool(vl) == (kind in ('value', 'info') or pick) and (not vl or ((vl[0].x, vl[0].w) == (ST.info_box() if kind == 'info' else ST.curve_box() if pick else ST.value_box()) and vl[0].get('sensitive') == 'false' and vl[0].get('style:normal:text_color') == ST.GREY
                                                                 and vl[0].get('style:normal:text_align_h') == 'right')), f'{page.key}:{it.label}: a grey right aligned insensitive value on value and info rows')
            expect(kind != 'info' or ((r.get('sensitive') == 'false') == (it.action != P.ACT_SFDEL) and not chev), f'{page.key}:{it.label}: an info row takes no touch (a Settings Files row is sensitive at build, the payload sets it per file) and has no chevron')
        # a card's pieces: a run of rows is top, mid.., bot; a lone row is single
        expect(all(k in ('single', 'top', 'mid', 'bot') for k in kinds) and all((kinds[i] in ('top', 'mid')) == (kinds[i + 1] in ('mid', 'bot')) for i in range(len(kinds) - 1)),
               f'{page.key}: the pieces make whole cards ({kinds})')
        for item in ('pod_sec', 'pod_note'):
            for v in [c for c in sv.children if c.name.startswith(item)]:
                lab = v.children[0]
                expect(v.type == 'view' and v.get('sensitive') == 'false' and len(v.children) == 1 and lab.name == v.name + '_t' and lab.x == ST.HDR_X + (lab.type == 'label') * 2 == 24 + (lab.type == 'label') * 2 and lab.w == ST.HDR_W - (lab.type == 'label') * 4
                       and lab.get('sensitive') == 'false' and lab.get('style:normal:text_color') == ST.GREY and lab.get('style:normal:text_align_h') == 'left'
                       and int(lab.get('style:normal:font_size')) == (ST.HDR_PX if item == 'pod_sec' else ST.NOTE_PX),
                       f'{page.key}:{v.name}: an insensitive item holding a grey label at x {ST.HDR_X}, where the row glyphs\' ink starts (x {ST.ICON_X + (ST.ICON_PX - ST.GLYPH_PX) // 2})')
        for v in [c for c in sv.children if c.name.startswith(('pod_top', 'pod_end', 'pod_gap'))]:
            expect(v.get('sensitive') == 'false' and not v.children, f'{page.key}:{v.name}: an insensitive empty spacer')
        fade = [c for c in t.children if c.name == pod_ui.NB_FADE_NAME]
        expect(len(fade) == 1 and fade[0].get('visible') == 'false', f'{page.key}: the navbar fade stays hidden (the first card is 10 px under the bar)')
        nb = next(w for w in t.walk() if w.name == 'btn_backtoplayer')
        expect(nb.get('style:normal:icon') == 'ah_nav_np', f'{page.key}: Now Playing is the round glass (ah_nav_np), not the capsule\'s cap')
        # taps, by demo's own hit test on the laid out page: the middle of a visible row reaches the row, a header, a note, a gap, the spacers reach nothing actionable
        path = os.path.join(UI, page.key + '.bin')
        node_tree = asset_tree(path)
        for n, (x_, y_, w_, h_) in ((n, m.box(n)) for n, _, _ in names):
            nd = node(node_tree, n); nd.x, nd.y, nd.w, nd.h = x_, y_, w_, h_
            if page.kind == 'peq' and n.startswith('pod_row'): nd.flags |= F_VISIBLE | F_SENSITIVE   # the rows the payload shows (the asset starts them hidden)
        mm = Machine()
        for n, y, h in names:
            if y + h > 400: continue   # (below the list's window)
            for x in (30, 160, 290):
                got_path = stock_target(mm, node_tree, x, 50 + y + h // 2)
                if n.startswith('pod_row') and (P.row_kind(prows[int(n[7:])]) != 'info' or page.rows[int(n[7:])].action == P.ACT_SFDEL):
                    expect(n in got_path and not any(c.startswith(('pod_value', 'pod_switch', 'pod_chevron', 'pod_icon', 'pod_check', 'pod_hair')) for c in got_path), f'{page.key}: a tap at x {x} on {n} reaches its list_item ({got_path})')
                elif n == 'pod_bright':   # the Display page's brightness card: the slider takes the touch over its own width; the card (a sensitive view, or stock's hit test would not look into it) has nothing bound
                    expect(got_path[-1] == ('slider_brightness' if x == 160 else 'pod_bright') and not any(c.startswith('pod_row') for c in got_path), f'{page.key}: a tap at x {x} on {n} reaches the slider only over the slider ({got_path})')
                else:
                    expect(not any(c.startswith('pod_row') for c in got_path) and got_path[-1] in ('pod_scrollview', 'pod_listview', page.name), f'{page.key}: a tap at x {x} on {n} reaches nothing actionable ({got_path})')
    # the Home Screen page with Daily Mix off: the regen row and its note are hidden (the payload's visible + sensitive), the layouter skips them and nothing else moves
    page = P.HOMESET_PAGE
    regen_i = next(i for i, r in enumerate(page.rows) if r.action == P.ACT_REGEN)
    regen_row, regen_note = f'pod_row{regen_i}', f'pod_note{sum(isinstance(it, P.Note) for it in page.layout) - 1}'
    expect(regen_i == len(page.rows) - 1 and isinstance(page.layout[-1], P.Note) and page.layout[-1].text == 'A new mix the next time Home opens' and page.layout[-2].label == 'Regenerate Daily Mix'
           and page.layout[-3].text == 'Items the menu does not show' and regen_note == 'pod_note3', 'Regenerate Daily Mix and its note end the Home Screen page, after Extras and its note (pod_note3, the name the payload hides)')
    full, hid = SL(page),SL(page, hide=(regen_row, regen_note))
    placed, end = ST.layout(page.layout)
    expect(ST.pieces(page.layout)[regen_i] == 'single', 'Regenerate Daily Mix is a card of its own: a single piece, correct whatever its neighbours do')
    keep = [n for n in full.kid if n not in (regen_row, regen_note, 'pod_end')]
    gone = ST.ROW_H + ST.NOTE_H
    expect(keep and all(hid.box(n) == full.box(n) for n in keep) and hid.box('pod_end')[1] == full.box('pod_end')[1] - gone and full.vh() == end and hid.vh() == end - gone,
           'Daily Mix off: the layouter skips the regen row and its note, everything above stays where it was and virtual_h shrinks by their heights (no gap at the end)')
    # and the page opens that way by itself: the payload hides them when no mix can be made, and nothing else
    sm = settings_page_machine(P.HOMESET_PAGE, daily=b'0\n')
    vis = lambda n, f: [c[2] for c in sm.calls if c[0] == f and c[1] == sm.widgets[n]][-1:]
    expect(vis(regen_row, 'widget_set_visible') == [0] and vis(regen_note, 'widget_set_visible') == [0] and vis(regen_row, 'widget_set_sensitive') == [0]
           and not [c for c in sm.calls if c[0] in ('widget_set_visible', 'widget_set_sensitive') and c[1] not in (sm.widgets[regen_row], sm.widgets[regen_note])],
           'with Daily Mix off the page opens with the row and its note hidden and insensitive, and no other widget touched')


def settings_page_machine(page, daily=None):
    P = pod_pages
    m = Machine()
    m.widgets = {n: 0x30000000 + 0x100 * i for i, n in enumerate(['btn_return', 'btn_backtoplayer'] + [f'pod_note{i}' for i in range(5)] + [f'pod_row{i}' for i in range(len(page.rows))] + [f'pod_switch{i}' for i in range(len(page.rows))])}
    if daily is not None: m.fs['/mnt/data/m1plus/home-daily-mix'] = daily
    m.call(PSYMS['on_row'], a0=PSYMS['pod_rows_%d' % P.SETTINGS_PAGE_INDEX] + 12 * next(i for i, r in enumerate(P.SETTINGS_PAGE.rows) if r.action == P.ACT_PAGE and r.arg == P.PAGES.index(page)), count=3000000)
    return m


def about_tests(ctx):
    """Settings > System > About: our own page, the stock About page's values read the stock way, laid out in sections; the stock page is no longer linked."""
    expect, P = ctx.expect, pod_pages
    A = P.ABOUT_PAGE
    S = P.SETTINGS_PAGE
    ab_i = next(i for i, r in enumerate(S.rows) if r.label == 'About')
    expect((S.rows[ab_i].action, S.rows[ab_i].arg) == (P.ACT_PAGE, P.ABOUT_PAGE_INDEX) and A.title == 'About' and A.key == 'm1plus_about' and all(P.row_kind(r) == 'info' for r in A.rows if r.action != P.ACT_UPDATE) and [r.label for r in A.rows][:2] == ['M1+ Music', 'Software Update'] and P.row_kind(A.rows[1]) == 'link'
           and not any(n == 'systemset/about_page' for n, *_ in P.STOCK_PAGES), 'Settings > About opens our own page of information rows; the stock About page is not linked')
    sections = [x.text if isinstance(x, P.Hdr) else x.label if isinstance(x, P.Row) else None for x in A.layout]
    expect(sections == ['M1+ Music', 'Software Update', 'Firmware', 'Device', 'Model', 'Serial Number', 'Wi-Fi MAC', 'IP Address', 'Storage', 'Capacity', 'Available'], f'the sections: build and firmware, Device, Storage ({sections})')
    names = {r.label: i for i, r in enumerate(A.rows)}

    def open_about(sn=b'', mac=b'', card=False, disk=(0.0, 0.0), net=0, ip=b''):
        m = Machine()
        m.widgets = {n: 0x30000000 + 0x100 * i for i, n in enumerate(['btn_return', 'btn_backtoplayer'] + [f'pod_row{i}' for i in range(len(S.rows))]
                                                                       + [f'pod_value{i}' for i in range(len(A.rows))] + [f'pod_label{i}' for i in range(len(A.rows))])}
        m.u.mem_write(pod.DATA['PRODUCT_SN'][0], sn.ljust(16, b'\0')); m.u.mem_write(pod.DATA['WIFI_MAC'][0], mac.ljust(32, b'\0'))
        m.disk, m.net, m.ip = disk, net, ip
        if card: m.present.add('/tmp/mmc_add')
        m.call(PSYMS['on_row'], a0=PSYMS[f'pod_rows_{P.SETTINGS_PAGE_INDEX}'] + 12 * ab_i, count=4000000)
        return m

    utf8 = lambda t: t.encode('latin-1').decode('utf-8')

    def text(m, label):
        t = [c[2] for c in m.calls if c[0] == 'widget_set_text_utf8' and c[1] == m.widgets[f'pod_value{names[label]}']]
        return utf8(t[-1]) if t else None

    m = open_about(b'SN12345678', b'98:b3:ec:00:11:22', True, (119.25, 100.5), 1, b'192.168.1.20')
    got = {k: text(m, k) for k in ('M1+ Music', 'Firmware', 'Model', 'Serial Number', 'Wi-Fi MAC', 'IP Address', 'Capacity', 'Available')}
    import build
    expect(('window_open', A.key) in m.calls and got == {'M1+ Music': build.about(build.TAG), 'Firmware': 'V2.1', 'Model': 'Shanling M1 Plus', 'Serial Number': 'SN12345678', 'Wi-Fi MAC': '98:b3:ec:00:11:22',
                                                          'IP Address': '192.168.1.20', 'Capacity': '119.25 GB', 'Available': '100.50 GB'}, f'every value is the stock source\'s ({got})')
    expect(('getDiskMemoryInfo', '/mnt/mmc') in m.calls and ('networkGetIPAddr', 0) in m.calls, 'the card numbers come from getDiskMemoryInfo(/mnt/mmc), the IP from networkGetIPAddr(0, buf)')
    m = open_about()
    expect(not any(c[0] == 'getDiskMemoryInfo' for c in m.calls) and text(m, 'Capacity') == '0.00 GB' and text(m, 'Available') == '0.00 GB' and ('networkGetIPAddr', 0) not in m.calls
           and [text(m, k) for k in ('Serial Number', 'Wi-Fi MAC', 'IP Address')] == ['-', '-', '-'], 'no card (no /tmp/mmc_add) reads 0.00 GB without a statfs, as stock; no connection reads no IP; empty values read -')
    expect(not any(c[0] in ('navigator_to', 'window_open', 'write_int_config', 'open', 'write') for c in m.calls if c != ('window_open', A.key))
           and not [c for c in m.calls if c[0] == 'widget_on' and c[1] in {m.widgets[f'pod_value{i}'] for i in range(len(A.rows))}], 'opening the page only reads')
    # the page's rows are not bound: a tap on one does nothing (the rows are insensitive in the asset too)
    expect(not [k for k in m.bound if k[0] in {m.widgets.get(f'pod_row{i}') for i in range(len(A.rows)) if A.rows[i].action != P.ACT_UPDATE}], 'no information row of the page is bound')
    tree = page_tree(A)
    expect(all((tree.find(f'pod_row{i}').get('sensitive') == 'false') == (A.rows[i].action != P.ACT_UPDATE) for i in range(len(A.rows))), 'every information row is insensitive: not tappable; the Software Update link row takes the tap')
    rows_with_value_fit = [c for c in m.calls if c[0] == 'widget_resize' and c[1] == m.widgets[f'pod_label{names["Wi-Fi MAC"]}']]
    expect(rows_with_value_fit, 'the value takes the room its text needs and the row\'s label gets the rest (value_fit)')


def settings_machine(language=None, **state):
    """The Settings page opened from the menu's row; state: flag bytes / words written into demo's data before it opens."""
    state = {'WIFI_FLAG': 0, 'BT_FLAG': 0, 'EQ_FLAG': 0, **state}   # (demo's data starts with Wi-Fi on)
    P = pod_pages
    S = P.SETTINGS_PAGE
    m = Machine()
    names = ['btn_return', 'btn_backtoplayer'] + [f'pod_row{i}' for i in range(len(S.rows))] + [f'pod_value{i}' for i, r in enumerate(S.rows) if P.row_kind(r) == 'value']
    names += [f'pod_label{i}' for i in range(len(S.rows))] + [f'pod_switch{i}' for i, r in enumerate(S.rows) if P.row_kind(r) == 'switch']
    m.widgets = {n: 0x30000000 + 0x100 * i for i, n in enumerate(names)}
    if state.pop('shuffle', False): m.fs['/mnt/data/m1plus/playback-shuffle'] = b'1\n'   # Shuffle on (the payload's flag; stock's mode stays 0, 1 or 3)
    for key, v in [(k, v) for k, v in state.items() if k != 'mode']:
        addr = pod.DATA[key][0]
        if key == 'EQ_MODE': m.setword(addr, v)
        else: m.u.mem_write(addr, bytes([v]))
    if 'mode' in state: m.mode = state['mode']
    if language: m.set_language(language)
    m.call(PSYMS['on_row'], a0=PSYMS['pod_rows_0'] + 12 * next(i for i, r in enumerate(P.MENU.rows) if r.action == P.ACT_PAGE and r.arg == P.SETTINGS_PAGE_INDEX), count=3000000)
    return m


def stock_tests(ctx):
    expect, P = ctx.expect, pod_pages
    S = P.SETTINGS_PAGE
    rows = {r.label: i for i, r in enumerate(S.rows)}
    m = settings_machine()
    expect(('window_open', S.key) in m.calls, 'the menu row opens the Settings page')
    # the deep links: a plain navigator_to of the stock page's name (the names stock's own lists call it with: tools/pod.py SETTINGS_PINS)
    want = {'Wi-Fi': 'systemset/wifi_page', 'Bluetooth': 'systemset/bluetooth_page'}
    expect({P.STOCK_PAGES[S.rows[rows[k]].arg][0] for k in want} == set(want.values()),
           'the stock pages the rows open are the ones stock\'s Settings list and Wi-Fi hub open')
    for label, name in want.items():
        m = settings_machine()
        m.click(f'pod_row{rows[label]}')
        opened = [c[1] for c in m.calls if c[0] == 'window_open']
        expect([c for c in m.calls if c[0] == 'navigator_to'] == [('navigator_to', name)] and 'navigator_to_with_context' not in m.names() and opened == (['m1plus_wifi'] if label == 'Wi-Fi' else []),
               f'{label}: one plain navigator_to("{name}"), no context, no window of ours' + (' but the Wi-Fi page, which opens first and (here, an asset without its widgets) hands over to the stock page' if label == 'Wi-Fi' else ''))
    m = settings_machine()
    m.click(f'pod_row{rows["All Playback Settings"]}'); m.click(f'pod_row{rows["All System Settings"]}')
    # (the Home dispatcher's ids 16 and 17 are bound to the two rows: tests/pod/menu.py checks the table)
    expect(len(P.STOCK_PAGES) == 2 and all(r.action == P.ACT_STOCK for r in S.rows if r.label in want) and [r.label for r in S.rows if r.action == P.ACT_STOCK] == list(want),
           'two stock pages, each opened by an ACT_STOCK row (Display is our own page, display/settings_tests; Lock Screen > Custom Wallpaper too, lockscreen/setting_tests)')
    expect(not [r for r in P.DEVELOPER_PAGE.rows if r.action == P.ACT_STOCK] and 'systemset/fwupdate_page' not in [n for n, *_ in P.STOCK_PAGES], 'no Developer row is a stock page: the firmware update page is not in STOCK_PAGES (About > Software Update is ours)')
    m = settings_machine()
    m.click(f'pod_row{rows["EQ"]}')
    expect(('window_open', P.PEQ_PAGE.key) in m.calls and 'navigator_to' not in m.names(), 'EQ opens our Equalizer page (ACT_PEQ), not stock\'s')
    # the values: the stock state, by the stock keys
    def value(m, label):
        keys = [c[2] for c in m.calls if c[0] == 'widget_set_tr_text' and c[1] == m.widgets[f'pod_value{rows[label]}']]
        return keys[-1] if keys else None
    m = settings_machine()
    expect([value(m, k) for k in ('Wi-Fi', 'Bluetooth', 'EQ')] == ['Off', 'Off', 'Off'], f'nothing on: Off, Off, EQ Off ({[value(m, k) for k in ("Wi-Fi", "Bluetooth", "EQ")]})')
    m = settings_machine(WIFI_FLAG=1, BT_FLAG=1, mode=3, EQ_FLAG=1, EQ_MODE=4)
    expect([value(m, k) for k in ('Wi-Fi', 'Bluetooth', 'EQ')] == ['On', 'On', 'Flat'], 'Wi-Fi and Bluetooth on, the 10-Band EQ on (no record: its curve, Flat)')
    expect(not any(c[0] in ('write_int_config', 'mclSetPlayMode', 'write') or (c[0] == 'open' and c[2] != 0) for c in settings_machine().calls), 'opening the page reads state and writes nothing (the Light Mode value reads its file)')
    # the value takes the room its text needs: the box is moved and resized, and the label gets the rest (patch/m1plus.c value_fit)
    m = settings_machine()
    vi = rows['EQ']
    expect(any(c[0] == 'widget_resize' and c[1] == m.widgets[f'pod_label{vi}'] for c in m.calls) and any(c[0] == 'widget_move' and c[1] == m.widgets[f'pod_value{vi}'] for c in m.calls), 'value_fit moves the value box and resizes the row\'s label')

    # coming back to the page (a stock page may have changed the state) shows it again
    m = settings_machine()
    fg = [(k, v) for k, v in m.bound.items() if k[1] == O['EVT_WINDOW_TO_FG']]
    expect(len(fg) == 1, 'the page binds its foreground event')
    m.u.mem_write(pod.DATA['WIFI_FLAG'][0], b'\x01')
    (w, ev), (fn, ctx_) = fg[0]
    m.calls = []; m.call(fn, a0=ctx_, a1=0, count=3000000)
    expect(value(m, 'Wi-Fi') == 'On', 'back in front: Wi-Fi On, read again')


SECTIONS = [layout_tests, stock_tests, about_tests]
