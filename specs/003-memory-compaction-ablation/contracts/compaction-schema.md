# Contract: Directional Research Memory compaction schema (third LLM job)

**Principle XII / II** — compaction is the **third** sanctioned, schema-constrained LLM call. The
agent is tool-less (ADK `output_schema`); output is JSON validated by `DirectionalMemory`. A
malformed/invalid artifact MUST fail fast (FR-010), never continue with malformed memory.

## `COMPACTION_SCHEMA` (lives in `prompts.py`)

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": [
    "confirmed_findings", "failed_directions", "promising_directions",
    "best_known_configs", "unresolved_questions", "next_step_recommendation",
    "confidence", "rationale"
  ],
  "properties": {
    "confirmed_findings":      {"type": "array", "items": {"type": "string"}},
    "failed_directions":       {"type": "array", "items": {"type": "string"}},
    "promising_directions":    {"type": "array", "items": {"type": "string"}},
    "best_known_configs": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["model_name", "hyperparameters", "metric"],
        "properties": {
          "model_name":      {"type": "string"},
          "hyperparameters": {"type": "object", "additionalProperties": true},
          "metric":          {"type": "number"}
        }
      }
    },
    "unresolved_questions":    {"type": "array", "items": {"type": "string"}},
    "next_step_recommendation":{"type": "string"},
    "confidence":              {"type": "number", "minimum": 0, "maximum": 1},
    "rationale":               {"type": "string"}
  }
}
```

## Call contract (`llm.request_compaction`)

```
request_compaction(
    settings: Settings,
    *,
    source_records_json: str,   # records at/before trigger only — NO future outcomes (FR-008)
    dataset_summary: str,       # task type + primary metric + direction
    allowlist: list[str],
) -> DirectionalMemory          # validated; raises LLMError on schema failure (FR-010)
```

- Reuses `_run_structured` (same minimal ADK agent posture as the two existing calls).
- `output_key="compaction"`; instruction = `COMPACTION_SYSTEM` (project memory of a research run;
  emit only the belief schema; never code).
- Inputs are the source experiment records' JSON; the call MUST NOT receive any record after the
  trigger iteration (enforced by `compaction.py`, asserted in tests; SC-005).

## Outer-loop trigger (`compaction.py`)

- Fires at every `m`-th experiment (fixed cadence; optional token-threshold `t` is FR-024).
- If `< m` source records exist at a trigger, apply the deterministic, logged rule (skip until
  enough, or compact over what exists) — spec Edge Cases.
- Persist the artifact with `source_record_ids` lineage; reuse unchanged until the next trigger.
