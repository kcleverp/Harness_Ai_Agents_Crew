"""
paths.py — Single source of truth for all workspace and log directory constants.

All harness and workflow modules must import from here rather than recomputing
__file__-relative paths independently. This eliminates silent divergence when
the directory layout changes.

Constants only — no functions, no classes.
"""
import os

BASE_DIR      = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WORKSPACE_DIR = os.path.join(BASE_DIR, "workspace")
CURRENT_DIR   = os.path.join(WORKSPACE_DIR, "current")
ARCHIVE_DIR   = os.path.join(WORKSPACE_DIR, "archive")
LOG_DIR       = os.path.join(BASE_DIR, "logs")
PROJ_DIR      = os.path.join(LOG_DIR, "projections")
VIEW_DIR      = os.path.join(LOG_DIR, "views")
PROMPTS_DIR   = os.path.join(BASE_DIR, "prompts")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
CANONICAL_TRACE = os.path.join(LOG_DIR, "reasoning_trace.jsonl")
THINKING_TRACE  = os.path.join(LOG_DIR, "thinking_trace.jsonl")
SIGNALS_DIR     = os.path.join(WORKSPACE_DIR, "signals")
USER_DIR        = os.path.join(CURRENT_DIR, "user")
OPP_DIR         = os.path.join(CURRENT_DIR, "opportunity")
COGNITION_DIR   = os.path.join(CURRENT_DIR, "cognition")
