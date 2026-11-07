"""Cover Flow opens on the playing album; the album order (the Albums "..." card's albums-sort file): the Artist order, the stock
Title order, the file, the one-off move of the retired album-order setting into it, the same order on the Albums page, and the stock row behind every album that is opened.
(The Settings > Cover Flow page itself is tested in test/pod/menu.py, the localisation in test/pod/i18n.py.)"""
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)

ALBUMS_FILE = '/mnt/data/m1plus/albums-view'
LAST = '/mnt/mmc/.m1plus/coverflow-position'
SEED = O['FNV_SEED']


# (album, artist) in the order the stock Albums query lists them: by album title, ASCII case aside; the "Unknown
# Album" row (id -1) last. It covers: the The-prefix in either case, "The" without a space, "A" which is not ignored,
# an empty artist, the same artist and title once "The " is dropped (a tie), and the Unknown Album row.
LIB = [('A Night at the Opera', 'Queen'), ('Abbey Road', 'The Beatles'), ('Blue', 'Joni Mitchell'),
       ('Greatest Hits', 'Queen'), ('Help!', 'the beatles'), ('Kind of Blue', 'Miles Davis'),
       ('Let It Be', 'The Beatles'), ('Nevermind', 'Nirvana'), ('Pet Sounds', 'The Beach Boys'),
       ('The Wall', 'Pink Floyd'), ('Theory', 'Theo'), ('Wall', 'Pink Floyd'), ('Zeit', ''), ('Unknown Album', '')]
LIB_ARTIST_ORDER = [12, 8, 1, 4, 6, 2, 5, 7, 9, 11, 0, 3, 10, 13]    # by hand: '' < beach boys < beatles (Abbey Road, Help!, Let It Be) < ...
# ... < queen (A Night at the Opera, Greatest Hits) < theo; The Wall and Wall tie and keep the stock order; Unknown Album last


def model(specs):
    """Artist order, independently: Unknown Album last, then the artist and the title by the library name order (name_sort_key), then the stock position."""
    return sorted(range(len(specs)), key=lambda i: (specs[i][0] == 'Unknown Album', name_sort_key(specs[i][1]), name_sort_key(specs[i][0]), i))


def lib_machine(specs=LIB, sort=None, data=None):
    """Cover Flow's machine with these albums in the library list, all cached. sort None: the setting file missing
    (the default, Artist); 'album': the file says Album; data: the file's exact content."""
    m = cover_machine(albums=0, sort='default' if sort is None else sort)
    if data is not None: m.fs[SORT_FILE] = data
    fill(m, specs)
    return m


def fill(m, specs):
    m.showlist = []
    for i, (album, artist) in enumerate(specs):
        path = f'/mnt/mmc/m/{i}/1.flac'
        m.showlist.append(m.record(album=album, artist=artist, path=path, rid=-1 if album == 'Unknown Album' else i + 1))
        cache = art_file(fnv(fnv(SEED, artist), album) or 1)
        m.present.update((path, cache)); m.files[cache] = 4096
    m.class_lists[O['CLASS_ALBUMS']] = m.showlist


def caption(m, which):
    return [c[2] for c in m.calls if c[0] == 'widget_set_text_utf8' and c[1] == m.widgets[which]][-1:]


def centred(m):
    """(shelf value, album caption, artist caption) the page opened on."""
    return shelf_value(m), caption(m, 'label_album'), caption(m, 'label_artist')


def shelf(m, n, step=1):
    """What the shelf shows, album by album: [(album, artist)], and the stock row each opens."""
    shown, rows = [], []
    for k in range(0, n, step):
        put_value(m, k)
        m.call(PSYMS['on_changed'], count=2000000)
        shown.append((caption(m, 'label_album')[0], caption(m, 'label_artist')[0]))
        m.tap(O['CF_CX'])
        rows.append([c[3] for c in m.calls if c[0] == 'navigator_to_with_context' and c[1] == 'albuminfo_page'][0])
    return shown, rows


