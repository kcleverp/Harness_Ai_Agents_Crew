# pm_build_mvp

AI-powered PM crew for structured MVP product planning.
Uses CrewAI hierarchical process with OpenRouter LLM backend.

**Hybrid OS Console** — FastAPI server + SSE + React frontend for live run monitoring,
founder intent review, workspace browsing, and kernel editing.

---

## Hybrid OS Console (FastAPI + SSE + React)

### Architecture

```
pm_build_mvp/
├── server/           FastAPI — runs, SSE events, intent gate, workspace, kernel, decisions, agent profiles, documents
├── frontend/         React + Vite — Live Feed, Intent Review, Workspace, Kernel, Decisions
├── harness/          Core engine (audit_hooks, event_stream, intent_review, pm_reconstruction, cognitive_*, telemetry_*)
└── workflows/        planning_workflow + phases/upstream (legacy Layer 1~3 fallback)
```

### Quick start

**한 번에 실행** (API + React, `pm_build_mvp/`에서):

```bash
cp .env.example .env   # configure OPENROUTER_* keys
npm run dev:setup      # pip install + frontend npm install + root npm install
npm run dev            # API: free port from 8000↑ + UI :5173
```

시작 시 콘솔에 실제 API 포트가 출력됩니다 (예: `[dev] API http://127.0.0.1:8003`).  
8000이 막혀 있으면 8001, 8002… 순으로 자동 탐색합니다.

> `npm install` alone only installs the root's `concurrently` devDependency — it does **not** install `frontend/`'s dependencies (no npm workspaces configured). Use `npm run dev:setup`, or run `npm install --prefix frontend` separately.

선택 env:
- `PM_API_PORT=8080` — 탐색 시작 포트 (기본 8000)
- `PM_API_PORT_MAX=50` — 최대 시도 개수 (기본 50)

브라우저: **http://localhost:5173**

---

**터미널 분리 실행** (디버깅용):

**Terminal 1 — API server** (from `pm_build_mvp/`):

```bash
pip install -r requirements.txt
cp .env.example .env   # configure OPENROUTER_* keys
uvicorn server.main:app --reload --port 8000
```

**Terminal 2 — React dev server**:

```bash
cd frontend
npm install
npm run dev    # http://localhost:5173 — proxies /runs, /kernel to :8000
```

Open the console → **Start Run**. Live Feed receives SSE events from `GET /runs/{id}/events`.

### SSE contract

| Item | Value |
|---|---|
| Endpoint | `GET /runs/{run_id}/events` |
| Format | `data: {canonical event JSON}\n\n` |
| Backfill | Full `reasoning_trace.jsonl` for run_id on connect |
| Live | In-proc pub/sub via `harness/event_stream.py` |
| End | `event: end\ndata: {}\n\n` when run reaches terminal state |
| Terminal states | `complete`, `failed`, `rejected` |

### REST endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Health check |
| POST | `/runs` | Start workflow thread (one active run max) |
| GET | `/runs` | List all runs |
| GET | `/runs/{id}` | Run status (`running` / `awaiting_choice` / `complete` / …) |
| GET | `/runs/{id}/events` | SSE event stream |
| GET | `/runs/{id}/intent-review` | Layer 0.5 review document |
| POST | `/runs/{id}/intent-choice` | Founder decision (`proceed` / `reject` / `edit`) |
| GET | `/runs/{id}/workspace` | Artifact file tree |
| GET | `/runs/{id}/workspace/file?path=` | File content (.md / .json) |
| GET | `/runs/{id}/decisions` | Decision graph timeline |
| GET | `/runs/{id}/agent-profile` | Per-run agent/model role profile |
| GET | `/runs/{id}/documents` | Bundled document listing |
| GET/PUT | `/kernel` | Founder kernel read/write |

### Key environment variables

