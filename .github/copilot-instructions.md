# Copilot Instructions for MS Learn Video Documenter Agent

## Architecture Overview

This is an **AI-powered multi-agent application** that transforms screen recording videos into structured Microsoft Learn-style documentation. It uses a **6-agent pipeline** orchestrated by **Microsoft Agent Framework (MAF) v1.0**, deployed as a **Foundry Hosted Agent** on Azure.

```
vscode-extension/        → TypeScript — VS Code Chat Participant (@video-documenter)
backend/
  src/
    agents/               → Python — MAF agent pipeline (Ingestion, Extraction, Structure, Writer, Editor, Evaluate)
    services/             → Python — Azure service clients (Video Indexer, Speech, Blob, GPT-4o Vision)
    templates/            → Markdown — MS Learn article templates (Quickstart, Tutorial, How-to, Concept, Overview)
    prompts/              → Markdown — Agent system prompts (writer, editor, evaluate, structure)
    models/               → Python — Data models (video, document, evaluation)
    api/                  → Python — FastAPI routes + WebSocket
  tests/                  → Python — Unit and integration tests
docs/                     → PRD, Architecture, Roadmap
```

### Key Reference Documents

- **PRD**: `docs/PRD.md` — product requirements, user stories, MS Learn style reference
- **Architecture**: `docs/ARCHITECTURE.md` — agent pipeline, Azure services, deployment, MAF vs Foundry positioning
- **Roadmap**: `docs/ROADMAP.md` — phased implementation plan

When working on a component, read the relevant doc section first — do NOT guess requirements or MS Learn formatting rules.

### Agent Pipeline Architecture

```
Video Input ──▶ [1. Ingestion] ──▶ [2. Extraction] ──▶ [3. Structure] ──▶ [4. Writer] ──▶ [5. Editor] ──▶ [6. Evaluate] ──▶ Output
                                                                                              ▲                    │
                                                                                              │    Refinement Loop  │
                                                                                              └────────────────────┘
```

| Agent | Responsibility | Model |
|-------|---------------|-------|
| **Ingestion** | Accept video from any source, upload to Blob | — |
| **Extraction** | Extract transcript, keyframes, OCR, scenes | GPT-4o (vision) |
| **Structure** | Map content to MS Learn template, create outline | GPT-4o-mini |
| **Writer** | Generate full Markdown in MS Learn voice/tone | GPT-4o |
| **Editor** | Refine for style compliance, handle user feedback | GPT-4o-mini |
| **Evaluate** | Quality-gate: completeness, accuracy, style, readability | GPT-4o |

### Two Processing Modes

| Mode | Video Analysis | Transcription | When to Use |
|------|---------------|---------------|-------------|
| **Cloud** | Azure Video Indexer | Azure AI Speech | Production, highest quality |
| **Local** | FFmpeg + PySceneDetect | OpenAI Whisper | Development, cost-sensitive |

Both modes use Azure AI Foundry (GPT-4o) for vision analysis and document generation.

---

## Technology Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| **Agent Framework** | Microsoft Agent Framework (MAF) v1.0 | Replaces Semantic Kernel + AutoGen |
| **Runtime (Production)** | Azure AI Foundry Agent Service (Hosted Agents) | Framework-agnostic managed runtime |
| **Backend** | Python 3.10+ / FastAPI | Video processing ecosystem |
| **VS Code Extension** | TypeScript / Chat Participant API | Primary user interface |
| **Video Analysis (Cloud)** | Azure AI Video Indexer | Scenes, keyframes, OCR, transcript |
| **Video Analysis (Local)** | FFmpeg + PySceneDetect + OpenCV | Free, containerizable |
| **Transcription** | Azure AI Speech / OpenAI Whisper | Fast transcription API / local fallback |
| **LLM** | Azure AI Foundry (GPT-4o, GPT-4o-mini) | Vision + generation |
| **Storage** | Azure Blob Storage / local filesystem | Video staging, keyframe images |

