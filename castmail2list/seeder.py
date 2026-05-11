# SPDX-FileCopyrightText: 2025 Max Mehl <https://mehl.mx>
#
# SPDX-License-Identifier: Apache-2.0

"""
Database seeding helper for CastMail2List.

It may serve as setting up a demo instance, or allows to pre-seed productive data from a secret file
"""

import json
import logging
import sys
from pathlib import Path
from typing import Any

from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
from flask import Flask
from werkzeug.security import generate_password_hash

from .models import AlembicVersion, MailingList, Subscriber, User, db


def _load_local_seed(seed_file: str) -> dict[str, Any]:
    """Try to import from a JSON file; return empty dict if not present."""
    try:
        with Path(seed_file).open(encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logging.critical("No local seed file found at %s.", seed_file)
        sys.exit(1)
    except json.JSONDecodeError as e:
        logging.critical("Error decoding JSON from seed file %s: %s", seed_file, e)
        sys.exit(1)


def seed_database(app: Flask, seed_file: str) -> None:  # noqa: C901, PLR0915
    """Create tables and seed DB if empty, using local overrides when present.

    Accepts an optional Flask `app`. If provided, this function will push `app.app_context()`
    while seeding. If `app` is None, the caller must have an active application context.

    Args:
        app (Flask): Optional Flask app to push context for seeding
        seed_file (str): Path to a seed file (.py file)
    """

    def _do_seed() -> None:  # noqa: C901, PLR0912, PLR0915
        # ensure tables exist (app caller should have context)
        db.create_all()

        if MailingList.query.first():
            logging.warning("Database already has lists — skipping seed.")
            return

        cfg: dict[str, Any] = _load_local_seed(seed_file=seed_file)

        logging.info("Seeding database with initial data from %s...", seed_file)

        cfg_lists_raw = cfg.get("lists", [])
        cfg_lists: list[dict[str, Any]] = cfg_lists_raw if isinstance(cfg_lists_raw, list) else []
        for lst_cfg in cfg_lists:
            if not isinstance(lst_cfg, dict):
                continue

            list_kwargs: dict[str, str | int | bool | list] = {}
            for field in (
                "id",
                "address",
                "display",
                "mode",
                "imap_host",
                "imap_port",
                "imap_user",
                "imap_pass",
                "from_addr",
                "allowed_senders",
            ):
                value = lst_cfg.get(field)
                if isinstance(value, (str, int, bool, list)):
                    list_kwargs[field] = value

            only_subscribers_send = lst_cfg.get("only_subscribers_send", True)
            list_kwargs["only_subscribers_send"] = (
                only_subscribers_send if isinstance(only_subscribers_send, bool) else True
            )

            new_list = MailingList(**list_kwargs)

            cfg_subs_raw = lst_cfg.get("subscribers", [])
            cfg_subs: list[dict[str, Any]] = cfg_subs_raw if isinstance(cfg_subs_raw, list) else []
            subs: list[Subscriber] = []
            for s in cfg_subs:
                if not isinstance(s, dict):
                    continue

                email = s.get("email")
                if not isinstance(email, str):
                    continue

                sub_kwargs: dict[str, str | int] = {
                    "email": email,
                    "list_id": new_list.id,
                }

                name = s.get("name")
                if isinstance(name, str):
                    sub_kwargs["name"] = name

                subscriber_type = s.get("subscriber_type")
                if isinstance(subscriber_type, str):
                    sub_kwargs["subscriber_type"] = subscriber_type

                subs.append(Subscriber(**sub_kwargs))

            db.session.add(new_list)
            if subs:
                db.session.add_all(subs)

        cfg_user_raw = cfg.get("users", [])
        cfg_user: list[dict[str, Any]] = cfg_user_raw if isinstance(cfg_user_raw, list) else []
        for user_cfg in cfg_user:
            if not isinstance(user_cfg, dict):
                continue

            username = user_cfg.get("username")
            if not isinstance(username, str):
                continue

            password = user_cfg.get("password", "")
            password_str = password if isinstance(password, str) else ""

            user_kwargs: dict[str, str | int] = {
                "username": username,
                "password": generate_password_hash(password=password_str),
            }

            api_key = user_cfg.get("api_key")
            if isinstance(api_key, str):
                user_kwargs["api_key"] = api_key

            new_user = User(**user_kwargs)
            db.session.add(new_user)

        # Get the latest alembic revision and write it into DB
        try:
            alembic_cfg = AlembicConfig()
            alembic_cfg.set_main_option("script_location", "castmail2list:migrations")
            script = ScriptDirectory.from_config(alembic_cfg)
            head_revision = script.get_current_head()
            if not head_revision:
                msg = "No head revision found in Alembic scripts"
                raise ValueError(msg)  # noqa: TRY301
            logging.info("Latest Alembic revision: %s", head_revision)
            # Write into alembic_version table if needed
            if not AlembicVersion.query.first():
                alembic_version = AlembicVersion(version_num=head_revision)
                db.session.add(alembic_version)
        except Exception as e:
            logging.warning("Could not determine or add Alembic revision: %s", e)
            raise

        db.session.commit()
        logging.info("✅ Seed data inserted.")

    if app is not None:
        # push provided app context while seeding
        with app.app_context():
            _do_seed()
    else:
        # assume caller has an active app context
        _do_seed()
