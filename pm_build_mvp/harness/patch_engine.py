from crewai import Agent, Task, Crew
from .safe_file_tools import safe_read, apply_partial_patch, read_workspace_file
from .audit_hooks import log_patch_action
from .llm_factory import build_technical_review_llm
from .prompt_loader import load_prompt, load_template

def _parse_agent_meta(text: str) -> dict:
    """Parse key: value lines from patch_agent.md into a dict."""
    result = {}
    for line in text.splitlines():
        if ": " in line:
            key, _, value = line.partition(": ")
            result[key.strip()] = value.strip()
    return result


def run_patch_crew(file_path: str, errors: list, run_id: str = ""):
    error_details = "\n".join(errors)
    founder_context = read_workspace_file("current/docs/founder_summary.md")
    patch_llm = build_technical_review_llm()

    agent_meta = _parse_agent_meta(load_prompt("patch_agent"))
    task_description = load_template("patch_task_description.template.md").format(
        file_path=file_path,
        error_details=error_details,
        founder_context=founder_context,
    )

    patch_agent = Agent(
        role=agent_meta.get("role", "JSON Partial Repair Specialist"),
        goal=agent_meta.get("goal", ""),
        backstory=agent_meta.get("backstory", ""),
        allow_delegation=False,
        verbose=True,
        tools=[safe_read, apply_partial_patch],
        llm=patch_llm
    )

    patch_task = Task(
        description=task_description,
        expected_output="Confirmation that all specified errors were patched.",
        agent=patch_agent
    )
    
    crew = Crew(agents=[patch_agent], tasks=[patch_task])
    result = crew.kickoff()
    
    for error in errors:
        log_patch_action(
            file_path, error, "Triggered Partial Patch Engine",
            error_code="SCHEMA_PATCH_TRIGGER",
            run_id=run_id, phase="PatchEngine",
        )
        
    return result
