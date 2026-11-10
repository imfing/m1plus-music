"""Payload pieces shared by several pages: pod_open_player (Now Playing opens the way a stock album row's tap opens it; patch/songops.c), the tone cache
(patch/common.c), and Cover Flow's first-album / last-album memory."""
import os, struct
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)


class StackMachine(StockEventMachine):
    """Play / Shuffle into Now Playing against a window stack. demo's own window_manager_get_top_window runs for real on
    a window manager struct laid out in emulated memory (children darray @0x58, a window's name @0x10 and flags @0x24, bit 4 =
    visible); navigator_back, window_close, navigator_window_is_exist and the navigator's open are the model: a window is
    removed at once, except one whose name is in anim (a close animation: it stays in the list, visible, until finish(), as
    window_close's pending close does, docs/modules/boot.md)."""
    MOCK = ('window_manager', 'navigator_window_is_exist', 'navigator_back', 'window_close', 'navigator_to_with_context')

    def __init__(self, stack, anim=(), songer=1, tracks=4, cls=0xff10):
        super().__init__()
        self.handlers.pop(pod.FUNCTIONS['window_manager_get_top_window'][2], None)   # stock's own
        self.wmw = self.alloc(0x100); self.u.mem_write(self.wmw, bytes(0x100))
        vt = self.alloc(0x40); self.u.mem_write(vt, bytes(0x40)); self.setword(self.wmw + 0x88, vt)   # the manager's own function table (no get_top_window slot: the default scan of the children runs)
        self.stack, self.anim, self.backs, self.closed, self.opened = [], set(anim), 0, [], []
        for name in stack: self.push(name)
        recs = [self.record(album='A', artist='B', title=f'T{i}', name=f'{i}.flac', path=f'/mnt/mmc/m/{i}.flac', rid=100 + i) for i in range(tracks)]
        for r in recs: self.present.add(self.read_cstr(self.word(r + O['REC_PATH'])))
        self.setword(pod.DATA['PDEQ_SHOWLIST'][0], self.new_deque(recs))
        self.setword(pod.DATA['G_CLASS_TYPE'][0], cls)
        self.u.mem_write(pod.DATA['SONGER_FLAG'][0], bytes([songer]))
        self.stock_songlist = True

    def push(self, name):
        w = self.alloc(0x40); self.u.mem_write(w, bytes(0x40))
        self.setword(w + O['WIDGET_NAME'], self.cstr(name)); self.u.mem_write(w + 0x24, struct.pack('<H', 0xd))
        self.stack.append((name, w)); self.sync()

    def sync(self):
        if self.stack: self.kids(self.wmw, [w for _, w in self.stack])
        else: self.setword(self.wmw + 0x58, 0)

    def names_(self): return [n for n, _ in self.stack]

    def top(self): return self.stack[-1] if self.stack else None

    def close(self, entry):
        self.closed.append(entry[0])
        if entry[0] not in self.anim: self.stack.remove(entry); self.sync()

    def finish(self):
        self.stack = [e for e in self.stack if e[0] not in self.anim or e[0] not in self.closed]; self.sync()

    def _hook(self, u, address, size, _):
        name = self.handlers.get(address)
        if name not in self.MOCK: return super()._hook(u, address, size, _)
        a0 = u.reg_read(UC_MIPS_REG_A0)
        ret = 0
        if name == 'window_manager': ret = self.wmw
        elif name == 'navigator_window_is_exist': ret = int(self.read_cstr(a0) in self.names_())
        elif name == 'navigator_back':
            self.backs += 1
            if self.top(): self.close(self.top())
        elif name == 'window_close':
            ent = [e for e in self.stack if e[1] == a0]
            if ent: self.close(ent[0])
        else:   # the navigator opens a page: a new window on top; the harness records the queue and index
            page = self.read_cstr(a0)
            self.opened.append(page)
            super()._hook(u, address, size, _)
            self.push(page)
            return
        u.reg_write(UC_MIPS_REG_V0, ret); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))


