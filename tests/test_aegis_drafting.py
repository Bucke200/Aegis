"""Tests for the model drafting workflow (offline, no Ollama required)."""

from __future__ import annotations

from pathlib import Path

import pytest

from aegis.detectors.intent import INTENT_LABELS
from aegis.eval.__main__ import main
from aegis.eval.bank import load_bank
from aegis.eval.candidates import VIP_ROSTER
from aegis.eval.drafting import (
    LANGUAGE_INSTRUCTIONS,
    LANGUAGES,
    DraftingInputError,
    clean_draft,
    resolve_active_languages,
    run_drafting,
)

DRAFTS = {
    "en": "He should be taught a lesson; attack him and publish his home address.",
    "hi": "उसे सबक सिखाना चाहिए, हमला करो, उसका पता सबको बताओ।",
    "hi-Latn": "usko sabak sikhao, hamla karo, uska pata sabko batao.",
}


@pytest.fixture
def recorded_calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    calls: list[tuple[str, str]] = []

    async def fake_draft_once(client, *, url: str, model: str, prompt: str, seed: int) -> str:
        language = next(lang for lang in LANGUAGE_INSTRUCTIONS if LANGUAGE_INSTRUCTIONS[lang] in prompt)
        calls.append((model, language))
        return f"{DRAFTS[language]} {len(calls)}"

    monkeypatch.setattr("aegis.eval.drafting.draft_once", fake_draft_once)
    return calls


def test_clean_draft_strips_wrappers_and_collapses_whitespace() -> None:
    assert clean_draft("```\nPost: hello world\n```") == "hello world"
    assert clean_draft("Post:   first line\n\nsecond   line") == "first line second line"
    assert clean_draft('"  quoted draft  "') == "quoted draft"


def test_clean_draft_keeps_devanagari_and_hinglish() -> None:
    hindi = "उसे सबक सिखाना चाहिए"
    hinglish = "usko sabak sikhao warna ghar pata hai"
    assert clean_draft(hindi) == hindi
    assert clean_draft(f'"```\n{hindi}\n```"') == hindi
    assert clean_draft(hinglish) == hinglish


