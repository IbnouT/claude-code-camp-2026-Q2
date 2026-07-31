# Observatory v2: clean rebuild, Live first

v1 (`../observatory/`) is PARKED/FROZEN as reference: its Python data layer,
typed contracts, and API are proven (71 tests, real 800-event session) and
are REUSED by v2 as-is. v2 rebuilds the FRONTEND only, one screen at a
time, starting with Live, governed by:

- `.coordination/live_interaction_spec.md` (fixed regions, thought dock,
  room inspector, data-driven legend, keyboard audit)
- the 7-point stable map contract (week0 layout.ts core, prefix-stable)

Stepwise: spec approval → stable map foundation → rendered checkpoint →
next step only on Ibnou's approval.

## Current surface

- `http://127.0.0.1:8787/` is the single served Observatory URL.
- `/` serves the approved launcher.
- `/live?player=…&session=…` serves the Live header and learned-world map.
- The map reads the retained typed snapshot projection every two seconds.
- Atlas-correlated rooms retain the approved raw-sector palette until a
  reviewed semantic override is explicitly enabled. The original `.wld` files
  remain unchanged.
- Room selection uses the mock's dashed aqua ring and aqua label. The stable
  `room` URL parameter restores that selection after reload.
- Room coordinates replay from first-evidence order on an integer lattice.
- An occupied target shifts the anchor component's whole far-side rows along
  the incoming axis. Diagonal insertions resolve vertically, unrelated
  clusters remain fixed, and amber links are reserved for genuine directional
  conflicts.
- Flee and other non-spatial transitions form floating clusters with dashed
  links.
- Directed evidence is reduced to one visible connection per room pair.
- The default frame fits the world while labels remain readable, never
  magnifies a young world, and enables bounded drag panning for larger maps.
- Vertical transitions remain attached through dashed, labeled connection
  lines.
- Observed but untraversed planar exits render as short directional stubs.
  Up and down stay on the room box, with quiet glyphs for frontier exits and
  solid glyphs for retained traversals.
- Repeat observations render the mock's `×N` badge only after the first visit.
- Grow keeps the complete graph and visible frontiers framed. Focus shows two
  learned hops with accessible `+N` boundary controls. Lantern keeps the full
  graph with a neutral distance falloff around the current room.
- Follow, Manual, and context-aware Fit remain independent from presentation.
  Zoom stays between `0.75` and `2`, drag enters Manual, and selected-room Fit
  frames the deterministic learned path.
- Selecting a room opens the fixed map inspector with retained description,
  exits, sightings, visits, attributed spend, confidence, and provenance.
  Escape, its close control, outside click, or room re-click closes it and
  clears the stable `room` URL parameter.
- The inspector shifts camera framing by the smallest safe distance rather
  than covering the selected square. Narrow layouts use a scrolling bottom
  sheet with the same evidence contract.
- Session identity comes only from the deep link.
- One context chip combines player, lifecycle state, and session identity.
- Its popover switches to live runs, opens recordings in Sessions, and exposes
  only lifecycle actions that are valid for the current session state.
- A verified missing session returns to the launcher. A catalog outage retains
  the current identity as reconnecting and removes write actions.
- Ask opens a deterministic query scoped to the selected live session.
- Theme choice persists across the launcher and Live shell.
- Leave returns to the launcher without stopping the agent.
- Stop uses the typed supervisor lifecycle endpoint.

## Web dependencies

- `lucide-react`: accessible interface icons that match the Observatory shell.
- `Vitest` and React Testing Library: component behavior and routing checks.
