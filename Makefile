.DEFAULT_GOAL := help

.PHONY: help
help: ## This help
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*? / {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

.PHONY: lint
lint: ## Linting project
	@echo Linting...
	uv run ruff check
	uv run mypy .

.PHONY: format
format: ## Apply formatting using black
	@echo Formatting...
	uv run black .
	uv run ruff check --fix

.PHONY: upgrade
upgrade: ## Update dependencies
	@echo Updating dependencies...
	uv lock
	uv sync

.PHONY: run
run: ## Run bot
	@echo Run project...
	uv run python -m app.main

.PHONY: test
test: ## Run tests
	@echo Test project...
	uv run pytest

.PHONY: test
coverage: ## Run tests with coverage report
	@echo Test project with coverage...
	uv run coverage run -m pytest
	coverage report
	rm .coverage
