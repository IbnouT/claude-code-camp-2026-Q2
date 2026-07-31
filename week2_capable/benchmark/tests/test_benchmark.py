from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import yaml

from benchmark.config import Repository, create_attempt
from benchmark.journeys import J1, J2, judge
from benchmark.metrics import AttemptMetrics, aggregate, week1_corpus
from benchmark.metrics import measure_attempt
from benchmark.report import write_markdown
from benchmark.runner import (
    Budget,
    BudgetError,
    SurfaceProof,
    _launch_agent,
    _redact,
    run_attempt,
)


def test_overlay_is_secret_free_and_pins_gateway_profile(tmp_path: Path) -> None:
    repository = Repository.discover()
    attempt = create_attempt(repository, tmp_path)
    text = (tmp_path / "settings.yaml").read_text()
    assert "boukensha-gateway" in text
    assert "direct-full" in text
    assert "result_mode: full" in text
    assert attempt.player_profile == "poucet"
    assert attempt.player_password_env == "MUD_PASSWORD"
    assert attempt.admin_password_env == "MUD_ADMIN_PASSWORD"
    assert "player-secret" not in text
    assert not (tmp_path / ".env").exists()
    assert attempt.max_turn_cost > 0


def test_one_off_player_becomes_an_ephemeral_secret_free_profile(
    tmp_path: Path,
) -> None:
    repository = Repository.discover()
    attempt = create_attempt(
        repository,
        tmp_path,
        player_character="NewTester",
    )
    settings = yaml.safe_load((tmp_path / "settings.yaml").read_text())

    assert attempt.player_profile == "benchmark-cli"
    assert attempt.player_password_env == "BOUKENSHA_PLAYER_PASSWORD"
    assert settings["gateway"]["connection"]["player_profile"] == "benchmark-cli"
    assert settings["gateway"]["players"]["benchmark-cli"] == {
        "character": "NewTester",
        "password_env": "BOUKENSHA_PLAYER_PASSWORD",
    }
    assert not (tmp_path / ".env").exists()


def test_reset_failure_is_a_setup_failure_before_any_model_evidence(
    tmp_path: Path,
) -> None:
    repository = Repository.discover()
    attempt = create_attempt(repository, tmp_path)
    launched = False

    def launch(**_: object) -> subprocess.CompletedProcess[str]:
        nonlocal launched
        launched = True
        return subprocess.CompletedProcess(
            [],
            2,
            "",
            "gateway reset failed: admin unavailable",
        )

    row = run_attempt(
        repository=repository,
        config=attempt,
        journey=J1,
        attempt_id="blocked",
        proof=SurfaceProof("direct-full", 25, 100, 25, "abc", "PASS"),
        launcher=launch,
    )
    assert launched
    assert row.status == "incomplete"
    assert row.error == "gateway reset failed: admin unavailable"


def test_attempt_uses_supervised_selected_session_reset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = Repository.discover()
    attempt = create_attempt(repository, tmp_path, player_profile="poucet")
    captured: dict[str, object] = {}

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        captured.update(kwargs)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("benchmark.runner.subprocess.run", run)
    _launch_agent(
        repository=repository,
        journey=J1,
        config=attempt,
        environment={"BOUKENSHA_DIR": str(tmp_path)},
    )

    command = captured["command"]
    assert isinstance(command, list)
    assert "boukensha" in command
    assert command[-2:] == ["--player-profile", "poucet"]
    assert "--task-stdin" in command
    assert command[command.index("--reset-baseline") + 1] == "level1-temple@1"
    assert command[command.index("--objective-title") + 1] == J1.objective_title
    assert command[command.index("--objective-source-kind") + 1] == "benchmark"
    assert captured["input"] == J1.order + "\n"


def test_journey_keeps_prompt_title_and_clue_distinct() -> None:
    assert J2.order == (
        "Travel north from the Temple into the newbie zone and find the "
        "Massive Minotaur."
    )
    assert J2.objective_title == "Find the Massive Minotaur"
    assert J2.clue == "north of the Temple · newbie area"


