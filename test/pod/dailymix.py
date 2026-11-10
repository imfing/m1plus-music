"""The Daily Mix card of the menu's Home instance (patch/dailymix.c, tools/pod_dailymix.py, tools/pod_mix.py, docs/modules/dailymix.md).

The design (geometry shared with the shelf, the art generator over many palettes, the texts in 13 languages and their widths, the previews) and the device code:
the compiled payload runs under Unicorn on the Home menu as real widget structs (the Recently Played test's machine with the section added, demo's own layouter,
scroll_view and pointer code) with the stock library, playlist table, clock and canvas mocked. The checks:
  constants     patch/offsets.inc against the Python models, the sRGB table, the stock addresses and calls the playlist sequence is mirrored from
  assets        the section's widgets, the Home Screen rows (a switch, an action row without a chevron), the disc images
  files         the mix file and the art file read strictly (a corpus of broken files against the model), the switch file
  art           the generator in C against pod_dailymix.art, pixel for pixel (RGB565 file and bitmap with its blended corners), over palettes and seeds
  mix           the whole job on a library: the picks against pod_mix.select, the constraints, the playlist written with the stock calls (header, songs, ids),
                yesterday's playlist removed, the files, the card; Regenerate; every failure leaving yesterday's mix; the cost in instructions
  text          the title and artists lines in 13 languages against the Python wrap
  touch         the card opens the playlist's songs, the disc plays them, a rename and a reused id
  menu          the section in the list: order, heights, hidden / shown, the shelf below it, the scroll position"""
import importlib.util, os, random, re, struct, sys
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)
import awtk_ui, mod_icons, pod_dailymix as D, pod_mix as X, pod_ui as U
from awtk_text import Ttf, StbText, awtk_width

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join('rootfs', 'release', 'assets', 'default', 'raw')


def sibling(name):
    mod = sys.modules.get(f'podtest_{name}')
    if mod is None:
        spec = importlib.util.spec_from_file_location(f'podtest_{name}', os.path.join(HERE, name + '.py'))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[f'podtest_{name}'] = mod
        spec.loader.exec_module(mod)
    return mod


recent, pulldown = sibling('recent'), sibling('pulldown')
CARD_DIR = '/mnt/mmc/.m1plus'
MIX_DIR = CARD_DIR + '/daily-mix'
MIX, MIX_TMP, ART, ART_TMP = MIX_DIR + '/tracks', MIX_DIR + '/tracks.tmp', MIX_DIR + '/art', MIX_DIR + '/art.tmp'
SET, SET_TMP = '/mnt/data/m1plus/home-daily-mix', '/mnt/data/m1plus/home-daily-mix.tmp'
EVT_DOWN, EVT_UP, EVT_ABORT = O['EVT_POINTER_DOWN'], O['EVT_POINTER_UP'], O['EVT_POINTER_ABORT']
EVT_BG, EVT_FG, EVT_DESTROY, EVT_AFTER_PAINT, EVT_CLICK = O['EVT_WINDOW_TO_BG'], O['EVT_WINDOW_TO_FG'], O['EVT_DESTROY'], O['EVT_AFTER_PAINT'], O['EVT_CLICK']
CLS_LIB, CLS_REC, CLS_OFT, CLS_FAV, CLS_ALB = 0xf001, 0xf007, 0xf008, 0xf00a, 0xf003
START_MS = O['DM_START_MS']
W, H = D.DM_W, D.DM_H


def key_of(artist, album): return fnv(fnv(O['FNV_SEED'], artist), album) or 1
def tone_word(rgb): return 0xff000000 | rgb[0] | rgb[1] << 8 | rgb[2] << 16
def day_of(wall, tz=0): return (wall + tz) // 86400
PATHS = [f'/mnt/mmc/Music/p{i:02d}.flac' for i in range(25)]     # a mix file's songs (the corpus and the art tests need no library)
def b8(s): return s.encode('utf-8').decode('latin-1')    # the file models keep bytes as latin-1 characters


class DM(recent.ST):
    """The Home instance of the menu with the Daily Mix section (the asset's children: header, card, glass disc, two style labels) between the rows and the shelf."""
    def __init__(self, count=False, **kw):
        super().__init__(start=False, **kw)
        if count: self.count()   # only a test that measures counts: the emulation is several times faster
        self.u.mem_map(SCRATCH + 0x100000, 0x800000)   # room for the records of a large library
        sv = self.sv
        self.daily = self.widget(self.zv, 0, 0, U.SH_W, D.DM_SEC_H, sv, emitter=True)
        self.u.mem_write(self.daily + 0x24, struct.pack('<H', 0x1))          # enabled, not visible, not sensitive: the asset's
        self.dhead = self.widget(self.zv, D.DM_HEAD_X, D.DM_HEAD_TOP, D.DM_HEAD_W, D.DM_HEAD_H, self.daily)
        self.u.mem_write(self.dhead + 0x24, struct.pack('<H', 0x5))
        self.busy = self.widget(self.zv, D.DM_BUSY_X, D.DM_BUSY_Y, D.DM_BUSY_PX, D.DM_BUSY_PX, self.daily)
        self.u.mem_write(self.busy + 0x24, struct.pack('<H', 0x1))           # hidden and insensitive: the asset's
        self.card = self.widget(self.zv, D.DM_X, D.DM_TOP, D.DM_W, D.DM_H, self.daily, emitter=True)
        self.disc = self.widget(self.zv, D.DM_X + D.DM_DISC_X, D.DM_TOP + D.DM_DISC_Y, D.DM_DISC, D.DM_DISC, self.daily, emitter=True)
        self.dlab = [self.widget(self.zv, 0, 0, 10, 10, self.daily) for _ in range(2)]
        for lab in self.dlab: self.u.mem_write(lab + 0x24, struct.pack('<H', 0x1))
        self.kids(self.daily, [self.dhead, self.busy, self.card, self.disc] + self.dlab)
        self.kids(sv, self.rows + [self.daily, self.shelf, self.pad])
        self.widgets.update({'pod_daily': self.daily, 'pod_dm_head': self.dhead, 'pod_dm_busy': self.busy, 'pod_dm_card': self.card, 'pod_dm_play': self.disc,
                             'pod_dm_title': self.dlab[0], 'pod_dm_sub': self.dlab[1]})
        self.arrange(); self.relayout()
        self.stock_songlist = True

    def stack(self):
        arr = self.word(self.sv + 0x58); elms = self.word(arr + 8)
        names = {self.daily: 'daily', self.shelf: 'shelf', self.pad: 'pad'}
        return [names.get(c, self.rows.index(c) if c in self.rows else hex(c)) for c in (self.word(elms + 4 * i) for i in range(self.word(arr)))]

    def up(self): return self.is_shown(self.daily)
    def busy_state(self): return self.is_visible(self.busy), bool(self.flags(self.busy) & 8)     # (visible, sensitive)
    def busy_seen(self): return all(self.is_visible(w) for w in (self.busy, self.daily))     # visible through its ancestors (the section; the menu is always shown)
    def hide_all(self):
        self.u.mem_write(self.daily + 0x24, struct.pack('<H', 0x1)); self.arrange(); self.relayout()

    def start_dm(self, **kw):
        self.calls = []
        self.call(PSYMS['dailymix_start'], a0=self.root, count=8000000)
        return list(self.calls)

    def ticks(self, limit=400, per=60000000):
        """dm_tick until the timer is not armed again; the instructions of each tick (None each on a machine that does not count)."""
        costs, self.tick_log = [], []
        for _ in range(limit):
            self.call(PSYMS['dm_tick'], a0=0, count=per)
            self.tick_log.append(list(self.calls))
            costs.append(self.icount if self.counting else None)
            if 'timer_add' not in self.names(): return costs
        raise AssertionError('the tick never ended')

    def abs_pos(self, w):
        x = y = 0
        p = w
        while p:
            x += self.s32(p); y += self.s32(p + 4); p = self.word(p + 0x44)
        return x, y - self.yoff()

    def card_xy(self, dx, dy):
        x, y = self.abs_pos(self.card)
        return x + dx, y + dy

    def scroll_to(self, y): self.setword(self.sv + 0x84, y)

    def paint_card(self):
        e = self.alloc(0x40); self.u.mem_write(e, bytes(0x40)); self.setword(e + O['EVENT_PAINT_CANVAS'], 0x22220000)
        self.blits.clear(); self.texts.clear(); self.measures.clear(); self.text_styles.clear()
        self.call(PSYMS['dm_on_paint'], a0=0, a1=e, count=40000000)
        return list(self.blits), list(self.texts), list(self.text_styles)


# ---- the world: a library, the lists the stock queries answer with, the playlist table
def library(seed=7, artists=34):
    rnd = random.Random(seed)
    names = [f'Artist {chr(65 + i % 26)}{i}' for i in range(artists)] + ['Björk', '坂本龍一']
    songs = []
    for a in names:
        for al in range(rnd.randint(1, 3)):
            album = f'{a} Album {al}'
            for t in range(rnd.randint(5, 11)):
                songs.append(dict(path=f'/mnt/mmc/Music/{a}/{album}/{t + 1:02d}.flac', artist=a, album=album, title=f'Track {t + 1}', name=f'{t + 1:02d}.flac'))
    return songs, rnd


def history(songs, rnd, played=0.6, recent_n=40, fav_n=12):
    """Plays, the recent order (newest first) and favourites for a library: three dicts/lists over the song indices."""
    plays = {i: rnd.choice([1, 1, 2, 3, 5, 8, 20, 60, 300]) for i in range(len(songs)) if rnd.random() < played}
    recent_ = rnd.sample(sorted(plays) or [0], min(recent_n, len(plays))) if plays else []
    fav = set(rnd.sample(range(len(songs)), min(fav_n, len(songs))))
    return plays, recent_, fav


def model(songs, plays, recent_, fav):
    return [dict(path=s['path'], artist=s['artist'], album=s['album'], plays=plays.get(i, 0), recpos=recent_.index(i) if i in recent_ else None, fav=i in fav) for i, s in enumerate(songs)]


