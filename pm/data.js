// EQORE PM platform: synthetic demo data.
// ALL projects, customers, companies, people, rates and documents are DEMO DATA, not real businesses or people.
// Dates are relative to "today" so the demo always shows projects at different stages.
(function (root) {
  // ---------- Project managers (each sees only their own portfolio) ----------
  const PMS = [
    { id: "PM-JORDAN", name: "Jordan Lee", email: "jordan.lee@eqore.demo.example", region: "Eastern Massachusetts" },
    { id: "PM-SAM", name: "Sam Ortiz", email: "sam.ortiz@eqore.demo.example", region: "Central and Western Massachusetts" },
    { id: "PM-PRIYA", name: "Priya Shah", email: "priya.shah@eqore.demo.example", region: "California" },
  ];
  const DEMO_PASSWORD = "demo";

  // ---------- Deployment template (steps 4-16 of docs/CHALLENGE.md, as one PM-facing timeline) ----------
  // key, short label, name, phase, owner role, duration (work days), predecessor keys
  const TEMPLATE = [
    ["contract", "Contract", "Contract & approvals", "Sign the customer", "customer", 15, []],
    ["equipment", "Equipment", "Select equipment", "Engineering", "supplier", 10, ["contract"]],
    ["engineering", "Stamped plans", "Stamped engineering", "Engineering", "engineering", 20, ["contract"]],
    ["permitting", "Permits", "Permitting", "Parallel tracks", "inspection", 30, ["engineering"]],
    ["interconnection", "Interconnect", "Utility interconnection", "Parallel tracks", "utility", 60, ["engineering"]],
    ["procurement", "Procurement", "Procurement & freight", "Parallel tracks", "freight", 50, ["equipment"]],
    ["precon", "Pre-con", "Pre-construction scheduling", "Construction", "eqore", 3, ["permitting", "procurement"]],
    ["civil", "Civil", "Civil work & pad cure", "Construction", "civil", 10, ["precon"]],
    ["placement", "Placement", "Delivery & crane placement", "Construction", "crane", 2, ["civil"]],
    ["electrical", "Electrical", "Electrical installation", "Construction", "electrical", 8, ["placement"]],
    ["tie_in", "Tie-in", "Tie-in to switchgear", "Construction", "electrical", 1, ["electrical"]],
    ["controls", "Controls", "Controls & comms", "Construction", "eqore", 4, ["placement"]],
    ["final_insp", "Inspections", "Final inspections", "Inspections & switch-on", "inspection", 5, ["tie_in"]],
    ["commissioning", "Commissioning", "Commissioning", "Inspections & switch-on", "commissioning", 3, ["final_insp", "controls"]],
    ["pto", "PTO", "Utility permission to operate", "Inspections & switch-on", "utility", 10, ["commissioning", "interconnection"]],
    ["energize", "Energize", "Energize & hand over", "Inspections & switch-on", "eqore", 1, ["pto"]],
  ].map(([key, short, name, phase, role, duration, preds]) => ({ key, short, name, phase, role, duration, preds }));

  // Paperwork per step. flow = who fills or signs, in order (PM, customer, or the project's company in that role).
  const DOCS = {
    contract: [["Customer energy services agreement", ["PM", "customer"]], ["Landlord consent package", ["customer"]], ["Certificate of insurance", ["customer", "PM"]]],
    equipment: [["UL 9540A fire test report", ["supplier"]], ["Equipment quote and lead time", ["supplier", "PM"]]],
    engineering: [["Stamped plan set", ["engineering", "PM"]], ["NFPA 855 package", ["engineering"]]],
    permitting: [["Building permit application", ["PM", "inspection"]], ["Electrical permit", ["electrical", "inspection"]]],
    interconnection: [["Interconnection application", ["PM", "utility"]], ["Interconnection agreement", ["utility", "PM"]]],
    procurement: [["Purchase order", ["PM", "supplier"]], ["Delivery schedule and bill of lading", ["freight", "PM"]]],
    precon: [["Shutdown window approval", ["PM", "customer"]], ["Crane lift plan", ["crane", "PM"]]],
    civil: [["Pad pour inspection report", ["civil", "PM"]]],
    placement: [["Delivery receipt", ["freight", "PM"]]],
    electrical: [["Rough wiring inspection sign-off", ["electrical", "inspection"]]],
    tie_in: [["Switching procedure", ["electrical", "customer"]]],
    final_insp: [["Certificate of completion", ["inspection", "PM"]]],
    commissioning: [["Commissioning report", ["commissioning", "PM"]]],
    pto: [["Permission to operate letter", ["utility"]]],
    energize: [["Customer handover acceptance", ["PM", "customer"]]],
  };

  const DEPARTMENTS = {
    contract: "Contracts & legal", equipment: "Procurement", engineering: "Engineering", permitting: "Permitting & inspections",
    interconnection: "Utility interconnection", procurement: "Procurement", precon: "Construction", civil: "Construction",
    placement: "Construction", electrical: "Permitting & inspections", tie_in: "Construction", controls: "Construction",
    final_insp: "Permitting & inspections", commissioning: "Construction", pto: "Utility interconnection", energize: "Customer",
  };

  const TRADES = {
    supplier: "Battery & inverter supplier", engineering: "Engineering (PE)", civil: "Concrete / civil", freight: "Freight carrier",
    crane: "Crane & rigging", electrical: "Electrical contractor", commissioning: "Commissioning", inspection: "Inspections (AHJ)",
    utility: "Utility", customer: "Customer", eqore: "EQORE",
  };

  // ---------- Companies (subcontractors, suppliers and agencies) ----------
  // id, name, trade, state, city, lat, lng, crews, day rate (USD), rating, certifications, service radius (mi), contact name
  const COMPANIES = [
    ["EL-HARBOR", "Harborline Electric", "electrical", "MA", "Boston", 42.3601, -71.0589, 1, 6400, 4.6, ["MA master electrician", "NFPA 855"], 90, "Dana Whitfield"],
    ["EL-CENTMA", "Central Mass Power Systems", "electrical", "MA", "Worcester", 42.2626, -71.8023, 1, 5600, 4.3, ["MA master electrician"], 90, "Marco Bellini"],
    ["EL-SOMER", "Somerville Electrical Contractors", "electrical", "MA", "Somerville", 42.3876, -71.0995, 2, 6800, 4.8, ["MA master electrician", "NFPA 855"], 90, "Grace Okafor"],
    ["EL-PIONEER", "Pioneer Valley Electric", "electrical", "MA", "Springfield", 42.1015, -72.5898, 1, 5200, 4.2, ["MA master electrician"], 90, "Tom Kowalski"],
    ["EL-NSHORE", "North Shore Electrical Services", "electrical", "MA", "Lynn", 42.4668, -70.9495, 1, 6100, 4.4, ["MA master electrician", "NFPA 855"], 80, "Renee Dubois"],
    ["EL-BERK", "Berkshire Electric Co.", "electrical", "MA", "Pittsfield", 42.4501, -73.2454, 1, 5000, 4.1, ["MA master electrician"], 70, "Owen Gallagher"],
    ["EL-CVALLEY", "Central Valley Electric", "electrical", "CA", "Fresno", 36.7378, -119.7871, 2, 6900, 4.5, ["CA C-10", "NFPA 855"], 220, "Luis Herrera"],
    ["EL-GOLDEN", "Golden State Electrical", "electrical", "CA", "Stockton", 37.9577, -121.2908, 1, 7200, 4.6, ["CA C-10", "NFPA 855"], 200, "Mei Chen"],
    ["EL-INLAND", "Inland Empire Power", "electrical", "CA", "Riverside", 33.9533, -117.3962, 1, 7000, 4.3, ["CA C-10"], 180, "Andre Willis"],
    ["CV-COMMON", "Commonwealth Civil & Concrete", "civil", "MA", "Framingham", 42.2793, -71.4162, 2, 4200, 4.5, ["MA hoisting", "ACI flatwork"], 90, "Kevin Brennan"],
    ["CV-MERRI", "Merrimack Site Works", "civil", "MA", "Lowell", 42.6334, -71.3162, 1, 3900, 4.2, ["ACI flatwork"], 70, "Sofia Petrakis"],
    ["CV-PIONEER", "Pioneer Pad & Paving", "civil", "MA", "Holyoke", 42.2043, -72.6162, 1, 3700, 4.0, ["ACI flatwork"], 70, "Jim Doherty"],
    ["CV-VALLEY", "Valley Pad & Paving", "civil", "CA", "Modesto", 37.6391, -120.9969, 2, 4300, 4.4, ["CA C-8", "ACI flatwork"], 200, "Rosa Delgado"],
    ["CV-SOCAL", "SoCal Site Concrete", "civil", "CA", "Riverside", 33.9533, -117.3962, 1, 4500, 4.1, ["CA C-8"], 150, "Derek Yamamoto"],
    ["CR-BAY", "Bay Crane & Rigging", "crane", "MA", "Quincy", 42.2529, -71.0023, 1, 5800, 4.7, ["NCCCO operator", "MA hoisting"], 90, "Pat Sullivan"],
    ["CR-WORC", "Worcester Rigging Co.", "crane", "MA", "Worcester", 42.2626, -71.8023, 1, 5200, 4.3, ["NCCCO operator"], 120, "Nina Rossi"],
    ["CR-CVAL", "Central Valley Crane", "crane", "CA", "Fresno", 36.7378, -119.7871, 1, 6000, 4.4, ["NCCCO operator"], 220, "Hector Ruiz"],
    ["CR-PAC", "Pacific Rigging", "crane", "CA", "Ontario", 34.0633, -117.6509, 1, 6300, 4.2, ["NCCCO operator"], 200, "Kim Nguyen"],
    ["FR-NEHH", "Northeast Heavy Haul", "freight", "MA", "Worcester", 42.2626, -71.8023, 2, 3100, 4.1, ["DOT oversize", "Hazmat class 9"], 150, "Bill Carver"],
    ["FR-COAST", "Coastline Freight", "freight", "MA", "Brockton", 42.0834, -71.0184, 1, 2900, 3.9, ["DOT oversize", "Hazmat class 9"], 120, "Angela Price"],
    ["FR-WCHH", "West Coast Heavy Haul", "freight", "CA", "Bakersfield", 35.3733, -119.0187, 2, 3400, 4.3, ["DOT oversize", "Hazmat class 9"], 260, "Ray Navarro"],
    ["CM-QPEAST", "QorePack Field Services East", "commissioning", "MA", "Somerville", 42.3876, -71.0995, 2, 4800, 4.8, ["QorePack certified", "NFPA 855"], 140, "Ilana Brooks"],
    ["CM-ATLAN", "Atlantic Commissioning Group", "commissioning", "MA", "Boston", 42.3601, -71.0589, 1, 5300, 4.4, ["QorePack certified"], 100, "Victor Osei"],
    ["CM-QPWEST", "QorePack Field Services West", "commissioning", "CA", "Fresno", 36.7378, -119.7871, 2, 5000, 4.7, ["QorePack certified", "NFPA 855"], 260, "Hannah Lee"],
    ["EN-STRATA", "Strata Engineering PE", "engineering", "MA", "Boston", 42.3601, -71.0589, 3, 2400, 4.6, ["MA PE (electrical)", "MA PE (structural)"], 200, "Rachel Adeyemi"],
    ["EN-PACPE", "Pacific Grid Engineers", "engineering", "CA", "Oakland", 37.8044, -122.2712, 3, 2600, 4.5, ["CA PE (electrical)", "CA PE (civil)"], 400, "David Park"],
    ["SU-QPACK", "QorePack Systems (battery supplier)", "supplier", "MA", "Boston", 42.3601, -71.0589, 9, 0, 4.4, ["UL 9540", "UL 9540A"], 3000, "Elena Marsh"],
    ["SU-VOLTA", "Voltaic Inverters", "supplier", "CA", "San Jose", 37.3382, -121.8863, 9, 0, 4.2, ["UL 1741"], 3000, "Sanjay Rao"],
    ["SU-BAYSW", "Bay State Switchgear Supply", "supplier", "MA", "Woburn", 42.4793, -71.1523, 9, 0, 4.3, ["UL 891"], 3000, "Carla Mendes"],
    ["SU-PACSW", "Pacific Switchgear Supply", "supplier", "CA", "Fresno", 36.7378, -119.7871, 9, 0, 4.1, ["UL 891"], 3000, "Ben Okoro"],
    ["IN-MA", "Municipal inspections (MA)", "inspection", "MA", "Boston", 42.3601, -71.0589, 9, 0, null, ["Building", "Wiring", "Fire"], 999, "Inspections desk"],
    ["IN-CA", "County inspections (CA)", "inspection", "CA", "Fresno", 36.7378, -119.7871, 9, 0, null, ["Building", "Wiring", "Fire"], 999, "Inspections desk"],
    ["UT-NGRID", "National Grid interconnection", "utility", "MA", "Waltham", 42.3765, -71.2356, 99, 0, null, [], 999, "Interconnection team"],
    ["UT-EVER", "Eversource interconnection", "utility", "MA", "Westwood", 42.2140, -71.2245, 99, 0, null, [], 999, "Interconnection team"],
    ["UT-PGE", "PG&E interconnection", "utility", "CA", "Oakland", 37.8044, -122.2712, 99, 0, null, [], 999, "Interconnection team"],
    ["UT-SCE", "SCE interconnection", "utility", "CA", "Rosemead", 34.0806, -118.0728, 99, 0, null, [], 999, "Interconnection team"],
  ];

  // Work the companies have with other (non-EQORE) clients: [company, start offset, length], in work days from today.
  const OUTSIDE_BOOKINGS = [
    ["EL-NSHORE", 0, 6], ["CR-WORC", 1, 4], ["CV-MERRI", 0, 4], ["EL-GOLDEN", 2, 3], ["EL-INLAND", 3, 10],
    ["CR-PAC", 0, 9], ["FR-COAST", 0, 3], ["CM-ATLAN", 5, 5], ["CV-PIONEER", 4, 6], ["EL-BERK", 8, 5],
  ];

  // ---------- Project sites ----------
  // id, customer site, city, state, lat, lng, utility id, PM, kW, kWh, current step, progress through that step (0-1)
  const PROJECTS = [
    ["JOB-001", "Harbor Point Cold Storage", "Boston", "MA", 42.3449, -71.0336, "UT-EVER", "PM-JORDAN", 500, 1000, "electrical", 0.5],
    ["JOB-002", "Kendall Biolabs", "Cambridge", "MA", 42.3656, -71.0911, "UT-EVER", "PM-JORDAN", 250, 500, "permitting", 0.4],
    ["JOB-003", "Assembly Row Logistics", "Somerville", "MA", 42.3925, -71.0776, "UT-EVER", "PM-JORDAN", 750, 1500, "procurement", 0.85],
    ["JOB-004", "Granite Shore Foods", "Quincy", "MA", 42.2612, -71.0110, "UT-NGRID", "PM-JORDAN", 500, 1000, "final_insp", 0.3],
    ["JOB-005", "Brockton Metal Finishing", "Brockton", "MA", 42.0790, -71.0390, "UT-NGRID", "PM-JORDAN", 1000, 2000, "precon", 0.5],
    ["JOB-006", "Lynnway Plastics", "Lynn", "MA", 42.4600, -70.9600, "UT-NGRID", "PM-JORDAN", 250, 500, "engineering", 0.6],
    ["JOB-007", "Salem Harbor Seafood", "Salem", "MA", 42.5230, -70.8850, "UT-NGRID", "PM-JORDAN", 500, 1000, "pto", 0.3],
    ["JOB-008", "Waltham Data Hall", "Waltham", "MA", 42.3890, -71.2420, "UT-NGRID", "PM-JORDAN", 1000, 2000, "civil", 0.4],
    ["JOB-009", "Metrowest Printing", "Framingham", "MA", 42.2900, -71.4300, "UT-EVER", "PM-JORDAN", 250, 500, "contract", 0.6],
    ["JOB-010", "Mill City Textiles", "Lowell", "MA", 42.6400, -71.3300, "UT-NGRID", "PM-JORDAN", 500, 1000, "commissioning", 0.4],
    ["JOB-011", "Merrimack Bottling", "Lawrence", "MA", 42.7000, -71.1500, "UT-NGRID", "PM-JORDAN", 750, 1500, "interconnection", 0.5],
    ["JOB-012", "Woburn Precision Parts", "Woburn", "MA", 42.4850, -71.1600, "UT-NGRID", "PM-JORDAN", 250, 500, "placement", 0.5],
    ["JOB-013", "Taunton River Brewing", "Taunton", "MA", 41.9050, -71.1000, "UT-NGRID", "PM-JORDAN", 250, 500, "equipment", 0.5],
    ["JOB-014", "Plymouth Cranberry Co-op", "Plymouth", "MA", 41.9500, -70.6800, "UT-EVER", "PM-JORDAN", 500, 1000, "procurement", 0.4],
    ["JOB-015", "Canal District Foundry", "Worcester", "MA", 42.2590, -71.7950, "UT-NGRID", "PM-SAM", 1000, 2000, "tie_in", 0.5],
    ["JOB-016", "Marlborough Medical Supply", "Marlborough", "MA", 42.3500, -71.5500, "UT-NGRID", "PM-SAM", 500, 1000, "permitting", 0.8],
    ["JOB-017", "Fitchburg Paper Converters", "Fitchburg", "MA", 42.5800, -71.8100, "UT-NGRID", "PM-SAM", 750, 1500, "civil", 0.6],
    ["JOB-018", "Springfield Armory Lofts", "Springfield", "MA", 42.1050, -72.5800, "UT-EVER", "PM-SAM", 250, 500, "energize", 0.2],
    ["JOB-019", "Chicopee Ice Arena", "Chicopee", "MA", 42.1550, -72.6000, "UT-EVER", "PM-SAM", 500, 1000, "procurement", 0.6],
    ["JOB-020", "Holyoke Canal Mills", "Holyoke", "MA", 42.2050, -72.6100, "UT-EVER", "PM-SAM", 750, 1500, "electrical", 0.2],
    ["JOB-021", "Westfield Distribution", "Westfield", "MA", 42.1300, -72.7500, "UT-EVER", "PM-SAM", 1000, 2000, "engineering", 0.3],
    ["JOB-022", "Berkshire Hills Dairy", "Pittsfield", "MA", 42.4500, -73.2500, "UT-EVER", "PM-SAM", 250, 500, "placement", 0.2],
    ["JOB-023", "Northampton Food Hub", "Northampton", "MA", 42.3250, -72.6400, "UT-NGRID", "PM-SAM", 250, 500, "interconnection", 0.7],
    ["JOB-024", "Leominster Molding", "Leominster", "MA", 42.5250, -71.7600, "UT-NGRID", "PM-SAM", 500, 1000, "commissioning", 0.7],
    ["JOB-025", "Auburn Auto Parts", "Auburn", "MA", 42.1950, -71.8350, "UT-NGRID", "PM-SAM", 500, 1000, "contract", 0.3],
    ["JOB-026", "Fresno Packing House", "Fresno", "CA", 36.7500, -119.7700, "UT-PGE", "PM-PRIYA", 1000, 2000, "electrical", 0.7],
    ["JOB-027", "Delta Cold Chain", "Stockton", "CA", 37.9500, -121.3000, "UT-PGE", "PM-PRIYA", 750, 1500, "precon", 0.2],
    ["JOB-028", "Modesto Almond Processing", "Modesto", "CA", 37.6400, -121.0000, "UT-PGE", "PM-PRIYA", 1000, 2000, "permitting", 0.5],
    ["JOB-029", "Kern Valley Ag Supply", "Bakersfield", "CA", 35.3700, -119.0300, "UT-PGE", "PM-PRIYA", 500, 1000, "final_insp", 0.6],
    ["JOB-030", "Capitol Mall Offices", "Sacramento", "CA", 38.5800, -121.4900, "UT-PGE", "PM-PRIYA", 250, 500, "engineering", 0.8],
    ["JOB-031", "Port of Oakland Reefer Yard", "Oakland", "CA", 37.8000, -122.3000, "UT-PGE", "PM-PRIYA", 1000, 2000, "interconnection", 0.3],
    ["JOB-032", "San Jose Fab Services", "San Jose", "CA", 37.3500, -121.9000, "UT-PGE", "PM-PRIYA", 500, 1000, "civil", 0.8],
    ["JOB-033", "Riverside Distribution Center", "Riverside", "CA", 33.9600, -117.4000, "UT-SCE", "PM-PRIYA", 750, 1500, "procurement", 0.7],
    ["JOB-034", "Ontario Air Cargo", "Ontario", "CA", 34.0600, -117.6000, "UT-SCE", "PM-PRIYA", 1000, 2000, "pto", 0.6],
    ["JOB-035", "Fontana Steel Service", "Fontana", "CA", 34.0900, -117.4400, "UT-SCE", "PM-PRIYA", 500, 1000, "contract", 0.8],
    ["JOB-036", "Long Beach Container Services", "Long Beach", "CA", 33.7700, -118.2100, "UT-SCE", "PM-PRIYA", 750, 1500, "placement", 0.6],
    ["JOB-037", "Visalia Citrus Growers", "Visalia", "CA", 36.3300, -119.2900, "UT-SCE", "PM-PRIYA", 250, 500, "equipment", 0.3],
  ];

  // ---------- Products procured for every project ----------
  // key, product, category, supplier (company id, a project role, or "switchgear" for the state's switchgear supplier),
  // quantity (number, or "kwh/250" / "kw/250"), unit, step it is needed for, lead
  // (lead "procurement" = long-lead equipment bought during the procurement step; a number = delivered that many work days before it's needed)
  const PRODUCTS = [
    ["cabinets", "Battery cabinets (QorePack 250 kWh)", "Battery storage", "SU-QPACK", "kwh/250", "units", "placement", "procurement"],
    ["inverter", "Power conversion system (250 kW inverter)", "Inverter / PCS", "SU-VOLTA", "kw/250", "units", "placement", "procurement"],
    ["switchgear", "Switchgear and fused disconnect", "Switchgear", "switchgear", 1, "set", "tie_in", "procurement"],
    ["concrete", "Concrete, rebar and anchor bolts", "Civil materials", "civil", 1, "lot", "civil", 3],
    ["cable", "Conduit and 480 V cable", "Electrical materials", "electrical", 1, "lot", "electrical", 3],
    ["bollards", "Bollards and perimeter fencing", "Site safety", "civil", 8, "bollards", "final_insp", 5],
    ["gateway", "Monitoring gateway and comms kit", "Controls", "SU-QPACK", 1, "kit", "controls", 5],
  ];
  const PRODUCT_STATUSES = ["Not ordered", "Quoted", "Ordered", "In production", "Shipped", "Delivered", "Installed"];
  const PRODUCT_CATEGORIES = ["Battery storage", "Inverter / PCS", "Switchgear", "Transformer", "Civil materials", "Electrical materials", "Site safety", "Controls", "Other"];

  // ---------- Problems already reported (these are what turn a project red) ----------
  // project, step, extra work days, reported N work days ago (by the company that owns the step), what happened
  const ISSUES = [
    ["JOB-003", "procurement", 15, 2, "Cabinets are held at the port of Savannah (congestion): carrier now quotes delivery three weeks late."],
    ["JOB-004", "final_insp", 6, 1, "Fire marshal failed the final inspection: bollard spacing short of the NFPA 855 plan. Rework and re-inspection needed."],
    ["JOB-011", "interconnection", 25, 4, "National Grid moved the feeder to a group study. Interconnection agreement now expected about five weeks later."],
    ["JOB-017", "civil", 4, 1, "Pad forms failed the pre-pour check (rebar cover). Re-pour adds a full cure cycle."],
    ["JOB-020", "electrical", 5, 2, "Crew pulled to an emergency job; electrical install restarts next week."],
    ["JOB-026", "electrical", 3, 1, "Conduit run hit an unmarked water line; trench re-routed."],
    ["JOB-033", "procurement", 12, 3, "Oversize permit for the inverter skid denied for the planned route; re-routing the load."],
    ["JOB-036", "placement", 4, 1, "Crane double-booked for the lift day; next open slot is next week."],
    // A small delay that the schedule absorbs (interconnection has slack), so the project stays on time.
    ["JOB-023", "interconnection", 4, 2, "Utility asked for a revised one-line diagram; resubmitted, review restarts."],
  ];

  // Meetings the demo calendar shows (offsets in work days from today). Project meetings are added by the model.
  const MEETINGS = [
    { offset: 0, time: "09:00", title: "Portfolio stand-up", project: null },
    { offset: 2, time: "10:30", title: "Weekly sync with EQORE engineering", project: null },
    { offset: 5, time: "09:00", title: "Portfolio stand-up", project: null },
    { offset: 7, time: "10:30", title: "Weekly sync with EQORE engineering", project: null },
    { offset: 10, time: "09:00", title: "Portfolio stand-up", project: null },
  ];

  const data = { PMS, DEMO_PASSWORD, TEMPLATE, DOCS, DEPARTMENTS, TRADES, COMPANIES, OUTSIDE_BOOKINGS, PROJECTS, PRODUCTS, PRODUCT_STATUSES, PRODUCT_CATEGORIES, ISSUES, MEETINGS };
  root.EQORE_PM_DATA = data;
  if (typeof module !== "undefined") module.exports = data;
})(typeof window !== "undefined" ? window : globalThis);
