"""EQORE PM platform: local server.

Serves the repository root (the app loads ../eqore-demo/web/styles.css for the shared look), signs PMs in, and
connects to the PM's real Gmail and Google Calendar through Google OAuth:

  * Sign in with a work email. Google accounts go through Google's own sign-in (OAuth), which signs the PM in to
    this platform and connects their inbox and calendar in one step. The demo PM accounts sign in with a password.
  * /api/inbox    scans the Gmail inbox for paperwork (documents to sign or complete) and sorts it by department.
  * /api/calendar reads the PM's Google Calendar.
  * /api/send     sends an email from the PM's own Gmail account.
  * /api/workspace saves the PM's own edits (products, contractors) in pm/data/<PM>.json.
  * /api/paperwork/* is Yichang's document center (pm/doccenter/, from eqore-demo): documents, revisions,
    signing events, compliance review, email drafts, DocuSign and Gmail drafts. Stored in pm/data/paperwork.json.

Google tokens stay in this server's memory only and are never sent to the browser.

Run from the repo root:  python pm/server.py   then open http://localhost:8790/
Python 3.10+, standard library only. Google setup: see pm/README.md (GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET or
pm/google_oauth.json). Without it, the demo accounts work with a synthetic inbox and calendar.
"""
import argparse
import base64
import json
import os
import re
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from email.message import EmailMessage
from email.utils import getaddresses, parseaddr, parsedate_to_datetime
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlencode, urlparse
from urllib.request import Request, urlopen
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "doccenter"))
from adapter import DocCenter  # noqa: E402  (Yichang's document center)
from engine import DomainError  # noqa: E402
from paperwork_connectors import ConnectorError  # noqa: E402
from storage import Conflict  # noqa: E402

DOCS = None  # the document center service, created in main()

ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent
CONFIG_FILE = HERE / "google_oauth.json"
EDITS_DIR = HERE / "data"  # each PM's saved edits (products, documents, contractors), git-ignored
MAX_BODY = 1024 * 1024
PORT = 8790

SCOPES = [
    "openid", "email", "profile",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.compose",  # the document center's Gmail drafts
    "https://www.googleapis.com/auth/calendar.readonly",
]

# Gmail search for paperwork: things to sign, fill out or return. Promotions and social mail are skipped.
PAPERWORK_QUERY = (
    'newer_than:90d -category:promotions -category:social -in:chats '
    '(sign OR signature OR signed OR docusign OR "please complete" OR "fill out" OR form OR permit OR agreement '
    'OR contract OR invoice OR application OR approval OR "purchase order" OR certificate OR W-9 OR COI OR "lien waiver")'
)

DEPARTMENT_RULES = [
    ("Permitting & inspections", r"\bpermit|inspect|fire marshal|ahj|building dep|certificate of occupancy|wiring"),
    ("Utility interconnection", r"interconnect|utility|\bpto\b|permission to operate|meter|national grid|eversource|pg&e|\bsce\b"),
    ("Contracts & legal", r"contract|agreement|\bnda\b|legal|insurance|\bcoi\b|consent|amendment|terms|lease"),
    ("Procurement", r"purchase order|\bpo\b|quote|invoice|payment|w-9|lien waiver|bill of lading|delivery|freight|order"),
    ("Engineering", r"stamped|engineering|one-line|drawing|plan set|\bpe\b|nfpa"),
    ("Construction", r"crane|lift plan|shutdown|commission|site|pad|construction|subcontract"),
]

SESSIONS = {}          # token -> session
PENDING_OAUTH = {}     # state -> {"created", "login_hint"}
LOCK = threading.Lock()


def load_roster():
    """Demo PM accounts, read from pm/data.js so there is one source of truth."""
    text = (HERE / "data.js").read_text(encoding="utf-8")
    rows = re.findall(r'\{ id: "(PM-\w+)", name: "([^"]+)", email: "([^"]+)"', text)
    password = re.search(r'DEMO_PASSWORD = "([^"]+)"', text).group(1)
    return {email.lower(): {"pm_id": pm_id, "name": name, "email": email} for pm_id, name, email in rows}, password


ROSTER, DEMO_PASSWORD = load_roster()
DEFAULT_PORTFOLIO = os.environ.get("PM_DEFAULT_PORTFOLIO", "PM-JORDAN")


