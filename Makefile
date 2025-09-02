.PHONY: dev run test eval build up down fmt

dev:
	python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt

run:
	uvicorn app.main:app --reload

test:
	python -m pytest -q

eval:
	python scripts/eval.py

load:
	python scripts/load_test.py -c 50 -n 500

build:
	docker build -t agentic-proof-pack:latest .

up:
	docker compose up --build

down:
	docker compose down
