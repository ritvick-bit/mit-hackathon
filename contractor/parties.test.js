// Run: node contractor/parties.test.js
const assert = require("assert");
const seed = require("../command-center/data.js");
const EQ = require("../command-center/engine.js");
const C = require("./parties.js");

const fresh = () => EQ.clone(seed);
const open = (s, id) => C.obligations(s, id).filter((i) => i.open);

// Every crew, vendor, inspector, utility, permit office and facility is a party.
let s = fresh();
const ids = C.parties(s).map((p) => p.id);
["crew:CREW-A", "vendor:Demo Vendor", "inspector:fire|MA", "utility:Eversource", "ahj:Fall River, MA", "facility:SITE-003"].forEach((id) => assert.ok(ids.includes(id), id));

// Each job's install, delivery, inspection, shutdown and utility item belongs to exactly one party.
const all = C.parties(s).flatMap((p) => C.obligations(s, p.id));
["install", "delivery", "inspection", "shutdown", "utility"].forEach((k) => assert.strictEqual(all.filter((i) => i.kind === k).length, s.jobs.length, k));
assert.strictEqual(all.filter((i) => i.kind === "permit").length, s.jobs.length * 3);

// What each party is holding up matches the PM board's blockers from the brief.
const blocking = (id) => open(s, id).filter((i) => i.blocking).map((i) => i.job_id).sort();
assert.deepStrictEqual(blocking("crew:CREW-A"), ["JOB-001", "JOB-002"]);
assert.deepStrictEqual(blocking("vendor:Demo Vendor"), ["JOB-001", "JOB-010"]);
assert.deepStrictEqual(blocking("facility:SITE-003"), ["JOB-003"]);
assert.deepStrictEqual(blocking("facility:SITE-017"), ["JOB-017"]);
assert.deepStrictEqual(blocking("inspector:fire|MA"), ["JOB-006", "JOB-023"]);
assert.deepStrictEqual(blocking("utility:Eversource"), ["JOB-013"]);
assert.deepStrictEqual(blocking("ahj:Fall River, MA"), ["JOB-008"]);
// Hard blockers sort first.
assert.strictEqual(C.obligations(s, "crew:CREW-A")[0].hard, true);

// Crew delay: the job moves, its shutdown needs re-approval, and the inspector's booking is now too early.
let r = C.impact(s, "crew:CREW-C", "Crew C", { item_id: "install:JOB-016", type: "delay", date: "2026-11-25" });
assert.strictEqual(s.jobs.find((j) => j.job_id === "JOB-016").install_date, "2026-11-18", "impact must not mutate input");
assert.deepStrictEqual(r.changes.map((c) => [c.job_id, c.from, c.to]), [["JOB-016", "green", "amber"]]);
assert.deepStrictEqual(r.others.map((o) => o.party).sort(), ["Demo Manufacturing Co. (Taunton)", "Wiring inspector (MA)"]);
assert.strictEqual(r.state.log.slice(-1)[0].text, "[Crew C] Can't make JOB-016 on Nov 18; earliest Nov 25.");

// Vendor delay past install turns a green job red.
r = C.impact(s, "vendor:Demo Vendor", "Demo Vendor", { item_id: "delivery:SHIP-005", type: "delay", date: "2026-11-20" });
assert.deepStrictEqual(r.changes.map((c) => [c.job_id, c.from, c.to]), [["JOB-005", "green", "red"]]);

// Facility approves JOB-003's shutdown: that blocker clears.
r = C.impact(s, "facility:SITE-003", "Facility", { item_id: "shutdown:SHUT-003", type: "approve" });
assert.ok(!r.changes[0].after || !/Shutdown/.test(r.changes[0].after));
assert.strictEqual(open(r.state, "facility:SITE-003").length, 0);

// Inspector fixes JOB-023's wrong-order booking; JOB-006's fire inspection gets booked.
s = C.impact(s, "inspector:fire|MA", "Fire marshal", { item_id: "inspection:INSP-023", type: "reschedule", date: "2026-11-23" }).state;
s = C.impact(s, "inspector:fire|MA", "Fire marshal", { item_id: "inspection:INSP-006", type: "book", date: "2026-11-13" }).state;
assert.deepStrictEqual(blocking("inspector:fire|MA"), []);
let ev = EQ.evaluate(s, true);
assert.strictEqual(ev.byJob["JOB-023"].readiness, "green");
assert.strictEqual(ev.byJob["JOB-006"].readiness, "green");

// A failed inspection reopens the item and needs rebooking.
s = C.impact(s, "inspector:fire|MA", "Fire marshal", { item_id: "inspection:INSP-006", type: "fail" }).state;
assert.strictEqual(C.obligations(s, "inspector:fire|MA").find((i) => i.job_id === "JOB-006").state, "Failed, needs rebooking");

// Utility, permit office and delivery actions clear their blockers.
s = C.impact(s, "utility:Eversource", "Eversource", { item_id: "utility:JOB-013", type: "grant" }).state;
s = C.impact(s, "ahj:Fall River, MA", "Fall River", { item_id: "permit:JOB-008:building", type: "approve" }).state;
ev = EQ.evaluate(s, true);
assert.strictEqual(ev.byJob["JOB-013"].readiness, "green");
assert.strictEqual(ev.byJob["JOB-008"].readiness, "green");

// Date-taking actions refuse to run without a date.
assert.throws(() => C.apply(fresh(), "x", { item_id: "install:JOB-001", type: "delay" }), /date is required/);

console.log("contractor tests passed");
