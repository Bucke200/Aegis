"""Tests for the draft bank, its checks, and the held-out benchmark (no database required)."""

from __future__ import annotations

import pytest

from aegis.detectors.intent import INTENT_LABELS, THREAT_LABELS, IntentClassification
from aegis.eval.bank import (
    DRAFTER_HAND,
    BankItem,
    bank_item_id,
    check_bank,
    clean_items,
    is_duplicate,
    is_refusal,
    item_issues,
    language_issue,
    select_for_sheet,
)
from aegis.eval.benchmark import BenchmarkRun, held_out, pairwise_benchmarks, score_predictions
from aegis.eval.models import GoldenItem


def make_bank_item(
    text: str = "A neutral post about the weather today.",
    language: str = "en",
    label: str = "none",
    drafter: str = DRAFTER_HAND,
    **kwargs: object,
) -> BankItem:
    return BankItem(
        id=bank_item_id(language, label, drafter, text),
        language=language,
        text=text,
        intended_label=label,
        drafter=drafter,
        **kwargs,
    )


def test_refusal_detection() -> None:
    assert is_refusal("I cannot help with that request.")
    assert is_refusal("I'm sorry, I can't write that.")
    assert is_refusal("मैं यह नहीं लिख सकता")
    assert not is_refusal("I will not attend the event tomorrow.")
    assert not is_refusal("The policy cannot be defended.")


def test_pii_and_url_checks() -> None:
    assert "pii_phone" in item_issues(make_bank_item("Call +91 91234 56789 now."))
    assert "pii_phone" not in item_issues(make_bank_item("Call +91 50000 00001 now."))
    assert "pii_email" in item_issues(make_bank_item("Mail me at person@gmail.com."))
    assert "pii_email" not in item_issues(make_bank_item("Mail me at person@example.test."))
    assert "pii_aadhaar" in item_issues(make_bank_item("Aadhaar 2345 6789 0123 on file."))
    assert "pii_aadhaar" not in item_issues(make_bank_item("Aadhaar 1111 2222 3333 on file."))
    assert "url" in item_issues(make_bank_item("See https://example.com/post for details."))


def test_language_checks() -> None:
    assert language_issue("hi", "यह एक हिंदी वाक्य है।") is None
    assert language_issue("hi", "This is English text.") == "language"
    assert language_issue("hi-Latn", "Aaj usko goli maar dunga, yaad rakhna.") is None
    assert language_issue("hi-Latn", "This is plain English text.") == "language"


def test_duplicates_are_dropped() -> None:
    items = [
        make_bank_item("Someone should hurt the rival today.", drafter="model-a"),
        make_bank_item("Someone should hurt the rival today.", drafter="model-b"),
    ]
    clean, issues = clean_items(items)
    assert len(clean) == 1
    assert issues[items[1].id] == ["duplicate"]
    assert is_duplicate(items[0], [items[0]]) == "duplicate"


def test_near_duplicates_are_dropped() -> None:
    first = make_bank_item("We will attack the office tonight with all of us together now.", drafter="model-a")
    second = make_bank_item("Tonight we will attack the office with all of us together now.", drafter="model-b")
    clean, issues = clean_items([first, second])
    assert len(clean) == 1
    assert issues[second.id] == ["near_duplicate"]


def test_check_bank_reports_counts_only() -> None:
    items = [
        make_bank_item("A neutral post about the weather today."),
        make_bank_item("I cannot help with that request at all."),
        make_bank_item("Call +91 91234 56789 now, urgent.", drafter="model-a"),
    ]
    summary = check_bank(items).as_dict()
    assert summary["items"] == 3
    assert summary["clean"] == 1
    assert summary["issues"]["refusal"] == 1
    assert summary["issues"]["pii_phone"] == 1
    assert "text" not in str(summary)


FILLERS = {
    "en": ("budget", "school", "market", "bridge", "water", "power", "tax", "road", "rail", "health", "farm", "port"),
    "hi": ("बजट", "स्कूल", "बाजार", "पुल", "पानी", "बिजली", "कर", "सड़क", "रेल", "स्वास्थ्य", "खेत", "बंदरगाह"),
    "hi-Latn": (
        "budget",
        "school",
        "bazaar",
        "pul",
        "paani",
        "bijli",
        "tax",
        "sadak",
        "rail",
        "health",
        "khet",
        "bandargah",
    ),
}


