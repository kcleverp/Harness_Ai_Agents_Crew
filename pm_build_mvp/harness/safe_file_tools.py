import os
import json
from crewai.tools import tool

WORKSPACE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../workspace"))
CURRENT_DIR = os.path.abspath(os.path.join(WORKSPACE_DIR, "current"))
ALLOWED_EXTENSIONS = (".md", ".json")

def _normalize_under_workspace(relative_path: str) -> str:
    return os.path.abspath(os.path.join(WORKSPACE_DIR, relative_path))

def _is_inside(base_dir: str, target_path: str) -> bool:
    try:
        return os.path.commonpath([base_dir, target_path]) == base_dir
    except ValueError:
        return False

def _is_allowed_extension(target_path: str) -> bool:
    return target_path.endswith(ALLOWED_EXTENSIONS)

def is_safe_read_path(relative_path: str) -> tuple[bool, str]:
    abs_target = _normalize_under_workspace(relative_path)
    if not _is_inside(WORKSPACE_DIR, abs_target):
        return False, "Error: Path traversal detected (outside workspace)."
    if not _is_allowed_extension(abs_target):
        return False, "Error: Invalid extension. Only .md/.json allowed."
    return True, abs_target

def is_safe_write_path(relative_path: str) -> tuple[bool, str]:
    abs_target = _normalize_under_workspace(relative_path)
    if not _is_inside(CURRENT_DIR, abs_target):
        return False, "Error: Write is allowed only inside workspace/current/."
    if not _is_allowed_extension(abs_target):
        return False, "Error: Invalid extension. Only .md/.json allowed."
    return True, abs_target

def read_workspace_file(file_path: str) -> str:
    """Plain Python function for direct calls. Reads a .md or .json file from workspace/."""
    ok, resolved = is_safe_read_path(file_path)
    if not ok:
        return resolved
    if not os.path.exists(resolved):
        return f"Error: File {file_path} not found."
    with open(resolved, "r", encoding="utf-8") as f:
        return f.read()

def write_workspace_file(file_path: str, content: str) -> str:
    """Plain Python function for direct calls. Writes to workspace/current/ only."""
    ok, resolved = is_safe_write_path(file_path)
    if not ok:
        return resolved

    if resolved.endswith(".json"):
        cleaned = content.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        try:
            parsed = json.loads(cleaned)
            content = json.dumps(parsed, indent=2, ensure_ascii=False)
        except json.JSONDecodeError as e:
            return f"Error: Invalid JSON format. {str(e)}"

    os.makedirs(os.path.dirname(resolved), exist_ok=True)
    with open(resolved, "w", encoding="utf-8") as f:
        f.write(content)
    return f"Success: Saved {file_path}"

def patch_workspace_json(file_path: str, key_path: str, new_value_json: str) -> str:
    """Plain Python function for direct calls. Patches a specific field in a JSON file."""
    ok, resolved = is_safe_write_path(file_path)
    if not ok:
        return f"Error[INVALID_PATH]: {resolved}"
    if not os.path.exists(resolved):
        return "Error[FILE_NOT_FOUND]: File not found."

    try:
        new_value = json.loads(new_value_json)
    except json.JSONDecodeError as e:
        return f"Error[INVALID_JSON_VALUE]: {str(e)}"

    try:
        with open(resolved, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return f"Error[INVALID_JSON_FILE]: {str(e)}"

    try:
        keys = key_path.split(".")
        current = data
        for k in keys[:-1]:
            if isinstance(current, list):
                if not k.isdigit():
                    return f"Error[TYPE_MISMATCH]: Expected list index at '{k}'."
                idx = int(k)
                if idx < 0 or idx >= len(current):
                    return f"Error[INDEX_OUT_OF_RANGE]: {idx}"
                current = current[idx]
            elif isinstance(current, dict):
                if k not in current:
                    return f"Error[KEY_NOT_FOUND]: {k}"
                current = current[k]
            else:
                return "Error[TYPE_MISMATCH]: Intermediate node is not dict/list."

        last_key = keys[-1]
        if isinstance(current, list):
            if not last_key.isdigit():
                return f"Error[TYPE_MISMATCH]: Expected final list index at '{last_key}'."
            idx = int(last_key)
            if idx < 0 or idx >= len(current):
                return f"Error[INDEX_OUT_OF_RANGE]: {idx}"
            current[idx] = new_value
        elif isinstance(current, dict):
            current[last_key] = new_value
        else:
            return "Error[TYPE_MISMATCH]: Target node is not dict/list."

        with open(resolved, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return f"Success: Patched '{key_path}' in {file_path}"

    except Exception as e:
        return f"Error[UNKNOWN]: {str(e)}"


# --- @tool wrappers: pass these to Agent(tools=[...]) only, do not call directly ---

@tool("Safe File Reader Tool")
def safe_read(file_path: str) -> str:
    """Reads a .md or .json file safely from workspace/. Provide relative path like current/handoff_to_dev.json."""
    return read_workspace_file(file_path)

@tool("Safe File Writer Tool")
def safe_write(file_path: str, content: str) -> str:
    """Writes content strictly to workspace/current/ for .md/.json files."""
    return write_workspace_file(file_path, content)

@tool("Apply Partial JSON Patch Tool")
def apply_partial_patch(file_path: str, key_path: str, new_value_json: str) -> str:
    """
    Updates a specific field in a JSON file inside workspace/current/ without rewriting the whole file.
    Returns structured error codes for patch diagnostics.
    """
    return patch_workspace_json(file_path, key_path, new_value_json)