---

## MS Learn Style Rules — CRITICAL

All generated documentation MUST follow Microsoft Learn voice, tone, and formatting. These rules are embedded in agent system prompts but must also be understood by developers working on prompt engineering.

### The Five Voice Principles

1. **Focus on intent** — Clearly identify the customer and what task they're doing
2. **Use everyday words** — Natural language, less formal but still technical
3. **Write concisely** — Short sentences, no wasted words, affirmative tone
4. **Make it scannable** — Most important things first, use H2s to chunk, ≤12 steps per procedure
5. **Show empathy** — Supportive tone, honest about limitations

### Grammar and Formatting Rules

- Use contractions: *it's, you'll, you're, we're, let's*
- Sentence case for all headings (never title case)
- Serial/Oxford comma in lists of 3+
- Use "sign in" not "log in"
- No gerunds in H1 headings
- Don't number H2 sections
- Title metadata: 43–59 characters
- Description metadata: 75–300 characters

### MS Learn Markdown Extensions

```markdown
# Alerts (use sparingly — max 1-2 per article)
> [!NOTE]
> [!TIP]
> [!IMPORTANT]
> [!CAUTION]
> [!WARNING]

# Images (always use this syntax, never standard markdown images)
:::image type="content" source="./media/step-01.png" alt-text="Description":::

# Code blocks with language identifiers
```azurecli
az resource create --name example
```

# Checklists (tutorials only)
> [!div class="checklist"]
> * First task
> * Second task

# Next step buttons
> [!div class="nextstepaction"]
> [Next article](next-article.md)
```

### Document Type Templates

| Type | H1 Format | ms.topic Value |
|------|-----------|---------------|
| **Quickstart** | `Quickstart: <verb> <noun>` | `quickstart` |
| **Tutorial** | `Tutorial: <verb> <noun>` | `tutorial` |
| **How-to** | `<verb> <noun>` | `how-to` |
| **Concept** | `What is <noun>?` | `concept-article` |
| **Overview** | `What is <product>?` | `overview` |

### Required YAML Frontmatter

```yaml
---
title: "<43-59 characters>"
description: "<75-300 characters>"
author: <github-id>
ms.author: <ms-alias>
ms.date: MM/DD/YYYY
ms.topic: quickstart|tutorial|how-to|concept-article|overview
ms.service: <service-name>
ms.custom: ai-assisted
# Customer intent: As a <role>, I want <what> so that <why>.
---
```

The `ms.service` values are configurable per team. The agent presents a selectable list with an "Other" option for custom values.

---

## Internal Microsoft Tooling

These internal tools are relevant to this project:

| Tool | Use For | Status |
|------|---------|--------|
| **Content Mentor (DocuMentor)** | Validate and refine generated docs | VS Code Marketplace — use as companion |
| **Doc-Kit** | Architecture reference (4-agent doc pipeline) | Internal pilot (`microsoft-foundry/doc-kit`) |
| **Learn Authoring Pack** | Preview generated MS Learn Markdown | VS Code Marketplace (`docsmsft.docs-authoring-pack`) |

---

## Design & Security Principles

- **Privacy first**: Video files may contain sensitive content. Process locally when possible; use Blob Storage with time-limited SAS tokens; no permanent video storage in cloud
- **AI disclosure**: All generated content MUST include `ms.custom: ai-assisted` metadata
- **Grounded generation**: Every step in generated docs must be traceable to transcript text, OCR evidence, or keyframe analysis. Do not allow the LLM to hallucinate steps not shown in the video
- **Reuse before building**: Before creating a new service client, check `backend/src/services/` for existing implementations. Before adding a new agent, verify it can't be handled by extending an existing one

---

## Python Backend Conventions

### Project Configuration
- Use `pyproject.toml` with `uv` or `pip` for dependency management
- Use `ruff` for linting + formatting
- Use `pyright` for type checking
- Use `pytest` for testing with `pytest-asyncio` for async tests

