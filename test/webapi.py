#!/usr/bin/env python3
"""Tests of Wi-Fi Transfer's server side (docs/modules/wifi-transfer.md): patch/webapi.c and tools/mod_webapp.py.

  uv run python -I test/webapi.py [TREE STOCK]

The CGI is compiled for the host with -DWEBAPI_HOST and -DWEBAPI_ROOT pointing at a temporary directory, then run
as a CGI would be (environment variables, the body on stdin) for every operation: path validation, JSON
escaping, tar archives (read back with tarfile), conflict names, chunked and interrupted uploads, symlinks.
The real MIPS executable runs in Unicorn (raw system calls answered from the same temporary directory) and
must answer a scripted session byte for byte like the host build. With a built TREE and the STOCK tree:
the executable is in the rootfs, is what the sources build, has the expected ELF layout, and the stock web app
is gone while thttpd, its configuration and the favicon are untouched.
"""
import json, os, re, shutil, struct, subprocess, sys, tarfile, io, tempfile, urllib.parse
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import mod_webapp   # noqa: E402
import pod_i18n     # noqa: E402

ok = fail = 0
RENAMES = []   # the rename(2) calls of the last mips_run


def expect(name, cond, detail=''):
    global ok, fail
    if cond: ok += 1
    else: fail += 1; print(f'FAIL {name} {detail}'[:600])


class Cgi:
    """The CGI built for the host over a temporary card; call() runs one request."""

    def __init__(self, td):
        self.root = os.path.realpath(td) + '/mmc'
        os.makedirs(self.root)
        self.exe = os.path.join(td, 'api')
        cc = shutil.which('cc') or shutil.which('clang')
        subprocess.run([cc, '-DWEBAPI_HOST', f'-DWEBAPI_ROOT="{self.root}"', '-Wall', '-Wextra', '-Werror', '-O1', '-g',
                        '-fsanitize=address,undefined', '-fno-sanitize-recover=undefined', '-o', self.exe,
                        os.path.join(ROOT, 'patch', 'webapi.c')], check=True)

    def env(self, op, method, q, ctype, length):
        qs = urllib.parse.urlencode([('op', op), *q], quote_via=urllib.parse.quote)
        e = {'REQUEST_METHOD': method, 'QUERY_STRING': qs, 'ASAN_OPTIONS': 'detect_leaks=0'}
        if ctype: e['CONTENT_TYPE'] = ctype
        if length is not None: e['CONTENT_LENGTH'] = str(length)
        return e

    def call(self, op, q=(), method='GET', body=b'', ctype=None, length=None, raw_qs=None):
        env = self.env(op, method, q, ctype, len(body) if length is None and method == 'POST' else length)
        if raw_qs is not None: env['QUERY_STRING'] = raw_qs
        r = subprocess.run([self.exe], env=env, input=body, capture_output=True, timeout=60)
        return parse_response(r.stdout, r.returncode, r.stderr)

    def post(self, op, q=(), form=(), **kw):
        body = urllib.parse.urlencode(list(form), quote_via=urllib.parse.quote).encode()
        return self.call(op, q, method='POST', body=body, ctype='application/octet-stream', **kw)

    def path(self, *p): return os.path.join(self.root, *p)


def parse_response(out, rc, err=b''):
    head, _, body = out.partition(b'\r\n\r\n')
    lines = head.decode('utf-8', 'replace').split('\r\n')
    status = 200
    headers = {}
    for ln in lines:
        k, _, v = ln.partition(': ')
        if k == 'Status': status = int(v.split()[0])
        else: headers[k] = v
    return {'status': status, 'headers': headers, 'body': body, 'rc': rc, 'err': err}


def js(r): return json.loads(r['body'])


def listing(c, path='/'):
    r = c.call('list', [('path', path)])
    return {e['name']: e for e in js(r)['entries']} if r['status'] == 200 else r


