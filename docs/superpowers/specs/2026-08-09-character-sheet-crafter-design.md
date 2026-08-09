# Character Sheet Crafter — Design

Date: 2026-08-09
Status: Approved, ready for planning

## Summary

Turn the one-off Toki Ironlung artifact into a system that crafts tuned digital
character sheets for 5–6 characters across multiple campaigns and players.

Two layers, deliberately separate:

- **Runtime layer** — a self-contained offline PWA per character, deployed to GitHub
  Pages. No network dependency at play time.
- **Authoring layer** — an agent-driven pipeline that builds those sheets from D&D
  Beyond exports, repo workshop notes, and Notion databases. Scripts do everything
  deterministic; the agent does only what needs judgment.

The Chrome extension keeps its existing single job: exporting a character's JSON from
D&D Beyond. It does not host the sheet.

## Goals

- One SPA codebase, built once per character, each deploying to its own URL.
- Sheets work fully offline on a phone, installed to the home screen.
- Each character is hand-tuned without forking shared code.
- Adding a seventh character touches only that character's folder.
- Crafting a sheet is a repeatable agent procedure, not an ad-hoc prompt.
- Minimum tokens per character: scripts wherever a script can do the job.

## Non-goals

- No Notion access from the deployed page. Notion is authoring-time only.
- No backend, no auth, no server. Static hosting only.
- No runtime D&D Beyond calls in production.
- No generic "render any character's export" mode. Sheets are hand-tuned.
- No cross-character or party-wide runtime features in this version.

## Decisions

| Decision | Chosen | Rejected, and why |
|---|---|---|
| Host | Static PWA on GitHub Pages | Chrome extension page — Chrome for Android has no extension support at all, so a phone could never run it |
| Character data | Baked at build time | Runtime file load and cloud sync — 5–6 hand-tuned sheets don't need either |
| Build shape | One SPA codebase, N per-character builds | Single multi-character SPA — would ship every player's data inside every other player's install |
| Code sharing | Shared pure core + per-character shell | Fork per character (drifts); one rigid template (caps tuning) |
| Notion at runtime | Removed entirely | Snapshot and live-proxy — both add hassle once sheets are not just for one person |
| Notion at authoring | `ntn` CLI, invoked by the agent | Agent MCP pull — every row would pass through model context on each refresh |
| Toolchain | Python for data, esbuild for JS | Porting `distill.py` to JS — risks re-introducing the four documented D&D Beyond field bugs |
| Offline | Installable, offline, explicit update prompt | Silent update — a version swap mid-combat is worse than a banner |
| Skill location | `.claude/skills/` in this repo | User-level skills only — would not follow the repo between laptop and desktop |

## Architecture

Nothing at runtime talks to D&D Beyond or Notion. The deployed output is inert static
files, which is what makes offline play and free hosting possible.

```
D&D Beyond ──[extension: export]──> chars/<campaign>/<char>/export.json  (committed)
Notion DBs ──[ntn CLI sync]───────> registry.json                        (committed)
workshop notes ──[agent]──────────> plays.js, layout.js                  (committed)
                                              │
                            distill.py + esbuild + build.py
                                              ▼
                    dist/<campaign>/<char>/  index.html app.js sw.js manifest.json
                                              │
                                    git push → GitHub Action → Pages
                                              ▼
                          phone: installed PWA, offline, localStorage state
```

### Layer boundaries

| Layer | Knows | Must not know |
|---|---|---|
| `src/core` | dice math, HP rules, state persistence | any character, tab, or campaign |
| `src/ui` | DOM rendering, panel chrome | game rules; it receives computed values |
| `src/app` | shell, routing, service worker lifecycle | any specific character |
| `chars/*/layout.js` | that character's tabs, lanes, plays | how dice or storage are implemented |
| `chars/*/data.json` | distilled stats, spells, items | nothing — pure data |

**Enforced rule: `core` is pure.** No DOM, no `localStorage`, no `Date.now`. Only `ui`
touches the DOM. This is what keeps modules small and makes `core` testable without
jsdom.

## Repo layout

