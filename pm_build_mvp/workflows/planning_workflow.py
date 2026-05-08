import os
import json
import re
import uuid
from crewai import Agent, Task, Crew, Process
from harness.safe_file_tools import safe_read, safe_write, read_workspace_file, write_workspace_file
from harness.schema_validator import validate_handoff, HandoffSchema
from harness.risk_engine import calculate_risk
from harness.audit_hooks import (
    log_pm_audit, log_run_summary, log_validation_error,
    log_pm_audit_event, log_decision_history, log_blueprint_logic, log_creative_process,
    log_reasoning_event, log_system_integrity_alert, log_founder_override,
)
from harness.dev_exporter import create_archive_snapshot
from harness.patch_engine import run_patch_crew
from harness.kernel_guard import (
    load_founder_kernel, save_founder_kernel,
    inject_kernel_guard, assert_kernel_integrity,
    validate_founder_evidence_ref,
)
from harness.llm_factory import (
    build_llm_from_env,
    build_idea_llm, build_idea_critic_llm, build_synthesis_llm,
    build_decision_llm, build_creative_llm,
    build_technical_gen_llm, build_technical_review_llm,
    build_strategic_qa_llm, build_investor_qa_llm,
    build_council_strategic_llm, build_council_execution_llm, build_council_simple_llm,
    build_validation_llm, build_failure_scenario_llm, build_consistency_llm,
    build_escalation_logic_llm, build_escalation_ops_llm, build_escalation_spec_llm,
)
from harness.translator_runner import ensure_founder_summary_korean
from harness.telemetry_projection import generate_all_projections

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
Review the concept draft and output a JSON array of critique items.

Output ONLY a valid JSON array. No markdown fences. No explanation. No other text.

Each item must follow this schema exactly:
{
  "persona": "pm|ops|user|growth|finance",
  "risk": "<specific risk or problem found>",
  "confidence": <0.0 to 1.0>,
  "confidence_basis": ["<reason 1>", "<reason 2>"],
  "conflict_type": "scope_creep|contradiction|missing_risk|ux_vs_ops|growth_vs_scope|speed_vs_quality|priority_contradiction|none",
  "suggested_fix": "<one-line fix or empty string>"
}

Rules:
- Output 3 to 5 items maximum.
- Flag only: scope creep, contradictions, missing risks, execution conflicts.
- No praise. Problems only.
- confidence_basis must contain at least 1 reason.
- If no issues found, return an empty array: []\
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
# v4 system prompts
# ---------------------------------------------------------------------------

_PRODUCT_QA_SYSTEM = """\
You are a strict product QA reviewer.
Perform structural and evidence validation on the provided concept checkpoint.

Output ONLY a valid JSON object. No markdown. No explanation.

Required schema:
{
  "qa_results": [
    {
      "qa_type": "structural|spec|validation|semantic|priority_contradiction",
      "passed": true,
      "finding": "<description or empty string if passed>",
      "severity": "none|warn|fail"
    }
  ],
  "evidence_bindings": [
    {
      "claim": "<claim being validated>",
      "evidence_type": "founder_conviction|market_observation|operational_assumption|user_research|unknown",
      "source_ref": "<e.g. kernel.non_negotiables[0] or 'none'>",
      "assumption": "<explicit assumption or empty string>",
      "confidence": "high|medium|low|unverified"
    }
  ],
  "overall_status": "pass|warn|fail",
  "failure_type": "none|logic|spec|validation|semantic|priority_contradiction",
  "ko_summary": "<1-2 sentence Korean summary>"
}

QA areas to check:
1. Structural QA: logical consistency, no contradictions
2. Spec QA: implementation feasibility, not vague
3. Validation QA: hypotheses are measurable
4. Semantic QA: cross-artifact terminology consistency
5. Priority QA: no execution-level contradictions in must_have_mvp

Evidence rules:
- For every major claim in must_have_mvp, produce one evidence_binding.
- If evidence_type is founder_conviction, source_ref MUST start with "kernel."
- If you cannot find a real kernel reference, set source_ref to "none" and confidence to "unverified".\
"""

_STRATEGIC_QA_FOUNDER_SYSTEM = """\
You are a founder thesis preservation reviewer.
Your ONLY job is to check whether the product blueprint drifts from the founder kernel.

You are STRICTLY PROHIBITED from:
- suggesting new features
- expanding scope
- exploring alternatives

Output ONLY a valid JSON object. No markdown. No explanation.

Required schema:
{
  "checks": [
    {
      "check_type": "thesis_drift|edge_dilution|generic_saasization|anti_pattern_violation",
      "passed": true,
      "finding": "<description or empty if passed>",
      "severity": "none|warn|high"
    }
  ],
  "overall_verdict": "preserved|warn|violated",
  "ko_summary": "<1-2 sentence Korean summary>"
}\
"""

_STRATEGIC_QA_INVESTOR_SYSTEM = """\
You are a market viability analyst.
Your ONLY job is to assess whether this MVP can survive in the market.

You are STRICTLY PROHIBITED from:
- suggesting new features
- expanding scope
- exploring alternatives

Output ONLY a valid JSON object. No markdown. No explanation.

Required schema:
{
  "checks": [
    {
      "check_type": "market_survival|scalability|moat_weakness|demand_uncertainty",
      "passed": true,
      "finding": "<description or empty if passed>",
      "severity": "none|warn|high"
    }
  ],
  "overall_verdict": "viable|warn|not_viable",
  "ko_summary": "<1-2 sentence Korean summary>"
}\
"""

_DECISION_COUNCIL_SYSTEM = """\
You are a senior product architect making the final MVP approval decision.

Given a concept checkpoint and strategic QA results, produce the final council decision.

Output ONLY a valid JSON object. No markdown. No explanation.

Required schema:
{
  "approved_mvp": ["<approved feature or direction>"],
  "rejected_features": ["<rejected feature>"],
  "tradeoffs": ["<explicit tradeoff accepted>"],
  "confidence": {
    "base_confidence": <0.0 to 1.0>,
    "critical_penalties": [
      {"source": "<source>", "severity": "high|medium|low", "penalty": <negative float>}
    ],
    "final_confidence": <0.0 to 1.0>
  },
  "confidence_penalties": ["<human-readable penalty explanation>"],
  "blockers": ["<unresolved blocker or empty list if none>"],
  "verdict": "approved|rejected|needs_revision",
  "ko_summary": "<1-2 sentence Korean summary>"
}

Confidence rules:
- base_confidence: your raw confidence before penalties
- If any strategic QA check has severity "high", apply a penalty that brings final_confidence to <= 0.30
- final_confidence = base_confidence + sum(penalties), clamped to [0.0, 1.0]
- verdict must be "approved" only when final_confidence >= 0.50 AND blockers is empty\
"""

