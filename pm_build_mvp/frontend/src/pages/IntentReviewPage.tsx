import { useEffect, useState } from "react";
import { api, type IntentReviewDoc } from "../lib/api";
import { resolveRole } from "../lib/roles";
import type { RunPayload } from "../lib/types";

const VERDICT_LABEL: Record<string, { label: string; cls: string }> = {
  proceed_recommended: { label: "진행 권고", cls: "pass" },
  proceed_with_concerns: { label: "주의하며 진행", cls: "warn" },
  reject_recommended: { label: "중단 권고", cls: "fail" },
};

const ANALYSIS_SECTIONS: { key: keyof IntentReviewDoc["review"]; label: string }[] = [
  { key: "user_analysis", label: "사용자" },
  { key: "problem_analysis", label: "문제" },
  { key: "opportunity_analysis", label: "기회" },
  { key: "coherence_analysis", label: "일관성" },
];

const AREA_LABEL: Record<string, string> = {
  user: "사용자",
  problem: "문제",
  opportunity: "기회",
  coherence: "일관성",
};

function pickReview(doc: IntentReviewDoc) {
  if (doc.translation_status === "ok") return doc.review;
  const ko = doc.review_ko;
  if (!ko) return doc.review;
  return {
    ...doc.review,
    user_analysis: ko.user_analysis ?? doc.review.user_analysis,
    problem_analysis: ko.problem_analysis ?? doc.review.problem_analysis,
    opportunity_analysis: ko.opportunity_analysis ?? doc.review.opportunity_analysis,
    coherence_analysis: ko.coherence_analysis ?? doc.review.coherence_analysis,
    ko_summary: ko.ko_summary ?? doc.review.ko_summary,
    problems: (doc.review.problems ?? []).map((p, i) => ({
      ...p,
      issue: ko.problems?.[i]?.issue ?? p.issue,
    })),
    structural_warnings: (doc.review.structural_warnings ?? []).map((p, i) => ({
      ...p,
      issue: ko.structural_warnings?.[i]?.issue ?? p.issue,
    })),
  };
}

export function IntentReviewPage({
  run,
  onRunUpdate,
}: {
  run: RunPayload | null;
  onRunUpdate: (r: RunPayload) => void;
}) {
  const [doc, setDoc] = useState<IntentReviewDoc | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [kernelText, setKernelText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState<string | null>(null);

  const runId = run?.run_id ?? null;
  const awaiting = run?.status === "awaiting_choice";

  useEffect(() => {
    setDoc(null);
    setError(null);
    setSubmitted(null);
    setEditing(false);
    if (!runId) return;
    api.getIntentReview(runId)
      .then((d) => {
        setDoc(d);
        setKernelText(JSON.stringify(d.kernel, null, 2));
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [runId, run?.status]);

  const submit = async (choice: "proceed" | "reject" | "edit") => {
    if (!runId) return;
    setSubmitting(true);
    setError(null);
    try {
      let kernel: Record<string, string[]> | undefined;
      if (choice === "edit") {
        kernel = JSON.parse(kernelText);
      }
      await api.postIntentChoice(runId, { choice, kernel, reason: "founder choice via UI" });
      setSubmitted(choice);
      setEditing(false);
      const updated = await api.getRun(runId);
      onRunUpdate(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  };

  if (!runId) {
    return (
      <div className="page">
        <h2>Intent Review</h2>
        <p className="lead">Run을 시작하면 Layer 0.5 Founder Intent Review 결과가 여기에 표시됩니다.</p>
      </div>
    );
  }

  if (!doc) {
    return (
      <div className="page">
        <h2>Intent Review</h2>
        <p className="lead">
          {error
            ? `리뷰를 불러올 수 없습니다: ${error}`
            : "리뷰 생성·번역 대기 중… (gate가 아직 실행되지 않았거나 skip 상태)"}
        </p>
      </div>
    );
  }

  const review = pickReview(doc);
  const verdict = VERDICT_LABEL[review.verdict ?? ""] ?? { label: review.verdict ?? "?", cls: "info" };
  const problems = [...(review.structural_warnings ?? []), ...(review.problems ?? [])];

  return (
    <div className="page">
      <h2>Founder Intent Review</h2>
      <p className="lead">
        {resolveRole("IntentReview").title_ko} · run {doc.run_id.slice(0, 8)} · mode: {doc.mode}
        {doc.translation_status === "ok" ? " · 한국어 번역 적용" : " · 번역 대기 중"}
      </p>

      <div className={`verdict-banner ${verdict.cls}`}>
        <div className="verdict-label">{verdict.label}</div>
        {review.confidence != null && (
          <div className="verdict-confidence">confidence {review.confidence}</div>
        )}
        {review.ko_summary && <div className="verdict-summary">{review.ko_summary}</div>}
      </div>

      <div className="review-grid">
        {ANALYSIS_SECTIONS.map(({ key, label }) => {
          const text = review[key];
          if (typeof text !== "string" || !text) return null;
          return (
            <div className="review-card" key={key}>
              <div className="review-card-title">{label}</div>
              <div className="review-card-body">{text}</div>
            </div>
          );
        })}
      </div>

      {problems.length > 0 && (
        <>
          <h3 style={{ margin: "20px 0 8px", fontSize: 15 }}>지적 사항 ({problems.length})</h3>
          <div className="problem-list">
            {problems.map((p, i) => (
              <div className={`problem-row ${p.severity}`} key={i}>
                <span className={`pill sev-${p.severity}`}>{p.severity}</span>
                <span className="pill">{AREA_LABEL[p.area] ?? p.area}</span>
                <span className="problem-issue">{p.issue}</span>
                {p.kernel_ref && <code className="problem-ref">{p.kernel_ref}</code>}
              </div>
            ))}
          </div>
        </>
      )}

      {awaiting && !submitted && (
        <div className="choice-panel">
          <div className="choice-title">Founder Decision</div>
          <p className="lead" style={{ marginBottom: 12 }}>
            이 리뷰를 읽고 결정하세요. 파이프라인은 결정 전까지 일시정지 상태입니다
            (timeout 시 reject 처리).
          </p>
          {editing && (
            <textarea
              className="kernel-editor"
              value={kernelText}
              onChange={(e) => setKernelText(e.target.value)}
              rows={14}
              spellCheck={false}
            />
          )}
          <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
            {!editing ? (
              <>
                <button className="btn primary" disabled={submitting} onClick={() => submit("proceed")}>
                  Proceed — 그래도 진행
                </button>
                <button className="btn" disabled={submitting} onClick={() => setEditing(true)}>
                  Edit Kernel — 수정 후 진행
                </button>
                <button className="btn danger" disabled={submitting} onClick={() => submit("reject")}>
                  Reject — 중단
                </button>
              </>
            ) : (
              <>
                <button className="btn primary" disabled={submitting} onClick={() => submit("edit")}>
                  Save Kernel &amp; Proceed
                </button>
                <button className="btn" disabled={submitting} onClick={() => setEditing(false)}>
                  Cancel
                </button>
              </>
            )}
          </div>
        </div>
      )}

      {submitted && (
        <div className="choice-panel">
          <div className="choice-title">결정 완료: {submitted}</div>
          <p className="lead">
            {submitted === "reject"
              ? "파이프라인이 중단되고 partial archive가 생성됩니다."
              : "파이프라인이 계속 진행됩니다. Live Feed에서 확인하세요."}
          </p>
        </div>
      )}

      {error && <div className="error-banner" style={{ margin: "14px 0 0" }}>{error}</div>}
    </div>
  );
}
