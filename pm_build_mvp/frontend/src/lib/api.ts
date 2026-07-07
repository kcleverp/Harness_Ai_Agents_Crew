import type { RunPayload } from "./types";

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch { /* keep status text */ }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export interface IntentReviewDoc {
  run_id: string;
  mode: string;
  kernel: Record<string, string[]>;
  review: {
    user_analysis?: string;
    problem_analysis?: string;
    opportunity_analysis?: string;
    coherence_analysis?: string;
    problems?: { area: string; severity: string; issue: string; kernel_ref?: string }[];
    structural_warnings?: { area: string; severity: string; issue: string; kernel_ref?: string }[];
    verdict?: string;
    confidence?: number;
    ko_summary?: string;
  };
  review_ko?: {
    user_analysis?: string;
    problem_analysis?: string;
    opportunity_analysis?: string;
    coherence_analysis?: string;
    ko_summary?: string;
    problems?: { issue?: string }[];
    structural_warnings?: { issue?: string }[];
  };
  translation_status?: "ok" | "pending";
}

export interface WorkspaceFile {
  path: string;
  name: string;
  dir: string;
  ext: string;
  size: number;
}

export interface WorkspaceTree {
  run_id: string;
  root: string;
  files: WorkspaceFile[];
}

export interface WorkspaceFileContent {
  run_id: string;
  root: string;
  path: string;
  ext: string;
  content: string;
}

export interface KernelDoc {
  core_thesis: string[];
  non_negotiables: string[];
  anti_patterns: string[];
  founder_convictions: string[];
  kernel_hash: string;
}

export interface DecisionGraphItem {
  id?: string;
  name?: string;
  rationale?: string;
  reason?: string;
  conflicts_with?: string;
  accepted?: string;
  sacrificed?: string;
  phase?: string;
}

export interface AgentProfileDoc {
  run_id: string;
  root: string;
  phases: string[];
  role_title_ko: string;
  role_title_en: string;
  model: string | null;
  primary_confidence: number | null;
  confidence_scores: { source: string; label: string; value: number; timestamp?: string | null }[];
  selected: DecisionGraphItem[];
  rejected: DecisionGraphItem[];
  tradeoffs: DecisionGraphItem[];
  snapshots: DecisionsDoc["snapshots"];
  events: DecisionsDoc["events"];
  activity: { event_type: string; timestamp?: string; status?: string }[];
  evidence_bindings?: {
    claim?: string;
    source_ref?: string;
    confidence_label?: string;
    confidence_value?: number;
  }[];
  intent_review?: {
    verdict?: string;
    confidence?: number;
    user_analysis?: string;
    problem_analysis?: string;
    opportunity_analysis?: string;
    coherence_analysis?: string;
    ko_summary?: string;
    problems?: { area?: string; severity?: string; issue?: string }[];
    structural_warnings?: { area?: string; severity?: string; issue?: string }[];
  };
  idea_loop?: {
    selected_core?: string;
    rejected_features?: string[];
    risks?: string[];
    ko_summary?: string;
    critiques?: {
      persona?: string;
      risk?: string;
      confidence?: number;
      confidence_basis?: string[];
      suggested_fix?: string;
    }[];
  };
  strategic_qa?: {
    has_high_severity?: boolean;
    founder_verdict?: string;
    market_verdict?: string;
    founder_summary?: string;
    market_summary?: string;
    failed_checks?: { check_type?: string; finding?: string; severity?: string; passed?: boolean }[];
    all_checks?: { check_type?: string; finding?: string; severity?: string; passed?: boolean }[];
  };
  validation_strategy?: {
    ko_summary?: string;
    hypotheses?: { id?: string; statement?: string; kpi?: string; minimum_success_signal?: string; decision_impact?: string }[];
    experiments?: string[];
    counterfactuals?: string[];
    failure_modes?: unknown[];
  };
}

export interface DocumentSection {
  id: string;
  title: string;
  kind: string;
  body: unknown;
}

export interface RunDocuments {
  run_id: string;
  root: string;
  title: string;
  subtitle: string;
  verdict?: string;
  confidence?: number;
  sections: DocumentSection[];
  translation_status?: "ok" | "partial" | "pending";
  ko_summary?: string;
}

export interface DecisionsDoc {
  run_id: string;
  root: string;
  snapshots: { source: string; phase: string; artifact: string; decision_graph: Record<string, unknown> }[];
  events: {
    source: string;
    event_id?: string;
    phase?: string;
    event_type?: string;
    timestamp?: string;
    artifact?: string;
    details?: Record<string, unknown>;
  }[];
  rejected: DecisionGraphItem[];
  selected: DecisionGraphItem[];
  tradeoffs: DecisionGraphItem[];
  selected_ko?: DecisionGraphItem[];
  rejected_ko?: DecisionGraphItem[];
  tradeoffs_ko?: DecisionGraphItem[];
  translation_status?: string;
}

export const api = {
  startRun: () => fetch("/runs", { method: "POST" }).then((r) => json<RunPayload>(r)),
  getRun: (runId: string) => fetch(`/runs/${runId}`).then((r) => json<RunPayload>(r)),
  listRuns: () => fetch("/runs").then((r) => json<{ runs: RunPayload[] }>(r)),
  getIntentReview: (runId: string) =>
    fetch(`/runs/${runId}/intent-review`).then((r) => json<IntentReviewDoc>(r)),
  postIntentChoice: (
    runId: string,
    body: { choice: "proceed" | "reject" | "edit"; reason?: string; kernel?: Record<string, string[]> },
  ) =>
    fetch(`/runs/${runId}/intent-choice`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then((r) => json<{ ok: boolean; choice: string }>(r)),
  getWorkspace: (runId: string) =>
    fetch(`/runs/${runId}/workspace`).then((r) => json<WorkspaceTree>(r)),
  getWorkspaceFile: (runId: string, path: string) =>
    fetch(`/runs/${runId}/workspace/file?path=${encodeURIComponent(path)}`).then((r) =>
      json<WorkspaceFileContent>(r),
    ),
  getKernel: () => fetch("/kernel").then((r) => json<KernelDoc>(r)),
  putKernel: (body: Omit<KernelDoc, "kernel_hash">) =>
    fetch("/kernel", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then((r) => json<KernelDoc>(r)),
  getDecisions: (runId: string) =>
    fetch(`/runs/${runId}/decisions`).then((r) => json<DecisionsDoc>(r)),
  getAgentProfile: (runId: string, opts: { phase?: string; role?: string }) => {
    const params = new URLSearchParams();
    if (opts.phase) params.set("phase", opts.phase);
    if (opts.role) params.set("role", opts.role);
    return fetch(`/runs/${runId}/agent-profile?${params}`).then((r) => json<AgentProfileDoc>(r));
  },
  getDocuments: (runId: string) =>
    fetch(`/runs/${runId}/documents`).then((r) => json<RunDocuments>(r)),
};
