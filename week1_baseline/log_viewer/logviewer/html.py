"""The page's raw materials: escaping, formatting, and one visual language.

Kept apart from `logweb` because building an element and deciding what a page contains
are different jobs, and because everything here is worth testing on its own. A helper
that escapes wrongly is a security hole rather than a rendering nit.

Three rules.

EVERYTHING IS ESCAPED, ONCE. A MUD carries player-authored text and a tool result can
contain anything, so no value reaches the page without going through :func:`esc`. The
only unescaped strings are the ones this module builds itself.

ABSENT IS RENDERED AS ABSENT. Every formatter takes ``None`` and returns a marked
absence rather than a zero. A viewer that printed `$0.0000` for a model with no
published price would be stating something false about money.

ONE VISUAL LANGUAGE. A tool call, a reply, an error, MUD output and a compaction are
distinguishable before any label is read, so the kinds are a closed set here rather
than a class name chosen at each call site.
"""

from __future__ import annotations

import html
import re
from typing import Any

#: What a missing value looks like. A middle dot rather than a dash, so it cannot be
#: mistaken for a minus sign in a column of numbers.
ABSENT = "·"

#: The kinds of thing a session contains. Closed, because the whole point of one visual
#: language is that a sixth kind is a decision rather than a new CSS class.
KINDS = ("reply", "plan", "reasoning", "call", "result", "mud", "error",
         "compaction", "retry", "ceiling", "raw")

#: ANSI SGR sequences, which MUD output is full of. Matched so they can be turned into
#: spans rather than shown as escape gibberish or stripped into a grey wall.
_ANSI = re.compile(r"\x1b\[([0-9;]*)m")

#: The sixteen SGR colours a MUD actually uses, as CSS custom properties so both
#: themes can define them. Bright variants share the hue and differ in the token.
_SGR_COLOURS = {
    30: "black", 31: "red", 32: "green", 33: "yellow",
    34: "blue", 35: "magenta", 36: "cyan", 37: "white",
    90: "bright-black", 91: "bright-red", 92: "bright-green",
    93: "bright-yellow", 94: "bright-blue", 95: "bright-magenta",
    96: "bright-cyan", 97: "bright-white",
}


def esc(value: Any) -> str:
    """Any value to page-safe text.

    ``None`` becomes the absence marker rather than the string "None", because a page
    reading "None" has told the reader about Python rather than about their session.
    """
    if value is None:
        return ABSENT
    return html.escape(str(value), quote=True)


def attr(value: Any) -> str:
    """A value for an attribute position, quotes included."""
    return f'"{html.escape("" if value is None else str(value), quote=True)}"'


def tokens(count: int | None) -> str:
    """A token count, shortened, because six-digit numbers do not compare by eye."""
    if count is None:
        return ABSENT
    count = int(count)
    if count < 1000:
        return str(count)
    if count < 1_000_000:
        return f"{count / 1000:.1f}k"
    return f"{count / 1_000_000:.2f}M"


def money(amount: float | None, places: int = 4) -> str:
    """Money, or an honest absence. Never a zero standing in for unknown."""
    if amount is None:
        return ABSENT
    return f"${amount:.{places}f}"


#: A labelled figure reads as a phrase, so a bare middle dot in it looks like a typo:
#: "took · · cost unavailable" was the header before. In a table column the dot is
#: right, and in a sentence the word is.
UNRECORDED = "unrecorded"


def labelled(label: str, value: str) -> str:
    """``label value``, with an absent value stated in words rather than as a dot."""
    return f"{label} {UNRECORDED if value == ABSENT else value}"


def duration(ms: float | None) -> str:
    """Wall clock at the scale a reader compares it at."""
    if ms is None:
        return ABSENT
    seconds = float(ms) / 1000
    if seconds < 1:
        return f"{int(ms)}ms"
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, rest = divmod(int(seconds), 60)
    return f"{minutes}m {rest}s"


def percent(fraction: float | None, places: int = 0) -> str:
    if fraction is None:
        return ABSENT
    return f"{fraction * 100:.{places}f}%"


