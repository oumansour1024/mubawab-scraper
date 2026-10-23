.PHONY: sync lint fmt test run export clean

sync:   ; uv sync
lint:   ; uv run ruff check src tests && uv run mypy
fmt:    ; uv run ruff format src tests
test:   ; uv run pytest -m "not integration"
run:    ; uv run mubawab-scrape --city casablanca --property-type appartements
export: ; uv run mubawab-scrape export --fmt csv
clean:  ; rm -rf .venv .pytest_cache .ruff_cache .mypy_cache data/processed/*

