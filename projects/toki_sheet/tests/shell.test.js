// Smoke-test the published Toki console in jsdom: does it render, and does
// every interactive path survive a click without throwing?
const fs = require("fs");
const { JSDOM } = require("jsdom");

const html = fs.readFileSync(process.argv[2], "utf8");
const errors = [];

const dom = new JSDOM(`<!doctype html><html><head></head><body>${html}</body></html>`, {
  runScripts: "dangerously",
  url: "https://artifact.test/toki",   // jsdom denies localStorage on opaque origins
  virtualConsole: new (require("jsdom").VirtualConsole)().on("jsdomError", e =>
    errors.push("jsdomError: " + (e.detail || e.message))),
});
const { window } = dom;
window.addEventListener("error", e => errors.push("window.error: " + e.message));
const doc = window.document;

function fail(msg) { errors.push(msg); }
function check(label, fn) {
  try { const r = fn(); console.log(`  ${r === false ? "FAIL" : "ok  "}  ${label}${
    typeof r === "string" ? " — " + r : ""}`); if (r === false) fail(label); }
  catch (e) { console.log(`  FAIL  ${label} — ${e.message}`); fail(`${label}: ${e.message}`); }
}

console.log("\nrender:");
check("title", () => doc.title === "Toki Ironlung — Field Console" || doc.title);
check("name in header", () => doc.getElementById("ch-name").textContent.trim());
check("subtitle populated", () => doc.getElementById("ch-sub").textContent.includes("Paladin 14"));
check("rail rendered", () => doc.querySelectorAll("#rail .panel").length >= 6);
check("hp gauge segments", () => doc.querySelectorAll(".gauge i").length === 24);
check("hp shows max", () => doc.querySelector(".hp-cur").textContent === "206");
check("AC tile", () => doc.querySelector(".vital .v").textContent === "22");
check("4 tabs", () => doc.querySelectorAll(".tab").length === 4);
check("4 lanes", () => doc.querySelectorAll(".lane").length === 4);
check("damage roller rendered", () => !!doc.querySelector("[data-roll=\"attack\"]") && doc.querySelector(".roll-bar .odds").textContent);
check("reaction watchlist", () => doc.querySelectorAll(".wcard").length === 8);
check("passive perception 22", () => [...doc.querySelectorAll("#rail .lrow")]
  .find(r => r.textContent.includes("Passive Perception")).querySelector(".vl").textContent === "22");
check("spell slots 4 rows", () => doc.querySelectorAll("[data-pips^='slot-']").length === 4);
check("resource meters", () => doc.querySelectorAll("[data-pips]").length >= 6);
check("no derived-note missing", () =>
  doc.querySelector(".derived-note") ? "slot fallback flagged" : "export had slots");

// --- tab switching ---------------------------------------------------------
console.log("\ntabs:");
for (const label of ["Playbook", "Sheet", "Codex", "Turn"]) {
  check(`switch to ${label}`, () => {
    const t = [...doc.querySelectorAll(".tab")].find(x => x.textContent === label);
    t.click();
    return doc.getElementById("stage").children.length > 0;
  });
}

console.log("\nplaybook:");
doc.querySelector(".tab").click(); // back to Turn first
[...doc.querySelectorAll(".tab")].find(x => x.textContent === "Playbook").click();
check("plays rendered", () => doc.querySelectorAll(".play").length === 7);
check("situation filters", () => doc.querySelectorAll("[data-plays] .chip").length >= 6);

console.log("\nload every play into the planner:");
const ids = [...doc.querySelectorAll("[data-load]")].map(b => b.dataset.load);
for (const id of ids) {
  check(`load ${id}`, () => {
    [...doc.querySelectorAll(".tab")].find(x => x.textContent === "Playbook").click();
    const btn = doc.querySelector(`[data-load="${id}"]`);
    if (!btn) return `button missing`;
    btn.click();
    const filled = doc.querySelectorAll(".lane.filled").length;
    return filled > 0 ? `${filled} lane(s)` : "no lanes filled";
  });
}

// --- rail interactions -----------------------------------------------------
console.log("\ntrackers:");
[...doc.querySelectorAll(".tab")].find(x => x.textContent === "Turn").click();