_VALIDATION_STRATEGY_SYSTEM = """\
You are a product validation strategist.
Generate a measurable validation structure for the approved MVP.

Output ONLY a valid JSON object. No markdown. No explanation.

Required schema:
{
  "core_hypothesis": [
    {
      "id": "H-01",
      "statement": "<hypothesis>",
      "kpi": "<measurable KPI>",
      "minimum_success_signal": "<minimum threshold to validate>",
      "signal_latency": "immediate|short|medium|long",
      "decision_impact": "high|medium|low"
    }
  ],
  "failure_modes": [],
  "counterfactuals": ["<what would invalidate this hypothesis>"],
  "next_experiments": ["<first actionable experiment>"],
  "ko_summary": "<1-2 sentence Korean summary>"
}\
"""

_FAILURE_SCENARIO_SYSTEM = """\
You are a failure scenario generator.
Generate realistic collapse scenarios for the provided MVP concept.

Output ONLY a valid JSON array. No markdown. No explanation.

Each item:
{
  "scenario_id": "FS-01",
  "failure_type": "no_show_cascade|abandonment|coordination_collapse|demand_miss|ops_breakdown",
  "description": "<realistic failure description>",
  "trigger": "<what causes this failure>",
  "severity": "critical|high|medium",
  "early_signal": "<observable early warning sign>"
}

Generate 3 to 5 scenarios. Focus on realistic, product-specific risks.\
"""

