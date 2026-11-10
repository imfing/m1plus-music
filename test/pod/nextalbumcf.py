"""Continue with Next Album, phase 1, from Cover Flow (patch/coverflow.c open_album, patch/nextalbum.c): a tap on the centre cover notes the albums in the order the shelf shows
them (the saved sort and direction), the artist's page notes its scope and artist row, the All albums card is not in the note, and the note is gone when cc_open_album returns."""
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)

NA = sibling('nextalbum')
SORT = '/mnt/data/m1plus/albums-sort'


def library_tests(ctx):
    """The library shelf: stock order, Z-A, and the saved Artist order; the tapped cover is the stock row; the setting off notes nothing."""
    expect = ctx.expect
    keys = lambda order: [album_key(f'Artist {i}', f'Album {i}') for i in order]

    def cover(sort_file=None, setting=True, centre=0, albums=3):
        m = NA.snap(cover_machine(albums=albums))
        if sort_file is not None: m.fs[SORT] = sort_file
        if setting: m.fs[NA.FILE] = b'1\n'
        m.call(PSYMS['coverflow_open'], count=5000000)
        if centre:
            put_value(m, centre); m.call(PSYMS['on_changed'], count=2000000)
        m.tap(O['CF_CX'])
        return m

    m = cover()
    expect(m.noted and m.noted['keys'] == keys([0, 1, 2]) and m.noted['scope'] == 0 and m.noted['artist'] == 0 and NA.state(m)['pending'] is None,
           'the stock order: the three albums\' keys, no scope, no artist; the note is gone once the opener returns')
    m = cover(centre=2)
    expect(m.noted and m.noted['keys'] == keys([0, 1, 2]) and ('navigator_to_with_context', 'albuminfo_page', O['CLASS_ALBUMS'], 2) in m.calls, 'a tap on the third cover opens stock row 2 with the whole list noted')
    m = cover(sort_file=b'a\n')   # Title, Z-A: the shelf shows the albums reversed, the centre cover is stock row 2
    expect(m.noted and m.noted['keys'] == keys([2, 1, 0]) and ('navigator_to_with_context', 'albuminfo_page', O['CLASS_ALBUMS'], 2) in m.calls, 'Z-A: the keys in the order shown; the centre cover is stock row 2')
    m = cover(sort_file=b'1\n')
    order = sorted(range(3), key=lambda i: (f'Artist {i}', f'Album {i}'))
    expect(m.noted and m.noted['keys'] == keys(order), 'the Artist order: the keys by artist')
    m = cover(setting=False)
    expect(m.noted is None and ('navigator_to_with_context', 'albuminfo_page', O['CLASS_ALBUMS'], 0) in m.calls, 'setting off: the album opens as before, nothing is noted')
    m = cover(albums=1)
    expect(m.noted and m.noted['keys'] == keys([0]), 'one album: a note of one (the next key is none)')


def scoped_tests(ctx):
    """An artist's Cover Flow: the artist's albums in the shelf order, the All albums card left out, the artist scope and a copy of the artist row."""
    expect = ctx.expect
    m = NA.snap(artists_machine()); m.fs[NA.FILE] = b'1\n'
    m.call(PSYMS['artists_open'], count=20000000); m.call(PSYMS['ar_open'], a0=0, count=8000000)
    put_value(m, 1); m.call(PSYMS['on_changed'], count=2000000)
    m.tap(O['CF_CX'])
    want = [album_key(m.read_cstr(m.word(r + O['REC_ARTIST'])), m.read_cstr(m.word(r + O['REC_ALBUM']))) for r in m.artist_albums['Miles Davis']]
    n = m.noted
    expect(n and n['keys'] == want and n['scope'] == O['CLASS_ARTISTS'] and len(n['artist_rows']) == 1 and m.read_cstr(m.word(n['artist_rows'][0] + O['REC_TITLE'])) == 'Miles Davis'
           and ('navigator_to_with_context', 'albuminfo_page', O['CLASS_ARTIST_ALBUMS'], 1) in m.calls,
           'the second cover of Miles Davis: his three albums (the All albums card is not one), the artist scope and a copy of the artist row')
    # the card opens our Songs page: no album, no note
    m = NA.snap(artists_machine()); m.fs[NA.FILE] = b'1\n'
    m.call(PSYMS['artists_open'], count=20000000); m.call(PSYMS['ar_open'], a0=0, count=8000000)
    put_value(m, 3); m.call(PSYMS['on_changed'], count=2000000)
    m.tap(O['CF_CX'], count=900000000)
    expect(m.noted is None and NA.state(m)['pending'] is None, 'the All albums card opens the Songs page: nothing is noted')
    # setting off
    m = NA.snap(artists_machine())
    m.call(PSYMS['artists_open'], count=20000000); m.call(PSYMS['ar_open'], a0=0, count=8000000)
    m.tap(O['CF_CX'])
    expect(m.noted is None, 'setting off: nothing is noted')


SECTIONS = [library_tests, scoped_tests]


def run(ctx):
    for f in SECTIONS: f(ctx)
