"""Structure-aware compaction: keep, compress, or drop history by meaning.

Freeing the window by dropping the oldest messages blind makes the agent forget
whatever scrolled off. This runs a pipeline over the message list and the session's
parsed :class:`~boukensha.journey.JourneyState`, least-lossy stage first, so the
window is freed with the least information loss:

1. COMPRESS  old tool-result bodies become a one-line stub, keeping the turn and
   the tool_use/tool_result pairing intact (wire-safe, the big token reclaim).
2. DROP      if still over the token target, drop the oldest WHOLE turns, so a
   tool_result is never orphaned from its tool_use and the survivor prefix
   always starts on a user turn.
3. SUMMARISE whatever was shed is distilled into one deterministic memory note
   from JourneyState, merged into the first surviving user turn, so continuity
   survives at zero extra model call.

Token sizes are estimated locally (about four characters per token) so the
pipeline can budget against a target fraction of the window rather than a blind
message count. Framework-free and unit-tested with plain messages.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass

from .message import Message, ReasoningBlock, Role, TextBlock, ToolResultBlock, ToolUseBlock

#: Characters kept from an old tool-result body when it is stubbed.
STUB_CHARS = 72
#: Rough chars-per-token estimate, enough to budget compaction locally.
CHARS_PER_TOKEN = 4
#: Default post-compaction target as a fraction of the window.
TARGET_FRACTION = 0.60


@dataclass
class CompactionResult:
    """What one compaction did: the new history and how it got there.

    ``over_budget`` distinguishes "freed enough" from "did everything allowed and
    the prompt is still too big". The second happens when the un-shrinkable part
    of the prompt is itself larger than the budget, or when ``keep_recent`` stops
    the loop, and a caller measuring compaction has to be able to tell them apart.
    """

    messages: list[Message]
    dropped: int
    compressed: int
    summarized: bool
    over_budget: bool = False

    def __str__(self) -> str:
        return (f"<CompactionResult dropped={self.dropped} "
                f"compressed={self.compressed} summarized={self.summarized} "
                f"over_budget={self.over_budget}>")

    __repr__ = __str__


def _block_text(block) -> str:
    if isinstance(block, (TextBlock, ReasoningBlock)):
        return block.text or ""
    if isinstance(block, ToolResultBlock):
        return block.content or ""
    if isinstance(block, ToolUseBlock):
        return f"{block.name} {block.input}"
    return ""


def _est_tokens(message: Message) -> int:
    chars = sum(len(_block_text(b)) for b in message.content)
    return math.ceil(chars / CHARS_PER_TOKEN)


def prefix_tokens(system: str | None, tools=None) -> int:
    """Estimated tokens of the part of every prompt that is NOT history.

    The system prompt and the tool schemas ride on every call and compaction
    cannot shrink either, so a token budget has to subtract them before deciding
    how much history to shed. Both are knowable from the objects that own them,
    which is why this is measured directly rather than inferred by subtracting a
    history estimate from a past call's reported size: those two are different
    prompts (the caller has already appended the new user turn by then), and the
    inference silently absorbs the estimator's own error as well.

    Tools are measured as the JSON a provider is actually sent, name plus
    description plus a JSON Schema object, because that wrapping is most of a
    schema's size. Measuring the raw parameter mapping instead understates a real
    tool surface several times over. Providers differ in their outer key names,
    so this is a close estimate of the wire prefix rather than one provider's
    exact bytes.
    """
    chars = len(system or "")
    values = tools.values() if hasattr(tools, "values") else (tools or ())
    for tool in values:
        params = getattr(tool, "parameters", None) or {}
        required = getattr(tool, "required_parameters", None)
        wire = {
            "name": getattr(tool, "name", ""),
            "description": getattr(tool, "description", ""),
            "input_schema": {
                "type": "object",
                "properties": dict(params),
                "required": list(required) if required else [],
            },
        }
        try:
            chars += len(json.dumps(wire))
        except (TypeError, ValueError):
            # A schema that will not serialize still occupies space; fall back
            # to its repr rather than counting it as zero.
            chars += len(repr(wire))
    return math.ceil(chars / CHARS_PER_TOKEN)


def _stub(block: ToolResultBlock) -> ToolResultBlock:
    """A verbose tool result collapsed to one line, pairing preserved."""
    first = next((ln.strip() for ln in block.content.splitlines() if ln.strip()), "")
    stub = first[:STUB_CHARS]
    if len(block.content) > len(stub):
        stub = (stub + " …[compacted]").strip()
    return ToolResultBlock(block.tool_use_id, block.tool_name,
                           stub or "[compacted]")


def summarize(state) -> str:
    """A deterministic memory note from the parsed journey state.

    No model call: everything here is already parsed for the observatory, so a
    compaction can shed raw history and still leave the agent knowing where it
    has been, how it is doing, and what it was told to do.
    """
    if state is None:
        return ""
    parts: list[str] = []
    titles: list[str] = []
    for room in state.rooms.values():
        if room["title"] not in titles:
            titles.append(room["title"])
    if titles:
        shown = ", ".join(titles[:12])
        more = f" (+{len(titles) - 12} more)" if len(titles) > 12 else ""
        parts.append(f"explored {shown}{more}")
    pos = getattr(state, "position", None)
    if pos and pos in state.rooms:
        parts.append(f"now at {state.rooms[pos]['title']}")
    vit = state.vitals
    if vit.get("hp") is not None:
        hp = f"{vit['hp']}/{vit['max_hp']}" if vit.get("max_hp") else str(vit["hp"])
        parts.append(f"HP {hp}")
    char = state.char
    if char.get("level") is not None:
        gold = char.get("gold")
        parts.append(f"level {char['level']}"
                     + (f", {gold} gold" if gold is not None else ""))
    if getattr(state, "deaths", 0):
        parts.append(f"{state.deaths} death(s)")
    events = [text for _turn, text in getattr(state, "events", [])
              if "kill" in text.lower() or "level" in text.lower()]
    if events:
        parts.append("recent: " + ", ".join(events[-4:]))
    if not parts:
        return ""
    return "Memory of earlier play (older turns were compacted): " + "; ".join(parts) + "."


def _advance_to_user(messages: list[Message], drop: int) -> int:
    """Round a proposed front-cut forward to the next user turn, so the prefix
    that survives never starts on an assistant or an orphaned tool_result."""
    drop = max(0, min(drop, len(messages)))
    while drop < len(messages) and messages[drop].role is not Role.USER:
        drop += 1
    return drop


def _inject_summary(messages: list[Message], summary: str) -> list[Message]:
    note = summary
    if not messages:
        return [Message(Role.USER, (TextBlock(note),))]
    first = messages[0]
    if first.role is Role.USER:
        blocks = list(first.content)
        for i, block in enumerate(blocks):
            if isinstance(block, TextBlock):
                blocks[i] = TextBlock(note + "\n\n" + block.text)
                break
        else:
            blocks.insert(0, TextBlock(note))
        return [Message(Role.USER, tuple(blocks))] + messages[1:]
    return [Message(Role.USER, (TextBlock(note),))] + messages


def compact(messages, journey_state=None, *, window: int = 0,
            overhead: int = 0, keep_recent: int = 2,
            target_fraction: float = TARGET_FRACTION) -> CompactionResult:
    """Run the compaction pipeline and return the new history.

    ``window`` sizes the token target (``target_fraction`` of it). With no
    window (``0``), fall back to a wire-safe count-based drop of the oldest 40
    percent, so the function is always safe to call.

    ``overhead`` is the size of the part of the prompt that is not history: the
    system prompt plus the tool schemas, which ride on every call and which
    compaction cannot shrink. Use :func:`prefix_tokens` to measure it from the
    objects that own it. Without it the pipeline sees only the message list,
    concludes almost nothing needs freeing, and stops early while the window
    keeps filling.
    """
    msgs = list(messages)
    n = len(msgs)
    old_end = max(n - keep_recent, 0)
    overhead = max(0, int(overhead))

    # STAGE 1: compress old tool-result bodies to stubs.
    compressed = 0
    for i in range(old_end):
        m = msgs[i]
        if m.role is Role.TOOL_RESULT:
            new_blocks = tuple(
                _stub(b) if isinstance(b, ToolResultBlock) else b
                for b in m.content)
            if new_blocks != m.content:
                msgs[i] = Message(m.role, new_blocks)
                compressed += 1

    # STAGE 2: drop oldest whole turns until under the token target. The budget is
    # what the window allows MINUS the fixed overhead, since the message list is
    # only the part of the prompt compaction can shrink. A budget at or below zero
    # means the overhead alone fills the window (a large tool surface against a
    # small window): the list is trimmed as far as keep_recent allows and
    # ``over_budget`` on the result says it was not enough.
    target = None
    if window and window > 0:
        target = max(0, int(target_fraction * window) - overhead)
    dropped = 0
    if target is None:
        cut = _advance_to_user(msgs, min(math.ceil(n * 0.40),
                                         max(n - keep_recent, 0)))
        dropped, msgs = cut, msgs[cut:]
    else:
        while (sum(_est_tokens(m) for m in msgs) > target
               and len(msgs) > keep_recent):
            cut = _advance_to_user(msgs, 1)
            if cut == 0 or cut >= len(msgs):
                break
            dropped += cut
            msgs = msgs[cut:]

    # STAGE 3: distil what was shed into one memory note.
    summarized = False
    if (dropped or compressed):
        summary = summarize(journey_state)
        if summary:
            msgs = _inject_summary(msgs, summary)
            summarized = True

    # STAGE 4: the survivor prefix must start on a user turn. Anything skipped
    # here is dropped like any other message and is counted as such, so the log
    # and the UI report the true total.
    start = 0
    while start < len(msgs) and msgs[start].role is not Role.USER:
        start += 1
    msgs = msgs[start:]
    dropped += start

    # Did it work? The remaining history plus the un-shrinkable overhead against
    # the budget, so a caller can tell "freed enough" from "did all I could".
    over_budget = bool(
        target is not None
        and sum(_est_tokens(m) for m in msgs) + overhead > int(target_fraction * window))
    return CompactionResult(msgs, dropped, compressed, summarized, over_budget)
