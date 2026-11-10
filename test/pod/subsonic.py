"""Navidrome/Subsonic network helpers (patch/sbnet.c) and the response parsers (patch/sbparse.c)."""
import json, struct
from harness import *  # noqa: F401,F403

REGION, SIZE = 0x30000000, 0x40000


def parser_tests(ctx):
    expect = ctx.expect
    m = Machine()
    m.u.mem_map(REGION, SIZE)
    src = REGION + 128
    # patch/sbnet.c: the token hash, URL escaping and the JSON walker are exported
    buf = REGION + 40000
    m.u.mem_write(buf, b'abc\0' + bytes(60))
    m.call(PSYMS['sbn_md5'], a0=buf, a1=3, a2=buf + 64)
    expect(bytes(m.u.mem_read(buf + 64, 16)).hex() == '900150983cd24fb0d6963f7d28e17f72',
           'sbnet MD5 matches the RFC 1321 test vector')
    m.u.mem_write(buf, 'a b/é~\0'.encode())
    n = m.call(PSYMS['sbn_urlenc'], a0=buf + 128, a1=64, a2=0, a3=buf)
    expect(bytes(m.u.mem_read(buf + 128, n)).decode() == 'a%20b%2F%C3%A9~' and
           m.call(PSYMS['sbn_urlenc'], a0=buf + 128, a1=4, a2=0, a3=buf) == 0,
           'sbnet URL escaping keeps unreserved characters and fails when the output is too small')
    doc = b'{"subsonic-response":{"status":"ok","n":{"title":"T\\u00e9","count":42,"tail":[{"x":"}"}]}}}'
    m.u.mem_write(src, doc)
    expect(m.call(PSYMS['sbn_response_ok'], a0=src, a1=len(doc)) == 1
           and m.call(PSYMS['sbn_response_ok'], a0=src, a1=len(doc) - 1) == 0,
           'sbnet accepts a complete ok response and rejects a truncated one')

# patch/sbparse.c: the struct layouts of patch/sbapi.h (o32, little endian): text arrays then 32-bit counters, then the flag byte, padded to 4
ID, TXT = 64, 192
TRACK = (ID + TXT * 3 + ID + ID + 12 + 9 * 4 + 1 + 3)
ALBUM = (ID + TXT + TXT + ID + ID + 4 * 4 + 1 + 3)
ARTIST = (ID + TXT + ID + 4 + 1 + 3)
PLAYLIST = (ID + TXT + ID + 2 * 4)
ERR_OK, ERR_AUTH, ERR_NOTFOUND, ERR_PARSE = 0, 7, 8, 10   # the SBA_* enum order of sbapi.h: OK NOCONF NOWIFI NOCLOCK NOCERT CERT NET AUTH NOTFOUND HTTP PARSE


def resp(body, status='ok'):
    return json.dumps({"subsonic-response": dict({"status": status, "version": "1.16.1", "type": "navidrome",
                                                  "serverVersion": "0.53.3", "openSubsonic": True}, **body)}, ensure_ascii=False).encode()


def cstr(raw, off, cap): return raw[off:off + cap].split(b'\0')[0].decode('utf-8')


class Parser:
    OUT, ERR, BUF = REGION + 0x100000, REGION + 0x3f000, REGION + 0x100

    def __init__(self):
        self.m = Machine()
        self.m.u.mem_map(REGION, 0x400000)

    def run(self, fn, body, size, mx=100):
        m = self.m
        m.u.mem_write(self.OUT, bytes(size * min(mx, 8) + 64))
        m.u.mem_write(self.BUF, body)
        m.setword(self.ERR, 0xdead)
        m.setword(STACK + 16, self.ERR)
        n = m.call(PSYMS[fn], a0=self.BUF, a1=len(body), a2=self.OUT, a3=mx)
        n = n - (1 << 32) if n >= 1 << 31 else n
        err = struct.unpack('<I', bytes(m.u.mem_read(self.ERR, 4)))[0]
        return n, err, bytes(m.u.mem_read(self.OUT, size * max(n, 0)))

    def ping(self, body):
        m = self.m
        m.u.mem_write(self.BUF, body)
        m.setword(self.ERR, 0xdead)
        n = m.call(PSYMS['sba_parse_ping'], a0=self.BUF, a1=len(body), a2=self.ERR)
        return (n - (1 << 32) if n >= 1 << 31 else n), struct.unpack('<I', bytes(m.u.mem_read(self.ERR, 4)))[0]

    def tracks(self, body, mx=100): return self.run('sba_parse_tracks', body, TRACK, mx)

    def albums(self, body, mx=100): return self.run('sba_parse_albums', body, ALBUM, mx)

    def artists(self, body, mx=100): return self.run('sba_parse_artists', body, ARTIST, mx)

    def playlists(self, body, mx=100): return self.run('sba_parse_playlists', body, PLAYLIST, mx)