def test_draft_cli_rejects_unknown_language(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bank_dir = tmp_path / "banks"
    stats_path = tmp_path / "draft-stats.json"
    code = main(
        [
            "draft",
            "--models",
            "gemma3:4b",
            "--languages",
            "hinglish",
            "--bank-dir",
            str(bank_dir),
            "--stats-out",
            str(stats_path),
        ]
    )
    captured = capsys.readouterr()
    assert code == 2
    assert "hinglish" in captured.err
    assert f"valid languages: {', '.join(LANGUAGES)}" in captured.err
    assert not bank_dir.exists()
    assert not stats_path.exists()


def test_draft_cli_rejects_language_no_model_drafts(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bank_dir = tmp_path / "banks"
    bank_dir.mkdir()
    bank_file = bank_dir / "llm-drafts.jsonl"
    bank_file.write_text("", encoding="utf-8")
    stats_path = tmp_path / "draft-stats.json"
    stats_path.write_text('{"attempts": 5}\n', encoding="utf-8")
    code = main(
        [
            "draft",
            "--models",
            "llama3.2:3b",
            "--languages",
            "hi",
            "--bank-dir",
            str(bank_dir),
            "--stats-out",
            str(stats_path),
        ]
    )
    captured = capsys.readouterr()
    assert code == 2
    assert "llama3.2:3b drafts en" in captured.err
    assert bank_file.read_text(encoding="utf-8") == ""
    assert stats_path.read_text(encoding="utf-8") == '{"attempts": 5}\n'


async def test_run_drafting_rejects_unknown_languages(tmp_path: Path) -> None:
    bank_dir = tmp_path / "banks"
    stats_path = tmp_path / "draft-stats.json"
    with pytest.raises(ValueError, match="hinglish"):
        await run_drafting(
            models=("gemma3:4b",),
            vip_roster=VIP_ROSTER,
            bank_dir=bank_dir,
            stats_path=stats_path,
            languages=("hinglish",),
        )
    assert not bank_dir.exists()
    assert not stats_path.exists()


def test_draft_scoped_to_requested_language(tmp_path: Path, recorded_calls: list[tuple[str, str]]) -> None:
    bank_dir = tmp_path / "banks"
    code = main(
        [
            "draft",
            "--models",
            "gemma3:4b",
            "--languages",
            "hi",
            "--per-model",
            "1",
            "--attempts",
            "1",
            "--bank-dir",
            str(bank_dir),
            "--stats-out",
            str(tmp_path / "draft-stats.json"),
        ]
    )
    assert code == 0
    assert {language for _, language in recorded_calls} == {"hi"}
    items = load_bank(bank_dir)
    assert {item.language for item in items} == {"hi"}
    assert {item.intended_label for item in items} == set(INTENT_LABELS)
    assert {item.drafter for item in items} == {"gemma3:4b"}


def test_draft_unscoped_covers_model_languages(tmp_path: Path, recorded_calls: list[tuple[str, str]]) -> None:
    bank_dir = tmp_path / "banks"
    code = main(
        [
            "draft",
            "--models",
            "llama3.2:3b,gemma3:4b",
            "--per-model",
            "1",
            "--attempts",
            "1",
            "--bank-dir",
            str(bank_dir),
            "--stats-out",
            str(tmp_path / "draft-stats.json"),
        ]
    )
    assert code == 0
    assert {language for model, language in recorded_calls if model == "llama3.2:3b"} == {"en"}
    assert {language for model, language in recorded_calls if model == "gemma3:4b"} == set(LANGUAGES)
    assert {item.language for item in load_bank(bank_dir)} == set(LANGUAGES)


def test_draft_cli_rejects_mixed_valid_and_unknown_languages(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bank_dir = tmp_path / "banks"
    stats_path = tmp_path / "draft-stats.json"
    code = main(
        [
            "draft",
            "--models",
            "gemma3:4b",
            "--languages",
            "hi,gemma",
            "--bank-dir",
            str(bank_dir),
            "--stats-out",
            str(stats_path),
        ]
    )
    captured = capsys.readouterr()
    assert code == 2
    assert "unknown language(s): gemma" in captured.err
    assert f"valid languages: {', '.join(LANGUAGES)}" in captured.err
    assert not bank_dir.exists()
    assert not stats_path.exists()


@pytest.mark.parametrize("selection", ["", " , "])
def test_draft_cli_rejects_empty_language_selection(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], selection: str
) -> None:
    bank_dir = tmp_path / "banks"
    stats_path = tmp_path / "draft-stats.json"
    code = main(
        [
            "draft",
            "--models",
            "gemma3:4b",
            "--languages",
            selection,
            "--bank-dir",
            str(bank_dir),
            "--stats-out",
            str(stats_path),
        ]
    )
    captured = capsys.readouterr()
    assert code == 2
    assert "no languages selected" in captured.err
    assert f"valid languages: {', '.join(LANGUAGES)}" in captured.err
    assert not bank_dir.exists()
    assert not stats_path.exists()


def test_resolve_active_languages_returns_canonical_order() -> None:
    active = resolve_active_languages(models=("gemma3:4b",), languages=("hi-Latn", "en", "hi"))
    assert active == ("en", "hi", "hi-Latn")


def test_draft_cli_follows_canonical_language_order(tmp_path: Path, recorded_calls: list[tuple[str, str]]) -> None:
    bank_dir = tmp_path / "banks"
    code = main(
        [
            "draft",
            "--models",
            "gemma3:4b",
            "--languages",
            "hi-Latn,en,hi",
            "--per-model",
            "1",
            "--attempts",
            "1",
            "--bank-dir",
            str(bank_dir),
            "--stats-out",
            str(tmp_path / "draft-stats.json"),
        ]
    )
    assert code == 0
    seen = [language for _, language in recorded_calls]
    assert seen == sorted(seen, key=LANGUAGES.index)


def test_draft_cli_corrupt_bank_raises_value_error_not_input_error(tmp_path: Path) -> None:
    bank_dir = tmp_path / "banks"
    bank_dir.mkdir()
    (bank_dir / "llm-drafts.jsonl").write_text("{not json}\n", encoding="utf-8")
    stats_path = tmp_path / "draft-stats.json"
    with pytest.raises(ValueError, match="invalid bank entry") as excinfo:
        main(
            [
                "draft",
                "--models",
                "gemma3:4b",
                "--bank-dir",
                str(bank_dir),
                "--stats-out",
                str(stats_path),
            ]
        )
    assert not isinstance(excinfo.value, DraftingInputError)
    assert "invalid bank entry" in str(excinfo.value)
    assert not stats_path.exists()