def stack_tests(expect):
    """The stock "play from here" loop (row handler @0x52569c, loop @0x525904) against the window stack, with our pages."""
    play = lambda m: m.call(PSYMS['pod_open_player'], a0=m.word(pod.DATA['PDEQ_SHOWLIST'][0]), a1=0, a2=O['CLASS_ALBUM_TRACKS'], count=60000000)
    pages = ['home_page', 'm1plus_menu', 'playing_page', 'm1plus_cover', 'albuminfo_page']
    mm = StackMachine(pages)
    expect(mm.call(pod.FUNCTIONS['window_manager_get_top_window'][2], a0=mm.wmw, count=100000) == mm.top()[1],
           'the model runs demo\'s own window_manager_get_top_window: it finds the topmost visible window')
    for label in ('Now Playing',):
        m = StackMachine(pages); play(m)
        expect(m.names_() == ['home_page', 'm1plus_menu', 'playing_page'] and m.backs == 2 and m.closed.count('playing_page') == 1
               and m.opened == ['playing_page'] and m.played and len(m.played[0]) == 4,
               f'{label} with a Now Playing under the pages: the pages above it are popped, the old Now Playing closed, a new one opened over the menu ({m.names_()}, {m.backs} back)')
        expect(m.top()[0] == 'playing_page' and 'start_player' not in m.names(), f'{label}: the player is started by the new Now Playing\'s init, not here')
        m = StackMachine(['home_page', 'm1plus_menu', 'm1plus_albums', 'albuminfo_page']); play(m)
        expect(m.names_() == ['home_page', 'm1plus_menu', 'm1plus_albums', 'albuminfo_page', 'playing_page'] and m.backs == 0 and not m.closed,
               f'{label} with no Now Playing in the stack: nothing is popped, the page opens over the album page ({m.names_()})')
        m = StackMachine(pages, songer=0); play(m)
        expect(m.names_() == pages + ['playing_page'] and m.backs == 0,
               f'{label} with songerinfoflag clear: the stock handler does not pop either, the page opens over the old one ({m.names_()})')
        m = StackMachine(['playing_page', 'home_page', 'm1plus_menu', 'albuminfo_page']); play(m)
        expect(m.names_() == ['playing_page', 'home_page', 'playing_page'] and m.backs == 2,
               f'{label}: the pop stops at home_page ({m.names_()})')
    # a page with a close animation would never leave: stock's loop would spin; ours stops at POP_MAX and opens anyway
    m = StackMachine(['home_page', 'playing_page', 'slide_page', 'albuminfo_page'], anim={'slide_page'}); play(m)
    expect(m.backs == O['POP_MAX'] and m.names_()[-1] == 'playing_page' and 'slide_page' in m.names_(),
           f'a page still on screen after navigator_back (a close animation) cannot spin the loop: {m.backs} calls, then it opens ({m.names_()})')
    # none of the library or pod pages has a close animation (only the settings windows slide): every stock navigator_back above is synchronous
    import awtk_ui
    raw = os.path.join(WORK, 'rootfs', 'release/assets/default/raw/ui')
    bad = []
    for f in sorted(os.listdir(raw)):
        if f.endswith('.bin'):
            root = awtk_ui.parse(open(os.path.join(raw, f), 'rb').read())
            if any('anim' in k for k, _ in root.props): bad.append(f)
    expect(len(os.listdir(raw)) > 20 and bad == ['kb_default_t9ext.bin', 'screensaver_page.bin'],
           f'no library, Cover Flow, menu or Now Playing page has an open/close animation; only the keyboard and the lock screen (neither in the pop path) slide ({bad})')


