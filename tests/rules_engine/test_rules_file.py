import pytest

from rules_engine.rules_file import RulesFile, Variable, load_rules


def test_loads_edition_and_verified_flag():
    rules = load_rules("rules/2024.toml")
    assert isinstance(rules, RulesFile)
    assert rules.edition == "2024"
    assert rules.verified is False


def test_exposes_declared_variables():
    rules = load_rules("rules/2024.toml")
    assert "PROFICIENCY_BONUS" in rules.variables
    assert rules.variables["PROFICIENCY_BONUS"].table == "proficiency_by_level"
    assert rules.variables["CANTRIP_DICE"].steps == "cantrip_dice"
    assert rules.variables["SPELL_SAVE_DC"].formula == "8 + SPELLCASTING_MOD + PROFICIENCY_BONUS"
    assert rules.variables["CHARACTER_LEVEL"].source == "character.totalLevel"


def test_picks_are_separate_from_variables():
    rules = load_rules("rules/2024.toml")
    assert "CHOICE_MOD" in rules.picks
    assert "CHOICE_MOD" not in rules.variables


def test_variable_declaring_two_kinds_is_rejected(tmp_path):
    path = tmp_path / "bad.toml"
    path.write_text(
        '[meta]\nedition = "x"\nverified = false\n'
        '[variables.BAD]\ntable = "t"\nformula = "1 + 1"\n'
    )
    with pytest.raises(ValueError, match="BAD.*exactly one"):
        load_rules(path)


def test_variable_declaring_zero_kinds_is_rejected(tmp_path):
    path = tmp_path / "bad.toml"
    path.write_text(
        '[meta]\nedition = "x"\nverified = false\n'
        '[variables.EMPTY]\ndescription = "nothing declared"\n'
    )
    with pytest.raises(ValueError, match="EMPTY.*none"):
        load_rules(path)


def test_variable_kind_rejects_all_none_construction():
    variable = Variable(name="GHOST")
    with pytest.raises(ValueError, match="GHOST"):
        _ = variable.kind


def test_missing_meta_key_is_rejected(tmp_path):
    path = tmp_path / "bad.toml"
    path.write_text('[meta]\nverified = false\n')
    with pytest.raises(ValueError, match=r"meta.*missing required key 'edition'"):
        load_rules(path)


def test_missing_meta_section_is_rejected(tmp_path):
    path = tmp_path / "bad.toml"
    path.write_text('[variables.X]\nfrom = "y"\n')
    with pytest.raises(ValueError, match=r"meta.*missing required key 'edition'"):
        load_rules(path)


def test_malformed_table_section_is_rejected(tmp_path):
    path = tmp_path / "bad.toml"
    path.write_text(
        '[meta]\nedition = "x"\nverified = false\n'
        '[tables.BAD]\nindex = "CHARACTER_LEVEL"\n'
    )
    with pytest.raises(ValueError, match=r"tables\.BAD.*missing required key 'values'"):
        load_rules(path)


def test_malformed_steps_section_is_rejected(tmp_path):
    path = tmp_path / "bad.toml"
    path.write_text(
        '[meta]\nedition = "x"\nverified = false\n'
        '[steps.BAD]\nindex = "CHARACTER_LEVEL"\nbase = 1\n'
    )
    with pytest.raises(ValueError, match=r"steps\.BAD.*missing required key 'thresholds'"):
        load_rules(path)


def test_table_wrong_length_is_rejected(tmp_path):
    path = tmp_path / "bad.toml"
    path.write_text(
        '[meta]\nedition = "x"\nverified = false\n'
        '[tables.SHORT]\nindex = "CHARACTER_LEVEL"\nvalues = [1, 2, 3]\n'
    )
    with pytest.raises(ValueError, match=r"tables\.SHORT.*20 entries.*found 3"):
        load_rules(path)
