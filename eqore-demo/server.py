#!/usr/bin/env python3
"""EQORE demo: local HTTP API, transactional persistence and live decision jobs."""
import argparse
import copy
import json
import mimetypes
import os
import secrets
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import engine
import dashboard
import evaluation
import llm
import projects
import project_evaluation
import challenges
import phases
import scenarios
import operations
import vendors
import messages
import workspace
import contractor_bridge
import project_resources
from storage import Conflict, Store

ROOT = Path(__file__).resolve().parent
APP_VERSION = "0.6.0"
CAPABILITIES = [
    ("CAP01", "Portfolio coordination", "Three saved project workspaces with distinct costs, stakeholders and constraints; shared resources are recorded assumptions, not a portfolio optimizer."),
    ("CAP02", "Schedule, procurement & cost", "Delivery evidence, feasible recovery options, scoped approval and atomic plan commitment."),
    ("CAP03", "Permits & interconnection", "Track applicable gates and distinguish acknowledgements from valid approval."),
    ("CAP04", "Field coordination", "Coordinate dependencies, site and customer windows, and separate crew confirmations."),
    ("CAP05", "Installation verification", "Request qualified evidence and preserve unresolved defects and design revisions."),
    ("CAP06", "Commissioning & handoff", "Track readiness, faults, retest evidence and handoff prerequisites."),
    ("CAP07", "Customer continuity", "Respect customer constraints and route decision requests to the authorized stakeholder."),
    ("CAP08", "Learning across projects", "Propose scoped process changes for review; no automatic policy adoption."),
]


def next_response_deadline(state):
    """Expose an observed waiting deadline, never a hidden scenario event."""
    now = datetime.fromisoformat(state["project"]["now"])
    deadlines = []
    policy = state["project"].get("response_policy", {})
    for request in state["requests"]:
        if request.get("status") not in {"pending", "sent", "open", "acknowledged"}:
            continue
        if request.get("due_at"):
            deadlines.append(datetime.fromisoformat(request["due_at"]))
        if request.get("gate_id") and request.get("created_at") and not request.get("parent_request_id"):
            deadlines.append(datetime.fromisoformat(request["created_at"]) +
                             timedelta(hours=float(policy.get("escalate_after_hours", 48))))
    future = [value for value in deadlines if value > now]
    return min(future).isoformat() if future else None


