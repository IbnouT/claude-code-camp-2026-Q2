# Week 3 · The Observatory answers while a session runs

The app becomes unusable for minutes at a time while a run is live. It
recovers on its own once the session view is closed, which is the shape
of a load problem rather than a leak or a deadlock.

## What happens now

The session view asks for the whole story every two seconds, and the
whole story takes longer than two seconds to build.

```
browser                         backend                        disk
   |                               |                             |
   |-- GET /api/sessions --------->|-- sweep 122 rows ---------->|
   |-- GET investigation --------->|-- sweep 122 rows (again) -->|
   |   both every 2.0s             |-- sweep 122 rows (a third ->|
   |                               |   time, inside agent_events)|
   |                               |                             |
   |                               |-- sanitise the whole -------|
   |                               |   conversation and return it|
   |<------- 19.3 MB, 2.4s --------|                             |
   |                               |
   |-- GET investigation --------->|  arrives before the last one finished
```

Requests arrive faster than they complete, so the queue never drains.
Every handler is `async def` with its work inline, so the one slow call
holds the event loop and the app stops answering anything at all.

Measured on session `6df1300b`, the largest recorded:

| Component | Cost | Size |
| --- | ---: | ---: |
| `sessions()`, one sweep of 122 rows | 0.352 s | |
| `session()`, paid three times per request | 1.04 s | |
| `events()` | 0.012 s | |
| `project_runtime_session()` | 0.942 s | |
| of which `_agent_fields`, sanitised and returned | 0.601 s | 16.87 MB |
| of which `_agent_preview`, sanitised and discarded | 0.309 s | 0.28 MB |
| `model_dump` and JSON render | 0.105 s | 19.29 MB |
| `_journal_summary` on the largest journal | 0.001 s | |

Nothing caches, so the third identical call costs what the first did:
2.52 s, 2.10 s, 2.56 s.

## The causes, each confirmed in code

| Cause | Where |
| --- | --- |
| The live view polls the story every 2 s while live | `web/src/sessions/SessionRoute.tsx:173` |
| The same tick also refetches the whole session catalog | `web/src/sessions/SessionRoute.tsx:83` |
| The response carries the entire conversation, sanitised | `backend/projections/runtime_session.py:685` |
| Answering about one session builds all 122, three times per request | `backend/sources/runtime.py:185`, `app.py:307`, `app.py:313`, `runtime.py:301` |

The third row is the expensive one and it is not the preview path.
`_agent_fields` sanitises the retained payload and returns it, which is
16.87 MB of the 19.29 MB body. The previews that are cut to 240
characters cost a third as much and are the minor half.

`session()` calls `sessions()`, which runs `_session()` for every row in
every registry, and `_session()` opens each journal and reads each agent
log. One request pays that sweep three times: twice in the handler and
once more inside `agent_events()`.

The input grows during a run because `agent.jsonl` is quadratic. Every
model request embeds the conversation so far, so 1154 records occupy
16.9 MB against 1.28 MB flat.

## What changes

Four changes, in the order they pay.

### The story stops carrying the conversation, and keeps everything else

The conversation rides in five members of the field set built at
`runtime_session.py:640`: `messages`, `request`, `response`, `tools` and
`system`. `request` alone embeds the messages, the system prompt and the
tool schemas together. The remaining thirty eight members are small and
do not grow with the run, totalling 0.39 MB across all 1154 records.

The story therefore carries every field except those five, and gains one
new member, `last_message`, holding the role and content of the final
message. It is built inside the sanitised dictionary rather than beside
it, so it carries the same redaction as everything else, and it costs
0.07 MB across the whole session.

`MessagePreview` at `SessionStory.tsx:988` reads
`fields.messages` and takes the last entry, so it is rewritten to read
`last_message`. Left alone it would fall through to the 240 character
preview, which is a quieter regression than a blank but a regression
all the same.

Everything the story renders without being asked keeps its source: token
economics from `usage`, tool arguments from `args`, transform stages
from `stages` and `result`, room titles and the objective epoch that
`storyProjection.ts` builds from.

