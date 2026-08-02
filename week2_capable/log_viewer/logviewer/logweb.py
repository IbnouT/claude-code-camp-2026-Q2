"""Logweb: the only module that emits HTML.

Everything else here is medium-independent and tested without a browser, so this layer
stays thin: it decides what a page contains and in what order, and takes every figure
from :mod:`logviewer.insights` and :mod:`logviewer.logview` rather than computing any of
its own.

Four properties every page has, because they are what make a viewer usable rather than
merely complete:

- ADDRESSABLE. A session, a lens, a turn and a filtered set are all URLs. The back
  button works and a link can be kept.
- PROGRESSIVE. Collapsed by default, expandable to the full value, with the RAW lens one
  click away from anywhere, so any rendering can be checked against the record.
- ABSENT AS ABSENT. Every value goes through a formatter that renders ``None`` as a
  marked absence. A page cannot accidentally print a zero for something unknown.
- CONTROLS ARE VISIBLE. Expand-all and next-failure are buttons that print their own
  shortcut, and the only two keys bound are the ones a browser cannot do for itself:
  `/` to search this record and `f` to jump to what went wrong. It already scrolls and
  already opens a disclosure triangle without being taught.

Seven lenses read the same session different ways. A lens is a VIEW, not a filter: each
answers something the others hide, and each has its own URL.
"""

from __future__ import annotations

import json
from typing import Any, Iterable

from . import insights
from . import world
from .html import (
    ABSENT, ansi, bar, chip, duration, esc, labelled, money, percent, preview,
    sparkline, strip_ansi, tag, tokens,
)
from .logview import Record, group_turns, pair_tools, totals
from .sessions import SessionSummary
from .style import CSS, JS

#: The seven lenses, in the order they are offered: the story first, then the
#: measurements, then the record itself. Each is a URL and each answers a question the
#: others cannot.
LENSES = (
    ("narrative", "Narrative", "the conversation as it ran"),
    ("map", "Map", "the path drawn on the world, rooms identified by their exits"),
    ("player", "Player", "confused, blocked, bored, overpowered, computed"),
    ("pressure", "Pressure", "prompt size against the window, compactions as cuts"),
    ("timeline", "Timeline", "where the wall clock went"),
    ("context", "Context", "what each prompt added"),
    ("tools", "Tools", "grouped by tool rather than by time"),
    ("journey", "Journey", "every movement and what the world said back"),
    ("errors", "Errors", "failures, retries and ceilings in one place"),
    ("raw", "Raw", "the record, so any rendering can be checked"),
)

LENS_NAMES = tuple(key for key, _label, _hint in LENSES)


# -- shell ------------------------------------------------------------------

def page(title: str, body: str, crumb: str = "", tools: str = "") -> str:
    """One complete document. No external request of any kind.

    The theme toggle stamps `data-theme` on the root so the viewer's choice beats the
    media query in both directions, and the page is styled for both grounds rather
    than one inverted into the other.
    """
    head = (
        f"<title>{esc(title)}</title>"
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<style>{CSS}</style>"
    )
    header = tag("header", tag("div", (
        tag("div", esc(crumb), class_="crumb") if crumb else ""
    ) + tag("h1", esc(title)), class_="grow") + tools + tag(
        "button", "◑", id="theme", type="button", title="switch theme",
        aria_label="switch between light and dark"), class_="top")
    keys = tag("footer", (
        "Nothing here is fetched, so this page works from a file with no network. "
        "The record is under <code>.boukensha/sessions/</code>."
    ), class_="foot")
    return (
        f"<!doctype html><html lang=\"en\"><head>{head}</head><body>"
        f"{tag('div', header + tag('main', body, class_='stack'), class_='wrap')}"
        f"{tag('div', keys, class_='wrap')}"
        f"<script>{JS}</script></body></html>"
    )


def _table(headers: Iterable[tuple[str, bool]], rows: Iterable[Iterable[str]],
           empty: str = "nothing to show") -> str:
    """A table, or a stated emptiness. Never an empty grid with a header on top."""
    body = "".join(tag("tr", "".join(cells)) for cells in rows)
    if not body:
        return tag("p", esc(empty), class_="empty")
    head = "".join(tag("th", esc(label), class_="num" if num else None)
                   for label, num in headers)
    return tag("div", tag("table", tag("thead", tag("tr", head)) + tag("tbody", body)),
               class_="scroll")


def _cell(value: str, num: bool = False, search: str | None = None) -> str:
    return tag("td", value, class_="num" if num else None, data_search=search)


def _search_box(placeholder: str, controls: bool = False) -> str:
    """The search field, and optionally the two controls that act on legs.

    Visible buttons rather than a legend of key bindings. The browser already scrolls and
    already opens a disclosure triangle, so the only things worth a shortcut are the two
    it cannot do, and each says so on its own face. A control you can see needs no
    legend, and a legend naming a binding without naming its reason invites the question
    "why does a browser need these keys".
    """
    row = tag("input", type="search", placeholder=placeholder,
              aria_label=placeholder) + tag("span", "", id="searchcount",
                                            class_="hint")
    if controls:
        row += (tag("button", "Expand all", type="button", id="expand",
                    class_="tool", title="open every leg on this page")
                + tag("button", "Next failure" + tag("kbd", "f"), type="button",
                      id="nextfail", class_="tool",
                      title="jump to the next leg that failed"))
    return tag("div", row + tag("span", tag("kbd", "/") + " to search",
                                class_="hint"), class_="row")


# -- L1, which run ----------------------------------------------------------

def sessions_page(summaries: list[SessionSummary]) -> str:
    """Which run. When, what model, how it ended, and what is wrong with it."""
    if not summaries:
        return page("Sessions", tag("section", tag(
            "p", "No session logs found. The agent writes them under "
                 "<code>.boukensha/sessions/</code> as it runs.",
            class_="empty"), class_="card"))

    priced = [s.cost for s in summaries if s.cost is not None]
    spend = sum(priced) if priced else None
    newest_first = summaries
    spark = sparkline([s.cost for s in reversed(newest_first[:24])],
                      width=360, height=34,
                      label="spend by session, newest right")

    rows = []
    for summary in newest_first:
        flags = []
        if summary.outcome not in ("completed", "no turns", "in progress"):
            flags.append(chip(summary.outcome, "ceiling"))
        elif summary.outcome != "completed":
            flags.append(chip(summary.outcome))
        if summary.failures:
            flags.append(chip(f"{summary.failures} failed", "failure"))
        if summary.compactions:
            flags.append(chip(f"{summary.compactions} compacted", "context"))
        rows.append((
            _cell(tag("a", esc(summary.when), href=f"/s/{summary.id}"),
                  search=f"{summary.when} {summary.model} {summary.outcome}"),
            _cell(esc(summary.model)),
            _cell(str(summary.turns), num=True),
            _cell(str(summary.iterations), num=True),
            _cell(summary.render_cost().replace("unavailable",
                                                f'<span class="absent">{ABSENT}</span>'),
                  num=True),
            _cell(tokens(summary.peak_input_tokens or None), num=True),
            _cell(" ".join(flags) or f'<span class="absent">{ABSENT}</span>'),
        ))

    head = (("when", False), ("model", False), ("turns", True), ("iters", True),
            ("cost", True), ("peak prompt", True), ("flags", False))
    summary_line = (
        f"{len(summaries)} sessions · {money(spend) if spend is not None else ABSENT}"
        + (f" · {len(summaries) - len(priced)} unpriced" if len(priced) < len(summaries)
           else ""))
    return page(
        "Sessions",
        tag("section", tag("div", esc(summary_line), class_="sub")
            + (tag("div", spark + tag("span", "spend by session, newest right. "
                                      f"{ABSENT} is unpriced, not zero",
                                      class_="hint"), class_="row") if spark else "")
            + _search_box("search sessions")
            + _table(head, rows), class_="card"),
        crumb="log viewer")


# -- L2, what happened ------------------------------------------------------

