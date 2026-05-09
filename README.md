# MS Learn Video Documenter Agent

An AI-powered agent that transforms screen recording videos into structured Microsoft Learn-style documentation.

## Overview

The Video Documenter Agent processes screen recordings through a 6-agent pipeline — extracting frames, transcripts, and on-screen text — and generates publication-ready Markdown documents that conform to Microsoft Learn's voice, tone, style guide, and document structure.

### Key Features

- **Video-to-documentation pipeline**: Process screen recordings and generate MS Learn articles (Quickstart, Tutorial, How-to, Concept, Overview)
- **MS Learn compliance**: Generated content follows Microsoft's voice principles, grammar rules, and Markdown extensions
- **Iterative refinement**: Conversational feedback loop to revise specific sections
- **Dual processing modes**: Azure-native services (cloud) or open-source tools (local)
- **VS Code integration**: Use as a Chat Participant via `@video-documenter` in Copilot Chat

### Architecture

```
Video → Ingestion → Extraction → Structure → Writer → Editor → Evaluate → MS Learn Markdown
```

Built with:
- **Microsoft Agent Framework (MAF) v1.0** — multi-agent orchestration
- **Azure AI Foundry** — GPT-4o/GPT-4o-mini for vision + generation
- **Azure Video Indexer** — scene detection, OCR, keyframes, transcription (cloud mode)
- **FFmpeg + PySceneDetect + Whisper** — video processing (local mode)
- **FastAPI** — backend API
- **VS Code Chat Participant API** — primary user interface

## Documentation

- [Product Requirements (PRD)](docs/PRD.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Implementation Roadmap](docs/ROADMAP.md)

## Getting Started

> 🚧 Under development — setup instructions will be added in Phase 0.

## License

TBD
