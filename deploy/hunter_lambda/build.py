"""Build the hunter Lambda deployment zip (§38).

Stages, into a clean dir, then zips:
  - handler.py (the Lambda entry)
  - src/porchlight/  (the package: pipeline + adapters + log + config)
  - db/data_api.py + db/schema.sql  (the backend seam; schema for reference)
  - third-party deps the hunter imports that are NOT in the Lambda runtime:
      structlog, beautifulsoup4 (+ soupsieve), tzdata
    boto3/botocore are provided by the Lambda Python runtime, so excluded.
    psycopg is NOT included: prod uses the RDS Data API path (boto3), not psycopg.

Run: uv run python deploy/hunter_lambda/build.py
Produces: deploy/hunter_lambda/hunter_lambda.zip
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
STAGE = HERE / "_stage"
ZIP = HERE / "hunter_lambda.zip"

DEPS = ["structlog", "beautifulsoup4", "tzdata"]


def main() -> None:
    if STAGE.exists():
        shutil.rmtree(STAGE)
    STAGE.mkdir(parents=True)

    # 1. handler
    shutil.copy2(HERE / "handler.py", STAGE / "handler.py")

    # 2. the porchlight package
    shutil.copytree(ROOT / "src" / "porchlight", STAGE / "porchlight")

    # 3. the db seam (data_api + schema)
    (STAGE / "db").mkdir()
    shutil.copy2(ROOT / "db" / "data_api.py", STAGE / "db" / "data_api.py")
    shutil.copy2(ROOT / "db" / "schema.sql", STAGE / "db" / "schema.sql")

    # 4. third-party deps into the stage root (Lambda flat layout)
    subprocess.run(
        ["uv", "pip", "install", "--target", str(STAGE), *DEPS, "--quiet"],
        check=True,
    )

    # 5. zip it (deterministic-ish; prune caches)
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
