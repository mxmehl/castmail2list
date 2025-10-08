"""Flask routes for castmail2list application"""

from flask import Flask

from .models import List, Message


def init_routes(app: Flask):
    """Initialize Flask routes"""
    @app.route("/")
    def index():
        lists = List.query.all()
        return "<h2>Lists</h2>" + "<br>".join(
            [f"{l.name} ({len(l.subscribers)} subs)" for l in lists]
        )

    @app.route("/messages")
    def messages() -> str:
        msgs: list[Message] = Message.query.order_by(Message.received_at.desc()).limit(20).all()
        return "<br>".join([f"{m.received_at} - {m.subject}" for m in msgs])
