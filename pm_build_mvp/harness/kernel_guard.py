"""Founder Intent Kernel — loader, hash guard, and prompt injector.

Responsibilities:
- Load/create workspace/founder_kernel.json
- Compute and verify kernel hash across pipeline stages
- Inject an immutable guard block at the top of system prompts

Kernel integrity rules:
- Lower-tier models MUST NOT summarize, reinterpret, generalize, soften, or
  expand the kernel. Any output that violates this constraint is invalid.
- Fabricated founder evidence (evidence_type == founder_conviction that does
  NOT reference a real kernel key) is a system integrity violation.
"""

import hashlib
import json
import os

from harness.safe_file_tools import read_workspace_file, WORKSPACE_DIR

_KERNEL_PATH = "founder_kernel.json"
_KERNEL_ABS_PATH = os.path.join(WORKSPACE_DIR, _KERNEL_PATH)

_KERNEL_TEMPLATE: dict = {
    "core_thesis": [],
    "non_negotiables": [],
    "anti_patterns": [],
    "founder_convictions": [],
    "kernel_hash": "",
}

_GUARD_HEADER = """\
[Inviolable Founder Kernel]

You MUST preserve every item in this section verbatim.

You are STRICTLY PROHIBITED from:
- summarizing any kernel item
- reinterpreting any kernel item
- optimizing any kernel item
- generalizing any kernel item
- softening any kernel item
- expanding any kernel item

Any output that violates the above constraints is invalid and must be discarded.

"""

_GUARD_FOOTER = "\n[End Inviolable Founder Kernel]\n\n"


# ---------------------------------------------------------------------------
# Hash helpers
# ---------------------------------------------------------------------------

def _compute_hash(kernel_data: dict) -> str:
    """SHA-256 over the canonical JSON of the kernel (excluding the hash field)."""
    payload = {k: v for k, v in kernel_data.items() if k != "kernel_hash"}
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Load / create
# ---------------------------------------------------------------------------

def load_founder_kernel() -> dict:
    """Load founder_kernel.json.

    If the file is missing or invalid, write a blank template and return it.
    The caller is responsible for populating content before the pipeline starts.
    """
    raw = read_workspace_file(_KERNEL_PATH)

    if raw.startswith("Error:"):
        # File does not exist — write template and return it
        _write_kernel(_KERNEL_TEMPLATE)
        from harness.audit_hooks import log_pm_audit
        log_pm_audit(
            "KernelGuard | Status=TEMPLATE_CREATED | "
            "Message=founder_kernel.json did not exist; blank template written"
        )
        return dict(_KERNEL_TEMPLATE)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        from harness.audit_hooks import log_pm_audit
        log_pm_audit(f"KernelGuard | Status=PARSE_ERROR | Error={exc}")
        return dict(_KERNEL_TEMPLATE)

    # Ensure required keys exist
    for k, v in _KERNEL_TEMPLATE.items():
        if k not in data:
            data[k] = v

    return data


def _write_kernel(kernel_data: dict) -> None:
    payload = dict(kernel_data)
    payload["kernel_hash"] = _compute_hash(payload)
    os.makedirs(os.path.dirname(_KERNEL_ABS_PATH), exist_ok=True)
    with open(_KERNEL_ABS_PATH, "w", encoding="utf-8") as f:
        f.write(json.dumps(payload, indent=2, ensure_ascii=False))


def save_founder_kernel(kernel_data: dict) -> str:
    """Compute hash, persist to workspace/founder_kernel.json, and return the hash."""
    h = _compute_hash(kernel_data)
    kernel_data["kernel_hash"] = h
    os.makedirs(os.path.dirname(_KERNEL_ABS_PATH), exist_ok=True)
    with open(_KERNEL_ABS_PATH, "w", encoding="utf-8") as f:
        f.write(json.dumps(kernel_data, indent=2, ensure_ascii=False))
    return h


# ---------------------------------------------------------------------------
# Hash verification
# ---------------------------------------------------------------------------

def verify_kernel_hash(kernel_data: dict) -> bool:
    """Return True when the stored hash matches the computed hash."""
    stored = kernel_data.get("kernel_hash", "")
    return stored == _compute_hash(kernel_data)


def assert_kernel_integrity(kernel_data: dict, phase: str) -> None:
    """Raise RuntimeError (and log) when kernel hash is tampered between stages."""
    if not verify_kernel_hash(kernel_data):
        from harness.audit_hooks import log_pm_audit
        log_pm_audit(
            f"KernelGuard | Status=HASH_MISMATCH | Phase={phase} | "
            "Message=kernel_hash does not match computed hash — kernel may have been mutated"
        )
        raise RuntimeError(
            f"Founder Kernel integrity check failed at phase '{phase}'. "
            "Kernel hash mismatch — pipeline halted."
        )


# ---------------------------------------------------------------------------
# Prompt injection
# ---------------------------------------------------------------------------

def _format_kernel_block(kernel_data: dict) -> str:
    """Render kernel content as a readable text block for prompt injection."""
    lines = []
    for key in ("core_thesis", "non_negotiables", "anti_patterns", "founder_convictions"):
        items = kernel_data.get(key, [])
        if items:
            label = key.replace("_", " ").upper()
            lines.append(f"{label}:")
            for item in items:
                lines.append(f"  - {item}")
    return "\n".join(lines) if lines else "(Founder Kernel is empty — populate before running)"


def inject_kernel_guard(system_prompt: str, kernel_data: dict) -> str:
    """Prepend the immutable guard block + kernel content to a system prompt.

    This must be called immediately before a prompt is sent to any model.
    If kernel data is empty (all lists empty), a warn comment is prepended
    but no error is raised — callers should ensure the kernel is populated.
    """
    kernel_block = _format_kernel_block(kernel_data)
    guard = _GUARD_HEADER + kernel_block + _GUARD_FOOTER
    return guard + system_prompt


# ---------------------------------------------------------------------------
# Founder evidence validation
# ---------------------------------------------------------------------------

_VALID_KERNEL_KEYS = frozenset(
    {"core_thesis", "non_negotiables", "anti_patterns", "founder_convictions"}
)


def validate_founder_evidence_ref(source_ref: str, kernel_data: dict) -> bool:
    """Return True when source_ref points to a real key in the kernel.

    Expected source_ref format: 'kernel.<key>' or 'kernel.<key>[<index>]'.
    Any reference not following this format or pointing to a non-existent
    key/index is treated as fabricated and returns False.
    """
    if not source_ref.startswith("kernel."):
        return False

    remainder = source_ref[len("kernel."):]

    # Strip optional index notation: key[0]
    bracket_pos = remainder.find("[")
    if bracket_pos != -1:
        key = remainder[:bracket_pos]
        try:
            idx = int(remainder[bracket_pos + 1 : remainder.index("]")])
        except (ValueError, IndexError):
            return False
        if key not in _VALID_KERNEL_KEYS:
            return False
        items = kernel_data.get(key, [])
        return 0 <= idx < len(items)

    key = remainder
    if key not in _VALID_KERNEL_KEYS:
        return False
    return bool(kernel_data.get(key))
