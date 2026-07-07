import { useEffect, useState } from "react";
import { api, type AgentProfileDoc } from "../lib/api";
import { shortModel } from "../lib/roles";

function confidencePct(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return `${Math.round(value * 100)}%`;
}

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.max(0, Math.min(100, Math.round(value * 100)));
  const tone = pct >= 70 ? "pass" : pct >= 40 ? "warn" : "fail";
  return (
    <div className="conf-bar">
      <div className="conf-bar-track">
        <div className={`conf-bar-fill ${tone}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="conf-bar-label">{pct}%</span>
    </div>
  );
}

function DecisionList({
  title,
  items,
  tone,
}: {
  title: string;
  items: { id?: string; name?: string; rationale?: string; reason?: string; accepted?: string; sacrificed?: string }[];
  tone: "pass" | "fail" | "warn";
}) {
  if (items.length === 0) return null;
  return (
    <div className="profile-section">
      <div className="profile-section-title">{title}</div>
      <div className="problem-list">
        {items.map((item, i) => {
          const label = item.name || item.id || item.accepted || `#${i + 1}`;
          const rationale = item.rationale || item.reason || item.sacrificed || "";
          return (
            <div key={`${label}-${i}`} className={`problem-row ${tone === "fail" ? "high" : tone === "warn" ? "medium" : "low"}`}>
              <div>
                <div className="profile-item-title">{label}</div>
                {rationale && <div className="profile-item-body">{rationale}</div>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function AgentProfilePanel({
  runId,
  phase,
  roleTitle,
  onClose,
}: {
  runId: string;
  phase?: string;
  roleTitle?: string;
  onClose: () => void;
}) {
  const [doc, setDoc] = useState<AgentProfileDoc | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    setError(null);
    setDoc(null);
    const opts = phase ? { phase } : roleTitle ? { role: roleTitle } : {};
    api.getAgentProfile(runId, opts)
      .then(setDoc)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [runId, phase, roleTitle]);

  const title = doc?.role_title_ko ?? roleTitle ?? phase ?? "Agent";

  const hasDecisions = doc && (doc.selected.length > 0 || doc.rejected.length > 0 || doc.tradeoffs.length > 0);
  const hasExtra = doc && (
    doc.intent_review || doc.idea_loop || doc.strategic_qa || doc.validation_strategy
    || (doc.evidence_bindings && doc.evidence_bindings.length > 0)
  );
  const showEmpty = doc && !hasDecisions && !hasExtra;

  return (
    <aside className="agent-panel">
      <div className="agent-panel-header">
        <div>
          <div className="agent-panel-title">{title}</div>
          {doc?.model && (
            <div className="agent-panel-sub">{shortModel(doc.model)}</div>
          )}
        </div>
        <button type="button" className="btn agent-panel-close" onClick={onClose} aria-label="Close">
          ✕
        </button>
      </div>

      <div className="agent-panel-body">
        {loading && <div className="agent-panel-empty">로딩 중…</div>}
        {error && <div className="agent-panel-empty">{error}</div>}
        {!loading && !error && doc && (
          <>
            {doc.primary_confidence != null && (
              <div className="profile-section">
                <div className="profile-section-title">신뢰 점수</div>
                <ConfidenceBar value={doc.primary_confidence} />
                {doc.confidence_scores.length > 1 && (
                  <div className="conf-list">
                    {doc.confidence_scores.map((s, i) => (
                      <div key={i} className="conf-row">
                        <span>{s.label}</span>
                        <span className="conf-value">{confidencePct(s.value)}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {doc.intent_review && (
              <div className="profile-section">
                <div className="profile-section-title">Intent 리뷰</div>
                {doc.intent_review.verdict && (
                  <div className={`verdict-banner ${doc.intent_review.verdict === "proceed" ? "pass" : "warn"}`}>
                    <div className="verdict-label">{doc.intent_review.verdict.toUpperCase()}</div>
                    {doc.intent_review.confidence != null && (
                      <div className="verdict-confidence">confidence {confidencePct(doc.intent_review.confidence)}</div>
                    )}
                    {doc.intent_review.ko_summary && (
                      <div className="verdict-summary">{doc.intent_review.ko_summary}</div>
                    )}
                  </div>
                )}
                <div className="review-grid">
                  {(["user_analysis", "problem_analysis", "opportunity_analysis", "coherence_analysis"] as const).map((key) => {
                    const val = doc.intent_review?.[key];
                    if (!val) return null;
                    const labels: Record<string, string> = {
                      user_analysis: "사용자",
                      problem_analysis: "문제",
                      opportunity_analysis: "기회",
                      coherence_analysis: "일관성",
                    };
                    return (
                      <div key={key} className="review-card">
                        <div className="review-card-title">{labels[key]}</div>
                        <div className="review-card-body">{val}</div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            <DecisionList title={`선택됨 (${doc.selected.length})`} items={doc.selected} tone="pass" />
            <DecisionList title={`기각됨 (${doc.rejected.length})`} items={doc.rejected} tone="fail" />
            <DecisionList title={`트레이드오프 (${doc.tradeoffs.length})`} items={doc.tradeoffs} tone="warn" />

            {doc.idea_loop && (
              <div className="profile-section">
                <div className="profile-section-title">생성된 아이디어</div>
                {doc.idea_loop.selected_core && (
                  <div className="profile-item-body" style={{ marginBottom: 8 }}>{doc.idea_loop.selected_core}</div>
                )}
                {doc.idea_loop.ko_summary && <div className="verdict-summary">{doc.idea_loop.ko_summary}</div>}
                {(doc.idea_loop.rejected_features ?? []).length > 0 && (
                  <>
                    <div className="profile-section-title" style={{ marginTop: 10 }}>기각 ({doc.idea_loop.rejected_features!.length})</div>
                    <ul className="doc-tag-list fail">
                      {doc.idea_loop.rejected_features!.map((x, i) => <li key={i}>{x}</li>)}
                    </ul>
                  </>
                )}
                {(doc.idea_loop.critiques ?? []).map((c, i) => (
                  <div key={i} className="problem-row medium" style={{ marginTop: 8 }}>
                    <div className="profile-item-title">{c.persona ?? "critique"} · {c.confidence != null ? `${Math.round(c.confidence * 100)}%` : ""}</div>
                    <div className="profile-item-body">{c.risk}</div>
                    {(c.confidence_basis ?? []).map((b, j) => (
                      <div key={j} className="profile-item-body" style={{ fontSize: 11.5, opacity: 0.85 }}>· {b}</div>
                    ))}
                    {c.suggested_fix && <div className="profile-item-body" style={{ fontStyle: "italic" }}>→ {c.suggested_fix}</div>}
                  </div>
                ))}
              </div>
            )}

            {doc.strategic_qa && (
              <div className="profile-section">
                <div className="profile-section-title">전략 QA 결과</div>
                <div className="conf-row">
                  <span>Founder</span><span>{doc.strategic_qa.founder_verdict ?? "—"}</span>
                </div>
                <div className="conf-row">
                  <span>Market</span><span>{doc.strategic_qa.market_verdict ?? "—"}</span>
                </div>
                {(doc.strategic_qa.failed_checks ?? []).map((c, i) => (
                  <div key={i} className="problem-row high">
                    <div className="profile-item-title">{c.check_type} · {c.severity}</div>
                    <div className="profile-item-body">{c.finding}</div>
                  </div>
                ))}
                {(doc.strategic_qa.failed_checks ?? []).length === 0 && (
                  <div className="profile-item-body">이슈 없음</div>
                )}
              </div>
            )}

            {doc.validation_strategy && (
              <div className="profile-section">
                <div className="profile-section-title">검증 전략</div>
                {doc.validation_strategy.ko_summary && (
                  <div className="verdict-summary">{doc.validation_strategy.ko_summary}</div>
                )}
                {(doc.validation_strategy.hypotheses ?? []).map((h, i) => (
                  <div key={i} className="problem-row low">
                    <div className="profile-item-title">{h.id}</div>
                    <div className="profile-item-body">{h.statement}</div>
                    {h.kpi && <div className="profile-item-body" style={{ fontSize: 11.5 }}>KPI: {h.kpi}</div>}
                  </div>
                ))}
                {(doc.validation_strategy.experiments ?? []).length > 0 && (
                  <>
                    <div className="profile-section-title" style={{ marginTop: 10 }}>다음 실험</div>
                    <ul className="doc-tag-list">
                      {doc.validation_strategy.experiments!.map((x, i) => <li key={i}>{x}</li>)}
                    </ul>
                  </>
                )}
              </div>
            )}

            {showEmpty && (
              <div className="agent-panel-empty">
                이 역할의 의사결정 기록이 아직 없습니다.
                {doc.activity.length > 0 && (
                  <div className="profile-activity">
                    {doc.activity.map((a, i) => (
                      <div key={i} className="profile-activity-row">
                        <span>{a.event_type}</span>
                        <span className="msg-time">{a.timestamp?.split("T")[1] ?? ""}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {doc.snapshots.length > 0 && (
              <div className="profile-section">
                <div className="profile-section-title">스냅샷 ({doc.snapshots.length})</div>
                {doc.snapshots.map((s, i) => (
                  <div key={i} className="profile-snapshot">
                    <code className="inline">{s.artifact}</code>
                  </div>
                ))}
              </div>
            )}

            {doc.evidence_bindings && doc.evidence_bindings.length > 0 && (
              <div className="profile-section">
                <div className="profile-section-title">근거 바인딩 ({doc.evidence_bindings.length})</div>
                <div className="evidence-list">
                  {doc.evidence_bindings.map((e, i) => (
                    <div key={i} className="evidence-row">
                      <div className="evidence-claim">{e.claim}</div>
                      <div className="evidence-meta">
                        <code className="inline">{e.source_ref ?? ""}</code>
                        <span className="pill">{e.confidence_label}</span>
                        {e.confidence_value != null && (
                          <span className="conf-value">{Math.round(e.confidence_value * 100)}%</span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </aside>
  );
}
