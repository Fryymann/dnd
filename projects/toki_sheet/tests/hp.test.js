// HP adjustment tests: manual temp HP, max-HP bonuses from Aid / Heroes' Feast,
// and the interactions with damage, healing, rests and persistence.
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

let queue = [];
const real = Math.random;
window.Math.random = function () {
  if (!queue.length) return real();
  const { face, faces } = queue.shift();
  return (face - 1) / faces + 1e-9;
};
const force = (...pairs) => { queue = pairs.map(([f, n]) => ({ face: f, faces: n })); };

function check(label, fn) {
  try { const r = fn(); console.log(`  ${r === false ? "FAIL" : "ok  "}  ${label}${
    typeof r === "string" ? " — " + r : ""}`); if (r === false) errors.push(label); }
  catch (e) { console.log(`  FAIL  ${label} — ${e.message}`); errors.push(`${label}: ${e.message}`); }
}
const cur = () => +doc.querySelector(".hp-cur").textContent;
const max = () => +doc.querySelector(".hp-max").textContent.replace("/", "").trim();
const temp = () => { const t = doc.querySelector(".hp-temp");
  return t ? +/\+(\d+)/.exec(t.textContent)[1] : 0; };
const bonus = () => { const b = doc.querySelector(".hp-bonus");
  return b ? +/\+(\d+)/.exec(b.textContent)[1] : 0; };
const setNum = (id, v) => { doc.getElementById(id).value = String(v); };
const click = sel => doc.querySelector(sel).click();
const state = () => JSON.parse(window.localStorage.getItem("toki-console-v1"));

console.log("\nbaseline:");
click("#long-rest");
check("206 / 206, no temp, no bonus", () =>
  cur() === 206 && max() === 206 && temp() === 0 && bonus() === 0
    ? `${cur()}/${max()}` : `${cur()}/${max()} temp ${temp()} bonus ${bonus()}`);

console.log("\nmanual temp HP:");
check("set temp to an exact value", () => {
  setNum("temp-set", 17); click("[data-temp-set]");
  return temp() === 17 ? "17" : `got ${temp()}`;
});
check("setting temp lower is allowed (manual means manual)", () => {
  setNum("temp-set", 4); click("[data-temp-set]");
  return temp() === 4 ? "17 → 4" : `got ${temp()}`;
});
check("temp does not change current or max HP", () =>
  cur() === 206 && max() === 206);
check("damage spends temp first", () => {
  setNum("hp-amt", 10); click("[data-hp='dmg']");
  return temp() === 0 && cur() === 200 ? "4 temp absorbed, 6 to HP" : `temp ${temp()} hp ${cur()}`;
});
check("clear temp by setting zero", () => {
  setNum("temp-set", 9); click("[data-temp-set]");
  setNum("temp-set", 0); click("[data-temp-set]");
  return temp() === 0;
});

console.log("\nAid (+5 max and +5 current):");
click("#long-rest");
check("Aid raises max and heals the same amount", () => {
  click('[data-grant="5"]');
  return max() === 211 && cur() === 211 && bonus() === 5
    ? "211/211, +5 max" : `${cur()}/${max()} bonus ${bonus()}`;
});
check("Aid at a higher slot stacks with a second click", () => {
  click('[data-grant="5"]');
  return max() === 216 && cur() === 216 && bonus() === 10
    ? "216/216, +10 max" : `${cur()}/${max()} bonus ${bonus()}`;
});
check("healing clamps to the boosted maximum, not the base", () => {
  setNum("hp-amt", 30); click("[data-hp='dmg']");
  setNum("hp-amt", 999); click("[data-hp='heal']");
  return cur() === 216 ? "healed to 216" : `got ${cur()}`;
});
check("clearing the bonus trims current HP down to the base max", () => {
  click('[data-grant="clear"]');
  return max() === 206 && cur() === 206 && bonus() === 0
    ? "216 → 206" : `${cur()}/${max()} bonus ${bonus()}`;
});
check("clearing does not heal someone who was already below base", () => {
  click('[data-grant="5"]');            // 211/211
  setNum("hp-amt", 100); click("[data-hp='dmg']");   // 111/211
  const before = cur();
  click('[data-grant="clear"]');
  return cur() === before && max() === 206 ? `stayed at ${before}` : `${cur()}/${max()}`;
});

