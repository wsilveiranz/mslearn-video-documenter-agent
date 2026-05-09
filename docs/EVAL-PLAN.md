# Evaluation plan

This document describes the evaluation strategy for each agent in the video-to-documentation pipeline. All eval tests live in `backend/tests/eval/` and run against a real test video (`test_videos/CloneToStandard-ShortDemo.mp4`).

## Quick reference

```bash
cd backend

# Run all evals
pytest tests/eval/ -v -s -m eval

# By category
pytest tests/eval/ -v -s -m "eval and local"    # FFmpeg + Whisper (no LLM cost)
pytest tests/eval/ -v -s -m "eval and cloud"    # Azure AI Foundry (LLM cost)

# Individual agent
pytest tests/eval/test_eval_<agent>.py -v -s

# Custom video
pytest tests/eval/ -v -s --video path/to/video.mp4

# Artifacts saved to backend/tests/eval/output/
```

## Pipeline flow and chaining

Each eval test saves its output as JSON in `tests/eval/output/`. Downstream tests load real upstream artifacts when available, falling back to synthetic fixtures from `tests/eval/fixtures.py`.

```
test_eval_ingestion.py   → ingestion_result.json
test_eval_extraction.py  → extraction_result.json
test_eval_structure.py   → document_outline.json
test_eval_writer.py      → generated_document.json  +  generated_document.md
test_eval_editor.py      → edited_document.json     +  edited_document.md
test_eval_evaluate.py    → evaluation_report.json
test_eval_pipeline.py    → pipeline_document.json/md +  pipeline_evaluation.json
```

Tests can run independently (using synthetic fixtures) or sequentially (chaining real data). Running the full suite chains automatically.

---

## 1. Ingestion Agent

**File:** `test_eval_ingestion.py` · **Markers:** `eval`, `local` · **LLM calls:** None

**What it tests:** Accepts a video file path, validates it, probes metadata with FFmpeg, and returns an `IngestionResult`.

| Grader | Type | What it checks |
|--------|------|----------------|
| `video_id` not empty | Assertion | Agent assigns a unique ID |
| `duration_seconds > 0` | Assertion | FFmpeg probed valid duration |
| `resolution_width > 0` | Assertion | FFmpeg probed valid resolution |
| `resolution_height > 0` | Assertion | FFmpeg probed valid resolution |
| `fps > 0` | Assertion | FFmpeg probed valid framerate |
| `file_size_bytes > 0` | Assertion | File size was read correctly |

### What's not evaluated

- Invalid file handling (corrupt video, unsupported codec, empty file)
- Large file handling (>1 GB)
- Network/URL source ingestion (Phase 3)
- Blob upload staging (Phase 3)

---

## 2. Extraction Agent

**File:** `test_eval_extraction.py` · **Markers:** `eval`, `local` · **LLM calls:** None (vision analysis skipped, `foundry_client=None`)

**What it tests:** Orchestrates FFmpeg audio extraction → Whisper transcription + PySceneDetect scene detection (parallel) → keyframe extraction → result assembly.

| Grader | Type | What it checks |
|--------|------|----------------|
| `len(transcript) > 0` | Assertion | Whisper returned at least one segment |
| `len(scenes) > 0` | Assertion | Scene detection found at least one scene |
| `len(keyframes) > 0` | Assertion | FFmpeg extracted at least one frame |

### What's not evaluated

- Transcript accuracy (word error rate vs ground truth)
- Transcript timestamp alignment (are segment boundaries correct?)
- Scene boundary accuracy (do detected cuts match actual scene changes?)
- Keyframe quality (are the selected frames representative?)
- Vision analysis (GPT-4o keyframe descriptions) — skipped when `foundry_client=None`
- OCR extraction accuracy
- Videos with no speech (music-only, silent demos)
- Non-English audio
- Long videos (>10 minutes)
- Multiple speakers / speaker diarization

---

## 3. Structure Agent

**File:** `test_eval_structure.py` · **Markers:** `eval`, `cloud` · **LLM calls:** 1–2 (GPT-4o-mini)

**What it tests:** Takes `ExtractionResult`, maps it to a `DocumentOutline` with MS Learn template structure.

| Grader | Type | What it checks |
|--------|------|----------------|
| `len(sections) >= 3` | Assertion | Outline has enough sections |
| Title length 30–80 chars | Heuristic | Relaxed from MS Learn 43–59 spec |
| Description length 50–350 chars | Heuristic | Relaxed from MS Learn 75–300 spec |
| Has H1 heading | Structural | At least one level-1 section |
| Has ≥2 H2 headings | Structural | Multiple level-2 sections |
| Tutorial title contains "tutorial" | Format | Doc type-specific title format |

