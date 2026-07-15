# AGENTS.md

Operating guide for agents working on the audio-filter Docker tool.

**Parent context:** This tool is owned by the `clean_recorded_voice` stage in the multimedia-pipeline project. See the root `AGENTS.md` for project-wide conventions.

## Project Scope

- Spoken-word audio post-processing for YouTube tutorial videos.
- Self-contained Docker tool: all dependencies (ffmpeg, DeepFilterNet) are inside the image.
- Goal: stable, repeatable audio rendering with objective loudness verification.

## Primary Documentation Anchor

- **Read first for all tuning/filter decisions:** `docs/audio-filter-playbook.md`.
- Canonical reference for voice context, processing order, stage tradeoffs, preset strategy (`natural`/`broadcast`/future `podcast`), and clarity-first decision criteria.
- If script behavior or recommendation logic changes, update `docs/audio-filter-playbook.md` in the same change set.

## Source of Truth Files

### Filter Script

- `scripts/filter.sh`: **Canonical production filter.** This is what the Docker image runs.

### Docker Assets

- `Dockerfile`: Builds the `audio-filter` image using `scripts/filter.sh` + DeepFilterNet binary.
- `run.sh`: Host wrapper — auto-builds image if absent, then runs it against the current directory.
- `scripts/docker-entrypoint.sh`: Container entrypoint; resolves bare filenames to `/data`.

### Python Tools (in `tools/`)

- `clearvoice_enhance.py` / `.sh`: ClearVoice MossFormer2 speech enhancement (experimental).
- `dereverb_wpe.py`: Offline WPE dereverberation (experimental).
- `deep-filter-0.5.6`: Statically-linked DeepFilterNet binary (used by Docker image).

### Documentation

- `docs/audio-filter-playbook.md`: **Primary tuning playbook (canonical).**
- `docs/voice-presence-troubleshooting.md`: Troubleshooting "far away" voice issues.

## Current Processing Policy

- Loudness target: `-14 LUFS` integrated.
- True-peak ceiling: `-1 dBTP`.
- Preferred LRA range for tutorials: `5-8 LU`.
- Canonical production script: `scripts/filter.sh` (Docker only).
- To process audio: `./run.sh input.m4a output.m4a`

## Workflow Rules

1. Use `docs/audio-filter-playbook.md` as the first reference for any tuning decision.
2. Treat `scripts/filter.sh` as the canonical script truth unless explicitly changed by the user.
3. Record objective metrics before recommending a filter change.
4. Update documentation when filter logic, targets, or recommendations change.

## Required Script Decoration and Documentation Style

All new or refactored shell scripts should follow the style in `scripts/filter.sh`.

### Filter Chain Documentation Rule

**Every filter stage in `build_filter_chain()` must have a numbered inline comment block above `build_filter_chain()` that explains:**

- What the filter does technically
- Why it is needed for this specific recording context (lavalier mic, small room, male voice)
- Why it is placed at this position in the chain

If you add, remove, reorder, or retune a filter stage, update its corresponding comment. A filter without a documented justification must not be merged.

### Structural Template

- Start with:
  - `#!/usr/bin/env bash`
  - `set -euo pipefail`
- Use section separators exactly in this style:

```bash
##==================================================================================================
##  Section Name
##==================================================================================================
```

- Standard section order (adjust as needed):
  1. `Requirements`
  2. `Helpers` / `Filter workflow` / `Workflow helpers`
  3. `Processing`
  4. `Main`

### Function Documentation Pattern

- Add a one-line doc comment immediately above each function:

```bash
## Describes what the function does in one clear sentence.
function_name() {
  ...
}
```

- Use action-oriented wording (`Validates`, `Builds`, `Runs`, `Parses`, `Orchestrates`).
- Keep comments concise and factual.

### Implementation Conventions

- Use local variables inside functions (`local var_name=...`).
- Validate required commands with `require_command`.
- Validate files with `require_file`.
- Keep filter chains in strict stage order and readable multiline heredocs where appropriate.
- Keep `main()` as the orchestration entrypoint and end scripts with:

```bash
main "$@"
```

- Emit clear usage/help text when arguments are missing.
- Use predictable success messages (output path + key mode/preset).

## Tooling and Environment Constraints

- Shell: `bash`.
- Host OS is NixOS; assume no FHS environment unless explicitly provided.
- Primary runtime dependency: `ffmpeg`.
- Do **not** use `nix-shell` in instructions, scripts, or runbooks for this project.
- Prefer direct host-installed tools and explicit dependency checks.
- If a required command/tool is not available, ask the user to install it before proceeding.
- Do not use `rm`, use `trash`, it works for files and directories.
- Do not run commands in the background or with `&` to avoid orphaned processes.
- Assume commands will run in the command line with direct user supervision; if there is nothing going on, the command never run (very likely no need to wait for it to complete wiht `timeout`).

## Python

- Use `uv` and `pyproject.toml`.

## Common problems

- Use `fhs -c` to run scripts in a more traditional environment if you encounter issues with missing commands or unexpected behavior due to the NixOS environment. Example, when `libstdc++.so.6` is missing. Only for NixOS.

## Update Checklist for Future Agents

When making meaningful changes:

1. Update relevant script(s) using the decoration/documentation style above.
2. Run targeted render/test to verify outputs.
3. Capture or confirm objective metrics (`I`, `TP`, `LRA`).
4. Update `docs/audio-filter-playbook.md` when workflow, context, or recommendation logic changes.

## Quick Operational Commands

```bash
# Process audio (builds image automatically if not present)
./run.sh sample.m4a output.m4a

# Rebuild image explicitly
docker build -t audio-filter .
```

Use these as baseline verification steps before and after significant filter changes.
