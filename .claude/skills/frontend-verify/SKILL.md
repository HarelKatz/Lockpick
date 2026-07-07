---
name: frontend-verify
description: Use when verifying or testing Lockpick frontend changes — graph features, UI behavior, bug fixes — via the Playwright e2e suite or a live browser check. Covers running make test-e2e, asserting canvas state through the window.__lockpick_graph__ hook (the graph is a <canvas>, invisible to the DOM), seeding deterministic data, and authoring a spec per feature. Use before claiming any frontend change works.
---

# Lockpick — Frontend Verification (our standard)

This is how we prove a frontend change actually works. The graph is drawn to an
HTML `<canvas>` (react-force-graph-2d), so it is **invisible to the DOM and the
accessibility tree** — you cannot assert on it by querying elements or text. Two
layers, always both:

1. **Committed specs** (`frontend/e2e/*.spec.ts`, Playwright) — deterministic
   regression. Run headless via `make test-e2e`. Every feature/bugfix adds one.
2. **Live browser check** (Playwright MCP) — exploratory, before a spec exists or
   to eyeball layout. Model drives the real browser.

## The one rule for canvas state

**Assert graph state as DATA, not pixels.** The app publishes a dev-only snapshot
on `window.__lockpick_graph__` (see ARCHITECTURE.md Rule #26):

```ts
{ nodeIds, highlightedNodeIds, visibleEdgeKeys, pathAnchorId, timeWindow, timeDomain }
```

Read it with `page.evaluate(() => window.__lockpick_graph__)` (specs) or
`browser_evaluate` (MCP). Do **not** screenshot the graph canvas for assertions —
force-layout node positions vary run-to-run, so `toHaveScreenshot` on the graph is
flaky. Reserve `toHaveScreenshot` for **stable chrome** (toolbar, the time-slider
bar, detail panels) if you need visual regression at all.

## Run the committed suite

```bash
make test-e2e          # spins up an ISOLATED backend (:8137) + dev frontend (:5273)
                       # on a throwaway DB, seeds a deterministic graph, runs specs
cd frontend && npm run test:e2e:update   # refresh screenshot baselines after an intended UI change
```

`playwright.config.ts` starts both servers itself (dedicated ports so it never
collides with a running dev/docker stack on 8000/5173) and `e2e/global-setup.ts`
seeds via `tests/e2e/seed_e2e.py`. You do **not** start anything by hand for the suite.

## The deterministic seed

`tests/e2e/seed_e2e.py` replays the 10-host `tests/fixtures/network` topology over
REST, then adds manual connections with **spread-out timestamps** (the fixtures all
share one hardcoded timestamp, so without these the time slider has no range).
Result: 10 hosts, 6 key-match edges, a multi-hop path, and dated connection edges.

Reach the seeded graph in a spec with the helper:

```ts
import { gotoGraph, graphState } from './helpers'
const op = await gotoGraph(page)   // injects sessionStorage, lands on the Graph tab, waits for nodes
const s = await graphState(page)   // reads window.__lockpick_graph__
```

## Authoring a spec for a new feature (the pattern)

1. If the feature adds render-state a test must see, **extend the hook** in
   `GraphCanvas.tsx`, the `graphState()` return type in `e2e/helpers.ts`, and
   ARCHITECTURE.md Rule #26 — in lockstep (never rename/remove existing fields).
2. Write `frontend/e2e/<feature>.spec.ts`: `gotoGraph` → interact (click, drag,
   keyboard) → assert on `graphState()`.
3. Run `make test-e2e` until green. Commit the spec with the feature.
4. Optional: initialize Playwright's Test Agents (`npx playwright init-agents --loop=claude`)
   for planner/generator/healer subagents that draft and self-heal specs. Not set up by
   default — its scaffolding is opinionated (drops a placeholder seed spec + `specs/`), so
   review what it generates before keeping it.

## Live browser check (Playwright MCP, no committed spec)

For quick exploration before a spec exists:

1. Start an isolated backend + seed once:
   ```bash
   cd backend && DB_PATH=/tmp/lp-e2e.db UPLOAD_PATH=/tmp/lp-e2e-uploads \
     uv run uvicorn main:app --host 127.0.0.1 --port 8137 &
   uv run --project backend python tests/e2e/seed_e2e.py --url http://127.0.0.1:8137
   API_PROXY_TARGET=http://127.0.0.1:8137 cd frontend && npm run dev -- --port 5273
   ```
2. Drive with Playwright MCP: `browser_navigate` to `http://127.0.0.1:5273`, inject
   sessionStorage (`lockpick_selected_op` = the op JSON, `lockpick_tab_<id>` = `graph`),
   reload, then `browser_evaluate(() => window.__lockpick_graph__)` to read state and
   `browser_take_screenshot` to eyeball layout.

## Files

- `frontend/playwright.config.ts` — servers, ports, isolated DB, screenshot config
- `frontend/e2e/global-setup.ts` / `global-teardown.ts` — seed + cleanup
- `frontend/e2e/helpers.ts` — `gotoGraph`, `graphState`, `seededOpId`
- `tests/e2e/seed_e2e.py` — deterministic REST seed
- `GraphCanvas.tsx` — the `window.__lockpick_graph__` hook
- ARCHITECTURE.md Rule #26 — the hook contract