The five withheld members are served per record by a new endpoint, and
fetched when the reader opens the detail that needs them. Every place
they are read today:

| What | Where | Visible without expanding |
| --- | --- | --- |
| Full message list | `SessionStory.tsx:1004` | no, inside the model request detail |
| Tool schemas | `SessionStory.tsx:1024` | no, the same detail and a nested one |
| Raw field dumps | `SessionStory.tsx:908`, `:1118`, `:1183` | no, inside "Evidence and provenance" |
| Collapsed preview | `SessionStory.tsx:988`, rendered at `:690` | yes, and it moves to `last_message` |
| Prompt step subtitle | `SessionStory.tsx:1252`, rendered at `:687` | yes, and it already falls back to `message_count` and `tool_count` |

Two facts the endpoint has to carry, both of them ways this change could
undo itself:

- It applies `sanitize_evidence` to what it serves. `request` and
  `system` are exactly where a key, a token or a local path appears, and
  they are sanitised today at `runtime_session.py:685`. Moving them to a
  new path without redaction would open a wider bypass than the one this
  plan rejects below.
- It seeks one record rather than parsing the log. Record ids are
  `agent:{line}` at `runtime_session.py:158`, so the endpoint reads that
  line. Resolving through `agent_events()` instead would read and parse
  16.9 MB per fetch, and `EvidenceDetail` is attached to nearly every
  record in the story at `SessionStory.tsx:715`, `:733`, `:748`, `:762`,
  `:829`, `:855` and `:941`. A reader expanding a section, or a
  find-in-page that opens every `details` at once, would then cost
  seconds of held interpreter and gigabytes of churn. That is worse than
  the timer this change removes, because nothing bounds it.

The existing wire evidence endpoint does not cover this. It returns
`None` unless the record is a wire event, so it serves 785 of 4844
records and no agent fields at all. This is a new endpoint, not a reuse.

### The live view polls a cheap signal, not the story

A new endpoint reports whether anything has changed for a session, and
the view fetches the story only when it has. The signal covers both
records a session can produce:

- the journal's latest sequence, from `_journal_summary`, at 0.001 s
- the agent log's size, from one `stat`, which grows while the model is
  thinking and the journal is quiet

Gating on the journal alone would freeze the view during exactly the
phase the change exists to serve, because `model_request`, `plan` and
`response` records arrive with no gateway event beside them.

Three details the signal has to get right:

- A missing agent log reads as zero rather than failing, as
  `_initial_objective` already does.
- The comparison is "different from last time", not "larger", so a
  rewritten or truncated log still triggers a fetch.
- A fetch fired the instant the size changes can catch a half written
  final line. `agent_events()` raises on that at `runtime.py:316` and
  fails the whole request. Tolerating a trailing partial line belongs
  with this change, because this change aims a trigger at the moment it
  is likeliest.

The same tick stops refetching the session catalog. Today one revision
counter drives both effects, so the catalog sweep fires every 2 s as
well.

### One session is looked up by its key, once

`session()` gains an indexed query by `session_id`, with the same
per-row derivations `_session()` performs today and the same
`PRAGMA table_info` fallback for registries with no `stop_mode` column.
The existing `_session_dir` is not that lookup: it returns a path and
none of the row fields, so this is new code rather than a call swap.

The handler resolves the session once and passes it down, so the sweep
is paid once per request rather than three times.

### Handlers move off the event loop, and shared state is guarded

Handlers that read files or databases run in a worker thread. The cost
is CPU rather than I/O, so this is not a cure on its own: a single
`re.sub` or `json.dumps` holds the interpreter lock for its whole
duration. It is still correct, because it stops a slow request from
holding the loop across every await.

Two pieces of shared state are widened by that move and are guarded with
it:

- `AtlasSource` fills lazy caches with no lock at `sources/atlas.py:224`
  and `:282`
- the model spend counter at `app.py:982`, which guards a spend cap

