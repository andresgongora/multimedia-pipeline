# Multimedia Pipeline Agent Guide

## Shape

- `stages/` — reusable media operations. Atomic stage: one `.py` file; composite stage: directory with `run.py`.
- `pipelines/` — single-file workflows; own YAML config, orchestration, output naming, temp lifecycle.
- `shared/` — shared helpers, including user-facing output.
- `wrapper_scripts/` — personal convenience scripts, not general-purpose interface.
- `.agent/` — durable architecture, interface, decision, and frontier notes. Read relevant docs before changing behavior.
- `test/` — stage/pipeline test scripts. `test/sample/` and `test/output/` are gitignored media.

## Stage contracts

- Names start with verb; boolean checks use `is_` or `has_`.
- Public entrypoint: `run(input_path, output_path, *, options=None) -> dict`.
- Mandatory inputs are named arguments. Tunables belong in one `options` dict. Defaults live in stage code; stages have no config files.
- Stages are standalone, pure, no shared mutable state or circular imports. Compose only another stage's `run()`.
- I/O stages with no work or non-fatal failure copy input to output and return `{"passthrough": true}`.
- Stage module docstring states purpose, inputs, outputs, options, and Python/CLI example.
- Keep trivial glue (<30 lines) inline. Promote stage to directory only when it needs helpers, owns external tooling, is a multi-step flow, or has grown substantially.

## Pipeline and runtime rules

- Pipeline config cascade: external config > pipeline YAML > stage defaults.
- Temp files: `.~<stage_name>~<original_filename>`; clean them on success and failure.
- Never overwrite output without explicit force.
- Python only through `uv`; dependencies only through `uv`.
- Never delete `test/sample/` fixtures.
- No polling or `sleep`; run long commands in foreground.

## Output and CLI

- Stages own detailed progress; pipelines log start/end only.
- User-facing progress uses `shared.output`; never `print()` or `logging.info()`.
- Pipelines use minimal positional inputs; optional behavior uses flags. CLI entrypoint: `__main__.py` / `multimedia_pipeline/cli.py`.

## External tools

- Tool belongs in `stages/<stage>/tools/<tool-name>/`; no top-level `tools/`.
- Tool changes: read local `AGENTS.md`; rebuild corresponding Docker image after Dockerfile/entrypoint changes.

## Tests

- Quick: `uv run test/run_quick.py`.
- Stage: `uv run test/stages/<stage>.py`.
- Docker-backed tests may be slow first run and skip when media fixtures are absent.

## Documentation

- Update relevant `.agent/` docs when behavior, contracts, or architecture changes.
- `architecture.md` is system map; `interfaces.md` is contract reference; `frontier.md` is current repo boundary.
