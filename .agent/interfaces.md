---
title: Interface Contracts
summary: Stage and pipeline function signatures, parameters, return values, and documentation standards.
updated: 2025-05-14
---

# Interface Contracts

## Stage Interface

### Signature

```python
def run(
    input_path: str,
    output_path: str,
    *,                           # keyword-only after this
    options: dict | None = None,
) -> dict:
```

Some stages have additional mandatory args (e.g., `cut` takes `remove: list`).

### Parameter Categories

1. **Mandatory args** — explicit, fail if missing. Core I/O paths + essential data.
2. **Options dict** — single `options` param for tunable behavior. Merged with `DEFAULTS`.

### Options Handling

```python
DEFAULTS: dict = {
    "mode": "precise",
    "verbose": True,
}

def run(input_path: str, output_path: str, *, options: dict | None = None) -> dict:
    opts = {**DEFAULTS, **(options or {})}
    # use opts["mode"], opts["verbose"], etc.
```

### Return Value

Always returns dict with at least `output_path`:

```python
{
    "output_path": "/path/to/output.mp4",
    "passthrough": False,          # True if stage had nothing to do
    "duration": 123.4,             # Optional: output duration
    # ... stage-specific keys
}
```

### Passthrough Convention

I/O stages with nothing to do must:
1. Copy input to output unchanged
2. Return `{"passthrough": True, ...}`

Ensures pipeline chains continue regardless of whether each stage found work.

### Error Handling

```python
if not src.exists():
    raise FileNotFoundError(f"Input not found: {src}")
if dst.exists():
    raise FileExistsError(f"Output exists: {dst}")
```

Stages raise, never return error dicts.

### Self-Documentation

Every stage starts with docstring:

```python
"""Stage: cut — remove time ranges from a media file.

Two modes:
  "precise" — Re-encodes, frame-accurate cuts. Slower.
  "fast"    — Stream copy, keyframe-accurate only. Faster.

Inputs:
    input_path  — path to source media
    output_path — path for output
    remove      — list of [start, end] pairs in seconds

Options:
    mode    — "precise" (default) | "fast"
    verbose — print progress (default: True)

Returns:
    {"output_path": "...", "removed_count": 3, "mode": "precise"}

Example:
    result = run("video.mp4", "cut.mp4", [[10.0, 30.0]])

    # CLI
    uv run -m stages.cut --input video.mp4 --output cut.mp4 \
        --remove '[[10.0, 30.0]]'
"""
```

## Pipeline Interface

### Signature

```python
def run(
    input_path: str,
    *,
    output_dir: str | None = None,
    output_path: str | None = None,
    force: bool = False,
    config_path: Path | None = None,
    options: dict | None = None,
) -> dict:
```

### Parameters

| Param | Purpose |
|-------|---------|
| `input_path` | Source file (required) |
| `output_dir` | Directory for output (optional) |
| `output_path` | Explicit output path (optional, overrides output_dir) |
| `force` | Overwrite existing output |
| `config_path` | Custom YAML config |
| `options` | Runtime overrides dict |

### Config Loading

```python
cfg = load_config(_DEFAULT_CONFIG, config_path, options)
verbose = cfg.get("verbose", True)
propagate_verbose(cfg)
stage_cfg = cfg.get("stages", {})
```

### Config Cascade

```
stage DEFAULTS → pipeline.yaml → custom --config → runtime options
```

### Verbose Propagation

`propagate_verbose(cfg)` sets `verbose` in each `stages.*` section automatically.

### Return Value

```python
{
    "output_path": "/path/to/output.mp4",
    "skipped": False,              # True if output existed and not force
    # ... stage results
}
```

### Skip Behavior

```python
if final_output.exists() and not force:
    pipeline_log(_PIPELINE, f"[dim]skip[/] {src.name} — output exists")
    return {"skipped": True, "output_path": str(final_output)}
```

## Logging Contract

### Stages

```python
from shared.output import stage_header, stage_log, stage_timer

if verbose:
    stage_header(_STAGE, src, dst, {"mode": mode})

with stage_timer(_STAGE, "done"):
    do_work()
```

### Pipelines

```python
from shared.output import pipeline_timer

with pipeline_timer(_PIPELINE, src.name, verbose) as pt:
    # stages log themselves
    pt["output"] = final.name
```

### Never Use

- `print()` for progress
- `logging.info()` for user-facing output

Use `stage_log()` / `pipeline_log()` instead.

## CLI Contract (Stages)

Every stage supports standalone CLI:

```python
def _cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--options", type=json.loads, default="{}")
    args = parser.parse_args()
    result = run(args.input, args.output, options=args.options)
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    _cli()
```

Usage:
```bash
uv run -m stages.cut --input video.mp4 --output cut.mp4 \
    --remove '[[10.0, 30.0]]' --options '{"mode": "fast"}'
```
