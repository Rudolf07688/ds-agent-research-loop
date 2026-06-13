"""End-to-end entrypoint for the AutoDS loop.

Pulls the single library entrypoint (``run_loop``) and drives a fixed 5-iteration run,
configured via ``config.py`` (pydantic-settings), writing the outcome to
``entrypoint/runs/run_<current_dt>/results.text``.

Run from the repository root:

    uv run python entrypoint/run.py
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path

from ds_agent_loop import run_loop  # the single library entrypoint
from ds_agent_loop.main import SUMMARY_FILE

from config import load_config

REPO_ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    config = load_config()

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = (REPO_ROOT / config.runs_dir / f"run_{timestamp}").resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    state_dir = run_dir / "state" if config.isolate_state else REPO_ROOT / "state"

    print(f"Running {config.n_iterations}-iteration loop -> {run_dir}")
    asyncio.run(run_loop(config, state_dir=state_dir, outputs_dir=run_dir))

    # The library writes its summary as run_summary.txt; surface it as results.text.
    summary_path = run_dir / SUMMARY_FILE
    results_path = run_dir / "results.text"
    if summary_path.exists():
        summary_path.replace(results_path)
    print(f"Results written to {results_path}")


if __name__ == "__main__":
    main()
