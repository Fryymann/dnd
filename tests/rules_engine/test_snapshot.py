import pytest

from rules_engine.models import Composition
from rules_engine.snapshot import load_snapshot

FIXTURE = "tests/fixtures/snapshot_small"


def test_loads_definitions_keyed_by_slug():
    snapshot = load_snapshot(FIXTURE)
    assert set(snapshot.definitions) == {
        "class-feature/sneak-attack",
        "spell/fire-bolt",
        "class-feature/cunning-action-dash",
    }
    assert snapshot.definitions["spell/fire-bolt"].rules_name == "Fire Bolt"
    assert snapshot.definitions["spell/fire-bolt"].formulas["damage_dice"] == "CANTRIP_DICE"


def test_loads_sets_with_composition():
    snapshot = load_snapshot(FIXTURE)
    assert snapshot.sets["class/rogue"].composition is Composition.APPLY_ALL
    assert snapshot.sets["spell-list/sorcerer"].composition is Composition.MATCH_MEMBERS


def test_filename_slug_mismatch_is_rejected(tmp_path):
    (tmp_path / "verbs").mkdir()
    (tmp_path / "sets").mkdir()
    (tmp_path / "verbs" / "spell__wrong-name.json").write_text(
        '{"slug": "spell/fire-bolt", "rules_name": "Fire Bolt"}'
    )
    with pytest.raises(ValueError, match="filename.*does not match slug"):
        load_snapshot(tmp_path)


def _empty_snapshot_dirs(tmp_path):
    (tmp_path / "verbs").mkdir()
    (tmp_path / "sets").mkdir()
    return tmp_path


def test_same_slug_in_verbs_and_sets_is_rejected(tmp_path):
    _empty_snapshot_dirs(tmp_path)
    (tmp_path / "verbs" / "class__rogue.json").write_text(
        '{"slug": "class/rogue", "rules_name": "Rogue"}'
    )
    (tmp_path / "sets" / "class__rogue.json").write_text(
        '{"slug": "class/rogue", "name": "Rogue", "composition": "apply_all", '
        '"grantor": "Rogue"}'
    )
    with pytest.raises(ValueError, match="declared more than once") as exc_info:
        load_snapshot(tmp_path)
    message = str(exc_info.value)
    assert "definition" in message
    assert "set" in message


def test_slug_charset_is_enforced_on_read(tmp_path):
    _empty_snapshot_dirs(tmp_path)
    (tmp_path / "verbs" / "Spell__Fire_Bolt.json").write_text(
        '{"slug": "Spell/Fire_Bolt", "rules_name": "Fire Bolt"}'
    )
    with pytest.raises(ValueError, match="Spell__Fire_Bolt.json"):
        load_snapshot(tmp_path)


def test_non_dict_json_is_rejected(tmp_path):
    _empty_snapshot_dirs(tmp_path)
    (tmp_path / "verbs" / "spell__fire-bolt.json").write_text("[]")
    with pytest.raises(ValueError, match="spell__fire-bolt.json.*JSON object"):
        load_snapshot(tmp_path)


def test_set_missing_composition_is_rejected(tmp_path):
    _empty_snapshot_dirs(tmp_path)
    (tmp_path / "sets" / "class__rogue.json").write_text(
        '{"slug": "class/rogue", "name": "Rogue", "grantor": "Rogue"}'
    )
    with pytest.raises(ValueError, match="class__rogue.json.*composition"):
        load_snapshot(tmp_path)


def test_set_invalid_composition_value_is_rejected(tmp_path):
    _empty_snapshot_dirs(tmp_path)
    (tmp_path / "sets" / "class__rogue.json").write_text(
        '{"slug": "class/rogue", "name": "Rogue", "composition": "bogus", "grantor": "Rogue"}'
    )
    with pytest.raises(ValueError, match="class__rogue.json.*bogus"):
        load_snapshot(tmp_path)


def test_set_level_gates_non_integer_value_is_rejected(tmp_path):
    _empty_snapshot_dirs(tmp_path)
    (tmp_path / "sets" / "class__rogue.json").write_text(
        '{"slug": "class/rogue", "name": "Rogue", "composition": "apply_all", '
        '"grantor": "Rogue", "level_gates": {"x": "2"}}'
    )
    with pytest.raises(ValueError, match="class__rogue.json.*level_gates"):
        load_snapshot(tmp_path)
