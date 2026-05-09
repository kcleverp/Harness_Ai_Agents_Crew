# pm_build_mvp

AI-powered PM crew for structured MVP product planning.
Uses CrewAI hierarchical process with OpenRouter LLM backend.

---

## Project Structure

```
pm_build_mvp/
├── main.py                          # Entry point
├── .env.example                     # Environment variable template
├── config.json                      # [reference only — not runtime-loaded; see .env for active config]
├── requirements.txt                 # Python dependencies
├── personas/
│   ├── translator.md                # [reference only — content moved to prompts/translator_system.md]
│   ├── pm_director.md               # [reference only — not runtime-loaded]
│   ├── product_pm.md                # [reference only — not runtime-loaded]
│   └── qa_pm.md                     # [reference only — not runtime-loaded]
├── prompts/                         # System prompts — runtime-loaded via prompt_loader.py
│   ├── idea_gen_system.md           # Phase 1: Idea generation
│   ├── idea_critique_system.md      # Phase 1: Critique
│   ├── idea_revise_system.md        # Phase 1: Revision
│   ├── synthesis_system.md          # Phase 2: Synthesis
│   ├── decision_system.md           # Phase 3: Decision
│   ├── founder_summary_system.md    # Phase 4: Founder summary
│   ├── feature_spec_system.md       # Phase 4: Feature spec
│   ├── tech_gen_system.md           # Phase 5: Tech JSON generation
│   ├── tech_review_system.md        # Phase 5: Tech review
│   ├── tech_revise_system.md        # Phase 5: Tech revision
│   ├── product_qa_system.md         # v4 QA gate
│   ├── strategic_qa_founder_system.md  # v4 Strategic QA: Founder
│   ├── strategic_qa_investor_system.md # v4 Strategic QA: Investor
│   ├── decision_council_system.md   # v4 Decision council
│   ├── validation_strategy_system.md   # Phase D: Validation
│   ├── failure_scenario_system.md   # Phase D: Failure scenarios
│   ├── consistency_guardrail_system.md # Phase D: Consistency
│   ├── escalation_system.md         # Escalation routing
│   ├── kernel_guard_header.md       # Kernel guard prefix
│   ├── kernel_guard_footer.md       # Kernel guard suffix
│   ├── patch_agent.md               # Patch crew agent meta
│   └── translator_system.md         # Post-process Korean translator
├── templates/
│   ├── raw_ideas.sample.md          # Sample idea (auto-copied on first run)
│   └── patch_task_description.template.md  # Patch task template
├── workflows/
│   └── planning_workflow.py         # Phase-based planning workflow
├── harness/
│   ├── llm_factory.py               # Role-specific LLM builders (7 required + optional v4)
│   ├── prompt_loader.py             # Prompt/template file loader with cache
│   ├── safe_file_tools.py           # Sandboxed file read/write/patch tools
│   ├── schema_validator.py          # Pydantic HandoffSchema validation
│   ├── audit_hooks.py               # Structured log writers
│   ├── dev_exporter.py              # workspace/current → archive snapshot
│   ├── patch_engine.py              # CrewAI partial JSON patch crew
│   ├── kernel_guard.py              # Founder Kernel loader, hash guard, prompt injector
│   ├── translator_runner.py         # Post-process Korean translation (prompts/translator_system.md)
│   └── risk_engine.py               # Risk score calculator
├── workspace/
│   ├── raw_ideas.md                 # (auto-created on first run) Idea input
│   ├── current/                     # Active run outputs (agents write here)
│   └── archive/                     # Timestamped snapshots per run
└── logs/                            # Runtime log files
```

---

## Setup

### 1. Install dependencies

```bash
cd pm_build_mvp
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` — minimum required (7 role-specific model vars + API key):

```env
# Connection (required)
OPENROUTER_API_KEY=sk-or-...
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1

# Role-based models (all 7 required — startup validation will fail if any are missing)
OPENROUTER_MODEL_IDEA=google/gemini-2.5-flash
OPENROUTER_MODEL_IDEA_CRITIC=openai/gpt-4o-mini
OPENROUTER_MODEL_SYNTHESIS=openai/gpt-4o-mini
OPENROUTER_MODEL_DECISION=anthropic/claude-opus-4-5
OPENROUTER_MODEL_CREATIVE=anthropic/claude-sonnet-4-5
OPENROUTER_MODEL_TECH_GEN=google/gemini-2.5-flash
OPENROUTER_MODEL_TECH_REVIEW=openai/gpt-4o-mini
```