### What's not evaluated

- Section-to-scene mapping accuracy (are sections grounded in the right video segments?)
- Screenshot selection quality (are the chosen keyframes relevant to each section?)
- Outline completeness (does the outline cover all video topics?)
- Content hint quality (are hints useful for the Writer?)
- Different doc types (only `tutorial` is tested; `quickstart`, `how-to`, `concept`, `overview` are not)
- Frontmatter field population (`ms.service`, `customer_intent` are generated but not validated)
- Strict MS Learn title/description length compliance (currently relaxed)

---

## 4. Writer Agent

**File:** `test_eval_writer.py` · **Markers:** `eval`, `cloud` · **LLM calls:** 1–2 (GPT-4o)

**What it tests:** Takes `DocumentOutline` + `ExtractionResult`, generates full Markdown in MS Learn format.

| Grader | Type | What it checks |
|--------|------|----------------|
| Has YAML frontmatter | Structural | Content starts with `---` |
| Has `title:` in frontmatter | Structural | Required metadata present |
| Has `ms.topic:` | Structural | Required metadata present |
| Has H1 heading | Structural | `# ` heading present |
| Has ≥2 H2 headings | Structural | Multiple `## ` sections |
| Word count > 200 | Heuristic | Substantial content generated |
| Has image references | Structural | `:::image` syntax present |
| Has code blocks | Structural | Triple-backtick blocks present |
| No placeholder text | Negative | No "placeholder" or "coming in phase" strings |

### What's not evaluated

- Content accuracy (does the text match what happened in the video?)
- Grounding verification (are steps traceable to transcript/keyframes?)
- MS Learn voice compliance (contractions, sentence case, serial comma)
- Step count per procedure (MS Learn limit: ≤12 steps)
- Image alt-text quality
- Frontmatter metadata correctness (ms.date format, ms.service value)
- Cross-reference validity (links to other articles)
- Word count upper bound (too-verbose articles)
- Markdown validity (do all code fences close? are headings properly nested?)

---

## 5. Editor Agent

**File:** `test_eval_editor.py` · **Markers:** `eval`, `cloud` · **LLM calls:** 1 (GPT-4o-mini)

**What it tests:** Takes a `GeneratedDocument`, refines it for MS Learn style compliance.

| Grader | Type | What it checks |
|--------|------|----------------|
| Revision incremented | Assertion | `revision_number` > original |
| Content not empty | Length | >100 characters |
| Content not truncated | Ratio | Refined words > 50% of original |
| Still has frontmatter | Structural | Content starts with `---` |
| Still has H1 | Structural | `# ` heading present |

### What's not evaluated

- Style improvement measurement (did specific style issues actually get fixed?)
- Feedback-driven editing (test only runs without evaluation feedback)
- Content preservation (are all original sections still present?)
- Semantic equivalence (did the meaning change during editing?)
- MS Learn-specific fixes: contractions added? sentence case applied? serial comma? "sign in" not "log in"?
- Truncation regression testing (editor truncation guard is tested indirectly, not explicitly)
- Multiple edit passes (only one refinement pass is tested)

---

## 6. Evaluate Agent

**File:** `test_eval_evaluate.py` · **Markers:** `eval`, `cloud` · **LLM calls:** 1–2 (GPT-4o)

**What it tests:** Takes a `GeneratedDocument` + `ExtractionResult`, scores across four dimensions, returns an `EvaluationReport`.

### Scoring dimensions (0.0 – 1.0)

| Dimension | Definition |
|-----------|------------|
| **Completeness** | Are all video steps represented in the document? |
| **Accuracy** | Does the text match what's shown/said in the video? |
| **Style compliance** | Does it follow MS Learn voice, tone, and formatting? |
| **Readability** | Is it scannable, concise, and well-structured? |

**Pass criteria:** Overall ≥ 0.7 AND no individual dimension < 0.5.

| Grader | Type | What it checks |
|--------|------|----------------|
| All scores in 0–1 range | Assertion | LLM returned valid numbers |
| Overall > 0 | Assertion | Not a parsing-failure fallback (all 0.5) |
| Has summary | Length | Summary text > 10 chars |
| Scores not all identical | Diversity | Dimensions are scored independently |

### What's not evaluated

