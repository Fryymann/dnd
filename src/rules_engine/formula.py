"""Arithmetic over a whitelisted AST. Formulas are untrusted input."""

from __future__ import annotations

import ast
import math
from typing import Any

MAX_EXPRESSION_LENGTH = 500


class FormulaError(ValueError):
    """A formula failed to parse or evaluate. Carries the offending expression.

    Subclasses ValueError so existing `except ValueError` / `match="not allowed"`
    callers keep working. NameError (undefined variable) stays a separate case —
    it is not a FormulaError — and MemoryError is never wrapped into one.
    """

    def __init__(self, message: str, expression: str) -> None:
        super().__init__(message)
        self.expression = expression


FUNCTIONS = {"ceil": math.ceil, "floor": math.floor, "min": min, "max": max}

ALLOWED_NODES = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    # ast.Mod and ast.FloorDiv are deliberately absent: no rules formula uses % or
    # //, and each is a second ZeroDivisionError surface (plus, for FloorDiv on
    # large ints, a quadratic big-int division path) for a feature nobody asked for.
    #
    # ast.Pow is deliberately absent. `9**9**9` is eight characters that pass every
    # other check and then hang the process on CPython's unbounded bigint pow — a
    # trivial denial of service against a Cloud Function evaluating authored formulas.
    # No D&D formula needs exponentiation.
    ast.USub,
    # ast.UAdd is deliberately absent: `+A` does nothing, so there is no formula
    # that needs it and no reason to carry the extra whitelist surface.
    ast.Constant,
    ast.Name,
    ast.Load,
    ast.Call,
    ast.Attribute,
)


def _parse(expression: str) -> ast.Expression:
    if len(expression) > MAX_EXPRESSION_LENGTH:
        raise FormulaError(
            f"formula exceeds {MAX_EXPRESSION_LENGTH} characters ({len(expression)} found)",
            expression,
        )
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        # IndentationError is a SyntaxError subclass, so this covers both.
        raise FormulaError(f"formula is not valid syntax: {expression!r}", expression) from exc

    # Track which Name nodes are the callee of a Call (e.g. `ceil` in `ceil(A)`) so a
    # function name can be told apart from the same identifier used as a bare
    # variable (`ceil + 1`). ast.walk is breadth-first, so a Call is always visited
    # before its own `func` child, meaning the id is recorded before it matters.
    call_func_ids: set[int] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            call_func_ids.add(id(node.func))
        if not isinstance(node, ALLOWED_NODES):
            raise FormulaError(
                f"{type(node).__name__} is not allowed in a formula: {expression!r}", expression
            )
        if isinstance(node, ast.Call) and (
            not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS
        ):
            raise FormulaError(
                f"only {sorted(FUNCTIONS)} may be called, not allowed: {expression!r}", expression
            )
        if isinstance(node, ast.Name) and node.id in FUNCTIONS and id(node) not in call_func_ids:
            raise FormulaError(
                f"{node.id!r} is a function name, not allowed as a variable: {expression!r}",
                expression,
            )
        if isinstance(node, ast.Attribute) and not isinstance(node.value, ast.Name):
            raise FormulaError(
                f"only VARIABLE.key access is allowed, not allowed: {expression!r}", expression
            )
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
                # bool is a subclass of int, so True would otherwise pass as a
                # numeric literal and `True + 1` would quietly evaluate to 2.
                raise FormulaError(
                    f"only numeric literals are allowed, not allowed: {expression!r}", expression
                )
            if isinstance(node.value, float) and not math.isfinite(node.value):
                # `1e400` is five characters that parse to `inf`. Left in, it (or an
                # `inf - inf` built from two of them) survives to a result that
                # `json.dumps` renders as the bare token `NaN` — invalid JSON.
                raise FormulaError(
                    f"only finite numeric literals are allowed, not allowed: {expression!r}",
                    expression,
                )
    return tree


def referenced_names(expression: str) -> set[str]:
    """Every variable name a formula depends on. Attribute accesses collapse to their
    base name."""
    tree = _parse(expression)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            names.add(node.value.id)
        elif isinstance(node, ast.Name) and node.id not in FUNCTIONS:
            names.add(node.id)
    return names


def evaluate_expression(expression: str, values: dict[str, Any]) -> int | float:
    tree = _parse(expression)

    def visit(node: ast.AST) -> Any:
        match node:
            case ast.Expression():
                return visit(node.body)
            case ast.Constant():
                return node.value
            case ast.Name():
                if node.id in values:
                    return values[node.id]
                raise NameError(f"formula references undefined variable {node.id!r}")
            case ast.Attribute():
                container = visit(node.value)
                if not isinstance(container, dict):
                    raise FormulaError(
                        f"{node.value.id} does not support attribute access: {expression!r}",
                        expression,
                    )
                if node.attr not in container:
                    # A missing key is not a value of zero — it is a fact the
                    # evaluator does not have. Silently defaulting here once made a
                    # typo'd or unbound class name (`CLASS_LEVEL.rouge`, or a class
                    # the character doesn't have) render as 0, which is a plausible
                    # value for most of these variables and therefore invisible.
                    raise FormulaError(
                        f"{node.value.id}.{node.attr} is not defined: {expression!r}", expression
                    )
                return container[node.attr]
            case ast.Call():
                return FUNCTIONS[node.func.id](*[visit(a) for a in node.args])
            case ast.UnaryOp():
                # ast.UAdd is not in ALLOWED_NODES, so node.op is always USub here.
                return -visit(node.operand)
            case ast.BinOp():
                left, right = visit(node.left), visit(node.right)
                match node.op:
                    case ast.Add():
                        return left + right
                    case ast.Sub():
                        return left - right
                    case ast.Mult():
                        return left * right
                    case ast.Div():
                        return left / right
        raise FormulaError(f"{type(node).__name__} is not allowed in a formula", expression)

    try:
        result = visit(tree)
    except (ZeroDivisionError, TypeError, OverflowError, RecursionError) as exc:
        # MemoryError is deliberately not caught here: it signals machine state
        # rather than bad input, and wrapping it risks allocating the replacement
        # exception's message in a process that may not be able to spare it.
        raise FormulaError(
            f"formula could not be evaluated: {expression!r} ({exc})", expression
        ) from exc

    if not isinstance(result, (int, float)) or not math.isfinite(result):
        # Catches what a non-finite *literal* can't: e.g. two huge caller-supplied
        # values whose product overflows to inf, or a caller-supplied string that
        # slips through arithmetic (`"5" * 3` == `"555"`, no exception raised).
        raise FormulaError(
            f"formula did not evaluate to a finite number: {expression!r}", expression
        )
    if abs(result) >= 10**15:
        raise FormulaError(f"formula result is too large: {expression!r}", expression)
    return result
