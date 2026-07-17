# World Notes (Midgaard)

## Map (relevant area)

Temple Of Midgaard (start room, exits n e s w d)
  d -> Temple Square (exits n e s w)
    w: Clerics' Guild, e: Grunting Boar Inn
    s -> Market Square (exits n e s w)
      n: Temple Square, s: Common Square, e/w: Main Street
      w -> Main Street (general store north, Pet Shop south) (exits n e s w)
        w -> Main Street (Armory south, **Bakery north**) (exits n e s w)
          n -> **The Bakery** (exit s) — baker NPC here
          w -> Main Street (Guild of Magic Users south, Magic Shop north, city gate west) (exits n e s w)
            n -> Magic Shop (exit s only)
      e -> Main Street (weapon shop north, Guild of Swordsmen south) (exits n e s w)
        e -> Inside The East Gate Of Midgaard (exits e s w) — Water Shop south, leads out of town east
    s -> Common Square (exits n e s w)
      w: poor alley, e: dark alley (unexplored)

## Findings

- The Bakery: small shop on Main Street, 2 rooms west of Market Square then 1 north.
  Sells:
    1) A danish pastry — 7 gold
    2) A bread — 14 gold
    3) A waybread — 72 gold
  Baker NPC stands behind the counter; there's also "a small sign on the counter" (not yet read).
- Magic Shop sells: gnarled staff (828), gray wand of invisibility (473), scroll of recall (236),
  yellow potion of see invisible (473), scroll of identify (5914).

## Connection notes

- telnet negotiation eats early input; wait ~3s after connecting before sending the name.
- Login sequence when creating/logging fresh: name `dummy` -> password `helloworld` -> "PRESS RETURN" (send anything, e.g. `1`) -> game menu -> `1` to enter game.
- If reconnecting while character is still marked in-game, server skips straight to "Reconnecting." and drops you back in the game (no menu choice needed) — sending extra `1`s in that case produces harmless "Huh!?!".
- Always `quit` at a safe spot (bakery is safe) before ending session.
