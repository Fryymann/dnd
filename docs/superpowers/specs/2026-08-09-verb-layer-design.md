# Verb Layer — Design

Date: 2026-08-09
Status: Approved, ready for planning
Companion to: `2026-08-09-character-sheet-crafter-design.md`
Origin: Notion — "The Verb-First Sheet — Concept & Method (for Clyde)" (Noti, Aug 2026)

## Summary

A character sheet is a reference document; a table needs an instrument. The failure mode
is **decision latency** — a player who spends their turn working out what they *can* do
contributes nothing that round. Players do not think in features; they think in things
they can do.

The verb layer makes those things first-class. Three layers, each built from the one
below:

- **Verbs** — every discrete thing a character can do, derived from a rules element.
- **Plays** — named sequences of verbs aimed at a situation, referenced not copied.
- **Playbooks** — filtered sets of plays; the at-table scope.

Verb *definitions* are global and shared across characters. Verb *bindings* are
per-character and generated. Nothing is hand-copied between characters.

## The governing principle

**The sheet teaches the real game.**

Identifiers, primary labels, and filters use D&D's own vocabulary. Invented language is
display-only and never load-bearing. A player who leans on this for a year should become
better at D&D — not fluent in a private system that strands them at another table. It
also means what they say aloud is what the DM can adjudicate.

This principle overrides the origin brief on naming, and the reason is empirical: shown
side by side, flavour names made the sheet *harder* to read. "Hold the Line" gives no
signal about what is being spent; "Champion Challenge — channel divinity" does.

## Decisions

| Decision | Chosen | Rejected, and why |
|---|---|---|
| Verb identity | Mechanic slug, e.g. `class-feature/champion-challenge` | Sayable name as key — re-flavouring would break every play referencing it |
| Primary label | Rules name + source line | Flavour name (obscures what is spent); flavour with mechanic subtitle (still leads with the invented term) |
| Flavour | `alias` field, display-only | Load-bearing flavour — teaches a proprietary system |
| Library scope | Global, shared across characters | Per-character verb sets — same verb re-authored and re-named per character |
| Source of truth | Repo, versioned | Notion — drift risk; verbs must be exact and diffable |
| Definition content | Data + formulas with variables | Baked numbers — would need re-authoring per character and per level |
| Formula evaluation | All at build; scaling expands to lookup tables | Runtime evaluator (arithmetic returns to the table, bugs fail on a phone); hybrid (two paths, escape hatch overused) |
| Collapse | Decided in the library, globally | Per-character (inconsistent naming across a party) |
| Library gaps | Build fails until authored | Auto-draft (uneven quality); silent skip (a player loses a capability they have) |
| Top-level filter | Three pillars — Combat / Exploration / Social | Binary Combat/Non-Combat — too coarse to narrow an 80-verb list |
| Player-authored verbs and plays | Out of scope this version | In scope — turns the sheet into a content editor; revisit later |

## Model

### A verb is two things

| | Verb definition | Verb binding |
|---|---|---|
| Scope | Global, character-agnostic | One character |
| Lives in | `verbs/` (repo, versioned, reviewed) | `chars/<campaign>/<char>/verbs.json` |
| Holds | slug, rules name, source, pillars, category, action cost, formulas, `covers`, `match`, optional `alias` | evaluated numbers, scaling tables, held members, resource pool, availability |
| Authored | Once, reused by every character forever | Generated at build from the export |

*Champion Challenge* is defined once. Toki's binding is DC 17, 30 ft, 3 uses; another
paladin's is DC 15, 2 uses. Same definition, different numbers, no duplication.

### Library tiers

- **Universal** — Shove, Dash, Dodge, Grapple, Help, Hide, Ready, Search. Every character
  binds them; only numbers differ.
- **Rules elements** — spells, feats, class and species features, item properties. Bound
  only when the export has them.
- **Character-specific** — homebrew, unique items, DM rulings. Still in the library,
  narrowly held.

### Identity never depends on a name

```json
{
  "slug": "class-feature/champion-challenge",
  "match": { "ddbIds": [2072], "aliases": ["Champion Challenge", "Challenge"] },
  "alias": "hold the line"
}
```

Matching runs on D&D Beyond entity id first, then alias. Entity ids survive renames;
aliases catch homebrew and re-imports. Plays reference slugs, so re-flavouring is free and
renaming cannot break anything.

