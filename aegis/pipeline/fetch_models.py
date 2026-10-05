"""Model weight download entrypoint (skeleton).

The real download lands with the analysis model runtime (task 7.1) and the
media stack (task 14.1), which populate the `models` volume used by Compose.
"""

from __future__ import annotations


def main() -> int:
    """Print a placeholder message until model fetching is implemented."""

    print("model weight download is not implemented yet; see tasks 7.1 and 14.1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
