"""Fictional vendor directory for the isolated EQORE coordination simulator.

These are invented businesses, qualification attestations and performance samples.
The directory is never evidence of real licensure, a real quote or availability.
"""
from copy import deepcopy

VERSION = "1.0.0"
CAPABILITIES = {
    "rigging": {"label": "Battery rigging and placement", "qualification": "rigging_lift_plan"},
    "electrical_ct": {"label": "Electrical correction and metering / CT verification", "qualification": "ma_electrical"},
    "epc_interconnection": {"label": "EPC engineering and utility application support", "qualification": "ma_engineering"},
}


def list_vendors():
    rows = [
        ("atlas_rigging_demo", "Atlas Lift Partners", "rigging", 36, 34, 1, 4.7, 11, 1200, 0),
        ("northstar_rigging_demo", "Northstar Equipment Movers", "rigging", 18, 16, 1, 4.6, 7, 1750, 1),
        ("bay_rigging_demo", "Bay Placement Services", "rigging", 8, 8, 0, 4.9, 3, None, 2),
        ("cedar_electrical_demo", "Cedar Electrical Services", "electrical_ct", 42, 39, 2, 4.6, 14, 1800, 0),
        ("meridian_electrical_demo", "Meridian Power Technicians", "electrical_ct", 21, 20, 1, 4.8, 8, 2900, 1),
        ("beacon_electrical_demo", "Beacon Electrical Projects", "electrical_ct", 6, 5, 0, 4.5, 2, None, 2),
        ("summit_epc_demo", "Summit EPC Engineering", "epc_interconnection", 30, 28, 1, 4.7, 10, 3600, 0),
        ("granite_epc_demo", "Granite Interconnection Partners", "epc_interconnection", 19, 17, 1, 4.5, 6, 4200, 1),
        ("elm_epc_demo", "Elm Grid Documentation", "epc_interconnection", 5, 5, 0, 4.8, 2, None, 2),
    ]
    result = []
    for identity, name, capability, jobs, ontime, rework, rating, references, amount, rank in rows:
        result.append({
            "id": identity, "name": name + " (fictional)", "synthetic": True,
            "contact": identity + "@vendors.example", "capabilities": [capability],
            "specialties": [CAPABILITIES[capability]["label"]], "service_states": ["MA", "NH", "RI"],
            "qualifications": [{"code": CAPABILITIES[capability]["qualification"], "status": "verified_demo",
                "expires_at": "2027-12-31T23:59:59-05:00", "reference": "DEMO-QUAL-" + identity,
                "provenance": "Invented credential record; no real license verification performed."}],
            "capacity": {"crew_size": 3 if capability == "rigging" else 2, "max_package_hours": 40,
                "battery_experience": True, "note": "Directory capability only. A scoped reply must confirm available capacity."},
            "performance": {"completed_jobs": jobs, "on_time_jobs": ontime, "rework_jobs": rework,
                "on_time_pct": round(100 * ontime / jobs, 1), "rework_pct": round(100 * rework / jobs, 1),
                "rating": rating, "rating_count": references, "reference_count": references,
                "as_of": "2026-11-01", "provenance": "Fictional internal closed-project records and invented customer references; not public reputation data."},
            "notes": "All business, price, qualification and reputation data are invented demo assumptions.",
            "demo_response": {"price": amount, "offset": rank, "currency": "USD",
                "duration_hours": 1 if capability == "rigging" else 4 if capability == "electrical_ct" else 8,
                "availability": "available" if rank < 2 else "needs_scope_review"},
        })
    # Deliberately attractive but ineligible profile exercises hard qualification filters.
    result.append({"id": "expired_trade_demo", "name": "Expired Trade Record (fictional)", "synthetic": True,
        "contact": "expired@vendors.example", "capabilities": list(CAPABILITIES), "service_states": ["MA"],
        "qualifications": [{"code": x["qualification"], "status": "verified_demo", "expires_at": "2026-10-01T00:00:00-04:00", "provenance": "Expired fictional record"} for x in CAPABILITIES.values()],
        "capacity": {"crew_size": 4, "max_package_hours": 80, "battery_experience": True},
        "performance": {"completed_jobs": 1, "on_time_jobs": 1, "rework_jobs": 0, "on_time_pct": 100,
            "rework_pct": 0, "rating": 5, "rating_count": 1, "reference_count": 1,
            "as_of": "2026-11-01", "provenance": "One invented reference; not comparable to a large sample."},
        "notes": "Must be excluded until credentials are renewed and reviewed.",
        "demo_response": {"price": 600, "offset": 0, "duration_hours": 4, "availability": "available"}})
    return deepcopy(result)


profiles = list_vendors


def public_profiles(items=None):
    """Directory facts safe to show before a simulated availability reply."""
    return [{key: deepcopy(value) for key, value in row.items() if key != "demo_response"} for row in (list_vendors() if items is None else items)]
