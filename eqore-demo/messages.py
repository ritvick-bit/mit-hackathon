"""Original stakeholder reports, bounded image uploads and separate model observations.

The readable summary is never an authorization or an engine event. Model-extracted
requests may open a sourcing inquiry; only the domain's explicit proposal/approval
path can change an operational plan.
"""
import base64
import copy
import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

MAX_IMAGE_BYTES = 4 * 1024 * 1024
MAX_ATTACHMENTS = 4


def image_type(data):
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        width, height = int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
        if not width or not height or width * height > 40_000_000:
            raise ValueError("PNG dimensions exceed the supported image size.")
        return "image/png"
    if data.startswith(b"\xff\xd8\xff") and data.endswith(b"\xff\xd9"):
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    raise ValueError("Attach a PNG, JPEG or WebP image. HTML and SVG uploads are not accepted.")


def prepare(state, payload, vendor_profiles):
    import operations
    raw = payload.get("raw_text", "")
    if not isinstance(raw, str) or not raw.strip() or len(raw) > 40_000:
        raise ValueError("Provide a message between 1 and 40,000 characters.")
    subject = payload.get("subject", "Stakeholder update")
    if not isinstance(subject, str) or len(subject) > 250:
        raise ValueError("Message subject must be no more than 250 characters.")
    sender = payload.get("sender_id")
    known = {p["id"] for p in state.get("stakeholders", [])} | {p["id"] for p in vendor_profiles}
    if sender not in known:
        raise ValueError("Select a stakeholder or vendor recorded for this demo.")
    uploads = payload.get("attachments", [])
    if not isinstance(uploads, list) or len(uploads) > MAX_ATTACHMENTS:
        raise ValueError("A report may have up to four image attachments.")
    metadata, blobs = [], []
    for upload in uploads:
        if not isinstance(upload, dict) or not isinstance(upload.get("data_base64"), str):
            raise ValueError("An attachment needs base64 image data.")
        if len(upload["data_base64"]) > MAX_IMAGE_BYTES * 1.4:
            raise ValueError("Each image must be at most 4 MiB.")
        try:
            data = base64.b64decode(upload["data_base64"], validate=True)
        except (ValueError, TypeError) as exc:
            raise ValueError("Invalid image encoding.") from exc
        if not data or len(data) > MAX_IMAGE_BYTES:
            raise ValueError("Each image must be between 1 byte and 4 MiB.")
        mime = image_type(data)
        if upload.get("mime_type") not in (None, "", mime):
            raise ValueError("Image content does not match its declared type.")
        name = re.sub(r"[\x00-\x1f\x7f]", "", Path(str(upload.get("name", "attachment"))).name)[:150] or "attachment"
        digest = hashlib.sha256(data).hexdigest()
        identity = "attachment-" + hashlib.sha256((state["project"]["id"] + digest).encode()).hexdigest()[:32]
        meta = {"id": identity, "name": name, "mime_type": mime, "sha256": digest,
                "size_bytes": len(data), "url": "/api/attachments/" + identity}
        metadata.append(meta)
        blobs.append(dict(meta, data=data, project_id=state["project"]["id"]))
    action = {"type": "ingest_message", "message_id": "message-" + secrets.token_hex(8),
              "issuer_id": sender, "text": raw, "subject": subject, "attachments": metadata}
    if payload.get("case_id"):
        action["case_id"] = payload["case_id"]
    updated = operations.apply(state, action, vendor_profiles=vendor_profiles)
    return updated, blobs, action["message_id"]


def find(state, identity):
    message = next((m for m in state.get("operations", {}).get("messages", []) if m["id"] == identity), None)
    if message is None:
        raise ValueError("Message is not part of the selected project.")
    return message


def seed_demo_image(state, path, vendor_profiles):
    """Add a clearly authored illustrative source record once, preserving saved work."""
    import operations
    identity = "message-riverbend-illustrative-field-note"
    case_id = "case-riverbend-electrical"
    if (state["project"].get("demo_project_id") != "riverbend_logistics" or
        not any(c["id"] == case_id for c in state.get("operations", {}).get("cases", [])) or
        any(m["id"] == identity for m in state.get("operations", {}).get("messages", []))):
        return state, []
    data = Path(path).read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    image_id = "attachment-" + hashlib.sha256((state["project"]["id"] + digest).encode()).hexdigest()[:32]
    meta = {"id": image_id, "name": "Illustrative field note — synthetic demo.png", "mime_type": image_type(data),
            "sha256": digest, "size_bytes": len(data), "url": "/api/attachments/" + image_id}
    updated = operations.apply(state, {"type": "ingest_message", "message_id": identity,
        "issuer_id": "verifier", "case_id": case_id,
        "subject": "Illustrative field note: metering identification review",
        "text": "Attached is an authored demo diagram illustrating the reported metering/CT identification discrepancy. It is not a site photograph or engineering diagnosis. Please arrange qualified electrical support and independent reinspection after the engineer reconciles the issued design. Utility operating acceptance and customer IT readiness remain separate open requirements.",
        "attachments": [meta]}, vendor_profiles=vendor_profiles)
    return updated, [dict(meta, data=data, project_id=state["project"]["id"])]


