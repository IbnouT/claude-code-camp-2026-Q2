# Player memory — dummy@localhost:4000

## Goals & notes (edit freely — this section is never auto-overwritten)
- Newbie Zone has limited monsters in accessible areas. Found: newbie monsters, creepy crawlers, Newbie Guard. Massive Minotaur likely in a restricted zone beyond dark passage or Chessboard area. Strategy: Hunt current creatures to level 3-5, then explore restricted areas.

<!-- AUTO — everything below is rewritten in real time by mud_session.py; edits below this line are lost -->

## Persona (apply this style to every decision)
balanced: probe shallowly before committing, flee at 50% health, gather intel first, experiment cheaply

## Plan (managed via `plan` subcommands)
Goal: Defeat the Massive Minotaur in the Newbie Zone
1. [x] Explore Newbie Zone and locate the Massive Minotaur  (check: item:map)
2. [ ] Hunt small creatures to reach level 3   ← CURRENT
   check [level>=3]: UNMET — level is 1, need >=3
3. [ ] Hunt medium creatures to reach level 5  (check: level>=5)
4. [ ] Defeat the Massive Minotaur  (check: level>=6)

## Vitals (live, from the game prompt)
HP 21 · Mana 100 · Moves 85  (max 21/100/85)

## Character (from the last `score`)
Dummy the Swordpupil — level 1
XP 436 (1564 to next level) · 0 gold

## Signals (computed — watch these, adapt strategy)
- Avg XP/kill (last 5): 113
- XP to next level: 1564 → ~14 more kills at this rate
- Moves: 85 now, +0 over the last 30 prompts
- Gold: 0 (+0 this session)
- Deaths recorded: 2
- Frontier: 26 untried exits across 32 mapped rooms

## Carrying (as of the last `inventory`)
(nothing)

## Current location
The Post Office — map, frontier and hazards in world.md

## Recent events (oldest first)
- Killed The creepy crawler (+34 xp)
- Killed The newbie monster (+153 xp)
- Killed The creepy crawler (+34 xp)
- Killed The newbie monster (+149 xp)
- Killed The creepy crawler (+36 xp)
- Killed The creepy crawler (+34 xp)
- Killed The newbie monster (+154 xp)
- Killed The creepy crawler (+33 xp)
- DIED near The Entrance To The Newbie Zone — respawned at the temple; corpse (with gear) left behind
- Killed The newbie monster (+308 xp)
- DIED near The Dirty Hallway — respawned at the temple; corpse (with gear) left behind
