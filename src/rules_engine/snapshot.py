"""Read verbs/snapshot/ into definitions and sets. Reads only; never validates rules."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from rules_engine.models import Composition, Definition, VerbSet, slug_from_filename


@dataclass(frozen=True)
class Snapshot:
    definitions: dict[str, Definition] = field(default_factory=dict)
    sets: dict[str, VerbSet] = field(default_factory=dict)


def _read(path: Path) -> dict:
    body = json.loads(path.read_text())
    expected = slug_from_filename(path.stem)
    if body.get("slug") != expected:
        raise ValueError(
            f"{path.name}: filename {path.stem!r} does not match slug {body.get('slug')!r}"
        )
    return dict(body)


def _require_dir(root: Path, name: str) -> Path:
    directory = root / name
    if not directory.is_dir():
        raise ValueError(f"snapshot directory {directory} does not exist")
    return directory


def load_snapshot(root: str | Path) -> Snapshot:
    root = Path(root)

    definitions: dict[str, Definition] = {}
    for path in sorted(_require_dir(root, "verbs").glob("*.json")):
        body = _read(path)
        try:
            definition = Definition(**body)
        except TypeError as exc:
            raise ValueError(f"{path.name}: {exc}") from exc
        if definition.slug in definitions:
            raise ValueError(
                f"{path.name}: duplicate definition slug {definition.slug!r}, "
                f"already loaded from another file"
            )
        definitions[definition.slug] = definition

    sets: dict[str, VerbSet] = {}
    for path in sorted(_require_dir(root, "sets").glob("*.json")):
        body = _read(path)
        body["composition"] = Composition(body["composition"])
        try:
            verb_set = VerbSet(**body)
        except TypeError as exc:
            raise ValueError(f"{path.name}: {exc}") from exc
        if verb_set.slug in sets:
            raise ValueError(
                f"{path.name}: duplicate set slug {verb_set.slug!r}, "
                f"already loaded from another file"
            )
        sets[verb_set.slug] = verb_set

    return Snapshot(definitions=definitions, sets=sets)