### Logging Standards

Use `structlog` for structured logging. Raw `print()` calls are not permitted.

```python
import structlog
logger = structlog.get_logger()

logger.info("video_processed", video_id=video_id, duration_s=duration, scenes=len(scenes))
logger.error("extraction_failed", video_id=video_id, error=str(e))
```

**Mandatory log fields:** Every log entry must include `operation` (what was attempted) and enough context to reproduce the issue (e.g., `video_id`, `agent_name`, `step`). Never log API keys or full file paths containing usernames.

**Log levels:** `error` = operation failed; `warn` = degraded but continuing; `info` = significant state change; `debug` = dev only, never in production.

### Configuration

Environment-based configuration via `pydantic-settings`. All secrets in `.env` (gitignored).

```python
class Settings(BaseSettings):
    processing_mode: Literal["cloud", "local"] = "cloud"
    azure_openai_endpoint: str
    azure_openai_api_key: str
    azure_openai_deployment: str = "gpt-4o"
    # ... see docs/ARCHITECTURE.md §5.3 for full spec
```

### Error Handling

- Wrap all Azure service calls in try/except with structured error logging
- Agent failures should be retryable — use MAF's checkpointing for recovery
- Never swallow exceptions silently; always log with context before re-raising

---

## VS Code Extension Conventions

### TypeScript Standards
- Strict TypeScript (`"strict": true` in tsconfig)
- Use the VS Code Chat Participant API (`vscode.chat.createChatParticipant`)
- Extension is a thin client — all processing logic lives in the Python backend
- Communicate with backend via `BackendClient` (HTTP + WebSocket)

### Chat Participant Interaction
- User invokes via `@video-documenter` in Copilot Chat
- Three input patterns for video files: chat prompt path, context menu, file picker dialog
- Stream progress via `stream.progress()`, content via `stream.markdown()`
- Support commands: `/analyze`, `/generate`, `/refine`

---

## Documentation Conventions

- **Use mermaid for diagrams**: All diagrams in markdown documents should use mermaid syntax rather than ASCII art. Mermaid renders natively in GitHub and VS Code
- **Update docs after architectural changes**: After changing the agent pipeline, service integrations, or data models, update the relevant section in `docs/ARCHITECTURE.md`. Do not wait for the user to ask
- **Prompt changes require documentation**: When modifying agent system prompts in `backend/src/prompts/`, document what changed and why in the commit message

---

## Git Workflow

- **Issue-first rule**: Before writing any code, create a GitHub issue (or confirm one exists). The issue number is required for the commit message (`Fixes #N`). If the user reports a bug or requests a feature, create the issue as the first step — not after committing.
- **Commit locally in small, logical groups** so individual features can be cherry-picked if needed
- **Do NOT push to GitHub** until the user has confirmed local testing is complete and they are happy with the changes
- When the user explicitly asks to push, then push to the remote
- **Always close issues in commit messages**: when a commit fully resolves a GitHub issue, include `Closes #N` (or `Fixes #N` for bugs) in the commit message body. This auto-closes the issue when pushed to `main`. Example:
  ```
  feat: implement extraction agent with FFmpeg + PySceneDetect

  Fixes #12

  Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
  ```
- Multiple issues can be closed in one commit: `Fixes #18, Fixes #21`
- **Task completion gate**: Before reporting a task as done, check these three items in order: (1) GitHub issue exists → (2) commit includes `Fixes #N` → (3) build/tests pass. If any is missing, do it now — do not ask the user to confirm or remind you

### Branch Strategy

- `main` — stable, deployable code
- `feature/<issue-number>-<short-description>` — feature branches
- `fix/<issue-number>-<short-description>` — bug fix branches
- Always create a PR for merging to `main`; direct pushes only for initial setup

### Conventional Commits

Use conventional commit prefixes:

