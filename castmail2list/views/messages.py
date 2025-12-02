"""Messages blueprint for CastMail2List application"""

from flask import Blueprint, flash, render_template
from flask_login import login_required

from ..models import EmailIn, EmailOut
from ..utils import get_all_incoming_messages, get_all_outgoing_messages

messages = Blueprint("messages", __name__, url_prefix="/messages")


@messages.route("/")
@login_required
def show_all() -> str:
    """Show all incoming messages including bounces"""
    msgs: list[EmailIn] = get_all_incoming_messages()
    return render_template("messages/index.html", messages=msgs)


@messages.route("/<message_id>")
@login_required
def show(message_id: int) -> str:
    """Show a specific message"""
    # Try incoming messages first
    msg_in: EmailIn | None = EmailIn.query.get(message_id)
    if not msg_in:
        # Try outgoing messages next
        msg_out: EmailOut | None = EmailOut.query.get(message_id)
        if msg_out:
            return render_template("messages/detail_sent.html", message=msg_out)
        flash("Message not found", "error")
    return render_template("messages/detail.html", message=msg_in)


@messages.route("/bounces")
@login_required
def bounces() -> str:
    """Show only bounced messages"""
    return render_template(
        "messages/bounces.html", messages=get_all_incoming_messages(only="bounces")
    )


@messages.route("/sent")
@login_required
def sent() -> str:
    """Show all outgoing messages"""
    return render_template("messages/sent.html", messages=get_all_outgoing_messages())
