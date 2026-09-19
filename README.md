# Strategy Factory

Internal framework that runs every trading-strategy idea through one standard, reproducible,
auditable funnel: market edge → method screening → entry/exit optimisation → diagnostics &
filters → robustness → statistics → report package → analyst review → portfolio → sizing →
forward lifecycle.

Package `strategy_factory` · CLI `sfac` · Python 3.12 · managed with `uv`.

## Prerequisites (Windows)

- [Git](https://git-scm.com/download/win)
- [uv](https://docs.astral.sh/uv/getting-started/installation/) (installs Python 3.12 itself)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (PostgreSQL registry)
- [Node.js](https://nodejs.org/) 20 or newer (only for the Dukascopy downloader: `cd tools/dukascopy && npm ci`)

## Setup

```bash
uv sync                          # create .venv with Python 3.12 + dev tools
copy .env.example .env           # then edit SFAC_DATA_ROOT / SFAC_ARTIFACTS_ROOT (PowerShell: Copy-Item)
docker compose up -d             # PostgreSQL registry (tables come with T03 migrations)
uv run sfac --version
uv run sfac info
```

Quality checks (all must pass before a PR):

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy src
uv run pytest                    # fast suite; slow self-tests: uv run pytest -m slow
```

## Documentation

- [`CLAUDE.md`](CLAUDE.md): working rules and conventions (read first)
- [`docs/spec/`](docs/spec): specification v1.2 (what each stage does)
- [`docs/features.md`](docs/features.md): feature list with acceptance criteria
- [`docs/design.md`](docs/design.md): technical design (how)
- [`docs/adr/`](docs/adr): architecture decision records
- [`docs/tasks/`](docs/tasks): implementation tasks
