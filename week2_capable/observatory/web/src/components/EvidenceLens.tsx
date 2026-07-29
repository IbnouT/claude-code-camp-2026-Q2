import { Binary, Bot, Braces, CheckCircle2, ScanText } from "lucide-react";
import type {
  EvidenceCitation,
  Investigation,
} from "../data/investigation";

type Props = {
  investigation: Investigation;
  activeEvidence: string[];
  onSelect: (sequence: number) => void;
};

const layers = [
  ["wire", "Wire", Binary],
  ["parsed", "Parsed", Braces],
  ["rendered", "Rendered", ScanText],
  ["believed", "Believed", Bot],
  ["truth", "Truth", CheckCircle2],
] as const;

export function EvidenceLens({
  investigation,
  activeEvidence,
  onSelect,
}: Props) {
  const citations = new Map(
    investigation.citations.map((citation) => [citation.id, citation]),
  );

  return (
    <section className="evidence-lens" aria-labelledby="evidence-lens-title">
      <header className="rail-heading">
        <div>
          <p className="eyebrow">One fact, five forms</p>
          <h2 id="evidence-lens-title">Evidence lens</h2>
        </div>
      </header>
      <div className="lens-stack">
        {layers.map(([key, label, Icon]) => {
          const form = investigation.lens[key];
          const cited = form.citations
            .map((id) => citations.get(id))
            .filter((item): item is EvidenceCitation => item !== undefined);
          return (
            <article
              key={key}
              className={
                activeEvidence.some((id) => form.citations.includes(id))
                  ? `lens-card lens-${key} is-active`
                  : `lens-card lens-${key}`
              }
            >
              <header>
                <span><Icon size={13} aria-hidden="true" />{label}</span>
                <small>{form.state}</small>
              </header>
              <strong>{form.title}</strong>
              <p>{form.text}</p>
              {cited.map((citation) => (
                <button
                  key={citation.id}
                  type="button"
                  disabled={citation.sequence === null}
                  onClick={() => citation.sequence !== null && onSelect(citation.sequence)}
                >
                  {citation.label}
                </button>
              ))}
            </article>
          );
        })}
      </div>
    </section>
  );
}
