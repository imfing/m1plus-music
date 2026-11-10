"""Shared by the payload tests (test/pod/*.py): the Unicorn machine that runs the real compiled
payload with the stock functions and libc it calls mocked, the widget-tree hit testing that runs
demo's own widget_find_target, the machine factories and the host render of the depth renderer.
Modelled on q2-pod's test/patch.py.

Requires unicorn (venv) and a workdir patched by tools/pod.py (its podbuild/manifest.json).
test/patch.py calls init(WORKDIR) first, then loads the feature modules, which star-import this one.
"""
import importlib.util, json, os, re, struct, sys, unicodedata
from unicorn import Uc, UC_ARCH_MIPS, UC_MODE_MIPS32, UC_MODE_LITTLE_ENDIAN, UC_HOOK_CODE, UC_HOOK_BLOCK, UC_HOOK_INTR
from unicorn.mips_const import (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3,
                                UC_MIPS_REG_V0, UC_MIPS_REG_SP, UC_MIPS_REG_RA, UC_MIPS_REG_T9, UC_MIPS_REG_PC, UC_MIPS_REG_GP, UC_MIPS_REG_F0,
                                UC_MIPS_REG_CP0_STATUS as _STATUS, UC_MIPS_REG_0 as UC_MIPS_REG_0)

PERF = os.environ.get('M1_PERF') == '1'   # cost measurement and stress-scale checks; off by default (make test PERF=1; dev/check/accept always set it)
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOOLS = os.path.join(ROOT, 'tools')
sys.path.insert(0, TOOLS)
import cdefs  # noqa: E402
import paths  # noqa: E402
import pod  # noqa: E402
import pod_i18n  # noqa: E402
import pod_pages  # noqa: E402
import pod_ui  # noqa: E402
import awtk_ui  # noqa: E402

WORK = DEMO = BUILD = MANIFEST = PSYMS = None   # set by init()
HOME_CLICK_RESUME = pod.HOME_CLICK + 12   # trampoline resumes stock here
RET = 0x00ff0000     # sentinel return address: emulation stops when PC lands here
STACK = 0x7ffe0000
SCRATCH = 0x10000000
HEAP = 0x40000000
HEAP_SIZE = 0x4000000


def init(work):
    """Point the harness at a built tree (the payload's manifest and symbols)."""
    global WORK, DEMO, BUILD, MANIFEST, PSYMS
    WORK = work
    DEMO = os.path.join(WORK, 'rootfs', pod.DEMO)
    BUILD = os.path.join(WORK, 'podbuild')
    MANIFEST = json.load(open(os.path.join(BUILD, 'manifest.json')))
    import workflow, build
    final = workflow.read(os.path.join(work, 'build.json'))
    if final.get('sources') != workflow.source_key() or final.get('demo_sha256') != workflow.sha(DEMO) \
            or final.get('elf_sha256') != workflow.sha(os.path.join(BUILD, 'patch.elf')):
        raise SystemExit('stale or modified test tree; rebuild with make test or make dev')
    build.TAG = pod.TAG = final['tag']
    PSYMS = pod.symbols_elf(os.path.join(BUILD, 'patch.elf'))


def sibling(name):
    """test/pod/<name>.py (its machines and helpers) as test/patch.py loaded it, or loaded here when the caller runs alone."""
    key = f'podtest_{name}'
    if key not in sys.modules:
        spec = importlib.util.spec_from_file_location(key, os.path.join(os.path.dirname(os.path.abspath(__file__)), name + '.py'))
        mod = importlib.util.module_from_spec(spec); sys.modules[key] = mod; spec.loader.exec_module(mod)
    return sys.modules[key]


def jpeg_header(side):
    """The first bytes of a JPEG of side x side (SOI, JFIF, a baseline SOF0): all the payload's size check reads."""
    return b'\xff\xd8' + b'\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00' + b'\xff\xc0\x00\x11\x08' + struct.pack('>HH', side, side) + b'\x03\x01\x22\x00\x02\x11\x01\x03\x11\x01' + bytes(64)


def tr_of(loc):
    """key -> our text for key in loc's table, as read_cstr returns it (the UTF-8 bytes as latin-1)."""
    t = pod_i18n.table_for(loc)
    return lambda key: pod_i18n.TEXT[key][t].encode('utf-8').decode('latin-1')


def asset_path(n): return os.path.join(WORK, 'rootfs', 'release', 'assets', 'default', 'raw', 'images', 'xx', n + '.png')


def asset_image(n):
    """The built image images/xx/<n>.png as RGBA."""
    from PIL import Image
    return Image.open(asset_path(n)).convert('RGBA')


def same_pixels(a, b):
    """Two PNGs (path, bytes or PIL image) hold the same RGBA pixels. Compressed bytes differ between zlib builds (macOS wheel vs Linux), pixels do not."""
    import io
    from PIL import Image
    def load(x):
        if isinstance(x, Image.Image): return x.convert('RGBA')
        return Image.open(io.BytesIO(x) if isinstance(x, bytes) else x).convert('RGBA')
    a, b = load(a), load(b)
    return a.size == b.size and a.tobytes() == b.tobytes()


def lum(c):
    """WCAG relative luminance of an (r, g, b) colour, 0..255 a channel, or of '#rrggbb'."""
    if isinstance(c, str): c = tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))
    f = lambda v: v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(c[0] / 255) + 0.7152 * f(c[1] / 255) + 0.0722 * f(c[2] / 255)


def contrast(a, b):
    """WCAG contrast ratio of two colours (either order)."""
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)



PINYIN_INITIAL = {'周': 'z', '杰': 'j', '伦': 'l', '孙': 's', '燕': 'y', '姿': 'z', '陈': 'c', '奕': 'y', '迅': 'x', '王': 'w', '菲': 'f', '米': 'm', '津': 'j', '玄': 'x', '師': 's'}   # (the stock table's, for the characters the tests use)


def kana_initial(c):
    """The Hepburn initial of a hiragana / katakana character (independently of the payload's table: from the Unicode name), else None."""
    try: nm = unicodedata.name(c)
    except ValueError: return None
    m = re.match(r'(?:HIRAGANA|KATAKANA) LETTER (?:SMALL )?([A-Z]+)$', nm)
    if not m or not ('\u3041' <= c <= '\u3096' or '\u30a1' <= c <= '\u30fa'): return None
    syl = m.group(1)
    return {'TI': 'C', 'DI': 'J', 'ZI': 'J', 'HU': 'F', 'DU': 'Z', 'TU': 'T', 'WI': 'I', 'WE': 'E', 'WO': 'O', 'VA': 'V', 'VI': 'V', 'VE': 'V', 'VO': 'V'}.get(syl, syl[0])


LATIN_NO_DECOMPOSITION = dict(zip('ßæÆœŒøØðÐþÞłŁđĐıħĦŧŦŋŊĸĳĲŀĿŉſ', 'saaooooddttllddihhttnnkiilln' + 's'))   # (letters with no Unicode decomposition: ß ae oe o d th l d dotless-i h t eng kra ij l n long-s)


def latin_initial(c):
    """The base letter of a Latin-1 Supplement / Latin Extended-A letter (U+00C0..U+017F), from its Unicode decomposition, else None (× and ÷ are symbols)."""
    if not '\u00c0' <= c <= '\u017f': return None
    if c in LATIN_NO_DECOMPOSITION: return LATIN_NO_DECOMPOSITION[c]
    d = unicodedata.normalize('NFD', c)
    return d[0].lower() if len(d) > 1 and d[0].isascii() and d[0].isalpha() else None


NAME_PUNCT = frozenset(c for c in map(chr, range(0x21, 0x7f)) if not c.isalnum()) | set('\u00a1\u00bf\u00ab\u00bb\u2018\u2019\u201a\u201c\u201d\u201e\u2039\u203a\u3008\u3009\u300a\u300b\u300c\u300d\u300e\u300f\u3010\u3011\uff08\uff09\uff3b\uff3d\uff5b\uff5d\uff02\uff07')   # (the leading punctuation the name order skips)


def name_sort_key(name):
    """The library name order, independently written: leading white space and a leading "The " dropped, a CJK character
    as its pinyin initial and a kana as its Hepburn initial, then per position a digit run (by value) before a symbol
    (any non-ASCII character left, such as Hangul, Cyrillic, × or a letter outside Latin-1 / Latin Extended-A, is one); an accented
    Latin letter is its base letter (ß s, æ a, ø o ...) before a letter (ASCII case
    folded); a shorter key that is a prefix comes first."""
    s = name.lstrip(' \t\n\r\v\f')
    t = s
    while t:   # a leading run of punctuation (white space between) is skipped when something else follows it
        t = t.lstrip(' \t\n\r\v\f')
        if t and t[0] in NAME_PUNCT: t = t[1:]
        else: break
    if t: s = t
    if len(s) > 4 and s[:4].lower() == 'the ': s = s[4:]
    s = ''.join(PINYIN_INITIAL.get(c) or kana_initial(c) or latin_initial(c) or c for c in s)
    key = []
    for tok in re.findall(r'\d+|.', s, re.S):
        if tok.isascii() and tok.isdigit(): key.append((0, int(tok)))
        else:
            c = tok.lower() if tok.isascii() else tok
            key.append((2 if 'a' <= c <= 'z' else 1, c))
    return key

class Ctx:
    """What a feature module's run(ctx) gets: the entry page, the built cover asset, and expect()."""
    def __init__(self, work):
        self.work, self.page = work, pod_pages.PAGES[0]
        self.cover_asset = os.path.join(work, 'rootfs', 'release/assets/default/raw/ui/m1plus_cover.bin')
        self.passed = self.failed = 0

    def expect(self, cond, msg):
        if cond: self.passed += 1
        else: self.failed += 1; print('  FAIL:', msg)


O = cdefs.defines(os.path.join(ROOT, 'patch', 'offsets.inc'))   # the constants the payload is built with, so the mocks cannot drift from it
# Cover Flow's page layout as tools/pod_ui.py builds ui/m1plus_cover.bin
CF_FRAME_Y, CF_ALBUM_Y, CF_ALBUM_H, CF_ARTIST_Y, CF_ARTIST_H = pod_ui.cover_layout()


def art_file(key):
    """The thumbnail cache file of an album key: r<key>-168.jpg (the size is in the name, the letter the sampling: patch/covercache.c cc_path)."""
    return f'/mnt/mmc/.m1plus/covers/r{key:08x}-{O["ART_SIZE"]}.jpg'
REC_SIZE = 0x58


_ARG_REGS = (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3, UC_MIPS_REG_SP)


class Traps(dict):
    """address -> name, with a code hook at each address added (one per address, however many tables hold it):
    only the mocked and watched instructions call back into Python, not every instruction."""
    def __init__(self, m): super().__init__(); self.m = m; self.building = True   # building: Machine.__init__ is still adding, nothing is translated yet to flush

    def __setitem__(self, address, name):
        super().__setitem__(address, name)
        if address not in self.m.hooked:
            self.m.hooked.add(address)
            self.m.u.hook_add(UC_HOOK_CODE, lambda u, a, s, d: self.m._hook(u, a, s, d), begin=address, end=address)
            if not self.building and hasattr(self.m.u, 'ctl_flush_tb'): self.m.u.ctl_flush_tb()

    def update(self, other):
        for k, v in dict(other).items(): self[k] = v


_IMAGES = {}


def _demo_image():
    """(the built demo's bytes, its LOAD segments as (vaddr, file offset, file size, memory size)), read once per path: every Machine loads the same immutable image."""
    if DEMO not in _IMAGES:
        data = open(DEMO, 'rb').read()
        _IMAGES[DEMO] = data, [(v, o, f, m) for _, (t, o, v, _, f, m, _, _) in pod.segments(data) if t == 1]
    return _IMAGES[DEMO]


