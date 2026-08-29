"""Live smoke test: Aurora Serverless v2 reachable via the RDS Data API (Spec 2 task 12.2, §28b).

Aurora would otherwise be proven once by hand and never re-checked. This leaves a
re-runnable check with the Spec 0 skip-vs-fail discipline:
  - skips ONLY when the Aurora endpoint env var is unset (no cluster to test)
  - fails on every error from a cluster that exists

Part of `make smoke` (pytest -m live). Asserts a real Data API query returns,
pgvector is present, min capacity is 0 (the dev setting, raised to 0.5 at Spec 5),
and the four cost tags are on the cluster.
"""

from __future__ import annotations

import os

import boto3
import pytest
from botocore.exceptions import NoCredentialsError

RUNTIME_ARN_VAR = "AURORA_CLUSTER_ARN"
SECRET_ARN_VAR = "AURORA_SECRET_ARN"

REQUIRED_TAGS = {
    "Project": "PorchLight",
    "Env": "dev",
    "Owner": "shara",
    "Purpose": "hackathon-agents-for-humans",
}


def _config():
    cluster = os.environ.get(RUNTIME_ARN_VAR)
    secret = os.environ.get(SECRET_ARN_VAR)
    if not cluster or not secret:
        pytest.skip(f"{RUNTIME_ARN_VAR}/{SECRET_ARN_VAR} unset: no Aurora cluster to test.")
    region = os.environ.get("AWS_REGION", "us-east-1")
    return cluster, secret, region


def _ensure_credentials() -> None:
    try:
        creds = boto3.Session().get_credentials()
        if creds is None:
            pytest.skip("No AWS credentials configured.")
        creds.get_frozen_credentials()
    except NoCredentialsError:
        pytest.skip("No AWS credentials configured (NoCredentialsError).")


@pytest.mark.live
def test_data_api_query_returns():
    cluster, secret, region = _config()
    _ensure_credentials()
    client = boto3.client("rds-data", region_name=region)
    resp = client.execute_statement(
        resourceArn=cluster, secretArn=secret, database="porchlight",
        sql="SELECT 1 AS one",
    )
    assert resp["records"][0][0]["longValue"] == 1


@pytest.mark.live
def test_pgvector_present():
    cluster, secret, region = _config()
    _ensure_credentials()
    client = boto3.client("rds-data", region_name=region)
    resp = client.execute_statement(
        resourceArn=cluster, secretArn=secret, database="porchlight",
        sql="SELECT extname FROM pg_extension WHERE extname = 'vector'",
    )
    assert len(resp["records"]) == 1, "pgvector extension not present"


@pytest.mark.live
def test_min_capacity_is_zero_for_dev():
    """Dev setting is min capacity 0 (raised to 0.5 at Spec 5). Assert it did not
    silently inherit 0.5."""
    cluster, secret, region = _config()
    _ensure_credentials()
    rds = boto3.client("rds", region_name=region)
    cid = cluster.split(":")[-1]
    dbc = rds.describe_db_clusters(DBClusterIdentifier=cid)["DBClusters"][0]
    assert dbc["ServerlessV2ScalingConfiguration"]["MinCapacity"] == 0.0


@pytest.mark.live
def test_four_cost_tags_present():
    cluster, secret, region = _config()
    _ensure_credentials()
    rds = boto3.client("rds", region_name=region)
    tags = {t["Key"]: t["Value"] for t in rds.list_tags_for_resource(ResourceName=cluster)["TagList"]}
    for k, v in REQUIRED_TAGS.items():
        assert tags.get(k) == v, f"missing/incorrect cost tag {k}={v} (got {tags.get(k)})"