def test_unpriced_and_incomplete_attempts_do_not_aggregate(tmp_path: Path) -> None:
    base = dict(
        attempt_id="a", journey_id="J1", status="complete",
        stop_reason="journey-complete", iterations=1, success=True,
        evidence=(), final_state={}, wall_ms=1, model_calls=1, tool_calls=1,
        tools={"look": 1}, invalid_calls=0, corrective_calls=0,
        fresh_input_tokens=1, cache_read_tokens=0, cache_write_tokens=0,
        output_tokens=1, occupancy_tokens=1, schema_bytes=1,
        schema_token_estimate=1, reset_id="reset-1", profile_id="direct-full",
        capability_digest="abc", parse_misses=0,
        result_mode="full", tool_result_chars=1,
        cost_curve=(0.1,),
        wire_sequences=(), agent_log="agent.jsonl", gateway_journal="gateway.db",
    )
    priced = AttemptMetrics(cost_usd=0.1, **base)
    priced_failure = AttemptMetrics(
        cost_usd=0.3,
        **{
            **base,
            "attempt_id": "failed",
            "success": False,
            "stop_reason": "max_iterations",
            "model_calls": 2,
            "tool_calls": 3,
            "invalid_calls": 2,
            "corrective_calls": 1,
            "fresh_input_tokens": 3,
        },
    )
    unpriced = AttemptMetrics(cost_usd=None, **{**base, "attempt_id": "b"})
    incomplete = AttemptMetrics(
        cost_usd=0.2, **{**base, "attempt_id": "c", "status": "incomplete"}
    )
    setup_failure = AttemptMetrics(
        cost_usd=None,
        **{
            **base,
            "attempt_id": "setup",
            "status": "incomplete",
            "model_calls": 0,
            "tool_calls": 0,
            "reset_id": None,
        },
    )
    totals = aggregate(
        [priced, priced_failure, unpriced, incomplete, setup_failure]
    )
    assert totals["attempts"] == 2
    assert totals["setup_failures"] == 1
    assert totals["successes"] == 1
    assert totals["success_rate"] == 0.5
    assert totals["cost_usd"] == 0.4
    assert totals["tool_calls"] == 4
    assert totals["model_calls"] == 3
    assert totals["distributions"]["cost_usd"] == pytest.approx(
        {"mean": 0.2, "median": 0.2, "stdev": 0.1414213562}
    )
    assert totals["distributions"]["invalid_calls"]["mean"] == 1
    assert totals["distributions"]["corrective_calls"]["mean"] == 0.5


def test_tracked_week1_corpus_has_reproducible_boundaries() -> None:
    corpus = week1_corpus(Repository.discover().week1_sessions)
    assert (corpus.executed_total, corpus.executed_by_tool["move"]) == (451, 316)
    assert (corpus.confirmed_total, corpus.confirmed_by_tool["move"]) == (447, 314)


def test_report_row_links_both_sources_and_escapes_text(tmp_path: Path) -> None:
    row = AttemptMetrics(
        attempt_id="a|b", journey_id="J1", status="complete",
        stop_reason="journey-complete", iterations=1, success=True,
        evidence=(), final_state={}, wall_ms=1, model_calls=1, tool_calls=1,
        tools={}, invalid_calls=0, corrective_calls=0, fresh_input_tokens=1,
        cache_read_tokens=0, cache_write_tokens=0, output_tokens=1,
        occupancy_tokens=1, schema_bytes=1, schema_token_estimate=1,
        cost_usd=0.1, reset_id="reset-1", profile_id="direct-full",
        result_mode="full", capability_digest="abc", parse_misses=0,
        tool_result_chars=1,
        cost_curve=(0.1,),
        wire_sequences=(1,), agent_log="agent|log.jsonl",
        gateway_journal="gateway.db",
    )
    target = tmp_path / "report.md"
    corpus = week1_corpus(Repository.discover().week1_sessions)
    write_markdown(target, [row], corpus=corpus)
    text = target.read_text()
    assert "a\\|b" in text
    assert "agent\\|log.jsonl" in text
    assert "gateway.db" in text
    assert "Executed calls: 451" in text
    assert "Context-confirmed calls: 447" in text
    assert "no twentieth look" in text
    assert "Attempt measurements" in text
    assert "Tool distribution" in text
    assert "Cumulative cost checkpoints" in text
    assert "Success rate: 100.0%" in text
    assert "Standard deviation" in text


def test_j1_requires_bakery_and_menu_good() -> None:
    verdict = judge(J1, [{
        "payload": {
            "text": "The Bakery\n  1) fresh bread  10 coins\nA loaf of bread waits here"
        }
    }])
    assert verdict.success


def test_j2_requires_minotaur_observation_evidence() -> None:
    verdict = judge(J2, [
        {
            "kind": "observation",
            "payload": {"kind": "room", "mobs": ["The Massive Minotaur is here."]},
        }
    ])
    assert verdict.success
    assert "Massive Minotaur" in verdict.evidence[0]
    assert not judge(J2, [
        {"kind": "command", "payload": {"line": "find Massive Minotaur"}}
    ]).success


