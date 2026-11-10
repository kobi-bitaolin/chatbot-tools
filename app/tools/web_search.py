"""Web search tool, mock version (FR-28, S1:183-190, G5).

Returns predefined results for queries that contain a known keyword, and an
empty list otherwise. No network and no API key are needed.
"""

import re

from app.tools.base import Tool

# keyword -> results. A query matches a keyword when it contains it as a word.
RESULTS = {
    "python": [
        {
            "title": "Welcome to Python.org",
            "snippet": "The official home of the Python programming language.",
            "url": "https://www.python.org/",
        },
        {
            "title": "The Python Tutorial",
            "snippet": "An informal introduction to the basic concepts and features of Python.",
            "url": "https://docs.python.org/3/tutorial/",
        },
    ],
    "fastapi": [
        {
            "title": "FastAPI",
            "snippet": "A modern, fast web framework for building APIs with Python, based on type hints.",
            "url": "https://fastapi.tiangolo.com/",
        },
    ],
    "docker": [
        {
            "title": "Docker Docs",
            "snippet": "Guides and references for building, sharing and running containers.",
            "url": "https://docs.docker.com/",
        },
    ],
    "sqlite": [
        {
            "title": "SQLite Home Page",
            "snippet": "SQLite is a small, fast, self-contained SQL database engine.",
            "url": "https://www.sqlite.org/",
        },
    ],
    "claude": [
        {
            "title": "Claude by Anthropic",
            "snippet": "Claude is an AI assistant made by Anthropic.",
            "url": "https://www.anthropic.com/claude",
        },
    ],
    "tokyo": [
        {
            "title": "Tokyo - Official Travel Guide",
            "snippet": "Things to do, places to visit and events in Tokyo, the capital of Japan.",
            "url": "https://www.gotokyo.org/en/",
        },
    ],
}


def run(query: str) -> dict:
    words = set(re.findall(r"[a-z0-9]+", query.lower()))
    results = []
    for keyword, items in RESULTS.items():  # fixed order, so output is repeatable
        if keyword in words:
            results.extend(items)
    return {"results": results}


TOOL = Tool(
    name="web_search",
    description="Search the web for current information. Returns titles, snippets and URLs.",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The search query", "maxLength": 300}
        },
        "required": ["query"],
    },
    run=run,
)
