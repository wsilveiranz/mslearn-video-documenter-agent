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

Every log entry must include enough context to reproduce the issue (e.g., `video_id`, `agent_name`, `step`). Never log API keys or full file paths containing usernames.

Log levels: `error` = operation failed; `warn` = degraded but continuing; `info` = significant state change; `debug` = dev only.

### Configuration

Environment-based configuration via `pydantic-settings`. All secrets in `.env` (gitignored). See `docs/ARCHITECTURE.md §5.3` for the full settings spec.

### Error Handling

- Wrap all Azure service calls in try/except with structured error logging
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
- Commands: `/plan`, `/analyze`, `/generate`, `/refine`, `/save`, `/status`

---

## Documentation Conventions

- **Use mermaid for diagrams** in markdown documents, not ASCII art
- **Update `docs/ARCHITECTURE.md`** after changing the agent pipeline, service integrations, or data models

---

## Git Workflow

- **Issue-first rule**: Before writing any code, create a GitHub issue (or confirm one exists). The issue number is required for the commit message (`Fixes #N`). If the user reports a bug or requests a feature, create the issue as the first step — not after committing.
- **Commit locally in small, logical groups** so individual features can be cherry-picked if needed
- **Do NOT push to GitHub** unless the user explicitly asks — local commits only until they confirm
- **Always close issues in commit messages**: when a commit fully resolves a GitHub issue, include `Closes #N` (or `Fixes #N` for bugs). Example: `feat: implement extraction agent\n\nFixes #12\n\nCo-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`
- Multiple issues can be closed in one commit: `Fixes #18, Fixes #21`
- **Task completion gate**: Before reporting a task as done, check these three items in order: (1) GitHub issue exists → (2) commit includes `Fixes #N` → (3) build/tests pass. If any is missing, do it now — do not ask the user to confirm or remind you

### PR Review Workflow

When fixing PR review comments, follow this exact sequence — do NOT skip steps:

1. **Fix** — implement all requested changes
2. **Commit** — `git add` + `git commit` with conventional commit prefix
3. **Push** — `git push` to the remote branch
4. **Reply** — for each review thread, post a brief comment explaining what was fixed
5. **Resolve** — resolve each review thread via the GitHub GraphQL `resolveReviewThread` mutation

Common mistakes to avoid:
- Do NOT report "all comments addressed" without also pushing and resolving threads on GitHub
- Do NOT resolve threads without first posting a reply explaining the fix
- If the user says "fix the comments" or "address the review", this means the full 5-step cycle — not just local commits

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
| `prompt:` | Agent system prompt changes (document what changed and why in the commit body) |

---

## Debugging & Observability

- **Instrument before investigating**: If structured logging or error handling is missing from code under investigation, add it first — treat missing instrumentation as a bug to fix before diagnosing
- **Never commit speculative fixes** for runtime bugs without evidence. If a fix doesn't work on the first attempt, stop guessing and add diagnostics (logs, try-catch)
- **Stop spinning once the fix works**: Commit immediately. Ask before investigating further.
- **For Azure service errors**: Check structured logs → verify env vars → check resource provisioning → escalate

---

## VS Code Extension Packaging

The extension runs in **two different layouts** — code must handle both:

| Layout | When | Backend location | Extension path |
|--------|------|------------------|---------------|
| **Monorepo (dev)** | `F5` debug or `code --extensionDevelopmentPath` | `../backend` (sibling directory) | Repository root `/vscode-extension` |
| **VSIX (installed)** | Production install via `.vsix` file | `{extensionPath}/backend` (bundled inside) | `~/.vscode/extensions/{ext-name}` |

**Rules:**
- **Always resolve paths relative to `context.extensionPath`**, never relative to the workspace or `../`
- **Detect layout at activation**: check if `{extensionPath}/backend/pyproject.toml` exists → bundled VSIX; otherwise → monorepo dev
- **Cache prerequisite state**: don't re-run `pip install -e` on every activation — check if the venv and package already exist
- **Activate on `onStartupFinished`**: prereqs and backend should start in the background before the user first invokes `@video-documenter`, not on first chat message

### PyInstaller Hidden Imports

The VSIX bundles the Python backend as a standalone executable via PyInstaller (`backend/backend.spec`). PyInstaller traces imports **statically** from `src/main.py` — any module imported lazily inside a function body (e.g., `from mcp import ClientSession` inside an `async def`) will **not** be discovered and must be added to the `hiddenimports` list in `backend.spec`.

**When adding a new backend module or dependency:**
1. Check whether the module is imported at the top level of a file in the import chain from `main.py → routes.py → agents/`
2. If it's imported inside a function (lazy/deferred import), add it to `hiddenimports` in `backend.spec`
3. This applies to both first-party modules (`src.services.*`) and third-party packages (`mcp`, `markitdown`, etc.)
4. Always clean `__pycache__` before building — stale `.pyc` files cause PyInstaller to bundle old bytecode (use the `--clean` flag)

---

## Implementation Quality

