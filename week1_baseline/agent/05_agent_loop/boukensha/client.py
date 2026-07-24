"""Client: posts the built request and returns the provider's parsed reply.

One HTTP POST with retries for the failures providers document as transient.
The transport and the sleep function are injectable, so the retry behavior is
verifiable offline without a network or a clock.
"""

from __future__ import annotations

import http.client
import json
import time
import urllib.error
import urllib.request
from typing import TYPE_CHECKING, Any, Callable, Mapping

from .errors import ApiError

if TYPE_CHECKING:
    from .prompt_builder import PromptBuilder

#: A transport takes (url, headers, body) and returns
#: (status, body_text, response_headers). Raising OSError or
#: http.client.HTTPException signals a transient failure.
Transport = Callable[
    [str, Mapping[str, str], str],
    tuple[int, str, Mapping[str, str]],
]

#: Exceptions from the transport treated as transient. OSError covers
#: connection, timeout, DNS, and SSL errors. http.client.HTTPException covers
#: a connection that closes mid-response (IncompleteRead), and EOFError a
#: connection that ends at a read boundary; neither is an OSError, and both
#: escape urllib unwrapped.
TRANSIENT_ERRORS = (OSError, http.client.HTTPException, EOFError)

DEFAULT_TIMEOUT = 60.0


def default_transport(url: str, headers: Mapping[str, str],
                      body: str) -> tuple[int, str, Mapping[str, str]]:
    """POST with the standard library. An HTTP error status is a response."""
    request = urllib.request.Request(
        url, data=body.encode("utf-8"), headers=dict(headers), method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT) as resp:
            return resp.status, resp.read().decode("utf-8"), dict(resp.headers)
    except urllib.error.HTTPError as err:
        # HTTPError is both an OSError and a response. It carries a real
        # status, so it is returned as a response, never retried blindly.
        return err.code, err.read().decode("utf-8", "replace"), dict(err.headers)


class Client:
    """Sends one PromptBuilder's requests and parses the JSON replies."""

    RETRYABLE_STATUSES = frozenset({408, 409, 429, 500, 502, 503, 504, 529})
    MAX_RETRIES = 3
    BASE_RETRY_DELAY = 0.5
    #: Upper bound on an honored Retry-After. The provider docs set no cap;
    #: this is a defensive limit so a malformed or hostile header cannot stall
    #: the client, set to the request timeout.
    RETRY_AFTER_CAP = 60.0

    def __init__(self, builder: PromptBuilder,
                 transport: Transport | None = None,
                 sleep: Callable[[float], None] | None = None) -> None:
        self.builder = builder
        self._transport = transport or default_transport
        self._sleep = sleep or time.sleep

    def for_builder(self, builder: PromptBuilder) -> Client:
        """A new client bound to a different builder, sharing this one's
        transport and sleep.

        The agent uses this for the tools-disabled wind-down call: it rebinds
        the client to a builder carrying an empty toolset without touching the
        ``call`` signature, and the shared transport keeps the offline stub in
        place.
        """
        return Client(builder, transport=self._transport, sleep=self._sleep)

    def call(self, max_output_tokens: int = 1024,
             thinking: str | None = None) -> dict[str, Any]:
        """POST the built request, retry transient failures, parse the JSON."""
        url = self.builder.url()
        headers = self.builder.headers()
        body = json.dumps(self.builder.build_request(
            max_output_tokens=max_output_tokens, thinking=thinking
        ))

        attempts = 0
        while True:
            attempts += 1
            try:
                status, text, response_headers = self._transport(
                    url, headers, body
                )
            except TRANSIENT_ERRORS as exc:
                if attempts > self.MAX_RETRIES:
                    raise ApiError(
                        f"API request failed after {attempts} attempts: "
                        f"{type(exc).__name__}: {exc}"
                    ) from exc
                self._sleep(self._backoff(attempts))
                continue
            if status in self.RETRYABLE_STATUSES and attempts <= self.MAX_RETRIES:
                self._sleep(self._retry_wait(attempts, response_headers))
                continue
            break

        if not 200 <= status < 300:
            raise ApiError(
                f"API request failed after {attempts} "
                f"attempt{'s' if attempts != 1 else ''} ({status}): {text}"
            )
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            preview = text[:200]
            raise ApiError(
                f"API returned {status} with a non-JSON body: {preview!r}"
            ) from exc

    def _backoff(self, attempt: int) -> float:
        """0.5 s doubling per attempt: 0.5, 1.0, 2.0."""
        return self.BASE_RETRY_DELAY * (2 ** (attempt - 1))

    def _retry_wait(self, attempt: int,
                    response_headers: Mapping[str, str]) -> float:
        """The backoff delay, unless a numeric Retry-After replaces it."""
        for name, value in response_headers.items():
            if name.lower() == "retry-after":
                try:
                    seconds = float(value)
                except (TypeError, ValueError):
                    break
                return min(max(seconds, 0.0), self.RETRY_AFTER_CAP)
        return self._backoff(attempt)

    def __str__(self) -> str:
        return f"<Client builder={self.builder}>"

    __repr__ = __str__
