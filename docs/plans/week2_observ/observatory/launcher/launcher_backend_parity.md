<!-- coordination: analysis doc, launcher backend parity, frontend-driven rebuild -->
# Launcher backend parity: frozen vs v3

## Purpose

Before rebuilding the Launcher on the v3 foundation, verify every backend
interface the Launcher needs. Presence is not enough. For each interface,
confirm v3 produces output equivalent to the frozen build.

Per interface, this doc records: what it does, frozen behavior and output, v3
behavior and output, a verdict, and how we should do it.

## Sources

- Frozen slim API: `week2_capable/observatory_v2/api/observatory_v2_api/server.py`
- Frozen full API: `week2_capable/observatory/observatory_api/`
- Frozen web Launcher: `week2_capable/observatory_v2/web/src/` (and `observatory/` web)
- v3 backend: `week2_capable/observatory_v3/backend/src/observatory_v3_backend/`
- Gateway identity: `week2_capable/gateway/mud_gateway/settings.py`

## Interfaces under audit

| # | Interface | Launcher need | Verdict |
|---|---|---|---|
| 1 | Session catalogue (roster, live status, recent summary) | list identities, show who is live | FIXED |
| 2 | Configured-player identity source | offer Start for configured, non-live players | FIXED |
| 3 | Start command (reset mode, opening objective) | start a session | FIXED |
| 4 | Command receipt / status flow | show start progress, navigate on success | FIXED |
| 5 | Watch-live routing + roster vitals | navigate to `/live`, show stat bars | FIXED |

## Findings

Audit-time evidence per interface. The verdicts below are what the audit
found. Current status is the table above, resolutions are in the progress log.

### 1. Session catalogue

- Frozen need: `GET /api/sessions` (polled every 2s), returns
  `players:[{id,label}]` and `sessions:[{id,player_id,character,live,latest_seq,updated_at,created_at,ended_at,event_count,stop_mode}]`.
  The `live` flag is the single driver of Start vs Watch. Source
  `observatory_v2/web/src/Launcher.tsx:200`, `contracts.ts:3-29`.
- How we should do it: serve the same roster fields bounded, and replace the 2s
  poll with a bounded query plus B6 notification. `live` must stay authoritative.
- v3 output / verdict: **PARTIAL**. Frozen `sessions()` (app.py:167-219 over
  runtime.py:58-79) vs v3 `/api/v1/sessions` (resources/handlers.py:68-234).
  - `live` matches exactly (same enum, same key). Start-vs-Watch works.
  - `id, player_id, state, created_at, updated_at, ended_at, stop_mode,
    gateway_session_id, capture_status, legacy` faithful.
  - Launcher-relevant divergence: `latest_seq` and `event_count` are now
    index-derived and nullable/stale (frozen reads live journal); roster is
    paginated/capped (20-50) and not live-first, so completeness is not
    guaranteed; envelope reshaped (frontend adapter maps it).
  - Weakened but not consumed by the Launcher: `control_state` (None),
    `control_available` (mirrors live, not socket-verified),
    `objective/goal_count/nudge_count` (index-recomputed). Lower priority here.
  - Fix for this screen: ensure the roster surfaces all players and every live
    session (raise page bound or float live first), and give `latest_seq`/
    `event_count` an acceptable value or accept documented staleness.

### 2. Configured-player identity source

- Frozen need: `players[]` in the catalog. Frozen derived players only from
  existing sessions (a configured player who never ran does not appear).
- How we should do it: read public identity from `GatewaySettings`
  (`gateway/mud_gateway/settings.py`), never secrets, so a configured non-live
  player can be offered Start.
- v3 output / verdict: **GAP**. v3 derives players only from existing sessions
  (`resources/handlers.py:198-201`), like frozen, so a configured-but-never-run
  identity is invisible. `GatewaySettings.players` gives
  `PlayerProfile{id, character, password_env}` (settings.py:21-27); `mud_gateway`
  is an editable dep of the backend and imports today.
  - Fix: add a configured-identity source from `GatewaySettings.load().players`,
    project only `id` + `character`, add a `start_available` flag (configured AND
    no live session), and never expose `password_env` or any secret.

### 3. Start command

- Frozen need: `POST /api/sessions/start` (lifecycle origin) body
  `{player_id, reset:"none"|"temple"|"baseline", objective?}` returns
  `{session_id, player_id, reset, objective, state}`. Reset modes and optional
  opening objective required. `Launcher.tsx:274-296`.
- How we should do it: fix the v3 start effect to the proven launch (correct
  agent executable, `--initial-task-stdin`, reset flags, captured stderr).
