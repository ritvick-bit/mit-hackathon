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
from urllib.parse import urlparse

import engine
import dashboard
import evaluation
import llm
import projects
import project_evaluation
import challenges
import phases
import scenarios
from storage import Conflict, Store

ROOT = Path(__file__).resolve().parent
APP_VERSION = "0.4.0"
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
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="eqore-job")
        self.auth = llm.runtime_status(check_auth=True)
        catalog = projects.list_projects()
        added = self.store.ensure_projects([projects.initial_state(p["id"]) for p in catalog])
        if self.store.read() is None or added == len(catalog):
            self.store.write(self.store.projects()[catalog[0]["id"]]["state"], operation="initialize_projects")
        self.store.refresh_pristine_projects([projects.initial_state(p["id"]) for p in catalog])

    def bootstrap(self):
        record = self.store.read()
        state = record["state"]
        runtime = llm.runtime_status()
        runtime.update(authenticated=self.auth["authenticated"], detail=self.auth["detail"])
        recommendation = record["recommendation"]
        if recommendation is None:
            recommendation = dict(engine.recommend(state), mode="baseline")
        analysis = engine.analyze(state)
        overview = dashboard.summarize(state, analysis)
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
            catalog.append(dict(project, metrics=metrics,
                                current_phase_titles=project_phases["active_phase_titles"], phase_summary=phase_summary,
                                selected=project["id"] == state["project"].get("demo_project_id")))
        return {"version": APP_VERSION, "state": state, "session_version": record["version"],
                "analysis": analysis, "dashboard": overview, "projects": catalog,
                "phases": phase_view, "workflow_review": knowledge.get("workflow_review", {}),
                "mode": "project" if state["project"].get("demo_project_id") else "scenario",
                "recommendation": recommendation,
                "scenarios": scenarios.list_scenarios(), "sources": scenarios.sources(),
                "runtime": runtime, "evaluations": [r for r in self.store.reports(50) if r.get("suite") != "challenges"][:10],
                "challenge_design": challenges.load_design(),
                "challenge_reports": [r for r in self.store.reports(50) if r.get("suite") == "challenges"],
                "simulation": {"next_response_at": next_response_deadline(state)},
                "reasoning_history": self.store.reasoning(project_id=state["project"]["id"]),
                "capabilities": [{"id": i, "title": t, "status": "demo", "description": d} for i, t, d in CAPABILITIES]}

    def mutate(self, path, payload):
        with self.store.lock:
            record = self.store.read()
            if path != "/api/reset" and "expected_version" not in payload:
                raise Conflict("An action must include the screen's session version. Refresh and try again.")
            expected = payload.get("expected_version", record["version"])
            if expected != record["version"]:
                raise Conflict("This screen is out of date. Refresh before applying this action.")
            state, cursor = record["state"], record["cursor"]
            if path == "/api/projects/select":
                self.store.activate_project(payload.get("project_id"), expected=expected)
                return self.bootstrap()
            elif path == "/api/projects/reset":
                project_id = payload.get("project_id")
                if project_id not in {p["id"] for p in projects.list_projects()}:
                    raise ValueError("Unknown demo project.")
                state, cursor = projects.initial_state(project_id), 0
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
            else:
                raise ValueError("Unknown mutation.")
            self.store.write(state, cursor, expected=expected, operation=path.removeprefix("/api/"))
        return self.bootstrap()

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
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'self'; base-uri 'none'; form-action 'self'")
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
            if path == "/api/bootstrap":
                return self.send(self.server.app.bootstrap())
            if path == "/api/health":
                return self.send({"ok": True, "version": APP_VERSION})
            if path == "/api/export":
                record = self.server.app.store.read()
                return self.send({"state": record["state"], "recommendation": record["recommendation"],
                                  "dashboard": dashboard.summarize(record["state"]),
                                  "phases": phases.summarize(record["state"]),
                                  "previous_world_versions": self.server.app.store.archives(record["state"]["project"].get("demo_project_id")),
                                  "reasoning_history": self.server.app.store.reasoning(limit=1000, include_context=True, project_id=record["state"]["project"]["id"]),
                                  "synthetic": True, "exported_at": datetime.now(timezone.utc).isoformat()}, attachment=True)
            if path.startswith("/api/jobs/"):
                with self.server.app.job_lock:
                    job = copy.deepcopy(self.server.app.jobs.get(path.rsplit("/", 1)[1]))
                return self.send(job if job else {"error": "Unknown job."}, 200 if job else 404)
            # Exact allowlist: database, fixtures and private oracle are never served.
            assets = {"/": "index.html", "/index.html": "index.html", "/styles.css": "styles.css", "/app.js": "app.js"}
            if path not in assets:
                return self.send({"error": "Not found."}, 404)
            file = ROOT / "web" / assets[path]
            self.send(file.read_bytes(), content_type=(mimetypes.guess_type(str(file))[0] or "application/octet-stream") + "; charset=utf-8")
        except PermissionError as exc:
            self.send({"error": str(exc)}, 403)
        except Exception as exc:
            self.send({"error": str(exc)}, 500)

    def do_POST(self):
        try:
            self.local_request(mutation=True)
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 256_000:
                raise ValueError("Invalid request size.")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("Request must be an object.")
            path = urlparse(self.path).path
            if path in {"/api/decide", "/api/evaluate"}:
                result = self.server.app.submit(path.removeprefix("/api/"), payload)
            elif path in {"/api/reset", "/api/action", "/api/event", "/api/clock", "/api/respond", "/api/projects/select", "/api/projects/reset"}:
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