### Collapse is global, narrowed per character

A definition may `cover` several rules elements — one *blast* verb covering comparable
damage spells rather than forty near-identical rows. The binding records which covered
members the character actually holds, so the rendered effect line shows their real
options, never the group's full range.

### The honesty invariant runs both directions

- **Never show what they do not have.** No binding, no verb. Enforced at build.
- **Never hide what they do have.** An export capability with no library definition fails
  the build and names it. A missing definition must never silently cost a player a
  capability they possess.

The second direction is not in the origin brief; it is created by having a shared library
at all.

## Definitions carry formulas, not numbers

```json
{
  "slug": "class-feature/champion-challenge",
  "name": "Champion Challenge",
  "source": { "kind": "class-feature", "feature": "Channel Divinity",
              "subclass": "Oath of the Crown" },
  "pillars": ["combat"],
  "category": "control",
  "actionCost": "action",
  "uses":  { "formula": "CHANNEL_DIVINITY_USES", "reset": "short-rest" },
  "save":  { "ability": "wis", "dc": "8 + CHA_MOD + PROFICIENCY_BONUS" },
  "range": { "formula": "30" },
  "effect": "DC {save.dc} Wis, {range} ft — targets cannot move away"
}
```

### The variable namespace is a contract

`CHA_MOD`, `PROFICIENCY_BONUS`, `CLASS_LEVEL.paladin`, `SPELL_SAVE_DC`, `WALK_SPEED`,
`CHANNEL_DIVINITY_USES` and the rest are defined once in `verbs/VARIABLES.md`, populated
by `distill.py` from the export, and versioned.

**An unknown variable fails the build.** A formula silently evaluating to `NaN` is the
worst available outcome — it reaches a table looking like a real number.

### Formulas mix arithmetic and dice

`"2d8 + STR_MOD"` substitutes to `"2d8 + 7"`, which is exactly what `core/dice.js`
`rollExpr` already parses. The evaluator emits a rollable expression string and the
existing roller consumes it unchanged.

### The DSL stays small

`+ - * / min max floor ceil`, variables, dice terms, parentheses. Parsed, never `eval`'d.
Every expansion is a permanent cost across the whole library, and "just add a
conditional" is how this becomes a programming language.

### Everything evaluates at build

Choice-dependent scaling expands into a precomputed table:

```
binding: class-feature/divine-smite
  scaling:
    slot 1: "2d8"   slot 3: "4d8"   slot 5: "6d8"
    slot 2: "3d8"   slot 4: "5d8"   (+1d8 vs fiend/undead)
```

The runtime ships no evaluator and does no arithmetic. It looks up a row.

## Pipeline

```
export.json ──distill.py──> data.json + context.json   (variable namespace, populated)
                                   │
              match: export capability → library definition
                     by DDB entity id, then alias
                                   │
                   ┌───────────────┴───────────────┐
              all matched                    any unmatched
                   │                               │
          evaluate formulas                  BUILD FAILS, names each gap
          against context
                   │
          chars/…/verbs.json   bindings: numbers, scaling tables, availability
                   │
          plays.json ──references slugs──> validate: every slug binds
                   │
          playbooks.json       named default loadouts
                   │
                 build ──> dist/<campaign>/<char>/
```

### Repo shape

```
verbs/                                  global library, versioned
  universal/shove.json
  class-feature/champion-challenge.json
  spell/fireball.json
  VARIABLES.md                          the namespace contract
chars/<campaign>/<char>/
  verbs.json                            bindings (generated, committed)
  plays.json                            AI-authored, slug references
  playbooks.json                        named default loadouts
```

### New core modules, all pure

| Module | Responsibility |
|---|---|
| `core/formula.js` | Parse and evaluate the DSL. No `eval`. |
| `core/verbs.js` | Index, group and filter bindings by pillar, cost, category |
| `core/plays.js` | Resolve a play's slugs to live bindings |
| `core/playbook.js` | Filter plays by the active loadout |

The runtime performs lookups only.

### Build gates

`validate.py` fails the build on any of:

1. An export capability with no library definition.
2. A formula referencing an unknown variable.
3. A play referencing a slug this character does not bind.

Gate 3 is the origin brief's Mold Earth case — a play silently depending on a capability
the export no longer grants — caught mechanically instead of by eye.

## The at-table view

