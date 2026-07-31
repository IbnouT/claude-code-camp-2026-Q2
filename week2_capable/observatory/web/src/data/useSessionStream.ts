import {
  useEffect,
  useMemo,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";
import {
  createEvidenceState,
  ingestEvidence,
  resumeLive,
  selectSequence,
  type EvidenceState,
} from "./reducer";
import { assertCanonicalEventContract } from "./contracts";
import { EvidenceStreamDecoder, decodeEvidenceText } from "./sse";
import {
  decodeLiveSnapshot,
  type LiveSessionState,
  type LiveSnapshot,
  type RuntimeSession,
} from "./liveContracts";

export type SessionEvidence = LiveSessionState & {
  select: (sequence: number) => void;
  resume: () => void;
};

export function useSessionStream(
  runtimeSession: RuntimeSession | null,
): SessionEvidence {
  const gatewaySession = runtimeSession?.gateway_session_id ?? "";
  const [evidence, setEvidence] = useState<EvidenceState>(
    () => createEvidenceState(gatewaySession),
  );
  const [connection, setConnection] = useState<LiveSessionState["connection"]>(
    "discovering",
  );
  const [error, setError] = useState<string | null>(null);
  const [snapshot, setSnapshot] = useState<LiveSnapshot | null>(null);

  useEffect(() => {
    setEvidence(createEvidenceState(gatewaySession));
    setSnapshot(null);
    setError(null);
    if (runtimeSession === null) {
      setConnection("waiting");
      return;
    }
    const abort = new AbortController();
    void connect(runtimeSession, abort.signal, setEvidence, setConnection, setError);
    return () => abort.abort();
  }, [gatewaySession, runtimeSession?.id, runtimeSession?.live]);

  useEffect(() => {
    if (runtimeSession === null) {
      return;
    }
    const abort = new AbortController();
    const through = evidence.followingLive ? "" : `?through=${evidence.selectedSeq}`;
    void fetch(
      `/api/sessions/${encodeURIComponent(runtimeSession.id)}/snapshot${through}`,
      { signal: abort.signal, cache: "no-store" },
    )
      .then(async (response) => {
        if (!response.ok) {
          const detail = await response.json() as { detail?: string };
          throw new Error(detail.detail ?? `snapshot returned ${response.status}`);
        }
        return decodeLiveSnapshot(await response.json() as unknown);
      })
      .then((value) => {
        setSnapshot(value);
      })
      .catch((caught: unknown) => {
        if (!(caught instanceof DOMException && caught.name === "AbortError")) {
          setError(caught instanceof Error ? caught.message : "snapshot failed");
          setConnection("unavailable");
        }
      });
    return () => abort.abort();
  }, [
    evidence.followingLive,
    evidence.latestSeq,
    evidence.selectedSeq,
    runtimeSession?.id,
  ]);

  useEffect(() => {
    if (runtimeSession === null || evidence.selectedSeq === 0) {
      return;
    }
    const url = new URL(window.location.href);
    url.searchParams.set("player", runtimeSession.player_id);
    url.searchParams.set("session", runtimeSession.id);
    url.searchParams.set("seq", String(evidence.selectedSeq));
    window.history.replaceState(null, "", url);
  }, [evidence.selectedSeq, runtimeSession?.id]);

  return useMemo(
    () => ({
      connection: evidence.followingLive
        ? connection
        : connection === "unavailable"
          ? connection
          : "paused",
      error,
      events: evidence.events,
      latestSequence: evidence.latestSeq,
      selectedSequence: evidence.selectedSeq,
      followingLive: evidence.followingLive,
      gaps: evidence.gaps,
      unknownKinds: evidence.unknownKinds,
      snapshot,
      select: (sequence: number) => {
        setEvidence((current) => selectSequence(current, sequence));
      },
      resume: () => {
        setEvidence((current) => resumeLive(current));
      },
    }),
    [connection, error, evidence, snapshot],
  );
}

async function connect(
  session: RuntimeSession,
  signal: AbortSignal,
  update: Dispatch<SetStateAction<EvidenceState>>,
  setConnection: Dispatch<SetStateAction<LiveSessionState["connection"]>>,
  setError: Dispatch<SetStateAction<string | null>>,
): Promise<void> {
  try {
    setConnection("replaying");
    const contractResponse = await fetch("/api/contracts", { signal });
    if (!contractResponse.ok) {
      throw new Error(`contract discovery returned ${contractResponse.status}`);
    }
    assertCanonicalEventContract(await contractResponse.json() as unknown);
    const replayResponse = await fetch(
      `/api/sessions/${encodeURIComponent(session.id)}/replay?after=0`,
      { signal, cache: "no-store" },
    );
    if (!replayResponse.ok) {
      throw new Error(`session replay returned ${replayResponse.status}`);
    }
    const replay = decodeEvidenceText(await replayResponse.text());
    let cursor = replay.at(-1)?.seq ?? 0;
    /* Session-scoped time selection: honor a requested seq ONLY when the
       URL's session parameter matches the session being connected —
       otherwise a previous session's seq would place this one at an
       unrelated historical prefix. */
    const pageUrl = new URL(window.location.href);
    const requested = pageUrl.searchParams.get("session") === session.id
      ? Number(pageUrl.searchParams.get("seq"))
      : Number.NaN;
    const replayed = ingestEvidence(createEvidenceState(session.gateway_session_id), replay);
    update(
      Number.isInteger(requested) && requested > 0
        ? selectSequence(replayed, requested)
        : replayed,
    );
    if (!session.live) {
      setConnection("ended");
      return;
    }
    setConnection(replay.length > 0 ? "streaming" : "waiting");
    while (!signal.aborted) {
      const response = await fetch(
        `/api/sessions/${encodeURIComponent(session.id)}/events?after=${cursor}`,
        { signal, cache: "no-store" },
      );
      if (!response.ok || response.body === null) {
        throw new Error(`live stream returned ${response.status}`);
      }
      const decoder = new EvidenceStreamDecoder();
      const reader = response.body.getReader();
      while (!signal.aborted) {
        const next = await reader.read();
        if (next.done) {
          break;
        }
        const events = decoder.push(next.value);
        if (events.length > 0) {
          cursor = Math.max(cursor, ...events.map((event) => event.seq));
          update((current) => ingestEvidence(current, events));
          setConnection("streaming");
        }
      }
      const final = decoder.finish();
      if (final.length > 0) {
        cursor = Math.max(cursor, ...final.map((event) => event.seq));
        update((current) => ingestEvidence(current, final));
      }
      await delay(300, signal);
    }
  } catch (caught) {
    if (!(caught instanceof DOMException && caught.name === "AbortError")) {
      setError(caught instanceof Error ? caught.message : "live stream failed");
      setConnection("unavailable");
    }
  }
}

function delay(milliseconds: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    const timeout = window.setTimeout(resolve, milliseconds);
    signal.addEventListener("abort", () => {
      window.clearTimeout(timeout);
      resolve();
    }, { once: true });
  });
}
