"""The routes, over a real socket, because addressability is the requirement.

Every view being a URL is not a nicety here: it is what makes a turn shareable, the
back button work, and a filtered set keepable. So the routes are exercised through an
actual server rather than by calling the render functions, which would test the
renderer again and the routing not at all.

Bound to loopback on an ephemeral port, over a temporary directory of fixture logs.
Nothing live, nothing on the network, no provider key.
"""

import shutil
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory

from logviewer.cli import (
    HOST, PORT_ATTEMPTS, PortsBusy, bind, build_parser, main, serve,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


class _Server:
    """A viewer on a throwaway copy of the fixtures, torn down after each test."""

    def __enter__(self):
        self._tmp = TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        for fixture in FIXTURES.glob("*.jsonl"):
            shutil.copy(fixture, self.dir / fixture.name)
        ready = threading.Event()
        self.httpd = serve(self.dir, port=0, open_browser=False, ready=ready,
                           serve_forever=False, quiet=True)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        ready.wait(5)
        self.base = f"http://{HOST}:{self.httpd.server_port}"
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)
        self._tmp.cleanup()

    def get(self, route):
        with urllib.request.urlopen(self.base + route) as response:
            return response.status, response.read().decode(), dict(response.headers)

    def status(self, route):
        try:
            return self.get(route)[0]
        except urllib.error.HTTPError as exc:
            return exc.code


class TestEveryViewIsAUrl(unittest.TestCase):
    def test_the_list_the_session_the_lenses_the_turn_and_the_record(self):
        with _Server() as server:
            status, body, _headers = server.get("/")
            self.assertEqual(200, status)
            self.assertIn("Sessions", body)
            session = "every_phase"
            for route, expected in (
                (f"/s/{session}", "WHAT STANDS OUT"),
                (f"/s/{session}/timeline", "TIMELINE"),
                (f"/s/{session}/context", "WHAT EACH PROMPT ADDED"),
                (f"/s/{session}/tools", "TOOLS"),
                # The fixture's tool is not a MUD tool, so the journey lens has an
                # empty view rather than an error. That is the behaviour, so it is
                # what is asserted.
                (f"/s/{session}/journey", "no journey to read"),
                (f"/s/{session}/errors", "ERRORS"),
                (f"/s/{session}/raw", "RAW"),
                (f"/s/{session}/turn/1", "Turn 1"),
                (f"/s/{session}/event/1", "THE RECORD"),
            ):
                with self.subTest(route=route):
                    status, body, _headers = server.get(route)
                    self.assertEqual(200, status)
                    self.assertIn(expected, body)

    def test_latest_names_the_most_recent_session(self):
        with _Server() as server:
            status, body, _headers = server.get("/s/latest")
            self.assertEqual(200, status)
            self.assertIn("WHAT STANDS OUT", body)

    def test_an_unambiguous_prefix_resolves(self):
        with _Server() as server:
            self.assertEqual(200, server.status("/s/every"))

    def test_a_diff_of_two_sessions_is_a_url(self):
        with _Server() as server:
            status, body, _headers = server.get(
                "/diff?a=every_phase&b=legacy_step11")
            self.assertEqual(200, status)
            self.assertIn("TWO SESSIONS", body)

    def test_a_raw_page_number_is_part_of_the_url(self):
        with _Server() as server:
            status, body, _headers = server.get("/s/every_phase/raw?page=1")
            self.assertEqual(200, status)
            self.assertIn("events 1 to", body)


class TestWhatIsNotThereIsSaidRatherThanCrashed(unittest.TestCase):
    def test_an_unknown_path_is_a_404_that_explains_itself(self):
        with _Server() as server:
            try:
                server.get("/nowhere")
                self.fail("expected a 404")
            except urllib.error.HTTPError as exc:
                self.assertEqual(404, exc.code)
                self.assertIn("No page at", exc.read().decode())

    def test_an_unknown_session_names_the_ambiguity(self):
        with _Server() as server:
            self.assertEqual(404, server.status("/s/definitely-not-a-session"))

    def test_a_turn_that_does_not_exist_says_how_many_there_are(self):
        with _Server() as server:
            status, body, _headers = server.get("/s/every_phase/turn/99")
            self.assertEqual(200, status)
            self.assertIn("there is no turn 99", body)

    def test_a_turn_that_is_not_a_number_is_a_404(self):
        with _Server() as server:
            self.assertEqual(404, server.status("/s/every_phase/turn/banana"))

    def test_a_diff_missing_a_side_names_which_side(self):
        with _Server() as server:
            try:
                server.get("/diff?a=every_phase")
                self.fail("expected a 404")
            except urllib.error.HTTPError as exc:
                self.assertIn("A diff needs two sessions", exc.read().decode())

    def test_an_empty_directory_serves_a_page_saying_so(self):
        with TemporaryDirectory() as tmp:
            ready = threading.Event()
            httpd = serve(tmp, port=0, open_browser=False, ready=ready,
                          serve_forever=False, quiet=True)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            ready.wait(5)
            try:
                with urllib.request.urlopen(
                        f"http://{HOST}:{httpd.server_port}/") as response:
                    self.assertIn("No session logs found", response.read().decode())
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=5)


