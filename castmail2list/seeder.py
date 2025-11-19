"""
Database seeding helper for CastMail2List.

It may serve as setting up a demo instance, or allows to pre-seed productive data from a secret file
"""

import json
import logging
import sys
from typing import Any, Dict

from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
from flask import Flask
from werkzeug.security import generate_password_hash

from .models import AlembicVersion, MailingList, Subscriber, User, db


def _load_local_seed(seed_file: str) -> Dict[str, Any]:
    """
    Try to import from a JSON file; return empty dict if not present
    """
    try:
        with open(seed_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except FileNotFoundError:
        logging.critical("No local seed file found at %s.", seed_file)
        sys.exit(1)
    except json.JSONDecodeError as e:
        logging.critical("Error decoding JSON from seed file %s: %s", seed_file, e)
        sys.exit(1)


def seed_database(app: Flask, seed_file: str) -> None:
    """Create tables and seed DB if empty, using local overrides when present.

    Accepts an optional Flask `app`. If provided, this function will push `app.app_context()`
    while seeding. If `app` is None, the caller must have an active application context.

    Args:
        app (Flask): Optional Flask app to push context for seeding
        seed_file (str): Path to a seed file (.py file)
    """

    def _do_seed() -> None:
        # ensure tables exist (app caller should have context)
        db.create_all()

        if MailingList.query.first():
            logging.warning("Database already has lists — skipping seed.")
            return

        cfg: dict[str, list] = _load_local_seed(seed_file=seed_file)

        logging.info("Seeding database with initial data from %s...", seed_file)

        cfg_lists: list[dict[str, str | int | list]] = cfg.get("lists", [])
        for lst_cfg in cfg_lists:
            new_list = MailingList(
                name=lst_cfg.get("name"),
                address=lst_cfg.get("address"),
                mode=lst_cfg.get("mode"),
                imap_host=lst_cfg.get("imap_host"),
                imap_port=lst_cfg.get("imap_port"),
                imap_user=lst_cfg.get("imap_user"),
                imap_pass=lst_cfg.get("imap_pass"),
                from_addr=lst_cfg.get("from_addr"),
                allowed_senders=lst_cfg.get("allowed_senders"),
                only_subscribers_send=lst_cfg.get("only_subscribers_send", True),
            )

            subs = []
            cfg_subs: list[dict[str, str]] = lst_cfg.get("subscribers", [])  # type: ignore
            for s in cfg_subs:
                subs.append(
                    Subscriber(
                        name=s.get("name"),
                        email=s.get("email"),
                        subscriber_type=s.get("subscriber_type"),
                        list=new_list,
                    )
                )

            db.session.add(new_list)
            if subs:
                db.session.add_all(subs)

        cfg_user: list[dict[str, str]] = cfg.get("users", [])
        for user_cfg in cfg_user:
            new_user = User(
                username=user_cfg.get("username"),
                password=generate_password_hash(password=user_cfg.get("password", "")),
            )
            db.session.add(new_user)

        # Get the latest alembic revision and write it into DB
        try:
            alembic_cfg = AlembicConfig()
            alembic_cfg.set_main_option("script_location", "castmail2list:migrations")
            script = ScriptDirectory.from_config(alembic_cfg)
            head_revision = script.get_current_head()
            if not head_revision:
                raise ValueError("No head revision found in Alembic scripts")
            logging.info("Latest Alembic revision: %s", head_revision)
            # Write into alembic_version table if needed
            if not AlembicVersion.query.first():
                alembic_version = AlembicVersion(version_num=head_revision)
                db.session.add(alembic_version)
        except Exception as e:  # pylint: disable=broad-except
            logging.warning("Could not determine or add Alembic revision: %s", e)
            raise e

        db.session.commit()
        logging.info("✅ Seed data inserted.")

    if app is not None:
        # push provided app context while seeding
        with app.app_context():
            _do_seed()
    else:
        # assume caller has an active app context
        _do_seed()
