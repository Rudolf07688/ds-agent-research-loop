"""The outer compaction loop — Directional Research Memory (Principle XII).

Distinct from the inner experiment loop: on a fixed cadence ``m`` the trajectory recorded
so far is re-read and projected into a single structured belief artifact (the third
sanctioned LLM call). Compaction sees ONLY experiments at or before the trigger iteration
— never any future outcome (FR-008, SC-005). When fewer than ``m`` source records exist at
a trigger, it compacts over whatever exists (deterministic + logged; clarification
2026-06-13). The caller (``run_cell``) persists the artifact with its source lineage.
"""

from __future__ import annotations

import json

from . import llm
from .prompts import ExperimentRecord


def should_compact(
    iteration: int,
    m: int,
    *,
    prompt_tokens: int | None = None,
    token_threshold: int | None = None,
) -> bool:
    """Compaction trigger. Fixed-cadence by default — fire at every ``m``-th experiment
    (FR-006). The optional secondary token-threshold mode (FR-024) ALSO fires when the
    current memory is estimated to exceed ``token_threshold`` tokens."""

    if m > 0 and iteration % m == 0:
        return True
    if token_threshold is not None and prompt_tokens is not None and prompt_tokens > token_threshold:
        return True
    return False


def select_source(history: list[ExperimentRecord], trigger_iteration: int) -> list[ExperimentRecord]:
    """Records at or before the trigger only — enforces no future-outcome leakage (FR-005, SC-005).

    The compaction operator (Principle XII) MUST see only experiments that existed at the trigger:
    no record with ``iteration > trigger_iteration`` may ever enter the source set. If fewer than
    ``m`` exist this still returns whatever is present (compact-over-what-exists; deterministic +
    logged, clarification 2026-06-13). This invariant is the producer-side half of the lineage the
    deterministic audit (``provenance.audit_compaction``) later checks against persisted history.
    """

    source = [r for r in history if r.iteration <= trigger_iteration]
    # No-future-leakage invariant, pinned at the seam (the audit re-proves it from persisted state).
    assert all(r.iteration <= trigger_iteration for r in source), "future record leaked into source"
    return source


def trigger_mode_for(
    iteration: int,
    m: int,
    source_count: int,
    *,
    prompt_tokens: int | None = None,
    token_threshold: int | None = None,
) -> str:
    """Classify which trigger mode actually fired at this compaction point (FR-006, recorded
    with the artifact). ``fixed`` — the exact ``m``-th cadence. ``compact_over_what_exists`` —
    an off-cadence fire over a short window (fewer than ``m`` source records). ``token_threshold``
    — the optional secondary trigger when memory exceeds the token budget off-cadence (FR-024)."""

    if m > 0 and iteration % m == 0:
        return "fixed"
    if source_count < m:
        return "compact_over_what_exists"
    return "token_threshold"


def _source_json(source_records: list[ExperimentRecord]) -> str:
    """Compact JSON projection of the source experiments for the compactor prompt."""

    rows = [
        {
            "iteration": r.iteration,
            "model_name": r.model_name,
            "hyperparameters": r.hyperparameters,
            "metrics": {k: round(v, 4) for k, v in (r.test_metrics or r.metrics).items()},
            "improved": r.improved,
            "rejected": r.rejected,
        }
        for r in source_records
    ]
    return json.dumps(rows, indent=2)


async def compact(settings, *, source_records, descriptor, request_fn=None) -> dict:
    """Produce a Directional Research Memory artifact (as a dict) from the source records.

    ``request_fn`` is injectable for hermetic tests; it defaults to the real Vertex/Gemini
    structured call. The operator is the only third sanctioned LLM job and emits a
    schema-validated ``DirectionalMemory`` (Principles II, XII): malformed / non-conforming
    output MUST fail fast as ``LLMError`` and is NEVER persisted (FR-002). The fail-fast happens
    inside ``request_fn`` (Pydantic validation of the structured response); this function only
    returns once a conforming artifact exists, so the caller never writes a malformed one.
    """

    request_fn = request_fn or llm.request_compaction
    from .train import allowlist_for  # local import avoids a module cycle

    allowlist = list(allowlist_for(descriptor.task_type))
    dataset_summary = (
        f"{descriptor.dataset_id} ({descriptor.task_type.value}), "
        f"primary metric {descriptor.primary_metric}"
    )
    artifact = await request_fn(
        settings,
        source_records_json=_source_json(source_records),
        dataset_summary=dataset_summary,
        allowlist=allowlist,
    )
    return artifact.model_dump(mode="json")