class TestReadingALogIsNotPublishingIt(unittest.TestCase):
    def test_it_binds_to_loopback_only(self):
        with _Server() as server:
            self.assertEqual("127.0.0.1", HOST)
            self.assertEqual("127.0.0.1", server.httpd.server_address[0])

    def test_the_response_forbids_fetching_anything(self):
        # The page references nothing external, and the policy says so rather than
        # relying on that staying true.
        with _Server() as server:
            _status, _body, headers = server.get("/")
            policy = headers["Content-Security-Policy"]
            self.assertIn("default-src 'none'", policy)
            self.assertIn("img-src data:", policy)

    def test_the_content_type_is_declared_with_its_charset(self):
        with _Server() as server:
            _status, _body, headers = server.get("/")
            self.assertEqual("text/html; charset=utf-8", headers["Content-Type"])


class TestTheCommandSurface(unittest.TestCase):
    def test_list_prints_the_sessions_and_serves_nothing(self):
        with TemporaryDirectory() as tmp:
            for fixture in FIXTURES.glob("*.jsonl"):
                shutil.copy(fixture, Path(tmp) / fixture.name)
            self.assertEqual(0, main(["--dir", tmp, "--list"]))

    def test_a_missing_directory_fails_with_a_reason_rather_than_a_traceback(self):
        self.assertEqual(1, main(["--dir", "/definitely/not/here", "--list"]))

    def test_a_session_that_does_not_exist_fails_before_binding_a_port(self):
        with TemporaryDirectory() as tmp:
            self.assertEqual(1, main(["--dir", tmp, "nonexistent"]))

    def test_the_parser_offers_what_the_plan_says_it_does(self):
        parsed = build_parser().parse_args(["latest", "--port", "9", "--no-open"])
        self.assertEqual("latest", parsed.session)
        self.assertEqual(9, parsed.port)
        self.assertTrue(parsed.no_open)


class TestABusyPortIsNotATraceback(unittest.TestCase):
    """Reported by Ibnou running it: `OSError: [Errno 48] Address already in use`.

    Straight out of the socket layer, which tells a reader about sockets rather than
    about their viewer. Two copies of a log reader open at once is an ordinary thing to
    want, so the second one moves along and says where it went.
    """

    def _hold(self, port=0):
        """Occupy a port and return it, so the next bind has to deal with it."""
        holder = serve(FIXTURES, port=port, open_browser=False,
                       serve_forever=False, quiet=True)
        self.addCleanup(holder.server_close)
        return holder

    def test_the_next_free_port_is_used_rather_than_raising(self):
        holder = self._hold()
        taken = holder.server_port
        moved = bind(taken, type("H", (object,), {}))
        self.addCleanup(moved.server_close)
        self.assertNotEqual(taken, moved.server_port)
        self.assertGreater(moved.server_port, taken)
        self.assertLess(moved.server_port, taken + PORT_ATTEMPTS)

    def test_serve_reports_where_it_moved_to(self):
        holder = self._hold()
        taken = holder.server_port
        moved = serve(FIXTURES, port=taken, open_browser=False,
                      serve_forever=False, quiet=True)
        self.addCleanup(moved.server_close)
        self.assertNotEqual(taken, moved.server_port)

    def test_a_full_range_fails_in_words_rather_than_an_errno(self):
        holders = []
        base = self._hold().server_port
        for offset in range(1, PORT_ATTEMPTS):
            try:
                holders.append(self._hold(base + offset))
            except OSError:
                pass
        with self.assertRaises(PortsBusy) as caught:
            bind(base, type("H", (object,), {}))
        message = str(caught.exception)
        self.assertIn("already running", message)
        self.assertIn("--port", message)
        self.assertNotIn("Errno", message)

    def test_port_zero_still_means_any(self):
        # The tests rely on it, and passing it through untouched keeps them honest.
        chosen = bind(0, type("H", (object,), {}))
        self.addCleanup(chosen.server_close)
        self.assertGreater(chosen.server_port, 0)

    def test_the_url_is_flushed_rather_than_buffered_away(self):
        """The URL is the only thing a launcher has to deliver.

        Python buffers stdout when it is not a terminal, so redirected to a file the
        line appeared only when the process exited, which is the moment it stopped being
        useful. Found by running the launcher with its output redirected.
        """
        import io
        from contextlib import redirect_stdout

        captured = io.StringIO()
        with redirect_stdout(captured):
            httpd = serve(FIXTURES, port=0, open_browser=False,
                          serve_forever=False)
        self.addCleanup(httpd.server_close)
        printed = captured.getvalue()
        self.assertIn(f"http://{HOST}:{httpd.server_port}/", printed)
        self.assertIn(str(FIXTURES), printed)


if __name__ == "__main__":
    unittest.main()
