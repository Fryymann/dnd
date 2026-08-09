# Devlog — Toki Ironlung Field Console

Published artifact: <https://claude.ai/code/artifact/763cf5c0-4e93-4b79-9b7b-36f7260584e4>

A self-contained digital character sheet for Toki Ironlung (Human Paladin 14, Oath of
the Crown, Knight of Solamnia). Character data is baked in from the D&D Beyond export;
campaign data is read live from Notion through the viewer's own connector.

Newest entry first. Dates are `America/Los_Angeles`.

---

## 2026-08-06 — v1 through v6, first build

Built from scratch in one session, then corrected six times against Ian's own sheet.
The corrections are the important part of this entry: **four separate fields in the
D&D Beyond export turned out to be untrustworthy**, and each was caught only because a
human compared a number to the real sheet.

### What shipped

Four tabs against a persistent left rail that never scrolls away.

| Tab | Contents |
|---|---|
| **Turn** | Live arc banner from Notion · four action-economy lanes with per-lane dice rolls · resource forecast · commit step · attack roller · reaction watchlist · roll log · decision tree |
| **Playbook** | The canonical A–G plays with live resource tokens and prepared-spell checks |
| **Sheet** | Abilities, saves, skills, attacks, 31 actions by economy, 26 spells with prepared toggles, inventory, 21 features, 15 feats, both steeds |
| **Codex** | Appearance, personality/ideals/bonds/flaws, backstory, ties, three live Notion panels |

Rail: segmented HP gauge, AC/initiative/speed, passives, senses, hit dice, seven
resource meters, spell slots, death saves, conditions, manual HP adjustments, and
short/long rest buttons. All table state persists to `localStorage` under
`toki-console-v1` and survives republishing.

### The four bad fields

Each of these produced a plausible-looking wrong number rather than an obvious error.

**1. `modifiers[].isGranted` does not mean "this applies."** It distinguishes
*auto-granted* entries (class saves, armor, weapon proficiencies) from ones the player
*chose* (ability score increases, skill picks, languages). Both are in effect.
Filtering on it silently dropped nine ability points and every skill proficiency.

| | before | after | confirmed by |
|---|---|---|---|
| Abilities | 16/14/15/9/14/16 | **20/18/16/10/14/17** | Notion's DEX 18 / CON 16 |
| HP max | 192 | **206** | the cowork dev sheet |
| Initiative | +7 | **+9** | Play A's "+5 Alert, +4 DEX" |
| Passive Perception | 12 | **22** | Ian's D&D Beyond sheet |
| Athletics / Intimidation / Persuasion / Survival | unproficient | **+10 / +8 / +8 / +7** | — |

Perception is proficiency (Human Skillful) *plus* expertise (Observant's Keen
Observer). Saving throws were never affected, because class save proficiencies are
`isGranted: true` — which is exactly why nothing looked wrong at first.

This was fixed twice: once for ability scores, then again for proficiencies when the
passive Perception report arrived. The filter is now gone entirely rather than
patched per call site, with a comment recording both confirmations.

**2. `spellSlots[].available` is always 0.** D&D Beyond's own web app computes slot
maxima client-side; the persisted array only carries overrides. The authoritative
table ships in the same payload at `classes[].definition.spellRules.levelSpellSlots`,
indexed by class level. The distiller now reads that, falling back to a pooled
multiclass calculation via each class's own `multiClassSpellSlotDivisor`, and prefers
the API's numbers whenever they are non-zero.

**3. `spells[].prepared` is always false**, including for spells the live sheet has
prepared. Unusable. Prepared state is now owned by the page: seeded from the
character's class list, tick to correct, persisted. A counter shows the total against
the cap from `levelSpellKnownMaxes` (11 at Paladin 14).

**4. Magic weapon bonuses are not in the item name.** The Dragonlance's **+3** and its
**3d6 force vs dragons** live in `grantedModifiers`; v1 inferred "+1" from the title
and got neither. To-hit went +8 → **+13**.

### Notion, live

Three pages are watched through `window.claude.mcp.watchTool` on `notion-fetch`:
the gameplay reference (for the 🔄 arc callout), the overview, and the story-so-far.

The connector is resolved by **the tool it exposes**, not a hard-coded display name —
`listTools()` runs at boot and matches on `notion-fetch`, so a connector named
something other than "Notion" still works. Every error code gets its own copy and its
own fix; retry is offered only for `server_unavailable`. Authorization denials retract
rendered data, transient errors keep last-good. Freshness comes from
`result.cache.storedAt`, never `Date.now()`.

The page renders completely without Notion. Every failure mode leaves the sheet fully
usable.

### Dice

Everything rolls. `rollExpr()` parses `2d8+3`-style expressions; crits double the dice
and never the flat modifier. The attack receipt shows each d20 face (the discarded
advantage die struck through), each damage source rolled separately, and a
hit/miss/crit/fumble verdict against target AC. Situational modifiers accept dice or
flats (`+1d4` for Bless).

