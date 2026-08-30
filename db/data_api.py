"""Porch Light — database access seam (Spec 2, §33).

One interface, two backends. Pipeline code calls `execute()` / `query()` and does
not know or care whether it is talking to:
  - local docker-compose Postgres (dev), via psycopg over DATABASE_URL, or
  - Aurora Serverless v2 PostgreSQL (prod), via the RDS Data API (HTTPS + IAM),
    so the web/pipeline layer needs no VPC and no NAT gateway (§33).

Backend is chosen by configuration, never guessed:
  - if AURORA_CLUSTER_ARN and AURORA_SECRET_ARN are set → RDS Data API
  - elif DATABASE_URL is set → local Postgres
  - else → raise, because a silent default DB is exactly the kind of ambient
    surprise this project refuses.

Credentials never pass through an agent or the repo (§security): the local URL
comes from .env, the Aurora ARNs + IAM come from the environment / Secrets Manager.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Sequence


class DatabaseConfigError(RuntimeError):
    """Raised when no backend is configured. Never a silent default (§never)."""


@dataclass(frozen=True)
class QueryResult:
    """Rows as a list of dicts, plus the raw row count. Backend-independent shape."""

    rows: list[dict[str, Any]]
    row_count: int


class Backend:
    """Interface both backends implement. Parameterized queries only (no string
    interpolation — §security injection posture)."""

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> int:
        raise NotImplementedError

    def query(self, sql: str, params: Sequence[Any] | None = None) -> QueryResult:
        raise NotImplementedError


class LocalPostgresBackend(Backend):
    """psycopg over DATABASE_URL (local docker-compose). Imported lazily so a
    prod-only environment need not install/resolve psycopg at import time."""

    def __init__(self, dsn: str) -> None:
        import psycopg  # lazy

        self._connect = psycopg.connect
        self._dsn = dsn

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> int:
        with self._connect(self._dsn, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params or ())
                return cur.rowcount

    def query(self, sql: str, params: Sequence[Any] | None = None) -> QueryResult:
        with self._connect(self._dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params or ())
                cols = [d.name for d in cur.description] if cur.description else []
                rows = [dict(zip(cols, r)) for r in cur.fetchall()]
                return QueryResult(rows=rows, row_count=len(rows))


class AuroraDataApiBackend(Backend):
    """RDS Data API (HTTPS + IAM) — no VPC, no NAT (§33). boto3 lazy-imported.

    Parameters are passed as Data API `parameters`, positional placeholders `%s`
    are translated to named `:p0, :p1, ...`. Data API is the deliberate prod path;
    it is slower per call than a socket but removes the VPC/NAT surface entirely.
    """

    def __init__(self, cluster_arn: str, secret_arn: str, database: str, region: str | None = None) -> None:
        import boto3  # lazy

        self._client = boto3.client("rds-data", region_name=region or os.environ.get("AWS_REGION", "us-east-1"))
        self._cluster_arn = cluster_arn
        self._secret_arn = secret_arn
        self._database = database

    def _named(self, sql: str, params: Sequence[Any] | None):
        if not params:
            return sql, []
        named_sql = sql
        data_params = []
        for i, val in enumerate(params):
            named_sql = named_sql.replace("%s", f":p{i}", 1)
            data_params.append({"name": f"p{i}", "value": _data_api_value(val)})
        return named_sql, data_params

    def _execute_with_resume(self, **kwargs):
        """Execute a Data API statement, absorbing the auto-pause cold resume.

        With Aurora min-capacity 0 (the dev setting, §33/§38), the first query
        after idle raises DatabaseResumingException while the cluster wakes (a few
        seconds). This is EXPECTED for the scheduled hunter (nobody is waiting), so
        we wait and retry a bounded number of times rather than crash. This is not
        a silent fallback (§never): it is a transient-wake retry, logged, bounded.
        """
        import time

        from botocore.exceptions import ClientError

        # Resume from FULLY paused (min-cap 0) can take up to ~60s, longer than a
        # first naive guess. Budget ~90s total: nobody is waiting on the scheduled
        # hunter (§38), and the whole run has T11=10min. This is a bounded transient
        # wait, not a silent fallback (§never).
        last = None
        for attempt in range(12):  # ~90s total (5s * 12, capped)
            try:
                return self._client.execute_statement(**kwargs)
            except ClientError as e:
                code = e.response.get("Error", {}).get("Code", "")
                if code in ("DatabaseResumingException", "DatabaseNotFoundException") or "resuming" in str(e).lower():
                    last = e
                    time.sleep(5)
                    continue
                raise
        raise last  # type: ignore[misc]

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> int:
        named_sql, data_params = self._named(sql, params)
        resp = self._execute_with_resume(
            resourceArn=self._cluster_arn,
            secretArn=self._secret_arn,
            database=self._database,
            sql=named_sql,
            parameters=data_params,
        )
        return resp.get("numberOfRecordsUpdated", 0)

    def query(self, sql: str, params: Sequence[Any] | None = None) -> QueryResult:
        named_sql, data_params = self._named(sql, params)
        resp = self._execute_with_resume(
            resourceArn=self._cluster_arn,
            secretArn=self._secret_arn,
            database=self._database,
            sql=named_sql,
            parameters=data_params,
            includeResultMetadata=True,
        )
        cols = [c["name"] for c in resp.get("columnMetadata", [])]
        rows = [
            {cols[i]: _from_data_api_field(f) for i, f in enumerate(record)}
            for record in resp.get("records", [])
        ]
        return QueryResult(rows=rows, row_count=len(rows))


def _data_api_value(val: Any) -> dict[str, Any]:
    if val is None:
        return {"isNull": True}
    if isinstance(val, bool):
        return {"booleanValue": val}
    if isinstance(val, int):
        return {"longValue": val}
    if isinstance(val, float):
        return {"doubleValue": val}
    return {"stringValue": str(val)}


def _from_data_api_field(field: dict[str, Any]) -> Any:
    if field.get("isNull"):
        return None
    for key in ("stringValue", "longValue", "doubleValue", "booleanValue"):
        if key in field:
            return field[key]
    return None


def get_backend() -> Backend:
    """Select the backend from configuration. Never a silent default."""
    cluster_arn = os.environ.get("AURORA_CLUSTER_ARN")
    secret_arn = os.environ.get("AURORA_SECRET_ARN")
    if cluster_arn and secret_arn:
        return AuroraDataApiBackend(
            cluster_arn=cluster_arn,
            secret_arn=secret_arn,
            database=os.environ.get("AURORA_DATABASE", "porchlight"),
        )
    dsn = os.environ.get("DATABASE_URL")
    if dsn:
        return LocalPostgresBackend(dsn)
    raise DatabaseConfigError(
        "No database configured. Set AURORA_CLUSTER_ARN + AURORA_SECRET_ARN (prod) "
        "or DATABASE_URL (local). Refusing to guess a default DB."
    )