- Evaluator accuracy (does the LLM evaluator agree with human judgment?)
- Inter-rater reliability (consistency across multiple runs on same document)
- Calibration (are 0.8 documents really better than 0.6 documents?)
- Suggestion actionability (can the Editor actually use the suggestions?)
- Feedback loop effectiveness (does the edit→evaluate cycle improve scores?)
- Edge cases: empty documents, very long documents, non-English content
- Dimension weighting (currently equal weight — is that appropriate?)

---

## 7. Full Pipeline

**File:** `test_eval_pipeline.py` · **Markers:** `eval`, `integration` · **LLM calls:** 5–10+ (runs all LLM agents + revision loop)

**What it tests:** End-to-end pipeline: video file → Ingestion → Extraction → Structure → Writer → Editor → Evaluate → output with revision loop.

| Grader | Type | What it checks |
|--------|------|----------------|
| Pipeline produces output | Assertion | `get_outputs()` returns at least one result |
| Word count > 100 | Heuristic | Document has substantial content |
| Overall quality score > 0 | Heuristic | Evaluation didn't fail |

### What's not evaluated

- Revision loop effectiveness (does score improve across iterations?)
- Pipeline timing / performance (how long does each stage take?)
- Error recovery (what happens when one stage fails?)
- Cloud mode (only local mode is tested)
- Multiple doc types from the same video
- Different video lengths and content types
- Resource cleanup (temp files, extracted frames)
- Concurrent pipeline runs

---

## Synthetic fixtures

`tests/eval/fixtures.py` provides deterministic test data for standalone agent evaluation:

| Fixture | Used by | Description |
|---------|---------|-------------|
| `make_extraction_result()` | Structure, Writer, Evaluate | 8 transcript segments, 3 scenes, 4 keyframes, 3 OCR entries |
| `make_document_outline()` | Writer | 7-section tutorial outline with scene mappings |
| `make_generated_document()` | Editor, Evaluate | Full markdown document with **intentional style issues** (capitalization, numbering) |

---

## Grader taxonomy

Current evaluations use three types of graders:

| Type | Description | Example |
|------|-------------|---------|
| **Assertion** | Hard pass/fail on a required property | `len(transcript) > 0` |
| **Structural** | Checks presence of expected document elements | Has YAML frontmatter, has H1 |
| **Heuristic** | Numeric threshold with relaxed bounds | Word count > 200, title 30–80 chars |

### Rule-based style graders (implemented)

`tests/eval/graders.py` provides 8 rule-based grader functions that check MS Learn style compliance. Each returns a list of `StyleFinding` objects with severity levels: `error` (hard fail), `warning` (should fix), `info` (nice to have).

| Grader | Checks | Severity |
|--------|--------|----------|
| `check_frontmatter` | YAML frontmatter present, required fields (`title`, `description`, `ms.topic`, `ms.date`), title length 43–59, description length 75–300 | error / warning |
| `check_headings` | Sentence case (not Title Case), no numbered headings, H1 present | error / warning |
| `check_voice_and_tone` | Contraction opportunities (`do not` → `don't`, etc.) | info |
| `check_terminology` | "select" not "click", "sign in" not "log in", "earlier" not "above", wordy phrases | warning |
| `check_markdown_extensions` | `:::image` syntax instead of `![](...)`, alert syntax (`> [!NOTE]`), code block language identifiers | warning |
| `check_structure` | Max 12 steps per procedure, prerequisites before steps, next-steps section present | warning |
| `check_serial_comma` | Oxford comma in lists of 3+ items | info |
| `check_grounding` | Transcript term coverage (≥30%), phrase coverage, stop-word filtering | error / info |

**Style tests:** `test_eval_style.py` — runs style graders against writer, editor, and pipeline output.
**Grounding tests:** `test_eval_grounding.py` — verifies document content is traceable to video transcript.
**Grader unit tests:** `test_graders.py` — 23 tests validating grader correctness against known-good and known-bad content.

### Missing grader types (not yet implemented)

| Type | Description | Would address |
|------|-------------|---------------|
| **LLM-as-judge** | A second LLM scores the output against criteria | Style compliance, content accuracy, grounding |
| **Reference comparison** | Diff against a gold-standard expected output | Writer accuracy, editor correctness |
| **Semantic similarity** | Embedding distance between video transcript and generated text | Grounding / hallucination detection |
| **Human-in-the-loop** | Log outputs for manual review with accept/reject | Calibrate LLM-as-judge scores |

---

## Test matrix coverage

