"""§32a: Assert the vendored deploy copy of log.py is byte-identical to src/porchlight/log.py.

If this test fails, run:
    uv run python scripts/sync_deploy_log.py

The deploy copy is generated. The source of truth is src/porchlight/log.py.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SOURCE = REPO_ROOT / "src" / "porchlight" / "log.py"
DEST = (
    REPO_ROOT
    / "deploy"
    / "spike_b"
    / "porchlightspike"
    / "app"
    / "porchlight_spike"
    / "porchlight"
    / "log.py"
)


def test_deploy_log_is_byte_identical_to_source():
    """The vendored log.py in the deploy zip must be byte-identical to src/porchlight/log.py."""
    assert SOURCE.exists(), f"Source not found: {SOURCE}"
    assert DEST.exists(), f"Deploy copy not found: {DEST}"

    source_bytes = SOURCE.read_bytes()
    dest_bytes = DEST.read_bytes()

    assert source_bytes == dest_bytes, (
        f"Deploy copy has drifted from source.\n"
        f"  Source: {SOURCE.relative_to(REPO_ROOT)} ({len(source_bytes)} bytes)\n"
        f"  Deploy: {DEST.relative_to(REPO_ROOT)} ({len(dest_bytes)} bytes)\n"
        f"Run: uv run python scripts/sync_deploy_log.py"
    )
