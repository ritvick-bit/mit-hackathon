// Run: node contractor/model.test.js
const assert = require("assert");
const cc = require("../command-center/data.js");
const db = require("./db.js");
const M = require("./model.js");

const fresh = () => M.seed(cc, db);
let s = fresh();
let sch = M.schedule(s);

// Seed: one 12-step timeline per command-center job, past work recorded as done.
assert.strictEqual(s.projects.length, cc.jobs.length);
assert.strictEqual(s.tasks.length, cc.jobs.length * M.TEMPLATE.length);
assert.ok(s.tasks.filter((t) => t.key === "pad_pour" && t.planned_start < s.today).every((t) => t.status === "done"));
assert.ok(s.tasks.filter((t) => t.key === "energize").every((t) => t.status === "open"));
assert.strictEqual(M.task(s, "T-JOB-003-shutdown").status, "open", "JOB-003 shutdown is not approved in the command-center seed");
// Command-center crews map to electrical companies.
assert.strictEqual(M.task(s, "T-JOB-001-electrical").owner_id, "EL-HARBOR");
// JOB-001's equipment arrives after install (command-center case 1), so it is the one project behind target.
assert.deepStrictEqual(s.projects.filter((p) => sch.projects[p.id].slip_days > 0).map((p) => p.id), ["JOB-001"]);
// Every task starts after its predecessors finish.
s.tasks.forEach((t) => t.preds.forEach((id) => assert.ok(sch.tasks[id].finish < sch.tasks[t.id].start, `${t.id} starts before ${id} ends`)));

// Contractor sees only their tasks; waiting tasks name what they wait on.
const crane = M.tasksFor(s, "CR-BAY", sch);
assert.ok(crane.length && crane.every((x) => x.task.owner_id === "CR-BAY"));
assert.throws(() => M.completeTask(s, "T-JOB-005-placement", "CR-BAY"), /Waiting on: Deliver battery cabinets/);
assert.throws(() => M.completeTask(s, "T-JOB-002-placement", "CR-WORC"), /not assigned to you/);

// Done: the task records today and the timeline and log update.
let r = M.completeTask(s, "T-JOB-002-placement", "CR-BAY");
assert.strictEqual(M.task(r.state, "T-JOB-002-placement").status, "done");
assert.strictEqual(M.task(r.state, "T-JOB-002-placement").actual_finish, s.today);
assert.match(r.state.log.slice(-1)[0].text, /Bay Crane & Rigging marked "Set cabinets on pad \(crane lift\)" done for JOB-002/);
assert.strictEqual(M.task(s, "T-JOB-002-placement").status, "open", "actions do not mutate the input state");
s = r.state;

// Resource search: same trade, same state, not the reporter, within range, free on the needed days.
const req = { mode: "replace", trade: "crane", days: 1, from: "2026-11-09" };
let options = M.searchResources(s, "T-JOB-005-placement", req);
assert.ok(options.length >= 1);
options.forEach((o) => {
  const c = M.company(s, o.company_id);
  assert.strictEqual(c.trade, "crane"); assert.strictEqual(c.state, "MA"); assert.notStrictEqual(c.id, "CR-BAY");
  assert.ok(o.distance_mi <= c.radius_mi);
  c.bookings.forEach((b) => assert.ok(o.finish < b.start || o.start > b.end, `${c.id} is booked on ${o.start}`));
});
assert.strictEqual(options[0].company_id, "CR-WORC");
assert.strictEqual(options[0].start, "2026-11-16", "Worcester Rigging is booked Nov 10-13 and needs a day to mobilize");
assert.ok(options[0].go_live_change_days > 0);

// Report with a resource request; the task is flagged until the PM decides.
assert.throws(() => M.fileReport(s, { task_id: "T-JOB-005-placement", by: "CR-BAY", details: "", urgency: 2 }), /Describe the problem/);
assert.throws(() => M.fileReport(s, { task_id: "T-JOB-005-placement", by: "CR-BAY", details: "x" }), /urgency/);
r = M.fileReport(s, { task_id: "T-JOB-005-placement", by: "CR-BAY", details: "Crane failed inspection.", urgency: 2, resource: req, photos: ["/contractor/data/uploads/a.jpg"] });
s = r.state;
const rep = r.result;
assert.strictEqual(rep.id, "R-001"); assert.strictEqual(rep.no_resource, false); assert.strictEqual(rep.status, "pending");
assert.strictEqual(M.task(s, "T-JOB-005-placement").problem, "R-001");
assert.strictEqual(M.taskState(s, M.task(s, "T-JOB-005-placement")).state, "problem");
assert.throws(() => M.fileReport(s, { task_id: "T-JOB-005-placement", by: "CR-BAY", details: "again", urgency: 3 }), /already an open report/);

