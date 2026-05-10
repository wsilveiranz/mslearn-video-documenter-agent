# MS Learn Video Documenter Agent

An AI-powered agent that transforms screen recording videos into structured Microsoft Learn-style documentation.

## Overview

The Video Documenter Agent processes screen recordings through a 6-agent pipeline — extracting frames, transcripts, and on-screen text — and generates publication-ready Markdown documents that conform to Microsoft Learn's voice, tone, style guide, and document structure.

### Key Features

- **Video-to-documentation pipeline**: Process screen recordings and generate MS Learn articles (Quickstart, Tutorial, How-to, Concept, Overview)
- **MS Learn compliance**: Generated content follows Microsoft's voice principles, grammar rules, and Markdown extensions
- **Iterative refinement**: Automatic revision loop — the Editor re-edits until the Evaluate agent passes
- **Dual processing modes**: Azure-native services (cloud) or open-source tools (local)
- **Multiple interfaces**: CLI, REST API, or VS Code Chat Participant (`@video-documenter`)

### Architecture

```
Video → Ingestion → Extraction → Structure → Writer → Editor → Evaluate → MS Learn Markdown
                                                          ▲                    │
                                                          │    Revision Loop   │
                                                          └────────────────────┘
```

Built with:
- **Microsoft Agent Framework (MAF) v1.0** — multi-agent orchestration
- **Azure AI Foundry** — GPT-4o/GPT-4o-mini for vision + generation
- **Azure Video Indexer** — scene detection, OCR, keyframes, transcription (cloud mode)
- **FFmpeg + PySceneDetect + Whisper** — video processing (local mode)
- **FastAPI** — backend API with WebSocket progress streaming
- **VS Code Chat Participant API** — primary user interface

## Getting started

### Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.11+ | Required |
| FFmpeg | 6.0+ | Required for local mode |
| Azure CLI | Latest | Required for `DefaultAzureCredential` |
| Azure AI Foundry project | — | GPT-4o / GPT-4o-mini deployments |
| Node.js | 18+ | Only for VS Code extension development |

### Install FFmpeg

FFmpeg is required for video processing (audio extraction, keyframe capture, metadata probing).

**Windows (winget):**
```powershell
winget install Gyan.FFmpeg
```

**macOS (Homebrew):**
```bash
brew install ffmpeg
```

**Linux (apt):**
```bash
sudo apt update && sudo apt install ffmpeg
```

Verify installation:
```bash
ffmpeg -version
```

> [!NOTE]
> If FFmpeg is installed but not on your system `PATH`, set the `FFMPEG_PATH` environment variable in your `.env` file to the full path of the `ffmpeg` binary.

### Install Python dependencies

```bash
cd backend

# Core dependencies
pip install -e .

# Local mode extras (Whisper, SceneDetect, OpenCV)
pip install -e ".[local]"

# Development tools (pytest, ruff, pyright)
pip install -e ".[dev]"
```

### Configure environment

Copy the example configuration and fill in your Azure AI Foundry endpoint:

```bash
cd backend
cp .env.example .env
```

Edit `.env` with your values:

```dotenv
# Required for all modes
PROCESSING_MODE=local
FOUNDRY_PROJECT_ENDPOINT=https://your-project.services.ai.azure.com
FOUNDRY_MODEL=gpt-4o
FOUNDRY_MODEL_MINI=gpt-4o-mini

# Local mode settings
WHISPER_MODEL=base
FFMPEG_PATH=ffmpeg

# Output directory
OUTPUT_DIRECTORY=./output
```

Sign in to Azure CLI for authentication:

```bash
az login
```

> [!IMPORTANT]
> This project uses `DefaultAzureCredential` — no API keys needed. Your Azure CLI credential is used locally; Managed Identity is used in production.

---

## Running the agent

### CLI mode

Process a video file directly from the command line:

```bash
cd backend

# Basic usage — generates a tutorial in local mode
python src/main.py process path/to/video.mp4 --mode local

# Specify document type
python src/main.py process path/to/video.mp4 --mode local --doc-type quickstart
python src/main.py process path/to/video.mp4 --mode local --doc-type tutorial
python src/main.py process path/to/video.mp4 --mode local --doc-type how-to
python src/main.py process path/to/video.mp4 --mode local --doc-type concept
python src/main.py process path/to/video.mp4 --mode local --doc-type overview

# Custom output directory
python src/main.py process path/to/video.mp4 --mode local --doc-type tutorial --output ./my-docs
```

> [!IMPORTANT]
> The `--mode` flag controls how video extraction runs. Use `--mode local` for local processing with FFmpeg + Whisper (recommended for development). Cloud mode (`--mode cloud`) requires Azure Video Indexer, which isn't yet implemented. If omitted, the mode defaults to the `PROCESSING_MODE` value in your `.env` file.

**Output:** The generated Markdown file and media assets are saved to the output directory (default: `./output/`).

```
output/
├── <document-id>.md        # Generated MS Learn article
└── media/
    ├── keyframe_001.png    # Extracted screenshots
    ├── keyframe_002.png
    └── ...
```

**Example** (provide your own video file):

```bash
python src/main.py process path/to/your-video.mp4 --mode local --doc-type tutorial
```

```
Document saved to output/abc123.md
Quality score: 0.85 (PASSED)
```

### API server mode

Start the FastAPI server for HTTP/WebSocket access:

```bash
cd backend

# Start with auto-reload (development)
python src/main.py

# Or explicitly with uvicorn
uvicorn src.main:app --host 127.0.0.1 --port 8000 --reload
```

API endpoints:

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/health` | Health check |
| `POST` | `/api/v1/videos/ingest` | Upload and ingest a video |
| `GET` | `/api/v1/videos/{video_id}/status` | Check processing status |
| `GET` | `/api/v1/videos/{video_id}/extraction` | Get extraction results |
| `POST` | `/api/v1/documents/generate` | Generate documentation from ingested video |
| `GET` | `/api/v1/documents/{document_id}` | Retrieve a generated document |
| `POST` | `/api/v1/documents/{document_id}/refine` | Refine a generated document with feedback |
| `WS` | `/api/v1/ws/{video_id}` | WebSocket for real-time progress |

Interactive API docs available at `http://127.0.0.1:8000/docs` when the server is running.

---

## VS Code extension (development)

The `@video-documenter` Chat Participant runs inside VS Code's Copilot Chat panel. To test it locally:

### 1. Start the backend

```bash
cd backend
python -m src.main
# Verify: curl http://localhost:8000/api/v1/health
```

### 2. Build and launch the extension

```bash
cd vscode-extension
npm install
npm run compile
```

Then press **F5** in VS Code (with `vscode-extension/` open) to launch the **Extension Development Host**, or run:

```bash
code --extensionDevelopmentPath=./vscode-extension --new-window
```

### 3. Use the chat participant

In the Extension Development Host, open Copilot Chat and type:

```
@video-documenter /analyze C:\path\to\your-video.mp4
```

This uploads the video, extracts content, and prepares it for document generation. Then:

```
@video-documenter /generate
```

Select a document type (Tutorial, Quickstart, How-to, Concept, or Overview). The generated Markdown is saved to your workspace and opened in the editor.

**Available commands:**

| Command | Description |
|---------|-------------|
| `/analyze <path>` | Analyze a screen recording video |
| `/generate [type]` | Generate MS Learn documentation |
| `/refine <feedback>` | Refine the generated document |
| `/save [path]` | Save the generated document to a file |
| `/status` | Check processing status |

You can also right-click any video file (`.mp4`, `.avi`, `.mov`, `.mkv`, `.webm`) in the Explorer and select **"Analyze with Video Documenter"**.

### Extension settings

| Setting | Default | Description |
|---------|---------|-------------|
| `video-documenter.backendUrl` | `http://localhost:8000` | Backend server URL |
| `video-documenter.outputDirectory` | `docs` | Workspace-relative output folder |
| `video-documenter.autoOpenPreview` | `true` | Open markdown preview after generation |

> [!TIP]
> See [Manual Test Plan](docs/MANUAL-TEST-PLAN.md) for a comprehensive list of test scenarios.

---

## Running tests

```bash
cd backend

# All unit tests
pytest tests/ -v --ignore=tests/eval/

# Agent evaluation tests (requires Azure AI Foundry)
pytest tests/eval/ -v -s -m eval

# Style compliance checks (fast, no LLM cost)
pytest tests/eval/ -v -m style

# Grounding checks (fast, no LLM cost)
pytest tests/eval/ -v -m grounding

# Grader unit tests
pytest tests/eval/test_graders.py -v

# Individual agent eval
pytest tests/eval/test_eval_writer.py -v -s

# Full pipeline eval (runs all 6 agents end-to-end)
pytest tests/eval/test_eval_pipeline.py -v -s
```

### VS Code extension tests

```bash
cd vscode-extension

# Unit tests (fileDetection, progress, backendClient, conversationState)
npm test
```

---

## Project structure

```
backend/
├── src/
│   ├── agents/          # 6 MAF agents + orchestrator
│   │   ├── ingestion.py     # Video intake + metadata probing
│   │   ├── extraction.py    # Transcript, scenes, keyframes, OCR
│   │   ├── structure.py     # Map content to MS Learn template
│   │   ├── writer.py        # Generate full Markdown article
│   │   ├── editor.py        # Refine for style compliance
│   │   ├── evaluate.py      # Quality-gate scoring
│   │   └── orchestrator.py  # Pipeline coordinator
│   ├── services/        # Azure + local service clients
│   │   ├── ffmpeg_service.py
│   │   ├── whisper_service.py
│   │   ├── scene_detect_service.py
│   │   └── vision_service.py
│   ├── models/          # Pydantic data models
│   ├── prompts/         # Agent system prompts (Markdown)
│   ├── templates/       # MS Learn article templates
│   ├── api/             # FastAPI routes + WebSocket
│   ├── config.py        # Environment configuration
│   └── main.py          # Entry point (CLI + API server)
├── tests/
│   ├── eval/            # Agent evaluation tests + graders
│   ├── test_agents/     # Unit tests for each agent
│   └── test_services/   # Unit tests for service clients
├── pyproject.toml
└── .env.example
vscode-extension/        # VS Code Chat Participant (TypeScript)
docs/
├── PRD.md               # Product requirements
├── ARCHITECTURE.md       # System architecture
├── ROADMAP.md           # Implementation roadmap
└── EVAL-PLAN.md         # Evaluation strategy + grader docs
```

## Documentation

- [Product Requirements (PRD)](docs/PRD.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Implementation Roadmap](docs/ROADMAP.md)
- [Evaluation Plan](docs/EVAL-PLAN.md)

## License

TBD