def stock_world(m, songs, plays=None, recent_=(), fav=(), present=True):
    """What loadLocalClassList answers: the library (0xf001), Most Played (0xf008, track = plays - 1), Recently Played (0xf007, newest first), favourites, albums."""
    plays = plays or {}
    rec = lambda s, i: m.record(album=s['album'], artist=s['artist'], path=s['path'], title=s['title'], name=s['name'], rid=i + 1)
    recs = [rec(s, i) for i, s in enumerate(songs)]
    m.class_lists[CLS_LIB] = recs
    often = []
    for i in sorted(plays, key=lambda i: -plays[i]):
        r = rec(songs[i], i); m.setword(r + O['REC_TRACK'], plays[i] - 1); often.append(r)
    m.class_lists[CLS_OFT] = often
    m.class_lists[CLS_REC] = [rec(songs[i], i) for i in recent_]
    m.class_lists[CLS_FAV] = [rec(songs[i], i) for i in sorted(fav)]
    seen, albums = set(), []
    for s in songs:
        if s['album'] not in seen:
            seen.add(s['album']); albums.append(m.record(album=s['album'], artist=s['artist'], path=s['path'], title=s['album'], name=s['name'], rid=len(albums) + 1))
    m.class_lists[CLS_ALB] = albums
    if present:
        for s in songs: m.present.add(b8(s['path']))   # (the mocked access reads the bytes of a path as latin-1 characters)
    return recs


def plrow(id_, name='', album='', cd_num=None, path='', artist='', title=''):
    return dict(id=id_, name=name, path=path, title=title or name, album=album, artist=artist, genre='', composer='', albumsonger='',
                type=4 if id_ <= 100 else 8, cd_num=id_ if cd_num is None else cd_num, track=0, year=0)


def put_tones(m, songs, picks, mdl):
    """The tone cache the job reads (the album page's tone cache, patch/common.c): the top albums of the picks get distinct tones. The expected tones, in order."""
    titles = X.top_albums(mdl, picks)
    tones, found = [(200, 90, 60), (60, 120, 200), (90, 190, 120)], []
    for t, title in zip(tones, titles):
        artist = next(s['artist'] for s in songs if s['album'] == title)
        m.call(PSYMS['pod_tone_put'], a0=key_of(artist, title), a1=tone_word(t), count=100000)
        found.append(t)
    return found


def expect_mix(m, songs, plays, recent_, fav, day, regen, tz=0, tones=None):
    """The model's mix for the library: (picks, seed, aseed, names, tones)."""
    mdl = model(songs, plays, recent_, fav)
    seed = X.seed_for(day, regen)
    picks = X.select(mdl, seed)
    return mdl, picks, seed, X.art_seed(seed, mdl[picks[0]]['path']) if picks else 0


def written(m, logs):
    """Every path the payload opened for writing (or created), renamed (both names) or unlinked in the logged calls (lists of calls): the rule of docs/modules/dailymix.md, the stock Import reads only the card's _explaylist_data."""
    out = set()
    for log in logs:
        for c in log:
            if c[0] == 'open' and c[2] & 0x303: out.add(c[1])
            elif c[0] == 'rename': out.update(c[1:3])
            elif c[0] in ('unlink', 'mkdir', 'fopen') and (c[0] != 'fopen' or 'w' in c[2] or 'a' in c[2]): out.add(c[1])
    return out


def words_of(rows): return [D.rgb565(px) for row in rows for px in row]


