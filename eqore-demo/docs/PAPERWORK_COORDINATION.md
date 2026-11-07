# Paperwork coordination: scope, evidence, and test-account integration

The [November 7 client calibration](CLIENT_CALIBRATION.md) adds EQORE's actual option-4 brief, source-linked site/equipment references and a separate 20-requirement document coverage review. The original D01–D20 records below are preserved as demonstration history. Specific compliance records are adopted individually with PM-selected deadlines; generic packet completion does not automatically satisfy them.

This direction comes from the user's report of a client conversation: a PM may coordinate about eight projects, with approximately twenty documents per project, and needs to know whom to contact and what is holding up the next step. Those numbers are design inputs, not an independently verified EQORE operating procedure. The user selected DocuSign test-account integration and corrected the mailbox provider to Gmail. Actual email connection remains deferred; no Google client ID or mailbox authorization is assumed. An existing provider account is not evidence of app registration, OAuth consent, or a working API connection.

## What changes from the installation workspace

| Existing installation workspace | Paperwork workspace |
| --- | --- |
| Three detailed deployment scenarios; schedule, budget, vendor offers and physical gates | Eight active projects assigned to Jordan, two assigned to Casey, and two closed archives |
| Contractor reports lead to proposed scope, resource and schedule changes | Documents, counterpart responses, originals, revisions and follow-up drafts |
| Bookings, design acceptance, receipt and operating authorization remain separate | Signature, review acceptance, record receipt and email acknowledgement remain separate |
| Decision rationale explains the current bottleneck and permitted action | Document priority explains the waiting recipient, deadline and prerequisite |

The additional paperwork projects do not claim to have fully modeled installations. A document's completion does not change the physical engine's permit, equipment receipt, construction or operating gates. The sample PM selector provides local portfolio filtering; it is not production authentication.

Each portfolio summary and selected project exposes a `profile`: industry, battery power and energy, scope, contract and target-handover dates, delivery model, site constraints, utility, contract baseline and provenance. Harbor, Millbrook and Riverbend reuse the original delivery-case sizes, baseline budgets and target dates. The other nine project briefs contain authored commercial assumptions, not verified client data or engineering designs. Millbrook's paperwork contract date is authored for the November 7 post-signing clock; its separate delivery scenario's November 16 signature date is not copied into this earlier view. Utility names remain unrecorded because service territories have not been verified.

The displayed baseline is not actual spend or the budget after later change orders. Profiles are read-only enrichment: existing saved profile fields, including explicit null or empty values, take precedence; missing fields receive case defaults. No database reset, document-state change or authority inference is needed to show the briefs. Source provenance belongs in About/documentation rather than repeated labels on every project card.

## Illustrative twenty-document template

These are coordination records for a post-signing demonstration. Required documents, signatories and sequencing depend on the actual customer contract, project design, jurisdiction and utility. A row can represent a packet containing several source documents. It is not a claim that each installation requires exactly twenty documents or that authorities use DocuSign.

| ID | Record | Kind | Coordination owner → required counterparts | Prerequisites |
| --- | --- | --- | --- | --- |
| D01 | Executed customer agreement | record | PM → commercial | — |
| D02 | Kickoff and responsibility review | review | PM → EPC, facilities | D01 |
| D03 | Site-survey record | record | EPC → engineer | D02 |
| D04 | Issued-design review | review | engineer → EPC | D03 |
| D05 | Customer implementation acknowledgement | e-sign | PM → customer, facilities | D04 |
| D06 | Permit submission record | record | engineer → submitting engineer | D04 |
| D07 | Issued permit and fire-review records | record | PM → AHJ and fire record issuers | D06 |
| D08 | Utility application record | record | engineer → submitting engineer | D04 |
| D09 | Utility comments disposition | review | engineer → utility | D08 |
| D10 | Installation-stage utility review record | record | PM → utility | D09 |
| D11 | Supplier order acceptance | e-sign | commercial → commercial, supplier | D04 |
| D12 | EPC and electrical scope agreement | e-sign | PM → commercial, EPC, electrician | D04 |
| D13 | Installation and lift-method review | review | EPC → engineer, rigger, electrician | D11, D12 |
| D14 | Change-control disposition | review | PM → commercial, EPC | D12 |
| D15 | Site-readiness and receiving packet | record | EPC → facilities, EPC | D07, D10, D13, D14 |
| D16 | Customer shutdown authorization | e-sign | PM → facilities, customer | D05, D12 |
| D17 | Field verification and correction record | record | engineer → engineer, electrician | D15, D16 |
| D18 | Test and witness results review | review | controls → engineer, utility | D17 |
| D19 | Utility operating-acceptance record | record | PM → utility | D18 |
| D20 | Customer and fleet handoff acceptance | e-sign | PM → customer, fleet | D19 |