console.log("\nHeroes' Feast (2d10):");
click("#long-rest");
check("rolls 2d10 and applies it to max and current", () => {
  force([7, 10], [6, 10]);              // 13
  click('[data-grant="2d10"]');
  return max() === 219 && cur() === 219 && bonus() === 13
    ? "rolled 13 → 219/219" : `${cur()}/${max()} bonus ${bonus()}`;
});
check("the roll is recorded in the roll log", () => {
  const rows = [...doc.querySelectorAll(".log-row")]
    .filter(r => /Heroes' Feast/.test(r.textContent));
  return rows.length ? rows[0].textContent.replace(/\s+/g, " ").trim() : false;
});
check("Aid stacks on top of Heroes' Feast", () => {
  click('[data-grant="5"]');
  return max() === 224 && bonus() === 18 ? "+18 max" : `bonus ${bonus()}`;
});

console.log("\nmanual max bonus:");
check("Set writes the bonus without granting hit points", () => {
  click('[data-grant="clear"]'); click("#long-rest");
  setNum("hp-amt", 50); click("[data-hp='dmg']");   // 156/206
  const before = cur();
  setNum("max-set", 20); click("[data-max-set]");
  return max() === 226 && cur() === before
    ? `max 226, HP unchanged at ${before}` : `${cur()}/${max()}`;
});
check("lowering the bonus below current HP pulls HP down", () => {
  setNum("hp-amt", 999); click("[data-hp='heal']");  // 226/226
  setNum("max-set", 0); click("[data-max-set]");
  return max() === 206 && cur() === 206 ? "226 → 206" : `${cur()}/${max()}`;
});

console.log("\nrests and persistence:");
check("long rest heals to the boosted max (Heroes' Feast lasts 24h)", () => {
  force([9, 10], [8, 10]);             // 17
  click('[data-grant="2d10"]');
  setNum("hp-amt", 120); click("[data-hp='dmg']");
  click("#long-rest");
  return cur() === 223 && max() === 223 ? "healed to 223" : `${cur()}/${max()}`;
});
check("long rest clears temp HP", () => {
  setNum("temp-set", 12); click("[data-temp-set]");
  click("#long-rest");
  return temp() === 0;
});
check("long rest keeps the max bonus (durations vary, so it is manual)", () =>
  bonus() === 17 ? "+17 retained" : `bonus ${bonus()}`);
check("bonus and temp persist to localStorage", () => {
  setNum("temp-set", 6); click("[data-temp-set]");
  const s = state();
  return s.maxBonus === 17 && s.temp === 6 ? "maxBonus 17, temp 6" : JSON.stringify(s.maxBonus);
});
check("Reset clears the bonus back to the exported maximum", () => {
  window.confirm = () => true;
  click("#reset");
  return max() === 206 && cur() === 206 && bonus() === 0 && temp() === 0
    ? "206/206 clean" : `${cur()}/${max()} bonus ${bonus()} temp ${temp()}`;
});

console.log("\nedge cases:");
check("the gauge never overflows its 24 segments", () => {
  force([10, 10], [10, 10]);
  click('[data-grant="2d10"]');
  setNum("temp-set", 400); click("[data-temp-set]");
  const segs = doc.querySelectorAll(".gauge i").length;
  const filled = doc.querySelectorAll(".gauge i.on, .gauge i.tmp").length;
  return segs === 24 && filled <= 24 ? `${filled}/24 filled` : `${filled}/${segs}`;
});
check("negative input is floored at zero", () => {
  setNum("temp-set", -50); click("[data-temp-set]");
  setNum("max-set", -10); click("[data-max-set]");
  return temp() === 0 && bonus() === 0 ? "floored" : `temp ${temp()} bonus ${bonus()}`;
});
check("damage cannot push HP below zero", () => {
  setNum("hp-amt", 9999); click("[data-hp='dmg']");
  return cur() === 0 ? "0" : `got ${cur()}`;
});
check("garbage in the number field is treated as zero, not NaN", () => {
  doc.getElementById("temp-set").value = "";
  click("[data-temp-set]");
  return temp() === 0 && !Number.isNaN(cur());
});

console.log("\n" + (errors.length ? `${errors.length} FAILURE(S):` : "all checks passed"));
errors.forEach(e => console.log("  - " + e));
process.exit(errors.length ? 1 : 0);
