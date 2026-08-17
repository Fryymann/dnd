# Library and Evaluator — Top-Level Progress Review

**Date:** 2026-08-16  
**Reviewer:** Hermes  
**For:** Clyde  
**Branch reviewed:** `feature/library-and-evaluator` at `8b86163`  
**Scope:** Architecture, plan adherence, milestone progress, and project-level risks. This was not a deep code review.

## Executive summary

Development is healthy and closely follows the approved design through Task 9. The package boundaries remain clean, the pure rules core has not acquired Notion or Firebase dependencies, the implementation sequence matches the plan, and the delivered subsystem has strong automated coverage.

The current code is ready to continue, but **Task 10 should not be implemented verbatim from the plan**. Its draft matching contract leaves three correctness questions unresolved:

1. class feature level gates are evaluated against total character level;
2. grantors are keyed only by normalized display name and map to only one set;
3. inventory matching does not distinguish owned, equipped, wielded, stowed, or attuned items.

All three can create silently incorrect capabilities, which is the central failure mode this design exists to prevent. Amend Task 10 before coding it.

## Evidence collected

- `uv run pytest` — **119 passed**.
- `uv run ruff check src/rules_engine tests/rules_engine` — **all checks passed**.
- Code-review graph — **261 nodes, 1,634 edges, 29 files**, current at `8b86163`.
- `code-review-graph detect-changes` — no changed functions, affected flows, or test gaps in the current working tree.
- Repository-wide `uv run ruff check .` — 15 existing `E501` failures in `projects/toki_sheet/distill.py`; none are in the new subsystem.
- Working tree before this report contained only untracked agent context files: `AGENTS.md` and `CLAUDE.md`.

## Current milestone

Tasks 1–9 of the 23-task plan are implemented:

1. project scaffold;
2. rules-file loading;
3. character facts;
4. safe formula evaluation;
5. variable resolution;
6. level 1–20 expansion;
7. domain models and small snapshot fixture;
8. committed snapshot loading;
9. D&D Beyond export adapter.

Task 10, set matching, is the next planned task. The absence of `notion_sync`, `publisher`, and `cli` is expected at this milestone and is not schedule drift.

## What is working well

### Architecture

The central architecture remains sound:

- `rules_engine` contains rules knowledge and correctness gates.
- D&D Beyond's shape is isolated in `export_adapter.py`.
- Notion transcription, Firestore publication, and CLI orchestration remain separate future units.
- Formulas are evaluated outside the browser; bindings carry evaluated level tables.
- The committed snapshot provides a reproducible input and reviewable authoring diff.
- The publisher is designed as an idempotent diff, not a destructive replacement.
- `origin: table` and `origin: library` establish an explicit content-ownership boundary.
- Golden character fixtures, PHB anchors, and a derived-value diff are planned before live publication.

The implementation currently respects the purity rule. The new `rules_engine` modules import only standard-library code and other `rules_engine` modules. No Notion, Firebase, network, or clock dependency has leaked into the core.

### Development discipline

The implementation order follows the task order, and each delivered module has corresponding tests. The commit history also shows a useful pattern: implement, review against real data, fix the discovered contract problem, and record the resulting doctrine in the plan.

The amendments made so far improve the design rather than merely documenting exceptions:

- unnecessary or dangerous formula operators were removed;
- expression inputs and outputs were bounded;
- missing facts now fail loudly rather than becoming plausible zeroes;
- container-path knowledge moved to `CharacterFacts`;
- ambiguous slug encodings are rejected before snapshot data can be overwritten;
- `SPELLCASTING_MOD` was narrowed to the casting class ability;
- no casting class is represented by `None`, not an ambiguous zero;
- feat- and item-selected casting abilities remain binding-level picks.

This is good adherence to the design's purpose even where it departs from the plan's original pasted implementation.

## Required alteration before Task 10

### 1. Define the progression source for every level gate

The draft Task 10 implementation compares a set member's gate with:

```text
export.facts.total_level >= gate
```

That is incorrect for class features. A Rogue 1 / Sorcerer 13 is character level 14 but must not receive Rogue features gated at Rogue level 2 or higher.

#### Suggested alteration

Make the gate's progression source explicit in the model. Suitable options include:

- a set-level field such as `level_source: "character" | "granting_class"`;
- a rules-variable reference such as `level_variable: "CHARACTER_LEVEL"` or a class-specific source;
- an explicit structured gate containing both threshold and source.

Prefer a declarative source over branching on slug prefixes or grantor names. Matching should resolve the declared progression and compare the threshold against that value.

Add Task 10 tests for at least:

