"""The Navidrome data layer (patch/sbapi.c, patch/sbapi.h, docs/modules/subsonic.md "Data and cache"): the conf file, the guard, the cache files on the card, the metadata worker (one detached
thread, a small request queue, a generation counter, a status record) and every request it makes, against a scripted libcurl. The parsers are patch/sbparse.c's (real), so the fixtures are real Subsonic JSON. Sections: conf, guard, cache, worker, sync, songs, star, cover, play, urls, bg, big (everything, or `sbapi/<section>`)."""
import hashlib, importlib.util, json, os, re, struct, sys
from urllib.parse import parse_qs, urlparse
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


PCN = sibling('pcnet')   # the card machine and scripted libcurl the podcast network tests use
CONF, ND, COVERS, CA = '/mnt/mmc/.m1plus/subsonic.conf', '/mnt/mmc/.m1plus/subsonic', '/mnt/mmc/.m1plus/subsonic/covers', '/etc/m1plus-cacert.pem'
R = dict(OK=0, NOCONF=1, NOWIFI=2, NOCLOCK=3, NOCERT=4, CERT=5, NET=6, AUTH=7, NOTFOUND=8, HTTP=9, PARSE=10, STORAGE=11, MEM=12, QFULL=13, CARDFULL=14, NOTAUDIO=15, WRITE=16, CANCELLED=17)
K = dict(PING=0, SYNC=1, ALBUM=2, ARTIST=3, PLAYLIST=4, SONGS=5, SEARCH=6, COVER=7, STAR=8)
ST = dict(NONE=0, LOAD=1, OK=2, FAIL=3)
KIND = dict(track=1, album=2, artist=3, playlist=4)
TRACK = '<64s192s192s192s64s64s12s9IB3x'      # sba_track_t
ALBUM = '<64s192s192s64s64s4IB3x'             # sba_album_t
ARTIST = '<64s192s64sIB3x'                    # sba_artist_t
PLAYLIST = '<64s192s64s2I'                    # sba_playlist_t
FMT = dict(track=TRACK, album=ALBUM, artist=ARTIST, playlist=PLAYLIST)
# the status record's place in the state struct (patch/sbapi.c `sba`): conf 4 + 256 + 64 + 128, 8 slots of 160, seq, stat_next, 48 statuses of 16, busy, net, then gen, cancel
GEN_OFF, CANCEL_OFF = 2516, 2520
JPEG = b'\xff\xd8\xff\xe0' + b'JFIF\0' + bytes(40)
PASSWORD = 's3cret'
SALT = 'a1b2c3d4e5f60718'


def secret(pw, salt=SALT):
    """The login secret the conf holds for a password (patch/sbnet.c sbn_auth_make): the salt, then md5(password + salt)."""
    return salt + hashlib.md5((pw + salt).encode()).hexdigest()


def conf_pw(blob, pw):
    """The conf's third field is a secret made from pw (any salt), and pw itself is not in the file."""
    parts = (blob or b'').decode().split('|')
    sec = parts[2] if len(parts) == 3 else ''
    return len(sec) == 48 and all(c in '0123456789abcdef' for c in sec) and hashlib.md5((pw + sec[:16]).encode()).hexdigest() == sec[16:]


def conf_is(blob, url, user, pw): return (blob or b'').decode().split('|')[:2] == [url, user] and conf_pw(blob, pw)
URL = 'https://nd.example:4533'


def fnv(s):
    h = 2166136261
    for b in s.encode():
        h = ((h ^ b) * 16777619) & 0xffffffff
    return h


def row(kind, **kw):
    """A cache row as the payload's struct lays it out (strings and numbers by member name; the rest zero)."""
    names = dict(track=('id', 'title', 'artist', 'album', 'album_id', 'cover', 'suffix', 'seconds', 'track', 'disc', 'year', 'size', 'bitrate', 'sample_rate', 'bit_depth', 'created', 'starred'),
                 album=('id', 'name', 'artist', 'artist_id', 'cover', 'year', 'songs', 'seconds', 'created', 'starred'),
                 artist=('id', 'name', 'cover', 'albums', 'starred'), playlist=('id', 'name', 'cover', 'songs', 'seconds'))[kind]
    out, i = [], 0
    for count, code in re.findall(r'(\d*)([sIB])', FMT[kind][1:]):
        for _ in range(1 if code == 's' else int(count or 1)):
            v = kw.get(names[i], '' if code == 's' else 0)
            out.append(v.encode() if isinstance(v, str) else v)
            i += 1
    return struct.pack(FMT[kind], *out)


def unrow(kind, data):
    fmt = FMT[kind]
    t = struct.unpack(fmt, data)
    return [v.split(b'\0')[0].decode() if isinstance(v, bytes) else v for v in t]


def cache_file(kind, rows, flags=0, rowsize=None):
    size = struct.calcsize(FMT[kind])
    return b'SBA1' + struct.pack('<3I', KIND[kind], rowsize or size, flags) + b''.join(rows)


def read_rows(m, path, kind):
    data = m.fs.get(path)
    if data is None:
        return None
    size = struct.calcsize(FMT[kind])
    assert data[:4] == b'SBA1' and struct.unpack('<3I', data[4:16])[:2] == (KIND[kind], size) and (len(data) - 16) % size == 0, f'{path}: a cache file of {kind} rows'
    return [unrow(kind, data[16 + i:16 + i + size]) for i in range(0, len(data) - 16, size)]


def ok_json(**body): return json.dumps({'subsonic-response': {'status': 'ok', 'version': '1.16.1', **body}}).encode()


def err_json(code): return json.dumps({'subsonic-response': {'status': 'failed', 'version': '1.16.1', 'error': {'code': code, 'message': 'x'}}}).encode()


def songs_json(ids, **extra): return ok_json(searchResult3={'song': [{'id': i, 'title': f'Song {i}', 'albumId': 'al1', 'coverArt': f'cv-{i}', 'suffix': 'flac'} for i in ids], **extra})


def machine(site=None, conf=True, **kw):
    m = PCN.machine(site=site, **kw)
    m.dirs.update({'/mnt/mmc', '/mnt/mmc/.m1plus'})
    m.reuse_heap = True
    m.fs['/dev/urandom'] = os.urandom(1 << 16)
    if conf:
        m.put(CONF, f'{URL}|alice|{secret(PASSWORD)}'.encode())
    return m


def call(m, fn, *args, **kw):
    regs = {}
    for i, v in enumerate(args):
        v = m.cstr(v) if isinstance(v, str) else v
        if i < 4:
            regs[f'a{i}'] = v
        else:
            m.setword(STACK + 16 + 4 * (i - 4), v)   # o32: the fifth and later arguments sit above the four register slots
    r = m.call(PSYMS[fn], count=1 << 40, **regs, **kw)
    return r - (1 << 32) if r >= 1 << 31 else r   # (a C int)


def ask(m, fn, *args):
    """A request: (result, the worker thread it started or None)."""
    m.thread = None
    r = call(m, fn, *args)
    return r, m.thread


def drain(m, th):
    """The worker's body, run to its end (what the detached thread would do)."""
    m.call(th[0], a0=th[1], count=1 << 40)


def state(m, kind, ident=''):
    code = m.alloc(4)
    st = call(m, 'sba_state', kind, ident, code)
    return st, m.word(code)


def tstate(m): return call(m, 'sba_trial_state', call(m, 'sba_trial_id'), 0)   # the latest trial ping's state


def gen(m): return call(m, 'sba_gen')


def busy(m): return sba_at(m, GEN_OFF - 8)   # `busy` sits two words before gen (no accessor: nothing in the firmware asks)


def ping_saved(m):
    """A ping with the saved login (sba_ping_try, whose answer is the trial status)."""
    return ask(m, 'sba_ping_try', URL, 'alice', '')


def tfull(m):
    """(state, code) of the latest trial ping."""
    p = m.alloc(4)
    s = call(m, 'sba_trial_state', call(m, 'sba_trial_id'), p)
    return s, m.word(p)


def sba_at(m, off): return m.word(PSYMS['sba'] + off)


class Site:
    """A scripted server: routes by view name; every request is kept."""
    def __init__(self, **routes):
        self.routes, self.urls, self.default = routes, [], {'body': ok_json()}

    def __call__(self, url, opts):
        self.urls.append(url)
        view = re.search(r'/rest/(\w+)\.view', url)
        r = self.routes.get(view.group(1) if view else '', self.default)
        return r(url, opts) if callable(r) else r

    def views(self): return [re.search(r'/rest/(\w+)\.view', u).group(1) for u in self.urls]

    def query(self, i=-1): return {k: v[0] for k, v in parse_qs(urlparse(self.urls[i]).query, keep_blank_values=True).items()}


def run_one(m, fn, *args, site=None):
    """Ask, then run the worker to its end; (result, state of the request is read by the caller)."""
    if site is not None:
        m.curl_site = site
    r, th = ask(m, fn, *args)
    if th:
        drain(m, th)
    return r


def acov_file(albums):
    """albcov.idx for albums (dicts with id and cover, in albums.idx order) as every sync writes it: per album the id's two hashes (FNV-1a, h*33 ^ c from 5381), the cover id's FNV (0 = none), the row."""
    def hash2(s):
        h = 5381
        for b in s.encode():
            h = ((h * 33) ^ b) & 0xffffffff
        return h
    return b'SBA1' + struct.pack('<3I', 5, 16, 0) + b''.join(struct.pack('<4I', fnv(a['id']), hash2(a['id']), fnv(a['cover']) if a.get('cover') else 0, i) for i, a in enumerate(albums))


def seed(m, path, kind, rows, flags=0):
    m.put(path, cache_file(kind, [row(kind, **r) for r in rows], flags))
    if kind == 'album' and path.endswith('/albums.idx'):   # (the sync writes albcov.idx with it)
        m.put(path[:-10] + 'albcov.idx', acov_file(rows))


# --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
def conf(ctx):
    expect = ctx.expect
    m = machine(conf=False)
    expect(call(m, 'sba_configured') == 0 and call(m, 'sba_guard') == R['NOCONF'], 'no conf file: not configured, the guard says NOCONF')
    expect(call(m, 'sba_conf_url_set', URL + '/') == 0 and call(m, 'sba_conf_user_set', 'alice') == 0 and call(m, 'sba_conf_password_set', 'p|w') == 0,
           'the three setters save one field at a time')
    expect(conf_is(m.fs.get(CONF), 'https://nd.example:4533', 'alice', 'p|w') and b'p|w' not in m.fs[CONF],
           'the file is one line, url|user|secret (a trailing slash dropped): the salt and the token of the password, a "|" in it included, never the password')
    expect(call(m, 'sba_configured') == 1 and m.read_cstr(call(m, 'sba_host')) == 'nd.example:4533' and m.read_cstr(call(m, 'sba_user')) == 'alice',
           'configured, the host without scheme, the user')
    expect(CONF + '.tmp' not in m.fs and not [p for p in m.fs if p.endswith('.tmp')], 'no temp file is left')
    m.calls = []
    call(m, 'sba_conf_password_set', 's3cret')
    opens = [c for c in m.calls if c[0] == 'open' and c[1] == CONF + '.tmp']
    expect(len(opens) == 1 and [c for c in m.calls if c[0] == 'rename'] == [('rename', CONF + '.tmp', CONF)] and ('fsync', CONF + '.tmp') in m.calls,
           'a save writes the temp file, fsyncs it and renames it over the conf')
    expect(conf_is(m.fs[CONF], URL, 'alice', 's3cret') and b's3cret' not in m.fs[CONF], 'the password changed in place: a new secret, no password in the file')
    saved = m.fs[CONF]
    expect(call(m, 'sba_conf_url_set', 'ftp://nd.example') == R['PARSE'] and call(m, 'sba_conf_url_set', 'https://') == R['PARSE'] and call(m, 'sba_conf_url_set', 'https://a b') == R['PARSE']
           and call(m, 'sba_conf_url_set', 'nd.example') == R['PARSE'] and call(m, 'sba_conf_url_set', 'https://h/?x=1') == R['PARSE'] and call(m, 'sba_conf_user_set', 'a|b') == R['PARSE']
           and call(m, 'sba_conf_user_set', '') == R['PARSE'] and call(m, 'sba_conf_password_set', '') == R['PARSE'] and call(m, 'sba_conf_password_set', 'a\nb') == R['PARSE'],
           'a refused value (scheme, host, spaces, a query, "|" in the user, empty, a newline) is SBA_PARSE and changes nothing')
    expect(m.fs[CONF] == saved, 'the file is unchanged after the refusals')
    call(m, 'sba_conf_url_set', 'http://box.local/music/rest')
    expect(m.fs[CONF] == b'http://box.local/music|alice|' + saved.split(b'|')[2] and m.read_cstr(call(m, 'sba_host')) == 'box.local', 'a trailing /rest is dropped, a base path kept, the host stops at the path')
    m.fail.add(('open', CONF + '.tmp'))
    expect(call(m, 'sba_conf_user_set', 'bob') == R['STORAGE'] and m.read_cstr(call(m, 'sba_user')) == 'alice' and m.fs[CONF].startswith(b'http://box.local/music|alice|'),
           'a conf that cannot be written: SBA_STORAGE, the user unchanged in memory and on the card')
    m.fail.discard(('open', CONF + '.tmp'))
    m.card_mounted = False
    expect(call(m, 'sba_conf_user_set', 'bob') == R['STORAGE'], 'no card: SBA_STORAGE')
    m.card_mounted = True
    # sbdl.c's way to the login: copies, and NOCONF without a server
    base, user, pw = m.alloc(300), m.alloc(70), m.alloc(130)
    expect(call(m, 'sba_net_open', base, 300, user, 70, pw, 130) == 0 and m.read_cstr(base) == 'http://box.local/music' and m.read_cstr(user) == 'alice' and m.read_cstr(pw).encode() == saved.split(b'|')[2],
           'sba_net_open hands sbdl.c the saved login in its own buffers')
    expect(call(m, 'sba_net_open', base, 8, user, 70, pw, 130) == R['NOCONF'], 'a buffer too small for the address: SBA_NOCONF, nothing half copied')
    expect(call(machine(conf=False), 'sba_net_open', base, 300, user, 70, pw, 130) == R['NOCONF'], 'no server: SBA_NOCONF')
    # a file written before the secret holds the password itself: the first read makes the secret from it and writes the file again without it
    m = machine(conf=False); m.put(CONF, f'{URL}|alice|old|pass'.encode())
    expect(call(m, 'sba_configured') == 1 and conf_is(m.fs[CONF], URL, 'alice', 'old|pass') and b'old|pass' not in m.fs[CONF],
           'an older file with the password in it: still signed in, and the file now holds the secret instead')
    m = machine(conf=False); m.put(CONF, f'{URL}|alice|old'.encode()); del m.fs['/dev/urandom']
    expect(call(m, 'sba_configured') == 0, 'an older file whose secret cannot be made (no random bytes): not signed in, the password is not used as it is')
    # loaded from the card by a fresh start
    m2 = machine()
    expect(call(m2, 'sba_configured') == 1 and m2.read_cstr(call(m2, 'sba_user')) == 'alice' and m2.read_cstr(call(m2, 'sba_host')) == 'nd.example:4533',
           'a conf on the card is read on first use')
    m3 = machine(conf=False)
    m3.put(CONF, b'http://a||')
    expect(call(m3, 'sba_configured') == 0, 'a conf with empty fields is not configured')
    m3 = machine(conf=False)
    m3.put(CONF, b'not a conf')
    expect(call(m3, 'sba_configured') == 0, 'a damaged conf is not configured')
    m3 = machine(conf=False)
    m3.put(CONF, b'http://a|u|pw|with|bars\n')
    call(m3, 'sba_configured')
    expect(call(m3, 'sba_configured') == 1 and call(m3, 'sba_conf_user_set', 'u') == 0, 'a trailing newline is tolerated and the password is the rest of the line')
    # a changed server drops the cache, the manifest stays; Sign Out drops everything but the music manifest
    m = machine()
    for p in ('albums.idx', 'songs.idx', 'al/x.idx', 'ar/y.idx', 'pl/z.idx', 'covers/00000001-168.jpg', 'sync.txt'):
        m.put(f'{ND}/{p}', b'x')
    m.put(f'{ND}/dl.idx', b'manifest')
    call(m, 'sba_conf_password_set', 'other')
    expect(f'{ND}/albums.idx' in m.fs, 'a new password keeps the cache (same server)')
    call(m, 'sba_conf_user_set', 'bob')
    left = sorted(p for p in m.fs if p.startswith(ND + '/'))
    expect(left == [f'{ND}/dl.idx'], f'another user empties the cache (the download manifest stays): {left}')
    m.put(f'{ND}/albums.idx', b'x')
    g0 = gen(m)
    expect(call(m, 'sba_conf_clear') == 0 and CONF not in m.fs and call(m, 'sba_configured') == 0 and f'{ND}/albums.idx' not in m.fs and f'{ND}/dl.idx' in m.fs and gen(m) != g0,
           'Sign Out removes the conf and the cache, keeps the manifest, and moves the generation')
    expect(call(m, 'sba_conf_clear') == 0, 'Sign Out twice is fine')

    # the pull request's old files go once
    m = machine()
    old = '/mnt/mmc/.m1plus/'
    for n in ('navidrome.index', 'navidrome.index.tmp', 'navidrome.dsd.tmp', 'navidrome-view'): m.put(old + n, b'x')
    m.dirs.add(old + 'navidrome-art'); m.put(old + 'navidrome-art/0a1b.jpg', b'x'); m.put('/mnt/mmc/Subsonic/ab-Song.flac', b'music')
    call(m, 'sba_retire_old')
    left = sorted(p for p in m.fs if p.startswith(old + 'navidrome') or p == CONF or p.startswith('/mnt/mmc/Subsonic'))
    expect(left == [CONF, '/mnt/mmc/Subsonic/ab-Song.flac'] and old + 'navidrome-art' not in m.dirs,
           f'the PR index, its temp files, the artwork folder and the view file are deleted; the conf and the music stay: {left}')
    m.put(old + 'navidrome.index', b'x')
    call(m, 'sba_retire_old')
    expect(old + 'navidrome.index' in m.fs, 'it runs once per boot')


