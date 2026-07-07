import type { CanonicalEvent, FeedMessage, FeedStatus } from "./types";
import { agentLabel, resolveRole } from "./roles";

/** Map a canonical telemetry event to a Slack-like feed message. */

const PASS_EVENTS = new Set([
  "validation_passed", "patch_applied", "council_approved",
  "consistency_check_passed", "escalation_resolved", "intent_proceed",
  "translation_generated", "translation_skipped",
]);
const WARN_EVENTS = new Set([
  "validation_warning", "schema_mismatch", "conflict_detected",
  "confidence_penalty_applied", "escalation_triggered", "translation_stale",
]);
const FAIL_EVENTS = new Set([
  "patch_failed", "workflow_failed", "system_integrity_alert",
  "fabricated_founder_evidence", "kernel_violation", "schema_violation",
  "council_rejected", "consistency_check_failed", "translation_failed",
  "repair_failed", "kernel_tampered", "intent_reject",
]);

/** Lifecycle / progress events shown in Live Feed (decision detail excluded). */
const LIVE_FEED_EVENTS = new Set([
  "run_start", "run_end", "phase_start", "phase_end", "workflow_failed",
  "intent_proceed", "intent_reject", "intent_choice",
  "validation_passed", "validation_warning", "schema_mismatch",
  "strategic_qa_completed", "validation_strategy_completed", "idea_loop_completed",
  "pm_reconstruction_completed",
  "patch_applied", "patch_failed",
  "council_approved", "council_rejected",
  "consistency_check_passed", "consistency_check_failed",
  "escalation_triggered", "escalation_resolved",
  "translation_generated", "translation_skipped", "translation_stale", "translation_failed",
  "system_integrity_alert", "schema_violation",
]);

export function isLiveFeedEvent(ev: CanonicalEvent): boolean {
  return LIVE_FEED_EVENTS.has(ev.event_type);
}

function statusOf(ev: CanonicalEvent): FeedStatus {
  if (PASS_EVENTS.has(ev.event_type)) return "pass";
  if (FAIL_EVENTS.has(ev.event_type)) return "fail";
  if (WARN_EVENTS.has(ev.event_type)) return "warn";
  if (ev.event_type === "phase_end" || ev.event_type === "run_end") {
    const st = String(ev.details?.status ?? "").toUpperCase();
    if (st === "FAILED") return "fail";
    return "pass";
  }
  return "info";
}

function compact(value: unknown, max = 160): string {
  if (value == null) return "";
  const s = typeof value === "string" ? value : JSON.stringify(value);
  return s.length > max ? s.slice(0, max) + "…" : s;
}

function contentOf(ev: CanonicalEvent): string {
  const d = ev.details ?? {};
  const parts: string[] = [];

  switch (ev.event_type) {
    case "run_start":
      parts.push(`워크플로 시작 · kernel ${compact(d.kernel_hash_prefix)}…`);
      break;
    case "run_end":
      parts.push(
        `워크플로 종료 · ${compact(d.status)} · risk=${compact(d.risk_score)} · tasks=${compact(d.tasks)} · patches=${compact(d.patch_attempts)}`,
      );
      break;
    case "phase_start":
      parts.push("작업 시작");
      break;
    case "phase_end":
      parts.push("작업 완료");
      break;
    case "intent_choice": {
      const choice = compact(d.choice, 40);
      parts.push(`founder 결정 · ${choice}`);
      break;
    }
    case "intent_proceed":
      parts.push("Intent gate · 진행");
      break;
    case "intent_reject":
      parts.push("Intent gate · 중단");
      break;
    case "council_approved":
      parts.push(`Council 승인 · confidence=${compact(d.final_confidence)}`);
      break;
    case "council_rejected":
      parts.push(`Council 기각 · verdict=${compact(d.verdict)}`);
      break;
    case "schema_mismatch":
      parts.push(`스키마 불일치 (attempt ${compact(d.attempt)})`);
      break;
    case "patch_applied":
      parts.push(`패치 적용 완료 (attempt ${compact(d.attempt)})`);
      break;
    case "patch_failed":
      parts.push(`패치 실패`);
      break;
    case "validation_warning": {
      const finding = typeof d.finding === "string" ? d.finding : "";
      const checkType = String(d.check_type ?? d.qa_type ?? "");
      const severity = String(d.severity ?? "");
      if (finding) {
        parts.push(`${checkType || "검증"} · ${severity || "warn"} · ${compact(finding, 140)}`);
      } else if (checkType) {
        parts.push(`${checkType} · ${severity || "warn"}`);
      } else {
        parts.push(`검증 경고 · ${compact(d, 100)}`);
      }
      break;
    }
    case "strategic_qa_completed": {
      const failed = (d.failed_checks as { check_type?: string; finding?: string }[] | undefined) ?? [];
      if (failed.length > 0) {
        const first = failed[0];
        parts.push(`전략 QA · ${failed.length}건 · ${compact(first.finding ?? first.check_type, 120)}`);
      } else {
        parts.push(`전략 QA 완료 · founder=${compact(d.founder_verdict)} · market=${compact(d.market_verdict)}`);
      }
      break;
    }
    case "validation_strategy_completed":
      parts.push(
        `검증 전략 · 가설 ${compact(d.hypothesis_count)}개 · 실험 ${compact(d.experiment_count)}개`,
      );
      break;
    case "idea_loop_completed":
      parts.push(
        `아이디어 확정 · ${compact(d.selected_core, 100)} · 기각 ${((d.rejected_features as string[]) ?? []).length}건`,
      );
      break;
    case "pm_reconstruction_completed":
      parts.push(
        `PM 재구성 · ${compact(d.persona_name, 40)} · 기회 ${compact(d.opportunity_score)} · ${compact(d.recommended_direction, 80)}`,
      );
      break;
    case "validation_passed":
      parts.push("검증 통과");
      break;
    case "consistency_check_passed":
      parts.push("일관성 검사 통과");
      break;
    case "consistency_check_failed":
      parts.push("일관성 검사 실패");
      break;
    case "escalation_triggered":
      parts.push(`에스컬레이션 발동`);
      break;
    case "escalation_resolved":
      parts.push("에스컬레이션 해소");
      break;
    case "translation_generated":
      parts.push("한국어 번역 완료");
      break;
    case "translation_skipped":
      parts.push("번역 생략 (최신 상태)");
      break;
    case "translation_stale":
      parts.push("번역 갱신 중");
      break;
    case "translation_failed":
      parts.push("번역 실패");
      break;
    case "system_integrity_alert":
      parts.push(`무결성 위반: ${compact(d.violation, 80)}`);
      break;
    case "schema_violation":
      parts.push(`스키마 거부: ${compact(d.rejected_event_type)}`);
      break;
    case "workflow_failed":
      parts.push(`워크플로 실패 · ${compact(d.reason, 100)}`);
      break;
    default:
      parts.push(compact(d, 120) || ev.event_type);
  }
  return parts.join(" ");
}

export function toFeedMessage(ev: CanonicalEvent): FeedMessage {
  const ts = ev.timestamp?.includes("T") ? ev.timestamp.split("T")[1] : ev.timestamp;
  const role = resolveRole(ev.phase);
  return {
    id: ev.event_id,
    phase: ev.phase,
    roleTitle: role.title_ko,
    agent: agentLabel(ev.phase, ev.details),
    domain: ev.domain,
    event_type: ev.event_type,
    timestamp: ts ?? "",
    content: contentOf(ev),
    artifact: ev.artifact ?? undefined,
    status: statusOf(ev),
  };
}

export { resolveRole, agentLabel };
