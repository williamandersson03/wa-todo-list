.PHONY: run test compose-up compose-down

run:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

test:
	pytest -q

compose-up:
	docker compose up -d --build

compose-down:
	docker compose down