def guard(ctx):
    expect = ctx.expect
    m = machine()
    expect(call(m, 'sba_guard') == R['OK'], 'https server, Wi-Fi, clock and CA bundle: nothing in the way')
    m.card_mounted = False
    expect(call(m, 'sba_guard') == R['STORAGE'], 'no card: SBA_STORAGE')
    m.card_mounted = True
    m.wifi = -1
    expect(call(m, 'sba_guard') == R['NOWIFI'], 'Wi-Fi not connected: SBA_NOWIFI')
    m.wifi = 0
    expect(call(m, 'sba_guard') == R['NOWIFI'], 'Wi-Fi level 0: SBA_NOWIFI too')
    m.wifi = 3
    m.wall = 1700000000
    expect(call(m, 'sba_guard') == R['NOCLOCK'], 'https with a clock never set: SBA_NOCLOCK')
    m.wall = 1800000000
    m.present.discard(CA)
    expect(call(m, 'sba_guard') == R['NOCERT'], 'https without the CA bundle: SBA_NOCERT')
    call(m, 'sba_conf_url_set', 'http://box.local:4533')
    m.wall = 1700000000
    expect(call(m, 'sba_guard') == R['OK'], 'an http server (a LAN box) needs neither clock nor bundle')
    m.wall = 1800000000
    call(m, 'sba_conf_clear')
    expect(call(m, 'sba_guard') == R['NOCONF'], 'no server saved: SBA_NOCONF')
    # a refused request changes nothing: no thread, no status, no generation
    m = machine()
    m.wifi = -1
    g0 = gen(m)
    for fn, args in (('sba_ping_try', (URL, 'alice', 'x')), ('sba_sync', ()), ('sba_fetch_album', ('a1',)), ('sba_fetch_songs', (0,)), ('sba_search', ('x',)), ('sba_cover', ('c1',))):
        r, th = ask(m, fn, *args)
        expect(r == R['NOWIFI'] and th is None and 'pthread_create' not in [c[0] for c in m.calls], f'{fn} offline: SBA_NOWIFI at once, no thread')
    expect(gen(m) == g0 and tstate(m) == ST['NONE'] and state(m, K['ALBUM'], 'a1')[0] == ST['NONE'], 'nothing changed: same generation, no status')
    m.wifi = 3
    r, th = ask(machine(conf=False), 'sba_fetch_album', 'a1')
    expect(r == R['NOCONF'] and th is None, 'no server: SBA_NOCONF')


def cache(ctx):
    expect = ctx.expect
    m = machine()
    seed(m, f'{ND}/albums.idx', 'album', [dict(id='a1', name='Kind of Blue', artist='Miles Davis', year=1959, songs=5), dict(id='a2', name='ZZ', songs=1)])
    seed(m, f'{ND}/artists.idx', 'artist', [dict(id='r1', name='Miles Davis', albums=3)])
    seed(m, f'{ND}/playlists.idx', 'playlist', [dict(id='p1', name='Road', songs=4, seconds=900)])
    out = m.alloc(8)
    n = call(m, 'sba_albums', out)
    v = m.word(out + 4)
    first = unrow('album', bytes(m.u.mem_read(v, struct.calcsize(ALBUM))))
    expect(n == 2 and m.word(out) == 2 and first[:3] == ['a1', 'Kind of Blue', 'Miles Davis'] and first[5:7] == [1959, 5], 'sba_albums: the rows as stored, a heap copy')
    call(m, 'sba_free_albums', out)
    expect(m.word(out) == 0 and m.word(out + 4) == 0 and ('free', v) in m.calls, 'sba_free_albums frees the copy and zeroes the list')
    n = call(m, 'sba_artists', out)
    expect(n == 1 and unrow('artist', bytes(m.u.mem_read(m.word(out + 4), struct.calcsize(ARTIST))))[:2] == ['r1', 'Miles Davis'], 'sba_artists')
    call(m, 'sba_free_artists', out)
    n = call(m, 'sba_playlists', out)
    expect(n == 1 and unrow('playlist', bytes(m.u.mem_read(m.word(out + 4), struct.calcsize(PLAYLIST))))[3:] == [4, 900], 'sba_playlists')
    call(m, 'sba_free_playlists', out)
    expect(call(m, 'sba_album_tracks', 'nope', out) == 0 and m.word(out) == 0 and m.word(out + 4) == 0, 'a list never cached: 0 rows, NULL')
    # album tracks: disc, then track; an id with odd characters gets a hashed file name
    tracks = [dict(id='t3', title='C', disc=2, track=1), dict(id='t2', title='B', disc=1, track=2), dict(id='t1', title='A', disc=1, track=1), dict(id='t4', title='D', disc=2, track=1)]
    seed(m, f'{ND}/al/al1.idx', 'track', tracks)
    n = call(m, 'sba_album_tracks', 'al1', out)
    got = [unrow('track', bytes(m.u.mem_read(m.word(out + 4) + i * struct.calcsize(TRACK), struct.calcsize(TRACK))))[0] for i in range(n)]
    expect(got == ['t1', 't2', 't3', 't4'], f'album tracks come back disc then track, ties in file order: {got}')
    call(m, 'sba_free_tracks', out)
    weird = 'a/b c'
    seed(m, f'{ND}/al/x{fnv(weird):08x}.idx', 'track', [dict(id='w1', title='W')])
    expect(call(m, 'sba_album_tracks', weird, out) == 1, 'an id with a slash is read from a hashed file name, never a path')
    call(m, 'sba_free_tracks', out)
    seed(m, f'{ND}/ar/r1.idx', 'album', [dict(id='a1', name='X')])
    seed(m, f'{ND}/pl/p1.idx', 'track', [dict(id='t9', title='P')])
    expect(call(m, 'sba_artist_albums', 'r1', out) == 1, 'ar/<id>.idx is the artist\'s albums')
    call(m, 'sba_free_albums', out)
    expect(call(m, 'sba_playlist_tracks', 'p1', out) == 1, 'pl/<id>.idx is the playlist\'s tracks')
    call(m, 'sba_free_tracks', out)
    # stale or foreign files read as empty
    data = cache_file('album', [row('album', id='a1')])
    for what, blob in (('wrong magic', b'XXXX' + data[4:]), ('wrong kind', data[:4] + struct.pack('<I', 1) + data[8:]), ('wrong row size', cache_file('album', [row('album', id='a1')], rowsize=100)),
                       ('truncated row', data[:-5]), ('header only', data[:16]), ('short header', data[:9]), ('empty file', b'')):
        m.put(f'{ND}/albums.idx', blob)
        expect(call(m, 'sba_albums', out) == 0 and m.word(out + 4) == 0, f'albums.idx with {what}: read as empty')
    m.fs.pop(f'{ND}/albums.idx')
    expect(call(m, 'sba_albums', out) == 0, 'albums.idx missing: 0 rows')
    # songs: the flag of the last page
    seed(m, f'{ND}/songs.idx', 'track', [dict(id=f's{i}') for i in range(3)], flags=1)
    expect(call(m, 'sba_songs_more') == 1 and call(m, 'sba_songs_cached') == 3 and call(m, 'sba_songs', out) == 3, 'songs.idx: more to ask when the last page was full; 3 rows cached')
    call(m, 'sba_free_tracks', out)
    seed(m, f'{ND}/songs.idx', 'track', [dict(id='s0')], flags=0)
    expect(call(m, 'sba_songs_more') == 0, 'a short last page: nothing more')
    # the summary
    m.put(f'{ND}/sync.txt', b'1799999000 1234 1\n')
    s, w, t = m.alloc(4), m.alloc(4), m.alloc(4)
    expect(call(m, 'sba_summary', s, w, t) == 1 and (m.word(s), m.word(w), m.word(t)) == (1234, 1799999000, 1), 'sba_summary reads sync.txt')
    m.fs.pop(f'{ND}/sync.txt')
    expect(call(m, 'sba_summary', s, w, t) == 0, 'no sync yet: 0')


def worker(ctx):
    expect = ctx.expect
    site = Site(ping={'body': ok_json()})
    m = machine(site=site)
    g0 = gen(m)
    r, th = ping_saved(m)
    names = [c[0] for c in m.calls]
    expect(r == 0 and th and th[0] == PSYMS['sba_main'] and names.count('pthread_create') == 1 and names.count('pthread_detach') == 1 and busy(m) == 1,
           'a request starts one detached worker; the page sees it busy')
    expect(tfull(m) == (ST['LOAD'], 0) and gen(m) != g0 and sba_at(m, GEN_OFF) == gen(m), 'the status is LOAD at once and the generation moved')
    r3, th3 = ask(m, 'sba_fetch_album', 'al1')
    expect(r3 == 0 and th3 is None, 'a second request while the worker runs joins the queue, no second thread')
    r2, th2 = ask(m, 'sba_fetch_album', 'al1')
    expect(r2 == 0 and th2 is None, 'the same request again while it waits is not queued twice')
    g1 = gen(m)
    drain(m, th)
    q = site.query(0)
    expect(site.views() == ['ping', 'getAlbum'] and q['u'] == 'alice' and q['v'] == '1.16.1' and q['c'] == 'm1plus-music' and q['f'] == 'json' and len(q['t']) == 32 and len(q['s']) == 16
           and hashlib.md5((PASSWORD + q['s']).encode()).hexdigest() == q['t'] and PASSWORD not in site.urls[0] and site.urls[0].startswith(URL + '/rest/ping.view?'),
           'requests carry user, a salted token (md5(password + salt)), version, client, json; never the password')
    expect(site.query(1)['id'] == 'al1', 'getAlbum carries the id')
    expect(busy(m) == 0 and gen(m) != g1 and tfull(m) == (ST['OK'], 0) and state(m, K['ALBUM'], 'al1') == (ST['OK'], 0), 'the worker ended: not busy, both OK, the generation moved again')
    # errors
    cases = [('wrong user (Subsonic 40)', {'body': err_json(40)}, 'AUTH'), ('wrong token (41)', {'body': err_json(41)}, 'AUTH'), ('not found (70)', {'body': err_json(70)}, 'NOTFOUND'),
             ('another Subsonic error', {'body': err_json(10)}, 'PARSE'), ('a web page', {'body': b'<html>proxy</html>'}, 'PARSE'), ('HTTP 401', {'rc': 22, 'code': 401}, 'AUTH'),
             ('HTTP 404', {'rc': 22, 'code': 404}, 'NOTFOUND'), ('HTTP 500', {'rc': 22, 'code': 500}, 'HTTP'), ('no answer', {'rc': 7}, 'NET'), ('time-out', {'rc': 28}, 'NET'),
             ('certificate refused', {'rc': 60}, 'CERT'), ('peer verification failed', {'rc': 51}, 'CERT')]
    for why, reply, want in cases:
        m = machine(site=Site(ping=reply))
        r, th = ping_saved(m)
        drain(m, th)
        expect(tfull(m) == (ST['FAIL'], R[want]), f'ping, {why}: SBA_{want}')
    # a request is refused when the queue is full
    m = machine(site=Site())
    codes = [ask(m, 'sba_fetch_album', f'a{i}')[0] for i in range(10)]
    expect(codes[:8] == [0] * 8 and codes[8:] == [R['QFULL']] * 2, f'eight requests wait, the ninth is SBA_QFULL: {codes}')
    expect(state(m, K['ALBUM'], 'a8')[0] == ST['NONE'], 'a refused request leaves no status')
    # cancel: queued requests go, the status forgets them
    m = machine(site=Site())
    r, th = ask(m, 'sba_fetch_album', 'x1')
    ask(m, 'sba_fetch_artist', 'y1')
    g0 = gen(m)
    call(m, 'sba_cancel')
    expect(state(m, K['ALBUM'], 'x1')[0] == ST['NONE'] and state(m, K['ARTIST'], 'y1')[0] == ST['NONE'] and gen(m) != g0, 'sba_cancel drops what is queued and its status')
    n0 = len(m.curl_site.urls)
    drain(m, th)
    expect(len(m.curl_site.urls) == n0 and busy(m) == 0, 'the worker finds nothing to do and ends')
    # cancel while a transfer runs: the transfer is aborted, nothing is committed, the status is cleared
    m = machine()
    seed(m, f'{ND}/al/x1.idx', 'track', [dict(id='old')])
    before = m.fs[f'{ND}/al/x1.idx']

    def during(url, opts):
        if not hasattr(during, 'done'):
            during.done = True
            m.setword(PSYMS['sba'] + CANCEL_OFF, m.word(PSYMS['sba'] + CANCEL_OFF) + 1)   # the page was destroyed mid-transfer
        return {'body': ok_json(album={'id': 'x1', 'song': [{'id': 'new', 'title': 'N'}]}), 'xfer': lambda u, sent, total: None}
    run_one(m, 'sba_fetch_album', 'x1', site=during)
    expect(m.fs[f'{ND}/al/x1.idx'] == before and state(m, K['ALBUM'], 'x1')[0] == ST['NONE'] and busy(m) == 0, 'a cancel during the transfer commits nothing and clears the status')
    # a thread that cannot be made
    m = machine(site=Site(), thread_ok=False)
    r, th = ping_saved(m)
    expect(r == R['MEM'] and busy(m) == 0 and tstate(m) == ST['NONE'], 'no thread: SBA_MEM, not busy, no status')
    # lists are run before covers whatever the order of asking
    site = Site(getCoverArt={'body': JPEG})
    m = machine(site=site)
    r, th = ask(m, 'sba_cover', 'cv1')
    ask(m, 'sba_fetch_album', 'al1')
    drain(m, th)
    expect(site.views() == ['getAlbum', 'getCoverArt'], f'a list request runs before a waiting cover: {site.views()}')
    # covers never take the last two slots
    m = machine(site=Site())
    codes = [ask(m, 'sba_cover', f'c{i}')[0] for i in range(8)]
    expect(codes == [0] * 6 + [R['QFULL']] * 2, f'six covers at most wait together (two slots stay for lists): {codes}')
    r, th = ask(m, 'sba_fetch_album', 'al1')
    expect(r == 0, 'a list request still fits behind six covers')


