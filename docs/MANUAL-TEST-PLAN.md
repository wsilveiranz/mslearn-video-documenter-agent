# Manual Test Plan — VS Code Chat Participant

This document describes how to test the `@video-documenter` VS Code Chat Participant with the Python backend. Use this after any changes to the extension or backend API.

## Prerequisites

| Requirement | How to verify |
|---|---|
| Python 3.11+ | `python --version` |
| FFmpeg 6.0+ | `ffmpeg -version` |
| Node.js 24+ | `node --version` |
| Azure CLI signed in | `az account show` |
| Azure AI Foundry endpoint configured | `.env` has `FOUNDRY_PROJECT_ENDPOINT` |
| VS Code 1.100+ | `code --version` |
| GitHub Copilot Chat extension | Installed in VS Code |
| A test video file (≤ 5 min recommended) | Any `.mp4` screen recording |

> [!TIP]
> Use a short (1–3 min) screen recording that shows a clear procedure — creating a resource, running a CLI command, navigating a UI. This produces the most testable output.

---

## Setup

### 1. Start the backend

```bash
cd backend
python -m src.main
```

Verify it starts on `http://localhost:8000`:

```bash
curl http://localhost:8000/api/v1/health
# Expected: {"status":"ok","service":"video-documenter"}
```

### 2. Launch the extension in development mode

**Option A — VS Code GUI:**

1. Open the `vscode-extension/` folder in VS Code
2. Press **F5** (or Run → Start Debugging)
3. A new VS Code window opens — this is the **Extension Development Host**
4. Open a workspace folder in the dev host (the folder where output docs will be saved)

**Option B — Command line:**

```bash
cd vscode-extension
npm run compile
code --extensionDevelopmentPath=. --new-window
```

### 3. Verify extension loaded

In the Extension Development Host:

1. Open **Copilot Chat** (Ctrl+Shift+I or the chat icon)
2. Type `@video-documenter` — autocomplete should show the participant
3. Type `@video-documenter hello` — you should get a conversational response about the available commands

---

## Test scenarios

### TC-01: Health check / backend down

| Step | Action | Expected result |
|------|--------|-----------------|
| 1 | **Stop** the backend server | |
| 2 | Type `@video-documenter /analyze C:\path\to\video.mp4` | ❌ "Backend not running" error with start instructions |
| 3 | **Start** the backend again | |
| 4 | Retry the same command | Should proceed to upload |

### TC-02: Analyze with path in prompt

| Step | Action | Expected result |
|------|--------|-----------------|
| 1 | Type `@video-documenter /analyze C:\path\to\your\video.mp4` | Progress spinner shows "Uploading video..." |
| 2 | Wait for ingestion | Progress updates: "ingesting → ingestion_complete" |
| 3 | Completion | ✅ success table with Video ID, prompt to `/generate` |

**Verify:**
- Video ID is displayed and looks like a UUID
- State shows `analyzed` (confirmed by `/status`)

### TC-03: Analyze with file picker

| Step | Action | Expected result |
|------|--------|-----------------|
| 1 | Type `@video-documenter /analyze` (no path) | File picker dialog opens |
| 2 | Select a video file | Ingestion starts, progress shown |
| 3 | Cancel the file picker instead | Help message shown with usage examples |

### TC-04: Analyze via context menu

| Step | Action | Expected result |
|------|--------|-----------------|
| 1 | In the Explorer, right-click an `.mp4` file | "Analyze with Video Documenter" option appears |
| 2 | Click it | Copilot Chat opens with `/analyze <path>` pre-filled |
| 3 | Send the message | Ingestion proceeds normally |

**Verify:**
- Context menu only appears for video file extensions (`.mp4`, `.avi`, `.mov`, `.mkv`, `.webm`)
- Non-video files (`.txt`, `.pdf`) should NOT show the option

### TC-05: Generate with QuickPick

