# Observatory v3

Observatory v3 is the single production home for the rebuilt application.

```mermaid
flowchart LR
    Capture["Agent, gateway, and runtime evidence"] --> Backend["backend"]
    Backend --> Contract["typed HTTP and SSE contracts"]
    Contract --> Web["web"]
    Web --> Browser["Observatory"]
```

## Ownership

- `backend/` owns all new Observatory backend production code.
- `web/` owns the React application and its verification gates.
- No production source imports or executes code from `observatory/` or
  `observatory_v2/`.
- The older packages are temporary executable references only.
- Deleting both older packages must not affect v3 build, test, or runtime
  behavior.

## Current state

- The web foundation and contract boundary are implemented under `web/`.
- The bounded source repositories and versioned API live under `backend/`.
- Pydantic, OpenAPI, generated TypeScript, and Zod share one public contract.
- A disposable index provides stable hierarchy identities, bounded catalog
  reads, sanitized search, and canonical experiment-to-session correlation.
- A demand-aware materializer advances selected sessions from composite source
  cursors without reparsing their committed agent or gateway prefixes.

## Commands

Run frontend commands from `web/`.

```bash
cd week2_capable/observatory_v3/web
npm run check
npm run dev
```