def run(ctx):
    expect = ctx.expect
    raw = os.path.join(WORK, RAW)
    font = Ttf(os.path.join(raw, 'fonts', 'default.ttf'))
    width = lambda t, px: awtk_width(font, t, px)

    # ===== 1. geometry (the design) and constants
    expect(D.DM_X == U.GRID_MARGIN and D.DM_W == U.GRID_COLS * U.GRID_COVER + (U.GRID_COLS - 1) * U.GRID_GAP and D.DM_X + D.DM_W == 308,
           'the card spans the two covers of the shelf (x 12..308) inside the 310 px scroll view')
    expect((D.DM_HEAD_TOP, D.DM_HEAD_H, D.DM_HEAD_PX, D.DM_HEAD_X) == (U.SH_HEAD_TOP, U.SH_HEAD_H, U.SH_HEAD_PX, U.SH_HEAD_X) and D.DM_HEAD_W < U.SH_HEAD_W
           and D.DM_TOP == U.SH_TOP and D.DM_W_VIEW == U.SH_W, 'the section header and the card top are the Recently Played shelf\'s')
    expect(D.DM_DISC >= 44 and D.DM_DISC_X + D.DM_DISC <= D.DM_W - 10 and D.DM_DISC_Y + D.DM_DISC <= D.DM_H - 10, 'the play disc is a 44 px touch target at least, 10 px inside the card')
    expect(D.DM_PAD + D.DM_SUB_W + 12 <= D.DM_DISC_X, 'the artist lines stop 12 px before the disc')
    expect(D.DM_TITLE_Y1 + D.DM_TITLE_PITCH == D.DM_TITLE_Y2 and D.DM_TITLE_Y2 + D.DM_TITLE_PITCH + D.DM_TITLE_GAP == D.DM_SUB_Y
           and D.DM_SUB_Y + D.DM_SUB_LINES * D.DM_SUB_PITCH + D.DM_BOT_PAD == D.DM_H and D.DM_TITLE_Y1 >= 60, 'the title and artist boxes stack from the card bottom and leave 60 px of free art above')
    expect(D.DM_SEC_H == D.DM_TOP + D.DM_H + D.DM_BOTTOM and D.DM_R * 2 < D.DM_H, 'section height')
    names = ('DM_X', 'DM_W', 'DM_H', 'DM_R', 'DM_TOP', 'DM_BOTTOM', 'DM_SEC_H', 'DM_PAD', 'DM_TITLE_PX', 'DM_TITLE_PITCH', 'DM_TITLE_W', 'DM_TITLE_Y1', 'DM_TITLE_Y2',
             'DM_SUB_PX', 'DM_SUB_PITCH', 'DM_SUB_LINES', 'DM_SUB_Y', 'DM_SUB_W', 'DM_DISC', 'DM_DISC_X', 'DM_DISC_Y', 'DM_MAX_NAMES', 'DM_BUSY_X', 'DM_BUSY_Y')
    expect(all(O[k] == getattr(D, k) for k in names) and O['DM_ZONE_Y'] == D.ZONE_Y and O['DM_RAMP'] == D.RAMP,
           f'patch/offsets.inc DM_* equal tools/pod_dailymix.py ({[k for k in names if O[k] != getattr(D, k)]})')
    expect(O['DM_X'] == O['GRID_MARGIN'] and O['DM_TOP'] == O['SH_TOP'] and O['DM_W'] == 2 * O['GRID_COVER'] + O['GRID_GAP'] and O['DM_SEC_H'] == O['DM_TOP'] + O['DM_H'] + O['DM_BOTTOM'],
           'the payload\'s card is the shelf\'s extent')
    expect(X.SONGS == 25 and X.MIN_SONGS <= X.SONGS and X.PER_ARTIST == 2 and X.PER_ALBUM == 2 and X.MAX_NAMES == D.DM_MAX_NAMES and (X.W, X.H) == (W, H)
           and O['DM_NAME'] == 96 and X.ART_HEAD == 16 and X.JITTER & (X.JITTER - 1) == 0, 'pod_mix.py reads the mix constants from offsets.inc (about 25 songs, 2 per artist and per album)')
    expect(O['DM_START_MS'] > 5000 == O['RC_RESOLVE_MS'] or O['DM_START_MS'] > O['RC_RESOLVE_MS'], 'a mix is made only after the boot guard\'s 5 s window (RC_RESOLVE_MS) has passed since the menu opened')
    src = open(os.path.join(ROOT, 'patch', 'dailymix.c')).read()
    stock_pl = ('addPlayList', 'deletePlaylist', 'getPlayListMaxId', 'checkPlayListExist', 'deleteAllMusicByPlaylist', 'PL_MARK', 'allmusic_page', 'CLASS_PLAYLIST', 'NAV_TITLE', 'PDEQ_PLAYLIST')
    save_at, save_end = src.index('/* The Add disc\'s playlist:'), src.index('static int dp_on_add(')
    outside = src[:save_at] + src[save_end:]
    only_save = ('addPlayList', 'getPlayListMaxId', 'checkPlayListExist', 'createPlayListItem', 'PDEQ_PLAYLIST', 'CLASS_PLAYLISTS', 'NAV_TITLE', 'CLASSINFO')
    expect(not [w for w in stock_pl + only_save if w in outside] and all(w in src[save_at:save_end] for w in ('addPlayList', 'getPlayListMaxId', 'checkPlayListExist', 'createPlayListItem'))
           and 'deletePlaylist' not in src and 'deleteAllMusicByPlaylist' not in src and 'allmusic_page' not in src and 'PL_MARK' not in src and 'CLASS_PLAYLIST_SONGS' not in src,
           'the mix is never a stock playlist but the one-off copy the Add disc saves: the playlist-table calls, the playlist list and the title / classinfo handling exist only in the Add disc code (dp_name .. dp_save: the lookup that shows its check, the save; no delete, no marker, no stock page, the job never touches them)')
    expect(all(n in pod.FUNCTIONS for n in ('createPlayListItem', 'checkPlayListExist', 'getPlayListMaxId', 'addPlayList')) and not [n for n in ('deletePlaylist', 'deleteAllMusicByPlaylist') if n in pod.FUNCTIONS],
           'tools/pod.py pins exactly the four calls the Add disc needs')
    table = re.search(r'static\s+const\s+unsigned\s+short\s+dm_lin\s*\[\s*256\s*\]\s*=\s*\{([^}]*)\}', src, re.S)
    expect(table is not None and [int(n) for n in re.findall(r'\d+', table.group(1))] == D.LIN16,
           'patch/dailymix.c carries every sRGB table value from tools/pod_dailymix.py --c-table')
    expect(len(set(D.LIN16)) > 200 and D.LIN16[0] == 0 and D.LIN16[255] == 65535 and D.lum16((255, 255, 255)) == 65535, 'the table runs from 0 to 65535, white\'s luminance is 1.0')

    # ===== 2. the generator, the design checks (Python)
    tones = [(70, 110, 190), (190, 90, 120), (60, 140, 150)]
    a, sa = D.art(tones, 7); b, sb = D.art(tones, 7); c, _ = D.art(tones, 8); dd, _ = D.art(tones[::-1], 7)
    expect(a == b and sa == sb, 'the art is a pure function of (tones, seed)')
    expect(a != c and a != dd, 'another seed or another tone order gives another card')
    expect(len(a) == D.DM_H and all(len(r) == D.DM_W for r in a), 'the art is 296 x 220')
    expect(all(px[0] == ((px[0] >> 3) << 3 | px[0] >> 5) and px[1] == ((px[1] >> 2) << 2 | px[1] >> 6)
               and px[2] == ((px[2] >> 3) << 3 | px[2] >> 5) for r in a[::7] for px in r[::5]), 'every pixel is an RGB565 value expanded to 8 bits')
    expect(D.xorshift32(1) == 270369 and D.xorshift32(D.xorshift32(1)) == 67634689, 'xorshift32 is the standard 13/17/5 generator (the C code uses the same)')
    prep = [D.tone_prep(t) for t in ((255, 255, 255), (0, 0, 0), (128, 128, 128), (255, 0, 0), (10, 10, 40), (250, 250, 210), (200, 100, 100), (30, 30, 31))]
    expect(prep[0] == (168,) * 3 and prep[1] == (63,) * 3 and prep[2] == (128,) * 3, f'greys keep to lightness 0.25..0.66 ({prep[:3]})')
    expect(all(D.L_MIN * 5.1 - 3 <= sum((min(p), max(p))) <= D.L_MAX * 5.1 + 3 for p in prep[3:7]), f'colourful tones land in lightness 0.30..0.56 ({prep[3:7]})')
    palettes = [t for _, t in __import__('preview_dailymix').PALETTES]
    palettes += [[(255, 255, 255)] * 2, [(0, 0, 0)] * 2, [(255, 255, 0), (0, 255, 0), (255, 255, 120)], [(255, 255, 255), (250, 250, 210)], [(0, 255, 255), (255, 0, 255), (255, 255, 0), (255, 255, 255)]]
    rnd = random.Random(1234)
    palettes += [[tuple(rnd.randrange(256) for _ in range(3)) for _ in range(rnd.randrange(2, 5))] for _ in range(60)]
    worst = (99, None)
    for i, t in enumerate(palettes):
        rows, a64 = D.art(t, 1000 + i)
        for ink in (D.TITLE_RGB, D.SUB_RGB):
            cr = D.zone_contrast(rows, ink)
            if cr < worst[0]: worst = (cr, t)
    expect(worst[0] >= D.DM_CONTRAST, f'white title and off-white artist text reach {D.DM_CONTRAST}:1 over the art on {len(palettes)} palettes (worst {worst[0]:.2f}:1 {worst[1]})')
    expect(D.art([(30, 30, 45)] * 2, 3)[1] == 10, 'a dark card gets the minimum scrim (10/64)')
    cov = D.corner_cover(D.DM_R)
    expect(cov[0] == 255 and cov[-1] == 0 and len(cov) == 144 and all(cov[y * 12 + x] >= cov[y * 12 + x + 1] for y in range(12) for x in range(11)), 'the corner coverage: opaque outside the arc, none inside, falling along a row')

    # ===== 3. the texts
    expect(all(set(v) == set(D.LOCALES) for v in D.TEXT.values()) and set(D.TEXT) == {'Made for You', 'Daily Mix', 'Regenerate Daily Mix', '%s and more', '%s, %s'} == set(pod_i18n.DAILY_KEYS),
           'five keys, 13 locales each, in tools/pod_i18n.py')
    expect(all(D.TEXT['%s and more'][l].count('%s') == 1 and D.TEXT['%s and more'][l].count('%') == 1 and D.TEXT['%s, %s'][l].count('%s') == 2 and D.TEXT['%s, %s'][l].count('%') == 2
               for l in D.LOCALES), 'the "and more" template has one %s, the join template two')
    probe = StbText(font, 20)
    missing = {c: l for l in D.LOCALES for k in D.TEXT for c in D.TEXT[k][l] if c not in ' %s' and probe.box(c) is None}
    expect(not missing, f'every character of the texts has ink in the font ({missing})')
    homeset = awtk_ui.parse(open(os.path.join(raw, 'ui', 'm1plus_homeset.bin'), 'rb').read())
    rows = [w for w in homeset.find('pod_scrollview').children if w.type == 'list_item']
    lab_w = lambda r: next(w for w in r.children if w.type == 'hscroll_label').w
    expect([r.name for r in rows] == [f'pod_row{i}' for i in range(5)] and lab_w(rows[1]) == lab_w(rows[0]), 'Settings > Home Screen has five rows (Regenerate Daily Mix the last); the Daily Mix switch row has the Recent Albums row\'s label box')
    sw_room, act_room = lab_w(rows[1]), lab_w(rows[4])
    over = []
    for l in D.LOCALES:
        if width(D.tr(l, 'Made for You'), D.DM_HEAD_PX) > D.DM_HEAD_W - 4: over.append((l, 'header'))
        if any(width(t, D.DM_TITLE_PX) > D.DM_TITLE_W for t in D.title_lines(D.tr(l, 'Daily Mix'))): over.append((l, 'title'))
        if width(D.tr(l, 'Daily Mix'), 21) > sw_room: over.append((l, 'switch row'))
        if width(D.tr(l, 'Regenerate Daily Mix'), 21) > act_room: over.append((l, 'action row'))
        lines = D.artist_lines(lambda t: width(t, D.DM_SUB_PX), ['Radiohead', 'Björk', 'Air', 'Portishead'], l)
        if not (1 <= len(lines) <= D.DM_SUB_LINES and all(width(t, D.DM_SUB_PX) <= D.DM_SUB_W for t in lines)): over.append((l, 'artists'))
        long_names = ['Rimsky-Korsakov Philharmonic Orchestra of Saint Petersburg', 'Beethoven', 'Bach']
        lines = D.artist_lines(lambda t: width(t, D.DM_SUB_PX), long_names, l)
        if not (1 <= len(lines) <= D.DM_SUB_LINES and all(width(t, D.DM_SUB_PX) <= D.DM_SUB_W for t in lines)): over.append((l, 'long artists'))
    expect(not over, f'header, title lines, both Home Screen rows ({sw_room} / {act_room} px) and the artist lines fit in all 13 languages ({over})')
    expect(D.title_lines('Daily Mix') == ['Daily', 'Mix'] and D.title_lines('Tagesmix') == ['Tagesmix'], 'the title splits at its first space')
    expect(D.artist_lines(lambda t: len(t) * 6, ['Radiohead', 'Björk', 'Air', 'Portishead'], 'en_US') == ['Radiohead, Björk, Air and more'], 'at most three names, as "A, B, C and more"')
    expect(D.join_names('zh_CN', ['甲', '乙', '丙']) == '甲、乙、丙' and D.join_names('en_US', ['a', 'b']) == 'a, b' and D.join_names('en_US', ['a']) == 'a', 'the names are joined by the locale\'s template')

    # ===== 4. assets: the section, the Home Screen rows, the disc images
    menu = awtk_ui.parse(open(os.path.join(raw, 'ui', 'm1plus_menu.bin'), 'rb').read())
    sv_n = menu.find('pod_scrollview')
    sec = sv_n.find('pod_daily')
    kids = [c.name for c in sv_n.children]
    expect(kids[-3:] == ['pod_daily', 'pod_shelf', 'pod_pad'], f'the section sits after the rows and before the shelf ({kids[-4:]})')
    expect(sec.type == 'view' and (sec.x, sec.y, sec.w, sec.h) == (0, 0, U.SH_W, D.DM_SEC_H) and sec.get('visible') == 'false' and sec.get('sensitive') == 'false',
           'pod_daily is a 310 x 272 view, hidden and insensitive in the asset')
    expect([c.name for c in sec.children] == ['pod_dm_head', 'pod_dm_busy', 'pod_dm_card', 'pod_dm_play', 'pod_dm_title', 'pod_dm_sub'], 'its children: the header, the busy mark, the card, the disc, the two style labels')
    head, card, play = sec.find('pod_dm_head'), sec.find('pod_dm_card'), sec.find('pod_dm_play')
    busy = sec.find('pod_dm_busy')
    expect(busy.type == 'image' and busy.get('image') == 'dm_sync' and busy.get('visible') == 'false' and busy.get('sensitive') == 'false' and (busy.x, busy.y, busy.w, busy.h) == (285, 20, 16, 16)
           and head.x + head.w + D.DM_BUSY_GAP == busy.x and busy.x + busy.w // 2 == U.CHEV_X + 5, 'pod_dm_busy is a 16 px image, hidden and insensitive, centred under the list chevron (x 288..298), the header label ends 6 px before it')
    expect(head.type == 'hscroll_label' and head.get('tr_text') == 'Made for You' and head.get('sensitive') == 'false' and (head.x, head.y, head.w, head.h) == (10, 17, 269, 22),
           'the header is the shelf\'s, 31 px narrower for the busy mark: a 269 x 22 insensitive label with the key "Made for You"')
    expect((card.x, card.y, card.w, card.h) == (12, 44, 296, 220) and card.type == 'view' and card.get('sensitive') != 'false' and card.get('visible') != 'false',
           'the card is 296 x 220 at (12, 44), sensitive')
    expect(play.type == 'button' and (play.x, play.y, play.w, play.h) == (12 + 234, 44 + 158, 48, 48) and play.get('style:normal:icon') == 'dm_disc' and play.get('style:pressed:icon') == 'dm_disc_down',
           'the disc is a 48 px glass button at (246, 202) in the section (14 px from the card\'s right and bottom edges), a later sibling of the card')
    expect(all(sec.find(n).get('visible') == 'false' and sec.find(n).get('sensitive') == 'false' for n in ('pod_dm_title', 'pod_dm_sub'))
           and sec.find('pod_dm_title').get('style:normal:font_size') == '36' and sec.find('pod_dm_sub').get('style:normal:font_size') == '16'
           and sec.find('pod_dm_sub').get('style:normal:text_color') == '#EBEBEB', 'the style labels are hidden, insensitive, 36 px white and 16 px #EBEBEB')
    xx = os.path.join(raw, 'images', 'xx')
    from PIL import Image
    for n, pressed in (('dm_disc', False), ('dm_disc_down', True)):
        im = Image.open(os.path.join(xx, n + '.png')).convert('RGBA')
        ref = mod_icons.glass_image(48, 48, 24, pressed)
        ring = [(x, y) for y in range(48) for x in range(48) if (x - 23.5) ** 2 + (y - 23.5) ** 2 > 15 ** 2]
        expect(im.size == (48, 48) and all(im.getpixel(p) == ref.getpixel(p) for p in ring) and im.getpixel((0, 0))[3] == 0 and (255, 255, 255, 255) in im.getdata()
               and open(os.path.join(xx, n + '.png'), 'rb').read() == open(os.path.join(mod_icons.PNG, n + '.png'), 'rb').read(),
               f'{n}.png: the 48 px glass disc (pressed={pressed}) with the white play glyph in the middle, the committed file')
    expect(set(n for n in ('dm_disc', 'dm_disc_down') if os.path.exists(os.path.join(mod_icons.PNG, n + '.png'))) == {'dm_disc', 'dm_disc_down'}
           and {'dm_disc', 'dm_disc_down'} <= set(mod_icons.pod_names()), 'the disc images are committed and added by the build')
    regen_row, daily_row = rows[4], rows[1]
    expect(not [w for w in regen_row.children if w.type == 'image' and w.name != 'pod_icon'] and any(w.name == 'pod_switch1' for w in daily_row.children) and not any(w.name.startswith('pod_switch') for w in regen_row.children)
           and homeset.find('pod_note3') is not None and homeset.find('pod_note3').get('sensitive') == 'false' and homeset.find('pod_row4').get('style:normal:bg_image') == 'pod_cd_single',
           'Regenerate Daily Mix is an action row without a chevron or a switch, in a card of its own (a single piece) and note (pod_note3) at the end of the page, the payload hides with it; Daily Mix has the switch pod_switch1')
    expect(pod_pages.ACT_DAILY in pod_pages.SWITCH_ACTIONS and pod_pages.ACT_REGEN in pod_pages.NO_CHEVRON_ACTIONS and pod_pages.ACT_REGEN not in pod_pages.SWITCH_ACTIONS,
           'the rows\' kinds in tools/pod_pages.py')

    # ===== 5. the switch file
    m = Machine(); m.dirs.add('/mnt/data')
    expect(m.call(PSYMS['dailymix_setting'], count=100000) == 1, 'no file: the card is on')
    for content, want in ((b'1\n', 1), (b'0\n', 0), (b'0', 0), (b'', 1), (b'x', 1), (b'10', 1), (b'0x', 1), (b'00', 1)):
        m.fs[SET] = content
        expect(m.call(PSYMS['dailymix_setting'], count=100000) == want, f'switch file {content!r}: {"on" if want else "off"}')
    m.fs[SET] = b'1\n'
    expect(m.call(PSYMS['dailymix_toggle'], count=400000) == 0 and m.fs[SET] == b'0\n' and ('rename', SET_TMP, SET) in m.calls and m.call(PSYMS['dailymix_toggle'], count=400000) == 1 and m.fs[SET] == b'1\n',
           'a tap flips the setting and saves it atomically (temp file, rename)')
    m.fail.add(('write', SET_TMP)); before = m.fs[SET]
    expect(m.call(PSYMS['dailymix_toggle'], count=400000) == 0xffffffff and m.fs[SET] == before, 'a failed save changes nothing and answers -1')

    # ===== 6. the mix file and the art file, read strictly
    day0 = day_of(1800000000)
    TONES3 = [(70, 110, 190), (190, 90, 120), (60, 140, 150)]
    def mk(day=day0, seed=0x1234abcd, aseed=0x0badf00d, regen=0, tones=TONES3, names=('Radiohead', 'Björk', 'Air'), paths=PATHS): return X.dump_mix(day, seed, aseed, regen, tones, list(names), list(paths))
    good = mk()
    expect(X.parse_mix(good) == (day0, 0x1234abcd, 0x0badf00d, 0, 25, TONES3, [b'Radiohead', 'Björk'.encode(), b'Air'], [p.encode() for p in PATHS]), 'the model reads its own file')
    expect(good.startswith(b'M1X2\n') and good.count(b'\n') == 4 + 25 and good.split(b'\n')[0:1] == [b'M1X2'] and b'.m3u' not in good.lower(), 'M1X2, the header, the tones, the names, then 25 paths one a line; the paths are plain lines, no playlist syntax')
    p255, p256 = '/' + 'a' * 254, '/' + 'a' * 255
    corpus = [good,
              good.replace(b'M1X2', b'M1X1'), good[:-1], good + b'\n', good + b'x', b'', good[:5], good.replace(b'\t', b' ', 1), good.replace(b'1234abcd', b'1234ABCD'),
              good.replace(b'1234abcd', b'1234abc'), good.replace(b'1234abcd', b'00000000'), good.replace(f'{day0}'.encode(), b'0', 1), good.replace(f'{day0}'.encode(), b'0' + f'{day0}'.encode(), 1),
              good.replace(b'\t0\t25\n', b'\t256\t25\n'), good.replace(b'\t0\t25\n', b'\t0\t24\n'), good.replace(b'\t0\t25\n', b'\t0\t26\n'), good.replace(b'\t0\t25\n', b'\t0\t10\n'), good.replace(b'\t0\t25\n', b'\t0\t025\n'),
              good.replace(b' ', b'', 1), good.replace(b'46 6e', b'46'), good.replace(b'Radiohead', b''), good.replace(b'Radiohead', b'Radio\x01head'),
              good.replace(b'\tAir', b''), good.replace(b'Air', b'Air\tFour'), good.replace(b'Air', b'A' * 95), good.replace(b'Air', b'A' * 96), good.replace(b'Air', b'A' * 300),
              good.replace(b'\n', b'\r\n'), good.replace(b'46', b'4G', 1), b'M1X2\n' + b'\n' * 5, b'M1X2\n' + b'\n' * 40,
              mk(regen=255, tones=[(1, 2, 3), (4, 5, 6)], names=['x'], paths=PATHS[:10]), mk(paths=PATHS[:9]), mk(paths=PATHS + ['/mnt/mmc/extra.flac']),
              mk(tones=[(1, 2, 3)] * 5, names=['x']), mk(tones=[(1, 2, 3)], names=['x']), mk(tones=[(1, 2, 3)] * 4, names=['a', 'b', 'c', 'd']),
              mk(paths=[p255] + PATHS[1:]), mk(paths=[p256] + PATHS[1:]), mk(paths=['/a b/ü ß/日本語.flac'] + PATHS[1:]), mk(paths=[PATHS[0] + '\x7f'] + PATHS[1:]),
              good.replace(PATHS[0].encode(), b'/x\x01y'), good.replace(PATHS[0].encode() + b'\n', b'\n', 1), good.replace(PATHS[0].encode(), b'/x\ty'), good.replace(PATHS[24].encode() + b'\n', PATHS[24].encode()),
              good.replace(PATHS[24].encode() + b'\n', b'') + b'\n']
    mm = DM()
    seen = []
    for k, data in enumerate(corpus):
        mm.fs[MIX] = data; mm.fs.pop(ART, None); mm.hide_all()
        mm.start_dm()
        want = X.parse_mix(data) is not None
        seen.append((mm.up(), want))
    expect(all(g == w for g, w in seen), f'the payload accepts exactly the files the model accepts, {sum(w for _, w in seen)} valid of {len(corpus)} ({[(k, g, w) for k, (g, w) in enumerate(seen) if g != w]})')
    mm.fs.pop(MIX, None); mm.hide_all(); mm.start_dm()
    expect(not mm.up(), 'no mix file: the section stays hidden and the menu is as it was')
    mm.fs[MIX] = good; mm.fs[SET] = b'0\n'; mm.hide_all(); mm.start_dm()
    expect(not mm.up(), 'a valid mix with the switch off: hidden')
    mm.fs[SET] = b'1\n'; mm.hide_all(); mm.start_dm()
    st = mm.stack()
    expect(mm.up() and st.index('daily') + 1 == st.index('shelf') and st[-1] == 'pad' and st.index('daily') == 8, f'a valid mix with the switch on: the section is shown after the shown rows, right before the shelf ({st})')
    art_ok = X.dump_art([0x1234] * (W * H), 0x0badf00d)
    m3 = DM(); m3.fs[MIX] = good; m3.fs[ART] = art_ok; m3.fs[SET] = b'0\n'; m3.start_dm(); m3.clock = 1
    m3.call(PSYMS['dm_tick'], a0=0, count=2000000)
    expect(not m3.bitmaps and 'timer_add' not in m3.names() and not m3.up(), 'with the card off the art file is not read and no bitmap is made (the timer ends)')
    m3.fs[SET] = b'1\n'; m3.fire(EVT_FG)
    m3.ticks()
    expect(len(m3.bitmaps) == 1 and m3.up(), 'switched on, the menu in front again: the section is up and its art is read')
    expect(X.parse_art(art_ok, 0x0badf00d) is not None and X.parse_art(art_ok, 1) is None and X.parse_art(art_ok[:-1], 0x0badf00d) is None and X.parse_art(b'M1XB' + art_ok[4:], 0x0badf00d) is None
           and X.parse_art(art_ok[:100] + b'\0\0' + art_ok[102:], 0x0badf00d) is None and len(art_ok) == 16 + W * H * 2, 'the art file model: size, magic, art seed and checksum')
    # the card reads a valid art file into its bitmap (the corners blended into black); a bad one makes the art again
    words = [(x * 7 + y * 3) & 0xffff for y in range(H) for x in range(W)]
    mm = DM(count=PERF); mm.fs[MIX] = good; mm.fs[ART] = X.dump_art(words, 0x0badf00d); mm.start_dm(); mm.clock = 1
    c0 = mm.ticks()
    bm = [b for b in mm.bitmaps]
    data, bw, bh = mm.bitmaps[bm[-1]]
    px = struct.unpack(f'<{W * H}I', bytes(mm.u.mem_read(data, W * H * 4)))
    exp_rows = [[D.expand565(words[y * W + x]) for x in range(W)] for y in range(H)]
    D.round_corners(exp_rows)
    exp_px = [0xff000000 | r | g << 8 | b_ << 16 for row in exp_rows for r, g, b_ in row]
    expect((bw, bh) == (W, H) and list(px) == exp_px and len(c0) == 1,
           f'a valid art file is read into the 296 x 220 bitmap, expanded from RGB565 with the four 12 px corners blended into black, in one tick ({c0[0]} instructions)')
    expect(px[0] == 0xff000000 and px[W * H - 1] == 0xff000000 and px[W * (H - 1)] == 0xff000000 and px[W - 1] == 0xff000000 and px[W // 2] != 0xff000000, 'the corner pixels are black, the top middle is not')
    for name, data_ in (('wrong art seed', X.dump_art(words, 5)), ('short', art_ok[:-2]), ('bad checksum', art_ok[:200] + b'\x55' + art_ok[201:]), ('bad magic', b'XXXX' + art_ok[4:])):
        m2 = DM(); m2.fs[MIX] = good; m2.fs[ART] = data_; m2.start_dm(); m2.clock = 1
        cs = m2.ticks()
        wrote = m2.fs.get(ART)
        expect(len(cs) > 5 and wrote and X.parse_art(wrote, 0x0badf00d) is not None, f'{name}: the art is made again from the mix\'s tones and seed and written ({len(cs)} ticks)')

    # ===== 7. the art in C against the model, pixel for pixel
    arts = [(tones, 0x0badf00d), ([(30, 30, 45)] * 2, 3), ([(255, 255, 255), (250, 250, 210)], 99), ([(255, 255, 0), (0, 255, 0), (255, 255, 120)], 12345),
            ([(0, 255, 255), (255, 0, 255), (255, 255, 0), (255, 255, 255)], 0xdeadbeef), ([(128, 128, 128), (60, 60, 60), (200, 200, 200)], 7), ([(10, 10, 12)] * 2, 0)]
    arts += [([tuple(rnd.randrange(256) for _ in range(3)) for _ in range(rnd.randrange(2, 5))], rnd.getrandbits(32) | 1) for _ in range(1)]
    worst_cost, total_cost, nart = 0, 0, 0
    ma = DM(count=PERF)
    bad = []
    for k, (tn, seed) in enumerate(arts):
        mix = X.dump_mix(day0, 0x1111, seed & 0xffffffff, 0, tn, ['Radiohead'], PATHS)
        ma.fs[MIX] = mix; ma.fs.pop(ART, None); ma.hide_all(); ma.start_dm(); ma.clock = 1
        cs = ma.ticks()
        rows, a64 = D.art(tn, seed)
        want = X.dump_art(words_of(rows), seed & 0xffffffff)
        got = ma.fs.get(ART)
        if PERF: total_cost += sum(cs); worst_cost = max(worst_cost, max(cs)); nart += 1
        data, _, _ = ma.bitmaps[list(ma.bitmaps)[-1]]
        pxs = struct.unpack(f'<{W * H}I', bytes(ma.u.mem_read(data, W * H * 4)))
        er = [[tuple(px) for px in row] for row in rows]; D.round_corners(er)
        if got != want or list(pxs) != [0xff000000 | r | g << 8 | b_ << 16 for row in er for r, g, b_ in row]: bad.append((k, got is not None and got == want))
    expect(not bad, f'the card art made by the payload equals pod_dailymix.art + the blended corners, byte for byte (the file) and pixel for pixel (the bitmap), on {len(arts)} palettes and seeds ({bad})')
    if PERF:
        print(f'  (art: {total_cost // nart} instructions for one card on average over {nart}, at most {worst_cost} in one tick of {O["DM_ROWS"]} rows)')
        expect(worst_cost < 3_000_000, f'one art tick stays under 3 million instructions ({worst_cost})')

    # ===== 8. the whole job on a library
    songs, rr = library()
    plays, rec_, fav = history(songs, rr)
    tz = 3600 * 5
    def fresh(songs_=songs, plays_=plays, rec__=rec_, fav_=fav, tz_=tz, wall=1800000000, mixfile=None, artfile=None, setting=None, start=True, count=False):
        m = DM(count=count); m.wall, m.tz = wall, tz_
        stock_world(m, songs_, plays_, rec__, fav_)
        if mixfile is not None: m.fs[MIX] = mixfile
        if artfile is not None: m.fs[ART] = artfile
        if setting is not None: m.fs[SET] = setting
        m.clock = 1000
        if start: m.start_dm()
        return m
    def run_job(m, after=START_MS + 1000):
        m.clock = after
        return m.ticks(limit=600)

    day = day_of(1800000000, tz)
    mdl, picks, seed, aseed = expect_mix(None, songs, plays, rec_, fav, day, 0)
    m = fresh(count=PERF)
    m.screen(False); m.clock = START_MS + 1000; m.call(PSYMS['dm_tick'], count=2000000)
    expect([c[2] for c in m.calls if c[0] == 'timer_add'] == [1000] and not any(c[0] == 'loadLocalClassList' for c in m.calls), 'dark Daily Mix defers pending work with one one-second check')
    m.screen(True); m.call(PSYMS['dm_tick'], count=2000000)
    expect([c[2] for c in m.calls if c[0] == 'timer_add'] == [O['DM_TICK_MS']], 'first lit Daily Mix check starts the pending job at its normal cadence')
    m.call(PSYMS['dm_tick'], count=2000000)
    expect(any(c[0] == 'loadLocalClassList' for c in m.calls), 'the resumed job loads its first list')
    m.screen(False); m.call(PSYMS['dm_tick'], count=2000000)
    expect([c[2] for c in m.calls if c[0] == 'timer_add'] == [1000] and not any(c[0] in ('loadLocalClassList', 'widget_load_image') for c in m.calls), 'an active job pauses with one one-second check')
    m.fire(EVT_DESTROY); m.call(PSYMS['dm_tick'], count=2000000)
    expect(not m.calls, 'a stray Daily Mix timer after destroy does nothing')
    m = fresh(count=PERF)
    expect(not m.up(), 'no mix yet: the card is hidden')
    # nothing is made inside the boot guard's window: the first ticks only arm the timer
    m.clock = 3000; m.call(PSYMS['dm_tick'], a0=0, count=2000000)
    expect(not [c for c in m.calls if c[0] in ('loadLocalClassList',)] and ('timer_add', PSYMS['dm_tick'], START_MS - 2000) in [(c[0], c[1], c[2]) for c in m.calls if c[0] == 'timer_add'],
           f'before DM_START_MS nothing is read; the timer waits for the rest of it ({[c for c in m.calls if c[0] == "timer_add"]})')
    found = put_tones(m, songs, picks, mdl)
    costs = run_job(m)
    want_tones = X.fill_tones(found, seed)
    names = X.top_artists(mdl, picks)
    mpaths = lambda m_: [p.decode('utf-8') for p in X.parse_mix(m_.fs[MIX])[7]]
    expect(mpaths(m) == [mdl[i]['path'] for i in picks] and len(picks) == 25, f'the mix file holds the model\'s 25 picks\' paths in play order ({len(mpaths(m))} paths)')
    arts_ = [mdl[i]['artist'] for i in picks]; albs = [mdl[i]['album'] for i in picks]
    expect(max(arts_.count(a) for a in set(arts_)) <= 2 and max(albs.count(a) for a in set(albs)) <= 2 and all(a != b for a, b in zip(arts_, arts_[1:])),
           'at most 2 songs of an artist and 2 of an album, no artist twice in a row')
    expect(m.fs.get(MIX) == X.dump_mix(day, seed, aseed, 0, want_tones, names, [mdl[i]['path'] for i in picks]), f'the mix file: day {day}, the model\'s seed, art seed, the covers\' tones, the top artists, the 25 paths ({m.fs.get(MIX)[:60]})')
    classes = {c[1] for log in m.tick_log for c in log if c[0] == 'loadLocalClassList'}
    expect(classes <= {CLS_LIB, CLS_REC, CLS_OFT, CLS_FAV, CLS_ALB}, f'the job reads the library, Most Played, Recently Played, Favourites and the albums and never the stock playlists ({[hex(c) for c in classes]})')
    wr = written(m, m.tick_log)
    expect({MIX, MIX_TMP, ART, ART_TMP} <= wr and all((p == CARD_DIR or p.startswith(CARD_DIR + '/')) and not p.lower().endswith(('.m3u', '.m3u8')) and '_explaylist_data' not in p for p in wr),
           f'every file the job writes or renames is under /mnt/mmc/.m1plus (or is its directory) and is no .m3u / .m3u8 the stock Import could read ({sorted(wr)})')
    expect(CARD_DIR not in fresh(start=False).dirs and CARD_DIR in wr and CARD_DIR in m.dirs and MIX_DIR in wr and MIX_DIR in m.dirs
           and m.calls.index(('mkdir', CARD_DIR)) < m.calls.index(('mkdir', MIX_DIR)),
           'the card had no mix directory: the writer made the card folder, then daily-mix in it (mkdir), and the job committed into it')
    rows_art, _ = D.art(want_tones, aseed)
    expect(m.fs.get(ART) == X.dump_art(words_of(rows_art), aseed), 'the art file is the model\'s art for the mix\'s tones and art seed')
    expect(m.up() and not [c for c in m.calls if c[0] == 'deletePlaylist'], 'the card is shown with the new mix')
    if PERF:
        expect(len(costs) < 120 and max(costs) < 5_000_000, f'the job: {len(costs)} ticks, the most expensive {max(costs)} instructions, {sum(costs)} in all (30 ms apart)')
        print(f'  (daily mix, {len(songs)} songs: {len(costs)} ticks, {sum(costs)} instructions in all, at most {max(costs)} in one tick; art {O["DM_ROWS"]} rows a tick)')
    # the same day again: nothing to do
    m.call(PSYMS['dm_tick'], a0=0, count=2000000)
    expect('timer_add' not in m.names() and not [c for c in m.calls if c[0] == 'loadLocalClassList'], 'the same day: no job')
    m.fire(EVT_FG)
    expect('timer_add' not in m.names(), 'the menu in front again on the same day: no job, no timer')
    main_m = m

    # ---- podcast episodes (docs/modules/podcasts.md) are no candidates: a library with a dozen of them, each the most played song of the card, gives the same mix as the library without
    eps_p = [dict(path=f'/mnt/mmc/Podcasts/Show {i % 3}/ep{i:02d}.mp3', artist='Narrator', album='A Show', title=f'Episode {i}', name=f'ep{i:02d}.mp3') for i in range(12)]
    plays_p = dict(plays); plays_p.update({len(songs) + i: 300 for i in range(12)})
    mp = fresh(songs_=songs + eps_p, plays_=plays_p)
    put_tones(mp, songs, picks, mdl)
    run_job(mp)
    expect(mpaths(mp) == [mdl[i]['path'] for i in picks] and not any('/Podcasts/' in p for p in mpaths(mp)),
           'the Daily Mix skips podcast episodes (a path under /mnt/mmc/Podcasts/): the mix is the one of the library without them')

    # ---- a previous mix: yesterday's is shown while the new one is made and replaced by the new file; an old "Daily Mix" stock playlist is not our business (no cleanup code)
    ymix0 = X.dump_mix(day - 1, 5, 6, 3, [(1, 2, 3), (4, 5, 6)], ['Old'], PATHS[:10])   # (yesterday was made three times)
    m = fresh(mixfile=ymix0)
    expect(m.up(), 'yesterday\'s mix is shown while the new one is made')
    put_tones(m, songs, picks, mdl)
    run_job(m)
    parsed = X.parse_mix(m.fs[MIX])
    expect(parsed and parsed[0] == day and parsed[3] == 0 and parsed[1] == seed and mpaths(m) == [mdl[i]['path'] for i in picks] and m.fs[MIX] != ymix0,
           'the new day replaces the file: the day\'s seed, regeneration 0 (a new day starts again), the model\'s picks')
    expect(not [c for log in m.tick_log for c in log if c[0] == 'loadLocalClassList' and c[1] in (0xf00b, 0xff13)], 'no stock playlist is read (the playlist-table calls are not even pinned: the source check above)')

    # ---- Regenerate (on the machine of the first mix): a new seed, the next regeneration count, a new playlist; two asks are one; with the card off it waits
    m = main_m
    m.call(PSYMS['dailymix_regen'], count=100000)
    expect([c[1] for c in m.calls if c[0] == 'toast'] == ['New mix when Home opens'], 'an accepted ask shows the toast')
    m.call(PSYMS['dailymix_regen'], count=100000)
    m.fire(EVT_FG)
    expect('timer_add' in m.names(), 'Regenerate Daily Mix: the next time the Home menu is in front a timer starts the job')
    m.clock += 1000
    cs = m.ticks(limit=600)
    mdl1, picks1, seed1, aseed1 = expect_mix(None, songs, plays, rec_, fav, day, 1)
    pm = X.parse_mix(m.fs[MIX])
    expect(pm and pm[1] == seed1 and pm[3] == 1 and pm[1] != X.seed_for(day, 0) and mpaths(m) == [mdl1[i]['path'] for i in picks1] and picks1 != picks,
           'regeneration (asked twice): seed of (day, 1), regen count 1, the model\'s other picks, the file replaced')
    m.call(PSYMS['dm_tick'], a0=0, count=2000000)
    expect('timer_add' not in m.names(), 'and nothing more is asked of the next tick')
    m = fresh(setting=b'0\n'); m.call(PSYMS['dm_tick'], a0=0, count=2000000)   # (the one-shot of the start, which arms nothing with the card off)
    m.call(PSYMS['dailymix_regen'], count=100000)
    expect(not [c for c in m.calls if c[0] == 'toast'], 'a refused ask (card off) shows no toast')
    m.fire(EVT_FG); m.clock += 20000; m.fire(EVT_FG)
    expect('timer_add' not in m.names() and MIX not in m.fs, 'with the card off nothing is made, not even for Regenerate')
    m.fs[SET] = b'1\n'; m.fire(EVT_FG)
    expect('timer_add' in m.names(), 'switched on again, the pending Regenerate runs')

    # ---- the clock decides the day (local time) and a clock that is not set makes no mix
    import calendar, datetime
    epoch = datetime.date(1970, 1, 1).toordinal()
    m = fresh(wall=1000); run_job(m)
    expect(MIX not in m.fs, 'a clock that is not set (before 2020) makes no mix')
    for y, mo, dd_, hh, off in ((2027, 1, 1, 12, 0), (2027, 3, 1, 12, 0), (2028, 2, 29, 12, 0), (2028, 3, 1, 12, 0), (2026, 12, 31, 12, 0), (2037, 3, 1, 12, 0), (2021, 6, 15, 12, 0),
                                (2027, 6, 15, 22, 5), (2027, 6, 15, 22, 1), (2027, 6, 15, 2, -3), (2027, 6, 15, 2, -2), (2028, 12, 31, 20, 9)):
        w = calendar.timegm((y, mo, dd_, hh, 0, 0))
        m = fresh(wall=w, tz_=off * 3600, setting=b'0\n')
        v = m.call(PSYMS['dm_today'], count=100000)
        local = datetime.datetime.fromtimestamp(w + off * 3600, datetime.timezone.utc).date()
        expect(v == local.toordinal() - epoch and v == day_of(w, off * 3600), f'dm_today for {y}-{mo:02d}-{dd_:02d} {hh}:00 UTC at UTC{off:+d} is the local day {local} (days since 1970 {v})')


    # ---- a library at the cap (DM_LIB_MAX songs, half of them played, 100 recent, 300 favourites): the model's picks and the cost of every tick
    nb, rb = O['DM_LIB_MAX'], random.Random(5)
    bigl = [dict(path=f'/mnt/mmc/B/{i // 12}/{i}.flac', artist=f'Band {i // 60}', album=f'Disc {i // 12}', title=f'Track number {i}', name=f'{i}.flac') for i in range(nb)]
    plays_b = {i: rb.choice([1, 2, 3, 8, 30, 300]) for i in range(nb) if rb.random() < 0.5}
    rec_b = rb.sample(sorted(plays_b), 100)
    fav_b = set(rb.sample(range(nb), 300))
    m = fresh(songs_=bigl, plays_=plays_b, rec__=rec_b, fav_=fav_b, count=PERF)
    costs_b = run_job(m)
    mdl_b = model(bigl, plays_b, rec_b, fav_b)
    picks_b = X.select(mdl_b, X.seed_for(day, 0))
    expect(mpaths(m) == [mdl_b[i]['path'] for i in picks_b] and len(picks_b) == 25, f'{nb} songs: the same 25 picks as the model')
    if PERF: expect(max(costs_b) < 3_000_000 and len(costs_b) < 160, f'{nb} songs: {len(costs_b)} ticks, {sum(costs_b)} instructions in all, the most expensive tick {max(costs_b)} (3 million at most)')
    wr_b = written(m, m.tick_log)
    expect({MIX, MIX_TMP, ART, ART_TMP} <= wr_b and all((p == CARD_DIR or p.startswith(CARD_DIR + '/')) and not p.lower().endswith(('.m3u', '.m3u8')) and '_explaylist_data' not in p for p in wr_b),
           f'{nb} songs: every file the job writes or renames is under /mnt/mmc/.m1plus (or is its directory) and is no .m3u / .m3u8 ({sorted(wr_b)})')
    if PERF: print(f'  (daily mix, {nb} songs: {len(costs_b)} ticks, {sum(costs_b)} instructions in all, at most {max(costs_b)} in one tick)')

    # ---- failures: yesterday's mix stays whole
    def stays(m, what, mix=None):
        expect(m.fs.get(MIX) == mix and m.up() == (mix is not None), f'{what}: nothing changed (the mix file, the card)')
    ymix = X.dump_mix(day - 1, 5, 6, 0, [(1, 2, 3), (4, 5, 6)], ['Old'], PATHS[:10])
    small = [dict(path=f'/mnt/mmc/S/{i // 7}/{i}.flac', artist=f'Band {i // 7}', album=f'Disc {i // 7}', title=f'T{i}', name=f'{i}.flac') for i in range(X.MIN_LIB)]
    m = fresh(songs_=small[:-1], plays_={}, rec__=(), fav_=(), mixfile=ymix); run_job(m); stays(m, f'a library of {X.MIN_LIB - 1} songs (under MIX_MIN_LIB)', ymix)
    expect(m.call(PSYMS['dailymix_can_regen'], count=100000) == 0, '... and Regenerate is off (Settings dims the row)')
    m.call(PSYMS['dailymix_regen'], count=100000); m.clock += 5000; m.fire(EVT_FG)
    expect('timer_add' not in m.names(), '... so a tap on it asks for no job')
    m = fresh(songs_=[], plays_={}, rec__=(), fav_=(), mixfile=ymix); run_job(m); stays(m, 'an empty library', ymix)
    expect(m.call(PSYMS['dailymix_can_regen'], count=100000) == 0, '... Regenerate is off')
    m = fresh(mixfile=ymix); m.calloc_fail = True; run_job(m); stays(m, 'no memory', ymix)
    expect(m.busy_state() == (False, False), 'no job started: the busy mark stays hidden')
    expect(m.call(PSYMS['dailymix_can_regen'], count=100000) == 1, '... Regenerate stays on (the library was not too small)')
    m.clock += 5000; m.fire(EVT_FG)
    expect('timer_add' not in m.names(), 'a day that failed is not tried again on the next visit (until tomorrow or a restart)')
    m.call(PSYMS['dailymix_regen'], count=100000); m.fire(EVT_FG)
    expect('timer_add' in m.names(), '... but Regenerate asks again')
    m = fresh(mixfile=ymix); m.fail.add(('write', MIX_TMP)); put_tones(m, songs, picks, mdl); m.clock = START_MS + 1000
    for _ in range(40): m.call(PSYMS['dm_tick'], a0=0, count=60000000)
    expect(m.busy_state() == (True, False), 'a job that will fail is showing the busy mark')
    m.ticks(limit=600)
    expect(m.busy_state() == (False, False), 'the busy mark is hidden after the job failed')
    m = fresh(mixfile=ymix); m.clock = START_MS + 1000
    for _ in range(5): m.call(PSYMS['dm_tick'], a0=0, count=60000000)
    expect(m.busy_state() == (True, False), 'the job started')
    expect(m.busy_seen(), '... and the mark is seen: yesterday\'s mix keeps its section shown')
    m.fire(EVT_DESTROY)
    expect('timer_add' not in m.names(), 'the window goes away with a job running: its timer is removed')
    m = fresh(); m.clock = START_MS + 1000
    for _ in range(5): m.call(PSYMS['dm_tick'], a0=0, count=60000000)
    expect(m.busy_state() == (True, False) and not m.busy_seen(), 'the first mix (no mix file yet): the mark is set but not seen, its section stays hidden until the mix exists')
    m = fresh(setting=b'0\n')
    expect(m.call(PSYMS['dailymix_can_regen'], count=100000) == 0, 'the Daily Mix switch off: Regenerate is off')

    # ---- thin libraries: the limits loosen a step at a time until the mix is full; untagged songs count by their folder
    def thin(lib, what, most):
        m = fresh(songs_=lib, plays_={}, rec__=(), fav_=()); run_job(m)
        p = X.select(model(lib, {}, [], set()), X.seed_for(day, 0))
        keys = [X.tag_hash(lib[i]['artist'], lib[i]['path']) for i in p]
        expect(len(p) == 25 and mpaths(m) == [lib[i]['path'] for i in p] and max(keys.count(k) for k in keys) <= most,
               f'{what}: the model\'s 25 picks, at most {most} of one artist ({len(mpaths(m))} paths, {sorted(keys.count(k) for k in set(keys))})')
    thin(small, f'{X.MIN_LIB} songs of 8 artists, an album each (2 per artist would give 15)', 25)
    thin([dict(path=f'/mnt/mmc/T/{i % 3}/{i % 6}/{i}.flac', artist=f'Trio {i % 3}', album=f'LP {i % 6}', title=f'T{i}', name=f'{i}.flac') for i in range(300)],
         '300 songs of 3 artists (2 per artist would give 6)', 25)
    thin([dict(path=f'/mnt/mmc/U/{i % 30}/{i}.flac', artist='', album='', title=f'T{i}', name=f'{i}.flac') for i in range(300)], '300 untagged songs in 30 folders', 2)
    m = fresh(mixfile=ymix, start=False); [m.present.discard(s['path']) for s in songs]; m.start_dm(); run_job(m); stays(m, 'the card is not there (no song file exists)', ymix)
    m = fresh(mixfile=ymix); m.fail.add(('write', MIX_TMP)); put_tones(m, songs, picks, mdl); run_job(m)
    expect(m.fs.get(MIX) == ymix and m.up(), 'the mix file cannot be written: yesterday\'s stays, the file is as it was')
    # ---- the mix lives on the card (CARD_DIR): not mounted, the directory missing, a card swap
    m = fresh(mixfile=ymix, start=False); m.card_mounted = False; m.start_dm()
    expect(not m.up(), 'the card is not mounted: a mix file under the mount point is not read, the section stays hidden')
    run_job(m)
    expect(not written(m, [m.calls]) and not [c for c in m.calls if c[0] in ('loadLocalClassList', 'open') and (c[0] == 'loadLocalClassList' or c[1].startswith(CARD_DIR))],
           f'... no job starts, nothing is written or opened under the card ({[c for c in m.calls if c[0] in ("open", "mkdir", "rename")]})')
    m = fresh(start=False); m.card_mounted = False; m.start_dm(); put_tones(m, songs, picks, mdl); run_job(m)
    expect(not m.up() and MIX not in m.fs and not written(m, [m.calls]) and CARD_DIR not in m.dirs, 'no card and no mix: nothing is made, nothing written, no directory, no crash')
    m.card_mounted = True; m.fire(EVT_FG)
    expect(not [c for c in m.calls if c[0] == 'loadLocalClassList'], 'a card back in does nothing until the menu is opened again')
    today_mix = X.dump_mix(day, 5, 6, 0, [(1, 2, 3), (4, 5, 6)], ['Old'], [mdl[i]['path'] for i in picks][:10])
    m = fresh(mixfile=today_mix); run_job(m)
    expect(m.up() and not [c for c in m.calls if c[0] == 'loadLocalClassList'] and MIX not in written(m, [m.calls]), 'the card has today\'s mix: it is shown, no job runs and the mix file is not written (only its art is drawn again, as before)')
    m = fresh(); put_tones(m, songs, picks, mdl); run_job(m)    # the same day, another card: no mix file there
    expect(not written(m, [m.tick_log[0]]) and X.parse_mix(m.fs[MIX])[0] == day and m.up() and mpaths(m) == [mdl[i]['path'] for i in picks],
           'a card swap, same day: the new card has no mix file, so a new mix is made after DM_START_MS and written to it')
    # the library changes under the job (another list was loaded, or it grew)
    big = [dict(path=f'/mnt/mmc/B/{i // 12}/{i}.flac', artist=f'Band {i // 60}', album=f'Disc {i // 12}', title=f'T{i}', name=f'{i}.flac') for i in range(1700)]
    m = fresh(songs_=big, plays_={}, rec__=(), fav_=(), mixfile=ymix); m.clock = START_MS + 1000
    for _ in range(200):   # up to the tick that opens the library (1,700 songs: two slices of DM_SLICE), one slice more, then another list replaces it
        m.call(PSYMS['dm_tick'], a0=0, count=60000000)
        if ('loadLocalClassList', CLS_LIB) in m.calls: break
    m.call(PSYMS['dm_tick'], a0=0, count=60000000)
    m.setword(pod.DATA['PDEQ_SHOWLIST'][0], m.new_deque([m.record()]))
    cs = m.ticks()
    expect(m.fs.get(MIX) == ymix and 'timer_add' not in m.names(),
           'another list loaded under the job (between two slices of the library): it ends, nothing is written')
    # the menu goes to the background in the middle of the job: nothing was written (the files are written at the end), it starts again from the top when the menu is back
    m = fresh(mixfile=ymix); put_tones(m, songs, picks, mdl); m.clock = START_MS + 1000
    for _ in range(40): m.call(PSYMS['dm_tick'], a0=0, count=60000000)
    expect('timer_add' in m.names() and m.fs.get(MIX) == ymix, 'the job is in the middle of the songs')
    expect(m.busy_state() == (True, False), 'the busy mark is shown while the job runs, and stays insensitive (decorative)')
    m.fire(EVT_BG)
    expect(m.fs.get(MIX) == ymix and not written(m, [m.calls]), 'the menu goes away in the middle: nothing was written, the files are as they were')
    expect(m.busy_state() == (False, False), 'the busy mark is hidden and insensitive after the menu goes to the background')
    m.fire(EVT_FG); m.clock += 100
    cs = m.ticks(limit=600)
    expect(X.parse_mix(m.fs[MIX])[0] == day and mpaths(m) == [mdl[i]['path'] for i in picks], 'and back in front the job starts again from the top and finishes')
    expect(m.busy_state() == (False, False), 'the busy mark is hidden after the commit')

    # A manual job must keep its request when Home is covered or destroyed before commit.
    # Unlike an automatic job, today's existing mix will not make dm_need retry it.
    today_mix = main_m.fs[MIX]
    for event in (EVT_BG, EVT_DESTROY):
        m = fresh(mixfile=today_mix)
        m.clock = START_MS + 1000
        m.ticks(limit=600)  # finish loading the existing art before the request
        m.fire(EVT_BG)
        m.call(PSYMS['dailymix_regen'], count=100000)
        m.fire(EVT_FG)
        for _ in range(5): m.call(PSYMS['dm_tick'], count=60000000)
        expect(m.fs[MIX] == today_mix and 'timer_add' in m.names(), 'manual regeneration is in progress with today\'s old mix still on disk')
        m.fire(event)
        expect(m.fs[MIX] == today_mix and not written(m, [m.calls]), 'interrupting manual regeneration keeps the committed mix untouched')
        if event == EVT_DESTROY: m.start_dm(); m.clock += START_MS + 1000
        else: m.fire(EVT_FG)
        m.ticks(limit=600)
        parsed = X.parse_mix(m.fs[MIX])
        old = X.parse_mix(today_mix)
        expect(parsed and parsed[3] == old[3] + 1 and parsed[1] == X.seed_for(day, old[3] + 1),
               f'manual regeneration resumes after event {event}, using the next seed exactly once')
        m.fire(EVT_FG)
        expect('timer_add' not in m.names(), 'a completed manual regeneration does not leave another request pending')

    # ---- the menu and the card go away: window destroyed, timer removed, bitmap freed
    m = fresh(mixfile=good); m.fs[ART] = art_ok; m.clock = 1
    m.ticks()
    destroyed_before = m.destroyed
    m.fire(EVT_DESTROY)
    expect(m.destroyed == destroyed_before + 1, 'the destroy event frees the bitmap')
    m.fire(EVT_BG)

    # ===== 9. text: the lines the card draws, in 13 languages
    nm = ['Radiohead', 'Björk', 'Air', 'Portishead']
    mix_txt = X.dump_mix(day0, 0x1234abcd, 0x0badf00d, 0, tones, nm[:3], PATHS)
    wfun = lambda t: sum(16 if ord(c) >= 0x2e80 or c == '…' else 8 for c in t)
    bad = []
    mt = DM(); mt.fs[MIX] = mix_txt; mt.fs[ART] = art_ok
    for loc in D.LOCALES:
        for nms in (nm[:3], nm[:1], ['Rimsky-Korsakov Philharmonic Orchestra of Saint Petersburg', 'Beethoven', 'Bach'], ['坂本龍一', 'Björk'], ['Aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'], ['Ab Cd Ef Gh Ij Kl Mn Op Qr St Uv Wx Yz Ab Cd Ef']):
            mt.set_language(loc); mt.fs[MIX] = X.dump_mix(day0, 0x1234abcd, 0x0badf00d, 0, tones, nms, PATHS)
            mt.hide_all(); mt.start_dm(); mt.fs[ART] = art_ok
            blits, texts, styles = mt.paint_card()
            tl = D.title_lines(D.tr(loc, 'Daily Mix'))
            want_t = [(t, (D.DM_PAD, [D.DM_TITLE_Y1, D.DM_TITLE_Y2][-len(tl):][i], D.DM_TITLE_W, D.DM_TITLE_PITCH)) for i, t in enumerate(tl)]
            want_s = [(t, (D.DM_PAD, D.DM_SUB_Y + i * D.DM_SUB_PITCH, D.DM_SUB_W, D.DM_SUB_PITCH)) for i, t in enumerate(D.artist_lines(wfun, [n for n in nms], loc))]
            got_t = [(t, r) for (t, r), s in zip(texts, styles) if s == 'pod_dm_title']; got_s = [(t, r) for (t, r), s in zip(texts, styles) if s == 'pod_dm_sub']
            if got_t != want_t or got_s != want_s: bad.append((loc, nms[0][:10], got_t, want_t, got_s, want_s))
    expect(not bad, f'the title and artists lines the card draws (stock canvas text in the title and artists styles) equal the model\'s in 13 languages x 6 name lists ({bad[:1]})')
    mt.set_language(None); mt.fs[MIX] = mix_txt; mt.hide_all(); mt.start_dm()
    blits, texts, styles = mt.paint_card()
    expect(len(texts) == 4 and texts[0] == ('Daily', (18, 84, 260, 38)) and texts[1] == ('Mix', (18, 122, 260, 38)) and texts[2:] == [('Radiohead, Björk, Air and', (18, 164, 204, 20)), ('more', (18, 184, 204, 20))], f'English: Daily / Mix and the artists in two lines (the mocked canvas is 8 px a character) ({texts})')
    expect(not blits and mt.fills and mt.fills[-1][1:] == (0, 0, W, H), 'no bitmap yet: a flat fill of the card')
    expect(mt.measures and not [c for c in mt.calls if c[0] in ('loadLocalClassList', 'bitmap_create_ex', 'calloc')], 'painting makes nothing (no list, no bitmap, no allocation)')
    mt.paint_card()
    expect(len(mt.measures) == 0, 'the text is laid out once (a second paint measures nothing)')
    mt.ticks()   # the one-shot reads the art file into the bitmap
    blits, texts, styles = mt.paint_card()
    expect(len(blits) == 1 and blits[0][1] == (0, 0, W, H) and blits[0][2] == (0, 0, W, H) and len(texts) == 4, 'with the bitmap: one blit of the whole card at (0, 0), then the text')

    # ===== 10. touch: the card opens the page, the disc plays the mix (the page itself: test/pod/dmpage.py)
    songs_t = songs[:30]
    order_t = [5, 3, 9, 0, 7, 11, 2, 8, 4, 10, 1, 6]          # the mix's songs: not the library's order
    mpaths_t = [songs_t[i]['path'] for i in order_t]
    mix1 = X.dump_mix(day, 0x1234abcd, 0x0badf00d, 0, tones, nm[:3], mpaths_t)
    def touch_world(mixfile=mix1, window=0):
        t = DM(); stock_world(t, songs_t, {}, (), ())
        t.fs[MIX] = mixfile; t.fs[ART] = art_ok; t.start_dm(); t.clock = 1; t.ticks()
        t.window = window                                  # (window_open fails here: the page's own widgets are not on this machine)
        return t
    nav_ = lambda t_: [c for c in t_.calls_all if c[0] == 'navigator_to_with_context']
    t = touch_world()
    t.scroll_to(250)    # the card and its disc are in the 430 px list (the section starts at y 416)
    cx, cy = t.card_xy(60, 30)
    t.tap(cx, cy)
    expect(('window_open', 'm1plus_dailymix') in t.calls_all and not nav_(t), f'a tap on the card opens the Daily Mix page, not the stock Songs page ({[c[:2] for c in t.calls_all if c[0] in ("window_open", "navigator_to_with_context")]})')
    expect(('pod_dm_card', EVT_DOWN) in t.fired and ('pod_dm_card', EVT_UP) in t.fired, 'the card gets the pointer down and up through demo\'s own dispatch')
    t.gesture([('d', cx, cy, 0), ('m', cx, cy + 30, 16), ('u', cx, cy + 30, 16)])
    expect(('window_open', 'm1plus_dailymix') not in t.calls_all, 'a drag that moves the finger 30 px opens nothing')
    t.gesture([('d', cx, cy, 0), ('a', cx, cy)]); t.gesture([('u', cx, cy, 16)])
    expect(('window_open', 'm1plus_dailymix') not in t.calls_all, 'an aborted press (the list took the drag) opens nothing')
    t.gesture([('d', cx, cy, 0), ('u', cx + 9, cy + 9, 16)])
    expect(('window_open', 'm1plus_dailymix') in t.calls_all, 'a release 9 px away is still a tap')
    dx_, dy_ = t.abs_pos(t.disc)
    expect(t.target(dx_ + 24, dy_ + 24)[-1] == 'pod_dm_play' and t.target(cx, cy)[-1] == 'pod_dm_card' and t.target(dx_ - 3, dy_ + 24)[-1] == 'pod_dm_card'
           and t.target(dx_ + 24, dy_ + 24 + 40)[-1] != 'pod_dm_play', 'demo\'s own hit test: the disc takes its 48 px square, the rest of the card is the card')
    expect(not [c for c in t.calls_all if c[0] == 'navigator_to_with_context' and c[1] == 'allmusic_page'], 'the Songs page (class 0xff13) and the stock playlists are not used any more')
    # the disc: the mix as the queue, in the mix's order
    qpaths = lambda t_: [t_.read_cstr(t_.word(r + O['REC_PATH'])) for r in t_.played[0]]
    t = touch_world()
    t.click('pod_dm_play')
    expect(t.played and qpaths(t) == mpaths_t and t.played[1] == 0, f'the disc plays the mix from its first song: the queue is its 12 songs in the mix\'s order, index 0 ({t.played and t.played[1]})')
    nav = [c for c in t.calls if c[0] == 'navigator_to_with_context']
    expect(nav and nav[-1][1] == 'playing_page' and ('loadSongList', songs_t[order_t[0]]['name'], 0, 0xf001) in t.calls and t.word(pod.DATA['G_CLASS_TYPE'][0]) == 0xf001
           and not [c for c in t.calls if c[0] == 'loadLocalClassList'], f'it starts as the Shuffle page does: loadSongList with the first song and the class 0xf001, then Now Playing, with no library read (loadLocalClassList / getAllMusic) ({nav})')
    dq_ = [c for c in t.calls if c[0] == 'toolsQueryDbTable']
    expect(len(dq_) == 1 and dq_[0][2] == "select * from songtable where fileurl in (" + ",".join("'" + p + "'" for p in mpaths_t) + ")" and dq_[0][4] == 0,
           f'the mix\'s rows come from one stock query of just its paths ({dq_})')
    t = touch_world(); t.present.discard(mpaths_t[0]); t.click('pod_dm_play')
    expect(t.played and qpaths(t) == mpaths_t[1:] and t.played[1] == 0, 'the first song is not on the card: it is left out, the queue starts at the next')
    t = touch_world(); [t.present.discard(p) for p in mpaths_t]; t.click('pod_dm_play')
    expect(t.played is None and [c for c in t.calls if c[0] == 'toast'] and not [c for c in t.calls if c[0] == 'navigator_to_with_context' and c[1] == 'playing_page'], 'no song of the mix is on the card: the usual message, nothing starts')
    gone = list(mpaths_t); gone[2] = "/mnt/mmc/Music/not-in-the-library's.flac"
    t = touch_world(mixfile=X.dump_mix(day, 0x1234abcd, 0x0badf00d, 0, tones, nm[:3], gone)); t.present.add(gone[2]); t.click('pod_dm_play')
    expect(t.played and qpaths(t) == [p for p in gone if p != gone[2]], 'a song that is not in the library is left out')
    expect("'/mnt/mmc/Music/not-in-the-library''s.flac'" in [c for c in t.calls if c[0] == 'toolsQueryDbTable'][0][2], 'a quote in a path is doubled in the SQL')

    # ===== 11. the section in the list
    sy = lambda mm_: mm_.y_of(mm_.daily)
    mw = DM(bar=True)
    stock_world(mw, songs, plays, rec_, fav)
    mw.fs[MIX] = good; mw.fs[ART] = art_ok
    mw.start_dm(); mw.relayout()
    rows_h = len([r for r in mw.rows if mw.is_visible(r)]) * 52
    expect(mw.up() and sy(mw) == rows_h and mw.y_of(mw.pad) == rows_h + D.DM_SEC_H and mw.vh() == rows_h + D.DM_SEC_H + O['MB_PAD'],
           f'the section follows the last shown row (y {rows_h}), the spacer follows it, virtual_h = rows + {D.DM_SEC_H} + the bar\'s padding ({mw.vh()})')
    mw.relayout(); mw.relayout()
    expect(mw.stack().index('daily') + 1 == mw.stack().index('shelf') and mw.stack()[-1] == 'pad' and sy(mw) == rows_h and mw.vh() == rows_h + D.DM_SEC_H + O['MB_PAD'], 'relayouts of demo\'s own list_view keep the order and the numbers')
    # the shelf below it
    mw.setword(mw.shelf + 0xc, recent.SH_H1)
    mw.call(pod.FUNCTIONS['widget_set_visible'][2], a0=mw.shelf, a1=1, a2=0, count=400000); mw.call(pod.FUNCTIONS['widget_set_sensitive'][2], a0=mw.shelf, a1=1, count=400000)
    mw.arrange(); mw.relayout()
    expect(mw.y_of(mw.shelf) == rows_h + D.DM_SEC_H and mw.y_of(mw.pad) == rows_h + D.DM_SEC_H + recent.SH_H1 and mw.vh() == rows_h + D.DM_SEC_H + recent.SH_H1 + O['MB_PAD'],
           'the Recently Played shelf starts right under the card\'s section, the spacer under the shelf')
    # scroll position kept when the section goes
    mw.scroll_to(300)
    mw.fs[SET] = b'0\n'; mw.fire(EVT_FG)
    expect(not mw.up() and mw.y_of(mw.shelf) == rows_h and mw.yoff() == min(300, mw.vh() - 430), 'the switch off (the menu in front again): the section is hidden, the shelf moves up, the list keeps its place (clamped)')
    mw.fs[SET] = b'1\n'; mw.fire(EVT_FG)
    expect(mw.up() and mw.y_of(mw.shelf) == rows_h + D.DM_SEC_H, 'the switch on again: the section is back')
    # hit tests: a touch on the section's header or the gap falls to the section; a row above stays reachable
    mw.scroll_to(300); mw.relayout()
    hx, hy = mw.abs_pos(mw.daily)
    expect(mw.target(160, hy + 25)[-1] == 'pod_daily' and mw.target(20, hy - 20)[-1].startswith('pod_row') and mw.target(160, hy + 100)[-1] == 'pod_dm_card'
           and mw.target(8, hy + 100)[-1] == 'pod_daily', 'the header and the 12 px margin are dead (the section takes them), the card is the card, the Settings row above is reachable')
    mw.hide_all()
    expect(mw.target(160, hy + 100)[-1] != 'pod_dm_card' and mw.target(160, hy + 100)[-1] != 'pod_daily', 'hidden: no touch reaches the section or the card')

    # ===== 12. fall-backs to the plain menu
    def plain(**kw):
        m_ = DM(); m_.fs[MIX] = good; m_.fs[ART] = art_ok
        for k_, v_ in kw.items(): setattr(m_, k_, v_)
        return m_
    m_ = plain(); m_.widgets.pop('pod_dm_card'); m_.start_dm()
    expect(not m_.up() and not m_.timers, 'a missing widget: the card is never shown')
    for ev in (EVT_DESTROY, EVT_BG, EVT_FG, EVT_AFTER_PAINT, EVT_DOWN, EVT_UP, EVT_ABORT, EVT_CLICK):
        m_ = plain(); m_.widget_on_fail = frozenset({ev}); m_.start_dm()
        expect(not m_.up(), f'a refused registration (event {ev:#x}): the card is never shown')
    m_ = plain(); m_.timer_fail = True; m_.start_dm()
    expect(not m_.up(), 'no timer: the card is never shown')

    # ===== 13. the previews run on the built tree
    import preview_dailymix as P
    s = P.side(WORK)
    card_im = P.card_image(s, tones)
    expect(card_im.size == (D.DM_W, D.DM_H) and card_im.getpixel((0, 0))[:3] == (0, 0, 0) and card_im.getpixel((D.DM_W // 2, 2))[:3] != (0, 0, 0), 'the card image: 296 x 220, black corner pixels')
    sec_im = P.section_image(s, tones)
    expect(sec_im.size == (D.DM_W_VIEW, D.DM_SEC_H) and sec_im.getbbox() is not None, 'the section image')
    page = P.settings_page(s)
    expect(page.size == (320, 450), 'Settings > Home Screen: the three rows in two cards, drawn from the built asset')