```
                   ┌──────────┬──────────┬───────────┬──────────┬─────────┐
                   │ Tutorial │Quickstart│  How-to   │ Concept  │Overview │
┌──────────────────┼──────────┼──────────┼───────────┼──────────┼─────────┤
│ Local mode       │    ✅    │    ❌    │    ❌     │    ❌    │   ❌    │
│ Cloud mode       │    ❌    │    ❌    │    ❌     │    ❌    │   ❌    │
│ Short video (<2m)│    ✅    │    ❌    │    ❌     │    ❌    │   ❌    │
│ Long video (>10m)│    ❌    │    ❌    │    ❌     │    ❌    │   ❌    │
│ No speech        │    ❌    │    ❌    │    ❌     │    ❌    │   ❌    │
│ Non-English      │    ❌    │    ❌    │    ❌     │    ❌    │   ❌    │
│ Multi-speaker    │    ❌    │    ❌    │    ❌     │    ❌    │   ❌    │
│ With vision      │    ❌    │    ❌    │    ❌     │    ❌    │   ❌    │
└──────────────────┴──────────┴──────────┴───────────┴──────────┴─────────┘
```

---

## Artifacts reference

All artifacts are saved to `backend/tests/eval/output/` and are gitignored.

| File | Producer | Format |
|------|----------|--------|
| `ingestion_result.json` | Ingestion | `IngestionResult` model |
| `extraction_result.json` | Extraction | `ExtractionResult` model |
| `document_outline.json` | Structure | `DocumentOutline` model |
| `generated_document.json` | Writer | `GeneratedDocument` model |
| `generated_document.md` | Writer | Raw Markdown output |
| `edited_document.json` | Editor | `GeneratedDocument` model (refined) |
| `edited_document.md` | Editor | Raw Markdown output (refined) |
| `evaluation_report.json` | Evaluate | `EvaluationReport` model |
| `pipeline_document.json` | Pipeline | `GeneratedDocument` model |
| `pipeline_document.md` | Pipeline | Raw Markdown output |
| `pipeline_evaluation.json` | Pipeline | `EvaluationReport` model |

---

## Evaluation roadmap

This phased roadmap progressively adds more sophisticated evaluation capabilities.

### Phase 1 — Rule-based graders ✅ (current)

Deterministic, fast, zero LLM cost. Run on every CI build.

- [x] YAML frontmatter validation (required fields, title/description length)
- [x] Heading style checks (sentence case, no numbering, H1 presence)
- [x] MS Learn voice and tone (contraction opportunities)
- [x] Terminology enforcement ("select" not "click", "sign in" not "log in")
- [x] Markdown extension validation (`:::image`, alerts, code block languages)
- [x] Document structure (step count, prerequisites, next-steps)
- [x] Grammar checks (serial comma detection)
- [x] Transcript grounding (term + phrase coverage ≥30%)
- [x] 23 unit tests for grader correctness

### Phase 2 — LLM-as-judge + reference comparison

Requires multiple test videos and gold-standard reference documents. Higher cost per run — use as nightly or pre-release gate.

- [ ] **LLM-as-judge evaluator** — GPT-4o scores documents against a rubric (accuracy, completeness, voice compliance) on a 1–5 scale with written justification
- [ ] **Reference document comparison** — Diff generated output against a human-authored reference document for the same video; measure ROUGE/BLEU-style overlap
- [ ] **Step-by-step grounding** — Verify each numbered step in the output maps to a specific transcript segment or keyframe; flag steps with no evidence
- [ ] **Cross-doc-type consistency** — Run the same video through all 5 doc types (tutorial, quickstart, how-to, concept, overview) and verify each follows its template rules
- [ ] **Multi-video test corpus** — Expand test suite beyond single demo video: add a coding tutorial, an Azure portal walkthrough, a CLI-heavy demo, and a silent UI demo
- [ ] **Semantic similarity scoring** — Use embedding models to measure cosine similarity between transcript chunks and corresponding document sections

### Phase 3 — Calibration and consistency

Requires Phase 2 data to calibrate. Focus on reliability and human alignment.

- [ ] **Inter-run consistency** — Run the same video 5× and measure output variance (scores, structure, content overlap); flag non-deterministic quality
- [ ] **Human-in-the-loop calibration** — Collect human accept/reject ratings on 20+ generated documents; compare with LLM-as-judge scores; tune rubric until correlation >0.8
- [ ] **Evaluator accuracy audit** — Test whether the Evaluate agent's scores agree with the LLM-as-judge (Phase 2) and human ratings (Phase 3)
- [ ] **Regression detection** — Track evaluation scores over time; alert when a prompt or model change degrades output quality by >5%
- [ ] **Suggestion actionability** — Measure how many Evaluate agent suggestions the Editor actually implements, and whether implemented suggestions improve scores
