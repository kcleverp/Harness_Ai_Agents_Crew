import type { ReactNode } from "react";
import { Markdown } from "../Markdown";

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="doc-section">
      <h3 className="doc-section-title">{title}</h3>
      {children}
    </section>
  );
}

function TagList({ items, tone = "neutral" }: { items: string[]; tone?: "pass" | "fail" | "neutral" }) {
  return (
    <ul className={`doc-tag-list ${tone}`}>
      {items.map((item, i) => (
        <li key={i}>{item}</li>
      ))}
    </ul>
  );
}

export function CheckpointView({ data }: { data: Record<string, unknown> }) {
  const mustHave = (data.must_have_mvp as string[]) ?? [];
  const excluded = (data.excluded_features as string[]) ?? [];
  const risks = (data.key_risks as string[]) ?? [];
  const questions = (data.open_questions as string[]) ?? [];

  return (
    <div className="doc-page">
      <h2 className="doc-title">Concept Checkpoint</h2>
      <Section title="문제">
        <p className="doc-lead">{String(data.problem ?? "")}</p>
      </Section>
      <Section title="타겟 사용자">
        <p className="doc-lead">{String(data.target_user ?? "")}</p>
      </Section>
      <Section title="핵심 가치">
        <p className="doc-lead">{String(data.core_value ?? "")}</p>
      </Section>
      <div className="doc-grid">
        <Section title="MVP 필수">
          <TagList items={mustHave} tone="pass" />
        </Section>
        <Section title="제외 기능">
          <TagList items={excluded} tone="fail" />
        </Section>
      </div>
      <Section title="핵심 리스크">
        <TagList items={risks} />
      </Section>
      <Section title="미결 질문">
        <TagList items={questions} />
      </Section>
      {data.recommended_direction ? (
        <Section title="권장 방향">
          <p className="doc-lead">{String(data.recommended_direction)}</p>
        </Section>
      ) : null}
    </div>
  );
}

export function BacklogView({ data }: { data: Record<string, unknown> }) {
  const tasks = (data.tasks as Record<string, unknown>[]) ?? [];
  return (
    <div className="doc-page">
      <h2 className="doc-title">개발 백로그</h2>
      <p className="doc-meta">{tasks.length} tasks</p>
      <div className="backlog-list">
        {tasks.map((task) => (
          <article key={String(task.id)} className="backlog-card">
            <div className="backlog-head">
              <span className="backlog-id">{String(task.id)}</span>
              <span className={`pill ${task.priority === "high" ? "sev-high" : "sev-low"}`}>
                {String(task.priority ?? "—")}
              </span>
              <span className="pill">{String(task.owner ?? "")}</span>
            </div>
            <h4 className="backlog-title">{String(task.title ?? "")}</h4>
            {(task.acceptance_criteria as string[] | undefined)?.length ? (
              <ul className="doc-checklist">
                {(task.acceptance_criteria as string[]).map((c, i) => (
                  <li key={i}>{c}</li>
                ))}
              </ul>
            ) : null}
            {task.notes ? <p className="doc-note">{String(task.notes)}</p> : null}
          </article>
        ))}
      </div>
    </div>
  );
}

export function CouncilView({ data }: { data: Record<string, unknown> }) {
  const conf = data.confidence as Record<string, unknown> | undefined;
  const finalConf = conf?.final_confidence as number | undefined;
  const approved = (data.approved_mvp as string[]) ?? [];
  const rejected = (data.rejected_features as string[]) ?? [];
  const tradeoffs = (data.tradeoffs as string[]) ?? [];

  return (
    <div className="doc-page">
      <div className={`verdict-banner ${data.verdict === "approved" ? "pass" : "fail"}`}>
        <div className="verdict-label">{String(data.verdict ?? "—").toUpperCase()}</div>
        {finalConf != null && (
          <div className="verdict-confidence">final confidence {(finalConf * 100).toFixed(0)}%</div>
        )}
        {data.ko_summary ? <div className="verdict-summary">{String(data.ko_summary)}</div> : null}
      </div>
      <div className="doc-grid">
        <Section title="승인 MVP">
          <TagList items={approved} tone="pass" />
        </Section>
        <Section title="기각 기능">
          <TagList items={rejected} tone="fail" />
        </Section>
      </div>
      <Section title="트레이드오프">
        <TagList items={tradeoffs} />
      </Section>
    </div>
  );
}

