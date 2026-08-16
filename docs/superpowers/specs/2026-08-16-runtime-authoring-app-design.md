# Runtime Authoring App — Design

Date: 2026-08-16

Status: approved in brainstorming, not yet planned or implemented.

## Summary

The character sheet becomes a hosted web application on Firebase, backed by Firestore,
in place of per-character static builds deployed to GitHub Pages. Characters, verbs, sets
and bindings live in a database the app reads at runtime. Players can author plays, verbs
and grantor sets at the table, mid-session.

Verb definitions are still authored in Notion and still pass through a committed snapshot
in git. Formulas are still evaluated outside the browser. What changes is *when* a verb
can be born: previously only at build time, now also during play.

## Why this changes

The DM grants homebrew — items, feats, spells, effects — during sessions. D&D Beyond's
homebrew system models character sheets rather than capabilities, so it has nowhere to put
"the DM gave you a thing that does X". Rafe's and Toki's homebrew feats are crude
workarounds there, and several do not grant what they should.

A verb is exactly the container that is missing. But a verb that can only be created
between sessions does not solve a problem that occurs at the table, and this project exists
to solve problems at the table. Runtime authoring is therefore not a feature addition; it
is the difference between the verb layer working and the verb layer being a nicer way to
write things down afterwards.

The audience is a fixed group of friends. Rules are not enforced and cheating is not a
threat. Validation exists to catch **mistakes**, not to police players.

## Decisions

| Decision | Choice | Why |
|---|---|---|
| Where writes land | App-owned store; Notion syncs in | Table speed, works when Notion is slow or down, clean line between curated library and table-grown content |
| Platform | Firebase — Firestore, Hosting, Python Cloud Functions | Existing GCP projects and prior Firebase experience; offline persistence and realtime come free; Python functions keep one language |
| Access | Link as key, no accounts | Fits a fixed group of friends; one tap to a sheet mid-session; accounts can layer on later without a data model change |
| Offline | Offline reads, online writes | Internet is stable ~99% of play time; Firestore's SDK provides offline reads with no code |
| Formula evaluation | Server side | Runtime stays arithmetic-free; homebrew scales on level-up like library content; one evaluator, one test suite |
| Runtime authoring scope | Custom plays, single homebrew verbs, homebrew grantor sets, quick capture | All four are real requirements |
| Verb library home | Firestore holds everything, published from the committed snapshot | One read path; homebrew and library render identically |
| Promotion to Notion | App emits a packet, Noti authors it | Matches the working division of labour; avoids two writers on one dataset |
| v1 | Library and evaluator first | Correctness stakes concentrate there; a debug view is enough to prove it |
| Build approach | Pure core driven by a CLI | Rules math is pure logic and tests in milliseconds; the Cloud Function becomes a thin wrapper later |

## Non-goals

- Rule enforcement or anti-cheat of any kind.
- Real user accounts in v1.
- AI coaching, ranking or recommendation at the table.
- Two-way sync with Notion.
- A DM or party view. Realtime listeners make it possible later; it is not v1.

## Architecture

Four units. Dependencies run one way only.

**`rules_engine/`** — pure Python package. Loads `rules/<edition>.toml`, evaluates
formulas, expands scaling into level tables, runs the gates. Given a snapshot and a
character export it returns evaluated bindings or gate failures. Imports no Firebase, no
Notion, no network, no clock. Every correctness stake in the project lives here.

**`notion_sync/`** — pulls the Verb Library and Verb Sets collections into
`verbs/snapshot/`. Depends on the Notion API and nothing else — deliberately not on
`rules_engine`. Its only job is faithful transcription. It does not validate, because
validation belongs to the gates, and doing it here would create two places that decide
what "valid" means.

**`publisher/`** — writes an evaluated result into Firestore. Depends on `rules_engine`
and the Firebase Admin SDK. Holds no math and no rules knowledge; if it needs to compute
something, that computation belongs in `rules_engine`.

**`cli/`** — `pull`, `check`, `build`, `publish`. Orchestration only, no logic.

**The dependency rule:** `rules_engine` imports nothing from the other three. This is what
lets the at-table evaluator be a thin wrapper rather than a second implementation, and it
is the same purity line `core/` already holds in the crafter design.

Out of v1: the sheet UI, the authoring UI, and the Cloud Functions themselves. The debug
view is `check` and `build` printing evaluated bindings as a table.

## Data model

Three record kinds. The split between them is the design.

