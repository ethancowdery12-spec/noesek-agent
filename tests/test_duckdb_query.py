import os

import pytest

from noesek.tools.duckdb_query import DuckdbInput, duckdb_query, _view_name


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("NOESEK_FILES_DIR", str(tmp_path))
    (tmp_path / "sales.csv").write_text("region,amount\nwest,10\neast,20\nwest,5\n")
    (tmp_path / "events.ndjson").write_text('{"kind":"a","n":1}\n{"kind":"b","n":2}\n')
    return tmp_path


def test_select_over_csv_view(store):
    out = duckdb_query(DuckdbInput(
        query="SELECT region, SUM(amount) AS total FROM sales GROUP BY region ORDER BY total DESC",
        files=["sales.csv"]))
    assert out["ok"] is True
    assert out["columns"] == ["region", "total"]
    assert out["rows"][0] == ["east", "20"]
    assert out["views"] == {"sales": "sales.csv"}


def test_ndjson_view(store):
    out = duckdb_query(DuckdbInput(query="SELECT kind, n FROM events ORDER BY n", files=["events.ndjson"]))
    assert out["rows"] == [["a", "1"], ["b", "2"]]


def test_plain_select_needs_no_files(store):
    out = duckdb_query(DuckdbInput(query="SELECT 6 * 7 AS answer"))
    assert out["rows"] == [["42"]]


@pytest.mark.parametrize("sql", [
    "COPY sales TO 'out.csv'",
    "ATTACH ':memory:' AS x",
    "INSERT INTO sales VALUES (1)",
    "CREATE TABLE t (i int)",
    "PRAGMA version",
    "INSTALL httpfs",
    "SELECT * FROM read_csv('/etc/passwd'); COPY x TO 'y'",
])
def test_blocked_statements_refused(store, sql):
    with pytest.raises(Exception, match="read-only|blocked"):
        duckdb_query(DuckdbInput(query=sql, files=["sales.csv"]))


@pytest.mark.parametrize("sql", [
    "SELECT * FROM read_csv('/etc/passwd')",
    "SELECT * FROM parquet_scan('s3://bucket/x.parquet')",
    "SELECT glob('/home/*')",
])
def test_direct_readers_refused(store, sql):
    with pytest.raises(Exception, match="files parameter"):
        duckdb_query(DuckdbInput(query=sql))


def test_missing_file(store):
    with pytest.raises(Exception, match="no such file"):
        duckdb_query(DuckdbInput(query="SELECT 1", files=["nope.csv"]))


def test_bad_extension(store, tmp_path):
    (tmp_path / "evil.exe").write_bytes(b"x")
    with pytest.raises(Exception, match="unsupported file type"):
        duckdb_query(DuckdbInput(query="SELECT 1", files=["evil.exe"]))


def test_max_rows_truncates(store, tmp_path):
    (tmp_path / "big.csv").write_text("n\n" + "\n".join(str(i) for i in range(100)) + "\n")
    out = duckdb_query(DuckdbInput(query="SELECT n FROM big", files=["big.csv"], max_rows=10))
    assert out["row_count"] == 10
    assert out["truncated"] is True


def test_view_name_sanitized():
    assert _view_name("2024 Sales.Report.csv") == "f_2024_sales_report"
    assert _view_name("a-b.csv") == "a_b"
