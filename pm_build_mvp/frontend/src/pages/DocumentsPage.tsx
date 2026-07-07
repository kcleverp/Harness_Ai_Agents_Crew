import { useEffect, useState } from "react";
import { Markdown } from "../components/Markdown";
import { api, type DocumentSection, type RunDocuments } from "../lib/api";
import type { RunPayload } from "../lib/types";

export const KIND_CLUSTER: Record<string, string> = {
  persona: "DISCOVERY",
  problem: "DISCOVERY",
  opportunity: "DISCOVERY",
  markdown: "SUMMARY",
  checkpoint: "CONCEPT",
  idea: "CONCEPT",
  council: "DECISION",
  backlog: "EXECUTION",
  qa: "VALIDATION",
  strategic_qa: "VALIDATION",
  validation: "VALIDATION",
};

const HIGHLIGHT_KINDS = new Set(["persona", "opportunity", "idea"]);
const ALERT_KINDS = new Set(["problem", "strategic_qa"]);

function sectionAccent(kind: string): string {
  if (ALERT_KINDS.has(kind)) return "paper-exhibit--alert";
  if (HIGHLIGHT_KINDS.has(kind)) return "paper-exhibit--highlight";
  return "";
}

function KoInterpretation({ text, label = "해석" }: { text?: unknown; label?: string }) {
  const value = typeof text === "string" ? text.trim() : "";
  if (!value) return null;
  return (
    <div className="paper-ko-interp">
      <div className="paper-ko-interp-label">{label}</div>
      <p>{value}</p>
    </div>
  );
}

function KoInterpretationList({ items }: { items?: { label?: string; text?: string }[] }) {
  if (!items?.length) return null;
  return (
    <>
      {items.map((item, i) => (
        <KoInterpretation key={i} label={item.label ?? "해석"} text={item.text} />
      ))}
    </>
  );
}

