# Live screen inventory and build plan

The reference Live screen, element by element, with every dynamic value
traced to its data source, compared against the v3 backend, and a build
plan per section. Sections marked OPEN are not yet built.

## Method

- Every reference claim cites the frozen source file and line.
- The reference styling is reproduced through the token and utility
  layers, never through parallel stylesheets.
- Reference algorithms independent of the UI port as logic. Reference
  delivery patterns (polling, monolith components, selector stylesheets)
  do not.
- Small presentation deviations are allowed when they preserve coherence
  with the already built header and launcher, and are recorded in the
  deviations section.

## v3 backend surface available to Live

| Resource | Path | Serves |
|---|---|---|
| Session catalog | `/api/v1/sessions` | roster, goals, states, liveness |
| Session detail | `/api/v1/sessions/{id}` | one session's summary |
| Live vitals | `/api/v1/live/{id}/vitals` | observed player fields |
| Live partitions | `/api/v1/live/{id}/{partition}` | identity-lifecycle, world-map, position-path, thought-activity, vitals-combat, economics, controls, diagnostics |
| Map | `/api/v1/sessions/{id}/map` | room graph for the spatial view |
| Goals | `/api/v1/sessions/{id}/goals` | objectives and their turns |
| Lifecycle | `/api/v1/sessions/{id}/lifecycle` | session lifecycle records |
| Evidence | `/api/v1/sessions/{id}/evidence/…` | drill-down records and content |
| Cost | `/api/v1/sessions/{id}/cost` | spend attribution |
| Search | `/api/v1/sessions/{id}/search` | in-session search |
| Notifications | `/api/v1/notifications?session_id=` | per-session change stream |
| Commands | `/api/v1/sessions/{id}/commands` | guide, revise, pause, resume, stop |

## Reference data map and v3 comparison

The reference Live screen is fed by two 2 second pollers and six on
demand calls. v3 replaces the pollers with bounded resources plus the
session scoped notification stream.

| Reference call | Purpose | v3 replacement |
|---|---|---|
| `GET /api/sessions/{id}/snapshot` 2s poll | one monolith of every panel's data | partitioned resources below, SSE invalidation |
| `GET /api/sessions/{id}/snapshot?through=` | pinned historical prefix | OPEN: no `through` bound on v3 resources yet |
| `GET /api/sessions` 2s poll | header context, capture status | session catalog + catalog notifications (built) |
| `POST 8792 /api/sessions/{id}/message` | guide or revise | `POST /api/v1/sessions/{id}/commands` (built) |
| `POST 8792 /api/sessions/{id}/stop` | stop | durable stop command (built) |
| `POST /api/ask` | evidence questions | `/api/ask` carried in v3 app |

Snapshot field to v3 source, per consumer:

| Field(s) | Consumer | v3 source | Status |
|---|---|---|---|
| `objective`, `objective_context`, `objective_initial` | objective strip, message dialog | goals resource | READY |
| `vitals`, `player_status` | evidence rail meters and facts | `/live/{id}/vitals` | READY |
| `operator_messages` | message dialog history | `controls` partition | READY |
| `lifecycle`, `control_state` | rail status, friction guards | catalog + `identity-lifecycle` partition | READY |
| `agent_thought`, `agent_belief` | thought dock, rail | derive from `thought-activity` records | DERIVE |
| `combat`, `combat_episode` | combat panel, map, rail | derive from `vitals-combat` records | DERIVE |
| `world` nodes, edges, frontier, beacons | map, inspector | map resource, nodes too thin | BACKEND |
| `timeline`, `milestones`, `friction` | causal timeline, friction block | no derived journey resource | BACKEND |
| `economics`, `usage`, `cost_usd`, caps | rail economics, timeline cost curve | cost totals only, no series | BACKEND |
| `room_economics` | map, inspector | cost contributors, mapping open | BACKEND |
| `through_sequence`, `following_live` | transport, all panels | client state, needs `through` bounds | BACKEND |

## Gaps and per-element plan

- READY sections build now on existing resources.
- DERIVE sections port the reference algorithm over partition records in
  a typed client projection module with unit tests.
- BACKEND sections need the reference world and journey projections
  ported into the v3 backend as bounded resources, plus an optional
  `through` bound for the pinned prefix. One batch, one restart.

Build order:

1. Shell layout, workspace regions, objective strip. No new data.
2. Message agent dialog and Ask dialog, header wiring. Commands and ask
   endpoints exist.
3. Evidence rail: status, posture, vitals, facts, conditions now,
   economics sub block after the backend batch.
4. Backend batch: the retained Live projection is exposed whole as
   `GET /api/v1/live/{id}/view` with the `through` bound, and ask moved
   to `POST /api/v1/ask`. The projection modules already lived in the
   backend, the batch routed them.
   A live parity spec against the reference stays required before any
   Live checklist line closes.
5. Causal timeline with transport.
6. Map cluster with ported layout, camera, presentation modules.
7. Thought dock, combat panel, friction block completion.

## Deviations

- Polling is replaced by bounded queries with SSE invalidation.
- The objective strip derives from the goals resource. The reference
  benchmark clue and the Goal replaced label have no retained v3 source,
  the revision count carries the replacement signal instead.
- Message history shows sent time and effect per retained control
  record. The applied-at-iteration line returns with the journey
  resource in the backend batch.
