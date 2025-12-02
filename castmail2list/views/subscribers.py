"""Flask routes for subscriber details"""

from flask import Blueprint, flash, render_template
from flask_babel import _
from flask_login import login_required

from ..models import MailingList, Subscriber, db
from ..utils import get_all_subscribers, is_email_a_list

subscribers = Blueprint("subscribers", __name__, url_prefix="/subscribers")


@subscribers.before_request
@login_required
def before_request() -> None:
    """Require login for all routes"""


@subscribers.route("/")
def index():
    """Show all subscribers across all lists"""
    return render_template("subscribers/index.html", subscribers=get_all_subscribers())


@subscribers.route("/<email>")
def by_email(email: str):
    """Show which lists a subscriber is part of"""
    # Find all subscriptions for this email address
    email_norm = email.strip().lower()
    subscriptions: list[Subscriber] = Subscriber.query.filter_by(email=email_norm).all()

    if not subscriptions:
        flash(_('No subscriptions found for "%(email)s"', email=email), "warning")
        return render_template("subscribers/by_email.html", email=email), 404

    # Get list information for each subscription
    subscriber_lists = []
    for sub in subscriptions:
        mailing_list: MailingList | None = db.session.get(MailingList, sub.list_id)
        if mailing_list:
            subscriber_lists.append({"list": mailing_list, "subscriber": sub})

    # Flash if subscriber is itself a list
    if is_email_a_list(email):
        flash(_("Note: This subscriber is a mailing list."), "message")

    return render_template(
        "subscribers/by_email.html", email=email, subscriber_lists=subscriber_lists
    )
