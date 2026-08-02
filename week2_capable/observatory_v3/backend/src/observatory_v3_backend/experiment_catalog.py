"""Typed dimensions and resettable scenarios available to experiments."""

from __future__ import annotations

from .contracts import ExperimentFeature, ExperimentScenario

RENDER_MODES = ("raw", "minimal", "full")


def experiment_registry() -> tuple[ExperimentFeature, ...]:
    """Return every configuration dimension the workbench can explain."""

    return (
        ExperimentFeature(
            id="render.mode",
            label="Model-facing result",
            group="rendering",
            kind="enum",
            description=(
                "Shapes the same typed gateway result as raw text, a minimal "
                "envelope, or full structured evidence."
            ),
            default="full",
            options=RENDER_MODES,
            source="gateway result-mode contract",
            execution_supported=True,
        ),
        ExperimentFeature(
            id="tools.profile",
            label="Gateway tool surface",
            group="tools",
            kind="enum",
            description="Selects one versioned gateway capability projection.",
            default="direct-full",
            options=(
                "direct-full",
                "direct-core",
                "hybrid-full",
                "hybrid-core",
            ),
            source="gateway surface registry",
            execution_supported=True,
        ),
        ExperimentFeature(
            id="model.id",
            label="Agent model",
            group="model",
            kind="text",
            description="Uses a priced model from the agent model catalog.",
            default="claude-haiku-4-5",
            source="agent model catalog",
            execution_supported=True,
        ),
        ExperimentFeature(
            id="context.compaction_threshold",
            label="Compaction threshold",
            group="context",
            kind="number",
            description="Context-window fraction that triggers compaction.",
            default=0.85,
            minimum=0.01,
            maximum=1,
            source="agent task settings",
            execution_supported=True,
        ),
        ExperimentFeature(
            id="memory.enabled",
            label="Persistent knowledge",
            group="memory",
            kind="boolean",
            description="Makes per-player learned state available to the agent.",
            default=True,
            source="agent knowledge contract",
            execution_supported=False,
        ),
        ExperimentFeature(
            id="policy.max_iterations",
            label="Maximum turns",
            group="policy",
            kind="integer",
            description="Stops one sample before an unbounded agent loop.",
            default=60,
            minimum=1,
            source="agent task limits",
            execution_supported=True,
        ),
    )


def experiment_scenarios() -> tuple[ExperimentScenario, ...]:
    """Return scenarios backed by reset and evidence-judging contracts."""

    return (
        ExperimentScenario(
            id="J1",
            label="Find the bakery and read the menu",
            objective="Find the bakery and read the menu.",
            success_predicate=(
                "Gateway observations prove the bakery was seen and retain a "
                "numbered menu row naming bread, danish, cake, or pastry."
            ),
            starting_state="level1-temple@1",
            reset_strategy="verified snapshot before every sample",
            reset_identity="level1-temple@1",
            execution_supported=True,
        ),
        ExperimentScenario(
            id="J2",
            label="Find the Massive Minotaur",
            objective=(
                "Travel north from the Temple into the newbie zone and find "
                "the Massive Minotaur."
            ),
            success_predicate=("A gateway observation contains the Massive Minotaur."),
            starting_state="level1-temple@1",
            reset_strategy="verified snapshot before every sample",
            reset_identity="level1-temple@1",
            execution_supported=True,
        ),
    )