- The message send gate omits the reference followingLive condition
  until the timeline's pinned prefix lands.
- The objective hint condition reads the catalog running state, the
  reference additionally required a controllable followed session.
- The revision label counts retained goal items, bounded at the goals
  page size of twenty. The reference read a server revision number.
- The economics block shows one retained token total. The reference
  split tokens in and out and showed the cache hit rate, both return
  with the usage fields in the backend batch, with the spend caps and
  the context fill.
- The rail's last command line and the progress diagnostics wait for
  the journey resource. The progress block shows the stopped state only,
  the crashed, paused, reconnecting, and capture gap guards land with
  the journey work.
- The fighting posture override and the historical prefix status on the
  Now block land with the pinned prefix and combat sections.
- The Ask dialog resets on every open. The reference remounted it.
- The context switcher, stop dialog, and header actions are the already
  built v3 components, not the reference markup.
- Small tint and radius adjustments follow the built header and launcher
  token scale where the reference used one off values.

## Decisions needed

- The backend batch (item 4) is required for full parity of the map,
  timeline, and economics. It ports reference projection logic into the
  v3 backend as bounded resources. Confirm scope on return.
- Pinned prefix (`through`) semantics on v3 resources: server side bound
  (reference behavior) is assumed; a client side approximation would be
  weaker.

## Component detail: shell cluster (LiveShell, LiveHeader, ObjectiveStrip, ThoughtDock, FrictionBlock, CombatPanel, focusContinuation, useLiveSnapshot, selectionUrl)

## Layout skeleton (LiveShell 153-253; live-shell.css cited)