| Step | Action | Expected result |
|------|--------|-----------------|
| 1 | After TC-02 or TC-03 completes, type `@video-documenter /generate` | QuickPick appears with 5 doc types |
| 2 | Select **Tutorial** | Progress: "Generating tutorial document..." |
| 3 | Wait for pipeline (2–5 min typical) | Progress updates as pipeline runs |
| 4 | Completion | ✅ success table, doc preview in chat, file opened in editor |

**Verify:**
- Document saved to `<workspace>/docs/<document-id>.md`
- Markdown preview opens side-by-side (if `autoOpenPreview` enabled)
- Preview in chat is truncated at ~3000 chars with "(truncated)" note
- Document contains valid YAML frontmatter with `ms.topic: tutorial`
- Document uses MS Learn heading conventions

### TC-06: Generate with doc type in prompt

| Step | Action | Expected result |
|------|--------|-----------------|
| 1 | Type `@video-documenter /generate quickstart` | No QuickPick — uses "quickstart" directly |
| 2 | Wait for pipeline | Pipeline runs with quickstart template |
| 3 | Completion | H1 should be `Quickstart: <verb> <noun>` format |

**Repeat for each doc type:** `tutorial`, `how-to`, `concept`, `overview`

### TC-07: Generate without prior analyze

| Step | Action | Expected result |
|------|--------|-----------------|
| 1 | Start a fresh chat session | |
| 2 | Type `@video-documenter /generate` | Error: "No analyzed video found" with `/analyze` instructions |

### TC-08: Refine with /refine command

| Step | Action | Expected result |
|------|--------|-----------------|
| 1 | After TC-05 completes, type `@video-documenter /refine Make the introduction shorter and more direct` | Progress: "Refining document..." |
| 2 | Wait for refinement | Updated doc preview shown |
| 3 | Check the saved file | File content updated with refined version |

**Verify:**
- Revision number incremented in the response table
- Changes reflect the feedback (introduction should be shorter)

### TC-09: Refine with free-form text

| Step | Action | Expected result |
|------|--------|-----------------|
| 1 | After TC-05, type `@video-documenter Add a troubleshooting section at the end` | "Treating your message as refinement feedback..." |
| 2 | Wait for refinement | Document updated with troubleshooting section |

### TC-10: Refine without prior generate

| Step | Action | Expected result |
|------|--------|-----------------|
| 1 | Start fresh, type `@video-documenter /refine fix the intro` | Error: "No document to refine" with `/generate` instructions |

### TC-11: Status command

| Step | Action | Expected result |
|------|--------|-----------------|
| 1 | After analyzing a video, type `@video-documenter /status` | Status table with Video ID, stage, step/total_steps, status |
| 2 | During pipeline generation, type `/status` | Shows current stage and step (e.g., "extracting — step 2/6") |
| 3 | In a fresh session, type `/status` | "No active processing jobs" message |

### TC-12: Save command

| Step | Action | Expected result |
|------|--------|-----------------|
| 1 | After generating a doc, type `@video-documenter /save C:\temp\output.md` | Document saved to `C:\temp\output.md`, confirmation shown |
| 2 | Type `@video-documenter /save` (no path) | File save dialog opens |
| 3 | Type `@video-documenter save this to ~/docs/` | Intent classified as "save", document saved to resolved path |
| 4 | Without a generated doc, type `@video-documenter /save C:\temp\out.md` | Error: "No document to save" with `/generate` instructions |