def _findings_block(records: list[Record], session_id: str) -> str:
    found = insights.findings(records)
    if not found:
        why = insights.why_nothing_stands_out(records)
        return tag("section", tag("div", "WHAT STANDS OUT", class_="eyebrow")
                   + tag("p", esc(why), class_="empty"), class_="card")
    items = []
    for finding in found:
        # The turn's own page, not an anchor: an anchor exists on one lens only, so
        # a jump from the timeline or the tools lens landed nowhere.
        link = (tag("a", f"turn {finding.turn} →",
                    href=f"/s/{session_id}/turn/{finding.turn}")
                if finding.turn is not None else "")
        items.append(tag("li", chip(finding.kind, finding.kind)
                         + tag("span", esc(finding.headline), class_="grow")
                         + (tag("span", esc(finding.detail), class_="detail")
                            if finding.detail else "") + link))
    causes = [row for row in insights.cost_cause(records) if row["cause"]]
    why = ""
    if causes:
        lines = [tag("li", chip("why", "cost")
                     + tag("span", f"turn {row['turn']} cost {row['cause']}",
                           class_="grow")
                     + tag("a", f"turn {row['turn']} →",
                           href=f"/s/{session_id}/turn/{row['turn']}"))
                 for row in causes]
        why = (tag("div", "WHY IT COST THAT", class_="eyebrow")
               + tag("ol", "".join(lines), class_="findings")
               + tag("p", "A turn with no such cause says nothing. A plausible "
                          "explanation for ordinary variation stops a reader looking "
                          "for the real one.", class_="hint"))
    return tag("section", tag("div", "WHAT STANDS OUT", class_="eyebrow")
               + tag("ol", "".join(items), class_="findings") + why, class_="card")


def _strip(records: list[Record], session_id: str) -> str:
    rows = insights.turn_activity(records)
    if not rows:
        return ""
    widest = max((r["calls"] or 1) for r in rows)
    blocks = []
    for row in rows:
        classes = "tripped" if (row["tripped"] or row["retries"]) else ""
        if row["failures"]:
            classes = "failed"
        share = (row["calls"] or 1) / widest
        blocks.append(tag(
            "a", esc(str(row["position"])),
            href=f"/s/{session_id}/turn/{row['position']}",
            class_=classes or None,
            style=f"flex:{max(1, int(share * 20))} 1 0",
            title=f"turn {row['position']}: {row['calls']} calls, "
                  f"{row['reason'] or 'unfinished'}"
                  + (f", {row['failures']} failed" if row["failures"] else "")
                  + (f", {row['retries']} retried" if row["retries"] else "")
                  + (f", logged as {row['number']}" if row["renumbered"] else "")))
    activity = []
    for row in rows:
        what = (esc(row["activity"]) if row["activity"]
                else tag("span", "no tool calls, the agent replied and stopped",
                         class_="absent"))
        activity.append(tag("div", tag("span", esc(str(row["position"])),
                                       class_="mono")
                            + " " + what, class_="sub"))
    return tag("section",
               tag("div", "TURNS · width by calls · colour by outcome", class_="eyebrow")
               + tag("div", "".join(blocks), class_="strip")
               + tag("div", "".join(activity), style="margin-top:.6rem"),
               class_="card")


def _card(label: str, body: str, quiet: bool = False) -> str:
    """One panel. ``quiet`` collapses it, for a card whose figures are all absent.

    Four rows reading `total ·`, `median call ·`, `slowest ·` took a quarter of the page
    to say nothing. A card with nothing to report says it in one line and gives the space
    back to the cards that do.
    """
    return tag("section", tag("div", esc(label), class_="eyebrow") + body,
               class_="card quiet" if quiet else "card")


def _configuration(records: list[Record]) -> str:
    """The run's own settings, which is what a reader chases when a turn dies.

    A turn stopping on `max_tokens` sends a reader looking for the ceiling it hit, and
    these were in the log and reachable only as raw JSON. Absent ones say so, because a
    session logged before a ceiling existed did not have that ceiling set to nothing.
    """
    start = next((r for r in records if r.phase == "session_start"), None)
    if start is None:
        return _card("CONFIGURATION",
                     tag("span", "This log has no session_start record, so the run's "
                                 "settings were never written.", class_="empty"),
                     quiet=True)
    rows = [
        tag("dt", "provider") + tag("dd", esc(start.get("provider"))),
        tag("dt", "model") + tag("dd", esc(start.get("model"))),
        tag("dt", "step ceiling")
        + tag("dd", _ceiling(start.get("max_iterations"), "iterations")),
        tag("dt", "work ceiling")
        + tag("dd", _ceiling(start.get("max_turn_tokens"), "tokens a turn")),
        tag("dt", "cost ceiling")
        + tag("dd", _cost_ceiling(start.get("max_turn_cost"))),
        tag("dt", "output cap")
        + tag("dd", _ceiling(start.get("max_output_tokens"), "tokens a reply")),
        tag("dt", "caching") + tag("dd", _caching(start)),
    ]
    return _card("CONFIGURATION", tag("dl", "".join(rows), class_="kv"))


def _ceiling(value: Any, unit: str) -> str:
    """A ceiling, or the two different ways it can be absent.

    Zero means DISABLED, which the agent treats as a deliberate choice, and a missing key
    means the log predates the setting. Rendering both as a dash would merge two
    different facts.
    """
    if value is None:
        return tag("span", "not recorded", class_="absent")
    if not int(value):
        return tag("span", "disabled", class_="absent")
    return f"{int(value):,} {unit}"


def _cost_ceiling(value: Any) -> str:
    if value is None:
        return tag("span", "not recorded", class_="absent")
    if not float(value):
        return tag("span", "disabled", class_="absent")
    return money(float(value), places=4)


def _caching(start: Record) -> str:
    """Whether caching was available, and the minimum below which it silently does not.

    The minimum is the answer to "why did this session cache nothing", which is otherwise
    unanswerable from the page.
    """
    if start.get("caches") is None:
        return tag("span", "not recorded", class_="absent")
    if not start.get("caches"):
        return "not supported by this provider"
    minimum = start.get("cache_min_tokens")
    if not minimum:
        return "on"
    return f"on above {int(minimum):,} tokens"


