"""Foundational store tests (T009): idempotent upserts, resume-skip, logging, export.

Hermetic — runs against the in-process ``FakeStore`` (research Decision 2), no network.
The real Postgres path shares the same interface and is exercised by the opt-in
integration test (T050)."""

from __future__ import annotations

import json

from ds_agent_loop import store as S
from ds_agent_loop.prompts import (
    CellStatus,
    ExperimentCell,
    ExperimentRecord,
    MemoryRegime,
    MemoryView,
)


def _cell(status: CellStatus = CellStatus.pending) -> ExperimentCell:
    return ExperimentCell(
        cell_id="diabetes|all_raw|s0|k5|m10",
        dataset_id="diabetes",
        regime=MemoryRegime.all_raw,
        seed=0,
        k=5,
        m=10,
        budget=30,
        status=status,
    )


def _record(iteration: int, rmse: float) -> ExperimentRecord:
    return ExperimentRecord(
        iteration=iteration,
        dataset_size=265,
        model_name="LinearRegression",
        metrics={"rmse": rmse},
        rationale="x",
        timestamp="t",
        cell_id="diabetes|all_raw|s0|k5|m10",
        dataset_id="diabetes",
        regime=MemoryRegime.all_raw,
        seed=0,
        test_metrics={"rmse": rmse},
    )


def test_upsert_cell_is_idempotent_and_updates_mutable_fields():
    store = S.FakeStore()
    store.upsert_cell(_cell())
    store.upsert_cell(_cell(CellStatus.running))
    store.upsert_cell(_cell(CellStatus.completed))
    assert len(store.all_cells()) == 1
    assert store.get_cell("diabetes|all_raw|s0|k5|m10").status is CellStatus.completed


def test_append_record_idempotent_on_cell_iteration():
    store = S.FakeStore()
    store.append_record(_record(1, 50.0))
    store.append_record(_record(1, 42.0))  # same (cell, iteration) -> overwrite, not dup
    records = store.get_records("diabetes|all_raw|s0|k5|m10")
    assert len(records) == 1
    assert records[0].metrics["rmse"] == 42.0


def test_records_ordered_by_iteration():
    store = S.FakeStore()
    for it in (3, 1, 2):
        store.append_record(_record(it, float(it)))
    assert [r.iteration for r in store.get_records("diabetes|all_raw|s0|k5|m10")] == [1, 2, 3]


def test_save_view_idempotent_on_cell_iteration():
    store = S.FakeStore()
    view = MemoryView(
        cell_id="diabetes|all_raw|s0|k5|m10",
        iteration=1,
        regime=MemoryRegime.all_raw,
        rendered_text="memory",
        content_hash="h1",
        prompt_token_count=12,
    )
    store.save_view(view)
    store.save_view(view.model_copy(update={"content_hash": "h2", "prompt_token_count": 20}))
    views = store.get_views("diabetes|all_raw|s0|k5|m10")
    assert len(views) == 1 and views[0].content_hash == "h2"


def test_artifact_lineage_persisted_and_latest():
    store = S.FakeStore()
    store.save_artifact(cell_id="c", trigger_iteration=10, artifact={"confirmed_findings": ["a"]}, source_record_ids=[1, 2])
    store.save_artifact(cell_id="c", trigger_iteration=20, artifact={"confirmed_findings": ["b"]}, source_record_ids=[1, 2, 3])
    assert store.latest_artifact("c")["trigger_iteration"] == 20
    assert store.latest_artifact("c")["source_record_ids"] == [1, 2, 3]


def test_resume_skip_detects_completed_cell():
    # The orchestrator's resume rule (SC-007) reads cell status; a completed cell is skipped.
    store = S.FakeStore()
    store.upsert_cell(_cell(CellStatus.completed))
    cell = store.get_cell("diabetes|all_raw|s0|k5|m10")
    assert cell.status in (CellStatus.completed, CellStatus.context_limited, CellStatus.failed)


def test_logger_writes_to_sink():
    store = S.FakeStore()
    log = S.get_logger(store, "c")
    log.info("iteration_done", iteration=1, rmse=1.0)
    log.warning("context_limited", iteration=2)
    logs = store.get_logs("c")
    assert len(logs) == 2
    assert logs[0]["event"] == "iteration_done" and logs[0]["payload"]["rmse"] == 1.0


def test_export_roundtrip(tmp_path):
    store = S.FakeStore()
    store.upsert_cell(_cell(CellStatus.completed))
    store.append_record(_record(1, 50.0))
    S.get_logger(store, "diabetes|all_raw|s0|k5|m10").info("done", iteration=1)
    out = S.export(store, tmp_path, outcomes={"primary": 50.0})
    assert (out / "cells.csv").exists()
    assert (out / "outcomes.json").exists()
    cell_dir = out / S._safe_dir("diabetes|all_raw|s0|k5|m10")
    records = json.loads((cell_dir / "records.json").read_text())
    assert records[0]["iteration"] == 1
    assert (cell_dir / "logs.csv").exists()
