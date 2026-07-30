import type { Page } from "@playwright/test";

export const knowledge = {
  version: 1,
  player_id: "poucet-recorded",
  state: "ready",
  source: "per-player durable knowledge",
  cdc_cursor: 14,
  metrics: [
    {
      id: "assertions",
      label: "Assertions",
      value: 7,
      detail: "Seven retained claims across learned and observer layers",
    },
    {
      id: "conflicts",
      label: "Unresolved",
      value: 2,
      detail: "One fact has two active candidates",
    },
  ],
  assertions: [
    assertion("room-title", "room:temple", "title", "Temple of Midgaard"),
    assertion("room-zone", "room:temple", "zone", "Midgaard"),
    assertion("room-exit", "room:temple", "exit.north", "White Square"),
    assertion(
      "entity-location-a",
      "entity:massive-minotaur",
      "sighting.location",
      "Newbie Entrance",
      "ambiguous",
      "minotaur-location",
    ),
    assertion(
      "entity-location-b",
      "entity:massive-minotaur",
      "sighting.location",
      "White Square",
      "ambiguous",
      "minotaur-location",
    ),
    assertion("player-hit", "player:poucet", "vitals.hit", 84),
    {
      ...assertion(
        "truth-minotaur",
        "entity:massive-minotaur",
        "sighting.location",
        "Courtyard",
        "high",
        "minotaur-location",
      ),
      layer: "observer_truth",
    },
  ],
  changes: [{
    change_seq: 14,
    transaction_id: "tx-14",
    operation: "supersede",
    entity_type: "assertion",
    entity_id: "entity-location-b",
    before_digest: "before",
    after_digest: "after",
    session_id: "gateway-j2",
    source_seq: 2,
    at: 1_775_000_000,
  }],
  snapshots: [{
    snapshot_id: "snapshot-verified",
    cdc_high_water: 14,
    reason: "before route experiment",
    digest: "a".repeat(64),
    generation: 2,
    at: 1_775_000_100,
    verified: true,
  }],
  recoveries: [{
    operation: "restore",
    operation_id: "restore-1",
    snapshot_id: "snapshot-verified",
    reason: "replay known baseline",
    assertions: 6,
    transaction_id: "tx-restore",
    at: 1_775_000_200,
  }],
  capture_gaps: [],
};

export async function mockKnowledge(page: Page) {
  await page.route("**/api/players/poucet-recorded/knowledge", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(knowledge),
    });
  });
}

function assertion(
  assertion_id: string,
  subject: string,
  predicate: string,
  value: unknown,
  confidence = "high",
  conflict_group: string | null = null,
) {
  return {
    assertion_id,
    fact_id: `${subject}:${predicate}`,
    subject,
    predicate,
    value,
    layer: "learned",
    status: "active",
    confidence,
    current: true,
    conflict_group,
    evidence: [{
      session_id: "gateway-j2",
      source_seq: 2,
      wire_digest: `wire-${assertion_id}`,
      parser_version: "knowledge-1",
      method: "structured-observation",
      observed_at: 1_775_000_000,
    }],
  };
}
