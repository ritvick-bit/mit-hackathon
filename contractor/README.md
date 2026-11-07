# EQORE Contractor Portal (demo)

The contractor and agency side of the Install Command Center. Pick who you are (install crew, equipment supplier, inspector, utility, permit office or customer facility) and see everything you owe across all jobs. Items that hold up an install come first, with the delay cost per day.

From the portal, a party can confirm dates, report a delay with a new date, mark work done, approve or decline, or book an inspection. Before sending, it previews what the PM will see: which jobs change readiness, and which other parties get new blocking items (for example, a crew delay moves the shutdown window back to the facility and makes the booked inspection too early).

All sites, companies and dates are DEMO DATA.

## Run

The portal reuses `../command-center/data.js` and `engine.js`, and shares the command center's saved state (`localStorage` key `eqore-cc-v1`). Serve the **repo root** so both pages are on the same origin:

```sh
python3 -m http.server 8765        # from the repo root
```

- PM view: http://localhost:8765/command-center/
- Contractor view: http://localhost:8765/contractor/ (link a party directly with a hash, e.g. `#crew:CREW-A`)

An update sent from the portal appears in the command center on its next reload. Other open portal tabs update immediately.

Tests: `node contractor/parties.test.js`

## Files

- `parties.js`: parties, the items each one owes, actions, and impact preview (pure functions, runs in Node)
- `app.js`, `index.html`, `styles.css`: the UI (base styles come from `../command-center/styles.css`)
