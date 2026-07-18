# Development guidelines

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
