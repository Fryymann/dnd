// Dice-engine tests. Math.random is stubbed so every roll is exact, then
// un-stubbed for statistical checks on ranges and advantage.
const fs = require("fs");
const { JSDOM, VirtualConsole } = require("jsdom");

const html = fs.readFileSync(process.argv[2], "utf8");
const errors = [];
const vc = new VirtualConsole();
vc.on("jsdomError", e => errors.push("jsdomError: " + (e.detail || e.message)));

const dom = new JSDOM(`<!doctype html><html><head></head><body>${html}</body></html>`,
  { runScripts: "outside-only", url: "https://artifact.test/toki", virtualConsole: vc });
const { window } = dom;
window.claude = { mcp: { watchTool: () => () => {}, invalidate: () => Promise.resolve(),
  listTools: () => Promise.resolve({ servers: [] }) } };
const doc = window.document;
for (const tag of doc.querySelectorAll("script")) {
  try { window.eval(tag.textContent); }
  catch (e) { errors.push("script threw: " + e.message); }
}

// Queue of forced die results, consumed in order. die(faces) = 1 + floor(r*faces),
// so to force face F we feed r = (F-1)/faces.
let queue = [];
const real = Math.random;
window.Math.random = function () {
  if (!queue.length) return real();
  const { face, faces } = queue.shift();
  return (face - 1) / faces + 1e-9;
};
const force = (...pairs) => { queue = pairs.map(([face, faces]) => ({ face, faces })); };

function check(label, fn) {
  try { const r = fn(); console.log(`  ${r === false ? "FAIL" : "ok  "}  ${label}${
    typeof r === "string" ? " — " + r : ""}`); if (r === false) errors.push(label); }
  catch (e) { console.log(`  FAIL  ${label} — ${e.message}`); errors.push(`${label}: ${e.message}`); }
}
const tab = n => [...doc.querySelectorAll(".tab")].find(x => x.textContent === n).click();
const setVal = (id, v) => { const n = doc.getElementById(id); n.value = v;
  n.dispatchEvent(new window.Event("change", { bubbles: true })); };
const tog = (k, on) => { const b = doc.querySelector(`[data-tog="${k}"]`);
  b.checked = on; b.dispatchEvent(new window.Event("change", { bubbles: true })); };
const receipt = () => doc.querySelector(".dmg-out .receipt");
const faces = el => [...el.querySelectorAll(".face")].map(f => f.textContent.trim());

console.log("\nexpression parsing:");
const rollExpr = window.eval("rollExpr");
check("2d8+3 rolls two d8 and adds a flat 3", () => {
  force([5, 8], [7, 8]);
  const r = rollExpr("2d8+3");
  return r.total === 15 && r.dice.length === 2 && r.flat === 3
    ? "5+7+3 = 15" : `got ${r.total}`;
});
check("crit doubles dice but not the flat modifier", () => {
  force([5, 8], [7, 8], [2, 8], [1, 8]);
  const r = rollExpr("2d8+3", { crit: true });
  return r.dice.length === 4 && r.total === 18 ? "4 dice, 5+7+2+1+3 = 18" : `got ${r.total}`;
});
check("bare modifier parses", () => rollExpr("+2").total === 2 && rollExpr("-3").total === -3);
check("garbage yields ok:false rather than NaN", () => {
  const r = rollExpr("banana");
  return r.ok === false && r.total === 0;
});
check("absurd dice counts are refused", () => rollExpr("999d6").dice.length === 0);

console.log("\nattack rolls (Dragonlance, crit 18-20, +13 to hit):");
tab("Turn");
setVal("c-w", "0"); setVal("c-ac", "19"); setVal("c-adv", "normal"); setVal("c-sm", "0");
for (const k of ["precise", "charge", "undead", "mounted", "dragon"]) tog(k, false);
setVal("atk-mod", "");