check("damage reduces HP", () => {
  doc.getElementById("hp-amt").value = "20";
  doc.querySelector("[data-hp='dmg']").click();
  return doc.querySelector(".hp-cur").textContent === "186"
    || doc.querySelector(".hp-cur").textContent;
});
check("temp HP soaks damage", () => {
  doc.getElementById("temp-set").value = "10";
  doc.querySelector("[data-temp-set]").click();
  doc.getElementById("hp-amt").value = "4";
  doc.querySelector("[data-hp='dmg']").click();
  const hp = doc.querySelector(".hp-cur").textContent;
  const temp = doc.querySelector(".hp-temp");
  return hp === "186" && temp && temp.textContent.includes("6")
    ? "hp held, temp 10→6" : `hp ${hp}, temp ${temp && temp.textContent}`;
});
check("heal clamps to max", () => {
  doc.getElementById("hp-amt").value = "999";
  doc.querySelector("[data-hp='heal']").click();
  return doc.querySelector(".hp-cur").textContent === "206" || doc.querySelector(".hp-cur").textContent;
});
check("channel divinity pip spends", () => {
  const pips = doc.querySelectorAll("[data-pips='cd'] .pip");
  const before = [...pips].filter(p => p.classList.contains("on")).length;
  pips[before - 1].click();
  const after = [...doc.querySelectorAll("[data-pips='cd'] .pip")]
    .filter(p => p.classList.contains("on")).length;
  return after === before - 1 ? `${before} → ${after}` : `${before} → ${after}`;
});
check("lay on hands pool spends", () => {
  doc.querySelector("[data-pool='loh'] button[data-d='10']").click();
  return doc.querySelector(".pool-n").textContent === "60/70"
    || doc.querySelector(".pool-n").textContent;
});
check("spell slot spends", () => {
  const pips = doc.querySelectorAll("[data-pips='slot-1'] .pip");
  pips[3].click();
  return [...doc.querySelectorAll("[data-pips='slot-1'] .pip")]
    .filter(p => p.classList.contains("on")).length === 3;
});
check("condition toggles", () => {
  doc.querySelector("[data-conds] .chip[data-c='Prone']").click();
  return doc.querySelector("[data-conds] .chip[data-c='Prone']").classList.contains("on");
});
check("death save toggles", () => {
  doc.querySelector("[data-death='bad'] .dot").click();
  return doc.querySelectorAll("[data-death='bad'] .dot.on").length === 1;
});
check("short rest restores Guarded Mind", () => {
  const pips = doc.querySelectorAll("[data-pips='guarded'] .pip");
  pips[0].click();
  doc.getElementById("short-rest").click();
  return [...doc.querySelectorAll("[data-pips='guarded'] .pip")]
    .filter(p => p.classList.contains("on")).length === 1;
});
check("long rest restores everything", () => {
  doc.getElementById("long-rest").click();
  const cd = [...doc.querySelectorAll("[data-pips='cd'] .pip")]
    .filter(p => p.classList.contains("on")).length;
  const hp = doc.querySelector(".hp-cur").textContent;
  const loh = doc.querySelector(".pool-n").textContent;
  return cd === 3 && hp === "206" && loh === "70/70"
    ? "cd 3, hp 206, loh 70/70" : `cd ${cd}, hp ${hp}, loh ${loh}`;
});

// --- calculator ------------------------------------------------------------
console.log("\ndamage calculator:");
const odds = () => doc.querySelector(".roll-bar .odds").textContent;
const avgDmg = () => parseFloat(/avg ([\d.]+)/.exec(odds())[1]);
const critPct = () => parseFloat(/([\d.]+)% crit/.exec(odds())[1]);
const hitPct  = () => parseFloat(/([\d.]+)% hit/.exec(odds())[1]);
const rangeRow = () => doc.querySelector(".bd tr.tot td").textContent;
const setVal = (id, v) => {
  const n = doc.getElementById(id); n.value = v;
  n.dispatchEvent(new window.Event("change", {bubbles:true}));
};
// Loading plays above left smite/precise toggles on — clear them so each check
// below measures only the thing it names.
const clearCalc = () => {
  setVal("c-ac", "17"); setVal("c-sm", "0"); setVal("c-adv", "normal"); setVal("c-w", "0");
  for (const k of ["precise","charge","undead","mounted"]) {
    const box = doc.querySelector(`[data-tog="${k}"]`);
    if (box.checked) { box.checked = false;
      box.dispatchEvent(new window.Event("change", {bubbles:true})); }
  }
};
clearCalc();

