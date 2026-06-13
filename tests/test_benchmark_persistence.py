"""Feature 004 persistence tests: materialize → load byte-identical, versioning + drift, export
round-trip, and re-materialization idempotency (US2/US3/US5; SC-003/005/006/007).

Hermetic: uses the in-memory ``FakeStore`` so the default suite stays offline and zero-network."""

from __future__ import annotations

import pandas as pd
import pytest

from ds_agent_loop import benchmark as B
from ds_agent_loop import store as S
from ds_agent_loop.prompts import TaskType


# --- T018 [US2]: full-suite materialize → load each member ------------------


def test_materialize_suite_then_load_every_member_byte_identical():
    store = S.FakeStore()
    descriptors = B.materialize_suite(store)
    assert 4 <= len(descriptors) <= 6
    persisted = store.all_benchmark_members(version=B.BENCHMARK_VERSION)
    assert {m["dataset_id"] for m in persisted} == set(B.DEFAULT_SUITE_IDS)

    for d in descriptors:
        desc, split, df = B.load_member(store, d.dataset_id)
        # load_member regenerates rows and asserts the persisted content hash matches.
        recomputed = B.content_hash(
            d.dataset_id, B.BENCHMARK_VERSION,
            {"train": split.train, "val": split.val, "test": split.test},
        )
        assert recomputed == split.content_hash
        assert desc.task_type in (TaskType.regression, TaskType.classification)
        assert len(df) == len(B.load_dataset(d.dataset_id))


def test_load_member_is_identical_across_two_independent_loads():
    # Two separate "processes": two stores materialized independently produce identical members.
    s1, s2 = S.FakeStore(), S.FakeStore()
    B.materialize_suite(s1, ["wine"])
    B.materialize_suite(s2, ["wine"])
    _, split1, df1 = B.load_member(s1, "wine")
    _, split2, df2 = B.load_member(s2, "wine")
    assert split1.content_hash == split2.content_hash
    assert split1.train == split2.train and split1.test == split2.test
    pd.testing.assert_frame_equal(df1, df2)


# --- T019 [US3]: version-drift rejection ------------------------------------


def test_re_materialize_with_changed_fixed_factor_raises_drift():
    store = S.FakeStore()
    B.materialize_suite(store, ["diabetes"])
    # Simulate a prior materialization that used a DIFFERENT fixed factor by corrupting the
    # persisted fingerprint under the same version. Re-materializing must reject the drift.
    member = store.get_benchmark_member("diabetes", B.BENCHMARK_VERSION)
    member["fingerprint"] = "deadbeef-different-factor"
    store.upsert_benchmark_member(member)
    with pytest.raises(B.BenchmarkDriftError):
        B.materialize_suite(store, ["diabetes"])


def test_split_content_hash_divergence_under_same_version_raises():
    store = S.FakeStore()
    B.materialize_suite(store, ["wine"])
    split = store.get_benchmark_split("wine", B.BENCHMARK_VERSION)
    split["content_hash"] = "not-the-real-hash"
    store.upsert_benchmark_split(split)
    with pytest.raises(B.BenchmarkDriftError):
        B.materialize_suite(store, ["wine"])


# --- T020 [US3]: version coexistence ----------------------------------------


def test_new_version_coexists_with_prior_version():
    store = S.FakeStore()
    B.materialize_suite(store, ["iris"], version="v1")
    B.materialize_suite(store, ["iris"], version="v2")
    v1 = store.get_benchmark_member("iris", "v1")
    v2 = store.get_benchmark_member("iris", "v2")
    assert v1 is not None and v2 is not None
    # the version string is part of the content hash, so fingerprints differ but v1 is intact
    assert v1["benchmark_version"] == "v1" and v2["benchmark_version"] == "v2"
    assert v1["fingerprint"] != v2["fingerprint"]
    # the prior version remains independently loadable/attributable
    desc_v1, split_v1, _ = B.load_member(store, "iris", version="v1")
    assert desc_v1.benchmark_version == "v1" and split_v1.benchmark_version == "v1"


# --- T027 [US5]: export round-trip ------------------------------------------


def test_export_member_round_trips_byte_identical(tmp_path):
    store = S.FakeStore()
    B.materialize_suite(store, ["wine"])
    dest = B.export_member(store, "wine", tmp_path)
    assert (dest / "descriptor.json").exists()
    assert (dest / "rows.csv").exists()
    assert (dest / "split.json").exists()

    _, split, df = B.load_member(store, "wine")
    reloaded = pd.read_csv(dest / "rows.csv")
    pd.testing.assert_frame_equal(reloaded, df)
    recomputed = B.content_hash(
        "wine", B.BENCHMARK_VERSION,
        {"train": split.train, "val": split.val, "test": split.test},
    )
    assert recomputed == split.content_hash


# --- T028 [US5]: re-materialization idempotency + loud failure --------------


def test_re_materialization_is_idempotent_no_duplication():
    store = S.FakeStore()
    B.materialize_suite(store)
    before = store.all_benchmark_members(version=B.BENCHMARK_VERSION)
    B.materialize_suite(store)  # no-op: same hashes/fingerprints
    after = store.all_benchmark_members(version=B.BENCHMARK_VERSION)
    assert len(before) == len(after) == len(B.DEFAULT_SUITE_IDS)
    assert {m["dataset_id"] for m in after} == set(B.DEFAULT_SUITE_IDS)


def test_load_member_fails_loud_on_content_hash_divergence():
    store = S.FakeStore()
    B.materialize_suite(store, ["wine"])
    split = store.get_benchmark_split("wine", B.BENCHMARK_VERSION)
    split["train"] = list(split["train_idx"])[:-1]  # tamper the persisted split rows
    split["train_idx"] = split["train"]
    store.upsert_benchmark_split(split)
    with pytest.raises(B.BenchmarkDriftError):
        B.load_member(store, "wine")
