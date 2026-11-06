PYTHON ?= python3
PYTHONPATH := src
export PYTHONPATH

.PHONY: help install build collect enrich export site serve test lint clean doctor

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

install: ## Install the package in editable mode (no runtime dependencies)
	$(PYTHON) -m pip install -e .

build: ## Full pipeline: collect, enrich, export, assemble _site/
	$(PYTHON) -m aiindex build

collect: ## Collect from all enabled sources into SQLite
	$(PYTHON) -m aiindex collect

enrich: ## Enrich stored items with the Gemini free tier
	$(PYTHON) -m aiindex enrich

export: ## Rebuild data/index.json
	$(PYTHON) -m aiindex export

site: ## Assemble the deployable static site in _site/
	$(PYTHON) -m aiindex site

serve: ## Build and serve the dashboard on http://127.0.0.1:8000
	$(PYTHON) -m aiindex serve --build --open

test: ## Run the offline unit tests
	$(PYTHON) -m unittest discover -s tests -v

doctor: ## Show environment and configuration state (no secrets)
	$(PYTHON) -m aiindex doctor

clean: ## Remove generated artefacts
	rm -rf _site data/index.sqlite3 data/index.sqlite3-shm data/index.sqlite3-wal
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
