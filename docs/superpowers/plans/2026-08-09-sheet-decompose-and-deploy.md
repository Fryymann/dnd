# Toki Sheet — Decompose and Deploy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `projects/toki_sheet/sheet.html` — a 115K single-file artifact — into a modular SPA codebase that builds and deploys Toki's sheet to GitHub Pages as an installable offline PWA, with behavior provably unchanged.

**Architecture:** Pure functional `core/` (no DOM, no storage, no clock) plus `ui/` base classes a character subclasses. The existing jsdom suites are kept running against the built page the entire time as a parity harness — the old page's tests must pass against the new one before the old page is deleted.

**Tech Stack:** Node 24 (built-in `node:test`), esbuild, jsdom, Python 3 (`distill.py`, `build.py`, unchanged parsing), GitHub Actions → Pages.

**Spec:** `docs/superpowers/specs/2026-08-09-character-sheet-crafter-design.md`

**Plan 2** (the crafter: Notion sync, validators, capability manifest, skill) is written after this plan completes, per the spec's split.

---

## Required input

This plan needs exactly one value it cannot derive: **Toki's campaign slug** (lowercase, hyphenated). It sets the folder path, the deploy URL, the service worker scope, and the storage key. In Plan 2 the Notion sync becomes authoritative for it; here it is entered by hand once, in Task 10.

Referred to below as `<campaign>`. Substitute the real slug everywhere it appears.

---

## Baseline (verified 2026-08-09)

`cd projects/toki_sheet && npm install && npm test` → **all 15 suites pass**:

| Suite | Checks |
|---|---|
| shell | 57 |
| dice | 25 |
| hp | 25 |
| content `[ok]` | 51 |
| content `[renamed]`, `[noconnector]`, `[absent]` | 44 each |
| content `[error:*]` × 8 | 45 each |

`content.test.js` runs 12 times, once per Notion connector state. Removing Notion collapses it to a single run; the ~44 checks common to every mode are the non-Notion ones and must all survive.

---

## File structure

| File | Responsibility |
|---|---|
| `projects/sheets/src/core/format.js` | `clamp`, `esc` — pure string/number helpers |
| `projects/sheets/src/core/dice.js` | `rollExpr`, `rollD20` — RNG injected |
| `projects/sheets/src/core/roll-log.js` | `pushRoll` — bounded roll history |
| `projects/sheets/src/core/hp.js` | `effectiveHpMax` |
| `projects/sheets/src/core/spells.js` | `preparedCount` |
| `projects/sheets/src/core/weapons.js` | `weapons` — derives weapon rows from data |
| `projects/sheets/src/core/damage.js` | `outcome` — damage math |
| `projects/sheets/src/core/attack.js` | `rollAttack` — composes dice + damage |
| `projects/sheets/src/core/planner.js` | `laneOptions`, `resLeftFor`, `forecast` |
| `projects/sheets/src/core/state.js` | `createStore` — namespaced persistence |
| `projects/sheets/src/ui/dom.js` | `el` — the only DOM primitive |
| `projects/sheets/src/ui/Panel.js` | `Panel` base class |
| `projects/sheets/src/ui/Tab.js` | `Tab` base class |
| `projects/sheets/src/ui/Tracker.js` | `Tracker` base class |
| `projects/sheets/src/ui/Lane.js` | `Lane` base class |
| `projects/sheets/src/ui/rail/` | Left rail, 4 files |
| `projects/sheets/src/ui/turn/` | Turn planner, 7 files |
| `projects/sheets/src/ui/playbook/` | Playbook, 3 files |
| `projects/sheets/src/ui/sheet/` | Sheet tab, 6 files |
| `projects/sheets/src/ui/codex/` | Codex tab, 2 files (no Notion) |
| `projects/sheets/src/app/main.js` | Entry: wires store, tabs, events |
| `projects/sheets/src/app/shell.js` | Tab shell and render loop |
| `projects/sheets/src/app/events.js` | Global event delegation |
| `projects/sheets/src/app/sw.js` | Service worker source |
| `projects/sheets/src/app/update-banner.js` | "New version — reload" UI |
| `projects/sheets/chars/<campaign>/toki/` | Toki's data, plays, layout, DEVLOG |
| `projects/sheets/tools/build.py` | Per-character page assembly |
| `projects/sheets/tools/build_fonts.py` | Emits real `.woff2` (no base64) |
| `.github/workflows/pages.yml` | Build all characters, deploy |

---

## Task 1: Rename the project and confirm the baseline

**Files:**
- Move: `projects/toki_sheet/` → `projects/sheets/`
- Modify: `projects/sheets/package.json`

- [ ] **Step 1: Move the directory, preserving history**

```bash
cd /home/ideans/data/projects/dnd
git mv projects/toki_sheet projects/sheets
```

- [ ] **Step 2: Rename the package**

In `projects/sheets/package.json`, change:

```json
  "name": "toki-sheet",
```

to:

```json
  "name": "dnd-sheets",
```

- [ ] **Step 3: Install and run the baseline suite**

```bash
cd projects/sheets && npm install && npm test
```

Expected: `all suites passed`, 15 suites listed.

- [ ] **Step 4: Commit**

```bash
git add -A projects/sheets
git commit -m "refactor: rename toki_sheet to sheets ahead of decomposition"
```

---

## Task 2: Unit test harness and the first pure module

Establishes `node:test` for module-level tests, separate from the jsdom parity suites.

**Files:**
- Create: `projects/sheets/src/core/format.js`
- Create: `projects/sheets/tests/core/format.test.js`
- Modify: `projects/sheets/package.json`

- [ ] **Step 1: Add the unit test script**

In `projects/sheets/package.json`, replace the `scripts` block with:

```json
  "scripts": {
    "build": "python3 distill.py && python3 build.py",
    "test:parity": "node tests/run.js",
    "test:unit": "node --test tests/core/ tests/ui/",
    "test": "npm run test:unit && npm run test:parity"
  },
```

- [ ] **Step 2: Write the failing test**

Create `projects/sheets/tests/core/format.test.js`:

```js
const { test } = require("node:test");
const assert = require("node:assert");
const { clamp, esc } = require("../../src/core/format.js");

test("clamp holds a value inside the range", () => {
  assert.equal(clamp(5, 0, 10), 5);
});

test("clamp pins to the low bound", () => {
  assert.equal(clamp(-3, 0, 10), 0);
});

test("clamp pins to the high bound", () => {
  assert.equal(clamp(99, 0, 10), 10);
});

test("esc neutralises the four HTML-significant characters", () => {
  assert.equal(esc(`<a href="x">&</a>`),
    "&lt;a href=&quot;x&quot;&gt;&amp;&lt;/a&gt;");
});

test("esc renders null and undefined as empty string", () => {
  assert.equal(esc(null), "");
  assert.equal(esc(undefined), "");
});
```

- [ ] **Step 3: Run it and confirm it fails**

```bash
cd projects/sheets && npm run test:unit
```

Expected: FAIL — `Cannot find module '../../src/core/format.js'`.

- [ ] **Step 4: Write the implementation**

Create `projects/sheets/src/core/format.js`. Logic is lifted from `sheet.html:846-849`:

```js
"use strict";

/** Constrain n to [lo, hi]. */
const clamp = (n, lo, hi) => Math.max(lo, Math.min(hi, n));

/** Escape the four characters that change meaning inside HTML. */
const esc = s => String(s ?? "").replace(/[&<>"]/g, c =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

module.exports = { clamp, esc };
```

- [ ] **Step 5: Run it and confirm it passes**

```bash
cd projects/sheets && npm run test:unit
```

Expected: PASS, 5 tests.

- [ ] **Step 6: Commit**

