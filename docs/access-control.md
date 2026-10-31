# Feature access control

Read this guide before adding a feature. `AGENTS.md` defines the required workflow;
this document explains the design and extension points. The executable permission
catalog is `src/modules/auth/permissions.py`.

## Invariants

- An independently usable feature has its own permission and admin checkbox.
  Additional endpoints or operations of an existing feature inherit its permission.
  Bug fixes and internal refactoring do not introduce new permissions.
- Active users pass a feature check when `is_admin` is true or its explicit flag
  is true. `is_admin` is superuser access, including permissions introduced later.
- All new feature flags default to false in Python and the database, including
  for existing users. Preserve existing `is_admin` values during upgrades.
- Inactive users and inactive/invalid API tokens remain blocked for superusers.
- Resolve users and their permissions on every request. Sessions and tokens store
  identity, not permission snapshots. Changes take effect on the next request.
- Feature access does not bypass record ownership rules.
- Missing/invalid API authentication returns 401; missing feature permission
  returns 403. Anonymous browser requests redirect to `/login`.
- UI visibility complements server authorization. Do not fetch restricted widget
  data even if the corresponding HTML would be hidden.

## Current features

| Permission | User flag | Protected functionality |
| --- | --- | --- |
| `ADMIN_PANEL` | `can_access_admin` | Admin login, user/permission management and existing administrative configuration |
| `SYSTEM_API` | `can_access_system_api` | System health and information API |
| `LLM` | `can_use_llm` | Model listing, chat completions, streaming and cancellation through the proxy API |
| `TIME_TRACKING` | `can_use_time_tracking` | Tracker pages, timer/entry operations and Dashboard tracking widgets |
| `BILLING` | `can_access_billing` | Balance API and Dashboard balance widget |

Admin Panel access lets its holder manage users and permissions. It does not
automatically authorize feature APIs or web pages. Existing admin management views
keep `ADMIN_PANEL` as their policy. A new independently usable feature exposed in
SQLAdmin declares its own permission, in addition to the panel login requirement.

## Add a feature

1. List all entry points: API operations, browser pages/forms, SQLAdmin views and
   actions, navigation and widgets. Choose a new permission for a new feature.
2. Add the `Permission` member and its `PermissionDefinition` metadata. The enum
   value is the stable `User` column name. Admin checkboxes, descriptions and
   detail labels are derived from the catalog.
3. Add an explicitly typed, non-null boolean field to `User`, with `default=False`
   and `server_default=sa.false()`. Add a new Alembic revision. Never import the
   live catalog into a migration: historical revisions must remain reproducible.
4. Use standard `APIRouter(dependencies=[Depends(APIAccess(Permission.NEW_FEATURE))])`
   for API routes, or `Depends(WebAccess(Permission.NEW_FEATURE))` for web routes.
   Inject the same `WebAccess` instance with `Depends` to obtain the authorized
   user; FastAPI reuses its result within the request.
5. Declare `required_permission = Permission.NEW_FEATURE` on a new functional
   SQLAdmin view. The configured `GrantsAuthorizationBackend` supplies per-request
   view grants; SQLAdmin protects direct URLs, actions and menu items itself.
6. Set the navigation item's permission and use `has_permission` before fetching
   widget data. Templates receive `feature_access`, keyed by permission value.
7. Update faithful test doubles and add HTTP tests for every new operation:
   no permission, correct permission, unrelated permission, superuser, inactive
   user/token and revocation through existing credentials. Verify hidden controls
   and that restricted data providers were not called.
8. Run catalog consistency and route coverage tests, migration tests, the relevant
   behavioral tests, and the normal lint/test gates. Update the feature table here.

## Route policies and exceptions

Use FastAPI's native `APIRouter` and `Depends` with the parameterized `APIAccess`
and `WebAccess` dependencies. Public routes need no placeholder dependency.
The route validator inspects effective registered routes, including
nested router prefixes and dependencies. A route without a policy fails validation.
Adding a business endpoint to a public or authentication-only router also fails.

The deliberate exceptions are GET/POST `/login`, POST `/logout`, and the
authentication-only Dashboard GET `/`. Static assets and FastAPI's own generated
documentation routes are infrastructure. LLM OPTIONS handlers retain their
unauthenticated CORS preflight behavior; they do not return feature data. SQLAdmin
owns its internal routes and authenticates through `AdminAuth`; each registered
application admin view must declare its required permission.

SQLAdmin's `GrantsAuthorizationBackend` maps these declarations to `(identity, "*")`
grants after `AdminAuth` reloads the user. Its native checks cover menu visibility,
CRUD and custom actions. Grants live only on the current request. Shared view
bases declare metadata and application types; they do not override library access
checks. No separate RBAC package or custom router subclass is needed.

Imports stay in the module's top import section. `src/application.py` holds the
shared application type, and the web package does not eagerly import its views;
neither admin views nor authentication dependencies need delayed imports.

Validate routes during app construction and again after mounting SQLAdmin at
startup. CI also runs negative tests that add unprotected or misclassified routes.
Keep explicit behavioral request cases: route coverage detects missing policy,
while HTTP tests prove actual authorization and side-effect boundaries.

## Migrations and verification

Migration `0006` initialized the five original flags as false without changing
accounts, tokens or existing application data. Existing non-superusers needed
explicit grants after that upgrade.

Historical migration tests use the schema and columns of that revision, not the
current `User` model or `Permission` enum. Separately, a PostgreSQL migration-chain
test upgrades an empty disposable schema to the current head and compares it with
the current model/catalog. Never execute that test against application tables.

Production storage is PostgreSQL. SQLite-based HTTP and historical migration tests
are useful local checks, but do not replace the PostgreSQL chain test. Report any
environment-related verification limits explicitly.

## HTTP end-to-end verification

`src/tests/e2e` runs the real application in a separate Uvicorn process against a
disposable PostgreSQL database. It provisions users and tokens through actual HTTP
handlers and checks both successful and denied API calls. Only external billing
and LLM providers are replaced with local HTTP servers.

Run `make test-e2e` locally using `DB_PASSWORD` from the environment or `.env`
(`E2E_POSTGRES_PASSWORD` overrides it), or
`make test-e2e-in-docker` with the Compose test environment. Both commands isolate
the suite from parent test fixtures using `--confcutdir`; do not remove that option.
`make test-full` runs the regular suite with coverage, then API e2e, stopping if
either stage fails.
The default pytest selection excludes the `e2e` marker. CI runs the e2e target as
a separate required step for PRs, main on AMD64/ARM64, and release tags.

Extend the independent role/operation matrix when adding an API feature. See
[the e2e guide](../src/tests/e2e/README.md) for setup and artifact locations.
