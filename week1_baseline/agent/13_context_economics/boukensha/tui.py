"""Tui: a readable, live journey view in front of a :class:`Repl`.

boukensha is a Player Journey Agent, so the TUI shows the journey a human wants
to watch, not a debug log. The full end-to-end technical trace (tool plumbing,
tokens, iterations, prompt sizes) lives in the JSONL log and the log viewer,
which own "where did my message go" debugging. This front-end never
shows it.

Two tabs, with the vitals strip pinned in the header so both tabs carry it:

    +-- mud(26) ok · HP 24/24 · Mana 100 · Moves 63 · ctx 3% · $0.20 --+
    +--[ Dashboard ]--[ Feed ]----------------------------------------+
    | Dashboard (default):                                            |
    |   MUD (largest): the current room, its exits and description,   |
    |     plus the latest one-off MUD message. Persists until new     |
    |     MUD text replaces it.                                       |
    |   RECENT (compact, side): the last three humanized actions and  |
    |     the current thinking / objective. Never a self-erasing line.|
    | Feed:                                                           |
    |   the whole journey as formatted cards (room / action /         |
    |   thinking) in order, with in-tab search.                       |
    +-----------------------------------------------------------------+
    | ⠹ playing: move west · 4s          (liveness, not a trace)      |
    | boukensha> input                                                |
    +-----------------------------------------------------------------+

Data flow: logger events arrive thread-safely via ``post_message``; on the app
thread the :class:`JourneyParser` updates vitals and the :class:`Presenter`
turns events into readable cards (and drops all plumbing events, so the noise
can never reach a widget). Esc sets the REPL's cancel event (real
cancellation). Durable numbers (turn, tokens, cost) are read from the Repl.
"""

from __future__ import annotations

import asyncio
import time
from functools import partial
from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.command import Hit, Hits, Provider
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.message import Message
from rich.markdown import Markdown
from rich.text import Text
from textual.screen import ModalScreen
from textual.widgets import Button, Input, RichLog, Static, TabbedContent, TabPane

from .journey import DIRECTIONS, Card, JourneyParser, Presenter
from .repl import Repl

SPARK_GLYPHS = "▁▂▃▄▅▆▇█"


def fmt_tokens(n: int) -> str:
    """Compact token count: ``< 1000`` as the integer, ``>= 1000`` as ``x.xk``."""
    n = int(n)
    if n >= 1000:
        return f"{round(n / 1000, 1)}k"
    return str(n)


def sparkline(samples: list[int], width: int = 8) -> str:
    """A unicode sparkline of the last ``width`` samples."""
    tail = samples[-width:]
    if not tail:
        return ""
    lo, hi = min(tail), max(tail)
    span = (hi - lo) or 1
    return "".join(
        SPARK_GLYPHS[round((v - lo) / span * (len(SPARK_GLYPHS) - 1))]
        for v in tail)


def spell_exits(exits: list[str]) -> str:
    """``["n", "e"]`` -> ``"north, east"``, readable rather than terse."""
    return ", ".join(DIRECTIONS.get(str(e).lower(), str(e)) for e in exits)


def render_card(card: Card):
    """One Feed card as a rich renderable.

    A thinking beat is the agent's own prose, which is markdown (tables, lists,
    bold), so it is rendered as Markdown and a menu table becomes a real table.
    Every other kind is styled Text, never parsed markup, so bracket-laden MUD
    prose is always safe.
    """
    if card.kind == "thinking":
        return Markdown(card.body or "")
    text = Text()
    if card.kind == "room":
        text.append(card.title + "\n", style="bold #d7af5f")
        if card.exits:
            text.append(f"exits: {spell_exits(card.exits)}\n", style="cyan")
        if card.body:
            text.append(card.body + "\n", style="#9e9e9e")
    elif card.kind == "action":
        text.append(card.body + "\n", style="bold #5fd7af")
    elif card.kind == "combat":
        text.append("⚔ " + card.title + "\n", style="bold red")
        for line in card.body.splitlines():
            text.append("  " + line + "\n", style="#e8b0b0")
    elif card.kind == "compaction":
        text.append(f"🗜 {card.title}: {card.body}\n", style="italic #ce93d8")
    elif card.kind == "command":
        text.append(f"{card.title}\n", style="bold #90caf9")
        for line in card.body.splitlines():
            text.append("  " + line + "\n", style="#b0bec5")
    elif card.kind == "stop":
        # A ceiling ended the turn. Amber, not red: it is a budget doing its job,
        # not a failure, but it must be visible or the agent just seems to stop.
        text.append(f"■ {card.title}: {card.body}\n", style="bold #ffb74d")
    elif card.kind == "you":
        text.append("> " + card.body + "\n", style="bold #90caf9")
    elif card.kind == "error":
        text.append(card.body + "\n", style="bold red")
    return text