function SectionBody({ section }: { section: DocumentSection }) {
  const body = section.body as Record<string, unknown>;

  switch (section.kind) {
    case "markdown":
      return (
        <div className="paper-prose">
          <Markdown source={String(section.body ?? "")} />
        </div>
      );
    case "persona": {
      const p = body;
      return (
        <div className="paper-prose">
          <KoInterpretation text={p.ko_summary} />
          <p className="paper-lead paper-lead--accent">
            {[p.name, p.role, p.environment].filter(Boolean).join(" · ")}
          </p>
          {p.job_to_be_done ? <p><strong>JTBD</strong> — {String(p.job_to_be_done)}</p> : null}
          {p.current_solution ? <p><strong>현재 도구</strong> — {String(p.current_solution)}</p> : null}
          {p.biggest_pain ? <p><strong>핵심 고통</strong> — {String(p.biggest_pain)}</p> : null}
          {p.success_metric ? <p><strong>성공 기준</strong> — {String(p.success_metric)}</p> : null}
        </div>
      );
    }
    case "problem": {
      const pains = (body.pain_points as { description?: string; severity?: string; evidence?: string }[]) ?? [];
      return (
        <div className="paper-prose">
          <KoInterpretation text={body.ko_summary} />
          {body.problem_statement ? <p className="paper-lead">{String(body.problem_statement)}</p> : null}
          {pains.length > 0 && (
            <>
              <h4>Pain Points</h4>
              {pains.map((pp, i) => (
                <blockquote key={i} className={`paper-callout ${pp.severity === "high" ? "paper-callout--alert" : ""}`}>
                  <div className="paper-callout-tag">{pp.severity ?? "?"}</div>
                  <p>{pp.description}</p>
                  {pp.evidence ? <p className="paper-meta">{pp.evidence}</p> : null}
                </blockquote>
              ))}
            </>
          )}
        </div>
      );
    }
    case "opportunity":
      return (
        <div className="paper-prose">
          <KoInterpretation text={body.ko_summary} />
          <p className="paper-score">
            score {String(body.opportunity_score ?? "—")} · {String(body.recommended_direction ?? "")}
          </p>
          <p>
            market={String(body.market_size ?? "—")} · competition={String(body.competition ?? "—")} ·
            switching={String(body.switching_cost ?? "—")}
          </p>
          {body.rationale ? <p>{String(body.rationale)}</p> : null}
        </div>
      );
    case "checkpoint":
      return (
        <div className="paper-prose">
          <KoInterpretation text={body.ko_summary} />
          <div className="paper-grid-2">
            <div className="paper-field">
              <span className="paper-field-label">문제</span>
              <p>{String(body.problem ?? "")}</p>
            </div>
            <div className="paper-field">
              <span className="paper-field-label">타겟</span>
              <p>{String(body.target_user ?? "")}</p>
            </div>
          </div>
          <div className="paper-field">
            <span className="paper-field-label">핵심 가치</span>
            <p>{String(body.core_value ?? "")}</p>
          </div>
          <h4>MVP 필수</h4>
          <ul>{((body.must_have_mvp as string[]) ?? []).map((x, i) => <li key={i}>{x}</li>)}</ul>
          <h4>제외</h4>
          <ul>{((body.excluded_features as string[]) ?? []).map((x, i) => <li key={i}>{x}</li>)}</ul>
        </div>
      );
    case "idea": {
      const critiques = (body.critiques as { persona?: string; risk?: string; confidence_basis?: string[]; suggested_fix?: string }[]) ?? [];
      return (
        <div className="paper-prose">
          <KoInterpretation text={body.ko_summary} />
          {body.selected_core ? (
            <p className="paper-lead paper-lead--accent"><strong>선택된 핵심</strong> — {String(body.selected_core)}</p>
          ) : null}
          {((body.rejected_features as string[]) ?? []).length > 0 && (
            <>
              <h4>기각된 아이디어</h4>
              <ul>{((body.rejected_features as string[]) ?? []).map((x, i) => <li key={i}>{x}</li>)}</ul>
            </>
          )}
          {critiques.length > 0 && (
            <>
              <h4>비평 근거</h4>
              {critiques.map((c, i) => (
                <blockquote key={i} className="paper-callout paper-callout--insight">
                  <div className="paper-callout-tag">{c.persona ?? "critic"}</div>
                  <p>{c.risk}</p>
                  {(c.confidence_basis ?? []).length > 0 && (
                    <ul>{c.confidence_basis!.map((b, j) => <li key={j}>{b}</li>)}</ul>
                  )}
                  {c.suggested_fix && <p><em>Fix: {c.suggested_fix}</em></p>}
                </blockquote>
              ))}
            </>
          )}
        </div>
      );
    }
    case "council":
      return (
        <div className="paper-prose">
          <KoInterpretation text={body.ko_summary} />
          <p className="paper-score">
            {String(body.verdict ?? "").toUpperCase()}
            {body.final_confidence != null && ` · ${Math.round(Number(body.final_confidence) * 100)}%`}
          </p>
          <h4>승인 MVP</h4>
          <ul>{((body.approved_mvp as string[]) ?? []).map((x, i) => <li key={i}>{x}</li>)}</ul>
        </div>
      );
    case "backlog": {
      const tasks = (body.tasks as { id?: string; title?: string; owner?: string; priority?: string }[]) ?? [];
      return (
        <div className="paper-prose">
          <p className="paper-meta">총 {Number(body.total ?? tasks.length)} tasks</p>
          {tasks.map((t) => (
            <div key={t.id} className="paper-row">
              <span className="paper-row-id">{t.id}</span>
              <strong>{t.title}</strong>
              <span className="paper-meta">{t.owner} · {t.priority}</span>
            </div>
          ))}
        </div>
      );
    }
    case "qa":
      return (
        <div className="paper-prose">
          <KoInterpretation text={body.ko_summary} />
          {((body.evidence_bindings as { claim?: string; source_ref?: string; confidence?: string }[]) ?? []).map((e, i) => (
            <div key={i} className="paper-evidence">
              <p>{e.claim}</p>
              <code>{e.source_ref}</code> · {e.confidence}
            </div>
          ))}
        </div>
      );
    case "strategic_qa": {
      const highlights = (body.highlights as { check_type?: string; finding?: string; severity?: string }[]) ?? [];
      const koSummaries = (body.ko_summaries as { label?: string; text?: string }[]) ?? [];
      return (
        <div className="paper-prose">
          <KoInterpretationList items={koSummaries} />
          {!koSummaries.length && <KoInterpretation text={body.ko_summary} />}
          {highlights.length === 0 && <p className="paper-lead">전략 QA 이슈 없음</p>}
          {highlights.map((c, i) => (
            <blockquote key={i} className="paper-callout paper-callout--alert">
              <div className="paper-callout-tag">{c.check_type} · {c.severity}</div>
              <p>{c.finding}</p>
            </blockquote>
          ))}
        </div>
      );
    }
    case "validation": {
      const hyps = (body.core_hypothesis as { id?: string; statement?: string; kpi?: string; minimum_success_signal?: string }[]) ?? [];
      return (
        <div className="paper-prose">
          <KoInterpretation text={body.ko_summary} />
          {hyps.map((h) => (
            <div key={h.id} className="paper-hypothesis">
              <div className="paper-hyp-id">{h.id}</div>
              <p>{h.statement}</p>
              <p className="paper-meta">KPI: {h.kpi} · 성공 기준: {h.minimum_success_signal}</p>
            </div>
          ))}
        </div>
      );
    }
    default:
      return <pre className="md-code paper-code">{JSON.stringify(section.body, null, 2)}</pre>;
  }
}

