#!/usr/bin/env python3
"""Tests of the build tooling itself (no firmware needed): fwtool's package verification on synthetic
update files and check.py's pass/fail/--update decisions.

  uv run python -I test/tools.py
"""
import argparse, contextlib, hashlib, io, os, shutil, signal, subprocess, sys, tarfile, tempfile, threading, time
from pathlib import Path
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import fwtool, check   # noqa: E402
import workflow, buildcache, autotime

ok = fail = 0


def expect(name, cond):
    global ok, fail
    if cond: ok += 1
    else: fail += 1; print(f'FAIL {name}')


def make(path, manifest=None, files=None, extra=(), model='Shanling M1 Plus', dup=None, drop=()):
    """A synthetic update tar. files: payload name -> bytes; manifest: list of lines (default: correct)."""
    files = {'recovery-update/xImage': b'kernel', 'recovery-update/rootfs.squashfs': b'rootfs'} if files is None else files
    if manifest is None:
        manifest = [f'{hashlib.md5(d).hexdigest()}  {n}' for n, d in files.items()]
    info = '\n'.join([model, 'V9.9x'] + manifest) + '\n'
    with tarfile.open(path, 'w') as t:
        def add(name, data, typ=tarfile.REGTYPE):
            ti = tarfile.TarInfo(name); ti.type = typ; ti.size = len(data) if typ == tarfile.REGTYPE else 0
            t.addfile(ti, io.BytesIO(data) if typ == tarfile.REGTYPE else None)
        add(fwtool.INFO_NAME, info.encode())
        add('recovery-update', b'', tarfile.DIRTYPE)
        for n, d in files.items():
            if n not in drop: add(n, d)
        for n in extra: add(n, b'x')
        if dup: add(dup, b'again')


def problems(**kw):
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, 'u.bin'); make(p, **kw)
        return fwtool.verify_package(p)[0]


