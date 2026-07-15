# AGENTS.md — AI Agent Instructions

IMPORTANT! READ `~/.agents/AGENTS.md` IF PRESENT.

## Project Overview

Multimedia pipeline processor. Hierarchical stage-based architecture. Stages = composable blocks, pipelines = top-level entry points.

## Architecture

```
multimedia-pipeline/
├── __main__.py    # Top-level CLI entry point (subcommands → pipelines)
├── stages/        # Atomic or composite processing stages
├── shared/
│   └── output.py  # Shared output helpers. One place. All use.
├── multimedia_pipeline/
│   └── cli.py     # App CLI package
├── pipelines/     # Top-level entry points (call stages)
├── doc/           # Documentation (agents may write here)
├── test/          # Test fixtures (gitignored media files)
│   ├── sample/    # Input test files
│   ├── output/    # Output test files
│   └── stages/    # Test scripts per stage
└── old/           # Legacy reference projects (will be removed)
```

## Key Concepts

### Stages (`stages/`)

Self-contained processing unit with explicit inputs/outputs. Like a function.

- **Atomic stage**: single `.py` file (no config)
- **Composite stage**: folder with `run.py` entry point + sub-stages

#### Naming

Stage names **start with verb** (e.g., `extract_metadata.py`, `filter_podcast_audio.py`, `cut_segments.py`). Exception: boolean stages use `is_`/`has_` prefix.

#### Stage Lifecycle — Start Flat, Grow Organically

New stages = single `.py` file. Promote to folder only when needed.

**Promote to folder when:**
- Exceeds ~200 lines
- Needs internal helper modules
- Is sequence of sub-steps (mini-pipeline)
- Uses external tools (Docker-based utilities etc.)

When promoted, stage folder structure:
```
stages/my_stage/
├── __init__.py    # re-exports run() from run.py
├── run.py         # stage entry point
└── tools/         # external utilities owned by this stage
    └── my-tool/   # Docker-based tool with own run.sh
```

**Merge/inline when:**
- Two stages always called together, no independent use → combine
- Stage <30 lines trivial glue → inline into caller

On promotion, `.py` becomes folder with `run.py`, same external interface. Callers unchanged.

#### Stage Documentation

Every stage file self-documenting. Top of file:
- Module docstring: purpose, inputs, outputs, options
- Example usage (function call + CLI)
- Options reference with defaults

#### Stage Interface

Two parameter categories:

1. **Mandatory args** — explicit named args, fail if missing. Core inputs: file paths, data structures.
2. **Options dict** — single optional `options` param (dict) for tunable behavior: formats, bitrates, thresholds, flags. Defaults hardcoded in stage code.

No stage config files. Defaults in code. Pipelines own config.

#### Invocation

Two modes:
- **Python function** — called by pipelines, passing dicts. Primary mode.
- **CLI** — `uv run stages/my_stage.py --input file.wav --output out.wav --options '{"bitrate": 320}'` for standalone testing.

#### Example stage signature:
```python
def run(input_path: str, output_path: str, *, options: dict | None = None) -> dict:
    opts = {**DEFAULTS, **(options or {})}
    # ... process ...
    return {"output_path": output_path, "duration": 42.5}
```

### Pipelines (`pipelines/`)

Top-level orchestrators. Each pipeline:
- Own config YAML (defaults, overridable)
- Wire stages together for complete transformation
- Handle temp file lifecycle (`.~<stage_name>~<filename>` convention)
- Operate on SINGLE file per invocation

### Tools

External utilities (often Docker-based) owned by their stage. Live inside `stages/<stage>/tools/<tool-name>/` with own `run.sh` entry point. No top-level `tools/` dir — each stage contains its own tools.

### Temp Files

Convention: `.~<stage_name>~<original_filename>` — hidden, ignored by sync, deleted when done.

## Development Rules

1. **Python only via `uv`** — never create or use custom Python environments (`venv`, `virtualenv`, `conda`, `poetry env`, etc.); all Python execution must go through `uv run`, and all Python dependencies must be managed via `uv`
2. **No overwriting** — refuse clobber existing output unless forced
3. **Clean up** — temp files removed after use or on failure
4. **Config cascade** — external config > pipeline default > stage hardcoded defaults
5. **Stages pure** — no shared mutable state, no circular deps
6. **Stage composition** — stages may call other stages' `run()` to reduce duplication. Rules:
   - Import only `run()` — never internals
   - Each stage must work standalone
   - Composed stage owns its temp files
   - Prefer atomic when composition trivial (<30 lines glue) — inline instead
   - No circular deps