def google_config():
    cid, secret = os.environ.get("GOOGLE_CLIENT_ID"), os.environ.get("GOOGLE_CLIENT_SECRET")
    if cid and secret:
        return {"client_id": cid, "client_secret": secret}
    if CONFIG_FILE.exists():
        raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        raw = raw.get("web") or raw.get("installed") or raw
        if raw.get("client_id") and raw.get("client_secret"):
            return {"client_id": raw["client_id"], "client_secret": raw["client_secret"]}
    return None


def redirect_uri():
    return f"http://localhost:{PORT}/auth/google/callback"


# ---------- Google HTTP helpers ----------
class GoogleError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def http_json(url, method="GET", data=None, token=None, form=False):
    headers = {"Accept": "application/json"}
    body = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if data is not None:
        if form:
            body = urlencode(data).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            body = json.dumps(data).encode()
            headers["Content-Type"] = "application/json"
    try:
        with urlopen(Request(url, data=body, method=method, headers=headers), timeout=20) as r:
            return json.loads(r.read() or b"{}")
    except HTTPError as e:
        try:
            detail = json.loads(e.read()).get("error", {})
            message = detail.get("message") if isinstance(detail, dict) else str(detail)
        except Exception:
            message = e.reason
        raise GoogleError(e.code, message or "Google request failed")
    except URLError as e:
        raise GoogleError(502, f"Could not reach Google: {e.reason}")


def access_token(session):
    """Returns a valid access token for a Google session, refreshing it when it has expired."""
    g = session["google"]
    if g["expires_at"] - 60 > time.time():
        return g["access_token"]
    cfg = google_config()
    if not (cfg and g.get("refresh_token")):
        raise GoogleError(401, "Google sign-in expired. Sign in again.")
    tok = http_json("https://oauth2.googleapis.com/token", "POST", {
        "client_id": cfg["client_id"], "client_secret": cfg["client_secret"],
        "refresh_token": g["refresh_token"], "grant_type": "refresh_token"}, form=True)
    g["access_token"] = tok["access_token"]
    g["expires_at"] = time.time() + int(tok.get("expires_in", 3600))
    return g["access_token"]


def department(text):
    low = text.lower()
    for name, pattern in DEPARTMENT_RULES:
        if re.search(pattern, low):
            return name
    return "Other paperwork"


