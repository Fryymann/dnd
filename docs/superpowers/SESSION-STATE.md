# Session state — character sheet crafter

Last updated: 2026-08-09 (paused mid-project, design complete, no code written yet)

## Where we are

Design phase is **done**. Two specs and one implementation plan are written and committed.
**No implementation has started** — `projects/toki_sheet/` is untouched except for a
`npm install` (node_modules, gitignored).

Next action: execute Plan 1, Task 1.

## Documents

| Document | What it holds |
|---|---|
| `docs/superpowers/specs/2026-08-09-character-sheet-crafter-design.md` | The system: runtime PWA + agent-driven authoring layer |
| `docs/superpowers/specs/2026-08-09-verb-layer-design.md` | Verbs → plays → playbooks; the global library and formula model |
| `docs/superpowers/plans/2026-08-09-sheet-decompose-and-deploy.md` | Plan 1 — 15 tasks, 107 steps, TDD |

Commits, oldest first: `205ec9d` `166f54e` `7f64995` `eb24b37` `fa09ff7` `a47a936`
`139d1a1` `7510225`.

## What is being built, in one paragraph

Toki's 115K single-file artifact becomes a modular SPA codebase. One codebase, built once
per character, each deploying to its own GitHub Pages URL as an installable offline PWA.
Character data bakes at build time. On top of that sits a crafter: an agent-driven pipeline
that turns a D&D Beyond export plus Notion records into a tuned sheet, where scripts do
everything deterministic and the agent does only what needs judgment. The sheet's
foundation is a **verb layer** — every discrete thing a character can do, derived from a
rules element, composed into plays, filtered into playbooks.

## Decisions locked (do not re-litigate without reason)

**Shape**
- Static PWA on GitHub Pages, not a Chrome extension page. Chrome for Android has no
  extension support, so an extension could never run on a phone.
- The Chrome extension keeps one job: exporting character JSON from D&D Beyond.
- One SPA codebase, per-character deploys. One crafter run produces one sheet.
- Single operator (Ian, via a coding agent). Players receive a URL and operate nothing.

**Architecture**
- `core/` is pure: no DOM, no storage, no clock. Only `ui/` touches the DOM.
- Characters extend via subclassing `Panel` / `Tab` / `Tracker` / `Lane`, and via rule
  strategies injected into pure functions. Never by importing unexported internals or
  mutating core state.
- Each character is a long-lived sub-project: own `DEVLOG.md`, own `modules/`, own tests.
- Inheritance is not automatic adoption — a core *fix* propagates, a core *capability* is
  opted into per character.

**Verbs**
- The sheet teaches the real game. Identifier is the mechanic slug
  (`class-feature/champion-challenge`), primary label is the rules name, second line is the
  source feature, flavour is a display-only `alias`.
- Global library in `verbs/` (repo, versioned). Per-character bindings generated at build.
- Definitions hold formulas (`8 + CHA_MOD + PROFICIENCY_BONUS`), never numbers.
- All formulas evaluate at build; scaling expands to lookup tables. Runtime does no
  arithmetic.
- Three build gates fail loudly: unmatched capability, unknown variable, play referencing
  an unbound slug.
- At-table view: mode chip (Combat / Exploration / Social) → action cost → category.
- Collapse (`covers`) is decided globally in the library; bindings narrow to held members.

**Data and storage**
- `localStorage` key is `sheet:v1:<campaign>:<char>`. GitHub Pages project sites share one
  origin, so an unnamespaced key would let one character clobber another's tracked HP.
- Notion is authoring-time only, never in the deployed page. Campaign membership comes from
  relation properties on records, never from URL paths.
- Story cache splits: `campaigns/<campaign>/canon/` shared, `campaigns/<campaign>/<party>/logs/`
  per party — DragonLance has two parties.

**Out of scope this version**
- Player-authored verbs and plays at the table.
- AI coaching, ranking, or recommendation at the table.
- Notion as a verb authoring surface.

## Resolved identifiers (Toki)

| Field | Value |
|---|---|
| Campaign | `dragonlance` ("Campaign — DragonLance") |
| Party | Dragonlance 1 (active) |
| Notion character record | `18bfe8ec-ae8f-80b0-a027-f3d1e05bd66f` |
| D&D Beyond id | `123798538` |
| Characters data source | `collection://2e4fe8ec-ae8f-805f-b4f6-000b1148ad99` |
| Relation properties | `🛡️ Campaigns`, `Player Party`, `D&D Player` |

Deploy path `/dnd/dragonlance/toki/`.

## Verified facts (do not re-derive)

- Baseline test suite was **green on 2026-08-09**: 15 suites. `jsdom` was missing and had
  to be installed first — `cd projects/toki_sheet && npm install`.
- `content.test.js` runs 12 times, once per Notion connector state. Dropping Notion
  collapses it to one run.
- Turn-planner references per suite: `hp` 0, `shell` 4, `content` 5, `dice` 27. Plan 1
  parks `dice` because it drives the roller entirely through the Turn UI; `core/dice.js`
  gets stronger direct coverage with an injected RNG.
- `sheet.html` has zero `eval`, `new Function`, or inline event handlers.
- Repo is public: `github.com/Fryymann/dnd`.

## Next session

1. Decide execution mode for Plan 1: subagent-driven (fresh agent per task, review between)
   or inline with checkpoints.
2. Start at Plan 1 Task 1 (`git mv projects/toki_sheet projects/sheets`).

Optional before starting, both offered and neither chosen:
- Split Plan 1 Task 9 (the ~800-line render port) into five per-directory tasks with their
  own parity gates.
- Reconcile the crafter spec's automation table, which the verb layer superseded — verb
  *naming* was its highest-volume agent job and no longer exists.

## Open items

- `covers` grouping policy needs writing down before the first large caster is crafted, or
  collapse decisions drift between authoring sessions.
- `verbs/VARIABLES.md` initial contents — derivable from `distill.py` plus Toki's and
  Bjorn's exports when the evaluator is written.
- Whether plays and playbooks live in Notion for authoring comfort. Verbs are settled as
  repo-only; plays are not yet pressed.
- Per-character icons for the PWA manifests — source and style undecided.
- Player consent before the first deploy that publishes another player's character data to
  a public URL.

## Environment notes

- `CLAUDE.md` at the repo root is untracked. It is a generated KoadOS identity anchor —
  left alone deliberately, neither committed nor ignored.
- `.superpowers/` is gitignored; brainstorm mockups from this session persist there
  (`at-table-layout.html`, `verb-naming.html`).
