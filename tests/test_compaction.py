"""US2 compaction tests (T020) — the Directional Research Memory operator (Principle XII).

Hermetic: the LLM call is injected. Covers the cadence trigger, no-future-leakage source
selection (SC-005), schema validation / fail-fast (FR-010), and the run_cell-level Condition
C behaviour (artifact at each cadence, lineage persisted, agent then sees artifact + tail-k,
never the full raw history — FR-004)."""

from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError

from ds_agent_loop import benchmark as B
from ds_agent_loop import compaction, main
from ds_agent_loop import store as S
from ds_agent_loop.llm import LLMError
from ds_agent_loop.prompts import (
    CellStatus,
    DirectionalMemory,
    ExperimentRecord,
    MemoryRegime,
    NextAction,
    NextStepDecision,
    Settings,
)


def _history(n: int) -> list[ExperimentRecord]:
    return [
        ExperimentRecord(
            iteration=i, dataset_size=100, model_name="RandomForestRegressor",
            metrics={"rmse": 10.0 - i}, rationale="r", timestamp="t",
            cell_id="c", seed=0, test_metrics={"rmse": 10.0 - i},
        )
        for i in range(1, n + 1)
    ]


def _valid_artifact() -> dict:
    return {
        "confirmed_findings": ["RandomForest beats linear"],
        "failed_directions": ["tiny n_estimators"],
        "promising_directions": ["tune depth"],
        "best_known_configs": [{"model_name": "RandomForestRegressor", "hyperparameters": {}, "metric": 5.0}],
        "unresolved_questions": ["does scaling help?"],
        "next_step_recommendation": "increase depth",
        "confidence": 0.6,
        "rationale": "rf dominates",
    }


# --- trigger + source selection -------------------------------------------------------


def test_should_compact_fires_at_multiples_of_m():
    assert compaction.should_compact(10, 10) and compaction.should_compact(20, 10)
    assert not compaction.should_compact(11, 10)
    assert not compaction.should_compact(5, 0)  # m=0 disables


def test_should_compact_token_threshold_is_secondary_trigger():
    # FR-024: optional token-threshold mode fires off-cadence when memory is large...
    assert compaction.should_compact(3, 10, prompt_tokens=500, token_threshold=400)
    assert not compaction.should_compact(3, 10, prompt_tokens=300, token_threshold=400)
    # ...and the fixed cadence still fires regardless of tokens.
    assert compaction.should_compact(10, 10, prompt_tokens=0, token_threshold=400)


def test_select_source_excludes_future_records():
    hist = _history(15)
    source = compaction.select_source(hist, trigger_iteration=10)
    assert [r.iteration for r in source] == list(range(1, 11))  # no records after the trigger (SC-005)
    assert max(r.iteration for r in source) <= 10


def test_select_source_compacts_over_what_exists_when_fewer_than_m():
    hist = _history(3)
    source = compaction.select_source(hist, trigger_iteration=10)
    assert [r.iteration for r in source] == [1, 2, 3]  # clarification 2026-06-13


# --- schema validation / fail fast (FR-010) -------------------------------------------


def test_directional_memory_validates_a_good_artifact():
    DirectionalMemory.model_validate(_valid_artifact())


def test_directional_memory_rejects_missing_field():
    bad = _valid_artifact()
    del bad["next_step_recommendation"]
    with pytest.raises(ValidationError):
        DirectionalMemory.model_validate(bad)


def test_directional_memory_rejects_out_of_range_confidence():
    bad = _valid_artifact()
    bad["confidence"] = 1.5
    with pytest.raises(ValidationError):
        DirectionalMemory.model_validate(bad)


def test_compact_propagates_request_failure_fast():
    async def boom(settings, **kwargs):
        raise LLMError("schema validation failed")

    d = B.get_descriptor("diabetes")
    with pytest.raises(LLMError):
        asyncio.run(compaction.compact(Settings(_env_file=None), source_records=_history(5), descriptor=d, request_fn=boom))


def test_compact_returns_artifact_dict_from_injected_request():
    async def fake_request(settings, *, source_records_json, dataset_summary, allowlist):
        return DirectionalMemory.model_validate(_valid_artifact())

    d = B.get_descriptor("diabetes")
    art = asyncio.run(compaction.compact(Settings(_env_file=None), source_records=_history(5), descriptor=d, request_fn=fake_request))
    assert art["next_step_recommendation"] == "increase depth"
    assert art["confidence"] == 0.6


# --- run_cell Condition C integration -------------------------------------------------


def _keep_rf():
    async def propose(settings, **kwargs):
        return NextStepDecision(action=NextAction.keep_model, model_name="RandomForestRegressor", hyperparameters={}, reason="keep")
    return propose


def _fake_compactor():
    calls = {"n": 0}

    async def compactor(settings, *, source_records, descriptor):
        calls["n"] += 1
        art = _valid_artifact()
        art["rationale"] = f"triggered with {len(source_records)} records"
        return art

    return compactor, calls


def test_condition_c_generates_artifacts_at_cadence_with_lineage(tmp_path):
    store = S.FakeStore()
    d = B.get_descriptor("diabetes")
    compactor, calls = _fake_compactor()
    cell = asyncio.run(
        main.run_cell(
            d, MemoryRegime.compacted_recent, seed=0, k=3, m=5, iterations=12,
            store=store, settings=Settings(_env_file=None), state_dir=tmp_path,
            propose=_keep_rf(), compactor=compactor,
        )
    )
    assert cell.status is CellStatus.completed
    artifacts = store.get_artifacts(cell.cell_id)
    # triggers at iterations 5 and 10 (m=5, budget 12)
    assert [a["trigger_iteration"] for a in artifacts] == [5, 10]
    assert calls["n"] == 2
    # lineage: only records at/before the trigger (SC-005)
    first = artifacts[0]
    assert max(first["source_record_ids"]) <= 5 and first["source_record_ids"] == [1, 2, 3, 4, 5]


def test_condition_c_agent_sees_artifact_plus_tail_k_after_trigger(tmp_path):
    store = S.FakeStore()
    d = B.get_descriptor("diabetes")
    compactor, _ = _fake_compactor()
    cell = asyncio.run(
        main.run_cell(
            d, MemoryRegime.compacted_recent, seed=0, k=3, m=5, iterations=8,
            store=store, settings=Settings(_env_file=None), state_dir=tmp_path,
            propose=_keep_rf(), compactor=compactor,
        )
    )
    views = {v.iteration: v for v in store.get_views(cell.cell_id)}
    # before the first trigger: no artifact in the view
    assert views[3].included_artifact_id is None
    # after the trigger at 5: the view carries the artifact AND only the last k=3 raw records (FR-004)
    after = views[7]
    assert after.included_artifact_id is not None
    assert len(after.included_record_ids) <= 3
    assert "DIRECTIONAL RESEARCH MEMORY" in after.rendered_text
