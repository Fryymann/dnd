# Building a character sheet — process and architecture

Status: **draft, in discussion.** Layout and tabs are deliberately out of scope.
Last revised: 2026-08-06

How we turn a D&D Beyond export into a playable digital character sheet, and where the
line sits between the shareable Core and the modules that stay behind.

---

## 1. What this is for

The Toki sheet was built for one character and hardcodes that character in ~30 places.
The goal now is a repeatable process: hand over a JSON export, answer some questions
about how the character is played, get back a single HTML file that player can keep.

Two audiences wanting different things:

- **The player** gets a self-contained file. Correct without supervision, works offline,
  never depends on Ian's Notion, connectors, or account.
- **Ian** gets the same Core plus modules — story snapshots, drift tracking, DM-adjacent
  material — on copies he never hands out.

---

## 2. Decisions taken

Settled 2026-08-06. Change deliberately; a lot hangs off each one.

| Decision | Choice | Consequence |
|---|---|---|
| **Delivery** | Standalone HTML file | No `mcp` capability in Core, ever. No artifact-platform dependency. Works from a USB stick. |
| **Rule set** | **2024 (5.5e) only** | Core assumes one rules dialect. A 2014 export is refused, not silently mis-built. |
| **Rules knowledge** | Rules library keyed to D&D Beyond `definitionKey`, plus a homebrew layer beneath | Least authoring per character. Validated — see §3. |
| **Source of truth** | **The export.** Notion is story information only | No mechanical data comes from Notion. Removes Notion from the build path entirely. |
| **Authored content** | Sidecar file in the repo, per character | Version-controlled, diffable, survives weekly re-exports untouched. |
| **Update cycle** | Re-extract → diff report → Ian approves → rebuild | Exports may change weekly. Authored content carries forward. |
| **Visual identity** | One neutral shell for everyone | No per-character palette or crest. One thing to maintain, nobody's sheet looks second-class. |
| **Alternate statblocks** | A module, covering forms, companions and buffs | Reusable across Wild Shape, Polymorph, summons and player-acquired forms. |

### Why no live Notion in Core

Declaring the `mcp` capability makes a page **unshareable** — a platform rule, not a
preference. A shared page also can't reach Ian's workspace: connector calls run with the
*viewer's* credentials. With Notion now story-only, it leaves the build path entirely;
any story text is pasted or snapshotted into the character package by hand.

---

## 3. The rules library — validated

Every class feature, feat, item and spell in an export carries a `definitionKey`.

**Keys are stable across characters within a ruleset.** Comparing Toki (Paladin 14) and
Pally (Paladin 5), both 2024: **21 of 21** shared features had identical keys.

```
Aura of Protection     class-feature:10292292  ==  class-feature:10292292
Channel Divinity       class-feature:10292287  ==  class-feature:10292287
Weapon Mastery (feat)  1088085227:1789212      ==  1088085227:1789212
```

**Keys are NOT stable across rulesets.** Toki (2024) vs Tyr (2014) shared **zero** keys
despite both being Paladins with Aura of Protection and Channel Divinity — they are
different definitions describing similar features.

Two consequences:

1. Ruleset is part of the library's identity, not a footnote. Since Core is 2024-only,
   the library is 2024-only and a 2014 export must be **rejected at extraction** with a
   clear message rather than built into a wrong sheet.
2. Detection is reliable: 2024 characters carry a `Core <Class> Traits` feature; 2014
   characters carry markers like Divine Health, Cleansing Touch, Aura of Hate.

### The homebrew layer

The library cannot know about Crownguard, Save-a-Homie!, Death to Dragons, or The
Legendary Dragonlance — they exist only as `characterValues` renames and item notes.
So resolution runs in three passes, last wins:

```
1. derived     — facts stated plainly by the export
2. library     — recognised by definitionKey; supplies riders, resources, interactions
3. homebrew    — characterValues renames/notes and package overrides
```

---

## 4. Core vs modules

### Core — ships to everyone

1. **Extraction** — export → standardised package (§6)
2. **Derived stats** — abilities, saves, skills, AC with breakdown, HP, speeds, senses,
   passives, initiative, proficiency
3. **Spellcasting** — per-class ability, slots from the class table, pact magic,
   prepared tracking against the class cap
