"""Messages blueprint for CastMail2List application"""

from flask import Blueprint, render_template
from flask_login import login_required

from ..models import Message

messages = Blueprint("messages", __name__, url_prefix="/messages")


@messages.route("/")
@login_required
def show_all() -> str:
    """Show recent messages"""
    msgs: list[Message] = Message.query.order_by(Message.received_at.desc()).limit(20).all()
    return render_template("messages/index.html", messages=msgs)
