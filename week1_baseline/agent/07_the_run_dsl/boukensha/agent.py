"""Agent: the turn loop.

One ``run`` drives a turn: call the model, normalize the reply, dispatch every
tool the model asked for back through the registry, feed the results into the
conversation, and repeat until the model ends the turn or the iteration ceiling
is reached. The ceiling is a trigger threshold, not a hard cap: reaching it
makes one tools-disabled wind-down call rather than raising.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from .errors import ApiError
from .logger import Logger
from .message import Message, TextBlock, ToolUseBlock
from .prompt_builder import PromptBuilder

if TYPE_CHECKING:
    from .client import Client
    from .context import Context
    from .registry import Registry
    from .tasks.base import Task


class Agent:
    """Runs one turn of the conversation to completion."""

    #: Default iteration ceiling. The enforced value is resolved in the
    #: constructor; 0 or None disables the ceiling.
    MAX_ITERATIONS = 25

    #: The wind-down call is deliberately short and cheap.
    WRAP_UP_OUTPUT_TOKENS = 400
    WRAP_UP_DIRECTIVE = (
        "You have reached your action limit for this turn. Do not call any "
        "more tools.\nBriefly summarize what you accomplished, what is still "
        "unfinished, and the\nsingle next action you would take."
    )

    def __init__(self, context: Context, registry: Registry,
                 builder: PromptBuilder, client: Client, *,
                 task: type[Task] | None = None,
                 task_settings: dict[str, Any] | None = None,
                 max_iterations: int | None = None,
                 max_output_tokens: int | None = None,
                 thinking: str | None = None,
                 logger: Logger | None = None) -> None:
        self._context = context
        self._registry = registry
        self._builder = builder
        self._client = client
        self._task = task
        # Build a default Logger when none is passed, rather than a def-time
        # default, so agents never share one session file and Python's
        # mutable-default pitfall is avoided. A default Logger opens a session
        # file immediately.
        self._logger = logger if logger is not None else Logger()
        self._max_iterations = self._resolve_max_iterations(
            task, task_settings, max_iterations
        )
        self._max_output_tokens = self._resolve_max_output_tokens(
            task, task_settings, max_output_tokens
        )
        self._thinking = self._resolve_thinking(task, task_settings, thinking)
        self._iteration = 0
        # Per-turn totals, reset at the start of each run().
        self._turn_in = 0
        self._turn_out = 0
        self._turn_duration_ms = 0.0
        # Surface transient-failure retries in the session log, without touching
        # the client's construction sites. Keep a caller-provided hook if set.
        self._client.on_retry = self._client.on_retry or self._logger.retry

    def run(self) -> str:
        """Run the turn and return the final text."""
        self._turn_in = 0
        self._turn_out = 0
        self._turn_duration_ms = 0.0
        while True:
            # Limits are trigger thresholds, not hard caps: on reaching one we
            # stop starting new work iterations and make exactly one terminal
            # wind-down call instead of raising.
            if self._iteration_limit_reached():
                self._logger.limit_reached(
                    kind="max_iterations", n=self._iteration,
                    max=self._max_iterations,
                )
                return self._wrap_up("max_iterations")

            self._iteration += 1
            self._logger.iteration(n=self._iteration, max=self._max_iterations)
            self._logger.prompt(
                messages=self._context.messages, tools=self._registry.tools
            )

            response, duration_ms = self._call_model(**self._call_opts())
            self._logger.raw(data=response)
            parsed = self._builder.parse_response(response)

            if parsed.stop_reason == "tool_use":
                self._handle_tool_calls(parsed.content, response, duration_ms)
            else:
                text = self._extract_text(parsed.content)
                self._log_response(text=text, response=response, duration_ms=duration_ms)
                self._logger.turn_end(reason="completed", iterations=self._iteration,
                                      **self._turn_totals())
                return text

    # -- limit resolution --------------------------------------------------

    def _resolve_max_iterations(self, task: type[Task] | None,
                                task_settings: dict[str, Any] | None,
                                explicit: int | None) -> int | None:
        if explicit is not None:
            return int(explicit)
        if task is not None and task_settings is not None:
            return task.max_iterations(task_settings)
        return self.MAX_ITERATIONS

    def _resolve_max_output_tokens(self, task: type[Task] | None,
                                   task_settings: dict[str, Any] | None,
                                   explicit: int | None) -> int | None:
        if explicit is not None:
            return explicit
        if task is not None and task_settings is not None:
            return task.max_output_tokens(task_settings)
        # None means "unset": the client applies its own default per call.
        return None

    def _resolve_thinking(self, task: type[Task] | None,
                          task_settings: dict[str, Any] | None,
                          explicit: str | None) -> str | None:
        if explicit is not None:
            return explicit
        if task is not None and task_settings is not None:
            return task.thinking(task_settings)
        # None means "unset": the backend sends nothing and the model default
        # applies.
        return None

    def _iteration_limit_reached(self) -> bool:
        limit = self._max_iterations
        return limit is not None and limit > 0 and self._iteration >= limit

    def _call_opts(self) -> dict[str, Any]:
        """Per-call options shared by every work-iteration model round trip.

        Carries the resolved output cap and thinking level. The wind-down call
        deliberately does not use these (see ``_wrap_up``).
        """
        opts: dict[str, Any] = {}
        if self._max_output_tokens is not None:
            opts["max_output_tokens"] = self._max_output_tokens
        if self._thinking is not None:
            opts["thinking"] = self._thinking
        return opts

    # -- wind-down ---------------------------------------------------------

    def _wrap_up(self, reason: str) -> str:
        """One final tools-disabled call so the turn ends in character.

        Runs outside the counted loop: it never rechecks the limit and never
        increments the counter, so it cannot re-trigger. Falls back to a
        deterministic message when the reply is empty or the call raises.

        The resolved thinking level is deliberately not carried here. This call
        is a short, cheap summary bounded to ``WRAP_UP_OUTPUT_TOKENS``, and
        spending a thinking budget on it defeats that purpose. The model default
        applies instead. The budget-versus-``max_tokens`` constraint is handled
        in the Anthropic backend, so this omission is a cost choice.
        """
        self._context.add(Message.user(self.WRAP_UP_DIRECTIVE))
        wrap_builder = PromptBuilder(self._context, self._builder.backend, ())
        wrap_client = self._client.for_builder(wrap_builder)
        try:
            start = time.monotonic()
            response = wrap_client.call(
                max_output_tokens=self.WRAP_UP_OUTPUT_TOKENS
            )
            duration_ms = (time.monotonic() - start) * 1000.0
            self._turn_duration_ms += duration_ms
        except ApiError:
            self._logger.turn_end(reason=reason, iterations=self._iteration,
                                  **self._turn_totals())
            return self._fallback_message(reason)
        text = self._extract_text(wrap_builder.parse_response(response).content)
        text = text if text.strip() else self._fallback_message(reason)
        self._log_response(text=text, response=response, duration_ms=duration_ms)
        self._logger.turn_end(reason=reason, iterations=self._iteration,
                              **self._turn_totals())
        return text

    def _fallback_message(self, reason: str) -> str:
        return (
            f"I reached my {self._max_iterations}-action limit for this turn "
            f"before finishing ({reason}). Ask me to continue and I'll pick up "
            f"from here."
        )

    # -- content -----------------------------------------------------------

    @staticmethod
    def _extract_text(content: tuple[Any, ...]) -> str:
        return "".join(b.text for b in content if isinstance(b, TextBlock))

    def _handle_tool_calls(self, content: tuple[Any, ...],
                           response: dict[str, Any],
                           duration_ms: float | None = None) -> None:
        tool_calls = [b for b in content if isinstance(b, ToolUseBlock)]

        # The response event fires on every model round trip, tool-use turns
        # included: it carries the reasoning text, or a synthetic placeholder
        # naming the call count when the reply had no text, plus the execution
        # metadata block.
        reasoning = self._extract_text(content)
        if reasoning.strip():
            text = reasoning
        else:
            plural = "s" if len(tool_calls) != 1 else ""
            text = f"(tool use: {len(tool_calls)} call{plural})"
        self._log_response(text=text, response=response, duration_ms=duration_ms)

        # The assistant message carrying the tool_use must land before its
        # tool_result, or the next provider request is rejected.
        self._context.add(Message.assistant(content))

        for block in tool_calls:
            self._logger.tool_call(name=block.name, args=block.input, id=block.id)
            # A raising tool no longer aborts the turn: the error becomes the
            # tool result string fed back to the model, and the tool_result
            # event is logged ok=False so the failure is visible in the log.
            try:
                result = self._registry.dispatch(block.name, block.input)
                self._logger.tool_result(
                    name=block.name, result=result, ok=True, tool_use_id=block.id
                )
            except Exception as exc:
                result = f"ERROR: {type(exc).__name__}: {exc}"
                self._logger.tool_result(
                    name=block.name, result=result, ok=False, error=str(exc),
                    tool_use_id=block.id,
                )
            self._context.add(
                Message.tool_result(block.id, block.name, str(result))
            )

    # -- logging -----------------------------------------------------------

    def _call_model(self, **opts: Any) -> tuple[dict[str, Any], float]:
        """Call the model, returning the reply and its wall-clock milliseconds.

        The elapsed time is added to the turn total so ``turn_end`` can report
        how long the turn spent in model calls.
        """
        start = time.monotonic()
        response = self._client.call(**opts)
        duration_ms = (time.monotonic() - start) * 1000.0
        self._turn_duration_ms += duration_ms
        return response, duration_ms

    def _turn_totals(self) -> dict[str, Any]:
        """The turn's summed usage and wall-clock, for the ``turn_end`` event.

        Each field is omitted when it could not be computed, so a turn with no
        usage reports none rather than a misleading zero.
        """
        totals: dict[str, Any] = {}
        if self._turn_in or self._turn_out:
            totals["input_tokens"] = self._turn_in
            totals["output_tokens"] = self._turn_out
            backend = self._builder.backend
            if backend is not None:
                cost = backend.estimate_cost(self._turn_in, self._turn_out)
                if cost is not None:
                    totals["cost_usd"] = cost
        if self._turn_duration_ms:
            totals["duration_ms"] = self._turn_duration_ms
        return totals

    def _log_response(self, text: str, response: dict[str, Any],
                      duration_ms: float | None = None) -> None:
        usage = self._normalized_usage(response)
        self._logger.response(
            text=text,
            usage=usage,
            stop_reason=response.get("stop_reason"),
            task=self._task,
            backend=self._builder.backend,
            duration_ms=duration_ms,
        )
        counts = Logger.token_counts(usage)
        if counts["input"] is not None:
            self._turn_in += counts["input"]
        if counts["output"] is not None:
            self._turn_out += counts["output"]

    @staticmethod
    def _normalized_usage(response: dict[str, Any]) -> dict[str, Any] | None:
        """The raw usage object for this response, or None when absent.

        Anthropic and OpenAI Responses carry ``usage``, Gemini carries
        ``usageMetadata``, and Ollama reports two top-level counts. The logger's
        ``usage_tokens`` reads token counts out of whichever shape this returns.
        """
        if response.get("usage"):
            return response["usage"]
        if response.get("usageMetadata"):
            return response["usageMetadata"]
        usage = {
            key: response[key]
            for key in ("prompt_eval_count", "eval_count")
            if key in response
        }
        return usage or None

    def __str__(self) -> str:
        return (
            f"<Agent max_iterations={self._max_iterations} "
            f"iteration={self._iteration}>"
        )

    __repr__ = __str__