4. **Resource economy** — every limited-use resource with a stable id
5. **Action economy** — actions bucketed by activation cost
6. **Dice engine** — expression parsing, crit doubling, advantage, receipts
7. **Attack roller** — weapons plus declared riders
8. **Turn planner** — lanes, per-lane rolls, forecast, commit
9. **Playbook** — renderer and play schema; content is per-character
10. **Trackers** — HP/temp/max-bonus, conditions, death saves, rests, roll log
11. **Reference** — features, feats, inventory, spell detail
12. **Story** — static text captured in the package

### Modules

| Module | Ships to players? | Why it's separate |
|---|---|---|
| `statblocks` | **Yes, when relevant** | Not every character has forms or companions. §5. |
| `story-snapshot` | Yes, optional | Static campaign/story text; opt-in per character. |
| `drift` | No | Needs Ian's table rulings to adjudicate. |
| `dm-notes` | No | Not the player's to see. |

Core containing no character-specific logic is the whole test. If Core has an `if` that
names a class feature, it belongs in the library or the package instead.

---

## 5. The statblock module

One mechanism covering four situations, distinguished by how they relate to the base
character:

| Kind | Relationship | Examples |
|---|---|---|
| `form` | **Replaces** physical stats, AC, HP, speeds; keeps mental stats and some features | Wild Shape, Polymorph, Shapechange |
| `companion` | **Alongside** — a separate entity with its own HP | Alduin, Find Steed, familiars, summons |
| `buff` | **Modifies** the base statblock in place | Rage, Enlarge/Reduce, Starry Form |
| `library` | Player-acquired options they choose from at the table | Forms collected as they level |

Design notes:

- A `form` needs an explicit rule for what survives the transformation. That rule differs
  per source (Wild Shape keeps mental stats and some features; Polymorph is harsher), so
  it belongs in the statblock definition, not in Core.
- Damage taken in a `form` reverts to the base at 0 HP; damage to a `companion` does not.
  Two different HP behaviours, both needing tracking.
- `buff` composes with the base rather than replacing it, so it must apply *after* all
  derived stats are computed.
- The active statblock is **state**, not data — it belongs with the trackers and persists.

Star Druid forces `form` immediately. Toki already needs `companion`. Neither is
optional for the second sheet we build.

---

## 6. The creation process

### Phase 0 — intake
Drop `dndbeyond-<name>.json` into `character_exports/`. Nothing else needed to start.

### Phase 1 — extraction (automated)
Run the extractor. It produces the standardised package (§7) and a **prep report**: what
it found, what it derived, what the library recognised, and — most importantly — **what
it could not resolve**. A 2014 export stops here with an explicit refusal.

### Phase 2 — review with Ian
Walk the prep report together. Every serious bug so far was found by a human comparing a
figure to the real sheet.

- Confirm headline numbers against D&D Beyond: **AC, HP, initiative, passives, spell save
  DC, attack bonuses**.
- Resolve renamed and annotated items — homebrew the library cannot know about.
- Confirm prepared spells. The export's `prepared` flag is unreliable (§8).
- Identify riders the library did not recognise.

### Phase 3 — action and resource inventory
Produce and agree two explicit lists:

- **Action inventory** — everything the character can *do*, bucketed by cost (action,
  bonus action, reaction, movement, free, special).
- **Resource inventory** — everything *spent*, each with a stable id, maximum, reset
  condition, and which actions consume it.

These are the contract between the HUD trackers and every interactive part of the sheet.
Plays reference resources **by id**, never by display name.

### Phase 4 — playstyle interview
Only once mechanics are settled. Ian answers for the player or relays. Topics: role in a
fight, what they always forget, what they over-spend, signature combos, what they do
outside combat, table rulings.

### Phase 5 — draft the plays
Both kinds, iterated with Ian, written to the character's sidecar file:

- **Combat plays** — turn or multi-turn sequences for recognisable situations.
- **Non-combat plays** — social, exploration, downtime, recovery.

Each names its trigger, steps by lane, resource cost, and expected outcome. Every feature
the character owns should appear in at least one play; a feature in no play is one they
will forget at the table.

### Phase 6 — layout
Deferred until Core is settled.

### Phase 7 — build, verify, hand over
Build, run the suites, spot-check against D&D Beyond, hand over.

---

## 7. The update cycle

Exports may change weekly. This is the routine path, not an exception.

```
characters/<name>/
  export.json        latest export           (replaced each update)
  package.json       extracted structures    (regenerated)
  plays.json         authored plays          (hand-edited, never regenerated)
  overrides.json     homebrew + rulings      (hand-edited, never regenerated)
  history/           prior packages          (for diffing)
```

**The cycle:**

