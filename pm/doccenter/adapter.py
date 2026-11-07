"""Connects Yichang's document center (paperwork.py, paperwork_api.py and friends, copied unchanged from
eqore-demo on branch codex/paperwork-coordination @ 1d6abe2) to the PM platform.

What this adapter changes, without editing his modules:
  * Identity comes from the PM platform's sign-in cookie instead of his profile picker.
  * Storage is a JSON file in pm/data/ instead of eqore-demo's SQLite database.
  * Projects are the PM platform's JOB-* projects. The browser sends a seed plan for each project the first
    time a PM opens the platform (dates come from the platform's schedule); after that his records are the
    single source of truth for documents.
  * His 20-document template (D01-D20) plus product paperwork and documents the PM adds.
  * OAuth callbacks point at this server's port, and a Google-signed-in PM's Gmail token is used for his
    Gmail draft and reply-sync features.
"""
import copy
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import llm
import paperwork
import signing
import paperwork_oauth
from engine import DomainError
from paperwork_api import PaperworkService
from paperwork_connectors import PaperworkConnectors
from storage import Conflict, JsonStore

ROLES = list(paperwork.ROLE_PROFILES)
TEMPLATE = {row[0]: row for row in paperwork.TEMPLATE}
KINDS = {"esign", "review", "record"}
ID = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")


def _iso(value, label):
    """A date (YYYY-MM-DD, end of that work day Eastern) or a full ISO timestamp with timezone."""
    if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        value = value + "T17:00:00-05:00"
    paperwork._dt(value)
    return value


def _person(identity, name, role, organization, email, company_id=None):
    return {"id": identity, "name": str(name)[:120], "role": str(role)[:120], "organization": str(organization)[:160],
            "email": str(email)[:254], "company_id": company_id}


def _document(project, doc_id, title, kind, phase, owner_id, recipient_ids, prereqs, due_at, created_at, extra):
    people = {p["id"]: p for p in project["stakeholders"]}
    recipients = [{"id": r, "name": people[r]["name"], "role": people[r]["role"], "status": "pending",
                   "signed_at": None, "responded_at": None, "source_event_id": None} for r in recipient_ids]
    doc = {"id": doc_id, "title": title, "kind": kind, "phase": phase, "owner_id": owner_id,
           "recipient_ids": list(recipient_ids), "recipients": recipients, "prerequisite_ids": list(prereqs),
           "dependency_revisions": {}, "due_at": due_at, "status": "ready", "revision": 1, "revisions": [],
           "source_event_ids": [],
           "body": "For %s: coordinate %s against the current issued scope and listed prerequisite records. Confirm the responsible parties and exceptions before dispatch.\n\nIllustrative draft for review; no external delivery or engineering approval is implied." % (project["name"], title.lower()),
           "envelope_id": None, "envelope_status": "created", "provider": "local_sample", "source_mode": "sample",
           "provider_recipient_map": {}, "created_at": created_at, "sent_at": None, "completed_at": None,
           "completion_record": None, "return_reason": None, "email_draft": None, "summary": None, "provider_observations": [],
           "authority_effect": "Coordinates the stated record only; does not grant construction, engineering or operating authority.",
           "template_note": "Illustrative post-signing requirement; site scope and the responsible authority determine actual required records."}
    doc.update(extra)
    return doc


def stakeholder_for(project, who):
    """A stakeholder id from an existing stakeholder id, or a company (added to the project if new)."""
    if not isinstance(who, dict):
        raise DomainError("Choose who the document is waiting on.")
    if who.get("stakeholder_id"):
        return paperwork._stakeholder(project, who["stakeholder_id"])["id"]
    company = who.get("company_id")
    if not isinstance(company, str) or not ID.match(company):
        raise DomainError("Choose who the document is waiting on.")
    found = next((p for p in project["stakeholders"] if p.get("company_id") == company), None)
    if found:
        return found["id"]
    person = _person(f"{project['id']}__c_{company}", paperwork._text(who.get("name"), "Contact name", 120), who.get("role") or "Contractor",
                     who.get("organization") or who.get("name"), who.get("email") or "", company)
    project["stakeholders"].append(person)
    return person["id"]


