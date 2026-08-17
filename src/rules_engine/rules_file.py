"""Load a rules/<edition>.toml into a validated in-memory contract."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

KINDS = ("table", "steps", "formula", "from")


@dataclass(frozen=True)
class Variable:
    name: str
    description: str = ""
    table: str | None = None
    steps: str | None = None
    formula: str | None = None
    source: str | None = None  # the TOML key is `from`, which is a Python keyword

    @property
    def kind(self) -> str:
        if self.table:
            return "table"
        if self.steps:
            return "steps"
        if self.formula:
            return "formula"
        if self.source:
            return "from"
        raise ValueError(f"variable {self.name}: declares none of {KINDS}")


@dataclass(frozen=True)
class Table:
    index: str
    values: list[int]


@dataclass(frozen=True)
class Steps:
    index: str
    base: int
    thresholds: list[int]


@dataclass(frozen=True)
class Pick:
    name: str
    description: str = ""
    required_on: str = "binding"


@dataclass(frozen=True)
class RulesFile:
    # frozen=True only blocks reassigning these fields (`rules.edition = ...`); the
    # dicts below are still mutable in place (`rules.variables["X"] = ...` works fine),
    # so don't assume this is safe to share mutably across Cloud Function invocations.
    edition: str
    verified: bool
    tables: dict[str, Table] = field(default_factory=dict)
    steps: dict[str, Steps] = field(default_factory=dict)
    variables: dict[str, Variable] = field(default_factory=dict)
    picks: dict[str, Pick] = field(default_factory=dict)


def _require(body: dict, key: str, section: str, path: Path):
    try:
        return body[key]
    except KeyError:
        raise ValueError(f"{path}: [{section}] missing required key '{key}'") from None


def load_rules(path: str | Path) -> RulesFile:
    path = Path(path)
    raw = tomllib.loads(path.read_text())

    meta = raw.get("meta", {})
    edition = _require(meta, "edition", "meta", path)
    verified = _require(meta, "verified", "meta", path)

    variables: dict[str, Variable] = {}
    for name, body in raw.get("variables", {}).items():
        declared = [k for k in KINDS if k in body]
        if len(declared) != 1:
            raise ValueError(
                f"variable {name}: must declare exactly one of {KINDS}, found {declared or 'none'}"
            )
        variables[name] = Variable(
            name=name,
            description=body.get("description", ""),
            table=body.get("table"),
            steps=body.get("steps"),
            formula=body.get("formula"),
            source=body.get("from"),
        )

    tables: dict[str, Table] = {}
    for k, v in raw.get("tables", {}).items():
        section = f"tables.{k}"
        index = _require(v, "index", section, path)
        values = _require(v, "values", section, path)
        if len(values) != 20:
            raise ValueError(
                f"{path}: [{section}] values must have exactly 20 entries (levels 1-20), "
                f"found {len(values)}"
            )
        if any(isinstance(x, bool) or not isinstance(x, int) for x in values):
            raise ValueError(f"{path}: [{section}] values must all be integers, found {values}")
        tables[k] = Table(index=index, values=values)

    steps: dict[str, Steps] = {}
    for k, v in raw.get("steps", {}).items():
        section = f"steps.{k}"
        index = _require(v, "index", section, path)
        base = _require(v, "base", section, path)
        thresholds = _require(v, "thresholds", section, path)
        if len(thresholds) != len(set(thresholds)):
            raise ValueError(
                f"{path}: [{section}] thresholds must not contain duplicates, found {thresholds}"
            )
        steps[k] = Steps(index=index, base=base, thresholds=thresholds)

    picks = {
        k: Pick(
            name=k,
            description=v.get("description", ""),
            required_on=v.get("required_on", "binding"),
        )
        for k, v in raw.get("picks", {}).items()
    }

    overlap = variables.keys() & picks.keys()
    if overlap:
        raise ValueError(
            f"{path}: declared as both a pick and a variable: {sorted(overlap)}"
        )

    return RulesFile(
        edition=edition,
        verified=verified,
        tables=tables,
        steps=steps,
        variables=variables,
        picks=picks,
    )
