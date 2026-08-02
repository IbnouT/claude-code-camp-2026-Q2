import {
  useMemo,
} from "react";
import type {
  SessionEvidenceRecord,
  SessionInvestigation,
  Snapshot,
  WorldNode,
  WorldProjection,
} from "../contracts";
import { LiveMap } from "../live/LiveMap";
import styles from "./SessionMap.module.css";

type Props = {
  compact?: boolean;
  investigation: SessionInvestigation;
  selectedIndex: number;
};

export function SessionReplayMap({
  compact = false,
  investigation,
  selectedIndex,
}: Props) {
  const snapshot = useMemo(
    () => sessionSnapshot(investigation, selectedIndex),
    [investigation, selectedIndex],
  );
  return (
    <section
      className={[
        styles["session-replay-map"],
        compact ? styles["is-compact"] : "",
      ].filter(Boolean).join(" ")}
      aria-label="Session spatial replay"
    >
      <LiveMap
        controls="session"
        identity={{
          playerId: investigation.player_id,
          sessionId: investigation.run.id,
        }}
        snapshot={snapshot}
        state="ready"
      />
    </section>
  );
}

function sessionSnapshot(
  investigation: SessionInvestigation,
  selectedIndex: number,
): Snapshot {
  const records = investigation.records;
  const throughIndex = selectedIndex < 0 ? records.length - 1 : selectedIndex;
  const prefix = records.slice(0, throughIndex + 1);
  const gatewayPrefix = prefix.filter((record) => record.source === "gateway");
  const throughSequence = Math.max(
    ...gatewayPrefix.map((record) => record.sequence),
    0,
  );
  const latestSequence = Math.max(
    ...records.filter((record) => record.source === "gateway")
      .map((record) => record.sequence),
    0,
  );
  const positions = prefix.filter(
    (record) => record.kind === "position" && record.room_id !== null,
  );
  const currentPosition = positions.at(-1) ?? null;
  const currentRoomId = currentPosition?.room_id ?? null;
  const world = prefixWorld(
    investigation.world,
    throughSequence,
    currentRoomId,
    positions,
  );
  const selected = prefix.at(-1) ?? null;
  const latestPlan = [...prefix].reverse().find(
    (record) => record.kind === "plan" || record.kind === "reasoning",
  );
  const goals = prefix.filter((record) => record.kind === "goal_revision");
  const activeGoal = goals.at(-1) ?? null;
  const initialGoal = goals[0] ?? null;
  const operatorMessages = prefix
    .filter((record) => (
      record.kind === "goal_revision" || record.kind === "guidance"
    ))
    .map((record) => ({
      action: record.kind === "goal_revision" ? "revise" as const : "guide" as const,
      instruction: (
        typeof record.fields.instruction === "string"
          ? record.fields.instruction
          : record.preview
      ),
      sent_at: (
        typeof record.fields.sent_at === "string"
          ? record.fields.sent_at
          : record.at
      ),
      applied_iteration: record.iteration,
    }));
  const objective = activeGoal?.preview || investigation.objective;

  return {
    session_id: investigation.run.id,
    gateway_session_id: investigation.gateway_session_id ?? "",
    player_id: investigation.player_id,
    character: investigation.player_id,
    lifecycle: investigation.run.success ? "completed" : "stopped",
    control_state: "stopped",
    agent_turn_active: false,
    following_live: false,
    through_sequence: throughSequence,
    latest_sequence: latestSequence,
    selected_at: selected === null ? null : Date.parse(selected.at) / 1_000,
    objective,
    objective_initial: initialGoal === null ? null : {
      title: initialGoal.preview,
      clue: null,
      source_kind: "operator",
      revision: 1,
      evidence: initialGoal.id,
    },
    objective_context: activeGoal === null ? null : {
      title: activeGoal.preview,
      clue: null,
      source_kind: "operator",
      revision: goals.length,
      evidence: activeGoal.id,
    },
    suggested_action: null,
    recent_path: null,
    agent_thought: latestPlan === undefined ? null : {
      text: latestPlan.preview,
      phase: latestPlan.kind === "reasoning" ? "reasoning" : "plan",
      observed_at: latestPlan.at,
      line: latestPlan.sequence,
      evidence: latestPlan.id,
    },
    agent_belief: null,
    model: investigation.model,
    tools: [],
    turn: selected?.turn ?? null,
    iteration: selected?.iteration ?? 0,
    context_limit: null,
    current_room: world.current_title,
    zone: null,
    position_confidence: world.current_confidence,
    position_method: (
      typeof currentPosition?.fields.method === "string"
        ? currentPosition.fields.method
        : null
    ),
    combat: false,
    combat_episode: null,
    friction: {
      kind: null,
      repeated_command: null,
      repeated_count: 0,
      distinct_places: world.nodes.length,
      iterations: selected?.iteration ?? 0,
      new_places: world.nodes.length,
      window_iterations: 0,
      iterations_since_new_place: null,
      threshold: null,
      evidence: [],
    },
    vitals: {},
    player_status: {
      fields: {},
      capture_gaps: investigation.capture_gaps,
    },
    cost_usd: prefix.reduce((total, record) => total + record.cost_usd, 0),
    current_turn_cost_usd: prefix
      .filter((record) => record.turn === selected?.turn)
      .reduce((total, record) => total + record.cost_usd, 0),
    spend_cap_usd: null,
    spend_cap_scope: null,
    economics: [],
    room_economics: [],
    unattributed_room_economics: null,
    usage: {},
    milestones: [],
    parse_miss_rate: world.parse_miss_rate,
    rooms: world.nodes.map((node) => ({
      id: node.id,
      place: node.place,
      title: node.title,
      exits: node.exits,
      first_sequence: node.first_seq,
      last_sequence: node.last_seq,
      visits: node.visits,
      state: node.id === currentRoomId ? "current" : "observed",
      confidence: node.confidence,
    })),
    world,
    timeline: [],
    operator_messages: operatorMessages,
    capture_gaps: investigation.capture_gaps,
  };
}