def sync(ctx):
    expect = ctx.expect
    site_views = lambda m: m.curl_site.views()

    def albums_page(start, n):
        return ok_json(albumList2={'album': [{'id': f'a{i}', 'name': f'Album {i}', 'songCount': 10, 'coverArt': f'al-a{i}'} for i in range(start, start + n)]})
    pages = {0: albums_page(0, 250), 250: albums_page(250, 250), 500: albums_page(500, 120)}
    site = Site(getAlbumList2=lambda url, o: {'body': pages[int(parse_qs(urlparse(url).query)['offset'][0])]},
                getArtists={'body': ok_json(artists={'index': []})}, getPlaylists={'body': ok_json(playlists={'playlist': []})},
                getStarred2={'body': ok_json(starred2={'song': [{'id': 's1', 'title': 'Fav'}], 'album': [{'id': 'a3', 'name': 'Album 3'}]})},
                search3=lambda url, o: {'body': songs_json(['s0'])}, getCoverArt={'body': JPEG})   # (phase 2 follows the sync on the same worker: an empty library of songs, covers that arrive)
    m = machine(site=site)
    m.wall = 1800000000
    expect(call(m, 'sba_sync_due') == 1, 'no sync yet: due')
    g0 = gen(m)
    r = run_one(m, 'sba_sync')
    expect(r == 0 and state(m, K['SYNC']) == (ST['OK'], 0), 'a sync finishes OK')
    expect(site.views()[:6] == ['getAlbumList2'] * 3 + ['getArtists', 'getPlaylists', 'getStarred2'], f'albums by pages, then artists, playlists, favorites: {site.views()[:6]}')
    expect(site.views()[6:8] == ['search3'] * 2 and set(site.views()[8:]) == {'getCoverArt'}, 'and then phase 2 (the songs, then the covers), nothing before the sync is whole')
    q0, q1 = site.query(0), site.query(1)
    expect((q0['type'], q0['size'], q0['offset'], q1['offset']) == ('alphabeticalByName', '250', '0', '250'), 'getAlbumList2 alphabeticalByName, 250 a page, the offset advancing')
    rows = read_rows(m, f'{ND}/albums.idx', 'album')
    expect(len(rows) == 620 and rows[0][:2] == ['a0', 'Album 0'] and rows[-1][0] == 'a619', 'albums.idx holds both pages in order')
    expect(m.fs.get(f'{ND}/albcov.idx') == acov_file([dict(id=r[0], cover=r[4]) for r in rows]),
           'albcov.idx is written with it: per album the two hashes of its id, its cover id\'s hash and its row in albums.idx (a track finds its album\'s cover file with it)')
    expect(read_rows(m, f'{ND}/starred.idx', 'track')[0][:2] == ['s1', 'Fav'] and f'{ND}/starred-al.idx' not in m.fs
           and read_rows(m, f'{ND}/artists.idx', 'artist') == [] and read_rows(m, f'{ND}/playlists.idx', 'playlist') == [], 'artists, playlists and the favorites list are replaced whole (no starred-al.idx)')
    s, w, t = m.alloc(4), m.alloc(4), m.alloc(4)
    expect(call(m, 'sba_summary', s, w, t) == 1 and (m.word(s), m.word(w), m.word(t)) == (6200, 1800000000, 0), 'sync.txt: time, the sum of the albums\' track counts, not truncated')
    expect(re.fullmatch(rb'1800000000 6200 0 \d+\n', m.fs[f'{ND}/sync.txt']) and int(m.fs[f'{ND}/sync.txt'].split()[3]) % 2 == 1, 'and the library signature (never 0)')
    expect(not [p for p in m.fs if p.endswith('.tmp')] and gen(m) != g0, 'no temp file is left')
    # the staleness rule
    m.curl_site = Site()
    r, th = ask(m, 'sba_sync_auto')
    expect(r == 0 and th is None and call(m, 'sba_sync_due') == 0, 'a fresh cache (under 15 minutes): the automatic sync queues nothing')
    m.wall += 899
    expect(call(m, 'sba_sync_due') == 0, '899 s later: still fresh')
    m.wall += 1
    r, th = ask(m, 'sba_sync_auto')
    expect(call(m, 'sba_sync_due') == 1 and r == 0 and th is not None, '900 s later: due, the automatic sync starts')
    drain(m, th)
    m.wall -= 1000
    expect(call(m, 'sba_sync_due') == 1, 'a clock that went back counts as stale')
    m.wall = 1800000910
    r, th = ask(m, 'sba_sync')
    expect(r == 0 and th is not None, 'Sync Now always starts (even when fresh)')
    m.wifi = -1
    expect(call(m, 'sba_sync_due') == 0 and call(m, 'sba_sync_auto') == R['OK'], 'fresh and offline: the automatic sync refuses nothing')
    # the sync itself no longer touches songs.idx (it would cut a complete list back to a page): phase 2 replaces it whole when the library changed
    m = machine(site=Site(getAlbumList2={'body': albums_page(0, 2)}, getArtists={'body': ok_json(artists={})}, getPlaylists={'body': ok_json(playlists={})}, getStarred2={'body': ok_json(starred2={})},
                          search3={'body': songs_json(['n0', 'n1'])}, getCoverArt={'body': JPEG}))
    m.wall = 1800000000
    seed(m, f'{ND}/songs.idx', 'track', [dict(id=f'o{i}') for i in range(5)])
    r, th = ask(m, 'sba_sync')
    m.curl_site.urls.clear()
    keep = m.fs[f'{ND}/songs.idx']
    expect(r == 0 and m.fs[f'{ND}/songs.idx'] == keep and not m.curl_site.urls, 'asking for a sync does not touch songs.idx')
    drain(m, th)
    expect([r[0] for r in read_rows(m, f'{ND}/songs.idx', 'track')] == ['n0', 'n1'] and site_views(m)[4] == 'search3' and m.curl_site.query(4)['songOffset'] == '0',
           'phase 2 pages the songs from offset 0 and replaces songs.idx with the whole list')
    # a failing stage fails the sync, keeps the earlier files, writes no sync.txt, and a library over the cap is cut and says so
    m = machine(site=Site(getAlbumList2={'body': albums_page(0, 3)}, getArtists={'rc': 7}))
    m.wall = 1800000000
    run_one(m, 'sba_sync')
    expect(state(m, K['SYNC']) == (ST['FAIL'], R['NET']) and f'{ND}/sync.txt' not in m.fs and len(read_rows(m, f'{ND}/albums.idx', 'album')) == 3,
           'artists unreachable: SBA_NET, albums.idx is already replaced, no sync.txt, so the next open syncs again')
    m = machine(site=Site(getAlbumList2={'body': err_json(40)}))
    seed(m, f'{ND}/albums.idx', 'album', [dict(id='keep')])
    old, old_cov = m.fs[f'{ND}/albums.idx'], m.fs[f'{ND}/albcov.idx']
    run_one(m, 'sba_sync')
    expect(state(m, K['SYNC']) == (ST['FAIL'], R['AUTH']) and m.fs[f'{ND}/albums.idx'] == old and m.fs[f'{ND}/albcov.idx'] == old_cov and not [p for p in m.fs if p.endswith('.tmp')],
           'a refused first page: SBA_AUTH, the old albums.idx and albcov.idx kept, no temp file')
    m = machine(site=Site(getAlbumList2={'body': ok_json(albumList2={'album': [{'id': f'a{i}', 'name': 'A'} for i in range(250)]}), 'chunk': 4096}, getArtists={'body': ok_json(artists={})}, getPlaylists={'body': ok_json(playlists={})}, getStarred2={'body': ok_json(starred2={})}))
    m.wall = 1800000000
    run_one(m, 'sba_sync')
    expect(len(m.curl_site.urls) > 20 and len(read_rows(m, f'{ND}/albums.idx', 'album')) == 20000 and call(m, 'sba_summary', s, w, t) == 1 and m.word(t) == 1,
           f'a library of more than 20,000 albums is cut there ({len(m.curl_site.urls)} requests) and sync.txt says truncated')
    expect(len(m.fs[f'{ND}/albcov.idx']) == 16 + 20000 * 16, 'and albcov.idx has the same 20,000 rows (320 KB)')
    m = machine(site=Site())
    m.free_mb = 3
    r = run_one(m, 'sba_sync')
    expect(state(m, K['SYNC']) == (ST['FAIL'], R['CARDFULL']), 'a card with less than the cache reserve free: SBA_CARDFULL')
    m = machine(site=Site(getAlbumList2={'body': albums_page(0, 2)}))
    m.fail.add(('write', f'{ND}/albums.idx.tmp'))
    run_one(m, 'sba_sync')
    expect(state(m, K['SYNC']) == (ST['FAIL'], R['STORAGE']) and f'{ND}/albums.idx.tmp' not in m.fs, 'a write error: SBA_STORAGE, the temp file removed')
    # albcov.idx is a convenience: when it cannot be written the sync still succeeds, and the albcov.idx of the albums before is gone (it would name rows of the old file)
    m = machine(site=Site(getAlbumList2={'body': albums_page(0, 2)}, getArtists={'body': ok_json(artists={})}, getPlaylists={'body': ok_json(playlists={})}, getStarred2={'body': ok_json(starred2={})},
                          search3={'body': songs_json([])}, getCoverArt={'body': JPEG}))
    m.wall = 1800000000
    seed(m, f'{ND}/albums.idx', 'album', [dict(id='old', cover='al-old')])
    m.fail.add(('write', f'{ND}/albcov.idx.tmp'))
    run_one(m, 'sba_sync')
    expect(state(m, K['SYNC']) == (ST['OK'], 0) and len(read_rows(m, f'{ND}/albums.idx', 'album')) == 2 and f'{ND}/albcov.idx' not in m.fs and f'{ND}/albcov.idx.tmp' not in m.fs,
           'albcov.idx cannot be written: the sync is OK, the old albcov.idx is removed, no temp file')
    # an optional list the server refuses (no rights to playlists): the albums are the sync; that list keeps its old file (an empty one when none), the sync is committed and the fill runs
    m = machine(site=Site(getAlbumList2={'body': albums_page(0, 2)}, getArtists={'body': ok_json(artists={})}, getPlaylists={'rc': 22, 'code': 500},
                          getStarred2={'body': ok_json(starred2={'song': [{'id': 's1', 'title': 'Fav'}]})}, search3={'body': songs_json([])}, getCoverArt={'body': JPEG}))
    m.wall = 1800000000
    seed(m, f'{ND}/playlists.idx', 'playlist', [dict(id='p-old', name='Old')])
    run_one(m, 'sba_sync')
    expect(state(m, K['SYNC']) == (ST['OK'], 0) and f'{ND}/sync.txt' in m.fs and [r[0] for r in read_rows(m, f'{ND}/playlists.idx', 'playlist')] == ['p-old']
           and read_rows(m, f'{ND}/starred.idx', 'track')[0][0] == 's1' and 'search3' in m.curl_site.views(), 'playlists answer 500: the old playlists.idx stays, the rest of the sync and phase 2 go on')
    m = machine(site=Site(getAlbumList2={'body': albums_page(0, 2)}, getArtists={'body': ok_json(artists={})}, getPlaylists={'body': err_json(50)}, getStarred2={'body': ok_json(starred2={})},
                          search3={'body': songs_json([])}, getCoverArt={'body': JPEG}))
    m.wall = 1800000000
    run_one(m, 'sba_sync')
    expect(state(m, K['SYNC']) == (ST['OK'], 0) and f'{ND}/sync.txt' in m.fs and read_rows(m, f'{ND}/playlists.idx', 'playlist') == [], 'a Subsonic error for playlists and no file before: an empty list, the sync commits')
    m = machine(site=Site(getAlbumList2={'body': albums_page(0, 2)}, getArtists={'body': err_json(40)}, getPlaylists={'body': ok_json(playlists={})}, getStarred2={'body': ok_json(starred2={})}))
    run_one(m, 'sba_sync')
    expect(state(m, K['SYNC']) == (ST['FAIL'], R['AUTH']) and f'{ND}/sync.txt' not in m.fs, 'a refused login still fails the whole sync')


def songs(ctx):
    expect = ctx.expect

    def page(start, n): return songs_json([f's{i}' for i in range(start, start + n)])
    pages = {0: page(0, 100), 100: page(100, 20)}
    site = Site(search3=lambda url, o: {'body': pages.get(int(parse_qs(urlparse(url).query)['songOffset'][0]), page(900, 5))})
    m = machine(site=site)
    run_one(m, 'sba_fetch_songs', 0)
    q = site.query(0)
    expect((q['query'], q['songCount'], q['songOffset'], q['albumCount'], q['artistCount']) == ('', '100', '0', '0', '0'), 'the Songs list: search3 with an empty query, 100 songs from offset 0')
    rows = read_rows(m, f'{ND}/songs.idx', 'track')
    expect(len(rows) == 100 and call(m, 'sba_songs_more') == 1 and call(m, 'sba_songs_cached') == 100, 'a full page: songs.idx has 100 rows and says there is more')
    run_one(m, 'sba_fetch_songs', 100)
    rows = read_rows(m, f'{ND}/songs.idx', 'track')
    expect(site.query(1)['songOffset'] == '100' and len(rows) == 120 and rows[0][0] == 's0' and rows[100][0] == 's100' and rows[-1][0] == 's119' and call(m, 'sba_songs_more') == 0,
           'the next page is appended (the first rows kept), a short page ends the list')
    expect(state(m, K['SONGS']) == (ST['OK'], 0), 'the status is OK')
    run_one(m, 'sba_fetch_songs', 0)
    expect(len(read_rows(m, f'{ND}/songs.idx', 'track')) == 100, 'offset 0 starts the list again')
    run_one(m, 'sba_fetch_songs', 900)
    expect(state(m, K['SONGS']) == (ST['FAIL'], R['PARSE']) or state(m, K['SONGS'])[0] == ST['FAIL'], 'an offset past what is cached is a failure, not a gap')
    expect(len(read_rows(m, f'{ND}/songs.idx', 'track')) == 100 and not [p for p in m.fs if p.endswith('.tmp')], 'and songs.idx is unchanged')
    run_one(m, 'sba_fetch_songs', 100)
    run_one(m, 'sba_fetch_songs', 100)
    expect(len(read_rows(m, f'{ND}/songs.idx', 'track')) == 120 and state(m, K['SONGS']) == (ST['OK'], 0), 'a stale page request (the list already holds those rows) changes nothing and is not a failure')
    # search
    site = Site(search3={'body': ok_json(searchResult3={'song': [{'id': 't1', 'title': 'One'}], 'album': [{'id': 'a1', 'name': 'Alb'}], 'artist': []})})
    m = machine(site=site)
    run_one(m, 'sba_search', 'Miles & Co é')
    q = site.query(0)
    expect(q['query'] == 'Miles & Co é' and '%C3%A9' in site.urls[0] and ' ' not in site.urls[0] and (q['songCount'], q['albumCount'], q['artistCount']) == ('20', '20', '20'),
           'search3 with the term escaped, 20 of each kind')
    expect(read_rows(m, f'{ND}/search.idx', 'track')[0][:2] == ['t1', 'One'] and read_rows(m, f'{ND}/search-al.idx', 'album')[0][0] == 'a1' and read_rows(m, f'{ND}/search-ar.idx', 'artist') == [],
           'tracks, albums and artists are three files, replaced by the next search')
    expect(call(m, 'sba_search', '') == R['PARSE'], 'an empty term is refused')
    # a search typed over: the older one queued behind is superseded and never goes out; sba_search_is says which term finished last
    site = Site(search3={'body': ok_json(searchResult3={'song': [{'id': 't1', 'title': 'One'}], 'album': [], 'artist': []})})
    m = machine(site=site)
    r1, th = ask(m, 'sba_search', 'mi')
    r2, _ = ask(m, 'sba_search', 'mile')
    expect(r1 == 0 and r2 == 0 and th, 'two searches queue')
    drain(m, th)
    expect(len(site.urls) == 1 and site.query(0)['query'] == 'mile', f'only the newest search is sent ({site.urls})')
    expect(call(m, 'sba_search_is', 'mile') == 1 and call(m, 'sba_search_is', 'mi') == 0 and state(m, K['SEARCH'])[0] == ST['OK'], 'sba_search_is names the term that finished')
    # album / artist / playlist on open
    site = Site(getAlbum={'body': ok_json(album={'id': 'al1', 'name': 'A', 'song': [{'id': 't2', 'title': 'B'}, {'id': 't1', 'title': 'A'}]})},
                getArtist={'body': ok_json(artist={'id': 'r1', 'album': [{'id': 'a1', 'name': 'X'}]})},
                getPlaylist={'body': ok_json(playlist={'id': 'p1', 'entry': [{'id': 't7', 'title': 'P'}]})})
    m = machine(site=site)
    for fn, ident in (('sba_fetch_album', 'al1'), ('sba_fetch_artist', 'r1'), ('sba_fetch_playlist', 'p1')):
        run_one(m, fn, ident)
    expect(site.views() == ['getAlbum', 'getArtist', 'getPlaylist'] and [site.query(i)['id'] for i in range(3)] == ['al1', 'r1', 'p1'], 'getAlbum, getArtist, getPlaylist with the id')
    expect([r[0] for r in read_rows(m, f'{ND}/al/al1.idx', 'track')] == ['t2', 't1'] and read_rows(m, f'{ND}/ar/r1.idx', 'album')[0][0] == 'a1'
           and read_rows(m, f'{ND}/pl/p1.idx', 'track')[0][0] == 't7', 'al/, ar/ and pl/ files hold the rows')
    run_one(m, 'sba_fetch_album', 'a/b c')
    expect(f'{ND}/al/x{fnv("a/b c"):08x}.idx' in m.fs and not [p for p in m.fs if 'a/b' in p], 'an id with a slash is hashed in the file name')
    expect(call(m, 'sba_fetch_album', '') == R['NOTFOUND'], 'an empty id is refused')


