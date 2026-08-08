# Week 3 · Putting the gateway back to its job

The gateway connects to the game, sends commands, parses replies, keeps
the journal, and serves the tool surface. Anything else in it is
misplaced. This removes what is misplaced and fixes the one place where
the observer writes where it should not.

## What goes

| Item | Why |
| --- | --- |
| `mud_gateway/walk.py` | Launcher work: mints an identity, registers a session, scripts a scenario, times it |
| `boukensha` in the gateway venv | An editable install added only for `walk.py`. The gateway must not depend on the agent |
| `mud_gateway/truth.py` + `tests/test_truth.py` | No production importer. Superseded by `observer.py` |
| `mud_gateway/rules.py`, `rules.yaml`, its import, `tests/test_rules.py` | Imported at `mcp_server.py:16` and never called. Authored gameplay advice is agent content |
| `mud_gateway/progress.py` + `tests/test_progress.py` | No importer, no entry point, no caller anywhere |
| `settings.rules_file` | No reader |
| `settings.record_room_numbers` | Parsed, no reader |
| `KnowledgeStore.retract_layer` | Definition only, repo wide |
| `derived` in `knowledge_models` layers | Only referenced by the tests being deleted |
| scratchpad probes | A dozen one-off scripts, none reusable |

Deleting the three test files takes the suite from 376 to 356. That is
the expected number afterwards, not a regression.

## One defect found while listing this

`settings.allow_raw` is parsed and never enforced. Nothing in `raw.py`
or `mcp_server.py` reads it, while `benchmark/config.py:162` sets it
false believing it closes off raw access. It is not dead code, it is a
setting that does nothing and is trusted to do something. Either enforce
it or remove it, in its own step.

## The observer writes into the player's session

Real, and the cause is not the observer. `AdminSession` names its own
session `admin-{name}` (`admin.py:52`) and writes into whatever journal
it is handed, so 205 admin events land in the player's session file
under `admin-admin`.

Fix: `AdminSession` takes a `session_id`, and the observer passes its
own.

## What is kept

- `observer.py`, the immortal connection that answers where the
  character is
- the room number as a parameter through `Session` into the pipeline and
  the projector. It arrives on a second socket, never in the parsed
  bytes, so it cannot be an observation: making it one would need a
  fabricated wire reference, and that reference becomes the evidence a
  fact is recorded against. It is also a key, not something learned
- rooms keyed by the game's number
- the deletion of `identity.py` and the graph's identity machinery
- the `visits` count, on the layer that supersedes

## Order

1. Delete everything above, tests included, in one commit. Suite goes to
   356 and stays green.
2. Give `AdminSession` its own session id. Exercise one live walk and
   read the journal at transcript level before anything else lands.
3. `allow_raw`, separately: enforce or remove.

## Where live checks belong

Not in the gateway. A scripted run with no model is the launcher's job,
and it already creates identities, registers sessions and lays out
paths. Until that exists, live checks are read from the journal at
transcript level, with no new code path invented for them.

## What this does not decide

`survival.py`, `economy.py`, `campaign.py`, `readiness.py`,
`state_block.py` and `navigation/executor.py` play the game or compose
the agent\'s prompt from inside the gateway. That was the capability
design, not an accident, and it is why the gateway keeps growing things
that are not gateway function. Redrawing that boundary is a separate
decision and is not in this step.