| Variable | Default | Purpose |
|---|---|---|
| `PM_VERDICT_MODE` | `api` | Intent gate: `api` \| `interactive` \| `auto_proceed` |
| `PM_INTENT_REVIEW_TIMEOUT_SEC` | `600` | api mode timeout → reject |
| `PM_EVENT_STREAM` | `1` (server enables) | Publish events to SSE pub/sub |
| `PM_COGNITIVE_MEMORY` | `1` | Extract `<thinking>` / `<decision_graph>` in Decision/Council |
| `OPENROUTER_MODEL_INTENT_REVIEW` | — | Layer 0.5 gate (unset → skip) |
| `PM_RECONSTRUCTION` | `on` | Layer 1 mode: `on` → `run_pm_reconstruction()` (default) \| `off` → legacy user_def/problem/opportunity trio |
| `OPENROUTER_MODEL_PM_RECON` | — | Layer 1 model when `PM_RECONSTRUCTION=on` (default path) |
| `OPENROUTER_MODEL_USER_DEF` | — | Legacy Layer 1 upstream — only used when `PM_RECONSTRUCTION=off` |
| `OPENROUTER_MODEL_PROBLEM` | — | Legacy Layer 2 problem discovery — only used when `PM_RECONSTRUCTION=off` |
| `OPENROUTER_MODEL_OPPORTUNITY` | — | Legacy Layer 3 opportunity sizing — only used when `PM_RECONSTRUCTION=off` |
| `PM_UPSTREAM_MODE` | — | Upstream phase mode toggle (see `workflows/phases/upstream.py`) |

### CLI mode (legacy)

```bash
python main.py    # direct workflow, no server/UI
```

---

## Project Structure

```
pm_build_mvp/
├── main.py                          # Entry point
├── .env.example                     # Environment variable template
├── docs/
│   ├── token_savings.md             # Notes on prompt/token cost reduction
│   ├── deferred/                    # (empty) Reserved for deferred design docs
│   └── reference/
│       ├── config.json              # [reference only — not runtime-loaded; see .env for active config]
│       └── personas/
│           ├── pm_director.md       # Historical guide reference
│           ├── product_pm.md        # Historical guide reference
│           └── qa_pm.md             # Historical guide reference
├── requirements.txt                 # Python dependencies
├── prompts/                         # System prompts — runtime-loaded via prompt_loader.py
│   ├── founder_intent_review.md     # Layer 0.5: Founder Intent Review Gate
│   ├── pm_reconstruction_system.md  # Layer 1 (default): PM reconstruction
│   ├── user_definition_system.md    # Layer 1 (legacy trio, PM_RECONSTRUCTION=off)
│   ├── problem_discovery_system.md  # Layer 2 (legacy trio, PM_RECONSTRUCTION=off)
│   ├── opportunity_sizing_system.md # Layer 3 (legacy trio, PM_RECONSTRUCTION=off)
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
│   ├── translator_system.md         # Post-process Korean translator (docs)
│   ├── translator_json.md           # Post-process Korean translator (JSON fields)
│   └── _cognitive_output_contract.md   # Shared <thinking>/<decision_graph> output contract
├── templates/
│   ├── raw_ideas.sample.md          # Sample idea (auto-copied on first run)
│   ├── founder_kernel.sample.json   # Starter kernel draft (auto-copied on first run)
│   └── patch_task_description.template.md  # Patch crew task description template
├── workflows/
│   ├── planning_workflow.py         # Phase-based planning workflow
│   └── phases/
│       └── upstream.py              # Legacy Layer 1~3 discovery (PM_RECONSTRUCTION=off only)
├── server/
│   ├── main.py                      # FastAPI app factory
│   ├── run_manager.py               # Background workflow threads
│   └── routes/                      # runs, stream (SSE), intent, workspace, kernel, decisions, agents, documents
├── frontend/                        # React + Vite Hybrid OS Console
├── harness/
│   ├── paths.py                     # Single source of truth for all path constants
│   ├── workspace_init.py            # init_workspace() — creates dirs, seeds raw_ideas.md
│   ├── llm_factory.py               # Role-specific LLM builders (7 required + optional v4)
│   ├── prompt_loader.py             # Prompt/template file loader with cache
│   ├── safe_file_tools.py           # Sandboxed file read/write/patch tools
│   ├── schema_validator.py          # Pydantic HandoffSchema validation
│   ├── audit_hooks.py               # Structured log writers + event_stream publish
│   ├── event_stream.py              # In-proc pub/sub for SSE
│   ├── intent_review.py             # Layer 0.5 Founder Intent Review Gate
│   ├── pm_reconstruction.py         # Default Layer 1 discovery (PM_RECONSTRUCTION=on)
│   ├── pm_brief.py                  # Writes workspace/current/discovery/pm_brief.json
│   ├── confidence_scoring.py        # Confidence calculators used across phases
│   ├── consistency_digest.py        # Cross-document digest for run_consistency_guardrail
│   ├── cognitive_parser.py          # <thinking> / <decision_graph> extraction
│   ├── cognitive_logger.py          # thinking_trace.jsonl + cognition snapshots
│   ├── cognitive_context.py         # Rejected-alternatives context injection
│   ├── cognitive_utils.py           # PM_COGNITIVE_MEMORY toggle (cognitive_enabled())
│   ├── cognitive_validate.py        # call_with_cognitive_retry
│   ├── batch_translator.py          # Korean translation for intent-review/decisions → logs/decisions_ko/
│   ├── decisions_aggregate.py       # Backs GET /runs/{id}/decisions
│   ├── documents_bundle.py          # Backs GET /runs/{id}/documents
│   ├── agent_profile.py             # Backs GET /runs/{id}/agent-profile
│   ├── role_registry.py             # Role/model registry used by agent_profile.py
│   ├── dev_exporter.py              # workspace/current → archive snapshot
│   ├── patch_engine.py              # CrewAI partial JSON patch crew
│   ├── kernel_guard.py              # Founder Kernel loader, hash guard, prompt injector
│   ├── translator_runner.py         # Post-process Korean translation (prompts/translator_system.md)
│   ├── risk_engine.py               # Risk score calculator
│   ├── telemetry_schema.py          # Canonical event schema v1 (validate_event)
│   └── telemetry_projection.py      # generate_all_projections() — projections/views
├── workspace/
│   ├── raw_ideas.md                 # (auto-created on first run) Idea input
│   ├── current/                     # Active run outputs (agents write here)
│   ├── archive/                     # Timestamped snapshots per run
│   ├── signals/                     # Upstream signal inputs (legacy Layer 1~3 path)
│   └── legacy_run/                  # Frozen pre-cutover run snapshots (pre_event_merge/, pre_v4/)
└── logs/                            # Runtime log files
```