**Verify:**
- Saved file is valid Markdown matching the generated doc
- Path with spaces works (e.g., `C:\Users\My Name\docs\`)
- Relative paths resolve against workspace root

### TC-13: Conversation / general question

| Step | Action | Expected result |
|------|--------|-----------------|
| 1 | Type `@video-documenter What document types do you support?` | LLM response explaining the 5 types |
| 2 | Type `@video-documenter How do I use this extension?` | LLM response mentioning commands |

### TC-14: Extension settings

| Step | Action | Expected result |
|------|--------|-----------------|
| 1 | Open Settings → search "video-documenter" | 3 settings visible: `backendUrl`, `outputDirectory`, `autoOpenPreview` |
| 2 | Change `outputDirectory` to `my-docs` | |
| 3 | Generate a document | Saved to `<workspace>/my-docs/` instead of `docs/` |
| 4 | Set `autoOpenPreview` to `false` | |
| 5 | Generate a document | File opens in editor but no preview pane |

### TC-14: Backend URL configuration

| Step | Action | Expected result |
|------|--------|-----------------|
| 1 | Start backend on port 9000: `uvicorn src.main:app --port 9000` | |
| 2 | Change setting `backendUrl` to `http://localhost:9000` | |
| 3 | Type `/analyze` with a video | Should connect to port 9000 successfully |

---

## Error handling scenarios

### TC-15: Invalid video file

| Step | Action | Expected result |
|------|--------|-----------------|
| 1 | Type `@video-documenter /analyze C:\path\to\document.pdf` | Path not detected (wrong extension), file picker shown |
| 2 | Rename a `.txt` file to `.mp4` and analyze it | Backend returns error — extension shows error message |

### TC-16: Very long video

| Step | Action | Expected result |
|------|--------|-----------------|
| 1 | Analyze a 30+ minute video | Ingestion takes longer but completes within 5 min timeout |
| 2 | Generate a document | Pipeline may take 5–10 minutes; should not time out (10 min limit) |

### TC-17: Cancel during processing

| Step | Action | Expected result |
|------|--------|-----------------|
| 1 | Start `/analyze`, then click Stop in chat | Processing stops cleanly, state resets to idle |
| 2 | Start `/generate`, then click Stop | State reverts to `analyzed` (not stuck in `generating`) |

### TC-18: Network errors

| Step | Action | Expected result |
|------|--------|-----------------|
| 1 | Set `backendUrl` to `http://localhost:9999` (nothing running) | `/analyze` shows "Backend not running" error |
| 2 | Start backend, begin analyzing, then kill backend mid-processing | Polling errors handled gracefully, eventually times out |

---

## Output quality checks

These verify that the generated documentation meets MS Learn standards. Run after any successful TC-05 or TC-06.

### QC-01: YAML frontmatter

- [ ] `title:` present, 43–59 characters
- [ ] `description:` present, 75–300 characters
- [ ] `ms.topic:` matches selected doc type (`quickstart`, `tutorial`, `how-to`, `concept-article`, `overview`)
- [ ] `ms.custom: ai-assisted` present
- [ ] `ms.date:` in `MM/DD/YYYY` format

### QC-02: Document structure

- [ ] H1 follows doc type convention (e.g., `Quickstart: <verb> <noun>`)
- [ ] H2 sections are not numbered
- [ ] Headings use sentence case (not Title Case)
- [ ] Steps are numbered (for procedural docs)
- [ ] No more than 12 steps per procedure

### QC-03: MS Learn voice

- [ ] Uses contractions (it's, you'll, you're)
- [ ] Uses "sign in" not "log in"
- [ ] Concise sentences, no unnecessary filler
- [ ] Addresses the reader as "you"

### QC-04: Markdown extensions

- [ ] Images use `:::image type="content" source="..." alt-text="...":::` syntax
- [ ] Alerts use `> [!NOTE]` / `> [!TIP]` syntax (not standard blockquotes)
- [ ] Code blocks have language identifiers

### QC-05: Grounding

- [ ] Every step described in the doc is visible in the video
- [ ] No fabricated steps or hallucinated UI elements
- [ ] Screenshots/keyframe references correspond to actual video content

---

## Test completion checklist

After running through the scenarios:

- [ ] All TC-01 through TC-14 pass (core functionality)
- [ ] At least 2 error scenarios tested (TC-15 through TC-18)
- [ ] Output quality checked for at least 2 different doc types (QC-01 through QC-05)
- [ ] No unhandled exceptions in the Extension Development Host debug console
- [ ] No unhandled exceptions in the backend terminal

### Recording results

Note the date, VS Code version, and which test video was used. If a test fails, create a GitHub issue with:
- Test case ID (e.g., TC-05)
- Steps to reproduce
- Expected vs. actual result
- Backend log output (if relevant)
