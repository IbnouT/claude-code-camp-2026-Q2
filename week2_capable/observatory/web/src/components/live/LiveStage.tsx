import type { LiveAgentExcerpt, LiveSnapshot } from "../../data/liveContracts";
import {
  FOCUS_RADIUS,
  frontierVector,
  graphDistances,
  liveMapLayout,
  type LiveMapNode,
  type MapMode,
} from "./liveCockpitModel";

export type CameraMode = "follow" | "center";

type Props = {
  snapshot: LiveSnapshot;
  mode: MapMode;
  camera: CameraMode;
  zoom: number;
  expanded: ReadonlySet<string>;
  selectedRoomId: string | null;
  thought: LiveAgentExcerpt | null;
  onToggleExpand: (boundaryId: string) => void;
  onSelectRoom: (roomId: string | null) => void;
  onOpenEvidence: (node: LiveMapNode) => void;
};

/** Visual vocabulary transcribed from live_cockpit.html, map_modes.html and
 *  map_detail.html. The thought callout anchors ABOVE the current room so the
 *  player stays visible; camera follows the agent or centers the selection;
 *  clicking a room opens its detail popover (absent fields stay absent). */
export function LiveStage({
  snapshot,
  mode,
  camera,
  zoom,
  expanded,
  selectedRoomId,
  thought,
  onToggleExpand,
  onSelectRoom,
  onOpenEvidence,
}: Props) {
  const { nodes, edges, conflicts } = liveMapLayout(snapshot);
  const conflictNodeIds = new Set(conflicts.map((item) => item.node_id));
  const frontier = snapshot.world.frontier;
  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  const currentTitle = snapshot.current_room;

  const isCurrent = (node: LiveMapNode) =>
    node.state === "current"
    || (currentTitle !== null && node.title === currentTitle);

  const anchor = nodes.find((node) => isCurrent(node)) ?? nodes.at(0) ?? null;
  const selected = selectedRoomId !== null
    ? nodeById.get(selectedRoomId) ?? null
    : null;
  const distances = graphDistances(snapshot, anchor?.id ?? null);
  const hops = (id: string): number => distances.get(id) ?? 99;

  /* ----- focus mode visibility ----- */
  const focusVisible = new Set<string>();
  if (mode === "focus") {
    for (const node of nodes) {
      if (hops(node.id) <= FOCUS_RADIUS) focusVisible.add(node.id);
    }
    for (const boundaryId of expanded) {
      for (const edge of edges) {
        if (edge.source === boundaryId && hops(edge.target) > FOCUS_RADIUS) {
          focusVisible.add(edge.target);
        }
        if (edge.target === boundaryId && hops(edge.source) > FOCUS_RADIUS) {
          focusVisible.add(edge.source);
        }
      }
    }
  }
  const visible = (id: string): boolean =>
    mode !== "focus" || focusVisible.has(id);

  /* boundary expanders */
  const expanders: { node: LiveMapNode; count: number }[] = [];
  if (mode === "focus" && anchor) {
    const hiddenCount = new Map<string, number>();
    for (const edge of edges) {
      const nearFar: [string, string] | null =
        hops(edge.source) === FOCUS_RADIUS && !visible(edge.target)
          ? [edge.source, edge.target]
          : hops(edge.target) === FOCUS_RADIUS && !visible(edge.source)
            ? [edge.target, edge.source]
            : null;
      if (nearFar) {
        hiddenCount.set(nearFar[0], (hiddenCount.get(nearFar[0]) ?? 0) + 1);
      }
    }
    for (const [id, count] of hiddenCount) {
      const node = nodeById.get(id);
      if (node) expanders.push({ node, count });
    }
  }

  /* ----- camera: follow the agent, center the selection, or (Grow) frame
     the complete graph ----- */
  /* The camera centre sits below the stage-control band so framed content
     never rises underneath the chips and toolbars. */
  const CENTER_X = 450;
  const CENTER_Y = 335;
  const target = camera === "center" && selected ? selected : anchor;
  const tx = (target?.x ?? 432) + 18;
  const ty = (target?.y ?? 292) + 18;
  const centerTransform = `translate(${CENTER_X - tx},${CENTER_Y - ty})`;
  /* Grow frames the COMPLETE graph: room nodes AND frontier ghost extents. */
  const ghostCenters = frontier.flatMap((exit) => {
    const source = nodeById.get(exit.source);
    if (!source) return [];
    const [dx, dy] = frontierVector(exit.direction);
    return [{ x: source.x + dx + 18, y: source.y + dy + 18 }];
  });
  const xs = [
    ...nodes.map((node) => node.x + 18),
    ...ghostCenters.map((ghost) => ghost.x),
  ];
  const ys = [
    ...nodes.map((node) => node.y + 18),
    ...ghostCenters.map((ghost) => ghost.y),
  ];
  const fit = xs.length === 0
    ? { scale: 1, cx: CENTER_X, cy: CENTER_Y }
    : (() => {
      const minX = Math.min(...xs) - 60;
      const maxX = Math.max(...xs) + 60;
      const minY = Math.min(...ys) - 60;
      const maxY = Math.max(...ys) + 70;
      return {
        scale: Math.min(1.2, 860 / (maxX - minX), 540 / (maxY - minY)),
        cx: (minX + maxX) / 2,
        cy: (minY + maxY) / 2,
      };
    })();

  /* ----- lantern mode ----- */
  const LANTERN_R = 280;
  const lanternOpacity = (x: number, y: number): number => {
    if (!anchor) return 1;
    const dx = x - (anchor.x + 18);
    const dy = y - (anchor.y + 18);
    return Math.max(0, 1 - Math.sqrt(dx * dx + dy * dy) / LANTERN_R);
  };
  const nodeOpacity = (node: LiveMapNode): number =>
    mode === "lantern" ? lanternOpacity(node.x + 18, node.y + 18) : 1;

  const ax = (anchor?.x ?? 432) + 18;
  const ay = (anchor?.y ?? 292) + 18;

  const userZoom = `translate(${CENTER_X},${CENTER_Y}) scale(${zoom}) translate(${-CENTER_X},${-CENTER_Y})`;
  const groupTransform = mode === "lantern"
    ? `${userZoom} ${centerTransform} translate(${ax},${ay}) scale(1.3) translate(${-ax},${-ay})`
    : mode === "grow"
      ? `translate(${CENTER_X},${CENTER_Y}) scale(${fit.scale * zoom}) translate(${-fit.cx},${-fit.cy})`
      : `${userZoom} ${centerTransform}`;

  /* Screen-space projection of a graph point through the active mode
     transform. The thought callout and the room popover render OUTSIDE the
     transformed group (mock behavior: absolutely positioned, unscaled) and
     clamp in viewBox space, so they stay inside the visible stage in every
     mode and at every zoom. */
  const project = (px: number, py: number): { x: number; y: number } => {
    if (mode === "grow") {
      const scale = fit.scale * zoom;
      return {
        x: CENTER_X + scale * (px - fit.cx),
        y: CENTER_Y + scale * (py - fit.cy),
      };
    }
    let x = px;
    let y = py;
    if (mode === "lantern") {
      x = ax + 1.3 * (x - ax);
      y = ay + 1.3 * (y - ay);
    }
    x += CENTER_X - tx;
    y += CENTER_Y - ty;
    return {
      x: CENTER_X + zoom * (x - CENTER_X),
      y: CENTER_Y + zoom * (y - CENTER_Y),
    };
  };
  const anchorScreen = anchor ? project(ax, ay) : null;
  const selectedScreen = selected
    ? project(selected.x + 18, selected.y + 18)
    : null;
  /* Overlay-safe top band: the stage chips and toolbars occupy roughly the
     first 50 viewBox units — unscaled overlays never enter it. */
  const OVERLAY_TOP = 56;
  /* Final overlay geometry of each beacon label — the SAME rectangles are
     rendered and used for thought-collision avoidance. */
  const BEACON_HALF = 110;
  const beaconLabels = snapshot.world.objective_beacons.flatMap((beacon) => {
    const node = nodeById.get(beacon.node_id);
    if (!node || !visible(node.id)) return [];
    const point = project(node.x + 18, node.y + 18);
    const cx = Math.min(892 - BEACON_HALF, Math.max(8 + BEACON_HALF, point.x));
    const above = point.y - 30;
    const baseline = above < OVERLAY_TOP + 10 ? point.y + 42 : above;
    return [{
      id: beacon.node_id,
      label: beacon.label,
      cx,
      baseline,
      left: cx - BEACON_HALF,
      right: cx + BEACON_HALF,
      top: baseline - 12,
      bottom: baseline + 4,
    }];
  });

  return (
    <svg
      aria-label="Learned world map"
      className="map"
      preserveAspectRatio="xMidYMid meet"
      role="group"
      viewBox="0 0 900 620"
    >
      <defs>
        <radialGradient cx="50%" cy="50%" id="live-curglow" r="50%">
          <stop offset="0%" stopColor="#4fd6c9" stopOpacity=".55" />
          <stop offset="100%" stopColor="#4fd6c9" stopOpacity="0" />
        </radialGradient>
        {mode === "lantern" ? (
          <radialGradient
            cx={ax}
            cy={ay}
            gradientUnits="userSpaceOnUse"
            id="live-lamp"
            r={LANTERN_R}
          >
            <stop offset="0%" stopColor="#212d40" />
            <stop offset="45%" stopColor="#131b27" />
            <stop offset="80%" stopColor="#080b11" />
            <stop offset="100%" stopColor="#05070a" />
          </radialGradient>
        ) : null}
      </defs>

      {mode === "lantern" ? (
        <rect fill="#05070a" height="620" width="900" x="0" y="0" />
      ) : null}

      <g transform={groupTransform}>
        {mode === "lantern" ? (
          <circle cx={ax} cy={ay} fill="url(#live-lamp)" r={LANTERN_R} />
        ) : null}

        {/* recent-path highlight from the typed contiguous tail */}
        <g fill="none">
          {(snapshot.recent_path?.edge_ids ?? [])
            .map((edgeId) => edges.find((edge) => edge.id === edgeId))
            .filter((edge): edge is NonNullable<typeof edge> =>
              edge !== undefined
              && visible(edge.source)
              && visible(edge.target))
            .map((edge) => (
              <path
                d={`M${edge.sourceNode.x + 18},${edge.sourceNode.y + 18} L${edge.targetNode.x + 18},${edge.targetNode.y + 18}`}
                key={`recent-${edge.id}`}
                stroke="#2f6b6f"
                strokeDasharray="2 6"
                strokeWidth="2.5"
              />
            ))}
        </g>

        <g fill="none" strokeWidth="2">
          {edges.map((edge) => {
            if (!visible(edge.source) || !visible(edge.target)) return null;
            const x1 = edge.sourceNode.x + 18;
            const y1 = edge.sourceNode.y + 18;
            const x2 = edge.targetNode.x + 18;
            const y2 = edge.targetNode.y + 18;
            const opacity = mode === "lantern"
              ? Math.min(lanternOpacity(x1, y1), lanternOpacity(x2, y2)) * 0.9
              : 1;
            if (opacity <= 0.06) return null;
            return (
              <g key={edge.id} opacity={opacity}>
                <path
                  d={`M${x1},${y1} L${x2},${y2}`}
                  stroke={mode === "lantern" ? "#48627e" : "#243449"}
                  strokeDasharray={edge.kind === "planar" ? undefined : "4 5"}
                  strokeWidth={mode === "lantern" ? 1.4 : 2}
                />
                {edge.label === null ? null : (
                  <text
                    className="rlabel"
                    style={{ fill: "#4a5c74" }}
                    textAnchor="middle"
                    x={(x1 + x2) / 2}
                    y={(y1 + y2) / 2 - 5}
                  >
                    {edge.label}
                  </text>
                )}
              </g>
            );
          })}
        </g>

        {/* frontier ghosts */}
        <g>
          {frontier.map((exit) => {
            const source = nodeById.get(exit.source);
            if (!source || !visible(exit.source)) return null;
            const [dx, dy] = frontierVector(exit.direction);
            const gx = source.x + dx;
            const gy = source.y + dy;
            const opacity = mode === "lantern"
              ? lanternOpacity(gx + 18, gy + 18)
              : 1;
            if (opacity <= 0.06) return null;
            return (
              <g key={exit.id} opacity={opacity}>
                <path
                  d={`M${source.x + 18},${source.y + 18} L${gx + 18},${gy + 18}`}
                  fill="none"
                  stroke="#1b2636"
                  strokeDasharray="3 6"
                  strokeWidth="2"
                />
                <rect
                  fill="none"
                  height="36"
                  rx="7"
                  stroke="#26374b"
                  strokeDasharray="3 4"
                  width="36"
                  x={gx}
                  y={gy}
                />
                <text
                  className="rlabel"
                  style={{ fill: "#4a5c74" }}
                  textAnchor="middle"
                  x={gx + 18}
                  y={gy - 10}
                >
                  ?
                </text>
              </g>
            );
          })}
        </g>

        <g>
          {nodes.map((node) => {
            if (!visible(node.id)) return null;
            const opacity = nodeOpacity(node);
            if (opacity <= 0.06) return null;
            const current = isCurrent(node);
            const isSelected = selected?.id === node.id;
            const candidate = node.state === "candidate";
            const combatHere = current && snapshot.combat;
            const flagged = node.collision || conflictNodeIds.has(node.id);
            const cx = node.x + 18;
            const showLabel = mode !== "lantern" || opacity > 0.45;
            return (
              <g
                aria-label={`Room ${node.title}: open detail`}
                className="roomnode"
                key={node.id}
                opacity={opacity}
                role="button"
                style={{ cursor: "pointer" }}
                tabIndex={0}
                onClick={() =>
                  onSelectRoom(isSelected ? null : node.id)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelectRoom(isSelected ? null : node.id);
                  }
                }}
              >
                {current && mode !== "lantern" ? (
                  <circle cx={cx} cy={node.y + 18} fill="url(#live-curglow)" r="46" />
                ) : null}
                {isSelected && !current ? (
                  <circle
                    cx={cx}
                    cy={node.y + 18}
                    fill="none"
                    opacity=".8"
                    r="30"
                    stroke="#5db4ff"
                    strokeDasharray="3 3"
                    strokeWidth="1.5"
                  />
                ) : null}
                <rect
                  fill={
                    combatHere
                      ? "#3a1620"
                      : current
                        ? "#12333a"
                        : candidate
                          ? "none"
                          : "#1c3350"
                  }
                  height="36"
                  rx="7"
                  stroke={
                    combatHere
                      ? "#ff5d6c"
                      : current
                        ? "#2f6b6f"
                        : isSelected
                          ? "#5db4ff"
                          : candidate
                            ? "#6a5a2a"
                            : "#2f5680"
                  }
                  strokeDasharray={candidate ? "4 3" : undefined}
                  strokeWidth={current || isSelected ? 2 : 1}
                  width="36"
                  x={node.x}
                  y={node.y}
                />
                {showLabel ? (
                  <text
                    className={current
                      ? "rlabel cur"
                      : isSelected
                        ? "rlabel sel"
                        : "rlabel"}
                    style={candidate ? { fill: "#b79a4a" } : undefined}
                    textAnchor="middle"
                    x={cx}
                    y={current ? node.y - 12 : node.y + 54}
                  >
                    {node.title}
                  </text>
                ) : null}
                {node.visits > 1 ? (
                  <g>
                    <circle
                      cx={node.x + 36}
                      cy={node.y}
                      fill="#151d26"
                      r="10"
                      stroke="#2f5680"
                    />
                    <text
                      fill="#8493a1"
                      fontSize="9"
                      textAnchor="middle"
                      x={node.x + 36}
                      y={node.y + 3.5}
                    >
                      ×{node.visits}
                    </text>
                  </g>
                ) : null}
                {flagged ? (
                  <text
                    aria-label="Layout constraint conflict"
                    style={{ fill: "#eac06a", fontSize: 12, fontWeight: 700 }}
                    textAnchor="middle"
                    x={node.x - 6}
                    y={node.y + 4}
                  >
                    ⚠
                  </text>
                ) : null}
                {node.mobs.length > 0 ? (
                  <circle
                    cx={node.x + 32}
                    cy={node.y + 6}
                    fill="#ff5d6c"
                    r="5"
                    stroke="#140b10"
                    strokeWidth="1.5"
                  />
                ) : null}
                {node.objects.length > 0 ? (
                  <circle
                    cx={node.x + 4}
                    cy={node.y + 6}
                    fill="#f5c463"
                    r="4"
                    stroke="#0b0f17"
                    strokeWidth="1.3"
                  />
                ) : null}
              </g>
            );
          })}
        </g>

        {/* focus-mode boundary expanders */}
        {mode === "focus" && anchor ? (
          <g>
            {expanders.map(({ node, count }) => {
              const angle = Math.atan2(node.y - anchor.y, node.x - anchor.x);
              const ex = node.x + 18 + Math.cos(angle) * 52;
              const ey = node.y + 18 + Math.sin(angle) * 52;
              const open = expanded.has(node.id);
              return (
                <g
                  aria-label={open
                    ? `Collapse rooms beyond ${node.title}`
                    : `Show ${count} hidden rooms beyond ${node.title}`}
                  className="expander"
                  key={`expand-${node.id}`}
                  role="button"
                  style={{ cursor: "pointer" }}
                  tabIndex={0}
                  onClick={() => onToggleExpand(node.id)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      onToggleExpand(node.id);
                    }
                  }}
                >
                  <path
                    d={`M${node.x + 18},${node.y + 18} L${ex},${ey}`}
                    fill="none"
                    stroke="#2f5680"
                    strokeDasharray="2 4"
                    strokeWidth="1.5"
                  />
                  <circle
                    cx={ex}
                    cy={ey}
                    fill="#111820"
                    r="13"
                    stroke="#2f5680"
                    strokeDasharray="3 3"
                  />
                  <text
                    fill="#8fb4e0"
                    fontSize="10"
                    textAnchor="middle"
                    x={ex}
                    y={ey + 3.5}
                  >
                    {open ? "−" : `+${count}`}
                  </text>
                </g>
              );
            })}
          </g>
        ) : null}

        {/* objective beacons: known-location evidence (map_detail) */}
        <g>
          {snapshot.world.objective_beacons.map((beacon) => {
            const node = nodeById.get(beacon.node_id);
            if (!node || !visible(node.id)) return null;
            return (
              <g key={`beacon-${beacon.node_id}`}>
                <circle
                  cx={node.x + 18}
                  cy={node.y + 18}
                  fill="#5db4ff"
                  opacity="0.16"
                  r="34"
                />
                <rect
                  fill="#10243a"
                  height="36"
                  rx="7"
                  stroke="#5db4ff"
                  strokeWidth="2.5"
                  width="36"
                  x={node.x}
                  y={node.y}
                />
                <text
                  fill="#5db4ff"
                  fontSize="14"
                  textAnchor="middle"
                  x={node.x + 18}
                  y={node.y + 23}
                >
                  ◎
                </text>
              </g>
            );
          })}
        </g>

        {/* player-status glyphs on the agent marker (player_status.html):
            only observed abnormal states draw attention */}
        {anchor ? (
          <g>
            {(() => {
              const fields = snapshot.player_status.fields;
              const glyphs: string[] = [];
              const posture = fields.posture?.value;
              if (typeof posture === "string" && posture.toLowerCase() !== "standing") {
                const map: Record<string, string> = {
                  resting: "🛌",
                  sitting: "🪑",
                  sleeping: "💤",
                  fighting: "⚔️",
                  incapacitated: "🛌",
                };
                glyphs.push(map[posture.toLowerCase()] ?? "🧍");
              }
              for (const [key, glyph] of [
                ["hungry", "🍖"],
                ["thirsty", "💧"],
                ["poisoned", "☠"],
              ] as const) {
                if (fields[key]?.value === true) glyphs.push(glyph);
              }
              const gold = fields.gold?.value;
              return (
                <>
                  {glyphs.map((glyph, index) => (
                    <g key={`glyph-${glyph}`}>
                      <rect
                        fill="#0c141bcc"
                        height="22"
                        rx="7"
                        stroke="#1d2833"
                        width="22"
                        x={ax - 33 + index * 26}
                        y={ay - 52}
                      />
                      <text
                        fontSize="12"
                        textAnchor="middle"
                        x={ax - 22 + index * 26}
                        y={ay - 36}
                      >
                        {glyph}
                      </text>
                    </g>
                  ))}
                  {typeof gold === "number" ? (
                    <text
                      fill="#eac06a"
                      fontSize="11"
                      textAnchor="middle"
                      x={ax}
                      y={ay + 48}
                    >
                      🪙 {gold.toLocaleString()}
                    </text>
                  ) : null}
                </>
              );
            })()}
          </g>
        ) : null}

      </g>

      {/* objective beacon labels: unscaled overlay, projected and clamped
          below the control band (flips under the beacon when the above
          slot would enter it) */}
      {beaconLabels.map((entry) => (
        <text
          className="rlabel"
          key={`beacon-label-${entry.id}`}
          style={{ fill: "#5db4ff" }}
          textAnchor="middle"
          x={entry.cx}
          y={entry.baseline}
        >
          ◎ {entry.label}: known location
        </text>
      ))}

      {/* agent thought: anchored ABOVE the current room so the player stays
          visible (mock behavior); unscaled overlay, projected through the
          mode transform and clamped to the viewBox with a below-room
          fallback. */}
      {thought && anchor && anchorScreen ? (
        (() => {
          /* ABOVE the current room always (Ibnou's rule: the player must
             stay unambiguous). When the above slot would enter the
             control band, move BESIDE the room — never below, never
             covering it. If the box would cover a projected objective
             beacon, flip to the room's other side. */
          const above = anchorScreen.y - 190;
          const fitsAbove = above >= OVERLAY_TOP;
          let x = fitsAbove
            ? Math.min(900 - 268, Math.max(8, anchorScreen.x - 42))
            : anchorScreen.x + 60 + 260 > 892
              ? Math.max(8, anchorScreen.x - 60 - 260)
              : anchorScreen.x + 60;
          const y = fitsAbove
            ? Math.min(620 - 158, above)
            : Math.max(OVERLAY_TOP, Math.min(620 - 158, anchorScreen.y - 75));
          const covers = (bx: number): boolean =>
            beaconLabels.some((entry) =>
              entry.right > bx - 8 && entry.left < bx + 268
              && entry.bottom > y - 8 && entry.top < y + 158);
          if (covers(x)) {
            const flipped = x <= anchorScreen.x - 42
              ? Math.min(900 - 268, anchorScreen.x + 60)
              : Math.max(8, anchorScreen.x - 60 - 260);
            if (!covers(flipped)) x = flipped;
          }
          return (
            <foreignObject height="150" width="260" x={x} y={y}>
              <div className="thought anchored">
                <small>
                  Agent · {thought.phase === "reasoning"
                    ? "thinking"
                    : thought.phase === "plan"
                      ? "planning"
                      : "acting"}
                </small>
                {thought.text}
              </div>
            </foreignObject>
          );
        })()
      ) : null}

      {/* room detail popover (map_detail.html), anchored beside selection;
          unscaled overlay projected through the mode transform */}
      {selected && visible(selected.id) && selectedScreen ? (
        (() => {
          /* beside the selected room, on the side pointing AWAY from the
             graph center, vertically centred on the room — the map's
             central mass stays visible (map_detail geometry) */
          const x = selectedScreen.x >= 450
            ? Math.min(892 - 310, selectedScreen.x + 46)
            : Math.max(8, selectedScreen.x - 46 - 310);
          const y = Math.min(
            620 - 448,
            Math.max(OVERLAY_TOP, selectedScreen.y - 220),
          );
          return (
            <foreignObject height="440" width="310" x={x} y={y}>
            <div className="roompop">
              <div className="ph2">
                <div className="nm">
                  {selected.title}
                  {selected.atlas
                    ? <span className="tagv">{selected.atlas.sector}</span>
                    : null}
                </div>
                <div className="mt">
                  <span>passed ×{selected.visits}</span>
                  <span>
                    first s{selected.first_seq} · last s{selected.last_seq}
                  </span>
                </div>
              </div>
              <div className="pb">
                {selected.description ? (
                  <div className="desc">{selected.description.text}</div>
                ) : null}
                <h6>Exits</h6>
                <div className="exits">
                  {selected.exits.length === 0 && frontier.every(
                    (exit) => exit.source !== selected.id,
                  ) ? (
                    <span className="dead">none observed</span>
                  ) : (
                    <>
                      {selected.exits.map((exit) => (
                        <span key={exit}>{exit}</span>
                      ))}
                      {frontier
                        .filter((exit) => exit.source === selected.id)
                        .map((exit) => (
                          <span className="dead" key={`unconfirmed-${exit.id}`}>
                            {exit.direction} ?
                          </span>
                        ))}
                    </>
                  )}
                </div>
                <h6>Seen here</h6>
                <div className="list">
                  {selected.mob_sightings.length === 0
                    ? <div className="li dead">no mob sightings retained</div>
                    : selected.mob_sightings.map((sighting) => (
                      <div className="li" key={`mob-${sighting.name}`}>
                        <span className="ic" style={{ color: "#ff8178" }}>☠</span>
                        {sighting.name}
                        <span className="ct">×{sighting.count}</span>
                      </div>
                    ))}
                </div>
                <h6>Objects known here</h6>
                <div className="list">
                  {selected.object_sightings.length === 0
                    ? <div className="li dead">none retained</div>
                    : selected.object_sightings.map((sighting) => (
                      <div className="li" key={`obj-${sighting.name}`}>
                        <span className="ic" style={{ color: "#eac06a" }}>⚷</span>
                        {sighting.name}
                        <span className="ct">
                          ×{sighting.count} · last s{sighting.last_seq}
                        </span>
                      </div>
                    ))}
                </div>
                <div className="stats2">
                  <div className="st2">
                    <div className="k">Passed</div>
                    <div className="v">{selected.visits}×</div>
                  </div>
                  {(() => {
                    const spend = snapshot.room_economics.find(
                      (entry) => entry.node_id === selected.id,
                    );
                    return spend === undefined ? null : (
                      <div className="st2">
                        <div className="k">Spent here</div>
                        <div className="v">${spend.cost_usd.toFixed(3)}</div>
                      </div>
                    );
                  })()}
                </div>
                <button
                  className="more"
                  type="button"
                  onClick={() => onOpenEvidence(selected)}
                >
                  Open full evidence →
                </button>
              </div>
            </div>
            </foreignObject>
          );
        })()
      ) : null}
    </svg>
  );
}