| Prefix | Use For |
|--------|---------|
| `feat:` | New feature or agent capability |
| `fix:` | Bug fix |
| `refactor:` | Code restructuring without behavior change |
| `docs:` | Documentation only |
| `test:` | Adding or updating tests |
| `chore:` | Build config, dependencies, tooling |
| `prompt:` | Agent system prompt changes |

---

## Debugging & Observability

- **Instrument before investigating**: If structured logging or error handling is missing from code under investigation, add it first — treat missing instrumentation as a bug to fix before diagnosing
- **Never commit speculative fixes** for runtime bugs without evidence. If a fix doesn't work on the first attempt, stop guessing and add diagnostics (logs, try-catch)
- **Stop spinning once the fix works**: If uncommitted changes resolve the reported issue, run `git add` and `git commit` immediately. Do not continue investigating — commit first, then ask the user if they want deeper analysis
- **For Azure service errors**: Check structured logs first; verify environment variables are loaded; check Azure resource provisioning status; then escalate

---

## Implementation Quality

- **Verify new data flows end-to-end**: When adding a new field or data type to the pipeline, trace it through every layer — agent → service → API response → data model → output file — and confirm it's present and correctly typed in each
- **Test with real video**: Before delivering any pipeline change, run it against a sample screen recording. Verify the output Markdown is valid and screenshots are correctly referenced
- **Prompt changes require A/B comparison**: When modifying agent system prompts, generate output with both old and new prompts against the same video and compare quality

---

## Session Management

- **Track turn count** throughout the session. At **turn 15**, briefly note: _"We're at ~15 turns — on track."_
- At **turn 25**, warn: _"We're at ~25 turns. Consider wrapping up or deferring remaining items to a new session."_
- At **turn 35**, strongly recommend: _"This session is getting long (35+ turns). Let's create issues for remaining work and start fresh."_
- If the user asks to continue past 35 turns, respect that — but remind them again at 45
- **To start a fresh session** without leaving the CLI: use `/clear` to reset conversation context. Memories and instructions carry over automatically

### When to Split vs. Continue Sessions
- **Don't split causally-connected work.** If you're testing what you just built and discover a bug during testing, that's one session
- **Do split independently-plannable work.** Bug fixes, documentation, infra setup, and test infrastructure are separate sessions
- **Use GitHub issues as context bridges.** When a session ends with unfinished work, update the issue with what was tried and what failed

---

## Fleet Mode

Plans should be optimised for **fleet mode** (parallel subagent execution) by default. When creating implementation plans:

- **Structure todos as independent, parallelisable units** wherever possible — avoid unnecessary sequential dependencies between tasks
- **Group work by component** (e.g., extraction agent, writer agent, VS Code extension, FastAPI routes) so each subagent gets a self-contained scope
- **Provide full context per todo** — each task description must include enough detail for an independent subagent to execute without cross-referencing other todos. **Every todo must specify which GitHub issue it closes** (e.g., "Closes #12") so the sub-agent includes it in the commit message
- **Mark true dependencies explicitly** in `todo_deps` — only add a dependency when one todo genuinely cannot start until another completes (e.g., data models must exist before agent uses them)
- **Include an issue-to-todo mapping table** in every plan

### Model Assignment Per Task — MANDATORY

When generating plans or task breakdowns intended for `/fleet` execution, the model selection **MUST** be embedded directly in each task description. Sub-agents do NOT receive copilot-instructions or global context — model guidance that lives only in a summary section will be lost during subagent invocation.

**Rules (strictly enforced):**

