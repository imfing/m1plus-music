"""A local Software Update server for development (the device's development channel, docs/modules/update.md).

  make ota-serve [PORT=8765]   run the one server (keep it open); it prints the line for the card file
  make ota [BUILD=latest]      upload a tested dev build's update.bin (from any checkout or worktree)

The card file /m1plus-update-url (on the TF card's root) holds the server's address, e.g. http://192.168.1.20:8765.
Software Update then asks this server GitHub's paths: /releases/latest (a redirect naming the tag), /releases/tags/<tag>
(the notes, here the pushing checkout's branch and commit) and /releases/download/<tag>/update.bin. The tag is what the
package's firmware_v20.info says: a dev build's V2.1z... tag, or a release's version. Only this machine may upload.
"""
import argparse, http.server, json, os, re, signal, socket, subprocess, sys, tarfile, tempfile, threading, urllib.error, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE = None   # the server's temporary folder, deleted when it stops: one package for every checkout, the last push wins
KEEP = 3   # generations still downloadable by tag (a device that checked before a push gets what it was offered)
LOCK = threading.Lock()   # guards GENS: every push is a new immutable file, switched in with its tag and notes in one step
GENS = {}   # tag -> (notes, package path), oldest first; the last one is the latest
TAG = re.compile(r'(\d{1,5}\.\d{1,5}\.\d{1,5}|V2\.1z[A-Z]{1,12})')   # what the device accepts (patch/upver.c up_parse, up_devtag)


def package_tag(path):
    """The tag the device will check against line 2 of firmware_v20.info, or SystemExit-worthy text."""
    with tarfile.open(path) as t:
        first = t.next()
        if not first or first.name != 'firmware_v20.info': raise ValueError('firmware_v20.info is not the first member')
        lines = t.extractfile(first).read().decode().split('\n')
    if len(lines) < 2 or lines[0] != 'Shanling M1 Plus': raise ValueError('not a Shanling M1 Plus package')
    tag = lines[1].removeprefix('V2.1-')
    if not TAG.fullmatch(tag): raise ValueError(f'line 2 {lines[1]!r} is neither V2.1-<x.y.z> nor a V2.1z dev tag')
    return tag


class Handler(http.server.BaseHTTPRequestHandler):
    def send(self, code, body=b'', ctype='text/plain; charset=utf-8', **headers):
        self.send_response(code)
        self.send_header('Content-Type', ctype); self.send_header('Content-Length', str(len(body)))
        for k, v in headers.items(): self.send_header(k, v)
        self.end_headers()
        if self.command != 'HEAD': self.wfile.write(body)

    def do_HEAD(self): self.do_GET()

    def do_GET(self):
        path = urllib.parse.urlsplit(self.path).path
        with LOCK: gens = dict(GENS)   # one snapshot: tag, notes and file always belong together
        latest = next(reversed(gens), None)
        if path == '/':
            return self.send(200, (f'{latest}  {gens[latest][0]}\n' if latest else 'nothing pushed yet\n').encode())
        if path == '/releases/latest':
            if not latest: return self.send(404, b'nothing pushed yet\n')
            return self.send(302, Location=f'http://{self.headers.get("Host", "")}/releases/tag/{latest}')
        parts = path.split('/')
        if len(parts) == 4 and parts[:3] == ['', 'releases', 'tags'] and parts[3] in gens:
            return self.send(200, json.dumps({'tag_name': parts[3], 'body': gens[parts[3]][0]}).encode(), 'application/json')
        if len(parts) == 5 and parts[:3] == ['', 'releases', 'download'] and parts[4] == 'update.bin':
            with LOCK:   # opened under the lock, so a push cannot delete it in between; an open file outlives its deletion
                try: f = open(GENS[parts[3]][1], 'rb') if parts[3] in GENS else None
                except OSError: f = None
            if not f: return self.send(404)
            with f:
                size = os.fstat(f.fileno()).st_size
                self.send_response(200)
                self.send_header('Content-Type', 'application/octet-stream'); self.send_header('Content-Length', str(size))
                self.end_headers()
                if self.command != 'HEAD':
                    try:
                        while chunk := f.read(1 << 20): self.wfile.write(chunk)
                    except (BrokenPipeError, ConnectionResetError): pass   # the device cancelled
            return None
        return self.send(404)

    def do_PUT(self):
        if self.client_address[0] not in ('127.0.0.1', '::1'): return self.send(403, b'push from this machine only\n')
        if urllib.parse.urlsplit(self.path).path != '/update.bin': return self.send(404)
        n = int(self.headers.get('Content-Length', '-1'))
        if n <= 0: return self.send(411)
        fd, tmp = tempfile.mkstemp(dir=STORE, suffix='.bin')
        try:
            with os.fdopen(fd, 'wb') as f:
                while n > 0:
                    chunk = self.rfile.read(min(n, 1 << 20))
                    if not chunk: raise ValueError('upload cut short')
                    f.write(chunk); n -= len(chunk)
            tag = package_tag(tmp)
        except (ValueError, OSError, tarfile.TarError) as e:
            os.unlink(tmp)
            return self.send(400, f'{e}\n'.encode())
        notes = urllib.parse.unquote(self.headers.get('X-Notes', ''))
        with LOCK:
            old = [GENS.pop(tag)[1]] if tag in GENS else []   # the same tag pushed again: the new file replaces it
            GENS[tag] = (notes, tmp)
            while len(GENS) > KEEP: old.append(GENS.pop(next(iter(GENS)))[1])
            for f in old: os.unlink(f)   # a download still reading one keeps its open file
        print(f'pushed {tag}: {notes}', flush=True)
        return self.send(200, f'{tag}\n'.encode())

    def log_message(self, fmt, *args):
        sys.stderr.write(f'{self.client_address[0]} {fmt % args}\n')


