import type { ReactNode } from "react";

type State =
  | "actual"
  | "inferred"
  | "believed"
  | "counterfactual"
  | "attention"
  | "incomplete";

type Props = {
  children: ReactNode;
  state: State;
};

export function StateBadge({ children, state }: Props) {
  return <span className={`state-badge state-${state}`}>{children}</span>;
}
