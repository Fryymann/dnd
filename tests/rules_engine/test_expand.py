import pytest

from rules_engine.expand import expand_expression
from rules_engine.facts import CharacterFacts
from rules_engine.rules_file import load_rules


def facts() -> CharacterFacts:
    return CharacterFacts(
        total_level=14,
        class_levels={"rogue": 14},
        ability_mods={"str": 0, "dex": 5, "con": 2, "int": 3, "wis": 1, "cha": 4},
        spellcasting_ability_mod=4,
        walk_speed=30,
    )


def test_expansion_covers_every_level():
    table = expand_expression("CANTRIP_DICE", load_rules("rules/2024.toml"), facts())
    assert sorted(table) == list(range(1, 21))


def test_cantrip_scaling_is_the_bug_this_prevents():
    table = expand_expression("CANTRIP_DICE", load_rules("rules/2024.toml"), facts())
    assert table[1] == 1
    assert table[4] == 1
    assert table[5] == 2
    assert table[10] == 2
    assert table[11] == 3
    assert table[16] == 3
    assert table[17] == 4
    assert table[20] == 4


def test_constant_expression_is_flat():
    table = expand_expression("8 + 2", load_rules("rules/2024.toml"), facts())
    assert set(table.values()) == {10}


def test_string_pick_is_rejected():
    with pytest.raises(ValueError, match="CHOICE_MOD"):
        expand_expression(
            "CHOICE_MOD", load_rules("rules/2024.toml"), facts(), picks={"CHOICE_MOD": "3"}
        )


def test_bool_pick_is_rejected():
    with pytest.raises(ValueError, match="CHOICE_MOD"):
        expand_expression(
            "CHOICE_MOD", load_rules("rules/2024.toml"), facts(), picks={"CHOICE_MOD": True}
        )


def test_none_pick_is_rejected():
    with pytest.raises(ValueError, match="CHOICE_MOD"):
        expand_expression(
            "CHOICE_MOD", load_rules("rules/2024.toml"), facts(), picks={"CHOICE_MOD": None}
        )
