"""Resolve one variable to a number for one character at one level."""

from __future__ import annotations

from typing import Any

from rules_engine.facts import CharacterFacts
from rules_engine.formula import evaluate_expression, referenced_names
from rules_engine.rules_file import RulesFile

# A `table` or `steps` variable indexes by a resolved character level. Levels 1-20
# are the only domain rules_file.py guarantees: every table's `values` list is
# required to have exactly 20 entries. Shared by both branches so the guarantee
# cannot drift apart between them again.
LEVEL_DOMAIN = range(1, 21)


class UnknownVariable(ValueError):
    """Gate 2. Always names the variable."""


def _validate_level_index(value: Any, *, name: str, section_kind: str, section_name: str) -> int:
    """Reject anything that isn't already an int level in 1-20.

    Mirrors formula.py's stance: a trust boundary validates on the way in rather
    than coercing. `int(value)` would silently accept `True` (as 1), `"3"`, `" 7 "`
    and `5.9` (truncated to 5) — all plausible-looking wrong numbers instead of
    errors.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise UnknownVariable(
            f"variable {name!r}: {section_kind} {section_name!r} index must be an int level, "
            f"got {type(value).__name__} ({value!r})"
        )
    if value not in LEVEL_DOMAIN:
        raise UnknownVariable(
            f"variable {name!r}: {section_kind} {section_name!r} index {value} is out of range "
            f"(levels 1-20)"
        )
    return value


def resolve(
    name: str,
    rules: RulesFile,
    facts: CharacterFacts,
    picks: dict[str, int] | None = None,
    _seen: tuple[str, ...] = (),
) -> int | float | dict[str, int]:
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
            try:
                if facts.is_container_path(variable.source):
                    return facts.read_container(variable.source)
                return facts.read(variable.source)
            except KeyError as exc:
                raise UnknownVariable(
                    f"variable {name!r} references unknown export path {variable.source!r}"
                ) from exc
        case "table":
            if variable.table not in rules.tables:
                raise UnknownVariable(
                    f"variable {name!r} references undeclared table {variable.table!r}"
                )
            table = rules.tables[variable.table]
            index = resolve(table.index, rules, facts, picks, seen)
            index = _validate_level_index(
                index, name=name, section_kind="table", section_name=variable.table
            )
            return table.values[index - 1]
        case "steps":
            if variable.steps not in rules.steps:
                raise UnknownVariable(
                    f"variable {name!r} references undeclared steps {variable.steps!r}"
                )
            steps = rules.steps[variable.steps]
            index = resolve(steps.index, rules, facts, picks, seen)
            index = _validate_level_index(
                index, name=name, section_kind="steps", section_name=variable.steps
            )
            return steps.base + sum(1 for t in steps.thresholds if index >= t)
        case "formula":
            values = {
                dep: resolve(dep, rules, facts, picks, seen)
                for dep in referenced_names(variable.formula)
            }
            return evaluate_expression(variable.formula, values)

    raise UnknownVariable(f"variable {name!r} declares no resolvable kind")
