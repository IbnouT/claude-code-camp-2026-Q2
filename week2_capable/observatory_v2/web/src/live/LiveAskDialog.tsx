import {
  Search,
  X,
} from "lucide-react";
import {
  useEffect,
  useRef,
  useState,
} from "react";
import type { FormEvent } from "react";
import type { LiveRouteIdentity } from "../routes";

type AskResponse = {
  answer: string;
  citations: Array<{
    id?: string;
    label?: string;
    excerpt?: string;
  }>;
  missing: string[];
  tier: string;
};

type Props = {
  identity: LiveRouteIdentity;
  open: boolean;
  selectedRecordId?: string | null;
  space?: "live" | "sessions";
  onClose: () => void;
};

export function LiveAskDialog({
  identity,
  open,
  selectedRecordId = null,
  space = "live",
  onClose,
}: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<AskResponse | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [limitToSelection, setLimitToSelection] = useState(false);

  useEffect(() => {
    if (!open) return;
    setLimitToSelection(false);
    input.current?.focus();
  }, [open]);

  if (!open) return null;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!question.trim() || loading) return;
    setLoading(true);
    setError("");
    setAnswer(null);
    try {
      const response = await fetch("/api/ask", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          question: question.trim(),
          scope: {
            space,
            player_id: identity.playerId,
            ...(space === "sessions"
              ? { run_id: identity.sessionId }
              : { live_session_id: identity.sessionId }),
            ...(selectedRecordId && limitToSelection
              ? { selected_record_id: selectedRecordId }
              : {}),
          },
          allow_model: false,
          allow_summary: false,
        }),
      });
      const payload = await response.json() as AskResponse & { detail?: string };
      if (!response.ok) {
        throw new Error(payload.detail ?? `Ask returned ${response.status}`);
      }
      setAnswer(payload);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Ask failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="live-dialog-backdrop"
      role="presentation"
      onMouseDown={onClose}
    >
      <section
        aria-label="Ask about this session"
        aria-modal="true"
        className="live-ask-dialog"
        role="dialog"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <form className="live-ask-query" onSubmit={submit}>
          <Search size={18} aria-hidden="true" />
          <input
            aria-label="Question about this session"
            placeholder="Ask why, find a trace, or search exact evidence"
            ref={input}
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
          />
          <button
            className="live-ask-submit"
            disabled={!question.trim() || loading}
            type="submit"
          >
            {loading ? "Planning…" : "Ask"}
          </button>
          <button
            aria-label="Close Ask"
            className="live-icon-button"
            type="button"
            onClick={onClose}
          >
            <X size={16} aria-hidden="true" />
          </button>
        </form>
        <div className="live-ask-scope">
          <span>Scope</span>
          <strong>{identity.playerId} · {identity.sessionId}</strong>
          <small>
            {limitToSelection && selectedRecordId
              ? `Evidence through ${selectedRecordId}.`
              : "Whole session evidence."}
            {" "}Answers cite retained records. Model use is off.
          </small>
          <small>
            Try: “Why did it stop?”, “Find the north gate”, or
            “Which positions were ambiguous?”
          </small>
          {selectedRecordId ? (
            <label className="live-ask-boundary">
              <input
                checked={limitToSelection}
                type="checkbox"
                onChange={(event) => setLimitToSelection(event.target.checked)}
              />
              Limit the answer to evidence through {selectedRecordId}
            </label>
          ) : null}
        </div>
        {error ? <p className="live-ask-error" role="alert">{error}</p> : null}
        {answer ? (
          <div className="live-ask-answer">
            <small>{answer.tier}</small>
            <p>{answer.answer}</p>
            {answer.missing.length > 0 ? (
              <p className="live-ask-missing">
                Missing: {answer.missing.join(", ")}
              </p>
            ) : null}
            <small>{answer.citations.length} evidence citations</small>
            {answer.citations.length > 0 ? (
              <ul className="live-ask-citations">
                {answer.citations.map((citation, index) => (
                  <li key={citation.id ?? `${citation.label ?? "evidence"}-${index}`}>
                    <strong>{citation.label ?? citation.id ?? "Evidence"}</strong>
                    {citation.excerpt ? <span>{citation.excerpt}</span> : null}
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}
      </section>
    </div>
  );
}
