"""
telemetry_schema.py — Canonical event schema, domain taxonomy, and replay contract.

Schema version: v1

═══════════════════════════════════════════════════════════════
 DESIGN CONTRACT
═══════════════════════════════════════════════════════════════

  - Event meaning is declared by the event itself via domain/category/event_type.
  - Projections read domain/category/event_type directly; they never infer meaning
    from phase names or log file origins.
  - canonical stream (reasoning_trace.jsonl) is append-only and immutable.
  - schema_version is required on every event for forward-compatible projection logic.
  - related_event_ids is reserved (default []) for future DAG lineage.

═══════════════════════════════════════════════════════════════
 DOMAIN TAXONOMY  (domain → category → event_type)
═══════════════════════════════════════════════════════════════

  workflow   / lifecycle    → run_start, run_end, phase_start, phase_end, workflow_failed
  decision   / selection    → option_selected, option_rejected, critique_generated,
                              conflict_detected
             / tradeoff     → tradeoff_recorded, confidence_penalty_applied,
                              council_approved, council_rejected
  qa         / validation   → schema_mismatch, validation_warning, validation_passed
             / patching     → patch_applied, patch_failed
             / integrity    → system_integrity_alert, fabricated_founder_evidence,
                              kernel_violation, malformed_lineage, invalid_escalation,
                              schema_violation
             / escalation   → escalation_triggered, escalation_resolved
             / consistency  → consistency_check_passed, consistency_check_failed
  system     / kernel       → kernel_hash_verified, kernel_hash_mismatch, kernel_loaded,
                              kernel_tampered, founder_override
             / config       → config_loaded, config_missing
  patch      / repair       → partial_patch_applied, repair_failed
  translation/ sync         → translation_generated, translation_skipped,
                              translation_stale, translation_failed

═══════════════════════════════════════════════════════════════
 REPLAY SEMANTICS  (v1 — replay-ready structure)
═══════════════════════════════════════════════════════════════

Current stage: replay-ready.
The canonical stream is sufficient to reconstruct all derived state deterministically.

IN SCOPE (current):
  canonical stream → lineage rebuild
    All events sorted by (timestamp, event_id) reconstruct the full event lineage.

  canonical stream → projection rebuild
    runtime.log   : filter domain=workflow
    decisions.log : filter domain=decision
    qa.log        : filter domain=qa | domain=system

  canonical stream → view rebuild
    lineage_index.md : chronological table of all events
    pretty.log       : human-readable multiline render

  canonical stream → decision outcomes
    Filter domain=decision, event_type in (option_selected, option_rejected,
    council_approved, council_rejected) to reconstruct decision history.

  canonical stream → QA outcomes
    Filter domain=qa to reconstruct validation failures, patch actions,
    integrity alerts, and escalations per run.

  canonical stream → artifact transition history
    Filter artifact field across all events to trace each file's lifecycle
    (created → modified → validated → patched → archived).

OUT OF SCOPE (future):
  - Real-time replay engine
  - Distributed event bus / streaming pipeline
  - Graph persistence (Neo4j or similar)
  - Stateful projection cache
  - Temporal queries (e.g. "state at time T")

REPLAY GUARANTEE:
  Projection regeneration must remain deterministic with hash-stable outputs.
  Same canonical input + same projection version → same hashes.
  This is the minimum bar for "replay-ready" status.

═══════════════════════════════════════════════════════════════
 FUTURE DIRECTION: EVENT REPLAYABLE ORCHESTRATION
═══════════════════════════════════════════════════════════════

Target architecture (post-MVP):
  Phase functions become stateless event emitters.
  Workflow state is derived entirely from the canonical stream — not from files.
  Any run can be replayed from its event stream to reproduce identical outputs.

Migration path:
  1. [DONE]  canonical stream as primary write target
  2. [DONE]  domain/category/event_type event identity semantics
  3. [DONE]  deterministic projection regeneration
  4. [FUTURE] phase functions become pure: input events → output events
  5. [FUTURE] workflow state machine driven by event stream
  6. [FUTURE] full replay engine: stream → re-execute → compare outputs

Priority guardrail:
  build quality > orchestration quality > observability sophistication
  Observability infrastructure must never exceed the core system in scope.
"""

from __future__ import annotations

import os
import warnings

SCHEMA_VERSION = "v1"

