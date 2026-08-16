import pytest

from rules_engine.facts import CharacterFacts


def facts() -> CharacterFacts:
    return CharacterFacts(
        total_level=14,
        class_levels={"rogue": 9, "sorcerer": 5},
        ability_mods={"str": 0, "dex": 5, "con": 2, "int": 3, "wis": 1, "cha": 4},
        spellcasting_ability_mod=4,
        walk_speed=30,
    )


def test_reads_a_scalar_path():
    assert facts().read("character.totalLevel") == 14
    assert facts().read("character.speed.walk") == 30


def test_reads_an_ability_mod():
    assert facts().read("character.abilities.dex.mod") == 5


def test_reads_a_class_level_by_subscript():
    assert facts().read("character.classLevels", key="rogue") == 9


def test_unknown_path_raises_by_name():
    with pytest.raises(KeyError, match="character.nope"):
        facts().read("character.nope")


def test_unknown_class_is_zero_not_an_error():
    # A rogue formula must evaluate to 0 for a character with no rogue levels,
    # not explode. Multiclass formulas are shared across characters.
    assert facts().read("character.classLevels", key="bard") == 0
