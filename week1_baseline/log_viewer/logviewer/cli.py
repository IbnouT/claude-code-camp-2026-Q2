"""The command surface and the server behind it.

`http.server` from the standard library, because routing a handful of local pages is
not a reason to take a web framework. Reading a log is not publishing it, so this binds
to localhost, makes no network call, and needs no provider key.

Routing is the whole of the addressability requirement, so it is small on purpose:

    /                        the session list
    /s/<id>                  one session, narrative lens
    /s/<id>/<lens>           one session, one of the seven lenses
    /s/<id>/raw?page=<n>     a page of the record
    /s/<id>/turn/<n>         one turn, everything the log holds about it
    /s/<id>/event/<line>     one record in full, by line number
    /diff?a=<id>&b=<id>      two sessions side by side

Every page is a GET with no state on the server. The back button works, a link can be
kept, and the same URL renders the same page from the same file.
"""

from __future__ import annotations

import argparse
import errno
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import logweb
from .logview import read
from .sessions import default_dir, list_sessions, resolve

#: Bound to loopback, not chosen by convenience. A log carries the system prompt, the
#: whole conversation, and what it cost, and none of that is for the network.
HOST = "127.0.0.1"
DEFAULT_PORT = 8713


class _Handler(BaseHTTPRequestHandler):
    """One request, one page, no state.

    The sessions directory is read on EVERY request rather than cached at startup, so a
    run that finishes while the viewer is open shows up on a refresh. That is the whole
    of "live" here, and it costs one directory listing.
    """

    server_version = "boukensha-logviewer"
    directory: Path = Path()

    def log_message(self, fmt, *args):  # noqa: A003 - silence the default access log
        pass

    def do_GET(self) -> None:  # noqa: N802 - the base class names it
        parsed = urlparse(self.path)
        parts = [unquote(p) for p in parsed.path.strip("/").split("/") if p]
        try:
            status, body = self._route(parts, parse_qs(parsed.query))
        except Exception as exc:  # noqa: BLE001 - a viewer must not die on one page
            status, body = 500, logweb.page(
                "Error", f"<section class=\"card\"><p class=\"empty\">"
                f"{logweb.esc(f'{type(exc).__name__}: {exc}')}</p></section>")
        raw = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        # Nothing here is fetched, so nothing may be. The policy says so rather than
        # relying on the page happening not to reference anything.
        self.send_header("Content-Security-Policy",
                         "default-src 'none'; style-src 'unsafe-inline'; "
                         "script-src 'unsafe-inline'; img-src data:")
        self.end_headers()
        self.wfile.write(raw)

    def _route(self, parts: list[str], query: dict[str, list[str]]
               ) -> tuple[int, str]:
        if not parts:
            return 200, logweb.sessions_page(list_sessions(self.directory))
        if parts[0] == "diff":
            return self._diff(query)
        if parts[0] == "s" and len(parts) >= 2:
            return self._session(parts[1], parts[2:], query)
        return 404, self._missing(f"No page at /{'/'.join(parts)}.")

    def _session(self, name: str, rest: list[str],
                 query: dict[str, list[str]]) -> tuple[int, str]:
        summary = resolve(name, self.directory)
        if summary is None:
            return 404, self._missing(
                f"No session matches {name!r}. Try the list, or a longer prefix if "
                f"more than one session starts the same way.")
        records = read(summary.path).records
        if rest and rest[0] == "turn":
            number = rest[1] if len(rest) > 1 else ""
            if not number.isdigit():
                return 404, self._missing(f"{number!r} is not a turn number.")
            return 200, logweb.turn_page(records, summary, int(number))
        if rest and rest[0] == "event":
            line = rest[1] if len(rest) > 1 else ""
            if not line.isdigit():
                return 404, self._missing(f"{line!r} is not a line number.")
            return 200, logweb.event_page(records, summary, int(line))
        lens = rest[0] if rest else "narrative"
        page_number = (query.get("page") or ["1"])[0]
        return 200, logweb.session_page(
            records, summary, lens,
            int(page_number) if page_number.isdigit() else 1)

    def _diff(self, query: dict[str, list[str]]) -> tuple[int, str]:
        left_name = (query.get("a") or [""])[0]
        right_name = (query.get("b") or [""])[0]
        left = resolve(left_name, self.directory) if left_name else None
        right = resolve(right_name, self.directory) if right_name else None
        missing = [n for n, s in ((left_name, left), (right_name, right)) if s is None]
        if missing:
            return 404, self._missing(
                "A diff needs two sessions this directory holds. "
                f"Not found: {', '.join(repr(m) for m in missing) or 'both'}.")
        return 200, logweb.diff_page(read(left.path).records,
                                     read(right.path).records, left, right)

    def _missing(self, message: str) -> str:
        return logweb.page(
            "Not found",
            f"<section class=\"card\"><p class=\"empty\">{logweb.esc(message)}</p>"
            f"<p><a href=\"/\">← every session</a></p></section>",
            crumb="log viewer")


