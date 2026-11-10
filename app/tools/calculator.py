"""Calculator tool (FR-27, NFR-5, D4).

Safe by design: the expression is parsed into a syntax tree with Python's
`ast` module and walked by our own code. Only the node types listed below
are allowed, so names, attributes, strings and calls to anything other than
the whitelisted math functions are rejected. Python's built-in evaluator is
never used.

All numbers are converted to float. After every step the result must be a
finite float, so inf, nan and complex numbers never reach the JSON response.
"""

import ast
import math
import operator

from app.tools.base import Tool, ToolError

INVALID = "Invalid expression"
MAX_EXPONENT = 1000
MAX_DEPTH = 20

BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
UNARY_OPERATORS = {ast.USub: operator.neg, ast.UAdd: operator.pos}
# Every function takes exactly one argument.
FUNCTIONS = {
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "log": math.log,  # natural logarithm
    "log10": math.log10,
    "exp": math.exp,
    "abs": abs,
    "round": round,
}
CONSTANTS = {"pi": math.pi, "e": math.e}


def run(expression: str) -> dict:
    expression = expression.replace("^", "**")  # S1:179: ^ means power
    try:
        tree = ast.parse(expression, mode="eval")
        return {"result": _evaluate(tree.body, depth=0)}
    except ToolError:
        raise
    except ZeroDivisionError:
        raise ToolError("Division by zero")
    except OverflowError:
        raise ToolError("Result too large")
    # SyntaxError: not valid Python syntax. ValueError: math domain errors
    # such as sqrt(-1). RecursionError: the parser's own nesting limit.
    except (SyntaxError, ValueError, RecursionError):
        raise ToolError(INVALID)


def _finite(value) -> float:
    """Every intermediate result must be a real, finite number."""
    if isinstance(value, complex):  # e.g. (-8) ** (1/3)
        raise ToolError(INVALID)
    value = float(value)  # OverflowError for a huge int, handled in run()
    if not math.isfinite(value):
        raise ToolError("Result too large")
    return value


def _evaluate(node: ast.AST, depth: int) -> float:
    if depth > MAX_DEPTH:
        raise ToolError(INVALID)
    depth += 1

    # A number. bool is excluded on purpose: in Python, True is also an int.
    if isinstance(node, ast.Constant):
        if type(node.value) not in (int, float):
            raise ToolError(INVALID)
        return _finite(node.value)

    if isinstance(node, ast.BinOp) and type(node.op) in BINARY_OPERATORS:
        left = _evaluate(node.left, depth)
        right = _evaluate(node.right, depth)
        if isinstance(node.op, ast.Pow) and abs(right) > MAX_EXPONENT:
            raise ToolError("Exponent too large")
        return _finite(BINARY_OPERATORS[type(node.op)](left, right))

    if isinstance(node, ast.UnaryOp) and type(node.op) in UNARY_OPERATORS:
        return _finite(UNARY_OPERATORS[type(node.op)](_evaluate(node.operand, depth)))

    if isinstance(node, ast.Name) and node.id in CONSTANTS:
        return CONSTANTS[node.id]

    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in FUNCTIONS
        and len(node.args) == 1
        and not node.keywords
    ):
        argument = _evaluate(node.args[0], depth)
        return _finite(FUNCTIONS[node.func.id](argument))

    # Anything else: other names, attributes, strings, lists, other calls...
    raise ToolError(INVALID)


TOOL = Tool(
    name="calculator",
    description=(
        "Evaluate a math expression. Use for ANY arithmetic, percentages or math "
        "functions, even trivial ones or ones you think have no answer (such as "
        "division by zero): the tool reports the error. Never calculate in your head."
    ),
    parameters={
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "Math expression, e.g. '2 + 2 * 3' or 'sqrt(144) + 5'",
                "maxLength": 200,
            }
        },
        "required": ["expression"],
    },
    run=run,
)
