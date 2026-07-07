import os
from dotenv import load_dotenv
from harness.llm_factory import validate_llm_env
from harness.prompt_loader import validate_prompt_files, WORKFLOW_REQUIRED_PROMPTS
from harness.workspace_init import init_workspace

load_dotenv()

if __name__ == "__main__":
    print("Initializing PM Planning System (Phase-based Mode)...")
    init_workspace()

    ok, env_errors = validate_llm_env()
    if not ok:
        print("LLM environment check failed:")
        for e in env_errors:
            print(f"- {e}")
        raise SystemExit(1)

    missing_prompts = validate_prompt_files(WORKFLOW_REQUIRED_PROMPTS)
    if missing_prompts:
        print(f"Prompt preflight failed — {len(missing_prompts)} file(s) missing:")
        for name in missing_prompts:
            print(f"  - prompts/{name}.md")
        raise SystemExit(1)

    from workflows.planning_workflow import run_planning

    print("Starting Planning Workflow...")
    output = run_planning()
    print("Workflow finished.")
    print(
        f"Result => ok={output.get('ok')} "
        f"risk={output.get('risk')} "
        f"attempts={output.get('attempts')} "
        f"errors={len(output.get('errors', []))} "
        f"risk_reasons={len(output.get('risk_reasons', []))} "
        f"consistency={output.get('consistency_status', 'skipped')},"
    )
