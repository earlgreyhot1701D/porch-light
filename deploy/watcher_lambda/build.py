"""Build the watcher Lambda deployment zip (Block B).

Mirrors deploy/hunter_lambda/build.py. Stages, then zips:
  - handler.py (the Function URL entry)
  - src/porchlight/  (the package: watch + verify + rewrite + pipeline + log + config)
  - db/data_api.py + db/schema.sql  (the backend seam, for the Aurora-first read + budget)
  - items.json  (BAKED verified items, the fallback source — see bake_items())
  - third-party deps the watcher imports that are NOT in the Lambda runtime:
      strands-agents (the matcher agent), structlog, tzdata
    boto3/botocore are provided by the Lambda Python runtime, so excluded.

items.json is baked from Aurora at build time (env: AURORA_CLUSTER_ARN +
AURORA_SECRET_ARN) so the deployed fallback matches the live record. If the DB is
not reachable at build time, it falls back to web/sample.json's items so the build
still produces a usable (if possibly stale) fallback — and prints which it used.

Run: AURORA_* env set, `uv run python deploy/watcher_lambda/build.py`
Produces: deploy/watcher_lambda/watcher_lambda.zip
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
STAGE = HERE / "_stage"
ZIP = HERE / "watcher_lambda.zip"
ITEMS = HERE / "items.json"

DEPS = ["strands-agents", "structlog", "tzdata"]


def bake_items() -> tuple[int, str]:
    """Write items.json = [{item_id, en_text}, ...] of verified items.

    Aurora first (the live record); web/sample.json fallback so the build never
    hard-fails. Returns (count, source) for the build log.
    """
    rows: list[dict] = []
    source = "aurora"
    if os.environ.get("AURORA_CLUSTER_ARN") and os.environ.get("AURORA_SECRET_ARN"):
        try:
            sys.path.insert(0, str(ROOT))
            sys.path.insert(0, str(ROOT / "src"))
            from db import data_api

            be = data_api.get_backend()
            r = be.query(
                "SELECT i.item_id, ir.en_text FROM item_rewrites ir "
                "JOIN items i ON i.item_id = ir.item_id "
                "WHERE ir.en_verified = true AND ir.en_text IS NOT NULL"
            )
            rows = [{"item_id": row["item_id"], "en_text": row["en_text"]} for row in r.rows]
        except Exception as exc:
            print(f"  (Aurora bake failed: {type(exc).__name__}; falling back to web/sample.json)")
            rows = []
    if not rows:
        source = "web/sample.json"
        sample = json.loads((ROOT / "web" / "sample.json").read_text(encoding="utf-8"))
        # sample.json's heading.en IS the verified summary text the matcher reads.
        rows = [{"item_id": c["id"], "en_text": c["heading"]["en"]} for c in sample.get("changed", [])]
    ITEMS.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(rows), source


def main() -> None:
    n, src = bake_items()
    print(f"baked items.json: {n} items (source: {src})")

    if STAGE.exists():
        shutil.rmtree(STAGE)
    STAGE.mkdir(parents=True)

    shutil.copy2(HERE / "handler.py", STAGE / "handler.py")
    shutil.copy2(ITEMS, STAGE / "items.json")
    shutil.copytree(ROOT / "src" / "porchlight", STAGE / "porchlight")
    (STAGE / "db").mkdir()
    shutil.copy2(ROOT / "db" / "data_api.py", STAGE / "db" / "data_api.py")
    shutil.copy2(ROOT / "db" / "schema.sql", STAGE / "db" / "schema.sql")

    # Install deps for the LAMBDA's platform (Linux/cp312/manylinux), NOT the build
    # host. Building on Windows pulled Windows wheels (pywin32) that fail to import on
    # the Lambda's Linux runtime — the ModuleNotFoundError we hit. --python-platform
    # + --only-binary forces manylinux wheels; --python-version pins cp312.
    subprocess.run(
        ["uv", "pip", "install", "--target", str(STAGE), *DEPS,
         "--python-platform", "x86_64-manylinux2014",
         "--python-version", "3.12",
         "--only-binary", ":all:",
         "--quiet"],
        check=True,
    )

    for cache in STAGE.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)
    if ZIP.exists():
        ZIP.unlink()
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(STAGE.rglob("*")):
            if p.is_file():
                zf.write(p, p.relative_to(STAGE))

    size_mb = ZIP.stat().st_size / 1_000_000
    print(f"built {ZIP.name}: {size_mb:.1f} MB")
    shutil.rmtree(STAGE)


if __name__ == "__main__":
    main()