- a single-class rogue receiving a feature at the correct rogue level;
- a Rogue 1 / Sorcerer 13 not receiving a Rogue 2 feature;
- a character-level feature using total level when that is the declared source;
- a missing or invalid progression source failing loudly by set and member name.

### 2. Treat grantor identity as structured and allow multiple matching sets

The draft builds:

```text
normalized grantor name -> one set
```

This loses information in two ways:

- two sets with the same grantor name overwrite one another;
- `Grantor.kind` is ignored, so unrelated grantor types with the same display name may collide.

A class set and a spell-list set may both legitimately relate to “Sorcerer.” Name-only matching cannot safely represent that.

#### Suggested alteration

Use structured identity and a one-to-many index, for example:

```text
(grantor_kind, normalized_grantor_name) -> list[VerbSet]
```

The snapshot set model should carry the expected grantor kind explicitly if it does not already do so. A character grantor should be allowed to activate every compatible set, not whichever set happened to win a dictionary overwrite.

Add Task 10 tests for at least:

- two sets activated by the same structured grantor;
- identical names with different grantor kinds not colliding;
- duplicate or ambiguous set declarations producing a named error where ambiguity is not permitted;
- deterministic output independent of snapshot file ordering.

### 3. Resolve item state before catalog matching becomes authoritative

The Task 9 amendment correctly notes that `ParsedExport.items` currently includes unequipped and container-stowed inventory. Task 10 nevertheless treats every catalog item name as held and eligible to grant capabilities.

That makes “owns Chain Mail,” “wears Chain Mail,” and “has Chain Mail stowed in a container” equivalent. The same problem applies to weapons, shields, attuned magic items, and consumables.

#### Suggested alteration

Replace the flat item-name list with structured item facts sufficient for matching. At minimum preserve:

- item name or stable identifier;
- equipped state;
- attunement state where available;
- container or stowed state where available;
- quantity where capability or resource semantics depend on it.

Then let each catalog member or set declare its required state. Do not hardcode “equipped only” globally: some capabilities arise from ownership, some from carrying, and some only while equipped, wielded, or attuned.

If the Notion schema cannot yet express this, constrain Task 10's initial item behavior explicitly and fail or defer unsupported equipment-dependent bindings rather than silently granting them.

Add tests covering owned-but-unequipped, equipped, stowed, and attunement-required items.

## Recommended Task 10 plan amendment

Before writing `matching.py`, insert a Task 10 contract amendment that defines:

1. the source used by level gates;
2. the structured identity of a grantor;
3. whether one grantor may activate multiple sets;
4. item-state facts and member requirements;
5. deterministic behavior when multiple sets hold the same definition;
6. which conditions are matching results and which become named gate failures.

After that amendment, rewrite the Task 10 tests first. The existing pasted implementation should be labeled superseded so another worker does not copy it accidentally.

## Lower-priority process and repository issues

### Plan tracking is stale

The plan's checkboxes remain unchecked even though Tasks 1–9 are complete. Git history makes progress recoverable, but the plan no longer functions as an execution dashboard.

Suggested alteration: mark completed steps, or add a compact status line to each task such as `implemented`, `verified`, `amended`, `superseded`, or `pending`. For amended tasks, place an unmistakable notice above the old pasted implementation that the later amendment and shipped source are authoritative.

### Repository-wide Ruff has no clean baseline

The new subsystem passes Ruff, but `ruff check .` fails on 15 line-length violations in the parked Toki sheet. This does not indicate a defect in the current branch, but it prevents repository-wide Ruff from being a useful binary gate.

Suggested alteration: either repair the parked file in a separately scoped maintenance change or configure an intentional Ruff exclusion/per-file policy for that legacy subtree. Do not mix those formatting changes into Task 10.

### Agent context files remain untracked

`AGENTS.md` and `CLAUDE.md` are untracked. They appear to be generated identity/context anchors, not product files.

Suggested alteration: establish one repository policy—tracked, generated outside the worktree, or ignored—so they do not remain permanent status noise. Do not remove them while an agent is using the worktree.

### Character export growth remains an explicit open item

Keeping real exports committed currently supports reproducible offline tests, which is valuable. The branch also demonstrates how quickly they dominate diffs and repository size.

Suggested alteration: retain them for the present milestone, but resolve the documented policy before the fixture set grows substantially. If they remain committed, consider a deliberate fixture/data policy rather than ad hoc additions.

## Recommendation

**GO** for continued development of the library and evaluator architecture.

**HOLD** implementation of Task 10 until its plan and tests define class-level progression, structured one-to-many grantor matching, and equipment-state semantics.

After that amendment, continue in the existing order. There is no evidence that the project needs an architectural reset or broad refactor. The work through Task 9 is coherent, well tested, and aligned with the approved design.