D01 records the already executed agreement; it does not reopen sales. D14 records whether a change is needed and its disposition; it does not invent a mandatory change order. D07 requires distinct records from the applicable issuers. D10 is not permission to operate. D18 can cover authorized testing before operating acceptance; the exact test permissions remain site-specific. D19 stores the utility's issued record rather than making the PM a utility approver. Completion of this paperwork template alone is insufficient for project closeout; explicit PM closeout attestation is additionally required.

## Evidence and event contract

Every observation must resolve to the current project, document revision and provider envelope; recipient observations additionally resolve to a configured provider-recipient ID and project stakeholder. Preserve originals and event IDs, source timestamps, received timestamps, revision history and source mode. Duplicate events must be harmless; conflicting IDs, stale revisions, older responses and cross-project observations need review. Reworking a predecessor can invalidate a dependent document's current applicability without deleting its historical signatures.

For DocuSign, recipient completion means that recipient finished their actions, which are not always signing. Envelope completion means all recipients completed. `delivered` means viewed in DocuSign, not delivered email. Keep envelope status and individual recipient statuses separate, and distinguish signer roles from copy recipients. [DocuSign event definitions](https://developers.docusign.com/platform/webhooks/connect/event-triggers/)

An email saying “signed,” a PM summary, or a successful signing-page redirect is a cue to retrieve evidence. It is not a replacement for the provider's envelope and recipient state. LLM summaries and follow-up suggestions should cite original message IDs, preserve uncertainty, and never silently create signatures or regulatory acceptance.

## Implemented adapter boundary

`paperwork_connectors.py` uses the Python standard library. It exposes:

- `PaperworkConnectors(env=None, transport=None).status()` — configuration and last explicit connection-test result; loading a token alone does not mean connected.
- `test_connection(provider)` — an authenticated, read-only check for `docusign`, `graph` or `gmail`.
- `reconcile_envelopes(mappings)` — at most twenty explicit project/document/revision/envelope mappings; returns observations and per-mapping errors.
- `pull_mail(provider, scope, limit=20)` — searches for a literal document token in the subject and checks the match before retrieving message text. It returns originals for review, not status transitions.
- `create_envelope_draft(payload)` and `recover_envelope_draft(payload)` — a sandbox draft and transaction recovery; no invitation is sent.
- `create_mail_draft(provider, payload)` — an Outlook or Gmail draft; no mail is sent.

All provider URLs are fixed and allowlisted; redirects are disabled, calls time out after fifteen seconds, and errors omit raw provider bodies and credentials. Tokens remain server-side. There are no send or recipient-view operations in this adapter. Mail pagination is reported as `has_more`; the initial adapter does not claim a complete mailbox history or download attachments. The server must enforce PM membership and exact document revision before calling it.

| Environment variable | Purpose |
| --- | --- |
| `EQORE_DOCUSIGN_ACCESS_TOKEN` | Short-lived token for the developer/sandbox account |
| `EQORE_DOCUSIGN_ACCOUNT_ID` | API account ID associated with that token |
| `EQORE_GMAIL_ACCESS_TOKEN` | Delegated Gmail token; selected mailbox provider, currently unconfigured |
| `EQORE_GRAPH_ACCESS_TOKEN` | Optional Outlook/Microsoft 365 adapter token |

Do not put tokens into source files, screenshots, chat, browser JavaScript or Git. The environment-token path is an initial integration mechanism, not automatic OAuth refresh. Operator-supplied environment credentials are process configuration. OAuth credentials are instead isolated per PM session in memory. The UI must report unconfigured, not tested, connected or error accurately. A successful connection test only proves that the tested read endpoint was accessible at that time; it does not certify draft-write permissions.

`paperwork_oauth.py` implements authorization-code PKCE for `docusign`, `gmail` and optional `graph`. `begin(provider, session_binding, client_id=None, tenant_id=None)` produces a provider authorization URL. `complete(provider, query, session_binding)` validates a ten-minute, single-use state tied to that PM session, exchanges the code, and returns only authorization metadata. `credentials(provider=None, session_binding=...)` is a **server-only** accessor; never return it in JSON. `status(session_binding=...)` is safe to display. `forget(session_binding)` clears that session's in-memory credentials and pending flows without claiming provider revocation. Tokens are not persisted or automatically refreshed. Expired tokens are excluded from the accessor.

Public app configuration uses `EQORE_DOCUSIGN_CLIENT_ID`, `EQORE_GMAIL_CLIENT_ID`, `EQORE_GRAPH_CLIENT_ID` and optional `EQORE_GRAPH_TENANT_ID` (default `organizations`). A Google client ID ends in `.apps.googleusercontent.com`; it is not a UUID. Optional `EQORE_GMAIL_CLIENT_SECRET` and `EQORE_GRAPH_CLIENT_SECRET` must belong to their respective configured client IDs and remain server-side. The DocuSign path uses public PKCE without a client secret. OAuth callbacks use `http://localhost:8765/api/paperwork/oauth/callback/docusign` and the same path ending in `gmail` or `graph`. Start OAuth on `localhost`, not `127.0.0.1`, so the session cookie matches the callback origin. Suppress callback query strings in HTTP logs.

Envelope draft input includes `project_id`, `document_id`, `document_revision`, stable `request_id`, `subject`, base64 documents and named recipients with email addresses and recipient IDs. The adapter forces `status=created` and returns the envelope ID, transaction ID and recovered flag. It does not return a signing link. The caller must durably bind the returned envelope before another create, serialize concurrent requests, reject reuse of an idempotency key for different content and preserve ambiguous outcomes. DocuSign transaction lookup is available for seven days; it is not a permanent deduplication store. [Envelope creation](https://developers.docusign.com/docs/esign-rest-api/reference/envelopes/envelopes/create/), [transaction recovery](https://developers.docusign.com/docs/esign-rest-api/reference/envelopes/envelopes/liststatuschanges/)

Mailbox draft input includes `project_id`, `document_id`, recipient addresses, subject and body. The matching token defaults to `EQORE-{project_id}-{document_id}`; a caller can provide a stricter revision-specific simple token. Draft creation adds the token if absent. Subject matching narrows retrieval but does not authenticate a sender or prove that an email belongs to the correct business revision. Draft request results also need durable records: an ambiguous network failure must not trigger automatic repeated creation. [Outlook draft creation](https://learn.microsoft.com/en-us/graph/api/user-post-messages?view=graph-rest-1.0), [Gmail draft creation](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.drafts/create)

## Connecting the selected test accounts

1. When email connection is requested, enable Gmail API in the team's Google Cloud project and configure the consent screen and intended test users. For local desktop use, choose a **Desktop app** OAuth client and PKCE; Google supports loopback redirects, including `localhost`. This app's callback is `http://localhost:8765/api/paperwork/oauth/callback/gmail`. A **Web application** client instead needs that exact authorized redirect URI and its secret supplied through `EQORE_GMAIL_CLIENT_SECRET`. Open consent in the system browser; Google can reject embedded user-agents. The installed flow's client secret is optional. [Google desktop OAuth](https://developers.google.com/identity/protocols/oauth2/native-app), [web application OAuth](https://developers.google.com/identity/protocols/oauth2/web-server)
2. Request `gmail.readonly` for message text and `gmail.compose` for draft creation. Google defines compose as managing drafts **and sending**; there is no draft-only permission at this scope level. Our API adapter permits draft endpoints and has no send operation. Both scopes are classified as restricted; a published integration must meet Google's applicable verification requirements. This implementation requests online access only and rejects explicitly partial scope grants. [Gmail scope definitions](https://developers.google.com/workspace/gmail/api/auth/scopes)
3. In the DocuSign **developer** account's Apps and Keys, configure the team's integration key and register `http://localhost:8765/api/paperwork/oauth/callback/docusign`. For this local implementation select the public authorization-code flow, no stored client secret, and **Native OS Application** with PKCE. Do not borrow an unrelated application's client ID. Sandbox OAuth uses `account-d.docusign.com`; OAuth user information verifies account membership and API base URI. This adapter intentionally permits only `demo.docusign.net`. A production DocuSign login alone does not configure a sandbox account. [App configuration](https://developers.docusign.com/platform/configure-app), [authorization choices](https://developers.docusign.com/platform/auth/authcode), [public PKCE flow and account discovery](https://developers.docusign.com/platform/auth/public-authcode-get-token)
4. For each account the user authorizes connecting, test read access and configure actual test counterpart addresses before creating a reviewed provider draft. Verify its provider ID and content. Leave deferred email providers unconfigured. Seed addresses under `example.invalid` are placeholders. There is no actual-account connection claim until authenticated checks succeed.

Microsoft Graph remains an optional alternative. Register the team's own Entra app, use an appropriate Web or desktop platform, and match `http://localhost:8765/api/paperwork/oauth/callback/graph`. Its delegated `Mail.ReadWrite` scope supports reading and draft creation without `Mail.Send`. [App registration](https://learn.microsoft.com/en-us/graph/auth-register-app-v2), [authorization flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow), [draft permissions](https://learn.microsoft.com/en-us/graph/api/user-post-messages?view=graph-rest-1.0)

A draft-envelope management location is not a signing link. Embedded signing requires a sent envelope and a recipient-specific view generated after authenticating that recipient. The returned URL expires after five minutes and is single-use, so it must not be saved as a reusable email link. A future email invite should point to the application's authenticated entry page, which generates a fresh view. [Recipient-view API](https://developers.docusign.com/docs/esign-rest-api/reference/envelopes/envelopeviews/createrecipient/)

## Event delivery and reconciliation plan

For DocuSign Connect, validate HMAC against the exact raw request bytes before queueing any business event. Keep the delivery record durable, acknowledge quickly, then process asynchronously with idempotency and current-revision checks. Reconcile known envelope IDs after uncertain or missed delivery; do not constantly scan the whole account. The adapter currently provides explicit pull reconciliation, not a public Connect listener. [HMAC verification](https://developers.docusign.com/platform/webhooks/connect/hmac/), [listener implementation](https://developers.docusign.com/platform/webhooks/connect/implement), [listener practices](https://developers.docusign.com/platform/webhooks/connect/build-listener)

For Microsoft Graph, add a renewable message subscription, endpoint validation, `clientState` checks, lifecycle handling and mailbox reconciliation. A notification is a change cue, not a full authoritative document event. Validate and queue before acknowledging; Graph retries failed delivery, and slow endpoints can lose notifications. These subscription operations are not implemented by the initial pull adapter. [Graph webhooks](https://learn.microsoft.com/en-us/graph/change-notifications-delivery-webhooks), [Outlook notifications](https://learn.microsoft.com/en-us/graph/outlook-change-notifications-overview)

For future Gmail background updates, configure Cloud Pub/Sub and a mailbox watch. Its notification provides a mailbox history cursor; use `history.list` and message reads. Renew watches at least every seven days, preferably daily. Handle dropped notifications with periodic reconciliation and expired history with a full resync. The present adapter supplies explicit token-scoped reads rather than this background service. [Gmail push](https://developers.google.com/workspace/gmail/api/guides/push), [Gmail synchronization](https://developers.google.com/workspace/gmail/api/guides/sync)

## Completion checks and remaining production work

Tests should cover: one signer completing while another waits; all signer observations arriving before envelope completion; duplicate and reordered events; stale revision replies; sender/name ambiguity; wrong project/envelope mappings; rejected reviews requiring rework; archive attempts with incomplete or stale records; unconfigured and expired credentials; redacted provider errors; retries after an uncertain draft creation; OAuth replay and cross-session callbacks. Run `python3 -m unittest tests.test_paperwork_connectors tests.test_paperwork_oauth -v` for the isolated adapter and OAuth contracts.

The local sample uses authored openings and explicit sample events; no sample action contacts an authority, vendor or customer. Production still needs authenticated users and tenant/PM authorization, durable encrypted per-user tokens, refresh/revocation, provider webhook infrastructure, subscription renewal, mailbox delta recovery, versioned document storage, attachment handling, recipient verification, monitored retries and clear retention rules. Actual dispatch, signing links and provider acceptance must be separately implemented and verified before the interface claims those capabilities.
