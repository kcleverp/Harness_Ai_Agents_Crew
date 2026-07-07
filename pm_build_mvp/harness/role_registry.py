"""Phase → display role title mapping (KO/EN). Token-free UI labels."""

from __future__ import annotations

ROLE_BY_PHASE: dict[str, dict[str, str]] = {
    "IntentReview": {"title_ko": "프리시드 리뷰어", "title_en": "Pre-seed Reviewer"},
    "PMReconstruction": {"title_ko": "PM 재구성", "title_en": "PM Reconstruction"},
    "IdeaLoop": {"title_ko": "아이디어 생성기", "title_en": "Idea Generator"},
    "Synthesis": {"title_ko": "블루프린트 구조화", "title_en": "Blueprint Structurer"},
    "Decision": {"title_ko": "수석 아키텍트", "title_en": "Chief Architect"},
    "CreativeProd": {"title_ko": "크리에이티브 프로듀서", "title_en": "Creative Producer"},
    "TechnicalProd": {"title_ko": "기술 명세 작성", "title_en": "Technical Spec Writer"},
    "ProductQA": {"title_ko": "QA 검증", "title_en": "QA Validator"},
    "StrategicQA": {"title_ko": "전략 QA", "title_en": "Strategic QA"},
    "DecisionCouncil": {"title_ko": "MVP 심의위원회", "title_en": "MVP Council"},
    "UserDefinition": {"title_ko": "사용자 정의", "title_en": "User Definition"},
    "ProblemDiscovery": {"title_ko": "문제 발견", "title_en": "Problem Discovery"},
    "OpportunitySizing": {"title_ko": "기회 평가", "title_en": "Opportunity Sizing"},
    "Translation": {"title_ko": "문서 번역기", "title_en": "Document Translator"},
    "Workflow": {"title_ko": "Orchestrator", "title_en": "Orchestrator"},
    "summary": {"title_ko": "Orchestrator", "title_en": "Orchestrator"},
    "validation": {"title_ko": "QA 검증", "title_en": "QA Validator"},
    "ValidationEngine": {"title_ko": "검증 전략", "title_en": "Validation Strategy"},
    "ConsistencyGuardrail": {"title_ko": "일관성 검사", "title_en": "Consistency Guard"},
}


def resolve_role(phase: str) -> dict[str, str]:
    """Return {title_ko, title_en} for a telemetry phase string."""
    if phase in ROLE_BY_PHASE:
        return ROLE_BY_PHASE[phase]
    return {"title_ko": phase, "title_en": phase}
