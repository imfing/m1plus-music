"""Build identities and receipts shared by build, check, preview and SD installation.

All mutable state stays in this checkout, except the machine's test slots. Nothing here changes firmware bytes.
"""
import contextlib, fcntl, hashlib, importlib.metadata, json, os, signal, subprocess, sys, tempfile, time
from pathlib import Path

import paths

ROOT = Path(paths.ROOT)
IGNORED_INPUTS = ('docs/', 'README.md', 'AGENTS.md', 'LICENSE', 'test/golden.sha256')
BUILD_IGNORED = IGNORED_INPUTS + ('test/',)   # the tree build (tools/build.py, pod.py) never reads test/


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''): h.update(b)
    return h.hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def read(path):
    try:
        value = json.loads(Path(path).read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError): return {}


def write(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as f: json.dump(value, f, indent=2, sort_keys=True); f.write('\n')
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


@contextlib.contextmanager
def lock(name):
    p = ROOT / 'work' / (name + '.lock'); p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('a') as f:
        try: fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise SystemExit(f'{name}: another command is using this checkout; retry when it finishes')
        try: yield
        finally: fcntl.flock(f, fcntl.LOCK_UN)


SLOTS = os.cpu_count() or 4


@contextlib.contextmanager
def test_slot(directory=None, count=SLOTS):
    """Hold one of the machine's test slots. Every checkout shares them, so runs in several
    worktrees queue for the CPUs instead of each starting a full set of workers."""
    d = Path(directory or Path(tempfile.gettempdir()) / 'm1plus-test-slots'); d.mkdir(parents=True, exist_ok=True)
    while True:
        for i in range(count):
            with (d / str(i)).open('a') as f:
                try: fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError: continue
                yield; return
        time.sleep(0.1)


def source_key(ignored=IGNORED_INPUTS):
    r = subprocess.run(['git', '-C', str(ROOT), 'ls-files', '-z', '--cached', '--others', '--exclude-standard'],
                       capture_output=True, check=True)
    entries = []
    for rel in sorted(set(os.fsdecode(r.stdout).split('\0')) - {''}):
        p = ROOT / rel
        if rel.startswith(ignored): continue
        if p.is_symlink(): entries.append((rel, 'link', os.readlink(p)))
        elif p.is_file(): entries.append((rel, p.stat().st_mode & 0o777, sha(p)))
    return digest(entries)


def environment():
    llvm = os.environ.get('LLVM_BIN', '/opt/homebrew/opt/llvm/bin')
    lld = os.environ.get('LLD_BIN', '/opt/homebrew/opt/lld/bin')
    out = {'python': sys.version, 'requirements': {}}
    for package in ('capstone', 'pyelftools', 'pillow', 'fonttools', 'unicorn'):
        try: out['requirements'][package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError: out['requirements'][package] = 'missing'
    for tool in ('clang', 'llvm-objcopy', 'llvm-readelf', 'ld.lld', 'mksquashfs', 'unsquashfs'):
        binary = os.path.join(lld if tool == 'ld.lld' else llvm, tool) if tool not in ('mksquashfs', 'unsquashfs') else tool
        try:
            r = subprocess.run([binary, '-version' if 'squashfs' in tool else '--version'], capture_output=True, text=True, timeout=10)
            out[tool] = (r.stdout + r.stderr).splitlines()[0]
        except (OSError, subprocess.SubprocessError, IndexError): out[tool] = 'missing'
    return out


def input_key(): return digest([source_key(), environment()])
def build_source_key(): return source_key(BUILD_IGNORED)
def build_key(): return digest([build_source_key(), environment()])   # what the tree build reads: unchanged by test-only edits


def tree_key(tree):
    tree = Path(tree); entries = []
    # The rootfs, package metadata and payload ELF are all consumed by tests or packaging.
    for rel in ('rootfs', 'podbuild', 'meta.json', 'stock.pseudo', 'stock.lln', 'recovery-update'):
        start = tree / rel
        files = sorted(start.rglob('*')) if start.is_dir() else [start]
        for p in files:
            if p.is_symlink(): entries.append((str(p.relative_to(tree)), 'link', os.readlink(p)))
            elif p.is_file(): entries.append((str(p.relative_to(tree)), p.stat().st_mode & 0o777, sha(p)))
    return digest(entries)


def letters(number, width):
    if not 0 <= number < 26 ** width: raise SystemExit('development version space exhausted; do not wrap or reuse tags')
    value = ''
    for _ in range(width): number, d = divmod(number, 26); value = chr(65 + d) + value
    return value


def namespace(root): return letters(int.from_bytes(hashlib.sha256(os.fsencode(os.path.realpath(root))).digest()[:8], 'big') % 26**4, 4)


def dev_tag():
    """Reserve z + four checkout letters + four counter letters; no writes to other worktrees."""
    with lock('dev-version'):
        ns = namespace(ROOT)
        r = subprocess.run(['git', '-C', str(ROOT), 'worktree', 'list', '--porcelain'], capture_output=True, text=True, check=True)
        for line in r.stdout.splitlines():
            if line.startswith('worktree '):
                other = line[9:]
                if os.path.realpath(other) != os.path.realpath(ROOT) and namespace(other) == ns:
                    raise SystemExit('development namespace collision with another worktree; use a different worktree path')
        p = ROOT / '.dev-number.json'; state = read(p)
        n = state.get('number', 0)
        if state and state.get('namespace') != ns: raise SystemExit('worktree path changed: remove .dev-number.json only after choosing a new dev namespace')
        n += 1
        tag = 'V2.1z' + ns + letters(n, 4)
        write(p, {'namespace': ns, 'number': n})
        return tag


def new_dev_dir():
    parent = ROOT / 'out' / 'dev'; parent.mkdir(parents=True, exist_ok=True)
    directory = parent / dev_tag()
    directory.mkdir()  # Never overwrite an earlier artifact if counter state was lost.
    return directory


def build_dir(value):
    if value == 'latest':
        value = read(ROOT / 'out' / 'dev' / 'latest.json').get('build')
        if not value: raise SystemExit('no tested dev build; run make dev first')
    p = Path(value).resolve()
    if not (p / 'tree' / 'build.json').is_file(): raise SystemExit(f'{p}: no build manifest')
    return p


def validate_tree(tree, current=True):
    m = read(Path(tree) / 'build.json')
    if not m or m.get('tree') != tree_key(tree): raise SystemExit(f'{tree}: tree changed or has no final manifest; rebuild it')
    if current and m.get('build_inputs') != build_key(): raise SystemExit(f'{tree}: source or environment changed; rebuild it')
    return m


def tested_package(directory):
    from check import ALL_TESTS, expected_results, test_ok
    directory = build_dir(str(directory)); m = validate_tree(directory / 'tree', current=False)
    r = read(directory / 'results.json'); package = directory / 'update.bin'
    if not package.is_file() or m.get('package_sha256') != sha(package): raise SystemExit('package differs from the build manifest')
    if r.get('passed') is not True or r.get('inputs') != m['inputs'] or r.get('tree') != m['tree'] \
            or r.get('package_sha256') != m['package_sha256'] or r.get('scope') != 'full' \
            or set(r.get('expected', [])) != set(ALL_TESTS) \
            or not all(test_ok(t) for t in expected_results(ALL_TESTS, r.get('tests', []))):
        raise SystemExit('no matching complete passing test receipt; run make dev')
    return package, m


def other_checkouts():
    """The repository's other worktrees (the main checkout included), for a receipt of the same inputs tested there."""
    r = subprocess.run(['git', '-C', str(ROOT), 'worktree', 'list', '--porcelain'], capture_output=True, text=True, check=True)
    here = os.path.realpath(ROOT)
    return [Path(p) for p in (line[9:] for line in r.stdout.splitlines() if line.startswith('worktree ')) if os.path.realpath(p) != here]


def reusable_dev_build(key, perf=False, roots=None):
    """Newest out/dev build (here, or in the given checkouts) whose passing full receipt has these inputs and whose package still verifies, else None."""
    from check import ALL_TESTS
    found = []
    for f in (f for root in roots or [ROOT] for f in (Path(root) / 'out' / 'dev').glob('*/results.json')):
        r = read(f)
        if r.get('passed') is True and r.get('scope') == 'full' and r.get('inputs') == key \
                and set(r.get('expected', [])) == set(ALL_TESTS) and (r.get('perf') or not perf):
            found.append((f.stat().st_mtime, f.parent))
    for _, d in sorted(found, reverse=True):
        try: return d, tested_package(d)[1]
        except SystemExit: continue
    return None


def exit_description(rc):
    if rc < 0:
        try: return signal.Signals(-rc).name
        except ValueError: return f'signal {-rc}'
    return f'exit {rc}'


def run_logged(cmd, logfile, timeout=600, env=None):
    """A foreground subprocess with a full log and bounded process-group lifetime."""
    logfile = Path(logfile); logfile.parent.mkdir(parents=True, exist_ok=True)
    with logfile.open('w') as f:
        f.write('command: ' + repr(cmd) + '\n'); f.flush()
        try:
            with subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT, env=env, start_new_session=True) as p:
                try: rc = p.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    os.killpg(p.pid, signal.SIGKILL); p.wait(); f.write(f'\nTIMEOUT after {timeout}s\n'); rc = 124
        except OSError as exc: f.write(str(exc)); rc = 127
    return rc, logfile.read_text(errors='replace')
