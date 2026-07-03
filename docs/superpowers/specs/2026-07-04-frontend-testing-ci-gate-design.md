# Frontend Testing Harness + CI Gate — Design

- **Date:** 2026-07-04
- **Branch:** `feature/claude-frontend-testing-ci-gate-20260704`
- **Status:** Approved (pending spec review)
- **Related:** issue #62 (CI 強化), issue #63 (eslint — done in PR #73)

## Problem

The frontend has **72 `.ts/.tsx` source files and zero tests**. CI's `frontend`
job only runs `tsc -b` + `vite build`, so all runtime logic (API clients, zustand
stores, the WebSocket reconnect hook, utils) is completely unverified. eslint was
cleaned up in PR #73 but is **not wired into CI**, so lint regressions are not
caught. This is the highest-leverage quality gap in the project — the backend has
43 test files / 380 passing tests by contrast.

## Goal

Stand up a **vitest** unit-test harness and add two CI gates (**eslint** +
**coverage-thresholded tests**) to the existing `frontend` job. Establish a real
coverage baseline on the highest-ROI pure-logic modules and lock it in with a
**ratchet** threshold (only goes up, never down).

Non-goals for this work (explicitly deferred):

- Component / page tests (needs broader `@testing-library` render setup) — later phase
- Wiring Playwright e2e into CI (heavier: needs backend + postgres + frontend) — issue #62
- Backend coverage threshold — this work touches frontend only

## Approach

Chosen: **vitest + jsdom + `@testing-library/react`**, tests colocated next to
source (`foo.test.ts`), coverage scoped to logic directories, CI gains `lint` +
`test:coverage` steps.

Rejected alternative — **node-env only, no testing-library, skip `useWebSocket`**:
smaller harness, but leaves the WebSocket reconnect logic (rewritten in PR #73, the
module most likely to regress) untested. The incremental cost of jsdom +
testing-library is one dev dependency; worth it to cover that module.

## Design

### 1. Test harness

- **Runner:** `vitest` (v3, pairs with Vite 8 already in the repo) + `@vitest/coverage-v8`
- **Environment:** `jsdom` (needed by `useWebSocket` via `renderHook`, and by
  `download.ts` which creates an `<a>` element)
- **Config:** merged into the existing `frontend/vite.config.ts` via
  `/// <reference types="vitest/config" />` — no separate config file
- **Globals:** OFF. Test files use explicit imports
  (`import { describe, it, expect, vi } from 'vitest'`) so no eslint globals
  override is needed
- **Setup file:** `src/test/setup.ts` registers `@testing-library/jest-dom` matchers

New devDependencies: `vitest`, `@vitest/coverage-v8`, `jsdom`,
`@testing-library/react`, `@testing-library/jest-dom`.

### 2. Initial test scope (pure logic only)

Not every logic file — a representative, high-value subset that establishes the
harness and a real baseline:

| Area | Modules | How tested |
|------|---------|------------|
| utils | `pickPrimary.ts`, `download.ts` | pure functions; `download` asserts anchor creation/click in jsdom |
| hooks | `useWebSocket.ts` | `renderHook` + a fake `WebSocket` global; assert connect / reconnect-backoff / cleanup |
| stores | `deviceStore`, `monitorStore`, write-event flow | drive actions, assert state transitions; mock the `services/` layer |
| services | `api.ts` (base), `deviceApi.ts`, `writeEventApi.ts` | mock axios; assert URL/method + `{ data }` unwrapping |

Components and pages are **out of scope** for this pass.

### 3. Coverage threshold (ratchet)

- `coverage.provider = 'v8'`
- `coverage.include = ['src/utils/**', 'src/stores/**', 'src/services/**', 'src/hooks/**']`
  — scope the number to logic modules so it is meaningful and not diluted to ~0 by
  untested components/pages
- Run the suite, measure the actual baseline (estimate: lines ~40–55%), then set
  `coverage.thresholds` (lines/functions/statements/branches) **just below** the
  measured value (e.g. measured 50% → gate at 45%). Only ratchet up later.
- When component tests arrive, widen `include` and raise the thresholds.

### 4. package.json scripts

```json
"test": "vitest",
"test:run": "vitest run",
"test:coverage": "vitest run --coverage"
```

### 5. CI changes (`frontend` job in `.github/workflows/ci.yml`)

Additive only; existing steps stay. New order after `npm ci`:

1. `npm run lint` — **new gate** (eslint; already green from PR #73, just not in CI)
2. `npx tsc -b` — existing typecheck
3. `npm run test:coverage` — **new gate** (vitest with ratchet thresholds)
4. `npm run build` — existing

## Risks / Notes

- Turning on the eslint gate means a future warning will block PRs. This is
  intentional (regression prevention) but worth flagging.
- `download.ts` triggers a browser download (creates `<a>`, clicks it); it runs
  under jsdom and may need light mocking of `URL.createObjectURL` / click.
- The exact threshold numbers are set during implementation from the measured
  baseline, not guessed here.

## Testing / Verification

- `npm run test:coverage` passes locally with the ratchet threshold met
- `npm run lint` passes
- CI `frontend` job green on the PR with all four steps
- No changes to backend job

## Out of Scope (restated)

- Component/page tests, Playwright-in-CI (#62), backend coverage gate.
