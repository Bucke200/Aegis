"""Media worker entrypoint (skeleton). Media analysis lands in tasks 14.1-14.4."""

from __future__ import annotations

from aegis.common.runtime import run_until_stopped


def main() -> None:
    """Run the media worker skeleton until task 14.1 is implemented."""

    run_until_stopped("media-worker", "media analysis lands in tasks 14.1-14.4")


if __name__ == "__main__":
    main()
