import pytest

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


def test_slug_with_double_underscore_is_rejected():
    # "homebrew/dm__gift" and "homebrew/dm/gift" would both encode to
    # "homebrew__dm__gift" — two distinct verbs colliding on one filename, with
    # the second write silently overwriting the first. Prove the collision
    # target first, then prove the guard stops the colliding slug from reaching it.
    assert slug_to_filename("homebrew/dm/gift") == "homebrew__dm__gift"
    with pytest.raises(ValueError, match="homebrew/dm__gift"):
        slug_to_filename("homebrew/dm__gift")


def test_slug_with_uppercase_is_rejected():
    # "spell/Fire-Bolt" and "spell/fire-bolt" are distinct strings but the SAME
    # FILE on a case-insensitive filesystem (default macOS APFS, default Windows
    # NTFS) — the identical silent-overwrite failure the "__" guard exists to
    # prevent. Prove the collision target first (case-folded, since the two
    # filenames only agree once case is ignored), then prove the guard.
    assert slug_to_filename("spell/fire-bolt").lower() == "spell__fire-bolt".lower()
    with pytest.raises(ValueError, match="Fire-Bolt"):
        slug_to_filename("spell/Fire-Bolt")


def test_slug_with_backslash_is_rejected():
    # A backslash is a path separator on Windows and is not neutralised by
    # replacing "/" with "__" — it would pass straight through into the filename.
    with pytest.raises(ValueError, match="not a valid slug"):
        slug_to_filename("homebrew\\gift")