1. Drop in the new export.
2. Re-extract to a candidate package.
3. **Diff** against the previous package.
4. Review the diff report; Ian approves.
5. Rebuild; archive the previous package to `history/`.

**The diff report must cover:**

| Category | Why it matters |
|---|---|
| Derived stat changes | AC, HP, saves, skills, passives — the numbers to re-verify |
| Features gained or lost | Level-ups, respecs, subclass changes |
| Spells added, removed, re-prepared | Prepared state is hand-held (§8) and must be re-confirmed |
| Resource maxima | PB-scaled resources shift on proficiency-bonus breakpoints |
| Inventory changes | New magic items alter attacks and AC |
| **Broken references** | Authored content citing something that no longer exists |

That last row is the one that protects the authored work: a play referencing a spell the
character no longer has, or a resource id that vanished, must fail loudly rather than
render a dead token. Authored content is never regenerated — only reported against.

---

## 8. Data structures

First-pass design, shaped against six exports. **Not yet implemented.**

Design rules:

- **Every entity gets a stable id.** Cross-references use ids, never display names. The
  current sheet matches resources by name string and it is the most brittle thing in it.
- **Preserve provenance.** Each derived value records where it came from, so a wrong
  number can be traced instead of re-derived by hand.
- **Homebrew overrides derived values**, never the reverse.
- **Everything is a list, even when there's one.** Single-class assumptions are the
  second-most common bug class found so far.

```
package
  meta          exportedAt, sourceFile, builtAt, coreVersion, ruleset: "2024"
  identity      name, species, classes[], background, level, portrait?
  abilities[]   key, score, modifier, sources[]
  saves[]       key, value, proficient, sources[]
  skills[]      key, ability, value, proficiency: none|half|prof|expertise, sources[]
  defences      ac{value, breakdown[]}, hp{base, max}, speeds{}, senses[],
                passives{}, initiative{value, sources[]}, hitDice[] (per class),
                resistances[], immunities[], conditionImmunities[]
  spellcasting[]  per class: ability, dc, attack, prepareType, preparedMax,
                  slots[], pactSlots[], ritual
  spells[]      id, name, level, school, source, prepared, alwaysPrepared,
                castingTime, range, duration, components, concentration, ritual,
                damage[], save{}, description
  actions[]     id, name, activation, range, target, uses{resourceId}, attack?,
                damage[], description, sourceRef
  resources[]   id, label, max{fixed|pb-scaled|formula}, reset, kind: pips|pool,
                consumedBy[], sourceRef
  attacks[]     id, name, weaponRef, toHit{value, sources[]}, damage[],
                critRange, properties[], mastery, riders[]
  riders[]      id, label, when{always|declared|conditional}, cost{resourceId?},
                damage?, toHit?, advantage?, appliesTo[], sourceRef
  inventory[]   id, name, originalName?, note?, qty, weight, equipped, attuned,
                rarity, magicBonus, grantedModifiers[]
  features[]    id, name, level, class, subclass, description, definitionKey
  feats[]       id, name, description, definitionKey
  statblocks[]  id, name, kind: form|companion|buff, source, retains[], stats{},
                ac, hp, speeds{}, senses[], traits[], actions[], duration,
                resourceId?
  story         appearance, personality, ideals, bonds, flaws, backstory, ties{}
  plays[]       id, name, type: combat|noncombat, tags[], trigger, steps[],
                cost[{resourceId, n}], notes
```

`riders[]` is what generalises Divine Smite, Sneak Attack, Radiant Strikes, Hunter's Mark
and Bardic Inspiration into one mechanism the attack roller consumes without knowing what
any of them are.

### Cases the structures must survive

| Case | Character | What it breaks |
|---|---|---|
| Multiclass | Buttery (Bard 11 / Warlock 2) | `hitDice[0]`, `classes[0]`, one spellcasting ability |
| Pact magic | Buttery | Separate slot pool on a **short** rest |
| Full prepared caster, 92 spells | Bjorn (Wizard 13) | Spell list scale, spellbook vs prepared |
| Low level | Star Druid (3), Pally (5) | Sparse everything; few subclass features |
| Shapeshifting | Star Druid | Wild Shape as resource *and* stat-replacing form |
| PB-scaled uses | Toki, Bjorn | `maxUses: 0` + `useProficiencyBonus: true` |
| Heavy homebrew | Toki | Renames and notes in `characterValues` |
| Conditional riders | Toki | +3d6 vs dragons; advantage vs dragons |
| Non-standard crit range | Toki | 18–20 from an item note, not a field |
| Same class, different level | Toki 14 / Pally 5 | Feature-set differences; library key stability |
| Wrong ruleset | Tyr (2014) | Must be refused, not mis-built |

