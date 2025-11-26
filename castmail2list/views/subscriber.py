"""Flask routes for subscriber details"""

from flask import Blueprint, flash, render_template
from flask_babel import _
from flask_login import login_required

from ..models import MailingList, Subscriber, db

subscribers = Blueprint("subscriber", __name__, url_prefix="/subscriber")


@subscribers.route("/<email>")
@login_required
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

    return render_template(
        "subscribers/by_email.html", email=email, subscriber_lists=subscriber_lists
    )
