// EQORE contractor portal: sample contractor and agency database.
// ALL companies, people, rates and bookings are DEMO DATA (synthetic), not real businesses.
(function (root) {
  const TRADES = {
    civil: { label: "Concrete / civil", matchable: true },
    freight: { label: "Freight carrier", matchable: true },
    crane: { label: "Crane & rigging", matchable: true },
    electrical: { label: "Electrical contractor", matchable: true },
    commissioning: { label: "Commissioning", matchable: true },
    inspection: { label: "Inspector (AHJ)", matchable: false },
    utility: { label: "Utility", matchable: false },
    customer: { label: "Customer facility", matchable: false },
    eqore: { label: "EQORE", matchable: false },
  };

  // id, name, trade, state, base city, lat, lng, crews, day rate (USD), rating, certifications, service radius (mi), crew_id (command-center crew it runs, if any)
  const ROWS = [
    // Electrical. The five command-center crews belong to these companies.
    ["EL-HARBOR", "Harborline Electric", "electrical", "MA", "Boston", 42.3601, -71.0589, 1, 6400, 4.6, ["MA master electrician", "NFPA 855", "480V"], 90, "CREW-A"],
    ["EL-CENTMA", "Central Mass Power Systems", "electrical", "MA", "Worcester", 42.2626, -71.8023, 1, 5600, 4.3, ["MA master electrician", "480V"], 90, "CREW-B"],
    ["EL-SOMER", "Somerville Electrical Contractors", "electrical", "MA", "Somerville", 42.3876, -71.0995, 1, 6800, 4.8, ["MA master electrician", "NFPA 855", "480V"], 90, "CREW-C"],
    ["EL-PIONEER", "Pioneer Valley Electric", "electrical", "MA", "Springfield", 42.1015, -72.5898, 1, 5200, 4.2, ["MA master electrician", "480V"], 90, "CREW-D"],
    ["EL-CVALLEY", "Central Valley Electric", "electrical", "CA", "Fresno", 36.7378, -119.7871, 1, 6900, 4.5, ["CA C-10", "NFPA 855", "480V"], 220, "CREW-E"],
    ["EL-NSHORE", "North Shore Electrical Services", "electrical", "MA", "Lynn", 42.4668, -70.9495, 2, 6100, 4.4, ["MA master electrician", "NFPA 855", "480V"], 80, null],
    ["EL-SCOAST", "South Coast Electric", "electrical", "MA", "New Bedford", 41.6362, -70.9342, 1, 5400, 4.0, ["MA master electrician", "480V"], 70, null],
    ["EL-BERK", "Berkshire Electric Co.", "electrical", "MA", "Pittsfield", 42.4501, -73.2454, 1, 5000, 4.1, ["MA master electrician", "480V"], 70, null],
    ["EL-GOLDEN", "Golden State Electrical", "electrical", "CA", "Stockton", 37.9577, -121.2908, 2, 7200, 4.6, ["CA C-10", "NFPA 855", "480V"], 200, null],
    ["EL-INLAND", "Inland Empire Power", "electrical", "CA", "Riverside", 33.9533, -117.3962, 1, 7000, 4.3, ["CA C-10", "480V"], 180, null],
    // Concrete / civil
    ["CV-COMMON", "Commonwealth Civil & Concrete", "civil", "MA", "Framingham", 42.2793, -71.4162, 2, 4200, 4.5, ["MA hoisting", "ACI flatwork"], 90, null],
    ["CV-MERRI", "Merrimack Site Works", "civil", "MA", "Lowell", 42.6334, -71.3162, 1, 3900, 4.2, ["ACI flatwork"], 70, null],
    ["CV-CAPE", "Cape & Coast Concrete", "civil", "MA", "Taunton", 41.9001, -71.0898, 1, 3800, 4.0, ["ACI flatwork"], 70, null],
    ["CV-VALLEY", "Valley Pad & Paving", "civil", "CA", "Modesto", 37.6391, -120.9969, 2, 4300, 4.4, ["CA C-8", "ACI flatwork"], 200, null],
    ["CV-SOCAL", "SoCal Site Concrete", "civil", "CA", "Riverside", 33.9533, -117.3962, 1, 4500, 4.1, ["CA C-8"], 150, null],
    // Crane & rigging
    ["CR-BAY", "Bay Crane & Rigging", "crane", "MA", "Quincy", 42.2529, -71.0023, 2, 5800, 4.7, ["NCCCO operator", "MA hoisting"], 90, null],
    ["CR-WORC", "Worcester Rigging Co.", "crane", "MA", "Worcester", 42.2626, -71.8023, 1, 5200, 4.3, ["NCCCO operator"], 90, null],
    ["CR-CVAL", "Central Valley Crane", "crane", "CA", "Fresno", 36.7378, -119.7871, 1, 6000, 4.4, ["NCCCO operator"], 220, null],
    ["CR-PAC", "Pacific Rigging", "crane", "CA", "Stockton", 37.9577, -121.2908, 1, 6300, 4.2, ["NCCCO operator"], 200, null],
    // Freight
    ["FR-NEHH", "Northeast Heavy Haul", "freight", "MA", "Worcester", 42.2626, -71.8023, 2, 3100, 4.1, ["DOT oversize", "Hazmat class 9"], 150, null],
    ["FR-COAST", "Coastline Freight", "freight", "MA", "Brockton", 42.0834, -71.0184, 1, 2900, 3.9, ["DOT oversize", "Hazmat class 9"], 120, null],
    ["FR-WCHH", "West Coast Heavy Haul", "freight", "CA", "Bakersfield", 35.3733, -119.0187, 2, 3400, 4.3, ["DOT oversize", "Hazmat class 9"], 260, null],
    // Commissioning
    ["CM-QPEAST", "QorePack Field Services East", "commissioning", "MA", "Somerville", 42.3876, -71.0995, 1, 4800, 4.8, ["QorePack certified", "NFPA 855"], 120, null],
    ["CM-ATLAN", "Atlantic Commissioning Group", "commissioning", "MA", "Boston", 42.3601, -71.0589, 1, 5300, 4.4, ["QorePack certified"], 100, null],
    ["CM-QPWEST", "QorePack Field Services West", "commissioning", "CA", "Fresno", 36.7378, -119.7871, 1, 5000, 4.7, ["QorePack certified", "NFPA 855"], 260, null],
    ["CM-SIERRA", "Sierra Commissioning", "commissioning", "CA", "Modesto", 37.6391, -120.9969, 1, 5100, 4.2, ["QorePack certified"], 200, null],
    // Agencies (can sign in and update their items, but are not swapped in as resources)
    ["IN-MA", "Massachusetts municipal inspections", "inspection", "MA", "Boston", 42.3601, -71.0589, 3, 0, null, ["Wiring", "Building", "Fire"], 999, null],
    ["IN-CA", "California county inspections", "inspection", "CA", "Fresno", 36.7378, -119.7871, 2, 0, null, ["Wiring", "Building", "Fire"], 999, null],
    ["UT-NGRID", "National Grid interconnection", "utility", "MA", "Waltham", 42.3765, -71.2356, 99, 0, null, [], 999, null],
    ["UT-EVER", "Eversource interconnection", "utility", "MA", "Westwood", 42.2140, -71.2245, 99, 0, null, [], 999, null],
    ["UT-PGE", "PG&E interconnection", "utility", "CA", "Oakland", 37.8044, -122.2712, 99, 0, null, [], 999, null],
    ["UT-SCE", "SCE interconnection", "utility", "CA", "Rosemead", 34.0806, -118.0728, 99, 0, null, [], 999, null],
  ];

  const UTILITY_COMPANY = { "National Grid": "UT-NGRID", Eversource: "UT-EVER", "PG&E": "UT-PGE", SCE: "UT-SCE" };

  // Work already booked with other (non-EQORE) clients. Blocks a crew on those days.
  const OUTSIDE_BOOKINGS = [
    ["EL-NSHORE", "2026-11-09", "2026-11-13"], ["EL-NSHORE", "2026-11-16", "2026-11-18"],
    ["EL-SCOAST", "2026-11-09", "2026-11-20"],
    ["EL-GOLDEN", "2026-11-09", "2026-11-11"],
    ["EL-INLAND", "2026-11-12", "2026-11-25"],
    ["CV-MERRI", "2026-11-09", "2026-11-12"],
    ["CR-WORC", "2026-11-10", "2026-11-13"],
    ["CR-PAC", "2026-11-09", "2026-11-20"],
    ["FR-COAST", "2026-11-09", "2026-11-11"],
    ["CM-ATLAN", "2026-11-16", "2026-11-20"],
    ["CM-SIERRA", "2026-11-09", "2026-11-30"],
  ];

  const slug = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, ".").replace(/^\.|\.$/g, "");
  const companies = ROWS.map(([id, name, trade, state, city, lat, lng, crews, day_rate, rating, certifications, radius_mi, crew_id]) => ({
    id, name, trade, state, city, lat, lng, crews, day_rate, rating, certifications, radius_mi, crew_id,
    email: slug(name.replace(/ (Co\.|Inc\.)$/, "")) + "@demo.example",
    bookings: OUTSIDE_BOOKINGS.filter((b) => b[0] === id).map(([, start, end]) => ({ start, end, note: "Booked with another client" })),
  }));

  const PM = { id: "PM", name: "Jordan Lee", role: "Deployment PM, EQORE", email: "pm@eqore.demo.example" };
  const DEMO_PASSWORD = "demo";

  const db = { TRADES, companies, UTILITY_COMPANY, PM, DEMO_PASSWORD };
  root.EQORE_CONTRACTOR_DB = db;
  if (typeof module !== "undefined") module.exports = db;
})(typeof window !== "undefined" ? window : globalThis);
