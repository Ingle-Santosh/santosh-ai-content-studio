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
- **Milestone 4 (Research Engine)**: Complete — Alembic `0003_research_engine` (`sources`, `research_documents`, `research_findings`), zero-key DuckDuckGo + optional Tavily search providers, `WebExtractor` (`trafilatura`), URL & content-checksum deduplication, strict source-grounded `ResearchService`, `/api/projects/{project_id}/research/*` routes, and Streamlit Research tab.
- **Milestone 5 (Fact Checking & Competitor Analysis)**: Complete — Alembic `0004_fact_check_competitors` (`claims`, `claim_sources`, `competitor_videos`), evidence-grounded `FactCheckService` (auto-downgrades ungrounded `VERIFIED` claims to `UNSUPPORTED` and creates Gate 2 research approval), YouTube Data API v3 + zero-key public search/oEmbed `CompetitorService`, `/fact-check/*` & `/competitors/*` routes, and Streamlit Fact Checking & Competitors tabs.
- **Milestone 6 (Scriptwriting & Storyboarding)**: Complete — Alembic `0005_scripts_and_storyboard` (`scripts`, `script_versions`, `scenes`), channel-guideline-driven 9-section Hinglish `ScriptwriterService` with versioning & deterministic `validate_script_sections`, Gate 3 script approval, approved-script-gated `StoryboardService` with scene-level asset requirements, `/scripts/*` & `/storyboard/*` routes, and Streamlit Script & Storyboard tabs.
- **Milestone 7 (LangGraph Orchestration)**: Complete — `TopicStrategistService`, LangGraph `StateGraph` with parallel Research + Competitor fan-out, persistent SQLite checkpointing (`data/checkpoints.db` via `AsyncSqliteSaver`), native `interrupt()` / `Command(resume=...)` across Gates 1–3, idempotent resume, `/api/projects/{project_id}/workflows/*` + `/api/workflows/{run_id}/*`, and Streamlit Workflow tab + Approval Center (`frontend/pages/3_Approval_Center.py`).
- **Next**: **Milestone 8** — Visual Asset Generation (Asset Planner, Mermaid diagrams, HTML animations, screenshots/annotations, isolated code demo validation, and Asset QA).
