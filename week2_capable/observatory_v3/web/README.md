# Observatory v3 web

This package is the Observatory v3 React application. It consumes only the
typed API and live transport owned by the sibling v3 backend.

```mermaid
flowchart LR
    Browser["React client"]
    Router["TanStack Router"]
    State["TanStack Query"]
    API["v3 typed API"]
    Live["v3 live transport"]
    UI["shadcn source components"]
    Style["Tailwind CSS"]

    Browser --> Router
    Router --> State
    State --> API
    Browser --> Live
    Browser --> UI
    UI --> Style
```

## Foundation

- Node `24.18.0` and npm `11.16.0` are fixed by `.nvmrc` and package engines.
- Dependencies are exact and reproducible through `package-lock.json`.
- TypeScript is strict across application, configuration, and test sources.
- Oxlint checks React, imports, Vitest, and JSX accessibility.
- Vitest and Testing Library cover component behavior.
- Playwright and axe cover browser behavior and accessibility.
- Architecture checks block old Observatory imports and bypasses.
- Orval generates TypeScript and status-specific Zod Mini validators.
- Network values enter application code as `unknown` and validate in `src/data`.
- Production builds exclude the development review module.

The development server exposes the cumulative foundation review and the
deterministic backend B0 measurements. The production build exposes only the
production application boundary.

## Backend B0 evidence

- A generated development artifact records the measured current API path.
- The fixture contains 66 sessions and a stopped session with 2,233 gateway
  events and 1,040 agent records.
- Unrelated sessions retain 21,766 gateway events and 8,640 agent records.
- Measurements report p50 and nearest-rank p95 latency.
- Failure cards show unrelated-session hydration, full-history folding,
  unbounded detail payloads, and partial-line rejection.
- The measured artifact and review components are excluded from production.

## Commands

| Command                      | Purpose                                             |
| ---------------------------- | --------------------------------------------------- |
| `npm run dev`                | Start Vite with Fast Refresh                        |
| `npm run format:check`       | Check repository formatting                         |
| `npm run typecheck`          | Check TypeScript without emitting files             |
| `npm run lint`               | Run Oxlint across the package                       |
| `npm run architecture:check` | Enforce runtime ownership boundaries                |
| `npm run contracts:generate` | Generate types and runtime validators               |
| `npm run contracts:check`    | Check deterministic output and operation coverage   |
| `npm test`                   | Run component tests                                 |
| `npm run test:e2e`           | Run Chromium and axe browser gates                  |
| `npm run build`              | Typecheck, build, and inspect the production bundle |
| `npm run check`              | Run every landing gate                              |

## Dependency roles

| Dependency                   | Reason                                                           |
| ---------------------------- | ---------------------------------------------------------------- |
| React and React DOM          | Typed component runtime and browser rendering                    |
| Vite and React plugin        | Development server, Fast Refresh, and production build           |
| Tailwind CSS and Vite plugin | Zero-runtime utility styling                                     |
| shadcn and Base UI           | Repository-owned components over accessible behavior             |
| TanStack Router              | Typed URL and navigation state for the shell landing             |
| TanStack Query               | Request lifecycle and server-state ownership                     |
| Lucide React                 | Tree-shakeable interface icons                                   |
| Oxlint                       | Full-source TypeScript, React, import, and accessibility linting |
| Prettier                     | Deterministic source and Tailwind class ordering                 |
| Vitest and Testing Library   | Component behavior verification                                  |
| Playwright and axe           | Browser and accessibility verification                           |
| Orval 8.23.0                 | OpenAPI TypeScript and Zod generation                            |
| Zod 4.4.3 Mini               | Tree-shakeable runtime contract validation                       |

Router and server-state packages are installed but remain inactive until their
own accepted landings.

## Boundaries

- No runtime import may leave this package.
- No code or stylesheet from `observatory/` or `observatory_v2/` may become a
  dependency.
- Presentation components do not call `fetch` or create polling loops.
- Feature components do not author transport request or response types.
- API route literals and network transports remain inside `src/data`.
- Internal navigation does not use raw document or history APIs.
- Product routes and semantic visual tokens arrive only in their owning
  landings.
