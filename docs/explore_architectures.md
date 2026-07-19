# Explore Agent Architectures

There are many ways to build an agent and their responsibilities overlap, so it is hard to know which level of complexity our Player Journey Agent actually needs. We explore the options from the simplest up and only move up when the current level is not enough.

## 1. An agent file with a coding harness

The simplest way to get an agent is an agent file (CLAUDE.md in our case) read by a coding harness. We write no code, the file is the only control we have.

We wrote the CLAUDE.md from our manual play: connection details, login sequence, a few basic commands, and an instruction to keep memory in data/player.md and data/world.md. Goals are entered as the prompt. We used the suggested goal "Find the bakery and list what is on the menu" plus a second one, "find the warrior guild and report which skills you can practice there", to confirm the results on more than one task. Models: Haiku 4.5 first, then Sonnet. The memory files start empty for every run.

### Technical Observations

Both models drove the game through code they wrote. The harness executes one-shot commands while the game is a live session, so each agent had to build its own telnet bridge before it could play at all.

Haiku cannot read the live session. Its scripted inputs went out of sync with the game prompts and it misread its own successful logins as password failures. To get around a credentials problem that did not exist, it created two new characters.

Haiku keeps no record of where it has been. On the guild goal it revisited the same rooms until the character was stuck in a no-exit room, then reported the goal as completed using skill lists from the help pages.

Haiku is not repeatable. It passed the bakery goal once and failed the same goal on a rerun, with a different method each time.

Sonnet completed both goals in minutes. It reused one connection script, corrected its own mistakes from the game text, and its reports matched what actually happened.

Neither model updated the memory files during play. Sonnet wrote them only at the end, including connection notes on the exact traps Haiku kept relearning.

Neither model read unrelated repository files. Both stayed inside the experiment folder for the whole run.

Sonnet knows this stock world from training. It identified the warrior guild on sight and confirmed afterwards that it has the general layout memorized. These results overstate what to expect on a private world.

### Technical Conclusions

The login and connection flow is deterministic. Making the model rediscover it every run is wasted tokens, a script should own it, and a dedicated SDK around the game connection is the dependable form of that. An MCP server could expose such an SDK as tools to the agent, we have not tested this.

Memory by instruction does not happen. If we want memory the loop has to force the reads and writes, and whether markdown files can hold real world state is still untested, no run got far enough.

Completion claims from the agent cannot be trusted. We caught false successes only because we know the game. Goal verification must sit outside the model.

The gap between Haiku and Sonnet is the model, not the architecture, but running a strong model on errands is not cost effective. The point of a better architecture is to make the small model dependable: owned connection, enforced memory, external verification.

This level is usable for trivial goals with a strong model. It is not a fit for our agent's actual job.


## 2. Agent skills

One step up from the agent file is a skill: instructions bundled with their own scripts, loadable by most coding harnesses and agent SDKs. At this level we can finally give the agent code.

We had the agent generate a Play MUD skill whose script owns the connection and the login, which is the fix our level 1 conclusions asked for. We ran the same goals with the same models as level 1 so we can compare. Then we extended the skill twice and gave it a longer goal, level up enough to defeat the Massive Minotaur in the Newbie Zone, on Haiku both times.

The first extension makes the script update the memory files in real time from the game output. The second adds a plan file with conditions the script can check, a persona, and signals computed from the collected data like experience per kill and unexplored exits.

### Technical Observations

The generated skill connected and played reliably from the first run. No model wrote its own telnet code again and Haiku completed the bakery goal on the first try. The connection problems from level 1 are gone.

On the guild goal Haiku read practicing skills as fighting the guildmaster, attacked it and died. When the model does not know a game rule it guesses, and we find out after the damage. We can patch each rule into the skill reference once we see it fail, but on a world the model has never seen in training there will be many of these, so it needs a cheaper way to learn rules than dying.

