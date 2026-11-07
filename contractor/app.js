(function () {
  const EQ = window.EQORE, SEED = window.EQORE_SEED, C = window.EQORE_CONTRACTOR;
  const KEY = "eqore-cc-v1"; // same record as the PM command center (same origin), so both views stay in sync
  const $ = (s, r) => (r || document).querySelector(s);
  const fmt = EQ.fmt;
  const money = (n) => "$" + Math.round(n).toLocaleString("en-US");
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const BAND = { red: "Red", amber: "Amber", green: "Green" };

  let S = load(), EV, PARTIES = C.parties(S);
  let party = pickParty(decodeURIComponent(location.hash.slice(1)));
  let filter = "open", draft = null; // draft: { item_id, type, date, note }

  function load() {
    try { const raw = localStorage.getItem(KEY); if (raw) return JSON.parse(raw); } catch (e) {}
    return EQ.clone(SEED);
  }
  function save() { try { localStorage.setItem(KEY, JSON.stringify(S)); } catch (e) {} }
  function pickParty(id) { return PARTIES.find((p) => p.id === id) || PARTIES[0]; }
  function toast(msg) { const t = $("#toast"); t.textContent = msg; t.classList.add("show"); clearTimeout(toast.h); toast.h = setTimeout(() => t.classList.remove("show"), 3200); }

  function refresh() { EV = EQ.evaluate(S, true); render(); }

  // ---------------- Render ----------------
  function render() {
    renderPicker();
    const items = C.obligations(S, party.id, EV);
    renderMetrics(items);
    renderItems(items);
    renderLog();
  }

  function renderPicker() {
    const groups = {};
    PARTIES.forEach((p) => {
      const n = C.summary(C.obligations(S, p.id, EV));
      (groups[p.group] = groups[p.group] || []).push(`<option value="${esc(p.id)}"${p.id === party.id ? " selected" : ""}>${esc(p.name)}${n.blocking ? ` (${n.blocking} holding up installs)` : n.open ? ` (${n.open} open)` : ""}</option>`);
    });
    $("#party").innerHTML = Object.entries(groups).map(([g, o]) => `<optgroup label="${esc(g)}">${o.join("")}</optgroup>`).join("");
  }

  function renderMetrics(items) {
    const m = C.summary(items);
    const tile = (k, v, s, cls) => `<div class="tile${cls ? " " + cls : ""}"><div class="k">${k}</div><div class="v">${v}</div><div class="s">${s}</div></div>`;
    $("#metrics").innerHTML =
      tile("Open items", m.open, "across all EQORE jobs") +
      tile("Holding up an install", m.blocking, m.blocking ? "the PM sees these as blockers" : "nothing waiting on you", m.blocking ? "ct-alert" : "") +
      tile("Delay cost riding on you", money(m.exposure) + "/day", "customer savings lost per day of slip") +
      tile("Done", m.done, "confirmed, delivered or approved");
  }

  function renderItems(items) {
    const shown = items.filter((i) => filter === "all" || (filter === "open" ? i.open : i.open && i.blocking));
    $("#list-title").textContent = `${party.name}: ${filter === "all" ? "all items" : filter === "open" ? "open items" : "items holding up an install"}`;
    document.querySelectorAll("#filters .chip").forEach((b) => b.classList.toggle("on", b.dataset.f === filter));
    if (!shown.length) { $("#items").innerHTML = `<p class="ct-empty">Nothing here. ${filter === "open" ? "You're all caught up." : ""}</p>`; return; }
    $("#items").innerHTML = shown.map(itemHTML).join("");
    const d = draft && $(`[data-draft]`);
    if (d) { const inp = $("input[type=date]", d) || $("input[name=note]", d); if (inp) inp.focus(); }
  }

  function itemHTML(i) {
    const days = EQ.diffDays(i.due, S.today);
    const when = days < 0 ? `${-days}d overdue` : days === 0 ? "today" : `in ${days}d`;
    const cls = !i.open ? "done" : i.hard ? "hard" : i.blocking ? "warn" : "";
    const acts = i.actions.map((t) => `<button class="ct-btn${t === "delay" || t === "fail" || t === "decline" || t === "revise" ? " ct-neg" : ""}" data-act="start" data-item="${esc(i.id)}" data-type="${t}">${esc(C.ACTION_LABEL[t])}</button>`).join("");
    return `<article class="ct-item ${cls}">
      <div class="ct-row">
        <div>
          <div class="ct-job"><b>${esc(i.job_id)}</b> &middot; ${esc(i.site)} <span class="pill ${i.readiness}" title="Job readiness on the PM board">${BAND[i.readiness]}</span></div>
          <div class="ct-title">${esc(i.title)}</div>
        </div>
        <div class="ct-due"><div>${fmt(i.due)}</div><div class="ct-muted">${i.open ? when : ""}</div></div>
      </div>
      <div class="ct-row ct-meta">
        <span class="ct-state">${esc(i.state)}</span>
        ${i.issue ? `<span class="ct-issue">${i.hard ? "Blocks install" : "At risk"}: ${esc(i.issue)} &middot; ${money(i.cost_per_day)}/day</span>` : ""}
      </div>
      ${acts ? `<div class="ct-acts">${acts}</div>` : ""}
      ${draft && draft.item_id === i.id ? draftHTML(i) : ""}
    </article>`;
  }

  function draftHTML(i) {
    const needDate = C.NEEDS_DATE[draft.type];
    let preview = "";
    if (!needDate || draft.date) {
      try {
        const r = C.impact(S, party.id, party.name, draft);
        const rows = r.changes.map((c) => `<li><b>${esc(c.job_id)}</b> <span class="pill ${c.from}">${BAND[c.from]}</span> &rarr; <span class="pill ${c.to}">${BAND[c.to]}</span> ${c.after ? esc(c.after) : "no blockers left"}</li>`).join("");
        const others = r.others.map((o) => `<li>${esc(o.party)}: <b>${esc(o.job_id)}</b> ${esc(o.issue)}</li>`).join("");
        preview = `<div class="ct-impact">
          <div class="ct-k">What the PM will see</div>
          ${rows ? `<ul>${rows}</ul>` : `<p class="ct-muted">No change to any job's readiness.</p>`}
          ${others ? `<div class="ct-k">New items for other parties</div><ul>${others}</ul>` : ""}
        </div>`;
      } catch (e) { preview = `<p class="ct-issue">${esc(e.message)}</p>`; }
    }
    return `<form class="ct-draft" data-draft>
      <div class="ct-k">${esc(C.ACTION_LABEL[draft.type])}: ${esc(i.job_id)}</div>
      <div class="ct-fields">
        ${needDate ? `<label>${draft.type === "delay" ? "New earliest date" : draft.type === "eta" ? "Expected date" : "Date"} <input type="date" name="date" value="${esc(draft.date || "")}" min="${S.today}" required></label>` : ""}
        <label class="ct-grow">Note to PM (optional) <input type="text" name="note" value="${esc(draft.note || "")}" maxlength="200" placeholder="e.g. truck held at port"></label>
      </div>
      ${preview}
      <div class="ct-acts"><button class="ct-btn ct-primary" type="submit"${needDate && !draft.date ? " disabled" : ""}>Send update</button><button class="ct-btn" type="button" data-act="cancel">Cancel</button></div>
    </form>`;
  }

  function renderLog() {
    const log = (S.log || []).slice(-12).reverse();
    $("#log").innerHTML = log.length ? log.map((l) => `<li>${esc(l.text)}</li>`).join("") : `<li class="ct-muted">No updates yet.</li>`;
  }

  // ---------------- Events ----------------
  $("#party").addEventListener("change", (e) => { party = pickParty(e.target.value); draft = null; history.replaceState(null, "", "#" + encodeURIComponent(party.id)); refresh(); });

  document.addEventListener("click", (e) => {
    const b = e.target.closest("[data-act]");
    if (!b) return;
    switch (b.dataset.act) {
      case "filter": filter = b.dataset.f; draft = null; refresh(); break;
      case "start": draft = { item_id: b.dataset.item, type: b.dataset.type, date: "", note: "" }; refresh(); break;
      case "cancel": draft = null; refresh(); break;
      case "reset":
        try { localStorage.removeItem(KEY); } catch (er) {}
        S = EQ.clone(SEED); PARTIES = C.parties(S); draft = null; refresh(); toast("Demo reset"); break;
    }
  });

  document.addEventListener("input", (e) => {
    if (!draft || !e.target.closest("[data-draft]")) return;
    draft[e.target.name] = e.target.value;
    if (e.target.name === "date") refresh(); // date changes the preview; note does not
  });

  document.addEventListener("submit", (e) => {
    e.preventDefault();
    if (!draft) return;
    try {
      const r = C.impact(S, party.id, party.name, draft);
      S = r.state; draft = null; save(); refresh();
      const worse = r.changes.filter((c) => c.to === "red" && c.from !== "red").length;
      toast(`Sent: ${r.line}${worse ? ` ${worse} job${worse > 1 ? "s" : ""} turned red on the PM board.` : ""}`);
    } catch (er) { toast(er.message); }
  });

  // Another tab (PM command center or another contractor) changed the record.
  window.addEventListener("storage", (e) => { if (e.key !== KEY) return; S = load(); PARTIES = C.parties(S); party = pickParty(party.id); refresh(); });
  window.addEventListener("hashchange", () => { party = pickParty(decodeURIComponent(location.hash.slice(1))); draft = null; refresh(); });

  refresh();
})();
