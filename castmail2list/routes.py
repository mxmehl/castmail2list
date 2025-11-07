"""Flask routes for castmail2list application"""

from datetime import datetime, timezone

from flask import Flask, flash, redirect, render_template, url_for
from flask_babel import _
from flask_login import login_required

from .config import Config
from .forms import MailingListForm, SubscriberAddForm
from .models import List, Message, Subscriber, db
from .utils import (
    flash_form_errors,
    get_version_info,
    is_email_a_list,
    normalize_email_list,
)


def init_routes(app: Flask):  # pylint: disable=too-many-statements
    """Initialize Flask routes"""

    # Inject variables into templates
    @app.context_processor
    def inject_vars():
        return {
            "version_info": get_version_info(),
        }

    @app.route("/")
    @login_required
    def index():
        active_lists = List.query.filter_by(deleted=False).all()
        return render_template("index.html", lists=active_lists)

    @app.route("/messages")
    @login_required
    def messages() -> str:
        msgs: list[Message] = Message.query.order_by(Message.received_at.desc()).limit(20).all()
        return render_template("messages.html", messages=msgs)

    @app.route("/subscriber/<email>")
    @login_required
    def subscriber(email):
        """Show which lists a subscriber is part of"""
        # Find all subscriptions for this email address
        email_norm = email.strip().lower()
        subscriptions = Subscriber.query.filter_by(email=email_norm).all()

        if not subscriptions:
            flash(_('No subscriptions found for "%(email)s"', email=email), "warning")
            return render_template("subscriber.html", email=email)

        # Get list information for each subscription
        subscriber_lists = []
        for sub in subscriptions:
            mailing_list = List.query.get(sub.list_id)
            if mailing_list:
                subscriber_lists.append({"list": mailing_list, "subscriber": sub})

        return render_template("subscriber.html", email=email, subscriber_lists=subscriber_lists)

    @app.route("/settings", methods=["GET", "POST"])
    @login_required
    def settings():
        """Manage application settings"""

        return render_template("settings.html", config=Config)
