import os
import json
from crewai import Agent, Task, Crew, Process
from harness.safe_file_tools import safe_read, safe_write, read_workspace_file
from harness.schema_validator import validate_handoff, HandoffSchema
from harness.risk_engine import calculate_risk
from harness.audit_hooks import log_pm_audit, log_run_summary, log_validation_error
from harness.dev_exporter import create_archive_snapshot
from harness.patch_engine import run_patch_crew
from harness.llm_factory import build_llm_from_env
from harness.translator_runner import ensure_founder_summary_korean

def load_persona(filename):
    with open(os.path.join(os.path.dirname(__file__), f"../personas/{filename}"), "r", encoding="utf-8") as f:
        return f.read()

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
