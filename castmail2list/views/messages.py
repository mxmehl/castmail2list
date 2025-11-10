"""Messages blueprint for CastMail2List application"""

from flask import Blueprint, flash, render_template
from flask_login import login_required

from ..models import Message

messages = Blueprint("messages", __name__, url_prefix="/messages")


@messages.route("/")
@login_required
def show_all() -> str:
    """Show all messages"""
    msgs: list[Message] = Message.query.all()  # will be reversed in template
    return render_template("messages/index.html", messages=msgs)


@messages.route("/<int:message_id>")
@login_required
def show(message_id: int) -> str:
    """Show a specific message"""
    msg: Message | None = Message.query.get(message_id)
    if not msg:
        flash("Message not found", "error")
    return render_template("messages/detail.html", message=msg)


@messages.route("/bounces")
@login_required
def bounces() -> str:
    """Show bounced messages"""
    bounce_messages: list[Message] = (
        Message.query.filter_by(status="bounce-msg").order_by(Message.received_at.desc()).all()
    )
    return render_template("messages/bounces.html", messages=bounce_messages)