class Machine:
    """demo's LOAD segments and the payload, with every stock call and libc call trapped."""

    def __init__(self):
        self.u = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN)
        self.data, loads = _demo_image()
        for v, o, f, m in loads:
            start = v & ~0xfff
            self.u.mem_map(start, ((v + m + 0xfff) & ~0xfff) - start)
            self.u.mem_write(v, self.data[o:o + f])
        self.u.mem_map(STACK & ~0xfffff, 0x200000)
        self.u.mem_map(SCRATCH, 0x100000)
        self.u.mem_map(HEAP, HEAP_SIZE)
        self.u.reg_write(_STATUS, self.u.reg_read(_STATUS) | 1 << 29 | 1 << 26)   # CU1 and FR: the payload is -mfp64 (patch/peq.c's doubles)
        self.u.mem_write(pod.DATA['BACKLIGHT_STATUS'][0], b'\x01')
        self.next = SCRATCH
        self.heap = HEAP
        self.calls = []
        self.py_log = []            # the engine's calls over the machine's life (call() clears calls): im_open_decoder, im_close_decoder, py_lemma_id (char), py_splids (char)
        self.strings = {}           # the language's table for the mocked locale_info_tr: key -> text (none: English, the key itself)
        self.bound = {}             # (widget, event) -> (handler, ctx): the latest widget_on, whatever call it was in
        self.present = {'/mnt/data/m1plus'}   # paths access() finds (the settings folder exists)
        self.files = {}             # path -> size, for fopen/ftell
        self.window = 0x20001000    # window_open's result (0 = failure)
        self.windows = {}           # ... for the windows named here (a page that opens another: one of them can fail)
        self.widgets = {}           # name -> handle; lookups miss if absent
        self.lookups = {}            # (parent handle, name) -> handle: a lookup below a widget (rows each have a pod_hair); else self.widgets answers
        self.props = {}             # (handle, prop) -> int, for widget_get_prop_int
        self.children = {}          # parent handle -> [child handles]
        self.types = {}             # handle -> widget type string (widget_get_type)
        self.deques = {}            # handle -> list of record addresses
        self.deque_reads = {}       # handle -> deque_at calls on it
        self.showlist = []          # what loadLocalClassList leaves in *pdeq_showlist
        self.playlists = []         # the playlist rows loadLocalClassList(0xf00b) leaves in *pdeq_playlist
        self.playlist_songs = {}    # playlist id -> its song rows (loadLocalClassList(0xff13) with classinfo[1] = the id)
        self.genre_songs = {}       # (genre name, Unknown Genre byte) -> its song rows (loadLocalClassList(0xff09) with classinfo[0], classinfo + 0x30d, classinfo + 0xc as the stock row tap leaves them)
        self.create_ret = 5         # createPlayListItem's result (-1 full, -2 exists)
        self.pl_names = set()       # playlist names createPlayListItem answers -2 for (a test sets them)
        self.fav_rows = []          # myfav as stock has it, in insertion order: (name, path, title); checkFavExist / addMyFav / deleteMusicFromFav and loadLocalClassList(0xf00a) read them
        self.pl_rows = []           # the playlist table's song rows addPlayList was given: (row id, playlist id, path, title); checkPlayListExist / getPlayListMaxId read them
        self.pl_created = []        # (name, id) of the playlists createPlayListItem made (a result >= 0)
        self.clobber = False        # createPlayListItem leaves the browsing class, classinfo[0..1] and the navigation title changed (a test of "put back")
        self.album_artists = []     # the artists list while artist_type == 1 (the stock page's album-artist switch)
        self.class_lists = {}       # ... per class, where a test sets one (0xf004: the artists)
        self.tracklist = []         # what loadSongList leaves there
        self.artist_albums = {}     # artist name -> its album rows (loadAlbumList 0xf004)
        self.artist_songs = {}      # artist name -> all its song rows (loadLocalClassList(0xff11) after loadAlbumdetailList on the All songs row)
        self.composer_songs = {}    # composer name -> all its song rows (0xff14 after loadAlbumdetailList(0xff02) on the composer's All songs row)
        self.free_mb = 1024
        self.thread_ok = True
        self.thread = None          # (start routine, argument) of the last pthread_create
        self.curl, self.curl_site, self.curl_last = {}, None, {}   # libcurl (patch/pcnet.c): handle -> options set; the scripted server; handle -> what the last request returned
        self.confirm_yes = False    # the answer of the stock confirm dialog (dialog/confirminfo_dialog)
        self.album_cover = 0        # toolsGetAlbumCover's result
        self.listing, self.open_dirs = {}, {}   # opendir / readdir (patch/covercache.c art_folder): directory path -> [(name, d_type)], open handle -> entries left
        self.dir_stop = {}          # directory path -> entries readdir serves before it returns NULL (the rest stay listed); opendir fails for ('opendir', path) in fail
        self.taglib_kind, self.taglib_data = None, None   # taglib_album_picture's result (2 JPEG, 1 PNG, 0 none; None: 2 when album_cover is set) and the picture it saves to /tmp/.tmp_picture (None: no file)
        self.extern_cover = 0
        self.durations = {}           # path -> seconds TagLib reads (patch/durations.c dur_probe); 0: the file opens but has no audio properties; a path not here: taglib_file_new fails
        self.tag_objs = {}          # taglib_file_new's handles -> path
        self.tag_len_fn = self.alloc(16)   # where the vtable's slot 3 (AudioProperties::length) points: trapped
        self.load_image = 1         # widget_load_image: 0 = success
        self.images = {}            # url -> (w, h, RGBA bytes) widget_load_image decodes when it succeeds
        self.parent = {}            # widget handle -> parent handle
        self.hooked = set()
        self.real_album = False     # patch/albumpage.c album_open: trapped (it returns -1, the stock page opens) unless a test runs it
        self.handlers = Traps(self)
        self.handlers[self.tag_len_fn] = 'taglib_length'
        self.handlers.update({a: n for n, (_, _, a) in pod.FUNCTIONS.items()})
        for name in pod.LIBC:       # the payload's libc stubs, trapped at their entry
            if f'pod_lib_{name}' in PSYMS:   # --gc-sections drops the ones it does not call
                self.handlers[PSYMS[f'pod_lib_{name}']] = name
        self.handlers.pop(pod.FUNCTIONS['widget_to_local'][2])   # stock's own, run for real: the payload and widget_find_target both call it
        self.handlers[HOME_CLICK_RESUME] = 'stock_resume'
        self.handlers[PSYMS['stock_backtoplayer_trampoline']] = 'on_backtoplayer_onclick'   # stock's Now Playing handler, reached through its hook's trampoline
        for sym, nm in (('stock_setmode_trampoline', 'stock_setmode'), ('stock_loadplaylist_trampoline', 'stock_loadplaylist')):   # the Shuffle hooks' way back into stock (patch/shuffle.c)
            if sym in PSYMS: self.handlers[PSYMS[sym]] = nm
        if 'album_open' in PSYMS: self.handlers[PSYMS['album_open']] = 'album_open'
        # Cover Flow's shelf commits and moves (noinline in patch/coverflow.c): ('set_value', album), ('set_offset', off)
        self.watch = Traps(self)
        self.watch.update({PSYMS[n]: n for n in ('set_value', 'set_offset') if n in PSYMS})
        self.handlers[pod.HOME_INIT + 12] = 'stock_init_resume'
        self.handlers[pod.TF_UPDATE] = 'tf_update_click'
        self.handlers[pod.PLAYLIST_IMPORT] = 'stock_playlist_import'   # the stock Playlists page's Import / Export click handlers
        self.handlers[pod.PLAYLIST_EXPORT] = 'stock_playlist_export'
        self.handlers[pod.GLYPH_CACHE_LOOKUP] = 'glyph_cache_lookup'   # the stb font's glyph path (patch/textgamma.c wraps it): mocked, test/pod/textgamma.py
        self.handlers[O['STB_GET_GLYPH']] = 'font_stb_get_glyph'
        # the Home guard's world (patch/home.c): flash/SD files, file descriptors, the window stack
        self.fs, self.fds, self.next_fd, self.fail = {}, {}, 3, set()
        self.dirs = {'/mnt/data', '/mnt/data/m1plus'}
        self.timers = []            # (callback, ms) of every timer_add
        self.timer_arg = {}         # callback -> the arg of its last timer_add
        self.timer_fail = False
        self.create_fail = set()    # widget constructors (view_create, ..) that return 0
        self.deque_fail = False     # _create_deque returns 0 (no memory for a list copy)
        self.wm, self.top_main, self.home_opened, self.init_ret = 0x22000000, 0, 1, 0
        self.handlers.building = self.watch.building = False   # (no code has run yet, so the hooks added so far need no translation flush)
        self._icount, self.limit, self.counting = 0, 0, False
        self._nested_contexts = []  # reusable CPU snapshots; active nested calls each hold their own
        self.bitmaps, self.free_blocks = {}, {}   # bitmap_create_ex's results; destroyed data blocks to reuse
        self.blits, self.texts, self.measures, self.glyphs, self.draw_oy = [], [], [], [], []
        self.fills, self.text_styles, self.cur_style, self.fill_color = [], [], '', 0 # canvas_fill_rect (colour, x, y, w, h); the style widget of each text
        self.destroyed, self.loads = 0, []   # bitmaps destroyed / images loaded, over the machine's life
        self.locked, self.load_into = 0, []  # the bitmap last locked for writing / (url, that bitmap) per image load: which bitmap a decode was for
        self.tm_buf = 0                     # the struct tm localtime answers with (patch/dailymix.c)
        self.sys = []               # syscalls the payload made itself (the cover worker's setpriority 4097, patch/covercache.c): (number, a0, a1, a2); answered 0
        self.u.hook_add(UC_HOOK_INTR, self._sys)
        if self.COUNT: self.count()

    def _sys(self, u, intno, _):
        if u.reg_read(UC_MIPS_REG_V0) != 4097: return   # (only setpriority: a test with its own syscall, test/pod/filetime.py, answers the rest)
        self.sys.append((4097,) + tuple(u.reg_read(r) for r in (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2)))
        u.reg_write(UC_MIPS_REG_A3, 0); u.reg_write(UC_MIPS_REG_V0, 0)

    def count(self):
        """Count instructions from now on (icount, and call()'s step limit): a block hook, which is most of the emulation time."""
        if not self.counting:
            self.u.hook_add(UC_HOOK_BLOCK, self._block); self.counting = True
            self.u.ctl_flush_tb()   # blocks translated before the hook would run without it
        return self

    @property
    def icount(self):
        """The instructions of the last call; reading it on a machine that does not count is an error, not 0."""
        assert self.counting, 'icount of a machine that does not count: m.count() first'
        return self._icount

    @icount.setter
    def icount(self, v): self._icount = v

    # ---------------- memory helpers ----------------
    def alloc(self, n):
        a = self.next; self.next = (self.next + n + 7) & ~7; return a

    reuse_heap = False        # a test that makes many short-lived blocks (the local search's scan) sets it: free() then gives a block back to a later malloc / calloc of the same size

    def malloc(self, n):
        rn = (n + 15) & ~15
        if self.reuse_heap and self.__dict__.setdefault('_free', {}).get(rn):
            return self._free[rn].pop()
        a = self.heap; self.heap = (self.heap + n + 15) & ~15
        assert self.heap < HEAP + HEAP_SIZE, 'emulated heap exhausted'
        if self.reuse_heap: self.__dict__.setdefault('_blocks', {})[a] = rn
        return a

    def cstr(self, s):
        a = self.alloc(len(s.encode()) + 1); self.u.mem_write(a, s.encode() + b'\0'); return a

    def read_cstr(self, a):
        out = b''
        while a:
            n = 256 - (a & 255)   # to the next 256-byte boundary: never past a page, so no byte is read that a byte-wise scan would not
            c = bytes(self.u.mem_read(a, n)); z = c.find(b'\0')
            if z >= 0: out += c[:z]; break
            out += c; a += n
        return out.decode('latin-1')

    def words_until_zero(self, a):
        """The 32-bit words from a up to the first zero one, read in chunks that never pass a 256-byte boundary (a word-by-word scan reads no further)."""
        out = []
        while True:
            n = max(4, (256 - (a & 255)) & ~3)
            ws = struct.unpack(f'<{n // 4}I', self.u.mem_read(a, n))
            z = ws.index(0) if 0 in ws else -1
            if z >= 0: return out + list(ws[:z])
            out += ws; a += n

    def word(self, a): return struct.unpack('<I', self.u.mem_read(a, 4))[0]
    def s32(self, a): return struct.unpack('<i', self.u.mem_read(a, 4))[0]
    def setword(self, a, v): self.u.mem_write(a, struct.pack('<I', v & 0xffffffff))

    def icon(self, name):
        """A fake widget whose +W_NAME word points at the name string (what the dispatcher reads)."""
        w = self.alloc(0x40); self.u.mem_write(w, bytes(0x40))
        self.u.mem_write(w + O['W_NAME'], struct.pack('<I', self.cstr(name)))
        return w

    def record(self, album='Album', artist='Artist', path='/mnt/mmc/a/1.flac', title='Track',
               name='1.flac', rid=1):
        r = self.alloc(REC_SIZE); self.u.mem_write(r, bytes(REC_SIZE))
        self.setword(r + O['REC_ID'], rid)
        for off, s in ((O['REC_PATH'], path), (O['REC_TITLE'], title), (O['REC_ALBUM'], album),
                       (O['REC_ARTIST'], artist), (O['REC_NAME'], name)):
            self.setword(r + off, self.cstr(s))
        self.setword(r + O['REC_TYPE'], 8)
        return r

    def play(self, tracks, pos):
        """The player on tracks[pos]: the play queue (the deque at PLAY_QUEUE) holds the given song records."""
        self.setword(pod.DATA['PLAY_QUEUE'][0], self.new_deque(tracks))
        self.play_pos = pos

    def all_songs(self, artist):
        r = self.record(album='All songs', artist=artist, path='', title='All songs', name='', rid=O['ID_ALL_SONGS'])
        self.setword(r + O['REC_PATH'], 0); self.setword(r + O['REC_TYPE'], 4)
        return r

    def artist_query(self):
        """loadLocalClassList(0xff11) as stock reads the record: the all-songs flag (+8) and the artist (+0x10d); 0xff14 (a composer's) the composer at +0x20d."""
        ci = pod.DATA['CLASSINFO'][0]
        if not self.u.mem_read(ci + O['CLASSINFO_ALL_SONGS'], 1)[0]: return []
        if self.word(ci) == O['CLASS_14']: return list(self.composer_songs.get(self.read_cstr(ci + O['CLASSINFO_ARTIST_14']), []))
        return list(self.artist_songs.get(self.read_cstr(ci + O['CLASSINFO_ARTIST']), []))

    CSTL_BASE = 0x77000000   # where install_libcstl maps the "library"
    pops = 0

    def install_libcstl(self, bound=True):
        """libcstl as the payload finds it (patch/shuffle.c cstl_pop_back): the real bytes of the stock library's text (the first 0x3c000 bytes: deque_size at CSTL_SIZE, deque_pop_back at CSTL_POP) mapped at
        CSTL_BASE, demo's GOT slot of deque_size bound to it (bound False: still the stub inside demo, as before the first call), and deque_pop_back trapped (cstl_pop_back models what the code does)."""
        slot = cdefs.defines(os.path.join(BUILD, 'stock.h'), ['GOT_DEQUE_SIZE'])['GOT_DEQUE_SIZE']
        lib = open(os.path.join(WORK, 'rootfs', pod.LIBCSTL), 'rb').read()
        if not hasattr(self, 'got_deque_size'):
            self.u.mem_map(self.CSTL_BASE, 0x3c000)
            self.u.mem_write(self.CSTL_BASE, lib[:0x3c000])
            self.handlers[self.CSTL_BASE + pod.CSTL_POP] = 'cstl_pop_back'
        self.got_deque_size = slot
        self.setword(slot, self.CSTL_BASE + pod.CSTL_SIZE if bound else 0x743590)

    def new_deque(self, items=()):
        h = self.alloc(8)
        self.deques[h] = list(items)
        return h

    def widget(self, name, **props):
        w = self.widgets.get(name) or self.alloc(0x80)
        self.widgets[name] = w
        for k, v in props.items(): self.props[(w, k)] = v
        return w

    # ---------------- the mocks ----------------
    def _block(self, u, address, size, _):
        self._icount += size >> 2
        if self._icount > self.limit: u.emu_stop()   # call()'s step limit, a block at a time

    def _hook(self, u, address, size, _):
        name = self.handlers.get(address)
        if not name:
            w = self.watch.get(address)   # a payload function of our own: recorded, then run for real
            if w: self.calls.append((w, struct.unpack('<i', struct.pack('<I', u.reg_read(UC_MIPS_REG_A0)))[0]))
            return
        a0, a1, a2, a3, sp = u.reg_read_batch(_ARG_REGS)
        stack = lambda i: self.word(sp + 16 + 4 * i)   # o32: arguments 4.. are on the stack
        ret = 0
        if name == 'atoi':
            s = self.read_cstr(a0); neg = s[:1] == '-'; dig = ''
            for c in s.lstrip('+-'):
                if c.isdigit(): dig += c
                else: break
            ret = (-1 if neg else 1) * int(dig) if dig else 0
            self.calls.append(('atoi', s))
        elif name == 'access':
            p = self.read_cstr(a0); ret = 0 if p in self.present or p in self.fs else -1
            self.calls.append(('access', p))
        elif name == '__xstat':   # a file's state, for the callers that keep a signature (the Home cache check: patch/homecover.c hc_dbsig): path -> [mtime, nsec, size] in self.db; anything else is missing
            p = self.read_cstr(a1); self.calls.append(('__xstat', p)); ret = 0xffffffff
            if p in self.db:
                self.u.mem_write(a2, bytes(144)); mt, ns, sz = self.db[p]
                self.setword(a2 + 0x40, mt); self.setword(a2 + 0x44, ns); self.setword(a2 + 0x30, sz); ret = 0
        elif name == 'album_open':   # patch/albumpage.c, trapped: the callers' tests (the Albums grid, Cover Flow, Artists, Recently Played) see the stock album page open; test/pod/albumpage.py runs it for real (real_album)
            if self.real_album: return
            self.calls.append(('album_open', a0, self.word(a1 + O['REC_ID']))); ret = -1
        elif name == 'window_open':
            nm = self.read_cstr(a0); self.calls.append(('window_open', nm)); ret = self.windows.get(nm, self.window)
        elif name == 'widget_get_window':   # the page window of a widget (a test sets page_window; none: the widget is in no window)
            ret = self.page_window
        elif name == 'widget_lookup':
            nm = self.read_cstr(a1); self.calls.append(('widget_lookup', nm))
            ret = self.lookups.get((a0, nm)) or self.widgets.get(nm, 0)
        elif name == 'widget_on':
            self.calls.append(('widget_on', a0, a1, a2, a3)); ret = 0 if a1 in self.widget_on_fail else 1
            if ret: self.bound[(a0, a1)] = (a2, a3)
        elif name == 'widget_set_text_utf8':
            self.calls.append(('widget_set_text_utf8', a0, self.read_cstr(a1))); ret = 0
        elif name == 'locale_info':   # a test's locale_info_t (country[3], language[3]), else en_US (patch/pcregion.c reads it)
            if not getattr(self, 'locale', 0):
                self.locale = self.alloc(8); self.u.mem_write(self.locale, b'US\0en\0\0\0')
            ret = self.locale
        elif name == 'locale_info_on':
            self.calls.append(('locale_info_on', a0, a1, a2, a3)); ret = 1
        elif name == 'font_manager':   # none unless a test gives one (patch/fontregion.c then does nothing)
            ret = getattr(self, 'fm', 0)
        elif name == 'font_manager_get_font':
            self.calls.append(('font_manager_get_font', a0, self.read_cstr(a1), a2)); ret = getattr(self, 'font', 0)
        elif name == 'font_manager_shrink_cache':
            self.calls.append(('font_manager_shrink_cache', a0, a1))
        elif name == 'locale_info_tr':   # the stock table lookup: the key itself when the table lacks it
            raw = self.tr(self.read_cstr(a1)).encode('latin-1')   # (the text as UTF-8 bytes; the key itself when the table lacks it)
            ret = self.alloc(len(raw) + 1); self.u.mem_write(ret, raw + b'\0')
        elif name == 'widget_set_tr_text':
            key = self.read_cstr(a1)
            self.calls.append(('widget_set_tr_text', a0, key)); self.calls.append(('widget_set_text_utf8', a0, self.tr(key))); ret = 0
        elif name == 'navigator_back':
            self.calls.append(('navigator_back',)); ret = 0
        elif name == 'navigator_close':   # (the page stays: a window's destroy event is the test's to deliver)
            self.calls.append(('navigator_close', self.read_cstr(a0))); ret = 0
        elif name == 'navigator_window_is_exist':   # the window names a test puts in self.windows (none by default)
            ret = int(self.read_cstr(a0) in getattr(self, 'windows', ()))
        elif name == 'on_backtoplayer_onclick':
            self.calls.append(('on_backtoplayer_onclick',)); ret = 0
        elif name == 'stock_resume':
            nm = self.read_cstr(self.word(a0 + O['W_NAME'])) if a0 else ''
            self.calls.append(('stock_resume', nm)); ret = 0x10
        # ---- Cover Flow: widgets
        elif name == 'widget_set_visible':
            self.props[(a0, 'visible')] = a1
            self.calls.append(('widget_set_visible', a0, a1))
        elif name == 'widget_get_visible':   # what widget_set_visible stored (a widget the test never hid or showed is visible)
            ret = int(self.props.get((a0, 'visible'), 1))
        elif name == 'widget_set_sensitive':
            self.props[(a0, 'sensitive')] = a1
            self.calls.append(('widget_set_sensitive', a0, a1))
        elif name == 'widget_set_opacity':
            self.props[(a0, 'opacity')] = a1 & 0xff
            self.calls.append(('widget_set_opacity', a0, a1 & 0xff))
        elif name == 'widget_set_state':
            self.calls.append(('widget_set_state', a0, self.read_cstr(a1)))
        elif name == 'widget_grab':
            self.calls.append(('widget_grab', a0, a1))
        elif name == 'widget_ungrab':
            self.calls.append(('widget_ungrab', a0, a1))
        elif name == 'widget_set_prop_int':
            self.props[(a0, self.read_cstr(a1))] = a2
            if a0 in self.live_scroll and self.read_cstr(a1) in ('virtual_h', 'yoffset'):   # a scroll_view struct: the setters' stores (virtual_h @0x7c, yoffset @0x84)
                self.setword(a0 + {'virtual_h': 0x7c, 'yoffset': 0x84}[self.read_cstr(a1)], a2)
            self.calls.append(('widget_set_prop_int', a0, self.read_cstr(a1), a2))
        elif name == 'widget_use_style':
            self.props[(a0, 'style')] = self.read_cstr(a1)
            self.calls.append(('widget_use_style', a0, self.read_cstr(a1)))
        elif name == 'widget_update_style':
            self.calls.append(('widget_update_style', a0))
        elif name in ('hscroll_label_set_only_parent_focus', 'hscroll_label_set_ellipses'):
            self.props[(a0, name)] = a1
        elif name == 'hscroll_label_create':
            w = self.alloc(0x80)
            self.children.setdefault(a0, []).append(w)
            self.rect(w, a1, a2, a3, stack(0))
            self.calls.append((name, w, a0)); ret = w
        elif name == 'widget_set_prop_str':
            self.props[(a0, self.read_cstr(a1))] = self.read_cstr(a2)
        elif name == 'widget_get_prop_str':
            ret = self.props.get((a0, self.read_cstr(a1)), a2)
        elif name == 'widget_get_prop_int':
            prop = self.read_cstr(a1)
            ret = self.props.get((a0, prop), a2) & 0xffffffff
        elif name == 'widget_count_children':
            ret = len(self.children.get(a0, []))
        elif name == 'widget_get_child':
            kids = self.children.get(a0, []); ret = kids[a1] if a1 < len(kids) else 0
        elif name == 'widget_get_type':
            ret = self.cstr(self.types.get(a0, 'widget'))
        elif name == 'widget_destroy_children':
            self.children[a0] = []; self.calls.append(('widget_destroy_children', a0))
        elif name == 'widget_invalidate_force':
            self.calls.append(('widget_invalidate_force', a0))
            if not hasattr(self, 'inval'): self.inval = []
            self.inval.append((a0, struct.unpack('<4i', u.mem_read(a1, 16)) if a1 else None))   # the rectangle it was given (widget coordinates), None: the whole widget
        elif name == 'widget_factory':
            ret = 0x21000000
        elif name == 'widget_factory_create_widget':
            kind = self.read_cstr(a1)
            w = self.alloc(0x80)
            self.children.setdefault(a2, []).append(w)
            self.rect(w, a3, stack(0), stack(1), stack(2))
            self.parent[w] = a2
            if kind == 'slide_menu' and self.slide_starts_at_1: self.props[(w, 'value')] = 1   # the stock constructor (@0x613970)
            self.calls.append((kind, w, stack(1), stack(2)))
            self.widgets.setdefault(kind, w)
            ret = w
        elif name in ('image_create', 'list_item_create',
                      'label_create', 'view_create'):
            if name in self.create_fail:
                self.calls.append((name, 0)); ret = 0
                u.reg_write(UC_MIPS_REG_V0, 0); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))
                return
            w = self.alloc(0x80)
            self.types[w] = {'image_create': 'image', 'label_create': 'label', 'view_create': 'view'}.get(name, name[:-7])
            self.children.setdefault(a0, []).append(w)
            self.rect(w, a1, a2, a3, stack(0))
            self.parent[w] = a0
            self.calls.append((name, w))
            ret = w
        elif name == 'widget_set_prop_bool':
            self.props[(a0, self.read_cstr(a1))] = a2
            self.calls.append(('widget_set_prop_bool', a0, self.read_cstr(a1), a2))
        elif name == 'widget_set_name':
            nm = self.read_cstr(a1)
            self.props[(a0, 'name')] = nm; self.widgets[nm] = a0
            self.setword(a0 + O['W_NAME'], self.cstr(nm))
            self.calls.append(('widget_set_name', a0, nm))
        elif name == 'label_set_line_wrap':
            self.calls.append(('label_set_line_wrap', a0, a1))
        elif name == 'slide_indicator_set_max':
            self.calls.append(('slide_indicator_set_max', a0, a1))
        elif name == 'widget_set_style':   # (widget, name, value_t): kept in styled, the list SelectMachine keeps too; the colour is the uint32 at 8
            if not hasattr(self, 'styled'): self.styled = []
            self.styled.append((a0, self.read_cstr(a1), self.word(a2 + 8)))
        elif name == 'value_set_uint32':   # value_t's uint32 at 8, as the setters read it
            self.setword(a0 + 8, a1); ret = a0
        elif name == 'widget_destroy':
            self.calls.append(('widget_destroy', a0))
            for kids in self.children.values():
                if a0 in kids: kids.remove(a0)
        elif name == 'window_close':
            self.calls.append(('window_close', a0))
        elif name == 'widget_move':
            self.props[(a0, 'x')], self.props[(a0, 'y')] = a1, a2
            if self.mem_geometry: self.setword(a0, a1); self.setword(a0 + 4, a2)   # widget_t x, y @0, 4
            self.calls.append(('widget_move', a0, a1, a2))
        elif name == 'widget_restack':   # the menu lists keep their rows' children in page order: recorded as (row, index)
            self.calls.append(('widget_restack', a0, a1))
        elif name == 'get_battery_capacity':   # stock: the bucketed capacity, left in power_capacity as well (patch/battery.c); a test sets stock_cap
            ret = getattr(self, 'stock_cap', 40); self.setword(pod.DATA['POWER_CAPACITY'][0], ret)
            self.calls.append(('get_battery_capacity',))
        elif name == 'widget_set_need_relayout_children':
            self.calls.append(('widget_set_need_relayout_children', a0)); ret = 0
        elif name == 'widget_resize':
            self.props[(a0, 'w')], self.props[(a0, 'h')] = a1, a2
            if self.mem_geometry: self.setword(a0 + 8, a1); self.setword(a0 + 0xc, a2)   # w, h @8, 0xc
            self.calls.append(('widget_resize', a0, a1, a2))
        elif name == 'image_set_draw_type':
            self.calls.append(('image_set_draw_type', a0, a1))
        elif name == 'image_base_set_image':
            self.calls.append(('image_base_set_image', a0, self.read_cstr(a1)))
            self.props[(a0, 'image')] = self.cstr(self.read_cstr(a1))
        elif name == 'widget_load_image':
            url = self.read_cstr(a1)
            self.loads.append(url); self.load_into.append((url, self.locked))
            self.calls.append(('widget_load_image', url))
            ret = self.load_image
            img = self.images.get(url)
            if img and not ret:   # decode: bitmap_t w, h, format, data (RGBA8888, tightly packed)
                iw, ih, pix = img
                data = self.malloc(len(pix)); self.u.mem_write(data, pix)
                self.setword(a2, iw); self.setword(a2 + 4, ih); self.setword(a2 + 0x14, data)
                self.u.mem_write(a2 + O['BITMAP_FORMAT'], struct.pack('<H', O['BITMAP_RGBA8888']))
        elif name == 'widget_unload_image':
            self.calls.append(('widget_unload_image',))
        elif name == 'slide_menu_set_value':
            self.props[(a0, 'value')] = a1
            self.calls.append(('slide_menu_set_value', a1))
        elif name == 'timer_add':
            self.calls.append(('timer_add', a0, a2)); ret = 0 if self.timer_fail else 0x777
            if ret: self.timers.append((a0, a2))
            self.timer_arg[a0] = a1   # the ctx of its last timer_add (stock calls the callback with the timer_info_t, not this)
        elif name == 'timer_remove':
            self.calls.append(('timer_remove', a0)); ret = 0
        elif name == 'timer_modify':   # the page timer's new interval (patch/ipod.c ip_retime): recorded and applied to the last timer_add of that callback's slot
            self.calls.append(('timer_modify', a0, a1)); ret = 9 if self.timer_modify_fail else 0
            if not ret and self.timers: self.timers[-1] = (self.timers[-1][0], a1)
        # ---- Cover Flow: bitmaps and the canvas
        elif name == 'bitmap_create_ex':
            if not self.bitmap_ok:
                self.calls.append(('bitmap_create_ex', 0)); ret = 0
                u.reg_write(UC_MIPS_REG_V0, 0); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))
                return
            b = self.malloc(0x48); self.u.mem_write(b, bytes(0x48))
            pool = self.free_blocks.setdefault(a0 * a1 * 4, [])
            data = pool.pop() if pool else self.malloc(a0 * a1 * 4)
            self.setword(b, a0); self.setword(b + 4, a1); self.setword(b + 0x14, data); self.setword(b + 0x10, a2)
            self.u.mem_write(b + O['BITMAP_FORMAT'], struct.pack('<H', a3))
            self.bitmap = (b, data, a0, a1)
            self.bitmaps[b] = (data, a0, a1)
            self.calls.append(('bitmap_create_ex', a0, a1)); ret = b
        elif name == 'bitmap_destroy':
            self.destroyed += 1
            if a0 in self.bitmaps:
                data, bw, bh = self.bitmaps.pop(a0); self.free_blocks.setdefault(bw * bh * 4, []).append(data)
            self.calls.append(('bitmap_destroy', a0))
        elif name == 'bitmap_get_line_length':
            ret = self.word(a0) * 4
        elif name in ('bitmap_lock_buffer_for_read', 'bitmap_lock_buffer_for_write'):
            ret = self.word(a0 + 0x14)
            if name == 'bitmap_lock_buffer_for_write': self.locked = a0
            self.calls.append((name,))
        elif name == 'bitmap_unlock_buffer':
            self.calls.append(('bitmap_unlock_buffer',))
        elif name == 'canvas_draw_image':
            self.calls.append(('canvas_draw_image', a1))
            self.blits.append((a1, struct.unpack('<4i', self.u.mem_read(a2, 16)), struct.unpack('<4i', self.u.mem_read(a3, 16))))
            if a0 and a0 == self.oy_canvas: self.draw_oy.append(struct.unpack('<i', self.u.mem_read(a0 + O['CANVAS_OY'], 4))[0])   # the canvas origin each cover was drawn at
        # ---- the Albums grid: the canvas' text calls, wide-char titles, a navbar button
        elif name == 'widget_prepare_text_style':
            self.calls.append(('widget_prepare_text_style', a0))
            self.cur_style = next((n for n, h in self.widgets.items() if h == a0), '')
            if a1 and a1 == self.canvas_mem:   # the canvas takes the widget's font and size (canvas_t @0x34 / @0xc)
                size = {'label_album': 22, 'label_artist': 18, 'label_row_title': 21, 'label_row_sub': 18}.get(next((n for n, h in self.widgets.items() if h == a0), ''), 16)
                self.setword(a1 + O['CANVAS_FONT'], self.font_mem)
                self.u.mem_write(a1 + O['CANVAS_FONT_SIZE'], struct.pack('<H', size))
        elif name == 'font_get_vmetrics':   # the 8 byte struct through the hidden pointer in $a0: ascent, descent, line gap
            self.u.mem_write(a0, struct.pack('<hhi', a2 - 4, -4, 2)); ret = a0
        elif name == 'glyph_cache_lookup':   # stock's cache of the stb font (test/pod/textgamma.py fills self.glyph_cache): 0 with the glyph_t copied to a3 on a hit, else a miss
            self.calls.append(('glyph_cache_lookup', a1, a2))
            hdr = self.glyph_cache.get((a1, a2))
            if hdr is None: ret = 9
            else: self.u.mem_write(a3, hdr); ret = 0
        elif name == 'font_stb_get_glyph':   # stock's rasterizer: a 4 x 3 mask of raw coverage, cached as glyph_cache_add does; 0 on success (a space: no bitmap)
            self.calls.append(('font_stb_get_glyph', a1, a2))
            if a1 == 0x20:
                hdr = struct.pack('<hhHHHBBI', 0, 0, 0, 0, 4, 0, 0, 0)
            else:
                w, h = 4, 3; raw = bytes((37 * i + 5 * a1 + a2) & 0xff for i in range(w * h))
                data = self.malloc(w * h); self.u.mem_write(data, raw); self.glyph_raw[(a1, a2)] = raw
                hdr = struct.pack('<hhHHHBBI', 0, -2, w, h, 5, 0, 0, data)
            self.glyph_cache[(a1, a2)] = hdr; self.u.mem_write(a3, hdr); ret = 0
        elif name == 'font_get_glyph':
            # a block of full alpha per char: 8 px advance (16 for CJK and the ellipsis), 6 (12) wide, 3/4 of the size high
            wide = a1 >= 0x2e80 or a1 == 0x2026
            self.glyphs.append((a1, a2))
            if a1 == 0xfffd: ret = 0x10   # RET_NOT_FOUND-like: the font has no such glyph
            else:
                w, h = (12 if wide else 6), a2 * 3 // 4
                data = self.malloc(w * h); self.u.mem_write(data, bytes([255]) * (w * h))
                self.u.mem_write(a3, struct.pack('<hhHHHBBI', 1, -(h - 2), w, h, 16 if wide else 8, 0, 0, data))
        elif name == 'canvas_measure_text':
            # a float in $f0: 8 px a char, 16 for CJK and the ellipsis
            chars = struct.unpack(f'<{a2}I', self.u.mem_read(a1, 4 * a2)) if a2 else ()
            w = float(sum(16 if c >= 0x2e80 or c == 0x2026 else 8 for c in chars))
            u.reg_write(UC_MIPS_REG_F0, struct.unpack('<I', struct.pack('<f', w))[0])
            self.measures.append(a2)
            u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))
            return
        elif name == 'canvas_draw_text_in_rect':
            chars = struct.unpack(f'<{a2}I', self.u.mem_read(a1, 4 * a2)) if a2 else ()
            self.texts.append((''.join(map(chr, chars)), struct.unpack('<4i', self.u.mem_read(a3, 16))))
            self.text_styles.append(self.cur_style)
        elif name == 'canvas_set_fill_color':
            self.fill_color = a1
        elif name == 'canvas_fill_rect':
            self.fills.append((self.fill_color, a1, a2, a3, stack(0)))
        elif name == 'tk_utf8_to_utf16_ex':
            text = bytes(self.u.mem_read(a0, a1)).decode('utf-8', 'replace')[:a3 - 1]
            self.u.mem_write(a2, struct.pack(f'<{len(text) + 1}I', *map(ord, text), 0)); ret = a2
        elif name == 'button_create':
            if name in self.create_fail:
                self.calls.append((name, 0)); u.reg_write(UC_MIPS_REG_V0, 0); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))
                return
            w = self.alloc(0x80)
            self.children.setdefault(a0, []).append(w); self.parent[w] = a0
            self.rect(w, a1, a2, a3, stack(0)); self.types[w] = 'button'
            self.calls.append(('button_create', w, a0)); ret = w
        # ---- Cover Flow: the stock library
        elif name == 'loadLocalClassList':
            self.calls.append(('loadLocalClassList', a0))
            if a0 == O['CLASS_PLAYLISTS']:   # getAllPlayList, assigned to *pdeq_playlist
                self.setword(pod.DATA['PDEQ_PLAYLIST'][0], self.new_deque(self.playlists))
                u.reg_write(UC_MIPS_REG_V0, len(self.playlists)); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))
                return
            if a0 == O['CLASS_PLAYLIST_SONGS']:   # getMusicByPlayList(classinfo[1]), assigned to *pdeq_showlist
                items = self.playlist_songs.get(self.word(pod.DATA['CLASSINFO'][0] + 4), [])
                self.setword(pod.DATA['PDEQ_SHOWLIST'][0], self.new_deque(items))
                u.reg_write(UC_MIPS_REG_V0, len(items)); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))
                return
            if a0 == O['CLASS_GENRE_SONGS']:   # getMusicByGenre(classinfo + 0x30d), or every song of an unknown genre; only when classinfo[0] is the class, as the stock row tap leaves it
                ci = pod.DATA['CLASSINFO'][0]
                key = (self.read_cstr(ci + O['CLASSINFO_GENRE']), self.u.mem_read(ci + O['CLASSINFO_GENRE_UNKNOWN'], 1)[0])
                items = self.genre_songs.get(key, []) if self.word(ci) == O['CLASS_GENRE_SONGS'] else []
                self.setword(pod.DATA['PDEQ_SHOWLIST'][0], self.new_deque(items))
                u.reg_write(UC_MIPS_REG_V0, len(items)); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))
                return
            if a0 in (O['CLASS_ARTIST_SONGS'], O['CLASS_14']):   # getMusicByAlbumAndAlbumSonger / AndComposer: from the browsing record alone (all-songs flag +8, artist +0x10d / composer +0x20d)
                items = self.artist_query()
                self.setword(pod.DATA['PDEQ_SHOWLIST'][0], self.new_deque(items))
                u.reg_write(UC_MIPS_REG_V0, len(items)); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))
                return
            if a0 == O['CLASS_FAV'] and self.fav_rows:   # getAllFav: the query filter's two answers (payload.md hook 6): music only, or with pc_saved_scope the episodes, the last saved first
                scope = self.u.mem_read(PSYMS['pc_saved_scope'], 1)[0]; self.calls.append(('fav_query', scope))
                rows = [r for r in self.fav_rows if r[1].lower().startswith('/mnt/mmc/podcasts/') == bool(scope)]
                items = [self.record(path=p, name=n, title=t) for n, p, t in (rows[::-1] if scope else rows)]
                self.setword(pod.DATA['PDEQ_SHOWLIST'][0], self.new_deque(items))
                u.reg_write(UC_MIPS_REG_V0, len(items)); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))
                return
            items = self.class_lists.get(a0, self.showlist)
            if a0 == O['CLASS_ARTISTS'] and self.album_artists:   # GetAllAlbumArtist when artist_type == 1
                items = self.album_artists if self.word(pod.DATA['ARTIST_TYPE'][0]) == 1 else items
            self.setword(pod.DATA['PDEQ_SHOWLIST'][0], self.new_deque(items))
            ret = len(items)
        elif name == 'loadAlbumList':
            # loadAlbumList(0xf004, artist row): the artist's albums, then the "All songs" row
            # (id -2, type 4, the artist at REC_ARTIST) getAlbumByArtist always appends; class 0xff01
            artist = self.read_cstr(self.word(a1 + O['REC_TITLE'])) if a1 else ''
            self.calls.append(('loadAlbumList', a0, a1, artist))
            if a0 == O['CLASS_ALBUMS']:   # the stock Albums page: every album (class 0xf003), no artist
                items = self.class_lists.get(a0, self.showlist)
                self.setword(pod.DATA['PDEQ_SHOWLIST'][0], self.new_deque(items))
                self.setword(pod.DATA['CLASSINFO'][0], a0)
                u.reg_write(UC_MIPS_REG_V0, len(items)); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))
                return
            items = list(self.artist_albums.get(artist, []))
            if artist in self.artist_albums: items.append(self.all_songs(artist))
            self.setword(pod.DATA['PDEQ_SHOWLIST'][0], self.new_deque(items))
            self.u.mem_write(pod.DATA['CLASSINFO'][0], bytes(O['CLASSINFO_SIZE']))   # memset, as stock
            self.setword(pod.DATA['CLASSINFO'][0], O['CLASS_COMPOSER_ALBUMS'] if a0 == O['CLASS_COMPOSERS'] else O['CLASS_ARTIST_ALBUMS'])
            if a0 == O['CLASS_ARTISTS']: self.u.mem_write(pod.DATA['CLASSINFO'][0] + O['CLASSINFO_ARTIST'], artist.encode() + b'\0')
            if a0 == O['CLASS_COMPOSERS']: self.u.mem_write(pod.DATA['CLASSINFO'][0] + O['CLASSINFO_ARTIST_14'], artist.encode() + b'\0')   # (the composer's name at +0x20d, addresses.md)
            ret = len(items)
        elif name == 'loadAlbumdetailList':
            # loadAlbumdetailList(0xff01, album row POINTER): the all-songs flag (+8) and the album text (+0xd) into the record, class 0xff11, then that class's query
            self.calls.append(('loadAlbumdetailList', a0, a1))
            ci = pod.DATA['CLASSINFO'][0]
            self.u.mem_write(ci + O['CLASSINFO_ALL_SONGS'], bytes([1 if self.word(a1 + O['REC_ID']) == 0xfffffffe else 0]))
            self.u.mem_write(ci + O['CLASSINFO_ALBUM'], self.read_cstr(self.word(a1 + O['REC_ALBUM'])).encode() + b'\0')
            self.setword(ci, O['CLASS_14'] if a0 == O['CLASS_COMPOSER_ALBUMS'] else O['CLASS_ARTIST_SONGS'])   # (0xff02 -> 0xff14, 0xff01 -> 0xff11)
            items = self.artist_query()
            self.setword(pod.DATA['PDEQ_SHOWLIST'][0], self.new_deque(items))
            ret = len(items)
        elif name == 'toolsQueryDbTable':
            # `select * from songtable where fileurl in ('a','b')` (the Daily Mix's own query, payload dm_rows): clears *tools_pdeq_directory, then the song row callback fills it
            # with the library's rows (class_lists[0xf001], else the shown list) that match, in reverse library order (the database's order is not the mix's)
            sql = self.read_cstr(a1)
            self.calls.append(('toolsQueryDbTable', self.read_cstr(a0), sql, a2, a3))
            self.__dict__.setdefault('queries', []).append(sql)   # (every query of the machine's life, which self.calls loses when a test clears it)
            m_ = re.fullmatch(r"select \* from songtable where fileurl in \((.*)\)", sql)
            a_ = re.fullmatch(re.escape(pod.ALBUM_HEAD) + r" where album='((?:[^']|'')*)' COLLATE NOCASE" + re.escape(pod.ALBUM_GROUP), sql) if a2 == 0x4e93c8 else None   # one album's record (payload cc_album_rep_key): getAllAlbum's statement filtered to a name, so the album list's own record of that name (class_lists[0xf003]), ASCII case folded
            album_sql = sql == pod.ALBUM_SQL and a2 == 0x4e93c8   # getAllAlbum's statement with stock's album row callback (payload cc_cmap_build): one record per album (class_lists[0xf003]), the empty-album group skipped as the callback does
            if (album_sql or a_) and self.__dict__.get('album_query_fails'):
                ret = -1
            elif not m_ and not a_ and not album_sql:
                ret = -1
            else:
                if album_sql:
                    rows = [r for r in self.class_lists.get(O['CLASS_ALBUMS'], []) if self.read_cstr(self.word(r + O['REC_ALBUM']))]
                elif a_:
                    album = a_.group(1).replace("''", "'")
                    ascii_lower = lambda t: ''.join(c.lower() if c.isascii() else c for c in t)
                    rows = [r for r in self.class_lists.get(O['CLASS_ALBUMS'], []) if self.read_cstr(self.word(r + O['REC_ALBUM'])) and ascii_lower(self.read_cstr(self.word(r + O['REC_ALBUM']))) == ascii_lower(album)][:1]
                else:
                    wanted = {p.replace("''", "'") for p in re.findall(r"'((?:[^']|'')*)'", m_.group(1))}
                    rows = [r for r in reversed(self.class_lists.get(0xf001, self.showlist)) if self.read_cstr(self.word(r + O['REC_PATH'])) in wanted]
                tmp = pod.DATA['PDEQ_TOOLS_TMP'][0]
                if not self.word(tmp): self.setword(tmp, self.new_deque())
                self.deques[self.word(tmp)] = rows
                ret = len(rows)
        elif name == 'deque_clear':
            self.deques[a0] = []; self.calls.append(('deque_clear', a0))
        elif name == 'loadSongList':
            self.calls.append(('loadSongList', self.read_cstr(a1), a2, a3))
            if self.stock_songlist:   # as stock does (@0x4e2ce0): the shown list's songs, class set,
                ret, out = -1, []    # the first song with this file name and CUE start
                key = (self.read_cstr(a1), a2)
                for r in self.deques.get(self.word(pod.DATA['PDEQ_SHOWLIST'][0]), []):
                    if self.word(r + O['REC_TYPE']) != 8: continue
                    self.setword(r + O['REC_CLASS'], a3)
                    if getattr(self, 'copy_queue', False):   # the queue holds copies of the records, as loadSongList's deque_assign makes them
                        r2 = self.alloc(REC_SIZE); self.u.mem_write(r2, bytes(self.u.mem_read(r, REC_SIZE))); out.append(r2)
                        if ret < 0 and (self.read_cstr(self.word(r + O['REC_NAME'])), self.word(r + O['REC_CUE_START'])) == key: ret = len(out) - 1
                        continue
                    out.append(r)
                    if ret < 0 and (self.read_cstr(self.word(r + O['REC_NAME'])), self.word(r + O['REC_CUE_START'])) == key:
                        ret = len(out) - 1
                self.deques[a0] = out
            else:
                self.deques[a0] = list(self.tracklist)
                ret = 1
        elif name == 'navigator_to_with_context':
            ctx = self.read_cstr(a0)
            if ctx == 'albuminfo_page':   # the context is a value, not a pointer: class | row << 16 (@0x523d94)
                self.calls.append(('navigator_to_with_context', ctx, a1 & 0xffff, a1 >> 16))
                self.opened_album = (a1 & 0xffff, a1 >> 16, self.word(pod.DATA['PDEQ_SHOWLIST'][0]))
                ret = 0
                u.reg_write(UC_MIPS_REG_V0, ret); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))
                return
            if ctx == 'allmusic_page':   # the Songs page: the context is the class, a value; the playlist is in classinfo[1] and the title in nagvation_title
                self.calls.append(('navigator_to_with_context', ctx, a1, self.word(pod.DATA['CLASSINFO'][0] + 4), self.read_cstr(pod.DATA['NAV_TITLE'][0])))
                u.reg_write(UC_MIPS_REG_V0, 0); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))
                return
            if ctx in ('search_page', 'playlist_page'):   # the Songs page's Search (no context) and the stock playlist picker (a value: the add context)
                self.calls.append(('navigator_to_with_context', ctx, a1))
                u.reg_write(UC_MIPS_REG_V0, 0); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))
                return
            self.calls.append(('navigator_to_with_context', ctx, self.word(a1 + 4),
                               self.word(a1 + 8), self.word(a1 + 12)))
            if ctx == 'playing_page':   # the queue as start_player copies it, and the class of its songs
                q = list(self.deques.get(self.word(a1), []))
                self.played = (q, self.word(a1 + 4))
            elif ctx == 'dialog/msginfo_dialog':
                self.calls.append(('toast', self.read_cstr(a1 + 8), self.word(a1), self.word(a1 + 4)))
            elif ctx == 'dialog/confirminfo_dialog':   # modal: the button pressed is the result (0xa Yes, else No; confirm_answer: any other value)
                self.calls.append(('confirm', self.read_cstr(a1 + 8), self.word(a1)))
                text = self.read_cstr(a1 + 8)
                if getattr(self, 'on_confirm', None): self.on_confirm(self)   # a test runs code while the modal dialog is up (what the page's windows hold then)
                ret = self.confirm_answers[text] if text in self.confirm_answers else self.confirm_answer if self.confirm_answer is not None else O['CONFIRM_YES'] if self.confirm_yes else 0
        elif name == 'createPlayListItem':   # (the stock list, the name): the new id, -1 full, -2 exists
            self.calls.append(('createPlayListItem', self.read_cstr(a1), len(self.deques.get(a0, [])))); ret = -2 if self.read_cstr(a1) in self.pl_names else self.create_ret
            if ret >= 0: self.pl_created.append((self.read_cstr(a1), ret))
            if self.clobber:   # what the stock calls may leave behind: the browsing class, classinfo[0..1], the navigation title
                self.setword(pod.DATA['G_CLASS_TYPE'][0], 0xf00b); self.setword(pod.DATA['CLASSINFO'][0], 0xdead); self.setword(pod.DATA['CLASSINFO'][0] + 4, 77)
                self.u.mem_write(pod.DATA['NAV_TITLE'][0], b'clobbered\0')
        elif name == 'checkPlayListExist':   # (song record, playlist id): 1 = that path is already in that playlist
            path = self.read_cstr(self.word(a0 + O['REC_PATH'])); self.calls.append(('checkPlayListExist', path, a1))
            ret = int(any(r[1] == a1 and r[2] == path for r in self.pl_rows))
        elif name in ('checkFavExist', 'addMyFav', 'deleteMusicFromFav'):   # (song record): keyed by file name and path, as the stock SQL (the cue times are 0)
            key = (self.read_cstr(self.word(a0 + O['REC_NAME'])), self.read_cstr(self.word(a0 + O['REC_PATH'])))
            self.calls.append((name,) + key)
            if name == 'checkFavExist': ret = int(any(r[:2] == key for r in self.fav_rows))
            elif name == 'addMyFav': self.fav_rows.append(key + (self.read_cstr(self.word(a0 + O['REC_TITLE'])),)); ret = 1
            else: self.fav_rows = [r for r in self.fav_rows if r[:2] != key]; ret = 1
        elif name == 'getPlayListMaxId':
            self.calls.append(('getPlayListMaxId',)); ret = max([r[0] for r in self.pl_rows], default=0)
        elif name == 'addPlayList':   # (song record): the row's id is REC_ID, its playlist REC_DISC
            row = (self.s32(a0 + O['REC_ID']), self.s32(a0 + O['REC_DISC']), self.read_cstr(self.word(a0 + O['REC_PATH'])), self.read_cstr(self.word(a0 + O['REC_TITLE'])))
            self.pl_rows.append(row); self.calls.append(('addPlayList',) + row); ret = 1
        elif name in ('stock_playlist_import', 'stock_playlist_export'):
            self.calls.append((name, self.word(pod.DATA['NAVIGATION_STATUS'][0])))
        elif name == 'albumcoverinfo_init':
            self.calls.append(('albumcoverinfo_init', a0))
        elif name == 'batchadd_albumcover_task':
            self.calls.append(('batchadd_albumcover_task', a0, a1))
        elif name == 'start_player':   # the stock Play all / Shuffle start: the queue as copied, index, class, mode
            self.calls.append(('start_player', a1, a2, a3))
            self.played = (list(self.deques.get(a0, [])), a1)
        elif name == 'widget_destroy':
            self.calls.append(('widget_destroy', a0))
        # ---- Shuffle: the stock play mode, the seed
        # ---- Settings: stock pages by name, the EQ preset name, the text measure (a base machine has no text: 0 wide)
        elif name == 'navigator_to':
            self.calls.append(('navigator_to', self.read_cstr(a0))); ret = 0
        elif name == 'tf_update_click':   # the stock TF card update's click handler (its confirmation, the battery check, the flash): called with no event
            self.calls.append(('tf_update_click', a0, a1)); ret = 0
        elif name == 'getDiskMemoryInfo':   # (path, &capacity, &free) in G as floats, the card's numbers a test sets in self.disk
            cap, rem = getattr(self, 'disk', (0.0, 0.0)); self.calls.append(('getDiskMemoryInfo', self.read_cstr(a0)))
            self.u.mem_write(a1, struct.pack('<f', cap)); self.u.mem_write(a2, struct.pack('<f', rem)); ret = 0
        elif name == 'networkGetConnectStatus':
            ret = getattr(self, 'net', 0)
        elif name == 'networkGetIPAddr':
            self.calls.append(('networkGetIPAddr', a0)); self.u.mem_write(a1, getattr(self, 'ip', b'') + b'\0'); ret = 0
        elif name == 'get_equalizer_preset_name':
            ret = 0 if a0 >= 12 else 1
            if ret: self.u.mem_write(a1, ('eq_' + str(a0)).encode() + b'\0')
        elif name == 'widget_get_text':
            ret = 0
        elif name == 'widget_measure_text':
            u.reg_write(UC_MIPS_REG_F0, 0); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA)); return
        elif name == 'mclGetPlayMode':
            ret = self.mode
        elif name == 'mclGetPlayPos':
            ret = self.play_pos & 0xffffffff; self.calls.append(('mclGetPlayPos',))
        elif name == 'mclSetPlayMode':
            self.mode = a0; self.calls.append(('mclSetPlayMode', a0))
        elif name == 'mclSetPlayPos':
            self.play_pos = a0; self.calls.append(('mclSetPlayPos', a0))
        elif name == 'stock_setmode':   # stock's mclSetPlayMode behind the hook's trampoline (patch/shuffle.c sh_set_mode): the mode word, and the gapless preload closed for a mode other than 0 and 3
            self.mode = a0; self.calls.append(('stock_setmode', a0))
            if self.word(pod.DATA['MCL_PRELOAD'][0]) == 1 and a0 not in (0, 3): self.setword(pod.DATA['MCL_PRELOAD'][0], -1); self.calls.append(('closegapless',))
        elif name == 'mclSetGaplessMode':   # @0x5d28ac: stores the Gapless byte; 0 with a preload open (state 1) sends {mcl-closegapless} and stores -1 in the state
            self.calls.append(('mclSetGaplessMode', a0)); self.u.mem_write(pod.DATA['MCL_GAPLESS'][0], bytes([a0 & 0xff])); ret = 1
            if a0 == 0 and self.word(pod.DATA['MCL_PRELOAD'][0]) == 1: self.setword(pod.DATA['MCL_PRELOAD'][0], -1); self.calls.append(('closegapless',))
            ret = 1
        elif name == 'stock_loadplaylist':   # stock's mclLoadPlayList behind its trampoline: the play queue becomes a copy of the deque, the position the index
            recs = []   # deque_assign copies the records (their strings are shared)
            for r in self.deques[a0]:
                if len(self.deques[a0]) > 4096: recs.append(r); continue   # (a cap test's huge queue shares one record: no room to copy it)
                c = self.alloc(REC_SIZE); self.u.mem_write(c, bytes(self.u.mem_read(r, REC_SIZE))); recs.append(c)
            self.setword(pod.DATA['PLAY_QUEUE'][0], self.new_deque(recs)); self.play_pos = a1; self.calls.append(('stock_loadplaylist', a1, a2))
        elif name == 'notifyPlayMode':
            self.calls.append(('notifyPlayMode',))
        elif name == 'dmrSendPlayMode':
            self.calls.append(('dmrSendPlayMode', a0))
        elif name == 'mclGetOutputWay':
            ret = getattr(self, 'out_way', 0)   # 0 the jacks, 1 Bluetooth, 2 USB audio (a test sets m.out_way)
        elif name == 'write_int_config':
            self.calls.append(('write_int_config', a0, self.read_cstr(a1), self.read_cstr(a2)))
            ret = getattr(self, 'config_ret', 0)   # toolsWriteConfig's: 0 done, -1 config.ini could not be opened (a test sets m.config_ret)
        elif name == 'toolsRandnum':
            ret = self.seed % a0 if a0 else 0
        elif name == 'time_now_ms':
            ret = self.clock; u.reg_write(UC_MIPS_REG_A3, 0)
        elif name == 'toolsGetAlbumCover':
            self.cover_size = (a2, a3)   # the thumbnail's requested size
            self.calls.append(('toolsGetAlbumCover', self.read_cstr(a0), self.read_cstr(a1)))
            if self.album_cover:
                self.files[self.read_cstr(a1)] = 4096; self.present.add(self.read_cstr(a1))
                if getattr(self, 'art_px', None): self.contents = getattr(self, 'contents', {}); self.contents[self.read_cstr(a1)] = jpeg_header(self.art_px)   # the stock encoder's output: fitted inside the request, never upscaled
            ret = self.album_cover
        elif name == 'taglib_album_picture':   # libtag_c: the embedded picture of a track, saved to /tmp/.tmp_picture; 2 JPEG, 1 PNG, 0 none (patch/covercache.c art_embedded)
            self.calls.append(('taglib_album_picture', self.read_cstr(a0), self.read_cstr(a1), a2, a3))
            ret = self.taglib_kind if self.taglib_kind is not None else 2 if self.album_cover else 0
            if ret and self.taglib_data is not None: self.fs['/tmp/.tmp_picture'] = self.taglib_data
        elif name == 'taglib_file_new':   # libtag_c (patch/durations.c dur_probe): a handle for the file, or NULL
            p = self.read_cstr(a0); self.calls.append(('taglib_file_new', p, a1))
            ret = 0
            if p in self.durations: ret = self.alloc(8); self.tag_objs[ret] = p
        elif name == 'taglib_file_audioproperties':   # the AudioProperties object: its vtable word 3 is the (trapped) length()
            self.calls.append(('taglib_file_audioproperties',)); ret = 0
            sec = self.durations.get(self.tag_objs.get(a0), 0)
            if sec:
                vt = self.alloc(32); self.setword(vt + 12, self.tag_len_fn)
                ret = self.alloc(8); self.setword(ret, vt); self.setword(ret + 4, sec)
        elif name == 'taglib_length':
            self.calls.append(('taglib_length',)); ret = self.word(a0 + 4)
        elif name == 'taglib_file_free':
            self.calls.append(('taglib_file_free',)); self.tag_objs.pop(a0, None)
        elif name == 'opendir':
            p = self.read_cstr(a0); self.calls.append(('opendir', p)); ret = 0
            if p in self.listing and ('opendir', p) not in self.fail:
                ret = self.alloc(4); self.open_dirs[ret] = list(self.listing[p])[:self.dir_stop.get(p)]
        elif name == 'readdir':   # struct dirent (32-bit): d_type at 10, d_name at 11
            ret = 0
            if self.open_dirs.get(a0):
                nm, typ = self.open_dirs[a0].pop(0); ret = self.alloc(280)
                self.u.mem_write(ret + 10, bytes([typ]) + nm.encode('latin-1') + b'\0')
        elif name == 'closedir':
            self.open_dirs.pop(a0, None); ret = 0
        elif name == 'toolsGetExternCover':
            self.calls.append(('toolsGetExternCover', self.read_cstr(a0), self.read_cstr(a1)))
            if self.extern_cover: self.files[self.read_cstr(a1)] = 4096
            ret = self.extern_cover
        # ---- libc
        elif name == 'memset':
            self.u.mem_write(a0, bytes([a1 & 0xff]) * a2); ret = a0
        elif name == 'memcpy':
            self.u.mem_write(a0, bytes(self.u.mem_read(a1, a2))); ret = a0
        elif name == 'strcmp':
            x, y = self.read_cstr(a0), self.read_cstr(a1); ret = (x > y) - (x < y)
        elif name in ('strlen', 'strchr', 'strrchr'):   # (the Navidrome source's row data: sbsrc.c reads its fields with these)
            text = self.read_cstr(a0).encode('latin-1')
            if name == 'strlen': ret = len(text)
            else:
                i = (text + b'\0').find(a1 & 0xff) if name == 'strchr' else (text + b'\0').rfind(a1 & 0xff)
                ret = a0 + i if i >= 0 else 0
        elif name == 'utf8_to_pinyin':   # stock's own algorithm (0x73a5f0), its table read from the mapped image: appends to the buffer at out
            src, o = bytes(self.read_cstr(a0).encode('latin-1')), bytes(self.read_cstr(a1).encode('latin-1')); i = 0
            self.calls.append(('utf8_to_pinyin', src))
            while i < len(src):
                c = src[i]
                if c < 0x80: o += bytes([c]); i += 1; continue
                if i + 2 >= len(src): break
                cp = (c << 12 & 0xffff) | (src[i + 1] << 6 & 0xfc0) | (src[i + 2] & 0x3f)
                if 0x4e00 <= cp < 0x9fa6: o += bytes(self.u.mem_read(0x9e2310 + cp - 0x4e00, 1))
                i += 3
            self.u.mem_write(a1, o + b'\0')
        elif name == 'strcasecmp':
            x, y = self.read_cstr(a0).lower(), self.read_cstr(a1).lower(); ret = (x > y) - (x < y)
        elif name == '_deque_push_back':
            self.deques.setdefault(a0, []).append(a1); self.calls.append(('_deque_push_back', a0, a1))
        elif name == 'strdup':
            s = self.read_cstr(a0); a = self.malloc(len(s) + 1)
            self.u.mem_write(a, s.encode('latin-1') + b'\0'); ret = a   # (read_cstr shows bytes as latin-1 characters)
        elif name == 'snprintf':
            fmt = self.read_cstr(a2)
            args = [a3] + [stack(i) for i in range(0, 10)]
            out, ai = '', 0
            i = 0
            while i < len(fmt):
                if fmt[i] == '%' and i + 1 < len(fmt):
                    spec = re.match(r'%(0\d+)?(08)?([sdux%])', fmt[i:])
                    conv = spec.group(3); i += spec.end() - 1
                    if conv == '%': out += '%'
                    elif conv == 's': out += self.read_cstr(args[ai]); ai += 1
                    elif conv == 'd': out += str(struct.unpack('<i', struct.pack('<I', args[ai]))[0]).zfill(int(spec.group(1)[1:]) if spec.group(1) else 0); ai += 1
                    elif conv == 'u': out += str(args[ai]); ai += 1
                    else: out += f'{args[ai]:08x}'; ai += 1
                else: out += fmt[i]
                i += 1
            out = out[:a1 - 1]
            self.u.mem_write(a0, out.encode('latin-1') + b'\0'); ret = len(out)   # bytes as read_cstr shows them
            self.calls.append(('snprintf', out))
        elif name == 'calloc':
            n = a0 * a1
            if self.heap + n >= HEAP + HEAP_SIZE or self.calloc_fail or (self.calloc_fail_size and n == self.calloc_fail_size): ret = 0
            else:
                ret = self.malloc(n); self.u.mem_write(ret, bytes(n))
            self.calls.append(('calloc', n, ret))
        elif name == 'free':
            self.calls.append(('free', a0))
            if self.reuse_heap and a0 in self.__dict__.get('_blocks', {}): self.__dict__.setdefault('_free', {}).setdefault(self._blocks[a0], []).append(a0)
        elif name == 'fopen':
            path, mode = self.read_cstr(a0), self.read_cstr(a1)
            self.calls.append(('fopen', path, mode))
            self.__dict__.setdefault('fopens', []).append(path)   # (every open of the machine's life, which self.calls loses when a test clears it)
            if 'w' in mode and ('fopen', path) not in self.fail: self.files[path] = 0; self.present.add(path)
            ret = (self.alloc(4) if path in self.files or path in self.fs else 0)
            self.fh = (ret, path)
        elif name == 'fclose':
            self.calls.append(('fclose',))
        elif name == 'fseek':
            self.calls.append(('fseek',))
        elif name == 'ftell':
            ret = self.files.get(self.fh[1], len(self.fs.get(self.fh[1], b'')))
        elif name == 'fread':
            data = getattr(self, 'contents', {}).get(self.fh[1])
            if data is not None:   # a file with real bytes (a test's JPEG header): size * count of them, from the start
                chunk = data[:a1 * a2]; self.u.mem_write(a0, chunk) if chunk else None
                ret = len(chunk) // a1 if a1 else 0
            else:
                self.u.mem_write(a0, b'\0' * 4)
                ret = 1 if self.files.get(self.fh[1]) else 0
            self.calls.append(('fread', ret))
        elif name == 'fwrite':
            self.calls.append(('fwrite', self.word(a0))); ret = 1
        elif name == 'rename':
            src, dst = self.read_cstr(a0), self.read_cstr(a1)
            self.calls.append(('rename', src, dst))
            if src in self.fs and ('rename', dst) not in self.fail:
                self.fs[dst] = self.fs.pop(src)
            elif src in self.fs: ret = -1
            elif src in self.files and ('rename', dst) not in self.fail:
                self.files[dst] = self.files.pop(src); self.present.discard(src); self.present.add(dst)
            else: ret = -1
        elif name == 'unlink':
            p = self.read_cstr(a0)
            if ('unlink', p) in self.fail: ret = -1
            else:
                self.files.pop(p, None); self.present.discard(p)
                ret = 0 if self.fs.pop(p, None) is not None else ret
            parent = p.rsplit('/', 1)[0]
            if parent in self.listing:   # the directory forgets what was unlinked
                self.listing[parent] = [e for e in self.listing[parent] if f'{parent}/{e[0]}' != p]
            self.calls.append(('unlink', p))
        elif name == 'mkdir':
            p = self.read_cstr(a0); self.calls.append(('mkdir', p))
            if ('mkdir', p) in self.fail: ret = -1
            else: self.present.add(p); self.dirs.add(p)
        elif name == 'statfs':
            # o32 struct statfs: f_type, f_bsize, .., f_bavail (word 7), f_fsid (words 8, 9). The card is its own file system
            # (type, fsid) unless a test unmounts it; everything else is the root file system.
            p = self.read_cstr(a0); on_card = p.startswith('/mnt/mmc') and self.card_mounted
            self.u.mem_write(a1, struct.pack('<10I', 0x4d44 if on_card else 0x73717368, 4096, 0, 0, 0, 0, 0,
                                             self.free_mb * 256, 0x1234 if on_card else 0x5678, 0) + bytes(88))
            self.calls.append(('statfs', p))
            if ('statfs', p) in self.fail: ret = -1
        # ---- Screenshot: the frame buffer. self.fb = {'var': 40 words, 'fix': 17 words, 'mem': bytes} (None: no /dev/fb0)
        elif name == 'ioctl':
            self.calls.append(('ioctl', self.fds[a0][0] if a0 in self.fds else '?', a1))
            if not self.fb or a0 not in self.fds or self.fds[a0][0] != '/dev/fb0' or ('ioctl', a1) in self.fail: ret = -1
            elif a1 in (0x4600, 0x4602):
                words = self.fb['var' if a1 == 0x4600 else 'fix']
                self.u.mem_write(a2, struct.pack(f'<{len(words)}I', *words))
            else: ret = -1
        elif name == 'mmap':
            self.calls.append(('mmap', a1, a2, a3, stack(0), stack(1)))
            if ('mmap',) in self.fail or not self.fb: ret = 0xffffffff
            else:
                ret = self.malloc(len(self.fb['mem'])); self.u.mem_write(ret, self.fb['mem'])
        elif name == 'munmap':
            self.calls.append(('munmap', a0, a1))
        elif name == 'pthread_create':
            self.calls.append(('pthread_create',))
            ret = 0 if self.thread_ok else 11
            if self.thread_ok: self.setword(a0, 0x1234); self.thread = (a2, a3)
        elif name == 'pthread_join':
            self.calls.append(('pthread_join',))
        elif name == 'pthread_mutex_lock' and a0 == PSYMS.get('cb_mutex'):   # the cover worker's own job-state mutex (patch/covercache.c): not the stock lock
            self.calls.append(('cb_lock',))
            if getattr(self, 'on_cb_lock', None): self.on_cb_lock()   # a test's way to interleave the UI thread with the worker's job transitions
        elif name == 'pthread_mutex_unlock' and a0 == PSYMS.get('cb_mutex'):
            self.calls.append(('cb_unlock',))
            if getattr(self, 'on_cb_unlock', None): self.on_cb_unlock()
        elif name == 'pthread_mutex_lock':
            self.calls.append(('lock', a0))
            if getattr(self, 'on_lock', None): self.on_lock()   # a test's way to act while the lock is "waited for"
        elif name == 'pthread_mutex_unlock':
            self.calls.append(('unlock', a0))
            if getattr(self, 'on_unlock', None): self.on_unlock()
        elif name == '_create_deque':
            ret = 0 if self.deque_fail else self.new_deque(); self.calls.append(('_create_deque', self.read_cstr(a0)))
        elif name == 'deque_init':
            self.deques.setdefault(a0, [])
        elif name == 'deque_assign':
            self.deques[a0] = list(self.deques.get(a1, []))
            self.calls.append(('deque_assign', len(self.deques[a0])))
        elif name == 'deque_size':
            ret = len(self.deques.get(a0, []))
        elif name == 'deque_at':
            items = self.deques.get(a0, []); ret = items[a1] if a1 < len(items) else 0
            self.deque_reads[a0] = self.deque_reads.get(a0, 0) + 1
            if a1 >= len(items): self.calls.append(('deque_at_oob', a1, len(items)))   # the device's deque_at reads past the end: a crash there
        elif name == 'deque_destroy':
            self.deques.pop(a0, None); self.calls.append(('deque_destroy',))
        elif name == 'cstl_pop_back':   # libcstl's deque_pop_back(q) = _deque_shrink_at_end(q, 1) (0x3f3dc, read from the disassembly): the deque's element destroy callback on the last element, then the emptied block
            items = self.deques[a0]   # freed. The callback of an stSongInfo deque is 0x5dabfc: free() of the pointers at +4 .. +0x2c (when set), memset(record, 0, 0x58). Nothing is allocated, copied or locked.
            if not items: self.calls.append(('pop_back_empty', a0)); raise AssertionError('deque_pop_back on an empty deque')
            r = items.pop(); self.calls.append(('pop_back', a0, r)); self.pops += 1
            for off in range(4, 0x30, 4):
                if self.word(r + off): self.calls.append(('free', self.word(r + off)))
            self.u.mem_write(r, bytes(0x58))
        # ---- Home guard: files, descriptors, the window stack
        elif name == 'open':
            p, fl = self.read_cstr(a0), a1
            self.calls.append(('open', p, fl))
            if ('open', p) in self.fail: ret = -1
            elif p == '/dev/fb0':
                if self.fb: ret = self.next_fd; self.fds[ret] = [p, fl, 0]; self.next_fd += 1
                else: ret = -1
            elif fl & 0x100 and p.startswith('/mnt/mmc/.m1plus/') and p.rsplit('/', 1)[0] not in self.dirs: ret = -1   # no such directory (the Daily Mix's folder, or the card folder above it)
            elif p in self.dirs: ret = self.next_fd; self.fds[ret] = [p, fl, 0]; self.next_fd += 1
            elif p in self.fs or fl & 0x100:
                if fl & 0x200 or p not in self.fs: self.fs[p] = b''
                ret = self.next_fd; self.fds[ret] = [p, fl, 0]; self.next_fd += 1
            else: ret = -1
        elif name == 'read':
            p, _, pos = self.fds[a0]
            data = self.fs.get(p, b'')[pos:pos + a2]
            self.u.mem_write(a1, data) if data else None
            self.fds[a0][2] += len(data); ret = len(data)
            self.calls.append(('read', p))
        elif name == 'write':
            p = self.fds[a0][0]; data = bytes(self.u.mem_read(a1, a2))
            self.calls.append(('write', p, data))
            if ('write', p) in self.fail: ret = -1
            elif self.fds[a0][1] & 3 == 2:   # O_RDWR: written at the descriptor's position (lseek), as the device does (the Subsonic cache patches a starred flag in place)
                old = self.fs.get(p, b''); pos = self.fds[a0][2]
                self.fs[p] = old[:pos] + data + old[pos + len(data):]; self.fds[a0][2] = pos + len(data); ret = a2
            else: self.fs[p] = self.fs.get(p, b'') + data; ret = a2
        elif name == 'fsync':
            p = self.fds[a0][0]; self.calls.append(('fsync', p))
            ret = -1 if ('fsync', p) in self.fail else 0
        elif name == 'close':
            self.calls.append(('close', self.fds.pop(a0)[0]))
        elif name == 'window_manager':
            ret = self.wm
        elif name == 'window_manager_get_top_main_window':
            self.calls.append(('get_top_main_window', a0)); ret = self.top_main
        elif name == 'widget_is_window_opened':
            ret = self.home_opened
        # ---- the Daily Mix (patch/dailymix.c): the wall clock
        elif name == 'time':
            ret = self.wall
            if a0: self.setword(a0, ret)
        elif name == 'localtime':
            import time as _t
            tm = _t.gmtime(self.u.mem_read(a0, 4) and struct.unpack('<I', bytes(self.u.mem_read(a0, 4)))[0] + self.tz)
            if not self.tm_buf: self.tm_buf = self.alloc(0x40)
            self.u.mem_write(self.tm_buf, struct.pack('<9i', tm.tm_sec, tm.tm_min, tm.tm_hour, tm.tm_mday, tm.tm_mon - 1, tm.tm_year - 1900, (tm.tm_wday + 1) % 7, tm.tm_yday - 1, 0))
            ret = self.tm_buf
        elif name == 'stock_init_resume':
            self.calls.append(('stock_init_resume', a0, a1)); ret = self.init_ret
        # ---- the keyboard's Chinese layer (patch/keyboard.c): stock's ime_pinyin open and close, scripted for the ways opening fails (the real engine runs, see test/pod/pinyin.py Engine)
        elif name == 'im_open_decoder':
            self.calls.append(('im_open_decoder', self.read_cstr(a0), self.read_cstr(a1))); self.py_log.append(('im_open_decoder',))
            ret = int(self.py_open_ok); eng = self.alloc(0x30d8); self.u.mem_write(eng, bytes([ret])); self.setword(pod.DATA['PY_ENGINE'][0], eng)
            trie = self.alloc(16); self.setword(eng + 0xc, trie); self.setword(trie + 4, self.PY_DL); self.setword(trie + 8, self.PY_SPT)   # MatrixSearch +0xc the DictTrie, its +4 the DictList, +8 the SpellingTrie   # a failed open leaves an object that is not initialised, as stock's
        elif name == 'py_lemma_id':   # DictList::get_lemma_id(this, char16 *, len): 0 for a character the dictionary does not have
            ch = chr(struct.unpack('<H', bytes(self.u.mem_read(a1, 2)))[0]); self.py_log.append(('py_lemma_id', ch)); ret = int(ch in self.py_dict)
        elif name == 'py_splids':   # get_splids_for_hanzi(this, hanzi, half, out, max): the character's readings as ids into py_spellings; a character that is not in the dictionary crashes
            ch = chr(a1 & 0xffff); assert ch in self.py_dict, f'get_splids_for_hanzi called for {ch!r}, not in the dictionary'
            ids = [self.py_ids.setdefault(s, len(self.py_ids) + 1) for s in self.py_dict[ch]][:stack(0)]; self.py_log.append(('py_splids', ch))
            self.u.mem_write(a3, struct.pack('<%dH' % len(ids), *ids)); ret = len(ids)
        elif name == 'py_spelling':   # SpellingTrie::get_spelling_str(this, id): upper case with a capital-and-lower head (ZhOU)
            s = next(k for k, v in self.py_ids.items() if v == (a1 & 0xffff)); t = s[0].upper() + (s[1] if s[:2] in ('zh', 'ch', 'sh') else '') + s[2 if s[:2] in ('zh', 'ch', 'sh') else 1:].upper()
            ret = self.cstr(t)
        elif name == 'im_close_decoder':
            self.calls.append(('im_close_decoder',)); self.py_log.append(('im_close_decoder',)); self.setword(pod.DATA['PY_ENGINE'][0], 0)
        # ---- libcurl's easy interface, the Wi-Fi level and worker threads (patch/pcnet.c)
        elif name == 'get_wifisignal':
            ret = self.wifi; self.calls.append(('get_wifisignal',))
        elif name == 'reset_poweroptions_timer':   # stock: standby / auto power-off / screen countdowns set again for a non-zero argument (patch/podcasts.c keeps the device awake with (1, 1, 0))
            self.calls.append(('reset_poweroptions_timer', a0, a1, a2))
        elif name == 'lseek':   # a descriptor's position (the downloads ask the size of a .part file with SEEK_END)
            p, _, pos = self.fds[a0]; size = len(self.fs.get(p, b''))
            ret = {0: a1, 1: pos + a1, 2: size + a1}[a2]; self.fds[a0][2] = ret
            self.calls.append(('lseek', p, a1, a2))
        elif name == 'curl_global_init':
            self.calls.append(('curl_global_init', a0))
        elif name == 'curl_easy_init':
            ret = self.alloc(8); self.curl[ret] = {}; self.calls.append(('curl_easy_init',))
        elif name == 'curl_easy_setopt':
            self.curl[a0][a1] = (self.read_cstr(a2) if a2 else None) if a1 in (10002, 10007, 10018, 10065, 10102) else a2   # URL, RANGE, USERAGENT, CAINFO, ACCEPT_ENCODING: strings (NULL: None)
        elif name == 'curl_easy_perform':
            ret = self.curl_perform(a0)
        elif name == 'curl_easy_getinfo':
            v = self.curl_last[a0].get(a1, 0)
            if a1 in (0x100001, 0x100012, 0x100020, 0x10001f): self.setword(a2, self.cstr(v) if v else 0)   # strings: the effective url, Content-Type, the primary IP, the Location of a redirect not followed
            elif a1 >> 20 == 6: self.u.mem_write(a2, struct.pack('<Q', v & 0xffffffffffffffff))
            else: self.setword(a2, v)
        elif name == 'curl_easy_cleanup':
            self.calls.append(('curl_easy_cleanup', a0)); self.curl.pop(a0, None)
        elif name == 'pthread_detach':
            self.calls.append(('pthread_detach', a0))
        elif name == 'sleep':
            self.calls.append(('sleep', a0)); self.wall += a0
            if getattr(self, 'on_sleep', None): self.on_sleep(len([c for c in self.calls if c[0] == 'sleep']))   # a test's way to act while the worker waits (the number of sleeps so far)
        # ---- the Equalizer page (patch/peq_ui.c, patch/peq.c): stock's EQ setter (recorded with the switch byte it reads), the parser's sscanf and libm
        # (doubles in $f12 / $f14, the result in $f0: the payload is -mfp64, so the machine needs FR set, fpu())
        elif name == 'set_equalizer_value':
            self.calls.append(('set_equalizer_value', a0, self.u.mem_read(pod.DATA['EQ_FLAG'][0], 1)[0]))
        elif name == 'ferror':
            ret = 0
        elif name == '__isoc99_sscanf':
            s, fmt = self.read_cstr(a0), self.read_cstr(a1)
            assert fmt == '%lf%n', fmt
            num = re.match(r'\s*[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?', s)
            if num:
                self.u.mem_write(a2, struct.pack('<d', float(num.group(0)))); self.setword(a3, num.end()); ret = 1
            else: ret = 0xffffffff if not s.strip() else 0
        elif name in ('pow', 'sqrt', 'cos', 'sin'):
            import math
            f = lambda r: struct.unpack('<d', struct.pack('<Q', u.reg_read(r) & (2 ** 64 - 1)))[0]
            from unicorn.mips_const import UC_MIPS_REG_F12, UC_MIPS_REG_F14
            x, y = f(UC_MIPS_REG_F12), f(UC_MIPS_REG_F14)
            r = {'pow': lambda: math.pow(x, y), 'sqrt': lambda: math.sqrt(x), 'cos': lambda: math.cos(x), 'sin': lambda: math.sin(x)}[name]()
            u.reg_write(UC_MIPS_REG_F0, struct.unpack('<Q', struct.pack('<d', r))[0])
        else:
            raise AssertionError(f'unmocked call {name} at {address:#x}')
        u.reg_write(UC_MIPS_REG_V0, ret & 0xffffffff)
        u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))

    def nested(self, fn, *args):
        """Payload code run from inside a mock (a libcurl callback): the registers are saved, the frame is below the caller's, and the
        caller continues afterwards. Returns $v0."""
        u = self.u
        # qsort/bsearch call this millions of times. A native CPU snapshot avoids 66 individual
        # register transfers per comparison and also preserves HI/LO and floating-point state.
        if self._nested_contexts:
            saved = self._nested_contexts.pop(); u.context_update(saved)
        else: saved = u.context_save()
        try:
            sp = (u.reg_read(UC_MIPS_REG_SP) - 0x400) & ~7
            for r, v in zip((UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3), args): u.reg_write(r, v & 0xffffffff)
            for i, v in enumerate(args[4:]): self.setword(sp + 16 + 4 * i, v)
            u.reg_write(UC_MIPS_REG_SP, sp); u.reg_write(UC_MIPS_REG_RA, RET); u.reg_write(UC_MIPS_REG_T9, fn)
            u.emu_start(fn, RET)
            return u.reg_read(UC_MIPS_REG_V0)
        finally:
            u.context_restore(saved); self._nested_contexts.append(saved)

    def curl_perform(self, h):
        """curl_easy_perform against the scripted server self.curl_site(url, options) -> a dict: rc, code, body, chunk (bytes per write
        callback), dbg ((type, text) pairs for the debug callback), eff, ip, redirects, verify, err and the times in microseconds (dns, conn, tls,
        first, total). The payload's write callback runs for every chunk and its debug callback for every line, inside this call."""
        o = self.curl[h]
        r = {'rc': 0, 'code': 200, 'body': b'', 'chunk': 16384, 'dbg': [], 'eff': o[10002], 'ip': '93.184.216.34', 'redirects': 0, 'verify': 0, 'err': '',
             'dns': 1000, 'conn': 2000, 'tls': 3000, 'first': 4000, 'total': 5000, **(self.curl_site(o[10002], o) if self.curl_site else {'rc': 6})}
        for typ, text in r['dbg']:
            buf = self.cstr(text); self.nested(o[20094], h, typ, buf, len(text.encode()), o[10095])
        body, rc, sent = r['body'], r['rc'], 0
        sizes = r['chunk'] if isinstance(r['chunk'], (list, tuple)) else [r['chunk']]   # 'chunk': an int, or a list of sizes in order (the last repeats)
        need = max(sizes) + 1   # (one buffer for the machine's requests: a phase-2 fill makes hundreds)
        if self.__dict__.get('_curl_buf_n', 0) < need: self._curl_buf, self._curl_buf_n = self.alloc(need), need
        buf = self._curl_buf
        total = r.get('length', len(body))   # the answer's length as the server gave it (0: unknown)

        def xfer(sent):
            """libcurl's transfer-info callback (CURLOPT_XFERINFOFUNCTION, 64-bit counts: o32 puts each pair in even registers / stack words); the test's r['xfer'](url, sent, total) runs first. Non-zero aborts."""
            if r.get('xfer'): r['xfer'](o[10002], sent, total)
            if not o.get(20219): return 0
            return self.nested(o[20219], o.get(10057, 0), 0, total & 0xffffffff, total >> 32, sent & 0xffffffff, sent >> 32, 0, 0, 0, 0)
        last = {0x200002: r['code'], 0x200014: r['redirects'], 0x20000d: r['verify'], 0x20000e: r.get('filetime', -1) & 0xffffffff, 0x100001: r['eff'], 0x100012: r.get('ctype'), 0x100020: r['ip'], 0x600008: 0, 0x10001f: r.get('redirect_url'), 0x60000f: r.get('clen', r.get('length', len(body))),
                0x600032: r['total'], 0x600033: r['dns'], 0x600034: r['conn'], 0x600038: r['tls'], 0x600036: r['first']}
        self.curl_last[h] = last   # (libcurl has the headers' facts ready before the first byte reaches the write callback: a download asks for the code and the Content-Type there)
        if r['rc'] == 0 and xfer(0): rc = 42   # CURLE_ABORTED_BY_CALLBACK
        i, k = 0, 0
        while i < (len(body) if rc == 0 or r.get('partial') else 0):   # 'partial': the body arrives, then the transfer fails with rc
            step = sizes[min(k, len(sizes) - 1)]; k += 1
            part = body[i:i + step]; i += step; self.u.mem_write(buf, part); sent += len(part)
            if self.nested(o[20011], buf, 1, len(part), o[10001]) != len(part): rc = 23; break   # CURLE_WRITE_ERROR: the callback cut the transfer off
            if xfer(sent): rc = 42; break
        self.calls.append(('curl_perform', o[10002], rc))
        if r['err']: self.u.mem_write(o[10010], r['err'].encode() + b'\0')
        last[0x600008] = sent
        return rc

    def set_language(self, table):
        """Make the mocked stock translation answer in a language (a strings table name such as 'ru_RU'): our keys from
        tools/pod_i18n.py, as tools/mod_strings.py writes them into the tables. None: English."""
        self.strings = {} if table is None else {k: v[pod_i18n.table_for(table)] for k, v in pod_i18n.TEXT.items()}

    @staticmethod
    def real_key(key):
        """A key as read_cstr returns it (UTF-8 bytes as latin-1 chars) as the text it is, so that a key with an ellipsis or a middle dot finds its table entry and comes back unchanged without one."""
        try: return key.encode('latin-1').decode('utf-8')
        except UnicodeError: return key

    def tr(self, key):
        """The translation as the payload gets it back, UTF-8 bytes read as latin-1 chars like read_cstr's results."""
        key = self.real_key(key)
        return self.strings.get(key, key).encode('utf-8').decode('latin-1')

    def rect(self, w, x, y, cw, ch):
        for k, v in (('x', x), ('y', y), ('w', cw), ('h', ch)): self.props[(w, k)] = v

    fb = None                 # Screenshot: the frame buffer /dev/fb0 answers with (see the ioctl / mmap mocks)
    db = {}                   # __xstat: path -> [mtime, nsec, size]
    card_mounted = True       # statfs tells the card's mount point from its parent
    blits = ()              # the Albums grid's canvas_draw_image calls (bitmap, src rect, dst rect), texts, text measures
    texts = ()
    measures = ()
    slide_starts_at_1 = True   # the stock slide_menu constructor stores value = 1 (the payload sets the value itself)
    fh = (0, '')
    stock_songlist = False   # loadSongList: stock's copy of the shown list (Shuffle) or the album mock
    mode = 0                 # mclGetPlayMode
    play_pos = -1            # mclGetPlayPos: the playing track's index in the play queue (*PLAY_QUEUE), -1 for none
    seed = 12345             # toolsRandnum
    wifi = 4                 # stock get_wifisignal: -1 not connected, else the level 2..5
    py_open_ok = True        # im_open_decoder's result (the engine object it leaves is initialised only on success)
    PY_DL, PY_SPT = 0x7d100001, 0x7d100002   # the scripted DictList and SpellingTrie (patch/search.c's initials): py_dict maps a character to its readings
    py_dict = {}
    py_ids = {}
    wall = 1800000000        # time(): the wall clock, seconds (2027-01-15 08:00 UTC); tz: seconds localtime adds
    tz = 0
    clock = 1                # time_now_ms
    calloc_fail = False
    calloc_fail_size = 0           # a calloc of exactly this many bytes is refused (one allocation, not all)
    played = None            # (queue records, index) handed to playing_page
    page_window = 0          # what widget_get_window answers
    bitmap = None
    bitmap_ok = True
    canvas_mem = 0            # a canvas in emulated memory (landscape reads its font); font_mem: the font it points at
    font_mem = 0x7000f000
    glyphs = ()               # (char, size) of every font_get_glyph call
    widget_on_fail = frozenset()   # events whose widget_on registration is refused (returns 0)
    timer_modify_fail = False
    live_scroll = frozenset() # scroll_view structs whose virtual_h / yoffset the widget_set_prop_int mock also stores (the stock setters' stores)
    oy_canvas = 0             # a canvas in emulated memory whose origin y (canvas_t @4) is logged in draw_oy at every canvas_draw_image
    draw_oy = ()
    confirm_answers = {}      # the answer by dialog text (a test sets a copy: m.confirm_answers = {text: code}); before confirm_answer
    confirm_answer = None     # what the stock confirm dialog returns when a test wants a value other than Yes / No (the Songs delete's 0x14)
    mem_geometry = False      # widget_move / widget_resize also write the widget_t (stock widget_to_local reads it)
    COUNT = False             # count from the start (count()); otherwise call() has no step limit

    def call(self, addr, a0=0, a1=0, count=20000, a2=0, a3=0):
        self.calls = []
        self._icount = 0
        self.u.reg_write(UC_MIPS_REG_SP, STACK)
        self.u.reg_write(UC_MIPS_REG_RA, RET)
        self.u.reg_write(UC_MIPS_REG_T9, addr)
        for r, v in ((UC_MIPS_REG_A0, a0), (UC_MIPS_REG_A1, a1), (UC_MIPS_REG_A2, a2), (UC_MIPS_REG_A3, a3)): self.u.reg_write(r, v & 0xffffffff)
        self.limit = count   # enforced by _block: emu_start's own count hooks every instruction (~10x slower)
        self.u.emu_start(addr, RET)   # uncounted: no step limit; a runaway is check.py's per-test timeout
        assert self.u.reg_read(UC_MIPS_REG_PC) == RET, 'did not return to sentinel'
        return self.u.reg_read(UC_MIPS_REG_V0)

    FIRE_WIN = None   # fire()'s default widget (None: the machine's window)

    def fire(self, ev, win=None):
        """The handler the payload bound with widget_on(win, ev), run as the emitter would, with no event struct."""
        fn, ctx = self.bound[(self.FIRE_WIN or self.window if win is None else win, ev)]
        return self.call(fn, a0=ctx, a1=0, count=8000000)

    def names(self): return [c[0] for c in self.calls]

    def screen(self, lit): self.u.mem_write(pod.DATA['BACKLIGHT_STATUS'][0], bytes([int(lit)]))

    def click(self, name, count=2000000, x=None, evt='EVT_CLICK'):
        """Tap the widget `name`: its latest EVT_CLICK handler (the payload's widget_on call) runs with the context it was given.
        x: the event is a pointer event at that x (y 0) as stock sends it, screen coordinates (evt: another event type)."""
        w = self.widgets[name]
        fn, ctx = self.bound[(w, O[evt])]
        e = 0
        if x is not None:
            e = self.alloc(0x30); self.u.mem_write(e, bytes(0x30))
            self.setword(e, O[evt]); self.setword(e + 0x18, x)
        return self.call(fn, a0=ctx, a1=e, count=count)

    def touch(self, kind, x, y=150, t=0, count=4000000, fn='on_pointer'):
        """Deliver one pointer event (EVT_POINTER_*) to the payload's touch layer, as stock's
        widget_dispatch would: pointer_event_t with type @0, time @8, x @0x18, y @0x1c. fn: the handler
        (Cover Flow's on_pointer, the Albums grid's al_on_pointer)."""
        e = self.alloc(0x30); self.u.mem_write(e, bytes(0x30))
        self.setword(e, {'down': 0xff, 'move': 0x101, 'up': 0x103, 'abort': 0x107}[kind])
        self.setword(e + 8, t); self.setword(e + 0x18, x); self.setword(e + 0x1c, y)
        return self.call(PSYMS[fn], a0=0, a1=e, count=count)

    def tap(self, x, y=150, count=4000000, fn='on_pointer'):
        self.touch('down', x, y, 1000, count=count, fn=fn); calls = list(self.calls)
        self.touch('up', x, y, 1080, count=count, fn=fn); self.calls = calls + self.calls

    def settle(self, limit=200, step=16):
        """Fire the snap timer until it stops re-arming (the harness's timer_add never runs), the clock
        (time_now_ms) advancing step ms before each callback."""
        seen = []
        for _ in range(limit):
            self.clock += step
            self.call(PSYMS['on_snap'], count=2000000); seen += self.calls
            if not any(c[0] == 'timer_add' for c in self.calls): break
        self.calls = seen


