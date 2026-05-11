# Implementation Roadmap

## MS Learn Video Documenter Agent

**Version:** 1.0  
**Status:** Draft  
**Last Updated:** 2026-05-09

---

## Roadmap Overview

The implementation is divided into **6 phases**, each delivering a usable increment. The agent becomes functional after Phase 2, with progressively richer capabilities in later phases.

```
Phase 0: Foundation ──▶ Phase 1: Core Pipeline ──▶ Phase 2: VS Code Integration
    │                       │                           │
    ▼                       ▼                           ▼
  Project setup          Video → Draft doc          Chat participant
  Azure provisioning     Local processing           End-to-end flow
  MAF scaffolding        Basic generation           File input/output

Phase 3: Tool & Extension ──▶ Phase 4: Cloud & Quality ──▶ Phase 5: Polish & Extensibility
    │                             │                             │
    ▼                             ▼                             ▼
  MCP client + grounding       Azure Video Indexer           Screenshot annotations
  Companion extensions         Azure Speech                  Multi-source video input
  Learn Authoring Pack         Evaluate Agent                Evaluation dashboard
  Content Mentor workflow      Iterative refinement          MCP server (future)
```

---

## Phase 0: Project Foundation

**Goal:** Set up the project structure, dependencies, Azure resources, and MAF scaffolding.

### Tasks

#### 0.1 Project Initialization
- Initialize Python project with `pyproject.toml` (using `uv` or `pip`)
- Set up project directory structure (see Architecture doc §5.1)
- Initialize git repository with `.gitignore`, `README.md`
- Configure linting (`ruff`), formatting (`black`), type checking (`pyright`)

#### 0.2 Azure Resource Provisioning
- Create or configure Azure AI Foundry project
  - Deploy GPT-4o model
  - Deploy GPT-4o-mini model
  - Note endpoints and API keys
- Create Azure Blob Storage account + container (`video-documenter`)
- Create Azure AI Speech resource
- Create Azure AI Video Indexer account (link to existing AI Services)
- Store all credentials in `.env` file (gitignored)

#### 0.3 MAF Scaffolding
- Install Microsoft Agent Framework: `pip install agent-framework`
- Create base agent classes for each pipeline agent
- Set up orchestrator with sequential pipeline graph
- Implement basic configuration loading (`config.py`)
- Verify MAF runs with a simple echo agent

#### 0.4 VS Code Extension Scaffold
- Initialize VS Code extension project with TypeScript
- Register chat participant in `package.json`
- Implement minimal handler that echoes user input
- Verify extension loads and `@video-documenter` responds in Copilot Chat

### Deliverable
- Working project skeleton with all dependencies
- Azure resources provisioned and accessible
- MAF orchestrator running with placeholder agents
- VS Code extension responding to `@video-documenter` mentions

---

## Phase 1: Core Video-to-Document Pipeline (Local Mode)

**Goal:** Build the end-to-end pipeline from video file to draft Markdown document using local/open-source tools only. This phase delivers core value without Azure service dependencies (except AI Foundry for GPT-4o).

### Tasks

#### 1.1 Video Ingestion Agent
- Accept local file paths (.mp4, .mov, .mkv, .webm, .avi)
- Validate file format and size (<2 GB)
- Extract basic video metadata (duration, resolution, fps)
- Copy/stage video to working directory

#### 1.2 Frame Extraction Service (FFmpeg)
- Implement FFmpeg wrapper for:
  - Audio extraction to WAV (16kHz mono for speech APIs)
  - Frame extraction at scene changes (`select=gt(scene,0.4)`)
  - Fallback: extract frames at fixed interval (1 per 5 seconds)
- Save extracted frames as numbered PNGs
- Save audio as WAV file

#### 1.3 Scene Detection (PySceneDetect)
- Integrate PySceneDetect with `AdaptiveDetector`
- Detect scene boundaries with timestamps
- Map scene boundaries to extracted keyframes
- Output: list of scenes with start/end times and keyframe references