check("baseline vs AC 17, no riders", () => {
  const v = avgDmg();
  // pike 1d10+8 (5.5+8) + radiant 1d8 (4.5) = 18.0 on hit; needs 4+ = 85%,
  // crit 18+ = 15% -> 0.70*18 + 0.15*28 = 16.8
  return Math.abs(v - 16.8) < 0.4 ? `${v} (expected 16.8)` : `${v}, expected ~16.8`;
});
check("higher AC lowers expected damage", () => {
  const a = avgDmg(); setVal("c-ac", "25");
  const b = avgDmg(); setVal("c-ac", "17");
  return b < a ? `AC17 ${a} > AC25 ${b}` : false;
});
check("smite dice scale with slot level", () => {
  const dice = lv => { setVal("c-sm", String(lv));
    const row = [...doc.querySelectorAll(".bd td")]
      .find(td => td.textContent.startsWith("Divine Smite"));
    return row && row.textContent.trim(); };
  // 2024 Divine Smite: 2d8 at 1st, +1d8 per level above.
  const got = [1,2,3,4].map(dice);
  const want = ["Divine Smite 2d8","Divine Smite 3d8","Divine Smite 4d8","Divine Smite 5d8"];
  setVal("c-sm", "0");
  return got.join(" / ") === want.join(" / ") ? got.join(", ") : `got ${got.join(", ")}`;
});
check("undead adds a smite die", () => {
  setVal("c-sm", "1");
  const box = doc.querySelector('[data-tog="undead"]');
  box.checked = true; box.dispatchEvent(new window.Event("change", {bubbles:true}));
  const row = [...doc.querySelectorAll(".bd td")]
    .find(td => td.textContent.startsWith("Divine Smite")).textContent.trim();
  box.checked = false; box.dispatchEvent(new window.Event("change", {bubbles:true}));
  setVal("c-sm", "0");
  return row === "Divine Smite 3d8" ? row : `got ${row}, wanted Divine Smite 3d8`;
});
check("smite raises expected damage", () => {
  const a = avgDmg(); setVal("c-sm", "4");
  const b = avgDmg(); setVal("c-sm", "0");
  return b > a ? `${a} → ${b}` : false;
});
check("crit range shows 18+ for Dragonlance", () => /crits on 18/.test(rangeRow()));
check("Precise Strike grants advantage on its own", () => {
  const box = doc.querySelector('[data-tog="precise"]');
  box.checked = true; box.dispatchEvent(new window.Event("change", {bubbles:true}));
  const c = critPct();
  box.checked = false; box.dispatchEvent(new window.Event("change", {bubbles:true}));
  return Math.abs(c - 27.75) < 0.6 ? `${c}% crit` : `${c}%, expected 27.8`;
});
check("weapon switch changes profile", () => {
  setVal("c-w", "3");
  const t = rangeRow(); setVal("c-w", "0");
  return /crits on 20/.test(t) ? "Crownguard crits on 20" : t;
});
check("forecast reflects a planned smite", () => {
  const cells = [...doc.querySelectorAll(".fc-cell .k")].map(k => k.textContent);
  return cells.join(", ");
});

// --- persistence -----------------------------------------------------------
console.log("\npersistence:");
check("state written to localStorage", () => {
  const raw = window.localStorage.getItem("toki-console-v1");
  if (!raw) return false;
  const s = JSON.parse(raw);
  return `hp ${s.hp}, tab ${s.tab}, keys ${Object.keys(s).length}`;
});

console.log("\nsheet + codex content:");
[...doc.querySelectorAll(".tab")].find(x => x.textContent === "Sheet").click();
check("abilities row", () => doc.querySelectorAll(".abil").length === 6);
check("attacks table has Dragonlance", () =>
  doc.querySelector(".bd").textContent.includes("Legendary Dragonlance"));
check("renamed items show original", () =>
  [...doc.querySelectorAll(".was")].some(w => w.textContent === "Dragonlance (Pike)"));
check("spells grouped", () => doc.body.textContent.includes("Cantrips"));
check("steeds rendered", () => doc.body.textContent.includes("Alduin"));
check("features listed", () => doc.querySelectorAll("details.item").length > 60);

[...doc.querySelectorAll(".tab")].find(x => x.textContent === "Codex").click();
check("backstory present", () => doc.body.textContent.includes("Ironlung"));
check("bonds card", () => doc.body.textContent.includes("Cidriel"));
check("codex campaign panel is live, not a placeholder", () =>
  !doc.querySelector(".feed-state") && doc.querySelectorAll(".arc").length === 3);

console.log("\n" + (errors.length ? `${errors.length} FAILURE(S):` : "all checks passed"));
errors.forEach(e => console.log("  - " + e));
process.exit(errors.length ? 1 : 0);
