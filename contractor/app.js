(() => {
  'use strict';
  const M = window.EQORE_CT, DB = window.EQORE_CONTRACTOR_DB, CC = window.EQORE_SEED;
  const app = document.getElementById('app');
  const fmt = M.fmt;
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const money = (n) => '$' + Math.round(n).toLocaleString('en-US');
  const SESSION = 'eqore-contractor-session';

  // Icons: same set and drawing style as the deployment workspace.
  const paths = {
    grid: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
    branch: '<circle cx="6" cy="5" r="2"/><circle cx="18" cy="7" r="2"/><circle cx="6" cy="19" r="2"/><path d="M6 7v10m0-5h6a6 6 0 0 0 6-3"/>',
    person: '<circle cx="12" cy="8" r="3.5"/><path d="M5 21v-3a7 7 0 0 1 14 0v3"/>',
    layers: '<path d="m12 3 10 5-10 5L2 8l10-5Zm-10 9 10 5 10-5M2 16l10 5 10-5"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    chevron: '<path d="m9 6 6 6-6 6"/>',
    check: '<path d="m5 12 4 4L19 6"/>',
    calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 11h18"/>',
    alert: '<path d="m12 3 10 18H2L12 3Z"/><path d="M12 9v5m0 3h.01"/>',
    info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10h.01"/>',
    money: '<circle cx="12" cy="12" r="9"/><path d="M15 8h-5a2 2 0 0 0 0 4h4a2 2 0 0 1 0 4H9m3-10v12"/>',
    flag: '<path d="M5 21V3m0 1c5-4 9 4 14 0v10c-5 4-9-4-14 0"/>',
    inbox: '<path d="m5 3-3 12v6h20v-6L19 3H5Zm-3 12h6l2 3h4l2-3h6"/>',
    spark: '<path d="m12 3 2.3 6.7L21 12l-6.7 2.3L12 21l-2.3-6.7L3 12l6.7-2.3L12 3Z"/>',
    camera: '<path d="M4 7h3l2-3h6l2 3h3a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1Z"/><circle cx="12" cy="13" r="4"/>',
    refresh: '<path d="M20 7v5h-5M4 17v-5h5"/><path d="M5.4 7a8 8 0 0 1 13.2-1L20 9M4 15l1.4 3a8 8 0 0 0 13.2-1"/>',
    out: '<path d="M15 4h4a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-4M10 17l5-5-5-5M15 12H3"/>',
  };
  const icon = (n) => `<svg class="icon" aria-hidden="true" viewBox="0 0 24 24">${paths[n] || paths.info}</svg>`;

  const URGENCY = { 1: ['Critical', 'Work is stopped'], 2: ['High', 'Will slip this week'], 3: ['Medium', 'Needs a decision soon'], 4: ['Low', 'Can wait a few days'], 5: ['FYI', 'Heads-up only'] };
  const STATE = { done: ['Done', 'green'], in_progress: ['In progress', 'gold'], ready: ['Ready', 'orange'], waiting: ['Waiting', 'outline'], problem: ['Problem reported', 'red'] };

  let S = null, V = 0, me = loadSession(), saving = false, toastTimer = null;
  let draft = null; // report form being filled in
  const ui = { pmNotes: {} };

  // ---------------- Server ----------------
  async function api(method, url, body) {
    const res = await fetch(url, { method, headers: body ? { 'Content-Type': 'application/json' } : {}, body: body ? JSON.stringify(body) : undefined });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) { const e = new Error(data.error || res.statusText); e.status = res.status; e.data = data; throw e; }
    return data;
  }
  async function boot() {
    try {
      const doc = await api('GET', '/api/state');
      V = doc.version;
      if (doc.state) S = doc.state;
      else { S = M.seed(CC, DB); await save(S, 'Created the demo portfolio'); }
    } catch (e) {
      app.innerHTML = `<div class="loading-shell"><div class="brand-mark">e</div><h1>Start the portal server</h1><p>Run <code>python contractor/server.py</code> from the repo root, then open http://127.0.0.1:8780/</p></div>`;
      return;
    }
    render();
    setInterval(poll, 2500);
  }
  async function save(next) {
    saving = true;
    try { const r = await api('PUT', '/api/state', { base_version: V, state: next }); V = r.version; S = next; return true; }
    catch (e) {
      if (e.status === 409) { S = e.data.state; V = e.data.version; render(); toast(e.message + ' Please try again.', true); return false; }
      toast(e.message, true); return false;
    } finally { saving = false; }
  }
  async function poll() {
    if (saving) return;
    try {
      const { version } = await api('GET', '/api/version');
      if (version === V) return;
      const doc = await api('GET', '/api/state');
      V = doc.version;
      if (!doc.state) { S = M.seed(CC, DB); await save(S); }
      else S = doc.state;
      const typing = document.activeElement && /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName);
      if (!typing) render();
    } catch (e) { /* server briefly unavailable */ }
  }

  // ---------------- Session ----------------
  function loadSession() { try { return JSON.parse(sessionStorage.getItem(SESSION)); } catch (e) { return null; } }
  function setSession(v) { me = v; try { v ? sessionStorage.setItem(SESSION, JSON.stringify(v)) : sessionStorage.removeItem(SESSION); } catch (e) {} }
  const isPM = () => me && me.kind === 'pm';
  const myCompany = () => (me && me.kind === 'company' ? M.company(S, me.id) : null);

  function toast(msg, error) {
    let t = document.getElementById('toast');
    if (!t) { t = document.createElement('div'); t.id = 'toast'; t.className = 'toast'; t.setAttribute('role', 'status'); document.body.appendChild(t); }
    t.textContent = msg; t.classList.toggle('error', !!error); t.classList.add('show');
    clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.remove('show'), 4200);
  }

  // ---------------- Routing ----------------
  const route = () => { const [view, ...rest] = location.hash.replace(/^#\/?/, '').split('/'); return { view: view || '', arg: decodeURIComponent(rest.join('/')) }; };
  const go = (h) => { if (location.hash === '#' + h) render(); else location.hash = h; };
  window.addEventListener('hashchange', () => { render(); window.scrollTo(0, 0); });

  // ---------------- Render ----------------
  function render() {
    if (!S) return;
    if (!me || (me.kind === 'company' && !myCompany())) { app.innerHTML = loginHTML(); return; }
    const r = route();
    const sch = M.schedule(S);
    let page, crumb;
    if (isPM()) {
      if (r.view === 'project' && M.project(S, r.arg)) [crumb, page] = ['Project timeline', projectHTML(r.arg, sch)];
      else if (r.view === 'projects') [crumb, page] = ['Projects', projectsHTML(sch)];
      else if (r.view === 'activity') [crumb, page] = ['Activity', activityHTML()];
      else [crumb, page] = ['Approvals', approvalsHTML(sch)];
    } else {
      if (r.view === 'project' && M.project(S, r.arg)) [crumb, page] = ['Project timeline', projectHTML(r.arg, sch)];
      else if (r.view === 'report' && M.task(S, r.arg)) [crumb, page] = ['Report a problem', reportFormHTML(r.arg, sch)];
      else if (r.view === 'reports') [crumb, page] = ['My reports', myReportsHTML()];
      else if (r.view === 'updates') [crumb, page] = ['Updates', updatesHTML()];
      else [crumb, page] = ['Tasks & timeline', tasksHTML(sch)];
    }
    app.innerHTML = `<div class="app-shell">${sidebarHTML(r)}<main class="main">
      <header class="topbar"><div class="breadcrumb"><span>Contractor portal</span>${icon('chevron')}<strong>${esc(crumb)}</strong></div>
        <div class="topbar-right"><span class="sync-dot"><span class="status-dot green"></span>Synced</span><span>LOCAL DEMO</span><span class="avatar">${esc(initials(isPM() ? DB.PM.name : myCompany().name))}</span></div></header>
      <div class="content">${page}</div></main></div>`;
  }
  const initials = (n) => n.split(/\s+/).filter((w) => /^[A-Z]/.test(w)).slice(0, 2).map((w) => w[0]).join('');

  function sidebarHTML(r) {
    let nav, who, sub;
    if (isPM()) {
      const pending = S.reports.filter((x) => x.status === 'pending').length;
      nav = [['approvals', 'Approvals', 'inbox', pending], ['projects', 'Projects', 'layers', S.projects.length], ['activity', 'Activity', 'clock', null]];
      who = DB.PM.name; sub = DB.PM.role;
    } else {
      const c = myCompany();
      const open = S.tasks.filter((t) => t.owner_id === c.id && t.status !== 'done').length;
      const unseen = S.notices.filter((n) => n.owner === c.id && !n.seen).length;
      const reps = S.reports.filter((x) => x.by === c.id && x.status === 'pending').length;
      nav = [['tasks', 'Tasks & timeline', 'grid', open], ['reports', 'My reports', 'flag', reps || null], ['updates', 'Updates', 'clock', unseen || null]];
      who = c.name; sub = `${DB.TRADES[c.trade].label} · ${c.city}, ${c.state}`;
    }
    const active = (k) => r.view === k || (!r.view && k === nav[0][0]) || (r.view === 'report' && k === 'tasks') || (r.view === 'project' && k === (isPM() ? 'projects' : 'tasks'));
    return `<aside class="sidebar">
      <div class="brand"><div class="brand-mark">e</div><div><div class="brand-word">EQORE</div><div class="brand-subtitle">Contractor portal</div></div></div>
      <div class="sidebar-caption">Signed in as</div>
      <div class="side-user">${esc(who)}</div><p class="side-description">${esc(sub)}</p>
      <div class="sidebar-caption">${isPM() ? 'Project lead' : 'Your work'}</div>
      <nav class="navigation">${nav.map(([k, label, ic, n]) => `<button class="nav-link${active(k) ? ' active' : ''}" data-go="${k}">${icon(ic)}<span>${label}</span>${n != null ? `<span class="nav-count">${n}</span>` : ''}</button>`).join('')}
        <button class="nav-link" data-act="signout">${icon('out')}<span>Sign out</span></button></nav>
      <div class="sidebar-bottom"><p class="side-description">Demo data. Simulated clock: ${fmt(S.today)}, 2026.</p>
        <button class="button on-navy small" data-act="reset">${icon('refresh')}Reset demo</button></div>
    </aside>`;
  }

  // ---------------- Login ----------------
  function loginHTML() {
    const groups = {};
    S.companies.forEach((c) => (groups[DB.TRADES[c.trade].label] = groups[DB.TRADES[c.trade].label] || []).push(c));
    const opts = `<option value="">Choose a demo account…</option><optgroup label="EQORE"><option value="${esc(DB.PM.email)}">${esc(DB.PM.name)} (PM)</option></optgroup>` +
      Object.entries(groups).map(([g, cs]) => `<optgroup label="${esc(g)}">${cs.map((c) => `<option value="${esc(c.email)}">${esc(c.name)}</option>`).join('')}</optgroup>`).join('');
    return `<div class="login-shell">
      <section class="login-side">
        <div class="brand"><div class="brand-mark">e</div><div><div class="brand-word">EQORE</div><div class="brand-subtitle">Contractor portal</div></div></div>
        <h2>Everything you owe across EQORE battery installs, in one place.</h2>
        <p>Crews, suppliers, inspectors and utilities sign in to see their upcoming tasks and each project's timeline.</p>
        <ul><li>Mark a task done and the project timeline and PM update automatically.</li><li>Report a problem with photos and an urgency level. The PM gets an AI summary.</li><li>Check which other companies could step in, and what it does to go-live. The PM approves before anything is booked.</li></ul>
        <p>All companies, sites and dates are synthetic demo data.</p>
      </section>
      <main class="login-main"><section class="panel login-card">
        <div class="panel-header"><div><h2>Sign in</h2><p>Demo sign-in for a local prototype, not real authentication.</p></div></div>
        <form class="panel-body" data-form="login">
          <label class="field"><span>Email</span><input name="email" type="email" autocomplete="username" required placeholder="you@company.example"></label>
          <label class="field"><span>Password</span><input name="password" type="password" autocomplete="current-password" required></label>
          <div id="login-error"></div>
          <button class="button" type="submit">Sign in</button>
          <label class="field"><span>Demo accounts</span><select data-act="pick-account">${opts}</select><small>Every demo account uses the password <b>${esc(DB.DEMO_PASSWORD)}</b>.</small></label>
        </form>
      </section></main></div>`;
  }

  // ---------------- Contractor: tasks & timeline ----------------
  function tasksHTML(sch) {
    const c = myCompany();
    const items = M.tasksFor(S, c.id, sch);
    const open = items.filter((x) => x.state !== 'done');
    const weekEnd = M.addDays(S.today, 7);
    const dueWeek = open.filter((x) => x.start <= weekEnd).length;
    const problems = open.filter((x) => x.state === 'problem').length;
    const projects = [...new Set(open.map((x) => x.project.id))];
    const unseen = S.notices.filter((n) => n.owner === c.id && !n.seen);
    const changed = new Set(unseen.map((n) => n.task_id));
    const done = items.filter((x) => x.state === 'done').slice(-5).reverse();
    return `<div class="page-heading"><div><div class="eyebrow">Contractor workspace</div><h1>${esc(c.name)}</h1>
        <p>${esc(DB.TRADES[c.trade].label)} based in ${esc(c.city)}, ${esc(c.state)}. When you mark a task done, the project timeline and the EQORE PM update right away.</p>
        <div class="project-tags">${c.certifications.map((x) => `<span class="badge outline">${esc(x)}</span>`).join('')}<span class="badge outline">${c.crews >= 99 ? 'Agency' : c.crews + ' crew' + (c.crews > 1 ? 's' : '')}</span></div></div>
        <div class="project-heading-right"><div class="eyebrow">Simulated clock</div><div class="date">${fmt(S.today)}, 2026</div></div></div>
      ${unseen.length ? `<div class="notice job">${icon('info')}<div><strong>${unseen.length} schedule update${unseen.length > 1 ? 's' : ''} since you last looked</strong><p>${esc(unseen.slice(-2).map((n) => n.text).join(' · '))} <a href="#updates">See all updates</a></p></div></div>` : ''}
      <div class="stats">
        ${stat('Open tasks', open.length, `across ${projects.length} project${projects.length === 1 ? '' : 's'}`, 'grid')}
        ${stat('Starting in the next 7 days', dueWeek, `through ${fmt(weekEnd)}`, 'calendar')}
        ${stat('Problems reported', problems, problems ? 'waiting for the PM' : 'nothing open', 'flag')}
        ${stat('Completed', items.length - open.length, 'recorded on EQORE timelines', 'check')}
      </div>
      <section class="panel" style="margin-bottom:19px"><div class="panel-header"><div><h2>Next three weeks</h2><p>Your tasks by day. Weekends are shaded; today is highlighted.</p></div>${icon('calendar')}</div>
        <div class="panel-body">${gantt(open.slice(0, 14).map((x) => ({ x, label: x.project.id, sub: shortName(x.task.name), mine: true })), S.today, 21)}</div></section>
      <div class="workspace-grid">
        <section class="panel"><div class="panel-header"><div><h2>Upcoming tasks</h2><p>Is the work done? Say yes and the timeline moves on. If not, report the problem.</p></div></div>
          <div class="panel-body">${open.length ? open.map((x) => taskRowHTML(x, changed.has(x.task.id))).join('') : empty('check', 'No open tasks', 'New tasks the PM assigns to you will show up here.')}</div></section>
        <div class="decision-stack">
          <section class="panel"><div class="panel-header"><div><h2>Recently completed</h2></div></div><div class="panel-body">
            ${done.length ? `<div class="timeline">${done.map((x) => `<div class="timeline-item"><h3>${esc(x.task.name)}</h3><p><a href="#project/${esc(x.project.id)}">${esc(x.project.id)}</a> · ${esc(x.project.name)}</p><div class="timeline-meta">Finished ${fmt(x.finish)}</div></div>`).join('')}</div>` : empty('clock', 'Nothing completed yet', '')}
          </div></section>
        </div>
      </div>`;
  }
  const shortName = (n) => n.replace(/\s*\(.*\)$/, '');
  function stat(label, value, bottom, ic) {
    return `<div class="stat"><div class="stat-top"><span>${esc(label)}</span>${icon(ic)}</div><div class="stat-number${String(value).replace(/<[^>]+>/g, '').length > 14 ? ' text-value' : String(value).length > 6 ? ' small-value' : ''}">${value}</div><div class="stat-bottom">${esc(bottom)}</div></div>`;
  }
  function empty(ic, title, text) { return `<div class="empty-state">${icon(ic)}<h3>${esc(title)}</h3>${text ? `<p>${esc(text)}</p>` : ''}</div>`; }

  function taskRowHTML(x, changed) {
    const t = x.task, [label, color] = STATE[x.state];
    const d = new Date(x.start + 'T00:00:00Z');
    const when = x.start === x.finish ? fmt(x.start) : `${fmt(x.start)} – ${fmt(x.finish)}`;
    const rep = t.problem && S.reports.find((r) => r.id === t.problem);
    let actions;
    if (x.state === 'problem') actions = `<span class="hint">${icon('flag')} Report ${esc(rep.id)} is with the PM${rep.no_resource ? ' (marked urgent: no resource found)' : ''}.</span> <a href="#reports">View report</a>`;
    else if (x.state === 'waiting') actions = `<span class="hint">Waiting on ${esc(x.waitingOn.map((p) => `${shortName(p.name)} (${M.ownerName(S, p.owner_id)})`).join(', '))}</span><button class="button secondary small" data-act="report" data-id="${esc(t.id)}">${icon('flag')}Report a problem</button>`;
    else actions = `<span class="hint">Is this done?</span><button class="button small" data-act="done" data-id="${esc(t.id)}">${icon('check')}Yes, done</button><button class="button secondary small" data-act="report" data-id="${esc(t.id)}">${icon('flag')}No, there's a problem</button>`;
    const origin = t.origin && t.origin.report_id ? `<span class="badge orange">Assigned by PM from ${esc(t.origin.report_id)}</span>` : '';
    return `<article class="bottleneck-row ${x.state}"><div class="rank-marker date"><small>${d.toLocaleDateString('en-US', { month: 'short', timeZone: 'UTC' })}</small>${d.getUTCDate()}</div>
      <div class="bottleneck-content"><div class="bottleneck-top"><h3>${esc(t.name)}</h3><span class="badge ${color}">${label}</span></div>
        <div class="bottleneck-meta"><span><a class="plain" href="#project/${esc(x.project.id)}"><b>${esc(x.project.id)}</b></a></span><span>${esc(x.project.name)}</span><span>${esc(when)}</span>${changed ? '<span class="changed">Date changed</span>' : ''}${origin}</div>
        <div class="task-actions">${actions}</div></div></article>`;
  }

  // rows: [{ x: {task,start,finish,state}, label, sub, mine }]
  function gantt(rows, from, days) {
    if (!rows.length) return empty('calendar', 'Nothing scheduled', '');
    const dates = Array.from({ length: days }, (_, i) => M.addDays(from, i));
    const last = dates[dates.length - 1];
    const cols = `grid-template-columns:minmax(120px,170px) repeat(${days},minmax(18px,1fr))`;
    const head = `<div class="gantt-head"><div class="gantt-label">Task</div>${dates.map((d, i) => `<div class="gantt-day">${i === 0 || d.endsWith('-01') || new Date(d + 'T00:00:00Z').getUTCDay() === 1 ? esc(fmt(d)) : ''}</div>`).join('')}</div>`;
    const body = rows.map(({ x, label, sub, mine }) => {
      const cls = [x.state === 'done' ? 'done' : x.state === 'problem' ? 'problem' : x.state === 'waiting' && !mine ? 'waiting' : mine ? 'mine' : '', x.task.key === 'added' ? 'added' : ''].join(' ');
      return `<div class="gantt-row"><div class="gantt-label${mine ? ' mine' : ''}" title="${esc(x.task.name)}">${esc(label)}<small>${esc(sub)}</small></div>${dates.map((d) => {
        const wk = !M.isWorkday(d) ? ' weekend' : '', td = d === S.today ? ' today' : '';
        const on = x.start <= d && d <= x.finish && (M.isWorkday(d) || x.task.unit === 'cal');
        const bar = on ? `<div class="gantt-bar ${cls}${d === from && x.start < from ? ' cont-l' : ''}${d === last && x.finish > last ? ' cont-r' : ''}" title="${esc(x.task.name)}: ${fmt(x.start)}–${fmt(x.finish)}"></div>` : '';
        return `<div class="gantt-day${wk}${td}">${bar}</div>`;
      }).join('')}</div>`;
    }).join('');
    return `<div class="gantt"><div class="gantt-grid" style="${cols}">${head}${body}</div></div>
      <div class="legend"><span><i style="background:var(--navy)"></i>${isPM() ? 'Open' : 'Yours'}</span><span><i style="background:#8da491"></i>Other parties</span><span><i style="background:#b9d3c6"></i>Done</span><span><i style="background:var(--red)"></i>Problem</span><span><i style="background:var(--accent)"></i>Added by PM approval</span><span><i style="background:#fdf1e8;border:1px solid #f0d6c4"></i>Today</span></div>`;
  }

  // ---------------- Project timeline (contractor and PM) ----------------
  function projectHTML(id, sch) {
    const p = M.project(S, id), sp = sch.projects[id];
    const tasks = S.tasks.filter((t) => t.project_id === id).map((t) => ({ task: t, project: p, ...M.taskState(S, t, sch) })).sort((a, b) => a.start.localeCompare(b.start) || a.finish.localeCompare(b.finish));
    const mineId = isPM() ? null : me.id;
    const done = tasks.filter((x) => x.state === 'done').length;
    const next = tasks.find((x) => x.state !== 'done');
    const reports = S.reports.filter((r) => r.project_id === id);
    const from = M.addDays(tasks.reduce((m, x) => (x.state !== 'done' && x.start < m ? x.start : m), sp.go_live), -2);
    const days = Math.min(42, Math.max(14, M.diffDays(sp.go_live, from) + 3));
    const slip = sp.slip_days;
    return `<div class="page-heading"><div><div class="eyebrow">Project timeline</div><h1>${esc(p.name)}</h1>
        <p>${esc(p.id)} · ${esc(p.city)}, ${esc(p.state)} · ${esc(p.utility)} · Install planned ${fmt(p.install_date)}. Dates recalculate whenever a task is marked done, a problem is reported or the PM approves a change.</p>
        <div class="project-tags"><span class="badge outline">${p.power_kw} kW / ${p.energy_kwh} kWh</span><span class="badge outline">Synthetic project</span>${slip > 0 ? `<span class="badge red">${slip} day${slip > 1 ? 's' : ''} behind target</span>` : '<span class="badge green">On target</span>'}</div></div>
        <div class="project-heading-right"><div class="eyebrow">Go-live</div><div class="date">${fmt(sp.go_live)}</div><div class="timezone">Target ${fmt(p.target_go_live)}</div></div></div>
      <div class="stats">
        ${stat('Tasks done', `${done}<span> / ${tasks.length}</span>`, 'contract to handover', 'check')}
        ${stat('Next task', next ? esc(shortName(next.task.name)) : 'All done', next ? `${M.ownerName(S, next.task.owner_id)} · ${fmt(next.start)}` : '', 'grid')}
        ${stat('Go-live', fmt(sp.go_live), slip > 0 ? `${slip} day(s) after the ${fmt(p.target_go_live)} target` : `target ${fmt(p.target_go_live)}`, 'flag')}
        ${stat('Delay cost', money(p.cost_of_delay_usd_per_day) + '/day', 'customer savings lost per day of slip', 'money')}
      </div>
      <section class="panel" style="margin-bottom:19px"><div class="panel-header"><div><h2>Timeline</h2><p>${mineId ? 'Your tasks are in navy. ' : ''}Each bar is one task; downstream work starts the day after its predecessors finish.</p></div></div>
        <div class="panel-body">${gantt(tasks.map((x) => ({ x, label: shortName(x.task.name), sub: M.ownerName(S, x.task.owner_id), mine: isPM() ? x.state !== 'done' : x.task.owner_id === mineId })), from, days)}</div></section>
      <section class="panel"><div class="panel-header"><div><h2>All tasks</h2><p>Who owns each step and what it is waiting on.</p></div></div>
        <div class="table-wrap"><table class="data-table"><thead><tr><th>Task</th><th>Owner</th><th>Dates</th><th>Status</th></tr></thead><tbody>
        ${tasks.map((x) => { const [l, c] = STATE[x.state]; return `<tr><td><strong>${esc(x.task.name)}</strong>${x.task.origin && x.task.origin.report_id ? `<div class="subline">From PM approval of ${esc(x.task.origin.report_id)}</div>` : ''}</td><td>${esc(M.ownerName(S, x.task.owner_id))}${x.task.owner_id === mineId ? ' <span class="badge orange">You</span>' : ''}</td><td>${fmt(x.start)}${x.finish !== x.start ? ' – ' + fmt(x.finish) : ''}</td><td><span class="badge ${c}">${l}</span>${x.state === 'waiting' ? `<div class="subline">Waiting on ${esc(x.waitingOn.map((w) => shortName(w.name)).join(', '))}</div>` : ''}</td></tr>`; }).join('')}
        </tbody></table></div></section>
      ${reports.length ? `<section class="panel" style="margin-top:19px"><div class="panel-header"><div><h2>Problem reports</h2></div></div><div class="panel-body"><div class="timeline">${reports.map((r) => `<div class="timeline-item"><h3>${esc(r.id)} · ${esc(M.task(S, r.task_id).name)} · ${statusLabel(r)}</h3><p>${esc(r.summary ? r.summary.text : r.details)}</p><div class="timeline-meta">Filed ${fmt(r.filed_at)} by ${esc(r.by_name)}</div></div>`).join('')}</div></div></section>` : ''}`;
  }

  // ---------------- Contractor: report form ----------------
  function newDraft(taskId, sch) {
    const t = M.task(S, taskId);
    return { task_id: taskId, details: '', photos: [], urgency: 0, needResource: null, mode: 'replace', trade: DB.TRADES[t.trade] && DB.TRADES[t.trade].matchable ? t.trade : 'electrical', days: t.duration || 1, from: M.nextWorkday(M.addDays(S.today, 1)) > sch.tasks[taskId].start ? M.nextWorkday(M.addDays(S.today, 1)) : sch.tasks[taskId].start, work: '', options: null, checkedKey: null, preferred: null, busy: false, uploading: 0 };
  }
  const resourceReq = (d) => ({ mode: d.mode, trade: d.trade, days: Math.max(1, Math.min(10, +d.days || 1)), from: d.from, work: d.mode === 'before' ? (d.work || '').trim() : '' });
  const reqKey = (d) => JSON.stringify(resourceReq(d));

  function reportFormHTML(taskId, sch) {
    const t = M.task(S, taskId), p = M.project(S, t.project_id);
    if (t.owner_id !== me.id) return empty('alert', 'Not your task', 'You can only report problems on tasks assigned to you.');
    if (t.problem) return `<div class="notice">${icon('info')}<div><strong>A report on this task is already with the PM</strong><p><a href="#reports">View your reports</a></p></div></div>`;
    if (!draft || draft.task_id !== taskId) draft = newDraft(taskId, sch);
    const d = draft, x = M.taskState(S, t, sch);
    const matchable = Object.entries(DB.TRADES).filter(([, v]) => v.matchable);
    const stale = d.options && d.checkedKey !== reqKey(d);
    return `<div class="page-heading"><div><div class="eyebrow">Report a problem</div><h1>${esc(t.name)}</h1>
        <p><a href="#project/${esc(p.id)}">${esc(p.id)}</a> · ${esc(p.name)} · scheduled ${fmt(x.start)}${x.finish !== x.start ? ' – ' + fmt(x.finish) : ''}. The PM gets your report with an AI summary and decides on any extra resource.</p></div></div>
      <div class="workspace-grid"><section class="panel"><form class="panel-body" data-form="report" style="padding-top:22px">
        <div class="form-section">
          <label class="field"><span>What's wrong?</span><textarea name="details" data-bind="details" placeholder="What happened, what you need, and anything the PM should know." maxlength="4000">${esc(d.details)}</textarea><small>Be specific: what's broken or missing, since when, and what it stops.</small></label>
          <div class="field"><span class="field-label">Photos</span>
            <div class="photo-grid">${d.photos.map((u, i) => `<div class="photo"><img src="${esc(u)}" alt="Report photo ${i + 1}"><button type="button" data-act="rm-photo" data-i="${i}">Remove</button></div>`).join('')}</div>
            <label class="photo-drop">${icon('camera')}<span>${d.uploading ? `Uploading ${d.uploading} photo(s)…` : 'Add photos (JPEG or PNG, up to 6)'}</span><input type="file" accept="image/*" multiple data-act="photos"></label></div>
        </div>
        <div class="form-section"><div class="field"><span class="field-label">Urgency (1 is most urgent)</span>
          <div class="segmented">${[1, 2, 3, 4, 5].map((u) => `<button type="button" class="u${u}${d.urgency === u ? ' on' : ''}" data-act="urgency" data-u="${u}">${u} · ${URGENCY[u][0]}<small>${URGENCY[u][1]}</small></button>`).join('')}</div></div></div>
        <div class="form-section"><div class="field"><span class="field-label">Do you need another company to step in?</span>
          <div class="segmented"><button type="button" class="${d.needResource === false ? 'on' : ''}" data-act="need" data-v="no">No<small>Just tell the PM</small></button><button type="button" class="${d.needResource ? 'on' : ''}" data-act="need" data-v="yes">Yes<small>Find an available company</small></button></div></div>
          ${d.needResource ? `<div class="form-grid">
            <label class="field"><span>How they help</span><select data-bind="mode"><option value="replace"${d.mode === 'replace' ? ' selected' : ''}>They take over this task</option><option value="before"${d.mode === 'before' ? ' selected' : ''}>They do work before this task</option></select></label>
            <label class="field"><span>Type of company</span><select data-bind="trade">${matchable.map(([k, v]) => `<option value="${k}"${d.trade === k ? ' selected' : ''}>${esc(v.label)}</option>`).join('')}</select></label>
            <label class="field"><span>Work days needed</span><input type="number" min="1" max="10" data-bind="days" value="${esc(d.days)}"></label>
            <label class="field"><span>Needed from</span><input type="date" data-bind="from" value="${esc(d.from)}" min="${esc(M.addDays(S.today, 1))}"></label>
            ${d.mode === 'before' ? `<label class="field" style="grid-column:1/-1"><span>What should they do?</span><input type="text" data-bind="work" maxlength="120" value="${esc(d.work)}" placeholder="e.g. Regrade and re-pour pad corner"></label>` : ''}
          </div>
          <div class="form-actions"><button type="button" class="button secondary" data-act="check">${icon('refresh')}${d.options ? 'Check again' : 'Check available companies'}</button><small class="hint">Checks the contractor database for ${esc(p.state)} companies of that type, their calendars and travel distance.</small></div>
          ${d.options ? optionsHTML(d, stale, p) : ''}` : ''}
        </div>
        <div class="form-actions"><button type="submit" class="button"${d.busy || d.uploading ? ' disabled' : ''}>${d.busy ? 'Writing the AI summary for the PM…' : 'Send report to PM'}</button><a class="button ghost" href="#tasks">Cancel</a></div>
      </form></section>
      <div class="decision-stack"><section class="panel next-action"><div class="panel-header"><div class="next-action-label">${icon('info')} What happens next</div></div><div class="panel-body">
        <div class="action-reason"><div class="reason-label">PM</div><div class="reason-copy">Gets your report, photos and an AI summary in their approvals inbox.</div></div>
        <div class="action-reason"><div class="reason-label">Resource</div><div class="reason-copy">Nothing is booked until the PM approves. The approved company gets the task on their dashboard, and every affected contractor sees the new dates.</div></div>
        <div class="action-reason"><div class="reason-label">No match</div><div class="reason-copy">If no company is available, the report goes to the PM marked urgent.</div></div>
      </div></section></div></div>`;
  }

  function optionsHTML(d, stale, p) {
    if (stale) return `<div class="notice job">${icon('info')}<div><strong>Details changed</strong><p>Check available companies again to update the options.</p></div></div>`;
    if (!d.options.length) return `<div class="notice error">${icon('alert')}<div><strong>No available ${esc(DB.TRADES[d.trade].label.toLowerCase())} company found</strong><p>No other company of this type in the ${esc(p.state)} database can reach ${esc(p.city)} and fit the work in within 25 work days. Your report will go to the PM as urgent.</p></div></div>`;
    return `<div class="option-list">${d.options.map((o) => `<label class="option${d.preferred === o.id ? ' on' : ''}"><input type="radio" name="preferred" data-act="prefer" value="${esc(o.id)}"${d.preferred === o.id ? ' checked' : ''}>
      <div><h4>${esc(o.company)}</h4><div class="subline">${esc(o.city)} · ${o.distance_mi} mi away${o.mobilization_days ? ` · ${o.mobilization_days} day(s) to mobilize` : ''} · rating ${o.rating} · ${esc(o.certifications.join(', '))}</div>
        <div class="subline">Available ${fmt(o.start)}${o.finish !== o.start ? ' – ' + fmt(o.finish) : ''} · est. ${money(o.cost_usd)}</div></div>
      <div class="impact">${impact(o)}</div></label>`).join('')}</div><small class="hint">Pick the one you'd prefer. The PM makes the final call.</small>`;
  }
  function impact(o) {
    return o.go_live_change_days > 0 ? `<strong style="color:var(--red)">Go-live +${o.go_live_change_days} day${o.go_live_change_days > 1 ? 's' : ''}</strong>${fmt(o.go_live)}` : o.go_live_change_days < 0 ? `<strong style="color:var(--teal)">Go-live ${o.go_live_change_days} days</strong>${fmt(o.go_live)}` : `<strong style="color:var(--teal)">No change to go-live</strong>${fmt(o.go_live)}`;
  }

  // ---------------- Contractor: reports & updates ----------------
  function statusLabel(r) {
    if (r.status === 'approved') return `<span class="badge green">Approved: ${esc(r.decision.option.company)} from ${fmt(r.decision.option.start)}</span>`;
    if (r.status === 'declined') return '<span class="badge outline">Resource declined</span>';
    if (r.status === 'acknowledged') return '<span class="badge outline">Acknowledged by PM</span>';
    return r.no_resource ? '<span class="badge red">Urgent: with PM, no resource found</span>' : '<span class="badge gold">Waiting for PM</span>';
  }
  function myReportsHTML() {
    const reps = S.reports.filter((r) => r.by === me.id).slice().reverse();
    return `<div class="page-heading"><div><div class="eyebrow">Problem reports</div><h1>My reports</h1><p>Reports you've sent to the EQORE PM and what they decided.</p></div></div>
      <section class="panel"><div class="panel-body" style="padding-top:8px">${reps.length ? reps.map((r) => { const t = M.task(S, r.task_id); return `<article class="bottleneck-row"><div class="rank-marker">${r.urgency}</div><div class="bottleneck-content">
        <div class="bottleneck-top"><h3>${esc(r.id)} · ${esc(t.name)}</h3>${statusLabel(r)}</div>
        <div class="bottleneck-meta"><span><a class="plain" href="#project/${esc(r.project_id)}"><b>${esc(r.project_id)}</b></a></span><span>Filed ${fmt(r.filed_at)}</span><span>Urgency ${r.urgency} · ${URGENCY[r.urgency][0]}</span>${r.photos.length ? `<span>${r.photos.length} photo(s)</span>` : ''}</div>
        <p class="bottleneck-next">${esc(r.details)}</p>${r.decision && r.decision.note ? `<p class="ranking-reason">PM note: ${esc(r.decision.note)}</p>` : ''}</div></article>`; }).join('') : empty('flag', 'No reports yet', 'Use "No, there\'s a problem" on a task to send one.')}</div></section>`;
  }
  function updatesHTML() {
    const mine = S.notices.filter((n) => n.owner === me.id).slice().reverse();
    const html = `<div class="page-heading"><div><div class="eyebrow">Schedule updates</div><h1>Updates</h1><p>New tasks and date changes on your work, with the reason.</p></div></div>
      <section class="panel"><div class="panel-body" style="padding-top:22px">${mine.length ? `<div class="timeline">${mine.map((n) => `<div class="timeline-item"><h3>${n.seen ? '' : '<span class="badge orange">New</span> '}${esc(n.text)}</h3><p>${esc(n.reason)}</p><div class="timeline-meta">${fmt(n.at)} · <a href="#project/${esc(M.task(S, n.task_id).project_id)}">${esc(M.task(S, n.task_id).project_id)}</a></div></div>`).join('')}</div>` : empty('clock', 'No updates', 'Date changes and new assignments will appear here.')}</div></section>`;
    if (mine.some((n) => !n.seen)) setTimeout(markSeen, 0);
    return html;
  }
  async function markSeen() {
    const next = M.clone(S);
    next.notices.forEach((n) => { if (n.owner === me.id) n.seen = true; });
    await save(next);
  }

  // ---------------- PM: approvals ----------------
  function approvalsHTML(sch) {
    const pending = S.reports.filter((r) => r.status === 'pending').sort((a, b) => (b.no_resource - a.no_resource) || a.urgency - b.urgency || a.id.localeCompare(b.id));
    const decided = S.reports.filter((r) => r.status !== 'pending').slice().reverse();
    const urgent = pending.filter((r) => r.no_resource || r.urgency <= 2).length;
    const slipping = S.projects.filter((p) => sch.projects[p.id].slip_days > 0);
    return `<div class="page-heading"><div><div class="eyebrow">Project lead</div><h1>Approvals</h1><p>Problem reports from contractors and agencies. Approving a resource books that company, adds the task to their dashboard and moves every affected date.</p></div>
        <div class="project-heading-right"><div class="eyebrow">Simulated clock</div><div class="date">${fmt(S.today)}, 2026</div></div></div>
      <div class="stats">${stat('Waiting for you', pending.length, 'problem reports', 'inbox')}${stat('Urgent', urgent, 'urgency 1–2 or no resource found', 'alert')}
        ${stat('Projects behind target', slipping.length, `of ${S.projects.length}`, 'flag')}${stat('Delay cost at risk', money(slipping.reduce((a, p) => a + p.cost_of_delay_usd_per_day, 0)) + '/day', 'savings lost on slipping projects', 'money')}</div>
      ${pending.length ? pending.map((r) => reportCardHTML(r, sch)).join('') : `<section class="panel">${empty('check', 'Nothing waiting', 'New contractor reports will appear here.')}</section>`}
      ${decided.length ? `<section class="panel" style="margin-top:19px"><div class="panel-header"><div><h2>Decided</h2></div></div><div class="panel-body"><div class="timeline">${decided.map((r) => `<div class="timeline-item"><h3>${esc(r.id)} · ${esc(r.project_id)} · ${esc(M.task(S, r.task_id).name)} ${statusLabel(r)}</h3><p>${esc(r.summary ? r.summary.text : r.details)}</p><div class="timeline-meta">${esc(r.by_name)} · decided ${fmt(r.decision.at)}${r.decision.note ? ' · ' + esc(r.decision.note) : ''}</div></div>`).join('')}</div></div></section>` : ''}`;
  }

  function reportCardHTML(r, sch) {
    const t = M.task(S, r.task_id), p = M.project(S, r.project_id), sp = sch.projects[p.id];
    const [ul] = URGENCY[r.urgency];
    const urgentCls = r.no_resource || r.urgency <= 2;
    const sum = r.summary || { source: 'rule', text: M.ruleSummary(S, r) };
    const res = r.resource;
    return `<section class="panel report-card${urgentCls ? ' urgent' : ''}"><div class="panel-header"><div><h2>${esc(r.id)} · ${esc(t.name)}</h2><p><a href="#project/${esc(p.id)}">${esc(p.id)}</a> · ${esc(p.name)} · from ${esc(r.by_name)} · filed ${fmt(r.filed_at)}</p></div>
        <span class="badge ${r.urgency <= 2 ? 'red' : r.urgency === 3 ? 'gold' : 'outline'}">Urgency ${r.urgency} · ${ul}</span></div>
      <div class="panel-body report-grid">
        ${r.no_resource ? `<div class="notice error">${icon('alert')}<div><strong>Urgent: no available resource found</strong><p>No other ${esc(DB.TRADES[res.trade].label.toLowerCase())} company in the ${esc(p.state)} database can reach ${esc(p.city)} and fit the work in within 25 work days. This needs your call: extend the search, pay to expedite, or re-sequence the project.</p></div></div>` : ''}
        <div class="summary-box${sum.source === 'ai' ? '' : ' rule'}"><div class="eyebrow">${sum.source === 'ai' ? `${icon('spark')} AI summary · ${esc(sum.model || 'Claude')}` : `${icon('info')} Fixed-rule summary · AI unavailable${sum.detail ? ': ' + esc(sum.detail) : ''}`}</div>${esc(sum.text)}</div>
        <details class="bottleneck-details" open><summary>Contractor's report${r.photos.length ? ` and ${r.photos.length} photo(s)` : ''}</summary><div class="detail-content" style="display:grid;gap:10px">
          <p style="white-space:pre-wrap;font-size:12px;color:var(--ink)">${esc(r.details)}</p>
          ${r.photos.length ? `<div class="photo-grid">${r.photos.map((u, i) => `<a class="photo" href="${esc(u)}" target="_blank" rel="noopener"><img src="${esc(u)}" alt="Photo ${i + 1} from ${esc(r.by_name)}"></a>`).join('')}</div>` : ''}
        </div></details>
        <dl class="kv"><dt>Go-live now</dt><dd>${fmt(sp.go_live)} (${sp.slip_days > 0 ? sp.slip_days + ' day(s) behind target' : 'on target'})</dd>
          <dt>Resource asked</dt><dd>${res ? `${esc(DB.TRADES[res.trade].label)}, ${res.days} work day(s) from ${fmt(res.from)}, ${res.mode === 'replace' ? 'taking over this task' : 'working before this task' + (res.work ? ': ' + esc(res.work) : '')}` : 'None. The contractor is flagging the issue.'}</dd></dl>
        ${res && !r.no_resource ? `<div class="option-list">${r.options.map((o) => `<div class="option${o.id === r.preferred_option_id ? ' on' : ''}"><span class="badge ${o.id === r.preferred_option_id ? 'green' : 'outline'}">${o.id === r.preferred_option_id ? 'Preferred' : 'Option'}</span>
            <div><h4>${esc(o.company)}</h4><div class="subline">${esc(o.city)} · ${o.distance_mi} mi · rating ${o.rating} · available ${fmt(o.start)}${o.finish !== o.start ? '–' + fmt(o.finish) : ''} · est. ${money(o.cost_usd)}</div></div>
            <div class="impact">${impact(o)}<div style="margin-top:6px"><button class="button small" data-act="approve" data-r="${esc(r.id)}" data-o="${esc(o.id)}">${icon('check')}Approve</button></div></div></div>`).join('')}</div>` : ''}
        <div class="decline-row"><input class="input" data-note="${esc(r.id)}" placeholder="Note to the contractor (optional)" value="${esc(ui.pmNotes[r.id] || '')}" maxlength="200">
          <button class="button secondary small" data-act="decline" data-r="${esc(r.id)}">${res ? 'Decline resource' : 'Acknowledge'}</button></div>
      </div></section>`;
  }

  function projectsHTML(sch) {
    const rows = S.projects.map((p) => {
      const sp = sch.projects[p.id];
      const next = S.tasks.filter((t) => t.project_id === p.id && t.status !== 'done').map((t) => ({ t, ...M.taskState(S, t, sch) })).sort((a, b) => a.start.localeCompare(b.start))[0];
      const open = S.reports.filter((r) => r.project_id === p.id && r.status === 'pending');
      return { p, sp, next, open };
    }).sort((a, b) => (b.open.length - a.open.length) || b.sp.slip_days - a.sp.slip_days || a.p.id.localeCompare(b.p.id));
    return `<div class="page-heading"><div><div class="eyebrow">Portfolio</div><h1>Projects</h1><p>Every project's next task, who owns it, and go-live against target. Open a project for its full timeline.</p></div></div>
      <section class="panel"><div class="table-wrap"><table class="data-table"><thead><tr><th>Project</th><th>Next task</th><th>Owner</th><th>Go-live</th><th>Reports</th></tr></thead><tbody>
      ${rows.map(({ p, sp, next, open }) => `<tr><td><a href="#project/${esc(p.id)}"><strong>${esc(p.id)}</strong></a><div class="subline">${esc(p.name)}</div></td>
        <td>${next ? esc(next.t.name) + `<div class="subline">${fmt(next.start)} · ${STATE[next.state][0]}</div>` : 'All done'}</td><td>${next ? esc(M.ownerName(S, next.t.owner_id)) : ''}</td>
        <td>${fmt(sp.go_live)}<div class="subline">${sp.slip_days > 0 ? `<span class="badge red">+${sp.slip_days} days</span>` : '<span class="badge green">On target</span>'}</div></td>
        <td>${open.length ? `<a href="#approvals"><span class="badge ${open.some((r) => r.no_resource || r.urgency <= 2) ? 'red' : 'gold'}">${open.length} waiting</span></a>` : ''}</td></tr>`).join('')}
      </tbody></table></div></section>`;
  }

  function activityHTML() {
    const log = S.log.slice().reverse();
    return `<div class="page-heading"><div><div class="eyebrow">Audit</div><h1>Activity</h1><p>Every update from contractors and the PM, with the projects whose dates moved.</p></div></div>
      <section class="panel"><div class="panel-body" style="padding-top:22px">${log.length ? `<div class="timeline">${log.map((l) => `<div class="timeline-item"><h3>${esc(l.text)}</h3><div class="timeline-meta">${fmt(l.at)} · ${esc(l.by)}${l.projects && l.projects.length ? ' · dates moved on ' + l.projects.map((id) => `<a href="#project/${esc(id)}">${esc(id)}</a>`).join(', ') : ''}</div></div>`).join('')}</div>` : empty('clock', 'No activity yet', '')}</div></section>`;
  }

  // ---------------- Actions ----------------
  async function markDone(taskId) {
    const before = M.schedule(S).projects[M.task(S, taskId).project_id].go_live;
    let r;
    try { r = M.completeTask(S, taskId, me.id); } catch (e) { toast(e.message, true); return; }
    if (!(await save(r.state))) return;
    const pid = M.task(S, taskId).project_id, after = M.schedule(S).projects[pid].go_live;
    toast(`Marked done. ${pid} timeline and the PM are updated${after !== before ? `; go-live ${fmt(before)} → ${fmt(after)}` : ''}.`);
    render();
  }

  function checkResources() {
    const d = draft;
    try { d.options = M.searchResources(S, d.task_id, resourceReq(d)); } catch (e) { toast(e.message, true); return; }
    d.checkedKey = reqKey(d);
    d.preferred = d.options[0] ? d.options[0].id : null;
    render();
  }

  async function submitReport() {
    const d = draft;
    if (!d.details.trim()) return toast('Describe the problem first.', true);
    if (!d.urgency) return toast('Pick an urgency level (1 is most urgent).', true);
    if (d.needResource == null) return toast('Say whether you need another company to step in.', true);
    if (d.needResource && (!d.options || d.checkedKey !== reqKey(d))) checkResources();
    const t = M.task(S, d.task_id), p = M.project(S, t.project_id), sch = M.schedule(S);
    const resource = d.needResource ? resourceReq(d) : null;
    const options = d.needResource ? d.options : [];
    d.busy = true; render();
    const payload = {
      project: { id: p.id, name: p.name, city: p.city, state: p.state, go_live: sch.projects[p.id].go_live, target_go_live: p.target_go_live, delay_cost_usd_per_day: p.cost_of_delay_usd_per_day },
      task: { name: t.name, scheduled: [sch.tasks[t.id].start, sch.tasks[t.id].finish] }, contractor: myCompany().name, urgency: `${d.urgency} (${URGENCY[d.urgency][0]}; 1 is most urgent)`,
      resource_request: resource && { ...resource, trade: DB.TRADES[resource.trade].label },
      options: options.map((o) => ({ company: o.company, start: o.start, go_live: o.go_live, go_live_change_days: o.go_live_change_days, cost_usd: o.cost_usd, distance_mi: o.distance_mi })),
      no_resource_found: !!resource && !options.length, go_live: sch.projects[p.id].go_live, details: d.details, photos: d.photos,
    };
    let summary;
    try { summary = await api('POST', '/api/summarize', payload); } catch (e) { summary = { source: 'error', detail: e.message }; }
    if (summary.source !== 'ai') {
      const pseudo = { by_name: myCompany().name, task_id: t.id, project_id: p.id, urgency: d.urgency, details: d.details.trim(), resource, options, no_resource: !!resource && !options.length };
      summary = { source: 'rule', text: M.ruleSummary(S, pseudo), detail: summary.detail };
    }
    let r;
    try { r = M.fileReport(S, { task_id: t.id, by: me.id, details: d.details, photos: d.photos, urgency: d.urgency, resource, preferred_option_id: d.preferred, summary }); }
    catch (e) { d.busy = false; render(); return toast(e.message, true); }
    if (!(await save(r.state))) { d.busy = false; render(); return; }
    draft = null;
    toast(r.result.no_resource ? `Sent ${r.result.id} to the PM as URGENT: no available company was found.` : `Sent ${r.result.id} to the PM${summary.source === 'ai' ? ' with an AI summary' : ''}.`);
    go('reports');
  }

  async function addPhotos(files) {
    const d = draft;
    const list = [...files].slice(0, Math.max(0, 6 - d.photos.length));
    d.uploading += list.length; render();
    for (const f of list) {
      try { const url = (await api('POST', '/api/photo', { data_url: await shrink(f) })).url; d.photos.push(url); }
      catch (e) { toast(`Couldn't add ${f.name}: ${e.message}`, true); }
      d.uploading--; render();
    }
  }
  function shrink(file) { // longest side 1280 px, JPEG
    return new Promise((resolve, reject) => {
      const img = new Image(), url = URL.createObjectURL(file);
      img.onload = () => { const k = Math.min(1, 1280 / Math.max(img.width, img.height)); const c = document.createElement('canvas'); c.width = Math.round(img.width * k); c.height = Math.round(img.height * k); c.getContext('2d').drawImage(img, 0, 0, c.width, c.height); URL.revokeObjectURL(url); resolve(c.toDataURL('image/jpeg', 0.82)); };
      img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('not an image')); };
      img.src = url;
    });
  }

  async function pmApprove(rid, oid) {
    const pid = S.reports.find((r) => r.id === rid).project_id, before = M.schedule(S).projects[pid].go_live;
    let r;
    try { r = M.approve(S, rid, oid, DB.PM.name, ui.pmNotes[rid]); } catch (e) { toast(e.message, true); return; }
    if (!(await save(r.state))) return;
    const after = M.schedule(S).projects[pid].go_live, o = r.result.decision.option;
    toast(`Approved ${o.company} from ${fmt(o.start)}${r.result.decision.changed ? ' (date updated since the report)' : ''}. It's on their dashboard; ${r.moved.length} task date(s) moved; go-live ${before === after ? 'unchanged' : fmt(before) + ' → ' + fmt(after)}.`);
    render();
  }
  async function pmDecline(rid) {
    let r;
    try { r = M.decline(S, rid, DB.PM.name, ui.pmNotes[rid]); } catch (e) { toast(e.message, true); return; }
    if (await save(r.state)) { toast(`${rid} ${r.result.status}. The contractor has been notified.`); render(); }
  }

  // ---------------- Events ----------------
  document.addEventListener('click', (e) => {
    const nav = e.target.closest('[data-go]');
    if (nav) { go(nav.dataset.go); return; }
    const b = e.target.closest('[data-act]');
    if (!b || b.tagName === 'SELECT' || b.tagName === 'INPUT') return;
    const a = b.dataset.act;
    if (a === 'signout') { setSession(null); draft = null; location.hash = ''; render(); }
    else if (a === 'reset') { if (confirm('Reset the demo for everyone? All tasks, reports and approvals go back to the starting data.')) api('POST', '/api/reset').then(async (doc) => { V = doc.version; S = M.seed(CC, DB); draft = null; await save(S); toast('Demo reset'); go(isPM() ? 'approvals' : 'tasks'); }); }
    else if (a === 'done') markDone(b.dataset.id);
    else if (a === 'report') { draft = null; go('report/' + encodeURIComponent(b.dataset.id)); }
    else if (a === 'urgency') { draft.urgency = +b.dataset.u; render(); }
    else if (a === 'need') { draft.needResource = b.dataset.v === 'yes'; render(); }
    else if (a === 'check') checkResources();
    else if (a === 'rm-photo') { draft.photos.splice(+b.dataset.i, 1); render(); }
    else if (a === 'approve') pmApprove(b.dataset.r, b.dataset.o);
    else if (a === 'decline') pmDecline(b.dataset.r);
  });
  document.addEventListener('input', (e) => {
    const k = e.target.dataset.bind;
    if (k && draft) { draft[k] = e.target.value; if (e.target.tagName === 'SELECT') render(); }
    if (e.target.dataset.note) ui.pmNotes[e.target.dataset.note] = e.target.value;
  });
  document.addEventListener('change', (e) => {
    const a = e.target.dataset.act;
    if (a === 'photos') addPhotos(e.target.files);
    else if (a === 'prefer') { draft.preferred = e.target.value; render(); }
    else if (a === 'pick-account' && e.target.value) {
      const f = document.querySelector('[data-form=login]');
      f.email.value = e.target.value; f.password.value = DB.DEMO_PASSWORD;
    }
    else if (e.target.dataset.bind && e.target.type === 'date' || e.target.dataset.bind === 'days') render();
  });
  document.addEventListener('submit', (e) => {
    const f = e.target.dataset.form;
    if (!f) return;
    e.preventDefault();
    if (f === 'login') {
      const email = e.target.email.value.trim().toLowerCase(), pw = e.target.password.value;
      const c = S.companies.find((x) => x.email === email);
      const err = (m) => { document.getElementById('login-error').innerHTML = `<div class="notice error">${icon('alert')}<div><strong>${esc(m)}</strong></div></div>`; };
      if (pw !== DB.DEMO_PASSWORD) return err('Wrong email or password.');
      if (email === DB.PM.email) setSession({ kind: 'pm', id: 'PM' });
      else if (c) setSession({ kind: 'company', id: c.id });
      else return err('Wrong email or password.');
      location.hash = isPM() ? 'approvals' : 'tasks';
      render();
    }
    if (f === 'report') submitReport();
  });

  boot();
})();