```bash
git add projects/sheets/src/core/format.js projects/sheets/tests/core/format.test.js projects/sheets/package.json
git commit -m "feat: extract core/format with unit test harness"
```

---

## Task 3: core/dice.js and core/roll-log.js

The monolith's `die()` closes over `Math.random` (`sheet.html:898`), which is why the existing tests must stub the global. The extracted module takes an RNG instead.

**Files:**
- Create: `projects/sheets/src/core/dice.js`
- Create: `projects/sheets/src/core/roll-log.js`
- Create: `projects/sheets/tests/core/dice.test.js`
- Create: `projects/sheets/tests/core/roll-log.test.js`
- Reference: `sheet.html:895-932`

- [ ] **Step 1: Write the failing dice test**

Create `projects/sheets/tests/core/dice.test.js`:

```js
const { test } = require("node:test");
const assert = require("node:assert");
const { rollExpr, rollD20 } = require("../../src/core/dice.js");

/** Feed exact die faces. die(faces) = 1 + floor(r * faces), so r = (face-1)/faces. */
function forced(...pairs) {
  const queue = pairs.slice();
  return () => {
    const [face, faces] = queue.shift();
    return (face - 1) / faces + 1e-9;
  };
}

test("2d8+3 rolls two d8 and adds a flat 3", () => {
  const r = rollExpr("2d8+3", { rng: forced([5, 8], [7, 8]) });
  assert.equal(r.total, 15);
  assert.equal(r.dice.length, 2);
  assert.equal(r.flat, 3);
});

test("crit doubles the dice but never the flat modifier", () => {
  const r = rollExpr("2d8+3", { crit: true, rng: forced([5, 8], [7, 8], [2, 8], [1, 8]) });
  assert.equal(r.dice.length, 4);
  assert.equal(r.flat, 3);
  assert.equal(r.total, 18);
});

test("a negative term subtracts", () => {
  const r = rollExpr("1d6-2", { rng: forced([4, 6]) });
  assert.equal(r.total, 2);
});

test("a bare number parses as flat with no dice", () => {
  const r = rollExpr("+4", { rng: forced() });
  assert.equal(r.total, 4);
  assert.equal(r.dice.length, 0);
  assert.equal(r.ok, true);
});

test("an unparseable expression reports ok false", () => {
  assert.equal(rollExpr("banana", { rng: forced() }).ok, false);
});

test("a die count over 100 is refused", () => {
  const r = rollExpr("200d6", { rng: () => 0 });
  assert.equal(r.dice.length, 0);
});

test("advantage keeps the higher of two faces", () => {
  const r = rollD20(1, { rng: forced([7, 20], [15, 20]) });
  assert.equal(r.kept, 15);
  assert.deepEqual(r.faces, [7, 15]);
});

test("disadvantage keeps the lower of two faces", () => {
  const r = rollD20(-1, { rng: forced([7, 20], [15, 20]) });
  assert.equal(r.kept, 7);
});

test("a straight roll keeps its single face", () => {
  const r = rollD20(0, { rng: forced([12, 20]) });
  assert.equal(r.kept, 12);
  assert.equal(r.faces.length, 1);
});
```

- [ ] **Step 2: Run it and confirm it fails**

```bash
cd projects/sheets && node --test tests/core/dice.test.js
```

Expected: FAIL — `Cannot find module '../../src/core/dice.js'`.

- [ ] **Step 3: Write core/dice.js**

Create `projects/sheets/src/core/dice.js`. Bodies of `rollExpr` and `rollD20` are moved verbatim from `sheet.html:902-928`; the only change is that `die` becomes a local taking the injected `rng`:

```js
"use strict";

const roll1 = (faces, rng) => 1 + Math.floor(rng() * faces);

/**
 * Parse and roll an expression like "2d8+3", "1d10", "+1d4", "-2".
 * `crit` doubles the DICE only, never the flat modifier.
 */
function rollExpr(expr, { crit = false, rng = Math.random } = {}) {
  const terms = String(expr || "").replace(/\s+/g, "").match(/[+-]?[^+-]+/g) || [];
  const dice = [];
  let flat = 0, ok = false;
  for (const term of terms) {
    const sign = term.startsWith("-") ? -1 : 1;
    const body = term.replace(/^[+-]/, "");
    const m = /^(\d*)d(\d+)$/i.exec(body);
    if (m) {
      const count = (+m[1] || 1) * (crit ? 2 : 1);
      const faces = +m[2];
      if (!faces || count > 100) continue;
      for (let i = 0; i < count; i++) dice.push({ faces, value: roll1(faces, rng), sign });
      ok = true;
    } else if (/^\d+$/.test(body)) { flat += sign * +body; ok = true; }
  }
  const total = dice.reduce((s, x) => s + x.sign * x.value, 0) + flat;
  return { total, dice, flat, ok };
}

/** d20 with advantage/disadvantage; both faces are kept so the receipt can show
    which was discarded. eff: 1 advantage, -1 disadvantage, 0 straight. */
function rollD20(eff, { rng = Math.random } = {}) {
  const faces = eff === 0 ? [roll1(20, rng)] : [roll1(20, rng), roll1(20, rng)];
  const kept = eff === 1 ? Math.max(...faces) : eff === -1 ? Math.min(...faces) : faces[0];
  return { faces, kept, eff };
}

module.exports = { rollExpr, rollD20 };
```

- [ ] **Step 4: Run it and confirm it passes**

```bash
cd projects/sheets && node --test tests/core/dice.test.js
```

Expected: PASS, 9 tests.

- [ ] **Step 5: Write the failing roll-log test**

Create `projects/sheets/tests/core/roll-log.test.js`:

```js
const { test } = require("node:test");
const assert = require("node:assert");
const { pushRoll } = require("../../src/core/roll-log.js");

test("a new entry goes to the front", () => {
  assert.deepEqual(pushRoll(["b"], "a"), ["a", "b"]);
});

test("the log is capped at twelve entries", () => {
  const twelve = Array.from({ length: 12 }, (_, i) => i);
  assert.equal(pushRoll(twelve, "new").length, 12);
});

test("the oldest entry is the one dropped", () => {
  const twelve = Array.from({ length: 12 }, (_, i) => i);
  const out = pushRoll(twelve, "new");
  assert.equal(out[0], "new");
  assert.equal(out.at(-1), 10);
});

test("a missing log is treated as empty", () => {
  assert.deepEqual(pushRoll(undefined, "a"), ["a"]);
});

test("the input array is not mutated", () => {
  const before = ["b"];
  pushRoll(before, "a");
  assert.deepEqual(before, ["b"]);
});
```

- [ ] **Step 6: Run it and confirm it fails**

```bash
cd projects/sheets && node --test tests/core/roll-log.test.js
```

Expected: FAIL — module not found.

- [ ] **Step 7: Write core/roll-log.js**

Create `projects/sheets/src/core/roll-log.js`. Logic from `sheet.html:930-932`, made pure — it returns a new array instead of assigning to `S.rolls`:

```js
"use strict";

const LIMIT = 12;

/** Return a new log with `entry` at the front, capped at LIMIT. */
const pushRoll = (rolls, entry, limit = LIMIT) =>
  [entry, ...(rolls || [])].slice(0, limit);

module.exports = { pushRoll, LIMIT };
```

- [ ] **Step 8: Run it and confirm it passes**

```bash
cd projects/sheets && node --test tests/core/roll-log.test.js
```

Expected: PASS, 5 tests.

- [ ] **Step 9: Commit**

```bash
git add projects/sheets/src/core/dice.js projects/sheets/src/core/roll-log.js projects/sheets/tests/core/
git commit -m "feat: extract core/dice with injected RNG and core/roll-log"
```

