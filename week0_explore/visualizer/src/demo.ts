// A scripted fake session that exercises every visual: rooms materializing,
// a collision with a bent connector, an up-stub, a floating cluster, darkness,
// combat with falling HP, a kill, a level-up, a death, plan progress, thoughts.
import type { Activity, LinkC, PlanStep, StateC } from "./state";

interface Op {
  room?: [string, string[], string[]?];
  link?: [string, string, string];
  move?: [string, string, string]; // like link but also pushes the trail
  pos?: string | null;
  v?: Partial<StateC["vitals"]>;
  event?: string;
  thought?: string;
  planDone?: number;
  death?: boolean;
  hazard?: [string, string, string]; // room, note, flag
  act?: [Activity["kind"], string];
  combat?: { foe: string; lines: string[] } | null;
  feed?: string[];
}

const G = "Temple Gate";
const SQ = "Temple Square";
const MK = "Market Square";
const ER = "East Road";
const AL = "Narrow Alley";
const WH = "Old Warehouse";
const GH = "Gatehouse";
const BD = "River Bend";
const TW = "Twisting Path";
const CL = "Damp Cellar";

const SCRIPT: Op[] = [
  { room: [G, ["north", "south", "east", "west"]], pos: G,
    v: { hp: 48, max_hp: 48, mana: 100, max_mana: 100, moves: 90, max_moves: 90, gold: 20, xp: 40, xp_to_next: 160, level: 1 },
    thought: "New session. Mapping outward from the gate." },
  { room: [SQ, ["north", "east", "south", "west"]], link: [G, "south", SQ], move: [G, "south", SQ], pos: SQ, v: { moves: 89 } },
  { event: "Killed a small rat (+12 xp)", v: { xp: 52 } },
  { room: [MK, ["north", "east", "south", "west", "up"]], link: [SQ, "south", MK], move: [SQ, "south", MK], pos: MK, v: { moves: 88 }, planDone: 0,
    thought: "Square scouted. A stairway leads up here — noted." },
  { v: { gold: 8 }, event: "Bought a torch (-12 gold)" },
  { room: [ER, ["west", "east", "north"]], link: [MK, "east", ER], move: [MK, "east", ER], pos: ER, v: { moves: 87 } },
  { room: [AL, ["south", "north", "west"]], link: [ER, "north", AL], move: [ER, "north", AL], pos: AL, v: { moves: 86 },
    thought: "This alley loops back toward the square — good shortcut." },
  { link: [AL, "west", SQ] },
  { room: [WH, ["south"]], link: [AL, "north", WH], move: [AL, "north", WH], pos: WH, v: { moves: 85 } },
  { move: [WH, "south", AL], pos: AL },
  // collision: Gatehouse wants the Warehouse's cell -> spiral + bent connector
  { move: [AL, "west", SQ], pos: SQ, v: { moves: 84 } },
  { move: [SQ, "north", G], pos: G, v: { moves: 83 } },
  { room: [GH, ["west", "north"]], link: [G, "east", GH], move: [G, "east", GH], pos: GH, v: { moves: 82 },
    thought: "Map disagrees with geometry here — the gatehouse overlaps. Interesting." },
  { move: [GH, "west", G], pos: G },
  // combat sequence on the east road
  { move: [G, "south", SQ], pos: SQ, v: { moves: 81 } },
  { move: [SQ, "south", MK], pos: MK, v: { moves: 80 } },
  { move: [MK, "east", ER], pos: ER, v: { moves: 79 }, thought: "A bandit here. Considering... beatable.",
    act: ["reading", "studying the road bandit"], feed: ["[SENT] consider bandit", "Do you feel lucky, punk?"] },
  { event: "Engaged a road bandit", v: { hp: 39 }, act: ["fighting", "fighting the road bandit"],
    combat: { foe: "road bandit", lines: ["[SENT] kill bandit", "You slash the road bandit hard.", "The road bandit hits you."] },
    feed: ["[SENT] kill bandit", "You slash the road bandit hard.", "The road bandit hits you."] },
  { v: { hp: 31 },
    combat: { foe: "road bandit", lines: ["[SENT] kill bandit", "You slash the road bandit hard.", "The road bandit hits you.", "You pierce the road bandit very hard.", "The road bandit pounds you!"] },
    feed: ["You pierce the road bandit very hard.", "The road bandit pounds you!"] },
  { event: "Killed the road bandit (+55 xp)", v: { hp: 31, xp: 107, gold: 15 }, combat: null,
    act: ["exploring", "exploring"],
    feed: ["The road bandit is dead!  R.I.P.", "You receive 55 experience points.", "You get 7 gold coins from the corpse."] },
  { v: { hp: 34 }, thought: "Won, but HP under two thirds. One more, then rest.",
    act: ["resting", "resting — recovering vitals"], feed: ["[SENT] rest", "You sit down and rest."] },
  { room: [BD, ["west", "north"]], link: [ER, "east", BD], move: [ER, "east", BD], pos: BD, v: { moves: 78 },
    act: ["exploring", "exploring"], feed: ["[SENT] e", "River Bend"] },
  { event: "Engaged a river troll", v: { hp: 22 }, act: ["fighting", "fighting the river troll"],
    combat: { foe: "river troll", lines: ["[SENT] kill troll", "You barely tickle the river troll.", "The river troll crushes you!"] },
    feed: ["[SENT] kill troll", "You barely tickle the river troll.", "The river troll crushes you!"] },
  { v: { hp: 12 }, thought: "This troll hits hard — HP critical. Fleeing!",
    combat: { foe: "river troll", lines: ["The river troll crushes you!", "You miss the river troll.", "The river troll pounds you very hard!"] },
    feed: ["You miss the river troll.", "The river troll pounds you very hard!"] },
  { death: true, pos: G, event: "DIED at River Bend — corpse left behind", v: { hp: 7 },
    hazard: [BD, "a death occurred here", "death"], combat: null, act: ["dead", "died — corpse run ahead"],
    feed: ["You are dead!  Sorry...", "You feel a strange pull... The Temple Gate."] },
  { thought: "Respawned. Resting before the corpse run.", v: { hp: 18 },
    act: ["resting", "resting — recovering vitals"], feed: ["[SENT] rest", "You sit down and rest."] },
  { v: { hp: 30 } },
  { v: { hp: 42, moves: 84 }, act: ["thinking", "quiet for 20s — deciding the next move"] },
  { event: "Killed a giant spider (+48 xp)", v: { xp: 155 } },
  { event: "LEVEL UP! Now level 2", v: { level: 2, xp: 165, xp_to_next: 300, max_hp: 61, hp: 58 }, planDone: 1,
    thought: "Level 2. The plan's next step needs a lamp — 25 gold short." },
  { room: [TW, ["south", "west"]], link: [AL, "east", TW], move: [AL, "east", TW], pos: TW, v: { moves: 82 } },
  // darkness south of the market
  { pos: MK, thought: "Checking the passage below the market." },
  { hazard: [MK, "darkness through south (bring a light source)", "hazard"], pos: null,
    event: "Stepped into pitch darkness", thought: "Can't see a thing. Backing out carefully." },
  // recall scroll -> floating cluster
  { room: [CL, ["north", "east"]], pos: CL, thought: "Fell through! No idea where this cellar connects." },
  { event: "Used a recall scroll", pos: G, v: { gold: 3 },
    thought: "Recalled to the gate. Cellar stays an island on the map for now." },
  { v: { hp: 61, moves: 88 } },
  { event: "Killed a small rat (+10 xp)", v: { xp: 175 } },
  { thought: "Steady. Saving for the lamp before going deep again." },
];

