.DEFAULT_GOAL := help

MAKEFILE_TARGET := $(filter-out ai-client --help Makefile,$(MAKECMDGOALS))
UV ?= $(if $(wildcard /opt/homebrew/bin/uv),/opt/homebrew/bin/uv,uv)
E2E_ARTIFACT_DIR ?= $(CURDIR)/.local/test-results/api-e2e

.PHONY: help
help: ## This help
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z0-9_-]+:.*? / {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

.PHONY: lint
lint: ## Linting project
	@echo Linting...
	$(UV) run ruff check
	$(UV) run mypy .

.PHONY: format
format: ## Apply formatting using black
	@echo Formatting...
	$(UV) run black src
	$(UV) run ruff check --fix

.PHONY: install
install: ## Install dependencies
	@echo Installing dependencies...
	uv venv --clear
	uv sync

.PHONY: deps
deps: ## Update dependencies
	@echo Updating dependencies...
	uv lock --upgrade
	uv sync --reinstall

.PHONY: run
run: .env ## Run app
	@echo Run project...
	uv run python -m src.main

.PHONY: run
run-in-docker: .env ## Run app
	@echo Run project in container...
	docker compose up app --build

.PHONY: test
test: .env ## Run tests with coverage report
	@echo Test project with coverage...
	$(UV) run coverage run -m pytest -v
	$(UV) run coverage report
	rm .coverage

.PHONY: test-full
test-full: ## Run regular tests with coverage, then API e2e tests
	$(MAKE) test
	$(MAKE) test-e2e

.PHONY: test-e2e
test-e2e: ## Run API e2e against PostgreSQL (uses DB_PASSWORD; optional E2E_POSTGRES_PASSWORD override)
	RUN_API_E2E=1 E2E_ARTIFACT_DIR="$(E2E_ARTIFACT_DIR)" $(UV) run pytest src/tests/e2e --confcutdir=src/tests/e2e -m e2e -q --junitxml="$(E2E_ARTIFACT_DIR)/junit.xml"

.PHONY: test-e2e-in-docker
test-e2e-in-docker: ## Run API e2e using the Compose test image and PostgreSQL
	docker compose run --rm -T --entrypoint pytest -e RUN_API_E2E=1 -e E2E_ARTIFACT_DIR=/tmp/api-e2e test src/tests/e2e --confcutdir=src/tests/e2e -m e2e -q --junitxml=/tmp/api-e2e/junit.xml

.PHONY: run
test-in-docker: .env  ## Run tests inside docker container
	@echo Run project in container...
	docker compose up test --build

.PHONY: run
lint-in-docker: .env  ## Run linting inside docker container
	@echo Run project in container...
	docker compose up lint --build

.PHONY: build-arm64
build-arm64: ## Build service and test images for linux/arm64
	@echo Building ARM64 images...
	docker buildx build --platform linux/arm64 --target service --tag code-agent:arm64 --load .
	docker buildx build --platform linux/arm64 --target tests --build-arg DEV_DEPS=true --tag code-agent:test-arm64 --load .

.PHONY: migration
migration: .env ## Make DB migrations
	@read -p "Revision: " db_revision; \
	uv run alembic revision --autogenerate -m "$$db_revision"

.PHONY: migrations-upgrade
migrate: .env ## Apply DB migrations
	@echo Migrations: apply revisions...
	uv run alembic upgrade head

.PHONY: migrations
downgrade: .env ## Downgrade (unapply) DB migration (last revision)
	@echo Migrations: downgrade last revisions...
	uv run alembic downgrade -1

.PHONY: secrets
secrets: .env ## Create new secrets
	@echo Encryption: creating new key
	uv run python -m src.modules.cli.generate_secrets
