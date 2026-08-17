"""The character.* namespace. Export-shape-independent by design."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import ClassVar


@dataclass(frozen=True)
class CharacterFacts:
    # frozen=True only blocks reassigning these fields (`facts.total_level = ...`); the
    # dicts below are still mutable in place, and `at_level()`'s `replace()` only copies
    # `total_level` and `class_levels` — `ability_mods` in the returned copy is the same
    # dict object as in the original, not a new one. Don't mutate it expecting isolation.
    total_level: int
    class_levels: dict[str, int]
    ability_mods: dict[str, int]
    # None for a character with no spellcasting class — that is a fact this character
    # doesn't have, not a modifier of zero. read() raises by name rather than handing
    # a formula a plausible-looking number for a character who can't cast.
    spellcasting_ability_mod: int | None
    walk_speed: int

    # Export paths that hold one value per key (a class, an ability, ...) rather than
    # a single scalar. This is the one place that knowledge should live — a caller
    # asks `is_container_path` rather than keeping its own name-based list, which is
    # what let a class-levels variable declared under any name other than CLASS_LEVEL
    # silently fall through to a scalar read and resolve to 0 for every character.
    CONTAINER_PATHS: ClassVar[frozenset[str]] = frozenset({"character.classLevels"})

    def is_container_path(self, path: str) -> bool:
        return path in self.CONTAINER_PATHS

    def read(self, path: str) -> int:
        if path in self.CONTAINER_PATHS:
            raise ValueError(f"{path} is a container path; use read_container() instead")
        if path == "character.totalLevel":
            return self.total_level
        if path == "character.speed.walk":
            return self.walk_speed
        if path == "character.spellcastingAbilityMod":
            if self.spellcasting_ability_mod is None:
                raise KeyError(
                    f"{path}: this character has no spellcasting class, "
                    "so there is no class spellcasting ability modifier to read"
                )
            return self.spellcasting_ability_mod
        if path.startswith("character.abilities.") and path.endswith(".mod"):
            ability = path.split(".")[2]
            if ability in self.ability_mods:
                return self.ability_mods[ability]
        raise KeyError(f"unknown export path: {path}")

    def read_container(self, path: str) -> dict[str, int]:
        if path not in self.CONTAINER_PATHS:
            raise ValueError(f"{path} is not a container path; use read() instead")
        if path == "character.classLevels":
            return self.class_levels
        raise AssertionError(f"container path {path!r} is declared but has no handler")

    def at_level(self, level: int) -> CharacterFacts:
        """The same character as if they were `level`, scaling class levels proportionally.

        Used only to expand a binding across levels 1-20. The character's real level is
        what the sheet renders; the rest of the table exists so level-up is a lookup.

        Each class is floored to at least 1 independently, with no renormalization across
        classes, so at low scaled levels sum(class_levels.values()) can exceed total_level
        (a 9/5 split at total 14 scaled down to level 1 becomes {1, 1}, summing to 2, not
        1). This is a deliberate consequence of the proportional-scaling approximation —
        do not "fix" it by renormalizing.
        """
        if self.total_level == 0:
            return replace(self, total_level=level)
        scaled = {
            name: max(1, round(levels * level / self.total_level))
            for name, levels in self.class_levels.items()
        }
        return replace(self, total_level=level, class_levels=scaled)
