"""Advice before a fight: read from facts, never enforced."""

from __future__ import annotations

from mud_gateway.readiness import before_hunting, render

SETTINGS = {
    "hunt_level_floor": 5,
    "gold_carry_ceiling": 20,
    "fit_health_percent": 70,
}


def _rules(advice) -> set[str]:
    return {item.rule for item in advice}


def test_a_fit_character_is_told_nothing() -> None:
    """Advice worth reading is advice that stops when it does not apply."""
    state = {"level": 6, "hit": 46, "max_hit": 46, "gold": 5}
    assert before_hunting(state, SETTINGS) == ()
    assert render(()) == ""


def test_being_under_the_level_says_so() -> None:
    state = {"level": 2, "hit": 46, "max_hit": 46, "gold": 0}
    assert "outmatched-means-prepare" in _rules(
        before_hunting(state, SETTINGS)
    )


def test_being_hurt_says_so() -> None:
    state = {"level": 6, "hit": 10, "max_hit": 46, "gold": 0}
    assert "rest-before-going-on" in _rules(before_hunting(state, SETTINGS))


def test_being_hungry_says_so_even_at_full_health() -> None:
    """Starving stops recovery, so full health now is not full health soon."""
    state = {"level": 6, "hit": 46, "max_hit": 46, "gold": 0, "hungry": True}
    assert "rest-before-going-on" in _rules(before_hunting(state, SETTINGS))


def test_carrying_too_much_gold_says_so() -> None:
    state = {"level": 6, "hit": 46, "max_hit": 46, "gold": 300}
    advice = before_hunting(state, SETTINGS)
    assert "carry-little-gold" in _rules(advice)
    assert "300" in render(advice)


def test_a_sighted_target_prompts_sizing_it_up() -> None:
    state = {"level": 6, "hit": 46, "max_hit": 46, "gold": 0}
    advice = before_hunting(state, SETTINGS, sighted=True)
    assert "appraise-before-fighting" in _rules(advice)


def test_nothing_known_advises_nothing_rather_than_guessing() -> None:
    """An empty character sheet is not evidence of being unfit."""
    assert before_hunting({}, SETTINGS) == ()


def test_every_line_names_the_rule_it_came_from() -> None:
    """A transcript must show which advice was given, to be judged later."""
    state = {"level": 1, "hit": 5, "max_hit": 46, "gold": 900, "hungry": True}
    block = render(before_hunting(state, SETTINGS))
    for rule in ("outmatched-means-prepare", "rest-before-going-on",
                 "carry-little-gold"):
        assert rule in block


def test_the_thresholds_are_settings_not_opinions() -> None:
    """The same character is fit or unfit depending on configuration."""
    state = {"level": 3, "hit": 46, "max_hit": 46, "gold": 0}
    strict = before_hunting(state, {"hunt_level_floor": 10})
    lenient = before_hunting(state, {"hunt_level_floor": 2})
    assert _rules(strict) == {"outmatched-means-prepare"}
    assert lenient == ()
