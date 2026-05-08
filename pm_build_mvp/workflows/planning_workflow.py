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

_DECISION_SYSTEM = """\
You are a senior product architect making definitive MVP decisions.

Given a concept checkpoint, produce a blueprint document.

Output format:
1. Write the blueprint in Markdown with EXACTLY these headings (no others):
   # Product Direction
   # MVP Boundary
   # Core User Flow
   # Tech Stack Decision
   # Data / Backend Notes
   # Rejected Options
   # Trade-offs
   # Risks
   # Build Order

2. After the document, append this metadata block:
   <!-- DECISION_META
   {"selected_decisions": ["decision1"], "trade_offs": ["tradeoff1"], "reasons": ["reason1"], "rejected_options": ["option1", "option2"], "ko_log_summary": "<1-2 sentence Korean summary of the key decisions made>"}
   DECISION_META -->

Rules:
- Be decisive. No "TBD" or "depends on context".
- Tech Stack Decision must name specific tools with a one-line justification each.
- Rejected Options must list at least 2 alternatives that were considered.
- Trade-offs must state what was sacrificed and why it was acceptable.
- Keep document concise: 400-600 words max.\
"""

_FOUNDER_SUMMARY_SYSTEM = """\
You are a product writer creating a concise founder-level summary.

Given a blueprint, write the founder summary.

Output format:
Markdown with EXACTLY these headings (no others):
# One-line Product
# Who It Is For
# Problem
# MVP Scope
# What Is Explicitly Out
# Why This Scope First

After the document, append:
<!-- CREATIVE_META
{"narrative_focus": "<what angle was emphasized>", "rejected_framings": ["framing1"], "ko_log_summary": "<1-2 sentence Korean summary>"}
CREATIVE_META -->

Rules:
- "One-line Product": one sentence, 15 words max.
- "MVP Scope": bullet list of 3-5 items only.
- "What Is Explicitly Out": bullet list, each item specific and unambiguous.
- No marketing language. Clarity over persuasion.
- 250-350 words total.\
"""

_FEATURE_SPEC_SYSTEM = """\
You are a senior product manager writing a feature specification.

Given a blueprint and founder summary, write the feature spec.

Output format:
Markdown with EXACTLY these headings (no others):
# Primary User Stories
# End-to-End User Flow
# Feature Breakdown
# Acceptance Boundaries
# Non-goals
# Open Product Risks

After the document, append:
<!-- CREATIVE_META
{"narrative_focus": "<what angle was emphasized>", "rejected_framings": ["framing1"], "ko_log_summary": "<1-2 sentence Korean summary>"}
CREATIVE_META -->

Rules:
- "Primary User Stories": "As a [user], I want [action] so that [outcome]" format, 3-5 stories.
- "End-to-End User Flow": numbered steps, 5-8 steps.
- "Feature Breakdown": one sub-heading per feature, 2-3 acceptance criteria each.
- "Non-goals": explicit list of what this spec does NOT cover.
- No tech stack details. Product language only.
- 400-500 words total.\
"""

_TECH_GEN_SYSTEM = """\
You are a technical product manager generating structured JSON artifacts.

Generate both a backlog and a dev handoff JSON from the provided context.

Output ONLY a valid JSON object with EXACTLY this structure. No markdown. No explanation.
{
  "backlog": {
    "tasks": []
  },
  "handoff": {
    "project_name": "",
    "objective": "",
    "target_platform": "web",
    "tech_stack": {
      "status": "proposed",
      "frontend": [],
      "backend": [],
      "database": [],
      "infra": [],
      "notes": ""
    },
    "tasks": []
  }
}

Task schema (identical for backlog.tasks and handoff.tasks):
{
  "id": "TASK-01",
  "title": "",
  "owner": "frontend",
  "priority": "high",
  "dependencies": [],
  "acceptance_criteria": [],
  "files_to_create": [],
  "files_to_modify": [],
  "notes": ""
}

Enum constraints:
- owner: frontend | backend | fullstack | qa
- priority: high | medium | low
- target_platform: web | mobile | api | desktop
- tech_stack.status: proposed | pending | locked

Rules:
- Include 4-8 tasks total. No placeholder tasks.
- Every task must have at least 2 acceptance_criteria.
- Task title must be specific and actionable (no vague wording).
- dependencies must reference only existing task IDs in this same list.
- No circular dependencies.
- Do not assign >80% of tasks to one owner when total tasks >= 5.
- backlog.tasks and handoff.tasks must be identical.\
"""

