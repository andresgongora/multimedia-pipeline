# multimedia-pipeline

[![GitHub release](https://img.shields.io/github/v/release/andresgongora/multimedia-pipeline)](https://github.com/andresgongora/multimedia-pipeline/releases)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![AGENTS.md](https://img.shields.io/badge/AGENTS.md-compatible-blue)](AGENTS.md)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Buy Me A Coffee](https://img.shields.io/badge/Buy_Me_A_Coffee-tip-yellow)](https://buymeacoffee.com/andresgongora)

Modular audio/video processing pipeline. Wires small composable stages into
user-facing workflows. Built for personal use; shared in case it helps.

Parts of this were written with AI assistance.

<!------------------------------------------------------------------------------------------------->
## Requirements
<!------------------------------------------------------------------------------------------------->

- [uv](https://docs.astral.sh/uv/) (Python package manager)
- [Docker](https://www.docker.com/) (used by some stages for audio filtering)
- `ffmpeg` on your PATH

`clean_recorded_voice` downloads the pinned
[DeepFilterNet v0.5.6](https://github.com/Rikorose/DeepFilterNet/releases/tag/v0.5.6)
x86_64 Linux binary while Docker builds its `audio-filter` image. Checksum verified during build.
First run needs internet access; other pipelines do not.

<!------------------------------------------------------------------------------------------------->
## Install
<!------------------------------------------------------------------------------------------------->

```bash
git clone https://github.com/andresgongora/multimedia-pipeline.git
cd multimedia-pipeline
uv sync
```

First run of any Docker-backed stage builds the image automatically. Takes a few minutes once.

<!------------------------------------------------------------------------------------------------->
## Usage
<!------------------------------------------------------------------------------------------------->

```bash
uv run multimedia-pipeline --help
```

### Pipelines

**`extract-and-clean-voice`** — extract audio from video, isolate and clean voice

```bash
uv run multimedia-pipeline extract-and-clean-voice video.mp4
uv run multimedia-pipeline extract-and-clean-voice /path/to/videos/
uv run multimedia-pipeline extract-and-clean-voice /path/to/videos/ --force
uv run multimedia-pipeline extract-and-clean-voice /path/to/videos/ --config custom.yaml --quiet
```

Output: `.wav` file next to source.

**`remove-silences-and-extract-clean-voice`** — remove silences first, then extract and clean voice

```bash
uv run multimedia-pipeline remove-silences-and-extract-clean-voice video.mp4
uv run multimedia-pipeline remove-silences-and-extract-clean-voice /path/to/videos/ --force
```

**`scrub-youtube-media`** — fetch SponsorBlock timestamps, cut sponsor
segments, strip metadata, embed clean YouTube metadata, suggest tidy filename

```bash
uv run multimedia-pipeline scrub-youtube-media podcast.opus
uv run multimedia-pipeline scrub-youtube-media /path/to/downloads/
uv run multimedia-pipeline scrub-youtube-media podcast.opus --force --quiet
```

**`scrub-youtube-podcast`** — like `scrub-youtube-media` but tuned for podcast
audio (filters to voice range, normalizes levels)

```bash
uv run multimedia-pipeline scrub-youtube-podcast podcast.opus
uv run multimedia-pipeline scrub-youtube-podcast /path/to/downloads/ -o /path/to/output/
```

<!------------------------------------------------------------------------------------------------->
## Architecture
<!------------------------------------------------------------------------------------------------->

```text
User → CLI → Pipeline → Stage₁ → Stage₂ → ... → Output
                ↓
           Config YAML
```

| Layer        | Owns                                                      |
| ------------ | --------------------------------------------------------- |
| **CLI**      | Arg parsing, dir expansion, per-file dispatch, exit codes |
| **Pipeline** | Stage orchestration, config loading, temp file lifecycle  |
| **Stage**    | Single processing operation, self-contained logic         |
| **Shared**   | Cross-cutting utilities (logging, probing, config)        |

Stages come in two forms: atomic (single `.py` file) or composite (folder with
`run.py` + `tools/` for Docker-based external tools). New stages start flat and
grow organically.

Config cascade: `stage defaults → pipeline YAML → custom --config → runtime
options`. Each layer deep-merges onto previous.

<!------------------------------------------------------------------------------------------------->
## Project Layout
<!------------------------------------------------------------------------------------------------->

```text
stages/          reusable processing stages (atomic or composite)
pipelines/       top-level entry points that wire stages together
shared/          output/logging helpers
wrapper_scripts/ personal convenience scripts (not general-purpose)
test/            test scripts; sample and output files are gitignored
```

<!------------------------------------------------------------------------------------------------->
## Development
<!------------------------------------------------------------------------------------------------->

```bash
uv sync --extra dev        # install dev deps (includes Ruff)
uv run ruff check .        # lint
uv run test/run_quick.py   # quick tests (no media files needed)
```

Stage tests require sample media files in `test/sample/` (gitignored, not included).

<!------------------------------------------------------------------------------------------------->
## Wrapper Scripts
<!------------------------------------------------------------------------------------------------->

`wrapper_scripts/` contains shell scripts for batch-processing folders. Not
general-purpose tools. Look at them for examples of how to call the CLI in a
loop, handle output directories, and forward options.

<!------------------------------------------------------------------------------------------------->
## Contributing
<!------------------------------------------------------------------------------------------------->

Issues and pull requests welcome. Please run `uv run ruff check .` and
`uv run test/run_quick.py` before submitting.

<!------------------------------------------------------------------------------------------------->
## Donations
<!------------------------------------------------------------------------------------------------->

If you like this project and want to show your support,
[buy me a coffee](https://buymeacoffee.com/andresgongora). Caffeine goes in, code comes out.

<!------------------------------------------------------------------------------------------------->
## License
<!------------------------------------------------------------------------------------------------->

[MIT](./LICENSE)
