# tbaMUD gameplay cheat sheet

All of these are sent through `mud_session.py cmd "<command>"`.
`help <command>` in-game gives the authoritative description.

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

Death drops your corpse (with your gear) where you died; you respawn at the
temple. `get all corpse` after returning.

## Communication

`say <msg>` (room), `gossip <msg>` (global), `tell <player> <msg>`,
`shout <msg>` (zone), `emote <action>`, `reply <msg>`.

## Practical tactics

- Midgaard (the starting city) is safe-ish. Wilderness and dungeons scale up fast.
- `consider` verdicts: "Now where did that chicken go?" = trivial,
  "You would need some luck!" and worse = do not engage.
- Keep V above ~20 when exploring — running out of moves strands you.
- Buy food/water early; hunger halts regen.
- `recall` scrolls (if available in shops) teleport you back to the temple —
  cheap insurance for deep exploration.
- The `bug`, `typo`, `idea` commands file reports on this dev server; the MOTD
  encourages using them.
