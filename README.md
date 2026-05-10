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
- **Azure AI Foundry** — GPT-4o/GPT-4o-mini for vision + generation (cloud mode)
- **GitHub Copilot models** — LLM access via VS Code Language Model API (local mode)
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
| Azure CLI | Latest | Required for cloud mode (`DefaultAzureCredential`) |
| Azure AI Foundry project | — | Cloud mode: GPT-4o / GPT-4o-mini deployments |
| GitHub Copilot subscription | — | Local mode: LLM access without Azure (optional) |
| Node.js | 24+ | Only for VS Code extension development |

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

Edit `.env` for your chosen mode:

### Local mode settings

Local mode uses FFmpeg + Whisper for video processing and either **GitHub Copilot** or **Azure AI Foundry** for LLM calls.

**Option A — Local + Copilot** (simplest, no Azure needed):

```dotenv
PROCESSING_MODE=local

# Video processing
WHISPER_MODEL=base
FFMPEG_PATH=ffmpeg

# LLM: Copilot models via VS Code (auto-configured by extension)
# No FOUNDRY_* settings needed — leave them empty or remove them.
# The extension starts a Copilot LM Proxy and notifies the backend.
# To set manually: COPILOT_PROXY_URL=http://localhost:3001

OUTPUT_DIRECTORY=./output
```

> [!TIP]
> This is the fastest way to get started. You only need a GitHub Copilot subscription and VS Code — no Azure login, no API keys.

**Option B — Local + Azure Foundry**:

```dotenv
PROCESSING_MODE=local

# Video processing
WHISPER_MODEL=base
FFMPEG_PATH=ffmpeg

# LLM: Azure AI Foundry
FOUNDRY_PROJECT_ENDPOINT=https://your-project.services.ai.azure.com
FOUNDRY_MODEL=gpt-4o
FOUNDRY_MODEL_MINI=gpt-4o-mini

OUTPUT_DIRECTORY=./output
```

Requires `az login` for authentication.

### Cloud mode settings

Cloud mode uses Azure Video Indexer, Azure AI Speech, and Azure AI Foundry for the full pipeline.

```dotenv
PROCESSING_MODE=cloud

# LLM: Azure AI Foundry
FOUNDRY_PROJECT_ENDPOINT=https://your-project.services.ai.azure.com
FOUNDRY_MODEL=gpt-4o
FOUNDRY_MODEL_MINI=gpt-4o-mini

# Azure Blob Storage
BLOB_ACCOUNT_URL=https://stvideodocumenter.blob.core.windows.net
BLOB_CONTAINER_NAME=video-documenter

# Azure AI Speech
SPEECH_SERVICE_ENDPOINT=https://speech-video-documenter.cognitiveservices.azure.com
SPEECH_SERVICE_REGION=eastus

# Azure Video Indexer
VIDEO_INDEXER_ACCOUNT_ID=<your-account-id>
VIDEO_INDEXER_RESOURCE_ID=<your-arm-resource-id>
VIDEO_INDEXER_LOCATION=trial

OUTPUT_DIRECTORY=./output
```

Requires `az login` for authentication.

> [!IMPORTANT]
> Cloud mode uses `DefaultAzureCredential` — no API keys or connection strings needed. Your Azure CLI credential is used locally; Managed Identity is used in production.

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
| `video-documenter.useCopilotModels` | `true` | Route LLM calls through Copilot in local mode |
| `video-documenter.lmProxyPort` | `0` (auto) | Port for the LM Proxy server |

> [!TIP]
> See [Manual Test Plan](docs/MANUAL-TEST-PLAN.md) for a comprehensive list of test scenarios.

---

## Testing local mode with Copilot (no Azure credentials)

In local mode, the extension can route all LLM calls through your **GitHub Copilot subscription** instead of requiring Azure AI Foundry credentials. This means you only need FFmpeg, Python, and a Copilot subscription to run the full pipeline.

### Prerequisites

| Requirement | Notes |
|-------------|-------|
| GitHub Copilot subscription | Active, signed in to VS Code |
| VS Code with GitHub Copilot extension | Provides the language models |
| Python 3.11+ | Backend runtime |
| FFmpeg 6.0+ | Video processing |
| Node.js 24+ | Extension development |

> [!NOTE]
> No Azure subscription, Azure CLI login, or `FOUNDRY_PROJECT_ENDPOINT` needed.

### Step 1: Configure the backend for local + Copilot mode

```bash
cd backend
cp .env.example .env
```

Edit `.env` — set these values only (you can ignore all Azure settings):

```dotenv
PROCESSING_MODE=local
WHISPER_MODEL=base
FFMPEG_PATH=ffmpeg
OUTPUT_DIRECTORY=./output

# Copilot proxy URL — auto-configured by the extension on startup,
# but you can set it manually if you start the backend first:
# COPILOT_PROXY_URL=http://localhost:3001
```

Install dependencies:

```bash
pip install -e ".[local,dev]"
```

### Step 2: Start the backend

```bash
cd backend
python -m src.main
```

Verify it's running:

```bash
curl http://localhost:8000/api/v1/health
```

### Step 3: Launch the extension (with LM Proxy)

```bash
cd vscode-extension
npm install
npm run compile
```

Press **F5** in VS Code to launch the Extension Development Host.

On activation, the extension:
1. Starts an **LM Proxy server** on localhost (check the output panel for the port)
2. Notifies the backend at `POST /api/v1/config/lm-proxy` with the proxy URL
3. The backend now routes LLM calls through Copilot models automatically

You should see in the extension output:
```
[video-documenter] LM Proxy started on port 3001
[video-documenter] Extension activated successfully
```

### Step 4: Verify the LM Proxy is working

Check the proxy health endpoint (port may vary):

```bash
curl http://localhost:3001/health
```

Expected response:
```json
{
  "status": "ok",
  "models": ["copilot-gpt-4o", ...]
}
```

### Step 5: Process a video

In the Extension Development Host's Copilot Chat:

```
@video-documenter /analyze C:\path\to\your-video.mp4
```

Wait for analysis to complete, then:

```
@video-documenter /generate tutorial
```

The pipeline runs entirely through Copilot models — no Azure calls.

### Troubleshooting

| Problem | Solution |
|---------|----------|
| `LM Proxy failed to start` | Ensure GitHub Copilot is installed and signed in |
| `No Copilot models available` (503) | Check your Copilot subscription is active in VS Code |
| `CopilotProxyUnreachableError` | Extension must be running; check the proxy port in output |
| Backend ignores proxy | Verify `PROCESSING_MODE=local` in `.env`; check backend logs for `pipeline.using_copilot_proxy` |
| Rate limit errors (429) | Copilot has per-user rate limits; wait and retry, or reduce keyframe count |

### How it works

```
VS Code Extension                          Python Backend
┌────────────────────────┐                 ┌──────────────────────┐
│ LM Proxy Server        │ ◀── HTTP ────  │ CopilotProxyChatClient│
│ localhost:3001         │                 │                      │
│  └─ vscode.lm API     │                 │ Orchestrator checks: │
│     └─ Copilot Models  │                 │  local + proxy_url?  │
│       (GPT-4o, etc.)  │                 │   → Copilot client   │
└────────────────────────┘                 └──────────────────────┘
```

- The extension's LM Proxy translates OpenAI-format HTTP requests into `vscode.lm.sendRequest()` calls
- Supports text and vision (image) messages — keyframe analysis works through Copilot's GPT-4o
- The backend's `CopilotProxyChatClient` is duck-type compatible with `FoundryChatClient`, so all agents work transparently

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