def run(ctx):
    expect = ctx.expect
    cover_open = PSYMS['coverflow_open']
    n = len(LIB)
    assert model(LIB) == LIB_ARTIST_ORDER, (model(LIB), LIB_ARTIST_ORDER)

    # ===================== 1. the Artist order =====================
    m = lib_machine()
    m.call(cover_open, count=30000000)
    shown, rows = shelf(m, n)
    expect(rows == LIB_ARTIST_ORDER, f'Artist order (the default): the shelf lists the stock rows {rows}')
    expect(shown == [LIB[i] for i in LIB_ARTIST_ORDER], f'... and each cover shows its own album and artist ({shown[:3]})')
    expect(rows[:3] == [12, 8, 1] and [LIB[i][0] for i in rows[8:10]] == ['The Wall', 'Wall'],
           'an empty artist first; "The Beach Boys" (B-e-a-c) before "The Beatles"; The Wall and Wall tie and keep their stock order')
    expect([LIB[i][1] for i in rows[2:5]] == ['The Beatles', 'the beatles', 'The Beatles'] and [LIB[i][0] for i in rows[2:5]] == ['Abbey Road', 'Help!', 'Let It Be'],
           'the Beatles, in either case, under B and then by title')
    expect(LIB[rows[-1]][0] == 'Unknown Album' and LIB[rows[-2]][1] == 'Theo', '"Theo" is not "The ": it sorts under T; the Unknown Album row stays last')
    expect([LIB[i][0] for i in rows if LIB[i][1] == 'Queen'] == ['A Night at the Opera', 'Greatest Hits'], '"A" is not ignored (only "The "): by title within an artist')
    expect(model(LIB) == rows, 'and it is the independent model\'s order')
    # every cover is still its own album: the cache key of a shelf position is the album's, not the stock row's
    m2 = lib_machine(); m2.call(cover_open, count=30000000)
    put_value(m2, 0); m2.call(PSYMS['on_changed'], count=2000000)
    first = LIB[12]
    expect(shelf_value(m2) == 0 and caption(m2, 'label_album') == [first[0]], 'the first cover is the first in the new order')
    key0 = fnv(fnv(SEED, first[1]), first[0]) or 1
    expect(f'file://{art_file(key0)}' in m2.loads, f'its texture is its own cache file ({m2.loads[:2]})')
    # a tap on the centre cover opens the STOCK row: the album page reads it from the stock list, which is not reordered
    m3 = lib_machine(); m3.call(cover_open, count=30000000)
    put_value(m3, 0); m3.tap(O['CF_CX'])
    expect(('navigator_to_with_context', 'albuminfo_page', O['CLASS_ALBUMS'], 12) in m3.calls
           and m3.deques[m3.opened_album[2]] == m3.showlist and m3.deques[m3.opened_album[2]][12] is m3.showlist[12],
           'the first cover (Zeit) opens stock row 12 of the unreordered stock list')

    # ===================== 2. the Album order is exactly the stock one =====================
    for data in (b'0\n', b'0'):
        m = lib_machine(data=data)
        m.call(cover_open, count=30000000)
        shown, rows = shelf(m, n)
        expect(rows == list(range(n)) and shown == LIB, f'saved {data!r}: Album order is the stock order, row for row')

    # ===================== 2b. reversed orders: the letter a (Title) / b (Artist) in albums-sort =====================
    last = [n - 1]    # the Unknown Album row stays last
    rev_title = list(range(n - 2, -1, -1)) + last
    rev_artist = sorted(range(n - 1), key=lambda i: (name_sort_key(LIB[i][1]), name_sort_key(LIB[i][0])), reverse=True) + last   # (ties keep the stock order: sorted is stable)
    for data, want, what in ((b'a\n', rev_title, 'Z-A by title'), (b'a', rev_title, 'Z-A by title, no newline'), (b'b\n', rev_artist, 'Z-A by artist')):
        m = lib_machine(data=data)
        m.call(cover_open, count=30000000)
        shown, rows = shelf(m, n)
        expect(rows == want, f'saved {data!r} ({what}): the shelf is the reverse of the saved order, Unknown Album last ({rows})')
    expect(rev_artist[0] == 10, 'the model\'s Z-A artist order starts with Theo')
    m = lib_machine(data=b'b\n'); m.call(cover_open, count=30000000)
    put_value(m, 0); m.call(PSYMS['on_changed'], count=2000000)
    expect(caption(m, 'label_artist') == [LIB[rev_artist[0]][1]] and f'file://{art_file(fnv(fnv(SEED, LIB[rev_artist[0]][1]), LIB[rev_artist[0]][0]) or 1)}' in m.loads,
           'the first reversed cover is its own album and its own cache file (keys by stock row)')

    # ===================== 3. the setting file: strict, anything invalid is Artist =====================
    small = [('Alpha', 'Zed'), ('Beta', 'Amy'), ('Gamma', 'Mel')]
    for data, artist in ((None, True), (b'1\n', True), (b'1', True), (b'', True), (b'x\n', True), (b'00', True), (b'0x', True),
                         (b'0\n\n', True), (b' 0\n', True), (b'\x00\n', True), (b'\xff\xff', True),
                         (b'0\n', False), (b'0', False)):
        m = lib_machine(small, data=data) if data is not None else lib_machine(small)
        m.call(cover_open, count=10000000)
        shown, rows = shelf(m, 3)
        expect(rows == ([1, 2, 0] if artist else [0, 1, 2]), f'saved {data!r}: {"Artist" if artist else "Album"} order ({rows})')
    m = lib_machine(small); m.call(cover_open, count=10000000)
    expect(SORT_FILE not in m.fs and SORT_TMP not in m.fs and not any(c[0] in ('write', 'rename') for c in m.calls),
           'reading the setting never writes it (a default or an invalid file is left as it is)')
    expect(len([c for c in m.calls if c[0] == 'open' and c[1] == SORT_FILE]) == 1, 'the file is read once, when the page opens')
    expect(not any(c[0] == 'unlink' for c in m.calls), 'with no retired album-order file nothing is unlinked')

    # The retired Settings > Library > Album Order file moves into albums-sort once (Title for "0", else Artist) and is deleted; albums-sort wins when it is there.
    for old, now, want_file, want_rows in ((b'0\n', None, b'0\n', [0, 1, 2]), (b'0', None, b'0\n', [0, 1, 2]), (b'1\n', None, b'1\n', [1, 2, 0]),
                                           (b'x', None, b'1\n', [1, 2, 0]), (b'', None, b'1\n', [1, 2, 0]),
                                           (b'0\n', b'1\n', b'1\n', [1, 2, 0]), (b'1\n', b'0\n', b'0\n', [0, 1, 2]), (b'0\n', b'junk', b'junk', [1, 2, 0])):
        m = lib_machine(small)
        m.fs[OLD_ORDER_FILE] = old; m.fs[OLD_ORDER_TMP] = b'0\n'
        if now is not None: m.fs[SORT_FILE] = now
        m.call(cover_open, count=10000000)
        atomic, written = ('rename', SORT_TMP, SORT_FILE) in m.calls, any(c[0] in ('write', 'rename') for c in m.calls)
        shown, rows = shelf(m, 3)
        expect(m.fs.get(SORT_FILE) == want_file and OLD_ORDER_FILE not in m.fs and OLD_ORDER_TMP not in m.fs and rows == want_rows,
               f'album-order {old!r}, albums-sort {now!r}: albums-sort {want_file!r}, both old files gone, rows {rows}')
        if now is None: expect(SORT_TMP not in m.fs and atomic, 'the move is written atomically')
        else: expect(not written, 'an albums-sort that is there is not written')
    m = lib_machine(small); m.fs[OLD_ORDER_FILE] = b'0\n'; m.fail.add(('write', SORT_TMP))
    m.call(cover_open, count=10000000)
    shown, rows = shelf(m, 3)
    expect(SORT_FILE not in m.fs and OLD_ORDER_FILE not in m.fs and rows == [1, 2, 0], 'a failed write: no albums-sort, the old file still goes, the order is the default Artist')
    m = lib_machine(small); m.fs[OLD_ORDER_FILE] = b'0\n'; m.call(cover_open, count=10000000); m.calls.clear()
    m.call(cover_open, count=10000000)
    expect(not any(c[0] in ('unlink', 'write', 'rename') for c in m.calls) and m.fs.get(SORT_FILE) == b'0\n', 'the move happens once')

    # ===================== 4. memory and size limits =====================
    m = lib_machine(small); m.calloc_fail = True
    m.call(cover_open, count=10000000)
    expect(('window_open', 'm1plus_cover') in m.calls and shelf_value(m) == 0 and caption(m, 'label_album') == ['Alpha'],
           'with no memory for the order the page still opens, on the stock order (the flat covers stand in)')
    m = lib_machine(small); m.call(cover_open, count=10000000); m.call(PSYMS['on_destroy'], count=2000000)
    freed = [c for c in m.calls if c[0] == 'free']
    expect(freed, 'closing the page frees what it allocated (the order included)')
    big = [(f'Album {i:04d}', f'Artist {(i * 37) % 4000:04d}') for i in range(4000)]
    m = lib_machine(big).count(); m.call(cover_open, count=200000000)
    spent = m.icount
    shown, rows = shelf(m, 4000, step=401)
    mdl = model(big)
    print(f'  sort of 4000 albums on open: {spent:,} payload instructions')
    expect(rows == mdl[::401] and spent < 120000000, f'4000 albums: sorted on open in {spent:,} payload instructions, and in the model\'s order')
    m = lib_machine(big + [('Album 4000', 'Artist')]); m.call(cover_open, count=2000000)
    expect(not any(c[0] == 'calloc' and c[1] == 4001 * 4 for c in m.calls) and m.props.get((m.widgets['label_status'], 'sensitive')) == 1,
           'a library over the limit is not sorted (nothing shows)')

    # ===================== 4b. the name comparison: digit runs, CJK by pinyin, white space, stable ties =====================
    nat = [('Vol 10', 'Mix'), ('Vol 2', 'Mix'), ('B', 'Disc 10'), ('B', 'Disc 9'), ('Z', ' Zed'), ('Y', 'zebra'), ('周杰伦', 'Jay'),
           ('Same', 'Twin'), ('Same', 'Twin'), ('_x', 'Sym'), ('7', 'Seven'), ('孙燕姿', 'Stefanie'), ('Sam', 'S'), ('The Abc', 'First')]
    nat = [(album, artist) for artist, album in nat]
    m = lib_machine(nat); m.call(cover_open, count=30000000)
    shown, rows = shelf(m, len(nat))
    expect(rows == model(nat), f'digit runs by value, CJK by pinyin initials, white space skipped, ties stable ({[nat[i] for i in rows]})')
    artists_in_order = [nat[i][1] for i in rows]
    expect(artists_in_order.index('Vol 2') < artists_in_order.index('Vol 10') and artists_in_order.index('7') < artists_in_order.index('_x') < artists_in_order.index('B'),
           'Vol 2 before Vol 10; digits before symbols before letters')
    expect(artists_in_order.index('Sam') < artists_in_order.index('孙燕姿') < artists_in_order.index('Y') < artists_in_order.index('Z') < artists_in_order.index('周杰伦'),
           'a CJK artist sits among the Latin ones by its initials (孙燕姿 "syz" after Sam; 周杰伦 "zjl" after Z)')
    twins = [i for i in rows if nat[i][1] == 'Same']
    expect(twins == sorted(twins), 'the same artist and title keep the stock order')
    m = lib_machine(nat)
    m.calloc_fail_size = 8 * len(nat) + sum(len(x.encode()) + 1 for pair in nat for x in pair if any(ord(c) > 127 for c in x))   # the keys: two pointers per album and the copies of the CJK names
    m.call(cover_open, count=30000000)
    shown, rows = shelf(m, len(nat))
    expect(rows == list(range(len(nat))), 'no memory for the keys: the page still opens, on the stock order')

    # ===================== 5. opens on the playing album =====================
    def opened(m, tracks, pos, **kw):
        if tracks is not None: m.play(tracks, pos)
        m.call(cover_open, count=30000000)
        return centred(m)
    rec = lambda m, album, artist: m.record(album=album, artist=artist, path='/mnt/mmc/p/1.flac')
    want = lambda i: (LIB_ARTIST_ORDER.index(i), [LIB[i][0]], [LIB[i][1]])
    m = lib_machine()
    expect(opened(m, [rec(m, 'Kind of Blue', 'Miles Davis')], 0) == want(5), 'the playing album (Kind of Blue) is centred: the sorted position, not the stock row')
    expect(('mclGetPlayPos',) in [(c[0],) for c in m.calls], 'the position is read from the player (mclGetPlayPos)')
    m = lib_machine(sort='album')
    expect(opened(m, [rec(m, 'Kind of Blue', 'Miles Davis')], 0) == (5, ['Kind of Blue'], ['Miles Davis']), 'and in Album order the stock row')
    m = lib_machine()
    t = [rec(m, 'Abbey Road', 'The Beatles'), rec(m, 'Zeit', ''), rec(m, 'Nevermind', 'Nirvana')]
    expect(opened(m, t, 2) == want(7), 'the playing track is the queue\'s row at the position, not the first (3 queued, on the third)')
    m = lib_machine()
    expect(opened(m, [rec(m, 'Blue', 'Joni Mitchell and guests')], 0) == want(2), 'a track whose artist is not the album row\'s artist (a compilation): matched by album name')
    m = lib_machine()
    expect(opened(m, [rec(m, 'KIND OF BLUE', 'miles davis')], 0) == want(5), 'the album name is compared ignoring ASCII case')
    m = lib_machine()
    expect(opened(m, [rec(m, 'Zeit', '')], 0) == want(12), 'an album with an empty artist')
    m = lib_machine()
    expect(opened(m, [rec(m, 'Unknown Album', '')], 0) == want(13), 'the Unknown Album row can be the playing one')
    # not found, nothing playing, errors: today's behaviour, the saved last album
    key = fnv(fnv(SEED, 'Nirvana'), 'Nevermind') or 1
    def saved(m):
        m.fs[LAST] = b'%08x\n' % key
    for what, setup in (('an album the library does not have', lambda m: m.play([rec(m, 'Not In The Library', 'Nobody')], 0)),
                        ('a track with no album tag', lambda m: m.play([rec(m, '', 'Nobody')], 0)),
                        ('nothing playing (position -1)', lambda m: m.play([rec(m, 'Kind of Blue', 'Miles Davis')], -1)),
                        ('no queue at all', lambda m: None),
                        ('a position but no queue', lambda m: setattr(m, 'play_pos', 0)),
                        ('a position past the queue', lambda m: m.play([rec(m, 'Kind of Blue', 'Miles Davis')], 1)),
                        ('a position far past the queue', lambda m: m.play([], 7)),
                        ('an empty queue', lambda m: m.play([], 0))):
        m = lib_machine(); saved(m); setup(m)
        expect(opened(m, None, 0) == want(7), f'{what}: the saved last album (Nevermind) opens as before')
        m = lib_machine(); setup(m)
        expect(opened(m, None, 0)[0] == 0, f'{what}, no saved album: the first')
    m = lib_machine(); saved(m); m.play([rec(m, 'Kind of Blue', 'Miles Davis')], 0)
    expect(opened(m, None, 0) == want(5), 'the playing album wins over the saved one')
    m = lib_machine(); m.play([rec(m, 'Kind of Blue', 'Miles Davis')], 0)
    m.call(cover_open, count=30000000); m.call(PSYMS['on_destroy'], count=2000000)
    mkey = fnv(fnv(SEED, 'Miles Davis'), 'Kind of Blue') or 1
    tmp = LAST + '.tmp'
    expect(('pthread_create',) in m.calls and any(c[0] == 'pthread_detach' for c in m.calls), 'closing queues the position write on a detached worker')
    def finish_position_worker(machine):
        thread = getattr(machine, 'thread', None)
        if thread: machine.call(thread[0], a0=thread[1], count=3000000)
    finish_position_worker(m)
    seq = [c[:2] for c in m.calls if len(c) > 1 and c[1] == tmp and c[0] in ('open', 'write', 'fsync', 'close')]
    seq += [c for c in m.calls if c[0] == 'rename' and c[1] == tmp]
    expect(seq == [('open', tmp), ('write', tmp), ('fsync', tmp), ('close', tmp), ('rename', tmp, LAST)], f'the last album is written atomically: temp, write, fsync, close, rename ({seq})')
    expect(('rename', tmp, LAST) in m.calls and tmp not in m.fs and m.fs.get(LAST) == b'%08x\n' % mkey,
           'the file holds the key as 8 lowercase hex digits and a newline, and no temp file is left')
    expect(not any(c[0] in ('fopen', 'fwrite') and 'covers/album' in str(c) for c in m.calls), 'the old file in the cover cache folder is not used')
    # a failed write leaves no temp file and no position
    for fail in (('write', tmp), ('fsync', tmp), ('rename', LAST)):
        m = lib_machine(); m.play([rec(m, 'Kind of Blue', 'Miles Davis')], 0)
        m.call(cover_open, count=30000000); m.fail.add(fail); m.call(PSYMS['on_destroy'], count=2000000); finish_position_worker(m)
        expect(tmp not in m.fs and LAST not in m.fs, f'a failed {fail[0]} leaves no temp file and no position file')
    # no card: nothing is written under the mount point, nothing is read
    m = lib_machine(); m.play([rec(m, 'Kind of Blue', 'Miles Davis')], 0); m.card_mounted = False
    m.call(cover_open, count=30000000); m.call(PSYMS['on_destroy'], count=2000000); finish_position_worker(m)
    expect(not any(c[0] in ('open', 'write', 'rename') and str(c[1]).startswith('/mnt/mmc/.m1plus/coverflow-position') for c in m.calls),
           'with no card the position is neither read nor written')
    # a malformed file is no saved album; an upper-case or newline-less key is still 8 hex digits
    for what, data in (('empty', b''), ('short', b'1234abc\n'), ('long', b'1234abcde\n'), ('junk', b'1234abcg\n'), ('zero', b'00000000\n'),
                       ('the old binary form', b'\x01\x02\x03\x04'), ('two lines', b'1234abcd\n\n'), ('a space', b' 234abcd\n')):
        m = lib_machine(); m.fs[LAST] = data
        expect(opened(m, None, 0)[0] == 0, f'a {what} position file: no saved album, the first opens')
    for what, data in (('without the newline', b'%08x' % mkey), ('upper case', b'%08X\n' % mkey)):
        m = lib_machine(); m.fs[LAST] = data
        expect(opened(m, None, 0) == want(5), f'a key {what} is read')
    # looked up once, at open: nothing in the page reads the player afterwards
    m = lib_machine(); m.play([rec(m, 'Kind of Blue', 'Miles Davis')], 0); m.call(cover_open, count=30000000)
    m.play([rec(m, 'Nevermind', 'Nirvana')], 0)
    put_value(m, 3); m.call(PSYMS['on_changed'], count=2000000); m.tap(O['CF_CX']); m.settle()
    polled = []
    for fn in ('on_changed', 'on_load', 'on_snap', 'on_poll'):
        m.call(PSYMS[fn], count=2000000); polled += [c for c in m.calls if c[0] == 'mclGetPlayPos']
    paint(m); polled += [c for c in m.calls if c[0] == 'mclGetPlayPos']
    expect(not polled, 'the page never polls the player after it opened (the shelf stays where the user put it)')
    # the playing album is also found when the cache is being built (the preparing screen, then the covers)
    m = cover_machine(albums=0, sort='default', cached=False); fill(m, LIB)
    for c in list(m.present):
        if c.startswith('/mnt/mmc/.m1plus/covers/'): m.present.discard(c)
    m.play([rec(m, 'Kind of Blue', 'Miles Davis')], 0)
    m.call(cover_open, count=30000000)
    expect(('pthread_create',) in m.calls, 'a library with no cache starts the build')
    m.call(PSYMS['on_cancel'], count=5000000)
    expect(centred(m) == want(5), 'the build\'s screen does not lose the playing album: the covers open on it')

    # ===================== 6. the artist's Cover Flow =====================
    def artist_page(artist_index, tracks=None, pos=0):
        m = artists_machine()
        m.fs.pop(SORT_FILE, None)       # the setting at its default, Artist: the artist's shelf must still keep its own order
        m.call(PSYMS['artists_open'], count=5000000)
        if tracks: m.play(tracks(m), pos)
        artists_tap(m, artist_index)
        return m
    m = artist_page(0)
    shown, rows = shelf(m, 3)
    expect([s[0] for s in shown] == ['Kind of Blue', 'Jazz Hits', 'Bitches Brew'] and rows == [0, 1, 2],
           'the artist\'s shelf keeps the stock order of its albums (by title as the artist query groups them, not re-sorted by artist)')
    m = artist_page(0, lambda m: [m.record(album='Bitches Brew', artist='Miles Davis', path='/mnt/mmc/p/1.flac')])
    expect(centred(m) == (2, ['Bitches Brew'], ['Miles Davis']), 'the playing album belongs to the artist: the artist page opens on it')
    m = artist_page(0, lambda m: [m.record(album='Jazz Hits', artist='Various Artists', path='/mnt/mmc/p/1.flac')])
    expect(centred(m)[0] == 1, 'a track of the artist\'s album filed under another artist in the library (a compilation): found by album name')
    m = artist_page(0, lambda m: [m.record(album='Pastel Blues', artist='Nina Simone', path='/mnt/mmc/p/1.flac')])
    expect(centred(m) == (0, ['Kind of Blue'], ['Miles Davis']), 'the playing album is another artist\'s: the artist page opens on its first album')
    m = artist_page(0, lambda m: [m.record(album='Bitches Brew', artist='Miles Davis', path='/mnt/mmc/p/1.flac')], pos=-1)
    expect(centred(m)[0] == 0, 'nothing playing: the first album')
    m = artist_page(1, lambda m: [m.record(album='Bitches Brew', artist='Miles Davis', path='/mnt/mmc/p/1.flac')])
    expect(centred(m) == (0, ['Pastel Blues'], ['Nina Simone']), 'an artist with one album and another artist playing: that album')
    m = artist_page(0, lambda m: [m.record(album='Bitches Brew', artist='Miles Davis', path='/mnt/mmc/p/1.flac')])
    m.call(PSYMS['on_destroy'], count=2000000)
    expect('fwrite' not in m.names(), 'and the artist page still writes no last album')

    # ===================== 7. the Albums page has the same order =====================
    albums = sibling('albums')

    def albums_page(specs, data=None, sort='artist'):
        m = albums.albums_machine(0, sort=sort)
        m.fs[ALBUMS_FILE] = b'0\n'      # list mode: a row per album, the title in label_row_title
        if data is not None: m.fs[SORT_FILE] = data
        fill(m, specs)
        albums.open_grid(m)
        return m

    def listed(m):
        albums.settle(m)
        rows = sorted(zip(m.texts, m.text_styles), key=lambda t: t[0][1][1])
        return [t[0][0] for t in rows if t[1] == 'label_row_title'], [t[0][0] for t in rows if t[1] == 'label_row_sub']

    def tap_row(m, r):
        y = albums.SCREEN_Y0 + albums.TOP + r * albums.ROW + 20
        m.touch('down', 40, y, 1000, fn='al_on_down'); down = list(m.calls)
        m.touch('up', 40, y, 1080, fn='al_on_up'); m.calls = down + m.calls
        return [c[3] for c in m.calls if c[0] == 'navigator_to_with_context' and c[1] == 'albuminfo_page']

    m = albums_page(LIB)
    titles, artists = listed(m)
    top = LIB_ARTIST_ORDER[:len(titles)]
    expect(len(titles) >= 6 and titles == [LIB[i][0] for i in top] and artists == [LIB[i][1] for i in top if LIB[i][1]],
           f'Albums (list): the rows are in the Artist order, each with its artist ({titles})')
    got = [tap_row(m, r) for r in range(6)]
    expect(got == [[LIB_ARTIST_ORDER[r]] for r in range(6)], f'a tap on a row opens the stock album row behind it ({got})')
    expect(m.deques[m.opened_album[2]] == m.showlist, 'and the album page reads the unreordered stock list')
    m = albums_page(LIB, data=b'0\n')
    titles, _ = listed(m)
    expect(titles == [a for a, _ in LIB][:len(titles)] and [tap_row(m, r) for r in range(6)] == [[r] for r in range(6)], 'Album order: the stock rows, as before')
    m = albums_page(LIB, data=b'junk')
    expect(listed(m)[0][:3] == [LIB[12][0], LIB[8][0], LIB[1][0]], 'a corrupt file: Artist')
    # grid mode: the same order, two to a row
    m = albums.albums_machine(0, sort='artist'); fill(m, LIB); albums.open_grid(m)
    albums.settle(m)
    cells = sorted((t[0][1][1], t[0][1][0], t[0][0]) for t in zip(m.texts, m.text_styles) if t[1] == 'label_grid_title')
    expect([c[2] for c in cells][:4] == [LIB[i][0] for i in LIB_ARTIST_ORDER[:4]],
           f'Albums (grid): the same order, two to a row ({[c[2] for c in cells][:4]})')
    # an empty library, and the page's memory
    m = albums.albums_machine(0, sort='artist'); albums.open_grid(m)
    expect(('window_open', 'm1plus_albums') in m.calls and ('widget_set_tr_text', m.widgets['label_status'], 'Update Local Music or sync Navidrome first') in m.calls,
           'no albums: no order, the message')
    m = albums_page(LIB); m.call(PSYMS['al_on_destroy'], count=2000000)
    expect(any(c[0] == 'free' for c in m.calls), 'closing the Albums page frees the order')
    # Cover Flow and Albums agree
    m1 = lib_machine(); m1.call(cover_open, count=30000000); _, cf_rows = shelf(m1, n)
    m2 = albums_page(LIB); listed(m2)
    expect(cf_rows[:6] == [tap_row(m2, r)[0] for r in range(6)], 'Cover Flow and Albums open the same stock rows in the same order')