def host_tests(td):
    c = Cgi(td)
    R = c.path
    os.makedirs(R('Music', 'Album'))
    os.makedirs(R('.m1plus'))
    os.makedirs(R('Empty'))
    for n, d in (('Music/a.flac', b'A' * 1000), ('Music/._a.flac', b'x'), ('Music/Album/t1.mp3', b'1' * 10),
                 ('Music/Album/t2.mp3', b''), ('Music/Album/.hidden', b'h'), ('top.txt', b'hello'), ('.m1plus/db', b'secret'),
                 ('odd "quote" \\back.txt', b'q'), ('日本語 ファイル.m4a', b'jp'), ('tab\tname.txt', b't'), ('nl\nname.txt', b'n'),
                 ('Music/Album/x.unknownext', b'u')):
        Path(R(n)).write_bytes(d)
    os.symlink('/etc', R('Music', 'evil'))
    os.symlink(R('top.txt'), R('linkfile'))

    # ---- list
    r = c.call('list', [('path', '/')])
    expect('list 200 json', r['status'] == 200 and r['headers']['Content-Type'].startswith('application/json'), r['headers'])
    j = js(r)
    names = {e['name']: e for e in j['entries']}
    expect('list path', j['path'] == '/')
    expect('list hides dot names', '.m1plus' not in names and not any(n.startswith('.') for n in names))
    expect('list skips symlinks', 'linkfile' not in names)
    expect('list odd names', all(n in names for n in ('odd "quote" \\back.txt', '日本語 ファイル.m4a', 'tab\tname.txt', 'nl\nname.txt')), list(names))
    expect('list raw escapes', b'\\"quote\\"' in r['body'] and b'\\\\back' in r['body'] and b'\\t' in r['body'] and b'\\n' in r['body'])
    expect('list utf8 passthrough', '日本語'.encode() in r['body'])
    expect('list file entry', names['top.txt'] == {'name': 'top.txt', 'dir': False, 'size': 5, 'mtime': int(os.lstat(R('top.txt')).st_mtime)}, names.get('top.txt'))
    expect('list folder entry', names['Music']['dir'] and names['Music']['items'] == 3 and names['Empty']['items'] == 0, names['Music'])
    sub = listing(c, '/Music/Album')
    expect('list all extensions', 'x.unknownext' in sub and 't2.mp3' in sub and sub['t2.mp3']['size'] == 0 and '.hidden' not in sub)
    expect('list subfolder path', js(c.call('list', [('path', 'Music//Album/')]))['path'] == '/Music/Album')
    expect('list default path', js(c.call('list'))['path'] == '/')
    expect('list a file 400', c.call('list', [('path', '/top.txt')])['status'] == 400)
    expect('list missing 404', c.call('list', [('path', '/nope')])['status'] == 404)
    expect('list under file 404', c.call('list', [('path', '/top.txt/x')])['status'] == 404)
    for bad, st in (('/..', 400), ('/Music/../top.txt', 400), ('/Music/./Album', 400), ('/%2e%2e/etc', 400), ('/.m1plus', 403),
                    ('/Music/.hidden', 403), ('/Music/evil', 403), ('/Music/evil/passwd', 403), ('/linkfile', 403)):
        r = c.call('list', raw_qs='op=list&path=' + urllib.parse.quote(bad, safe='%/') if '%' in bad else None, q=[('path', bad)])
        expect(f'list {bad!r} -> {st}', r['status'] == st, r['status'])
        expect(f'list {bad!r} error json', 'error' in js(r))
    expect('nul byte', c.call('list', raw_qs='op=list&path=%2FMusic%00').get('status') == 400)
    expect('bad percent', c.call('list', raw_qs='op=list&path=%zz')['status'] == 400)
    # a parameter without '=' has an empty value (it once crashed the CGI by writing into a string literal)
    r = c.call('list', raw_qs='op=list&unused')
    expect('bare unused parameter is ignored', r['status'] == 200 and js(r)['path'] == '/', r['status'])
    r = c.call('list', raw_qs='op=list&path')
    expect('bare path behaves like an empty path', r['status'] == c.call('list', raw_qs='op=list&path=')['status'], r['status'])
    expect('bare parameter first and last', c.call('list', raw_qs='unused&op=list&x&path=%2FMusic&y')['status'] == 200)
    expect('plus is space', c.call('list', raw_qs='op=list&path=/Music+x')['status'] == 404)
    expect('no op 400', c.call('x', raw_qs='path=/')['status'] == 400)
    expect('unknown op 400', c.call('frob')['status'] == 400)
    expect('head 405', c.call('list', method='HEAD')['status'] == 405)
    os.makedirs(R('Big'))
    for i in range(300): Path(R('Big', f'f{i}')).write_bytes(b'')
    expect('list 300 entries', len(js(c.call('list', [('path', '/Big')]))['entries']) == 300)

    # ---- df
    d = js(c.call('df'))
    expect('df', d['total'] > 0 and 0 <= d['free'] <= d['total'], d)

    # ---- download
    r = c.call('download', [('path', '/Music/a.flac')])
    expect('download', r['status'] == 200 and r['body'] == b'A' * 1000 and r['headers']['Content-Length'] == '1000'
           and r['headers']['Content-Type'] == 'application/octet-stream', r['headers'])
    expect('download disposition', r['headers']['Content-Disposition'] == 'attachment; filename="a.flac"; filename*=UTF-8\'\'a.flac')
    r = c.call('download', [('path', '/日本語 ファイル.m4a')])
    cd = r['headers']['Content-Disposition']
    expect('download utf8 name', "filename*=UTF-8''%E6%97%A5%E6%9C%AC%E8%AA%9E%20%E3%83%95%E3%82%A1%E3%82%A4%E3%83%AB.m4a" in cd
           and 'filename="___' in cd.replace('_', '_') and r['body'] == b'jp', cd)
    r = c.call('download', [('path', '/odd "quote" \\back.txt')])
    expect('download quote name', 'filename="odd _quote_ _back.txt"' in r['headers']['Content-Disposition'], r['headers'])
    expect('download folder 400', c.call('download', [('path', '/Music')])['status'] == 400)
    expect('download missing 404', c.call('download', [('path', '/nope')])['status'] == 404)
    expect('download hidden 403', c.call('download', [('path', '/.m1plus/db')])['status'] == 403)
    expect('download via symlink 403', c.call('download', [('path', '/Music/evil/passwd')])['status'] == 403)
    expect('download empty file', c.call('download', [('path', '/Music/Album/t2.mp3')])['body'] == b'')
    big = os.urandom(3 * 1024 * 1024 + 17)
    Path(R('big.bin')).write_bytes(big)
    r = c.call('download', [('path', '/big.bin')])
    expect('download 3 MB', r['body'] == big and r['headers']['Content-Length'] == str(len(big)))

    # ---- tar
    deep = 'd' * 60
    os.makedirs(R('Tree', deep, deep, 'leaf'))
    long_name = 'n' * 120 + '.txt'
    Path(R('Tree', deep, deep, long_name)).write_bytes(b'long')
    Path(R('Tree', 'f512')).write_bytes(b'z' * 512)
    Path(R('Tree', 'f513')).write_bytes(b'y' * 513)
    Path(R('Tree', 'zero')).write_bytes(b'')
    Path(R('Tree', '.dot')).write_bytes(b'no')
    os.makedirs(R('Tree', 'Empty'))
    Path(R('Tree', 'big.bin')).write_bytes(big)
    os.symlink('/etc', R('Tree', 'link'))
    r = c.call('tar', [('path', '/Tree')])
    expect('tar headers', r['status'] == 200 and r['headers']['Content-Type'] == 'application/x-tar'
           and 'filename="Tree.tar"' in r['headers']['Content-Disposition'], r['headers'])
    expect('tar block aligned', len(r['body']) % 512 == 0 and r['body'].endswith(bytes(1024)))
    with tarfile.open(fileobj=io.BytesIO(r['body'])) as t:
        m = {x.name: x for x in t.getmembers()}
        expect('tar names', set(m) == {'Tree', 'Tree/' + deep, 'Tree/' + deep + '/' + deep, 'Tree/' + deep + '/' + deep + '/leaf',
                                       f'Tree/{deep}/{deep}/{long_name}', 'Tree/f512', 'Tree/f513', 'Tree/zero', 'Tree/Empty', 'Tree/big.bin'}, sorted(m))
        expect('tar types', m['Tree'].isdir() and m['Tree/Empty'].isdir() and m['Tree/f512'].isfile())
        expect('tar contents', t.extractfile('Tree/f512').read() == b'z' * 512 and t.extractfile('Tree/f513').read() == b'y' * 513
               and t.extractfile('Tree/zero').read() == b'' and t.extractfile('Tree/big.bin').read() == big
               and t.extractfile(f'Tree/{deep}/{deep}/{long_name}').read() == b'long')
        expect('tar mtime and mode', m['Tree/f512'].mtime == int(os.lstat(R('Tree', 'f512')).st_mtime) and m['Tree/f512'].mode == 0o644 and m['Tree'].mode == 0o755)
        expect('tar format is GNU', r['body'][257:265] == b'ustar  \0')
    r = c.call('tar', [('path', '/Music/a.flac'), ('path', '/日本語 ファイル.m4a'), ('path', '/Empty')])
    with tarfile.open(fileobj=io.BytesIO(r['body'])) as t:
        expect('tar several items', t.getnames() == ['a.flac', '日本語 ファイル.m4a', 'Empty'], t.getnames())
    expect('tar several name', 'filename="M1 Plus.tar"' in r['headers']['Content-Disposition'])
    r = c.call('tar', [('path', '/Music/a.flac'), ('name', 'mine')])
    expect('tar name param', 'filename="mine.tar"' in r['headers']['Content-Disposition'])
    expect('tar none 400', c.call('tar')['status'] == 400)
    expect('tar root 400', c.call('tar', [('path', '/')])['status'] == 400)
    expect('tar missing 404', c.call('tar', [('path', '/Music'), ('path', '/nope')])['status'] == 404)
    expect('tar hidden 403', c.call('tar', [('path', '/.m1plus')])['status'] == 403)
    r = c.call('tar', method='POST', body=urllib.parse.urlencode([('path', '/Music/a.flac')]).encode(), ctype='application/x-www-form-urlencoded')
    expect('tar by POST form', r['status'] == 200 and tarfile.open(fileobj=io.BytesIO(r['body'])).getnames() == ['a.flac'])
    # nesting: the walk reaches 40 levels below the item; deeper content is refused before any byte of the archive
    os.makedirs(R('Lim', *['a'] * 40))
    Path(R('Lim', *['a'] * 39, 'f.txt')).write_bytes(b'ok')
    r = c.call('tar', [('path', '/Lim')])
    expect('tar at the depth limit succeeds, complete', r['status'] == 200 and r['body'].endswith(bytes(1024))
           and len(tarfile.open(fileobj=io.BytesIO(r['body'])).getnames()) == 42)
    os.makedirs(R('Over', *['a'] * 41))
    r = c.call('tar', [('path', '/Over')])
    expect('tar 41 levels deep is refused, not truncated', r['status'] == 400 and 'deep' in js(r)['error']
           and r['headers']['Content-Type'].startswith('application/json'), r['status'])
    Path(R('Lim', *['a'] * 40, 'f.txt')).write_bytes(b'x')
    expect('tar a file below the limit is refused', c.call('tar', [('path', '/Lim')])['status'] == 400)
    expect('tar refusal covers a mixed selection', c.call('tar', [('path', '/Music/a.flac'), ('path', '/Over')])['status'] == 400)
    shutil.rmtree(R('Over')); shutil.rmtree(R('Lim'))

    # ---- mutating ops need POST and a non-simple content type
    for op, q in (('mkdir', [('path', '/'), ('name', 'x')]), ('rename', [('path', '/top.txt'), ('name', 'y')]),
                  ('move', [('path', '/top.txt'), ('to', '/Empty')]), ('delete', [('path', '/top.txt')]), ('upload', [('path', '/'), ('name', 'u')])):
        expect(f'{op} GET 405', c.call(op, q)['status'] == 405)
        for ct in (None, 'application/x-www-form-urlencoded', 'multipart/form-data; boundary=x', 'text/plain'):
            r = c.call(op, q, method='POST', body=b'', ctype=ct)
            expect(f'{op} POST {ct} 403', r['status'] == 403, r['status'])
    expect('nothing changed', os.path.exists(R('top.txt')) and not os.path.exists(R('x')) and not os.path.exists(R('u')))

    # ---- mkdir
    r = c.post('mkdir', [('path', '/Music'), ('name', 'New Folder')])
    expect('mkdir', r['status'] == 200 and js(r) == {'name': 'New Folder'} and os.path.isdir(R('Music', 'New Folder')), r['body'])
    expect('mkdir exists 409', c.post('mkdir', [('path', '/Music'), ('name', 'New Folder')])['status'] == 409)
    expect('mkdir clashes with file 409', c.post('mkdir', [('path', '/'), ('name', 'top.txt')])['status'] == 409)
    for bad in ('', '.', '..', 'a/b', '/', '.hidden', 'x' * 241, 'nl\nx', 'a\x7fb'):
        r = c.post('mkdir', [('path', '/'), ('name', bad)])
        expect(f'mkdir name {bad!r} 400', r['status'] == 400, (r['status'], r['body']))
    expect('mkdir no name 400', c.post('mkdir', [('path', '/')])['status'] == 400)
    expect('mkdir parent missing 404', c.post('mkdir', [('path', '/nope'), ('name', 'x')])['status'] == 404)
    expect('mkdir parent file 400', c.post('mkdir', [('path', '/top.txt'), ('name', 'x')])['status'] == 400)
    expect('mkdir under symlink 403', c.post('mkdir', [('path', '/Music/evil'), ('name', 'x')])['status'] == 403)
    expect('mkdir hidden parent 403', c.post('mkdir', [('path', '/.m1plus'), ('name', 'x')])['status'] == 403)
    expect('mkdir by form body', c.post('mkdir', form=[('path', '/Music'), ('name', 'Body')])['status'] == 200)

    # ---- rename
    r = c.post('rename', [('path', '/top.txt'), ('name', 'renamed.txt')])
    expect('rename', r['status'] == 200 and js(r) == {'name': 'renamed.txt'} and os.path.exists(R('renamed.txt')) and not os.path.exists(R('top.txt')))
    expect('rename same name', c.post('rename', [('path', '/renamed.txt'), ('name', 'renamed.txt')])['status'] == 200)
    expect('rename clash 409', c.post('rename', [('path', '/renamed.txt'), ('name', 'Music')])['status'] == 409)
    expect('rename case only', c.post('rename', [('path', '/renamed.txt'), ('name', 'Renamed.txt')])['status'] == 200 and 'Renamed.txt' in os.listdir(R()))
    expect('rename case only leaves no temporary name', not [n for n in os.listdir(R()) if n.startswith('.rename')])
    for bad in ('a"b', 'a*b', 'a:b', 'a<b', 'a>b', 'a?b', 'a\\b', 'a|b', 'a\x01b', 'trail.', 'trail ', 'a\x7fb'):
        expect(f'rename {bad!r} 400', c.post('rename', [('path', '/Renamed.txt'), ('name', bad)])['status'] == 400)
        expect(f'mkdir {bad!r} 400', c.post('mkdir', [('path', '/'), ('name', bad)])['status'] == 400)
        r = c.call('upload', [('path', '/Music'), ('name', bad)], method='POST', body=b'x' * 5000, ctype='application/octet-stream')
        expect(f'upload {bad!r} 400', r['status'] == 400 and 'error' in js(r), r['status'])
    expect('illegal names leave nothing behind', not [n for n in os.listdir(R()) + os.listdir(R('Music')) if n.endswith('.part') or n.startswith('a') and n.endswith('b')])
    expect('rename root 403', c.post('rename', [('path', '/'), ('name', 'x')])['status'] == 403)
    expect('rename slash 400', c.post('rename', [('path', '/Renamed.txt'), ('name', 'a/b')])['status'] == 400)
    expect('rename dotdot 400', c.post('rename', [('path', '/Renamed.txt'), ('name', '..')])['status'] == 400)
    expect('rename hidden target 400', c.post('rename', [('path', '/Renamed.txt'), ('name', '.m1plus')])['status'] == 400)
    expect('rename hidden source 403', c.post('rename', [('path', '/.m1plus'), ('name', 'x')])['status'] == 403)
    expect('rename missing 404', c.post('rename', [('path', '/nope'), ('name', 'x')])['status'] == 404)
    expect('rename a folder', c.post('rename', [('path', '/Music/New Folder'), ('name', 'Renamed Folder')])['status'] == 200 and os.path.isdir(R('Music', 'Renamed Folder')))
    expect('rename symlink 403', c.post('rename', [('path', '/Music/evil'), ('name', 'x')])['status'] == 403)

    # ---- move
    for n in ('m1', 'm2', 'm3'): Path(R(n)).write_bytes(n.encode())
    os.makedirs(R('Dest')); os.makedirs(R('Src', 'inner'))
    Path(R('Dest', 'm2')).write_bytes(b'old')
    r = c.post('move', form=[('to', '/Dest'), ('path', '/m1'), ('path', '/m2'), ('path', '/m3')])
    expect('move clash 409 moves nothing', r['status'] == 409 and os.path.exists(R('m1')) and os.path.exists(R('m3')) and Path(R('Dest', 'm2')).read_bytes() == b'old', r['body'])
    r = c.post('move', form=[('to', '/Dest'), ('conflict', 'keep'), ('path', '/m1'), ('path', '/m2'), ('path', '/m3')])
    expect('move keep', r['status'] == 200 and js(r)['moved'] == [{'from': '/m1', 'to': '/Dest/m1'}, {'from': '/m2', 'to': '/Dest/m2 2'}, {'from': '/m3', 'to': '/Dest/m3'}]
           and Path(R('Dest', 'm2 2')).read_bytes() == b'm2' and Path(R('Dest', 'm2')).read_bytes() == b'old', r['body'])
    r = c.post('move', form=[('to', '/Dest'), ('path', '/Src')])
    expect('move folder', r['status'] == 200 and os.path.isdir(R('Dest', 'Src', 'inner')) and not os.path.exists(R('Src')))
    expect('move into itself 400', c.post('move', form=[('to', '/Dest/Src/inner'), ('path', '/Dest')])['status'] == 400)
    expect('move into self dir 400', c.post('move', form=[('to', '/Dest'), ('path', '/Dest')])['status'] == 400)
    r = c.post('move', form=[('to', '/Dest'), ('path', '/Dest/m1')])
    expect('move same folder is a no-op', r['status'] == 200 and js(r)['moved'] == [] and os.path.exists(R('Dest', 'm1')))
    expect('move to missing 404', c.post('move', form=[('to', '/nope'), ('path', '/Dest/m1')])['status'] == 404)
    expect('move to file 400', c.post('move', form=[('to', '/Renamed.txt'), ('path', '/Dest/m1')])['status'] == 400)
    expect('move root 403', c.post('move', form=[('to', '/Dest'), ('path', '/')])['status'] == 403)
    expect('move hidden 403', c.post('move', form=[('to', '/Dest'), ('path', '/.m1plus')])['status'] == 403)
    expect('move into hidden 403', c.post('move', form=[('to', '/.m1plus'), ('path', '/Dest/m1')])['status'] == 403)
    expect('move missing source 404 and nothing moved', c.post('move', form=[('to', '/Empty'), ('path', '/Dest/m1'), ('path', '/nope')])['status'] == 404 and os.path.exists(R('Dest', 'm1')))
    expect('move none 400', c.post('move', form=[('to', '/Dest')])['status'] == 400)
    expect('move bad mode 400', c.post('move', form=[('to', '/Dest'), ('conflict', 'replace'), ('path', '/Dest/m1')])['status'] == 400)
    expect('move from query', c.post('move', [('to', '/Empty'), ('path', '/Dest/m1')])['status'] == 200 and os.path.exists(R('Empty', 'm1')))

    # ---- delete
    outside = tempfile.mkdtemp(); Path(outside, 'keep.txt').write_bytes(b'k')
    os.makedirs(R('Del', 'a', 'b')); Path(R('Del', 'a', 'b', 'f')).write_bytes(b'f'); Path(R('Del', '.hid')).write_bytes(b'h')
    os.makedirs(R('Del', '.hidden dir')); Path(R('Del', '.hidden dir', 'z')).write_bytes(b'z')
    os.symlink(outside, R('Del', 'link'))
    Path(R('one.txt')).write_bytes(b'1'); Path(R('two.txt')).write_bytes(b'2')
    r = c.post('delete', form=[('path', '/Del'), ('path', '/one.txt')])
    expect('delete', r['status'] == 200 and js(r) == {'deleted': 2} and not os.path.exists(R('Del')) and not os.path.exists(R('one.txt')), r['body'])
    expect('delete did not follow the symlink', Path(outside, 'keep.txt').read_bytes() == b'k')
    shutil.rmtree(outside)
    expect('delete root 403', c.post('delete', form=[('path', '/')])['status'] == 403 and os.path.isdir(R('Music')))
    expect('delete hidden 403', c.post('delete', form=[('path', '/.m1plus')])['status'] == 403 and os.path.isdir(R('.m1plus')))
    expect('delete traversal 400', c.post('delete', form=[('path', '/Empty/../Music')])['status'] == 400 and os.path.isdir(R('Music')))
    expect('delete missing 404, nothing deleted', c.post('delete', form=[('path', '/two.txt'), ('path', '/nope')])['status'] == 404 and os.path.exists(R('two.txt')))
    expect('delete none 400', c.post('delete')['status'] == 400)
    expect('delete symlink itself 403', c.post('delete', form=[('path', '/Music/evil')])['status'] == 403 and os.path.islink(R('Music', 'evil')))
    os.makedirs(R('Many'))
    for i in range(300): Path(R('Many', 'file number %04d with a longish name.txt' % i)).write_bytes(b'x')
    names = ['/Many/' + n for n in os.listdir(R('Many'))]
    r = c.post('delete', form=[('path', n) for n in names])
    expect('delete 300 in one body', r['status'] == 200 and js(r)['deleted'] == 300 and os.listdir(R('Many')) == [], r['body'][:100])
    deep_dir = R('Deep'); os.makedirs(deep_dir)
    p = deep_dir
    for i in range(30): p = os.path.join(p, 'd%d' % i); os.mkdir(p)
    expect('delete deep tree', c.post('delete', form=[('path', '/Deep')])['status'] == 200 and not os.path.exists(R('Deep')))

    # ---- upload
    def up(name, data, conflict=None, path='/Music', ctype='application/octet-stream', extra=(), length=None):
        q = [('path', path), ('name', name)] + ([('conflict', conflict)] if conflict else []) + list(extra)
        return c.call('upload', q, method='POST', body=data, ctype=ctype, length=length)

    r = up('new.flac', b'N' * 100000)
    expect('upload', r['status'] == 200 and js(r) == {'name': 'new.flac', 'size': 100000} and Path(R('Music', 'new.flac')).read_bytes() == b'N' * 100000, r['body'])
    expect('upload leaves no part', not [n for n in os.listdir(R('Music')) if n.endswith('.part')])
    expect('upload empty', up('empty.bin', b'')['status'] == 200 and os.path.getsize(R('Music', 'empty.bin')) == 0)
    r = up('new.flac', b'second')
    expect('upload exists fails 409', r['status'] == 409 and Path(R('Music', 'new.flac')).read_bytes() == b'N' * 100000 and 'error' in js(r))
    expect('upload explicit fail 409', up('new.flac', b'x', 'fail')['status'] == 409)
    expect('upload replace', js(up('new.flac', b'second', 'replace')) == {'name': 'new.flac', 'size': 6} and Path(R('Music', 'new.flac')).read_bytes() == b'second')
    expect('upload keep', js(up('new.flac', b'three', 'keep'))['name'] == 'new 2.flac' and js(up('new.flac', b'four', 'keep'))['name'] == 'new 3.flac'
           and Path(R('Music', 'new 2.flac')).read_bytes() == b'three' and Path(R('Music', 'new.flac')).read_bytes() == b'second')
    expect('upload keep no extension', js(up('README', b'1'))['name'] == 'README' and js(up('README', b'2', 'keep'))['name'] == 'README 2')
    expect('upload keep dotted', js(up('a.tar.gz', b'1'))['name'] == 'a.tar.gz' and js(up('a.tar.gz', b'2', 'keep'))['name'] == 'a.tar 2.gz')
    expect('upload over a folder 409', up('Album', b'x', 'replace')['status'] == 409 and os.path.isdir(R('Music', 'Album')))
    expect('upload keep beside a folder', js(up('Album', b'x', 'keep'))['name'] == 'Album 2' and os.path.isdir(R('Music', 'Album')))
    expect('upload bad conflict 400', up('q', b'x', 'overwrite')['status'] == 400)
    expect('upload utf8 name', js(up('日本語.flac', b'jp'))['name'] == '日本語.flac' and os.path.exists(R('Music', '日本語.flac')))
    for bad in ('', 'a/b', '..', '.', '.hidden', '.x.part', 'x' * 241):
        expect(f'upload name {bad!r} 400', up(bad, b'x')['status'] == 400)
    expect('upload no name 400', c.call('upload', [('path', '/')], method='POST', body=b'x', ctype='application/octet-stream')['status'] == 400)
    expect('upload folder missing 404', up('x', b'x', path='/nope')['status'] == 404)
    expect('upload into file 400', up('x', b'x', path='/Renamed.txt')['status'] == 400)
    expect('upload into hidden 403', up('x', b'x', path='/.m1plus')['status'] == 403)
    expect('upload via symlink 403', up('x', b'x', path='/Music/evil')['status'] == 403)
    expect('upload needs content type', up('x', b'x', ctype=None)['status'] == 403)
    expect('upload form type 403', up('x', b'x', ctype='multipart/form-data; boundary=a')['status'] == 403)
    r = c.call('upload', [('path', '/Music'), ('name', 'nolen')], method='POST', body=b'abc', ctype='application/octet-stream', length=None)
    expect('upload content length from body', r['status'] == 200)
    env = c.env('upload', 'POST', [('path', '/Music'), ('name', 'nolen2')], 'application/octet-stream', None)
    r = parse_response(subprocess.run([c.exe], env=env, input=b'abc', capture_output=True).stdout, 0)
    expect('upload without Content-Length 400', r['status'] == 400 and not os.path.exists(R('Music', 'nolen2')))
    r = up('short.bin', b'x' * 1000, length=5000)
    expect('upload interrupted removes the part', r['status'] == 400 and not os.path.exists(R('Music', 'short.bin')) and not os.path.exists(R('Music', '.short.bin.part')), r['body'])
    Path(R('Music', 'keepme.bin')).write_bytes(b'precious')
    r = up('keepme.bin', b'x' * 10, 'replace', length=500)
    expect('interrupted replace keeps the old file', r['status'] == 400 and Path(R('Music', 'keepme.bin')).read_bytes() == b'precious' and not os.path.exists(R('Music', '.keepme.bin.part')))
    expect('upload bad length 400', up('x', b'x', length='abc')['status'] == 400)
    Path(R('Music', '.stale.bin.part')).write_bytes(b'stale partial')
    expect('stale part is replaced', up('stale.bin', b'fresh')['status'] == 200 and Path(R('Music', 'stale.bin')).read_bytes() == b'fresh' and not os.path.exists(R('Music', '.stale.bin.part')))
    huge = os.urandom(5 * 1024 * 1024 + 3)
    expect('upload 5 MB', up('huge.bin', huge)['status'] == 200 and Path(R('Music', 'huge.bin')).read_bytes() == huge)
    # chunked
    a, b_, c_ = os.urandom(70000), os.urandom(65536), os.urandom(11)
    r1 = up('chunks.bin', a, extra=[('offset', '0')])
    expect('chunk 1', r1['status'] == 200 and js(r1) == {'size': 70000} and os.path.exists(R('Music', '.chunks.bin.part')) and not os.path.exists(R('Music', 'chunks.bin')), r1['body'])
    expect('chunk wrong offset 409', up('chunks.bin', b_, extra=[('offset', '123')])['status'] == 409)
    expect('chunk offset without part 409', up('nopart.bin', b_, extra=[('offset', '5')])['status'] == 409)
    r2 = up('chunks.bin', b_, extra=[('offset', '70000')])
    expect('chunk 2', js(r2) == {'size': 135536})
    r3 = up('chunks.bin', c_, extra=[('offset', '135536'), ('last', '1')])
    expect('chunk last', r3['status'] == 200 and js(r3) == {'name': 'chunks.bin', 'size': 135547} and Path(R('Music', 'chunks.bin')).read_bytes() == a + b_ + c_
           and not os.path.exists(R('Music', '.chunks.bin.part')), r3['body'])
    expect('chunk 1 conflict fails early', up('chunks.bin', a, extra=[('offset', '0')])['status'] == 409)
    up('ck.bin', b'1' * 10, extra=[('offset', '0')])
    r = up('ck.bin', b'2' * 10, 'keep', extra=[('offset', '10'), ('last', '1')])
    expect('chunk last single', js(r) == {'name': 'ck.bin', 'size': 20})
    up('ck.bin', b'1' * 10, 'replace', extra=[('offset', '0')])
    r = up('ck.bin', b'2' * 10, 'replace', extra=[('offset', '10'), ('last', '1')])
    expect('chunk replace', js(r)['name'] == 'ck.bin' and Path(R('Music', 'ck.bin')).read_bytes() == b'1' * 10 + b'2' * 10)
    up('cs.bin', b'1' * 10, extra=[('offset', '0')])
    r = up('cs.bin', b'2' * 10, extra=[('offset', '10'), ('last', '1'), ('conflict', 'fail')], length=30)
    expect('chunk interrupted removes the part', r['status'] == 400 and not os.path.exists(R('Music', '.cs.bin.part')) and not os.path.exists(R('Music', 'cs.bin')))
    expect('chunk bad offset 400', up('x', b'x', extra=[('offset', 'zz')])['status'] == 400)

    # ---- hidden=1: dot names are reachable; /.m1plus is read-only; the API still never creates a dot name
    H = [('hidden', '1')]
    os.makedirs(R('Hid', '.sub'))
    for n, d in (('Hid/vis.txt', b'v'), ('Hid/.dot.txt', b'dot'), ('Hid/._vis.txt', b'ad'), ('Hid/.x.bin.part', b'p'),
                 ('Hid/.sub/in.txt', b'in'), ('Hid/.sub/.deep', b'dp')):
        Path(R(n)).write_bytes(d)
    hl = listing(c, '/Hid')
    expect('hidden off: list skips dot names', sorted(hl) == ['vis.txt'], sorted(hl))
    r = c.call('list', [('path', '/Hid'), *H])
    hl = {e['name']: e for e in js(r)['entries']}
    expect('hidden on: list has dot names', sorted(hl) == ['._vis.txt', '.dot.txt', '.sub', '.x.bin.part', 'vis.txt'], sorted(hl))
    expect('hidden on: folder count includes dot names', hl['.sub']['items'] == 2 and hl['.sub']['dir'], hl['.sub'])
    expect('hidden off: folder count skips dot names', listing(c, '/Hid')['vis.txt']['size'] == 1 and
           next(e for e in js(c.call('list', [('path', '/')]))['entries'] if e['name'] == 'Hid')['items'] == 1)
    expect('hidden on: root lists .m1plus', '.m1plus' in {e['name'] for e in js(c.call('list', [('path', '/'), *H]))['entries']})
    expect('hidden on: list a dot folder', sorted(e['name'] for e in js(c.call('list', [('path', '/Hid/.sub'), *H]))['entries']) == ['.deep', 'in.txt'])
    expect('hidden=0 is off', c.call('list', [('path', '/Hid/.sub'), ('hidden', '0')])['status'] == 403)
    expect('hidden off: dot path 403', c.call('download', [('path', '/Hid/.dot.txt')])['status'] == 403)
    for bad in ('/Hid/.', '/Hid/..', '/Hid/.sub/..'):
        expect(f'hidden on: {bad!r} 400', c.call('list', [('path', bad), *H])['status'] == 400)
    r = c.call('download', [('path', '/Hid/.dot.txt'), *H])
    expect('hidden on: download a dot file', r['status'] == 200 and r['body'] == b'dot' and b'filename="' + b'.dot.txt' in r['headers']['Content-Disposition'].encode(), r['status'])
    r = c.call('tar', [('path', '/Hid'), *H])
    tf = tarfile.open(fileobj=io.BytesIO(r['body']))
    expect('hidden on: tar includes dot names', sorted(tf.getnames()) == sorted(['Hid', 'Hid/vis.txt', 'Hid/.dot.txt', 'Hid/._vis.txt',
           'Hid/.x.bin.part', 'Hid/.sub', 'Hid/.sub/in.txt', 'Hid/.sub/.deep']), tf.getnames())
    tf = tarfile.open(fileobj=io.BytesIO(c.call('tar', [('path', '/Hid')])['body']))
    expect('hidden off: tar skips dot names', sorted(tf.getnames()) == ['Hid', 'Hid/vis.txt'], tf.getnames())
    expect('hidden on: tar of a dot folder', '.sub/.deep' in tarfile.open(fileobj=io.BytesIO(c.call('tar', [('path', '/Hid/.sub'), *H])['body'])).getnames())
    # delete
    expect('hidden off: delete dot file 403', c.post('delete', form=[('path', '/Hid/._vis.txt')])['status'] == 403 and os.path.exists(R('Hid', '._vis.txt')))
    r = c.post('delete', form=[('path', '/Hid/._vis.txt'), ('path', '/Hid/.x.bin.part'), *H])
    expect('hidden on: delete ._ and .part files', r['status'] == 200 and js(r) == {'deleted': 2} and
           not os.path.exists(R('Hid', '._vis.txt')) and not os.path.exists(R('Hid', '.x.bin.part')), r['body'])
    r = c.post('delete', form=[('path', '/Hid/.sub'), *H])
    expect('hidden on: delete a dot folder', r['status'] == 200 and not os.path.exists(R('Hid', '.sub')), r['body'])
    # rename: a dot source is fine, a dot target never
    expect('hidden off: rename dot source 403', c.post('rename', form=[('path', '/Hid/.dot.txt'), ('name', 'plain.txt')])['status'] == 403)
    r = c.post('rename', form=[('path', '/Hid/.dot.txt'), ('name', 'plain.txt'), *H])
    expect('hidden on: rename a dot source', r['status'] == 200 and Path(R('Hid', 'plain.txt')).read_bytes() == b'dot' and not os.path.exists(R('Hid', '.dot.txt')), r['body'])
    for q in (c.post('rename', form=[('path', '/Hid/plain.txt'), ('name', '.dot.txt'), *H]),
              c.post('mkdir', form=[('path', '/Hid'), ('name', '.newdir'), *H]),
              up('.up.bin', b'x', path='/Hid', extra=H)):
        expect('hidden on: dot target 400', q['status'] == 400 and 'dot' in js(q)['error'], q['body'])
    expect('hidden on: dot target left nothing', sorted(os.listdir(R('Hid'))) == ['plain.txt', 'vis.txt'], os.listdir(R('Hid')))
    # .m1plus: readable, never writable
    r = c.call('download', [('path', '/.m1plus/db'), *H])
    expect('.m1plus download', r['status'] == 200 and r['body'] == b'secret')
    expect('.m1plus tar', b'secret' in c.call('tar', [('path', '/.m1plus'), *H])['body'])
    expect('.m1plus list', [e['name'] for e in js(c.call('list', [('path', '/.m1plus'), *H]))['entries']] == ['db'])
    # The SD card is case-insensitive on the player. Keep a case-distinct host fixture so the
    # reserved-path guard is exercised on this case-sensitive test filesystem too.
    os.mkdir(R('.M1PLUS'))
    Path(R('.M1PLUS', 'db')).write_bytes(b'case alias')
    ro = []
    for op, form in (('delete', [('path', '/.m1plus/db')]), ('delete', [('path', '/.m1plus')]), ('delete', [('path', '/.M1PLUS/db')]),
                     ('rename', [('path', '/.m1plus/db'), ('name', 'db2')]), ('rename', [('path', '/.m1plus'), ('name', 'other')]),
                     ('mkdir', [('path', '/.m1plus'), ('name', 'sub')]), ('move', [('path', '/Hid/vis.txt'), ('to', '/.m1plus')]),
                     ('move', [('path', '/.m1plus/db'), ('to', '/Hid')])):
        r = c.post(op, form=[*form, *H])
        ro.append(r['status'] == 403 and 'read-only' in js(r)['error'])
    expect('.m1plus refuses delete, rename, mkdir, move', all(ro), ro)
    body = b'data'
    r = c.call('upload', [('path', '/.m1plus'), ('name', 'u.bin'), *H], method='POST', body=body, ctype='application/octet-stream')
    expect('.m1plus refuses upload', r['status'] == 403 and 'read-only' in js(r)['error'] and not os.path.exists(R('.m1plus', 'u.bin')), r['body'])
    expect('.m1plus untouched', os.listdir(R('.m1plus')) == ['db'] and Path(R('.m1plus', 'db')).read_bytes() == b'secret')
    expect('.M1PLUS case alias untouched', os.listdir(R('.M1PLUS')) == ['db'] and Path(R('.M1PLUS', 'db')).read_bytes() == b'case alias')

    # ---- the card is never left with a stray part file after all of the above
    stray = [os.path.join(d, n) for d, _, fs in os.walk(c.root) for n in fs if n.endswith('.part')]
    expect('no stray parts', not stray, stray)
    # ---- nothing outside the root was touched
    expect('root intact', os.path.isdir(R('.m1plus')) and Path(R('.m1plus', 'db')).read_bytes() == b'secret')
    return c


