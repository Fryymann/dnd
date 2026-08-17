from rules_engine.models import Composition, slug_from_filename, slug_to_filename


def test_slug_round_trips_through_a_filename():
    assert (
        slug_to_filename("subclass/rogue/arcane-trickster") == "subclass__rogue__arcane-trickster"
    )
    assert (
        slug_from_filename("subclass__rogue__arcane-trickster") == "subclass/rogue/arcane-trickster"
    )


def test_composition_values():
    assert Composition.APPLY_ALL.value == "apply_all"
    assert Composition.MATCH_MEMBERS.value == "match_members"