`RuntimeSource._database` opens and closes per call, so it carries no
sqlite3 thread affinity problem.

## Built, measured, and taken out

Returning only the most recent records with a control to load older
ones. It was built and it worked: 0.29 MB and 210 ms against 3.74 MB and
470 ms without it.

It was removed after being seen in the app. Opening a session no longer
began at the session's beginning. The reader landed at Turn 2, iteration
122, with a small button that did not say a beginning existed. Every
heading that counted iterations then counted the loaded ones, so numbers
either had to be suppressed or answered from new whole-session fields,
and a mid-run goal change dropped its whole chapter.

The speed it bought was not the speed that mattered. The application
wedged because 2.4 s of work arrived every 2.0 s, and the change signal
alone ends that: work now arrives only when the session has actually
changed. Paying for the rest with the story's first half was a bad
trade, and the target it served was invented here rather than asked for.

A replacement was designed and rejected on measurement: an outline of
every turn and iteration, always whole, with the steps loading from the
beginning forwards. It reads well and it does not survive its own
numbers.

Every figure the outline carries is an aggregate over the records it
replaces, so building it means projecting all 4845 records first. The
outline is 0.0008 s of the 0.370 s, and with nothing cached each
contents request pays the projection again. Reading a session end to end
would cost the full projection once per batch rather than once. It
multiplies server work to save transfer, and transfer was never the
problem: the browser opens one iteration and holds the rest as collapsed
cards.

It would also have put the grouping rule, the iteration titles, the tool
summaries and the room title rule on the server as second copies, and it
needed a scroll trigger this codebase has no mechanism for. Story search
would have narrowed silently to loaded records and reported that as a
session count.

## Considered and rejected

Truncating previews before sanitising them, which the first draft of
this plan proposed. It is a credential leak, in three separate ways:

- `sanitize_evidence` redacts by key, and previews are built from dicts.
  `{"token": "super-secret-value"}` is redacted today and would not be
  after, because the JSON form does not match the value pattern.
- A secret straddling the 240 character boundary survives. A 40
  character credential at offset 231 is redacted today and exposed
  after.
- The output differs even with no secret present, because a replacement
  is a different length than what it replaced.

The preview path keeps sanitising before it truncates. What changes is
how many records it runs on.

The preview path keeps sanitising before it truncates, over every
record, as it always did.

## Judged by

- The story still opens at the session's first turn and every heading
  carries the numbers it carried before. The view is not the price of
  the speed.
- `/api/health` answers in under 50 ms while a live session view is
  open, measured against the running app rather than in a test.
- The story is fetched only when something has changed, so a session
  sitting in a model call costs nothing.
- The session view still updates within a few seconds of a new event
  during a model call, verified by watching a live run.
- Opening the model request detail on an old record still shows the full
  message list, the system prompt and the tool schemas.

## What this does not do

- No caching layer. The reads become cheap enough not to need one, and a
  cache over a live session is a correctness problem rather than a speed
  one.
- No change to `agent.jsonl` being quadratic. That is the agent's record
  format and belongs with the agent.
- No fix for `_gateway_records` setting fields with no sanitisation at
  `runtime_session.py:348`. Withholding the five heavy members narrows
  what reaches the browser through this endpoint, but the projection
  still builds unsanitised gateway fields and the new per record
  endpoint will serve them. It stays in the defect register.

## How it is built

### The two new endpoints

| Route | Answers | Cost |
| --- | --- | ---: |
| `GET /api/sessions/{session}/changed` | `{latest_seq, agent_log_size, live}` | one `PRAGMA`-free `COUNT` and one `stat` |
| `GET /api/sessions/{session}/records/{record}/fields` | the five withheld members for one record, sanitised | one file scan, one line parsed |

The change signal lands in `queries/live.py` beside the other reads. It
never opens the agent log, only stats it, so a growing log is seen
without being parsed.

