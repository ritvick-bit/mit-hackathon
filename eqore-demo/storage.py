"""Transactional local snapshots. Simulator internals are never stored in the UI state."""
import json
import hashlib
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path


class Conflict(Exception):
    pass


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS session (
                    id INTEGER PRIMARY KEY CHECK(id=1), version INTEGER NOT NULL,
                    state TEXT NOT NULL, cursor INTEGER NOT NULL,
                    recommendation TEXT
                );
                CREATE TABLE IF NOT EXISTS reports (
                    id TEXT PRIMARY KEY, created_at TEXT NOT NULL, payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL,
                    version INTEGER NOT NULL, operation TEXT NOT NULL, snapshot TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reasoning (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL,
                    version INTEGER NOT NULL, payload TEXT NOT NULL, observed_state TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS project_snapshots (
                    project_id TEXT PRIMARY KEY, state TEXT NOT NULL,
                    cursor INTEGER NOT NULL, recommendation TEXT
                );
                CREATE TABLE IF NOT EXISTS project_archives (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL,
                    archived_at TEXT NOT NULL, record TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS vendor_profiles (
                    id TEXT PRIMARY KEY, payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS attachments (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                    name TEXT NOT NULL, mime_type TEXT NOT NULL,
                    sha256 TEXT NOT NULL, data BLOB NOT NULL
                );
                CREATE TABLE IF NOT EXISTS workspaces (
                    id TEXT PRIMARY KEY, version INTEGER NOT NULL, payload TEXT NOT NULL
                );
            """)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        return db

    def ensure_workspace(self, identity, initial):
        with self.lock, self.connect() as db:
            db.execute("INSERT OR IGNORE INTO workspaces VALUES(?,1,?)", (identity, json.dumps(initial)))

    def read_workspace(self, identity):
        with self.connect() as db:
            row = db.execute("SELECT version,payload FROM workspaces WHERE id=?", (identity,)).fetchone()
        if row is None:
            raise ValueError("Unknown workspace.")
        return {"version": row["version"], "state": json.loads(row["payload"])}

    def write_workspace(self, identity, state, expected):
        with self.lock, self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT version FROM workspaces WHERE id=?", (identity,)).fetchone()
            if not row or row["version"] != expected:
                raise Conflict("Paperwork changed while you were reviewing it. Refresh and review the current record before trying again.")
            version = expected + 1
            db.execute("UPDATE workspaces SET version=?,payload=? WHERE id=?", (version, json.dumps(state, ensure_ascii=False), identity))
        return version

    def seed_vendors(self, profiles):
        with self.lock, self.connect() as db:
            for profile in profiles:
                db.execute("INSERT OR IGNORE INTO vendor_profiles VALUES(?,?)",
                           (profile["id"], json.dumps(profile)))

    def vendors(self):
        with self.connect() as db:
            return [json.loads(row[0]) for row in db.execute("SELECT payload FROM vendor_profiles ORDER BY id")]

    def enrich_projects(self, transform):
        """Add new observed records at startup without resetting saved progress."""
        with self.lock, self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            for row in db.execute("SELECT * FROM project_snapshots").fetchall():
                original = json.loads(row["state"])
                updated = transform(original)
                if isinstance(updated, tuple):
                    updated, attachments = updated
                    self._write_attachments(db, attachments, updated["project"]["id"])
                if updated != original:
                    db.execute("UPDATE project_snapshots SET state=?,recommendation=NULL WHERE project_id=?",
                               (json.dumps(updated), row["project_id"]))
            current = db.execute("SELECT * FROM session WHERE id=1").fetchone()
            if current:
                original = json.loads(current["state"])
                updated = transform(original)
                if isinstance(updated, tuple):
                    updated, attachments = updated
                    self._write_attachments(db, attachments, updated["project"]["id"])
                if updated != original:
                    version = current["version"] + 1
                    serialized = json.dumps(updated)
                    db.execute("UPDATE session SET state=?,version=?,recommendation=NULL WHERE id=1", (serialized, version))
                    db.execute("INSERT INTO history(at,version,operation,snapshot) VALUES(?,?,?,?)",
                               (datetime.now(timezone.utc).isoformat(), version, "initialize_pm_workspace", serialized))

    def attachment(self, identity, project_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM attachments WHERE id=? AND project_id=?", (identity, project_id)).fetchone()
        return dict(row) if row else None

    @staticmethod
    def _write_attachments(db, attachments, project_id):
        for item in attachments:
            if item["project_id"] != project_id:
                raise ValueError("Attachment belongs to a different project.")
            prior = db.execute("SELECT sha256 FROM attachments WHERE id=?", (item["id"],)).fetchone()
            if prior and prior[0] != item["sha256"]:
                raise ValueError("An original attachment cannot be overwritten.")
            db.execute("INSERT OR IGNORE INTO attachments VALUES(?,?,?,?,?,?)",
                       tuple(item[k] for k in ("id", "project_id", "name", "mime_type", "sha256", "data")))

    def read(self):
        with self.connect() as db:
            row = db.execute("SELECT * FROM session WHERE id=1").fetchone()
        if row is None:
            return None
        return {"version": row["version"], "state": json.loads(row["state"]),
                "cursor": row["cursor"], "recommendation": json.loads(row["recommendation"]) if row["recommendation"] else None}

    def ensure_projects(self, states):
        """Seed missing demo worlds without resetting any existing project."""
        added = 0
        with self.lock, self.connect() as db:
            for state in states:
                added += db.execute("INSERT OR IGNORE INTO project_snapshots VALUES(?,?,0,NULL)",
                                    (state["project"]["demo_project_id"], json.dumps(state))).rowcount
        return added

    def projects(self):
        with self.connect() as db:
            rows = db.execute("SELECT * FROM project_snapshots ORDER BY project_id").fetchall()
        return {row["project_id"]: {"state": json.loads(row["state"]), "cursor": row["cursor"],
                                   "project_version": self.snapshot_version(json.loads(row["state"]), row["cursor"]),
                                   "recommendation": json.loads(row["recommendation"]) if row["recommendation"] else None}
                for row in rows}

    @staticmethod
    def snapshot_version(state, cursor=0):
        payload = json.dumps({"state": state, "cursor": cursor}, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()

    def portfolio_revision(self):
        versions = {key: record["project_version"] for key, record in self.projects().items()}
        return hashlib.sha256(json.dumps(versions, sort_keys=True).encode()).hexdigest()

    def write_project(self, state, expected_project_version, operation="contractor_update", attachments=()):
        """Mutate one project atomically without changing another PM's selected project."""
        project_id = state["project"]["demo_project_id"]
        with self.lock, self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM project_snapshots WHERE project_id=?", (project_id,)).fetchone()
            if not row:
                raise ValueError("Unknown project.")
            prior = json.loads(row["state"])
            if prior["project"]["id"] != state["project"]["id"]:
                raise ValueError("Project identity cannot be changed.")
            if expected_project_version != self.snapshot_version(prior, row["cursor"]):
                raise Conflict("This project changed. Refresh the contractor portal before submitting again.")
            self._write_attachments(db, attachments, state["project"]["id"])
            payload = json.dumps(state, ensure_ascii=False)
            db.execute("UPDATE project_snapshots SET state=?,recommendation=NULL WHERE project_id=?", (payload, project_id))
            current = db.execute("SELECT * FROM session WHERE id=1").fetchone()
            version = current["version"] if current else 0
            if current and json.loads(current["state"])["project"].get("demo_project_id") == project_id:
                version += 1
                db.execute("UPDATE session SET state=?,version=?,recommendation=NULL WHERE id=1", (payload, version))
            db.execute("INSERT INTO history(at,version,operation,snapshot) VALUES(?,?,?,?)",
                       (datetime.now(timezone.utc).isoformat(), version, operation, payload))
        return self.snapshot_version(state, row["cursor"])

    def refresh_pristine_projects(self, states):
        """Upgrade untouched demo openings; archive their prior worlds and never erase progress."""
        refreshed = []
        with self.lock:
            current = self.read()
            records = self.projects()
            for state in states:
                project_id = state["project"]["demo_project_id"]
                old = records.get(project_id)
                if not old or old["state"]["project"].get("world_version") == state["project"].get("world_version"):
                    continue
                if old["cursor"] or any(old["state"].get(k) for k in ("audit", "events", "requests", "proposals")):
                    continue
                if self.has_workspace_progress(old["state"]):
                    continue
                with self.connect() as db:
                    db.execute("INSERT INTO project_archives(project_id,archived_at,record) VALUES(?,?,?)",
                               (project_id, datetime.now(timezone.utc).isoformat(), json.dumps(old)))
                    db.execute("UPDATE project_snapshots SET state=?,cursor=0,recommendation=NULL WHERE project_id=?",
                               (json.dumps(state), project_id))
                if current and current["state"]["project"].get("demo_project_id") == project_id:
                    self.write(state, expected=current["version"], operation="refresh_demo_world")
                    current = self.read()
                refreshed.append(project_id)
        return refreshed

    @staticmethod
    def has_workspace_progress(state):
        """Opening fixtures may upgrade; submitted reports and vendor work may not."""
        if state.get("contractor_reports"):
            return True
        ops = state.get("operations", {})
        seeded_messages = {"message-case-harbor-rigging", "message-case-millbrook-utility",
                           "message-case-riverbend-electrical", "message-riverbend-illustrative-field-note"}
        return (any(ops.get(key) for key in ("replies", "proposals", "decisions", "bookings")) or
                any(m["id"] not in seeded_messages or m.get("summary") for m in ops.get("messages", [])) or
                any(entry.get("action") != "ingest_message" for entry in ops.get("audit", [])))

    def archives(self, project_id):
        with self.connect() as db:
            rows = db.execute("SELECT * FROM project_archives WHERE project_id=? ORDER BY id DESC", (project_id,)).fetchall()
        return [{"archived_at": row["archived_at"], **json.loads(row["record"])} for row in rows]

    def activate_project(self, project_id, expected):
        with self.lock:
            record = self.projects().get(project_id)
            if record is None:
                raise ValueError("Unknown demo project.")
            return self.write(record["state"], record["cursor"], record["recommendation"],
                              expected=expected, operation="select_project")

    def write(self, state, cursor=0, recommendation=None, expected=None, operation="update", attachments=()):
        with self.lock, self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT version FROM session WHERE id=1").fetchone()
            current = row[0] if row else 0
            if expected is not None and current != expected:
                raise Conflict("Project changed while this operation was running. Review the current state and run it again.")
            self._write_attachments(db, attachments, state["project"]["id"])
            version = current + 1
            payload = json.dumps(state, ensure_ascii=False)
            db.execute("INSERT OR REPLACE INTO session VALUES(1,?,?,?,?)",
                       (version, payload, cursor, json.dumps(recommendation) if recommendation else None))
            db.execute("INSERT INTO history(at,version,operation,snapshot) VALUES(?,?,?,?)",
                       (datetime.now(timezone.utc).isoformat(), version, operation, payload))
            project_id = state["project"].get("demo_project_id")
            if project_id:
                db.execute("INSERT OR REPLACE INTO project_snapshots VALUES(?,?,?,?)",
                           (project_id, payload, cursor, json.dumps(recommendation) if recommendation else None))
        return version

    def save_recommendation(self, recommendation, expected):
        # A recommendation is not a project mutation, but must bind to the exact snapshot.
        with self.lock, self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT version,state FROM session WHERE id=1").fetchone()
            if not row or row[0] != expected:
                raise Conflict("The project changed during model reasoning. This recommendation was discarded; run reasoning again.")
            db.execute("UPDATE session SET recommendation=? WHERE id=1", (json.dumps(recommendation),))
            project_id = json.loads(row[1])["project"].get("demo_project_id")
            if project_id:
                db.execute("UPDATE project_snapshots SET recommendation=? WHERE project_id=?",
                           (json.dumps(recommendation), project_id))
            db.execute("INSERT INTO reasoning(created_at,version,payload,observed_state) VALUES(?,?,?,?)",
                       (datetime.now(timezone.utc).isoformat(), expected, json.dumps(recommendation), row[1]))

    def reasoning(self, limit=10, include_context=False, project_id=None):
        with self.connect() as db:
            rows = db.execute("SELECT * FROM reasoning ORDER BY id DESC").fetchall()
        result = []
        for row in rows:
            observed = json.loads(row["observed_state"])
            if project_id is not None and observed["project"]["id"] != project_id:
                continue
            item = {"id": row["id"], "created_at": row["created_at"], "session_version": row["version"],
                    "project_id": observed["project"]["id"], "scenario_id": observed["project"].get("scenario_id"),
                    "recommendation": json.loads(row["payload"])}
            if include_context:
                item["observed_state"] = observed
            result.append(item)
            if len(result) >= limit:
                break
        return result

    def save_report(self, report):
        with self.lock, self.connect() as db:
            db.execute("INSERT OR REPLACE INTO reports VALUES(?,?,?)",
                       (report["id"], report["created_at"], json.dumps(report)))

    def reports(self, limit=10):
        with self.connect() as db:
            return [json.loads(row[0]) for row in db.execute(
                "SELECT payload FROM reports ORDER BY created_at DESC LIMIT ?", (limit,))]