**Definition** — a rules element, character-independent. Slug (the id), rules name,
source, source feature, category, modes, kind, action cost, cadence, effect text,
formulas, resource kind and amount, `requires[]`, `applies[]`, `covers[]`, rules edition.
Holds formulas, never numbers.

**Set** — a grantor. Slug, `composition` (`apply_all` or `match_members`), level gates,
choice points, rules edition, members by reference.

**Binding** — one definition as held by one character. Alias, evaluated numbers, held
members of a covered group, resource pool, availability. Everything that varies per
character, and nothing else.

### Firestore layout

```
/verbs/{slug}                     library and homebrew definitions   (public read)
/sets/{slug}                      library and homebrew sets          (public read)
/characters/{characterId}         the unguessable id IS the key
/characters/{characterId}/bindings/{slug}    who holds what          (private)
/characters/{characterId}/plays/{playId}                             (private)
/characters/{characterId}/captures/{captureId}   unstructured notes  (private)
/characters/{characterId}/state/{doc}        HP, resources, ticks    (private)
```

Homebrew definitions live in the shared library rather than under a character. A
definition is a rules element, not character data — the DM's homebrew may well be granted
to another character later, and that should be a binding rather than a re-author. What is
sensitive is *who holds* a verb, and that is the binding, which stays private.

Three fields carry the distinction:

- **`campaign`** — `null` for official rules content, a campaign id for DM homebrew.
  Homebrew is offered when granting to characters in that campaign; official content is
  offered everywhere.
- **`status`** — `draft` for anything born at the table, `published` once reviewed. A
  draft works fully on the character that created it and renders identically; it is
  excluded from browsing when granting to someone else. Promotion is `draft` →
  `published` plus a packet for Noti.
- **`origin`** — `library` for anything that came from the snapshot, `table` for anything
  authored in the app. This is what `publish` reads to know which documents it owns.
  A verb authored at the table is `origin: table, status: draft`; once Noti has authored
  it into Notion and the next `pull` brings it back, the snapshot version supersedes it as
  `origin: library, status: published`. `origin` records where a document came from;
  `status` records how far through review it is.

**Quick capture is not a verb.** "The DM gave me something, sort it out later" has no
action cost, effect or formula. Captures live under the character and are *converted into*
a draft verb when someone gives them structure. Raw notes in `/verbs` would make the
library's shape meaningless.

### Evaluation is stored, not computed

A binding carries the source formula for provenance and the expanded table across levels
1–20. The runtime indexes by the character's level and renders a number. Level-up is a
lookup, it works offline, and no arithmetic ships to the browser.

This is also the precise boundary of offline capability. Reading a sheet, and tracking
state on it, work with no signal — Firestore's SDK serves cached reads and queues state
writes. *Authoring* a verb does not, because evaluation happens on the server. Quick
capture is the offline path for authoring: the note is recorded immediately and becomes a
draft verb when there is a connection.

### Bindings denormalize display fields

The sheet renders a character from one collection read rather than a fan-out of joins.
The cost is explicit: a library edit requires republishing affected bindings, and
`publish` owns that.

### Security rules

- `/verbs`, `/sets`: public read, no client write. The server writes them after evaluation.
- `/characters/{id}` and everything beneath: `get` and `update` allowed, `list` denied.
  Knowing the id grants access; nothing permits enumeration.
- No client writes an evaluated field.

## Pipeline and data flow

```
Notion ──pull──▶ verbs/snapshot/ ──┐
                                   ├──check──▶ gate report
character_exports/*.json ──────────┤
rules/<edition>.toml ──────────────┘
                                   └──build──▶ evaluated bindings ──publish──▶ Firestore
```

Each command has one input and one output, and any of them can be re-run without side
effects.

**`pull`** transcribes the Notion collections into `verbs/snapshot/`, one file per record,
sorted keys, stable formatting. Stable ordering is load-bearing: it is what makes the diff
after a Noti authoring run reviewable, which is the entire reason the snapshot exists.
`pull` never validates and writes nothing but the snapshot.

**`check`** resolves a character against the snapshot and runs the gates. Matching follows
composition — a set marked `apply_all` fires wholesale when the export names its grantor;
a set marked `match_members` fires per member, matched against what the export lists.

| Gate | Fails on | Severity |
|---|---|---|
| 1 | Export grantor with no matching set | Hard — names the grantor |
| 2 | Formula references an undeclared variable | Hard — names the variable and the verb |
| 3 | Play references an unbound slug | Hard — names the play and the slug |
| 4 | Unresolvable set member | Hard for a module member; per item for a catalog member |

