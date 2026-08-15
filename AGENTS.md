# AGENTS.md

Guidelines for AI agents (and contributors) working in this repository.

## Workflow

- **Never commit or push directly to `main`.** All changes go through a feature
  branch and a pull request.
- Create a descriptive branch off `main`, e.g. `feat/<short-description>` or
  `fix/<short-description>`.
- After opening a PR, `main` is only updated by merging the PR. Do not force
  push to shared branches.

## Before every change

1. Pull latest `main` and branch off it.
2. Make your change.
3. Run lint and tests (see below). All must pass.
4. Commit with a conventional-commit message (`feat:`, `fix:`, `docs:`, `ci:`,
   `chore:`, etc.).
5. Push the branch and open a PR. The CI/CD workflow runs the same checks on
   the PR.

## Verification commands

Run these locally before pushing:

```bash
uv sync                          # install dev dependencies
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest
```

## Code quality

- **Typing is required.** Add type annotations to all function and method
  signatures (`mypy` runs with `disallow_untyped_defs = true`). Use precise
  types where they add clarity (e.g. `Optional`, `List[...]`), and `--cast`/
  `Any` sparingly.
- **Use named (keyword) arguments** when calling functions, especially for
  non-obvious parameters, so calls stay readable.
- **Every code path must be covered by a meaningful test.** `pytest` runs with
  `--cov-fail-under=100`; coverage is reported in the README. Write honest
  tests that exercise real behavior (loopback sockets, real config files) and
  mock only system boundaries. Do not add synthetic targets just to inflate
  coverage.

## Dependency changes

- Use `uv` for dependency management. When adding/updating dependencies, run
  `uv lock` and commit the updated `uv.lock`.
- Python version is pinned in `pyproject.toml` (`requires-python`); keep the
  tool config (`ruff`, `mypy`) in sync.

## Releases

- Releases are cut from `main` only.
- Bump the version in `pyproject.toml` **and** `src/vlan_probe/__init__.py`
  (`__version__`), then run `uv lock`.
- Create the GitHub release with tag `v<version>`; publishing the distribution
  to PyPI is handled by the GitLab CI workflow (trusted publishing).