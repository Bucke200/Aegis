"""Describe validation failures without echoing the offending input."""

from __future__ import annotations


def validation_summary(error: ValueError) -> str:
    """Describe a validation error without echoing the offending input.

    Pydantic embeds the input value in ``str(error)``; for golden items, cache
    entries, and model output that input can be private text, so messages
    destined for logs must use only the field locations and reasons.
    """

    errors = getattr(error, "errors", None)
    if not callable(errors):
        return "invalid value"
    parts: list[str] = []
    for item in errors():
        location = ".".join(str(piece) for piece in item.get("loc", ())) or "<root>"
        parts.append(f"{location}: {item.get('msg', 'invalid')}")
    return "; ".join(parts) if parts else "invalid value"