1. **Every task MUST include an explicit model assignment** — no task may omit the model.
2. **The model must be stated inside the task description itself** — not only in a global "Recommended Model" section.
3. **Repeat the model requirement in the task instruction** to ensure it is preserved during prompt rewriting. Model instructions are part of the execution instruction, not a separate metadata note.
4. **Do NOT rely on global model guidance alone** — it must be localised per task.
5. **Use the Model Complexity Map** (see [Model Selection](#model-selection)) to assign the appropriate model based on task complexity.
6. **Plans intended for `/fleet` must be directly usable** as input without requiring additional model instructions to be injected.
7. **Prefer redundancy over brevity** for model instructions — it is better to repeat the model requirement than risk it being dropped.

**Required task format:**

Each task in a fleet plan must follow this structure:

```
Task: <short task name>
Description:
  - Clearly describe the work to be done
  - Explicitly state the model to use (e.g., "Use claude-sonnet-4.6 to implement the service client")
  - Ensure the model instruction is part of the execution instruction, not a separate note
  - Include the GitHub issue reference (e.g., "Closes #12")
```

**Examples:**

❌ BAD — model is separated from execution context (will be lost in subagent prompt):
```
Task: Design architecture
Model: claude-opus-4.6
Description: Define system design including components, boundaries, and trade-offs.
```

✅ GOOD — model is embedded in the execution instruction:
```
Task: Design architecture
Description:
  Use claude-opus-4.6 to perform deep architectural analysis and define system design,
  including components, boundaries, and trade-offs. The model choice is claude-opus-4.6
  because this is a complex (🔴) multi-component design task. Closes #7.
```

❌ BAD — model only in global section, not in task:
```
## Tasks
1. Implement extraction agent — extract keyframes and transcript
2. Write unit tests for extraction

## Recommended Models
- Task 1: claude-sonnet-4.6
- Task 2: claude-haiku-4.5
```

✅ GOOD — model stated in each task description:
```
## Tasks
1. Implement extraction agent — Use claude-sonnet-4.6 to implement the extraction agent
   that extracts keyframes and transcript via FFmpeg + PySceneDetect. Medium complexity (🟡).
   Closes #14.
2. Write unit tests for extraction — Use claude-haiku-4.5 to write pytest unit tests
   for the extraction agent. Simple complexity (🟢). Closes #15.
```

### Sub-Agent Rules (mandatory — sub-agents do NOT receive copilot-instructions)

The orchestrator must include the following in every sub-agent prompt:

1. **Commit rules**: The GitHub issue number, `Fixes #N` format, and `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>` trailer
2. **Model assignment**: The specific model to use for the task, as determined by the Model Complexity Map. This MUST be part of the task description text, not a separate parameter — sub-agents lose context that isn't in their prompt
3. **MS Learn style rules**: If the sub-agent generates or modifies prompts/templates, include the voice principles and formatting rules from this document
4. **Logging requirement**: Use `structlog`, never raw `print()`

### Post-Fleet Verification

After a fleet deployment completes, the orchestrator must verify integration before reporting success:

1. **Type check** — run `pyright` on the backend
2. **Lint** — run `ruff check` on the backend
3. **Test** — run `pytest` for all modified modules
4. **Build extension** — if VS Code extension was modified, verify it compiles

---

## Model Selection

After completing any plan (plan.md), always end with a "Recommended Model" section:

- 🟢 Simple (config, boilerplate, docs, single-file changes): recommend `claude-haiku-4.5` or `gpt-4.1`
- 🟡 Medium (feature builds, agent implementation, service clients): recommend `claude-sonnet-4.6` or `gpt-5.2-codex`
- 🔴 Complex (multi-agent orchestration, pipeline integration, prompt engineering): recommend `claude-opus-4.6`

### Component-specific defaults
- **Individual agent implementation**: 🟡 medium
- **System prompt engineering**: 🔴 complex — quality of prompts directly determines output quality
- **Service clients (Video Indexer, Speech, Blob)**: 🟡 medium
- **VS Code extension**: 🟡 medium
- **Pipeline orchestration / MAF integration**: 🔴 complex
- **Configuration, tests, docs**: 🟢 simple

Format: **Suggested model for implementation:** `model-name` — [one-line justification]
