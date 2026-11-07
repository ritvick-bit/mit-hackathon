// EQORE Install Command Center: seed data.
// ALL sites, companies, savings and dates are DEMO DATA, not an EQORE published catalog.
(function (root) {
  const TODAY = "2026-11-07"; // demo clock

  const DAY = 86400000;
  const addDays = (s, n) => new Date(new Date(s + "T00:00:00Z").getTime() + n * DAY).toISOString().slice(0, 10);

  const CREWS = [
    { crew_id: "CREW-A", name: "Crew A", base_city: "Boston, MA", size: 4, skills: ["480V", "NFPA 855", "commissioning"], certifications: ["MA electrician", "NFPA 855"] },
    { crew_id: "CREW-B", name: "Crew B", base_city: "Worcester, MA", size: 3, skills: ["480V", "rigging"], certifications: ["MA electrician"] },
    { crew_id: "CREW-C", name: "Crew C", base_city: "Somerville, MA", size: 4, skills: ["480V", "NFPA 855", "rigging", "commissioning"], certifications: ["MA electrician", "NFPA 855"] },
    { crew_id: "CREW-D", name: "Crew D", base_city: "Springfield, MA", size: 3, skills: ["480V"], certifications: ["MA electrician"] },
    { crew_id: "CREW-E", name: "Crew E", base_city: "Fresno, CA", size: 4, skills: ["480V", "NFPA 855", "commissioning"], certifications: ["CA electrician", "NFPA 855"] },
  ];

  const CITY = {
    Worcester: [42.2626, -71.8023], Boston: [42.3601, -71.0589], Lowell: [42.6334, -71.3162],
    Springfield: [42.1015, -72.5898], Somerville: [42.3876, -71.0995], Cambridge: [42.3736, -71.1097],
    "Fall River": [41.7015, -71.155], Fresno: [36.7378, -119.7871], Bakersfield: [35.3733, -119.0187],
    Quincy: [42.2529, -71.0023], Chicopee: [42.1487, -72.6079], Modesto: [37.6391, -120.9969],
    "New Bedford": [41.6362, -70.9342], Taunton: [41.9001, -71.0898], Stockton: [37.9577, -121.2908],
    Lynn: [42.4668, -70.9495], Brockton: [42.0834, -71.0184], Pittsfield: [42.4501, -73.2454],
    Riverside: [33.9533, -117.3962], Haverhill: [42.7762, -71.0773], Framingham: [42.2793, -71.4162],
    Salinas: [36.6777, -121.6555], Attleboro: [41.9445, -71.2856],
  };

  // id, facility type, city, state, utility, kW, crew, install date
  const ROWS = [
    ["JOB-001", "Cold storage", "Worcester", "MA", "National Grid", 250, "CREW-A", "2026-11-10"],
    ["JOB-002", "Warehouse", "Boston", "MA", "Eversource", 300, "CREW-A", "2026-11-10"],
    ["JOB-003", "Manufacturing", "Lowell", "MA", "National Grid", 400, "CREW-C", "2026-11-11"],
    ["JOB-004", "Food processing", "Springfield", "MA", "Eversource", 200, "CREW-D", "2026-11-11"],
    ["JOB-005", "Logistics hub", "Somerville", "MA", "Eversource", 150, "CREW-C", "2026-11-12"],
    ["JOB-006", "Cold storage", "Cambridge", "MA", "Eversource", 350, "CREW-A", "2026-11-12"],
    ["JOB-007", "Warehouse", "Worcester", "MA", "National Grid", 250, "CREW-B", "2026-11-13"],
    ["JOB-008", "Manufacturing", "Fall River", "MA", "National Grid", 500, "CREW-C", "2026-11-13"],
    ["JOB-009", "Distribution", "Fresno", "CA", "PG&E", 300, "CREW-E", "2026-11-13"],
    ["JOB-010", "Cold storage", "Bakersfield", "CA", "SCE", 200, "CREW-E", "2026-11-14"],
    ["JOB-011", "Warehouse", "Boston", "MA", "Eversource", 100, "CREW-A", "2026-11-14"],
    ["JOB-012", "Manufacturing", "Quincy", "MA", "National Grid", 450, "CREW-A", "2026-11-16"],
    ["JOB-013", "Logistics", "Chicopee", "MA", "Eversource", 250, "CREW-D", "2026-11-16"],
    ["JOB-014", "Food processing", "Modesto", "CA", "PG&E", 350, "CREW-E", "2026-11-17"],
    ["JOB-015", "Warehouse", "New Bedford", "MA", "National Grid", 200, "CREW-B", "2026-11-17"],
    ["JOB-016", "Manufacturing", "Taunton", "MA", "National Grid", 300, "CREW-C", "2026-11-18"],
    ["JOB-017", "Cold storage", "Stockton", "CA", "PG&E", 400, "CREW-E", "2026-11-18"],
    ["JOB-018", "Distribution", "Lynn", "MA", "National Grid", 150, "CREW-A", "2026-11-19"],
    ["JOB-019", "Warehouse", "Brockton", "MA", "National Grid", 250, "CREW-B", "2026-11-19"],
    ["JOB-020", "Manufacturing", "Pittsfield", "MA", "Eversource", 200, "CREW-D", "2026-11-20"],
    ["JOB-021", "Logistics", "Riverside", "CA", "SCE", 300, "CREW-E", "2026-11-20"],
    ["JOB-022", "Cold storage", "Haverhill", "MA", "National Grid", 350, "CREW-A", "2026-11-21"],
    ["JOB-023", "Warehouse", "Framingham", "MA", "Eversource", 250, "CREW-C", "2026-11-21"],
    ["JOB-024", "Manufacturing", "Salinas", "CA", "PG&E", 400, "CREW-E", "2026-11-22"],
    ["JOB-025", "Distribution", "Attleboro", "MA", "National Grid", 200, "CREW-B", "2026-11-22"],
  ];

  const SAVINGS = { "JOB-001": 3200, "JOB-002": 3800, "JOB-003": 4200 };
  const SIZES = { "JOB-001": [4, 180], "JOB-002": [5, 200], "JOB-003": [6, 240] };
  const cityCount = {};

  const sites = [], jobs = [], shipments = [], inspections = [], shutdowns = [];

  ROWS.forEach((r, i) => {
    const [id, type, city, st, utility, kw, crew, date] = r;
    const n = String(i + 1).padStart(3, "0");
    const peak = Math.round((kw * 3.2) / 10) * 10;
    cityCount[city] = (cityCount[city] || 0) + 1;
    const k = cityCount[city] - 1;
    const [lat, lng] = CITY[city];
    sites.push({
      site_id: "SITE-" + n, name: `Demo ${type} Co. (${city})`, city, state: st, utility,
      facility_type: type.toLowerCase(), monthly_bill_usd: Math.max(10000, Math.round((peak * 38) / 500) * 500),
      peak_kw: peak, lat: lat + k * 0.006, lng: lng + k * 0.006,
      contact: "Facility manager (demo)",
    });
    const kwh = kw * 2;
    const modules = SIZES[id] ? SIZES[id][0] : Math.max(2, Math.round(kwh / 133));
    const savings = SAVINGS[id] || Math.round((kw * 13 * (st === "CA" ? 1.15 : 1)) / 100) * 100;
    jobs.push({
      job_id: id, site_id: "SITE-" + n, status: "scheduled", power_kw: kw, energy_kwh: kwh,
      modules, pad_sqft: SIZES[id] ? SIZES[id][1] : modules * 42, tie_in: "480V 3-phase",
      install_date: date, install_window: "06:00-14:00", crew_id: crew,
      projected_savings_usd_per_month: savings, cost_of_delay_usd_per_day: Math.round(savings / 30),
      // readiness inputs
      pad_ready: true, tie_in_confirmed: true,
      permits: { building: "approved", electrical: "approved", fire: "approved" },
      permit_approved_date: addDays(date, -(10 + ((i * 5) % 12))),
      utility_permission: true, crew_held: false,
    });
    // equipment
    shipments.push({
      shipment_id: "SHIP-" + n, job_id: id, item: "battery cabinets + inverter", vendor: "Demo Vendor",
      delivery_date: addDays(date, -3), status: addDays(date, -3) <= TODAY ? "delivered" : "in_transit",
    });
    // inspection
    inspections.push({
      inspection_id: "INSP-" + n, job_id: id, type: "electrical", scheduled_date: addDays(date, 1), status: "booked",
    });
    // shutdown
    shutdowns.push({
      shutdown_id: "SHUT-" + n, job_id: id, date, start_time: "06:00", end_time: "08:00",
      approved: true, requested: true, notes: "Short shutdown, facility approved",
    });
  });

  // ---- Hand-tuned cases from the brief ----
  const J = (id) => jobs.find((j) => j.job_id === id);
  const SH = (id) => shipments.find((x) => x.job_id === id);
  const IN = (id) => inspections.find((x) => x.job_id === id);
  const SD = (id) => shutdowns.find((x) => x.job_id === id);

  // JOB-001: equipment arrives after install + crew A double-booked with JOB-002
  Object.assign(SH("JOB-001"), { item: "battery cabinets", delivery_date: "2026-11-12", status: "in_transit" });
  Object.assign(IN("JOB-001"), { scheduled_date: "2026-11-14" });
  // JOB-002
  Object.assign(SH("JOB-002"), { item: "inverter + switchgear", delivery_date: "2026-11-09", status: "delivered" });
  Object.assign(IN("JOB-002"), { scheduled_date: "2026-11-11" });
  // JOB-003: shutdown never approved
  Object.assign(SH("JOB-003"), { item: "battery cabinets", delivery_date: "2026-11-10", status: "delivered" });
  Object.assign(IN("JOB-003"), { type: "fire", scheduled_date: "2026-11-12" });
  Object.assign(SD("JOB-003"), { approved: false, requested: false, notes: "Facility runs production, approval not yet given" });
  // Amber cases
  Object.assign(IN("JOB-006"), { type: "fire", scheduled_date: null, status: "not_booked" });
  J("JOB-008").permits.building = "revision"; J("JOB-008").permit_round = 2; J("JOB-008").permit_approved_date = null;
  Object.assign(SH("JOB-010"), { delivery_date: "2026-11-14", status: "in_transit" });
  J("JOB-013").utility_permission = false;
  Object.assign(SD("JOB-017"), { approved: false, requested: true, notes: "Shutdown requested, awaiting facility approval" });
  Object.assign(IN("JOB-023"), { type: "fire", scheduled_date: "2026-11-20" });

  const seed = { today: TODAY, sites, crews: CREWS, jobs, shipments, inspections, shutdowns, field: {}, log: [] };
  root.EQORE_SEED = seed;
  if (typeof module !== "undefined") module.exports = seed;
})(typeof window !== "undefined" ? window : globalThis);
