"""What the character has to show for playing: gains, losses, and pace.

Every number here comes from what the game reported about the character,
never from prose. The store already keeps each value's history, so a gain
is the step between two readings, and the pace of gains is what tells the
agent that its current hunting ground has stopped paying.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence


@dataclass(frozen=True)
class Step:
    """One change in a tracked number, with when it was observed."""

    value: int
    delta: int
    at: float


@dataclass(frozen=True)
class Progress:
    """What changed for the character over the readings held."""

    experience: tuple[Step, ...] = ()
    level: tuple[Step, ...] = ()
    gold: tuple[Step, ...] = ()

    @property
    def experience_gained(self) -> int:
        """Every rise in experience added up, over the whole history held.

        Losses are not subtracted, so a character that died and ground the
        loss back counts the same experience twice. This is how much was
        ever earned, not how far the character has come, and the two part
        company the first time it dies.
        """
        return sum(step.delta for step in self.experience if step.delta > 0)

    @property
    def levels_gained(self) -> int:
        return sum(1 for step in self.level if step.delta > 0)

    @property
    def gold_gained(self) -> int:
        """Every rise in carried gold added up, whatever caused it.

        Taking money out of the bank raises carried gold, so this counts
        withdrawals alongside loot. It says what passed through the purse,
        not what was won.
        """
        return sum(step.delta for step in self.gold if step.delta > 0)

    def recent_gains(self, count: int) -> tuple[int, ...]:
        """The last few experience gains, most recent last."""
        gains = [step.delta for step in self.experience if step.delta > 0]
        return tuple(gains[-count:])

    def gains_per_reading_are_falling(self, window: int = 3) -> bool:
        """True when recent rises are smaller than the ones before them.

        A hunting ground that pays less than it used to has been outgrown,
        which is the moment to look for stronger prey rather than to keep
        killing what is nearby.

        Read it for what it measures: the step between two readings of the
        score, not the reward of one kill. Checking the score half as often
        doubles each step and makes a steady hunt look like a rich one, so
        this only means anything while the score is read at a steady pace.
        Reward per kill needs a kill to be recognised, which is prose, and
        waits for the perception model.
        """
        gains = [step.delta for step in self.experience if step.delta > 0]
        if len(gains) < window * 2:
            return False
        earlier = gains[-window * 2:-window]
        later = gains[-window:]
        return sum(later) / window < sum(earlier) / window


def _steps(store: Any, player_id: str, name: str) -> tuple[Step, ...]:
    """Every reading of one tracked number, in the order observed."""
    subject = f"player:{player_id}"
    predicate = f"state.{name}"
    readings = [
        assertion
        for assertion in store.assertions()
        if assertion.subject == subject
        and assertion.predicate == predicate
        and assertion.status != "retracted"
        and isinstance(assertion.value, int)
    ]
    steps: list[Step] = []
    previous: int | None = None
    for assertion in readings:
        at = assertion.latest_evidence.observed_at
        delta = 0 if previous is None else assertion.value - previous
        steps.append(Step(value=assertion.value, delta=delta, at=at))
        previous = assertion.value
    return tuple(steps)


def read(store: Any, player_id: str) -> Progress:
    """Everything the store knows about how the character is faring."""
    return Progress(
        experience=_steps(store, player_id, "exp"),
        level=_steps(store, player_id, "level"),
        gold=_steps(store, player_id, "gold"),
    )