**Rolling never spends resources.** Spending is a separate *Commit round* button. That
separation exposed a real bug: `forecast()` only charged a smite slot when "Divine
Smite" occupied a lane by itself, but a smite rides an attack — so Play A never cost
the slot. Now any attacking round with a smite slot set charges it.

### Drift against the Notion playbook

Resolved with Ian at the table:

- **Spirit Guardians** — prepared. My "not on the prepared list" note was wrong, from
  trusting field 3 above. Replaced with a live prepared-check.
- **Revivify** — not prepared. Play C flags it live and suggests swapping it in.
- **5th-level slot** — Toki has none until level 17. Notion's slot level is wrong, but
  the damage isn't: a 4th-level slot already reaches the 5d8 smite maximum. The
  calculator now caps there.
- **Athlete** — does not grant Athletics proficiency or expertise. Notion's feat table
  says it does; the proficiency actually comes from the Knight of Solamnia background.
  Athletics is +10, confirmed correct.

Still open: **smite-as-a-bonus-action** collides with Pole Strike in Play A. Genuinely
unresolved at the table, so it stays flagged.

### The Chrome extension

Investigated and **left unchanged** — it is not at fault. It stores `body.data`
verbatim, which is exactly what `docs/specs/2026-07-25-character-export-design.md`
specifies (*"Any derived or normalized view of character data"* is explicitly out of
scope). Nothing is missing from its output either: `spellRules` ships inside the
verbatim payload. All 61 of its tests pass. The defect was in this project's consumer,
not the exporter.

Open question for Ian: whether to add a sibling `derived` block to the envelope so
future consumers don't have to rediscover the `spellRules` trick. That needs a spec
amendment and changes the documented file format, so it wasn't done unilaterally.

### Design

Modern tactical HUD. Order of the Crown gold `#C8A33A` as the single accent;
kingfisher `#3E86B0` for interactive; verdigris / ember / blood as a resource ramp kept
separate from the accent so "low" never reads as "branded". Neutrals biased blue-steel
rather than warm cream. Type is the Ubuntu superfamily in three roles — condensed for
chrome, regular for Codex prose, mono for every numeral — subset and inlined as woff2
data URIs (178 KB), because the artifact CSP blocks font CDNs.

### Process note

While editing play strings I injected an unescaped double quote, which broke the
entire inline script — the page shipped, the browser refused the whole block, and
nothing rendered. `build.py` now runs `node --check` on every script block and exits
non-zero with the offending line and caret. Verified by reintroducing the bad quote
deliberately.

Separately, one commit-step assertion returned a string on both branches, so it could
never fail — it printed `slot 1→1` and still reported `ok`. Rewriting it to return
`false` is what surfaced the smite-slot bug. Worth remembering when reading these
suites: a check that cannot fail is worse than no check.

---

## Files

| Path | Purpose |
|---|---|
| `sheet.html` | Source template. `/*__FONTS__*/` and `/*__DATA__*/` are substituted at build. |
| `distill.py` | `character_exports/*.json` → `toki.data.json`. 716 KB → 104 KB. |
| `build.py` | Template + fonts + data → `dist/toki.html`. Syntax-checks before writing. |
| `build_fonts.py` | Subsets and instances the Ubuntu superfamily into `fonts.css`. |
| `toki.data.json` | Distilled character payload (generated). |
| `dist/toki.html` | The publishable artifact, 395 KB (generated). |
| `tests/` | Four suites; `tests/run.js` runs all 15 configurations. |

## Refresh loop

Drop a new export in `character_exports/`, then:

```bash
npm run build && npm test
```

Then republish `dist/toki.html` to the same artifact URL. Table state lives in the
viewer's browser and survives it.

`build_fonts.py` only needs re-running if the type system changes; it requires
`fonttools` and `brotli`, which are not in `package.json` because the output
(`fonts.css`) is committed.

## Testing

650 checks across 15 runs.

| Suite | Covers |
|---|---|
| `shell.test.js` | Render, tabs, trackers, rests, persistence, sheet and codex content |
| `content.test.js` | Corrected stats, A–G plays, resource tokens, drift markers, prepared spells, dragon math, live Notion — run once per connector state |
| `dice.test.js` | Expression parsing, crit doubling, advantage/disadvantage, fumbles, lane rolls, commit, plus 1,200 unstubbed rolls for range sanity |
| `hp.test.js` | Manual temp HP, Aid and Heroes' Feast max bonuses, clamping, rests, persistence, edge cases |

`Math.random` is stubbed to force exact die faces, then restored for statistical
checks. Notion is driven by a stub replaying a real observed `notion-fetch` payload
across twelve connector states including every documented error code.

## Known limits

- Declaring the `mcp` capability means **this page cannot be shared publicly**. Live
  Notion and sharing the sheet with the table are mutually exclusive.
- Table state is per-browser. No sync between devices.
- The page cannot read `character_exports/` directly; refreshing character data means
  re-running the build and republishing.
- Max-HP bonuses are never expired automatically — Aid runs 8 hours and Heroes' Feast
  24, so *Clear* is a deliberate click.