def test_budget_requires_headroom_and_pricing() -> None:
    budget = Budget(cap=1.0, spent=0.7)
    with pytest.raises(BudgetError):
        budget.require_headroom(0.5)
    with pytest.raises(BudgetError):
        Budget(cap=1.0).record(None)


def test_runtime_errors_redact_environment_credentials() -> None:
    assert _redact(
        "failed with secret-value and public",
        {"API_KEY": "secret-value", "PUBLIC_NAME": "public"},
    ) == "failed with [REDACTED] and public"


def test_metrics_preserve_limit_stop_reason_and_iterations(tmp_path: Path) -> None:
    agent_log = tmp_path / "agent.jsonl"
    agent_log.write_text(
        json.dumps({
            "phase": "turn_end",
            "reason": "max_iterations",
            "iterations": 125,
            "cost_usd": 0.2,
        }) + "\n"
    )
    row = measure_attempt(
        attempt_id="limited",
        journey=J1,
        agent_log=agent_log,
        gateway_journal=tmp_path / "missing.db",
        wall_ms=1,
        process_ok=True,
        schema_bytes=100,
        schema_token_estimate=25,
    )
    assert row.stop_reason == "max_iterations"
    assert row.iterations == 125


def test_metrics_record_cumulative_model_cost_curve(tmp_path: Path) -> None:
    agent_log = tmp_path / "agent.jsonl"
    agent_log.write_text(
        "\n".join(
            json.dumps({"phase": "response", "cost_usd": cost})
            for cost in (0.01, 0.02, 0.03)
        )
        + "\n"
        + json.dumps({
            "phase": "turn_end",
            "reason": "max_iterations",
            "iterations": 3,
            "cost_usd": 0.06,
        })
        + "\n"
    )
    row = measure_attempt(
        attempt_id="curve",
        journey=J1,
        agent_log=agent_log,
        gateway_journal=tmp_path / "missing.db",
        wall_ms=1,
        process_ok=True,
        schema_bytes=100,
        schema_token_estimate=25,
    )
    assert row.cost_curve == (0.01, 0.03, 0.06)


def test_cost_curve_prices_cached_tokens_from_model_catalog(tmp_path: Path) -> None:
    agent_log = tmp_path / "agent.jsonl"
    agent_log.write_text(
        json.dumps({
            "phase": "response",
            "provider": "test",
            "model": "cached",
            "cost_usd": 0.000005,
            "usage": {
                "input_tokens": 5,
                "cache_read_input_tokens": 10_000,
                "cache_creation_input_tokens": 100,
                "cache_creation": {"ephemeral_5m_input_tokens": 100},
                "output_tokens": 10,
            },
        })
        + "\n"
        + json.dumps({
            "phase": "turn_end",
            "reason": "max_iterations",
            "iterations": 1,
            "cost_usd": 0.00118,
        })
        + "\n"
    )
    models = tmp_path / "models.yaml"
    models.write_text(
        "test:\n"
        "  cached:\n"
        "    cost_per_million: {input: 1, cache_read: 0.1, "
        "cache_write_5m: 1.25, cache_write_1h: 2, output: 5}\n"
    )
    row = measure_attempt(
        attempt_id="curve",
        journey=J1,
        agent_log=agent_log,
        gateway_journal=tmp_path / "missing.db",
        wall_ms=1,
        process_ok=True,
        schema_bytes=100,
        schema_token_estimate=25,
        models_path=models,
    )
    assert row.cost_curve == (0.00118,)


def test_overlay_selects_model_result_mode(tmp_path: Path) -> None:
    repository = Repository.discover()
    attempt = create_attempt(repository, tmp_path, result_mode="minimal")
    assert attempt.result_mode == "minimal"
    assert "result_mode: minimal" in (tmp_path / "settings.yaml").read_text()


def test_overlay_applies_per_sample_iteration_and_spend_ceilings(
    tmp_path: Path,
) -> None:
    repository = Repository.discover()
    attempt = create_attempt(
        repository,
        tmp_path,
        model="claude-haiku-4-5",
        compaction_threshold=0.72,
        max_iterations=17,
        max_turn_cost=0.42,
    )

    text = (tmp_path / "settings.yaml").read_text()
    assert attempt.max_turn_cost == 0.42
    assert "max_iterations: 17" in text
    assert "max_turn_cost: 0.42" in text
    assert "model: claude-haiku-4-5" in text
    assert "compaction_threshold: 0.72" in text