`llm_factory.validate_llm_env()` checks all 7 required role vars at startup and exits(1) on failure.
Optional v4 roles (`STRATEGIC_QA`, `INVESTOR_QA`, `COUNCIL_*`, `VALIDATION`, `FAILURE_SCENARIO`, `CONSISTENCY`, `ESCALATION_*`) print a warning if unset; those phases are skipped.

> **Note**: `OPENROUTER_MODEL` is a legacy var used only by `patch_engine.py`. Do not rely on it for new phase configuration. See `.env.example` for a full annotated template.

### 3. Run

```bash
python main.py
```

Must be run from the `pm_build_mvp/` directory so that relative paths resolve correctly.

---

## Runtime Flow

```
main.py
  └─ init_workspace()           # Creates dirs, auto-generates workspace/raw_ideas.md
  └─ validate_llm_env()         # Checks API key / URL / model — exits(1) on fail
  └─ run_planning()
       ├─ load_founder_kernel()         # Load/create founder_kernel.json + hash
       ├─ run_idea_loop()               # Kernel guard injected; structured critique JSON
       ├─ run_synthesis()               # concept_checkpoint.json
       ├─ run_decision()                # blueprint.md + kernel guard
       ├─ run_product_qa_gate()         # Evidence binding, integrity alert, failure taxonomy
       ├─ run_strategic_qa_gate()       # Founder preservation + market viability (optional)
       ├─ run_decision_council()        # Approval + non-linear confidence clamp (optional)
       ├─ run_creative_production()     # founder_summary.md, feature_spec.md + kernel guard
       ├─ run_technical_production()    # backlog.json, handoff_to_dev.json
       ├─ run_final_validation_and_patch() # Pydantic schema check + patch loop (max 3)
       ├─ run_validation_strategy_engine() # KPI/hypothesis/failure modes (optional)
       ├─ run_consistency_guardrail()   # Cross-document alignment (optional)
       ├─ calculate_risk()              # Risk score 0–100
       └─ create_archive_snapshot()
```

---

## Outputs

| Path | Description |
|---|---|
| `workspace/raw_ideas.md` | Input idea (auto-generated template on first run) |
| `workspace/founder_kernel.json` | Founder thesis kernel with hash |
| `workspace/current/docs/founder_summary.md` | MVP scope distilled by PM Director |
| `workspace/current/docs/founder_summary_ko.md` | Korean translation of founder summary |
| `workspace/current/docs/feature_spec.md` | Feature specs and user stories |
| `workspace/current/docs/concept_draft.md` | Initial concept draft |
| `workspace/current/docs/concept_checkpoint.json` | Synthesized concept checkpoint |
| `workspace/current/docs/blueprint.md` | Architecture and decision blueprint |
| `workspace/current/tech/backlog.json` | Structured backlog |
| `workspace/current/tech/handoff_to_dev.json` | Final dev handoff (HandoffSchema) |
| `workspace/current/qa/product_qa_result.json` | Evidence binding + failure taxonomy |
| `workspace/current/qa/strategic_qa_result.json` | Founder preservation + market viability |
| `workspace/current/qa/consistency_result.json` | Cross-document alignment result |
| `workspace/current/decision/council_decision.json` | Final approval + confidence penalties |
| `workspace/current/validation/validation_strategy.json` | Hypothesis/KPI/failure mode structure |
| `workspace/archive/<timestamp>_<tag>/` | Snapshot of current/ at run end |
| `logs/pm_audit.log` | Workflow lifecycle events |
| `logs/run_summary.log` | Per-run result summary (ok/risk/tasks/patches) |
| `logs/validation_failures.log` | Schema validation errors with coordinates |
| `logs/patch_actions.log` | Partial patch operations |
| `logs/reasoning_trace.jsonl` | Canonical stream — append-only structured events (schema v1: domain/category/event_type) |
| `logs/projections/runtime.log` | Derived: workflow lifecycle events (regenerable) |
| `logs/projections/decisions.log` | Derived: decision/selection/tradeoff events (regenerable) |
| `logs/projections/qa.log` | Derived: qa + system integrity events (regenerable) |
| `logs/views/lineage_index.md` | View: chronological event lineage table (regenerable) |
| `logs/views/pretty.log` | View: human-readable multiline event export (regenerable) |

Archive tag: `todo_mvp` (risk < 70) or `high_risk_pending` (risk ≥ 70).

---

## Terminal Output (success)

