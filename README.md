# Santosh Analytics — AI Content Studio

Local-first, modular-monolith AI content production platform for technical YouTube video creation on the **Santosh Analytics** channel.

## Architecture Overview

- **Backend**: FastAPI (`app/`)
- **Dashboard**: Streamlit (`frontend/`)
- **Core Domain & Persistence**: `src/content_studio/` (async SQLAlchemy 2.x + `aiosqlite`, Alembic migrations, `pathlib.Path` filesystem `ArtifactStore`, Pydantic v2 contracts)
- **Local-First by Default**: Runs with `LOCAL_ONLY=true` and `MAX_BUDGET_USD=0.0` (Ollama primary inference, optional gated cloud fallback).
- **Plan & Engineering Directives**: See [project_plan.md](project_plan.md) and [AGENTS.md](AGENTS.md).

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Optional (for local LLM inference in Milestone 3+): [Ollama](https://ollama.com/)

## Quick Start

1. **Install dependencies**

   ```powershell
   uv sync
   ```

2. **Configure local environment**

   ```powershell
   Copy-Item .env.example .env
   ```

3. **Apply database migrations**

   ```powershell
   uv run alembic upgrade head
   ```

4. **Start the FastAPI backend**

   ```powershell
   uv run uvicorn app.main:app --reload
   ```

   - Health check: `http://127.0.0.1:8000/health`
   - Interactive API docs: `http://127.0.0.1:8000/docs`

5. **Start the Streamlit dashboard** (in a second terminal)

   ```powershell
   uv run streamlit run frontend/Home.py
   ```

## Development Checks

```powershell
uv run pytest -v
uv run ruff check .
uv run ruff format --check .
```

## Current Status

- **Milestone 1 (Foundation)**: Complete — FastAPI backend, Streamlit dashboard, async SQLite + Alembic initial migration (`projects`, `workflow_runs`, `artifacts`, `llm_usage_logs`), filesystem `ArtifactStore`, and test suite.
- **Milestone 2 (Shared Persistence & Artifact Management)**: Complete — Alembic `0002_shared_persistence` (`approvals`, `channel_guidelines`, `agent_runs`), `ArtifactService` (versioning, non-destructive draft superseding, SHA-256 verification), `/api/projects/{project_id}/artifacts`, `/api/guidelines`, `/api/approvals`, and Streamlit Project Workspace + Settings pages.
- **Milestone 3 (Hybrid LLM & Provider Layer)**: Complete — Provider-agnostic `BaseLLMProvider`, local `OllamaProvider`, optional cloud `GeminiProvider`, task-based `ModelRouter` with `LOCAL_ONLY`/budget guardrails, retries, structured Pydantic repair loop, usage logging, and `/api/llm/status` + `/api/projects/{project_id}/usage`.
- **Next**: **Milestone 4** — Research Engine (research tables, search provider interface, webpage extraction with `trafilatura`, deduplication, structured research findings with source traceability, and Research UI).