> Note: an empty `personas/` directory also exists at repo root of `pm_build_mvp/` (unused — superseded by `docs/reference/personas/` above; easy to confuse the two).

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

> **Note**: `OPENROUTER_MODEL` is a fully deprecated legacy var. `patch_engine.py` now uses `OPENROUTER_MODEL_TECH_REVIEW`. Do not set or rely on `OPENROUTER_MODEL`. See `.env.example` for a full annotated template.

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
  └─ validate_prompt_files()    # Checks all WORKFLOW_REQUIRED_PROMPTS exist — exits(1) on fail
  └─ run_planning()
       ├─ load_founder_kernel()         # Load/create founder_kernel.json + hash
       ├─ run_intent_review()           # Layer 0.5 Founder Intent Review Gate (api/interactive/auto_proceed)
       ├─ run_pm_reconstruction()       # Layer 1 discovery (default; PM_RECONSTRUCTION=on)
       │     or run_user_definition() + run_problem_discovery() + run_opportunity_sizing()
       │                                # Legacy Layer 1~3 trio (PM_RECONSTRUCTION=off)
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
       ├─ ensure_founder_summary_korean() / ensure_decisions_korean() # Korean translation pass
       ├─ create_archive_snapshot()
       └─ generate_all_projections(run_id=...)  # Regenerate telemetry projections/views
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
| `workspace/current/docs/idea_meta.json` | Idea-phase metadata (confidence, model attribution) |
| `workspace/current/docs/decision_meta.json` | Decision-phase metadata |
| `workspace/current/kernel/founder_choice.json` | Founder's Layer 0.5 intent-review decision |
| `workspace/current/kernel/founder_intent_review.json` | Layer 0.5 review document |
| `workspace/current/kernel/founder_intent_review_ko.json` | Korean translation of intent review |
| `workspace/current/discovery/pm_brief.json` | Layer 1 PM reconstruction brief (default path, `PM_RECONSTRUCTION=on`) |
| `workspace/current/user/user_model.json` | Legacy Layer 1 user model (`PM_RECONSTRUCTION=off`) |
| `workspace/current/opportunity/problem_statement.json` | Legacy Layer 2 problem statement (`PM_RECONSTRUCTION=off`) |
| `workspace/current/opportunity/opportunity_model.json` | Legacy Layer 3 opportunity model (`PM_RECONSTRUCTION=off`) |
| `workspace/current/tech/backlog.json` | Structured backlog |
| `workspace/current/tech/handoff_to_dev.json` | Final dev handoff (HandoffSchema) |
| `workspace/current/qa/product_qa_result.json` | Evidence binding + failure taxonomy |
| `workspace/current/qa/strategic_qa_result.json` | Founder preservation + market viability |
| `workspace/current/qa/consistency_result.json` | Cross-document alignment result |
| `workspace/current/qa/escalation_result_{failure_type}.json` | Escalation model response per failure type (logic/spec/validation/semantic/priority_contradiction) |
| `workspace/current/decision/council_decision.json` | Final approval + confidence penalties |
| `workspace/current/validation/validation_strategy.json` | Hypothesis/KPI/failure mode structure |
| `workspace/current/cognition/*.json` | Per-phase `<thinking>`/`<decision_graph>` snapshots |
| `workspace/archive/<YYYY-MM-DD_HHMMss>_<tag>_<run_id[:8]>/` | Snapshot of current/ at run end |
| `logs/pm_audit.log` | Workflow lifecycle events |
| `logs/run_summary.log` | Per-run result summary (ok/risk/tasks/patches) |
| `logs/validation_failures.log` | Schema validation errors with coordinates |
| `logs/thinking_trace.jsonl` | Raw `<thinking>`/`<decision_graph>` extraction trace |
| `logs/decisions_ko/{run_id}.json` | Korean translation of the decision graph timeline |
| `logs/reasoning_trace.jsonl` | Canonical stream — append-only structured events (schema v1: domain/category/event_type) |
| `logs/projections/runtime.log` | Derived: workflow lifecycle events (regenerable) |
| `logs/projections/decisions.log` | Derived: decision/selection/tradeoff events (regenerable) |
| `logs/projections/qa.log` | Derived: qa + system integrity events (regenerable) |
| `logs/projections/cognition.log` | Derived: thinking + decision_graph events (regenerable) |
| `logs/views/lineage_index.md` | View: chronological event lineage table (regenerable) |
| `logs/views/pretty.log` | View: human-readable multiline event export (regenerable) |
| `logs/decision_history.legacy_pre_v2.log` | Frozen pre-cutover archive (not validated, not projected) |
| `logs/blueprint_logic.legacy_pre_v2.log` | Frozen pre-cutover archive (not validated, not projected) |
| `logs/creative_process.legacy_pre_v2.log` | Frozen pre-cutover archive (not validated, not projected) |
| `logs/patch_actions.legacy_pre_v2.log` | Frozen pre-cutover archive (not validated, not projected) |

