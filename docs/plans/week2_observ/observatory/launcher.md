# Observatory · Launcher

## Goal

The launcher is the Observatory's entry screen. It answers one question the
moment the app opens: what can I do right now? Watch a session that is live,
start a new one, or load a recorded one. It carries no application shell:
the space navigation appears only once a context is open, because enabling
navigation before any session exists would present actions that cannot yet
mean anything.

Any deep link (a URL naming a space, session or player) bypasses the
launcher entirely. The URL always wins.

## Visual authority

`launcher_mock.html` in this folder is the binding visual reference. Tokens
map 1:1 to `tokens.css`; the light theme must work unchanged. The backdrop
is a fixed decorative constellation, independent of session data.

## Data

- On mount, one call to the sessions API supplies players, live flags and
  session times. One snapshot call supplies the selected profile's stats.
- Stats shown for an ended session are labeled as observed in the last
  session. A status field that was never observed is absent, not dashed.
- A configured profile with no sessions renders name and sigil only, with
  "no sessions yet". The roster source must include configured players
  with zero sessions, which the sessions API alone cannot provide.
- The screen never claims a player's current location. Between sessions the
  game may move a character in ways the Observatory cannot observe, so
  location text appears nowhere on this screen.

## Roster

The launcher is always a roster of player profiles; the selected tile is
always expanded to the full character card. One profile yields a single
auto-selected expanded tile; several profiles yield compact tiles with one
expanded. One component, two densities.

- Order: live players first, then most recent session, then name.
- Default selection: the single live player when exactly one is live,
  otherwise the most recently active player.
- Compact tile: sigil, name, live pulse when live, level, HP micro-bar,
  and either "LIVE now · turn N" or "last session · time".
- Expanded tile adds full HP and mana bars with numbers, gold, and the
  observed-in-last-session label.
- Tiles are keyboard reachable; Enter or Space selects.

## Watch live

Rendered only when at least one session is live; absent otherwise, never
disabled. One row per live session, naming the live player with turn and
spend from the live snapshot. Selection-independent: it names whoever is
live regardless of which tile is selected. Opens the session's Live view.

## Start a new session

The header carries the selected player prominently, and the action button
repeats it, so there is no ambiguity about which character starts.

Enabled only when the selected player is not live and the supervised
launcher is ready. A running gateway is not a prerequisite: the launcher
starts the gateway child. Failures surface inline as typed errors.

Two checkboxes, both unchecked by default. Unchecked means the player
resumes where they left the game, handled by the MUD itself.

- Reset to Temple location: a typed relocation operation moves the player
  to the Temple before the session starts. It runs after the mortal
  gateway authenticates and before the first model call, uses only
  privileged one-shot admin operations, verifies the destination room and
  retains a receipt as evidence. Player fields are untouched.
- Reset to baseline: the versioned baseline reset. It restores vitals and
  the versioned fields (level, experience, gold, bank, alignment, hunger,
  thirst) and places the player at the Temple. Inventory is not part of
  the baseline contract.
- The two resets are mutually exclusive in both directions: selecting
  either deselects the other. Neither is ever disabled, so switching
  choice is always a single click.

Submitting posts the player and reset choice to the typed start endpoint,
which delegates to the existing supervised launcher lifecycle (locking,
child startup, cleanup) and returns the new session id. The form locks
while starting; success navigates to the session's Live view. The browser
never receives credentials or spawn commands.

## Load a session

A count chip shows the selected player's recorded sessions against the
total. Expanding lists ended sessions newest first with time, event count
and duration; a toggle widens the list to all players. Sessions carry no
outcome badges: success and failure belong to benchmarks and experiments,
which use sessions but are not sessions. Loading opens the recorded run in
the Sessions space.

## Session lifecycle from the launcher

Stopping a session elsewhere in the app must reflect here from the
registry: a live row disappears when its session reaches a terminal state,
the tile's live indicator clears, and Start re-enables only once the
character lock is released.

## Keyboard

Escape collapses an expanded start form or load list. All interactive
elements are tabbable with a visible focus ring.

## Acceptance

- Rendered comparison against `launcher_mock.html` at 1440x900.
- Watch is absent, not disabled, when nothing is live.
- Start is disabled with an explanation when the selected player is live.
- Selecting either reset deselects the other, in both directions.
- A zero-session profile renders without invented values.
- Deep links bypass the launcher.
- No location text anywhere on the screen.
