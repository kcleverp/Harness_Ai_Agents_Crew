import { useEffect, useMemo, useState } from "react";
import { api, type WorkspaceFile, type WorkspaceTree } from "../lib/api";
import type { RunPayload } from "../lib/types";
import { DocRenderer } from "../components/workspace/DocRenderer";

function formatRunLabel(run: RunPayload): string {
  const date = run.started_at?.split("T")[0] ?? "";
  return `${run.run_id.slice(0, 8)} · ${run.status}${date ? ` · ${date}` : ""}`;
}

export function WorkspacePage({ run }: { run: RunPayload | null }) {
  const [runs, setRuns] = useState<RunPayload[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(run?.run_id ?? null);
  const [tree, setTree] = useState<WorkspaceTree | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [content, setContent] = useState<{ path: string; ext: string; body: string } | null>(null);

  useEffect(() => {
    api.listRuns()
      .then(({ runs: list }) => {
        setRuns(list);
        if (!selectedRunId && list.length > 0) setSelectedRunId(list[0].run_id);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (run?.run_id && !selectedRunId) setSelectedRunId(run.run_id);
  }, [run?.run_id, selectedRunId]);

  useEffect(() => {
    setTree(null);
    setSelectedPath(null);
    setContent(null);
    setError(null);
    if (!selectedRunId) return;
    api.getWorkspace(selectedRunId)
      .then((t) => {
        setTree(t);
        const preferred =
          t.files.find((f) => f.name === "founder_summary_ko.md") ??
          t.files.find((f) => f.name === "founder_summary.md") ??
          t.files.find((f) => f.name === "concept_checkpoint.json") ??
          t.files[0];
        if (preferred) setSelectedPath(preferred.path);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [selectedRunId]);

  useEffect(() => {
    if (!selectedRunId || !selectedPath) return;
    api.getWorkspaceFile(selectedRunId, selectedPath)
      .then((f) => setContent({ path: f.path, ext: f.ext, body: f.content }))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [selectedRunId, selectedPath]);

  const grouped = useMemo(() => {
    const groups = new Map<string, WorkspaceFile[]>();
    for (const f of tree?.files ?? []) {
      const dir = f.dir || "(root)";
      if (!groups.has(dir)) groups.set(dir, []);
      groups.get(dir)!.push(f);
    }
    return [...groups.entries()];
  }, [tree]);

  const selectedRun = runs.find((r) => r.run_id === selectedRunId) ?? run;

  if (!runs.length && !selectedRunId) {
    return (
      <div className="page">
        <h2>Workspace</h2>
        <p className="lead">Run을 시작하면 산출물(artifacts)이 여기에 표시됩니다.</p>
      </div>
    );
  }

  return (
    <div className="workspace-layout">
      <aside className="ws-runs">
        <div className="ws-tree-header">
          <span>실행 목록</span>
          <span className="ws-count">{runs.length}</span>
        </div>
        {runs.map((r) => (
          <div
            key={r.run_id}
            className={`ws-run-item ${selectedRunId === r.run_id ? "active" : ""}`}
            onClick={() => setSelectedRunId(r.run_id)}
          >
            <div className="ws-run-id">{r.run_id.slice(0, 8)}</div>
            <div className="ws-run-meta">{r.status}</div>
          </div>
        ))}
      </aside>

      <aside className="ws-tree">
        <div className="ws-tree-header">
          <span className="ws-root">{tree?.root ?? "…"}</span>
          <span className="ws-count">{tree?.files.length ?? 0} files</span>
        </div>
        {error && !tree && <div className="ws-dir">{error}</div>}
        {grouped.map(([dir, files]) => (
          <div key={dir}>
            <div className="ws-dir">{dir}</div>
            {files.map((f) => (
              <div
                key={f.path}
                className={`ws-file ${selectedPath === f.path ? "active" : ""}`}
                onClick={() => setSelectedPath(f.path)}
              >
                <span className={`ws-ext ${f.ext}`}>{f.ext}</span>
                {f.name}
              </div>
            ))}
          </div>
        ))}
        {tree && tree.files.length === 0 && (
          <div className="ws-dir">아직 산출물이 없습니다</div>
        )}
      </aside>

      <section className="ws-content">
        {content ? (
          <>
            <div className="ws-content-header">
              <code>{content.path}</code>
              {selectedRun && (
                <span className="ws-content-meta">{formatRunLabel(selectedRun)}</span>
              )}
            </div>
            <div className="ws-doc">
              <DocRenderer path={content.path} content={content.body} />
            </div>
          </>
        ) : (
          <div className="feed-empty">파일을 선택하세요</div>
        )}
      </section>
    </div>
  );
}