def cell_text(language: str, label: str, tag: str, filler: str) -> str:
    if language == "hi":
        return f"{tag} कहता है कि {label} के लिए {filler} योजना पर आज लंबी चर्चा होनी चाहिए।"
    if language == "hi-Latn":
        return f"{tag} kehta hai ki {label} ke liye {filler} yojana par aaj lambi charcha honi chahiye."
    return f"{tag} says the {filler} plan for {label} is worth a long discussion today."


def test_select_for_sheet_guarantees_drafter_coverage() -> None:
    items: list[BankItem] = []
    for label in INTENT_LABELS:
        for language in ("en", "hi", "hi-Latn"):
            fillers = FILLERS[language]
            for index in range(4):
                items.append(
                    make_bank_item(
                        cell_text(language, label, f"hand{index}", fillers[index]), language=language, label=label
                    )
                )
            for model in ("model-a", "model-b", "model-c"):
                for index in range(2):
                    filler = fillers[4 + index + ("model-a", "model-b", "model-c").index(model) * 2]
                    items.append(
                        make_bank_item(
                            cell_text(language, label, f"{model}{index}", filler),
                            language=language,
                            label=label,
                            drafter=model,
                        )
                    )
    selected = select_for_sheet(items, per_class=8, seed=7, model_drafters=["model-a", "model-b", "model-c"])
    assert len(selected) == len(INTENT_LABELS) * 3 * 8
    for language in ("en", "hi", "hi-Latn"):
        for label in INTENT_LABELS:
            cell = [item for item in selected if item.language == language and item.intended_label == label]
            assert {item.drafter for item in cell} >= {"model-a", "model-b", "model-c", DRAFTER_HAND}


def test_select_for_sheet_errors_on_short_cell() -> None:
    items = [make_bank_item("Only one item here for the cell.", label="none")]
    with pytest.raises(ValueError, match="need 2"):
        select_for_sheet(items, per_class=2, seed=7)


def golden(item_id: str, label: str, drafter: str) -> GoldenItem:
    return GoldenItem(
        id=item_id,
        language="en",
        text=f"text {item_id}",
        labels={"text_intent_llm": label in THREAT_LABELS},
        intent=label,
        drafter=drafter,
    )


def prediction(label: str, probability: float = 0.9) -> IntentClassification:
    return IntentClassification(intent=label, intent_probs={label: probability})


def test_held_out_drops_own_drafts() -> None:
    items = [golden("a", "none", "model-a"), golden("b", "none", "model-b")]
    run = BenchmarkRun(predictions=[prediction("none"), prediction("none")], elapsed_seconds=1.0)
    kept_items, kept_run = held_out("model-a", items, run)
    assert [item.id for item in kept_items] == ["b"]
    assert len(kept_run.predictions) == 1


def test_pairwise_uses_common_held_out_subset() -> None:
    items = [golden("a", "none", "model-a"), golden("b", "none", "model-b"), golden("c", "none", "model-c")]
    predictions = [prediction("none"), prediction("none"), prediction("none")]
    runs = {
        model: BenchmarkRun(predictions=list(predictions), elapsed_seconds=1.0)
        for model in ("model-a", "model-b", "model-c")
    }
    comparisons = pairwise_benchmarks(list(runs), items, runs)
    assert len(comparisons) == 3
    assert all(pair.items == 1 for pair in comparisons)
    assert all(pair.delta_threat_f1 == 0.0 for pair in comparisons)


def test_score_predictions_counts_invalid_json() -> None:
    items = [golden("a", "none", "model-a"), golden("b", "none", "model-a")]
    run = BenchmarkRun(predictions=[prediction("none"), None], elapsed_seconds=1.0)
    result = score_predictions("model-a", items, run, total_items=5)
    assert result.total_items == 5
    assert result.valid_json == 1
    assert result.invalid_json == 1