Archive tag: `todo_mvp` (risk < 70, consistency pass/skipped), `high_risk_pending` (risk ≥ 70 or ConsistencyGuardrail fail), or `intent_rejected` (founder rejects at the Layer 0.5 gate).

---

## Terminal Output (success)

```
Initializing PM Planning System (Phase-based Mode)...
Starting Planning Workflow...
Schema Validation Passed.
Risk Level Acceptable (30).
Archived to workspace/archive/2026-05-01_034215_todo_mvp_a3f7c1d2
Workflow finished.
Result => ok=True risk=30 attempts=0 errors=0 risk_reasons=0 consistency=pass,
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

| Category | Files | Mutability | Validation |
|---|---|---|---|
| **Canonical stream** | `logs/reasoning_trace.jsonl` | append-only, immutable | schema v1 strict (write-level rejection) |
| **Projection / View** | `logs/projections/runtime.log`<br>`logs/projections/decisions.log`<br>`logs/projections/qa.log`<br>`logs/views/lineage_index.md`<br>`logs/views/pretty.log` | regenerable | derived from canonical |
| **Operational summary** | `logs/run_summary.log`<br>`logs/validation_failures.log`<br>`logs/pm_audit.log` | append-only, human-readable | none (text format) |
| **Cognitive trace** | `logs/thinking_trace.jsonl` | append-only | raw `<thinking>`/`<decision_graph>` extraction, not schema-validated |
| **Translation cache** | `logs/decisions_ko/{run_id}.json` | regenerable per-run | Korean translation of the decision timeline |
| **Frozen archive** | `logs/reasoning_trace.legacy_pre_v1.jsonl`<br>`logs/decision_history.legacy_pre_v2.log`<br>`logs/blueprint_logic.legacy_pre_v2.log`<br>`logs/creative_process.legacy_pre_v2.log`<br>`logs/patch_actions.legacy_pre_v2.log` | read-only | not validated |

**Operational summary logs** are written for human `grep`/`tail` use and are kept in dual-write with the canonical stream by design.

**Phase-centric transition logs** are frozen at cutover v2 and preserved as `*.legacy_pre_v2.log` archives. Current code does not append to these files.

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
from harness.telemetry_projection import generate_all_projections

# Regenerate all projections
generate_all_projections(run_id="<run_id>")   # single run
generate_all_projections()                    # full stream
```
