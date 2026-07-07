import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "./lib/api";
import { toFeedMessage, isLiveFeedEvent } from "./lib/feed";
import type { RunPayload } from "./lib/types";
import { useEventStream } from "./lib/useEventStream";
import { Feed } from "./components/Feed";
import { AgentProfilePanel } from "./components/AgentProfilePanel";
import { IntentReviewPage } from "./pages/IntentReviewPage";
import { KernelPage } from "./pages/KernelPage";
import { DocumentsPage } from "./pages/DocumentsPage";
import type { RunDocuments } from "./lib/api";
import { DecisionsPage } from "./pages/DecisionsPage";

type Page = "feed" | "intent" | "kernel" | "documents" | "decisions";

const PAGES: { id: Page; label: string }[] = [
  { id: "feed", label: "Live Feed" },
  { id: "intent", label: "Intent Review" },
  { id: "kernel", label: "Founder Kernel" },
  { id: "documents", label: "산출물" },
  { id: "decisions", label: "Decisions" },
];

const ACTIVE_STATUSES = new Set(["running", "awaiting_choice"]);

export default function App() {
  const [page, setPage] = useState<Page>("feed");
  const [channel, setChannel] = useState("all");
  const [run, setRun] = useState<RunPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [profilePhase, setProfilePhase] = useState<string | null>(null);
  const [profileRole, setProfileRole] = useState<string | null>(null);
  const [docNav, setDocNav] = useState<RunDocuments | null>(null);
  const [docSectionId, setDocSectionId] = useState<string | null>(null);
  const [docSidebarMode, setDocSidebarMode] = useState<"app" | "sections">("app");

  const runId = run?.run_id ?? null;
  const { events, streamEnded } = useEventStream(runId);

  useEffect(() => {
    api.listRuns()
      .then(({ runs }) => { if (runs.length > 0) setRun(runs[0]); })
      .catch(() => { /* server not up yet — fine */ });
  }, []);

  useEffect(() => {
    if (!runId || !ACTIVE_STATUSES.has(run?.status ?? "")) return;
    const t = setInterval(() => {
      api.getRun(runId).then(setRun).catch(() => {});
    }, 2000);
    return () => clearInterval(t);
  }, [runId, run?.status]);

  useEffect(() => {
    if (run?.status === "awaiting_choice") setPage("intent");
  }, [run?.status]);

  useEffect(() => {
    if (page !== "documents") {
      setDocSidebarMode("app");
      setDocSectionId(null);
    }
  }, [page]);

  const openDocSection = useCallback((sectionId: string | null) => {
    setDocSectionId(sectionId);
    if (sectionId) setDocSidebarMode("sections");
  }, []);

  const backToAppSidebar = useCallback(() => {
    setDocSidebarMode("app");
    setDocSectionId(null);
  }, []);

  const handleDocumentLoad = useCallback((doc: RunDocuments) => {
    setDocNav(doc);
  }, []);

  const handleDocumentClear = useCallback(() => {
    setDocNav(null);
    setDocSectionId(null);
    setDocSidebarMode("app");
  }, []);

  const openProfile = useCallback((opts: { phase?: string; role?: string }) => {
    setProfilePhase(opts.phase ?? null);
    setProfileRole(opts.role ?? null);
  }, []);

  const closeProfile = useCallback(() => {
    setProfilePhase(null);
    setProfileRole(null);
  }, []);

  const startRun = useCallback(async () => {
    setError(null);
    setStarting(true);
    try {
      const payload = await api.startRun();
      setRun(payload);
      setChannel("all");
      setPage("feed");
      closeProfile();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setStarting(false);
    }
  }, [closeProfile]);

  const messages = useMemo(
    () => events.filter(isLiveFeedEvent).map(toFeedMessage),
    [events],
  );
  const filtered = channel === "all" ? messages : messages.filter((m) => m.roleTitle === channel);

  const channels = useMemo(() => {
    const order: string[] = [];
    for (const m of messages) {
      if (!order.includes(m.roleTitle)) order.push(m.roleTitle);
    }
    return order;
  }, [messages]);

  const counts = useMemo(() => {
    const c = { pass: 0, warn: 0, fail: 0 };
    for (const m of filtered) {
      if (m.status === "pass") c.pass++;
      else if (m.status === "warn") c.warn++;
      else if (m.status === "fail") c.fail++;
    }
    return c;
  }, [filtered]);

  const status = run?.status ?? "idle";
  const isActive = ACTIVE_STATUSES.has(status);

  const pageTitle = page === "feed"
    ? `# ${channel === "all" ? "all-agents" : channel.toLowerCase()}`
    : page === "documents" && docSectionId && docNav
      ? docNav.sections.find((s) => s.id === docSectionId)?.title ?? "산출물"
      : PAGES.find((p) => p.id === page)?.label ?? "";

  return (
    <div className="app">
      <header className="app-header">
        <div className="app-header-brand">
          <div className="sidebar-logo">PM</div>
          <div className="app-header-brand-text">
            <div className="sidebar-title">Hybrid OS Console</div>
            <div className="sidebar-sub">{runId ? `run: ${runId.slice(0, 8)}` : "no run"}</div>
          </div>
        </div>
        <div className="app-header-main">
          <span className="topbar-title">{pageTitle}</span>
          <div className="topbar-divider" />
          <span className="topbar-meta">
            {events.length} events{streamEnded ? " · stream ended" : ""}
          </span>
          <div className="legend">
            <span className="legend-item">
              <span className="legend-swatch" style={{ background: "var(--pass)" }} /> {counts.pass} pass
            </span>
            <span className="legend-item">
              <span className="legend-swatch" style={{ background: "var(--warn)" }} /> {counts.warn} warn
            </span>
            {counts.fail > 0 && (
              <span className="legend-item">
                <span className="legend-swatch" style={{ background: "var(--fail)" }} /> {counts.fail} fail
              </span>
            )}
          </div>
          <button className="btn primary topbar-action" onClick={startRun} disabled={starting || isActive}>
            {isActive ? "Run in progress…" : starting ? "Starting…" : "Start Run"}
          </button>
        </div>
      </header>

      <div className="app-body">
        <aside className="sidebar">
          <div className="sidebar-body">
            {page === "documents" && docSidebarMode === "sections" && docNav ? (
              <>
                <button type="button" className="nav-item nav-back" onClick={backToAppSidebar}>
                  ← Console
                </button>
                <div className="nav-label">PAGES · {docNav.title.slice(0, 24)}</div>
                <div
                  className={`nav-item ${docSectionId === null ? "active" : ""}`}
                  onClick={() => openDocSection(null)}
                >
                  Overview
                </div>
                {docNav.sections.map((s, i) => (
                  <div
                    key={s.id}
                    className={`nav-item ${docSectionId === s.id ? "active" : ""}`}
                    onClick={() => openDocSection(s.id)}
                  >
                    <span className="nav-section-num">{String(i + 1).padStart(2, "0")}</span>
                    {s.title}
                  </div>
                ))}
              </>
            ) : (
              <>
                <div className="nav-label">PAGES</div>
                {PAGES.map((p) => (
                  <div
                    key={p.id}
                    className={`nav-item ${page === p.id ? "active" : ""}`}
                    onClick={() => setPage(p.id)}
                  >
                    {p.label}
                    {p.id === "intent" && status === "awaiting_choice" && (
                      <span className="count" style={{ color: "var(--warn)" }}>●</span>
                    )}
                  </div>
                ))}

                {page === "documents" && docNav && docNav.sections.length > 0 && (
                  <>
                    <div className="nav-label">DOCUMENT</div>
                    <div
                      className={`nav-item ${docSectionId === null ? "active" : ""}`}
                      onClick={() => openDocSection(null)}
                    >
                      Overview
                    </div>
                    {docNav.sections.map((s, i) => (
                      <div
                        key={s.id}
                        className={`nav-item ${docSectionId === s.id ? "active" : ""}`}
                        onClick={() => openDocSection(s.id)}
                      >
                        <span className="nav-section-num">{String(i + 1).padStart(2, "0")}</span>
                        {s.title}
                      </div>
                    ))}
                  </>
                )}

                {page === "feed" && (
                  <>
                    <div className="nav-label">CHANNELS</div>
                    <div
                      className={`nav-item ${channel === "all" ? "active" : ""}`}
                      onClick={() => setChannel("all")}
                    >
                      <span className="hash">#</span> all-agents
                      <span className="count">{messages.length || ""}</span>
                    </div>
                    {channels.map((ch) => (
                      <div
                        key={ch}
                        className={`nav-item ${channel === ch ? "active" : ""}`}
                        onClick={() => {
                          setChannel(ch);
                          openProfile({ role: ch });
                        }}
                      >
                        <span className="hash">#</span> {ch.toLowerCase()}
                        <span className="count">{messages.filter((m) => m.roleTitle === ch).length}</span>
                      </div>
                    ))}
                  </>
                )}
              </>
            )}
          </div>

          <div className="sidebar-footer">
            <div className={`status-dot ${status}`} />
            {status === "idle" ? "no run started" : status.replace("_", " ")}
          </div>
        </aside>

        <main className="main">
          {error && <div className="error-banner">{error}</div>}
          {run?.error && <div className="error-banner">{run.error}</div>}

          <div className={`content ${page === "feed" ? "content-feed" : ""}`}>
            {page === "feed" && (
              <div className="feed-layout">
                <Feed
                  messages={filtered}
                  selectedPhase={profilePhase}
                  onSelectAgent={(msg) => openProfile({ phase: msg.phase, role: msg.roleTitle })}
                />
                {runId && (profilePhase || profileRole) && (
                  <AgentProfilePanel
                    runId={runId}
                    phase={profilePhase ?? undefined}
                    roleTitle={profilePhase ? undefined : profileRole ?? undefined}
                    onClose={closeProfile}
                  />
                )}
              </div>
            )}
            {page === "intent" && <IntentReviewPage run={run} onRunUpdate={setRun} />}
            {page === "kernel" && <KernelPage />}
            {page === "documents" && (
              <DocumentsPage
                run={run}
                activeSectionId={docSectionId}
                onActiveSectionChange={openDocSection}
                onDocumentLoad={handleDocumentLoad}
                onDocumentClear={handleDocumentClear}
              />
            )}
            {page === "decisions" && <DecisionsPage run={run} />}
          </div>
        </main>
      </div>
    </div>
  );
}
