# Quickstart: Memory-Regime Abstraction & Decision Provenance

Prereqs: Postgres up and migrated (`docker compose up` runs `alembic upgrade head` at startup) and the
004 suite materialized (`uv run python -m ds_agent_loop.benchmark materialize`). 005 adds **no
migration**.

## 1. Run a member under a chosen regime (regime is pure config — US1)

```bash
# Single-run path: select the regime + tail size as configuration.
REGIME=recent_only K=5 uv run ds-agent-loop --member wine --seed 0
REGIME=all_raw            uv run ds-agent-loop --member wine --seed 0
REGIME=compacted_recent K=5 uv run ds-agent-loop --member wine --seed 0
```

- Only the memory shown differs across the three runs; prompts, action space, allowlist, budget,
  split, and scoring are identical (SC-001/002).
- An unknown regime (`REGIME=foo`) fails fast at startup, no silent default (FR-002).

## 2. Inspect the exact memory shown per decision (US2)

```bash
uv run python -m ds_agent_loop.store export ./outputs   # per-cell records.json + memory_views.json
```

Each `memory_views.json` entry carries `rendered_text`, `content_hash`, `included_record_ids`, and the
`(cell_id, iteration)` key; the matching `records.json` entry's `memory_view_ref` equals that hash.

## 3. Verify a cell is replayable (US3 — no LLM calls)

```bash
ds-agent-memory replay --cell wine__recent_only__seed0__k5__m0
# -> ReplayResult: matched 30/30  ok=True       (exit 0)
ds-agent-memory replay --all                    # verify every cell; exit 0 iff all ok
```

Each decision's view is rebuilt from persisted history with `memory.build_view` and its hash compared
to the stored one. A tampered/corrupted view makes replay exit non-zero and list the offending
iteration (FR-009).

## 4. Audit two regimes as a memory-only comparison (US4)

```bash
ds-agent-memory audit \
  --cell-a wine__recent_only__seed0__k5__m0 \
  --cell-b wine__all_raw__seed0__k0__m0
# -> AuditResult: same_member_seed=True  fingerprint_equal=True
#    differing_dimension="regime: recent_only -> all_raw"  ok=True   (exit 0)
```

- If a held-fixed factor actually differs (e.g. different budget or split), the audit exits non-zero
  and names the contaminating factor (FR-011).
- Auditing two cells of different members/seeds is rejected as "not a memory-only comparison".

## 5. What to check (maps to Success Criteria)

| Check | Criterion |
|-------|-----------|
| Three regimes run from config alone, only memory differs | SC-001, SC-002 |
| Every decision has a persisted, hashed, linked view | SC-003 |
| `replay --all` reports 100% hash match, no LLM calls; corruption fails loudly | SC-004 |
| `audit` confirms fingerprint equality and fails on contamination | SC-005 |
| Empty-history first decision is replayable; `k` clamps to available history | SC-006 |
| `memory_views.json` round-trips byte-identically; schema is Alembic-managed | SC-007 |
```
