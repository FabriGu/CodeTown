import base64
import contextlib
import hashlib
import http.client
import io
import json
import os
import re
import socket
import threading
import unittest
from unittest import mock

import webserve

TOWN = {"version": 1, "repo": "fake", "buildings": []}


def select(module=None, package=None):
    if module == "a.py":
        return {"focused": ["a.py"], "dim": {"a.py": 1.0}, "lit": []}
    if package == "flask":
        return {"focused": [], "dim": {}, "lit": []}
    return None


SITE = webserve.Site(TOWN, select)


def page():
    with open(os.path.join(webserve.WEB, "index.html"), encoding="utf-8") as f:
        return f.read()


class ServerTest(unittest.TestCase):
    def setUp(self):
        self.server = webserve.make_server(SITE, 0)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def request(self, path, method="GET", host="here"):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        self.addCleanup(conn.close)
        conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
        if host == "here":
            host = f"127.0.0.1:{self.port}"
        if host is not None:
            conn.putheader("Host", host)
        conn.endheaders()
        response = conn.getresponse()
        return response, response.read()

    def test_it_listens_on_this_machine_only(self):
        self.assertEqual(self.server.server_address[0], "127.0.0.1")

    def test_the_page_comes_with_a_strict_policy_and_no_cors(self):
        r, body = self.request("/")
        self.assertEqual(r.status, 200)
        self.assertEqual(r.getheader("Content-Type"), "text/html; charset=utf-8")
        self.assertEqual(body.decode("utf-8"), page())
        self.assertEqual(r.getheader("Content-Security-Policy"), webserve.policy(page()))
        self.assertEqual(r.getheader("X-Content-Type-Options"), "nosniff")
        self.assertEqual(r.getheader("Referrer-Policy"), "no-referrer")
        self.assertEqual(r.getheader("Cache-Control"), "no-store")
        self.assertIsNone(r.getheader("Access-Control-Allow-Origin"))

    def test_the_policy_allows_the_import_map_and_nothing_else_inline(self):
        html = page()
        inline = re.search(r'<script type="importmap">(.*?)</script>', html, re.S).group(1)
        digest = base64.b64encode(hashlib.sha256(inline.encode("utf-8")).digest()).decode()
        self.assertEqual(webserve.policy(html),
                         "default-src 'self'; "
                         f"script-src 'self' 'sha256-{digest}'; "
                         "style-src 'self'; img-src 'self' data:; connect-src 'self'; "
                         "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
        self.assertEqual(len(re.findall(r"<script(?![^>]*\bsrc=)", html)), 1)
        self.assertNotIn("style=", html)
        self.assertNotRegex(html, r"\son[a-z]+=")

    def test_the_import_map_points_only_at_served_files(self):
        inline = re.search(r'<script type="importmap">(.*?)</script>', page(), re.S).group(1)
        for target in json.loads(inline)["imports"].values():
            self.assertIn(target, webserve.STATIC)

    def test_town_json_is_the_sites_town(self):
        r, body = self.request("/town.json")
        self.assertEqual((r.status, r.getheader("Content-Type")), (200, "application/json"))
        self.assertEqual(json.loads(body), TOWN)

    def test_focus_answers_one_known_module_or_package(self):
        r, body = self.request("/focus?module=a.py")
        self.assertEqual((r.status, json.loads(body)["focused"]), (200, ["a.py"]))
        r, body = self.request("/focus?package=flask")
        self.assertEqual((r.status, json.loads(body)["focused"]), (200, []))

    def test_focus_needs_exactly_one_known_name(self):
        for path in ("/focus", "/focus?module=nope.py", "/focus?package=nope",
                     "/focus?module=a.py&package=flask", "/focus?module="):
            self.assertEqual(self.request(path)[0].status, 404, path)

    def test_vendored_three_is_served_as_javascript(self):
        r, body = self.request("/static/vendor/three.module.js")
        self.assertEqual((r.status, r.getheader("Content-Type")),
                         (200, "text/javascript; charset=utf-8"))
        self.assertIn(b"three.core.js", body)

    def test_unknown_and_escaping_paths_are_not_found(self):
        for path in ("/static/../towncode.py", "/towncode.py", "/static/nope.js",
                     "//evil.example/town.json", "/web/index.html", "/static/vendor/VERSION"):
            self.assertEqual(self.request(path)[0].status, 404, path)

    def test_requests_for_another_host_are_refused(self):
        for host in ("evil.example", f"evil.example:{self.port}", "127.0.0.1", None):
            self.assertEqual(self.request("/town.json", host=host)[0].status, 403, host)
        self.assertEqual(self.request("/town.json", host=f"localhost:{self.port}")[0].status, 200)

    def test_only_get_is_allowed(self):
        for method in ("POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"):
            r, body = self.request("/town.json", method=method)
            self.assertEqual((r.status, r.getheader("Allow")), (405, "GET"), method)
        self.assertEqual(self.request("/", method="HEAD")[1], b"")

    def test_every_static_file_exists(self):
        for path, (name, _) in webserve.STATIC.items():
            self.assertTrue(os.path.isfile(os.path.join(webserve.WEB, name)), path)


class StartTest(unittest.TestCase):
    def test_a_busy_port_says_how_to_pick_another(self):
        busy = socket.socket()
        self.addCleanup(busy.close)
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        with self.assertRaises(SystemExit) as caught:
            webserve.make_server(SITE, busy.getsockname()[1])
        self.assertIn("--port 0", str(caught.exception))

    def serve(self, **options):
        opened = []
        out = io.StringIO()
        with mock.patch.object(webserve.Server, "serve_forever", side_effect=KeyboardInterrupt), \
                contextlib.redirect_stdout(out):
            code = webserve.serve(SITE, 0, opener=lambda url: opened.append(url) or True, **options)
        return code, out.getvalue(), opened

    def test_serve_prints_the_address_and_opens_it(self):
        code, out, opened = self.serve()
        url = re.search(r"http://127\.0\.0\.1:\d+/", out).group(0)
        self.assertEqual((code, opened), (0, [url]))

    def test_serve_can_leave_the_browser_closed(self):
        code, out, opened = self.serve(open_browser=False)
        self.assertEqual((code, opened), (0, []))
        self.assertIn("http://127.0.0.1:", out)


if __name__ == "__main__":
    unittest.main()