function prefixWorld(
  world: WorldProjection,
  throughSequence: number,
  currentRoomId: string | null,
  positions: SessionEvidenceRecord[],
): WorldProjection {
  const visitCounts = new Map<string, number>();
  for (const position of positions) {
    if (position.room_id === null) continue;
    visitCounts.set(position.room_id, (visitCounts.get(position.room_id) ?? 0) + 1);
  }
  const nodes = world.nodes
    .filter((node) => node.first_seq <= throughSequence)
    .map((node) => prefixNode(
      node,
      throughSequence,
      currentRoomId,
      visitCounts.get(node.id) ?? 0,
    ));
  const nodeIds = new Set(nodes.map((node) => node.id));
  const edges = world.edges
    .filter((edge) => (
      nodeIds.has(edge.source)
      && nodeIds.has(edge.target)
      && edge.evidence.some((sequence) => sequence <= throughSequence)
    ))
    .map((edge) => ({
      ...edge,
      evidence: edge.evidence.filter((sequence) => sequence <= throughSequence),
    }));
  const current = nodes.find((node) => node.id === currentRoomId) ?? null;
  return {
    ...world,
    nodes,
    edges,
    current_title: current?.title ?? null,
    current_confidence: current?.confidence ?? "unknown",
    frontier: world.frontier.filter((item) => (
      nodeIds.has(item.source)
      && item.evidence.some((sequence) => sequence <= throughSequence)
    )),
    objective_beacons: world.objective_beacons.filter(
      (beacon) => nodeIds.has(beacon.node_id),
    ),
    candidates: world.candidates.filter((candidate) => nodeIds.has(candidate)),
    candidate_details: world.candidate_details.filter(
      (candidate) => nodeIds.has(candidate.node_id),
    ),
    parse_misses: world.parse_misses.filter(
      (miss) => miss.sequence <= throughSequence,
    ),
    unknown_positions: positions.filter((position) => (
      position.fields.confidence === "unknown"
      || position.fields.confidence === "ambiguous"
    )).length,
  };
}

function prefixNode(
  node: WorldNode,
  throughSequence: number,
  currentRoomId: string | null,
  visits: number,
): WorldNode {
  const evidence = node.evidence.filter((sequence) => sequence <= throughSequence);
  const mobSightings = node.mob_sightings
    .filter((sighting) => sighting.first_seq <= throughSequence)
    .map((sighting) => ({
      ...sighting,
      evidence: sighting.evidence.filter((sequence) => sequence <= throughSequence),
      count: sighting.evidence.filter((sequence) => sequence <= throughSequence).length,
      last_seq: Math.min(sighting.last_seq, throughSequence),
    }));
  const objectSightings = node.object_sightings
    .filter((sighting) => sighting.first_seq <= throughSequence)
    .map((sighting) => ({
      ...sighting,
      evidence: sighting.evidence.filter((sequence) => sequence <= throughSequence),
      count: sighting.evidence.filter((sequence) => sequence <= throughSequence).length,
      last_seq: Math.min(sighting.last_seq, throughSequence),
    }));
  return {
    ...node,
    description: (
      node.description !== null
      && node.description.evidence.some((sequence) => sequence <= throughSequence)
    ) ? {
        ...node.description,
        evidence: node.description.evidence.filter(
          (sequence) => sequence <= throughSequence,
        ),
      }
      : null,
    mobs: mobSightings.map((sighting) => sighting.name),
    objects: objectSightings.map((sighting) => sighting.name),
    mob_sightings: mobSightings,
    object_sightings: objectSightings,
    evidence,
    visits,
    last_seq: Math.min(node.last_seq, throughSequence),
    state: node.id === currentRoomId ? "current" : "observed",
  };
}