7. **No stage config files** — defaults in code; pipelines pass options dicts
8. **Never delete test samples** — `test/sample/` gitignored but never removed; manually curated fixtures
9. **Logging conventions** — uniform output formatting keeps logs scannable.

   **Stages** own detailed logging:
   ```python
   from shared.output import stage_header, stage_log, stage_timer

   if verbose:
       stage_header(_STAGE, src, dst, {"mode": mode})  # input → output + config
   with stage_timer(_STAGE, "done"):                   # times work, prints ✓
       do_work()
   ```
   Output looks like:
   ```
     cut                    → ◷ input.mp4 → output.mp4
     cut                    → ◷ mode=precise
     cut                    → ✓ done (12.3s)
   ```

   **Pipelines** log only start/end (stages log their own progress):
   ```python
   from shared.output import pipeline_timer

   with pipeline_timer(_PIPELINE, src.name, verbose) as pt:
       # stages run here and log themselves
       pt["output"] = final.name
   ```
   Output looks like:
   ```
   scrub_youtube_media    → ◷ video.mp4
     identify_youtube_media → ◷ video.mp4
     identify_youtube_media → ✓ fetch info (2.1s)
     cut                    → ◷ video.mp4 → output.mp4
     cut                    → ✓ cut (8.4s)
   scrub_youtube_media    → ✓ video_clean.mp4 (45.2s)
   ```

   **Never** use `print()` or `logging.info()` for user-facing progress.

10. **Minimal CLI args** — pipelines expose the fewest required args as positional, everything else optional. Top-level CLI in `__main__.py` uses argparse subcommands.
11. **No sleeping or polling** — never use `sleep` to wait for a command to finish. Long-running commands (pipelines, Docker builds) must run in the foreground. Wait for natural completion.
12. **Stages degrade gracefully** — I/O stages (those with `input_path` + `output_path`) that have nothing to do (empty operation list, no data, non-fatal error) must copy `input_path` to `output_path` and include `"passthrough": true` in the return dict. This ensures pipeline chains continue uninterrupted regardless of whether each stage found work to perform.

## Documentation (`doc/`)

- Write docs here for new stages/pipelines
- Read existing docs before modifying components
- Keep docs updated when behavior changes

Files in `doc/`:
- `architecture.md` — project structure, code responsibility, output formatting, config cascade. **Read this first** for a quick overview of how everything fits together. **Keep it updated** when adding stages or pipelines.

## File Awareness

Before working, agents:
1. Read this file
2. Read **all other `AGENTS.md` files** found anywhere in the project tree — each tool, stage, or sub-component may have its own rules, constraints, and context that override or extend the root instructions
3. Check `doc/` for relevant docs
4. Understand existing stages in `stages/`
5. Check `old/` for reference patterns (temporary)

## Testing (`test/`)

Tests live in `test/stages/`, one file per stage. Run with `uv run test/stages/<stage>.py`.

- Tests need sample files in `test/sample/` (gitignored, manually curated)
- Docker-using stages (clean_recorded_voice, remove_silences) auto-build images on first run — slow first time
- **After editing Dockerfile or entrypoint.sh, rebuild the Docker image manually** — `run.sh` only builds if image absent, not on file changes:
  ```bash
  docker build -t silence-remover stages/remove_silences/tools/silence-remover/
  docker build -t audio-filter stages/clean_recorded_voice/tools/audio-filter/
  ```
- Tests skip gracefully if sample files missing
- Some tests keep output in `test/output/` for manual A/B comparison

### Test suites

| Suite | Command | When to run |
|-------|---------|-------------|
| Quick (no media) | `uv run test/run_quick.py` | Every change — fast |
| Stage tests | `uv run test/stages/<stage>.py` | When stage changes |
| All stages | Run each `test/stages/*.py` manually | Before releasing |

## Config Format

All configs YAML. Only pipelines have config files. Stages have hardcoded defaults.

Pipeline config example:

```yaml
# pipelines/sponsorblock.yaml
stages:
  identify:
    method: "filename"
  cut:
    precise: false  # fast mode, no re-encode
  metadata:
    embed_chapters: true
```