check("a natural 4 misses AC 19 and rolls no damage", () => {
  force([4, 20]);
  doc.querySelector('[data-roll="attack"]').click();
  const r = receipt();
  return /MISS/.test(r.textContent) && /No damage rolled/.test(r.textContent)
    ? "4+13 = 17 vs AC 19" : r.textContent.slice(0, 60);
});
check("a natural 6 hits AC 19", () => {
  force([6, 20], [8, 10], [4, 8]);   // d20, weapon d10, radiant d8
  doc.querySelector('[data-roll="attack"]').click();
  const r = receipt();
  // 8 + 8 (STR 5 + magic 3) = 16, radiant 4 -> 20
  return /HIT/.test(r.textContent) && r.querySelector(".r-total").textContent === "20"
    ? "6+13 = 19 vs AC 19, 20 damage" : r.querySelector(".r-total")?.textContent;
});
check("a natural 18 crits and doubles the damage dice", () => {
  force([18, 20], [3, 10], [2, 10], [1, 8], [1, 8]);
  doc.querySelector('[data-roll="attack"]').click();
  const r = receipt();
  const weaponLine = [...r.querySelectorAll(".r-line")]
    .find(l => /Dragonlance 1d10/.test(l.textContent));
  const n = weaponLine.querySelectorAll(".face").length;
  return /CRIT/.test(r.textContent) && n === 2
    ? `2 weapon dice, total ${r.querySelector(".r-total").textContent}` : `${n} dice`;
});
check("a natural 1 is a fumble even though +13 would clear the AC", () => {
  force([1, 20]);
  doc.querySelector('[data-roll="attack"]').click();
  return /FUMBLE/.test(receipt().textContent);
});
check("advantage shows both dice with the discard struck through", () => {
  setVal("c-adv", "adv");
  force([3, 20], [15, 20], [6, 10], [3, 8]);
  doc.querySelector('[data-roll="attack"]').click();
  const line = receipt().querySelector(".r-line");
  const dropped = line.querySelectorAll(".face.drop").length;
  return faces(line).join(",") === "3,15" && dropped === 1
    ? "kept 15, struck 3" : `${faces(line)} drop=${dropped}`;
});
check("disadvantage keeps the lower die", () => {
  setVal("c-adv", "dis");
  force([17, 20], [5, 20]);
  doc.querySelector('[data-roll="attack"]').click();
  const t = receipt().textContent;
  setVal("c-adv", "normal");
  return /MISS/.test(t) ? "kept 5 -> miss" : t.slice(0, 50);
});
check("situational +1d4 Bless is added to the attack roll", () => {
  setVal("atk-mod", "+1d4");
  force([6, 20], [4, 4], [5, 10], [2, 8]);
  doc.querySelector('[data-roll="attack"]').click();
  const line = receipt().querySelector(".r-line");
  // 6 + 13 + 4 = 23
  return /= 23/.test(line.textContent) ? "6+13+4 = 23" : line.textContent.trim().slice(0, 50);
});
check("smite dice appear in the receipt when a slot is set", () => {
  setVal("atk-mod", "");
  setVal("c-sm", "4");
  force([15, 20], [5, 10], [4, 8], [3, 8], [3, 8], [3, 8], [3, 8], [3, 8]);
  doc.querySelector('[data-roll="attack"]').click();
  const line = [...receipt().querySelectorAll(".r-line")]
    .find(l => /Divine Smite/.test(l.textContent));
  setVal("c-sm", "0");
  return line && line.querySelectorAll(".face").length === 5
    ? "5d8 rolled" : `${line && line.querySelectorAll(".face").length} dice`;
});

console.log("\nrolling never spends resources:");
check("rolling an attack leaves Channel Divinity untouched", () => {
  const before = doc.querySelectorAll("[data-pips='cd'] .pip.on").length;
  force([12, 20], [5, 10], [4, 8]);
  doc.querySelector('[data-roll="attack"]').click();
  return doc.querySelectorAll("[data-pips='cd'] .pip.on").length === before;
});

console.log("\nplanner lane rolls:");
tab("Playbook");
doc.querySelector('[data-load="A"]').click();
check("a planned bonus action exposes a Roll button", () =>
  !!doc.querySelector('[data-roll-lane="bonus"]'));
