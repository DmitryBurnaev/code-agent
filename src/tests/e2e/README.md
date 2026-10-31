# API access end-to-end suite

This suite starts the unmodified application in a separate Uvicorn process and
uses HTTPX over a real TCP connection. It creates a uniquely named PostgreSQL
database, applies the real Alembic chain, and removes that database at teardown.
It is isolated from `src/tests/conftest.py` and its mocked repositories through
pytest's standard `--confcutdir=src/tests/e2e` option.

User creation, permission changes, token issuance, and token activation use the
actual SQLAdmin HTTP handlers. No browser or UI layout is tested. SQL reads verify
persisted flags and hashed token storage; they do not provision users or tokens.
The initial administrator is created by migration `0001`.

Only external services are substitutes: a local HTTP server supplies Selectel
billing and OpenAI-compatible model/chat/stream/cancellation responses. Real
provider credentials, paid requests, Selectel IAM, TLS, and reverse proxies are
outside this suite. No dependency overrides, monkeypatches, SQLite, in-process
ASGI transport, or mocked authentication are used.

## Run

Requirements: synced project dependencies, PostgreSQL with permission to create
and drop a disposable database, and free loopback ports. The password defaults to
the standard `DB_PASSWORD` from the environment or the project's `.env`, using
`DBSettings` and its default when neither is set. Set `E2E_POSTGRES_PASSWORD` only
to override that password. Optional connection settings are
`E2E_POSTGRES_HOST` (default `127.0.0.1`), `E2E_POSTGRES_PORT` (`5432`), and
`E2E_POSTGRES_USER` (`postgres`). No application database name is accepted: the
suite always generates its own `code_agent_e2e_<uuid>` database.

From the repository root, run:

```sh
make test-e2e
```

To run the regular suite with coverage first, followed by API e2e:

```sh
make test-full
```

This stops on the first failed stage and keeps the suites sequential, including
with `make -j`. The regular suite uses its existing `.env`/database configuration;
e2e uses the password fallback above and creates its own temporary database.

```sh
E2E_POSTGRES_HOST=127.0.0.1 E2E_POSTGRES_PORT=5432 E2E_POSTGRES_USER=postgres make test-e2e
```

```sh
make test-e2e-in-docker
```

The Docker command uses the existing Compose test image and database, with
credentials supplied by the Compose environment. It starts the database dependency
if necessary and propagates pytest's exit code. It does not need uv or make inside
the image. CI invokes this target after the regular suite for pull requests, main
(AMD64 and ARM64), and release tags.

Both targets select the `e2e` marker explicitly and exclude parent conftests. The
default pytest selection is `not e2e`, so the regular suite does not run this
database/process fixture or count its cases as skipped. Direct pytest invocations
must preserve `--confcutdir=src/tests/e2e -m e2e` and set `RUN_API_E2E=1`.

The password is resolved before the fixture changes to a fresh temporary working
directory. Application settings and migrations then load from that isolated
directory, which Uvicorn uses too. The application uses generated test settings
and a disposable database, rather than the application database named in `.env`.
No source copy or additional configuration file is needed. Local execution uses
`/opt/homebrew/bin/uv` when installed; `UV` can be overridden for other environments.

`results.json` records expected/actual API statuses, response bodies, upstream
call counts, provisioning statuses, and environment/cleanup metadata. It excludes
passwords, raw API tokens, and authentication headers. JUnit records individual
pytest results. Local artifacts default to `.local/test-results/api-e2e`; override
`E2E_ARTIFACT_DIR` to preserve another run. Docker execution writes to `/tmp/api-e2e`
inside its disposable container; CI reports pass/fail in the job log.

The suite is opt-in and excluded from the default selection. Add each new API
feature to the independent role/operation matrix and
the provider fixture when necessary. Keep the explicit expected permissions;
do not infer expected access from the application's authorization implementation.

An interrupted process may leave its generated database behind. Only remove the
exact database recorded in that run's artifacts; never clean an application
database to reset this suite.
