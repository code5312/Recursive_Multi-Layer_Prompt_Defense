Test Suite Layout
=================

The test tree is scaffolded but currently empty. Populate the folders as the
project matures:

- `tests/unit/` – fast tests that cover individual functions or classes.
- `tests/integration/` – multi-component checks (e.g. orchestrator + tool
  registry).
- `tests/e2e/` – full pipeline scenarios that hit the public API.

Tips:

1. Mirror real-world attack/benign cases with lightweight fixtures.
2. Tag long-running evaluations with `@pytest.mark.slow` so they can be skipped
   in CI.
3. Update `README.md` once representative tests land, or delete this file if the
   directories are reorganised.

