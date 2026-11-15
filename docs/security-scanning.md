# Security scans

This document describes the configured security checks, their trust boundaries,
and the reasons for existing exceptions. A scanner finding is evidence for the
specific revision, target, architecture and database used for that scan; a
successful run is not proof that the application has no vulnerabilities.

## Coverage and CI triggers

`.github/workflows/scan.yaml` runs these independent jobs:

| Scanner | Coverage | Trigger |
| --- | --- | --- |
| Trivy image | Vulnerabilities in the built Linux/amd64 `service` image, including OS and installed language packages | Pull requests to `main`, pushes to `main`, weekly schedule |
| Trivy filesystem | Vulnerabilities in supported manifests including `uv.lock` dev dependencies, plus supported configuration checks | Pull requests to `main`, pushes to `main`, weekly schedule |
| TruffleHog | Filesystem secret findings with `verified` or `unknown` results | Pushes to `main`, weekly schedule |
| Gitleaks | Secret findings in the checked-out Git history | Pushes to `main`, weekly schedule |
| Opengrep | Python source rules | Pushes to `main`, weekly schedule |

The weekly schedule is Monday at 00:00 UTC. The temporary push trigger for
`feature/58-trivy-security-scans` runs all jobs for branch verification and must
be removed before merging. `.github/workflows/codeql.yaml` separately runs
Python CodeQL on pushes to `main` and on the same schedule. Trivy is not a
replacement for source analysis or secret scanning.

Trivy reports LOW, MEDIUM, HIGH and CRITICAL findings, including unfixed
vulnerabilities; any reported finding at these severities fails its job. UNKNOWN
is outside the configured threshold. The image and filesystem JSON reports are
validated and uploaded separately as `trivy-image` and `trivy-fs` for 60 days.
The alert step evaluates the uploaded report rather than rescanning, so it uses
the same target and filtering. A failed build, scanner or database download,
invalid report, or missing artifact fails the job, not a clean result. Other
scanners use separate report and alert runs with matching rules and exclusions.
Treat reports as potentially sensitive before sharing them.

See [Trivy scan details](../.github/scan/README.md) for local commands, image
identity checks, and the full evidence for the image exception.

## Supply-chain safeguards and remaining trust

- The Trivy job uses a GitHub-hosted runner, read-only repository permission,
  and checkout without persisted credentials. It builds the `service` target
  from the current checkout and records and validates its revision, image ID
  and architecture. It does not use `pull_request_target` or deployment secrets.
