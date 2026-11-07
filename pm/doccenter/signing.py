"""Signing for the PM platform's document center: DocuSign embedded signing, in-platform signatures, signed PDFs.

Yichang's adapter (paperwork_connectors.py) deliberately stops at unsent DocuSign drafts. This module adds the
two calls the platform needs to let a PM sign inside the platform and have DocuSign email the other signers:
  * send an envelope (status "sent") with the PM as an embedded signer (routing order 1, clientUserId) and the
    document's recipients as remote signers (routing order 2, DocuSign emails them once the PM has signed);
  * create the PM's recipient view (the signing page), which returns to this server when done.
It uses the same safety rules as his adapter: fixed sandbox host, allowlisted paths, no redirects, and errors
that never echo provider bodies or credentials. Signatures of the remote signers are then recorded by his
existing reconciliation (sync_envelope), never inferred.

Without DocuSign, the PM can sign in the platform (drawn or typed), and render_pdf() produces the signed copy
to download or email.
"""
import base64
import hashlib
import json
import re
import urllib.error
import urllib.parse
from datetime import datetime, timezone

from paperwork_connectors import BASES, TOKEN_NAMES, ConnectorError, _email, _identifier, _text

DOCUSIGN = BASES["docusign"]
ALLOWED = {"POST": [r"/accounts/[A-Za-z0-9_-]+/envelopes", r"/accounts/[A-Za-z0-9_-]+/envelopes/[A-Za-z0-9_-]+/views/recipient"]}


def _request(connectors, method, path, payload):
    """One allowlisted DocuSign sandbox call through the connector's own transport (no redirects, size-capped)."""
    env = connectors._env
    if not env.get(TOKEN_NAMES["docusign"]) or not env.get("EQORE_DOCUSIGN_ACCOUNT_ID"):
        raise ConnectorError("unconfigured", "Connect DocuSign in Integrations first.")
    if method not in ALLOWED or not any(re.fullmatch(p, path) for p in ALLOWED[method]) or ".." in path:
        raise ConnectorError("invalid_endpoint", "Provider endpoint is not permitted.")
    url = DOCUSIGN + path
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != urllib.parse.urlsplit(DOCUSIGN).hostname or parsed.port is not None:
        raise ConnectorError("invalid_endpoint", "Provider endpoint is not permitted.")
    headers = {"Authorization": "Bearer " + env[TOKEN_NAMES["docusign"]], "Accept": "application/json", "Content-Type": "application/json"}
    try:
        value = connectors._transport(method, url, headers, json.dumps(payload).encode("utf-8"), 15)
        if not isinstance(value, dict):
            raise ValueError("Expected object")
        return value
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        code = "authentication_failed" if status in (401, 403) else "provider_http_error"
        raise ConnectorError(code, "DocuSign %s request failed (HTTP %d)." % (method, status), ambiguous=status >= 500) from None
    except ConnectorError:
        raise
    except Exception:
        raise ConnectorError("provider_unavailable", "DocuSign could not be reached.", ambiguous=True) from None


def _account(connectors):
    return "/accounts/" + _identifier(connectors._env.get("EQORE_DOCUSIGN_ACCOUNT_ID"), "DocuSign account ID")