---

## Task 4: core/hp.js and core/spells.js

**Files:**
- Create: `projects/sheets/src/core/hp.js`
- Create: `projects/sheets/src/core/spells.js`
- Create: `projects/sheets/tests/core/hp.test.js`
- Create: `projects/sheets/tests/core/spells.test.js`
- Reference: `sheet.html:807-809`, `sheet.html:861-866`

- [ ] **Step 1: Write the failing hp test**

Create `projects/sheets/tests/core/hp.test.js`:

```js
const { test } = require("node:test");
const assert = require("node:assert");
const { effectiveHpMax } = require("../../src/core/hp.js");

test("with no bonus the base maximum is returned", () => {
  assert.equal(effectiveHpMax(128, 0), 128);
});

test("Aid and Heroes' Feast raise the maximum itself", () => {
  assert.equal(effectiveHpMax(128, 10), 138);
});

test("a missing bonus counts as zero", () => {
  assert.equal(effectiveHpMax(128, undefined), 128);
});

test("a negative bonus lowers the maximum", () => {
  assert.equal(effectiveHpMax(128, -8), 120);
});
```

- [ ] **Step 2: Run it and confirm it fails**

```bash
cd projects/sheets && node --test tests/core/hp.test.js
```

Expected: FAIL — module not found.

- [ ] **Step 3: Write core/hp.js**

Create `projects/sheets/src/core/hp.js`. From `sheet.html:809`, with `D` and `S` becoming arguments:

```js
"use strict";

/** Effective maximum HP. Aid and Heroes' Feast raise the maximum itself, so it
    is state rather than a constant — everything that clamps or refills reads this. */
const effectiveHpMax = (baseMax, maxBonus) => baseMax + (maxBonus || 0);

module.exports = { effectiveHpMax };
```

- [ ] **Step 4: Run it and confirm it passes**

```bash
cd projects/sheets && node --test tests/core/hp.test.js
```

Expected: PASS, 4 tests.

- [ ] **Step 5: Read the monolith's preparedCount before porting it**

```bash
sed -n '861,866p' projects/sheets/sheet.html
```

Write the test in Step 6 to match the behavior you just read — the counting rule (which spells count as prepared, and whether always-prepared spells are excluded) must be preserved exactly, not reinvented.

- [ ] **Step 6: Write the failing spells test**

Create `projects/sheets/tests/core/spells.test.js`. Replace the fixture spells with shapes taken from `toki.data.json`'s spell entries, and the expected counts with what the monolith produces:

```js
const { test } = require("node:test");
const assert = require("node:assert");
const { preparedCount } = require("../../src/core/spells.js");

const SPELLS = [
  { name: "Bless", level: 1, alwaysPrepared: false },
  { name: "Cure Wounds", level: 1, alwaysPrepared: false },
  { name: "Divine Smite", level: 1, alwaysPrepared: true },
  { name: "Shield of Faith", level: 1, alwaysPrepared: false },
];

test("counts only spells toggled prepared", () => {
  assert.equal(preparedCount({ Bless: true, "Cure Wounds": true }, SPELLS), 2);
});

test("an untoggled spell is not counted", () => {
  assert.equal(preparedCount({ Bless: true, "Cure Wounds": false }, SPELLS), 1);
});

test("always-prepared spells do not consume the prepared budget", () => {
  assert.equal(preparedCount({ "Divine Smite": true }, SPELLS), 0);
});

test("an empty selection counts zero", () => {
  assert.equal(preparedCount({}, SPELLS), 0);
});
```

- [ ] **Step 7: Run it and confirm it fails**

```bash
cd projects/sheets && node --test tests/core/spells.test.js
```

Expected: FAIL — module not found.

- [ ] **Step 8: Write core/spells.js**

Create `projects/sheets/src/core/spells.js` by moving the body of `preparedCount` from `sheet.html:861-866`, replacing its references to the globals `S` and `DATA` with the `prepared` and `spells` parameters:

```js
"use strict";

/** How many of the character's prepared-spell slots are currently spent.
    Always-prepared spells never count against the budget. */
function preparedCount(prepared, spells) {
  return spells.filter(s => !s.alwaysPrepared && prepared[s.name]).length;
}

module.exports = { preparedCount };
```

If Step 5 showed the monolith counting differently — for instance keying on spell id rather than name — use that rule and update the test fixtures to match.

- [ ] **Step 9: Run it and confirm it passes**

```bash
cd projects/sheets && node --test tests/core/spells.test.js
```

Expected: PASS, 4 tests.

- [ ] **Step 10: Commit**

```bash
git add projects/sheets/src/core/hp.js projects/sheets/src/core/spells.js projects/sheets/tests/core/hp.test.js projects/sheets/tests/core/spells.test.js
git commit -m "feat: extract core/hp and core/spells"
```

---

## Task 5: core/weapons.js, core/damage.js, core/attack.js

These three move together because `rollAttack` composes the other two (`sheet.html:936`).

**Files:**
- Create: `projects/sheets/src/core/weapons.js`, `damage.js`, `attack.js`
- Create: `projects/sheets/tests/core/weapons.test.js`, `damage.test.js`, `attack.test.js`
- Reference: `sheet.html:867-894` (weapons), `955-992` (outcome), `934-953` (rollAttack)

- [ ] **Step 1: Read all three source ranges**

```bash
sed -n '867,894p;934,992p' projects/sheets/sheet.html
```

Note every global each function reads — `DATA`, `S`, `D`, `RESOURCES`. Each becomes an explicit parameter.

- [ ] **Step 2: Write the failing weapons test**

Create `projects/sheets/tests/core/weapons.test.js`. Build the `data` and `state` fixtures from the shapes you read in Step 1, and assert on the fields `renderTurn` and `rollAttack` actually consume — at minimum `name`, `toHit`, and `crit`:

```js
const { test } = require("node:test");
const assert = require("node:assert");
const { weapons } = require("../../src/core/weapons.js");

const DATA = require("../fixtures/toki.data.json");

test("every derived weapon carries the fields the roller needs", () => {
  const list = weapons(DATA, { calc: {} });
  assert.ok(list.length > 0);
  for (const w of list) {
    assert.equal(typeof w.name, "string");
    assert.equal(typeof w.toHit, "number");
    assert.equal(typeof w.crit, "number");
  }
});

test("the crit threshold defaults to 20", () => {
  const list = weapons(DATA, { calc: {} });
  assert.ok(list.every(w => w.crit >= 19 && w.crit <= 20));
});
```

- [ ] **Step 3: Create the shared test fixture**

```bash
mkdir -p projects/sheets/tests/fixtures
cp projects/sheets/toki.data.json projects/sheets/tests/fixtures/toki.data.json
```

- [ ] **Step 4: Run it and confirm it fails**

```bash
cd projects/sheets && node --test tests/core/weapons.test.js
```

Expected: FAIL — module not found.

- [ ] **Step 5: Write core/weapons.js**

Create `projects/sheets/src/core/weapons.js` by moving `sheet.html:871-894` into an exported `weapons(data, state)`. Replace `DATA` with `data` and `S` with `state`. Export nothing else.

- [ ] **Step 6: Run it and confirm it passes**

```bash
cd projects/sheets && node --test tests/core/weapons.test.js
```

Expected: PASS, 2 tests.

- [ ] **Step 7: Write the failing damage test**

Create `projects/sheets/tests/core/damage.test.js`. `outcome(weapon, ctx)` returns `{ eff, rows }` where each row has `src`, `dice`, `flat`, and `doubles` (read at `sheet.html:946-948`):

