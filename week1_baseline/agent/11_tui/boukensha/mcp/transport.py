"""Transport: move JSON-RPC messages to and from a live MCP server.

The transport owns the connection and the process, and correlates responses to
requests. The :class:`~boukensha.mcp.client.Client` above it owns the protocol
(building ``initialize``/``tools/list``/``tools/call`` envelopes and reading
their results). Splitting the two mirrors the HTTP client's injectable-transport
convention (``boukensha.client``): a test can drive a :class:`Client` over a fake
transport, and a non-stdio transport could slot in later without touching the
client.

:class:`StdioTransport` spawns the server as a subprocess and reads its stdout on
a single background thread, routing each response to the caller waiting on its
request id. That thread is what buys two things a blocking ``readline`` loop
cannot:

- a per-call timeout, so one hung tool call cannot hang the whole agent turn, and
- prompt, exit-code-aware failure when the server crashes or closes the pipe,
  waking every blocked caller at once instead of one dead read at a time.
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import time
from typing import Any, Protocol, runtime_checkable

from ..errors import McpError, McpTimeoutError

#: Default per-call timeout in seconds. Long enough for a real tool to work,
#: short enough that a hung server is a bounded wait a REPL user will sit out.
DEFAULT_TIMEOUT = 30.0

#: Pushed into a waiting call's queue when the connection closes, so a blocked
#: caller wakes immediately with a clear error instead of waiting out its timeout.
_CLOSED = object()


@runtime_checkable
class Transport(Protocol):
    """A live channel to one MCP server: request/response, notify, close."""

    def request(self, message: dict[str, Any], request_id: int,
                timeout: float) -> dict[str, Any]:
        """Send a request and block for its correlated response, up to ``timeout``."""
        ...

    def notify(self, message: dict[str, Any]) -> None:
        """Send a fire-and-forget notification (no response expected)."""
        ...

    def close(self, timeout: float = 5.0) -> None:
        """Shut the connection down. Idempotent."""
        ...

    @property
    def closed(self) -> bool:
        ...

    @property
    def exit_code(self) -> int | None:
        ...


class StdioTransport:
    """An MCP transport over a spawned subprocess's stdin/stdout.

    One reader thread drains stdout and routes responses by id into per-call
    queues. ``env`` is merged over the inherited environment (never replacing it,
    so the server still finds ``PATH``) with values stringified for the OS
    environment. A nonexistent command raises ``FileNotFoundError`` here, at
    construction, the same spawn-time signal as before.
    """

    def __init__(self, command: str, args: tuple[str, ...] | list[str] = (),
                 env: dict[str, str] | None = None) -> None:
        cmd = [str(command), *[str(a) for a in args]]
        child_env = dict(os.environ)
        for key, value in (env or {}).items():
            child_env[str(key)] = str(value)

        self._proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            # stderr inherited (flows to the host's stderr), never an undrained
            # pipe that would backpressure-deadlock a chatty server.
            stderr=None,
            env=child_env,
            text=True,
            bufsize=1,  # line-buffered
        )
        self._lock = threading.Lock()
        self._pending: dict[int, queue.Queue] = {}
        self._closed = False
        self._exit_code: int | None = None
        self._reader = threading.Thread(
            target=self._read_loop, name="mcp-stdio-reader", daemon=True)
        self._reader.start()

    # -- Transport ---------------------------------------------------------

    def request(self, message: dict[str, Any], request_id: int,
                timeout: float) -> dict[str, Any]:
        response_q: queue.Queue = queue.Queue(maxsize=1)
        # Register the waiter before writing, so a response that arrives before
        # this call blocks on the queue is still delivered, not dropped.
        with self._lock:
            if self._closed:
                raise McpError(self._closed_reason())
            self._pending[request_id] = response_q
        try:
            self._write(message)
            try:
                item = response_q.get(timeout=timeout)
            except queue.Empty:
                raise McpTimeoutError(
                    f"MCP request '{message.get('method')}' timed out "
                    f"after {timeout:g}s"
                ) from None
        finally:
            with self._lock:
                self._pending.pop(request_id, None)
        if item is _CLOSED:
            raise McpError(self._closed_reason())
        return item

    def notify(self, message: dict[str, Any]) -> None:
        with self._lock:
            if self._closed:
                raise McpError(self._closed_reason())
        self._write(message)

    def close(self, timeout: float = 5.0) -> None:
        with self._lock:
            first = not self._closed
            self._closed = True
        proc = self._proc
        if first:
            try:
                if proc.stdin is not None:
                    proc.stdin.close()
            except OSError:
                pass
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            self._exit_code = proc.poll()
            # Wake anything still blocked, then let the reader thread finish on EOF.
            self._drain_pending()
            self._reader.join(timeout=timeout)
        # Always close the pipe handles, even when the reader thread already
        # marked the transport closed on a crash (EOF) without closing them, so
        # a crashed or respawned server never leaks its stdin/stdout files.
        for pipe in (proc.stdin, proc.stdout):
            try:
                if pipe is not None:
                    pipe.close()
            except OSError:
                pass

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def exit_code(self) -> int | None:
        return self._exit_code

    # -- internals ---------------------------------------------------------

    def _write(self, message: dict[str, Any]) -> None:
        stdin = self._proc.stdin
        if stdin is None:
            raise McpError("MCP server stdin is not available")
        try:
            stdin.write(json.dumps(message) + "\n")
            stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise McpError(f"failed to send to MCP server: {exc}") from exc

    def _read_loop(self) -> None:
        stdout = self._proc.stdout
        if stdout is None:
            return
        while True:
            line = stdout.readline()
            if line == "":  # EOF: the server closed its stdout / exited.
                self._exit_code = self._await_exit()
                with self._lock:
                    self._closed = True
                self._drain_pending()
                return
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue  # a non-JSON stray line is not our concern; keep reading.
            message_id = message.get("id")
            if message_id is None:
                continue  # a server-initiated notification: no waiter, drop it.
            with self._lock:
                waiter = self._pending.get(message_id)
            if waiter is not None:
                waiter.put(message)
            # else: a late response to an abandoned (timed-out) call, or an
            # unknown id. No one is waiting, so drop it.

    def _await_exit(self) -> int | None:
        """The child's exit code, waiting briefly for it to be reaped.

        At EOF the child has closed stdout but may not be fully exited yet, so a
        bare ``poll()`` can return ``None``. Poll for a short bounded window so a
        crash reports its real exit code rather than the vaguer
        "connection closed", without blocking shutdown if the child lingers.
        """
        code = self._proc.poll()
        waited = 0.0
        while code is None and waited < 0.5:
            time.sleep(0.01)
            waited += 0.01
            code = self._proc.poll()
        return code

    def _drain_pending(self) -> None:
        """Hand every blocked caller the closed sentinel, once."""
        with self._lock:
            waiters = list(self._pending.values())
            self._pending.clear()
        for waiter in waiters:
            try:
                waiter.put_nowait(_CLOSED)
            except queue.Full:
                pass

    def _closed_reason(self) -> str:
        code = self._exit_code
        if code is None:
            return "MCP server connection closed"
        if code == 0:
            return "MCP server exited"
        return f"MCP server crashed (exit code {code})"

    def __str__(self) -> str:
        pid = getattr(self._proc, "pid", "?")
        return f"<StdioTransport pid={pid} closed={self._closed} exit_code={self._exit_code}>"

    __repr__ = __str__
