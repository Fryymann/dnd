import pytest

from rules_engine.facts import CharacterFacts
from rules_engine.rules_file import load_rules
from rules_engine.variables import UnknownVariable, resolve


def facts(level: int = 14) -> CharacterFacts:
    return CharacterFacts(
        total_level=level,
        class_levels={"rogue": 9, "sorcerer": 5},
        ability_mods={"str": 0, "dex": 5, "con": 2, "int": 3, "wis": 1, "cha": 4},
        spellcasting_ability_mod=4,
        walk_speed=30,
    )


def test_from_variable():
    rules = load_rules("rules/2024.toml")
    assert resolve("CHARACTER_LEVEL", rules, facts()) == 14


def test_table_variable():
    rules = load_rules("rules/2024.toml")
    assert resolve("PROFICIENCY_BONUS", rules, facts(level=14)) == 5
    assert resolve("PROFICIENCY_BONUS", rules, facts(level=1)) == 2


def test_steps_variable():
    rules = load_rules("rules/2024.toml")
    assert resolve("CANTRIP_DICE", rules, facts(level=1)) == 1
    assert resolve("CANTRIP_DICE", rules, facts(level=4)) == 1
    assert resolve("CANTRIP_DICE", rules, facts(level=5)) == 2
    assert resolve("CANTRIP_DICE", rules, facts(level=11)) == 3
    assert resolve("CANTRIP_DICE", rules, facts(level=17)) == 4


def test_formula_variable_resolves_dependencies():
    rules = load_rules("rules/2024.toml")
    # 8 + CHA_MOD(4) + PROFICIENCY_BONUS(5)
    assert resolve("SPELL_SAVE_DC", rules, facts()) == 17


def test_subscripted_dependency():
    rules = load_rules("rules/2024.toml")
    # ceil(rogue 9 / 2)
    assert resolve("SNEAK_ATTACK_DICE", rules, facts()) == 5


def test_pick_value_is_supplied_by_the_binding():
    rules = load_rules("rules/2024.toml")
    assert resolve("CHOICE_MOD", rules, facts(), picks={"CHOICE_MOD": 3}) == 3


def test_missing_pick_raises_by_name():
    rules = load_rules("rules/2024.toml")
    with pytest.raises(UnknownVariable, match="CHOICE_MOD"):
        resolve("CHOICE_MOD", rules, facts(), picks={})


def test_undeclared_variable_raises_by_name():
    rules = load_rules("rules/2024.toml")
    with pytest.raises(UnknownVariable, match="WARLOCK_SLOTS"):
        resolve("WARLOCK_SLOTS", rules, facts())


def test_circular_formula_raises_by_name(tmp_path):
    path = tmp_path / "circular.toml"
    path.write_text(
        '[meta]\nedition = "x"\nverified = false\n'
        '[variables.A]\nformula = "B + 1"\n'
        '[variables.B]\nformula = "A + 1"\n'
    )
    rules = load_rules(path)
    with pytest.raises(UnknownVariable, match="circular"):
        resolve("A", rules, facts())


def test_table_index_out_of_range_raises_by_name(tmp_path):
    # Regression: `table.values[int(index) - 1]` with a plain Python list silently
    # wraps around for index <= 0 (values[-1] is the LAST element, not an error).
    # An out-of-range index must fail loudly instead of returning a wrong number.
    path = tmp_path / "out_of_range.toml"
    path.write_text(
        '[meta]\nedition = "x"\nverified = false\n'
        '[tables.t]\nindex = "CHARACTER_LEVEL"\n'
        "values = [2, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4, 5, 5, 5, 5, 6, 6, 6, 6]\n"
        '[variables.CHARACTER_LEVEL]\nfrom = "character.totalLevel"\n'
        '[variables.OVER]\ntable = "t"\n'
    )
    rules = load_rules(path)
    with pytest.raises(UnknownVariable, match="OVER"):
        resolve("OVER", rules, facts(level=21))


def test_table_referencing_undeclared_section_raises_by_name(tmp_path):
    path = tmp_path / "missing_table.toml"
    path.write_text(
        '[meta]\nedition = "x"\nverified = false\n'
        '[variables.CHARACTER_LEVEL]\nfrom = "character.totalLevel"\n'
        '[variables.BAD]\ntable = "does_not_exist"\n'
    )
    rules = load_rules(path)
    with pytest.raises(UnknownVariable, match="does_not_exist"):
        resolve("BAD", rules, facts())
