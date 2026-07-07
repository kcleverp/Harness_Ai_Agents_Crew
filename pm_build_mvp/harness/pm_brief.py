"""Load and format PM discovery brief for downstream planning phases."""
from __future__ import annotations

import json
import os

from harness.paths import CURRENT_DIR
from harness.safe_file_tools import read_workspace_file

PM_BRIEF_REL = "current/discovery/pm_brief.json"
USER_MODEL_REL = "current/user/user_model.json"
PROBLEM_REL = "current/opportunity/problem_statement.json"
OPP_REL = "current/opportunity/opportunity_model.json"


def _read_json_file(rel_path: str) -> dict | None:
    raw = read_workspace_file(rel_path)
    if raw.startswith("Error:"):
        return None
    try:
        doc = json.loads(raw)
        return doc if isinstance(doc, dict) else None
    except json.JSONDecodeError:
        return None


def load_pm_brief() -> dict | None:
    """Prefer pm_brief.json; assemble from legacy upstream files if needed."""
    brief = _read_json_file(PM_BRIEF_REL)
    if brief:
        return brief

    user = _read_json_file(USER_MODEL_REL)
    problem = _read_json_file(PROBLEM_REL)
    opp = _read_json_file(OPP_REL)
    if not any((user, problem, opp)):
        return None

    persona = user.get("persona") if user else None
    if not persona and user and user.get("personas"):
        legacy = user["personas"][0] if isinstance(user["personas"], list) else {}
        if isinstance(legacy, dict):
            persona = {
                "name": legacy.get("name"),
                "role": legacy.get("role"),
                "job_to_be_done": (user.get("jtbd") or [{}])[0].get("job") if user.get("jtbd") else None,
                "biggest_pain": (legacy.get("frustrations") or [None])[0],
            }

    assembled: dict = {}
    if persona:
        assembled["persona"] = persona
    if problem:
        assembled["problem_statement"] = problem.get("problem_statement")
        assembled["pain_points"] = problem.get("pain_points")
        assembled["friction"] = problem.get("friction")
    if opp:
        assembled["opportunity"] = {
            "market_size": opp.get("market_size"),
            "switching_cost": opp.get("switching_cost"),
            "competition": opp.get("competition"),
            "opportunity_score": opp.get("opportunity_score") or (opp.get("priority_score", 0) / 10),
            "recommended_direction": opp.get("recommended_direction"),
            "impact": opp.get("impact"),
            "reach": opp.get("reach"),
            "risk": opp.get("risk"),
        }
    if user and user.get("ko_summary"):
        assembled["ko_summary"] = user["ko_summary"]
    return assembled or None


def format_persona_line(persona: dict) -> str:
    parts = [
        persona.get("name"),
        persona.get("role"),
        persona.get("environment"),
    ]
    head = " · ".join(p for p in parts if p)
    lines = [head] if head else []
    for label, key in (
        ("JTBD", "job_to_be_done"),
        ("현재 도구", "current_solution"),
        ("핵심 고통", "biggest_pain"),
        ("성공 기준", "success_metric"),
    ):
        val = persona.get(key)
        if val:
            lines.append(f"- {label}: {val}")
    return "\n".join(lines)