def _measures(records: list[Record]) -> str:
    figures = totals(records)
    window = insights.window_pressure(records)
    spend = insights.attribution(records)
    share = insights.repetition(records)
    saving = insights.cache_saving(records)
    durations = insights.call_durations(records)

    if durations.values:
        time_card = _card("TIME", tag("dl", "".join([
            tag("dt", "total") + tag("dd", duration(sum(durations.values))),
            tag("dt", "median call") + tag("dd", duration(durations.middle)),
            tag("dt", "slowest") + tag("dd", duration(durations.largest)),
            tag("dt", "calls") + tag("dd", str(figures["calls"])),
        ]), class_="kv"))
    else:
        time_card = _card("TIME", tag(
            "span", f"{figures['calls']} calls, none of which recorded a duration",
            class_="empty"), quiet=True)

    window_card = _card("WINDOW", tag("dl", "".join([
        tag("dt", "peak prompt") + tag("dd", tokens(window["peak_prompt"] or None)),
        tag("dt", "of window") + tag("dd", bar(window["peak_fraction"],
                                               percent(window["peak_fraction"], 1))),
        tag("dt", "compactions") + tag("dd", str(window["compactions"])),
        tag("dt", "still over") + tag("dd", str(window["still_over_budget"])),
    ]), class_="kv"))

    unit = next((r.get("usage_unit") for r in records
                 if r.phase == "response" and r.get("usage_unit")), None)
    spend_rows = [
        tag("dt", "session") + tag("dd", money(spend["total"])),
        tag("dt", "counted in") + tag("dd", esc(unit) if unit
                                      else tag("span", "not recorded",
                                               class_="absent")),
        tag("dt", "from") + tag("dd", esc(spend["total_from"] or ABSENT)),
        tag("dt", "largest turn") + tag("dd", (
            f"{spend['largest_turn']} at {money(spend['largest_turn_cost'])}"
            if spend["largest_turn"] else ABSENT)),
        tag("dt", "amplification") + tag("dd", (
            f"x{spend['amplification']}" if spend["amplification_available"]
            else f'<span class="absent">{ABSENT} not recorded</span>')),
        tag("dt", "genuinely new") + tag("dd", (
            tokens(spend["unique_tokens"]) if spend["unique_tokens"]
            else f'<span class="absent">{ABSENT} not recorded</span>')),
    ]
    if spend["unpriced_turns"]:
        spend_rows.append(tag("dt", "unpriced turns")
                          + tag("dd", str(spend["unpriced_turns"])))
    spend_card = _card("SPEND", tag("dl", "".join(spend_rows), class_="kv"))

    if share.get("available"):
        cache_rows = [
            tag("dt", "served from cache")
            + tag("dd", bar(share["cached_share"], percent(share["cached_share"]))),
            tag("dt", "fresh input") + tag("dd", tokens(share["fresh_input"])),
            tag("dt", "cache reads") + tag("dd", tokens(share["cache_read"])),
        ]
        if saving.get("available"):
            cache_rows.append(tag("dt", "caching saved")
                              + tag("dd", money(saving["saved"], 6)))
            cache_rows.append(tag("dt", "same tokens uncached")
                              + tag("dd", money(saving["as_if_uncached"], 6)))
        else:
            cache_rows.append(tag("dt", "saving")
                              + tag("dd", tag("span", esc(saving["why"]),
                                              class_="absent")))
        cache_card = _card("REPETITION", tag("dl", "".join(cache_rows),
                                           class_="kv"))
    else:
        cache_card = _card("REPETITION",
                           tag("span", esc(share["why"]), class_="empty"), quiet=True)

    # The world files identify rooms where titles cannot, so the progress measure uses
    # them when they are there and says which basis it used. Two rooms sharing a name is
    # common enough here that the difference is not academic.
    rooms = world.load()
    identified = None
    if rooms:
        steps = world.trail(_movements(records), rooms)
        identified = len({s.vnum for s in steps if s.vnum is not None and not s.blocked})
    progress = insights.rooms_seen(records, resolved=identified)
    if progress.get("available"):
        progress_card = _card("PROGRESS", tag("dl", "".join([
            tag("dt", f"distinct {progress['basis']}")
            + tag("dd", str(progress["headings"])),
            tag("dt", "visits") + tag("dd", str(progress["visits"])),
            tag("dt", "tokens each") + tag("dd", tokens(progress["tokens_each"])),
            tag("dt", "cost each") + tag("dd", money(progress["cost_each"], 4)),
        ]), class_="kv")
                              + tag("p", esc(
                                  "Rooms identified by the world's own files, because "
                                  "two rooms can share a name."
                                  if progress["basis"] == "rooms" else
                                  "Headings, not rooms: the world files are not "
                                  "available here, and two rooms can share a name.")
                                  , class_="hint"))
    else:
        progress_card = _card("PROGRESS",
                              tag("span", esc(progress["why"]), class_="empty"),
                              quiet=True)
    return tag("div", _configuration(records) + time_card + window_card + spend_card
               + cache_card + progress_card, class_="cols")


def _lens_nav(session_id: str, current: str) -> str:
    links = []
    for key, label, hint in LENSES:
        links.append(tag("a", esc(label), href=f"/s/{session_id}/{key}", title=hint,
                         aria_current="page" if key == current else None))
    return tag("nav", "".join(links), class_="lenses")


def session_page(records: list[Record], summary: SessionSummary,
                 lens: str = "narrative", page_number: int = 1) -> str:
    """One session, with the seven lenses over it.

    The instruction that started the run is the title, because that is how a person
    recognises which run this was. The findings lead, because that is what the reader
    came for.
    """
    lens = lens if lens in LENS_NAMES else "narrative"
    figures = totals(records)
    start = next((r for r in records if r.phase == "session_start"), None)
    first_user = _first_instruction(records)
    # The instruction is the title. A person recognises a run by what they asked for,
    # not by its task category or its id, and both of those are still on the page.
    title = _one_line(first_user, 90) if first_user else (
        (start.get("task") if start else None) or summary.id)

    header = tag("div", " · ".join(filter(None, [
        esc((start.get("task") if start else None) or ""),
        esc(summary.model), f"{figures['turns']} turns",
        f"{figures['calls']} calls", summary.render_cost(),
        esc(summary.outcome),
    ])), class_="sub")

    body = [header]
    body.append(_findings_block(records, summary.id))
    body.append(_measures(records))
    body.append(_strip(records, summary.id))
    body.append(_lens_nav(summary.id, lens))
    body.append(_lens_body(records, summary, lens, page_number))
    return page(title, "".join(body),
                crumb=f"log viewer · {summary.id}",
                tools=tag("a", "← sessions", href="/", class_="crumb"))


def _one_line(text: str, width: int) -> str:
    """A title's worth of a possibly long instruction, escaped."""
    return preview(text, width)


def _first_instruction(records: list[Record]) -> str | None:
    for record in records:
        if record.phase == "turn":
            instruction = record.get("instruction")
            if isinstance(instruction, str) and instruction.strip():
                return instruction
    for record in records:
        if record.phase != "prompt":
            continue
        for message in record.get("messages") or []:
            if isinstance(message, dict) and message.get("role") == "user":
                content = message.get("content")
                if isinstance(content, str):
                    return content
                if isinstance(content, list) and content:
                    first = content[0]
                    if isinstance(first, dict):
                        return str(first.get("text") or "")
                    return str(first)
    return None


# -- the lenses -------------------------------------------------------------

def _lens_body(records: list[Record], summary: SessionSummary, lens: str,
               page_number: int = 1) -> str:
    if lens == "map":
        return _lens_map(records)
    if lens == "player":
        return _lens_player(records)
    if lens == "pressure":
        return _lens_pressure(records)
    if lens == "timeline":
        return _lens_timeline(records)
    if lens == "context":
        return _lens_context(records)
    if lens == "tools":
        return _lens_tools(records)
    if lens == "journey":
        return _lens_journey(records)
    if lens == "errors":
        return _lens_errors(records)
    if lens == "raw":
        return _lens_raw(records, summary.id, page_number)
    return _lens_narrative(records, summary)


def _lens_narrative(records: list[Record], summary: SessionSummary) -> str:
    """The conversation as it ran, turn by turn, each turn a link to its own page."""
    rows = insights.turn_activity(records)
    if not rows:
        return tag("section", tag("p", "This session recorded no turns.",
                                  class_="empty"), class_="card")
    blocks = []
    for row in rows:
        marks = []
        if row["tripped"]:
            marks.append(chip(row["reason"], "ceiling"))
        if row["failures"]:
            marks.append(chip(f"{row['failures']} failed", "failure"))
        if row["retries"]:
            marks.append(chip(f"{row['retries']} retried", "retry"))
        if row["renumbered"]:
            marks.append(chip(f"logged as {row['number']}", "context"))
        blocks.append(tag("section", tag("div", tag(
            "a", f"turn {row['position']}",
            href=f"/s/{summary.id}/turn/{row['position']}") + " " + " ".join(marks),
            class_="row", id=f"turn-{row['position']}")
            + tag("div", " · ".join([
                f"{row['calls']} calls", f"{row['iterations']} iterations",
                duration(row["duration_ms"]), money(row["cost"]),
                tokens(row["tokens"] or None) + " volume",
            ]), class_="sub mono")
            + (tag("p", esc(row["activity"])) if row["activity"] else ""),
            class_="card",
            data_search=f"turn {row['position']} {row['activity']}"))
    return tag("div", _search_box("search turns") + tag(
        "div", "".join(blocks), class_="stack"), class_="stack")