// PM approval: the new company owns the task, downstream dates move, everyone affected is told.
const goBefore = M.schedule(s).projects["JOB-005"].go_live;
r = M.approve(s, "R-001", rep.options[0].id, "Jordan Lee");
s = r.state;
const placed = M.task(s, "T-JOB-005-placement");
assert.strictEqual(placed.owner_id, "CR-WORC"); assert.strictEqual(placed.problem, null);
assert.strictEqual(M.schedule(s).tasks[placed.id].start, "2026-11-16");
assert.strictEqual(M.schedule(s).projects["JOB-005"].go_live, rep.options[0].go_live);
assert.ok(M.schedule(s).projects["JOB-005"].go_live > goBefore);
assert.ok(M.tasksFor(s, "CR-WORC").some((x) => x.task.id === placed.id), "approved task is on the new company's dashboard");
assert.ok(!M.tasksFor(s, "CR-BAY").some((x) => x.task.id === placed.id));
const notes = (owner) => s.notices.filter((n) => n.owner === owner).map((n) => n.text).join(" | ");
assert.match(notes("CR-WORC"), /New task assigned: Set cabinets on pad \(crane lift\), Nov 16 \(taken over from Bay Crane & Rigging\)/);
assert.match(notes("CR-BAY"), /reassigned to Worcester Rigging Co\./);
assert.match(notes(M.task(s, "T-JOB-005-electrical").owner_id), /Electrical installation moved/);
assert.match(notes("IN-MA"), /moved/);
assert.throws(() => M.approve(s, "R-001", rep.options[0].id, "Jordan Lee"), /not waiting/);

// "Before" mode adds a new task for the new company ahead of the reported one.
r = M.fileReport(s, { task_id: "T-JOB-021-electrical", by: "EL-CVALLEY", details: "Pad is cracked at the anchor bolts.", urgency: 1, resource: { mode: "before", trade: "civil", days: 2, from: "2026-11-10", work: "Repair pad anchors" } });
s = r.state;
r = M.approve(s, r.result.id, r.result.options[0].id, "Jordan Lee");
s = r.state;
const added = s.tasks.find((t) => t.key === "added" && t.project_id === "JOB-021");
assert.ok(added && added.name === "Repair pad anchors" && added.owner_id !== "EL-CVALLEY");
assert.ok(M.task(s, "T-JOB-021-electrical").preds.includes(added.id));
assert.ok(M.schedule(s).tasks["T-JOB-021-electrical"].start > M.schedule(s).tasks[added.id].finish);
assert.strictEqual(M.task(s, "T-JOB-021-electrical").owner_id, "EL-CVALLEY", "original contractor keeps their task");

// No company available: report is flagged urgent for the PM, nothing to approve.
r = M.fileReport(s, { task_id: "T-JOB-010-delivery", by: "FR-WCHH", details: "Trailer damaged.", urgency: 1, resource: { mode: "replace", trade: "freight", days: 1, from: "2026-11-10" } });
s = r.state;
assert.strictEqual(r.result.no_resource, true);
assert.strictEqual(r.result.options.length, 0);
assert.match(M.ruleSummary(s, r.result), /no available company found in CA/);
r = M.decline(s, r.result.id, "Jordan Lee", "Calling the supplier to ship direct");
s = r.state;
assert.strictEqual(s.reports.find((x) => x.id === r.result.id).status, "declined");
assert.strictEqual(M.task(s, "T-JOB-010-delivery").problem, null);
assert.match(notes("FR-WCHH"), /PM declined report R-003: Calling the supplier/);

// A report without a resource request is acknowledged.
r = M.fileReport(s, { task_id: "T-JOB-007-pto", by: "UT-NGRID", details: "Witness test needs a new date.", urgency: 4 });
assert.strictEqual(r.result.resource, null);
s = M.decline(r.state, r.result.id, "Jordan Lee").state;
assert.strictEqual(s.reports.slice(-1)[0].status, "acknowledged");

console.log("contractor model tests passed");
