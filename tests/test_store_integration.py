"""Opt-in Postgres integration test (T050 / analyze G2).

Exercises the REAL ``Store`` against the compose ``db`` — the actual ``ON CONFLICT DO UPDATE``
upsert and resume semantics that the in-process ``FakeStore`` can only approximate. Skipped
automatically when no Postgres is reachable, so the default offline suite stays hermetic
(research Decision 2). Run with the compose db up and ``DATABASE_URL`` set.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from ds_agent_loop import store as S
from ds_agent_loop.prompts import (
    CellStatus,
    ExperimentCell,
    ExperimentRecord,
    MemoryRegime,
    Settings,
)

_TEST_CELL = "itest|all_raw|s0|k5|m10"


def _cleanup(engine, cell_id: str) -> None:
    with engine.begin() as conn:
        for table in ("experiment_records", "memory_views", "compaction_artifacts", "run_logs", "cells"):
            col = "cell_id"
            conn.execute(text(f"DELETE FROM {table} WHERE {col} = :c"), {"c": cell_id})


@pytest.fixture
def pg_store():
    settings = Settings()
    try:
        engine = S.make_engine(settings.database_url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # no DB reachable -> skip, keep the suite hermetic
        pytest.skip(f"Postgres not available ({exc}); skipping integration test.")
    store = S.Store(engine)
    _cleanup(engine, _TEST_CELL)
    try:
        yield store
    finally:
        _cleanup(engine, _TEST_CELL)


def _cell(status: CellStatus) -> ExperimentCell:
    return ExperimentCell(
        cell_id=_TEST_CELL, dataset_id="diabetes", regime=MemoryRegime.all_raw,
        seed=0, k=5, m=10, budget=30, status=status,
    )


def _record(iteration: int, rmse: float) -> ExperimentRecord:
    return ExperimentRecord(
        iteration=iteration, dataset_size=265, model_name="LinearRegression",
        metrics={"rmse": rmse}, rationale="x", timestamp="t", cell_id=_TEST_CELL,
        dataset_id="diabetes", regime=MemoryRegime.all_raw, seed=0, test_metrics={"rmse": rmse},
    )


def test_real_upsert_cell_is_idempotent(pg_store):
    pg_store.upsert_cell(_cell(CellStatus.pending))
    pg_store.upsert_cell(_cell(CellStatus.running))
    pg_store.upsert_cell(_cell(CellStatus.completed))
    cell = pg_store.get_cell(_TEST_CELL)
    assert cell is not None and cell.status is CellStatus.completed


def test_real_append_record_on_conflict_updates(pg_store):
    pg_store.upsert_cell(_cell(CellStatus.running))
    pg_store.append_record(_record(1, 50.0))
    pg_store.append_record(_record(1, 42.0))  # same (cell, iteration) -> ON CONFLICT update
    records = pg_store.get_records(_TEST_CELL)
    assert len(records) == 1 and records[0].test_metrics["rmse"] == 42.0


def test_real_artifact_and_logs_roundtrip(pg_store):
    pg_store.upsert_cell(_cell(CellStatus.running))
    pg_store.save_artifact(cell_id=_TEST_CELL, trigger_iteration=10, artifact={"confirmed_findings": ["x"]}, source_record_ids=[1, 2, 3])
    pg_store.save_artifact(cell_id=_TEST_CELL, trigger_iteration=10, artifact={"confirmed_findings": ["y"]}, source_record_ids=[1, 2, 3])  # upsert
    arts = pg_store.get_artifacts(_TEST_CELL)
    assert len(arts) == 1 and arts[0]["artifact"]["confirmed_findings"] == ["y"]
    S.get_logger(pg_store, _TEST_CELL).info("iteration_done", iteration=1, rmse=42.0)
    assert any(line["event"] == "iteration_done" for line in pg_store.get_logs(_TEST_CELL))
