# MS Learn Video Documenter

An AI-powered VS Code chat participant that transforms screen recording videos into structured Microsoft Learn-style documentation.

## Overview

The Video Documenter agent processes screen recordings through a multi-agent pipeline — extracting frames, transcripts, and on-screen text — and generates publication-ready Markdown documents that follow Microsoft Learn's voice, tone, style guide, and document structure.

## Getting started

1. Install the extension from the VSIX file
2. Open VS Code and wait for the extension to activate (it starts automatically)
3. The extension checks for prerequisites (Python 3.10+, FFmpeg) and installs them if needed
4. Open Copilot Chat and type `@video-documenter` to start

### Prerequisites

The extension auto-installs these on first activation (Windows only):

- **Python 3.10+** — installed via `winget` if missing
- **FFmpeg** — installed via `winget` if missing
- **Backend dependencies** — installed automatically into a virtual environment

### Processing modes

| Mode | Video analysis | Transcription | Best for |
|------|---------------|---------------|----------|
| **Local** (default) | FFmpeg + PySceneDetect | OpenAI Whisper | Development, cost-sensitive |
| **Cloud** | Azure Video Indexer | Azure AI Speech | Production, highest quality |

Configure the mode in **Settings > Video Documenter > Processing Mode**.

## Commands

Use these commands in Copilot Chat by typing `@video-documenter /command`:

### `/plan` — Plan your documentation

Interactive wizard that guides you through the full documentation setup:

1. **Select a video** — paste a file path or use the file picker
2. **Choose document type** — Quickstart, Tutorial, How-to, Concept, or Overview
3. **Select Azure service** — pick from common services or enter a custom one
4. **Set author metadata** — GitHub username and Microsoft alias
5. **Confirm and analyze** — the video is analyzed automatically

This is the recommended starting point for new documents.

```
@video-documenter /plan
@video-documenter /plan Create a tutorial for Azure Functions
```

### `/analyze` — Analyze a video

Processes a video file to extract scenes, keyframes, transcript, and on-screen text. This step must complete before generating documentation.

```
@video-documenter /analyze C:\videos\demo.mp4
@video-documenter /analyze
```

If no file path is provided, a file picker dialog opens. Supported formats: `.mp4`, `.avi`, `.mov`, `.mkv`, `.webm`.

### `/generate` — Generate documentation

Creates a full Microsoft Learn article from the analyzed video. Requires a video to be analyzed first (via `/plan` or `/analyze`).

```
@video-documenter /generate
@video-documenter /generate tutorial
@video-documenter /generate quickstart
```

You can specify the document type directly, or the agent will prompt you to choose. Available types:

| Type | H1 format | Example |
|------|-----------|---------|
| **Quickstart** | `Quickstart: <verb> <noun>` | Quickstart: Deploy a web app |
| **Tutorial** | `Tutorial: <verb> <noun>` | Tutorial: Build a chatbot |
| **How-to** | `<verb> <noun>` | Configure authentication |
| **Concept** | `What is <noun>?` | What is Azure Functions? |
| **Overview** | `What is <product>?` | What is Azure App Service? |

### `/refine` — Refine documentation

Iteratively improve a section of the generated document. Provide feedback on what to change, and the editor agent rewrites the content while maintaining MS Learn style compliance.

```
@video-documenter /refine Make the introduction more concise
@video-documenter /refine Add more detail to step 3
@video-documenter /refine The code sample in step 5 is missing error handling
```

### `/save` — Save the document

Save the generated document to a specific location on disk.

```
@video-documenter /save
@video-documenter /save C:\docs\my-tutorial.md
@video-documenter /save docs/output/
```

If no path is provided, saves to the configured output directory (default: `docs/` in your workspace).

### `/status` — Check processing status

View the current state of video processing, including which pipeline stage is active and progress details.

```
@video-documenter /status
```

## Context menu

Right-click any video file (`.mp4`, `.avi`, `.mov`, `.mkv`, `.webm`) in the Explorer sidebar and select **Analyze with Video Documenter** to start processing it directly.

## Settings

Configure the extension in **File > Preferences > Settings** and search for "Video Documenter":

| Setting | Default | Description |
|---------|---------|-------------|
| `processingMode` | `local` | Processing mode: `local` or `cloud` |
| `backendUrl` | `http://localhost:8000` | Backend server URL |
| `autoStartBackend` | `true` | Auto-start the Python backend on activation |
| `autoOpenPreview` | `true` | Open markdown preview after generating |
| `outputDirectory` | `docs` | Workspace-relative output directory |
| `useCopilotModels` | `true` | Route LLM calls through Copilot (local mode) |
| `author` | | Default GitHub username for documents |
| `msAuthor` | | Default Microsoft alias for documents |

### Cloud mode settings

These apply when `processingMode` is set to `cloud`:

| Setting | Description |
|---------|-------------|
| `foundryProjectEndpoint` | Azure AI Foundry project endpoint |
| `foundryModel` | Foundry model deployment (default: `gpt-4o`) |
| `foundryModelMini` | Smaller model for simpler tasks (default: `gpt-4o-mini`) |
| `blobAccountUrl` | Azure Blob Storage account URL |
| `speechServiceEndpoint` | Azure AI Speech endpoint |
| `videoIndexerAccountId` | Azure Video Indexer account ID |

### Local mode settings

These apply when `processingMode` is set to `local`:

| Setting | Description |
|---------|-------------|
| `whisperModel` | Whisper model size: `tiny`, `base`, `small`, `medium`, `large` |
| `ffmpegPath` | Path to FFmpeg binary (default: uses PATH) |

## Typical workflow

```
1. @video-documenter /plan              → Interactive setup wizard
2.    (video is analyzed automatically)
3. @video-documenter /generate           → Generate the article
4. @video-documenter /refine <feedback>   → Iterate on content
5. @video-documenter /save               → Save to disk
```

## Troubleshooting

- **Backend won't start**: Check the "Video Documenter Backend" output channel for errors
- **Prerequisites failed**: Check the "Video Documenter Prerequisites" output channel
- **Cloud mode errors**: Verify Azure settings are configured in Settings (`Ctrl+,` → search "video-documenter")
- **Slow transcription**: Try a smaller Whisper model (e.g., `tiny` or `base`) in local mode settings