def star(ctx):
    expect = ctx.expect
    site = Site(star={'body': ok_json()}, unstar={'body': ok_json()})
    m = machine(site=site)
    seed(m, f'{ND}/songs.idx', 'track', [dict(id='t0'), dict(id='t1', title='One', album_id='al1'), dict(id='t2')])
    seed(m, f'{ND}/al/al1.idx', 'track', [dict(id='t1', title='One')])
    seed(m, f'{ND}/search.idx', 'track', [dict(id='t1', title='One')])
    t = m.alloc(struct.calcsize(TRACK))
    m.u.mem_write(t, row('track', id='t1', title='One', album_id='al1'))
    flag = lambda p, i=0: read_rows(m, p, 'track')[i][-1]
    pending = lambda: call(m, 'sba_star_pending', 't1')
    out = m.alloc(8)

    def songs_flag(i=1):
        n = call(m, 'sba_songs', out)
        v = struct.unpack(TRACK, bytes(m.u.mem_read(m.word(out + 4) + i * struct.calcsize(TRACK), struct.calcsize(TRACK))))[-1]
        call(m, 'sba_free_tracks', out)
        return v if n > i else None
    before = bytes(m.fs[f'{ND}/songs.idx'])
    g0 = gen(m)
    r, th = ask(m, 'sba_star', t, 1)
    expect(r == 0 and th is not None and pending() == 1 and gen(m) != g0 and songs_flag() == 1 and songs_flag(0) == 0,
           'the heart flips at once through the overlay (the track list read shows it) and the generation moves')
    expect(bytes(m.fs[f'{ND}/songs.idx']) == before and f'{ND}/starred.idx' not in m.fs, 'the page side wrote no cache file: the worker has not run yet')
    expect(state(m, K['STAR'], 't1')[0] == ST['LOAD'], 'the request is pending')
    drain(m, th)
    expect(pending() == -1 and site.views() == ['star'] and site.query(0)['id'] == 't1' and state(m, K['STAR'], 't1') == (ST['OK'], 0), 'star.view with the id; the server accepts; the overlay is gone')
    expect(flag(f'{ND}/songs.idx', 1) == 1 and flag(f'{ND}/al/al1.idx') == 1 and flag(f'{ND}/search.idx') == 1 and flag(f'{ND}/songs.idx', 0) == 0 and len(m.fs[f'{ND}/songs.idx']) == len(before),
           'the worker flipped the row in place in songs, its album file and search, and no other row')
    expect([x[:2] for x in read_rows(m, f'{ND}/starred.idx', 'track')] == [['t1', 'One']] and flag(f'{ND}/starred.idx') == 1, 'starred.idx (not there yet) is made with the track')
    expect(not [c for c in m.calls if c[0] == 'open' and c[1] in (f'{ND}/songs.idx.tmp', f'{ND}/search.idx.tmp', f'{ND}/al/al1.idx.tmp')], 'no copy of the three row files (no .tmp)')
    r, th = ask(m, 'sba_star', t, 0)
    expect(pending() == 0 and songs_flag() == 0, 'unstar: the overlay says off at once')
    drain(m, th)
    expect(site.views() == ['star', 'unstar'], 'unstar.view')
    expect(read_rows(m, f'{ND}/starred.idx', 'track') == [] and flag(f'{ND}/songs.idx', 1) == 0 and flag(f'{ND}/al/al1.idx') == 0, 'gone from starred.idx, the flag cleared')
    # a row that no file has: songs.idx is not rewritten
    seed(m, f'{ND}/songs.idx', 'track', [dict(id='t0'), dict(id='t2')])
    before = bytes(m.fs[f'{ND}/songs.idx'])
    m.calls.clear()
    r, th = ask(m, 'sba_star', t, 1)
    drain(m, th)
    expect(bytes(m.fs[f'{ND}/songs.idx']) == before and not [c for c in m.calls if c[0] == 'write' and c[1] == f'{ND}/songs.idx'] and not [c for c in m.calls if c[0] == 'open' and c[1] == f'{ND}/songs.idx.tmp'],
           'a star whose row songs.idx does not have leaves it byte-identical, with no write and no copy')
    ask_un = ask(m, 'sba_star', t, 0)
    drain(m, ask_un[1])
    seed(m, f'{ND}/songs.idx', 'track', [dict(id='t0'), dict(id='t1', title='One', album_id='al1'), dict(id='t2')])
    # refused: the cache goes back
    m.curl_site = Site(star={'body': err_json(70)})
    r, th = ask(m, 'sba_star', t, 1)
    expect(pending() == 1 and songs_flag() == 1, 'flipped at once')
    drain(m, th)
    expect(pending() == -1 and state(m, K['STAR'], 't1') == (ST['FAIL'], R['NOTFOUND']) and flag(f'{ND}/songs.idx', 1) == 0 and flag(f'{ND}/al/al1.idx') == 0 and read_rows(m, f'{ND}/starred.idx', 'track') == [],
           'the server refuses (SBA_NOTFOUND): the heart goes back everywhere')
    m.curl_site = Site(star={'rc': 7})
    r, th = ask(m, 'sba_star', t, 1)
    drain(m, th)
    expect(state(m, K['STAR'], 't1') == (ST['FAIL'], R['NET']) and flag(f'{ND}/songs.idx', 1) == 0 and read_rows(m, f'{ND}/starred.idx', 'track') == [] and pending() == -1, 'no answer: reverted too')
    # offline: refused, nothing flips
    m.wifi = -1
    r, th = ask(m, 'sba_star', t, 1)
    expect(r == R['NOWIFI'] and th is None and flag(f'{ND}/songs.idx', 1) == 0 and pending() == -1, 'offline: SBA_NOWIFI, the overlay is not left set')
    m.wifi = 3
    # a full queue drops the overlay at once
    m.curl_site = Site()
    for i in range(8):
        ask(m, 'sba_fetch_album', f'q{i}')
    r, th = ask(m, 'sba_star', t, 1)
    expect(r == R['QFULL'] and pending() == -1 and flag(f'{ND}/songs.idx', 1) == 0 and read_rows(m, f'{ND}/starred.idx', 'track') == [], 'a full queue: SBA_QFULL and the flip is undone')
    # cancelled before it ran: undone, the files were never touched
    m = machine(site=Site())
    seed(m, f'{ND}/songs.idx', 'track', [dict(id='t1', title='One')])
    t = m.alloc(struct.calcsize(TRACK))
    m.u.mem_write(t, row('track', id='t1', title='One'))
    ask(m, 'sba_star', t, 1)
    expect(call(m, 'sba_star_pending', 't1') == 1, 'queued: the overlay holds the star')
    call(m, 'sba_cancel')
    expect(call(m, 'sba_star_pending', 't1') == -1 and read_rows(m, f'{ND}/songs.idx', 'track')[0][-1] == 0 and f'{ND}/starred.idx' not in m.fs,
           'a star dropped by sba_cancel is taken back (the overlay goes; no file was written)')
    # two stars of one id in flight: the overlay shows the latest wish until the last one is done
    m = machine(site=Site(star={'body': ok_json()}, unstar={'body': ok_json()}))
    seed(m, f'{ND}/songs.idx', 'track', [dict(id='t1', title='One')])
    t = m.alloc(struct.calcsize(TRACK))
    m.u.mem_write(t, row('track', id='t1', title='One'))
    r1, th1 = ask(m, 'sba_star', t, 1)
    r2, th2 = ask(m, 'sba_star', t, 0)
    expect(call(m, 'sba_star_pending', 't1') == 0, 'two stars in flight: the latest wish shows')
    drain(m, th1)
    expect(read_rows(m, f'{ND}/songs.idx', 'track')[0][-1] == 0 and read_rows(m, f'{ND}/starred.idx', 'track') == [] and call(m, 'sba_star_pending', 't1') == -1,
           'the worker ran both in order: star then unstar, the file is off, the overlay gone')


def cover(ctx):
    expect = ctx.expect
    site = Site(getCoverArt={'body': JPEG})
    m = machine(site=site)
    path = m.alloc(128)
    expect(call(m, 'sba_cover_path', path, 128, 'al-a1_5f3a') == 0 and m.read_cstr(path) == f'{COVERS}/{fnv("al-a1_5f3a"):08x}-168.jpg', 'the cover file is in Navidrome\'s own folder, named by the cover id')
    expect(not m.read_cstr(path).startswith('/mnt/mmc/.m1plus/covers/') and call(m, 'sba_cover_path', path, 16, 'x') == -1 and call(m, 'sba_cover_path', path, 128, '') == -1,
           'never Cover Flow\'s folder; a small buffer or an empty id is refused')
    want = f'{COVERS}/{fnv("al-a1_5f3a"):08x}-168.jpg'
    expect(call(m, 'sba_cover_have', 'al-a1_5f3a') == 0, 'no file yet')
    r, th = ask(m, 'sba_cover', 'al-a1_5f3a')
    expect(r == 0 and th is not None and state(m, K['COVER'], 'al-a1_5f3a')[0] == ST['LOAD'], 'a missing cover is queued')
    r2, th2 = ask(m, 'sba_cover', 'al-a1_5f3a')
    expect(r2 == 0 and th2 is None, 'the same cover is not queued twice')
    drain(m, th)
    q = site.query(0)
    expect(site.views() == ['getCoverArt'] and q['id'] == 'al-a1_5f3a' and q['size'] == '168', 'getCoverArt with the id and size 168')
    expect(m.fs.get(want) == JPEG and state(m, K['COVER'], 'al-a1_5f3a') == (ST['OK'], 0) and call(m, 'sba_cover_have', 'al-a1_5f3a') == 1 and not [p for p in m.fs if p.endswith('.tmp')],
           'the picture is written whole and atomically into the covers folder')
    expect(not [p for p in m.fs if p.startswith('/mnt/mmc/.m1plus/covers')], 'nothing under Cover Flow\'s own folder')
    n0 = len(site.urls)
    r, th = ask(m, 'sba_cover', 'al-a1_5f3a')
    expect(r == 0 and th is None and len(site.urls) == n0, 'a cover that is there: SBA_OK at once, no request')
    # not a picture
    m = machine(site=Site(getCoverArt={'body': b'<html>nope</html>' + bytes(20)}))
    run_one(m, 'sba_cover', 'c2')
    expect(state(m, K['COVER'], 'c2') == (ST['FAIL'], R['PARSE']) and call(m, 'sba_cover_have', 'c2') == 0, 'a web page instead of a picture: SBA_PARSE, no file')
    m = machine(site=Site(getCoverArt={'body': b'{"subsonic-response":{"status":"failed"}}'}))
    run_one(m, 'sba_cover', 'c3')
    expect(state(m, K['COVER'], 'c3')[0] == ST['FAIL'] and call(m, 'sba_cover_have', 'c3') == 0, 'a Subsonic error answer is not a picture either')
    m = machine(site=Site(getCoverArt={'body': b'\x89PNG\r\n\x1a\n' + bytes(30)}))
    run_one(m, 'sba_cover', 'c4')
    expect(call(m, 'sba_cover_have', 'c4') == 1, 'a PNG is accepted')
    # the server has none: an empty marker
    m = machine(site=Site(getCoverArt={'rc': 22, 'code': 404}))
    run_one(m, 'sba_cover', 'c5')
    expect(state(m, K['COVER'], 'c5') == (ST['FAIL'], R['NOTFOUND']) and call(m, 'sba_cover_have', 'c5') == -1, 'a 404 leaves an empty marker file: known to have no art')
    r, th = ask(m, 'sba_cover', 'c5')
    expect(r == R['NOTFOUND'] and th is None, 'and asking again is SBA_NOTFOUND at once')
    # Navidrome's stand-in for an artist or album with no art is a WebP served as it is (never resized): no art, the same marker, not a parse error
    m = machine(site=Site(getCoverArt={'body': b'RIFF\x1a\0\0\0WEBPVP8 ' + bytes(40)}))
    run_one(m, 'sba_cover', 'ar-c7')
    expect(state(m, K['COVER'], 'ar-c7') == (ST['FAIL'], R['NOTFOUND']) and call(m, 'sba_cover_have', 'ar-c7') == -1 and m.fs.get(f'{COVERS}/{fnv("ar-c7"):08x}-168.jpg') == b'', 'a WebP answer is the server\'s stand-in picture: an empty marker, no art')
    m = machine(site=Site(getCoverArt={'rc': 7}))
    run_one(m, 'sba_cover', 'c6')
    expect(state(m, K['COVER'], 'c6') == (ST['FAIL'], R['NET']) and call(m, 'sba_cover_have', 'c6') == 0, 'a network error leaves no marker (it is asked again later)')
    m = machine(site=Site(getCoverArt={'body': JPEG}))
    m.free_mb = 3
    run_one(m, 'sba_cover', 'c7')
    expect(state(m, K['COVER'], 'c7') == (ST['FAIL'], R['CARDFULL']) and call(m, 'sba_cover_have', 'c7') == 0, 'a nearly full card: no cover written')
    expect(call(m, 'sba_cover', '') == R['NOTFOUND'], 'an empty cover id: SBA_NOTFOUND')
    # a track shows its album's cover file (the one phase 2 fetched), not its own "mf-" cover: sba_track_cover(album id, own cover id, path, cap, ask)
    site = Site(getCoverArt={'body': JPEG})
    m = machine(site=site)
    albums = [dict(id=f'al{i}', cover=f'al-al{i}_5f') for i in range(1, 6)] + [dict(id='nocover', cover='')]   # (written in albums.idx order; the hashes are not in id order)
    seed(m, f'{ND}/albums.idx', 'album', albums)
    buf = m.alloc(128)
    file = lambda cover: f'{COVERS}/{fnv(cover):08x}-168.jpg'

    def track_cover(album, own, ask=1): return call(m, 'sba_track_cover', album, own, buf, 128, ask)

    def asked(): return [site.query(i)['id'] for i, v in enumerate(site.views()) if v == 'getCoverArt']
    expect(track_cover('al3', 'mf-s1_aa', 0) == 0 and not site.urls, 'ask 0 only looks at the card: nothing there, nothing asked')
    r, th = ask(m, 'sba_track_cover', 'al3', 'mf-s1_aa', buf, 128, 1)
    expect(r == 0 and th is not None and state(m, K['COVER'], 'al-al3_5f')[0] == ST['LOAD'] and state(m, K['COVER'], 'mf-s1_aa')[0] == ST['NONE'],
           'the album\'s cover is not cached: 0 and the ALBUM\'s cover id is queued, never the song\'s own')
    drain(m, th)
    expect(asked() == ['al-al3_5f'] and track_cover('al3', 'mf-s1_aa') == 1 and m.read_cstr(buf) == file('al-al3_5f'), 'the album\'s file arrives: 1 and its path')
    n0 = len(site.urls)
    expect(all(track_cover('al3', f'mf-s{i}_aa') == 1 and m.read_cstr(buf) == file('al-al3_5f') for i in range(2, 30)) and len(site.urls) == n0 and track_cover('al3', 'mf-s9_aa', 0) == 1,
           'every other song of the album answers 1 with the same file, no request (29 songs, 29 different own cover ids)')
    m.put(file('al-al5_5f'), JPEG)
    r, th = ask(m, 'sba_track_cover', 'al1', '', buf, 128, 1)
    expect(track_cover('al5', 'mf-zz_aa') == 1 and m.read_cstr(buf) == file('al-al5_5f') and r == 0 and th is not None and state(m, K['COVER'], 'al-al1_5f')[0] == ST['LOAD'],
           'a song with no cover id of its own still shows its album\'s; the first lookup of an album asks for its cover')
    drain(m, th)
    m.put(file('al-al2_5f'), b'')
    expect(track_cover('al2', 'mf-s1_aa') == -1 and state(m, K['COVER'], 'mf-s1_aa')[0] == ST['NONE'], 'an album the server has no picture for (empty marker): -1, the song\'s own cover is not tried')
    # the album is unknown, or has no coverArt: the song's own cover
    m.put(file('mf-own_aa'), JPEG)
    expect(track_cover('', 'mf-own_aa') == 1 and m.read_cstr(buf) == file('mf-own_aa') and track_cover('zz', 'mf-own_aa') == 1 and track_cover('nocover', 'mf-own_aa') == 1,
           'a song with no album id, an album that is not in albcov.idx, or an album with no coverArt shows its own cover file')
    r, th = ask(m, 'sba_track_cover', 'zz', 'mf-new_aa', buf, 128, 1)
    expect(r == 0 and th is not None and state(m, K['COVER'], 'mf-new_aa')[0] == ST['LOAD'] and track_cover('zz', '') == -1 and track_cover('', '', 0) == -1,
           'and asks for it when it is not cached; no cover at all: -1')
    drain(m, th)
    # albcov.idx is read again when a sync replaces it, and gone with the cache
    seed(m, f'{ND}/albums.idx', 'album', [dict(id='al3', cover='al-al3_6e')])
    expect(track_cover('al3', 'mf-s1_aa', 0) == 1, 'a changed albcov.idx is not read until a sync or a Sign Out moves it (the copy in memory answers)')
    call(m, 'sba_conf_clear')
    m.put(file('mf-s1_aa'), JPEG)
    expect(f'{ND}/albcov.idx' not in m.fs and track_cover('al3', 'mf-s1_aa', 0) == 1 and m.read_cstr(buf) == file('mf-s1_aa'), 'Sign Out removes albcov.idx and the copy: the song falls back to its own cover')
    # a stale albcov.idx (its row is another album, or beyond albums.idx): the album's row is read back only to ask, and the song's own cover is used
    m = machine(site=Site(getCoverArt={'body': JPEG}))
    seed(m, f'{ND}/albums.idx', 'album', [dict(id='x1', cover='al-x1'), dict(id='x2', cover='al-x2')])
    m.put(f'{ND}/albcov.idx', acov_file([dict(id='x2', cover='al-x2'), dict(id='x3', cover='al-x3')]))   # (x2 claims row 0, x3 row 1: both rows name other albums)
    buf = m.alloc(128)
    r, th = ask(m, 'sba_track_cover', 'x2', 'mf-x2_aa', buf, 128, 1)
    expect(r == 0 and th is not None and state(m, K['COVER'], 'mf-x2_aa')[0] == ST['LOAD'] and state(m, K['COVER'], 'al-x2')[0] == ST['NONE'],
           'an albcov.idx row that does not name the album in albums.idx: ignored, the song\'s own cover is asked for')


