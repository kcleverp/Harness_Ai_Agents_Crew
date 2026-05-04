from crewai import Agent, Task, Crew
from .safe_file_tools import safe_read, apply_partial_patch, read_workspace_file
from .audit_hooks import log_patch_action
from .llm_factory import build_llm_from_env

def run_patch_crew(file_path: str, errors: list):
    error_details = "\n".join(errors)
    founder_context = read_workspace_file("current/founder_summary.md")
    patch_llm = build_llm_from_env()
    
    patch_agent = Agent(
        role="JSON Partial Repair Specialist",
        goal="Fix JSON schema validation errors strictly using targeted partial patches.",
        backstory=(
            "You are a strict JSON surgeon. "
            "You DO NOT rewrite files. "
            "You ONLY use the Apply Partial JSON Patch Tool."
        ),
        allow_delegation=False,
        verbose=True,
        tools=[safe_read, apply_partial_patch],
        llm=patch_llm
    )
    
    patch_task = Task(
        description=f"""The file '{file_path}' failed Schema Validation.
Exact errors found:
{error_details}

Reference Business Logic:
{founder_context}

Action Steps:
1. Use 'Safe File Reader Tool' to inspect '{file_path}'.
2. Identify specific key paths that are broken.
3. Use 'Apply Partial JSON Patch Tool' repeatedly for each broken path.
4. Never rewrite the full file.
""",
        expected_output="Confirmation that all specified errors were patched.",
        agent=patch_agent
    )
    
    crew = Crew(agents=[patch_agent], tasks=[patch_task])
    result = crew.kickoff()
    
    for error in errors:
        log_patch_action(file_path, error, "Triggered Partial Patch Engine", error_code="SCHEMA_PATCH_TRIGGER")
        
    return result
