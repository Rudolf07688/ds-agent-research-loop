"""The memory-regime seam: regime + history -> the exact memory view shown (Principle XIII).

``build_view`` is the single constructor behind all three regimes (configuration, not forks
of the loop). It returns a :class:`MemoryView` carrying both the rendered prompt-memory text
the agent receives AND the identifiers of every record/artifact included, so the store can
persist the exact view per decision and any decision is replayable and auditable across
regimes (FR-013; contracts/memory-view.md).

A record is identified within its cell by its ``iteration`` — a stable, per-cell id reused
as the compaction lineage key (``source_record_ids``).
"""

from __future__ import annotations

import hashlib
import json

from .prompts import ExperimentRecord, MemoryRegime, MemoryView

# How many tokens the rendered memory is worth. A deterministic ~4-chars-per-token estimate
# (no model tokenizer needed offline); monotonic in content so all-raw growth is visible
# (SC-006). Not a billing figure — a measured, reproducible proxy.
_CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _record_view(record: ExperimentRecord) -> dict:
    """The compact, agent-facing projection of one prior experiment record."""

    metrics = record.test_metrics or record.metrics
    return {
        "iteration": record.iteration,
        "model_name": record.model_name,
        "hyperparameters": record.hyperparameters,
        "metrics": {k: round(v, 4) for k, v in metrics.items()},
        "improved": record.improved,
        "rejected": record.rejected,
    }


def _render_raw(records: list[ExperimentRecord]) -> str:
    if not records:
        return "No prior experiments yet."
    return json.dumps([_record_view(r) for r in records], indent=2)


def _render_artifact(artifact: dict) -> str:
    """Render a DirectionalMemory belief schema as compact, agent-facing text."""

    def _lines(label: str, items: list) -> str:
        if not items:
            return f"{label}: (none)"
        return label + ":\n" + "\n".join(f"  - {it}" for it in items)

    parts = [
        "DIRECTIONAL RESEARCH MEMORY (compacted prior history):",
        _lines("Confirmed findings", artifact.get("confirmed_findings", [])),
        _lines("Failed directions", artifact.get("failed_directions", [])),
        _lines("Promising directions", artifact.get("promising_directions", [])),
        _lines("Best-known configs", artifact.get("best_known_configs", [])),
        _lines("Unresolved questions", artifact.get("unresolved_questions", [])),
        f"Next-step recommendation: {artifact.get('next_step_recommendation', '')}",
        f"Confidence: {artifact.get('confidence', '')}",
    ]
    return "\n".join(parts)


def build_view(
    regime: MemoryRegime,
    history: list[ExperimentRecord],
    *,
    k: int,
    cell_id: str,
    iteration: int,
    latest_artifact: dict | None = None,
) -> MemoryView:
    """Construct the exact memory view for ``regime`` at ``iteration`` (FR-002/003/004).

    Edge cases (deterministic; contracts/memory-view.md):
      * fewer than ``k`` records early on -> show whatever exists, no padding/error;
      * ``compacted_recent`` before the first compaction trigger (``latest_artifact`` None)
        -> behaves identically to ``recent_only``.
    """

    artifact_id: str | None = None

    if regime is MemoryRegime.all_raw:
        shown = list(history)  # full history; token count grows across iterations (SC-006)
        text = "Full experiment history (most recent last):\n" + _render_raw(shown)
    elif regime is MemoryRegime.recent_only:
        shown = history[-k:] if k > 0 else []
        text = f"Last {k} experiment records (most recent last):\n" + _render_raw(shown)
    elif regime is MemoryRegime.compacted_recent:
        shown = history[-k:] if k > 0 else []
        if latest_artifact is not None:
            artifact_id = latest_artifact.get("artifact_id")
            text = (
                _render_artifact(latest_artifact.get("artifact", {}))
                + f"\n\nPlus the last {k} raw experiment records (most recent last):\n"
                + _render_raw(shown)
            )
        else:
            # Pre-first-trigger: identical behaviour to recent_only.
            text = f"Last {k} experiment records (most recent last):\n" + _render_raw(shown)
    else:  # pragma: no cover - exhaustive enum
        raise ValueError(f"Unknown regime {regime!r}")

    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return MemoryView(
        cell_id=cell_id,
        iteration=iteration,
        regime=regime,
        included_record_ids=[r.iteration for r in shown],
        included_artifact_id=artifact_id,
        rendered_text=text,
        content_hash=content_hash,
        prompt_token_count=estimate_tokens(text),
    )