# ---- the MIPS executable under Unicorn


def mips_run(exe, root, env, body):
    """Run the static MIPS CGI in Unicorn: raw system calls answered from the host directory root (its /mnt/mmc)."""
    from unicorn import Uc, UC_ARCH_MIPS, UC_MODE_MIPS32, UC_MODE_LITTLE_ENDIAN, UC_HOOK_INTR, UC_PROT_ALL
    from unicorn.mips_const import UC_MIPS_REG_SP, UC_MIPS_REG_V0, UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3
    data = open(exe, 'rb').read()
    e_entry, e_phoff = struct.unpack_from('<II', data, 24)[0], struct.unpack_from('<I', data, 28)[0]
    phentsize, phnum = struct.unpack_from('<HH', data, 42)
    u = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN)
    for i in range(phnum):
        t, off, va, _, filesz, memsz, flags, _ = struct.unpack_from('<8I', data, e_phoff + i * phentsize)
        if t != 1: continue
        lo, hi = va & ~0xfff, (va + memsz + 0xfff) & ~0xfff
        try: u.mem_map(lo, hi - lo, UC_PROT_ALL)
        except Exception: pass   # overlaps the previous segment's last page
        u.mem_write(va, data[off:off + filesz])
    STACK = 0x7ff00000
    u.mem_map(STACK - 0x100000, 0x200000, UC_PROT_ALL)
    addr = STACK + 0x1000
    ptrs = []
    for s in ['api.cgi'] + [f'{k}={v}' for k, v in env.items()]:
        b = s.encode() + b'\0'; u.mem_write(addr, b); ptrs.append(addr); addr += len(b)
    argv, envp = ptrs[:1], ptrs[1:]
    sp = STACK - 0x1000
    vec = struct.pack('<I', 1) + struct.pack('<I', argv[0]) + b'\0\0\0\0' + b''.join(struct.pack('<I', p) for p in envp) + b'\0\0\0\0'
    u.mem_write(sp, vec)
    u.reg_write(UC_MIPS_REG_SP, sp)
    out = bytearray()
    stdin = bytearray(body)
    fds = {}      # guest fd -> [host fd, path, dir listing]
    nextfd = [3]
    RENAMES.clear()
    result = {'exit': None}

    def tr(p):
        s = p.decode()
        assert s == '/mnt/mmc' or s.startswith('/mnt/mmc/'), s
        return root + s[len('/mnt/mmc'):]

    def cstr(a):
        b = bytearray()
        while True:
            ch = u.mem_read(a, 1)[0]
            if not ch: return bytes(b)
            b.append(ch); a += 1

    def err(e): return (e.errno, True)

    def sysc(uc, intno, _):
        nr = uc.reg_read(UC_MIPS_REG_V0)
        a = [uc.reg_read(r) for r in (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3)]
        sp_ = uc.reg_read(UC_MIPS_REG_SP)
        a5 = struct.unpack('<I', bytes(uc.mem_read(sp_ + 16, 4)))[0]
        ret, bad = 0, False
        try:
            if nr == 4246:
                result['exit'] = a[0]; uc.emu_stop(); return
            elif nr == 4003:   # read
                n = a[2]
                if a[0] == 0:
                    chunk = bytes(stdin[:n]); del stdin[:n]
                else: chunk = os.read(fds[a[0]][0], n)
                uc.mem_write(a[1], chunk); ret = len(chunk)
            elif nr == 4004:   # write
                chunk = bytes(uc.mem_read(a[1], a[2]))
                if a[0] == 1: out.extend(chunk)
                else: os.write(fds[a[0]][0], chunk)
                ret = len(chunk)
            elif nr == 4005:   # open (o32 flag values)
                p = tr(cstr(a[0])); f = a[1]
                hf = (os.O_WRONLY if f & 1 else os.O_RDONLY) | (os.O_APPEND if f & 8 else 0) | (os.O_CREAT if f & 0x100 else 0) | (os.O_TRUNC if f & 0x200 else 0) \
                    | (os.O_DIRECTORY if f & 0x10000 else 0) | (os.O_NOFOLLOW if f & 0x20000 else 0)
                assert f & 0x2000, 'O_LARGEFILE missing'
                fd = os.open(p, hf, a[2])
                fds[nextfd[0]] = [fd, p, None]; ret = nextfd[0]; nextfd[0] += 1
            elif nr == 4006:
                os.close(fds.pop(a[0])[0])
            elif nr == 4010: os.unlink(tr(cstr(a[0])))
            elif nr == 4038: RENAMES.append((cstr(a[0]).decode(), cstr(a[1]).decode())); os.rename(tr(cstr(a[0])), tr(cstr(a[1])))
            elif nr == 4039: os.mkdir(tr(cstr(a[0])), a[1])
            elif nr == 4040: os.rmdir(tr(cstr(a[0])))
            elif nr == 4118: os.fsync(fds[a[0]][0])
            elif nr == 4099:   # statfs: o32 struct statfs
                assert tr(cstr(a[0])) == root
                st = struct.pack('<8I', 0x4d44, 4096, 4096, 1000000, 400000, 0, 0, 300000) + bytes(36)
                uc.mem_write(a[1], st)
            elif nr == 4219:   # getdents64
                ent = fds[a[0]]
                if ent[2] is None: ent[2] = ['.', '..'] + sorted(os.listdir(ent[1]))
                buf = b''
                while ent[2]:
                    nm = ent[2][0].encode() + b'\0'
                    rl = (19 + len(nm) + 7) & ~7
                    if len(buf) + rl > a[2]: break
                    full = os.path.join(ent[1], ent[2][0])
                    dt = 4 if os.path.isdir(full) else 8
                    buf += struct.pack('<QqHB', 1, 1, rl, dt) + nm + bytes(rl - 19 - len(nm))
                    ent[2].pop(0)
                uc.mem_write(a[1], buf); ret = len(buf)
            elif nr == 4366:   # statx(AT_FDCWD, path, flags, mask, buf)
                assert a[0] == 0xffffff9c and a[2] & 0x100
                s = os.lstat(tr(cstr(a[1])))
                x = bytearray(256)
                struct.pack_into('<IIQ', x, 0, 0x241, 4096, 0); struct.pack_into('<H', x, 28, s.st_mode & 0xffff)
                struct.pack_into('<Q', x, 40, s.st_size); struct.pack_into('<qI', x, 112, int(s.st_mtime), 0)
                uc.mem_write(a5, bytes(x))
            else: raise AssertionError(f'unexpected syscall {nr}')
        except OSError as e:
            ret, bad = e.errno, True
        if bad:
            import errno as E
            mips = {E.ENOENT: 2, E.EEXIST: 17, E.ENOTDIR: 20, E.EISDIR: 21, E.ENOTEMPTY: 93, E.EINVAL: 22, E.ENOSPC: 28, E.EACCES: 13, E.EXDEV: 18}
            ret = mips.get(ret, 5)
        uc.reg_write(UC_MIPS_REG_V0, ret); uc.reg_write(UC_MIPS_REG_A3, 1 if bad else 0)

    u.hook_add(UC_HOOK_INTR, sysc)
    u.emu_start(e_entry, 0, timeout=120 * 1000000, count=400000000)
    assert result['exit'] is not None, 'the MIPS program did not exit'
    return parse_response(bytes(out), result['exit'])