```js
const { test } = require("node:test");
const assert = require("node:assert");
const { outcome } = require("../../src/core/damage.js");

const WEAPON = { name: "Longsword", toHit: 11, crit: 20, dice: "1d10", flat: 5 };

test("returns an advantage-effect value and damage rows", () => {
  const o = outcome(WEAPON, { ac: 16, adv: 0 });
  assert.equal(typeof o.eff, "number");
  assert.ok(Array.isArray(o.rows));
});

test("every row declares whether it doubles on a crit", () => {
  const o = outcome(WEAPON, { ac: 16, adv: 0 });
  for (const r of o.rows) {
    assert.equal(typeof r.src, "string");
    assert.equal(typeof r.doubles, "boolean");
  }
});

test("advantage in the context produces eff 1", () => {
  assert.equal(outcome(WEAPON, { ac: 16, adv: 1 }).eff, 1);
});
```

- [ ] **Step 8: Run it and confirm it fails**

```bash
cd projects/sheets && node --test tests/core/damage.test.js
```

Expected: FAIL — module not found.

- [ ] **Step 9: Write core/damage.js**

Move `sheet.html:956-992` into an exported `outcome(weapon, ctx)`. Every global it reads (`S`, `DATA`, `RESOURCES`) becomes a field on `ctx`. Adjust the test fixtures in Step 7 to supply exactly those fields.

- [ ] **Step 10: Run it and confirm it passes**

```bash
cd projects/sheets && node --test tests/core/damage.test.js
```

Expected: PASS, 3 tests.

- [ ] **Step 11: Write the failing attack test**

Create `projects/sheets/tests/core/attack.test.js`:

```js
const { test } = require("node:test");
const assert = require("node:assert");
const { rollAttack } = require("../../src/core/attack.js");

const WEAPON = { name: "Longsword", toHit: 11, crit: 20 };
const CTX = { ac: 16, adv: 0 };

const deps = (d20, ...exprTotals) => ({
  rollD20: () => ({ faces: [d20], kept: d20, eff: 0 }),
  rollExpr: () => ({ total: exprTotals.shift() ?? 0, dice: [], flat: 0, ok: true }),
  outcome: () => ({ eff: 0, rows: [{ src: "Longsword", dice: "1d10", flat: 5, doubles: true }] }),
});

test("a natural 1 is a fumble and deals no damage", () => {
  const r = rollAttack(WEAPON, CTX, "", deps(1, 9));
  assert.equal(r.fumble, true);
  assert.equal(r.hit, false);
  assert.equal(r.damage, 0);
});

test("meeting the target AC is a hit", () => {
  const r = rollAttack(WEAPON, CTX, "", deps(5, 9));
  assert.equal(r.total, 16);
  assert.equal(r.hit, true);
});

test("falling short of the target AC misses", () => {
  const r = rollAttack(WEAPON, CTX, "", deps(3, 9));
  assert.equal(r.hit, false);
  assert.equal(r.damage, 0);
});

test("rolling the crit threshold hits regardless of AC", () => {
  const r = rollAttack(WEAPON, { ac: 99, adv: 0 }, "", deps(20, 9));
  assert.equal(r.crit, true);
  assert.equal(r.hit, true);
});

test("damage is the sum of every rolled row", () => {
  const r = rollAttack(WEAPON, CTX, "", deps(15, 9));
  assert.equal(r.damage, 9);
});
```

- [ ] **Step 12: Run it and confirm it fails**

```bash
cd projects/sheets && node --test tests/core/attack.test.js
```

Expected: FAIL — module not found.

- [ ] **Step 13: Write core/attack.js**

Move `sheet.html:935-953` into `rollAttack(weapon, ctx, extra, deps)`. The `deps` object supplies `rollExpr`, `rollD20`, and `outcome` so the function stays pure and testable. Preserve every returned field exactly: `kind`, `weapon`, `d20`, `bonus`, `toHitExtra`, `total`, `crit`, `fumble`, `hit`, `ac`, `rows`, `damage`, `extra`.

- [ ] **Step 14: Run it and confirm it passes**

```bash
cd projects/sheets && node --test tests/core/attack.test.js
```

Expected: PASS, 5 tests.

- [ ] **Step 15: Commit**

```bash
git add projects/sheets/src/core/ projects/sheets/tests/core/ projects/sheets/tests/fixtures/
git commit -m "feat: extract core/weapons, core/damage and core/attack"
```

---

## Task 6: core/planner.js

**Files:**
- Create: `projects/sheets/src/core/planner.js`
- Create: `projects/sheets/tests/core/planner.test.js`
- Reference: `sheet.html:993-1054`

- [ ] **Step 1: Read the source range**

```bash
sed -n '993,1054p' projects/sheets/sheet.html
```

Three functions: `laneOptions(lane)`, `resLeftFor(a)`, `forecast()`. Note every global read — `DATA`, `S`, `RESOURCES`.

- [ ] **Step 2: Write the failing test**

Create `projects/sheets/tests/core/planner.test.js`. Set the fixtures from what Step 1 showed:

```js
const { test } = require("node:test");
const assert = require("node:assert");
const { laneOptions, resLeftFor, forecast } = require("../../src/core/planner.js");

const DATA = require("../fixtures/toki.data.json");
const RESOURCES = [
  { id: "cd", label: "Channel Divinity", max: 3, reset: "Long Rest" },
  { id: "smite", label: "Free Smite", max: 1, reset: "Long Rest" },
];
const STATE = { res: { cd: 2, smite: 1 }, slots: {}, laneMod: {}, plan: {} };

test("laneOptions returns the actions available in a lane", () => {
  const opts = laneOptions("action", { data: DATA, state: STATE });
  assert.ok(Array.isArray(opts));
});

test("resLeftFor reports the remaining uses of a resource", () => {
  assert.equal(resLeftFor({ res: "cd" }, { state: STATE, resources: RESOURCES }), 2);
});

test("resLeftFor reports null for an action that costs no resource", () => {
  assert.equal(resLeftFor({}, { state: STATE, resources: RESOURCES }), null);
});

test("forecast reports one entry per tracked resource", () => {
  const f = forecast({ data: DATA, state: STATE, resources: RESOURCES });
  assert.equal(f.length, RESOURCES.length);
});
```

- [ ] **Step 3: Run it and confirm it fails**

```bash
cd projects/sheets && node --test tests/core/planner.test.js
```

Expected: FAIL — module not found.

- [ ] **Step 4: Write core/planner.js**

Move the three functions from `sheet.html:1023-1054` plus the option tables at `993-1022`. Signatures:

```js
laneOptions(laneId, { data, state })
resLeftFor(action, { state, resources })
forecast({ data, state, resources })
```

Adjust the Step 2 fixtures to whatever these actually return; the assertions describe shape, not invented values.

- [ ] **Step 5: Run it and confirm it passes**

```bash
cd projects/sheets && node --test tests/core/planner.test.js
```

Expected: PASS, 4 tests.

- [ ] **Step 6: Commit**

```bash
git add projects/sheets/src/core/planner.js projects/sheets/tests/core/planner.test.js
git commit -m "feat: extract core/planner"
```

---

## Task 7: core/state.js — namespaced storage, versioning, visible save failure

This task fixes three defects identified in the spec: the origin-shared key collision, the missing schema version, and the silently swallowed save error (`sheet.html:840`).

**Files:**
- Create: `projects/sheets/src/core/state.js`
- Create: `projects/sheets/tests/core/state.test.js`
- Reference: `sheet.html:784-842`

- [ ] **Step 1: Write the failing test**

Create `projects/sheets/tests/core/state.test.js`:

