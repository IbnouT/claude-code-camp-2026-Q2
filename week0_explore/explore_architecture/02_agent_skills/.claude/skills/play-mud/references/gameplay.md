# tbaMUD gameplay cheat sheet

All of these are sent through `mud_session.py cmd "<command>"`.

**The game documents itself** — this file is a starter, not the full manual:
`commands` lists every command you can use (paged; handled automatically),
`help <command>` explains any of them, and `help <topic>` covers concepts
(e.g. `help shops`, `help death`). When you're unsure HOW to do something,
ask the game before improvising.

**Addressing things**: when several objects/mobs share a keyword, pick one
with `N.keyword` — `kill 2.rat`, `get all 3.corpse`, `look 2.guard`.
`all` works with containers and the floor: `get all`, `get all corpse`,
`put all bag`.

## Information

| Command | Purpose |
|---|---|
| `look` / `look <thing>` | Describe the room / an object, mob, or player |
| `exits` | List visible exits with destinations |
| `score` | Full character sheet (level, XP, gold, condition) |
| `inventory` (`i`) | What you carry |
| `equipment` (`eq`) | What you wear/wield |
| `who` | Players online |
| `where` | Nearby players/mobs |
| `weather`, `time` | World state |
| `commands` | Full command list (paged — handled automatically) |

## Movement

`north south east west up down` (or `n s e w u d`), `open <door>`, `close`,
`unlock`/`lock <door>`, `enter <thing>`, `follow <player>`, `sit`, `rest`,
`sleep`, `stand`, `wake`.

Movement costs V (moves); rest to recover it.

### Reading exits, doors, and locks

- The room's `[ Exits: n (e) s ]` line: a **parenthesized** direction means a
  closed door that way — open it before moving.
- `exits` lists each visible exit **with its destination room name** — cheaper
  than walking somewhere to see what it is.
- `look <direction>` describes what lies that way (including the door itself).
- Locked doors don't announce themselves: `open door` answers "It seems to be
  locked." Then you need the matching key (`unlock door`), or `pick` (thief
  skill). Keys are acquirable — shops, corpses, hidden in rooms.

## Items & money

| Command | Purpose |
|---|---|
| `get <item>` / `get <item> <container>` | Pick up / take from container |
| `drop <item>`, `put <item> <container>` | Put down / store |
| `wear <item>`, `wield <weapon>`, `hold <item>` | Equip |
| `remove <item>` | Unequip |
| `eat` / `drink <thing>` | Hunger and thirst affect regen |
| `give <item> <target>`, `give <n> coins <target>` | Transfer |
| `list`, `buy <item>`, `sell <item>`, `value <item>` | In shops |
| `deposit` / `withdraw <n>` | At the bank/ATM |
| `donate <item>` | Send to the donation room |

## Combat

| Command | Purpose |
|---|---|
| `consider <mob>` | Estimate difficulty BEFORE attacking |
| `kill <mob>` | Start a fight (rounds continue asynchronously — poll with `recv`) |
| `flee` | Escape a losing fight (random exit, small XP loss) |
| `cast '<spell>' <target>` | Casters; quotes around the spell name matter |
| `rescue <player>`, `assist <player>` | Group combat |
| `wimpy <hp>` | Auto-flee below this HP |
| `practice` | At your guildmaster: list your skills and remaining practice sessions |
| `practice <skill>` | At your guildmaster: spend a session to improve a skill. This is training, NOT using the skill — never attack the guildmaster |

**Loot everything.** The session enables `autoloot`/`autogold` at login, so
your kills' corpses empty themselves into your inventory automatically — but
verify with `inventory` after fights, and loot manually when needed:
`get all corpse` (several corpses: `get all 2.corpse`, `3.corpse`, ...),
`look in corpse` to inspect first. Items lying in rooms ("A sword is lying
here.") are free — `get sword`, then `wear`/`wield` it or `sell` it. Loot is
your gold income and your gear ladder; walking past it wastes both.

Death drops your corpse (with your gear) where you died; you respawn at the
temple. `get all corpse` after returning.

**Gold dies with you — bank it.** Everything you carry, coins included, goes
into your corpse when you die; a failed corpse run means losing it all. Banks
and ATMs exist (`deposit <n>`, `withdraw <n>`, `balance`) and deposits survive
death. So treat gold like a budget with risk exposure: bank the surplus
whenever you pass a bank/ATM (your world memory records where you've seen
one — try `find atm` or `find bank`), keep only shopping money on you, and
especially deposit before pushing into dangerous territory. Skipping the bank
on the way to a risky area is how a death turns into a bankruptcy.

## Communication

`say <msg>` (room), `gossip <msg>` (global), `tell <player> <msg>`,
`shout <msg>` (zone), `emote <action>`, `reply <msg>`.

## Practical tactics

- Midgaard (the starting city) is safe-ish. Wilderness and dungeons scale up fast.
- `consider` verdict ladder (weakest → strongest): "Now where did that chicken
  go?" → "You could do it with a needle!" → "Easy." → "Fairly easy." →
  "The perfect match!" → "You would need some luck!" → "...a lot of luck!" →
  "...luck and great equipment!" → "Do you feel lucky, punk?" → "Are you
  mad!?"
- **Engagement policy**: at full HP, fight everything up to "The perfect
  match!" — that's where the XP is. "You would need some luck!" is winnable
  when healthy and equipped (let your persona decide). Only the tiers above
  that are a genuine no.
- **Trivial kills are an XP trap**: rewards scale with difficulty, so farming
  "chicken"-tier mobs stalls your leveling — the signals block will show your
  avg XP/kill collapsing. The fastest leveling is the hardest mob you can
  RELIABLY beat, killed repeatedly. Kill everything at your level as you
  travel; be choosy only about what's above you.
- **Risk gradient = XP gradient**: farther from the safe starting zones
  (deeper, darker, underground) generally means harder mobs and better XP.
  When your XP/kill drops, push one ring outward/downward rather than
  grinding where you are.
- **Read the room before you swing** — `consider` rates the target, not the
  situation:
  - **Law-keepers** (guards, soldiers, watchmen): attacking anyone in front
    of them makes you the criminal, and they hit far above your level. If a
    guard-type mob is in the room, don't start a fight there — wait for your
    target to wander somewhere unwatched, or find another target.
  - **Count the pack, then fight anyway**: same-kind mobs may assist each
    other, so judge the group, not the individual — two "easy" targets
    together ≈ one "fair match", which is still a fight you take. Swarms of
    weak vermin (rats and the like) are excellent XP farms even in groups;
    clear them freely. Only back off when the COMBINED pack sits above your
    level. And note many aggressive mobs attack you on sight anyway — you
    don't get to decline those fights, so enter their territory with HP
    topped up rather than trying to avoid them.
  - **Know your flee routes**: `flee` throws you through a RANDOM exit.
    Fighting next to darkness, a death room, or unexplored exits means a bad
    flee can be worse than the fight. Prefer fighting in rooms whose exits
    you've mapped.
  - Shopkeepers, healers, and other service mobs are usually unbeatable and
    killing them costs you their services — never worth it.
- Keep V above ~20 when exploring — running out of moves strands you.
- Buy food/water early; hunger halts regen.
- `recall` scrolls (if available in shops) teleport you back to the temple —
  cheap insurance for deep exploration.
- The `bug`, `typo`, `idea` commands file reports on this dev server; the MOTD
  encourages using them.
