"""Definitions, sets and bindings. The split between them is the design."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Composition(StrEnum):
    APPLY_ALL = "apply_all"
    MATCH_MEMBERS = "match_members"


def slug_to_filename(slug: str) -> str:
    return slug.replace("/", "__")


def slug_from_filename(name: str) -> str:
    return name.replace("__", "/")


@dataclass(frozen=True)
class Definition:
    """A rules element. Character-independent. Holds formulas, never numbers."""

    slug: str
    rules_name: str
    source: str = ""
    source_feature: str = ""
    category: str = ""
    modes: list[str] = field(default_factory=list)
    kind: str = "action"
    action_cost: str = ""
    cadence: str = ""
    effect: str = ""
    formulas: dict[str, str] = field(default_factory=dict)
    resource_kind: str = ""
    resource_amount: str = ""
    requires: list[str] = field(default_factory=list)
    applies: list[str] = field(default_factory=list)
    covers: list[str] = field(default_factory=list)
    rules_edition: str = "2024"
    campaign: str | None = None
    status: str = "published"
    origin: str = "library"


@dataclass(frozen=True)
class VerbSet:
    """A grantor. Applies wholesale or member by member."""

    slug: str
    name: str
    composition: Composition
    grantor: str
    members: list[str] = field(default_factory=list)
    level_gates: dict[str, int] = field(default_factory=dict)
    choice_points: list[str] = field(default_factory=list)
    rules_edition: str = "2024"


@dataclass(frozen=True)
class Binding:
    """One definition as held by one character. Everything that varies lives here."""

    character_id: str
    slug: str
    alias: str = ""
    evaluated: dict[str, dict[int, float]] = field(default_factory=dict)
    formulas: dict[str, str] = field(default_factory=dict)
    held_members: list[str] = field(default_factory=list)
    resource_pool: int | None = None
    picks: dict[str, int] = field(default_factory=dict)
    origin: str = "library"
    display: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class GateFailure:
    gate: int
    severity: str  # "hard" or "item"
    subject: str
    message: str
