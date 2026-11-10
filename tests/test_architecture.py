"""Separation of concerns (NFR-12, AC-59): the import rules of architecture §2.1.

Every file in app/ is parsed with Python's `ast` module (nothing is run), and
each import is checked against the rule of the layer the file belongs to.
"""

import ast
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent / "app"

# Allowed for now, removed when its task fixes the leak.
KNOWN_EXCEPTIONS = {
    ("api/routes.py", "app.models"),  # T-8 moves the message mapping into schemas.py
}


def imports_of(source: str) -> list[tuple[str, str | None]]:
    """(module, imported name) pairs. `from app import models` gives ("app.models", None)."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found += [(alias.name, None) for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                if module == "app":
                    found.append((f"app.{alias.name}", None))
                else:
                    found.append((module, alias.name))
    return found


def top(module: str) -> str:
    return module.split(".")[0]


def is_under(module: str, package: str) -> bool:
    return module == package or module.startswith(package + ".")


def is_llm_sdk(module: str, name: str | None) -> bool:
    """`import google.genai`, `from google.genai import types` and `from google import genai`."""
    return is_under(module, "google.genai") or (module == "google" and name == "genai")


def violations(path: str, source: str) -> list[str]:
    """The broken rules for one file. `path` is relative to app/, with forward slashes."""
    layer = path.split("/")[0] if "/" in path else ""
    problems = []
    for module, name in imports_of(source):
        if (path, module) in KNOWN_EXCEPTIONS:
            continue
        where = f"{path}: {module}" + (f".{name}" if name else "")

        if is_llm_sdk(module, name) and layer != "llm":
            problems.append(f"{where} (only app/llm may import the Gemini SDK)")
        if layer == "tools":
            allowed = (
                top(module) in sys.stdlib_module_names
                or top(module) == "jsonschema"
                or is_under(module, "app.tools")
            )
            if not allowed:
                problems.append(f"{where} (tools import only stdlib, jsonschema, app.tools)")
        if layer == "services" and top(module) == "fastapi":
            problems.append(f"{where} (services must not know about HTTP)")
        if layer == "llm" and is_under(module, "app.config"):
            problems.append(f"{where} (the LLM client gets plain values, not Settings)")
        if layer == "api":
            if top(module) == "sqlalchemy" and (module, name) != ("sqlalchemy.orm", "Session"):
                problems.append(f"{where} (routes don't query the database)")
            if is_under(module, "app.models"):
                problems.append(f"{where} (routes don't use DB models)")
    return problems


def test_ac_59_layer_imports():
    problems = []
    for file in sorted(APP_DIR.rglob("*.py")):
        path = file.relative_to(APP_DIR).as_posix()
        problems += violations(path, file.read_text(encoding="utf-8"))
    assert problems == []


def test_ac_59_checker_catches_violations():
    """The checker itself must work, or the test above would pass for nothing."""
    assert violations("tools/x.py", "from app.db import Base")
    assert violations("tools/x.py", "import requests")
    assert violations("services/x.py", "from fastapi import Request")
    assert violations("services/x.py", "from google import genai")
    assert violations("services/x.py", "from google.genai import types")
    assert violations("api/x.py", "import google.genai")
    assert violations("llm/x.py", "from app.config import Settings")
    assert violations("api/x.py", "from sqlalchemy import select")
    assert violations("api/x.py", "from app import models")
    assert violations("api/x.py", "from app.models import Conversation")
    # Allowed imports pass.
    assert violations("tools/x.py", "import math\nfrom app.tools.base import ToolError") == []
    assert violations("api/x.py", "from sqlalchemy.orm import Session") == []
    assert violations("llm/x.py", "from google import genai") == []
    assert violations("llm/x.py", "from google.genai import errors, types") == []
