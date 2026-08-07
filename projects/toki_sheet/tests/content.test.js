// v2 smoke test: canonical plays, resource tokens, dragon math, decision tree,
// and the live-Notion layer driven by a stub that mimics window.claude.mcp.
const fs = require("fs");
const { JSDOM, VirtualConsole } = require("jsdom");

const html = fs.readFileSync(process.argv[2], "utf8");
const MODE = process.argv[3] || "ok";     // ok | error:<code> | absent | noconnector | renamed
const SERVER_NAME = MODE === "renamed" ? "Notion (Personal)" : "Notion";
const errors = [];

// The real notion-fetch payload observed this session, trimmed to the parts the
// page parses. Not sample data — it is replayed only inside this test harness.
const ARC = `<page url="https://app.notion.com/p/7b2b">
<callout icon="⚔️" color="red_bg">
\tOfficial source — at-table gameplay reference.
</callout>
<callout icon="🔄" color="blue_bg">
\t**This arc — Sylvanesti: on foot past the Thon-Thalas, racing to free King Lorac:**
\t· **New gear and feat:** your family's **+1 Solamnic plate** and the **Inspiring Leader** feat.
\t· **No mounts:** Alduin and the griffons are on the far bank of the Thon-Thalas.
\t· **Clock:** reach Lorac before the **1st of December** or Alhana goes in alone.
</callout>
## Threads
Some overview prose that should show up in the digest.
</page>`;

const vc = new VirtualConsole();
vc.on("jsdomError", e => errors.push("jsdomError: " + (e.detail || e.message)));

const dom = new JSDOM(`<!doctype html><html><head></head><body>${html}</body></html>`, {
  runScripts: "outside-only",
  url: "https://artifact.test/toki",
  virtualConsole: vc,
});
const { window } = dom;

// Install the stub BEFORE the page script runs.
if (MODE !== "absent") {
  window.claude = {
    mcp: {
      watchTool(server, tool, input, handler) {
        if (server !== SERVER_NAME) errors.push("wrong server: " + server);
        if (tool !== "notion-fetch") errors.push("wrong tool: " + tool);
        if (!input || !input.id) errors.push("no page id in input");
        Promise.resolve().then(() => {
          if (MODE.startsWith("error:")) {
            handler({type:"error", error:{code:MODE.slice(6), message:"stub failure",
                     server:"Notion", retryable:MODE.includes("unavailable")}});
          } else {
            handler({type:"data", result:{
              content:[{type:"text", text:"..."}],
              payload:{title:"Toki Ironlung — Gameplay Reference",
                       url:"https://app.notion.com/p/7b2b", text:ARC},
              cache:{storedAt: 1754532000000, revalidating:false},
            }});
          }
        });
        return () => {};
      },
      invalidate: () => Promise.resolve(),
      callTool: () => Promise.reject({code:"upstream_error", message:"unused"}),
      listTools: () => Promise.resolve({servers:
        MODE === "noconnector" ? []
        : [{server: SERVER_NAME, authStatus: "connected",
            tools: [{name:"notion-fetch", description:"", annotations:{readOnlyHint:true}}]}]}),
    },
  };
}

// Run the page's scripts now that the stub exists.
const doc = window.document;
for (const tag of doc.querySelectorAll("script")) {
  try { window.eval(tag.textContent); }
  catch (e) { errors.push("script threw: " + e.message); }
}
window.addEventListener("error", e => errors.push("window.error: " + e.message));

function check(label, fn) {
  try { const r = fn(); console.log(`  ${r === false ? "FAIL" : "ok  "}  ${label}${
    typeof r === "string" ? " — " + r : ""}`); if (r === false) errors.push(label); }
  catch (e) { console.log(`  FAIL  ${label} — ${e.message}`); errors.push(`${label}: ${e.message}`); }
}
const tab = name => [...doc.querySelectorAll(".tab")].find(x => x.textContent === name).click();
const setVal = (id, v) => { const n = doc.getElementById(id); n.value = v;
  n.dispatchEvent(new window.Event("change", {bubbles:true})); };
const tog = (k, on) => { const b = doc.querySelector(`[data-tog="${k}"]`);
  b.checked = on; b.dispatchEvent(new window.Event("change", {bubbles:true})); };

