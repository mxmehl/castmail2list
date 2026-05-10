<!--
  SPDX-FileCopyrightText: 2025 Max Mehl <https://mehl.mx>
  SPDX-License-Identifier: CC-BY-4.0
-->

# CastMail2List — Agent Instructions

Flask-based mailing-list service: polls IMAP mailboxes, stores messages in a
SQLAlchemy-backed database, and serves a web UI with bounce handling. See
[README.md](../README.md) and [CONTRIBUTING.md](../CONTRIBUTING.md).

- **Stack:** Python 3.10–3.14, Flask, SQLAlchemy, imap-tools
- **Package manager:** uv — always use `uv run` / `uv sync`; never `pip` directly
- **Entry points** (do not rename): `castmail2list-cli` (debug/CLI), `castmail2list` (gunicorn/WSGI)

## Quick Commands

```sh
uv sync                            # install / sync deps
uv run pytest --cov=castmail2list  # unit tests
uv run ruff check                  # lint
uv run ruff format --check         # format check
uv run ty check                    # type check
uv run reuse lint                  # REUSE license compliance
make test-all                      # all checks at once
make translations-compile          # compile Babel translations (en, de)
```

Run debug server: `uv run castmail2list-cli --config config.yaml --debug`
(copy `config.example.yaml` → `config.yaml` first and fill in required keys).

## Architecture

| Layer | Key file(s) |
|-------|-------------|
| App factory & CLI | `castmail2list/app.py` |
| WSGI / gunicorn | `castmail2list/wsgi.py` |
| IMAP polling & processing | `castmail2list/imap_worker.py` |
| DB models | `castmail2list/models.py` |
| Config loading & schema | `castmail2list/config.py` |
| Web views (blueprints) | `castmail2list/views/` |
| Helpers | `castmail2list/utils.py` |
| Tests (in-memory SQLite) | `tests/` |

Feature docs: [modes & headers](../doc/modes_and_headers.md) ·
[sender authorization](../doc/sender_authorization.md) · [API](../doc/api.md).
Read these before changing behaviour in those areas, and update them if you do.

## Conventions

- **Docstrings:** Required on all functions/classes — **Google style**, enforced by ruff.
- **Type annotations:** Required; checked by `ty`. Scope: `castmail2list/` (migrations excluded).
- **Line length:** 100 characters.
- **REUSE:** Every new file needs an SPDX header. Run `uv run reuse lint` to verify.
- **Translations:** Wrap user-visible strings with `_()`. After adding strings: `make translations-update` then `make translations-compile`.
- **DB migrations:** Any schema change requires a new Alembic migration (`flask db migrate -m "…"`). Update seeders and tests accordingly.
- **Conservative changes:** Prefer minimal, well-tested edits. Large refactors need justification and full test coverage.

## Pitfalls

- **Background IMAP thread:** `initialize_imap_polling` is skipped when `app.config['TESTING']` is set. In tests always call `create_app(..., one_off_call=True)` — see `tests/conftest.py`.
- **SCSS at startup:** The app shells out to `sass` on startup. `sass` must be on PATH for the production server but is not needed for tests (`one_off_call=True` skips it).
- **EmailIn composite PK:** `email_in.(message_id, list_id)` is a composite PK. `email_out` holds a compound FK to both columns — handle carefully in queries and migrations.
- **Soft-delete:** `MailingList` is never hard-deleted. Use `.deactivate()` / `.reactivate()`.
- **IMAP in tests:** Use the `fixture_mailbox_stub` fixture (`MailboxStub`) — never open real IMAP connections in tests.

## Validation Checklist Before PR

```sh
uv sync
uv run pytest --cov=castmail2list
uv run ruff check
uv run ruff format --check
uv run ty check
uv run reuse lint
```

All steps must pass. Fix failures; do not disable tests. To reproduce a CI matrix
failure locally: `uv python install <version> && uv sync`, then re-run the failing command.
