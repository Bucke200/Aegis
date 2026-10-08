"""Model benchmark over a labelled golden set.

Each model is scored only on items it did not draft. Because a single held-out
split compares different subsets per model, pairs are also compared on items
neither model drafted (the third model's drafts plus hand-written and template
items). The scoring core is pure; the CLI wires it to Ollama with a pinned
Modelfile per candidate model.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel

from aegis.detectors.intent import THREAT_LABELS, IntentClassification
from aegis.eval.adapters import THREAT_PROBABILITY_THRESHOLD, threat_probability
from aegis.eval.models import GoldenItem
from aegis.eval.runner import compute_metrics

BENCHMARK_JSON = "model-benchmark.json"
BENCHMARK_MARKDOWN = "model-benchmark.md"


class Classifying(Protocol):
    async def classify(self, text: str, vip_names: list[str]) -> IntentClassification: ...


class ModelBenchmark(BaseModel):
    """Aggregate result for one candidate model on its held-out items."""

    model: str
    items: int
    total_items: int
    valid_json: int
    invalid_json: int
    valid_json_rate: float
    threat_precision: float
    threat_recall: float
    threat_f1: float
    exact_accuracy: float
    items_per_second: float


class PairwiseBenchmark(BaseModel):
    """Two models compared on the items neither of them drafted."""

    model_a: str
    model_b: str
    items: int
    a_threat_f1: float
    b_threat_f1: float
    delta_threat_f1: float
    a_valid_json_rate: float
    b_valid_json_rate: float


@dataclass(frozen=True)
class BenchmarkRun:
    predictions: list[IntentClassification | None]
    elapsed_seconds: float


def score_predictions(
    model: str, items: list[GoldenItem], run: BenchmarkRun, *, total_items: int | None = None
) -> ModelBenchmark:
    pairs: list[tuple[bool, bool]] = []
    valid = 0
    exact = 0
    for item, prediction in zip(items, run.predictions, strict=True):
        expected = item.effective_label in THREAT_LABELS
        if prediction is None:
            pairs.append((expected, False))
            continue
        valid += 1
        pairs.append((expected, threat_probability(prediction.intent_probs) >= THREAT_PROBABILITY_THRESHOLD))
        if prediction.intent == item.effective_label:
            exact += 1
    metrics = compute_metrics(pairs)
    total = len(items)
    return ModelBenchmark(
        model=model,
        items=total,
        total_items=total_items if total_items is not None else total,
        valid_json=valid,
        invalid_json=total - valid,
        valid_json_rate=round(valid / total, 4) if total else 0.0,
        threat_precision=metrics.precision,
        threat_recall=metrics.recall,
        threat_f1=metrics.f1,
        exact_accuracy=round(exact / total, 4) if total else 0.0,
        items_per_second=round(total / run.elapsed_seconds, 3) if run.elapsed_seconds > 0 else 0.0,
    )


def held_out(model: str, items: list[GoldenItem], run: BenchmarkRun) -> tuple[list[GoldenItem], BenchmarkRun]:
    """Drop items the model drafted, keeping predictions aligned."""

    kept_items: list[GoldenItem] = []
    kept_predictions: list[IntentClassification | None] = []
    for item, prediction in zip(items, run.predictions, strict=True):
        if (item.drafter or "") == model:
            continue
        kept_items.append(item)
        kept_predictions.append(prediction)
    return kept_items, BenchmarkRun(predictions=kept_predictions, elapsed_seconds=run.elapsed_seconds)


def pairwise_benchmarks(
    models: list[str],
    items: list[GoldenItem],
    runs: dict[str, BenchmarkRun],
) -> list[PairwiseBenchmark]:
    """Compare each model pair on items neither model drafted."""

    comparisons: list[PairwiseBenchmark] = []
    for model_a, model_b in combinations(sorted(models), 2):
        subset_items = [item for item in items if (item.drafter or "") not in {model_a, model_b}]
        if not subset_items:
            continue
        scored: dict[str, ModelBenchmark] = {}
        for model in (model_a, model_b):
            run = runs[model]
            predictions = [
                prediction
                for item, prediction in zip(items, run.predictions, strict=True)
                if (item.drafter or "") not in {model_a, model_b}
            ]
            scored[model] = score_predictions(
                model, subset_items, BenchmarkRun(predictions=predictions, elapsed_seconds=run.elapsed_seconds)
            )
        comparisons.append(
            PairwiseBenchmark(
                model_a=model_a,
                model_b=model_b,
                items=len(subset_items),
                a_threat_f1=scored[model_a].threat_f1,
                b_threat_f1=scored[model_b].threat_f1,
                delta_threat_f1=round(scored[model_a].threat_f1 - scored[model_b].threat_f1, 4),
                a_valid_json_rate=scored[model_a].valid_json_rate,
                b_valid_json_rate=scored[model_b].valid_json_rate,
            )
        )
    return comparisons


async def run_classifications(classifier: Classifying, items: list[GoldenItem]) -> BenchmarkRun:
    start = time.monotonic()
    predictions: list[IntentClassification | None] = []
    for item in items:
        try:
            predictions.append(await classifier.classify(item.text, []))
        except Exception:
            predictions.append(None)
    return BenchmarkRun(predictions=predictions, elapsed_seconds=time.monotonic() - start)


def render_markdown(results: list[ModelBenchmark], comparisons: list[PairwiseBenchmark]) -> str:
    lines = [
        "# Local model benchmark",
        "",
        "Held-out per model (items the model did not draft):",
        "",
        "| Model | Held out | Total | Valid JSON | Threat P | Threat R | Threat F1 | Exact | Items/s |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for result in results:
        lines.append(
            f"| {result.model} | {result.items} | {result.total_items} | {result.valid_json_rate:.4f} "
            f"| {result.threat_precision:.4f} | {result.threat_recall:.4f} "
            f"| {result.threat_f1:.4f} | {result.exact_accuracy:.4f} "
            f"| {result.items_per_second:.3f} |"
        )
    if comparisons:
        lines.append("")
        lines.append("Pairwise on items neither model drafted:")
        lines.append("")
        lines.append("| Model A | Model B | Items | A Threat F1 | B Threat F1 | Delta | A Valid JSON | B Valid JSON |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for pair in comparisons:
            lines.append(
                f"| {pair.model_a} | {pair.model_b} | {pair.items} | {pair.a_threat_f1:.4f} "
                f"| {pair.b_threat_f1:.4f} | {pair.delta_threat_f1:+.4f} "
                f"| {pair.a_valid_json_rate:.4f} | {pair.b_valid_json_rate:.4f} |"
            )
    lines.append("")
    return "\n".join(lines)


def write_benchmark(
    results: list[ModelBenchmark],
    comparisons: list[PairwiseBenchmark],
    out_dir: Path,
) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / BENCHMARK_JSON
    markdown_path = out_dir / BENCHMARK_MARKDOWN
    payload = {
        "held_out": [result.model_dump() for result in results],
        "pairwise": [pair.model_dump() for pair in comparisons],
    }
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(results, comparisons), encoding="utf-8")
    return json_path, markdown_path