Selected from three mocked alternatives; chosen for shortest path to a spoken verb.

**Mode chip → action cost → category.**

```
Toki · Turn
[Combat] Exploration  Social
─ Action · attack ──────────────────────────
◆ Attack — Glaive          +11, 1d10+7 slashing, reach 10 ft      Action
◆ Divine Smite             on hit +2d8 radiant per slot · 3rd: 4d8  Free
─ Action · control ─────────────────────────
◆ Champion Challenge       DC 17 Wis, 30 ft — cannot move away · 3 left
  channel divinity · oath of the crown                            Action
◆ Shove                    Athletics vs Athletics/Acrobatics
  universal action                                                Action
─ Bonus · support ──────────────────────────
◆ Lay on Hands             heal from pool · 62 of 70 left         Bonus
─ Not available now (2) ────────────────────
○ Find Steed               used · returns on long rest
```

Rules:

- **Every row is complete.** Cost, resource, remaining uses, and effect with real numbers.
  Success means the player never opens a detail view during play.
- **Primary line is the rules name; second line is the source feature.** `alias` may
  appear in a play's phrasing but never replaces the mechanic name here.
- **Unavailable verbs collapse to a dimmed tail** — never hidden, never mixed in.
- **Pillar first** because it is the coarsest honest cut; **cost second** because that is
  the question a turn actually asks; **category third** as a scanning aid.

Plays and playbooks render above the verb list when a loadout is active. Toggling a play
in or out of a playbook is local state, like HP — selection, not authoring.

## Testing

| Layer | Approach |
|---|---|
| `core/formula.js` | Golden tests: `8 + CHA_MOD + PROFICIENCY_BONUS` against a known context → 17. Parse errors, unknown variables, dice terms, precedence. |
| Library lint | Every definition parses; every referenced variable exists in `VARIABLES.md`; every slug unique. |
| Matching | Fixture export → expected slug set, including a deliberate unmatched entry that must fail. |
| Binding | Golden: Toki's export → expected `verbs.json`. Pins the evaluator against real data. |
| `core/verbs.js`, `plays.js`, `playbook.js` | Pure unit tests on grouping, filtering, slug resolution. |

## Impact on the crafter spec

The automation split moves substantially toward scripts:

| Job | Was | Now |
|---|---|---|
| Extract capabilities | agent | script — match on entity id |
| Compute numbers | agent | script — formula evaluator |
| Author a missing definition | — | agent, once, reused forever |
| Compose plays | agent | agent — unchanged, now the main creative work |
| Name verbs | agent | **removed** — rules names, nothing invented |

The highest-volume generative task in the crafter spec no longer exists. What remains for
the agent is play composition and layout tuning — the work that is genuinely per character
and per player.

`summary.json` gains the bound verb list, which is a better agent-readable digest of what
a character can do than the raw distilled data it replaces.

## Impact on Plan 1

The verb view replaces the Turn tab, so Plan 1 no longer ports it. Verified consequences:

| Suite | Turn-planner references | Fate |
|---|---|---|
| `hp` (25 checks) | 0 | survives intact |
| `shell` (57) | 4 | survives, minor edits |
| `content` (~44) | 5 | survives, minor edits |
| `dice` (25) | 27 | parked — it drives the roller entirely through the Turn UI |

Only the `dice` parity suite parks, and its coverage is replaced by something stronger:
Plan 1 already unit-tests `core/dice.js` directly with an injected RNG. Driving dice
through a UI was always the weaker test.

`core/planner.js` leaves Plan 1 with the Turn tab and returns as `core/verbs.js` plus
`core/plays.js`, which supersede it.

## Out of scope this version

- Player-authored verbs and plays at the table. Revisit once the generated layer is in
  real use.
- AI coaching, ranking, or recommendation at the table. Assistance comes from verb
  quality, layout, and AI-composed plays — all pre-build.
- Notion as a verb authoring surface. Repo only, for drift reasons.

## Open items

- The `covers` grouping policy — which rules elements collapse together — needs a written
  rule in the library README before the first large caster is crafted, or grouping will
  drift per authoring session.
- `VARIABLES.md` initial contents: derivable from `distill.py`'s existing outputs plus
  Toki's and Bjorn's exports, when the evaluator is written.
- Whether plays and playbooks live in Notion for authoring comfort. Deferred; verbs are
  settled as repo-only, plays are not yet pressed.