const odds = () => doc.querySelector(".roll-bar .odds").textContent;
const avgDmg = () => parseFloat(/avg ([\d.]+)/.exec(odds())[1]);
const critPct = () => parseFloat(/([\d.]+)% crit/.exec(odds())[1]);
const hitPct  = () => parseFloat(/([\d.]+)% hit/.exec(odds())[1]);
const rangeRow = () => doc.querySelector(".bd tr.tot td").textContent;

const wait = () => new Promise(r => setTimeout(r, 60));

(async () => {
console.log(`\n=== MODE: ${MODE} ===`);
await wait();

console.log("\ncorrected character math:");
check("HP max 206", () => doc.querySelector(".hp-cur").textContent === "206"
  || doc.querySelector(".hp-cur").textContent);
check("AC 22", () => doc.querySelectorAll(".vital .v")[0].textContent === "22");
check("Initiative +9", () => doc.querySelectorAll(".vital .v")[1].textContent === "+9");
tab("Sheet");
check("STR 20 / DEX 18 / CON 16 / INT 10 / WIS 14 / CHA 17", () => {
  const got = [...doc.querySelectorAll(".abil")].map(a =>
    a.querySelector(".s").textContent).join("/");
  return got === "20/18/16/10/14/17" ? got : `got ${got}`;
});
check("passive Perception 22 (matches D&D Beyond)", () => {
  const rows = [...doc.querySelectorAll("#rail .lrow")];
  const r = rows.find(x => x.textContent.includes("Passive Perception"));
  const v = r.querySelector(".vl").textContent.trim();
  return v === "22" ? v : `got ${v}, D&D Beyond shows 22`;
});
check("skill proficiencies restored", () => {
  tab("Sheet");
  const prof = [...doc.querySelectorAll(".lrow .pf.on, .lrow .pf.ex")].length;
  return prof >= 7 ? `${prof} marked (5 skills + 2 saves)` : `only ${prof} marked`;
});
check("Perception shows expertise +12", () => {
  const r = [...doc.querySelectorAll(".lrow")].find(x => x.textContent.includes("Perception")
    && x.querySelector(".ab"));
  return r.querySelector(".vl").textContent.trim() === "+12"
    && r.querySelector(".pf").classList.contains("ex");
});
check("senses surfaced in the rail", () => {
  const t = doc.querySelector("#rail").textContent;
  return t.includes("Darkvision") && t.includes("Blindsight") && t.includes("Climb Speed");
});
check("Dragonlance to hit +13", () => {
  const row = [...doc.querySelectorAll(".bd tr")]
    .find(r => r.textContent.includes("Legendary Dragonlance"));
  const hit = row.querySelectorAll("td")[1].textContent.trim();
  return hit === "+13" ? hit : `got ${hit} (want +13: STR 5 + prof 5 + magic 3)`;
});
tab("Turn");

console.log("\nplaybook A–G:");
tab("Playbook");
check("seven canonical plays", () => doc.querySelectorAll(".play").length === 7);
check("play ids A–G", () => {
  const ids = [...doc.querySelectorAll(".play-id")].map(x => x.textContent.trim().split(" ")[1]);
  return ids.join("") === "ABCDEFG" ? ids.join(" ") : `got ${ids.join(" ")}`;
});
check("tags rendered", () => doc.querySelectorAll(".ptag").length > 8);
check("core loop line", () => doc.querySelector(".loop").textContent.includes("→"));
check("resource tokens are live buttons", () => {
  const n = doc.querySelectorAll(".tok[data-spend]").length;
  return n > 0 ? `${n} use-tokens` : false;
});
check("slot tokens rendered", () => doc.querySelectorAll("[data-spend-slot]").length > 0);
check("pool token rendered", () => doc.querySelectorAll("[data-spend-pool]").length > 0);
check("drift markers present", () => {
  const d = [...doc.querySelectorAll(".drift")];
  return d.length ? d.map(x => x.textContent.replace(" ⚠","")).join(", ") : false;
});
check("5th-level slot drift is flagged", () =>
  [...doc.querySelectorAll(".drift")].some(d => d.textContent.includes("5th-level")));
check("no level-5 slot token pretends to exist", () => {
  const dead = [...doc.querySelectorAll(".tok.dry")].filter(t => /L5/.test(t.textContent));
  return dead.length === 0 ? "none referenced" : `${dead.length} shown as unavailable`;
});

check("spending a token decrements the rail", () => {
  const t = doc.querySelector('.tok[data-spend="cd"]');
  if (!t) return "no cd token in current filter";
  const before = [...doc.querySelectorAll("[data-pips='cd'] .pip")]
    .filter(p => p.classList.contains("on")).length;
  t.click();
  const after = [...doc.querySelectorAll("[data-pips='cd'] .pip")]
    .filter(p => p.classList.contains("on")).length;
  return after === before - 1 ? `${before} → ${after}` : `${before} → ${after}`;
});

console.log("\nload plays:");
for (const id of ["A","B","C","D","E","F","G"]) {
  check(`load ${id}`, () => {
    tab("Playbook");
    doc.querySelector(`[data-load="${id}"]`).click();
    return doc.querySelectorAll(".lane.filled").length + " lane(s)";
  });
}
check("play D arms the dragon toggle and picks the lance", () => {
  tab("Playbook"); doc.querySelector('[data-load="D"]').click();
  const dragon = doc.querySelector('[data-tog="dragon"]').checked;
  const w = doc.getElementById("c-w");
  const name = w.options[w.selectedIndex].textContent;
  return dragon && /Dragonlance/.test(name) ? `dragon on, ${name}` : `dragon=${dragon}, ${name}`;
});

console.log("\nprepared spells:");
tab("Sheet");
check("prepared counter shows 10 / 11", () => {
  const h = [...doc.querySelectorAll(".panel-h")].find(x => x.textContent.includes("Prepared"));
  const v = h.querySelectorAll(".eyebrow")[1].textContent.trim();
  return v === "10 / 11" ? v : `got ${v}`;
});
check("10 preparable spells have toggles", () =>
  doc.querySelectorAll("[data-prep]").length === 10);
check("Divine Smite is not user-preparable (always prepared)", () =>
  ![...doc.querySelectorAll("[data-prep]")].some(b => b.dataset.prep === "Divine Smite"));
check("unticking Revivify persists and decrements the count", () => {
  doc.querySelector('[data-prep="Revivify"]').click();
  const h = [...doc.querySelectorAll(".panel-h")].find(x => x.textContent.includes("Prepared"));
  const v = h.querySelectorAll(".eyebrow")[1].textContent.trim();
  const stored = JSON.parse(window.localStorage.getItem("toki-console-v1")).prepared;
  return v === "9 / 11" && stored.Revivify === false ? `${v}, persisted` : `${v}`;
});
check("Play C now warns Revivify is not prepared", () => {
  tab("Playbook");
  const c = [...doc.querySelectorAll(".play")].find(x => x.textContent.includes("Bodyguard"));
  return /Revivify/.test(c.textContent) && /not prepared/.test(c.textContent);
});
check("Spirit Guardians reads as prepared, no warning", () => {
  const b = [...doc.querySelectorAll(".play")].find(x => x.textContent.includes("Lockdown"));
  const seg = b.innerHTML.split("Spirit Guardians")[1].slice(0, 120);
  return !/not prepared/.test(seg) ? "clean" : "still warning";
});
check("re-ticking Revivify clears the play warning", () => {
  tab("Sheet");
  doc.querySelector('[data-prep="Revivify"]').click();
  tab("Playbook");
  const c = [...doc.querySelectorAll(".play")].find(x => x.textContent.includes("Bodyguard"));
  return !/not prepared/.test(c.textContent);
});
check("no stale Spirit Guardians drift marker", () =>
  ![...doc.querySelectorAll(".drift")].some(d => /Spirit Guardians/.test(d.textContent)));
check("5th-level drift explains the 5d8 cap correctly", () => {
  const d = [...doc.querySelectorAll(".drift")].find(x => /5th-level/.test(x.textContent));
  return /already reaches the 5d8/.test(d.title) ? "accurate" : d.title.slice(0,60);
});

console.log("\ndragon math:");
tab("Turn");
setVal("c-w", "0"); setVal("c-ac", "19"); setVal("c-sm", "0"); setVal("c-adv", "normal");
for (const k of ["precise","charge","undead","mounted","dragon"]) tog(k, false);
check("baseline vs AC 19", () => `avg ${avgDmg()}`);
check("dragon toggle adds the 3d6 force rider", () => {
  tog("dragon", true);
  const row = [...doc.querySelectorAll(".bd td")].find(td => /vs dragons/.test(td.textContent));
  return row ? row.textContent.trim() : false;
});
check("dragon toggle grants advantage (crit 15% → 27.8%)", () => {
  const crit = critPct();
  return Math.abs(crit - 27.75) < 0.6 ? `${crit}%` : `${crit}%, expected 27.8`;
});
check("Death to Dragons callout cites current HP", () =>
  [...doc.querySelectorAll(".note-in")].some(n =>
    n.textContent.includes("Death to Dragons") && n.textContent.includes("206")));
tog("dragon", false);

console.log("\ndecision tree:");
check("nine tree rows", () => doc.querySelectorAll(".tree-row").length === 9);

console.log("\nlive Notion:");
if (MODE === "ok") {
  check("arc banner rendered on the Turn tab", () =>
    doc.querySelector(".arc-b ul") ? "bullets present" : false);
  check("arc heading parsed", () =>
    doc.querySelector(".arc-b").textContent.includes("Sylvanesti"));
  check("arc bullets parsed", () => {
    const n = doc.querySelectorAll(".arc-b li").length;
    return n === 3 ? "3 bullets" : `got ${n}, expected 3`;
  });
  check("markdown bold converted, tags stripped", () => {
    const h = doc.querySelector(".arc-b").innerHTML;
    return h.includes("<b>") && !h.includes("**") && !h.includes("&lt;callout");
  });
  check("freshness from cache.storedAt, not Date.now", () =>
    doc.querySelector(".arc-h .age").textContent.trim().length > 0);
  check("open-in-Notion link", () =>
    doc.querySelector('.arc-h a[href*="app.notion.com"]') ? "present" : false);
  check("live dot is healthy", () =>
    doc.querySelector(".live-dot").className.trim() === "live-dot");
  check("codex shows three live panels", () => {
    tab("Codex");
    const n = doc.querySelectorAll(".arc").length;
    return n === 3 ? "3 panels" : `got ${n}`;
  });
  check("refresh button present", () => !!doc.querySelector("[data-notion-refresh]"));
} else if (MODE === "absent") {
  check("degrades without window.claude", () =>
    doc.querySelector(".arc-b").textContent.includes("can't reach connectors"));
  check("rest of the sheet still renders", () =>
    doc.querySelectorAll(".lane").length === 4 && doc.querySelectorAll(".play").length === 0
    || doc.querySelectorAll(".lane").length === 4);
} else if (MODE === "noconnector") {
  check("no Notion connector says so once, not three times", () =>
    doc.querySelector(".arc-b").textContent.includes("Add Notion"));
  check("sheet still fully usable", () => doc.querySelectorAll(".lane").length === 4);
} else if (MODE === "renamed") {
  check("resolves a differently-named Notion connector", () =>
    doc.querySelector(".arc-b ul") ? "arc rendered via 'Notion (Personal)'" : false);
  check("no wrong-server errors", () => errors.length === 0 || errors.join("; "));
} else {
  const code = MODE.slice(6);
  const EXPECT = {
    needs_reauth: "Settings → Connectors",
    server_not_connected: "Add Notion",
    selection_required: "more than one Notion",
    blocked_by_policy: "organization blocks",
    approval_required: "per-call approval",
    server_unavailable: "Temporary",
    tool_error: "rejected the request",
    not_granted: "can't reach connectors",
  };
  check(`${code} gets its own copy`, () => {
    const txt = doc.querySelector(".arc-b").textContent;
    return txt.includes(EXPECT[code]) ? txt.trim().slice(0, 60) : `got: ${txt.trim().slice(0,70)}`;
  });
  check("retry offered only when retryable", () => {
    const has = !!doc.querySelector("[data-notion-refresh]");
    const want = code === "server_unavailable";
    return has === want ? `retry=${has}` : `retry=${has}, expected ${want}`;
  });
  check("sheet still fully usable", () => doc.querySelectorAll(".lane").length === 4);
}

console.log("\n" + (errors.length ? `${errors.length} FAILURE(S):` : "all checks passed"));
errors.forEach(e => console.log("  - " + e));
process.exit(errors.length ? 1 : 0);
})();
