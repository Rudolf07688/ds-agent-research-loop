"""Run history and best-run tracking.

All durable results are human-readable JSON under ``state/`` (Constitution Principle IV):
``history.json`` is an append-only array of run records; ``best_run.json`` holds the single
best result so far, updated only when the primary metric (RMSE, lower is better) improves.
"""

from __future__ import annotations

import json
from pathlib import Path

from prompts import RunRecord

STATE_DIR = Path("state")
HISTORY_FILE = "history.json"
BEST_RUN_FILE = "best_run.json"


class StateError(RuntimeError):
    """Raised when a history/best-run file exists but cannot be read/parsed."""


def load_history(state_dir: Path = STATE_DIR) -> list[RunRecord]:
    """Load the run history (empty list if none yet)."""

    path = state_dir / HISTORY_FILE
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text())
        return [RunRecord.model_validate(r) for r in raw]
    except Exception as exc:
        raise StateError(f"Corrupt history at {path}: {exc}") from exc


def append_run(record: RunRecord, state_dir: Path = STATE_DIR) -> list[RunRecord]:
    """Append a run record to ``history.json`` and return the full history."""

    state_dir.mkdir(parents=True, exist_ok=True)
    history = load_history(state_dir)
    history.append(record)
    (state_dir / HISTORY_FILE).write_text(
        json.dumps([r.model_dump() for r in history], indent=2)
    )
    return history


def load_best_run(state_dir: Path = STATE_DIR) -> RunRecord | None:
    """Load the current best run, or None if not set."""

    path = state_dir / BEST_RUN_FILE
    if not path.exists():
        return None
    try:
        return RunRecord.model_validate_json(path.read_text())
    except Exception as exc:
        raise StateError(f"Corrupt best run at {path}: {exc}") from exc


def update_best_run(record: RunRecord, state_dir: Path = STATE_DIR) -> tuple[RunRecord, bool]:
    """Update ``best_run.json`` only if RMSE improved. Return (best, improved)."""

    state_dir.mkdir(parents=True, exist_ok=True)
    current = load_best_run(state_dir)
    improved = current is None or record.metrics["rmse"] < current.metrics["rmse"]
    if improved:
        (state_dir / BEST_RUN_FILE).write_text(json.dumps(record.model_dump(), indent=2))
        return record, True
    return current, False


def record_rejection(
    iteration: int,
    dataset_size: int,
    current_model: str,
    retained_metrics: dict[str, float],
    reason: str,
    timestamp: str,
    state_dir: Path = STATE_DIR,
) -> list[RunRecord]:
    """Record a rejected LLM proposal in history while retaining the prior model (US4).

    The loop keeps the previous model and its last known metrics; the record is appended
    to history but is never passed to ``update_best_run``, so it cannot become the best.
    Carrying the retained metrics keeps ``history.json`` standard, inspectable JSON.
    """

    record = RunRecord(
        iteration=iteration,
        dataset_size=dataset_size,
        model_name=current_model,
        hyperparameters={},
        metrics=dict(retained_metrics),
        rationale=f"REJECTED proposal; retained prior model. {reason}",
        timestamp=timestamp,
    )
    return append_run(record, state_dir)