```js
const { test } = require("node:test");
const assert = require("node:assert");
const { createStore, SCHEMA_VERSION } = require("../../src/core/state.js");

/** Minimal in-memory Storage stand-in. */
function memStorage(initial = {}) {
  const map = new Map(Object.entries(initial));
  return {
    getItem: k => (map.has(k) ? map.get(k) : null),
    setItem: (k, v) => map.set(k, v),
    _map: map,
  };
}

const blank = () => ({ hp: 100, rolls: [], res: {} });

test("the storage key is namespaced by campaign and character", () => {
  const storage = memStorage();
  const store = createStore({ campaign: "frostmarch", character: "toki", storage, blank });
  store.set(s => { s.hp = 42; });
  assert.ok(storage._map.has("sheet:v1:frostmarch:toki"));
});

test("two characters in one origin cannot see each other's state", () => {
  const storage = memStorage();
  const toki = createStore({ campaign: "frostmarch", character: "toki", storage, blank });
  const bjorn = createStore({ campaign: "frostmarch", character: "bjorn", storage, blank });

  toki.set(s => { s.hp = 42; });
  bjorn.set(s => { s.hp = 7; });

  const reloadedToki = createStore({ campaign: "frostmarch", character: "toki", storage, blank });
  assert.equal(reloadedToki.state.hp, 42);
});

test("saved state is merged onto the blank shape", () => {
  const storage = memStorage({
    "sheet:v1:frostmarch:toki":
      JSON.stringify({ schemaVersion: SCHEMA_VERSION, hp: 55 }),
  });
  const store = createStore({ campaign: "frostmarch", character: "toki", storage, blank });
  assert.equal(store.state.hp, 55);
  assert.deepEqual(store.state.rolls, []);
});

test("corrupt stored JSON falls back to blank instead of throwing", () => {
  const storage = memStorage({ "sheet:v1:frostmarch:toki": "{not json" });
  const store = createStore({ campaign: "frostmarch", character: "toki", storage, blank });
  assert.equal(store.state.hp, 100);
});

test("a stale schema version resets state and reports it", () => {
  const storage = memStorage({
    "sheet:v1:frostmarch:toki": JSON.stringify({ schemaVersion: 0, hp: 55 }),
  });
  const events = [];
  const store = createStore({
    campaign: "frostmarch", character: "toki", storage, blank,
    onReset: r => events.push(r),
  });
  assert.equal(store.state.hp, 100);
  assert.equal(events.length, 1);
});

test("a failed write reports instead of failing silently", () => {
  const storage = {
    getItem: () => null,
    setItem: () => { throw new Error("QuotaExceededError"); },
  };
  const errors = [];
  const store = createStore({
    campaign: "frostmarch", character: "toki", storage, blank,
    onError: e => errors.push(e),
  });
  store.set(s => { s.hp = 1; });
  assert.equal(errors.length, 1);
  assert.equal(store.state.hp, 1);
});
```

- [ ] **Step 2: Run it and confirm it fails**

```bash
cd projects/sheets && node --test tests/core/state.test.js
```

Expected: FAIL — module not found.

- [ ] **Step 3: Write core/state.js**

Create `projects/sheets/src/core/state.js`:

```js
"use strict";

const SCHEMA_VERSION = 1;

/**
 * Persistent character state.
 *
 * The key is namespaced by campaign and character because GitHub Pages project
 * sites share one origin, and localStorage is scoped to origin rather than path.
 * Without namespacing, opening one character would clobber another's HP, slots
 * and roll log. The ids are constructor arguments, never module constants, so
 * the collision is structurally impossible.
 */
function createStore({ campaign, character, storage, blank,
                       onError = () => {}, onReset = () => {} }) {
  const key = `sheet:v${SCHEMA_VERSION}:${campaign}:${character}`;

  let state;
  try {
    const saved = JSON.parse(storage.getItem(key) || "null");
    if (!saved) {
      state = blank();
    } else if (saved.schemaVersion !== SCHEMA_VERSION) {
      state = blank();
      onReset({ from: saved.schemaVersion, to: SCHEMA_VERSION });
    } else {
      state = merge(blank(), saved);
    }
  } catch {
    state = blank();
  }

  function save() {
    try {
      storage.setItem(key, JSON.stringify({ ...state, schemaVersion: SCHEMA_VERSION }));
    } catch (e) {
      // Never silent: the player must know their session is not being persisted.
      onError(e);
    }
  }

  function set(fn) { fn(state); save(); }

  return { get state() { return state; }, set, save, key };
}

/** Shallow-merge saved values onto the blank shape, one level into objects so a
    new field added to blank() appears even in state saved before it existed. */
function merge(base, saved) {
  const out = { ...base, ...saved };
  for (const k of Object.keys(base)) {
    if (base[k] && typeof base[k] === "object" && !Array.isArray(base[k])) {
      out[k] = { ...base[k], ...(saved[k] || {}) };
    }
  }
  return out;
}

module.exports = { createStore, SCHEMA_VERSION };
```

- [ ] **Step 4: Run it and confirm it passes**

```bash
cd projects/sheets && node --test tests/core/state.test.js
```

Expected: PASS, 6 tests.

- [ ] **Step 5: Commit**

```bash
git add projects/sheets/src/core/state.js projects/sheets/tests/core/state.test.js
git commit -m "feat: extract core/state with namespaced keys, versioning and visible save failure

Fixes the origin-shared localStorage collision that would let one character
overwrite another's tracked HP, and surfaces write failures that the monolith
swallowed at sheet.html:840."
```

---

## Task 8: ui/dom.js and the base classes

These do not exist in the monolith. They are what a character subclasses, so their contract is tested directly.

**Files:**
- Create: `projects/sheets/src/ui/dom.js`, `Panel.js`, `Tab.js`, `Tracker.js`, `Lane.js`
- Create: `projects/sheets/tests/ui/base.test.js`

- [ ] **Step 1: Write the failing contract test**

Create `projects/sheets/tests/ui/base.test.js`:

```js
const { test } = require("node:test");
const assert = require("node:assert");
const { JSDOM } = require("jsdom");

const dom = new JSDOM("<!doctype html><body></body>");
global.document = dom.window.document;

const { Panel } = require("../../src/ui/Panel.js");
const { Tab } = require("../../src/ui/Tab.js");

test("a Panel renders a header and a body", () => {
  const node = new Panel({ title: "Resources" }).render();
  assert.equal(node.querySelector(".panel-header").textContent, "Resources");
  assert.ok(node.querySelector(".panel-body"));
});

test("a subclass overriding body keeps the inherited header", () => {
  class OathPanel extends Panel {
    body() { const n = document.createElement("div"); n.textContent = "oath"; return n; }
  }
  const node = new OathPanel({ title: "Oath" }).render();
  assert.equal(node.querySelector(".panel-header").textContent, "Oath");
  assert.equal(node.querySelector(".panel-body").textContent, "oath");
});

test("a subclass can extend the inherited header via super", () => {
  class Badged extends Panel {
    header() {
      const n = super.header();
      n.textContent += " *";
      return n;
    }
  }
  assert.equal(new Badged({ title: "Oath" }).render()
    .querySelector(".panel-header").textContent, "Oath *");
});

test("a Tab reports its id and title", () => {
  const t = new Tab({ id: "turn", title: "Turn" });
  assert.equal(t.id, "turn");
  assert.equal(t.title(), "Turn");
});

test("a throwing Tab renders a fallback rather than propagating", () => {
  class Broken extends Tab {
    body() { throw new Error("boom"); }
  }
  const node = new Broken({ id: "x", title: "X" }).render();
  assert.ok(node.querySelector(".tab-error"));
  assert.match(node.textContent, /boom/);
});
```

- [ ] **Step 2: Run it and confirm it fails**

