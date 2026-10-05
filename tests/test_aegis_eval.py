"""Tests for the evaluation harness."""

from __future__ import annotations

import json
from pathlib import Path

from aegis.eval.__main__ import main
from aegis.eval.dataset import load_golden
from aegis.eval.detectors import keyword_smoke
from aegis.eval.gate import compare_reports
from aegis.eval.models import EvalReport, Metrics
from aegis.eval.runner import compute_metrics, evaluate

GOLDEN = Path("data/golden")


def make_report(precision: float, recall: float) -> EvalReport:
    return EvalReport(
        generated_at="2026-01-01T00:00:00+00:00",
        golden_path="test",
        item_count=1,
        detectors={"keyword_smoke": {"all": Metrics(precision=precision, recall=recall, f1=0.5)}},
    )


def test_load_golden_synthetic() -> None:
    items = load_golden(GOLDEN)
    assert len(items) == 27
    assert len({item.id for item in items}) == 27
    assert {item.language for item in items} == {"en", "hi", "hi-Latn"}


def test_compute_metrics() -> None:
    metrics = compute_metrics([(True, True), (True, False), (False, True), (False, False)])
    assert (metrics.tp, metrics.fp, metrics.fn, metrics.tn) == (1, 1, 1, 1)
    assert metrics.precision == 0.5
    assert metrics.recall == 0.5
    assert metrics.f1 == 0.5


def test_reference_detector_metrics() -> None:
    items = load_golden(GOLDEN)
    report = evaluate(items, {"keyword_smoke": keyword_smoke}, str(GOLDEN))
    for language in ("en", "hi", "hi-Latn"):
        metrics = report.detectors["keyword_smoke"][language]
        assert metrics.precision == 0.75
        assert metrics.recall == 0.75
        assert metrics.support == 4
    assert report.detectors["keyword_smoke"]["all"].support == 12


def test_gate_passes_on_equal_reports() -> None:
    assert compare_reports(make_report(0.8, 0.8), make_report(0.8, 0.8), 0.02) == []


def test_gate_fails_on_regression() -> None:
    regressions = compare_reports(make_report(0.8, 0.8), make_report(0.75, 0.8), 0.02)
    assert len(regressions) == 1
    assert "precision" in regressions[0]


def test_gate_accepts_new_detectors() -> None:
    baseline = EvalReport(generated_at="t", golden_path="x", item_count=0, detectors={})
    assert compare_reports(baseline, make_report(0.5, 0.5), 0.02) == []


def test_cli_run_then_gate(tmp_path: Path) -> None:
    assert main(["run", "--golden", str(GOLDEN), "--out", str(tmp_path)]) == 0
    report_file = tmp_path / "report.json"
    assert report_file.exists()
    assert main(["gate", "--baseline", str(report_file), "--report", str(report_file)]) == 0

    data = json.loads(report_file.read_text(encoding="utf-8"))
    data["detectors"]["keyword_smoke"]["all"]["recall"] = 0.1
    worse = tmp_path / "worse.json"
    worse.write_text(json.dumps(data), encoding="utf-8")
    assert main(["gate", "--baseline", str(report_file), "--report", str(worse)]) == 1
