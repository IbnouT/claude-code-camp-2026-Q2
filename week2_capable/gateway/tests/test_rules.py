"""Standing advice: configuration the model reads, never code that acts."""

from __future__ import annotations

from pathlib import Path

from mud_gateway.rules import Rule, by_id, load, render

AUTHORED = Path(__file__).resolve().parents[1] / "mud_gateway" / "rules.yaml"


def test_the_shipped_advice_loads_and_reads_as_advice() -> None:
    rules = load(AUTHORED)
    assert rules, "the shipped rules must load"
    assert all(rule.text for rule in rules)
    assert len({rule.id for rule in rules}) == len(rules), "ids are unique"


def test_the_shipped_advice_names_nothing_that_must_be_discovered() -> None:
    """Advice is genre common sense. Naming the world would be cheating."""
    forbidden = ("minotaur", "midgaard", "temple", "sewer", "armory")
    for rule in load(AUTHORED):
        lowered = rule.render({"gold_carry_ceiling": 20}).casefold()
        for word in forbidden:
            assert word not in lowered, f"{rule.id} names {word}"


def test_numbers_come_from_settings_not_from_the_text() -> None:
    rules = by_id(load(AUTHORED))
    rule = rules["carry-little-gold"]
    assert "{gold_carry_ceiling}" in rule.text
    assert "keeping about 35" in rule.render({"gold_carry_ceiling": 35})


def test_a_rule_missing_its_number_still_reads(tmp_path: Path) -> None:
    """A gap in settings must not produce an unreadable line."""
    rule = Rule(id="x", text="bank above {ceiling}")
    assert rule.render({}) == "bank above {ceiling}"


def test_switching_a_rule_off_removes_it(tmp_path: Path) -> None:
    path = tmp_path / "rules.yaml"
    path.write_text(
        "rules:\n"
        "  - id: kept\n    text: keep this\n"
        "  - id: dropped\n    text: drop this\n    enabled: false\n"
    )
    block = render(load(path), {})
    assert "keep this" in block
    assert "drop this" not in block


def test_all_rules_off_leaves_nothing_in_the_context(tmp_path: Path) -> None:
    path = tmp_path / "rules.yaml"
    path.write_text("rules:\n  - id: a\n    text: t\n    enabled: false\n")
    assert render(load(path), {}) == ""


def test_a_missing_file_is_no_advice_rather_than_a_failure(
    tmp_path: Path,
) -> None:
    assert load(tmp_path / "absent.yaml") == ()


def test_a_malformed_entry_is_skipped_not_fatal(tmp_path: Path) -> None:
    path = tmp_path / "rules.yaml"
    path.write_text(
        "rules:\n  - text: no id here\n  - id: fine\n    text: kept\n"
    )
    rules = load(path)
    assert [rule.id for rule in rules] == ["fine"]
