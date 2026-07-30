import { Search, X } from "lucide-react";
import { useEffect, useRef } from "react";

type Props = {
  open: boolean;
  onClose: () => void;
};

export function SearchDialog({ open, onClose }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const previousFocus = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (open) {
      previousFocus.current = document.activeElement as HTMLElement | null;
      input.current?.focus();
      return;
    }
    previousFocus.current?.focus();
  }, [open]);

  if (!open) {
    return null;
  }

  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        aria-label="Ask or search evidence"
        aria-modal="true"
        className="search-dialog"
        role="dialog"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header>
          <Search size={18} aria-hidden="true" />
          <input
            aria-label="Question or evidence query"
            placeholder="Ask why, find a trace, or search exact evidence"
            ref={input}
          />
          <button
            aria-label="Close search"
            className="icon-button"
            type="button"
            onClick={onClose}
          >
            <X size={16} aria-hidden="true" />
          </button>
        </header>
        <div className="search-guidance">
          <p className="eyebrow">Deterministic by default</p>
          <h2>Ask with evidence, even without a model</h2>
          <p>
            Questions are planned into typed local operations. Every answer
            shows the plan, citations, missing data, and optional translation
            cost.
          </p>
          <div className="suggestion-grid">
            <button type="button">Why did the agent stop?</button>
            <button type="button">Show the most expensive loop</button>
            <button type="button">Which evidence disagrees?</button>
          </div>
        </div>
      </section>
    </div>
  );
}
