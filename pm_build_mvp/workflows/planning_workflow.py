import os
import json
import re
from crewai import Agent, Task, Crew, Process
from harness.safe_file_tools import safe_read, safe_write, read_workspace_file, write_workspace_file
from harness.schema_validator import validate_handoff, HandoffSchema
from harness.risk_engine import calculate_risk
from harness.audit_hooks import (
    log_pm_audit, log_run_summary, log_validation_error,
    log_pm_audit_event, log_decision_history, log_blueprint_logic, log_creative_process,
)
from harness.dev_exporter import create_archive_snapshot
from harness.patch_engine import run_patch_crew
from harness.llm_factory import (
    build_llm_from_env,
    build_idea_llm, build_idea_critic_llm, build_synthesis_llm,
    build_decision_llm, build_creative_llm,
    build_technical_gen_llm, build_technical_review_llm,
)
from harness.translator_runner import ensure_founder_summary_korean

def load_persona(filename):
    with open(os.path.join(os.path.dirname(__file__), f"../personas/{filename}"), "r", encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# Phase system prompts
# ---------------------------------------------------------------------------

_IDEA_GEN_SYSTEM = """\
You are a lean startup idea analyst.
Expand a raw app idea into a clear MVP concept.

Output rules:
- 300-400 words maximum.
- Use exactly these headings (no others, no extra sections):
  # Problem
  # Target User
  # Core Value
  # Proposed MVP Scope
  # Excluded Ideas
  # Risks
  # Open Questions
- After the document body, append this block on its own lines (fill in every field):
  <!-- LOG_META
  {"selected_core": "<one-line core feature>", "rejected_features": ["feat1", "feat2"], "risks": ["risk1"], "ko_log_summary": "<1-2 sentence Korean summary of what was kept and excluded>"}
  LOG_META -->
- MVP only. Cut everything that is not essential for a first launch.\
"""

_IDEA_CRITIQUE_SYSTEM = """\
You are a strict MVP scope critic.
Review the concept draft and output up to 5 bullet points.

Flag only:
- Scope creep (non-MVP features that slipped in)
- Contradictions or unclear requirements
- Key risks not mentioned

No praise. No suggestions. Problems only. 150 words max.\
"""

_IDEA_REVISE_SYSTEM = """\
You are a lean startup idea analyst revising a concept draft.
Apply the critique feedback to improve the draft.

Output rules:
- 300-400 words maximum.
- Keep the same headings:
  # Problem
  # Target User
  # Core Value
  # Proposed MVP Scope
  # Excluded Ideas
  # Risks
  # Open Questions
- Append the LOG_META block at the end with updated values:
  <!-- LOG_META
  {"selected_core": "<one-line core feature>", "rejected_features": ["feat1", "feat2"], "risks": ["risk1"], "ko_log_summary": "<1-2 sentence Korean summary>"}
  LOG_META -->
- Do not add new features. Only address what the critique flagged.\
"""

_SYNTHESIS_SYSTEM = """\
You are a product synthesis expert.
Convert a concept draft into a structured JSON checkpoint.

Output rules:
- Output ONLY a valid JSON object. No markdown fences. No explanation. No other text.
- Fill every field. Use [] for empty arrays. Never omit a key.

Required schema:
{
  "problem": "",
  "target_user": "",
  "core_value": "",
  "must_have_mvp": [],
  "excluded_features": [],
  "key_risks": [],
  "open_questions": [],
  "recommended_direction": ""
}\
"""

_CHECKPOINT_REQUIRED_KEYS = frozenset({
    "problem", "target_user", "core_value",
    "must_have_mvp", "excluded_features", "key_risks",
    "open_questions", "recommended_direction",
})


# ---------------------------------------------------------------------------
# Phase response helpers
# ---------------------------------------------------------------------------

def _extract_log_meta(text: str) -> dict:
    """Extract <!-- LOG_META {...} LOG_META --> block from generated text."""
    match = re.search(r'<!--\s*LOG_META\s*(.*?)\s*LOG_META\s*-->', text, re.DOTALL)
    if not match:
        return {}
    try:
        return json.loads(match.group(1).strip())
    except json.JSONDecodeError:
        return {}


def _strip_log_meta(text: str) -> str:
    """Remove LOG_META block and return clean markdown content."""
    return re.sub(r'<!--\s*LOG_META.*?LOG_META\s*-->', '', text, flags=re.DOTALL).strip()


def _clean_json_response(text: str) -> str:
    """Strip markdown code fences from a JSON-only model response."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    return cleaned


def _validate_checkpoint(data: dict) -> list:
    """Return list of missing required keys in concept_checkpoint."""
    return [k for k in _CHECKPOINT_REQUIRED_KEYS if k not in data]


# ---------------------------------------------------------------------------
# Phase 1: Idea Loop
# ---------------------------------------------------------------------------

def run_idea_loop() -> str:
    """Phase 1: Idea Loop

    5-step Flash/mini iteration over raw_ideas.md.
    Outputs current/concept_draft.md with required sections.
    Returns the output file path.
    """
    raw_idea = read_workspace_file("raw_ideas.md")
    idea_llm = build_idea_llm()
    critic_llm = build_idea_critic_llm()

    idea_model = os.getenv("OPENROUTER_MODEL_IDEA", "idea_model")
    critic_model = os.getenv("OPENROUTER_MODEL_IDEA_CRITIC", "critic_model")

    log_pm_audit_event("IdeaLoop", "START", model=f"{idea_model},{critic_model}")

    # Step 1: Flash expands raw idea → draft v1
    draft_v1 = idea_llm.call([
        {"role": "system", "content": _IDEA_GEN_SYSTEM},
        {"role": "user", "content": f"Expand this raw idea into an MVP concept:\n\n{raw_idea}"},
    ])

    # Step 2: Mini critiques draft v1
    critique_1 = critic_llm.call([
        {"role": "system", "content": _IDEA_CRITIQUE_SYSTEM},
        {"role": "user", "content": f"Critique this MVP concept draft:\n\n{draft_v1}"},
    ])

    # Step 3: Flash revises based on critique → draft v2
    draft_v2 = idea_llm.call([
        {"role": "system", "content": _IDEA_REVISE_SYSTEM},
        {"role": "user", "content": (
            f"Original draft:\n{draft_v1}\n\n"
            f"Critique to apply:\n{critique_1}\n\n"
            "Revise the draft."
        )},
    ])

    # Step 4: Mini critiques draft v2
    critique_2 = critic_llm.call([
        {"role": "system", "content": _IDEA_CRITIQUE_SYSTEM},
        {"role": "user", "content": f"Critique this revised MVP concept draft:\n\n{draft_v2}"},
    ])

    # Step 5: Flash generates final draft with LOG_META
    final_draft = idea_llm.call([
        {"role": "system", "content": _IDEA_REVISE_SYSTEM},
        {"role": "user", "content": (
            f"Revised draft:\n{draft_v2}\n\n"
            f"Final critique to apply:\n{critique_2}\n\n"
            "Generate the definitive final concept draft."
        )},
    ])

    # Extract meta for logging; strip from saved file content
    meta = _extract_log_meta(final_draft)
    clean_draft = _strip_log_meta(final_draft)

    write_workspace_file("current/concept_draft.md", clean_draft)

    rejected_list = meta.get("rejected_features", [])
    risks_list = meta.get("risks", [])

    log_pm_audit_event(
        "IdeaLoop", "END",
        selected=meta.get("selected_core"),
        rejected=",".join(rejected_list) or None,
        risk=",".join(risks_list) or None,
        output="current/concept_draft.md",
        summary_ko=meta.get("ko_log_summary"),
    )
    for feat in rejected_list:
        log_decision_history("IdeaLoop", rejected=feat, reason="non-MVP scope")

    return "current/concept_draft.md"


# ---------------------------------------------------------------------------
# Phase 2: Synthesis
# ---------------------------------------------------------------------------

def run_synthesis() -> dict:
    """Phase 2: Synthesis

    Compresses concept_draft.md into a structured JSON checkpoint.
    Outputs current/concept_checkpoint.json.
    Returns the parsed checkpoint dict.
    Raises RuntimeError if valid JSON cannot be produced after 1 self-correction.
    """
    draft = read_workspace_file("current/concept_draft.md")
    llm = build_synthesis_llm()

    synthesis_model = os.getenv("OPENROUTER_MODEL_SYNTHESIS", "synthesis_model")
    log_pm_audit_event("Synthesis", "START", model=synthesis_model)

    base_msgs = [
        {"role": "system", "content": _SYNTHESIS_SYSTEM},
        {"role": "user", "content": f"Convert this concept draft into the JSON checkpoint:\n\n{draft}"},
    ]

    raw = llm.call(base_msgs)
    cleaned = _clean_json_response(raw)

    # Parse attempt 1
    try:
        checkpoint = json.loads(cleaned)
        missing = _validate_checkpoint(checkpoint)
        if missing:
            raise ValueError(f"Missing required keys: {missing}")
    except (json.JSONDecodeError, ValueError) as err:
        log_pm_audit(f"Phase=Synthesis | Status=PARSE_FAIL_ATTEMPT_1 | Error={err}")

        # Self-correction: one retry with the error fed back
        retry_msgs = base_msgs + [
            {"role": "assistant", "content": raw},
            {"role": "user", "content": (
                f"Your response failed validation: {err}\n"
                "Output ONLY the corrected JSON object. No explanation. No fences."
            )},
        ]
        raw2 = llm.call(retry_msgs)
        cleaned2 = _clean_json_response(raw2)

        try:
            checkpoint = json.loads(cleaned2)
            missing2 = _validate_checkpoint(checkpoint)
            if missing2:
                raise ValueError(f"Missing required keys after retry: {missing2}")
        except (json.JSONDecodeError, ValueError) as err2:
            log_pm_audit(f"Phase=Synthesis | Status=PARSE_FAIL_ATTEMPT_2 | Error={err2}")
            raise RuntimeError(
                f"Synthesis failed: could not produce valid concept_checkpoint.json "
                f"after 1 self-correction. Last error: {err2}"
            ) from err2

    content = json.dumps(checkpoint, indent=2, ensure_ascii=False)
    write_workspace_file("current/concept_checkpoint.json", content)

    direction = checkpoint.get("recommended_direction", "")
    excluded = checkpoint.get("excluded_features", [])

    log_pm_audit_event(
        "Synthesis", "END",
        selected=direction[:80] if direction else None,
        output="current/concept_checkpoint.json",
        summary_ko=f"핵심 방향: {direction[:60]}" if direction else None,
    )
    for feat in excluded:
        log_decision_history(
            "Synthesis",
            rejected=feat,
            reason="excluded in synthesis checkpoint",
            summary_ko=f"{feat} MVP 범위에서 제외됨",
        )

    return checkpoint


def run_planning():
    raw_idea = read_workspace_file("raw_ideas.md")
    openrouter_llm = build_llm_from_env()
    
    pm_director = Agent(
        role="PM Director",
        goal="Finalize MVP scope, tech stack, and act as the overarching manager",
        backstory=load_persona("pm_director.md"),
        verbose=True,
        allow_delegation=True,
        llm=openrouter_llm
    )
    
    prod_pm = Agent(
        role="Product PM",
        goal="Draft feature specs and dev handoff JSON",
        backstory=load_persona("product_pm.md"),
        verbose=True,
        tools=[safe_read, safe_write],
        llm=openrouter_llm
    )
    
    qa_pm = Agent(
        role="QA PM",
        goal="Refine acceptance criteria and detect edge cases",
        backstory=load_persona("qa_pm.md"),
        verbose=True,
        tools=[safe_read, safe_write],
        llm=openrouter_llm
    )
    
    task_scope = Task(
        description=f"Review this raw idea: {raw_idea}\nRemove non-MVP features. Write a concise 'founder_summary.md' to current/ using Safe File Writer.",
        expected_output="A saved current/founder_summary.md file"
    )
    
    task_spec = Task(
        description="""1. Use Safe File Reader to read 'current/founder_summary.md'.
2. Based on the summary, write 'feature_spec.md' and 'backlog.json' to current/ with user stories and flows.""",
        expected_output="Saved current/feature_spec.md and current/backlog.json"
    )
    
    task_handoff = Task(
        description="""1. Use Safe File Reader to read all previously created files in current/.
2. Based on the read context, create a final handoff object.
3. Save it as 'handoff_to_dev.json' in current/ using Safe File Writer Tool.""",
        expected_output="A perfectly structured JSON object representing the dev handoff.",
        output_json=HandoffSchema
    )
    
    crew = Crew(
        agents=[prod_pm, qa_pm],
        tasks=[task_scope, task_spec, task_handoff],
        manager_agent=pm_director,
        manager_llm=openrouter_llm,
        process=Process.hierarchical
    )
    
    log_pm_audit("Started Hierarchical MVP Planning Workflow")

    # ensure_founder_summary_korean() runs in finally so it executes on every
    # exit path: normal completion, early return, kickoff exception, etc.
    # It swallows its own exceptions internally so it never masks the real error.
    try:
        result = crew.kickoff()

        max_retries = 3
        attempts = 0
        is_valid = False
        handoff_dict = {}

        while attempts < max_retries:
            handoff_content = read_workspace_file("current/handoff_to_dev.json")
            is_valid, errors = validate_handoff(handoff_content)
            if is_valid:
                print("Schema Validation Passed.")
                handoff_dict = json.loads(handoff_content)
                break

            attempts += 1
            print(f"Validation Failed (Attempt {attempts}/{max_retries}). Triggering PARTIAL PATCH Engine...")
            for err in errors:
                log_validation_error("handoff_to_dev.json", err, "Schema mismatch", attempts, error_code="SCHEMA_MISMATCH")

            if attempts < max_retries:
                run_patch_crew("current/handoff_to_dev.json", errors)
            else:
                print("Max retries reached. Auto-rejecting output.")
                log_pm_audit("Workflow failed: Max PATCH retries reached.")
                log_run_summary(False, ["handoff_to_dev.json"], 0, 0, attempts, 0)
                return {
                    "ok": False,
                    "risk": None,
                    "attempts": attempts,
                    "errors": errors,
                }

        risk_result = calculate_risk(handoff_dict)
        risk = risk_result["score"]
        reasons = risk_result["reasons"]

        if risk >= 70:
            print(f"HIGH RISK ({risk}): Founder Approval Required.")
            log_pm_audit(f"Workflow paused. High risk score: {risk}. reasons={reasons}")
            snapshot_tag = "high_risk_pending"
        else:
            print(f"Risk Level Acceptable ({risk}).")
            snapshot_tag = "todo_mvp"

        snapshot = create_archive_snapshot(snapshot_tag)
        print(f"Archived to {snapshot}")

        log_run_summary(
            True,
            ["handoff_to_dev.json", "founder_summary.md", "backlog.json", "feature_spec.md", "founder_summary_ko.md"],
            len(handoff_dict.get("tasks", [])),
            risk,
            attempts,
            len(reasons),
        )

        return {
            "ok": True,
            "risk": risk,
            "attempts": attempts,
            "errors": [],
            "risk_reasons": reasons,
            "crew_result": str(result),
        }

    finally:
        # Translation runs on every exit path (success, early return, exception).
        # This is the ONLY place ensure_founder_summary_korean() is called.
        ensure_founder_summary_korean()
