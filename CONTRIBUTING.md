# Contributing to flashpi

Read [docs/decisions.md](docs/decisions.md) first: it records why the SDK is built the way it
is. Decisions about the product (names, behavior, releases) belong to the Flashpi team: ask
before changing them.

## Setup

[uv](https://docs.astral.sh/uv/), which installs the Python of `.python-version` (3.13) and the
locked dependencies:

```bash
uv sync
```

## Checks

Run the same checks as CI before every commit:

```bash
uv run ruff format --check . && uv run ruff check . && uv run pyright && uv run pytest
```

- `uv run pytest` measures coverage (it fails below 95 %) and also checks that the generated types
  match `openapi/openapi.json` and that `tests/examples/readme/` matches the READMEs.
- `uv run pyright` is strict and covers `src`, `tests` and `scripts`, the README examples
  included. `tests/test_resource_types.py` is only type-checked: it holds what a user's type
  checker must accept and refuse.
- CI also runs the tests on Python 3.11 to 3.15, and on Python 3.11 with the oldest version of
  each direct dependency (`uv sync --resolution lowest-direct`, which rewrites `uv.lock`: do it in
  a scratch copy).
- `uv build && uv run python scripts/package_check.py` builds the sdist and the wheel and fails on
  anything missing or extra in them. CI then installs the wheel alone in a clean environment and
  runs `scripts/installed_check.py` with it.
- `uv run pytest -m live --no-cov` calls the real API in test mode. It needs
  `FLASHPI_TEST_API_KEY` (an `fp_test_` key, read_write) and `FLASHPI_DEMO_ISSUER_ID`, and issues
  one test invoice on the demo issuer, which has a daily quota: run it only when needed.

## Code conventions

- English for code, identifiers, comments and commit messages. The READMEs are in Spanish
  (`README.md`) and English (`README.en.md`); keep both in step. Every python block in them is
  checked: after changing one, run `uv run python scripts/readme.py generate`. A block must be a
  whole module (no `await` outside a function); names it takes from an earlier block come from
  `tests/examples/readme/_context.py`.
- Python 3.11 or later, pyright strict, Ruff for lint and format (line length 100).
- The SDK has **one runtime dependency**, httpx (`>=0.27,<1`). Models are `TypedDict`s generated
  from the OpenAPI document, with the API's camelCase keys; no pydantic.
- `Flashpi` and `AsyncFlashpi` share every behavior: retries, idempotency, recovery and errors run
  once, in `_http.plan()`, and each operation is declared once (a `RequestSpec` function in
  `src/flashpi/resources/`) for both clients.
- Resource methods mirror the API in snake_case: `create`, `list`, `get`, `update`, `delete`,
  then actions named after the operation (`send_email`, `rotate_secret`, `replay`, ...). Path ids
  come first, then the body or the filters, then the keyword-only options of `RequestOptions`.
  `tests/test_operations.py` checks that every operation of the OpenAPI document has exactly one
  method on each client, with the same signature.

## The API contract

`openapi/openapi.json` is a copy of the public document at
https://flashpi.com.ec/docs/openapi.json and `src/flashpi/types/_generated.py` is generated from
it. Never edit either by hand:

```bash
uv run python scripts/openapi.py sync      # download the document and regenerate the types
uv run python scripts/openapi.py generate  # regenerate from the committed copy
```

The `OpenAPI sync` workflow does this every day and opens a pull request when the contract
changes. New operations or fields may need a method or a hand-written type in `src/flashpi/`.

## Commits and releases

Commit with [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`,
`docs:`, `test:`, `ci:`, `chore:`). They drive the version and the changelog:
[release-please](https://github.com/googleapis/release-please) keeps a release pull request
open, and merging it tags the version and publishes it to PyPI from the `Release` workflow, with
PyPI trusted publishing (OIDC, no token) and attestations. release-please writes the version to
`pyproject.toml`, `src/flashpi/_version.py` and the package's own entry in `uv.lock`.

While the version is 0.x, `feat:` raises the minor version and `fix:` the patch version.

The release PR and the OpenAPI sync PR are opened with a token of the organization's GitHub
App, so CI runs on them like on any pull request. (One opened with `GITHUB_TOKEN` would get its
CI only after someone approves it.) The Release workflow also starts the live API test
(`live.yml`) on the release branch each time release-please updates it. A dispatched `ci.yml`
run does not count for a pull request's required checks: to run CI again, re-run the PR's own
checks.

### The GitHub App

An app of the `flashpi1` organization, installed on `flashpi-python` (as on `flashpi-node`), with
no webhook and these repository permissions: Contents, Pull requests and Issues, read and write.
Its Client ID is the repository variable `FLASHPI_BOT_CLIENT_ID` and its private key the
repository secret `FLASHPI_BOT_PRIVATE_KEY`. The workflows create a one-hour token per run with
only the permissions each job needs. To rotate the key, generate a new one in the app's settings,
update the secret, then delete the old key.

The publish job runs in the `pypi` environment, which waits for a maintainer's approval in
GitHub before it publishes.

### PyPI trusted publishing

No PyPI token exists for this project: PyPI trusts the `Release` workflow through OpenID
Connect. PyPI accepts a **pending publisher** for a project that does not exist yet, so every
version, 0.1.0 included, is published by the workflow. Before the first release PR is merged:

1. An owner of the Flashpi PyPI account (PyPI requires two-factor authentication) adds a pending
   publisher at https://pypi.org/manage/account/publishing/: PyPI project name `flashpi`, owner
   `flashpi1`, repository `flashpi-python`, workflow `release.yml`, environment `pypi`. A pending
   publisher does not reserve the name, so add it shortly before the release.
2. In this repository's settings, create the `pypi` environment with the maintainers as required
   reviewers, limited to the `main` branch.
3. Drop the not-on-PyPI notice from both READMEs in its own pull request (PyPI shows `README.md`
   as the project's page).
4. Merge the release PR. release-please tags `v0.1.0`; approve the `pypi` environment, and the
   publish job builds the tag and uploads the sdist and the wheel. The first upload creates the
   project, and the pending publisher becomes its trusted publisher.

From then on, versions are published by the workflow only: do not create PyPI API tokens for
the project.
