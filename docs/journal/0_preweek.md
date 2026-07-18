# Preweek Technical Documentation

## Technical Goal

The technical goal of the preweek is to find the lowest architecture level that can support our Player Journey Agent, by testing the cheap levels on a real MUD and identifying what each level cannot do.

- An agent file read by the coding harness
- Agent skills with bundled scripts and file memory
- Decide with evidence whether the higher levels are needed and what they must provide

We also test everything on a small model (Haiku), because the agent will need long sessions and a strong model for every step will not be affordable.

## Technical Uncertainty

- I'm uncertain a coding harness built for code work can drive a live game, the game is one continuous telnet session while the harness runs one-shot commands.
- I'm uncertain a small model can play the game at all, and whether moving up architecture levels changes that or only model size does.
- I'm uncertain files can hold enough world and player state for long goals, and that the model will maintain them.
- I'm uncertain how we will know a goal was really achieved, other than trusting the agent's own report.

## Technical Hypotheses

- I think the telnet session will be the first blocker and a script will have to own the connection end to end.
- I think the small model alone will not be dependable, and that each responsibility moved from the model into code will recover part of the gap.
- I think markdown memory will work for short goals and break as the world map grows.
- I think instructions alone will not make the model keep memory or follow plans, something will have to enforce both.

## Technical Observations

- With only an agent file neither model could hold the game connection. Each wrote its own connection scripts, with different results on every run, and the small model reported goals as done that were not.
- Asking the model to keep memory files did not work at any level, they were never updated during play. When we moved that job into the skill's script, which updates the files from the game output as it arrives, memory became real and the model started navigating from its map instead of re-exploring.
- The script built the map by keying rooms on their names, and two rooms with the same name corrupted it. The game text gives no reliable identity for a room, we had to infer it from exits and connections and keep the real state in a structured store, with markdown as a readable view over it.
- We extended the skill so the model can set a persona for how it plays, write a plan whose conditions the script can verify, and get signals computed from its own play, like experience per kill. The verified plan worked, the model stopped at a danger it would earlier have walked into. The persona and the signals did not, the model set the persona itself and never followed it, and never read a signal before making a decision.
- When leveling up required a long run of repetitive fighting, the model launched a background subagent by itself to do the grinding. Cost also grew with every fight, since each combat round is a model call.
- Full detail in [explore_architectures.md](../explore_architectures.md)

## Technical Conclusions

- The telnet hypothesis held. A script owning the connection removed all of those failures, at every model size.
- The small model hypothesis held in an unexpected way. Haiku is dependable for everything code carries, and what it lacks is not knowledge but attention, it does not look at the data it already has when it decides.
- The markdown hypothesis held. World state needs identity and structure, plain files cannot carry it.
- New uncertainties set aside for weeks 1 and 2: whether putting the plan, persona, and signals directly into every model call fixes attention, whether consequences like a death and what it cost should be linked in the state or raised by the loop, and whether repetition can run as code with the model called only at decision points.
- Subagents and workflow platforms were skipped, one character on one connection gives them nothing to improve.

## Key Takeaway

Everything we moved from the model into code became dependable, even on the small model, and what is still stuck in the model, attention, verification, repetition, is why we will build our own loop.
