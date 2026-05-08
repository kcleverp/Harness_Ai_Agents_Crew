"""
telemetry_schema.py — Canonical event schema and domain taxonomy.

Schema version: v1

Design contract:
  - Event meaning is declared by the event itself via domain/category/event_type.
  - Projections read domain/category/event_type directly; they never infer meaning
    from phase names.
  - canonical stream (reasoning_trace.jsonl) is append-only and immutable.
  - schema_version is required on every event for forward-compatible projection logic.
  - related_event_ids is reserved (default []) for future DAG lineage.

Domain taxonomy  (domain → category → event_type):
  workflow   / lifecycle    → run_start, run_end, phase_start, phase_end, workflow_failed
  decision   / selection    → option_selected, option_rejected, critique_generated, conflict_detected
             / tradeoff     → tradeoff_recorded, confidence_penalty_applied,
                              council_approved, council_rejected
  qa         / validation   → schema_mismatch, validation_warning, validation_passed
             / patching     → patch_applied, patch_failed
             / integrity    → system_integrity_alert, fabricated_founder_evidence,
                              kernel_violation, malformed_lineage, invalid_escalation
             / escalation   → escalation_triggered, escalation_resolved
             / consistency  → consistency_check_passed, consistency_check_failed
  system     / kernel       → kernel_hash_verified, kernel_hash_mismatch, kernel_loaded,
                              kernel_tampered, founder_override
             / config       → config_loaded, config_missing
  patch      / repair       → partial_patch_applied, repair_failed
  translation/ sync         → translation_generated, translation_skipped,
                              translation_stale, translation_failed
"""

from __future__ import annotations

SCHEMA_VERSION = "v1"

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
        ],
        "tradeoff": [
            "tradeoff_recorded", "confidence_penalty_applied",
            "council_approved", "council_rejected",
        ],
    },
    "qa": {
        "validation": ["schema_mismatch", "validation_warning", "validation_passed"],
        "patching":   ["patch_applied", "patch_failed"],
        "integrity":  [
            "system_integrity_alert", "fabricated_founder_evidence",
            "kernel_violation", "malformed_lineage", "invalid_escalation",
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
        raise SchemaValidationError(
            f"Unknown domain {domain!r}. Valid: {list(DOMAIN_TAXONOMY)}"
        )
    category = event["category"]
    if category not in DOMAIN_TAXONOMY[domain]:
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


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

def build_event(
    *,
    run_id: str,
    phase: str,
    domain: str,
    category: str,
    event_type: str,
    event_id: str,
    timestamp: str,
    parent_event_id: str | None = None,
    related_event_ids: list[str] | None = None,
    artifact: str | None = None,
    details: dict | None = None,
) -> dict:
    """Construct and validate a canonical event record."""
    record = {
        "schema_version": SCHEMA_VERSION,
        "event_id": event_id,
        "parent_event_id": parent_event_id,
        "related_event_ids": related_event_ids if related_event_ids is not None else [],
        "run_id": run_id,
        "phase": phase,
        "domain": domain,
        "category": category,
        "event_type": event_type,
        "artifact": artifact,
        "timestamp": timestamp,
        "details": details or {},
    }
    validate_event(record)
    return record
