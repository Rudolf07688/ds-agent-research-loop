"""Pydantic-settings config for the entrypoint sweep runner.

Extends the library's central ``Settings`` (from ``prompts``) with container-run defaults.
The container batch job runs the ablation SWEEP (see ``run.py``); these defaults keep a
``docker compose up`` validation run small and feasible (a couple of seeds, a short budget)
while a real research sweep overrides them via ``.env`` / environment. Values still load
from ``.env`` / environment, so credentials and overrides live in one place.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import SettingsConfigDict

from ds_agent_loop import Settings


class RunConfig(Settings):
    """Configuration for the container ablation sweep."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Container default: a short budget (override via env for a full study). ``seeds`` /
    # ``datasets`` / ``regimes`` are inherited from ``Settings`` (with their NoDecode +
    # comma-split env handling) so e.g. ``SEEDS=0`` and ``DATASETS=delivery_time`` parse.
    n_iterations: int = 8

    # Where per-run artifact directories are created (kept for compatibility).
    runs_dir: Path = Path("entrypoint/runs")


def load_config() -> RunConfig:
    """Build the run configuration from defaults + ``.env`` / environment."""

    return RunConfig()
