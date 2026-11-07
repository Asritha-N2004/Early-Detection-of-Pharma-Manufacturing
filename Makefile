.PHONY: test data backend frontend build docker
test:
	python -m pytest backend/tests -q
data:
	python scripts/generate_data.py
	python scripts/bootstrap.py
backend:
	python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8010
frontend:
	cd frontend && npm run dev
build:
	cd frontend && npm run build
docker:
	docker compose up --build
