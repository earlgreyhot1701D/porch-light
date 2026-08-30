"""AWS Lambda handler for the Porch Light hunter (§38).

The hunter is DETERMINISTIC (no model, no agent loop): it fetches the Ventura
AgendaCenter index, applies pure classification/horizon rules, and records
documents. It runs IN-PROCESS here — EventBridge invokes this Lambda directly,
there is no AgentCore runtime and no InvokeAgentRuntime hop (§38).

On any unhandled error the handler logs and re-raises so the invocation is marked
failed; it does NOT retry. The DB run lock plus the next hourly trigger handle
recovery — a retrying handler would fight the lock.

Backend selection is by env var (db.data_api.get_backend): AURORA_CLUSTER_ARN +
AURORA_SECRET_ARN → RDS Data API. Credentials never appear here; the Data API uses
the Lambda execution role's IAM plus the RDS-managed secret.
"""

from __future__ import annotations

import sys

# db/ is shipped alongside the package in the zip; ensure it is importable.
sys.path.insert(0, "db")

from porchlight.pipeline.run import run_ingestion  # noqa: E402


def handler(event, context):
    """EventBridge (hourly, direct) invokes this. Returns the run status string."""
    import data_api  # from db/, lazy so import errors surface in the run, logged

    backend = data_api.get_backend()
    try:
        status = run_ingestion(backend)
    except Exception:
        import traceback
        print("HUNTER_TRACEBACK:\n" + traceback.format_exc())
        raise
    return {"status": status}
