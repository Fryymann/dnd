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


def test_unknown_ability_in_known_path_raises_by_name():
    with pytest.raises(KeyError, match="character.abilities.xyz.mod"):
        facts().read("character.abilities.xyz.mod")


def test_at_level_scales_class_levels_to_a_mid_level():
    scaled = facts().at_level(7)
    assert scaled.total_level == 7
    assert scaled.class_levels == {"rogue": 4, "sorcerer": 2}


def test_at_level_scales_class_levels_down_to_level_one():
    scaled = facts().at_level(1)
    assert scaled.total_level == 1
    assert scaled.class_levels == {"rogue": 1, "sorcerer": 1}


def test_at_level_scales_class_levels_up_to_level_twenty():
    scaled = facts().at_level(20)
    assert scaled.total_level == 20
    assert scaled.class_levels == {"rogue": 13, "sorcerer": 7}


def test_scaling_down_can_exceed_total_level_and_that_is_accepted():
    # Each class floors to at least 1 independently with no renormalization, so at
    # low scaled levels the class levels can sum to more than total_level. This is
    # a known, accepted edge of the proportional-scaling approximation, not a bug.
    scaled = facts().at_level(1)
    assert sum(scaled.class_levels.values()) > scaled.total_level


def test_at_level_zero_total_level_bypasses_scaling():
    zero_level = CharacterFacts(
        total_level=0,
        class_levels={},
        ability_mods={"str": 0, "dex": 5, "con": 2, "int": 3, "wis": 1, "cha": 4},
        spellcasting_ability_mod=4,
        walk_speed=30,
    )
    scaled = zero_level.at_level(5)
    assert scaled.total_level == 5
    assert scaled.class_levels == {}
