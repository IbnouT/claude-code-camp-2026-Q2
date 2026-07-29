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
  selectedProjection,
  type EvidenceState,
} from "./reducer";
import { EvidenceStreamDecoder, decodeEvidenceText } from "./sse";
import { assertCanonicalEventContract } from "./contracts";

type SessionsResponse = {
  sessions: string[];
};

export type SessionEvidence = {
  available: boolean;
  state: EvidenceState;
  projection: ReturnType<typeof selectedProjection>;
  select: (sequence: number) => void;
  resume: () => void;
};

export function useSessionStream(): SessionEvidence {
  const [state, setState] = useState(() => createEvidenceState(""));

  useEffect(() => {
    const abort = new AbortController();
    void connect(abort.signal, setState);
    return () => abort.abort();
  }, []);

  useEffect(() => {
    if (!state.session || state.selectedSeq === 0) {
      return;
    }
    const url = new URL(window.location.href);
    url.searchParams.set("session", state.session);
    url.searchParams.set("seq", String(state.selectedSeq));
    window.history.replaceState(null, "", url);
  }, [state.selectedSeq, state.session]);

  const projection = useMemo(() => selectedProjection(state), [state]);
  return {
    available: state.events.length > 0,
    state,
    projection,
    select: (sequence) => {
      setState((current) => selectSequence(current, sequence));
    },
    resume: () => {
      setState((current) => resumeLive(current));
    },
  };
}

async function connect(
  signal: AbortSignal,
  update: Dispatch<SetStateAction<EvidenceState>>,
): Promise<void> {
  try {
    const contractResponse = await fetch("/api/contracts", { signal });
    if (!contractResponse.ok) {
      return;
    }
    assertCanonicalEventContract(await contractResponse.json() as unknown);
    const sessionsResponse = await fetch("/api/sessions", { signal });
    if (!sessionsResponse.ok) {
      return;
    }
    const payload = await sessionsResponse.json() as SessionsResponse;
    const requested = new URL(window.location.href).searchParams.get("session");
    const session = requested && payload.sessions.includes(requested)
      ? requested
      : payload.sessions.at(-1);
    if (!session) {
      return;
    }
    const initial = createEvidenceState(session);
    const replayResponse = await fetch(
      `/api/sessions/${encodeURIComponent(session)}/replay?after=0`,
      { signal },
    );
    if (!replayResponse.ok) {
      return;
    }
    const replay = decodeEvidenceText(await replayResponse.text());
    let cursor = replay.at(-1)?.seq ?? 0;
    const requestedSequence = Number(
      new URL(window.location.href).searchParams.get("seq"),
    );
    const replayed = ingestEvidence(initial, replay);
    update(
      Number.isInteger(requestedSequence) && requestedSequence > 0
        ? selectSequence(replayed, requestedSequence)
        : replayed,
    );

    while (!signal.aborted) {
      const response = await fetch(
        `/api/sessions/${encodeURIComponent(session)}/events?after=${cursor}`,
        { signal },
      );
      if (!response.ok || response.body === null) {
        return;
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
        }
      }
      const finalEvents = decoder.finish();
      if (finalEvents.length > 0) {
        cursor = Math.max(cursor, ...finalEvents.map((event) => event.seq));
        update((current) => ingestEvidence(current, finalEvents));
      }
      await delay(500, signal);
    }
  } catch (error) {
    if (!(error instanceof DOMException && error.name === "AbortError")) {
      return;
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
