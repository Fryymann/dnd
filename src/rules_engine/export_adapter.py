"""Turn a D&D Beyond export into CharacterFacts and a grantor list.

This is the only module that knows D&D Beyond's shape. Everything downstream sees
CharacterFacts, so a different export source means a new adapter and nothing else.

The export root is {"exportedAt", "source", "characterId", "character"} — verified
against real dndbeyond-character-v5 exports (source string confirmed). Everything
relevant lives under "character".
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from rules_engine.facts import CharacterFacts

STAT_IDS = {1: "str", 2: "dex", 3: "con", 4: "int", 5: "wis", 6: "cha"}
SCORE_SUBTYPES = {f"{full}-score": short for full, short in {
    "strength": "str",
    "dexterity": "dex",
    "constitution": "con",
    "intelligence": "int",
    "wisdom": "wis",
    "charisma": "cha",
}.items()}


class ExportError(ValueError):
    """Something the export was expected to carry is missing or malformed. Names it."""


@dataclass(frozen=True)
class Grantor:
    """Something the export names that a set may match: a class, a feat, a species."""

    kind: str
    name: str


@dataclass(frozen=True)
class ParsedExport:
    facts: CharacterFacts
    grantors: list[Grantor] = field(default_factory=list)
    spells: list[str] = field(default_factory=list)
    items: list[str] = field(default_factory=list)


def _ability_scores(data: dict) -> dict[str, int]:
    # Base scores. A base score of null (as opposed to simply absent) is not a score
    # of 0 — treating it as one would silently produce a -5 modifier on every check
    # that uses it. Fail by name instead of guessing.
    scores: dict[str, int] = {}
    for s in data["stats"]:
        ability = STAT_IDS[s["id"]]
        value = s.get("value")
        if value is None:
            raise ExportError(f"ability score {ability!r} has no base value in this export")
        scores[ability] = value

    missing = set(STAT_IDS.values()) - set(scores)
    if missing:
        raise ExportError(f"export is missing base ability score(s): {sorted(missing)}")

    for bonus in data.get("bonusStats") or []:
        if bonus.get("value"):
            scores[STAT_IDS[bonus["id"]]] += bonus["value"]

    for group in (data.get("modifiers") or {}).values():
        for modifier in group or []:
            subtype = modifier.get("subType", "")
            if (
                modifier.get("type") == "bonus"
                and subtype in SCORE_SUBTYPES
                and modifier.get("value")
            ):
                scores[SCORE_SUBTYPES[subtype]] += modifier["value"]

    # Override replaces rather than adds, and must win last. A legitimate override of
    # 0 is rare but real (a cursed item, a debuff) — `if override.get("value")` would
    # silently discard it because 0 is falsy, leaving the summed score in place instead
    # of the override the sheet says is authoritative. Check presence, not truthiness.
    for override in data.get("overrideStats") or []:
        if override.get("value") is not None:
            scores[STAT_IDS[override["id"]]] = override["value"]

    return scores


def _spellcasting_ability_ids(data: dict) -> set[int]:
    """Every ability id a spellcasting CLASS declares.

    SPELLCASTING_MOD means the ability of the character's spellcasting class — not
    any ability a feat- or item-granted spell happens to use. Fey Touched, Magic
    Initiate and similar let a player choose the ability when the feature is taken;
    that choice varies per character and belongs on the binding as CHOICE_MOD (see
    `[picks.CHOICE_MOD]` in rules/2024.toml — the same shape as Kender Taunt), not
    folded into the class's own spellcasting modifier. Consulting spell entries here
    would let one off-class spell silently redefine what SPELLCASTING_MOD means for
    the character's actual casting class.
    """
    ids: set[int] = set()
    for klass in data["classes"]:
        if ability_id := klass["definition"].get("spellCastingAbilityId"):
            ids.add(ability_id)
    return ids


def _spellcasting_ability_mod(data: dict, ability_mods: dict[str, int]) -> int | None:
    """The ability modifier of the character's spellcasting class, or None.

    None means "no spellcasting class" — a fact this character genuinely doesn't
    have, not a modifier of zero. CharacterFacts.read() raises by name if a formula
    asks for it on a character with no casting class, rather than silently handing
    back 0, which is exactly the defect closed for missing ability scores and
    missing class levels.

    Two casting classes with different abilities (a true Wizard/Cleric multiclass)
    is genuinely unrepresentable by one scalar. rules/2024.toml documents
    SPELLCASTING_MOD as resolving "per class"; refusing here is honest about that
    limit rather than silently picking one class's answer for both.
    """
    ids = _spellcasting_ability_ids(data)
    if not ids:
        return None
    if len(ids) > 1:
        names = sorted(STAT_IDS[i] for i in ids)
        raise ExportError(
            f"{data.get('name', 'this character')} has classes with different "
            f"spellcasting abilities ({names}); spellcasting_ability_mod cannot "
            "represent that"
        )
    return ability_mods[STAT_IDS[next(iter(ids))]]


def read_export(path: str | Path) -> ParsedExport:
    # The export is {"exportedAt", "source", "characterId", "character"} — verified
    # against dndbeyond-character-v5 exports. Everything lives under "character".
    data = json.loads(Path(path).read_text())["character"]

    class_levels = {c["definition"]["name"].lower(): c["level"] for c in data["classes"]}
    scores = _ability_scores(data)
    ability_mods = {name: (score - 10) // 2 for name, score in scores.items()}

    spellcasting_ability_mod = _spellcasting_ability_mod(data, ability_mods)

    grantors: list[Grantor] = []
    if race := data.get("race"):
        grantors.append(
            Grantor(kind="species", name=race.get("fullName") or race.get("baseName", ""))
        )
    for klass in data["classes"]:
        grantors.append(Grantor(kind="class", name=klass["definition"]["name"]))
        if subclass := klass.get("subclassDefinition"):
            grantors.append(Grantor(kind="subclass", name=subclass["name"]))
    if background := (data.get("background") or {}).get("definition"):
        grantors.append(Grantor(kind="background", name=background["name"]))
    for feat in data.get("feats") or []:
        grantors.append(Grantor(kind="feat", name=feat["definition"]["name"]))

    spells: list[str] = []
    for group in (data.get("spells") or {}).values():
        for spell in group or []:
            spells.append(spell["definition"]["name"])
    for entry in data.get("classSpells") or []:
        for spell in entry.get("spells") or []:
            spells.append(spell["definition"]["name"])

    items = [i["definition"]["name"] for i in data.get("inventory") or []]

    facts = CharacterFacts(
        total_level=sum(class_levels.values()),
        class_levels=class_levels,
        ability_mods=ability_mods,
        spellcasting_ability_mod=spellcasting_ability_mod,
        walk_speed=(data.get("race") or {}).get("weightSpeeds", {}).get("normal", {}).get(
            "walk", 30
        ),
    )

    return ParsedExport(
        facts=facts, grantors=grantors, spells=sorted(set(spells)), items=sorted(set(items))
    )
