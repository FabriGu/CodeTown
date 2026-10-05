import contextlib
import http.client
import io
import json
import queue
import threading
import unittest
from unittest import mock

import townjson
import webserve


def _site():
    return webserve.LiveSite({"version": 1, "live": True}, lambda **kw: None)


def _read_message(resp):
    kind, data = None, None
    while True:
        line = resp.fp.readline().decode("utf-8")
        if not line:
            raise EOFError("the stream ended")
        if line == "\n" and (kind or data):
            return kind, data
        if line.startswith(":"):
            return "comment", line.strip()
        if line.startswith("event: "):
            kind = line[7:].strip()
        elif line.startswith("data: "):
            data = json.loads(line[6:])


class FramingTest(unittest.TestCase):
    def test_one_event_line_one_data_line_and_a_blank_line(self):
        raw = webserve.sse("tick", {"t": 1.5, "status": ["a\nb", "c"]})
        self.assertEqual(raw.decode("utf-8"),
                         'event: tick\ndata: {"t":1.5,"status":["a\\nb","c"]}\n\n')

    def test_the_heartbeat_is_a_comment(self):
        self.assertEqual(webserve.HEARTBEAT_BYTES, b": heartbeat\n\n")


class LiveSiteTest(unittest.TestCase):
    def test_a_new_client_gets_the_latest_state(self):
        site = _site()
        site.publish({"t": 0.0, "clawds": []})
        q, state = site.subscribe()
        self.assertEqual(state, {"t": 0.0, "clawds": []})

    def test_broadcast_reaches_every_client(self):
        site = _site()
        a, _ = site.subscribe()
        b, _ = site.subscribe()
        site.broadcast("tick", {"t": 1.0})
        self.assertEqual(a.get_nowait(), webserve.sse("tick", {"t": 1.0}))
        self.assertEqual(b.get_nowait(), webserve.sse("tick", {"t": 1.0}))

    def test_a_client_too_far_behind_is_dropped(self):
        site = _site()
        q, _ = site.subscribe()
        for i in range(webserve.MAX_BEHIND + 1):
            site.broadcast("tick", {"t": float(i)})
        items = [q.get_nowait() for _ in range(q.qsize())]
        self.assertIsNone(items[-1])
        site.broadcast("tick", {"t": 999.0})
        self.assertTrue(q.empty())

    def test_close_ends_every_stream(self):
        site = _site()
        q, _ = site.subscribe()
        site.close()
        self.assertIsNone(q.get_nowait())


class FakeLive:
    def __init__(self, *, fail_on_step=None):
        self.version, self.t, self.ingested, self.steps = 1, 0.0, [], []
        self._fail_on_step = fail_on_step
        self._step_n = 0

    def ingest(self, snapshot):
        self.ingested.append(snapshot)
        return ["ev"]

    def step(self, dt, now):
        self._step_n += 1
        if self._fail_on_step == self._step_n:
            raise RuntimeError("boom")
        self.t = now
        self.steps.append((dt, now))
        return False


class FakeDirector:
    def __init__(self):
        self.applied, self.steps = [], []

    def apply_events(self, events, now):
        self.applied.append(events)

    def step(self, dt, now):
        self.steps.append(now)


