import os
from dotenv import load_dotenv
from workflows.planning_workflow import run_planning
from harness.llm_factory import validate_llm_env

load_dotenv()

def init_workspace():
    dirs =[
        "workspace/current",
        "workspace/archive",
        "logs"
    ]
    for d in dirs:
        os.makedirs(d, exist_ok=True)
        
    raw_ideas_path = os.path.join("workspace", "raw_ideas.md")
    if not os.path.exists(raw_ideas_path):
        sample_idea = """# App Idea: Simple To-Do App (MVP)
I want to build a simple task management app to track my daily goals.
Core needs:
- Users can create a task with a title and optional notes.
- Users can edit existing tasks.
- Users can mark a task as completed.
- Users can delete tasks.
- A view to filter tasks by 'All', 'Active', and 'Completed'.
- I'd like a referral system where users can invite friends to get premium themes.
- Maybe a subscription payment module for Pro features.

Let's keep it quick to build. I want to use Supabase because I know the Python client SDK.
Platform: Web for now, maybe Mobile later."""
        with open(raw_ideas_path, "w", encoding="utf-8") as f:
            f.write(sample_idea)
        print(f"Created initial template: {raw_ideas_path}")

if __name__ == "__main__":
    print("Initializing PM CrewAI System (Hierarchical Mode)...")
    init_workspace()
    
    ok, env_errors = validate_llm_env()
    if not ok:
        print("LLM environment check failed:")
        for e in env_errors:
            print(f"- {e}")
        raise SystemExit(1)
        
    print("Starting Planning Workflow...")
    output = run_planning()
    print("Workflow finished.")
    print(
        f"Result => ok={output.get('ok')} "
        f"risk={output.get('risk')} "
        f"attempts={output.get('attempts')} "
        f"errors={len(output.get('errors'))},"
    )