- Trivy 0.76.2 is downloaded as a versioned release archive and checked against
  a SHA-256 digest recorded from the [official release](https://github.com/aquasecurity/trivy/releases/tag/v0.76.2).
  Its checkout and artifact-upload actions are pinned to full commit SHAs.
  Pinning detects later substitution; it does not prove that the original
  release or its publisher was uncompromised. Review upstream advisories when
  changing versions, including the [Trivy ecosystem incident](https://github.com/aquasecurity/trivy/security/advisories/GHSA-69fq-xp46-6x23).
- `uv.lock` records package versions and artifact hashes, and the image installs
  its exported requirements with `pip --require-hashes`. Base-image tags,
  Alpine packages and the Trivy vulnerability database still come from external
  services and can change independently. Filesystem misconfiguration checks are
  the checks embedded in the pinned Trivy binary.
- The other jobs have different, weaker provenance guarantees: TruffleHog and
  Opengrep are installed with scripts fetched from mutable upstream branches;
  Gitleaks is built from a Git tag; the Opengrep rules repository is cloned
  without a fixed revision. Their action references use version tags rather than
  commit SHAs. CodeQL also uses action version tags. These are remaining trust
  dependencies, not verified or immutable artifacts.

## Adding and reviewing exceptions

Prefer a compatible upgrade and a new scan. Do not suppress a finding solely to
make CI pass. For a proposed exception, record the scanner and finding ID,
affected component and version, target and analyzer, source/advisory links,
evidence that the affected code or platform does not apply, scope, and when to
reassess or remove it. Inspect installed files and embedded archives as well as
SBOM metadata; a lockfile version alone does not prove an image finding is false.

Use the narrowest matching fields available and fail closed: do not ignore a
whole package, path, SBOM, or CVE globally when only one instance is justified.
Keep report and alert filtering consistent. Verify the actual filtered report
and include a negative control, such as an unreviewed layer, version, package or
finding that must remain visible. Reassess exceptions when the image, platform,
scanner, rules, or relevant dependency changes; a changed layer requires its
own inspection. Image exceptions do not apply to filesystem scans by default.

## Current exceptions

### Trivy: setuptools metadata in pip's SBOM

The image-only policy `.github/scan/trivy-image-ignore.rego` excludes exactly
`CVE-2025-47273`, `CVE-2026-59890`, and `GHSA-xmj3-9gf7-h52w` for the SBOM
component `setuptools` 70.3.0 with its matching PURL, BOMRef and inspected
Linux/amd64 layer DiffID. The inspected image had no installed or importable
setuptools distribution; its `ensurepip` wheel and installed pip SBOM listed
the component. pip documents that its vendored setuptools content is limited to
`pkg_resources`. The findings concern `PackageIndex`, sdist manifest processing,
and Windows legacy wheel installation respectively, not the inspected component
paths. Details, evidence and advisory links are in the
[Trivy scan guide](../.github/scan/README.md#image-only-exception-pips-setuptools-sbom).

The policy is applied only to the image JSON report and therefore also to its
alert. A different CVE, package, version, PURL/BOMRef or DiffID stays visible.
The separate filesystem dependency was upgraded to setuptools 84.2.1; no FS
exception was added. The bundled `ensurepip` wheel contains other vendored
components and this exception does not suppress their findings.

### Gitleaks: historical findings

`.github/scan/gitleaks-ignore.txt` contains exact commit/path/rule/line fingerprints
from the reports reviewed in issue #56. Test values are synthetic and current
fixtures use short, explicit dummy values. Deployment Compose no longer embeds the
historical encryption key: it reads configuration from the environment.
The 19 entries cover 17 historical `generic-api-key` matches in secret-generation
and vendor-encryption unit tests, and two matches for the former Compose key.
Each fingerprint is tied to a particular commit, file, rule and line; it does not
approve the same value in new code or another location.

Never ignore an entire path or secret rule to silence a historical finding. Both
Gitleaks steps pass `--gitleaks-ignore-path` explicitly and redact scan output,
including uploaded JSON reports. New findings still fail the alert step.

An ignore entry does not revoke an exposed credential. If the historical Compose
key was used in a deployment, the operator must replace it and re-encrypt stored
vendor credentials. API tokens exposed in old DEBUG logs must also be revoked and
reissued; remove sensitive retained logs according to the deployment's policy.

## Failure diagnostics

Keep failure logging when fixing scanner findings. Startup failures are CRITICAL;
database initialization, connection checks, transaction begin/commit/rollback,
operation failures and cleanup emit WARNING before propagating to their caller.
The API error boundary logs the final failure with request method and path.

`src/db/diagnostics.py:failure_details` records exception types and causal chains, stack locations
(filename, function, line), validated PostgreSQL SQLSTATE with known explanations,
schema/table/column/constraint identifiers, and operating-system errno. SQLSTATE
explanations follow the [PostgreSQL error code catalog](https://www.postgresql.org/docs/current/errcodes-appendix.html).
This remains available at normal log levels. Exception
messages, SQL statements, bound values, local variables and request payloads are
excluded, including in DEBUG. SQLAlchemy's native `hide_parameters=True` also
protects its own parameter logging. Unexpected API failures keep a generic public
response; internal diagnostics stay in logs.

Propagated failures use WARNING to distinguish them from the final handled error,
as recommended by the scanner's logging rule. Do not delete these records or
silence security rules globally to make scans pass. Regression tests must prove
that failures remain diagnosable without leaking data.

## Opengrep: rule and template exceptions

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