_TECH_REVIEW_SYSTEM = """\
You are a strict JSON schema reviewer for development task artifacts.

Review the generated JSON and identify all issues.

Output ONLY a valid JSON object. No markdown. No explanation.
{
  "issues": ["issue description"],
  "fix_requests": ["exact fix instruction"],
  "ko_log_summary": "<1-2 sentence Korean summary of main issues found>"
}

Check for:
1. Schema: all required fields present, correct types
2. Enum values: owner (frontend/backend/fullstack/qa), priority (high/medium/low),
   target_platform (web/mobile/api/desktop), tech_stack.status (proposed/pending/locked)
3. Task completeness: acceptance_criteria >= 2, titles specific and actionable
4. Dependency integrity: no undefined IDs, no circular dependencies
5. Ownership: not >80% on one owner when task_count >= 5
6. backlog.tasks and handoff.tasks must be identical

If no issues found:
{"issues": [], "fix_requests": [], "ko_log_summary": "모든 항목 유효함"}\
"""

_TECH_REVISE_SYSTEM = """\
You are a technical product manager fixing JSON artifacts based on reviewer feedback.

Apply every fix request exactly. Output ONLY the corrected JSON. No markdown. No explanation.

Keep the same top-level structure:
{"backlog": {"tasks": [...]}, "handoff": {"project_name": "", ...}}

Rules:
- Apply every fix request listed.
- Keep tasks that were not flagged as issues.
- backlog.tasks and handoff.tasks must be identical after fixes.\
"""


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


def _extract_decision_meta(text: str) -> dict:
    """Extract <!-- DECISION_META {...} DECISION_META --> block."""
    match = re.search(r'<!--\s*DECISION_META\s*(.*?)\s*DECISION_META\s*-->', text, re.DOTALL)
    if not match:
        return {}
    try:
        return json.loads(match.group(1).strip())
    except json.JSONDecodeError:
        return {}


def _strip_decision_meta(text: str) -> str:
    """Remove DECISION_META block, returning clean markdown."""
    return re.sub(r'<!--\s*DECISION_META.*?DECISION_META\s*-->', '', text, flags=re.DOTALL).strip()


def _extract_creative_meta(text: str) -> dict:
    """Extract <!-- CREATIVE_META {...} CREATIVE_META --> block."""
    match = re.search(r'<!--\s*CREATIVE_META\s*(.*?)\s*CREATIVE_META\s*-->', text, re.DOTALL)
    if not match:
        return {}
    try:
        return json.loads(match.group(1).strip())
    except json.JSONDecodeError:
        return {}


def _strip_creative_meta(text: str) -> str:
    """Remove CREATIVE_META block, returning clean markdown."""
    return re.sub(r'<!--\s*CREATIVE_META.*?CREATIVE_META\s*-->', '', text, flags=re.DOTALL).strip()


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


# ---------------------------------------------------------------------------
# Phase 3: Decision
# ---------------------------------------------------------------------------

def run_decision() -> dict:
    """Phase 3: Decision

    Reads concept_checkpoint.json, produces definitive blueprint.md.
    Uses claude-opus class model for structural/architectural decisions.
    Logs decisions to blueprint_logic.log and decision_history.log.
    Returns the decision meta dict.
    """
    checkpoint_raw = read_workspace_file("current/concept_checkpoint.json")
    checkpoint = json.loads(checkpoint_raw)
    llm = build_decision_llm()

    decision_model = os.getenv("OPENROUTER_MODEL_DECISION", "decision_model")
    log_pm_audit_event("Decision", "START", model=decision_model)

    checkpoint_summary = json.dumps(checkpoint, indent=2, ensure_ascii=False)

    blueprint_raw = llm.call([
        {"role": "system", "content": _DECISION_SYSTEM},
        {"role": "user", "content": (
            "Make decisions and write the blueprint based on this concept checkpoint:\n\n"
            f"{checkpoint_summary}"
        )},
    ])

    meta = _extract_decision_meta(blueprint_raw)
    clean_blueprint = _strip_decision_meta(blueprint_raw)

    write_workspace_file("current/blueprint.md", clean_blueprint)

    selected_str = ", ".join(meta.get("selected_decisions", []))[:120] or None
    rejected_str = ", ".join(meta.get("rejected_options", []))[:120] or None
    tradeoff_str = ", ".join(meta.get("trade_offs", []))[:120] or None
    reason_str = ", ".join(meta.get("reasons", []))[:120] or None

    log_blueprint_logic(
        "Decision",
        selected=selected_str,
        rejected=rejected_str,
        trade_off=tradeoff_str,
        reason=reason_str,
        summary_ko=meta.get("ko_log_summary"),
    )
    for opt in meta.get("rejected_options", []):
        log_decision_history(
            "Decision",
            rejected=opt,
            reason="rejected in architecture decision phase",
        )

    log_pm_audit_event(
        "Decision", "END",
        selected=selected_str,
        rejected=rejected_str,
        output="current/blueprint.md",
        summary_ko=meta.get("ko_log_summary"),
    )

    return meta


