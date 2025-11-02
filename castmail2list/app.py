"""Flask app for CastMail2List"""

import argparse
import logging
import threading
from logging.config import dictConfig

from flask import Flask
from flask_babel import Babel
from flask_migrate import Migrate
from sassutils.wsgi import SassMiddleware

from .config import Config
from .imap_worker import poll_imap
from .models import db
from .seeder import seed_database
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

    # Translations
    Babel(app, default_locale=app.config.get("LANGUAGE", "en"))
    logging.info("Language set to: %s", app.config.get("LANGUAGE", "en"))

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
    parser.add_argument("--seed-only", action="store_true", help="Seed the database and exit")
    parser.add_argument(
        "--seed", action="store_true", help="Seed the database and continue to start the server"
    )
    args = parser.parse_args()

    configure_logging(args.debug)

    app = create_app()

    # seeding actions
    if args.seed_only:
        seed_database(app)
        print("Database seeded (seed-only).")
        return

    if args.seed:
        seed_database(app)

    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