---

## 9. Export fields that cannot be trusted

Every one produced a plausible wrong number rather than an error. The extractor must
handle all of these, and the prep report must state which fired.

| Field | Reality | Correct source |
|---|---|---|
| `modifiers[].isGranted` | Means auto-granted vs **player-chosen**, not "applies". Filtering on it drops every ASI and skill proficiency. | Ignore the flag entirely. |
| `spellSlots[].available` | **Zero on all six characters.** D&D Beyond computes maxima client-side. | `classes[].definition.spellRules.levelSpellSlots[level]` |
| `spells[].prepared` | False even for spells the live sheet has prepared. | Unknowable — confirm with the player, then store in the package. |
| Magic weapon bonus | Not in the item name. | `grantedModifiers[]` where `subType == "magic"` |
| `activationType` 8/9/10 | "Legendary/Mythic/Lair" — meaningless on a PC. | Treat as "Special". |
| Ability score | Base only; racial and ASI bumps are separate. | `stats` + `bonusStats` + `-score` modifiers |
| `spellCastingAbilityId` | Correct, but **per class** — assuming one ability is wrong on multiclass. | Read per class. |

The Chrome extension is **not** at fault for any of these. It stores the API payload
verbatim, which its spec requires, and everything needed is present in that payload.

---

## 10. Open questions

1. **Project layout.** Outgrowing `projects/toki_sheet/`. Proposal: promote to
   `projects/character_sheet/` with `core/`, `library/`, `characters/<name>/` — do this
   when the second sheet starts.
2. **Rules library scope.** Start with the classes on hand (Paladin, Wizard, Bard,
   Warlock, Druid) and grow on demand, or attempt broad coverage up front?
3. **Storage keys.** Two sheets sharing `localStorage` would clobber each other. Key by
   character id — decide the namespace before the second sheet exists.
4. **Verification bar.** What must match D&D Beyond before a sheet ships? Proposal: AC,
   HP, initiative, all passives, spell DC, and every attack bonus.
5. **Martial coverage.** Every export on hand is a caster. Pally is being re-rolled to
   close this (§12); until then, martial resource shapes and alternate AC formulas are
   unverified.

---

## 12. Test fixtures

**Pally is not a played character.** It exists to exercise the extractor, and Ian can
re-class it in D&D Beyond and re-export on demand. Treat it as a generator for structural
cases rather than a person.

Every other export is a caster, so the martial half of the rules surface is unverified.
Priority order for re-rolls, chosen by what each one breaks that nothing else does:

| # | Build | Uniquely exercises |
|---|---|---|
| 1 | **Barbarian** ~5 | Unarmored Defense (10+DEX+**CON**) — a second AC formula; Rage as a `buff` statblock *and* a resource; Reckless Attack as declared advantage |
| 2 | **Rogue** ~5 | **Sneak Attack** — the canonical conditional rider the whole `riders[]` design rests on; Cunning Action bonus-action economy; expertise at scale |
| 3 | **Monk** ~5 | Unarmored Defense (10+DEX+**WIS**) — a *third* formula; Focus points as a **short-rest** pool; the Martial Arts die as a level-scaling die |
| 4 | **Fighter (Battle Master)** ~5 | **Action Surge** — grants an extra action, mutating the action economy itself; superiority dice as a pool *of dice*; Second Wind |
| 5 | **Sorcerer** ~5 | Sorcery points ↔ spell slots — **convertible** resources, which no current structure models |
| 6 | **Multiclass, mismatched hit dice** | e.g. Fighter/Wizard — `hitDice[]` as a genuine list (d10 + d6); two different spellcasting abilities on one sheet |

Level ~5 is enough for each: it reaches the subclass and the signature resource without
the bulk of a high-level spell list.

Two of these change Core's shape rather than just its data:

- **Unarmored Defense** proves AC needs a formula resolver, not `10 + dex`.
- **Action Surge** proves the turn planner cannot assume one action lane.

## 11. Next work

1. Design and validate the structures in §8 against all six exports.
2. Build the extractor to emit the package plus the prep report, refusing 2014.
3. Build the differ and the update cycle (§7).
4. Stand up the rules library with the five classes on hand.
5. Rebuild Toki through the new pipeline and diff against the current sheet — its numbers
   are confirmed correct against D&D Beyond, which makes it the regression test.
6. Then, and only then, layout.
