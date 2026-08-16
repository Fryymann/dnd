"""The character.* namespace. Export-shape-independent by design."""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class CharacterFacts:
    total_level: int
    class_levels: dict[str, int]
    ability_mods: dict[str, int]
    spellcasting_ability_mod: int
    walk_speed: int

    def read(self, path: str, key: str | None = None) -> int:
        if path == "character.totalLevel":
            return self.total_level
        if path == "character.speed.walk":
            return self.walk_speed
        if path == "character.spellcastingAbilityMod":
            return self.spellcasting_ability_mod
        if path == "character.classLevels":
            return self.class_levels.get(key or "", 0)
        if path.startswith("character.abilities.") and path.endswith(".mod"):
            ability = path.split(".")[2]
            if ability in self.ability_mods:
                return self.ability_mods[ability]
        raise KeyError(f"unknown export path: {path}")

    def at_level(self, level: int) -> CharacterFacts:
        """The same character as if they were `level`, scaling class levels proportionally.

        Used only to expand a binding across levels 1-20. The character's real level is
        what the sheet renders; the rest of the table exists so level-up is a lookup.
        """
        if self.total_level == 0:
            return replace(self, total_level=level)
        scaled = {
            name: max(1, round(levels * level / self.total_level))
            for name, levels in self.class_levels.items()
        }
        return replace(self, total_level=level, class_levels=scaled)
