"""Unit tests for language and script detection."""

from __future__ import annotations

from aegis.common.language import DetectedLanguage, detect_language


def test_devanagari_is_hindi() -> None:
    assert detect_language("मैं तुम्हें मार डालूंगा") == DetectedLanguage("hi", "Devanagari")


def test_romanized_hindi_markers() -> None:
    result = detect_language("usko maar dunga dekh lena")
    assert result.language == "hi-Latn"
    assert result.script == "Latin"


def test_english_text() -> None:
    result = detect_language("We must act against the politician immediately")
    assert result.language == "en"
    assert result.script == "Latin"


def test_blank_text() -> None:
    assert detect_language("   ") == DetectedLanguage(None, None)


def test_non_latin_script() -> None:
    assert detect_language("こんにちは世界") == DetectedLanguage(None, None)
