# Contract: Provenance API (replay, fingerprint, audit) + `memory` CLI

New module `provenance.py`. Pure, deterministic, **no LLM calls** (Principle IX). Reads persisted
state via the `store` interface (real `Store` or `FakeStore`). Reuses `memory.build_view` for
rebuilds so "rebuilt" and "shown" are produced by identical code.

## Library API

```python
def replay_view(
    record: ExperimentRecord,
    history_before: list[ExperimentRecord],
    *,
    artifact: dict | None = None,
) -> ReplayMismatch | None:
    """Rebuild the view for `record` from `history_before` (records with iteration < record.iteration)
    under record.regime/record.k (+ artifact for compacted). Return None if the rebuilt content_hash
    equals record.memory_view_ref, else a ReplayMismatch. No LLM calls. (FR-008/009)"""

def verify_cell(store, cell_id: str) -> ReplayResult:
    """Replay every recorded decision of `cell_id` in order; return a ReplayResult. ok == all matched.
    Reads records, views, and (for compacted) the artifact current at each iteration. (FR-008/009, US3)"""

def config_fingerprint(cell: ExperimentCell, descriptor: DatasetDescriptor) -> str:
    """SHA-256 over a canonical (sorted-key) JSON of held-fixed factors — prompt/schema version,
    action space, allowlist, budget, patience, split_ref + benchmark_version, primary metric +
    direction, seed — EXCLUDING regime, k, and memory content. Deterministic. (FR-010)"""

def audit_regimes(store, cell_id_a: str, cell_id_b: str) -> AuditResult:
    """Audit two cells as a memory-only comparison: gate on same (member, seed); assert equal
    config_fingerprint (name the first differing factor on mismatch); on success report the
    regime/k difference and expose per-iteration view pairs. (FR-011, US4)"""
```

### Guarantees

| Guarantee | Enforced by |
|-----------|-------------|
| Replay makes no LLM calls; reads only persisted state | `verify_cell` / `replay_view` (FR-008) |
| Rebuilt hash must equal stored hash; else loud mismatch naming the iteration | `replay_view` (FR-009, Principle X) |
| Corrupted/tampered view fails verification | hash comparison in `verify_cell` |
| Fingerprint excludes regime, k, memory | `config_fingerprint` (FR-010, Decision 2) |
| Audit rejects different-(member, seed) pairs as not-a-comparison | `audit_regimes` gate (FR-011) |
| Audit fails loudly naming a contaminating held-fixed factor | `audit_regimes` (FR-011) |
| Empty-history / k-clamp / compacted-fallback views replay identically | reuse of `build_view` (FR-013) |

## CLI

A thin subcommand group mirroring the 004 `benchmark` CLI (`argparse` `add_subparsers`), backed by
the library above. Registered in `[project.scripts]` (e.g. `ds-agent-memory = "ds_agent_loop.provenance:main"`).

```
memory replay --cell <cell_id>            # verify_cell; exit non-zero + list mismatches on failure
memory replay --all                       # verify every cell in the store
memory audit --cell-a <id> --cell-b <id>  # audit_regimes; exit non-zero on contamination/invalid pair
```

| Command | Output | Exit code |
|---------|--------|-----------|
| `replay --cell` | `ReplayResult` summary (matched/total) + mismatches | 0 if ok else 1 |
| `replay --all` | per-cell `ReplayResult` lines | 0 iff all cells ok |
| `audit` | `AuditResult` summary (gate, fingerprint, differing dimension) | 0 if ok else 1 |

Verification is **on demand only** — never invoked from the loop run path (clarification 2026-06-13).