def _lens_player(records: list[Record]) -> str:
    """The four words of the brief, computed rather than left to the reader.

    This is the lens the project exists for. Everything else here reports what the RUN
    did, and this reports what the PLAYER experienced, which is the finding a Player
    Journey Agent is supposed to produce.

    Each carries the evidence that triggered it, so a reader can disagree with a
    threshold rather than having to trust a label.
    """
    found = insights.journey_findings(records)
    words = {
        "confused": "went in circles, which is a player who has lost the thread",
        "blocked": "kept trying something the world refuses",
        "bored": "repeated the same action, which is motion without progress",
        "stuck": "burned a turn without getting anywhere",
        "overpowered": "was out of its depth, and the world said so outright",
        "drained": "ran a resource to nothing and stopped being able to play",
    }
    if found:
        items = []
        for finding in found:
            items.append(tag("li", chip(finding.word, finding.word)
                             + tag("span", tag("strong", esc(finding.headline)) + " "
                                   + tag("span", esc(words.get(finding.word, "")),
                                         class_="detail"), class_="grow")
                             + (tag("span", esc(finding.evidence), class_="detail")
                                if finding.evidence else "")))
        body = tag("ol", "".join(items), class_="findings")
    else:
        body = tag("p", esc(insights.why_no_journey(records)), class_="empty")
    return tag("div", tag("section",
                          tag("div", "THE PLAYER'S EXPERIENCE", class_="eyebrow")
                          + body,
                          class_="card lead" if found else "card")
               + tag("section", tag("div", "HOW EACH IS DECIDED", class_="eyebrow")
                     + tag("dl", "".join([
                         tag("dt", "confused")
                         + tag("dd", f"a room entered {insights.CIRCLING} or more "
                                     f"times"),
                         tag("dt", "blocked")
                         + tag("dd", "the same action refused twice or more"),
                         tag("dt", "bored")
                         + tag("dd", f"{insights.GRINDING} identical successful "
                                     f"actions in a row"),
                         tag("dt", "stuck")
                         + tag("dd", f"a turn of {insights.STUCK} or more actions "
                                     f"reaching at most one new room"),
                         tag("dt", "overpowered")
                         + tag("dd", "the world naming a zone above the agent's level"),
                         tag("dt", "drained")
                         + tag("dd", "the game reporting exhaustion, hunger, thirst "
                                     "or death"),
                     ]), class_="kv")
                     + tag("p", "Thresholds, not judgements. Every finding names the "
                                "count behind it so the number can be argued with.",
                           class_="hint"), class_="card"), class_="stack")


def _lens_pressure(records: list[Record]) -> str:
    """Prompt size per call against the window, with compactions as cuts.

    The one view that shows a compaction WORKING. Both compaction records in this
    project's corpus sat inside turns no page could reach until recently, so a thing that
    has been happening all along has never been drawn.
    """
    series = insights.pressure_series(records)
    if not series.get("available"):
        return tag("section", tag("div", "WINDOW PRESSURE", class_="eyebrow")
                   + tag("p", esc(series["why"]), class_="empty"), class_="card")

    points = series["points"]
    width, height, pad = 1000, 300, 40
    window = series["window"]
    peak = series["peak"] or 1

    # SCALE TO THE DATA, not to the limit. Forcing the axis to a 200,000 window when
    # the peak is 7,600 draws a flat line on the floor and a dashed rule near the top,
    # which says the window is large and nothing about the session. The window is drawn
    # only when the data comes near enough to it to be worth comparing, and stated as a
    # figure when it does not.
    near = bool(window) and peak >= window * 0.4
    top = (window if near else peak * 1.25) or 1
    inner_w, inner_h = width - pad * 2, height - pad * 2 - 14

    def px(index: int) -> float:
        return pad + (index / max(len(points) - 1, 1)) * inner_w

    def py(value: float) -> float:
        return pad + inner_h - (min(value, top) / top) * inner_h

    line = " ".join(f"{px(i):.1f},{py(p['prompt']):.1f}"
                    for i, p in enumerate(points))
    area = (f"{pad},{pad + inner_h} " + line
            + f" {px(len(points) - 1):.1f},{pad + inner_h}")
    marks = [tag("polygon", "", class_="area", points=area),
             tag("polyline", "", class_="line", points=line)]
    if near:
        marks.append(tag("line", "", class_="limit", x1=pad, x2=width - pad,
                         y1=f"{py(window):.1f}", y2=f"{py(window):.1f}"))
        marks.append(tag("text", esc(f"window {tokens(window)}"),
                         x=pad + 4, y=f"{py(window) - 7:.1f}"))
        if series["threshold"]:
            marks.append(tag("line", "", class_="thresh", x1=pad, x2=width - pad,
                             y1=f"{py(series['threshold']):.1f}",
                             y2=f"{py(series['threshold']):.1f}"))
            marks.append(tag("text", esc(f"compacts at {tokens(series['threshold'])}"),
                             x=pad + 4, y=f"{py(series['threshold']) - 7:.1f}"))

    # Compaction cuts, staggered so two close together do not print over each other.
    for order, cut in enumerate(series["cuts"]):
        index = min(max(cut["at"] - 1, 0), len(points) - 1)
        x = px(index)
        marks.append(tag("line", "", class_="cut", x1=f"{x:.1f}", x2=f"{x:.1f}",
                         y1=pad, y2=pad + inner_h))
        label = ("compact, asked for" if cut.get("trigger") == "manual"
                 else "compact")
        # A label near the right edge is drawn leftwards, or the SVG clips it. A cut at
        # the end of a session is the common case, so this is the common case.
        flip = x > width - pad - len(label) * 8
        marks.append(tag("text", esc(label), class_="cutlabel",
                         x=f"{x + (-5 if flip else 5):.1f}",
                         y=pad + 13 + (order % 3) * 16,
                         text_anchor="end" if flip else "start"))

    marks.append(tag("line", "", class_="axis", x1=pad, x2=width - pad,
                     y1=pad + inner_h, y2=pad + inner_h))
    marks.append(tag("text", esc(f"peak {tokens(peak)}"), class_="peak",
                     x=pad, y=f"{max(py(peak) - 8, 14):.1f}"))
    marks.append(tag("text", esc(f"{len(points)} calls, first to last"),
                     x=pad, y=pad + inner_h + 20))
    if not near and window:
        share = peak / window
        marks.append(tag("text", esc(f"the window is {tokens(window)}, so the peak is "
                                     f"{percent(share, 1)} of it and is not drawn "
                                     f"to scale against it"),
                         x=width - pad, y=pad + inner_h + 20, text_anchor="end"))

    note = []
    if series["cuts"]:
        for cut in series["cuts"]:
            did = []
            if cut["dropped"]:
                did.append(f"dropped {cut['dropped']} messages")
            if cut["compressed"]:
                did.append(f"compressed {cut['compressed']} tool results")
            asked = cut.get("trigger") == "manual"
            if not cut["before"]:
                what = "there was nothing left to compact"
            else:
                what = (f"from {cut['before']:,} tokens, "
                        + (" and ".join(did) or "changed nothing"))
            note.append(tag("li", chip("compaction", "compaction")
                            + (chip("asked for", "context") if asked else "")
                            + tag("span", esc(f"turn {cut['turn']}, {what}"
                                              + (", still over budget"
                                                 if cut["over_budget"] else "")),
                                  class_="grow")))
    else:
        note.append(tag("li", tag("span", "No compaction happened in this session, so "
                                          "the line is the context growing "
                                          "unchecked.", class_="empty")))
    manual = [c for c in series["cuts"] if c.get("trigger") == "manual"]
    lead = ""
    if manual:
        lead = tag("p", esc(
            f"{len(manual)} of these compactions were ASKED FOR with /compact rather "
            f"than triggered by pressure, which is why one fired far below the "
            f"threshold. The record says which, so a compaction at four percent of the "
            f"window is not mistaken for a broken threshold."), class_="sub")
    elif series["cuts"] and not near:
        lead = tag("p", esc(
            "These compactions fired well below the threshold. The log does not record "
            "why, which means it predates the field that says whether a compaction was "
            "asked for."), class_="sub")
    return tag("section", tag("div", "WINDOW PRESSURE", class_="eyebrow") + lead
               + tag("svg", "".join(marks), class_="pressure",
                     viewBox=f"0 0 {width} {height}", role="img",
                     aria_label="prompt size per call against the context window")
               + tag("ol", "".join(note), class_="findings"), class_="card")


