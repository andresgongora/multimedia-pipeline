# multimedia-pipeline

Modular audio/video processing pipeline. Each pipeline wires together small, composable stages. Built for personal use; shared in case it's useful.

Parts of this were written with AI assistance.

## Requirements

- [uv](https://docs.astral.sh/uv/) (Python package manager).
- [Docker](https://www.docker.com/) (used by some stages for audio filtering).
- `ffmpeg` on your PATH.

`clean_recorded_voice` downloads the pinned
[DeepFilterNet v0.5.6](https://github.com/Rikorose/DeepFilterNet/releases/tag/v0.5.6)
x86_64 Linux binary while Docker builds its `audio-filter` image. Its checksum is
verified during the build. This stage needs internet access on first use; other
pipelines do not.

## Install

```bash
git clone https://github.com/andresgongora/multimedia-pipeline.git
cd multimedia-pipeline
uv sync
```

The first run of any Docker-backed stage will build the image automatically. That takes a few minutes once.

## Usage

The simplest thing you can do is use the built-in help to see available pipelines and options. I've put extra care to make it intuitive and self-documenting.

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

Output: `.wav` file next to the source.

**`remove-silences-and-extract-clean-voice`** — remove silences first, then extract and clean voice

```bash
uv run multimedia-pipeline remove-silences-and-extract-clean-voice video.mp4
uv run multimedia-pipeline remove-silences-and-extract-clean-voice /path/to/videos/ --force
```

**`scrub-youtube-media`** — fetch SponsorBlock timestamps, cut sponsor segments, strip metadata, embed clean YouTube metadata, suggest a tidy filename

```bash
uv run multimedia-pipeline scrub-youtube-media podcast.opus
uv run multimedia-pipeline scrub-youtube-media /path/to/downloads/
uv run multimedia-pipeline scrub-youtube-media podcast.opus --force --quiet
```

**`scrub-youtube-podcast`** — like `scrub-youtube-media` but tuned for podcast audio (filters to voice range, normalizes levels)

```bash
uv run multimedia-pipeline scrub-youtube-podcast podcast.opus
uv run multimedia-pipeline scrub-youtube-podcast /path/to/downloads/ -o /path/to/output/
```

## Wrapper scripts

`wrapper_scripts/` contains shell scripts I use personally to batch-process folders on my machine. They are not general-purpose tools. Look at them for examples of how to call the CLI in a loop, handle output directories, and forward options.

## Project layout

```text
stages/          reusable processing stages (atomic or composite)
pipelines/       top-level entry points that wire stages together
shared/          output/logging helpers
wrapper_scripts/ personal convenience scripts (not general-purpose)
doc/             internal documentation
test/            test scripts; sample and output files are gitignored
```

## Development

```bash
uv sync --extra dev   # install dev deps (includes Ruff)
uv run ruff check .   # lint
uv run test/run_quick.py  # quick tests (no media files needed)
```

Stage tests require sample media files in `test/sample/` (gitignored, not included).

## License

MIT. See [LICENSE](LICENSE).
