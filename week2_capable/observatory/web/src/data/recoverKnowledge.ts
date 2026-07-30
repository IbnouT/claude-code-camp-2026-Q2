export type KnowledgeRecoveryAction = {
  action: "reset" | "restore";
  sessionId: string;
  expectedSequence: number;
  reason: string;
  snapshotId: string | null;
};

export async function recoverKnowledge(
  playerId: string,
  request: KnowledgeRecoveryAction,
): Promise<Record<string, unknown>> {
  const response = await fetch(
    `/api/players/${encodeURIComponent(playerId)}/knowledge/recovery`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        request_id: crypto.randomUUID(),
        action: request.action,
        session_id: request.sessionId,
        expected_sequence: request.expectedSequence,
        confirmed: true,
        reason: request.reason,
        snapshot_id: request.snapshotId,
      }),
    },
  );
  const payload = await response.json() as Record<string, unknown>;
  if (!response.ok) {
    throw new Error(
      typeof payload.detail === "string"
        ? payload.detail
        : "Knowledge recovery was rejected.",
    );
  }
  return payload;
}