class Application:
    def __init__(self, database):
        self.store = Store(database)
        self.jobs = {}
        self.job_lock = threading.RLock()
        self.contractor_sessions = {}
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="eqore-job")
        self.auth = llm.runtime_status(check_auth=True)
        catalog = projects.list_projects()
        added = self.store.ensure_projects([projects.initial_state(p["id"]) for p in catalog])
        if self.store.read() is None or added == len(catalog):
            self.store.write(self.store.projects()[catalog[0]["id"]]["state"], operation="initialize_projects")
        self.store.refresh_pristine_projects([projects.initial_state(p["id"]) for p in catalog])
        self.store.seed_vendors(vendors.list_vendors())
        self.store.enrich_projects(self.initialize_workspace)

    def initialize_workspace(self, state):
        if not state["project"].get("demo_project_id"):
            return state
        return messages.seed_demo_image(operations.ensure(state), ROOT / "web" / "field-note.png", self.store.vendors())

    def vendor_context(self, state):
        """Global saved bookings constrain vendor capacity across demo projects."""
        profiles = self.store.vendors()
        by_id = {v["id"]: v for v in profiles}
        for record in self.store.projects().values():
            other = record["state"]
            if other["project"]["id"] == state["project"]["id"]:
                continue
            for booking in other.get("operations", {}).get("bookings", []):
                if booking.get("status") not in {"confirmed", "pending", "requested", "required"}:
                    continue
                vendor = by_id.get(booking.get("vendor_id", booking.get("recipient_id")))
                if vendor:
                    vendor.setdefault("reservations", []).append({
                        "start": booking.get("start", booking.get("planned_start")), "end": booking.get("end"),
                        "project_id": other["project"]["id"], "case_id": booking.get("case_id"), "status": booking["status"]})
        return profiles

    def bootstrap(self, project_id=None):
        record = self.store.read()
        active_session_version = record["version"]
        if project_id and project_id != record["state"]["project"].get("demo_project_id"):
            saved = self.store.projects().get(project_id)
            if saved is None:
                raise ValueError("Unknown project.")
            # A read-only refresh must not authorize mutations against a different selection.
            record = dict(saved, version=-1)
        state = record["state"]
        runtime = llm.runtime_status()
        runtime.update(authenticated=self.auth["authenticated"], detail=self.auth["detail"])
        recommendation = record["recommendation"]
        if recommendation is None:
            recommendation = dict(engine.recommend(state), mode="baseline")
        analysis = engine.analyze(state)
        operation_view = workspace.public(operations.summarize(state, self.vendor_context(state)))
        overview = workspace.finance(dashboard.summarize(state, analysis), state, operation_view)
        phase_view = phases.summarize(state, analysis)
        knowledge = json.loads((ROOT / "knowledge.json").read_text())
        saved_projects = self.store.projects()
        catalog = []
        for project in projects.list_projects():
            saved = saved_projects[project["id"]]["state"]
            is_current = saved["project"]["id"] == state["project"]["id"]
            metrics = overview["metrics"] if is_current else dashboard.summarize(saved)["metrics"]
            project_phases = phase_view if is_current else phases.summarize(saved)
            phase_summary = {key: project_phases[key] for key in
                             ("version", "active_phase_ids", "active_phase_titles", "open_rework_count", "all_accepted")}
            phase_summary["statuses"] = [{key: row[key] for key in
                                          ("id", "title", "status", "acceptance_current", "completed_task_count", "task_count")}
                                         for row in project_phases["phases"]]
            project_operations = operation_view if is_current else workspace.public(operations.summarize(saved, self.vendor_context(saved)))
            operation_summary = workspace.operation_summary(project_operations)
            pending_reports = self.contractor_requests(saved)
            if pending_reports:
                operation_summary["open_count"] += len(pending_reports)
                operation_summary["cases"].extend({"id": r["id"], "title": r["title"], "priority": r["priority"],
                                                   "status": r["status"], "why": r["message"].get("text", "")} for r in pending_reports)
                highest = max(operation_summary["cases"], key=lambda c: c.get("priority", 0))
                operation_summary.update(top_priority=highest["priority"], top_title=highest["title"])
            catalog.append(dict(project, metrics=metrics,
                                geography=project_resources.geography(saved),
                                readiness=project_resources.view(saved, operation_view if is_current else
                                    workspace.public(operations.summarize(saved, self.vendor_context(saved))), self.vendor_context(saved))["readiness"],
                                current_phase_titles=project_phases["active_phase_titles"], phase_summary=phase_summary,
                                operation_summary=operation_summary,
                                selected=project["id"] == state["project"].get("demo_project_id")))
        return {"version": APP_VERSION, "state": state, "session_version": record["version"],
                "active_session_version": active_session_version,
                "analysis": analysis, "dashboard": overview, "projects": catalog,
                "phases": phase_view, "workflow_review": knowledge.get("workflow_review", {}),
                "operations": operation_view, "vendors": workspace.public(self.store.vendors()),
                "workspace": {"calendar": workspace.calendar(state, operation_view),
                              "resources": project_resources.view(state, operation_view, self.vendor_context(state)),
                              "portfolio_revision": self.store.portfolio_revision(),
                              "contractor_requests": self.contractor_requests(state),
                              "timezone": state["project"].get("timezone", "America/New_York")},
                "mode": "project" if state["project"].get("demo_project_id") else "scenario",
                "recommendation": recommendation,
                "scenarios": scenarios.list_scenarios(), "sources": scenarios.sources(),
                "runtime": runtime, "evaluations": [r for r in self.store.reports(50) if r.get("suite") != "challenges"][:10],
                "challenge_design": challenges.load_design(),
                "challenge_reports": [r for r in self.store.reports(50) if r.get("suite") == "challenges"],
                "simulation": {"next_response_at": next_response_deadline(state)},
                "reasoning_history": self.store.reasoning(project_id=state["project"]["id"]),
                "capabilities": [{"id": i, "title": t, "status": "demo", "description": d} for i, t, d in CAPABILITIES]}

    @staticmethod
    def contractor_requests(state):
        result = []
        linked_messages = {identity for case in state.get("operations", {}).get("cases", [])
                           for identity in case.get("source_message_ids", [])}
        for report in state.get("contractor_reports", []):
            if report.get("type") != "problem" or report.get("case_id") or report.get("message_id") in linked_messages or report.get("status") not in {"reported", "needs_scope_review"}:
                continue
            actor = next((x for x in state["stakeholders"] if x["id"] == report["actor_id"]), {})
            task = next((x for x in state["tasks"] if x["id"] == report["task_id"]), {})
            message = messages.find(state, report["message_id"])
            result.append(dict(report, actor_name=actor.get("name", report["actor_id"]),
                               task_title=task.get("title", report["task_id"]), message=workspace.public(message),
                               title=message.get("subject") or "Review contractor report"))
        return sorted(result, key=lambda x: -x["priority"])

    def updates(self, project_id):
        record = self.store.projects().get(project_id)
        if record is None:
            raise ValueError("Unknown project.")
        return {"portfolio_revision": self.store.portfolio_revision(), "project_revision": record["project_version"],
                "report_count": len(record["state"].get("contractor_reports", []))}

    def contractor_accounts(self):
        return contractor_bridge.accounts([r["state"] for r in self.store.projects().values()])

    def contractor_login(self, actor_id):
        account = next((a for a in self.contractor_accounts() if a["id"] == actor_id), None)
        if account is None:
            raise PermissionError("Choose a recorded contractor account.")
        token = secrets.token_urlsafe(32)
        with self.job_lock:
            self.contractor_sessions[token] = {"actor_id": actor_id, "expires_at": datetime.now(timezone.utc) + timedelta(hours=12)}
        return {"token": token, "actor": account}

    def contractor_actor(self, token):
        with self.job_lock:
            session = self.contractor_sessions.get(token)
        if not session or session["expires_at"] <= datetime.now(timezone.utc):
            raise PermissionError("Select your contractor account to continue.")
        account = next((a for a in self.contractor_accounts() if a["id"] == session["actor_id"]), None)
        if account is None:
            raise PermissionError("This account no longer has project access.")
        return account

    def contractor_record(self, token, project_id):
        actor = self.contractor_actor(token)
        if project_id not in actor["project_ids"]:
            raise PermissionError("This contractor is not assigned to this project.")
        return actor, self.store.projects()[project_id]

    def contractor_bootstrap(self, token):
        actor = self.contractor_actor(token)
        records = self.store.projects()
        return {"actor": actor, "projects": [contractor_bridge.view(records[p]["state"], actor["id"],
                    records[p]["project_version"], self.vendor_context(records[p]["state"])) for p in actor["project_ids"]],
                "portfolio_revision": self.store.portfolio_revision(),
                "runtime": {"authenticated": self.auth["authenticated"], "detail": self.auth["detail"]}}

    def contractor_action(self, token, payload):
        with self.store.lock:
            actor, record = self.contractor_record(token, payload.get("project_id"))
            if payload.get("expected_project_version") != record["project_version"]:
                raise Conflict("This project changed. Refresh before submitting your update.")
            action = payload.get("action")
            if not isinstance(action, dict):
                raise ValueError("A structured contractor action is required.")
            updated, blobs = contractor_bridge.apply(record["state"], action, actor["id"], self.vendor_context(record["state"]))
            if updated != record["state"]:
                self.store.write_project(updated, record["project_version"], attachments=blobs)
            previous = {m["id"] for m in record["state"].get("operations", {}).get("messages", [])}
            new_messages = [m["id"] for m in updated.get("operations", {}).get("messages", []) if m["id"] not in previous]
        result = self.contractor_bootstrap(token)
        if new_messages and self.auth["authenticated"]:
            try:
                result["summary_job"] = self.submit_project_summary(payload["project_id"], new_messages[-1], actor["id"])
            except Conflict:
                result["summary_status"] = "A model job is busy. The original report is saved; the PM can request a summary."
        return result

    def contractor_attachment(self, token, project_id, identity):
        actor, record = self.contractor_record(token, project_id)
        view = contractor_bridge.view(record["state"], actor["id"], record["project_version"], self.vendor_context(record["state"]))
        visible = [r["message"] for r in view["reports"]] + view.get("linked_messages", [])
        referenced = any(a.get("id") == identity for m in visible for a in m.get("attachments", []))
        if not referenced:
            raise PermissionError("This attachment is not available to this contractor.")
        return self.store.attachment(identity, record["state"]["project"]["id"])

    def submit_project_summary(self, project_id, message_id, actor_id):
        record = self.store.projects()[project_id]
        message = messages.find(record["state"], message_id)
        attachments = [self.store.attachment(a["id"], record["state"]["project"]["id"]) for a in message.get("attachments", [])]
        if any(a is None for a in attachments):
            raise ValueError("An original attachment is missing.")
        with self.job_lock:
            if any(j["status"] == "running" for j in self.jobs.values()):
                raise Conflict("Another model job is running.")
            job_id = secrets.token_hex(8)
            self.jobs[job_id] = {"status": "running", "kind": "contractor-summary", "mode": "live", "actor_id": actor_id,
                                 "project_id": project_id, "message_id": message_id, "started_at": datetime.now(timezone.utc).isoformat()}
        def work():
            try:
                output = llm.summarize_message(record["state"], message, attachments)
                with self.store.lock:
                    current = self.store.projects()[project_id]
                    if current["project_version"] != record["project_version"]:
                        raise Conflict("Project changed during analysis. Original report is saved; request a fresh summary.")
                    updated = messages.apply_analysis(current["state"], message_id, output, self.vendor_context(current["state"]))
                    self.store.write_project(updated, current["project_version"], operation="contractor_message_analysis")
                with self.job_lock:
                    self.jobs[job_id].update(status="completed")
            except Exception as exc:
                with self.job_lock:
                    self.jobs[job_id].update(status="failed", error=str(exc))
        self.pool.submit(work)
        return {"job_id": job_id}

    def mutate(self, path, payload):
        with self.store.lock:
            record = self.store.read()
            if path != "/api/reset" and "expected_version" not in payload:
                raise Conflict("An action must include the screen's session version. Refresh and try again.")
            expected = payload.get("expected_version", record["version"])
            if expected != record["version"]:
                raise Conflict("This screen is out of date. Refresh before applying this action.")
            state, cursor = record["state"], record["cursor"]
            attachments = []
            if path == "/api/projects/select":
                self.store.activate_project(payload.get("project_id"), expected=expected)
                return self.bootstrap()
            elif path == "/api/projects/reset":
                project_id = payload.get("project_id")
                if project_id not in {p["id"] for p in projects.list_projects()}:
                    raise ValueError("Unknown demo project.")
                state, attachments = self.initialize_workspace(projects.initial_state(project_id))
                cursor = 0
            elif path == "/api/reset":
                scenario_id = payload.get("scenario_id", scenarios.list_scenarios()[0]["id"])
                if scenario_id not in {s["id"] for s in scenarios.list_scenarios()}:
                    raise ValueError("Unknown scenario.")
                state, cursor = scenarios.initial_state(scenario_id), 0
            elif path == "/api/event":
                project_id = state["project"].get("demo_project_id")
                event = projects.next_event(project_id, cursor, state) if project_id else scenarios.next_event(state["project"]["scenario_id"], cursor, state)
                if event is None:
                    raise ValueError("No further project update is ready at this stage. Resolve current work and requests before advancing the story.")
                state = engine.apply_event(state, event)
                cursor += 1
            elif path == "/api/clock":
                deadline = next_response_deadline(state)
                if deadline is None:
                    raise ValueError("No future response deadline is recorded for an open request.")
                state = engine.apply_event(state, {"id": "sim-clock-" + str(record["version"]),
                    "type": "clock_advance", "at": deadline,
                    "summary": "Simulation clock advanced to an observed response deadline; no approval or work was inferred."})
            elif path == "/api/respond":
                request = next((r for r in state["requests"] if r["id"] == payload.get("request_id")), None)
                if request is None:
                    raise ValueError("Unknown request.")
                if request.get("status") in {"answered", "completed", "resolved", "closed"}:
                    raise ValueError("This request already has a response.")
                event = projects.actor_response(state, request) if state["project"].get("demo_project_id") else scenarios.actor_response(state, request)
                if event is None:
                    raise ValueError("No simulated response is currently available for this request.")
                state = engine.apply_event(state, event)
            elif path == "/api/action":
                action = payload.get("action")
                if not isinstance(action, dict) or not isinstance(action.get("type"), str):
                    raise ValueError("A structured action with a type is required.")
                # UI decisions explicitly simulate the named authority. Model output never
                # gets this route automatically; its allowed actions are validated in llm.py.
                actor = payload.get("actor_id", "coordinator") if action["type"] == "resolve_decision" else "coordinator"
                state = engine.apply_action(state, action, actor_id=actor)
            elif path in {"/api/operations", "/api/operations/respond"}:
                operation = payload.get("operation")
                if not isinstance(operation, dict) or not isinstance(operation.get("type"), str):
                    raise ValueError("A structured operation is required.")
                actor = "pm"
                if path.endswith("/respond"):
                    actor = payload.get("actor_id")
                    commercial = actor == "commercial" and operation["type"] in {"simulate_authority_response", "approve_and_commit", "approve_proposal"}
                    counterpart = actor in {v["id"] for v in self.store.vendors()} and operation["type"] in {"confirm_booking", "receive_vendor_reply"}
                    if operation["type"] == "confirm_booking":
                        booking = next((b for b in state.get("operations", {}).get("bookings", [])
                                        if b["id"] == operation.get("booking_id")), None)
                        counterpart = bool(booking and actor == booking.get("recipient_id") and
                                           actor in {s["id"] for s in state["stakeholders"]})
                    if not (commercial or counterpart):
                        raise ValueError("The demo responder must be the named commercial approver or vendor counterpart for this operation.")
                state = operations.apply(state, operation, actor_id=actor, vendor_profiles=self.vendor_context(state))
            elif path == "/api/messages":
                state, attachments, message_id = messages.prepare(state, payload, self.vendor_context(state))
            else:
                raise ValueError("Unknown mutation.")
            self.store.write(state, cursor, expected=expected, operation=path.removeprefix("/api/"), attachments=attachments)
        return self.bootstrap()

    def submit_summary(self, payload):
        if not self.auth["authenticated"]:
            raise ValueError("Live message analysis requires this machine's ChatGPT/Codex login.")
        record = self.store.read()
        if payload.get("expected_version") != record["version"]:
            raise Conflict("Refresh this message before starting analysis.")
        identity = payload.get("message_id")
        message = messages.find(record["state"], identity)
        attachments = []
        for meta in message.get("attachments", []):
            item = self.store.attachment(meta["id"], record["state"]["project"]["id"])
            if item is None:
                raise ValueError("An original attachment is missing. Restore it before image analysis.")
            attachments.append(item)
        with self.job_lock:
            if any(j["status"] == "running" for j in self.jobs.values()):
                raise Conflict("Another model job is running. Wait for it to finish.")
            job_id = secrets.token_hex(8)
            self.jobs[job_id] = {"status": "running", "kind": "message-summary", "mode": "live",
                                 "started_at": datetime.now(timezone.utc).isoformat(), "message_id": identity}

        def work():
            try:
                result = llm.summarize_message(record["state"], message, attachments)
                with self.store.lock:
                    current = self.store.read()
                    if current["version"] != record["version"]:
                        raise Conflict("The project changed during message analysis. Discarded the result; run it again.")
                    updated = messages.apply_analysis(current["state"], identity, result, self.vendor_context(current["state"]))
                    self.store.write(updated, current["cursor"], expected=current["version"], operation="message_analysis")
                with self.job_lock:
                    self.jobs[job_id].update(status="completed", result=self.bootstrap())
            except Exception as exc:
                with self.job_lock:
                    self.jobs[job_id].update(status="failed", error=str(exc))
        self.pool.submit(work)
        return {"job_id": job_id}

    def submit(self, kind, payload):
        mode = payload.get("mode", "baseline")
        if mode not in {"live", "baseline"}:
            raise ValueError("Mode must be live or baseline.")
        if mode == "live" and not self.auth["authenticated"]:
            raise ValueError("Live reasoning requires Codex signed in with ChatGPT. Run codex login, then restart this local server.")
        ids = payload.get("scenario_ids")
        if ids is not None and (not isinstance(ids, list) or not ids or not set(ids).issubset({s["id"] for s in scenarios.list_scenarios()})):
            raise ValueError("Provide one or more known scenario IDs.")
        suite = payload.get("suite", "scenarios")
        if suite not in {"scenarios", "projects", "challenges"}:
            raise ValueError("Unknown evaluation suite.")
        if suite == "challenges" and mode != "baseline":
            raise ValueError("Challenge replay uses the frozen independent checks. Fresh live probes are recorded separately.")
        project_ids = payload.get("project_ids")
        if project_ids is not None and (not isinstance(project_ids, list) or not project_ids or not set(project_ids).issubset({p["id"] for p in projects.list_projects()})):
            raise ValueError("Provide one or more known demo project IDs.")
        with self.job_lock:
            if any(j["status"] == "running" for j in self.jobs.values()):
                raise Conflict("Another reasoning or evaluation job is running. Wait for it to finish.")
            job_id = secrets.token_hex(8)
            self.jobs[job_id] = {"status": "running", "kind": kind, "mode": mode,
                                 "started_at": datetime.now(timezone.utc).isoformat()}
        record = self.store.read()

        def work():
            try:
                if kind == "decide":
                    decision = llm.decide(copy.deepcopy(record["state"])) if mode == "live" else dict(engine.recommend(record["state"]), mode="baseline")
                    self.store.save_recommendation(decision, expected=record["version"])
                    result = self.bootstrap()
                else:
                    if suite == "challenges":
                        result = challenges.run_suite(mode="baseline", phase="after")
                        result["suite"] = "challenges"
                    else:
                        result = (project_evaluation.run_suite(mode=mode, decide=llm.decide if mode == "live" else None, project_ids=project_ids)
                                  if suite == "projects" else evaluation.run_suite(mode=mode, decide=llm.decide if mode == "live" else None, scenario_ids=ids))
                    self.store.save_report(result)
                with self.job_lock:
                    self.jobs[job_id].update(status="completed", result=result)
            except Exception as exc:
                with self.job_lock:
                    self.jobs[job_id].update(status="failed", error=str(exc))
                traceback.print_exc()
        self.pool.submit(work)
        return {"job_id": job_id}


