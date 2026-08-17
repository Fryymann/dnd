"""Read verbs/snapshot/ into definitions and sets. Reads only; never validates rules."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from rules_engine.models import (
    Composition,
    Definition,
    VerbSet,
    slug_from_filename,
    slug_to_filename,
)


@dataclass(frozen=True)
class Snapshot:
    definitions: dict[str, Definition] = field(default_factory=dict)
    sets: dict[str, VerbSet] = field(default_factory=dict)


def _read(path: Path) -> dict:
    raw = json.loads(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError(f"{path.name}: expected a JSON object, got {type(raw).__name__}")

    expected = slug_from_filename(path.stem)
    slug = raw.get("slug")
    if slug != expected:
        raise ValueError(f"{path.name}: filename {path.stem!r} does not match slug {slug!r}")

    # slug_to_filename re-runs the same charset rule slugs are encoded under (no
    # underscores, no uppercase, no backslashes). It's called only for its
    # validation; the encoded string it returns is discarded. Without this, a
    # hand-placed file can declare a slug outside the charset — e.g. one that
    # differs from another only by case — and load cleanly on a case-sensitive
    # filesystem while silently colliding the moment the snapshot is checked out
    # somewhere case-insensitive.
    try:
        slug_to_filename(slug)
    except ValueError as exc:
        raise ValueError(f"{path.name}: {exc}") from exc

    return raw


def _require_dir(root: Path, name: str) -> Path:
    directory = root / name
    if not directory.is_dir():
        raise ValueError(f"snapshot directory {directory} does not exist")
    return directory


def _validate_level_gates(level_gates: dict) -> None:
    for key, value in level_gates.items():
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"level_gates[{key!r}] must be an integer, got {value!r}")


def load_snapshot(root: str | Path) -> Snapshot:
    root = Path(root)

    # Tracks every slug claimed so far, across both verbs/ and sets/, so a slug
    # names exactly one thing in the snapshot regardless of which directory or
    # kind it was declared in.
    claimed: dict[str, tuple[str, Path]] = {}

    def _claim(slug: str, kind: str, path: Path) -> None:
        if slug in claimed:
            other_kind, other_path = claimed[slug]
            raise ValueError(
                f"slug {slug!r} is declared more than once: "
                f"{other_kind} {other_path.name!r} and {kind} {path.name!r}"
            )
        claimed[slug] = (kind, path)

    definitions: dict[str, Definition] = {}
    for path in sorted(_require_dir(root, "verbs").glob("*.json")):
        body = _read(path)
        try:
            definition = Definition(**body)
        except TypeError as exc:
            raise ValueError(f"{path.name}: {exc}") from exc
        _claim(definition.slug, "definition", path)
        definitions[definition.slug] = definition

    sets: dict[str, VerbSet] = {}
    for path in sorted(_require_dir(root, "sets").glob("*.json")):
        body = _read(path)
        try:
            body["composition"] = Composition(body["composition"])
            _validate_level_gates(body.get("level_gates", {}))
            verb_set = VerbSet(**body)
        except KeyError as exc:
            raise ValueError(f"{path.name}: missing required key {exc}") from exc
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{path.name}: {exc}") from exc
        _claim(verb_set.slug, "set", path)
        sets[verb_set.slug] = verb_set

    return Snapshot(definitions=definitions, sets=sets)
