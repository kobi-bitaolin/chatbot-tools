"""Calculator tool tests (T-4): FR-27, NFR-5."""

import json
import math
import re
from pathlib import Path

import pytest

from app.tools import calculator
from app.tools.base import ToolError


def error_of(expression: str) -> str:
    with pytest.raises(ToolError) as caught:
        calculator.run(expression=expression)
    return str(caught.value)


def test_ac_31_calculator_examples():
    assert calculator.run(expression="2 + 2") == {"result": 4.0}
    assert calculator.run(expression="sqrt(16)") == {"result": 4.0}
    assert calculator.run(expression="sin(3.14159/2)")["result"] == pytest.approx(1.0, abs=1e-5)
    assert calculator.run(expression="100 * (1 + 0.05)^10")["result"] == pytest.approx(
        162.889, abs=0.001
    )
    assert calculator.run(expression="sqrt(144) + 5") == {"result": 17.0}


def test_fr_27_results_are_floats():
    # Every number is converted to float, so results are always floats.
    for expression in ["2 + 2", "7 % 3", "-5", "abs(-3)", "round(2.6)", "pi", "e"]:
        assert type(calculator.run(expression=expression)["result"]) is float, expression


@pytest.mark.parametrize(
    ("expression", "error"),
    [
        ("1/0", "Division by zero"),
        ("5 % 0", "Division by zero"),
        ("2 +", "Invalid expression"),
        ("sqrt(-1)", "Invalid expression"),
        ("log(0)", "Invalid expression"),
        ("sqrt(1, 2)", "Invalid expression"),
        ("9**9**9", "Exponent too large"),
        ("10.0**400", "Result too large"),
        ("1e999", "Result too large"),
        ("1e308*10", "Result too large"),
        ("((2**1000)**1000)**1000", "Result too large"),
    ],
)
def test_ac_32_calculator_errors(expression, error):
    assert error_of(expression) == error


def test_ac_32_results_are_json_safe():
    # No result may be inf or nan: the API's JSON response would break.
    for expression in ["1e308 + 1e308", "exp(1000)", "2**1000 * 2**1000"]:
        try:
            result = calculator.run(expression=expression)
        except ToolError:
            continue
        assert math.isfinite(result["result"])
        json.dumps(result, allow_nan=False)


def test_fr_27_complex_results_are_invalid():
    # Python returns a complex number for a negative base and a fractional power.
    assert error_of("(-8)^(1/3)") == "Invalid expression"


@pytest.mark.parametrize(
    "expression",
    ["__import__('os')", "().__class__", "open('x')", "a+1", "True + 1", "'a' * 3", "[1, 2]"],
)
def test_ac_33_calculator_security(expression):
    assert error_of(expression) == "Invalid expression"


def test_ac_33_no_eval_or_exec_in_source():
    source = Path(calculator.__file__).read_text(encoding="utf-8")
    assert not re.search(r"\b(eval|exec)\(", source)
    # The 201-character limit is the tool's JSON Schema (maxLength 200), which
    # the executor checks; that part of AC-33 is tested in T-11.


def test_nfr_5_nesting_limit():
    assert calculator.run(expression="-" * 20 + "1") == {"result": 1.0}  # depth 20 is fine
    assert error_of("-" * 30 + "1") == "Invalid expression"