def _lens_map(records: list[Record]) -> str:
    """The path drawn on the world, with rooms identified by their exits.

    The one lens a generic log viewer could not have. It needs the world's own files,
    because ROOM TITLES DO NOT IDENTIFY ROOMS: this world has 241 titles shared by more
    than one room and one shared by forty-one. A trail built from titles folds distinct
    places together and draws movements that never happened.

    Those files are DATA, read the way the log is read, so nothing is imported and the
    boundary holds.
    """
    rooms = world.load()
    if not rooms:
        return tag("section", tag("div", "THE MAP", class_="eyebrow")
                   + tag("p", "The world files are not available here, so a path "
                              "cannot be drawn: room titles alone cannot identify "
                              "rooms. Set BOUKENSHA_WORLD to a directory of .wld "
                              "files.", class_="empty"), class_="card")
    moves = _movements(records)
    if not moves:
        return tag("section", tag("div", "THE MAP", class_="eyebrow")
                   + tag("p", "This session made no movements, so there is no path.",
                         class_="empty"), class_="card")
    steps = world.trail(moves, rooms)
    grid = world.layout(steps, rooms)
    if not grid:
        return tag("section", tag("div", "THE MAP", class_="eyebrow")
                   + tag("p", "No movement resolved to a room in this world, so the "
                              "session was probably played somewhere else.",
                         class_="empty"), class_="card")

    visits: dict[int, int] = {}
    blocked_at: dict[int, int] = {}
    for step in steps:
        if step.vnum is None:
            continue
        if step.blocked:
            blocked_at[step.vnum] = blocked_at.get(step.vnum, 0) + 1
        else:
            visits[step.vnum] = visits.get(step.vnum, 0) + 1

    cell, box = 150, 112
    xs = [p[0] for p in grid.values()]
    ys = [p[1] for p in grid.values()]
    ox, oy = min(xs), min(ys)
    width = (max(xs) - ox + 1) * cell + 40
    height = (max(ys) - oy + 1) * cell + 40

    def centre(vnum: int) -> tuple[float, float]:
        gx, gy = grid[vnum]
        return (20 + (gx - ox) * cell + box / 2, 20 + (gy - oy) * cell + box / 2)

    marks = []
    # The exits between rooms the agent saw, so the shape of the place shows even
    # where the agent did not walk that edge.
    drawn = set()
    for vnum in grid:
        for target in rooms[vnum].exits.values() if vnum in rooms else ():
            if target not in grid or (target, vnum) in drawn:
                continue
            drawn.add((vnum, target))
            x1, y1 = centre(vnum)
            x2, y2 = centre(target)
            marks.append(tag("line", "", class_="link", x1=f"{x1:.0f}",
                             y1=f"{y1:.0f}", x2=f"{x2:.0f}", y2=f"{y2:.0f}"))
    # The path actually walked, in order.
    walked = [s.vnum for s in steps if s.vnum is not None and not s.blocked]
    if len(walked) > 1:
        marks.append(tag("polyline", "", class_="path", points=" ".join(
            f"{centre(v)[0]:.0f},{centre(v)[1]:.0f}" for v in walked
            if v in grid)))
        # Where it began and where it ended, because a route without its ends is a
        # shape rather than a journey.
        for vnum, kind in ((walked[0], "from"), (walked[-1], "to")):
            if vnum not in grid:
                continue
            cx, cy = centre(vnum)
            marks.append(tag("circle", "", class_=f"mark {kind}", cx=f"{cx:.0f}",
                             cy=f"{cy:.0f}", r=7))

    busiest = max(visits.values()) if visits else 1
    for vnum, (gx, gy) in grid.items():
        x = 20 + (gx - ox) * cell
        y = 20 + (gy - oy) * cell
        count = visits.get(vnum, 0)
        # Fill by how often the agent was here, which is where its time went.
        weight = 0.12 + 0.6 * (count / busiest if busiest else 0)
        classes = "room"
        if walked and vnum == walked[0]:
            classes += " start"
        if vnum in blocked_at:
            classes += " blocked"
        title = strip_ansi(rooms[vnum].title if vnum in rooms else str(vnum))
        marks.append(tag("rect", "", class_=classes, x=x, y=y, width=box, height=box,
                         rx=3, fill=f"color-mix(in oklab, var(--brass) "
                                    f"{weight * 100:.0f}%, var(--raised))"))
        marks.append(tag("text", esc(str(vnum)), class_="n", x=x + 8, y=y + 19))
        # Four lines of thirteen characters fit the box. A fifth is dropped with an
        # ellipsis rather than drawn over the room next door.
        parts = _wrap(title, 14)
        for line, part in enumerate(parts[:4]):
            last = line == 3 and len(parts) > 4
            marks.append(tag("text", esc(part + ("…" if last else "")),
                             x=x + 8, y=y + 37 + line * 15))
        if count > 1:
            marks.append(tag("text", esc(f"x{count}"), class_="n",
                             x=x + box - 30, y=y + box - 9))

    ambiguous = sum(1 for s in steps if s.disambiguated)
    legend = tag("div", " ".join([
        tag("span", tag("span", "", class_="swatch",
                        style="background:color-mix(in oklab, var(--brass) 12%, "
                              "var(--raised))") + " visited once"),
        tag("span", tag("span", "", class_="swatch",
                        style="background:color-mix(in oklab, var(--brass) 72%, "
                              "var(--raised))") + " visited most"),
        tag("span", tag("span", "", class_="swatch",
                        style="border-color:var(--good);border-width:3px") + " start"),
        tag("span", tag("span", "", class_="swatch",
                        style="border-color:var(--bad);border-width:3px")
            + " a move was refused here"),
    ]), class_="legend")

    return tag("section", tag("div", "THE MAP", class_="eyebrow")
               + tag("p", esc(f"{len(grid)} rooms across {len(steps)} movements. "
                              f"{ambiguous} of them had a title shared by more than one "
                              f"room and were resolved by the exit taken, which is why "
                              f"this reads the world's own files rather than trusting "
                              f"the titles."), class_="sub")
               + legend
               + tag("div", tag("svg", "".join(marks), class_="map",
                                viewBox=f"0 0 {width} {height}",
                                width=width, height=height, role="img",
                                aria_label="the rooms visited and the path between them"),
                     class_="mapwrap"), class_="card")


def _wrap(text: str, width: int) -> list[str]:
    """Break a room title into short lines, for a label inside a box."""
    out, line = [], ""
    for word in text.split():
        if len(line) + len(word) + 1 > width:
            if line:
                out.append(line)
            line = word[:width]
        else:
            line = f"{line} {word}".strip()
    if line:
        out.append(line)
    return out


def _movements(records: list[Record]) -> list[tuple[int, str | None, str, bool]]:
    """Every move or look, as (turn, direction, what the game said, whether it worked).

    A refusal is kept rather than dropped. A wall the agent walked into repeatedly is
    the most informative thing on the map.
    """
    turn = 0
    results = {str(r.get("tool_use_id") or r.get("name")): r
               for r in records if r.phase == "tool_result"}
    out = []
    for record in records:
        if record.phase == "turn":
            turn = int(record.get("n") or turn)
        if record.phase != "tool_call":
            continue
        name = str(record.get("name") or "")
        if "move" not in name and "look" not in name:
            continue
        result = results.get(str(record.get("id") or record.get("name")))
        text = strip_ansi(str(result.get("result") or "")) if result else ""
        first = next((line.strip() for line in text.splitlines() if line.strip()), "")
        args = record.get("args") or {}
        direction = args.get("direction") if isinstance(args, dict) else None
        lowered = text.lower()
        ok = bool(result and result.get("ok", True)
                  and "cannot go" not in lowered
                  and "too relaxed" not in lowered
                  and "too exhausted" not in lowered
                  and "alas, you cannot" not in lowered)
        out.append((turn, direction, first, ok))
    return out


def _lens_timeline(records: list[Record]) -> str:
    """A time axis, one row per call, width by duration and colour by outcome."""
    durations = insights.call_durations(records)
    if not durations.values:
        return tag("section", tag(
            "p", "No call in this session recorded a duration, so there is no "
                 "timeline to draw.", class_="empty"), class_="card")
    longest = durations.largest or 1.0
    turn = None
    rows = []
    index = 0
    for record in records:
        if record.phase == "turn":
            turn = record.get("n")
        if record.phase != "response":
            continue
        index += 1
        ms = record.get("duration_ms")
        if ms is None:
            rows.append(tag("div", tag("span", f"{index}", class_="mono")
                            + tag("span", "untimed", class_="absent"), class_="t"))
            continue
        classes = "t slow" if durations.is_outlier(float(ms)) else "t"
        width = max(0.5, float(ms) / longest * 100)
        rows.append(tag("div",
                        tag("span", f"t{turn}·{index}", class_="mono")
                        + tag("span", tag("span", "", style=f"width:{width:.1f}%"),
                              class_="track")
                        + tag("span", duration(ms), class_="mono"),
                        class_=classes,
                        data_search=f"turn {turn} call {index}"))
    note = (f"median {duration(durations.middle)}, slowest "
            f"{duration(durations.largest)}"
            + (f", {len([v for v in durations.values if durations.is_outlier(v)])} "
               f"above twice the median" if durations.enough else
               ", too few calls for a median"))
    return tag("section", tag("div", "TIMELINE", class_="eyebrow")
               + tag("div", esc(note), class_="sub")
               + tag("div", "".join(rows), class_="timeline"), class_="card")