# ---------------------------------------------------------------------------
# Phase 4: Creative Production
# ---------------------------------------------------------------------------

def run_creative_production() -> dict:
    """Phase 4: Creative Production

    Reads blueprint.md, produces:
    - current/founder_summary.md
    - current/feature_spec.md
    Uses two focused calls to the creative (sonnet-class) model.
    Logs framing decisions to creative_process.log.
    Returns combined meta dict.
    """
    blueprint = read_workspace_file("current/blueprint.md")
    llm = build_creative_llm()

    creative_model = os.getenv("OPENROUTER_MODEL_CREATIVE", "creative_model")
    log_pm_audit_event("CreativeProd", "START", model=creative_model)

    # Call 1: founder_summary.md
    founder_raw = llm.call([
        {"role": "system", "content": _FOUNDER_SUMMARY_SYSTEM},
        {"role": "user", "content": (
            f"Write the founder summary based on this blueprint:\n\n{blueprint}"
        )},
    ])
    founder_meta = _extract_creative_meta(founder_raw)
    clean_founder = _strip_creative_meta(founder_raw)
    write_workspace_file("current/founder_summary.md", clean_founder)

    # Call 2: feature_spec.md (receives both blueprint and founder summary for coherence)
    spec_raw = llm.call([
        {"role": "system", "content": _FEATURE_SPEC_SYSTEM},
        {"role": "user", "content": (
            f"Blueprint:\n{blueprint}\n\n"
            f"Founder Summary:\n{clean_founder}\n\n"
            "Write the feature specification."
        )},
    ])
    spec_meta = _extract_creative_meta(spec_raw)
    clean_spec = _strip_creative_meta(spec_raw)
    write_workspace_file("current/feature_spec.md", clean_spec)

    # founder_meta takes priority for combined summary
    combined_meta = {**spec_meta, **founder_meta}

    rejected_framings_str = ", ".join(combined_meta.get("rejected_framings", []))[:120] or None
    log_creative_process(
        "CreativeProd",
        selected=combined_meta.get("narrative_focus"),
        rejected=rejected_framings_str,
        summary_ko=combined_meta.get("ko_log_summary"),
    )
    log_pm_audit_event(
        "CreativeProd", "END",
        selected=combined_meta.get("narrative_focus"),
        output="current/founder_summary.md,current/feature_spec.md",
        summary_ko=combined_meta.get("ko_log_summary"),
    )

    return combined_meta


# ---------------------------------------------------------------------------
# Phase 5 helper: backlog structural validation
# ---------------------------------------------------------------------------

_VALID_OWNER = frozenset({"frontend", "backend", "fullstack", "qa"})
_VALID_PRIORITY = frozenset({"high", "medium", "low"})
_BACKLOG_REQUIRED_TASK_FIELDS = frozenset({
    "id", "title", "owner", "priority", "dependencies",
    "acceptance_criteria", "files_to_create", "files_to_modify", "notes",
})


