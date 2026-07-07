/** Phase → display role title (mirrors harness/role_registry.py). */

export interface RoleInfo {
  title_ko: string;
  title_en: string;
}

const ROLE_BY_PHASE: Record<string, RoleInfo> = {
  IntentReview: { title_ko: "프리시드 리뷰어", title_en: "Pre-seed Reviewer" },
  PMReconstruction: { title_ko: "PM 재구성", title_en: "PM Reconstruction" },
  IdeaLoop: { title_ko: "아이디어 생성기", title_en: "Idea Generator" },
  Synthesis: { title_ko: "블루프린트 구조화", title_en: "Blueprint Structurer" },
  Decision: { title_ko: "수석 아키텍트", title_en: "Chief Architect" },
  CreativeProd: { title_ko: "크리에이티브 프로듀서", title_en: "Creative Producer" },
  TechnicalProd: { title_ko: "기술 명세 작성", title_en: "Technical Spec Writer" },
  ProductQA: { title_ko: "QA 검증", title_en: "QA Validator" },
  StrategicQA: { title_ko: "전략 QA", title_en: "Strategic QA" },
  DecisionCouncil: { title_ko: "MVP 심의위원회", title_en: "MVP Council" },
  UserDefinition: { title_ko: "사용자 정의", title_en: "User Definition" },
  ProblemDiscovery: { title_ko: "문제 발견", title_en: "Problem Discovery" },
  OpportunitySizing: { title_ko: "기회 평가", title_en: "Opportunity Sizing" },
  Translation: { title_ko: "문서 번역기", title_en: "Document Translator" },
  Workflow: { title_ko: "Orchestrator", title_en: "Orchestrator" },
  summary: { title_ko: "Orchestrator", title_en: "Orchestrator" },
    "ValidationEngine": { title_ko: "검증 전략", title_en: "Validation Strategy" },
    "ConsistencyGuardrail": { title_ko: "일관성 검사", title_en: "Consistency Guard" },
    validation: { title_ko: "QA 검증", title_en: "QA Validator" },
};

export function resolveRole(phase: string): RoleInfo {
  return ROLE_BY_PHASE[phase] ?? { title_ko: phase, title_en: phase };
}

export function shortModel(model: string): string {
  return model.split(",")[0].split("/").pop() ?? model;
}

export function phasesForRoleTitle(titleKo: string): string[] {
  return Object.entries(ROLE_BY_PHASE)
    .filter(([, v]) => v.title_ko === titleKo)
    .map(([k]) => k);
}

export function agentLabel(phase: string, details?: Record<string, unknown>): string {
  const role = typeof details?.role === "string" && details.role
    ? details.role
    : resolveRole(phase).title_ko;
  const model = details?.model;
  if (typeof model === "string" && model) {
    return `${role} · ${shortModel(model)}`;
  }
  if (phase === "Workflow" || phase === "summary") return "Orchestrator";
  return role;
}
