"""US1 memory-regime tests (T012): per-regime views, edge cases, provenance (FR-002/003/004).

Covers contracts/memory-view.md: recent_only (<= k), all_raw (full + token growth, SC-006),
the fewer-than-k early-history case, compacted_recent before/after the first artifact, and the
provenance fields every view must carry."""

from __future__ import annotations

import pytest

from ds_agent_loop import memory
from ds_agent_loop.prompts import ExperimentRecord, MemoryRegime, Settings


def _history(n: int) -> list[ExperimentRecord]:
    return [
        ExperimentRecord(
            iteration=i,
            dataset_size=100,
            model_name="LinearRegression" if i % 2 else "RandomForestRegressor",
            hyperparameters={"n_estimators": i} if i % 2 == 0 else {},
            metrics={"rmse": 10.0 - i},
            rationale="r",
            timestamp="t",
            cell_id="c",
            regime=MemoryRegime.recent_only,
            seed=0,
            test_metrics={"rmse": 10.0 - i},
        )
        for i in range(1, n + 1)
    ]


def test_recent_only_shows_at_most_k_records():
    view = memory.build_view(MemoryRegime.recent_only, _history(10), k=3, cell_id="c", iteration=11)
    assert view.included_record_ids == [8, 9, 10]
    assert view.included_artifact_id is None
    assert view.regime is MemoryRegime.recent_only


def test_all_raw_shows_full_history():
    view = memory.build_view(MemoryRegime.all_raw, _history(10), k=3, cell_id="c", iteration=11)
    assert view.included_record_ids == list(range(1, 11))


def test_all_raw_token_count_grows_with_history():
    small = memory.build_view(MemoryRegime.all_raw, _history(2), k=3, cell_id="c", iteration=3)
    large = memory.build_view(MemoryRegime.all_raw, _history(8), k=3, cell_id="c", iteration=9)
    assert large.prompt_token_count > small.prompt_token_count  # SC-006


def test_fewer_than_k_records_shows_whatever_exists_no_error():
    view = memory.build_view(MemoryRegime.recent_only, _history(2), k=5, cell_id="c", iteration=3)
    assert view.included_record_ids == [1, 2]  # no padding, no error


def test_empty_history_renders_cleanly():
    view = memory.build_view(MemoryRegime.recent_only, [], k=5, cell_id="c", iteration=1)
    assert view.included_record_ids == []
    assert "No prior experiments" in view.rendered_text


def test_compacted_recent_before_first_trigger_equals_recent_only():
    hist = _history(6)
    compacted = memory.build_view(MemoryRegime.compacted_recent, hist, k=3, cell_id="c", iteration=7)
    recent = memory.build_view(MemoryRegime.recent_only, hist, k=3, cell_id="c", iteration=7)
    assert compacted.included_record_ids == recent.included_record_ids == [4, 5, 6]
    assert compacted.included_artifact_id is None
    assert compacted.rendered_text == recent.rendered_text  # identical pre-trigger


def test_compacted_recent_includes_artifact_and_tail_k_only():
    hist = _history(20)
    artifact = {
        "artifact_id": "c@10",
        "artifact": {
            "confirmed_findings": ["RandomForest beats linear"],
            "failed_directions": ["tiny n_estimators"],
            "promising_directions": ["tune depth"],
            "best_known_configs": [],
            "unresolved_questions": ["does scaling help?"],
            "next_step_recommendation": "increase depth",
            "confidence": 0.7,
        },
    }
    view = memory.build_view(
        MemoryRegime.compacted_recent, hist, k=4, cell_id="c", iteration=21, latest_artifact=artifact
    )
    # artifact + last-4 raw ONLY, never the full history (FR-004)
    assert view.included_record_ids == [17, 18, 19, 20]
    assert view.included_artifact_id == "c@10"
    assert "DIRECTIONAL RESEARCH MEMORY" in view.rendered_text
    assert "RandomForest beats linear" in view.rendered_text


def test_view_carries_content_hash_and_token_count():
    view = memory.build_view(MemoryRegime.recent_only, _history(3), k=3, cell_id="c", iteration=4)
    assert view.content_hash and len(view.content_hash) == 64  # sha256 hex
    assert view.prompt_token_count >= 1


def test_distinct_content_yields_distinct_hash():
    a = memory.build_view(MemoryRegime.recent_only, _history(3), k=3, cell_id="c", iteration=4)
    b = memory.build_view(MemoryRegime.all_raw, _history(3), k=3, cell_id="c", iteration=4)
    assert a.content_hash != b.content_hash


# --- US1 (T010/T011): regime is pure configuration, fail-fast on unknown -----


def test_settings_default_regime_is_recent_only():
    assert Settings(_env_file=None).regime is MemoryRegime.recent_only


def test_settings_selects_regime_from_config():
    assert Settings(_env_file=None, regime="all_raw").regime is MemoryRegime.all_raw


def test_settings_rejects_unknown_regime_fail_fast():
    with pytest.raises(Exception):  # pydantic ValidationError — no silent default (FR-002)
        Settings(_env_file=None, regime="not_a_regime")