def workflow_tests():
    def refused(fn):
        try: fn(); return False
        except SystemExit: return True

    # Exercise the gate with a synthetic golden file. No real packages or goldens are changed.
    with tempfile.TemporaryDirectory() as td:
        golden = Path(td) / 'golden'
        def gate(expected=(), tests=(), builds=None, skipped=None, update=False, no_tests=False, sel=()):
            args = argparse.Namespace(expected=list(expected), tests_only=False, update=update, no_tests=no_tests, dev=False)
            with patch.object(check, 'GOLDEN', str(golden)), contextlib.redirect_stdout(io.StringIO()):
                return check.finish(args, list(sel), skipped or {}, {}, builds or {}, list(tests), time.monotonic())
        expect('missing required task fails', gate(expected=['tools']) == 1)
        expect('skipped required build fails', gate(sel=['release'], skipped={'release': 'missing firmware'}) == 1)
        expect('missing required build fails', gate(sel=['release']) == 1)
        builds = {n: {'sha': 'a' * 64} for n in check.TARGETS}
        expect('NEW package requires acceptance', gate(sel=['release'], builds=builds) == 1)
        expect('no-tests cannot accept golden', gate(sel=list(builds), builds=builds, update=True, no_tests=True) == 1 and not golden.exists())
        expect('missing test cannot accept golden', gate(sel=list(builds), builds=builds, update=True, expected=check.ALL_TESTS) == 1 and not golden.exists())
        tests = [{'test': n, 'rc': 0, 'counts': None, 'secs': 0, 'log': ''} for n in check.ALL_TESTS]
        expect('complete passing integration can accept synthetic golden', gate(sel=list(builds), builds=builds, update=True,
               expected=check.ALL_TESTS, tests=tests) == 0 and len(golden.read_text().splitlines()) == 2)
        crashed = [{'test': 'tools', 'rc': -signal.SIGILL, 'counts': None, 'secs': 0, 'log': ''}]
        expect('native crash without assertion output fails', gate(expected=['tools'], tests=crashed) == 1)

    for args in (['--update', '--no-tests'], ['--update', '--only', 'release'], ['--dev', '--test', 'tools']):
        r = subprocess.run([sys.executable, '-I', os.path.join(ROOT, 'tools/check.py'), *args], capture_output=True)
        expect('invalid validation scope rejected: ' + ' '.join(args), r.returncode == 2)
    ns = lambda **k: type('A', (), {'perf': False, 'tests_only': False, **k})
    expect('cost/stress checks run for integration; tests-only and dev runs need --perf',
           check.perf_enabled(ns(dev=False)) and check.perf_enabled(ns(tests_only=True, dev=False, perf=True)) and check.perf_enabled(ns(dev=True, perf=True))
           and not check.perf_enabled(ns(tests_only=True, dev=False)) and not check.perf_enabled(ns(dev=True)))
    with tempfile.TemporaryDirectory() as td:
        order = []
        def second():
            with workflow.test_slot(td, 1): order.append('second')
        with workflow.test_slot(td, 1):
            t = threading.Thread(target=second); t.start(); time.sleep(0.3); order.append('first')
        t.join(5)
        expect('a test waits for a free machine slot', order == ['first', 'second'])
        with workflow.test_slot(td, 2), workflow.test_slot(td, 2): expect('free slots are taken at once', True)
    with tempfile.TemporaryDirectory() as td, patch.object(check, 'CACHE', Path(td)):
        workflow.write(check.timing_file(True), {'patch:pcpng': 60})
        workflow.write(check.timing_file(False), {'patch:pcpng': 2})
        expect('quick timings cannot overwrite stress scheduling history',
               workflow.read(check.timing_file(True)) == {'patch:pcpng': 60}
               and workflow.read(check.timing_file(False)) == {'patch:pcpng': 2})
    expect('empty test selection refused', refused(lambda: check.parse_tests([','])))
    expect('SIGILL named in diagnostics', workflow.exit_description(-signal.SIGILL) == 'SIGILL')

    with tempfile.TemporaryDirectory() as td, patch.object(workflow, 'ROOT', Path(td)):
        with workflow.lock('test'):
            expect('overlapping checkout command refused', refused(lambda: workflow.lock('test').__enter__()))
        fake = subprocess.CompletedProcess([], 0, stdout='worktree ' + td + '\n')
        with patch.object(workflow.subprocess, 'run', return_value=fake):
            first, second = workflow.dev_tag(), workflow.dev_tag()
        expect('dev tags unique, same namespace, valid format', first != second and first[:-4] == second[:-4]
               and __import__('re').fullmatch(r'V2\.1z[A-Z]{8}', second) is not None)
        expect('dev counter persisted locally', workflow.read(Path(td) / '.dev-number.json')['number'] == 2)
        expect('dev counter exhaustion refused', refused(lambda: workflow.letters(26**4, 4)))

    with tempfile.TemporaryDirectory() as td, patch.object(workflow, 'ROOT', Path(td)):
        for d in ('test', 'patch', 'tools'): (Path(td) / d).mkdir(); (Path(td) / d / 'f').write_text('a')
        subprocess.run(['git', '-C', td, 'init', '-q'], check=True)
        with patch.object(workflow, 'environment', return_value={}):
            k, ik = workflow.build_key(), workflow.input_key()
            (Path(td) / 'test/f').write_text('b')
            expect('test edit keeps the build key', workflow.build_key() == k and workflow.input_key() != ik)
            for d in ('patch', 'tools'):
                (Path(td) / d / 'f').write_text('b')
                expect(f'{d} edit changes the build key', workflow.build_key() != k); k = workflow.build_key()

    with tempfile.TemporaryDirectory() as td:
        tree = Path(td) / 'tree'; (tree / 'rootfs').mkdir(parents=True)
        asset = tree / 'rootfs/asset'; asset.write_bytes(b'original')
        key = workflow.tree_key(tree)
        m = {'tree': key, 'inputs': 'inputs', 'mode': 'dev', 'tag': 'V2.1zTESTAAAB'}
        package = Path(td) / 'update.bin'; package.write_bytes(b'package')
        m['package_sha256'] = workflow.sha(package); workflow.write(tree / 'build.json', m)
        expect('stale source prevents packing', refused(lambda: workflow.validate_tree(tree)))
        r = {'passed': True, 'scope': 'full', 'expected': ['tools'], 'tests': [{'test': 'tools', 'rc': 0, 'counts': None}],
             'inputs': 'inputs', 'tree': key, 'package_sha256': m['package_sha256']}
        workflow.write(Path(td) / 'results.json', r)
        with patch.object(check, 'ALL_TESTS', ['tools']):
            expect('matching test receipt selects exact package', workflow.tested_package(td)[0] == package.resolve())
            package.write_bytes(b'tampered')
            expect('modified package rejected', refused(lambda: workflow.tested_package(td)))
            package.write_bytes(b'package'); r['tests'] = []; workflow.write(Path(td) / 'results.json', r)
            expect('passed boolean without test coverage rejected', refused(lambda: workflow.tested_package(td)))
            workflow.write(Path(td) / 'results.json', r | {'tests': [{'test': 'tools', 'rc': 0, 'counts': None}]})
            asset.write_bytes(b'modified')
            expect('modified tested tree rejected', refused(lambda: workflow.tested_package(td)))

    # make dev reuse: a passing full receipt with the same inputs is reused; anything else is not
    with tempfile.TemporaryDirectory() as td, patch.object(workflow, 'ROOT', Path(td)), patch.object(check, 'ALL_TESTS', ['tools']):
        d = Path(td) / 'out/dev/V2.1zTESTAAAB'; (d / 'tree').mkdir(parents=True)
        tkey = workflow.tree_key(d / 'tree'); pk = d / 'update.bin'; pk.write_bytes(b'package')
        workflow.write(d / 'tree/build.json', {'tree': tkey, 'inputs': 'in', 'tag': 'T', 'package_sha256': workflow.sha(pk)})
        rr = {'passed': True, 'scope': 'full', 'expected': ['tools'], 'tests': [{'test': 'tools', 'rc': 0, 'counts': None}],
              'inputs': 'in', 'tree': tkey, 'package_sha256': workflow.sha(pk), 'perf': False}
        workflow.write(d / 'results.json', rr)
        expect('reuse picks a matching passing build', (workflow.reusable_dev_build('in') or [None])[0] == d)
        with patch.object(check, 'run_test', return_value={'test': 'docs', 'rc': 0, 'counts': None, 'log': ''}), patch.object(check, 'ROOT', td):
            expect('reuse points latest at the build', check.reuse_dev(ns(timeout=5), d, {'tag': 'T'}) == 0
                   and workflow.read(Path(td) / 'out/dev/latest.json')['build'] == str(d))
        with patch.object(check, 'run_test', return_value={'test': 'docs', 'rc': 1, 'counts': None, 'log': 'x', 'logfile': 'l'}), patch.object(check, 'ROOT', td):
            expect('docs failure refuses reuse', check.reuse_dev(ns(timeout=5), d, {'tag': 'T'}) == 1)
        with tempfile.TemporaryDirectory() as other, patch.object(workflow, 'ROOT', Path(other)):   # another checkout sees it only when asked to look there
            expect('a peer checkout is not searched by default', workflow.reusable_dev_build('in') is None)
            expect('a peer checkout\'s matching receipt is found', (workflow.reusable_dev_build('in', roots=[Path(td)]) or [None])[0] == d)
            expect('a peer receipt of other inputs is not reused', workflow.reusable_dev_build('other', roots=[Path(td)]) is None)
        expect('different input key not reused', workflow.reusable_dev_build('other') is None)
        expect('perf receipt required when perf asked', workflow.reusable_dev_build('in', True) is None)
        workflow.write(d / 'results.json', rr | {'passed': False})
        expect('failed receipt not reused', workflow.reusable_dev_build('in') is None)
        workflow.write(d / 'results.json', rr); pk.write_bytes(b'tampered')
        expect('package hash mismatch not reused', workflow.reusable_dev_build('in') is None)

    with tempfile.TemporaryDirectory() as td:
        rc, _ = workflow.run_logged([sys.executable, '-I', __file__, '--signal-child'], Path(td) / 'signal.log')
        expect('signal return code preserved in worker', rc == -signal.SIGTERM)
        rc, log = workflow.run_logged([sys.executable, '-I', __file__, '--timeout-child'], Path(td) / 'timeout.log', timeout=0.1)
        expect('hung test killed with a recorded timeout', rc == 124 and 'TIMEOUT' in log)

    # Payload data is downstream of the cached battery/font/space base.
    with patch.object(buildcache, 'data_sha', side_effect=AssertionError('payload dependency in base')):
        expect('base key excludes payload data', bool(buildcache.base_key('stock', 'mod_battery', 'mod_font', 'mod_space')))
    import pull_shots
    from PIL import Image
    with tempfile.TemporaryDirectory() as td:
        bmp = Path(td) / 'shot-0001.bmp'; out = Path(td) / 'shots'
        Image.new('RGB', (1, 1), 'red').save(bmp)
        expect('first screenshot imported', pull_shots.import_shot(bmp, out))
        expect('identical screenshot deduplicated', not pull_shots.import_shot(bmp, out))
        Image.new('RGB', (1, 1), 'blue').save(bmp)
        expect('reused screenshot number preserves both images', pull_shots.import_shot(bmp, out) and len(list(out.glob('*.png'))) == 2)


