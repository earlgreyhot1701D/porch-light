"""§32b: Assert the app manifest's pinned versions match what uv.lock resolved.

The deployed dependency set is resolved by AgentCore server-side from the app's
pyproject.toml. uv.lock governs local dev/test. This test is the drift guarantee
that keeps them honest: if a dev bumps a version in uv.lock, this test fails
until the app manifest is updated to match, and vice versa.

If this test fails, update the pins in:
    deploy/spike_b/porchlightspike/app/porchlight_spike/pyproject.toml
to match the versions shown in `uv lock --check` / `uv.lock`.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

APP_PYPROJECT = (
    REPO_ROOT
    / "deploy"
    / "spike_b"
    / "porchlightspike"
    / "app"
    / "porchlight_spike"
    / "pyproject.toml"
)

UV_LOCK = REPO_ROOT / "uv.lock"

# Packages that must be pinned and must match uv.lock exactly.
PINNED_PACKAGES = ("bedrock-agentcore", "strands-agents", "structlog")


def _parse_app_pins(content: str) -> dict[str, str]:
    """Extract pinned versions from pyproject.toml dependencies."""
    pins: dict[str, str] = {}
    # Match lines like:  "package==1.2.3",
    pattern = re.compile(r'"([^"]+)==([^"]+)"')
    for match in pattern.finditer(content):
        name = match.group(1).strip().lower()
        version = match.group(2).strip()
        pins[name] = version
    return pins


def _parse_uv_lock_versions(content: str, packages: tuple[str, ...]) -> dict[str, str]:
    """Extract resolved versions from uv.lock for specified packages."""
    versions: dict[str, str] = {}
    lines = content.splitlines()
    for i, line in enumerate(lines):
        for pkg in packages:
            if line.strip() == f'name = "{pkg}"':
                # Next line should be version = "x.y.z"
                if i + 1 < len(lines):
                    ver_match = re.match(r'version = "(.+)"', lines[i + 1].strip())
                    if ver_match:
                        versions[pkg] = ver_match.group(1)
    return versions


def test_app_manifest_pins_match_uv_lock():
    """Every pinned dependency in the app manifest must match the uv.lock resolution."""
    assert APP_PYPROJECT.exists(), f"App manifest not found: {APP_PYPROJECT}"
    assert UV_LOCK.exists(), f"uv.lock not found: {UV_LOCK}"

    app_pins = _parse_app_pins(APP_PYPROJECT.read_text(encoding="utf-8"))
    lock_versions = _parse_uv_lock_versions(
        UV_LOCK.read_text(encoding="utf-8"), PINNED_PACKAGES
    )

    errors = []
    for pkg in PINNED_PACKAGES:
        app_ver = app_pins.get(pkg)
        lock_ver = lock_versions.get(pkg)

        if app_ver is None:
            errors.append(f"  {pkg}: not pinned in app manifest (expected =={lock_ver})")
        elif lock_ver is None:
            errors.append(f"  {pkg}: not found in uv.lock")
        elif app_ver != lock_ver:
            errors.append(f"  {pkg}: app=={app_ver} but uv.lock=={lock_ver}")

    assert not errors, (
        "App manifest pins do not match uv.lock:\n" + "\n".join(errors)
    )


def test_all_direct_deps_are_pinned_exact():
    """Every dependency in the app manifest must use == (exact pin), not >= or ~=."""
    content = APP_PYPROJECT.read_text(encoding="utf-8")
    # Find the dependencies array
    in_deps = False
    unpinned = []
    for line in content.splitlines():
        if line.strip().startswith("dependencies"):
            in_deps = True
            continue
        if in_deps:
            if line.strip() == "]":
                break
            # Skip comments and blank lines
            stripped = line.strip().strip(",").strip('"')
            if not stripped or stripped.startswith("#"):
                continue
            if "==" not in stripped:
                unpinned.append(stripped)

    assert not unpinned, (
        "All app manifest dependencies must be pinned with ==.\n"
        f"Unpinned: {unpinned}"
    )
