# Excavator

Excavator is a field-notebook-style code archaeology tool. It connects Git
history, symbol lineage, pull requests, reviews, and issues to explain how a
codebase changed over time.

## What it does

- Analyzes Python symbols across Git history.
- Tracks symbol additions, edits, renames, and removals.
- Ingests GitHub pull requests, reviews, and issue references.
- Builds evidence-backed explanations for why a symbol changed.
- Presents the results in a visual React interface.

## Project layout

```text
.
├── backend/              FastAPI service, analysis engine, persistence, and tests
├── frontend/             React + Vite field-notebook interface
├── docker-compose.yml    Local PostgreSQL service
├── .env.example          Local environment variable template
└── README.md             Project setup and usage guide
```

More detailed backend behavior and deployment constraints are documented in
[`backend/LIMITATIONS.md`](backend/LIMITATIONS.md).

## Prerequisites

- Python 3.12
- [`uv`](https://docs.astral.sh/uv/)
- Node.js and npm
- Docker Desktop, for the local PostgreSQL database
- A GitHub token for higher API limits or private development environments

## Quick start

### 1. Configure the environment

From the repository root:

```powershell
Copy-Item .env.example .env
```

Edit `.env` when you need a different database, GitHub token, or explanation
provider. Keep `.env` out of version control.

### 2. Start PostgreSQL

```powershell
docker compose up -d db
```

### 3. Start the backend

```powershell
Set-Location backend
uv sync
uv run alembic upgrade head
uv run uvicorn excavator.api.main:create_app --factory --reload --host 127.0.0.1 --port 8000
```

The API is available at <http://127.0.0.1:8000>. Interactive API
documentation is available at <http://127.0.0.1:8000/docs>.

### 4. Start the frontend

In a second terminal:

```powershell
Set-Location frontend
npm install
npm run dev
```

Open <http://localhost:5173>.

The frontend uses `http://127.0.0.1:8000` by default. Set
`VITE_API_BASE_URL` when the backend runs at another address.

## Development commands

### Backend

Run the default test suite:

```powershell
Set-Location backend
uv run pytest
```

Run formatting and lint checks:

```powershell
uv run ruff format --check .
uv run ruff check .
uv run mypy
```

The PostgreSQL integration test is opt-in:

```powershell
$env:TEST_POSTGRES_URL = "postgresql+psycopg://excavator:excavator@localhost:5432/excavator"
uv run pytest -m postgres tests\integration\test_postgres.py
```

### Frontend

```powershell
Set-Location frontend
npm test
npm run build
```

## Configuration

The most important variables are:

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | SQLAlchemy connection string |
| `GITHUB_TOKEN` | Optional GitHub API token |
| `REPOS_ROOT` | Root directory for local repository clones |
| `EXPLAIN_PROVIDER` | `anthropic` or `ollama` |
| `ANTHROPIC_API_KEY` | API key for Anthropic explanations |
| `OLLAMA_BASE_URL` | URL for a local Ollama server |
| `OLLAMA_MODEL` | Ollama model name |
| `LOG_LEVEL` | Application log level |

Use environment variables for all tokens and API keys. For local-only
development, keep the service bound to `127.0.0.1`.

## Architecture

- `backend/src/excavator/api/` exposes the HTTP API.
- `backend/src/excavator/core/` contains language-independent analysis logic.
- `backend/src/excavator/infra/` integrates Git, GitHub, databases, and
  explanation providers.
- `backend/src/excavator/languages/` contains language analyzers and the
  analyzer registry.
- `frontend/src/` contains the React application, API types, and presentation
  components.

## Current scope

Python is the supported analysis language. The service is designed for local
development and public repository analysis; review
[`backend/LIMITATIONS.md`](backend/LIMITATIONS.md) before deploying it or
enabling additional repository sources.

## License

No license has been declared yet.
