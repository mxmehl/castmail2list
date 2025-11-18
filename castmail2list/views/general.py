"""Flask routes for castmail2list application"""

from flask import Blueprint, flash, render_template
from flask_babel import _
from flask_login import login_required

from ..config import Config
from ..models import List, Subscriber

general = Blueprint("general", __name__)


@general.route("/")
@login_required
def index():
    """Show dashboard"""
    active_lists: list[List] = List.query.filter_by(deleted=False).all()
    return render_template("index.html", lists=active_lists)


@general.route("/subscriber/<email>")
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
        mailing_list: List | None = List.query.get(sub.list_id)
        if mailing_list:
            subscriber_lists.append({"list": mailing_list, "subscriber": sub})

    return render_template("subscriber.html", email=email, subscriber_lists=subscriber_lists)


@general.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    """Manage application settings"""

    return render_template("settings.html", config=Config)
