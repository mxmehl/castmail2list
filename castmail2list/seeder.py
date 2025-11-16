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

from .models import List, Subscriber, db

DEFAULT_SEED: Dict[str, Any] = {
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
    ]
}


def _merge_defaults(defaults: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge lists and their subscribers from overrides into defaults.
    """
    result = defaults.copy()
    if "lists" in overrides and isinstance(overrides["lists"], list):
        # Replace the entire lists array if present in overrides
        result["lists"] = overrides["lists"]
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


def seed_database(app: None = None) -> None:
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
                subs.append(Subscriber(name=s.get("name"), email=s.get("email"), list=new_list))

            db.session.add(new_list)
            if subs:
                db.session.add_all(subs)

        db.session.commit()
        logging.info("✅ Seed data inserted.")

    if app is not None:
        # push provided app context while seeding
        with app.app_context():
            _do_seed()
    else:
        # assume caller has an active app context
        _do_seed()
