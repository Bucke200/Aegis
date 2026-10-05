"""Evidence capture entrypoint (skeleton). The capture service lands in task 10.1."""

from __future__ import annotations

from aegis.common.runtime import run_until_stopped


def main() -> None:
    """Run the capture skeleton until task 10.1 is implemented."""

    run_until_stopped("capture", "sandboxed capture lands in task 10.1")


if __name__ == "__main__":
    main()