def _lens_context(records: list[Record]) -> str:
    """What each prompt ADDED, which is the most explanatory view here.

    The payload is logged, so the diff between consecutive prompts is a fact rather
    than an inference. The system prompt and the tool schemas appear once at the
    session level rather than on every iteration, which is what makes the rest legible.
    """
    prompts = [r for r in records if r.phase == "prompt"]
    requests = [r for r in records if r.phase == "model_request"]
    if not prompts:
        return tag("section", tag("p", "No prompt payload was recorded.",
                                  class_="empty"), class_="card")
    start = next((r for r in records if r.phase == "session_start"), None)
    once = []
    if start and start.get("system"):
        once.append(tag("details", tag("summary", "system prompt, sent on every call")
                        + tag("pre", esc(start.get("system"))), class_="leg"))
    if prompts[0].get("tools"):
        names = ", ".join(str(t) for t in prompts[0].get("tools"))
        once.append(tag("details", tag(
            "summary", f"{prompts[0].get('tool_count')} tool schemas, sent on every call")
            + tag("pre", esc(names)), class_="leg"))
    for index, record in enumerate(requests, start=1):
        once.append(tag(
            "details",
            tag("summary", f"exact model request {index}")
            + tag("pre", esc(json.dumps(
                record.get("request"),
                indent=2,
                ensure_ascii=False,
            ))),
            class_="leg",
        ))

    steps = []
    previous: list[Any] = []
    for index, record in enumerate(prompts, start=1):
        messages = record.get("messages") or []
        added = messages[len(previous):] if len(messages) >= len(previous) else []
        removed = len(previous) - len(messages) if len(previous) > len(messages) else 0
        lines = []
        for message in added:
            lines.append(tag("div", tag("span", "+", class_="diffadd") + " "
                             + tag("span", esc(_role_of(message)), class_="mono")
                             + " " + preview(_text_of(message), 110)))
        if removed:
            lines.append(tag("div", tag("span", f"- {removed} messages dropped",
                                        class_="diffdel")))
        if not lines:
            lines.append(tag("div", "no change in the message list", class_="absent"))
        # The writer's own count beside the payload's length. They should agree, and a
        # reader deserves to see it rather than trust it.
        counted = record.get("message_count")
        disagrees = counted is not None and int(counted) != len(messages)
        steps.append(tag("details", tag("summary", " ".join([
            tag("span", f"iteration {index}", class_="mono"),
            tag("span", f"{len(previous)} → {len(messages)} messages", class_="sub"),
            chip(f"writer counted {counted}", "error") if disagrees else "",
            chip(f"+{len(added)}") if added else "",
            chip(f"-{removed}", "error") if removed else "",
        ])) + tag("div", "".join(lines), class_="legbody"),
            class_="leg" + (" marked" if removed else ""),
            open=index == 1,
            data_search=f"iteration {index}"))
        previous = messages

    note = tag("p", "Additions are what the previous call did not carry. A shrinking "
                    "list is a compaction, and the compaction record says what it "
                    "dropped.", class_="sub")
    return tag("div", tag("section", tag("div", "SENT ONCE, SHOWN ONCE", class_="eyebrow")
                          + "".join(once), class_="card")
               + tag("section", tag("div", "WHAT EACH PROMPT ADDED", class_="eyebrow")
                     + note + _search_box("search iterations", controls=True)
                     + "".join(steps), class_="card"), class_="stack")


def _role_of(message: Any) -> str:
    if not isinstance(message, dict):
        return "?"
    role = str(message.get("role") or "?")
    content = message.get("content")
    kinds = []
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type"):
                kinds.append(str(block["type"]))
    return f"{role}/{'+'.join(dict.fromkeys(kinds))}" if kinds else role


def _text_of(message: Any) -> str:
    if isinstance(message, str):
        return message
    if not isinstance(message, dict):
        return str(message)
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(str(block.get("text") or block.get("content")
                                 or block.get("input") or ""))
            else:
                parts.append(str(block))
        return " ".join(p for p in parts if p)
    return ""


def _lens_tools(records: list[Record]) -> str:
    """Grouped by tool rather than by time, which is what time-ordering hides."""
    pairs = pair_tools(records)
    if not pairs:
        return tag("section", tag("p", "No tool call was recorded.",
                                  class_="empty"), class_="card")
    groups: dict[str, dict[str, Any]] = {}
    for call, result in pairs:
        name = str(call.get("name") or "?")
        group = groups.setdefault(name, {"calls": 0, "failed": 0, "unpaired": 0,
                                         "samples": []})
        group["calls"] += 1
        if result is None:
            group["unpaired"] += 1
        elif not result.get("ok", True):
            group["failed"] += 1
        if len(group["samples"]) < 6:
            group["samples"].append((call, result))

    rows = []
    for name, group in sorted(groups.items(), key=lambda kv: -kv[1]["calls"]):
        rate = group["failed"] / group["calls"]
        detail = []
        for call, result in group["samples"]:
            outcome = ("no result recorded" if result is None else
                       ("ok" if result.get("ok", True) else
                        f"FAILED {result.get('error') or ''}"))
            detail.append(tag("div", tag("span", esc(json.dumps(call.get("args") or {})),
                                         class_="mono")
                              + " → " + esc(outcome), class_="sub"))
        rows.append(tag("details", tag("summary", " ".join([
            tag("span", esc(name), class_="mono"),
            chip(f"{group['calls']} calls"),
            chip(f"{group['failed']} failed", "failure") if group["failed"] else "",
            chip(f"{group['unpaired']} unpaired", "retry") if group["unpaired"] else "",
            tag("span", bar(rate, percent(rate), "bad" if rate else ""), class_="sub"),
        ])) + tag("div", "".join(detail), class_="legbody"),
            class_="leg" + (" broken" if group["failed"] else ""),
            data_search=name))
    return tag("section", tag("div", "TOOLS", class_="eyebrow")
               + tag("p", f"{len(groups)} distinct tools across {len(pairs)} calls. "
                          "A tool called once has no spread, and says so by showing "
                          "one sample.", class_="sub")
               + _search_box("search tools", controls=True) + "".join(rows), class_="card")


def _lens_journey(records: list[Record]) -> str:
    """The game read out of the log, from the MUD output alone.

    Deliberately NOT the agent's journey parser. Importing it would put this program
    inside the one it reads, and the plan settles that as a decision to make when the
    parser is shared rather than a licence taken now. What is here comes from the tool
    results themselves: where the agent went and what the world said back.
    """
    moves = []
    for call, result in pair_tools(records):
        name = str(call.get("name") or "")
        if "move" not in name and "look" not in name:
            continue
        args = call.get("args") or {}
        where = args.get("direction") if isinstance(args, dict) else None
        text = strip_ansi(str(result.get("result") or "")) if result else ""
        first = next((line.strip() for line in text.splitlines() if line.strip()), "")
        ok = result.get("ok", True) if result else False
        moves.append((name.split("__")[-1], where, first, ok))
    if not moves:
        return tag("section", tag(
            "p", "This session's tools are not MUD tools, so there is no journey to "
                 "read. That is an empty view rather than an error.",
            class_="empty"), class_="card")
    rows = []
    for index, (what, where, first, ok) in enumerate(moves, start=1):
        rows.append((
            _cell(str(index), num=True),
            _cell(esc(what) + (f" {esc(where)}" if where else "")),
            _cell(esc(first) if ok else tag("span", esc(first or "blocked"),
                                            class_="diffdel"),
                  search=f"{what} {where} {first}"),
        ))
    blocked = sum(1 for *_rest, ok in moves if not ok)
    return tag("section", tag("div", "JOURNEY", class_="eyebrow")
               + tag("p", f"{len(moves)} movement and look actions, {blocked} blocked. "
                          "Derived from the tool results, and clearly derived.",
                     class_="sub")
               + _search_box("search the journey")
               + _table((("#", True), ("action", False), ("what the world said", False)),
                        rows), class_="card")