```
Initializing PM CrewAI System (Hierarchical Mode)...
Starting Planning Workflow...
Schema Validation Passed.
Risk Level Acceptable (30).
Archived to workspace/archive/2026-05-01_0342_todo_mvp
Workflow finished.
Result => ok=True risk=30 attempts=0 errors=0,
```

---

## Phases

- Phase 1: Scaffolding ✅
- Phase 2: Harness implementation ✅
- Phase 3: Workflow + Main ✅
- Phase 4: Docs & verification ✅
- Phase v4: Final Architecture v4 integration ✅
  - Founder Intent Kernel (kernel_guard.py)
  - Structured critique JSON + confidence scoring
  - Product QA Gate with evidence integrity
  - Strategic QA Gate (optional, warn mode)
  - Decision Council with non-linear confidence clamp (optional)
  - Validation Strategy Engine + failure scenarios (optional)
  - Production Consistency Guardrail (optional)
  - Structured Decision Memory (reasoning_trace.jsonl)
- Phase v5: Forward Observability Refactor ✅
  - Canonical event schema v1 (telemetry_schema.py)
  - Canonical write path unified (audit_hooks.py)
  - Telemetry projections: runtime / decisions / qa (telemetry_projection.py)
  - Views: lineage_index / pretty (telemetry_projection.py)
  - Deterministic reconstruction verification (verify_run_reconstruction)
  - Transition compatibility mode + deprecation warnings

---

## Observability Architecture

### Priority Guardrail

```
build quality  >  orchestration quality  >  observability sophistication
```

Observability infrastructure must never grow larger than the core system it serves.

---

### Log Layer Definitions

| Layer | Files | Role | Immutable? |
|---|---|---|---|
| **Canonical** | `logs/reasoning_trace.jsonl` | Single source of truth. Append-only event stream. | Yes |
| **Projections** | `logs/projections/runtime.log`<br>`logs/projections/decisions.log`<br>`logs/projections/qa.log` | Semantic slices from canonical. Regenerable. | No |
| **Views** | `logs/views/lineage_index.md`<br>`logs/views/pretty.log` | Human-readable rendering. Regenerable. | No |
| **Legacy** (transition) | `logs/pm_audit.log`<br>`logs/decision_history.log`<br>`logs/blueprint_logic.log`<br>`logs/creative_process.log`<br>`logs/patch_actions.log`<br>`logs/run_summary.log`<br>`logs/validation_failures.log` | Phase-centric logs. Kept during transition. **Deprecated.** | No |

**Rule**: Event meaning is declared by the event itself via `domain/category/event_type`. Projections never infer meaning from phase names.

---

### Event Schema v1 — Required Fields

```json
{
  "schema_version": "v1",
  "event_id": "<uuid>",
  "parent_event_id": "<uuid> | null",
  "related_event_ids": [],
  "run_id": "<uuid>",
  "phase": "<phase_name>",
  "domain": "workflow | decision | qa | system | patch | translation",
  "category": "<category_within_domain>",
  "event_type": "<specific_event_type>",
  "artifact": "<filename> | null",
  "timestamp": "<ISO-8601>",
  "details": {}
}
```

`related_event_ids` is reserved for future DAG lineage (default `[]`).

---

### Projection Regeneration Policy

- Projections and views are **disposable**. Delete and regenerate at any time.
- Canonical stream (`reasoning_trace.jsonl`) is **immutable** (append-only, never rewrite).
- Regeneration is **deterministic**: same canonical input + same projection version → hash-equivalent output.
- Regeneration triggers:
  - Manual (operator command): `generate_all_projections(run_id=...)`
  - Automatic: called at end of each `run_planning()` execution
  - After schema/taxonomy change: regenerate full stream

---

### Replay Semantics

Current stage: **replay-ready structure** — the canonical stream is sufficient to reconstruct all derived state.

Reproducible from `reasoning_trace.jsonl`:
- Event lineage rebuild
- Projection rebuild (runtime / decisions / qa)
- View rebuild (pretty / lineage_index)
- Decision outcomes
- QA outcomes
- Artifact transition history

**Out of scope** (future):
- Real-time replay engine
- Distributed event bus
- Graph persistence

**Future Direction**: event replayable orchestration — stateless phase functions that are fully reconstructable from the canonical event stream alone.

---

### Verification

```python
from harness.telemetry_projection import verify_run_reconstruction, generate_all_projections

# Verify a specific run
result = verify_run_reconstruction(run_id="<run_id>")
print(result["ok"], result["anomalies"], result["hashes"])

# Regenerate all projections
generate_all_projections(run_id="<run_id>")   # single run
generate_all_projections()                    # full stream
```
