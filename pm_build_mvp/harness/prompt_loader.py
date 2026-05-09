import os

_PROMPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../prompts"))
_TEMPLATES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../templates"))

_cache: dict[str, str] = {}


def load_prompt(name: str) -> str:
    """Load a prompt file from prompts/{name}.md.

    Results are cached per process — each file is read exactly once.
    Raises FileNotFoundError if the prompt file does not exist.
    """
    if name in _cache:
        return _cache[name]
    path = os.path.join(_PROMPTS_DIR, f"{name}.md")
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Prompt file not found: {path}\n"
            f"Expected a file named '{name}.md' inside {_PROMPTS_DIR}"
        )
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    _cache[name] = content
    return content


def load_template(name: str) -> str:
    """Load a template file from templates/{name}.

    Results are cached per process.
    Raises FileNotFoundError if the template file does not exist.
    """
    if name in _cache:
        return _cache[name]
    path = os.path.join(_TEMPLATES_DIR, name)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Template file not found: {path}\n"
            f"Expected a file named '{name}' inside {_TEMPLATES_DIR}"
        )
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    _cache[name] = content
    return content
