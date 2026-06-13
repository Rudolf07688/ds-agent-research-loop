"""Pydantic-settings config for the entrypoint runner.

Extends the library's central ``Settings`` (from ``prompts``) with run-launcher details:
the iteration count is fixed to 5 for this entrypoint and the per-run output location is
configurable. Values still load from ``.env`` / environment, so credentials and overrides
live in one place.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import SettingsConfigDict

from prompts import Settings


class RunConfig(Settings):
    """Configuration for an end-to-end entrypoint run."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # This entrypoint runs a fixed 5-iteration end-to-end loop.
    n_iterations: int = 5

    # Where per-run output directories are created.
    runs_dir: Path = Path("entrypoint/runs")

    # Keep each run self-contained: its own state lives under the run directory.
    isolate_state: bool = True


def load_config() -> RunConfig:
    """Build the run configuration from defaults + ``.env`` / environment."""

    return RunConfig()
