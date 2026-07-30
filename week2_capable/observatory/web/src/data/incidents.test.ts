import { expect, test } from "vitest";
import { readIncident } from "./incidents";

const payload = {
  generated_at: "2026-07-29T18:10:00Z",
  title: "J2 incident",
  source_versions: { capsule: "2" },
  player_id: "poucet",
  investigation: {
    source_kind: "experiment_sample",
    player_id: "poucet",
    run: { id: "run-1", label: "J2", journey: "J2" },
    records: [],
    diagnostics: [],
    world: {},
    cost: {},
    capture_gaps: [],
  },
  knowledge: {
    version: 1,
    player_id: "poucet",
    assertions: [],
    changes: [],
    snapshots: [],
    recoveries: [],
    capture_gaps: [],
    metrics: [],
  },
  history: { player_id: "poucet", total_runs: 1, items: [] },
  selection: {
    selected_record_id: "gateway:42",
    diagnostic_id: null,
    lens: "evidence",
  },
  annotations: [],
  redaction: {
    local_paths_included: false,
    credentials_included: false,
  },
};

async function digest(value: unknown): Promise<string> {
  const buffer = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(JSON.stringify(value)),
  );
  return [...new Uint8Array(buffer)]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

test("opens an intact portable capsule without a source server", async () => {
  const file = new File([
    JSON.stringify({
      kind: "boukensha.observatory.incident",
      version: 2,
      digest: await digest(payload),
      payload,
    }),
  ], "incident.json", { type: "application/json" });

  const capsule = await readIncident(file);
  expect(capsule.payload.selection.selected_record_id).toBe("gateway:42");
  expect(capsule.payload.investigation.run.id).toBe("run-1");
});

test("rejects a modified offline capsule", async () => {
  const file = new File([
    JSON.stringify({
      kind: "boukensha.observatory.incident",
      version: 2,
      digest: "0".repeat(64),
      payload,
    }),
  ], "incident.json", { type: "application/json" });

  await expect(readIncident(file)).rejects.toThrow("Integrity check failed");
});

test("rejects a structurally incomplete capsule before rendering", async () => {
  const file = new File([
    JSON.stringify({
      kind: "boukensha.observatory.incident",
      version: 2,
      digest: "0".repeat(64),
      payload: { title: "not enough evidence" },
    }),
  ], "incident.json", { type: "application/json" });

  await expect(readIncident(file)).rejects.toThrow(
    "not a supported Boukensha incident",
  );
});
