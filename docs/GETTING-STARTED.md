# Getting started with MS Learn Video Documenter

Transform your screen recordings into professional Microsoft Learn documentation in minutes — no Azure subscription required.

## What it does

The Video Documenter Agent watches your screen recording, extracts every meaningful step (screenshots, UI actions, narration), and produces a fully-formatted Microsoft Learn article — complete with YAML metadata, numbered procedures, alt-text images, and proper MS Learn markdown extensions. You record a walkthrough; it writes the docs.

## Prerequisites

### For VSIX install (recommended)

- [ ] **GitHub Copilot subscription** (active in VS Code)
- [ ] **VS Code 1.100+** with the GitHub Copilot extension installed
- [ ] A screen recording video file (`.mp4`, `.mov`, `.mkv`, `.webm`, or `.avi`)

That's it! The VSIX bundles its own Python backend (no Python install needed), and if FFmpeg isn't found on your system the extension will offer to install it automatically via winget on first use.

### For development setup (contributors only)

All of the above, plus:

- [ ] **Python 3.11** or later
- [ ] **Node.js 24+**
- [ ] **FFmpeg 6.0** or later

## Installation

### Option 1: Install from VSIX (recommended)

1. Download the latest `.vsix` file from the [GitHub Releases](https://github.com/wsilveiranz/mslearn-video-documenter-agent/releases) page
2. In VS Code: open the Extensions panel → click the **⋯** menu → select **"Install from VSIX..."** → choose the downloaded file
3. Restart VS Code

The extension automatically starts its Python backend — no extra terminal commands needed.

### Option 2: Development setup

1. Clone the repository:
   ```powershell
   git clone https://github.com/wsilveiranz/mslearn-video-documenter-agent.git
   cd mslearn-video-documenter-agent
   ```
2. Install Python dependencies:
   ```powershell
   cd backend
   pip install -e ".[local]"
   ```
3. Install extension dependencies:
   ```powershell
   cd ..\vscode-extension
   npm install && npm run compile
   ```
4. Press **F5** in VS Code to launch the Extension Development Host

## Quick start

### Step 1: Plan (`/plan`)

Open GitHub Copilot Chat in VS Code and type:

```
@video-documenter /plan
```

The agent guides you through selecting a video file, choosing a document type (tutorial, quickstart, etc.), and filling in metadata (title, author, ms.service). It then analyzes the video — extracting scenes, transcript, and screenshots.

### Step 2: Generate (`/generate`)

Once planning and analysis are complete, generate the document:

```
@video-documenter /generate
```

The agent produces a full MS Learn article based on everything collected in the `/plan` step.

### Optional: Polish and save

After generation, you can refine the output:

```
@video-documenter /polish
```
Runs quality checks for style, branding, metadata, and formatting.

```
@video-documenter /save
```
Writes the final `.md` file and extracted screenshots to your output directory.

### Alternative: manual analyze + generate

If you prefer to skip the guided `/plan` flow:

1. `@video-documenter /analyze C:\Videos\deploy-webapp.mp4` — analyze a video directly
2. `@video-documenter /generate tutorial` — generate with a specific document type

## Available commands

| Command | What it does |
|---------|-------------|
| `/plan` | Guided setup — select video, choose doc type, fill metadata, analyze |
| `/analyze <path>` | Analyze a screen recording video |
| `/generate [type]` | Generate documentation (tutorial, quickstart, how-to, concept, overview) |
| `/edit <feedback>` | Refine a specific section with your feedback |
| `/polish` | Run quality checks on style, metadata, SEO, and formatting |
| `/save [path]` | Save the document to a file (defaults to `docs/` in your workspace) |
| `/status` | Check the current processing status |

## Document types

| Type | Best for | Example H1 |
|------|----------|-----------|
| **Quickstart** | "Get running in 5 minutes" guides | `Quickstart: Deploy a web app` |
| **Tutorial** | Step-by-step learning paths | `Tutorial: Build a chatbot` |
| **How-to** | Specific task procedures | `Configure SSO for your app` |
| **Concept** | Explaining ideas or architecture | `What is managed identity?` |
| **Overview** | Product or feature introductions | `What is Azure Functions?` |

## Tips for best results

- **Keep videos under 10 minutes** — shorter recordings produce tighter, more focused docs
- **Narrate your walkthrough** — the transcript is a primary source for the written steps, so clear audio matters
- **Make UI elements visible** — avoid small windows or obscured menus; full-screen works best
- **Use `/plan` for the guided experience** — it asks the right questions and picks sensible defaults
- **Iterate with `/edit`** — after generation, refine specific sections (e.g., `@video-documenter /edit make step 3 clearer`)
- **Always `/polish` before sharing** — it catches style issues, missing metadata, and formatting problems

## Output

After saving, you'll find:

- A `.md` file in your workspace's `docs/` folder (or the path you specified) with full MS Learn formatting and YAML frontmatter
- A `media/` subfolder containing extracted screenshots referenced in the article

VS Code automatically opens a Markdown preview so you can review the result side-by-side with the source.

## Configuration

The extension works out of the box with these defaults (no changes needed for most users):

| Setting | Default | Description |
|---------|---------|-------------|
| `video-documenter.processingMode` | `local` | Uses local FFmpeg + Whisper (no Azure needed) |
| `video-documenter.outputDirectory` | `docs` | Where saved files go (workspace-relative) |
| `video-documenter.autoOpenPreview` | `true` | Opens Markdown preview after save |
| `video-documenter.useCopilotModels` | `true` | Routes AI calls through your Copilot subscription |
| `video-documenter.autoStartBackend` | `true` | Starts the Python backend automatically |

## Going further: cloud mode

Local mode works great for getting started, but if you have an Azure subscription you can unlock higher-quality extraction by switching to **cloud mode**. Azure Video Indexer and Azure AI Speech produce richer transcripts, better scene detection, and more accurate OCR — which means better documentation output.

### What you need

- An Azure subscription with these services provisioned:
  - **Azure AI Foundry** project (GPT-4o and GPT-4o-mini deployments)
  - **Azure Blob Storage** account
  - **Azure AI Speech** service
  - **Azure Video Indexer** account

> [!TIP]
> You can provision all of these with a single command: `azd up` from the repository root. See [Azure Setup Guide](AZURE-SETUP.md) for details.

### Configure the extension for cloud mode

In VS Code Settings (search "video-documenter"), update:

| Setting | Value |
|---------|-------|
| `video-documenter.processingMode` | `cloud` |
| `video-documenter.foundryProjectEndpoint` | Your AI Foundry endpoint (e.g., `https://your-project.services.ai.azure.com`) |
| `video-documenter.blobAccountUrl` | Your Blob Storage URL (e.g., `https://stvideodocumenter.blob.core.windows.net`) |
| `video-documenter.speechServiceEndpoint` | Your Speech service URL |
| `video-documenter.videoIndexerAccountId` | Your Video Indexer account ID |
| `video-documenter.videoIndexerResourceId` | Your Video Indexer ARM resource ID |

You'll also need to sign in with Azure CLI (`az login`) — the extension uses `DefaultAzureCredential`, so no API keys are needed.

### What improves with cloud mode

| Dimension | Local | Cloud |
|-----------|-------|-------|
| Transcription | Whisper (base model) | Azure AI Speech (fast, with diarization) |
| Scene detection | PySceneDetect | Azure Video Indexer (semantic scenes) |
| OCR | GPT-4o vision | Video Indexer (frame-level, bounding boxes) |
| Keyframes | Adaptive threshold | Video Indexer (shot-aware, stable frames) |

The document generation pipeline (Structure → Writer → Editor → Evaluate) works the same in both modes — cloud mode just feeds it richer source data.

## Need help?

- Run `@video-documenter /status` to check if the backend is running and healthy
- See the [README](../README.md) for full documentation and architecture details
- [File an issue](https://github.com/wsilveiranz/mslearn-video-documenter-agent/issues) on GitHub if something isn't working
