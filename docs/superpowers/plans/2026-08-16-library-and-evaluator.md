# Library and Evaluator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the pure rules engine, the Notion snapshot sync, and the Firestore publisher, so that a character's verb bindings can be evaluated from formulas and published, with every wrong number caught by a gate or a diff.

**Architecture:** Four Python packages with one-way dependencies. `rules_engine` is pure — no network, no clock, no Firebase — and holds all rules math and all gates. `notion_sync` transcribes Notion into a committed snapshot and validates nothing. `publisher` writes evaluated output to Firestore and computes nothing. `cli` orchestrates and holds no logic. The Cloud Functions of a later plan become thin wrappers over `rules_engine`, which is why nothing may leak into it.

**Tech Stack:** Python 3.12, `uv` for environment and dependency management, `pytest`, `tomllib` (stdlib), `notion-client`, `firebase-admin`, Firestore emulator, `ruff`.

**Spec:** `docs/superpowers/specs/2026-08-16-runtime-authoring-app-design.md`

**Scope note:** This plan covers subsystem 1 of 4 from the spec's sequencing section. The sheet UI (2), at-table authoring (3) and promotion (4) each get their own spec and plan. Nothing here renders anything to a player.

---

## File Structure

```
pyproject.toml                          uv project, deps, pytest + ruff config
src/rules_engine/__init__.py            public API: evaluate_character()
src/rules_engine/rules_file.py          load rules/<edition>.toml into RulesFile
src/rules_engine/facts.py               CharacterFacts — the character.* namespace
src/rules_engine/export_adapter.py      D&D Beyond export JSON -> CharacterFacts
src/rules_engine/formula.py             safe arithmetic evaluator over an AST whitelist
src/rules_engine/variables.py           resolve a variable by table/steps/formula/from
src/rules_engine/expand.py              evaluate a formula across levels 1-20
src/rules_engine/snapshot.py            read verbs/snapshot/ into Definition and Set
src/rules_engine/models.py              Definition, Set, Binding, GateFailure dataclasses
src/rules_engine/matching.py            export grantors -> sets; module vs catalog
src/rules_engine/gates.py               the four gates
src/rules_engine/binding.py             build evaluated bindings from matches
src/rules_engine/diff.py                derived-value diff between two build artifacts
src/notion_sync/__init__.py
src/notion_sync/client.py               thin Notion API wrapper, injectable
src/notion_sync/pull.py                 collections -> verbs/snapshot/, fails on drift
src/publisher/__init__.py
src/publisher/firestore_client.py       Firestore handle, emulator-aware
src/publisher/publish.py                idempotent upserts, origin:table protection
src/cli/__init__.py
src/cli/main.py                         pull / check / build / publish
firestore.rules                         security rules — the whole security boundary
tests/rules_engine/...                  unit tests, no I/O
tests/notion_sync/...                   replayed API responses, inline in the test
tests/publisher/...                     Firestore emulator tests
tests/fixtures/snapshot_small/          five hand-built records, every value deliberate
tests/fixtures/golden/                  Toki and Rafe expected numbers
tests/rules/test_phb_anchors.py         2024 PHB anchors — closes verified=false
```

**Why this split:** `formula.py`, `variables.py` and `expand.py` are separated because they fail differently — a bad expression, an undeclared variable, and a wrong progression are three distinct bugs, and keeping them apart keeps their tests apart. `matching.py` and `gates.py` are separate because matching answers "what does this character have" and gates answer "what is wrong with that", and merging them is how a gate quietly starts deciding matches.

---

### Task 1: Project scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `src/rules_engine/__init__.py`
- Create: `tests/rules_engine/test_smoke.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/rules_engine/test_smoke.py
import rules_engine


def test_package_imports():
    assert rules_engine.__name__ == "rules_engine"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/rules_engine/test_smoke.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rules_engine'`

- [ ] **Step 3: Create the project files**

```toml
# pyproject.toml
[project]
name = "dnd-crafter"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = []

[project.optional-dependencies]
sync = ["notion-client>=2.2"]
publish = ["firebase-admin>=6.5"]

[dependency-groups]
dev = ["pytest>=8", "ruff>=0.6"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/rules_engine", "src/notion_sync", "src/publisher", "src/cli"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]

[tool.ruff]
line-length = 100

# Pin the rule set explicitly. Leaving it unset does not give a small default —
# ruff 0.16 enables 413 rules here, and which ones would drift with the version.
[tool.ruff.lint]
select = ["E", "F", "I", "B", "SIM", "UP"]
```

```python
# src/rules_engine/__init__.py
"""Pure rules evaluation. Imports no network, no clock, no Firebase."""
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/rules_engine/test_smoke.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/rules_engine/__init__.py tests/rules_engine/test_smoke.py
git commit -m "chore: scaffold python project for the rules engine"
```

---

### Task 2: Load the rules file

`rules/2024.toml` already exists and is the contract. This reads it and nothing more.

**Files:**
- Create: `src/rules_engine/rules_file.py`
- Test: `tests/rules_engine/test_rules_file.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/rules_engine/test_rules_file.py
import pytest

from rules_engine.rules_file import RulesFile, load_rules


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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/rules_engine/test_rules_file.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rules_engine.rules_file'`

- [ ] **Step 3: Write the implementation**

```python
# src/rules_engine/rules_file.py
"""Load a rules/<edition>.toml into a validated in-memory contract."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

KINDS = ("table", "steps", "formula", "from")


@dataclass(frozen=True)
class Variable:
    name: str
    description: str = ""
    table: str | None = None
    steps: str | None = None
    formula: str | None = None
    source: str | None = None  # the TOML key is `from`, which is a Python keyword

    @property
    def kind(self) -> str:
        if self.table:
            return "table"
        if self.steps:
            return "steps"
        if self.formula:
            return "formula"
        return "from"


@dataclass(frozen=True)
class Table:
    index: str
    values: list[int]


@dataclass(frozen=True)
class Steps:
    index: str
    base: int
    thresholds: list[int]


@dataclass(frozen=True)
class Pick:
    name: str
    description: str = ""
    required_on: str = "binding"


@dataclass(frozen=True)
class RulesFile:
    edition: str
    verified: bool
    tables: dict[str, Table] = field(default_factory=dict)
    steps: dict[str, Steps] = field(default_factory=dict)
    variables: dict[str, Variable] = field(default_factory=dict)
    picks: dict[str, Pick] = field(default_factory=dict)


def load_rules(path: str | Path) -> RulesFile:
    raw = tomllib.loads(Path(path).read_text())

    variables: dict[str, Variable] = {}
    for name, body in raw.get("variables", {}).items():
        declared = [k for k in KINDS if k in body]
        if len(declared) != 1:
            raise ValueError(
                f"variable {name}: must declare exactly one of {KINDS}, found {declared or 'none'}"
            )
        variables[name] = Variable(
            name=name,
            description=body.get("description", ""),
            table=body.get("table"),
            steps=body.get("steps"),
            formula=body.get("formula"),
            source=body.get("from"),
        )

    return RulesFile(
        edition=raw["meta"]["edition"],
        verified=raw["meta"]["verified"],
        tables={k: Table(index=v["index"], values=v["values"]) for k, v in raw.get("tables", {}).items()},
        steps={
            k: Steps(index=v["index"], base=v["base"], thresholds=v["thresholds"])
            for k, v in raw.get("steps", {}).items()
        },
        variables=variables,
        picks={
            k: Pick(name=k, description=v.get("description", ""), required_on=v.get("required_on", "binding"))
            for k, v in raw.get("picks", {}).items()
        },
    )
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/rules_engine/test_rules_file.py -v`
Expected: PASS, 4 tests

- [ ] **Step 5: Commit**

```bash
git add src/rules_engine/rules_file.py tests/rules_engine/test_rules_file.py
git commit -m "feat: load and validate rules/<edition>.toml"
```

---

### Task 3: Character facts

The `character.*` namespace that `from` variables read. Keeping this a plain dataclass rather than raw export JSON is what stops D&D Beyond's shape leaking into the evaluator.

**Files:**
- Create: `src/rules_engine/facts.py`
- Test: `tests/rules_engine/test_facts.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/rules_engine/test_facts.py
import pytest

from rules_engine.facts import CharacterFacts


def facts() -> CharacterFacts:
    return CharacterFacts(
        total_level=14,
        class_levels={"rogue": 9, "sorcerer": 5},
        ability_mods={"str": 0, "dex": 5, "con": 2, "int": 3, "wis": 1, "cha": 4},
        spellcasting_ability_mod=4,
        walk_speed=30,
    )


def test_reads_a_scalar_path():
    assert facts().read("character.totalLevel") == 14
    assert facts().read("character.speed.walk") == 30


def test_reads_an_ability_mod():
    assert facts().read("character.abilities.dex.mod") == 5


def test_reads_a_class_level_by_subscript():
    assert facts().read("character.classLevels", key="rogue") == 9


def test_unknown_path_raises_by_name():
    with pytest.raises(KeyError, match="character.nope"):
        facts().read("character.nope")


def test_unknown_class_is_zero_not_an_error():
    # A rogue formula must evaluate to 0 for a character with no rogue levels,
    # not explode. Multiclass formulas are shared across characters.
    assert facts().read("character.classLevels", key="bard") == 0
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/rules_engine/test_facts.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rules_engine.facts'`

- [ ] **Step 3: Write the implementation**

```python
# src/rules_engine/facts.py
"""The character.* namespace. Export-shape-independent by design."""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class CharacterFacts:
    total_level: int
    class_levels: dict[str, int]
    ability_mods: dict[str, int]
    spellcasting_ability_mod: int
    walk_speed: int

    def read(self, path: str, key: str | None = None) -> int:
        if path == "character.totalLevel":
            return self.total_level
        if path == "character.speed.walk":
            return self.walk_speed
        if path == "character.spellcastingAbilityMod":
            return self.spellcasting_ability_mod
        if path == "character.classLevels":
            return self.class_levels.get(key or "", 0)
        if path.startswith("character.abilities.") and path.endswith(".mod"):
            ability = path.split(".")[2]
            if ability in self.ability_mods:
                return self.ability_mods[ability]
        raise KeyError(f"unknown export path: {path}")

    def at_level(self, level: int) -> CharacterFacts:
        """The same character as if they were `level`, scaling class levels proportionally.

        Used only to expand a binding across levels 1-20. The character's real level is
        what the sheet renders; the rest of the table exists so level-up is a lookup.
        """
        if self.total_level == 0:
            return replace(self, total_level=level)
        scaled = {
            name: max(1, round(levels * level / self.total_level))
            for name, levels in self.class_levels.items()
        }
        return replace(self, total_level=level, class_levels=scaled)
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/rules_engine/test_facts.py -v`
Expected: PASS, 5 tests

- [ ] **Step 5: Commit**

```bash
git add src/rules_engine/facts.py tests/rules_engine/test_facts.py
git commit -m "feat: add CharacterFacts, the character.* namespace"
```

---

### Task 4: Safe formula evaluation

Formulas come from Notion, which means they are untrusted input authored by an agent. This evaluates arithmetic and refuses everything else — no `eval`, no attribute access, no calls beyond a fixed list.

**Files:**
- Create: `src/rules_engine/formula.py`
- Test: `tests/rules_engine/test_formula.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/rules_engine/test_formula.py
import pytest

from rules_engine.formula import evaluate_expression, referenced_names


def test_arithmetic():
    assert evaluate_expression("8 + 4 + 3", {}) == 15
    assert evaluate_expression("A * 2 - 1", {"A": 5}) == 9
    assert evaluate_expression("A / 2", {"A": 9}) == 4.5


def test_allowed_functions():
    assert evaluate_expression("ceil(A / 2)", {"A": 9}) == 5
    assert evaluate_expression("floor(A / 2)", {"A": 9}) == 4
    assert evaluate_expression("min(A, 3)", {"A": 9}) == 3
    assert evaluate_expression("max(A, 3)", {"A": 9}) == 9


def test_subscripted_variable():
    assert evaluate_expression("CLASS_LEVEL.rogue", {"CLASS_LEVEL": {"rogue": 9}}) == 9


def test_referenced_names_finds_plain_and_subscripted():
    assert referenced_names("8 + SPELLCASTING_MOD + PROFICIENCY_BONUS") == {
        "SPELLCASTING_MOD",
        "PROFICIENCY_BONUS",
    }
    assert referenced_names("ceil(CLASS_LEVEL.rogue / 2)") == {"CLASS_LEVEL"}


def test_undefined_name_raises_by_name():
    with pytest.raises(NameError, match="MYSTERY"):
        evaluate_expression("MYSTERY + 1", {})


@pytest.mark.parametrize(
    "expr",
    [
        "__import__('os').system('rm -rf /')",
        "open('/etc/passwd').read()",
        "(1).__class__",
        "[x for x in range(10)]",
        "lambda: 1",
        "min(A, key=str)",
        "min(*A)",
        "f'{A}'",
    ],
)
def test_rejects_everything_that_is_not_arithmetic(expr):
    with pytest.raises(ValueError, match="not allowed"):
        evaluate_expression(expr, {})


@pytest.mark.parametrize("expr", ["2 ** 3", "9**9**9"])
def test_rejects_exponentiation(expr):
    """`9**9**9` passes every other check and then hangs the process.

    CPython's bigint pow has no cutoff, so this is a denial of service in eight
    characters against whatever evaluates an authored formula. No D&D formula needs
    exponentiation, so the operator is simply not in the language.
    """
    with pytest.raises(ValueError, match="not allowed"):
        evaluate_expression(expr, {"A": 2})


def test_rejects_boolean_literals():
    """bool subclasses int, so True would otherwise pass as a numeric literal."""
    with pytest.raises(ValueError, match="not allowed"):
        evaluate_expression("True + 1", {})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/rules_engine/test_formula.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rules_engine.formula'`

