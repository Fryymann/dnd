import json

from rules_engine.export_adapter import read_export

TOKI = "character_exports/dndbeyond-toki-ironlung.json"


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