```
projects/sheets/
  registry.json  local cache of Notion campaign/character/player/party rows
  src/core/      dice.js hp.js state.js format.js spells.js weapons.js
                 attack.js damage.js planner.js roll-log.js
  src/ui/        dom.js rail/ turn/ playbook/ sheet/ codex/
  src/app/       main.js shell.js events.js sw.js
  chars/<campaign>/<char>/
                 character.json export.json data.json summary.json
                 derived.lock.json plays.js layout.js
  tools/         distill.py build_fonts.py build.py
                 sync_notion.py new_character.py validate.py
  tests/         core/ ui/ golden/ fixtures/
  dist/          <campaign>/<char>/…
.claude/skills/craft-character-sheet/SKILL.md
```

Character *development* material is not duplicated here. `characters/active/<slug>/`
already holds concept, workshop, and build notes per `characters/README.md`;
`character.json` points at that slug.

### `character.json`

```json
{
  "id": "toki",
  "name": "Toki Ironlung",
  "player": "Ian",
  "campaign": "<campaign-id>",
  "notionPageId": "<uuid>",
  "workshop": "characters/active/toki-ironlung"
}
```

The Notion page id is the durable link — it survives renames of both the character and
the folder.

## Module decomposition

The sheet's JavaScript currently runs `sheet.html:638–2268`, about 1,630 lines in 13
banner sections. Extraction map:

| Current (`sheet.html`) | Lines | → Module | Kind |
|---|---|---|---|
| `blank`, load, `save`, `set` | 784–842 | `core/state.js` | pure + storage port |
| `hpMax` | 809 | `core/hp.js` | pure |
| `el`, `esc` | 844–847 | `ui/dom.js` | DOM |
| `clamp`, formatting | 849–860 | `core/format.js` | pure |
| `preparedCount` | 861–866 | `core/spells.js` | pure |
| `weapons` | 867–894 | `core/weapons.js` | pure |
| `rollExpr`, `rollD20` | 895–929 | `core/dice.js` | pure, injected RNG |
| `logRoll` | 930–934 | `core/roll-log.js` | pure |
| `rollAttack` | 935–954 | `core/attack.js` | pure |
| `outcome` | 955–992 | `core/damage.js` | pure |
| `laneOptions`, `resLeftFor`, `forecast` | 993–1054 | `core/planner.js` | pure |
| Notion block | 1055–1254 | **deleted** | — |
| `renderRail` | 1255–1430 | `ui/rail/` (4 files) | DOM |
| `renderTurn` and helpers | 1431–1764 | `ui/turn/` (6 files) | DOM |
| `renderPlaybook`, `tokens`, `loadPlay` | 1765–1871 | `ui/playbook/` (3 files) | DOM |
| `renderSheet`, `itemBlock` | 1872–2064 | `ui/sheet/` (5 files) | DOM |
| `renderCodex` | 2065–2143 | `ui/codex/` (2 files) | DOM |
| `render`, shell, events | 2144–2268 | `app/shell.js`, `app/events.js` | DOM |
| playbook A–G data | 641–783 | `chars/*/plays.js` | character data |
| `const DATA` | 639 | `chars/*/data.json` | character data |

The two largest functions split by the visual unit they emit:

```
ui/turn/   index.js lane-card.js roll-card.js face-chips.js
           commit-bar.js cost-line.js forecast-panel.js
ui/sheet/  index.js ability-block.js skill-table.js
           action-list.js spell-list.js item-block.js
```

Deleting the Notion block removes roughly 200 lines of connector handling
(`needs_reauth`, `server_not_connected`, live watches, freshness display) and replaces
it with nothing — the Codex tab keeps appearance, personality, ideals, bonds, flaws,
backstory, and ties, all of which come from the D&D Beyond export.

## Build pipeline

```
npm run build -- <campaign>/<char>
  1. tools/distill.py     export.json  → data.json + summary.json + derived values
  2. tools/build_fonts.py (shared)     → dist/_fonts/*.woff2 + fonts.css
  3. esbuild  app/main.js + chars/…/layout.js → dist/…/app.js (+ sourcemap)
  4. tools/build.py --char …           → dist/…/index.html + manifest.json + icons
  5. stamp BUILD_ID (git short sha)    → dist/…/sw.js
npm run build:all
```

`distill.py` and `build_fonts.py` are unchanged. `distill.py` gains one addition: it
emits `summary.json` and the derived-value set (see Failure modes).

