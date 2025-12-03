"""Messages blueprint for CastMail2List application"""

from flask import Blueprint, flash, render_template
from flask_babel import _
from flask_login import login_required

from ..models import EmailIn, EmailOut
from ..utils import (
    get_all_incoming_messages,
    get_all_outgoing_messages,
    get_message_id_in_db,
)

messages = Blueprint("messages", __name__, url_prefix="/messages")


@messages.before_request
@login_required
def before_request() -> None:
    """Require login for all routes"""


@messages.route("/")
def index() -> str:
    """Show all normal incoming messages"""
    msgs: list[EmailIn] = get_all_incoming_messages(only="normal")
    return render_template("messages/index.html", messages=msgs)


@messages.route("/<message_id>")
def show(message_id: str) -> str:
    """Show a specific message"""
    message = get_message_id_in_db([message_id])
    if message:
        msg_type = "out" if isinstance(message, EmailOut) else "in"
        bounce = getattr(message, "status", "") == "bounce-msg"
        return render_template(
            "messages/detail.html", message=message, msg_type=msg_type, bounce=bounce
        )
    flash(_("Message not found"), "error")
    return render_template("messages/detail.html", message=None)


@messages.route("/bounces")
def bounces() -> str:
    """Show only bounced messages"""
    return render_template(
        "messages/bounces.html", messages=get_all_incoming_messages(only="bounces")
    )


@messages.route("/sent")
def sent() -> str:
    """Show all outgoing messages"""
    return render_template("messages/sent.html", messages=get_all_outgoing_messages())