export function QaResultView({ data, title }: { data: Record<string, unknown>; title: string }) {
  const results = (data.qa_results as Record<string, unknown>[]) ?? [];
  const evidence = (data.evidence_bindings as Record<string, unknown>[]) ?? [];

  return (
    <div className="doc-page">
      <h2 className="doc-title">{title}</h2>
      <div className="qa-grid">
        {results.map((r, i) => (
          <div key={i} className={`qa-card ${r.passed ? "pass" : "fail"}`}>
            <div className="qa-type">{String(r.qa_type)}</div>
            <div className="qa-status">{r.passed ? "PASS" : "FAIL"}</div>
            {r.finding ? <p className="qa-finding">{String(r.finding)}</p> : null}
          </div>
        ))}
      </div>
      {evidence.length > 0 && (
        <Section title="근거 바인딩">
          <div className="evidence-list">
            {evidence.map((e, i) => (
              <div key={i} className="evidence-row">
                <div className="evidence-claim">{String(e.claim)}</div>
                <div className="evidence-meta">
                  <code className="inline">{String(e.source_ref ?? "")}</code>
                  <span className="pill">{String(e.confidence ?? "")}</span>
                </div>
              </div>
            ))}
          </div>
        </Section>
      )}
    </div>
  );
}

export function UpstreamView({ data, title }: { data: Record<string, unknown>; title: string }) {
  const entries = Object.entries(data).filter(([, v]) => v != null && typeof v !== "object");
  const nested = Object.entries(data).filter(([, v]) => v != null && typeof v === "object" && !Array.isArray(v));

  return (
    <div className="doc-page">
      <h2 className="doc-title">{title}</h2>
      {entries.map(([k, v]) => (
        <Section key={k} title={k.replace(/_/g, " ")}>
          <p className="doc-lead">{String(v)}</p>
        </Section>
      ))}
      {nested.map(([k, v]) => (
        <Section key={k} title={k.replace(/_/g, " ")}>
          <pre className="md-code">{JSON.stringify(v, null, 2)}</pre>
        </Section>
      ))}
      {Array.isArray(data.items) && (
        <TagList items={data.items as string[]} />
      )}
    </div>
  );
}

export function GenericJsonView({ data }: { data: unknown }) {
  if (data == null) return <pre className="md-code">(empty)</pre>;
  if (typeof data !== "object") return <pre className="md-code">{String(data)}</pre>;

  const obj = data as Record<string, unknown>;
  const primitives = Object.entries(obj).filter(([, v]) => v == null || typeof v !== "object");
  const complex = Object.entries(obj).filter(([, v]) => v != null && typeof v === "object");

  return (
    <div className="doc-page">
      {primitives.map(([k, v]) => (
        <Section key={k} title={k.replace(/_/g, " ")}>
          <p className="doc-lead">{String(v)}</p>
        </Section>
      ))}
      {complex.map(([k, v]) => (
        <Section key={k} title={k.replace(/_/g, " ")}>
          {Array.isArray(v) && v.every((x) => typeof x === "string") ? (
            <TagList items={v as string[]} />
          ) : (
            <pre className="md-code">{JSON.stringify(v, null, 2)}</pre>
          )}
        </Section>
      ))}
    </div>
  );
}

export function DocRenderer({ path, content }: { path: string; content: string }) {
  const name = path.split("/").pop() ?? path;
  const ext = path.split(".").pop()?.toLowerCase();

  if (ext === "md") {
    return (
      <div className="doc-page doc-markdown">
        <Markdown source={content} />
      </div>
    );
  }

  let data: unknown;
  try {
    data = JSON.parse(content);
  } catch {
    return <pre className="md-code">{content}</pre>;
  }

  const doc = data as Record<string, unknown>;

  switch (name) {
    case "concept_checkpoint.json":
      return <CheckpointView data={doc} />;
    case "backlog.json":
      return <BacklogView data={doc} />;
    case "council_decision.json":
      return <CouncilView data={doc} />;
    case "product_qa_result.json":
      return <QaResultView data={doc} title="Product QA" />;
    case "strategic_qa_result.json":
      return <QaResultView data={doc} title="Strategic QA" />;
    case "consistency_result.json":
      return <GenericJsonView data={doc} />;
    case "validation_strategy.json":
      return <GenericJsonView data={doc} />;
    case "handoff_to_dev.json":
      return <GenericJsonView data={doc} />;
    case "user_model.json":
      return <UpstreamView data={doc} title="사용자 정의" />;
    case "problem_statement.json":
      return <UpstreamView data={doc} title="문제 발견" />;
    case "opportunity_model.json":
      return <UpstreamView data={doc} title="기회 평가" />;
    case "founder_intent_review.json":
    case "founder_intent_review_ko.json":
      return <GenericJsonView data={doc} />;
    default:
      return <GenericJsonView data={doc} />;
  }
}
