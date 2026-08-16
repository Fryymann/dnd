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
        return "from"


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
    edition: str
    verified: bool
    tables: dict[str, Table] = field(default_factory=dict)
    steps: dict[str, Steps] = field(default_factory=dict)
    variables: dict[str, Variable] = field(default_factory=dict)
    picks: dict[str, Pick] = field(default_factory=dict)


def load_rules(path: str | Path) -> RulesFile:
    raw = tomllib.loads(Path(path).read_text())

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

    tables = {
        k: Table(index=v["index"], values=v["values"]) for k, v in raw.get("tables", {}).items()
    }
    steps = {
        k: Steps(index=v["index"], base=v["base"], thresholds=v["thresholds"])
        for k, v in raw.get("steps", {}).items()
    }
    picks = {
        k: Pick(
            name=k,
            description=v.get("description", ""),
            required_on=v.get("required_on", "binding"),
        )
        for k, v in raw.get("picks", {}).items()
    }

    return RulesFile(
        edition=raw["meta"]["edition"],
        verified=raw["meta"]["verified"],
        tables=tables,
        steps=steps,
        variables=variables,
        picks=picks,
    )
