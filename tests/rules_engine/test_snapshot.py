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
