// Run: node engine.test.js
const assert = require("assert");
const seed = require("./data.js");
const EQ = require("./engine.js");

const S = EQ.clone(seed);
let ev = EQ.evaluate(S);
const band = (id) => ev.byJob[id].readiness;

// 25 jobs: 3 red, 6 amber, 16 green
const counts = EQ.metrics(S, ev).counts;
console.log("counts", counts);
assert.deepStrictEqual(counts, { red: 3, amber: 6, green: 16 });

// Blockers match the brief
assert.strictEqual(ev.byJob["JOB-001"].blocker, "Equipment arrives Nov 12, install is Nov 10");
assert.strictEqual(ev.byJob["JOB-002"].blocker, "Crew A is booked in Boston and Worcester on Nov 10");
assert.strictEqual(ev.byJob["JOB-003"].blocker, "Shutdown window not approved by the facility, install cannot start");
assert.strictEqual(ev.byJob["JOB-006"].blocker, "Fire inspection not yet booked");
assert.strictEqual(ev.byJob["JOB-008"].blocker, "Permit revision, round 2");
assert.strictEqual(ev.byJob["JOB-010"].blocker, "Equipment delivery Nov 14, install Nov 14, no buffer");
assert.strictEqual(ev.byJob["JOB-013"].blocker, "Utility PTO pending (Eversource)");
assert.strictEqual(ev.byJob["JOB-017"].blocker, "Shutdown window requested, not approved");
assert.match(ev.byJob["JOB-023"].blocker, /wrong order/);

// Case 2: reschedule JOB-001
const sg = EQ.suggest(S, "JOB-001", ev);
console.log("JOB-001 suggestion:", sg.text, sg.reasons);
assert.strictEqual(sg.change.install_date, "2026-11-13");
assert.strictEqual(sg.delay_days, 3);
assert.strictEqual(sg.cost, 321);
const pv = EQ.preview(S, "JOB-001", sg.change);
console.log("cascade:", pv.diff.map((d) => `${d.job_id} ${d.from}->${d.to}`).join(", "));
assert.ok(pv.diff.some((d) => d.job_id === "JOB-001" && d.to === "green"));
assert.ok(pv.diff.some((d) => d.job_id === "JOB-002" && d.to === "green")); // clears the double-booking too
EQ.applyChange(S, "JOB-001", sg.change);
ev = EQ.evaluate(S);
assert.strictEqual(band("JOB-001"), "green");
assert.strictEqual(band("JOB-002"), "green");

// Case 3: JOB-003 is a hold, not a reschedule
const h = EQ.suggest(S, "JOB-003", ev);
assert.strictEqual(h.kind, "hold");
EQ.applyChange(S, "JOB-003", { shutdown_requested: true });
ev = EQ.evaluate(S);
assert.strictEqual(band("JOB-003"), "amber");
EQ.applyChange(S, "JOB-003", { shutdown_approved: true });
ev = EQ.evaluate(S);
assert.strictEqual(band("JOB-003"), "green");

// Case 1 before fixing: JOB-002 is a cascade suggestion
const S2 = EQ.clone(seed);
const c = EQ.suggest(S2, "JOB-002");
assert.strictEqual(c.kind, "cascade");
console.log("JOB-002:", c.text);

// Conflicts have fixes
const all = EQ.evaluate(S2).conflicts;
console.log(all.length, "conflicts/at-risk flags");
assert.ok(all.every((x) => x.suggested_fix));

// Weekend / what-if: moving JOB-002 onto Crew A's Nov 12 job double-books
const wi = EQ.preview(S2, "JOB-002", { install_date: "2026-11-12", crew_id: "CREW-A" });
assert.ok(wi.diff.some((d) => d.job_id === "JOB-006"));
console.log("ALL TESTS PASSED");
