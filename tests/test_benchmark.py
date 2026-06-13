"""Foundational benchmark tests (T010): the suite and its frozen, reproducible splits.

Splits must be frozen and byte-for-byte reproducible, independent of the cell seed, and
cover every row exactly once with no overlap (FR-017, SC-002)."""

from __future__ import annotations

import pytest

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


# ===========================================================================
# Feature 004
# ===========================================================================


# --- T008 [US1]: descriptor validation by task type ------------------------


def test_classification_descriptor_has_classifier_allowlist_and_higher_is_better():
    d = B.get_descriptor("wine")
    assert d.task_type is TaskType.classification
    assert d.primary_metric == "macro_f1" and d.metric_direction == 1
    assert d.model_allowlist and set(d.model_allowlist) <= set(B.CLASSIFIER_ALLOWLIST)


def test_regression_descriptor_has_regressor_allowlist_and_lower_is_better():
    d = B.get_descriptor("diabetes")
    assert d.task_type is TaskType.regression
    assert d.primary_metric == "rmse" and d.metric_direction == -1
    assert d.model_allowlist and set(d.model_allowlist) <= set(B.MODEL_ALLOWLIST)


def test_metric_task_type_mismatch_is_rejected():
    # a regression member declaring a classification metric is rejected at declaration
    with pytest.raises(ValueError):
        B.DatasetDescriptor(
            dataset_id="x", task_type=TaskType.regression, feature_schema={"a": "numeric"},
            target="t", primary_metric="macro_f1", metric_direction=1, split_ref="x-v1",
        )


def test_allowlist_task_type_mismatch_is_rejected():
    # a classification member whose allowlist contains a regressor is rejected
    with pytest.raises(ValueError):
        B.DatasetDescriptor(
            dataset_id="x", task_type=TaskType.classification, feature_schema={"a": "numeric"},
            target="t", primary_metric="macro_f1", metric_direction=1, split_ref="x-v1",
            model_allowlist=["LinearRegression"],
        )


# --- T009 [US1]: content-hash stability + no-LLM synthetic generation -------


def test_content_hash_is_stable_across_processes(tmp_path):
    # Recomputing from the fixed seed in two fresh dirs yields the same content hash (SC-003).
    a = B.frozen_split("breast_cancer", state_dir=tmp_path / "a")
    b = B.frozen_split("breast_cancer", state_dir=tmp_path / "b")
    assert a.content_hash == b.content_hash
    recomputed = B.content_hash("breast_cancer", B.BENCHMARK_VERSION,
                                {"train": a.train, "val": a.val, "test": a.test})
    assert recomputed == a.content_hash


def test_anchored_synthetic_generates_rows_without_an_llm():
    d = B.get_descriptor("delivery_time")
    assert d.provenance == "anchored_synthetic"
    df = B.load_dataset("delivery_time")  # pure-Python generation, no network/LLM
    assert len(df) > 0 and d.target in df.columns


# --- T014 [US2]: suite composition -----------------------------------------


def test_suite_covers_both_task_types_and_provenances_incl_delivery_time():
    descriptors = B.suite()
    assert 4 <= len(descriptors) <= 6
    task_types = {d.task_type for d in descriptors}
    provenances = {d.provenance for d in descriptors}
    assert task_types == {TaskType.regression, TaskType.classification}
    assert provenances == {"anchored_synthetic", "curated_real"}
    assert "delivery_time" in {d.dataset_id for d in descriptors}


# --- T015 [US2]: stratified classification split ----------------------------


def test_stratified_split_preserves_all_classes_and_no_leakage(tmp_path):
    for dataset_id in ("wine", "iris", "breast_cancer"):
        df = B.load_dataset(dataset_id)
        d = B.get_descriptor(dataset_id)
        split = B.frozen_split(dataset_id, state_dir=tmp_path / dataset_id)
        assert split.stratified is True
        classes = set(df[d.target].unique().tolist())
        for part in ("train", "val", "test"):
            present = set(df[d.target].iloc[split[part]].unique().tolist())
            assert present == classes  # every class in every partition
        # no test-row leakage: partitions are disjoint and cover all rows exactly once
        idx = split["train"] + split["val"] + split["test"]
        assert sorted(idx) == list(range(len(df)))