def canon(op, body):
    """A response body without what legitimately differs between the two builds: directory order, the df numbers."""
    if op == 'list' and body.startswith(b'{"path"'):
        j = json.loads(body); j['entries'].sort(key=lambda e: e['name']); return j
    if op == 'df': return {k: v > 0 for k, v in json.loads(body).items()}
    if op == 'tar':
        with tarfile.open(fileobj=io.BytesIO(body)) as t:
            return sorted((m.name, m.type, m.size, m.mtime, m.mode, t.extractfile(m).read() if m.isfile() else b'') for m in t.getmembers())
    return body


def mips_tests(td, host):
    exe = os.path.join(td, 'api.mips')
    open(exe, 'wb').write(mod_webapp.build_cgi())
    # a fresh card for the scripted session, the same one for the host build and the MIPS build
    def card(name):
        d = os.path.join(td, name, 'mmc'); os.makedirs(d + '/Music/Album'); os.makedirs(d + '/.m1plus')
        Path(d, 'Music', 'a.flac').write_bytes(b'A' * 3000)
        Path(d, 'Music', 'Album', 't.mp3').write_bytes(bytes(range(256)) * 10)
        Path(d, '日本 "q".txt').write_bytes(b'jp')
        Path(d, '.m1plus', 'x').write_bytes(b'x')
        for f in Path(d).rglob('*'): os.utime(f, (1700000000, 1700000000))
        return d
    sessions = [
        ('list', 'GET', [('path', '/')], b'', None), ('list', 'GET', [('path', '/Music')], b'', None), ('df', 'GET', [], b'', None),
        ('download', 'GET', [('path', '/Music/a.flac')], b'', None), ('download', 'GET', [('path', '/日本 "q".txt')], b'', None),
        ('tar', 'GET', [('path', '/Music'), ('path', '/日本 "q".txt')], b'', None),
        ('list', 'GET', [('path', '/../etc')], b'', None), ('list', 'GET', [('path', '/.m1plus')], b'', None),
        ('mkdir', 'POST', [('path', '/Music'), ('name', 'New')], b'', 'application/octet-stream'),
        ('mkdir', 'POST', [('path', '/Music'), ('name', 'New')], b'', 'application/octet-stream'),
        ('rename', 'POST', [('path', '/Music/New'), ('name', 'Newer')], b'', 'application/octet-stream'),
        ('upload', 'POST', [('path', '/Music/Newer'), ('name', 'up.bin')], os.urandom(100000), 'application/octet-stream'),
        ('upload', 'POST', [('path', '/Music/Newer'), ('name', 'up.bin'), ('conflict', 'keep')], b'second', 'application/octet-stream'),
        ('upload', 'POST', [('path', '/Music/Newer'), ('name', 'up.bin')], b'third', 'application/octet-stream'),
        ('upload', 'POST', [('path', '/Music/Newer'), ('name', 'c.bin'), ('offset', '0')], b'1' * 70000, 'application/octet-stream'),
        ('upload', 'POST', [('path', '/Music/Newer'), ('name', 'c.bin'), ('offset', '70000'), ('last', '1')], b'2' * 70000, 'application/octet-stream'),
        ('move', 'POST', [('to', '/Music/Newer'), ('conflict', 'keep'), ('path', '/Music/a.flac')], b'', 'application/octet-stream'),
        ('delete', 'POST', [('path', '/Music/Newer'), ('path', '/日本 "q".txt')], b'', 'application/octet-stream'),
        ('list', 'GET', [('path', '/')], b'', None),
    ]
    hd, md = card('host'), card('mips')
    hostc = Cgi(os.path.join(td, 'hostbin'))   # rooted at its own directory: replace its card with hd
    shutil.rmtree(hostc.root); shutil.copytree(hd, hostc.root, symlinks=True)
    for f in Path(hostc.root).rglob('*'): os.utime(f, (1700000000, 1700000000))
    same = 0
    for i, (op, method, q, body, ct) in enumerate(sessions):
        h = hostc.call(op, q, method=method, body=body, ctype=ct)
        env = hostc.env(op, method, q, ct, len(body) if method == 'POST' else None)
        env.pop('ASAN_OPTIONS')
        m = mips_run(exe, md, env, body)
        if h['status'] != m['status'] or h['headers'] != m['headers'] or canon(op, h['body']) != canon(op, m['body']):
            expect(f'mips session {i} {op} matches the host build', False, f'host={h["status"]} {h["body"][:80]!r} mips={m["status"]} {m["body"][:80]!r} {m["headers"]}')
        else: same += 1
    # a case-only rename goes through a hidden temporary name (exFAT keeps the old case otherwise)
    Path(md, 'Music', 'Small.bin').write_bytes(b's')
    env = hostc.env('rename', 'POST', [('path', '/Music/Small.bin'), ('name', 'small.bin')], 'application/octet-stream', 0)
    env.pop('ASAN_OPTIONS')
    m = mips_run(exe, md, env, b'')
    Path(hostc.root, 'Music', 'Small.bin').write_bytes(b's')
    hostc.call('rename', [('path', '/Music/Small.bin'), ('name', 'small.bin')], method='POST', ctype='application/octet-stream')
    expect('mips case-only rename answers', m['status'] == 200 and json.loads(m['body']) == {'name': 'small.bin'}, m['body'])
    expect('mips case-only rename uses a temporary name', len(RENAMES) == 2 and RENAMES[0][0] == '/mnt/mmc/Music/Small.bin' and RENAMES[0][1] == RENAMES[1][0]
           and RENAMES[0][1].startswith('/mnt/mmc/Music/.rename') and RENAMES[1][1] == '/mnt/mmc/Music/small.bin', RENAMES)
    expect('mips case-only rename ends with the new case', 'small.bin' in os.listdir(Path(md, 'Music')) and not [n for n in os.listdir(Path(md, 'Music')) if n.startswith('.rename')])
    expect('mips session answers like the host build', same == len(sessions), f'{same}/{len(sessions)}')
    expect('mips card equals host card', sorted(str(p.relative_to(hostc.root)) for p in Path(hostc.root).rglob('*')) == sorted(str(p.relative_to(md)) for p in Path(md).rglob('*')))