div.live-shell (100vh flex column, bg var(--color-bg))
  LiveHeader (rebuilt: our ApplicationHeader covers it; Message/Ask buttons exist disabled)
  LiveObjectiveStrip
  main.live-workspace [aria "Live workspace"]
    vars: --live-evidence-rail-width:320px; --live-timeline-height:110px
    position:relative; flex:1; min-height:0; overflow:hidden
    bg radial-gradient(1200px 600px at 60% 30%, #0d1622, transparent), var(--color-bg)
    LiveMap (identity != null)
    aside.live-evidence-rail [aria "Live evidence rail"] .is-open/.is-closed
      abs top:0 right:0 bottom:var(--live-timeline-height); w:320px;
      border-left 1px var(--color-line); bg var(--color-surface); overflow-y:auto
      button.live-rail-toggle (only <=700px: abs top:12 left:-68 68x34 r9 0 0 9 cyan 9px uppercase)
      LiveEvidenceRail
    section.live-causal-timeline [aria "Causal timeline"]
      abs right/bottom/left:0; h:var(--live-timeline-height); border-top; padding 12px 18px
      LiveCausalTimeline
  LiveAskDialog (askOpen), MessageAgentDialog (messageOpen && snapshot), SessionStopDialog (stopOpen)

State: askOpen, catalog, catalogRevision, stopOpen, messageOpen,
throughSequence (URL param 'through', positive int), railOpen (innerWidth>700),
contextState ("checking" initial).
contextState derivation (105-120): draining | stopped | running(live) | ended;
"reconnecting" on fetch fail; "checking" while catalog null.
selectedSession: catalog.sessions find by id AND player (51-54).
Keyboard: Cmd/Ctrl+K open Ask; Escape close Ask (134-150).
Redirects: identity null -> "/"; session vanished from catalog -> "/" (72-76, 100-104).
Stop callbacks: onStopFailed->running; onStopping->draining; onStopped->close+catalogRevision++ (246-251).
through URL sync via history.replaceState (55-70).

## LiveHeader (rebuilt already — reference for wiring)
Message btn: disabled !messageAvailable (= selectedSession.control_available); title
"Guide the running agent" / "Messaging requires a running, controllable session".
Ask btn: disabled identity null; kbd ⌘K. (Styling matches our built header actions.)
Responsive: <=1440px label spans hidden.

## LiveObjectiveStrip (36-50; css 69-122)
section.live-objective-strip [aria "Current objective"] [title = objective.evidence]
  min-height:34px flex center gap:10 pad 7px 22px border-b; bg color-mix(surface 94%, cyan)
  span "Objective" (quiet 9.5px 600 .16em uppercase)
  strong title (ellipsis, 12px 600 text) = objective?.title ?? compatibilityObjective ?? "No goal set"
  small clue (quiet 10.5px, flex 1 1000 auto, hidden <=700px):
    "Objective clue · {clue}" when from objective.clue;
    bare "First message starts the agent" when no goal && canSetGoal
  em revision (ml auto cyan 10.5px 700 .06em uppercase):
    "Revision {n}" when objective && objectiveInitial && revision>1;
    "Goal replaced" when objective && !objectiveInitial && source_kind=="operator"
Data: snapshot.objective_context / objective_initial / objective; canSetGoal =
identity && following_live (LiveShell 170-177).

## LiveThoughtDock (29-70; css 1356-1421)
aside.live-map-dock.live-thought-dock [aria "Agent thought"] data-map-marker-occluder
  abs bottom:18 left:18 w:min(340px, calc(50% - 38px)); r12 border line-strong;
  bg color-mix(surface 62%, transparent); shadow popover; backdrop blur(7px) saturate(105%)
  button.live-map-dock-toggle (min-h 36 full-w space-between pad 8 11; 9.5px 600 .12em uppercase; cyan in thought dock)
    span "Agent · {Thinking|Planning|Acting}[ · {time}]"
    ChevronDown/Up 14
  div.live-thought-dock-body (expanded only; max-h 108 scroll pad 0 12 11)
    p thought.text (12px lh 1.5) | "Agent thought not observed."
    small [title "Observed {observed_at}"] "{evidence} · line {line}" (mono 9px quiet mt 7)
Phase: reasoning->Thinking, plan/null->Planning, else Acting.
Time: historical? Intl hour:minute:2d:second:2d.fff : formatAge (now/Ns/Nm/Nh ago).
Historical = map controls === "session".

## LiveFrictionBlock (inside evidence rail; css 142-147, 363-417)
section.live-rail-block.live-friction-block [.is-fired: border-left 3 amber; bg amber 7%]
  h2 "Progress" (rail heading style 9.5px 600 .14em uppercase quiet)
  Guard precedence (88-118): reconnecting -> "Live evidence connection lost"...;
  crashed -> "Agent process ended unexpectedly" + "Retained evidence stops at sequence {n}.";
  stopped -> "Session stopped" + "No further activity...{n}.";
  paused -> "Agent paused by operator"...;
  captureStatus!=complete or capture_gaps in {agent_events_missing, agent_events_incomplete,
  gateway_events_missing, position_not_observed} -> "Progress cannot be determined"...
  Fired = no guard && friction.kind != null:
    strong "Possible navigation loop"(confusion_loop) | "Possible progress stall" (green; amber when fired)
    small code {kind} " · {threshold}"
  p "{new_places} new place(s) · {window_iterations} iterations"
  p "No new place retained" | "{n} iterations since the last new place"
  p code {repeated_command} " repeated ×{count} in the current room" (count>1)
  small "Combat in progress. Spatial progress may pause." (combat)
  fired: button "Inspect attempts"/"Hide attempts" (fit-content pad 5 8 r7 raised cyan 9.5px)
    p.live-friction-evidence "Evidence sequences {evidence.join(", ") || "not retained"}" (mono 9px)

## LiveCombatPanel (css 500-594)
null unless episode.active. aside.live-combat-panel [aria "Active combat"] data-map-focus-occluder
  abs top:18 left:18 w:340; r14; border color-mix(coral 24%, line);
  bg linear-gradient(180deg,#1a0f14,#140b10) [light: #fff3f3,#fff8f8]; shadow 0 18 50 -20 #000
  header.live-combat-header (flex gap 9 pad 11 14 border-b; bg #20111a [light #f7dcdd])
    span.live-combat-icon "⚔" (26x26 grid r8 bg #3a1620 coral)
    div min-w-0: strong "In combat[: {opponent}]" (13.5px ellipsis);
      small "{n} combat event(s) · since turn {t}|turn unknown" (11px quiet)
  div.live-combat-events [role log aria-live polite] (max-h 138 scroll pad 10 14 mono 12px lh 1.7;
    scrollbar thin coral 32%)
    span per line (block), tone by regex order:
      kill: /is dead!|death cry|you receive .*experience/i (green 650)
      critical: /critical|obliterate|annihilate|massacre/i (amber)
      incoming: /hits you|slashes you|...|you are dead/i (coral)
      outgoing: else (muted)
  Auto-scroll to bottom on last line sequence change.
Data: snapshot.combat_episode.

## focusContinuation.ts — pure; port as-is (contracts summarized)
projectFocusContinuations(graph, visibleRoomIds, viewport): hidden-neighbor
markers per edge (top/right/bottom/left priority), one per edge by smallest
overshoot then id. projectFocusContinuationOverlay(...): world->frame scale,
safe insets, occupied-rect avoidance with 3px gap, ±4px scan, fixed 24x50/50x24
boxes. nearestEdgePositions, rectanglesIntersect(gap), clamp.

## useLiveSnapshot — REPLACED in v3 by partition queries + SSE.
Contract to preserve: (latestSnapshot, snapshot, state loading|ready|reconnecting);
pinned view = parallel ?through fetch; reset on identity/through change;
failures keep last data + reconnecting.

## selectionUrl.ts — ?room= param read/replaceState sync (map deep link).

## Responsive: 1440 (header labels), 1040 (rail 260px), 700 (rail drawer
translateX, timeline 64px, objective clue hidden, dock adjustments 3055-3071).

## Component detail: map cluster (LiveMap + rooms/toolbar/legend/frontier/continuation/inspector + math modules)

Snapshot fields consumed: world.nodes/edges/frontier/objective_beacons,
room_economics, combat, combat_episode, agent_thought.

## LiveMap.tsx (1184 lines) — orchestrator
Early states: null snapshot -> .live-map-message[status] "World evidence is
reconnecting."|"Loading learned world…"; zero rooms -> "Waiting for the first
observed room."
Tree: section.live-map-stage [.is-lantern|.has-inspector] [aria "Learned world map"]
  style --live-map-overlay-safe-band:{overlayBand}px
  LiveMapToolbar
  svg.live-map [.is-pannable|.is-dragging] [img "Learned world, {N} rooms"]
    viewBox from projectedViewport; preserveAspectRatio xMidYMid meet
    defs: radialGradient#live-current-room-glow (#4fd6c9 .55->0);
      lantern: #live-map-lantern-gradient userSpaceOnUse cx/cy current room r=280
      (.live-map-lantern-center stop var(--color-text) .07; edge 0)
    lantern rect fill gradient sized to viewport
    g.live-map-connections > MapLink (g.live-map-link [.is-bent|.is-displacement|.is-vertical] > path;
      straight M..L.. or bentPath quadratic ctrl 34 perpendicular from midpoint)
    g.live-map-frontiers > g[opacity=roomOpacity(source)] > LiveMapFrontier
    g.live-map-rooms > g[opacity] > LiveMapRoom
  focus: div.live-map-continuations [aria "Learned map continuations"] > LiveMapContinuation*
  inspector: LiveRoomInspector; LiveCombatPanel; LiveThoughtDock; LiveMapLegend
  camera.panning && panHintVisible: p.live-map-pan-hint "Drag to explore the learned world."
    (abs left 50% bottom 68 pad 7 10 r9 surface muted 10px)
  reconnecting: p.live-map-connection-state[status] "Showing the latest world while
    evidence reconnects." (abs right 18 bottom calc(band+10) amber 10px)
CSS: stage abs top0 right:rail-width bottom:timeline-height left0 grid overflow hidden.
link stroke var(--color-map-link)(#243449/#aab8c8) w2 non-scaling; bent #8a6d3b;
displacement/vertical dasharray 4 5.

State: frame{1600,900 default}, cameraView{center,scale(session .8 else 1)},
cameraMode follow, chosenMode (session:"grow" else null), selectedRoomId (URL ?room=),
thoughtExpanded, legendExpanded(session true), panHintVisible, dragging, safeInsets(8s),
focusOverlayRects, markerOverlayRects, reflowRevision.
Graph: buildMapGraph | reflowMapGraph (after Reflow). evidenceMarkers: projectMapEvidence.
beaconRoomIds: world.objective_beacons canonicalized. inspector: projectRoomInspector.
legendEntries: projectMapLegend(combat). overlayBand: mapOverlaySafeBand.
Mode: automaticMapMode (focus auto >12 rooms; explicit choice wins).
Viewport: mapCameraViewport -> keepSelectedRoomOutsidePanel (inset: <=700 ->
{bottom:min(h*.55,420)+14} else {right:318}; only when inspector).
Pan: pointer drag >=4px, capture, camera->manual, lantern->grow; panMapCamera with
world-units-per-px; focus clamped clampFocusCamera; click after drag swallowed.
Camera buttons: fit -> fitMapCameraToSafeFrame(fitExtent); follow/manual keep center.
Mode buttons: focus/lantern snap to current room + follow.
Zoom: x/÷1.25 clamped [0.1,2]. Reflow: reflowMapGraph + fit to selection path|visible,
camera fit, revision++, hide hint.
Follow effect: first run snap; on room change resolveFollowMapCameraAnchor
(dead-zone: half-extents min(gap, frame*0.12/scale)) when isContinuousMapTransition
else jump-cut; honors prefers-reduced-motion; stepCriticallyDampedMapCenter per rAF
(response .28s, settle dist<.05 speed<.05); velocity zeroed on reversal.
Focus+manual+room change -> back to follow. Session-change resets all.
Escape: close selection first else collapse legend (unless dialog open);
outside pointerdown closes selection (outside inspector/room/dock/toolbar).
Selection: toggle + ?room= URL sync (selectionUrl).
Measurement: ResizeObserver frame (1px hysteresis); occluders [data-map-focus-occluder]
/[data-map-marker-occluder] rects ±8 clamped; safeInsets from data-map-overlay-edge +8.
roomOpacity: 1 for current/selected/non-lantern else lanternOpacities.get(id) ?? .12.

## LiveMapRoom (memo w/ custom comparator)
g.live-map-room .{sectorClass} [.is-candidate] .{is-combat|is-current|is-selected|is-beacon}
  translate(point) role button tabIndex 0 aria-pressed; title identityLabel
  current: circle.live-current-room-glow cx32 cy32 r48
  selected: rect.live-selected-room-halo 76x76 rx16 x-6 y-6
  rect 64x64 rx10
  vertical markers: text.live-map-vertical-marker.is-{up|down}.is-{traversed|frontier}
    x10 y15(up)/57(down) ▲▼ (frontier opacity .48)
  visits>1: g.live-map-visit-badge circle cx{48 if mob else 64} cy0 r10; text "×n" y3.5
  mobs: g.live-map-content-badge.is-mob circle cx62 cy0 r{8 current else 7}; "☠" y2.8
  objects: .is-object circle cx-2 cy62 r7; "◇" y65
  text.live-map-room-debug-id x32 y36 "p{place}"|"#{vnum}"
  text.live-map-room-title x32 y-14(current)/82: truncateMapRoomTitle
Colors: base map-room #1c3350/line #2f5680; sector classes -> token pairs
(field/forest->temple; inside/hills->shop; mountain->dark; water families;
highland woodland commerce civic sacred special); candidate: fill none stroke
#6a5a2a dash 4 3; beacon: shop+amber w2; selected: #5db4ff w2; current:
map-current w2; combat: #3a1620/#ff5d6c w2. Title 10.5px muted paint-order
stroke(bg 3px); current text 600; candidate #b79a4a; selected #5db4ff;
beacon amber; combat #ff5d6c. Badges: visit raised/room-line 9px; mob
#35131b/#ff5d6c text #ff8178 8px 700; object #33270f/amber. Halo rgb(93 180
255/34%) + 2 drop-shadows. focus-visible rect #5db4ff w2.
Click/Enter/Space -> onSelect. roomStateClass priority combat>current>selected>beacon.
sectorClass: water exact -> semantic-water; water*/flying/underwater -> water;
unknown -> neutral (no rule).

## LiveMapToolbar
div.live-map-toolbar [.is-session] data-map-overlay-edge=top data-map-focus-occluder
  group "Map camera": small "Camera"; Follow/Manual/{Fit map|Fit selection} aria-pressed
  group "Map presentation": small "Map"; Grow/Focus/Lantern
  full-variant: button.live-map-reflow "Reflow" [aria "Reflow map"]
  zoom "+"/"−" 34x34 disabled at limits
CSS: abs top14 right18 z5 flex gap8; group inline-flex pad3 border r9
raised-92% mix; small 9px uppercase .1em; buttons min-h28 r6 11px quiet;
pressed cyan-soft/cyan; disabled .48; tools 34x34 r9 16px; reflow auto pad 0 10.
Titles: Follow "Keep the current room within the central follow zone";
Manual "Freeze the camera at its current center and scale";
Reflow "Recalculate room positions from retained evidence".

## LiveMapLegend
aside.live-map-dock.live-map-legend data-map-overlay-edge=bottom focus-occluder
  toggle "Legend" + Chevron; expanded: ul.live-map-legend-entries > li >
  span.live-map-legend-swatch.is-{kind} + label
CSS: right18 w190 transition right 160ms; has-inspector -> right 336px.
Swatches 14x14 r4; kinds: current, selected(blue glow), frontier(dashed top
border), continuation("»" #b99cff 20px), vertical("▲"), visits(circle ×N 7px),
beacon(amber on shop), mob("☠"), object("◇").
projectMapLegend order: Learned room; Current room|Current · combat; Selected
room; Frontier exit; Learned map continues; Up or down exit (when any);
Repeat visit; Objective beacon (when); Mob sighting; Object sighting.
[] when no visible rooms.

## LiveMapFrontier: g.live-map-frontier path M start L end + circle r2.5 end;
color map-frontier (#4a5c74); dash 3 4 w2. From projectMapEvidence.

## LiveMapContinuation: div.live-map-continuation data-edge [img "Learned map
continues {dir}"] pos from projectFocusContinuationOverlay; span fade +
ChevronsRight 18. #b99cff; per-edge rotation; 32x4 gradient fades.
LiveMap passes safeInsets=defaultSafeInsets(8) and markerOverlayRects.

## LiveRoomInspector
aside.live-room-inspector [aria "Room inspector, {title}"] data-map-overlay-edge=right
  header: name strong 15px; meta "passed ×{visits}" + "first s{f} · last s{l}"; close X 28x28
  body: p description (12px/1.5); h2 "Exits" + chips "{dir}[ ?]" (.is-unconfirmed;
  "none observed"); "Seen here" ☠ mob list; "Objects known here" ◇; stats grid 2col
  (Passed "{n}×", Spent here "${spend.toFixed(3)}" when econ, Confidence);
  "Agent evidence" dl (Room/Description/Frontier/Sighting observations, Economics
  records; only counts>0); atlas section (Vnum/Sector/Zone/Correlation/Atlas sources).
CSS: abs z6 top62 right18 w300 max-h calc(100%-80) scroll r14 border line-strong
gradient surface/cyan mix shadow popover blur(5px); header sticky.
projectRoomInspector: canonical id; frontier dirs -> unconfirmed exits merged
evidence; exits sorted compass then up/down, unknown last; spendUsd sum
cost_usd by canonical node_id (null when none); evidence counts distinct sets;
description ?.text.

## Math modules (PORT AS PURE LOGIC, with their tests' contracts)
- mapModel: room 64x64, gaps 148/122, inset 92. buildMapGraph (evidence-order
  placement) / reflowMapGraph (best of improveLayout(placeRooms) vs
  improveLayout(directionalReflowRooms) by layoutPenalty = crossings*1e6 +
  directionViolations*1e4 + edgeSpan*10 + area). canonicalizeAtlasRooms merges
  by vnum (union exits/sightings, sum visits, state current>candidate>observed).
  aggregateConnections (undirected pairs, flags vertical/displacement/bent/oneWay).
  placeRooms precedence: planar edge -> direction vector + openInsertionSlot
  (shift dependent BFS set min distance; throws on foreign component);
  vertical -> diagonal vectors or nearestVerticalFree; displacement ->
  nearestFree; disconnected -> new cluster maxX+3, y cycle -1/0/1.
- mapCamera: fitMapViewport (aspect expand), mapCameraViewport (clamp .1..2),
  fitMapCameraToSafeFrame (inset-aware), zoom 1.25, panMapCamera,
  followMapCameraWithinDeadZone (12% frame), resolveFollowMapCameraAnchor,
  stepCriticallyDampedMapCenter (ω=2/0.28 closed-form, snap on overshoot),
  clampFocusCamera (±min(viewport/4, dist-to-edge+room)),
  keepSelectedRoomOutsidePanel (+38/+30 screen margins),
  mapOverlaySafeBand (max(thought,legend)+18; collapsed 36, thought 121,
  legend ceil(26+entries*19.2)), isContinuousMapTransition (non-displacement
  connection joins rooms).
- mapPresentation: modes grow/focus/lantern; focusMax 18, autoThreshold 12;
  projectMapPresentation (BFS shells fit-checked vs layout+overlays; selection
  path union/rebuild; fillConnectedFocusRooms greedy to 18;
  pruneToCurrentComponent); projectLanternOpacities 1/.8/.5/.12;
  visibleRoomComponentSize.
- mapRoomFootprint: title char limit 18, width<=112(+8 buffer), top -28,
  bottom 88, badges -10/-9/+74; truncate + estimated width table (M/W 9.5,
  ilftr 3.5, lower 5.8, caps 7, space 3, … 10.5).
- markerProjection: frontier length 26 from edge midpoint (center±32);
  grouped per source:direction merged evidence; vertical markers up before
  down, state frontier when live frontier or never traversed (reverse-exit
  aware); markerKinds {frontier, vertical, visits(>1)}.
- selectionUrl: ?room= replaceState.
- UNCLEAR/unused exports: resolveMapViewport, mapSafeViewport, clampMapCamera,
  initialMapCamera, centerMapViewport, mapDragScale, transitionMapCamera,
  changeMapZoom; .is-session/.is-expanded/.is-collapsed classes without rules.

## Component detail: causal timeline + evidence rail + liveEvidence helpers

## LiveCausalTimeline (pure render of props; no local state)
Props: latestSnapshot, snapshot, state, onSelectThrough.
Landmarks/scale/cost/stepping read latestSnapshot; heading state/reading/
cursor read snapshot (through-scoped).

Tree:
- empty: div.live-timeline-empty[status] "Timeline evidence is
  reconnecting." (state==reconnecting) | "Waiting for retained timeline
  evidence."
- div.live-timeline-heading (flex gap 13, quiet 11.5px)
  small "Recent journey" (9.5px 600 .18em uppercase) + span "· last {N} events"
  span.live-timeline-prefix-state.is-live|is-paused > i dot(7px; cyan glow when live) + "following live"|"paused"
  span.live-timeline-reading "turn {n} · " (null-omitted) + "seq {through_sequence}"
  div.live-timeline-transport[aria "Timeline transport"] (ml auto, gap 8):
    buttons (min-h 28 pad 5 11 r8 line-strong raised muted 11.5px; disabled .35):
    "⏸ Pause"/"▶ Resume"; "◀ Step"; "Step ▶"; "⏭ Jump to live" (.live-timeline-return cyan)
- div.live-timeline-track (rel h 52 mt 10 pointer)
  div.live-timeline-axis (1px line top 30 line-strong; hover tint)
  svg.live-timeline-cost[img "Cumulative session cost"][viewBox 0 0 900 52] > polyline (#1c2836 w1.4) when curve
  button.live-timeline-landmark.is-{room|level_up|friction|operator_message}
    at left {position(seq)}%; 9px dot (room #2f5680) / 12px (level amber, friction #c98f3a, operator violet);
    hover scale 1.25 glow; title "{Kind}: {label}, sequence {n}"
  span.live-timeline-label at same %; top 40; shortLabel (latest per kind for level/operator/friction; rooms unlabeled)
  div.live-timeline-cursor at selected % (2px cyan bar top14 bottom8 + ::after 10px dot)
  input.live-timeline-scrubber[range][aria "Observed prefix"] invisible overlay (opacity .001 inset 0)
    min=firstSequence max=lastSequence value=clamped selected; onChange -> onSelectThrough(Number)
  span.live-timeline-no-landmarks "No causal landmarks in the recent retained window"

Behaviors: Pause -> onSelectThrough(through_sequence); Resume/Jump -> null;
Step prev/next over eventSequences (all latest timeline seqs + latest_sequence,
dedup asc); next disabled when following; landmark at latest_sequence selects null.

Algorithms (port): recentLandmarks (rooms dedup vs previous position label;
level-ups >= firstRetained; operator_control agent items; friction max(evidence),
suppressed when kind null/empty/old/confusion_loop w/o repeated_command;
sorted asc). costCurve (900x52, "" when <2 pts or last cumulative <=0;
x=i/(n-1)*900, y=46-(cum/high)*33, toFixed(1)). position: degenerate->50 else
2+clamp01(...)*94. labelledLandmarks: latest of level_up/operator_message/friction.

## LiveEvidenceRail (no state; all from through-scoped snapshot)
- empty: p.live-rail-empty "Waiting for retained evidence…" (m 42 16 0, quiet 11px)
- div.live-rail-content (grid, align-content start)
- RailBlock: section.live-rail-block (grid gap 10 pad 14 16 border-b) >
  header (h2 9.5px 600 .14em uppercase quiet; optional span.live-rail-prefix-state.is-live|is-history > i dot + label)
- Block "Now": status: following && lifecycle==running -> "Live"/live;
  following && other -> lifecycleLabel (underscores->spaces, capitalize)/history;
  !following -> "Historical prefix"/history.
  span.live-posture-pill[.is-fighting] title=evidenceTitle; text combat?"fighting":posture
  EvidenceText "Latest tool action": agent_belief.text | "No tool action retained"; meta formatAge; title evidence
  EvidenceText "Last command": latestCommand | "No command retained"
- Block "Character": VitalBar hit/mana/move (grid 44px 1fr 72px; track 8px #0c1320;
  fills: hit #ff5d6c->#f5c463, mana #2b5f8f->#7ec3f0, move #2e7d5b->#8bdfa9;
  "{v} / {max}" | "{v}" | "Not observed")
  div.live-character-facts: Level, Gold (gold amber) title "{method} · sequence {n}"
  div.live-condition-list [aria "Observed conditions"]: hungry/thirsty Warn(amber),
  drunk "Intoxicated" warn, poisoned bad(coral); only value===true
- Block "Live economics" (LiveEconomics):
  live-spend: small "Turn spend"|"Session spend" (spend_cap_scope) +
  strong money(amount)[ / money(cap)]; span.live-spend-track aria "{n} percent of cap",
  fill width min(ratio,1) (amber)
  live-economics-grid 2col: Latest response (money|"Not retained", em trend "+/-{n}% vs prior");
  Tokens in (fresh+cache_read+cache_write, toLocaleString); Tokens out; Cache hit "{n}%"|"Not observed"
  CostSparkline: figure > figcaption "Cost per response: last 20" +
  svg 240x36 polyline #4fd6c9 w1.6 non-scaling | span "No response costs retained"
  live-context-fill: small "Latest response context" + strong "{n}%" + bar (economics.at(-1).context_tokens / context_limit)
- LiveFrictionBlock (part 1)
Money: <0.01 -> $x.xxxx else $x.xxx.

## liveEvidence.ts — port whole module
formatAge, projectSpend (scope turn->current_turn else cost_usd; cap),
observedNumber, latestCommand (last gateway command, strip /^Command:\s*/i),
tokensIn (fresh_input+cache_read+cache_write), cacheHit (cache_read/tokensIn,
null when 0), latestContextFill (unclamped), responseTrend ((last-prev)/prev).

## Raw literals to tokenize
#0c1320 (tracks) #0c131d (cells) #3a1620 (fighting) vital gradients
#ff5d6c #f5c463 #2b5f8f #7ec3f0 #2e7d5b #8bdfa9; #4fd6c9 sparkline;
#1c2836 cost stroke; #2f5680 room dot; #c98f3a friction dot; #0d1622 workspace radial.

## Component detail: dialogs + data map 

### Key build implications

- Frozen live data arrives through TWO 2-second setTimeout pollers:
  snapshot (`/api/sessions/{id}/snapshot`, optionally + `?through=` pinned
  view fetched in parallel) and catalog (`/api/sessions`). v3 replaces
  both with bounded resources + the session-scoped notification stream.
- The snapshot is one monolith response; v3 serves partitions. The
  per-field consumer table below is the mapping key.
- MessageAgentDialog delivers via lifecycle 8792 with a v1-commands
  fallback; v3 goes straight to `/api/v1/sessions/{id}/commands`
  (guide/revise wired server-side incl. idle wake).
- `/api/ask` exists in the v3 app routes (legacy carry). Ask dialog can
  target it as-is.
- SessionStopDialog behavior already rebuilt in v3 (header work).
- Route identity `/live?player=&session=` + `through` URL param for the
  pinned sequence: v3 live route search schema must add `through`.


### LiveAskDialog (live/LiveAskDialog.tsx)

Props (24-30): identity, open, selectedRecordId=null, space="live", onClose.
State (39-44): input ref, question, answer, error, loading, limitToSelection.
Tree: div.live-dialog-backdrop[presentation, mousedown closes] >
section.live-ask-dialog[dialog, aria-modal, label "Ask about this session"] >
form.live-ask-query[submit] > Search(18) icon; input[aria "Question about
this session", placeholder "Ask why, find a trace, or search exact
evidence", autofocus]; button.live-ask-submit[disabled empty/loading,
"Planning…"/"Ask"]; button.live-icon-button[Close Ask, X(16)].
div.live-ask-scope: span "Scope", strong "{player} · {session}"; small
"Evidence through {rec}." | "Whole session evidence." + "Answers cite
retained records. Model use is off."; small example questions;
label.live-ask-boundary checkbox limitToSelection (only when
selectedRecordId). p.live-ask-error[alert]. div.live-ask-answer: small
tier; p answer; p.live-ask-missing "Missing: …"; small "{n} evidence
citations"; ul.live-ask-citations > li > strong label/id/"Evidence" +
span excerpt.
Request (61-79): POST /api/ask JSON {question, scope{space, player_id,
live_session_id | run_id, selected_record_id?}, allow_model:false,
allow_summary:false}. Response: {answer, citations[{id,label,excerpt}],
missing[], tier}; non-ok throws detail. Escape/⌘K handled by shell
(LiveShell 134-150).

### MessageAgentDialog (live/MessageAgentDialog.tsx)

Props (99-117): controlAvailable, followingLive, identity, messages
(LiveOperatorMessage[]), objectiveAvailable, selectedSequence,
sessionRunning, onClose. Shell wiring (LiveShell 228-240):
following_live, operator_messages, objective_context/objective,
through_sequence, contextState==="running", control_available.
State (118-127): action guide|revise (initial guide iff
objectiveAvailable... NOTE initial "guide" if objectiveAvailable else
"revise"), closing, instruction, optimistic{...status sending|waiting,
baselineCount}, error, refs. canSend = followingLive && sessionRunning
&& controlAvailable && !sending.
Tree: div.live-dialog-backdrop.live-message-backdrop[.is-closing/.is-opening,
pointerdown self closes] > section.live-message-dialog[dialog] >
header.live-dialog-heading (p "Running agent · {player}", h2 "Your
messages"; button.live-icon-button Close X(17)).
div.live-message-compose > div.live-message-history[aria "Sent message
history"]: empty p.live-message-empty "You have not messaged this
agent."; else article per msg (p instruction, small "{sentTime} ·
{appliedLine}"), appliedLine (90-97): null→"waiting for the next
iteration"; revise→"replaced the goal at iteration N"; else "applied at
iteration N". Optimistic article.is-optimistic "sending…"/"waiting for
the next iteration". label[for=live-agent-message] "Message for the
agent"; textarea#live-agent-message[disabled !followingLive||!running,
maxLength 4000, rows 5, placeholder: "Return to live to message the
agent" / "The agent is not running" / "Steer the agent"]; warning p when
not following; p "The agent is not running." when stopped;
p.live-message-error[alert]; div.live-message-controls:
div.live-message-mode[group "Message effect"] two aria-pressed buttons
"Goal"(revise) / "Nudge"(guide) when following+running, else
span.live-message-disabled-mode "session stopped" | "inspecting sequence
{n}"; button.live-message-submit[aria "Send message", Send(15),
"Sending"/"Send", disabled !canSend||empty].
Delivery (24-78): POST 8792 /api/sessions/{id}/message
{request_id: crypto.randomUUID(), action, instruction}; fallback ONLY on
409+supervisor_mismatch → GET /api/v1/sessions/{id} no-store, read
source_cursor → POST /api/v1/sessions/{id}/commands {idempotency_key:
requestId, actor:"frozen-observatory", player_id, action, instruction,
expected_cursor}. Optimistic lifecycle: sending → waiting → dropped when
messages.length > baselineCount from later snapshot. Close animated
360ms (.is-closing). Escape closes; textarea autofocus.

### SessionStopDialog — already rebuilt in v3 (durable command). Frozen:
POST 8792 /api/sessions/{id}/stop, receipt {state:"stopped", mode}.

## Data map (frozen live/)

| # | Path | Method | Cadence | Consumer | Fields used |
|---|---|---|---|---|---|
| 1 | /api/sessions/{id}/snapshot | GET | 2s setTimeout chain (useLiveSnapshot 70,74) | shell + all panels | full Snapshot |
| 2 | /api/sessions/{id}/snapshot?through={n} | GET | same loop, parallel when pinned (52-55) | pinned view (snapshot) vs latestSnapshot | full Snapshot |
| 3 | /api/sessions | GET | 2s chain, stops on terminal (LiveShell 84-125) | shell/header/switcher | sessions: id, player_id, state, live, control_available, capture_status, updated_at, event_count; players |
| 4 | /api/ask | POST | on submit | AskDialog | answer, tier, missing, citations, detail |
| 5 | 8792 /api/sessions/{id}/message | POST | on send | MessageDialog | ok/status/text |
| 6 | /api/v1/sessions/{id} | GET | fallback only | MessageDialog | source_cursor |
| 7 | /api/v1/sessions/{id}/commands | POST | fallback only | MessageDialog | ok/status/text |
| 8 | 8792 /api/sessions/{id}/stop | POST | on confirm | StopDialog | detail on error |

Poll failure → "reconnecting" state, retry forever (useLiveSnapshot
62-70; LiveShell 115-124).

## Snapshot field → consumer (contracts.ts 602-653)

lifecycle → EvidenceRail pill (59-62), FrictionBlock; control_state →
FrictionBlock paused (102); following_live → EvidenceRail 57, Timeline
177-196, shell canSetGoal 173, MessageDialog; through_sequence →
Timeline 144,193, MessageDialog 236; latest_sequence → Timeline
34,137-148,247, FrictionBlock 97-100; objective/objective_initial/
objective_context → ObjectiveStrip 175-177, MessageDialog 234;
agent_thought → Map overlay 353-354,620,1100; agent_belief →
EvidenceRail 79-83; turn → Timeline 183; context_limit → liveEvidence
65-67; combat → Map 339,350,1059, EvidenceRail 69-74; combat_episode →
CombatPanel via Map 1096; friction → Timeline 70-84, FrictionBlock;
vitals → EvidenceRail meters 92-104; player_status → EvidenceRail 45;
cost_usd/current_turn_cost_usd/spend_cap_usd/spend_cap_scope →
liveEvidence 26-31; economics → EvidenceRail 233-234,260, Timeline 105,
liveEvidence 71-72; room_economics → Map 296; usage → EvidenceRail
235,256-257; milestones → Timeline 48,96; rooms → Timeline 95; world →
Map 153-163,278; timeline → Timeline 30,57; operator_messages →
MessageDialog; capture_gaps → FrictionBlock 113. Unused-in-live/:
session_id, gateway_session_id, player_id, character, agent_turn_active,
selected_at, suggested_action, recent_path, model, tools, iteration,
current_room, zone, position_confidence, position_method,
unattributed_room_economics, parse_miss_rate(top).

Route: /live?player=&session= (+ `through` URL param managed by shell
40-70).

