# Product Requirements Document (PRD)

## MS Learn Video Documenter Agent

**Version:** 1.0  
**Status:** Draft  
**Last Updated:** 2026-05-09

---

## 1. Executive Summary

The **MS Learn Video Documenter Agent** is an AI-powered tool that transforms screen recording videos (product demos, walkthroughs, tutorials) into structured Microsoft Learn-style documentation. The agent processes video content — extracting visual frames, audio transcripts, and on-screen text — and generates publication-ready Markdown documents that conform to Microsoft Learn's voice, tone, style guide, and document structure.

The agent runs as a **VS Code Chat Participant** (primary interface) with a backend designed for easy extension to a web UI. It uses **Azure AI Foundry** models and **Azure-native video/audio processing services**, with open-source fallbacks for cost optimization and local development.

---

## 2. Problem Statement

Engineering teams frequently create screen recordings to demonstrate new product features, walk through workflows, or showcase architecture. Converting these recordings into structured, high-quality documentation is:

- **Time-consuming:** Manual transcription, screenshot capture, and writing takes 4-10x the video length
- **Inconsistent:** Without style enforcement, documents vary widely in quality, structure, and voice
- **Error-prone:** Manual step extraction from videos leads to missed steps, incorrect sequences, and stale screenshots
- **Unscalable:** Documentation backlogs grow as product velocity increases

Commercial tools (Scribe, Tango, Loom) address parts of this problem but target SOP/process documentation — none produce MS Learn-formatted technical tutorials, quickstarts, or how-to guides.

---

## 3. Goals and Non-Goals

### Goals

| # | Goal | Success Metric |
|---|------|----------------|
| G1 | Process screen recording videos (<15 min) and extract structured content | Video processed in <5 min, >90% of key steps identified |
| G2 | Generate MS Learn-compliant Markdown with correct voice, tone, and structure | Documents pass Content Mentor/DocuMentor validation |
| G3 | Support multiple MS Learn document types (Quickstart, Tutorial, How-to, Concept, Overview) | Agent asks user which type to produce and adapts output accordingly |
| G4 | Enable iterative refinement via conversational feedback | User can request changes to specific sections; agent revises without full regeneration |
| G5 | Run locally (VS Code) or on Azure with identical capabilities | Feature parity between local and cloud deployments |
| G6 | Accept video from multiple sources (local files, Azure Blob, YouTube/Stream) | All three source types supported |
| G7 | Auto-capture and annotate screenshots from video keyframes | Screenshots included in output with step numbers and captions |

### Non-Goals (v1)

- Real-time video streaming analysis (batch processing only)
- Multi-language documentation generation (English only)
- Full MS Learn publishing pipeline integration (output is Markdown files; no auto-PR/auto-publish)
- MS Learn Module/Training content generation (YamlMime:Module format — future consideration)
- Code sample validation or execution (the agent generates docs, not runnable code)

---

## 4. Target Users

### Primary: Engineering Documentation Authors

- Engineers who create screen recordings of product demos
- Technical writers who need to convert video content to documentation
- Product managers who want to quickly document new features

### Secondary: Documentation Reviewers

- Senior engineers who review generated docs for technical accuracy
- Style reviewers who ensure MS Learn compliance

---

## 5. User Stories

### Core Workflow

```
US-1: As an engineer, I want to provide a screen recording video file so the agent can 
      analyze it and suggest what type of documentation to create.

US-2: As an engineer, I want the agent to ask me what type of MS Learn document to produce 
      (Quickstart, Tutorial, How-to, Concept, Overview) and what supplementary materials 
      I have available.

US-3: As an engineer, I want the agent to generate a complete MS Learn-compliant Markdown 
      document with frontmatter, annotated screenshots, and step-by-step instructions.

US-4: As an engineer, I want to iteratively refine the generated document by providing 
      feedback on specific sections.

US-5: As an engineer, I want the agent to extract and save key screenshots from the video 
      with annotations (step numbers, highlighted UI elements).
```

### Video Input

```
US-6: As an engineer, I want to provide videos from local files, Azure Blob Storage URLs, 
      or YouTube/Stream links.

US-7: As an engineer, I want to process videos up to 15 minutes long without timeouts 
      or failures.
```

### Quality and Style