_CONSISTENCY_GUARDRAIL_SYSTEM = """\
You are a cross-document semantic consistency checker.
Check alignment between the provided artifacts.

Output ONLY a valid JSON object. No markdown. No explanation.

Required schema:
{
  "checks": [
    {
      "comparison": "spec_vs_backlog|validation_vs_kpi|validation_vs_spec|kernel_vs_outputs",
      "passed": true,
      "mismatch": "<description of mismatch or empty if passed>",
      "severity": "none|warn|fail",
      "auto_fixable": true
    }
  ],
  "overall_status": "pass|warn|fail",
  "ko_summary": "<1-2 sentence Korean summary>"
}\
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

def _parse_structured_critiques(raw_critique: str) -> list:
    """Parse structured critique JSON array from model output.

    Returns empty list on parse failure (critique revisions continue unaffected).
    """
    try:
        cleaned = _clean_json_response(raw_critique)
        result = json.loads(cleaned)
        if isinstance(result, list):
            return result
    except (json.JSONDecodeError, ValueError):
        pass
    return []


def _format_critique_for_revision(critiques: list, fallback_text: str) -> str:
    """Convert structured critiques to bullet text for revision prompt.

    Falls back to raw text if parsing failed (empty list).
    """
    if not critiques:
        return fallback_text
    lines = []
    for item in critiques:
        risk = item.get("risk", "")
        fix = item.get("suggested_fix", "")
        persona = item.get("persona", "")
        line = f"- [{persona}] {risk}"
        if fix:
            line += f" → {fix}"
        lines.append(line)
    return "\n".join(lines)


def run_idea_loop(kernel_data: dict | None = None, run_id: str = "", parent_event_id: str | None = None) -> str:
    """Phase 1: Idea Loop

    5-step Flash/mini iteration over raw_ideas.md.
    Outputs current/concept_draft.md with required sections.
    Injects Founder Kernel Guard into generation prompts when kernel_data provided.
    Logs structured critique confidence to reasoning_trace.jsonl.
    Returns the output file path.
    """
    raw_idea = read_workspace_file("raw_ideas.md")
    idea_llm = build_idea_llm()
    critic_llm = build_idea_critic_llm()

    idea_model = os.getenv("OPENROUTER_MODEL_IDEA", "idea_model")
    critic_model = os.getenv("OPENROUTER_MODEL_IDEA_CRITIC", "critic_model")

    log_pm_audit_event("IdeaLoop", "START", model=f"{idea_model},{critic_model}", run_id=run_id)

    # Kernel guard injection
    gen_system = _IDEA_GEN_SYSTEM
    revise_system = _IDEA_REVISE_SYSTEM
    if kernel_data:
        gen_system = inject_kernel_guard(_IDEA_GEN_SYSTEM, kernel_data)
        revise_system = inject_kernel_guard(_IDEA_REVISE_SYSTEM, kernel_data)

    # Step 1: Flash expands raw idea → draft v1
    draft_v1 = idea_llm.call([
        {"role": "system", "content": gen_system},
        {"role": "user", "content": f"Expand this raw idea into an MVP concept:\n\n{raw_idea}"},
    ])

    # Step 2: Mini produces structured critique of draft v1
    critique_raw_1 = critic_llm.call([
        {"role": "system", "content": _IDEA_CRITIQUE_SYSTEM},
        {"role": "user", "content": f"Critique this MVP concept draft:\n\n{draft_v1}"},
    ])
    critiques_1 = _parse_structured_critiques(critique_raw_1)
    critique_text_1 = _format_critique_for_revision(critiques_1, critique_raw_1)

    # Log critique confidence events
    loop_event_id = parent_event_id
    for item in critiques_1:
        loop_event_id = log_reasoning_event(
            run_id=run_id, phase="IdeaLoop",
            event_type="critique_generated",
            artifact="concept_draft_v1",
            details=item,
            parent_event_id=loop_event_id,
        )

    # Step 3: Flash revises based on critique → draft v2
    draft_v2 = idea_llm.call([
        {"role": "system", "content": revise_system},
        {"role": "user", "content": (
            f"Original draft:\n{draft_v1}\n\n"
            f"Critique to apply:\n{critique_text_1}\n\n"
            "Revise the draft."
        )},
    ])

    # Step 4: Mini produces structured critique of draft v2
    critique_raw_2 = critic_llm.call([
        {"role": "system", "content": _IDEA_CRITIQUE_SYSTEM},
        {"role": "user", "content": f"Critique this revised MVP concept draft:\n\n{draft_v2}"},
    ])
    critiques_2 = _parse_structured_critiques(critique_raw_2)
    critique_text_2 = _format_critique_for_revision(critiques_2, critique_raw_2)

    # Log conflict_type events for detected conflicts
    for item in critiques_2:
        if item.get("conflict_type") not in ("none", None, ""):
            loop_event_id = log_reasoning_event(
                run_id=run_id, phase="IdeaLoop",
                event_type="conflict_detected",
                artifact="concept_draft_v2",
                details={"conflict_type": item.get("conflict_type"), "risk": item.get("risk"), "confidence": item.get("confidence")},
                parent_event_id=loop_event_id,
            )

    # Step 5: Flash generates final draft with LOG_META
    final_draft = idea_llm.call([
        {"role": "system", "content": revise_system},
        {"role": "user", "content": (
            f"Revised draft:\n{draft_v2}\n\n"
            f"Final critique to apply:\n{critique_text_2}\n\n"
            "Generate the definitive final concept draft."
        )},
    ])

    # Extract meta for logging; strip from saved file content
    meta = _extract_log_meta(final_draft)
    clean_draft = _strip_log_meta(final_draft)

    write_workspace_file("current/docs/concept_draft.md", clean_draft)

    rejected_list = meta.get("rejected_features", [])
    risks_list = meta.get("risks", [])

    log_pm_audit_event(
        "IdeaLoop", "END",
        selected=meta.get("selected_core"),
        rejected=",".join(rejected_list) or None,
        risk=",".join(risks_list) or None,
        output="current/docs/concept_draft.md",
        summary_ko=meta.get("ko_log_summary"),
        run_id=run_id,
    )
    for feat in rejected_list:
        log_decision_history("IdeaLoop", rejected=feat, reason="non-MVP scope", run_id=run_id)

    return "current/docs/concept_draft.md"


# ---------------------------------------------------------------------------
# Phase 2: Synthesis
# ---------------------------------------------------------------------------

def run_synthesis(run_id: str = "") -> dict:
    """Phase 2: Synthesis

    Compresses concept_draft.md into a structured JSON checkpoint.
    Outputs current/concept_checkpoint.json.
    Returns the parsed checkpoint dict.
    Raises RuntimeError if valid JSON cannot be produced after 1 self-correction.
    """
    draft = read_workspace_file("current/docs/concept_draft.md")
    llm = build_synthesis_llm()

    synthesis_model = os.getenv("OPENROUTER_MODEL_SYNTHESIS", "synthesis_model")
    log_pm_audit_event("Synthesis", "START", model=synthesis_model, run_id=run_id)

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
    write_workspace_file("current/docs/concept_checkpoint.json", content)

    direction = checkpoint.get("recommended_direction", "")
    excluded = checkpoint.get("excluded_features", [])

    log_pm_audit_event(
        "Synthesis", "END",
        selected=direction[:80] if direction else None,
        output="current/docs/concept_checkpoint.json",
        summary_ko=f"핵심 방향: {direction[:60]}" if direction else None,
        run_id=run_id,
    )
    for feat in excluded:
        log_decision_history(
            "Synthesis",
            rejected=feat,
            reason="excluded in synthesis checkpoint",
            summary_ko=f"{feat} MVP 범위에서 제외됨",
            run_id=run_id,
        )

    return checkpoint


# ---------------------------------------------------------------------------
# Phase 3: Decision
# ---------------------------------------------------------------------------

def run_decision(kernel_data: dict | None = None, run_id: str = "") -> dict:
    """Phase 3: Decision

    Reads concept_checkpoint.json, produces definitive blueprint.md.
    Uses claude-opus class model for structural/architectural decisions.
    Logs decisions to blueprint_logic.log and decision_history.log.
    Returns the decision meta dict.
    """
    checkpoint_raw = read_workspace_file("current/docs/concept_checkpoint.json")
    checkpoint = json.loads(checkpoint_raw)
    llm = build_decision_llm()

    decision_model = os.getenv("OPENROUTER_MODEL_DECISION", "decision_model")
    log_pm_audit_event("Decision", "START", model=decision_model, run_id=run_id)

    checkpoint_summary = json.dumps(checkpoint, indent=2, ensure_ascii=False)

    decision_system = _DECISION_SYSTEM
    if kernel_data:
        decision_system = inject_kernel_guard(_DECISION_SYSTEM, kernel_data)

    blueprint_raw = llm.call([
        {"role": "system", "content": decision_system},
        {"role": "user", "content": (
            "Make decisions and write the blueprint based on this concept checkpoint:\n\n"
            f"{checkpoint_summary}"
        )},
    ])

    meta = _extract_decision_meta(blueprint_raw)
    clean_blueprint = _strip_decision_meta(blueprint_raw)

    write_workspace_file("current/docs/blueprint.md", clean_blueprint)

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
        run_id=run_id,
    )
    for opt in meta.get("rejected_options", []):
        log_decision_history(
            "Decision",
            rejected=opt,
            reason="rejected in architecture decision phase",
            run_id=run_id,
        )

    log_pm_audit_event(
        "Decision", "END",
        selected=selected_str,
        rejected=rejected_str,
        output="current/docs/blueprint.md",
        summary_ko=meta.get("ko_log_summary"),
        run_id=run_id,
    )

    return meta


# ---------------------------------------------------------------------------
# Phase 4: Creative Production
# ---------------------------------------------------------------------------

def run_creative_production(kernel_data: dict | None = None, run_id: str = "") -> dict:
    """Phase 4: Creative Production

    Reads blueprint.md, produces:
    - current/founder_summary.md
    - current/feature_spec.md
    Uses two focused calls to the creative (sonnet-class) model.
    Logs framing decisions to creative_process.log.
    Returns combined meta dict.
    """
    blueprint = read_workspace_file("current/docs/blueprint.md")
    llm = build_creative_llm()

    creative_model = os.getenv("OPENROUTER_MODEL_CREATIVE", "creative_model")
    log_pm_audit_event("CreativeProd", "START", model=creative_model, run_id=run_id)

    founder_system = _FOUNDER_SUMMARY_SYSTEM
    spec_system = _FEATURE_SPEC_SYSTEM
    if kernel_data:
        founder_system = inject_kernel_guard(_FOUNDER_SUMMARY_SYSTEM, kernel_data)
        spec_system = inject_kernel_guard(_FEATURE_SPEC_SYSTEM, kernel_data)

    # Call 1: founder_summary.md
    founder_raw = llm.call([
        {"role": "system", "content": founder_system},
        {"role": "user", "content": (
            f"Write the founder summary based on this blueprint:\n\n{blueprint}"
        )},
    ])
    founder_meta = _extract_creative_meta(founder_raw)
    clean_founder = _strip_creative_meta(founder_raw)
    write_workspace_file("current/docs/founder_summary.md", clean_founder)

    # Call 2: feature_spec.md (receives both blueprint and founder summary for coherence)
    spec_raw = llm.call([
        {"role": "system", "content": spec_system},
        {"role": "user", "content": (
            f"Blueprint:\n{blueprint}\n\n"
            f"Founder Summary:\n{clean_founder}\n\n"
            "Write the feature specification."
        )},
    ])
    spec_meta = _extract_creative_meta(spec_raw)
    clean_spec = _strip_creative_meta(spec_raw)
    write_workspace_file("current/docs/feature_spec.md", clean_spec)

    # founder_meta takes priority for combined summary
    combined_meta = {**spec_meta, **founder_meta}

    rejected_framings_str = ", ".join(combined_meta.get("rejected_framings", []))[:120] or None
    log_creative_process(
        "CreativeProd",
        selected=combined_meta.get("narrative_focus"),
        rejected=rejected_framings_str,
        summary_ko=combined_meta.get("ko_log_summary"),
        run_id=run_id,
    )
    log_pm_audit_event(
        "CreativeProd", "END",
        selected=combined_meta.get("narrative_focus"),
        output="current/docs/founder_summary.md,current/docs/feature_spec.md",
        summary_ko=combined_meta.get("ko_log_summary"),
        run_id=run_id,
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

def run_technical_production(run_id: str = "") -> None:
    """Phase 5: Technical Production

    Reads blueprint.md, founder_summary.md, feature_spec.md.
    Flash generates combined backlog + handoff draft.
    mini reviews for schema/enum/completeness/dependency issues.
    Flash revises if issues found.

    Outputs:
    - current/backlog.json  (with basic structural validation; warns, does not fail)
    - current/handoff_to_dev.json  (raw; final gate is validate_handoff() in orchestration)
    """
    blueprint = read_workspace_file("current/docs/blueprint.md")
    founder_summary = read_workspace_file("current/docs/founder_summary.md")
    feature_spec = read_workspace_file("current/docs/feature_spec.md")

    gen_llm = build_technical_gen_llm()
    review_llm = build_technical_review_llm()

    tech_gen_model = os.getenv("OPENROUTER_MODEL_TECH_GEN", "tech_gen_model")
    tech_review_model = os.getenv("OPENROUTER_MODEL_TECH_REVIEW", "tech_review_model")
    log_pm_audit_event("TechnicalProd", "START", model=f"{tech_gen_model},{tech_review_model}", run_id=run_id)

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
        "current/tech/backlog.json",
        json.dumps(backlog, indent=2, ensure_ascii=False),
    )
    write_workspace_file(
        "current/tech/handoff_to_dev.json",
        json.dumps(handoff, indent=2, ensure_ascii=False),
    )

    log_pm_audit_event(
        "TechnicalProd", "END",
        output="current/tech/backlog.json,current/tech/handoff_to_dev.json",
        summary_ko=review_result.get("ko_log_summary"),
        run_id=run_id,
    )


# ---------------------------------------------------------------------------
# Phase v4-B6: Product QA Gate
# ---------------------------------------------------------------------------

def run_product_qa_gate(
    kernel_data: dict | None = None,
    run_id: str = "",
    parent_event_id: str | None = None,
) -> dict:
    """Phase v4-B6: Product QA Gate

    Runs structural/spec/validation/semantic/priority QA with evidence binding.
    - fabricated founder evidence → system_integrity_alert + immediate reject
    - failure_type logged for escalation routing
    Returns the QA result dict.
    Raises RuntimeError on immediate reject (fabricated founder evidence).
    """
    checkpoint_raw = read_workspace_file("current/docs/concept_checkpoint.json")
    blueprint = read_workspace_file("current/docs/blueprint.md")
    llm = build_idea_critic_llm()  # cheap model — product QA is structural

    log_pm_audit_event("ProductQA", "START")

    context = (
        f"## Concept Checkpoint\n{checkpoint_raw}\n\n"
        f"## Blueprint\n{blueprint}"
    )
    if kernel_data:
        kernel_summary = json.dumps(
            {k: v for k, v in kernel_data.items() if k != "kernel_hash"},
            ensure_ascii=False,
        )
        context = f"## Founder Kernel\n{kernel_summary}\n\n" + context

    raw = llm.call([
        {"role": "system", "content": _PRODUCT_QA_SYSTEM},
        {"role": "user", "content": f"Run product QA on these artifacts:\n\n{context}"},
    ])

    try:
        result = json.loads(_clean_json_response(raw))
    except (json.JSONDecodeError, ValueError):
        log_pm_audit("ProductQA | Status=PARSE_FAIL | falling back to warn")
        result = {"overall_status": "warn", "failure_type": "none", "qa_results": [], "evidence_bindings": []}

    # --- Evidence integrity validation ---
    integrity_violations = []
    for binding in result.get("evidence_bindings", []):
        if binding.get("evidence_type") == "founder_conviction":
            source_ref = binding.get("source_ref", "none")
            if source_ref == "none" or not validate_founder_evidence_ref(source_ref, kernel_data or {}):
                alert_id = log_system_integrity_alert(
                    run_id=run_id,
                    phase="ProductQA",
                    claim=binding.get("claim", ""),
                    source_ref=source_ref,
                    parent_event_id=parent_event_id,
                )
                integrity_violations.append({"claim": binding.get("claim"), "source_ref": source_ref, "alert_id": alert_id})

    if integrity_violations:
        raise RuntimeError(
            f"ProductQA: IMMEDIATE REJECT — fabricated founder evidence detected. "
            f"Violations: {integrity_violations}. "
            "This is a system integrity violation, not an escalation."
        )

    # --- Log QA failures ---
    qa_event_id = parent_event_id
    for qa in result.get("qa_results", []):
        if not qa.get("passed", True):
            qa_event_id = log_reasoning_event(
                run_id=run_id, phase="ProductQA",
                event_type="validation_warning",
                artifact="concept_checkpoint",
                details={
                    "qa_type": qa.get("qa_type"),
                    "finding": qa.get("finding"),
                    "severity": qa.get("severity"),
                    "failure_type": result.get("failure_type"),
                },
                parent_event_id=qa_event_id,
            )

    # --- Escalation routing for failures ---
    overall = result.get("overall_status", "pass")
    failure_type = result.get("failure_type", "none")
    if overall == "fail" and failure_type != "none":
        _run_escalation_retry(failure_type, context, run_id, qa_event_id)

    write_workspace_file(
        "current/qa/product_qa_result.json",
        json.dumps(result, indent=2, ensure_ascii=False),
    )
    log_pm_audit_event(
        "ProductQA", "END",
        risk=overall,
        output="current/qa/product_qa_result.json",
        summary_ko=result.get("ko_summary"),
    )
    return result


def _run_escalation_retry(
    failure_type: str,
    context: str,
    run_id: str,
    parent_event_id: str | None = None,
) -> None:
    """Route QA failure to the specialist escalation model.

    failure_type → escalation model:
      logic                 → escalation_logic_llm
      priority_contradiction→ escalation_logic_llm
      spec                  → escalation_spec_llm
      semantic              → escalation_spec_llm
      validation            → escalation_ops_llm
    """
    _ESCALATION_MAP = {
        "logic": ("OPENROUTER_MODEL_ESCALATION_LOGIC", build_escalation_logic_llm),
        "priority_contradiction": ("OPENROUTER_MODEL_ESCALATION_LOGIC", build_escalation_logic_llm),
        "spec": ("OPENROUTER_MODEL_ESCALATION_SPEC", build_escalation_spec_llm),
        "semantic": ("OPENROUTER_MODEL_ESCALATION_SPEC", build_escalation_spec_llm),
        "validation": ("OPENROUTER_MODEL_ESCALATION_OPS", build_escalation_ops_llm),
    }
    entry = _ESCALATION_MAP.get(failure_type)
    if not entry:
        return
    env_var, factory = entry
    if not os.getenv(env_var, "").strip():
        log_pm_audit(
            f"Escalation | Status=SKIPPED | FailureType={failure_type} | "
            f"Reason={env_var} not configured"
        )
        return
    try:
        llm = factory()
        llm.call([
            {"role": "system", "content": "You are a specialist reviewer. Identify the root cause of the following QA failure and suggest a specific resolution."},
            {"role": "user", "content": f"Failure type: {failure_type}\n\nContext:\n{context}"},
        ])
        log_reasoning_event(
            run_id=run_id, phase="Escalation",
            event_type="escalation_triggered",
            artifact="product_qa",
            details={"failure_type": failure_type, "model": os.getenv(env_var, "")},
            parent_event_id=parent_event_id,
        )
    except Exception as exc:
        log_pm_audit(f"Escalation | Status=ERROR | FailureType={failure_type} | Error={exc}")


# ---------------------------------------------------------------------------
# Phase v4-C7: Strategic QA Gate
# ---------------------------------------------------------------------------

def run_strategic_qa_gate(
    kernel_data: dict | None = None,
    run_id: str = "",
    parent_event_id: str | None = None,
) -> dict:
    """Phase v4-C7: Strategic QA Gate

    Founder Preservation Check + Market Viability Check.
    Runs ONLY after Product QA passes.
    Strictly prohibits exploration or feature expansion.
    Returns combined strategic QA result dict.
    """
    if not os.getenv("OPENROUTER_MODEL_STRATEGIC_QA", "").strip():
        log_pm_audit("StrategicQA | Status=SKIPPED | Reason=OPENROUTER_MODEL_STRATEGIC_QA not configured")
        return {"overall_verdict": "skipped", "checks": []}

    blueprint = read_workspace_file("current/docs/blueprint.md")
    checkpoint_raw = read_workspace_file("current/docs/concept_checkpoint.json")
    log_pm_audit_event("StrategicQA", "START")

    context = f"## Blueprint\n{blueprint}\n\n## Concept Checkpoint\n{checkpoint_raw}"
    if kernel_data:
        kernel_summary = json.dumps(
            {k: v for k, v in kernel_data.items() if k != "kernel_hash"},
            ensure_ascii=False,
        )
        context = f"## Founder Kernel\n{kernel_summary}\n\n" + context

    # Founder Preservation Check
    founder_llm = build_strategic_qa_llm()
    founder_raw = founder_llm.call([
        {"role": "system", "content": _STRATEGIC_QA_FOUNDER_SYSTEM},
        {"role": "user", "content": f"Check founder thesis preservation:\n\n{context}"},
    ])
    try:
        founder_result = json.loads(_clean_json_response(founder_raw))
    except (json.JSONDecodeError, ValueError):
        founder_result = {"overall_verdict": "warn", "checks": []}

    # Market Viability Check (optional — needs investor model)
    investor_result = {"overall_verdict": "skipped", "checks": []}
    if os.getenv("OPENROUTER_MODEL_INVESTOR_QA", "").strip():
        investor_llm = build_investor_qa_llm()
        investor_raw = investor_llm.call([
            {"role": "system", "content": _STRATEGIC_QA_INVESTOR_SYSTEM},
            {"role": "user", "content": f"Check market viability:\n\n{context}"},
        ])
        try:
            investor_result = json.loads(_clean_json_response(investor_raw))
        except (json.JSONDecodeError, ValueError):
            investor_result = {"overall_verdict": "warn", "checks": []}

    combined = {
        "founder_preservation": founder_result,
        "market_viability": investor_result,
        "has_high_severity": any(
            c.get("severity") == "high"
            for checks in [founder_result.get("checks", []), investor_result.get("checks", [])]
            for c in checks
        ),
    }

    # Log critical violations
    qa_event_id = parent_event_id
    for check in founder_result.get("checks", []) + investor_result.get("checks", []):
        if not check.get("passed", True) or check.get("severity") in ("warn", "high"):
            qa_event_id = log_reasoning_event(
                run_id=run_id, phase="StrategicQA",
                event_type="validation_warning",
                artifact="blueprint",
                details=check,
                parent_event_id=qa_event_id,
            )

    if combined["has_high_severity"]:
        log_reasoning_event(
            run_id=run_id, phase="StrategicQA",
            event_type="escalation_triggered",
            artifact="strategic_qa",
            details={"reason": "high_severity_risk_detected", "combined": combined},
            parent_event_id=qa_event_id,
        )

    write_workspace_file(
        "current/qa/strategic_qa_result.json",
        json.dumps(combined, indent=2, ensure_ascii=False),
    )
    log_pm_audit_event(
        "StrategicQA", "END",
        risk="high_severity" if combined["has_high_severity"] else "none",
        output="current/qa/strategic_qa_result.json",
    )
    return combined


# ---------------------------------------------------------------------------
# Phase v4-C8: Decision Council
# ---------------------------------------------------------------------------

def run_decision_council(
    kernel_data: dict | None = None,
    run_id: str = "",
    parent_event_id: str | None = None,
) -> dict:
    """Phase v4-C8: Decision Council

    Final MVP approval with tradeoff resolution and confidence aggregation.
    Applies non-linear confidence clamp when Strategic QA has high severity risks.
    Returns council decision dict.
    """
    if not os.getenv("OPENROUTER_MODEL_COUNCIL_STRATEGIC", "").strip():
        log_pm_audit("DecisionCouncil | Status=SKIPPED | Reason=OPENROUTER_MODEL_COUNCIL_STRATEGIC not configured")
        return {"verdict": "skipped", "approved_mvp": [], "blockers": []}

    checkpoint_raw = read_workspace_file("current/docs/concept_checkpoint.json")
    blueprint = read_workspace_file("current/docs/blueprint.md")
    strategic_qa_raw = read_workspace_file("current/qa/strategic_qa_result.json")
    log_pm_audit_event("DecisionCouncil", "START")

    try:
        strategic_qa = json.loads(strategic_qa_raw) if not strategic_qa_raw.startswith("Error:") else {}
    except json.JSONDecodeError:
        strategic_qa = {}

    has_high_severity = strategic_qa.get("has_high_severity", False)

    context = (
        f"## Concept Checkpoint\n{checkpoint_raw}\n\n"
        f"## Blueprint\n{blueprint}\n\n"
        f"## Strategic QA Results\n{json.dumps(strategic_qa, indent=2, ensure_ascii=False)}"
    )

    council_system = _DECISION_COUNCIL_SYSTEM
    if kernel_data:
        council_system = inject_kernel_guard(_DECISION_COUNCIL_SYSTEM, kernel_data)

    llm = build_council_strategic_llm()
    raw = llm.call([
        {"role": "system", "content": council_system},
        {"role": "user", "content": f"Make the final MVP decision:\n\n{context}"},
    ])

    try:
        result = json.loads(_clean_json_response(raw))
    except (json.JSONDecodeError, ValueError):
        log_pm_audit("DecisionCouncil | Status=PARSE_FAIL | returning default reject")
        result = {"verdict": "needs_revision", "approved_mvp": [], "blockers": ["council_parse_failure"]}

    # Non-linear confidence clamp: if any strategic QA high severity, force confidence <= 0.30
    if has_high_severity:
        conf = result.get("confidence", {})
        current_final = conf.get("final_confidence", 0.5)
        if current_final > 0.30:
            penalty = 0.30 - current_final
            conf.setdefault("critical_penalties", []).append({
                "source": "strategic_qa_high_severity",
                "severity": "high",
                "penalty": round(penalty, 4),
            })
            conf["final_confidence"] = 0.30
            result["confidence"] = conf
            result.setdefault("confidence_penalties", []).append(
                "Non-linear clamp applied: Strategic QA high severity risk forced confidence to 0.30"
            )
            log_reasoning_event(
                run_id=run_id, phase="DecisionCouncil",
                event_type="confidence_penalty_applied",
                artifact="council_decision",
                details={"clamp": 0.30, "previous": round(current_final, 4)},
                parent_event_id=parent_event_id,
            )

    # Enforce approval rules
    final_confidence = result.get("confidence", {}).get("final_confidence", 0.5)
    blockers = result.get("blockers", [])
    if result.get("verdict") == "approved" and (final_confidence < 0.50 or blockers):
        result["verdict"] = "needs_revision"
        result.setdefault("confidence_penalties", []).append(
            f"Approval blocked: final_confidence={final_confidence:.2f} or unresolved blockers={blockers}"
        )

    council_event_id = log_reasoning_event(
        run_id=run_id, phase="DecisionCouncil",
        event_type="council_approved" if result.get("verdict") == "approved" else "council_rejected",
        artifact="council_decision",
        details={
            "verdict": result.get("verdict"),
            "final_confidence": final_confidence,
            "blockers": blockers,
        },
        parent_event_id=parent_event_id,
    )

    # Log rejected features to decision_history
    for feat in result.get("rejected_features", []):
        log_decision_history(
            "DecisionCouncil", rejected=feat,
            reason="rejected by decision council",
        )

    write_workspace_file(
        "current/decision/council_decision.json",
        json.dumps(result, indent=2, ensure_ascii=False),
    )
    log_pm_audit_event(
        "DecisionCouncil", "END",
        selected=result.get("verdict"),
        output="current/decision/council_decision.json",
        summary_ko=result.get("ko_summary"),
    )
    return result


# ---------------------------------------------------------------------------
# Phase v4-D9: Validation Strategy Engine
# ---------------------------------------------------------------------------

def run_validation_strategy_engine(
    run_id: str = "",
    parent_event_id: str | None = None,
) -> dict:
    """Phase v4-D9: Validation Strategy Engine

    Generates hypothesis/KPI/failure mode structure.
    Failure scenarios generated by cheap model.
    Returns combined validation strategy dict.
    """
    if not os.getenv("OPENROUTER_MODEL_VALIDATION", "").strip():
        log_pm_audit("ValidationEngine | Status=SKIPPED | Reason=OPENROUTER_MODEL_VALIDATION not configured")
        return {"core_hypothesis": [], "failure_modes": [], "skipped": True}

    council_raw = read_workspace_file("current/decision/council_decision.json")
    blueprint = read_workspace_file("current/docs/blueprint.md")
    log_pm_audit_event("ValidationEngine", "START")

    context = f"## Blueprint\n{blueprint}\n\n## Council Decision\n{council_raw}"

    # Core hypothesis + KPI mapping
    val_llm = build_validation_llm()
    val_raw = val_llm.call([
        {"role": "system", "content": _VALIDATION_STRATEGY_SYSTEM},
        {"role": "user", "content": f"Generate the validation strategy:\n\n{context}"},
    ])
    try:
        val_result = json.loads(_clean_json_response(val_raw))
    except (json.JSONDecodeError, ValueError):
        val_result = {"core_hypothesis": [], "failure_modes": [], "counterfactuals": [], "next_experiments": []}

    # Failure scenarios (cheap model, optional)
    failure_scenarios = []
    if os.getenv("OPENROUTER_MODEL_FAILURE_SCENARIO", "").strip():
        fs_llm = build_failure_scenario_llm()
        fs_raw = fs_llm.call([
            {"role": "system", "content": _FAILURE_SCENARIO_SYSTEM},
            {"role": "user", "content": f"Generate failure scenarios for:\n\n{context}"},
        ])
        try:
            failure_scenarios = json.loads(_clean_json_response(fs_raw))
        except (json.JSONDecodeError, ValueError):
            failure_scenarios = []

    val_result["failure_modes"] = failure_scenarios

    # Log hypothesis events
    val_event_id = parent_event_id
    for hyp in val_result.get("core_hypothesis", []):
        val_event_id = log_reasoning_event(
            run_id=run_id, phase="ValidationEngine",
            event_type="validation_warning",
            artifact=hyp.get("id", "hypothesis"),
            details={"kpi": hyp.get("kpi"), "signal_latency": hyp.get("signal_latency"), "decision_impact": hyp.get("decision_impact")},
            parent_event_id=val_event_id,
        )

    write_workspace_file(
        "current/validation/validation_strategy.json",
        json.dumps(val_result, indent=2, ensure_ascii=False),
    )
    log_pm_audit_event(
        "ValidationEngine", "END",
        output="current/validation/validation_strategy.json",
        summary_ko=val_result.get("ko_summary"),
    )
    return val_result


# ---------------------------------------------------------------------------
# Phase v4-D10: Production Consistency Guardrail
# ---------------------------------------------------------------------------

def run_consistency_guardrail(
    kernel_data: dict | None = None,
    run_id: str = "",
    parent_event_id: str | None = None,
) -> dict:
    """Phase v4-D10: Production Consistency Guardrail

    Cross-document semantic alignment check.
    warn → logged and auto-fix hint recorded
    fail → escalation_triggered event logged
    Returns guardrail result dict.
    """
    if not os.getenv("OPENROUTER_MODEL_CONSISTENCY", "").strip():
        log_pm_audit("ConsistencyGuardrail | Status=SKIPPED | Reason=OPENROUTER_MODEL_CONSISTENCY not configured")
        return {"overall_status": "skipped", "checks": []}

    feature_spec = read_workspace_file("current/docs/feature_spec.md")
    backlog_raw = read_workspace_file("current/tech/backlog.json")
    validation_raw = read_workspace_file("current/validation/validation_strategy.json")
    founder_summary = read_workspace_file("current/docs/founder_summary.md")
    log_pm_audit_event("ConsistencyGuardrail", "START")

    kernel_summary = ""
    if kernel_data:
        kernel_summary = f"## Founder Kernel\n{json.dumps({k: v for k, v in kernel_data.items() if k != 'kernel_hash'}, ensure_ascii=False)}\n\n"

    context = (
        f"{kernel_summary}"
        f"## Feature Spec\n{feature_spec}\n\n"
        f"## Backlog\n{backlog_raw}\n\n"
        f"## Validation Strategy\n{validation_raw}\n\n"
        f"## Founder Summary\n{founder_summary}"
    )

    llm = build_consistency_llm()
    raw = llm.call([
        {"role": "system", "content": _CONSISTENCY_GUARDRAIL_SYSTEM},
        {"role": "user", "content": f"Check cross-document consistency:\n\n{context}"},
    ])

    try:
        result = json.loads(_clean_json_response(raw))
    except (json.JSONDecodeError, ValueError):
        result = {"overall_status": "warn", "checks": []}

    # Process checks
    cg_event_id = parent_event_id
    for check in result.get("checks", []):
        severity = check.get("severity", "none")
        if severity in ("warn", "fail"):
            cg_event_id = log_reasoning_event(
                run_id=run_id, phase="ConsistencyGuardrail",
                event_type="validation_warning" if severity == "warn" else "escalation_triggered",
                artifact=check.get("comparison", "document"),
                details=check,
                parent_event_id=cg_event_id,
            )

    write_workspace_file(
        "current/qa/consistency_result.json",
        json.dumps(result, indent=2, ensure_ascii=False),
    )
    log_pm_audit_event(
        "ConsistencyGuardrail", "END",
        risk=result.get("overall_status"),
        output="current/qa/consistency_result.json",
        summary_ko=result.get("ko_summary"),
    )
    return result


def run_final_validation_and_patch(run_id: str = "") -> tuple:
    """Validate handoff_to_dev.json and patch if needed.

    Runs up to 3 validate attempts and up to 2 patch crew calls.
    Returns (True, handoff_dict) on success.
    Returns (False, {"attempts": N, "errors": [...]}) on max retries exhausted.
    """
    max_retries = 3
    attempts = 0
    handoff_dict = {}

    while attempts < max_retries:
        handoff_content = read_workspace_file("current/tech/handoff_to_dev.json")
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
                run_id=run_id, phase="FinalValidation",
            )

        if attempts < max_retries:
            run_patch_crew("current/tech/handoff_to_dev.json", errors)

    return False, {"attempts": attempts, "errors": errors}


def run_planning():
    """Phase-based MVP planning workflow (v4).

    Execution order:
      0. load_founder_kernel()     — founder_kernel.json (create template if missing)
      1. run_idea_loop()           — concept_draft.md + kernel guard
      2. run_synthesis()           — concept_checkpoint.json
      3. run_decision()            — blueprint.md + kernel guard
      4. [v4] run_product_qa_gate()       — product_qa_result.json
      5. [v4] run_strategic_qa_gate()     — strategic_qa_result.json
      6. [v4] run_decision_council()      — council_decision.json
      7. run_creative_production() — founder_summary.md, feature_spec.md + kernel guard
      8. run_technical_production()— backlog.json, handoff_to_dev.json
      9. run_final_validation_and_patch() — validate_handoff + patch loop
     10. [v4] run_validation_strategy_engine() — validation_strategy.json
     11. [v4] run_consistency_guardrail()      — consistency_result.json
     12. calculate_risk()
     13. ensure_founder_summary_korean()
     14. create_archive_snapshot()
    """
    run_id = str(uuid.uuid4())
    log_pm_audit_event("Workflow", "START", run_id=run_id)
    log_reasoning_event(
        run_id=run_id, phase="Workflow", event_type="run_start",
        domain="workflow", category="lifecycle",
        artifact="run_start", details={"run_id": run_id},
    )

    # Load and verify founder kernel
    kernel_data = load_founder_kernel()
    save_founder_kernel(kernel_data)  # ensures hash is stamped
    kernel_hash = kernel_data.get("kernel_hash", "")
    log_pm_audit(f"KernelGuard | Status=LOADED | Hash={kernel_hash[:12]}...")

    translation_checked = False
    workflow_event_id = None

    try:
        print("Phase 1: Idea Loop")
        workflow_event_id = log_reasoning_event(
            run_id=run_id, phase="IdeaLoop", event_type="critique_generated",
            artifact="raw_ideas", details={"step": "start"}, parent_event_id=workflow_event_id,
        )
        run_idea_loop(kernel_data=kernel_data, run_id=run_id, parent_event_id=workflow_event_id)
        assert_kernel_integrity(kernel_data, "post-IdeaLoop")

        print("Phase 2: Synthesis")
        run_synthesis(run_id=run_id)

        print("Phase 3: Decision")
        run_decision(kernel_data=kernel_data, run_id=run_id)
        assert_kernel_integrity(kernel_data, "post-Decision")

        print("Phase v4-B6: Product QA Gate")
        qa_result = run_product_qa_gate(kernel_data=kernel_data, run_id=run_id, parent_event_id=workflow_event_id)
        workflow_event_id = log_reasoning_event(
            run_id=run_id, phase="ProductQA", event_type="validation_warning",
            artifact="product_qa_result",
            details={"overall_status": qa_result.get("overall_status")},
            parent_event_id=workflow_event_id,
        )

        print("Phase v4-C7: Strategic QA Gate")
        strategic_result = run_strategic_qa_gate(kernel_data=kernel_data, run_id=run_id, parent_event_id=workflow_event_id)
        workflow_event_id = log_reasoning_event(
            run_id=run_id, phase="StrategicQA", event_type="validation_warning",
            artifact="strategic_qa_result",
            details={"has_high_severity": strategic_result.get("has_high_severity", False)},
            parent_event_id=workflow_event_id,
        )

        print("Phase v4-C8: Decision Council")
        council_result = run_decision_council(kernel_data=kernel_data, run_id=run_id, parent_event_id=workflow_event_id)
        council_verdict = council_result.get("verdict", "skipped")
        workflow_event_id = log_reasoning_event(
            run_id=run_id, phase="DecisionCouncil",
            event_type="council_approved" if council_verdict == "approved" else "council_rejected",
            artifact="council_decision",
            details={"verdict": council_verdict},
            parent_event_id=workflow_event_id,
        )
        if council_verdict not in ("approved", "skipped"):
            log_pm_audit(f"Workflow | DecisionCouncil verdict={council_verdict} — continuing in warn mode")

        print("Phase 4: Creative Production")
        run_creative_production(kernel_data=kernel_data, run_id=run_id)
        assert_kernel_integrity(kernel_data, "post-CreativeProd")

        print("Phase 5: Technical Production")
        run_technical_production(run_id=run_id)

        print("Phase 6: Final Validation + Patch")
        ok, result = run_final_validation_and_patch(run_id=run_id)
        if not ok:
            print("Max retries reached. Auto-rejecting output.")
            log_pm_audit("Workflow failed: Max PATCH retries reached.")
            log_run_summary(False, ["handoff_to_dev.json"], 0, 0, result["attempts"], 0, run_id=run_id)
            return {
                "ok": False,
                "risk": None,
                "attempts": result["attempts"],
                "errors": result["errors"],
            }

        handoff_dict = result

        print("Phase v4-D9: Validation Strategy Engine")
        run_validation_strategy_engine(run_id=run_id, parent_event_id=workflow_event_id)

        print("Phase v4-D10: Consistency Guardrail")
        run_consistency_guardrail(kernel_data=kernel_data, run_id=run_id, parent_event_id=workflow_event_id)

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
            "product_qa_result.json", "strategic_qa_result.json",
            "council_decision.json", "validation_strategy.json", "consistency_result.json",
        ]
        log_run_summary(
            True,
            output_files,
            len(handoff_dict.get("tasks", [])),
            risk,
            result.get("attempts", 0) if isinstance(result, dict) else 0,
            len(reasons),
            run_id=run_id,
        )
        log_reasoning_event(
            run_id=run_id, phase="Workflow", event_type="council_approved",
            artifact="run_complete",
            details={"risk": risk, "council_verdict": council_verdict, "kernel_hash": kernel_hash[:12]},
            parent_event_id=workflow_event_id,
        )
        log_pm_audit_event("Workflow", "END", risk=str(risk), run_id=run_id)
        generate_all_projections(run_id=run_id)

        return {
            "ok": True,
            "risk": risk,
            "attempts": 0,
            "errors": [],
            "risk_reasons": reasons,
            "council_verdict": council_verdict,
            "kernel_hash": kernel_hash,
            "run_id": run_id,
        }

    finally:
        if not translation_checked:
            ensure_founder_summary_korean()

