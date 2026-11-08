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

// Procurement: every project gets products; JOB-003's supplier delay shows on its battery cabinets.
assert.ok(S.projects.every((p) => p.products.length === D.PRODUCTS.length));
const cab3 = P("JOB-003").products.find((x) => x.key === "cabinets");
assert.strictEqual(P("JOB-003").product_states[cab3.id].key, "delayed");
assert.ok(P("JOB-003").product_states[cab3.id].red && P("JOB-003").todos.some((x) => x.kind === "product" && x.product === cab3));
assert.ok(P("JOB-001").products.filter((x) => x.key === "cabinets" || x.key === "inverter").every((x) => M.productRank(x) >= 5), "JOB-001 is past placement");
// Every product has its purchase order and delivery receipt in the document list, and deliveries are on the calendar.
S.projects.forEach((p) => p.products.forEach((pr) => assert.strictEqual(p.docs.filter((d) => d.product_id === pr.id && /^(Purchase order|Bill of lading)/.test(d.name)).length, 2)));
assert.ok(M.calendarItems(S, P("JOB-003")).some((x) => x.kind === "delivery" && x.product_id === cab3.id && x.date === cab3.expected_date && x.state === "late"));

// The PM's edits: a late delivery holds back the step that needs it and turns the project red.
const p8 = P("JOB-008");
assert.strictEqual(p8.slip, 0);
const products8 = JSON.parse(JSON.stringify(p8.products));
const pl = p8.tasks.find((t) => t.key === "placement");
const late = M.addDays(S.cal.date(pl.fc.s), 21);
Object.assign(products8.find((x) => x.key === "cabinets"), { status: "Shipped", delivered_date: "", expected_date: late });
products8.push({ id: "JOB-008:p:c1", name: "Step-up transformer", category: "Transformer", supplier_id: "X-1", quantity: 1, unit: "unit", needed_for: "tie_in", status: "Ordered", promised_date: "", expected_date: "", order_date: "", delivered_date: "", custom: true });
const ov = {
  seq: 1, companies: { "X-1": { id: "X-1", name: "Granite State Transformer", trade: "supplier", contact: "Lee Park", email: "lee@granite.demo.example" } },
  company_edits: { "EL-SOMER": { phone: "(617) 555-0100" } },
  projects: { "JOB-008": {
    products: products8,
    owners: { tie_in: "EL-NSHORE" },
    contractors_added: ["CV-MERRI"],
    doc_edits: { "JOB-008:interconnection:doc1": { status: "complete", completed_date: "2026-11-09" } },
    docs_added: [{ id: "JOB-008:doc:c2", name: "Lien waiver", step: "civil", next_id: "CV-COMMON", status: "waiting", due_date: "2026-11-20" }],
    docs_removed: ["JOB-008:civil:doc0"],
  } },
};
const S2 = M.build(D, "2026-11-09", ov), q8 = S2.projects.find((p) => p.id === "JOB-008");
const pl2 = q8.tasks.find((t) => t.key === "placement");
assert.ok(pl2.fc.s > S2.cal.index(late), "placement waits for the late cabinets");
assert.ok(q8.slip > 0 && q8.status === "red" && /now expected/.test(q8.status_text));
assert.strictEqual(q8.product_states["JOB-008:p:cabinets"].key, "delayed");
assert.ok(q8.products.some((x) => x.id === "JOB-008:p:c1") && S2.byCompany["X-1"].name === "Granite State Transformer");
assert.strictEqual(S2.byCompany["EL-SOMER"].phone, "(617) 555-0100");
assert.strictEqual(q8.tasks.find((t) => t.key === "tie_in").owner_id, "EL-NSHORE");
assert.strictEqual(q8.docs.find((d) => d.key === undefined && d.name === "Switching procedure").flow[0].id, "EL-NSHORE", "paperwork follows the new owner");
const subs8 = M.subcontractors(S2, q8);
assert.ok(subs8.some((x) => x.company.id === "CV-MERRI" && x.added && !x.tasks.length));
assert.ok(subs8.some((x) => x.company.id === "EL-NSHORE" && x.tasks.some((t) => t.task.key === "tie_in")));
assert.strictEqual(q8.docs.find((d) => d.id === "JOB-008:interconnection:doc1").status, "complete");
assert.ok(!q8.todos.some((x) => x.doc && x.doc.id === "JOB-008:interconnection:doc1"));
const lien = q8.docs.find((d) => d.id === "JOB-008:doc:c2");
assert.ok(lien && lien.status === "waiting" && lien.next.id === "CV-COMMON" && lien.due === S2.cal.index("2026-11-20"));
assert.ok(!q8.docs.some((d) => d.id === "JOB-008:civil:doc0"));
// Edits for one project leave the others alone.
assert.deepStrictEqual(S2.projects.filter((p) => p.status === "red").map((p) => p.id).sort(), red.concat("JOB-008").sort());

