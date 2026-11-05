# Security scans

`.github/workflows/scan.yaml` scans source with Opengrep and Git history with
Gitleaks. Report and alert steps must use the same rules and exceptions.

## Historical Gitleaks findings

`.github/scan/gitleaks-ignore.txt` contains exact commit/path/rule/line fingerprints
from the reports reviewed in issue #56. Test values are synthetic and current
fixtures use short, explicit dummy values. Deployment Compose no longer embeds the
historical encryption key: it reads configuration from the environment.

Never ignore an entire path or secret rule to silence a historical finding. Both
Gitleaks steps pass `--gitleaks-ignore-path` explicitly and redact scan output,
including uploaded JSON reports. New findings still fail the alert step.

An ignore entry does not revoke an exposed credential. If the historical Compose
key was used in a deployment, the operator must replace it and re-encrypt stored
vendor credentials. API tokens exposed in old DEBUG logs must also be revoked and
reissued; remove sensitive retained logs according to the deployment's policy.

## Opengrep rule selection

The Python ruleset remains enabled, including all security rules. Two
maintainability heuristics are excluded by their exact IDs:

- `is-function-without-parentheses` treats every `is_*` attribute as a method,
  including typed SQLAlchemy booleans and HTTPX properties.
- `return-not-in-function` flags valid lambda expressions.

Ruff and mypy check the corresponding Python syntax and type errors. The
`--no-rewrite-rule-ids` option keeps IDs independent of the checkout/config path
so these exact exclusions work in both local scans and CI. Type aliases use
`TypeAlias` declarations because the scanner still partially parses files with
PEP 695 `type` statements. The alert step uses `--strict` so parsing errors also
fail the scan.

The Django `csrf_token` template rule does not understand our ASGI middleware.
Forms carry narrowly scoped `nosemgrep` comments referencing
`CSRFProtectionMiddleware`, whose HTTP regressions cover all current mutations.
Do not copy these exceptions into templates served outside that middleware.

## Browser request forgery protection

Web and admin mutations require a source matching the request's scheme, hostname
and effective port. `Origin` is authoritative; `Referer` is used only if `Origin`
is absent. Missing, opaque, malformed and foreign sources return 403 before any
form parsing, authentication or data mutation. `Sec-Fetch-Site: cross-site` is
also rejected. The check includes login, logout, imports, CRUD and SQLAdmin's GET
actions. Regular navigation and preflight requests remain available.

This follows the [OWASP origin verification guidance](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html#using-standard-headers-to-verify-origin).
Clients submitting browser forms must send a same-origin `Origin` or `Referer`;
privacy tools that remove both headers will receive 403. The reverse proxy must
preserve Host and set the original scheme through trusted proxy headers. Never
trust arbitrary client-supplied forwarded hosts to make the check pass.

`/api` uses explicit Authorization credentials and does not authenticate through
session cookies, so it is excluded from browser CSRF checks. Feature permissions
and ownership checks still apply to both browser and API routes.
