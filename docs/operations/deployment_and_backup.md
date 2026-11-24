# Deployment, Operations & Backup Runbook

## 1. Local Deployment Architecture

Santosh Analytics AI Content Studio runs as a **local-first modular monolith**:

- **FastAPI Backend** (`app/main.py`) — REST API, structured JSON logging, request ID tracing (`X-Request-ID`), and global exception handling.
- **Streamlit Dashboard** (`frontend/Home.py` + `frontend/pages/`) — Home KPIs, Project Workspace, Settings, and Approval Center.
- **SQLite Persistence** (`data/content_studio.db`, WAL mode, managed strictly via Alembic).
- **LangGraph Checkpointer** (`data/checkpoints.db`, separate SQLite store via `AsyncSqliteSaver`).
- **Filesystem Artifact Store** (`data/projects/{project_id}/`, atomic writes + SHA-256 checksums).

---

## 2. Database Migrations (Alembic)

Never create or alter tables manually. Apply migrations before starting the API:

```powershell
uv run alembic upgrade head
uv run alembic current
```

To verify rollback safety in staging/test:

```powershell
uv run alembic downgrade -1
uv run alembic upgrade head
```

---

## 3. Backup & Restore Procedures

Use the built-in CLI (`scripts/backup_restore.py`), which uses SQLite's online `.backup()` API (safe even under active WAL journaling) and records SHA-256 checksums for every database and artifact file.

### Create a Verified Backup

```powershell
uv run python scripts/backup_restore.py backup
```

Or specify an explicit output archive:

```powershell
uv run python scripts/backup_restore.py backup --output .\backups\manual_snapshot.zip
```

### Verify Backup Integrity

```powershell
uv run python scripts/backup_restore.py verify .\backups\manual_snapshot.zip
```

### Restore from Backup

Stop FastAPI and Streamlit first, then restore:

```powershell
uv run python scripts/backup_restore.py restore .\backups\manual_snapshot.zip --target .\data --overwrite
```

---

## 4. Budget & Security Guardrails

- **Local-First Default**: Keep `LOCAL_ONLY=true` and `MAX_BUDGET_USD=0.0` for zero-cost local Ollama inference.
- **Cloud Fallback**: Only set `LOCAL_ONLY=false`, `GEMINI_API_KEY=...`, and explicit `MAX_BUDGET_USD` + per-project `budget_usd` caps when cloud synthesis is desired.
- **Isolated Code Validation**: Generated Python demos execute in `python -I` inside a temporary directory with stripped environment variables (no host secrets passed) after static AST safety checks. SQL demos execute in ephemeral in-memory SQLite.
- **Manual Publishing Only**: Exported ZIP production packages under `06_export/` are strictly `MANUAL_ONLY`; no automatic upload or publishing occurs.

---

## 5. Future Cloud Migration Path

Because all persistence, storage, and external integrations sit behind modular repository/provider interfaces:

1. **Database**: Swap `DATABASE_URL` from `sqlite+aiosqlite:///` to `postgresql+asyncpg://...` and run `uv run alembic upgrade head`.
2. **Artifact Storage**: Implement an S3/GCS adapter matching `ArtifactStore`'s async read/write/verify contract.
3. **Observability**: Ship stdout structured JSON logs directly to Cloud Logging / Datadog / Loki.