# ---------------------------------------------------------------------------
# Lenient mode — set PM_TELEMETRY_LENIENT=1 to downgrade unknown
# domain/category pairs from SchemaValidationError to a warning.
# Default is strict (empty string → False).
# Use only during experimental iteration; revert before production runs.
# ---------------------------------------------------------------------------
LENIENT_MODE: bool = os.getenv("PM_TELEMETRY_LENIENT", "").lower() in ("1", "true")

# ---------------------------------------------------------------------------
# Taxonomy registry
# ---------------------------------------------------------------------------

DOMAIN_TAXONOMY: dict[str, dict[str, list[str]]] = {
    "workflow": {
        "lifecycle": [
            "run_start", "run_end",
            "phase_start", "phase_end",
            "workflow_failed",
        ],
    },
    "decision": {
        "selection": [
            "option_selected", "option_rejected",
            "critique_generated", "conflict_detected",
            "thinking_recorded",
            "intent_review_completed", "intent_choice",
            "intent_proceed", "intent_reject",
            "decision_completed",
            "idea_loop_completed",
        ],
        "tradeoff": [
            "tradeoff_recorded", "confidence_penalty_applied",
            "council_approved", "council_rejected",
            "decision_graph_recorded",
        ],
    },
    "qa": {
        "validation": ["schema_mismatch", "validation_warning", "validation_passed", "product_qa_completed", "strategic_qa_completed", "validation_strategy_completed"],
        "patching":   ["patch_applied", "patch_failed"],
        "integrity":  [
            "system_integrity_alert", "fabricated_founder_evidence",
            "kernel_violation", "malformed_lineage", "invalid_escalation",
            "schema_violation",
        ],
        "escalation": ["escalation_triggered", "escalation_resolved"],
        "consistency": ["consistency_check_passed", "consistency_check_failed"],
    },
    "system": {
        "kernel": [
            "kernel_hash_verified", "kernel_hash_mismatch",
            "kernel_loaded", "kernel_tampered", "founder_override",
        ],
        "config": ["config_loaded", "config_missing"],
    },
    "patch": {
        "repair": ["partial_patch_applied", "repair_failed"],
    },
    "translation": {
        "sync": [
            "translation_generated", "translation_skipped",
            "translation_stale", "translation_failed",
        ],
    },
    "discovery": {
        "user": ["user_model_generated", "jtbd_extracted", "persona_defined"],
        "problem": ["problem_statement_created", "friction_identified"],
        "opportunity": ["opportunity_scored", "opportunity_prioritized", "pm_reconstruction_completed"],
    },
}

REQUIRED_FIELDS: tuple[str, ...] = (
    "schema_version",
    "event_id",
    "run_id",
    "timestamp",
    "phase",
    "domain",
    "category",
    "event_type",
)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class SchemaValidationError(ValueError):
    """Raised when an event does not satisfy the canonical schema."""


def validate_event(event: dict) -> None:
    """Strict validation. Raises SchemaValidationError on failure."""
    missing = [f for f in REQUIRED_FIELDS if f not in event]
    if missing:
        raise SchemaValidationError(
            f"Missing required fields: {missing}  event_id={event.get('event_id', '?')}"
        )
    if event["schema_version"] != SCHEMA_VERSION:
        raise SchemaValidationError(
            f"schema_version mismatch: expected {SCHEMA_VERSION!r}, "
            f"got {event['schema_version']!r}  event_id={event['event_id']}"
        )
    domain = event["domain"]
    if domain not in DOMAIN_TAXONOMY:
        if LENIENT_MODE:
            warnings.warn(
                f"Unregistered domain {domain!r} (LENIENT_MODE on; event will be written). "
                f"Valid: {list(DOMAIN_TAXONOMY)}",
                stacklevel=3,
            )
            return
        raise SchemaValidationError(
            f"Unknown domain {domain!r}. Valid: {list(DOMAIN_TAXONOMY)}"
        )
    category = event["category"]
    if category not in DOMAIN_TAXONOMY[domain]:
        if LENIENT_MODE:
            warnings.warn(
                f"Unregistered category {category!r} under domain {domain!r} "
                f"(LENIENT_MODE on; event will be written). "
                f"Valid: {list(DOMAIN_TAXONOMY[domain])}",
                stacklevel=3,
            )
            return
        raise SchemaValidationError(
            f"Unknown category {category!r} under domain {domain!r}. "
            f"Valid: {list(DOMAIN_TAXONOMY[domain])}"
        )
    # event_type: warn-only to allow forward extension without breaking callers.


def is_valid_event(event: dict) -> bool:
    try:
        validate_event(event)
        return True
    except SchemaValidationError:
        return False
