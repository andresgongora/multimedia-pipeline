---
title: Boilerplate Templates
summary: Copy-paste templates for creating new stages and pipelines.
updated: 2025-05-14
---

# Boilerplate Templates

## Stage Template

```python
"""Stage: my_stage — one-line description.

Longer description of what this stage does...

Inputs:
    input_path  — path to source file
    output_path — path for output file

Options:
    option1 — description (default: value)
    verbose — print progress (default: True)

Returns:
    {
      "output_path": "...",
      "some_metric": 42,
    }

Example:
    from stages.my_stage import run
    result = run("input.mp4", "output.mp4")
    result = run("input.mp4", "output.mp4", options={"option1": "custom"})

    # CLI
    uv run -m stages.my_stage --input input.mp4 --output output.mp4
    uv run -m stages.my_stage --input input.mp4 --output output.mp4 \
        --options '{"option1": "custom"}'
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from shared.output import stage_header, stage_timer

_STAGE = "my_stage"

DEFAULTS: dict = {
    "option1": "default_value",
    "verbose": True,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run(input_path: str, output_path: str, *, options: dict | None = None) -> dict:
    """Process a single file."""
    opts = {**DEFAULTS, **(options or {})}
    verbose = opts["verbose"]

    src = Path(input_path)
    dst = Path(output_path)

    # Validate
    if not src.exists():
        raise FileNotFoundError(f"Input not found: {src}")
    if dst.exists():
        raise FileExistsError(f"Output exists: {dst}")

    dst.parent.mkdir(parents=True, exist_ok=True)

    # Log
    if verbose:
        stage_header(_STAGE, src, dst, {"option1": opts["option1"]})

    # Process
    with stage_timer(_STAGE, "done"):
        # TODO: actual processing
        # shutil.copy2(src, dst)  # placeholder
        pass

    return {
        "output_path": str(dst),
        "some_metric": 42,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--input", required=True, help="Input file")
    parser.add_argument("--output", required=True, help="Output file")
    parser.add_argument("--options", type=json.loads, default="{}", help="JSON options")
    args = parser.parse_args()
    result = run(args.input, args.output, options=args.options)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    _cli()
```

## Pipeline Template

```python
"""Pipeline: my_pipeline — one-line description.

Longer description of the workflow...

Config (pipelines/my_pipeline.yaml):
    verbose         — print progress (default: true)
    stages.stage1   — options for stage1
    stages.stage2   — options for stage2

Usage:
    uv run -m pipelines.my_pipeline input.mp4
    uv run -m pipelines.my_pipeline input.mp4 -o /out/dir
    uv run -m pipelines.my_pipeline /dir/of/files -r
    uv run -m pipelines.my_pipeline input.mp4 --force
    uv run -m pipelines.my_pipeline input.mp4 --config custom.yaml
"""
from __future__ import annotations

from pathlib import Path

from shared.config import load_config, propagate_verbose
from shared.io import safe_output_path
from shared.output import pipeline_log, pipeline_timer
import stages.stage1 as stage1
import stages.stage2 as stage2

_PIPELINE = "my_pipeline"
_DEFAULT_CONFIG = Path(__file__).with_suffix(".yaml")


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def run(
    input_path: str,
    *,
    output_dir: str | None = None,
    output_path: str | None = None,
    force: bool = False,
    config_path: Path | None = None,
    options: dict | None = None,
) -> dict:
    """Process a single file."""

    # ── 1. Config ─────────────────────────────────────────────────────────
    cfg = load_config(_DEFAULT_CONFIG, config_path, options)
    verbose = cfg.get("verbose", True)
    propagate_verbose(cfg)
    stage_cfg = cfg.get("stages", {})

    # ── 2. Validate input ─────────────────────────────────────────────────
    src = Path(input_path)
    if not src.exists():
        raise FileNotFoundError(f"Input not found: {src}")

    # ── 3. Resolve output ─────────────────────────────────────────────────
    out_dir = Path(output_dir) if output_dir else src.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    if output_path:
        final_output = safe_output_path(src, Path(output_path))
    else:
        final_output = safe_output_path(src, out_dir / f"{src.stem}_processed{src.suffix}")

    # ── 4. Skip check ─────────────────────────────────────────────────────
    if final_output.exists() and not force:
        if verbose:
            pipeline_log(_PIPELINE, f"[dim]skip[/] {src.name} — output exists")
        return {"skipped": True, "input_path": str(src), "output_path": str(final_output)}

    if force and final_output.exists():
        final_output.unlink()

    # ── 5. Execute stages ─────────────────────────────────────────────────
    temps: list[Path] = []
    try:
        with pipeline_timer(_PIPELINE, src.name, verbose) as pt:
            # Stage 1
            temp1 = out_dir / f".~stage1~{src.name}"
            temps.append(temp1)
            r1 = stage1.run(str(src), str(temp1), options=stage_cfg.get("stage1"))

            # Stage 2
            r2 = stage2.run(str(temp1), str(final_output), options=stage_cfg.get("stage2"))

            pt["output"] = final_output.name

    finally:
        for t in temps:
            if t.exists():
                t.unlink()

    return {
        "input_path": str(src),
        "output_path": str(final_output),
        "stage1_result": r1,
        "stage2_result": r2,
    }
```

## Pipeline Config Template

Create `pipelines/my_pipeline.yaml`:

```yaml
# Pipeline: my_pipeline
# Default configuration

verbose: true

stages:
  stage1:
    option1: "default"
  stage2:
    option2: 42
```

## Composite Stage Template (Folder)

Structure:
```
stages/my_composite/
├── __init__.py
├── run.py
└── tools/
    └── my-tool/
        ├── Dockerfile
        └── run.sh
```

`stages/my_composite/__init__.py`:
```python
from .run import run

__all__ = ["run"]
```

`stages/my_composite/run.py`:
```python
"""Stage: my_composite — one-line description.

Uses Docker-based tool for processing...
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from shared.output import stage_header, stage_timer

_STAGE = "my_composite"
_TOOLS_DIR = Path(__file__).parent / "tools"

DEFAULTS: dict = {
    "tool_option": "default",
    "verbose": True,
}


def run(input_path: str, output_path: str, *, options: dict | None = None) -> dict:
    opts = {**DEFAULTS, **(options or {})}
    verbose = opts["verbose"]

    src = Path(input_path).resolve()
    dst = Path(output_path).resolve()

    if not src.exists():
        raise FileNotFoundError(f"Input not found: {src}")
    if dst.exists():
        raise FileExistsError(f"Output exists: {dst}")

    run_sh = _TOOLS_DIR / "my-tool" / "run.sh"
    if not run_sh.exists():
        raise FileNotFoundError(f"Tool not found: {run_sh}")

    if verbose:
        stage_header(_STAGE, src, dst, {"tool_option": opts["tool_option"]})

    with stage_timer(_STAGE, "done"):
        cmd = [str(run_sh), str(src), str(dst), opts["tool_option"]]
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=dst.parent)

    if result.returncode != 0:
        raise RuntimeError(f"Tool failed:\n{result.stderr}")

    return {"output_path": str(dst)}
```

## Adding Pipeline to CLI

Edit `multimedia_pipeline/cli.py`:

```python
@app.command()
def my_pipeline(
    input: InputArg,
    output: OutputOpt = None,
    recursive: RecursiveOpt = False,
    force: ForceOpt = False,
    config: ConfigOpt = None,
) -> None:
    """One-line description for --help."""
    from pipelines import my_pipeline as pipeline
    _run_pipeline(pipeline.run, input, output, recursive, force, config)
```
