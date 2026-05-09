"""Rule-based MS Learn style graders.

Deterministic checks for Microsoft Learn documentation style compliance.
Each grader returns a list of findings — violations found in the document.

Usage:
    from tests.eval.graders import run_all_style_checks

    findings = run_all_style_checks(markdown_content, doc_type="tutorial")
    for f in findings:
        print(f"{f.severity} [{f.rule}] {f.message}")
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class StyleFinding:
    """A single style rule violation."""

    rule: str
    category: str
    severity: str  # "error", "warning", "info"
    message: str
    line: int | None = None
    suggestion: str | None = None


@dataclass
class StyleReport:
    """Aggregated style check results."""

    findings: list[StyleFinding] = field(default_factory=list)

    @property
    def errors(self) -> list[StyleFinding]:
        return [f for f in self.findings if f.severity == "error"]

    @property
    def warnings(self) -> list[StyleFinding]:
        return [f for f in self.findings if f.severity == "warning"]

    @property
    def passed(self) -> bool:
        return len(self.errors) == 0

    def by_category(self, category: str) -> list[StyleFinding]:
        return [f for f in self.findings if f.category == category]

    def summary(self) -> str:
        counts = {}
        for f in self.findings:
            counts[f.severity] = counts.get(f.severity, 0) + 1
        parts = [f"{v} {k}s" for k, v in sorted(counts.items())]
        return f"Style check: {', '.join(parts) or 'clean'} — {'PASS' if self.passed else 'FAIL'}"


# ---------------------------------------------------------------------------
# Frontmatter checks
# ---------------------------------------------------------------------------

def _extract_frontmatter(content: str) -> tuple[str, dict[str, str]]:
    """Extract YAML frontmatter as raw text and key-value dict."""
    match = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
    if not match:
        return "", {}
    raw = match.group(1)
    fields: dict[str, str] = {}
    for line in raw.split("\n"):
        line = line.strip()
        if line.startswith("#") or not line:
            continue
        kv = line.split(":", 1)
        if len(kv) == 2:
            key = kv[0].strip().strip('"').strip("'")
            val = kv[1].strip().strip('"').strip("'")
            fields[key] = val
    return raw, fields


def check_frontmatter(content: str, doc_type: str = "tutorial") -> list[StyleFinding]:
    """Validate YAML frontmatter fields."""
    findings: list[StyleFinding] = []
    raw, fields = _extract_frontmatter(content)

    if not raw:
        findings.append(StyleFinding(
            rule="frontmatter-present",
            category="frontmatter",
            severity="error",
            message="Document has no YAML frontmatter (---...---)",
        ))
        return findings

    # Required fields
    required = ["title", "description", "ms.topic"]
    for key in required:
        if key not in fields and key.replace(".", "_") not in fields:
            findings.append(StyleFinding(
                rule=f"frontmatter-{key}",
                category="frontmatter",
                severity="error",
                message=f"Missing required frontmatter field: {key}",
            ))

    # Title length (43-59 chars)
    title = fields.get("title", "")
    if title:
        title_len = len(title)
        if title_len < 43:
            findings.append(StyleFinding(
                rule="frontmatter-title-length",
                category="frontmatter",
                severity="warning",
                message=f"Title is {title_len} chars (recommended: 43-59): \"{title}\"",
            ))
        elif title_len > 59:
            findings.append(StyleFinding(
                rule="frontmatter-title-length",
                category="frontmatter",
                severity="warning",
                message=f"Title is {title_len} chars (recommended: 43-59): \"{title}\"",
            ))

    # Description length (75-300 chars)
    desc = fields.get("description", "")
    if desc:
        desc_len = len(desc)
        if desc_len < 75:
            findings.append(StyleFinding(
                rule="frontmatter-desc-length",
                category="frontmatter",
                severity="warning",
                message=f"Description is {desc_len} chars (recommended: 75-300)",
            ))
        elif desc_len > 300:
            findings.append(StyleFinding(
                rule="frontmatter-desc-length",
                category="frontmatter",
                severity="warning",
                message=f"Description is {desc_len} chars (recommended: 75-300)",
            ))

    # ms.topic value
    topic = fields.get("ms.topic") or fields.get("ms_topic", "")
    expected_topics = {
        "tutorial": "tutorial",
        "quickstart": "quickstart",
        "how-to": "how-to",
        "howto": "how-to",
        "concept": "concept-article",
        "overview": "overview",
    }
    if topic and doc_type in expected_topics:
        if topic != expected_topics[doc_type]:
            findings.append(StyleFinding(
                rule="frontmatter-ms-topic",
                category="frontmatter",
                severity="warning",
                message=f"ms.topic is \"{topic}\", expected \"{expected_topics[doc_type]}\" for {doc_type}",
            ))

    # ai-assisted marker
    custom = fields.get("ms.custom") or fields.get("ms_custom", "")
    ai_usage = fields.get("ai-usage", "")
    if "ai-assisted" not in custom and "ai-assisted" not in ai_usage:
        findings.append(StyleFinding(
            rule="frontmatter-ai-assisted",
            category="frontmatter",
            severity="warning",
            message="Missing ms.custom: ai-assisted (or ai-usage: ai-assisted)",
        ))

    # ms.date format
    date = fields.get("ms.date") or fields.get("ms_date", "")
    if date and not re.match(r'^\d{2}/\d{2}/\d{4}$', date):
        findings.append(StyleFinding(
            rule="frontmatter-date-format",
            category="frontmatter",
            severity="warning",
            message=f"ms.date \"{date}\" should be MM/DD/YYYY format",
        ))

    return findings


# ---------------------------------------------------------------------------
# Heading checks
# ---------------------------------------------------------------------------

def _extract_headings(content: str) -> list[tuple[int, int, str]]:
    """Extract headings as (line_number, level, text) tuples."""
    headings: list[tuple[int, int, str]] = []
    # Skip frontmatter
    body = re.sub(r'^---\n.*?\n---\n', '', content, flags=re.DOTALL)
    for i, line in enumerate(body.split("\n"), start=1):
        match = re.match(r'^(#{1,6})\s+(.+)$', line)
        if match:
            level = len(match.group(1))
            text = match.group(2).strip()
            headings.append((i, level, text))
    return headings


# Common proper nouns / acronyms that should stay capitalized
_PROPER_NOUNS = {
    "Azure", "Microsoft", "Windows", "Linux", "macOS", "SQL", "API", "APIs",
    "REST", "HTTP", "HTTPS", "URL", "URLs", "CLI", "SDK", "VS", "Code",
    "Docker", "Kubernetes", "Git", "GitHub", "ARM", "JSON", "YAML", "XML",
    "OAuth", "JWT", "DNS", "IP", "TCP", "UDP", "SSH", "SSL", "TLS",
    "DevOps", "App", "Web", "Cloud", "AI", "ML", "GPT", "OpenAI",
    "Node.js", "Python", "Java", "C#", ".NET", "TypeScript", "JavaScript",
    "PowerShell", "Bash", "Terraform", "Bicep", "Redis", "Cosmos",
    "Blob", "Queue", "Table", "Functions", "Logic", "Apps", "Service",
    "Storage", "Container", "Registry", "Hub", "IoT",
}


def _is_sentence_case(heading: str) -> bool:
    """Check if heading is in sentence case (first word + proper nouns capitalized)."""
    # Strip doc type prefix ("Tutorial: ", "Quickstart: ")
    text = re.sub(r'^(Tutorial|Quickstart|How-to|What is)\s*:?\s*', '', heading)
    if not text:
        return True
    words = text.split()
    for i, word in enumerate(words):
        clean = word.strip("()[]{}.,;:!?\"'`")
        if not clean:
            continue
        if i == 0:
            continue  # First word can be capitalized
        if clean in _PROPER_NOUNS:
            continue  # Known proper nouns
        if clean[0].isupper() and clean.lower() != clean and len(clean) > 1:
            # Capitalized word that's not a proper noun
            if not clean.isupper():  # Skip ALL-CAPS acronyms
                return False
    return True


def check_headings(content: str, doc_type: str = "tutorial") -> list[StyleFinding]:
    """Check heading style: sentence case, no gerunds in H1, no numbered H2s."""
    findings: list[StyleFinding] = []
    headings = _extract_headings(content)

    if not headings:
        findings.append(StyleFinding(
            rule="heading-present",
            category="headings",
            severity="error",
            message="Document has no headings",
        ))
        return findings

    for line_num, level, text in headings:
        # H1 checks
        if level == 1:
            # H1 format by doc type
            h1_patterns = {
                "tutorial": r'^Tutorial:\s+\S',
                "quickstart": r'^Quickstart:\s+\S',
                "concept": r'^What is\s+',
                "overview": r'^What is\s+',
            }
            if doc_type in h1_patterns and not re.match(h1_patterns[doc_type], text):
                findings.append(StyleFinding(
                    rule="heading-h1-format",
                    category="headings",
                    severity="warning",
                    message=f"H1 \"{text}\" doesn't match {doc_type} format",
                    line=line_num,
                ))

            # No gerunds in H1
            # Extract verb part after prefix
            verb_text = re.sub(r'^(Tutorial|Quickstart|What is)\s*:?\s*', '', text).strip()
            if verb_text and verb_text.split()[0].endswith("ing"):
                first_word = verb_text.split()[0]
                # Exclude words that aren't gerunds
                non_gerund_ing = {"string", "ring", "king", "thing", "bring", "spring", "using"}
                if first_word.lower() not in non_gerund_ing:
                    findings.append(StyleFinding(
                        rule="heading-h1-no-gerund",
                        category="headings",
                        severity="warning",
                        message=f"H1 starts with gerund \"{first_word}\" — use imperative verb",
                        line=line_num,
                    ))

        # H2 checks — no numbered sections
        if level == 2:
            if re.match(r'^(Step\s+)?\d+[\.\):\s]', text):
                findings.append(StyleFinding(
                    rule="heading-h2-no-numbers",
                    category="headings",
                    severity="warning",
                    message=f"H2 \"{text}\" should not be numbered",
                    line=line_num,
                ))

        # Sentence case check for all headings
        if not _is_sentence_case(text):
            findings.append(StyleFinding(
                rule="heading-sentence-case",
                category="headings",
                severity="warning",
                message=f"Heading not in sentence case: \"{text}\"",
                line=line_num,
            ))

    return findings


# ---------------------------------------------------------------------------
# Voice and terminology checks
# ---------------------------------------------------------------------------

# Contraction patterns: (expanded form, contraction)
_CONTRACTION_PATTERNS: list[tuple[str, str]] = [
    (r"\bit is\b", "it's"),
    (r"\byou will\b", "you'll"),
    (r"\byou are\b", "you're"),
    (r"\bwe are\b", "we're"),
    (r"\blet us\b", "let's"),
    (r"\bdo not\b", "don't"),
    (r"\bcannot\b", "can't"),
    (r"\bcan not\b", "can't"),
    (r"\bwill not\b", "won't"),
    (r"\bis not\b", "isn't"),
    (r"\bdoes not\b", "doesn't"),
    (r"\bwould not\b", "wouldn't"),
    (r"\bshould not\b", "shouldn't"),
    (r"\bcould not\b", "couldn't"),
    (r"\bdid not\b", "didn't"),
    (r"\bhas not\b", "hasn't"),
    (r"\bhave not\b", "haven't"),
    (r"\bwere not\b", "weren't"),
    (r"\bthat is\b", "that's"),
    (r"\bwhat is\b", "what's"),
]


def _get_body(content: str) -> str:
    """Strip frontmatter and return document body."""
    return re.sub(r'^---\n.*?\n---\n', '', content, flags=re.DOTALL)


def check_contractions(content: str) -> list[StyleFinding]:
    """Flag missing contractions in document body."""
    findings: list[StyleFinding] = []
    body = _get_body(content)

    # Exclude code blocks and headings starting with "What is" (doc type format)
    body_no_code = re.sub(r'```.*?```', '', body, flags=re.DOTALL)

    for pattern, contraction in _CONTRACTION_PATTERNS:
        matches = list(re.finditer(pattern, body_no_code, re.IGNORECASE))
        for m in matches:
            # Skip if inside heading format "What is <noun>?"
            if contraction == "what's" and re.search(r'^#+\s+What is', body_no_code[max(0, m.start()-20):m.start()+20], re.MULTILINE):
                continue
            findings.append(StyleFinding(
                rule="voice-contraction",
                category="voice",
                severity="info",
                message=f"Use contraction: \"{m.group()}\" → \"{contraction}\"",
                suggestion=contraction,
            ))

    return findings


def check_terminology(content: str) -> list[StyleFinding]:
    """Check for prohibited terminology."""
    findings: list[StyleFinding] = []
    body = _get_body(content)
    body_no_code = re.sub(r'```.*?```', '', body, flags=re.DOTALL)

    # "click" → "select"
    for m in re.finditer(r'\bclick(?:\s+on)?\b', body_no_code, re.IGNORECASE):
        findings.append(StyleFinding(
            rule="term-click",
            category="terminology",
            severity="warning",
            message=f"Use \"select\" instead of \"{m.group()}\"",
            suggestion="select",
        ))

    # "log in" / "login" → "sign in"
    for m in re.finditer(r'\blog\s*in(?:to)?\b', body_no_code, re.IGNORECASE):
        findings.append(StyleFinding(
            rule="term-login",
            category="terminology",
            severity="warning",
            message=f"Use \"sign in\" instead of \"{m.group()}\"",
            suggestion="sign in",
        ))

    # Wordy phrases
    wordy: list[tuple[str, str]] = [
        (r'\bin order to\b', "to"),
        (r'\bdue to the fact that\b', "because"),
        (r'\bat this point in time\b', "now"),
        (r'\butilize\b', "use"),
        (r'\bplease note that\b', "(remove)"),
        (r'\bit should be noted that\b', "(remove)"),
        (r'\bas you can see\b', "(remove)"),
    ]
    for pattern, replacement in wordy:
        for m in re.finditer(pattern, body_no_code, re.IGNORECASE):
            findings.append(StyleFinding(
                rule="term-wordy",
                category="terminology",
                severity="info",
                message=f"Wordy: \"{m.group()}\" → \"{replacement}\"",
                suggestion=replacement,
            ))

    return findings


# ---------------------------------------------------------------------------
# Markdown extension checks
# ---------------------------------------------------------------------------

def check_markdown_extensions(content: str) -> list[StyleFinding]:
    """Check MS Learn markdown extensions: images, alerts, code blocks."""
    findings: list[StyleFinding] = []
    body = _get_body(content)

    # Standard markdown images (should use :::image::: syntax)
    for m in re.finditer(r'!\[([^\]]*)\]\(([^)]+)\)', body):
        findings.append(StyleFinding(
            rule="md-image-syntax",
            category="markdown",
            severity="warning",
            message=f"Use :::image::: syntax instead of ![{m.group(1)}]({m.group(2)})",
        ))

    # Code blocks without language identifiers
    for m in re.finditer(r'^```\s*$', body, re.MULTILINE):
        findings.append(StyleFinding(
            rule="md-code-lang",
            category="markdown",
            severity="warning",
            message="Code block missing language identifier (```bash, ```python, etc.)",
        ))

    # Alert syntax check
    alerts = re.findall(r'>\s*\[!(\w+)\]', body)
    valid_alerts = {"NOTE", "TIP", "IMPORTANT", "CAUTION", "WARNING"}
    for alert in alerts:
        if alert.upper() not in valid_alerts:
            findings.append(StyleFinding(
                rule="md-alert-type",
                category="markdown",
                severity="warning",
                message=f"Invalid alert type: [!{alert}]. Use: {', '.join(sorted(valid_alerts))}",
            ))

    # Alert count (max 2 recommended)
    alert_count = len(alerts)
    if alert_count > 2:
        findings.append(StyleFinding(
            rule="md-alert-count",
            category="markdown",
            severity="info",
            message=f"Document has {alert_count} alerts (recommended: max 2)",
        ))

    # Image alt-text quality
    for m in re.finditer(r':::image.*?alt-text="([^"]*)"', body):
        alt = m.group(1)
        if not alt:
            findings.append(StyleFinding(
                rule="md-alt-empty",
                category="markdown",
                severity="warning",
                message="Image has empty alt-text",
            ))
        elif alt.lower().startswith(("screenshot", "image of", "picture of")):
            findings.append(StyleFinding(
                rule="md-alt-generic",
                category="markdown",
                severity="info",
                message=f"Alt-text starts with generic term: \"{alt[:50]}...\"",
                suggestion="Describe what the image shows specifically",
            ))

    return findings


# ---------------------------------------------------------------------------
# Document structure checks
# ---------------------------------------------------------------------------

def check_structure(content: str, doc_type: str = "tutorial") -> list[StyleFinding]:
    """Check document structure: prerequisites, next steps, clean up, checklist."""
    findings: list[StyleFinding] = []
    body = _get_body(content)
    headings = _extract_headings(content)
    heading_texts = [h[2].lower() for h in headings]

    # Prerequisites (required for tutorial, quickstart, how-to)
    procedural_types = {"tutorial", "quickstart", "how-to", "howto"}
    if doc_type in procedural_types:
        if not any("prerequisite" in h for h in heading_texts):
            findings.append(StyleFinding(
                rule="structure-prerequisites",
                category="structure",
                severity="warning",
                message="Missing 'Prerequisites' section (required for procedural docs)",
            ))

    # Next steps
    if not any("next step" in h for h in heading_texts):
        findings.append(StyleFinding(
            rule="structure-next-steps",
            category="structure",
            severity="info",
            message="Missing 'Next steps' section",
        ))

    # Clean up resources (tutorial, quickstart)
    cleanup_types = {"tutorial", "quickstart"}
    if doc_type in cleanup_types:
        if not any("clean up" in h or "cleanup" in h for h in heading_texts):
            findings.append(StyleFinding(
                rule="structure-cleanup",
                category="structure",
                severity="info",
                message="Missing 'Clean up resources' section (recommended for tutorials/quickstarts)",
            ))

    # Tutorial checklist
    if doc_type == "tutorial":
        if '[!div class="checklist"]' not in body:
            findings.append(StyleFinding(
                rule="structure-checklist",
                category="structure",
                severity="info",
                message="Missing checklist (recommended for tutorials)",
            ))

    # Step count per procedure (max 12)
    numbered_blocks = re.split(r'\n## ', body)
    for block in numbered_blocks:
        steps = re.findall(r'^\d+\.\s', block, re.MULTILINE)
        if len(steps) > 12:
            section_name = block.split('\n')[0].strip()
            findings.append(StyleFinding(
                rule="structure-step-count",
                category="structure",
                severity="warning",
                message=f"Section \"{section_name}\" has {len(steps)} steps (max 12 recommended)",
            ))

    # Introduction — first paragraph should orient the reader
    intro_patterns = {
        "tutorial": r"In this tutorial",
        "quickstart": r"In this quickstart",
    }
    if doc_type in intro_patterns:
        # Check the first ~500 chars of body (after H1)
        body_start = re.sub(r'^#\s+.*?\n', '', body, count=1).strip()[:500]
        if not re.search(intro_patterns[doc_type], body_start, re.IGNORECASE):
            findings.append(StyleFinding(
                rule="structure-intro",
                category="structure",
                severity="info",
                message=f"Introduction should start with \"{intro_patterns[doc_type]}...\"",
            ))

    return findings


# ---------------------------------------------------------------------------
# Serial comma check
# ---------------------------------------------------------------------------

def check_serial_comma(content: str) -> list[StyleFinding]:
    """Check for missing Oxford/serial commas in lists of 3+."""
    findings: list[StyleFinding] = []
    body = _get_body(content)
    body_no_code = re.sub(r'```.*?```', '', body, flags=re.DOTALL)

    # Pattern: "A, B and C" without comma before "and" (missing serial comma)
    # This is simplified — catches common cases
    pattern = r'\b\w+,\s+\w+(?:\s+\w+)*\s+(?:and|or)\s+\w+'
    for m in re.finditer(pattern, body_no_code):
        text = m.group()
        # Check if there's a comma before "and/or"
        if not re.search(r',\s+(?:and|or)\s+', text):
            # Report if there is at least 1 comma (pattern already matched "A, B and C")
            comma_count = text.count(",")
            if comma_count >= 1:
                findings.append(StyleFinding(
                    rule="grammar-serial-comma",
                    category="grammar",
                    severity="info",
                    message=f"Possible missing serial comma: \"{text[:60]}\"",
                ))

    return findings


# ---------------------------------------------------------------------------
# Grounding checks
# ---------------------------------------------------------------------------

def check_grounding(
    content: str,
    transcript_segments: list[str],
    min_coverage: float = 0.3,
) -> list[StyleFinding]:
    """Verify generated content is grounded in the video transcript.

    Checks what fraction of transcript key terms appear in the generated document.
    This catches hallucinated content that doesn't relate to the video.

    Args:
        content: The generated markdown document.
        transcript_segments: List of transcript segment texts.
        min_coverage: Minimum fraction of transcript terms that should appear (0-1).
    """
    findings: list[StyleFinding] = []
    if not transcript_segments:
        findings.append(StyleFinding(
            rule="grounding-no-transcript",
            category="grounding",
            severity="info",
            message="No transcript segments provided — grounding check skipped",
        ))
        return findings

    body = _get_body(content).lower()
    body_no_code = re.sub(r'```.*?```', '', body, flags=re.DOTALL)

    # Extract meaningful terms from transcript (nouns, verbs — skip stop words)
    stop_words = {
        "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "up", "about", "into", "through", "during",
        "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
        "do", "does", "did", "will", "would", "could", "should", "may", "might",
        "shall", "can", "need", "must", "it", "its", "this", "that", "these",
        "those", "i", "you", "he", "she", "we", "they", "my", "your", "his",
        "her", "our", "their", "what", "which", "who", "whom", "how", "when",
        "where", "why", "not", "no", "so", "if", "then", "than", "too", "very",
        "just", "also", "now", "here", "there", "all", "each", "every", "both",
        "some", "any", "most", "other", "new", "first", "last", "next", "get",
        "go", "going", "see", "want", "click", "select", "um", "uh", "like",
        "right", "okay", "well",
    }

    full_transcript = " ".join(transcript_segments).lower()
    transcript_words = re.findall(r'\b[a-z]{3,}\b', full_transcript)
    key_terms = {w for w in transcript_words if w not in stop_words}

    if not key_terms:
        return findings

    # Check which key terms appear in the document
    found = {term for term in key_terms if term in body_no_code}
    coverage = len(found) / len(key_terms) if key_terms else 0

    # Extract multi-word phrases from transcript (2-grams)
    bigrams: set[str] = set()
    for segment in transcript_segments:
        words = segment.lower().split()
        for i in range(len(words) - 1):
            w1, w2 = words[i], words[i + 1]
            if w1 not in stop_words and w2 not in stop_words and len(w1) >= 3 and len(w2) >= 3:
                bigrams.add(f"{w1} {w2}")

    found_bigrams = {bg for bg in bigrams if bg in body_no_code}
    bigram_coverage = len(found_bigrams) / len(bigrams) if bigrams else 0

    # Missing key terms (only report top unique ones)
    missing = key_terms - found
    # Count term frequency in transcript to find most important missing terms
    term_freq = {}
    for term in missing:
        term_freq[term] = full_transcript.count(term)
    important_missing = sorted(term_freq.items(), key=lambda x: -x[1])[:10]

    if coverage < min_coverage:
        findings.append(StyleFinding(
            rule="grounding-low-coverage",
            category="grounding",
            severity="warning",
            message=(
                f"Low transcript term coverage: {coverage:.0%} "
                f"({len(found)}/{len(key_terms)} terms found, min {min_coverage:.0%})"
            ),
        ))

    if important_missing:
        missing_str = ", ".join(f"\"{t}\" ({c}x)" for t, c in important_missing[:5])
        findings.append(StyleFinding(
            rule="grounding-missing-terms",
            category="grounding",
            severity="info",
            message=f"Key transcript terms not found in document: {missing_str}",
        ))

    # Report coverage stats
    findings.append(StyleFinding(
        rule="grounding-coverage",
        category="grounding",
        severity="info",
        message=(
            f"Grounding: {coverage:.0%} term coverage ({len(found)}/{len(key_terms)}), "
            f"{bigram_coverage:.0%} phrase coverage ({len(found_bigrams)}/{len(bigrams)})"
        ),
    ))

    return findings


# ---------------------------------------------------------------------------
# Aggregate runner
# ---------------------------------------------------------------------------

def run_all_style_checks(content: str, doc_type: str = "tutorial") -> StyleReport:
    """Run all style checks and return aggregated report."""
    report = StyleReport()
    report.findings.extend(check_frontmatter(content, doc_type))
    report.findings.extend(check_headings(content, doc_type))
    report.findings.extend(check_contractions(content))
    report.findings.extend(check_terminology(content))
    report.findings.extend(check_markdown_extensions(content))
    report.findings.extend(check_structure(content, doc_type))
    report.findings.extend(check_serial_comma(content))
    return report