- **Verify new data flows end-to-end**: Trace new fields through every layer (agent → service → API → model → output) and confirm each is present and correctly typed
- **Test with real video**: Before delivering pipeline changes, run against a sample screen recording and verify the output Markdown
- **Run eval suite before and after pipeline changes**: Run `pytest -m eval` before and after any change to agents, prompts, or the orchestrator. Flag any dimension that drops >5% as a regression. Do NOT skip this even if the change seems minor
- **Model routing changes require output comparison**: If changing how models are selected or routed, generate a test document with old and new routing and compare quality before committing

---

## Session Management

- At **turn 25**, warn: _"Consider wrapping up or deferring remaining items to a new session."_
- At **turn 35**, strongly recommend creating issues for remaining work and starting fresh
- **Don't split causally-connected work** — if you're testing what you just built and discover a bug, that's one session
- **Do split independently-plannable work** — bug fixes, documentation, infra setup are separate sessions
- **Use GitHub issues as context bridges** — when a session ends with unfinished work, update the issue with what was tried and what failed

---

## Fleet Mode

All plans must be optimised for **fleet mode** (parallel subagent execution). When creating implementation plans:

- **Structure todos as independent, parallelisable units** wherever possible — avoid unnecessary sequential dependencies between tasks
- **Group work by component** (e.g., extraction agent, writer agent, VS Code extension, FastAPI routes) so each subagent gets a self-contained scope
- **Provide full context per todo** — sub-agents do NOT receive copilot-instructions, so each task description must include commit rules (`Fixes #N` + `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>` trailer), the assigned model, and any project conventions (MS Learn style, `structlog` logging) relevant to that task
- **Mark true dependencies explicitly** in `todo_deps` — only add a dependency when one todo genuinely cannot start until another completes (e.g., data models must exist before agent uses them)
- **Include an issue-to-todo mapping table** in every plan

### Model Assignment Per Task — MANDATORY

Sub-agents do NOT receive copilot-instructions. Model guidance in a summary section will be lost. Every task must have a model assigned **during planning**, not as an afterthought.

**Rules:**

1. **Embed the model in the task description text** — not as a separate field, not in a global "Recommended Models" section. It must be part of the execution instruction so it survives prompt rewriting.
2. **Use the complexity map below** to assign the right model. Do not blanket-assign the same model to all tasks regardless of complexity.
3. **Include the GitHub issue reference** (e.g., "Closes #12") in every task.

**Complexity map:**

- 🟢 Simple — single-file changes, config, boilerplate, docs, straightforward bug fixes: `claude-haiku-4.5` or `gpt-4.1`
- 🟡 Medium — feature implementation, service clients, UI components, most new code: `claude-sonnet-4.6` or `gpt-5.2-codex`
- 🔴 Complex — multi-component coordination, system prompts, pipeline orchestration, architectural decisions: `claude-opus-4.6`

**Classification rule**: If a task touches one file and requires no design decisions → 🟢. If it implements a feature within a single component → 🟡. If it spans multiple components or determines output quality (prompts, orchestration) → 🔴.

**Self-check gate**: Before presenting a plan, verify (1) every task has a model in its description, and (2) tasks at different complexity levels use different models. If all tasks say `claude-sonnet-4.6`, the complexity map wasn't consulted.

**Examples:**

❌ BAD — model as separate metadata (lost in subagent prompt):
```
Task: Design architecture
Model: claude-opus-4.6
Description: Define system design including components, boundaries, and trade-offs.
```

❌ BAD — same model blanket-assigned regardless of complexity:
```
1. Update .gitignore — Use claude-sonnet-4.6. Closes #10.
2. Implement extraction agent — Use claude-sonnet-4.6. Closes #11.
3. Update ARCHITECTURE.md — Use claude-sonnet-4.6. Closes #12.
```

✅ GOOD — model embedded in description, varies by complexity:
```
1. Update .gitignore — Use claude-haiku-4.5 (🟢 simple config change). Closes #10.
2. Implement extraction agent — Use claude-sonnet-4.6 to implement the extraction agent
   that extracts keyframes and transcript via FFmpeg + PySceneDetect (🟡 medium). Closes #11.
3. Design pipeline orchestration — Use claude-opus-4.6 to define multi-agent pipeline
   coordination and error recovery (🔴 complex). Closes #12.
```

### Post-Fleet Cleanup and Verification

After a fleet deployment completes, the orchestrator must clean up and verify before reporting success:

**Cleanup (do this FIRST):**
1. **`git status`** — check for uncommitted files left behind by sub-agents
2. **Stage and commit** any legitimate files sub-agents forgot to commit
3. **Remove stray files** — sub-agents sometimes create `.vscode/tasks.json`, temp files, or other artifacts. Delete anything that wasn't part of the plan
4. **Verify `git diff --stat`** — confirm only expected files were modified

**Verification:**
1. **Type check** — run `pyright` on the backend
2. **Lint** — run `ruff check` on the backend
3. **Test** — run `pytest` for all modified modules
4. **Build extension** — if VS Code extension was modified, verify it compiles
