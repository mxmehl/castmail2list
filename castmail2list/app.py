import threading

from config import Config
from flask import Flask, render_template
from imap_worker import poll_imap
from models import List, Message, Subscriber, db


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)

    with app.app_context():
        db.create_all()

    @app.route("/")
    def index():
        lists = List.query.all()
        return "<h2>Lists</h2>" + "<br>".join([f"{l.name} ({len(l.subscribers)} subs)" for l in lists])

    @app.route("/messages")
    def messages():
        msgs = Message.query.order_by(Message.received_at.desc()).limit(20).all()
        return "<br>".join([f"{m.received_at} - {m.subject}" for m in msgs])

    # start background IMAP thread
    t = threading.Thread(target=poll_imap, args=(app,), daemon=True)
    t.start()

    return app

if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