class LogEvent(Message):
    """One logger event, posted thread-safely from the subscribe fan-out."""

    def __init__(self, event: dict[str, Any]) -> None:
        self.event = event
        super().__init__()


class ReplNotice(Message):
    """One line of routed REPL output, posted thread-safely."""

    def __init__(self, text: str) -> None:
        self.text = text
        super().__init__()


class ReplCommandProvider(Provider):
    """Feeds the command palette (Ctrl+P) from the REPL's own command table."""

    async def search(self, query: str) -> Hits:
        app = self.app
        if not isinstance(app, Tui):
            return
        matcher = self.matcher(query)
        for name, summary in [("/info", "session card: config, servers, limits")]:
            score = matcher.match(name)
            if score > 0:
                yield Hit(score, matcher.highlight(name),
                          partial(app.submit_line, name), help=summary)
        for command in app.repl.commands:
            score = matcher.match(command.name)
            if score > 0:
                yield Hit(score, matcher.highlight(command.name),
                          partial(app.submit_line, command.name),
                          help=command.summary)


ART = [
    r"      o                                       (\____/)  ",
    r"     /|\    o==[]::::::::::::::::>             ( o  o )  ",
    r"     / \                                       /  ww  \  ",
    r"    hero        the labyrinth awaits           minotaur  ",
]


