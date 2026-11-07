// Run: node pm/model.test.js
const assert = require("assert");
const D = require("./data.js");
const M = require("./model.js");

const S = M.build(D, "2026-11-09"); // a Monday
const P = (id) => S.projects.find((p) => p.id === id);

// Every project gets the full template; each PM sees only their own portfolio.
assert.strictEqual(S.tasks.length, D.PROJECTS.length * D.TEMPLATE.length);
assert.ok(D.PROJECTS.length >= 30 && D.PROJECTS.length <= 50, "30-50 projects per the challenge brief");
const jordan = M.portfolio(S, "PM-JORDAN");
assert.ok(jordan.length > 0 && jordan.every((p) => p.pm_id === "PM-JORDAN"));
assert.strictEqual(D.PMS.reduce((n, pm) => n + M.portfolio(S, pm.id).length, 0), S.projects.length);

// Forecast: every open task starts after its predecessors finish, and nothing new starts in the past.
S.tasks.forEach((t) => t.preds.forEach((id) => assert.ok(S.byTask[id].fc.f < t.fc.s, `${t.id} starts before ${id} ends`)));
S.tasks.filter((t) => !t.done && !t.started).forEach((t) => assert.ok(t.fc.s >= 0, `${t.id} starts in the past`));

// Status colours: red = a reported delay that moves go-live; green projects have no urgent PM action.
const red = S.projects.filter((p) => p.status === "red").map((p) => p.id).sort();
assert.deepStrictEqual(red, ["JOB-003", "JOB-004", "JOB-011", "JOB-017", "JOB-020", "JOB-026", "JOB-033", "JOB-036"]);
red.forEach((id) => assert.ok(P(id).slip > 0 && P(id).issues.length));
S.projects.filter((p) => p.status !== "red").forEach((p) => assert.strictEqual(p.slip, 0));
S.projects.filter((p) => p.status === "green").forEach((p) => assert.ok(!p.todos.some((x) => x.urgency <= 2 && x.kind !== "chase")));
S.projects.filter((p) => p.status === "yellow").forEach((p) => assert.ok(p.todos.some((x) => x.urgency <= 2)));
const counts = { green: 0, yellow: 0, red: 0 };
S.projects.forEach((p) => counts[p.status]++);
assert.ok(counts.green > 0 && counts.yellow > 0, JSON.stringify(counts));

// Slack absorbs a small delay: JOB-023's interconnection delay is reported but go-live holds.
assert.strictEqual(P("JOB-023").issues.length, 1);
assert.strictEqual(P("JOB-023").slip, 0);
// The supplier delay on JOB-003 pushes the whole construction sequence by its length.
assert.strictEqual(P("JOB-003").slip, 15);
assert.strictEqual(M.taskState(S.byTask["JOB-003:procurement"]), "problem");
assert.strictEqual(M.taskState(S.byTask["JOB-003:civil"]), "late");

// Subcontractors: a company's own reported delay is flagged; tasks pushed by someone else's delay are not "delayed".
const subs3 = M.subcontractors(S, P("JOB-003"));
assert.deepStrictEqual(subs3.filter((x) => x.delayed.length).map((x) => x.company.id), [S.byTask["JOB-003:procurement"].owner_id]);
assert.ok(subs3.some((x) => x.pushed.length));
assert.ok(subs3.every((x) => !["eqore", "customer"].includes(x.company.trade)));

// Paperwork: complete docs have a full signing history; waiting docs say who is next.
const docs = S.projects.flatMap((p) => p.docs);
docs.filter((d) => d.status === "complete").forEach((d) => assert.strictEqual(d.history.length, d.flow.length));
docs.filter((d) => d.status === "waiting").forEach((d) => assert.ok(d.next && d.due != null));
// To-do: issues first, then by urgency and due date.
S.projects.forEach((p) => p.todos.forEach((x, i) => i && assert.ok(p.todos[i - 1].urgency <= x.urgency)));

// Demo inbox: one paperwork email per document waiting on the PM, with a department.
const inbox = M.demoInbox(S, jordan);
assert.strictEqual(inbox.length, jordan.flatMap((p) => p.docs).filter((d) => d.status === "waiting" && d.next.label === "PM").length);
assert.ok(inbox.every((m) => m.department && m.subject.includes(m.project_id) && /\.demo\.example$/.test(m.from_email)));

// Calendar: sorted, and the shared meetings land on work days.
const items = M.calendarItems(S);
items.forEach((x, i) => i && assert.ok(items[i - 1].date <= x.date));
items.filter((x) => x.kind === "meeting" && !x.project_id).forEach((x) => assert.ok(M.isWorkday(x.date)));

// Contractor database: filters by job type, task and name; availability respects bookings and crew count.
const cranes = M.searchCompanies(S, { trade: "crane", state: "MA" }, P("JOB-003"));
assert.ok(cranes.length && cranes.every((r) => r.company.trade === "crane" && r.company.state === "MA"));
assert.deepStrictEqual(M.searchCompanies(S, { step: "placement" }).map((r) => r.company.trade).filter((t, i, a) => a.indexOf(t) === i), ["crane"]);
assert.deepStrictEqual(M.searchCompanies(S, { name: "worcester rig" }).map((r) => r.company.id), ["CR-WORC"]);
const worc = M.earliestFree(S, "CR-WORC", 0, 1);
M.busy(S, "CR-WORC").forEach((b) => assert.ok(!(b.s <= worc && worc <= b.f) || S.byCompany["CR-WORC"].crews > 1));
assert.ok(M.searchCompanies(S, { trade: "crane", from: 1, to: 1, days: 1, only_available: true }).every((r) => r.available && r.free === 1));

console.log("pm model tests passed", JSON.stringify(counts));