```
US-8: As an engineer, I want generated documents to use Microsoft Learn voice and tone 
      (friendly, concise, scannable, empathetic, action-oriented).

US-9: As an engineer, I want the agent to use correct MS Learn Markdown extensions 
      (alerts, image syntax, code blocks, tabs) in the output.

US-10: As an engineer, I want generated documents to include minimal MS Learn YAML 
       frontmatter (title, description, author, ms.date, ms.topic, ms.service).
```

### Integration

```
US-11: As an engineer, I want to use the agent as a VS Code Chat Participant 
       (invoked via @video-documenter in Copilot Chat).

US-12: As an engineer, I want the agent to integrate with existing docs repos by 
       generating files in the correct directory structure.
```

---

## 6. Functional Requirements

### 6.1 Video Ingestion

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-1 | Accept local video files (.mp4, .mov, .mkv, .webm, .avi) via file path or file picker dialog | P0 |
| FR-2 | Accept Azure Blob Storage SAS URLs as video input | P0 |
| FR-3 | Accept YouTube and Microsoft Stream URLs (via download and re-upload) | P1 |
| FR-4 | Upload local videos to Azure Blob Storage for processing | P0 |
| FR-5 | Support videos up to 2 GB / 15 minutes duration | P0 |

### 6.2 Video Analysis Pipeline

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-6 | Extract audio track from video | P0 |
| FR-7 | Generate timestamped transcript from audio (speech-to-text) | P0 |
| FR-8 | Detect scene/screen transitions (UI state changes) | P0 |
| FR-9 | Extract keyframe images at scene change points | P0 |
| FR-10 | Perform OCR on keyframes to extract on-screen text (UI labels, menu items, dialog text) | P0 |
| FR-11 | Analyze keyframes with vision AI to describe UI state and identify user actions | P0 |
| FR-12 | Correlate transcript segments with corresponding keyframes by timestamp | P0 |

### 6.3 Document Generation

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-13 | Ask user which document type to produce and what supplementary materials are available | P0 |
| FR-14 | Generate document structure matching selected MS Learn template (Quickstart, Tutorial, How-to, Concept, Overview) | P0 |
| FR-15 | Generate YAML frontmatter with required MS Learn metadata fields | P0 |
| FR-16 | Write body content in MS Learn voice and tone | P0 |
| FR-17 | Include extracted screenshots with MS Learn image syntax (`:::image type="content" source="..." alt-text="...":::`) | P0 |
| FR-18 | Generate numbered step-by-step procedures from detected actions | P0 |
| FR-19 | Use MS Learn Markdown extensions appropriately (alerts, code blocks, checklists) | P1 |
| FR-20 | Generate alt-text for all images | P0 |

### 6.4 Iterative Refinement

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-21 | Accept natural language feedback on specific document sections | P0 |
| FR-22 | Revise targeted sections without regenerating the full document | P0 |
| FR-23 | Track conversation history for context-aware refinements | P0 |
| FR-24 | Allow user to accept, reject, or modify individual steps | P1 |

### 6.5 Output

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-25 | Output Markdown file(s) to a user-specified directory | P0 |
| FR-26 | Output extracted screenshots to a `media/` subdirectory | P0 |
| FR-27 | Generate frontmatter without triggering MS Learn compilation errors | P0 |
| FR-28 | Optionally annotate screenshots with step numbers and highlighted UI regions | P1 |

---

## 7. Non-Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| NFR-1 | Process a 10-minute video end-to-end in under 5 minutes | P0 |
| NFR-2 | Run fully locally with only an Azure AI Foundry endpoint (no other Azure services required) | P1 |
| NFR-3 | Run on Azure with managed services for production workloads | P0 |
| NFR-4 | Provide progress indicators during long-running video processing | P0 |
| NFR-5 | Handle errors gracefully with actionable error messages | P0 |
| NFR-6 | Support concurrent video processing (multiple users) when deployed on Azure | P2 |

---

## 8. MS Learn Style and Formatting Reference

### 8.1 Voice Principles

The agent MUST generate content following the five Microsoft voice principles:

1. **Focus on intent** — Clearly identify the customer and what task they're doing
2. **Use everyday words** — Natural language, less formal but still technical
3. **Write concisely** — Short sentences, no wasted words, affirmative tone
4. **Make it scannable** — Most important things first, use H2s to chunk, ≤12 steps per procedure
5. **Show empathy** — Supportive tone, honest about limitations

### 8.2 Grammar Rules