#### 1.4 Transcription Service (Whisper)
- Integrate OpenAI Whisper (local model, `base` or `small`)
- Transcribe extracted audio to timestamped segments
- Output: list of transcript segments with start/end times and text

#### 1.5 Vision Analysis Service (GPT-4o)
- For each keyframe, call GPT-4o Vision API via Azure AI Foundry
- System prompt: "Describe the UI state shown in this screenshot. Identify: what application/page is visible, what UI elements are highlighted or active, what action the user appears to be performing."
- Output: UI state description per keyframe

#### 1.6 Extraction Agent (Combines 1.2–1.5)
- Orchestrate: FFmpeg → PySceneDetect → Whisper → GPT-4o Vision
- Produce unified `ExtractionResult` with all data correlated by timestamp
- Handle errors in individual components gracefully

#### 1.7 MS Learn Templates
- Embed all 5 MS Learn article templates (from `MicrosoftDocs/content-templates`)
- Include template selection logic based on user input
- Define YAML frontmatter generation with required fields

#### 1.8 Structure Agent
- Implement step identification from scenes + transcript
- Cluster adjacent scenes into logical documentation steps
- Map steps to selected template structure
- Select best keyframe per step (most stable/representative frame)
- Generate document outline

#### 1.9 Writer Agent
- Implement GPT-4o-based content generation with MS Learn system prompt
- Generate full Markdown from outline + extraction data
- Include YAML frontmatter, section headings, numbered steps, screenshots
- Use MS Learn Markdown extensions (alerts, image syntax)

#### 1.10 Editor Agent
- Implement single-pass editing for style compliance
- Fix common issues: heading case, contractions, step formatting
- Validate frontmatter completeness

#### 1.11 Pipeline Integration
- Wire all agents through MAF orchestrator
- Implement sequential pipeline: Ingestion → Extraction → Structure → Writer → Editor
- Add progress callbacks for each stage
- Test end-to-end with a sample screen recording

### Deliverable
- Complete local pipeline: video file → MS Learn Markdown document
- Works with only Azure AI Foundry (GPT-4o) as cloud dependency
- Outputs: `.md` file + `media/` folder with keyframe screenshots
- Can be run from command line: `python -m src.main process video.mp4`

---

## Phase 2: VS Code Chat Participant Integration

**Goal:** Connect the pipeline to the VS Code Chat Participant interface, enabling conversational interaction.

### Tasks

#### 2.1 Backend API (FastAPI)
- Implement FastAPI application with endpoints:
  - `POST /api/v1/videos/ingest` — upload video, return video_id
  - `GET /api/v1/videos/{id}/status` — processing status (step-based)
  - `POST /api/v1/documents/generate` — trigger generation
  - `GET /api/v1/documents/{id}` — retrieve generated document
  - `POST /api/v1/documents/{id}/refine` — iterative refinement
  - `POST /api/v1/classify-intent` — classify user message intent (save/refine/general)
- Add WebSocket endpoint for step-based progress streaming (fire-and-forget, never blocks pipeline)
- Add CORS configuration for VS Code extension

#### 2.2 Extension → Backend Communication
- Implement `BackendClient` in TypeScript (HTTP + WebSocket)
- Handle video file upload from extension to backend
- Implement progress streaming from WebSocket to chat stream

#### 2.3 Chat Participant Handler
- Implement full chat handler with conversation flow:
  1. User provides video → extension uploads → shows progress
  2. Extraction complete → ask user for document type
  3. User selects type → generate document → stream preview
  4. User can request refinements → iterate
- Implement file path parsing from chat prompt
- Implement file picker dialog as fallback (no path provided)
- Implement context menu: right-click `.mp4` → "Analyze with Video Documenter"

#### 2.4 Output Integration
- Save generated files to workspace directory
- Open generated Markdown in VS Code editor
- Show document preview (if Learn Preview extension installed)

#### 2.5 Chat Commands
- `/analyze` — Start video analysis
- `/generate` — Generate document (after analysis)
- `/refine` — Enter refinement mode for current document
- `/save` — Save generated document to a specific location
- `/status` — Check processing status