def apply_analysis(state, identity, result, vendor_profiles):
    """Save two independent projections; a summary itself never closes a gate."""
    import operations
    updated = copy.deepcopy(state)
    message = find(updated, identity)
    output = result["output"]
    text = message.get("text", message.get("raw_text", ""))
    now = datetime.now(timezone.utc).isoformat()
    source_hash = message.get("content_hash") or hashlib.sha256(text.encode()).hexdigest()
    quotes = output.get("source_quotes", [])
    if any(not q or q not in text for q in quotes):
        raise ValueError("Model extraction cited text absent from the original report. Nothing was applied.")
    known_tasks = {t["id"]: t for t in state["tasks"]}
    task_ids = output.get("affected_task_ids", [])
    if any(tid not in known_tasks for tid in task_ids):
        raise ValueError("Model extraction referenced an unknown task.")
    message["summary"] = {"text": output["summary"], "mode": "live", "generated_at": now,
                          "source_hash": source_hash, "uncertainties": output["uncertainties"],
                          "trace": {key: value for key, value in result.items() if key != "output"}}
    message["assertions"] = [{"claim": claim, "source_message_id": identity,
                               "source_quotes": quotes, "source_hash": source_hash,
                               "validation_status": "reported_not_authorized"}
                              for claim in output["observations"]]
    message["image_observations"] = output.get("image_observations", [])
    message["extraction"] = {key: output[key] for key in
                              ("request_type", "vendor_capability", "affected_task_ids", "request_summary")}
    # A narrowly classified request can solicit information. It cannot approve a
    # design, assign a permit, set a quote price or complete physical work.
    capability = output["vendor_capability"]
    supported = {"rigging", "electrical_ct", "epc_interconnection"}
    related = [case for case in updated["operations"]["cases"]
               if identity in case.get("source_message_ids", [])]
    if not related and output["request_type"] == "vendor_help" and capability in supported and task_ids and quotes:
        targets = [known_tasks[tid] for tid in task_ids]
        pending = [task for task in targets if task.get("status") != "completed"]
        if not pending:
            message["triage_status"] = "needs_scope_review"
            return updated
        from vendors import CAPABILITIES
        qualification = [CAPABILITIES[capability]["qualification"]]
        # A correction enables downstream acceptance; it cannot require its own
        # future sign-off. Use execution gates for the trade, not the target's
        # verification/commissioning gates, and retain all external predecessors.
        execution_gates = {
            "electrical_ct": ["design", "permit", "utility_install", "customer_window"],
            "rigging": ["permit", "utility_install", "delivery_receipt"],
            "epc_interconnection": [],
        }[capability]
        affected = {t["id"] for t in pending}
        predecessors = list(dict.fromkeys(p for task in pending for p in task.get("predecessors", [])
                                          if p not in affected))
        earliest = datetime.fromisoformat(state["project"]["now"])
        for predecessor in predecessors:
            task = known_tasks[predecessor]
            earliest = max(earliest, datetime.fromisoformat(task["planned_start"]) +
                           timedelta(hours=float(task.get("duration_hours", 0))))
        request = {"title": output["request_summary"][:180], "why": "Stakeholder requested additional vendor support; scope and offer must be confirmed.",
                   "request": output["request_summary"], "vendor_capability": capability,
                   "affected_task_ids": [t["id"] for t in pending],
                   "stakeholder_ids": list(dict.fromkeys(t["owner_id"] for t in targets)),
                   "required_gates": [g for g in execution_gates if g in state["gates"]],
                   "predecessor_task_ids": predecessors, "earliest_start": earliest.isoformat(),
                   "priority": 75, "duration_hours": {"rigging": 1, "electrical_ct": 4, "epc_interconnection": 8}[capability],
                   "required_qualifications": qualification,
                   "additional_conditions": ["Scope and duration are preliminary until the qualified vendor confirms its scoped offer."]}
        # Reuse the immutable original message ID; domain layer links the request
        # without manufacturing a second report or changing its original content.
        updated = operations.apply(updated, {"type": "ingest_message", "message_id": identity,
                                  "issuer_id": message.get("issuer_id", message.get("sender_id")),
                                  "text": text, "subject": message.get("subject", "Stakeholder update"),
                                  "attachments": message.get("attachments", []), "validated_request": request},
                                   vendor_profiles=vendor_profiles)
        find(updated, identity)["triage_status"] = "sourcing_requested"
    else:
        message["triage_status"] = "linked_case" if related else "needs_scope_review"
    return updated
