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
  const fmtDate = (s) => parse(s).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
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
  // ov: the PM's saved edits (custom companies, contact edits, and per project: products, step owners,
  // added contractors, added and edited documents). Everything else is generated from data.js.
  // paper: the document center's feed (GET /api/paperwork/documents). When present, it is the only source of documents.
  function build(D, today, ov, paper) {
    ov = normalize(ov);
    const cal = calendar(today);
    const companies = D.COMPANIES.map(([id, name, trade, state, city, lat, lng, crews, day_rate, rating, certifications, radius_mi, contact]) => ({
      id, name, trade, state, city, lat, lng, crews, day_rate, rating, certifications, radius_mi, contact,
      email: slug(contact.split(" ")[0]) + "@" + slug(name.replace(/\(.*\)/, "").replace(/ (Co\.|Inc\.)$/, "")) + ".demo.example",
      bookings: D.OUTSIDE_BOOKINGS.filter((b) => b[0] === id).map(([, s, n]) => ({ s, f: s + n - 1, note: "Booked with another client" })),
    }));
    Object.values(ov.companies).forEach((c) => companies.push(customCompany(c)));
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
    Object.entries(ov.company_edits).forEach(([id, e]) => byCompany[id] && Object.assign(byCompany[id], pick(e, ["contact", "email", "phone", "notes"])));

    const tasks = [];
    projects.forEach((p) => {
      D.TEMPLATE.forEach((t) => {
        const ps = p.P + rel[t.key].s, pf = p.P + rel[t.key].f;
        const issue = D.ISSUES.find((x) => x[0] === p.id && x[1] === t.key);
        const task = {
          id: `${p.id}:${t.key}`, project_id: p.id, key: t.key, short: t.short, name: t.name, phase: t.phase, role: t.role,
          description: (D.STEP_INFO || {})[t.key] || "",
          owner_id: ownerOverride(ov, byCompany, p.id, t.key) || p.parties[t.role],
          default_owner_id: p.parties[t.role], duration: t.duration, preds: t.preds.map((k) => `${p.id}:${k}`),
          planned: { s: ps, f: pf }, done: pf < 0 && !issue, started: ps <= 0,
          issue: issue ? { extra: issue[2], reported: -issue[3], text: issue[4] } : null,
        };
        tasks.push(task);
      });
    });

    const state = { D, cal, pms, companies, byCompany, projects, tasks, rel, ov, paper: paper && paper.projects ? paper : null };
    forecast(state);
    // Products: the PM's saved list, or generated from where the project is. Undelivered products hold back the step they're needed for.
    projects.forEach((p) => {
      p.tasks = tasks.filter((t) => t.project_id === p.id);
      const saved = ov.projects[p.id] && ov.projects[p.id].products;
      p.products = saved ? clone(saved) : seedProducts(state, p);
    });
    projects.forEach((p) => p.products.forEach((pr) => {
      const t = p.tasks.find((x) => x.key === pr.needed_for);
      if (!t || t.done || productRank(pr) >= 5 || !pr.expected_date) return;
      t.not_before = Math.max(t.not_before == null ? -Infinity : t.not_before, Math.max(0, cal.index(pr.expected_date)) + 1);
    }));
    forecast(state);
    projects.forEach((p) => derive(state, p));
    return state;
  }

  const clone = (o) => JSON.parse(JSON.stringify(o));
  const pick = (o, keys) => Object.fromEntries(keys.filter((k) => o[k] != null).map((k) => [k, String(o[k])]));
  function normalize(ov) {
    ov = ov && typeof ov === "object" ? ov : {};
    return { companies: ov.companies || {}, company_edits: ov.company_edits || {}, projects: ov.projects || {}, seq: ov.seq || 0 };
  }
  function ownerOverride(ov, byCompany, projectId, key) {
    const id = ov.projects[projectId] && ov.projects[projectId].owners && ov.projects[projectId].owners[key];
    return id && byCompany[id] ? id : null;
  }
  function customCompany(c) {
    return { id: c.id, name: c.name, trade: c.trade || "supplier", state: c.state || "", city: c.city || "", lat: null, lng: null, crews: 1, day_rate: 0,
      rating: null, certifications: [], radius_mi: 0, contact: c.contact || "", email: c.email || "", phone: c.phone || "", notes: c.notes || "", bookings: [], custom: true };
  }

  // ---------- Products ----------
  const PRODUCT_STATUSES = ["Not ordered", "Quoted", "Ordered", "In production", "Shipped", "Delivered", "Installed"];
  const productRank = (pr) => PRODUCT_STATUSES.indexOf(pr.status);
  function seedProducts(state, p) {
    const { D, cal } = state;
    const task = (k) => p.tasks.find((t) => t.key === k);
    const proc = task("procurement"), equip = task("equipment");
    return D.PRODUCTS.map(([key, name, category, sup, qty, unit, needed_for, lead], n) => {
      const need = task(needed_for);
      const supplier_id = sup === "switchgear" ? (p.state === "MA" ? "SU-BAYSW" : "SU-PACSW") : state.byCompany[sup] ? sup : p.parties[sup];
      const quantity = typeof qty === "number" ? qty : Math.max(1, Math.round((qty.startsWith("kwh") ? p.kwh : p.kw) / 250));
      let status, order, prom, exp, delivered = null;
      if (lead === "procurement") {
        order = proc.planned.s; prom = key === "switchgear" ? proc.planned.f - 5 : proc.planned.f;
        exp = key === "switchgear" ? prom : proc.fc.f;
        if (proc.done) { status = need.done ? "Installed" : "Delivered"; delivered = exp; }
        else if (proc.fc.s <= 0) { const frac = -proc.fc.s / (proc.fc.f - proc.fc.s + 1); status = frac < 0.35 ? "Ordered" : frac < 0.8 ? "In production" : "Shipped"; }
        else status = equip.done ? "Quoted" : "Not ordered";
      } else {
        exp = prom = need.fc.s - lead; order = prom - 10;
        if (need.done) { status = "Installed"; delivered = prom; }
        else if (need.fc.s <= 0 || prom < 0) { status = "Delivered"; delivered = prom; }
        else status = need.fc.s <= 25 ? "Ordered" : "Not ordered"; // small items are ordered about five weeks ahead
      }
      const rank = PRODUCT_STATUSES.indexOf(status);
      return {
        id: `${p.id}:p:${key}`, key, name, category, supplier_id, quantity, unit, needed_for, status,
        po_number: rank >= 2 ? `PO-${p.id.slice(4)}-${String(n + 1).padStart(2, "0")}` : "",
        order_date: rank >= 2 ? cal.date(order) : "", promised_date: rank >= 1 ? cal.date(prom) : "", expected_date: rank >= 1 ? cal.date(exp) : "",
        delivered_date: delivered != null ? cal.date(delivered) : "", tracking: status === "Shipped" ? "PRO " + (100000 + (hash(p.id + key) % 900000)) : "",
        notes: "", custom: false,
      };
    });
  }
  // delivered | overdue | delayed (later than promised) | at_risk (arrives after the step that needs it starts) | order_now | pending | on_track
  function productState(state, p, pr) {
    const { cal } = state;
    const need = p.tasks.find((t) => t.key === pr.needed_for);
    const needIdx = need && !need.done ? need.fc.s : null;
    const rank = productRank(pr);
    const exp = pr.expected_date ? cal.index(pr.expected_date) : null, prom = pr.promised_date ? cal.index(pr.promised_date) : null;
    const base = { need, need_date: needIdx != null ? cal.date(needIdx) : null, exp, prom, red: false, days: 0 };
    if (rank >= 5) return { ...base, key: "delivered" };
    if (exp != null && exp < 0) return { ...base, key: "overdue", red: true, days: -exp };
    if (exp != null && prom != null && exp > prom) return { ...base, key: "delayed", red: true, days: exp - prom };
    if (exp != null && needIdx != null && exp >= needIdx) return { ...base, key: "at_risk", red: true, days: exp - needIdx + 1 };
    if (rank <= 1 && needIdx != null && needIdx <= 20) return { ...base, key: "order_now" };
    if (rank === 0) return { ...base, key: "pending" };
    return { ...base, key: "on_track" };
  }

  // Paperwork for each product: purchase order, spec sheet (equipment), and the delivery receipt.
  function productDocs(state, p) {
    const proc = p.tasks.find((t) => t.key === "procurement");
    const cal = state.cal, docs = [];
    p.products.forEach((pr) => {
      const rank = productRank(pr), sup = party(state, p, pr.supplier_id), pm = party(state, p, p.pm_id);
      const at = (d, fallback) => (d ? cal.index(d) : fallback);
      const make = (suffix, name, flow, status, due, history) => docs.push({ id: `${pr.id}:${suffix}`, name, task: proc, project_id: p.id, flow, step: 0,
        status, next: status === "complete" ? null : flow[0], due: status === "complete" ? null : due, history,
        department: "Procurement", product_id: pr.id, sent_at: history.length ? history[history.length - 1].at : -1 });
      const orderAt = at(pr.order_date, 0);
      make("po", `Purchase order: ${pr.name}`, [pm, sup], rank >= 2 ? "complete" : rank === 1 ? "waiting" : "not_started",
        rank === 1 ? Math.max(0, at(pr.promised_date, 30) - 30) : orderAt,
        rank >= 2 ? [{ at: orderAt, by: pm.id, action: "Signed" }, { at: orderAt + 1, by: sup.id, action: "Signed" }] : []);
      if (["Battery storage", "Inverter / PCS", "Switchgear", "Transformer"].includes(pr.category))
        make("spec", `Spec sheet and certification: ${pr.name}`, [sup], rank >= 1 ? "complete" : "not_started", null,
          rank >= 1 ? [{ at: Math.min(-1, orderAt - 3), by: sup.id, action: "Filled out and sent" }] : []);
      const exp = at(pr.expected_date, 0), del = at(pr.delivered_date, exp);
      make("receipt", `Bill of lading and delivery receipt: ${pr.name}`, [sup, pm], rank >= 5 ? "complete" : rank === 4 ? "waiting" : "not_started", exp,
        rank >= 5 ? [{ at: del, by: sup.id, action: "Filled out and sent" }, { at: del, by: pm.id, action: "Signed" }] : []);
    });
    return docs;
  }

  function party(state, p, id) {
    const label = id === p.pm_id ? "PM" : /^CUST-/.test(id) ? "Customer" : "Contractor";
    return { role: label === "PM" ? "PM" : label === "Customer" ? "customer" : (state.byCompany[id] || {}).trade, id, label };
  }

  // The PM's added documents and edits to any document.
  function applyDocEdits(state, p, docs) {
    const po = state.ov.projects[p.id] || {}, cal = state.cal;
    const taskFor = (k) => p.tasks.find((t) => t.key === k) || p.current[0] || p.tasks[0];
    (po.docs_added || []).forEach((a) => {
      const t = taskFor(a.step);
      docs.push({ id: a.id, name: a.name, task: t, project_id: p.id, flow: [], step: 0, status: "waiting", next: null, due: t.fc.f, history: [],
        department: state.D.DEPARTMENTS[t.key], product_id: a.product_id || null, sent_at: -1, custom: true });
    });
    docs.forEach((d) => {
      const e = d.custom ? (po.docs_added || []).find((a) => a.id === d.id) : (po.doc_edits || {})[d.id];
      if (!e) return;
      d.edited = true;
      if (e.name) d.name = e.name;
      if (e.product_id !== undefined) d.product_id = e.product_id || null;
      if (e.step && e.step !== d.task.key) d.task = taskFor(e.step);
      if (e.step || e.product_id !== undefined) d.department = d.product_id ? "Procurement" : state.D.DEPARTMENTS[d.task.key];
      if (e.notes != null) d.notes = e.notes;
      if (!e.status) return;
      d.status = e.status;
      if (e.status === "complete") {
        d.next = null; d.due = null; d.step = d.flow.length;
        if (e.completed_date) d.history = d.history.concat({ at: cal.index(e.completed_date), by: p.pm_id, action: "Marked complete" });
      } else {
        const who = party(state, p, e.next_id || (d.next && d.next.id) || p.pm_id);
        if (!d.flow.some((x) => x.id === who.id)) d.flow = d.flow.concat(who);
        d.next = who; d.step = d.flow.findIndex((x) => x.id === who.id);
        d.due = e.due_date ? cal.index(e.due_date) : d.due != null ? d.due : d.task.fc.f;
      }
    });
    return docs.filter((d) => !(po.docs_removed || []).includes(d.id));
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
        s = Math.max(t.planned.s, after, t.not_before == null ? -Infinity : t.not_before);
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
    p.product_states = Object.fromEntries(p.products.map((pr) => [pr.id, productState(state, p, pr)]));
    p.docs = state.paper && state.paper.projects[p.id] ? paperDocs(state, p) : applyDocEdits(state, p, documents(state, p).concat(productDocs(state, p)));
    p.todos = todos(state, p);
    const pmTodo = p.todos.find((x) => x.urgency <= 2 && x.kind !== "chase");
    if (p.slip > 0) p.status = "red";
    else if (pmTodo) p.status = "yellow";
    else p.status = "green";
    const top = p.issues[0], lateProduct = p.products.find((pr) => p.product_states[pr.id].red);
    const reason = top ? ": " + top.text : lateProduct && lateProduct.expected_date ? `: ${lateProduct.name} now expected ${fmtDate(lateProduct.expected_date)}.` : "";
    p.status_text = p.status === "red" ? `Behind schedule by ${p.slip} work day${p.slip === 1 ? "" : "s"}${reason}`
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
        const parties = flow.map((role) => (role === "PM" ? { role, id: p.pm_id, label: "PM" } : { role, id: role === t.role ? t.owner_id : p.parties[role], label: role === "customer" ? "Customer" : "Contractor" }));
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
      out.push({ kind: "doc", urgency: urgencyOf(d.due), due: d.due, title: d.action_title || `${d.step === 0 ? "Fill out" : "Sign"}: ${d.name}`, detail: d.task.name === d.department ? `${d.task.name}.` : `${d.task.name}. ${d.department}.`, doc: d, party: null }));
    p.tasks.filter((t) => !t.done && t.role === "eqore" && t.key !== "controls" && t.fc.s <= 5).forEach((t) =>
      out.push({ kind: "task", urgency: urgencyOf(t.fc.s <= 0 ? t.fc.f : t.fc.s), due: t.fc.s <= 0 ? t.fc.f : t.fc.s, title: t.key === "precon" ? "Run pre-construction scheduling: book crew, crane and the shutdown window" : t.name, detail: t.phase, task: t }));
    p.products.forEach((pr) => {
      const st = p.product_states[pr.id], sup = state.byCompany[pr.supplier_id];
      if (st.red) out.push({ kind: "product", urgency: st.key === "overdue" ? 1 : 2, due: st.exp != null ? st.exp : 0,
        title: `${st.key === "at_risk" ? "Delivery expected too late" : st.key === "overdue" ? "Delivery overdue" : "Delivery delayed"}: ${pr.name}`,
        detail: `${sup ? sup.name : "Supplier"}. Needed for ${st.need ? st.need.name.toLowerCase() : "the project"}.`, party: pr.supplier_id, product: pr });
      else if (st.key === "order_now") out.push({ kind: "product", urgency: 2, due: Math.max(0, st.need.fc.s - 15), title: `Order: ${pr.name}`,
        detail: `Needed for ${st.need.name.toLowerCase()}.`, party: pr.supplier_id, product: pr });
    });
    p.docs.filter((d) => d.status === "waiting" && d.next.label !== "PM" && d.due <= 3).forEach((d) =>
      out.push({ kind: "chase", urgency: d.due < 0 ? 2 : 4, due: d.due, title: `Chase ${state.byCompany[d.next.id].name}: ${d.name}`, detail: `Waiting on the ${d.next.label.toLowerCase()} to ${d.step === d.flow.length - 1 ? "sign" : "fill out"}.`, doc: d, party: d.next.id }));
    return out.sort((a, b) => a.urgency - b.urgency || a.due - b.due);
  }

  // ---------- Subcontractors on a project ----------
  function subcontractors(state, p) {
    const added = ((state.ov.projects[p.id] || {}).contractors_added || []).filter((id) => state.byCompany[id]);
    const ids = [...new Set(p.tasks.filter((t) => t.role !== "eqore" && t.role !== "customer").map((t) => t.owner_id).concat(added))];
    return ids.map((id) => {
      const c = state.byCompany[id];
      const tasks = p.tasks.filter((t) => t.owner_id === id).map((t) => ({ task: t, state: taskState(t) }));
      const docs = p.docs.filter((d) => d.flow.some((x) => x.id === id));
      const open = docs.filter((d) => d.status === "waiting" && d.next.id === id);
      const delayed = tasks.filter((x) => x.state === "problem"); // their own reported delay
      const pushed = tasks.filter((x) => x.state === "late"); // moved by a delay upstream
      return { company: c, tasks, docs, open, delayed, pushed, added: added.includes(id) };
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
      q.products.filter((pr) => productRank(pr) < 5 && pr.expected_date && pr.expected_date >= cal.today).forEach((pr) =>
        items.push({ date: pr.expected_date, kind: "delivery", title: `Delivery: ${pr.name}`, project_id: q.id, owner: pr.supplier_id, product_id: pr.id, state: q.product_states[pr.id].red ? "late" : "" }));
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
      .filter((c) => !q || [c.name, c.contact, c.city].some((x) => (x || "").toLowerCase().includes(q)))
      .filter((c) => !f.state || c.state === f.state)
      .map((c) => {
        const from = f.from != null ? f.from : 0;
        const free = earliestFree(state, c.id, from, f.days || 1);
        const available = free != null && (f.to == null || free + (f.days || 1) - 1 <= f.to);
        const dist = project && c.lat != null ? Math.round(miles(c, project)) : null;
        return { company: c, free, free_date: free != null ? state.cal.date(free) : null, available, distance: dist, in_range: dist == null || dist <= c.radius_mi,
          jobs: state.tasks.filter((t) => t.owner_id === c.id && !t.done && t.fc.s <= 10).length };
      })
      .filter((r) => !f.only_available || r.available)
      .sort((a, b) => (b.available - a.available) || ((a.distance || 0) - (b.distance || 0)) || a.company.name.localeCompare(b.company.name));
  }

  // ---------- Document center (Yichang's records) ----------
  // His documents, in the shape the dashboards, to-dos, inbox and popups use.
  function paperDocs(state, p) {
    const feed = state.paper.projects[p.id], cal = state.cal;
    const people = Object.fromEntries(feed.stakeholders.map((x) => [x.id, x]));
    const idx = (iso) => (iso ? cal.index(String(iso).slice(0, 10)) : null);
    const partyOf = (sid) => {
      if (sid === p.pm_id) return { id: p.pm_id, label: "PM", role: "PM" };
      const st = people[sid] || { id: sid, name: sid };
      if (st.company_id && state.byCompany[st.company_id]) {
        const c = state.byCompany[st.company_id];
        return { id: c.id, label: /^CUST-/.test(c.id) ? "Customer" : "Contractor", role: c.trade, stakeholder: sid };
      }
      if (!state.byCompany[sid]) state.byCompany[sid] = { id: sid, name: st.organization && st.organization !== st.name ? `${st.name} (${st.organization})` : st.name,
        contact: st.name, email: st.email || "", trade: st.organization === "EQORE" ? "eqore" : "contact", bookings: [], crews: 1, certifications: [], city: "", state: "" };
      return { id: sid, label: st.organization === "Customer" ? "Customer" : "Contractor", role: "contact", stakeholder: sid };
    };
    const ACTION = { esign: "Signed", review: "Review accepted", record: "Record received" };
    return feed.documents.map((d) => {
      const owner = partyOf(d.owner_id);
      const recips = d.recipients.map((r) => ({ ...partyOf(r.id), r }));
      const flow = [owner].concat(recips.filter((x, i) => x.id !== owner.id && recips.findIndex((y) => y.id === x.id) === i));
      let status = "waiting", next = owner;
      if (d.status === "completed") { status = "complete"; next = null; }
      else if (d.status === "blocked") status = "not_started";
      else if (["sent", "partially_signed"].includes(d.status)) next = recips.find((x) => x.r.status === "pending") || owner;
      const history = recips.filter((x) => x.r.signed_at || x.r.responded_at)
        .map((x) => ({ at: idx(x.r.signed_at || x.r.responded_at), by: x.id, action: x.r.status === "pending" ? "Responded" : ACTION[d.kind] }))
        .sort((a, b) => a.at - b.at);
      const task = p.tasks.find((t) => t.key === d.step) || p.tasks.find((t) => t.key === "procurement");
      return { id: d.id, name: d.title, task, project_id: p.id, flow, step: next ? Math.max(0, flow.findIndex((x) => x.id === next.id)) : flow.length,
        status, next, due: status === "complete" ? null : idx(d.due_at), history, department: d.phase, product_id: d.product_id || null, notes: d.notes || "",
        kind: d.kind, paper: d, action_title: d.next_action && d.next_action.title, action_reason: d.next_action && d.next_action.reason,
        sent_at: d.sent_at ? idx(d.sent_at) : -1 };
    });
  }

  // What the document center needs to create a project's records the first time: who the stakeholders are, and for
  // each document its step, due date, whether it is already complete and whether it is under way, from the timeline.
  function paperPlan(state, p) {
    const { D, cal } = state;
    const task = (k) => p.tasks.find((t) => t.key === k);
    const point = (k, frac) => { const t = task(k); return Math.round(t.fc.s + frac * (t.fc.f - t.fc.s)); };
    const issueOn = (k) => p.issues.find((x) => x.task.key === k);
    const at = {};
    Object.keys(D.DOC_MAP).forEach((id) => {
      const [k, frac] = D.DOC_MAP[id];
      let v = point(k, frac);
      if (issueOn(k) && !task(k).done) v = Math.max(v, 0); // a reported problem on the step keeps its paperwork open
      (D.DOC_PREREQS[id] || []).forEach((q) => (v = Math.max(v, at[q])));
      at[id] = v;
    });
    const documents = Object.keys(D.DOC_MAP).map((id) => {
      const [k] = D.DOC_MAP[id], t = task(k), complete = at[id] < 0;
      const ready = (D.DOC_PREREQS[id] || []).every((q) => at[q] < 0);
      let opening = null, opening_text;
      if (!complete && ready && t.fc.s <= 0) {
        const issue = issueOn(k);
        if (issue) { opening = "returned"; opening_text = issue.text; }
        else opening = D.DOC_KINDS[id] === "esign" && hash(p.id + id) % 2 ? "partial" : "sent";
      }
      return { id, step: k, due_at: cal.date(at[id]), completed_at: complete ? cal.date(at[id]) : null, opening, opening_text };
    });
    const company = (id, role, name) => { const c = state.byCompany[id]; return c ? { name: name || c.contact || c.name, role, organization: c.name, email: c.email, company_id: c.id } : undefined; };
    const proc = task("procurement");
    const past = (d) => (d && d < cal.today ? d : null);
    p.products.forEach((pr) => {
      const rank = productRank(pr), sup = state.byCompany[pr.supplier_id] || {};
      const who = { company_id: pr.supplier_id, name: sup.contact || sup.name || "Supplier", organization: sup.name || "Supplier", email: sup.email || "", role: D.TRADES[sup.trade] || "Supplier" };
      const base = "P-" + pr.id.split(":p:")[1];
      const orderDue = pr.order_date || cal.date(Math.max(0, proc.fc.s));
      documents.push({ id: `${base}-po`, title: `Purchase order: ${pr.name}`, kind: "esign", phase: "Procurement", owner_role: "pm", recipient_roles: ["commercial"], recipients: [who],
        step: "procurement", product_id: pr.id, due_at: orderDue, completed_at: rank >= 2 ? past(pr.order_date) : null, opening: rank === 1 ? "draft" : null });
      if (["Battery storage", "Inverter / PCS", "Switchgear", "Transformer"].includes(pr.category))
        documents.push({ id: `${base}-spec`, title: `Spec sheet and certification: ${pr.name}`, kind: "record", phase: "Procurement", owner_role: "pm", recipients: [who],
          step: "equipment", product_id: pr.id, due_at: orderDue, completed_at: rank >= 1 ? past(pr.order_date ? addDays(pr.order_date, -3) : addDays(cal.today, -1)) : null });
      documents.push({ id: `${base}-receipt`, title: `Bill of lading and delivery receipt: ${pr.name}`, kind: "record", phase: "Procurement", owner_role: "pm", recipients: [who],
        step: pr.needed_for, product_id: pr.id, due_at: pr.expected_date || pr.promised_date || cal.date(Math.max(0, proc.fc.f)),
        completed_at: rank >= 5 ? past(pr.delivered_date || pr.expected_date) : null, opening: rank === 4 ? "sent" : null });
    });
    const inspector = company(`IN-${p.state}`, "AHJ record issuer");
    return {
      id: p.id, pm_id: p.pm_id, name: p.name, site: `${p.city}, ${p.state}`,
      profile: { system_power_kw: p.kw, system_energy_kwh: p.kwh, contract_date: cal.date(task("contract").fc.f), target_handover_date: p.target_date,
        utility: (state.byCompany[p.utility_id] || {}).name, scope: `Behind-the-meter battery (${p.kw} kW / ${p.kwh} kWh): pad, placement, electrical tie-in, commissioning and utility permission to operate.`,
        site_constraints: [] },
      stakeholders: {
        customer: { name: "Customer signatory", role: "Customer signatory", organization: p.name, email: p.customer.email, company_id: p.customer.id },
        facilities: { name: "Facilities manager", role: "Facilities and operations lead", organization: p.name, email: p.customer.email, company_id: p.customer.id },
        epc: company(p.parties.civil, "Site works lead (EPC)"), engineer: company(p.parties.engineering, "Responsible design engineer"),
        electrician: company(task("electrical").owner_id, "Electrical contractor"), rigger: company(task("placement").owner_id, "Rigging supervisor"),
        supplier: company("SU-QPACK", "Equipment supplier"), ahj: inspector, fire: inspector && { ...inspector, name: "Fire marshal", role: "Fire record issuer" },
        utility: company(p.utility_id, "Utility record issuer", "Interconnection desk"),
      },
      documents,
    };
  }

  const portfolio = (state, pmId) => state.projects.filter((p) => p.pm_id === pmId);

  const api = { build, forecast, calendar, portfolio, paperPlan, paperDocs, subcontractors, taskState, productState, productRank, seedProducts, party, PRODUCT_STATUSES, updates, calendarItems, demoInbox, searchCompanies, earliestFree, busy,
    URGENCY, urgencyOf, miles, addDays, addWorkdays, nextWorkday, isWorkday, slug };
  root.EQORE_PM = api;
  if (typeof module !== "undefined") module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
