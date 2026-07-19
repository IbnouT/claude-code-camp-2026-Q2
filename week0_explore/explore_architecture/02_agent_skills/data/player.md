# Player memory — dummy@localhost:4000

## Goals & notes (edit freely — this section is never auto-overwritten)
- Killing the janitor (a flavor/civilian mob, not a monster) dropped alignment from 93 to 38 and gave no gold — avoid killing town flavor NPCs (janitor, beggar, etc), stick to actual monsters/vermin like fidos.
- Already had a candle equipped as light source from character creation (plus sword, shield, staff, full armor set) — no need to buy a torch/lantern. Drank from the fountain at Temple Square for free thirst relief. Still hungry but HP/mana regen unaffected so far; food not yet found (general store only sells container/light items, inn sells drinks not food).
- User advised targeting level 7 (not just 4-5) before fighting the Massive Minotaur, for extra safety margin. Found a great grinding pocket in the sewers: 'Under The Dark Pit' (west of 'Under The Pit', reached via down from 'The Pit' east of the sewer entrance) has giant earth beetles worth ~3000 XP each ('Do you feel lucky, punk?' tier) plus maggots and sewer rats nearby worth 300-1000+ XP.
- Deposited 350 gold at the temple ATM (Temple Of Midgaard, south end) to protect against loss on death, per user reminder — kept ~48 on hand for shopping. ATM commands: deposit/withdraw <n>.
- 'The Pool' (west of Stalagmite Tunnel, via Spongy Room) is always dark even with a light source equipped, and something unseen touches your leg there — retreated without engaging since I couldn't assess the threat. Avoid or investigate later with more HP/levels. The 'Square Lair' area (north of Stalagmite T-Cross) has a puzzle room with colored dragon-head doors (Circular Hall) and named NPCs Jones and Herald (killed Herald, 'some luck' tier, 1356 XP) — no Minotaur sighting yet in this branch.
- 'The Southwestern Corner Of The Ledge' (north of An Odd Intersection) has a circular narrow ledge around 'a bottomless Abyss' — east exit is 'Mid-Air' (fall hazard) and the '(d)' edge exit leads to 'total destruction'. Both are death traps, avoid. No useful content found there; retreated to the known farming loop instead.
- Found 'A Dark Tunnel' (north of 'The Entrance To The Lair', which is west of North Tunnel, north of Square Lair/Jones's room) guarded by TWO guardian nagas — 'Are you mad!?' tier, far too strong even at level 6/87HP. Bones scattered on the floor there (past deaths). Likely guards something important (maybe the path toward the Massive Minotaur or treasure) — revisit at a much higher level.
- South of 'The Entrance To The Lair' is 'The Basilisk's Cave' with a scaled basilisk — also 'Are you mad!?' tier, too strong. This whole area (nagas + basilisk) is a high-level zone well above level 6; retreated. Sticking to the beetle/lemure/Jones-tier grinding pockets in the sewers/caves for now.
- Mercenaries in The Dark Alley (east of Common Square) are 'Fairly easy' at level 6 and give ~830-840 XP each (5 of them spawn there) plus gold/weapon drops — great in-town XP source. BUT a cityguard can wander in and 'jump to the aid' of the mercenary being attacked, forcing you into an accidental guard fight (guards are dangerous, above-level). Fled successfully at full HP with . Watch for guard arrival and flee immediately if one joins.
- DANGER: The Great Chessboard of Midgaard (reached via countryside north of the Temple's back exit → Great Field → west split path → rusty gate archway) has aggressive chess-piece bosses. The Black King (found deep in the board, several squares in) is 'Are you mad!?' tier and hit me for 21-23 damage per hit, dropping me from 97 to 15 HP in just 3 rounds — nearly died. It attacked immediately without me issuing 'kill', so entering its square is enough to trigger combat. AVOID the Chessboard's King/Queen squares entirely until much higher level. No Minotaur found there so far.
- DEFEATED the Massive Minotaur! Found it in 'A T-Intersection In The Passage' inside the Newbie Zone's hidden lower dungeon (accessed via: countryside north of Temple's back exit -> Great Field -> east split -> Entrance to Newbie Zone -> north into the zone -> through the hallways to the Alchemist's Room -> down the stairs past the 'level 7 minimum' warning sign -> into the maze -> east from Crossing of Corridors -> north -> west -> T-Intersection). It was aggressive (attacked alongside a zombie), 'The perfect match!' tier at level 7/97 max HP, gave 1668 XP. Fight lasted ~15 rounds, ended at 81/97 HP (83%) — no real danger once actually engaged. The earlier 'sewers Massive Minotaur' assumption was wrong; the real one is in the Newbie Zone's secret dungeon, consistent with the level 4-7 sign requirement.

<!-- AUTO — everything below is rewritten in real time by mud_session.py; edits below this line are lost -->

## Persona (apply this style to every decision)
Efficient grinder: fight anything near my level, avoid trivial kills that waste time, avoid fights I'd likely lose, retreat below 30% HP, always carry a light before going underground.

## Plan (managed via `plan` subcommands)
Goal: Defeat the Massive Minotaur
1. [x] Scout the city, eat/drink, learn shops and sewers entrance  (check: item:lamp)
2. [x] Level up to 4-5 hunting the sewers (vermin swarms good XP) with a light source  (check: level>=4)
3. [x] Consider the Massive Minotaur, gear up if needed, then engage  (check: level>=4)
4. [x] Push further to level 7 for a safer margin before engaging the Massive Minotaur  (check: level>=7)
5. [x] Search for and locate the Massive Minotaur  (check: room:Minotaur)
6. [ ] Engage and defeat the Massive Minotaur   ← CURRENT
   check [room:Minotaur]: UNMET — current room is A T-Intersection In The Passage

## Vitals (live, from the game prompt)
HP 97 · Mana 100 · Moves 98  (max 97/100/98)

## Character (from the last `score`)
Dummy the Veteran — level 7
XP 81287 (43713 to next level) · 768 gold

## Signals (computed — watch these, adapt strategy)
- Avg XP/kill (last 5): 683
- XP to next level: 43713 → ~65 more kills at this rate
- Moves: 98 now, +0 over the last 30 prompts
- Gold: 768 (+758 this session)
- Deaths recorded: 0
- Frontier: 133 untried exits across 163 mapped rooms

## Carrying (as of the last `inventory`)
- a dagger
- a bright green newbie vest
- a shiny newbie dagger ..It has a soft glowing aura!
- some cool newbie leggings
- some cool newbie sleeves
- a glowing newbie mace ..It has a soft glowing aura!
- a wee little key
- a small sword
- the teleporter
- a warhammer
- a bright newbie helm ..It has a soft glowing aura!

## Current location
A T-Intersection In The Passage — map, frontier and hazards in world.md

## Recent events (oldest first)
- Killed The small bat (+33 xp)
- Killed The small bat (+33 xp)
- Killed The mercenary (+833 xp)
- Killed The mercenary (+843 xp)
- Killed The mercenary (+833 xp)
- Killed The cityguard (+5092 xp)
- LEVEL UP! Now level 7
- Killed The mercenary (+835 xp)
- Killed The mercenary (+833 xp)
- Killed The zombiefied newbie (+533 xp)
- Killed The zombiefied newbie (+538 xp)
- Killed The smart newbie (+833 xp)
- Killed The zombiefied newbie (+533 xp)
- Killed The zombiefied newbie (+538 xp)
- Killed The zombiefied newbie (+533 xp)
- Killed The zombiefied newbie (+533 xp)
- Killed The quasit (+300 xp)
- Killed The newbie monster (+138 xp)
- Killed The newbie monster (+235 xp)
- Killed The annoying newbie (+133 xp)
- Killed The newbie monster (+133 xp)
- Killed The pit beast (+833 xp)
- Killed The zombiefied newbie (+533 xp)
- Killed The smart newbie (+849 xp)
- Killed The talkative newbie (+300 xp)
- Killed The annoying newbie (+133 xp)
- Killed The zombiefied newbie (+540 xp)
- Killed The massive Minotaur (+1668 xp)
- Killed The zombiefied newbie (+533 xp)
- Killed The zombiefied newbie (+540 xp)
