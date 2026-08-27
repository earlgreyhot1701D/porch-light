"""OBSOLETE — §32b.

This script was planned (design.md §11.3) to guarantee the deployed dependency
set matches uv.lock by building the zip locally with `uv pip install --target`.

It was never built, and is now unnecessary: AgentCore resolves dependencies
server-side from the app's pyproject.toml (CodeZip build type). The drift
guarantee is re-owned by tests/test_deploy_pins.py, which asserts the app
manifest's exact pins match the versions in uv.lock.

Do not implement this script. Do not delete it silently (the obsolescence
record is the point).
"""

raise SystemExit("OBSOLETE: see §32b. Drift guarantee owned by tests/test_deploy_pins.py.")
