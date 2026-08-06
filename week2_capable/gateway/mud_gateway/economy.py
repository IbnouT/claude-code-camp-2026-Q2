"""The economy capability: gold custody over typed facts.

Death drops carried gold, so surplus above a configurable ceiling is
banked at a service place the agent has recorded. Everything here is
arithmetic over parsed numbers and typed service facts; recognizing that
a place is a bank happens in the model, which records it as a fact.
"""

from __future__ import annotations

import json
from typing import Any, Mapping


class Economy:
    """Numeric custody bound to one session, store, and navigator."""

    def __init__(
        self,
        session: Any,
        store: Any,
        navigation: Any = None,
        settings: Mapping[str, Any] | None = None,
    ) -> None:
        block = dict(settings or {})
        self.session = session
        self.store = store
        self.navigation = navigation
        self.carry_ceiling = int(block.get("carry_ceiling", 20))

    def carried_gold(self) -> int | None:
        for fact in self.store.current_facts(layer="parsed"):
            if fact.subject.startswith("player:") \
                    and fact.predicate == "state.gold" \
                    and isinstance(fact.value, int):
                return fact.value
        return None

    def known_services(self, kind: str) -> list[str]:
        """Place identities the agent recorded as offering one service."""
        predicate = f"service.{kind}"
        return sorted(
            fact.subject
            for fact in self.store.current_facts(layer="belief")
            if fact.predicate == predicate
            and fact.subject.startswith("place:")
        )

    async def bank_surplus(self) -> dict[str, Any]:
        """Deposit gold above the carry ceiling at a recorded bank.

        Returns a typed report. Every declined case names its reason
        instead of pretending to act.
        """
        gold = self.carried_gold()
        report: dict[str, Any] = {
            "routine": "bank_surplus",
            "gold": gold,
            "ceiling": self.carry_ceiling,
        }
        if gold is None:
            return self._done(report, "gold_unknown")
        surplus = gold - self.carry_ceiling
        if surplus <= 0:
            return self._done(report, "no_surplus")
        banks = self.known_services("bank")
        if not banks:
            return self._done(report, "no_known_bank")
        if self.navigation is None:
            return self._done(report, "navigation_disabled")
        graph = self.navigation._graph()
        titles = {
            place: graph.rooms[place].title
            for place in banks if place in graph.rooms
        }
        if not titles:
            return self._done(report, "bank_not_on_map")
        place, title = sorted(titles.items())[0]
        travel = await self.navigation.travel(title)
        report["travel"] = travel.stop
        if travel.stop != "arrived":
            return self._done(report, "travel_failed")
        await self.session.command(f"deposit {surplus}")
        report["deposited"] = surplus
        return self._done(report, "deposited")

    def _done(self, report: dict[str, Any], stop: str) -> dict[str, Any]:
        report["stop"] = stop
        self.session.journal.append(
            self.session.id, "reflex",
            {"rule": "custody", "version": "economy-1", **report},
        )
        return report


def report_text(report: Mapping[str, Any]) -> str:
    return json.dumps(dict(report), separators=(",", ":"), sort_keys=True)
