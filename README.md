<!--
  SPDX-FileCopyrightText: 2025 Max Mehl <https://mehl.mx>
  SPDX-License-Identifier: CC-BY-4.0
-->

# CastMail2List

[![Test suites](https://github.com/mxmehl/castmail2list/actions/workflows/test.yaml/badge.svg)](https://github.com/mxmehl/castmail2list/actions/workflows/test.yaml)
[![REUSE status](https://api.reuse.software/badge/github.com/mxmehl/castmail2list)](https://api.reuse.software/info/github.com/mxmehl/castmail2list)
[![The latest version can be found on PyPI.](https://img.shields.io/pypi/v/castmail2list.svg)](https://pypi.org/project/castmail2list/)
[![Information on what versions of Python are supported can be found on PyPI.](https://img.shields.io/pypi/pyversions/castmail2list.svg)](https://pypi.org/project/castmail2list/)

CastMail2List is a lightweight, self-hosted mailing list application. It polls standard IMAP mailboxes for incoming messages, distributes them to subscribers, and provides a web interface for list management. No MTA configuration, no complex server setup — just point it at one or more IMAP accounts and go.

## Why CastMail2List?

**Compared to plain email forwarding:**

- Subscriber management with a web UI and REST API
- Two list modes: **broadcast** (newsletters/announcements) and **group** (discussion lists)
- Sender authorization via allowed-sender lists or password-based authentication
- Automatic bounce detection
- Duplicate message prevention
- Per-list IMAP accounts — each list can use its own mailbox
- Message logs, delivery tracking, and rejection notifications

**Compared to Mailman 3 or similar:**

- Minimal dependencies — runs on Python 3.10+, SQLite, and any IMAP/SMTP provider
- No MTA integration required — works with any email provider that offers IMAP and SMTP
- Simple YAML-based configuration
- Hierarchical list support via nested lists (lists can subscribe to other lists)
- Easy to deploy on shared hosting ([Uberspace](https://uberspace.de/) natively supported) or as a container
- Single process, small footprint - suitable for personal use or small communities

CastMail2List is not a replacement for Mailman in large-scale or enterprise setups. It's designed for people who want mailing list functionality without the operational overhead of running a full mail server stack.

## Features

- **Broadcast mode** — one-to-many distribution (newsletters, announcements). Only authorized senders can post.
- **Group mode** — many-to-many discussion lists with reply-to-list behavior.
- **Web interface** — manage lists, subscribers, messages, and delivery logs.
- **REST API** — programmatic subscriber management with API key authentication.
- **IMAP-based** — polls mailboxes on a configurable interval; no MTA hooks needed.
- **Bounce handling** — detects bounced messages and tracks per-subscriber bounce counts.
- **Sender authorization** — allowed-sender lists and/or password-in-address authentication.
- **Rejection notifications** — optionally notify senders when their message is rejected.
- **Nested lists** — lists can include other lists as subscribers for hierarchical distribution.
- **Internationalization** — UI available in English and German; extensible via standard gettext.
- **Database migrations** — schema changes handled automatically via Alembic/Flask-Migrate.

## Installation

### From PyPI

```sh
pip install castmail2list
```

### From source

```sh
git clone https://github.com/mxmehl/castmail2list.git
cd castmail2list
uv sync --no-dev
```

## Quick start

1. **Create a configuration file:**

   ```sh
   cp config.example.yaml config.yaml
   ```

2. **Edit `config.yaml`** with your IMAP/SMTP credentials, database path, and other settings. See `config.example.yaml` for all available options.

3. **Run the application:**

   For production (using gunicorn as WSGI server):

   ```sh
   castmail2list --config config.yaml
   ```

   For development and admin commands (using Flask directly):

   ```sh
   castmail2list-cli --config config.yaml --debug
   ```

4. **Access the web interface** at `http://localhost:2278` and log in with the credentials set in your configuration.

Run `castmail2list --help` or `castmail2list-cli --help` for all available options.

## Configuration

CastMail2List is configured via a YAML file. See [`config.example.yaml`](config.example.yaml) for the full reference.

The configuration file is validated against a JSON schema (`castmail2list/config_schema.json`) to ensure all required fields are present and correctly formatted. This is the single source of truth for configuration options, their types, and default values. The application will fail to start if the configuration file is invalid.

## Documentation

- [Mailing list modes and headers](doc/modes_and_headers.md) — how broadcast and group modes differ
- [Sender authorization](doc/sender_authorization.md) — controlling who can send to a list
- [API documentation](doc/api.md) — REST API for subscriber management
- [Contributing](CONTRIBUTING.md) — development setup, testing, and translation guide

## Contributing

Contributions and translations are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, testing, and translation guidelines.

## Copyright and Licensing

This project is mainly licensed under the Apache License 2.0, copyrighted by Max Mehl.

It also contains files from different copyright holders and under different licenses. As the project follows the [REUSE](https://reuse.software) best practices, you can find the according information for each individual file.
