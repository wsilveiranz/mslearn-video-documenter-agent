"""Evaluation score reporter — aggregates, displays, and tracks eval results."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path


@dataclass
class DimensionScore:
    """Score for a single evaluation dimension."""

    dimension: str
    score: float
    source: str = ""  # e.g., "rule-based", "llm-judge", "evaluate-agent"


@dataclass
class TestResult:
    """Result from a single evaluation test."""

    test_name: str
    doc_type: str
    video_id: str = ""
    scores: list[DimensionScore] = field(default_factory=list)
    style_errors: int = 0
    style_warnings: int = 0
    passed: bool = True
    notes: str = ""


@dataclass
class EvalRunReport:
    """Complete report for an evaluation run."""

    run_id: str
    timestamp: str
    results: list[TestResult] = field(default_factory=list)

    def add_result(self, result: TestResult) -> None:
        self.results.append(result)

    def summary_table(self) -> str:
        """Generate a formatted console summary table."""
        if not self.results:
            return "No results to display."

        # Collect all dimension names in order of first appearance
        all_dims: list[str] = []
        seen: set[str] = set()
        for r in self.results:
            for s in r.scores:
                if s.dimension not in seen:
                    all_dims.append(s.dimension)
                    seen.add(s.dimension)

        # Abbreviated column headers (max 6 chars)
        abbrev = {d: d[:6] for d in all_dims}

        # Build rows: [test_name, doc_type, *scores, style, result]
        rows: list[list[str]] = []
        dim_totals: dict[str, list[float]] = {d: [] for d in all_dims}
        style_errors_total = 0
        style_warnings_total = 0

        for r in self.results:
            score_map = {s.dimension: s.score for s in r.scores}
            row: list[str] = [r.test_name, r.doc_type]
            for d in all_dims:
                if d in score_map:
                    row.append(f"{score_map[d]:.2f}")
                    dim_totals[d].append(score_map[d])
                else:
                    row.append("  — ")
            style_cell = f"{r.style_errors}E/{r.style_warnings}W"
            row.append(style_cell)
            row.append("PASS" if r.passed else "FAIL")
            rows.append(row)
            style_errors_total += r.style_errors
            style_warnings_total += r.style_warnings

        # Aggregate row
        agg_row: list[str] = ["(aggregate)", ""]
        for d in all_dims:
            vals = dim_totals[d]
            agg_row.append(f"{sum(vals)/len(vals):.2f}" if vals else "  — ")
        agg_row.append(f"{style_errors_total}E/{style_warnings_total}W")
        pass_count = sum(1 for r in self.results if r.passed)
        agg_row.append(f"{pass_count}/{len(self.results)}")

        # Column headers
        headers = ["Test", "Doc Type"] + [abbrev[d] for d in all_dims] + ["Style", "Result"]

        # Compute column widths
        all_rows = [headers, *rows, agg_row]
        col_widths = [max(len(str(cell)) for cell in col) for col in zip(*all_rows, strict=False)]

        def fmt_row(cells: list[str], widths: list[int]) -> str:
            padded = [str(c).ljust(w) for c, w in zip(cells, widths, strict=False)]
            return "│ " + " │ ".join(padded) + " │"

        def separator(widths: list[int], left: str, mid: str, right: str, fill: str = "─") -> str:
            segments = [fill * (w + 2) for w in widths]
            return left + mid.join(segments) + right

        lines: list[str] = []
        lines.append(separator(col_widths, "┌", "┬", "┐"))
        lines.append(fmt_row(headers, col_widths))
        lines.append(separator(col_widths, "├", "┼", "┤"))
        for row in rows:
            lines.append(fmt_row(row, col_widths))
        lines.append(separator(col_widths, "├", "┼", "┤"))
        lines.append(fmt_row(agg_row, col_widths))
        lines.append(separator(col_widths, "└", "┴", "┘"))

        header = f"Eval Run: {self.run_id}  ({self.timestamp})"
        return header + "\n" + "\n".join(lines)

    def save_json(self, output_dir: Path) -> Path:
        """Save results as JSON for regression tracking."""
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"eval_run_{self.run_id}.json"
        path = output_dir / filename
        data = {
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "results": [
                {
                    "test_name": r.test_name,
                    "doc_type": r.doc_type,
                    "video_id": r.video_id,
                    "scores": {s.dimension: s.score for s in r.scores},
                    "style_errors": r.style_errors,
                    "style_warnings": r.style_warnings,
                    "passed": r.passed,
                    "notes": r.notes,
                }
                for r in self.results
            ],
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return path

    @classmethod
    def load_json(cls, path: Path) -> EvalRunReport:
        """Load a previous run report from JSON."""
        raw = json.loads(path.read_text(encoding="utf-8"))
        report = cls(run_id=raw["run_id"], timestamp=raw["timestamp"])
        for r in raw.get("results", []):
            scores = [
                DimensionScore(dimension=dim, score=score)
                for dim, score in r.get("scores", {}).items()
            ]
            result = TestResult(
                test_name=r["test_name"],
                doc_type=r["doc_type"],
                video_id=r.get("video_id", ""),
                scores=scores,
                style_errors=r.get("style_errors", 0),
                style_warnings=r.get("style_warnings", 0),
                passed=r.get("passed", True),
                notes=r.get("notes", ""),
            )
            report.add_result(result)
        return report


def compare_runs(
    current: EvalRunReport, previous: EvalRunReport, threshold: float = 0.05
) -> list[str]:
    """Compare two eval runs and return regression warnings.

    Args:
        current: The current eval run report.
        previous: A previous run report to compare against.
        threshold: Score drop threshold to flag as regression (default 5%).

    Returns:
        List of warning strings for any dimension that dropped more than threshold.
    """
    prev_map: dict[tuple[str, str], TestResult] = {
        (r.test_name, r.doc_type): r for r in previous.results
    }

    warnings: list[str] = []
    for cur in current.results:
        key = (cur.test_name, cur.doc_type)
        prev = prev_map.get(key)
        if prev is None:
            continue

        prev_scores = {s.dimension: s.score for s in prev.scores}
        for s in cur.scores:
            prev_score = prev_scores.get(s.dimension)
            if prev_score is None:
                continue
            drop = prev_score - s.score
            if drop > threshold:
                pct = drop / prev_score * 100 if prev_score else 0.0
                warnings.append(
                    f"REGRESSION: {cur.test_name} / {s.dimension} dropped "
                    f"{prev_score:.2f} → {s.score:.2f} (-{pct:.1f}%)"
                )

    return warnings


def find_latest_report(output_dir: Path) -> Path | None:
    """Find the most recent eval run JSON report in the output directory."""
    reports = sorted(output_dir.glob("eval_run_*.json"), reverse=True)
    return reports[0] if reports else None


def make_run_id() -> str:
    """Generate a run ID using the current UTC timestamp."""
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def print_summary(output_dir: Path) -> None:
    """Load the latest report and print summary + regression check."""
    latest = find_latest_report(output_dir)
    if latest is None:
        print("No evaluation reports found.")
        return

    report = EvalRunReport.load_json(latest)
    print(report.summary_table())

    reports = sorted(output_dir.glob("eval_run_*.json"), reverse=True)
    if len(reports) >= 2:
        previous = EvalRunReport.load_json(reports[1])
        warnings = compare_runs(report, previous)
        if warnings:
            print("\n⚠️  REGRESSIONS DETECTED:")
            for w in warnings:
                print(f"  {w}")
        else:
            print("\n✅ No regressions detected vs previous run.")
