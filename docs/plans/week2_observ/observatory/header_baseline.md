# Observatory header: item inventory, behaviour, and the shared baseline

Purpose: before touching the header, record what every item in every space
actually does and what data enables it, so the rebuild cannot silently break a
control. Anything not listed here is out of scope for the header work.

Baseline commit: `week2/v2-complete` after the consolidation commit.
Launcher is **out of scope** — it has no header and gains none.

## 1. Current owners

| Space | Component | Uses `ObservatoryHeader`? |
| --- | --- | --- |
| Live | `live/LiveHeader.tsx` | yes |
| Sessions | `sessions/SessionRoute.tsx` | yes |
| Experiments | `experiments/ExperimentRoute.tsx` | **no — hand-copied `<header className="live-header">`** |

`ObservatoryHeader` (`shell/ObservatoryHeader.tsx`) today owns brand, nav and
theme, and renders `children` into `.live-header-context`. All CSS lives in
`live-shell.css` under `live-*` names.

## 2. Item-by-item inventory

### 2.1 Brand

| Space | Markup | Behaviour |
| --- | --- | --- |
| Live | shared | `<a href="/">` → launcher |
| Sessions | shared | same |
| Experiments | duplicated | same target, separate markup |

No behavioural difference. Duplication only.

### 2.2 Navigation

Shared version renders four `<button>`s from a `spaces` list, each enabled only
when `destinations[id].href` exists, `aria-current="page"` on the active one,
and `title` used to explain why a space is unavailable.

| Space | Live | Sessions | Experiments | Knowledge |
| --- | --- | --- | --- | --- |
| From Live | active | `sessionsHref(playerId)` | disabled, title "Experiments will be rebuilt after Live" | disabled, title |
| From Sessions | `liveHref(...)` **only when `selected?.live`**, else disabled with title | active | `/experiments` | disabled, title |
| From Experiments | **`<a href="/">` — goes to the launcher, not Live** | `<a href="/sessions">` | active | disabled |

Two defects: Experiments uses `<a>` (hence underlines) and its Live link is
wrong.

### 2.3 Context slot

Three unrelated implementations. Content differs legitimately; the shell should
not.

**Live — `LiveContextSwitcher`** (395 lines)
- props: `catalog`, `identity`, `state: ContextState`, `onLeave`,
  `onNavigate`, `onRequestStop`
- `ContextState` = `checking | running | draining | stopped | ended | reconnecting`,
  held in `LiveShell` and set from the snapshot poll, plus
  `onStopping → draining` and `onStopFailed → running`
- renders a toggle button that opens a menu containing: leave live, request
  stop, jump to the recorded session, other sessions for this player, and a
  link to all sessions
- **this is the only place the operator can stop a session** — it must survive
  the rebuild

**Sessions — inline**
- player `<select>` bound to `catalog.players`, `onChange → changePlayer`
- then either a recorded-experiment chip (`experiment · <runId>`) when
  `recording !== null`, or `SessionPicker` bound to `sessions` with
  `onSelect → onSessionChange`

**Experiments — inline**
- comparison `<select>` bound to `catalog.comparisons`, `onChange → setComparisonId`
- monospace styling, different height and border from the other two

### 2.4 Primary action

| Space | Control | Enabled when | Handler |
| --- | --- | --- | --- |
| Live | `Message agent` | `identity !== null && selectedSession?.control_available === true` | `setMessageOpen(true)` |
| Sessions | **none** | — | — |
| Experiments | `New experiment` | always | `setAuthoring(true)` + writes `?mode=new` to the URL |

Classes differ: `.live-message-action` versus `.experiment-new`.

### 2.5 Ask

| Space | Label | Icon | Enabled when | Handler |
| --- | --- | --- | --- | --- |
| Live | "Ask about this session" | `Search` | `identity !== null` | `setAskOpen(true)` |
| Sessions | "Ask about this session" | `Search` | always | `setAskOpen(true)` |
| Experiments | "Ask this experiment" | **`MessageSquareText`** | always | `setAskOpen(true)` |

Experiments uses the wrong icon for an Ask control.

### 2.6 Theme toggle

Identical behaviour everywhere (`onThemeChange(theme === "dark" ? "light" : "dark")`),
but Experiments duplicates the markup.

## 3. Target baseline

- `ObservatoryHeader` owns brand, nav and theme. No space re-implements them.
- **One action class** — fixed height, radius, border, padding, icon size.
  Variants may change **colour only**, as v3 does (`Message agent` = warning).
- **One context-chip shell** — fixed height, border, radius, typography — with
  a variant per space for its contents.
- **Actions passed as a slot**, chosen in one place.
- Nav items are `<button>`, never `<a>`.

## 4. Rules that protect behaviour

1. Every handler in section 2 keeps its current trigger. In particular
   `onRequestStop` stays reachable — it is the only stop control.
2. Every enablement condition is carried over verbatim. `Message agent` stays
   bound to `control_available`; Sessions' Live nav item stays bound to
   `selected?.live`.
3. No new control is invented, and no existing control is dropped, without
   explicit approval first.
4. Experiments gains nothing beyond what it has; it only stops duplicating.

## 5. Header changes

- Sessions renders the shared header: the context chip, Ask, and theme. Its
  player `<select>`, inline picker, and recorded-experiment chip are removed.
  Player switching lives on the launcher.
- An experiment sample renders through the same chip with its run identity and
  the ended state.
- The chip's "View all sessions" row opens the session finder dialog in both
  Live and Sessions instead of navigating.
- Finder search matches everything its rows display: goal, lifecycle as
  displayed, date in displayed and ISO form, short or full session id.
- The chip carries no "Other players" group and no "All sessions & players"
  footer. Its recorded action is "View map recording".
- Live-only actions (Leave Live view, Stop session, Message agent) render only
  when their callbacks are passed. Stop stays reachable from Live, unchanged.

Owners after the rebuild: `shell/AppHeader.tsx` composes `ObservatoryHeader`,
`shell/ContextSwitcher.tsx`, and the actions. Live and Sessions both render it.
`shell/SessionFinderDialog.tsx` is the shared archive dialog. The header sits
outside any page typography scope, so both spaces compute identical styles.

## 6. Defects to fix while rebuilding

- Experiments "Live" points at `/`, should be a Live href.
- Experiments nav uses `<a>`, giving underlines the other spaces do not have.
- Experiments Ask uses a message icon instead of a search icon.

## 7. Test coverage that must stay green

- `live/LiveShell.test.tsx` — asserts header actions and the context switcher
- `sessions/SessionRoute.test.tsx` — asserts the Sessions header
- `experiments/ExperimentWorkspace.test.tsx` — asserts the Experiments surface

Frontend suite is 175 tests across 25 files at the baseline commit.
