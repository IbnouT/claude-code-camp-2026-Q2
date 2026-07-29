import type { ComparisonLane } from "../data/comparison";

type Props = {
  lane: ComparisonLane;
  through: number;
};

const steps: Record<string, [number, number]> = {
  north: [0, -1],
  south: [0, 1],
  east: [1, 0],
  west: [-1, 0],
  up: [0.7, -0.7],
  down: [-0.7, 0.7],
};

export function RouteFingerprint({ lane, through }: Props) {
  const points: Array<[number, number]> = [[0, 0]];
  for (const milestone of lane.milestones) {
    if (milestone.index > through || milestone.kind !== "move") continue;
    const [dx, dy] = steps[milestone.argument ?? ""] ?? [0, 0];
    const [x, y] = points.at(-1) ?? [0, 0];
    points.push([x + dx, y + dy]);
  }
  const xs = points.map(([x]) => x);
  const ys = points.map(([, y]) => y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const width = Math.max(1, maxX - minX);
  const height = Math.max(1, maxY - minY);
  const normalized = points.map(([x, y]) => [
    18 + ((x - minX) / width) * 184,
    15 + ((y - minY) / height) * 76,
  ] as const);

  return (
    <svg
      className={`route-fingerprint mode-${lane.mode}`}
      viewBox="0 0 220 106"
      role="img"
      aria-label={`${lane.mode} route through semantic action ${through}`}
    >
      <polyline points={normalized.map((point) => point.join(",")).join(" ")} />
      {normalized.map(([x, y], index) => (
        <circle
          key={`${x}:${y}:${index}`}
          cx={x}
          cy={y}
          r={index === normalized.length - 1 ? 4 : 2.5}
        />
      ))}
      <text x="18" y="102">start</text>
      <text x="202" y="102" textAnchor="end">{points.length - 1} moves</text>
    </svg>
  );
}
