import ast
import asyncio
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

from content_studio.contracts.assets import CodeExecutionResult

_BLOCKED_MODULES: frozenset[str] = frozenset(
    {
        "ctypes",
        "ftplib",
        "http",
        "importlib",
        "multiprocessing",
        "os",
        "pathlib",
        "pty",
        "requests",
        "httpx",
        "shutil",
        "signal",
        "socket",
        "subprocess",
        "sys",
        "tempfile",
        "urllib",
        "webbrowser",
    }
)
_BLOCKED_CALLS: frozenset[str] = frozenset(
    {
        "__import__",
        "breakpoint",
        "compile",
        "eval",
        "exec",
        "input",
        "open",
    }
)
_MAX_OUTPUT_CHARS = 8000


def check_python_ast_safety(code: str) -> list[str]:
    """Static AST guardrail rejecting host filesystem, network, and subprocess access."""
    blocked: list[str] = []
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return [f"Python syntax error at line {exc.lineno}: {exc.msg}"]

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root_mod = alias.name.split(".")[0]
                if root_mod in _BLOCKED_MODULES:
                    blocked.append(f"Blocked import: '{alias.name}'")
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root_mod = node.module.split(".")[0]
                if root_mod in _BLOCKED_MODULES:
                    blocked.append(f"Blocked import from: '{node.module}'")
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in _BLOCKED_CALLS:
                blocked.append(f"Blocked builtin call: '{node.func.id}()'")
            elif isinstance(node.func, ast.Attribute) and node.func.attr in {
                "system",
                "popen",
                "unlink",
                "rmtree",
                "remove",
            }:
                blocked.append(f"Blocked attribute call: '.{node.func.attr}()'")
    return blocked


async def run_python_isolated(
    code: str,
    *,
    timeout_seconds: float = 5.0,
) -> CodeExecutionResult:
    """Validate and execute Python demo in an isolated subprocess with stripped env."""
    start = time.perf_counter()
    blocked = check_python_ast_safety(code)
    if blocked:
        return CodeExecutionResult(
            language="python",
            passed=False,
            exit_code=-1,
            blocked_reasons=blocked,
            duration_ms=int((time.perf_counter() - start) * 1000),
        )

    with tempfile.TemporaryDirectory(prefix="studio_code_sandbox_") as tmp:
        sandbox_dir = Path(tmp)
        script_path = sandbox_dir / "demo.py"
        script_path.write_text(code, encoding="utf-8")

        # Stripped environment: zero host API keys or secrets exposed to generated code
        clean_env = {"PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"}
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-I",
            str(script_path),
            cwd=str(sandbox_dir),
            env=clean_env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            raw_out, raw_err = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
        except TimeoutError:
            proc.kill()
            await proc.communicate()
            return CodeExecutionResult(
                language="python",
                passed=False,
                exit_code=-1,
                stderr=f"Execution timed out after {timeout_seconds}s.",
                blocked_reasons=[f"Timeout exceeded ({timeout_seconds}s)"],
                duration_ms=int((time.perf_counter() - start) * 1000),
            )

        stdout = raw_out.decode("utf-8", errors="replace")[:_MAX_OUTPUT_CHARS]
        stderr = raw_err.decode("utf-8", errors="replace")[:_MAX_OUTPUT_CHARS]
        exit_code = int(proc.returncode or 0)
        return CodeExecutionResult(
            language="python",
            passed=exit_code == 0,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_ms=int((time.perf_counter() - start) * 1000),
        )


def _run_sql_sync(sql_code: str) -> CodeExecutionResult:
    start = time.perf_counter()
    lower = sql_code.lower()
    if "attach " in lower or "load_extension" in lower:
        return CodeExecutionResult(
            language="sql",
            passed=False,
            exit_code=-1,
            blocked_reasons=["Blocked SQL directive (ATTACH / load_extension)."],
            duration_ms=int((time.perf_counter() - start) * 1000),
        )

    conn = sqlite3.connect(":memory:")
    try:
        statements = [s.strip() for s in sql_code.split(";") if s.strip()]
        outputs: list[str] = []
        cursor = conn.cursor()
        for stmt in statements:
            cursor.execute(stmt)
            if cursor.description:
                cols = [d[0] for d in cursor.description]
                rows = cursor.fetchmany(20)
                outputs.append(" | ".join(cols))
                for row in rows:
                    outputs.append(" | ".join(str(val) for val in row))
        conn.commit()
        return CodeExecutionResult(
            language="sql",
            passed=True,
            exit_code=0,
            stdout="\n".join(outputs)[:_MAX_OUTPUT_CHARS],
            duration_ms=int((time.perf_counter() - start) * 1000),
        )
    except sqlite3.Error as exc:
        return CodeExecutionResult(
            language="sql",
            passed=False,
            exit_code=1,
            stderr=str(exc),
            duration_ms=int((time.perf_counter() - start) * 1000),
        )
    finally:
        conn.close()


async def run_sql_isolated(sql_code: str) -> CodeExecutionResult:
    return await asyncio.to_thread(_run_sql_sync, sql_code)
