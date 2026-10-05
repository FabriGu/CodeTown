"""The 3D town's web server: the page, its files, the town document and selection answers.

It listens on 127.0.0.1 only and answers GET only. A request naming any other Host is refused,
which blocks DNS rebinding. Static files come from a fixed table, so no request reaches a file
outside web/. Every response carries a strict Content-Security-Policy.
"""

import base64
import errno
import hashlib
import json
import os
import queue
import re
import threading
import time
import traceback
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import townjson

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(HERE, "web")
DEFAULT_PORT = 8765
JS = "text/javascript; charset=utf-8"
TEXT = "text/plain; charset=utf-8"
TICK = 0.1
HEARTBEAT = 15.0
MAX_BEHIND = 100
HEARTBEAT_BYTES = b": heartbeat\n\n"
EVENTS = "text/event-stream; charset=utf-8"
STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/static/town3d.css": ("town3d.css", "text/css; charset=utf-8"),
    "/static/town3d.js": ("town3d.js", JS),
    "/static/look.js": ("look.js", JS),
    "/static/live.js": ("live.js", JS),
    "/static/transit.js": ("transit.js", JS),
    "/static/vendor/three.module.js": ("vendor/three.module.js", JS),
    "/static/vendor/three.core.js": ("vendor/three.core.js", JS),
    "/static/vendor/OrbitControls.js": ("vendor/OrbitControls.js", JS),
}
IMPORT_MAP = re.compile(r'<script type="importmap">(.*?)</script>', re.S)


class Site:
    """What the server hands out: the town document, and what a selection lights up."""

    def __init__(self, town, select):
        self.town = town
        self.select = select


def sse(kind, data):
    """One Server-Sent Event. json.dumps escapes newlines, so data stays on one line."""
    body = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    return f"event: {kind}\ndata: {body}\n\n".encode("utf-8")


class LiveSite(Site):
    """A Site whose town moves: it keeps the latest state and a queue per /events client."""

    def __init__(self, town, select):
        super().__init__(town, select)
        self._lock = threading.Lock()
        self._clients = set()
        self._state = None
        self.closed = False

    def subscribe(self):
        q = queue.Queue()
        with self._lock:
            if self.closed:
                q.put(None)
            else:
                self._clients.add(q)
            return q, self._state

    def unsubscribe(self, q):
        with self._lock:
            self._clients.discard(q)

    def publish(self, state):
        with self._lock:
            self._state = state

    def retown(self, town, select):
        with self._lock:
            self.town, self.select = town, select

    def broadcast(self, kind, data):
        message = sse(kind, data)
        with self._lock:
            for q in list(self._clients):
                if q.qsize() >= MAX_BEHIND:
                    self._clients.discard(q)
                    q.put(None)
                else:
                    q.put(message)

    def close(self):
        with self._lock:
            self.closed = True
            for q in self._clients:
                q.put(None)
            self._clients.clear()


class Simulation(threading.Thread):
    """Steps the live town every TICK and streams what changed. The only thread that touches it."""

    name = "Simulation"

    def __init__(self, live, director, site, snapshots, build_town, *, clock=time.monotonic,
                 interval=TICK):
        super().__init__(daemon=True)
        self._live, self._director, self._site = live, director, site
        self._snapshots, self._build_town = snapshots, build_town
        self._clock, self._interval = clock, interval
        self._version = live.version
        self._prev = None
        self._halt = threading.Event()

    def step_once(self, dt, now):
        while True:
            try:
                snapshot = self._snapshots.get_nowait()
            except queue.Empty:
                break
            events = self._live.ingest(snapshot)
            if events:
                self._director.apply_events(events, self._live.t)
        self._live.step(dt, now)
        self._director.step(dt, now)
        if self._live.version != self._version:
            self._version = self._live.version
            self._site.retown(*self._build_town(self._live))
            self._site.broadcast("town", townjson.town_message(self._version, now))
        cur = townjson.live_state(self._live, self._director)
        self._site.publish(townjson.state_message(cur, now))
        if self._prev is not None:
            tick = townjson.tick_message(self._prev, cur, now)
            if tick is not None:
                self._site.broadcast("tick", tick)
        self._prev = cur

    def run(self):
        start = self._clock()
        prev = self._live.t
        while not self._halt.wait(self._interval):
            now = self._clock() - start
            try:
                self.step_once(now - prev, now)
            except Exception as e:
                traceback.print_exc()
                with self._site._lock:
                    state = self._site._state
                    line1 = state.get("status", ["", ""])[0] if state else ""
                err_line = f"live updates stopped: {type(e).__name__}: {e} (see the terminal)"
                if self._prev is not None:
                    cur = {**self._prev, "status": [line1, err_line]}
                else:
                    cur = townjson.live_state(self._live, self._director)
                    cur["status"] = [line1, err_line]
                self._site.publish(townjson.state_message(cur, now))
                self._site.broadcast("tick", {"t": now, "status": [line1, err_line]})
                return
            prev = now

    def stop(self):
        self._halt.set()


