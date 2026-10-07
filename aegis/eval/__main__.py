"""Command line interface for the evaluation harness.

Usage:
    python -m aegis.eval run --golden data/golden/ --out reports/eval/
    python -m aegis.eval gate --baseline reports/eval/baseline.json

    python -m aegis.eval generate --out data/labelling/candidates.jsonl
    python -m aegis.eval sheet
    python -m aegis.eval import --sheet data/labelling/sheet.csv --annotator you
    python -m aegis.eval stats --out data/labelling/stats.json
    python -m aegis.eval sample
    python -m aegis.eval merge --reviewed data/labelling/reviewed.jsonl
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from aegis.eval import annotate
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

    generate_parser = subparsers.add_parser("generate", help="generate blind-labelling candidates")
    generate_parser.add_argument("--out", type=Path, default=annotate.DEFAULT_CANDIDATES)
    generate_parser.add_argument("--per-class", type=int, default=100)
    generate_parser.add_argument("--seed", type=int, default=7)
    generate_parser.add_argument("--vip", default="Vip Sharma")

    sheet_parser = subparsers.add_parser("sheet", help="write the shuffled blind annotation sheet")
    sheet_parser.add_argument("--candidates", type=Path, default=annotate.DEFAULT_CANDIDATES)
    sheet_parser.add_argument("--out", type=Path, default=annotate.DEFAULT_SHEET)
    sheet_parser.add_argument("--seed", type=int, default=7)

    import_parser = subparsers.add_parser("import", help="validate labels from a sheet")
    import_parser.add_argument("--sheet", type=Path, required=True)
    import_parser.add_argument("--annotator", required=True)
    import_parser.add_argument("--role", choices=["annotator", "reviewer"], default="annotator")
    import_parser.add_argument("--out", type=Path, default=None)

    stats_parser = subparsers.add_parser("stats", help="intended-vs-blind agreement")
    stats_parser.add_argument("--candidates", type=Path, default=annotate.DEFAULT_CANDIDATES)
    stats_parser.add_argument("--annotated", type=Path, default=annotate.DEFAULT_ANNOTATED)
    stats_parser.add_argument("--out", type=Path, default=None)

    sample_parser = subparsers.add_parser("sample", help="write the second-reviewer sheet")
    sample_parser.add_argument("--candidates", type=Path, default=annotate.DEFAULT_CANDIDATES)
    sample_parser.add_argument("--annotated", type=Path, default=annotate.DEFAULT_ANNOTATED)
    sample_parser.add_argument("--out", type=Path, default=annotate.DEFAULT_REVIEW_SHEET)
    sample_parser.add_argument("--fraction", type=float, default=0.25)
    sample_parser.add_argument("--seed", type=int, default=7)

    merge_parser = subparsers.add_parser("merge", help="write validated golden items")
    merge_parser.add_argument("--candidates", type=Path, default=annotate.DEFAULT_CANDIDATES)
    merge_parser.add_argument("--annotated", type=Path, default=annotate.DEFAULT_ANNOTATED)
    merge_parser.add_argument("--reviewed", type=Path, default=annotate.DEFAULT_REVIEWED)
    merge_parser.add_argument("--out-dir", type=Path, default=annotate.DEFAULT_GOLDEN_DIR)
    merge_parser.add_argument("--guideline-version", default="v1")
    merge_parser.add_argument("--sample-fraction", type=float, default=0.25)
    merge_parser.add_argument("--sample-seed", type=int, default=7)

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


def generate_command(out: Path, per_class: int, seed: int, vip: str) -> int:
    path = annotate.run_generate(out=out, per_class=per_class, seed=seed, vip=vip)
    print(f"wrote {per_class} candidates per class/language to {path}")
    return 0


def sheet_command(candidates_path: Path, out: Path, seed: int) -> int:
    candidates = annotate.load_candidates(candidates_path)
    path = annotate.write_sheet(candidates, out, seed=seed)
    print(f"wrote {len(candidates)} rows to {path}")
    return 0


def import_command(sheet_path: Path, annotator_name: str, role: str, out: Path | None) -> int:
    records = annotate.import_sheet(sheet_path, annotator=annotator_name, role=role)
    target = out or (annotate.DEFAULT_ANNOTATED if role == "annotator" else annotate.DEFAULT_REVIEWED)
    annotate.write_records(records, target)
    print(f"imported {len(records)} {role} labels to {target}")
    return 0


def stats_command(candidates_path: Path, annotated_path: Path, out: Path | None) -> int:
    candidates = annotate.load_candidates(candidates_path)
    annotated = annotate.load_records(annotated_path)
    stats = annotate.agreement_stats(candidates, annotated)
    text = json.dumps(stats, indent=2, ensure_ascii=False)
    print(text)
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    return 0


def sample_command(candidates_path: Path, annotated_path: Path, out: Path, fraction: float, seed: int) -> int:
    candidates = annotate.load_candidates(candidates_path)
    annotated = annotate.load_records(annotated_path)
    ids = annotate.review_sample_ids(candidates, annotated, fraction=fraction, seed=seed)
    path = annotate.write_review_sheet(candidates, ids, out, seed=seed)
    print(f"wrote {len(ids)} review rows to {path}")
    return 0


def merge_command(
    candidates_path: Path,
    annotated_path: Path,
    reviewed_path: Path,
    out_dir: Path,
    guideline_version: str,
    sample_fraction: float,
    sample_seed: int,
) -> int:
    summary = annotate.merge_to_golden(
        candidates=annotate.load_candidates(candidates_path),
        annotated=annotate.load_records(annotated_path),
        reviewed=annotate.load_records(reviewed_path),
        out_dir=out_dir,
        guideline_version=guideline_version,
        sample_fraction=sample_fraction,
        sample_seed=sample_seed,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        return run_command(args.golden, args.out)
    if args.command == "gate":
        return gate_command(args.baseline, args.report, args.tolerance)
    if args.command == "generate":
        return generate_command(args.out, args.per_class, args.seed, args.vip)
    if args.command == "sheet":
        return sheet_command(args.candidates, args.out, args.seed)
    if args.command == "import":
        return import_command(args.sheet, args.annotator, args.role, args.out)
    if args.command == "stats":
        return stats_command(args.candidates, args.annotated, args.out)
    if args.command == "sample":
        return sample_command(args.candidates, args.annotated, args.out, args.fraction, args.seed)
    if args.command == "merge":
        return merge_command(
            args.candidates,
            args.annotated,
            args.reviewed,
            args.out_dir,
            args.guideline_version,
            args.sample_fraction,
            args.sample_seed,
        )
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