Gate 4 has two severities because the module and catalog asymmetry is real. An
unresolvable member of a **module** set means the character silently lacks capabilities,
so it stops the build. An unresolvable **catalog** member means one spell or item is
unaccounted for, so it is reported by name and the rest still ship.

**`build`** evaluates every formula against `rules/<edition>.toml`, expands scaling into a
level 1–20 table, and denormalizes display fields onto bindings. Output is a plain JSON
artifact on disk — inspectable, diffable, and what tests assert against. It touches no
network. It runs the gates itself rather than trusting that `check` was run first; an
optional safety check is not a safety check.

**`publish`** writes that artifact into Firestore as a diff, not a wipe. Definitions and
sets upsert by slug, bindings upsert per character. Anything with `origin: table` is never
touched — the server owns library content, the table owns homebrew. When a library
definition changes, publish recomputes and rewrites the bindings that reference it.

**The at-table path reuses the middle two commands.** A player authoring a verb posts it
to a Cloud Function; the function runs the same `check` and `build` code on that one
record and writes the result. Same gates, same evaluator, same expansion — the only
difference is that the input arrives over HTTP rather than from a snapshot file.

## Failure modes

The failure this system exists to prevent is a **silently wrong number**. A sheet that
confidently shows `1d10` when the answer is `3d10` is worse than no sheet, because the
player trusts it and the table does not catch it. These are ordered by how much they serve
that.

**Derived-value diff on publish.** Before writing, `publish` prints every number that
changed, for which character, old and new — `toki · fire-bolt · damage 2d10 → 3d10`.
Level-ups produce expected churn; a Notion edit that quietly moves a spell save DC appears
in the same report. Highest-value safeguard in the design, and nearly free because `build`
already has both artifacts on disk.

**Unverified rules block publish.** `rules/2024.toml` carries `verified = false`. Publish
refuses to run against an unverified edition; `--allow-unverified` is a deliberate,
typed-out override.

**Notion schema drift.** Property names carry emoji and spaces and change when someone
renames a column. `pull` fails on an unresolvable property, names it, and writes nothing —
a partial snapshot that looks complete is worse than no snapshot. Because a full run
rewrites the snapshot, a schema change from a Noti session appears as a reviewable diff
rather than a surprise at build time.

**Notion unavailable.** Nothing happens. The snapshot is committed, so `check`, `build`
and `publish` all work with Notion completely down.

**Gate failure.** Non-zero exit, nothing published.

**Interrupted publish.** All writes are idempotent upserts by slug, batched and chunked to
Firestore's 500-write limit. A publish that dies halfway is fixed by running it again.
There is no cleanup path to get wrong.

**Publish clobbering table-authored content.** Anything with `origin: table` is never
written by `publish` — not updated, not deleted. A homebrew verb captured mid-session
exists nowhere else until it is promoted.

**Leaked character link.** The id is the credential, so rotation is the remedy: write the
character's documents under a new id, delete the old, hand out a new URL.

`rules_engine` touches no network, no clock and no filesystem beyond reading TOML, so it
cannot fail in a way that depends on when or where it runs.

## Testing

TDD, matching the convention set in Plan 1. The architecture split is what makes it
affordable — the valuable code is pure, so most tests are fast and hermetic.

**`rules_engine`** — table-driven unit tests, no I/O: formula evaluation, scaling
expansion, module and catalog matching, each gate. Gate tests assert the *message*, not
only the failure. Gate 1 must name the unmatched grantor; gate 2 must name the variable
and the verb holding it. "Fails loudly by name" is a specified feature, so it is asserted
like one.

**Golden fixtures per character.** Toki and Rafe each get a fixture pairing their real
export with hand-verified expected numbers. These are also the honest answer to
`verified = false`: verifying `rules/2024.toml` means writing anchors against the 2024 PHB
— cantrip scaling at 5/11/17, proficiency bonus by level, sneak attack dice, spell save DC
— and having them pass.

**Small handcrafted snapshots for logic, the real one for smoke.** Unit tests run against
a five-record snapshot where every value is deliberate. One integration test runs the full
committed snapshot end to end, catching what only real data has: the emoji property key,
the spell in two lists, the set with a choice point.

**`notion_sync`** — recorded API responses, replayed. Schema-drift handling is tested by
renaming a property in a fixture and asserting the run fails and names it. One live pull
stays a manual smoke step; nothing in CI depends on Notion being up.

**`publisher`** — Firestore emulator. Upsert idempotency (publish twice, assert one
result), chunking past the 500-write batch limit, and the clobber rule: seed an
`origin: table` verb, publish, assert it is unchanged.