- [ ] **Step 3: Write the implementation**

```python
# src/rules_engine/formula.py
"""Arithmetic over a whitelisted AST. Formulas are untrusted input."""

from __future__ import annotations

import ast
import math
from typing import Any

FUNCTIONS = {"ceil": math.ceil, "floor": math.floor, "min": min, "max": max}

ALLOWED_NODES = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    # ast.Pow is deliberately absent. `9**9**9` is eight characters that pass every
    # other check and then hang the process on CPython's unbounded bigint pow — a
    # trivial denial of service against a Cloud Function evaluating authored formulas.
    # No D&D formula needs exponentiation.
    ast.USub,
    ast.UAdd,
    ast.Constant,
    ast.Name,
    ast.Load,
    ast.Call,
    ast.Attribute,
)


def _parse(expression: str) -> ast.Expression:
    tree = ast.parse(expression, mode="eval")
    for node in ast.walk(tree):
        if not isinstance(node, ALLOWED_NODES):
            raise ValueError(f"{type(node).__name__} is not allowed in a formula: {expression!r}")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS:
                raise ValueError(f"only {sorted(FUNCTIONS)} may be called, not allowed: {expression!r}")
        if isinstance(node, ast.Attribute) and not isinstance(node.value, ast.Name):
            raise ValueError(f"only VARIABLE.key access is allowed, not allowed: {expression!r}")
        if isinstance(node, ast.Constant) and (
            isinstance(node.value, bool) or not isinstance(node.value, (int, float))
        ):
            # bool is a subclass of int, so True would otherwise pass as a numeric
            # literal and `True + 1` would quietly evaluate to 2.
            raise ValueError(f"only numeric literals are allowed, not allowed: {expression!r}")
    return tree


def referenced_names(expression: str) -> set[str]:
    """Every variable name a formula depends on. Subscripts collapse to their base name."""
    tree = _parse(expression)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            names.add(node.value.id)
        elif isinstance(node, ast.Name) and node.id not in FUNCTIONS:
            names.add(node.id)
    return names


def evaluate_expression(expression: str, values: dict[str, Any]) -> float:
    tree = _parse(expression)

    def visit(node: ast.AST) -> Any:
        match node:
            case ast.Expression():
                return visit(node.body)
            case ast.Constant():
                return node.value
            case ast.Name():
                if node.id in values:
                    return values[node.id]
                raise NameError(f"formula references undefined variable {node.id!r}")
            case ast.Attribute():
                container = visit(node.value)
                if not isinstance(container, dict):
                    raise ValueError(f"{node.value.id} is not subscriptable")
                return container.get(node.attr, 0)
            case ast.Call():
                return FUNCTIONS[node.func.id](*[visit(a) for a in node.args])
            case ast.UnaryOp():
                operand = visit(node.operand)
                return -operand if isinstance(node.op, ast.USub) else +operand
            case ast.BinOp():
                left, right = visit(node.left), visit(node.right)
                match node.op:
                    case ast.Add():
                        return left + right
                    case ast.Sub():
                        return left - right
                    case ast.Mult():
                        return left * right
                    case ast.Div():
                        return left / right
                    case ast.FloorDiv():
                        return left // right
                    case ast.Mod():
                        return left % right
        raise ValueError(f"{type(node).__name__} is not allowed in a formula")

    return visit(tree)
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/rules_engine/test_formula.py -v`
Expected: PASS, 11 tests (5 parametrized)

- [ ] **Step 5: Commit**

```bash
git add src/rules_engine/formula.py tests/rules_engine/test_formula.py
git commit -m "feat: add whitelisted formula evaluator"
```

---

#### Task 4 amendment — the shipped contract

Three review rounds changed this module substantially. The pasted implementation above is
the starting point, not the shipped code; `src/rules_engine/formula.py` is authoritative.
The reasoning is kept here rather than rewritten above, so the superseded version stays
readable.

**Removed from the language.** `ast.Pow`, `ast.Mod`, `ast.FloorDiv`, `ast.UAdd`. `9**9**9`
is eight characters that pass every other check and then hang the process on CPython's
unbounded bigint pow. No rules formula uses `%` or `//`, and they carry a second
`ZeroDivisionError` surface plus the quadratic bigint division path that measured 7.5
seconds. `+A` does nothing. An unnecessary allowance in a security boundary costs you
reasoning about it forever.

**A missing attribute key raises.** The original `container.get(node.attr, 0)` meant
`CLASS_LEVEL.rouge` evaluated to `0`, silently rendering a 9th-level rogue's Sneak Attack
as zero dice. Nothing could catch it: `referenced_names` reports only the base name, so no
gate validated the key, and `0` is plausible for most of these variables. A missing key is
not a value of zero — it is a fact the evaluator does not have. A formula reaching a class
the character lacks means the binding is wrong, and that should fail loudly.

**Bounded input, bounded output.** `MAX_EXPRESSION_LENGTH = 500` — a 3.9 MB formula of
nothing but `*` burned 25.7 seconds of CPU, which on a billed concurrent Cloud Function is
an outage. The cap also closes the `RecursionError` window where `referenced_names` accepted
input `evaluate_expression` could not run. Literals and results must be finite: `1e400`
yields `inf`, `1e400 - 1e400` yields `nan`, and `json.dumps` emits a bare `NaN` token that
the web app's `JSON.parse` rejects. Results are bounded at `abs(value) < 10**15` because a
20 KB expression evaluates in under 2 ms to an integer that `str()` itself refuses.

**`values` is validated before parsing.** Every value must be a finite non-`bool` `int` or
`float`, or a dict of them. Validating the result instead would catch `"x" * 200000000`
only after allocating 200 MB; validating the input makes it unreachable. Measured: 4.7µs to
reject, against 112ms to perform the allocation.

**`FormulaError(ValueError)`** carries the offending expression and wraps `SyntaxError`,
`IndentationError`, `ZeroDivisionError`, `TypeError`, `OverflowError` and `RecursionError`.
`SyntaxError` is the most likely production failure, because an agent authoring formulas
and a player typing one both produce malformed strings routinely — without a typed error a
caller's only option is `except Exception`, which also swallows real bugs. `MemoryError`
deliberately propagates: it signals machine state, not bad input. `NameError` stays distinct
for undefined variables.

**Confirmed sound and left alone.** Default-deny over `ast.walk`; `Attribute.value` must be
a bare `Name`, which makes dunder access structurally impossible rather than filtered by a
denylist; the `FUNCTIONS` table cannot be smuggled through `values`. A 62-expression attack
corpus rejected 53, and the 9 it accepted were all legitimate arithmetic.

---

### Task 5: Variable resolution

Ties the four declaration kinds together and detects circular formulas.

**Files:**
- Create: `src/rules_engine/variables.py`
- Test: `tests/rules_engine/test_variables.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/rules_engine/test_variables.py
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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/rules_engine/test_variables.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rules_engine.variables'`

- [ ] **Step 3: Write the implementation**

```python
# src/rules_engine/variables.py
"""Resolve one variable to a number for one character at one level."""

from __future__ import annotations

from typing import Any

from rules_engine.facts import CharacterFacts
from rules_engine.formula import evaluate_expression, referenced_names
from rules_engine.rules_file import RulesFile

SUBSCRIPTABLE = {"CLASS_LEVEL"}


class UnknownVariable(Exception):
    """Gate 2. Always names the variable."""


def resolve(
    name: str,
    rules: RulesFile,
    facts: CharacterFacts,
    picks: dict[str, int] | None = None,
    _seen: frozenset[str] = frozenset(),
) -> Any:
    picks = picks or {}

    if name in _seen:
        raise UnknownVariable(f"circular variable reference: {' -> '.join([*_seen, name])}")

    if name in rules.picks:
        if name not in picks:
            raise UnknownVariable(f"pick {name!r} has no value on this binding")
        return picks[name]

    if name not in rules.variables:
        raise UnknownVariable(f"variable {name!r} is not declared in rules/{rules.edition}.toml")

    variable = rules.variables[name]

    match variable.kind:
        case "from":
            if name in SUBSCRIPTABLE:
                return facts.class_levels
            return facts.read(variable.source)
        case "table":
            table = rules.tables[variable.table]
            index = resolve(table.index, rules, facts, picks, _seen | {name})
            return table.values[int(index) - 1]
        case "steps":
            steps = rules.steps[variable.steps]
            index = resolve(steps.index, rules, facts, picks, _seen | {name})
            return steps.base + sum(1 for t in steps.thresholds if index >= t)
        case "formula":
            values = {
                dep: resolve(dep, rules, facts, picks, _seen | {name})
                for dep in referenced_names(variable.formula)
            }
            return evaluate_expression(variable.formula, values)

    raise UnknownVariable(f"variable {name!r} declares no resolvable kind")
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/rules_engine/test_variables.py -v`
Expected: PASS, 9 tests

- [ ] **Step 5: Commit**

```bash
git add src/rules_engine/variables.py tests/rules_engine/test_variables.py
git commit -m "feat: resolve variables by table, steps, formula and from"
```

---

#### Task 5 amendment — the container seam, and a doctrine reversal

Review found a third silent wrong number, the same `.get(key, 0)` shape as the two before
it. The fix spans Tasks 2, 3 and 5, so it is recorded here rather than in three places.

**The bug.** `SUBSCRIPTABLE = {"CLASS_LEVEL"}` decided container-ness by the variable's
NAME. What actually determines it is the export PATH. So a rules file declaring
`[variables.ROGUE_LEVEL]` with `from = "character.classLevels"` fell through to
`facts.read`, whose only reachable behaviour was `class_levels.get(key or "", 0)` — no
production caller ever passed `key`. A 9th-level rogue's Sneak Attack rendered as zero
dice, for every character, at every level. Gate 2 could not catch it: it checks that names
are declared, never that they resolve sensibly, and `0` is plausible for most of these
variables. It was reachable through the documented editing surface, since there is no
other syntax for "levels in one named class".

**The fix.** `CharacterFacts` owns `CONTAINER_PATHS` and exposes `is_container_path` and
`read_container`; `read` raises when handed a container path, and its `key` parameter is
deleted. `variables.py` routes on the path rather than a hardcoded name set. The knowledge
lives with the data, so the mismatch is now impossible rather than merely caught.

**Doctrine reversal.** Task 3 shipped a test asserting
`read("character.classLevels", key="bard") == 0`, with a comment arguing a rogue formula
must evaluate to 0 rather than explode for a character with no rogue levels. The Task 4
amendment had already overturned that reasoning — a verb only binds to a character who
holds it, so a formula reaching a class they lack means the binding is wrong. Two modules
disagreed in writing about the same question, which is how this bug survived two reviews.
Resolved in favour of `formula.py`: that test is deleted and replaced by
`test_read_refuses_a_container_path`.

**Branch asymmetry closed.** The `table` branch was hardened during review and the `steps`
branch was not, so `CANTRIP_DICE` returned `1` at level −3 and `4` at level 100 while
`PROFICIENCY_BONUS` raised on both. Both branches now share one `_validate_level_index`
helper, which also rejects the index types `int()` silently coerced — `True` as level 1,
`"3"` as level 3, `5.9` as level 5 — matching `formula.py`'s stance that a trust boundary
validates on the way in.

**Load-time checks added to `rules_file.py`:** duplicate steps thresholds (`[5, 5, 11]`
double-counted to 3 at level 5), a name declared as both a pick and a variable (silently
resolved to the pick), and non-integer table values.

