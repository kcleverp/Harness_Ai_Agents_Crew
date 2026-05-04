# pm_build_mvp

AI-powered PM crew for structured MVP product planning.
Uses CrewAI hierarchical process with OpenRouter LLM backend.

---

## Project Structure

```
pm_build_mvp/
├── main.py                          # Entry point
├── .env.example                     # Environment variable template
├── config.json                      # Project configuration reference
├── requirements.txt                 # Python dependencies
├── personas/
│   ├── pm_director.md               # PM Director agent backstory
│   ├── product_pm.md                # Product PM agent backstory
│   └── qa_pm.md                     # QA PM agent backstory
├── workflows/
│   └── planning_workflow.py         # CrewAI hierarchical workflow
├── harness/
│   ├── llm_factory.py               # LLM build (OpenRouter → OpenAI fallback)
│   ├── safe_file_tools.py           # Sandboxed file read/write/patch tools
│   ├── schema_validator.py          # Pydantic HandoffSchema validation
│   ├── audit_hooks.py               # Structured log writers
│   ├── dev_exporter.py              # workspace/current → archive snapshot
│   ├── patch_engine.py              # CrewAI partial JSON patch crew
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

Edit `.env` — minimum required:

```env
# Option A: OpenRouter (recommended)
OPENROUTER_API_KEY=sk-or-...
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MODEL=anthropic/claude-3.5-sonnet

# Option B: OpenAI fallback
OPENAI_API_KEY=sk-...
```

`llm_factory.py` reads `OPENROUTER_*` first; falls back to `OPENAI_*` if unset.

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
       ├─ Crew.kickoff()        # Hierarchical: PM Director manages Product PM + QA PM
       ├─ validate_handoff()    # Pydantic schema check on handoff_to_dev.json
       ├─ run_patch_crew()      # Partial patch retry (max 3 attempts)
       ├─ calculate_risk()      # Risk score 0–100
       └─ create_archive_snapshot()
```

---

## Outputs

| Path | Description |
|---|---|
| `workspace/raw_ideas.md` | Input idea (auto-generated template on first run) |
| `workspace/current/founder_summary.md` | MVP scope distilled by PM Director |
| `workspace/current/feature_spec.md` | Feature specs and user stories |
| `workspace/current/backlog.json` | Structured backlog |
| `workspace/current/handoff_to_dev.json` | Final dev handoff (HandoffSchema) |
| `workspace/archive/<timestamp>_<tag>/` | Snapshot of current/ at run end |
| `logs/pm_audit.log` | Workflow lifecycle events |
| `logs/run_summary.log` | Per-run result summary (ok/risk/tasks/patches) |
| `logs/validation_failures.log` | Schema validation errors with coordinates |
| `logs/patch_actions.log` | Partial patch operations |

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
- Phase 4: Docs & verification ✅ (current)
