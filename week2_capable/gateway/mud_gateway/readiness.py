"""Advice on whether the character is fit for what it intends.

Nothing here acts. Each check reads facts the agent earned by playing and
says what it sees, naming the rule the observation belongs to, and the
agent decides. Advice that cannot be overruled is a leash, and a leash
would decide the mission on the harness's judgement rather than the
model's.

An override is legitimate and expected. What it is not is silent: the
advice and the choice both end up in the record, so a transcript shows
what was suggested, what was done, and why they differed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class Advice:
    """One thing worth saying before the agent commits to something."""

    rule: str
    say: str


def _number(value: Any) -> int | None:
    return value if isinstance(value, int) else None


def before_hunting(
    state: Mapping[str, Any],
    settings: Mapping[str, Any],
    *,
    sighted: bool = False,
) -> tuple[Advice, ...]:
    """What is worth saying before going looking for a fight."""
    found: list[Advice] = []
    level = _number(state.get("level"))
    floor = _number(settings.get("hunt_level_floor"))
    if level is not None and floor is not None and level < floor:
        found.append(Advice(
            "outmatched-means-prepare",
            f"you are level {level} and this hunt suits level {floor}; "
            "growing stronger first is the shorter road",
        ))

    hit, top = _number(state.get("hit")), _number(state.get("max_hit"))
    share = _number(settings.get("fit_health_percent")) or 70
    if hit is not None and top:
        if hit * 100 < top * share:
            found.append(Advice(
                "rest-before-going-on",
                f"you are at {hit} of {top} health; resting first costs "
                "less than dying",
            ))

    for condition in ("hungry", "thirsty"):
        if state.get(condition):
            found.append(Advice(
                "rest-before-going-on",
                f"you are {condition}, and nothing recovers while it lasts",
            ))

    gold = _number(state.get("gold"))
    ceiling = _number(settings.get("gold_carry_ceiling"))
    if gold is not None and ceiling is not None and gold > ceiling:
        found.append(Advice(
            "carry-little-gold",
            f"you are carrying {gold} gold and would lose it dying; "
            f"about {ceiling} is enough to have on you",
        ))

    if sighted:
        found.append(Advice(
            "appraise-before-fighting",
            "you know where it is; size it up before you commit",
        ))
    return tuple(found)


def render(advice: Sequence[Advice]) -> str:
    """The advice as lines the agent reads, or nothing when all is well."""
    if not advice:
        return ""
    return "worth knowing:\n" + "\n".join(
        f"- {item.say} ({item.rule})" for item in advice
    )
