"""Library rows: the pinned demo edits and the restyled stock row builders."""
import json, os, re, struct
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)


# Library rows (patch/rows.c, patch/rows.json). The real stock row
# constructors run (their widget-creation calls mocked into a widget model in emulated memory:
# x/y/w/h @0..0xc, flags @0x24, children layout @0x64), so the retargeted `jal
# compact_set_row_layout` is exercised as patched; the installed layouter is then run for real,
# with the stock default layout (0x63a444, r=1,c=0: each visible child keeps its width, gets
# y = y_margin, h = h - 2 * y_margin, x advancing by width + spacing) modelled in Python.
ROW_BUILDERS = {'music_create_tablerow': 0x528560, 'folder_create_tablerow': 0x5331fc,
                'localclass_create_tablerow': 0x5368ac, 'album_listitem_layout': 0x524228,
                'albumdeinfo_listitem_layout': 0x526394, 'playlist_listitem_layout': 0x53e44c,
                'search_albums_row': 0x542630}
CREATE = ('table_row_create', 'button_create', 'image_create', 'view_create', 'hscroll_label_create',
          'list_item_create', 'label_create')
ROW_STUBS = ('memset', 'snprintf', 'strcpy', 'deque_at')          # libc / libcstl through demo's stubs
ROW_PLAIN = ('widget_set_name', 'widget_use_style', 'image_base_set_image', 'image_set_draw_type',
             'hscroll_label_set_ellipses', 'hscroll_label_set_speed', 'get_indexrecord', 'is_playing',
             'is_otherplaying', 'getFormatString', 'toolsTrimLeft', 'toolsTrimRight', 'tk_snprintf',
             'widget_set_text_utf8', 'widget_on')


PLAYLIST_DEQ = 0xa045d0
SEARCH_DEQ = 0xa045b8


def bind_normal(m, row):
    """What a row's bind does outside multi-select before AWTK lays it out: no check box, no badge."""
    for n in ('img_choice', 'img_mqa'):
        w = m.find(row, n)
        if w: m.set_visible(w, 0)


