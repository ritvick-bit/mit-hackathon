(function () {
  const EQ = window.EQORE, SEED = window.EQORE_SEED;
  const KEY = "eqore-cc-v1";
  const $ = (s, r) => (r || document).querySelector(s);
  const fmt = EQ.fmt;
  const money = (n) => "$" + Math.round(n).toLocaleString("en-US");
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const BAND = { red: "Red", amber: "Amber", green: "Green" };
  const COLOR = { red: "#d64545", amber: "#d99100", green: "#2a9d68" };

  let S = load(), EV;
  let tab = "cc", sel = null, pending = null, filter = "all", region = "MA";
  let custView = false, fieldJob = "JOB-004", draft = null, wi = { date: "", crew: "" };

  function load() {
    try { const raw = localStorage.getItem(KEY); if (raw) return JSON.parse(raw); } catch (e) {}
    return EQ.clone(SEED);
  }
  function save() { try { localStorage.setItem(KEY, JSON.stringify(S)); } catch (e) {} }
  const job = (id) => S.jobs.find((j) => j.job_id === id);
  const site = (id) => S.sites.find((x) => x.site_id === id);
  const crew = (id) => S.crews.find((c) => c.crew_id === id);
  const bandOf = (id) => EV.byJob[id].readiness;
  function toast(msg) { const t = $("#toast"); t.textContent = msg; t.classList.add("show"); clearTimeout(toast.h); toast.h = setTimeout(() => t.classList.remove("show"), 3200); }
  function logit(text) { S.log.push({ n: S.log.length + 1, text }); }

  function refresh() { EV = EQ.evaluate(S); save(); render(); }

  // ---------------- Render ----------------
  function render() {
    renderMetrics(); renderTabs();
    if (tab === "cc") { renderChips(); renderList(); updateMap(); }
    if (tab === "cal") renderCal();
    if (tab === "alerts") renderAlerts();
    if (tab === "field") renderField();
    $("#alert-count").textContent = EV.conflicts.length;
    renderDrawer();
  }

  function renderMetrics() {
    const m = EQ.metrics(S, EV);
    const wk = Object.keys(m.weeks).sort().map((w) => `${fmt(w)}: <b>${m.weeks[w]}</b>`).join(" &middot; ");
    $("#metrics").innerHTML = `
      <div class="tile"><div class="k">Installs in flight</div><div class="v">${m.total}</div>
        <div class="mini"><b><i class="dot red"></i>${m.counts.red}</b><b><i class="dot amber"></i>${m.counts.amber}</b><b><i class="dot green"></i>${m.counts.green}</b></div></div>
      <div class="tile"><div class="k">Dispatchable now</div><div class="v">${m.counts.green}/${m.total}</div><div class="s">${Math.round((m.counts.green / m.total) * 100)}% at readiness 100</div></div>
      <div class="tile"><div class="k">Installs per week</div><div class="v">${Object.keys(m.weeks).length ? "" : "0"}</div><div class="s">week of ${wk}</div></div>
      <div class="tile"><div class="k">Crew utilization</div><div class="v">${Math.round(m.util * 100)}%</div><div class="s">crew-days booked, Nov 9-22</div></div>
      <div class="tile"><div class="k">Permit to install</div><div class="v">${m.avgPermitDays.toFixed(1)} d</div><div class="s">avg days, approval to install</div></div>
      <div class="tile"><div class="k">Truck rolls held</div><div class="v">${m.counts.red}</div><div class="s">${money(m.redExposure)}/day in savings waiting</div></div>`;
    // the per-week tile: show numbers big
    const weeks = Object.keys(m.weeks).sort();
    $("#metrics").children[2].querySelector(".v").textContent = weeks.map((w) => m.weeks[w]).join(" / ");
  }

  function renderTabs() {
    document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === tab));
    document.querySelectorAll(".view").forEach((v) => v.classList.toggle("on", v.id === "view-" + tab));
  }

  function renderChips() {
    const m = EQ.metrics(S, EV).counts;
    const f = [["all", `All ${S.jobs.length}`], ["red", `Red ${m.red}`], ["amber", `Amber ${m.amber}`], ["green", `Green ${m.green}`]];
    $("#filters").innerHTML = f.map(([k, l]) => `<button class="chip ${filter === k ? "on" : ""}" data-act="filter" data-v="${k}">${l}</button>`).join("");
    $("#regions").innerHTML = [["MA", "Massachusetts"], ["CA", "California"], ["ALL", "All"]].map(([k, l]) => `<button class="chip ${region === k ? "on" : ""}" data-act="region" data-v="${k}">${l}</button>`).join("");
  }

  function sortedJobs() {
    const rank = { red: 0, amber: 1, green: 2 };
    return S.jobs.filter((j) => filter === "all" || bandOf(j.job_id) === filter)
      .sort((a, b) => rank[bandOf(a.job_id)] - rank[bandOf(b.job_id)] || a.install_date.localeCompare(b.install_date) || a.job_id.localeCompare(b.job_id));
  }

  function renderList() {
    const js = sortedJobs();
    $("#list-sub").textContent = `${js.length} shown, red first`;
    $("#job-list").innerHTML = js.map((j) => {
      const r = EV.byJob[j.job_id], st = site(j.site_id);
      return `<button class="row ${r.readiness}" data-act="open" data-id="${j.job_id}">
        <i class="dot ${r.readiness}"></i>
        <div><div class="t">${j.job_id} &middot; ${esc(st.facility_type)}, ${esc(st.city)}</div>
          <div class="sub">${j.power_kw} kW / ${j.energy_kwh} kWh &middot; ${esc(crew(j.crew_id).name)} &middot; ${st.utility}</div>
          <div class="blk">${r.blocker ? esc(r.blocker) : "Ready to dispatch"}</div></div>
        <div class="r"><div>${fmt(j.install_date)}</div><div>score ${r.score}</div></div></button>`;
    }).join("");
  }

  // ---------------- Map ----------------
  let map, markers = {};
  function initMap() {
    if (!window.L) { $("#map").innerHTML = '<div class="map-fallback">The map needs internet access (Leaflet and OpenStreetMap tiles). The job list still works.</div>'; return; }
    map = L.map("map").setView([42.25, -71.8], 8);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 18, attribution: "&copy; OpenStreetMap" }).addTo(map);
    S.jobs.forEach((j) => {
      const st = site(j.site_id);
      const m = L.circleMarker([st.lat, st.lng], { radius: 8 + j.power_kw / 60, weight: 2, color: "#fff", fillOpacity: 0.9 });
      m.on("click", () => openJob(j.job_id));
      m.bindTooltip("", { direction: "top" });
      markers[j.job_id] = m; m.addTo(map);
    });
    setRegion(region, true);
  }
  function setRegion(r, skipRender) {
    region = r;
    if (map) {
      if (r === "MA") map.setView([42.2, -71.7], 8);
      else if (r === "CA") map.setView([36.3, -120.2], 6);
      else map.setView([39.5, -96], 4);
    }
    if (!skipRender) render();
  }
  function updateMap() {
    if (!map) return;
    S.jobs.forEach((j) => {
      const r = EV.byJob[j.job_id], m = markers[j.job_id];
      const on = filter === "all" || filter === r.readiness;
      m.setStyle({ fillColor: COLOR[r.readiness], fillOpacity: on ? 0.9 : 0.12, opacity: on ? 1 : 0.2 });
      m.setTooltipContent(`<b>${j.job_id}</b> ${esc(site(j.site_id).city)} &middot; ${j.power_kw} kW<br>${esc(r.blocker || "Ready to dispatch")}`);
    });
    setTimeout(() => map.invalidateSize(), 0);
  }

  // ---------------- Calendar ----------------
  function renderCal() {
    const start = "2026-11-09", days = Array.from({ length: 15 }, (_, i) => EQ.addDays(start, i));
    const dn = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
    const wd = (d) => new Date(d + "T00:00:00Z").getUTCDay();
    let h = '<div class="gantt"><div class="hd">Crew</div>' + days.map((d) => `<div class="hd ${EQ.isWeekday(d) ? "" : "we"}">${dn[wd(d)]} ${fmt(d)}</div>`).join("");
    S.crews.forEach((c) => {
      h += `<div class="crew">${esc(c.name)}<small>${esc(c.base_city)}</small></div>`;
      days.forEach((d) => {
        const js = S.jobs.filter((j) => j.crew_id === c.crew_id && j.install_date === d);
        const cls = js.length > 1 ? "clash" : EQ.isWeekday(d) ? "" : "we-cell";
        h += `<div class="${cls}">` + js.map((j) => `<button class="gchip ${bandOf(j.job_id)}" data-act="open" data-id="${j.job_id}"><b>${j.job_id}</b>${esc(site(j.site_id).city)}</button>`).join("") + "</div>";
      });
    });
    h += "</div>";
    $("#view-cal").innerHTML = `<div class="card"><h2>Crew calendar</h2>
      <p class="muted">One row per crew. A red cell means the crew is double-booked that day. Click any block for the job. Weekends are shaded. Demo clock: ${fmt(S.today)}.</p>
      <div class="gantt-scroll">${h}</div></div>`;
  }

  // ---------------- Alerts ----------------
  const TYPE_LABEL = {
    crew_double_booked: "Crew double-booked", equipment_after_install: "Equipment after install", equipment_delayed: "Equipment delayed",
    no_delivery_buffer: "No delivery buffer", inspection_before_install: "Inspection before install", inspection_not_booked: "Inspection not booked",
    shutdown_not_requested: "Shutdown not approved", shutdown_not_approved: "Shutdown awaiting approval", permit_not_approved: "Permit not approved",
    utility_pto_pending: "Utility PTO pending", field_verification_failed: "Field check failed", pad_not_ready: "Pad not ready", tie_in_unconfirmed: "Tie-in unconfirmed",
    crew_skills_missing: "Crew skills missing", crew_wrong_region: "Crew wrong region",
  };
  function renderAlerts() {
    const cs = EV.conflicts;
    $("#view-alerts").innerHTML = `<div class="card"><h2>Alert inbox</h2>
      <p class="muted">${cs.filter((c) => c.severity === "hard").length} blocking, ${cs.filter((c) => c.severity !== "hard").length} at risk. Rules re-run on every schedule change.</p>
      ${cs.map((c) => {
        const cost = Math.max(...c.job_ids.map((id) => job(id).cost_of_delay_usd_per_day));
        return `<div class="alert ${c.severity}">
          <div class="top2"><span class="pill ${c.severity === "hard" ? "red" : "amber"}">${c.severity === "hard" ? "Blocking" : "At risk"}</span>
            <b>${TYPE_LABEL[c.type] || c.type}</b> ${c.job_ids.map((id) => `<button class="jobchip" data-act="open" data-id="${id}">${id}</button>`).join("")}
            <span class="muted" style="margin-left:auto">${money(cost)}/day at stake</span></div>
          <div>${esc(c.description)}</div>
          <div class="fix"><b>Suggested fix:</b> ${esc(c.suggested_fix)}</div></div>`;
      }).join("") || '<p class="muted">No alerts. Every install is dispatchable.</p>'}</div>`;
  }

  // ---------------- Drawer ----------------
  function openJob(id) { sel = id; pending = null; draft = null; custView = false; wi = { date: "", crew: "" }; renderDrawer(); }
  function closeJob() { sel = null; pending = null; draft = null; renderDrawer(); }

  function renderDrawer() {
    const d = $("#drawer");
    if (!sel) { d.classList.remove("open"); d.setAttribute("aria-hidden", "true"); return; }
    d.innerHTML = drawerHTML(sel);
    d.classList.add("open"); d.setAttribute("aria-hidden", "false");
  }

  function drawerHTML(id) {
    const j = job(id), st = site(j.site_id), r = EV.byJob[id], c = crew(j.crew_id);
    const head = `<div class="dr-head"><span class="id">${id}</span><span class="pill ${r.readiness}">${BAND[r.readiness]}</span>
      ${j.crew_held ? '<span class="pill hold">Crew held</span>' : ""}
      <button class="btn sec" style="margin-left:8px;padding:3px 9px" data-act="cust">${custView ? "Ops view" : "Customer view"}</button>
      <button class="x" data-act="close" aria-label="Close">&times;</button></div>`;
    if (custView) return head + `<div class="dr-body">${customerHTML(j, st, r, c)}</div>`;

    const sd = S.shutdowns.find((x) => x.job_id === id), ships = S.shipments.filter((x) => x.job_id === id), ins = S.inspections.filter((x) => x.job_id === id);
    const sug = EQ.suggest(S, id, EV);
    const advice = r.readiness === "green" ? "Dispatch" : r.readiness === "amber" ? "One or two items missing" : "Do not dispatch";

    return head + `<div class="dr-body">
      <div><div class="big">${esc(st.name)}</div>
        <div class="muted">${esc(st.city)}, ${st.state} &middot; ${st.utility} &middot; ${esc(st.facility_type)} &middot; bill ${money(st.monthly_bill_usd)}/mo &middot; peak ${st.peak_kw} kW</div>
        <div class="muted">${j.power_kw} kW / ${j.energy_kwh} kWh &middot; ${j.modules} cabinets &middot; ${j.pad_sqft} sq ft pad &middot; ${esc(j.tie_in)}</div></div>

      <div class="score ${r.readiness}"><div class="ring" style="--p:${r.score};--c:var(--${r.readiness})"><span>${r.score}</span></div>
        <div><b>${advice}</b><div>${r.blocker ? esc(r.blocker) : "All eight readiness checks pass."}</div></div></div>

      ${actionHTML(j, sug)}

      <div><h3>Schedule</h3><dl class="kv">
        <dt>Install</dt><dd>${fmt(j.install_date)}, ${j.install_window}</dd>
        <dt>Crew</dt><dd>${esc(c.name)} (${esc(c.base_city)}, ${c.size} people) &middot; ${c.skills.join(", ")}</dd>
        <dt>Status</dt><dd>${r.status.replace(/_/g, " ")}</dd>
        <dt>Cost of delay</dt><dd>${money(j.cost_of_delay_usd_per_day)}/day (${money(j.projected_savings_usd_per_month)}/month projected savings)</dd></dl></div>

      <div><h3>Readiness checks (100 = dispatch)</h3><table class="checks">
        ${r.checks.filter((x) => x.weight > 0 || x.status !== "ok").map((x) => `<tr><td class="${x.status === "ok" ? "ok-i" : x.status === "warn" ? "warn-i" : "bad-i"}">${x.status === "ok" ? "&#10003;" : x.status === "warn" ? "!" : "&#10007;"}</td>
          <td>${esc(x.label)}${x.message ? `<div class="muted">${esc(x.message)}</div>` : ""}</td><td class="w">${x.status === "ok" ? "" : "-" + (x.weight - x.earned)} / ${x.weight}</td></tr>`).join("")}</table></div>

      <div><h3>Logistics</h3><dl class="kv">
        <dt>Equipment</dt><dd>${ships.map((x) => `${esc(x.item)}: ${fmt(x.delivery_date)} (${x.status.replace("_", " ")})`).join("<br>")}</dd>
        <dt>Inspection</dt><dd>${ins.map((x) => `${x.type}: ${x.scheduled_date ? fmt(x.scheduled_date) : "no date"} (${x.status.replace("_", " ")})`).join("<br>")}</dd>
        <dt>Shutdown</dt><dd>${sd ? `${fmt(sd.date)} ${sd.start_time}-${sd.end_time}, ${sd.approved ? "approved" : sd.requested ? "requested, not approved" : "NOT approved"}<br><span class="muted">${esc(sd.notes)}</span>` : "none"}</dd>
        <dt>Permits</dt><dd>${Object.entries(j.permits).map(([k, v]) => `${k}: ${v}`).join(", ")}</dd>
        <dt>Utility</dt><dd>${j.utility_permission ? "PTO / approval to install granted" : "PTO pending"}</dd></dl></div>

      <div><h3>What if I move it?</h3>
        <div class="whatif">
          <label>New date<input type="date" id="wi-date" value="${wi.date || j.install_date}"></label>
          <label>Crew<select id="wi-crew">${S.crews.map((x) => `<option value="${x.crew_id}" ${(wi.crew || j.crew_id) === x.crew_id ? "selected" : ""}>${esc(x.name)}</option>`).join("")}</select></label>
          <button class="btn sec" data-act="whatif">Preview cascade</button></div></div>

      ${S.log.length ? `<div><h3>Change log</h3><div class="muted">${S.log.slice(-5).reverse().map((l) => `#${l.n} ${esc(l.text)}`).join("<br>")}</div></div>` : ""}
    </div>`;
  }

  function actionHTML(j, sug) {
    if (!sug) return `<div class="action"><b>Next action</b><div>Nothing to fix. Dispatch ${esc(crew(j.crew_id).name)} on ${fmt(j.install_date)}.</div></div>`;
    const id = j.job_id;
    let body = `<b>Next best action</b><div>${esc(sug.text)}</div>`, btns = "", cls = "action";
    if (sug.kind === "move") {
      body += `<ul>${sug.reasons.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`;
      btns = `<button class="btn" data-act="preview-sug">${sug.change.install_date ? "Reschedule" : "Apply"}</button>`;
    } else if (sug.kind === "cascade") {
      btns = sug.others.map((o) => `<button class="btn" data-act="open" data-id="${o}">Open ${o}</button>`).join("") +
        (sug.alt ? `<button class="btn sec" data-act="preview-alt">Preview reassign</button>` : "");
    } else if (sug.kind === "hold") {
      cls += " warn";
      btns = `<button class="btn danger" data-act="draft-fac">Message facility contact</button>`;
      if (draft === "fac") {
        const st = site(j.site_id), sd = S.shutdowns.find((x) => x.job_id === id);
        body += `<div class="draft">To: ${esc(st.contact)}, ${esc(st.name)}\nSubject: Shutdown approval needed for ${fmt(sd.date)}\n\nHi, we are ready to install your battery system on ${fmt(j.install_date)} (${j.install_window}). We need a short ${sd.start_time}-${sd.end_time} shutdown of your main service to make the tie-in. We cannot start without your approval. Can you confirm the window works for production? We are holding ${esc(crew(j.crew_id).name)} until we hear back.\n\nThanks, EQORE Deployments (demo message)</div>`;
        btns = `<button class="btn" data-act="send-fac">Send and hold crew (demo)</button><button class="btn sec" data-act="draft-fac">Hide draft</button>`;
      }
    } else if (sug.kind === "approve_shutdown") {
      btns = `<button class="btn" data-act="approve-fac">Mark facility approved (demo)</button>`;
    } else if (sug.kind === "field") {
      btns = `<button class="btn" data-act="go-field">Open field checklist</button>`;
    }
    let pv = "";
    if (pending && pending.jobId === id) {
      const p = pending.p, ch = pending.change;
      pv = `<div class="diff"><b>Impact preview</b>
        ${ch.install_date ? `<div>${esc(j.job_id)}: ${fmt(j.install_date)} <span class="arrow">&rarr;</span> ${fmt(ch.install_date)}${ch.crew_id && ch.crew_id !== j.crew_id ? `, ${esc(crew(j.crew_id).name)} <span class="arrow">&rarr;</span> ${esc(crew(ch.crew_id).name)}` : ""}</div>` : ""}
        ${p.diff.map((d) => `<div><b>${d.job_id}</b> <span class="pill ${d.from}">${d.from}</span> <span class="arrow">&rarr;</span> <span class="pill ${d.to}">${d.to}</span> <span class="muted">${esc(d.after || "ready")}</span></div>`).join("") || "<div>No other readiness changes.</div>"}
        ${p.diff.some((d) => d.job_id !== id && (d.to === "red" || (d.from === "green" && d.to !== "green"))) ? '<div class="bad-i"><b>Warning:</b> this move breaks another job that shares the crew or slot.</div>' : ""}
        <div>Cost of delay: <b>${p.delay_days ? `${p.delay_days} day${p.delay_days > 1 ? "s" : ""} &times; ${money(j.cost_of_delay_usd_per_day)} = ${money(p.cost)}` : "none"}</b></div></div>`;
      btns = `<button class="btn" data-act="apply">Apply</button><button class="btn sec" data-act="cancel">Cancel</button>`;
    }
    return `<div class="${cls}">${body}${pv}<div class="btns">${btns}</div></div>`;
  }

  function customerHTML(j, st, r, c) {
    const sd = S.shutdowns.find((x) => x.job_id === j.job_id);
    const ships = S.shipments.filter((x) => x.job_id === j.job_id);
    const permitsOk = Object.values(j.permits).every((v) => v === "approved");
    const step = (ok, text, sub) => `<li><span class="ic ${ok ? "ok-i" : "warn-i"}">${ok ? "&#10003;" : "&#9679;"}</span><div>${text}${sub ? `<div class="muted">${sub}</div>` : ""}</div></li>`;
    return `<div class="cust"><div><h4>Your battery install, ${esc(st.name)}</h4>
      <div class="muted">Customer view &middot; one point of contact: EQORE Deployments (demo)</div></div>
      <div class="big">${r.readiness === "green" ? `On track for ${fmt(j.install_date)}` : `We are working to confirm ${fmt(j.install_date)}`}</div>
      <ul class="steps">
        ${step(permitsOk, "Permits", permitsOk ? "All approved" : "One permit in review with the city")}
        ${step(ships.every((x) => x.delivery_date < j.install_date && x.status !== "delayed"), "Equipment", ships.map((x) => `${esc(x.item)} due ${fmt(x.delivery_date)}`).join(", "))}
        ${step(sd && sd.approved, "Short power shutdown", sd ? `${sd.start_time}-${sd.end_time} on ${fmt(sd.date)}. ${sd.approved ? "You approved this window." : "We need your OK on this window. Please reply to your EQORE contact."}` : "")}
        ${step(j.utility_permission, "Utility sign-off", j.utility_permission ? "Complete" : `Waiting on ${st.utility}`)}
        ${step(false, "Install day", `${fmt(j.install_date)}, ${j.install_window}. ${esc(c.name)} (${c.size} people) will be on site. Your facility keeps running except for the short shutdown.`)}
        ${step(false, "Inspection and commissioning", "We test the system and confirm it performs as designed before handoff.")}
      </ul></div>`;
  }

  // ---------------- Field crew ----------------
  function fieldState(id) { S.field[id] = S.field[id] || { items: {}, signed: false }; return S.field[id]; }
  function renderField() {
    const jobs = S.jobs.filter((j) => j.status !== "done").sort((a, b) => a.install_date.localeCompare(b.install_date));
    const f = fieldState(fieldJob), j = job(fieldJob);
    const items = EQ.FIELD_ITEMS;
    const allPass = items.every((it) => f.items[it.key] && f.items[it.key].result === "pass");
    const anyFail = items.find((it) => f.items[it.key] && f.items[it.key].result === "fail");
    $("#view-field").innerHTML = `<div class="phone"><div class="card"><h2>Field verification before energization</h2>
      <p class="muted">One tap per item, with photos. Saved on this device, so it works with no signal. A failed item blocks energization and shows up in the command center as a blocked install.</p>
      <div style="margin-top:10px"><select id="field-job" style="width:100%">${jobs.map((x) => `<option value="${x.job_id}" ${x.job_id === fieldJob ? "selected" : ""}>${x.job_id} &middot; ${esc(site(x.site_id).city)} &middot; ${fmt(x.install_date)}</option>`).join("")}</select></div></div>
      ${items.map((it) => {
        const s = f.items[it.key] || {};
        return `<div class="fi ${s.result || ""}"><div class="lbl">${esc(it.label)}</div>
          <div class="acts"><button class="btn" data-act="fpass" data-k="${it.key}">Pass</button><button class="btn danger" data-act="ffail" data-k="${it.key}">Fail</button>
            <label class="btn sec" style="text-align:center">Photo<input type="file" accept="image/*" capture="environment" hidden data-photo="${it.key}"></label></div>
          ${s.result === "fail" ? `<input style="width:100%;margin-top:8px" placeholder="What is wrong?" value="${esc(s.note || "")}" data-note="${it.key}">` : ""}
          ${s.photos && s.photos.length ? `<div class="thumbs">${s.photos.map((p) => `<img src="${p}" alt="Field photo">`).join("")}</div>` : ""}</div>`;
      }).join("")}
      <div class="fi ${f.signed ? "pass" : ""}"><div class="lbl">Sign-off before energization</div>
        <div class="acts"><button class="btn" data-act="fsign" ${allPass && !f.signed ? "" : "disabled"}>${f.signed ? "Signed off" : "Sign off"}</button></div></div>
      ${anyFail ? `<div class="banner red">Energization blocked: ${esc(anyFail.label)} failed. ${j.job_id} is now a blocked install in the command center. <button class="btn sec" data-act="open" data-id="${j.job_id}" style="margin-left:6px">Open job</button></div>` : ""}
      ${f.signed ? `<div class="banner green">Signed off. ${j.job_id} moved to commissioning.</div>` : ""}</div>`;
  }

  function resizePhoto(file, cb) {
    const img = new Image(), url = URL.createObjectURL(file);
    img.onload = () => {
      const s = 240 / Math.max(img.width, img.height, 240), cv = document.createElement("canvas");
      cv.width = Math.round(img.width * s); cv.height = Math.round(img.height * s);
      cv.getContext("2d").drawImage(img, 0, 0, cv.width, cv.height);
      URL.revokeObjectURL(url); cb(cv.toDataURL("image/jpeg", 0.7));
    };
    img.src = url;
  }

  // ---------------- Events ----------------
  document.addEventListener("click", (e) => {
    const t = e.target.closest("[data-act]"); if (!t) return;
    const a = t.dataset.act, id = sel;
    switch (a) {
      case "tab": tab = t.dataset.tab; render(); if (tab === "cc" && map) setTimeout(() => map.invalidateSize(), 50); break;
      case "filter": filter = t.dataset.v; render(); break;
      case "region": setRegion(t.dataset.v); break;
      case "open": if (tab === "field" && t.closest("#view-field")) { /* stay on field tab */ } openJob(t.dataset.id); break;
      case "close": closeJob(); break;
      case "cust": custView = !custView; renderDrawer(); break;
      case "reset": try { localStorage.removeItem(KEY); } catch (er) {} S = EQ.clone(SEED); sel = null; pending = null; refresh(); toast("Demo reset"); break;
      case "preview-sug": { const sg = EQ.suggest(S, id, EV); pending = { jobId: id, change: sg.change, p: EQ.preview(S, id, sg.change), label: sg.text }; renderDrawer(); break; }
      case "preview-alt": { const sg = EQ.suggest(S, id, EV); pending = { jobId: id, change: sg.alt.change, p: EQ.preview(S, id, sg.alt.change), label: sg.alt.text }; renderDrawer(); break; }
      case "whatif": {
        wi = { date: $("#wi-date").value, crew: $("#wi-crew").value };
        const j = job(id), ch = { install_date: wi.date, crew_id: wi.crew, shutdown_date: wi.date };
        pending = { jobId: id, change: ch, p: EQ.preview(S, id, ch), label: "Manual move" }; renderDrawer(); break;
      }
      case "cancel": pending = null; renderDrawer(); break;
      case "apply": {
        const j = job(id), before = `${fmt(j.install_date)} ${crew(j.crew_id).name}`;
        EQ.applyChange(S, id, pending.change);
        logit(`${id}: ${before} -> ${fmt(j.install_date)} ${crew(j.crew_id).name}${pending.p.cost ? ` (delay cost ${money(pending.p.cost)})` : ""}`);
        const fixed = pending.p.diff.filter((d) => d.to === "green" && d.job_id !== id).map((d) => d.job_id);
        pending = null; refresh();
        toast(`${id} is now ${bandOf(id)}${fixed.length ? `. Also cleared ${fixed.join(", ")}` : ""}`); break;
      }
      case "draft-fac": draft = draft === "fac" ? null : "fac"; renderDrawer(); break;
      case "send-fac": EQ.applyChange(S, id, { shutdown_requested: true }); logit(`${id}: asked facility to approve shutdown, ${crew(job(id).crew_id).name} held`); draft = null; refresh(); toast("Message sent. Crew held, not dispatched."); break;
      case "approve-fac": EQ.applyChange(S, id, { shutdown_approved: true }); logit(`${id}: facility approved shutdown window`); refresh(); toast(`Facility approved. ${id} is now ${bandOf(id)}`); break;
      case "go-field": fieldJob = id; tab = "field"; closeJob(); render(); break;
      case "fpass": case "ffail": {
        const f = fieldState(fieldJob), k = t.dataset.k, it = f.items[k] || (f.items[k] = { photos: [] });
        it.result = a === "fpass" ? "pass" : "fail"; f.signed = false;
        if (job(fieldJob).status === "commissioning") job(fieldJob).status = "installing";
        if (a === "ffail") logit(`${fieldJob}: field check failed (${k}), energization blocked`);
        refresh(); break;
      }
      case "fsign": { const f = fieldState(fieldJob); f.signed = true; job(fieldJob).status = "commissioning"; logit(`${fieldJob}: field verification signed off, moved to commissioning`); refresh(); break; }
    }
  });
  document.addEventListener("change", (e) => {
    if (e.target.id === "field-job") { fieldJob = e.target.value; renderField(); }
    if (e.target.dataset.photo) {
      const f = fieldState(fieldJob), k = e.target.dataset.photo, file = e.target.files[0]; if (!file) return;
      resizePhoto(file, (url) => { const it = f.items[k] || (f.items[k] = { photos: [] }); (it.photos = it.photos || []).push(url); save(); renderField(); });
    }
    if (e.target.dataset.note) { const f = fieldState(fieldJob); f.items[e.target.dataset.note].note = e.target.value; save(); }
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && sel) closeJob(); });

  // ---------------- Boot ----------------
  EV = EQ.evaluate(S);
  initMap();
  render();
  window.__eqore = { get state() { return S; }, get ev() { return EV; } };
})();
