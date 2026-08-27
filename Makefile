# Porch Light — development targets

.PHONY: test smoke

test:
	uv run pytest

smoke:
	uv run pytest -m live -v