class Handler(BaseHTTPRequestHandler):
    server_version = "EqoreDemo/" + APP_VERSION

    def log_message(self, fmt, *args):
        if "/api/jobs/" not in str(args):
            super().log_message(fmt, *args)

    def send(self, value, status=200, content_type="application/json; charset=utf-8", attachment=False):
        data = json.dumps(value, ensure_ascii=False).encode() if isinstance(value, (dict, list)) else value
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; frame-ancestors 'self'; base-uri 'none'; form-action 'self'")
        if attachment:
            self.send_header("Content-Disposition", 'attachment; filename="eqore-project-trace.json"')
        self.end_headers()
        self.wfile.write(data)

    def local_request(self, mutation=False):
        port = self.server.server_address[1]
        allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if self.headers.get("Host", "") not in allowed:
            raise PermissionError("Only this local application host is accepted.")
        origin = self.headers.get("Origin")
        if origin and origin not in {f"http://{x}" for x in allowed}:
            raise PermissionError("Cross-origin requests are not accepted.")
        if mutation and self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
            raise PermissionError("Mutations require application/json.")

    def do_GET(self):
        try:
            self.local_request()
            path = urlparse(self.path).path
            query = parse_qs(urlparse(self.path).query)
            if path == "/api/bootstrap":
                return self.send(self.server.app.bootstrap(query.get("project_id", [None])[0]))
            if path == "/api/updates":
                return self.send(self.server.app.updates(query.get("project_id", [None])[0]))
            if path == "/api/contractor/accounts":
                return self.send({"accounts": self.server.app.contractor_accounts()})
            if path == "/api/contractor/bootstrap":
                return self.send(self.server.app.contractor_bootstrap(self.bearer()))
            if path.startswith("/api/contractor/attachments/"):
                parts = path.split("/")
                if len(parts) != 6:
                    raise ValueError("Invalid attachment path.")
                item = self.server.app.contractor_attachment(self.bearer(), parts[4], parts[5])
                return self.send(item["data"], content_type=item["mime_type"]) if item else self.send({"error": "Attachment not found."}, 404)
            if path.startswith("/api/contractor/jobs/"):
                actor = self.server.app.contractor_actor(self.bearer())
                with self.server.app.job_lock:
                    job = copy.deepcopy(self.server.app.jobs.get(path.rsplit("/", 1)[1]))
                if not job or job.get("actor_id") != actor["id"]:
                    return self.send({"error": "Unknown job."}, 404)
                return self.send(job)
            if path == "/api/health":
                return self.send({"ok": True, "version": APP_VERSION})
            if path == "/api/export":
                record = self.server.app.store.read()
                operation_view = workspace.public(operations.summarize(record["state"], self.server.app.vendor_context(record["state"])))
                return self.send({"state": record["state"], "recommendation": record["recommendation"],
                                  "dashboard": workspace.finance(dashboard.summarize(record["state"]), record["state"], operation_view),
                                  "operations": operation_view,
                                  "calendar": workspace.calendar(record["state"], operation_view),
                                  "phases": phases.summarize(record["state"]),
                                  "previous_world_versions": self.server.app.store.archives(record["state"]["project"].get("demo_project_id")),
                                  "reasoning_history": self.server.app.store.reasoning(limit=1000, include_context=True, project_id=record["state"]["project"]["id"]),
                                  "synthetic": True, "exported_at": datetime.now(timezone.utc).isoformat()}, attachment=True)
            if path.startswith("/api/jobs/"):
                with self.server.app.job_lock:
                    job = copy.deepcopy(self.server.app.jobs.get(path.rsplit("/", 1)[1]))
                return self.send(job if job else {"error": "Unknown job."}, 200 if job else 404)
            if path.startswith("/api/attachments/"):
                state = self.server.app.store.read()["state"]
                selector = query.get("project_id", [None])[0]
                if selector:
                    snapshot = self.server.app.store.projects().get(selector)
                    if snapshot is None:
                        raise ValueError("Unknown project.")
                    state = snapshot["state"]
                identity = path.rsplit("/", 1)[1]
                referenced = any(a.get("id") == identity for m in state.get("operations", {}).get("messages", [])
                                 for a in m.get("attachments", []))
                item = self.server.app.store.attachment(identity, state["project"]["id"]) if referenced else None
                if item is None:
                    return self.send({"error": "Attachment not found in this project."}, 404)
                return self.send(item["data"], content_type=item["mime_type"])
            # Exact allowlist: database, fixtures and private oracle are never served.
            assets = {"/": "index.html", "/index.html": "index.html", "/styles.css": "styles.css", "/pm.css": "pm.css", "/app.js": "app.js",
                      "/contractor.html": "contractor.html", "/contractor.js": "contractor.js", "/contractor.css": "contractor.css",
                      "/legacy.html": "legacy.html", "/legacy.js": "legacy.js", "/legacy.css": "legacy.css",
                      "/map.svg": "map.svg", "/field-note.svg": "field-note.svg"}
            if path not in assets:
                return self.send({"error": "Not found."}, 404)
            file = ROOT / "web" / assets[path]
            self.send(file.read_bytes(), content_type=(mimetypes.guess_type(str(file))[0] or "application/octet-stream") + "; charset=utf-8")
        except PermissionError as exc:
            self.send({"error": str(exc)}, 403)
        except (ValueError, KeyError, TypeError) as exc:
            self.send({"error": str(exc)}, 400)
        except Exception as exc:
            self.send({"error": str(exc)}, 500)

    def do_POST(self):
        try:
            self.local_request(mutation=True)
            path = urlparse(self.path).path
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > (23_000_000 if path in {"/api/messages", "/api/contractor/action"} else 256_000):
                raise ValueError("Invalid request size.")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("Request must be an object.")
            path = urlparse(self.path).path
            if path == "/api/contractor/login":
                result = self.server.app.contractor_login(payload.get("actor_id"))
            elif path == "/api/contractor/action":
                result = self.server.app.contractor_action(self.bearer(), payload)
            elif path == "/api/contractor/logout":
                with self.server.app.job_lock:
                    self.server.app.contractor_sessions.pop(self.bearer(), None)
                result = {"ok": True}
            elif path in {"/api/decide", "/api/evaluate"}:
                result = self.server.app.submit(path.removeprefix("/api/"), payload)
            elif path == "/api/message-summary":
                result = self.server.app.submit_summary(payload)
            elif path in {"/api/reset", "/api/action", "/api/event", "/api/clock", "/api/respond", "/api/projects/select", "/api/projects/reset", "/api/messages", "/api/operations", "/api/operations/respond"}:
                result = self.server.app.mutate(path, payload)
            else:
                return self.send({"error": "Not found."}, 404)
            self.send(result)
        except PermissionError as exc:
            self.send({"error": str(exc)}, 403)
        except Conflict as exc:
            self.send({"error": str(exc)}, 409)
        except (ValueError, KeyError, TypeError, engine.DomainError) as exc:
            self.send({"error": str(exc)}, 400)
        except Exception as exc:
            traceback.print_exc()
            self.send({"error": str(exc)}, 500)

    def bearer(self):
        header = self.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            raise PermissionError("A contractor session is required.")
        return header[7:]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--db", default=str(ROOT / "data" / "eqore.sqlite3"))
    args = parser.parse_args()
    app = Application(args.db)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.app = app
    print(f"EQORE demo: http://127.0.0.1:{args.port}  |  {app.auth['detail']}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        app.pool.shutdown(wait=False, cancel_futures=True)


if __name__ == "__main__":
    main()