def _validate_backlog(data: dict) -> list:
    """Basic structural check for backlog.json.

    Returns a list of error strings (empty = valid).
    Does NOT raise — caller logs warnings and continues.
    """
    errors = []
    tasks = data.get("tasks", [])
    if not isinstance(tasks, list) or len(tasks) == 0:
        errors.append("backlog.tasks is empty or not a list")
        return errors

    ids_seen = {t.get("id") for t in tasks if t.get("id")}
    for i, task in enumerate(tasks):
        prefix = f"tasks.{i}"
        for field in _BACKLOG_REQUIRED_TASK_FIELDS:
            if field not in task:
                errors.append(f"{prefix}: missing field '{field}'")
        if task.get("owner") not in _VALID_OWNER:
            errors.append(f"{prefix}.owner: invalid value '{task.get('owner')}'")
        if task.get("priority") not in _VALID_PRIORITY:
            errors.append(f"{prefix}.priority: invalid value '{task.get('priority')}'")
        if len(task.get("acceptance_criteria", [])) < 2:
            errors.append(f"{prefix}: acceptance_criteria must have >= 2 items")
        for dep in task.get("dependencies", []):
            if dep not in ids_seen:
                errors.append(f"{prefix}: undefined dependency '{dep}'")

    return errors


# ---------------------------------------------------------------------------
# Phase 5: Technical Production
# ---------------------------------------------------------------------------

def run_technical_production() -> None:
    """Phase 5: Technical Production

    Reads blueprint.md, founder_summary.md, feature_spec.md.
    Flash generates combined backlog + handoff draft.
    mini reviews for schema/enum/completeness/dependency issues.
    Flash revises if issues found.

    Outputs:
    - current/backlog.json  (with basic structural validation; warns, does not fail)
    - current/handoff_to_dev.json  (raw; final gate is validate_handoff() in orchestration)
    """
    blueprint = read_workspace_file("current/blueprint.md")
    founder_summary = read_workspace_file("current/founder_summary.md")
    feature_spec = read_workspace_file("current/feature_spec.md")

    gen_llm = build_technical_gen_llm()
    review_llm = build_technical_review_llm()

    tech_gen_model = os.getenv("OPENROUTER_MODEL_TECH_GEN", "tech_gen_model")
    tech_review_model = os.getenv("OPENROUTER_MODEL_TECH_REVIEW", "tech_review_model")
    log_pm_audit_event("TechnicalProd", "START", model=f"{tech_gen_model},{tech_review_model}")

    context = (
        f"## Blueprint\n{blueprint}\n\n"
        f"## Founder Summary\n{founder_summary}\n\n"
        f"## Feature Spec\n{feature_spec}"
    )

    # Step 1: Flash generates combined draft
    gen_raw = gen_llm.call([
        {"role": "system", "content": _TECH_GEN_SYSTEM},
        {"role": "user", "content": f"Generate the backlog and handoff JSON from:\n\n{context}"},
    ])
    gen_cleaned = _clean_json_response(gen_raw)

    # Step 2: mini reviews the draft
    review_raw = review_llm.call([
        {"role": "system", "content": _TECH_REVIEW_SYSTEM},
        {"role": "user", "content": f"Review these JSON artifacts:\n\n{gen_cleaned}"},
    ])
    review_cleaned = _clean_json_response(review_raw)

    try:
        review_result = json.loads(review_cleaned)
    except json.JSONDecodeError:
        review_result = {"issues": [], "fix_requests": [], "ko_log_summary": None}

    issues = review_result.get("issues", [])
    fix_requests = review_result.get("fix_requests", [])

    # Step 3: Flash revises only when issues exist
    if issues:
        fix_lines = "\n".join(f"- {r}" for r in fix_requests)
        revised_raw = gen_llm.call([
            {"role": "system", "content": _TECH_REVISE_SYSTEM},
            {"role": "user", "content": (
                f"Original JSON:\n{gen_cleaned}\n\n"
                f"Fix requests:\n{fix_lines}"
            )},
        ])
        final_combined = _clean_json_response(revised_raw)
    else:
        final_combined = gen_cleaned

    # Parse combined output
    try:
        combined = json.loads(final_combined)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"TechnicalProd failed: cannot parse combined JSON output. {exc}"
        ) from exc

    backlog = combined.get("backlog", {})
    handoff = combined.get("handoff", {})

    # Validate backlog (warn only — does not fail the workflow)
    backlog_errors = _validate_backlog(backlog)
    if backlog_errors:
        log_pm_audit(
            f"Phase=TechnicalProd | Status=BACKLOG_WARN | Issues={backlog_errors[:3]}"
        )

    write_workspace_file(
        "current/backlog.json",
        json.dumps(backlog, indent=2, ensure_ascii=False),
    )
    write_workspace_file(
        "current/handoff_to_dev.json",
        json.dumps(handoff, indent=2, ensure_ascii=False),
    )

    log_pm_audit_event(
        "TechnicalProd", "END",
        output="current/backlog.json,current/handoff_to_dev.json",
        summary_ko=review_result.get("ko_log_summary"),
    )