# ---------------------------------------------------------------------------
# Demo's own pointer-event code run for real (test/pod/scroll.py, menutap.py, pulldown.py): the window manager's entry
# points, scroll_view, list_item and button code under Unicorn on a tree of real widget structs, with only the leaves
# mocked (timers, animators, the emitter, widget states). A test subclasses StockEventMachine and handles what is its
# own in leaf(); everything else falls through to the shared mocks here.
SV_VT, LI_VT, LV_VT, BTN_VT, IMG_VT = 0x97a298, 0x979f78, 0x97a018, 0x97a8d8, 0x97ae78   # g_scroll_view_vtable, g_list_item_vtable, ...
# leaves of the stock event code that are mocked (address -> name); memcpy and memset are the base machine's
STOCK_LEAVES = {0x66cd50: 'widget_ref', 0x66ce2c: 'widget_unref', 0x6f11c0: 'darray_init', 0x66a850: 'widget_is_keyboard',
                0x666888: 'widget_is_focusable', 0x66a9a8: 'widget_get_window', 0x66e620: 'widget_set_focused_internal',
                0x66962c: 'widget_set_state', 0x666ec0: 'widget_off_by_func', 0x6f4c40: 'event_init', 0x6f4458: 'emitter_dispatch',
                0x671f18: 'widget_dispatch_simple_event', 0x70122c: 'log_get_log_level', 0x742950: 'printf', 0x743c20: 'fflush',
                0x742c40: '__cmpdi2', 0x68cc30: 'anim_create', 0x68cd04: 'anim_set_params', 0x673440: 'anim_on', 0x6730c8: 'anim_start',
                0x66e8c4: 'widget_set_focused', 0x6691d0: 'widget_invalidate_force', 0x66c114: 'widget_update_pointer_cursor'}