**Fonts stop being base64.** `fonts.css` is 178K of `data:` URIs because an Artifact must
be a single file; GitHub Pages has no such constraint. Real `.woff2` files are ~25%
smaller (base64 inflates by a third) and the service worker caches them once across all
characters instead of once per character.

Approximate first load per character: `index.html` ~30K + `app.js` ~120K + `data.json`
~104K + fonts ~130K shared ≈ 380K. Zero on every subsequent open.

## Deploy, storage, and offline

Push to `main` → GitHub Action → `npm run build:all` → publish `dist/` to Pages.

URLs: `fryymann.github.io/dnd/<campaign>/<char>/`.

### Origin-shared storage — mandatory namespacing

GitHub Pages project sites are all one origin (`fryymann.github.io`), and `localStorage`
is scoped to origin, **not path**. The sheet today uses a single fixed key
(`sheet.html:830`). Shipped as-is across six characters, opening one would overwrite
another's HP, slots, prepared spells, and roll log.

| Thing | Namespaced | Value |
|---|---|---|
| `localStorage` key | required | `sheet:v1:<campaign>:<char>` |
| SW cache name | required | `sheet-<campaign>-<char>-<BUILD_ID>` |
| SW scope | automatic by path | `/dnd/<campaign>/<char>/` |
| Manifest `start_url`, `scope` | required | `/dnd/<campaign>/<char>/` |

`core/state.js` takes the character id as a constructor argument — never a module-level
constant — so the collision is structurally impossible rather than merely remembered.

### PWA

- Per-character `manifest.json` with its own name and icons; installs as its own app.
- Service worker precaches the shell at install; cache-first thereafter. Full offline use.
- A new build installs in the background and parks in `waiting`. The app shows a
  **"New version — reload"** banner; the reload happens only on tap. State lives in
  `localStorage` and survives it either way.

## Failure modes

| Failure | Caught at | Behavior |
|---|---|---|
| `layout.js` references an id absent from `data.json` | build | Build fails, names the missing ids |
| Derived values shifted since last build | build | Prints a diff, build continues |
| Corrupt or stale saved state | runtime | Merge onto `blank()`, or reset on schema bump |
| A character's `layout.js` throws | runtime | That tab shows a fallback; rest stays live |
| Broken service worker wedges the app | runtime | `?reset` escape hatch |
| Storage write fails | runtime | Visible warning, never silent |
| First visit while offline | runtime | Plain message |

### Schema versioning

State gains a `schemaVersion`. On mismatch, run migrations; if none applies, reset that
character's state **and tell the player** their tracked HP and slots were cleared. A
silent reset mid-campaign is worse than the message.

### Derived-value diff

The DEVLOG records four D&D Beyond export fields that proved untrustworthy, each caught
only because a human compared a number against the real sheet. That comparison becomes
automatic: each build writes AC, HP max, save DCs, attack bonuses, and slot counts to
`derived.lock.json`, and the next build diffs against it:

```
toki: AC 21 → 19        (!)
toki: hpMax 128 → 134
```

The build does **not** fail — leveling legitimately changes these. It puts the numbers in
front of a human at the moment they can still be checked, which is how the bugs were
found the first time. The lock file is committed, so the diff also shows up in the PR.

### Silent save failure — existing behavior to fix

`save()` is currently `try { … } catch {}` (`sheet.html:840`). With storage full or in iOS
private browsing, every change is discarded with no indication and the player finds out
at the end of a session. Replace with a persistent "not saving — changes will be lost on
reload" banner. The sheet keeps working in memory.

### SW recovery

A broken service worker can wedge an installed PWA permanently — there is no URL bar to
hard-refresh from once it is on a home screen. A `?reset` query param unregisters the
worker, clears caches, and reloads. Roughly ten lines. Without it the only remedy is
uninstalling the app, which is a bad thing to discover at a table.

### Per-tab error boundary

Each tab renders inside a try/catch. A throw shows that tab's fallback with the message;
the rail and other tabs stay live. A typo in one character's playbook should not cost
them their HP tracker mid-fight.

## Authoring layer

**Governing rule: scripts do anything deterministic; the agent does only what needs
judgment.** Any job AI does that a script could do is tokens spent again on every future
character.

### Deterministic — `tools/`, zero tokens