def lan_ip():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try: s.connect(('192.0.2.1', 9)); return s.getsockname()[0]   # no packet is sent; it picks the outgoing interface
        except OSError: return '127.0.0.1'


def serve(a):
    global STORE
    signal.signal(signal.SIGTERM, signal.default_int_handler)   # kill and Ctrl+C both delete the folder
    signal.signal(signal.SIGINT, signal.default_int_handler)
    try: srv = http.server.ThreadingHTTPServer(('0.0.0.0', a.port), Handler)
    except OSError as e: sys.exit(f'port {a.port}: {e.strerror} (is the server already running?)')
    with tempfile.TemporaryDirectory(prefix='m1plus-ota-') as STORE:
        print(f'store {STORE} (deleted on exit)\ncard file m1plus-update-url: http://{lan_ip()}:{a.port}', flush=True)
        try: srv.serve_forever()
        except KeyboardInterrupt: pass
        finally: srv.server_close()


def git(*args):
    r = subprocess.run(['git', '-C', ROOT, *args], capture_output=True, text=True)
    return r.stdout.strip()


def push(a):
    sys.path.insert(0, os.path.join(ROOT, 'tools'))
    import workflow
    pkg, m = workflow.tested_package(a.build)   # the same gate as make flash: a fully passing dev build
    notes = a.notes if a.notes is not None else f'{git("branch", "--show-current") or "detached"} {git("rev-parse", "--short", "HEAD")}: {git("log", "-1", "--format=%s")}'
    size = os.path.getsize(pkg)
    with open(pkg, 'rb') as f:
        req = urllib.request.Request(a.server.rstrip('/') + '/update.bin', data=f, method='PUT',
                                     headers={'Content-Length': str(size), 'X-Notes': urllib.parse.quote(notes)})
        try:
            with urllib.request.urlopen(req) as r: tag = r.read().decode().strip()
        except urllib.error.HTTPError as e: sys.exit(f'push refused: {e.code} {e.read().decode().strip()}')
        except urllib.error.URLError as e: sys.exit(f'no server at {a.server} ({e.reason}); start it with make ota-serve')
    print(f'pushed {m["tag"]} ({size // 1024} KiB) as {tag}: {notes}')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('serve'); s.add_argument('--port', type=int, default=8765)
    p = sub.add_parser('push'); p.add_argument('--build', default='latest'); p.add_argument('--notes')
    p.add_argument('--server', default='http://127.0.0.1:8765')
    a = ap.parse_args()
    serve(a) if a.cmd == 'serve' else push(a)


if __name__ == '__main__': main()