STOCK_LIBC = {0x742160: 'memcpy', 0x742da0: 'memset'}
STOCK_NOOPS = ('widget_set_focused', 'widget_set_focused_internal', 'widget_invalidate_force', 'widget_ref', 'widget_unref', 'printf',
               'fflush', 'widget_update_pointer_cursor', 'widget_is_keyboard', 'widget_is_focusable', 'widget_get_window',
               'darray_init', 'widget_off_by_func', 'darray_deinit')


class SelectMachine(Machine):
    """The machine plus the stock multi-select calls the Songs and Playlists pages make: the selection vector (select_recordinit, set_selectindex: `sel_vec`), the
    stock batch delete (recorded with the selected rows), and the style setter of the pills (`styled`) with its value (value_set_uint32)."""
    SELECT_CALLS = ('select_recordinit', 'set_selectindex', 'batch_delete_file', 'batch_add_file', 'widget_set_style', 'value_set_uint32')

    def __init__(self):
        super().__init__()
        self.styled, self.sel_vec = [], None
        for n in self.SELECT_CALLS:
            self.handlers[pod.FUNCTIONS[n][2]] = n

    def _hook(self, u, address, size, _):
        name = self.handlers.get(address, '')
        if name not in self.SELECT_CALLS: return super()._hook(u, address, size, _)
        a0, a1, a2, a3 = (u.reg_read(r) for r in (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3))
        sp = u.reg_read(UC_MIPS_REG_SP)
        ret = 0
        if name == 'select_recordinit':
            self.sel_vec = [0] * a0 if a0 >= 0 else self.sel_vec
            self.calls.append(('select_recordinit', a0))
        elif name == 'set_selectindex':
            assert self.sel_vec is not None and 0 <= a0 < len(self.sel_vec), f'set_selectindex({a0}) out of range'
            self.sel_vec[a0] ^= 1; ret = 1
            self.calls.append(('set_selectindex', a0))
        elif name == 'batch_delete_file':
            flag = self.word(sp + 16)
            self.calls.append(('batch_delete_file', a0, a1, a2, a3, flag, [i for i, v in enumerate(self.sel_vec or []) if v]))
            ret = 1
        elif name == 'batch_add_file':   # (class, 0xf00b, the list, the vector, playlist id): recorded with the selected rows
            self.calls.append(('batch_add_file', a0, a1, a2, a3, self.word(sp + 16), [i for i, v in enumerate(self.sel_vec or []) if v]))
            ret = 1
        elif name == 'widget_set_style':
            self.styled.append((a0, self.read_cstr(a1), self.word(a2 + 8)))
        elif name == 'value_set_uint32':
            self.setword(a0 + 8, a1); ret = a0
        else:
            return super()._hook(u, address, size, _)
        u.reg_write(UC_MIPS_REG_V0, ret & 0xffffffff)
        u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))