def main():
    expect('good package verifies', problems() == [])
    expect('manifest-only archive rejected', problems(files={}) != [])
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, 'u.bin')
        with tarfile.open(p, 'w') as t:
            info = b'Shanling M1 Plus\nV9.9x\n'
            ti = tarfile.TarInfo(fwtool.INFO_NAME); ti.size = len(info); t.addfile(ti, io.BytesIO(info))
        expect('manifest-only tar: verify command fails', fwtool.cmd_verify(type('A', (), {'update': p})) == 1)
        open(p, 'wb').write(b'not a tar')
        expect('non-tar rejected', fwtool.verify_package(p)[0] != [])
    good = [f'{hashlib.md5(b"kernel").hexdigest()}  recovery-update/xImage',
            f'{hashlib.md5(b"rootfs").hexdigest()}  recovery-update/rootfs.squashfs']
    expect('empty manifest rejected', problems(manifest=[]) != [])
    expect('truncated manifest (one entry) rejected', problems(manifest=good[:1]) != [])
    expect('malformed checksum line rejected', problems(manifest=good + ['zz  recovery-update/other']) != [])
    expect('duplicate checksum line rejected', problems(manifest=good + good[:1]) != [])
    expect('extra manifest entry rejected', problems(manifest=good + [f'{"0" * 32}  recovery-update/extra']) != [])
    expect('md5 mismatch rejected', problems(manifest=['0' * 32 + '  recovery-update/xImage', good[1]]) != [])
    expect('wrong model rejected', problems(model='Other Player') != [])
    expect('missing payload file rejected', problems(drop=('recovery-update/xImage',)) != [])
    expect('unexpected member rejected', problems(extra=('recovery-update/evil',)) != [])
    expect('path traversal member rejected', problems(extra=('../evil',)) != [])
    expect('duplicate member rejected', problems(dup='recovery-update/xImage') != [])

    # check.py: a failing test never passes, and --update never blesses a failed run
    t = lambda rc, c: {'rc': rc, 'counts': c}
    expect('test crash without counts fails', not check.test_ok(t(-11, None)))
    expect('non-zero exit after a success line fails', not check.test_ok(t(1, (10, 0))))
    expect('failed count fails', not check.test_ok(t(1, (9, 1))))
    expect('clean run passes', check.test_ok(t(0, (10, 0))) and check.test_ok(t(0, None)))
    expect('plain match passes', check.outcome(False, False, False) == (False, False))
    expect('changed hash fails without --update', check.outcome(False, True, False) == (True, False))
    expect('--update accepts a changed hash', check.outcome(False, True, True) == (False, True))
    expect('--update with a failed test fails and writes nothing', check.outcome(True, True, True) == (True, False))
    expect('--update with a failed test and no change fails', check.outcome(True, False, True) == (True, False))

    # check.py --test: names resolve to patch modules (a module with SECTIONS: one test per section) or the named tests; unknown names are refused
    expect('--test resolves a patch module', check.parse_tests(['home,tools']) == ['patch:home', 'tools'])
    albums = [f'patch:albums/{s}' for s in check.sections('albums')]
    expect('a module with SECTIONS is one test per section, by name or as patch:', len(albums) > 1 and check.parse_tests(['albums']) == check.parse_tests(['patch:albums']) == albums)
    expect('--test runs one section', check.parse_tests([albums[1][6:]]) == [albums[1]])
    try: check.parse_tests(['nosuchtest']); refused = False
    except SystemExit: refused = True
    expect('--test refuses an unknown name', refused)

    # the build cache: a rewrite that keeps size and mtime (the steps set mtimes on purpose) is still a change
    import buildcache, subprocess
    with tempfile.TemporaryDirectory() as td:
        root = os.path.join(td, 'tree'); os.makedirs(os.path.join(root, 'd')); os.makedirs(os.path.join(root, 'gdir/sub'))
        for n, d in (('a', b'one'), ('d/b', b'two'), ('gone', b'x'), ('gdir/f', b'1'), ('gdir/sub/g', b'2')): open(os.path.join(root, n), 'wb').write(d)
        os.symlink('a', os.path.join(root, 'lnk'))
        before = buildcache.snap(root); st = os.stat(os.path.join(root, 'a'))
        open(os.path.join(root, 'a'), 'wb').write(b'ONE'); os.utime(os.path.join(root, 'a'), ns=(st.st_atime_ns, st.st_mtime_ns))
        open(os.path.join(root, 'new'), 'wb').write(b'n'); os.remove(os.path.join(root, 'gone'))
        shutil.rmtree(os.path.join(root, 'gdir'))
        changed, removed, _ = buildcache.delta_since(before, root)
        expect('delta sees a same-size same-mtime rewrite, an addition, a removal', sorted(changed) == ['a', 'new'] and 'gone' in removed)
        expect('delta records a removed directory', {'gdir', 'gdir/sub', 'gdir/f', 'gdir/sub/g'} <= set(removed))
        buildcache.CACHE = os.path.join(td, 'cache'); buildcache.ENABLED = True
        buildcache.store_delta('k', root, changed, removed)
        other = os.path.join(td, 'other'); os.makedirs(other)
        for n, d in (('a', b'one'), ('gone', b'x')): open(os.path.join(other, n), 'wb').write(d)
        os.makedirs(os.path.join(other, 'gdir/sub'))      # replaying the step leaves no empty directory behind
        buildcache.apply_delta('k', other)
        expect('a stored delta reproduces the tree', open(os.path.join(other, 'a'), 'rb').read() == b'ONE'
               and os.path.exists(os.path.join(other, 'new')) and not os.path.exists(os.path.join(other, 'gone')))
        expect('a replayed delta removes a removed directory', not os.path.exists(os.path.join(other, 'gdir')))
    expect('code hash follows imports', 'modlib' in buildcache.closure('mod_theme') or 'awtk_ui' in buildcache.closure('mod_theme'))

    # sub.py refuses an ambiguous or missing OLD and changes nothing
    with tempfile.TemporaryDirectory() as td:
        f = os.path.join(td, 'f.txt'); open(f, 'w').write('x = 1\nx = 1\ny = 2\n')
        sub = lambda *a: subprocess.run([sys.executable, '-I', os.path.join(ROOT, 'tools', 'sub.py'), f, *a], capture_output=True, text=True).returncode
        expect('sub: ambiguous OLD refused', sub('x = 1', 'x = 3') == 1 and open(f).read() == 'x = 1\nx = 1\ny = 2\n')
        expect('sub: missing OLD refused', sub('z', 'w') == 1)
        expect('sub: --all replaces every occurrence', sub('x = 1', 'x = 3', '--all') == 0 and open(f).read() == 'x = 3\nx = 3\ny = 2\n')
    # autotime: every literal keeps its slot length and ends in NUL; a changed stock byte or neighbour is refused, nothing written
    expect('autotime slots keep their length and NUL end', all(len(o) == len(n) and n.endswith(b'\0') and b'\0' not in n.rstrip(b'\0') for _, o, n, _ in autotime.EDITS))
    expect('autotime commands', {n for _, _, n, _ in autotime.EDITS} >= {b'hwclock -su\0', b'hwclock -wu\0'}
           and len(autotime.EDITS) == 2)
    def stock_image():
        img = bytearray(0x757000)   # identity address -> offset
        for a, o, _, _ in autotime.EDITS: img[a:a + len(o)] = o
        for a, x in autotime.NEIGHBOURS: img[a:a + len(x)] = x
        return img
    ident = lambda b, a: a
    img = stock_image(); autotime.apply(img, ident)
    expect('autotime writes every new slot and keeps the neighbours', all(img[a:a + len(n)] == n for a, _, n, _ in autotime.EDITS)
           and all(img[a:a + len(x)] == x for a, x in autotime.NEIGHBOURS))
    for a, _, _, what in autotime.EDITS + tuple((a, 0, 0, 'neighbour') for a, _ in autotime.NEIGHBOURS):
        img = stock_image(); img[a] ^= 1; before = bytes(img)
        try: autotime.apply(img, ident); refused = False
        except ValueError: refused = True
        expect(f'autotime refuses a changed byte at {a:#x} and writes nothing', refused and bytes(img) == before)
    workflow_tests()
    print(f'{ok} passed, {fail} failed')
    sys.exit(1 if fail else 0)


if __name__ == '__main__':
    if sys.argv[1:] == ['--signal-child']: os.kill(os.getpid(), signal.SIGTERM)
    elif sys.argv[1:] == ['--timeout-child']: time.sleep(10)
    else: main()
