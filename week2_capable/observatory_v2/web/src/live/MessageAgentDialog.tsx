import {
  Send,
  X,
} from "lucide-react";
import {
  useEffect,
  useRef,
  useState,
} from "react";
import type { LiveRouteIdentity } from "../routes";

type Receipt = {
  request_id: string;
  action: "guide";
  state: string;
  insertion: string;
};

export function MessageAgentDialog({
  expectedSequence,
  identity,
  onClose,
}: {
  expectedSequence: number;
  identity: LiveRouteIdentity;
  onClose: () => void;
}) {
  const [instruction, setInstruction] = useState("");
  const [pending, setPending] = useState(false);
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    inputRef.current?.focus();
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);

  const submit = () => {
    const message = instruction.trim();
    if (message.length === 0 || pending) return;
    setPending(true);
    setError(null);
    const requestId = crypto.randomUUID();
    fetch(`/api/sessions/${encodeURIComponent(identity.sessionId)}/control`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        request_id: requestId,
        action: "guide",
        instruction: message,
        expected_sequence: expectedSequence,
      }),
    })
      .then(async (response) => {
        if (!response.ok) {
          const detail = await response.text();
          throw new Error(detail || `Message rejected (${response.status})`);
        }
        return response.json() as Promise<Receipt>;
      })
      .then((nextReceipt) => setReceipt(nextReceipt))
      .catch((reason: unknown) => {
        setError(reason instanceof Error ? reason.message : "Message failed");
      })
      .finally(() => setPending(false));
  };

  return (
    <div
      className="live-dialog-backdrop"
      onPointerDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section aria-label="Message agent" aria-modal="true" className="live-message-dialog" role="dialog">
        <header className="live-dialog-heading">
          <div>
            <p>Running agent</p>
            <h2>Message agent</h2>
          </div>
          <button aria-label="Close message agent" className="live-icon-button" type="button" onClick={onClose}>
            <X aria-hidden="true" size={17} />
          </button>
        </header>
        {receipt === null ? (
          <div className="live-message-compose">
            <label htmlFor="live-agent-message">Guidance for the next iteration boundary</label>
            <textarea
              id="live-agent-message"
              ref={inputRef}
              maxLength={4_000}
              rows={5}
              value={instruction}
              onChange={(event) => setInstruction(event.target.value)}
            />
            <p>
              This inserts an operator message at the next agent iteration boundary.
              It does not issue a MUD command directly.
            </p>
            {error === null ? null : <p className="live-message-error" role="alert">{error}</p>}
            <button
              className="live-message-submit"
              disabled={pending || instruction.trim().length === 0}
              type="button"
              onClick={submit}
            >
              <Send aria-hidden="true" size={15} />
              {pending ? "Sending…" : "Send guidance"}
            </button>
          </div>
        ) : (
          <div className="live-message-receipt" role="status">
            <strong>Guidance accepted</strong>
            <p>{receipt.insertion}</p>
            <small>Request {receipt.request_id}</small>
            <button type="button" onClick={onClose}>Done</button>
          </div>
        )}
      </section>
    </div>
  );
}
