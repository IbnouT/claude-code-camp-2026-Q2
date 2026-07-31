# Observatory · Live map

## Goal

The map is the Live screen's foundation: the learned world drawn from
evidence, stable while it grows. This plan consolidates the three approved
map mockups (`live_cockpit.html`, `map_modes.html`, `map_detail.html`) with
the corrections agreed after real-session testing. `live_map_mock.html` in
this folder is the binding visual reference.

## Layout stability

- Placement seeds at the first-discovered room and replays rooms and
  spatial edges in first-evidence order.
- Cardinal and diagonal movements are the only planar constraints.
  Flee, recall, death relocation, teleport and unknown transitions carry
  no direction vector: their targets join a floating cluster region and
  the connection renders as a dashed displacement link labeled by kind.
- Authenticated reset, relocation and reconnect receipts break player
  traversal continuity. Control-generated verification contributes no room
  visit, sighting or edge. The first subsequent player position starts a new
  observed component without an inbound edge.
- An occupied cell opens by shifting every room in the anchor's evidence
  component at or beyond the requested cell along the incoming axis. Whole
  lateral rows move together. The new room takes its requested integer cell.
  An unrelated blocking cluster stays fixed, so the dependent block advances
  by the smallest whole-cell distance that clears it. Diagonal insertions
  resolve on the vertical axis.
- Placement is deterministic and replayable. Existing rooms move only through
  an evidence-named insertion shift. Camera follow, centering and fit remain
  transforms only.
- A connection is marked bent only when the evidence itself is contradictory.
- One visual connection per room pair: two-way plain, one-way arrowhead,
  contradictory bent. Traversal counts live in the inspector.
- Unexplored exits render as short directional stubs, never ghost rooms.
- Up and down render as glyphs on the room box. A labeled layer
  transition draws only between two placed rooms.

## Feature checklist (from the approved mockups)

- Header chips: turn/iteration, zone, learned-world count with frontier,
  capture gaps when present.
- Camera group: Follow, Manual, Fit map, zoom in and zoom out.
- Mode group: Grow shows the complete learned graph. Focus shows complete
  breadth-first shells around the agent while every room's full drawn
  footprint fits the pane and clears the toolbar and legend. The translucent
  thought dock does not constrain room membership. Its 18-room value is an
  upper bound. Lantern shows the complete graph in distance-based light tiers.
- Focus shows as much of the neighborhood as fits at the viewer's chosen
  scale. Zooming out widens the lens, zooming in narrows it, and continuation
  chevrons name the learned context outside it.
- Focus never changes zoom. Entry recenters on the agent and resumes Follow.
  Only Fit map and the zoom buttons change scale.
- Focus panning remains bounded with the agent in frame. Agent movement
  recenters and resumes Follow. Learned rooms outside the projection are
  announced by fixed-size solid double chevrons on the pane edge.
- A dashed frontier stub means an observed exit with an unlearned destination.
  It remains visually distinct from a solid Focus continuation.
- Lantern does not pan. A drag hands the unchanged view to Grow and Manual.
- Agent marker with current-room glow, observed abnormal status glyphs
  and gold on the marker, recent-path highlight, visit-count badges,
  combat coloring on the current room, and objective beacon with label.
- Level-up toast from milestone data.
- Fixed thought dock, bottom-left: the agent's current
  thinking/planning/acting excerpt. It is translucent and collapsible.
- Fixed room inspector panel, right edge of the stage: opens on room
  click or Enter. It shows the name with a sector chip when the atlas
  correlation is verified, description, exits with unconfirmed directions,
  mob and object sighting counts, passed count, per-room spend when
  attributed, and the evidence link. Closes with X, Escape, click outside or
  re-click. Never covers the selected room.
- Legend: generated from the marker kinds actually drawn in the current
  mode and is collapsible.
- Every value traces to a typed field. An unavailable value is absent,
  never substituted.

## Semantic room color

Original CircleMUD sector flags are source evidence, not a sufficient visual
taxonomy. The observer atlas can apply a reviewed disagreement-only override
without changing the `.wld` files. Without that verified artifact, the served
map keeps the raw atlas-sector palette.

- Twelve categories cover route, interior, underground, urban, open land,
  water, highland, woodland, commerce, civic, sacred, and special rooms.
- Each override retains vnum, original sector, corrected category, and a
  content-grounded rationale.
- Loading rejects an override when its recorded original sector does not match
  the configured atlas.
- The semantic palette activates only when the verified override artifact is
  explicitly enabled.
- Current, combat, selected, beacon, and candidate states remain visually
  stronger than the underlying semantic fill.

## Delivery

The map lands in small verified checkpoints. M1, the structural map:
evidence graph and immutable layout, one connection per pair, bent and
displacement links, labeled vertical connection lines, floating clusters,
rooms and the agent marker. Its initial camera fits every placed room while
labels remain readable and never magnifies beyond the standard room size.
A larger world opens at a readable minimum scale with bounded drag panning.
M2, evidence semantics: frontier stubs, vertical room glyphs, visit badges.
Additional camera controls, modes, inspector, thought dock and legend follow
as their own checkpoints. Mock coordinates are composition guidance.
evidence order owns production coordinates.

## Acceptance (per checkpoint)

- M1: replay stability. Replaying the recorded session in increments changes
  existing positions only through deterministic integer insertion shifts.
  Rendered comparisons at 1440x900 cover one room, five rooms and the complete
  recorded world.
- M2: rendered comparison covering stubs, glyphs and badges.
- Focus: the rendered set is one connected component containing the agent.
  Every rendered room's complete DOM rectangle, including its title and
  external badges, stays inside the map pane. Focus entry and overlay changes
  preserve camera scale. A structurally required bridge may cross a persistent
  overlay so an otherwise admissible visible path stays connected. Solid
  continuation chevrons and dashed frontier stubs remain distinguishable.
  Agent-movement recentring is verified by the polling integration test, and
  in-browser observation of two consecutive live transitions was not performed.
- Lantern: graph-distance tiers preserve the complete learned graph. Dragging
  hands the unchanged framing to Grow and Manual.
- Semantic color: all 1,878 rooms receive one category, the frozen file
  contains only reviewed disagreements, representative corrected rooms pass
  API tests, and dark and light rendered captures preserve state precedence.
- Later checkpoints carry their own acceptance when planned.