def gmail_paperwork(session):
    token = access_token(session)
    listing = http_json("https://gmail.googleapis.com/gmail/v1/users/me/messages?" + urlencode({"q": PAPERWORK_QUERY, "maxResults": 30}), token=token)
    ids = [m["id"] for m in listing.get("messages", [])]

    def fetch(mid):
        q = "format=metadata&metadataHeaders=From&metadataHeaders=Subject&metadataHeaders=Date"
        return http_json(f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{mid}?{q}", token=token)

    with ThreadPoolExecutor(max_workers=8) as pool:
        messages = list(pool.map(fetch, ids))
    email = session["email"]
    items = []
    for m in messages:
        headers = {h["name"].lower(): h["value"] for h in m.get("payload", {}).get("headers", [])}
        name, addr = parseaddr(headers.get("from", ""))
        subject = headers.get("subject", "(no subject)")
        try:
            date = parsedate_to_datetime(headers["date"]).date().isoformat()
        except Exception:
            date = time.strftime("%Y-%m-%d", time.localtime(int(m.get("internalDate", "0")) / 1000))
        snippet = m.get("snippet", "")
        items.append({
            "id": m["id"], "thread_id": m.get("threadId"), "from_name": name or addr, "from_email": addr, "subject": subject,
            "snippet": snippet, "date": date, "department": department(subject + " " + snippet),
            "unread": "UNREAD" in m.get("labelIds", []),
            "link": f"https://mail.google.com/mail/u/?authuser={quote(email)}#all/{m.get('threadId')}",
        })
    return {"mode": "google", "email": email, "items": items, "inbox_link": f"https://mail.google.com/mail/u/?authuser={quote(email)}"}


def google_calendar(session, start, end):
    token = access_token(session)
    params = {"timeMin": f"{start}T00:00:00Z", "timeMax": f"{end}T23:59:59Z", "singleEvents": "true", "orderBy": "startTime", "maxResults": 250}
    data = http_json("https://www.googleapis.com/calendar/v3/calendars/primary/events?" + urlencode(params), token=token)
    events = []
    for e in data.get("items", []):
        s = e.get("start", {})
        when = s.get("dateTime") or s.get("date") or ""
        events.append({"date": when[:10], "time": when[11:16] if "T" in when else None, "title": e.get("summary") or "(busy)",
                       "link": e.get("htmlLink"), "location": e.get("location")})
    return {"mode": "google", "events": events, "calendar_link": "https://calendar.google.com/calendar/u/?authuser=" + quote(session["email"])}


ADDRESS = re.compile(r"^[^@\s<>\"]+@[^@\s<>\"]+\.[^@\s<>\"]+$")


def gmail_send(session, body, attachments=()):
    to = [a for _, a in getaddresses([str(body.get("to", ""))]) if a]
    cc = [a for _, a in getaddresses([str(body.get("cc", ""))]) if a]
    subject = str(body.get("subject", "")).strip()
    text = str(body.get("body", ""))
    if not to:
        raise GoogleError(400, "Add at least one recipient.")
    bad = [a for a in to + cc if not ADDRESS.match(a)]
    if bad:
        raise GoogleError(400, "Not a valid email address: " + ", ".join(bad))
    if not subject or len(subject) > 300 or len(text) > 50000 or "\n" in subject or "\r" in subject:
        raise GoogleError(400, "Add a subject (one line) and keep the message under 50,000 characters.")
    msg = EmailMessage()
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["From"] = session["email"]
    msg["Subject"] = subject
    msg.set_content(text)
    for data, filename in attachments:
        msg.add_attachment(data, maintype="application", subtype="pdf", filename=filename)
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    sent = http_json("https://gmail.googleapis.com/gmail/v1/users/me/messages/send", "POST", {"raw": raw}, token=access_token(session))
    return {"sent": True, "id": sent.get("id"), "thread_id": sent.get("threadId"), "to": to}


# ---------- The PM's saved edits ----------
def edits_file(pm_id):
    if not re.match(r"^PM-[A-Z]+$", pm_id or ""):
        raise ValueError("Unknown portfolio")
    return EDITS_DIR / f"{pm_id}.json"


def load_edits(pm_id):
    f = edits_file(pm_id)
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {"version": 0, "data": {}}


def save_edits(pm_id, doc):
    EDITS_DIR.mkdir(exist_ok=True)
    f = edits_file(pm_id)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc), encoding="utf-8")
    tmp.replace(f)


