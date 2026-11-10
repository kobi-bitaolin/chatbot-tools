"""Weather tool, mock version (FR-29, S1:192-199, G5).

Returns random but realistic weather. The random generator is a parameter,
so tests pass `random.Random(42)` and always get the same values.
"""

import random

CONDITIONS = ["sunny", "cloudy", "rainy", "snowy", "windy", "foggy"]
_default_rng = random.Random()


def run(location: str, rng: random.Random = _default_rng) -> dict:
    condition = rng.choice(CONDITIONS)
    # Keep the values believable: snow only when it's cold,
    # high humidity with rain and fog. Ranges: -30..45 °C, 0..100 %.
    if condition == "snowy":
        temperature = rng.randint(-30, 2)
    else:
        temperature = rng.randint(-10, 45)
    if condition in ("rainy", "foggy"):
        humidity = rng.randint(70, 100)
    else:
        humidity = rng.randint(20, 90)
    return {
        "location": location.strip(),
        "temperature": temperature,
        "condition": condition,
        "humidity": humidity,
    }