def _lens_errors(records: list[Record]) -> str:
    """Everything that went wrong, in one place, with its context."""
    turn = None
    rows = []
    for record in records:
        if record.phase == "turn":
            turn = record.get("n")
        if not record.trouble:
            continue
        if record.phase == "tool_result":
            what, detail = "tool failed", (f"{record.get('name')}: "
                                           f"{record.get('error') or record.get('result')}")
        elif record.phase == "retry":
            what = "retry"
            detail = (f"attempt {record.get('attempt')}, waited "
                      f"{record.get('wait')}s, "
                      f"{record.get('status') or record.get('error')}")
        elif record.phase == "limit_reached":
            what = "ceiling"
            detail = f"{record.get('kind')} at {record.get('n')}/{record.get('max')}"
        else:
            what, detail = record.phase, json.dumps(record.data)[:200]
        rows.append((
            _cell(esc(str(turn)), num=True),
            _cell(chip(what, "error" if what != "retry" else "retry")),
            _cell(preview(detail, 140), search=f"{turn} {what} {detail}"),
            _cell(esc(record.get("at") or ABSENT)),
        ))
    if not rows:
        return tag("section", tag("div", "ERRORS", class_="eyebrow") + tag(
            "p", "Nothing failed, nothing was retried and no ceiling was reached.",
            class_="empty"), class_="card")
    return tag("section", tag("div", "ERRORS", class_="eyebrow")
               + _search_box("search failures")
               + _table((("turn", True), ("what", False), ("detail", False),
                         ("when", False)), rows), class_="card")


#: Events per page of the raw lens. A real session runs to hundreds of events whose
#: prompt payloads each carry the whole conversation, so rendering every body inline
#: produced a 32MB page: complete, and unusable, which is not a trade this viewer gets
#: to make. Pages are URLs, so nothing is lost and everything stays addressable.
RAW_PAGE = 150

#: Bodies longer than this are shown truncated with the full record one click away, on
#: its own page. "Nothing hidden" means reachable, not all at once.
RAW_INLINE_CHARS = 4000