def ansi(text: str) -> str:
    """MUD output with its colours kept, as spans.

    Stripping the colours would make the game unreadable in the one place it should
    read like the game, and passing them through raw would show escape codes. Every
    text run is escaped before any markup is added, so colour handling cannot become
    an injection path.
    """
    out: list[str] = []
    depth = 0
    position = 0
    for match in _ANSI.finditer(text):
        out.append(esc(text[position:match.start()]))
        position = match.end()
        codes = [int(c) for c in match.group(1).split(";") if c.isdigit()] or [0]
        for code in codes:
            if code == 0:
                out.append("</span>" * depth)
                depth = 0
            elif code == 1:
                out.append('<span class="b">')
                depth += 1
            elif code in _SGR_COLOURS:
                out.append(f'<span class="c-{_SGR_COLOURS[code]}">')
                depth += 1
    out.append(esc(text[position:]))
    out.append("</span>" * depth)
    return "".join(out)


def strip_ansi(text: str) -> str:
    """The same text with the codes removed, for a title or a summary line."""
    return _ANSI.sub("", text)


def preview(text: Any, width: int = 90) -> str:
    """One line of a long value, for a collapsed row.

    Newlines collapse, because a preview that wrapped would stop being one line and
    the row it sits in is one line tall.
    """
    flat = " ".join(strip_ansi(str("" if text is None else text)).split())
    if len(flat) <= width:
        return esc(flat)
    return esc(flat[:width - 1]) + "…"


#: Elements HTML forbids a closing tag on. Emitting ``</input>`` is not cosmetic: it
#: makes the document ill-formed, and a parser recovering from it can reparent
#: everything after the mistake.
VOID = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input",
                  "link", "meta", "param", "source", "track", "wbr"})


def tag(name: str, content: str = "", **attrs: Any) -> str:
    """One element. Attribute names ending in an underscore drop it, for ``class_``.

    A void element takes no closing tag and no content, and passing content to one is
    a caller error worth raising on rather than silently dropping.
    """
    parts = []
    for key, value in attrs.items():
        if value is None or value is False:
            continue
        key = key.rstrip("_").replace("_", "-")
        if value is True:
            parts.append(key)
        else:
            parts.append(f"{key}={attr(value)}")
    opened = f"<{name}{' ' if parts else ''}{' '.join(parts)}>"
    if name in VOID:
        if content:
            raise ValueError(f"<{name}> is a void element and cannot hold content")
        return opened
    return f"{opened}{content}</{name}>"


def chip(text: str, kind: str | None = None, title: str | None = None) -> str:
    """A small labelled value. The kind carries the colour, never the text."""
    classes = "chip" + (f" k-{kind}" if kind else "")
    return tag("span", esc(text), class_=classes, title=title)


def bar(fraction: float | None, label: str = "", kind: str = "") -> str:
    """A proportion, as a bar with its number beside it.

    ``None`` renders as the absence marker and no bar at all, since a zero-width bar
    and a bar of unknown length look identical.
    """
    if fraction is None:
        return f'<span class="absent">{ABSENT}</span>'
    width = max(0.0, min(1.0, fraction)) * 100
    inner = tag("span", "", class_=f"fill {kind}".strip(),
                style=f"width:{width:.1f}%")
    return tag("span", inner + tag("span", esc(label), class_="barlabel"),
               class_="bar")


def sparkline(values: list[float | None], width: int = 120, height: int = 24,
              label: str = "") -> str:
    """A tiny chart, as inline SVG, with gaps for the values that are not there.

    Generated rather than fetched: a chart library would be a dependency and a CDN
    asset would break offline. A `None` leaves a GAP rather than dropping to zero,
    because an unpriced session did not cost nothing.
    """
    known = [v for v in values if v is not None]
    if not known:
        return ""
    high = max(known) or 1.0
    step = width / max(len(values), 1)
    marks = []
    for index, value in enumerate(values):
        x = index * step
        if value is None:
            marks.append(tag("rect", "", x=f"{x:.1f}", y=height - 2, width=f"{step * 0.7:.1f}",
                             height=2, class_="gap"))
            continue
        bar_height = max(1.0, (value / high) * (height - 2))
        marks.append(tag("rect", "", x=f"{x:.1f}", y=f"{height - bar_height:.1f}",
                         width=f"{step * 0.7:.1f}", height=f"{bar_height:.1f}"))
    return tag("svg", "".join(marks), class_="spark", viewBox=f"0 0 {width} {height}",
               width=width, height=height, role="img",
               aria_label=label or "distribution")
