import { useEffect, useState } from "react";
import { api, type DecisionsDoc } from "../lib/api";
import { resolveRole } from "../lib/roles";
import type { RunPayload } from "../lib/types";

function koText(
  item: { id?: string; name?: string; rationale?: string; reason?: string; accepted?: string; sacrificed?: string },
  koList: { id?: string; name?: string; rationale?: string; reason?: string; accepted?: string; sacrificed?: string }[] | undefined,
  index: number,
  fields: ("name" | "rationale" | "reason" | "accepted" | "sacrificed")[],
): string {
  const ko = koList?.[index];
  if (!ko) {
    return fields.map((f) => item[f]).filter(Boolean).join(" — ");
  }
  return fields.map((f) => (ko[f] as string | undefined) ?? (item[f] as string | undefined)).filter(Boolean).join(" — ");
}

function phaseLabel(phase?: string): string {
  if (!phase) return "?";
  return resolveRole(phase).title_ko;
}

export function DecisionsPage({ run }: { run: RunPayload | null }) {
  const [doc, setDoc] = useState<DecisionsDoc | null>(null);
  const [error, setError] = useState<string | null>(null);

  const runId = run?.run_id ?? null;

  useEffect(() => {
    setDoc(null);
    setError(null);
    if (!runId) return;
    api.getDecisions(runId)
      .then(setDoc)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [runId, run?.status]);

  if (!runId) {
    return (
      <div className="page">
        <h2>Decisions</h2>
        <p className="lead">Run을 시작하면 의사결정 타임라인이 표시됩니다.</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="page">
        <h2>Decisions</h2>
        <p className="lead">{error}</p>
      </div>
    );
  }

  if (!doc) {
    return (
      <div className="page">
        <h2>Decisions</h2>
        <p className="lead">로딩 중…</p>
      </div>
    );
  }

  const hasKo = Boolean(doc.selected_ko?.length || doc.rejected_ko?.length || doc.tradeoffs_ko?.length);

  return (
    <div className="page">
      <h2>Decisions Timeline</h2>
      <p className="lead">
        run {doc.run_id.slice(0, 8)} · {doc.root} · {doc.events.length} events · {doc.snapshots.length} snapshots
        {hasKo ? " · 한국어 번역 적용" : " · 번역 대기 중"}
      </p>

      {doc.selected.length > 0 && (
        <>
          <h3 style={{ margin: "16px 0 8px", fontSize: 15 }}>선택됨 ({doc.selected.length})</h3>
          <div className="problem-list">
            {doc.selected.map((item, i) => (
              <div className="problem-row" key={`s-${i}`}>
                <span className="pill pass">{phaseLabel(item.phase)}</span>
                <span className="problem-issue">
                  {koText(item, doc.selected_ko, i, ["name", "rationale"])}
                </span>
              </div>
            ))}
          </div>
        </>
      )}

      {doc.rejected.length > 0 && (
        <>
          <h3 style={{ margin: "20px 0 8px", fontSize: 15 }}>기각됨 ({doc.rejected.length})</h3>
          <div className="problem-list">
            {doc.rejected.map((item, i) => (
              <div className="problem-row high" key={`r-${i}`}>
                <span className="pill fail">{phaseLabel(item.phase)}</span>
                <span className="problem-issue">
                  {koText(item, doc.rejected_ko, i, ["name", "reason"])}
                </span>
                {item.conflicts_with && (
                  <code className="problem-ref">{item.conflicts_with}</code>
                )}
              </div>
            ))}
          </div>
        </>
      )}

      {doc.tradeoffs.length > 0 && (
        <>
          <h3 style={{ margin: "20px 0 8px", fontSize: 15 }}>트레이드오프 ({doc.tradeoffs.length})</h3>
          <div className="problem-list">
            {doc.tradeoffs.map((item, i) => (
              <div className="problem-row medium" key={`t-${i}`}>
                <span className="pill warn">{phaseLabel(item.phase)}</span>
                <span className="problem-issue">
                  {koText(item, doc.tradeoffs_ko, i, ["accepted", "sacrificed", "reason"])}
                </span>
              </div>
            ))}
          </div>
        </>
      )}

      {doc.selected.length === 0 && doc.rejected.length === 0 && doc.tradeoffs.length === 0 && (
        <p className="lead">아직 decision_graph 데이터가 없습니다. Decision/Council phase 실행 후 표시됩니다.</p>
      )}
    </div>
  );
}
