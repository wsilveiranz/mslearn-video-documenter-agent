# Evaluation Test Corpus

Place test video files in this directory (or configure `EVAL_VIDEO_CORPUS_PATH` to point to another directory).

## Setup

1. Place `.mp4`, `.mkv`, `.webm`, or `.avi` files in this directory
2. Update `manifest.json` with video metadata
3. Run `pytest -m eval` to execute evaluation tests

## Manifest format

See `manifest.json` for the expected structure. Each entry maps a video file to:
- Expected document types to test
- Brief content summary for validation
- Expected key topics/actions (for grounding checks)

## Configuration

- `EVAL_VIDEO_CORPUS_PATH` environment variable: Override the default corpus directory
- `--eval-corpus` pytest option: Override via CLI
