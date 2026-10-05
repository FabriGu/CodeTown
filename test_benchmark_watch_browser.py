"""Benchmark for watch --browser: fixture repo, one second, must stay under limits."""
import io
import os
import shutil
import tempfile
import unittest
from unittest import mock

from scripts import benchmark_watch_browser as bench


class BenchmarkWatchBrowserTest(unittest.TestCase):
    def test_fixture_stays_under_limits(self):
        out = io.StringIO()
        with mock.patch("sys.stdout", out):
            code = bench.main(["--seconds", "1"])
        self.assertEqual(code, 0)
        line = out.getvalue().strip()
        self.assertRegex(line, r"^town\.json: \d+ bytes; simulation: .+ of one core over 1 s \(\d+ Clawds\)$")

    def test_watch_live_failure_restores_env_when_unset(self):
        repo = bench._fixture()
        saved = os.environ.pop("TOWNCODE_SURVEY_DIR", None)
        try:
            with mock.patch.object(bench.towncode, "_watch_live", side_effect=RuntimeError("boom")):
                with self.assertRaises(RuntimeError):
                    bench.measure(repo, 0.1)
            self.assertNotIn("TOWNCODE_SURVEY_DIR", os.environ)
        finally:
            shutil.rmtree(repo, ignore_errors=True)
            if saved is not None:
                os.environ["TOWNCODE_SURVEY_DIR"] = saved

    def test_watch_live_failure_restores_prior_env(self):
        repo = bench._fixture()
        prior = tempfile.mkdtemp(prefix="towncode-bench-prior-")
        saved = os.environ.get("TOWNCODE_SURVEY_DIR")
        os.environ["TOWNCODE_SURVEY_DIR"] = prior
        try:
            with mock.patch.object(bench.towncode, "_watch_live", side_effect=RuntimeError("boom")):
                with self.assertRaises(RuntimeError):
                    bench.measure(repo, 0.1)
            self.assertEqual(os.environ.get("TOWNCODE_SURVEY_DIR"), prior)
        finally:
            shutil.rmtree(repo, ignore_errors=True)
            shutil.rmtree(prior, ignore_errors=True)
            if saved is None:
                os.environ.pop("TOWNCODE_SURVEY_DIR", None)
            else:
                os.environ["TOWNCODE_SURVEY_DIR"] = saved


if __name__ == "__main__":
    unittest.main()
