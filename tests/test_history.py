"""Tests for history append + best-run selection (US3, T016)."""

from __future__ import annotations

from ds_agent_loop import history
from ds_agent_loop.prompts import RunRecord


def _record(iteration: int, rmse: float) -> RunRecord:
    return RunRecord(
        iteration=iteration,
        dataset_size=500,
        model_name="LinearRegression",
        hyperparameters={},
        metrics={"rmse": rmse, "r2": 0.5, "mae": rmse * 0.8},
        rationale="baseline",
        timestamp="2026-06-13T00:00:00",
    )


def test_append_records_all_fields(tmp_path):
    hist = history.append_run(_record(1, 10.0), state_dir=tmp_path)
    assert len(hist) == 1
    loaded = history.load_history(state_dir=tmp_path)
    rec = loaded[0]
    assert rec.iteration == 1
    assert rec.dataset_size == 500
    assert rec.model_name == "LinearRegression"
    assert rec.metrics["rmse"] == 10.0
    assert rec.rationale and rec.timestamp


def test_best_run_updates_only_on_improvement(tmp_path):
    best, improved = history.update_best_run(_record(1, 10.0), state_dir=tmp_path)
    assert improved and best.metrics["rmse"] == 10.0

    # Worse RMSE: best is retained, not updated.
    best, improved = history.update_best_run(_record(2, 12.0), state_dir=tmp_path)
    assert not improved and best.metrics["rmse"] == 10.0

    # Better RMSE: best updates.
    best, improved = history.update_best_run(_record(3, 8.0), state_dir=tmp_path)
    assert improved and best.metrics["rmse"] == 8.0


def test_rejection_recorded_but_never_becomes_best(tmp_path):
    history.update_best_run(_record(1, 9.0), state_dir=tmp_path)
    history.record_rejection(
        iteration=2,
        dataset_size=500,
        current_model="LinearRegression",
        retained_metrics={"rmse": 9.0},
        reason="bad proposal",
        timestamp="2026-06-13T00:01:00",
        state_dir=tmp_path,
    )
    hist = history.load_history(state_dir=tmp_path)
    assert any("REJECTED" in r.rationale for r in hist)
    best = history.load_best_run(state_dir=tmp_path)
    assert best.metrics["rmse"] == 9.0
