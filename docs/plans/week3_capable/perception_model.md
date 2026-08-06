# Week 3 · Perception model

A trained classifier that reads one game reply block and predicts typed
boolean flags, replacing prose pattern-matching with a learned,
versioned, measured component. It trains in a lab isolated from the
product code and ships as one pinned artifact the gateway can load.
This plan is the training experiment's authority.

## Task

Multi-label binary classification.

- Input: one command's complete cleaned output text (ANSI stripped,
  prompt line included), truncated at 512 tokens.
- Output: one probability per label, thresholded per label.

Labels, version 1:

| Group | Labels |
| --- | --- |
| perception | dark_or_blind, menu_or_pager, movement_refused, door_blocked |
| combat | combat_active, being_attacked, something_died |
| opportunity | corpse_or_loot, item_on_floor, gold_mentioned, shopkeeper_present, sign_readable |
| status | died_respawned, dangerous_zone_warning, hungry, thirsty |

The model predicts what the text states, never what to do about it.
Policy stays in rules and gates that read the flags.

A label earns its place only if the agent acts on the flag and no
protocol-shaped source carries the same information. That test removed
near_death and leveled_up from an earlier draft: exact hp and level are
parsed from the prompt line and the score output, so a prose classifier
for them is redundant. Values wanted only for observability are computed
from stored facts, never predicted by the classifier.

## Corpora

Two training corpora, one shared evaluation set.

- Governing rule: the deployed model must be buildable from
  observation of the game's output alone, the position a player holds
  with any game whose source is closed. Nothing trained on the engine's
  templates or source ships. Observed vocabulary is allowed in
  generated text: words the game has been seen to say are experience,
  not source access.
- Corpus A (reference only, never deployed): real reply blocks plus
  synthetic blocks generated from the engine's message templates. It
  measures string coverage when the source is read, as a comparison
  bound.
- Corpus B: the same real blocks, plus synthetic blocks generated only
  from patterns observed in our logs, slot fills varied the same way.
- Corpus D (the deployment corpus): authored text only. Every
  training block is generated from the label definitions and the
  interest vocabulary learned by playing, with freely written sentence
  contexts, realistic block structure, and hard negatives from the
  pinned contract decisions. No journal text and no engine source
  appear anywhere in training or threshold tuning: real game text
  exists only in the frozen gold set, as the exam. A floor unreachable
  from authored text is reported per label as an honest finding.
- Corpus C: text generated from the label definitions alone, in
  genuinely varied wording, with no engine templates, no journal text,
  and nothing derived from the gold set. Training on A measures string
  coverage of this game's messages; training on C measures whether the
  model learned the concepts. Only C is a generalization test: the
  game emits its templates at runtime, so A-trained scores are partly
  memorization of the test distribution.
- Adoption rule: a corpus is adopted on per-label floor performance on
  the frozen gold set, with the A versus C gap reported per label and
  the fragility tradeoff stated: an A-trained artifact that beats a
  C-trained one only through template memorization is a string table,
  and the report must say so.

Training labels come from weak supervision: the existing detectors and
parser where they exist, plus a one-time model-assisted labeling pass
over a stratified sample. Synthetic blocks carry perfect labels by
construction.

## Gold evaluation set

- 400 real reply blocks sampled from the journals, stratified so every
  label has meaningful support, including hard negatives (combat spam
  that is not a death, shop text without a shopkeeper line).
- Labeled once by a strong model through a local Claude Code instance
  in non-interactive mode (subscription seat, no metered API), then
  human-verified, then frozen.
- Never used for training or threshold tuning. A separate validation
  split from training data serves tuning.
- Circularity guard: gold labels are produced independently of the
  detectors used for weak supervision.

## The experiment grid

Three architectures by two corpora, six runs, one gold set:

| Rung | Architecture | Checkpoint |
| --- | --- | --- |
| 3 | TF-IDF word 1-2 grams and char 3-5 grams, one-vs-rest logistic regression | scikit-learn |
| 2 | Frozen sentence embeddings, trained logistic head | sentence-transformers/all-MiniLM-L6-v2 (fallback BAAI/bge-small-en-v1.5) |
| 4 | Fine-tuned encoder, multi-label head | microsoft/deberta-v3-small (fallback distilbert-base-uncased) |

