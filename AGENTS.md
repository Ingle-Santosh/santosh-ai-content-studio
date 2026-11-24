# AGENTS.md — Santosh Analytics AI Content Studio

## Core Directives
1. **Local-First & Zero-Cost by Default**: Never require external API keys for core application boot, testing, or basic runs. Default LLM provider is local Ollama. Cloud providers (e.g., Gemini) are optional fallback routes gated by explicit user configuration and budget thresholds.
2. **Modular Monolith**: Code resides in a single repository under `src/content_studio/` and `app/`. No microservices, distributed queues, or external message brokers in v1.
3. **Structured Contracts**: All agent outputs must be strictly typed using Pydantic models. Never accept or return loose strings or unvalidated dicts between agents.
4. **Filesystem as Artifact Store**: Large assets (markdown reports, Mermaid files, SVG/PNG renders, HTML animations, code demos) are stored in `data/projects/{project_id}/`. Database records and LangGraph checkpoints hold only metadata and relative path references.
5. **Pathlib Only**: Never use `os.path`. Use `pathlib.Path` across all modules.
6. **Async I/O**: Use asynchronous patterns for FastAPI routes, external network calls, and subprocess execution.
7. **Idempotence & Checkpoints**: Workflow state transitions must persist via SQLite checkpointers. Graph nodes must be idempotent on resume.

---

## Technical Stack & Constraints
- **Python**: 3.12+
- **Package Manager**: `uv`
- **Backend**: FastAPI
- **Frontend**: Streamlit
- **Orchestration**: LangGraph
- **Database**: SQLite + SQLAlchemy 2.0 (async) + Alembic
- **Validation**: Pydantic v2
- **Testing**: `pytest`, `pytest-asyncio`
- **Linting & Formatting**: `ruff`

---

## Directory Standards
```text
santosh-ai-content-studio/
├── app/
│   ├── api/
│   │   ├── routes/
│   │   └── schemas/
│   ├── dependencies.py
│   └── main.py
├── frontend/
│   ├── Home.py
│   └── pages/
├── src/
│   └── content_studio/
│       ├── config/
│       ├── database/
│       │   ├── models/
│       │   └── repositories/
│       └── utils/
├── tests/
├── data/
│   ├── content_studio.db
│   └── projects/
├── pyproject.toml
├── alembic.ini
└── .env.example