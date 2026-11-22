#!/usr/bin/env python3
"""Test features, produce a tested dev package, or validate integration.

  make test [TEST=albums]     tree + tests; no package or goldens
  make dev                    one dev tree + full tests + verified package
  make check                  release + restore + full tests vs goldens
  make accept                 accept goldens after complete integration validation

make test and make dev run the cost/stress checks only with PERF=1; make check and make accept always do.
Logs and failed trees are retained. --list lists tests. --jobs and --timeout control
concurrency and the per-test wall limit. Native crashes include their signal.
"""
import argparse, ast, concurrent.futures as cf, glob, os, re, shutil, sys, time
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, 'tools'); TEST = os.path.join(ROOT, 'test')
sys.path.insert(0, TOOLS)
import build, paths, workflow

GOLDEN = os.path.join(TEST, 'golden.sha256')
CACHE = Path(ROOT) / 'work/cache'
LAST = CACHE / 'check-last.json'
TARGETS = {'release': (build.TAG, []), 'restore': (build.RESTORE_TAG, ['--restore'])}
MODULES = sorted(Path(f).stem for f in glob.glob(os.path.join(TEST, 'pod', '*.py')) if not f.endswith('harness.py'))


def sections(module):
    for node in ast.parse(Path(TEST, 'pod', module + '.py').read_text()).body:
        if isinstance(node, ast.Assign) and [getattr(t, 'id', None) for t in node.targets] == ['SECTIONS']:
            return [e.id for e in node.value.elts]
    return []


PATCH = {m: [f'patch:{m}/{s}' for s in sections(m)] or [f'patch:{m}'] for m in MODULES}
LIGHT = ['tools', 'docs', 'cdefs', 'consts', 'coverflow', 'awtk_fill']
TREE_TESTS = ('demo_diff', 'webapi')   # tests that read the built tree
ALL_TESTS = LIGHT + list(TREE_TESTS) + [t for m in MODULES for t in PATCH[m]]


def counts(text):
    m = re.findall(r'(\d+) passed, (\d+) failed', text)
    return tuple(map(int, m[-1])) if m else None


def test_ok(t): return t['rc'] == 0 and (t['counts'] is None or t['counts'][1] == 0)
def outcome(bad, changed, update): return bad or (changed and not update), update and not bad
def perf_enabled(a): return a.perf or not (a.tests_only or a.dev)   # goldens need the cost checks; a dev receipt gets them at integration
def timing_file(perf): return CACHE / ('test-times.json' if perf else 'test-times-quick.json')
def tree_key(): return workflow.input_key()


def read_golden():
    g = {}
    if os.path.isfile(GOLDEN):
        for line in Path(GOLDEN).read_text().splitlines():
            p = line.split()
            if len(p) == 3 and not line.startswith('#'): g[p[2]] = (p[0], p[1])
    return g


def parse_tests(spec):
    names = []
    for n in (n for s in spec for n in s.split(',') if n):
        m = n.removeprefix('patch:')
        names += PATCH[m] if m in PATCH else ['patch:' + m] if 'patch:' + m in ALL_TESTS else [n]
    bad = [n for n in names if n not in ALL_TESTS]
    if bad: raise SystemExit(f'unknown test {", ".join(bad)}; use --list')
    if not names: raise SystemExit('empty test selection; use --list')
    return list(dict.fromkeys(names))


def test_cmd(name, stock, tree=None):
    py = [sys.executable, '-I']
    if name in ('tools', 'docs', 'cdefs', 'consts', 'coverflow'): return py + [os.path.join(TEST, name + '.py')]
    if name == 'awtk_fill': return py + [os.path.join(TEST, 'awtk_fill.py'), stock]
    if name == 'webapi': return py + [os.path.join(TEST, 'webapi.py'), str(tree), stock]
    if name == 'demo_diff':
        return py + [os.path.join(TEST, 'demo_diff.py'), os.path.join(stock, 'rootfs/release/bin/demo'),
                     str(Path(tree) / 'rootfs/release/bin/demo')]
    return py + [os.path.join(TEST, 'patch.py'), str(tree), name[6:]]


def run_test(name, cmd, logdir, timeout):
    logfile = Path(logdir) / (name.replace(':', '-').replace('/', '-') + '.log')
    with workflow.test_slot():   # the wait is not the test's cost
        start = time.monotonic(); rc, log = workflow.run_logged(cmd, logfile, timeout)
    return {'test': name, 'rc': rc, 'counts': counts(log), 'log': log[-2500:],
            'logfile': str(logfile), 'cmd': cmd, 'secs': time.monotonic() - start}


