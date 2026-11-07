// EQORE PM platform: the app (login, portfolio map, project dashboards, procurement, subcontractors).
// Look and components come from ../eqore-demo/web/styles.css; portal-only rules are in styles.css.
(function () {
  const D = window.EQORE_PM_DATA, M = window.EQORE_PM;
  const $app = document.getElementById("app"), $modal = document.getElementById("modal-root"), $toast = document.getElementById("toast");
  const today = new Date().toLocaleDateString("en-CA");
  let S = M.build(D, today);
  let WS = { version: 0, data: {} }; // this PM's saved edits (products, documents, contractors)
  let me = null, map = null;
  const cache = { inbox: null, inboxError: null, gcal: {}, gcalError: null };

  // ---------- helpers ----------
  const esc = (v) => String(v == null ? "" : v).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const parse = (s) => new Date(s + "T00:00:00");
  const fmt = (s, opt) => (s ? parse(s).toLocaleDateString("en-US", opt || { month: "short", day: "numeric" }) : "");
  const fmtI = (i) => fmt(S.cal.date(i));
  const company = (id) => S.byCompany[id] || (/^PM-/.test(id) ? { name: "You (EQORE PM)", contact: "", email: "" } : { name: id, contact: "", email: "" });
  const project = (id) => S.projects.find((p) => p.id === id);
  const mine = () => M.portfolio(S, me.pm_id);
  const STATUS = { green: { label: "On schedule", badge: "green" }, yellow: { label: "Action needed", badge: "gold" }, red: { label: "Behind schedule", badge: "red" } };
  const TASK_STATE = { done: ["Done", "green"], active: ["In progress", "live"], upcoming: ["Upcoming", "outline"], at_risk: ["At risk", "gold"], late: ["Pushed back", "orange"], problem: ["Delayed", "red"] };
  const URG_BADGE = { 1: "red", 2: "orange", 3: "gold", 4: "outline" };
  const icon = (d) => `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">${d}</svg>`;
  const I = {
    map: icon('<path d="M9 4 3 6v14l6-2 6 2 6-2V4l-6 2-6-2z"/><path d="M9 4v14M15 6v14"/>'),
    grid: icon('<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>'),
    line: icon('<path d="M3 12h18"/><circle cx="6" cy="12" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="18" cy="12" r="2"/>'),
    cal: icon('<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>'),
    mail: icon('<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/>'),
    check: icon('<path d="M9 11l3 3 8-8"/><path d="M20 12v7a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h9"/>'),
    doc: icon('<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6M8 13h8M8 17h5"/>'),
    people: icon('<circle cx="9" cy="8" r="3"/><path d="M3 20c0-3 3-5 6-5s6 2 6 5"/><circle cx="17" cy="9" r="2.5"/><path d="M16 15c3 0 5 2 5 4"/>'),
    out: icon('<path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4M10 17l-5-5 5-5M5 12h11"/>'),
    ext: icon('<path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>'),
    search: icon('<circle cx="11" cy="11" r="6"/><path d="m20 20-4-4"/>'),
    warn: icon('<path d="M12 3 2 20h20z"/><path d="M12 10v4M12 17v.5"/>'),
    left: icon('<path d="m15 18-6-6 6-6"/>'), right: icon('<path d="m9 18 6-6-6-6"/>'),
    box: icon('<path d="M21 8 12 3 3 8v8l9 5 9-5z"/><path d="m3 8 9 5 9-5M12 13v8"/>'),
    plus: icon('<path d="M12 5v14M5 12h14"/>'), edit: icon('<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="m14 6 4 4"/>'),
  };
  function toast(text, error) {
    $toast.textContent = text; $toast.className = "toast show" + (error ? " error" : "");
    clearTimeout(toast.t); toast.t = setTimeout(() => ($toast.className = "toast"), 4200);
  }
  async function api(path, opts) {
    const r = await fetch(path, Object.assign({ credentials: "same-origin", headers: { "Content-Type": "application/json" } }, opts || {}));
    const body = await r.json().catch(() => ({}));
    if (!r.ok) throw Object.assign(new Error(body.error || `Request failed (${r.status})`), { status: r.status });
    return body;
  }
  const inboxLink = () => (me && me.mode === "google" ? `https://mail.google.com/mail/u/?authuser=${encodeURIComponent(me.email)}` : "https://mail.google.com/mail/u/0/#inbox");
  const calendarLink = () => (me && me.mode === "google" ? `https://calendar.google.com/calendar/u/?authuser=${encodeURIComponent(me.email)}` : "https://calendar.google.com/");

  // ---------- data: inbox and calendar (real Gmail / Google Calendar, or the demo set) ----------
  function matchProject(item) {
    const text = (item.subject + " " + item.snippet).toLowerCase();
    const hit = mine().find((p) => text.includes(p.id.toLowerCase()) || text.includes(p.name.toLowerCase()));
    return hit ? hit.id : null;
  }
  async function loadInbox() {
    if (cache.inbox) return cache.inbox;
    if (me.mode !== "google") return (cache.inbox = { mode: "demo", items: M.demoInbox(S, mine()) });
    try {
      const r = await api("/api/inbox");
      r.items.forEach((x) => (x.project_id = matchProject(x)));
      cache.inboxError = null;
      return (cache.inbox = r);
    } catch (e) { cache.inboxError = e.message; return { mode: "google", items: [], error: e.message }; }
  }
  async function loadGoogleCalendar(from, to) {
    if (me.mode !== "google") return [];
    const key = from + to;
    if (cache.gcal[key]) return cache.gcal[key];
    try { const r = await api(`/api/calendar?from=${from}&to=${to}`); cache.gcalError = null; return (cache.gcal[key] = r.events.map((e) => ({ ...e, kind: "google" }))); }
    catch (e) { cache.gcalError = e.message; return []; }
  }

  // ---------- routing ----------
  function route() {
    const h = location.hash.replace(/^#\/?/, "");
    const [path, query] = h.split("?");
    const parts = path.split("/").filter(Boolean);
    return { parts, query: new URLSearchParams(query || "") };
  }
  async function render() {
    if (map) { map.remove(); map = null; }
    const { parts, query } = route();
    if (!me || !me.signed_in) return renderLogin(query.get("error"));
    if (parts[0] === "project" && project(parts[1]) && project(parts[1]).pm_id === me.pm_id) return renderProject(project(parts[1]), parts[2] || "overview", query);
    if (parts[0] === "login") { location.hash = "#/portfolio"; return; }
    return renderPortfolio(query);
  }
  window.addEventListener("hashchange", () => { closeModal(); render(); window.scrollTo(0, 0); });

  // ---------- login ----------
  function renderLogin(error) {
    const g = me && me.google_configured;
    $app.innerHTML = `
      <div class="login-shell">
        <aside class="login-side">
          <div class="brand"><div class="brand-mark">e</div><div><div class="brand-word">EQORE</div><div class="brand-subtitle">Deployment PM</div></div></div>
          <h2>Every battery project you run, on one map, with the next action on each.</h2>
          <p>Sign in with your work email. It signs you in here and connects your inbox and calendar in one step, so paperwork to sign and site meetings show up next to each project.</p>
          <ul><li>Portfolio map: green on schedule, yellow action needed, red behind</li><li>Project dashboards: timeline, calendar, paperwork, to-dos</li><li>Subcontractors: who did what, their documents, email them from here</li></ul>
          <p class="tiny">Projects, companies and people in this demo are synthetic.</p>
        </aside>
        <main class="login-main">
          <section class="panel login-card">
            <div class="panel-header"><div><h2>Sign in</h2><p>Use your work email.</p></div></div>
            <form class="panel-body" id="login-form" novalidate>
              ${error ? `<div class="notice error"><p>${esc(error)}</p></div>` : ""}
              <label class="field"><span>Work email</span><input id="login-email" type="email" autocomplete="email" required placeholder="you@company.com"></label>
              <label class="field" id="pw-field" hidden><span>Password</span><input id="login-password" type="password" autocomplete="current-password"><small>Demo accounts use the password <strong>demo</strong>.</small></label>
              <div class="form-actions"><button class="button" type="submit" id="login-submit">Continue</button></div>
              <p class="tiny muted" id="login-hint">${g ? "Google Workspace and Gmail accounts continue to Google's own sign-in page. EQORE never sees your Google password." : "Google sign-in isn't set up on this server yet (see pm/README.md). The demo accounts below work without it."}</p>
              <div class="demo-accounts"><div class="field-label">Demo accounts</div>
                ${D.PMS.map((p) => `<button type="button" class="demo-account" data-email="${esc(p.email)}"><strong>${esc(p.name)}</strong><small>${esc(p.region)} · ${esc(p.email)}</small></button>`).join("")}
              </div>
            </form>
          </section>
        </main>
      </div>`;
    const form = document.getElementById("login-form"), email = document.getElementById("login-email"), pw = document.getElementById("login-password"), pwField = document.getElementById("pw-field");
    const isDemo = () => D.PMS.some((p) => p.email === email.value.trim().toLowerCase());
    email.addEventListener("input", () => { pwField.hidden = !isDemo(); });
    form.querySelectorAll(".demo-account").forEach((b) => b.addEventListener("click", () => { email.value = b.dataset.email; pwField.hidden = false; pw.value = ""; pw.focus(); }));
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const value = email.value.trim();
      if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(value)) return toast("Enter your work email.", true);
      if (isDemo()) {
        if (pwField.hidden || !pw.value) { pwField.hidden = false; pw.focus(); return; }
        try { await api("/api/login", { method: "POST", body: JSON.stringify({ email: value, password: pw.value }) }); await boot("#/portfolio"); }
        catch (err) { toast(err.message, true); }
        return;
      }
      if (!g) return toast("Google sign-in isn't set up on this server. Use a demo account, or see pm/README.md.", true);
      location.href = "/auth/google/start?login_hint=" + encodeURIComponent(value);
    });
  }

  // ---------- shared chrome ----------
  function menu() {
    return `
      <div class="menu" id="main-menu">
        <button class="menu-button" aria-label="Menu" aria-haspopup="true"><span></span><span></span><span></span></button>
        <div class="menu-pop" role="menu">
          <a role="menuitem" href="#/portfolio">${I.map}Portfolio</a>
          <div class="menu-sub"><button role="menuitem" class="menu-sub-trigger">${I.grid}Dashboard<span class="menu-caret">›</span></button>
            <div class="menu-pop menu-pop-sub" role="menu">
              ${mine().map((p) => `<a role="menuitem" href="#/project/${p.id}"><i class="dot ${p.status}"></i><span>${esc(p.name)}<small>${p.id} · ${esc(p.city)}, ${p.state}</small></span></a>`).join("")}
            </div>
          </div>
          <button role="menuitem" data-action="logout">${I.out}Log out</button>
        </div>
      </div>`;
  }
  function userChip() {
    const initials = me.name.split(" ").map((x) => x[0]).slice(0, 2).join("").toUpperCase();
    return `<div class="user-chip"><div class="avatar">${esc(initials)}</div><div><strong>${esc(me.name)}</strong><small>${esc(me.email)} · ${me.mode === "google" ? '<span class="status-dot green"></span> Gmail connected' : "Demo inbox"}</small></div></div>`;
  }
  function topbar(crumbs) {
    return `<header class="topbar"><div class="breadcrumb">${crumbs}</div><div class="topbar-right">${userChip()}${menu()}</div></header>`;
  }

  // ---------- portfolio map ----------
  function renderPortfolio(query) {
    const ps = mine();
    const n = (c) => ps.filter((p) => p.status === c).length;
    const pm = D.PMS.find((x) => x.id === me.pm_id);
    $app.innerHTML = `
      <div class="page-shell">
        ${topbar(`<a class="brand-inline" href="#/portfolio"><span class="brand-mark">e</span><strong>EQORE</strong></a><span>/</span><strong>Portfolio</strong>`)}
        <main class="content">
          ${!me.in_roster ? `<div class="notice job"><p><strong>Your Google account is connected.</strong>It isn't linked to an EQORE portfolio in this demo, so you're seeing ${esc(pm.name)}'s sample projects. Your inbox and calendar are real.</p></div>` : ""}
          ${query.get("missing_scopes") ? `<div class="notice error"><p><strong>Some Google permissions weren't granted.</strong>Inbox, calendar or sending may not work. Log out and sign in again, and allow all the requested access.</p></div>` : ""}
          <div class="page-heading"><div><div class="eyebrow">${esc(pm.region)}</div><h1>${esc(me.name.split(" ")[0])}'s portfolio</h1><p>${ps.length} projects. Hover a dot to see its status, click it to open the project dashboard. Scroll or pinch to zoom.</p></div></div>
          <div class="stats">
            ${stat("Projects", ps.length, "in your portfolio")}
            ${stat("On schedule", n("green"), "green: on the timeline", "green")}
            ${stat("Action needed", n("yellow"), "yellow: something for you to do", "gold")}
            ${stat("Behind schedule", n("red"), "red: a problem is holding it up", "red")}
          </div>
          <section class="panel map-panel">
            <div id="map" role="region" aria-label="Map of your projects"></div>
            <div class="map-legend"><span><i class="dot green"></i>On schedule</span><span><i class="dot yellow"></i>Action needed</span><span><i class="dot red"></i>Behind schedule</span></div>
          </section>
          <section class="panel section-spacer">
            <div class="panel-header"><div><h2>Needs you first</h2><p>Red and yellow projects, worst first.</p></div></div>
            <div class="table-wrap"><table class="data-table"><thead><tr><th>Project</th><th>Status</th><th>Now</th><th>Go-live</th></tr></thead><tbody>
              ${ps.filter((p) => p.status !== "green").sort((a, b) => (a.status === b.status ? b.slip - a.slip : a.status === "red" ? -1 : 1)).map((p) => `
                <tr><td><a href="#/project/${p.id}"><strong>${esc(p.name)}</strong></a><div class="subline">${p.id} · ${esc(p.city)}, ${p.state}</div></td>
                <td><span class="badge ${STATUS[p.status].badge}">${STATUS[p.status].label}</span><div class="subline">${esc(p.status_text)}</div></td>
                <td>${p.current.map((t) => esc(t.name)).join(", ")}</td>
                <td class="nowrap">${fmt(p.go_live_date)}${p.slip > 0 ? `<div class="subline">target ${fmt(p.target_date)}</div>` : ""}</td></tr>`).join("")}
            </tbody></table></div>
          </section>
        </main>
      </div>`;
    drawMap(ps);
  }
  function stat(label, value, sub, tone) {
    return `<div class="stat ${tone ? "stat-" + tone : ""}"><div class="stat-top"><span>${label}</span></div><div class="stat-number">${value}</div><div class="stat-bottom">${sub}</div></div>`;
  }
  function drawMap(ps) {
    if (!window.L) { document.getElementById("map").innerHTML = `<div class="empty-state"><h3>The map couldn't load</h3><p>The map library comes from the internet. Check the connection and reload.</p></div>`; return; }
    map = L.map("map", { scrollWheelZoom: true, zoomControl: true, attributionControl: true });
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 18, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(map);
    const color = { green: "#2f9e6b", yellow: "#e0a526", red: "#c8452f" };
    const markers = ps.map((p) => {
      const m = L.circleMarker([p.lat, p.lng], { radius: 10, color: "#fff", weight: 2, fillColor: color[p.status], fillOpacity: 0.95 }).addTo(map);
      m.bindTooltip(`<div class="map-tip"><strong>${esc(p.name)}</strong><small>${p.id} · ${esc(p.city)}, ${p.state}</small><span class="badge ${STATUS[p.status].badge}">${STATUS[p.status].label}</span><p>${esc(p.status_text)}</p></div>`, { direction: "top", offset: [0, -8], opacity: 1, className: "map-tooltip" });
      m.on("click", () => (location.hash = `#/project/${p.id}`));
      m.on("mouseover", () => m.setStyle({ radius: 13 })); m.on("mouseout", () => m.setStyle({ radius: 10 }));
      return m;
    });
    map.fitBounds(L.featureGroup(markers).getBounds().pad(0.15));
    setTimeout(() => map && map.invalidateSize(), 50);
  }

  // ---------- project pages ----------
  const SECTIONS = [["overview", "Overview", I.grid], ["timeline", "Timeline", I.line], ["calendar", "Calendar", I.cal], ["inbox", "Inbox", I.mail], ["todo", "To do", I.check], ["procurement", "Procurement", I.box], ["documents", "Document center", I.doc], ["subcontractors", "Subcontractors", I.people]];
  function renderProject(p, section, query) {
    if (!SECTIONS.some((s) => s[0] === section)) section = "overview";
    const name = SECTIONS.find((s) => s[0] === section)[1];
    const counts = { todo: p.todos.filter((t) => t.kind !== "chase").length, procurement: p.products.filter((x) => p.product_states[x.id].red).length || "", subcontractors: M.subcontractors(S, p).filter((x) => x.delayed.length).length || "" };
    $app.innerHTML = `
      <div class="app-shell">
        <aside class="sidebar">
          <a class="brand" href="#/portfolio"><div class="brand-mark">e</div><div><div class="brand-word">EQORE</div><div class="brand-subtitle">Deployment PM</div></div></a>
          <div class="sidebar-caption">${p.id}</div>
          <div class="side-project"><strong>${esc(p.name)}</strong><small>${esc(p.city)}, ${p.state} · ${p.kw} kW / ${p.kwh} kWh</small><span class="badge ${STATUS[p.status].badge}">${STATUS[p.status].label}</span></div>
          <nav class="navigation">${SECTIONS.map(([k, label, ic]) => `<a class="nav-link ${k === section ? "active" : ""}" href="#/project/${p.id}${k === "overview" ? "" : "/" + k}">${ic}${label}${counts[k] ? `<span class="nav-count">${counts[k]}</span>` : ""}</a>`).join("")}</nav>
          <div class="sidebar-bottom"><a class="side-button secondary" href="#/portfolio">${I.map}Back to portfolio map</a></div>
        </aside>
        <div class="main">
          ${topbar(`<a href="#/portfolio">Portfolio</a><span>/</span><a href="#/project/${p.id}">${esc(p.name)}</a>${section === "overview" ? "" : `<span>/</span><strong>${name}</strong>`}`)}
          <main class="content" id="page"></main>
        </div>
      </div>`;
    const page = document.getElementById("page");
    const head = `<div class="page-heading"><div><div class="eyebrow">${p.id} · ${esc(p.city)}, ${p.state} · ${esc(company(p.utility_id).name.replace(" interconnection", ""))}</div><h1>${section === "overview" ? esc(p.name) : name}</h1><p>${esc(p.status_text)}</p></div>
      <div class="project-heading-right"><div class="eyebrow">Forecast go-live</div><div class="date ${p.slip > 0 ? "text-red" : ""}">${fmt(p.go_live_date, { month: "short", day: "numeric", year: "numeric" })}</div><div class="timezone">${p.slip > 0 ? `${p.slip} work days after target (${fmt(p.target_date)})` : "On target"}</div></div></div>`;
    const views = { overview, timeline: timelinePage, calendar: calendarPage, inbox: inboxPage, todo: todoPage, documents: documentsPage, subcontractors: subsPage, procurement: procurementPage };
    page.innerHTML = head + `<div id="view"></div>`;
    views[section](p, document.getElementById("view"), query || new URLSearchParams());
  }

  // Overview: timeline across the top; to-do and subcontractors on the left; calendar, inbox and document center on the right.
  function overview(p, el) {
    el.innerHTML = `
      <section class="panel">${timelineHeader(p)}<div class="panel-body">${timeline(p)}</div></section>
      <div class="overview-grid section-spacer">
        <div class="secondary-stack">
          <section class="panel">${panelHead("To do", "Documents and actions for you, by urgency", `#/project/${p.id}/todo`)}<div class="panel-body">${todoList(p, 6)}</div></section>
          <section class="panel">${panelHead("Subcontractors", "Their open items, delays and latest updates", `#/project/${p.id}/subcontractors`)}<div class="panel-body">${subsSummary(p)}</div></section>
          <section class="panel">${panelHead("Procurement", "Products for this project, delays and next deliveries", `#/project/${p.id}/procurement`)}<div class="panel-body">${procSummary(p)}</div></section>
        </div>
        <div class="secondary-stack">
          <section class="panel clickable" data-action="open-calendar" data-project="${p.id}" tabindex="0" role="button" aria-label="Open the large calendar">${panelHead("Calendar", "Tasks and meetings. Click for the large view.")}<div class="panel-body" id="mini-cal"></div></section>
          <section class="panel">${panelHead("Inbox", "Paperwork to sign or complete", `#/project/${p.id}/inbox`, "Open")}<div class="panel-body" id="mini-inbox"><div class="spinner"></div></div>
            <div class="panel-footer"><span>${me.mode === "google" ? "From your Gmail" : "Demo inbox"}</span><a href="${inboxLink()}" target="_blank" rel="noopener">Go to my email ${I.ext}</a></div></section>
          <section class="panel">${panelHead("Document center", "Every document on this project")}<div class="panel-body">${docSummary(p)}<a class="button secondary" href="#/project/${p.id}/documents">${I.doc}Open the document center</a></div></section>
        </div>
      </div>`;
    miniCalendar(p, document.getElementById("mini-cal"));
    inboxList(p, document.getElementById("mini-inbox"), { limit: 5, compact: true });
  }
  function panelHead(title, sub, href, linkText) {
    return `<div class="panel-header"><div><h2>${title}</h2>${sub ? `<p>${sub}</p>` : ""}</div>${href ? `<a class="button ghost small" href="${href}">${linkText || "View all"}</a>` : ""}</div>`;
  }

  // ---------- timeline ----------
  function timelineHeader(p) {
    const done = p.tasks.filter((t) => t.done).length;
    return `<div class="panel-header"><div><h2>Timeline</h2><p>${done} of ${p.tasks.length} steps done. ${p.slip > 0 ? `<strong class="text-red">Behind schedule by ${p.slip} work days.</strong>` : "On schedule."}</p></div><a class="button ghost small" href="#/project/${p.id}/timeline">Details</a></div>`;
  }
  function timeline(p) {
    const n = p.tasks.length;
    const cur = Math.max(0, ...p.tasks.map((t, i) => (t.done || t.fc.s <= 0 ? i : 0))); // furthest step done or under way
    const frac = cur / (n - 1);
    return `<div class="tl-scroll"><div class="tl ${p.slip > 0 ? "late" : "ontime"}" style="--n:${n}">
      <div class="tl-track"></div><div class="tl-fill" style="--frac:${frac}"></div>
      <ol class="tl-steps">${p.tasks.map((t, i) => {
        const st = M.taskState(t);
        const cls = t.done ? "done" : t.fc.s <= 0 ? "current" : "future";
        const date = t.done ? fmtI(t.fc.f) : t.fc.s <= 0 ? `due ${fmtI(t.fc.f)}` : fmtI(t.fc.s);
        return `<li class="tl-step ${cls} ${st === "problem" || st === "late" ? "warn" : ""}" title="${esc(t.name)}: ${esc(TASK_STATE[st][0])}"><span class="tl-dot"></span><span class="tl-label">${esc(t.short)}</span><span class="tl-date">${t.done ? "" : t.fc.s <= 0 ? "" : "~"}${date}</span></li>`;
      }).join("")}</ol></div></div>
      <div class="legend ${p.slip > 0 ? "late" : "ontime"}"><span><i style="background:var(--tl)"></i>Completed (date done)</span><span><i class="ring"></i>Current step</span><span><i style="background:#d5dbd0"></i>Ahead (~ forecast start)</span></div>`;
  }
  function timelinePage(p, el) {
    el.innerHTML = `<section class="panel">${timelineHeader(p).replace(/<a class="button[^>]*>Details<\/a>/, "")}<div class="panel-body">${timeline(p)}</div></section>
      <section class="panel section-spacer">${panelHead("Every step", "Planned versus forecast dates, owner, and slack (days a step can slip before go-live moves)")}
      <div class="table-wrap"><table class="data-table"><thead><tr><th>Step</th><th>Owner</th><th>Status</th><th>Planned</th><th>Forecast / actual</th><th>Slack</th></tr></thead><tbody>
      ${p.tasks.map((t) => { const st = M.taskState(t); return `<tr><td><strong>${esc(t.name)}</strong><div class="subline">${esc(t.phase)}${t.preds.length ? " · after " + t.preds.map((id) => S.byTask[id].short).join(", ") : ""}</div>${t.issue ? `<div class="subline text-red">${esc(t.issue.text)}</div>` : ""}</td>
        <td>${esc(t.role === "eqore" ? "EQORE (you)" : company(t.owner_id).name)}</td><td><span class="badge ${TASK_STATE[st][1]}">${TASK_STATE[st][0]}</span></td>
        <td class="nowrap">${fmtI(t.planned.s)} – ${fmtI(t.planned.f)}</td><td class="nowrap ${t.fc.f > t.planned.f ? "text-red" : ""}">${fmtI(t.fc.s)} – ${fmtI(t.fc.f)}</td>
        <td>${t.done ? "–" : t.critical ? '<span class="badge orange">Critical</span>' : t.slack + " d"}</td></tr>`; }).join("")}
      </tbody></table></div></section>`;
  }

  // ---------- calendar ----------
  async function eventsFor(p, from, to) {
    const items = M.calendarItems(S, p).concat(M.calendarItems(S).filter((x) => !x.project_id));
    const g = await loadGoogleCalendar(from, to);
    return items.concat(g).filter((x) => x.date >= from && x.date <= to).sort((a, b) => (a.date + (a.time || "")).localeCompare(b.date + (b.time || "")));
  }
  const monthStart = (d) => d.slice(0, 8) + "01";
  const monthEnd = (d) => { const x = parse(monthStart(d)); x.setMonth(x.getMonth() + 1); x.setDate(0); return x.toLocaleDateString("en-CA"); };
  const shiftMonth = (d, n) => { const x = parse(monthStart(d)); x.setMonth(x.getMonth() + n); return x.toLocaleDateString("en-CA"); };
  function monthGrid(month, events, big, highlight) {
    const first = parse(month), start = new Date(first); start.setDate(1 - first.getDay());
    const cells = [];
    for (let i = 0; i < 42; i++) {
      const d = new Date(start); d.setDate(start.getDate() + i);
      const iso = d.toLocaleDateString("en-CA"), ev = events.filter((e) => e.date === iso);
      if (i >= 35 && d.getMonth() !== first.getMonth()) break;
      cells.push(`<div class="cal-cell ${d.getMonth() !== first.getMonth() ? "other" : ""} ${iso === today ? "today" : ""} ${iso === highlight ? "highlight" : ""} ${d.getDay() % 6 === 0 ? "weekend" : ""}">
        <span class="cal-num">${d.getDate()}</span>
        ${big ? ev.slice(0, 4).map((e) => `<span class="cal-ev ${e.kind} ${e.state || ""}" title="${esc(e.title)}">${e.time ? e.time + " " : ""}${esc(e.title)}</span>`).join("") + (ev.length > 4 ? `<span class="cal-more">+${ev.length - 4} more</span>` : "")
          : `<span class="cal-dots">${ev.slice(0, 3).map((e) => `<i class="${e.kind}"></i>`).join("")}</span>`}
      </div>`);
    }
    return `<div class="cal ${big ? "big" : "mini"}"><div class="cal-head">${["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((d) => `<span>${big ? d : d[0]}</span>`).join("")}</div><div class="cal-grid">${cells.join("")}</div></div>`;
  }
  function agenda(events, limit, anyDate) {
    const up = events.filter((e) => anyDate || e.date >= today).slice(0, limit || 99);
    if (!up.length) return `<div class="empty-state compact"><p>Nothing scheduled.</p></div>`;
    return `<ul class="agenda">${up.map((e) => `<li><span class="agenda-date">${fmt(e.date, { weekday: "short", month: "short", day: "numeric" })}${e.time ? `<small>${e.time}</small>` : ""}</span><span class="agenda-title ${e.state === "late" ? "text-red" : ""}"><i class="kind ${e.kind}"></i>${e.link ? `<a href="${esc(e.link)}" target="_blank" rel="noopener">${esc(e.title)}</a>` : esc(e.title)}${e.owner ? `<small>${esc(company(e.owner).name)}</small>` : ""}${e.kind === "google" ? "<small>Google Calendar</small>" : ""}</span></li>`).join("")}</ul>`;
  }
  const calLegend = `<div class="legend"><span><i class="kind task"></i>Task start</span><span><i class="kind milestone"></i>Milestone</span><span><i class="kind doc"></i>Paperwork due</span><span><i class="kind delivery"></i>Delivery</span><span><i class="kind meeting"></i>Meeting</span>${"<span><i class=\"kind google\"></i>Your Google Calendar</span>"}</div>`;
  async function miniCalendar(p, el) {
    const from = monthStart(today), to = M.addDays(today, 30) > monthEnd(today) ? M.addDays(today, 30) : monthEnd(today);
    const events = await eventsFor(p, from, to);
    el.innerHTML = `<div class="cal-title">${fmt(today, { month: "long", year: "numeric" })}</div>${monthGrid(monthStart(today), events, false)}<div class="field-label section-spacer-sm">Coming up</div>${agenda(events, 4)}${cache.gcalError ? `<p class="tiny text-red">Google Calendar: ${esc(cache.gcalError)}</p>` : ""}`;
  }
  async function bigCalendar(p, el, month, highlight) {
    el.innerHTML = `<div class="spinner"></div>`;
    const events = await eventsFor(p, M.addDays(month, -7), M.addDays(monthEnd(month), 7));
    el.innerHTML = `<div class="cal-toolbar"><button class="button secondary small" data-cal="-1" aria-label="Previous month">${I.left}</button><h3>${fmt(month, { month: "long", year: "numeric" })}</h3><button class="button secondary small" data-cal="1" aria-label="Next month">${I.right}</button>
      <button class="button ghost small" data-cal="0">Today</button><a class="button ghost small" href="${calendarLink()}" target="_blank" rel="noopener">Open my calendar ${I.ext}</a></div>
      <div class="cal-layout">${monthGrid(month, events, true, highlight)}<div><div class="field-label">${highlight ? fmt(highlight, { weekday: "long", month: "short", day: "numeric" }) : "Upcoming"}</div>${agenda(highlight ? events.filter((e) => e.date === highlight) : events.filter((e) => e.date >= month), 14, !!highlight)}${highlight ? `<div class="field-label section-spacer-sm">After that</div>${agenda(events.filter((e) => e.date > highlight), 8)}` : ""}</div></div>${calLegend}
      ${me.mode !== "google" ? `<p class="tiny muted">Demo calendar. Sign in with Google to see your own meetings here too.</p>` : cache.gcalError ? `<p class="tiny text-red">Google Calendar: ${esc(cache.gcalError)}</p>` : ""}`;
    el.querySelectorAll("[data-cal]").forEach((b) => b.addEventListener("click", () => bigCalendar(p, el, b.dataset.cal === "0" ? monthStart(today) : shiftMonth(month, +b.dataset.cal), highlight)));
  }
  function calendarPage(p, el) {
    el.innerHTML = `<section class="panel"><div class="panel-body panel-body-top" id="big-cal"></div></section>`;
    bigCalendar(p, document.getElementById("big-cal"), monthStart(today));
  }

  // ---------- inbox ----------
  async function inboxList(p, el, opts) {
    const box = await loadInbox();
    const all = box.items, forProject = all.filter((x) => x.project_id === p.id);
    const scope = opts.scope || (forProject.length || box.mode === "demo" ? "project" : "all");
    const dept = opts.dept || "";
    let items = (scope === "project" ? forProject : all).filter((x) => !dept || x.department === dept);
    const depts = [...new Set((scope === "project" ? forProject : all).map((x) => x.department))].sort();
    const err = box.error || cache.inboxError;
    const rows = items.slice(0, opts.limit || 999).map((x) => `
      <a class="mail-row ${x.unread ? "unread" : ""}" href="${esc(x.link || inboxLink())}" target="_blank" rel="noopener">
        <span class="mail-from">${esc(x.from_name)}</span>
        <span class="mail-subject">${esc(x.subject)}${opts.compact ? "" : `<small>${esc(x.snippet)}</small>`}</span>
        <span class="mail-meta"><span class="badge outline">${esc(x.department)}</span><small>${fmt(x.date)}</small></span>
      </a>`).join("");
    el.innerHTML = `
      ${opts.compact ? "" : `<div class="filter-row"><div class="segmented small">${["project", "all"].map((k) => `<button type="button" class="${scope === k ? "on" : ""}" data-scope="${k}">${k === "project" ? "This project" : "All paperwork"}</button>`).join("")}</div>
        <select class="input select-inline" data-dept aria-label="Department"><option value="">All departments</option>${depts.map((d) => `<option ${d === dept ? "selected" : ""}>${esc(d)}</option>`).join("")}</select></div>`}
      ${err ? `<div class="notice error"><p><strong>Couldn't read Gmail.</strong>${esc(err)}</p></div>` : ""}
      ${rows ? `<div class="mail-list">${rows}</div>` : `<div class="empty-state compact"><p>${scope === "project" && box.mode === "google" ? "No paperwork emails mention this project. Switch to All paperwork." : "No paperwork waiting."}</p></div>`}
      ${opts.compact && scope === "all" && box.mode === "google" ? `<p class="tiny muted">No emails mention this project, so this shows all paperwork in your inbox.</p>` : ""}`;
    el.querySelectorAll("[data-scope]").forEach((b) => b.addEventListener("click", () => inboxList(p, el, { ...opts, scope: b.dataset.scope, dept: "" })));
    const sel = el.querySelector("[data-dept]");
    if (sel) sel.addEventListener("change", () => inboxList(p, el, { ...opts, scope, dept: sel.value }));
  }
  function inboxPage(p, el) {
    el.innerHTML = `<section class="panel"><div class="panel-header"><div><h2>Paperwork in your inbox</h2><p>${me.mode === "google" ? "Scanned from your Gmail: emails about documents to sign or complete, sorted by department. Click one to open it in Gmail." : "Demo inbox: paperwork waiting on you across this project. Sign in with Google to scan your real inbox."}</p></div>
      <a class="button" href="${inboxLink()}" target="_blank" rel="noopener">${I.mail}Go to my email</a></div><div class="panel-body" id="inbox-full"><div class="spinner"></div></div></section>`;
    inboxList(p, document.getElementById("inbox-full"), {});
  }

  // ---------- to do ----------
  function todoList(p, limit) {
    const items = p.todos.slice(0, limit || 999);
    if (!items.length) return `<div class="empty-state compact"><p>Nothing for you on this project right now.</p></div>`;
    return `<div class="todo-list">${items.map((x, i) => `
      <div class="todo u${x.urgency}">
        <span class="badge ${URG_BADGE[x.urgency]}">${x.kind === "issue" ? "Delay" : M.URGENCY[x.urgency]}</span>
        <div class="todo-body"><strong>${esc(x.title)}</strong><small>${esc(x.detail)}${x.kind !== "issue" ? ` · due ${fmtI(x.due)}` : ` · reported ${fmtI(x.due)}`}</small></div>
        ${x.party || x.doc ? `<button class="button secondary small" data-action="email-todo" data-project="${p.id}" data-i="${p.todos.indexOf(x)}">${I.mail}${x.kind === "doc" ? "Reply" : "Email"}</button>` : ""}
      </div>`).join("")}</div>${limit && p.todos.length > limit ? `<a class="tiny" href="#/project/${p.id}/todo">${p.todos.length - limit} more</a>` : ""}`;
  }
  function todoPage(p, el) {
    el.innerHTML = `<section class="panel">${panelHead("To do", "From the timeline and paperwork: overdue first, then by due date. Delays reported by subcontractors are at the top.")}<div class="panel-body">${todoList(p)}</div></section>`;
  }

  // ---------- documents ----------
  function docSummary(p) {
    const c = (s) => p.docs.filter((d) => d.status === s).length;
    const pmWaiting = p.docs.filter((d) => d.status === "waiting" && d.next.label === "PM").length;
    return `<div class="doc-counts"><div><strong>${c("complete")}</strong><small>complete</small></div><div><strong>${c("waiting")}</strong><small>in progress</small></div><div><strong class="${pmWaiting ? "text-orange" : ""}">${pmWaiting}</strong><small>waiting on you</small></div><div><strong>${c("not_started")}</strong><small>not started</small></div></div>`;
  }
  function docStatus(d) {
    if (d.status === "complete") return `<span class="badge green">Complete</span>`;
    if (d.status === "not_started") return `<span class="badge outline">Not started</span>`;
    const who = d.next.label === "PM" ? "you" : d.next.label === "Customer" ? "customer" : company(d.next.id).name;
    return `<span class="badge ${d.next.label === "PM" ? "orange" : "gold"}">Waiting on ${esc(who)}</span>`;
  }
  // Where a document (or a step's paperwork) opens. Today: this app's document page, scrolled to that document.
  // When Yichang's document center lands, point DOC_CENTER at it; every link below (subcontractor documents,
  // task chips, to-dos) goes through these two functions. Document ids are stable: "<JOB>:<step>:doc<n>".
  const DOC_CENTER = null; // e.g. (q) => `/documents/?${q}`
  const docQuery = (p, extra) => new URLSearchParams({ project: p.id, ...extra }).toString();
  const docLink = (p, d) => (DOC_CENTER ? DOC_CENTER(docQuery(p, { doc: d.id })) : `#/project/${p.id}/documents?doc=${encodeURIComponent(d.id)}`);
  const stepDocsLink = (p, t) => (DOC_CENTER ? DOC_CENTER(docQuery(p, { step: t.key })) : `#/project/${p.id}/documents?step=${encodeURIComponent(t.key)}`);

  function documentsPage(p, el, query) {
    const focus = query.get("doc"), step = query.get("step"), productId = query.get("product");
    const stepTask = step && p.tasks.find((t) => t.key === step);
    const prod = productId && p.products.find((x) => x.id === productId);
    const rows = p.docs.filter((d) => (!stepTask || d.task === stepTask) && (!prod || d.product_id === prod.id));
    el.innerHTML = `<div class="notice job"><p><strong>Document center</strong>Yichang is building the full document center (files, versions, e-signature). It will plug in here. For now this lists every document on the project and where it stands.</p></div>
      <section class="panel"><div class="panel-header"><div><h2>${stepTask ? `Documents for ${esc(stepTask.name)}` : prod ? `Documents for ${esc(prod.name)}` : "Documents"}</h2>${stepTask || prod ? `<p><a href="#/project/${p.id}/documents">Show all documents</a></p>` : ""}</div>
        <button class="button small" data-action="add-doc" data-project="${p.id}" ${stepTask ? `data-step="${stepTask.key}"` : ""} ${prod ? `data-product="${esc(prod.id)}"` : ""}>${I.plus}Add document</button></div><div class="panel-body">${docSummary(p)}</div>
      <div class="table-wrap"><table class="data-table"><thead><tr><th>Document</th><th>Step</th><th>Department</th><th>Status</th><th>Due</th><th></th></tr></thead><tbody>
      ${rows.sort((a, b) => ({ waiting: 0, not_started: 1, complete: 2 })[a.status] - ({ waiting: 0, not_started: 1, complete: 2 })[b.status]).map((d) => `<tr id="doc-${esc(d.id.replace(/:/g, "-"))}" class="${d.id === focus ? "focus" : ""}"><td><strong>${esc(d.name)}</strong><div class="subline">${d.flow.map((x) => (x.label === "PM" ? "You" : company(x.id).name)).join(" → ")}</div>${d.notes ? `<div class="subline">${esc(d.notes)}</div>` : ""}</td><td>${esc(d.task.name)}${d.product_id && p.products.find((x) => x.id === d.product_id) ? `<div class="subline"><a href="#/project/${p.id}/procurement">${esc(p.products.find((x) => x.id === d.product_id).name)}</a></div>` : ""}</td><td>${esc(d.department)}</td><td>${docStatus(d)}</td><td class="nowrap ${d.due != null && d.due < 0 && d.status !== "complete" ? "text-red" : ""}">${d.due != null ? fmtI(d.due) : d.history.length ? "done " + fmtI(d.history[d.history.length - 1].at) : ""}</td><td><button class="button ghost small" data-action="edit-doc" data-project="${p.id}" data-doc="${esc(d.id)}">${I.edit}Edit</button></td></tr>`).join("")}
      </tbody></table></div>${!rows.length ? `<div class="empty-state compact panel-body"><p>No documents here yet.</p></div>` : ""}</section>`;
    const row = focus && el.querySelector(`#doc-${CSS.escape(focus.replace(/:/g, "-"))}`);
    if (row) setTimeout(() => row.scrollIntoView({ block: "center", behavior: "smooth" }), 60);
  }

  // ---------- subcontractors ----------
  function subsSummary(p) {
    const subs = M.subcontractors(S, p);
    const delayed = subs.filter((x) => x.delayed.length);
    const open = subs.filter((x) => x.open.length || x.tasks.some((t) => t.state === "active" || t.state === "at_risk"));
    const ups = M.updates(S, p, 10).slice(0, 4);
    return `
      ${delayed.map((x) => `<div class="notice error compact">${I.warn}<p><strong>${esc(x.company.name)}: delay</strong>${x.delayed.map((t) => esc(t.task.issue.text)).join(" ")}</p></div>`).join("")}
      <div class="field-label">Their to-dos</div>
      ${open.length ? `<ul class="plain-list">${open.slice(0, 5).map((x) => `<li><strong>${esc(x.company.name)}</strong><small>${[...x.tasks.filter((t) => t.state === "active" || t.state === "at_risk" || t.state === "problem").map((t) => t.task.name + " (" + TASK_STATE[t.state][0].toLowerCase() + ", due " + fmtI(t.task.fc.f) + ")"), ...x.open.map((d) => (d.step === d.flow.length - 1 ? "Sign " : "Send ") + d.name)].map(esc).join(" · ")}</small></li>`).join("")}</ul>` : `<p class="tiny muted">No open items.</p>`}
      <div class="field-label section-spacer-sm">Recent updates</div>${updatesList(ups)}`;
  }
  function updatesList(ups) {
    if (!ups.length) return `<p class="tiny muted">No updates in the last two weeks.</p>`;
    return `<div class="timeline">${ups.map((u) => `<div class="timeline-item ${u.kind}"><h3>${esc(company(u.party).name)}</h3><p>${esc(u.text)}${u.delay ? ` <span class="badge red">+${u.delay} work days</span>` : ""}</p><div class="timeline-meta">${fmtI(u.at)}</div></div>`).join("")}</div>`;
  }
  function subsPage(p, el) {
    const subs = M.subcontractors(S, p);
    el.innerHTML = `
      <div class="workspace-grid">
        <section class="panel">
          <div class="panel-header"><div><h2>Tasks by contractor</h2><p>Who did what, colour-coded against the timeline. Open a contractor's documents, email them, or edit their details and steps.</p></div><button class="button small" data-action="add-contractor" data-project="${p.id}">${I.plus}Add contractor</button></div>
          <div class="legend legend-top">${Object.entries(TASK_STATE).map(([k, [l]]) => `<span><i class="chip-key ${k}"></i>${l}</span>`).join("")}</div>
          <div class="sub-list">${subs.map((x) => {
            const c = x.company, signed = x.docs.filter((d) => d.status === "complete").length, waiting = x.docs.length - signed;
            return `<div class="sub-row ${x.delayed.length ? "delayed" : ""}">
              <div class="sub-who"><strong>${esc(c.name)}</strong><small>${esc(D.TRADES[c.trade] || c.trade)} · ${esc(c.contact)}</small>${c.phone ? `<small>${esc(c.phone)}</small>` : ""}${x.delayed.length ? `<span class="badge red">${I.warn}Delay</span>` : ""}</div>
              <div class="sub-tasks">${x.tasks.length ? "" : `<span class="tiny muted">Added by you. No steps assigned yet.</span>`}${x.tasks.map((t) => `<a class="task-chip ${t.state}" href="${stepDocsLink(p, t.task)}" title="${esc(TASK_STATE[t.state][0])}${t.task.issue ? ": " + esc(t.task.issue.text) : ""}. Open this step's documents."><strong>${esc(t.task.name)}</strong><small>${TASK_STATE[t.state][0]} · ${t.task.done ? "done " + fmtI(t.task.fc.f) : fmtI(t.task.fc.s) + " – " + fmtI(t.task.fc.f)}</small></a>`).join("")}</div>
              <div class="sub-actions"><button class="button secondary small" data-action="docs" data-project="${p.id}" data-company="${c.id}">${I.doc}Documents <span class="muted">${signed} done · ${waiting} to do</span></button>
                <button class="button small" data-action="email" data-project="${p.id}" data-company="${c.id}">${I.mail}Email</button>
                <button class="button ghost small" data-action="edit-contractor" data-project="${p.id}" data-company="${c.id}">${I.edit}Edit</button></div>
            </div>`; }).join("")}</div>
        </section>
        <div class="secondary-stack">
          <section class="panel">${panelHead("Delays and updates", "Latest from subcontractors on this project")}<div class="panel-body">${updatesList(M.updates(S, p, 15).slice(0, 8))}</div></section>
          <section class="panel db-card">${panelHead("Contractor database", `${S.companies.filter((c) => !["utility", "inspection"].includes(c.trade)).length} companies. Search by job type, task, name or availability.`)}
            <div class="panel-body"><button class="button" data-action="database" data-project="${p.id}">${I.search}Search contractors</button></div></section>
        </div>
      </div>`;
  }

  // ---------- modals ----------
  function openModal(title, body, wide) {
    $modal.innerHTML = `<div class="modal-backdrop" data-action="close-modal"></div><div class="modal ${wide ? "wide" : ""}" role="dialog" aria-modal="true" aria-label="${esc(title)}"><div class="modal-head"><h2>${esc(title)}</h2><button class="button ghost small" data-action="close-modal" aria-label="Close">✕</button></div><div class="modal-body">${body}</div></div>`;
    document.body.classList.add("modal-open");
    const first = $modal.querySelector("input, select, textarea, button:not([data-action=close-modal])");
    if (first) first.focus();
  }
  function closeModal() { $modal.innerHTML = ""; document.body.classList.remove("modal-open"); }
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && $modal.innerHTML) closeModal(); });

  function docCard(p, d) {
    const step = (i) => {
      const party = d.flow[i], who = party.label === "PM" ? "You (PM)" : party.label === "Customer" ? "Customer" : company(party.id).name;
      const h = d.history[i];
      const verb = i === d.flow.length - 1 || party.label === "PM" ? "sign" : "fill out";
      if (h) return `<li class="done"><strong>${esc(who)}</strong> ${esc(h.action.toLowerCase())} · ${fmtI(h.at)}</li>`;
      if (d.status === "waiting" && i === d.step) return `<li class="now"><strong>${esc(who)}</strong> needs to ${verb} · due ${fmtI(d.due)}</li>`;
      return `<li><strong>${esc(who)}</strong> to ${verb}</li>`;
    };
    return `<div class="doc-card"><div class="doc-card-head"><strong>${esc(d.name)}</strong>${docStatus(d)}</div><small class="muted">${esc(d.task.name)} · ${esc(d.department)}${d.notes ? " · " + esc(d.notes) : ""}</small>
      ${d.flow.length ? `<ol class="doc-steps">${d.flow.map((_, i) => step(i)).join("")}</ol>` : ""}
      <div class="doc-card-actions"><a class="doc-open" href="${docLink(p, d)}">Open in document center ${I.ext}</a><button class="button ghost small" data-action="edit-doc" data-project="${p.id}" data-doc="${esc(d.id)}">${I.edit}Edit</button></div></div>`;
  }
  function docsModal(p, companyId) {
    const c = company(companyId), x = M.subcontractors(S, p).find((s) => s.company.id === companyId);
    openModal(`${c.name}: documents and tasks`, `
      <p class="muted tiny">${esc(D.TRADES[c.trade] || c.trade)} · ${esc(c.contact)} · ${esc(c.email)}${c.phone ? " · " + esc(c.phone) : ""}</p>
      <div class="field-label section-spacer-sm">Tasks on ${esc(p.name)}</div>
      <ul class="plain-list">${x.tasks.map((t) => `<li><span class="badge ${TASK_STATE[t.state][1]}">${TASK_STATE[t.state][0]}</span> <strong>${esc(t.task.name)}</strong><small>${t.task.done ? "Completed " + fmtI(t.task.fc.f) : fmtI(t.task.fc.s) + " – " + fmtI(t.task.fc.f)}${t.task.issue ? " · " + esc(t.task.issue.text) : ""}</small></li>`).join("")}</ul>
      <div class="field-label section-spacer-sm">Documents (history and who's next)</div>
      ${x.docs.length ? x.docs.map((d) => docCard(p, d)).join("") : `<p class="tiny muted">No documents with this company on this project.</p>`}
      <div class="form-actions section-spacer-sm"><button class="button" data-action="email" data-project="${p.id}" data-company="${c.id}">${I.mail}Email ${esc(!c.contact || /desk|team|manager/i.test(c.contact) ? c.name : c.contact.split(" ")[0])}</button>
        <button class="button secondary" data-action="add-doc" data-project="${p.id}" data-party="${c.id}">${I.plus}Add document</button></div>`, true);
  }

  function composeModal(draft) {
    const demo = me.mode !== "google";
    openModal("New email", `
      <form id="compose" class="compose" novalidate>
        <label class="field"><span>To</span><input name="to" value="${esc(draft.to)}" autocomplete="off"></label>
        <label class="field"><span>Cc</span><input name="cc" value="${esc(draft.cc || "")}" autocomplete="off"></label>
        <label class="field"><span>Subject</span><input name="subject" value="${esc(draft.subject)}"></label>
        <label class="field"><span>Message</span><textarea name="body" rows="10">${esc(draft.body)}</textarea></label>
        ${/\.demo\.example\b/.test(draft.to) ? `<p class="tiny muted">Demo contacts use .example addresses, which never deliver. Put a real address in To if you want to test sending.</p>` : ""}
        <div class="form-actions"><button class="button" type="submit">${I.mail}${demo ? "Open in Gmail to send" : "Send from " + esc(me.email)}</button><button class="button ghost" type="button" data-action="close-modal">Cancel</button></div>
        <p class="tiny muted">${demo ? "Demo account: this opens a Gmail draft in a new tab. Sign in with Google to send straight from here." : "Sent through your Gmail. It appears in your Sent folder."}</p>
      </form>`, true);
    document.getElementById("compose").addEventListener("submit", async (e) => {
      e.preventDefault();
      const f = Object.fromEntries(new FormData(e.target));
      if (!f.to.trim() || !f.subject.trim()) return toast("Add a recipient and a subject.", true);
      if (demo) {
        const url = "https://mail.google.com/mail/?view=cm&fs=1&" + new URLSearchParams({ to: f.to, cc: f.cc, su: f.subject, body: f.body }).toString();
        window.open(url, "_blank", "noopener"); closeModal(); return;
      }
      const btn = e.target.querySelector("button[type=submit]"); btn.disabled = true;
      try { const r = await api("/api/send", { method: "POST", body: JSON.stringify(f) }); closeModal(); toast(`Sent to ${r.to.join(", ")}.`); }
      catch (err) { btn.disabled = false; toast(err.message, true); }
    });
  }
  function draftFor(p, companyId, about) {
    const c = company(companyId), first = (c.contact || "").split(" ")[0];
    const greet = c.contact && !/desk|team|manager/i.test(c.contact) ? `Hi ${first},` : "Hello,";
    return { to: c.email, subject: about ? about.subject : `${p.name} (${p.id})`, body: `${greet}\n\n${about ? about.body : ""}\n\nThanks,\n${me.name}\nEQORE` };
  }
  function todoDraft(p, x) {
    if (x.kind === "product") return productDraft(p, x.product);
    if (x.kind === "issue") return draftFor(p, x.party, { subject: `${x.task.name}: recovery plan - ${p.name} (${p.id})`, body: `Thanks for flagging the delay on ${x.task.name.toLowerCase()} at ${p.name}: "${x.detail}"\n\nCan you send me the recovery plan and the earliest date you can commit to? It currently moves go-live to ${fmt(p.go_live_date)}.` });
    if (x.kind === "chase") return draftFor(p, x.party, { subject: `${x.doc.name} - ${p.name} (${p.id})`, body: `Checking in on the ${x.doc.name.toLowerCase()} for ${p.name}. We need it by ${fmtI(x.doc.due)} to keep ${x.doc.task.name.toLowerCase()} on schedule. Can you send it over?` });
    const from = x.doc.step > 0 ? x.doc.flow[x.doc.step - 1].id : (x.doc.flow.find((f) => f.label !== "PM") || {}).id;
    return draftFor(p, from, { subject: `Re: ${x.doc.name} - ${p.name} (${p.id})`, body: `${x.doc.step === 0 ? `I'm completing the ${x.doc.name.toLowerCase()} now and will send it by ${fmtI(x.doc.due)}.` : `Signed ${x.doc.name.toLowerCase()} attached.`}` });
  }

  function databaseModal(p) {
    const steps = D.TEMPLATE.filter((t) => !["eqore", "customer"].includes(t.role));
    const trades = Object.entries(D.TRADES).filter(([k]) => !["eqore", "customer"].includes(k));
    openModal("Contractor database", `
      <form id="db-filter" class="db-filters">
        <label class="field"><span>Name, contact or city</span><input name="name" placeholder="Search"></label>
        <label class="field"><span>Job type</span><select name="trade"><option value="">Any</option>${trades.map(([k, l]) => `<option value="${k}">${esc(l)}</option>`).join("")}</select></label>
        <label class="field"><span>Task</span><select name="step"><option value="">Any</option>${steps.map((t) => `<option value="${t.key}">${esc(t.name)}</option>`).join("")}</select></label>
        <label class="field"><span>State</span><select name="state"><option value="">Any</option><option ${p.state === "MA" ? "selected" : ""}>MA</option><option ${p.state === "CA" ? "selected" : ""}>CA</option></select></label>
        <label class="field"><span>Available from</span><input type="date" name="from" value="${S.cal.base}"></label>
        <label class="field"><span>Available until</span><input type="date" name="to"></label>
        <label class="field"><span>For (work days)</span><input type="number" name="days" min="1" max="60" value="1"></label>
        <label class="field check"><input type="checkbox" name="only_available"><span>Only show available</span></label>
      </form>
      <div id="db-results"></div>`, true);
    const form = document.getElementById("db-filter"), out = document.getElementById("db-results");
    const onProject = new Set(M.subcontractors(S, p).map((x) => x.company.id));
    const run = () => {
      const f = Object.fromEntries(new FormData(form));
      const rows = M.searchCompanies(S, { name: f.name, trade: f.trade, step: f.step, state: f.state, from: f.from ? S.cal.index(f.from) : 0, to: f.to ? S.cal.index(f.to) : null, days: +f.days || 1, only_available: !!f.only_available }, p);
      out.innerHTML = `<p class="tiny muted">${rows.length} compan${rows.length === 1 ? "y" : "ies"}. Availability counts their EQORE jobs on every project plus work booked with other clients.</p>
        <div class="table-wrap"><table class="data-table"><thead><tr><th>Company</th><th>Job type</th><th>Availability</th><th>Distance to ${esc(p.city)}</th><th>Rate</th><th></th></tr></thead><tbody>
        ${rows.map((r) => { const c = r.company; return `<tr><td><strong>${esc(c.name)}</strong><div class="subline">${esc(c.contact)} · ${esc(c.city)}, ${c.state}${c.rating ? ` · ★ ${c.rating}` : ""}</div><div class="subline">${c.certifications.map(esc).join(", ")}</div></td>
          <td>${esc(D.TRADES[c.trade])}</td>
          <td>${r.available ? `<span class="badge green">${r.free_date === f.from || !f.from ? "Available" : "Available from " + fmt(r.free_date)}</span>` : `<span class="badge outline">Not in that window</span>`}<div class="subline">${r.free_date ? "Earliest " + fmt(r.free_date) : "Booked for months"} · ${r.jobs} EQORE job${r.jobs === 1 ? "" : "s"} in next 2 weeks</div></td>
          <td>${r.distance != null ? r.distance + " mi" : ""}${r.in_range ? "" : `<div class="subline text-red">outside their ${c.radius_mi} mi range</div>`}</td>
          <td>${c.day_rate ? "$" + c.day_rate.toLocaleString() + "/day" : "–"}</td>
          <td class="nowrap"><button class="button secondary small" data-action="email" data-project="${p.id}" data-company="${c.id}">${I.mail}Email</button>
            ${onProject.has(c.id) ? `<span class="badge outline">On project</span>` : `<button class="button small" data-action="add-contractor" data-project="${p.id}" data-company="${c.id}">${I.plus}Add</button>`}</td></tr>`; }).join("")}
        </tbody></table></div>`;
    };
    form.addEventListener("input", run); form.addEventListener("change", run); form.addEventListener("submit", (e) => e.preventDefault());
    run();
  }

  // ---------- saved edits (products, documents, contractors) ----------
  async function loadWorkspace() {
    try { WS = await api("/api/workspace"); } catch (e) { WS = { version: 0, data: {} }; toast("Couldn't load your saved changes: " + e.message, true); }
    S = M.build(D, today, WS.data);
  }
  // Applies `mutate` to a copy of the saved edits, saves it, then rebuilds every timeline and re-renders.
  async function save(mutate, message) {
    const data = JSON.parse(JSON.stringify(WS.data || {}));
    data.projects = data.projects || {}; data.companies = data.companies || {}; data.company_edits = data.company_edits || {};
    data.seq = data.seq || 0;
    mutate(data);
    try {
      const r = await api("/api/workspace", { method: "PUT", body: JSON.stringify({ base_version: WS.version, data }) });
      WS = { version: r.version, data };
    } catch (e) {
      if (e.status === 409) await loadWorkspace();
      toast(e.message, true);
      if (e.status === 409) { closeModal(); render(); }
      return false;
    }
    S = M.build(D, today, WS.data);
    cache.inbox = null;
    closeModal(); render(); toast(message);
    return true;
  }
  const projEdits = (data, pid) => (data.projects[pid] = data.projects[pid] || {});
  const newId = (data, prefix) => `${prefix}${++data.seq}`;
  const field = (label, html, wide) => `<label class="field ${wide ? "span-2" : ""}"><span>${label}</span>${html}</label>`;
  const opt = (value, label, selected) => `<option value="${esc(value)}" ${selected ? "selected" : ""}>${esc(label)}</option>`;
  const dateOr = (i) => (i != null ? S.cal.date(i) : "");
  function wireForm(id, onSubmit, onDelete) {
    const form = document.getElementById(id);
    form.addEventListener("submit", (e) => { e.preventDefault(); onSubmit(Object.fromEntries(new FormData(form)), form); });
    const del = form.querySelector("[data-role=delete]");
    if (del && onDelete) del.addEventListener("click", () => { if (del.dataset.armed) onDelete(); else { del.dataset.armed = "1"; del.textContent = "Click again to confirm"; } });
    return form;
  }

  // ---------- procurement ----------
  const PROD_BADGE = { delivered: "green", on_track: "live", pending: "outline", order_now: "gold", delayed: "red", at_risk: "red", overdue: "red" };
  function prodLabel(pr, st) {
    switch (st.key) {
      case "delivered": return `${pr.status}${pr.delivered_date ? " " + fmt(pr.delivered_date) : ""}`;
      case "overdue": return `Overdue: was expected ${fmt(pr.expected_date)}`;
      case "delayed": return `Delayed ${st.days} work day${st.days === 1 ? "" : "s"} (promised ${fmt(pr.promised_date)})`;
      case "at_risk": return `Expected delay: arrives after ${st.need.name.toLowerCase()} is due to start (${fmt(st.need_date)})`;
      case "order_now": return `Order now: needed by ${fmt(st.need_date)}`;
      case "pending": return "Not ordered yet";
      default: return "On track";
    }
  }
  const dateLink = (p, d, red) => (d ? `<button class="link-date ${red ? "text-red" : ""}" data-action="calendar-at" data-project="${p.id}" data-date="${d}" title="Show on the calendar">${I.cal}${fmt(d)}</button>` : "–");
  function productRow(p, pr) {
    const st = p.product_states[pr.id], sup = company(pr.supplier_id);
    const docs = p.docs.filter((d) => d.product_id === pr.id), done = docs.filter((d) => d.status === "complete").length;
    const need = p.tasks.find((t) => t.key === pr.needed_for);
    return `<div class="sub-row prod-row ${st.red ? "delayed" : ""}">
      <div class="sub-who"><strong>${esc(pr.name)}</strong><small>${esc(pr.category)} · ${esc(pr.quantity)} ${esc(pr.unit)}</small><small>${esc(sup.name)}</small>${pr.po_number ? `<small>${esc(pr.po_number)}</small>` : ""}${st.red ? `<span class="badge red">${I.warn}${st.key === "at_risk" ? "Expected delay" : "Delay"}</span>` : ""}</div>
      <div class="prod-detail">
        <div class="prod-status"><span class="badge ${PROD_BADGE[st.key]}">${esc(pr.status)}</span><span class="${st.red ? "text-red" : "muted"}">${esc(prodLabel(pr, st))}</span></div>
        <dl class="prod-dates">
          <div><dt>Ordered</dt><dd>${pr.order_date ? fmt(pr.order_date) : "–"}</dd></div>
          <div><dt>Promised</dt><dd>${pr.promised_date ? fmt(pr.promised_date) : "–"}</dd></div>
          <div><dt>${M.productRank(pr) >= 5 ? "Delivered" : "Expected delivery"}</dt><dd>${M.productRank(pr) >= 5 ? (pr.delivered_date ? fmt(pr.delivered_date) : "–") : dateLink(p, pr.expected_date, st.red)}</dd></div>
          <div><dt>Needed for</dt><dd>${need ? esc(need.name) : "–"}${need && !need.done ? `<small>${dateLink(p, S.cal.date(Math.max(0, need.fc.s)))}</small>` : need ? "<small>done</small>" : ""}</dd></div>
        </dl>
        ${pr.tracking || pr.notes ? `<p class="tiny muted">${pr.tracking ? "Tracking " + esc(pr.tracking) : ""}${pr.tracking && pr.notes ? " · " : ""}${esc(pr.notes || "")}</p>` : ""}
      </div>
      <div class="sub-actions"><button class="button secondary small" data-action="product-docs" data-project="${p.id}" data-product-id="${esc(pr.id)}">${I.doc}Documents <span class="muted">${done} done · ${docs.length - done} to do</span></button>
        <button class="button small" data-action="email-product" data-project="${p.id}" data-product-id="${esc(pr.id)}">${I.mail}Email supplier</button>
        <button class="button ghost small" data-action="edit-product" data-project="${p.id}" data-product-id="${esc(pr.id)}">${I.edit}Edit</button></div>
    </div>`;
  }
  function deliveriesList(p, limit) {
    const up = p.products.filter((pr) => M.productRank(pr) < 5 && pr.expected_date).sort((a, b) => a.expected_date.localeCompare(b.expected_date)).slice(0, limit || 99);
    if (!up.length) return `<p class="tiny muted">No deliveries scheduled.</p>`;
    return `<ul class="agenda">${up.map((pr) => { const st = p.product_states[pr.id]; return `<li><span class="agenda-date">${dateLink(p, pr.expected_date, st.red)}</span><span class="agenda-title ${st.red ? "text-red" : ""}"><i class="kind delivery"></i>${esc(pr.name)}<small>${esc(company(pr.supplier_id).name)}${st.red ? " · " + esc(prodLabel(pr, st)) : ""}</small></span></li>`; }).join("")}</ul>`;
  }
  function procSummary(p) {
    const red = p.products.filter((pr) => p.product_states[pr.id].red);
    return `${red.map((pr) => `<div class="notice error compact">${I.warn}<p><strong>${esc(pr.name)}</strong>${esc(prodLabel(pr, p.product_states[pr.id]))}</p></div>`).join("")}
      <div class="field-label">Next deliveries</div>${deliveriesList(p, 3)}`;
  }
  function procurementPage(p, el) {
    const order = { overdue: 0, delayed: 1, at_risk: 2, order_now: 3, on_track: 4, pending: 5, delivered: 6 };
    const list = p.products.slice().sort((a, b) => order[p.product_states[a.id].key] - order[p.product_states[b.id].key] || (a.expected_date || "9").localeCompare(b.expected_date || "9"));
    const red = list.filter((pr) => p.product_states[pr.id].red);
    el.innerHTML = `
      <div class="workspace-grid">
        <section class="panel">
          <div class="panel-header"><div><h2>Products</h2><p>Everything being bought for this project, with its supplier, status and delivery dates. Click a delivery date to see it on the calendar. A late delivery holds back the step that needs it.</p></div>
            <button class="button small" data-action="add-product" data-project="${p.id}">${I.plus}Add product</button></div>
          <div class="legend legend-top"><span><i class="chip-key done"></i>Delivered</span><span><i class="chip-key active"></i>On track</span><span><i class="chip-key at_risk"></i>Order now</span><span><i class="chip-key upcoming"></i>Not ordered</span><span><i class="chip-key problem"></i>Delayed or expected late</span></div>
          <div class="sub-list">${list.length ? list.map((pr) => productRow(p, pr)).join("") : `<div class="empty-state"><p>No products yet. Add the first one.</p></div>`}</div>
        </section>
        <div class="secondary-stack">
          <section class="panel">${panelHead("Delays", red.length ? `${red.length} product${red.length === 1 ? "" : "s"} late or expected late` : "Nothing late")}<div class="panel-body">${red.length ? red.map((pr) => `<div class="notice error compact">${I.warn}<p><strong>${esc(pr.name)}</strong>${esc(prodLabel(pr, p.product_states[pr.id]))}. ${esc(company(pr.supplier_id).name)}.</p></div>`).join("") : `<p class="tiny muted">Every delivery is on time.</p>`}</div></section>
          <section class="panel">${panelHead("Upcoming deliveries", "From the delivery dates above, also on the calendar")}<div class="panel-body">${deliveriesList(p)}<button class="button secondary small section-spacer-sm" data-action="open-calendar" data-project="${p.id}">${I.cal}Open calendar</button></div></section>
        </div>
      </div>`;
  }
  function productDocsModal(p, pr) {
    const docs = p.docs.filter((d) => d.product_id === pr.id), sup = company(pr.supplier_id);
    openModal(`${pr.name}: documents`, `
      <p class="muted tiny">${esc(pr.category)} · ${esc(pr.quantity)} ${esc(pr.unit)} · ${esc(sup.name)}${pr.po_number ? " · " + esc(pr.po_number) : ""}</p>
      <div class="field-label section-spacer-sm">Documents (history and who's next)</div>
      ${docs.length ? docs.map((d) => docCard(p, d)).join("") : `<p class="tiny muted">No documents for this product yet.</p>`}
      <div class="form-actions section-spacer-sm"><a class="button secondary" href="${DOC_CENTER ? DOC_CENTER(docQuery(p, { product: pr.id })) : `#/project/${p.id}/documents?product=${encodeURIComponent(pr.id)}`}">${I.doc}All in document center</a>
        <button class="button secondary" data-action="add-doc" data-project="${p.id}" data-product="${esc(pr.id)}" data-party="${esc(pr.supplier_id)}">${I.plus}Add document</button>
        <button class="button" data-action="email-product" data-project="${p.id}" data-product-id="${esc(pr.id)}">${I.mail}Email supplier</button></div>`, true);
  }
  function productDraft(p, pr) {
    const st = p.product_states[pr.id], need = st.need;
    const ref = pr.po_number ? ` (${pr.po_number})` : "";
    const needBy = st.need_date ? ` We need it on site by ${fmt(st.need_date)} for ${need.name.toLowerCase()}.` : "";
    let body;
    if (st.red) body = `Your delivery of ${pr.name.toLowerCase()}${ref} for ${p.name} is now expected ${fmt(pr.expected_date)}${pr.promised_date && pr.promised_date < pr.expected_date ? `, later than the ${fmt(pr.promised_date)} you promised` : ""}.${needBy}\n\nCan you confirm the date, and let me know anything you can do to bring it forward?`;
    else if (M.productRank(pr) === 0) body = `We'd like a quote and lead time for ${pr.quantity} ${pr.unit} of ${pr.name.toLowerCase()} for ${p.name} (${p.city}, ${p.state}).${needBy}`;
    else if (M.productRank(pr) >= 5) body = `Thanks for delivering ${pr.name.toLowerCase()}${ref} to ${p.name}. Please send the signed delivery receipt and invoice.`;
    else body = `Can you confirm the delivery date for ${pr.name.toLowerCase()}${ref} for ${p.name}? We have it expected on ${fmt(pr.expected_date)}.${needBy}`;
    return draftFor(p, pr.supplier_id, { subject: `${pr.name}${ref} - ${p.name} (${p.id})`, body });
  }

  // Add or edit a product. Saving stores the project's whole product list, so generated products become editable too.
  function productForm(p, pr) {
    const suppliers = S.companies.filter((c) => !["inspection", "utility", "customer"].includes(c.trade)).sort((a, b) => (a.trade + a.name).localeCompare(b.trade + b.name));
    const v = pr || { name: "", category: "Other", supplier_id: "", quantity: 1, unit: "units", needed_for: "placement", status: "Not ordered", po_number: "", order_date: "", promised_date: "", expected_date: "", delivered_date: "", tracking: "", notes: "" };
    openModal(pr ? `Edit product: ${pr.name}` : "Add product", `
      <form id="product-form" class="form-grid" novalidate>
        ${field("Product", `<input name="name" required value="${esc(v.name)}" placeholder="e.g. Step-up transformer">`, true)}
        ${field("Category", `<select name="category">${D.PRODUCT_CATEGORIES.map((c) => opt(c, c, c === v.category)).join("")}</select>`)}
        ${field("Supplier", `<select name="supplier_id">${opt("", "Choose a supplier", !v.supplier_id)}${suppliers.map((c) => opt(c.id, `${c.name} (${D.TRADES[c.trade] || c.trade})`, c.id === v.supplier_id)).join("")}${opt("__new", "+ New supplier…")}</select>`)}
        <fieldset class="new-supplier span-2" hidden><legend>New supplier</legend><div class="form-grid">
          ${field("Company name", `<input name="new_name">`)}${field("Contact", `<input name="new_contact">`)}${field("Email", `<input name="new_email" type="email">`)}${field("Phone", `<input name="new_phone">`)}</div></fieldset>
        ${field("Quantity", `<input name="quantity" type="number" min="0" step="any" value="${esc(v.quantity)}">`)}
        ${field("Unit", `<input name="unit" value="${esc(v.unit)}">`)}
        ${field("Needed for", `<select name="needed_for">${D.TEMPLATE.map((t) => opt(t.key, t.name, t.key === v.needed_for)).join("")}</select>`)}
        ${field("Status", `<select name="status">${D.PRODUCT_STATUSES.map((x) => opt(x, x, x === v.status)).join("")}</select>`)}
        ${field("PO number", `<input name="po_number" value="${esc(v.po_number)}">`)}
        ${field("Order date", `<input name="order_date" type="date" value="${esc(v.order_date)}">`)}
        ${field("Promised delivery", `<input name="promised_date" type="date" value="${esc(v.promised_date)}">`)}
        ${field("Expected delivery", `<input name="expected_date" type="date" value="${esc(v.expected_date)}">`)}
        ${field("Delivered on", `<input name="delivered_date" type="date" value="${esc(v.delivered_date)}">`)}
        ${field("Tracking", `<input name="tracking" value="${esc(v.tracking)}">`)}
        ${field("Notes", `<textarea name="notes" rows="3">${esc(v.notes)}</textarea>`, true)}
        <p class="tiny muted span-2">If the expected delivery is later than the step it's needed for, that step and everything after it move back, and the project turns red.</p>
        <div class="form-actions span-2"><button class="button" type="submit">${pr ? "Save changes" : "Add product"}</button><button class="button ghost" type="button" data-action="close-modal">Cancel</button>
          ${pr ? `<button class="button danger push-right" type="button" data-role="delete">Delete product</button>` : ""}</div>
      </form>`, true);
    const form = wireForm("product-form", (f) => {
      if (!f.name.trim()) return toast("Give the product a name.", true);
      if (!f.supplier_id) return toast("Choose a supplier, or add a new one.", true);
      if (f.supplier_id === "__new" && !f.new_name.trim()) return toast("Give the new supplier a name.", true);
      if (f.quantity !== "" && !(+f.quantity >= 0)) return toast("Quantity must be a number.", true);
      save((data) => {
        let supplier = f.supplier_id;
        if (supplier === "__new") {
          supplier = newId(data, "X-");
          data.companies[supplier] = { id: supplier, name: f.new_name.trim(), trade: "supplier", contact: f.new_contact.trim(), email: f.new_email.trim(), phone: f.new_phone.trim(), state: p.state };
        }
        const pe = projEdits(data, p.id);
        const list = pe.products || JSON.parse(JSON.stringify(p.products));
        const rec = { name: f.name.trim(), category: f.category, supplier_id: supplier, quantity: f.quantity === "" ? "" : +f.quantity, unit: f.unit.trim(), needed_for: f.needed_for,
          status: f.status, po_number: f.po_number.trim(), order_date: f.order_date || (D.PRODUCT_STATUSES.indexOf(f.status) >= 2 ? today : ""), promised_date: f.promised_date, expected_date: f.expected_date,
          delivered_date: f.delivered_date || (["Delivered", "Installed"].includes(f.status) ? today : ""), tracking: f.tracking.trim(), notes: f.notes.trim() };
        if (pr) Object.assign(list.find((x) => x.id === pr.id), rec);
        else list.push({ id: `${p.id}:p:${newId(data, "c")}`, key: null, custom: true, ...rec });
        pe.products = list;
      }, pr ? "Product saved. Timeline updated." : "Product added.");
    }, () => save((data) => {
      const pe = projEdits(data, p.id);
      pe.products = (pe.products || JSON.parse(JSON.stringify(p.products))).filter((x) => x.id !== pr.id);
    }, "Product deleted."));
    const sel = form.querySelector("[name=supplier_id]"), box = form.querySelector(".new-supplier");
    sel.addEventListener("change", () => (box.hidden = sel.value !== "__new"));
  }

  // Add or edit a document (any document; generated ones keep their id so document-center links still work).
  function docForm(p, d, preset) {
    preset = preset || {};
    const parties = [{ id: p.pm_id, name: "You (PM)" }, { id: p.customer.id, name: `Customer: ${p.customer.name}` }]
      .concat(M.subcontractors(S, p).map((x) => ({ id: x.company.id, name: x.company.name })))
      .concat(p.products.map((pr) => ({ id: pr.supplier_id, name: company(pr.supplier_id).name })))
      .filter((x, i, a) => a.findIndex((y) => y.id === x.id) === i);
    const v = d ? { name: d.name, step: d.task.key, product_id: d.product_id || "", status: d.status, next_id: d.next ? d.next.id : p.pm_id, due_date: dateOr(d.due), notes: d.notes || "" }
      : { name: "", step: preset.step || (preset.product_id ? "procurement" : (p.current[0] || p.tasks[0]).key), product_id: preset.product_id || "", status: "waiting", next_id: preset.next_id || p.pm_id, due_date: "", notes: "" };
    openModal(d ? `Edit document: ${d.name}` : "Add document", `
      <form id="doc-form" class="form-grid" novalidate>
        ${field("Document", `<input name="name" required value="${esc(v.name)}" placeholder="e.g. Lien waiver">`, true)}
        ${field("Step", `<select name="step">${D.TEMPLATE.map((t) => opt(t.key, t.name, t.key === v.step)).join("")}</select>`)}
        ${field("Product (optional)", `<select name="product_id">${opt("", "None", !v.product_id)}${p.products.map((pr) => opt(pr.id, pr.name, pr.id === v.product_id)).join("")}</select>`)}
        ${field("Status", `<select name="status">${opt("not_started", "Not started", v.status === "not_started")}${opt("waiting", "In progress", v.status === "waiting")}${opt("complete", "Complete", v.status === "complete")}</select>`)}
        ${field("Waiting on", `<select name="next_id">${parties.map((x) => opt(x.id, x.name, x.id === v.next_id)).join("")}</select>`)}
        ${field("Due", `<input name="due_date" type="date" value="${esc(v.due_date)}">`)}
        ${field("Notes", `<textarea name="notes" rows="3">${esc(v.notes)}</textarea>`, true)}
        <p class="tiny muted span-2">Documents waiting on you show up in your to-do list.</p>
        <div class="form-actions span-2"><button class="button" type="submit">${d ? "Save changes" : "Add document"}</button><button class="button ghost" type="button" data-action="close-modal">Cancel</button>
          ${d ? `<button class="button danger push-right" type="button" data-role="delete">Remove document</button>` : ""}</div>
      </form>`, true);
    wireForm("doc-form", (f) => {
      if (!f.name.trim()) return toast("Give the document a name.", true);
      save((data) => {
        const pe = projEdits(data, p.id);
        const rec = { name: f.name.trim(), step: f.step, product_id: f.product_id || null, status: f.status, next_id: f.next_id, due_date: f.due_date, notes: f.notes.trim(),
          completed_date: f.status === "complete" ? (d && d.status === "complete" ? (d.history.length ? S.cal.date(d.history[d.history.length - 1].at) : today) : today) : "" };
        if (d && !d.custom) (pe.doc_edits = pe.doc_edits || {})[d.id] = rec;
        else {
          pe.docs_added = pe.docs_added || [];
          if (d) Object.assign(pe.docs_added.find((x) => x.id === d.id), rec);
          else pe.docs_added.push({ id: `${p.id}:doc:${newId(data, "c")}`, ...rec });
        }
      }, d ? "Document saved." : "Document added.");
    }, () => save((data) => {
      const pe = projEdits(data, p.id);
      if (d.custom) pe.docs_added = (pe.docs_added || []).filter((x) => x.id !== d.id);
      else { pe.docs_removed = (pe.docs_removed || []).concat(d.id); if (pe.doc_edits) delete pe.doc_edits[d.id]; }
    }, "Document removed."));
  }

  // Add a contractor (from the database or a new company) or edit one: contact details and which steps they own.
  function contractorForm(p, companyId, presetId) {
    const editing = !!companyId, c = editing ? company(companyId) : null;
    const sub = editing && M.subcontractors(S, p).find((x) => x.company.id === companyId);
    const onProject = new Set(M.subcontractors(S, p).map((x) => x.company.id));
    const choices = S.companies.filter((x) => !["customer"].includes(x.trade) && !onProject.has(x.id)).sort((a, b) => (a.trade + a.name).localeCompare(b.trade + b.name));
    const steps = p.tasks.filter((t) => !["eqore", "customer"].includes(t.role));
    const stepBox = (t) => {
      const mineNow = editing && t.owner_id === companyId, locked = mineNow && t.default_owner_id === companyId;
      return `<label class="check-row"><input type="checkbox" name="step_${t.key}" ${mineNow ? "checked" : ""} ${locked ? "disabled" : ""}><span>${esc(t.name)}<small>${locked ? "Original owner: assign another company to replace them" : "Now: " + esc(company(t.owner_id).name)}${t.done ? " · done" : ""}</small></span></label>`;
    };
    openModal(editing ? `Edit contractor: ${c.name}` : "Add contractor", `
      <form id="contractor-form" class="form-grid" novalidate>
        ${editing ? "" : field("Company", `<select name="company_id">${opt("", "Choose from the contractor database", !presetId)}${choices.map((x) => opt(x.id, `${x.name} (${D.TRADES[x.trade] || x.trade}, ${x.city || x.state})`, x.id === presetId)).join("")}${opt("__new", "+ New company…")}</select>`, true)}
        <fieldset class="new-supplier span-2" ${editing ? "" : "hidden"}><legend>${editing ? "Contact details" : "New company"}</legend><div class="form-grid">
          ${editing ? "" : field("Company name", `<input name="name">`) + field("Job type", `<select name="trade">${Object.entries(D.TRADES).filter(([k]) => !["customer", "eqore"].includes(k)).map(([k, l]) => opt(k, l)).join("")}</select>`) + field("City", `<input name="city">`) + field("State", `<select name="state">${opt("MA", "MA", p.state === "MA")}${opt("CA", "CA", p.state === "CA")}</select>`)}
          ${field("Contact", `<input name="contact" value="${esc(editing ? c.contact : "")}">`)}${field("Email", `<input name="email" type="email" value="${esc(editing ? c.email : "")}">`)}
          ${field("Phone", `<input name="phone" value="${esc(editing ? c.phone || "" : "")}">`)}${editing ? field("Notes", `<input name="notes" value="${esc(c.notes || "")}">`) : ""}</div></fieldset>
        <fieldset class="span-2"><legend>Steps they own on ${esc(p.name)}</legend><div class="check-grid">${steps.map(stepBox).join("")}</div></fieldset>
        <div class="form-actions span-2"><button class="button" type="submit">${editing ? "Save changes" : "Add to project"}</button><button class="button ghost" type="button" data-action="close-modal">Cancel</button>
          ${editing && sub && sub.added ? `<button class="button danger push-right" type="button" data-role="delete">Remove from project</button>` : ""}</div>
      </form>`, true);
    const form = wireForm("contractor-form", (f) => {
      let id = companyId || f.company_id;
      if (!id) return toast("Choose a company, or add a new one.", true);
      if (id === "__new" && !f.name.trim()) return toast("Give the new company a name.", true);
      if (f.email && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(f.email.trim())) return toast("That email address doesn't look right.", true);
      save((data) => {
        if (id === "__new") {
          id = newId(data, "X-");
          data.companies[id] = { id, name: f.name.trim(), trade: f.trade, city: f.city.trim(), state: f.state, contact: f.contact.trim(), email: f.email.trim(), phone: f.phone.trim() };
        } else if (editing) {
          const contact = { contact: f.contact.trim(), email: f.email.trim(), phone: f.phone.trim(), notes: (f.notes || "").trim() };
          if (data.companies[id]) Object.assign(data.companies[id], contact); else data.company_edits[id] = contact;
        }
        const pe = projEdits(data, p.id);
        pe.owners = pe.owners || {};
        steps.forEach((t) => {
          const checked = !!f["step_" + t.key];
          if (checked) { if (t.default_owner_id === id) delete pe.owners[t.key]; else pe.owners[t.key] = id; }
          else if (pe.owners[t.key] === id) delete pe.owners[t.key];
        });
        pe.contractors_added = pe.contractors_added || [];
        if (!editing && !pe.contractors_added.includes(id) && !p.tasks.some((t) => t.default_owner_id === id)) pe.contractors_added.push(id);
      }, editing ? "Contractor saved. Timeline updated." : "Contractor added to the project.");
    }, () => save((data) => {
      const pe = projEdits(data, p.id);
      pe.contractors_added = (pe.contractors_added || []).filter((x) => x !== companyId);
      Object.keys(pe.owners || {}).forEach((k) => pe.owners[k] === companyId && delete pe.owners[k]);
    }, "Contractor removed from the project."));
    const sel = form.querySelector("[name=company_id]");
    if (sel) {
      const box = form.querySelector(".new-supplier");
      sel.addEventListener("change", () => (box.hidden = sel.value !== "__new"));
    }
  }

  // ---------- global actions ----------
  document.addEventListener("click", async (e) => {
    const el = e.target.closest("[data-action]");
    if (!el) return;
    const a = el.dataset.action, p = el.dataset.project && project(el.dataset.project);
    if (a === "close-modal") return closeModal();
    if (a === "logout") { await api("/api/logout", { method: "POST", body: "{}" }).catch(() => {}); me = { signed_in: false, google_configured: me.google_configured }; cache.inbox = null; cache.gcal = {}; WS = { version: 0, data: {} }; S = M.build(D, today); location.hash = "#/login"; return render(); }
    if (a === "open-calendar") { openModal(`Calendar: ${p.name}`, `<div id="modal-cal"></div>`, true); return bigCalendar(p, document.getElementById("modal-cal"), monthStart(today)); }
    if (a === "docs") return docsModal(p, el.dataset.company);
    if (a === "email") return composeModal(draftFor(p, el.dataset.company));
    if (a === "email-todo") return composeModal(todoDraft(p, p.todos[+el.dataset.i]));
    if (a === "database") return databaseModal(p);
    if (a === "calendar-at") { openModal(`Calendar: ${p.name}`, `<div id="modal-cal"></div>`, true); return bigCalendar(p, document.getElementById("modal-cal"), monthStart(el.dataset.date), el.dataset.date); }
    const prod = el.dataset.productId && p && p.products.find((x) => x.id === el.dataset.productId);
    if (a === "product-docs") return productDocsModal(p, prod);
    if (a === "email-product") return composeModal(productDraft(p, prod));
    if (a === "edit-product") return productForm(p, prod);
    if (a === "add-product") return productForm(p, null);
    if (a === "edit-doc") return docForm(p, p.docs.find((d) => d.id === el.dataset.doc));
    if (a === "add-doc") return docForm(p, null, { step: el.dataset.step, product_id: el.dataset.product, next_id: el.dataset.party });
    if (a === "add-contractor") return contractorForm(p, null, el.dataset.company);
    if (a === "edit-contractor") return contractorForm(p, el.dataset.company);
  });
  document.addEventListener("keydown", (e) => {
    if ((e.key === "Enter" || e.key === " ") && e.target.matches("[role=button][data-action]")) { e.preventDefault(); e.target.click(); }
  });

  async function boot(hash) {
    try { me = await api("/api/me"); } catch (e) { me = { signed_in: false, google_configured: false }; }
    if (me.signed_in) await loadWorkspace();
    if (hash) { if (location.hash === hash) render(); else location.hash = hash; return; }
    render();
  }
  boot();
})();
