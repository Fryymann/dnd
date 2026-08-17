# Session state — character sheet crafter

Last updated: 2026-08-16 (subsystem 1 under construction, tasks 1-9 of 23 complete)

## Where we are

The project changed shape on 2026-08-16. It is no longer per-character static sheets; it is a
**hosted web application on Firebase with at-table authoring**. The design is approved and
written down, one of its four subsystems has an implementation plan, and that plan is nine tasks
in with working code.

Branch `feature/library-and-evaluator`, tip `8b86163`, 31 commits ahead of `main`.
**119 tests pass, ruff clean.** Nothing is merged to `main` yet.

Next action: **amend Task 10 before implementing it.** See the stop notice below.

## Why the shape changed

The DM grants homebrew items, feats and effects mid-session, and D&D Beyond's homebrew system
cannot express them — it models character sheets rather than capabilities, so it has nowhere to
put "the DM gave you a thing that does X". Rafe and Toki both carry crude workarounds that do
not grant what they should.

A verb is exactly that missing container. But a verb that can only be created between sessions
does not solve a problem that happens at the table, which is what this project exists for. So
authoring moved to runtime, and runtime authoring needs a server.

## Documents

| Document | What it holds |
|---|---|
| `docs/superpowers/specs/2026-08-16-runtime-authoring-app-design.md` | The approved design for the whole app |
| `docs/superpowers/plans/2026-08-16-library-and-evaluator.md` | Subsystem 1 — 23 tasks, TDD, five amendment sections |
| `docs/reviews/2026-08-16-library-and-evaluator-top-level-review.md` | Hermes's progress review at `8b86163` |
| `docs/superpowers/specs/2026-08-09-verb-layer-design.md` | The verb layer — still current |
| `docs/superpowers/specs/2026-08-09-character-sheet-crafter-design.md` | Partly superseded; see the new spec's "Relationship to existing specs" |

## The four subsystems

1. **Library and evaluator** — in progress, this is the current plan
2. The sheet — Plan 1's decomposition, reading Firestore
3. At-table authoring — Cloud Functions wrapping `rules_engine`, plus the authoring UI
4. Promotion — the packet format that turns a draft into published library content via Noti

Each gets its own spec, plan and implementation cycle.

## Decisions locked on 2026-08-16

- **Firebase** — Firestore, Hosting, Python Cloud Functions. Chosen over a Pi with a tunnel or a
  managed host: existing GCP projects, prior experience, and offline persistence plus realtime
  come free.
- **Link as key, no accounts.** The character id IS the credential; rules deny `list` so nothing
  permits enumeration. Audience is a fixed group of friends, so validation guards against
  mistakes, not cheating.
- **Offline reads, online writes.** Authoring needs a connection because evaluation is
  server-side; quick capture is the offline authoring path.
- **Formulas evaluate server-side.** The runtime stays arithmetic-free and homebrew scales on
  level-up like library content.
- **Homebrew definitions live in the shared library**, not under a character, with `campaign`,
  `status` and `origin` fields. A definition is a rules element, not character data; what is
  sensitive is who HOLDS it, and that is the binding.
- **Promotion to Notion is a manual packet** handed to Noti. No two-way sync.
- **`rules_engine` imports nothing** from `notion_sync`, `publisher` or `cli`. That purity is what
  lets subsystem 3's Cloud Function wrap it rather than reimplement it.

## Tasks 1-9 — what exists

| # | Module | |
|---|---|---|
| 1 | scaffold | uv, hatchling, pytest, ruff pinned to `["E","F","I","B","SIM","UP"]` |
| 2 | `rules_file.py` | loads `rules/<edition>.toml`, validates shape at load |
| 3 | `facts.py` | `CharacterFacts` — the `character.*` namespace |
| 4 | `formula.py` | whitelisted AST evaluator; the security boundary |
| 5 | `variables.py` | resolves by table / steps / formula / from |
| 6 | `expand.py` | evaluates across levels 1-20 |
| 7 | `models.py` | Definition, VerbSet, Binding, GateFailure + fixtures |
| 8 | `snapshot.py` | reads the committed snapshot |
| 9 | `export_adapter.py` | the only module that knows D&D Beyond's shape |

Absent by design at this milestone: `notion_sync`, `publisher`, `cli`.

## STOP — do not implement Task 10 verbatim

Hermes reviewed the plan's next task and found three unresolved correctness problems. All three
produce silently incorrect **capabilities** — the same failure family as the wrong numbers
already fixed.

1. **Level gates use the wrong progression.** The draft compares a gate against
   `export.facts.total_level`. A Rogue 1 / Sorcerer 13 is character level 14 and must not receive
   Rogue features gated at Rogue 2. Make the progression source declarative on the model rather
   than branching on slug prefixes.
2. **Grantors are keyed only by normalised display name and map to one set.** Two sets sharing a
   normalised grantor means one silently wins.
3. **Inventory matching does not distinguish** owned, equipped, wielded, stowed or attuned.

## Open risks

- **`rules/2024.toml` is `verified = false`.** Every passing test could be green with the
  constants wrong — the engine faithfully computes whatever that file says. Task 15 closes it by
  checking against the printed 2024 PHB. Publish is blocked against an unverified edition until
  then. A green suite currently proves internal consistency and nothing about D&D.
- `walk_speed` ignores speed modifiers — Mobile, Monk, Barbarian would render base speed.
- `items` includes stowed gear. Jeff: 22 entries, 3 equipped, including Chain Mail in his pack.
  Do not add a global filter — a Horn of Valhalla works from a pack and Chain Mail does not.
- `race.fullName` gives "Variant Human" for Jasper; a set authored as "Human" will not match.
- `covers` grouping policy still unwritten before the first large caster.
- Security rules are the entire boundary under link-as-key and must pass the
  `firebase-security-rules-auditor` skill before any real deploy.

## Verified facts — do not re-derive

- D&D Beyond exports are `{"exportedAt", "source", "characterId", "character"}`, **not**
  `{"data": ...}`. Source is `dndbeyond-character-v5`.
- Toki Ironlung is a **level 14 Paladin**. Earlier drafts wrongly assumed a rogue.
- The six exports: Toki 14 Paladin; Billie 13 Warlock 8/Fighter 5; Bjorn 13 Wizard; Jasper 10
  Wizard; Jeff 13 Fighter; The Grey Man 13 Rogue 10/Ranger 3.
- **There is no Rafe export.** His 93 verb rows exist only in Notion. The Grey Man is Task 16's
  multiclass golden fixture instead.
- All six exports are committed; Ian is squaring the publication with his players.
- ruff with only `line-length` set enables 413 rules and would drift between versions.

## Execution method

Subagent-driven: one implementer per task, then spec-compliance review, then code-quality review,
never quality before spec. Brief implementers with the task text unabridged, the amendment
sections that postdate the plan, an explicit statement that the pasted implementation is
**unreviewed**, specific suspect areas to probe, and the project's failure mode named outright.
That briefing shape produced every high-value finding.

Every defect found across nine tasks was in the plan or in instructions — none was a subagent
failing to reproduce specified code. Treat pasted plan code as a hypothesis.
