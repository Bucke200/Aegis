"""Command line interface for the evaluation harness.

Usage:
    python -m aegis.eval run --golden data/golden/ --out reports/eval/
    python -m aegis.eval gate --baseline reports/eval/baseline.json
"""

from __future__ import annotations

import argparse
from pathlib import Path

from aegis.eval.dataset import load_golden
from aegis.eval.detectors import get_detectors
from aegis.eval.gate import compare_reports
from aegis.eval.models import EvalReport
from aegis.eval.report import REPORT_JSON, write_report
from aegis.eval.runner import evaluate

DEFAULT_GOLDEN = Path("data/golden")
DEFAULT_OUT = Path("reports/eval")
DEFAULT_TOLERANCE = 0.02


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aegis.eval", description="Aegis evaluation harness")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="evaluate detectors on the golden set")
    run_parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    run_parser.add_argument("--out", type=Path, default=DEFAULT_OUT)

    gate_parser = subparsers.add_parser("gate", help="compare a report against the baseline")
    gate_parser.add_argument("--baseline", type=Path, default=DEFAULT_OUT / "baseline.json")
    gate_parser.add_argument("--report", type=Path, default=DEFAULT_OUT / REPORT_JSON)
    gate_parser.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE)

    return parser


def run_command(golden_path: Path, out_dir: Path) -> int:
    items = load_golden(golden_path)
    report = evaluate(items, get_detectors(), golden_path=str(golden_path))
    json_path, markdown_path = write_report(report, out_dir)
    print(f"evaluated {len(items)} items; wrote {json_path} and {markdown_path}")
    for detector, languages in sorted(report.detectors.items()):
        overall = languages.get("all")
        if overall is not None:
            print(f"  {detector}: precision={overall.precision:.4f} recall={overall.recall:.4f} f1={overall.f1:.4f}")
    return 0


def gate_command(baseline_path: Path, report_file: Path, tolerance: float) -> int:
    baseline = EvalReport.model_validate_json(baseline_path.read_text(encoding="utf-8"))
    current = EvalReport.model_validate_json(report_file.read_text(encoding="utf-8"))
    regressions = compare_reports(baseline, current, tolerance)
    if regressions:
        print("evaluation gate FAILED:")
        for regression in regressions:
            print(f"  - {regression}")
        return 1
    print(f"evaluation gate passed (tolerance {tolerance})")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        return run_command(args.golden, args.out)
    if args.command == "gate":
        return gate_command(args.baseline, args.report, args.tolerance)
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