def run_final_validation_and_patch() -> tuple:
    """Validate handoff_to_dev.json and patch if needed.

    Runs up to 3 validate attempts and up to 2 patch crew calls.
    Returns (True, handoff_dict) on success.
    Returns (False, {"attempts": N, "errors": [...]}) on max retries exhausted.
    """
    max_retries = 3
    attempts = 0
    handoff_dict = {}

    while attempts < max_retries:
        handoff_content = read_workspace_file("current/handoff_to_dev.json")
        is_valid, errors = validate_handoff(handoff_content)
        if is_valid:
            print("Schema Validation Passed.")
            handoff_dict = json.loads(handoff_content)
            return True, handoff_dict

        attempts += 1
        print(f"Validation Failed (Attempt {attempts}/{max_retries}). Triggering PARTIAL PATCH Engine...")
        for err in errors:
            log_validation_error(
                "handoff_to_dev.json", err, "Schema mismatch",
                attempts, error_code="SCHEMA_MISMATCH",
            )

        if attempts < max_retries:
            run_patch_crew("current/handoff_to_dev.json", errors)

    return False, {"attempts": attempts, "errors": errors}


def run_planning():
    """Phase-based MVP planning workflow.

    Execution order:
      1. run_idea_loop()          — concept_draft.md
      2. run_synthesis()          — concept_checkpoint.json
      3. run_decision()           — blueprint.md
      4. run_creative_production()— founder_summary.md, feature_spec.md
      5. run_technical_production()— backlog.json, handoff_to_dev.json
      6. run_final_validation_and_patch() — validate_handoff + patch loop
      7. calculate_risk()
      8. ensure_founder_summary_korean() — before snapshot so ko file is included
      9. create_archive_snapshot()
    """
    log_pm_audit_event("Workflow", "START")

    translation_checked = False
    # ensure_founder_summary_korean() runs before archive on the normal path.
    # finally keeps it as a fallback for early returns and exceptions.
    try:
        print("Phase 1: Idea Loop")
        run_idea_loop()

        print("Phase 2: Synthesis")
        run_synthesis()

        print("Phase 3: Decision")
        run_decision()

        print("Phase 4: Creative Production")
        run_creative_production()

        print("Phase 5: Technical Production")
        run_technical_production()

        print("Phase 6: Final Validation + Patch")
        ok, result = run_final_validation_and_patch()
        if not ok:
            print("Max retries reached. Auto-rejecting output.")
            log_pm_audit("Workflow failed: Max PATCH retries reached.")
            log_run_summary(False, ["handoff_to_dev.json"], 0, 0, result["attempts"], 0)
            return {
                "ok": False,
                "risk": None,
                "attempts": result["attempts"],
                "errors": result["errors"],
            }

        handoff_dict = result

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

        ensure_founder_summary_korean()
        translation_checked = True

        snapshot = create_archive_snapshot(snapshot_tag)
        print(f"Archived to {snapshot}")

        output_files = [
            "concept_draft.md", "concept_checkpoint.json", "blueprint.md",
            "founder_summary.md", "feature_spec.md",
            "backlog.json", "handoff_to_dev.json", "founder_summary_ko.md",
        ]
        log_run_summary(
            True,
            output_files,
            len(handoff_dict.get("tasks", [])),
            risk,
            result.get("attempts", 0) if isinstance(result, dict) else 0,
            len(reasons),
        )
        log_pm_audit_event("Workflow", "END", risk=str(risk))

        return {
            "ok": True,
            "risk": risk,
            "attempts": 0,
            "errors": [],
            "risk_reasons": reasons,
        }

    finally:
        # Translation runs before archive on the normal success path.
        # Keep this as a fallback for early returns and exceptions.
        if not translation_checked:
            ensure_founder_summary_korean()