def tone_cache_tests(expect):
    """The tone cache (patch/common.c): lookups, the least recently used entry goes first, bounds."""
    m = Machine()
    out = m.alloc(4)
    get = lambda k: (m.call(PSYMS['pod_tone_get'], a0=k, a1=out, count=100000), m.word(out))[0] and m.word(out)
    put = lambda k, t: m.call(PSYMS['pod_tone_put'], a0=k, a1=t, count=100000)
    n = O['TONE_CACHE_N']
    expect(n == 64 and get(5) == 0, 'the cache holds 64 tones; empty at start')
    for k in range(1, n + 1): put(k, 0xff000000 | k)
    expect(all(get(k) == 0xff000000 | k for k in range(1, n + 1)), 'every one of 64 keys is found')
    put(n + 1, 0xff0000aa)
    expect(not get(1) and get(2) and get(n + 1) == 0xff0000aa, 'the 65th evicts the least recently used (key 1)')
    put(n + 2, 0xff0000bb)
    expect(not get(3) and get(2) == 0xff000002, 'a looked-up entry (key 2) is younger: the next eviction takes key 3')
    put(2, 0xff0000cc)
    expect(get(2) == 0xff0000cc and get(4) == 0xff000004, 'the same key again replaces in place, evicting nothing')
    put(0, 0xff0000dd)
    expect(not get(0) and get(4), 'key 0 is never stored or found')
    expect(sum(1 for k in range(0, 200) if get(k)) == n, 'never more than 64 entries')
    expect(len(range(n)) * 12 <= 768, 'a tone entry is 12 bytes: 768 bytes of .scratch')


def cover_flow_tests(expect):
    # the artist's Cover Flow starts on its first album; the main one keeps its last album
    m = artists_machine(); m.load_image = 0; m.stock_songlist = True
    m.call(PSYMS['artists_open'], count=5000000)
    artists_tap(m, 0)
    expect(shelf_value(m) == 0,
           "the artist's Cover Flow starts on its first (leftmost) album, not the stock slide_menu's item 1")
    expect(('widget_set_text_utf8', m.widgets['label_album'], 'Bitches Brew') in m.calls
           and ('widget_set_text_utf8', m.widgets['label_artist'], 'Miles Davis') in m.calls, 'and its captions are set')
    m.tap(O['CF_CX'], count=60000000)
    expect(('navigator_to_with_context', 'albuminfo_page', O['CLASS_ARTIST_ALBUMS'], 0) in m.calls,
           "a tap on that album opens the stock album page with the artist page's class")
    # one album: the captions are there as soon as the page opens
    m = artists_machine(); m.call(PSYMS['artists_open'], count=5000000)
    artists_tap(m, 1)
    expect(('widget_set_text_utf8', m.widgets['label_album'], 'Pastel Blues') in m.calls
           and ('widget_set_text_utf8', m.widgets['label_artist'], 'Nina Simone') in m.calls and shelf_value(m) == 0,
           'an artist with one album shows its captions on open')
    for last in (0, 2):
        m = cover_machine(albums=3)
        key = fnv(fnv(O['FNV_SEED'], f'Artist {last}'), f'Album {last}') or 1
        m.fs['/mnt/mmc/.m1plus/coverflow-position'] = b'%08x\n' % key
        m.call(PSYMS['coverflow_open'], count=5000000)
        expect(shelf_value(m) == last
               and ('widget_set_text_utf8', m.widgets['label_album'], f'Album {last}') in m.calls,
               f'the main Cover Flow reopens on its last album ({last})')
    m = cover_machine(albums=1); m.call(PSYMS['coverflow_open'], count=5000000)
    expect(('widget_set_text_utf8', m.widgets['label_album'], 'Album 0') in m.calls, 'a library with one album shows its captions on open')
    tree = awtk_ui.parse(open(os.path.join(WORK, 'rootfs', 'release/assets/default/raw/ui/m1plus_cover.bin'), 'rb').read())
    expect('view_tracks' not in [x.name for x in tree.walk()], 'the Cover Flow asset has no track list view any more')



def run(ctx):
    stack_tests(ctx.expect)
    tone_cache_tests(ctx.expect)
    cover_flow_tests(ctx.expect)