def send_for_signature(connectors, *, scope, request_id, title, body, pm, recipients):
    """Sends one envelope: the PM signs first in the platform, then DocuSign emails each recipient.

    scope: {project_id, document_id, document_revision}; pm: {name, email, client_user_id};
    recipients: [{recipient_id (platform actor id), name, email}]. Returns envelope id, sent time and the
    wire-id -> actor map for the document's recipients (the PM's own wire id "1" is not a document recipient).
    """
    title = _text(title, "subject", 100)
    if not isinstance(body, str) or not body.strip() or len(body.encode("utf-8")) > 3 * 1024 * 1024:
        raise ConnectorError("invalid_input", "The document needs a reviewed draft before it can be signed.")
    if not isinstance(recipients, list) or not 1 <= len(recipients) <= 19:
        raise ConnectorError("invalid_input", "Provide 1-19 recipients.")
    signers, recipient_map, blocks = [], {}, ["\n\nSIGNATURES\n"]
    people = [dict(pm, recipient_id=None, routing="1")] + [dict(r, routing="2") for r in recipients]
    for index, person in enumerate(people, 1):
        wire = str(index)
        signer = {"name": _text(person.get("name"), "signer name", 100), "email": _email(person.get("email")),
                  "recipientId": wire, "routingOrder": person["routing"]}
        if index == 1:
            signer["clientUserId"] = _identifier(person.get("client_user_id"), "client user id", 100)
        else:
            recipient_map[wire] = _identifier(person.get("recipient_id"), "recipient_id")
        suffix = hashlib.sha256(json.dumps([scope, request_id, wire], sort_keys=True).encode()).hexdigest()[:20]
        sign_anchor, date_anchor = "[[ps_" + suffix + "]]", "[[pd_" + suffix + "]]"
        if sign_anchor in body or date_anchor in body:
            raise ConnectorError("invalid_input", "A generated signature anchor already occurs in this document.")
        blocks.append("\n" + signer["name"] + "\nSignature:\n" + sign_anchor + "\n\n\n\nDate signed:\n" + date_anchor + "\n\n\n")
        common = {"documentId": "1", "recipientId": wire, "anchorUnits": "pixels", "anchorXOffset": "0", "anchorYOffset": "0",
                  "anchorIgnoreIfNotPresent": "false", "anchorCaseSensitive": "true"}
        signer["tabs"] = {"signHereTabs": [{**common, "anchorString": sign_anchor, "optional": "false", "tabLabel": "signature_" + suffix}],
                          "dateSignedTabs": [{**common, "anchorString": date_anchor, "tabLabel": "date_signed_" + suffix}]}
        signers.append(signer)
    rendered = (body + "".join(blocks)).encode("utf-8")
    transaction = hashlib.sha256(json.dumps([scope, request_id], sort_keys=True).encode()).hexdigest()[:40]
    data = _request(connectors, "POST", _account(connectors) + "/envelopes", {
        "status": "sent", "transactionId": transaction, "emailSubject": title,
        "emailBlurb": "Please review and sign. Sent from the EQORE PM platform.",
        "documents": [{"documentBase64": base64.b64encode(rendered).decode(), "name": title, "fileExtension": "txt", "documentId": "1"}],
        "recipients": {"signers": signers},
        "customFields": {"textCustomFields": [{"name": k, "value": str(v), "show": "false"} for k, v in scope.items()]}})
    envelope_id = data.get("envelopeId")
    if not isinstance(envelope_id, str) or not envelope_id:
        raise ConnectorError("invalid_provider_response", "DocuSign returned no envelope ID; check the account before retrying.", ambiguous=True)
    sent_at = data.get("statusDateTime") or datetime.now(timezone.utc).isoformat()
    return {"envelope_id": envelope_id, "sent_at": sent_at, "recipient_map": recipient_map, "status": data.get("status", "sent")}


def signing_url(connectors, *, envelope_id, pm, return_url):
    """The PM's embedded signing page for an envelope that was sent with them as signer 1."""
    _identifier(envelope_id, "envelope id")
    parsed = urllib.parse.urlsplit(return_url)
    if parsed.scheme != "http" or parsed.hostname != "localhost":
        raise ConnectorError("invalid_input", "The return address must be this local platform.")
    data = _request(connectors, "POST", _account(connectors) + f"/envelopes/{envelope_id}/views/recipient", {
        "returnUrl": return_url, "authenticationMethod": "none", "recipientId": "1",
        "userName": _text(pm.get("name"), "signer name", 100), "email": _email(pm.get("email")),
        "clientUserId": _identifier(pm.get("client_user_id"), "client user id", 100)})
    url = data.get("url")
    host = urllib.parse.urlsplit(url or "").hostname or ""
    if not url or not url.startswith("https://") or not (host == "docusign.net" or host.endswith(".docusign.net") or host.endswith(".docusign.com")):
        raise ConnectorError("invalid_provider_response", "DocuSign returned no signing page.")
    return url


# ---------- In-platform signatures ----------
def clean_signature(sig, name):
    """A drawn (strokes of 0-1 points) or typed signature, size-limited."""
    if not isinstance(sig, dict) or sig.get("method") not in ("draw", "type"):
        raise ValueError("Draw or type your signature.")
    if sig["method"] == "type":
        typed = str(sig.get("typed") or "").strip()
        if not 2 <= len(typed) <= 80:
            raise ValueError("Type your full name to sign.")
        return {"method": "type", "typed": typed, "name": name}
    strokes = sig.get("strokes")
    if not isinstance(strokes, list) or not 1 <= len(strokes) <= 80:
        raise ValueError("Draw your signature in the box.")
    clean, points = [], 0
    for stroke in strokes:
        if not isinstance(stroke, list) or not stroke:
            continue
        row = []
        for pt in stroke[:600]:
            if isinstance(pt, list) and len(pt) == 2 and all(isinstance(v, (int, float)) and 0 <= v <= 1 for v in pt):
                row.append([round(pt[0], 4), round(pt[1], 4)])
        if row:
            clean.append(row); points += len(row)
    if points < 8:
        raise ValueError("Draw your signature in the box.")
    return {"method": "draw", "strokes": clean, "name": name}