- v3 output / verdict: **GAP (broken)**. Verified:
  - `StartCommandRequest` has no `reset` and no `objective`, only `instruction`
    (contracts.py:313-319).
  - `_start` runs `sys.executable -m boukensha.launcher` (effects.py:124-126);
    `import boukensha` fails in the backend env (ModuleNotFoundError). No `cwd`,
    flag is `--task-stdin` not `--initial-task-stdin`, `stderr=DEVNULL`.
  - Frozen builds `uv run --project <repo>/week2_capable/agent boukensha`,
    `cwd=repo_root`, reset flags, `--initial-task-stdin` with trailing newline,
    `stderr=PIPE`, 55s readiness + reset-receipt verify (server.py:245-301,503-580).
  - Fix: add `reset` + `objective` to the command request/submission; rewrite
    `_start` to the frozen invocation (correct executable, cwd, reset flags,
    task-stdin, captured stderr threaded into the error), and verify readiness +
    reset receipt.

### 4. Command receipt / status flow

- Frozen need: synchronous. `start()` waits for readiness and returns the
  `session_id` directly; the UI navigates on that.
- v3 model: durable command (receipt + status endpoint). Question: how the
  Launcher reliably goes Start to running session before a session id exists.
- v3 output / verdict: **DIFFERENT (workable via polling)**. `POST /commands/start`
  returns `202` + `command_id` (session_id null); lifecycle
  `queued -> running -> succeeded|failed`; client polls `GET /commands/{id}` for
  `result_session_id`. Durable, idempotent, crash-recoverable. But
  `/notifications` requires a `session_id` (app.py:1637-1644), so a queued start
  cannot be awaited on the stream (chicken-and-egg).
  - Fix: keep the durable model; either add a `command_id`/`player_id`
    notification scope, or sanction polling `GET /commands/{id}` then subscribe
    to `?session_id=` only after `result_session_id` appears.

### 5. Watch-live routing (and roster vitals)

- Frozen need: navigate to `/live?player=&session=`; roster stat bars read
  `GET /api/sessions/{id}/snapshot` -> `player_status.fields` (hp, max_hp, mana,
  max_mana, level, gold). `routes.ts:10-16`, `contracts.ts:655-719`.
- Flag: snapshot is retired in v3; `player_status` vitals need a real bounded
  home for the roster bars.
- v3 output / verdict: **PARTIAL**. Routing contract `/live?player=&session=` is
  fine. But roster stat bars read snapshot `player_status.fields`
  (hp/mana/level/gold), and the snapshot endpoint is retired (410) in v3; the
  live vitals partition serves raw records, not the typed `player_status`.
  - Fix: expose `player_status` (or the specific vitals fields) through a bounded
    resource the roster can read.

## Fix order for the Launcher (backend, then screen)

1. Start command (#3): rewrite `_start` + extend the command request. Without it
   nothing launches.
2. Configured identity (#2): `GatewaySettings` source + `start_available`.
3. Roster completeness + vitals (#1, #5): surface all players and live sessions,
   give a bounded home to `player_status` and to `latest_seq`/`event_count`.
4. Receipt bridge (#4): sanction polling or add a command/player notification
   scope.
5. Build the Launcher screen against the corrected contracts.

## Progress log

- Audit complete. Three deep agents plus own spot-verification.
- Verified directly: broken start executable + missing reset/objective
  (effects.py, contracts.py:313-319); notifications require session_id
  (app.py:1637-1644); gateway identity shape (settings.py:21-27).
- All five interfaces have a verdict and a fix. Ready to implement in fix order.
- All five fixes are implemented and gated:
  1. Start rebuilt to the proven launch with typed reset, persistent stdin
     objective, retained process, control-state and reset-receipt readiness,
     and captured stderr detail.
  2. Configured identities merge from the gateway settings with an
     authoritative `start_available`.
  3. Catalog `latest_seq` and `event_count` read the session journal directly.
  4. The catalog notification scope announces roster transitions without a
     session identity. The browser follows a start receipt to its terminal
     state and opens Live from `result_session_id`.
  5. `/api/v1/live/{session_id}/vitals` serves the observed player state from
     a bounded journal tail for the roster stat bars.
- Behavior closure is tracked line by line in
  `launcher_parity_checklist.md`.
- Fix #3 (Start command) IMPLEMENTED and gated (ruff, mypy, full pytest green):
  - `reset` added as a persisted, typed field through request, submission,
    command, and durable store (idempotent column migration).
  - `_start` rewritten to the proven launch: `uv run --project <agent> boukensha`,
    `cwd` at repo root, `--initial-task-stdin`, reset flags
    (`--reset-baseline level1-temple@1` / `--relocate-temple`), stderr captured to
    a temp file and surfaced as the failure detail, 55s readiness budget.
  - New tests assert the built launch command (would have caught the original
    `ModuleNotFoundError` bug). OpenAPI artifact regenerated.
  - Deferred (honest): full reset-receipt verification (frozen also reads
    control-state and gateway reset receipt). The reset flag reaches the agent,
    but the backend does not yet verify the receipt. Follow-up hardening.
  - Not committed (awaiting approval).