- Use contractions: *it's, you'll, you're, we're, let's*
- Sentence case for all headings (never title case)
- Serial/Oxford comma in lists of 3+
- Use "sign in" not "log in"
- No gerunds in H1 headings
- Don't number H2 sections
- Description metadata: 75–300 characters
- Title metadata: 43–59 characters

### 8.3 Document Templates

The agent uses templates from `MicrosoftDocs/content-templates`:

| Type | H1 Format | Key Sections |
|------|-----------|--------------|
| **Quickstart** | `Quickstart: <verb> <noun>` | Prerequisites → Task steps → Clean up → Next steps |
| **Tutorial** | `Tutorial: <verb> <noun>` | Checklist outline → Prerequisites → Task steps → Clean up → Next steps |
| **How-to** | `<verb> <noun>` | Prerequisites → Task steps → Next steps |
| **Concept** | `What is <noun>?` or `<noun> overview` | Conceptual sections (no numbered steps) → Next steps |
| **Overview** | `What is <product>?` | Feature sections → Requirements → Next steps |

### 8.4 Required YAML Frontmatter

```yaml
---
title: "<43-59 characters>"
description: "<75-300 characters>"
author: <github-id>
ms.author: <ms-alias>
ms.date: MM/DD/YYYY
ms.topic: quickstart|tutorial|how-to|concept-article|overview
ms.service: <service-name>
# Customer intent: As a <role>, I want <what> so that <why>.
---
```

### 8.5 MS Learn Markdown Extensions

The agent should use these extensions where appropriate:

```markdown
# Alerts
> [!NOTE]
> [!TIP]  
> [!IMPORTANT]
> [!CAUTION]
> [!WARNING]

# Images
:::image type="content" source="./media/step-01.png" alt-text="Description of the screenshot":::

# Code blocks
```azurecli
az resource create --name example
```

# Checklists (tutorials)
> [!div class="checklist"]
> * First task
> * Second task

# Next step buttons
> [!div class="nextstepaction"]
> [Next article](next-article.md)
```

---

## 9. Internal Microsoft Tooling Integration

### 9.1 Content Mentor (DocuMentor)

**Status:** Available in VS Code Marketplace  
**Owner:** Dana Martens, Microsoft Learn content tooling team  
**Integration point:** Use Content Mentor to validate and refine agent-generated documents

- AI-powered MS Learn style enforcement
- Metadata generation and optimization (titles, descriptions, customer intent)
- Word → Markdown conversion
- Code-aware documentation verification
- Style guide Q&A with authoritative source links

**Recommendation:** The Video Documenter agent should be designed as a **complementary tool** that generates draft content, which can then be refined using Content Mentor.

**Key capabilities for Video Documenter workflow:**
- `@content-mentor` chat participant in GitHub Copilot Chat for documentation-specific AI review
- Markdown auto-fix for common formatting issues (lists, tables, links, alerts, spacing, images)
- Link validation including detection of broken links, redirects, and timeouts
- Visual TOC management for Learn documentation hierarchies
- "Verify Against UI" capability — AI agent walks through live product UIs and compares against documentation

**Integration model:** Companion workflow. The Video Documenter generates draft content, then users run Content Mentor for AI-powered validation and refinement. The VS Code extension detects Content Mentor installation and provides contextual tips.

**Note:** Content Mentor (formerly DocuMentor) is maintained by Microsoft and is available as an internal Microsoft VS Code extension (`msft-content.content-mentor`).

### 9.2 Doc-Kit

**Status:** Internal pilot (Foundry docs team)  
**Owner:** Nick Brady (builder), Jill Reinauer (Foundry pilot)  
**Repo:** `microsoft-foundry/doc-kit` (internal)

Four-agent pipeline: **Plan → Author → Evaluate → Research**

- Plan Agent: Defines scope, audience, intent, section structure
- Author Agent: Generates prose + code samples grounded in real SDK code from GitHub
- Evaluate Agent: Quality grades (technical accuracy, completeness, developer experience)
- Research Agent: Validates instructions with Playwright, pulls latest SDK versions

**Relevance:** Doc-Kit's architecture directly validates our multi-agent approach. Key differences:
- Doc-Kit targets code-based documentation; our agent targets video-based content
- Doc-Kit grounds in SDK code; our agent grounds in video frames + transcripts
- Doc-Kit's evaluation agent pattern should be replicated for quality assurance

**Recommendation:** Contact Nick Brady for potential collaboration or API access. The Evaluate Agent pattern is directly reusable.