def play(ctx):
    expect = ctx.expect
    m = machine()
    buf = m.alloc(1100)
    expect(call(m, 'sba_stream_url', buf, 1024, 't1/x') == 0, 'a stream address is made')
    url = m.read_cstr(buf)
    q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
    expect(url.startswith(URL + '/rest/stream.view?') and q['id'] == 't1/x' and 't1%2Fx' in url and q['format'] == 'raw' and q['u'] == 'alice' and PASSWORD not in url
           and hashlib.md5((PASSWORD + q['s']).encode()).hexdigest() == q['t'], 'stream.view with the escaped id, format=raw (no transcoding), a salted token, no password')
    expect(q['s'] == SALT and q['t'] == secret(PASSWORD)[16:], 'the salt and the token are the saved secret\'s (nothing is made from a password per request)')
    expect(call(m, 'sba_stream_url', buf, 20, 't1') == -1 and call(m, 'sba_stream_url', buf, 1024, '') == -1 and call(machine(conf=False), 'sba_stream_url', buf, 1024, 't1') == -1,
           'a small buffer, an empty id or no server: -1')
    for suffix, want in (('dsf', 1), ('DFF', 1), ('dsd', 0), ('flac', 0), ('mp3', 0), ('', 0), ('dsfx', 0)):
        got = call(m, 'sba_is_dsd', suffix)
        expect(got == want, f'sba_is_dsd({suffix!r}) == {want}')
    # the queue record's file name
    def fname(**kw):
        t = m.alloc(struct.calcsize(TRACK))
        m.u.mem_write(t, row('track', **kw))
        n = call(m, 'sba_track_filename', buf, 64, t)
        return n, m.read_cstr(buf) if n >= 0 else None
    expect(fname(title='Song', suffix='flac') == (9, 'Song.flac'), 'title.suffix')
    expect(fname(title='A/B\tC', suffix='mp3')[1] == 'A_B_C.mp3', 'a slash and control characters are replaced')
    expect(fname(title='', suffix='dsf') == (12, 'Untitled.dsf'), 'no title: Untitled')
    expect(fname(title='T', suffix='f/la')[1] == 'T', 'a suffix with odd characters is left off')
    n, name = fname(title='音' * 40, suffix='flac')
    expect(0 < n < 64 and name.endswith('.flac') and len(name.encode('latin-1')) == n and name.encode('latin-1')[:-5].decode('utf-8') == '音' * ((n - 5) // 3), 'a long title is cut at a character boundary and keeps the suffix')
    # the queue map
    ids = ['t%d' % i for i in range(3)] + ['t0']          # a repeated id collides
    tracks = m.alloc(struct.calcsize(TRACK) * 4)
    for i, ident in enumerate(ids):
        m.u.mem_write(tracks + i * struct.calcsize(TRACK), row('track', id=ident, cover=f'cv-{ident}', title=ident, album_id=f'al-{ident}', suffix='flac', size=1000 * (i + 1)))
    recs = m.alloc(16)
    call(m, 'sba_queue_note', tracks, 4, recs)
    rec = [struct.unpack('<i', bytes(m.u.mem_read(recs + 4 * i, 4)))[0] for i in range(4)]
    expect(rec[0] == -((fnv('t0') & 0x3fffffff) + 2) and all(r <= -2 for r in rec) and len(set(rec)) == 4 and rec[3] == rec[0] - 1, f'synthetic REC_IDs are -(FNV-1a & 0x3fffffff) - 2, a collision is bumped: {rec}')
    expect(m.read_cstr(call(m, 'sba_rec_track', rec[1])) == 't1' and m.read_cstr(call(m, 'sba_rec_track', rec[3])) == 't0' and m.read_cstr(call(m, 'sba_rec_track', -999)) == '' and m.read_cstr(call(m, 'sba_rec_track', 5)) == '',
           'sba_rec_track maps a queue record back to its track id, "" for anything else')
    expect([call(m, 'sba_rec_size', rec[i]) for i in range(3)] == [1000, 2000, 3000] and call(m, 'sba_rec_size', -999) == 0 and call(m, 'sba_rec_size', 5) == 0,
           'sba_rec_size: the server size noted with the queue, 0 for an unknown or local record')
    m.put(f'{COVERS}/{fnv("cv-t1"):08x}-168.jpg', JPEG)
    record = m.alloc(0x60)
    m.setword(record, rec[1] & 0xffffffff)
    p = call(m, 'sba_now_cover', record)
    expect(p and m.read_cstr(p) == f'{COVERS}/{fnv("cv-t1"):08x}-168.jpg', 'sba_now_cover: the playing record -> its cover file in the Navidrome folder')
    m.setword(record, rec[2] & 0xffffffff)
    r, th = ask(m, 'sba_now_cover', record)
    expect(r == 0 and th and state(m, K['COVER'], 'cv-t2') == (ST['LOAD'], 0), 'no cover file yet: NULL, and the cover is asked for')
    drain(m, th)
    r, th = ask(m, 'sba_now_cover', record)
    expect(r == 0 and not th, 'asked once: a repeat while it is queued or after it failed starts nothing')
    m.setword(record, 7)
    expect(call(m, 'sba_now_cover', record) == 0 and call(m, 'sba_now_cover', 0) == 0, 'a local record or NULL: NULL')
    # sba_rec_cover: the same lookup with its answer kept apart (1 there, 0 on its way, -1 none)
    path = m.alloc(160)
    m.setword(record, rec[1] & 0xffffffff)
    expect(call(m, 'sba_rec_cover', record, path, 160) == 1 and m.read_cstr(path) == f'{COVERS}/{fnv("cv-t1"):08x}-168.jpg', 'sba_rec_cover: 1 and the path of a cached cover')
    m.setword(record, rec[0] & 0xffffffff)
    r, th = ask(m, 'sba_rec_cover', record, path, 160)
    expect(r == 0 and th, 'sba_rec_cover: a cover not cached yet is asked for and answers 0 (look again)')
    drain(m, th)
    m.setword(record, rec[2] & 0xffffffff)
    expect(call(m, 'sba_rec_cover', record, path, 160) == -1, 'sba_rec_cover: a cover whose ask failed answers -1 (the placeholder), not asked again')
    m.put(f'{COVERS}/{fnv("cv-t0"):08x}-168.jpg', b'')
    m.setword(record, rec[0] & 0xffffffff)
    expect(call(m, 'sba_rec_cover', record, path, 160) == -1, 'sba_rec_cover: the server has no picture (an empty marker file): -1')
    m.setword(record, 7)
    expect(call(m, 'sba_rec_cover', record, path, 160) == -1 and call(m, 'sba_rec_cover', 0, path, 160) == -1, 'sba_rec_cover: a local record or NULL: -1, nothing asked')
    # sba_rec_row: what the map kept (id, cover, album, suffix, size) so a queue record can be starred or downloaded
    out = m.alloc(struct.calcsize(TRACK))
    t1 = unrow('track', bytes(m.u.mem_read(out, struct.calcsize(TRACK)))) if call(m, 'sba_rec_row', rec[1], out) == 1 else None
    expect(t1 and (t1[0], t1[4], t1[5], t1[6], t1[11]) == ('t1', 'al-t1', 'cv-t1', 'flac', 2000) and not t1[1], 'sba_rec_row: id, album id, cover, suffix and size of the queue record\'s track, the rest zero')
    expect(call(m, 'sba_rec_row', 7, out) == 0 and call(m, 'sba_rec_row', -999, out) == 0, 'sba_rec_row: a local or unknown record is not ours')
    call(m, 'sba_queue_note', tracks, 1, recs)
    expect(m.read_cstr(call(m, 'sba_rec_track', rec[1])) == '', 'a new queue replaces the map')


def urls(ctx):
    """sbn_url leaves a terminated string in every shape (id only, id + extra, no id, an escaped id, stream): the output buffer and the stack are pre-filled with 'A', so a missing terminator
    shows as trailing garbage (sbn_urlenc writes none)."""
    expect = ctx.expect
    m = machine()
    out = m.alloc(1024)
    shapes = [('getArtist', 'ar 1/x', None), ('getAlbum', 'al1', None), ('getPlaylist', 'pl1', None), ('download', 'tr-1', None), ('star', 'a\u00e9b', None), ('getArtists', None, None),
              ('getAlbumList2', None, '&type=newest&size=500'), ('search3', None, '&query=a%20b'), ('getArtist', 'ar1', '&x=1'), ('stream', 'tr-1', None), ('getCoverArt', 'cv-1', '&size=240')]
    bad = []
    for view, ident, extra in shapes:
        m.u.mem_write(out, b'A' * 1024)
        m.u.mem_write(STACK - 0x20000, b'A' * 0x20000)
        r = call(m, 'sbn_url', out, 1024, URL, 'alice', secret(PASSWORD), view, ident or 0, extra or 0)
        u = m.read_cstr(out)
        q = parse_qs(urlparse(u).query, keep_blank_values=True)
        want = {'u': ['alice'], 'v': ['1.16.1'], 'c': ['m1plus-music'], 'f': ['json']}
        if ident is not None: want['id'] = [ident]
        if view == 'stream': want['format'] = ['raw']
        want.update({k: v for k, v in parse_qs((extra or '').lstrip('&')).items()})
        got = {k: v for k, v in q.items() if k not in ('t', 's')}
        if r != 0 or got != want or 'AAAA' in u or not u.startswith(f'{URL}/rest/{view}.view?u=alice&t='):
            bad.append((view, ident, extra, r, u[-40:]))
    expect(not bad, f'every request shape ends where its last parameter ends, with a dirty buffer and stack ({bad[:2]})')
    m.u.mem_write(out, b'A' * 64)
    r = call(m, 'sbn_url', out, 40, URL, 'alice', secret(PASSWORD), 'getAlbum', 'al1', 0)
    expect(r == -1, 'an output too small for the request fails')
    expect(call(m, 'sbn_url', out, 1024, URL, 'alice', PASSWORD, 'ping', 0, 0) == -1 and call(m, 'sbn_url', out, 1024, URL, 'alice', secret(PASSWORD) + '0', 'ping', 0, 0) == -1
           and call(m, 'sbn_url', out, 1024, URL, 'alice', secret(PASSWORD).upper(), 'ping', 0, 0) == -1, 'a login that is not a secret (a password, a longer or upper-case text) makes no address')


def trial(ctx):
    """sba_ping_try: a ping with a login that is not saved (the sign-in page saves it only once the server has answered)."""
    expect = ctx.expect
    m = machine(conf=False)
    site = Site()
    m.curl_site = site
    r, th = ask(m, 'sba_ping_try', 'http://box.local:4533/', 'bob', 'pw|1')
    expect(r == R['OK'] and th is not None, 'with no server saved a trial ping is asked')
    drain(m, th)
    q = site.query()
    expect(site.urls[0].startswith('http://box.local:4533/rest/ping.view?') and q['u'] == 'bob' and hashlib.md5(('pw|1' + q['s']).encode()).hexdigest() == q['t'],
           'it goes to the cleaned address with the typed user and a token of the typed password')
    expect(tstate(m) == ST['OK'] and CONF not in m.fs and call(m, 'sba_configured') == 0, 'it answered, and nothing was saved: still no server')
    # a working login is left alone by a trial (and by a failed one), an empty password means the saved one
    m = machine()
    seed(m, f'{ND}/albums.idx', 'album', [dict(id='a1', name='One')])
    old = m.fs[CONF]
    site = Site(ping={'body': err_json(40)})
    m.curl_site = site
    r, th = ask(m, 'sba_ping_try', 'http://other.local', 'alice', '')
    drain(m, th)
    q = site.query()
    expect(site.urls[0].startswith('http://other.local/rest/ping.view?') and hashlib.md5((PASSWORD + q['s']).encode()).hexdigest() == q['t'],
           'an empty password uses the saved one')
    expect(tstate(m) == ST['FAIL'] and m.fs[CONF] == old and f'{ND}/albums.idx' in m.fs and call(m, 'sba_url') != 'http://other.local', 'a refused trial leaves the conf and the cache alone')
    r, th = ping_saved(m)
    drain(m, th)
    expect(site.urls[-1].startswith(URL + '/rest/ping.view?'), 'the next ping with the saved login goes to the saved server')
    for args, what in (((0, 'ftp://x'), 'address'), ((1, 'a|b'), 'user'), ((2, ''), 'password')):
        expect(call(m, 'sba_conf_check', *args) == R['PARSE'], f'sba_conf_check refuses a bad {what}')
    expect(call(m, 'sba_conf_check', 0, 'http://h:1') == 0 and call(m, 'sba_conf_check', 1, 'bob') == 0 and call(m, 'sba_conf_check', 2, 'p|w') == 0, 'and takes good ones, saving nothing')
    m.wifi = 0
    r, th = ask(m, 'sba_ping_try', 'http://other.local', 'alice', 'x')
    expect(r == R['NOWIFI'] and th is None, 'no Wi-Fi: SBA_NOWIFI at once')
    r, th = ask(m, 'sba_ping_try', 'nope', 'alice', 'x')
    expect(r == R['PARSE'] and th is None, 'a bad address: SBA_PARSE')
    # two sign-ins while the first ping is still queued: each is its own request with its own login and id
    m = machine(conf=False)
    seen = []
    def ping(url, opts):
        seen.append((re.match(r'http://(\w+)', url).group(1), parse_qs(urlparse(url).query)['u'][0]))
        return {'body': ok_json()}
    m.curl_site = Site(ping=ping)
    r, th = ask(m, 'sba_ping_try', 'http://aaa.local', 'ann', 'pa')
    ida = call(m, 'sba_trial_id')
    r2, th2 = ask(m, 'sba_ping_try', 'http://bbb.local', 'bob', 'pb')
    idb = call(m, 'sba_trial_id')
    expect(r == R['OK'] and r2 == R['OK'] and th2 is None and ida and idb and ida != idb, 'a second trial is queued as its own request with its own id')
    expect(call(m, 'sba_trial_state', ida, 0) == ST['LOAD'] and call(m, 'sba_trial_state', idb, 0) == ST['LOAD'], 'both are loading')
    drain(m, th)
    expect(seen == [('aaa', 'ann'), ('bbb', 'bob')], f'both go out, each with the login it was asked with ({seen})')
    expect(call(m, 'sba_trial_state', ida, 0) == ST['OK'] and call(m, 'sba_trial_state', idb, 0) == ST['OK'] and call(m, 'sba_trial_state', idb + 5, 0) == ST['NONE'], 'each id has its own answer, an unknown id has none')
    m = machine(conf=False)
    m.curl_site = Site(ping=lambda url, opts: {'body': ok_json()} if 'aaa' in url else {'body': err_json(40)})
    r, th = ask(m, 'sba_ping_try', 'http://aaa.local', 'ann', 'pa')
    ida = call(m, 'sba_trial_id')
    ask(m, 'sba_ping_try', 'http://bbb.local', 'bob', 'pb')
    idb = call(m, 'sba_trial_id')
    drain(m, th)
    expect(call(m, 'sba_trial_state', ida, 0) == ST['OK'] and call(m, 'sba_trial_state', idb, 0) == ST['FAIL'], 'A answering OK says nothing about B: B has its own failure')
    m = machine(conf=False)
    r, th = ask(m, 'sba_ping_try', 'http://aaa.local', 'ann', 'pa')
    ida = call(m, 'sba_trial_id')
    call(m, 'sba_cancel')
    expect(call(m, 'sba_trial_state', ida, 0) == ST['NONE'], 'a cancelled trial is dropped')


# --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
# Phase 2, the background fill (patch/sbapi.c "Phase 2")
def bg_lib(counts=(100, 100, 30), **routes):
    """A scripted library: albums a0.. with counts[i] songs each, search3 serving them interleaved (so no album is contiguous) in pages of 100, getAlbum serving one album in disc / track order.
    Returns (site, songs in the order search3 gives them, album ids)."""
    ids = [f'a{i}' for i in range(len(counts))]
    by = {a: [dict(id=f'{a}-t{t}', title=f'{a} T{t}', artist='Art', album=f'Album {a}', albumId=a, coverArt=f'al-{a}', track=t % 20 + 1, discNumber=t // 20 + 1, suffix='flac',
                   size=1000 + t, duration=100 + t, year=2020) for t in range(n)] for a, n in zip(ids, counts)}
    songs = [by[a][t] for t in range(max(counts)) for a in ids if t < len(by[a])]

    def page(url, o):
        off = int(parse_qs(urlparse(url).query)['songOffset'][0])
        return {'body': ok_json(searchResult3={'song': songs[off:off + 100]})}

    def album(url, o):
        a = parse_qs(urlparse(url).query)['id'][0]
        return {'body': ok_json(album={'id': a, 'name': f'Album {a}', 'coverArt': f'al-{a}', 'year': 2020, 'song': sorted(by[a], key=lambda s: (s['discNumber'], s['track']))})}
    site = Site(getAlbumList2={'body': ok_json(albumList2={'album': [dict(id=a, name=f'Album {a}', artist='Art', artistId='ar1', songCount=n, duration=n * 100, coverArt=f'al-{a}', created='2024-01-02T03:04:05Z')
                                                                      for a, n in zip(ids, counts)]})},
                getArtists={'body': ok_json(artists={'index': []})}, getPlaylists={'body': ok_json(playlists={'playlist': []})}, getStarred2={'body': ok_json(starred2={})},
                search3=page, getCoverArt={'body': JPEG}, getAlbum=album, **routes)
    return site, songs, ids


def bg_machine(site, **kw):
    m = machine(site=site, **kw)
    m.wall = 1800000000
    return m


def bg_progress(m):
    """(kind, done, total) of sba_bg_progress, read from inside a callback (the emulator is running)."""
    d, t = m.alloc(4), m.alloc(4)
    k = m.nested(PSYMS['sba_bg_progress'], d, t)
    return (k, m.word(d), m.word(t))


def bg_run(m):
    """A sync, the worker run to its end."""
    r = run_one(m, 'sba_sync')
    assert r == 0, r


def sleeps_of(m): return len([c for c in m.calls if c[0] == 'sleep'])


def bg_stage(m):
    t = m.fs.get(f'{ND}/bg.txt')
    return tuple(int(x) for x in t.split()) if t else None


def bg(ctx):
    expect = ctx.expect
    # A then B after the sync, on the same worker; the progress is published as it goes
    seen = []
    site, songs, ids = bg_lib()
    inner = site.routes['search3']
    cover_inner = site.routes['getCoverArt']
    holder = {}
    site.routes['search3'] = lambda url, o: (seen.append(bg_progress(holder['m'])), inner(url, o))[1]
    site.routes['getCoverArt'] = lambda url, o: (seen.append(bg_progress(holder['m'])), cover_inner)[1]
    m = bg_machine(site)
    holder['m'] = m
    expect(call(m, 'sba_bg_progress', 0, 0) == 0, 'idle before anything ran')
    bg_run(m)
    v = site.views()
    expect(v[:4] == ['getAlbumList2', 'getArtists', 'getPlaylists', 'getStarred2'], 'the sync (phase 1) goes first, whole')
    expect(v[4:] == ['search3'] * 3 + ['getCoverArt'] * 3 and [site.query(i)['songOffset'] for i in (4, 5, 6)] == ['0', '100', '200'],
           f'then A (search3 from offset 0, 100, 200: three pages of the Songs pager\'s request) and then B (a cover a request): {v[4:]}')
    expect([site.query(i)['songCount'] for i in (4, 5, 6)] == ['100'] * 3 and site.query(4)['query'] == '', 'the pager\'s own request: an empty query, 100 songs a page')
    expect(seen[:3] == [(1, 0, 230), (1, 100, 230), (1, 200, 230)] and seen[3:] == [(2, 0, 3), (2, 1, 3), (2, 2, 3)], f'progress: songs 0, 100, 200 of 230, then covers 0, 1, 2 of 3 ({seen})')
    expect(call(m, 'sba_bg_progress', 0, 0) == 0 and busy(m) == 0, 'idle again at the end, the worker ended')
    rows = read_rows(m, f'{ND}/songs.idx', 'track')
    expect(len(rows) == 230 and call(m, 'sba_songs_more') == 0 and call(m, 'sba_songs_cached') == 230 and f'{ND}/songs.part' not in m.fs, 'songs.idx holds the whole library (no more pages to ask), songs.part is gone')
    expect([r[0] for r in rows] == [s['id'] for s in songs], 'in the order the server gave')
    # the album files derived from the songs are the getAlbum path's
    ref = bg_machine(Site(getAlbum=site.routes['getAlbum']))
    same = True
    for a in ids:
        run_one(ref, 'sba_fetch_album', a)
        want = sorted(read_rows(ref, f'{ND}/al/{a}.idx', 'track'), key=lambda r: (r[9], r[8]))
        got = read_rows(m, f'{ND}/al/{a}.idx', 'track')
        same = same and got is not None and sorted(got, key=lambda r: (r[9], r[8])) == want and len(got) == len(want)
    expect(same, 'al/<id>.idx derived from the songs holds the same rows as the file getAlbum writes (ids, titles, sizes, suffix, cover, disc / track, year)')
    n0 = len(site.urls)
    # an album page is served from the derived file: no request is needed
    out = m.alloc(8)
    expect(call(m, 'sba_album_tracks', 'a2', out) == 30 and len(site.urls) == n0, 'sba_album_tracks answers from the derived file')
    expect([call(m, 'sba_cover_have', f'al-{a}') for a in ids] == [1, 1, 1], 'every album\'s cover is cached at the list size')
    expect([site.query(i)['id'] for i in range(7, 10)] == ['al-a0', 'al-a1', 'al-a2'] and site.query(7)['size'] == '168', 'covers in the albums\' order, at SBA_COVER_PX')
    expect(bg_stage(m)[1] == 5 and not [p for p in m.fs if p.endswith('.tmp')], 'the cursor file says done; no temp file')
    # a second sync of the same library: A and B do not run again; nothing is requested for them
    n = len(site.urls)
    run_one(m, 'sba_sync')
    expect(site.views()[n:] == ['getAlbumList2', 'getArtists', 'getPlaylists', 'getStarred2'], f'the same library: only phase 1 again ({site.views()[n:]})')
    r, th = ask(m, 'sba_bg_kick')
    expect(th is None, 'a kick with nothing left starts no worker')
    r, th = ask(m, 'sba_sync_auto')
    expect(th is None, 'a fresh cache and a finished fill: the root page\'s open queues nothing')
    # the library changed (one more song): the fill runs again, the covers already there are not fetched again
    site.routes['getAlbumList2'] = {'body': ok_json(albumList2={'album': [dict(id=a, name=f'Album {a}', artist='Art', artistId='ar1', songCount=n + (a == 'a2'), duration=n * 100, coverArt=f'al-{a}',
                                                                                created='2024-01-02T03:04:05Z') for a, n in zip(ids, (100, 100, 30))]})}
    n = len(site.urls)
    run_one(m, 'sba_sync')
    v = site.views()[n:]
    expect(v == ['getAlbumList2', 'getArtists', 'getPlaylists', 'getStarred2', 'search3', 'search3', 'search3', 'search3'], f'another signature: A again (the sync says 231 songs, the server holds 230: one empty page ends it), B has nothing to fetch ({v})')
    expect(bg_stage(m)[1] == 5, 'and done again')
    # a library a week old is filled again whatever the signature
    m.wall += 7 * 86400
    expect(call(m, 'sba_sync_due') == 1, 'a week later the sync is due')
    r, th = ask(m, 'sba_bg_kick')
    expect(th is not None, 'a finished fill a week old starts again on a kick')
    drain(m, th)

    # the Wi-Fi: nothing starts without it
    site, songs, ids = bg_lib()
    m = bg_machine(site)
    bg_run(m)
    m2 = bg_machine(site)
    m2.fs.update({k: v for k, v in m.fs.items() if k.startswith(ND + '/albums') or k.endswith('sync.txt')})
    m2.wifi = -1
    r, th = ask(m2, 'sba_bg_kick')
    expect(th is None and m2.fs.get(f'{ND}/bg.txt') is None, 'no Wi-Fi: a kick starts nothing')
    m2.wifi = 4
    r, th = ask(m2, 'sba_bg_kick')
    expect(th is not None, 'with Wi-Fi the kick starts the worker (a synced library nobody filled)')
    n = len(site.urls)
    drain(m2, th)
    expect(site.views()[n] == 'search3' and bg_stage(m2)[1] == 5, 'it fills from the cache: no sync request, the pages then the covers')

    # a request a page makes goes first, and cuts the transfer of phase 2 off; the cut-off page is asked again
    site, songs, ids = bg_lib()
    holder = {}
    fired = []

    def first_search(url, o):
        if not fired:
            fired.append(1)
            holder['m'].nested(PSYMS['sba_fetch_album'], holder['m'].cstr('a1'))   # a page opens an album while the first page of songs is out
        return page_inner(url, o)
    page_inner = site.routes['search3']
    site.routes['search3'] = first_search
    m = bg_machine(site)
    holder['m'] = m
    bg_run(m)
    v = site.views()
    expect(v[4:7] == ['search3', 'getAlbum', 'search3'] and site.query(4)['songOffset'] == '0' and site.query(6)['songOffset'] == '0' and site.query(5)['id'] == 'a1',
           f'the album request ran before the page of songs, which was asked again from the same offset ({v[4:8]})')
    expect(state(m, K['ALBUM'], 'a1') == (ST['OK'], 0) and len(read_rows(m, f'{ND}/songs.idx', 'track')) == 230 and sleeps_of(m) == 0,
           'the cut-off was not an error: no pause, the fill finished')

    # errors back off, five in a row end the run; the next kick resumes at the page it stopped at
    site, songs, ids = bg_lib()
    ok_search = site.routes['search3']
    state_ = {'bad': False}

    def flaky(url, o):
        off = int(parse_qs(urlparse(url).query)['songOffset'][0])
        if off >= 100 and state_['bad']: return {'rc': 7}
        return ok_search(url, o)
    site.routes['search3'] = flaky
    m = bg_machine(site)
    state_['bad'] = True
    slept = []
    m.on_sleep = lambda k: slept.append(k)
    bg_run(m)
    v = site.views()
    expect(v[4:] == ['search3'] * 6 and [site.query(i)['songOffset'] for i in range(4, 10)] == ['0'] + ['100'] * 5, f'a failing page is tried five times and the run ends ({v[4:]})')
    expect(len(slept) == 10 + 20 + 40 + 60 and call(m, 'sba_bg_progress', 0, 0) == 0 and busy(m) == 0, f'with pauses of 10, 20, 40 and 60 s between them ({len(slept)} s), then idle')
    part = m.fs[f'{ND}/songs.part']
    expect(len(part) == 16 + 100 * struct.calcsize(TRACK) and bg_stage(m)[1] == 1 and f'{ND}/songs.idx' not in m.fs, 'songs.part keeps the first page, bg.txt the stage; songs.idx is not touched')
    state_['bad'] = False
    m.on_sleep = None
    n = len(site.urls)
    r, th = ask(m, 'sba_bg_kick')
    expect(th is not None, 'the next kick resumes')
    drain(m, th)
    v = site.views()[n:]
    expect(v == ['search3', 'search3'] + ['getCoverArt'] * 3 and [site.query(i)['songOffset'] for i in (n, n + 1)] == ['100', '200'], f'from offset 100 (the first page is not fetched again), then the covers ({v})')
    expect(len(read_rows(m, f'{ND}/songs.idx', 'track')) == 230 and bg_stage(m)[1] == 5, 'complete')
    # an authentication error ends the run at once, no retries
    site, songs, ids = bg_lib()
    site.routes['search3'] = {'body': err_json(40)}
    m = bg_machine(site)
    bg_run(m)
    expect(site.views()[4:] == ['search3'] and not [c for c in m.calls if c[0] == 'sleep'], 'a refused login: one try, no pause')

    # the card: below the downloads\' floor nothing is fetched
    site, songs, ids = bg_lib()
    m = bg_machine(site)
    m.free_mb = 20
    bg_run(m)
    expect(site.views()[4:] == [] and f'{ND}/songs.part' not in m.fs and call(m, 'sba_bg_progress', 0, 0) == 0, 'under 32 MiB free: phase 2 fetches nothing and keeps nothing')

    # a download goes first: phase 2 waits for it
    site, songs, ids = bg_lib()
    m = bg_machine(site)
    sbd_busy = PSYMS['sbd'] + 8
    m.setword(sbd_busy, 1)
    waits = []

    def on_sleep(k):
        waits.append(len(site.urls))
        if k == 3: m.setword(sbd_busy, 0)
    m.on_sleep = on_sleep
    bg_run(m)
    expect(waits == [4, 4, 4] and site.views()[4:5] == ['search3'], f'while the download worker runs phase 2 sleeps (three seconds here) and asks for nothing ({waits})')
    m.on_sleep = None

    # Sign Out stops it and its files go with the cache
    site, songs, ids = bg_lib()
    holder = {}
    page_inner = site.routes['search3']
    done = []

    def sign_out(url, o):
        if len([u for u in site.urls if 'search3' in u]) == 2 and not done:
            done.append(1)
            holder['m'].nested(PSYMS['sba_conf_clear'])
        return page_inner(url, o)
    site.routes['search3'] = sign_out
    m = bg_machine(site)
    holder['m'] = m
    run_one(m, 'sba_sync')
    names = [p for p in m.fs if p.startswith(ND + '/') and 'dl.' not in p]
    expect(done and busy(m) == 0 and call(m, 'sba_bg_progress', 0, 0) == 0 and not names and site.views().count('search3') == 2 and 'getCoverArt' not in site.views(),
           f'Sign Out in the middle of the songs: the transfer is cut off, the worker ends, no more requests, no file is left ({names})')
    r, th = ask(m, 'sba_bg_kick')
    expect(th is None, 'and a kick has no library to fill')

    # covers: cached ones and the empty markers are skipped; a 404 leaves a marker and counts; an album with no cover id is left out
    site, songs, ids = bg_lib((3, 3, 3, 3, 3))
    site.routes['getAlbumList2'] = {'body': ok_json(albumList2={'album': [dict(id=a, name=f'Album {a}', artist='Art', songCount=3, **({} if a == 'a4' else {'coverArt': f'al-{a}'})) for a in ids]})}
    site.routes['getCoverArt'] = lambda url, o: {'rc': 22, 'code': 404} if parse_qs(urlparse(url).query)['id'][0] == 'al-a3' else {'body': JPEG}
    m = bg_machine(site)
    m.put(f'{COVERS}/{fnv("al-a0"):08x}-168.jpg', JPEG)   # cached
    m.put(f'{COVERS}/{fnv("al-a2"):08x}-168.jpg', b'')    # known to have no art
    seen = []
    cover_route = site.routes['getCoverArt']
    holder['m'] = m
    site.routes['getCoverArt'] = lambda url, o: (seen.append(bg_progress(m)), cover_route(url, o))[1]
    bg_run(m)
    got = [site.query(i)['id'] for i, vname in enumerate(site.views()) if vname == 'getCoverArt']
    expect(got == ['al-a1', 'al-a3'], f'only the missing covers, in the albums\' order ({got})')
    expect(seen == [(2, 0, 2), (2, 1, 2)] and call(m, 'sba_cover_have', 'al-a3') == -1 and call(m, 'sba_cover_have', 'al-a1') == 1 and bg_stage(m)[1] == 5,
           f'progress counts what was left to fetch; a 404 leaves the marker and counts as fetched ({seen})')

    # artist pictures: the stage after the covers, the same rules. r0 cached, r1 fetched, r2 a 404, r3 Navidrome's WebP stand-in (no art: a marker, not an error), r4 no coverArt id, r5 a marker already
    WEBP = b'RIFF\x1a\0\0\0WEBPVP8 ' + bytes(40)
    arts = [dict(id=f'r{i}', name=f'Artist {i}', albumCount=1, **({} if i == 4 else {'coverArt': f'ar-r{i}'})) for i in range(6)]

    def art_lib(**routes):
        site, songs, ids = bg_lib((3, 3), **routes)
        site.routes['getArtists'] = {'body': ok_json(artists={'index': [{'name': 'A', 'artist': arts}]})}
        return site, ids

    def art_route(site, m, seen=None):
        def cover(url, o):
            i = parse_qs(urlparse(url).query)['id'][0]
            if seen is not None: seen.append((i, bg_progress(m)))
            return {'rc': 22, 'code': 404} if i == 'ar-r2' else {'body': WEBP} if i == 'ar-r3' else {'body': JPEG}
        site.routes['getCoverArt'] = cover
    site, ids = art_lib()
    m = bg_machine(site)
    seen = []
    art_route(site, m, seen)
    m.put(f'{COVERS}/{fnv("ar-r0"):08x}-168.jpg', JPEG)
    m.put(f'{COVERS}/{fnv("ar-r5"):08x}-168.jpg', b'')
    bg_run(m)
    got = [site.query(i)['id'] for i, vname in enumerate(site.views()) if vname == 'getCoverArt']
    expect(got == ['al-a0', 'al-a1', 'ar-r1', 'ar-r2', 'ar-r3'], f'the albums\' covers, then only the artists\' missing pictures in artists.idx order ({got})')
    expect([s for s in seen if s[0].startswith('ar-')] == [('ar-r1', (3, 0, 3)), ('ar-r2', (3, 1, 3)), ('ar-r3', (3, 2, 3))], f'progress kind 3: the total is what was missing when the stage began ({seen})')
    expect(call(m, 'sba_cover_have', 'ar-r1') == 1 and call(m, 'sba_cover_have', 'ar-r2') == -1 and call(m, 'sba_cover_have', 'ar-r3') == -1 and m.fs[f'{COVERS}/{fnv("ar-r3"):08x}-168.jpg'] == b''
           and call(m, 'sba_cover_have', 'ar-r4') == 0 and bg_stage(m)[1] == 5 and call(m, 'sba_bg_progress', 0, 0) == 0,
           'a 404 and a WebP leave the empty marker and count as fetched; the artist with no id is left out; the fill is done')
    p, n = m.alloc(256), len(site.urls)
    expect(call(m, 'sba_cover_get', 'ar-r1', p, 256) == 1 and call(m, 'sba_cover_get', 'ar-r3', p, 256) == -1 and call(m, 'sba_cover_get', '', p, 256) == -1 and len(site.urls) == n,
           'the pages read those: the file, -1 for the marker and for no id, nothing asked')
    # a second run (a week later): nothing is fetched again; a picture removed from the card is the only one fetched
    n = len(site.urls)
    m.wall += 7 * 86400
    m.fs.pop(f'{COVERS}/{fnv("ar-r1"):08x}-168.jpg')
    r, th = ask(m, 'sba_bg_kick')
    drain(m, th)
    got = [site.query(i)['id'] for i in range(n, len(site.urls)) if site.views()[i] == 'getCoverArt']
    expect(got == ['ar-r1'] and bg_stage(m)[1] == 5, f're-run: only the missing picture is fetched ({got})')
    # an artist whose picture fails three times is left for the next run (the stage stays), the others go on; the next run fetches that one
    site, ids = art_lib()
    m = bg_machine(site)
    state_ = {'bad': True}
    art_route(site, m)
    good = site.routes['getCoverArt']
    site.routes['getCoverArt'] = lambda url, o: {'rc': 22, 'code': 500} if parse_qs(urlparse(url).query)['id'][0] == 'ar-r1' and state_['bad'] else good(url, o)
    m.on_sleep = lambda k: None
    bg_run(m)
    got = [site.query(i)['id'] for i, vname in enumerate(site.views()) if vname == 'getCoverArt']
    expect(got.count('ar-r1') == 3 and got[-3:] == ['ar-r2', 'ar-r3', 'ar-r5'] and bg_stage(m)[1] == 4 and call(m, 'sba_cover_have', 'ar-r3') == -1,
           f'a picture that fails three times is skipped for the run, the next ones are fetched, the stage stays ({got}, {bg_stage(m)})')
    state_['bad'] = False
    n = len(site.urls)
    r, th = ask(m, 'sba_bg_kick')
    drain(m, th)
    got = [site.query(i)['id'] for i in range(n, len(site.urls)) if site.views()[i] == 'getCoverArt']
    expect(got == ['ar-r1'] and bg_stage(m)[1] == 5 and call(m, 'sba_cover_have', 'ar-r1') == 1, f'the next run fetches only the one left ({got})')
    # an album cover that failed comes first in the next run: the fill goes on to the artists, then goes back to the covers stage
    site, ids = art_lib()
    m = bg_machine(site)
    art_route(site, m)
    good = site.routes['getCoverArt']
    state_ = {'bad': True}
    site.routes['getCoverArt'] = lambda url, o: {'rc': 22, 'code': 500} if parse_qs(urlparse(url).query)['id'][0] == 'al-a1' and state_['bad'] else good(url, o)
    m.on_sleep = lambda k: None
    bg_run(m)
    got = [site.query(i)['id'] for i, vname in enumerate(site.views()) if vname == 'getCoverArt']
    expect(got.count('al-a1') == 3 and got[-5:] == ['ar-r0', 'ar-r1', 'ar-r2', 'ar-r3', 'ar-r5'] and bg_stage(m)[1] == 3, f'a cover left for the next run does not hold the artists back; the stage is covers again at the end ({got}, {bg_stage(m)})')
    state_['bad'] = False
    n = len(site.urls)
    r, th = ask(m, 'sba_bg_kick')
    drain(m, th)
    got = [site.query(i)['id'] for i in range(n, len(site.urls)) if site.views()[i] == 'getCoverArt']
    expect(got == ['al-a1'] and bg_stage(m)[1] == 5, f'the next run fetches that cover, finds the artists done ({got})')
    # a request a page makes goes first and cuts the picture off; it is asked again, with no pause
    site, ids = art_lib()
    holder = {}
    fired = []
    m = bg_machine(site)
    holder['m'] = m
    art_route(site, m)
    good = site.routes['getCoverArt']

    def cut(url, o):
        if parse_qs(urlparse(url).query)['id'][0] == 'ar-r1' and not fired:
            fired.append(1)
            holder['m'].nested(PSYMS['sba_fetch_album'], holder['m'].cstr('a1'))
        return good(url, o)
    site.routes['getCoverArt'] = cut
    bg_run(m)
    v = site.views()
    k = [i for i, x in enumerate(v) if x == 'getCoverArt' and site.query(i)['id'] == 'ar-r1']
    expect(len(k) == 2 and v[k[0] + 1] == 'getAlbum' and sleeps_of(m) == 0 and bg_stage(m)[1] == 5, f'the page\'s album request ran before the picture, which was asked again; no pause, done ({v[k[0]:k[0] + 3]})')
    # no answer from the server at all (Wi-Fi gone): not a try of the cover and never a skip; the run ends after SBA_BG_FAILS failures on the same cover, the stage and cursor stay, the next kick resumes
    site, ids = art_lib()
    m = bg_machine(site)
    art_route(site, m)
    good = site.routes['getCoverArt']
    state_ = {'down': True}
    site.routes['getCoverArt'] = lambda url, o: {'rc': 7} if state_['down'] else good(url, o)
    slept = []
    m.on_sleep = lambda k: slept.append(k)
    bg_run(m)
    got = [site.query(i)['id'] for i, vname in enumerate(site.views()) if vname == 'getCoverArt']
    expect(got == ['al-a0'] * 5 and bg_stage(m)[1] == 3 and len(slept) == 10 + 20 + 40 + 60 and call(m, 'sba_bg_progress', 0, 0) == 0,
           f'every request without an answer: the same cover five times (SBA_BG_FAILS), never skipped, the stage stays covers, then the run ends ({got}, {bg_stage(m)})')
    state_['down'] = False
    n = len(site.urls)
    r, th = ask(m, 'sba_bg_kick')
    drain(m, th)
    got = [site.query(i)['id'] for i in range(n, len(site.urls)) if site.views()[i] == 'getCoverArt']
    expect(got[:2] == ['al-a0', 'al-a1'] and bg_stage(m)[1] == 5, f'the next kick resumes at the first cover and finishes ({got})')
    # a library whose artists all have their files or no id: the stage ends at once, no progress line of its own
    site, ids = art_lib()
    m = bg_machine(site)
    seen = []
    art_route(site, m, seen)
    for i in (0, 1, 2, 3, 5): m.put(f'{COVERS}/{fnv(f"ar-r{i}"):08x}-168.jpg', JPEG)
    bg_run(m)
    expect(not [s for s in seen if s[0].startswith('ar-')] and bg_stage(m)[1] == 5 and call(m, 'sba_bg_progress', 0, 0) == 0, 'nothing missing: no request and the fill is done')

    # an album whose songs are not all in the list is left to getAlbum; a stale count does not derive a short file
    site, songs, ids = bg_lib((4, 4))
    site.routes['getAlbumList2'] = {'body': ok_json(albumList2={'album': [dict(id='a0', name='A', songCount=4, coverArt='al-a0'), dict(id='a1', name='B', songCount=9, coverArt='al-a1')]})}
    m = bg_machine(site)
    bg_run(m)
    expect(f'{ND}/al/a0.idx' in m.fs and f'{ND}/al/a1.idx' not in m.fs and not [p for p in m.fs if p.endswith('.tmp')], 'a0 is derived (4 of 4); a1 (9 stated, 4 listed) is not and leaves no file')

    # two covers that fail for good, side by side: a skip is progress, so the run does not end at the second and the ones after them are fetched
    site, ids = art_lib()
    m = bg_machine(site)
    art_route(site, m)
    good = site.routes['getCoverArt']
    site.routes['getCoverArt'] = lambda url, o: {'rc': 22, 'code': 500} if parse_qs(urlparse(url).query)['id'][0] in ('ar-r1', 'ar-r2') else good(url, o)
    m.on_sleep = lambda k: None
    bg_run(m)
    got = [site.query(i)['id'] for i, vname in enumerate(site.views()) if vname == 'getCoverArt']
    expect(got.count('ar-r1') == 3 and got.count('ar-r2') == 3 and got[-2:] == ['ar-r3', 'ar-r5'] and call(m, 'sba_cover_have', 'ar-r3') == -1 and call(m, 'sba_cover_have', 'ar-r5') == 1 and bg_stage(m)[1] == 4,
           f'two adjacent failing pictures use their three tries each, the run goes on to the ones after them, the stage stays for the next run ({got}, {bg_stage(m)})')
    # a 200 whose body is no picture (a Subsonic error in JSON): the marker, no retry, no pause
    site, ids = art_lib()
    m = bg_machine(site)
    art_route(site, m)
    good = site.routes['getCoverArt']
    site.routes['getCoverArt'] = lambda url, o: {'body': err_json(70)} if parse_qs(urlparse(url).query)['id'][0] == 'ar-r1' else good(url, o)
    bg_run(m)
    got = [site.query(i)['id'] for i, vname in enumerate(site.views()) if vname == 'getCoverArt']
    expect(got.count('ar-r1') == 1 and got[-3:] == ['ar-r2', 'ar-r3', 'ar-r5'] and call(m, 'sba_cover_have', 'ar-r1') == -1 and sleeps_of(m) == 0 and bg_stage(m)[1] == 5,
           f'an answer that is no picture leaves the empty marker at once and the fill goes on, done ({got}, {bg_stage(m)})')

    # a first page that is empty for a library that has songs is a failure: no songs.idx (it would say "complete" for a week); the next kick starts again
    site, songs, ids = bg_lib()
    inner = site.routes['search3']
    state_ = {'empty': True}
    site.routes['search3'] = lambda url, o: {'body': ok_json(searchResult3={'song': []})} if state_['empty'] else inner(url, o)
    m = bg_machine(site)
    m.on_sleep = lambda k: None
    bg_run(m)
    expect(f'{ND}/songs.idx' not in m.fs and site.views()[4:] == ['search3'] * 5 and bg_stage(m)[1] == 1, f'an empty first page is five failed tries, never a finished empty list ({site.views()[4:]}, {bg_stage(m)})')
    state_['empty'] = False
    r, th = ask(m, 'sba_bg_kick')
    drain(m, th)
    expect(len(read_rows(m, f'{ND}/songs.idx', 'track')) == 230, 'the next kick fills it')
    # a short page in the middle (the server\'s own limit) is not the end: paging goes on by offset to the sync\'s total
    site, songs, ids = bg_lib()
    inner = site.routes['search3']
    site.routes['search3'] = lambda url, o: {'body': ok_json(searchResult3={'song': songs[100:160]})} if parse_qs(urlparse(url).query)['songOffset'][0] == '100' else inner(url, o)
    m = bg_machine(site)
    bg_run(m)
    offs = [site.query(i)['songOffset'] for i, vname in enumerate(site.views()) if vname == 'search3']
    expect(offs == ['0', '100', '160'] and len(read_rows(m, f'{ND}/songs.idx', 'track')) == 230, f'a short page before the total goes on from the rows held ({offs})')
    # a songs.part with a half row at its end resumes from the whole rows
    site, songs, ids = bg_lib()
    ok_search = site.routes['search3']
    state_ = {'bad': True}
    site.routes['search3'] = lambda url, o: {'rc': 7} if int(parse_qs(urlparse(url).query)['songOffset'][0]) >= 100 and state_['bad'] else ok_search(url, o)
    m = bg_machine(site)
    m.on_sleep = lambda k: None
    bg_run(m)
    m.fs[f'{ND}/songs.part'] += bytes(50)
    state_['bad'] = False
    n = len(site.urls)
    r, th = ask(m, 'sba_bg_kick')
    drain(m, th)
    offs = [site.query(i)['songOffset'] for i in range(n, len(site.urls)) if site.views()[i] == 'search3']
    expect(offs == ['100', '200'] and [r[0] for r in read_rows(m, f'{ND}/songs.idx', 'track')] == [s['id'] for s in songs] and f'{ND}/songs.cut' not in m.fs,
           f'a torn last row is cut away and the fill resumes at 100, not at 0 ({offs})')

    # a star taken while the pages come in is applied to the list that replaces songs.idx
    site, songs, ids = bg_lib()
    holder = {}
    page_inner = site.routes['search3']
    fired = []

    def star_during(url, o):
        if int(parse_qs(urlparse(url).query)['songOffset'][0]) == 100 and not fired:
            fired.append(1)
            mm = holder['m']
            t = mm.alloc(struct.calcsize(TRACK))
            mm.u.mem_write(t, row('track', id='a0-t0', title='a0 T0', album_id='a0'))
            holder['star'] = mm.nested(PSYMS['sba_star'], t, 1)
        return page_inner(url, o)
    site.routes['search3'] = star_during
    site.routes['star'] = {'body': ok_json()}
    m = bg_machine(site)
    holder['m'] = m
    bg_run(m)
    rows = read_rows(m, f'{ND}/songs.idx', 'track')
    flags = {r[0]: r[-1] for r in rows}
    expect(holder.get('star') == 0 and flags['a0-t0'] == 1 and sum(flags.values()) == 1 and 'star' in site.views(), 'the star is in the replaced songs.idx (and in the album file derived after it), sent to the server')
    expect([r[-1] for r in read_rows(m, f'{ND}/al/a0.idx', 'track') if r[0] == 'a0-t0'] == [1], 'and in the derived album file')

    # a reboot in the middle of the derive: the new run reads bg.txt, asks the server for nothing and derives from the album it stopped at
    site, songs, ids = bg_lib()
    m = bg_machine(site)
    bg_run(m)
    sig, _, _, when = bg_stage(m)
    m.fs.pop(f'{ND}/al/a1.idx'), m.fs.pop(f'{ND}/al/a2.idx')
    m.fs[f'{ND}/al/a0.idx'] = b'stale'
    m.put(f'{ND}/bg.txt', f'{sig} 2 1 {when}\n'.encode())
    n = len(site.urls)
    r, th = ask(m, 'sba_bg_kick')
    expect(th is not None, 'the kick finds a derive half done')
    drain(m, th)
    expect(len(site.urls) == n and f'{ND}/al/a1.idx' in m.fs and f'{ND}/al/a2.idx' in m.fs and m.fs[f'{ND}/al/a0.idx'] == b'stale' and bg_stage(m)[1] == 5,
           'nothing was asked of the server; the albums from the cursor on were derived again, the ones before it left as they were; then the covers (all there) and done')

    # an artist\'s albums before getArtist has answered: the sync's albums that name the artist
    site, songs, ids = bg_lib()
    m = bg_machine(site)
    bg_run(m)
    out = m.alloc(8)
    n = call(m, 'sba_artist_albums', 'ar1', out)
    expect(n == 3 and m.word(out) == 3 and [m.read_cstr(m.word(out + 4) + i * struct.calcsize(ALBUM)) for i in range(3)] == ['a0', 'a1', 'a2'], 'no ar/<id>.idx yet: the albums of albums.idx with that artist id')
    expect(call(m, 'sba_artist_albums', 'nobody', out) == 0, 'another artist: none')
    m.put(f'{ND}/ar/ar1.idx', cache_file('album', [row('album', id='only')]))
    n = call(m, 'sba_artist_albums', 'ar1', out)
    expect(n == 1 and m.read_cstr(m.word(out + 4)) == 'only', 'once the file is there it is the answer')


def big(ctx):
    """A response bigger than the old 512 KiB buffer: the sink grows by doubling (64 KiB first) up to SBN_RESPONSE_MAX (4 MiB), a larger one fails cleanly, and the buffer is given back after the request."""
    expect = ctx.expect
    CAP = 4 << 20
    pad = 'x' * 160

    def entries(n, pad=pad): return [{'id': f't{i}', 'title': f'Song {i}', 'artist': 'Artist', 'album': 'Album', 'albumId': 'al1', 'coverArt': f'cv-{i}', 'suffix': 'flac', 'track': i % 20 + 1, 'comment': pad} for i in range(n)]
    pl = ok_json(playlist={'id': 'p1', 'entry': entries(3000)})
    expect(512 * 1024 < len(pl) < CAP, f'the fixture playlist is over the old limit and under the new ({len(pl)} bytes)')
    site = Site(getPlaylist={'body': pl, 'chunk': 65536})
    m = machine(site=site)
    run_one(m, 'sba_fetch_playlist', 'p1')
    calls = list(m.calls)   # (every later call clears the log)
    rows = read_rows(m, f'{ND}/pl/p1.idx', 'track')
    expect(state(m, K['PLAYLIST'], 'p1') == (ST['OK'], 0) and rows and len(rows) == 3000 and rows[0][0] == 't0' and rows[2999][0] == 't2999', f'a 3000-track getPlaylist opens whole ({len(rows or [])} rows)')
    sizes = [c[1] for c in calls if c[0] == 'calloc' and c[1] >= 64 * 1024 and c[1] & (c[1] - 1) == 0]
    expect(sizes[:4] == [1 << 16, 1 << 17, 1 << 18, 1 << 19] and sizes[-1] >= 1 << 20, f'the body buffer started at 64 KiB and doubled ({sizes[:6]})')
    frees = [c for c in calls if c[0] == 'free']
    expect(frees and any(c[1] != 0 for c in frees), 'and the grown buffer was freed after the request')
    # the same list is the album page's: SBA_ALBUM_TRACKS rows are kept
    site = Site(getAlbum={'body': ok_json(album={'id': 'al1', 'name': 'A', 'song': entries(3200)}), 'chunk': 65536})
    m = machine(site=site)
    run_one(m, 'sba_fetch_album', 'al1')
    expect(len(read_rows(m, f'{ND}/al/al1.idx', 'track') or []) == 3000, 'an album or playlist keeps at most 3000 tracks')
    # a response over the cap fails the transfer and keeps nothing
    over = ok_json(playlist={'id': 'p1', 'entry': []}) + b' ' * (CAP + 1)
    exact = bytearray(ok_json(playlist={'id': 'p1', 'entry': []})); exact += b' ' * (CAP - 1 - len(exact))
    site = Site(getPlaylist={'body': over, 'chunk': 65536})
    m = machine(site=site)
    run_one(m, 'sba_fetch_playlist', 'p1')
    expect(state(m, K['PLAYLIST'], 'p1')[0] == ST['FAIL'] and f'{ND}/pl/p1.idx' not in m.fs, 'a response over 4 MiB fails the request and writes no file')
    site.routes['getPlaylist'] = {'body': bytes(exact), 'chunk': 65536}
    run_one(m, 'sba_fetch_playlist', 'p1')
    expect(state(m, K['PLAYLIST'], 'p1') == (ST['OK'], 0), 'a response of 4 MiB less one byte (the buffer is full with its NUL) is read')
    m.calloc_fail_size = CAP
    site.routes['getPlaylist'] = {'body': ok_json(playlist={'id': 'p1', 'entry': entries(10)}) + b' ' * (3 << 20), 'chunk': 65536}
    run_one(m, 'sba_fetch_playlist', 'p1')
    expect(state(m, K['PLAYLIST'], 'p1')[0] == ST['FAIL'] and busy(m) == 0, 'no memory for the next doubling: the request fails cleanly')
    m.calloc_fail_size = 0
    # getStarred2 with 1500 favourite songs (the sync's last step)
    star = ok_json(starred2={'song': entries(1500, 'x' * 400), 'album': [{'id': 'a3', 'name': 'Album 3'}]})
    expect(len(star) > 512 * 1024, f'the favourites fixture is over the old limit ({len(star)} bytes)')
    site = Site(getAlbumList2={'body': ok_json(albumList2={'album': []})}, getArtists={'body': ok_json(artists={'index': []})}, getPlaylists={'body': ok_json(playlists={'playlist': []})},
                getStarred2={'body': star, 'chunk': 65536}, search3={'body': songs_json([])})
    m = machine(site=site)
    m.wall = 1800000000
    run_one(m, 'sba_sync')
    rows = read_rows(m, f'{ND}/starred.idx', 'track')
    expect(state(m, K['SYNC']) == (ST['OK'], 0) and rows and len(rows) == 1500 and rows[1499][0] == 't1499', f'a sync with 1500 favourites keeps them all ({len(rows or [])})')
    out = m.alloc(8)
    expect(call(m, 'sba_starred_tracks', out) == 1500, 'and the Favorites list reads them all')


def relogin(m):
    for fn, v in (('sba_conf_url_set', URL), ('sba_conf_user_set', 'alice'), ('sba_conf_password_set', PASSWORD)):
        assert call(m, fn, v) == 0


def hearts(ctx):
    """starred.idx is the truth for every heart on the page side; the stat record keeps the entries in use; a cancelled star is not put back."""
    expect = ctx.expect
    site = Site(star={'body': ok_json()}, unstar={'body': ok_json()})
    m = machine(site=site)
    size = struct.calcsize(TRACK)
    files = [dict(id='t0', title='A', album_id='al1', track=1, starred=0), dict(id='t1', title='B', album_id='al1', track=2, starred=1),
             dict(id='t2', title='C', album_id='al1', track=3, starred=0), dict(id='t3', title='D', album_id='al1', track=4, starred=1)]
    seed(m, f'{ND}/songs.idx', 'track', files)
    seed(m, f'{ND}/al/al1.idx', 'track', files)
    out = m.alloc(8)

    def flags(fn='sba_album_tracks', *args):
        n = call(m, fn, *args, out) if fn == 'sba_album_tracks' else call(m, fn, out)
        r = [struct.unpack(TRACK, bytes(m.u.mem_read(m.word(out + 4) + i * size, size)))[-1] for i in range(max(n, 0))]
        call(m, 'sba_free_tracks', out)
        return r

    def window():
        buf = m.alloc(4 * size)
        n = call(m, 'sba_songs_window', 0, 4, buf)
        return [struct.unpack(TRACK, bytes(m.u.mem_read(buf + i * size, size)))[-1] for i in range(n)]
    expect(flags('sba_album_tracks', 'al1') == [0, 1, 0, 1] and window() == [0, 1, 0, 1], 'no starred.idx (no sync yet): the files\' own flags stand, in an album and in the Songs window')
    m.put(f'{ND}/starred.idx', cache_file('track', [row('track', id='t0', starred=1), row('track', id='t2', starred=1)]))
    expect(flags('sba_album_tracks', 'al1') == [0, 1, 0, 1], 'a starred.idx the worker did not commit (no counter move) is not read again: the set is the one of before')
    # the set is read when first needed after a counter move: a sync's starred list does it (the file put above was not committed by the worker)
    m.curl_site = Site(getAlbumList2={'body': ok_json(albumList2={'album': [{'id': 'a0', 'name': 'A', 'songCount': 1}]})}, getArtists={'body': ok_json(artists={})},
                       getPlaylists={'body': ok_json(playlists={})}, getStarred2={'body': ok_json(starred2={'song': [{'id': 't0', 'title': 'A', 'starred': '2024-05-01T10:00:00Z'}, {'id': 't2', 'title': 'C', 'starred': '2024-05-01T10:00:00Z'}]})},
                       search3={'body': songs_json([])}, getCoverArt={'body': JPEG})
    m.wall = 1800000000
    run_one(m, 'sba_sync')
    seed(m, f'{ND}/songs.idx', 'track', files)
    seed(m, f'{ND}/al/al1.idx', 'track', files)
    expect(flags('sba_album_tracks', 'al1') == [1, 0, 1, 0] and window() == [1, 0, 1, 0],
           'the sync replaced starred.idx: a row whose file flag is 0 but whose id is in it reads starred, one whose flag is 1 but is not in it reads 0, in an album and in the Songs window')
    expect(flags('sba_starred_tracks') == [1, 1], 'the starred.idx rows themselves stay starred')
    call(m, 'sba_conf_clear')   # Sign Out: the cache goes and the set with it
    relogin(m)
    seed(m, f'{ND}/songs.idx', 'track', files)
    seed(m, f'{ND}/al/al1.idx', 'track', files)
    expect(flags('sba_album_tracks', 'al1') == [0, 1, 0, 1], 'after a cache clear, with no starred.idx, the files\' flags stand again (the old set is dropped)')
    m.curl_site = Site(getAlbumList2={'body': ok_json(albumList2={'album': [{'id': 'a0', 'name': 'A', 'songCount': 1}]})}, getArtists={'body': ok_json(artists={})},
                       getPlaylists={'body': ok_json(playlists={})}, getStarred2={'body': ok_json(starred2={'song': [{'id': 't3', 'title': 'D', 'starred': '2024-05-01T10:00:00Z'}, {'id': 't2', 'title': 'C', 'starred': '2024-05-01T10:00:00Z'}]})},
                       search3={'body': songs_json([])}, getCoverArt={'body': JPEG})
    m.wall = 1800000000
    run_one(m, 'sba_sync')
    seed(m, f'{ND}/songs.idx', 'track', files)
    seed(m, f'{ND}/al/al1.idx', 'track', files)
    expect(flags('sba_album_tracks', 'al1') == [0, 0, 1, 1], 'and the next sync\'s starred.idx (t2, t3) is read')
    m.curl_site = site
    # the overlay is on top: a star the worker has not finished, then the worker replacing starred.idx (a reload)
    t = m.alloc(size)
    m.u.mem_write(t, row('track', id='t1', title='B', album_id='al1', track=2))
    r, th = ask(m, 'sba_star', t, 1)
    expect(r == 0 and flags('sba_album_tracks', 'al1') == [0, 1, 1, 1], 'a star in flight (overlay) wins over a starred.idx that does not have the track')
    u = m.alloc(size)
    m.u.mem_write(u, row('track', id='t3', title='D', album_id='al1', track=4))
    r2, th2 = ask(m, 'sba_star', u, 0)
    expect(r2 == 0 and th2 is None and flags('sba_album_tracks', 'al1') == [0, 1, 1, 0], 'and an unstar in flight wins over a starred.idx that has it')
    drain(m, th)
    expect(flags('sba_album_tracks', 'al1') == [0, 1, 1, 0] and window() == [0, 1, 1, 0]
           and sorted(x[0] for x in read_rows(m, f'{ND}/starred.idx', 'track')) == ['t1', 't2'], 'the worker committed both: starred.idx has t1 and t2 and the set was read again')
    # the status record: the sync, the Songs pager and the search keep their entry through 60 other requests; an ordinary entry is replaced in its turn
    m = machine(site=Site(search3={'body': songs_json(['s0'])}))
    m.wall = 1800000000
    run_one(m, 'sba_sync')
    run_one(m, 'sba_fetch_songs', 0)
    run_one(m, 'sba_search', 'x')
    run_one(m, 'sba_fetch_album', 'first')
    want = [state(m, K['SYNC']), state(m, K['SONGS']), state(m, K['SEARCH']), state(m, K['ALBUM'], 'first')]
    expect(all(w[0] != ST['NONE'] for w in want), f'four finished requests have their status ({want})')
    for i in range(60):
        run_one(m, 'sba_fetch_album', f'other{i}')
    expect([state(m, K['SYNC']), state(m, K['SONGS']), state(m, K['SEARCH'])] == want[:3] and state(m, K['ALBUM'], 'first')[0] == ST['NONE'] and state(m, K['ALBUM'], 'other59')[0] != ST['NONE'],
           'after 60 other requests the sync, the Songs pager and the search still have their result; an ordinary entry was replaced')
    # a star cancelled while it runs (Sign Out): the unstar is not put back, so no starred.idx of the old server is made; the overlay is released
    m = machine()
    seed(m, f'{ND}/songs.idx', 'track', [dict(id='t1', title='One', starred=1)])
    m.put(f'{ND}/starred.idx', cache_file('track', [row('track', id='t1', title='One', starred=1)]))
    t = m.alloc(size)
    m.u.mem_write(t, row('track', id='t1', title='One'))

    def during(url, opts):
        if not hasattr(during, 'done'):
            during.done = True
            m.setword(PSYMS['sba'] + CANCEL_OFF, m.word(PSYMS['sba'] + CANCEL_OFF) + 1)
        return {'body': ok_json(), 'xfer': lambda u, sent, total: None}
    m.curl_site = during
    r, th = ask(m, 'sba_star', t, 0)
    drain(m, th)
    expect(read_rows(m, f'{ND}/starred.idx', 'track') == [] and call(m, 'sba_star_pending', 't1') == -1 and state(m, K['STAR'], 't1')[0] == ST['NONE'] and busy(m) == 0
           ,
           'an unstar cancelled during its request is not reverted (starred.idx stays without the track), the overlay is released and the status cleared')


SECTIONS = [conf, guard, cache, trial, worker, sync, songs, star, hearts, cover, play, urls, bg, big]


def run(ctx):
    for section in SECTIONS:
        section(ctx)