def track_at(raw, i):
    r = raw[i * TRACK:(i + 1) * TRACK]
    o = ID + TXT * 3 + ID + ID + 12
    nums = struct.unpack_from('<9I', r, o)
    return dict(id=cstr(r, 0, ID), title=cstr(r, ID, TXT), artist=cstr(r, ID + TXT, TXT), album=cstr(r, ID + TXT * 2, TXT),
                album_id=cstr(r, ID + TXT * 3, ID), cover=cstr(r, ID + TXT * 3 + ID, ID), suffix=cstr(r, ID + TXT * 3 + ID * 2, 12),
                seconds=nums[0], track=nums[1], disc=nums[2], year=nums[3], size=nums[4], bitrate=nums[5], rate=nums[6], depth=nums[7],
                created=nums[8], starred=r[o + 36])


def parse(ctx):
    """patch/sbparse.c: the sba_parse_* parsers over realistic Subsonic / OpenSubsonic / Navidrome answers."""
    expect = ctx.expect
    P = Parser()
    song = {"id": "so-1", "parent": "al-1", "isDir": False, "title": "Café – Ünïcode 音楽", "album": "Album One", "artist": "The Artist",
            "track": 3, "year": 2019, "genre": "Jazz", "coverArt": "mf-so-1_65f0", "size": 31457280, "contentType": "audio/flac", "suffix": "flac",
            "duration": 245, "bitRate": 912, "bitDepth": 24, "samplingRate": 96000, "path": "The Artist/Album One/03 Cafe.flac", "discNumber": 2,
            "created": "2024-05-01T10:00:00Z", "albumId": "al-1", "artistId": "ar-1", "type": "music", "starred": "2024-06-01T00:00:00Z"}
    album = {"id": "al-1", "name": "Album One", "artist": "The Artist", "artistId": "ar-1", "coverArt": "al-1_65f0", "songCount": 2, "duration": 500,
             "year": 2019, "genre": "Jazz", "created": "2024-05-01T10:00:00Z", "song": [song, {"id": "so-2", "title": "Bare", "track": 4}]}
    # getAlbum: fields, and what a song leaves out comes from the album
    n, err, raw = P.tracks(resp({"album": album}))
    t = [track_at(raw, i) for i in range(max(n, 0))]
    expect(n == 2 and err == ERR_OK, f'getAlbum parses two songs: {n} {err}')
    s = t[0]
    expect(s['id'] == 'so-1' and s['title'] == 'Café – Ünïcode 音楽' and s['artist'] == 'The Artist' and s['album'] == 'Album One'
           and s['album_id'] == 'al-1' and s['cover'] == 'mf-so-1_65f0' and s['suffix'] == 'flac', f'song text fields: {s}')
    expect((s['seconds'], s['track'], s['disc'], s['year'], s['size'], s['bitrate'], s['rate'], s['depth']) == (245, 3, 2, 2019, 31457280, 912, 96000, 24)
           and s['starred'] == 1, f'song numbers and the starred flag: {s}')
    expect(t[0]['created'] == 1714557600, 'created parses an ISO time to epoch seconds (2024-05-01T10:00:00Z)')
    s = t[1]
    expect(s['id'] == 'so-2' and s['title'] == 'Bare' and s['album'] == 'Album One' and s['album_id'] == 'al-1' and s['cover'] == 'al-1_65f0'
           and s['year'] == 2019 and s['artist'] == 'The Artist' and s['starred'] == 0 and s['suffix'] == '' and s['seconds'] == 0,
           f'a song without album fields inherits the album id, cover, year, album and artist: {s}')
    # getPlaylist (entry[]), getStarred2 and search3 song[]
    pl = {"id": "pl-1", "name": "Mix", "songCount": 1, "entry": [dict(song, id="e-1", albumId="al-9")]}
    n, err, raw = P.tracks(resp({"playlist": pl}))
    expect(n == 1 and track_at(raw, 0)['id'] == 'e-1' and track_at(raw, 0)['album_id'] == 'al-9', 'getPlaylist entries parse and keep their own album id')
    st = {"starred2": {"song": [dict(song, id="s-1"), dict(song, id="s-2")], "album": [album], "artist": [{"id": "ar-1", "name": "X"}]}}
    n, err, raw = P.tracks(resp(st))
    expect(n == 2 and track_at(raw, 1)['id'] == 's-2', 'getStarred2 song[] parses (albums and artists beside it are left alone)')
    n, err, raw = P.tracks(resp({"searchResult3": {"song": [dict(song, id="q-1")]}}))
    expect(n == 1 and track_at(raw, 0)['id'] == 'q-1', 'search3 song[] parses')
    # malformed scalars and mismatched brackets end the walk (the instruction budget of Machine.call catches a hang)
    for bad in (b'{"subsonic-response":{"status":"ok","searchResult3":{"song":[}{]}}}', b'{"subsonic-response":{"status":"ok","searchResult3":{"song":[}',
                b'{"subsonic-response":{"status":"ok","searchResult3":{"song":[{"id":"a"},}]}}}', b'{"subsonic-response":{"status":"ok","searchResult3":{"song":{"a":}}}}',
                b'{"subsonic-response":{"status":"ok","searchResult3":{"song":[{"id":"a"]}}}'):
        n, err, raw = P.tracks(bad)
        expect(n <= 1 and (n >= 0 or err != ERR_OK), f'malformed JSON {bad[-30:]!r} returns without hanging: {n} {err}')
    n, err, raw = P.tracks(resp({"searchResult3": {}}))
    expect(n == 0 and err == ERR_OK, 'an empty search3 is zero rows, not an error')
    n, err, raw = P.tracks(resp({"album": album}), mx=1)
    expect(n == 1, 'the row cap is honoured')
    # DSD detection inputs: suffix, contentType and path fallbacks
    rows = [{"id": "d1", "title": "A", "suffix": "DSF"}, {"id": "d2", "title": "B", "contentType": "audio/x-dff"},
            {"id": "d3", "title": "C", "path": "x/y.v2/Song.DFF"}, {"id": "d4", "title": "D", "contentType": "audio/mpeg"},
            {"id": "d5", "title": "E", "contentType": "audio/x-dsf"}, {"id": "d6", "title": "F", "path": "dir.d/noext"}]
    n, err, raw = P.tracks(resp({"searchResult3": {"song": rows}}))
    sf = [track_at(raw, i)['suffix'] for i in range(n)]
    expect(sf == ['dsf', 'dff', 'dff', 'mp3', 'dsf', ''], f'suffix: own (lower case), then contentType, then the path extension: {sf}')
    # ids: a row without an id, an id that is too long, a numeric id
    rows = [{"title": "no id"}, {"id": "x" * 80, "title": "long"}, {"id": 42, "title": "numeric"}, {"id": "ok", "title": "ok"}]
    n, err, raw = P.tracks(resp({"searchResult3": {"song": rows}}))
    expect(n == 2 and track_at(raw, 0)['id'] == '42' and track_at(raw, 1)['id'] == 'ok', 'rows without a usable id are skipped, a numeric id is written out')
    # overlong text is cut at a UTF-8 boundary; a key inside a title does not confuse the walker
    rows = [{"id": "l1", "title": "音" * 100, "artist": 'say "song": [ {"id":"evil"} ]', "album": "é" * 200}]
    n, err, raw = P.tracks(resp({"searchResult3": {"song": rows}}))
    t0 = track_at(raw, 0) if n == 1 else {}
    expect(n == 1 and len(t0['title'].encode()) == 189 and len(t0['album'].encode()) == 190 and t0['artist'].startswith('say "song"'),
           f'long text is cut on a character boundary and structural lookup ignores keys inside strings: {n}')
    # string numbers, floats, nulls
    rows = [{"id": "n1", "title": "T", "duration": "187", "track": 5.0, "year": None, "size": "x", "starred": None, "bitDepth": 16.5}]
    n, err, raw = P.tracks(resp({"searchResult3": {"song": rows}}))
    t0 = track_at(raw, 0)
    expect((t0['seconds'], t0['track'], t0['year'], t0['size'], t0['starred'], t0['depth']) == (187, 5, 0, 0, 0, 16),
           f'numbers sent as strings or floats parse, null and junk are 0: {t0}')

    # getAlbumList2, getArtist, search3 and getStarred2 albums
    al = [{"id": "a1", "name": "Alpha", "title": "Alpha", "artist": "AA", "artistId": "r1", "coverArt": "al-a1", "songCount": 10, "duration": 2400,
           "year": 1999, "created": "2020-01-02T03:04:05.678Z", "starred": "2021-01-01T00:00:00Z", "isDir": True, "isVideo": False},
          {"id": "a2", "name": "Beta 音", "songCount": 1}, {"name": "no id"}]
    n, err, raw = P.albums(resp({"albumList2": {"album": al}}))
    rows = [raw[i * ALBUM:(i + 1) * ALBUM] for i in range(max(n, 0))]
    num = lambda r: struct.unpack_from('<4I', r, ID + TXT * 2 + ID * 2)
    expect(n == 2 and cstr(rows[0], 0, ID) == 'a1' and cstr(rows[0], ID, TXT) == 'Alpha' and cstr(rows[0], ID + TXT, TXT) == 'AA'
           and cstr(rows[0], ID + TXT * 2, ID) == 'r1' and cstr(rows[0], ID + TXT * 2 + ID, ID) == 'al-a1'
           and num(rows[0]) == (1999, 10, 2400, 1577934245) and rows[0][ID + TXT * 2 + ID * 2 + 16] == 1,
           'getAlbumList2 album fields, counters, created time and starred flag')
    expect(cstr(rows[1], ID, TXT) == 'Beta 音' and num(rows[1])[1] == 1, 'a sparse album keeps what it has; the id-less one is skipped')
    n, err, raw = P.albums(resp({"albumList2": {}}))
    expect(n == 0 and err == ERR_OK, 'an empty getAlbumList2 page is zero rows')
    ar = {"id": "r1", "name": "AA", "albumCount": 2, "album": [{"id": "a1", "name": "Alpha"}, {"id": "a2", "name": "Beta", "artist": "Guest", "artistId": "r9"}]}
    n, err, raw = P.albums(resp({"artist": ar}))
    rows = [raw[i * ALBUM:(i + 1) * ALBUM] for i in range(max(n, 0))]
    expect(n == 2 and cstr(rows[0], ID + TXT, TXT) == 'AA' and cstr(rows[0], ID + TXT * 2, ID) == 'r1' and cstr(rows[1], ID + TXT, TXT) == 'Guest'
           and cstr(rows[1], ID + TXT * 2, ID) == 'r9', "getArtist's albums inherit the artist's name and id when they omit them")
    n, err, raw = P.albums(resp(st))
    expect(n == 1 and cstr(raw, 0, ID) == 'al-1', 'getStarred2 album[] parses')
    n, err, raw = P.albums(resp({"searchResult3": {"album": al, "song": [song]}}))
    expect(n == 2, 'search3 album[] parses')

    # getArtists: index[] -> artist[] flattened
    idx = {"artists": {"ignoredArticles": "The El La", "lastModified": 1700000000000, "index": [
        {"name": "A", "artist": [{"id": "r1", "name": "AA", "albumCount": 3, "coverArt": "ar-r1", "artistImageUrl": "http://x/y.jpg", "starred": "2020-01-01T00:00:00Z"},
                                 {"id": "r2", "name": "Ab"}]},
        {"name": "B", "artist": []}, {"name": "C"}, {"name": "Z", "artist": [{"id": "r3", "name": "Zoë"}, {"name": "no id"}]}]}}
    n, err, raw = P.artists(resp(idx))
    rows = [raw[i * ARTIST:(i + 1) * ARTIST] for i in range(max(n, 0))]
    expect(n == 3 and [cstr(r, 0, ID) for r in rows] == ['r1', 'r2', 'r3'] and cstr(rows[0], ID, TXT) == 'AA' and cstr(rows[0], ID + TXT, ID) == 'ar-r1'
           and struct.unpack_from('<I', rows[0], ID + TXT + ID)[0] == 3 and rows[0][ID + TXT + ID + 4] == 1 and cstr(rows[2], ID, TXT) == 'Zoë',
           'getArtists flattens the index letters in the server order')
    n, err, raw = P.artists(resp(idx), mx=2)
    expect(n == 2, 'getArtists honours the row cap across letters')
    n, err, raw = P.artists(resp({"artists": {"index": []}}))
    expect(n == 0 and err == ERR_OK, 'getArtists with no letters is zero rows')
    n, err, raw = P.artists(resp(st))
    expect(n == 1 and cstr(raw, 0, ID) == 'ar-1', 'getStarred2 artist[] parses')
    n, err, raw = P.artists(resp({"searchResult3": {"artist": [{"id": "r5", "name": "Q"}]}}))
    expect(n == 1 and cstr(raw, ID, TXT) == 'Q', 'search3 artist[] parses')

    # getPlaylists
    pls = {"playlists": {"playlist": [{"id": "p1", "name": "Road 🚗", "comment": "c", "owner": "xin", "public": False, "songCount": 12, "duration": 3000,
                                         "created": "2024-01-01T00:00:00Z", "changed": "2024-01-02T00:00:00Z", "coverArt": "pl-p1"}, {"id": "p2", "name": "Empty"}]}}
    n, err, raw = P.playlists(resp(pls))
    rows = [raw[i * PLAYLIST:(i + 1) * PLAYLIST] for i in range(max(n, 0))]
    expect(n == 2 and cstr(rows[0], ID, TXT) == 'Road 🚗' and cstr(rows[0], ID + TXT, ID) == 'pl-p1'
           and struct.unpack_from('<2I', rows[0], ID + TXT + ID) == (12, 3000) and cstr(rows[1], 0, ID) == 'p2', 'getPlaylists parses names, covers, counts')
    n, err, raw = P.playlists(resp({"playlists": {}}))
    expect(n == 0 and err == ERR_OK, 'a server with no playlists answers an empty object: zero rows')

    # errors, truncation and non-Subsonic bodies
    fail = lambda code, msg: resp({"error": {"code": code, "message": msg}}, status='failed')
    for code, want, label in ((40, ERR_AUTH, 'wrong password'), (41, ERR_AUTH, 'token authentication refused'), (70, ERR_NOTFOUND, 'not found'),
                              (10, ERR_PARSE, 'a missing parameter'), (0, ERR_PARSE, 'a generic error')):
        for fn in (P.tracks, P.albums, P.artists, P.playlists):
            n, err, _ = fn(fail(code, label))
            if not (n == -1 and err == want):
                expect(False, f'error {code} ({label}) through {fn.__name__}: {n} {err}')
                break
        else:
            expect(True, f'error {code} ({label}) is -1 with the matching SBA_ code')
    whole = resp({"album": album})
    for cut in (len(whole) - 1, len(whole) // 2, 40, 1):
        n, err, _ = P.tracks(whole[:cut])
        if not (n == -1 and err == ERR_PARSE):
            expect(False, f'a response cut at {cut} of {len(whole)} is refused: {n} {err}')
            break
    else:
        expect(True, 'a truncated response is refused whole (-1, SBA_PARSE), never half read')
    for body in (b'<html><body>502 Bad Gateway</body></html>', b'', b'{"foo":1}', b'[]', b'{"subsonic-response":[]}'):
        n, err, _ = P.albums(body)
        if not (n == -1 and err == ERR_PARSE):
            expect(False, f'a non-Subsonic body {body[:20]!r} is SBA_PARSE: {n} {err}')
            break
    else:
        expect(True, 'a web page, an empty body and foreign JSON are SBA_PARSE')
    n, err, _ = P.tracks(resp({"album": {"id": "a", "song": [{"id": "1"}], "song2": 1}}).replace(b'"song2"', b'"song"'))
    expect(n == -1 and err == ERR_PARSE, 'a duplicate song key is malformed, not guessed')
    expect(P.ping(resp({})) == (0, ERR_OK) and P.ping(fail(40, 'bad')) == (-1, ERR_AUTH) and P.ping(fail(70, 'x')) == (-1, ERR_NOTFOUND)
           and P.ping(b'oops') == (-1, ERR_PARSE), 'ping: ok is 0, errors map to SBA_AUTH / SBA_NOTFOUND / SBA_PARSE')
    big = resp({"searchResult3": {"song": [dict(song, id=f"id{i}") for i in range(300)]}})
    n, err, raw = P.tracks(big, mx=500)
    expect(n == 300 and track_at(raw, 299)['id'] == 'id299', f'a page of 300 songs ({len(big)} bytes) parses in full')


SECTIONS = [parser_tests, parse]   # tools/check.py runs each as its own task


def run(ctx):
    for section in SECTIONS: section(ctx)