### 9.3 Learn Authoring Pack (VS Code)

**Status:** Publicly available on VS Code Marketplace  
**Extension ID:** `docsmsft.docs-authoring-pack`

Includes: Learn Markdown, Learn Preview, Learn YAML, Learn Article Templates, Learn Scaffolding, Learn Images, markdownlint.

**Recommendation:** Require Learn Authoring Pack as a companion extension. Use Learn Preview for rendered previews of generated content.

**Integration details (Phase 3):**
- Registered as `extensionDependencies` in the Video Documenter extension's `package.json`
- VS Code prompts users to install Learn Authoring Pack when they install Video Documenter
- Learn Preview integration: after generating a document, offer to open Learn Preview side-by-side
- Learn Article Templates used as a validation reference in the Evaluate Agent
- markdownlint configuration aligned with MS Learn rules

**Companion extension hierarchy:**
1. **Learn Authoring Pack** (public, required) — baseline authoring toolkit
2. **Content Mentor** (internal, optional) — AI documentation review and lifecycle
3. **Learn Authoring Assistant** (internal, optional) — AI writing style enforcement

### 9.4 AI Usage Disclosure

All agent-generated content MUST include the `ai-usage: ai-assisted` metadata flag:

```yaml
ms.custom: ai-assisted
```

This enables automatic AI disclosure notices on the published MS Learn page.

### 9.5 Microsoft Learn MCP Server

**Status:** Public, hosted, free, no authentication required  
**Endpoint:** `https://learn.microsoft.com/api/mcp` (Streamable HTTP transport)  
**Source:** `MicrosoftDocs/mcp` (also supports stdio for local development)  
**Docs:** `https://learn.microsoft.com/training/support/mcp`

The Microsoft Learn MCP Server exposes trusted, up-to-date Microsoft Learn documentation to MCP-compatible agents. It is designed to reduce hallucinations by grounding model outputs in official Microsoft content.

**MCP Tools:**

| Tool | Capability |
|------|-----------|
| `microsoft_docs_search` | Search the Microsoft Learn documentation index; returns titles, sections, and URLs |
| `microsoft_docs_fetch` | Fetch the full content of a specific Microsoft Learn article |
| `microsoft_code_sample_search` | Search for official code samples within Learn docs |

**Content scope:**
- ✅ Public Microsoft Learn documentation (Azure, Power Platform, Microsoft 365, .NET, etc.)
- ✅ Official Learn code samples embedded in docs
- ❌ Training modules, learning paths, exams

**Integration strategy:** The Video Documenter agents use MCP tools as live reference during processing:
- **Structure Agent** searches for related published articles to inform outline structure
- **Writer Agent** fetches published article examples for voice/tone grounding
- **Editor Agent** references published docs for style consistency checks

**Note:** "Microsoft Docs MCP" and "Microsoft Learn MCP" refer to the same server — Microsoft Docs was merged into Microsoft Learn.

**Recommendation:** Integrate as live tools available to agents during processing (Phase 3). Implement caching and graceful degradation for availability.

### 9.6 Microsoft Learn Authoring Assistant

**Status:** Available in VS Code Marketplace (Microsoft-internal only)  
**Extension ID:** `docsmsft.learn-authoring-assistant`

The Microsoft Learn Authoring Assistant is an AI-powered VS Code extension that helps authors improve the quality and style of Microsoft Learn content. It works with GitHub Copilot Chat to analyze Learn Markdown files using a custom AI model.

**Key capabilities:**
- Detect grammar, clarity, and voice issues in MS Learn content
- Enforce rules from the Microsoft Writing Style Guide
- Suggest edits directly in the editor via a "Suggested edits" pane
- Explanations of which style rules were applied, with links to official guidance
- Preview branding rule that checks product/technology names against Microsoft's corporate taxonomy

**How it differs from Content Mentor:**

| Dimension | Content Mentor | Learn Authoring Assistant |
|-----------|---------------|--------------------------|
| Focus | Documentation lifecycle (metadata, links, validation, UI verification) | Editorial quality (grammar, voice, style, branding) |
| AI features | `@content-mentor` chat participant | `/suggestEdits` in Copilot Chat |
| Markdown tooling | Auto-fix for formatting | None |
| Link validation | Yes | No |
| Metadata optimization | Yes | No |
| Writing style enforcement | Yes (partial) | Yes (primary focus) |