def seed_project(state, pm_id, plan, now):
    """Builds one paperwork project from the platform's plan, replaying completed documents as sample evidence."""
    pid = plan.get("id")
    if not isinstance(pid, str) or not re.fullmatch(r"JOB-\d{3}", pid):
        raise ValueError("Unknown project id.")
    pm = next(p for p in state["pms"] if p["id"] == pm_id)
    people = [_person(pm_id, pm["name"], "Deployment PM", "EQORE", pm.get("email", ""))]
    given = plan.get("stakeholders") or {}
    for role in ROLES:
        s = given.get(role) or {}
        name, label, org = paperwork.ROLE_PROFILES[role]
        people.append(_person(f"{pid}__{role}", s.get("name") or name, s.get("role") or label, s.get("organization") or org,
                              s.get("email") or f"{role}@{pid.lower()}.demo.example", s.get("company_id")))
    project = {"id": pid, "name": str(plan.get("name") or pid)[:160], "site": str(plan.get("site") or "")[:160], "pm_id": pm_id,
               "status": "active", "version": 1, "paperwork_only": True, "stakeholders": people, "documents": [], "history": [],
               "emails": [], "signed_history": [], "source_events": [], "last_activity": now, "closeout_attestation": None,
               "profile": copy.deepcopy(plan.get("profile") or {})}
    role_id = lambda role: pm_id if role == "pm" else f"{pid}__{role}"
    rows = plan.get("documents") or []
    earliest = min([r.get("completed_at") or now for r in rows] + [now])
    created = (paperwork._dt(_iso(earliest, "date")) - timedelta(days=7)).isoformat()
    for r in rows:
        doc_id = r.get("id")
        if not isinstance(doc_id, str) or not ID.match(doc_id) or any(d["id"] == doc_id for d in project["documents"]):
            raise ValueError("Invalid or duplicate document id in the plan.")
        extra = {"step": r.get("step"), "product_id": r.get("product_id"), "notes": r.get("notes") or ""}
        if doc_id in TEMPLATE:
            _, title, kind, phase, owner, recipients, prereqs = TEMPLATE[doc_id]
        else:
            title, kind, phase = str(r.get("title", ""))[:200], r.get("kind"), str(r.get("phase") or "Procurement")[:80]
            owner, recipients, prereqs = r.get("owner_role", "pm"), r.get("recipient_roles") or [], r.get("prereqs") or []
            if not title or kind not in KINDS or any(x not in ROLES for x in recipients) or (owner != "pm" and owner not in ROLES):
                raise ValueError(f"Invalid document {doc_id} in the plan.")
        ids = [role_id(x) for x in recipients] + [stakeholder_for(project, w) for w in (r.get("recipients") or [])[:6]]
        project["documents"].append(_document(project, doc_id, title, kind, phase, role_id(owner), list(dict.fromkeys(ids)),
                                              prereqs, _iso(r.get("due_at"), "Due date"), created, extra))
    for doc in project["documents"]:
        unknown = [x for x in doc["prerequisite_ids"] if not any(d["id"] == x for d in project["documents"])]
        doc["prerequisite_ids"] = [x for x in doc["prerequisite_ids"] if x not in unknown]
    state["projects"][pid] = project
    by_id = {r["id"]: r for r in rows}
    # Completed documents: replay a local-sample dispatch and every recipient's response, oldest first.
    done = sorted((r for r in rows if r.get("completed_at")), key=lambda r: _iso(r["completed_at"], "date"))
    for r in done:
        doc = paperwork._doc(project, r["id"])
        at = paperwork._dt(_iso(r["completed_at"], "Completed date"))
        if at > paperwork._dt(now):
            continue
        try:
            state["now"] = (at - timedelta(hours=4)).isoformat()
            paperwork._dispatch(state, project, doc, pm_id)
            state["now"] = at.isoformat()
            for recipient in doc["recipients"]:
                kind = {"esign": "recipient_signed", "review": "review_accepted", "record": "record_received"}[doc["kind"]]
                paperwork._receive(state, project, {"id": f"{pid}-seed-{doc['id']}-{recipient['id']}", "project_id": pid, "doc_id": doc["id"],
                    "revision": 1, "envelope_id": doc["envelope_id"], "type": kind, "actor_id": recipient["id"], "occurred_at": state["now"],
                    "text": f"Opening record: {doc['title']}.", "reference": f"sample-opening:{pid}:{doc['id']}", "source_mode": "sample",
                    "source_kind": "sample_esign" if doc["kind"] == "esign" else "sample_record"})
        except DomainError:
            continue  # a prerequisite was not complete; the document stays open
    state["now"] = now
    # Open documents: the ones under way are sent; some have a partial signature or were returned.
    for r in rows:
        opening = r.get("opening")
        doc = paperwork._doc(project, r["id"])
        if not opening or doc["status"] != "ready":
            continue
        if opening == "draft":
            doc["status"] = "draft"
            continue
        try:
            paperwork._dispatch(state, project, doc, pm_id)
        except DomainError:
            continue
        if opening in ("partial", "returned") and doc["recipients"]:
            first = doc["recipients"][0]
            kind = ("recipient_signed" if opening == "partial" else "recipient_declined") if doc["kind"] == "esign" else \
                   ("review_returned" if doc["kind"] == "review" else "record_returned")
            if opening == "partial" and doc["kind"] != "esign":
                continue
            text = str(r.get("opening_text") or ("First recipient completed; the remaining recipients must still respond." if opening == "partial" else "Returned for correction."))[:2000]
            paperwork._receive(state, project, {"id": f"{pid}-seed-{doc['id']}-opening", "project_id": pid, "doc_id": doc["id"], "revision": 1,
                "envelope_id": doc["envelope_id"], "type": kind, "actor_id": first["id"], "occurred_at": now, "text": text,
                "reference": f"sample-opening-response:{pid}:{doc['id']}", "source_mode": "sample",
                "source_kind": "sample_esign" if doc["kind"] == "esign" else "sample_record"})
            if opening == "returned":
                email = {"id": f"{pid}-{doc['id']}-opening-email", "project_id": pid, "doc_id": doc["id"], "sender_id": first["id"],
                         "subject": "Re: " + doc["title"], "text": text, "occurred_at": now, "source_mode": "sample",
                         "sender_verified": False, "provider_message_id": None}
                email["content_hash"] = paperwork._hash(email)
                project["emails"].append(email)
                paperwork._audit(state, project, "email_received", first["id"], "Original email received; no completion inferred.", doc, email["id"], source_mode="sample")
    return project