class ListMachine(SelectMachine):
    """The machine plus what the A-Z list pages (patch/azlist.c, the Songs and Artists pages) call that the shared mocks do not know: the widget text calls the title
    fit and the pills make (widget_get_text, widget_measure_text: `measure` gives a text's width), the scroll animator's destroy and the stock scroll end handler (the
    rail's jump stops a coasting list first)."""
    def __init__(self):
        super().__init__()
        self.wtext, self.measure = {}, lambda t: 8 * len(t)
        self.measure_w = None   # or a function (widget, text) -> width: the font differs per widget (the keyboard's field, pinyin label and candidates)
        self.handlers[pod.SCROLL_DONE] = 'stock_scroll_done'   # the stock scroll end handler (patch/scroll.c's): mocked, it clears wa
        for n in ('widget_get_text', 'widget_measure_text', 'widget_animator_destroy'):
            self.handlers[pod.FUNCTIONS[n][2]] = n

    def _hook(self, u, address, size, _):
        name = self.handlers.get(address, '')
        if name not in ('widget_set_tr_text', 'widget_set_text_utf8', 'widget_get_text', 'widget_measure_text',
                        'widget_animator_destroy', 'stock_scroll_done'):
            return super()._hook(u, address, size, _)
        a0, a1 = (u.reg_read(r) for r in (UC_MIPS_REG_A0, UC_MIPS_REG_A1))
        if name == 'widget_set_tr_text': self.wtext[a0] = self.tr(self.read_cstr(a1))
        elif name == 'widget_set_text_utf8': self.wtext[a0] = self.read_cstr(a1)
        if name == 'widget_get_text':
            t = self.wtext.get(a0)
            ret = 0
            if t is not None:
                t = t.encode('latin-1').decode('utf-8')
                ret = self.alloc(4 * len(t) + 4); self.u.mem_write(ret, struct.pack(f'<{len(t) + 1}I', *map(ord, t), 0))
        elif name == 'widget_measure_text':
            t = ''.join(map(chr, self.words_until_zero(a1)))
            w = float(self.measure_w(a0, t) if self.measure_w else self.measure(t)) if t else 0.0
            u.reg_write(UC_MIPS_REG_F0, struct.unpack('<I', struct.pack('<f', w))[0]); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))
            return
        elif name == 'widget_animator_destroy':
            self.calls.append(('widget_animator_destroy', a0)); self.setword(a0 + 0x28, 0); ret = 0
        elif name == 'stock_scroll_done':
            self.calls.append(('stock_scroll_done', a0)); self.setword(a0 + O['SC_WA'], 0); ret = 0
        else:
            return super()._hook(u, address, size, _)
        u.reg_write(UC_MIPS_REG_V0, ret & 0xffffffff)
        u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))


