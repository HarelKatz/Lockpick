.PHONY: run up down logs backup dev-backend dev-frontend test

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
	cd backend && uv run pytest ../tests/ -v
