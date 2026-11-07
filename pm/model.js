// EQORE PM platform: portfolio model.
// Builds every project's timeline from data.js, forecasts it (forward pass with finish-to-start links, work days),
// finds slack (backward pass), and derives project status, the PM's to-do list, paperwork, calendar items,
// subcontractor updates and contractor availability. Pure functions; works in the browser and in Node.
(function (root) {
  const DAY = 86400000;
  const parse = (s) => new Date(s + "T00:00:00Z");
  const iso = (d) => d.toISOString().slice(0, 10);
  const addDays = (s, n) => iso(new Date(parse(s).getTime() + n * DAY));
  const isWorkday = (s) => { const d = parse(s).getUTCDay(); return d !== 0 && d !== 6; };
  const nextWorkday = (s) => { while (!isWorkday(s)) s = addDays(s, 1); return s; };
  function addWorkdays(s, n) {
    const step = n >= 0 ? 1 : -1;
    for (let i = 0; i < Math.abs(n); i++) { s = addDays(s, step); while (!isWorkday(s)) s = addDays(s, step); }
    return s;
  }
  function miles(a, b) {
    const R = 3959, r = Math.PI / 180;
    const dLat = (b.lat - a.lat) * r, dLng = (b.lng - a.lng) * r;
    const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * r) * Math.cos(b.lat * r) * Math.sin(dLng / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(h));
  }
  const hash = (str) => { let h = 7; for (const c of str) h = (h * 31 + c.charCodeAt(0)) >>> 0; return h; };
  const slug = (s) => s.toLowerCase().replace(/&/g, "and").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

  // Work-day index <-> date. Index 0 is today (or the next work day when today is a weekend).
  function calendar(today) {
    const base = nextWorkday(today);
    return { today, base, date: (i) => addWorkdays(base, i), index: (d) => {
      let i = 0, x = base;
      if (d >= base) { while (x < d) { x = addDays(x, 1); if (isWorkday(x)) i++; } return i; }
      while (x > d) { x = addDays(x, -1); if (isWorkday(x)) i--; } return i;
    } };
  }

  // ---------- Build the portfolio ----------
  function build(D, today) {
    const cal = calendar(today);
    const companies = D.COMPANIES.map(([id, name, trade, state, city, lat, lng, crews, day_rate, rating, certifications, radius_mi, contact]) => ({
      id, name, trade, state, city, lat, lng, crews, day_rate, rating, certifications, radius_mi, contact,
      email: slug(contact.split(" ")[0]) + "@" + slug(name.replace(/\(.*\)/, "").replace(/ (Co\.|Inc\.)$/, "")) + ".demo.example",
      bookings: D.OUTSIDE_BOOKINGS.filter((b) => b[0] === id).map(([, s, n]) => ({ s, f: s + n - 1, note: "Booked with another client" })),
    }));
    const byCompany = Object.fromEntries(companies.map((c) => [c.id, c]));
    const pms = D.PMS;

    // Planned offsets of every step from project start (forward pass, no constraints).
    const rel = {};
    D.TEMPLATE.forEach((t) => {
      const s = t.preds.length ? Math.max(...t.preds.map((k) => rel[k].f + 1)) : 0;
      rel[t.key] = { s, f: s + t.duration - 1 };
    });

    const projects = D.PROJECTS.map(([id, name, city, state, lat, lng, utility_id, pm_id, kw, kwh, stage, progress]) => {
      const site = { lat, lng, state };
      const nearest = (trade) => companies.filter((c) => c.trade === trade && c.state === state).sort((a, b) => miles(a, site) - miles(b, site))[0].id;
      const parties = {
        customer: "CUST-" + id, supplier: "SU-QPACK", engineering: nearest("engineering"), inspection: "IN-" + state,
        utility: utility_id, freight: nearest("freight"), civil: nearest("civil"), crane: nearest("crane"),
        electrical: nearest("electrical"), commissioning: nearest("commissioning"), eqore: pm_id,
      };
      const step = D.TEMPLATE.find((t) => t.key === stage);
      const P = -(rel[stage].s + Math.floor(progress * step.duration));
      const customer = { id: "CUST-" + id, name, trade: "customer", contact: "Facilities manager", city, state, lat, lng,
        email: "facilities@" + slug(name) + ".demo.example", crews: 1, bookings: [] };
      return { id, name, city, state, lat, lng, utility_id, pm_id, kw, kwh, stage, parties, customer, P };
    });
    projects.forEach((p) => (byCompany[p.customer.id] = p.customer));

    const tasks = [];
    projects.forEach((p) => {
      D.TEMPLATE.forEach((t) => {
        const ps = p.P + rel[t.key].s, pf = p.P + rel[t.key].f;
        const issue = D.ISSUES.find((x) => x[0] === p.id && x[1] === t.key);
        const task = {
          id: `${p.id}:${t.key}`, project_id: p.id, key: t.key, short: t.short, name: t.name, phase: t.phase, role: t.role,
          owner_id: p.parties[t.role], duration: t.duration, preds: t.preds.map((k) => `${p.id}:${k}`),
          planned: { s: ps, f: pf }, done: pf < 0 && !issue, started: ps <= 0,
          issue: issue ? { extra: issue[2], reported: -issue[3], text: issue[4] } : null,
        };
        tasks.push(task);
      });
    });

    const state = { D, cal, pms, companies, byCompany, projects, tasks, rel };
    forecast(state);
    projects.forEach((p) => derive(state, p));
    return state;
  }

  // ---------- Forecast (forward pass) and slack (backward pass) ----------
  function forecast(state) {
    const byId = Object.fromEntries(state.tasks.map((t) => [t.id, t]));
    state.byTask = byId;
    const memo = {};
    function calc(t) {
      if (memo[t.id]) return memo[t.id];
      const preds = t.preds.map((id) => calc(byId[id]));
      let s, f;
      if (t.done) { s = t.planned.s; f = t.planned.f; }
      else {
        const after = preds.length ? Math.max(...preds.map((x) => x.f + 1)) : -Infinity;
        s = Math.max(t.planned.s, after);
        if (!t.started || s > 0) s = Math.max(s, 0); // nothing new starts in the past
        f = s + t.duration + (t.issue ? t.issue.extra : 0) - 1;
        if (f < 0) f = 0; // an open task finishes today at the earliest
      }
      return (memo[t.id] = { s, f });
    }
    state.tasks.forEach((t) => (t.fc = calc(t)));
    // Backward pass per project: latest finish that keeps the forecast go-live.
    state.projects.forEach((p) => {
      const ts = state.tasks.filter((t) => t.project_id === p.id);
      const end = Math.max(...ts.map((t) => t.fc.f));
      const succ = {};
      ts.forEach((t) => t.preds.forEach((id) => (succ[id] = (succ[id] || []).concat(t))));
      const lf = {};
      const late = (t) => {
        if (lf[t.id] != null) return lf[t.id];
        const ss = succ[t.id] || [];
        const span = (x) => x.fc.f - x.fc.s; // remaining length of the successor
        return (lf[t.id] = ss.length ? Math.min(...ss.map((x) => late(x) - span(x) - 1)) : end);
      };
      ts.forEach((t) => { t.slack = t.done ? 0 : late(t) - t.fc.f; t.critical = !t.done && t.slack <= 0; });
      p.target = Math.max(...ts.map((t) => t.planned.f));
      p.go_live = end;
      p.slip = end - p.target;
    });
  }

  // ---------- Per-project derived views ----------
  function derive(state, p) {
    const { cal } = state;
    const ts = state.tasks.filter((t) => t.project_id === p.id);
    p.tasks = ts;
    p.current = ts.filter((t) => !t.done && t.fc.s <= 0);
    if (!p.current.length) p.current = [ts.filter((t) => !t.done).sort((a, b) => a.fc.s - b.fc.s)[0]].filter(Boolean);
    p.step_index = Math.max(0, ts.findIndex((t) => !t.done));
    p.issues = ts.filter((t) => t.issue).map((t) => ({ task: t, ...t.issue, owner_id: t.owner_id }));
    p.docs = documents(state, p);
    p.todos = todos(state, p);
    const pmTodo = p.todos.find((x) => x.urgency <= 2 && x.kind !== "chase");
    if (p.slip > 0) p.status = "red";
    else if (pmTodo) p.status = "yellow";
    else p.status = "green";
    const top = p.issues[0];
    p.status_text = p.status === "red" ? `Behind schedule by ${p.slip} work day${p.slip === 1 ? "" : "s"}${top ? ": " + top.text : ""}`
      : p.status === "yellow" ? `Action needed: ${pmTodo.title}` : `On schedule. ${p.current.map((t) => t.name).join(", ")} in progress.`;
    p.go_live_date = cal.date(p.go_live);
    p.target_date = cal.date(p.target);
  }

  // Paperwork: done steps are complete; active steps (in progress or starting within 10 work days) are partly through their flow.
  function documents(state, p) {
    const docs = [];
    p.tasks.forEach((t) => {
      (state.D.DOCS[t.key] || []).forEach(([name, flow], n) => {
        const id = `${t.id}:doc${n}`;
        const parties = flow.map((role) => (role === "PM" ? { role, id: p.pm_id, label: "PM" } : { role, id: p.parties[role], label: role === "customer" ? "Customer" : "Contractor" }));
        const active = !t.done && t.fc.s <= 10;
        const frac = t.fc.s <= 0 ? -t.fc.s / (t.fc.f - t.fc.s + 1) : 0; // how far through the step we are
        let k = t.done ? flow.length : active && t.fc.s <= 0 ? Math.min(flow.length - 1, Math.floor(frac * flow.length + (hash(id) % 2) * 0.5)) : 0;
        const history = [];
        const span = Math.max(1, (t.done ? t.fc.f : 0) - t.fc.s);
        for (let i = 0; i < k; i++) {
          const at = Math.min(t.done ? t.fc.f : -1, t.fc.s + Math.round((span * (i + 1)) / (flow.length + 1)));
          history.push({ at, by: parties[i].id, action: i === flow.length - 1 || parties[i].role === "PM" ? "Signed" : "Filled out and sent" });
        }
        const status = k >= flow.length ? "complete" : active ? "waiting" : "not_started";
        const next = status === "complete" ? null : parties[k];
        // Paperwork for a step is due when the step is due to finish; prerequisites (first step of the flow) by its start.
        const due = status === "complete" ? null : k === 0 && t.fc.s > 0 ? t.fc.s : t.fc.f;
        docs.push({ id, name, task: t, project_id: p.id, flow: parties, step: k, status, next, due, history,
          department: state.D.DEPARTMENTS[t.key], sent_at: history.length ? history[history.length - 1].at : Math.min(0, t.fc.s) - 1 });
      });
    });
    return docs;
  }

  const urgencyOf = (due) => (due < 0 ? 1 : due <= 3 ? 2 : due <= 10 ? 3 : 4);
  const URGENCY = { 1: "Overdue", 2: "Due this week", 3: "Due in 2 weeks", 4: "Later" };

  function todos(state, p) {
    const out = [];
    p.issues.forEach((x) => out.push({ kind: "issue", urgency: 1, due: x.reported, title: `Delay reported: ${x.task.name}`, detail: x.text, party: x.owner_id, task: x.task }));
    p.docs.filter((d) => d.status === "waiting" && d.next.label === "PM").forEach((d) =>
      out.push({ kind: "doc", urgency: urgencyOf(d.due), due: d.due, title: `${d.step === 0 ? "Fill out" : "Sign"}: ${d.name}`, detail: d.task.name === d.department ? `${d.task.name}.` : `${d.task.name}. ${d.department}.`, doc: d, party: null }));
    p.tasks.filter((t) => !t.done && t.role === "eqore" && t.key !== "controls" && t.fc.s <= 5).forEach((t) =>
      out.push({ kind: "task", urgency: urgencyOf(t.fc.s <= 0 ? t.fc.f : t.fc.s), due: t.fc.s <= 0 ? t.fc.f : t.fc.s, title: t.key === "precon" ? "Run pre-construction scheduling: book crew, crane and the shutdown window" : t.name, detail: t.phase, task: t }));
    p.docs.filter((d) => d.status === "waiting" && d.next.label !== "PM" && d.due <= 3).forEach((d) =>
      out.push({ kind: "chase", urgency: d.due < 0 ? 2 : 4, due: d.due, title: `Chase ${state.byCompany[d.next.id].name}: ${d.name}`, detail: `Waiting on the ${d.next.label.toLowerCase()} to ${d.step === d.flow.length - 1 ? "sign" : "fill out"}.`, doc: d, party: d.next.id }));
    return out.sort((a, b) => a.urgency - b.urgency || a.due - b.due);
  }

  // ---------- Subcontractors on a project ----------
  function subcontractors(state, p) {
    const ids = [...new Set(p.tasks.filter((t) => t.role !== "eqore" && t.role !== "customer").map((t) => t.owner_id))];
    return ids.map((id) => {
      const c = state.byCompany[id];
      const tasks = p.tasks.filter((t) => t.owner_id === id).map((t) => ({ task: t, state: taskState(t) }));
      const docs = p.docs.filter((d) => d.flow.some((x) => x.id === id));
      const open = docs.filter((d) => d.status === "waiting" && d.next.id === id);
      const delayed = tasks.filter((x) => x.state === "problem"); // their own reported delay
      const pushed = tasks.filter((x) => x.state === "late"); // moved by a delay upstream
      return { company: c, tasks, docs, open, delayed, pushed };
    });
  }

  // done | active | upcoming | at_risk (on the critical path, about to start or running) | late (pushed back by a delay upstream) | problem (its own reported delay)
  function taskState(t) {
    if (t.done) return "done";
    if (t.issue) return "problem";
    if (t.fc.f > t.planned.f) return "late";
    if (t.critical && t.fc.s <= 5) return "at_risk";
    return t.fc.s <= 0 ? "active" : "upcoming";
  }

  function updates(state, p, days) {
    const out = [];
    p.tasks.filter((t) => t.done && t.fc.f >= -(days || 15)).forEach((t) => out.push({ at: t.fc.f, kind: "done", party: t.owner_id, text: `${t.name} completed` }));
    p.tasks.filter((t) => !t.done && t.started && t.planned.s >= -(days || 15)).forEach((t) => out.push({ at: t.planned.s, kind: "start", party: t.owner_id, text: `${t.name} started` }));
    p.docs.forEach((d) => d.history.filter((h) => h.at >= -(days || 15) && h.by !== p.pm_id).forEach((h) => out.push({ at: h.at, kind: "doc", party: h.by, text: `${h.action}: ${d.name}` })));
    p.issues.forEach((x) => out.push({ at: x.reported, kind: "issue", party: x.owner_id, text: x.text, delay: x.extra }));
    return out.sort((a, b) => b.at - a.at);
  }

  // ---------- Calendar ----------
  function calendarItems(state, p) {
    const { cal } = state;
    const items = [];
    const projs = p ? [p] : state.projects;
    projs.forEach((q) => {
      q.tasks.filter((t) => !t.done).forEach((t) => {
        if (t.fc.s >= 0) items.push({ date: cal.date(t.fc.s), kind: "task", title: `${t.name} starts`, project_id: q.id, owner: t.owner_id, state: taskState(t) });
        if (["final_insp", "pto", "energize", "placement", "tie_in"].includes(t.key) && t.fc.f >= 0) items.push({ date: cal.date(t.fc.f), kind: "milestone", title: `${t.name} due`, project_id: q.id, owner: t.owner_id, state: taskState(t) });
      });
      q.docs.filter((d) => d.status === "waiting" && d.next.label === "PM" && d.due >= 0).forEach((d) =>
        items.push({ date: cal.date(d.due), kind: "doc", title: `Paperwork due: ${d.name}`, project_id: q.id }));
      const pre = q.tasks.find((t) => t.key === "precon");
      if (!pre.done && pre.fc.s <= 10) items.push({ date: cal.date(Math.max(0, pre.fc.s)), time: "13:00", kind: "meeting", title: `Pre-construction meeting: ${q.name}`, project_id: q.id });
      const insp = q.tasks.find((t) => t.key === "final_insp");
      if (!insp.done && insp.fc.s >= 0 && insp.fc.s <= 15) items.push({ date: cal.date(insp.fc.s), time: "10:00", kind: "meeting", title: `Inspector site visit: ${q.name}`, project_id: q.id });
    });
    if (!p) state.D.MEETINGS.forEach((m) => items.push({ date: state.cal.date(m.offset), time: m.time, kind: "meeting", title: m.title, project_id: null }));
    return items.sort((a, b) => (a.date + (a.time || "")).localeCompare(b.date + (b.time || "")));
  }

  // ---------- Demo inbox: paperwork emails waiting on the PM ----------
  function demoInbox(state, projects) {
    const mails = [];
    projects.forEach((p) => p.docs.filter((d) => d.status === "waiting" && d.next.label === "PM").forEach((d) => {
      const fromParty = d.step > 0 ? d.flow[d.step - 1] : d.flow.find((x) => x.label !== "PM") || d.flow[0];
      const c = state.byCompany[fromParty.id] || {};
      const verb = d.step === 0 ? "Please complete" : "Signature needed";
      mails.push({
        id: d.id, project_id: p.id, from_name: c.contact === "Facilities manager" ? `Facilities, ${c.name}` : `${c.contact} (${c.name})`, from_email: c.email,
        subject: `${verb}: ${d.name} - ${p.name} (${p.id})`, department: d.department, date: state.cal.date(Math.min(0, d.sent_at)),
        snippet: d.step === 0 ? `We need the ${d.name.toLowerCase()} from EQORE before ${d.task.name.toLowerCase()} can go ahead.` : `Attached is the ${d.name.toLowerCase()} for your signature.`,
        due: d.due, link: null, demo: true,
      });
    }));
    return mails.sort((a, b) => b.date.localeCompare(a.date));
  }

  // ---------- Contractor availability ----------
  // Busy work-day ranges for a company: its open EQORE tasks on any project plus outside bookings.
  function busy(state, companyId) {
    const r = state.tasks.filter((t) => t.owner_id === companyId && !t.done).map((t) => ({ s: t.fc.s, f: t.fc.f, note: t.id.split(":")[0] }));
    return r.concat((state.byCompany[companyId].bookings || []));
  }
  // Earliest start at or after `from` with `days` consecutive work days where fewer than `crews` jobs overlap.
  function earliestFree(state, companyId, from, days) {
    const c = state.byCompany[companyId];
    const ranges = busy(state, companyId);
    const load = (i) => ranges.filter((r) => r.s <= i && i <= r.f).length;
    for (let s = Math.max(0, from); s < from + 120; s++) {
      let ok = true;
      for (let i = s; i < s + days; i++) if (load(i) >= c.crews) { ok = false; s = i; break; }
      if (ok) return s;
    }
    return null;
  }

  // Filters: trade, step (template key -> its role), name, available between from..to (work-day indices) for `days`.
  function searchCompanies(state, f, project) {
    const trade = f.step ? state.D.TEMPLATE.find((t) => t.key === f.step).role : f.trade;
    const q = (f.name || "").trim().toLowerCase();
    return state.companies
      .filter((c) => !trade || c.trade === trade)
      .filter((c) => !q || c.name.toLowerCase().includes(q) || c.contact.toLowerCase().includes(q) || c.city.toLowerCase().includes(q))
      .filter((c) => !f.state || c.state === f.state)
      .map((c) => {
        const from = f.from != null ? f.from : 0;
        const free = earliestFree(state, c.id, from, f.days || 1);
        const available = free != null && (f.to == null || free + (f.days || 1) - 1 <= f.to);
        const dist = project ? Math.round(miles(c, project)) : null;
        return { company: c, free, free_date: free != null ? state.cal.date(free) : null, available, distance: dist, in_range: dist == null || dist <= c.radius_mi,
          jobs: state.tasks.filter((t) => t.owner_id === c.id && !t.done && t.fc.s <= 10).length };
      })
      .filter((r) => !f.only_available || r.available)
      .sort((a, b) => (b.available - a.available) || ((a.distance || 0) - (b.distance || 0)) || a.company.name.localeCompare(b.company.name));
  }

  const portfolio = (state, pmId) => state.projects.filter((p) => p.pm_id === pmId);

  const api = { build, forecast, calendar, portfolio, subcontractors, taskState, updates, calendarItems, demoInbox, searchCompanies, earliestFree, busy,
    URGENCY, urgencyOf, miles, addDays, addWorkdays, nextWorkday, isWorkday, slug };
  root.EQORE_PM = api;
  if (typeof module !== "undefined") module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
