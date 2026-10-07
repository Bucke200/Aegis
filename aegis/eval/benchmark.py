"""Model benchmark over a labelled golden set.

Used after the pilot labels exist to choose between local Ollama models on
valid-JSON rate, binary threat P/R, and throughput. The scoring core is pure;
the CLI wires it to Ollama with a pinned Modelfile per candidate model.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
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
    """Aggregate result for one candidate model."""

    model: str
    items: int
    valid_json: int
    invalid_json: int
    valid_json_rate: float
    threat_precision: float
    threat_recall: float
    threat_f1: float
    exact_accuracy: float
    items_per_second: float


@dataclass(frozen=True)
class BenchmarkRun:
    predictions: list[IntentClassification | None]
    elapsed_seconds: float


def score_predictions(model: str, items: list[GoldenItem], run: BenchmarkRun) -> ModelBenchmark:
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
        valid_json=valid,
        invalid_json=total - valid,
        valid_json_rate=round(valid / total, 4) if total else 0.0,
        threat_precision=metrics.precision,
        threat_recall=metrics.recall,
        threat_f1=metrics.f1,
        exact_accuracy=round(exact / total, 4) if total else 0.0,
        items_per_second=round(total / run.elapsed_seconds, 3) if run.elapsed_seconds > 0 else 0.0,
    )


async def run_classifications(classifier: Classifying, items: list[GoldenItem]) -> BenchmarkRun:
    start = time.monotonic()
    predictions: list[IntentClassification | None] = []
    for item in items:
        try:
            predictions.append(await classifier.classify(item.text, []))
        except Exception:
            predictions.append(None)
    return BenchmarkRun(predictions=predictions, elapsed_seconds=time.monotonic() - start)


def render_markdown(results: list[ModelBenchmark]) -> str:
    lines = [
        "# Local model benchmark",
        "",
        "| Model | Items | Valid JSON | Threat P | Threat R | Threat F1 | Exact | Items/s |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for result in results:
        lines.append(
            f"| {result.model} | {result.items} | {result.valid_json_rate:.4f} "
            f"| {result.threat_precision:.4f} | {result.threat_recall:.4f} "
            f"| {result.threat_f1:.4f} | {result.exact_accuracy:.4f} "
            f"| {result.items_per_second:.3f} |"
        )
    lines.append("")
    return "\n".join(lines)


def write_benchmark(results: list[ModelBenchmark], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / BENCHMARK_JSON
    markdown_path = out_dir / BENCHMARK_MARKDOWN
    payload = "[\n" + ",\n".join(result.model_dump_json(indent=2) for result in results) + "\n]\n"
    json_path.write_text(payload, encoding="utf-8")
    markdown_path.write_text(render_markdown(results), encoding="utf-8")
    return json_path, markdown_path
