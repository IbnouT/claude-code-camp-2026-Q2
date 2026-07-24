"""Agent: the turn loop.

One ``run`` drives a turn: call the model, normalize the reply, dispatch every
tool the model asked for back through the registry, feed the results into the
conversation, and repeat until the model ends the turn or the iteration ceiling
is reached. The ceiling is a trigger threshold, not a hard cap: reaching it
makes one tools-disabled wind-down call rather than raising.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .errors import ApiError
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
                 thinking: str | None = None) -> None:
        self._context = context
        self._registry = registry
        self._builder = builder
        self._client = client
        self._max_iterations = self._resolve_max_iterations(
            task, task_settings, max_iterations
        )
        self._max_output_tokens = self._resolve_max_output_tokens(
            task, task_settings, max_output_tokens
        )
        self._thinking = self._resolve_thinking(task, task_settings, thinking)
        self._iteration = 0

    def run(self) -> str:
        """Run the turn and return the final text."""
        while True:
            # Limits are trigger thresholds, not hard caps: on reaching one we
            # stop starting new work iterations and make exactly one terminal
            # wind-down call instead of raising.
            if self._iteration_limit_reached():
                return self._wrap_up("max_iterations")

            self._iteration += 1
            print(f"[iteration {self._iteration}/{self._max_iterations}]")

            response = self._client.call(**self._call_opts())
            parsed = self._builder.parse_response(response)

            if parsed.stop_reason == "tool_use":
                self._handle_tool_calls(parsed.content)
            else:
                return self._extract_text(parsed.content)

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
            response = wrap_client.call(
                max_output_tokens=self.WRAP_UP_OUTPUT_TOKENS
            )
        except ApiError:
            return self._fallback_message(reason)
        text = self._extract_text(wrap_builder.parse_response(response).content)
        return text if text.strip() else self._fallback_message(reason)

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

    def _handle_tool_calls(self, content: tuple[Any, ...]) -> None:
        # The assistant message carrying the tool_use must land before its
        # tool_result, or the next provider request is rejected.
        self._context.add(Message.assistant(content))

        for block in content:
            if isinstance(block, ToolUseBlock):
                print(f"  tool call -> {block.name}({block.input})")
                result = self._registry.dispatch(block.name, block.input)
                print(f"  tool result -> {str(result)[:60]}")
                self._context.add(
                    Message.tool_result(block.id, block.name, str(result))
                )

    def __str__(self) -> str:
        return (
            f"<Agent max_iterations={self._max_iterations} "
            f"iteration={self._iteration}>"
        )

    __repr__ = __str__