```bash
cd projects/sheets && node --test tests/ui/base.test.js
```

Expected: FAIL — module not found.

- [ ] **Step 3: Write ui/dom.js**

Create `projects/sheets/src/ui/dom.js`, moved from `sheet.html:844-845`:

```js
"use strict";

/** The single DOM primitive. Nothing else in ui/ calls createElement directly. */
const el = (t, c, h) => {
  const n = document.createElement(t);
  if (c) n.className = c;
  if (h != null) n.innerHTML = h;
  return n;
};

module.exports = { el };
```

- [ ] **Step 4: Write ui/Panel.js**

```js
"use strict";
const { el } = require("./dom.js");

/**
 * A titled box. Characters subclass this and override `body`, or override
 * `header` and call `super.header()` to extend it.
 *
 * Overridable: header(), body(), className()
 */
class Panel {
  constructor(ctx = {}) { this.ctx = ctx; }

  className() { return "panel"; }

  header() { return el("div", "panel-header", this.ctx.title || ""); }

  body() { return el("div", "panel-body"); }

  render() {
    const root = el("section", this.className());
    root.append(this.header());
    const body = this.body();
    body.classList.add("panel-body");
    root.append(body);
    return root;
  }
}

module.exports = { Panel };
```

- [ ] **Step 5: Write ui/Tab.js**

```js
"use strict";
const { el } = require("./dom.js");

/**
 * One top-level tab. `render` wraps `body` in an error boundary so a throw in
 * one tab cannot take down the rail or the other tabs.
 *
 * Overridable: title(), body(), className()
 */
class Tab {
  constructor(ctx = {}) { this.ctx = ctx; this.id = ctx.id; }

  className() { return "tab-view"; }

  title() { return this.ctx.title || this.id; }

  body() { return el("div"); }

  render() {
    const root = el("section", this.className());
    try {
      root.append(this.body());
    } catch (e) {
      root.append(el("div", "tab-error",
        `This tab failed to render: ${e.message}`));
    }
    return root;
  }
}

module.exports = { Tab };
```

- [ ] **Step 6: Write ui/Tracker.js and ui/Lane.js**

`Tracker` is a `Panel` subclass rendering a resource meter; `Lane` is a `Panel` subclass rendering one action-economy lane. Port their markup from `renderRail` (`sheet.html:1256-1430`) and `renderTurn` (`sheet.html:1432-1633`) respectively, keeping every class name identical — the parity suites match on those class names.

- [ ] **Step 7: Run it and confirm it passes**

```bash
cd projects/sheets && node --test tests/ui/base.test.js
```

Expected: PASS, 5 tests.

- [ ] **Step 8: Commit**

```bash
git add projects/sheets/src/ui/ projects/sheets/tests/ui/
git commit -m "feat: add ui/dom and the Panel, Tab, Tracker and Lane base classes"
```

---

## Task 9: Port the four render sections

Mechanical but large. Class names and DOM structure must be preserved exactly — the parity suites in Task 12 assert on them.

**Files:**
- Create: `projects/sheets/src/ui/rail/` (4 files), `turn/` (7), `playbook/` (3), `sheet/` (6), `codex/` (2)
- Reference: `sheet.html:1255-2143`

- [ ] **Step 1: Port the rail**

Move `sheet.html:1256-1430` into `src/ui/rail/`: `index.js` (composition), `hp-block.js`, `resource-list.js`, `rest-controls.js`. `resource-list.js` renders `Tracker` instances.

- [ ] **Step 2: Commit the rail**

```bash
git add projects/sheets/src/ui/rail/
git commit -m "refactor: extract the rail into ui/rail"
```

- [ ] **Step 3: Port the turn planner**

Move `sheet.html:1432-1764` into `src/ui/turn/`: `index.js`, `lane-card.js`, `roll-card.js`, `face-chips.js`, `commit-bar.js`, `cost-line.js`, `forecast-panel.js`. The helpers map one-to-one: `faceChips` (1634), `rollCard` (1640), `poleStrike` (1682), `rollableExpr` (1691), `rollLane` (1705), `commitRound` (1730), `costLine` (1746).

- [ ] **Step 4: Commit the turn planner**

```bash
git add projects/sheets/src/ui/turn/
git commit -m "refactor: extract the turn planner into ui/turn"
```

- [ ] **Step 5: Port the playbook**

Move `sheet.html:1766-1871` into `src/ui/playbook/`: `index.js`, `tokens.js` (1806), `load-play.js` (1845).

- [ ] **Step 6: Port the sheet tab**

Move `sheet.html:1873-2064` into `src/ui/sheet/`: `index.js`, `ability-block.js`, `skill-table.js`, `action-list.js`, `spell-list.js`, `item-block.js` (2049).

- [ ] **Step 7: Port the codex tab, dropping Notion**

Move `sheet.html:2066-2143` into `src/ui/codex/`: `index.js` and `text-block.js`. Keep appearance, personality, ideals, bonds, flaws, backstory and ties — all present in the export. Do **not** port `notionLines` (2134), the three live panels, or the arc banner.

- [ ] **Step 8: Commit the remaining tabs**

```bash
git add projects/sheets/src/ui/playbook/ projects/sheets/src/ui/sheet/ projects/sheets/src/ui/codex/
git commit -m "refactor: extract playbook, sheet and codex tabs; drop the Notion panels"
```

---

## Task 10: Toki's character folder

**Files:**
- Create: `projects/sheets/chars/<campaign>/toki/character.json`, `plays.js`, `layout.js`
- Move: `toki.data.json` → `chars/<campaign>/toki/data.json`
- Move: `DEVLOG.md` → `chars/<campaign>/toki/DEVLOG.md`

- [ ] **Step 1: Create the folder using the real campaign slug**

Substitute the campaign slug from the Required Input section:

```bash
cd /home/ideans/data/projects/dnd/projects/sheets
mkdir -p chars/<campaign>/toki
git mv toki.data.json chars/<campaign>/toki/data.json
git mv DEVLOG.md chars/<campaign>/toki/DEVLOG.md
```

- [ ] **Step 2: Write character.json**

Create `chars/<campaign>/toki/character.json`:

```json
{
  "id": "toki",
  "name": "Toki Ironlung",
  "player": "Ian",
  "campaign": "<campaign>",
  "notionPageId": "",
  "workshop": "characters/active/toki-ironlung"
}
```

`notionPageId` is filled by the Notion sync in Plan 2; it is empty here because nothing in Plan 1 reads it.

- [ ] **Step 3: Extract the playbook data**

Move the A–G play definitions from `sheet.html:641-783` into `chars/<campaign>/toki/plays.js` as a single exported array:

```js
"use strict";
module.exports = { PLAYS: [ /* moved verbatim from sheet.html:641-783 */ ] };
```

- [ ] **Step 4: Write layout.js**

Create `chars/<campaign>/toki/layout.js`. It declares Toki's tab set, his resource list (moved from `sheet.html:790-801`), and his lanes:

```js
"use strict";
const { PLAYS } = require("./plays.js");

const RESOURCES = [ /* moved verbatim from sheet.html:790-801 */ ];

/** The starting state shape for this character. Moved from sheet.html:811-826,
    with DATA and RESOURCES becoming arguments instead of globals. */
function blank(data) {
  return {
    /* moved verbatim from the body of blank() at sheet.html:811-826,
       reading `data` and RESOURCES rather than the globals DATA and RESOURCES */
  };
}

module.exports = {
  tabs: ["turn", "playbook", "sheet", "codex"],
  resources: RESOURCES,
  plays: PLAYS,
  lanes: ["action", "bonus", "reaction", "movement"],
  blank,
};
```