# ---- the built tree


def elf_checks(path):
    d = open(path, 'rb').read()
    expect('elf magic 32-bit LE', d[:4] == b'\x7fELF' and d[4] == 1 and d[5] == 1)
    e_type, e_machine = struct.unpack_from('<HH', d, 16)
    e_flags = struct.unpack_from('<I', d, 36)[0]
    e_phoff = struct.unpack_from('<I', d, 28)[0]
    phentsize, phnum = struct.unpack_from('<HH', d, 42)
    types = [struct.unpack_from('<I', d, e_phoff + i * phentsize)[0] for i in range(phnum)]
    expect('elf is a MIPS executable', e_type == 2 and e_machine == 8, (e_type, e_machine))
    expect('elf flags: o32, mips32r2, NaN 2008, no FP64', e_flags & 0x70000000 == 0x50000000 or e_flags >> 28 == 7, hex(e_flags))
    expect('elf o32 abi', e_flags & 0x1000 and not e_flags & 0x20 and not e_flags & 0x200, hex(e_flags))
    expect('elf nan2008 like stock', e_flags & 0x400, hex(e_flags))
    expect('elf is static: no interpreter, no dynamic section', 3 not in types and 2 not in types, types)
    expect('elf has no libc symbol imports', b'GLIBC' not in d and b'libc.so' not in d and b'ld-linux' not in d)
    expect('elf is small', len(d) < 40000, len(d))


