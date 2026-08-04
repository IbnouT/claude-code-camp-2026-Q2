/**
 * The launcher constellation backdrop: a fixed star network behind the scene.
 * One node lights up while any session is live.
 */

type BackdropNode = { id: string; x: number; y: number; emphasis?: boolean }

const backdropNodes: BackdropNode[] = [
  { id: "a", x: 110, y: 105 },
  { id: "b", x: 235, y: 72 },
  { id: "c", x: 355, y: 125, emphasis: true },
  { id: "d", x: 485, y: 80 },
  { id: "e", x: 615, y: 130 },
  { id: "f", x: 755, y: 68 },
  { id: "g", x: 900, y: 115, emphasis: true },
  { id: "h", x: 1065, y: 82 },
  { id: "i", x: 175, y: 235 },
  { id: "j", x: 305, y: 265 },
  { id: "k", x: 435, y: 210 },
  { id: "l", x: 565, y: 270, emphasis: true },
  { id: "m", x: 705, y: 215 },
  { id: "n", x: 850, y: 270 },
  { id: "o", x: 995, y: 220 },
  { id: "p", x: 1120, y: 285 },
  { id: "q", x: 105, y: 395 },
  { id: "r", x: 255, y: 365 },
  { id: "s", x: 395, y: 425 },
  { id: "t", x: 535, y: 365 },
  { id: "u", x: 675, y: 430 },
  { id: "v", x: 825, y: 375, emphasis: true },
  { id: "w", x: 985, y: 425 },
  { id: "x", x: 170, y: 565 },
  { id: "y", x: 325, y: 520 },
  { id: "z", x: 475, y: 590 },
  { id: "aa", x: 630, y: 535 },
  { id: "ab", x: 785, y: 605 },
  { id: "ac", x: 945, y: 545 },
  { id: "ad", x: 1090, y: 635 },
  { id: "ae", x: 370, y: 715 },
  { id: "af", x: 545, y: 680 },
  { id: "ag", x: 720, y: 730 },
  { id: "ah", x: 900, y: 680 },
]

const backdropEdges: Array<readonly [string, string]> = [
  ["a", "b"],
  ["b", "c"],
  ["c", "d"],
  ["d", "e"],
  ["e", "f"],
  ["f", "g"],
  ["g", "h"],
  ["a", "i"],
  ["b", "i"],
  ["c", "j"],
  ["c", "k"],
  ["d", "k"],
  ["e", "l"],
  ["e", "m"],
  ["f", "m"],
  ["g", "n"],
  ["g", "o"],
  ["h", "o"],
  ["i", "j"],
  ["j", "k"],
  ["k", "l"],
  ["l", "m"],
  ["m", "n"],
  ["n", "o"],
  ["o", "p"],
  ["i", "q"],
  ["j", "r"],
  ["k", "s"],
  ["l", "t"],
  ["m", "u"],
  ["n", "v"],
  ["o", "w"],
  ["q", "r"],
  ["r", "s"],
  ["s", "t"],
  ["t", "u"],
  ["u", "v"],
  ["v", "w"],
  ["q", "x"],
  ["r", "x"],
  ["r", "y"],
  ["s", "y"],
  ["s", "z"],
  ["t", "z"],
  ["t", "aa"],
  ["u", "aa"],
  ["u", "ab"],
  ["v", "ab"],
  ["v", "ac"],
  ["w", "ac"],
  ["w", "ad"],
  ["x", "y"],
  ["y", "z"],
  ["z", "aa"],
  ["aa", "ab"],
  ["ab", "ac"],
  ["ac", "ad"],
  ["y", "ae"],
  ["z", "af"],
  ["aa", "af"],
  ["ab", "ag"],
  ["ac", "ah"],
  ["ae", "af"],
  ["af", "ag"],
  ["ag", "ah"],
]

const backdropById = new Map(backdropNodes.map((node) => [node.id, node]))

function Constellation({ live }: { live: boolean }) {
  return (
    <div
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 bg-[radial-gradient(900px_620px_at_62%_40%,var(--scene-core)_0%,var(--scene-mid)_45%,var(--canvas)_100%)]"
    >
      <svg
        viewBox="0 0 1200 800"
        preserveAspectRatio="xMidYMid slice"
        className="h-full w-full opacity-[0.42] drop-shadow-[0_0_9px_rgba(28,55,82,0.22)]"
      >
        {backdropEdges.map(([sourceId, targetId]) => {
          const source = backdropById.get(sourceId)
          const target = backdropById.get(targetId)
          if (!source || !target) return null
          return (
            <line
              key={`${sourceId}-${targetId}`}
              x1={source.x}
              y1={source.y}
              x2={target.x}
              y2={target.y}
              stroke="var(--scene-link)"
              strokeWidth={1.15}
            />
          )
        })}
        {backdropNodes.map((node) => (
          <circle
            key={node.id}
            cx={node.x}
            cy={node.y}
            r={node.emphasis ? 5.5 : 3.5}
            className={
              live && node.id === "v"
                ? "animate-[pulse-glow_2.6s_ease-in-out_infinite] fill-accent"
                : node.emphasis
                  ? "fill-(--scene-node-strong) drop-shadow-[0_0_5px_rgba(61,99,134,0.45)]"
                  : "fill-(--scene-node)"
            }
          />
        ))}
      </svg>
    </div>
  )
}

export { Constellation }