# ---------- HTTP ----------
class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, fmt, *args):
        pass

    def end_headers(self):
        if not self.path.startswith("/api/"):
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    # -- helpers
    def send_json(self, value, status=HTTPStatus.OK, cookie=None):
        body = json.dumps(value).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if cookie is not None:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(body)

    def redirect(self, location, cookie=None):
        self.send_response(HTTPStatus.FOUND)
        self.send_header("Location", location)
        if cookie is not None:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()

    def read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            raise ValueError("Request too large")
        return json.loads(self.rfile.read(length) or b"{}")

    def token(self):
        cookies = dict(p.strip().split("=", 1) for p in (self.headers.get("Cookie") or "").split(";") if "=" in p)
        return cookies.get("pm_session", "")

    def session(self):
        with LOCK:
            return SESSIONS.get(self.token())

    # -- Yichang's document center (pm/doccenter)
    def paperwork(self, fn):
        try:
            return self.send_json(fn(self.token()))
        except PermissionError as e:
            return self.send_json({"error": str(e)}, HTTPStatus.FORBIDDEN if self.session() else HTTPStatus.UNAUTHORIZED)
        except Conflict as e:
            return self.send_json({"error": str(e)}, HTTPStatus.CONFLICT)
        except ConnectorError as e:
            return self.send_json({"error": str(e), "code": e.code, "retryable": e.retryable, "ambiguous": e.ambiguous}, HTTPStatus.BAD_GATEWAY)
        except (ValueError, KeyError, TypeError, DomainError) as e:
            return self.send_json({"error": str(e)}, HTTPStatus.BAD_REQUEST)

    def paperwork_get(self, path, query):
        if path.startswith("/api/paperwork/oauth/callback/"):
            provider = path.rsplit("/", 1)[-1]
            s = self.session() or {}
            back = s.get("doc_return") or "#/portfolio"
            try:
                DOCS.oauth_complete(provider, query, self.token())
                return self.redirect("/pm/" + back + ("&" if "?" in back else "?") + "connected=" + quote(provider))
            except Exception as e:  # shown to the PM on return; provider errors never include tokens
                return self.redirect("/pm/" + back + ("&" if "?" in back else "?") + "connect_error=" + quote(str(e)[:200]))
        if path == "/api/paperwork/document.pdf":
            g = lambda k: query.get(k, [None])[0]
            try:
                data, name = DOCS.pdf(self.token(), g("project_id"), g("doc_id"), g("revision"))
            except PermissionError as e:
                return self.send_json({"error": str(e)}, HTTPStatus.UNAUTHORIZED)
            except (ValueError, KeyError, DomainError) as e:
                return self.send_json({"error": str(e)}, HTTPStatus.BAD_REQUEST)
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/pdf")
            self.send_header("Content-Disposition", f'{"attachment" if g("download") else "inline"}; filename="{name}"')
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return
        if path == "/api/paperwork/signing/return":
            g = lambda k: query.get(k, [""])[0]
            try:
                r = DOCS.signing_return(self.token(), {"project_id": g("project_id"), "doc_id": g("doc_id"), "event": g("event")})
            except Exception as e:  # noqa: BLE001  shown to the PM; no provider detail is included
                r = {"project_id": g("project_id"), "doc_id": g("doc_id"), "event": "error", "error": str(e)[:200]}
            target = "/pm/#/project/%s/documents?doc=%s&signed=%s" % (quote(r["project_id"] or ""), quote(r["doc_id"] or ""), quote(r["event"]))
            page = ("<!doctype html><meta charset='utf-8'><title>Signing finished</title><body style='font-family:sans-serif;padding:24px'>"
                    "<p>Returning to the EQORE PM platform…</p><script>const t=%s,e=%s;"
                    "if(window.opener&&!window.opener.closed){window.opener.postMessage({type:'eqore-signing',event:e},location.origin);window.close();}"
                    "else location.replace(t);</script>") % (json.dumps(target), json.dumps(r["event"]))
            data = page.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if path == "/api/paperwork/bootstrap":
            return self.paperwork(lambda t: DOCS.bootstrap(t, query.get("project_id", [None])[0]))
        if path == "/api/paperwork/connectors":
            return self.paperwork(lambda t: (DOCS.actor(t), DOCS.connector_status(t))[1])
        if path.startswith("/api/paperwork/jobs/"):
            return self.paperwork(lambda t: DOCS.job(t, path.rsplit("/", 1)[1]))
        if path == "/api/paperwork/documents":
            return self.paperwork(DOCS.feed)
        return self.send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def paperwork_post(self, path, body):
        if path == "/api/paperwork/action":
            return self.paperwork(lambda t: DOCS.action(t, body))
        if path == "/api/paperwork/docusign/sign":
            return self.paperwork(lambda t: DOCS.docusign_sign(t, body))
        if path == "/api/paperwork/ensure":
            return self.paperwork(lambda t: DOCS.ensure(t, body))
        if path == "/api/paperwork/assist":
            return self.paperwork(lambda t: DOCS.assist(t, body))
        if path == "/api/paperwork/connectors":
            return self.paperwork(lambda t: DOCS.connector_action(t, body))
        if path == "/api/paperwork/oauth/start":
            back = str(body.get("return_to") or "")
            s = self.session()
            if s and re.fullmatch(r"#/project/JOB-\d{3}/documents(\?[A-Za-z0-9=&%._:-]*)?", back):
                s["doc_return"] = back
            return self.paperwork(lambda t: DOCS.oauth_start(t, body))
        return self.send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    @staticmethod
    def new_session(data):
        token = secrets.token_urlsafe(32)
        with LOCK:
            SESSIONS[token] = data
        return f"pm_session={token}; HttpOnly; SameSite=Lax; Path=/"

    def same_origin(self):
        origin = self.headers.get("Origin")
        return origin is None or urlparse(origin).netloc == self.headers.get("Host")

    # -- routes
    def do_GET(self):
        url = urlparse(self.path)
        path = url.path
        host = self.headers.get("Host", "")
        if host.startswith("127.0.0.1"):  # one origin, so the sign-in cookie and Google's redirect address match
            return self.redirect(f"http://localhost:{PORT}{self.path}")
        if path == "/":
            return self.redirect("/pm/")
        if path == "/api/me":
            s = self.session()
            base = {"google_configured": bool(google_config())}
            if not s:
                return self.send_json({"signed_in": False, **base})
            return self.send_json({"signed_in": True, **base, **{k: s[k] for k in ("email", "name", "mode", "pm_id", "in_roster", "picture")}})
        if path == "/auth/google/start":
            cfg = google_config()
            if not cfg:
                return self.redirect("/pm/#/login?error=" + quote("Google sign-in is not set up on this server yet (see pm/README.md)."))
            state = secrets.token_urlsafe(24)
            hint = parse_qs(url.query).get("login_hint", [""])[0][:200]
            with LOCK:
                PENDING_OAUTH[state] = {"created": time.time()}
            params = {"client_id": cfg["client_id"], "redirect_uri": redirect_uri(), "response_type": "code", "scope": " ".join(SCOPES),
                      "state": state, "access_type": "offline", "include_granted_scopes": "true", "prompt": "consent"}
            if hint:
                params["login_hint"] = hint
            return self.redirect("https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params))
        if path == "/auth/google/callback":
            return self.google_callback(parse_qs(url.query))
        if path.startswith("/api/paperwork/"):
            return self.paperwork_get(path, parse_qs(url.query))
        if path == "/api/workspace":
            s = self.session()
            if not s:
                return self.send_json({"error": "Not signed in"}, HTTPStatus.UNAUTHORIZED)
            with LOCK:
                return self.send_json(load_edits(s["pm_id"]))
        if path == "/api/inbox":
            return self.with_google(lambda s: gmail_paperwork(s))
        if path == "/api/calendar":
            q = parse_qs(url.query)
            start, end = q.get("from", [""])[0], q.get("to", [""])[0]
            if not (re.match(r"^\d{4}-\d{2}-\d{2}$", start) and re.match(r"^\d{4}-\d{2}-\d{2}$", end)):
                return self.send_json({"error": "from and to must be YYYY-MM-DD"}, HTTPStatus.BAD_REQUEST)
            return self.with_google(lambda s: google_calendar(s, start, end))
        if any(part.startswith(".") for part in path.split("/") if part) or path.endswith(".py") or path.startswith("/pm/google_oauth") or path.startswith("/pm/data/"):
            return self.send_error(HTTPStatus.NOT_FOUND)
        return super().do_GET()

    def with_google(self, fn):
        s = self.session()
        if not s:
            return self.send_json({"error": "Not signed in"}, HTTPStatus.UNAUTHORIZED)
        if s["mode"] != "google":
            return self.send_json({"mode": "demo"})
        try:
            return self.send_json(fn(s))
        except GoogleError as e:
            return self.send_json({"error": str(e)}, e.status if 400 <= e.status < 600 else 502)

    def google_callback(self, q):
        state = q.get("state", [""])[0]
        with LOCK:
            pending = PENDING_OAUTH.pop(state, None)
        if not pending or time.time() - pending["created"] > 600:
            return self.redirect("/pm/#/login?error=" + quote("Sign-in link expired. Try again."))
        if "error" in q:
            return self.redirect("/pm/#/login?error=" + quote("Google sign-in was cancelled."))
        cfg = google_config()
        try:
            tok = http_json("https://oauth2.googleapis.com/token", "POST", {
                "code": q.get("code", [""])[0], "client_id": cfg["client_id"], "client_secret": cfg["client_secret"],
                "redirect_uri": redirect_uri(), "grant_type": "authorization_code"}, form=True)
            me = http_json("https://openidconnect.googleapis.com/v1/userinfo", token=tok["access_token"])
        except GoogleError as e:
            return self.redirect("/pm/#/login?error=" + quote(f"Google sign-in failed: {e}"))
        granted = set(tok.get("scope", "").split())
        missing = [s for s in SCOPES[3:] if s not in granted]
        email = me.get("email", "").lower()
        roster = ROSTER.get(email)
        cookie = self.new_session({
            "mode": "google", "email": email, "name": me.get("name") or email, "picture": me.get("picture"),
            "pm_id": roster["pm_id"] if roster else DEFAULT_PORTFOLIO, "in_roster": bool(roster),
            "google": {"access_token": tok["access_token"], "refresh_token": tok.get("refresh_token"),
                       "expires_at": time.time() + int(tok.get("expires_in", 3600))},
        })
        target = "/pm/#/portfolio" + ("?missing_scopes=1" if missing else "")
        return self.redirect(target, cookie)

    def do_PUT(self):
        if urlparse(self.path).path != "/api/workspace":
            return self.send_error(HTTPStatus.NOT_FOUND)
        if not self.same_origin():
            return self.send_json({"error": "Cross-site request blocked"}, HTTPStatus.FORBIDDEN)
        s = self.session()
        if not s:
            return self.send_json({"error": "Not signed in"}, HTTPStatus.UNAUTHORIZED)
        try:
            body = self.read_json()
        except ValueError as error:
            return self.send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
        if not isinstance(body.get("data"), dict):
            return self.send_json({"error": "Nothing to save"}, HTTPStatus.BAD_REQUEST)
        with LOCK:
            doc = load_edits(s["pm_id"])
            if body.get("base_version") != doc["version"]:
                return self.send_json({"error": "Your changes were saved from another tab. Reloaded the latest.", **doc}, HTTPStatus.CONFLICT)
            doc = {"version": doc["version"] + 1, "data": body["data"]}
            save_edits(s["pm_id"], doc)
        return self.send_json({"version": doc["version"]})

    def do_POST(self):
        path = urlparse(self.path).path
        if not self.same_origin():
            return self.send_json({"error": "Cross-site request blocked"}, HTTPStatus.FORBIDDEN)
        try:
            body = self.read_json()
        except ValueError as error:
            return self.send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
        if path == "/api/login":
            email = str(body.get("email", "")).strip().lower()
            pm = ROSTER.get(email)
            if not pm or body.get("password") != DEMO_PASSWORD:
                return self.send_json({"error": "Email or password is not right for a demo account."}, HTTPStatus.UNAUTHORIZED)
            cookie = self.new_session({"mode": "demo", "email": pm["email"], "name": pm["name"], "pm_id": pm["pm_id"], "in_roster": True, "picture": None})
            return self.send_json({"ok": True}, cookie=cookie)
        if path.startswith("/api/paperwork/"):
            return self.paperwork_post(path, body)
        if path == "/api/logout":
            if DOCS:
                DOCS.logout(self.token())
            cookies = dict(p.strip().split("=", 1) for p in (self.headers.get("Cookie") or "").split(";") if "=" in p)
            with LOCK:
                SESSIONS.pop(cookies.get("pm_session", ""), None)
            return self.send_json({"ok": True}, cookie="pm_session=; Max-Age=0; Path=/")
        if path == "/api/send":
            # Attachments are documents from the document center, rendered here; the browser never uploads files.
            wanted = body.get("attachments") or []
            if not isinstance(wanted, list) or len(wanted) > 3:
                return self.send_json({"error": "Attach up to three documents."}, HTTPStatus.BAD_REQUEST)
            try:
                files = [DOCS.pdf(self.token(), a.get("project_id"), a.get("doc_id"), a.get("revision")) for a in wanted if isinstance(a, dict)]
            except (PermissionError, ValueError, KeyError, DomainError) as e:
                return self.send_json({"error": f"Couldn't attach the document: {e}"}, HTTPStatus.BAD_REQUEST)
            return self.with_google(lambda s: gmail_send(s, body, files))
        return self.send_error(HTTPStatus.NOT_FOUND)


def main():
    global PORT
    parser = argparse.ArgumentParser(description="EQORE PM platform (local demo)")
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args()
    PORT = args.port
    global DOCS
    # DocuSign integration key (a public app ID): environment, or pm/docusign.json (git-ignored, per developer).
    ds_file = HERE / "docusign.json"
    if not os.environ.get("EQORE_DOCUSIGN_CLIENT_ID") and ds_file.exists():
        key = json.loads(ds_file.read_text(encoding="utf-8")).get("client_id")
        if key:
            os.environ["EQORE_DOCUSIGN_CLIENT_ID"] = key
    DOCS = DocCenter(EDITS_DIR, PORT, SESSIONS, LOCK, [{"id": v["pm_id"], "name": v["name"], "email": v["email"]} for v in ROSTER.values()], google_token=access_token)
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    status = "Google sign-in ready" if google_config() else "Google sign-in not configured: demo accounts only (see pm/README.md)"
    status += "; DocuSign key loaded" if os.environ.get("EQORE_DOCUSIGN_CLIENT_ID") else "; DocuSign not configured"
    print(f"EQORE PM platform on http://localhost:{PORT}/  ({status})")
    server.serve_forever()


if __name__ == "__main__":
    main()