def load_pm_brief_context() -> str:
    brief = load_pm_brief()
    if not brief:
        return ""
    sections: list[str] = ["## PM Discovery Brief", ""]

    persona = brief.get("persona")
    if isinstance(persona, dict) and persona:
        sections.append("### Persona")
        sections.append(format_persona_line(persona))
        sections.append("")

    if brief.get("problem_statement"):
        sections.append("### Problem Statement")
        sections.append(str(brief["problem_statement"]))
        sections.append("")

    for pp in brief.get("pain_points") or []:
        if isinstance(pp, dict) and pp.get("description"):
            sections.append(f"- Pain ({pp.get('severity', '?')}): {pp['description']}")
    if brief.get("pain_points"):
        sections.append("")

    opp = brief.get("opportunity")
    if isinstance(opp, dict) and opp:
        sections.append("### Opportunity")
        score = opp.get("opportunity_score")
        sections.append(
            f"score={score} · market={opp.get('market_size')} · "
            f"competition={opp.get('competition')} · switching={opp.get('switching_cost')} · "
            f"direction={opp.get('recommended_direction')}"
        )
        if opp.get("rationale"):
            sections.append(str(opp["rationale"]))
        sections.append("")

    if brief.get("reconstruction_notes"):
        sections.append("### Reconstruction Notes")
        for note in brief["reconstruction_notes"]:
            sections.append(f"- {note}")
        sections.append("")

    if brief.get("ko_summary"):
        sections.append(f"**KO:** {brief['ko_summary']}")

    return "\n".join(sections).strip()


def sync_legacy_upstream_files(brief: dict) -> None:
    """Write user/problem/opportunity JSON from unified pm_brief for compatibility."""
    from harness.safe_file_tools import write_workspace_file

    persona = brief.get("persona") or {}
    opp = brief.get("opportunity") or {}

    user_model = {
        "persona": persona,
        "personas": [{
            "name": persona.get("name"),
            "role": persona.get("role"),
            "goals": [persona.get("job_to_be_done")] if persona.get("job_to_be_done") else [],
            "frustrations": [persona.get("biggest_pain")] if persona.get("biggest_pain") else [],
        }] if persona else [],
        "jtbd": [{
            "job": persona.get("job_to_be_done"),
            "context": persona.get("environment"),
            "outcome": persona.get("success_metric"),
        }] if persona.get("job_to_be_done") else [],
        "icp": format_persona_line(persona) if persona else "",
        "confidence": brief.get("confidence"),
        "ko_summary": brief.get("ko_summary"),
    }
    write_workspace_file(USER_MODEL_REL, json.dumps(user_model, indent=2, ensure_ascii=False))

    problem_doc = {
        "problem_statement": brief.get("problem_statement", ""),
        "pain_points": brief.get("pain_points") or [],
        "friction": brief.get("friction") or [],
        "confidence": brief.get("confidence"),
        "ko_summary": brief.get("ko_summary"),
    }
    write_workspace_file(PROBLEM_REL, json.dumps(problem_doc, indent=2, ensure_ascii=False))

    opportunity_doc = {
        "market_size": opp.get("market_size"),
        "switching_cost": opp.get("switching_cost"),
        "competition": opp.get("competition"),
        "opportunity_score": opp.get("opportunity_score"),
        "recommended_direction": opp.get("recommended_direction", "investigate"),
        "priority_score": round(float(opp.get("opportunity_score", 5)) * 10, 1),
        "confidence": brief.get("confidence"),
        "ko_summary": brief.get("ko_summary"),
        "impact": opp.get("impact"),
        "reach": opp.get("reach"),
        "risk": opp.get("risk"),
    }
    write_workspace_file(OPP_REL, json.dumps(opportunity_doc, indent=2, ensure_ascii=False))


def enrich_checkpoint_from_brief(checkpoint: dict) -> dict:
    brief = load_pm_brief()
    if not brief:
        return checkpoint
    out = dict(checkpoint)
    persona = brief.get("persona") or {}
    if persona:
        line = format_persona_line(persona)
        if line and (not out.get("target_user") or len(str(out["target_user"])) < 40):
            out["target_user"] = line.split("\n")[0]
    ps = brief.get("problem_statement")
    if ps and (not out.get("problem") or len(str(out["problem"])) < 40):
        out["problem"] = ps
    opp = brief.get("opportunity") or {}
    if opp.get("recommended_direction") == "defer" and not out.get("key_risks"):
        out["key_risks"] = [f"Opportunity score {opp.get('opportunity_score')} — market/competition risk"]
    return out