def import_map_hash(html):
    """The CSP source for the page's one inline script, its import map."""
    found = IMPORT_MAP.search(html)
    if not found:
        raise ValueError("web/index.html has no import map")
    digest = hashlib.sha256(found.group(1).encode("utf-8")).digest()
    return "'sha256-" + base64.b64encode(digest).decode("ascii") + "'"


def policy(html):
    return ("default-src 'self'; "
            f"script-src 'self' {import_map_hash(html)}; "
            "style-src 'self'; img-src 'self' data:; connect-src 'self'; "
            "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")


class Handler(BaseHTTPRequestHandler):
    server_version = "towncode"
    sys_version = ""

    def log_message(self, format, *args):
        pass

    def _send(self, code, body, kind, allow=None):
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Security-Policy", self.server.policy)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        if allow:
            self.send_header("Allow", allow)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, value):
        self._send(200, json.dumps(value, separators=(",", ":")).encode("utf-8"),
                   "application/json")

    def _not_found(self):
        self._send(404, b"not found\n", TEXT)

    def _events(self):
        site = self.server.site
        if not isinstance(site, LiveSite):
            return self._not_found()
        q, state = site.subscribe()
        try:
            self.send_response(200)
            self.send_header("Content-Type", EVENTS)
            self.send_header("Content-Security-Policy", self.server.policy)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if state is not None:
                self.wfile.write(sse("state", state))
                self.wfile.flush()
            while True:
                try:
                    message = q.get(timeout=self.server.heartbeat)
                except queue.Empty:
                    message = HEARTBEAT_BYTES
                if message is None:
                    return
                self.wfile.write(message)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return
        finally:
            site.unsubscribe(q)

    def do_GET(self):
        if self.headers.get("Host") not in self.server.hosts:
            return self._send(403, b"forbidden\n", TEXT)
        path, _, query = self.path.partition("?")
        if path == "/events":
            return self._events()
        if path == "/town.json":
            return self._json(self.server.site.town)
        if path == "/focus":
            return self._focus(urllib.parse.parse_qs(query))
        entry = STATIC.get(path)
        if entry is None:
            return self._not_found()
        name, kind = entry
        try:
            with open(os.path.join(WEB, name), "rb") as f:
                body = f.read()
        except FileNotFoundError:
            return self._not_found()
        self._send(200, body, kind)

    def _focus(self, query):
        module = query.get("module", [None])[0]
        package = query.get("package", [None])[0]
        answer = None
        if (module is None) != (package is None):
            answer = self.server.site.select(module=module, package=package)
        if answer is None:
            return self._not_found()
        self._json(answer)

    def _refuse(self):
        self._send(405, b"GET only\n", TEXT, allow="GET")

    do_POST = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = do_HEAD = _refuse


class Server(ThreadingHTTPServer):
    daemon_threads = True
    # Two towncode servers must never share a port.
    allow_reuse_port = False

    def __init__(self, site, port):
        with open(os.path.join(WEB, "index.html"), encoding="utf-8") as f:
            self.policy = policy(f.read())
        super().__init__(("127.0.0.1", port), Handler)
        self.site = site
        self.heartbeat = HEARTBEAT
        bound = self.server_address[1]
        self.hosts = {f"127.0.0.1:{bound}", f"localhost:{bound}"}


def make_server(site, port=DEFAULT_PORT):
    try:
        return Server(site, port)
    except OSError as e:
        if e.errno == errno.EADDRINUSE:
            raise SystemExit(f"Port {port} is in use. Try --port 0 to pick any free port.")
        raise


def serve(site, port=DEFAULT_PORT, *, open_browser=True, opener=webbrowser.open,
          on_close=None):
    """Serve until Ctrl-C, after printing the address and opening it in a browser."""
    try:
        server = make_server(site, port)
        try:
            url = f"http://127.0.0.1:{server.server_address[1]}/"
            print(f"Town at {url}  (Ctrl-C to stop)", flush=True)
            if open_browser and not opener(url):
                print("Couldn't open a browser. Open the address above.", flush=True)
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            if isinstance(site, LiveSite):
                site.close()
            server.server_close()
    finally:
        if on_close is not None:
            on_close()
    return 0
