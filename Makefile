# AgencyDesk dev commands. Postgres runs in Docker (docker-compose.yml, host port 5433).
PYTHON ?= python3
VENV   := .venv
BIN    := $(VENV)/bin
PSQL   := docker compose exec -T db psql -U postgres -v ON_ERROR_STOP=1 -q

.PHONY: install db-up db-wait db-reset migrate seed test

install:                 ## create .venv and install backend deps
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install -q -r backend/requirements.txt

db-up:                   ## start Postgres
	docker compose up -d --wait db

db-reset: db-up          ## drop + recreate the dev DB, run migrations, load seed
	$(PSQL) -d postgres -c 'DROP DATABASE IF EXISTS agencydesk WITH (FORCE)' -c 'CREATE DATABASE agencydesk'
	$(MAKE) migrate seed

migrate:                 ## alembic upgrade head
	cd backend && ../$(BIN)/alembic upgrade head

seed:                    ## load db/seed.sql into the dev DB
	$(PSQL) -d agencydesk < db/seed.sql

test: db-up              ## run all tests (they create/drop their own databases)
	$(BIN)/pytest -q