The fields endpoint takes the record id the story already carries.
`agent:{line}` yields the line number directly. Reading it streams the
file counting newlines and parses only the line that matches, so the
parse and the memory are constant where they are proportional today.
The scan itself still walks the bytes, so this is roughly 0.08 s down to
0.01 s, not to nothing. A byte offset index would remove the scan too
and is not worth its invalidation problem at this size.

### What the reader sees

Nothing new is invented. Two existing idioms carry both changes.

- The withheld members reuse `StoryWireEvidence`. A new
  `StoryRecordFields` component follows it: a `story-wire-load` button,
  a loading label, an error paragraph with `role="alert"`, and the body
  rendered once loaded.
- The button matters beyond styling. Loading on a button press rather
  than on `details` opening means expanding a section costs nothing, so
  a find-in-page that opens two hundred details fires no requests at
  all.
- One fetch serves the whole detail body. `MessageBody` and
  `ToolSurface` are siblings inside the same `details` at
  `SessionStory.tsx:696`, and both want the same record. A component
  owning its own state at each site would issue two requests for one
  press, so the fetch is held once above them and the loaded payload is
  passed down.
- A record whose body was never captured shows the reason instead of a
  button, the way `StoryWireEvidence` handles a redacted wire record at
  `:49`. The signal is already beside it: `_evidence_capture_gaps`
  emits `model_request_body_not_retained` and
  `provider_response_body_not_retained`, and `EvidenceDetail` renders
  those gaps at `SessionStory.tsx:1119`. Offering a button that can only
  fail is worse than saying why.


`MessagePreview` reads `record.fields.last_message` instead of the last
entry of `fields.messages`, keeping its existing fall back to
`record.preview`.

### What breaks

| Change | What stops working until it is followed through |
| --- | --- |
| Five members withheld | `MessagePreview`, until it reads `last_message`. `MessageBody`, `ToolSurface` and the three raw dumps, until they fetch |
| Handlers threaded | `AtlasSource` caches and the spend counter, until they are locked |
| Catalog decoupled from the tick | Nothing. The catalog still refreshes on focus, on visibility and on demand |
| The same, in the suite | Four assertions in `tests/test_runtime_source.py:560-572`, which read `fields.system`, `fields.request.messages`, `fields.request.api_key` and `fields.response.content` |
| `MessagePreview` rewritten | The prompt fixture at `SessionWorkspace.test.tsx:68`, which supplies `fields.messages` and `fields.tools` and needs `last_message` |

The redaction assertion at `test_runtime_source.py:567` moves to the new
endpoint's tests rather than being deleted. It proves that `request` is
sanitised, and `request` is the member this change relocates, so
deleting it would remove the proof of the property the change promises.

Gateway records are untouched by all of it. `_gateway_records` withholds
nothing and keeps shipping its fields inline, which is why the
sanitisation gap there stays in the register rather than being closed by
this work.

### How a person checks it

In the app, with a live session open:

- The story keeps updating while a model call is in flight, which is the
  case the change signal exists for.
- Opening "Exact model request, system prompt, messages, and tool
  schemas" shows a button, and pressing it shows the full message list
  and the tool schemas.
- The system prompt shown there contains no key, no token and no local
  path.

At the terminal, against the running app:

- `/api/sessions/6df1300b-.../investigation` returns every record of
  the session, and the story opens at Turn 1.
- `/api/health` under 50 ms while that session view is open.
- `/api/sessions/{id}/changed` answering in single digit milliseconds.

## Quality bar

| Item | How this meets it |
| --- | --- |
| One responsibility per module | The change signal is a query, not a projection. It lands in `queries/`, beside the other reads |
| Public interfaces are typed | Both new endpoints answer with contract models, and the frontend consumes the generated types |
| Tests | pytest for the partial trailing line, the change signal during a model call, and the per record endpoint sanitising what it serves. Vitest for the polling change, the deferred field fetch, and the collapsed preview reading `last_message` |
| UI verified by rendering | The polling change and the deferred fetch are verified by watching a live session and opening the detail, not by reading the effect |
| Dependencies pinned and justified | No new dependency. Threading uses what Starlette already provides |