#: How many ports past the requested one to try before giving up. A viewer is a thing
#: someone opens more than once, so a second copy finding the first one's port busy is
#: ordinary rather than exceptional, and an ordinary situation should not need a flag.
PORT_ATTEMPTS = 12


def bind(port: int, handler: type) -> ThreadingHTTPServer:
    """Bind the first free port at or after ``port``.

    A busy port used to raise `OSError: [Errno 48] Address already in use` straight out
    of the socket layer, which told the reader about sockets rather than about their
    viewer. Two copies of a log reader is a normal thing to want, so the second one moves
    along and says where it went.

    Port 0 means "any", which the caller uses in tests, and is passed through untouched.
    """
    if port == 0:
        return ThreadingHTTPServer((HOST, 0), handler)
    last: OSError | None = None
    for offset in range(PORT_ATTEMPTS):
        try:
            return ThreadingHTTPServer((HOST, port + offset), handler)
        except OSError as exc:
            if exc.errno not in (errno.EADDRINUSE, errno.EACCES):
                raise
            last = exc
    raise PortsBusy(port, port + PORT_ATTEMPTS - 1) from last


class PortsBusy(RuntimeError):
    """Every port in the range was taken, said in words rather than as an errno."""

    def __init__(self, first: int, last: int) -> None:
        super().__init__(
            f"ports {first} to {last} are all in use. Another log viewer is probably "
            f"already running, so open it instead, or pass --port to choose one.")
        self.first = first
        self.last = last


def serve(directory: Path, port: int = DEFAULT_PORT, open_browser: bool = True,
          at: str | None = None, ready: threading.Event | None = None,
          serve_forever: bool = True, quiet: bool = False) -> ThreadingHTTPServer:
    """Start the viewer. Returns the server so a test can stop it.

    ``serve_forever`` is false in tests, which need the socket bound and nothing
    blocking. The default is the real thing: a launcher hands over control and does not
    come back.
    """
    handler = type("Handler", (_Handler,), {"directory": Path(directory)})
    httpd = bind(port, handler)
    url = f"http://{HOST}:{httpd.server_port}/" + (f"s/{at}" if at else "")
    if not quiet:
        # Flushed, because the URL is the only thing a launcher has to deliver and
        # Python buffers stdout when it is not a terminal. Redirected to a file it
        # otherwise appears only when the process exits, which is the moment it stops
        # being useful.
        if port and httpd.server_port != port:
            print(f"port {port} was busy, using {httpd.server_port}", flush=True)
        print(f"log viewer reading {directory}", flush=True)
        print(f"  {url}", flush=True)
    if open_browser:
        threading.Thread(target=lambda: webbrowser.open(url), daemon=True).start()
    if ready is not None:
        ready.set()
    if serve_forever:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")
        finally:
            httpd.server_close()
    return httpd


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="log_viewer",
        description="Read a boukensha session log and make it answerable.")
    parser.add_argument("session", nargs="?", default=None,
                        help="a session id, a prefix of one, or 'latest'")
    parser.add_argument("--dir", default=None,
                        help="the sessions directory (default: the nearest "
                             ".boukensha/sessions walking up)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-open", action="store_true",
                        help="do not launch a browser")
    parser.add_argument("--list", action="store_true",
                        help="print the sessions and exit, without serving")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    directory = Path(args.dir) if args.dir else default_dir()
    if not directory.is_dir():
        print(f"no sessions directory at {directory}", file=sys.stderr)
        print("pass --dir, or run the agent once so it writes one.", file=sys.stderr)
        return 1

    if args.list:
        rows = list_sessions(directory)
        if not rows:
            print(f"no session logs in {directory}")
            return 0
        for summary in rows:
            print(f"{summary.id}  {summary.when}  {summary.turns:>3} turns  "
                  f"{summary.render_cost():>12}  {summary.outcome}")
        return 0

    at = None
    if args.session:
        summary = resolve(args.session, directory)
        if summary is None:
            print(f"no session matches {args.session!r} in {directory}",
                  file=sys.stderr)
            return 1
        at = summary.id
    try:
        serve(directory, port=args.port, open_browser=not args.no_open, at=at)
    except PortsBusy as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
