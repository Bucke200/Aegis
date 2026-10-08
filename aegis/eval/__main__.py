"""Command line interface for the evaluation harness.

Usage:
    python -m aegis.eval run --golden data/private/golden --out data/private/reports/eval
    python -m aegis.eval gate --baseline data/private/reports/eval/baseline.json

    python -m aegis.eval seed-bank --out data/private/banks/hand-written.jsonl
    python -m aegis.eval draft --bank-dir data/private/banks
    python -m aegis.eval check-bank --bank-dir data/private/banks
    python -m aegis.eval generate --bank-dir data/private/banks --out data/labelling/candidates.jsonl
    python -m aegis.eval sheet
    python -m aegis.eval import --sheet data/labelling/sheet.csv --annotator you
    python -m aegis.eval stats --out data/labelling/stats.json
    python -m aegis.eval sample
    python -m aegis.eval merge --reviewed data/labelling/reviewed.jsonl
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from aegis.eval import annotate
from aegis.eval.adapters import build_detectors
from aegis.eval.bank import DEFAULT_BANK_DIR, check_bank, load_bank, write_bank
from aegis.eval.benchmark import (
    held_out,
    pairwise_benchmarks,
    run_classifications,
    score_predictions,
    write_benchmark,
)
from aegis.eval.caches import (
    DEFAULT_LLM_CACHE,
    DEFAULT_TOXICITY_CACHE,
    fetch_ollama_digest,
    refresh_llm_cache,
    refresh_toxicity_cache,
)
from aegis.eval.candidates import VIP_ROSTER, seed_bank
from aegis.eval.dataset import load_golden
from aegis.eval.gate import compare_reports
from aegis.eval.models import EvalReport
from aegis.eval.report import REPORT_JSON, write_report
from aegis.eval.runner import evaluate

DEFAULT_GOLDEN = Path("data/private/golden")
DEFAULT_OUT = Path("data/private/reports/eval")
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

    generate_parser = subparsers.add_parser("generate", help="sample blind-labelling candidates from the bank")
    generate_parser.add_argument("--out", type=Path, default=annotate.DEFAULT_CANDIDATES)
    generate_parser.add_argument("--bank-dir", type=Path, default=DEFAULT_BANK_DIR)
    generate_parser.add_argument("--per-class", type=int, default=100)
    generate_parser.add_argument("--seed", type=int, default=7)
    generate_parser.add_argument("--cells", default=None, help="comma-separated language/label cells to select")

    seed_parser = subparsers.add_parser("seed-bank", help="write the hand-written and template seed entries")
    seed_parser.add_argument("--out", type=Path, default=DEFAULT_BANK_DIR / "hand-written.jsonl")

    draft_parser = subparsers.add_parser("draft", help="draft bank entries with the candidate models")
    draft_parser.add_argument("--bank-dir", type=Path, default=DEFAULT_BANK_DIR)
    draft_parser.add_argument("--models", default="llama3.2:3b,qwen2.5:3b,gemma3:4b")
    draft_parser.add_argument("--per-model", type=int, default=3)
    draft_parser.add_argument("--attempts", type=int, default=6)
    draft_parser.add_argument("--seed", type=int, default=7)
    draft_parser.add_argument("--ollama-url", default="http://localhost:11434")
    draft_parser.add_argument("--stats-out", type=Path, default=Path("data/labelling/draft-stats.json"))

    check_parser = subparsers.add_parser("check-bank", help="report bank statistics and issues")
    check_parser.add_argument("--bank-dir", type=Path, default=DEFAULT_BANK_DIR)
    check_parser.add_argument("--out", type=Path, default=Path("data/labelling/bank-stats.json"))

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

    cache_parser = subparsers.add_parser("cache", help="refresh the committed detector caches")
    cache_parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    cache_parser.add_argument("--llm", action="store_true", help="refresh the LLM intent cache")
    cache_parser.add_argument("--toxicity", action="store_true", help="refresh the toxicity cache")
    cache_parser.add_argument("--out-llm", type=Path, default=DEFAULT_LLM_CACHE)
    cache_parser.add_argument("--out-toxicity", type=Path, default=DEFAULT_TOXICITY_CACHE)
    cache_parser.add_argument("--model", default="aegis-intent")
    cache_parser.add_argument("--ollama-url", default="http://localhost:11434")
    cache_parser.add_argument("--force", action="store_true", help="re-fetch every labelled item")

    benchmark_parser = subparsers.add_parser("benchmark", help="compare Ollama models on a labelled set")
    benchmark_parser.add_argument("--golden", type=Path, default=Path("data/private/golden"))
    benchmark_parser.add_argument("--models", required=True, help="comma-separated Ollama base models")
    benchmark_parser.add_argument("--ollama-url", default="http://localhost:11434")
    benchmark_parser.add_argument("--out", type=Path, default=Path("data/private/reports/labelling"))

    return parser


def run_command(golden_path: Path, out_dir: Path) -> int:
    items = load_golden(golden_path)
    report = evaluate(items, build_detectors(), golden_path=str(golden_path))
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


def generate_command(out: Path, per_class: int, seed: int, bank_dir: Path, cells: list[str] | None = None) -> int:
    path = annotate.run_generate(out=out, per_class=per_class, seed=seed, bank_dir=bank_dir, cells=cells)
    print(f"wrote {per_class} candidates per class/language to {path}")
    return 0


def seed_bank_command(out: Path) -> int:
    items = seed_bank()
    write_bank(items, out)
    print(f"wrote {len(items)} seed bank entries to {out}")
    return 0


def check_bank_command(bank_dir: Path, out: Path | None) -> int:
    summary = check_bank(load_bank(bank_dir)).as_dict()
    text = json.dumps(summary, indent=2, ensure_ascii=False)
    print(text)
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    return 0


def draft_command(
    bank_dir: Path,
    models: str,
    per_model: int,
    attempts: int,
    seed: int,
    ollama_url: str,
    stats_out: Path,
) -> int:
    from aegis.eval.drafting import run_drafting

    model_list = tuple(entry.strip() for entry in models.split(",") if entry.strip())
    stats = asyncio.run(
        run_drafting(
            models=model_list,
            vip_roster=VIP_ROSTER,
            bank_dir=bank_dir,
            stats_path=stats_out,
            target_per_model=per_model,
            attempts_per_model=attempts,
            ollama_url=ollama_url,
            seed=seed,
        )
    )
    print(json.dumps(stats.as_dict(), indent=2, ensure_ascii=False))
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


def cache_command(
    golden_path: Path,
    *,
    llm: bool,
    toxicity: bool,
    out_llm: Path,
    out_toxicity: Path,
    model: str,
    ollama_url: str,
    force: bool,
) -> int:
    if not llm and not toxicity:
        print("choose --llm and/or --toxicity")
        return 2
    items = load_golden(golden_path)
    if llm:
        from aegis.detectors.intent import IntentClassifier, OpenAICompatibleClient

        digest = fetch_ollama_digest(ollama_url, model)
        client = OpenAICompatibleClient(
            base_url=f"{ollama_url.rstrip('/')}/v1",
            api_key="ollama",
            model=model,
        )
        written = asyncio.run(
            refresh_llm_cache(
                items,
                classifier=IntentClassifier(client),
                model_id=model,
                model_digest=digest,
                path=out_llm,
                force=force,
            )
        )
        print(f"llm cache: wrote {written} entries to {out_llm} (digest {digest[:12]})")
    if toxicity:
        from aegis.detectors.toxicity import TransformersToxicityScorer

        written = refresh_toxicity_cache(
            items,
            scorer=TransformersToxicityScorer(),
            path=out_toxicity,
            force=force,
        )
        print(f"toxicity cache: wrote {written} entries to {out_toxicity}")
    return 0


def _benchmark_modelfile(base_model: str) -> str:
    return f"FROM {base_model}\nPARAMETER num_ctx 2048\nPARAMETER temperature 0\nPARAMETER seed 42\n"


def benchmark_command(golden_path: Path, models: str, ollama_url: str, out: Path) -> int:
    from aegis.detectors.intent import IntentClassifier, OpenAICompatibleClient

    if shutil.which("ollama") is None:
        print("ollama CLI is not on PATH; install it in WSL before benchmarking")
        return 2
    items = [item for item in load_golden(golden_path) if item.effective_label]
    if not items:
        print(f"no labelled items under {golden_path}")
        return 2

    base_url = f"{ollama_url.rstrip('/')}/v1"
    results = []
    model_list = [entry.strip() for entry in models.split(",") if entry.strip()]
    runs = {}
    for base_model in model_list:
        slug = re.sub(r"[^a-z0-9]+", "-", base_model.lower()).strip("-")
        name = f"aegis-bench-{slug}"
        with tempfile.NamedTemporaryFile("w", suffix=".Modelfile", delete=False, encoding="utf-8") as handle:
            handle.write(_benchmark_modelfile(base_model))
            modelfile = Path(handle.name)
        try:
            subprocess.run(["ollama", "create", name, "-f", str(modelfile)], check=True, capture_output=True)
            classifier = IntentClassifier(OpenAICompatibleClient(base_url=base_url, api_key="ollama", model=name))
            run = asyncio.run(run_classifications(classifier, items))
            runs[base_model] = run
            scored_items, scored_run = held_out(base_model, items, run)
            result = score_predictions(base_model, scored_items, scored_run, total_items=len(items))
            results.append(result)
            print(
                f"{base_model}: held_out={result.items} valid_json={result.valid_json_rate:.3f} "
                f"threat_f1={result.threat_f1:.3f} items/s={result.items_per_second:.2f}"
            )
        finally:
            modelfile.unlink(missing_ok=True)
            subprocess.run(["ollama", "rm", name], capture_output=True)

    comparisons = pairwise_benchmarks(model_list, items, runs)
    for pair in comparisons:
        print(f"{pair.model_a} vs {pair.model_b}: items={pair.items} delta_f1={pair.delta_threat_f1:+.3f}")
    json_path, markdown_path = write_benchmark(results, comparisons, out)
    print(f"wrote {json_path} and {markdown_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        return run_command(args.golden, args.out)
    if args.command == "gate":
        return gate_command(args.baseline, args.report, args.tolerance)
    if args.command == "generate":
        cells = [cell.strip() for cell in args.cells.split(",") if cell.strip()] if args.cells else None
        return generate_command(args.out, args.per_class, args.seed, args.bank_dir, cells)
    if args.command == "seed-bank":
        return seed_bank_command(args.out)
    if args.command == "draft":
        return draft_command(
            args.bank_dir,
            args.models,
            args.per_model,
            args.attempts,
            args.seed,
            args.ollama_url,
            args.stats_out,
        )
    if args.command == "check-bank":
        return check_bank_command(args.bank_dir, args.out)
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
    if args.command == "cache":
        return cache_command(
            args.golden,
            llm=args.llm,
            toxicity=args.toxicity,
            out_llm=args.out_llm,
            out_toxicity=args.out_toxicity,
            model=args.model,
            ollama_url=args.ollama_url,
            force=args.force,
        )
    if args.command == "benchmark":
        return benchmark_command(args.golden, args.models, args.ollama_url, args.out)
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
