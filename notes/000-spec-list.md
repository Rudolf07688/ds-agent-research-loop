# Spec Roadmap — Directional Research Memory

> Long-term build plan toward the thesis **Directional Research Memory for Autonomous
> Data-Scientist Agents: Compaction as Momentum in Experiment Space**
> (story: `notes/research/paths/001-directional-research-memory-thesis-story.md`;
> governance: `.specify/memory/constitution.md` v5.0.0).
>
> Each entry is a header-spec: a one-line scope plus the constitution principles and thesis
> chapter it serves. Run each through `/speckit-specify` in order. Features 001–003 already exist.

## Done / In flight

### 001 — AutoDS Loop *(baseline)*
The seed autonomous-data-scientist loop: fixed inner loop (seed → expand → train → next-step →
save), two-schema LLM contract, model allowlist, resumable file state. Foundation everything
else builds on.

### 002 — Live Tests & Containerize *(re-platform)*
Re-platform the LLM backend onto Google Gemini / Vertex AI via a minimal ADK agent; live
verification; portable container that takes credentials/config at run time. (Principles I, II,
III, X.)

### 003 — Memory-Compaction Ablation (A/B/C) *(seed of the study)*
First controlled ablation: recent-only / all-raw / compacted+recent over the loop, Postgres
provenance. **Re-plan note:** adopt "Directional Research Memory" vocabulary, generalize off the
single delivery-time dataset, and fold the per-condition run mechanics into 005–007 below.

## Planned

### 004 — Benchmark Harness & Dataset Suite
Versioned multi-dataset tabular suite (regression **and** classification) with frozen
train/val/test splits, per-dataset fixed action space, fixed experiment budgets, and the widened
regressor+classifier allowlist. State in Postgres, exportable to JSON/CSV. The seed delivery-time
task becomes one member, not the whole project.
*Principles: V, III, IV. Thesis ch. 4.*

### 005 — Memory-Regime Abstraction & Decision Provenance
One interface behind the three regimes (recent-only / all-raw / compacted+recent); regime is pure
configuration, not a fork of the loop. Persist the **exact** memory shown before every decision so
every decision is replayable and regimes are auditable against each other.
*Principles: XIII, IX, IV. Thesis ch. 3.*

### 006 — Directional Research Memory Compaction Operator
The typed belief-schema compaction artifact — what is **true / failed / unresolved**, and which
**directions** to pursue next — as the sanctioned third LLM job. Explicit **outer compaction loop**
with recorded cadence; full source→artifact lineage.
*Principles: XII, II, VIII. Thesis ch. 3.*

### 007 — A/B/C Ablation Study (multi-dataset, multi-seed)
Pre-registered run of all three regimes across the full benchmark over many seeds, with paired
comparisons and significance testing. Successor/expansion of 003.
*Principles: XIV, IX, XI. Thesis ch. 5.*

### 008 — Trajectory & Phase-Transition Analysis
Beyond final scores: sample-efficiency curves, proposal-diversity collapse, repeated-failure and
regret-style measures; locate (or faithfully report the absence of) the raw-history threshold
where adding more history starts to hurt.
*Principles: XIV, XI. Thesis ch. 6.*

### 009 — Theory: Compaction as Momentum / Regret Reduction
Formalize the agent as a dynamical system, state simplifying assumptions, and derive the
momentum/regret argument — checked against, not substituted for, the empirical results.
*Principles: XIV, XI. Thesis ch. 2, 7.*

### 010 — Whitepaper Assembly
Regenerable figures/tables/statistics from persisted runs, compiled through `notes/` into the
final thesis document.
*Principles: XI, VII. Thesis ch. 1, 8.*

## Dependency sketch

```
001 → 002 → 003 ─┐
                 ├→ 004 ─┬→ 005 ─┬→ 006 ─┬→ 007 → 008 → 009 → 010
                 │       │       │       │
                 │  (suite)  (regimes)(compaction)(study)
   (003 mechanics fold into 005–007)
```

- **004** unblocks everything: no fair comparison without fixed datasets/splits/budgets.
- **005 + 006** are the experimental backbone (memory is the only variable; the compaction
  operator is precisely defined).
- **007 → 008 → 009** produce the result, the threshold, and the theory.
- **010** is continuous — `notes/` is kept thesis-ready throughout (Principle VII).
