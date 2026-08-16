import pytest

from rules_engine.rules_file import RulesFile, load_rules


def test_loads_edition_and_verified_flag():
    rules = load_rules("rules/2024.toml")
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
