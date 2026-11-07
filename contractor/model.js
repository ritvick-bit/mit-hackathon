// EQORE contractor portal: project timelines, contractor tasks, problem reports and resource matching.
// Pure functions over a plain JSON state. Works in the browser and in Node.
// Projects come from the command-center seed (../command-center/data.js) so job IDs match the PM map.
(function (root) {
  const DAY = 86400000;
  const parse = (s) => new Date(s + "T00:00:00Z");
  const iso = (d) => d.toISOString().slice(0, 10);
  const addDays = (s, n) => iso(new Date(parse(s).getTime() + n * DAY));
  const diffDays = (a, b) => Math.round((parse(a) - parse(b)) / DAY);
  const isWorkday = (s) => { const d = parse(s).getUTCDay(); return d !== 0 && d !== 6; };
  const nextWorkday = (s) => { while (!isWorkday(s)) s = addDays(s, 1); return s; };
  const prevWorkday = (s) => { while (!isWorkday(s)) s = addDays(s, -1); return s; };
  function addWorkdays(s, n) {
    s = n >= 0 ? nextWorkday(s) : prevWorkday(s);
    const step = n >= 0 ? 1 : -1;
    for (let i = 0; i < Math.abs(n); i++) { s = addDays(s, step); while (!isWorkday(s)) s = addDays(s, step); }
    return s;
  }
  const maxDate = (...xs) => xs.filter(Boolean).sort().slice(-1)[0];
  const fmt = (s) => (s ? parse(s).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" }) : "");
  const clone = (o) => JSON.parse(JSON.stringify(o));
  function miles(a, b) {
    const R = 3959, r = Math.PI / 180;
    const dLat = (b.lat - a.lat) * r, dLng = (b.lng - a.lng) * r;
    const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * r) * Math.cos(b.lat * r) * Math.sin(dLng / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(h));
  }

  // ---------- Seed ----------
  // key, name, trade, duration, unit (work days or calendar days), predecessor keys, planned start offset from install day (work days)
  const TEMPLATE = [
    ["pad_pour", "Pour concrete pad", "civil", 1, "work", [], -10],
    ["pad_cure", "Pad cure", "civil", 7, "cal", ["pad_pour"], null],
    ["delivery", "Deliver battery cabinets and inverter", "freight", 1, "work", [], null],
    ["shutdown", "Approve tie-in shutdown window", "customer", 1, "work", [], -5],
    ["placement", "Set cabinets on pad (crane lift)", "crane", 1, "work", ["pad_cure", "delivery"], -1],
    ["electrical", "Electrical installation", "electrical", 2, "work", ["placement"], 0],
    ["rough_insp", "Rough electrical inspection", "inspection", 1, "work", ["electrical"], 2],
    ["tie_in", "Tie-in to main switchgear", "electrical", 1, "work", ["rough_insp", "shutdown"], 3],
    ["final_insp", "Final inspections (building, wiring, fire)", "inspection", 1, "work", ["tie_in"], 4],
    ["commissioning", "Commissioning", "commissioning", 2, "work", ["final_insp"], 5],
    ["pto", "Utility permission to operate", "utility", 5, "work", ["commissioning"], 7],
    ["energize", "Energize and hand over", "eqore", 1, "work", ["pto"], 12],
  ];

  function nearest(companies, trade, site) {
    return companies.filter((c) => c.trade === trade && c.state === site.state)
      .sort((a, b) => miles(a, site) - miles(b, site))[0];
  }

  function seed(cc, db) {
    const s = { today: cc.today, companies: clone(db.companies), projects: [], tasks: [], reports: [], notices: [], log: [], seq: { report: 0, notice: 0, task: 0, log: 0 } };
    cc.jobs.forEach((j) => {
      const site = cc.sites.find((x) => x.site_id === j.site_id);
      const D = nextWorkday(j.install_date);
      const ship = cc.shipments.find((x) => x.job_id === j.job_id);
      const shut = cc.shutdowns.find((x) => x.job_id === j.job_id);
      const owner = {
        civil: nearest(s.companies, "civil", site).id,
        freight: nearest(s.companies, "freight", site).id,
        crane: nearest(s.companies, "crane", site).id,
        electrical: s.companies.find((c) => c.crew_id === j.crew_id).id,
        inspection: "IN-" + site.state,
        commissioning: nearest(s.companies, "commissioning", site).id,
        utility: db.UTILITY_COMPANY[site.utility],
        customer: "CUST-" + site.site_id,
        eqore: "EQORE",
      };
      const p = {
        id: j.job_id, name: site.name, city: site.city, state: site.state, utility: site.utility, lat: site.lat, lng: site.lng,
        power_kw: j.power_kw, energy_kwh: j.energy_kwh, install_date: D, customer_name: site.name,
        target_go_live: addWorkdays(D, 12), cost_of_delay_usd_per_day: j.cost_of_delay_usd_per_day,
      };
      s.projects.push(p);
      const byKey = {};
      TEMPLATE.forEach(([key, name, trade, duration, unit, preds, offset]) => {
        let planned = offset != null ? addWorkdays(D, offset) : null;
        if (key === "pad_cure") planned = addDays(byKey.pad_pour.planned_start, 1);
        // Deliveries land 3 work days before install, unless the command-center record has them late (on or after install day).
        if (key === "delivery") planned = ship.delivery_date >= D ? nextWorkday(ship.delivery_date) : addWorkdays(D, -3);
        const t = {
          id: `T-${j.job_id}-${key}`, project_id: j.job_id, key, name, trade, owner_id: owner[trade], duration, unit,
          preds: preds.map((k) => byKey[k].id), planned_start: planned, status: "open", actual_start: null, actual_finish: null,
          not_before: null, problem: null, history: [], origin: null,
        };
        if (key === "shutdown" && !shut.approved) t.note = shut.notes;
        byKey[key] = t;
        s.tasks.push(t);
      });
    });
    // Work planned to finish before today is recorded as done; work spanning today is in progress.
    const sch = schedule(s, { plan: true });
    s.tasks.forEach((t) => {
      const d = sch.tasks[t.id];
      if (t.key === "shutdown") { // approval status comes from the command-center record
        const shut = cc.shutdowns.find((x) => x.job_id === t.project_id);
        if (shut.approved) Object.assign(t, { status: "done", actual_start: d.start < s.today ? d.start : s.today, actual_finish: d.finish < s.today ? d.finish : s.today });
        return;
      }
      if (d.finish < s.today) Object.assign(t, { status: "done", actual_start: d.start, actual_finish: d.finish });
      else if (d.start < s.today) t.actual_start = d.start;
    });
    return s;
  }

  // ---------- Timeline (forward pass) ----------
  // A task starts at the latest of: its planned start, the day after every predecessor finishes, any not-before date,
  // and the next work day if it has not started yet. Done tasks keep their recorded dates.
  // opts.plan: ignore the clock (the original plan, used when seeding).
  function schedule(s, opts) {
    const byId = {};
    s.tasks.forEach((t) => (byId[t.id] = t));
    const out = {}, visiting = {};
    const firstOpenDay = opts && opts.plan ? null : nextWorkday(s.today);
    function calc(id) {
      if (out[id]) return out[id];
      if (visiting[id]) throw new Error("Dependency cycle at " + id);
      visiting[id] = true;
      const t = byId[id];
      const preds = t.preds.map(calc);
      let start, finish;
      if (t.status === "done") { start = t.actual_start; finish = t.actual_finish; }
      else {
        const after = preds.length ? addDays(maxDate(...preds.map((p) => p.finish)), 1) : null;
        start = t.actual_start || maxDate(t.planned_start, after, t.not_before, firstOpenDay);
        if (t.unit === "work") start = nextWorkday(start);
        finish = t.unit === "cal" ? addDays(start, t.duration - 1) : addWorkdays(start, t.duration - 1);
      }
      visiting[id] = false;
      return (out[id] = { start, finish });
    }
    s.tasks.forEach((t) => calc(t.id));
    const projects = {};
    s.projects.forEach((p) => {
      const end = s.tasks.filter((t) => t.project_id === p.id).reduce((m, t) => maxDate(m, out[t.id].finish), null);
      projects[p.id] = { go_live: end, slip_days: diffDays(end, p.target_go_live) };
    });
    return { tasks: out, projects };
  }

  // ---------- Lookups ----------
  const task = (s, id) => s.tasks.find((t) => t.id === id);
  const project = (s, id) => s.projects.find((p) => p.id === id);
  const company = (s, id) => s.companies.find((c) => c.id === id);
  function ownerName(s, id) {
    const c = company(s, id);
    if (c) return c.name;
    if (id === "EQORE") return "EQORE";
    if (id && id.startsWith("CUST-")) { const p = s.projects.find((x) => "CUST-SITE-" + x.id.slice(4) === id); return p ? p.customer_name : "Customer facility"; }
    return id;
  }

  function taskState(s, t, sch) {
    sch = sch || schedule(s);
    const d = sch.tasks[t.id];
    const waitingOn = t.preds.map((id) => task(s, id)).filter((p) => p.status !== "done");
    let state = "ready";
    if (t.status === "done") state = "done";
    else if (t.problem) state = "problem";
    else if (waitingOn.length) state = "waiting";
    else if (t.actual_start || d.start <= s.today) state = "in_progress";
    return { ...d, state, waitingOn };
  }

  // Everything a company owes, open first, by start date.
  function tasksFor(s, companyId, sch) {
    sch = sch || schedule(s);
    return s.tasks.filter((t) => t.owner_id === companyId)
      .map((t) => ({ task: t, project: project(s, t.project_id), ...taskState(s, t, sch) }))
      .sort((a, b) => ((a.state === "done") - (b.state === "done")) || a.start.localeCompare(b.start) || a.task.id.localeCompare(b.task.id));
  }

  // ---------- Change tracking ----------
  // Runs a mutation on a copy, then tells every owner whose task moved or was added.
  function commit(s, by, reason, mutate) {
    const before = schedule(s);
    const owners = {};
    s.tasks.forEach((x) => (owners[x.id] = x.owner_id));
    const t = clone(s);
    const result = mutate(t);
    const after = schedule(t);
    const moved = [];
    t.tasks.forEach((x) => {
      const b = before.tasks[x.id], a = after.tasks[x.id];
      if (x.status === "done") return;
      if (b && owners[x.id] !== x.owner_id) {
        note(t, x.owner_id, x.id, `New task assigned: ${x.name}, ${fmt(a.start)}${a.finish !== a.start ? "–" + fmt(a.finish) : ""} (taken over from ${ownerName(t, owners[x.id])})`, reason);
        note(t, owners[x.id], x.id, `${x.name} reassigned to ${ownerName(t, x.owner_id)}`, reason);
        if (b.start !== a.start) moved.push(x.id);
      } else if (!b) note(t, x.owner_id, x.id, `New task assigned: ${x.name}, ${fmt(a.start)}${a.finish !== a.start ? "–" + fmt(a.finish) : ""}`, reason);
      else if (b.start !== a.start) { moved.push(x.id); note(t, x.owner_id, x.id, `${x.name} moved ${fmt(b.start)} → ${fmt(a.start)}`, reason); }
    });
    t.seq.log++;
    t.log.push({ id: t.seq.log, at: t.today, by, text: reason, projects: [...new Set(moved.map((id) => task(t, id).project_id))] });
    return { state: t, result, moved };
  }
  function note(s, owner, taskId, text, reason) {
    s.seq.notice++;
    s.notices.push({ id: s.seq.notice, owner, task_id: taskId, text, reason, at: s.today, seen: false });
  }

  // ---------- Contractor actions ----------
  function completeTask(s, taskId, byCompany) {
    const t0 = task(s, taskId);
    if (!t0) throw new Error("Unknown task");
    if (t0.owner_id !== byCompany) throw new Error("This task is not assigned to you");
    if (t0.status === "done") throw new Error("Already marked done");
    const waiting = t0.preds.map((id) => task(s, id)).filter((p) => p.status !== "done");
    if (waiting.length) throw new Error(`Waiting on: ${waiting.map((p) => p.name).join(", ")}`);
    const name = ownerName(s, byCompany);
    return commit(s, name, `${name} marked "${t0.name}" done for ${t0.project_id}`, (t) => {
      const x = task(t, taskId), d = schedule(t).tasks[taskId];
      Object.assign(x, { status: "done", actual_start: x.actual_start || (d.start <= t.today ? d.start : t.today), actual_finish: t.today, problem: null });
      x.history.push({ at: t.today, type: "done", by: byCompany });
    });
  }

  // Candidate companies that could do `days` work days of `trade` work on the task's site, earliest first.
  // Each option includes the go-live date the project would have if the PM approves it.
  function searchResources(s, taskId, req, opts) {
    opts = opts || {};
    const t = task(s, taskId), p = project(s, t.project_id);
    const sch = schedule(s);
    const days = Math.max(1, Math.min(10, req.days | 0 || 1));
    const from = nextWorkday(maxDate(req.from, addDays(s.today, 1)));
    const exclude = new Set([req.exclude || t.owner_id]);
    const load = (c, day) => {
      let n = 0;
      s.tasks.forEach((x) => { if (x.owner_id === c.id && x.status !== "done") { const d = sch.tasks[x.id]; if (d.start <= day && day <= d.finish) n++; } });
      c.bookings.forEach((b) => { if (b.start <= day && day <= b.end) n++; });
      return n;
    };
    const options = [];
    s.companies.filter((c) => c.trade === req.trade && c.state === p.state && !exclude.has(c.id)).forEach((c) => {
      const dist = Math.round(miles(c, p));
      if (dist > c.radius_mi) return;
      const mob = dist < 30 ? 0 : dist < 100 ? 1 : 2;
      let start = addWorkdays(from, mob);
      for (let i = 0; i < 25; i++, start = addWorkdays(start, 1)) {
        let ok = true;
        for (let k = 0, d = start; k < days; k++, d = addWorkdays(d, 1)) if (load(c, d) >= c.crews) { ok = false; break; }
        if (!ok) continue;
        const opt = { id: `${c.id}@${start}`, company_id: c.id, company: c.name, city: c.city, distance_mi: dist, mobilization_days: mob,
          start, finish: addWorkdays(start, days - 1), days, cost_usd: Math.round(c.day_rate * days + c.day_rate * 0.5 * mob), rating: c.rating, certifications: c.certifications };
        const sim = applyOption(clone(s), taskId, req, opt);
        const after = schedule(sim).projects[p.id];
        Object.assign(opt, { go_live: after.go_live, go_live_change_days: diffDays(after.go_live, sch.projects[p.id].go_live), slip_vs_target_days: after.slip_days });
        options.push(opt);
        break;
      }
    });
    options.sort((a, b) => a.go_live.localeCompare(b.go_live) || a.cost_usd - b.cost_usd || b.rating - a.rating);
    return options.slice(0, opts.limit || 4);
  }

  // mode "replace": the new company takes over this task. mode "before": a new task for the new company runs before this one.
  function applyOption(s, taskId, req, opt, reportId) {
    const t = task(s, taskId);
    if (req.mode === "replace") {
      t.history.push({ at: s.today, type: "reassigned", from: t.owner_id, to: opt.company_id, report: reportId || null });
      Object.assign(t, { owner_id: opt.company_id, not_before: opt.start, duration: opt.days, actual_start: null, origin: reportId ? { report_id: reportId, replaced: t.owner_id } : null });
      if (t.unit === "cal") t.unit = "work";
    } else {
      s.seq.task++;
      const id = `T-${t.project_id}-R${s.seq.task}`;
      s.tasks.push({
        id, project_id: t.project_id, key: "added", name: req.work || `${TRADE_LABEL(req.trade)} support before ${t.name.toLowerCase()}`,
        trade: req.trade, owner_id: opt.company_id, duration: opt.days, unit: "work", preds: t.preds.slice(), planned_start: opt.start,
        status: "open", actual_start: null, actual_finish: null, not_before: opt.start, problem: null, history: [], origin: reportId ? { report_id: reportId } : null,
      });
      t.preds = t.preds.concat(id);
      if (t.actual_start) t.actual_start = null;
    }
    return s;
  }
  const DB = root.EQORE_CONTRACTOR_DB || (typeof require !== "undefined" ? require("./db.js") : { TRADES: {} });
  const TRADE_LABEL = (k) => (DB.TRADES[k] ? DB.TRADES[k].label : k);

  // A problem report. resource = { mode, trade, days, from, work } or null when no extra resource is needed.
  function fileReport(s, input) {
    const t0 = task(s, input.task_id);
    if (!t0) throw new Error("Unknown task");
    if (t0.owner_id !== input.by) throw new Error("This task is not assigned to you");
    if (t0.problem) throw new Error("There is already an open report on this task");
    if (!String(input.details || "").trim()) throw new Error("Describe the problem");
    const urgency = Math.max(1, Math.min(5, input.urgency | 0));
    if (!input.urgency) throw new Error("Pick an urgency level");
    const name = ownerName(s, input.by);
    const resource = input.resource || null;
    const options = resource ? searchResources(s, input.task_id, resource) : [];
    return commit(s, name, `${name} reported a problem on "${t0.name}" for ${t0.project_id} (urgency ${urgency})`, (t) => {
      t.seq.report++;
      const id = "R-" + String(t.seq.report).padStart(3, "0");
      const sch = schedule(t);
      const r = {
        id, task_id: input.task_id, project_id: t0.project_id, by: input.by, by_name: name, filed_at: t.today,
        details: String(input.details).trim().slice(0, 4000), photos: (input.photos || []).slice(0, 6), urgency,
        resource, options, preferred_option_id: input.preferred_option_id || (options[0] && options[0].id) || null,
        no_resource: !!resource && !options.length, go_live_at_filing: sch.projects[t0.project_id].go_live,
        summary: input.summary || null, status: "pending", decision: null,
      };
      t.reports.push(r);
      task(t, input.task_id).problem = id;
      task(t, input.task_id).history.push({ at: t.today, type: "problem", report: id });
      return r;
    });
  }

  // ---------- PM decisions ----------
  function approve(s, reportId, optionId, pmName, note) {
    const r0 = s.reports.find((r) => r.id === reportId);
    if (!r0 || r0.status !== "pending") throw new Error("This report is not waiting for a decision");
    if (!r0.resource) throw new Error("No resource was requested");
    const filed = r0.options.find((o) => o.id === optionId);
    if (!filed) throw new Error("Unknown option");
    // Re-check: the calendar may have changed since the report was filed.
    const fresh = searchResources(s, r0.task_id, Object.assign({ exclude: r0.by }, r0.resource), { limit: 99 }).find((o) => o.company_id === filed.company_id);
    if (!fresh) throw new Error(`${filed.company} is no longer available. Ask the contractor to check resources again.`);
    return commit(s, pmName, `PM approved ${fresh.company} for ${r0.project_id} (${reportId}), starting ${fmt(fresh.start)}`, (t) => {
      applyOption(t, r0.task_id, r0.resource, fresh, reportId);
      const r = t.reports.find((x) => x.id === reportId);
      const x = task(t, r0.task_id);
      x.problem = null;
      Object.assign(r, { status: "approved", decision: { by: pmName, at: t.today, option: fresh, changed: fresh.start !== filed.start, note: note || "" } });
      return r;
    });
  }

  function decline(s, reportId, pmName, pmNote) {
    const r0 = s.reports.find((r) => r.id === reportId);
    if (!r0 || r0.status !== "pending") throw new Error("This report is not waiting for a decision");
    return commit(s, pmName, `PM ${r0.resource ? "declined the resource request" : "acknowledged the report"} ${reportId} for ${r0.project_id}${pmNote ? ": " + pmNote : ""}`, (t) => {
      const r = t.reports.find((x) => x.id === reportId);
      Object.assign(r, { status: r0.resource ? "declined" : "acknowledged", decision: { by: pmName, at: t.today, note: pmNote || "" } });
      task(t, r0.task_id).problem = null;
      note(t, r0.by, r0.task_id, `PM ${r.status} report ${reportId}${pmNote ? ": " + pmNote : ""}`, "PM decision");
      return r;
    });
  }

  // Rule-based summary, used when the AI summary is unavailable. Labelled as such in the UI.
  function ruleSummary(s, r) {
    const t = task(s, r.task_id), p = project(s, r.project_id);
    const first = r.details.split(/(?<=[.!?])\s+/)[0].slice(0, 220);
    const res = !r.resource ? "No extra resource requested." : r.no_resource
      ? `Needs ${r.resource.days} day(s) of ${TRADE_LABEL(r.resource.trade).toLowerCase()} work; no available company found in ${p.state}.`
      : `Best option: ${r.options[0].company}, starting ${fmt(r.options[0].start)}; go-live ${r.options[0].go_live_change_days > 0 ? "moves " + r.options[0].go_live_change_days + " day(s) later" : "does not move"}.`;
    return `${r.by_name}, ${t.name} at ${p.name} (${p.id}), urgency ${r.urgency}: ${first} ${res}`;
  }

  const api = {
    TEMPLATE, seed, schedule, taskState, tasksFor, completeTask, fileReport, searchResources, approve, decline, ruleSummary,
    task, project, company, ownerName, miles,
    addDays, diffDays, addWorkdays, nextWorkday, isWorkday, fmt, clone, TRADE_LABEL,
  };
  root.EQORE_CT = api;
  if (typeof module !== "undefined") module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