class SplashScreen(ModalScreen):
    """The start screen: art, the session card, and a Start button.

    The card answers "did it load?" up front: version, provider and model, each
    MCP server with its tool count, config dir. Zero tools renders as a loud red
    warning. ``/info`` reopens it mid-session.
    """

    CSS = """
    SplashScreen { align: center middle; }
    #splash { width: 76; max-height: 90%; background: $surface;
              border: round $primary; padding: 1 2; }
    #splash-art { color: #8d6e63; }
    #splash-card { margin: 1 0; }
    #splash-buttons { height: 3; align-horizontal: center; }
    #splash-buttons Button { margin: 0 2; }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="splash"):
            yield Static(Text("\n".join(ART)), id="splash-art")
            yield Static(self._card(), id="splash-card")
            with Horizontal(id="splash-buttons"):
                yield Button("Start", variant="success", id="start")
                yield Button("Quit", variant="error", id="quit")

    def _card(self) -> Text:
        repl = self.app.repl
        card = Text()
        card.append(f"boukensha {repl.version or ''} · the journey observatory\n",
                    style="bold")
        card.append("\n")
        card.append(str(repl.banner()).rstrip() + "\n")
        tools = len(repl.registry)
        if tools:
            card.append(f"tools     {tools} registered\n", style="green")
        else:
            card.append("tools     NONE REGISTERED: the MCP server did not "
                        "start.\n          Check `mud-manager` is on PATH and "
                        "settings.yaml mcp_servers.\n", style="bold red")
        window = getattr(repl, "context_window", None)
        if window:
            card.append(f"context   {fmt_tokens(window)} token window\n")
        card.append("\n")
        card.append("Enter/Start to play · /info reopens this card · "
                    "Ctrl+P commands", style="dim")
        return card

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "quit":
            self.app.exit()
        else:
            self.action_dismiss_splash()

    def on_key(self, event) -> None:
        if event.key in ("enter", "escape", "s"):
            event.stop()
            self.action_dismiss_splash()
        elif event.key == "q":
            event.stop()
            self.app.exit()

    def action_dismiss_splash(self) -> None:
        try:
            self.dismiss()
        except Exception:  # idempotent: a double close is a no-op
            pass


class Tui(App):
    """A Textual application: the readable, live journey view over a Repl."""

    SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    TICK = 0.1

    COMMANDS = App.COMMANDS | {ReplCommandProvider}

    CSS = """
    #header { height: 1; background: #22303a; color: #cfd8dc; }
    #tabs { height: 1fr; }
    TabPane { padding: 0; }
    #dash { height: 1fr; }
    #tabs.combat { border: heavy #ff5555; }
    #tabs.combat.beat { border: heavy #7a0000; }
    #mud-scroll { width: 2fr; border-right: solid #37474f; }
    #combat { display: none; border: round #ff5555; height: auto;
              max-height: 14; padding: 0 1; margin: 0 0 1 0; }
    #combat.on { display: block; }
    #combat.on.beat { border: round #7a0000; }
    #mud { padding: 0 1; }
    #side { width: 1fr; padding: 0 1; }
    #goal { height: auto; padding: 0 0 1 0; }
    #avatar { height: 3; content-align: center middle; }
    #recent { height: auto; color: #b0bec5; }
    #thinking-scroll { height: 1fr; }
    #thinking { color: #9e9e9e; }
    #feed-search { border: none; height: 1; background: #263238; }
    #feed { height: 1fr; }
    #progress { height: 1; color: cyan; }
    #inputrow { height: 1; }
    #prompt { width: auto; color: green; text-style: bold; }
    #input { border: none; height: 1; padding: 0; }
    """

    BINDINGS = [
        Binding("escape", "cancel_turn", "Cancel turn", priority=True),
        Binding("ctrl+t", "next_tab", "Switch tab", priority=True),
        Binding("ctrl+f", "focus_search", "Search feed", priority=True),
        Binding("ctrl+l", "clear_history", "Clear", priority=True),
        Binding("ctrl+c", "quit_app", "Quit", show=False, priority=True),
        Binding("ctrl+d", "quit_app", "Quit", priority=True),
    ]

    TAB_CYCLE = ("tab-dashboard", "tab-feed")

    def __init__(self, repl: Repl, splash: bool = True) -> None:
        self._repl = repl
        self._journey = JourneyParser()              # vitals + character stats
        self._present = Presenter()                  # readable cards
        self._show_splash = splash
        self._worker: Any = None
        self._spinner_timer: Any = None
        self._live = self._idle_live()
        self._ctx_history: list[int] = []
        self._header_line = ""
        self._progress_line = ""
        #: A slow always-on frame counter driving the state badge animation and
        #: the combat heartbeat pulse.
        #: The slash command currently running, so its output is rendered as a
        #: command result rather than as the agent speaking.
        self._pending_command: str | None = None
        self._anim_frame = 0
        self._anim_timer: Any = None
        super().__init__()

    @property
    def repl(self) -> Repl:
        return self._repl

    @property
    def journey(self) -> JourneyParser:
        return self._journey

    @property
    def present(self) -> Presenter:
        return self._present

    @staticmethod
    def _idle_live() -> dict[str, Any]:
        # ``iteration`` belongs here so it RESETS per turn. Its absence is what
        # made the header read iter 0/N for the life of the feature: the key was
        # read and never written, so it defaulted forever.
        return {"active": False, "spinner_idx": 0, "start_time": None,
                "elapsed": 0.0, "action": "", "iteration": 0}

    # -- layout ------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Static("", id="header")
        with TabbedContent(id="tabs", initial="tab-dashboard"):
            with TabPane("Dashboard", id="tab-dashboard"):
                with Horizontal(id="dash"):
                    with VerticalScroll(id="mud-scroll"):
                        yield Static("", id="combat")
                        yield Static("", id="mud")
                    with Vertical(id="side"):
                        yield Static("", id="goal")
                        yield Static("", id="avatar")
                        yield Static("", id="recent")
                        with VerticalScroll(id="thinking-scroll"):
                            yield Static("", id="thinking")
            with TabPane("Feed", id="tab-feed"):
                yield Input(placeholder="search the journey…", id="feed-search")
                yield RichLog(id="feed", wrap=True, markup=False, auto_scroll=True)
        yield Static("", id="progress")
        with Horizontal(id="inputrow"):
            yield Static(Repl.PROMPT, id="prompt")
            # /help leads, because it is the only affordance that tells a person
            # the command surface exists at all. The key bindings are discoverable
            # by trying them; a slash command is not.
            yield Input(placeholder="Type a message, or /help for commands  "
                        "(Ctrl+T: tabs · Ctrl+F: search · Ctrl+P: palette)",
                        id="input")

    def on_mount(self) -> None:
        if len(self._repl.registry) == 0:
            self._present.add_error(
                "NO TOOLS REGISTERED: the MCP server did not start. Check "
                "`mud-manager` is on PATH and .boukensha/settings.yaml.")
            self.notify("No tools: MCP server failed to start", severity="error",
                        timeout=10)
        # The TUI renders the trace itself from logger events, so silence the
        # REPL's own activity feed: otherwise its `[iteration]` / `-> tool`
        # lines leak through on_output and pollute the cards and the thinking.
        # The agent's final reply is not part of the feed, so it still arrives.
        self._repl.quiet = True
        self._repl.on_output(lambda s: self.post_message(ReplNotice(s)))
        self._repl.logger.subscribe(lambda e: self.post_message(LogEvent(e)))
        self.query_one("#input", Input).focus()
        # A gentle always-on timer animates the state badge and pulses the
        # combat edge like a heartbeat while a fight is on.
        self._anim_timer = self.set_interval(0.5, self._animate_tick)
        self._refresh_all()
        if self._show_splash:
            self.push_screen(SplashScreen())

    # -- event delivery (app thread, via post_message) -----------------------

    def on_log_event(self, message: LogEvent) -> None:
        event = message.event
        # The parser keeps vitals/character state; the presenter makes cards.
        self._journey.on_event(event)
        new_cards = self._present.on_event(event)
        # Liveness only, never the raw trace: a humanized current action and a
        # per-call context sample for the ctx% gauge.
        phase = event.get("phase")
        if phase == "iteration":
            # The live step counter the header's iter chip reads. Without this
            # the chip is not a counter, it is a constant with a denominator.
            self._live["iteration"] = int(event.get("n") or 0)
        elif phase == "tool_call" and new_cards:
            self._live["action"] = new_cards[0].body.lstrip("-> ")
        elif phase == "response":
            itok = int(event.get("input_tokens") or 0)
            if itok:
                self._ctx_history.append(itok)
                del self._ctx_history[:-30]
        elif phase == "compaction":
            # A dashboard flash so the freeing is visible, not just a Feed card.
            self.notify("context compacted to free the window", timeout=4)
        if new_cards:
            self._write_feed(new_cards)
        self._refresh_all()

    def on_repl_notice(self, message: ReplNotice) -> None:
        # With the feed silenced, on_output carries the agent's final reply, the
        # occasional error notice, and the output of any slash command. A command
        # result is NOT the agent speaking: routing it into the thinking view
        # hides it where nobody looks for it, so it gets its own card kind.
        text = message.text
        if any(m in text for m in ("[error]", "[cancelled]", "[aborted]",
                                   " ERROR:")):
            stripped = text.strip()
            if stripped:
                self._write_feed([self._present.add_error(stripped)])
        elif self._pending_command is not None:
            stripped = text.strip()
            if stripped:
                self._write_feed(
                    [self._present.add_command(self._pending_command, stripped)])
                # The Feed card is the record, but a person typing a command on the
                # Dashboard never sees it. A toast reaches them on whichever tab
                # they are on, which is the same pattern this file already uses for
                # a compaction, an MCP failure, and a cancellation.
                self._notify_command(self._pending_command, stripped)
        else:
            self._write_feed(self._present.add_reply(text))
        self._refresh_all()

    #: Beyond this, a command result is summarized in the toast rather than
    #: truncated mid-content, and the Feed carries the whole thing.
    TOAST_CHARS = 110

    def _notify_command(self, name: str, output: str) -> None:
        """Toast a command's result, short form for long output.

        `/history`, `/tools` and `/system` do not fit a notification, so those are
        announced by their first line plus where the full text went. A rejection
        toasts as an error, since a command that was not understood is the case a
        person most needs to see.
        """
        lines = [line for line in output.splitlines() if line.strip()]
        first = lines[0].strip().rstrip(":") if lines else ""
        rejected = "unknown command" in output.lower()
        if len(lines) > 1 or len(first) > self.TOAST_CHARS:
            body = (f"{first} · see the Feed tab" if first
                    else f"{len(lines)} lines · see the Feed tab")
        else:
            body = first
        self.notify(body, title=name,
                    severity="error" if rejected else "information")

    # -- rendering ---------------------------------------------------------

    def _refresh_all(self) -> None:
        self._header_line = self._render_header()
        self._progress_line = self._progress_text()
        try:
            self.query_one("#header", Static).update(Text(self._header_line))
            self.query_one("#mud", Static).update(self._render_mud())
            self.query_one("#goal", Static).update(self._render_goal())
            self.query_one("#recent", Static).update(self._render_recent())
            self.query_one("#thinking", Static).update(self._render_thinking())
            self.query_one("#avatar", Static).update(self._render_avatar())
            self.query_one("#progress", Static).update(Text(self._progress_line))
            self._update_combat_box()
        except NoMatches:
            pass
        except Exception:  # noqa: BLE001 - render must degrade, never crash.
            pass

    #: Overflow marker. A strip that clips silently is worse than a crowded one,
    #: because nothing tells the reader that something is gone.
    OVERFLOW_MARK = "+{n}\u2026"

    #: Alert glyph for a condition that needs acting on. A condition rendered
    #: like a stat reads like a stat: a run ended on "You are too exhausted" with
    #: hungry and thirsty sitting unremarked in a row of dots.
    ALERT = "\u26a0"

    @property
    def _width(self) -> int:
        """Terminal width, or 0 meaning unknown so nothing is dropped."""
        try:
            return int(self.size.width)
        except Exception:  # noqa: BLE001 - layout must never break a render.
            return 0

    @classmethod
    def _fit(cls, items: list[tuple[int, str]], width: int,
             sep: str = " \u00b7 ") -> str:
        """Join ``items`` to fit ``width``, dropping the lowest priority first.

        Each item is ``(rank, text)`` in DISPLAY order, rank 0 being the most
        important. What does not fit is dropped from the least important end and
        the count of drops is shown, so a reader can always tell the difference
        between "nothing else to report" and "no room to report it".

        A width of 0 means unknown, and then nothing is dropped: guessing a
        terminal is narrow and hiding real information is the worse error.
        """
        kept = list(items)
        dropped = 0
        while True:
            body = sep.join(text for _rank, text in kept if text)
            mark = cls.OVERFLOW_MARK.format(n=dropped) if dropped else ""
            line = sep.join(p for p in (body, mark) if p)
            if width <= 0 or len(line) <= width or not kept:
                return line
            victim = max(range(len(kept)), key=lambda i: kept[i][0])
            kept.pop(victim)
            dropped += 1

    def _render_header(self) -> str:
        """GAME STATE, and nothing else.

        This is the strip a player watches continuously, so it carries only what
        the game reports. Agent economics moved to the footer, beside the stop
        reason they explain, and the clock left entirely: the terminal has one and
        it was competing with HP for width.

        Ranks order the drop, not the display. HP and a condition outrank Gold
        because a reader who loses one line of width should lose the number they
        were least likely to act on.
        """
        vit = self._journey.state.vitals
        char = self._journey.state.char
        status = self._journey.state.status
        items: list[tuple[int, str]] = []

        # Infrastructure earns width only when it is broken. Working tools are a
        # dot, and the dot is the first thing dropped.
        if self._repl.servers and len(self._repl.registry):
            items.append((9, "\u25cf"))
        else:
            items.append((0, "NO TOOLS"))

        if vit["hp"] is not None:
            items.append((1, f"HP {vit['hp']}/{vit['max_hp']}" if vit["max_hp"]
                          else f"HP {vit['hp']}"))
        conditions = [name for name in ("hungry", "thirsty") if status[name]]
        if conditions:
            items.append((2, f"{self.ALERT} " + " ".join(conditions)))
        if vit["moves"] is not None:
            items.append((3, f"Moves {vit['moves']}"))
        if status["stance"]:
            items.append((4, status["stance"]))
        if vit["mana"] is not None:
            items.append((5, f"Mana {vit['mana']}"))
        if char["level"] is not None:
            items.append((6, f"Lv {char['level']}"))
        if char["gold"] is not None:
            items.append((7, f"Gold {char['gold']}"))
        return " " + self._fit(items, self._width - 1)

    def _economics_items(self) -> list[tuple[int, str]]:
        """The agent's own numbers, for the footer rather than the header.

        Glanced at rather than watched, and they belong next to the stop reason
        because that is what they explain: a turn that ended on a ceiling ended
        on one of these.
        """
        # Ranks are explicit rather than positional, because two items sharing a
        # rank makes the drop order depend on list position, which is arbitrary.
        # Order here is also the display order: steps, then window, then work,
        # then money.
        ceilings = self._ceiling_labels()
        labels = dict(zip(("iter", "tok", "cost"), ceilings))
        items: list[tuple[int, str]] = []
        if labels.get("iter"):
            items.append((1, labels["iter"]))
        ctx = self._ctx_label().strip(" \u00b7 ")
        if ctx:
            items.append((2, ctx))
        if labels.get("tok"):
            items.append((3, labels["tok"]))
        if labels.get("cost"):
            items.append((4, labels["cost"]))
        ratio = getattr(getattr(self._repl, "context", None), "amplification",
                        None)
        if callable(ratio):
            value = ratio()
            if value and value >= 1.5:
                # Only worth screen space once repetition is real. This is the
                # number that explains a bill nobody expected.
                items.append((9, f"x{value} repeat"))
        return items

    def _ceiling_labels(self) -> list[str]:
        """Every ceiling as current over limit, and every measurement either way.

        Two rules, the second learned by playing rather than by any test:

        - A number with no denominator cannot warn anyone. The figure that ended
          a turn was 62,357 against 60,000 and only the first half was on screen,
          so each row carries its limit and the one closest to tripping is
          marked, which puts the ceiling about to bite where the eye goes.
        - DISABLING A CEILING TURNS OFF THE LIMIT, NEVER THE MEASUREMENT. Setting
          ``max_turn_tokens: 0`` used to remove the token count itself, which
          contradicts the argument that volume processed is a metric in its own
          right. A fraction when a limit exists, a bare number when it does not,
          and never nothing.
        """
        ctx = getattr(self._repl, "context", None)
        iters = self._live.get("iteration") or 0
        tokens = getattr(ctx, "turn_tokens", 0) if ctx else 0
        spend = getattr(ctx, "turn_cost", 0.0) if ctx else 0.0
        rows: list[tuple[str | None, float, float | None, str]] = []

        max_iters = getattr(self._repl, "max_iterations", None)
        rows.append(("iter", iters, max_iters,
                     f"iter {iters}/{max_iters}" if max_iters
                     else f"iter {iters}"))
        max_tokens = getattr(self._repl, "max_turn_tokens", None)
        rows.append(("tok", tokens, max_tokens,
                     f"tok {fmt_tokens(tokens)}/{fmt_tokens(max_tokens)}"
                     if max_tokens else f"tok {fmt_tokens(tokens)}"))
        # With a money ceiling the turn is measured against it. With none, the
        # session total is the useful figure, and money stays on screen either
        # way. A row with no limit is excluded from the closest-to-tripping mark
        # below, since nothing can be close to a ceiling that is not set.
        max_cost = getattr(self._repl, "max_turn_cost", None)
        rows.append(("cost", spend, max_cost,
                     f"${spend:.3f}/${max_cost:.2f}" if max_cost
                     else f"${round(self._repl.cost, 4)}"))

        closest = None
        for name, current, limit, _label in rows:
            if name and limit:
                fraction = current / limit
                if closest is None or fraction > closest[0]:
                    closest = (fraction, name)
        out = []
        for name, _current, _limit, label in rows:
            if closest and name == closest[1] and closest[0] >= 0.5:
                label = f"[{label}]"
            out.append(label)
        return out

    #: Context-usage alert threshold (percent of the model window). Step-12
    #: delta: the shared Context tracks window pressure and the TUI reads it,
    #: never recomputing what the compactor already knows.
    CTX_ALERT_PCT = 90

    def _ctx_label(self) -> str:
        """CURRENT window occupancy from the shared Context, not lifetime spend.

        Step 12 owns context management, so the header reads the same
        current_tokens / context_window the compactor acts on and the two
        cannot disagree. Falls back to the per-call history before a Context
        window is known.
        """
        ctx = getattr(self._repl, "context", None)
        if ctx is not None and getattr(ctx, "context_window", None):
            pct = ctx.usage_pct()
            warn = " ⚠" if pct >= self.CTX_ALERT_PCT else ""
            return f"ctx {pct}%{warn} {sparkline(self._ctx_history)}"
        last = self._ctx_history[-1] if self._ctx_history else 0
        window = getattr(self._repl, "context_window", None)
        if last and window:
            return f"ctx {round(100 * last / window)}% {sparkline(self._ctx_history)}"
        if last:
            return f"ctx {fmt_tokens(last)}"
        return ""

    def _render_mud(self) -> Text:
        """The dashboard's main area: the current room, then any one-off message."""
        room = self._present.current_room
        text = Text()
        if room is None:
            text.append("Waiting for the first room…\n", style="dim")
            return text
        text.append(room.title + "\n", style="bold #d7af5f")
        if room.exits:
            text.append(f"exits: {spell_exits(room.exits)}\n\n", style="cyan")
        if room.body:
            text.append(room.body + "\n", style="#cfd8dc")
        if self._present.latest_message:
            # A one-off MUD reply (a shop list, an examine): keep its lines so a
            # list stays a list rather than one run-on line.
            text.append("\n")
            for i, line in enumerate(self._present.latest_message.splitlines()):
                text.append(("· " if i == 0 else "  ") + line + "\n",
                            style="italic #9e9e9e")
        return text

    def _render_goal(self) -> Text:
        """The standing objective, pinned at the top of the side column: the
        latest instruction the user gave the agent."""
        text = Text()
        text.append("GOAL\n", style="bold")
        goal = self._present.current_goal
        text.append(goal if goal else "awaiting your first instruction",
                    style="#ffd54f" if goal else "dim")
        return text

    def _render_recent(self) -> Text:
        """The compact side header: the last few humanized actions."""
        text = Text()
        text.append("RECENT\n\n", style="bold")
        if not self._present.recent_actions:
            text.append("no actions yet\n", style="dim")
        for card in self._present.recent_actions:
            text.append(card.body + "\n", style="#5fd7af")
        text.append("\nTHINKING", style="bold")
        return text

    def _render_thinking(self):
        """The current thinking / objective in full, rendered as markdown so a
        summary's list or table stays readable. Scrolls in its own pane."""
        thinking = self._present.current_thinking
        if thinking is None or not thinking.body.strip():
            return Text("nothing yet", style="dim")
        return Markdown(thinking.body)

    def _render_combat(self) -> Text:
        """The fight box: the blow-by-blow stream and the outcome once known."""
        p = self._present
        text = Text()
        text.append(f"⚔ {p.combat_result or 'IN COMBAT'}\n\n", style="bold red")
        for line in p.combat_lines[-12:]:
            text.append(line + "\n", style="#e8b0b0")
        return text

    def _update_combat_box(self) -> None:
        """Show the fight box while a fight is live or freshly resolved, and
        flag the tabs edge for the heartbeat pulse while it is live."""
        try:
            box = self.query_one("#combat", Static)
            tabs = self.query_one("#tabs")
        except NoMatches:
            return
        show = bool(self._present.combat_lines or self._present.combat_result)
        box.set_class(show, "on")
        tabs.set_class(self._present.combat_active, "combat")
        if show:
            box.update(self._render_combat())

    #: The state-badge frames per stance (unicode, the terminal ceiling for an
    #: "animated character"). Fighting and sleeping cycle for a sense of motion.
    def _render_avatar(self) -> Text:
        frame = self._anim_frame
        if self._present.combat_active:
            glyph, label, style = (["⚔️ ", " ⚔️"][frame % 2], "fighting",
                                   "bold red")
        else:
            stance = self._journey.state.status.get("stance")
            if stance == "sleeping":
                glyph, label, style = "😴 " + "z" * (1 + frame % 3), "sleeping", "cyan"
            elif stance in ("resting", "sitting"):
                glyph, label, style = "🧘", stance, "green"
            elif stance == "standing" or stance is None:
                glyph, label, style = "🧍", stance or "idle", "#b0bec5"
            else:
                glyph, label, style = "🧍", stance, "#b0bec5"
        text = Text()
        text.append(glyph + "  ", style=style)
        text.append(label, style=style)
        return text

    def _animate_tick(self) -> None:
        """Advance the badge animation and pulse the combat edge (heartbeat)."""
        self._anim_frame += 1
        beat = self._anim_frame % 2 == 0
        active = self._present.combat_active
        try:
            self.query_one("#avatar", Static).update(self._render_avatar())
            self.query_one("#tabs").set_class(active and beat, "beat")
            self.query_one("#combat").set_class(active and beat, "beat")
        except NoMatches:
            pass
        except Exception:  # noqa: BLE001 - animation must never crash a turn.
            pass

    def _write_feed(self, cards: list[Card]) -> None:
        query = ""
        try:
            query = self.query_one("#feed-search", Input).value.lower()
        except NoMatches:
            pass
        try:
            log = self.query_one("#feed", RichLog)
        except NoMatches:
            return
        for card in cards:
            if query and query not in self._card_haystack(card):
                continue
            log.write(render_card(card))

    def _rebuild_feed(self, query: str) -> None:
        try:
            log = self.query_one("#feed", RichLog)
        except NoMatches:
            return
        log.clear()
        needle = query.lower()
        for card in self._present.cards:
            if needle and needle not in self._card_haystack(card):
                continue
            log.write(render_card(card))

    @staticmethod
    def _card_haystack(card: Card) -> str:
        """Searchable text of a card (its rendered form may be Markdown, which
        has no plain-text accessor, so search reads the card's own fields)."""
        return f"{card.title} {card.body}".lower()

    def _progress_text(self) -> str:
        """Liveness and the agent's own numbers, on the line that was near empty.

        The state of the run and the figures that explain it read together: a
        turn that stopped on a ceiling stopped on one of the numbers beside it.
        The state itself is rank 0 and never dropped, because a footer that lost
        it would say nothing at all.
        """
        if self._live["active"]:
            frame = self.SPINNER_FRAMES[self._live["spinner_idx"]]
            secs = int(self._live["elapsed"])
            action = self._live["action"] or "thinking"
            state = f"{frame} playing: {action} \u00b7 {secs}s"
        else:
            # Idle: say how the last turn ended. A turn cut short by a ceiling is
            # otherwise indistinguishable from one the agent chose to finish.
            stop = self._present.last_stop or "ready"
            state = f"[{stop}] \u00b7 {self._repl.turn} turns"
        items = [(0, state)] + self._economics_items()
        return "  " + self._fit(items, self._width - 2)

    # -- input and the one worker path --------------------------------------

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "feed-search":
            self._rebuild_feed(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "feed-search":
            return
        text = event.value.strip()
        self.query_one("#input", Input).value = ""
        if text:
            self.submit_line(text)

    def submit_line(self, text: str) -> None:
        """Route one line exactly as the plain REPL would, then run off-thread."""
        if text.strip() == "/info":
            self.push_screen(SplashScreen())
            return
        kind, payload = Repl.classify_input(text)
        self._pending_command = payload.split()[0] if kind == "command" else None
        if kind == "turn":
            self._write_feed([self._present.add_user(payload)])
        self._begin_submission()
        self._worker = self.run_worker(
            self._submission_worker(kind, text, payload),
            name="submission", group="submission", exclusive=True)

    async def _submission_worker(self, kind: str, text: str, payload: str) -> None:
        try:
            if kind == "command":
                result = await asyncio.to_thread(self._repl.handle_command, payload)
                if result == "quit":
                    self.exit()
                    return
                # /clear drops the model's history, so the Feed has to go with it
                # or the screen and the model disagree about what was said.
                if payload.split()[0] in ("/clear",):
                    self._present.clear()
                    self._rebuild_feed("")
            else:
                await asyncio.to_thread(self._repl.run_turn, payload)
        except Exception as exc:  # noqa: BLE001 - a front-end must stay alive.
            self._write_feed([self._present.add_error(
                f"{type(exc).__name__}: {exc}")])
            self.notify(str(exc), severity="error")
        finally:
            self._pending_command = None
            self._end_submission()

    def _begin_submission(self) -> None:
        self._live = self._idle_live()
        self._live.update(active=True, start_time=time.monotonic())
        self._spinner_timer = self.set_interval(self.TICK, self._advance_spinner)
        self._refresh_all()

    def _end_submission(self) -> None:
        if self._spinner_timer is not None:
            self._spinner_timer.stop()
            self._spinner_timer = None
        self._live = self._idle_live()
        self._refresh_all()

    def _advance_spinner(self) -> None:
        if not self._live["active"]:
            return
        self._live["spinner_idx"] = (
            self._live["spinner_idx"] + 1) % len(self.SPINNER_FRAMES)
        if self._live["start_time"] is not None:
            self._live["elapsed"] = time.monotonic() - self._live["start_time"]
        self._refresh_all()

    # -- keyboard actions --------------------------------------------------

    def action_cancel_turn(self) -> None:
        if isinstance(self.screen, SplashScreen):
            self.screen.action_dismiss_splash()
            return
        if self._repl.cancel_turn():
            self.notify("cancelling turn…", severity="warning")

    def action_next_tab(self) -> None:
        try:
            tabs = self.query_one("#tabs", TabbedContent)
        except NoMatches:
            return
        current = tabs.active or self.TAB_CYCLE[0]
        idx = (self.TAB_CYCLE.index(current) + 1) % len(self.TAB_CYCLE) \
            if current in self.TAB_CYCLE else 0
        tabs.active = self.TAB_CYCLE[idx]

    def action_focus_search(self) -> None:
        try:
            self.query_one("#tabs", TabbedContent).active = "tab-feed"
            self.query_one("#feed-search", Input).focus()
        except NoMatches:
            pass

    def on_tabbed_content_tab_activated(
            self, event: TabbedContent.TabActivated) -> None:
        # A RichLog sized while hidden defers rendering, so rebuild the feed
        # from the card list whenever its tab comes back into view.
        if event.pane.id == "tab-feed":
            try:
                query = self.query_one("#feed-search", Input).value
            except NoMatches:
                query = ""
            self._rebuild_feed(query)

    def action_clear_history(self) -> None:
        self.submit_line("/clear")

    def action_quit_app(self) -> None:
        self.exit()

    def __str__(self) -> str:
        return (f"<Tui turn={self._repl.turn} cards={len(self._present.cards)} "
                f"active={self._live['active']}>")

    __repr__ = __str__
