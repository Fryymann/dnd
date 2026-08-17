import pytest

from rules_engine.facts import CharacterFacts
from rules_engine.formula import FormulaError
from rules_engine.rules_file import RulesFile, Variable, load_rules
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


def test_table_index_below_range_does_not_wrap_to_the_last_entry():
    # Regression: a level-0 index is `int(index) - 1 == -1`. Python's negative
    # indexing turns that into `values[-1]`, the LAST table entry, which for
    # proficiency_by_level is 6 — a plausible-looking bonus, not an error. This is
    # the silent-wrong-number case the bounds check exists to catch; the level-21
    # (past the end) case above is a different failure that already raised
    # IndexError even before the fix.
    rules = load_rules("rules/2024.toml")
    with pytest.raises(UnknownVariable, match="PROFICIENCY_BONUS"):
        resolve("PROFICIENCY_BONUS", rules, facts(level=0))


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


def test_three_variable_circular_chain_prints_in_true_order(tmp_path):
    # Regression: `_seen` used to be a frozenset, which has no order, so the joined
    # chain in the error message could come out scrambled. A two-variable cycle
    # (A -> B -> A) can't tell an ordered chain from a scrambled one — both read the
    # same either way. Three variables can: this only passes if `_seen` preserves
    # insertion order (a tuple), and fails on a frozenset revert.
    path = tmp_path / "circular3.toml"
    path.write_text(
        '[meta]\nedition = "x"\nverified = false\n'
        '[variables.A]\nformula = "B + 1"\n'
        '[variables.B]\nformula = "C + 1"\n'
        '[variables.C]\nformula = "A + 1"\n'
    )
    rules = load_rules(path)
    with pytest.raises(UnknownVariable, match=r"A -> B -> C -> A"):
        resolve("A", rules, facts())


def test_class_levels_source_under_any_name_is_a_container_not_zero(tmp_path):
    # The actual bug: SUBSCRIPTABLE used to key on the variable's NAME ("CLASS_LEVEL"),
    # but what makes a `from` source a container is its export PATH
    # ("character.classLevels"), not what the rules file happens to call it. A
    # class-levels variable declared under any other name fell through to
    # `facts.read`, which silently returned 0 for every character — a 9th-level
    # rogue's Sneak Attack rendering as zero dice. Now the source path decides, so
    # `ROGUE_LEVEL` resolves to the whole {"rogue": 9, ...} container, and dividing
    # a dict by 2 raises FormulaError instead of quietly evaluating to 0.
    path = tmp_path / "renamed.toml"
    path.write_text(
        '[meta]\nedition = "x"\nverified = false\n'
        '[variables.ROGUE_LEVEL]\nfrom = "character.classLevels"\n'
        '[variables.SNEAK]\nformula = "ceil(ROGUE_LEVEL / 2)"\n'
    )
    rules = load_rules(path)
    with pytest.raises(FormulaError):
        resolve("SNEAK", rules, facts())


def test_steps_index_below_domain_raises(tmp_path):
    # Branch-asymmetry regression: the table branch was hardened to reject an
    # out-of-domain index; steps was not, so CANTRIP_DICE quietly returned 1 at
    # level 0 and level -3, and 4 at level 25 and level 100, while PROFICIENCY_BONUS
    # (a table) already raised on all four. Both branches now share one validator.
    rules = load_rules("rules/2024.toml")
    with pytest.raises(UnknownVariable, match="CANTRIP_DICE"):
        resolve("CANTRIP_DICE", rules, facts(level=0))


def test_steps_index_negative_raises():
    rules = load_rules("rules/2024.toml")
    with pytest.raises(UnknownVariable, match="CANTRIP_DICE"):
        resolve("CANTRIP_DICE", rules, facts(level=-3))


def test_steps_index_above_domain_raises():
    rules = load_rules("rules/2024.toml")
    with pytest.raises(UnknownVariable, match="CANTRIP_DICE"):
        resolve("CANTRIP_DICE", rules, facts(level=25))


def test_steps_index_far_above_domain_raises():
    rules = load_rules("rules/2024.toml")
    with pytest.raises(UnknownVariable, match="CANTRIP_DICE"):
        resolve("CANTRIP_DICE", rules, facts(level=100))


def test_table_index_bool_is_rejected_not_treated_as_one(tmp_path):
    # `int(True) == 1` would silently treat a boolean pick as level 1. A pick's
    # value is a `dict[str, int]` by type hint, but nothing upstream enforces that
    # yet (finding 6, left to Task 6), so this must be checked here too.
    path = tmp_path / "bool_index.toml"
    path.write_text(
        '[meta]\nedition = "x"\nverified = false\n'
        '[tables.t]\nindex = "IDX"\n'
        "values = [2, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4, 5, 5, 5, 5, 6, 6, 6, 6]\n"
        '[variables.OVER]\ntable = "t"\n'
        '[picks.IDX]\n'
    )
    rules = load_rules(path)
    with pytest.raises(UnknownVariable, match="OVER"):
        resolve("OVER", rules, facts(), picks={"IDX": True})


def test_table_index_float_is_rejected_not_truncated(tmp_path):
    # `int(5.9) == 5` would silently truncate a fractional index to a plausible
    # level instead of failing on the non-integer input.
    path = tmp_path / "float_index.toml"
    path.write_text(
        '[meta]\nedition = "x"\nverified = false\n'
        '[tables.t]\nindex = "IDX"\n'
        "values = [2, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4, 5, 5, 5, 5, 6, 6, 6, 6]\n"
        '[variables.OVER]\ntable = "t"\n'
        '[picks.IDX]\n'
    )
    rules = load_rules(path)
    with pytest.raises(UnknownVariable, match="OVER"):
        resolve("OVER", rules, facts(), picks={"IDX": 5.9})


def test_typo_export_path_raises_unknown_variable_not_key_error(tmp_path):
    # Every other failure in this module is UnknownVariable so gate 2 can catch by
    # type. A typo'd `from` path used to escape as a bare KeyError instead.
    path = tmp_path / "typo.toml"
    path.write_text(
        '[meta]\nedition = "x"\nverified = false\n'
        '[variables.FLY_SPEED]\nfrom = "character.speed.fly"\n'
    )
    rules = load_rules(path)
    with pytest.raises(UnknownVariable, match="FLY_SPEED"):
        resolve("FLY_SPEED", rules, facts())


def test_variable_kind_reraise_is_reachable_through_resolve():
    # Variable.kind raises ValueError for an all-None variable (see
    # test_rules_file.py::test_variable_kind_rejects_all_none_construction). load_rules
    # itself can never produce one, but resolve() must not let that ValueError escape
    # unwrapped — gate 2 only catches UnknownVariable by name.
    rules = RulesFile(edition="x", verified=False, variables={"GHOST": Variable(name="GHOST")})
    with pytest.raises(UnknownVariable, match="GHOST"):
        resolve("GHOST", rules, facts())
