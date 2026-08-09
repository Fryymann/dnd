#!/usr/bin/env node
// Runs every suite against dist/toki.html. The content suite runs once per
// connector state so the degraded paths are covered, not just the happy one.
const { execFileSync } = require("child_process");
const { existsSync } = require("fs");
const path = require("path");

const dist = path.join(__dirname, "..", "dist", "toki.html");
if (!existsSync(dist)) {
  console.error("dist/toki.html not found — run `npm run build` first.");
  process.exit(1);
}

const MODES = ["ok", "renamed", "noconnector", "absent", "error:needs_reauth",
  "error:server_not_connected", "error:selection_required", "error:blocked_by_policy",
  "error:approval_required", "error:server_unavailable", "error:tool_error",
  "error:not_granted"];

const runs = [
  ["shell.test.js", []], ["dice.test.js", []], ["hp.test.js", []],
  ...MODES.map(m => ["content.test.js", [m]]),
];

let failed = 0;
for (const [file, args] of runs) {
  const label = `${file.replace(".test.js", "")}${args.length ? ` [${args[0]}]` : ""}`;
  try {
    const out = execFileSync("node", [path.join(__dirname, file), dist, ...args],
      { encoding: "utf8" });
    const passed = (out.match(/^ {2}ok/gm) || []).length;
    console.log(`ok    ${label.padEnd(34)} ${passed} checks`);
  } catch (e) {
    failed++;
    console.log(`FAIL  ${label}`);
    const out = (e.stdout || "") + (e.stderr || "");
    out.split("\n").filter(l => /FAIL|FAILURE|^ {2}- /.test(l)).forEach(l => console.log("      " + l));
  }
}
console.log(failed ? `\n${failed} suite(s) failed` : "\nall suites passed");
process.exit(failed ? 1 : 0);
