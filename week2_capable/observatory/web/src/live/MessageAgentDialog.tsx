import { Send, X } from "lucide-react";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import type { LiveOperatorMessage } from "../contracts";
import { lifecycleApiUrl } from "../lifecycleApi";
import type { LiveRouteIdentity } from "../routes";

type Action = "guide" | "revise";

type Receipt = {
  request_id: string;
  action: Action;
  state: string;
  insertion: string;
};

type OptimisticMessage = LiveOperatorMessage & {
  status: "sending" | "waiting";
  baselineCount: number;
};

function sentTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.valueOf())
    ? value
    : new Intl.DateTimeFormat(undefined, {
      hour: "2-digit",
      minute: "2-digit",
    }).format(date);
}

function appliedLine(message: LiveOperatorMessage): string {
  if (message.applied_iteration === null) {
    return "waiting for the next iteration";
  }
  return message.action === "revise"
    ? `replaced the goal at iteration ${message.applied_iteration}`
    : `applied at iteration ${message.applied_iteration}`;
}

export function MessageAgentDialog({
  controlAvailable,
  followingLive,
  identity,
  messages,
  objectiveAvailable,
  selectedSequence,
  sessionRunning,
  onClose,
}: {
  controlAvailable: boolean;
  followingLive: boolean;
  identity: LiveRouteIdentity;
  messages: LiveOperatorMessage[];
  objectiveAvailable: boolean;
  selectedSequence: number;
  sessionRunning: boolean;
  onClose: () => void;
}) {
  const [action, setAction] = useState<Action>(
    objectiveAvailable ? "guide" : "revise",
  );
  const [closing, setClosing] = useState(false);
  const [instruction, setInstruction] = useState("");
  const [optimistic, setOptimistic] = useState<OptimisticMessage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const closeTimerRef = useRef(0);
  const onCloseRef = useRef(onClose);

  const sending = optimistic?.status === "sending";
  const canSend = followingLive
    && sessionRunning
    && controlAvailable
    && !sending;

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  const requestClose = useCallback(() => {
    setClosing((current) => {
      if (current) return current;
      closeTimerRef.current = window.setTimeout(
        () => onCloseRef.current(),
        360,
      );
      return true;
    });
  }, []);

  useEffect(() => {
    inputRef.current?.focus();
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") requestClose();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      window.removeEventListener("keydown", closeOnEscape);
      window.clearTimeout(closeTimerRef.current);
    };
  }, [requestClose]);

  useEffect(() => {
    if (
      optimistic !== null
      && optimistic.status === "waiting"
      && messages.length > optimistic.baselineCount
    ) {
      setOptimistic(null);
    }
  }, [messages.length, optimistic]);

  const submit = () => {
    const message = instruction.trim();
    if (message.length === 0 || !canSend) return;
    const nextOptimistic: OptimisticMessage = {
      action,
      instruction: message,
      sent_at: new Date().toISOString(),
      applied_iteration: null,
      status: "sending",
      baselineCount: messages.length,
    };
    setOptimistic(nextOptimistic);
    setError(null);
    const target = lifecycleApiUrl(
      `/api/sessions/${encodeURIComponent(identity.sessionId)}/message`,
    );
    fetch(target, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        request_id: crypto.randomUUID(),
        action,
        instruction: message,
      }),
    })
      .then(async (response) => {
        if (!response.ok) {
          const detail = await response.text();
          throw new Error(detail || `Message rejected (${response.status})`);
        }
        return response.json() as Promise<Receipt>;
      })
      .then(() => {
        setInstruction("");
        setOptimistic((current) => (
          current === null ? null : { ...current, status: "waiting" }
        ));
      })
      .catch((reason: unknown) => {
        setOptimistic(null);
        setError(reason instanceof Error ? reason.message : "Message failed");
      });
  };

  const disabledPlaceholder = !followingLive
    ? "Return to live to message the agent"
    : !sessionRunning
      ? "The agent is not running"
      : "Steer the agent";

  return (
    <div
      className={[
        "live-dialog-backdrop",
        "live-message-backdrop",
        closing ? "is-closing" : "is-opening",
      ].join(" ")}
      onPointerDown={(event) => {
        if (event.target === event.currentTarget) requestClose();
      }}
    >
      <section aria-label="Your messages" aria-modal="true" className="live-message-dialog" role="dialog">
        <header className="live-dialog-heading">
          <div>
            <p>Running agent · {identity.playerId}</p>
            <h2>Your messages</h2>
          </div>
          <button aria-label="Close messages" className="live-icon-button" type="button" onClick={requestClose}>
            <X aria-hidden="true" size={17} />
          </button>
        </header>
        <div className="live-message-compose">
          <div aria-label="Sent message history" className="live-message-history">
            {messages.length === 0 && optimistic === null ? (
              <p className="live-message-empty">You have not messaged this agent.</p>
            ) : messages.map((message, index) => (
              <article key={`${message.sent_at}-${index}`}>
                <p>{message.instruction}</p>
                <small>{sentTime(message.sent_at)} · {appliedLine(message)}</small>
              </article>
            ))}
            {optimistic === null ? null : (
              <article className="is-optimistic">
                <p>{optimistic.instruction}</p>
                <small>
                  {sentTime(optimistic.sent_at)} · {optimistic.status === "sending"
                    ? "sending…"
                    : "waiting for the next iteration"}
                </small>
              </article>
            )}
          </div>
          <label htmlFor="live-agent-message">Message for the agent</label>
          <textarea
            disabled={!followingLive || !sessionRunning}
            id="live-agent-message"
            ref={inputRef}
            maxLength={4_000}
            rows={5}
            value={instruction}
            placeholder={disabledPlaceholder}
            onChange={(event) => setInstruction(event.target.value)}
          />
          {!followingLive ? (
            <p>
              A message would arrive at the live boundary, not at the moment
              being inspected.
            </p>
          ) : null}
          {!sessionRunning ? <p>The agent is not running.</p> : null}
          {error === null ? null : <p className="live-message-error" role="alert">{error}</p>}
          <div className="live-message-controls">
            {followingLive && sessionRunning ? (
              <div aria-label="Message effect" className="live-message-mode" role="group">
                <button
                  aria-pressed={action === "revise"}
                  type="button"
                  onClick={() => setAction("revise")}
                >
                  Goal
                </button>
                <button
                  aria-pressed={action === "guide"}
                  type="button"
                  onClick={() => setAction("guide")}
                >
                  Nudge
                </button>
              </div>
            ) : (
              <span className="live-message-disabled-mode">
                {followingLive ? "session stopped" : `inspecting sequence ${selectedSequence}`}
              </span>
            )}
            <button
              aria-label="Send message"
              className="live-message-submit"
              disabled={!canSend || instruction.trim().length === 0}
              type="button"
              onClick={submit}
            >
              <Send aria-hidden="true" size={15} />
              {sending ? "Sending" : "Send"}
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}
