"""Web search and weather mock tests (T-5): FR-28, FR-29."""

import random

from app.tools import weather, web_search

CONDITIONS = {"sunny", "cloudy", "rainy", "snowy", "windy", "foggy"}


def test_ac_34_web_search():
    found = web_search.run(query="python")["results"]
    assert len(found) >= 1
    for item in found:
        assert set(item) == {"title", "snippet", "url"}
        assert all(isinstance(value, str) and value for value in item.values())

    assert web_search.run(query="zzqx") == {"results": []}


def test_fr_28_matches_words_in_any_case():
    assert web_search.run(query="Best PYTHON tutorial?")["results"] == web_search.run(
        query="python"
    )["results"]
    # A keyword inside another word doesn't count ("pythonic" is not "python").
    assert web_search.run(query="pythonic") == {"results": []}


def test_ac_35_weather():
    # Same seed, fresh generators: the same output.
    first = weather.run(location="Tokyo", rng=random.Random(42))
    second = weather.run(location="Tokyo", rng=random.Random(42))
    assert first == second
    assert first["location"] == "Tokyo"

    rng = random.Random(42)
    for _ in range(100):
        result = weather.run(location="Paris", rng=rng)
        assert set(result) == {"location", "temperature", "condition", "humidity"}
        assert type(result["temperature"]) is int and -30 <= result["temperature"] <= 45
        assert result["condition"] in CONDITIONS
        assert type(result["humidity"]) is int and 0 <= result["humidity"] <= 100

    # The output is a bare number, so the LLM learns the unit from the description (spec v0.8).
    assert "°C" in weather.TOOL.description
