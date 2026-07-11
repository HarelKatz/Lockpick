.PHONY: run up down logs backup dev-backend dev-frontend test-full test-backend test-api test-parsers test-services test-scenarios test-real-examples test-unit test-e2e

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

# Full suite across every layer — backend + frontend unit + e2e. Serial + fail-fast:
# stops at the first red layer and names it, so an agent or CI sees exactly what broke.
# Layers run serially on purpose: backend pytest already uses every core (-n auto) and
# the e2e stack is timing-sensitive, so running layers concurrently risks flaky e2e for
# little gain — within each layer, tests already run in parallel.
test-full:
	@$(MAKE) --no-print-directory test-backend || { echo "=== FAIL: backend ==="; exit 1; }
	@$(MAKE) --no-print-directory test-unit    || { echo "=== FAIL: frontend unit ==="; exit 1; }
	@$(MAKE) --no-print-directory test-e2e     || { echo "=== FAIL: frontend e2e ==="; exit 1; }
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
