"""duckdb_query: SQL over the user's files in the agent file store.

Roadmap item 71 (skills batch 1, top pick). Own implementation over DuckDB
(MIT) - SQL across CSV/TSV/JSON/NDJSON/Parquet without loading a database.
The dependency is the only thing taken; all code here is ours.

Safety shape: read-only statements only (SELECT/WITH/EXPLAIN/DESCRIBE/SHOW/
SUMMARIZE). Anything that can write, attach, or load extensions is refused
before DuckDB sees it. Files come from the file store by name (same rules as
create_file - no traversal), are exposed as views named by file stem, and the
query runs in an in-memory connection with a hard interrupt timer.
"""
from __future__ import annotations

import re
import threading

from pydantic import BaseModel, Field

from ..filestore import FileStoreError, files_dir

_ALLOWED_HEAD = re.compile(r"^\s*(select|with|explain|describe|show|summarize)\b", re.I)
_BLOCKED_WORD = re.compile(
    r"\b(attach|detach|install|load|copy|export|import|create|drop|insert|update|delete|alter|pragma|call|set|checkpoint|vacuum)\b",
    re.I,
)
_DIRECT_READER = re.compile(
    r"\b(read_csv|read_csv_auto|read_json|read_json_auto|read_parquet|read_text|read_blob|parquet_scan|csv_scan|glob|sqlite_scan|list_files)\s*\(",
    re.I,
)
_EXT_MAP = {
    ".csv": "read_csv_auto",
    ".tsv": "read_csv_auto",
    ".json": "read_json_auto",
    ".ndjson": "read_json_auto",
    ".jsonl": "read_json_auto",
    ".parquet": "read_parquet",
}
_TIMEOUT_S = 20.0
_MAX_CELL = 300


class DuckdbInput(BaseModel):
    query: str = Field(min_length=1, max_length=4000, description="One read-only SQL statement (SELECT/WITH/EXPLAIN/DESCRIBE/SHOW/SUMMARIZE)")
    files: list[str] = Field(default_factory=list, max_length=8, description="File-store file names to expose as views (csv/tsv/json/ndjson/jsonl/parquet). View name = file stem, e.g. sales.csv -> sales")
    max_rows: int = Field(default=50, ge=1, le=500)


def _check_read_only(sql: str) -> None:
    if not _ALLOWED_HEAD.search(sql):
        raise ValueError("only read-only statements (SELECT/WITH/EXPLAIN/DESCRIBE/SHOW/SUMMARIZE) are allowed")
    m = _BLOCKED_WORD.search(sql)
    if m:
        raise ValueError(f"blocked SQL keyword: {m.group(1).upper()} - this tool is read-only")
    if _DIRECT_READER.search(sql):
        raise ValueError("file access goes through the files parameter (store files become views) - direct reader functions are blocked")


def _view_name(file_name: str) -> str:
    stem = re.sub(r"\.[^.]+$", "", file_name)
    stem = re.sub(r"[^A-Za-z0-9_]", "_", stem)
    if not stem or stem[0].isdigit():
        stem = "f_" + stem
    return stem.lower()


def duckdb_query(inp: DuckdbInput) -> dict:
    _check_read_only(inp.query)
    try:
        import duckdb
    except ImportError:
        return {"ok": False, "error": "duckdb is not installed in this deployment - add duckdb==1.4.3 to dependencies"}

    views = {}
    con = duckdb.connect(":memory:")
    try:
        for name in inp.files:
            ext = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""
            reader = _EXT_MAP.get(ext)
            if not reader:
                raise FileStoreError(f"unsupported file type for SQL: {name} (csv/tsv/json/ndjson/jsonl/parquet)")
            path = files_dir() / name
            if not path.is_file():
                raise FileStoreError(f"no such file in the file store: {name}")
            view = _view_name(name)
            safe_path = str(path).replace("'", "''")
            if reader == "read_csv_auto" and ext == ".tsv":
                con.execute(f"CREATE VIEW {view} AS SELECT * FROM read_csv_auto('{safe_path}', delim='\\t')")
            else:
                con.execute(f"CREATE VIEW {view} AS SELECT * FROM {reader}('{safe_path}')")
            views[view] = name

        timer = threading.Timer(_TIMEOUT_S, con.interrupt)
        timer.start()
        try:
            cur = con.execute(inp.query)
            cols = [d[0] for d in (cur.description or [])]
            rows = cur.fetchmany(inp.max_rows + 1)
        finally:
            timer.cancel()
    finally:
        con.close()

    truncated = len(rows) > inp.max_rows
    rows = rows[: inp.max_rows]
    out_rows = [
        [(str(c)[:_MAX_CELL] if c is not None else None) for c in row]
        for row in rows
    ]
    return {
        "ok": True,
        "columns": cols,
        "rows": out_rows,
        "row_count": len(out_rows),
        "truncated": truncated,
        "views": views,
    }