`blank` lives in the layout rather than in `core/state.js` because the starting
shape is character-specific — it is seeded from that character's resource list.
`core/state.js` receives it as the `blank` argument (Task 7).

- [ ] **Step 5: Commit**

```bash
git add -A projects/sheets/chars
git commit -m "refactor: move Toki into a character folder"
```

---

## Task 11: App shell and the per-character build

**Files:**
- Create: `projects/sheets/src/app/main.js`, `shell.js`, `events.js`
- Modify: `projects/sheets/build.py` → `projects/sheets/tools/build.py`
- Modify: `projects/sheets/build_fonts.py` → `projects/sheets/tools/build_fonts.py`
- Modify: `projects/sheets/package.json`

- [ ] **Step 1: Write the app shell**

Move `sheet.html:2144-2181` into `src/app/shell.js` and `2182-2268` into `src/app/events.js`. `src/app/main.js` wires them:

```js
"use strict";
const { createStore } = require("../core/state.js");
const { createShell } = require("./shell.js");
const { bindEvents } = require("./events.js");

const DATA = require("__DATA_MODULE__");
const LAYOUT = require("__LAYOUT_MODULE__");
const { campaign, id: character } = require("__CHARACTER_MODULE__");

const store = createStore({
  campaign, character, storage: window.localStorage,
  blank: () => LAYOUT.blank(DATA),
  onError: () => document.body.classList.add("save-failed"),
  onReset: () => document.body.classList.add("state-reset"),
});

const shell = createShell({ data: DATA, layout: LAYOUT, store,
  root: document.getElementById("app") });
bindEvents({ shell, store });
shell.render();
```

esbuild resolves the three `__*_MODULE__` paths via `--define` aliases set per character in Step 3.

- [ ] **Step 2: Move the Python tools**

```bash
cd /home/ideans/data/projects/dnd/projects/sheets
mkdir -p tools
git mv build.py tools/build.py
git mv build_fonts.py tools/build_fonts.py
git mv distill.py tools/distill.py
```

- [ ] **Step 3: Rewrite tools/build.py for per-character output**

`tools/build.py --char <campaign>/<char>` must:

1. Run esbuild, bundling `src/app/main.js` with that character's `data.json`, `layout.js`, and `character.json` aliased in, to `dist/<campaign>/<char>/app.js`.
2. Emit `dist/<campaign>/<char>/index.html` — the template shell with `<link>` to the shared fonts and `<script src="app.js">`. No inline script.
3. Emit `manifest.json` with `name` from `character.json`, and `start_url` and `scope` both `/dnd/<campaign>/<char>/`.
4. Copy `sw.js` with `BUILD_ID` replaced by `git rev-parse --short HEAD` and the cache name set to `sheet-<campaign>-<char>-<BUILD_ID>`.

- [ ] **Step 4: Change build_fonts.py to emit real woff2**

`tools/build_fonts.py` currently base64-inlines every face into `fonts.css`. Change it to write `dist/_fonts/*.woff2` and a `fonts.css` referencing them by relative URL. The single-file constraint existed only for Artifact publishing; the files are ~25% smaller unencoded and the service worker caches them once across all characters.

- [ ] **Step 5: Update the npm scripts**

```json
  "scripts": {
    "distill": "python3 tools/distill.py",
    "build": "python3 tools/build.py --char",
    "build:all": "python3 tools/build.py --all",
    "test:parity": "node tests/run.js",
    "test:unit": "node --test tests/core/ tests/ui/",
    "test": "npm run test:unit && npm run test:parity"
  },
```

- [ ] **Step 6: Build Toki and confirm the output exists**

```bash
cd projects/sheets && npm run build -- <campaign>/toki
ls dist/<campaign>/toki/
```

Expected: `index.html`, `app.js`, `sw.js`, `manifest.json`.

- [ ] **Step 7: Commit**

```bash
git add -A projects/sheets
git commit -m "feat: per-character build with an external bundle and real woff2 fonts"
```

---

## Task 12: Parity — the old suites must pass against the new page

The proof that the decomposition changed nothing a player can see.

**Files:**
- Modify: `projects/sheets/tests/run.js`
- Modify: `projects/sheets/tests/content.test.js`
- Modify: `projects/sheets/tests/shell.test.js`, `dice.test.js`, `hp.test.js`

- [ ] **Step 1: Point the parity runner at the new dist**

In `tests/run.js`, replace lines 8-12:

```js
const dist = path.join(__dirname, "..", "dist", "toki.html");
if (!existsSync(dist)) {
  console.error("dist/toki.html not found — run `npm run build` first.");
  process.exit(1);
}
```

with:

```js
const CHAR = process.env.PARITY_CHAR || "<campaign>/toki";
const dist = path.join(__dirname, "..", "dist", CHAR, "index.html");
if (!existsSync(dist)) {
  console.error(`${dist} not found — run \`npm run build -- ${CHAR}\` first.`);
  process.exit(1);
}
```

- [ ] **Step 2: Collapse the Notion mode matrix**

In `tests/run.js`, delete the `MODES` array (lines 14-17) and replace the `runs` array with:

```js
const runs = [
  ["shell.test.js", []], ["dice.test.js", []], ["hp.test.js", []],
  ["content.test.js", []],
];
```

- [ ] **Step 3: Strip Notion assertions from content.test.js**

Remove every check that asserts on connector state, panel freshness, or the arc banner, along with the `process.argv[3]` mode plumbing. Keep every check common to all 12 modes — those are the ~44 non-Notion checks the baseline recorded.

- [ ] **Step 4: Load the external bundle in the jsdom harness**

Each suite currently evals inline `<script>` tags (`dice.test.js:17-20`). The built page has none. In all four suites, add `path` to the requires at the top:

```js
const path = require("path");
```

then replace that loop with:

```js
const appJs = fs.readFileSync(path.join(path.dirname(process.argv[2]), "app.js"), "utf8");
try { window.eval(appJs); }
catch (e) { errors.push("bundle threw: " + e.message); }
```

Also delete the `window.claude` stub (`dice.test.js:14-15`) — nothing reads it now.

- [ ] **Step 5: Run the parity suite**

```bash
cd projects/sheets && npm run build -- <campaign>/toki && npm run test:parity
```

Expected: 4 suites pass. `shell` 57 checks, `dice` 25, `hp` 25, `content` ~44.

**If any check fails, the port changed behavior.** Fix the module, not the test. A test edited to match new behavior proves nothing — that is the whole point of keeping these suites.

- [ ] **Step 6: Run everything**

```bash
cd projects/sheets && npm test
```

Expected: unit tests pass, then all 4 parity suites pass.

- [ ] **Step 7: Commit**

```bash
git add projects/sheets/tests/
git commit -m "test: run the original suites against the built page as a parity harness"
```

---

## Task 13: Service worker, manifest, update banner, reset hatch

**Files:**
- Create: `projects/sheets/src/app/sw.js`, `src/app/update-banner.js`
- Create: `projects/sheets/tests/ui/update-banner.test.js`
- Modify: `projects/sheets/src/app/main.js`

- [ ] **Step 1: Write the service worker**

Create `projects/sheets/src/app/sw.js`. `__BUILD_ID__`, `__CAMPAIGN__` and `__CHAR__` are replaced by `tools/build.py`:

```js
"use strict";
const CACHE = `sheet-__CAMPAIGN__-__CHAR__-__BUILD_ID__`;
const ASSETS = ["./", "./index.html", "./app.js", "./manifest.json",
                "../../_fonts/fonts.css"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(ASSETS)));
});

self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(keys =>
    Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))));
});

self.addEventListener("fetch", e => {
  e.respondWith(caches.match(e.request).then(hit => hit || fetch(e.request)));
});