class SimulationTest(unittest.TestCase):
    def setUp(self):
        self.live, self.director, self.site = FakeLive(), FakeDirector(), _site()
        self.snapshots = queue.Queue()
        self.states = [{"version": 1, "clawds": {}, "scaffold": {}, "sites": [], "flags": [],
                        "status": ["a", ""], "camera": None}]
        self.builds = []
        patcher = mock.patch.object(townjson, "live_state",
                                    side_effect=lambda live, d: self.states[-1])
        patcher.start()
        self.addCleanup(patcher.stop)
        self.sim = webserve.Simulation(self.live, self.director, self.site, self.snapshots,
                                       lambda live: self.builds.append(live.version) or
                                       ({"version": live.version}, None))

    def test_a_step_drains_snapshots_into_the_town_and_the_director(self):
        self.snapshots.put("snap")
        self.sim.step_once(0.1, 0.1)
        self.assertEqual(self.live.ingested, ["snap"])
        self.assertEqual(self.director.applied, [["ev"]])
        self.assertEqual(self.director.steps, [0.1])

    def test_the_first_step_publishes_state_and_sends_no_tick(self):
        q, _ = self.site.subscribe()
        self.sim.step_once(0.0, 0.0)
        self.assertTrue(q.empty())
        _, state = self.site.subscribe()
        self.assertEqual(state["status"], ["a", ""])

    def test_a_change_is_broadcast_as_a_tick(self):
        self.sim.step_once(0.0, 0.0)
        q, _ = self.site.subscribe()
        self.states.append({**self.states[-1], "status": ["b", ""]})
        self.sim.step_once(0.1, 0.1)
        self.assertEqual(q.get_nowait(),
                         webserve.sse("tick", {"status": ["b", ""], "t": 0.1}))

    def test_a_new_version_rebuilds_the_town_and_sends_town(self):
        self.sim.step_once(0.0, 0.0)
        q, _ = self.site.subscribe()
        self.live.version = 2
        self.sim.step_once(0.1, 0.1)
        self.assertEqual(self.builds, [2])
        self.assertEqual(self.site.town, {"version": 2})
        self.assertEqual(q.get_nowait(), webserve.sse("town", {"t": 0.1, "version": 2}))

    def test_a_step_exception_stops_the_sim_and_broadcasts_the_error(self):
        live = FakeLive(fail_on_step=2)
        sim = webserve.Simulation(live, FakeDirector(), self.site, self.snapshots,
                                  lambda live: ({}, None), interval=0.01)
        sim.step_once(0.0, 0.0)
        q, _ = self.site.subscribe()
        sim.start()
        sim.join(timeout=2)
        self.assertFalse(sim.is_alive())
        head, data = q.get_nowait().decode("utf-8").split("\n")[:2]
        kind, tick = head[len("event: "):], json.loads(data[len("data: "):])
        self.assertEqual(kind, "tick")
        self.assertTrue(tick["status"][1].startswith("live updates stopped: "))
        self.assertIn("RuntimeError", tick["status"][1])
        self.assertEqual(tick["status"][0], "a")
        _, state = self.site.subscribe()
        self.assertEqual(state["status"][1], tick["status"][1])


class EventsEndpointTest(unittest.TestCase):
    def setUp(self):
        self.site = _site()
        self.site.publish({"t": 0.0, "version": 1, "clawds": [], "scaffold": {}, "sites": [],
                           "flags": [], "status": ["hello", ""], "camera": None})
        self.server = webserve.make_server(self.site, 0)
        self.server.heartbeat = 0.2
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.addCleanup(self.site.close)

    def _open(self, host=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", "/events", headers={"Host": host or f"127.0.0.1:{self.port}"})
        return conn.getresponse()

    def test_events_starts_with_state_then_ticks_and_heartbeats(self):
        resp = self._open()
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.getheader("Content-Type"), "text/event-stream; charset=utf-8")
        self.assertIn("default-src 'self'", resp.getheader("Content-Security-Policy"))
        self.assertIsNone(resp.getheader("Access-Control-Allow-Origin"))
        kind, data = _read_message(resp)
        self.assertEqual((kind, data["status"]), ("state", ["hello", ""]))
        self.site.broadcast("tick", {"t": 1.0, "camera": "a"})
        self.assertEqual(_read_message(resp), ("tick", {"t": 1.0, "camera": "a"}))
        self.assertEqual(_read_message(resp), ("comment", ": heartbeat"))

    def test_events_refuses_another_host(self):
        self.assertEqual(self._open(host="evil.example:80").status, 403)

    def test_a_static_site_has_no_events(self):
        plain = webserve.make_server(webserve.Site({}, lambda **kw: None), 0)
        threading.Thread(target=plain.serve_forever, daemon=True).start()
        self.addCleanup(plain.server_close)
        self.addCleanup(plain.shutdown)
        port = plain.server_address[1]
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/events", headers={"Host": f"127.0.0.1:{port}"})
        self.assertEqual(conn.getresponse().status, 404)

    def test_live_js_is_served_and_its_test_is_not(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        for path, status in (("/static/live.js", 200), ("/static/live.test.mjs", 404)):
            conn.request("GET", path, headers={"Host": f"127.0.0.1:{self.port}"})
            resp = conn.getresponse()
            resp.read()
            self.assertEqual(resp.status, status, path)


class ServeClosesTest(unittest.TestCase):
    def test_ctrl_c_closes_the_site_and_calls_on_close(self):
        site, closed = _site(), []
        with mock.patch.object(webserve.Server, "serve_forever", side_effect=KeyboardInterrupt), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(webserve.serve(site, 0, open_browser=False,
                                            on_close=lambda: closed.append(True)), 0)
        self.assertEqual(closed, [True])
        self.assertTrue(site.closed)

    def test_a_port_in_use_still_calls_on_close(self):
        closed = []
        with mock.patch.object(webserve, "make_server", side_effect=SystemExit("in use")):
            with self.assertRaises(SystemExit):
                webserve.serve(_site(), 0, open_browser=False,
                               on_close=lambda: closed.append(True))
        self.assertEqual(closed, [True])


if __name__ == "__main__":
    unittest.main()
