<!--
  SPDX-FileCopyrightText: 2025 Max Mehl <https://mehl.mx>
  SPDX-License-Identifier: CC-BY-4.0
-->

This file instructs an automated coding agent (Copilot coding agent) how to work
effectively with the castmail2list repository. Keep changes conservative and run the
validation steps exactly as written before creating a pull request.

Summary

- Purpose: CastMail2List is a small Flask-based mailing-list application that polls
  IMAP mailboxes, stores messages in a SQLAlchemy-backed database, and serves a web
  interface. It includes an IMAP worker, bounce handling, and basic list/group modes.
- Languages / frameworks: Python 3.10+ (project declares ^3.10), Flask, SQLAlchemy,
  imap-tools. Project uses Poetry for dependency management and packaging.
- Size: small-to-medium Python web app (top-level package `castmail2list/`, `tests/`,
  `  static/`, `templates/`). Tests exist under `tests/` and use `pytest`.

High-level guidance for an agent

- Be conservative: prefer minimal, well-tested changes. Avoid large refactors unless
  the PR clearly documents why they are necessary and includes tests.
- Preserve public APIs: do not rename script entrypoints listed in `pyproject.toml`
  (e.g. `castmail2list-cli`, `castmail2list`).
- Read documentation in `doc/` for context on mailing list modes and sender
  authorization before changing functionality in those areas. If you change
  functionality, also edit the docs.
- Run the validation pipeline (below) locally in the order given and only open a PR
  when all steps pass. If anything fails, reproduce the failure in CI and fix tests
  rather than disabling them.

Bootstrap / dev environment

- This repo uses Poetry. Always use Poetry-managed virtual environments when running
  commands. Typical bootstrap steps (macOS / Linux / CI):

  - Install a recent Python interpreter 3.10-3.14. The project CI tests 3.10..3.14.
  - Install Poetry (if not present): `pip install poetry`.
  - Create/activate virtualenv and install dependencies (inside repo root):
    `poetry install --with dev` (or `poetry install` then `poetry install --with dev`)

- Notes: The project expects `sass` to be available on PATH when the app starts
  because SCSS is compiled at startup via a simple `sass` command. For tests this is
  not required (tests avoid compiling SCSS), but CI runs lint/formatters which use
  Python-only tools.

Build / test / run / lint (validated commands)

- Install dependencies (required):

  - `poetry install --with dev`

- Run unit tests with coverage (recommended before PR):

  - `poetry run pytest --cov=castmail2list`

- Run the app locally (development):

  - Prepare a config: `cp config.example.yaml config.yaml` and edit `config.yaml` as needed.
  - Run debug server: `poetry run castmail2list-cli --config config.yaml --debug`.
  - For production-style run, use: `poetry run castmail2list --config config.yaml` or
    use the `wsgi.gunicorn()` wrapper: `poetry run python -m castmail2list.wsgi gunicorn`.

- Packaging / build (used by CI):

  - `poetry build` produces `dist/` artifacts.

- Formatting & static checks (CI mirrors these):
  - Lint: `poetry run pylint --disable=fixme castmail2list/`
  - Formatting checks: `poetry run isort --check castmail2list/` then `poetry run black --check .`
  - Typing: `poetry run mypy`

Known CI and checks

- GitHub Actions workflows are in `.github/workflows/`.
  - `test.yaml` runs multiple jobs: matrix with Python 3.10–3.14, `pytest`, packaging,
    `pylint`, `isort`/`black`, and `mypy`.
  - The actions use a local `.github/actions/poetrybuild` helper to install dependencies
    (you do not need to replicate that exactly; using `poetry install` locally is fine).
- Functions and classes need proper docstrings. We use `pylint` to enforce this. It should follow
  the Google style.

Project layout and where to make changes

- Key files and directories (priority order):
  - `pyproject.toml` — project, dependencies, dev tools, scripts. Update here for
    dependency/version changes and console scripts.
  - `castmail2list/` — main package. Primary modules:
    - `app.py` — Flask app factory, CLI entrypoint and configuration handling.
    - `wsgi.py` — WSGI entrypoint and gunicorn helper.
    - `imap_worker.py` — IMAP polling and incoming message processing. Tests target this
      heavily; be careful making behavior changes.
    - `models.py` — SQLAlchemy models and DB schema.
    - `utils.py` — helper functions (email parsing, SCSS compilation, config path helpers).
    - `mailer.py`, `seeder.py`, `views/`, `templates/`, `static/` — supporting code.
  - `doc/` — documentation, e.g. for mailing list modes and sender authorization.
  - `tests/` — pytest test suite. Tests create an in-memory SQLite DB and rely on
    `create_app(..., one_off_call=True)` to avoid starting background threads.

Tips for safe edits and common pitfalls

- Tests: they run with an in-memory SQLite DB. Ensure any DB changes (migrations, new
  columns) include model changes and adjustments in tests or seeders.
- App background threads: `initialize_imap_polling` checks `app.config['TESTING']`.
  When running tests or one-off CLI commands ensure `one_off_call=True` or `TESTING`
  set to True to avoid background threads and network I/O during test runs.
- External services: IMAP connections, `sass` cli, and system-specific commands are
  used in some utilities. Avoid invoking them in tests or mock them. Use the existing
  `MailboxStub` fixture for IMAP-related tests.
- SCSS compilation: the app calls `sass` via `subprocess` on startup. CI doesn't run the
  server; if your change adds code executed during import/creation ensure it’s robust
  when `sass` is missing (or skip compilation in tests by using `one_off_call=True`).

Validation checklist before creating a PR

- Run these locally in the workspace root and confirm they pass in sequence:
  1. `poetry install --with dev`
  2. `poetry run pytest --cov=castmail2list`
  3. `poetry run pylint --disable=fixme castmail2list/ tests/` (address new warnings only)
  4. `poetry run isort --check castmail2list/ tests/` and `poetry run black --check .`
  5. `poetry run mypy`
  6. `poetry build` (optional for packaging changes)

If CI fails after a PR is opened

- Reproduce the failure locally with the same Python version as the failing matrix job
  (CI shows matrix entry). Run the failing job steps locally with `poetry env use <py>`
  and `poetry install`, then re-run the failing commands.

Search guidance for the agent

- Prefer editing files under `castmail2list/` and `tests/` only. Use `pyproject.toml`
  to learn supported tooling and versions.
- Only search the repo when the instructions above are insufficient; trust this file
  first (it encodes repository conventions and CI steps). If you must search, favor
  these files in order: `pyproject.toml`, `.github/workflows/test.yaml`, `README.md`,
  `tests/conftest.py`, `castmail2list/app.py`, `castmail2list/imap_worker.py`.

Final note

- This onboarding file is intentionally conservative and practical: ensure your PRs
  include tests for behavioral changes and pass the local validation checklist before
  requesting review.
