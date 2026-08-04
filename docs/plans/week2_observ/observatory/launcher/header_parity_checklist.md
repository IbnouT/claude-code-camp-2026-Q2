# Application header parity checklist

Closing authority: `npm run test:parity` green. The header spec is
exhaustive: every element pair, every compared computed property, with each
declared difference named and justified inside the spec.

Every observable behavior of the reference header, from its source, with the
v3 status. Live-screen actions are deferred to the Live checklist, listed here
so nothing is silently dropped.

## Shell

| # | Behavior | Status |
|---|---|---|
| A1 | Brand mark and two-line name, links to the launcher at `/` | CLOSED |
| A2 | Brand link preselects the current player on the launcher | CLOSED |
| A3 | Four spaces with icons: Live, Sessions, Experiments, Knowledge | CLOSED |
| A4 | Active space marked, every space routed | CLOSED |
| A5 | Theme toggle at the end of the header | CLOSED |
| A6 | Header on every space, none on the launcher | CLOSED |
| A7 | Header surface: dark #070b10 override over the surface token, measured equal | CLOSED |
| A8 | Context area on Live carries only the switcher and theme control until the Live actions land | CLOSED |

## Context switcher

| # | Behavior | Status |
|---|---|---|
| B1 | Trigger: player, state, short session id | CLOSED |
| B2 | Panel: selected context with state and control availability | CLOSED |
| B3 | Leave Live view returns to the launcher, shown on Live only | CLOSED |
| B4 | Player selection through the Launcher and Sessions spaces | CLOSED |
| B5 | Latest three sessions, selectable, per the approved switcher design | CLOSED |
| B6 | Show all sessions with search | CLOSED |
| B7 | Refresh action | CLOSED |
| B8 | Stop session with confirmation, running sessions only | CLOSED |
| B9 | View recording opens the selected ended session | CLOSED |

## Deliberate differences from the reference

- Bare `/live` shows the header over empty content instead of redirecting to
  the launcher. Requested behavior.
- Experiments and Knowledge stay enabled because their routes exist. The
  reference disabled them as unbuilt.
- Review appears only in development. Production builds prove its absence.
- Context panel root computes `position: static`: the popover library
  positions through a dedicated wrapper, the panel lands at the same
  measured place.
- The reference wraps the switcher trigger in a positioning div that v3
  does not need. The trigger subtree is measured aligned from each trigger
  root, where the only residue is `inline-flex` computing `flex` because
  the v3 trigger is a direct flex item. Same rendered layout.
- Controls disabled pending the Live experience (Message agent, Ask)
  show the reference disabled treatment, dimmed with
  `cursor: not-allowed`, where the reference had them wired and active.
- The Sessions header is the Live header, one component on every space.
  The reference restyled the same elements per page. Its functional
  differences are kept: no Message agent outside Live, and session
  finding through the switcher and the Sessions space. Context actions
  live only in the switcher panel, the bar itself stays constant.
  Reaching Live needs no extra action, the Live space button already
  carries the context.
- The panel is exactly three blocks, the approved switcher design:
  Current, Recent sessions, and one footer row that views all the
  current player's sessions. The reference's Other players section and
  All sessions and players footer are gone, players change through the
  Launcher and Sessions spaces. The reference also showed five recents,
  the footer row carries the rest.
- Switcher session rows lead with the retained goal, with id and time
  beneath, falling back to the reference id-led row when no goal exists.
  Carries the reference Sessions picker's goal-first behavior into the
  one shared panel. The current section shows the goal the same way.
- On a recording's own page the Current action is View map recording,
  a deep link to `?view=map`, instead of a self link. Elsewhere it stays
  View recording to the Story view.

## Deferred to the Live screen checklist

- Message agent wiring. The button is present with the reference styling and
  stays disabled until control lands.
- Ask about this session wiring. The button and shortcut hint are present and
  stay disabled until the Live experience lands.

## Development-only

- The Review space is the development foundation gallery: tokens, primitives,
  and server-state review pages. It exists only in the development entry and
  the production boundary test proves it is absent from production builds.
