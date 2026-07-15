---
title: Architecture Overview
summary: System structure, responsibility domains, conventions, and data flow.
updated: 2026-07-10
---

# Architecture Overview

## System Flow

```
User → CLI → Pipeline → Stage₁ → Stage₂ → ... → Output
                ↓
           Config YAML
```

Hierarchical stage-based processor. Stages = reusable blocks. Pipelines = user-facing workflows.

## Directory Structure

```
multimedia-pipeline/
├── __main__.py              # CLI entry (delegates to multimedia_pipeline/cli.py)
├── multimedia_pipeline/
│   └── cli.py               # Typer CLI: subcommands, dir expansion, per-file dispatch
├── pipelines/               # User-facing workflows
│   ├── scrub_youtube_media.py
│   ├── scrub_youtube_media.yaml
│   └── ...
├── stages/                  # Reusable processing units
│   ├── cut.py               # Atomic stage (single file)
│   ├── remove_silences/     # Composite stage (folder)
│   │   ├── __init__.py
│   │   ├── run.py
│   │   └── tools/           # Docker-based external tools
│   └── ...
├── shared/                  # Common utilities
│   ├── config.py            # YAML loading, deep merge, verbose propagation
│   ├── ffprobe.py           # Media probing helpers
│   ├── io.py                # Output path resolution, safety checks
│   └── output.py            # Rich-based logging helpers
├── doc/                     # Documentation
│   └── bugs/                # Bug logs (root cause + fix, keep after resolve)
└── test/                    # Test fixtures and scripts
    ├── sample/              # Input fixtures (gitignored)
    ├── output/              # Output for A/B comparison (gitignored)
    └── stages/              # Per-stage test scripts
```

## Responsibility Domains

| Layer | Owns | Does Not Own |
|-------|------|--------------|
| **CLI** (`multimedia_pipeline/cli.py`) | Arg parsing, dir expansion, per-file dispatch, exit codes | Processing logic, config interpretation |
| **Pipeline** (`pipelines/*.py`) | Stage orchestration, config loading, temp file lifecycle, output naming | Low-level media operations |
| **Stage** (`stages/*.py`) | Single processing operation, self-contained logic, CLI for testing | Multi-file orchestration, config files |
| **Shared** (`shared/`) | Cross-cutting utilities (logging, probing, config) | Business logic |

## Stage Types

| Type | Structure | When to use |
|------|-----------|-------------|
| **Atomic** | Single `.py` file | Most stages. <200 lines, no external tools |
| **Compound** | Single `.py` calling other stages | Combines existing stages. <30 lines glue |
| **Composite** | Folder with `run.py` + `tools/` | Uses Docker tools, needs internal helpers |

### Lifecycle: Start Flat, Grow Organically

New stage = single `.py`. Promote to folder when:
- Exceeds ~200 lines
- Needs internal helper modules
- Uses Docker-based tools

Merge/inline when:
- Two stages always called together → combine
- Stage <30 lines trivial glue → inline

## Conventions

### Config Cascade

```
stage DEFAULTS → pipeline.yaml → custom --config → runtime options
```

Each layer deep-merges onto previous.

### Temp Files

Pattern: `.~<stage_name>~<original_filename>`

- Hidden (dot prefix)
- Same directory as output
- Cleaned in `finally` blocks

### Import Style

```python
import stages.cut as cut
result = cut.run(input, output, segments)
```

Not `from stages.cut import run`.

### Naming

- Stages start with verb: `extract_audio`, `convert_to_wav`, `filter_podcast_audio`, `cut`
- Exception: boolean stages use `is_`/`has_` prefix
- Pipelines describe workflow: `scrub_youtube_media`

### Verbosity

All stages/pipelines accept `verbose` (default `True`). When `False`, only errors print.

### No Overwrite

Stages refuse to clobber existing output. Pipelines skip (or delete if `force=True`).

### Passthrough

I/O stages with nothing to do must copy input → output unchanged and return `{"passthrough": True}`.

## Logging Hierarchy

Pipelines bold, stages indented/dim:

```
scrub_youtube_media    → ◷ video.mp4
  identify             → ◷ video.mp4
  identify             → ✓ identified (2.1s)
  cut                  → ◷ video.mp4 → output.mp4
  cut                  → ✓ done (8.4s)
scrub_youtube_media    → ✓ video_clean.mp4 (45.2s)
```

## Testing

```
test/
├── sample/         # Input fixtures (gitignored, manually curated)
├── output/         # Output for A/B comparison
└── stages/         # Per-stage test scripts
```

Run: `uv run test/stages/<stage>.py`

- Tests skip if samples missing
- Docker stages auto-build first run
- Never delete test samples

## CLI Usage

```bash
uv run -m multimedia_pipeline scrub-youtube-media video.mp4
uv run -m multimedia_pipeline scrub-youtube-media /videos -r
uv run -m multimedia_pipeline scrub-youtube-media video.mp4 -o /output
uv run -m multimedia_pipeline scrub-youtube-media video.mp4 --force
uv run -m multimedia_pipeline scrub-youtube-media video.mp4 --config my.yaml
```

## See Also

- [interfaces.md](interfaces.md) — Stage and pipeline contracts
- [boilerplate.md](boilerplate.md) — Templates for new components
- [reference.md](reference.md) — Shared modules and component tables
