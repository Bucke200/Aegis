"""Analysis worker entrypoint (skeleton). The pipeline lands in tasks 3.1 and 6-8."""

from __future__ import annotations

from aegis.common.runtime import run_until_stopped


def main() -> None:
    """Run the worker skeleton until the pipeline is implemented."""

    run_until_stopped(
        "analysis-worker",
        "collectors, normalization, detection, and scoring land in tasks 3.1 and 6-8",
    )


if __name__ == "__main__":
    main()
