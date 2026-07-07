// Canonical telemetry event — mirror of telemetry_schema.py (schema v1).
export interface CanonicalEvent {
  schema_version: string;
  event_id: string;
  parent_event_id: string | null;
  related_event_ids: string[];
  run_id: string;
  phase: string;
  domain: string;
  category: string;
  event_type: string;
  artifact: string | null;
  timestamp: string;
  details: Record<string, unknown>;
}

export type RunStatus =
  | "running"
  | "awaiting_choice"
  | "complete"
  | "rejected"
  | "failed";

export interface RunPayload {
  run_id: string;
  status: RunStatus;
  started_at: string;
  finished_at: string | null;
  result: Record<string, unknown> | null;
  error: string | null;
}

export type FeedStatus = "pass" | "warn" | "fail" | "info";

// Slack-like display projection of a canonical event (see lib/feed.ts).
export interface FeedMessage {
  id: string;
  phase: string;
  roleTitle: string;
  agent: string;
  domain: string;
  event_type: string;
  timestamp: string;
  content: string;
  artifact?: string;
  status: FeedStatus;
}
