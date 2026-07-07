"""
cognitive_parser.py — Extract <thinking> and <decision_graph> from LLM output.

Parsing failure never affects artifact parsing: callers strip cognitive blocks
first, then run existing _extract_*_meta / _parse_json_phase paths.
"""
import json
import re
from dataclasses import dataclass

THINKING_MAX_CHARS = 1000

_THINKING_RE = re.compile(r"<thinking>(.*?)</thinking>", re.DOTALL | re.IGNORECASE)
_GRAPH_RE = re.compile(r"<decision_graph>(.*?)</decision_graph>", re.DOTALL | re.IGNORECASE)


@dataclass
class PhaseCognitiveResult:
    thinking_text: str
    decision_graph: dict
    artifact_body: str


def extract_thinking(raw: str) -> str:
    match = _THINKING_RE.search(raw or "")
    return match.group(1).strip() if match else ""


def extract_decision_graph(raw: str) -> dict:
    match = _GRAPH_RE.search(raw or "")
    if not match:
        return {}
    text = match.group(1).strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def strip_cognitive_blocks(raw: str) -> str:
    text = _THINKING_RE.sub("", raw or "")
    text = _GRAPH_RE.sub("", text)
    return text.strip()


def truncate_thinking(text: str, max_len: int = THINKING_MAX_CHARS) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + "…"


def parse_phase_response(raw: str, phase_label: str = "") -> PhaseCognitiveResult:
    """Split LLM output into cognitive blocks and artifact body."""
    _ = phase_label  # reserved for future per-phase diagnostics
    thinking = truncate_thinking(extract_thinking(raw))
    graph = extract_decision_graph(raw)
    body = strip_cognitive_blocks(raw)
    return PhaseCognitiveResult(
        thinking_text=thinking,
        decision_graph=graph,
        artifact_body=body,
    )