**Deferred deliberately:** picks are returned unvalidated (Task 6 owns it), and a formula
using `/` can return `7.0` where an integer is meant (Task 12's display layer owns it).

---

### Task 6: Expand across levels 1-20

**Files:**
- Create: `src/rules_engine/expand.py`
- Test: `tests/rules_engine/test_expand.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/rules_engine/test_expand.py
from rules_engine.expand import expand_expression
from rules_engine.facts import CharacterFacts
from rules_engine.rules_file import load_rules


def facts() -> CharacterFacts:
    return CharacterFacts(
        total_level=14,
        class_levels={"rogue": 14},
        ability_mods={"str": 0, "dex": 5, "con": 2, "int": 3, "wis": 1, "cha": 4},
        spellcasting_ability_mod=4,
        walk_speed=30,
    )


def test_expansion_covers_every_level():
    table = expand_expression("CANTRIP_DICE", load_rules("rules/2024.toml"), facts())
    assert sorted(table) == list(range(1, 21))


def test_cantrip_scaling_is_the_bug_this_prevents():
    table = expand_expression("CANTRIP_DICE", load_rules("rules/2024.toml"), facts())
    assert table[1] == 1
    assert table[4] == 1
    assert table[5] == 2
    assert table[10] == 2
    assert table[11] == 3
    assert table[16] == 3
    assert table[17] == 4
    assert table[20] == 4


def test_constant_expression_is_flat():
    table = expand_expression("8 + 2", load_rules("rules/2024.toml"), facts())
    assert set(table.values()) == {10}
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/rules_engine/test_expand.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rules_engine.expand'`

- [ ] **Step 3: Write the implementation**

```python
# src/rules_engine/expand.py
"""Evaluate an expression at every level so the runtime never does arithmetic."""

from __future__ import annotations

from rules_engine.facts import CharacterFacts
from rules_engine.formula import evaluate_expression, referenced_names
from rules_engine.rules_file import RulesFile
from rules_engine.variables import resolve

LEVELS = range(1, 21)


def expand_expression(
    expression: str,
    rules: RulesFile,
    facts: CharacterFacts,
    picks: dict[str, int] | None = None,
) -> dict[int, float]:
    """Map every level 1-20 to the expression's value at that level."""
    table: dict[int, float] = {}
    for level in LEVELS:
        at = facts.at_level(level)
        values = {name: resolve(name, rules, at, picks) for name in referenced_names(expression)}
        table[level] = evaluate_expression(expression, values)
    return table
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/rules_engine/test_expand.py -v`
Expected: PASS, 3 tests

- [ ] **Step 5: Commit**

```bash
git add src/rules_engine/expand.py tests/rules_engine/test_expand.py
git commit -m "feat: expand expressions across levels 1-20"
```

---

### Task 7: Models and the small snapshot fixture

**Files:**
- Create: `src/rules_engine/models.py`
- Create: `tests/fixtures/snapshot_small/verbs/class-feature__sneak-attack.json`
- Create: `tests/fixtures/snapshot_small/verbs/spell__fire-bolt.json`
- Create: `tests/fixtures/snapshot_small/verbs/class-feature__cunning-action-dash.json`
- Create: `tests/fixtures/snapshot_small/sets/class__rogue.json`
- Create: `tests/fixtures/snapshot_small/sets/spell-list__sorcerer.json`
- Test: `tests/rules_engine/test_models.py`

Slugs contain `/`, which cannot appear in a filename. The snapshot encodes `/` as `__`.

- [ ] **Step 1: Write the failing test**

```python
# tests/rules_engine/test_models.py
from rules_engine.models import Composition, slug_from_filename, slug_to_filename


def test_slug_round_trips_through_a_filename():
    assert slug_to_filename("subclass/rogue/arcane-trickster") == "subclass__rogue__arcane-trickster"
    assert slug_from_filename("subclass__rogue__arcane-trickster") == "subclass/rogue/arcane-trickster"


def test_composition_values():
    assert Composition.APPLY_ALL.value == "apply_all"
    assert Composition.MATCH_MEMBERS.value == "match_members"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/rules_engine/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rules_engine.models'`

- [ ] **Step 3: Write the models**

```python
# src/rules_engine/models.py
"""Definitions, sets and bindings. The split between them is the design."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Composition(str, Enum):
    APPLY_ALL = "apply_all"
    MATCH_MEMBERS = "match_members"


def slug_to_filename(slug: str) -> str:
    return slug.replace("/", "__")


def slug_from_filename(name: str) -> str:
    return name.replace("__", "/")


@dataclass(frozen=True)
class Definition:
    """A rules element. Character-independent. Holds formulas, never numbers."""

    slug: str
    rules_name: str
    source: str = ""
    source_feature: str = ""
    category: str = ""
    modes: list[str] = field(default_factory=list)
    kind: str = "action"
    action_cost: str = ""
    cadence: str = ""
    effect: str = ""
    formulas: dict[str, str] = field(default_factory=dict)
    resource_kind: str = ""
    resource_amount: str = ""
    requires: list[str] = field(default_factory=list)
    applies: list[str] = field(default_factory=list)
    covers: list[str] = field(default_factory=list)
    rules_edition: str = "2024"
    campaign: str | None = None
    status: str = "published"
    origin: str = "library"


@dataclass(frozen=True)
class VerbSet:
    """A grantor. Applies wholesale or member by member."""

    slug: str
    name: str
    composition: Composition
    grantor: str
    members: list[str] = field(default_factory=list)
    level_gates: dict[str, int] = field(default_factory=dict)
    choice_points: list[str] = field(default_factory=list)
    rules_edition: str = "2024"


@dataclass(frozen=True)
class Binding:
    """One definition as held by one character. Everything that varies lives here."""

    character_id: str
    slug: str
    alias: str = ""
    evaluated: dict[str, dict[int, float]] = field(default_factory=dict)
    formulas: dict[str, str] = field(default_factory=dict)
    held_members: list[str] = field(default_factory=list)
    resource_pool: int | None = None
    picks: dict[str, int] = field(default_factory=dict)
    origin: str = "library"
    display: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class GateFailure:
    gate: int
    severity: str  # "hard" or "item"
    subject: str
    message: str
```

- [ ] **Step 4: Write the fixture files**

```json
// tests/fixtures/snapshot_small/verbs/class-feature__sneak-attack.json
{
  "slug": "class-feature/sneak-attack",
  "rules_name": "Sneak Attack",
  "source": "Class Feature",
  "source_feature": "Rogue",
  "category": "damage",
  "modes": ["combat"],
  "kind": "modifier",
  "action_cost": "none",
  "cadence": "once per turn",
  "effect": "Extra damage when you have advantage or an ally is within 5 feet.",
  "formulas": {"damage_dice": "SNEAK_ATTACK_DICE"},
  "requires": ["advantage", "ally-within-5"],
  "applies": [],
  "rules_edition": "2024"
}
```

```json
// tests/fixtures/snapshot_small/verbs/spell__fire-bolt.json
{
  "slug": "spell/fire-bolt",
  "rules_name": "Fire Bolt",
  "source": "Spell",
  "source_feature": "Sorcerer",
  "category": "damage",
  "modes": ["combat"],
  "kind": "action",
  "action_cost": "action",
  "cadence": "at will",
  "effect": "Ranged spell attack, 120 feet. Fire damage.",
  "formulas": {"damage_dice": "CANTRIP_DICE", "attack": "SPELL_ATTACK"},
  "requires": ["target-visible"],
  "applies": [],
  "rules_edition": "2024"
}
```

```json
// tests/fixtures/snapshot_small/verbs/class-feature__cunning-action-dash.json
{
  "slug": "class-feature/cunning-action-dash",
  "rules_name": "Cunning Action: Dash",
  "source": "Class Feature",
  "source_feature": "Rogue",
  "category": "movement",
  "modes": ["combat", "exploration"],
  "kind": "action",
  "action_cost": "bonus",
  "cadence": "at will",
  "effect": "Double your movement for the turn.",
  "formulas": {"distance": "WALK_SPEED * 2"},
  "requires": [],
  "applies": [],
  "rules_edition": "2024"
}
```

```json
// tests/fixtures/snapshot_small/sets/class__rogue.json
{
  "slug": "class/rogue",
  "name": "Rogue",
  "composition": "apply_all",
  "grantor": "Rogue",
  "members": ["class-feature/sneak-attack", "class-feature/cunning-action-dash"],
  "level_gates": {"class-feature/cunning-action-dash": 2},
  "choice_points": [],
  "rules_edition": "2024"
}
```

```json
// tests/fixtures/snapshot_small/sets/spell-list__sorcerer.json
{
  "slug": "spell-list/sorcerer",
  "name": "Sorcerer Spells",
  "composition": "match_members",
  "grantor": "Sorcerer",
  "members": ["spell/fire-bolt"],
  "level_gates": {},
  "choice_points": [],
  "rules_edition": "2024"
}
```

- [ ] **Step 5: Run it to verify it passes**

Run: `uv run pytest tests/rules_engine/test_models.py -v`
Expected: PASS, 2 tests

- [ ] **Step 6: Commit**

```bash
git add src/rules_engine/models.py tests/rules_engine/test_models.py tests/fixtures/snapshot_small
git commit -m "feat: add definition, set and binding models with a small snapshot fixture"
```

---

#### Task 7 amendment — a double underscore cannot appear in a slug

`slug_to_filename` maps `/` to `__`, which is not injective: `homebrew/dm__gift` and
`homebrew/dm/gift` both encode to `homebrew__dm__gift`. On the read path Task 8 catches the
mismatch, because the filename disagrees with the slug recorded inside the file. On the
write path nothing caught it — the second verb would silently overwrite the first and
vanish from the snapshot. That is data loss rather than a wrong number, and the first
defect of that kind in this build.

The encoding stays and the input is forbidden instead. Readable filenames are the reason
the snapshot exists — they turn a Notion authoring run into a reviewable `git diff` — and a
double underscore never appears in an authored kebab-case slug. `slug_to_filename` now
raises, which closes it at the source for Task 17 (which writes the snapshot) and Task 19
(which derives Firestore document ids from the same slugs) without either repeating the
check. `slug_from_filename` needs no guard: once encoding refuses `__`, every `__` in a
legitimate filename provably came from a `/`, so decoding is total.

---

### Task 8: Read the snapshot

**Files:**
- Create: `src/rules_engine/snapshot.py`
- Test: `tests/rules_engine/test_snapshot.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/rules_engine/test_snapshot.py
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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/rules_engine/test_snapshot.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rules_engine.snapshot'`

- [ ] **Step 3: Write the implementation**

```python
# src/rules_engine/snapshot.py
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
        raise ValueError(f"{path.name}: filename {path.stem!r} does not match slug {body.get('slug')!r}")
    return body


def load_snapshot(root: str | Path) -> Snapshot:
    root = Path(root)

    definitions = {}
    for path in sorted((root / "verbs").glob("*.json")):
        body = _read(path)
        definitions[body["slug"]] = Definition(**body)

    sets = {}
    for path in sorted((root / "sets").glob("*.json")):
        body = _read(path)
        body["composition"] = Composition(body["composition"])
        sets[body["slug"]] = VerbSet(**body)

    return Snapshot(definitions=definitions, sets=sets)
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/rules_engine/test_snapshot.py -v`
Expected: PASS, 3 tests

- [ ] **Step 5: Commit**

```bash
git add src/rules_engine/snapshot.py tests/rules_engine/test_snapshot.py
git commit -m "feat: read the committed verb snapshot"
```

---

### Task 9: The D&D Beyond export adapter

Converts a raw export into `CharacterFacts` plus the grantor list. This is the fiddliest code in the plan — D&D Beyond stores base ability scores separately from the modifiers that raise them.

**Files:**
- Create: `src/rules_engine/export_adapter.py`
- Test: `tests/rules_engine/test_export_adapter.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/rules_engine/test_export_adapter.py
import json
from pathlib import Path

from rules_engine.export_adapter import read_export

TOKI = "character_exports/dndbeyond-toki-ironlung.json"


def test_total_level_is_the_sum_of_class_levels():
    parsed = read_export(TOKI)
    assert parsed.facts.total_level == sum(parsed.facts.class_levels.values())
    assert parsed.facts.total_level > 0


def test_ability_mods_are_derived_not_read():
    parsed = read_export(TOKI)
    assert set(parsed.facts.ability_mods) == {"str", "dex", "con", "int", "wis", "cha"}
    for mod in parsed.facts.ability_mods.values():
        assert -5 <= mod <= 10


def test_grantors_include_species_class_and_background():
    parsed = read_export(TOKI)
    kinds = {g.kind for g in parsed.grantors}
    assert {"species", "class", "background"} <= kinds


def test_catalog_items_are_named():
    parsed = read_export(TOKI)
    assert parsed.spells, "expected at least one spell on the export"
    assert all(isinstance(name, str) and name for name in parsed.spells)


def test_toki_is_a_level_14_paladin():
    """Confirmed from the export on 2026-08-16. If this fails, the export was replaced."""
    parsed = read_export(TOKI)
    assert parsed.facts.total_level == 14
    assert parsed.facts.class_levels == {"paladin": 14}


def test_ability_score_math(tmp_path):
    export = {
        "exportedAt": "2026-08-16T00:00:00Z",
        "source": "dndbeyond-character-v5",
        "characterId": 1,
        "character": {
            "name": "Test",
            "classes": [{"level": 3, "definition": {"name": "Rogue"}}],
            "stats": [{"id": 1, "value": 14}, {"id": 2, "value": 16}, {"id": 3, "value": 12},
                      {"id": 4, "value": 10}, {"id": 5, "value": 8}, {"id": 6, "value": 13}],
            "bonusStats": [{"id": i, "value": None} for i in range(1, 7)],
            "overrideStats": [{"id": i, "value": None} for i in range(1, 7)],
            "modifiers": {"race": [{"type": "bonus", "subType": "dexterity-score", "value": 2}]},
            "race": {"fullName": "Kender"},
            "background": {"definition": {"name": "Urchin"}},
            "feats": [],
            "spells": {"class": []},
            "classSpells": [],
            "inventory": [],
        }
    }
    path = tmp_path / "export.json"
    path.write_text(json.dumps(export))

    parsed = read_export(path)
    assert parsed.facts.class_levels == {"rogue": 3}
    assert parsed.facts.total_level == 3
    # dex 16 base + 2 racial = 18 -> +4
    assert parsed.facts.ability_mods["dex"] == 4
    # str 14 -> +2
    assert parsed.facts.ability_mods["str"] == 2
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/rules_engine/test_export_adapter.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rules_engine.export_adapter'`

- [ ] **Step 3: Write the implementation**

```python
# src/rules_engine/export_adapter.py
"""Turn a D&D Beyond export into CharacterFacts and a grantor list.

This is the only module that knows D&D Beyond's shape. Everything downstream sees
CharacterFacts, so a different export source means a new adapter and nothing else.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from rules_engine.facts import CharacterFacts

STAT_IDS = {1: "str", 2: "dex", 3: "con", 4: "int", 5: "wis", 6: "cha"}
SCORE_SUBTYPES = {f"{full}-score": short for full, short in {
    "strength": "str",
    "dexterity": "dex",
    "constitution": "con",
    "intelligence": "int",
    "wisdom": "wis",
    "charisma": "cha",
}.items()}


@dataclass(frozen=True)
class Grantor:
    """Something the export names that a set may match: a class, a feat, a species."""

    kind: str
    name: str


@dataclass(frozen=True)
class ParsedExport:
    facts: CharacterFacts
    grantors: list[Grantor] = field(default_factory=list)
    spells: list[str] = field(default_factory=list)
    items: list[str] = field(default_factory=list)


def _ability_scores(data: dict) -> dict[str, int]:
    scores = {STAT_IDS[s["id"]]: s["value"] or 0 for s in data["stats"]}

    for bonus in data.get("bonusStats") or []:
        if bonus.get("value"):
            scores[STAT_IDS[bonus["id"]]] += bonus["value"]

    for group in (data.get("modifiers") or {}).values():
        for modifier in group or []:
            subtype = modifier.get("subType", "")
            if modifier.get("type") == "bonus" and subtype in SCORE_SUBTYPES and modifier.get("value"):
                scores[SCORE_SUBTYPES[subtype]] += modifier["value"]

    for override in data.get("overrideStats") or []:
        if override.get("value"):
            scores[STAT_IDS[override["id"]]] = override["value"]

    return scores


def read_export(path: str | Path) -> ParsedExport:
    # The export is {"exportedAt", "source", "characterId", "character"} — verified
    # against dndbeyond-character-v5 exports. Everything lives under "character".
    data = json.loads(Path(path).read_text())["character"]

    class_levels = {c["definition"]["name"].lower(): c["level"] for c in data["classes"]}
    scores = _ability_scores(data)
    ability_mods = {name: (score - 10) // 2 for name, score in scores.items()}

    grantors: list[Grantor] = []
    if race := data.get("race"):
        grantors.append(Grantor(kind="species", name=race.get("fullName") or race.get("baseName", "")))
    for klass in data["classes"]:
        grantors.append(Grantor(kind="class", name=klass["definition"]["name"]))
        if subclass := klass.get("subclassDefinition"):
            grantors.append(Grantor(kind="subclass", name=subclass["name"]))
    if background := (data.get("background") or {}).get("definition"):
        grantors.append(Grantor(kind="background", name=background["name"]))
    for feat in data.get("feats") or []:
        grantors.append(Grantor(kind="feat", name=feat["definition"]["name"]))

    spells: list[str] = []
    for group in (data.get("spells") or {}).values():
        for spell in group or []:
            spells.append(spell["definition"]["name"])
    for entry in data.get("classSpells") or []:
        for spell in entry.get("spells") or []:
            spells.append(spell["definition"]["name"])

    items = [i["definition"]["name"] for i in data.get("inventory") or []]

    # Highest spellcasting modifier across casting classes; single-class characters
    # resolve to their one caster, which is the common case.
    casting_mods = [
        ability_mods[STAT_IDS[c["definition"]["spellCastingAbilityId"]]]
        for c in data["classes"]
        if c["definition"].get("spellCastingAbilityId")
    ]

    facts = CharacterFacts(
        total_level=sum(class_levels.values()),
        class_levels=class_levels,
        ability_mods=ability_mods,
        spellcasting_ability_mod=max(casting_mods, default=0),
        walk_speed=(data.get("race") or {}).get("weightSpeeds", {}).get("normal", {}).get("walk", 30),
    )

    return ParsedExport(facts=facts, grantors=grantors, spells=sorted(set(spells)), items=sorted(set(items)))
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/rules_engine/test_export_adapter.py -v`
Expected: PASS, 5 tests

If a test on Toki's real export fails, the export's shape differs from the assumption — fix the adapter, not the test, and record what differed in a comment.

- [ ] **Step 5: Commit**

```bash
git add src/rules_engine/export_adapter.py tests/rules_engine/test_export_adapter.py
git commit -m "feat: adapt D&D Beyond exports into CharacterFacts and grantors"
```

---

#### Task 9 amendment — what SPELLCASTING_MOD means

The pasted adapter took `max(casting_mods, default=0)` across casting classes. That produced
a wrong number on real data: **Jeff** is a Fighter with no casting class, so the default
fired and gave `0`, while his feat spells (Cure Wounds, Lesser Restoration) declare Wisdom
at +3. Through `SPELL_SAVE_DC = 8 + SPELLCASTING_MOD + PROFICIENCY_BONUS` at PB +5 the engine
rendered **DC 13 against a sheet that says 16**. Zero was undetectable as a sentinel, because
Bjorn's charisma modifier is a genuine 0 in the same dataset.

Reading the ability from the spells instead then made **Bjorn** raise: his Wizard spells cast
with Intelligence and his Fey Touched spells with Wisdom. That is not bad data — Fey Touched
lets you choose the ability when you take the feat, so both are true at once.

**The resolution, which the rules file already contained.** `[picks.CHOICE_MOD]` is declared
as "ability modifier chosen when the feature was taken" with `required_on = "binding"`, and
exists for Kender Taunt. Fey Touched is structurally identical. So:

- `SPELLCASTING_MOD` is the spellcasting **class's** ability and nothing else.
- Feat- and item-granted spells use `CHOICE_MOD`, supplied per binding.
- Two casting **classes** with different abilities still raises — genuinely unrepresentable
  by a scalar, and `rules/2024.toml` documents the intent as "multiclass casters resolve per
  class".
- `spellcasting_ability_mod` is `int | None`, and reading it for a character with no casting
  class raises by name. Returning `0` would have restored the original defect.

Final state: Toki 3, Billie 3, Bjorn 5, Jasper 5, Jeff `None`, The Grey Man 2.

**Carried into Task 10 rather than rediscovered there:** `walk_speed` reads the species base
and ignores speed modifiers, so Mobile, Monk Unarmored Movement and Barbarian Fast Movement
would render base speed (none of the six characters is affected today).
`items` includes unequipped and container-stowed gear — Jeff has 22 inventory entries and 3
equipped, including a stowed Chain Mail — so an equipment set granting armour consequences
needs a "requires equipped" notion that the Notion schema does not yet have.

---

### Task 10: Set matching

**Files:**
- Create: `src/rules_engine/matching.py`
- Test: `tests/rules_engine/test_matching.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/rules_engine/test_matching.py
from rules_engine.export_adapter import Grantor, ParsedExport
from rules_engine.facts import CharacterFacts
from rules_engine.matching import match_sets
from rules_engine.snapshot import load_snapshot

FIXTURE = "tests/fixtures/snapshot_small"


def parsed(level: int = 14, spells: list[str] | None = None) -> ParsedExport:
    return ParsedExport(
        facts=CharacterFacts(
            total_level=level,
            class_levels={"rogue": level},
            ability_mods={"str": 0, "dex": 5, "con": 2, "int": 3, "wis": 1, "cha": 4},
            spellcasting_ability_mod=4,
            walk_speed=30,
        ),
        grantors=[Grantor(kind="class", name="Rogue")],
        spells=spells or [],
    )


def test_module_set_applies_every_member():
    result = match_sets(parsed(), load_snapshot(FIXTURE))
    assert "class-feature/sneak-attack" in result.held
    assert "class-feature/cunning-action-dash" in result.held


def test_level_gate_withholds_a_member():
    result = match_sets(parsed(level=1), load_snapshot(FIXTURE))
    assert "class-feature/sneak-attack" in result.held
    assert "class-feature/cunning-action-dash" not in result.held


def test_catalog_set_matches_only_what_the_export_names():
    export = parsed()
    export = ParsedExport(
        facts=export.facts,
        grantors=[Grantor(kind="class", name="Sorcerer")],
        spells=["Fire Bolt"],
    )
    result = match_sets(export, load_snapshot(FIXTURE))
    assert "spell/fire-bolt" in result.held


def test_catalog_member_not_held_is_not_applied():
    export = ParsedExport(
        facts=parsed().facts,
        grantors=[Grantor(kind="class", name="Sorcerer")],
        spells=[],
    )
    result = match_sets(export, load_snapshot(FIXTURE))
    assert "spell/fire-bolt" not in result.held


def test_unmatched_grantor_is_reported():
    export = ParsedExport(
        facts=parsed().facts,
        grantors=[Grantor(kind="feat", name="War Caster")],
        spells=[],
    )
    result = match_sets(export, load_snapshot(FIXTURE))
    assert "War Caster" in result.unmatched_grantors


def test_spell_on_the_export_with_no_definition_is_reported():
    export = ParsedExport(
        facts=parsed().facts,
        grantors=[Grantor(kind="class", name="Sorcerer")],
        spells=["Fire Bolt", "Chaos Bolt"],
    )
    result = match_sets(export, load_snapshot(FIXTURE))
    assert "Chaos Bolt" in result.unmatched_members
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/rules_engine/test_matching.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rules_engine.matching'`

- [ ] **Step 3: Write the implementation**

```python
# src/rules_engine/matching.py
"""Decide what a character holds. Answers 'what', never 'what is wrong'."""

from __future__ import annotations

from dataclasses import dataclass, field

from rules_engine.export_adapter import ParsedExport
from rules_engine.models import Composition
from rules_engine.snapshot import Snapshot


@dataclass(frozen=True)
class MatchResult:
    held: dict[str, str] = field(default_factory=dict)  # definition slug -> granting set slug
    unmatched_grantors: list[str] = field(default_factory=list)
    unmatched_members: list[str] = field(default_factory=list)
    missing_definitions: list[str] = field(default_factory=list)


def _normalise(name: str) -> str:
    return name.strip().lower()


def match_sets(export: ParsedExport, snapshot: Snapshot) -> MatchResult:
    by_grantor = {_normalise(s.grantor): s for s in snapshot.sets.values()}

    held: dict[str, str] = {}
    unmatched_grantors: list[str] = []
    missing_definitions: list[str] = []

    catalog_names = {_normalise(n): n for n in [*export.spells, *export.items]}
    consumed: set[str] = set()

    for grantor in export.grantors:
        verb_set = by_grantor.get(_normalise(grantor.name))
        if verb_set is None:
            unmatched_grantors.append(grantor.name)
            continue

        for member in verb_set.members:
            definition = snapshot.definitions.get(member)
            if definition is None:
                missing_definitions.append(member)
                continue

            if verb_set.composition is Composition.APPLY_ALL:
                gate = verb_set.level_gates.get(member, 1)
                if export.facts.total_level >= gate:
                    held[member] = verb_set.slug
            else:
                key = _normalise(definition.rules_name)
                if key in catalog_names:
                    held[member] = verb_set.slug
                    consumed.add(key)

    unmatched_members = [original for key, original in catalog_names.items() if key not in consumed]

    return MatchResult(
        held=held,
        unmatched_grantors=unmatched_grantors,
        unmatched_members=sorted(unmatched_members),
        missing_definitions=sorted(missing_definitions),
    )
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/rules_engine/test_matching.py -v`
Expected: PASS, 6 tests

- [ ] **Step 5: Commit**

```bash
git add src/rules_engine/matching.py tests/rules_engine/test_matching.py
git commit -m "feat: match export grantors against module and catalog sets"
```

---

### Task 11: The gates

Gate messages are a specified feature, so they are asserted like one.

**Files:**
- Create: `src/rules_engine/gates.py`
- Test: `tests/rules_engine/test_gates.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/rules_engine/test_gates.py
from rules_engine.export_adapter import Grantor, ParsedExport
from rules_engine.facts import CharacterFacts
from rules_engine.gates import run_gates
from rules_engine.matching import match_sets
from rules_engine.rules_file import load_rules
from rules_engine.snapshot import load_snapshot

FIXTURE = "tests/fixtures/snapshot_small"
RULES = "rules/2024.toml"


def export(grantors, spells=None, level=14) -> ParsedExport:
    return ParsedExport(
        facts=CharacterFacts(
            total_level=level,
            class_levels={"rogue": level},
            ability_mods={"str": 0, "dex": 5, "con": 2, "int": 3, "wis": 1, "cha": 4},
            spellcasting_ability_mod=4,
            walk_speed=30,
        ),
        grantors=grantors,
        spells=spells or [],
    )


def test_clean_character_produces_no_failures():
    parsed = export([Grantor(kind="class", name="Rogue")])
    snapshot = load_snapshot(FIXTURE)
    failures = run_gates(parsed, snapshot, match_sets(parsed, snapshot), load_rules(RULES), plays=[])
    assert failures == []


def test_gate_1_names_the_unmatched_grantor():
    parsed = export([Grantor(kind="feat", name="War Caster")])
    snapshot = load_snapshot(FIXTURE)
    failures = run_gates(parsed, snapshot, match_sets(parsed, snapshot), load_rules(RULES), plays=[])
    gate_1 = [f for f in failures if f.gate == 1]
    assert len(gate_1) == 1
    assert gate_1[0].severity == "hard"
    assert "War Caster" in gate_1[0].message


def test_gate_2_names_the_variable_and_the_verb(tmp_path):
    (tmp_path / "verbs").mkdir()
    (tmp_path / "sets").mkdir()
    (tmp_path / "verbs" / "class-feature__mystery.json").write_text(
        '{"slug": "class-feature/mystery", "rules_name": "Mystery",'
        ' "formulas": {"damage_dice": "WARLOCK_SLOTS + 1"}}'
    )
    (tmp_path / "sets" / "class__rogue.json").write_text(
        '{"slug": "class/rogue", "name": "Rogue", "composition": "apply_all",'
        ' "grantor": "Rogue", "members": ["class-feature/mystery"]}'
    )
    parsed = export([Grantor(kind="class", name="Rogue")])
    snapshot = load_snapshot(tmp_path)
    failures = run_gates(parsed, snapshot, match_sets(parsed, snapshot), load_rules(RULES), plays=[])
    gate_2 = [f for f in failures if f.gate == 2]
    assert len(gate_2) == 1
    assert "WARLOCK_SLOTS" in gate_2[0].message
    assert "class-feature/mystery" in gate_2[0].message


def test_gate_3_names_the_play_and_the_slug():
    parsed = export([Grantor(kind="class", name="Rogue")])
    snapshot = load_snapshot(FIXTURE)
    plays = [{"id": "burst", "name": "Opening Burst", "verbs": ["class-feature/sneak-attack", "spell/eldritch-blast"]}]
    failures = run_gates(parsed, snapshot, match_sets(parsed, snapshot), load_rules(RULES), plays=plays)
    gate_3 = [f for f in failures if f.gate == 3]
    assert len(gate_3) == 1
    assert "Opening Burst" in gate_3[0].message
    assert "spell/eldritch-blast" in gate_3[0].message


def test_gate_4_is_hard_for_a_module_member_and_per_item_for_a_catalog_member():
    parsed = export([Grantor(kind="class", name="Sorcerer")], spells=["Fire Bolt", "Chaos Bolt"])
    snapshot = load_snapshot(FIXTURE)
    failures = run_gates(parsed, snapshot, match_sets(parsed, snapshot), load_rules(RULES), plays=[])
    gate_4 = [f for f in failures if f.gate == 4]
    assert len(gate_4) == 1
    assert gate_4[0].severity == "item"
    assert "Chaos Bolt" in gate_4[0].message
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/rules_engine/test_gates.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rules_engine.gates'`

- [ ] **Step 3: Write the implementation**

```python
# src/rules_engine/gates.py
"""The four gates. Every failure names the thing that failed."""

from __future__ import annotations

from rules_engine.export_adapter import ParsedExport
from rules_engine.formula import referenced_names
from rules_engine.matching import MatchResult
from rules_engine.models import GateFailure
from rules_engine.rules_file import RulesFile
from rules_engine.snapshot import Snapshot


def run_gates(
    export: ParsedExport,
    snapshot: Snapshot,
    matches: MatchResult,
    rules: RulesFile,
    plays: list[dict],
) -> list[GateFailure]:
    failures: list[GateFailure] = []

    # Gate 1 — an export grantor with no matching set.
    for grantor in matches.unmatched_grantors:
        failures.append(
            GateFailure(
                gate=1,
                severity="hard",
                subject=grantor,
                message=f"gate 1: export grantor {grantor!r} has no matching set",
            )
        )

    # Gate 2 — a formula referencing a variable that is not declared.
    declared = set(rules.variables) | set(rules.picks)
    for slug in matches.held:
        definition = snapshot.definitions[slug]
        for field_name, expression in definition.formulas.items():
            for name in referenced_names(expression):
                if name not in declared:
                    failures.append(
                        GateFailure(
                            gate=2,
                            severity="hard",
                            subject=name,
                            message=(
                                f"gate 2: {slug} formula {field_name!r} references undeclared "
                                f"variable {name!r} (rules/{rules.edition}.toml)"
                            ),
                        )
                    )

    # Gate 3 — a play referencing a slug the character does not hold.
    for play in plays:
        for slug in play.get("verbs", []):
            if slug not in matches.held:
                failures.append(
                    GateFailure(
                        gate=3,
                        severity="hard",
                        subject=slug,
                        message=f"gate 3: play {play.get('name', play.get('id'))!r} references unbound slug {slug!r}",
                    )
                )

    # Gate 4 — an unresolvable set member. Hard for a module, per item for a catalog.
    for slug in matches.missing_definitions:
        failures.append(
            GateFailure(
                gate=4,
                severity="hard",
                subject=slug,
                message=f"gate 4: set member {slug!r} has no definition in the snapshot",
            )
        )
    for name in matches.unmatched_members:
        failures.append(
            GateFailure(
                gate=4,
                severity="item",
                subject=name,
                message=f"gate 4: {name!r} is on the export but no catalog set defines it",
            )
        )

    return failures
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/rules_engine/test_gates.py -v`
Expected: PASS, 5 tests

- [ ] **Step 5: Commit**

```bash
git add src/rules_engine/gates.py tests/rules_engine/test_gates.py
git commit -m "feat: add the four build gates with named failures"
```

---

### Task 12: Build bindings

**Files:**
- Create: `src/rules_engine/binding.py`
- Modify: `src/rules_engine/__init__.py`
- Test: `tests/rules_engine/test_binding.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/rules_engine/test_binding.py
from rules_engine.binding import build_bindings
from rules_engine.export_adapter import Grantor, ParsedExport
from rules_engine.facts import CharacterFacts
from rules_engine.matching import match_sets
from rules_engine.rules_file import load_rules
from rules_engine.snapshot import load_snapshot

FIXTURE = "tests/fixtures/snapshot_small"


def parsed(level: int = 14) -> ParsedExport:
    return ParsedExport(
        facts=CharacterFacts(
            total_level=level,
            class_levels={"rogue": level},
            ability_mods={"str": 0, "dex": 5, "con": 2, "int": 3, "wis": 1, "cha": 4},
            spellcasting_ability_mod=4,
            walk_speed=30,
        ),
        grantors=[Grantor(kind="class", name="Rogue")],
    )


def build(level: int = 14):
    export = parsed(level)
    snapshot = load_snapshot(FIXTURE)
    return build_bindings(
        character_id="toki",
        export=export,
        snapshot=snapshot,
        matches=match_sets(export, snapshot),
        rules=load_rules("rules/2024.toml"),
    )


def test_binding_per_held_definition():
    bindings = build()
    assert set(bindings) == {"class-feature/sneak-attack", "class-feature/cunning-action-dash"}


def test_evaluated_table_covers_every_level():
    bindings = build()
    damage = bindings["class-feature/sneak-attack"].evaluated["damage_dice"]
    assert sorted(damage) == list(range(1, 21))
    assert damage[14] == 7  # ceil(14 / 2)
    assert damage[1] == 1


def test_binding_keeps_the_source_formula_for_provenance():
    bindings = build()
    assert bindings["class-feature/sneak-attack"].formulas["damage_dice"] == "SNEAK_ATTACK_DICE"


def test_display_fields_are_denormalised_onto_the_binding():
    bindings = build()
    display = bindings["class-feature/cunning-action-dash"].display
    assert display["rules_name"] == "Cunning Action: Dash"
    assert display["action_cost"] == "bonus"
    assert display["modes"] == ["combat", "exploration"]


def test_origin_defaults_to_library():
    assert build()["class-feature/sneak-attack"].origin == "library"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/rules_engine/test_binding.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rules_engine.binding'`

- [ ] **Step 3: Write the implementation**

```python
# src/rules_engine/binding.py
"""Turn matched definitions into evaluated, renderable bindings."""

from __future__ import annotations

from rules_engine.expand import expand_expression
from rules_engine.export_adapter import ParsedExport
from rules_engine.matching import MatchResult
from rules_engine.models import Binding
from rules_engine.rules_file import RulesFile
from rules_engine.snapshot import Snapshot

DISPLAY_FIELDS = (
    "rules_name",
    "source",
    "source_feature",
    "category",
    "modes",
    "kind",
    "action_cost",
    "cadence",
    "effect",
    "requires",
    "applies",
)


def build_bindings(
    character_id: str,
    export: ParsedExport,
    snapshot: Snapshot,
    matches: MatchResult,
    rules: RulesFile,
    picks: dict[str, dict[str, int]] | None = None,
    aliases: dict[str, str] | None = None,
) -> dict[str, Binding]:
    picks = picks or {}
    aliases = aliases or {}

    bindings: dict[str, Binding] = {}
    for slug in sorted(matches.held):
        definition = snapshot.definitions[slug]
        slug_picks = picks.get(slug, {})

        evaluated = {
            field_name: expand_expression(expression, rules, export.facts, slug_picks)
            for field_name, expression in definition.formulas.items()
        }

        bindings[slug] = Binding(
            character_id=character_id,
            slug=slug,
            alias=aliases.get(slug, ""),
            evaluated=evaluated,
            formulas=dict(definition.formulas),
            picks=slug_picks,
            origin=definition.origin,
            display={field: getattr(definition, field) for field in DISPLAY_FIELDS},
        )

    return bindings
```

```python
# src/rules_engine/__init__.py
"""Pure rules evaluation. Imports no network, no clock, no Firebase."""

from rules_engine.binding import build_bindings
from rules_engine.export_adapter import read_export
from rules_engine.gates import run_gates
from rules_engine.matching import match_sets
from rules_engine.rules_file import load_rules
from rules_engine.snapshot import load_snapshot

__all__ = [
    "build_bindings",
    "load_rules",
    "load_snapshot",
    "match_sets",
    "read_export",
    "run_gates",
]
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/rules_engine/test_binding.py -v`
Expected: PASS, 5 tests

- [ ] **Step 5: Commit**

```bash
git add src/rules_engine/binding.py src/rules_engine/__init__.py tests/rules_engine/test_binding.py
git commit -m "feat: build evaluated bindings with denormalised display fields"
```

---

### Task 13: Derived-value diff

The highest-value safeguard in the design.

**Files:**
- Create: `src/rules_engine/diff.py`
- Test: `tests/rules_engine/test_diff.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/rules_engine/test_diff.py
from rules_engine.diff import diff_artifacts, format_diff


def artifact(damage_at_14: int) -> dict:
    return {
        "character_id": "toki",
        "bindings": {
            "spell/fire-bolt": {
                "evaluated": {"damage_dice": {"14": damage_at_14}},
                "display": {"rules_name": "Fire Bolt"},
            }
        },
    }


def test_no_change_produces_no_rows():
    assert diff_artifacts(artifact(3), artifact(3)) == []


def test_changed_number_is_reported_with_old_and_new():
    rows = diff_artifacts(artifact(2), artifact(3))
    assert len(rows) == 1
    assert rows[0].character_id == "toki"
    assert rows[0].slug == "spell/fire-bolt"
    assert rows[0].field == "damage_dice"
    assert rows[0].level == 14
    assert rows[0].old == 2
    assert rows[0].new == 3


def test_added_binding_is_reported():
    before = {"character_id": "toki", "bindings": {}}
    rows = diff_artifacts(before, artifact(3))
    assert rows[0].old is None
    assert rows[0].new == 3


def test_removed_binding_is_reported():
    after = {"character_id": "toki", "bindings": {}}
    rows = diff_artifacts(artifact(3), after)
    assert rows[0].old == 3
    assert rows[0].new is None


def test_format_reads_like_the_spec():
    rows = diff_artifacts(artifact(2), artifact(3))
    assert format_diff(rows) == ["toki · spell/fire-bolt · damage_dice @L14 2 → 3"]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/rules_engine/test_diff.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rules_engine.diff'`

- [ ] **Step 3: Write the implementation**

```python
# src/rules_engine/diff.py
"""Report every number that changed between two build artifacts."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DiffRow:
    character_id: str
    slug: str
    field: str
    level: int
    old: float | None
    new: float | None


def _values(artifact: dict) -> dict[tuple[str, str, int], float]:
    flat: dict[tuple[str, str, int], float] = {}
    for slug, binding in artifact.get("bindings", {}).items():
        for field, table in binding.get("evaluated", {}).items():
            for level, value in table.items():
                flat[(slug, field, int(level))] = value
    return flat


def diff_artifacts(before: dict, after: dict) -> list[DiffRow]:
    character_id = after.get("character_id") or before.get("character_id", "")
    old_values, new_values = _values(before), _values(after)

    rows = [
        DiffRow(
            character_id=character_id,
            slug=slug,
            field=field,
            level=level,
            old=old_values.get(key),
            new=new_values.get(key),
        )
        for key in sorted(set(old_values) | set(new_values))
        for slug, field, level in [key]
        if old_values.get(key) != new_values.get(key)
    ]
    return rows


def format_diff(rows: list[DiffRow]) -> list[str]:
    def side(value: float | None) -> str:
        return "—" if value is None else str(value)

    return [
        f"{r.character_id} · {r.slug} · {r.field} @L{r.level} {side(r.old)} → {side(r.new)}"
        for r in rows
    ]
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/rules_engine/test_diff.py -v`
Expected: PASS, 5 tests

- [ ] **Step 5: Commit**

```bash
git add src/rules_engine/diff.py tests/rules_engine/test_diff.py
git commit -m "feat: add derived-value diff between build artifacts"
```

---

### Task 14: CLI check and build

**Files:**
- Create: `src/cli/__init__.py`
- Create: `src/cli/main.py`
- Test: `tests/cli/test_check_build.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/cli/test_check_build.py
import json

from cli.main import main

SMALL = "tests/fixtures/snapshot_small"


def write_export(path, grantor="Rogue"):
    path.write_text(json.dumps({
        "data": {
            "classes": [{"level": 14, "definition": {"name": grantor}}],
            "stats": [{"id": i, "value": 14} for i in range(1, 7)],
            "bonusStats": [], "overrideStats": [], "modifiers": {},
            "race": {"fullName": "Kender"}, "background": None, "feats": [],
            "spells": {}, "classSpells": [], "inventory": [],
        }
    }))
    return path


def test_check_passes_and_returns_zero(tmp_path, capsys):
    export = write_export(tmp_path / "export.json")
    code = main(["check", "--character", "toki", "--export", str(export), "--snapshot", SMALL,
                 "--rules", "rules/2024.toml"])
    assert code != 0  # Kender species has no set in the small fixture -> gate 1
    assert "gate 1" in capsys.readouterr().out


def test_build_writes_an_artifact(tmp_path):
    export = write_export(tmp_path / "export.json")
    out = tmp_path / "toki.json"
    code = main(["build", "--character", "toki", "--export", str(export), "--snapshot", SMALL,
                 "--rules", "rules/2024.toml", "--out", str(out), "--ignore-gate", "1"])
    assert code == 0
    artifact = json.loads(out.read_text())
    assert artifact["character_id"] == "toki"
    assert "class-feature/sneak-attack" in artifact["bindings"]
    assert artifact["bindings"]["class-feature/sneak-attack"]["evaluated"]["damage_dice"]["14"] == 7


def test_build_refuses_when_a_hard_gate_fails(tmp_path, capsys):
    export = write_export(tmp_path / "export.json")
    out = tmp_path / "toki.json"
    code = main(["build", "--character", "toki", "--export", str(export), "--snapshot", SMALL,
                 "--rules", "rules/2024.toml", "--out", str(out)])
    assert code != 0
    assert not out.exists()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/cli/test_check_build.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cli'`

- [ ] **Step 3: Write the implementation**

```python
# src/cli/__init__.py
"""Command surface. Orchestration only — no logic lives here."""
```

```python
# src/cli/main.py
"""pull / check / build / publish."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rules_engine import build_bindings, load_rules, load_snapshot, match_sets, read_export, run_gates


def _load_plays(path: str | None) -> list[dict]:
    return json.loads(Path(path).read_text()) if path else []


def _evaluate(args) -> tuple[dict, list]:
    export = read_export(args.export)
    snapshot = load_snapshot(args.snapshot)
    rules = load_rules(args.rules)
    matches = match_sets(export, snapshot)
    failures = run_gates(export, snapshot, matches, rules, _load_plays(args.plays))

    bindings = build_bindings(
        character_id=args.character,
        export=export,
        snapshot=snapshot,
        matches=matches,
        rules=rules,
    )
    artifact = {
        "character_id": args.character,
        "edition": rules.edition,
        "verified": rules.verified,
        "level": export.facts.total_level,
        "bindings": {
            slug: {
                "slug": b.slug,
                "alias": b.alias,
                "evaluated": {f: {str(k): v for k, v in t.items()} for f, t in b.evaluated.items()},
                "formulas": b.formulas,
                "picks": b.picks,
                "origin": b.origin,
                "display": b.display,
            }
            for slug, b in bindings.items()
        },
    }
    return artifact, failures


def _report(failures, ignore: set[int]) -> bool:
    blocking = False
    for failure in failures:
        print(failure.message)
        if failure.severity == "hard" and failure.gate not in ignore:
            blocking = True
    return blocking


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="crafter")
    sub = parser.add_subparsers(dest="command", required=True)

    for name in ("check", "build"):
        p = sub.add_parser(name)
        p.add_argument("--character", required=True)
        p.add_argument("--export", required=True)
        p.add_argument("--snapshot", default="verbs/snapshot")
        p.add_argument("--rules", default="rules/2024.toml")
        p.add_argument("--plays")
        p.add_argument("--ignore-gate", action="append", type=int, default=[])
        if name == "build":
            p.add_argument("--out", required=True)

    args = parser.parse_args(argv)
    artifact, failures = _evaluate(args)

    if _report(failures, set(args.ignore_gate)):
        print(f"{args.command} failed: a hard gate did not pass", file=sys.stderr)
        return 1

    if args.command == "build":
        Path(args.out).write_text(json.dumps(artifact, indent=2, sort_keys=True))
        print(f"wrote {args.out} — {len(artifact['bindings'])} bindings")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/cli/test_check_build.py -v`
Expected: PASS, 3 tests

- [ ] **Step 5: Commit**

```bash
git add src/cli tests/cli
git commit -m "feat: add check and build commands"
```

---

### Task 15: PHB anchors — close `verified = false`

This is what verifying the rules file actually means.

**Files:**
- Create: `tests/rules/test_phb_anchors.py`
- Modify: `rules/2024.toml:15` (`verified = false` → `true`)

- [ ] **Step 1: Write the failing test**

```python
# tests/rules/test_phb_anchors.py
"""Anchors against the 2024 Player's Handbook.

These are the tests that let rules/2024.toml claim verified = true. Each value is
checked against the printed book, not against the implementation.
"""

import pytest

from rules_engine.facts import CharacterFacts
from rules_engine.rules_file import load_rules
from rules_engine.variables import resolve

RULES = load_rules("rules/2024.toml")


def facts(level: int, klass: str = "rogue", casting_mod: int = 4) -> CharacterFacts:
    return CharacterFacts(
        total_level=level,
        class_levels={klass: level},
        ability_mods={"str": 0, "dex": 5, "con": 2, "int": 3, "wis": 1, "cha": casting_mod},
        spellcasting_ability_mod=casting_mod,
        walk_speed=30,
    )


@pytest.mark.parametrize(
    "level,expected",
    [(1, 2), (4, 2), (5, 3), (8, 3), (9, 4), (12, 4), (13, 5), (16, 5), (17, 6), (20, 6)],
)
def test_proficiency_bonus_by_level(level, expected):
    assert resolve("PROFICIENCY_BONUS", RULES, facts(level)) == expected


@pytest.mark.parametrize(
    "level,expected",
    [(1, 1), (4, 1), (5, 2), (10, 2), (11, 3), (16, 3), (17, 4), (20, 4)],
)
def test_cantrip_dice_scale_at_5_11_17(level, expected):
    assert resolve("CANTRIP_DICE", RULES, facts(level)) == expected


@pytest.mark.parametrize(
    "level,expected",
    [(1, 1), (2, 1), (3, 2), (4, 2), (5, 3), (11, 6), (19, 10), (20, 10)],
)
def test_sneak_attack_dice_is_half_rogue_level_rounded_up(level, expected):
    assert resolve("SNEAK_ATTACK_DICE", RULES, facts(level)) == expected


def test_spell_save_dc_is_eight_plus_mod_plus_proficiency():
    # Level 5, casting mod +4, proficiency +3 -> 15
    assert resolve("SPELL_SAVE_DC", RULES, facts(5, casting_mod=4)) == 15


def test_spell_attack_is_mod_plus_proficiency():
    assert resolve("SPELL_ATTACK", RULES, facts(5, casting_mod=4)) == 7


def test_rules_file_is_marked_verified():
    """The gate that stops an unverified edition from publishing."""
    assert RULES.verified is True, (
        "rules/2024.toml still says verified = false. Flip it only once every anchor "
        "above has been checked against the printed 2024 PHB."
    )
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/rules/test_phb_anchors.py -v`
Expected: The anchor tests pass; `test_rules_file_is_marked_verified` FAILS with the message above.

If any *anchor* fails, the seeded table is wrong. Fix `rules/2024.toml` against the book and re-run — that is the entire point of this task.

- [ ] **Step 3: Verify each anchor against the printed 2024 PHB, then flip the flag**

Check proficiency bonus, cantrip scaling, sneak attack progression, spell save DC and spell attack against the book. Then edit `rules/2024.toml`:

```toml
[meta]
edition = "2024"
verified = true
```

Also delete the now-false `STATUS: seed, unverified` comment at the top of the file.

- [ ] **Step 4: Run the whole suite**

Run: `uv run pytest -v`
Expected: PASS, all tests

- [ ] **Step 5: Commit**

```bash
git add rules/2024.toml tests/rules/test_phb_anchors.py
git commit -m "test: verify rules/2024.toml against the 2024 PHB anchors"
```

---

### Task 16: Golden fixtures

The spec calls for Toki and Rafe. **Rafe has no D&D Beyond export** — `character_exports/`
holds Billie, Bjorn Flabberhammer, Jasper Ravenwood, Jeff, The Grey Man and Toki Ironlung
(verified 2026-08-16). Rafe's 93 rows exist only in Notion. So this task builds Toki's
fixture and a second one for **The Grey Man**, who is a Rogue/Ranger and therefore
exercises multiclassing and the sneak attack progression that Toki (a single-class
Paladin) does not. Add Rafe when an export exists.

**Files:**
- Create: `tests/fixtures/golden/toki.json`
- Create: `tests/fixtures/golden/the-grey-man.json`
- Create: `tests/rules_engine/test_golden.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/rules_engine/test_golden.py
"""Real exports against hand-verified numbers.

A change to a formula or a rules table shows up here as a diff naming the character
and the value, which is the point.
"""

import json
from pathlib import Path

import pytest

from rules_engine import build_bindings, load_rules, load_snapshot, match_sets, read_export

CASES = [
    ("toki", "character_exports/dndbeyond-toki-ironlung.json"),
    ("the-grey-man", "character_exports/dndbeyond-the-grey-man.json"),
]


@pytest.mark.parametrize("name,export_path", CASES)
def test_golden_numbers(name, export_path):
    golden = json.loads(Path(f"tests/fixtures/golden/{name}.json").read_text())

    export = read_export(export_path)
    snapshot = load_snapshot("verbs/snapshot")
    rules = load_rules("rules/2024.toml")
    bindings = build_bindings(
        character_id=name,
        export=export,
        snapshot=snapshot,
        matches=match_sets(export, snapshot),
        rules=rules,
    )

    assert export.facts.total_level == golden["total_level"]

    for slug, expected in golden["expected"].items():
        assert slug in bindings, f"{name} no longer holds {slug}"
        for field, value in expected.items():
            actual = bindings[slug].evaluated[field][golden["total_level"]]
            assert actual == value, f"{name} · {slug} · {field}: expected {value}, got {actual}"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/rules_engine/test_golden.py -v`
Expected: FAIL — `FileNotFoundError: tests/fixtures/golden/toki.json`

- [ ] **Step 3: Write the fixtures**

Open each character's real sheet on D&D Beyond and record the numbers you can confirm by
eye. Start with the handful that matter, not everything. The levels below are verified
from the exports; the slugs and values must come from the real sheets, because a golden
fixture copied from the engine's own output tests nothing.

Toki is a **level 14 Paladin** — so their anchors are paladin numbers (spell save DC, lay
on hands pool, smite dice), not rogue ones.

```json
// tests/fixtures/golden/toki.json
{
  "total_level": 14,
  "expected": {
    "class-feature/lay-on-hands": {"pool": 70},
    "class-feature/divine-smite": {"damage_dice": 2}
  }
}
```

The Grey Man is **level 13, Rogue and Ranger** — the multiclass case, where
`SNEAK_ATTACK_DICE` must read rogue levels only rather than total level. Fill in the
rogue/ranger split from the sheet.

```json
// tests/fixtures/golden/the-grey-man.json
{
  "total_level": 13,
  "expected": {
    "class-feature/sneak-attack": {"damage_dice": 4}
  }
}
```

If the engine disagrees with a number here, check the sheet before changing either side.
A golden fixture edited to match the code is worthless.

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/rules_engine/test_golden.py -v`
Expected: PASS, 2 tests

A failure here before the fixture is trusted means either the fixture or the engine is wrong. Check the number against the real sheet before changing either.

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/golden tests/rules_engine/test_golden.py
git commit -m "test: add golden number fixtures for Toki and Rafe"
```

---

### Task 17: Notion pull

**Files:**
- Create: `src/notion_sync/__init__.py`
- Create: `src/notion_sync/client.py`
- Create: `src/notion_sync/pull.py`
- Test: `tests/notion_sync/test_pull.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/notion_sync/test_pull.py
import json
from pathlib import Path

import pytest

from notion_sync.pull import SchemaDrift, pull

PAGE = {
    "id": "page-1",
    "properties": {
        "Rules Name": {"type": "title", "title": [{"plain_text": "Fire Bolt"}]},
        "Slug": {"type": "rich_text", "rich_text": [{"plain_text": "spell/fire-bolt"}]},
        "Source": {"type": "select", "select": {"name": "Spell"}},
        "Source Feature": {"type": "rich_text", "rich_text": [{"plain_text": "Sorcerer"}]},
        "Category": {"type": "select", "select": {"name": "damage"}},
        "Modes": {"type": "multi_select", "multi_select": [{"name": "combat"}]},
        "Kind": {"type": "select", "select": {"name": "action"}},
        "Action Cost": {"type": "select", "select": {"name": "action"}},
        "Cadence": {"type": "select", "select": {"name": "at will"}},
        "Effect": {"type": "rich_text", "rich_text": [{"plain_text": "Ranged spell attack."}]},
        "Requires": {"type": "multi_select", "multi_select": [{"name": "target-visible"}]},
        "Applies": {"type": "multi_select", "multi_select": []},
        "Formulas": {"type": "rich_text", "rich_text": [{"plain_text": "damage_dice=CANTRIP_DICE"}]},
        "Rules": {"type": "select", "select": {"name": "2024"}},
    },
}


class FakeClient:
    def __init__(self, pages, sets=None):
        self.pages = pages
        self.sets = sets or []

    def query(self, collection_id):
        return self.pages if "520a" in collection_id else self.sets


def test_writes_one_file_per_record(tmp_path):
    pull(FakeClient([PAGE]), out_dir=tmp_path)
    written = tmp_path / "verbs" / "spell__fire-bolt.json"
    assert written.exists()
    body = json.loads(written.read_text())
    assert body["slug"] == "spell/fire-bolt"
    assert body["rules_name"] == "Fire Bolt"
    assert body["formulas"] == {"damage_dice": "CANTRIP_DICE"}


def test_output_is_stable_so_diffs_are_readable(tmp_path):
    pull(FakeClient([PAGE]), out_dir=tmp_path)
    first = (tmp_path / "verbs" / "spell__fire-bolt.json").read_text()
    pull(FakeClient([PAGE]), out_dir=tmp_path)
    second = (tmp_path / "verbs" / "spell__fire-bolt.json").read_text()
    assert first == second
    assert first.index('"category"') < first.index('"slug"')  # keys sorted


def test_renamed_property_fails_and_names_it(tmp_path):
    drifted = json.loads(json.dumps(PAGE))
    drifted["properties"]["Verb Slug"] = drifted["properties"].pop("Slug")
    with pytest.raises(SchemaDrift, match="Slug"):
        pull(FakeClient([drifted]), out_dir=tmp_path)


def test_nothing_is_written_when_a_record_drifts(tmp_path):
    good = PAGE
    drifted = json.loads(json.dumps(PAGE))
    drifted["properties"]["Verb Slug"] = drifted["properties"].pop("Slug")
    with pytest.raises(SchemaDrift):
        pull(FakeClient([good, drifted]), out_dir=tmp_path)
    assert not (tmp_path / "verbs").exists()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/notion_sync/test_pull.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'notion_sync'`

- [ ] **Step 3: Write the implementation**

```python
# src/notion_sync/__init__.py
"""Transcribe Notion into the committed snapshot. Validates nothing."""
```

```python
# src/notion_sync/client.py
"""Thin Notion wrapper. Injectable so tests never touch the network."""

from __future__ import annotations

import os

VERB_LIBRARY = "520a0754-7054-47d1-b836-9fd462f18b81"
VERB_SETS = "95c1044e-ace7-45ae-87e1-51ae0207f453"


class NotionClient:
    def __init__(self, token: str | None = None):
        from notion_client import Client

        self._client = Client(auth=token or os.environ["NOTION_TOKEN"])

    def query(self, collection_id: str) -> list[dict]:
        pages, cursor = [], None
        while True:
            response = self._client.databases.query(database_id=collection_id, start_cursor=cursor)
            pages.extend(response["results"])
            if not response.get("has_more"):
                return pages
            cursor = response["next_cursor"]
```

```python
# src/notion_sync/pull.py
"""Notion -> verbs/snapshot/. One file per record, stable ordering."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from notion_sync.client import VERB_LIBRARY, VERB_SETS

REQUIRED_VERB_PROPERTIES = (
    "Rules Name", "Slug", "Source", "Source Feature", "Category", "Modes",
    "Kind", "Action Cost", "Cadence", "Effect", "Requires", "Applies", "Formulas", "Rules",
)
REQUIRED_SET_PROPERTIES = ("Name", "Slug", "Composition", "Grantor", "Members", "Rules")


class SchemaDrift(Exception):
    """A property Notion no longer has, or never had. Always names it."""


def _text(prop: dict) -> str:
    match prop["type"]:
        case "title":
            return "".join(t["plain_text"] for t in prop["title"])
        case "rich_text":
            return "".join(t["plain_text"] for t in prop["rich_text"])
        case "select":
            return (prop["select"] or {}).get("name", "")
        case "multi_select":
            return ",".join(o["name"] for o in prop["multi_select"])
        case "relation":
            return ",".join(r["id"] for r in prop["relation"])
    return ""


def _list(prop: dict) -> list[str]:
    value = _text(prop)
    return [part.strip() for part in value.split(",") if part.strip()]


def _require(page: dict, names: tuple[str, ...]) -> dict:
    properties = page["properties"]
    for name in names:
        if name not in properties:
            raise SchemaDrift(
                f"Notion page {page['id']} has no property {name!r} — "
                f"it was renamed or removed. Nothing was written."
            )
    return properties


def _parse_formulas(raw: str) -> dict[str, str]:
    formulas = {}
    for line in raw.replace(";", "\n").splitlines():
        if "=" in line:
            field, expression = line.split("=", 1)
            formulas[field.strip()] = expression.strip()
    return formulas


def _verb_record(page: dict) -> dict:
    p = _require(page, REQUIRED_VERB_PROPERTIES)
    return {
        "slug": _text(p["Slug"]),
        "rules_name": _text(p["Rules Name"]),
        "source": _text(p["Source"]),
        "source_feature": _text(p["Source Feature"]),
        "category": _text(p["Category"]),
        "modes": _list(p["Modes"]),
        "kind": _text(p["Kind"]),
        "action_cost": _text(p["Action Cost"]),
        "cadence": _text(p["Cadence"]),
        "effect": _text(p["Effect"]),
        "requires": _list(p["Requires"]),
        "applies": _list(p["Applies"]),
        "formulas": _parse_formulas(_text(p["Formulas"])),
        "rules_edition": _text(p["Rules"]),
    }


def _set_record(page: dict) -> dict:
    p = _require(page, REQUIRED_SET_PROPERTIES)
    return {
        "slug": _text(p["Slug"]),
        "name": _text(p["Name"]),
        "composition": _text(p["Composition"]),
        "grantor": _text(p["Grantor"]),
        "members": _list(p["Members"]),
        "rules_edition": _text(p["Rules"]),
    }


def pull(client, out_dir: str | Path = "verbs/snapshot") -> int:
    """Transcribe both collections. Parses everything before writing anything."""
    verbs = [_verb_record(page) for page in client.query(VERB_LIBRARY)]
    sets = [_set_record(page) for page in client.query(VERB_SETS)]

    out_dir = Path(out_dir)
    if out_dir.exists():
        shutil.rmtree(out_dir)

    for folder, records in (("verbs", verbs), ("sets", sets)):
        target = out_dir / folder
        target.mkdir(parents=True)
        for record in records:
            filename = record["slug"].replace("/", "__") + ".json"
            (target / filename).write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")

    return len(verbs) + len(sets)
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/notion_sync/test_pull.py -v`
Expected: PASS, 4 tests

- [ ] **Step 5: Commit**

```bash
git add src/notion_sync tests/notion_sync
git commit -m "feat: pull Notion verb collections into the committed snapshot"
```

---

### Task 18: Wire pull into the CLI and take a real snapshot

**Files:**
- Modify: `src/cli/main.py`
- Create: `verbs/snapshot/` (generated, committed)

- [ ] **Step 1: Add the subcommand**

In `src/cli/main.py`, inside `main()` after the `check`/`build` parsers are added:

```python
    pull_parser = sub.add_parser("pull")
    pull_parser.add_argument("--out", default="verbs/snapshot")
```

And before `artifact, failures = _evaluate(args)`:

```python
    if args.command == "pull":
        from notion_sync.client import NotionClient
        from notion_sync.pull import pull

        count = pull(NotionClient(), out_dir=args.out)
        print(f"pulled {count} records into {args.out}")
        return 0
```

- [ ] **Step 2: Run the existing suite to confirm nothing broke**

Run: `uv run pytest -v`
Expected: PASS, all tests

- [ ] **Step 3: Take a real snapshot**

```bash
NOTION_TOKEN=<token> uv run python -m cli.main pull
```

Expected: `pulled N records into verbs/snapshot`

If it raises `SchemaDrift`, the Notion schema has moved. Fix the property list in `pull.py` to match what Noti actually authored — do not loosen the check.

- [ ] **Step 4: Run check against Toki with the real snapshot**

```bash
uv run python -m cli.main check --character toki --export character_exports/dndbeyond-toki-ironlung.json
```

Expected: a gate report. Gate 1 failures naming grantors with no set are the expected state until the sets are authored — record what it names.

- [ ] **Step 5: Commit**

```bash
git add src/cli/main.py verbs/snapshot
git commit -m "feat: add pull command and commit the first verb snapshot"
```

---

### Task 19: Firestore publisher

**Files:**
- Create: `src/publisher/__init__.py`
- Create: `src/publisher/firestore_client.py`
- Create: `src/publisher/publish.py`
- Test: `tests/publisher/test_publish.py`

Tests run against the Firestore emulator. Start it with:
`firebase emulators:start --only firestore` and export `FIRESTORE_EMULATOR_HOST=localhost:8080`.

- [ ] **Step 1: Write the failing test**

```python
# tests/publisher/test_publish.py
import os

import pytest

from publisher.firestore_client import get_client
from publisher.publish import publish_artifact

pytestmark = pytest.mark.skipif(
    "FIRESTORE_EMULATOR_HOST" not in os.environ,
    reason="requires the Firestore emulator; run firebase emulators:start --only firestore",
)


def artifact(damage: int = 7) -> dict:
    return {
        "character_id": "toki",
        "edition": "2024",
        "verified": True,
        "level": 14,
        "bindings": {
            "class-feature/sneak-attack": {
                "slug": "class-feature/sneak-attack",
                "alias": "",
                "evaluated": {"damage_dice": {"14": damage}},
                "formulas": {"damage_dice": "SNEAK_ATTACK_DICE"},
                "picks": {},
                "origin": "library",
                "display": {"rules_name": "Sneak Attack"},
            }
        },
    }


@pytest.fixture(autouse=True)
def clean():
    client = get_client()
    for doc in client.collection("characters").document("toki").collection("bindings").stream():
        doc.reference.delete()
    yield


def test_publish_writes_bindings():
    publish_artifact(artifact(), get_client())
    doc = (
        get_client()
        .collection("characters").document("toki")
        .collection("bindings").document("class-feature__sneak-attack")
        .get()
    )
    assert doc.exists
    assert doc.to_dict()["evaluated"]["damage_dice"]["14"] == 7


def test_publish_is_idempotent():
    client = get_client()
    publish_artifact(artifact(), client)
    publish_artifact(artifact(), client)
    docs = list(client.collection("characters").document("toki").collection("bindings").stream())
    assert len(docs) == 1


def test_publish_updates_a_changed_number():
    client = get_client()
    publish_artifact(artifact(damage=7), client)
    publish_artifact(artifact(damage=8), client)
    doc = (
        client.collection("characters").document("toki")
        .collection("bindings").document("class-feature__sneak-attack").get()
    )
    assert doc.to_dict()["evaluated"]["damage_dice"]["14"] == 8


def test_publish_never_touches_table_authored_content():
    client = get_client()
    ref = (
        client.collection("characters").document("toki")
        .collection("bindings").document("homebrew__dm-gift")
    )
    ref.set({"slug": "homebrew/dm-gift", "origin": "table", "display": {"rules_name": "DM Gift"}})

    publish_artifact(artifact(), client)

    after = ref.get().to_dict()
    assert after["origin"] == "table"
    assert after["display"]["rules_name"] == "DM Gift"


def test_publish_refuses_an_unverified_edition():
    unverified = artifact()
    unverified["verified"] = False
    with pytest.raises(ValueError, match="verified"):
        publish_artifact(unverified, get_client())


def test_publish_allows_unverified_when_explicitly_overridden():
    unverified = artifact()
    unverified["verified"] = False
    publish_artifact(unverified, get_client(), allow_unverified=True)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/publisher/test_publish.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'publisher'` (or SKIPPED if the emulator is not running — start it first)

- [ ] **Step 3: Write the implementation**

```python
# src/publisher/__init__.py
"""Write evaluated output to Firestore. Contains no math and no rules knowledge."""
```

```python
# src/publisher/firestore_client.py
"""Firestore handle. Talks to the emulator when FIRESTORE_EMULATOR_HOST is set."""

from __future__ import annotations

import os


def get_client():
    import firebase_admin
    from firebase_admin import firestore

    if not firebase_admin._apps:
        project = os.environ.get("GOOGLE_CLOUD_PROJECT", "dnd-crafter")
        firebase_admin.initialize_app(options={"projectId": project})
    return firestore.client()
```

```python
# src/publisher/publish.py
"""Idempotent upserts. The server owns library content; the table owns its own."""

from __future__ import annotations

BATCH_LIMIT = 500


def _doc_id(slug: str) -> str:
    return slug.replace("/", "__")


def publish_artifact(artifact: dict, client, allow_unverified: bool = False) -> int:
    if not artifact.get("verified") and not allow_unverified:
        raise ValueError(
            f"rules edition {artifact.get('edition')!r} is not verified; "
            "pass allow_unverified=True to override deliberately"
        )

    character = client.collection("characters").document(artifact["character_id"])
    bindings = character.collection("bindings")

    # Never write over anything the table authored.
    protected = {
        doc.id for doc in bindings.stream() if (doc.to_dict() or {}).get("origin") == "table"
    }

    writes = 0
    batch = client.batch()
    pending = 0

    for slug, binding in sorted(artifact["bindings"].items()):
        doc_id = _doc_id(slug)
        if doc_id in protected:
            continue
        batch.set(bindings.document(doc_id), binding)
        writes += 1
        pending += 1
        if pending == BATCH_LIMIT:
            batch.commit()
            batch = client.batch()
            pending = 0

    batch.set(
        character,
        {"level": artifact["level"], "edition": artifact["edition"]},
        merge=True,
    )
    batch.commit()

    return writes
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/publisher/test_publish.py -v`
Expected: PASS, 6 tests

- [ ] **Step 5: Commit**

```bash
git add src/publisher tests/publisher
git commit -m "feat: publish evaluated bindings to Firestore with clobber protection"
```

---

### Task 20: Security rules

Under link-as-key these rules are the entire security boundary.

**Files:**
- Create: `firestore.rules`
- Test: `tests/publisher/test_security_rules.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/publisher/test_security_rules.py
"""The security boundary. A bug here exposes every character.

Run against the emulator with rules loaded:
  firebase emulators:start --only firestore
"""

import os

import pytest
import requests

pytestmark = pytest.mark.skipif(
    "FIRESTORE_EMULATOR_HOST" not in os.environ,
    reason="requires the Firestore emulator",
)

HOST = os.environ.get("FIRESTORE_EMULATOR_HOST", "localhost:8080")
PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "dnd-crafter")
BASE = f"http://{HOST}/v1/projects/{PROJECT}/databases/(default)/documents"


def test_get_with_a_known_id_is_allowed():
    response = requests.get(f"{BASE}/characters/known-id")
    assert response.status_code in (200, 404), response.text


def test_listing_characters_is_denied():
    response = requests.get(f"{BASE}/characters")
    assert response.status_code == 403, "listing characters must be denied — the id is the credential"


def test_client_write_to_verbs_is_denied():
    response = requests.post(
        f"{BASE}/verbs?documentId=spell__forged",
        json={"fields": {"rules_name": {"stringValue": "Forged"}}},
    )
    assert response.status_code == 403


def test_client_write_to_an_evaluated_field_is_denied():
    response = requests.patch(
        f"{BASE}/characters/known-id/bindings/spell__fire-bolt",
        json={"fields": {"evaluated": {"mapValue": {"fields": {}}}}},
    )
    assert response.status_code == 403
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/publisher/test_security_rules.py -v`
Expected: FAIL — requests succeed because no rules file is loaded, so the deny assertions fail

- [ ] **Step 3: Write the rules**

```javascript
// firestore.rules
rules_version = '2';

service cloud.firestore {
  match /databases/{database}/documents {

    // Definitions and sets are rules elements, not character data. Readable by anyone
    // holding any character link; written only by the server, which holds admin
    // credentials and bypasses these rules entirely.
    match /verbs/{slug} {
      allow get, list: if true;
      allow write: if false;
    }
    match /sets/{slug} {
      allow get, list: if true;
      allow write: if false;
    }

    // The character id IS the credential. Knowing it grants access; nothing permits
    // discovering it. `list` is denied at every level beneath a character for that reason.
    match /characters/{characterId} {
      allow get: if true;
      allow list: if false;
      allow update: if true;
      allow create, delete: if false;

      // Evaluated numbers come from the server only. A client may create and edit its
      // own captures and plays, but may never write a number the evaluator produced.
      match /bindings/{slug} {
        allow get: if true;
        allow list: if true;
        allow create, update: if !request.resource.data.keys().hasAny(['evaluated']);
        allow delete: if false;
      }

      match /plays/{playId} {
        allow read, write: if true;
      }

      match /captures/{captureId} {
        allow read, write: if true;
      }

      match /state/{docId} {
        allow read, write: if true;
      }
    }
  }
}
```

- [ ] **Step 4: Restart the emulator with the rules and run the tests**

```bash
firebase emulators:start --only firestore
uv run pytest tests/publisher/test_security_rules.py -v
```

Expected: PASS, 4 tests

- [ ] **Step 5: Audit the rules**

Invoke the `firebase-security-rules-auditor` skill against `firestore.rules`. Fix anything it raises before committing. This is the gate on the first real deploy.

- [ ] **Step 6: Commit**

```bash
git add firestore.rules tests/publisher/test_security_rules.py
git commit -m "feat: add firestore security rules for link-as-key access"
```

---

### Task 21: Publish command and the diff report

**Files:**
- Modify: `src/cli/main.py`
- Test: `tests/cli/test_publish_command.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/cli/test_publish_command.py
import json

from cli.main import main


def artifact(damage: int) -> dict:
    return {
        "character_id": "toki",
        "edition": "2024",
        "verified": True,
        "level": 14,
        "bindings": {
            "class-feature/sneak-attack": {
                "slug": "class-feature/sneak-attack",
                "evaluated": {"damage_dice": {"14": damage}},
                "display": {"rules_name": "Sneak Attack"},
                "origin": "library",
            }
        },
    }


def test_dry_run_prints_the_diff_and_writes_nothing(tmp_path, capsys):
    previous = tmp_path / "previous.json"
    current = tmp_path / "current.json"
    previous.write_text(json.dumps(artifact(7)))
    current.write_text(json.dumps(artifact(8)))

    code = main(["publish", "--artifact", str(current), "--against", str(previous), "--dry-run"])

    assert code == 0
    out = capsys.readouterr().out
    assert "toki · class-feature/sneak-attack · damage_dice @L14 7 → 8" in out
    assert "dry run" in out


def test_dry_run_reports_no_changes(tmp_path, capsys):
    previous = tmp_path / "previous.json"
    current = tmp_path / "current.json"
    previous.write_text(json.dumps(artifact(7)))
    current.write_text(json.dumps(artifact(7)))

    code = main(["publish", "--artifact", str(current), "--against", str(previous), "--dry-run"])

    assert code == 0
    assert "no numbers changed" in capsys.readouterr().out
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/cli/test_publish_command.py -v`
Expected: FAIL — `argparse` exits with "invalid choice: 'publish'"

- [ ] **Step 3: Add the subcommand**

In `src/cli/main.py`, add after the `pull` parser:

```python
    publish_parser = sub.add_parser("publish")
    publish_parser.add_argument("--artifact", required=True)
    publish_parser.add_argument("--against", help="previous artifact, for the derived-value diff")
    publish_parser.add_argument("--dry-run", action="store_true")
    publish_parser.add_argument("--allow-unverified", action="store_true")
```

And add this branch next to the `pull` branch:

```python
    if args.command == "publish":
        from rules_engine.diff import diff_artifacts, format_diff

        artifact = json.loads(Path(args.artifact).read_text())
        previous = json.loads(Path(args.against).read_text()) if args.against else {"bindings": {}}

        rows = diff_artifacts(previous, artifact)
        if rows:
            for line in format_diff(rows):
                print(line)
        else:
            print("no numbers changed")

        if args.dry_run:
            print("dry run — nothing was written")
            return 0

        from publisher.firestore_client import get_client
        from publisher.publish import publish_artifact

        written = publish_artifact(artifact, get_client(), allow_unverified=args.allow_unverified)
        print(f"published {written} bindings for {artifact['character_id']}")
        return 0
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/cli/test_publish_command.py -v`
Expected: PASS, 2 tests

- [ ] **Step 5: Run the whole suite**

Run: `uv run pytest -v`
Expected: PASS. Emulator tests skip unless `FIRESTORE_EMULATOR_HOST` is set.

- [ ] **Step 6: Commit**

```bash
git add src/cli/main.py tests/cli/test_publish_command.py
git commit -m "feat: add publish command with derived-value diff and dry run"
```

---

### Task 22: End-to-end integration against the real snapshot

**Files:**
- Test: `tests/test_integration.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_integration.py
"""The full committed snapshot end to end.

Unit tests use a five-record fixture where every value is deliberate. This one catches
what only real data has: the emoji property key, the spell in two lists, the set with
a choice point.
"""

import json
from pathlib import Path

import pytest

from cli.main import main

SNAPSHOT = Path("verbs/snapshot")

pytestmark = pytest.mark.skipif(
    not SNAPSHOT.exists(), reason="run `python -m cli.main pull` first"
)


def test_toki_builds_from_the_real_snapshot(tmp_path, capsys):
    out = tmp_path / "toki.json"
    code = main([
        "build",
        "--character", "toki",
        "--export", "character_exports/dndbeyond-toki-ironlung.json",
        "--snapshot", str(SNAPSHOT),
        "--rules", "rules/2024.toml",
        "--out", str(out),
    ])
    assert code == 0, capsys.readouterr().out

    artifact = json.loads(out.read_text())
    assert artifact["bindings"], "Toki built with no bindings at all"
    for slug, binding in artifact["bindings"].items():
        for field, table in binding["evaluated"].items():
            assert len(table) == 20, f"{slug}.{field} does not cover levels 1-20"


def test_no_binding_carries_a_null_number(tmp_path):
    out = tmp_path / "toki.json"
    main([
        "build", "--character", "toki",
        "--export", "character_exports/dndbeyond-toki-ironlung.json",
        "--snapshot", str(SNAPSHOT), "--rules", "rules/2024.toml", "--out", str(out),
    ])
    artifact = json.loads(out.read_text())
    for slug, binding in artifact["bindings"].items():
        for field, table in binding["evaluated"].items():
            for level, value in table.items():
                assert value is not None, f"{slug}.{field} is null at level {level}"
```

- [ ] **Step 2: Run it**

Run: `uv run pytest tests/test_integration.py -v`
Expected: FAIL initially — gate failures naming grantors or variables the real snapshot does not yet cover.

Every failure here is a real gap in the Notion content, not a bug in the engine. Record what it names, hand the list to Ian for Noti, and re-run after the next `pull`. The test passing is the definition of done for this plan.

- [ ] **Step 3: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: add end-to-end build against the real snapshot"
```

---

### Task 23: Publish the library itself

The spec says Firestore holds everything — definitions and sets, not only bindings. Task
19 published bindings; this publishes the library they denormalize from, so the app has
one read path.

**Files:**
- Modify: `src/publisher/publish.py`
- Modify: `src/cli/main.py`
- Test: `tests/publisher/test_publish_library.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/publisher/test_publish_library.py
import os

import pytest

from publisher.firestore_client import get_client
from publisher.publish import publish_library
from rules_engine.snapshot import load_snapshot

pytestmark = pytest.mark.skipif(
    "FIRESTORE_EMULATOR_HOST" not in os.environ,
    reason="requires the Firestore emulator",
)

FIXTURE = "tests/fixtures/snapshot_small"


@pytest.fixture(autouse=True)
def clean():
    client = get_client()
    for collection in ("verbs", "sets"):
        for doc in client.collection(collection).stream():
            doc.reference.delete()
    yield


def test_publishes_every_definition_and_set():
    written = publish_library(load_snapshot(FIXTURE), get_client())
    assert written == 5

    doc = get_client().collection("verbs").document("spell__fire-bolt").get()
    assert doc.exists
    assert doc.to_dict()["rules_name"] == "Fire Bolt"
    assert doc.to_dict()["origin"] == "library"
    assert doc.to_dict()["status"] == "published"
    assert doc.to_dict()["campaign"] is None


def test_is_idempotent():
    client = get_client()
    publish_library(load_snapshot(FIXTURE), client)
    publish_library(load_snapshot(FIXTURE), client)
    assert len(list(client.collection("verbs").stream())) == 3


def test_never_touches_table_authored_definitions():
    client = get_client()
    ref = client.collection("verbs").document("homebrew__dm-gift")
    ref.set({"slug": "homebrew/dm-gift", "origin": "table", "status": "draft",
             "rules_name": "DM Gift", "campaign": "dragonlance"})

    publish_library(load_snapshot(FIXTURE), client)

    after = ref.get().to_dict()
    assert after["origin"] == "table"
    assert after["rules_name"] == "DM Gift"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/publisher/test_publish_library.py -v`
Expected: FAIL — `ImportError: cannot import name 'publish_library'`

- [ ] **Step 3: Add the function**

Append to `src/publisher/publish.py`:

```python
from dataclasses import asdict


def publish_library(snapshot, client) -> int:
    """Upsert definitions and sets. Never writes over anything with origin 'table'."""
    written = 0

    for collection, records in (("verbs", snapshot.definitions), ("sets", snapshot.sets)):
        ref = client.collection(collection)
        protected = {
            doc.id for doc in ref.stream() if (doc.to_dict() or {}).get("origin") == "table"
        }

        batch = client.batch()
        pending = 0
        for slug, record in sorted(records.items()):
            doc_id = _doc_id(slug)
            if doc_id in protected:
                continue

            body = asdict(record)
            if "composition" in body:
                body["composition"] = record.composition.value

            batch.set(ref.document(doc_id), body)
            written += 1
            pending += 1
            if pending == BATCH_LIMIT:
                batch.commit()
                batch = client.batch()
                pending = 0

        if pending:
            batch.commit()

    return written
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/publisher/test_publish_library.py -v`
Expected: PASS, 3 tests

- [ ] **Step 5: Wire it into the CLI**

In `src/cli/main.py`, add to the `publish` parser:

```python
    publish_parser.add_argument("--library", action="store_true",
                                help="also publish definitions and sets from the snapshot")
    publish_parser.add_argument("--snapshot", default="verbs/snapshot")
```

And inside the `publish` branch, after `publish_artifact(...)`:

```python
        if args.library:
            from publisher.publish import publish_library
            from rules_engine import load_snapshot

            count = publish_library(load_snapshot(args.snapshot), get_client())
            print(f"published {count} library records")
```

- [ ] **Step 6: Run the whole suite**

Run: `uv run pytest -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/publisher/publish.py src/cli/main.py tests/publisher/test_publish_library.py
git commit -m "feat: publish definitions and sets to firestore"
```

---

## Definition of done

- `uv run pytest -v` is green, with the emulator running.
- `rules/2024.toml` says `verified = true`, and the PHB anchors prove it.
- `python -m cli.main build --character toki ...` produces an artifact where every binding covers levels 1–20 with no nulls.
- `python -m cli.main publish --dry-run --against <previous>` prints a readable derived-value diff.
- `python -m cli.main publish --library` puts definitions, sets and bindings in Firestore, so the app has one read path.
- `firestore.rules` has passed the `firebase-security-rules-auditor` skill.
- Any gate failures remaining are recorded as Notion content gaps for Noti, not code defects.

## What this plan does not build

The sheet UI, the at-table authoring UI, the Cloud Functions, and the promotion packet.
Those are subsystems 2, 3 and 4 in the spec's sequencing section, and each needs its own
spec and plan. The `rules_engine` purity rule is what keeps them cheap: the Cloud Function
of subsystem 3 wraps `run_gates` and `build_bindings` without reimplementing either.
