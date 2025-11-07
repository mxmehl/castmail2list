"""
Database seeding helper.

Optional local overrides:
Create castmail2list/local_secrets.py (ignored) and set a SEED dict, for example:

SEED = {
    "list": {
        "name": "Custom Announcements",
        "address": "custom@example.com",
        "imap_pass": "supersecret-from-local",
    },
    "subscribers": [
        {"name": "Carol", "email": "carol@example.com"},
    ],
}
"""

import logging
from typing import Any, Dict

from alembic.config import Config
from alembic.script import ScriptDirectory
from flask import Flask
from werkzeug.security import generate_password_hash

from .models import AlembicVersion, List, Subscriber, User, db

DEFAULT_SEED: Dict[str, Any] = {
    "users": [
        {
            "username": "admin",
            "password": "admin",
        }
    ],
    "lists": [
        {
            "name": "General Announcements",
            "address": "general@example.com",
            "mode": "broadcast",
            "imap_host": "imap.example.com",
            "imap_port": 993,
            "imap_user": "general@example.com",
            "imap_pass": "supersecret",
            "from_addr": "no-reply@example.com",
            "allowed_senders": "admin@example.com",
            "only_subscribers_send": False,
            "subscribers": [
                {"name": "Alice", "email": "alice@example.com"},
                {"name": "Bob", "email": "bob@example.com"},
            ],
        },
        {
            "name": "Group Chat",
            "address": "group@example.com",
            "mode": "group",
            "imap_host": "imap.example.com",
            "imap_port": 993,
            "imap_user": "general@example.com",
            "imap_pass": "supersecret",
            "from_addr": "",
            "allowed_senders": "",
            "only_subscribers_send": True,
            "subscribers": [
                {"name": "Carol", "email": "carol@example.com"},
            ],
        },
    ],
}


def _merge_defaults(defaults: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge local secrets overrides into defaults.
    """
    result = defaults.copy()
    if "lists" in overrides and isinstance(overrides["lists"], list):
        # Replace the entire lists array if present in overrides
        result["lists"] = overrides["lists"]
    if "users" in overrides and isinstance(overrides["users"], list):
        # Replace the entire users array if present in overrides
        result["users"] = overrides["users"]
    return result


def _load_local_seed() -> Dict[str, Any]:
    """
    Try to import local_secrets.SEED from package; return empty dict if not present
    """
    try:
        from . import local_secrets  # pylint: disable=import-outside-toplevel
    except Exception:  # pylint: disable=broad-except
        return {}
    return getattr(local_secrets, "SEED", {}) or {}


def seed_database(app: Flask) -> None:
    """Create tables and seed DB if empty, using local overrides when present.

    Accepts an optional Flask `app`. If provided, this function will push `app.app_context()`
    while seeding. If `app` is None, the caller must have an active application context.
    """

    def _do_seed() -> None:
        # ensure tables exist (app caller should have context)
        db.create_all()

        if List.query.first():
            logging.debug("Database already has lists — skipping seed.")
            return

        local = _load_local_seed()
        cfg = _merge_defaults(DEFAULT_SEED, local)

        logging.info("Seeding database with initial data (overrides present: %s).", bool(local))

        for lst_cfg in cfg.get("lists", []):
            # ensure port is int
            try:
                lst_cfg["imap_port"] = int(lst_cfg.get("imap_port", 993))
            except (TypeError, ValueError):
                lst_cfg["imap_port"] = 993

            new_list = List(
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
            for s in lst_cfg.get("subscribers", []):
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

        for user_cfg in cfg.get("users", []):
            new_user = User(
                username=user_cfg.get("username"),
                password=generate_password_hash(user_cfg.get("password")),
            )
            db.session.add(new_user)

        # Get the latest alembic revision and write it into DB
        try:
            alembic_cfg = Config("alembic.ini")
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

        db.session.commit()
        logging.info("✅ Seed data inserted.")

    if app is not None:
        # push provided app context while seeding
        with app.app_context():
            _do_seed()
    else:
        # assume caller has an active app context
        _do_seed()