// Document center seed plan: Yichang's 20 documents plus each product's paperwork, dated from the timeline.
const plan3 = M.paperPlan(S, P("JOB-003"));
assert.strictEqual(plan3.pm_id, "PM-JORDAN");
assert.deepStrictEqual(plan3.documents.slice(0, 20).map((d) => d.id), Object.keys(D.DOC_MAP));
const at3 = Object.fromEntries(plan3.documents.map((d) => [d.id, d]));
Object.entries(D.DOC_PREREQS).forEach(([id, pre]) => pre.forEach((q) => assert.ok(at3[q].due_at <= at3[id].due_at, `${id} is due before its prerequisite ${q}`)));
plan3.documents.filter((d) => d.completed_at).forEach((d) => assert.ok(d.completed_at < S.cal.today));
assert.ok(at3.D01.completed_at && !at3.D20.completed_at, "contract paperwork done, handover not yet");
assert.ok(P("JOB-003").products.every((pr) => plan3.documents.some((d) => d.product_id === pr.id && /^Purchase order/.test(d.title))));
assert.strictEqual(plan3.stakeholders.supplier.company_id, "SU-QPACK");
// A reported problem leaves that step's paperwork returned.
const plan4 = M.paperPlan(S, P("JOB-004"));
assert.ok(plan4.documents.some((d) => d.step === "final_insp" && d.opening === "returned" && /Fire marshal/.test(d.opening_text)));

// Converting the document center's feed: statuses, who is next, and the PM's to-dos.
const feed = { version: 3, projects: { "JOB-008": {
  status: "active",
  stakeholders: [{ id: "PM-JORDAN", name: "Jordan Lee" }, { id: "JOB-008__supplier", name: "Elena Marsh", organization: "QorePack", company_id: "SU-QPACK" },
                 { id: "JOB-008__commercial", name: "Morgan Chen", organization: "EQORE" }],
  documents: [
    { id: "D11", title: "Supplier order acceptance", kind: "esign", phase: "Reviews and procurement", status: "partially_signed", owner_id: "PM-JORDAN", due_at: "2026-11-12T17:00:00-05:00", revision: 1, step: "procurement",
      next_action: { title: "Follow up on Supplier order acceptance", reason: "Waiting for Elena Marsh on revision 1." },
      recipients: [{ id: "JOB-008__commercial", status: "signed", signed_at: "2026-11-05T17:00:00-05:00" }, { id: "JOB-008__supplier", status: "pending" }], signed_history: [] },
    { id: "D12", title: "EPC and electrical scope agreement", kind: "esign", phase: "Reviews and procurement", status: "ready", owner_id: "PM-JORDAN", due_at: "2026-11-10T17:00:00-05:00", revision: 1, step: "procurement",
      next_action: { title: "Prepare EPC and electrical scope agreement", reason: "Its current prerequisite records are complete." }, recipients: [{ id: "JOB-008__commercial", status: "pending" }], signed_history: [] },
    { id: "D20", title: "Customer and fleet handoff acceptance", kind: "esign", phase: "Handoff", status: "blocked", owner_id: "PM-JORDAN", due_at: "2027-01-20T17:00:00-05:00", revision: 1, step: "energize", recipients: [], signed_history: [] },
    { id: "P-cabinets-po", title: "Purchase order: Battery cabinets", kind: "esign", phase: "Procurement", status: "completed", owner_id: "PM-JORDAN", due_at: "2026-09-01T17:00:00-05:00", revision: 1, step: "procurement", product_id: "JOB-008:p:cabinets",
      recipients: [{ id: "JOB-008__supplier", status: "signed", signed_at: "2026-09-01T17:00:00-05:00" }], signed_history: [] },
  ] } } };
const S3 = M.build(D, "2026-11-09", {}, feed), p8b = S3.projects.find((p) => p.id === "JOB-008");
const byId = Object.fromEntries(p8b.docs.map((d) => [d.id, d]));
assert.strictEqual(p8b.docs.length, 4, "the feed replaces the generated documents");
assert.strictEqual(byId.D11.status, "waiting"); assert.strictEqual(byId.D11.next.id, "SU-QPACK"); assert.strictEqual(byId.D11.next.label, "Contractor");
assert.strictEqual(byId.D11.history[0].by, "JOB-008__commercial", "an EQORE contact without a company becomes its own party");
assert.strictEqual(byId.D12.next.label, "PM"); assert.strictEqual(byId.D20.status, "not_started"); assert.strictEqual(byId["P-cabinets-po"].status, "complete");
assert.ok(p8b.todos.some((x) => x.kind === "doc" && x.title === "Prepare EPC and electrical scope agreement" && x.urgency === 2));
assert.ok(M.subcontractors(S3, p8b).find((x) => x.company.id === "SU-QPACK").docs.some((d) => d.id === "D11"));
assert.strictEqual(p8b.docs.filter((d) => d.product_id === "JOB-008:p:cabinets").length, 1);

console.log("pm model tests passed", JSON.stringify(counts));
