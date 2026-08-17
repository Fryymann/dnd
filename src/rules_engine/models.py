"""Definitions, sets and bindings. The split between them is the design."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum


class Composition(StrEnum):
    APPLY_ALL = "apply_all"
    MATCH_MEMBERS = "match_members"


# A slug is lowercase kebab-case segments joined by "/": each segment is one or
# more [a-z0-9] runs joined by single hyphens, no leading/trailing hyphen, no
# empty segment. This is the one rule that keeps slug -> filename encoding safe:
# - underscores (so "__", the filename path separator, can never appear in a slug)
# - uppercase letters (so "spell/Fire-Bolt" and "spell/fire-bolt" can't collide on
#   a case-insensitive filesystem — the default on macOS APFS and Windows NTFS,
#   even though Linux is case-sensitive)
# - backslashes (a Windows path separator that "/" -> "__" replacement never
#   touches, so it would pass through into the filename untouched)
# all fall out of one charset check instead of three special cases.
_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*(/[a-z0-9]+(-[a-z0-9]+)*)*$")


def _validate_slug_charset(slug: str) -> None:
    if not _SLUG_PATTERN.fullmatch(slug):
        raise ValueError(
            f"slug {slug!r} is not a valid slug: slugs must be lowercase kebab-case "
            "segments — each segment one or more runs of [a-z0-9] joined by single "
            "hyphens, no leading/trailing hyphen, no empty segment — joined by '/'. "
            "No underscores, uppercase letters, backslashes, or other characters."
        )


def slug_to_filename(slug: str) -> str:
    """Encode a slug as a snapshot filename, using `__` in place of `/`.

    A double underscore is reserved as the path separator in snapshot filenames,
    so it cannot appear inside a slug: "homebrew/dm__gift" and "homebrew/dm/gift"
    would both encode to "homebrew__dm__gift", and the second write would silently
    overwrite the first with no error anywhere. The dedicated check below exists
    to give that specific collision a message an author can actually act on;
    `_validate_slug_charset` is the real guarantee — it also catches the same
    collision arising from case (case-insensitive filesystems) or from characters
    outside the kebab-case charset entirely (e.g. a backslash).
    """
    if "__" in slug:
        raise ValueError(
            f"slug {slug!r} contains '__', which is reserved as the path separator "
            "in snapshot filenames and cannot appear inside a slug"
        )
    _validate_slug_charset(slug)
    return slug.replace("/", "__")


def slug_from_filename(name: str) -> str:
    """Decode a snapshot filename back into a slug.

    No collision guard is needed on this side: every "__" in a filename was
    produced by a "/" in the original slug, because slug_to_filename now refuses
    to encode a slug that itself contains "__". Given only filenames produced by
    slug_to_filename, this direction is already total and unambiguous.
    """
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
    evaluated: dict[str, dict[int, int | float]] = field(default_factory=dict)
    # A copy of the source Definition's formulas, carried for provenance: so you
    # can see what formula produced a baked evaluated number without going back
    # to the library the binding was created from.
    formulas: dict[str, str] = field(default_factory=dict)
    held_members: list[str] = field(default_factory=list)
    resource_pool: int | None = None
    picks: dict[str, int] = field(default_factory=dict)
    # "library" if this binding traces to published library content, "table" (or
    # similar) if it was authored directly for this character. The publisher
    # reads this to decide what it is allowed to overwrite on the next sync.
    origin: str = "library"
    display: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class GateFailure:
    gate: int
    severity: str  # "hard" or "item"
    subject: str
    message: str
