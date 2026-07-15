"""Test: scrub_youtube_podcast pipeline.

Runs the full pipeline against the standard sample file and keeps the
output in test/output/ for manual A/B listening.

Usage:
    uv run test/pipelines/scrub_youtube_podcast.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

SAMPLE = ROOT / "test/sample/Searching the Moon for Alien Technosignatures (160kbit_Opus).opus"
OUTPUT_DIR = ROOT / "test/output"

if not SAMPLE.exists():
    print(f"SKIP — sample file not found: {SAMPLE}")
    sys.exit(0)

# Remove any pre-existing output so --force isn't needed during development.
for stale in OUTPUT_DIR.glob("*.m4a"):
    if "Searching the Moon" in stale.name or "scrub_youtube_podcast" in stale.name:
        stale.unlink()
        print(f"Removed stale output: {stale.name}")

from pipelines.scrub_youtube_podcast import run  # noqa: E402

result = run(str(SAMPLE), output_dir=str(OUTPUT_DIR), force=True)

print("\nResult:")
for k, v in result.items():
    print(f"  {k}: {v}")

out = Path(result["output_path"])
assert out.exists(), f"Output file missing: {out}"
assert out.suffix == ".m4a", f"Expected .m4a output, got: {out.suffix}"
print("\nPASS")