### Deliverable
- Fully functional VS Code Chat Participant
- Conversational flow: upload → analyze → choose type → generate → refine
- Files saved to workspace with proper structure

#### 2.6 Copilot LM Proxy (local mode) ✅ **DONE**
- Extension hosts an OpenAI-compatible HTTP proxy (`lmProxyServer.ts`) that translates to `vscode.lm` API calls
- Backend `CopilotProxyChatClient` routes LLM requests through the proxy in local mode
- Orchestrator `create_llm_client()` selects Copilot or Foundry client based on configuration
- Handshake endpoint `POST /api/v1/config/lm-proxy` allows the extension to register the proxy URL at startup
- Configuration: `copilot_proxy_url`, `copilot_proxy_model`, `use_copilot_proxy` (computed), `useCopilotModels` (extension setting)
- **Result:** Local development works with zero Azure credentials — only a GitHub Copilot subscription is needed

---

## Phase 3: Tool & Extension Integration

**Goal:** Integrate Microsoft Learn MCP Server and companion VS Code extensions to enhance agent output quality, documentation grounding, and author workflow.

### Tasks

#### 3.1 MCP Client Infrastructure
- Create reusable MCP client service (`backend/src/services/mcp_client.py`)
- Implement Streamable HTTP transport client (for hosted MCP servers like Microsoft Learn)
- Implement stdio transport support (for local development with `MicrosoftDocs/mcp` repo)
- Build generic tool-calling abstraction: `call_tool(server, tool_name, params) → result`
- Add response caching (TTL-based) to avoid redundant MCP calls
- Add rate limiting and structured logging (`structlog`)
- Add MCP configuration to `config.py` (endpoint URL, cache TTL, enabled flag)

#### 3.2 Microsoft Learn MCP Server Integration
- Connect to Microsoft Learn MCP Server at `https://learn.microsoft.com/api/mcp`
- Register three MCP tools as MAF tools available to agents:
  - `microsoft_docs_search` — search MS Learn documentation index
  - `microsoft_docs_fetch` — fetch full content of a specific MS Learn article
  - `microsoft_code_sample_search` — search for official code samples
- Integration points per agent:
  - **Structure Agent**: Search for related published articles when creating outline (use as reference patterns)
  - **Writer Agent**: Fetch published article examples for voice/tone and formatting grounding
  - **Editor Agent**: Reference published docs for style consistency checks
- Implement query construction from agent context (document type, topic, Azure service)
- Handle graceful degradation when MCP server is unavailable (log warning, continue without grounding)
- Implement token budget management for fetched doc content

#### 3.3 Agent System Prompt Updates
- Update `structure_system.md`, `writer_system.md`, and `editor_system.md` with MCP tool-use instructions
- Add tool-use examples showing how to search and fetch MS Learn docs during processing
- Add fallback instructions for when doc search returns no results
- Include token budget guidance for fetched content

#### 3.4 Content Mentor Companion Workflow
- Create `docs/CONTENT-MENTOR-WORKFLOW.md` documenting the end-to-end workflow:
  1. Generate docs with Video Documenter
  2. Open in VS Code
  3. Use `@content-mentor` chat participant for AI review
  4. Apply suggestions
  5. Final validation
