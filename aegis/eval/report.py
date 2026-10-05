"""Render evaluation reports as JSON and Markdown."""

from __future__ import annotations

from pathlib import Path

from aegis.eval.models import EvalReport

REPORT_JSON = "report.json"
REPORT_MARKDOWN = "report.md"


def render_markdown(report: EvalReport) -> str:
    """Render the report as a Markdown table."""

    lines = [
        "# Evaluation report",
        "",
        f"- Generated at: {report.generated_at}",
        f"- Golden set: `{report.golden_path}`",
        f"- Items: {report.item_count}",
        "",
        "| Detector | Language | Precision | Recall | F1 | TP | FP | FN | TN | Support |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for detector, languages in sorted(report.detectors.items()):
        for language, metrics in sorted(languages.items()):
            lines.append(
                f"| {detector} | {language} | {metrics.precision:.4f} | {metrics.recall:.4f} "
                f"| {metrics.f1:.4f} | {metrics.tp} | {metrics.fp} | {metrics.fn} "
                f"| {metrics.tn} | {metrics.support} |"
            )
    lines.append("")
    return "\n".join(lines)


def write_report(report: EvalReport, out_dir: Path) -> tuple[Path, Path]:
    """Write JSON and Markdown reports and return their paths."""

    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / REPORT_JSON
    markdown_path = out_dir / REPORT_MARKDOWN
    json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, markdown_path
