# Observatory · Header context

## Goal

The header answers "what am I looking at" and offers, in one place,
everything else the user could look at. Player and session are one
context, not two independent controls: a view is identified by its
session, and the session owns its player. Every control in the header has
exactly one predictable result; a choice that leads nowhere is not shown.

## Context chip

One chip replaces the player and session controls:

    poucet · ● running · a4da9f6a

It shows player, lifecycle state and short session id for the current
view. Clicking opens a popover (not a native select, because it mixes
navigation with lifecycle actions).

## Popover

Ordered groups; every row navigates somewhere that exists:

1. Current — the session being viewed, with its lifecycle actions:
   Leave Live view, and Stop session… only while running.
2. The current player's recent sessions (about five): live first, then
   recordings newest first, each with time and event count. A recording
   opens in Sessions. A final row "View all <player> sessions (N)" opens
   the Sessions space filtered to that player.
3. Other players — one row each: their live session if running, else
   their latest recording. A player with no sessions has no row.
4. Footer — "All sessions & players" opens the Sessions space
   unfiltered.

Keyboard: arrows, typeahead, Enter, Escape closes with focus return.
Depth never exceeds chip → shortcut rows → Sessions space; the popover is
a quick switcher, the Sessions space is the archive.

## Chip states

- running — live indicator; Stop available.
- draining — stop in progress; write controls locked.
- stopped — offers "View recording"; Stop absent.
- ended — a link to a session that has ended; recording CTA, no Stop.
- reconnecting — transient catalog failure: the last verified identity
  stays visible, writes are disabled, and neither a stop nor a redirect
  is ever claimed. Only a verified missing session redirects to the
  launcher.

## Data

One request: the sessions catalog already carries the roster and all
rows. Group by player, sort live first then most recent. No snapshots,
no extra calls. The v2 frontend contract retains the catalog's lifecycle
fields (state, capture status, control availability) instead of reducing
them to a boolean. Stop provenance (cooperative or forced) is served as
an explicit field for Sessions.

## Acceptance

- No dead or disabled rows in any state of the catalog.
- Chip state transitions follow the lifecycle exactly; a connection loss
  never shows a false stop.
- Keyboard interaction complete; focus returns to the chip on close.
- One catalog request serves the whole popover.
