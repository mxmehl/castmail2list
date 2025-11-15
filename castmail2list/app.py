"""Flask app for CastMail2List"""

import argparse
import threading
from logging.config import dictConfig

from flask import Flask

from .config import Config
from .imap_worker import poll_imap
from .models import List, Message, db

dictConfig(
    {
        "version": 1,
        "formatters": {
            "default": {
                "format": "[%(asctime)s] %(levelname)s in %(module)s: %(message)s",
            }
        },
        "handlers": {
            "wsgi": {
                "class": "logging.StreamHandler",
                "stream": "ext://flask.logging.wsgi_errors_stream",
                "formatter": "default",
            }
        },
        "root": {"level": "DEBUG", "handlers": ["wsgi"]},
    }
)


def create_app():
    """Create Flask app"""
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)

    with app.app_context():
        db.create_all()

    @app.route("/")
    def index():
        lists = List.query.all()
        return "<h2>Lists</h2>" + "<br>".join(
            [f"{l.name} ({len(l.subscribers)} subs)" for l in lists]
        )

    @app.route("/messages")
    def messages():
        msgs = Message.query.order_by(Message.received_at.desc()).limit(20).all()
        return "<br>".join([f"{m.received_at} - {m.subject}" for m in msgs])

    # start background IMAP thread
    t = threading.Thread(target=poll_imap, args=(app,), daemon=True)
    t.start()

    return app


def main():
    """Run the app"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-H", "--host", default="127.0.0.1")
    parser.add_argument("-p", "--port", default=5000, type=int)
    parser.add_argument("--debug", action="store_true", help="Run in debug mode (development only)")
    args = parser.parse_args()

    app = create_app()
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
