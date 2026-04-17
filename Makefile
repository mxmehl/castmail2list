# SPDX-FileCopyrightText: 2025 Max Mehl <https://mehl.mx>
# SPDX-License-Identifier: CC0-1.0

.DEFAULT_GOAL := help
.PHONY: help check-requirements setup pytest ruff ty reuse test-all


help: ## Show help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

PYTHON = python3
UV = uv
APPDIR = castmail2list

check-requirements: ## Check if Python and uv are installed
	@command -v $(PYTHON) >/dev/null 2>&1 || { \
		echo "Python 3 is not installed. Please install it from https://www.python.org/downloads/"; \
		exit 1; \
	}
	@command -v $(UV) >/dev/null 2>&1 || { \
		echo "uv is not installed. Please install it from https://docs.astral.sh/uv/getting-started/installation/"; \
		exit 1; \
	}

setup: check-requirements ## Install dependencies: install dependencies via uv
	$(UV) sync

# -----------------------------------
# Testing targets
# -----------------------------------
pytest: ## Run pytest: unit tests
	$(UV) run pytest --cov=$(APPDIR)

ruff: ## Run ruff: lint and format check
	$(UV) run ruff check
	$(UV) run ruff format --check

ty: ## Run ty: type checking
	$(UV) run ty check

reuse: ## Run reuse: license and copyright best practices
	$(UV) run reuse lint

test-all: setup pytest ruff ty reuse ## Run all tests
	@echo
	@echo "--------------------------------"
	@echo "All tests passed!"

# -----------------------------------
# Translation targets
# -----------------------------------
translations-update: ## Update translation template and .po files
	@$(UV) run pybabel extract -F $(APPDIR)/babel.cfg -o $(APPDIR)/messages.pot $(APPDIR)
	@$(UV) run pybabel update -i $(APPDIR)/messages.pot -d $(APPDIR)/translations

translations-compile: ## Compile .po files to .mo files
	@$(UV) run pybabel compile -d $(APPDIR)/translations
