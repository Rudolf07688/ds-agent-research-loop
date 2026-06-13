# Technical Guideline: Async Memory Compaction for Autonomous Research Agents

## Purpose

This guideline describes a practical memory architecture for an autonomous research or data-scientist agent that must operate over long experimental horizons without collapsing under raw context growth. The design uses Postgres as the source of truth, optional Weaviate as a semantic retrieval layer, and a hybrid compaction system that combines asynchronous background memory generation with synchronous runtime context assembly.[web:104][web:157][web:168]

## Core principle

The memory compactor should run **mostly asynchronously**, but not exclusively asynchronously. A robust system separates durable memory generation from prompt-time working-context compaction, because those two operations serve different roles and have different latency requirements.[web:104][web:161][web:166]

## Architectural split

Use two related but distinct processes:

| Process | Mode | Purpose |
|---|---|---|
| Durable memory generation | Async background task | Extract high-value findings, semantic memories, embeddings, and candidate compaction artifacts |
| Working-context compaction | Sync or near-sync runtime step | Shrink and assemble the active context safely before the next planning step |

This split follows emerging long-running agent patterns in which memory extraction and vectorization can happen in the background, while prompt-safe context shaping must still happen at decision time.[web:157][web:160][web:168]

## Recommended system layers

The architecture should be organized into three memory planes:

1. **Raw state plane** — Postgres experiment logs, metrics, prompts, compactions, lineage, and run metadata.
2. **Durable memory plane** — structured compaction artifacts plus semantic memory objects stored in Weaviate or another vector store.
3. **Active context plane** — the bounded, runtime prompt view assembled synchronously for the next experiment-planning step.

This layered design prevents the agent from carrying its full history in-context forever and instead allows it to retrieve only what is needed at runtime.[web:162][web:168]

## Async background compactor

The background compactor should be responsible for generating durable memory that does not need to block every agent step.

### Trigger conditions

The async compactor may be triggered by:
- every `N` completed experiments,
- estimated prompt-token growth crossing a threshold,
- a research phase boundary,
- explicit agent request,
- or a scheduled periodic job.[web:104][web:158]

### Responsibilities

The async compactor should:
- read recent experiment runs from Postgres,
- identify high-value outcomes,
- generate or refresh structured compaction artifacts,
- extract durable semantic memories,
- embed memory objects,
- write semantic memories into Weaviate,
- store lineage, timestamps, and confidence back into Postgres.[web:157][web:160]

### Output artifacts

Typical durable outputs include:
- compacted research summaries,
- stable findings,
- failed directions,
- open questions,
- procedural heuristics,
- semantic memory objects,
- embedding references and retrieval metadata.

## Sync planner-time context assembly

Before every new experiment proposal, the planner should synchronously build the context it will actually see.

### Required retrieval order

A recommended retrieval order is:
1. fetch current project and dataset state from Postgres,
2. fetch best runs and latest recent runs,
3. fetch the latest valid compaction snapshot,
4. retrieve top-k semantic memories from Weaviate,
5. assemble a bounded active context for the planner.

This step must be synchronous because the planner needs a deterministic working set at the moment of decision.

## Emergency sync compaction

The system should also include a fallback synchronous compaction path.

If the planner needs to act and:
- no valid compaction exists,
- or the assembled prompt would exceed the token budget,

then the system should trigger an emergency safe-compaction step before handing control back to the planner. This fallback should be rare, but it is necessary for robustness when the async layer lags or fails.[web:166][web:164]

## Agent-triggered compaction

The agent should be able to request compaction, but the system should not rely on the agent alone to do so.

### Recommended trigger model

Use a hybrid policy:
- **Programmatic triggers** for reliability, for example every 10 runs or after a token threshold is crossed.
- **Agent-triggered requests** for adaptivity, for example when the model decides that enough has changed to justify a new summary.[web:158][web:104]

This gives the system both predictable maintenance and situational flexibility.

## Role of Weaviate

If a vector store such as Weaviate is added, it should be treated as a **semantic retrieval substrate**, not the entire memory system. Vector stores are useful for retrieving semantically similar prior findings, but they do not by themselves solve promotion, deduplication, contradiction handling, or memory governance.[web:143][web:147][web:152]

### Good objects to store semantically

Store memory objects such as:
- distilled findings,
- failed directions,
- procedural heuristics,
- unresolved hypotheses,
- compaction outputs,
- durable research beliefs.[web:110][web:151][web:152]

### Bad objects to store naively

Avoid blindly embedding:
- every raw experiment row,
- every hyperparameter combination,
- every log line,
- large prompt dumps.

Long-term semantic memory should be selective and policy-governed, not a raw archive.[web:147][web:151]

## Recommended retrieval model

The planner should combine three retrieval channels:

| Channel | Source | Purpose |
|---|---|---|
| Relational retrieval | Postgres | Exact facts, best scores, latest runs, known configs |
| Semantic retrieval | Weaviate | Meaning-based recall of findings, failures, and heuristics |
| Compacted retrieval | Postgres compaction artifacts | High-level research direction and durable conclusions |

This creates a multi-memory system instead of a single prompt-history mechanism, which is more aligned with current thinking on episodic, semantic, and procedural memory for agents.[web:151][web:154]

## Suggested event-driven flow

A practical workflow is:

1. Experiment run completes.
2. Run and metrics are written to Postgres.
3. Event `experiment.completed` is emitted.
4. Background worker evaluates whether memory extraction or compaction should run.
5. If triggered, the worker generates or refreshes compaction artifacts.
6. Durable semantic memories are extracted and embedded.
7. Embeddings and memory objects are written to Weaviate.
8. Planner requests the next action.
9. Context builder assembles bounded context from Postgres and Weaviate.
10. If context is too large and no current compaction exists, emergency sync compaction runs.
11. Planner receives final working context and proposes the next experiment.

## Operational recommendations

### Keep Postgres as source of truth
Postgres should remain authoritative for:
- experiment lineage,
- metrics,
- run status,
- compaction lineage,
- prompt versioning,
- and reproducibility metadata.

### Use Weaviate only for semantic access
Weaviate should be used to accelerate meaning-based retrieval, not to replace structured experiment records.[web:143][web:145][web:152]

### Version compactions
Every compaction artifact should be versioned and traceable back to its source runs. This is important for later audit, debugging, and academic reporting.

### Keep compaction structured
Compaction outputs should use explicit fields such as:
- confirmed findings,
- failed directions,
- promising directions,
- best-known configurations,
- unresolved questions,
- next-step recommendations,
- rationale,
- confidence.

Structured compaction is much more useful than free-form prose for both retrieval and evaluation.

## Research implications

This architecture supports deeper research questions beyond simple summarization. It allows controlled study of:
- async versus inline compaction,
- agent-triggered versus system-triggered memory updates,
- semantic retrieval versus compacted directionality,
- and how autonomous agents build, maintain, and govern a body of scientific knowledge over time without collapsing into noise, dogma, or incoherence.[web:118][web:142]

## Recommended implementation stance

For a practical research system:
- run durable memory extraction asynchronously,
- keep planner-time context assembly synchronous,
- include a synchronous emergency compaction fallback,
- allow both system-triggered and agent-triggered compaction,
- and treat vector memory as one layer in a broader governed memory architecture.[web:104][web:157][web:166][web:168]

This is the most balanced design for long-running autonomous research agents because it preserves responsiveness, limits prompt bloat, and creates a clear separation between storage, consolidation, retrieval, and decision-making.
