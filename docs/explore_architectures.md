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
