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

from .compaction import prefix_tokens
from .errors import ApiError, TurnCancelled
from .operator_control import OperatorMailbox, OperatorStopped
from .logger import Logger
from .message import Message, ReasoningBlock, TextBlock, ToolUseBlock
from .prompt_builder import PromptBuilder
from .usage import normalize

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

    #: Per-turn spend-breaker default (input+output tokens); 0 disables it.
    MAX_TURN_TOKENS = 60_000

    #: Per-turn money ceiling in USD; 0 disables it, which is the default.
    MAX_TURN_COST = 0.0

    def __init__(self, context: Context, registry: Registry,
                 builder: PromptBuilder, client: Client, *,
                 task: type[Task] | None = None,
                 task_settings: dict[str, Any] | None = None,
                 max_iterations: int | None = None,
                 max_turn_tokens: int | None = None,
                 max_turn_cost: float | None = None,
                 max_output_tokens: int | None = None,
                 thinking: str | None = None,
                 cancel_event: Any = None,
                 operator: OperatorMailbox | None = None,
                 logger: Logger | None = None) -> None:
        self._context = context
        self._registry = registry
        self._builder = builder
        self._client = client
        self._task = task
        #: A ``threading.Event`` (or None). Checked at the top of every loop
        #: iteration: once set, the turn raises TurnCancelled before the next
        #: model call, so Esc in the TUI ends a turn promptly and cheaply.
        self._cancel_event = cancel_event
        self._operator = operator
        # Build a default Logger when none is passed, rather than a def-time
        # default, so agents never share one session file and Python's
        # mutable-default pitfall is avoided. A default Logger opens a session
        # file immediately.
        self._logger = logger if logger is not None else Logger()
        self._max_iterations = self._resolve_max_iterations(
            task, task_settings, max_iterations
        )
        self._max_turn_tokens = self._resolve_max_turn_tokens(
            task, task_settings, max_turn_tokens
        )
        self._max_turn_cost = self._resolve_max_turn_cost(
            task, task_settings, max_turn_cost
        )
        self._max_output_tokens = self._resolve_max_output_tokens(
            task, task_settings, max_output_tokens
        )
        self._thinking = self._resolve_thinking(task, task_settings, thinking)
        self._iteration = 0
        #: Wall-clock milliseconds spent in model calls this turn, so
        #: turn_end can report where the time went. Time is a different
        #: question from tokens: a turn can be cheap and slow.
        self._turn_duration_ms = 0.0
        # Surface transient-failure retries in the session log. The per-turn
        # duration and token-total reporting the earlier steps add to turn_end
        # merges with this step's own context token accounting when step 12 is
        # opened; the retry hook is safe and useful now.
        self._client.on_retry = self._client.on_retry or self._logger.retry
        self._client.on_request = (
            self._client.on_request
            or (
                lambda *, request: self._logger.model_request(
                    request=request,
                    provider=self._builder.backend.provider_name,
                    model=self._builder.backend.model,
                )
            )
        )

    def run(self) -> str:
        """Run the turn and return the final text."""
        # Reset the per-turn spend counter and compact before the first call, so
        # a turn opening near the window limit frees space before it requests.
        self._context.reset_turn_tokens()
        self._turn_duration_ms = 0.0
        self._compact_if_needed()

        while True:
            if self._operator is not None:
                try:
                    self._operator.checkpoint(
                        self._context,
                        self._logger,
                        iteration=self._iteration,
                    )
                except OperatorStopped as error:
                    self._logger.turn_end(
                        reason="operator_stop",
                        iterations=self._iteration,
                        **self._turn_totals(),
                    )
                    raise error
            # Esc in the TUI sets the cancel event; end the turn promptly at the
            # iteration boundary rather than starting another model call.
            if self._cancel_event is not None and self._cancel_event.is_set():
                raise TurnCancelled("turn cancelled by the user")

            # Three independent ceilings, each measuring a different quantity:
            # iterations cap steps, volume caps work and holds even on an unpriced
            # model, cost caps money and is stable across models. Stop at
            # whichever trips first. Limits are
            # trigger thresholds, not hard caps: on reaching one we stop starting
            # new work iterations and make exactly one terminal wind-down call
            # instead of raising.
            if self._iteration_limit_reached():
                self._logger.limit_reached(
                    kind="max_iterations", n=self._iteration,
                    max=self._max_iterations,
                )
                return self._wrap_up("max_iterations")

            if self._token_limit_reached():
                self._logger.limit_reached(
                    kind="max_tokens", n=self._context.turn_tokens,
                    max=self._max_turn_tokens,
                )
                return self._wrap_up("max_tokens")

            if self._cost_limit_reached():
                self._logger.limit_reached(
                    kind="max_cost", n=round(self._context.turn_cost, 6),
                    max=self._max_turn_cost,
                )
                return self._wrap_up("max_cost")

            self._iteration += 1
            self._logger.iteration(n=self._iteration, max=self._max_iterations)
            self._logger.prompt(
                messages=self._context.messages, tools=self._registry.tools,
                context_window=self._context.context_window,
            )

            response, duration_ms = self._call_model(**self._call_opts())
            self._log_provider_response(response)
            self._logger.raw(data=response)
            parsed = self._builder.parse_response(response)
            self._record_usage(response)
            self._log_reasoning(parsed.content)

            if parsed.stop_reason == "tool_use":
                self._handle_tool_calls(parsed.content, response,
                                        duration_ms=duration_ms)
            else:
                text = self._extract_text(parsed.content)
                self._log_response(text=text, response=response,
                                   content=parsed.content,
                                   stop_reason=parsed.stop_reason,
                                   duration_ms=duration_ms)
                self._logger.turn_end(
                    reason="completed", iterations=self._iteration,
                    **self._turn_totals(),
                )
                # Persist the final reply so the next REPL turn sees it. Correct
                # for one-shot run too: the message is added just before the
                # return, then the process ends, so history is uniform across
                # both entry points and providers that require the assistant
                # turn to be present accept the follow-up request.
                self._context.add(Message.assistant(text))
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

    def _resolve_max_turn_tokens(self, task: type[Task] | None,
                                 task_settings: dict[str, Any] | None,
                                 explicit: int | None) -> int:
        if explicit is not None:
            return int(explicit)
        if task is not None and task_settings is not None:
            return task.max_turn_tokens(task_settings)
        return self.MAX_TURN_TOKENS

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

    def _resolve_max_turn_cost(self, task: type[Task] | None,
                               task_settings: dict[str, Any] | None,
                               explicit: float | None) -> float:
        if explicit is not None:
            return float(explicit)
        if task is not None and task_settings is not None:
            return task.max_turn_cost(task_settings)
        return self.MAX_TURN_COST

    def _cost_limit_reached(self) -> bool:
        """Whether the turn has spent its money ceiling.

        Only binds when the model is priced. An unpriced model spends an unknown
        amount, so this cannot judge it and the volume and iteration ceilings are
        what stop a runaway turn there. No boot failure is needed, because a
        guard remains either way.
        """
        limit = self._max_turn_cost
        return bool(limit and limit > 0 and self._context.turn_cost >= limit)

    def _token_limit_reached(self) -> bool:
        limit = self._max_turn_tokens
        return limit > 0 and self._context.turn_tokens >= limit

    def _compact_if_needed(self) -> None:
        """Compact before the first call when window pressure is over threshold,
        logging one ``compaction`` event with the pre-compaction pressure."""
        if not self._context.needs_compaction():
            return
        before = self._context.current_tokens
        # The un-shrinkable part of every prompt, measured from the objects that
        # own it rather than inferred from a past call's reported size.
        overhead = prefix_tokens(self._context.system, self._registry.tools)
        dropped = self._context.compact_messages(overhead=overhead)
        result = self._context.last_compaction
        self._logger.compaction(
            before=before, dropped=dropped,
            compressed=result.compressed if result else 0,
            over_budget=result.over_budget if result else False,
            summarized=result.summarized if result else False,
            context_window=self._context.context_window,
        )

    def _record_usage(self, response: dict[str, Any],
                      window_pressure: bool = True) -> None:
        """Record one call in every quantity that means something different.

        Four token classes are normalized once (see :mod:`boukensha.usage`) and
        each metric is derived from the classes, never from another metric:

        - window pressure is the WHOLE prompt, fresh plus cache read plus cache
          write. Cached tokens still occupy the window. Reading occupancy from
          fresh input alone makes a cached session look nearly empty, so
          compaction stops firing and history grows until the provider rejects
          it. This is why caching and this line ship together.
        - turn volume is every input class plus output, so enabling caching does
          not move it and a ceiling measured in volume keeps its meaning.
        - turn cost is each class at its own rate, priced by the backend.

        ``window_pressure`` is false for the wind-down call. That call is sent
        with tools disabled, so its input is far smaller than a normal call's and
        is not what the next turn will send. Letting it set the pressure masks
        the real occupancy and the next turn skips a compaction it needed. Its
        tokens still count toward the turn's spend.
        """
        usage = normalize(response)
        self._context.count_prefix_once(
            prefix_tokens(self._context.system, self._registry.tools))
        self._context.add_turn_usage(usage)
        cost = self._builder.backend.cost_of(usage)
        if cost.total is not None:
            self._context.add_turn_cost(cost.total)
        if window_pressure:
            self._context.update_tokens(usage.prompt_tokens)

    def _turn_totals(self) -> dict[str, Any]:
        """The turn's totals for ``turn_end``, so a reader never re-sums a log.

        Steps 10 and 11 logged the input/output split and the turn's cost here,
        and the step-12 rewrite replaced all three with a single summed
        ``tokens``. A sum cannot be taken apart again, so both are reported now:
        ``tokens`` for the ceiling that measures it, the four classes beside it,
        and the exact cost the pricing table produced rather than an estimate.

        Amplification is included because it CANNOT be derived from the log. Its
        denominator is the count of distinct things sent, which this agent tracks
        and the message stream does not record. Leaving it out would leave the
        viewer either silent about repetition or inventing a figure.

        Each field is omitted when it could not be computed, so an unpriced model
        reports no cost rather than a zero that reads as free.
        """
        ctx = self._context
        usage = ctx.turn_usage
        totals: dict[str, Any] = {"tokens": ctx.turn_tokens}
        if usage.volume:
            totals["input_tokens"] = usage.prompt_tokens
            totals["output_tokens"] = usage.output
            totals["usage"] = {
                "fresh_input": usage.fresh_input,
                "cache_read": usage.cache_read,
                "cache_write": usage.cache_write,
                "output": usage.output,
            }
        if ctx.turn_cost:
            totals["cost_usd"] = round(ctx.turn_cost, 8)
        if ctx.unique_tokens:
            totals["unique_tokens"] = ctx.unique_tokens
            ratio = ctx.amplification()
            if ratio is not None:
                totals["amplification"] = ratio
        if self._turn_duration_ms:
            totals["duration_ms"] = self._turn_duration_ms
        return totals

    def _call_model(self, client: Any = None,
                    **opts: Any) -> tuple[dict[str, Any], float]:
        """Call the model, returning the reply and its wall-clock milliseconds.

        EVERY model call in a turn goes through here, including the wind-down,
        which passes its own tools-disabled client. A second call path that did
        its own timing is precisely how the wind-down came to be the one
        untimed call in a turn, so there is now only one path.

        Measured here rather than inside the client because the client is shared
        and knows nothing of turns. The elapsed time accumulates in a ``finally``
        so a call that raises still reports the time the turn spent waiting on
        it, which on a timeout is the largest number in the turn.
        """
        start = time.monotonic()
        try:
            response = (client or self._client).call(**opts)
        finally:
            duration_ms = (time.monotonic() - start) * 1000.0
            self._turn_duration_ms += duration_ms
        return response, duration_ms

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
            response, duration_ms = self._call_model(
                client=wrap_client,
                max_output_tokens=self.WRAP_UP_OUTPUT_TOKENS,
            )
        except ApiError:
            self._logger.turn_end(
                reason=reason, iterations=self._iteration,
                **self._turn_totals(),
            )
            message = self._fallback_message(reason)
            self._context.add(Message.assistant(message))
            return message
        # The breaker was evaluated on pre-wind-down spend. The wind-down call's
        # tokens still count toward the turn total reported to turn_end, but it
        # is sent with tools disabled, so it must not set window pressure.
        self._record_usage(response, window_pressure=False)
        self._log_provider_response(response)
        wrap_parsed = wrap_builder.parse_response(response)
        text = self._extract_text(wrap_parsed.content)
        text = text if text.strip() else self._fallback_message(reason)
        self._log_response(text=text, response=response,
                           content=wrap_parsed.content,
                           stop_reason=wrap_parsed.stop_reason,
                           duration_ms=duration_ms)
        self._logger.turn_end(
            reason=reason, iterations=self._iteration,
            **self._turn_totals(),
        )
        self._context.add(Message.assistant(text))
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
        # Newline, not empty string: a provider may split one reply across
        # several text blocks (Gemini emits a part per paragraph), and joining
        # those with nothing glues the last word of one to the first of the next.
        return "\n".join(b.text for b in content if isinstance(b, TextBlock))

    def _handle_tool_calls(self, content: tuple[Any, ...],
                           response: dict[str, Any],
                           duration_ms: float | None = None) -> None:
        tool_calls = [b for b in content if isinstance(b, ToolUseBlock)]

        # Any text preamble accompanying the tool calls is its own plan event,
        # so a viewer shows the model's stated intent as a first-class step.
        # The response event then always carries the placeholder naming the
        # call count, and it owns the turn's usage.
        preamble = self._extract_text(content)
        if preamble.strip():
            self._logger.plan(text=preamble)
        plural = "s" if len(tool_calls) != 1 else ""
        # Reached only from the tool_use branch of the loop, so the normalized
        # stop reason for this call is known without re-deriving it.
        self._log_response(
            text=f"(tool use: {len(tool_calls)} call{plural})", response=response,
            content=content, stop_reason="tool_use", duration_ms=duration_ms,
        )

        # The assistant message carrying the tool_use must land before its
        # tool_result, or the next provider request is rejected.
        self._context.add(Message.assistant(content))

        for block in tool_calls:
            self._logger.tool_call(name=block.name, args=block.input, id=block.id)
            self._context.feed_tool_call(block.name, block.input, block.id)
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
            self._context.feed_tool_result(block.name, result, block.id)
            self._context.add(
                Message.tool_result(block.id, block.name, str(result))
            )

    # -- logging -----------------------------------------------------------

    def _log_reasoning(self, content: tuple[Any, ...]) -> None:
        """One reasoning event per thinking block in the reply.

        An empty, non-redacted block is skipped as noise. A redacted block
        still logs: it tells the viewer the model thought here.
        """
        for block in content:
            if not isinstance(block, ReasoningBlock):
                continue
            if not block.text.strip() and not block.redacted:
                continue
            self._logger.reasoning(text=block.text, redacted=block.redacted)

    def _log_response(self, text: str, response: dict[str, Any],
                      content: tuple[Any, ...] = (),
                      stop_reason: str | None = None,
                      duration_ms: float | None = None) -> None:
        # The normalized stop reason is passed in, never re-read from the raw
        # body: only Anthropic and OpenAI chat completions carry a literal
        # "stop_reason" key, so reading the body logs null on Gemini, Ollama,
        # and the OpenAI Responses API.
        self._logger.response(
            text=text,
            usage=self._normalized_usage(response),
            stop_reason=stop_reason,
            duration_ms=duration_ms,
            task=self._task,
            backend=self._builder.backend,
            content=content,
        )

    def _log_provider_response(self, response: dict[str, Any]) -> None:
        self._logger.provider_response(
            response=response,
            provider=self._builder.backend.provider_name,
            model=self._builder.backend.model,
        )

    #: Provider key families for input and output token counts, first-present
    #: wins per family (Anthropic/OpenAI, OpenAI legacy, Gemini, Ollama).
    _INPUT_KEYS = ("input_tokens", "prompt_tokens",
                   "promptTokenCount", "prompt_eval_count")
    _OUTPUT_KEYS = ("output_tokens", "completion_tokens",
                    "candidatesTokenCount", "eval_count")

    @classmethod
    def _usage_in_out(cls, response: dict[str, Any]) -> tuple[int, int]:
        """Normalized ``(input, output)`` token counts for this response.

        Reads the raw usage sub-object for the provider, then the first present
        key in each family, mirroring the logger's normalization so the two
        never disagree. Missing counts read as 0.
        """
        usage = cls._normalized_usage(response) or {}
        return (
            cls._first_integer(usage, cls._INPUT_KEYS),
            cls._first_integer(usage, cls._OUTPUT_KEYS),
        )

    @staticmethod
    def _first_integer(usage: dict[str, Any], keys: tuple[str, ...]) -> int:
        for key in keys:
            value = usage.get(key)
            if value is not None:
                try:
                    return int(value)
                except (TypeError, ValueError):
                    return 0
        return 0

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
