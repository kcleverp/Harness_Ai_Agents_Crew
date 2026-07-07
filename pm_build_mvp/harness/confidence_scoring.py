"""Normalize and compute phase confidence scores (0.0–1.0)."""
from __future__ import annotations

_SEVERITY_WEIGHT = {"high": 0.15, "medium": 0.08, "low": 0.03}
_EVIDENCE_QUAL = {"high": 0.9, "medium": 0.6, "low": 0.35, "unverified": 0.15}


def _clamp(value: float, lo: float = 0.1, hi: float = 0.98) -> float:
    return round(max(lo, min(hi, value)), 2)


def compute_intent_confidence(review: dict) -> float:
    """Certainty in the verdict — aligned with founder_intent_review.md rubric."""
    verdict = review.get("verdict", "proceed_with_concerns")
    problems = review.get("problems") or []
    warnings = review.get("structural_warnings") or []
    high = sum(1 for p in problems if p.get("severity") == "high")
    medium = sum(1 for p in problems if p.get("severity") == "medium")
    low = sum(1 for p in problems if p.get("severity") == "low")

    if verdict == "reject_recommended":
        base = 0.65 + min(0.30, high * 0.10 + medium * 0.05)
    elif verdict == "proceed_recommended":
        base = 0.85 - high * 0.20 - medium * 0.10 - low * 0.03
    else:
        base = 0.60 - high * 0.08 + min(0.12, medium * 0.03)

    for item in warnings:
        base -= _SEVERITY_WEIGHT.get(item.get("severity", "low"), 0.03)

    for field in ("user_analysis", "problem_analysis", "opportunity_analysis", "coherence_analysis"):
        if not (review.get(field) or "").strip():
            base -= 0.10

    return _clamp(base)


def normalize_intent_confidence(review: dict) -> float:
    computed = compute_intent_confidence(review)
    llm_val = review.get("confidence")
    if isinstance(llm_val, (int, float)):
        blended = (computed + float(llm_val)) / 2
        if abs(float(llm_val) - computed) > 0.25:
            return _clamp(computed * 0.7 + float(llm_val) * 0.3)
        return _clamp(blended)
    return computed


def compute_user_definition_confidence(doc: dict) -> float:
    persona = doc.get("persona") if isinstance(doc.get("persona"), dict) else {}
    personas = doc.get("personas") or []
    jtbd = doc.get("jtbd") or []
    base = 0.40
    if persona.get("name") and persona.get("job_to_be_done"):
        base += 0.25
    elif personas:
        base += 0.12
    if persona.get("current_solution") and persona.get("success_metric"):
        base += 0.12
    if doc.get("icp"):
        base += 0.08
    if len(jtbd) >= 1:
        base += 0.08
    ko = (doc.get("ko_summary") or "").lower()
    if any(w in ko for w in ("assumption", "thin", "가정", "부족")):
        base -= 0.12
    return merge_confidence(base, doc.get("confidence"))


def compute_problem_discovery_confidence(doc: dict) -> float:
    pains = doc.get("pain_points") or []
    base = 0.40 + min(0.25, len(pains) * 0.07)
    base += sum(0.05 for p in pains if p.get("severity") == "high")
    if (doc.get("problem_statement") or "").strip():
        base += 0.15
    ps = str(doc.get("problem_statement") or "").lower()
    if "because" in ps:
        base += 0.08
    with_evidence = sum(1 for p in pains if (p.get("evidence") or "").strip())
    base += min(0.10, with_evidence * 0.04)
    return merge_confidence(base, doc.get("confidence"))


def compute_opportunity_confidence(doc: dict) -> float:
    if doc.get("opportunity_score") is not None:
        base = float(doc["opportunity_score"]) / 10.0
    else:
        dims = ("impact", "reach", "revenue", "retention", "cost", "risk")
        scores = []
        for dim in dims:
            block = doc.get(dim)
            if isinstance(block, dict) and isinstance(block.get("score"), (int, float)):
                scores.append(float(block["score"]) / 10.0)
        base = sum(scores) / len(scores) if scores else 0.5
    return merge_confidence(base, doc.get("confidence"))


def compute_decision_confidence(meta: dict, graph: dict | None = None) -> float:
    base = 0.55
    if meta.get("selected_decisions"):
        base += 0.10
    rejected = meta.get("rejected_options") or []
    if len(rejected) >= 2:
        base += 0.10
    if meta.get("reasons"):
        base += 0.10
    if meta.get("trade_offs"):
        base += 0.05
    graph = graph or {}
    selected = graph.get("selected") or []
    if selected and all(isinstance(s, dict) and s.get("rationale") for s in selected):
        base += 0.10
    llm_val = meta.get("confidence")
    if isinstance(llm_val, (int, float)):
        return _clamp((base + float(llm_val)) / 2)
    return _clamp(base)


def compute_product_qa_confidence(result: dict) -> float:
    bindings = result.get("evidence_bindings") or []
    qa_results = result.get("qa_results") or []
    if bindings:
        vals = [_EVIDENCE_QUAL.get(str(b.get("confidence", "unverified")).lower(), 0.15) for b in bindings]
        evidence_avg = sum(vals) / len(vals)
    else:
        evidence_avg = 0.5
    if qa_results:
        pass_rate = sum(1 for q in qa_results if q.get("passed")) / len(qa_results)
    else:
        overall = result.get("overall_status", "pass")
        pass_rate = 1.0 if overall == "pass" else 0.5 if overall == "warn" else 0.0
    return _clamp(evidence_avg * 0.65 + pass_rate * 0.35)


def merge_confidence(computed: float, llm_val: object) -> float:
    if isinstance(llm_val, (int, float)):
        return _clamp((computed + float(llm_val)) / 2)
    return _clamp(computed)
