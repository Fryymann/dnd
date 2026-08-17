"""Evaluate an expression at every level so the runtime never does arithmetic."""

from __future__ import annotations

import math
from typing import Any

from rules_engine.facts import CharacterFacts
from rules_engine.formula import evaluate_expression, referenced_names
from rules_engine.rules_file import RulesFile
from rules_engine.variables import resolve

LEVELS = range(1, 21)


def _validate_picks(picks: dict[str, int]) -> None:
    """Reject any pick value that isn't a finite, non-bool int or float.

    Mirrors formula.py's `_validate_values`: a trust boundary validates on the way
    in rather than letting a bad pick travel until some downstream branch happens to
    catch it. Without this, a pick of `"dex"`, `None`, `[1, 2]` or `True` flows
    straight through `resolve` on the table and steps branches (neither of which
    validates its input at all) and is only caught, if at all, deep inside
    `evaluate_expression` on the formula branch — where the error names the formula
    rather than the pick that actually caused it.
    """
    for name, value in picks.items():
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ValueError(f"pick {name!r} is {type(value).__name__}, not a finite number")


def expand_expression(
    expression: str,
    rules: RulesFile,
    facts: CharacterFacts,
    picks: dict[str, int] | None = None,
) -> dict[int, int | float]:
    """Map every level 1-20 to the expression's value at that level."""
    picks = picks or {}
    _validate_picks(picks)

    names = referenced_names(expression)
    table: dict[int, Any] = {}
    for level in LEVELS:
        at = facts.at_level(level)
        values = {name: resolve(name, rules, at, picks) for name in names}
        table[level] = evaluate_expression(expression, values)
    return table
