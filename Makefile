# AgencyDesk dev commands. Postgres runs in Docker (docker-compose.yml, host port 5433).
PYTHON ?= python3
VENV   := .venv
BIN    := $(VENV)/bin
PSQL   := docker compose exec -T db psql -U postgres -v ON_ERROR_STOP=1 -q

.PHONY: install env db-up db-reset migrate seed run test web-install web web-check check

install:                 ## create .venv and install backend deps
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install -q -r backend/requirements.txt

env:                     ## create .env from .env.example with a random SESSION_SECRET
	$(PYTHON) scripts/make_env.py

db-up:                   ## start Postgres
	docker compose up -d --wait db

db-reset: db-up          ## drop + recreate the dev DB, run migrations, load seed + dev role passwords
	$(PSQL) -d postgres -c 'DROP DATABASE IF EXISTS agencydesk WITH (FORCE)' -c 'CREATE DATABASE agencydesk'
	$(MAKE) migrate seed
	$(PSQL) -d agencydesk < db/dev_roles.sql

migrate:                 ## alembic upgrade head
	cd backend && ../$(BIN)/alembic upgrade head

seed:                    ## load db/seed.sql into the dev DB, plus placeholder bytes for seeded files
	$(PSQL) -d agencydesk < db/seed.sql
	$(PYTHON) scripts/seed_files.py

run:                     ## start the API on http://localhost:8000 (needs .env: `make env`)
	cd backend && ../$(BIN)/uvicorn app.main:create_app --factory --env-file ../.env --reload

test: db-up              ## run all tests (they create/drop their own databases)
	$(BIN)/pytest -q

web-install:             ## install frontend deps (exact versions from package-lock.json)
	cd frontend && npm ci

web:                     ## start the frontend on http://localhost:5173 (proxies /api to the API on :8000)
	cd frontend && npm run dev

web-check:               ## frontend: typecheck, unit tests, production build
	cd frontend && npm run typecheck && npm test && npm run build

check: test web-check    ## everything: backend tests + frontend checks
