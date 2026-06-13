# Contract: Memory regime → exact memory view (Principle XIII) — 005 reaffirmation

`memory.build_view` is the single, **unchanged** seam mapping a regime + history (+ latest artifact)
to the exact text the agent sees, with its provenance. Feature 005 does not change its behavior; it
re-keys the surrounding run path to 004 benchmark **members** and adds the verification layer
(see `provenance-api.md`). This file restates the seam contract that replay depends on.

## Interface (unchanged from 003)

```
build_view(
    regime: MemoryRegime,            # recent_only | all_raw | compacted_recent
    history: list[ExperimentRecord], # prior records of THIS cell, in order
    *,
    k: int,
    cell_id: str,
    iteration: int,
    latest_artifact: dict | None = None,
) -> MemoryView
```

## Per-regime behavior (the replay-critical invariants)

| regime | included_record_ids | included_artifact_id | invariant |
|--------|---------------------|----------------------|-----------|
| `recent_only` | last `k` raw records | — | never more than `k`; nothing else from history |
| `all_raw` | every prior raw record | — | full history; `prompt_token_count` grows across iterations |
| `compacted_recent` | last `k` raw records | most recent artifact | artifact + tail-`k` only; NEVER the full raw history; with no artifact yet, identical to `recent_only` |

## Determinism contract (what makes replay possible — FR-008/009)

- `content_hash = sha256(rendered_text)`; `rendered_text` is a pure function of
  `(regime, history_before, k, latest_artifact)`. No clocks, no randomness.
- The caller persists the view with `store.save_view` **before** the agent decides; the resulting
  `ExperimentRecord.memory_view_ref` equals `MemoryView.content_hash`.
- Given the same inputs, `build_view` MUST return a byte-identical `rendered_text` — this is the
  property `provenance.replay_view` asserts. Any change to rendering is a behavior change that MUST be
  reflected as new persisted views (never silently re-hashed).

## Member keying (005 change, outside `build_view`)

`cell_id` is derived from the **004 benchmark member id** (via `cell_id_for`) so every view is keyed
to `(member, seed, regime, iteration)`. The run path resolves the member + frozen split through
`benchmark.load_member` (no on-disk fallback in the run path); the held-fixed factors a view is
compared against come from the member descriptor (see `config_fingerprint`).
