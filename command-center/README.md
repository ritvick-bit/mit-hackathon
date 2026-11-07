# EQORE Install Command Center (demo)

Static web app, no build step. All sites, savings and dates are DEMO DATA.

Run: `python3 -m http.server 8765` in this folder, open http://localhost:8765 (map needs internet).
Test the engine: `node engine.test.js`

Files: data.js (seed), engine.js (readiness, conflicts, reschedule), app.js + index.html + styles.css (UI).
State saves in localStorage; "Reset demo" restores the seed.