def tree_checks(tree, stock):
    web = Path(tree, 'rootfs', mod_webapp.WEB)
    sweb = Path(stock, 'rootfs', mod_webapp.WEB)
    cgi = Path(tree, 'rootfs', mod_webapp.CGI)
    expect('api.cgi installed and executable', cgi.is_file() and os.access(cgi, os.X_OK) and cgi.stat().st_mode & 0o777 == 0o755)
    elf_checks(cgi)
    expect('api.cgi is what patch/webapi.c builds', cgi.read_bytes() == mod_webapp.build_cgi())
    left = sorted(str(p.relative_to(web)) for p in web.rglob('*'))
    expect('web root holds only the page, favicon and api.cgi', left == ['cgi-bin', 'cgi-bin/api.cgi', 'favicon.ico', 'index.html'], left)
    expect('stock CGIs and links are gone', not any((web / n).exists() or (web / n).is_symlink() for n in
           [*mod_webapp.STOCK_FILES, *mod_webapp.STOCK_LINKS, *mod_webapp.STOCK_DIRS]))
    expect('favicon is stock', (web / 'favicon.ico').read_bytes() == (sweb / 'favicon.ico').read_bytes())
    page = (web / 'index.html').read_text()
    expect('index.html is the new page', 'api.cgi' in page and 'jquery' not in page.lower() and 'bootstrap' not in page.lower())
    expect('index.html is the built asset', (web / 'index.html').read_bytes() == Path(mod_webapp.INDEX_SRC).read_bytes())
    expect('index.html is not the stock one', (web / 'index.html').read_bytes() != (sweb / 'index.html').read_bytes())
    for rel in ('etc/thttpd.conf', 'usr/bin/thttpd'):
        expect(f'{rel} untouched', Path(tree, 'rootfs', rel).read_bytes() == Path(stock, 'rootfs', rel).read_bytes())
    size = lambda p: sum(f.stat().st_size for f in p.rglob('*') if f.is_file() and not f.is_symlink())
    print(f'web root: stock {size(sweb)} bytes, now {size(web)} bytes')
    expect('web root shrank', size(web) < size(sweb) - 550000, (size(web), size(sweb)))
    listed = {ln.split(None, 5)[5].rstrip('\n') for ln in open(Path(stock, 'stock.lln'), encoding='utf-8', errors='replace') if len(ln.split(None, 5)) == 6}
    expect('removed list names stock entries as fwtool lists them', all('/' + r in listed for r in mod_webapp.removed_rels()), [r for r in mod_webapp.removed_rels() if '/' + r not in listed])
    expect('removed list is stock entries', all((sweb / n).exists() or (sweb / n).is_symlink() for n in [r[len(mod_webapp.WEB) + 1:].split(' -> ')[0] for r in mod_webapp.removed_rels()]))


