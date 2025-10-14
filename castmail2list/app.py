"""Flask app for CastMail2List"""

import argparse
import threading
from logging.config import dictConfig

from flask import Flask
from flask_migrate import Migrate
from sassutils.wsgi import SassMiddleware

from .config import Config
from .imap_worker import poll_imap
from .models import db
from .views import init_routes


def configure_logging(debug: bool) -> None:
    """Configure logging"""
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
            "root": {"level": "DEBUG" if debug else "INFO", "handlers": ["wsgi"]},
        }
    )


def create_app() -> Flask:
    """Create Flask app"""
    app = Flask(__name__)
    app.config.from_object(Config)

    # Database
    db.init_app(app)
    Migrate(app, db)
    with app.app_context():
        db.create_all()

    # Settings for SCSS conversion
    app.wsgi_app = SassMiddleware(  # type: ignore
        app.wsgi_app,
        {
            "castmail2list": {
                "sass_path": "static/scss",
                "css_path": "static/css",
                "wsgi_path": "/static/css",
                "strip_extension": False,
            }
        },
    )

    # Import routes
    init_routes(app)

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

    configure_logging(args.debug)

    app = create_app()
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