def _lens_raw(records: list[Record], session_id: str, page_number: int = 1) -> str:
    """The record itself, so any rendering on any other lens can be checked.

    This is what makes the completeness claim credible rather than asserted: a reader
    who doubts a number can drop to the line it came from, by line number, and read the
    bytes.
    """
    total_pages = max(1, (len(records) + RAW_PAGE - 1) // RAW_PAGE)
    page_number = max(1, min(total_pages, page_number))
    start = (page_number - 1) * RAW_PAGE
    window = records[start:start + RAW_PAGE]

    rows = []
    for record in window:
        label = record.phase if record.known else f"{record.phase} (unknown)"
        body = json.dumps(record.data, indent=1, default=str)
        flat = json.dumps(record.data, default=str)
        if len(body) > RAW_INLINE_CHARS:
            shown = (tag("pre", esc(body[:RAW_INLINE_CHARS]) + "\n…")
                     + tag("p", tag("a", f"the whole record, {len(body):,} characters",
                                    href=f"/s/{session_id}/event/{record.line}"),
                           class_="sub"))
        else:
            shown = tag("pre", esc(body))
        rows.append(tag("details", tag("summary", " ".join([
            tag("span", f"{record.line:>4}", class_="mono"),
            chip(label, "error" if record.trouble else None),
            tag("span", preview(flat, 100), class_="sub"),
        ])) + tag("div", shown, class_="legbody"),
            class_="leg" + (" broken" if record.malformed else ""),
            # The search key is a preview rather than the whole body, because a
            # thousand full payloads in attributes is most of what made the page
            # unusable. A full-text hunt belongs in the file, not in a browser.
            data_search=flat[:600]))

    nav = []
    if page_number > 1:
        nav.append(tag("a", "← earlier",
                       href=f"/s/{session_id}/raw?page={page_number - 1}"))
    nav.append(tag("span", f"events {start + 1} to "
                           f"{min(start + RAW_PAGE, len(records))} of {len(records)}",
                   class_="sub mono"))
    if page_number < total_pages:
        nav.append(tag("a", "later →",
                       href=f"/s/{session_id}/raw?page={page_number + 1}"))

    return tag("section", tag("div", "RAW", class_="eyebrow")
               + tag("p", f"{len(records)} events, in file order, by line number. "
                          "Every figure on every other lens comes from these. A long "
                          "body is truncated here with the whole record one click "
                          "away, because nothing hidden means reachable rather than "
                          "all at once.", class_="sub")
               + tag("div", " · ".join(nav), class_="row")
               + _search_box("search this page of events", controls=True)
               + "".join(rows)
               + tag("div", " · ".join(nav), class_="row"), class_="card")


def event_page(records: list[Record], summary: SessionSummary, line: int) -> str:
    """One record, in full, by line number. The end of every drill-down."""
    match = next((r for r in records if r.line == line), None)
    if match is None:
        return page(f"Line {line}", tag("section", tag(
            "p", f"This session has no event on line {line}.", class_="empty"),
            class_="card"), crumb=summary.id,
            tools=tag("a", "← raw", href=f"/s/{summary.id}/raw", class_="crumb"))
    return page(
        f"{match.phase} · line {line}",
        tag("section", tag("div", "THE RECORD", class_="eyebrow")
            + tag("pre", esc(json.dumps(match.data, indent=1, default=str))),
            class_="card"),
        crumb=f"log viewer · {summary.id}",
        tools=tag("a", "← raw", href=f"/s/{summary.id}/raw", class_="crumb"))


# -- L3, one turn -----------------------------------------------------------

def turn_page(records: list[Record], summary: SessionSummary, number: int) -> str:
    """One turn in full: every leg, everything the log holds about each.

    A leg containing a failure, a retry, or the turn's slowest call is EXPANDED and
    marked, so nobody has to hunt for what broke.
    """
    turns = group_turns(records)
    # By POSITION, not by the recorded number. A redone turn keeps its number, so four
    # turns can all be labelled 3 and a lookup by number reaches the first and hides
    # the rest.
    match = next((t for t in turns if t.position == number), None)
    if match is None:
        return page(f"Turn {number}", tag("section", tag(
            "p", f"This session has {len(turns)} turns, so there is no turn "
                 f"{number}. Turns are numbered by position in the file.",
            class_="empty"), class_="card"),
            crumb=summary.id,
            tools=tag("a", "← session", href=f"/s/{summary.id}", class_="crumb"))

    durations = insights.call_durations(match.records)
    calls = len([r for r in match.records if r.phase == "response"])
    header = tag("div", " · ".join([
        f"{calls} call" + ("" if calls == 1 else "s"),
        f"{match.iterations} iteration" + ("" if match.iterations == 1 else "s"),
        # Every figure names itself. A bare separator followed by an unlabelled
        # "unavailable" told the reader something was missing and not what.
        labelled("took", duration(match.duration_ms)),
        labelled("cost", match.render_cost()),
        labelled("volume", tokens(match.tokens
                                  or (match.input_tokens + match.output_tokens)
                                  or None)),
        esc(match.reason or "unfinished"),
    ]), class_="sub mono")
    if match.renumbered:
        # The writer says whether the reuse was deliberate. With `attempt` this is a
        # turn someone redone. Without it, an older log that did not record the
        # distinction, and guessing which would put words in the writer's mouth.
        why = (f"This is attempt {match.attempt} at turn {match.number}, redone with "
               f"/retry or /undo, so the log reuses the earlier number."
               if match.attempt else
               f"The log calls this turn {match.number}, which an earlier turn also "
               f"used. That log did not record whether the reuse was deliberate.")
        header += tag("p", chip(f"logged as turn {match.number}", "context") + " "
                      + why + " It is addressed by its position in the file, which is "
                      + "the only thing that identifies it.", class_="sub")

    legs = []
    for iteration, segment in _iterations(match.records):
        seen_response = False
        for record in segment:
            if record.phase == "response":
                # A ceiling makes one final tools-disabled call inside the same
                # iteration block, so two legs would otherwise wear the same label.
                legs.append(_leg_response(record, segment, durations, iteration,
                                          wind_down=seen_response))
                seen_response = True
            elif record.phase == "compaction":
                legs.append(_leg_compaction(record))
            elif record.phase in ("retry", "limit_reached"):
                legs.append(_leg_trouble(record))

    nav = []
    if number > 1:
        nav.append(tag("a", "← previous turn",
                       href=f"/s/{summary.id}/turn/{number - 1}"))
    if any(t.position == number + 1 for t in turns):
        nav.append(tag("a", "next turn →",
                       href=f"/s/{summary.id}/turn/{number + 1}"))

    return page(
        f"Turn {number} of {len(turns)}",
        header + tag("div", " · ".join(nav), class_="row")
        + _search_box("search in this turn", controls=True)
        + tag("section", "".join(legs) or tag(
            "p", "This turn recorded no calls.", class_="empty"), class_="card"),
        crumb=f"log viewer · {summary.id}",
        tools=tag("a", "← session", href=f"/s/{summary.id}", class_="crumb"))


def _iterations(records: list[Record]) -> list[tuple[int, list[Record]]]:
    """Split a turn's records into its iterations.

    Each leg has to carry ITS OWN calls. Rendering a response against the whole turn's
    records looked right and was wrong: every leg listed every tool call the turn made,
    so a reader opening iteration six saw twenty calls that belonged to other legs.

    Records before the first ``iteration`` marker, and any turn that has none, still
    come back as one segment: a leg that could not be attributed is still a leg, and
    dropping it would lose part of the record.
    """
    segments: list[tuple[int, list[Record]]] = []
    current: list[Record] = []
    number = 0
    for record in records:
        if record.phase == "iteration":
            if current:
                segments.append((number, current))
            number = int(record.get("n") or number + 1)
            current = []
            continue
        current.append(record)
    if current:
        segments.append((number, current))
    return segments


def _leg_response(record: Record, segment: list[Record],
                  durations: insights.Distribution, iteration: int,
                  wind_down: bool = False) -> str:
    ms = record.get("duration_ms")
    slow = ms is not None and durations.is_outlier(float(ms))
    calls = [r for r in segment if r.phase == "tool_call"]
    results = {str(r.get("tool_use_id") or r.get("name")): r
               for r in segment if r.phase == "tool_result"}
    body = []

    plans = [r for r in segment if r.phase == "plan"]
    if plans:
        body.append(tag("h3", "plan") + tag("p", esc(plans[0].get("text"))))
    reasons = [r for r in segment if r.phase == "reasoning"]
    if reasons:
        # Redacted is not empty. A provider that withholds a thinking block still sent
        # one, and showing nothing would read as the model not having thought.
        label = ("reasoning, redacted by the provider" if reasons[0].get("redacted")
                 else "reasoning")
        body.append(tag("h3", esc(label)) + tag("p", esc(reasons[0].get("text"))))
    if record.get("text"):
        body.append(tag("h3", "says") + tag("p", esc(record.get("text"))))

    broken = False
    for call in calls:
        key = str(call.get("id") or call.get("name"))
        result = results.get(key)
        body.append(tag("h3", "tool call") + tag(
            "pre", esc(f"{call.get('name')} "
                       f"{json.dumps(call.get('args') or {}, default=str)}")))
        if result is None:
            body.append(tag("p", "no result was recorded for this call",
                            class_="absent"))
            broken = True
            continue
        ok = result.get("ok", True)
        broken = broken or not ok
        text = str(result.get("result") or "")
        label = "result" if ok else f"result · FAILED {result.get('error') or ''}"
        body.append(tag("h3", esc(label))
                    + tag("pre", ansi(text), class_="term"))

    usage = record.get("usage") or {}
    label = (f"iteration {iteration}" if not wind_down
             else f"wind-down after iteration {iteration}")
    summary_line = " ".join([
        tag("span", label, class_="mono"),
        chip("reply", "reply"),
        tag("span", duration(ms), class_="mono"),
        tag("span", "ctx " + tokens(insights.prompt_occupancy(record)), class_="mono"),
        tag("span", "out " + tokens(usage.get("output_tokens")
                                    or record.get("output_tokens")), class_="mono"),
        tag("span", money(record.get("cost_usd")), class_="mono"),
        # The model's own account of why it stopped. It appeared nowhere, and it is the
        # difference between a reply that finished and one the cap cut off.
        chip(str(record.get("stop_reason")), "reply") if record.get("stop_reason")
        else chip("no stop_reason recorded"),
        chip("slowest call", "time") if slow else "",
        chip("failed", "failure") if broken else "",
    ])
    return tag("details", tag("summary", summary_line)
               + tag("div", "".join(body), class_="legbody"),
               class_="leg" + (" broken" if broken else
                               (" marked" if slow else "")),
               open=broken or slow,
               data_search=f"iteration {iteration} {record.get('text') or ''}")


def _leg_compaction(record: Record) -> str:
    """What a compaction actually did, rather than only what it dropped.

    A compaction that dropped nothing and compressed fifteen tool results summarised as
    "dropping 0 messages", which reads as having done nothing at all. It has four
    distinct moves and the summary names whichever ones it made.
    """
    did = []
    for count, what in ((record.get("dropped"), "dropped {} messages"),
                        (record.get("compressed"), "compressed {} tool results")):
        if count:
            did.append(what.format(count))
    if record.get("summarized"):
        did.append("kept a journey note")
    if not did:
        did.append("changed nothing")
    before = record.get("before")
    detail = ", ".join(did)
    if before:
        detail = f"from {before:,} tokens, {detail}"
    if record.get("over_budget"):
        detail += ", and was STILL over budget"
    return tag("details", tag("summary", " ".join([
        chip("compaction", "compaction"),
        tag("span", esc(detail), class_="sub"),
    ])) + tag("div", tag("pre", esc(json.dumps(record.data, indent=1, default=str))),
              class_="legbody"),
        class_="leg marked", open=True, data_search="compaction")


def _leg_trouble(record: Record) -> str:
    """A retry or a tripped ceiling, which is what "went wrong" usually means here.

    Marked BROKEN rather than merely notable, and that is not cosmetic: `broken` is what
    "next failure" jumps to. No session on disk has a failed tool result. Every real
    failure in the whole corpus is a retry or a ceiling, so a jump that only looked for
    failed tool calls had nothing to land on in any real log, which is a control that
    works in tests and never in use.
    """
    kind = "retry" if record.phase == "retry" else "ceiling"
    detail = (f"attempt {record.get('attempt')}, waited {record.get('wait')}s, "
              f"{record.get('status') or record.get('error')}"
              if record.phase == "retry" else
              f"{record.get('kind')} at {record.get('n')}/{record.get('max')}")
    return tag("details", tag("summary", chip(kind, kind) + " "
                              + tag("span", esc(detail), class_="sub"))
               + tag("div", tag("pre", esc(json.dumps(record.data, indent=1,
                                                      default=str))),
                     class_="legbody"),
               class_="leg broken", open=True, data_search=f"{kind} {detail}")


# -- diff -------------------------------------------------------------------

def diff_page(left: list[Record], right: list[Record],
              left_summary: SessionSummary, right_summary: SessionSummary) -> str:
    """Two sessions side by side, with a field one side lacks stated as missing."""
    rows = []
    for row in insights.diff(left, right):
        def render(value: Any) -> str:
            if value is None:
                return f'<span class="absent">{ABSENT}</span>'
            if isinstance(value, float):
                return money(value) if row["field"] == "cost" else f"{value:g}"
            if isinstance(value, int) and row["field"] == "peak prompt":
                return tokens(value)
            return esc(value)
        change = row["change"]
        cls = ("absent" if change == "not recorded" else
               ("diffdel" if change.startswith("-") else
                ("diffadd" if change.startswith("+") else None)))
        rows.append((
            _cell(esc(row["field"])),
            _cell(render(row["left"]), num=True),
            _cell(render(row["right"]), num=True),
            _cell(tag("span", esc(change), class_=cls)),
        ))
    head = (("field", False), (left_summary.id[:17], True),
            (right_summary.id[:17], True), ("change", False))
    return page(
        "Diff",
        tag("section", tag("div", "TWO SESSIONS", class_="eyebrow")
            + tag("p", "A field one side lacks reads as not recorded rather than as "
                       "zero, because a session that never recorded amplification did "
                       "not have none of it.", class_="sub")
            + _table(head, rows), class_="card")
        + tag("div", tag("a", f"← {left_summary.id}", href=f"/s/{left_summary.id}")
              + " · " + tag("a", f"{right_summary.id} →",
                            href=f"/s/{right_summary.id}"), class_="row"),
        crumb="log viewer", tools=tag("a", "← sessions", href="/", class_="crumb"))