self.addEventListener("message", e => {
  if (e.data === "skipWaiting") self.skipWaiting();
});
```

Note there is no `skipWaiting()` in `install` — a new build must wait for the player to tap the banner.

- [ ] **Step 2: Write the failing update-banner test**

Create `projects/sheets/tests/ui/update-banner.test.js`:

```js
const { test } = require("node:test");
const assert = require("node:assert");
const { JSDOM } = require("jsdom");

const dom = new JSDOM("<!doctype html><body></body>");
global.document = dom.window.document;

const { updateBanner } = require("../../src/app/update-banner.js");

test("no banner appears when no worker is waiting", () => {
  const node = updateBanner({ waiting: null });
  assert.equal(node, null);
});

test("a waiting worker produces a reload banner", () => {
  const node = updateBanner({ waiting: {} });
  assert.match(node.textContent, /New version/);
});

test("activating posts skipWaiting to the waiting worker", () => {
  const posted = [];
  const node = updateBanner({ waiting: { postMessage: m => posted.push(m) },
                              reload: () => {} });
  node.querySelector("button").click();
  assert.deepEqual(posted, ["skipWaiting"]);
});
```

- [ ] **Step 3: Run it and confirm it fails**

```bash
cd projects/sheets && node --test tests/ui/update-banner.test.js
```

Expected: FAIL — module not found.

- [ ] **Step 4: Write the update banner**

Create `projects/sheets/src/app/update-banner.js`:

```js
"use strict";
const { el } = require("../ui/dom.js");

/** Returns a banner node, or null when there is nothing waiting to install.
    The reload happens only on tap — never mid-combat. */
function updateBanner({ waiting, reload = () => location.reload() }) {
  if (!waiting) return null;
  const bar = el("div", "update-banner", "New version — ");
  const btn = el("button", "update-reload", "reload");
  btn.addEventListener("click", () => { waiting.postMessage("skipWaiting"); reload(); });
  bar.append(btn);
  return bar;
}

module.exports = { updateBanner };
```

- [ ] **Step 5: Run it and confirm it passes**

```bash
cd projects/sheets && node --test tests/ui/update-banner.test.js
```

Expected: PASS, 3 tests.

- [ ] **Step 6: Register the worker and add the reset hatch**

Add this import to the top of `src/app/main.js`, beside the existing requires:

```js
const { updateBanner } = require("./update-banner.js");
```

Then append:

```js
if ("serviceWorker" in navigator) {
  if (new URLSearchParams(location.search).has("reset")) {
    // Recovery hatch: an installed PWA has no URL bar to hard-refresh from, so
    // a wedged worker would otherwise require uninstalling the app.
    navigator.serviceWorker.getRegistrations()
      .then(rs => Promise.all(rs.map(r => r.unregister())))
      .then(() => caches.keys())
      .then(ks => Promise.all(ks.map(k => caches.delete(k))))
      .then(() => location.replace(location.pathname));
  } else {
    navigator.serviceWorker.register("./sw.js").then(reg => {
      const show = () => {
        const bar = updateBanner({ waiting: reg.waiting });
        if (bar) document.body.prepend(bar);
      };
      if (reg.waiting) show();
      reg.addEventListener("updatefound", () =>
        reg.installing.addEventListener("statechange", function () {
          if (this.state === "installed" && navigator.serviceWorker.controller) show();
        }));
    });
  }
}
```

- [ ] **Step 7: Rebuild and confirm the suites still pass**

```bash
cd projects/sheets && npm run build -- <campaign>/toki && npm test
```

Expected: all unit and parity suites pass.

- [ ] **Step 8: Commit**

```bash
git add projects/sheets/src/app/ projects/sheets/tests/ui/update-banner.test.js
git commit -m "feat: offline service worker, update banner and ?reset recovery hatch"
```

---

## Task 14: Deploy to GitHub Pages

**Files:**
- Create: `.github/workflows/pages.yml`
- Create: `projects/sheets/CHECKLIST.md`

- [ ] **Step 1: Write the workflow**

Create `.github/workflows/pages.yml`:

```yaml
name: Deploy sheets
on:
  push:
    branches: [main]
permissions:
  contents: read
  pages: write
  id-token: write
concurrency:
  group: pages
  cancel-in-progress: true
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "24" }
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: npm ci
        working-directory: projects/sheets
      - run: npm test
        working-directory: projects/sheets
      - run: npm run build:all
        working-directory: projects/sheets
      - uses: actions/upload-pages-artifact@v3
        with: { path: projects/sheets/dist }
  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment: github-pages
    steps:
      - uses: actions/deploy-pages@v4
```

Tests run before the build, so a broken character subclass fails the workflow rather than a player's phone.

- [ ] **Step 2: Enable Pages**

In the repository settings, set Pages → Build and deployment → Source to **GitHub Actions**.

- [ ] **Step 3: Write the manual checklist**

Create `projects/sheets/CHECKLIST.md`:

```markdown
# Pre-release checklist

Walked on a real phone before a character goes live. Service worker lifecycle
is not unit tested — this is the coverage.

- [ ] Page loads at `https://fryymann.github.io/dnd/<campaign>/<char>/`
- [ ] "Add to home screen" installs it with the character's own name and icon
- [ ] Launched from the home screen it opens without browser chrome
- [ ] Airplane mode: relaunch works fully offline
- [ ] HP, slots and prepared toggles survive a force-quit and relaunch
- [ ] After a redeploy, the "New version — reload" banner appears
- [ ] Tapping reload loads the new build and preserves tracked state
- [ ] `?reset` clears the worker and caches, and the page loads fresh afterwards
- [ ] A second character's sheet does not disturb this one's tracked state
```

- [ ] **Step 4: Push and confirm the deploy**

```bash
git add .github/workflows/pages.yml projects/sheets/CHECKLIST.md
git commit -m "ci: build and deploy sheets to GitHub Pages"
git push
gh run watch
```

Expected: the workflow succeeds and the sheet is reachable at its URL.

- [ ] **Step 5: Walk the checklist on a phone**

Complete every item in `CHECKLIST.md`. Any failure is a bug in this plan's work, not a deployment issue.

---

## Task 15: Delete the monolith

Only after Task 12 is green and Task 14's checklist is complete.

**Files:**
- Delete: `projects/sheets/sheet.html`, `projects/sheets/dist/toki.html`, `projects/sheets/fonts.css`

- [ ] **Step 1: Confirm nothing still references the monolith**

```bash
cd projects/sheets && grep -rn "sheet\.html\|dist/toki\.html" --include="*.js" --include="*.py" --include="*.json" . | grep -v node_modules
```

Expected: no output.

- [ ] **Step 2: Delete it**

```bash
cd projects/sheets
git rm sheet.html fonts.css
git rm -r --ignore-unmatch dist
```

- [ ] **Step 3: Rebuild from scratch and run everything**

```bash
cd projects/sheets && npm run build:all && npm test
```

Expected: build succeeds, all unit and parity suites pass.

- [ ] **Step 4: Commit**

```bash
git add -A projects/sheets
git commit -m "refactor: delete the monolithic sheet.html

Behavior is pinned by the original jsdom suites, which now run against the
built page."
```

---

## Done when

- `npm test` green: unit suites plus 4 parity suites (~151 checks).
- Toki's sheet installed on a phone, working in airplane mode.
- Every item in `CHECKLIST.md` walked.
- `sheet.html` gone; no file in `src/core/` imports the DOM or `localStorage`.

Plan 2 — Notion sync, `validate.py`, `capabilities.py`, the campaign story cache, and `.claude/skills/craft-character-sheet/` — is written once this plan lands.
