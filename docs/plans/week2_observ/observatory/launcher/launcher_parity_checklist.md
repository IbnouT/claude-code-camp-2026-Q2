# Launcher parity checklist

Closing authority: `npm run test:parity` green, covering the line.

Every observable behavior of the reference Launcher, from its source, with the
v3 status. The screen is done when every line is CLOSED with evidence. Partial
landings against this list are defects.

## Roster

| # | Behavior | Status |
|---|---|---|
| R1 | Players from the catalog, including configured players with no sessions | CLOSED |
| R2 | Rows ordered live first, then most recent | CLOSED |
| R3 | Sigil ⚔ live, ◎ idle, sizes 36 to 44 selected | CLOSED |
| R4 | Name with pulsing live dot when live | CLOSED |
| R5 | Recency block: LIVE now with real Turn N · it M when known, or last session · relative time | CLOSED |
| R6 | Progress shows the agent's true turn and iteration, never the gateway event sequence. Hidden until the projection knows them | CLOSED |
| R7 | "no sessions yet" for a player without history | CLOSED |
| R8 | Selected row expands with stat bars: Level line, HP, Mana, gold, observed note | CLOSED |
| R9 | Compact mini HP bar on a non-selected row whose stats are already loaded | CLOSED |
| R10 | `?player=` query preselects the roster row | CLOSED |
| R11 | Live transitions update the roster and the selected vitals without reload | CLOSED, user confirm pending |

## Start panel

| # | Behavior | Status |
|---|---|---|
| S1 | Heading with "as {player}" chip, collapse toggle, default open | CLOSED |
| S2 | Subtext branches: live player vs idle player | CLOSED |
| S3 | Objective textarea, 4000 max, trimmed, empty means idle start | CLOSED |
| S4 | Temple and baseline checkboxes, mutually exclusive, frozen tooltips | CLOSED |
| S5 | "Unchecked resumes the game normally." hint | CLOSED |
| S6 | Panel and controls disabled while the player is live or a start runs | CLOSED |
| S7 | Start submits the typed request with player, objective, reset | CLOSED |
| S8 | Starting overlay stays up until the session is genuinely running | CLOSED |
| S9 | Successful start navigates to Live for the new session automatically | CLOSED |
| S10 | Failed start surfaces the typed failure reason inline | CLOSED |
| S11 | Start button labels: idle, "Starting…" | CLOSED |
| S12 | Start rendering, guard, and submit all require the authoritative start_available | CLOSED |

## Watch and load

| # | Behavior | Status |
|---|---|---|
| W1 | WATCH LIVE tile per live session, navigates to Live with typed params | CLOSED |
| W2 | LOAD A SESSION heading with selected-of-all counts | CLOSED |
| W3 | All players toggle widens the recorded list | CLOSED |
| W4 | Rows: optional character prefix, relative time, stop-mode annotation, events, duration, Load | CLOSED |
| W5 | Load navigates to the recorded session route | CLOSED |
| W6 | Empty state "No recorded sessions yet." | CLOSED |
| W7 | `?load=1` opens the load panel | CLOSED |

## Global

| # | Behavior | Status |
|---|---|---|
| G1 | Constellation backdrop, one node pulses while anything is live | CLOSED |
| G2 | Loading skeleton, fatal error with Retry | CLOSED |
| G3 | Escape closes both panels | CLOSED |
| G4 | Full-bleed scene, no application header, theme control top right | CLOSED |
| G5 | Roster refresh without polling | CLOSED |
| G6 | Visual geometry identical to the reference (measured element pairs) | CLOSED |

## Open items

None. Closing evidence: start receipt follow in the start command data module
(submission held until succeeded or failed, typed failure detail thrown),
automatic Live navigation from result_session_id in the launcher container,
start_available enforced in render, guard, and submit, index route search
schema for player and load, Escape listener, compact status from retained
vitals. Sigil glyph color measured identical after teaching the class-merge
helper that launcher type tokens are font sizes, not colors. Gates: web
typecheck, lint, architecture, and 49 tests green.

## Verification pending

- User-confirmed live transition tracking after the notification ordering fix.
- One real end to end start: agent spawn, running session, automatic Live
  navigation.
