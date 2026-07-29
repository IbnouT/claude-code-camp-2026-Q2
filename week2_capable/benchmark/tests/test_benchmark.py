from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from benchmark.config import Repository, create_attempt
from benchmark.journeys import J1, judge
from benchmark.metrics import AttemptMetrics, aggregate, week1_corpus
from benchmark.metrics import measure_attempt
from benchmark.report import write_markdown
from benchmark.runner import Budget, BudgetError, SurfaceProof, _redact, run_attempt


def test_overlay_is_secret_free_and_pins_gateway_profile(tmp_path: Path) -> None:
    repository = Repository.discover()
    attempt = create_attempt(repository, tmp_path)
    text = (tmp_path / "settings.yaml").read_text()
    assert "boukensha-gateway" in text
    assert "direct-full" in text
    assert "MUD_PASSWORD" not in text
    assert not (tmp_path / ".env").exists()
    assert attempt.max_turn_cost > 0


def test_reset_failure_prevents_agent_launch(tmp_path: Path) -> None:
    repository = Repository.discover()
    attempt = create_attempt(repository, tmp_path)
    launched = False

    def fail_reset(**_: object) -> object:
        raise RuntimeError("no reset")

    def launch(**_: object) -> subprocess.CompletedProcess[str]:
        nonlocal launched
        launched = True
        return subprocess.CompletedProcess([], 0, "", "")

    row = run_attempt(
        repository=repository,
        config=attempt,
        journey=J1,
        attempt_id="blocked",
        proof=SurfaceProof("direct-full", 25, 100, 25, "abc", "PASS"),
        resetter=fail_reset,
        launcher=launch,
    )
    assert not launched
    assert row.status == "incomplete"
    assert row.error == "reset failed: no reset"


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
        wire_sequences=(), agent_log="agent.jsonl", gateway_journal="gateway.db",
    )
    priced = AttemptMetrics(cost_usd=0.1, **base)
    unpriced = AttemptMetrics(cost_usd=None, **{**base, "attempt_id": "b"})
    incomplete = AttemptMetrics(
        cost_usd=0.2, **{**base, "attempt_id": "c", "status": "incomplete"}
    )
    assert aggregate([priced, unpriced, incomplete]) == {
        "attempts": 1, "successes": 1, "cost_usd": 0.1,
        "tool_calls": 1, "model_calls": 1,
    }


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
        capability_digest="abc", parse_misses=0,
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


def test_j1_requires_bakery_and_menu_good() -> None:
    verdict = judge(J1, [{
        "payload": {
            "text": "The Bakery\n  1) fresh bread  10 coins\nA loaf of bread waits here"
        }
    }])
    assert verdict.success


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
