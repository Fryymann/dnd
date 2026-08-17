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


def test_reads_class_levels_as_a_container():
    assert facts().read_container("character.classLevels") == {"rogue": 9, "sorcerer": 5}


def test_unknown_path_raises_by_name():
    with pytest.raises(KeyError, match="character.nope"):
        facts().read("character.nope")


def test_read_refuses_a_container_path():
    # `character.classLevels` holds one value per class, not a single scalar. `read()`
    # used to accept an optional `key` and default a missing class to 0 — which meant a
    # rogue formula for a character with no rogue levels evaluated to a plausible 0
    # instead of failing, and a class-levels variable declared under any name other
    # than the one caller that always passed a key silently fell through to that same
    # 0 for EVERY character, rogue or not. formula.py already settled the underlying
    # question: a missing key is a fact the evaluator doesn't have, not a value of
    # zero. `read()` now refuses container paths outright so the old behavior can't be
    # recreated by hand; `read_container()` is the only way to get the whole dict.
    with pytest.raises(ValueError, match="character.classLevels"):
        facts().read("character.classLevels")


def test_read_container_refuses_a_scalar_path():
    with pytest.raises(ValueError, match="character.totalLevel"):
        facts().read_container("character.totalLevel")


def test_read_container_unknown_path_raises_by_name():
    with pytest.raises(ValueError, match="character.nope"):
        facts().read_container("character.nope")


def test_is_container_path():
    assert facts().is_container_path("character.classLevels") is True
    assert facts().is_container_path("character.totalLevel") is False


def test_unknown_ability_in_known_path_raises_by_name():
    with pytest.raises(KeyError, match="character.abilities.xyz.mod"):
        facts().read("character.abilities.xyz.mod")


def test_no_spellcasting_class_raises_by_name_rather_than_reading_zero():
    no_caster = CharacterFacts(
        total_level=13,
        class_levels={"fighter": 13},
        ability_mods={"str": 0, "dex": 5, "con": 2, "int": 3, "wis": 1, "cha": 4},
        spellcasting_ability_mod=None,
        walk_speed=30,
    )
    with pytest.raises(KeyError, match="character.spellcastingAbilityMod"):
        no_caster.read("character.spellcastingAbilityMod")


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