POINTER_ON = {'d': 0x67126c, 'm': 0x6715f4, 'u': 0x67187c}   # widget_on_pointer_down / _move / _up (the window manager's entry points)
POINTER_EVT = {'d': O['EVT_POINTER_DOWN'], 'm': O['EVT_POINTER_MOVE'], 'u': O['EVT_POINTER_UP']}


class StockEventMachine(Machine):
    """The machine with demo's pointer-event code running for real. Class attributes of a subclass: LEAVES (extra mocked
    addresses, merged over STOCK_LEAVES), EXTRA (extra mocked names the base Machine does not know, such as
    'widget_animator_destroy'), NOOPS, REAL (more stock functions, from pod.FUNCTIONS, to run for real). log holds what
    the last pointer event caused, owner maps an emitter to its widget, states the widget_set_state calls."""
    LEAVES = STOCK_LEAVES
    EXTRA = ()
    NOOPS = STOCK_NOOPS
    REAL = ()
    WIN_Y = 0         # the window's screen y: pointer() adds it (pointer events carry screen coordinates)
    DELIVER_COUNT = 8000000   # the instruction budget of each handler deliver() calls
    DELIVER = False   # queue what the stock code emits (a copy: it lives on the stock stack) for the handlers the payload bound;
                      # pointer() hands it to them after the stock code returned, in the order it was sent

    def __init__(self):
        super().__init__()
        for a, n in {**self.LEAVES, **STOCK_LIBC}.items(): self.handlers[a] = n
        for n in ('widget_grab', 'widget_ungrab', 'widget_dispatch', 'widget_dispatch_event_to_target_recursive') + tuple(self.REAL):
            if n in pod.FUNCTIONS: self.handlers.pop(pod.FUNCTIONS[n][2], None)        # stock's own, run for real
        self.u.reg_write(_STATUS, self.u.reg_read(_STATUS) | 1 << 29 | 1 << 26)   # CU1 and FR: the velocity code is floating point (-mfp64)
        self.setword(pod.GP - 0xd98, self.alloc(8))   # the GOT slot of `stdout` (the dynamic loader fills it): the debug fflush(stdout) reads through it
        self.owner, self.states, self.log, self.anims, self.end, self.t = {}, {}, [], {}, {}, 0
        self.queue, self.fired, self.calls_all = [], [], []

    def pointer(self, kind, x, y, dt=16, abort=False, root=None):
        """One pointer event at root (the window): widget_on_pointer_down / _move / _up, or (abort) the EVT_POINTER_ABORT that
        window_base_on_event sends on EVT_WINDOW_TO_BACKGROUND while the window is pressed (pointer_event_init(.., 0x107, ..)
        then widget_on_pointer_up, @0x676e38). calls_all collects the calls of the event and of the handlers it reached."""
        self.t += dt
        e = self.alloc(0x30); self.u.mem_write(e, bytes(0x30))
        self.setword(e, O['EVT_POINTER_ABORT'] if abort else POINTER_EVT[kind]); self.setword(e + 4, 0x30); self.setword(e + 8, self.t)
        self.setword(e + 0x18, x); self.setword(e + 0x1c, y + self.WIN_Y)
        self.u.mem_write(e + 0x24, bytes([0 if kind == 'u' else 1]))
        self.queue, self.log = [], []
        ret = self.call(POINTER_ON[kind], a0=self.root if root is None else root, a1=e, count=8000000)
        self.calls_all += self.calls
        if self.DELIVER: self.deliver()
        return ret

    def deliver(self):
        """The queued events to the handlers the payload bound; fired records (owner name, event) of every one."""
        for owner, evt, raw in self.queue:
            self.fired.append((self.name_of(owner), evt))
            if (owner, evt) in self.bound:
                fn, ctx = self.bound[(owner, evt)]
                ev = self.alloc(0x30); self.u.mem_write(ev, raw)
                self.call(fn, a0=ctx, a1=ev, count=self.DELIVER_COUNT)
                self.calls_all += self.calls
                self.handled()
        self.queue = []

    def handled(self):
        """After each delivered handler: a subclass writes what the payload's mocked calls changed back into its structs."""

    def name_of(self, a): return next((n for n, w in self.widgets.items() if w == a), hex(a))

    def call(self, *a, **k):
        try: return super().call(*a, **k)
        except Exception as ex:   # noqa: BLE001 - say where the emulation stopped
            raise AssertionError(f'{ex} at pc {self.u.reg_read(UC_MIPS_REG_PC):#x}, ra {self.u.reg_read(UC_MIPS_REG_RA):#x}') from ex

    def _hook(self, u, address, size, _):
        name = self.handlers.get(address)
        if name not in self.LEAVES.values() and name not in self.EXTRA:
            return super()._hook(u, address, size, _)
        a0, a1, a2, a3 = (u.reg_read(r) for r in (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3))
        ret = self.leaf(name, a0, a1, a2, a3, u.reg_read(UC_MIPS_REG_SP))
        u.reg_write(UC_MIPS_REG_V0, (ret or 0) & 0xffffffff)
        u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))

    def leaf(self, name, a0, a1, a2, a3, sp):
        """One mocked leaf; its result. A subclass handles its own names first and ends with super().leaf()."""
        if name in self.NOOPS: return 0
        if name == 'widget_set_state': self.states[a0] = self.read_cstr(a1)
        elif name == 'event_init':
            self.u.mem_write(a0, struct.pack('<II', a1, 0x18)); self.setword(a0 + 0x10, a2)
        elif name == 'emitter_dispatch':
            self.log.append(('emit', self.owner.get(a0, a0), self.word(a1) & 0xffff))
            if self.DELIVER: self.queue.append((self.owner.get(a0, a0), self.word(a1) & 0xffff, bytes(self.u.mem_read(a1, 0x30))))
        elif name == 'widget_dispatch_simple_event': self.log.append(('simple', a0, a1))
        elif name == '__cmpdi2':   # libgcc: signed 64 bit compare (a1:a0 against a3:a2) -> 0 less, 1 equal, 2 greater
            s64 = lambda lo, hi: struct.unpack('<q', struct.pack('<II', lo, hi))[0]
            x, y = s64(a0, a1), s64(a2, a3); return 0 if x < y else 1 if x == y else 2
        elif name == 'log_get_log_level': return 5
        elif name == 'anim_create':   # widget_animator_scroll_create: a new animator, not started
            an = self.alloc(0x80); self.u.mem_write(an, bytes(0x80))
            self.setword(an + 4, a0); self.setword(an + 0x28, 2)
            self.anims[an] = {'dur': a1}; return an
        elif name == 'anim_set_params': self.anims[a0].update(x0=a1, y0=a2, x1=a3, y1=self.word(sp + 16))
        elif name == 'anim_on': self.end[a0] = (a2, a3)
        elif name == 'anim_start': self.setword(a0 + 0x28, 1)
        elif name == 'widget_animator_destroy':   # stock queues the free on an idle; the animator is out of the manager and not running
            self.log.append(('anim_destroy', a0)); self.setword(a0 + 0x28, 0); self.setword(a0 + 0x48, 0)
        return 0

    # ---- the widget tree: x/y/w/h, flags (enable, visible, sensitive), parent, vtable; an emitter gets the listener object
    def widget(self, vt, x, y, w, h, parent=0, emitter=False):
        a = self.alloc(0x180); self.u.mem_write(a, bytes(0x180))
        for off, v in ((0, x), (4, y), (8, w), (0xc, h), (0x24, 0xd), (0x44, parent), (0x70, vt)): self.setword(a + off, v)
        if emitter:
            em = self.alloc(0x20); self.owner[em] = a; self.setword(a + 0x5c, em)
        return a

    def kids(self, parent, kids):
        elms = self.alloc(4 * len(kids))
        for i, c in enumerate(kids): self.setword(elms + 4 * i, c)
        arr = self.alloc(12)
        self.setword(arr, len(kids)); self.setword(arr + 4, len(kids)); self.setword(arr + 8, elms)
        self.setword(parent + 0x58, arr)


