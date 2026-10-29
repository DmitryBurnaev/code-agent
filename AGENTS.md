# Development guidelines

## Simplicity and imports

- Prefer standard Python, FastAPI and installed-library extension points over
  custom infrastructure. Check the available library API before introducing
  a wrapper, subclass or new dependency.
- Keep imports at the top of the module, with type-only imports in the top-level
  `TYPE_CHECKING` section. Imports inside functions, methods and other runtime
  blocks are forbidden, including in tests. Ruff enforces `PLC0415`.
- Resolve circular dependencies by correcting module boundaries and extracting
  shared types into neutral modules. Never hide a cycle with a local import.

## Feature access control

- Read [docs/access-control.md](docs/access-control.md) before adding or extending
  application features. Update it when the access model changes.
- Every new independently usable feature must ship with its own `Permission`
  and checkbox in the admin user form. Additional operations within an existing
  feature must enforce that feature's permission.
- A new permission requires a disabled-by-default `User` field, a new Alembic
  migration, catalog metadata, server-side enforcement, UI visibility rules,
  tests, and documentation. Never edit historical migrations to add a permission.
- Register business HTTP endpoints through standard `APIRouter` with an explicit
  `Depends(APIAccess(...))` or `Depends(WebAccess(...))` access policy. Public and
  authentication-only exceptions are deliberately limited; do not broaden them
  to bypass feature authorization.
- Use shared permission checks. Preserve the `is_admin` superuser override,
  inactive-user/token restrictions, request-time permission reloads, and data
  ownership rules. Do not store permission snapshots in sessions or API tokens.
- Hide restricted controls and skip fetching their data. Declare an explicit
  permission on every admin view; administrative configuration remains covered
  by `ADMIN_PANEL`, while new feature pages require their feature permission too.
- Verify denied access, explicit grants, superuser access, and revocation through
  existing sessions/tokens. Include every new entry point in behavioral tests.
- Do not finish feature work until catalog consistency, route-policy coverage,
  relevant migration tests, and the normal lint/test gates pass.

## Test typing

- Treat `src/tests` as typed code. `make lint` checks production code strictly
  and test modules through the `src.tests.*` override in `pyproject.toml`.
- Keep all tool configuration in `pyproject.toml`; do not add separate tool
  configuration files unless the repository cannot express the setting there.
- Keep test doubles faithful to the interface used by production code. Prefer a
  real domain model or a spec-based mock; do not add attributes dynamically to
  a loosely typed fake.
- When a framework object is impractical to construct (for example, a request
  with only a session), isolate a justified `cast` in a named test helper
  instead of scattering casts or `type: ignore` comments through tests.
- Annotate fixtures, including generator fixtures, with their yielded type.
