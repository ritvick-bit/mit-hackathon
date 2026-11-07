// EQORE contractor view: who owes what across all jobs, and what each party can do about it.
// Pure functions over the command-center state (see ../command-center/data.js).
// Uses EQORE (../command-center/engine.js) for readiness. Works in the browser and in Node.
(function (root) {
  const EQ = root.EQORE || (typeof require !== "undefined" ? require("../command-center/engine.js") : null);
  const { fmt, clone } = EQ;

  // Which readiness check each kind of obligation feeds.
  const CHECK = { install: "crew", delivery: "equipment", inspection: "inspection", shutdown: "shutdown", utility: "utility", permit: "permits" };
  const PERMIT_OFFICE = { building: "Building dept", electrical: "Wiring inspector", fire: "Fire marshal" };

  const siteOf = (s, j) => s.sites.find((x) => x.site_id === j.site_id);
  const jobOf = (s, id) => s.jobs.find((j) => j.job_id === id);

  // ---------- Parties ----------
  function parties(s) {
    const out = [];
    s.crews.forEach((c) => out.push({ id: "crew:" + c.crew_id, group: "Install crews", name: `${c.name} (${c.base_city})` }));
    [...new Set(s.shipments.map((x) => x.vendor))].sort().forEach((v) => out.push({ id: "vendor:" + v, group: "Equipment suppliers", name: v }));
    const insp = new Set();
    s.inspections.forEach((i) => { const j = jobOf(s, i.job_id); insp.add(i.type + "|" + siteOf(s, j).state); });
    [...insp].sort().forEach((k) => { const [t, st] = k.split("|"); out.push({ id: "inspector:" + k, group: "Inspectors", name: `${t === "fire" ? "Fire marshal" : "Wiring inspector"} (${st})` }); });
    [...new Set(s.sites.map((x) => x.utility))].sort().forEach((u) => out.push({ id: "utility:" + u, group: "Utilities", name: u }));
    [...new Set(s.sites.map((x) => x.city + ", " + x.state))].sort().forEach((c) => out.push({ id: "ahj:" + c, group: "Permit offices (AHJ)", name: `${c} permit office` }));
    s.sites.slice().sort((a, b) => a.name.localeCompare(b.name)).forEach((x) => out.push({ id: "facility:" + x.site_id, group: "Customer facilities", name: x.name }));
    return out;
  }

  // ---------- Obligations ----------
  // Every item a party owes on any job, open or done, with whether it is holding the install up right now.
  function obligations(s, partyId, ev) {
    ev = ev || EQ.evaluate(s, true);
    const [kind, ...rest] = partyId.split(":");
    const key = rest.join(":");
    const items = [];
    const push = (j, o) => {
      const r = ev.byJob[j.job_id];
      const check = r.checks.find((c) => c.key === CHECK[o.kind]);
      const blocking = !!check && check.status !== "ok" && o.open;
      const site = siteOf(s, j);
      items.push(Object.assign({
        job_id: j.job_id, site: site.name, city: site.city, state: site.state, install_date: j.install_date,
        readiness: r.readiness, blocking, hard: blocking && check.hard, issue: blocking ? check.message : null,
        cost_per_day: j.cost_of_delay_usd_per_day,
      }, o));
    };

    s.jobs.forEach((j) => {
      const site = siteOf(s, j);
      if (kind === "crew" && j.crew_id === key) {
        const done = j.status === "done";
        push(j, { id: "install:" + j.job_id, kind: "install", open: !done, due: j.install_date,
          title: `Install ${j.power_kw} kW / ${j.energy_kwh} kWh, ${j.install_window}`,
          state: done ? "Installed" : j.crew_confirmed ? "Confirmed" : "Not confirmed",
          actions: done ? [] : ["confirm", "delay", "complete"] });
      }
      if (kind === "utility" && site.utility === key) {
        push(j, { id: "utility:" + j.job_id, kind: "utility", open: !j.utility_permission, due: j.install_date,
          title: "Permission to install / interconnect",
          state: j.utility_permission ? "Granted" : j.utility_eta ? `Expected ${fmt(j.utility_eta)}` : "Pending",
          actions: j.utility_permission ? [] : ["grant", "eta"] });
      }
      if (kind === "ahj" && site.city + ", " + site.state === key) {
        Object.entries(j.permits).forEach(([p, v]) => {
          push(j, { id: "permit:" + j.job_id + ":" + p, kind: "permit", permit: p, open: v !== "approved", due: EQ.addDays(j.install_date, -3),
            title: `${PERMIT_OFFICE[p]}: ${p} permit`,
            state: v === "approved" ? "Approved" : v === "revision" ? `Revision, round ${j.permit_round || 2}` : "Under review",
            actions: v === "approved" ? [] : ["approve", "revise"] });
        });
      }
      if (kind === "facility" && j.site_id === key) {
        const sd = s.shutdowns.find((x) => x.job_id === j.job_id);
        if (sd) push(j, { id: "shutdown:" + sd.shutdown_id, kind: "shutdown", ref: sd.shutdown_id, open: !sd.approved, due: sd.date,
          title: `Power shutdown ${fmt(sd.date)} ${sd.start_time}-${sd.end_time} for tie-in`,
          state: sd.approved ? "Approved" : sd.requested ? "Requested, awaiting you" : "Not yet requested",
          actions: sd.approved ? ["decline"] : ["approve", "decline"] });
      }
    });
    s.shipments.forEach((x) => {
      if (kind !== "vendor" || x.vendor !== key) return;
      const j = jobOf(s, x.job_id);
      const open = x.status !== "delivered";
      push(j, { id: "delivery:" + x.shipment_id, kind: "delivery", ref: x.shipment_id, open, due: x.delivery_date,
        title: `Deliver ${x.item} (needed by ${fmt(j.install_date)})`,
        state: x.status === "delivered" ? "Delivered" : x.status === "delayed" ? "Delayed" : x.confirmed ? "Date confirmed" : "In transit",
        actions: open ? ["confirm", "delay", "delivered"] : [] });
    });
    s.inspections.forEach((i) => {
      if (kind !== "inspector") return;
      const j = jobOf(s, i.job_id);
      if (i.type + "|" + siteOf(s, j).state !== key) return;
      const open = i.status !== "passed";
      push(j, { id: "inspection:" + i.inspection_id, kind: "inspection", ref: i.inspection_id, open,
        due: i.scheduled_date || EQ.addDays(j.install_date, 1),
        title: `${i.type === "fire" ? "Fire" : "Electrical"} inspection`,
        state: i.status === "passed" ? "Passed" : i.status === "not_booked" ? (i.failed ? "Failed, needs rebooking" : "Not booked") : i.confirmed ? "Confirmed" : "Booked",
        actions: !open ? [] : i.status === "not_booked" ? ["book"] : ["confirm", "reschedule", "pass", "fail"] });
    });

    items.sort((a, b) => (b.open - a.open) || (b.hard - a.hard) || (b.blocking - a.blocking) || a.due.localeCompare(b.due) || a.job_id.localeCompare(b.job_id));
    return items;
  }

  function summary(items) {
    const open = items.filter((i) => i.open), blocking = open.filter((i) => i.blocking);
    const jobs = [...new Set(blocking.map((i) => i.job_id))];
    const exposure = jobs.reduce((a, id) => a + blocking.find((i) => i.job_id === id).cost_per_day, 0);
    return { open: open.length, blocking: blocking.length, done: items.length - open.length, exposure };
  }

  // ---------- Actions ----------
  // An action is { item_id, type, date?, note? }. apply() mutates s and returns a log line.
  const ACTION_LABEL = {
    confirm: "Confirm date", delay: "Report a delay", complete: "Mark installed", grant: "Grant permission", eta: "Give expected date",
    approve: "Approve", revise: "Request revision", decline: "Decline window", delivered: "Mark delivered", book: "Book a date",
    reschedule: "Move date", pass: "Pass", fail: "Fail",
  };
  const NEEDS_DATE = { delay: true, eta: true, book: true, reschedule: true };

  function apply(s, partyName, a) {
    const [kind, ref, extra] = a.item_id.split(":");
    const say = (t) => { s.log = s.log || []; s.log.push({ n: s.log.length + 1, text: `[${partyName}] ${t}` }); return t; };
    if (NEEDS_DATE[a.type] && !a.date) throw new Error("A date is required");
    const note = a.note ? ` Note: ${a.note}` : "";

    if (kind === "install") {
      const j = jobOf(s, ref);
      if (a.type === "confirm") { j.crew_confirmed = true; return say(`Confirmed install ${j.job_id} on ${fmt(j.install_date)}.${note}`); }
      if (a.type === "complete") { j.status = "done"; j.crew_confirmed = true; return say(`Install of ${j.job_id} complete.${note}`); }
      if (a.type === "delay") {
        const from = j.install_date;
        EQ.applyChange(s, j.job_id, { install_date: a.date });
        j.crew_confirmed = true;
        // The tie-in shutdown moves with the install and goes back to the facility for approval.
        const sd = s.shutdowns.find((x) => x.job_id === j.job_id);
        if (sd && sd.date !== a.date) Object.assign(sd, { date: a.date, approved: false, requested: true, notes: `Moved from ${fmt(from)} by crew delay, needs re-approval` });
        return say(`Can't make ${j.job_id} on ${fmt(from)}; earliest ${fmt(a.date)}.${note}`);
      }
    }
    if (kind === "delivery") {
      const x = s.shipments.find((y) => y.shipment_id === ref), j = jobOf(s, x.job_id);
      if (a.type === "confirm") { x.confirmed = true; return say(`Confirmed delivery of ${x.item} for ${j.job_id} on ${fmt(x.delivery_date)}.${note}`); }
      if (a.type === "delivered") { x.status = "delivered"; if (x.delivery_date > s.today) x.delivery_date = s.today; return say(`Delivered ${x.item} for ${j.job_id}.${note}`); }
      if (a.type === "delay") { const from = x.delivery_date; Object.assign(x, { delivery_date: a.date, status: "in_transit", confirmed: true }); return say(`Delivery for ${j.job_id} slips ${fmt(from)} to ${fmt(a.date)}.${note}`); }
    }
    if (kind === "inspection") {
      const i = s.inspections.find((y) => y.inspection_id === ref);
      if (a.type === "confirm") { i.confirmed = true; return say(`Confirmed ${i.type} inspection for ${i.job_id} on ${fmt(i.scheduled_date)}.${note}`); }
      if (a.type === "book" || a.type === "reschedule") { Object.assign(i, { scheduled_date: a.date, status: "booked", confirmed: true, failed: false }); return say(`${i.type} inspection for ${i.job_id} set for ${fmt(a.date)}.${note}`); }
      if (a.type === "pass") { i.status = "passed"; return say(`${i.type} inspection for ${i.job_id} passed.${note}`); }
      if (a.type === "fail") { Object.assign(i, { status: "not_booked", scheduled_date: null, failed: true, confirmed: false }); return say(`${i.type} inspection for ${i.job_id} failed; needs fix and rebooking.${note}`); }
    }
    if (kind === "shutdown") {
      const sd = s.shutdowns.find((y) => y.shutdown_id === ref);
      if (a.type === "approve") { Object.assign(sd, { requested: true, approved: true, notes: "Facility approved" }); jobOf(s, sd.job_id).crew_held = false; return say(`Approved shutdown for ${sd.job_id} on ${fmt(sd.date)}.${note}`); }
      if (a.type === "decline") { Object.assign(sd, { requested: false, approved: false, notes: "Declined by facility" + (a.note ? ": " + a.note : "") }); return say(`Declined the ${fmt(sd.date)} shutdown for ${sd.job_id}.${note}`); }
    }
    if (kind === "utility") {
      const j = jobOf(s, ref);
      if (a.type === "grant") { j.utility_permission = true; return say(`Granted permission to install for ${j.job_id}.${note}`); }
      if (a.type === "eta") { j.utility_eta = a.date; return say(`Permission for ${j.job_id} expected ${fmt(a.date)}.${note}`); }
    }
    if (kind === "permit") {
      const j = jobOf(s, ref);
      if (a.type === "approve") { j.permits[extra] = "approved"; if (Object.values(j.permits).every((v) => v === "approved")) j.permit_approved_date = s.today; return say(`Approved ${extra} permit for ${j.job_id}.${note}`); }
      if (a.type === "revise") { j.permit_round = j.permits[extra] === "revision" ? (j.permit_round || 2) + 1 : 2; j.permits[extra] = "revision"; j.permit_approved_date = null; return say(`Sent ${extra} permit for ${j.job_id} back for revision (round ${j.permit_round}).${note}`); }
    }
    throw new Error(`Unknown action ${a.type} on ${a.item_id}`);
  }

  // What an action would do to the whole portfolio: jobs whose readiness or blocker changes, and new open items for other parties.
  function impact(s, partyId, partyName, a) {
    const before = EQ.evaluate(s, true);
    const t = clone(s);
    const line = apply(t, partyName, a);
    const after = EQ.evaluate(t, true);
    const changes = [];
    s.jobs.forEach((j) => {
      const b = before.byJob[j.job_id], f = after.byJob[j.job_id];
      if (b.readiness !== f.readiness || b.blocker !== f.blocker)
        changes.push({ job_id: j.job_id, from: b.readiness, to: f.readiness, before: b.blocker, after: f.blocker, cost_per_day: j.cost_of_delay_usd_per_day });
    });
    const others = [];
    parties(s).forEach((p) => {
      if (p.id === partyId) return;
      const was = new Set(obligations(s, p.id, before).filter((i) => i.open && i.blocking).map((i) => i.id));
      obligations(t, p.id, after).filter((i) => i.open && i.blocking && !was.has(i.id)).forEach((i) => others.push({ party: p.name, job_id: i.job_id, issue: i.issue }));
    });
    return { line, changes, others, state: t };
  }

  const api = { parties, obligations, summary, apply, impact, ACTION_LABEL, NEEDS_DATE };
  root.EQORE_CONTRACTOR = api;
  if (typeof module !== "undefined") module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