**Security rules get their own suite, and it gates the first real deploy.** Under
link-as-key the rules are the entire security boundary: `list` on characters denied, `get`
with a known id allowed, client write to `/verbs` denied, client write to an evaluated
field denied. Run the `firebase-security-rules-auditor` skill against them before anything
leaves the emulator.

**Not tested:** Notion's API, Firestore's engine, the network. Mocking those tests the
mock.

**Parked:** the 15 Jest suites in `projects/toki_sheet/` stay untouched. v1 is Python and
does not load the sheet.

## Relationship to existing specs

This supersedes parts of
`docs/superpowers/specs/2026-08-09-character-sheet-crafter-design.md` and reshapes
`docs/superpowers/plans/2026-08-09-sheet-decompose-and-deploy.md`. Superseded reasoning
stays readable in those documents rather than being rewritten.

**Superseded:**

- Static per-character builds deployed to GitHub Pages project sites.
- Character data baked in at build time.
- The `localStorage` key `sheet:v1:<campaign>:<char>` and origin-shared namespacing.
  Firestore replaces browser storage as the system of record; the namespacing problem it
  solved no longer exists.
- The dual-channel delivery decision of 2026-08-13, including the inlined standalone
  `.html` and its `file://` constraints. There is no `file://` channel in a hosted app.
- "Player-authored verbs and plays at the table" as a non-goal. It is now the point.
- "Notion as a verb authoring surface" as a non-goal — already superseded on 2026-08-13.

**Survives unchanged:**

- The verb layer: verbs, plays, playbooks, and the layering that keeps judgment in plays.
- Definitions hold formulas, never numbers.
- The runtime performs no arithmetic.
- The four build gates and their loud-by-name failure behaviour.
- Notion as the verb authoring surface, with a committed snapshot for diffs and gates.
- Module and catalog set composition, and the granularity rule.
- Rules constants in `rules/<edition>.toml`, selected by the `Rules` field on a set.
- Naming: the sheet teaches the real game. Slug is the identifier, rules name is the
  primary label, flavour is a display-only alias.
- Notion is relational — campaign and party membership come from relation properties,
  never from a URL path.
- `core/` purity and the extension model, for when the UI is rebuilt.

**Deferred, not cancelled:** Plan 1's decomposition of Toki's 115K single-file sheet.
The modular SPA codebase is still what renders a character; it now reads Firestore instead
of baked data, and it is built after the library and evaluator.

## Sequencing

This design is too large for one implementation plan. It decomposes into four subsystems,
each getting its own spec, plan and implementation cycle.

1. **Library and evaluator (v1, this plan).** `rules_engine`, `notion_sync`, `publisher`,
   `cli`. Debug view only. Ends with Toki's and Rafe's numbers verified against golden
   fixtures and published to Firestore.
2. **The sheet.** Plan 1's decomposition, reading Firestore, deployed to Firebase Hosting.
3. **At-table authoring.** Cloud Functions wrapping `rules_engine`, plus the authoring UI
   for plays, verbs, sets and captures.
4. **Promotion.** The packet format and the flow that turns a draft into published library
   content via Noti.

## Open items

- `rules/2024.toml` is `verified = false`. Closes when the PHB anchor tests are green.
  Publish is blocked against it until then.
- `covers` grouping policy still needs writing down before the first large caster is
  crafted, or collapse decisions drift between authoring sessions.
- A `rules/2014.toml` will be needed the first time a 2014 character is crafted.
- The Verb Bindings structural fix in Notion — one Bindings database with a Character
  relation, replacing the relation that pointed at Rafe's collection only. Identified;
  completion not confirmed.
- Toki's 108 verb rows are on the old schema with migration on hold, to go straight into
  the set-aware shape.
- Rafe's 93 rows are bindings wearing a definition's clothes: baked numbers, character
  voice, no set membership. Promotion into the library splits each row in two. Slugs and
  rules names carry over intact.
- Whether `Universal Action` stays a Source value or is fully replaced by membership in
  `core/universal-actions`.
- Whether plays and playbooks are authored in Notion or only in the app. Verbs are settled.
- The Firestore document shape for plays — they reference verbs by slug, but whether a
  play stores a resolved binding reference or resolves at read time is undecided.
- Player consent before another player's character is reachable by URL.
- Per-character icons for the app — source and style undecided.
- Whether `character_exports/*.json` (593K–1.1M each) stay committed. They are committed
  for now so builds are reproducible offline.
