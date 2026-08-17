import json

import pytest

from rules_engine.export_adapter import ExportError, read_export

TOKI = "character_exports/dndbeyond-toki-ironlung.json"


def _base_character(**overrides):
    character = {
        "name": "Test",
        "classes": [{"level": 3, "definition": {"name": "Rogue"}}],
        "stats": [{"id": 1, "value": 14}, {"id": 2, "value": 16}, {"id": 3, "value": 12},
                  {"id": 4, "value": 10}, {"id": 5, "value": 8}, {"id": 6, "value": 13}],
        "bonusStats": [{"id": i, "value": None} for i in range(1, 7)],
        "overrideStats": [{"id": i, "value": None} for i in range(1, 7)],
        "modifiers": {},
        "race": {"fullName": "Kender"},
        "background": {"definition": {"name": "Urchin"}},
        "feats": [],
        "spells": {"class": []},
        "classSpells": [],
        "inventory": [],
    }
    character.update(overrides)
    return character


def _write_export(tmp_path, character):
    export = {
        "exportedAt": "2026-08-16T00:00:00Z",
        "source": "dndbeyond-character-v5",
        "characterId": 1,
        "character": character,
    }
    path = tmp_path / "export.json"
    path.write_text(json.dumps(export))
    return path


def test_total_level_is_the_sum_of_class_levels():
    parsed = read_export(TOKI)
    assert parsed.facts.total_level == sum(parsed.facts.class_levels.values())
    assert parsed.facts.total_level > 0


def test_ability_mods_are_derived_not_read():
    parsed = read_export(TOKI)
    assert set(parsed.facts.ability_mods) == {"str", "dex", "con", "int", "wis", "cha"}
    for mod in parsed.facts.ability_mods.values():
        assert -5 <= mod <= 10


def test_grantors_include_species_class_and_background():
    parsed = read_export(TOKI)
    kinds = {g.kind for g in parsed.grantors}
    assert {"species", "class", "background"} <= kinds


def test_catalog_items_are_named():
    parsed = read_export(TOKI)
    assert parsed.spells, "expected at least one spell on the export"
    assert all(isinstance(name, str) and name for name in parsed.spells)


def test_toki_is_a_level_14_paladin():
    """Confirmed from the export on 2026-08-16. If this fails, the export was replaced."""
    parsed = read_export(TOKI)
    assert parsed.facts.total_level == 14
    assert parsed.facts.class_levels == {"paladin": 14}


def test_ability_score_math(tmp_path):
    export = {
        "exportedAt": "2026-08-16T00:00:00Z",
        "source": "dndbeyond-character-v5",
        "characterId": 1,
        "character": {
            "name": "Test",
            "classes": [{"level": 3, "definition": {"name": "Rogue"}}],
            "stats": [{"id": 1, "value": 14}, {"id": 2, "value": 16}, {"id": 3, "value": 12},
                      {"id": 4, "value": 10}, {"id": 5, "value": 8}, {"id": 6, "value": 13}],
            "bonusStats": [{"id": i, "value": None} for i in range(1, 7)],
            "overrideStats": [{"id": i, "value": None} for i in range(1, 7)],
            "modifiers": {"race": [{"type": "bonus", "subType": "dexterity-score", "value": 2}]},
            "race": {"fullName": "Kender"},
            "background": {"definition": {"name": "Urchin"}},
            "feats": [],
            "spells": {"class": []},
            "classSpells": [],
            "inventory": [],
        }
    }
    path = tmp_path / "export.json"
    path.write_text(json.dumps(export))

    parsed = read_export(path)
    assert parsed.facts.class_levels == {"rogue": 3}
    assert parsed.facts.total_level == 3
    # dex 16 base + 2 racial = 18 -> +4
    assert parsed.facts.ability_mods["dex"] == 4
    # str 14 -> +2
    assert parsed.facts.ability_mods["str"] == 2


def test_null_base_ability_score_raises_by_name(tmp_path):
    character = _base_character(
        stats=[{"id": 1, "value": None}, {"id": 2, "value": 16}, {"id": 3, "value": 12},
               {"id": 4, "value": 10}, {"id": 5, "value": 8}, {"id": 6, "value": 13}],
    )
    path = _write_export(tmp_path, character)

    with pytest.raises(ExportError, match="str"):
        read_export(path)


def test_override_of_zero_wins_over_the_summed_score(tmp_path):
    character = _base_character(
        # str 14 base, would sum to 14 with no other bonuses; override to 0 must win.
        overrideStats=[{"id": 1, "value": 0}] + [{"id": i, "value": None} for i in range(2, 7)],
    )
    path = _write_export(tmp_path, character)

    parsed = read_export(path)
    assert parsed.facts.ability_mods["str"] == -5  # (0 - 10) // 2


def test_no_casting_class_yields_none_and_reading_it_raises_by_name(tmp_path):
    # A Fighter with a feat-granted spell: the class carries no spellCastingAbilityId.
    # This is Jeff's shape (Cure Wounds via a feat) — his Wisdom comes from the feat,
    # not from a spellcasting class, so SPELLCASTING_MOD must be a fact he doesn't
    # have (None), not 0 (silently non-caster) and not 3 (silently borrowing the
    # feat's ability, which belongs on the binding as CHOICE_MOD instead).
    character = _base_character(
        classes=[{"level": 13, "definition": {"name": "Fighter"}}],
        spells={"feat": [{"definition": {"name": "Cure Wounds"}, "spellCastingAbilityId": 5}]},
    )
    path = _write_export(tmp_path, character)

    parsed = read_export(path)
    assert parsed.facts.spellcasting_ability_mod is None
    with pytest.raises(KeyError, match="spellcastingAbilityMod"):
        parsed.facts.read("character.spellcastingAbilityMod")


def test_feat_spell_disagreeing_with_class_does_not_raise_and_uses_class_ability(tmp_path):
    # A Wizard (INT) with a feat spell declaring wisdom: this is Bjorn's shape
    # (Silvery Barbs, Misty Step via Fey Touched, whose ability is a per-character
    # choice that belongs on the binding as CHOICE_MOD). SPELLCASTING_MOD means the
    # casting class's ability only — the off-class feat spell must not influence it,
    # and must not cause a refusal either, since the class ability is unambiguous.
    character = _base_character(
        classes=[{"level": 10, "definition": {"name": "Wizard", "spellCastingAbilityId": 4}}],
        spells={"feat": [{"definition": {"name": "Silvery Barbs"}, "spellCastingAbilityId": 5}]},
    )
    path = _write_export(tmp_path, character)

    parsed = read_export(path)
    assert parsed.facts.spellcasting_ability_mod == parsed.facts.ability_mods["int"]


def test_two_casting_classes_with_different_abilities_raises(tmp_path):
    # A true dual-caster, e.g. Wizard (INT) / Cleric (WIS): genuinely unrepresentable
    # by one scalar. rules/2024.toml documents SPELLCASTING_MOD as resolving "per
    # class"; a single value can't, so this must refuse rather than pick one class's
    # answer and silently misprice the other class's spells.
    character = _base_character(
        classes=[
            {"level": 10, "definition": {"name": "Wizard", "spellCastingAbilityId": 4}},
            {"level": 5, "definition": {"name": "Cleric", "spellCastingAbilityId": 5}},
        ],
    )
    path = _write_export(tmp_path, character)

    with pytest.raises(ExportError, match="int.*wis"):
        read_export(path)