function DocumentCover({ doc }: { doc: RunDocuments }) {
  return (
    <header className="paper-cover">
      <div className="paper-cover-main">
        <span className="paper-kicker">Confidential · For Discussion</span>
        <h1 className="paper-title">{doc.title}</h1>
        {doc.subtitle && <p className="paper-subtitle">{doc.subtitle}</p>}
        {doc.ko_summary && (
          <div className="paper-cover-ko">
            <KoInterpretation text={doc.ko_summary} />
          </div>
        )}
      </div>
      <aside className="paper-cover-aside">
        <div className="paper-meta-block">
          <span className="paper-meta-label">Run</span>
          <span className="paper-meta-value">{doc.run_id.slice(0, 8)}</span>
        </div>
        {doc.verdict && (
          <div className="paper-meta-block">
            <span className="paper-meta-label">Verdict</span>
            <span className="paper-meta-value paper-meta-value--badge">{doc.verdict}</span>
          </div>
        )}
        {doc.confidence != null && (
          <div className="paper-meta-block">
            <span className="paper-meta-label">Confidence</span>
            <span className="paper-meta-value">{Math.round(doc.confidence * 100)}%</span>
          </div>
        )}
        <div className="paper-meta-block">
          <span className="paper-meta-label">Sections</span>
          <span className="paper-meta-value">{doc.sections.length}</span>
        </div>
      </aside>
    </header>
  );
}

function DocumentOverview({
  doc,
  onSelectSection,
}: {
  doc: RunDocuments;
  onSelectSection: (id: string) => void;
}) {
  return (
    <article className="paper-sheet">
      <DocumentCover doc={doc} />
      <div className="paper-rule" />
      <nav className="paper-contents" aria-label="목차">
        <h2 className="paper-contents-heading">Contents</h2>
        <ol className="paper-contents-list">
          {doc.sections.map((s, i) => (
            <li key={s.id}>
              <button type="button" className="paper-contents-link" onClick={() => onSelectSection(s.id)}>
                <span className="paper-contents-num">{String(i + 1).padStart(2, "0")}</span>
                <span className="paper-contents-title">{s.title}</span>
                <span className="paper-contents-cluster">{KIND_CLUSTER[s.kind] ?? "REPORT"}</span>
              </button>
            </li>
          ))}
        </ol>
      </nav>
      <footer className="paper-footer">
        <span>PM Build MVP · Hybrid OS</span>
        <span>Overview · {doc.sections.length} sections</span>
      </footer>
    </article>
  );
}

function DocumentSectionPage({
  doc,
  section,
  index,
  onSelectSection,
}: {
  doc: RunDocuments;
  section: DocumentSection;
  index: number;
  onSelectSection: (id: string | null) => void;
}) {
  const prev = index > 0 ? doc.sections[index - 1] : null;
  const next = index < doc.sections.length - 1 ? doc.sections[index + 1] : null;

  return (
    <article className="paper-sheet paper-sheet--section">
      <header className="paper-section-header">
        <button type="button" className="paper-section-back" onClick={() => onSelectSection(null)}>
          ← Overview
        </button>
        <div className="paper-section-header-meta">
          <span className="paper-section-header-cluster">{KIND_CLUSTER[section.kind] ?? "REPORT"}</span>
          <span className="paper-section-header-run">{doc.run_id.slice(0, 8)}</span>
        </div>
      </header>

      <section className={`paper-exhibit paper-exhibit--solo ${sectionAccent(section.kind)}`}>
        <div className="paper-exhibit-rail">
          <span className="paper-exhibit-num">{String(index + 1).padStart(2, "0")}</span>
          <span className="paper-exhibit-cluster">{KIND_CLUSTER[section.kind] ?? "REPORT"}</span>
        </div>
        <div className="paper-exhibit-body">
          <h2 className="paper-exhibit-title">{section.title}</h2>
          <SectionBody section={section} />
        </div>
      </section>

      <nav className="paper-section-nav" aria-label="Section navigation">
        {prev ? (
          <button type="button" className="paper-section-nav-btn" onClick={() => onSelectSection(prev.id)}>
            <span className="paper-section-nav-dir">Previous</span>
            <span className="paper-section-nav-title">{prev.title}</span>
          </button>
        ) : <span />}
        {next ? (
          <button type="button" className="paper-section-nav-btn paper-section-nav-btn--next" onClick={() => onSelectSection(next.id)}>
            <span className="paper-section-nav-dir">Next</span>
            <span className="paper-section-nav-title">{next.title}</span>
          </button>
        ) : <span />}
      </nav>

      <footer className="paper-footer">
        <span>{doc.title}</span>
        <span>{String(index + 1).padStart(2, "0")} / {String(doc.sections.length).padStart(2, "0")}</span>
      </footer>
    </article>
  );
}

