.PHONY: venv lint test clean format build publish run install hooks

.venv: pyproject.toml
	if [ ! -d .venv ]; then uv venv; fi
	uv pip install -e . --group dev

venv: .venv hooks

hooks:
	git config core.hooksPath .githooks
	chmod +x .githooks/*

lint: .venv
	.venv/bin/ruff check .
	.venv/bin/ruff format --check .

format: .venv
	.venv/bin/ruff format .

test: .venv
	.venv/bin/mypy src
	.venv/bin/pytest --cov=src/vlan_probe --cov-report=term-missing

run: .venv
	.venv/bin/python3 -m vlan_probe $(ARGS)

install:
	uv tool install --force .

build: .venv
	uv build

publish: build
	uv publish

clean:
	rm -rf .venv __pycache__ .pytest_cache .ruff_cache dist

