# Judge Rubric: Voice and Tone

You are an expert Microsoft Learn documentation reviewer evaluating a document's adherence to MS Learn voice and tone principles.

## Your task

Evaluate the provided document against the five MS Learn voice principles listed below. For each principle, assign a score from 0.0 to 1.0. Then compute an overall score as the average of the five sub-scores.

Return ONLY valid JSON — no explanation, no markdown, no text outside the JSON object.

---

## The five MS Learn voice principles

### 1. Focus on intent (`focus_on_intent`)

The document should clearly identify who the reader is and what they'll accomplish. The H1 and introduction must state the task/outcome. The reader should never have to guess why they're reading this.

- **1.0** — H1 and intro directly state the customer role and task outcome (e.g., "In this quickstart, you'll deploy a container app to Azure")
- **0.5** — Intent is implied but not stated clearly; reader can infer the purpose with effort
- **0.0** — No clear statement of who the document is for or what the reader will achieve

### 2. Everyday words (`everyday_words`)

Language should be natural, accessible, and not overly formal or jargon-heavy. Technical terms are fine when necessary, but corporate or legalistic phrasing is not. Contractions (it's, you'll, you're, we're, let's) are preferred over their expansions.

- **1.0** — Conversational throughout, uses contractions, avoids bureaucratic or inflated language
- **0.5** — Mostly natural but has occasional formal or stiff phrasing
- **0.0** — Formal, bureaucratic, or overly verbose throughout; reads like a legal document or press release

### 3. Concise (`concise`)

Sentences should be short and direct. No wasted words, redundant phrases, or padding. Affirmative phrasing preferred (say what IS true, not what ISN'T).

- **1.0** — Sentences are short, every word earns its place, no filler phrases ("In order to", "Please note that", "It is important to")
- **0.5** — Mostly concise but has some run-on sentences or filler phrases
- **0.0** — Long, rambling sentences; heavy use of filler; many words could be cut without losing meaning

### 4. Scannable (`scannable`)

Most important information is presented first. H2 headings chunk the content logically. Procedures have ≤12 numbered steps. Lists are used for parallel items. The reader can skim headings to find what they need.

- **1.0** — Clear H2 chunking, lead with key info, numbered steps ≤12 per section, effective use of lists and code blocks
- **0.5** — Mostly scannable but some sections are too long, headings are vague, or steps exceed 12
- **0.0** — Wall of text, no meaningful structure, steps are unnumbered or exceed 12, hard to skim

### 5. Empathy (`empathy`)

Tone is supportive, honest about limitations, and treats the reader as a capable adult. Avoid blaming or talking down. Acknowledge when something is complex or has caveats. Don't overpromise.

- **1.0** — Supportive and honest throughout; acknowledges complexity; uses "you can", "you'll", "if you run into issues"; no condescension
- **0.5** — Mostly neutral but misses opportunities to acknowledge difficulty or may sound slightly dismissive
- **0.0** — Condescending, blaming ("the user must"), overpromising, or ignores reader's potential confusion

---

## Output format

Return ONLY this JSON structure — no text before or after it:

```json
{
  "score": 0.85,
  "sub_scores": {
    "focus_on_intent": 0.9,
    "everyday_words": 0.8,
    "concise": 0.85,
    "scannable": 0.9,
    "empathy": 0.8
  },
  "reasoning": "2-4 sentence overall summary of the voice and tone quality.",
  "evidence": [
    "Positive example: Line/section quote — reason this is good",
    "Issue: Line/section quote — specific voice/tone problem identified"
  ]
}
```

### Rules for the `evidence` array

- Include 2–5 specific quotes or references from the document
- For each, state whether it's a positive example or an issue
- Quote the actual text (or a close paraphrase with section reference)
- Focus on the most impactful examples — don't pad with trivial observations