export type DocumentsPageProps = {
  run: RunPayload | null;
  activeSectionId: string | null;
  onActiveSectionChange: (id: string | null) => void;
  onDocumentLoad: (doc: RunDocuments) => void;
  onDocumentClear: () => void;
};

export function DocumentsPage({
  run,
  activeSectionId,
  onActiveSectionChange,
  onDocumentLoad,
  onDocumentClear,
}: DocumentsPageProps) {
  const [runs, setRuns] = useState<RunPayload[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(run?.run_id ?? null);
  const [doc, setDoc] = useState<RunDocuments | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listRuns().then(({ runs: list }) => {
      setRuns(list);
      if (!selectedRunId && list.length > 0) setSelectedRunId(list[0].run_id);
    }).catch(() => {});
  }, []);

  useEffect(() => {
    if (run?.run_id) setSelectedRunId(run.run_id);
  }, [run?.run_id]);

  useEffect(() => {
    setDoc(null);
    setError(null);
    onDocumentClear();
    onActiveSectionChange(null);
    if (!selectedRunId) return;
    api.getDocuments(selectedRunId)
      .then((loaded) => {
        setDoc(loaded);
        onDocumentLoad(loaded);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [selectedRunId]);

  useEffect(() => {
    if (!selectedRunId) return;
    api.getDocuments(selectedRunId)
      .then((loaded) => {
        setDoc(loaded);
        onDocumentLoad(loaded);
      })
      .catch(() => {});
  }, [run?.status]);

  const activeIndex = doc && activeSectionId
    ? doc.sections.findIndex((s) => s.id === activeSectionId)
    : -1;
  const activeSection = activeIndex >= 0 ? doc!.sections[activeIndex] : null;

  const handleRunChange = (runId: string) => {
    setSelectedRunId(runId);
    onActiveSectionChange(null);
  };

  if (!runs.length && !selectedRunId) {
    return (
      <div className="paper-shell">
        <div className="paper-stage">
          <div className="paper-sheet paper-sheet--empty">
            <p className="paper-empty">Run을 시작하면 산출물 문서가 생성됩니다.</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="paper-shell">
      <header className="paper-run-bar">
        <span className="paper-run-label">Run Archive</span>
        <div className="paper-run-pills">
          {runs.map((r) => (
            <button
              key={r.run_id}
              type="button"
              className={`paper-run-pill ${selectedRunId === r.run_id ? "active" : ""}`}
              onClick={() => handleRunChange(r.run_id)}
            >
              {r.run_id.slice(0, 8)} · {r.status}
            </button>
          ))}
        </div>
        {doc && (
          <>
            <span className="paper-run-divider" />
            <span className="paper-run-context">
              {activeSection
                ? `${String(activeIndex + 1).padStart(2, "0")} · ${activeSection.title}`
                : "Overview"}
              {" · "}
              {doc.translation_status === "ok"
                ? "한국어 해석 적용"
                : doc.translation_status === "partial"
                  ? "한국어 해석 일부"
                  : "한국어 해석 대기"}
            </span>
          </>
        )}
      </header>

      {error && !doc && (
        <div className="paper-stage">
          <div className="paper-sheet paper-sheet--empty">
            <p className="paper-empty">{error}</p>
          </div>
        </div>
      )}

      {doc && (
        <div className="paper-stage">
          {activeSection && activeIndex >= 0 ? (
            <DocumentSectionPage
              doc={doc}
              section={activeSection}
              index={activeIndex}
              onSelectSection={onActiveSectionChange}
            />
          ) : (
            <DocumentOverview doc={doc} onSelectSection={onActiveSectionChange} />
          )}
        </div>
      )}

      {!doc && !error && selectedRunId && (
        <div className="paper-stage">
          <div className="paper-sheet paper-sheet--empty">
            <p className="paper-empty">로딩 중…</p>
          </div>
        </div>
      )}
    </div>
  );
}
