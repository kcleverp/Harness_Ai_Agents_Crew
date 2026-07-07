"""Build agent profile payload for Live Feed detail panel."""
from __future__ import annotations

import json
import os

from harness.batch_translator import ensure_decisions_korean_if_needed
from harness.confidence_scoring import compute_product_qa_confidence
from harness.decisions_aggregate import aggregate_decisions
from harness.paths import CANONICAL_TRACE
from harness.role_registry import resolve_role


def phases_for_role_title(title_ko: str) -> list[str]:
    from harness.role_registry import ROLE_BY_PHASE

    return [phase for phase, info in ROLE_BY_PHASE.items() if info["title_ko"] == title_ko]


def _load_trace_events(run_id: str) -> list[dict]:
    if not os.path.exists(CANONICAL_TRACE):
        return []
    events: list[dict] = []
    with open(CANONICAL_TRACE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get("run_id") == run_id:
                events.append(ev)
    return events


def _read_json(path: str) -> dict | None:
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            doc = json.load(f)
        return doc if isinstance(doc, dict) else None
    except (json.JSONDecodeError, OSError):
        return None


def _filter_by_phases(items: list[dict], phases: set[str]) -> list[dict]:
    return [item for item in items if item.get("phase") in phases]


def _match_ko_items(en_items: list[dict], ko_items: list[dict] | None) -> list[dict]:
    if not ko_items:
        return []
    out: list[dict] = []
    for i, item in enumerate(en_items):
        ko = ko_items[i] if i < len(ko_items) else {}
        if isinstance(ko, dict):
            out.append({**item, **{k: v for k, v in ko.items() if v is not None}})
        else:
            out.append(item)
    return out


def _qualitative_confidence_to_float(label: str) -> float:
    mapping = {"high": 0.9, "medium": 0.6, "low": 0.35, "unverified": 0.15}
    return mapping.get(str(label).lower(), 0.15)


def _extract_confidence(run_id: str, phases: set[str], run_root: str | None) -> list[dict]:
    scores: list[dict] = []

    for ev in _load_trace_events(run_id):
        if ev.get("phase") not in phases:
            continue
        details = ev.get("details") or {}
        event_type = ev.get("event_type", "")

        if event_type == "critique_generated" and details.get("confidence") is not None:
            scores.append({
                "source": "critique",
                "label": "비평 신뢰도",
                "value": details["confidence"],
                "timestamp": ev.get("timestamp"),
            })
        if event_type in ("council_approved", "council_rejected") and details.get("final_confidence") is not None:
            scores.append({
                "source": "council",
                "label": "Council 최종 신뢰도",
                "value": details["final_confidence"],
                "timestamp": ev.get("timestamp"),
            })
        if event_type == "intent_review_completed" and details.get("confidence") is not None:
            scores.append({
                "source": "intent_review",
                "label": "Intent 리뷰 신뢰도",
                "value": details["confidence"],
                "timestamp": ev.get("timestamp"),
            })
        if event_type == "decision_completed" and details.get("confidence") is not None:
            scores.append({
                "source": "decision",
                "label": "아키텍처 결정 신뢰도",
                "value": details["confidence"],
                "timestamp": ev.get("timestamp"),
            })
        if event_type == "product_qa_completed" and details.get("confidence") is not None:
            scores.append({
                "source": "product_qa",
                "label": "Product QA 종합 신뢰도",
                "value": details["confidence"],
                "timestamp": ev.get("timestamp"),
            })
        if event_type in ("user_model_generated", "problem_statement_created", "opportunity_scored"):
            if details.get("confidence") is not None:
                labels = {
                    "user_model_generated": "사용자 정의 신뢰도",
                    "problem_statement_created": "문제 발견 신뢰도",
                    "opportunity_scored": "기회 평가 신뢰도",
                }
                scores.append({
                    "source": event_type,
                    "label": labels.get(event_type, "신뢰도"),
                    "value": details["confidence"],
                    "timestamp": ev.get("timestamp"),
                })
        if event_type == "validation_passed" and details.get("confidence") is not None:
            scores.append({
                "source": "validation",
                "label": "검증 신뢰도",
                "value": details["confidence"],
                "timestamp": ev.get("timestamp"),
            })

    if run_root:
        if "IntentReview" in phases:
            review_doc = _read_json(os.path.join(run_root, "kernel", "founder_intent_review.json"))
            if review_doc:
                conf = (review_doc.get("review") or {}).get("confidence")
                if conf is not None and not any(s["source"] == "intent_review" for s in scores):
                    scores.append({
                        "source": "intent_review",
                        "label": "Intent 리뷰 신뢰도",
                        "value": conf,
                        "timestamp": None,
                    })

        if "DecisionCouncil" in phases:
            council_doc = _read_json(os.path.join(run_root, "decision", "council_decision.json"))
            if council_doc:
                conf = (council_doc.get("confidence") or {}).get("final_confidence")
                if conf is not None and not any(s["source"] == "council" for s in scores):
                    scores.append({
                        "source": "council",
                        "label": "Council 최종 신뢰도",
                        "value": conf,
                        "timestamp": None,
                    })

        if "Decision" in phases:
            meta_doc = _read_json(os.path.join(run_root, "docs", "decision_meta.json"))
            if meta_doc and meta_doc.get("confidence") is not None:
                if not any(s["source"] == "decision" for s in scores):
                    scores.append({
                        "source": "decision",
                        "label": "아키텍처 결정 신뢰도",
                        "value": meta_doc["confidence"],
                        "timestamp": None,
                    })

        if "OpportunitySizing" in phases:
            opp_doc = _read_json(os.path.join(run_root, "opportunity", "opportunity_model.json"))
            if opp_doc and opp_doc.get("confidence") is not None:
                if not any(s["source"] == "opportunity_scored" for s in scores):
                    scores.append({
                        "source": "opportunity_scored",
                        "label": "기회 평가 신뢰도",
                        "value": opp_doc["confidence"],
                        "timestamp": None,
                    })

        if "UserDefinition" in phases:
            user_doc = _read_json(os.path.join(run_root, "user", "user_model.json"))
            if user_doc and user_doc.get("confidence") is not None:
                if not any(s["source"] == "user_model_generated" for s in scores):
                    scores.append({
                        "source": "user_model_generated",
                        "label": "사용자 정의 신뢰도",
                        "value": user_doc["confidence"],
                        "timestamp": None,
                    })

        if "ProblemDiscovery" in phases:
            prob_doc = _read_json(os.path.join(run_root, "opportunity", "problem_statement.json"))
            if prob_doc and prob_doc.get("confidence") is not None:
                if not any(s["source"] == "problem_statement_created" for s in scores):
                    scores.append({
                        "source": "problem_statement_created",
                        "label": "문제 발견 신뢰도",
                        "value": prob_doc["confidence"],
                        "timestamp": None,
                    })

        if "PMReconstruction" in phases:
            brief_doc = _read_json(os.path.join(run_root, "discovery", "pm_brief.json"))
            if brief_doc and brief_doc.get("confidence") is not None:
                if not any(s["source"] == "pm_reconstruction_completed" for s in scores):
                    scores.append({
                        "source": "pm_reconstruction_completed",
                        "label": "PM 재구성 신뢰도",
                        "value": brief_doc["confidence"],
                        "timestamp": None,
                    })

        if "ProductQA" in phases:
            qa_doc = _read_json(os.path.join(run_root, "qa", "product_qa_result.json"))
            if qa_doc:
                conf = qa_doc.get("confidence")
                if conf is None:
                    conf = compute_product_qa_confidence(qa_doc)
                if not any(s["source"] == "product_qa" for s in scores):
                    scores.append({
                        "source": "product_qa",
                        "label": "Product QA 종합 신뢰도",
                        "value": conf,
                        "timestamp": None,
                    })

    return scores


def _load_product_qa_evidence(run_root: str | None) -> list[dict]:
    if not run_root:
        return []
    qa_doc = _read_json(os.path.join(run_root, "qa", "product_qa_result.json"))
    if not qa_doc:
        return []
    out: list[dict] = []
    for binding in qa_doc.get("evidence_bindings") or []:
        if not isinstance(binding, dict):
            continue
        qual = str(binding.get("confidence", "unverified"))
        out.append({
            "claim": binding.get("claim"),
            "source_ref": binding.get("source_ref"),
            "confidence_label": qual,
            "confidence_value": _qualitative_confidence_to_float(qual),
        })
    return out


def _latest_model(run_id: str, phases: set[str]) -> str | None:
    model: str | None = None
    for ev in reversed(_load_trace_events(run_id)):
        if ev.get("phase") not in phases:
            continue
        if ev.get("event_type") != "phase_start":
            continue
        details = ev.get("details") or {}
        if isinstance(details.get("model"), str):
            return details["model"]
    return model


def _phase_activity(run_id: str, phases: set[str]) -> list[dict]:
    activity: list[dict] = []
    for ev in _load_trace_events(run_id):
        if ev.get("phase") not in phases:
            continue
        if ev.get("event_type") not in ("phase_start", "phase_end", "run_start", "run_end"):
            continue
        activity.append({
            "event_type": ev.get("event_type"),
            "timestamp": ev.get("timestamp"),
            "status": (ev.get("details") or {}).get("status"),
        })
    return activity


def _load_idea_loop(run_id: str, run_root: str | None, phases: set[str]) -> dict | None:
    if "IdeaLoop" not in phases:
        return None
    doc = _read_json(os.path.join(run_root, "docs", "idea_meta.json")) if run_root else None
    if doc:
        return doc
    critiques = []
    for ev in _load_trace_events(run_id):
        if ev.get("phase") != "IdeaLoop":
            continue
        if ev.get("event_type") == "critique_generated":
            details = ev.get("details") or {}
            if details:
                critiques.append(details)
        if ev.get("event_type") == "idea_loop_completed":
            details = ev.get("details") or {}
            if details:
                return details
    if critiques:
        return {"critiques": critiques}
    return None


def _load_strategic_qa(run_root: str | None) -> dict | None:
    if not run_root:
        return None
    doc = _read_json(os.path.join(run_root, "qa", "strategic_qa_result.json"))
    if not doc:
        return None
    founder = doc.get("founder_preservation") or {}
    market = doc.get("market_viability") or {}
    checks = (founder.get("checks") or []) + (market.get("checks") or [])
    failed = [
        c for c in checks
        if isinstance(c, dict) and (not c.get("passed", True) or c.get("severity") in ("warn", "high"))
    ]
    return {
        "has_high_severity": doc.get("has_high_severity"),
        "founder_verdict": founder.get("overall_verdict"),
        "market_verdict": market.get("overall_verdict"),
        "founder_summary": founder.get("ko_summary"),
        "market_summary": market.get("ko_summary"),
        "failed_checks": failed,
        "all_checks": checks,
    }


def _load_validation_strategy(run_root: str | None) -> dict | None:
    if not run_root:
        return None
    doc = _read_json(os.path.join(run_root, "validation", "validation_strategy.json"))
    if not doc:
        return None
    return {
        "ko_summary": doc.get("ko_summary"),
        "hypotheses": doc.get("core_hypothesis") or [],
        "experiments": doc.get("next_experiments") or [],
        "counterfactuals": doc.get("counterfactuals") or [],
        "failure_modes": doc.get("failure_modes") or [],
    }


def _load_intent_review(run_root: str | None) -> dict | None:
    if not run_root:
        return None
    doc = _read_json(os.path.join(run_root, "kernel", "founder_intent_review.json"))
    if not doc:
        return None
    ko = _read_json(os.path.join(run_root, "kernel", "founder_intent_review_ko.json"))
    review = dict(doc.get("review") or {})
    if ko and isinstance(ko.get("review"), dict):
        for key, val in ko["review"].items():
            if val and not review.get(key):
                review[key] = val
    return {
        "verdict": review.get("verdict"),
        "confidence": review.get("confidence"),
        "user_analysis": review.get("user_analysis"),
        "problem_analysis": review.get("problem_analysis"),
        "opportunity_analysis": review.get("opportunity_analysis"),
        "coherence_analysis": review.get("coherence_analysis"),
        "ko_summary": review.get("ko_summary"),
        "problems": review.get("problems") or [],
        "structural_warnings": review.get("structural_warnings") or [],
    }


def build_agent_profile(run_id: str, phases: list[str], run_root: str | None) -> dict:
    phase_set = set(phases)
    primary = phases[0] if phases else "?"
    role = resolve_role(primary)

    agg = aggregate_decisions(run_id, run_root)
    selected = _filter_by_phases(agg["selected"], phase_set)
    rejected = _filter_by_phases(agg["rejected"], phase_set)
    tradeoffs = _filter_by_phases(agg["tradeoffs"], phase_set)
    snapshots = _filter_by_phases(agg["snapshots"], phase_set)
    events = _filter_by_phases(agg["events"], phase_set)

    ko_doc = ensure_decisions_korean_if_needed(run_id, run_root)
    selected_ko = _match_ko_items(selected, (ko_doc or {}).get("selected_ko"))
    rejected_ko = _match_ko_items(rejected, (ko_doc or {}).get("rejected_ko"))
    tradeoffs_ko = _match_ko_items(tradeoffs, (ko_doc or {}).get("tradeoffs_ko"))

    confidence = _extract_confidence(run_id, phase_set, run_root)
    primary_confidence = confidence[-1]["value"] if confidence else None

    payload: dict = {
        "run_id": run_id,
        "phases": phases,
        "role_title_ko": role["title_ko"],
        "role_title_en": role["title_en"],
        "model": _latest_model(run_id, phase_set),
        "confidence_scores": confidence,
        "primary_confidence": primary_confidence,
        "selected": selected_ko or selected,
        "rejected": rejected_ko or rejected,
        "tradeoffs": tradeoffs_ko or tradeoffs,
        "snapshots": snapshots,
        "events": events,
        "activity": _phase_activity(run_id, phase_set),
    }

    if "IntentReview" in phase_set:
        payload["intent_review"] = _load_intent_review(run_root)

    if "PMReconstruction" in phase_set:
        brief = _read_json(os.path.join(run_root, "discovery", "pm_brief.json")) if run_root else None
        if brief:
            payload["pm_brief"] = brief

    if "ProductQA" in phase_set:
        payload["evidence_bindings"] = _load_product_qa_evidence(run_root)

    if "IdeaLoop" in phase_set:
        payload["idea_loop"] = _load_idea_loop(run_id, run_root, phase_set)

    if "StrategicQA" in phase_set:
        payload["strategic_qa"] = _load_strategic_qa(run_root)

    if "ValidationEngine" in phase_set:
        payload["validation_strategy"] = _load_validation_strategy(run_root)

    return payload
