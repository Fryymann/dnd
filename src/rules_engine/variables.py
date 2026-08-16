"""Resolve one variable to a number for one character at one level."""

from __future__ import annotations

from typing import Any

from rules_engine.facts import CharacterFacts
from rules_engine.formula import evaluate_expression, referenced_names
from rules_engine.rules_file import RulesFile

# Variables whose `from` source is a dict rather than a scalar. A formula that
# references CLASS_LEVEL.rogue needs the whole dict of class levels so attribute
# access can resolve the `.rogue` key; CharacterFacts.read() would need a key up
# front to return a single int, which resolve() doesn't have at this point.
SUBSCRIPTABLE = {"CLASS_LEVEL"}


class UnknownVariable(ValueError):
    """Gate 2. Always names the variable."""


def resolve(
    name: str,
    rules: RulesFile,
    facts: CharacterFacts,
    picks: dict[str, int] | None = None,
    _seen: tuple[str, ...] = (),
) -> Any:
    picks = picks or {}

    if name in _seen:
        chain = " -> ".join([*_seen, name])
        raise UnknownVariable(f"circular variable reference: {chain}")

    if name in rules.picks:
        if name not in picks:
            raise UnknownVariable(f"pick {name!r} has no value on this binding")
        return picks[name]

    if name not in rules.variables:
        raise UnknownVariable(f"variable {name!r} is not declared in rules/{rules.edition}.toml")

    variable = rules.variables[name]

    try:
        kind = variable.kind
    except ValueError as exc:
        raise UnknownVariable(f"variable {name!r} declares no resolvable kind: {exc}") from exc

    seen = (*_seen, name)

    match kind:
        case "from":
            if name in SUBSCRIPTABLE:
                return facts.class_levels
            return facts.read(variable.source)
        case "table":
            if variable.table not in rules.tables:
                raise UnknownVariable(
                    f"variable {name!r} references undeclared table {variable.table!r}"
                )
            table = rules.tables[variable.table]
            index = resolve(table.index, rules, facts, picks, seen)
            position = int(index) - 1
            if not 0 <= position < len(table.values):
                raise UnknownVariable(
                    f"variable {name!r}: index {index} is out of range for table "
                    f"{variable.table!r} (levels 1-{len(table.values)})"
                )
            return table.values[position]
        case "steps":
            if variable.steps not in rules.steps:
                raise UnknownVariable(
                    f"variable {name!r} references undeclared steps {variable.steps!r}"
                )
            steps = rules.steps[variable.steps]
            index = resolve(steps.index, rules, facts, picks, seen)
            return steps.base + sum(1 for t in steps.thresholds if index >= t)
        case "formula":
            values = {
                dep: resolve(dep, rules, facts, picks, seen)
                for dep in referenced_names(variable.formula)
            }
            return evaluate_expression(variable.formula, values)

    raise UnknownVariable(f"variable {name!r} declares no resolvable kind")