export const DEMO_TICKS = SCRIPT.length + 4; // hold the final frame briefly

const PLAN_STEPS: PlanStep[] = [
  { text: "scout the town squares", check: null, done: false },
  { text: "reach level 2 on safe targets", check: "level>=2", done: false },
  { text: "buy a lamp for the dark passage", check: "item:lamp", done: false },
  { text: "find and defeat the minotaur", check: null, done: false },
];

export function demoFrame(tick: number): StateC {
  const rooms: StateC["rooms"] = {};
  const links: LinkC[] = [];
  const trail: LinkC[] = [];
  const events: string[] = [];
  const steps = PLAN_STEPS.map((s) => ({ ...s }));
  const feed: string[] = [];
  let vitals: StateC["vitals"] = {};
  let position: string | null = null;
  let deaths = 0;
  let thought = "";
  let activity: Activity | null = { kind: "exploring", detail: "exploring" };
  let combat: StateC["combat"] = null;

  for (const op of SCRIPT.slice(0, Math.min(tick + 1, SCRIPT.length))) {
    if (op.room) {
      const [key, exits, flags] = op.room;
      rooms[key] = { title: key, exits, flags: flags ?? [], hazards: [] };
    }
    if (op.link) links.push({ from: op.link[0], dir: op.link[1], to: op.link[2] });
    if (op.move) trail.push({ from: op.move[0], dir: op.move[1], to: op.move[2] });
    if (op.pos !== undefined) position = op.pos;
    if (op.v) vitals = { ...vitals, ...op.v };
    if (op.event) events.push(op.event);
    if (op.thought) thought = op.thought;
    if (op.planDone !== undefined) steps[op.planDone].done = true;
    if (op.death) deaths += 1;
    if (op.act) activity = { kind: op.act[0], detail: op.act[1] };
    else if (op.move) activity = { kind: "exploring", detail: "exploring" };
    if (op.combat !== undefined) combat = op.combat;
    if (op.feed) feed.push(...op.feed);
    else if (op.move) feed.push(`[SENT] ${op.move[1]}`, op.move[2]);
    if (op.hazard) {
      const [key, note, flag] = op.hazard;
      if (rooms[key]) {
        rooms[key].hazards.push(note);
        if (!rooms[key].flags.includes(flag)) rooms[key].flags.push(flag);
      }
    }
  }

  return {
    rooms,
    links,
    trail: trail.slice(-10),
    position,
    vitals,
    deaths,
    events,
    plan: { goal: "Defeat the minotaur in the deep passage", steps },
    thought,
    conditions: tick > 20 ? ["hungry"] : [],
    activity,
    combat,
    feed: feed.slice(-40),
    quiet_seconds: activity?.kind === "thinking" ? 20 : 0,
  };
}