- Add Content Mentor extension detection in VS Code extension (`msft-content.content-mentor`)
- Show contextual tips when Content Mentor is installed (Microsoft-internal only — don't recommend to external users)

#### 3.5 Learn Authoring Assistant Companion Workflow
- Document integration workflow for Microsoft Learn Authoring Assistant (`docsmsft.learn-authoring-assistant`)
- Add extension detection in VS Code extension
- Show `/suggestEdits` tip when installed (Microsoft-internal only)
- Document how it differs from Content Mentor (editorial quality vs. lifecycle management)

#### 3.6 Learn Authoring Pack Integration
- Register `docsmsft.docs-authoring-pack` as `extensionDependencies` in `package.json`
- Implement Learn Preview integration (auto-open preview side-by-side after generation)
- Use Learn Article Templates as validation reference for Evaluate Agent
- Add `markdownlint` configuration matching MS Learn rules

#### 3.7 Extension Companion Framework
- Create `vscode-extension/src/utils/companions.ts`
- Detect installed companion extensions (Content Mentor, Authoring Assistant, Authoring Pack)
- Build post-generation guidance flow based on installed companions
- Show "recommended extensions" prompt on first use (public extensions only)

#### 3.8 Documentation Updates
- Update ARCHITECTURE.md with MCP client architecture
- Update PRD.md with new tool integrations
- Create CONTENT-MENTOR-WORKFLOW.md

### Deliverable
- MCP client connected to Microsoft Learn MCP Server with search, fetch, and code sample tools
- Agents enhanced with live MS Learn documentation grounding during processing
- Companion extension framework detecting and leveraging Content Mentor, Authoring Assistant, and Authoring Pack
- Post-generation validation workflow documented for Microsoft-internal tools
- Learn Preview integration for rendered document previews

---

## Phase 4: Cloud Services & Quality

**Goal:** Add Azure-native video processing for higher quality results, implement the evaluation agent, and enable iterative refinement.

### Tasks

#### 4.1 Azure Video Indexer Integration
- Implement Video Indexer client:
  - Authentication (account access token)
  - Upload video for indexing
  - Poll for index completion
  - Retrieve insights JSON (transcript, scenes, shots, keyframes, OCR)
  - Download keyframe thumbnail images
- Map Video Indexer output to `ExtractionResult` schema

#### 4.2 Azure Speech Integration
- Implement Fast Transcription API client
- Support diarization (speaker attribution)
- Add phrase lists for domain-specific vocabulary

#### 4.3 Azure Blob Storage Integration
- Implement Blob upload/download client
- Generate SAS URLs for Video Indexer
- Manage temporary storage lifecycle (auto-cleanup)

#### 4.4 Processing Mode Selection
- Implement cloud vs. local mode toggle in configuration
- Auto-detect available services and fall back gracefully
- Cloud mode: Video Indexer + Speech + Blob
- Local mode: FFmpeg + PySceneDetect + Whisper

#### 4.5 Evaluate Agent
- Implement quality scoring:
  - Completeness: compare steps in document vs. scenes in video
  - Accuracy: cross-reference generated text with transcript + OCR
  - Style compliance: check against MS Learn rules (heading case, contractions, etc.)
  - Readability: sentence length, scannability, structure
- Generate evaluation report with scores and suggestions
- Gate output on minimum quality threshold (≥0.7 overall)

#### 4.6 Iterative Refinement
- Implement section-level editing via chat
- Track document state across refinement cycles
- Apply user feedback to specific sections without full regeneration
- Maintain conversation context for multi-turn refinement

### Deliverable
- Azure-native video processing (higher quality than local mode)
- Quality evaluation with scoring and suggestions
- Iterative refinement via conversational feedback
- Cloud + local mode parity

---

## Phase 5: Polish & Extensibility

**Goal:** Add screenshot annotations, multi-source video input, deployment automation, and prepare for future extensibility.

### Tasks

#### 5.1 Screenshot Annotation Engine
- Implement image annotation using Pillow/OpenCV:
  - Step number badges (red circle with white number)
  - UI element highlighting (red rectangles around relevant areas)
  - Captions below images
- Let GPT-4o Vision suggest which UI elements to highlight
- Generate annotated versions alongside originals

#### 5.2 Multi-Source Video Input
- YouTube URL support via yt-dlp download
- Microsoft Stream URL support
- Azure Blob Storage direct URL support
- Source auto-detection from URL patterns

#### 5.3 Docker Containerization
- Create production Dockerfile (Python + FFmpeg + dependencies)
- Create `docker-compose.yml` for local development
- Test container on Azure Container Apps
- Document deployment process

#### 5.4 Azure Deployment
- Create Azure Container Apps deployment config
- Set up Azure Managed Identity (no API keys in production)
- Configure environment variables from Azure Key Vault
- Implement health check endpoint
- Document Azure deployment runbook

#### 5.5 Observability
- Add OpenTelemetry tracing (MAF built-in)
- Add structured logging
- Track processing metrics (duration, token usage, quality scores)
- Optional: Application Insights integration

#### 5.6 Testing & Documentation
- Unit tests for all agents and services
- Integration tests with sample videos
- End-to-end tests for full pipeline
- User documentation and getting started guide
- API documentation (auto-generated from FastAPI)

#### 5.7 Extensibility Preparation
- Design MCP server interface for future GitHub Copilot integration
- Document extension points for additional document types
- Prepare for web UI frontend (verify API completeness)

### Deliverable
- Production-ready containerized deployment
- Annotated screenshots in generated documents
- Multi-source video support
- Full test coverage and documentation
- Ready for web UI or MCP server extension

---

## Phase Summary

| Phase | Key Milestone | Primary Dependencies |
|-------|--------------|---------------------|
| **Phase 0** | Project skeleton + Azure setup | Azure subscription, MAF, VS Code Extension API |
| **Phase 1** | Local video → Markdown pipeline | FFmpeg, PySceneDetect, Whisper, GPT-4o |
| **Phase 2** | VS Code Chat Participant working | FastAPI, TypeScript, WebSocket |
| **Phase 3** | MCP grounding + companion extensions | Microsoft Learn MCP Server, Content Mentor, Learn Authoring Pack |
| **Phase 4** | Cloud processing + quality gates | Azure Video Indexer, Azure Speech, Blob Storage |
| **Phase 5** | Production deployment + polish | Docker, Azure Container Apps, Pillow |

---

## Technical Risks and Mitigations

| Risk | Phase | Mitigation |
|------|-------|------------|
| MAF v1.0 is new; limited community examples | Phase 0-1 | Start with simple sequential pipeline; reference Contoso Creative Writer pattern |
| PySceneDetect may not detect subtle UI transitions | Phase 1 | Supplement with fixed-interval frame extraction; tune AdaptiveDetector threshold |
| GPT-4o Vision may not identify specific UI elements reliably | Phase 1 | Iterate on system prompt; combine with OCR text for grounding |
| Microsoft Learn MCP Server may be unavailable or rate-limited | Phase 3 | Implement caching, graceful degradation; agents continue without grounding |
| Content Mentor and Authoring Assistant are Microsoft-internal only | Phase 3 | Treat as companion workflow only; don't create hard dependencies; detect presence conditionally |
| Video Indexer shot types (Wide/Medium/Close-up) may not apply to screen recordings | Phase 4 | Ignore shot type tags; use scene/keyframe data only |
| VS Code Chat Participant has no native video upload | Phase 2 | Implement file picker + context menu + path parsing (3 input methods) |
| Evaluate Agent scoring may be unreliable (Doc-Kit has this issue too) | Phase 4 | Use simple rule-based checks alongside LLM evaluation; set conservative thresholds |

---

## Reference Implementations

| Project | Relevance | URL |
|---------|-----------|-----|
| **Contoso Creative Writer** | Multi-agent writing pipeline on Azure (Research → Write → Edit) | `Azure-Samples/contoso-creative-writer` |
| **Doc-Kit** (internal) | 4-agent doc pipeline (Plan → Author → Evaluate → Research) | `microsoft-foundry/doc-kit` |
| **VS Code Chat Sample** | Chat Participant reference implementation | `microsoft/vscode-extension-samples:chat-sample` |
| **Video Indexer Samples** | Python/C#/Java samples for Video Indexer API | `Azure-Samples/azure-video-indexer-samples` |
| **MS Learn Content Templates** | Official article templates | `MicrosoftDocs/content-templates` |
| **MS Learn Style Guide** | Voice, tone, and formatting rules | `learn.microsoft.com/contribute/style-quick-start` |
| **Microsoft Learn MCP Server** | MCP server for documentation grounding | `MicrosoftDocs/mcp` + `https://learn.microsoft.com/api/mcp` |
| **Microsoft MCP Catalog** | Azure, Fabric, DevOps MCP servers (reference) | `microsoft/mcp` |
