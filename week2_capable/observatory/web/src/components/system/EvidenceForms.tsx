import { Braces, Eye, Radio, Sparkles, Telescope } from "lucide-react";
import { useState } from "react";
import type { EvidenceForm, WorkspaceFixture } from "../../app/shellTypes";
import { StateBadge } from "./StateBadge";

type Props = {
  evidence: WorkspaceFixture["evidence"];
};

const forms: { id: EvidenceForm; label: string; icon: typeof Radio }[] = [
  { id: "wire", label: "Wire", icon: Radio },
  { id: "parsed", label: "Parsed", icon: Braces },
  { id: "rendered", label: "Rendered", icon: Eye },
  { id: "believed", label: "Believed", icon: Sparkles },
  { id: "truth", label: "Truth", icon: Telescope },
];

export function EvidenceForms({ evidence }: Props) {
  const [active, setActive] = useState<EvidenceForm>("parsed");
  const selected = evidence[active];

  return (
    <section className="evidence-panel" aria-labelledby="evidence-heading">
      <div className="panel-heading">
        <span>
          <p className="eyebrow">Selected observation</p>
          <h2 id="evidence-heading">Evidence forms</h2>
        </span>
        <StateBadge state={selected.state === "available" ? "actual" : "incomplete"}>
          {selected.state}
        </StateBadge>
      </div>
      <div className="evidence-tabs" role="tablist" aria-label="Evidence forms">
        {forms.map(({ id, icon: Icon, label }) => (
          <button
            aria-selected={active === id}
            className="evidence-tab"
            key={id}
            role="tab"
            type="button"
            onClick={() => setActive(id)}
          >
            <Icon size={14} aria-hidden="true" />
            {label}
            <span
              className={`form-availability is-${evidence[id].state}`}
              aria-label={evidence[id].state}
            />
          </button>
        ))}
      </div>
      <div className={`evidence-preview evidence-${active}`} role="tabpanel">
        <pre>{selected.preview}</pre>
      </div>
    </section>
  );
}
