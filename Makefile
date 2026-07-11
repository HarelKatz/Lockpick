.PHONY: run up down logs backup dev-backend dev-frontend test-full test-backend test-api test-parsers test-services test-scenarios test-real-examples test-unit test-e2e test-fast test-invariants test-scale build fast-e2e test-scale-e2e gate

run:
	docker compose up -d --build && docker compose logs -f

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

backup:
	tar czf lockpick-backup-$(shell date +%Y%m%d-%H%M%S).tar.gz data/

dev-backend:
	cd backend && uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000

dev-frontend:
	cd frontend && npm run dev

# Full suite across every layer — backend + frontend unit + e2e. Serial + fail-fast by
# default: stops at the first red layer, and each layer prints a '=== ... ===' banner so
# an agent or CI sees exactly what ran and what broke.
# For ~30% faster on a multi-core box run the layers concurrently:
#   make -j3 --output-sync=target test-full   (measured 46s vs 64s serial, 16 cores)
# The layers then share CPU, so the timing-sensitive e2e runs a bit slower — prefer the
# serial default on small machines or when reliability matters most.
test-full: test-backend test-unit test-e2e
	@echo "=== PASS: backend + frontend unit + e2e ==="

test-backend:
	@echo "=== backend: pytest ==="
	cd backend && uv run pytest ../tests/ -n auto -q --tb=short

test-api:
	cd backend && uv run pytest ../tests/test_api/ -n auto -q --tb=short

test-parsers:
	cd backend && uv run pytest ../tests/test_parsers/ -q --tb=short

test-services:
	cd backend && uv run pytest ../tests/test_services/ -q --tb=short

test-scenarios:
	cd backend && uv run pytest ../tests/test_scenario_network.py ../tests/test_scenario_random_network.py -n auto -q --tb=short

test-real-examples:
	cd backend && uv run pytest ../tests/test_real_examples/ -q --tb=short

# Frontend unit tests (vitest) — pure logic extracted to src/utils/ (node env, fast).
test-unit:
	@echo "=== frontend unit: vitest ==="
	cd frontend && npm run test:unit

# Frontend end-to-end tests (Playwright). Spins up an isolated backend + dev
# frontend on dedicated ports and seeds a deterministic graph — see
# frontend/playwright.config.ts and the frontend-verify skill.
test-e2e:
	@echo "=== frontend e2e: playwright ==="
	cd frontend && npm run test:e2e

# ── Marker-driven tiers ──────────────────────────────────────────────────────
# Fast backend layer for the gate: everything except the property battery and
# slow/scale tests. (Markers are registered in tests/conftest.py — see the note
# in backend/pyproject.toml.)
test-fast:
	@echo "=== backend fast: pytest -m 'not slow and not property' ==="
	cd backend && uv run pytest ../tests/ -m "not slow and not property" -n auto -q --tb=short

# The hypothesis property/invariant battery (tests/test_invariants/).
test-invariants:
	@echo "=== backend invariants: pytest -m property ==="
	cd backend && uv run pytest ../tests/ -m property -q --tb=short

# Heavy/scale backend tests (scale(N) invariants). Nightly / on-demand.
test-scale:
	@echo "=== backend scale: pytest -m slow ==="
	cd backend && uv run pytest ../tests/ -m slow -q --tb=short

# Heavy scale(50) e2e layout invariants (chromium-invariants project). Nightly.
test-scale-e2e:
	@echo "=== frontend e2e (scale): playwright --project=chromium-invariants ==="
	cd frontend && npm run test:e2e:invariants

# Frontend typecheck + production build.
build:
	@echo "=== frontend build: tsc + vite ==="
	cd frontend && npm run build

# Fast e2e project only (committed specs; excludes the scale(50) sweep).
fast-e2e:
	@echo "=== frontend e2e (fast): playwright --project=chromium ==="
	cd frontend && npm run test:e2e:fast

# Sub-90s pre-PR gate: frontend build + unit + fast backend + fast e2e. Serial +
# fail-fast (prereq list, cheapest first); add -j for concurrent layers (recommended
# to stay under 90s — the fast e2e layer dominates). The heavier test-full runs
# everything; the nightly test-scale / test-scale-e2e run the scale sweeps.
gate: build test-unit test-fast fast-e2e
	@echo "=== PASS: gate ==="
