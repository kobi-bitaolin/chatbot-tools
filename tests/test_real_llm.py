"""Real-LLM checks (T-13): AC-53..AC-56. Run in stage 5 with `pytest -m real_llm`.

These call the real Gemini API with the real tools, so they cost a little
and an answer can vary between runs. They are skipped when no key is set
(see tests/conftest.py), so the normal suite never needs one (NFR-3).
Each one checks the tools used and a key fact in the answer, not exact wording.
"""

import re

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.conftest import REAL_API_KEY

pytestmark = pytest.mark.real_llm


@pytest.fixture
def real_client(tmp_path):
    """The app with the real LLM client (no fake), its data in a temp folder."""
    settings = Settings(data_dir=tmp_path, gemini_api_key=REAL_API_KEY)
    with TestClient(create_app(settings)) as client:
        yield client


def new_conversation(client):
    return client.post("/conversations", json={}).json()["id"]


def ask(client, conversation_id, content):
    """Send one message; a real-LLM answer must never be an API error."""
    reply = client.post(f"/conversations/{conversation_id}/messages", json={"content": content})
    assert reply.status_code == 200, reply.text
    body = reply.json()
    return body["message"]["content"], [t["tool"] for t in body["tools_used"]]


def test_ac_53_real_calculator(real_client):
    """The request with all 5 declarations is accepted, and the tip is 12.75."""
    answer, tools = ask(real_client, new_conversation(real_client), "What's 15% tip on $85?")

    assert "calculator" in tools
    assert "12.75" in answer


def test_ac_54_real_two_tools(real_client):
    answer, tools = ask(
        real_client, new_conversation(real_client), "What's the weather and time in London?"
    )

    assert "weather" in tools
    assert "datetime" in tools


def test_ac_55_real_history_replay(real_client):
    """Three tool turns, then a question about the first: replay is accepted and used."""
    conversation = new_conversation(real_client)
    ask(real_client, conversation, "What is 15% of 85?")
    ask(real_client, conversation, "What's the weather in Paris?")
    ask(real_client, conversation, "What time is it in Tokyo?")

    answer, _ = ask(real_client, conversation, "What did you calculate earlier?")

    assert "12.75" in answer


def test_ac_56_real_database(real_client):
    answer, tools = ask(
        real_client, new_conversation(real_client), "How many orders were placed last month?"
    )

    assert "database_query" in tools
    assert re.search(r"\d+", answer)