def reuse_dev(a, directory, manifest):
    """Reuse a passing build; docs are not an input, so their test still runs fresh."""
    logs = Path(ROOT) / 'work/check/logs'; logs.mkdir(parents=True, exist_ok=True)
    t = run_test('docs', test_cmd('docs', None), logs, a.timeout)
    if not test_ok(t):
        print(f'docs: FAIL ({workflow.exit_description(t["rc"])}); log: {t["logfile"]}\n{t["log"]}'); return 1
    workflow.write(Path(ROOT) / 'out/dev/latest.json', {'build': str(directory)})
    print(f'reusing passing dev build {manifest["tag"]} (inputs unchanged); docs check passed; next: make flash', flush=True)
    return 0


def run_build(flags, logfile, env=None):
    start = time.monotonic()
    cmd = [sys.executable, '-I', os.path.join(TOOLS, 'build.py'), *map(str, flags)]
    rc, log = workflow.run_logged(cmd, logfile, env=env)
    if rc: raise SystemExit(f'build {workflow.exit_description(rc)}; log: {logfile}\n{log[-2500:]}')
    elapsed = time.monotonic() - start
    print(f'build ready ({elapsed:.1f}s); log: {logfile}', flush=True)
    return elapsed


def expected_results(names, tests):
    found = {t['test']: t for t in tests}
    return [found.get(n, {'test': n, 'rc': 125, 'counts': None, 'log': 'required test did not run',
                          'secs': 0, 'logfile': '(no log)', 'cmd': []}) for n in names]