| Job | Tool |
|---|---|
| Pull campaign / character / player / party rows from Notion → `registry.json` | `sync_notion.py` wrapping the `ntn` CLI |
| Raw export → `data.json` | `distill.py` |
| Emit `summary.json`, a ~3K agent-readable digest | `distill.py` |
| Scaffold a character folder with ids prefilled from the registry | `new_character.py` |
| Validate `layout.js` / `plays.js` ids against `data.json` | `validate.py` |
| Derived-value diff | `validate.py` |
| Bundle, build, stamp, deploy | esbuild, `build.py`, Action |

The Notion integration token lives in the local environment only. It is never committed
and never reaches the deployed page.

### Agent — interpretation only

| Job | Why a script cannot |
|---|---|
| `characters/active/<slug>/` notes → `plays.js` | Turning stated fantasy and playstyle into concrete plays is design judgment |
| Tune `layout.js` — lanes, tabs, thresholds | Bespoke per character, which is the point |
| Select campaign context from Notion transcripts for the Codex tab | Requires reading and choosing from prose |
| Adjudicate export oddities against the real sheet | The four known bad fields were caught by judgment |

### Token discipline

1. **The agent never reads `export.json`.** 716K raw, 104K distilled — both too large to
   load repeatedly. It reads `summary.json` (~3K).
2. **Script-verified output.** The agent writes `plays.js`; `validate.py` proves every
   referenced id exists. No second pass spent re-checking its own work.
3. **The procedure is a skill.** `.claude/skills/craft-character-sheet/` holds the steps,
   templates, and validation gates. Committed to this repo so it follows the checkout
   between laptop and desktop, and versioned alongside the tools it drives.

### Privacy

Other players' character data would be published under a public repo and a public Pages
URL. It is their data, and once on a public URL it can be cached and indexed even after
removal. Get each player's agreement before the first deploy that includes them.

## Testing

**The baseline comes first.** The four existing test files (`dice`, `hp`, `shell`,
`content`) are ported to run green against `sheet.html` *as it stands* before any module
moves. That run is the only evidence the decomposition preserved behavior; tests written
after a refactor merely describe the new code.

| Layer | Runner | Notes |
|---|---|---|
| `core/*` | node, no jsdom | Pure functions; `dice.js` takes an injected RNG |
| `ui/*` | node + jsdom | Render to a fragment, assert structure |
| `distill.py` | golden fixture | Fixture export → expected `data.json`, compared exactly |
| `validate.py` | fixtures | A layout with a missing id must fail the build |
| build | smoke | `build:all` produces expected files for every character |

Two tests exist specifically for identified hazards:

1. **Golden distill test** — guards the four untrustworthy-field corrections, which
   currently live only inside `distill.py` with nothing pinning them.
2. **Storage isolation test** — loads two characters in one origin and asserts neither
   can read or clobber the other's key. Direct regression test for the collision above.

**Manual checklist, shipped in the repo** — PWA install, airplane-mode offline, the
update banner, and `?reset` recovery, walked on a real phone before a character goes
live. Service worker lifecycle testing costs more than it returns at this scale.

## Implementation sequence

1. Port the four test files; confirm green against the current monolith.
2. Extract `core/*` one module at a time, tests green after each.
3. Extract `ui/*`; delete the Notion block.
4. Stand up `app/*`, esbuild, and the per-character build.
5. Namespace storage; add the isolation test.
6. Migrate Toki into `chars/<campaign>/toki/`; verify output matches the current sheet.
7. Add service worker, manifest, `?reset`, and the update banner.
8. Add the Pages Action; deploy Toki; walk the manual checklist on a phone.
9. Add `sync_notion.py`, `new_character.py`, `validate.py`, `derived.lock.json`.
10. Write `.claude/skills/craft-character-sheet/`.
11. Craft the second character end-to-end through the skill; fix what the process exposes.

Steps 1–8 deliver a working deployed sheet. Steps 9–11 turn it into a system. Anything
the skill cannot do smoothly for character two is a defect in the system, not in
character two.

## Open items

- Campaign ids come from Notion; exact slugs are set when `sync_notion.py` first runs.
- Icon set per character — source and style undecided.
- Whether `export.json` (716K–1.1M each) stays committed or is fetched on demand; it is
  committed for now so builds are reproducible offline.