The lab verifies checkpoint availability and licenses at setup and
records exact revisions in the artifact manifest.

Adoption rule across rungs: the simplest architecture that clears the
floors wins. A heavier rung must beat the lighter one on the gold set
to justify itself.

## Metric floors

| Labels | Precision | Recall |
| --- | --- | --- |
| dark_or_blind, combat_active | at least 0.98 | at least 0.90 |
| all others | at least 0.95 | at least 0.85 |

Per-label support is reported beside every metric. Class imbalance is
handled with per-label class weights and stratified sampling. Thresholds
are tuned per label on the validation split for the precision floors and
pinned in the artifact manifest.

## Lab structure

Isolated from the product: nothing under the lab imports product code,
and no product package imports the lab.

```text
lab/perception/
├── pyproject.toml        pinned: torch, transformers,
│                         sentence-transformers, scikit-learn,
│                         onnxruntime, tensorboard
├── extract.py            journals -> reply blocks JSONL
├── generate.py           template expansion for both corpora
├── label.py              weak supervision + assisted labeling
├── goldset.py            sampling, freeze, verification workflow
├── train.py              the six-run grid, TensorBoard events
├── evaluate.py           per-label tables, A/B and rung comparisons
├── export.py             ONNX int8 + manifest (metrics, thresholds,
│                         corpus hashes, checkpoint revisions)
└── runs/                 events and artifacts, never committed
```

## Compute

Training runs locally on the M4 Max (16-core CPU, 40-core GPU, 128GB
unified memory) using the MPS backend. At this scale every rung is
fast: the linear rung in seconds, the frozen-embedding rung in minutes,
the fine-tuned small encoder in well under an hour with generous batch
sizes. If the small encoders miss a floor, one escalation rung is
allowed before any conclusion of infeasibility: a base-size encoder
(deberta-v3-base or ModernBERT-base class, 100-200M parameters), which
this memory holds trivially. Runtime inference still targets CPU ONNX
int8 in the gateway regardless of what training used, so the deployment
budget stays milliseconds.

## Live monitoring

TensorBoard over `lab/perception/runs`, one run per grid cell, named
`rung{n}-corpus{A|B}`. Watched live: training loss, validation
per-label precision, recall, and F1 per epoch, and the six runs side by
side. The final gold-set tables land in a report under `docs/reports/`
when the experiment concludes.

## Execution

Run by a spawned agent in the lab. The metric floors are the objective,
and the loop continues until they are met. Stopping early on a failed
simple model is not an outcome.

Data phase, reported step by step:

1. Extract and deduplicate reply blocks from all retained journals;
   report corpus size and label-frequency estimates.
2. Build both synthetic corpora; report generated counts per label.
3. Build, verify, and freeze the gold set.

Improvement loop, repeated until every floor is met:

4. Train the current rung on both corpora and evaluate on the gold set.
5. For every label under its floor, run an error analysis: read the
   misclassified blocks and name the failure (missing training
   coverage, label noise, threshold, model capacity).
6. Apply the cheapest fix the analysis names: targeted synthetic data
   for the failing label, label corrections, threshold retuning, or
   the next rung up. Escalation order: linear, frozen embeddings,
   fine-tuned small encoder, base-size encoder. Data fixes are always
   tried before model escalation at the same rung.
7. Return to step 4.

Exit conditions, exactly two:

- Every floor met: export the winning artifact with its manifest and
  write the experiment report, including every rung and fix attempted.
- Every rung through the base-size escalation exhausted with error
  analysis showing the residual failures are irreducibly ambiguous
  text: report that conclusion with the misclassified blocks as
  evidence. Silent stopping or unreported lowering of floors is not
  permitted.

The runtime integration (gateway loads the artifact, flags become typed
observations with classifier provenance and probability-mapped
confidence) is specified in the [knowledge rework](knowledge_rework.md)
contract and lands only after the artifact exists and its report is
approved.

## Spend

None. Model-assisted labeling runs through a local Claude Code instance
in non-interactive mode on the existing subscription, never the metered
API. Training runs locally and costs nothing.