# ---------------------------------------------------------------------------
# Stock hit testing, executed for real. widget_on_pointer_down_children (0x67145c) asks
# widget_find_target (0x666bdc -> widget_find_target_default 0x6747d4, widget_to_local,
# widget_is_point_in) for the child under the absolute point, requires (flags & 9) == 9 and
# recurses into it. These run unmocked on a widget tree laid out in emulated memory exactly as
# the page's asset and runtime calls leave it: x/y/w/h @0..0xc, flags u16 @0x24 (bit 0 enable,
# bit 2 visible, bit 3 sensitive), parent @0x44, grab @0x4c, children darray @0x58
# ({size, capacity, elms}), vtable @0x70 (zeroed: the stock defaults are used).
FIND_TARGET = 0x666bdc
CLIENT_H = 450
STATES = ('normal', 'pressed', 'over', 'focused', 'disable', 'selected')
F_ENABLE, F_VISIBLE, F_SENSITIVE = 1, 4, 8


class Node:
    def __init__(self, name, x, y, w, h, flags=F_ENABLE | F_VISIBLE | F_SENSITIVE, children=()):
        self.name, self.x, self.y, self.w, self.h, self.flags = name, x, y, w, h, flags
        self.children = list(children)
        self.addr = 0


def asset_tree(path, names=None):
    """A Node tree from a built ui/*.bin, its flags from the asset's visible/sensitive/enable."""
    def conv(w):
        f = F_ENABLE | F_VISIBLE | F_SENSITIVE
        if w.get('visible') == 'false': f &= ~F_VISIBLE
        if w.get('sensitive') == 'false': f &= ~F_SENSITIVE
        if w.get('enable') == 'false': f &= ~F_ENABLE
        return Node(w.name or w.type, w.x, w.y, w.w, w.h, f, [conv(c) for c in w.children])
    root = conv(awtk_ui.parse(open(path, 'rb').read()))
    root.w, root.h = 320, CLIENT_H   # a normal window is 450 px tall under the 30 px system_bar
    return root


def lay_out(m, root):
    vt = m.alloc(0x80); m.u.mem_write(vt, bytes(0x80))
    def place(n, parent):
        n.addr = m.alloc(0x80); m.u.mem_write(n.addr, bytes(0x80))
        for off, v in ((0, n.x), (4, n.y), (8, n.w), (0xc, n.h), (0x24, n.flags),
                       (0x44, parent), (0x70, vt)):
            m.setword(n.addr + off, v)
        for c in n.children: place(c, n.addr)
        if n.children:
            elms = m.alloc(4 * len(n.children))
            for i, c in enumerate(n.children): m.setword(elms + 4 * i, c.addr)
            arr = m.alloc(12)
            m.setword(arr, len(n.children)); m.setword(arr + 4, len(n.children)); m.setword(arr + 8, elms)
            m.setword(n.addr + 0x58, arr)
    place(root, 0)
    by_addr = {}
    def index(n):
        by_addr[n.addr] = n
        for c in n.children: index(c)
    index(root)
    return by_addr


def stock_target(m, root, x, y):
    """The widget a touch at the absolute (x, y) is delivered to, by demo's own code."""
    mark = m.next   # the laid out tree is scratch for this one query: give it back (a page of 70 rows, asked 20 times, would fill the 1 MB)
    by_addr = lay_out(m, root)
    w, path = root.addr, [root.name]
    try:
        while True:
            t = m.call(FIND_TARGET, a0=w, a1=x, a2=y, count=200000)
            if not t or (by_addr[t].flags & 9) != 9: return path
            w = t; path.append(by_addr[t].name)
    finally:
        m.next = mark


def node(root, name):
    if root.name == name: return root
    for c in root.children:
        r = node(c, name)
        if r: return r


def cover_page_tree(m, asset, runtime=True):
    """The Cover Flow page as the window manager sees it: the built asset, the runtime
    slide_menu and touch layer in view_covers, and every visibility/sensitivity the payload set."""
    root = asset_tree(asset)
    for n in COVER_WIDGETS:
        nd, h = node(root, n), m.widgets.get(n)
        if not nd or h is None: continue
        if (h, 'visible') in m.props:
            nd.flags = nd.flags & ~F_VISIBLE | (F_VISIBLE if m.props[(h, 'visible')] else 0)
        if (h, 'sensitive') in m.props:
            nd.flags = nd.flags & ~F_SENSITIVE | (F_SENSITIVE if m.props[(h, 'sensitive')] else 0)
    if runtime:   # and the geometry the payload's widget_move / widget_resize calls left
        covers = node(root, 'view_covers')
        def geo(h, d): return tuple(m.props.get((h, k), v) for k, v in zip('xywh', d)) if h else d
        covers.x, covers.y, covers.w, covers.h = geo(m.widgets.get('view_covers'), (covers.x, covers.y, covers.w, covers.h))
        slide = m.widgets.get('slide_menu')
        sf = F_ENABLE | F_VISIBLE | F_SENSITIVE
        if slide and m.props.get((slide, 'sensitive')) == 0: sf &= ~F_SENSITIVE
        covers.children.append(Node('slide_menu', *geo(slide, (0, 0, 320, O['CF_VIEW_H'])), sf))
        if m.widgets.get('view'):
            covers.children.append(Node('touch_layer', *geo(m.widgets['view'], (0, 0, 320, O['CF_VIEW_H']))))
    return root