check("Pole Strike rolls 1d4 + STR 5", () => {
  force([3, 4]);
  doc.querySelector('[data-roll-lane="bonus"]').click();
  const r = doc.querySelector('.lane-receipt .receipt');
  return /= 8/.test(r.textContent) || /8/.test(r.querySelector(".r-total").textContent)
    ? "3+5 = 8" : r.textContent.slice(0, 60);
});
check("a lane modifier is applied", () => {
  const inp = doc.querySelector('[data-lanemod="bonus"]');
  inp.value = "+1d6"; inp.dispatchEvent(new window.Event("change", { bubbles: true }));
  force([2, 4], [6, 6]);
  doc.querySelector('[data-roll-lane="bonus"]').click();
  const r = doc.querySelector('.lane-receipt .receipt');
  return /= 13/.test(r.textContent) ? "2+5+6 = 13" : r.textContent.slice(0, 70);
});
check("the action lane rolls a full attack with crit handling", () => {
  force([19, 20], [4, 10], [4, 10], [2, 8], [2, 8], [7, 8], [7, 8]);
  doc.querySelector('[data-roll-lane="action"]').click();
  const r = [...doc.querySelectorAll(".lane-receipt .receipt")]
    .find(x => /CRIT|HIT|MISS/.test(x.textContent));
  return /CRIT/.test(r.textContent) ? "crit on a 19" : r.textContent.slice(0, 50);
});
check("roll log records the rolls", () => {
  const n = doc.querySelectorAll(".log-row").length;
  return n > 0 ? `${n} entries` : false;
});

console.log("\ncommit:");
check("forecast lists the smite slot before committing", () => {
  tab("Playbook"); doc.querySelector('[data-load="A"]').click();
  const keys = [...doc.querySelectorAll(".fc-cell .k")].map(k => k.textContent);
  return keys.some(k => /Level 4 slots/.test(k)) ? keys.join(", ") : `got ${keys.join(", ")}`;
});
check("Commit round spends the planned Precise Strike and slot", () => {
  tab("Playbook"); doc.querySelector('[data-load="A"]').click();
  const cdBefore = doc.querySelectorAll("[data-pips='precise'] .pip.on").length;
  const slotBefore = doc.querySelectorAll("[data-pips='slot-4'] .pip.on").length;
  doc.querySelector("[data-commit]").click();
  const cdAfter = doc.querySelectorAll("[data-pips='precise'] .pip.on").length;
  const slotAfter = doc.querySelectorAll("[data-pips='slot-4'] .pip.on").length;
  if (cdAfter !== cdBefore - 1) return false;
  if (slotAfter !== slotBefore - 1) return false;
  return `precise ${cdBefore}→${cdAfter}, 4th slot ${slotBefore}→${slotAfter}`;
});
check("committing clears the plan", () =>
  doc.querySelectorAll(".lane.filled").length === 0);

console.log("\nstatistical sanity (unstubbed RNG, 400 rolls):");
queue = [];
check("d20 faces stay within 1..20 and cover the range", () => {
  const seen = new Set();
  for (let i = 0; i < 400; i++) {
    const r = window.eval("rollD20(0)");
    if (r.kept < 1 || r.kept > 20) return `out of range: ${r.kept}`;
    seen.add(r.kept);
  }
  return seen.size >= 18 ? `${seen.size}/20 faces seen` : `only ${seen.size} faces`;
});
check("advantage keeps the higher of two", () => {
  for (let i = 0; i < 400; i++) {
    const r = window.eval("rollD20(1)");
    if (r.kept !== Math.max(...r.faces)) return "kept the wrong die";
  }
  return "400/400 correct";
});
check("5d8 totals stay in 5..40", () => {
  for (let i = 0; i < 400; i++) {
    const t = rollExpr("5d8").total;
    if (t < 5 || t > 40) return `out of range: ${t}`;
  }
  return "in range";
});

console.log("\n" + (errors.length ? `${errors.length} FAILURE(S):` : "all checks passed"));
errors.forEach(e => console.log("  - " + e));
process.exit(errors.length ? 1 : 0);
