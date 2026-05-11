<!--
  SPDX-FileCopyrightText: 2025 Max Mehl <https://mehl.mx>
  SPDX-License-Identifier: CC-BY-4.0
-->

# Contributing to CastMail2List

Thank you for your interest in contributing! This guide covers the development setup, quality checks, and translation workflow.

## Prerequisites

- Python 3.10 or newer
- [uv](https://docs.astral.sh/uv/getting-started/installation/) for dependency management

## Development setup

Clone the repository and install all dependencies (including dev tools):

```sh
git clone https://github.com/mxmehl/castmail2list.git
cd castmail2list
uv sync
```

This creates a virtual environment in `.venv/` and installs all runtime and development dependencies.

## Running the app locally

```sh
cp config.example.yaml config.yaml
# Edit config.yaml with your settings
uv run castmail2list-cli --config config.yaml --debug
```

## Configuration changes

When you add, remove, or edit a configuration item (including default values), keep all config
sources in sync in the same PR.

Checklist:

1. Update the runtime default in `AppConfig` in `castmail2list/config.py`.
2. Update the schema in `castmail2list/config_schema.json`:
   - Keep the `type`/validation constraints aligned with runtime behavior.
   - Update `description` text.
   - Update `default` to match `AppConfig`.
3. Update `config.example.yaml`:
   - Add or update the setting value.
   - Add or update the preceding comment with description and default value.
4. If behavior or recommended values changed, update user-facing docs (at least `README.md`, and
   related files in `doc/` where applicable).

## Quality checks

The project uses the following tools for code quality:

| Tool | Purpose |
|---|---|
| [ruff](https://docs.astral.sh/ruff/) | Linting and formatting (replaces pylint, black, isort) |
| [ty](https://docs.astral.sh/ty/) | Type checking (replaces mypy) |
| [pytest](https://docs.pytest.org/) | Unit tests with coverage |

### Running checks individually

```sh
uv run pytest --cov=castmail2list   # Tests with coverage
uv run ruff check                   # Linting
uv run ruff format --check          # Formatting check
uv run ty check                     # Type checking
```

### Running all checks at once

With Makefile:

```sh
make test-all
```

### Auto-fixing issues

```sh
uv run ruff check --fix     # Auto-fix lint issues
uv run ruff format           # Auto-format code
```

### Code style notes

- Line length: 100 characters
- Docstrings: Google style, enforced by ruff
- All public functions and classes need docstrings
- Type annotations are expected and checked by ty

## Translations

CastMail2List uses [Flask-Babel](https://python-babel.github.io/flask-babel/) for internationalization. The UI is currently available in English (default) and German.

### Compiling translations

Translations must be compiled before they are available at runtime. **This step is required after cloning or after updating `.po` files:**

```sh
make translations-compile
# or: uv run pybabel compile -d castmail2list/translations
```

### Adding a new language

1. **Initialize the language** (e.g. French):

   ```sh
   uv run pybabel init -i castmail2list/messages.pot -d castmail2list/translations -l fr
   ```

2. **Translate the strings** in `castmail2list/translations/fr/LC_MESSAGES/messages.po` using a PO editor (e.g. [Poedit](https://poedit.net/)) or a text editor.

3. **Compile:**

   ```sh
   make translations-compile
   ```

### Updating existing translations

When translatable strings in the source code or templates change:

```sh
make translations-update
```

This extracts new strings into `messages.pot` and merges them into the existing `.po` files. Review and translate any new or fuzzy entries, then compile.

## Project layout

```
castmail2list/          Main package
├── app.py              Flask app factory and CLI entrypoint
├── wsgi.py             WSGI/gunicorn entrypoint
├── imap_worker.py      IMAP polling and message processing
├── mailer.py           Outbound email composition and sending
├── models.py           SQLAlchemy database models
├── config.py           Configuration loading and validation
├── services.py         Business logic (subscriber CRUD)
├── utils.py            Helper functions
├── views/              Flask blueprints (web UI, API, auth)
├── templates/          Jinja2 HTML templates
├── static/             CSS, JS, fonts
├── translations/       Gettext translation files
└── migrations/         Alembic database migrations
tests/                  Pytest test suite
doc/                    Documentation
scripts/                Utility scripts
```

## Testing notes

- Tests run with an in-memory SQLite database
- The app is created with `one_off_call=True` to avoid starting background IMAP threads
- IMAP interactions are mocked using the `MailboxStub` fixture in `tests/conftest.py`
- SCSS compilation requires `sass` on PATH; tests skip this via `one_off_call=True`

## Submitting changes

1. Create a branch for your changes
2. Ensure all checks pass: `make test-all` (or run them individually)
3. Open a pull request — CI will run the same checks automatically
