"""Arithmetic over a whitelisted AST. Formulas are untrusted input."""

from __future__ import annotations

import ast
import math
from typing import Any

FUNCTIONS = {"ceil": math.ceil, "floor": math.floor, "min": min, "max": max}

ALLOWED_NODES = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
    ast.USub,
    ast.UAdd,
    ast.Constant,
    ast.Name,
    ast.Load,
    ast.Call,
    ast.Attribute,
)


def _parse(expression: str) -> ast.Expression:
    tree = ast.parse(expression, mode="eval")
    for node in ast.walk(tree):
        # ValueError (not TypeError) is deliberate here: these guard the whitelist that is
        # the security boundary for untrusted formulas, and callers/tests key off ValueError
        # with a "not allowed" message rather than the node's Python type.
        if not isinstance(node, ALLOWED_NODES):
            raise ValueError(  # noqa: TRY004
                f"{type(node).__name__} is not allowed in a formula: {expression!r}"
            )
        if isinstance(node, ast.Call) and (
            not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS
        ):
            raise ValueError(
                f"only {sorted(FUNCTIONS)} may be called, not allowed: {expression!r}"
            )
        if isinstance(node, ast.Attribute) and not isinstance(node.value, ast.Name):
            raise ValueError(  # noqa: TRY004
                f"only VARIABLE.key access is allowed, not allowed: {expression!r}"
            )
        if isinstance(node, ast.Constant) and not isinstance(node.value, (int, float)):
            raise ValueError(  # noqa: TRY004
                f"only numeric literals are allowed, not allowed: {expression!r}"
            )
    return tree


def referenced_names(expression: str) -> set[str]:
    """Every variable name a formula depends on. Subscripts collapse to their base name."""
    tree = _parse(expression)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            names.add(node.value.id)
        elif isinstance(node, ast.Name) and node.id not in FUNCTIONS:
            names.add(node.id)
    return names


def evaluate_expression(expression: str, values: dict[str, Any]) -> float:
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
                    raise ValueError(f"{node.value.id} is not subscriptable")  # noqa: TRY004
                return container.get(node.attr, 0)
            case ast.Call():
                return FUNCTIONS[node.func.id](*[visit(a) for a in node.args])
            case ast.UnaryOp():
                operand = visit(node.operand)
                return -operand if isinstance(node.op, ast.USub) else +operand
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
                    case ast.FloorDiv():
                        return left // right
                    case ast.Mod():
                        return left % right
                    case ast.Pow():
                        return left**right
        raise ValueError(f"{type(node).__name__} is not allowed in a formula")

    return visit(tree)
