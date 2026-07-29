import { Activity, GitCompareArrows, SearchCode } from "lucide-react";
import type { Mode } from "../app/types";

const modes: { id: Mode; label: string; icon: typeof Activity }[] = [
  { id: "live", label: "Live", icon: Activity },
  { id: "investigate", label: "Investigate", icon: SearchCode },
  { id: "compare", label: "Compare", icon: GitCompareArrows },
];

type Props = {
  active: Mode;
  enabled: Mode[];
  onChange: (mode: Mode) => void;
};

export function ModeNav({ active, enabled, onChange }: Props) {
  return (
    <nav className="mode-nav" aria-label="Observatory modes">
      {modes.filter(({ id }) => enabled.includes(id)).map(({ id, label, icon: Icon }) => (
        <button
          key={id}
          className={active === id ? "mode-button is-active" : "mode-button"}
          type="button"
          aria-pressed={active === id}
          onClick={() => onChange(id)}
        >
          <Icon aria-hidden="true" size={15} strokeWidth={1.8} />
          {label}
        </button>
      ))}
    </nav>
  );
}
