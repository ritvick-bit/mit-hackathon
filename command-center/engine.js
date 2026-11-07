// EQORE Install Command Center: readiness score, conflict detection, reschedule suggestions.
// Pure functions over a plain state object (see data.js). Works in the browser and in Node.
(function (root) {
  const DAY = 86400000;
  const parse = (s) => new Date(s + "T00:00:00Z");
  const iso = (d) => d.toISOString().slice(0, 10);
  const addDays = (s, n) => iso(new Date(parse(s).getTime() + n * DAY));
  const diffDays = (a, b) => Math.round((parse(a) - parse(b)) / DAY);
  const dow = (s) => parse(s).getUTCDay();
  const isWeekday = (s) => dow(s) !== 0 && dow(s) !== 6;
  const nextWeekday = (s) => { while (!isWeekday(s)) s = addDays(s, 1); return s; };
  const fmt = (s) => parse(s).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
  const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
  const clone = (o) => JSON.parse(JSON.stringify(o));
  const crewState = (c) => c.base_city.split(", ")[1];

  const FIELD_ITEMS = [
    { key: "build", label: "Build matches approved design" },
    { key: "terminations", label: "Terminations checked" },
    { key: "conductors", label: "Conductor sizing checked" },
    { key: "grounding", label: "Grounding checked" },
    { key: "ct_metering", label: "CT and metering orientation checked" },
    { key: "protection", label: "Protection settings checked" },
  ];

  function index(s) {
    const ix = { site: {}, crew: {}, job: {}, ship: {}, insp: {}, shut: {} };
    s.sites.forEach((x) => (ix.site[x.site_id] = x));
    s.crews.forEach((x) => (ix.crew[x.crew_id] = x));
    s.jobs.forEach((x) => (ix.job[x.job_id] = x));
    s.shipments.forEach((x) => (ix.ship[x.job_id] = ix.ship[x.job_id] || []).push(x));
    s.inspections.forEach((x) => (ix.insp[x.job_id] = ix.insp[x.job_id] || []).push(x));
    s.shutdowns.forEach((x) => (ix.shut[x.job_id] = x));
    return ix;
  }

  const requiredSkills = (j) => (j.power_kw >= 300 ? ["480V", "NFPA 855"] : ["480V"]);

  // ---------- Readiness score ----------
  function evalJob(j, ix, s) {
    const site = ix.site[j.site_id], crew = ix.crew[j.crew_id];
    const checks = [];
    const add = (o) => checks.push(Object.assign({ status: "ok", message: "", hard: false, earned: null }, o,
      { earned: o.earned != null ? o.earned : (o.status && o.status !== "ok" ? 0 : o.weight) }));

    // 1. Pad ready (15)
    add(j.pad_ready
      ? { key: "pad", label: "Pad ready", weight: 15 }
      : { key: "pad", label: "Pad ready", weight: 15, status: "fail", type: "pad_not_ready", message: "Concrete pad is not ready" });

    // 2. Equipment (20)
    const sh = ix.ship[j.job_id] || [];
    const EQL = "Equipment delivered / arriving on or before install";
    const late = sh.find((x) => x.delivery_date > j.install_date);
    const delayed = sh.find((x) => x.status === "delayed");
    const tight = sh.find((x) => x.delivery_date === j.install_date);
    if (late) add({ key: "equipment", label: EQL, weight: 20, status: "fail", hard: true, type: "equipment_after_install",
      message: `Equipment arrives ${fmt(late.delivery_date)}, install is ${fmt(j.install_date)}` });
    else if (delayed) add({ key: "equipment", label: EQL, weight: 20, status: "fail", hard: true, type: "equipment_delayed",
      message: `Delivery of ${delayed.item} is delayed` });
    else if (tight) add({ key: "equipment", label: EQL, weight: 20, status: "warn", earned: 10, type: "no_delivery_buffer",
      message: `Equipment delivery ${fmt(tight.delivery_date)}, install ${fmt(j.install_date)}, no buffer` });
    else add({ key: "equipment", label: EQL, weight: 20 });

    // 3. Electrical tie-in (15)
    add(j.tie_in_confirmed
      ? { key: "tiein", label: "Electrical tie-in confirmed", weight: 15 }
      : { key: "tiein", label: "Electrical tie-in confirmed", weight: 15, status: "fail", type: "tie_in_unconfirmed", message: "Electrical tie-in not confirmed" });

    // 4. Permits (15)
    const badP = Object.entries(j.permits).filter(([, v]) => v !== "approved");
    const PL = "Permits approved (building, electrical, fire)";
    if (!badP.length) add({ key: "permits", label: PL, weight: 15 });
    else {
      const [k, v] = badP[0];
      add({ key: "permits", label: PL, weight: 15, status: "fail", type: "permit_not_approved",
        atRisk: diffDays(j.install_date, s.today) <= 7,
        message: v === "revision" ? `Permit revision, round ${j.permit_round || 2}` : `${cap(k)} permit not approved` });
    }

    // 5. Utility PTO / approval to install (10)
    add(j.utility_permission
      ? { key: "utility", label: "Utility permission / approval to install", weight: 10 }
      : { key: "utility", label: "Utility permission / approval to install", weight: 10, status: "fail", type: "utility_pto_pending", message: `Utility PTO pending (${site.utility})` });

    // 6. Crew (10)
    const CL = "Crew available with right skills";
    const others = s.jobs.filter((o) => o.job_id !== j.job_id && o.crew_id === j.crew_id && o.install_date === j.install_date && o.status !== "done");
    const missing = requiredSkills(j).filter((k) => !crew.skills.includes(k));
    if (others.length) {
      const cities = [...new Set([j, ...others].map((o) => ix.site[o.site_id].city))].sort();
      const where = cities.length === 1 ? `on ${others.length + 1} jobs in ${cities[0]}` : `in ${cities.length === 2 ? cities.join(" and ") : cities.slice(0, -1).join(", ") + " and " + cities.slice(-1)}`;
      add({ key: "crew", label: CL, weight: 10, status: "fail", hard: true, type: "crew_double_booked",
        others: others.map((o) => o.job_id), message: `${crew.name} is booked ${where} on ${fmt(j.install_date)}` });
    } else if (missing.length) {
      add({ key: "crew", label: CL, weight: 10, status: "fail", hard: true, type: "crew_skills_missing", message: `${crew.name} lacks ${missing.join(", ")}` });
    } else if (crewState(crew) !== site.state) {
      add({ key: "crew", label: CL, weight: 10, status: "fail", hard: true, type: "crew_wrong_region", message: `${crew.name} is based in ${crewState(crew)}, site is in ${site.state}` });
    } else add({ key: "crew", label: CL, weight: 10 });

    // 7. Inspection (5)
    const ins = ix.insp[j.job_id] || [];
    const IL = "Inspection booked on/after install";
    const isBooked = (i) => i.status === "booked" || i.status === "passed";
    const nb = ins.find((i) => i.status === "not_booked");
    const early = ins.find((i) => isBooked(i) && i.scheduled_date < j.install_date);
    const good = ins.some((i) => isBooked(i) && i.scheduled_date >= j.install_date);
    if (nb) add({ key: "inspection", label: IL, weight: 5, status: "fail", type: "inspection_not_booked", message: `${cap(nb.type)} inspection not yet booked` });
    else if (early && !good) add({ key: "inspection", label: IL, weight: 5, status: "fail", type: "inspection_before_install",
      message: `Inspection booked ${fmt(early.scheduled_date)}, before install ${fmt(j.install_date)}, wrong order` });
    else if (!good) add({ key: "inspection", label: IL, weight: 5, status: "fail", type: "inspection_not_booked", message: "No inspection booked" });
    else add({ key: "inspection", label: IL, weight: 5 });

    // 8. Shutdown window (10)
    const sd = ix.shut[j.job_id];
    const SL = "Facility shutdown window approved";
    if (sd && sd.approved) add({ key: "shutdown", label: SL, weight: 10 });
    else if (sd && !sd.requested) add({ key: "shutdown", label: SL, weight: 10, status: "fail", hard: true, type: "shutdown_not_requested",
      message: "Shutdown window not approved by the facility, install cannot start" });
    else add({ key: "shutdown", label: SL, weight: 10, status: "fail", type: "shutdown_not_approved", message: "Shutdown window requested, not approved" });

    // Field verification (blocks energization, no weight)
    const f = s.field && s.field[j.job_id];
    if (f) {
      const bad = FIELD_ITEMS.find((it) => f.items[it.key] && f.items[it.key].result === "fail");
      if (bad) add({ key: "field", label: "Field verification", weight: 0, status: "fail", hard: true, type: "field_verification_failed",
        message: `Field check failed: ${bad.label}. Energization blocked` });
    }

    let score = 100 - checks.reduce((a, c) => a + (c.weight - c.earned), 0);
    const hard = checks.some((c) => c.hard);
    if (hard) score = Math.min(score, 69); // any hard blocker = do not dispatch
    const flagged = checks.filter((c) => c.status !== "ok").sort((a, b) => (b.hard - a.hard) || (b.weight - a.weight));
    const readiness = hard || score < 70 ? "red" : flagged.length ? "amber" : "green";
    return {
      job_id: j.job_id, checks, flagged, score, readiness, hard,
      blocker: flagged.length ? flagged[0].message : null,
      status: hard && !["installing", "commissioning", "done"].includes(j.status) ? "blocked" : j.status,
    };
  }

  function evaluate(s, noFix) {
    const ix = index(s);
    const byJob = {};
    s.jobs.forEach((j) => (byJob[j.job_id] = evalJob(j, ix, s)));
    const conflicts = [], seen = {};
    s.jobs.forEach((j) => byJob[j.job_id].flagged.forEach((c) => {
      let key, ids = [j.job_id];
      if (c.type === "crew_double_booked") { ids = [j.job_id, ...c.others].sort(); key = `crew:${j.crew_id}:${j.install_date}`; }
      else key = `${c.type}:${j.job_id}`;
      if (seen[key]) return;
      seen[key] = 1;
      conflicts.push({ conflict_id: "C-" + (conflicts.length + 1), type: c.type, severity: c.hard ? "hard" : "at_risk",
        job_ids: ids, job_id: j.job_id, description: c.message, weight: c.weight });
    }));
    conflicts.sort((a, b) => (a.severity === b.severity ? 0 : a.severity === "hard" ? -1 : 1) || a.job_id.localeCompare(b.job_id));
    if (!noFix) conflicts.forEach((c) => { const sg = suggest(s, c.job_id, { byJob }); c.suggested_fix = sg ? sg.text : ""; });
    return { byJob, conflicts };
  }

  // ---------- Reschedule suggestions ----------
  function inspectionSlot(s, from) {
    let d = nextWeekday(from);
    for (let i = 0; i < 30; i++) {
      const load = s.inspections.filter((x) => x.scheduled_date === d && x.status === "booked").length;
      if (load < 3) return d;
      d = nextWeekday(addDays(d, 1));
    }
    return d;
  }

  function eligibleCrews(j, ix, s) {
    const site = ix.site[j.site_id];
    const need = requiredSkills(j);
    return s.crews
      .filter((c) => crewState(c) === site.state && need.every((k) => c.skills.includes(k)))
      .sort((a, b) => (b.crew_id === j.crew_id) - (a.crew_id === j.crew_id));
  }

  function findMove(s, j, ix, opts) {
    opts = opts || {};
    const sh = ix.ship[j.job_id] || [];
    const maxDel = sh.reduce((m, x) => (x.delivery_date > m ? x.delivery_date : m), "0000-00-00");
    let min = nextWeekday(addDays(s.today, 1));
    if (sh.length && addDays(maxDel, 1) > min) min = addDays(maxDel, 1);
    if (j.install_date > min) min = j.install_date;
    min = nextWeekday(min);
    const crews = eligibleCrews(j, ix, s).filter((c) => !(opts.excludeCrew && c.crew_id === opts.excludeCrew));
    for (let i = 0; i < 30; i++) {
      const d = nextWeekday(addDays(min, i));
      for (const c of crews) {
        const busy = s.jobs.some((o) => o.job_id !== j.job_id && o.crew_id === c.crew_id && o.install_date === d && o.status !== "done");
        if (busy) continue;
        const change = { install_date: d, crew_id: c.crew_id };
        const reasons = [];
        const delay = diffDays(d, j.install_date);
        if (sh.length) reasons.push(`Equipment arrives ${fmt(maxDel)}, ${diffDays(d, maxDel)} day${diffDays(d, maxDel) === 1 ? "" : "s"} before install`);
        reasons.push(c.crew_id === j.crew_id ? `${c.name} is free that day and has the skills` : `${c.name} (${c.base_city}) is free that day and has the skills; reassigned from ${ix.crew[j.crew_id].name}`);
        const sd = ix.shut[j.job_id];
        if (sd) { change.shutdown_date = d; reasons.push(sd.approved ? `Shutdown window moves with the job (already approved; reconfirm with the facility)` : `Shutdown window moves with the job (still needs approval)`); }
        const insp = (ix.insp[j.job_id] || []).filter((x) => x.status === "booked" || x.status === "passed");
        if (insp.length && insp.every((x) => x.scheduled_date >= d)) reasons.push(`Inspection stays ${fmt(insp[0].scheduled_date)} (on/after install)`);
        else { change.inspection_date = inspectionSlot(s, addDays(d, 1)); reasons.push(`Inspection rebooked to ${fmt(change.inspection_date)} (open slot, after install)`); }
        return { kind: "move", change, delay_days: Math.max(0, delay), cost: Math.max(0, delay) * j.cost_of_delay_usd_per_day, reasons,
          text: `Move ${j.job_id} to ${fmt(d)} with ${c.name}` + (delay > 0 ? ` (${delay} day${delay === 1 ? "" : "s"} later)` : delay < 0 ? "" : ` (same day, different crew)`) };
      }
    }
    return null;
  }

  function suggest(s, jobId, ev) {
    const ix = index(s), j = ix.job[jobId];
    ev = ev || evaluate(s, true);
    const top = ev.byJob[jobId].flagged[0];
    if (!top) return null;
    const crew = ix.crew[j.crew_id], site = ix.site[j.site_id];
    switch (top.type) {
      case "equipment_after_install": case "equipment_delayed": case "no_delivery_buffer":
        return findMove(s, j, ix) || { kind: "chase", text: "No free crew and date found in the next 30 days. Escalate to the deployment lead." };
      case "crew_double_booked": case "crew_skills_missing": case "crew_wrong_region": {
        const others = top.others || [];
        const blockedOthers = others.filter((id) => ev.byJob[id].checks.some((c) => c.hard && c.type !== "crew_double_booked"));
        const alt = findMove(s, j, ix, { excludeCrew: top.type === "crew_double_booked" ? undefined : j.crew_id });
        if (blockedOthers.length && top.type === "crew_double_booked")
          return { kind: "cascade", others: blockedOthers, alt, text: `${j.job_id} clears on its own when ${blockedOthers.join(", ")} moves, because it has its own blocker${alt ? `. Or reassign to ${ix.crew[alt.change.crew_id].name} on ${fmt(alt.change.install_date)}` : ""}` };
        return alt || { kind: "chase", text: "No free crew found. Escalate." };
      }
      case "shutdown_not_requested":
        return { kind: "hold", text: `Do not reschedule the crew yet. Message the facility contact for shutdown approval and hold ${crew.name}` };
      case "shutdown_not_approved": {
        const sd = ix.shut[jobId];
        return { kind: "approve_shutdown", text: `Get facility approval for the ${fmt(sd.date)} ${sd.start_time}-${sd.end_time} window, then dispatch` };
      }
      case "inspection_before_install": {
        const slot = inspectionSlot(s, addDays(j.install_date, 1));
        return { kind: "move", change: { inspection_date: slot }, delay_days: 0, cost: 0, reasons: [`${fmt(slot)} is the next open slot after install ${fmt(j.install_date)}`],
          text: `Rebook the inspection to ${fmt(slot)} (after install ${fmt(j.install_date)})` };
      }
      case "inspection_not_booked": {
        const slot = inspectionSlot(s, addDays(j.install_date, 1));
        const t = (ix.insp[jobId] || []).find((x) => x.status === "not_booked");
        return { kind: "move", change: { inspection_date: slot }, delay_days: 0, cost: 0, reasons: [`${fmt(slot)} is the next open slot on/after install`],
          text: `Book the ${t ? t.type + " " : ""}inspection for ${fmt(slot)} (open slot, after install)` };
      }
      case "permit_not_approved":
        return { kind: "chase", text: `Chase the AHJ for permit approval. Hold ${fmt(j.install_date)} and re-check by ${fmt(addDays(j.install_date, -3))}; if it slips, reschedule` };
      case "utility_pto_pending":
        return { kind: "chase", text: `Follow up with ${site.utility} on permission to operate before ${fmt(j.install_date)}` };
      case "field_verification_failed":
        return { kind: "field", text: "Fix the failed item on site, then re-verify in the Field crew tab" };
      default:
        return { kind: "chase", text: "Resolve the open item, then re-check readiness" };
    }
  }

  // ---------- Applying and previewing changes ----------
  function applyChange(s, jobId, ch) {
    const j = s.jobs.find((x) => x.job_id === jobId);
    if (ch.install_date) j.install_date = ch.install_date;
    if (ch.crew_id) j.crew_id = ch.crew_id;
    const sd = s.shutdowns.find((x) => x.job_id === jobId);
    if (sd && ch.shutdown_date) sd.date = ch.shutdown_date;
    if (sd && ch.shutdown_requested) { sd.requested = true; sd.notes = "Approval requested from facility contact, crew held"; j.crew_held = true; }
    if (sd && ch.shutdown_approved) { sd.requested = true; sd.approved = true; sd.notes = "Facility approved"; j.crew_held = false; }
    if (ch.inspection_date) {
      const list = s.inspections.filter((x) => x.job_id === jobId);
      const t = list.find((x) => x.status === "not_booked") || list.find((x) => x.scheduled_date && x.scheduled_date < j.install_date) || list[0];
      if (t) { t.scheduled_date = ch.inspection_date; t.status = "booked"; }
    }
  }

  function preview(s, jobId, ch) {
    const before = evaluate(s, true);
    const t = clone(s);
    applyChange(t, jobId, ch);
    const after = evaluate(t, true);
    const diff = [];
    s.jobs.forEach((j) => {
      const b = before.byJob[j.job_id], a = after.byJob[j.job_id];
      if (b.readiness !== a.readiness || b.blocker !== a.blocker)
        diff.push({ job_id: j.job_id, from: b.readiness, to: a.readiness, before: b.blocker, after: a.blocker });
    });
    const j = s.jobs.find((x) => x.job_id === jobId);
    const newDate = ch.install_date || j.install_date;
    const delay = Math.max(0, diffDays(newDate, j.install_date));
    return { diff, delay_days: delay, cost: delay * j.cost_of_delay_usd_per_day };
  }

  // ---------- Metrics ----------
  function metrics(s, ev) {
    const counts = { red: 0, amber: 0, green: 0 };
    s.jobs.forEach((j) => counts[ev.byJob[j.job_id].readiness]++);
    const weekStart = (d) => addDays(d, -((dow(d) + 6) % 7));
    const weeks = {};
    s.jobs.forEach((j) => { const w = weekStart(j.install_date); weeks[w] = (weeks[w] || 0) + 1; });
    const windowDays = 14, start = "2026-11-09";
    let booked = 0;
    s.jobs.forEach((j) => { if (j.install_date >= start && j.install_date < addDays(start, windowDays)) booked++; });
    const util = booked / (s.crews.length * windowDays);
    const pd = s.jobs.filter((j) => j.permit_approved_date).map((j) => diffDays(j.install_date, j.permit_approved_date));
    const exposure = s.jobs.filter((j) => ev.byJob[j.job_id].readiness !== "green").reduce((a, j) => a + j.cost_of_delay_usd_per_day, 0);
    const redExposure = s.jobs.filter((j) => ev.byJob[j.job_id].readiness === "red").reduce((a, j) => a + j.cost_of_delay_usd_per_day, 0);
    return { counts, weeks, util, avgPermitDays: pd.length ? pd.reduce((a, b) => a + b, 0) / pd.length : 0, exposure, redExposure, total: s.jobs.length };
  }

  const api = { evaluate, suggest, preview, applyChange, metrics, index, addDays, diffDays, nextWeekday, isWeekday, fmt, clone, FIELD_ITEMS, requiredSkills, crewState };
  root.EQORE = api;
  if (typeof module !== "undefined") module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