class RowMachine(Machine):
    elf = None    # (demo's dynsym, its GOT slots of ROW_STUBS): parsed once, not per machine (0.15 s each)

    def __init__(self):
        super().__init__()
        if RowMachine.elf is None: RowMachine.elf = (pod.dynsym(DEMO), pod.got_slots(DEMO, ROW_STUBS))
        syms, got = RowMachine.elf
        self.rows_names = set()
        for n in CREATE + ROW_PLAIN + ('widget_set_visible', 'widget_set_sensitive', 'widget_restack', 'widget_set_need_relayout_children'):
            if n in syms: self.handlers[syms[n]] = 'row:' + n
        for n, slot in got.items(): self.handlers[self.word(slot)] = 'row:' + n
        for n in ('widget_count_children', 'widget_get_child', 'widget_get_type', 'widget_get_visible',
                  'widget_resize', 'widget_move', 'hscroll_label_set_only_focus', 'widget_set_children_layout'):
            self.handlers[pod.FUNCTIONS[n][2]] = 'row:' + n
        self.handlers[O['DEFAULT_LAYOUT_FN']] = 'row:stock_layout'
        self.handlers[pod.FUNCTIONS['widget_set_tr_text'][2]] = 'row:widget_set_tr_text'
        self.wtype, self.wname, self.style, self.focus, self.texts = {}, {}, {}, {}, {}
        self.images_set = {}
        self.types = {}
        self.layout_ret = 0
        self.layout_vt = O['DEFAULT_LAYOUT_VTABLE']   # what widget_set_children_layout creates
        self.stock_layouts = 0
        self.resizes = []

    def new_widget(self, kind, parent, x, y, w, h):
        a = self.alloc(0x80); self.u.mem_write(a, bytes(0x80))
        for off, v in ((0, x), (4, y), (8, w), (0xc, h), (0x24, F_ENABLE | F_VISIBLE | F_SENSITIVE), (0x44, parent)):
            self.setword(a + off, v)
        self.wtype[a] = kind
        if parent: self.children.setdefault(parent, []).append(a)
        return a

    def geo(self, w): return tuple(self.word(w + o) - (1 << 32 if self.word(w + o) >> 31 else 0) for o in (0, 4, 8, 12))
    def visible(self, w): return bool(self.word(w + 0x24) & F_VISIBLE)
    def set_visible(self, w, v):
        f = self.word(w + 0x24); self.setword(w + 0x24, f | F_VISIBLE if v else f & ~F_VISIBLE)
    def kids(self, w): return self.children.get(w, [])
    def find(self, root, name):
        if self.wname.get(root) == name: return root
        for c in self.kids(root):
            r = self.find(c, name)
            if r: return r

    def default_layout(self, layout, row):
        if not layout or not row: return 0x10
        self.stock_layouts += 1
        xm, ym, sp = (self.u.mem_read(layout + 0x14, 3))
        x, (_, _, _, h) = xm, self.geo(row)
        for c in [c for c in self.kids(row) if self.visible(c)]:
            cw = self.geo(c)[2]
            self.setword(c, x); self.setword(c + 4, ym); self.setword(c + 0xc, h - 2 * ym)
            x += cw + sp
        for c in self.kids(row): self.layout_children(c)
        return 0

    def layout_children(self, w):
        """widget_layout_children: the widget's layouter, else each child's own children in turn."""
        inner = self.word(w + O['W_CHILDREN_LAYOUT'])
        if inner: self.default_layout(inner, w)
        else:
            for c in self.kids(w): self.layout_children(c)

    def _hook(self, u, address, size, _):
        name = self.handlers.get(address)
        if not name or not name.startswith('row:'):
            return super()._hook(u, address, size, _)
        name = name[4:]
        a0, a1, a2, a3 = (u.reg_read(r) for r in (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3))
        sp = u.reg_read(UC_MIPS_REG_SP)
        stack = lambda i: self.word(sp + 16 + 4 * i)
        sx = lambda v: v - (1 << 32) if v >> 31 else v
        ret = 0
        if name in CREATE:
            kind = name[:-len('_create')]
            ret = self.new_widget(kind, a0, sx(a1), sx(a2), sx(a3), sx(stack(0)))
            self.calls.append(('create', kind, ret, a0))
        elif name == 'widget_set_name': self.wname[a0] = self.read_cstr(a1)
        elif name == 'widget_use_style': self.style[a0] = self.read_cstr(a1)
        elif name == 'widget_set_text_utf8': self.texts[a0] = self.read_cstr(a1)
        elif name == 'widget_set_tr_text': self.texts[a0] = self.tr(self.read_cstr(a1)); self.calls.append(('widget_set_tr_text', a0, self.read_cstr(a1)))
        elif name == 'widget_set_visible':
            self.set_visible(a0, a1); self.calls.append(('widget_set_visible', a0, a1))
        elif name == 'widget_set_sensitive':
            f = self.word(a0 + 0x24); self.setword(a0 + 0x24, f | F_SENSITIVE if a1 else f & ~F_SENSITIVE)
            self.props[(a0, 'sensitive')] = a1; self.calls.append(('widget_set_sensitive', a0, a1))   # (the album page tests read the prop)
        elif name == 'image_base_set_image':
            nm = self.read_cstr(a1) if a1 else None
            self.images_set[a0] = nm; self.calls.append(('image_base_set_image', a0, nm))
        elif name == 'widget_restack':    # AWTK: the child moves to index (clamped to the last), the others shift
            sib = self.kids(self.word(a0 + O['W_PARENT'])); sib.remove(a0); sib.insert(min(a1, len(sib)), a0)
            self.calls.append(('widget_restack', a0, a1))
        elif name == 'widget_set_need_relayout_children': self.calls.append(('widget_set_need_relayout_children', a0))
        elif name == 'widget_count_children': ret = len(self.kids(a0))
        elif name == 'widget_get_child':
            k = self.kids(a0); ret = k[a1] if a1 < len(k) else 0
        elif name == 'widget_get_type':
            t = self.wtype.get(a0)
            if t and t not in self.types: self.types[t] = self.cstr(t)
            ret = self.types.get(t, 0)
        elif name == 'widget_get_visible': ret = int(self.visible(a0))
        elif name == 'widget_resize':   # stock returns early on an unchanged size (@0x66d198)
            if self.geo(a0)[2:] != (sx(a1), sx(a2)): self.resizes.append((a0, sx(a1), sx(a2)))
            self.setword(a0 + 8, a1); self.setword(a0 + 0xc, a2)
        elif name == 'widget_move':
            self.setword(a0, a1); self.setword(a0 + 4, a2); self.calls.append(('widget_move', a0, sx(a1), sx(a2)))
        elif name == 'hscroll_label_set_only_focus': self.focus[a0] = a1
        elif name == 'widget_set_children_layout':
            params = self.read_cstr(a1)
            self.calls.append(('widget_set_children_layout', a0, params))
            ret = self.layout_ret if a0 else 0x10
            if not ret:
                lay = self.alloc(0x20); self.u.mem_write(lay, bytes(0x20))
                self.setword(lay + O['LAYOUT_VTABLE'], self.layout_vt)
                vals = dict(re.findall(r'([xys])=(\d+)', params))
                self.u.mem_write(lay + 0x14, bytes([int(vals.get('x', 0)), int(vals.get('y', 0)), int(vals.get('s', 0))]))
                self.setword(a0 + O['W_CHILDREN_LAYOUT'], lay)
        elif name == 'stock_layout': ret = self.default_layout(a0, a1)
        elif name == 'memset': self.u.mem_write(a0, bytes([a1 & 0xff]) * a2); ret = a0
        elif name in ('snprintf', 'tk_snprintf'):
            # the track label's "%d %s" (number, title) and a plain format (the row builders pass the record's title as one)
            # are formatted; any other format (widget names) is 'x'
            fmt = self.read_cstr(a2).encode('latin-1') if a2 else b''
            if fmt == b'%d %s': out = b'%d ' % a3 + self.read_cstr(stack(0)).encode('latin-1')
            elif b'%' not in fmt and fmt: out = fmt
            else: out = b'x'
            if a0 and a1: self.u.mem_write(a0, out[:a1 - 1] + b'\0')
            ret = len(out)
        elif name == 'strcpy':
            self.u.mem_write(a0, self.read_cstr(a1).encode('latin-1') + b'\0'); ret = a0
        elif name == 'deque_at':
            items = self.deques.get(a0, []); ret = items[a1] if a1 < len(items) else 0
        elif name == 'getFormatString':
            self.u.mem_write(a1, self.read_cstr(a0).encode('latin-1') + b'\0'); ret = a1
        # get_indexrecord, is_playing, is_otherplaying, trims, image calls, widget_on: 0, recorded
        else: self.calls.append((name, a0, a1))
        u.reg_write(UC_MIPS_REG_V0, ret & 0xffffffff)
        u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))

    def layout(self, row):
        """Run the row's installed layouter the way AWTK does: vtable slot 2 (layouter, row)."""
        lay = self.word(row + O['W_CHILDREN_LAYOUT'])
        fn = self.word(self.word(lay + O['LAYOUT_VTABLE']) + 4 * O['LAYOUT_SLOT'])
        self.resizes = []
        return self.call(fn, a0=lay, a1=row, count=400000)


def row_machine(albums=1):
    m = RowMachine()
    recs = [m.record(album=f'A long album title number {i}', artist='Artist', title=f'Track {i}') for i in range(albums)]
    dq = m.new_deque(recs)
    m.setword(pod.DATA['PDEQ_SHOWLIST'][0], dq)   # what the album rows read
    m.setword(PLAYLIST_DEQ, dq)                   # playlist_listitem_layout: lw $a0, 0($v0 = 0xa045d0) @0x53e5f0
    m.setword(SEARCH_DEQ, dq)                     # the search album rows: lw $a0, 0($v0 = 0xa045b8) @0x542720
    return m