class DocCenter(PaperworkService):
    """Yichang's PaperworkService with the PM platform's identity, storage and project seeding."""

    def __init__(self, folder, port, sessions, sessions_lock, pms, google_token=None):
        self.port = port
        self.store = JsonStore(folder)
        self.pool = ThreadPoolExecutor(max_workers=2)
        self.auth = llm.runtime_status()
        self.platform_sessions, self.platform_lock, self.google_token = sessions, sessions_lock, google_token
        self.sessions, self.jobs, self.connection_checks, self.session_connectors = {}, {}, {}, {}
        self.lock = threading.RLock()
        self.connectors = PaperworkConnectors()
        self.oauth = paperwork_oauth.PaperworkOAuth()
        for provider in list(paperwork_oauth.CALLBACKS):
            paperwork_oauth.CALLBACKS[provider] = f"http://localhost:{port}/api/paperwork/oauth/callback/{provider}"
        self.store.ensure_workspace("paperwork", {"schema_version": paperwork.SCHEMA_VERSION, "now": self.now(),
                                                  "pms": [{"id": p["id"], "name": p["name"], "email": p["email"]} for p in pms],
                                                  "projects": {}, "event_receipts": {}, "quarantine": []})

    @staticmethod
    def now():
        return datetime.now(timezone.utc).isoformat()

    def _session(self, token):
        with self.platform_lock:
            return self.platform_sessions.get(token)

    # -- identity: the platform's signed-in PM
    def actor(self, token):
        session = self._session(token)
        if not session:
            raise PermissionError("Your session has ended. Sign in again.")
        return session["pm_id"]

    def client(self, token):
        self.actor(token)
        if token in self.session_connectors:
            return self.session_connectors[token]
        session = self._session(token)
        if session and session.get("mode") == "google" and self.google_token:
            try:
                return PaperworkConnectors({**os.environ, "EQORE_GMAIL_ACCESS_TOKEN": self.google_token(session)})
            except Exception:
                pass
        return self.connectors

    def bootstrap(self, token, project_id=None):
        self.auth = llm.runtime_status()
        return super().bootstrap(token, project_id)

    # -- seeding and the compact feed the rest of the platform reads
    def ensure(self, token, payload):
        pm = self.actor(token)
        plans = payload.get("projects")
        if not isinstance(plans, list) or len(plans) > 60:
            raise ValueError("Send a list of project plans.")
        with self.store.lock:
            record = self.store.read_workspace("paperwork")
            state = copy.deepcopy(record["state"])
            if not any(p["id"] == pm for p in state["pms"]):
                raise PermissionError("Unknown PM portfolio.")
            created = []
            for plan in plans:
                if not isinstance(plan, dict) or plan.get("id") in state["projects"]:
                    continue
                if plan.get("pm_id") != pm:
                    raise PermissionError("A project in the plan is not in your portfolio.")
                seed_project(state, pm, plan, self.now())
                created.append(plan["id"])
            if created:
                state["now"] = self.now()
                self.store.write_workspace("paperwork", state, record["version"])
        return {"created": created}

    def feed(self, token):
        """Every document in the PM's projects, in a compact form for the dashboards, to-dos and popups."""
        pm = self.actor(token)
        record = self.store.read_workspace("paperwork")
        state = copy.deepcopy(record["state"])
        state["now"] = self.now()
        projects = {}
        for project in state["projects"].values():
            if project["pm_id"] != pm:
                continue
            docs = []
            for doc in project["documents"]:
                v = paperwork._document_view(state, project, doc)
                docs.append({k: v.get(k) for k in ("id", "title", "kind", "phase", "status", "lifecycle_status", "owner_id", "owner_name",
                                                   "due_at", "revision", "step", "product_id", "notes", "requirement_id", "sent_at",
                                                   "completed_at", "next_action", "blockers", "priority")}
                            | {"recipients": [{k: r.get(k) for k in ("id", "name", "status", "signed_at", "responded_at")} for r in v["recipients"]],
                               "signed_history": [{k: h.get(k) for k in ("recipient_id", "signed_at", "status", "revision")} for h in v.get("signed_history", [])]})
            projects[project["id"]] = {"status": project["status"], "documents": docs,
                                       "stakeholders": [{k: p.get(k) for k in ("id", "name", "role", "organization", "email", "company_id")} for p in project["stakeholders"]]}
        return {"version": record["version"], "now": state["now"], "projects": projects}

    # -- platform additions to his action set: add a document, edit its details
    def action(self, token, payload):
        act = payload.get("action") if isinstance(payload, dict) else None
        if isinstance(act, dict) and act.get("type") in ("add_document", "edit_document_details", "sign_locally"):
            with self.store.lock:
                pm, record = self.current(token, payload)
                state = copy.deepcopy(record["state"])
                state["now"] = self.now()
                project = paperwork._project(state, pm, act.get("project_id"), writable=True)
                if act["type"] == "add_document":
                    self._add_document(state, project, pm, act)
                elif act["type"] == "sign_locally":
                    self._sign_locally(state, project, pm, act, token)
                else:
                    self._edit_details(state, project, pm, act)
                self.store.write_workspace("paperwork", state, record["version"])
            return self.bootstrap(token, act.get("project_id"))
        return super().action(token, payload)

    def _add_document(self, state, project, pm, act):
        title = paperwork._text(act.get("title"), "Document name", 200)
        kind = act.get("kind") if act.get("kind") in KINDS else "record"
        recipients = list(dict.fromkeys(stakeholder_for(project, w) for w in (act.get("recipients") or [])[:6]))
        if not recipients:
            raise DomainError("Add at least one recipient.")
        doc_id = act.get("doc_id") or "X%02d" % (1 + sum(d["id"].startswith("X") for d in project["documents"]))
        if not ID.match(doc_id) or any(d["id"] == doc_id for d in project["documents"]):
            raise DomainError("That document id is already used.")
        doc = _document(project, doc_id, title, kind, str(act.get("phase") or "Project documents")[:80], pm, recipients, [],
                        _iso(act.get("due_at"), "Due date"), state["now"],
                        {"step": act.get("step"), "product_id": act.get("product_id"), "notes": str(act.get("notes") or "")[:2000], "added_by_pm": True})
        project["documents"].append(doc)
        paperwork._audit(state, project, "document_added", pm, f"Document added by the PM: {title}.", doc)

    def _edit_details(self, state, project, pm, act):
        doc = paperwork._doc(project, act.get("doc_id"))
        changes = []
        if act.get("title") is not None:
            doc["title"] = paperwork._text(act["title"], "Document name", 200); changes.append("name")
        if act.get("due_at"):
            doc["due_at"] = _iso(act["due_at"], "Due date"); changes.append("due date")
        for key in ("notes", "step", "product_id"):
            if key in act:
                doc[key] = (str(act[key])[:2000] if act[key] is not None else None); changes.append(key.replace("_id", "").replace("_", " "))
        paperwork._audit(state, project, "document_details_edited", pm, "PM edited " + (", ".join(changes) or "nothing") + ".", doc)

    # -- signing: in the platform, or through DocuSign (pm/doccenter/signing.py)
    def _pm_person(self, token, pm):
        session = self._session(token) or {}
        return {"name": session.get("name") or pm, "email": session.get("email") or "", "client_user_id": pm}

    def _signable(self, state, project, doc, pm):
        if doc["kind"] != "esign":
            raise DomainError("Only signature documents are signed. Reviews and records follow their own workflow.")
        if doc["owner_id"] != pm:
            raise DomainError("This document is prepared by someone else; you sign it when they send it.")
        view = paperwork._document_view(state, project, doc)
        if view["blockers"]:
            raise DomainError("Complete its prerequisites first: " + "; ".join(view["blockers"]))
        if not doc.get("body", "").strip():
            raise DomainError("Prepare the document draft before signing it.")

    def _sign_locally(self, state, project, pm, act, token):
        """The PM signs the current revision in the platform, then it goes to the recipients as a local package."""
        doc = paperwork._doc(project, act.get("doc_id"))
        if doc["status"] not in ("ready", "draft") or doc["provider"] != "local_sample":
            raise DomainError("This revision has already been sent. Open a new revision to change and re-sign it.")
        self._signable(state, project, doc, pm)
        if act.get("consent") is not True:
            raise DomainError("Confirm that you are signing this revision electronically.")
        person = self._pm_person(token, pm)
        sig = signing.clean_signature(act.get("signature"), person["name"])
        sig.update(revision=doc["revision"], signed_at=state["now"], signer_id=pm, source_mode="platform",
                   body_hash=signing.body_hash(doc["title"], doc["revision"], doc["body"]))
        doc.setdefault("pm_signatures", []).append(sig)
        paperwork._audit(state, project, "pm_signed", pm, "Signed revision %s in the platform (%s signature)." % (doc["revision"], "drawn" if sig["method"] == "draw" else "typed"), doc)
        paperwork._dispatch(state, project, doc, pm)

    def docusign_sign(self, token, payload):
        """Sends the document through DocuSign with the PM signing first, and returns the PM's signing page."""
        pm = self.actor(token)
        project_id, doc_id = payload.get("project_id"), payload.get("doc_id")
        client = self.client(token)
        if not client.status()["docusign"]["configured"]:
            raise DomainError("Connect DocuSign in Integrations first, or sign in the platform.")
        person = self._pm_person(token, pm)
        with self.store.lock:
            record = self.store.read_workspace("paperwork")
            state = copy.deepcopy(record["state"])
            state["now"] = self.now()
            project = paperwork._project(state, pm, project_id, writable=True)
            doc = paperwork._doc(project, doc_id)
            ps = doc.get("platform_signing") or {}
            if ps.get("envelope_id") and ps["envelope_id"] == doc.get("envelope_id") and doc["status"] in ("sent", "partially_signed") and not ps.get("pm_signed_at"):
                envelope_id = ps["envelope_id"]
            elif doc["status"] in ("ready", "draft") and doc["provider"] == "local_sample":
                self._signable(state, project, doc, pm)
                people = {p["id"]: p for p in project["stakeholders"]}
                recipients = []
                for r in doc["recipients"]:
                    email = people.get(r["id"], {}).get("email", "")
                    if self.placeholder_email(email):
                        raise DomainError(f"Set a real email address for {r['name']} first (open them under Contacts and choose Edit project contact). DocuSign emails each signer.")
                    recipients.append({"recipient_id": r["id"], "name": r["name"], "email": email})
                result = signing.send_for_signature(client, scope={"project_id": project_id, "document_id": doc_id, "document_revision": doc["revision"]},
                                                    request_id=f"sign-{project_id}-{doc_id}-r{doc['revision']}", title=doc["title"], body=doc["body"], pm=person, recipients=recipients)
                sent_at = result["sent_at"]  # DocuSign's own time, so later reconciliation matches it exactly
                if paperwork._dt(sent_at) > paperwork._dt(state["now"]):
                    state["now"] = sent_at  # this server's clock is a little behind DocuSign's
                state = paperwork.apply(state, pm, {"type": "bind_provider_envelope", "project_id": project_id, "doc_id": doc_id, "envelope_id": result["envelope_id"],
                                                    "provider": "docusign", "recipient_map": result["recipient_map"], "envelope_status": "sent", "sent_at": sent_at}, trusted_provider=True)
                project = state["projects"][project_id]
                doc = paperwork._doc(project, doc_id)
                doc["platform_signing"] = {"envelope_id": result["envelope_id"], "requested_at": state["now"], "pm_signed_at": None}
                envelope_id = result["envelope_id"]
                self.store.write_workspace("paperwork", state, record["version"])
            else:
                raise DomainError("This document isn't waiting for your signature.")
        url = signing.signing_url(client, envelope_id=envelope_id, pm=person,
                                  return_url=f"http://localhost:{self.port}/api/paperwork/signing/return?project_id={project_id}&doc_id={doc_id}")
        return {"signing_url": url, "envelope_id": envelope_id}

    def signing_return(self, token, query):
        """DocuSign sends the PM back here. A completed signature is noted, then the envelope is reconciled."""
        pm = self.actor(token)
        project_id, doc_id, event = query.get("project_id"), query.get("doc_id"), query.get("event") or "unknown"
        if event == "signing_complete":
            with self.store.lock:
                record = self.store.read_workspace("paperwork")
                state = copy.deepcopy(record["state"])
                state["now"] = self.now()
                project = paperwork._project(state, pm, project_id)
                doc = paperwork._doc(project, doc_id)
                ps = doc.get("platform_signing")
                if ps and not ps.get("pm_signed_at"):
                    ps["pm_signed_at"] = state["now"]
                    paperwork._audit(state, project, "pm_signed", pm, "Signed in DocuSign from the platform; DocuSign now emails the other signers.", doc)
                    self.store.write_workspace("paperwork", state, record["version"])
            try:
                version = self.store.read_workspace("paperwork")["version"]
                self.connector_action(token, {"operation": "sync_envelope", "provider": "docusign", "expected_version": version,
                                              "project_id": project_id, "doc_id": doc_id})
            except Exception:
                pass  # the PM can sync again from the document
        return {"project_id": project_id, "doc_id": doc_id, "event": event}

    def pdf(self, token, project_id, doc_id, revision=None):
        """The document (current or an earlier revision) as a PDF with its signatures."""
        pm = self.actor(token)
        state = self.store.read_workspace("paperwork")["state"]
        project = paperwork._project(state, pm, project_id)
        doc = paperwork._doc(project, doc_id)
        rev = int(revision) if revision not in (None, "") else doc["revision"]
        snap = doc if rev == doc["revision"] else next((r for r in doc["revisions"] if r["revision"] == rev), None)
        if not snap:
            raise ValueError("No such revision.")
        sigs = [x for x in (doc.get("pm_signatures") or []) if x.get("revision") == rev]
        status = snap.get("status", "")
        data = signing.render_pdf(title=snap["title"], subtitle=f"{project['name']} ({project['id']}) - {doc_id} - revision {rev} - {status.replace('_', ' ')}",
                                  body=snap.get("body") or "(No document text.)", revision=rev, signatures=sigs,
                                  recipients=[{"name": r["name"], "status": r["status"], "signed_at": r.get("signed_at")} for r in snap.get("recipients", [])],
                                  footer=f"Generated by the EQORE PM platform on {self.now()[:16].replace('T', ' ')} UTC from document center record {project_id}/{doc_id}/r{rev}.")
        return data, f"{project_id}-{doc_id}-r{rev}.pdf"
