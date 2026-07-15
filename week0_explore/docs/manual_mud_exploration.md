# Manual MUD Exploration

Before building anything I played the game myself as a warrior and reached level 6. The goal was to understand what the agent will actually face, and what a player journey feels like from the inside.

## What I noticed while playing

- Hunger, thirst and movement points are consumable resources. Being hungry slows healing to a crawl, and running out of movement blocks walking.
- Healing means waiting. After a fight you sleep for minutes of real time before you can safely take the next one. An agent would have to deal with that waiting somehow.
- Combat runs in automatic rounds without input. The player only injects extra text like `kick`, which then locks your commands for a few rounds.
- I used `consider <mob>` before fights to gauge difficulty. So far its verdicts matched how the fights actually went.
- Dying loses the gold you carry but keeps XP, and there is a bank in town. Risk depends on what you carry at the moment.
- Some passages are one-way. The guild well drops you into the sewers with no way back up, and nothing warns you before you jump.
- The world resets over time. Doors close again, monsters respawn or wander away from where you first saw them. What you learned about a place can be outdated the next time you pass.
- Darkness hides everything (mobs, exits, room contents) until you carry a light. What you can perceive depends on your equipment.
- Inventory has an item count limit. I only found out when it stopped me mid-looting, with no prior indication.

## Where I got stuck

1. Lost in dark tunnels with no light and no map, died there.
2. Took the guild well without knowing it was one-way, stranded underground.
3. Inventory limit blocked me mid-looting.

## Map

A partial map of the areas I explored (town, newbie zone, sewers) is in [manual_exploration_map.png](manual_exploration_map.png). It only shows what I actually visited.
