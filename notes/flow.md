# Demo Flow — what `scripts/demo.sh` actually runs

A code-level trace of [`scripts/demo.sh`](../scripts/demo.sh). The script is five shell
steps; each shells out to a console entry point (`ds-agent-loop`, `ds-agent-memory`, or a
`python -m …` module) that drives the library in `src/ds_agent_loop/`. Everything runs offline
because `demo.sh` exports `STUB_LLM=1`, which swaps the real Vertex/Gemini calls for
deterministic in-process stubs.

> `member|regime|s<seed>|k<k>|m<m>` is a *cell* — one experiment run. The demo records two
> cells (`recent_only` + `compacted_recent`), then exports, analyses, and audits them.

---

## 1. Top-level: the five demo steps

```mermaid
flowchart TD
    sh["scripts/demo.sh<br/>(STUB_LLM=1)"]

    sh --> S1["Step 1 — run 2 cells<br/>ds-agent-loop × {recent_only, compacted_recent}"]
    S1 --> S2["Step 2 — export evidence<br/>python -m ds_agent_loop.store export"]
    S2 --> S3["Step 3 — analyse<br/>python -m ds_agent_loop.analysis"]
    S3 --> S4["Step 4 — cross-regime audit<br/>ds-agent-memory audit"]
    S4 --> S5["Step 5 — compaction lineage audit<br/>ds-agent-memory compaction"]

    S1 -. writes .-> PG[("Postgres<br/>cells · records · views · artifacts")]
    S2 -. reads PG, writes .-> EXP["outputs/export/*.json,*.csv"]
    S3 -. reads .-> EXP
    S3 -. writes .-> AN["outputs/analysis/*.png<br/>notes/ablation_results.html"]
    S4 -. reads .-> PG
    S5 -. reads .-> PG

    classDef store fill:#fdf6e3,stroke:#b58900;
    classDef art fill:#eef7ee,stroke:#2e7d32;
    class PG store;
    class EXP,AN art;
```

---

## 2. Step 1 — `ds-agent-loop` runs one cell

Console script `ds-agent-loop` → `main.main()`. The `STUB_LLM` branch (added for the demo)
wires the offline proposer/compactor before delegating to the shared `run_cell` loop.

```mermaid
flowchart TD
    A["main.main()"] --> B["_parse_args(settings)"]
    B --> C["_run_single_cell(args, settings)"]

    C --> D["store.upgrade_to_head()<br/>(alembic upgrade head)"]
    C --> E["make_engine() → Store(engine)"]
    C --> F["benchmark.materialize_suite()<br/>benchmark.load_member()"]
    C --> G{"regime ==<br/>compacted_recent?"}
    G -- yes --> H["compactor = compaction.compact"]
    G -- no --> I["compactor = None"]
    H --> J
    I --> J{"STUB_LLM set?<br/>(_stub_enabled)"}
    J -- yes --> K["propose = _stub_propose<br/>compactor → _stub_compactor"]
    J -- no --> L["propose = None<br/>(real Vertex/Gemini)"]
    K --> M["run_cell(...)"]
    L --> M

    classDef stub fill:#eef2ff,stroke:#3949ab;
    class K stub;
```

---

## 3. Inside `run_cell` — the per-iteration loop

For `i = 1 … iterations`: build the exact memory view → ask the agent → validate → train/score
→ persist the view and the record. For `compacted_recent`, an **outer compaction loop** fires
at cadence `m`. This is where the green audits in steps 4–5 get their evidence.

```mermaid
flowchart TD
    start(["for i in 1..iterations"]) --> V["memory.build_view(regime, history, k, latest_artifact)<br/>→ rendered text + content_hash"]
    V --> base{"i == 1?"}
    base -- yes --> BL["baseline model<br/>(no agent call)"]
    base -- no --> P["await propose(...)<br/>(_stub_propose | real LLM)"]
    P --> AS{"action in<br/>frozen action_space?"}
    AS -- no --> REJ["reject · retain prev model"]
    AS -- yes --> VAL["train.validate_decision()"]
    VAL -->|ok| APP["_apply_decision()"]
    VAL -->|ValidationRejected| REJ
    BL --> SV
    REJ --> SV
    APP --> SV["store.save_view(view)<br/>(persisted BEFORE the record)"]
    SV --> SC["train.score_on_split()<br/>→ val/test metrics"]
    SC --> REC["build ExperimentRecord<br/>(memory_view_ref = view.content_hash)"]
    REC --> AR["store.append_record() · history.append()"]

    AR --> CK{"compacted_recent<br/>AND should_compact(i, m)?"}
    CK -- no --> nxt
    CK -- yes --> CS["compaction.select_source(history, i)<br/>(records at/before trigger only)"]
    CS --> CM["await compactor(...)<br/>→ DirectionalMemory artifact"]
    CM --> CSA["store.save_artifact(trigger=i, cadence=m,<br/>source_record_ids, trigger_mode)"]
    CSA --> UL["latest_artifact = store.latest_artifact()"]
    UL --> nxt(["next i"])
    nxt --> start

    note["memory_view_ref is hashed from in-memory records<br/>with sort_keys=True → reproducible after a JSONB reload<br/>(this is what makes step-4/5 replay green)"]:::n
    REC -.-> note
    classDef n fill:#fff8e1,stroke:#f9a825,font-size:11px;
```

---

## 4. Steps 2–5 — export, analyse, audit

The agent never runs again here; these steps only read persisted state. The two audits are
**deterministic and make zero LLM calls**.

```mermaid
flowchart LR
    subgraph Export["Step 2 · store.export()"]
      X1["read cells/records/<br/>views/artifacts"] --> X2["write JSON + CSV<br/>(artifacts.json = lineage)"]
    end
    subgraph Analyse["Step 3 · analysis"]
      Y1["load_export()"] --> Y2["analyze()"] --> Y3["token_growth.png<br/>paired_differences.png<br/>ablation_results.html"]
    end
    subgraph AuditR["Step 4 · provenance.audit_regimes()"]
      Z1["load both cells"] --> Z2["config_fingerprint(A) == (B)?"] --> Z3["[ok] memory was the<br/>only variable"]
    end
    subgraph AuditC["Step 5 · provenance.audit_compaction()"]
      W1["for each artifact"] --> W2["reconstruct records<br/>at/before trigger from history"] --> W3["== recorded source_record_ids?"] --> W4["[ok] no signal dropped"]
    end

    Export --> Analyse
```

---

## Key files

| Concern | File |
|---|---|
| Orchestrator + `run_cell` loop + `STUB_LLM` wiring | `src/ds_agent_loop/main.py` |
| Memory view rendering (`build_view`, `sort_keys` fix) | `src/ds_agent_loop/memory.py` |
| Compaction operator (`should_compact`, `select_source`, `compact`) | `src/ds_agent_loop/compaction.py` |
| Train / validate / score | `src/ds_agent_loop/train.py` |
| Persistence (Postgres) + `export` | `src/ds_agent_loop/store.py` |
| Replay + cross-regime + compaction audits | `src/ds_agent_loop/provenance.py` |
| Analysis + report | `src/ds_agent_loop/analysis.py` |