# ---- the page (assets/webapp/index.html): self-contained, one string table


# the page's locale codes, in pod_i18n.LOCALES order
PAGE_LOCALES = ['en', 'zh', 'zh-HK', 'ja', 'ko', 'fr', 'de', 'es', 'it', 'th', 'pl', 'ru', 'uk']
# string keys that reuse an existing translation of the mod: key -> pod_i18n.TEXT key
SHARED = {'search': 'Search', 'size': 'Size', 'download': 'Download', 'del': 'Delete', 'info': 'Get Info', 'cancel': 'Cancel',
          'waiting': 'Waiting', 'done': 'Done', 'cancelled': 'Cancelled'}
API_OPS = {'list', 'df', 'download', 'tar', 'mkdir', 'rename', 'move', 'delete', 'upload'}


def page_checks():
    page = Path(mod_webapp.INDEX_SRC).read_text(encoding='utf-8')
    expect('page is small', len(page.encode()) < 100000, len(page.encode()))
    expect('page has no external URL', not re.search(r'https?:|//[a-z]|@import|url\(|<link|<img|src=["\']?[^"\' >]', page, re.I), re.findall(r'https?:\S*|<link|<img', page)[:3])
    expect('page title and subtitle', '<title>M1 Plus</title>' in page and 'Wi-Fi Transfer' in page)
    expect('page names no other product', not re.search(r'q2|apple|ipod|mockup|simulate', page.replace('-apple-system', ''), re.I))
    m = re.search(r'const STR = (\{.*?\n\});', page, re.S)
    expect('page has a string table', bool(m))
    if not m: return
    strs = json.loads(m.group(1))
    expect('page locales are the mod\'s 13', list(strs) == PAGE_LOCALES and len(PAGE_LOCALES) == len(pod_i18n.LOCALES))
    en = strs['en']
    holes = [(l, k) for l in strs for k in en if not strs[l].get(k)]
    expect('every string exists in every language', not holes and all(set(strs[l]) == set(en) for l in strs), holes[:5])
    ph = lambda x: sorted(re.findall(r'\{\w+\}', x))
    expect('placeholders match English', all(ph(strs[l][k]) == ph(en[k]) for l in strs for k in en), [(l, k) for l in strs for k in en if ph(strs[l][k]) != ph(en[k])][:5])
    cjk = re.compile(r'[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af\u0e00-\u0e7f\u0400-\u04ff]')
    expect('no CJK, Thai or Cyrillic in English', not any(cjk.search(v) for v in en.values()))
    expect('other languages differ from English where they must', all(strs[l]['newFolder'] != en['newFolder'] for l in strs if l != 'en'))
    expect('shared words equal the mod\'s translations',
           all(strs[l][k] == pod_i18n.TEXT[v][loc] for k, v in SHARED.items() for l, loc in zip(PAGE_LOCALES, pod_i18n.LOCALES)),
           [(l, k) for k, v in SHARED.items() for l, loc in zip(PAGE_LOCALES, pod_i18n.LOCALES) if strs[l][k] != pod_i18n.TEXT[v][loc]][:5])
    used = set(re.findall(r'\bt\("(\w+)"', page))
    expect('every t("key") exists', used <= set(en), sorted(used - set(en)))
    expect('every string is used', set(en) <= used, sorted(set(en) - used))
    for k in ('auto', 'language', 'themeAuto', 'themeLight', 'themeDark'):
        expect(f'every language has the {k} string', all(strs[l].get(k) for l in strs))
    head = page.split('<style>')[0]
    expect('a head script sets the saved theme before first paint', 'localStorage.getItem("wt-theme")' in head and 'dataset.theme' in head)
    expect('dark variables follow data-theme', ':root:not([data-theme])' in page and ':root[data-theme=dark]' in page and ':root[data-theme=light]' in page)
    expect('language picker and theme button exist', 'id="langsel"' in page and 'id="theme"' in page
           and all(f'"{c}"' in page.split('const LANGS')[1].split(']];')[0] for c in strs))
    expect('storage access is guarded', all(re.search(r'try \{[^}]*localStorage', ln) for ln in page.splitlines() if 'localStorage' in ln))
    ops = set(re.findall(r'api\("(\w+)"', page)) | set(re.findall(r'op=(\w+)', page))
    expect('page calls only known ops', ops <= API_OPS, sorted(ops - API_OPS))
    dlg = re.search(r'function dialog\(.*?\n}\n', page, re.S)
    expect('dialog dismissal (Escape, outside click, close button) calls onDismiss', bool(dlg) and 'onDismiss' in dlg.group(0)
           and 'Escape' in dlg.group(0) and dlg.group(0).count('dismiss()') >= 2)
    expect('dialog hears Escape on the document (focus may be outside it)', bool(dlg) and 'document.addEventListener("keydown"' in dlg.group(0)
           and 'document.removeEventListener("keydown"' in dlg.group(0))
    cf = re.search(r'function conflict\(.*?\n}\n', page, re.S)
    expect('dismissing the conflict dialog settles the promise as skip', bool(cf) and re.search(r'\(\) => res\("skip"\)\)\)', cf.group(0)))
    expect('every mutating request is a POST with the octet-stream type', 'application/octet-stream' in page and page.count('"Content-Type"') == 2)


def main():
    with tempfile.TemporaryDirectory() as td:
        c = host_tests(td)
        try: import unicorn   # noqa: F401
        except ImportError: print('skip: no unicorn'); unicorn = None
        if unicorn: mips_tests(td, c)
    page_checks()
    if len(sys.argv) >= 3: tree_checks(sys.argv[1], sys.argv[2])
    print(f'{ok} passed, {fail} failed')
    return 1 if fail else 0


if __name__ == '__main__': sys.exit(main())
