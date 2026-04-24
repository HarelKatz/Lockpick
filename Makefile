.PHONY: run up down logs backup dev-backend dev-frontend test test-api test-parsers test-services test-scenarios

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

test:
	cd backend && uv run pytest ../tests/ -n auto -q --tb=short

test-api:
	cd backend && uv run pytest ../tests/test_api/ -q --tb=short

test-parsers:
	cd backend && uv run pytest ../tests/test_parsers/ -q --tb=short

test-services:
	cd backend && uv run pytest ../tests/test_services/ -q --tb=short

test-scenarios:
	cd backend && uv run pytest ../tests/test_scenario_network.py ../tests/test_scenario_random_network.py -q --tb=short