# ---------------------------------------------------------------------------
# Repaint, as AWTK does it: only the dirty rectangles are painted, the canvas clipped to them (canvas_begin_frame
# 0x6447b4 -> canvas_set_clip_rect). widget_invalidate 0x668d9c with no rectangle marks the widget's own 0, 0, w, h,
# which widget_invalidate_default 0x674920 carries up to the window by the widgets' x, y, unclipped by the parents.
# The stock slide_menu marks its own rectangle when its xoffset changes (slide_menu_set_prop 0x613c94 -> 0x613bec)
# and when its value does (slide_menu_set_value 0x61399c, tail call at 0x613a1c). Rectangles are (x, y, w, h) in the
# window, from the props the payload's calls left (view_covers: the asset's place unless moved, see cover_rects).
def abs_rect(m, w):
    x, y = m.props.get((w, 'x'), 0), m.props.get((w, 'y'), 0)
    p = m.parent.get(w)
    while p and p != m.window:
        x, y = x + m.props.get((p, 'x'), 0), y + m.props.get((p, 'y'), 0)
        p = m.parent.get(p)
    return x, y, m.props.get((w, 'w'), 0), m.props.get((w, 'h'), 0)


def cover_rects(m):
    """Give view_covers its asset rectangle and the window as its parent, so abs_rect works on the page."""
    cv = m.widgets['view_covers']
    for k, v in zip('xywh', (0, pod_ui.COVER_Y, 320, pod_ui.COVER_FRAME_H)): m.props.setdefault((cv, k), v)
    m.parent[cv] = m.window
    for k, v in zip('xywh', (0, 0, 320, CLIENT_H)): m.props[(m.window, k)] = v


def dirty_rects(m):
    """The window rectangles the calls of the last m.call marked for repaint."""
    slide, out = m.widgets.get('slide_menu'), []
    for c in m.calls:
        if c[0] == 'widget_invalidate_force': out.append(abs_rect(m, c[1]))
        elif slide and (c[0] == 'slide_menu_set_value' or (c[0] == 'widget_set_prop_int' and c[1] == slide and c[2] == 'xoffset')):
            out.append(abs_rect(m, slide))
    return out


def covered(rects, r, step=2):
    """Whether the union of rects covers the rectangle r (sampled every step px, and its last row and column)."""
    x0, y0, w, h = r
    xs = sorted(set(range(x0, x0 + w, step)) | {x0 + w - 1})
    ys = sorted(set(range(y0, y0 + h, step)) | {y0 + h - 1})
    return all(any(a <= x < a + c and b <= y < b + d for a, b, c, d in rects) for y in ys for x in xs)


COVER_WIDGETS = ['btn_return', 'btn_backtoplayer', 'btn_cancel', 'navigationbar_view', 'view_covers',
                 'label_album', 'label_artist', 'label_status', 'label_title', 'btn_songs']


SORT_FILE, SORT_TMP = '/mnt/data/m1plus/albums-sort', '/mnt/data/m1plus/albums-sort.tmp'   # patch/home.h; the album order (0 Title, 1 Artist, 2 Recently Added, 3 Year)
AZRAIL_FILE, AZHEAD_FILE = '/mnt/data/m1plus/appearance-index-rail', '/mnt/data/m1plus/appearance-headers'   # patch/home.h: the Index Rail and Section Headers switches (both on by default)
OLD_ORDER_FILE, OLD_ORDER_TMP = '/mnt/data/m1plus/album-order', '/mnt/data/m1plus/album-order.tmp'   # the retired Album Order setting (patch/covercache.c migrates and deletes it)


def cover_machine(albums=3, tracks=2, cached=True, sort='album', cls=None):
    """A machine set up to open Cover Flow: the asset's widgets, an album list and, by default,
    a complete thumbnail cache (so no build runs). sort: the order setting; the machines default to the stock order
    ('album'), which the shelf tests index by album number; 'artist' is the setting's own default (the sort tests)."""
    m = (cls or Machine)()
    if sort == 'album': m.fs[SORT_FILE] = b'0\n'
    for n in COVER_WIDGETS: m.widget(n)
    m.showlist = [m.record(album=f'Album {i}', artist=f'Artist {i}',
                           path=f'/mnt/mmc/m/{i}/1.flac', rid=i + 1) for i in range(albums)]
    m.tracklist = [m.record(album='Album 0', title=f'Track {i}', name=f'{i}.flac',
                            path=f'/mnt/mmc/m/0/{i}.flac', rid=100 + i) for i in range(tracks)]
    m.present.add('/mnt/mmc/m/0/0.flac')
    for i in range(albums): m.present.add(f'/mnt/mmc/m/{i}/1.flac')
    if cached:   # every album already has a cache file, so the page opens straight on the covers
        for c in cache_paths(m, albums): m.present.add(c); m.files[c] = 4096
    return m


def fnv(h, s):
    for c in s.encode(): h = (h ^ c) * 16777619 & 0xffffffff
    return h * 16777619 & 0xffffffff


def album_key(artist, album):
    """The cover cache's key of an album: FNV-1a of artist then album, never 0 (patch/covercache.c)."""
    return fnv(fnv(O['FNV_SEED'], artist), album) or 1


def cache_paths(m, albums):
    return [art_file(album_key(f'Artist {i}', f'Album {i}')) for i in range(albums)]


def build_state(m):
    """The shared cache worker's state struct `cb` (patch/covercache.c): jobs, cap, thread, mode, running, done, total, cancelled, exited, orphan (words); the image path (a string) follows isof."""
    b = PSYMS['cb']
    keys = ('jobs', 'cap', 'thread', 'mode', 'running', 'done', 'total', 'cancelled', 'exited', 'orphan', 'seen', 'at', 'stalled', 'cur', 'orphan_at', 'began', 'seq', 'claimed', 'seen_seq', 'phase', 'iw', 'ih', 'ikind', 'isof')
    return {k: m.word(b + 4 * i) for i, k in enumerate(keys)}


def build_jobs(m):
    """[(track, key)] of the held job set, in the order the worker takes them."""
    s = build_state(m)
    return [(m.read_cstr(m.word(s['jobs'] + 16 * i)), m.word(s['jobs'] + 16 * i + 4)) for i in range(s['total'])] if s['jobs'] else []


def build_durs(m):
    """[(track, key, size, seconds)] of a CC_DURATIONS set (job_t is track, key, size, sec)."""
    s = build_state(m)
    return [(m.read_cstr(m.word(s['jobs'] + 16 * i)),) + tuple(m.word(s['jobs'] + 16 * i + 4 * k) for k in (1, 2, 3)) for i in range(s['total'])] if s['jobs'] else []


def count_of(m, name):
    """How often libc/stock function `name` was called in the last Machine.call (which starts a fresh log)."""
    return len([c for c in m.calls if c[0] == name])


def fired(m, fn, count=40000000):
    """A payload function (a page timer's callback, a handler) runs: the calls it made."""
    m.call(PSYMS[fn], count=count)
    return list(m.calls)


def artists_row(page):
    return next((i for i, r in enumerate(page.rows) if r.action == pod_pages.ACT_ARTISTS), None)


def artist_rec(m, name, rid):
    """An Artists row as getAllArtist / GetAllAlbumArtist leave it: the name in REC_TITLE."""
    return m.record(album='', artist=name, path='', title=name, name='', rid=rid)


COMPOSER_ALBUMS = {'Bach': ['Cello Suites', 'Goldberg Variations'], 'Mozart': ['Requiem'], 'Unknown Composer': []}


AR_WIDGETS = ('artists_listview', 'view_grid', 'sg_rail', 'sg_bubble', 'sg_bubble_letter', 'ar_title', 'label_hdr', 'label_rail', 'label_rail_on', 'label_row_title',
              'img_nb_fade', 'ar_spin')


def artists_row_y(i, starts=(0, 1)):
    """The y (from the list's top, the scroll offset not included) of the middle of display row i of the Artists page, the sections starting at the rows `starts`."""
    return O['SG_TITLE_H'] + sum(1 for s in starts if s <= i) * O['SG_HDR_H'] + i * 52 + 26


def artists_tap(m, i, starts=(0, 1), dx=0, dy=0, count=30000000):
    """A tap on display row i of the Artists page (a press and a release at the row's middle; dx, dy: the finger moves between them)."""
    y = 80 + artists_row_y(i, starts)
    m.touch('down', 100, y, 1000, fn='ar_on_down', count=count)
    calls = list(m.calls)
    m.touch('up', 100 + dx, y + dy, 1080, fn='ar_on_up', count=count)
    m.calls = calls + m.calls


# the Albums page's navbar buttons and "..." card (patch/viewsort.c): rows 0..3 the sorts, 4 Grid, 5 List, 6 Search, 7 Select (no tick); a tick on each but Search, a glyph on the view rows and Search, vs_hair between Search and Grid, a second line on the sorts
VS_WIDGETS = ('btn_more', 'vs_scrim', 'vs_card', 'vs_hair', 'vs_glyph4', 'vs_glyph5', 'vs_glyph6', 'vs_glyph7') + tuple(f'vs_item{i}' for i in range(8)) + tuple(f'vs_label{i}' for i in range(8)) + tuple(f'vs_tick{i}' for i in range(6)) + tuple(f'vs_sub{i}' for i in range(4))


AR_WIDGETS += VS_WIDGETS   # the Artists page's "..." card is the Albums page's (patch/viewsort.c)


def forget_card(m):
    """The "..." card's widgets as an asset leaves them: what a page's vs_bind hid or restyled is forgotten (a Machine has one set of named widgets for every page)."""
    ids = {m.widgets[n] for n in VS_WIDGETS if n in m.widgets}
    for k in [k for k in m.props if k[0] in ids and k[1] != 'x']: del m.props[k]


def view_switch(m, count):
    """A tap on the View row of the view the page is not in (the ticked one is Grid or List; a tap on it does nothing)."""
    list_now = m.fs.get('/mnt/data/m1plus/albums-view') == b'0\n'   # the saved mode is the page's (a missing file is the grid): the payload writes it at every switch
    m.call(PSYMS['al_on_item'], a0=O['VS_SORTS'] + (0 if list_now else 1), count=count)


def utf8(s):
    """A text the harness read from payload memory (latin-1 of the UTF-8 bytes) as the text it is."""
    return s.encode('latin-1').decode('utf-8')
ALBUMS_PAGE_WIDGETS = ('btn_coverflow', 'btn_play', 'btn_shuffle', 'label_row_sub', 'label_grid_title', 'label_grid_sub', 'al_title', 'al_name', 'img_nb_fade') + VS_WIDGETS


def artists_machine(artists=('Miles Davis', 'Nina Simone', 'Unknown Artist'), composers=(), genres=(), albums_page=False, cls=ListMachine):
    """A machine with the Artists page's widgets, the stock artist list (class 0xf004), each
    artist's albums (loadAlbumList) and the library album list (getAllAlbum). Miles Davis has
    three albums, one of them (Jazz Hits) filed under Various Artists in the library list; Nina
    Simone has one; Unknown Artist none. Every library album is cached under its library key.
    A row's tap opens our Albums page scoped to the artist when albums_page is set (its widgets exist);
    otherwise that window will not open and the tap falls back to Cover Flow on the artist, which
    the Cover Flow tests of this module drive."""
    m = cover_machine(albums=0, cls=cls)
    m.fs[AZRAIL_FILE] = b'1\n'   # Index Rail on: the rail tests of this page (the switch defaults on)
    for n in AR_WIDGETS: m.widget(n)
    if albums_page:
        for n in ALBUMS_PAGE_WIDGETS: m.widget(n)
    else:
        m.windows['m1plus_albums'] = 0
    # the page's widgets as widget structs (window > list_view > scroll_view > view_grid, and the rail), for demo's own widget_to_local (as songs_machine)
    win, lv, sv, view, rail = m.alloc(0x80), m.widgets['artists_listview'], m.alloc(0x180), m.widgets['view_grid'], m.widgets['sg_rail']
    m.u.mem_write(sv, bytes(0x180)); m.u.mem_write(lv, bytes(0x80)); m.u.mem_write(view, bytes(0x80)); m.u.mem_write(rail, bytes(0x80))
    for w, y, h, parent in ((win, 30, 450, 0), (lv, 50, O['GRID_VIEW_H'], win), (sv, 0, O['GRID_VIEW_H'], lv), (view, 0, O['GRID_VIEW_H'], sv)):
        for off, v in ((4, y), (8, 320), (0xc, h), (0x44, parent)): m.setword(w + off, v)
    m.setword(sv + 8, 310)
    for off, v in ((0, O['SG_RAIL_X']), (4, 50), (8, O['SG_RAIL_W']), (0xc, O['GRID_VIEW_H']), (0x44, win)): m.setword(rail + off, v)
    m.widgets['artists_scrollview'] = sv
    if albums_page: m.widgets['albums_scrollview'] = sv   # the Albums page's stock list, the same geometry
    m.mem_geometry, m.live_scroll = True, frozenset({sv, rail})
    m.sv, m.rail, m.view, m.lv = sv, rail, view, lv
    m.canvas = m.alloc(0x80); m.oy_canvas = m.canvas
    m.measure = lambda t: 0   # no title is cut (test/pod/artists.py measures in the real font)
    for n, w in (('label_title', O['NAV_VIEW_X'] - O['NAV_TITLE_X']), ('ar_title', O['SG_TITLE_W'])): m.setword(m.widgets[n] + 8, w)
    m.album_artists = [artist_rec(m, a, i + 1) for i, a in enumerate(('Various Artists', 'Miles Davis'))]
    m.class_lists[O['CLASS_ARTISTS']] = [artist_rec(m, a, -1 if a == 'Unknown Artist' else i + 1)
                                         for i, a in enumerate(artists)]
    # Genres and Composers (opt in): the stock lists (class 0xf006, 0xf005: the name in REC_TITLE, the Unknown row id -1) and each composer's albums (loadAlbumList(0xf005))
    if composers:
        m.class_lists[O['CLASS_COMPOSERS']] = [artist_rec(m, c, -1 if c.startswith('Unknown') else i + 1) for i, c in enumerate(composers)]
    if genres:
        m.class_lists[O['CLASS_GENRES']] = [artist_rec(m, g, -1 if g.startswith('Unknown') else i + 1) for i, g in enumerate(genres)]
    albums = {'Miles Davis': ['Bitches Brew', 'Jazz Hits', 'Kind of Blue'], 'Nina Simone': ['Pastel Blues'],
              'Unknown Artist': []}
    albums.update({c: COMPOSER_ALBUMS.get(c, []) for c in composers})
    artists = tuple(artists) + tuple(composers)
    library = []   # getAllAlbum's rows: one per album name
    for artist, names in albums.items():
        if artist not in artists: continue
        m.artist_albums[artist] = []
        for album in names:
            path = f'/mnt/mmc/{artist}/{album}/1.flac'
            m.artist_albums[artist].append(m.record(album=album, artist=artist, path=path, rid=100 + len(library)))
            lib_artist = 'Various Artists' if album == 'Jazz Hits' else artist
            library.append(m.record(album=album, artist=lib_artist, path=path, rid=len(library) + 1))
            c = art_file(fnv(fnv(O["FNV_SEED"], lib_artist), album) or 1)
            m.present.update((path, c)); m.files[c] = 4096
    m.class_lists[O['CLASS_ALBUMS']] = library
    m.showlist = library
    return m


def _pos(field):
    """The address of Cover Flow's cfpos.value (0) or cfpos.off (1); clang may split the struct (cfpos.0, cfpos.1)."""
    return PSYMS['cfpos'] + 4 * field if 'cfpos' in PSYMS else PSYMS[f'cfpos.{field}']


def shelf_value(m): return struct.unpack('<i', struct.pack('<I', m.word(_pos(0))))[0]
def shelf_off(m): return struct.unpack('<i', struct.pack('<I', m.word(_pos(1))))[0]
def put_value(m, v): m.setword(_pos(0), v)
def put_off(m, v): m.setword(_pos(1), v)


def paint(m):
    """One EVT_AFTER_PAINT on the touch layer, as stock's widget_paint dispatches it."""
    event = m.alloc(0x40); m.u.mem_write(event, bytes(0x40))
    m.setword(event + O['EVENT_PAINT_CANVAS'], 0x22220000)
    m.call(PSYMS['on_paint'], a0=0, a1=event, count=400000000)


def host_frame(frac, ring=None, land=False):
    """The same shelf from the host build of patch/coverflow.c: every slot the placeholder, which
    is what the payload has when no cover decodes (widget_load_image fails in the harness). land: the
    landscape shelf, turned, in its window-sized bitmap."""
    import ctypes, tempfile
    sys.path.insert(0, os.path.join(ROOT, 'test'))
    import coverflow as hostcf
    with tempfile.TemporaryDirectory() as tmp:
        lib = hostcf.build(tmp)
        tex = (ctypes.c_uint * (O['ART_SIZE'] * O['ART_SIZE']))()
        for i in range(len(tex)): tex[i] = 0xff2b2b2b
        texs = [tex if r else None for r in ring] if ring else [tex] * 7
        frame = (hostcf.render(lib, frac, texs, hostcf.land_cfg(lib), O['CFL_H'], O['CFL_W']) if land
                 else hostcf.render(lib, frac, texs))
        return bytes(frame)