def body_hash(title, revision, body):
    return hashlib.sha256(json.dumps([title, revision, body], ensure_ascii=False).encode("utf-8")).hexdigest()


# ---------- Signed PDF (standard library only) ----------
def _latin(text):
    table = {"–": "-", "—": "-", "’": "'", "‘": "'", "“": '"', "”": '"', "•": "-", "·": "-", "→": "->", "…": "..."}
    return "".join(table.get(c, c) for c in str(text)).encode("latin-1", "replace").decode("latin-1")


def _pdf_text(text):
    return _latin(text).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _wrap(text, width=92):
    out = []
    for para in _latin(text).split("\n"):
        line = ""
        for word in para.split(" "):
            while len(word) > width:
                out.append((line + " " + word[:width - len(line) - 1]).strip()); word = word[width - len(line) - 1:]; line = ""
            if len(line) + len(word) + 1 > width:
                out.append(line); line = word
            else:
                line = (line + " " + word).strip() if line else word
        out.append(line)
    return out


def render_pdf(*, title, subtitle, body, revision, signatures, recipients, footer):
    """A Letter-size PDF: the document text, a signature block (drawn strokes as vector paths) and a verification footer."""
    W, H, M, LEAD = 612, 792, 56, 13
    pages, ops, y = [], [], H - M

    def new_page():
        nonlocal ops, y
        if ops:
            pages.append(ops)
        ops, y = [], H - M

    def text(s, size=10, font="F1", x=M, gap=LEAD):
        nonlocal y
        if y < M + 40:
            new_page()
        ops.append(f"BT /{font} {size} Tf {x} {y} Td ({_pdf_text(s)}) Tj ET")
        y -= gap

    text(title, 16, "F2", gap=20)
    text(subtitle, 9, "F1", gap=18)
    for line in _wrap(body):
        text(line)
    y -= 10
    text("SIGNATURES", 11, "F2", gap=18)
    if not signatures:
        text("Not signed yet.", 10)
    for sig in signatures:
        if y < M + 120:
            new_page()
        top = y
        ops.append(f"0.75 G 0.5 w {M} {top - 62} 240 62 re S")
        if sig.get("method") == "draw":
            ops.append("0.02 0.09 0.17 RG 1.4 w 1 J 1 j")
            for stroke in sig.get("strokes", []):
                pts = [(M + 6 + px * 228, top - 4 - py * 54) for px, py in stroke]
                if len(pts) == 1:
                    pts.append((pts[0][0] + 0.5, pts[0][1]))
                ops.append(" ".join([f"{pts[0][0]:.1f} {pts[0][1]:.1f} m"] + [f"{a:.1f} {b:.1f} l" for a, b in pts[1:]]) + " S")
        else:
            ops.append(f"0.02 0.09 0.17 rg BT /F3 22 Tf {M + 10} {top - 40} Td ({_pdf_text(sig.get('typed', ''))}) Tj ET 0 g")
        y = top - 76
        text(f"{sig.get('name', '')}  -  signed {sig.get('signed_at', '')[:16].replace('T', ' ')} UTC  -  revision {sig.get('revision', revision)}", 9)
        text(f"Signed in the EQORE PM platform ({'drawn' if sig.get('method') == 'draw' else 'typed'} signature). Verification: {sig.get('body_hash', '')[:32]}", 8, gap=18)
    for r in recipients:
        text(f"{r.get('name', '')}: {r.get('status', 'pending')}{(' ' + str(r.get('signed_at'))[:10]) if r.get('signed_at') else ''}", 9)
    y -= 6
    text(footer, 8)
    new_page()
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", None,
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Oblique /Encoding /WinAnsiEncoding >>"]
    kids = []
    for page_ops in pages:
        stream = "\n".join(page_ops).encode("latin-1")
        objs.append(f"<< /Length {len(stream)} >>\nstream\n".encode("latin-1") + stream + b"\nendstream")
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {W} {H}] /Resources << /Font << /F1 3 0 R /F2 4 0 R /F3 5 0 R >> >> /Contents {len(objs)} 0 R >>")
        kids.append(len(objs))
    objs[1] = f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in kids)}] /Count {len(kids)} >>"
    out, offsets = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"), []
    for i, obj in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + (obj if isinstance(obj, bytes) else obj.encode("latin-1")) + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode() + b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)