def rows_tests(expect):
    edits = MANIFEST.get('row_edits', [])
    J = json.load(open(os.path.join(ROOT, 'patch', 'rows.json')))
    target = PSYMS['compact_set_row_layout']
    # 37. Pins: every edit as rows.json says, on the stock word, in the built demo; nothing else.
    stock_demo = open(os.path.join(paths.find_stock() or os.path.join(os.path.dirname(WORK), 'stock'), 'rootfs', pod.DEMO), 'rb').read()
    built = open(DEMO, 'rb').read()
    w = lambda b, a: struct.unpack_from('<I', b, pod.fileoff(b, a))[0]
    kinds = {k: sum(e[3] == k for e in edits) for k in ('immediate', 'call', 'nop', 'icon')}
    expect(kinds == {'immediate': sum(len(g['sites']) for g in J['immediates']),
                     'call': len(J['row_layout_calls']['sites']), 'nop': len(J['nops']['sites']), 'icon': len(J['icon_calls']['sites'])},
           f'the manifest lists every rows.json edit ({kinds})')
    icon_target = PSYMS['rows_track_icon']
    expect(sorted(int(a, 16) for a, _, _, k in edits if k == 'icon') == [0x5284e0, 0x5367b0, 0x53935c]
           and all(int(new, 16) == 0x0c000000 | (icon_target >> 2) for a, old, new, k in edits if k == 'icon'),
           'the Songs-family, Artists/Genres/Composers and queue rebinds\' image_base_set_image call is jal rows_track_icon')
    expect(all(w(stock_demo, int(a, 16)) == int(old, 16) and w(built, int(a, 16)) == int(new, 16) for a, old, new, _ in edits),
           f'all {len(edits)} edits: stock word before, the patched word in the built demo')
    expect(all(int(new, 16) == 0x0c000000 | (target >> 2) for a, old, new, k in edits if k == 'call'),
           'each row-layout call is jal compact_set_row_layout')
    def imm(old, v):   # addiu rt, $zero, imm keeps its word but the low half; move rd, $zero (or / addu rd, $zero, $zero) -> addiu rd, $zero, v
        if old >> 26 == 0 and old & 0x03e007ff in (0x25, 0x21) and (old >> 16) & 31 == 0:
            return 0x24000000 | ((old >> 11) & 31) << 16 | v
        return (old & 0xffff0000) | v
    moves = [a for g in J['immediates'] for a, old, *_ in g['sites'] if int(old, 16) >> 26 == 0]
    expect(all(int(new, 16) == imm(int(old, 16), g['value']) for g in J['immediates']
               for a, old, *_ in g['sites'] for e in edits if e[0] == hex(int(a, 16)) for new in (e[2],))
           and moves == ['0x526f00'],
           'each immediate keeps its instruction and register, only the 16-bit value changes (the one move $a1, $zero, the navbar Back x, becomes addiu $a1, $zero, 3)')
    pins = [s for g in J['pinned'] for s in g['sites']]
    expect(all(w(built, int(a, 16)) == int(old, 16) for a, old, *_ in pins), f'the {len(pins)} pinned words are untouched')
    # inside the stock file length only .pdr, PH[10], the hook and these words differ from stock
    changed = {i * 4 for i in range(len(stock_demo) // 4) if built[4 * i:4 * i + 4] != stock_demo[4 * i:4 * i + 4]}
    phoff = struct.unpack_from('<I', built, 28)[0]
    allowed = set(range(phoff + 10 * 32, phoff + 11 * 32, 4)) | {pod.fileoff(built, pod.HOME_CLICK), pod.fileoff(built, pod.HOME_CLICK) + 4}
    allowed |= {pod.fileoff(built, int(a, 16)) for a, *_ in edits}
    # the boot guard's hook on home_page_init, the same two words
    allowed |= {pod.fileoff(built, pod.HOME_INIT), pod.fileoff(built, pod.HOME_INIT) + 4}
    allowed |= {pod.fileoff(built, pod.PLAYING_INIT), pod.fileoff(built, pod.PLAYING_INIT) + 4}           # the Now Playing init hook
    allowed |= {pod.fileoff(built, pod.BIGCOVER_INIT), pod.fileoff(built, pod.BIGCOVER_INIT) + 4}         # the timed cover page init hook (patch/bigcover.c)
    allowed |= {pod.fileoff(built, pod.LOCKSCREEN_INIT), pod.fileoff(built, pod.LOCKSCREEN_INIT) + 4}     # the lock screen init hook (patch/lockscreen.c)
    allowed |= {pod.fileoff(built, pod.PLAYMORE_INIT), pod.fileoff(built, pod.PLAYMORE_INIT) + 4}         # the More dialog init hook
    allowed |= {pod.fileoff(built, pod.PULLDOWN_INIT), pod.fileoff(built, pod.PULLDOWN_INIT) + 4}         # the pull-down init hook
    allowed |= {pod.fileoff(built, pod.START_PLAYER), pod.fileoff(built, pod.START_PLAYER) + 4}           # the mclStartPlayer hook (Internet Radio's hand-over)
    allowed |= {pod.fileoff(built, h) + k for h in (pod.SAVE_STOP, pod.SAVE_START) for k in (0, 4)}      # the output-change hooks (Internet Radio)
    allowed |= {pod.fileoff(built, pod.BACKTOPLAYER), pod.fileoff(built, pod.BACKTOPLAYER) + 4}   # the on_backtoplayer_onclick hook
    allowed |= {pod.fileoff(built, pod.ID3_SITE)}                                                            # the tag reader's call (Podcasts)
    allowed |= {pod.fileoff(built, pod.QUERY_DB), pod.fileoff(built, pod.QUERY_DB) + 4, pod.fileoff(built, pod.QUERY_SORT), pod.fileoff(built, pod.QUERY_SORT) + 4}   # the Library query hooks (patch/pcmodel.c)
    allowed.add(pod.fileoff(built, pod.SCAN_SITE))                                                       # the library scan's folder test (patch/common.c pod_scan_dir)
    allowed |= {pod.fileoff(built, h) + k for h in (pod.SETMODE, pod.LOADPL, pod.FILETIME) for k in (0, 4)}               # the Shuffle hooks (patch/shuffle.c)
    allowed |= {pod.fileoff(built, a) for a, _ in pod.MODE_SITES}                                           # the 19 play mode display sites (jal sh_display_mode)
    allowed |= {pod.fileoff(built, pod.LOCKROW), pod.fileoff(built, pod.LOCKROW) + 4}                                  # the Display page's Lock Screen row: its jump to our Lock Screen page (patch/lockscreen.c lk_redirect)
    allowed |= {pod.fileoff(built, pod.EQ_ROW), pod.fileoff(built, pod.EQ_ROW) + 4}                                  # the Play Settings Equalizer row's jump to the 10-Band editor (patch/tenband.c)
    allowed |= {pod.fileoff(built, pod.NEXTALBUM_SITE), pod.fileoff(built, pod.NEXTALBUM_SITE) + 4}                     # mclNextSong's List play end branch (Continue with Next Album, hook 24)
    allowed.add(pod.fileoff(built, pod.CLEAR_SITE))                                                      # dmr_serverstart's deque_clear call (jal sh_clear_queue)
    allowed.add(pod.fileoff(built, pod.UPDATE_SITE))                                                     # update_firmware's version compare operand (docs/modules/version.md)
    for a, old, *_ in pod.autotime.EDITS: allowed |= {pod.fileoff(built, a) + k for k in range(0, len(old), 4)}   # the clock sync's string literals (tools/autotime.py)
    allowed |= {pod.fileoff(built, a) for a, *_ in pod.coex.EDITS}                                      # Wi-Fi and Bluetooth together: four beqz -> b (tools/coex.py)
    allowed |= {pod.fileoff(built, a) for a, *_ in pod.themeoff.EDITS}                                   # stock theme1 off: the clamp, the System page's row table and count (tools/themeoff.py)
    allowed.update(pod.fileoff(built, a) for a, _ in pod.LINEOUT_SITES)                                  # the jalr widget_set_text_utf8 of label_volume in show_sysbar_face and dropdown_showface (patch/lineout.c)
    allowed.add(pod.fileoff(built, pod.IDLE_SITE))                                                       # the timed open's navigator_to call (patch/bigcover.c bc_timed_open)
    allowed.add(pod.fileoff(built, pod.WIFIHUB_SITE))                                                  # the All System Settings Wi-Fi row's navigator_to call (patch/wifipage.c wifi_hub_open)
    allowed.add(pod.fileoff(built, pod.TIDALKB_SITE))                                                    # the stock Tidal search page's edit_set_focus call (patch/tidalkb.c tidal_kb_focus)
    allowed.update(pod.fileoff(built, a) for a in pod.PULLDOWN_OPEN_SITES)                               # on_wm_tsmove_fun's two navigator_to calls that open the page a pull-down tile chose (patch/pulldown.c pd_open_settings)
    allowed.add(pod.fileoff(built, pod.BATTERY_SITE))                                                    # show_sysbar_face's get_battery_capacity call (patch/battery.c)
    allowed |= {pod.fileoff(built, pod.timezones.SELECT), pod.fileoff(built, pod.timezones.SELECT) + 4}   # select_timezone's hook (tools/timezones.py)
    allowed |= {pod.fileoff(built, a) for a, *_ in pod.timezones.edits(0, 0)}                           # the time zone picker's clamp, counts and two call sites
    allowed.add(pod.fileoff(built, pod.SCROLL_SLOT))                                                   # the scroll_view vtable slot (patch/scroll.c)
    allowed |= {pod.fileoff(built, a) + k for a in (pod.STYLE_COLOR, pod.IMAGE_ADD, pod.STYLE_GRADIENT) for k in (0, 4)}   # Light Mode's three hooks: two words each (patch/palette.c)
    allowed.add(pod.fileoff(built, pod.SCROLL_SLOT))                                                     # the scroll_view vtable slot (patch/scroll.c)
    import mod_nowplaying   # the A-B marker immediates (five pinned words, disjoint from the row edits)
    expect(not {hex(a) for a in mod_nowplaying.MARKER_WORDS} & {e[0] for e in edits}, 'the 5 A-B marker sites are not among the row edits')
    allowed |= {pod.fileoff(built, a) for a in mod_nowplaying.MARKER_WORDS}
    # the lock screen also sets the cover file size in four `addiu a3/a2, zero, 0xfe` words
    # (mod_lockscreen.COVER_IMM); they must be disjoint from the row edits and only change the 16-bit value
    cover_sites = (0x4df1dc, 0x4df1e0, 0x4df21c, 0x4df220)
    expect(not {hex(c) for c in cover_sites} & {e[0] for e in edits}, 'the 4 cover-size sites are not among the row edits')
    for c in cover_sites:
        o, n = w(stock_demo, c), w(built, c)
        if o != n:
            expect(o in (0x240700fe, 0x240600fe) and (n & 0xffff0000) == (o & 0xffff0000) and 66 <= (n & 0xffff) < 0x8000,
                   f'cover-size word {c:#x}: addiu immediate only ({o:#010x} -> {n:#010x})')
            allowed.add(pod.fileoff(built, c))
    from elftools.elf.elffile import ELFFile
    pdr = [s for s in ELFFile(open(DEMO, 'rb')).iter_sections() if s.name == '.pdr']
    if pdr: allowed |= set(range(pdr[0]['sh_offset'] // 4 * 4, pdr[0]['sh_offset'] + pdr[0]['sh_size'] + 4, 4))
    extra = sorted(changed - allowed)
    expect(not extra, f'demo differs from stock only in .pdr, PH[10], the hook and the row edits ({[hex(x) for x in extra[:6]]})')
    hook_words = {pod.fileoff(built, h + 4 * k) for h in (pod.HOME_CLICK, pod.HOME_INIT) for k in range(3)}
    expect(not any(pod.fileoff(built, int(a, 16)) in hook_words for a, *_ in edits), 'no row edit touches a hook')

    # 38. Songs: the real music_create_tablerow builds a 64 px row with a 60 px button; its layout
    #     call reaches compact_set_row_layout, which installs the row fit.
    m = row_machine()
    table = m.new_widget('table_client', 0, 0, 0, 310, 400)
    m.call(ROW_BUILDERS['music_create_tablerow'], a0=table, count=400000)
    row = m.kids(table)[0]; btn = m.kids(row)[0]
    lay = m.word(btn + O['W_CHILDREN_LAYOUT'])
    vt = m.word(lay + O['LAYOUT_VTABLE'])
    expect(m.geo(row)[3] == 64 and m.geo(btn)[3] == 60 and m.wname.get(btn) == 'btn_table_row',
           f'Songs: table_row 310x{m.geo(row)[3]}, btn_table_row 310x{m.geo(btn)[3]} (PITCH 64, BODY 60)')
    expect(('widget_set_children_layout', btn, 'default(r=1,c=0,x=12,s=8)') in m.calls,
           'the constructor\'s own layout call reaches the stock widget_set_children_layout through the payload')
    expect(vt == PSYMS['row_vtable'] and m.word(vt + 4 * O['LAYOUT_SLOT']) == PSYMS['compact_row_layout'] and
           all(m.word(vt + 4 * k) == m.word(O['DEFAULT_LAYOUT_VTABLE'] + 4 * k) for k in range(O['LAYOUT_VTABLE_WORDS'])
               if k != O['LAYOUT_SLOT']),
           'the row\'s layouter now uses the default vtable with compact_row_layout in the layout slot')
    bind_normal(m, row); m.set_visible(m.find(row, 'img_mqa'), 1)
    m.layout(btn)
    g = lambda n: m.geo(m.find(row, n))
    name, info, artist = m.find(row, 'scrlabel_name'), m.find(row, 'view_info'), m.find(row, 'scrlabel_artist')
    va = [c for c in m.kids(info) if m.wtype[c] == 'view'][0]
    expect(g('img_icon')[:2] == (12, 0) and g('view_info') == (60, 0, 238, 60),
           f'Songs: icon at 12, text container x 60 w 238 (to 298) ({g("img_icon")}, {g("view_info")})')
    expect(g('scrlabel_name') == (0, 7, 238, 24) and m.geo(va) == (0, 33, 238, 20),
           f'Songs: title (0, 7, 238, 24), second line (0, 33, 238, 20) ({g("scrlabel_name")}, {m.geo(va)})')
    mqa = g('img_mqa')
    expect(g('scrlabel_artist')[0] == 25 and g('scrlabel_artist')[2] == 213 and mqa[2] == 20,
           f'Songs: with the MQA badge the artist runs 25 .. 238 ({g("scrlabel_artist")})')
    m.set_visible(m.find(row, 'img_mqa'), 0); m.layout(btn)
    expect(g('scrlabel_artist')[:3] == (0, 0, 238), f'without it the artist takes the whole line ({g("scrlabel_artist")})')
    expect(m.focus.get(name) == 1 and m.focus.get(artist) == 1, 'Songs: title and artist scroll only while focused')
    m.set_visible(m.find(row, 'img_choice'), 1); m.layout(btn)
    expect(g('view_info')[0] == 94 and g('view_info')[2] == 204 and g('scrlabel_name')[2] == 204,
           f'Songs multi-select: the check box takes 34 px, the text 94 .. 298 ({g("view_info")})')
    m.set_visible(m.find(row, 'img_choice'), 0); m.layout(btn); before = [m.geo(c) for c in m.kids(btn)]
    m.layout(btn)
    expect(not m.resizes and [m.geo(c) for c in m.kids(btn)] == before,
           'a second layout pass changes nothing (no relayout loop)')

    # 39. Folders and Artists/Genres: one 21 px line, x 60, 217 with the chevron, 238 without.
    for key in ('folder_create_tablerow', 'localclass_create_tablerow'):
        m = row_machine()
        table = m.new_widget('table_client', 0, 0, 0, 310, 400)
        m.call(ROW_BUILDERS[key], a0=table, count=400000)
        row = m.kids(table)[0]; btn = m.kids(row)[0]
        bind_normal(m, row)
        m.layout(btn)
        lab, chev = m.find(row, 'scrlabel_name'), m.kids(btn)[-1]
        expect(m.geo(row)[3] == 64 and m.geo(btn)[3] == 60 and m.geo(lab)[0] == 60 and m.geo(lab)[2] == 217 and
               m.geo(chev)[0] == 285 and m.geo(chev)[2] == 13,
               f'{key}: row 64 / button 60, title x 60 w 217, chevron 285 .. 298 ({m.geo(lab)}, {m.geo(chev)})')
        m.set_visible(chev, 0); m.layout(btn)
        expect(m.geo(lab)[2] == 238 and m.focus.get(lab) == 1,
               f'{key}: no chevron (a song file): the title runs to 298, scrolls only focused ({m.geo(lab)})')

    # 40. Albums (x=0 list_item rows): 52 px cover drawn 1:1 at (4, 4) within the 60 px body,
    #     title and artist x 60 w 217, chevron 285 .. 298; the row keeps its 64 px.
    m = row_machine()
    item = m.new_widget('list_item', 0, 0, 0, 310, 64)
    m.call(ROW_BUILDERS['album_listitem_layout'], a0=item, a1=0, count=600000)
    expect(('widget_set_children_layout', item, 'default(r=1,c=0,x=0,s=8)') in m.calls and
           m.word(m.word(item + O['W_CHILDREN_LAYOUT']) + O['LAYOUT_VTABLE']) == PSYMS['row_vtable'],
           'Albums: the row layout call installs the row fit')
    m.layout(item)
    kids = m.kids(item)
    choice, cover, text, chev = kids[0], kids[1], kids[2], kids[3]
    t_title, t_artist = m.kids(text)[:2]
    expect(m.geo(cover) == (4, 0, 52, 60) and m.geo(item)[3] == 64,
           f'Albums: cover 52 x 60 at x 4 (a 52 px thumbnail centres 1:1: 4 px inset), row still 64 ({m.geo(cover)})')
    expect(m.geo(text) == (60, 0, 217, 60) and m.geo(t_title) == (0, 7, 217, 24) and m.geo(t_artist) == (0, 33, 217, 20),
           f'Albums: text x 60 w 217, title (0, 7), artist (0, 33) ({m.geo(text)}, {m.geo(t_title)}, {m.geo(t_artist)})')
    expect(m.geo(chev)[0] == 285 and m.geo(chev)[2:] == (13, 60) and all(m.geo(c)[3] == 60 for c in kids if m.visible(c)),
           f'Albums: chevron 285 .. 298; every child on the 60 px body above the separator ({m.geo(chev)})')
    m.set_visible(choice, 1); m.layout(item)
    expect(m.geo(text)[2] == 159 and m.geo(cover)[0] == 58 and m.geo(choice)[0] == 0,
           f'Albums multi-select: the 50 px check box first, the cover after it, text 159 ({m.geo(choice)}, {m.geo(cover)}, {m.geo(text)})')

    # 41. Album tracks and Playlists (x=12 list_item rows): one stretched label.
    m = row_machine()
    item = m.new_widget('list_item', 0, 0, 0, 310, 64)
    m.call(ROW_BUILDERS['albumdeinfo_listitem_layout'], a0=item, a1=0, count=600000)
    m.layout(item)
    lab = [c for c in m.kids(item) if m.wtype[c] == 'hscroll_label'][0]
    expect(m.geo(lab) == (12, 0, 286, 60) and m.focus.get(lab) == 1 and not [c for c in m.kids(item) if m.wtype[c] == 'label'],
           f'album tracks (the plain stock page): one title label x 12 w 286 on the 60 px body, scrolls only focused, no number label ({m.geo(lab)})')
    m = row_machine(albums=3)
    item = m.new_widget('list_item', 0, 0, 0, 310, 64)
    m.call(ROW_BUILDERS['playlist_listitem_layout'], a0=item, a1=0, count=600000)
    m.layout(item)
    lab = [c for c in m.kids(item) if m.wtype[c] == 'hscroll_label'][0]
    arrow = m.kids(item)[-1]
    expect(m.geo(lab)[0] == 60 and m.geo(lab)[2] == 217 and m.geo(arrow)[0] == 285 and m.geo(arrow)[3] == 60,
           f'Playlists: name x 60 w 217, the arrow at 285 ({m.geo(lab)}, {m.geo(arrow)})')

    # 42. Search albums: the M1-only search row builder, its own call retargeted too.
    m = row_machine()
    item = m.new_widget('list_item', 0, 0, 0, 310, 64)
    m.call(ROW_BUILDERS['search_albums_row'], a0=item, a1=0, count=600000)
    m.layout(item)
    cover, text = m.kids(item)[0], m.kids(item)[1]
    expect(m.geo(cover) == (4, 0, 52, 60) and m.geo(text)[0] == 60 and m.geo(text)[2] == 238 and
           [m.geo(c)[1:] for c in m.kids(text)[:2]] == [(7, 238, 24), (33, 238, 20)],
           f'Search albums: cover at 4, text x 60 w 238 (no chevron), title 7 / artist 33 ({m.geo(cover)}, {m.geo(text)})')

    # 43. Fallbacks: the stock layout always runs; anything unexpected is left to it alone.
    m = row_machine(); m.layout_ret = 0x10
    table = m.new_widget('table_client', 0, 0, 0, 310, 400)
    m.call(ROW_BUILDERS['music_create_tablerow'], a0=table, count=400000)
    btn = m.kids(m.kids(table)[0])[0]
    expect(m.word(btn + O['W_CHILDREN_LAYOUT']) == 0, 'a failed widget_set_children_layout: nothing installed')
    m = RowMachine()
    v = m.call(PSYMS['compact_set_row_layout'], a0=0, a1=m.cstr('default(r=1,c=0,x=12,s=8)'))
    expect(v == 0x10, 'a null row: the stock error, nothing else')
    m = RowMachine(); m.layout_vt = 0x00904000   # e.g. a list / grid layouter: another vtable
    r = m.new_widget('button', 0, 0, 0, 310, 60)
    m.call(PSYMS['compact_set_row_layout'], a0=r, a1=m.cstr('default(r=1,c=0,x=12,s=8)'))
    expect(m.word(m.word(r + O['W_CHILDREN_LAYOUT']) + O['LAYOUT_VTABLE']) == 0x00904000,
           'a layouter that is not the stock default one is left alone')
    m = RowMachine()
    expect(m.call(PSYMS['compact_row_layout'], a0=0, a1=0) == 0x10 and m.stock_layouts == 0,
           'a null layouter or row: straight to the stock layout (its own error)')
    lay = m.alloc(0x20); m.u.mem_write(lay, bytes(0x20)); m.u.mem_write(lay + 0x14, bytes([12, 0, 8]))
    r = m.new_widget('button', 0, 0, 0, 310, 60)
    img = m.new_widget('image', r, 0, 0, 40, 60); m.new_widget('label', r, 0, 0, 200, 60)
    m.resizes = []
    m.call(PSYMS['compact_row_layout'], a0=lay, a1=r, count=200000)
    expect(m.stock_layouts == 1 and not m.resizes and not m.focus,
           'a row without an hscroll_label: the stock layout alone, nothing resized')
    m.stock_layouts = 0
    lbl2 = m.new_widget('hscroll_label', r, 0, 0, 100, 60); m.set_visible(lbl2, 0)
    m.call(PSYMS['compact_row_layout'], a0=lay, a1=r, count=200000)
    expect(m.stock_layouts == 1 and not m.resizes, 'a hidden title: nothing resized, the stock layout runs')
    big = m.new_widget('button', 0, 0, 0, 310, 60)
    for k in range(O['ROW_MAX_CHILDREN'] + 1): m.new_widget('hscroll_label', big, 0, 0, 10, 60)
    m.stock_layouts = 0
    m.call(PSYMS['compact_row_layout'], a0=lay, a1=big, count=400000)
    expect(m.stock_layouts == 1 and not m.resizes, f'more than {O["ROW_MAX_CHILDREN"]} children: the stock layout alone')
    tiny = m.new_widget('button', 0, 0, 0, 30, 60)
    m.new_widget('image', tiny, 0, 0, 40, 60); t2 = m.new_widget('hscroll_label', tiny, 0, 0, 100, 60)
    m.call(PSYMS['compact_row_layout'], a0=lay, a1=tiny, count=200000)
    expect(m.geo(t2)[2] == 0, 'a row too narrow for its text: width 0, not negative')

    # 44. The track rows' repeated format disc (rows_track_icon, replacing the rebinds' image_base_set_image): the stock call
    #     first, then the placeholder is hidden (visible and sensitive off) and the title takes its place; the playing
    #     disc and the icons of places stay; a recycled row shows the disc again when it turns out to be the playing one.
    m = row_machine()
    table = m.new_widget('table_client', 0, 0, 0, 310, 400)
    m.call(ROW_BUILDERS['music_create_tablerow'], a0=table, count=400000)
    row = m.kids(table)[0]; btn = m.kids(row)[0]; bind_normal(m, row)
    img = m.find(row, 'img_icon'); info = m.find(row, 'view_info')
    shown = lambda: (m.visible(img), bool(m.word(img + 0x24) & F_SENSITIVE))
    def seticon(name, w=None): m.call(PSYMS['rows_track_icon'], a0=w or img, a1=m.cstr(name), count=100000)
    m.layout(btn)
    expect(shown() == (True, True) and m.geo(info)[0] == 60, 'before the bind: the icon is there and the text starts at 60')
    seticon('icon_flac'); m.layout(btn)
    expect(m.images_set[img] == 'icon_flac' and shown() == (False, False), 'a track\'s format disc: the stock call is made, then it is hidden and insensitive')
    expect(m.geo(info) == (12, 0, 286, 60) and m.geo(m.find(row, 'scrlabel_name')) == (0, 7, 286, 24),
           f'the text container starts at the 12 px margin and runs to 298 ({m.geo(info)})')
    n_vis = sum(c[0] == 'widget_set_visible' for c in m.calls); seticon('icon_ogg')
    expect(sum(c[0] == 'widget_set_visible' for c in m.calls) == n_vis and m.images_set[img] == 'icon_ogg', 'another format disc on a hidden icon: no further visibility call (no relayout)')
    order = lambda: [m.wname.get(c) for c in m.kids(btn)]
    expect(order() == ['img_choice', 'img_icon', 'view_info'], f'the stock flow is check box, icon, text ({order()})')
    seticon('icon_playing'); pc = list(m.calls); m.layout(btn)
    expect(m.images_set[img] == 'np_row_playing' and shown() == (True, True) and order() == ['img_choice', 'view_info', 'img_icon'] and ('image_set_draw_type', img, 2) in pc
           and ('widget_restack', img, 2) in pc,
           f'the playing row: the red disc is replaced by the wave marker, drawn centred, moved after the text ({order()})')
    ix, iy, iw, ih = m.geo(img)
    expect(m.geo(info) == (12, 0, 238, 60) and (ix, iw) == (258, 40) and ix + iw == 298 and m.geo(info)[0] == 12,
           f'the title starts at the 12 px margin like every row, ends at {m.geo(info)[0] + m.geo(info)[2]}; the marker widget is 258..298 ({m.geo(img)})')
    from PIL import Image
    wave = Image.open(os.path.join(WORK, 'rootfs', 'release/assets/default/raw/images/xx/np_row_playing.png')).convert('RGBA')
    wb = wave.getchannel('A').point(lambda v: 255 if v > 0 else 0).getbbox()
    gx0, gx1 = ix + (iw - wave.width) // 2 + wb[0], ix + (iw - wave.width) // 2 + wb[2]
    gy0, gy1 = iy + (ih - wave.height) // 2 + wb[1], iy + (ih - wave.height) // 2 + wb[3]
    expect(wave.size == (40, 20) and wb[2] == 40 and wb[2] - wb[0] == 20 and (gx0, gx1) == (278, 298) and (gy0 + gy1) / 2 == iy + ih / 2 and gy1 - gy0 == 20,
           f'the wave is 20 px wide at the right end of the title column (x {gx0}..{gx1}), 20 px tall, vertically centred in the row')
    expect(m.geo(m.find(row, 'scrlabel_name'))[2] == 238 and 12 + 238 < gx0, 'a long title is cut at the label (238 px, x 250) before the marker (x 278)')
    from awtk_text import Ttf, StbText
    ttf = Ttf(os.path.join(WORK, 'rootfs', 'release/assets/default/raw/fonts/default.ttf'))
    expect(StbText(ttf, 20).layout('A' * 60)[1] > 238 and StbText(ttf, 20).layout('Track 1')[1] < 238, 'a 60 char title overflows the 238 px label (it ellipsises there), a short one fits')
    seticon('icon_playing')
    expect(not any(c[0] in ('widget_restack', 'widget_set_visible', 'widget_set_need_relayout_children') for c in m.calls) and order() == ['img_choice', 'view_info', 'img_icon'],
           'the same row rebound as playing again: nothing moves (no relayout)')
    seticon('icon_mp3'); m.layout(btn)
    expect(shown() == (False, False) and order() == ['img_choice', 'img_icon', 'view_info'] and m.geo(info) == (12, 0, 286, 60),
           'and the same row, rebound to another track, hides the marker and is back in the stock order, the title at 12 .. 298')
    m.set_visible(img, 1)
    seticon('icon_playing'); pc = list(m.calls); m.layout(btn)
    expect(order() == ['img_choice', 'view_info', 'img_icon'] and ('widget_restack', img, 2) in pc
           and not any(c[0] == 'widget_set_visible' for c in pc) and ('widget_set_need_relayout_children', btn) in pc,
           'a first-bound row (icon still visible): the restack alone relayouts the row')
    seticon('icon_mp3')
    # multi-select: the check box (first) stays, the marker is after the text
    m.set_visible(m.find(row, 'img_choice'), 1); seticon('icon_playing'); m.layout(btn)
    expect(m.geo(m.find(row, 'img_choice'))[0] == 12 and m.geo(info)[0] == 46 and m.geo(img)[0] + m.geo(img)[2] == 298 and m.geo(info)[0] + m.geo(info)[2] + 8 == m.geo(img)[0],
           f'multi-select, playing row: check box, title, marker; the marker still ends at 298 ({m.geo(info)}, {m.geo(img)})')
    seticon('icon_mp3'); m.set_visible(m.find(row, 'img_choice'), 0); m.layout(btn)
    # the Now Playing queue (the jump list): rows cloned from the asset, a stock flow (x 12, spacing 8) of icon and text 238 wide
    jr = m.new_widget('button', 0, 0, 0, 310, 60); jimg = m.new_widget('image', jr, 0, 0, 40, 0); jinfo = m.new_widget('view', jr, 0, 0, 238, 0)
    m.wname[jimg], m.wname[jinfo] = 'img_icon', 'view_info'
    jl = m.alloc(0x20); m.u.mem_write(jl, bytes(0x20)); m.setword(jl + O['LAYOUT_VTABLE'], O['DEFAULT_LAYOUT_VTABLE']); m.u.mem_write(jl + 0x14, bytes([12, 0, 8]))
    m.setword(jr + O['W_CHILDREN_LAYOUT'], jl)
    seticon('icon_playing', jimg); m.default_layout(jl, jr)
    expect([m.wname[c] for c in m.kids(jr)] == ['view_info', 'img_icon'] and m.geo(jinfo)[:3] == (12, 0, 238) and m.geo(jimg)[0] + m.geo(jimg)[2] == 298
           and m.images_set[jimg] == 'np_row_playing',
           'the queue\'s playing row: title at 12 (width 238), the wave marker at the right end like in Songs')
    seticon('icon_flac', jimg); m.default_layout(jl, jr)
    expect([m.wname[c] for c in m.kids(jr)] == ['img_icon', 'view_info'] and not m.visible(jimg) and m.geo(jinfo)[0] == 12, 'and a recycled queue row is back in the stock order, the title at 12')
    seticon('icon_playing')   # the table row again, playing, for the checks below
    for place in ('icon_folder', 'icon_playlist', 'icon_tf', 'icon_otg'):
        seticon(place); expect(m.images_set[img] == place and shown() == (True, True), f'{place}: a place, not a track: kept')
    for fmt in ('icon_aiff', 'icon_alac', 'icon_dsf', 'icon_m4a', 'icon_wav', 'icon_mp3'):
        seticon(fmt); expect(shown() == (False, False), f'{fmt}: hidden'); seticon('icon_playing')
    m.set_visible(m.find(row, 'img_choice'), 1); seticon('icon_flac'); m.layout(btn)
    expect(m.geo(info)[0] == 46 and m.geo(info)[2] == 252, f'multi-select with the disc hidden: the check box takes its 34 px, the text 46 .. 298 ({m.geo(info)})')
    m.set_visible(m.find(row, 'img_choice'), 0)
    m.calls = []; m.call(PSYMS['rows_track_icon'], a0=0, a1=m.cstr('icon_flac'), count=100000)
    expect(m.calls == [('image_base_set_image', 0, 'icon_flac')], 'a null widget: only the stock call (its own null check)')
    m.set_visible(img, 1); m.setword(img + 0x24, m.word(img + 0x24) | F_SENSITIVE)
    m.call(PSYMS['rows_track_icon'], a0=img, a1=0, count=100000)
    expect(shown() == (True, True), 'a null name: nothing hidden')


def class_icon_tests(expect):
    """Artists / Genres / Composers (localclass_create_tablerow 0x5368ac, whose bind 0x536634 names the one placeholder icon of
    the page: icon_artist / icon_genre / icon_composer, or icon_playing, at the join 0x5367b0): the placeholder is hidden,
    the name starts at the 12 px margin and takes the width up to the chevron; the playing row's wave sits before the chevron."""
    from awtk_text import Ttf, StbText
    m = row_machine()
    table = m.new_widget('table_client', 0, 0, 0, 310, 400)
    m.call(ROW_BUILDERS['localclass_create_tablerow'], a0=table, count=400000)
    row = m.kids(table)[0]; btn = m.kids(row)[0]; bind_normal(m, row)
    img, name, chev, choice = m.find(row, 'img_icon'), m.find(row, 'scrlabel_name'), m.find(row, 'btn_right'), m.find(row, 'img_choice')
    shown = lambda: (m.visible(img), bool(m.word(img + 0x24) & F_SENSITIVE))
    order = lambda: [m.wname.get(c) for c in m.kids(btn)]
    seticon = lambda n: m.call(PSYMS['rows_track_icon'], a0=img, a1=m.cstr(n), count=100000)
    m.layout(btn)
    expect(m.geo(name) == (60, 0, 217, 60), f'before the bind: icon at 12, name x 60 w 217 ({m.geo(name)})')
    ttf = Ttf(os.path.join(WORK, 'rootfs', 'release/assets/default/raw/fonts/default.ttf'))
    for icon in ('icon_artist', 'icon_genre', 'icon_composer'):
        m.set_visible(img, 1); seticon(icon); m.layout(btn)
        expect(m.images_set[img] == icon and shown() == (False, False) and m.geo(name) == (12, 0, 265, 60) and m.geo(chev)[0] == 285 and m.geo(chev)[2] == 13,
               f'{icon}: the stock call, then hidden and insensitive; name x 12 w 265, chevron kept at 285 ({m.geo(name)}, {m.geo(chev)})')
    long_name = 'Wolfgang Amadeus Mozart'
    expect(217 < StbText(ttf, 21).layout(long_name)[1] <= 265,
           f'a name of {StbText(ttf, 21).layout(long_name)[1]} px was cut at 217 before and fits the 265 px label now')
    expect(order() == ['img_choice', 'img_icon', 'scrlabel_name', 'btn_right'] and m.focus.get(name) == 1, 'the flow order is unchanged, the name scrolls only focused')
    n_vis = sum(c[0] == 'widget_set_visible' for c in m.calls); seticon('icon_artist')
    expect(sum(c[0] == 'widget_set_visible' for c in m.calls) == n_vis, 'another placeholder on the hidden icon: no further visibility call')
    # multi-select: the check box first, then the name; the chevron is hidden by the bind (a hidden child is skipped)
    m.set_visible(choice, 1); m.set_visible(chev, 0); m.layout(btn)
    cx, _, cw, _ = m.geo(choice)
    expect(cx == 12 and m.geo(name)[0] == cx + cw + 8 and m.geo(name)[0] + m.geo(name)[2] == 298,
           f'multi-select: check box, name to 298 ({m.geo(choice)}, {m.geo(name)})')
    m.set_visible(choice, 0); m.set_visible(chev, 1)
    # the artist that is playing: the wave marker before the chevron, the chevron stays last at 285 .. 298
    seticon('icon_playing'); pc = list(m.calls); m.layout(btn)
    ix, iy, iw, ih = m.geo(img)
    expect(m.images_set[img] == 'np_row_playing' and shown() == (True, True) and order() == ['img_choice', 'scrlabel_name', 'img_icon', 'btn_right']
           and ('widget_restack', img, 2) in pc and ('image_set_draw_type', img, 2) in pc,
           f'the playing row: the wave marker moves after the name, before the chevron ({order()})')
    expect(m.geo(name) == (12, 0, 217, 60) and (ix, iw) == (237, 40) and ix + iw + 8 == m.geo(chev)[0] and m.geo(chev)[0] + m.geo(chev)[2] == 298,
           f'name x 12 w 217, marker 237..277 (wave 257..277), chevron 285..298 ({m.geo(name)}, {m.geo(img)}, {m.geo(chev)})')
    pc = len(m.calls); seticon('icon_playing')
    expect(not any(c[0] in ('widget_restack', 'widget_set_visible', 'widget_set_need_relayout_children') for c in m.calls[pc:]) and order()[2] == 'img_icon',
           'the same row rebound as playing again: nothing moves')
    seticon('icon_composer'); m.layout(btn)
    expect(shown() == (False, False) and order() == ['img_choice', 'img_icon', 'scrlabel_name', 'btn_right'] and m.geo(name) == (12, 0, 265, 60),
           'a recycled row rebound to a non-playing artist: back in the stock order, hidden, the name at 12 w 265')
    m.layout(btn); before = [m.geo(c) for c in m.kids(btn)]; m.layout(btn)
    expect(not m.resizes and [m.geo(c) for c in m.kids(btn)] == before, 'a second layout pass changes nothing (no relayout loop)')
    # pressed band: the row layout still draws children on the 60 px body (row 64 minus the 4 px separator) and the chevron height is 60
    expect(all(m.geo(c)[3] == 60 for c in m.kids(btn) if m.visible(c)) and m.geo(row)[3] == 64, 'every visible child is on the 60 px body, the row stays 64 px')


def run(ctx):
    rows_tests(ctx.expect)
    class_icon_tests(ctx.expect)