**Integration model:** Companion workflow. After document generation, Microsoft-internal users can invoke `/suggestEdits` in Copilot Chat for AI-powered style review. The VS Code extension detects installation and provides contextual tips.

**Recommendation:** Document the companion workflow. The extension is Microsoft-internal only, so do not create hard dependencies or recommend to external users.

---

## 10. Success Criteria

| Metric | Target | Measurement |
|--------|--------|-------------|
| Step detection accuracy | ≥90% of manual steps from a video are captured | Compare agent output vs. manual walkthrough |
| Style compliance | Documents pass Content Mentor validation with <3 warnings | Run Content Mentor on output |
| User time saved | ≥70% reduction in documentation time vs. manual | Time comparison study |
| Refinement cycles | Average ≤3 refinement rounds to reach publishable quality | Track conversation turns |
| Video processing time | <5 min for a 10-minute video | End-to-end timing |

---

## 11. Risks and Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Azure Video Indexer may not detect UI-specific elements (buttons, menus) in screen recordings | Medium | High | Supplement with GPT-4o Vision analysis of keyframes with UI-aware prompts |
| GPT-4o may hallucinate steps not shown in the video | High | Medium | Ground generation in transcript + OCR text; require frame evidence for each step |
| YouTube/Stream URL download may violate ToS | Low | Medium | Document legal considerations; prefer direct file upload |
| Doc-Kit evaluate agent has reliability issues (per internal assessment) | Medium | Medium | Build custom evaluation using MS Learn templates as rubrics |
| Azure AI Foundry model availability varies by region | Medium | Low | Support model flexibility; allow fallback to GPT-4o-mini |
| VS Code Chat Participant cannot natively accept video file uploads | Medium | High | Implement file picker dialog and context menu integration patterns |
| Microsoft Learn MCP Server may be unavailable or rate-limited | Medium | Low | Implement response caching (1-hour TTL), graceful degradation (agents continue with embedded style rules), structured logging for monitoring |
| Content Mentor and Learn Authoring Assistant are Microsoft-internal only | Low | N/A (by design) | Treat as companion workflow only; detect presence conditionally; never recommend to external users; no hard dependencies |

---

## 12. Dependencies

| Dependency | Type | Status |
|------------|------|--------|
| Azure AI Foundry (GPT-4o, GPT-4o-mini) | External service | Available |
| Azure AI Video Indexer | External service | Available |
| Azure AI Speech | External service | Available |
| Azure Blob Storage | External service | Available |
| VS Code Chat Participant API | Platform API | Stable (v1.100+) |
| Content Mentor extension | Internal tool | Available (Microsoft-internal) |
| FFmpeg | Open source | Available |
| PySceneDetect | Open source | Available |
| Microsoft Agent Framework v1.0 | Framework | Available |
| Microsoft Learn MCP Server | External service (MCP) | Available (public, free, no auth) |
| Learn Authoring Assistant extension | Internal tool | Available (Microsoft-internal) |

---

## 13. Resolved Questions

| # | Question | Decision |
|---|----------|----------|
| Q1 | Should we integrate with Doc-Kit's Evaluate Agent, or build our own? | **Build our own.** No external dependency on Doc-Kit. Use rule-based checks (heading case, frontmatter, step count) + lightweight LLM scoring pass. Doc-Kit's own team acknowledges reliability issues. |
| Q2 | What specific `ms.service` values should the agent support for frontmatter? | **Configurable list.** Ship with a default list of the team's most common services. Other users can configure their own list. Agent presents the list as selectable options with an "Other (enter your own)" escape hatch. |
| Q3 | Should we support MS Learn Module (training) format in addition to article format? | **Deferred to v2.** The 5 article types (Quickstart, Tutorial, How-to, Concept, Overview) cover most needs. Module format (`YamlMime:Module` + unit files) is significantly more complex. |
| Q4 | What is the licensing situation for yt-dlp for downloading YouTube videos? | **Optional with documented risk.** yt-dlp is an optional dependency. Users must acknowledge YouTube ToS considerations. Direct file upload and Blob URLs are the primary supported paths. |
| Q5 | Should we expose the agent as an MCP server for broader Copilot surface integration? | **Stretch goal in Phase 4.** The backend API is already MCP-compatible by design. Adding an MCP adapter in Phase 4 enables GitHub Copilot Chat across all surfaces (VS Code, JetBrains, GitHub.com, CLI). |