The real-time memory worked. The files were updated on disk while the game was played and the model used the map to navigate back instead of re-exploring. But keying rooms by their title corrupted the map as soon as two rooms had the same name. The game text gives no stable identity for a room, we had to infer it from exits and connections, and the markdown ended up as a readable view over a structured store. For an agent whose whole job is mapping a world, plain markdown notes will not be enough.

On the first minotaur run the model made a sensible plan, level up first, then descend. Then it descended at level one anyway and got stuck in a dark maze. A plan written in prose does not constrain anything. When we moved the plan into a file with conditions the script can verify, like a level reached or an item held, the rerun turned back at the warning sign instead of pushing on. But the model also wrote one condition that tested nothing, so I think goals and their checks have to come from outside the model.

These failures are the same places a human beginner struggles in this game, darkness and fights above your level, the difference is a human learns after one death.

The persona and the signals were both ignored. The model set a persona itself and then did not follow it in a single fight, and the signals were computed on every memory read and never used in a decision. It is not that the model cannot use its data. When it was blocked by darkness it searched its memory, remembered a glowing helm and went to get it as a light source. It is that nothing at this level makes it look at the data at the moment it decides. A loop we own could inject the plan status, the persona and the signals into every call, so no decision is taken without them. Whether persona should even be text, or just rules in code like flee under a health threshold, is open.

The character died twice and lost its equipment in the corpses, and the model never connected the losses to the deaths. Our memory records events but not consequences. Maybe the state needs cause links, a death entry pointing to the corpse and what was lost. Maybe the loop should simply tell the model after a death what it cost. We have not tested either.

Long goals are expensive here because every combat round goes through the model. Halfway through, the model spawned a background subagent on its own to do the grinding, which I read as the agent telling us the same thing the cost does: grinding is a fixed fight and rest cycle and should be code, with the model called only at decision points like a new room, low health, or a plan step done.

### Technical Conclusions

Skills work well. Everything we moved into the script, connection, login, memory upkeep, plan checking, became dependable, even on the small model. The ideas that stayed as text for the model to read, persona, signals, plans in prose, are the ones that failed.

So the limit of this level is attention, not knowledge. We cannot make the model read the right data at the right moment from inside a skill, and we cannot see or change the harness loop that decides what the model gets. We need our own loop: inject the state into every call, verify goals in code, link consequences to causes, and run repetition as code.

We skip the subagent and workflow platform levels. One character on one connection gives nothing to parallelize, and they do not give us the loop either. Next we build the loop.


## 3. Watching the agent play

We built a live viewer (week0_explore/visualizer) for the play sessions of the level 2 skill: the agent's memory drawn as a map that grows during play, plus vitals, plan state, and current activity. It only reads files the skill's session already writes, so it costs no tokens and the agent is not aware of it.

### Technical Observations

All the data the viewer needs was already on disk: the memory store, the plan file, the session transcript. What the agent is doing (fighting, resting, shopping) is derived from the transcript.

Watching the play exposed gaps faster than reading the files, and each one became a skill improvement. The agent walked into rooms knowing nothing about them, so the skill now records the destinations the exits command names without walking there. It left corpses unlooted and carried gold into dangerous areas, so it gained autoloot and a banking rule. Combat reflexes moved to game settings, the game runs fight rounds itself, so the model only decides to engage, continue, flee, or rest, and a fight costs two or three model calls instead of one per round.

The viewer hit the room identity problem again: rooms sharing a name collided on the map. Titles cannot identify rooms, so the viewer resolves identity from the server's own world files, localizing the agent on the real map by replaying its session. The playing agent keeps only its discovered knowledge.

We first asked the model to write a one-line intent for the viewer. It forgot, like it forgot the persona. Reading its narration from the session log worked instead.

Given the one fact it could not find, the minotaur's location, the agent completed the challenge at level seven with zero deaths.

### Technical Conclusions

Watching the agent is how we found what to fix, and it cost nothing because all state lives on disk. The custom loop should keep its state on disk for the same reason.

Derive state from what the agent produces, do not depend on it reporting. True for memory, true for intent.

The last blocker was knowledge. One supplied fact completed the challenge, so on a private world the loop's exploration and memory must be able to produce such facts.
