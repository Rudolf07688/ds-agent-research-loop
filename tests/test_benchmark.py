"""Foundational benchmark tests (T010): the suite and its frozen, reproducible splits.

Splits must be frozen and byte-for-byte reproducible, independent of the cell seed, and
cover every row exactly once with no overlap (FR-017, SC-002)."""

from __future__ import annotations

from ds_agent_loop import benchmark as B
from ds_agent_loop.prompts import TaskType


def test_default_suite_has_five_datasets_with_metrics():
    descriptors = B.suite()
    assert len(descriptors) == 5
    for d in descriptors:
        assert d.primary_metric in ("rmse", "macro_f1")
        # direction is correct for the metric (FR-023)
        if d.primary_metric == "rmse":
            assert d.task_type is TaskType.regression and d.metric_direction == -1
        else:
            assert d.task_type is TaskType.classification and d.metric_direction == 1
        assert d.feature_names and d.target


def test_suite_mixes_regression_and_classification():
    kinds = {d.task_type for d in B.suite()}
    assert kinds == {TaskType.regression, TaskType.classification}


def test_split_covers_all_rows_without_overlap(tmp_path):
    for dataset_id in B.DEFAULT_SUITE_IDS:
        n = len(B.load_dataset(dataset_id))
        split = B.frozen_split(dataset_id, state_dir=tmp_path)
        idx = split["train"] + split["val"] + split["test"]
        assert sorted(idx) == list(range(n))  # exact cover, no overlap


def test_split_is_frozen_and_reproducible(tmp_path):
    first = B.frozen_split("diabetes", state_dir=tmp_path)
    # second call reads the persisted indices -> identical
    second = B.frozen_split("diabetes", state_dir=tmp_path)
    assert first == second
    assert (tmp_path / "splits" / f"diabetes-{B.BENCHMARK_VERSION}.json").exists()


def test_split_independent_of_recompute_seed(tmp_path):
    # Two fresh state dirs recompute from the fixed SPLIT_SEED -> identical splits,
    # so the split never depends on a cell seed (SC-002).
    a = B.frozen_split("wine", state_dir=tmp_path / "a")
    b = B.frozen_split("wine", state_dir=tmp_path / "b")
    assert a == b