def finish(a, sel, skipped, golden, builds, tests, t0, reused=False, key=None):
    """Single gate for integration, tests-only and dev receipts; never bless missing work."""
    tests = expected_results(a.expected, tests)
    bad = bool(skipped); changed = False; rows = []
    for n in sel:
        if n in skipped: print(f'{n}: BLOCKED {skipped[n]}'); continue
        r = builds.get(n)
        if not r or r.get('error'):
            bad = True; print(f'{n}: ERROR {(r or {}).get("error", "required build did not run")}'); continue
        if a.tests_only: continue
        g = golden.get(n); status = 'NEW' if not g else 'MATCH' if g == (r['sha'], TARGETS[n][0]) else 'CHANGED'
        changed |= status != 'MATCH'
        print(f'{n}: {status} {r["sha"]}')
        rows.append((n, TARGETS[n][0], r['sha']))
    assertions = [0, 0]; failed = crashed = 0
    for t in tests:
        if t['counts']:
            for i in (0, 1): assertions[i] += t['counts'][i]
        if not test_ok(t):
            failed += 1; crashed += t['rc'] < 0; bad = True
            print(f'{t["test"]}: FAIL ({workflow.exit_description(t["rc"])}); log: {t.get("logfile", "(no log)")}')
            print('command:', repr(t.get('cmd', []))); print(t['log'])
    if key and (workflow.build_key() if a.tests_only else workflow.input_key()) != key:
        bad = True; print('ERROR: source or environment changed during this run; results cannot certify this build')
    print(f'tasks {len(tests) - failed} passed, {failed} failed ({crashed} crashed); '
          f'assertions {assertions[0]} passed, {assertions[1]} failed; {time.monotonic() - t0:.1f}s wall')
    if a.update and (a.no_tests or set(sel) != set(TARGETS) or set(a.expected) != set(ALL_TESTS)):
        bad = True; print('ERROR: golden acceptance requires both packages and the complete test suite')
    if key and not reused and not a.tests_only and not a.no_tests and not bad and not a.dev:
        workflow.write(LAST, {'key': key, 'builds': builds, 'tests': tests, 'expected': a.expected})
    fail, write = outcome(bad, changed, a.update)
    if write:
        for n, tag, sha in rows: golden[n] = (sha, tag)
        Path(GOLDEN).write_text(''.join(f'{golden[n][0]}  {golden[n][1]}  {n}\n' for n in TARGETS))
        print('updated test/golden.sha256')
    return 1 if fail else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--only', nargs='+', choices=list(TARGETS)); ap.add_argument('--no-tests', action='store_true')
    ap.add_argument('--update', action='store_true'); ap.add_argument('--tests-only', action='store_true')
    ap.add_argument('--test', nargs='+', metavar='NAME[,NAME]'); ap.add_argument('--list', action='store_true')
    ap.add_argument('--dev', action='store_true', help='build, fully test and package one development artifact')
    ap.add_argument('--fresh', action='store_true', help='with --dev: run the full tests even when a passing build has the same inputs')
    ap.add_argument('--clean', action='store_true', help='remove retained integration/test scratch files')
    ap.add_argument('--no-cache', action='store_true')
    ap.add_argument('--perf', action='store_true', help='also run the cost and stress-scale checks (always on for integration and --update)')
    ap.add_argument('--verbose', action='store_true', help='print every passing test, not only failures')
    ap.add_argument('--jobs', type=int, default=workflow.SLOTS)
    ap.add_argument('--timeout', type=int, default=300, help='seconds per test (default 300)')
    a = ap.parse_args()
    if a.list:
        print('\n'.join(t.removeprefix('patch:') for t in ALL_TESTS)); return 0
    if a.jobs < 1 or a.timeout < 1: ap.error('--jobs and --timeout must be positive')
    if a.test: a.tests_only = True
    if a.tests_only and (a.update or a.no_tests or a.only): ap.error('--tests-only/--test cannot combine with --update, --no-tests or --only')
    if a.update and (a.no_tests or a.only): ap.error('--update requires the full integration scope, including tests')
    if a.dev and (a.tests_only or a.update or a.no_tests or a.only): ap.error('--dev always builds and tests the complete development package')
    if a.no_cache: os.environ['M1_NO_CACHE'] = '1'
    a.perf = perf_enabled(a)
    os.environ['M1_PERF'] = '1' if a.perf else '0'
    selected = parse_tests(a.test) if a.test else None
    names = [] if a.no_tests else selected or (LIGHT if a.only == ['restore'] else ALL_TESTS)
    a.expected = names
    with workflow.lock('check'):
        if a.clean:
            with workflow.lock('build'): shutil.rmtree(Path(ROOT) / 'work/check', ignore_errors=True)
            print('removed work/check; dev artifacts, version counter and caches kept')
            return 0
        start = time.monotonic(); peer = None
        if a.dev and not a.fresh:
            hit = workflow.reusable_dev_build(workflow.input_key(), a.perf)
            if hit:
                return reuse_dev(a, *hit)
            peer = workflow.reusable_dev_build(workflow.input_key(), a.perf, workflow.other_checkouts())   # a squash merge of a branch that passed in its worktree: the same inputs
        key = workflow.build_key() if a.tests_only else workflow.input_key()   # tests-only runs certify nothing: only an edit to what the tree is built from invalidates them
        sel = [] if a.tests_only or a.dev else a.only or list(TARGETS)
        golden = read_golden(); builds = {}; tests = []
        base = workflow.new_dev_dir() if a.dev else Path(ROOT) / 'work/check'
        logs = base / 'logs'; logs.mkdir(parents=True, exist_ok=True)
        print(f'run: {base}; {len(names)} tests, {a.jobs} workers' + ('' if a.perf else '; perf checks skipped (PERF=1 to run)'), flush=True)
        if any(n == 'awtk_fill' or n.startswith('patch:') for n in names):
            rc, log = workflow.run_logged([sys.executable, '-I', os.path.join(TOOLS, 'doctor.py'), '--emulator'], logs / 'emulator.log', 15)
            if rc:
                raise SystemExit(f'Unicorn execution failed ({workflow.exit_description(rc)}); log: {logs / "emulator.log"}\n'
                                 'The sandbox may prohibit native JIT execution. Run make doctor in a permitted native environment.\n' + log[-1500:])
        last = workflow.read(LAST)
        if a.update and last.get('key') == key and last.get('expected') == ALL_TESTS \
                and set(last.get('builds', {})) == set(TARGETS) and all(test_ok(t) for t in last.get('tests', [])) \
                and all(Path(r['package']).is_file() and workflow.sha(r['package']) == r['sha'] for r in last['builds'].values()):
            print('reusing complete validated integration artifacts')
            return finish(a, sel, {}, golden, last['builds'], last['tests'], start, reused=True, key=key)
        stock = paths.find_stock()
        if not stock and ('awtk_fill' in names or sel or a.dev or any(n.startswith('patch:') or n in TREE_TESTS for n in names)):
            run_build(['--restore', '--tree-only'], logs / 'stock.log')
            stock = paths.find_stock()
        stock = stock or os.path.join(paths.WORK, 'stock')
        needs_tree = a.dev or 'release' in sel or any(n.startswith('patch:') or n in TREE_TESTS for n in names)
        tree = None
        env = dict(os.environ, M1_WORK=str(base / 'release/work'), M1_OUT=str(base / 'release/out'))
        flags = ['--dev', '--out', base] if a.dev else []
        if needs_tree:
            tree = base / 'tree' if a.dev else base / 'release/work/mod-release'
            reuse = False
            if a.tests_only and not a.dev and tree.is_dir():   # targeted runs: a tree built from the same build inputs (test-only edits) is still good
                try: workflow.validate_tree(tree); reuse = True
                except SystemExit: pass
            if reuse: print('build reused (inputs unchanged)', flush=True)
            else:
                run_build([*flags, '--tree-only'], logs / 'tree.log', env)
                workflow.validate_tree(tree)
        # Stress inputs have very different costs. Quick runs must not schedule a
        # later dev run's long stress tasks last by overwriting their durations.
        os.environ['M1_SOURCE_KEY'] = workflow.build_source_key()   # the tasks compare the tree with this instead of hashing the sources once each; the input key is checked again after them
        times_path = timing_file(a.perf)
        times = workflow.read(times_path)
        test_start = progress = time.monotonic()
        timings = {'setup': test_start - start}
        todo = names
        if peer:   # its tests ran on these inputs (its tree differs in the dev tag only); docs are not an input, so their test runs here
            tests = [t for t in workflow.read(peer[0] / 'results.json')['tests'] if t['test'] != 'docs']; todo = ['docs']
            print(f'tests reused from {peer[0]} (same inputs, passed there)', flush=True)
        with cf.ThreadPoolExecutor(max_workers=a.jobs) as ex:
            pending = {ex.submit(run_test, n, test_cmd(n, stock, tree), logs, a.timeout): n
                       for n in sorted(todo, key=lambda n: times.get(n, 0), reverse=True)}
            for f in cf.as_completed(pending):
                r = f.result(); tests.append(r)
                if a.verbose or not test_ok(r):   # passes only with --verbose; the summary line counts them
                    print(f'{r["test"]}: {"PASS" if test_ok(r) else "FAIL " + workflow.exit_description(r["rc"])} ({r["secs"]:.1f}s)', flush=True)
                now = time.monotonic()
                if not a.verbose and now - progress >= 10:
                    print(f'tests: {len(tests)}/{len(names)} completed ({now - test_start:.1f}s)', flush=True)
                    progress = now
        timings['tests'] = time.monotonic() - test_start
        if tests:
            slowest = sorted(tests, key=lambda t: t['secs'], reverse=True)[:3]
            print(f'tests ready ({timings["tests"]:.1f}s); slowest: ' +
                  ', '.join(f'{t["test"].removeprefix("patch:")} {t["secs"]:.1f}s' for t in slowest), flush=True)
        workflow.write(times_path, {n: s for n, s in {**times, **{t['test']: t['secs'] for t in tests}}.items() if n in ALL_TESTS})   # names no longer run are dropped
        tests_passed = len(tests) == len(names) and all(test_ok(t) for t in tests)
        if (workflow.build_key() if a.tests_only else workflow.input_key()) != key: tests_passed = False
        if tests_passed and (a.dev or 'release' in sel):
            timings['package'] = run_build([*flags, '--pack-only'], logs / 'package.log', env)
            package = base / 'update.bin' if a.dev else base / 'release/out' / f'M1Plus-{build.TAG}-release-update.bin'
            if not a.dev: builds['release'] = {'sha': workflow.sha(package), 'package': str(package)}
        elif 'release' in sel: builds['release'] = {'error': 'tests failed; package not produced'}
        if 'restore' in sel:
            restore_env = dict(os.environ, M1_WORK=str(base / 'restore/work'), M1_OUT=str(base / 'restore/out'))
            run_build(['--restore'], logs / 'restore.log', restore_env)
            package = base / 'restore/out' / f'M1Plus-{build.RESTORE_TAG}-stock-restore-update.bin'
            builds['restore'] = {'sha': workflow.sha(package), 'package': str(package)}
        if a.dev:
            m = workflow.read(tree / 'build.json')
            passed = tests_passed and bool(m.get('package_sha256')) and workflow.input_key() == key
            workflow.write(base / 'results.json', {'passed': passed, 'scope': 'full', 'inputs': key, 'tree': m['tree'],
                                                  'package_sha256': m.get('package_sha256'), 'expected': names, 'perf': a.perf, 'tests': tests,
                                                  'timings': timings, **({'tested_in': str(peer[0])} if peer else {})})
            if passed:
                workflow.tested_package(base)
                workflow.write(Path(ROOT) / 'out/dev/latest.json', {'build': str(base)})
                print(f'tested dev package: {base} ({m["tag"]}); next: make flash', flush=True)
        else: passed = True
        return max(finish(a, sel, {}, golden, builds, tests, start, key=key), 0 if passed else 1)


if __name__ == '__main__': sys.exit(main())
